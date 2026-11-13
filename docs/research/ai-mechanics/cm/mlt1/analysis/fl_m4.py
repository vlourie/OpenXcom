"""MISSION_DIRECTOR_V0: two battles of one start side by side, turn by turn: the module tiles left (all, and the objective's), the hostile side's shots at modules,
attacks at units, damage and losses of both sides, where the group's fighters ended.

  py -3.13 -I fl_m4.py <D0-like battle dir with [AIMISSION]> <orders battle dir>"""
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")


def read(d):
    t = defaultdict(lambda: defaultdict(int))
    grid = {}
    fighters = set()
    dec = None
    fate = {}
    plan_turns = []
    for raw in gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        s = raw.rstrip("\n").split("\t", 2)[-1]
        if s.startswith("[AIMISSION] what=grid"):
            m = dict(KV.findall(s))
            cells = {}
            for g in s.split("left: ")[-1].split():
                k, v = g.split("=")
                cells[k] = tuple(map(int, v.split("/")))
            grid[int(m["turn"])] = cells
        elif s.startswith("[AIMISSION] what=hit"):
            m = dict(KV.findall(s))
            if m["side"] == "1" and m["part"] != "4":
                t[int(m["turn"])]["terrain_hits"] += 1
                if m["module"] == "1" and m["part"] == "3":
                    t[int(m["turn"])]["module_hits"] += 1
                    if int(m["tdmg"]) >= int(m["partarmor"]):
                        t[int(m["turn"])]["module_broke"] += 1
        elif s.startswith("[AIMISSION] what=blast"):
            t[int(dict(KV.findall(s))["turn"])]["blast"] += 1
        elif s.startswith("[AIMISSION] what=plan"):
            m = dict(KV.findall(s))
            for f in m["fighters"].split(";"):
                fighters.add(f.split(">")[0])
            plan_turns.append((int(m["turn"]), m["cell"]))
        elif s.startswith("[AIDECIDE] "):
            dec = dict(KV.findall(s.split(" hu=")[0]))
            if dec["side"] != "1":
                dec = None
                continue
            a, mo = int(dec["act"]), int(dec["mode"])
            tt = int(dec["turn"])
            if a in (6, 7, 8, 9) and mo != 0:
                t[tt]["attack_decisions"] += 1
            if a in (7, 8, 9) and mo == 0:
                t[tt]["patrol_shots"] += 1
            fate[dec["unit"]] = (tt, dec["from"])
        elif s.startswith("[AIEXEC] ") and dec:
            x = json.loads(s[9:])
            if str(x["unit"]) == dec["unit"]:
                t[int(dec["turn"])]["dmg"] += x.get("dmg") or 0
                t[int(dec["turn"])]["downed"] += x.get("downed") or 0
                t[int(dec["turn"])]["hp_lost"] += x.get("hp_lost") or 0
            dec = None
        elif s.startswith("[AICASUALTY]"):
            m = dict(KV.findall(s))
            side = m.get("side") or m.get("faction")
            t[int(m.get("turn", 0))]["cas_side" + str(side)] += 1
    return t, grid, fighters, fate, plan_turns


A = read(sys.argv[1])
B = read(sys.argv[2])
turns = sorted(set(A[0]) | set(B[0]))
keys = ("module_hits", "module_broke", "blast", "patrol_shots", "terrain_hits", "attack_decisions", "dmg", "downed", "hp_lost", "cas_side0", "cas_side1")
print("per turn, first run / second run")
print("turn " + " ".join(k[:9].rjust(9) for k in keys) + "  tiles_left")
sa = defaultdict(int)
sb = defaultdict(int)
for tt in turns:
    row = []
    for k in keys:
        a, b = A[0][tt][k], B[0][tt][k]
        sa[k] += a
        sb[k] += b
        row.append(f"{a}/{b}".rjust(9))
    la = sum(v[0] for v in A[1].get(tt, {}).values()) if A[1].get(tt) else "-"
    lb = sum(v[0] for v in B[1].get(tt, {}).values()) if B[1].get(tt) else "-"
    print(f"{tt:>4} " + " ".join(row) + f"  {la}/{lb}")
print("sum  " + " ".join(f"{sa[k]}/{sb[k]}".rjust(9) for k in keys))
for name, g in (("first", A[1]), ("second", B[1])):
    last = max(g) if g else None
    if last:
        print(name, "last grid turn", last, "cells changed:", {k: v for k, v in g[last].items() if v[0] != v[1]})
print("plans of the second run:", B[4])
print("second run's fighters, last decision (turn, place):", {u: B[3].get(u) for u in sorted(B[2])})
print("the same units in the first run:", {u: A[3].get(u) for u in sorted(B[2])})
