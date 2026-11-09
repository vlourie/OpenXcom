"""COORDINATED_ENGAGEMENT_V1 diagnostics: the exposed hostile unit-turns (no attack, ended in sight) of a series - the decisions
of that unit-turn (mode, action, walk target), how the walk ended (AIEXEC trail: stop reason), and the h.ce.* tallies of the
series' tables.

  py -3.13 -I ce_exposed.py <out dir> <arena dir> <prefix>"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, AR, PRE = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
MODE = {"0": "patrol", "1": "ambush", "2": "combat", "3": "escape"}

tac = Counter()
for p in sorted(AR.glob(f"{PRE}_*.tsv")):
    if p.name.endswith(".data_manifest.tsv"):
        continue
    lines = p.read_text(encoding="utf-8-sig").splitlines()
    r = dict(zip(lines[0].split("\t"), lines[-1].split("\t")))
    for kv in r.get("tac", "").split(","):
        if kv.startswith("h.ce."):
            k, v = kv[2:].rsplit(":", 1)
            tac[k] += int(v)
print("tallies:", dict(sorted(tac.items())))

def pos(t):
    return tuple(int(x) for x in t.strip("()").split(","))


shape = Counter()
stops = Counter()
lastdec = Counter()
dist = Counter()
for d in sorted(OUT.glob(f"{PRE}_*")):
    last = {}
    players = {}
    ut = defaultdict(lambda: {"att": 0, "spotted": 0, "decs": [], "stops": [], "near": None})
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AISTATE] "):
                k = dict(KV.findall(body))
                if k.get("faction") == "0" and "pos" in k:
                    if k["status"] in ("0", "1", "2", "3"):
                        players[k["unit"]] = pos(k["pos"])
                    else:
                        players.pop(k["unit"], None)
            elif body.startswith("[AIDECIDE] "):
                k = dict(KV.findall(body))
                last[k["unit"]] = k
                if k.get("side") == "1" and k.get("from") and players:
                    p = pos(k["from"])
                    q = min(players.values(), key=lambda q: (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2)
                    ut[(int(k["turn"]), k["unit"])]["near"] = (max(abs(q[0] - p[0]), abs(q[1] - p[1])), abs(q[2] - p[2]))
            elif body.startswith("[AIEXEC] "):
                e = json.loads(body[len("[AIEXEC] "):])
                k = last.pop(str(e["unit"]), None)
                if not k or k.get("side") != "1":
                    continue
                s = ut[(int(k["turn"]), k["unit"])]
                s["decs"].append(MODE.get(k["mode"], k["mode"]) + "/" + k["act"])
                if int(k["act"]) in ATT:
                    s["att"] += 1
                if "pos" in e:
                    s["spotted"] = e.get("spotted", 0)
                for t in e.get("trail", []):
                    s["stops"].append(t.split(" ")[0])
    for s in ut.values():
        if s["att"] or not s["spotted"]:
            continue
        shape[" ".join(s["decs"][-3:])] += 1
        lastdec[s["decs"][-1] if s["decs"] else "-"] += 1
        stops[s["stops"][-1] if s["stops"] else "-"] += 1
        if s["near"] and s["decs"] and s["decs"][-1].split("/")[0] in ("patrol", "combat"):
            dd, dz = s["near"]
            dist[("<=12" if dd <= 12 else "13-20" if dd <= 20 else ">20") + (" dz0-1" if dz <= 1 else " dz2+")] += 1
print("exposed patrol/combat: distance of its last decision's start to the closest player unit:", dict(dist.most_common()))
print("exposed unit-turns, last decision:", dict(lastdec.most_common()))
print("exposed, how the last walk ended:", dict(stops.most_common(12)))
print("exposed, last three decisions:")
for k, v in shape.most_common(12):
    print(f"  {v:4d}  {k}")
