"""TACTICAL AI 2.0 scale check (logs only): hostile attacking unit-turns in a battle set and how many of them did damage
to a player unit (the aim of the attack is a player unit at that turn's aistart, the action's dmg > 0). Same reading
of [AIDECIDE] + [AIEXEC] as fl_focus2.py, so the numbers are comparable with it.

  py -3.13 -I fl_useful.py <out dir> <prefix>"""
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
att_ut = useful_ut = att_pl = 0
nb = 0
for d in sorted(Path(sys.argv[1]).glob(f"{sys.argv[2]}_*")):
    nb += 1
    snap = defaultdict(dict)
    pend = None
    per = defaultdict(lambda: [0, 0, 0])
    for raw in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        body = raw.rstrip("\n").split("\t", 2)[-1]
        if body.startswith("[AISTATE] aistart "):
            s = dict(KV.findall(body))
            snap[int(s["turn"])][s["unit"]] = s
        elif body.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(body.split(" hu=")[0]))
        elif body.startswith("[AIEXEC] ") and pend:
            x = json.loads(body[9:])
            if str(x["unit"]) == pend["unit"] and pend["side"] == "1":
                if int(pend["act"]) in ATT and (x.get("spent") or 0) > 0 and not x.get("walk"):
                    t = int(pend["turn"])
                    k = (t, pend["unit"])
                    per[k][0] = 1
                    tv = snap.get(t, {}).get(pend["aim"])
                    if tv and tv["faction"] == "0":
                        per[k][1] = 1
                        if (x.get("dmg") or 0) > 0:
                            per[k][2] = 1
            pend = None
    for a, p, u in per.values():
        att_ut += a
        att_pl += p
        useful_ut += u
print(f"battles {nb}; attacking unit-turns {att_ut}; of them aimed at a player unit {att_pl}; "
      f"damaging a player unit {useful_ut}")
