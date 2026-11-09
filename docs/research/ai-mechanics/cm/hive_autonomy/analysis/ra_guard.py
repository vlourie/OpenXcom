"""RESTORE COMBAT AUTONOMY: FREE answers on an order still named guard_sector: is the squad still a guard? The last [HIVEHOLD] and [HIVETASK] of its squad before the answer. And TU against tumax on every state line. Read only."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
for run in ("cc8_CC_M6_s1", "ra1_AN_M6_s1", "ra2_AN_M6_s2", "ra3_AV_M3_s1"):
    hold = {}
    task = {}
    order = {}
    C = Counter()
    sample = []
    tu = Counter()
    for s in read(run):
        if s.startswith("[HIVEHOLD]"):
            k = kv(s)
            hold[k["squad"]] = (k.get("event"), k.get("why"), k.get("turn"))
        elif s.startswith("[HIVETASK]"):
            k = kv(s)
            task[k["squad"]] = (k.get("task"), k.get("kind"), k.get("turn"), k.get("role"))
        elif s.startswith("[HIVEORD]"):
            k = kv(s)
            order[k["unit"]] = k
        elif s.startswith("[HIVECC] event=AUTONOMY"):
            k = kv(s)
            if k["answer"] == "FREE" and k["why"] == "guard_sector":
                o = order.get(k["unit"], {})
                h = hold.get(o.get("squad"), ("?",))
                t = task.get(o.get("squad"), ("?",))
                C[f"hold_event={h[0]} squad_task={t[0]} order_turn_same={o.get('turn') == k['turn']} from={k['from']}"] += 1
                if len(sample) < 3:
                    sample.append((k["turn"], k["unit"], o.get("squad"), h, t, o.get("turn"), o.get("state"), o.get("task")))
        elif s.startswith("[AISTATE]"):
            k = kv(s)
            if k.get("faction") == "1":
                tu["lines"] += 1
                tu["above_tumax"] += int(k["tu"]) > int(k["tumax"])
    print(run, "tu", dict(tu))
    print("   free on guard_sector", dict(C.most_common()))
    print("   sample", sample)
