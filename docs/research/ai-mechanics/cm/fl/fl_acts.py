"""TACTICAL FLANKING stage 1: what the engine offered one unit at one decision (D0 probe log).

For each [AIREC] of the unit in the turn: the state, the chosen action and the alternatives the AI itself proposed (props, with
scores); the attack actions of its [AICAND] acts list (kind, action type, target cell, TU) - only those aimed at the given
cells; and, from its [AICAND] moves list, the TU cost of the given cells (the engine's own path costs from where it stood).

  py -3.13 -I fl_acts.py <log> <turn> <unit> [cells x.y.z;...]"""
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
T, U = int(sys.argv[2]), sys.argv[3]
cells = sys.argv[4].split(";") if len(sys.argv) > 4 else []
want = {}
lines = open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines()
moves, acts = {}, {}
for l in lines:
    if l.startswith("[AICAND] moves=") and f" unit={U} " in l:
        h = l.split()[1].split("=")[1]
        moves[h] = l.split(" list=", 1)[1]
    elif l.startswith("[AICAND] acts=") and f" unit={U} " in l:
        h = l.split()[1].split("=")[1]
        acts[h] = l.split(" list=", 1)[1]
for l in lines:
    if not l.startswith("[AIREC] "):
        continue
    r = json.loads(l[8:])
    if r["turn"] != T or str(r["unit"]) != U:
        continue
    st, b = r["state"], r["base"]
    print(f"rec {r['rec']} n={r['n']} pos={st['pos']} dir={st['dir']} tu={st['tu']}: chosen {b['src']} t={b['t']} to={b['to']} "
          f"w={b['w']} mode={b['mode']} score={b['score']}")
    for p in b["reason"].get("props", []):
        print(f"    prop {p['src']:<14} t={p['t']} to={p['to']} w={p['w']} score={p['sc']}")
    for o in b["reason"].get("odds", []):
        print(f"    odds {o}")
    a = acts.get(r["cand"]["acts"])
    if a:
        lst = json.loads(a) if a.startswith("[") else []
        att = [x for x in lst if x.get("t") in (6, 7, 8, 9, 10, 12)]
        kinds = {}
        for x in att:
            kinds.setdefault((x.get("k"), x.get("t"), tuple(x.get("to"))), x.get("tu"))
        tgt = [f"{k[0]}/t{k[1]}->{list(k[2])}:{v}" for k, v in kinds.items() if not cells or ".".join(map(str, k[2])) in cells]
        print(f"    attack acts {len(att)}; at the cells: {' '.join(tgt[:30]) or '-'}")
    m = moves.get(r["cand"]["moves"])
    if m and cells:
        cost = dict(x.rsplit(":", 1) for x in m.split(";") if ":" in x)
        print("    move cost: " + " ".join(f"{c}={cost.get(c, 'unreachable')}" for c in cells))
