#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Листы проверки предметов: оригинал x4 | пак, который стоит в игре | наши варианты - по предмету.

Предмет берётся из очереди obj_queue (items.json): составной показывается собранным целиком, как он
стоит на карте, анимация - первым кадром. Кадр, которого в очереди нет, показывается один.
Всё в размере игры (k=4) на тёмном полу боя, без уменьшения - качество судится в полный рост (R-088).
Числа охвата силуэта (cover_check, R-116) - только отсев явного брака: красная подпись.

Варианты - папки вида <имя>=<путь>, внутри <НАБОР>.PCK/<кадр>.png; порядок = старшинство
(первый найденный вариант предлагается к установке). Пишет в --out:
  sheet_NN.png - листы; review.tsv - строка на предмет: номер на листе, ключи, какие варианты есть,
  флаги брака, столбец «берём» (заполняется при проверке: имя варианта или пусто).

    py -3.13 tools/hdart/obj_review.py --out art/_review/ours_vs_pack ^
        --cand photo=art/objects/photo_cap2 --cand photo=art/objects/photo ...
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

from PIL import Image, ImageDraw, ImageFont       # noqa: E402

import map_mockup as mm                           # noqa: E402

ENC = "utf-8-sig"
GAME_HD = "Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN"
FONT = "Пиратки/Dioxine_XPiratez/user/mods/hd/hd/UI/FontSmall.ttf"
FLOOR = (24, 20, 18)
K = 4
LABEL = 26
GAP = 10


def key_of(s):
    name, fr = s.rsplit(":", 1)
    return name.upper(), int(fr)


def load_cover(path):
    out = {}
    if os.path.exists(path):
        with open(path, encoding=ENC) as f:
            for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                out[r["кадр"].upper()] = (float(r["cover"]), float(r["spill"]), float(r["semi"]))
    return out


def frame_file(root, key):
    p = os.path.join(root, key[0] + ".PCK", "%d.png" % key[1])
    return p if os.path.exists(p) else None


