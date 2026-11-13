"""Every fire and in_place order of REINFORCE, decision by decision: where the unit stood, what it chose, whether a line to the contact was there. Read only."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
sum_ = Counter()
for run in sys.argv[1:]:
    orders, seq = {}, defaultdict(list)
    pending = None
    arrived = {}
    for s in read(run):
        if s.startswith("[HIVECC]"):
            k = kv(s)
            if k["event"] == "ORDER" and k["role"] == "REINFORCE" and k["kind"] in ("fire", "in_place"):
                orders[(int(k["turn"]), int(k["unit"]))] = k
        elif s.startswith("[HIVEORD]"):
            k = kv(s)
            if k.get("state") == "COMPLETED":
                arrived[(int(k["turn"]), int(k["unit"]))] = k.get("at")
        elif s.startswith("[AICAND] acts"):
            try:
                pending = (int(s.split("unit=")[1].split()[0]), json.loads(s[s.find("list=") + 5:]))
            except ValueError:
                pending = None
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] != "1":
                continue
            t, u = int(k["turn"]), int(k["unit"])
            seq[(t, u)].append((k, pending[1] if pending and pending[0] == u else None))
            pending = None
    for (t, u), o in sorted(orders.items()):
        c = int(o["contact"])
        parts = []
        reached = (t, u) in arrived or o["kind"] == "in_place"
        line_at_goal = 0
        for k, L in seq[(t, u)]:
            lof = "?"
            if L is not None:
                x = [a for a in L if a.get("k") == "a" and a.get("u") == c]
                lof = "L" if any(a.get("lof") for a in x) else "n" if x else "-"
            if k["from"] == o.get("target") and lof == "L":
                line_at_goal = 1
            parts.append(f"{k['from']}m{k['mode']}a{k['act']}{'>' + k['aim'] if int(k['act']) in ATT else ''}:{lof}")
        hit = any(int(k["act"]) in ATT and k["aim"] == str(c) for k, _ in seq[(t, u)])
        anyhit = any(int(k["act"]) in ATT for k, _ in seq[(t, u)])
        sum_["n"] += 1
        sum_["reached"] += reached
        sum_["line_at_goal"] += line_at_goal
        sum_["hit_contact"] += hit
        sum_["hit_any"] += anyhit
        print(run[:6], "t", t, u, o["kind"], "c", c, "goal", o.get("target"), "cost", o.get("cost"), "tu", o.get("tu"), "shot", o.get("shot"), "| reached", int(reached), "|", " ".join(parts))
print(dict(sum_))
