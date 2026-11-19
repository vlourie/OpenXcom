"""Orders whose path_now is far above the plan (now >= plan + 20): what the unit did and spent, on any role. Read only."""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
tab = Counter()
for run in sys.argv[1:]:
    open_ = {}
    for s in read(run):
        if not s.startswith("[HIVEORD]"):
            continue
        k = kv(s)
        key = (k["id"], k["unit"])
        note = s.split("note=", 1)[1] if "note=" in s else ""
        m = re.search(r"path_now=(-?\d+) plan=(-?\d+)", note)
        if m and key not in open_ and int(m.group(1)) >= int(m.group(2)) + 20:
            open_[key] = dict(run=run, id=k["id"], unit=k["unit"], turn=k["turn"], why=k["why"], at=k["at"], target=k["target"], tu=int(k["tu"]), plan=int(m.group(2)), now=int(m.group(1)), end=None)
        elif key in open_ and open_[key]["end"] is None and k.get("state") in ("COMPLETED", "PAUSED", "CANCELLED", "FAILED") and k["turn"] == open_[key]["turn"]:
            open_[key].update(end=k["state"], endat=k["at"], endtu=int(k["tu"]), note=note[:30])
    for r in open_.values():
        tab["n"] += 1
        tab[str(r.get("end"))] += 1
        print(r["run"][:6], r["id"], r["unit"], "t" + r["turn"], r["why"], r["at"], "->", r["target"], "tu", r["tu"], "plan", r["plan"], "now", r["now"], r.get("end"), r.get("endat"), "left", r.get("endtu"), r.get("note"))
print(dict(tab))
