"""OPERATIONAL INTELLIGENCE, step 1: weapon against class of target and side of armour, from the D0 logs: attacks, attacks with damage, damage. Classes: tank (444 448 470), wolverine (545), infantry (the rest). Also melee and the weapons used by carriers, the list of all weapons seen, and the HP lost per class. Read only.
Usage: wclass.py <run> [<run> ...]"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import SIDE, Battle, acts_of, pos, side_code  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def cls(u):
    return {"444": "tank", "448": "tank", "470": "tank", "545": "wolv"}.get(u, "inf")


def arc(code):
    if code is None:
        return "under"
    s = SIDE[code]
    if s.startswith("front"):
        return "front"
    if s.startswith("rear"):
        return "rear"
    return "side"


for run in sys.argv[1:]:
    b = Battle(run)
    tab = defaultdict(lambda: [0, 0, 0])
    names = Counter()
    for d in b.attacks:
        names[d["weapon"]] += 1
        if int(d["act"]) == 6:
            continue
        st = b.state.get(int(d["turn"]), {}).get(d["target"])
        if not st or st.get("faction") != "0":
            continue
        a = arc(side_code(pos(d["from"]), pos(d["to"]), int(st["dir"])))
        e = d.get("exec") or {}
        key = (d["weapon"], cls(d["target"]), a)
        tab[key][0] += 1
        tab[key][1] += e.get("dmg", 0) > 0
        tab[key][2] += e.get("dmg", 0)
    print("=====", run)
    for w in sorted({k[0] for k in tab}, key=lambda w: -sum(v[0] for k, v in tab.items() if k[0] == w)):
        parts = []
        for c in ("tank", "wolv", "inf"):
            for a in ("front", "side", "rear", "under"):
                v = tab.get((w, c, a))
                if v:
                    parts.append(f"{c}/{a} {v[0]}:{v[1]}:{v[2]}")
        print(f"  {w:30s} " + "  ".join(parts))
    print("  (attacks:with damage:damage)")
    all_w = Counter()
    for d in b.decisions:
        for a in acts_of(d):
            if a.get("k") == "a":
                all_w[a["w"]] += 1
    print("  weapons in engine lists:", " ".join(sorted(all_w)))
