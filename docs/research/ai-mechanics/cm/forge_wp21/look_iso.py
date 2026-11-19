"""AI FORGE WP2.1: what the two modes did, from the two logs: every event from the action to the next decision, the units and the tiles, the first differences by section."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
out = {}
for name in ("A1", "B1"):
    run = rr.Run(name)
    i, j, ev = rr.act_at(run)
    nxt = next(k for k in range(j + 1, len(ev)) if ev[k][3].get("ev") == "decide")
    print(f"== {name}: events {j}..{nxt}, decision index {i}")
    for k in range(j - 2, nxt + 1):
        print(k, ev[k][0], ev[k][2].strip()[:190])
    # the engine's own lines between the action and the next decision
    head, tail = f"[FORGE] n={ev[j][0]} ", f"[FORGE] n={ev[nxt][0]} "
    a = next(x for x, s in enumerate(run.lines) if s.startswith(head))
    b = next(x for x, s in enumerate(run.lines) if s.startswith(tail))
    print("-- engine lines")
    for s in run.lines[a:b]:
        if s.startswith("[AI") or s.startswith("[FORGEDUMP] ") and " why=" in s:
            print("  ", s[:260])
    ef = rr.effects(run)
    out[name] = ef
    print("-- units since the intervention")
    for u in ef["units"]:
        print("  ", u["unit"], u["type"], {k: v for k, v in u["fields"].items() if k not in ("uh", "ai", "inv", "type")})
    print("-- tiles", ef["tiles_changed"], ef["first_floor"])
    for t in ef["tiles"][:14]:
        print("  ", t[:230])
    c = rr.casualties(run)
    print("-- casualties", len(c), "dead", sum(1 for x in c if x["dead"] == "1"), c[:4])
x = json.loads((Path(__file__).resolve().parent / "WP21_COMPARE.json").read_text(encoding="utf-8-sig"))
ab = x["AB"]
print("first section differences", json.dumps(ab["first_section_difference"], ensure_ascii=False))
print("sections at intervention", ab["sections_at_intervention"])
print("fingerprint at decide", ab["fingerprint_at_decide"])
print("actor", ab["actor_at_intervention"])
print("next decision units", json.dumps(ab["next_decision_units"], ensure_ascii=False)[:1800])
print("next decision floor", ab["next_decision_first_floor"])
print("end", ab["end_raw_not_a_measure_of_use"])
print("AC", x["AC"]["chain_first_difference"], x["AC"]["pre_all_same"], x["AC"]["dump_identical"])
print("dump lines", ab["dump_lines"], "prefix game lines", ab["prefix_game_lines"], "prefix events", ab["prefix_events"])
