"""DECISION ENGINE FOUNDATION, read only, over the 48 D0 battles. The candidates of a decision come by hash from the AIREC record: a list is logged once per battle.
ATT: every attack decision the soldier executed. Other enemy targets at hand with a line of fire; a comrade in the lane or next to the target; damage to own side during it.
SNIPER: same for the sniper source.
BLOCK: whole unit-turns lost with the reach taken by hash; a comrade on the edge; what the comrade did on that turn before the soldier; his own acts list.
Numbers only; each class says how often the choice exists and how often it would have mattered."""
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
ATT = {5, 6, 7, 8, 9, 10, 11, 12}


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


def danger(me, to, comrades):
    """the comrades in the lane of a shot from me to to, or next to to, on the same floor as either end"""
    out = []
    for w, p in comrades.items():
        if p == me or p[2] not in (me[2], to[2]):
            continue
        d, t = lane(me, to, p)
        near = max(abs(p[0] - to[0]), abs(p[1] - to[1])) <= 1
        if (d <= 1.0 and 0 < t < 1) or near:
            out.append(w)
    return out


zf = zipfile.ZipFile(A)
at = Counter()
sn = Counter()
bl = Counter()
per = defaultdict(Counter)
sample = []
bsample = []
for n in sorted(x for x in zf.namelist() if x.endswith("openxcom.log.gz")):
    name = n.split("/")[-2].replace("scpa_D_", "")
    L = [x.rstrip("\n").split("\t")[-1] for x in gzip.open(io.BytesIO(zf.read(n)), "rt", encoding="utf-8", errors="replace")]
    moves = {}
    acts = {}
    for s in L:
        if s.startswith("[AICAND] moves="):
            m = re.match(r"\[AICAND\] moves=(\w+) unit=\d+ list=(.*)", s)
            if m:
                moves[m.group(1)] = [tuple(int(v) for v in c.split(":")[0].split(".")) for c in m.group(2).split(";") if ":" in c]
        elif s.startswith("[AICAND] acts="):
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
            m = re.match(r"\((-?\d+),(-?\d+),(-?\d+)\)", k.get("pos", ""))
            if m:
                pos[k["unit"]] = tuple(int(v) for v in m.groups())
            if k.get("faction") == "1":
                side1.add(k["unit"])
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            m = re.match(r"\((-?\d+),(-?\d+),(-?\d+)\)", k.get("from", ""))
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
            D[-1]["hp"] = (j.get("state") or {}).get("hp")
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            u = str(j.get("unit"))
            if j.get("pos"):
                pos[u] = tuple(j["pos"])
            if D and D[-1]["k"]["unit"] == u:
                D[-1]["ex"] = j
        elif s.startswith("[AICASUALTY]"):
            out.add(kv(s).get("victim"))
    H = [d for d in D if d["k"].get("side") == "1" and d.get("b")]
    for d in H:
        b = d["b"]
        t = b.get("t", 0)
        ex = d.get("ex") or {}
        if t not in ATT or not b.get("to"):
            continue
        u = d["k"]["unit"]
        me = d["pos"].get(u)
        if not me:
            continue
        to = tuple(b["to"])
        com = {w: p for w, p in d["pos"].items() if w in side1 and w != u and w not in d["out"]}
        dang = danger(me, to, com)
        L_ = acts.get((d.get("c") or {}).get("acts"), [])
        foes = {}
        for c in L_:
            if c.get("k") == "a" and c.get("t") in (7, 8, 9) and c.get("lof") == 1 and c.get("u", 0) < 1000000 and c.get("u", -1) >= 0 and c.get("tu", 0) <= int(d["k"]["tu"]) and c.get("p", 0) > 0:
                foes.setdefault(c["u"], []).append(c)
        chosen = next((c for c in L_ if c.get("k") == "a" and c.get("to") and tuple(c["to"]) == to), None)
        other = [v for f, v in foes.items() if not chosen or f != chosen.get("u")]
        clean = [v for v in other if not danger(me, tuple(v[0]["to"]), com)]
        rec = at if b.get("src") != "sniper" else sn
        for c in (rec, per[name]):
            c["att"] += 1
            c["dmg"] += ex.get("dmg", 0)
            c["fdmg"] += ex.get("fdmg", 0)
            c["fdowned"] += ex.get("fdowned", 0)
            if other:
                c["other target"] += 1
            if dang:
                c["comrade at risk"] += 1
                c["dmg, comrade at risk"] += ex.get("dmg", 0)
                c["fdmg, comrade at risk"] += ex.get("fdmg", 0)
                c["fdowned, comrade at risk"] += ex.get("fdowned", 0)
                if ex.get("fdmg", 0):
                    c["comrade at risk and hurt"] += 1
                if clean:
                    c["at risk, clean other target"] += 1
                    c["fdmg, at risk, clean other"] += ex.get("fdmg", 0)
                    c["dmg, at risk, clean other"] += ex.get("dmg", 0)
                    if ex.get("fdmg", 0):
                        c["at risk, clean other, hurt"] += 1
            elif ex.get("fdmg", 0):
                c["not at risk by the line, yet hurt"] += 1
                c["fdmg, not at risk by the line"] += ex.get("fdmg", 0)
        if dang and clean and ex.get("fdmg", 0) and len(sample) < 12:
            sample.append(dict(b=name, t=d["k"]["turn"], u=u, src=b.get("src"), me=me, to=to, w=b.get("w"), dang=dang, fdmg=ex.get("fdmg"), dmg=ex.get("dmg"), clean=[(v[0]["u"], v[0]["to"], v[0]["w"], v[0]["p"]) for v in clean][:3]))
    # BLOCK
    ut = defaultdict(list)
    for d in H:
        ut[(int(d["k"]["turn"]), d["k"]["unit"])].append(d)
    reach_later = defaultdict(dict)
    for (t, u), v in ut.items():
        reach_later[u][t] = len(moves.get((v[0].get("c") or {}).get("moves"), []))
    for (t, u), v in ut.items():
        tu = int(v[0]["k"]["tu"])
        if sum(x.get("ex", {}).get("spent", 0) for x in v) or not tu:
            continue
        cells = set(moves.get((v[0].get("c") or {}).get("moves"), []))
        here = v[0]["pos"].get(u)
        if here:
            cells.add(here)
        bl["lost"] += 1
        bl["tu"] += tu
        com = {w: p for w, p in v[0]["pos"].items() if w in side1 and w != u and w not in v[0]["out"]}
        edge = [w for w, p in com.items() if p not in cells and any(abs(p[0] - c[0]) <= 1 and abs(p[1] - c[1]) <= 1 and p[2] == c[2] for c in cells)]
        grow = max([s for tt, s in reach_later[u].items() if tt > t], default=0)
        before = {d["k"]["unit"] for d in H if d["i"] < v[0]["i"] and int(d["k"]["turn"]) == t and d["k"]["unit"] in edge}
        mode = v[0]["k"].get("mode")
        bl[f"mode {mode}"] += 1
        bl[f"reach {'<=80' if len(cells) <= 80 else '>80'}"] += 1
        if len(cells) <= 80 and edge:
            bl["pocket + comrade on the edge"] += 1
            bl["tu, pocket + comrade"] += tu
            if before:
                bl["...he decided earlier this turn"] += 1
                if grow > 3 * len(cells):
                    bl["...and later reach 3x"] += 1
                    bl["tu, ...and later reach 3x"] += tu
                    if len(bsample) < 25:
                        bsample.append(dict(b=name, t=t, u=u, reach=len(cells), later=grow, tu=tu, mode=mode, act=v[0]["k"].get("act"), before=sorted(before)))
print("ATT", dict(at))
print("SNIPER", dict(sn))
print("BLOCK", dict(bl))
print("samples FF with a clean other target")
for s in sample:
    print(" ", s)
print("samples BLOCK")
for s in bsample:
    print(" ", s)
print("per battle", [(k, v["att"], v["comrade at risk"], v["at risk, clean other target"], v["at risk, clean other, hurt"], v["fdmg, at risk, clean other"]) for k, v in sorted(per.items())])
