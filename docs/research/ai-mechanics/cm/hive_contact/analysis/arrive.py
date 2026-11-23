"""Contact coordination, feasibility check 4: does walking to a contact end in an attack? For the active runs of HH: each unit under a walking order towards a contact objective (why=seek_contact): on the turn after it first got such an order, did it attack, at what, did it see; arrivals and the time units left; the modes of the unit-turns that followed (read only)."""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))


def one(run):
    L = read(run)
    dec = defaultdict(lambda: defaultdict(list))
    order_turns = defaultdict(set)
    arrive = []
    for s in L:
        if s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1":
                dec[int(k["unit"])][int(k["turn"])].append(k)
        elif s.startswith("[HIVEORD]"):
            k = kv(s)
            if k.get("why") in ("seek_contact", "advance") and k.get("state") == "CREATED" and k.get("kind") == "GO":
                order_turns[int(k["unit"])].add((int(k["turn"]), k["why"]))
            if k.get("why") in ("seek_contact", "advance") and k.get("state") == "COMPLETED" and k.get("note") == "arrived":
                arrive.append((int(k["turn"]), int(k["unit"]), int(k["tu"]), k["why"]))
    res = Counter()
    modes_after = Counter()
    for u, ts in order_turns.items():
        for t, why in ts:
            if why != "seek_contact":
                continue
            res["orders"] += 1
            same = any(int(d["act"]) in ATT for d in dec[u].get(t, []))
            nxt = any(int(d["act"]) in ATT for d in dec[u].get(t + 1, []))
            res["attack_same_turn"] += same
            res["attack_next_turn"] += nxt
            res["attack_either"] += same or nxt
            for d in dec[u].get(t + 1, []):
                modes_after[d["mode"]] += 1
    arr = [a for a in arrive if a[3] == "seek_contact"]
    after_arr = 0
    tu_left = sorted(a[2] for a in arr)
    for t, u, tu, why in arr:
        after_arr += any(int(d["act"]) in ATT for d in dec[u].get(t, [])) or any(int(d["act"]) in ATT for d in dec[u].get(t + 1, []))
    print(run, dict(res), "modes next turn", dict(modes_after))
    print("   arrived", len(arr), "attack in that or next turn", after_arr, "TU left median", tu_left[len(tu_left) // 2] if tu_left else None)


if __name__ == "__main__":
    for r in sys.argv[1:]:
        one(r)
