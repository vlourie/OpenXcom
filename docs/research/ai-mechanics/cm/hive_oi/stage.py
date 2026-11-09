"""OPERATIONAL INTELLIGENCE, step 3: M3 s1, the two Chryssalids against tank 470, turns 4 and 5. Cells next to the tank at t5 and their cost from 1000000's own engine list of t5 (standing at (44,32,3)), the staging cells near that place in 1000005's own list of t4, its own list of t5, all reaction and casualty lines of turn 5 by 470 with the count, fate of 1000005, HP of each. Read only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import SIDE, Battle, kv, moves_of, pos, side_code  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
b = Battle("scpa_D_M3_s1")
st5 = b.state[5]["470"]
tp, td = pos(st5["pos"]), int(st5["dir"])
print("470 at t5", tp, "dir", td, "hp", st5["hp"], "tu", st5["tu"], "spotted", st5["spotted"], "seenby", st5["seenby"])
tiles = [(tp[0] + x, tp[1] + y, tp[2]) for x in (0, 1) for y in (0, 1)]
near = [(tp[0] + x, tp[1] + y, tp[2]) for x in range(-1, 3) for y in range(-1, 3) if (tp[0] + x, tp[1] + y, tp[2]) not in tiles]
d0 = next(d for d in b.decisions if d["unit"] == "1000000" and d["turn"] == "5")
d5 = next(d for d in b.decisions if d["unit"] == "1000005" and d["turn"] == "5")
d4 = next(d for d in b.decisions if d["unit"] == "1000005" and d["turn"] == "4")
m0, m5, m4 = moves_of(d0), moves_of(d5), moves_of(d4)
print("cells next to 470: side of armour, way from (44,32,3) by 1000000's list t5, way from (40,54,3) by 1000005's list t5")
for c in near:
    s = SIDE.get(side_code(c, tp, td), "under")
    print("  ", c, s, m0.get(c), m5.get(c))
print("staging cells for 1000005 at t4 near (44,32,3), TU 181:", d4["from"], d4["tu"])
for x in range(42, 48):
    for y in range(30, 35):
        c = (x, y, 3)
        if c in m4 and m4[c] >= 0:
            print("   ", c, "way", m4[c], "then to 470's rear by proxy:", m0.get(c))
turn = None
n = 0
print("turn 5 events of 470:")
for s in b.L:
    if s.startswith("[AISTATE] aistart"):
        turn = int(kv(s)["turn"])
    if turn == 5:
        if s.startswith("[AIEVENT]") and "what=reaction unit=470" in s:
            n += 1
            print("   reaction", n, s[8:80])
        if s.startswith("[AICASUALTY]") and ("killer=470" in s or "victim=470" in s):
            print("   ", s[:150])
print("casualties of the two:")
for c in b.casualties:
    if c.get("victim") in ("1000005", "1000000") and c.get("how") == "dead":
        print("   ", {k: c.get(k) for k in ("turn", "victim", "killer", "weapon", "dist", "pos")})
print("1000005 state by turn:", [(t, b.state.get(t, {}).get("1000005", {}).get("hp")) for t in range(3, 9)])
print("1000000 state by turn:", [(t, b.state.get(t, {}).get("1000000", {}).get("hp"), b.state.get(t, {}).get("1000000", {}).get("seenby")) for t in range(3, 7)])
print("470 acts sample:")
for s in b.L:
    if s.startswith("[AICAND] acts=") and "unit=470" in s:
        print("  ", s[:40])
        import json
        L = json.loads(s.split(" list=", 1)[1])
        print("  ", sorted({(a["w"], a["t"], a["tu"]) for a in L if a.get("k") == "a"})[:8])
        break
