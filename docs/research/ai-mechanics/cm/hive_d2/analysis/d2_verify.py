"""HIVE D2 CORRECTION, read only: the numbers the report states that were read by eye: thinks, refusals in the window, the exit, whole-turn losses by node owner, OFF of the soldiers who lost turns, the no-reason empty walks."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
tot = 0
for r in ("d23_DN_M3_s1", "d24_DN_M3_s1", "d26_DN_M6_s1"):
    n = sum(s.startswith("[HIVEUA] event=PATROLEND") for s in read(r))
    tot += n
    print(r, "thinks", n)
print("thinks in the three ON runs", tot)
L = read("d23_DN_M3_s1")
ref = [i for i, s in enumerate(L) if s.startswith("[HIVEUA] event=OFFER_REFUSED")]
print("refusals: lines", ref[0], "..", ref[-1], "count", len(ref))


def lost(run, us):
    L = read(run)
    seq = []
    for s in L:
        if s.startswith("[AIDECIDE]"):
            seq.append(kv(s))
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[9:])
            if seq and str(j.get("unit")) == seq[-1]["unit"]:
                seq[-1]["spent_"] = j.get("spent", 0)
    res = {}
    for k in seq:
        if k.get("side") == "1":
            key = (int(k["turn"]), k["unit"])
            res[key] = res.get(key, 0) + k.get("spent_", 0)
    return {x: res.get(x) for x in us}


cases = [(2, "1000025"), (3, "1000025"), (4, "1000025"), (4, "1000011"), (4, "1000014"), (3, "1000008"), (1, "1000050")]
print("M3 TU spent, OFF:", lost("d21_DO_M3_s1", cases))
print("M3 TU spent, ON: ", lost("d23_DN_M3_s1", cases))
print("M3 TU spent, SAFETY:", lost("us2_QN_M3_s1", cases))
c6 = [(5, "1000021"), (6, "1000021"), (7, "1000021"), (8, "1000021"), (5, "1000037")]
print("M6 TU spent, OFF:", lost("d25_DO_M6_s1", c6))
print("M6 TU spent, ON: ", lost("d26_DN_M6_s1", c6))
for run in ("d23_DN_M3_s1", "d26_DN_M6_s1"):
    P = [kv(s) for s in read(run) if s.startswith("[HIVEPERF]") and "phase=plan" in s]
    print(run, "plan floods", sum(int(p.get("floods", 0)) for p in P))
