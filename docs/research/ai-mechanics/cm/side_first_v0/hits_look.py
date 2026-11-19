"""SIDE-FIRST COMBAT: every hostile attack that did damage: turn, weapon, aim, damage, friendly damage; the attacks per target and weapon with damage per hit. args: zip label"""
import json
import re
import sys
from collections import defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0])
from battle_stats import KV, lines

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
pend = None
tab = defaultdict(lambda: [0, 0, 0, 0])
for s in lines(sys.argv[1], sys.argv[2]):
    if s.startswith("[AIDECIDE] "):
        d = dict(KV.findall(s.split(" hu=")[0]))
        pend = d
    elif s.startswith("[AIEXEC] ") and pend:
        x = json.loads(s[9:])
        d, pend = pend, None
        if d.get("side") != "1" or int(d.get("act", 0)) not in (7, 8, 9) or not x.get("spent"):
            continue
        k = (d.get("aim"), d.get("weapon"))
        t = tab[k]
        t[0] += 1
        dm = x.get("dmg") or 0
        t[1] += 1 if dm else 0
        t[2] += dm
        t[3] += x.get("fdmg") or 0
print("aim, weapon: shots, with damage, damage, friendly; damage per hit")
for k, t in sorted(tab.items(), key=lambda kv_: (str(kv_[0][0]), str(kv_[0][1]))):
    print(" ", k, t, round(t[2] / t[1], 1) if t[1] else "-")
