"""COORDINATED OPERATION, phase A: does the same kind of chance occur again. Over the D0 logs allowed by the GO (M3 s1 and s2, M11 s1 and s2, M2 s1 and s2; logs from the archive scpa_D): at each AI turn, a player's armoured unit known to the side (spotted 0 at aistart) and at least two living AI fighters holding a cheap melee weapon able to hurt armour by the D0 record, whose engine list of the first decision reaches a cell next to it. Rule of the chance: neither can land K blows this turn, but each has a cell on its way to stop at with the turn's TU and from there would have K blows next turn. D0's own outcome is added: blows and damage on that unit by these fighters on the turns t and t+1. Read only.
Usage: a3_repeat.py <archive dir>"""
import gzip
import io
import json
import re
import sys
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=([^ ]*)")
K = 4
GOOD = ("CHRYSSALID", "VAMPIRE_WEAP", "KATANA", "WAKIZASHI")
ARM = {"444", "448", "470", "545"}
RUNS = ["M3_s1", "M3_s2", "M11_s1", "M11_s2", "M2_s1", "M2_s2"]


def pos(p):
    return tuple(int(x) for x in p.strip("()").split(","))


def moves(s):
    out = {}
    for c in s.split(" list=", 1)[1].split(";"):
        try:
            p, tu = c.split(":")
            x, y, z = p.split(".")
            out[(int(x), int(y), int(z))] = int(tu)
        except ValueError:
            pass
    return out


def read(zf, name):
    with gzip.open(io.BytesIO(zf.read(name)), "rt", encoding="utf-8", errors="replace") as h:
        return [ln.rstrip("\n").split("\t")[-1] for ln in h]


root = Path(sys.argv[1])
total = 0
for z in sorted(root.glob("res_*.zip")):
    zf = zipfile.ZipFile(z)
    for name in zf.namelist():
        m = re.search(r"scpa_D_((M3|M11|M2)_s\d+)/.*log\.gz$", name)
        if not m or m.group(1) not in RUNS:
            continue
        L = read(zf, name)
        state = defaultdict(dict)
        first = defaultdict(dict)  # turn -> unit -> (moves, melee cost by weapon, from, tu)
        blows = defaultdict(lambda: [0, 0])
        cur = mv = None
        recs = {}
        for s in L:
            if s.startswith("[AISTATE] aistart"):
                k = dict(KV.findall(s))
                state[int(k["turn"])][k["unit"]] = k
            elif s.startswith("[AIDECIDE]"):
                cur = dict(KV.findall(s))
                mv = None
            elif s.startswith("[AICAND] moves=") and cur:
                mv = s
            elif s.startswith("[AICAND] acts=") and cur:
                t, u = int(cur["turn"]), cur["unit"]
                if cur.get("side") == "1" and u not in first[t] and mv:
                    try:
                        acts = json.loads(s.split(" list=", 1)[1])
                    except (IndexError, ValueError):
                        acts = []
                    w = {}
                    for a in acts:
                        if a.get("k") == "a" and a.get("t") == 10 and any(g in a["w"] for g in GOOD):
                            w[a["w"]] = a["tu"]
                    first[t][u] = (moves(mv), w, pos(cur["from"]), int(cur["tu"]), cur.get("weapon"))
            elif s.startswith("[AIREC]") and cur:
                try:
                    recs[json.loads(s[8:])["rec"]] = cur
                except ValueError:
                    pass
            elif s.startswith("[AIEXEC]"):
                try:
                    j = json.loads(s[9:])
                except ValueError:
                    continue
                d = recs.get(j["rec"])
                if d and d.get("side") == "1" and j.get("dmg", 0) > 0:
                    blows[(int(d["turn"]), d["unit"])][0] += j.get("spent", 0)
                    blows[(int(d["turn"]), d["unit"])][1] += j["dmg"]
        found = 0
        print("=====", m.group(1), "turns", max(state) if state else 0, "melee fighters by turn", {t: sum(1 for x in first[t].values() if x[1]) for t in sorted(first) if any(x[1] for x in first[t].values())})
        for t in sorted(first):
            for tid in ARM:
                st = state[t].get(tid)
                if not st or st.get("spotted") != "0" or int(st.get("status", 0)) >= 6:
                    continue
                tp = pos(st["pos"])
                size = 2 if tid in ("444", "448", "470", "545") else 1
                near = [(tp[0] + x, tp[1] + y, tp[2]) for x in range(-1, size + 1) for y in range(-1, size + 1) if not (0 <= x < size and 0 <= y < size)]
                can = []
                for u, (mm, w, fr, tu, wp) in first[t].items():
                    if not w or tu < 1:
                        continue
                    c = min(w.values())
                    ways = [mm[q] for q in near if q in mm and mm[q] >= 0]
                    if not ways:
                        continue
                    way = min(ways)
                    now = max(0, (tu - way) // c) if way <= tu else 0
                    # stop on the way with the turn's TU: what is left of the way next turn
                    left = max(0, way - tu)
                    tumax = int(state[t].get(u, {}).get("tumax", tu))
                    nxt = (tumax - left) // c if left else tumax // c
                    if now < K and nxt >= K and left <= tumax:
                        can.append((u, wp[4:14] if wp else "", tu, way, now, nxt, state[t].get(u, {}).get("hp")))
                if len(can) >= 2:
                    found += 1
                    res = {(u[0], t2): blows.get((t2, u[0]), [0, 0]) for u in can for t2 in (t, t + 1)}
                    print(f"  t{t} target {tid} at {st['pos']} dir {st['dir']} hp {st['hp']}: ", [(x[0], x[1], "tu", x[2], "way", x[3], "now", x[4], "next", x[5], "hp", x[6]) for x in can][:5])
                    print("      D0 on t,t+1 (TU spent, dmg of damaging decisions):", {f"{a}/{b}": v for (a, b), v in res.items() if v[1]}, "target hp next", state.get(t + 1, {}).get(tid, {}).get("hp"))
        print("  chances:", found)
        total += found
print("all chances:", total)
