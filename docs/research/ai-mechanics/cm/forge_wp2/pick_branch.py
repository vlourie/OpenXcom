"""AI FORGE WP2: the branch point, by a rule fixed before any new battle, from the WP1 logs. args: WP1 run names (R5 L8, R2 M3).
Rule: the first decision of the hostile side (s=1) in log order whose own action is a firearm shot and whose candidates, as the engine's
own candidate list gave them at that decision, hold another shot of the same unit at the same target with the same weapon, in another mode,
with chance above 0, a clear line of fire and time units it can pay. The first match is taken, nothing after it is read: the outcome
of the shot is not looked at."""
import json
import re
import sys
from pathlib import Path

F = Path(__file__).resolve().parent.parent / "forge"
sys.path.insert(0, str(F))
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SHOTS = {7: "AUTO", 8: "SNAP", 9: "AIMED"}


def pick(run):
    lines = sic.read_log(*rr.source_of(run))
    acts = {}
    for s in lines:
        if s.startswith("[AICAND] acts="):
            m = re.match(r"\[AICAND\] acts=(\w+) unit=(\d+) list=(\[.*\])$", s)
            acts[m.group(1)] = json.loads(m.group(3))
    decision = 0
    open_dec = None
    rec = None
    act = None
    seen = 0

    def check():
        nonlocal seen
        if not (open_dec and act and rec):
            return None
        kv = act
        if open_dec["s"] != "1" or int(kv["type"]) not in SHOTS:
            return None
        seen += 1
        lst = acts.get(rec["cand"]["acts"], [])
        to = [int(x) for x in kv["to"].split(",")]
        own = [c for c in lst if c.get("k") == "a" and c["t"] == int(kv["type"]) and c["to"] == to and c["w"] == kv["weapon"]]
        if not own:
            return None
        others = [c for c in lst if c.get("k") == "a" and c["t"] != int(kv["type"]) and c["t"] in SHOTS and c["to"] == to and c["w"] == kv["weapon"]
                  and c["u"] == own[0]["u"] and c["p"] > 0 and c["lof"] == 1 and c["tu"] <= int(open_dec["tu"])]
        if not others:
            return None
        return {"run": run, "decision": decision, "decide": open_dec, "act": kv, "own": own[0], "alternatives": others, "shots_before": seen - 1}

    for s in lines:
        if s.startswith("[AIREC] "):
            rec = json.loads(s[8:])
            continue
        if not s.startswith("[FORGE] "):
            continue
        kv = dict(re.findall(r"(\w+)=(\S+)", s))
        if kv.get("ev") == "decide":
            found = check()
            if found:
                return found
            decision += 1
            open_dec, rec, act = kv, None, None
        elif kv.get("ev") == "act" and open_dec:
            act = kv
    return check()


for run in sys.argv[1:]:
    print(json.dumps(pick(run), ensure_ascii=False, indent=0))
