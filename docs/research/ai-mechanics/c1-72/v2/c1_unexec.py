"""Attacks that were decided but not carried out (k=a, no TU spent, or no cover.confirm when the series notes it): what
the same unit did next in that turn - a cover step there would be the false trigger the correction must stop.
usage: c1_unexec.py <dir> <prefix> <id> [<id> ...]"""
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
d, P, ids = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
c = Counter()
for sid in ids:
    R, X = {}, {}
    with gzip.open(d / f"{P}_B_{sid}.rec.gz", "rt", encoding="utf-8") as f:
        for l in f:
            tag, _, body = l.partition("] {")
            if not body:
                continue
            j = json.loads("{" + body)
            if tag.endswith("[AIREC"):
                R[j["rec"]] = j
            elif tag.endswith("[AIEXEC"):
                X[j["rec"]] = j
    recs = sorted(R)
    for i, r in enumerate(recs):
        j = R[r]
        if j["side"] != 1 or j["base"]["k"] != "a":
            continue
        x = X.get(r, {})
        if x.get("spent", 0) > 0 and "cover.confirm" in x.get("trail", []):
            continue
        c["unexec"] += 1
        nxt = next((R[k] for k in recs[i + 1:] if R[k]["unit"] == j["unit"]), None)
        same = nxt is not None and nxt["turn"] == j["turn"]
        step = same and any(s.startswith("cover.step ") for s in nxt["base"]["reason"]["trail"])
        c["unexec_spent"] += x.get("spent", 0) > 0
        c["unexec_next_same_turn"] += same
        c["unexec_next_cover_step"] += step
        c[f"unexec_next_k_{nxt['base']['k'] if same else '-'}"] += 1
        if step:
            print(f"{sid} rec {r} -> cover step at rec {nxt['rec']} spent={x.get('spent')} trail={x.get('trail', [])[:4]}")
for k, v in sorted(c.items()):
    print(f"{k}\t{v}")
