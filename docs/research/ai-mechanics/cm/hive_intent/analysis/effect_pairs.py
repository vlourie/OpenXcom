"""HIVE COMBAT INTENT V0: the pairs where the estimate said no_effect and the same soldier really hurt that contact: all CHOICE lines of the pair next to the real attacks, by turn. Read only.
Usage: effect_pairs.py <run> <unit> <contact> [<unit> <contact>...]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
lines = read(sys.argv[1])
args = sys.argv[2:]
pairs = {(args[i], args[i + 1]) for i in range(0, len(args), 2)}
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
turn = 0
for s in lines:
    if s.startswith("[AIDECIDE]"):
        turn = kv(s)["turn"]
    if s.startswith("[HIVEINTENT] event=CHOICE"):
        k = kv(s)
        if (k["unit"], k["contact"]) in pairs and k["no"] in ("no_effect", "weak_effect"):
            print("choice", {a: k.get(a) for a in ("turn", "unit", "contact", "site", "no", "tu", "own")}, s[-90:])
    if s.startswith("[AIEXEC]"):
        try:
            j = json.loads(s[9:])
        except ValueError:
            continue
        d = rec.get(j.get("rec"))
        if d and (d["unit"], d["aim"]) in pairs:
            print("REAL  ", d["turn"], d["unit"], d["aim"], "act", d["act"], "weapon", d.get("weapon"), "tu", d.get("tu"), "dmg", j.get("dmg"), {a: j.get(a) for a in ("hit", "dist", "hp", "armor", "killed", "stun")})
