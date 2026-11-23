"""HIVE COMBAT INTENT V0: walking in circles that costs time units: a soldier of the AI side comes back in one turn, with fewer TU, to a tile it decided from before, and its act is a walk. Repeats of the same decision at the same TU (a step that did not run) are not counted. Read only.
Usage: bounce.py <run> [<run>...]"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
for run in sys.argv[1:]:
    walks = defaultdict(list)
    changed = set()
    for s in read(run):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1":
                walks[(k["turn"], k["unit"])].append((k["from"], int(k["tu"]), k["act"], k.get("to"), k.get("aim")))
        elif s.startswith("[HIVEINTENT] event=CHOICE") and " changed=1 " in s and " site=firepoint " in s:
            k = kv(s)
            changed.add((k["turn"], k["unit"]))
    rows = []
    for key, w in walks.items():
        seen = {}
        burned = 0
        back = 0
        for frm, tu, act, to, aim in w:
            if frm in seen and tu < seen[frm]:
                back += 1
                burned += seen[frm] - tu
            seen[frm] = tu
        if back >= 1 and any(x[2] == "2" for x in w):
            rows.append((burned, back, key, key in changed))
    rows.sort(reverse=True)
    print(f"{run}: soldier-turns coming back at a TU cost {len(rows)}; returns {sum(r[1] for r in rows)}; TU between the returns {sum(r[0] for r in rows)}; on firepoint changed {sum(1 for r in rows if r[3])}")
    for r in rows[:6]:
        print("   ", r)
