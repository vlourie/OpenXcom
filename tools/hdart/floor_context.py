#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Где лежит пол: опознание кадра пола по его месту на картах, а не по пикселям.

Vitali 27.09 про пробу полов: «пол может быть в джунглях, может быть на улице, а снаружи может быть
крыша - надо сравнивать с объектами на карте, чтобы понять, какой пол нужен». Кадр 32x40 сам этого
не говорит: каменная мостовая MUJUNGLE_2 39 - то ли тропа, то ли вершина пирамиды.

По каждому кадру пола (часть 0) на всех картах всех террейнов, где стоит его набор, считается:
    этаж        z и что под клеткой: земля (z=0 или пусто внизу) или постройка (внизу стена/предмет/пол);
    крыша       есть ли пол этажом выше - под крышей (внутри) или под небом;
    стены       сколько стен в клетке и у соседей - в комнате или на открытом месте;
    на нём      что стоит в клетке (часть 3) - по описаниям кадров;
    рядом       полы-соседи и стены-соседи по описаниям.
И вырезы карт: клетка в рамке, всё выше её этажа срезано, как в игре. Ничего не рисует,
видеокарта не нужна.

    py -3.13 tools/hdart/floor_context.py --terrain JUNGLETEMPLE_2 --block MUJUNGLE14 ^
        --hints art/maps/paint/hints_MUJUNGLE.json

Кладёт в art/floor_context/<карта>/: context.tsv (utf-8-sig), sheet.png (кадр x4 | вырезы карт |
сводка латиницей: у шрифта PIL нет кириллицы).
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image, ImageDraw                    # noqa: E402

import map_mockup as mm                             # noqa: E402
import map_paint as mp_                             # noqa: E402
import pck_census as pc                             # noqa: E402

ENC = "utf-8-sig"
ROLE_EN = {"ground": "ground (z0)", "upper": "upper storey over building", "roof": "roof (open sky, building below)",
           "indoor": "indoor (floor above)"}


def cell_keys(world, terrain, block):
    """{(x, y, z): [ключ части 0..3 или None]} - ключ (НАБОР, кадр)."""
    sets = world.sets_of(terrain)
    sizes = {s: len(world.records(s)) for s in sets}
    sx, sy, sz, cells = mm.read_block(world, block)
    out = {}
    for pos, cell in cells.items():
        keys = []
        for part in range(4):
            v = cell[part]
            key = None
            if v:
                s, rec = pc.resolve(v, sets, sizes)
                if s is not None:
                    key = (s.upper(), world.records(s)[rec]["frame"])
            keys.append(key)
        if any(keys):
            out[pos] = keys
    return (sx, sy, sz), out


def role_of(cells, x, y, z):
    below = cells.get((x, y, z - 1)) if z > 0 else None
    above = cells.get((x, y, z + 1))
    covered = bool(above and above[0])
    if z == 0 or not below or not any(below):
        # на нижнем этаже - земля; выше - пол над пустотой (мостик, край) считаем землёй этажа
        return "indoor" if covered else "ground"
    if covered:
        return "indoor"
    return "roof" if (below[1] or below[2] or below[3]) else "upper"


