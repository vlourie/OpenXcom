"""HIVE COMBAT INTENT V0: gates T4 and T8 as declared, the 20 decisions without RESULT on M3, what own_other decided. Read only."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
PAIRS = [("ra1_AN_M6_s1", "ci5_IA_M6_s1"), ("ra2_AN_M6_s2", "ci6_IA_M6_s2"), ("ra3_AV_M3_s1", "ci7_IV_M3_s1")]
for ra, ci in PAIRS:
    A = [s for s in read(ra) if s.startswith("[HIVESQUAD]")]
    B = [s for s in read(ci) if s.startswith("[HIVESQUAD]")]
    n = min(len(A), len(B))
    first = next((i for i in range(n) if A[i] != B[i]), None)
    print(ci, "HIVESQUAD lines", len(A), len(B), "first differing", first)
    if first is not None:
        print("   ra", A[first][:150])
        print("   ci", B[first][:150])
    t1a = [s for s in A if kv(s).get("turn") in ("1", None)]
    t1b = [s for s in B if kv(s).get("turn") in ("1", None)]
    print("   first plan lines same:", t1a == t1b, len(t1a), len(t1b))
    L = read(ci)
    dec = [kv(s) for s in L if s.startswith("[AIDECIDE]") and kv(s)["side"] == "1"]
    print("   AIDECIDE keys", sorted(dec[0].keys())[:40])
    tus = [int(d["tu"]) for d in dec if "tu" in d]
    print("   min tu", min(tus), "energy keys", [k for k in dec[0] if "en" in k.lower()][:6])
    if "energy" in dec[0]:
        print("   min energy", min(int(d["energy"]) for d in dec))

L = read("ci7_IV_M3_s1")
d = Counter()
r = Counter()
for s in L:
    if s.startswith("[AIDECIDE]"):
        k = kv(s)
        if k["side"] == "1":
            d[(k["turn"], k["unit"])] += 1
    elif s.startswith("[HIVEINTENT] event=RESULT"):
        k = kv(s)
        r[(k["turn"], k["unit"])] += 1
gap = {x: (d[x], r[x]) for x in d if d[x] != r[x]}
print("M3 decisions without RESULT:", sum(a - b for a, b in gap.values()), "units", sorted({x[1] for x in gap}))
print("  ", sorted(gap.items())[:12])
units = sorted({x[1] for x in gap})
for s in L:
    if s.startswith("[HIVESQUAD]") and any(u in s for u in units[:2]):
        print("   squad line", s[:150])
        break
print("  squad mentions in ISSUE or DECIDED of those units:", sum(1 for s in L if s.startswith("[HIVEINTENT] event=DECIDED") and kv(s)["unit"] in units))

print("own by act and kind")
for run in ("ci5_IA_M6_s1", "ci6_IA_M6_s2", "ci7_IV_M3_s1"):
    c = Counter()
    for s in read(run):
        if s.startswith("[HIVEINTENT] event=DECIDED"):
            k = kv(s)
            if k.get("own", "-") != "-":
                c[(k["own"], k.get("act"))] += 1
    print(" ", run, sorted(c.items(), key=lambda x: (x[0][0], -x[1])))
