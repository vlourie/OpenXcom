"""Movement diagnosis, last checks for the report: live orders the same in the two runs, RNG streams of the two loads, all closers with how they got there, the sums the report quotes (read only)."""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from classify import run_table  # noqa: E402
from closers import analyse, why_there  # noqa: E402
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
A = read("hh6_JV_M3_s1")
B = read("hh7_HL_M3_s1")
C = read("hh8_HL_M3_s1")
line = next(i for i, s in enumerate(A) if s.startswith("[HIVESAVE]"))
text = A[line][A[line].index("text=") + 5 :]
ids = [int(r.split(",")[1]) for r in text.split(";") if r.startswith("O,")]


def fates(L, start=0):
    return {int(kv(s)["id"]): kv(s) for s in L[start:] if s.startswith("[HIVEFATE]")}


before = fates(A[:line])
fa = fates(A, line)
fb = fates(B)
live = [i for i in ids if i not in before]
na = {i for i in live if i not in fa}
nb = {i for i in live if i not in fb}
print("live", len(live), "never closed: same set", na == nb, len(na), "; kinds of them", Counter(next((r.split(",")[4] + "/" + r.split(",")[5]) for r in text.split(";") if r.startswith(f"O,{i},")) for i in na).most_common())
db = [kv(s) for s in B if s.startswith("[AIDECIDE]")]
dc = [kv(s) for s in C if s.startswith("[AIDECIDE]")]
n = 0
for x, y in zip(db, dc):
    if x["hr0"] != y["hr0"]:
        break
    n += 1
print("RNG before each decision the same in the two loads for", n, "decisions of", min(len(db), len(dc)), "; first different decision", db[n].get("turn"), db[n].get("side"), db[n].get("unit"), "/", dc[n].get("unit"))
print("  decisions where the action differs before that:", sum(x["act"] != y["act"] or x.get("to") != y.get("to") for x, y in zip(db[:n], dc[:n])))
print("  the last 2 before it:", [(x["unit"], x["mode"], x["act"], x.get("to"), y["unit"], y["mode"], y["act"], y.get("to")) for x, y in zip(db[n - 2 : n], dc[n - 2 : n])])
for run in ["hh4_JA_M6_s2", "hh3_JA_M6_s1", "hh6_JV_M3_s1"]:
    L, res = analyse(run)
    print("==", run)
    for r in res:
        if "note" in r:
            continue
        print(f" line {r['line']} turn {r['turn']} {r['big']}->{r['small']} union {r['part']} complete={r['complete']} free {r['free'][:4]} players {r['players']}")
        for g, v in r["closers"].items():
            if g not in r["closed0"]:
                print(f"    came after the big flood: {v} at {g}: {why_there(L, v, r['line'])}")
tot = Counter()
for run in ["hh4_JA_M6_s2", "hh6_JV_M3_s1"]:
    L, rows, _ = run_table(run)
    tot.update(o["cause"] for o in rows)
    tot["всего"] += len(rows)
print(tot.most_common())
