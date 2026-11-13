"""Does [AIREC] follow its [AIDECIDE] one to one? n repeats inside a unit's turn (the action counter is reset after BA_NONE), so (turn, unit, n) is not a key. Read only.
Usage: join_check.py <run> ..."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
for run in sys.argv[1:]:
    L = read(run)
    keys = Counter()
    recs = Counter()
    order = []
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            key = (int(k["turn"]), int(k["unit"]), int(k["n"]))
            keys[key] += 1
            order.append(("D", key, k["tu"]))
        elif s.startswith("[AIREC]"):
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            key = (j["turn"], j["unit"], j["n"])
            recs[key] += 1
            order.append(("R", key, j.get("tu")))
    rep = {k: v for k, v in keys.items() if v > 1}
    print(run, "decisions", sum(keys.values()), "recs", sum(recs.values()), "keys", len(keys), "repeated keys", len(rep), "decisions under them", sum(rep.values()), "count differs", sum(keys[k] != recs[k] for k in set(keys) | set(recs)))
    # the neighbour of each decision: the next record of the stream
    pair = Counter()
    for a, b in zip(order, order[1:]):
        if a[0] == "D":
            pair["next is its own rec" if b[0] == "R" and b[1] == a[1] else "next is other: " + b[0]] += 1
    print("  ", dict(pair))
    print("   sample", [(x[0], x[1], x[2]) for x in order[:6]])
