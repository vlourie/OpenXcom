"""DECISION ENGINE FOUNDATION, read only, over the 48 D0 battles: an exchange of targets between two shooters of one enemy turn.
S1 fired at T1 with a comrade in the line or next to T1; S2 fired later on the same turn at T2. From the bench's own list of attacks S1 held a line to T2 and S2 a line to T1 at their decisions, and the exchange leaves both lines clean: both soldiers keep a shot, both targets stay under fire, the comrade is out of the line.
Chances are the list's, before range; the distances show what the exchange costs."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
A = Path("E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30/res_scpa.zip")
KV = re.compile(r"(\w+)=([^ ]*)")
POS = re.compile(r"\((-?\d+),(-?\d+),(-?\d+)\)")
ATT = {7, 8, 9}  # auto, snap, aimed: a throw (6) is listed with a line at any distance, it is no shot to exchange for


def kv(s):
    return dict(KV.findall(s))


def lane(a, b, p):
    bx, by = b[0] - a[0], b[1] - a[1]
    px, py = p[0] - a[0], p[1] - a[1]
    n = bx * bx + by * by
    if not n:
        return 99, 0
    t = (px * bx + py * by) / n
    dx, dy = px - t * bx, py - t * by
    return (dx * dx + dy * dy) ** 0.5, t


def danger(me, to, com):
    out = []
    for w, p in com.items():
        if p == me or p[2] not in (me[2], to[2]):
            continue
        d, t = lane(me, to, p)
        if (d <= 1.0 and 0 < t < 1) or max(abs(p[0] - to[0]), abs(p[1] - to[1])) <= 1:
            out.append(w)
    return out


zf = zipfile.ZipFile(A)
C = Counter()
per = Counter()
samples = []
named = []
for n in sorted(x for x in zf.namelist() if x.endswith("openxcom.log.gz")):
    name = n.split("/")[-2].replace("scpa_D_", "")
    L = [x.rstrip("\n").split("\t")[-1] for x in gzip.open(io.BytesIO(zf.read(n)), "rt", encoding="utf-8", errors="replace")]
    acts = {}
    for s in L:
        m = re.match(r"\[AICAND\] acts=(\w+) unit=\d+ list=(.*)", s)
        if m:
            try:
                acts[m.group(1)] = json.loads(m.group(2))
            except json.JSONDecodeError:
                pass
    pos = {}
    side1 = set()
    out = set()
    D = []
    for i, s in enumerate(L):
        if s.startswith("[AISTATE] before"):
            k = kv(s)
            m = POS.match(k.get("pos", ""))
            if m:
                pos[k["unit"]] = tuple(int(v) for v in m.groups())
            if k.get("faction") == "1":
                side1.add(k["unit"])
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            m = POS.match(k.get("from", ""))
            if m:
                pos[k["unit"]] = tuple(int(v) for v in m.groups())
            if k.get("side") == "1":
                side1.add(k["unit"])
            D.append({"i": i, "k": k, "pos": dict(pos), "out": set(out)})
        elif s.startswith("[AIREC]") and D and '"base"' in s:
            try:
                j = json.loads(s[8:])
            except json.JSONDecodeError:
                continue
            D[-1]["b"] = j.get("base") or {}
            D[-1]["c"] = j.get("cand") or {}
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            u = str(j.get("unit"))
            if j.get("pos"):
                pos[u] = tuple(j["pos"])
            if D and D[-1]["k"]["unit"] == u:
                D[-1]["ex"] = j
        elif s.startswith("[AICASUALTY]"):
            out.add(kv(s).get("victim"))
    byturn = defaultdict(list)
    for d in D:
        if d["k"].get("side") != "1" or not d.get("b"):
            continue
        b = d["b"]
        ex = d.get("ex") or {}
        if b.get("t") not in ATT or not b.get("to") or not ex.get("spent", 0):
            continue
        u = d["k"]["unit"]
        me = d["pos"].get(u)
        if not me:
            continue
        opts = {}
        for c in acts.get(d["c"].get("acts"), []):
            if c.get("k") == "a" and c.get("t") in ATT and c.get("lof") == 1 and 0 <= c.get("u", -1) < 1000000 and c.get("tu", 0) <= int(d["k"]["tu"]) and c.get("p", 0) > 0:
                o = opts.get(c["u"])
                if not o or c["p"] > o["p"]:
                    opts[c["u"]] = c
        tgt = next((f for f, c in opts.items() if tuple(c["to"]) == tuple(b["to"])), None)
        if tgt is None:
            C["attack whose target is not in the list with a line"] += 1
            continue
        com = {w: p for w, p in d["pos"].items() if w in side1 and w != u and w not in d["out"]}
        d.update(u=u, me=me, opts=opts, tgt=tgt, com=com, dang=danger(me, tuple(b["to"]), com), f=ex.get("fdmg", 0), dm=ex.get("dmg", 0), dn=ex.get("fdowned", 0))
        byturn[int(d["k"]["turn"])].append(d)
        C["attacks"] += 1
        if d["dang"]:
            C["attacks at risk"] += 1
            C["at risk: fdmg"] += d["f"]
            C["at risk: downed"] += d["dn"]
    seen1 = set()
    for t, v in byturn.items():
        for a, d1 in enumerate(v):
            if not d1["dang"]:
                continue
            for d2 in v[a + 1:] + v[:a]:
                if d2["u"] == d1["u"] or d2["tgt"] == d1["tgt"]:
                    continue
                if d2["tgt"] not in d1["opts"] or d1["tgt"] not in d2["opts"]:
                    continue
                t2 = d1["opts"][d2["tgt"]]
                t1 = d2["opts"][d1["tgt"]]
                if danger(d1["me"], tuple(t2["to"]), d1["com"]) or danger(d2["me"], tuple(t1["to"]), d2["com"]):
                    continue
                C["exchange pairs"] += 1
                if d1["i"] in seen1:
                    continue
                seen1.add(d1["i"])
                C["attacks with an exchange"] += 1
                C["their fdmg"] += d1["f"]
                C["their dmg"] += d1["dm"]
                C["their downed"] += d1["dn"]
                C["hurt"] += 1 if d1["f"] else 0
                per[name] += 1
                C["comrades, sum"] += len(d1["com"])
                C["attacks in the list, sum of targets"] += len(d1["opts"])
                # a named victim: a casualty line right after this decision, killer S1, victim in the line
                nxt = next((x["i"] for x in D if x["i"] > d1["i"]), len(L))
                cas = [kv(s) for s in L[d1["i"]:nxt] if s.startswith("[AICASUALTY]")]
                own = [k for k in cas if k.get("killer") == d1["u"] and k.get("vfaction") == "1"]
                if own:
                    C["with a named own victim"] += 1
                    if any(k.get("victim") in d1["dang"] for k in own):
                        C["...the victim is the comrade in the line"] += 1
                    named.append(dict(b=name, t=t, S1=d1["u"], at=d1["me"], w=d1["b"].get("w"), src=d1["b"].get("src"), T1=(d1["tgt"], d1["opts"][d1["tgt"]]["to"], d1["opts"][d1["tgt"]]["p"], d1["opts"][d1["tgt"]]["d"]), inline=d1["dang"], T2=(d2["tgt"], t2["to"], t2["p"], t2["d"]), S2=d2["u"], S2at=d2["me"], S2src=d2["b"].get("src"), S2_on_T1=(t1["p"], t1["d"]), S2_on_T2=(d2["opts"][d2["tgt"]]["p"], d2["opts"][d2["tgt"]]["d"]), S2dmg=d2["dm"], S2f=d2["f"], order="S1 first" if d1["i"] < d2["i"] else "S2 first", victims=[(k.get("victim"), k.get("how"), k.get("pos"), k.get("type")) for k in own], fdmg=d1["f"], dmg=d1["dm"]))
                # the list's chance and distance for the shot given up and the shot taken
                c1 = d1["opts"][d1["tgt"]]
                C["sum dist, given up"] += c1["d"]
                C["sum dist, taken"] += t2["d"]
                C["sum p, given up"] += c1["p"]
                C["sum p, taken"] += t2["p"]
                if d1["f"] and len(samples) < 14:
                    samples.append(dict(b=name, t=t, S1=d1["u"], S1at=d1["me"], w=d1["b"].get("w"), T1=(d1["tgt"], c1["to"], c1["p"], c1["d"]), T2=(d2["tgt"], t2["to"], t2["p"], t2["d"]), inline=d1["dang"], fdmg=d1["f"], dn=d1["dn"], dmg=d1["dm"], S2=d2["u"], S2at=d2["me"], S2_T1=(t1["p"], t1["d"]), S2_T2=(d2["opts"][d2["tgt"]]["p"], d2["opts"][d2["tgt"]]["d"]), S2dmg=d2["dm"], S2f=d2["f"], order="S1 first" if d1["i"] < d2["i"] else "S2 first"))
print(dict(C))
print("by battle", per.most_common(14))
print("named own victims")
for s in named:
    print(" ", s)
for s in samples:
    print(" ", s)
