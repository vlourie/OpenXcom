"""UNIFIED ARMY SAFETY, read only: was the loss of free tries in V0 too: a think of five tries with a node of the condition among them, and how many of those nodes failed the path. Usage: us_v0tries.py"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
NONE = "(-1,-1,-1)"
for run in ("ua1_UN_M6_s1", "ua2_UN_M3_s1", "ua3_UN_M8_s1", "us1_QN_M6_s1", "us2_QN_M3_s1", "us3_QN_M8_s1"):
    L = [kv(s) for s in read(run) if s.startswith("[HIVEUA] event=CHOICE")]
    seq = []
    cur = None
    for k in L:
        if k["try"] == "1" or cur is None or cur[-1]["unit"] != k["unit"] or int(k["try"]) <= int(cur[-1]["try"]):
            cur = []
            seq.append(cur)
        cur.append(k)
    lost = [q for q in seq if len(q) == 5 and any(c["chosen"] != NONE for c in q)]
    tried = sum(c["chosen"] != NONE for c in L)
    fail = sum(1 for a, b in zip(L, L[1:]) if a["chosen"] != NONE and b["unit"] == a["unit"] and b["turn"] == a["turn"] and int(b["try"]) == int(a["try"]) + 1)
    print(run, "thinks", len(seq), "five tries with the condition's node", len(lost), dict(Counter((q[0]["unit"], q[0]["turn"]) for q in lost)), "condition's node tried", tried, "path failed", fail)
