"""Classify every cover.step of arm B: did the record keep the step (k=m, target at the noted distance), was the debt
set by a real attack, and what spent the TU.  usage: c1_steps.py <dir> <scen.tsv>"""
import gzip
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
d = Path(sys.argv[1])
ids = [l.split("\t")[0] for l in Path(sys.argv[2]).read_text(encoding="utf-8-sig").splitlines()[1:] if l.strip()]
c = Counter()
odd = []
for sid in ids:
    R, X = {}, {}
    with gzip.open(d / f"c1_B_{sid}.rec.gz", "rt", encoding="utf-8") as f:
        for l in f:
            tag, _, body = l.partition("] {")
            if not body:
                continue
            j = json.loads("{" + body)
            if tag.endswith("[AIREC"):
                R[j["rec"]] = j
            elif tag.endswith("[AIEXEC"):
                X[j["rec"]] = j
    for r, j in sorted(R.items()):
        notes = [s for s in j["base"]["reason"]["trail"] if s.startswith("cover.step ")]
        if not notes:
            continue
        n = {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", notes[-1])}
        x = X.get(r, {})
        p0, to = j["state"]["pos"], j["base"]["to"]
        dist_to = math.ceil(math.sqrt((p0[0] - to[0]) ** 2 + (p0[1] - to[1]) ** 2))
        prev = [R[k] for k in sorted(R) if k < r and R[k]["unit"] == j["unit"] and R[k]["turn"] == j["turn"]]
        attacked = bool(prev) and prev[-1]["base"]["k"] == "a" and X.get(prev[-1]["rec"], {}).get("spent", 0) > 0
        kept = j["base"]["k"] == "m" and dist_to == n["dist"]
        walk_tu = n["tu"] - x.get("tu", 0)
        c["steps"] += 1
        c["kept"] += kept
        c["debt_real_attack"] += attacked
        c["pre_spend"] += j["state"]["tu"] != n["tu"]
        if kept:
            c["kept_walk_eq_cost"] += walk_tu == n["cost"]
            c["kept_walk_lt_cost"] += walk_tu < n["cost"]
            c["kept_walk_gt_cost"] += walk_tu > n["cost"]
            c["kept_tu_below_keep"] += x.get("tu", 0) < n["keep"] and not x.get("down")
            if walk_tu != n["cost"]:
                odd.append(f"{sid} rec {r} kept: walk_tu {walk_tu} cost {n['cost']} walk {x.get('walk')} trail {[s[:60] for s in x.get('trail', [])]}")
        else:
            odd.append(f"{sid} rec {r} REPLACED: k={j['base']['k']} to={to} dist_to={dist_to} noted dist={n['dist']} exec walk={x.get('walk')} spent={x.get('spent')} prev={[k['base']['k'] for k in prev][-3:]} trail={j['base']['reason']['trail'][:6]}")
        if not attacked:
            odd.append(f"{sid} rec {r} DEBT WITHOUT SPENT ATTACK: prev={[(k['base']['k'], X.get(k['rec'], {}).get('spent')) for k in prev][-3:]}")
for k, v in sorted(c.items()):
    print(f"{k}\t{v}")
print()
for o in odd:
    print(o)
