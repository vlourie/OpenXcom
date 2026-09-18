# -*- coding: utf-8 -*-
"""Отчёт по сторожу HD-картинок интерфейса.

Повторяет проверку HdUiArt::pictureMatch (src/Engine/HdUiArt.cpp) вне игры: для каждой
картинки hd/UI/<имя>.png с палитрой <имя>.pal.txt находит классический файл того же имени
в модах и считает два числа, по которым игра решает, картинка это или подмена:

    distance - средняя разница каналов (картинка, сжатая до классического размера,
               против классического изображения в его палитре);
    shape    - корреляция яркостей, то есть насколько сохранена светотень.

Отбраковка в игре: distance > MATCH_LIMIT И shape < SHAPE_LIMIT.

Запуск (нужен venv с Pillow и numpy):
    tools/hdart/.venv/Scripts/python.exe tools/hd_match_report.py [--mods <папка модов>]
"""
import argparse
import io
import os
import sys

import numpy as np
from PIL import Image

ENC_W = "utf-8-sig"
MATCH_LIMIT = 30.0
SHAPE_LIMIT = 0.55


def read_palette(path):
    """256 строк 'r g b' рядом с картинкой - палитра, в которой её рисовали."""
    vals = []
    with io.open(path, encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3:
                vals.append([int(parts[0]), int(parts[1]), int(parts[2])])
    return np.array(vals, dtype=np.float64) if len(vals) == 256 else None


def match(base_png, hd_png, palette):
    """distance и shape, как их считает движок. None - сравнить нельзя."""
    base = Image.open(base_png)
    if base.mode != "P":
        return None
    idx = np.array(base, dtype=np.uint8)
    bh, bw = idx.shape
    hd = Image.open(hd_png).convert("RGBA")
    hw, hh = hd.size
    if bw == 0 or bh == 0 or hw % bw or hh % bh or hw // bw != hh // bh:
        return None
    s = hw // bw
    pix = np.array(hd, dtype=np.float64)
    a = pix[:, :, 3]
    # средний цвет блока s x s, взвешенный по альфе
    blocks = lambda m: m.reshape(bh, s, bw, s).sum(axis=(1, 3))
    wa = blocks(a)
    with np.errstate(invalid="ignore", divide="ignore"):
        pr = blocks(pix[:, :, 0] * a) / wa
        pg = blocks(pix[:, :, 1] * a) / wa
        pb = blocks(pix[:, :, 2] * a) / wa
    ok = (idx != 0) & (wa > 0)
    if ok.sum() < 256:
        return None
    ref = palette[idx]
    cr, cg, cb = ref[:, :, 0], ref[:, :, 1], ref[:, :, 2]
    distance = (np.abs(pr - cr) + np.abs(pg - cg) + np.abs(pb - cb))[ok].sum() / (ok.sum() * 3)
    lx = (0.299 * pr + 0.587 * pg + 0.114 * pb)[ok]
    ly = (0.299 * cr + 0.587 * cg + 0.114 * cb)[ok]
    vx, vy = lx.var(), ly.var()
    shape = float(np.cov(lx, ly)[0, 1] / np.sqrt(vx * vy)) if vx > 1e-6 and vy > 1e-6 else 0.0
    return float(distance), shape


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mods", default=os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods"))
    ap.add_argument("--pack", default=None, help="папка hd/UI (по умолчанию <mods>/hd/hd/UI)")
    ap.add_argument("--out", default=os.path.join("docs", "QA", "hd_match_report.tsv"))
    args = ap.parse_args()

    pack = args.pack or os.path.join(args.mods, "hd", "hd", "UI")
    # классические файлы по имени без расширения, мимо самого HD-пака
    base_by_name = {}
    for dirpath, _, files in os.walk(args.mods):
        if os.sep + "hd" + os.sep in dirpath + os.sep:
            continue
        for f in files:
            if f.lower().endswith(".png"):
                base_by_name.setdefault(os.path.splitext(f)[0].lower(), os.path.join(dirpath, f))

    rows = []
    skipped = 0
    for f in sorted(os.listdir(pack)):
        if not f.lower().endswith(".png"):
            continue
        name = f[:-4]
        pal_path = os.path.join(pack, name + ".pal.txt")
        base_path = base_by_name.get(name.lower())
        if not base_path or not os.path.exists(pal_path):
            skipped += 1
            continue
        palette = read_palette(pal_path)
        if palette is None:
            skipped += 1
            continue
        try:
            res = match(base_path, os.path.join(pack, f), palette)
        except Exception as e:
            print("не смог:", f, e)
            skipped += 1
            continue
        if res is None:
            skipped += 1
            continue
        d, shape = res
        rows.append((name, d, shape, d > MATCH_LIMIT and shape < SHAPE_LIMIT))

    rows.sort(key=lambda r: r[2])
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with io.open(args.out, "w", encoding=ENC_W, newline="\r\n") as f:
        f.write("name\tdistance\tshape\trejected\n")
        for name, d, shape, bad in rows:
            f.write("%s\t%.1f\t%.3f\t%s\n" % (name, d, shape, "да" if bad else ""))

    bad = [r for r in rows if r[3]]
    print("сравнено: %d, пропущено (нет пары/палитры/размер не кратен): %d" % (len(rows), skipped))
    print("отбраковано игрой: %d" % len(bad))
    print("\nраспределение shape:")
    for lo in [x / 10 for x in range(0, 10)]:
        cnt = sum(1 for r in rows if lo <= r[2] < lo + 0.1)
        print("  %.1f-%.1f  %4d  %s" % (lo, lo + 0.1, cnt, "#" * min(60, cnt // 5)))
    print("\nхуже всего по shape:")
    for name, d, shape, b in rows[:20]:
        print("  %-40s distance %5.1f  shape %5.2f %s" % (name, d, shape, "ОТБРАКОВАНА" if b else ""))
    print("\nотчёт: " + args.out)


if __name__ == "__main__":
    sys.exit(main())
