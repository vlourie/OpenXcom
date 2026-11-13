#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000222: дорожка PORTROADS:16 и вся её семья (11 кадров) - плитка рядами с тёмными швами вместо «грязи». Без генерации.

Что не так: в HD волнистые древесные прожилки на всём кадре, читается как грязь; в классике - доски в диагональных рядах с
тёмно-фиолетовыми швами (индекс 93) и светлой кромкой (168/169).

Рецепт (Vitali 23.10, прототип t222_proc/PORTROADS.PCK/16.png):
  1. основа - классика кадра КАЖДОГО набора (палитра Пираток), увеличенная x4 бикубикой и размытая по маске ромба (ступеньки
     пикселей классики растворяются, швы остаются рядами);
  2. тон набора - сдвиг среднего Lab основы к среднему Lab НЫНЕШНЕГО HD этого набора (у членов семьи он один и тот же с точностью
     до сотых, у PORTROADS:16 свой);
  3. зерно - высокие частоты нынешнего HD этого набора (HD минус его гауссово размытие), умеренно (GRAIN), поверх основы;
  4. альфа кадра не меняется (она точно по силуэту классики x4).
Семья - ticket_family.py PORTROADS:16 (t222_path_family.tsv): CAFEENTRY:0, COMROADS:8, CULTEXTRA:8, FLOORSET:10, FLOORSETSTYX:10,
FREIGHTER_PASSENGER:39, GOVROADS:8, MANSIONFLOOR_MAG:10, MILBARR:11, MILBARRGHOUL:11 (PORTURBITS:30 и его копии - другая семья,
не трогаются).

    py -3.13 tools/hdart/t222_path.py                  # кадры в art/tickets/t222/out_path/TERRAIN/...
    py -3.13 tools/hdart/t222_path.py --install --yes  # + в мод hd через манифест (под очередью правок)
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts  # noqa: E402
import water_build as wb   # noqa: E402

OUT = ROOT / "art" / "tickets" / "t222" / "out_path"
FAMILY = [("PORTROADS", 16), ("CAFEENTRY", 0), ("COMROADS", 8), ("CULTEXTRA", 8), ("FLOORSET", 10), ("FLOORSETSTYX", 10),
          ("FREIGHTER_PASSENGER", 39), ("GOVROADS", 8), ("MANSIONFLOOR_MAG", 10), ("MILBARR", 11), ("MILBARRGHOUL", 11)]
BLUR = 1.1          # px HD: размытие основы по маске
GRAIN = 0.4        # доля зерна нынешнего HD
GSIG = 3.0          # px HD: радиус высоких частот зерна


def lab(rgb):
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.float32) / 255, cv2.COLOR_RGB2Lab)


def unlab(x):
    return np.clip(cv2.cvtColor(x.astype(np.float32), cv2.COLOR_Lab2RGB) * 255, 0, 255)


def load_hd(s, f):
    return np.asarray(Image.open(ts.PACK / (s + ".PCK") / ("%d.png" % f)).convert("RGBA")).astype(np.float32)


def masked_blur(img, m, sig):
    w = cv2.GaussianBlur(m.astype(np.float32), (0, 0), sig)
    num = cv2.GaussianBlur(img * m[..., None], (0, 0), sig)
    return num / np.maximum(w, 1e-3)[..., None]


def build(s, f, pal):
    cl = wb.read_set(s)[f]
    hd = load_hd(s, f)
    m = hd[..., 3] > 127
    rgb = np.zeros(cl.shape + (3,), np.uint8)
    rgb[cl > 0] = pal[cl[cl > 0]][:, :3]
    up = cv2.resize(rgb.astype(np.float32), (128, 160), interpolation=cv2.INTER_CUBIC)
    base = masked_blur(up, m, BLUR)
    # тон: средний Lab нынешнего HD набора
    Lb, Lh = lab(base), lab(hd[..., :3])
    d = Lh[m].mean(0) - Lb[m].mean(0)
    base = unlab(Lb + d)
    # зерно нынешнего HD
    low = masked_blur(hd[..., :3], m, GSIG)
    grain = (hd[..., :3] - low) * GRAIN
    out = np.clip(base + grain, 0, 255)
    return np.dstack([out, hd[..., 3]])


def build_all():
    pal = wb.palette()
    return {(s, f): build(s, f, pal) for s, f in FAMILY}


def save_all(res):
    files = {}
    for (s, f), a in res.items():
        d = OUT / "TERRAIN" / (s + ".PCK")
        d.mkdir(parents=True, exist_ok=True)
        p = d / ("%d.png" % f)
        Image.fromarray(np.clip(a, 0, 255).round().astype(np.uint8), "RGBA").save(p)
        files["TERRAIN/%s.PCK/%d.png" % (s, f)] = p
    return files


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files = save_all(build_all())
    print("кадров: %d -> %s" % (len(files), OUT))
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(files, "t222_path", "t222_path.py 23.10 дорожка: классика набора x4 + тон и зерно нынешнего HD",
                         "Vitali 23.10 (XP-000222 дорожка, процедурно, прототип t222_path.png); семья 11 кадров",
                         "t222: дорожка PORTROADS 16 и семья (11 кадров) плиткой рядами")
    return 0


if __name__ == "__main__":
    sys.exit(main())
