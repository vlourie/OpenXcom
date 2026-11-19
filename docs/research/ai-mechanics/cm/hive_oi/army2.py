"""OPERATIONAL INTELLIGENCE, step 1: the rest of the inventory of capabilities: kinds of action in the engine's lists, ammunition and spare clips at the first state by main weapon, modes and sources of decisions of the AI side, carriers of grenades. Read only.
Usage: army2.py <run> [<run> ...]"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import Battle, acts_of, kv  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
MODE = {"0": "PATROL", "1": "AMBUSH", "2": "COMBAT", "3": "ESCAPE"}
for run in sys.argv[1:]:
    b = Battle(run)
    print("=====", run)
    kinds = Counter()
    for d in b.decisions:
        for a in acts_of(d):
            kinds[(a.get("k"), a.get("t"))] += 1
    print("  kinds of action in lists (k,t):", dict(kinds))
    am = defaultdict(Counter)
    for u, k in b.units.items():
        if k.get("faction") == "1":
            am[k.get("rh")][(k.get("ammo"), k.get("spare"))] += 1
    for w, c in sorted(am.items(), key=lambda x: -sum(x[1].values())):
        print(f"  {w}: (ammo, spare) {dict(c)}")
    modes = Counter(MODE.get(d["mode"], d["mode"]) for d in b.decisions)
    print("  modes of decisions:", dict(modes))
    src = Counter(d.get("src") for d in b.decisions)
    print("  sources:", src.most_common(14))
    # how many decisions of a live AI fighter with full TU moved without attacking, share of TU spent on walks
    walk = attack = 0
    for d in b.decisions:
        e = d.get("exec") or {}
        if int(d["act"]) in (1, 2, 3):
            walk += e.get("spent", 0) or 0
        elif int(d["act"]) >= 4:
            attack += e.get("spent", 0) or 0
    print("  TU spent: walks", walk, "attacks", attack)
