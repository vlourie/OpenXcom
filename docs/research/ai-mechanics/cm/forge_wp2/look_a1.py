"""AI FORGE WP2: decision N of a run, against the choice taken from R5: the plan's stop condition. args: run"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
name = sys.argv[1]
run = rr.Run(name)
i, j, ev = rr.decision_at(run)
print("decide", ev[i][2][:220])
print("fp", ev[j][2][:400])
for k in range(j + 1, j + 8):
    print(ev[k][0], ev[k][2][:230])
act = next(d for *_, d in ev[j + 1:] if d.get("ev") == "act")
print("expected D0: type", rr.TYPE_D0, "to", rr.TO, rr.WEAPON, "unit", rr.UNIT, "got", act.get("type"), act.get("to"), act.get("weapon"), act.get("unit"))
pick = json.loads(Path(rr.HERE / "PICK_R5.json").read_text(encoding="utf-8"))
print("same rng as R5 at decide:", ev[i][3].get("rng") == pick["decide"]["rng"], "same rng at act:", act.get("rng") == pick["act"]["rng"])
print("branch line", run.branch)
print("game against WP1 R5", {k: v for k, v in rr.game_compare(name, "arch:R5").items() if k != "first_difference"})
print("first diff", rr.game_compare(name, "arch:R5")["first_difference"])
