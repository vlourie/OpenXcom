"""OPERATIONAL INTELLIGENCE, step 3: one episode in full from a D0 log: the target at each turn (place, facing, HP, spotted, seen by how many), every decision of the named AI fighters in those turns (cell, TU, mode, source, act, destination, side of armour met, spent, damage, the engine's own numbers for that target: p, lof, cost, distance), reaction events, casualties on either side, kills by the target after the episode. Read only.
Usage: episode.py <run> <target> <first turn> <last turn> <unit,unit,...|all>"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import SIDE, Battle, acts_of, kv, moves_of, pos, side_code  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
run, T, t0, t1, who = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
b = Battle(run)
ids = None if who == "all" else set(who.split(","))
pstart = {}
for s in b.L:
    if s.startswith("[AISTATE] pstart"):
        k = kv(s)
        pstart[(int(k["turn"]), k["unit"])] = k
print("====", run, "target", T)
for t in range(t0, t1 + 2):
    k = b.state.get(t, {}).get(T)
    n = pstart.get((t, T))
    if n:
        print(f" t{t} pstart: pos {n['pos']} dir {n['dir']} tu {n['tu']} hp {n['hp']}")
    if k:
        print(f" t{t} aistart: pos {k['pos']} dir {k['dir']} tu {k['tu']} hp {k['hp']} spotted {k.get('spotted')} sniped {k.get('sniped')} seenby {k.get('seenby')} wounds {k.get('wounds')}")
for d in b.decisions:
    t = int(d["turn"])
    if not (t0 <= t <= t1) or (ids is not None and d["unit"] not in ids):
        continue
    k = b.state.get(t, {}).get(T)
    side = "?"
    if k:
        c = side_code(pos(d["to"]), pos(k["pos"]), int(k["dir"]))
        side = SIDE.get(c, "under")
    mine = [a for a in acts_of(d) if a.get("k") == "a" and a.get("u") == int(T)]
    best = sorted(mine, key=lambda a: -a.get("p", 0))[:3]
    m = moves_of(d)
    e = d.get("exec") or {}
    tp = (e.get("trail") or [])
    print(f" t{t} {d['unit']} from {d['from']} tu {d['tu']} hp {d['hp']} mode {d['mode']} act {d['act']} to {d['to']} {d['weapon'][4:16]} src {d.get('src')} tgt {d.get('target', '')} side-if-from-to {side} spent {e.get('spent')} dmg {e.get('dmg')} down {e.get('downed')} | on {T}: " + " ".join(f"t{a['t']} {a['w'][4:12]} tu{a['tu']} p{a.get('p')} lof{a.get('lof')} d{a.get('d')}" for a in best))
print("-- reactions and casualties in the window, in log order")
turn = None
for s in b.L:
    if s.startswith("[AISTATE] aistart"):
        turn = int(kv(s)["turn"])
    if turn is None or not (t0 <= turn <= t1):
        continue
    if s.startswith("[AICASUALTY]"):
        c = kv(s)
        print("  casualty", {x: c.get(x) for x in ("turn", "victim", "how", "killer", "weapon", "hit", "dist", "pos")})
    elif s.startswith("[AIEVENT]") and "reaction" in s:
        print("  " + s[:190])
print("-- kills by the target, per turn, over the whole battle")
kills = Counter()
for c in b.casualties:
    if c.get("killer") == T and c.get("how") == "dead" and c.get("vfaction") == "1":
        kills[int(c["turn"])] += 1
print("  ", sorted(kills.items()))
print("-- all player's kills per turn:", sorted(Counter(int(c["turn"]) for c in b.casualties if c.get("how") == "dead" and c.get("vfaction") == "1").items()))
