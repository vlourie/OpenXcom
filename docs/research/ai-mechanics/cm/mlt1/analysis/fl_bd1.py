"""MISSION-LEVEL TACTICS: in a base defense battle (D0 logs), what the hostile side does about the base modules. The engine's patrol protocol
(AIModule::setupPatrol) walks small hostile units to target nodes and shoots a base module there: a snap shot decided in patrol mode.

  py -3.13 -I fl_bd1.py <out dir> <battle dir name>..."""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
out = Path(sys.argv[1])
for name in sys.argv[2:]:
    d = out / name
    pend = None
    units = set()
    acts = Counter()
    per_turn = defaultdict(Counter)
    module_shots = []
    events = Counter()
    last_pos = {}
    first_pos = {}
    res = ""
    for raw in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        s = raw.rstrip("\n").split("\t", 2)[-1]
        if s.startswith("[AIRESULT]"):
            res = " ".join(f"{k}={v}" for k, v in KV.findall(s) if k in ("how", "turn", "player", "pdead", "hostile", "hdead", "hattacks", "hmoves", "livesoldiers", "livealiens"))
        elif s.startswith("[AIEVENT]"):
            m = dict(KV.findall(s))
            events[m.get("what", "?")] += 1
        elif s.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(s.split(" hu=")[0]))
            if pend["side"] != "1":
                pend = None
                continue
            u = pend["unit"]
            units.add(u)
            first_pos.setdefault(u, pend["from"])
            last_pos[u] = pend["from"]
            a, mo = int(pend["act"]), int(pend["mode"])
            acts[(mo, a)] += 1
            per_turn[int(pend["turn"])][(mo, a)] += 1
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            if str(x["unit"]) == pend["unit"]:
                if int(pend["mode"]) == 0 and int(pend["act"]) in (7, 8, 9):
                    module_shots.append((int(pend["turn"]), pend["unit"], pend["from"], pend["to"], pend["aim"], pend["weapon"], x.get("spent"), x.get("dmg")))
            pend = None
    print(f"== {name}: {res}")
    print(f"  hostile units deciding {len(units)}, moved at all {sum(1 for u in units if first_pos[u] != last_pos[u])}")
    print("  (mode,act) counts: " + ", ".join(f"{k}={v}" for k, v in acts.most_common(14)))
    print("  events: " + ", ".join(f"{k}={v}" for k, v in events.most_common(14)))
    print(f"  shots decided in patrol mode: {len(module_shots)}")
    tiles = Counter(t[3] for t in module_shots)
    print("  their target tiles: " + ", ".join(f"{k}x{v}" for k, v in tiles.most_common(15)))
    for t in module_shots[:12]:
        print("    ", t)
    print("  by turn: " + " | ".join(f"t{k}:" + ",".join(f"{a}/{b}={n}" for (a, b), n in sorted(v.items())) for k, v in sorted(per_turn.items())[:6]))
