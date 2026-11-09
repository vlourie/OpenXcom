"""The trails of a unit-turn's recs and execs.  usage: c2_trails.py <rec.gz> <unit> <turn>; and how many hostile unit-turns
in each file have recs that repeat with nothing spent (k, to, pos, tu the same, spent 0)  usage: c2_trails.py --rep <rec.gz>..."""
import gzip
import json
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")


def load(p):
    R, X = {}, {}
    with gzip.open(p, "rt", encoding="utf-8") as f:
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


if sys.argv[1] == "--rep":
    for p in sys.argv[2:]:
        R, X = load(p)
        g = defaultdict(list)
        for r in sorted(R):
            if R[r]["side"] == 1:
                g[(R[r]["unit"], R[r]["turn"])].append(R[r])
        turns = recs = 0
        for lst in g.values():
            seen, rep = set(), 0
            for j in lst:
                k = (j["base"]["k"], tuple(j["base"]["to"]), tuple(j["state"]["pos"]), j["state"]["tu"])
                rep += k in seen and X.get(j["rec"], {}).get("spent", 0) == 0
                seen.add(k)
            turns += rep >= 4
            recs += rep
        print(f"{p.split('/')[-1]}: unit-turns with 4+ idle repeats {turns}, idle repeat recs {recs}")
else:
    R, X = load(sys.argv[1])
    for r in sorted(R):
        j = R[r]
        if j["unit"] == int(sys.argv[2]) and j["turn"] == int(sys.argv[3]):
            print(r, j["n"], j["base"]["k"], j["base"]["reason"]["trail"][:8])
            print("   exec", X.get(r, {}).get("spent"), X.get(r, {}).get("trail", [])[:4])
