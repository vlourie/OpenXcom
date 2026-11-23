"""HIVE COMMAND gate: D0 logs (read only): the state at turn 12 and the end of the turn: patrol targets used, TU left by those on patrol, the player's state by turn 12 for the measure. Usage: targets.py <log.gz> [...]"""
import gzip
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
LIMIT = 12
for log in sys.argv[1:]:
    tgt = set()
    tu_after = defaultdict(list)
    pdown = hdown = 0
    php = {}
    hhp = {}
    lastdec = {}
    for line in gzip.open(log, "rt", encoding="utf-8", errors="replace"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 3:
            continue
        m = p[2]
        if m.startswith("[AIDECIDE]"):
            k = dict(kv.findall(m))
            if k.get("side") == "1" and k["mode"] == "0" and k["act"] == "2":
                tgt.add(k["to"])
        elif m.startswith("[AISTATE] end "):
            k = dict(kv.findall(m))
            t = int(k["turn"])
            if t <= 6 and k.get("faction") == "1" and k.get("status") not in ("6", "7"):
                tu_after[t].append(int(k["tu"]) * 100 // max(1, int(k.get("tumax", 1))))
        elif m.startswith("[AISTATE] aistart "):
            k = dict(kv.findall(m))
            t = int(k["turn"])
            if t <= LIMIT:
                if k.get("faction") == "0":
                    php[k["unit"]] = int(k["hp"].split("/")[0])
                else:
                    hhp[k["unit"]] = (t, int(k["hp"].split("/")[0]), k.get("status"))
        elif m.startswith("[AICASUALTY]"):
            k = dict(kv.findall(m))
            if int(k["turn"]) <= LIMIT:
                if k.get("vfaction") == "0":
                    pdown += 1
                elif k.get("vfaction") == "1":
                    hdown += 1
    print(log.split("/")[-2], "distinct patrol targets", len(tgt), "| falls by t12: player", pdown, "hostile", hdown, "| live hostile at last aistart<=12:", sum(1 for v in hhp.values() if v[0] == max(x[0] for x in hhp.values())), "| player hp sum (last seen)", sum(php.values()))
    print("   TU% left at side end, mean by turn:", {t: sum(v) // max(1, len(v)) for t, v in sorted(tu_after.items())})
