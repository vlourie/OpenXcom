"""HIVE COMMAND gate: the patrol nodes of a battle save (read only): how many, by rank and flags, how they link. Usage: nodes.py <file.sav> [...]"""
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
for f in sys.argv[1:]:
    text = open(f, encoding="utf-8-sig", errors="replace").read()
    i = text.find("\n  nodes:")
    if i < 0:
        print(f, "no nodes block")
        continue
    j = re.compile(r"(?m)^  [a-zA-Z]").search(text, i + 9)
    block = text[i:j.start() if j else None]
    items = re.split(r"(?m)^    - ", block)[1:]
    rank = Counter()
    links = 0
    z = Counter()
    dummy = 0
    for b in items:
        g = re.search(r"rank: *(-?\d+)", b)
        rank[g.group(1) if g else "-"] += 1
        p = re.search(r"position: *\[(-?\d+), *(-?\d+), *(-?\d+)\]", b)
        if p:
            z[p.group(3)] += 1
        dummy += "dummy: true" in b
        ln = re.search(r"links: *\[([^\]]*)\]", b)
        if ln:
            links += sum(1 for v in ln.group(1).split(",") if v.strip() and int(v) >= 0)
    print(f.split("/")[-1], "nodes", len(items), "dummy", dummy, "ranks", sorted(rank.items()), "floors", sorted(z.items()), "links>=0", links)
    if items:
        print("  sample:", items[0][:200].replace("\n", " "))
