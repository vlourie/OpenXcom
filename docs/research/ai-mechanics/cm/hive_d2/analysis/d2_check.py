"""HIVE D2 CORRECTION, read only, one run: the invariant of the tries, the offers and what came of them, the law of scout=false, standing soldiers, the time. d2_check.py <run> [unit ...]"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
NONE = "(-1,-1,-1)"
run = sys.argv[1]
U = sys.argv[2:]
L = read(run)
ch = [kv(s) for s in L if s.startswith("[HIVEUA] event=CHOICE")]
ref = [kv(s) for s in L if s.startswith("[HIVEUA] event=OFFER_REFUSED")]
end = [kv(s) for s in L if s.startswith("[HIVEUA] event=PATROLEND")]
print("=====", run)
print("thinks with an intent", len(end), "tries", dict(sorted(Counter(int(e["tries"]) for e in end).items())))
bad = [e for e in end if int(e["tries"]) != int(e["free_checked"]) + int(e["free_none"]) + int(e["taken"])]
print("invariant tries = free_checked + free_none + taken, broken:", len(bad))
for e in bad[:8]:
    print("   ", e)
none = [e for e in end if e["end"] == "none"]
print("no node at the end:", len(none), "with fewer than 5 tries:", sum(int(e["tries"]) != 5 for e in none), "with a refused offer:", sum(int(e["refused"]) > 0 for e in none), "units", dict(Counter(e["unit"] for e in none)))
print("offers in thinks", sum(int(e["offers"]) for e in end), "refused", sum(int(e["refused"]) for e in end), "taken", sum(int(e["taken"]) for e in end), "thinks with a refusal", sum(int(e["refused"]) > 0 for e in end))
print("refused: expanded=0 (before any search)", sum(r["expanded"] == "0" for r in ref), "seed moved", sum(r["seed_moved"] != "0" for r in ref), "units", dict(Counter(r["unit"] for r in ref).most_common(8)))
print("after a refusal the free node was taken at once / the free failed too:", end=" ")
ok = 0
for r in ref:
    e = [x for x in end if x["unit"] == r["unit"] and x["turn"] == r["turn"]]
    ok += any(x["end"] == r["free"] for x in e)
print(ok, len(ref) - ok)
got = [c for c in ch if c["chosen"] != NONE]
print("CHOICE", len(ch), "by scout", dict(Counter(c["scout"] for c in ch)), "chosen", len(got), "changed", sum(c["chosen"] != c["free"] for c in got))
print("S1 scout=0, a chosen node not linked:", sum(c["scout"] == "0" and c["chosen_linked"] == "0" for c in got), "| scout=0 chosen linked:", sum(c["scout"] == "0" and c["chosen_linked"] == "1" for c in got), "| scout=0 chosen, not the best by flags (chosen != free):", sum(c["scout"] == "0" and c["chosen"] != c["free"] for c in got))
kept = [kv(s) for s in L if s.startswith("[HIVEUA] event=KEPT_DROP")]
print("KEPT_DROP (only written now):", len(kept), "KEPT_BACK:", sum(s.startswith("[HIVEUA] event=KEPT_BACK") for s in L))
dec = [kv(s) for s in L if s.startswith("[AIDECIDE]")]
if kept:
    # the node the task would have taken away: did the soldier reach it later, and did it walk on after that
    reached = 0
    for k in kept:
        node = k.get("kept") or k.get("node")
        if node and any(d["unit"] == k["unit"] and int(d["turn"]) >= int(k["turn"]) and d["from"] == node for d in dec):
            reached += 1
    print("   of those, the soldier stood on that node later:", reached)
for u in U:
    print("--", u)
    for s in L:
        if f" unit={u} " not in s:
            continue
        if s.startswith("[HIVEUA] event=CHOICE"):
            c = kv(s)
            if c["turn"] in ("1", "2"):
                print("   t", c["turn"], "CHOICE try", c["try"], "at", c["at"], "scout", c["scout"], "free", c["free"], "chosen", c["chosen"], "rung", c["rung"])
        elif s.startswith("[HIVEUA] event=OFFER_REFUSED") or s.startswith("[HIVEUA] event=PATROLEND"):
            c = kv(s)
            if c["turn"] in ("1", "2"):
                print("   ", s[8:].strip()[:190])
        elif s.startswith("[AIDECIDE]"):
            c = kv(s)
            if c["turn"] in ("1", "2"):
                print("   t", c["turn"], "DECIDE from", c["from"], "tu", c["tu"], "mode", c["mode"], "act", c["act"], "to", c.get("to"))
print("-- perf by turn")
keys = ("floods", "floodUs", "intentFloods", "intentFloodUs", "offers", "offersRefused", "offersTaken", "refusedUs", "maxRefusedUs", "takenUs", "seedMoved", "repeatFloods", "repeatUs", "repeatTurnFloods", "repeatTurnUs", "unusedFloods", "unusedUs", "sigUs", "freeUs", "stepsUs", "pathUs", "paths", "pathFails", "thinkUs")
rows = [kv(s) for s in L if s.startswith("[HIVEPERF]") and "phase=turn" in s]
plan = {kv(s)["turn"]: kv(s) for s in L if s.startswith("[HIVEPERF]") and "phase=plan" in s}
tot = Counter()
peak = 0
for r in rows:
    pl = plan.get(r["turn"], {})
    part = int(r["floodUs"]) + int(r["freeUs"]) + int(r["stepsUs"]) + int(r["thinkUs"]) + int(r["refusedUs"])
    peak = max(peak, part)
    print("  t", r["turn"], " ".join(f"{k}={r.get(k)}" for k in keys), "planUs", pl.get("us"), "planFloods", pl.get("floods"))
    for k in keys:
        tot[k] += int(r.get(k, 0))
print("  sum", " ".join(f"{k}={tot[k]}" for k in keys))
for s in L:
    if s.startswith("[AIRESULT]"):
        print(s[:170].strip())
