"""AI FORGE WP2: the dump at N of P1 against A1, and the consequences of the branches from WP2_COMPARE.json and the logs. Reads only."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def dump_at(run, why="why=branch"):
    return next(((n, r) for n, r in run.dumps.items() if r and why in r[0]), (None, []))


a1, p1, b1, c1 = rr.Run("A1"), rr.Run("P1"), rr.Run("B1"), rr.Run("C1")
na, da = dump_at(a1)
np_, dp = dump_at(p1)
print("dump A1 at", na, len(da), "P1 at", np_, len(dp), "same", da == dp)
print("dumps in A1", {n: r[0][:40] for n, r in list(a1.dumps.items())[:30]})
print("dumps in P1", {n: r[0][:40] for n, r in list(p1.dumps.items())[:30]})
print("dump lines without why", [x for x in (rr.first_difference(da, dp),)])
print("rows only in one", len(set(da) ^ set(dp)))
for s in sorted(set(da) ^ set(dp))[:6]:
    print("  ", s[:260])

c = json.loads((rr.HERE / "WP2_COMPARE.json").read_text(encoding="utf-8-sig"))
for key in ("AB", "AC", "CB"):
    x = c[key]
    print("=====", key, x["a"], x["b"], "prefix", x["prefix_events"], x["prefix_chain_identical"], x["prefix_game_lines"], x["prefix_game_identical"], "dump", x["dump_at_N_lines"], x["dump_at_N_identical"])
    print("first section difference", json.dumps(x["first_section_difference"], ensure_ascii=False))
    print("after decision dumps", x["after_decision_dump_events"], "units", len(x["after_decision_units"]), "floors", len(x["after_decision_floors"]))
    for u in x["after_decision_units"][:10]:
        print("  ", json.dumps(u, ensure_ascii=False)[:420])
    print("end", json.dumps({k: {f: v[f] for f in ("result", "casualties", "dead", "decisions")} for k, v in x["end"].items()}, ensure_ascii=False))
    print("casualty first difference", x["casualties_first_difference"])
    print("what a did")
    for s in x["what_a_did"][:10]:
        print("  ", s[:190])
    print("what b did")
    for s in x["what_b_did"][:10]:
        print("  ", s[:190])
print("actor", c["AB"]["actor_at_N"])
print("fp", json.dumps(c["AB"]["fingerprint_at_N"]["a"]), c["AB"]["fingerprint_at_N"]["chain"], c["AB"]["fingerprint_at_N"]["rng"])
for name in ("A1", "B1", "C1"):
    r = rr.Run(name)
    reuse = next(s for s in r.lines if s.startswith("[AIREUSE]"))
    res = next(s for s in r.lines if s.startswith("[AIRESULT]"))
    print(name, reuse[:140])
    print(name, res[:520])
