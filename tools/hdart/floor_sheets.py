# -*- coding: utf-8 -*-
r"""Контактные листы всех полов + таблица описаний, которую правит человек.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\floor_sheets.py --sheets art/TERRAIN --out floors_ru

Зачем: художнику важна не тема набора, а что нарисовано в конкретном кадре. У наборов Пираток
покадровых подсказок нет почти нигде (в логе «0 with hints»), и модель рисует что угодно - круги,
колёса, мох вместо травы. Подсказка на каждый пол это чинит.

Складывает:
  sheet_001.png ...  - листы по 24 пола: оригинальный кадр в 4x, подпись «НАБОР #кадр» и нынешняя
                       подсказка, если она есть;
  floors.tsv         - строка на пол: набор, кадр, лист, нынешняя подсказка, описание по-русски,
                       подсказка для художника (англ.). Две последние колонки заполняются людьми.

Потом `hints_apply.py` разносит колонку с английской подсказкой по `<набор>\hints.json`, откуда её
берёт gen_hd.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                   # noqa: E402
from PIL import Image, ImageDraw     # noqa: E402
import xcom_sprites as xs            # noqa: E402
from hints import hints_for          # noqa: E402

ENC = "utf-8-sig"


def floors_of(set_dir, info):
    """[(кадр, площадь)] ровных полов набора."""
    count, fw, fh = info["count"], info["frame_w"], info["frame_h"]
    types = info.get("types") or [-1] * count
    ground = info.get("ground") or [False] * count
    sheet = xs.Sheet(fw, fh, count, info["columns"], info["margin"])
    original = Image.open(os.path.join(set_dir, "original.png")).convert("RGBA")
    out = []
    for i in range(count):
        if types[i] != xs.MCD_FLOOR or not ground[i]:
            continue
        frame = sheet.cut(original, i, 1)
        box = frame.getbbox()
        if box is None or box[1] < fh - 16 - 6:
            continue
        area = float(np.asarray(frame.split()[3], np.float64).sum()) / 255.0
        out.append((i, area, frame))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="листы полов и таблица описаний")
    ap.add_argument("--sheets", required=True)
    ap.add_argument("--out", default="art/_review/floors_ru")
    ap.add_argument("--sets", default="", help="только эти наборы, через запятую")
    ap.add_argument("--per-sheet", type=int, default=24, dest="per_sheet")
    ap.add_argument("--columns", type=int, default=6)
    ap.add_argument("--scale", type=int, default=4, help="во сколько раз показать кадр 32x40")
    ap.add_argument("--min-area", type=float, default=0.0, dest="min_area",
                    help="пропускать полы мельче этой доли ромба (0 - брать все)")
    args = ap.parse_args(argv)

    only = {s.strip().upper() for s in args.sets.split(",") if s.strip()}
    names = sorted(n for n in os.listdir(args.sheets)
                   if n.upper().endswith(".PCK") and os.path.isdir(os.path.join(args.sheets, n)))
    if only:
        names = [n for n in names if n.upper() in only or n.upper()[:-4] in only]

    os.makedirs(args.out, exist_ok=True)
    rows, tiles = [], []
    for name in names:
        set_dir = os.path.join(args.sheets, name)
        layout = os.path.join(set_dir, "layout.json")
        if not os.path.exists(layout):
            continue
        with open(layout, encoding=ENC) as f:
            info = json.load(f)
        info.setdefault("set", name)
        hints = hints_for(info["set"])
        hj = os.path.join(set_dir, "hints.json")
        if os.path.exists(hj):
            with open(hj, encoding=ENC) as f:
                hints.update({int(k): v for k, v in json.load(f).items()})
        full = float(info["frame_w"] * 16)
        for i, area, frame in floors_of(set_dir, info):
            if args.min_area and area < args.min_area * full:
                continue
            rows.append({"set": name, "frame": i, "hint": hints.get(i, "")})
            tiles.append(frame)

    if not rows:
        print("полов не найдено")
        return 1

    per, cols, k = args.per_sheet, args.columns, args.scale
    tw, th, label = 32 * k, 40 * k, 26
    sheets = 0
    for start in range(0, len(rows), per):
        chunk = list(zip(rows[start:start + per], tiles[start:start + per]))
        rws = (len(chunk) + cols - 1) // cols
        im = Image.new("RGB", (cols * (tw + 8) + 8, rws * (th + label + 8) + 8), (26, 26, 28))
        d = ImageDraw.Draw(im)
        for n, (row, tile) in enumerate(chunk):
            x = 8 + (n % cols) * (tw + 8)
            y = 8 + (n // cols) * (th + label + 8)
            im.paste(tile.resize((tw, th), Image.NEAREST).convert("RGB"), (x, y + label))
            stem = row["set"][:-4] if row["set"].upper().endswith(".PCK") else row["set"]
            d.text((x, y + 2), "%s #%d" % (stem[:18], row["frame"]), fill=(255, 232, 120))
            d.text((x, y + 13), (row["hint"] or "-")[:26], fill=(150, 150, 150))
            row["sheet"] = "sheet_%03d.png" % (sheets + 1)
        sheets += 1
        im.save(os.path.join(args.out, "sheet_%03d.png" % sheets))

    tsv = os.path.join(args.out, "floors.tsv")
    with open(tsv, "w", encoding=ENC, newline="") as f:
        f.write("\t".join(["лист", "набор", "кадр", "подсказка сейчас", "что вижу (рус)", "подсказка (eng)"]) + "\n")
        for row in rows:
            f.write("\t".join([row["sheet"], row["set"], str(row["frame"]), row["hint"], "", ""]) + "\n")

    print("полов: %d, наборов: %d, листов: %d" % (len(rows), len({r["set"] for r in rows}), sheets))
    print("без подсказки сейчас: %d" % sum(1 for r in rows if not r["hint"]))
    print("листы: %s\\sheet_001.png ...   таблица: %s" % (args.out, tsv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
