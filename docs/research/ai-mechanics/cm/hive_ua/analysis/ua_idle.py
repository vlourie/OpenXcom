"""UNIFIED ARMY CONTROL V0, read only: why M6 without headquarters has soldiers standing in escape with time units while the same soldiers walk with it; whether RESULT's lost time units are panic. Usage: ua_idle.py"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
OFF, ON = "ua4_UO_M6_s1", "ua1_UN_M6_s1"


def decs(run):
    d = defaultdict(list)
    for s in read(run):
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1":
                d[(int(k["turn"]), k["unit"])].append(k)
    return d


a, b = decs(OFF), decs(ON)
stand = [(t, u) for (t, u), ds in a.items() if any(x["mode"] == "3" and x["act"] == "0" for x in ds)]
print("OFF unit-turns with escape and act 0:", len(stand), "by turn", sorted(Counter(t for t, u in stand).items()))
print("OFF first three of them, with the record's source and reason:")
L = read(OFF)
shown = 0
for i, s in enumerate(L):
    if s.startswith("[AIDECIDE]") and " mode=3 " in s and " act=0 " in s and " side=1 " in s:
        k = kv(s)
        for t in L[i + 1:i + 4]:
            if t.startswith("[AIREC]"):
                j = json.loads(t[8:])
                base = j.get("base") or {}
                print(" ", k["turn"], k["unit"], "from", k["from"], "tu", k["tu"], "src", base.get("src"), "reason", json.dumps(base.get("reason"))[:420])
                break
        shown += 1
        if shown == 3:
            break
ch = defaultdict(list)
for s in read(ON):
    if s.startswith("[HIVEUA] event=CHOICE"):
        k = kv(s)
        ch[(int(k["turn"]), k["unit"])].append(k)
print("same soldiers in ON on the same turn:")
for key in sorted(stand)[:10]:
    ds = b.get(key)
    c = ch.get(key, [])
    print(" ", key, "ON", [(x["mode"], x["act"], x["from"], x["to"]) for x in ds[:2]] if ds else "no decisions", "choice", [(x["kind"], x["free"], x["chosen"], x["fallback"]) for x in c[:2]])
print("units in the OFF list", Counter(u for t, u in stand).most_common(8))
free_none = [k for v in ch.values() for k in v if "-1" in k["free"]]
print("ON choices with no free node", len(free_none))
print("first ON decisions of those units on turn 1", {u: [(x["mode"], x["act"], x["from"], x["to"]) for x in b.get((1, u), [])[:1]] for t, u in stand[:3]})
print("OFF same", {u: [(x["mode"], x["act"], x["from"], x["to"]) for x in a.get((1, u), [])[:1]] for t, u in stand[:3]})
for run in (ON, "ua3_UN_M8_s1"):
    L = read(run)
    pan = [s for s in L if s.startswith("[AIPANIC]")]
    print(run, "panic lines", len(pan), pan[:1])
    res = [kv(s) for s in L if s.startswith("[HIVEUA] event=RESULT") and " tu=0 " in s and " moved=0 " in s]
    d = decs(run)
    lost = [k for k in res if (int(k["turn"]), k["unit"]) not in d]
    print(" RESULT tu 0, not moved, no decision at all:", len(lost), [(k["turn"], k["unit"]) for k in lost[:6]])
    print(" panic on side 1:", sum(" side=1 " in s for s in pan), "state lines for a lost one:", [s[:240] for s in L if s.startswith("[AISTATE]") and lost and "unit=" + lost[0]["unit"] + " " in s and "turn=" + lost[0]["turn"] + " " in s][:2])
    tu0 = [kv(s) for s in L if s.startswith("[HIVEUA] event=RESULT") and " tu=0 " in s and " moved=0 " in s]
    print(" of RESULT tu 0 not moved, statuses at the turn's end:", Counter(next((kv(x).get("status") for x in L if x.startswith("[AISTATE]") and "unit=" + k["unit"] + " " in x and "turn=" + str(int(k["turn"]) + 1) + " " in x), "?") for k in tu0[:20]))
L = read(OFF)
for u in ("1000021", "1000039"):
    print("OFF", u, [kv(s).get("type") for s in L if s.startswith("[AISTATE]") and "unit=" + u + " " in s][:1], [(kv(s)["turn"], kv(s)["mode"], kv(s)["act"], kv(s)["tu"], kv(s)["from"]) for s in L if s.startswith("[AIDECIDE]") and "unit=" + u + " " in s][:4])
