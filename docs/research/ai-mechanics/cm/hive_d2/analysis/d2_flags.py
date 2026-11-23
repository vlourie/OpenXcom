"""D2 design: what the patrol byte (value[21], Node::_flags) holds in the routes of the installed mod. Read only."""
import collections
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
root = Path("E:/OpenXCom/Пиратки/Dioxine_XPiratez")
files = [p for p in root.rglob("*") if p.suffix.upper() == ".RMP"]
flags = collections.Counter()
ranks = collections.Counter()
zero_gate = nodes = 0
same_best = diff_best = 0
for p in files:
    data = p.read_bytes()
    recs = [data[i:i + 24] for i in range(0, len(data) - 23, 24)]
    for r in recs:
        nodes += 1
        flags[r[21]] += 1
        ranks[r[20]] += 1
        if r[21] == 0 and r[20] == 0:
            zero_gate += 1
        # links of this node: how often its neighbours differ in the patrol byte at all
        vals = [recs[r[4 + j * 3]][21] for j in range(5) if r[4 + j * 3] <= 250 and r[4 + j * 3] < len(recs)]
        if len(vals) >= 2:
            if len(set(vals)) > 1:
                diff_best += 1
            else:
                same_best += 1
print("files", len(files), "nodes", nodes)
print("flags", sorted(flags.items()))
print("rank", sorted(ranks.items()))
print("flags=0 and rank=0 (closed to a scout=false search):", zero_gate)
print("nodes with 2+ links in the block: neighbours differ in flags", diff_best, "all equal", same_best)
