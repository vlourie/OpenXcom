"""AI FORGE WP2: on which floor the map first moved after N in each branch, against the same run's dump at N; and the second action of the actor. Reads only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for name in ("A1", "A2", "B1", "B2", "C1"):
    r = rr.Run(name)
    n0 = next(n for n, rows in r.dumps.items() if rows and "why=branch" in rows[0])
    d0 = rr.one_dump(r.dumps[n0])
    na, da = rr.after_dump(r)
    print(name, "at", n0, "after", na, "first floor moved since N:", rr.first_floor(d0, da))
    i, j, ev = rr.decision_at(r)
    fp = [d for *_, d in ev[j + 1:] if d.get("ev") == "fp"]
    print("  M at N", ev[j][3].get("M"), "M at the next decision", fp[0].get("M"), "N at N", ev[j][3].get("N"), "N next", fp[0].get("N"))
    tu = [d for *_, d in ev[: j + 1] if d.get("ev") == "tu"]
    print("  tu changes before N", len(tu), "by kind", {k: sum(1 for d in tu if d.get("kind") == k) for k in sorted({d.get("kind") for d in tu})})
    print("  random consumption: rng at N", ev[j][3].get("rng"), "first act", next(d.get("rng") for *_, d in ev[j + 1:] if d.get("ev") == "act"))
for x, y in (("A1", "B1"), ("C1", "B1"), ("A1", "C1")):
    a, b = rr.Run(x), rr.Run(y)
    _, ra = rr.after_dump(a)
    _, rb = rr.after_dump(b)
    print(x, y, "first floor differing after the decision", rr.first_floor(ra, rb))
    ea, eb = a.events(), b.events()
    same = 0
    for p, q in zip(ea, eb):
        if p[3].get("rng") == q[3].get("rng"):
            same += 1
        else:
            break
    print(x, y, "events with the same rng from the start", same, "last common rng", ea[same - 1][3].get("rng"), "next", ea[same][3].get("rng"), eb[same][3].get("rng"))
