"""Movement diagnosis: the continuous battle, the load with hive and the load without it, decision by decision from the save on, with the state hashes the bench logs (read only)."""
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
A = read("hh6_JV_M3_s1")
B = read("hh7_HL_M3_s1")
C = read("hh8_HL_M3_s1")
save = next(i for i, s in enumerate(A) if s.startswith("[HIVESAVE]"))
print("save line in the continuous run", save, A[save][:90])
for name, X in (("B", B), ("C", C)):
    head = [(i, s[:170]) for i, s in enumerate(X) if s.startswith(("[HIVEINIT]", "[HIVELOAD]", "[AIPROBE]", "[HIVEFIRST]"))][:10]
    print(name, "head")
    for i, s in head:
        print("  ", i, s)


def decisions(X, start=0):
    out = []
    for i, s in enumerate(X):
        if i >= start and s.startswith("[AIDECIDE]"):
            k = kv(s)
            out.append((i, k))
    return out


da = decisions(A, save)
db = decisions(B)
dc = decisions(C)
print("decisions after the save: continuous", len(da), "hive", len(db), "no hive", len(dc))
FIELDS = ["turn", "side", "unit", "n", "from", "tu", "mode", "act", "to", "aim", "weapon", "seen"]
HASH = ["hu", "hi", "ho", "hou", "hm", "hr", "hr0", "ha0", "ha"]


def same(x, y, f):
    return x.get(f) == y.get(f)


def first_diff(p, q, title):
    n = 0
    for (i, x), (j, y) in zip(p, q):
        bad = [f for f in FIELDS if not same(x, y, f)]
        if bad:
            print(f"{title}: first decision difference at #{n} lines {i}/{j}: {bad}")
            print("   ", {f: x.get(f) for f in FIELDS})
            print("   ", {f: y.get(f) for f in FIELDS})
            print("    hashes", {f: (x.get(f), y.get(f)) for f in HASH if not same(x, y, f)})
            return n
        n += 1
    print(f"{title}: no decision difference in the {n} compared")
    return n


n1 = first_diff(da, db, "continuous vs load with hive")
n2 = first_diff(da, dc, "continuous vs load without hive")
n3 = first_diff(db, dc, "load with hive vs load without hive")
for title, p, q in (("continuous vs load with hive", da, db), ("load with hive vs load without hive", db, dc)):
    print(title, "first 6 decisions, hash differences")
    for (i, x), (j, y) in list(zip(p, q))[:6]:
        print("   ", x.get("turn"), x.get("side"), x.get("unit"), x.get("n"), "act", x.get("act"), y.get("act"), "hash differs", [f for f in HASH if not same(x, y, f)])
print("hash fields per record sample:", re.findall(r" (h\w+)=", A[da[0][0]]))
for name, X in (("A", A), ("B", B), ("C", C)):
    tag = [s[:150] for s in X if s.startswith("[AIRESULT]")]
    print(name, tag)