def walls_near(cells, x, y, z):
    """Стены, ограничивающие клетку: свои западная/северная и соседские с востока/юга."""
    n = 0
    own = cells.get((x, y, z)) or [None] * 4
    n += bool(own[1]) + bool(own[2])
    e = cells.get((x + 1, y, z))
    s = cells.get((x, y + 1, z))
    n += bool(e and e[1]) + bool(s and s[2])
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--terrain", default="JUNGLETEMPLE_2")
    ap.add_argument("--block", default="MUJUNGLE14", help="полы этой карты; места ищутся по всем картам")
    ap.add_argument("--hints", default="art/maps/paint/hints_MUJUNGLE.json")
    ap.add_argument("--out", default="art/floor_context")
    ap.add_argument("--crops", type=int, default=3, help="вырезов на кадр (разные места)")
    ap.add_argument("--radius", type=int, default=5, help="клеток вокруг в вырезе")
    args = ap.parse_args()

    with open(args.hints, encoding=ENC) as f:
        hints = json.load(f)
    world = mm.World()

    def hint(k):
        return hints.get("%s:%d" % k, "") if k else ""

    _dims, here = cell_keys(world, args.terrain, args.block)
    floors = Counter(v[0] for v in here.values() if v[0])
    sets = {s for s, _f in floors}
    # все террейны, где стоит хоть один набор этих полов, и все их карты
    terrains = [t for t in world.terrains if sets & {s.upper() for s in world.sets_of(t)}]
    print("полов на карте %s: %d; террейнов с их наборами: %d" % (args.block, len(floors), len(terrains)),
          flush=True)

    stats = defaultdict(lambda: {"n": 0, "role": Counter(), "walls": Counter(), "on": Counter(),
                                 "near": Counter(), "maps": Counter(), "places": []})
    for t in terrains:
        for b in world.blocks_of(t):
            try:
                _d, cells = cell_keys(world, t, b)
            except (SystemExit, Exception):             # noqa: BLE001  нет файла карты - мимо
                continue
            for (x, y, z), keys in cells.items():
                k = keys[0]
                if k not in floors:
                    continue
                st = stats[k]
                st["n"] += 1
                role = role_of(cells, x, y, z)
                st["role"][role] += 1
                w = walls_near(cells, x, y, z)
                st["walls"]["room" if w >= 2 else "wall" if w == 1 else "open"] += 1
                if keys[3]:
                    st["on"][keys[3]] += 1
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nb = cells.get((x + dx, y + dy, z))
                    if nb and nb[0] and nb[0] != k:
                        st["near"][nb[0]] += 1
                    for part in (1, 2, 3):
                        if nb and nb[part]:
                            st["near"][nb[part]] += 1
                st["maps"]["%s/%s" % (t, b)] += 1
                st["places"].append((t, b, x, y, z, role))

    out_dir = os.path.join(args.out, args.block)
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    lines = ["кадр\tописание\tклеток\tкарт\tместо\tстены\tна нём\tрядом\tкарты"]
    for k, _c in floors.most_common():
        st = stats[k]
        n = max(1, st["n"])
        role = ", ".join("%s %d%%" % (r, 100 * c // n) for r, c in st["role"].most_common())
        walls = ", ".join("%s %d%%" % (r, 100 * c // n) for r, c in st["walls"].most_common())
        on = "; ".join("%s %d: %s (%d)" % (kk[0], kk[1], hint(kk)[:50], c) for kk, c in st["on"].most_common(4))
        near = "; ".join("%s %d: %s (%d)" % (kk[0], kk[1], hint(kk)[:50], c) for kk, c in st["near"].most_common(5))
        maps = ", ".join("%s (%d)" % (m, c) for m, c in st["maps"].most_common(5))
        lines.append("%s %d\t%s\t%d\t%d\t%s\t%s\t%s\t%s\t%s" % (k[0], k[1], hint(k), st["n"], len(st["maps"]),
                                                               role, walls, on, near, maps))
        print("%s %d: %d клеток на %d картах | %s | %s" % (k[0], k[1], st["n"], len(st["maps"]), role, walls),
              flush=True)

        # вырезы: по одному месту на каждую роль, потом самые частые карты
        picks, seen = [], set()
        for p in st["places"]:
            key = (p[5], p[1])
            if p[5] not in {q[5] for q in picks} and key not in seen:
                picks.append(p)
                seen.add(key)
        for p in st["places"]:
            if len(picks) >= args.crops:
                break
            if p[1] not in {q[1] for q in picks}:
                picks.append(p)
        crops = []
        for t, b, x, y, z, r in picks[:args.crops]:
            try:
                im, _m = mm.render(world, t, b, None, 1, None, maxz=z)
            except (SystemExit, Exception):             # noqa: BLE001
                continue
            _sx, sy, sz, _c = mm.read_block(world, b)
            px = sy * 16 + (x - y) * 16
            py = sz * 24 + 8 + (x + y) * 8 - z * 24
            rw, rh = 32 * args.radius // 2 + 32, 16 * args.radius // 2 + 60
            box = (max(0, px + 16 - rw), max(0, py + 32 - rh), min(im.width, px + 16 + rw),
                   min(im.height, py + 32 + rh))
            c = im.crop(box).convert("RGB")
            c = c.resize((c.width * 2, c.height * 2), Image.NEAREST)
            d = ImageDraw.Draw(c)
            ax, ay = (px - box[0]) * 2, (py - box[1]) * 2
            d.polygon([(ax + 32, ay + 48), (ax + 64, ay + 64), (ax + 32, ay + 80), (ax, ay + 64)],
                      outline=(255, 40, 40), width=3)
            crops.append(mm.label(c, "%s z%d %s" % (b, z, ROLE_EN[r])) if hasattr(mm, "label") else c)
        spr = world.sprite(k[0], k[1], None)
        tile = Image.new("RGB", (128, 160), (24, 20, 18))
        tile.paste(spr.resize((128, 160), Image.NEAREST), (0, 0), spr.resize((128, 160), Image.NEAREST))
        text = ["%s %d  cells %d, maps %d" % (k[0], k[1], st["n"], len(st["maps"])),
                "place: " + ", ".join("%s %d%%" % (ROLE_EN[r], 100 * c // n) for r, c in st["role"].most_common()),
                "walls: " + walls,
                "hint: " + hint(k)[:90]]
        rows.append((tile, crops, text))

    tsv = os.path.join(out_dir, "context.tsv")
    with open(tsv, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    # лист: строка на кадр
    rh = max(max([c.height for c in cr] + [160]) for _t, cr, _x in rows) + 70
    rw = max(128 + 8 + sum(c.width + 8 for c in cr) for _t, cr, _x in rows)
    board = Image.new("RGB", (rw, rh * len(rows)), (32, 32, 36))
    d = ImageDraw.Draw(board)
    for i, (tile, crops, text) in enumerate(rows):
        y = i * rh
        board.paste(tile, (0, y))
        x = 136
        for c in crops:
            board.paste(c, (x, y))
            x += c.width + 8
        for j, t in enumerate(text):
            d.text((4, y + rh - 66 + j * 15), t, fill=(230, 230, 120))
    board.save(os.path.join(out_dir, "sheet.png"))
    print("ЛИСТ %s\nсводка %s" % (os.path.join(out_dir, "sheet.png"), tsv), flush=True)


if __name__ == "__main__":
    main()
