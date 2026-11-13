"""Orders that arrived on their first turn: TU really spent against the plan (flood) and the path_now asked at first use. Does path_now overstate the walk? Read only."""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
tab = Counter()
rows = []
for run in sys.argv[1:]:
    now = {}
    start = {}
    for s in read(run):
        if not s.startswith("[HIVEORD]"):
            continue
        k = kv(s)
        key = (k["id"], k["turn"])
        note = s.split("note=", 1)[1] if "note=" in s else ""
        m = re.search(r"path_now=(-?\d+) plan=(-?\d+)", note)
        if m and key not in now:
            now[key] = (int(m.group(1)), int(m.group(2)), int(k["tu"]), k["why"], k["at"], k["target"])
        if k.get("state") == "COMPLETED" and "arrived" in note and key in now:
            p_now, plan, tu0, why, at, target = now[key]
            spent = tu0 - int(k["tu"])
            if at == target:
                continue
            tab["arrived"] += 1
            tab["spent==plan"] += spent == plan
            tab["spent==now"] += spent == p_now
            tab["now>spent"] += p_now > spent
            tab["now<spent"] += p_now < spent
            tab["spent>plan"] += spent > plan
            if p_now != plan:
                rows.append((run, k["id"], k["unit"], k["turn"], why, at, target, "tu", tu0, "plan", plan, "now", p_now, "spent", spent))
print(dict(tab))
for r in rows[:30]:
    print(*r)
print("rows", len(rows))
