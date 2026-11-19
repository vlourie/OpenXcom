"""MISSION-LEVEL TACTICS: the base defense battle unit by unit: every aim at a module with what came of the shot, every unit that reached a target
node and found no module, what the rooms hold by level.

  py -3.13 -I fl_m2.py <probe battle dir>"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
rows = []
with gzip.open(Path(sys.argv[1]) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
    for raw in f:
        rows.append(raw.rstrip("\n").split("\t", 2)[-1])

mt = defaultdict(Counter)
fac = {}
for s in rows:
    if s.startswith("[AIMISSION] what=mtile"):
        d = dict(KV.findall(s))
        x, y, z = map(int, d["at"].split(","))
        mt[(x // 10, y // 10)][z] += 1
    elif s.startswith("[AIMISSION] what=fac"):
        d = dict(KV.findall(s))
        fac[d["at"]] = d["type"].replace("STR_", "")
nodes = defaultdict(list)
for s in rows:
    if s.startswith("[AIMISSION] what=node"):
        d = dict(KV.findall(s))
        nodes[d["grid"]].append(d["at"])
print("grid: facility, module tiles by z, target nodes")
for g, c in sorted(mt.items()):
    k = f"{g[0]},{g[1]}"
    print(f"  {k} {fac.get(k, '-'):32} {dict(sorted(c.items()))} nodes {nodes.get(k, [])}")

# an aim, the decision that follows it for that unit, the hits up to its [AIEXEC]
pend = {}
cur = None
shots = []
seq = []
for s in rows:
    if s.startswith("[AIMISSION] what=aim"):
        d = dict(KV.findall(s))
        pend[d["unit"]] = d
    elif s.startswith("[AIDECIDE] "):
        d = dict(KV.findall(s.split(" hu=")[0]))
        if d["side"] == "1":
            aim = pend.pop(d["unit"], None)
            cur = {"aim": aim, "dec": d, "hits": []}
    elif s.startswith("[AIMISSION] what=hit") and cur is not None:
        d = dict(KV.findall(s))
        if d["unit"] == cur["dec"]["unit"]:
            cur["hits"].append(d)
    elif s.startswith("[AIEXEC] ") and cur is not None:
        x = json.loads(s[9:])
        if str(x["unit"]) == cur["dec"]["unit"]:
            cur["exec"] = x
            if cur["aim"]:
                shots.append(cur)
            cur = None
print("aims with the decision and the outcome:")
print(" turn unit from target tu/cost lof line impact | mode act spent | hits (tile part tdmg/armor module)")
outcome = Counter()
for c in shots[:90]:
    a, d, x = c["aim"], c["dec"], c.get("exec", {})
    h = " ".join(f"{i['tile']}:p{i['part']}:{i['tdmg']}/{i['partarmor']}:m{i['module']}" for i in c["hits"])
    print(f" t{a['turn']} {a['unit']} {a['from']} > {a['target']} {a['tu']}/{a['cost']} lof{a['lof']} l{a['line']} {a['impact']} | m{d['mode']} a{d['act']} sp{x.get('spent')} | {h}"[:190])
    fired = int(d["act"]) in (7, 8, 9) and (x.get("spent") or 0) > 0
    key = "not fired" if not fired else ("no hit line" if not c["hits"] else "unit" if all(i["part"] == "4" for i in c["hits"]) else "module" if any(i["module"] == "1" and i["part"] == "3" for i in c["hits"]) else "other terrain")
    outcome[key] += 1
print("outcome of aims:", outcome.most_common())
print("nomodule:", [(dict(KV.findall(s))["turn"], dict(KV.findall(s))["unit"], dict(KV.findall(s))["from"]) for s in rows if s.startswith("[AIMISSION] what=nomodule")][:30])
w = Counter()
for s in rows:
    if s.startswith("[AIMISSION] what=walk"):
        d = dict(KV.findall(s))
        w[(d["unit"], d["node"])] += 1
print("walks unit>node:", w.most_common(16))
un = [dict(KV.findall(s)) for s in rows if s.startswith("[AIMISSION] what=unit")]
print("protocol units at start:", [(d["id"], d["at"]) for d in un if d["protocol"] == "1"][:30])
b = Counter()
for s in rows:
    if s.startswith("[AIMISSION] what=blast"):
        d = dict(KV.findall(s))
        b[(d["turn"], d["tile"][:6])] += 1
print("blasts:", b.most_common(12))
