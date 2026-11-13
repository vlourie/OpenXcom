"""For REINFORCE unit-turns: did a real line to the assigned contact exist at any decision (AICAND acts of the unit, lof to that unit id), how far, what chance, and did the order's kind predict it. Read only.
Diagnosis only: acts list what the unit's own AI weighs, it is not used by any gate."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
T = defaultdict(Counter)
W = defaultdict(Counter)
TRANS = Counter()
MEL = []
for run in sys.argv[1:]:
    orders, acts, dec = {}, {}, defaultdict(list)
    pending = None
    for s in read(run):
        if s.startswith("[HIVECC]"):
            k = kv(s)
            if k["event"] == "ORDER" and k["role"] == "REINFORCE":
                orders[(int(k["turn"]), int(k["unit"]))] = k
        elif s.startswith("[AICAND] acts"):
            i = s.find("list=")
            try:
                pending = (int(s.split("unit=")[1].split()[0]), json.loads(s[i + 5:]))
            except ValueError:
                pending = None
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] != "1":
                continue
            t, u = int(k["turn"]), int(k["unit"])
            dec[(t, u)].append(k)
            if pending and pending[0] == u:
                acts.setdefault((t, u), []).append((k, pending[1]))
            pending = None
    for (t, u), o in orders.items():
        c = int(o["contact"])
        kind = o["kind"]
        row = T[kind]
        row["n"] += 1
        best_p, line, seen_in_list, dmin = 0, 0, 0, 999
        anyline = 0
        for k, L in acts.get((t, u), []):
            for a in L:
                if a.get("k") != "a":
                    continue
                if a.get("lof"):
                    anyline += 1
                if a.get("u") == c:
                    seen_in_list = 1
                    dmin = min(dmin, a.get("d", 999))
                    if a.get("lof"):
                        line = 1
                        best_p = max(best_p, a.get("p", 0))
        attacked = any(int(d["act"]) in ATT and d["aim"] == str(c) for d in dec[(t, u)])
        anyatt = any(int(d["act"]) in ATT for d in dec[(t, u)])
        row["contact_in_acts"] += seen_in_list
        row["line_to_contact"] += line
        row["attacked_contact"] += attacked
        row["line_any_target"] += anyline > 0
        row["attacked_any"] += anyatt
        row["line_no_attack"] += line and not attacked
        w = o.get("kind")
        nxt = orders.get((t + 1, u))
        TRANS[(kind, nxt["kind"] if nxt else "off")] += 1
        if line:
            W[kind][("p<25" if best_p < 25 else "p25-49" if best_p < 50 else "p50+")] += 1
keys = ["n", "contact_in_acts", "line_to_contact", "attacked_contact", "line_no_attack", "line_any_target", "attacked_any"]
print("kind\t" + "\t".join(keys))
for kk in sorted(T):
    print(kk + "\t" + "\t".join(str(T[kk][x]) for x in keys))
print("chance of the best shot on the contact where a line existed:", {k: dict(v) for k, v in W.items()})
print("kind at t -> kind at t+1:")
for k, v in sorted(TRANS.items()):
    print(" ", k, v)
