"""Plan cost of a contact order against the engine's own path asked at the order's first use (path_now), and what came of it. Read only."""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
tab = defaultdict(Counter)
rows = []
for run in sys.argv[1:]:
    orders = {}
    now = {}
    pause = set()
    arrived = set()
    dec = defaultdict(list)
    for s in read(run):
        if s.startswith("[HIVECC]"):
            k = kv(s)
            if k["event"] == "ORDER" and k["role"] == "REINFORCE" and k["kind"] in ("fire", "approach"):
                orders[(int(k["turn"]), int(k["unit"]))] = k
        elif s.startswith("[HIVEORD]"):
            k = kv(s)
            key = (int(k["turn"]), int(k["unit"]))
            note = s.split("note=", 1)[1] if "note=" in s else ""
            m = re.search(r"path_now=(-?\d+) plan=(-?\d+)", note)
            if m and key not in now:
                now[key] = (k["id"], int(m.group(1)), int(m.group(2)))
            if "pause_no_time_units" in note:
                pause.add(key)
            if k.get("state") == "COMPLETED":
                arrived.add(key)
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1":
                dec[(int(k["turn"]), int(k["unit"]))].append(k)
    for key, o in orders.items():
        kind = o["kind"]
        tab[kind]["n"] += 1
        if key not in now:
            tab[kind]["not_asked"] += 1
            continue
        _, p_now, plan = now[key]
        tu, shot = int(o.get("tu", 0)), int(o.get("shot", 0))
        c = o["contact"]
        hit = any(int(d["act"]) in ATT and d["aim"] == c for d in dec[key])
        anyh = any(int(d["act"]) in ATT for d in dec[key])
        over = p_now > plan + 8
        fits = p_now + shot <= tu
        tab[kind]["asked"] += 1
        tab[kind]["real_more_than_plan_by_8"] += over
        tab[kind]["real_path_fits_shot"] += fits
        tab[kind]["arrived"] += key in arrived
        tab[kind]["paused_no_tu"] += key in pause
        tab[kind]["hit_contact_fits"] += hit and fits
        tab[kind]["hit_contact_nofit"] += hit and not fits
        tab[kind]["hit_any_fits"] += anyh and fits
        tab[kind]["hit_any_nofit"] += anyh and not fits
        if over:
            rows.append((run[:6], key, kind, "plan", plan, "now", p_now, "tu", tu, "arrived", key in arrived, "pause", key in pause))
keys = ["n", "not_asked", "asked", "real_more_than_plan_by_8", "real_path_fits_shot", "arrived", "paused_no_tu", "hit_contact_fits", "hit_contact_nofit", "hit_any_fits", "hit_any_nofit"]
print("kind\t" + "\t".join(keys))
for k in sorted(tab):
    print(k + "\t" + "\t".join(str(tab[k][x]) for x in keys))
for r in rows:
    print(*r)
