"""The unit-turns with the most decision records in an arm: is it a loop (the same decision at the same place and TU
again) or OXCE picking the unit back while it has TU.  usage: c1_maxrecs.py <dir> <label> [min]"""
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
d, label = Path(sys.argv[1]), sys.argv[2]
lo = int(sys.argv[3]) if len(sys.argv) > 3 else 13
g = defaultdict(list)
X = {}
with gzip.open(d / f"{label}.rec.gz", "rt", encoding="utf-8") as f:
    for l in f:
        tag, _, body = l.partition("] {")
        if not body:
            continue
        j = json.loads("{" + body)
        if tag.endswith("[AIREC"):
            g[(j["side"], j["unit"], j["turn"])].append(j)
        elif tag.endswith("[AIEXEC"):
            X[j["rec"]] = j
for key, lst in g.items():
    if len(lst) < lo:
        continue
    seen = set()
    repeats = 0
    for j in lst:
        k = (j["base"]["k"], tuple(j["base"]["to"]), tuple(j["state"]["pos"]), j["state"]["tu"])
        repeats += k in seen
        seen.add(k)
    print(f"{label} side {key[0]} unit {key[1]} turn {key[2]}: {len(lst)} recs, exact repeats {repeats}")
    for j in lst:
        x = X.get(j["rec"], {})
        print(f"  rec {j['rec']} n {j['n']} k {j['base']['k']} tu {j['state']['tu']} pos {j['state']['pos']} -> {j['base']['to']} spent {x.get('spent')}")
