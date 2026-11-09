"""HIVE COMMAND CORE V0: can the units refused 'no path' really leave where they stood? Over a whole D0 battle: every tile any unit of the same movement type stood on is a witness of reach. For each refused pair (at, target): did any unit in D0 walk from that floor area to the target's floor, and how far did this very unit ever go in D0. Read only. Usage: reach.py <active dir> <D0 dir> <n units>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")


def read(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


def xyz(s):
    return tuple(int(v) for v in s.strip("()").split(","))


a = read(sys.argv[1])
d = read(sys.argv[2])
n = int(sys.argv[3])

move = {}
for s in a:
    if s.startswith("[HIVEUNIT]"):
        k = dict(kv.findall(s))
        move[k["id"]] = k["move"]

ref = Counter()
pairs = defaultdict(Counter)
for s in a:
    if s.startswith("[HIVEORD]") and "state=BLOCKED" in s and "note=no_path" in s:
        k = dict(kv.findall(s))
        ref[k["unit"]] += 1
        pairs[k["unit"]][(k["at"], k["target"])] += 1

# the walks of D0 as a graph over tiles, by movement type: an edge is a position change of one unit between two records
pos = defaultdict(list)
for s in d:
    if s.startswith("[AIDECIDE]"):
        k = dict(kv.findall(s))
        if k.get("side") == "1":
            pos[k["unit"]].append((int(k["turn"]), k["from"], k.get("mode"), k.get("act")))
edges = {"0": defaultdict(set), "1": defaultdict(set)}
for u, seq in pos.items():
    m = move.get(u, "0")
    for x, y in zip(seq, seq[1:]):
        if x[1] != y[1]:
            edges[m][x[1]].add(y[1])
            edges[m][y[1]].add(x[1])


def component(start, g):
    seen = {start}
    stack = [start]
    while stack:
        for nxt in g.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


for u, c in ref.most_common(n):
    seq = pos.get(u, [])
    tiles = [xyz(p[1]) for p in seq]
    if tiles:
        x0, y0, z0 = tiles[0]
        far = max(max(abs(t[0] - x0), abs(t[1] - y0)) for t in tiles)
        floors = Counter(t[2] for t in tiles)
    else:
        far, floors = 0, {}
    last = seq[-1][0] if seq else 0
    print(f"{u} move={move.get(u)} refused {c}; in D0 it lives to turn {last}, farthest {far} tiles from its start, floors {dict(floors)}")
    g0 = edges[move.get(u, "0")]
    ats = Counter()
    for (at, target), v in pairs[u].items():
        ats[at] += v
    for at, v in ats.most_common(2):
        comp = component(at, g0) if at in g0 else set()
        fl = Counter(xyz(t)[2] for t in comp)
        xs = [xyz(t)[0] for t in comp] or [0]
        ys = [xyz(t)[1] for t in comp] or [0]
        print(f"   at {at} ({v} refusals): known in D0's walks of that movement type {at in g0}; connected tiles {len(comp)}, floors {dict(fl)}, x {min(xs)}-{max(xs)}, y {min(ys)}-{max(ys)}")
        tg = Counter(t for (a0, t), w in pairs[u].items() if a0 == at)
        hit = sum(w for t, w in tg.items() if t in comp)
        print(f"      of its refused targets, tiles that D0's walks connect to it: {hit} of {sum(tg.values())}; sample targets {[t for t, _ in tg.most_common(4)]}")
