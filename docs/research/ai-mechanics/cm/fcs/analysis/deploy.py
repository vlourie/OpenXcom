"""FIRST CONTACT SURVIVAL, stage 1: the starting positions from the [AISTATE] before snapshot of turn 1 (read only).
For each battle: how many hostile units, how many seen by the player at the very start, the distance to the nearest player unit, the floors; for each scenario: how far the starting cells coincide between the seeds.
Usage: deploy.py <battle dir>..."""
import gzip
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
POS = re.compile(r"pos=\((-?\d+),(-?\d+),(-?\d+)\)")
cells = defaultdict(dict)
for d in sys.argv[1:]:
    h, p = [], []
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for ln in f:
            s = ln.rstrip("\n").split("\t")[-1]
            if not s.startswith("[AISTATE] before"):
                continue
            k = dict(KV.findall(s))
            if k.get("turn") != "1":
                continue
            m = POS.search(s)
            q = tuple(int(x) for x in m.groups())
            seen = int(k.get("seenby", "0"))  # a count
            (h if k.get("faction") == "1" else p).append((k["unit"], q, seen, k.get("sees", "-")))
    near = []
    for u, q, seen, _ in h:
        ds = [((q[0] - a[1][0]) ** 2 + (q[1] - a[1][1]) ** 2) ** 0.5 for a in p]
        near.append(min(ds) if ds else 999)
    name = Path(d).name
    sc = name.split("_")[-2]
    cells[sc][name] = {q for _, q, _, _ in h}
    print(f"{name}: hostile {len(h)} player {len(p)}; hostile seen at the start {sum(bool(x[2]) for x in h)}; nearest player d min {min(near):.0f} median {statistics.median(near):.0f}; d<=10: {sum(n <= 10 for n in near)}, d<=20: {sum(n <= 20 for n in near)}; hostile floors {sorted(Counter(x[1][2] for x in h).items())}; player floors {sorted(Counter(x[1][2] for x in p).items())}")
print()
for sc, by in cells.items():
    names = sorted(by)
    base = by[names[0]]
    un = set().union(*by.values())
    print(sc, "distinct starting cells over the seeds", len(un), "per battle", [len(by[n]) for n in names], "shared with the first seed", [len(by[n] & base) for n in names])
