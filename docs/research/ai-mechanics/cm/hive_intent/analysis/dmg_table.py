"""HIVE COMBAT INTENT V0: did the attacks really hurt? For each aim and weapon of the AI side: attacks, attacks with damage, total damage from [AIEXEC]. Then, for a shadow run, each refusal no_effect/weak_effect against what this weapon really did to that contact in the same battle. Read only.
Usage: dmg_table.py <run>"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
lines = read(sys.argv[1])
last = None
rec = {}
weapon_of = {}
for s in lines:
    if s.startswith("[AIDECIDE]"):
        k = kv(s)
        last = k
        if k["side"] == "1":
            weapon_of[k["unit"]] = k.get("weapon")
    elif s.startswith("[AIREC]") and last is not None:
        try:
            j = json.loads(s[8:])
        except ValueError:
            continue
        if last["side"] == "1" and int(last["act"]) in ATT:
            rec[j.get("rec")] = last
        last = None
tab = defaultdict(lambda: [0, 0, 0])
by_aim = defaultdict(lambda: [0, 0, 0])
for s in lines:
    if s.startswith("[AIEXEC]"):
        try:
            j = json.loads(s[9:])
        except ValueError:
            continue
        d = rec.get(j.get("rec"))
        if not d:
            continue
        key = (d["aim"], d.get("weapon"))
        for t in (tab[key], by_aim[d["aim"]]):
            t[0] += 1
            t[1] += 1 if j.get("dmg", 0) > 0 else 0
            t[2] += j.get("dmg", 0)
print("aim: attacks, with damage, total")
for a, v in sorted(by_aim.items(), key=lambda e: -e[1][0]):
    print(" ", a, v)
print("aim, weapon: attacks, with damage, total")
for a, v in sorted(tab.items(), key=lambda e: (e[0][0], -e[1][0])):
    print(" ", a, v)
print("refusals of the effect check against what the same weapon really did to that contact")
ref = defaultdict(int)
for s in lines:
    if s.startswith("[HIVEINTENT] event=CHOICE") and (" no=no_effect" in s or " no=weak_effect" in s):
        k = kv(s)
        ref[(k["contact"], weapon_of.get(k["unit"]), k["no"])] += 1
for key, n in sorted(ref.items(), key=lambda e: -e[1]):
    print(" ", key, n, "real", tab.get((key[0], key[1])))
