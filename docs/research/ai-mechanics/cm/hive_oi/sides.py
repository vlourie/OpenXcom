"""OPERATIONAL INTELLIGENCE, step 1: damage of the AI's attacks by the side of armour they meet: what the rule in BattleUnit::damage gives from the shooter's cell and the target's facing at the start of that AI turn. First a check of the formula against the side the log names in [AICASUALTY]. Read only.
Usage: sides.py <run> [<run> ...]"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import SIDE, Battle, pos, side_code  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
tab = defaultdict(lambda: [0, 0, 0])
check = Counter()
per_run = {}
for run in sys.argv[1:]:
    b = Battle(run)
    n = 0
    for d in b.attacks:
        if int(d["act"]) == 6:
            continue
        st = b.state.get(int(d["turn"]), {}).get(d["target"])
        if not st or st.get("faction") != "0":
            continue
        code = side_code(pos(d["from"]), pos(d["to"]), int(st["dir"]))
        if code is None:
            continue
        e = d.get("exec") or {}
        key = (d["weapon"], SIDE[code])
        tab[key][0] += 1
        tab[key][1] += e.get("dmg", 0) > 0
        tab[key][2] += e.get("dmg", 0)
        n += 1
    per_run[run] = n
    # the formula against the log: killing shots of the AI at the player's units
    for c in b.casualties:
        if c.get("kfaction") == "1" and c.get("how") in ("dead", "stun") and c.get("hit") and len(c.get("victim", "")) < 7:
            st = b.state.get(int(c["turn"]), {}).get(c["victim"])
            at = next((d for d in b.attacks if d["unit"] == c.get("killer") and d["turn"] == c["turn"] and int(d["act"]) != 6 and pos(d["to"])[:2] == pos(c["pos"])[:2]), None)
            if st and at:
                code = side_code(pos(at["from"]), pos(c["pos"]), int(st["dir"]))
                check[(SIDE[code] if code is not None else "under", c["hit"])] += 1
print("attacks counted", per_run)
print("formula against [AICASUALTY] hit (predicted, logged):")
for k, n in sorted(check.items(), key=lambda x: -x[1]):
    print("  ", k, n)
print("weapon by side: attacks, with damage, share, damage, damage per attack")
for w in sorted({k[0] for k in tab}, key=lambda w: -sum(v[0] for k, v in tab.items() if k[0] == w)):
    tot = sum(v[0] for k, v in tab.items() if k[0] == w)
    if tot < 8:
        continue
    print(" ", w, tot)
    for s in ("front", "front/right", "front/left", "right", "left", "rear/right", "rear/left", "rear"):
        v = tab.get((w, s))
        if v:
            print(f"    {s:12s} {v[0]:5d} {v[1]:4d} {100 * v[1] / v[0]:5.1f}% {v[2]:6d} {v[2] / v[0]:6.1f}")
agg = defaultdict(lambda: [0, 0, 0])
for (w, s), v in tab.items():
    g = "front arc" if s.startswith("front") else "side" if s in ("right", "left") else "rear arc"
    for i in range(3):
        agg[g][i] += v[i]
print("all weapons:", {k: (v[0], v[1], round(100 * v[1] / v[0], 1), v[2], round(v[2] / v[0], 1)) for k, v in agg.items()})
