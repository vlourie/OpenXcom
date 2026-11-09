"""SIDE_TURN_ACTION_SCHEDULER stage 3: where OXCE's reaction checks stopped the covering units ([AICOVERGATE], TileEngine::
getSpottingUnits / checkReactionFire, log only). Per COVER order (hostile turn T, unit B): in the player's turn T+1 the checks
made for B (one per player unit's walk step, shot or kneel), how many stopped at each gate in the engine's order, the deepest
gate reached, the nearest mover, and for the score gate the lowest mover score against B's; then B's reactions in that turn.

  py -3.13 -I sc_gate.py <out dir> <label>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, LAB = Path(sys.argv[1]), sys.argv[2]
KV = re.compile(r"(\w+)=(\S+)")
ORDER = ["out", "score", "dist", "sector", "lof", "visible", "weapon", "range", "accuracy", "spotter", "count", "try"]

covers, gates, reacts = [], defaultdict(list), Counter()
with gzip.open(OUT / LAB / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
    for raw in f:
        body = raw.rstrip("\n").split("\t", 2)[-1]
        if body.startswith("[AICOVER] "):
            covers.append(dict(KV.findall(body)))
        elif body.startswith("[AICOVERGATE] "):
            d = dict(KV.findall(body))
            gates[(int(d["turn"]), d["unit"])].append(d)
        elif body.startswith("[AIEVENT] ") and " what=reaction " in body:
            d = dict(KV.findall(body))
            if d["side"] == "0":
                reacts[(int(d["turn"]), d["unit"])] += 1

total = Counter()
reached = Counter()
print(f"{LAB}: COVER orders {len(covers)}, gate lines {sum(len(v) for v in gates.values())}")
for c in covers:
    t, b = int(c["turn"]) + 1, c["unit"]
    g = gates.get((t, b), [])
    cnt = Counter(x["gate"] for x in g)
    total.update(cnt)
    deep = max((ORDER.index(x["gate"]) for x in g), default=-1)
    reached[ORDER[deep] if deep >= 0 else "none"] += 1
    movers = {x["mover"] for x in g}
    near = min(g, key=lambda x: int(x["d2"]), default=None)
    sc = [x for x in g if x["gate"] == "score"]
    low = min(sc, key=lambda x: int(x["mscore"]), default=None)
    print(f"\n turn {c['turn']} B {b} pos {c['pos']} face {c['face']} {c['weapon']} reactions {c['reactions']}: player turn {t}: "
          f"{len(g)} checks from {len(movers)} movers; " + " ".join(f"{k}:{cnt[k]}" for k in ORDER if cnt[k]))
    print(f"   deepest gate: {ORDER[deep] if deep >= 0 else '-'}; B's reactions in turn {t}: {reacts[(t, b)]}")
    if near:
        print(f"   nearest check: mover {near['mover']} at {near['mpos']} d2 {near['d2']} mscore {near['mscore']} uscore {near['uscore']} "
              f"udir {near['udir']} gate {near['gate']}")
    if low:
        print(f"   score gate: B {low['uscore']} vs the lowest mover score {low['mscore']} (mover {low['mover']}, tu {low['mtu']}, d2 {low['d2']})")
    for x in g:
        if ORDER.index(x["gate"]) >= ORDER.index("weapon"):
            print(f"   {x['gate']}: mover {x['mover']} at {x['mpos']} tu {x['mtu']} mscore {x['mscore']}, B tu {x['utu']} uscore {x['uscore']} "
                  f"d2 {x['d2']} a {x['a']} b {x['b']}")
print("\nall checks by gate: " + " ".join(f"{k}:{total[k]}" for k in ORDER if total[k]))
print("orders by the deepest gate reached: " + " ".join(f"{k}:{reached[k]}" for k in ORDER + ["none"] if reached[k]))
