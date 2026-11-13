"""FIRST CONTACT SURVIVAL, stage 1: the units lost before any decision: in which phase, seen at the very start or not, by whom; and the survival of the first player turn against being seen at the start (read only).
Usage: never.py <cat.tsv> <battle dir>..."""
import csv
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig"), delimiter="\t"))
total = Counter()
for d in sys.argv[2:]:
    name = Path(d).name
    start = {}
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for ln in f:
            s = ln.rstrip("\n").split("\t")[-1]
            if s.startswith("[AISTATE] before"):
                k = dict(KV.findall(s))
                if k.get("turn") == "1" and k.get("faction") == "1":
                    start[k["unit"]] = int(k.get("seenby", "0"))
    x = [r for r in rows if r["battle"] == name]
    lost_p1 = {r["victim"] for r in x if r["turn"] == "1" and r["side"] == "0"}
    seen = {u for u, n in start.items() if n > 0}
    print(f"{name}: hostile {len(start)}, seen at the start {len(seen)}; fell in the player's first turn: seen {len(lost_p1 & seen)} of {len(seen)}, unseen {len(lost_p1 - seen)} of {len(start) - len(seen)}")
    a = [r for r in x if r["cat"] == "A"]
    print("   A:", len(a), "phases", Counter((r["turn"], r["phase"]) for r in a).most_common(), "cause", Counter(r["why"] for r in a).most_common(), "killer saw at the phase start", Counter(r.get("k_sees") for r in a).most_common())
    for r in a:
        total[("A", r["phase"], r["why"])] += 1
print(sorted(total.items(), key=lambda a: -a[1]))
