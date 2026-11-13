"""OPERATIONAL INTELLIGENCE, step 1: effect of AI attacks against armoured units by weapon, side and distance over all archived logs of the three battles: the rule of damage is the same in every build, only the choices differ. The side is taken from the shooter's cell and the facing at aistart (facing.py: a reaction does not turn the body). Also melee chains of Chryssalids on armoured units (not downed, at least 100 TU spent), the chance that two independent chains reach 132 HP, and the cost of a reaction shot of each tank from its own engine list. Read only."""
import itertools
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import OUT, kv, read  # noqa: E402
from oilib import SIDE, Battle, pos, side_code  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ARM = {"444": "tank", "448": "tank", "470": "tank", "545": "wolv"}
tab = defaultdict(list)
chains = []
costs = defaultdict(set)
runs = [p.name for p in sorted(OUT.iterdir()) if p.name.endswith(("M6_s1", "M6_s2", "M3_s1"))]
for run in runs:
    b = Battle(run)
    for d in b.decisions:
        e = d.get("exec") or {}
        if d["weapon"].endswith("CHRYSSALID_WEAPON") and int(d["act"]) in (2, 10) and e.get("dmg", 0) > 0 and not e.get("downed") and e.get("spent", 0) >= 100:
            chains.append(e["dmg"])
    for d in b.attacks:
        if int(d["act"]) == 6:
            continue
        c = ARM.get(d["target"])
        st = b.state.get(int(d["turn"]), {}).get(d["target"])
        if not c or not st:
            continue
        code = side_code(pos(d["from"]), pos(d["to"]), int(st["dir"]))
        if code is None:
            continue
        s = SIDE[code]
        arc = "front" if s.startswith("front") else "rear" if s.startswith("rear") else "side"
        fr, to = pos(d["from"]), pos(d["to"])
        dist = max(abs(fr[0] - to[0]), abs(fr[1] - to[1]))
        bucket = "<=10" if dist <= 10 else "11-20" if dist <= 20 else "21+"
        tab[(d["weapon"], c, arc, bucket)].append((d.get("exec") or {}).get("dmg", 0))
    cur = None
    for s in b.L:
        if s.startswith("[AICAND] acts="):
            try:
                for a in json.loads(s.split(" list=", 1)[1]):
                    if a.get("k") == "a" and a["w"].startswith("AUX_TANK") and a.get("t") in (7, 8):
                        costs[(a["w"], a["t"])].add(a["tu"])
            except (IndexError, ValueError):
                pass
print("logs:", len(runs))
print("weapon, target class, side, distance: attacks, with damage, mean damage per attack, median of damaging")
for k in sorted(tab, key=lambda k: (k[0], k[1], k[2], k[3])):
    v = tab[k]
    if len(v) >= 5 or "HEAVY" in k[0]:
        pos_ = [x for x in v if x > 0]
        print(f"  {k[0][4:16]:14s} {k[1]:5s} {k[2]:6s} {k[3]:6s} n={len(v):4d} dmg>0={len(pos_):4d} mean={sum(v) / len(v):6.1f} med+={statistics.median(pos_) if pos_ else 0}")
print("melee chains on armoured units (not downed, >=100 TU spent):", len(chains), sorted(chains))
if chains:
    print("  mean", round(statistics.mean(chains), 1), "median", statistics.median(chains))
    pairs = list(itertools.product(chains, chains))
    print("  P(two chains >= 132) by resampling:", round(sum(a + b >= 132 for a, b in pairs) / len(pairs), 3), " P(one chain >= 132):", round(sum(a >= 132 for a in chains) / len(chains), 3))
print("tank shot costs (weapon, mode: costs in lists):", {k: sorted(v) for k, v in costs.items()})
