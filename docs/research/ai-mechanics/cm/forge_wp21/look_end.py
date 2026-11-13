"""AI FORGE WP2.1: the raw ends of the battles, the raw differences kept, the sections at the three points of the two runs."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for name in ("A1", "A2", "B1", "B2", "C1"):
    run = rr.Run(name)
    s = next(x for x in run.lines if x.startswith("[AIRESULT]"))
    print(name, s[:420])
x = json.loads((Path(__file__).resolve().parent / "WP21_COMPARE.json").read_text(encoding="utf-8-sig"))
for k in ("AA", "BB"):
    print(k, json.dumps(x[k]["raw_differences"], ensure_ascii=False)[:500])
print("D0", json.dumps(x["off"][0]["raw_differences"], ensure_ascii=False)[:500])
print("off", [(g["a"], g["b"], g["identical"]) for g in x["off"]])
print("ledger", [(r[0], r[3], r[2][:12]) for r in x["ledger"]])
a = rr.Run("A1")
print("A1 bytes, sha of frozen and lines", (Path(__file__).resolve().parent / "FROZEN.txt").read_text(encoding="utf-8")[:600])
# the actor and the target at the intervention and at the next decision
for name in ("A1", "B1"):
    run = rr.Run(name)
    for why in ("intervene", "after_branch"):
        rows = rr.unit_rows(rr.dump_of(run, why))
        print(name, why, rows[str(rr.UNIT)][:150], "|", rows["324"][:150])
