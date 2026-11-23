"""OPERATIONAL INTELLIGENCE, step 1: every grenade the AI side threw in a battle, and what happened at the end of that AI turn: player's units within the blast radius, HP from [AISTATE] aistart of that turn to the first state of the next side, direct damage subtracted. Then which carriers could throw and did not. Read only.
Usage: throws.py <run> [radius]"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import Battle, acts_of, kv, pos  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
b = Battle(sys.argv[1])
R = int(sys.argv[2]) if len(sys.argv) > 2 else 5
# HP of the player's units at the start of each of their turns
hp_before = defaultdict(dict)
pos_at = defaultdict(dict)
kinds = Counter()
for s in b.L:
    if s.startswith("[AISTATE]"):
        kind = s.split(" ", 2)[1]
        kinds[kind] += 1
        k = kv(s)
        if k.get("faction") == "0" and kind == "before":
            hp_before[int(k["turn"])].setdefault(k["unit"], k)
print("AISTATE kinds", dict(kinds))
direct = defaultdict(lambda: defaultdict(int))
for d in b.attacks:
    if int(d["act"]) != 6:
        direct[int(d["turn"])][d["target"]] += (d.get("exec") or {}).get("dmg", 0)
print("====", b.run)
throws = [d for d in b.attacks if int(d["act"]) == 6]
print("throws", len(throws))
by_turn = defaultdict(list)
for d in throws:
    by_turn[int(d["turn"])].append(d)
for t in sorted(by_turn):
    st = b.state.get(t, {})
    print(f"-- AI turn {t}: {len(by_turn[t])} throws")
    for d in by_turn[t]:
        to = pos(d["to"])
        near = []
        for u, k in st.items():
            if k.get("faction") == "0" and int(k.get("status", 0)) < 6:
                p = pos(k["pos"])
                dist = max(abs(p[0] - to[0]), abs(p[1] - to[1]))
                if dist <= R and abs(p[2] - to[2]) <= 2:
                    near.append(f"{u}@{dist}")
        print(f"   {d['unit']} from {d['from']} to {d['to']} tu {d['tu']} src {d.get('src')} units in radius: {' '.join(near)}")
    nxt = hp_before.get(t + 1, {})
    for u, k in st.items():
        if k.get("faction") != "0":
            continue
        h0 = int(k["hp"].split("/")[0])
        h1 = int(nxt[u]["hp"].split("/")[0]) if u in nxt else None
        if h1 is not None and h0 != h1:
            print(f"      {u} hp {h0} -> {h1}, direct on it {direct[t].get(u, 0)}")
# carriers
carry = {}
first_t = {}
threw = Counter(d["unit"] for d in throws)
for d in b.decisions:
    for a in acts_of(d):
        if a.get("k") == "a" and a.get("t") == 6:
            carry[d["unit"]] = a["w"]
            first_t.setdefault(d["unit"], int(d["turn"]))
in_range = Counter()
could = Counter()
for d in b.decisions:
    ok = False
    for a in acts_of(d):
        if a.get("k") == "a" and a.get("t") == 6 and a.get("lof") == 1 and a.get("tu", 999) <= int(d["tu"]):
            ok = True
    if ok:
        in_range[d["unit"]] += 1
        could[(d["turn"], d["unit"])] = 1
print("carriers", len(carry), "threw", len(threw), "throws", sum(threw.values()))
print("carrier-turns where the engine's list had a legal throw with TU:", len(could), " decisions:", sum(in_range.values()), " carriers with at least one:", len(in_range))
dead = {c["victim"] for c in b.casualties if c.get("vfaction") == "1" and c.get("how") == "dead"}
print("carriers killed without having thrown:", len([u for u in carry if u in dead and u not in threw]), "of", len([u for u in carry if u in dead]))
