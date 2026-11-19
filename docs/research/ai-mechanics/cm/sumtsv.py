"""Totals of an ai_arena series: pdead, phplost, hdead, hostile, turns over the <prefix>_*.tsv tables of a folder.

  py -3.13 -I sumtsv.py <arena dir> <prefix>"""
import sys
from pathlib import Path

D, PRE = Path(sys.argv[1]), sys.argv[2]
rows = []
for p in sorted(D.glob(f"{PRE}_*.tsv")):
    lines = p.read_text(encoding="utf-8-sig").splitlines()
    head = lines[0].split("\t")
    for l in lines[1:]:
        if l.strip():
            rows.append(dict(zip(head, l.split("\t"))))
tot = {k: sum(float(r[k]) for r in rows) for k in ("pdead", "phplost", "hdead", "hostile", "turn", "hattacks")}
print(f"battles {len(rows)}", " ".join(f"{k}={v:.0f}" for k, v in tot.items()),
      f"| per battle pdead {tot['pdead'] / len(rows):.2f} phplost {tot['phplost'] / len(rows):.0f}",
      f"| player won {sum(r['livealiens'] == '0' for r in rows)}")
