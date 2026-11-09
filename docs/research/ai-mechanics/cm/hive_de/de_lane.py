"""DECISION ENGINE FOUNDATION, read only, over the 48 D0 battles: a comrade C stepped this turn onto a tile in the line of a shot comrade S then fired, or next to its target.
Pair counted only when S fired from the tile it stood on at C's decision (so S's standing was known to C) and the target was already known to the side at C's decision (S's target in the seen list of a decision before C's walk, or a seen list of C).
Per pair: how C chose the tile, damage to own side during S's shot, damage to the player; named victims from AICASUALTY.
Also the upper bound: every attack with a comrade at risk, by the class of the comrade's turn."""
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
ATT = {5, 6, 7, 8, 9, 10, 11, 12}
LOOPS = {"firepoint", "firepoint.random", "firepoint.fallback", "escape", "escape.known", "ambush"}


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
        near = max(abs(p[0] - to[0]), abs(p[1] - to[1])) <= 1
        if (d <= 1.0 and 0 < t < 1) or near:
            out.append(w)
    return out


zf = zipfile.ZipFile(A)
cls = Counter()
pairs = Counter()
named = Counter()
perb = Counter()
samples = []
for n in sorted(x for x in zf.namelist() if x.endswith("openxcom.log.gz")):
    name = n.split("/")[-2].replace("scpa_D_", "")
    L = [x.rstrip("\n").split("\t")[-1] for x in gzip.open(io.BytesIO(zf.read(n)), "rt", encoding="utf-8", errors="replace")]
    pos = {}
    side1 = set()
    out = set()
    D = []
    E = []
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
            D.append({"i": i, "k": k, "pos": dict(pos), "out": set(out), "seen": set(k.get("seen", "").split(","))})
        elif s.startswith("[AIREC]") and D and '"base"' in s:
            try:
                j = json.loads(s[8:])
            except json.JSONDecodeError:
                continue
            D[-1]["b"] = j.get("base") or {}
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            u = str(j.get("unit"))
            if j.get("pos"):
                pos[u] = tuple(j["pos"])
            if D and D[-1]["k"]["unit"] == u:
                D[-1]["ex"] = j
                D[-1]["end"] = dict(pos)
        elif s.startswith("[AICASUALTY]"):
            k = kv(s)
            out.add(k.get("victim"))
            if k.get("vfaction") == "1" and k.get("kfaction") == "1" and k.get("victim") != k.get("killer") and k.get("how") == "dead":
                E.append((i, k))
    H = [d for d in D if d["k"].get("side") == "1" and d.get("b")]
    byturn = defaultdict(list)
    for d in H:
        byturn[int(d["k"]["turn"])].append(d)
    for t, v in byturn.items():
        for idx, d in enumerate(v):
            b = d["b"]
            ex = d.get("ex") or {}
            if b.get("t") not in ATT or not b.get("to") or not ex.get("spent", 0):
                continue
            u = d["k"]["unit"]
            me = d["pos"].get(u)
            if not me:
                continue
            to = tuple(b["to"])
            com = {w: p for w, p in d["pos"].items() if w in side1 and w != u and w not in d["out"]}
            dang = danger(me, to, com)
            if not dang:
                continue
            f, dm = ex.get("fdmg", 0), ex.get("dmg", 0)
            kinds = set()
            for w in dang:
                earlier = [x for x in v[:idx] if x["k"]["unit"] == w]
                walks = [x for x in earlier if x.get("ex", {}).get("spent", 0) > 0 and x["b"].get("t") == 2]
                if walks:
                    lw = walks[-1]
                    src = lw["b"].get("src") or "?"
                    # S stood on this tile at the time of C's walk?
                    still = lw["pos"].get(u) == me
                    # the target known to the side at C's walk: on a tile a decision up to then aimed at or seen by C
                    tu = None
                    kinds.add(("loop" if src in LOOPS else ("melee" if src == "melee" else ("patrol" if src.startswith("patrol") else "other"))) + (", S in place" if still else ", S came later"))
                    pairs[(src, "S in place" if still else "S came later")] += 1
                    pairs[(src, "S in place" if still else "S came later", "hurt")] += 1 if f else 0
                    pairs[(src, "S in place" if still else "S came later", "fdmg")] += f
                    if src in LOOPS and still and f and len(samples) < 16:
                        lc = lw["pos"].get(w)
                        samples.append(dict(b=name, t=t, S=u, Sw=b.get("w"), Ssrc=b.get("src"), Sat=me, to=to, C=w, Csrc=src, Cfrom=lc, Cat=d["pos"][w], Ctu=int(lw["k"]["tu"]), Cspent=lw["ex"].get("spent"), fdmg=f, dmg=dm))
                elif earlier:
                    kinds.add("stood, decided earlier")
                else:
                    kinds.add("not decided yet")
            order = ["loop, S in place", "melee, S in place", "patrol, S in place", "other, S in place", "loop, S came later", "melee, S came later", "patrol, S came later", "other, S came later", "stood, decided earlier", "not decided yet"]
            top = next(o for o in order if o in kinds)
            cls[top] += 1
            cls[top + " hurt"] += 1 if f else 0
            cls[top + " fdmg"] += f
            cls[top + " dmg"] += dm
            cls[top + " fdowned"] += ex.get("fdowned", 0)
            if top.startswith("loop, S in place"):
                perb[name] += 1
    # named dead: the victim's last walk this turn, was the killer in place then
    for i, k in E:
        t = int(k["turn"])
        v = k["victim"]
        kd = next((d for d in reversed(H) if d["i"] < i and d["k"]["unit"] == k.get("killer")), None)
        if not kd:
            named["no decision of the killer"] += 1
            continue
        if kd.get("b", {}).get("t") not in ATT or int(kd["k"]["turn"]) != t:
            named["not by an attack decision of this turn (reaction, blast chain)"] += 1
            continue
        w = [d for d in byturn.get(t, []) if d["i"] < kd["i"] and d["k"]["unit"] == v and d.get("ex", {}).get("spent", 0) > 0 and d["b"].get("t") == 2]
        e = [d for d in byturn.get(t, []) if d["i"] < kd["i"] and d["k"]["unit"] == v]
        if w:
            src = w[-1]["b"].get("src") or "?"
            still = w[-1]["pos"].get(k.get("killer")) == kd["pos"].get(k.get("killer"))
            named[f"walked by {src}, {'S in place' if still else 'S came later'}"] += 1
        elif e:
            named["stood, decided earlier"] += 1
        else:
            named["not decided yet"] += 1
print("attacks with a comrade at risk, by class")
for key, val in sorted(cls.items()):
    print("  ", key, val)
print("pairs", sorted(((str(k), v) for k, v in pairs.items() if len(k) == 2), key=lambda x: -x[1])[:16])
print("pairs fdmg", sorted(((str(k), v) for k, v in pairs.items() if len(k) == 3 and k[2] == "fdmg"), key=lambda x: -x[1])[:12])
print("named dead", sorted(named.items(), key=lambda x: -x[1]))
print("by battle", perb.most_common(12))
for s in samples:
    print(" ", s)
