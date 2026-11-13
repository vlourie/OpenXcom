"""C2 details: the plans by shots and by what followed them (exit, wait, drop, second shot), the fire-point plans, and
one rec in full.  usage: c2_detail.py <dir> <ids comma> [scen:rec ...]"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
D = Path(sys.argv[1])
IDS = sys.argv[2].split(",")
SHOW = [a.split(":") for a in sys.argv[3:]]


def load(label):
    R, X = {}, {}
    with gzip.open(D / f"{label}.rec.gz", "rt", encoding="utf-8") as f:
        for l in f:
            tag, _, body = l.partition("] {")
            if not body:
                continue
            j = json.loads("{" + body)
            if tag.endswith("[AIREC"):
                R[j["rec"]] = j
            elif tag.endswith("[AIEXEC"):
                X[j["rec"]] = j
    return R, X


c = Counter()
for sid in IDS:
    R, X = load(f"c2_B_{sid}")
    g = defaultdict(list)
    for r in sorted(R):
        if R[r]["side"] == 1:
            g[(R[r]["unit"], R[r]["turn"])].append(R[r])
    for lst in g.values():
        for i, j in enumerate(lst):
            tr = j["base"]["reason"]["trail"]
            pl = next((s for s in tr if s.startswith("c2.plan.here ") or s.startswith("c2.plan.fp ")), None)
            if not pl:
                continue
            n = {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", pl)}
            kind = pl.split()[0]
            c[f"{kind} shots={min(n['shots'], 3)}"] += 1
            # what the rest of the unit-turn did with this plan
            rest = [t for k in lst[i + 1:] for t in k["base"]["reason"]["trail"] if t.startswith("c2.")]
            first = next((t.split()[0] for t in rest if t.split()[0] in ("c2.exit", "c2.exit.safe", "c2.noexit", "c2.drop.changed",
                                                                         "c2.drop.noshot", "c2.drop.walk", "c2.arrived")), None)
            ends = "exit" if any(t.startswith("c2.exit ") for t in rest) else first or "turn ended / nothing"
            c[f"  {kind} shots={min(n['shots'], 3)} -> {ends}"] += 1
            if "c2.drop.mode" in tr:
                c[f"  {kind} dropped in the same think (c2.drop.mode)"] += 1
            c[f"{kind} left_sum"] += n.get("left", 0)
            c[f"{kind} exit_sum"] += n.get("exit", 0)
    for s, r in SHOW:
        if s != sid:
            continue
        j = R[int(r)]
        print(json.dumps(j, ensure_ascii=False)[:3000])
        print(json.dumps(X.get(int(r), {}), ensure_ascii=False)[:1500])
        prev = [R[k] for k in sorted(R) if k < int(r) and R[k]["unit"] == j["unit"] and R[k]["turn"] == j["turn"]]
        for p in prev:
            print(" prev", p["rec"], p["n"], p["base"]["k"], p["state"]["tu"], [t for t in p["base"]["reason"]["trail"] if t.startswith("c2.")],
                  X.get(p["rec"], {}).get("spent"), [t for t in X.get(p["rec"], {}).get("trail", []) if t.startswith("c2.")])
for k in sorted(c):
    print(f"{k}\t{c[k]}")
