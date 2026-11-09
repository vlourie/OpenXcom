"""Movement diagnosis: what happens to the orders written in the save: each one closed once, in which run, how; the numbering after the load; the same order in the continuous run (read only)."""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
A = read("hh6_JV_M3_s1")
B = read("hh7_HL_M3_s1")
C = read("hh8_HL_M3_s1")
line = next(i for i, s in enumerate(A) if s.startswith("[HIVESAVE]"))
text = A[line][A[line].index("text=") + 5 :]
recs = text.split(";")
O = [r.split(",") for r in recs if r.startswith("O,")]
print("H record", next(r for r in recs if r.startswith("H,")))
print("X record", next(r for r in recs if r.startswith("X")))
print("B records", [r[:80] for r in recs if r.startswith("B,")])
print("first order records", [",".join(x)[:110] for x in O[:3]])
ids = [int(x[1]) for x in O]
print("orders in the save", len(ids), "ids", min(ids), "..", max(ids), "unique", len(set(ids)))
print("states (field 6 guess)", Counter(x[5] for x in O).most_common(), Counter(x[4] for x in O).most_common(5))


def go_lines(L, start=0):
    """id -> list of states seen after the start, and the fate lines."""
    states = {}
    fates = {}
    for i, s in enumerate(L):
        if i < start:
            continue
        if s.startswith("[HIVEORD]"):
            k = kv(s)
            if "state" not in k or "id" not in k or "unit" not in k:
                continue
            states.setdefault(int(k["id"]), []).append((i, k["state"], k.get("kind"), k.get("note", ""), int(k["unit"]), k.get("target"), int(k["turn"])))
        elif s.startswith("[HIVEFATE]"):
            k = kv(s)
            fates.setdefault(int(k["id"]), []).append((i, k["fate"], k.get("reason"), int(k.get("unit", -1)), int(k.get("issued", -1)), k.get("target")))
    return states, fates


sa, fa = go_lines(A, line)
sb, fb = go_lines(B)
print("after the save: continuous ids with lines", len(sa), "fates", len(fa), "; loaded ids with lines", len(sb), "fates", len(fb))
print("max id before the save in the continuous log:", max(int(kv(s)["id"]) for s in A[:line] if s.startswith("[HIVEORD]")))
new_a = sorted(i for i in sa if i not in ids and i > max(ids))
new_b = sorted(i for i in sb if i not in ids and i > max(ids))
print("first new ids after the save: continuous", new_a[:6], "loaded", new_b[:6])
print("ids after the load that are neither saved nor new:", sorted(i for i in sb if i not in ids and i <= max(ids))[:20])
dup = {i: v for i, v in fb.items() if len(v) > 1}
print("orders with more than one fate in the loaded run:", len(dup), list(dup.items())[:4])
dup = {i: v for i, v in fa.items() if len(v) > 1}
print("orders with more than one fate in the continuous run:", len(dup))
# which saved orders are live: not closed before the save in the continuous log
closed_before = {int(kv(s)["id"]) for s in A[:line] if s.startswith("[HIVEFATE]")}
live = [i for i in ids if i not in closed_before]
print("saved orders closed already before the save (history records):", len(ids) - len(live), "still live", len(live))
print("live with a fate later: continuous", sum(i in fa for i in live), "loaded", sum(i in fb for i in live), "live never closed: continuous", [i for i in live if i not in fa][:12], "loaded", [i for i in live if i not in fb][:12])
print("fate of the live orders by reason: continuous", Counter(fa[i][0][2] for i in live if i in fa).most_common(), "loaded", Counter(fb[i][0][2] for i in live if i in fb).most_common())
same = sum(i in fa and i in fb and fa[i][0][1:3] == fb[i][0][1:3] for i in live)
print("live orders with the same fate and reason in both:", same, "of", sum(i in fa and i in fb for i in live))
for tag, L in (("A", A[line:]), ("B", B), ("C", C)):
    print(tag, "save checks", Counter((kv(s).get("same"), kv(s).get("parsed")) for s in L if s.startswith("[HIVESAVECHECK]")).most_common())
    print(tag, "turn records", [s[:165] for s in L if s.startswith("[HIVETURN]")][:2])
print("the first line of each squad review after the load, the count of reviews vs continuous:", sum(s.startswith("[HIVEREVIEW]") for s in B), sum(s.startswith("[HIVEREVIEW]") for s in A[line:]))
print("squads kept in the load vs reorganised: squads in B", {kv(s).get("squad") for s in B if s.startswith("[HIVESQUADTURN]") and "squad=" in s}, "in C", {kv(s).get("squad") for s in C if s.startswith("[HIVESQUADTURN]") and "squad=" in s})
for tag, L in (("B", B), ("C", C), ("A", A[line:])):
    print(tag, "first turn 5 squad turn:", next((s[:210] for s in L if s.startswith("[HIVESQUADTURN]")), None))
print("C birth:", [s[:210] for s in C if s.startswith("[HIVESQUAD]")][:3])
print("units of C with HQ task from the start: squads", sum(s.startswith("[HIVESQUAD]") for s in C), "apart", next(s[:190] for s in C if s.startswith("[HIVEINIT]")))
