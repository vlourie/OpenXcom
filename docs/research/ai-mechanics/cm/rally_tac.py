"""STAGE_RALLY_V1 coverage in a series: the h.rally.* tallies of the result's tac column, totals and per mission type.

  py -3.13 -I rally_tac.py <arena dir> <prefix>"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

D, PRE = Path(sys.argv[1]), sys.argv[2]
tot = Counter()
by = defaultdict(Counter)
n = Counter()
for p in sorted(D.glob(f"{PRE}_*.tsv")):
    if p.name.endswith(".data_manifest.tsv"):
        continue
    lines = p.read_text(encoding="utf-8-sig").splitlines()
    r = dict(zip(lines[0].split("\t"), lines[-1].split("\t")))
    m = r["mission"]
    n[m] += 1
    for kv in r["tac"].split(","):
        if kv.startswith("h.rally."):
            k, v = kv[len("h.rally."):].rsplit(":", 1)
            tot[k] += int(v)
            by[m][k] += int(v)
print("battles", sum(n.values()), "totals", dict(tot))
for m in sorted(by, key=lambda m: -by[m]["to_node"]):
    print(f"  {m} x{n[m]}: {dict(by[m])}")
print("missions with no rally:", sorted(set(n) - set(by)))
