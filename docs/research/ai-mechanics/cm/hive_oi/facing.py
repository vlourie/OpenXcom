"""OPERATIONAL INTELLIGENCE, step 1: does a reaction turn the body of a tank? Facing and TU of armoured player's units from aistart(t) to pstart(t+1) (nothing but reactions moves them in the AI's turn), with the number of reaction events by that unit in turn t. Also chains of melee damage on the M3 logs: spent, damage, per log, to give damage per blow. Read only.
Usage: facing.py <run> [<run> ...]"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import Battle, acts_of, kv, moves_of, pos  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
total = Counter()
blows = []
for run in sys.argv[1:]:
    b = Battle(run)
    react = Counter()
    pstart = {}
    end_tu = {}
    for s in b.L:
        if s.startswith("[AISTATE] pstart"):
            k = kv(s)
            pstart[(int(k["turn"]), k["unit"])] = k
        elif s.startswith("[AIEVENT]") and "what=reaction" in s:
            k = kv(s)
            if k.get("side") == "1":
                react[(int(k["turn"]), k["unit"])] += 1
    for t, st in b.state.items():
        for u in ("444", "448", "470", "545"):
            k = st.get(u)
            n = pstart.get((t + 1, u))
            if not k or not n:
                continue
            r = react[(t, u)]
            same = k["dir"] == n["dir"]
            total[("turn with reactions" if r else "turn without", "same facing" if same else "other facing")] += 1
    for d in b.decisions:
        e = d.get("exec") or {}
        if d["weapon"].endswith("CHRYSSALID_WEAPON") and e.get("dmg", 0) > 0:
            way = moves_of(d).get(pos(d["to"]))
            blows.append((run, d["turn"], d["unit"], d["from"], d["to"], d["tu"], way, e.get("spent"), e.get("dmg"), e.get("downed")))
print("facing of armoured units across the AI's turn:", dict(total))
print("melee chains of Chryssalids: run, turn, unit, from, to, tu, way, spent, dmg, downed")
for x in blows:
    print("  ", x)
