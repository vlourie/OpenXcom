"""Items with ids in [lo, hi]: py -3.13 items_range.py <lo> <hi> <sav> [sav ...]"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from cmp_b0 import load

lo, hi = int(sys.argv[1]), int(sys.argv[2])
for p in sys.argv[3:]:
    bg = load(p)["battleGame"]
    print("==", p.rsplit("/", 2)[-2])
    for it in sorted(bg["items"], key=lambda x: x["id"]):
        if lo <= it["id"] <= hi:
            print(" ", it["id"], {k: v for k, v in it.items() if k != "id"})
