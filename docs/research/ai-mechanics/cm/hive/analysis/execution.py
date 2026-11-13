"""HIVE COMMAND CORE V0: what really became of the walking orders of one battle, and what the side did late in it, against D0 (read only).
Per GO order: refused at once, walked or not, net approach to the target between the first and the last record. Per turn band: shots, walks, units that spent nothing. First turn: the same unit against D0, was the first patrol walk the order's and not D0's. Usage: execution.py <active dir> <D0 dir>"""
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


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) + 2 * abs(a[2] - b[2])


a = read(sys.argv[1])
d = read(sys.argv[2])

orders = {}
for s in a:
    if not s.startswith("[HIVEORD]"):
        continue
    k = dict(kv.findall(s))
    if "id" not in k or "state" not in k or k.get("kind") != "GO":
        continue
    o = orders.setdefault(k["id"], {"first": k["at"], "task": k["task"], "target": k["target"], "unit": k["unit"], "turn": int(k["turn"]), "squad": k["squad"], "trail": []})
    o["last"] = k["at"]
    o["state"] = k["state"]
    o["note"] = k.get("note", "")
    o["trail"].append(k["state"])

fate = Counter()
approach = defaultdict(list)
for o in orders.values():
    if o["state"] == "BLOCKED" and "EXECUTING" not in o["trail"]:
        fate["refused_before_a_step"] += 1
        continue
    if "EXECUTING" not in o["trail"]:
        fate["never_executing:" + o["state"]] += 1
        continue
    fate["executed:" + o["state"]] += 1
    gain = dist(xyz(o["first"]), xyz(o["target"])) - dist(xyz(o["last"]), xyz(o["target"]))
    approach[o["task"]].append(gain)
print("GO orders", len(orders), dict(fate))
for t, g in sorted(approach.items()):
    closer = sum(x > 0 for x in g)
    print(f"  executed, {t}: {len(g)}, closer to the target at the last record {closer}, not closer {len(g) - closer}, mean gain {sum(g) / max(1, len(g)):.1f}, distinct units {len({o['unit'] for o in orders.values() if o['task'] == t and 'EXECUTING' in o['trail']})}, distinct squads {len({o['squad'] for o in orders.values() if o['task'] == t and 'EXECUTING' in o['trail']})}")

refused_units = Counter(o["unit"] for o in orders.values() if o["state"] == "BLOCKED" and o["note"] == "no_path")
walkers = {o["unit"] for o in orders.values() if "EXECUTING" in o["trail"]}
print("refused 'no path': units", len(refused_units), "orders", sum(refused_units.values()), "top", refused_units.most_common(6), "| of these units, also walked some other order:", sum(u in walkers for u in refused_units))


def bands(lines):
    tab = defaultdict(Counter)
    for s in lines:
        if s.startswith("[AIDECIDE]"):
            k = dict(kv.findall(s))
            if k.get("side") != "1":
                continue
            t = int(k["turn"])
            b = (t - 1) // 3
            if k["act"] in ("6", "7", "8", "9", "10", "11", "12"):
                tab[b]["shots"] += 1
            elif k["act"] == "2":
                tab[b]["walks"] += 1
    return tab


ba, bd = bands(a), bands(d)
print("turns: shots/walks active // D0")
for b in range(0, 4):
    print(f"  {b * 3 + 1:2d}-{b * 3 + 3:2d}: {ba[b]['shots']}/{ba[b]['walks']} // {bd[b]['shots']}/{bd[b]['walks']}")

# first turn: same unit, first patrol walk
order_to = defaultdict(set)
for o in orders.values():
    if o["turn"] == 1:
        order_to[o["unit"]].add(o["target"])
first = {}
for s in a:
    if s.startswith("[AIDECIDE]"):
        k = dict(kv.findall(s))
        if k.get("side") == "1" and k["turn"] == "1" and k["mode"] == "0" and k["act"] == "2":
            first.setdefault(k["unit"], k["to"])
d0first = {}
for s in d:
    if s.startswith("[AIDECIDE]"):
        k = dict(kv.findall(s))
        if k.get("side") == "1" and k["turn"] == "1" and k["mode"] == "0" and k["act"] == "2":
            d0first.setdefault(k["unit"], k["to"])
same = sum(first.get(u) == d0first.get(u) for u in first if u in d0first)
ordered = sum(first[u] in order_to[u] for u in first)
d0_elsewhere = sum(first[u] in order_to[u] and first[u] != d0first.get(u) for u in first)
print("turn 1, first patrol walk: units", len(first), "to their order's target", ordered, "of those not where the same unit went in D0", d0_elsewhere, "| D0 patrol walkers", len(d0first), "active walkers that matched D0", same)

stay = {}
for s in a:
    if s.startswith("[HIVEORD]"):
        k = dict(kv.findall(s))
        if k.get("turn") == "1" and k.get("kind") == "STAY" and k.get("state") == "VALIDATED":
            stay[k["unit"]] = True
walked_d0 = sum(u in d0first for u in stay)
walked_a = sum(u in first for u in stay)
print("turn 1, units with a STAY order:", len(stay), "patrol-walked in D0", walked_d0, "patrol-walked here", walked_a)


def tu_of(lines, turn, units):
    out = []
    for s in lines:
        if s.startswith("[AISTATE] pstart "):
            k = dict(kv.findall(s))
            if int(k["turn"]) == turn and k.get("unit") in units and k.get("faction") == "1" and k.get("status") not in ("6", "7"):
                out.append(int(k["tu"]) * 100 // max(1, int(k.get("tumax", 1))))
    return sum(out) // max(1, len(out)), len(out)


print("TU% at the player's turn 2 of the STAY units: active", tu_of(a, 2, stay), "D0", tu_of(d, 2, stay))
