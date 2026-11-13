"""OPERATIONAL INTELLIGENCE: final check of episode E1 from the D0 log: every kill by tank 470, who killed it, every player unit's distance from the staging cell at aistart t4 and t5, the nearest known target there, the order of the first decisions of the AI side on t5, the shots of the Chryssalids' own ammo fields, the way lists of both at t4 towards 470's cell of t4. Read only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oilib import Battle, moves_of, pos  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
b = Battle("scpa_D_M3_s1")
print("kills by 470:", [(c["turn"], c["victim"], c.get("type"), c.get("pos"), c.get("dist"), c.get("weapon")) for c in b.casualties if c.get("killer") == "470" and c.get("how") == "dead"])
print("470 dead:", [(c["turn"], c.get("killer"), c.get("ktype"), c.get("weapon"), c.get("dist"), c.get("pos")) for c in b.casualties if c.get("victim") == "470" and c.get("how") == "dead"])
PL = ["444", "448", "470", "545", "454", "503", "520", "543"]
for t, cell in ((4, (45, 32, 3)), (5, (45, 32, 3))):
    st = b.state[t]
    r = []
    for u in PL:
        if u in st and int(st[u].get("status", 0)) < 6:
            p = pos(st[u]["pos"])
            r.append((max(abs(p[0] - cell[0]), abs(p[1] - cell[1])), u, st[u]["pos"], "spotted", st[u].get("spotted"), "seenby", st[u].get("seenby")))
    print("t", t, "player's units from staging cell", cell, sorted(r))
print("order of AI side's first decisions, turn 5:", [d["unit"] for d in b.decisions if d["turn"] == "5"][:12])
print("order, turn 4:", [d["unit"] for d in b.decisions if d["turn"] == "4"][:12])
tp = pos(b.state[4]["470"]["pos"])
near = [(tp[0] + x, tp[1] + y, tp[2]) for x in range(-1, 3) for y in range(-1, 3) if not (x in (0, 1) and y in (0, 1))]
for u in ("1000000", "1000005"):
    d = next(d for d in b.decisions if d["unit"] == u and d["turn"] == "4")
    m = moves_of(d)
    print(u, "t4 from", d["from"], "tu", d["tu"], "way to cells next to 470 of t4:", sorted(m[c] for c in near if c in m and m[c] >= 0))
print("first state fields of 1000005:", {k: v for k, v in b.units.get("1000005", {}).items()})
for s in b.L:
    if "unit=1000013" in s and ("ammo=" in s):
        print("sample with ammo:", s[:260])
        break
