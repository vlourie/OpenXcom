#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Кабины кораблей и машин - кандидаты для cockpit_pilot.py (Vitali 20.10: «s7302 Идеально»).

Цветом по всем наборам кабины не найти (R-407: синий корпус - тысячи ложных кадров). Поэтому от карты:
корабли и машины игрока из рулсетов (crafts.*.battlescapeTerrainData), их блоки, кадры стен и объектов
этих блоков; в HD-кадре игры стекло ищет glass_alpha.object_mask. На листе - корабль целиком (HD-пак) и
кандидаты с маской пурпуром: выбирает человек, в cockpit_pilot идёт только выбранное.

Пишет art/_review/glass/cockpit/census/craft_NN.png и candidates.tsv. Модель не грузит.

    python tools/hdart/cockpit_census.py
"""
import csv
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import glass_alpha as ga  # noqa: E402
import map_mockup as mm  # noqa: E402
import pck_census as pc  # noqa: E402

OUT = os.path.join(ga.REVIEW, "cockpit", "census")
VALUES = os.path.join(".index", "mod", "Piratez", "rul", "values.tsv")
LEAST = 60      # пикселей стекла в кадре, меньше - огонёк, не окно
PER_CRAFT = 8
PER_SHEET = 5
ROW_H = 260


def crafts():
    csv.field_size_limit(1 << 28)
    out = {}
    with open(VALUES, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row["section"] == "crafts" and row["field"] == "battlescapeTerrainData":
                try:
                    out[row["id"]] = json.loads(row["value"])
                except ValueError:
                    pass
    return out


def main():
    os.chdir(ga.ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    world = mm.World()
    game = os.path.join(ga.GAME, "TERRAIN")
    os.makedirs(OUT, exist_ok=True)
    rows, seen_block = [], set()
    for craft, td in sorted(crafts().items()):
        name = td.get("name")
        blocks = [b["name"] for b in td.get("mapBlocks") or [] if isinstance(b, dict) and b.get("name")]
        if not name or not blocks:
            continue
        world.terrains.setdefault(name, td)
        sets = world.sets_of(name)
        sizes = {s: len(world.records(s)) for s in sets}
        for block in blocks:
            if (name, block) in seen_block:
                continue
            seen_block.add((name, block))
            try:
                sx, sy, sz, cells = mm.read_block(world, block)
            except SystemExit:
                continue
            frames = {}
            for cell in cells.values():
                for part in (1, 2, 3):
                    if not cell[part]:
                        continue
                    s, rec = pc.resolve(cell[part], sets, sizes)
                    if s is None:
                        continue
                    key = (s.upper(), world.records(s)[rec]["frame"])
                    frames[key] = frames.get(key, 0) + 1
            cand = []
            for (s, f), places in frames.items():
                p = os.path.join(game, s + ".PCK", "%d.png" % f)
                if not os.path.exists(p):
                    continue
                hd = np.array(Image.open(p).convert("RGBA"))
                g, _lum = ga.object_mask(hd)
                # фиолетовые полосы и огни красных кораблей проходят «синий выше красного»; стекло - нет:
                # у голубого и синего стекла зелёный не ниже красного
                rgb = hd[..., :3].astype(np.int32)
                g &= rgb[..., 1] >= rgb[..., 0]
                g = ga.big_parts(g, ga.OBJ_PART)
                if g.sum() >= LEAST:
                    cand.append((int(g.sum()), s, f, places, hd, g))
            if not cand:
                continue
            cand.sort(key=lambda c: -c[0])
            img, _ = mm.render(world, name, block, game, k=1)
            rows.append((craft, name, block, img, cand[:PER_CRAFT]))
            print("%s %s/%s: кандидатов %d" % (craft, name, block, len(cand)), flush=True)
    with open(os.path.join(OUT, "candidates.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["лист", "корабль", "террейн", "блок", "кадр", "пикселей", "мест"])
        for i, (craft, name, block, _img, cand) in enumerate(rows):
            for n, s, f, places, _hd, _g in cand:
                w.writerow([i // PER_SHEET + 1, craft, name, block, "%s:%d" % (s, f), n, places])
    for sh in range(0, len(rows), PER_SHEET):
        part = rows[sh:sh + PER_SHEET]
        width = 0
        tiles = []
        for craft, name, block, img, cand in part:
            sc = ROW_H / float(img.height)
            craft_im = img.resize((max(1, int(img.width * sc)), ROW_H), Image.LANCZOS)
            row = [craft_im]
            for n, s, f, places, hd, g in cand:
                t = ga.over(hd, ga.checker(hd.shape[1], hd.shape[0]))
                t[g] = (t[g] * 0.4 + np.array([255, 0, 255]) * 0.6).astype(np.uint8)
                row.append(Image.fromarray(t))
            tiles.append((craft, name, block, row, cand))
            width = max(width, sum(im.width + 6 for im in row))
        sheet = Image.new("RGB", (width, len(part) * (ROW_H + 40)), (16, 16, 16))
        d = ImageDraw.Draw(sheet)
        for r, (craft, name, block, row, cand) in enumerate(tiles):
            y = r * (ROW_H + 40)
            d.text((4, y + 4), "%s  %s/%s" % (craft, name, block), fill=(240, 240, 240))
            x = 0
            for i, im in enumerate(row):
                sheet.paste(im.convert("RGB"), (x, y + 20))
                if i:
                    n, s, f = cand[i - 1][:3]
                    d.text((x + 2, y + 20 + im.height + 2), "%s:%d %d" % (s, f, n), fill=(230, 230, 120))
                x += im.width + 6
        p = os.path.join(OUT, "craft_%02d.png" % (sh // PER_SHEET + 1))
        sheet.save(p)
        print("лист:", p, flush=True)
    print("кораблей с кандидатами:", len(rows))


if __name__ == "__main__":
    main()
