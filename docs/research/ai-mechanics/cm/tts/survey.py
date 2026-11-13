"""TACTICAL TURN SOLVER: the units, their hands, and the map of one level of a battle save. args: save [z]"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from save_lib import Save, read_mcd, F_LOS, F_BIG, F_TUW, F_ARMOR, F_DOOR, F_UFO, F_NOFLOOR, F_LOFT

sys.stdout.reconfigure(encoding="utf-8")
s = Save(sys.argv[1])
z = int(sys.argv[2]) if len(sys.argv) > 2 else 0
print(s.w, s.l, s.h, s.sets, "bytes", s.bytes)
items = {}
for r in s.records("items"):
    o = s.field(r, "owner")
    if o:
        items.setdefault(o, []).append((s.field(r, "inventoryslot"), s.field(r, "type"), s.field(r, "id"), s.field(r, "ammoItem")))
for r in s.records("units"):
    st = s.field(r, "status")
    uid = s.field(r, "id")
    hands = [(a, b) for a, b, c, d in items.get(uid, []) if a in ("STR_RIGHT_HAND", "STR_LEFT_HAND")]
    if st == "0":
        print(uid, "f", s.field(r, "faction"), s.field(r, "position"), "tu", s.field(r, "tu"), "hp", s.field(r, "health"), s.field(r, "genUnitType"), s.field(r, "genUnitArmor"), "arm", s.field(r, "armor"), hands)
root = Path("E:/OpenXCom/Пиратки/Dioxine_XPiratez")
mcd = {}
for name in s.sets:
    hits = list(root.rglob(name + ".MCD"))
    mcd[name] = read_mcd(hits[0]) if hits else []
    print(name, hits[0] if hits else "NOT FOUND", len(mcd[name]))
T = s.tiles()


def part(t, k):
    if t[0][k] < 0 or t[1][k] < 0:
        return None
    m = mcd[s.sets[t[1][k]]]
    return m[t[0][k]] if t[0][k] < len(m) else None


print("    " + "".join(str(x // 10) for x in range(s.w)))
print("    " + "".join(str(x % 10) for x in range(s.w)))
for y in range(s.l):
    row = ""
    for x in range(s.w):
        t = T.get(s.pos(x, y, z))
        if not t:
            row += " "
            continue
        fl, wn, nw, ob = (part(t, k) for k in range(4))
        c = "."
        if fl is None:
            c = "_"
        if wn is not None or nw is not None:
            c = "|" if wn is not None and nw is None else ("-" if wn is None else "+")
        if ob is not None:
            c = "#" if ob[F_BIG] == 1 or ob[F_TUW] == 255 else "o"
        row += c
    print(f"{y:3d} " + row)
# the solid big-wall objects of this map, how many, their armor
cnt = {}
for i, t in T.items():
    ob = part(t, 3)
    if ob is not None and ob[F_BIG] == 1 and ob[F_TUW] == 255 and ob[F_LOS]:
        cnt[(t[1][3], t[0][3], ob[F_ARMOR], tuple(ob[F_LOFT:F_LOFT + 12]))] = cnt.get((t[1][3], t[0][3], ob[F_ARMOR], tuple(ob[F_LOFT:F_LOFT + 12])), 0) + 1
for k, v in sorted(cnt.items(), key=lambda x: -x[1])[:12]:
    print("solid", k, v)
