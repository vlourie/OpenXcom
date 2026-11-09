"""HIVE hardening: who stood "locked" in a journal, with its field that turn, and how far the objective was (read only). Usage: hh_locked.py <out dir>"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
d = Path(sys.argv[1])
with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
    lines = [ln.rstrip("\n").split("\t")[-1] for ln in f]
reach = {}
last = {}
rows = []
for s in lines:
    if s.startswith("[HIVEREACH]"):
        k = dict(kv.findall(s))
        reach[(k["unit"], k["turn"])] = (k["tiles"], k["capped"], k["at"])
    if s.startswith("[HIVEORD]") and "kind=STAY" in s and "why=locked" in s and "state=CREATED" in s:
        k = dict(kv.findall(s))
        rows.append((k["turn"], k["squad"], k["unit"], k["at"], reach.get((k["unit"], k["turn"]))))
print("locked orders", len(rows), "units", len({r[2] for r in rows}))
print("by unit", Counter(r[2] for r in rows).most_common())
for r in rows[:40]:
    print(r)
print(Counter(s for s in (dict(kv.findall(x)).get("tiles") for x in lines if x.startswith("[HIVEREACH]") and "capped=0" in x)).most_common(14))
