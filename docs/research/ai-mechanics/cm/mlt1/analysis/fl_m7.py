"""MISSION_DIRECTOR_V0: the grid at each turn's start/end (all tiles, the two first objectives' cells), where the first plan stands against the side's first decision,
hostile hits on modules by the side's own shooters - order or not, the fate of the fighters.

  py -3.13 -I fl_m7.py <battle dir> <cut turn>"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
cut = int(sys.argv[2])
rows = []
for raw in gzip.open(Path(sys.argv[1]) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
    rows.append(raw.rstrip("\n").split("\t", 2)[-1])
first_plan = next((i for i, s in enumerate(rows) if s.startswith("[AIMISSION] what=plan")), None)
first_dec = next((i for i, s in enumerate(rows) if s.startswith("[AIDECIDE] ") and " side=1 " in s), None)
print("first plan line", first_plan, "first hostile decision line", first_dec)
if first_plan is not None:
    print(" ", rows[first_plan][:150])
when = Counter()
g = {}
for s in rows:
    if s.startswith("[AIMISSION] what=grid"):
        d = dict(KV.findall(s))
        cells = {}
        for x in s.split("left: ")[-1].split():
            k, v = x.split("=")
            cells[k] = tuple(map(int, v.split("/")))
        g[(int(d["turn"]), d["when"])] = cells
        when[d["when"]] += 1
print("grid kinds:", dict(when))
for key in sorted(g):
    if key[0] >= cut - 1:
        c = g[key]
        print(f"  t{key[0]} {key[1]}: tiles {sum(v[0] for v in c.values())} of {sum(v[1] for v in c.values())}, cell 0,0 {c.get('0,0')}, cell 1,0 {c.get('1,0')}, empty {[k for k, v in c.items() if v[0] == 0]}")
task = set()
pend = {}
cnt = Counter()
for s in rows:
    if s.startswith("[AIMISSION] what=task"):
        d = dict(KV.findall(s))
        if d["kind"] == "shoot":
            pend[d["unit"]] = d["tile"]
    elif s.startswith("[AIMISSION] what=hit"):
        d = dict(KV.findall(s))
        if d["side"] == "1" and d["module"] == "1" and d["part"] == "3" and int(d["turn"]) <= cut:
            k = "order" if pend.get(d["unit"]) == d["tile"] else "protocol"
            cnt[k + "_hit"] += 1
            if int(d["tdmg"]) >= int(d["partarmor"]):
                cnt[k + "_broke"] += 1
        elif d["side"] == "0" and d["module"] == "1" and d["part"] == "3" and int(d["turn"]) <= cut:
            cnt["player_hit"] += 1
            if int(d["tdmg"]) >= int(d["partarmor"]):
                cnt["player_broke"] += 1
    elif s.startswith("[AIMISSION] what=blast") and int(dict(KV.findall(s))["turn"]) <= cut:
        cnt["blast"] += 1
print(f"to turn {cut}:", dict(cnt))
