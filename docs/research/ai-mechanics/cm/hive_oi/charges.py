"""OPERATIONAL INTELLIGENCE, step 1: every decision of the AI side with melee damage: charge is logged as a walk (act 2) with src melee and [AIEXEC] dmg, not as act 10. So: all decisions with a melee weapon in the engine's list, the cost of that melee, decisions with damage, spent, dmg, trail end, target near the trail end. Read only.
Usage: charges.py <run>"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import SIDE, Battle, acts_of, moves_of, pos, side_code  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
b = Battle(sys.argv[1])
MELEE = {"AUX_CHRYSSALID_WEAPON", "AUX_ZOMBIE_WEAPON", "AUX_SILACOID_WEAPON_MELEE", "AUX_PRED_CLAWS", "STR_GLADIUS"}
costs = Counter()
for d in b.decisions:
    for a in acts_of(d):
        if a.get("k") == "a" and a["w"] in MELEE:
            costs[(a["w"], a["t"], a["tu"])] += 1
print("====", b.run, "melee entries (weapon, act, tu):", costs.most_common(12))
for d in b.decisions:
    e = d.get("exec") or {}
    if e.get("dmg", 0) > 0 and int(d["act"]) < 4:
        print(f" t{d['turn']} unit {d['unit']} from {d['from']} tu {d['tu']} act {d['act']} to {d['to']} src {d.get('src')} spent {e.get('spent')} dmg {e.get('dmg')} downed {e.get('downed')} stunned {e.get('stunned')}")
one = next((d for d in b.decisions if int(d["act"]) == 10), None)
if one:
    print(" sample act10:", {k: one.get(k) for k in ("turn", "unit", "from", "tu", "to", "weapon")}, one.get("exec"))
    print(" list:", [a for a in acts_of(one) if a.get("k") == "a"][:6])
