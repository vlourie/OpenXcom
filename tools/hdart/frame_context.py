#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""frame_context.py - кадр террейна в классической сборке целых сооружений, для опознания (R-071, R-245).

Кадр 32x40 сам по себе назначение не доказывает. Здесь он показан там, где стоит:
  * сводка по блокам: этаж и часть клетки, что этажом ниже, что над ним, соседи на том же этаже;
  * лист блока в классике целиком (все этажи) с рамками на клетках кадра;
  * тот же блок со срезом под этажом кадра - что он накрывает;
  * вырез x4 вокруг первой клетки кадра - как узор сходится с соседними копиями.

Блок читается тем террейном, в котором его считала перепись (map_mockup.usage), а не первым по
алфавиту: URBAN05 есть и в SUNKURBAN с другими наборами.

    py -3.13 tools/hdart/frame_context.py URBAN:52 --blocks 6
Выход: census/maps/pilot2/identity/<НАБОР>_<кадр>/ (summary.txt, <блок>.png, sheet.png).
"""
import argparse
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image, ImageDraw, ImageFont             # noqa: E402

import map_mockup as mm                                 # noqa: E402
import pck_census as pc                                 # noqa: E402

ENC = "utf-8-sig"
PART = ("пол", "стена З", "стена С", "объект")
FONT = "C:/Windows/Fonts/arial.ttf"


def label(im, text):
    """Подпись сверху; шрифт с кириллицей (у map_mockup.label шрифт по умолчанию её не знает)."""
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, im.width, 20), fill=(20, 20, 24))
    d.text((6, 2), text, fill=(255, 220, 0), font=ImageFont.truetype(FONT, 14))
    return im


def resolved(w, terrain, block):
    sets = w.sets_of(terrain)
    sizes = {s: len(w.records(s)) for s in sets}
    sx, sy, sz, cells = mm.read_block(w, block)
    out = {}
    for key, cell in cells.items():
        row = []
        for p in range(4):
            v = cell[p]
            s, rec = pc.resolve(v, sets, sizes) if v else (None, None)
            row.append(None if s is None else "%s:%d" % (s.upper(), w.records(s)[rec]["frame"]))
        out[key] = row
    return sx, sy, sz, out


def summary(w, key, terrain, block):
    sx, sy, sz, cells = resolved(w, terrain, block)
    hits = [(k, row.index(key)) for k, row in cells.items() if key in row]
    levels = Counter((k[2], PART[p]) for k, p in hits)
    below, above, side = Counter(), Counter(), Counter()
    for (x, y, z), _p in hits:
        b = cells.get((x, y, z - 1))
        below[b[0] if b else None] += 1
        a = cells.get((x, y, z + 1))
        above[" + ".join(v for v in a if v) if a and any(a) else "пусто"] += 1
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = cells.get((x + dx, y + dy, z))
            if n is None:
                side["край блока"] += 1
            elif key not in n:
                side[" + ".join(v for v in n if v) or "пусто"] += 1
    lines = ["== %s (%s) %dx%dx%d, клеток с кадром %d" % (block, terrain, sx, sy, sz, len(hits)),
             "   этаж (0 - земля) и часть: " + ", ".join("%d %s: %d" % (z, p, n) for (z, p), n in sorted(levels.items())),
             "   пол этажом ниже: " + ", ".join("%s %d" % kv for kv in below.most_common(8)),
             "   над клеткой: " + ", ".join("%s %d" % kv for kv in above.most_common(5)),
             "   соседи на этаже: " + ", ".join("%s %d" % kv for kv in side.most_common(8))]
    return lines, (min(z for (_x, _y, z), _p in hits) if hits else None)


def framed(w, terrain, block, mark, maxz, k=2):
    im, marks = mm.render(w, terrain, block, None, 1, mark, maxz=maxz)
    im = im.resize((im.width * k, im.height * k), Image.NEAREST).convert("RGB")
    d = ImageDraw.Draw(im)
    for _s, _f, r, z in marks:
        if maxz is None or z <= maxz:
            # ромб клетки внизу кадра 32x40 (строки 24..40), а не весь прямоугольник кадра
            x0, y0 = r[0], r[1]
            d.polygon([((x0 + 16) * k, (y0 + 24) * k), ((x0 + 32) * k, (y0 + 32) * k),
                       ((x0 + 16) * k, (y0 + 40) * k), (x0 * k, (y0 + 32) * k)], outline=(255, 40, 40))
    return im, marks


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("frame", help="НАБОР:кадр")
    ap.add_argument("--blocks", type=int, default=6, help="сколько блоков показать (самые ходовые, без копий)")
    ap.add_argument("--pick", help="блоки для листов через запятую (вместо самых ходовых: у копий блока лист один и тот же)")
    args = ap.parse_args(argv)
    os.chdir(ROOT)
    s, f = mm.parse_frame(args.frame)
    key = "%s:%d" % (s, f)
    w = mm.World()
    rows = sorted(mm.usage(w).get(key, []), key=lambda r: -r[2])
    out = os.path.join(ROOT, "census", "maps", "pilot2", "identity", "%s_%d" % (s, f))
    os.makedirs(out, exist_ok=True)
    text = ["%s: блоков %d, клеток %d" % (key, len(rows), sum(r[2] for r in rows))]
    seen, picks = set(), []
    for t, b, n in rows:
        if b in seen:
            continue
        seen.add(b)
        lines, z = summary(w, key, t, b)
        text += lines
        wanted = (b in args.pick.split(",")) if args.pick else len(picks) < args.blocks
        if wanted and z is not None:
            picks.append((t, b, z))
    tiles = []
    for t, b, z in picks:
        full, marks = framed(w, t, b, (s, f), None)
        under, _ = framed(w, t, b, (s, f), z - 1) if z > 0 else (None, None)
        # вырез x4 вокруг первой клетки кадра, срез по его этажу
        im1, m1 = mm.render(w, t, b, None, 1, (s, f), maxz=z)
        x0, y0, x1, y1 = m1[0][2]
        box = (max(0, x0 - 64), max(0, y0 - 40), min(im1.width, x1 + 64), min(im1.height, y1 + 40))
        zoom = im1.crop(box).resize(((box[2] - box[0]) * 4, (box[3] - box[1]) * 4), Image.NEAREST).convert("RGB")
        parts = [label(full, "%s / %s: целиком, красное - %s" % (t, b, key))]
        if under is not None:
            parts.append(label(under, "срез под этажом %d - что накрывает %s" % (z, key)))
        parts.append(label(zoom, "x4 у клетки кадра, этаж %d" % z))
        hgt = max(p.height for p in parts)
        row = Image.new("RGB", (sum(p.width for p in parts) + 8 * len(parts), hgt), (20, 20, 24))
        x = 0
        for p in parts:
            row.paste(p, (x, 0))
            x += p.width + 8
        row.save(os.path.join(out, "%s.png" % b))
        tiles.append(row)
    sheet_w = max(t.width for t in tiles)
    sheet = Image.new("RGB", (sheet_w, sum(t.height + 8 for t in tiles)), (20, 20, 24))
    y = 0
    for t in tiles:
        sheet.paste(t, (0, y))
        y += t.height + 8
    if sheet.width > 3000:
        sheet = sheet.resize((3000, sheet.height * 3000 // sheet.width), Image.LANCZOS)
    sheet.save(os.path.join(out, "sheet.png"))
    with open(os.path.join(out, "summary.txt"), "w", encoding=ENC) as fh:
        fh.write("\n".join(text) + "\n")
    print("\n".join(text[:40]))
    print("листы:", out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
