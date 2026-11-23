"""HIVE COMMAND CORE V0: the organization and execution checks of one active battle (read only): all units accounted once, commanders real and at the place they were named, no unit with two open orders, a squad never left without a commander, tasks kept over turns and commander changes, two squads doing different tasks in one turn, orders refused, whether the walk really was the order's. Usage: orgcheck.py <dir>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
lines = [ln.rstrip("\n").split("\t")[-1] for ln in gzip.open(Path(sys.argv[1]) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace")]


def xyz(s):
    return tuple(int(v) for v in s.strip("()").split(","))


units = {}
squads0 = []
for s in lines:
    if s.startswith("[HIVEUNIT]"):
        k = dict(kv.findall(s))
        units[k["id"]] = k
    elif s.startswith("[HIVESQUAD] id="):
        squads0.append(dict(kv.findall(s)))
    elif s.startswith("[HIVEINIT]"):
        print(s[:200])

managed = {u for u, k in units.items() if k["managed"] == "1"}
apart = Counter(k["why"] for k in units.values() if k["managed"] == "0")
members = Counter()
for q in squads0:
    for m in q["members"].split(","):
        members[re.sub(r"\D", "", m)] += 1
print("units", len(units), "managed", len(managed), "apart", dict(apart))
print("in squads", len(members), "twice", sum(v > 1 for v in members.values()), "managed but not in a squad", len(managed - set(members)), "in a squad but not managed", len(set(members) - managed))
print("squad sizes", sorted(int(q["size"]) for q in squads0), "tasks", Counter(q["task"] for q in squads0))
print("first commanders by rank:", Counter(q["rank"] + " int=" + q["int"] for q in squads0))
print("not their own squad's member:", sum(q["commander"] not in {re.sub(r"\D", "", m) for m in q["members"].split(",")} for q in squads0))
print("ranks and Intelligence of all:", sorted(Counter((k["rank"], k["int"], k["aggr"]) for k in units.values()).items()))

# orders: one open per unit; the walk against the order
OPEN = {"CREATED", "ASSIGNED", "VALIDATED", "EXECUTING"}
opened = {}
overlap = 0
states = defaultdict(list)
orders = {}
for s in lines:
    if not s.startswith("[HIVEORD]"):
        continue
    k = dict(kv.findall(s))
    if "own" in k or "state" not in k or "id" not in k:
        continue
    oid, unit, st = k["id"], k["unit"], k["state"]
    if st == "CREATED":
        if unit in opened and opened[unit] != oid:
            overlap += 1
        opened[unit] = oid
    elif st not in OPEN and opened.get(unit) == oid:
        del opened[unit]
    states[oid].append(st)
    orders[oid] = k
print("orders", len(orders), "a unit given a new order with another still open:", overlap)
bad = Counter()
ORDER = ["CREATED", "ASSIGNED", "VALIDATED", "EXECUTING"]
for oid, tr in states.items():
    idx = [ORDER.index(x) for x in tr if x in ORDER]
    if idx != sorted(idx):
        bad["backwards"] += 1
    if tr[0] != "CREATED":
        bad["no_created"] += 1
    if sum(x not in OPEN for x in tr) > 1:
        bad["two_ends"] += 1
print("state chain errors:", dict(bad))

# the order was the unit's walk: decision's target against the order's target when the unit walks on patrol
target = {}
same = other = 0
for s in lines:
    if s.startswith("[HIVEORD]"):
        k = dict(kv.findall(s))
        if "state" in k and k.get("kind") == "GO":
            if k["state"] in OPEN:
                target[k["unit"]] = k["target"]
            else:
                target.pop(k["unit"], None)
    elif s.startswith("[AIDECIDE]"):
        k = dict(kv.findall(s))
        if k.get("side") == "1" and k.get("mode") == "0" and k.get("act") == "2" and k["unit"] in target:
            if k["to"] == target[k["unit"]]:
                same += 1
            else:
                other += 1
print("patrol walks of units with a walking order: to the order's target", same, "elsewhere", other)

# per turn: squads of each task with a unit that did its order
by_turn = defaultdict(lambda: defaultdict(set))
for oid, k in orders.items():
    pass
for s in lines:
    if s.startswith("[HIVEORD]"):
        k = dict(kv.findall(s))
        if k.get("state") == "COMPLETED":
            by_turn[int(k["turn"])][k["task"] + "_" + k["kind"]].add(k["squad"])
print("turn: squads with a completed order, by task and kind")
for t in sorted(by_turn):
    print(" ", t, {a: len(b) for a, b in sorted(by_turn[t].items())})

for s in lines:
    if s.startswith("[HIVETURN]"):
        k = dict(kv.findall(s))
        print(" T", k["turn"], "alive", k["alive"], "squads", k["squads"], "hold", k["hold"], k["holdUnits"], k["holdTuPct"] + "%", "search", k["search"], k["searchUnits"], k["searchTuPct"] + "%", "thinks", k["thinks"], "thinkUs", k["thinkUs"])
print("commander changes:", [(dict(kv.findall(s))["turn"], dict(kv.findall(s))["why"], dict(kv.findall(s))["task"], dict(kv.findall(s))["kept"]) for s in lines if s.startswith("[HIVECMD]")])
print("merges:", sum(s.startswith("[HIVESQUAD] turn=") and " merged=" in s for s in lines), "squad lines after start:", [s[:90] for s in lines if s.startswith("[HIVESQUAD] turn=") and " merged=" not in s][:6])
print("objective kinds:", Counter(dict(kv.findall(s)).get("kind") for s in lines if s.startswith("[HIVETASK]")), "contacts aimed at:", Counter(dict(kv.findall(s)).get("contact") for s in lines if s.startswith("[HIVETASK]")))
print("contact classes:", Counter(dict(kv.findall(s)).get("cls") for s in lines if s.startswith("[HIVECONTACT]")), "expired:", sum("event=expired" in s for s in lines if s.startswith("[HIVECONTACT]")))
print("refusals:", Counter(o.get("note") for o in orders.values() if o["state"] == "BLOCKED"))
print("plan us max:", max([int(dict(kv.findall(s)).get("us", 0)) for s in lines if s.startswith("[HIVEPERF]")] or [0]), "init us:", [dict(kv.findall(s)).get("us") for s in lines if s.startswith("[HIVEINIT]")])
print("errors in the journal:", sum(("FATAL" in s or "[ERROR]" in s or "Segmentation" in s) for s in lines))