def compose(frames, at):
    """Куски в одну картинку по местам layout (x, y) - как их рисует игра; кадр None - пропуск."""
    x0 = min(x for x, _y, _z in at)
    y0 = min(y for _x, y, _z in at)
    w = max(x for x, _y, _z in at) - x0 + 32
    h = max(y for _x, y, _z in at) - y0 + 40
    im = Image.new("RGBA", (w * K, h * K), FLOOR + (255,))
    for f, (x, y, _z) in zip(frames, at):
        if f is not None:
            im.alpha_composite(f.convert("RGBA").resize((32 * K, 40 * K), Image.NEAREST)
                               if f.width == 32 else f.convert("RGBA"), ((x - x0) * K, (y - y0) * K))
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default="art/objects/queue/items.json")
    ap.add_argument("--cand", action="append", default=[], help="имя=папка, можно несколько")
    ap.add_argument("--cover", default="art/objects/cover.tsv")
    ap.add_argument("--out", default="art/_review/ours_vs_pack")
    ap.add_argument("--width", type=int, default=2600)
    ap.add_argument("--height", type=int, default=2400)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cands = [c.split("=", 1) for c in a.cand]
    world = mm.World()
    cover = load_cover(a.cover)
    font = ImageFont.truetype(FONT, 18)

    with open(a.items, encoding=ENC) as f:
        items = json.load(f)
    seen, todo = set(), []
    for it in items:
        keys = [key_of(k) for k in it["keys"]]
        frames = [key_of(k) for k in it["frames"]]
        if it["kind"] == "анимация":
            keys = frames[:1]
        have = [n for n, root in cands if any(frame_file(root, k) for k in keys)]
        if have:
            todo.append((it, keys))
            seen |= set(frames) | set(keys)
    # кадры вариантов, которых нет в очереди (обломки, массивы) - по одному
    extra = set()
    for _n, root in cands:
        for d in os.listdir(root) if os.path.isdir(root) else []:
            if d.endswith(".PCK"):
                for fn in os.listdir(os.path.join(root, d)):
                    if fn.endswith(".png") and fn[:-4].isdigit():
                        k = (d[:-4].upper(), int(fn[:-4]))
                        if k not in seen:
                            extra.add(k)
    for k in sorted(extra):
        todo.append(({"rank": 0, "kind": "вне очереди", "keys": ["%s:%d" % k], "at": [[0, 0, 0]],
                      "places": 0}, [k]))

    panels, rows = [], []
    for n, (it, keys) in enumerate(todo, 1):
        at = it["at"] if it["kind"] == "составной" and len(it["at"]) == len(keys) else [[0, 0, 0]] * len(keys)
        if len(keys) > 1 and at == [[0, 0, 0]] * len(keys):
            keys = keys[:1]
            at = [[0, 0, 0]]
        orig = compose([world.sprite(k[0], k[1], None) for k in keys], at)
        pack_f = [Image.open(p) if p else None for p in (frame_file(GAME_HD, k) for k in keys)]
        pack = compose(pack_f, at)
        cols = [("original x4", orig), ("pack in game" if any(pack_f) else "pack: none", pack)]
        have = []
        for name, root in cands:
            fs = [frame_file(root, k) for k in keys]
            if any(fs) and name not in have:
                have.append(name)
                cols.append((name + ("" if all(fs) else " (part)"),
                             compose([Image.open(p) if p else None for p in fs], at)))
        flags = []
        for k in keys:
            c = cover.get("%s:%d" % k)
            if c and (c[0] < 0.85 or c[1] > 0.15):
                flags.append("cover %.2f spill %.2f" % (c[0], c[1]))
        w = sum(im.width for _t, im in cols) + GAP * (len(cols) - 1)
        h = max(im.height for _t, im in cols) + LABEL * 2
        p = Image.new("RGB", (w, h), (40, 40, 44))
        d = ImageDraw.Draw(p)
        title = "#%d  %s  %s  q%d x%d" % (n, it["kind"], " ".join("%s:%d" % k for k in keys)[:60],
                                          it.get("rank", 0), it.get("places", 0))
        d.text((4, 3), title, fill=(255, 230, 120), font=font)
        x = 0
        for t, im in cols:
            p.paste(im.convert("RGB"), (x, LABEL * 2))
            d.text((x + 4, LABEL + 2), t, fill=(200, 200, 200), font=font)
            x += im.width + GAP
        if flags:
            d.text((w - 330, 3), flags[0], fill=(255, 80, 80), font=font)
        panels.append(p)
        rows.append([n, it.get("rank", 0), it["kind"], it.get("places", 0),
                     " ".join("%s:%d" % k for k in keys), ",".join(have), "; ".join(flags), ""])

    # раскладка панелей по листам построчно
    sheet_no, x, y, rowh, sheet, placed = 1, 0, 0, 0, None, []

    def flush():
        nonlocal sheet
        if sheet is not None:
            sheet.crop((0, 0, a.width, min(a.height, y + rowh))).save(
                os.path.join(a.out, "sheet_%02d.png" % sheet_no))
        sheet = None

    for i, p in enumerate(panels):
        if sheet is None:
            sheet = Image.new("RGB", (a.width, a.height), (18, 18, 20))
            x = y = rowh = 0
        if x and x + p.width > a.width:
            x, y, rowh = 0, y + rowh + GAP * 2, 0
        if y + p.height > a.height and (x or y):
            flush()
            sheet_no += 1
            sheet = Image.new("RGB", (a.width, a.height), (18, 18, 20))
            x = y = rowh = 0
        sheet.paste(p, (x, y))
        placed.append(sheet_no)
        x += p.width + GAP * 3
        rowh = max(rowh, p.height)
    flush()
    with open(os.path.join(a.out, "review.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("\t".join(["номер", "очередь", "вид", "мест", "ключи", "варианты", "брак", "лист", "берём"]) + "\n")
        for r, s in zip(rows, placed):
            f.write("\t".join(str(v) for v in r[:7] + [s, r[7]]) + "\n")
    print("предметов на проверку %d, листов %d -> %s" % (len(rows), sheet_no, a.out))


if __name__ == "__main__":
    main()
