"""HIVE D2 CORRECTION, read only: where this build first differs from SAFETY: the first decision that differs, and the first drop of a kept node SAFETY made before it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
for new, old in (("d23_DN_M3_s1", "us2_QN_M3_s1"), ("d26_DN_M6_s1", "us1_QN_M6_s1")):
    A = read(new)
    B = read(old)
    a = [(i, kv(s)) for i, s in enumerate(A) if s.startswith("[AIDECIDE]")]
    b = [(i, kv(s)) for i, s in enumerate(B) if s.startswith("[AIDECIDE]")]
    print("=====", new, old, "decisions", len(a), len(b))
    F = ("turn", "unit", "from", "tu", "mode", "act", "to")
    at = None
    for n, ((i, x), (j, y)) in enumerate(zip(a, b)):
        if any(x.get(f) != y.get(f) for f in F):
            at = (n, i, j, x, y)
            break
    if at:
        n, i, j, x, y = at
        print("first differing decision no", n, "new line", i, [x.get(f) for f in F])
        print("                         old line", j, [y.get(f) for f in F])
        drops = [(k, kv(s)) for k, s in enumerate(B) if s.startswith("[HIVEUA] event=KEPT_DROP") and k < j]
        print("drops in SAFETY before it:", len(drops))
        for k, d in drops[-3:]:
            print("   line", k, "t", d["turn"], "unit", d["unit"], "node", d["node"])
        same_t1 = all(all(p.get(f) == q.get(f) for f in F) for (_, p), (_, q) in zip(a, b) if p["turn"] == "1")
        print("all decisions of turn 1 the same:", same_t1, "; turn 1 decisions:", sum(p["turn"] == "1" for _, p in a), sum(p["turn"] == "1" for _, p in b))
