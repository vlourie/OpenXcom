"""HIVE COMBAT INTENT V0: the first point of each active battle, the episode by the journal, the budget of the difference of TU and the reasons of not_valid_target. Read only."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
PAIRS = [("ci5_IA_M6_s1", "ra1_AN_M6_s1"), ("ci6_IA_M6_s2", "ra2_AN_M6_s2"), ("ci7_IV_M3_s1", "ra3_AV_M3_s1")]
F = ("turn", "side", "unit", "n", "from", "tu", "mode", "act", "to", "aim", "hr", "hu", "ho", "hi")


def decs(L):
    return [(i, kv(s)) for i, s in enumerate(L) if s.startswith("[AIDECIDE]")]


for a, b in PAIRS:
    A, B = read(a), read(b)
    da, db = decs(A), decs(B)
    print("=====", a, b, "decisions", len(da), len(db))
    first_any = first_act = None
    for n, ((ia, x), (ib, y)) in enumerate(zip(da, db)):
        if first_any is None and any(x.get(f) != y.get(f) for f in F):
            first_any = n
        if any(x.get(f) != y.get(f) for f in ("turn", "unit", "n", "from", "tu", "act", "to", "hr", "hu", "hi", "ho")):
            first_act = n
            print(" first difference of any field at", first_any, "; first in the action or in state at", n)
            print("   base  ", {f: y.get(f) for f in F})
            print("   active", {f: x.get(f) for f in F})
            prev = da[n - 1][0] if n else 0
            for s in A[prev + 1 : ia + 1]:
                if s.startswith(("[HIVEINTENT]", "[HIVECC]", "[AIDECIDE]")):
                    print("     ", s[:175])
            break
    # first CHOICE changed=1
    for s in A:
        if s.startswith("[HIVEINTENT] event=CHOICE") and " changed=1 " in s:
            print(" first changed:", s[:150])
            break
    roles = [s[:140] for s in A if s.startswith("[HIVECC] event=") and "intent_priority" in s][:3]
    print(" role changes for the priority", sum(1 for s in A if "intent_priority" in s), roles)
    # TU differences
    last_exec = None
    d = Counter()
    for s in A:
        if s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
                last_exec = (j["unit"], j["spent"])
            except ValueError:
                pass
        elif s.startswith("[HIVEINTENT] event=RESULT"):
            k = kv(s)
            if int(k["act"]) in ATT and last_exec and str(last_exec[0]) == k["unit"]:
                if str(last_exec[1]) == k["tu_spent"]:
                    d[("same", k["act"])] += 1
                else:
                    d[("differ", k["act"], last_exec[1] - int(k["tu_spent"]))] += 1
    print(" tu against AIEXEC", sorted(d.items(), key=lambda e: str(e[0])))
    # not_valid_target: is the contact's tile dangerous? there is no line; what happened to the contact just before
    nv = Counter()
    for s in A:
        if s.startswith("[HIVEINTENT] event=CHOICE") and " no=not_valid_target" in s:
            k = kv(s)
            nv[(k["turn"], k["contact"])] += 1
    print(" not_valid_target", sorted(nv.items()))
    thrown = defaultdict(list)
    for s in A:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1" and k["act"] == "6":
                thrown[k["turn"]].append((k["unit"], k["to"]))
    print(" grenades by turn", {t: v[:6] for t, v in thrown.items()})
    # the hits of the changed decisions and the kills they gave
    ch = [kv(s) for s in A if s.startswith("[HIVEINTENT] event=RESULT") and " changed=1 " in s and " kind=ATTACKED_CONTACT " in s]
    print(" changed attacks", [(c["turn"], c["unit"], c["contact"], c["act"], c["hit"], c["down"], c["hp_lost"]) for c in ch])
    print(" closes", Counter((kv(s)["status"], kv(s).get("why", "-")) for s in A if s.startswith("[HIVEINTENT] event=CLOSE")).most_common(8))
    print(" SKIP", [s[13:125] for s in A if s.startswith("[HIVEINTENT] event=SKIP")][:6])
    print(" PRIORITY", [(kv(s)["turn"], kv(s)["contact"], kv(s).get("capable"), kv(s).get("was")) for s in A if s.startswith("[HIVEINTENT] event=PRIORITY")][:12])

print("===== the episode: M6 s1, turn 1, contact 503")
for run in ("ci5_IA_M6_s1", "ra1_AN_M6_s1"):
    A = read(run)
    print(run)
    last = None
    place = None
    rec = {}
    for s in A:
        if s.startswith("[AISTATE]"):
            k = kv(s)
            if k.get("unit") == "503" and k["turn"] == "1":
                place = k["pos"]
    for s in A:
        if s.startswith("[AIDECIDE]"):
            last = kv(s)
        elif s.startswith("[AIREC]") and last is not None:
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            rec[j["rec"]] = last
            last = None
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            d = rec.get(j["rec"])
            if d and d["turn"] in ("1", "2") and d["side"] == "1" and int(d["act"]) in ATT and d["to"] == place:
                print("   ", d["turn"], d["unit"], "act", d["act"], "tu", d["tu"], "to", d["to"], "aim", d["aim"], d.get("weapon"), "spent", j["spent"], "dmg", j["dmg"], "down", j["downed"])
        elif s.startswith("[AICASUALTY]") and "victim=503 " in s:
            print("   ", s[:175])
    if run.startswith("ci"):
        for s in A:
            if s.startswith("[HIVEINTENT]") and " turn=1 " in s and (" squad=4 " in s):
                k = kv(s)
                if k["event"] in ("ISSUE", "CLOSE") or (k["event"] == "CHOICE" and k["changed"] == "1" and k["unit"] in ("1000001", "1000006", "1000014", "1000027")):
                    print("    ", s[13:150])
        for s in A:
            if s.startswith("[HIVEINTENT] event=PRIORITY") and " turn=1 " in s:
                print("    ", s[13:175])
