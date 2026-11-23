"""COORDINATED OPERATION, phase A: the source episode, M3 s1 D0, turns 4 and 5. Every state line of the two Chryssalids and of the tanks, trails of their walks, routes rebuilt from the engine's own cost lists, what any AI unit met standing in the region of the staging cells over all logs of this seed. Read only."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "oi"))
sys.path.insert(0, str(HERE.parent / "mc"))
from lib import OUT, kv  # noqa: E402
from oilib import Battle, moves_of, pos  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
b = Battle("scpa_D_M3_s1")
print("== state lines, turns 4-5")
turn = 0
for s in b.L:
    if s.startswith("[AISTATE]"):
        k = kv(s)
        t = int(k.get("turn", 0))
        if t in (4, 5) and k.get("unit") in ("1000000", "1000005", "470"):
            print(" ", s.split(" ", 2)[1], "t", t, k["unit"], "pos", k["pos"], "dir", k["dir"], "tu", k["tu"], "hp", k["hp"], "spot", k.get("spotted"), "sees", k.get("sees"), "seenby", k.get("seenby"), "known", k.get("known"), "near", k.get("near"), "reach", k.get("reach"))
print("== decisions and trails")
for d in b.decisions:
    if d["unit"] in ("1000000", "1000005") and d["turn"] in ("4", "5"):
        e = d.get("exec") or {}
        print(" ", d["turn"], d["unit"], d["from"], "tu", d["tu"], "mode", d["mode"], "src", d.get("src"), "to", d["to"], "aim", d["aim"], "seen", d.get("seen"), "spent", e.get("spent"), "dmg", e.get("dmg"), "trail", e.get("trail"))
print("== rebuilt routes of 1000005 at t4 (cost descent on its own first list)")
d4 = next(d for d in b.decisions if d["unit"] == "1000005" and d["turn"] == "4")
m4 = moves_of(d4)
start = pos(d4["from"])


def route(m, start, cell):
    r = [cell]
    cur = cell
    guard = 0
    while cur != start and guard < 200:
        guard += 1
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    c = (cur[0] + dx, cur[1] + dy, cur[2] + dz)
                    if c == cur:
                        continue
                    v = 0 if c == start else m.get(c)
                    if v is None or v < 0 or v >= m[cur]:
                        continue
                    if best is None or v < best[0]:
                        best = (v, c)
        if best is None:
            return r + ["?"]
        cur = best[1]
        r.append(cur)
    return list(reversed(r))


for c in ((44, 32, 3), (45, 32, 3), (44, 33, 3), (45, 33, 3), (44, 31, 3), (44, 34, 3)):
    if c in m4:
        print(" ", c, "cost", m4[c], "route", route(m4, start, c))
d0 = next(d for d in b.decisions if d["unit"] == "1000000" and d["turn"] == "4")
m0 = moves_of(d0)
print(" 1000000 at t4 from", d0["from"], "tu", d0["tu"], {c: m0.get(c) for c in ((44, 32, 3), (45, 32, 3), (44, 33, 3), (45, 33, 3))})
print("== any AI unit standing in x 41..49, y 28..37, z 3, all logs of this seed, by kind of state line")
for p in sorted(OUT.iterdir()):
    if not p.name.endswith("M3_s1"):
        continue
    bb = Battle(p.name)
    seen = {}
    for s in bb.L:
        if s.startswith("[AISTATE]"):
            k = kv(s)
            if k.get("faction") != "1" or "pos" not in k:
                continue
            q = pos(k["pos"])
            if 41 <= q[0] <= 49 and 28 <= q[1] <= 37 and q[2] == 3:
                key = (int(k["turn"]), k["unit"], s.split(" ", 2)[1])
                seen[key] = (k["pos"], k.get("seenby"), k.get("hp"), k.get("type", "")[4:14], k.get("sees"))
    print(" ", p.name, len(seen))
    for key in sorted(seen)[:22]:
        if key[0] <= 8:
            print("    ", key, seen[key])
