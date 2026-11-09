"""COORDINATED OPERATION, phase C: numbers for the report, from the logs only. Each run: was the target seen by the side at the moment of the proposal (aistart seenby, and its logged place against the assigned one), modes of the fighters on the operation's turns, states reached, whether EXECUTING ever came, on-cell check by state line, reactions on the fighters' turn, hits on fighters during the player's next turn, bot's shot at the staged fighter; the chain table. Read only."""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
for run in ("op1_OA_M3_s1", "op3_OS_M3_s1", "op4_OA_M3_s1", "op5_OG_M3_s1", "op6_OG_M3_s2"):
    L = read(run)
    print("=====", run)
    prop = next(kv(s) for s in L if s.startswith("[HIVEOP] event=PROPOSED"))
    t = prop["turn"]
    st = [kv(s) for s in L if s.startswith("[AISTATE] aistart") and kv(s).get("turn") == t and kv(s).get("unit") == prop["target"]]
    print(" proposal: turn", t, "target", prop["target"], "logged at", prop["at"], "| state line:", st[0]["pos"] if st else None, "seenby", st[0].get("seenby") if st else None, "spotted", st[0].get("spotted") if st else None)
    states = [kv(s)["state"] for s in L if s.startswith("[HIVEOP] event=STATE")]
    print(" states:", states, "EXECUTING reached:", "EXECUTING" in states, "operations:", sum(1 for x in states if x == "VALIDATED"))
    asg = [kv(s) for s in L if s.startswith("[HIVEOP] event=ASSIGN")]
    print(" cells:", [(a["unit"], a["cell"], a["cost"], a["next_blows"]) for a in asg], "different cells:", len({a["cell"] for a in asg}) == 2)
    ids = {a["unit"] for a in asg}
    next_t = str(int(t) + 1)
    for a in asg:
        p = [kv(s) for s in L if s.startswith("[AISTATE] pstart") and kv(s).get("turn") == next_t and kv(s).get("unit") == a["unit"]]
        print(f"   {a['unit']} at the start of the player's turn {next_t}:", p[0]["pos"] if p else None, "on its cell:", (p[0]["pos"] == a["cell"]) if p else None, "tu", p[0]["tu"] if p else None, "seenby", p[0].get("seenby") if p else None)
    modes = Counter()
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["unit"] in ids and k["turn"] in (t, next_t) and k.get("side") == "1":
                modes[(k["unit"], k["turn"], k["mode"])] += 1
    print(" fighters' modes on the two turns:", sorted(modes.items()))
    print(" events:", Counter(kv(s)["event"] for s in L if s.startswith("[HIVEOP]")))
    print(" ", next((s[9:200] for s in L if s.startswith("[HIVEOP] event=RESULT")), "no result"))
