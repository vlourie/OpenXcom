"""MISSION_DIRECTOR_V0: the decisions whose execution spent more than the TU at the decision (what are they, are they the group's), the unpaid patrol shots
(whose, and did the unit do something else after), the sums of two runs cut at one turn.

  py -3.13 -I fl_m6.py <battle dir> [<cut turn>]"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
cut = int(sys.argv[2]) if len(sys.argv) > 2 else 999
tasks = set()
dec = None
sum_ = Counter()
unpaid = Counter()
for raw in gzip.open(Path(sys.argv[1]) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
    s = raw.rstrip("\n").split("\t", 2)[-1]
    if s.startswith("[AIMISSION] what=task"):
        d = dict(KV.findall(s))
        tasks.add((d["turn"], d["unit"]))
    elif s.startswith("[AIDECIDE] "):
        dec = dict(KV.findall(s.split(" hu=")[0]))
        if dec["side"] != "1":
            dec = None
    elif s.startswith("[AIEXEC] ") and dec:
        x = json.loads(s[9:])
        if str(x["unit"]) != dec["unit"]:
            continue
        sp = x.get("spent") or 0
        a, m, t = int(dec["act"]), int(dec["mode"]), int(dec["turn"])
        order = (dec["turn"], dec["unit"]) in tasks
        if sp > int(dec["tu"]):
            print(f"over: t{t} {dec['unit']} n{dec['n']} tu{dec['tu']} spent{sp} mode{m} act{a} order {order} keys", {k: x[k] for k in x if k in ("tu_start", "tu_end", "steps", "moved", "shots")})
        if a in (7, 8, 9) and m == 0 and sp == 0:
            unpaid["order" if order else "protocol"] += 1
        if t <= cut:
            sum_["decisions"] += 1
            sum_["spent"] += sp
            sum_["dmg"] += x.get("dmg") or 0
            sum_["downed"] += x.get("downed") or 0
            sum_["hp_lost"] += x.get("hp_lost") or 0
            if a in (6, 7, 8, 9) and m != 0:
                sum_["attack_decisions"] += 1
            if a in (7, 8, 9) and m == 0:
                sum_["patrol_shots"] += 1
            if a == 2:
                sum_["walks"] += 1
        dec = None
print("unpaid patrol shots:", dict(unpaid))
print(f"to turn {cut}:", dict(sum_))
