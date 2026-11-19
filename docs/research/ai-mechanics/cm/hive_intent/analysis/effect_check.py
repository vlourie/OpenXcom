"""HIVE COMBAT INTENT V0: is the effect estimate right to say zero? For each pair soldier+contact the estimate refused as no_effect in a shadow run: what the same soldier really did to that contact in that battle ([AIEXEC] dmg, attacks). Also what the soldiers' real attacks did in all, by weapon. Read only.
Usage: effect_check.py <run>"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
lines = read(sys.argv[1])
last = None
rec = {}
for s in lines:
    if s.startswith("[AIDECIDE]"):
        last = kv(s)
    elif s.startswith("[AIREC]") and last is not None:
        try:
            j = json.loads(s[8:])
        except ValueError:
            continue
        if last["side"] == "1" and int(last["act"]) in ATT:
            rec[j.get("rec")] = last
        last = None
real = defaultdict(lambda: [0, 0, 0])
weapon = {}
for s in lines:
    if s.startswith("[AIEXEC]"):
        try:
            j = json.loads(s[9:])
        except ValueError:
            continue
        d = rec.get(j.get("rec"))
        if d:
            weapon[d["unit"]] = d.get("weapon")
            for key in ((d["unit"], d["aim"]),):
                real[key][0] += 1
                real[key][1] += 1 if j.get("dmg", 0) > 0 else 0
                real[key][2] += j.get("dmg", 0)
ref = Counter()
for s in lines:
    if s.startswith("[HIVEINTENT] event=CHOICE") and " no=no_effect" in s:
        k = kv(s)
        ref[(k["unit"], k["contact"])] += 1
tot = hurt = attacked = 0
for (u, c), n in sorted(ref.items(), key=lambda e: -e[1]):
    r = real.get((u, c))
    tot += 1
    attacked += bool(r)
    hurt += bool(r and r[1])
    print(u, c, weapon.get(u), "refused", n, "real attacks/hits/dmg", r)
print(f"pairs refused no_effect {tot}; the same soldier really attacked that contact in {attacked}; with damage in {hurt}")
a = sum(v[0] for v in real.values())
h = sum(v[1] for v in real.values())
print("all real attacks", a, "with damage", h)
