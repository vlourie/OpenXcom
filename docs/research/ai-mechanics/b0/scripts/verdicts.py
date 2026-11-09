"""Summary of a cmp_b0 report.tsv: per pair, verdict counts and the scenarios that are not IDENTICAL.
py -3.13 verdicts.py <report.tsv>"""
import sys
from collections import defaultdict

rows = open(sys.argv[1], encoding="utf-8-sig").read().splitlines()
head = rows[0].split("\t")
cnt = defaultdict(lambda: defaultdict(list))
order = []
for line in rows[1:]:
    r = dict(zip(head, line.split("\t")))
    if r["pair"] not in order:
        order.append(r["pair"])
    cnt[r["pair"]][r["verdict"]].append(r["scen"])
for p in order:
    print(f"{p:8s}", "  ".join(f"{v} {len(s)}" + (f" [{' '.join(s)}]" if v != "IDENTICAL" and len(s) < 12 else "")
                              for v, s in sorted(cnt[p].items())))
