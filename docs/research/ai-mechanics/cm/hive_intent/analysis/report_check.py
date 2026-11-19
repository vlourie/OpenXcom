"""HIVE COMBAT INTENT V0: recounts from the journals the numbers the report states. Read only."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
RUNS = ["ci5_IA_M6_s1", "ci6_IA_M6_s2", "ci7_IV_M3_s1"]
T = Counter()
for r in RUNS:
    L = read(r)
    ev = Counter()
    c = Counter()
    for s in L:
        if not s.startswith("[HIVEINTENT]"):
            continue
        k = kv(s)
        e = k["event"]
        ev[e] += 1
        if e == "ISSUE":
            T["issue_" + k["type"]] += 1
        elif e == "CLOSE":
            T["close_" + k["status"]] += 1
        elif e == "CHOICE":
            T["choice"] += 1
            T["no_" + (k["no"] if k["no"] != "-" else ("takes" if k["changed"] == "1" else "would"))] += 1
        elif e == "RESULT":
            T["res_" + k["kind"]] += 1
            if k["changed"] == "1":
                T["changed"] += 1
                T["changed_" + k["kind"]] += 1
        elif e == "DECIDED":
            T["own_" + k.get("own", "-")] += 1
        elif e in ("SKIP", "BACK"):
            T[e] += 1
            c[e] += 1
    print(r, {x: ev[x] for x in ("ISSUE", "CHOICE", "RESULT", "CLOSE", "SKIP", "BACK", "PRIORITY")}, dict(c))
    # TU and aim against the facts
    last = None
    for s in L:
        if s.startswith("[AIEXEC]"):
            try:
                last = json.loads(s[9:])
            except ValueError:
                pass
        elif s.startswith("[HIVEINTENT] event=RESULT") and last:
            k = kv(s)
            if int(k["act"]) in ATT and str(last["unit"]) == k["unit"]:
                T["atk_checked"] += 1
                if str(last["spent"]) == k["tu_spent"]:
                    T["tu_same"] += 1
                else:
                    T["tu_differ_act" + k["act"]] += 1
                if last.get("dmg", 0) > int(k["hp_lost"]):
                    T["exec_more"] += 1
for k in sorted(T):
    print(f"  {k:32s} {T[k]}")
print("  refusals", sum(v for k, v in T.items() if k.startswith("no_") and k not in ("no_same", "no_takes", "no_would")))
print("-- attacks of ra1 by damage, and on 470")
L = read("ra1_AN_M6_s1")
rec = {}
last = None
for s in L:
    if s.startswith("[AIDECIDE]"):
        last = kv(s)
    elif s.startswith("[AIREC]") and last is not None:
        try:
            rec[json.loads(s[8:])["rec"]] = last
        except ValueError:
            pass
        last = None
a = h = a470 = h470 = 0
for s in L:
    if s.startswith("[AIEXEC]"):
        try:
            j = json.loads(s[9:])
        except ValueError:
            continue
        d = rec.get(j["rec"])
        if d and d["side"] == "1" and int(d["act"]) in ATT:
            a += 1
            h += j.get("dmg", 0) > 0
            if d["aim"] == "470":
                a470 += 1
                h470 += j.get("dmg", 0) > 0
print("  ra1 attacks", a, "with damage", h, "on 470", a470, "with damage", h470)
