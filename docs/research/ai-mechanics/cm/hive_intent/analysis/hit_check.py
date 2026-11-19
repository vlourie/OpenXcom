"""HIVE COMBAT INTENT V0: RESULT against AIEXEC for every attack of the AI side in an intent's squad: RESULT says what its aim lost, AIEXEC what the side's enemies lost. Where they part, who really lost it: the [AICASUALTY] lines right after, and the aim's HP on the next state line. Read only.
Usage: hit_check.py <run> [print-limit]"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
L = read(sys.argv[1])
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 8
C = Counter()
shown = 0
last_exec = None
idx = 0
for i, s in enumerate(L):
    if s.startswith("[AIEXEC]"):
        try:
            last_exec = (i, json.loads(s[9:]))
        except ValueError:
            pass
    elif s.startswith("[HIVEINTENT] event=RESULT") and last_exec:
        k = kv(s)
        if int(k["act"]) not in ATT or str(last_exec[1]["unit"]) != k["unit"]:
            continue
        ex_d = last_exec[1].get("dmg", 0)
        ex_s = last_exec[1].get("stunned", 0)
        rs = int(k["hp_lost"])
        cls = "both_zero" if ex_d == 0 and rs == 0 else "same" if ex_d == rs else "exec_more" if ex_d > rs else "result_more"
        C[(cls, k["act"] == "6")] += 1
        if cls in ("exec_more", "result_more") and shown < limit:
            shown += 1
            print(cls, "turn", k["turn"], "unit", k["unit"], "act", k["act"], "aim", k["aim"], "contact", k["contact"], "result hit/down/hp", k["hit"], k["down"], rs, "exec dmg/stunned/downed", ex_d, ex_s, last_exec[1].get("downed"), "fdmg", last_exec[1].get("fdmg"))
            for t in L[max(0, last_exec[0] - 12) : i]:
                if t.startswith("[AICASUALTY]"):
                    c = kv(t)
                    print("     casualty", c.get("victim"), c.get("how"), "by", c.get("killer"), c.get("weapon"), c.get("pos"), "hit", c.get("hit"))
print(sys.argv[1], dict(C))
