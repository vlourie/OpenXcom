"""UNIFIED ARMY SAFETY: the laws of one ON run: no node outside the unit's kind of search, what the three guards of M6 did and on whose node, what else the task changed, time. chosen (-1,-1,-1) is no node: the rung then is only the last one tried. Usage: us_check.py <run> [unit...]"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
NONE = "(-1,-1,-1)"
run = sys.argv[1]
U = sys.argv[2:] or ["1000021", "1000038", "1000039"]
L = read(run)
ch = [kv(s) for s in L if s.startswith("[HIVEUA] event=CHOICE")]
got = [c for c in ch if c["chosen"] != NONE]
changed = [c for c in got if c["chosen"] != c["free"]]
print(run, "CHOICE", len(ch), "by scout", dict(Counter(c["scout"] for c in ch)), "chosen", len(got), "by rung", dict(Counter(c["rung"] for c in got)), "changed", len(changed), "by rung", dict(Counter(c["rung"] for c in changed)))
bad = [c for c in got if c["scout"] == "0" and c["chosen_linked"] == "0"]
print("S1 scout=0, a chosen node not linked:", len(bad))
for c in bad[:10]:
    print("   ", c["turn"], c["unit"], "from", c["from"], "chosen", c["chosen"], "rung", c["rung"])
sc0 = [c for c in ch if c["scout"] == "0"]
print("scout=0:", len(sc0), "free not linked (the engine's own step to the other kind):", sum(c["free_linked"] == "0" and c["free"] != NONE for c in sc0), "no free node:", sum(c["free"] == NONE for c in sc0))
print("changed by scout", dict(Counter(c["scout"] for c in changed)), "scout=0 chosen, all linked:", sum(c["chosen_linked"] == "1" for c in got if c["scout"] == "0"))
for u in U:
    c = [x for x in ch if x["unit"] == u]
    g = [x for x in c if x["chosen"] != NONE]
    d = [kv(s) for s in L if s.startswith("[AIDECIDE]") and f" unit={u} " in s]
    print("--", u, "choices", len(c), "scout", dict(Counter(x["scout"] for x in c)), "chosen", len(g), "changed", sum(x["chosen"] != x["free"] for x in g), "free linked", sum(x["free_linked"] == "1" for x in c), "free far", sum(x["free_linked"] == "0" and x["free"] != NONE for x in c))
    for x in c[:12]:
        print("    t", x["turn"], "try", x["try"], "at", x["at"], "from", x["from"], "rank", x["from_rank"], "scout", x["scout"], "free", x["free"], "fl", x["free_linked"], "chosen", x["chosen"], "cl", x["chosen_linked"], "rung", x["rung"])
    print("   decisions", len(d), "modes", dict(Counter(x["mode"] for x in d)), "acts", dict(Counter(x["act"] for x in d)), "places", len({x["from"] for x in d}))
    print("   walks", [(x["turn"], x["from"], x["to"]) for x in d if x["act"] == "2"][:12])
print("-- perf")
for s in L:
    if s.startswith("[HIVEPERF]") and "phase=turn" in s:
        print("  ", s[11:].strip()[:230])
print("plan", [kv(s).get("us") for s in L if s.startswith("[HIVEPERF]") and "phase=plan" in s])
for s in L:
    if s.startswith("[AIRESULT]"):
        r = kv(s)
print("result", {k: r.get(k) for k in ("how", "turn", "pdead", "phplost", "hostile", "hdead", "hout", "hleft", "pattacks", "hattacks", "ms")})
