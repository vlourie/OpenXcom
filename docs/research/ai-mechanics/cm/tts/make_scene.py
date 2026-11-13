"""TACTICAL TURN SOLVER: the controlled scene, a copy of a real battle save with real rules. Nothing of the engine, the weapons, TU or stats is changed:
only walls of the map's own solid block are laid on the floor, three units are put in the corridor, every other unit and its items are taken out.

      y=27           #
      y=28   # # # # . # # # # # # # # #      the niche (22,28), one cell, closed at the back
      y=29   # . B . A . . . . . . T #        the corridor, one wide: B (20,29), A (22,29), T (29,29)
      y=30   # # # # # # # # # # # # # #

A has the weak weapon, B the strong one, T the armor A hardly gets through. args: src out rng"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from save_lib import Save

sys.stdout.reconfigure(encoding="utf-8")
src, out, rng = sys.argv[1], sys.argv[2], sys.argv[3]
s = Save(src)

A, B, T = "1000012", "1000031", "115"  # DOOM_SOLDIER with STR_UAC_CARBINE, DOOM_GUNNER with STR_HEAVY_CANNON, soldier in STR_TAC_FULL_ARMOR_UC
Y, Z = 29, 0
X0, X1 = 18, 30  # end walls of the corridor
PLACE = {A: ((22, Y, Z), 2), B: ((20, Y, Z), 2), T: ((29, Y, Z), 6)}  # direction 2 is +x, 6 is -x (Pathfinding::directionToVector)
NICHE = (22, Y - 1, Z)
SOLID_SET, SOLID_ID = 15, 41  # C_EXT_XCOM: armor 100, all LOFT solid, big wall, stops sight (survey.py)

assert s.sets[SOLID_SET] == "C_EXT_XCOM"
tiles = s.tiles()


def clear(t):
    """no west wall, north wall, object on the tile; the floor stays"""
    t[0][1:4] = [-1, -1, -1]
    t[1][1:4] = [-1, -1, -1]


def solid(t):
    clear(t)
    t[0][3] = SOLID_ID
    t[1][3] = SOLID_SET


cells = [(x, Y, Z) for x in range(X0 + 1, X1)] + [NICHE]
for c in cells:
    t = tiles[s.pos(*c)]
    assert t[0][0] >= 0, ("no floor", c)
    clear(t)
    # nothing on the level above that would stop a line
    up = tiles.get(s.pos(c[0], c[1], c[2] + 1))  # an empty tile is not in the save at all (SavedBattleGame::save)
    assert up is None or all(v < 0 for v in up[0]), ("something above", c, up)


def wall(x, y, z):
    # a tile the save does not hold is empty: all four parts -1, no smoke, no fire, no flags
    t = tiles.setdefault(s.pos(x, y, z), ([-1, -1, -1, -1], [-1, -1, -1, -1], 0, 0, 0))
    solid(t)


for x in range(X0, X1 + 1):
    for y in (Y - 1, Y + 1):
        if (x, y, Z) != NICHE:
            wall(x, y, Z)
wall(X0, Y, Z)
wall(X1, Y, Z)
wall(NICHE[0], NICHE[1] - 1, Z)
# the sides of the niche are the corridor's wall cells (21,28) and (23,28); walls on the tiles past the corridor would change nothing
s.store_tiles(tiles)

# the units: three are kept
keep = set(PLACE)
drop_lines = set()
kept = {}
for r in s.records("units"):
    uid = s.field(r, "id")
    if uid in keep:
        kept[uid] = r
    else:
        drop_lines.update(range(*r))
assert set(kept) == keep, kept
for uid, r in kept.items():
    for i in range(*r):
        if re.match(r"^      position: ", s.L[i]):
            x, y, z = PLACE[uid][0]
            s.L[i] = f"      position: [{x},{y},{z}]"
        elif re.match(r"^      direction: ", s.L[i]):
            s.L[i] = f"      direction: {PLACE[uid][1]}"
        elif re.match(r"^      directionTurret: ", s.L[i]):
            s.L[i] = f"      directionTurret: {PLACE[uid][1]}"
        elif re.match(r"^      (lastPos|destination): ", s.L[i]):
            pass
# the items: of the kept units and the ammo loaded in them; everything else goes, the map's loose items too
items = s.records("items")
byid = {s.field(r, "id"): r for r in items}
keep_items = set()
for r in items:
    if s.field(r, "owner") in keep:
        keep_items.add(s.field(r, "id"))
        am = s.field(r, "ammoItem")
        if am and am != "-1":
            keep_items.add(am)
        sl = s.field(r, "ammoItemSlots")
        if sl:
            keep_items.update(v for v in re.findall(r"-?\d+", sl) if v != "-1" and v in byid)
for r in items:
    if s.field(r, "id") not in keep_items:
        drop_lines.update(range(*r))
# the special items (AUX_*) belong to their units: those of the units taken out go with them
special = s.records("itemsSpecial")
spec_keep = 0
for r in special:
    if s.field(r, "owner") in keep or s.field(r, "id") in keep_items:
        spec_keep += 1
    else:
        drop_lines.update(range(*r))
print("itemsSpecial kept", spec_keep, "of", len(special))
s.L[s.key["selectedUnit"]] = f"  selectedUnit: {A}"
# the seed of the battle: SavedGame::load takes it when newSeedOnLoad is off
n = next(i for i, x in enumerate(s.L) if x.startswith("rng: "))
s.L[n] = f"rng: {rng}"
s.L = [x for i, x in enumerate(s.L) if i not in drop_lines]
s.write(out)

# read the result back as the game would see it
c = Save(out)
print("units", [(c.field(r, "id"), c.field(r, "faction"), c.field(r, "position"), c.field(r, "direction"), c.field(r, "tu")) for r in c.records("units")])
for r in c.records("items"):
    print("item", c.field(r, "id"), c.field(r, "type"), "owner", c.field(r, "owner"), c.field(r, "inventoryslot"), "ammo", c.field(r, "ammoItem"))
T2 = c.tiles()
print("    " + "".join(str(x % 10) for x in range(X0 - 2, X1 + 3)))
for y in range(Y - 3, Y + 3):
    row = ""
    for x in range(X0 - 2, X1 + 3):
        t = T2.get(c.pos(x, y, Z), ([-1] * 4, [-1] * 4, 0, 0, 0))
        ch = "." if t[0][0] >= 0 else "_"
        if t[0][3] == SOLID_ID and t[1][3] == SOLID_SET:
            ch = "#"
        elif t[0][3] >= 0:
            ch = "o"
        elif t[0][1] >= 0 or t[0][2] >= 0:
            ch = "+"
        for uid, (p, _) in PLACE.items():
            if p == (x, y, Z):
                ch = {A: "A", B: "B", T: "T"}[uid]
        row += ch
    print(f"{y:3d} " + row)
print("written", out)
