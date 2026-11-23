"""Movement diagnosis: one row per walking order with what the unit really did during its life (read only). Writes ledger_<run>.tsv, prints the raw counts."""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from lib import kv, read, tup

sys.stdout.reconfigure(encoding="utf-8")
ATTACK = {4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20}


def load(run):
    L = read(run)
    orders = {}
    open_by_unit = {}
    decisions = defaultdict(list)  # unit -> decisions in log order
    last_dec = {}
    tasks = defaultdict(list)  # squad -> (line, text)
    for i, s in enumerate(L):
        if s.startswith("[HIVEORD]"):
            k = kv(s)
            if "own" in k or k.get("kind") != "GO":
                continue
            oid = int(k["id"])
            o = orders.setdefault(oid, dict(id=oid, unit=int(k["unit"]), squad=int(k["squad"]), task=k["task"], target=tup(k["target"]), why=k["why"], line0=i, turn0=int(k["turn"]), start=tup(k["at"]), tu0=int(k["tu"]), states=[], note={}))
            o["states"].append(k["state"])
            m = re.search(r"path_tu=(\d+) turns=(\d+) reach=(\w+) end=(\([^)]*\)) tiles=(\d+)", s)
            if m:
                o["note"] = dict(path_tu=int(m.group(1)), turns=int(m.group(2)), reach=m.group(3), end=m.group(4), tiles=int(m.group(5)))
        elif s.startswith("[HIVEFATE]"):
            k = kv(s)
            o = orders[int(k["id"])]
            o.update(fate=k["fate"], reason=k["reason"], end=tup(k["end"]), gain=int(k["gain"]), line1=i, turn1=int(k["turn"]), decided_walk=int(k["decided_walk"]), overrides=int(k["overrides"]))
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] != "1":
                continue
            d = dict(line=i, turn=int(k["turn"]), unit=int(k["unit"]), n=int(k["n"]), frm=tup(k["from"]), tu=int(k["tu"]), mode=int(k["mode"]), act=int(k["act"]), to=tup(k["to"]) if "to" in k else None, spent=0, stop=None, pos=None)
            decisions[d["unit"]].append(d)
            last_dec[d["unit"]] = d
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[len("[AIEXEC] "):])
            d = last_dec.get(j["unit"])
            if d is not None and d["pos"] is None:
                d["spent"] = j.get("spent", 0)
                d["pos"] = tuple(j["pos"]) if "pos" in j else None
                stops = [t.split()[0].replace("walk.stop.", "") for t in j.get("trail", []) if t.startswith("walk.stop.")]
                d["stop"] = stops[-1] if stops else None
                d["down"] = j.get("down", 0)
        elif s.startswith("[HIVETASK]") or s.startswith("[HIVEREVIEW]") or (s.startswith("[HIVEHOLD]") and "turn=" in s):
            k = kv(s)
            if "squad" in k:
                tasks[int(k["squad"])].append((i, s))
    return L, orders, decisions, tasks


def summarise(o, decisions):
    """What the unit did from the order's first line to its last: time units on the order, on its own choices, and how the last walk ended."""
    end = o.get("line1", 10 ** 9)
    ds = [d for d in decisions[o["unit"]] if o["line0"] <= d["line"] <= end]
    o["decs"] = ds
    o["walk_tu"] = sum(d["spent"] for d in ds if d["act"] == 2 and d["to"] == o["target"])
    o["own_tu"] = sum(d["spent"] for d in ds if not (d["act"] == 2 and d["to"] == o["target"]))
    o["n_walk"] = sum(d["act"] == 2 and d["to"] == o["target"] for d in ds)
    o["n_ownwalk"] = sum(d["act"] == 2 and d["to"] != o["target"] for d in ds)
    o["n_attack"] = sum(d["act"] in ATTACK for d in ds)
    o["n_none"] = sum(d["act"] == 0 for d in ds)
    o["modes"] = Counter(d["mode"] for d in ds)
    walks = [d for d in ds if d["act"] == 2 and d["to"] == o["target"] and d["stop"]]
    o["last_stop"] = walks[-1]["stop"] if walks else None
    o["stops"] = Counter(d["stop"] for d in ds if d["stop"])


if __name__ == "__main__":
    for run in sys.argv[1:]:
        L, orders, decisions, tasks = load(run)
        print("==", run, "walking orders", len(orders))
        rows = []
        for o in orders.values():
            summarise(o, decisions)
            rows.append(o)
        print(" reasons", Counter((o.get("fate", "OPEN"), o.get("reason", "open")) for o in rows).most_common())
        print(" stops of walks on order", Counter(s for o in rows for s, n in o["stops"].items() for _ in range(n)).most_common())
        allD = [d for ds in decisions.values() for d in ds]
        print(" side decisions", len(allD), "modes", Counter(d["mode"] for d in allD).most_common(), "acts", Counter(d["act"] for d in allD).most_common())
        print(" all walks stop", Counter(d["stop"] for d in allD if d["act"] == 2).most_common())
        ex = [o for o in rows if o.get("reason") == "too_long"][:3]
        for o in ex:
            print("  sample too_long", o["id"], o["unit"], o["start"], o["target"], o["note"], "walk_tu", o["walk_tu"], "own_tu", o["own_tu"], [(d["turn"], d["mode"], d["act"], d["to"], d["spent"], d["stop"]) for d in o["decs"]])
