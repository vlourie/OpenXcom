"""TACTICAL FLANKING stage 1: the engine's own attack options of each decision of the given units in one turn.

[AICAND] acts holds, for every attack the unit could make from where it stood: the target unit, the action type, TU cost,
the hit chance the engine computed (p, %), whether there is a line of fire from the current cell (lof) and the distance.
Printed per decision ([AIREC] order), only for the given target units, with the decision's position and TU.

  py -3.13 -I fl_lof.py <log> <turn> <units a,b,..> <targets x,y,..>"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
T, UNITS, TGT = int(sys.argv[2]), sys.argv[3].split(","), set(sys.argv[4].split(","))
TYPE = {6: "throw", 7: "auto", 8: "snap", 9: "aimed", 10: "melee", 12: "launch"}
lines = open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines()
acts = {}
for l in lines:
    if l.startswith("[AICAND] acts="):
        h = l.split()[1].split("=")[1]
        acts[h] = l.split(" list=", 1)[1]
for l in lines:
    if not l.startswith("[AIREC] "):
        continue
    r = json.loads(l[8:])
    if r["turn"] != T or str(r["unit"]) not in UNITS:
        continue
    st = r["state"]
    a = acts.get(r["cand"]["acts"], "[]")
    lst = json.loads(a) if a.startswith("[") else []
    out = []
    for x in lst:
        if x.get("k") == "a" and str(x.get("u")) in TGT:
            out.append(f"{x['u']}:{TYPE.get(x['t'], x['t'])}/{x.get('w', '')[:14]} tu{x['tu']} p{x.get('p')} lof{x.get('lof')} d{x.get('d')}")
    print(f"{r['unit']} n={r['n']} pos={st['pos']} tu={st['tu']} chosen={r['base']['src']} t={r['base']['t']} to={r['base']['to']}")
    for o in out:
        print("     " + o)
