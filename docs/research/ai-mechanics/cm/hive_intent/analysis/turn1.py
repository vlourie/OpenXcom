"""COMBAT INTENT V0, choosing the episode: the first turn of a RA battle before any change can act. Each first attack of a unit: squad, role and contact of its squad, the branch, the aim, the contacts open to it by the journal's candidates. Read only.
Usage: turn1.py <run> <turn>"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
run, want = sys.argv[1], int(sys.argv[2])
lines = read(run)
squad, roles, acts = {}, {}, {}
rows = []
last = None
for s in lines:
    if s.startswith("[HIVESQUAD]") and "members=" in s:
        k = kv(s)
        for m in k["members"].split(","):
            squad[m.rstrip("SLA")] = k["id"]
    elif s.startswith("[HIVECC] event=DECISION") and int(kv(s)["turn"]) == want:
        roles = {p.split("=")[0]: p.split("=")[1] for p in s.split("squads:")[1].split()}
        print(s[:300])
    elif s.startswith("[HIVECC] event=CONTACT") and int(kv(s)["turn"]) == want:
        print(s[s.index("target"):][:90])
    elif s.startswith("[AICAND] acts="):
        try:
            acts[s.split()[1].split("=")[1]] = json.loads(s.split("list=", 1)[1])
        except ValueError:
            pass
    elif s.startswith("[AIDECIDE]"):
        k = kv(s)
        last = None
        if k["side"] == "1" and int(k["turn"]) == want and int(k["act"]) in ATT:
            last = dict(k, rec=None)
            rows.append(last)
    elif s.startswith("[AIREC]") and last is not None and last["rec"] is None:
        try:
            last["rec"] = json.loads(s[8:])
        except ValueError:
            pass
by = defaultdict(list)
seen = set()
for d in rows:
    rec = d["rec"] or {}
    cand = acts.get((rec.get("cand") or {}).get("acts"), [])
    opened = sorted({str(c["u"]) for c in cand if c.get("k") == "a" and c.get("lof") and c.get("tu", 10**6) <= int(d["tu"]) and int(c["u"]) < 1000000})
    sq = squad.get(d["unit"], "?")
    by[sq].append((d["unit"], d["n"], "act" + d["act"], (rec.get("base") or {}).get("src"), "aim", d["aim"], "tu", d["tu"], "open", opened))
for sq in sorted(by, key=lambda x: (x == "?", int(x) if x != "?" else 0)):
    print("squad", sq, roles.get(sq))
    for r in by[sq]:
        print("   ", r)
