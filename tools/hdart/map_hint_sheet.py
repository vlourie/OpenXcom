#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""map_hint_sheet.py - лист кадров, которые map_paint закажет модели на этой карте, и заготовка подсказок.

Подсказка на кадр обязательна (R-007) и пишется по оригиналу, а не по памяти (R-040). Лист
показывает ровно то, что пойдёт в работу: записи на карте, их фазы анимации (R-071), обломки
(Die_MCD) и открытые двери (Alt_MCD) по цепочке, кроме уже готового в --root. Одинаковые картинки
(census/frame_hash.tsv) показаны один раз - reuse_base возьмёт их из готового до байта.

Кадры увеличены ближайшим соседом - это ПРОСМОТР оригинала, в конвейер не идёт (R-004).
Фон - тёмный пол боя (R-041). Рядом json: {"НАБОР:кадр": подсказка}; где подсказки ещё нет, стоит
текст hints_for набора из прежнего конвейера с пометкой "?" - его проверить по листу и поправить.

    py -3 tools\hdart\map_hint_sheet.py --terrain CYDHANGAR --block SGR_TERMINAL_01 --root art\maps\paint\series
      -> art\maps\paint\hints\SGR_TERMINAL_01_NN.png и SGR_TERMINAL_01.draft.json
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image, ImageDraw                        # noqa: E402

import map_mockup as mm                                 # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("art", "maps", "paint", "hints")
BG = (18, 18, 20)
FLOOR = (38, 34, 30)
PART = {0: "floor", 1: "wall W", 2: "wall N", 3: "object"}      # шрифт листа без кириллицы
WHY = {"анимация": "anim", "обломки": "debris", "дверь": "door"}


def set_hints(S, cache={}):
    """Подсказки прежнего конвейера: art/TERRAIN/<НАБОР>.PCK/hints.json (gen_hd)."""
    if S not in cache:
        p = os.path.join("art", "TERRAIN", S + ".PCK", "hints.json")
        cache[S] = {}
        if os.path.exists(p):
            with open(p, encoding=ENC) as f:
                cache[S] = json.load(f)
    return cache[S]


def jobs_of(world, terrain, block):
    """[(набор, кадр, часть, клеток на карте, почему)] в порядке первого появления."""
    sets = world.sets_of(terrain)
    sizes = {s: len(world.records(s)) for s in sets}
    _sx, _sy, _sz, cells = mm.read_block(world, block)
    import pck_census as pc
    count, order = {}, []
    for cell in cells.values():
        for part, v in enumerate(cell):
            if not v:
                continue
            s, rec = pc.resolve(v, sets, sizes)
            if s is None:
                continue
            key = (s, rec)
            if key not in count:
                order.append((key, part))
                count[key] = 0
            count[key] += 1
    out, seen = [], set()
    for (s, rec), part in order:
        recs = world.records(s)
        chain = [(rec, "")]
        while chain:
            cur, why = chain.pop()
            r = recs[cur]
            for fa in dict.fromkeys(r["frames"]):
                if (s, fa) not in seen:
                    seen.add((s, fa))
                    out.append((s, fa, part, count.get((s, rec), 0) if not why else 0,
                                why or ("анимация" if fa != r["frame"] else "")))
            for nxt, w in ((r["die"], "обломки"), (r["alt"], "дверь")):
                if nxt and nxt < len(recs) and ("rec", s, nxt) not in seen:
                    seen.add(("rec", s, nxt))
                    chain.append((nxt, w))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--terrain", required=True)
    ap.add_argument("--block", required=True)
    ap.add_argument("--root", default="", help="общая папка клеток серии: готовое в ней не показывается")
    ap.add_argument("--hints", default="", help="уже написанные подсказки {НАБОР:кадр: текст}")
    ap.add_argument("--per", type=int, default=40, help="кадров на лист")
    args = ap.parse_args(argv)
    world = mm.World()
    import hints as hh
    hashes = {}
    with open(os.path.join("census", "frame_hash.tsv"), encoding=ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            hashes[(r["набор"].upper(), int(r["кадр"]))] = r["хэш"]
    known = {}
    if args.hints and os.path.exists(args.hints):
        with open(args.hints, encoding=ENC) as f:
            known = json.load(f)
    rows, pics, skipped = [], {}, {"готово": 0, "повтор": 0, "пусто": 0}
    for s, fr, part, n, why in jobs_of(world, args.terrain, args.block):
        S = s.upper()
        if args.root and os.path.exists(os.path.join(args.root, S + ".PCK", "%d.png" % fr)):
            skipped["готово"] += 1
            continue
        spr = world.sprite(s, fr, None)
        if spr is None or not spr.getbbox():
            skipped["пусто"] += 1
            continue
        h = hashes.get((S, fr))
        if h and h in pics:
            skipped["повтор"] += 1
            pics[h][3] += n
            continue
        row = [S, fr, part, n, why, spr]
        rows.append(row)
        if h:
            pics[h] = row
    os.makedirs(OUT, exist_ok=True)
    cols, cw, chh = 8, 32 * 4 + 12, 40 * 4 + 34
    for p0 in range(0, len(rows), args.per):
        part_rows = rows[p0:p0 + args.per]
        nr = (len(part_rows) + cols - 1) // cols
        im = Image.new("RGB", (cols * cw, nr * chh), BG)
        d = ImageDraw.Draw(im)
        for j, (S, fr, part, n, why, spr) in enumerate(part_rows):
            x, y = (j % cols) * cw + 6, (j // cols) * chh + 4
            tile = Image.new("RGBA", (128, 160), FLOOR + (255,))
            tile.alpha_composite(spr.resize((128, 160), Image.NEAREST))
            im.paste(tile.convert("RGB"), (x, y))
            d.text((x, y + 162), "%s:%d" % (S, fr), fill=(235, 220, 120))
            d.text((x, y + 174), "%s n=%d %s" % (PART.get(part, part), n, WHY.get(why, why)),
                   fill=(160, 160, 170))
        p = os.path.join(OUT, "%s_%02d.png" % (args.block, p0 // args.per + 1))
        im.save(p)
        print(p, im.size)
    draft = {}
    for S, fr, part, n, why, _spr in rows:
        key = "%s:%d" % (S, fr)
        if key in known:
            draft[key] = known[key]
        else:
            old = hh.hints_for(S + ".PCK").get(fr) or set_hints(S).get(str(fr))
            draft[key] = "? " + old if old else "?"
    p = os.path.join(OUT, "%s.draft.json" % args.block)
    with open(p, "w", encoding=ENC) as f:
        json.dump(draft, f, ensure_ascii=False, indent=1)
    print("кадров к рисованию %d; не показано: готово %d, повтор картинки %d, пустых %d -> %s"
          % (len(rows), skipped["готово"], skipped["повтор"], skipped["пусто"], p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
