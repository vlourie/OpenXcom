"""RESTORE COMBAT AUTONOMY: what remained open after the gates. A fire position left on a free choice; the unit-turn with the most empty walks; start TU above D0's against the unit's own state lines. Read only."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
RUNS = ["ra1_AN_M6_s1", "ra2_AN_M6_s2", "ra3_AV_M3_s1"]
ATT = set(range(4, 21))


def stream(run):
    answer = {}
    out = []
    recs = {}
    last = None
    for s in read(run):
        if s.startswith("[HIVECC] event=AUTONOMY"):
            k = kv(s)
            answer[k["unit"]] = k
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            last = None
            if k["side"] == "1" and int(k["turn"]) <= 8:
                last = dict(k, ans=answer.pop(k["unit"], None), exec=None, rec=None)
                out.append(last)
        elif s.startswith("[AIREC]") and last is not None and last["rec"] is None:
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            last["rec"] = j
            recs[j["rec"]] = last
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            if j["rec"] in recs:
                recs[j["rec"]]["exec"] = j
    return out


for run in RUNS:
    D = stream(run)
    W = Counter()
    by = defaultdict(list)
    for d in D:
        by[(d["turn"], d["unit"])].append(d)
        a = d["ans"]
        if a and a["answer"] == "FREE":
            why = a["why"]
            spent = (d["exec"] or {}).get("spent", 0)
            W[why + ":decisions"] += 1
            if d["act"] == "2" and d["mode"] == "0" and spent > 0:
                W[why + ":patrol_step"] += 1
            if int(d["act"]) in ATT:
                W[why + ":attack"] += 1
    print(run)
    print("  free answers by order why", dict(sorted(W.items())))
    # a fire position left: the free step from a contact_in_place order; was there an attack by this unit later that turn or in the next
    left = 0
    shot_later = 0
    for (t, u), ds in by.items():
        step = [i for i, d in enumerate(ds) if d["ans"] and d["ans"]["why"] == "contact_in_place" and d["act"] == "2" and d["mode"] == "0" and (d["exec"] or {}).get("spent", 0) > 0]
        if step:
            left += 1
            shot_later += any(int(d["act"]) in ATT for d in ds[step[0] + 1:]) or any(int(d["act"]) in ATT for d in by.get((str(int(t) + 1), u), []))
    print("  contact_in_place left on a free step: unit-turns", left, "attacked after it", shot_later)
    key, ds = max(by.items(), key=lambda x: sum(1 for d in x[1] if d["act"] == "2" and (d["exec"] or {}).get("spent", 1) == 0))
    n = sum(1 for d in ds if d["act"] == "2" and (d["exec"] or {}).get("spent", 1) == 0)
    print("  most empty walks in one unit-turn", key, n, "tu", [d["tu"] for d in ds][:14], "ans", Counter((d["ans"] or {}).get("answer", "") for d in ds), "trail", ((ds[-1]["exec"] or {}).get("trail") or [""])[0][:90])


# start TU above D0's in M3
def starts(run):
    s = {}
    for d in stream(run):
        s.setdefault(d["unit"], []).append(int(d["tu"]))
    return {u: max(v) for u, v in s.items()}


a, b, c = starts("scpa_D_M3_s1"), starts("cc6_CV_M3_s1"), starts("ra3_AV_M3_s1")
print("M3: units above D0's highest TU: CC", {u: (a.get(u), v) for u, v in b.items() if u in a and v > a[u]}, "RA", {u: (a.get(u), v) for u, v in c.items() if u in a and v > a[u]})
for s in read("ra3_AV_M3_s1"):
    if s.startswith("[AISTATE]"):
        print("AISTATE sample", s[:260])
        break
