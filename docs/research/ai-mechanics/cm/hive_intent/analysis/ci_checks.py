"""HIVE COMBAT INTENT V0: the checks of an active run against its base. Read only.
Usage: ci_checks.py <active run> <base run>"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
run, base = sys.argv[1:3]
A, B = read(run), read(base)


def decs(lines):
    return [(i, kv(s)) for i, s in enumerate(lines) if s.startswith("[AIDECIDE]")]


da, db = decs(A), decs(B)
print("decisions", len(da), len(db))
for n, ((ia, a), (ib, b)) in enumerate(zip(da, db)):
    same = all(a.get(f) == b.get(f) for f in ("turn", "unit", "n", "from", "tu", "act", "to", "aim", "hr", "hu"))
    if not same:
        print("first difference at decision", n)
        print(" base  ", {f: b.get(f) for f in ("turn", "side", "unit", "n", "from", "tu", "act", "to", "aim", "hr", "hu", "ho", "hi")})
        print(" active", {f: a.get(f) for f in ("turn", "side", "unit", "n", "from", "tu", "act", "to", "aim", "hr", "hu", "ho", "hi")})
        for s in A[max(0, ia - 12) : ia + 1]:
            if s.startswith("[HIVEINTENT]"):
                print("   ", s[:170])
        break

print("-- not_valid_target by turn, contact")
c = Counter()
for s in A:
    if s.startswith("[HIVEINTENT] event=CHOICE") and "no=not_valid_target" in s:
        k = kv(s)
        c[(k["turn"], k["contact"], k["site"])] += 1
print(sorted(c.items()))
print("-- contact states: last AISTATE before those")
print("-- result kinds: active vs base (base = shadow if it has them)")
print(" active", Counter(kv(s)["kind"] for s in A if s.startswith("[HIVEINTENT] event=RESULT")))
print(" base  ", Counter(kv(s)["kind"] for s in B if s.startswith("[HIVEINTENT] event=RESULT")))

print("-- repeats: same soldier, same turn, from a place visited before (act 2 walks)")
for name, lines in (("active", A), ("base", B)):
    seen = defaultdict(list)
    for s in lines:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1" and k["act"] == "2":
                seen[(k["turn"], k["unit"])].append((k["from"], k["to"], k["tu"]))
    back = wasted = 0
    worst = []
    for key, walk in seen.items():
        places = [w[0] for w in walk]
        rep = len(places) - len(set(places))
        if rep:
            back += 1
            wasted += rep
            worst.append((rep, key, walk[:16]))
    print(f" {name}: walks {sum(len(v) for v in seen.values())}, soldier-turns with a return to a place {back}, returns {wasted}")
    for r in sorted(worst, key=lambda e: -e[0])[:3]:
        print("   ", r[0], r[1], " ".join(f"{w[0]}>{w[1]}:{w[2]}" for w in r[2])[:300])

print("-- broken chains: changed decisions whose aim differs from DECIDED contact, or act not an attack")
last = None
for s in A:
    if s.startswith("[AIDECIDE]"):
        last = kv(s)
    elif s.startswith("[HIVEINTENT] event=DECIDED") and " changed=1" in s:
        k = kv(s)
        if int(k["act"]) in ATT and last and last.get("aim") != k["contact"]:
            print("  ", s[:150], "| aim", last.get("aim"))

print("-- tu against AIEXEC, differing")
rec = {}
last = None
for s in A:
    if s.startswith("[AIDECIDE]"):
        last = kv(s)
    elif s.startswith("[AIEXEC]"):
        try:
            j = json.loads(s[9:])
        except ValueError:
            continue
        last_exec = (j.get("unit"), j.get("spent"), j.get("rec"))
    elif s.startswith("[HIVEINTENT] event=RESULT"):
        k = kv(s)
        if int(k["act"]) in ATT and last_exec and str(last_exec[0]) == k["unit"] and str(last_exec[1]) != k["tu_spent"]:
            print("  ", s[:120], "| exec spent", last_exec[1], "rec", last_exec[2])
