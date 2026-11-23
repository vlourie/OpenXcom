"""AI FORGE WP2.1: the tiles A's action changed: which fields, in the rows the log holds (at most 300), and what the next actions of the two branches were."""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TILE = re.compile(r"tile=(\S+) was=(\S+) now=(\S+)")


def fields(s):
    return dict(x.split(":", 1) for x in s.split(","))


for name in ("A1", "B1"):
    run = rr.Run(name)
    after = rr.dump_of(run, "after_branch")
    rows = [TILE.match(r).groups() for r in after if r.startswith("tile=")]
    kinds = Counter()
    other = []
    lights = Counter()
    last = None
    for at, was, now in rows:
        a, b = fields(was), fields(now)
        changed = tuple(k for k in a if a[k] != b[k])
        kinds[changed] += 1
        last = at
        if changed != ("l",):
            other.append((at, was, now))
        la, lb = a["l"].split("/"), b["l"].split("/")
        for layer in range(4):
            if la[layer] != lb[layer]:
                lights[layer] += 1
    print(name, "rows", len(rows), "total line", next((r for r in after if r.startswith("tiles_changed")), None), "last row", last)
    print("  fields changed", dict(kinds))
    print("  light layers changed", dict(lights))
    print("  other than light", other[:10])
    print("  after dump head", after[0][:300])
    i, j, ev = rr.act_at(run)
    acts = [e for e in ev[j + 1:] if e[3].get("ev") == "act"][:6]
    print("  next actions")
    for e in acts:
        print("   ", e[0], e[2].strip()[:170])
    # was the unit list seen by anyone changed by the next decision: the [AIEVENT] lines from the action to the second next decision
    s = [x for x in run.lines if x.startswith("[AIEVENT]")]
    print("  events", len(s), s[:0])
