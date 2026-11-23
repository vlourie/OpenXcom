"""SIDE-FIRST COMBAT: the totals of fair.txt over the 16 XN battles. args: fair.txt"""
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
c = Counter()
for s in open(sys.argv[1], encoding="utf-8", errors="replace"):
    if s.startswith("sfF_XN"):
        c["battles"] += 1
        for k, v in re.findall(r"'(\w+)': (\d+)", s):
            c[k] += int(v)
print(dict(c))
