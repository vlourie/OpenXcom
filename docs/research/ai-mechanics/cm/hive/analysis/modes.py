"""HIVE COMMAND CORE V0: the modes the units chose, active against D0, and in the active battle by what the unit's order was in that turn (read only). Does a refused order take the free patrol away? 'none' is a unit with no order or a closed one. Usage: modes.py <active dir> <D0 dir> <last turn>"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
last = int(sys.argv[3])


def read(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


a = read(sys.argv[1])
d = read(sys.argv[2])


def key(k):
    return "m" + k["mode"] + ("_walk" if k["act"] == "2" else "_none" if k["act"] == "0" else "_fire")


for name, lines in (("active", a), ("D0", d)):
    c = Counter()
    for s in lines:
        if s.startswith("[AIDECIDE]"):
            k = dict(kv.findall(s))
            if k.get("side") == "1" and int(k["turn"]) <= last:
                c[key(k)] += 1
    print(name, sorted(c.items()))

state = {}
by = defaultdict(Counter)
refused_turn = {}
for s in a:
    if s.startswith("[HIVEORD]"):
        k = dict(kv.findall(s))
        if "state" in k and "id" in k:
            state[k["unit"]] = (k.get("task"), k.get("kind"), k["state"])
            if k["state"] == "BLOCKED" and k.get("note") == "no_path":
                refused_turn[k["unit"]] = k["turn"]
    elif s.startswith("[AIDECIDE]"):
        k = dict(kv.findall(s))
        if k.get("side") != "1" or int(k["turn"]) > last:
            continue
        st = state.get(k["unit"])
        label = "no_order" if not st else f"{st[0]}_{st[1]}_{st[2]}"
        if refused_turn.get(k["unit"]) == k["turn"] and st and st[2] == "BLOCKED":
            label = "REFUSED_NOW_free_patrol"
        by[label][key(k)] += 1
print("active by the order at the moment of the decision:")
for label, c in sorted(by.items()):
    print(f"  {label}: {sorted(c.items())}")
same_tile = Counter()
for s in a:
    if s.startswith("[HIVEORD]") and "state=BLOCKED" in s and "note=no_path" in s:
        k = dict(kv.findall(s))
        same_tile["target_is_own_tile" if k["at"] == k["target"] else "other"] += 1
print("refused 'no path':", dict(same_tile))
