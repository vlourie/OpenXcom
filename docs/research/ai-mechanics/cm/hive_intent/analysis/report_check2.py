"""HIVE COMBAT INTENT V0: the episode details the report states, one by one, from the journals. Read only."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
RUNS = ["ci5_IA_M6_s1", "ci6_IA_M6_s2", "ci7_IV_M3_s1"]

print("== changed attacks, all runs: RESULT and the AIEXEC right before it")
for r in RUNS:
    L = read(r)
    last = None
    for s in L:
        if s.startswith("[AIEXEC]"):
            try:
                last = json.loads(s[9:])
            except ValueError:
                pass
        elif s.startswith("[HIVEINTENT] event=RESULT"):
            k = kv(s)
            if k["changed"] == "1" and k["kind"] == "ATTACKED_CONTACT":
                print(r, "turn", k["turn"], "unit", k["unit"], "squad", k.get("squad"), "contact", k["contact"], "aim", k["aim"], "act", k["act"], "hit", k["hit"], "down", k["down"], "hp", k["hp_lost"], "tu", k["tu_spent"], "| exec dmg", last and last.get("dmg"), "stunned", last and last.get("stunned"), "downed", last and last.get("downed"))

print("== M6 s1 turn 1: attacks on the contact's tile and what happened to 503, 520, 543")
L = read("ci5_IA_M6_s1")
last = None
for s in L:
    if s.startswith("[AIEXEC]"):
        try:
            last = json.loads(s[9:])
        except ValueError:
            pass
    elif s.startswith("[HIVEINTENT] event=RESULT"):
        k = kv(s)
        if k["turn"] == "1" and k["contact"] == "503" and int(k["act"]) in ATT:
            print("  ", k["unit"], "changed", k["changed"], "kind", k["kind"], "aim", k["aim"], "act", k["act"], "hit", k["hit"], "hp", k["hp_lost"], "exec", last and last.get("dmg"), last and last.get("downed"))
    elif s.startswith("[AICASUALTY]"):
        k = kv(s)
        if k.get("victim") in ("503", "520", "543") and int(k.get("turn", "99")) <= 3:
            print("   casualty turn", k.get("turn"), k.get("victim"), k.get("how"), "by", k.get("killer"), k.get("weapon"), k.get("pos"))
for r in ("ra1_AN_M6_s1",):
    for s in read(r):
        if s.startswith("[AICASUALTY]"):
            k = kv(s)
            if k.get("victim") == "503" and int(k.get("turn", "99")) <= 3:
                print("   ra1 casualty turn", k.get("turn"), k.get("victim"), k.get("how"), "by", k.get("killer"), k.get("weapon"))
print("   squads of the units:", {u: next((kv(s).get("squad") for s in L if s.startswith("[HIVEINTENT] event=RESULT") and kv(s)["unit"] == u), None) for u in ("1000001", "1000006", "1000014", "1000024", "1000025", "1000027")})

print("== refusals not_valid_target: by run and contact, turn")
for r in RUNS:
    c = Counter()
    for s in read(r):
        if s.startswith("[HIVEINTENT] event=CHOICE"):
            k = kv(s)
            if k["no"] == "not_valid_target":
                c[(k["turn"], k["contact"])] += 1
    print(" ", r, sum(c.values()), sorted(c.items(), key=lambda x: -x[1])[:6])
c = Counter()
for s in read("ci5_IA_M6_s1"):
    if s.startswith("[HIVEINTENT] event=CHOICE"):
        k = kv(s)
        if k["turn"] == "1" and k["contact"] == "503":
            c[k["no"]] += 1
print("  M6 s1 turn 1 contact 503 answers:", dict(c))

print("== decisions against RESULT lines on each run, AI side")
for r in RUNS:
    L = read(r)
    d = sum(1 for s in L if s.startswith("[AIDECIDE]") and kv(s)["side"] == "1")
    rs = [kv(s) for s in L if s.startswith("[HIVEINTENT] event=RESULT")]
    print(" ", r, "decisions", d, "RESULT", len(rs), "by turn gap", sorted((t, n) for t, n in Counter(kv(s)["turn"] for s in L if s.startswith("[AIDECIDE]") and kv(s)["side"] == "1").items() if n != sum(1 for x in rs if x["turn"] == t)))

print("== HIVESAVECHECK")
for r in RUNS:
    L = [kv(s) for s in read(r) if s.startswith("[HIVESAVECHECK]")]
    print(" ", r, len(L), Counter(x.get("same") for x in L), [x.get("turn") for x in L][:10])

print("== run 4: 1000035 on turn 2")
try:
    n = 0
    for s in read("ci4_IA_M6_s1"):
        if s.startswith("[HIVEINTENT] event=RESULT"):
            k = kv(s)
            if k["unit"] == "1000035" and k["turn"] == "2":
                n += 1
                print("  ", k["act"], k["kind"], "changed", k["changed"], "tu", k.get("tu"), "spent", k["tu_spent"], k.get("to"))
    print("   lines", n)
except Exception as e:  # the run may be stored under another name
    print("   not read:", e)
