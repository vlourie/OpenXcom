"""HIVE COMMAND gate: what do the enemy's patrol moves buy in D0 (read only). Per turn of a log: units acting on patrol, patrol decisions, how many of them keep the same target as the unit's previous patrol decision (a walk cut short), how many aim at a tile the unit already stood on this turn (a real return), the path actually walked between decisions against the straight displacement, and the TU left (% of max) at the start of the player's next turn - what reaction fire has to spend. Usage: patrol_waste.py <log.gz> [<log.gz> ...]"""
import gzip
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")


def xyz(s):
    return tuple(int(v) for v in s.strip("()").split(","))


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) + abs(a[2] - b[2]) * 2


for log in sys.argv[1:]:
    stat = defaultdict(lambda: defaultdict(int))
    seq = defaultdict(list)
    fired = set()
    units = set()
    known = defaultdict(int)
    tu = defaultdict(list)
    for line in gzip.open(log, "rt", encoding="utf-8", errors="replace"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 3:
            continue
        m = p[2]
        if m.startswith("[AISTATE] aistart ") or m.startswith("[AISTATE] pstart "):
            k = dict(kv.findall(m))
            if k.get("faction") != "1" or k.get("status") in ("6", "7"):
                continue
            t = int(k["turn"])
            if m.startswith("[AISTATE] pstart "):
                tu[t].append(int(k["tu"]) * 100 // max(1, int(k.get("tumax", 1))))
                continue
            stat[t]["alive"] += 1
            units.add(k["unit"])
            stat[t]["sees"] += k.get("sees", "-") != "-"
            known[t] = max(known[t], int(k.get("known", 0)))
        elif m.startswith("[AIDECIDE]"):
            k = dict(kv.findall(m))
            if k.get("side") != "1":
                continue
            t = int(k["turn"])
            u = k["unit"]
            if k["act"] in ("6", "7", "8", "9", "10", "11", "12"):
                fired.add(u)
                stat[t]["shots"] += 1
            if k["mode"] == "0" and k["act"] == "2":
                stat[t]["patrol"] += 1
                seq[(t, u)].append((xyz(k["from"]), xyz(k["to"])))
            elif k["mode"] == "2" and k["act"] == "2":
                stat[t]["combatwalk"] += 1
    for (t, u), s in seq.items():
        stat[t]["punits"] += 1
        stood = set()
        walked = 0
        prev = None
        for i, (a, b) in enumerate(s):
            stood.add(a)
            stat[t]["same"] += prev == b
            stat[t]["back"] += b in stood and prev != b
            prev = b
            walked += dist(a, s[i + 1][0]) if i + 1 < len(s) else 0
        stat[t]["walked"] += walked
        stat[t]["net"] += dist(s[0][0], s[-1][0])
    print(log.replace("\\", "/").split("/")[-2], "units", len(units), "never fired", len(units - fired))
    print(" turn alive sees known | pUnits pDecisions sameTarget back walked net | combatwalk shots | TU% at player's next turn")
    for t in sorted(stat)[:8]:
        st = stat[t]
        v = tu.get(t + 1, tu.get(t, []))
        print(f' {t:3d} {st["alive"]:4d} {st["sees"]:4d} {known[t]:4d} | {st["punits"]:4d} {st["patrol"]:4d} {st["same"]:4d} {st["back"]:4d} {st["walked"]:4d} {st["net"]:4d} | {st["combatwalk"]:4d} {st["shots"]:4d} | {sum(v) // max(1, len(v))}')
