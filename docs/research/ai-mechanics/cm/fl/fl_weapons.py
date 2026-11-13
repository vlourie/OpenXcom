"""TACTICAL FLANKING stage 1: what the hostile weapons did in whole battles (D0 logs) - is a weapon able to hurt a target?

Per hostile weapon and action type, split by the aimed player unit's kind (a tank/HWP - main weapon AUX_* - or infantry):
executed attacks, attacks with damage, damage; and the same for the player's reaction... no - only hostile attacks.
The aimed unit's kind is taken from its [AISTATE] weapon.

  py -3.13 -I fl_weapons.py <log.gz> [<log.gz> ...]"""
import gzip
import json
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6: "throw", 7: "auto", 8: "snap", 9: "aimed", 10: "melee", 12: "launch"}
tab = defaultdict(lambda: [0, 0, 0])
for f in sys.argv[1:]:
    kind, pend = {}, None
    for raw in gzip.open(f, "rt", encoding="utf-8", errors="replace"):
        body = raw.rstrip("\n").split("\t", 2)[-1]
        if body.startswith("[AISTATE] ") and " faction=0 " in body:
            d = dict(KV.findall(body))
            kind.setdefault(d["unit"], "tank" if d["weapon"].startswith("AUX_") else "infantry")
        elif body.startswith("[AIDECIDE] "):
            d = dict(KV.findall(body.split(" hu=")[0]))
            pend = d if d["side"] == "1" and int(d["act"]) in ATT else None
        elif body.startswith("[AIEXEC] ") and pend:
            x = json.loads(body[9:])
            if str(x["unit"]) == pend["unit"] and (x.get("spent") or 0) > 0 and not x.get("walk"):
                k = (pend["weapon"], ATT[int(pend["act"])], kind.get(pend["aim"], "other"))
                t = tab[k]
                t[0] += 1
                t[1] += (x.get("dmg") or 0) > 0
                t[2] += x.get("dmg") or 0
            pend = None
print(f"{'weapon':<28} {'act':<6} {'target':<9} {'att':>5} {'hit':>4} {'dmg':>6} {'dmg/att':>7}")
for k, (a, h, d) in sorted(tab.items(), key=lambda kv: -kv[1][0]):
    print(f"{k[0][:28]:<28} {k[1]:<6} {k[2]:<9} {a:5d} {h:4d} {d:6d} {d / a:7.1f}")
