"""OPERATIONAL INTELLIGENCE, steps 2-3: per AI turn and per known player's armoured unit: which AI fighters could, from their first decision of the turn, reach a cell where the rule of armour lets their weapon through, with TU left for the attack. The line of fire of a far cell is not guessed: only pairs (cell, target tile) the engine itself reported lof=1 for in any log of the same battle (same mission and seed: same map), in either direction. Then what D0 did with that fighter in that turn. Read only.
Usage: flank.py <run> <minimum capable fighters>"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import OUT, kv, read  # noqa: E402
from oilib import SIDE, Battle, acts_of, moves_of, pos, side_code  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
run = sys.argv[1]
MIN = int(sys.argv[2]) if len(sys.argv) > 2 else 2
parts = run.split("_")
tail = "_".join(parts[-2:])  # M6_s1
OK = {
    "STR_HEAVY_GAUSS": ("side", "rear"),
    "STR_GAUSS_SNIPER": ("rear",),
    "STR_GAUSS_RIFLE": ("rear",),
    "AUX_CHRYSSALID_WEAPON": ("front", "side", "rear"),
    "STR_PIR_PLASMA_RIFLE": ("rear",),
}
MELEE = {"AUX_CHRYSSALID_WEAPON"}
ARMOURED = ("444", "448", "470", "545")


def tiles(u, p):
    if u == "545":
        return [p]
    return [(p[0] + x, p[1] + y, p[2]) for x in (0, 1) for y in (0, 1)]


def arc(code):
    if code is None:
        return "under"
    s = SIDE[code]
    return "front" if s.startswith("front") else "rear" if s.startswith("rear") else "side"


def in_view(pos_u, size, direction, p):
    """BattleUnit::checkViewSector."""
    for x in range(size):
        for y in range(size):
            dx = p[0] - (pos_u[0] + x)
            dy = (pos_u[1] + y) - p[1]
            d = direction
            if (d == 0 and dx + dy >= 0 and dy - dx >= 0) or (d == 1 and dx >= 0 and dy >= 0) or (d == 2 and dx + dy >= 0 and dy - dx <= 0) or (d == 3 and dy <= 0 and dx >= 0) or (d == 4 and dx + dy <= 0 and dy - dx <= 0) or (d == 5 and dx <= 0 and dy <= 0) or (d == 6 and dx + dy <= 0 and dy - dx >= 0) or (d == 7 and dy >= 0 and dx <= 0):
                return True
    return False


# line of fire proved by the engine in any log of this battle
lofdb = set()
n_logs = 0
for rd in sorted(OUT.iterdir()):
    if not rd.name.endswith(tail):
        continue
    n_logs += 1
    cur = None
    for s in read(rd.name):
        if s.startswith("[AIDECIDE]"):
            cur = pos(kv(s)["from"])
        elif s.startswith("[AICAND] acts=") and cur:
            try:
                L = json.loads(s.split(" list=", 1)[1])
            except (IndexError, ValueError):
                continue
            for a in L:
                if a.get("k") == "a" and a.get("lof") == 1 and a.get("t") in (7, 8, 9):
                    to = tuple(a["to"])
                    lofdb.add((cur, to))
                    lofdb.add((to, cur))
print(f"==== {run}: lines of fire from {n_logs} logs of {tail}: {len(lofdb)}")
b = Battle(run)
first = defaultdict(dict)
acted = defaultdict(lambda: defaultdict(list))
for d in b.decisions:
    first[int(d["turn"])].setdefault(d["unit"], d)
for d in b.attacks:
    acted[int(d["turn"])][d["unit"]].append(d)
tot_cap = 0
for t in sorted(first):
    st = b.state.get(t, {})
    players = {u: k for u, k in st.items() if k.get("faction") == "0" and int(k.get("status", 0)) < 6}
    for T in ARMOURED:
        k = players.get(T)
        if not k or k.get("spotted") != "0":
            continue
        tp = pos(k["pos"])
        ttiles = tiles(T, tp)
        tdir = int(k["dir"])
        rows = []
        for U, d in first[t].items():
            ents = [a for a in acts_of(d) if a.get("k") == "a" and a["w"] in OK]
            if not ents:
                continue
            tu = int(d["tu"])
            moves = moves_of(d)
            moves[pos(d["from"])] = 0
            best = None
            weapons = defaultdict(lambda: 999)
            for a in ents:
                weapons[a["w"]] = min(weapons[a["w"]], a["tu"])
            for w, cost in weapons.items():
                for cell, c in moves.items():
                    left = tu - c - cost
                    if c < 0 or left < 0:
                        continue
                    a_ = arc(side_code(cell, tp, tdir))
                    if a_ not in OK[w]:
                        continue
                    if w in MELEE:
                        if cell[2] != tp[2] or cell in ttiles or min(max(abs(cell[0] - q[0]), abs(cell[1] - q[1])) for q in ttiles) != 1:
                            continue
                    elif not any((cell, q) in lofdb for q in ttiles):
                        continue
                    n = 1 + left // cost
                    view = sum(1 for u2, k2 in players.items() if max(abs(pos(k2["pos"])[0] - cell[0]), abs(pos(k2["pos"])[1] - cell[1])) <= 20 and in_view(pos(k2["pos"]), 1 if u2 not in ("444", "448", "470") else 2, int(k2["dir"]), cell))
                    score = (a_ == "rear", n, -view, -c)
                    if best is None or score > best[0]:
                        best = (score, w, cell, c, left, n, a_, view)
            if best:
                _, w, cell, c, left, n, a_, view = best
                did = acted[t].get(U, [])
                did_s = ";".join(f"{x['weapon'][4:12]}@{x.get('target')}:{(x.get('exec') or {}).get('dmg', 0)}" for x in did) or "no attack"
                rows.append(f"     {U} {b.units[U].get('type', '')[4:16]} {w[4:16]} from {d['from']} tu {tu}: cell {cell} way {c} shots {n} arc {a_} eyes {view} | D0: {did_s}")
        if len(rows) >= MIN:
            tot_cap += 1
            print(f" t{t} target {T} at {k['pos']} dir {tdir} hp {k['hp']}: {len(rows)} capable")
            print("\n".join(rows))
print("target-turns with enough capable fighters:", tot_cap)
