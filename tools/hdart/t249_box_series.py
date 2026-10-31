#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000249: сломанный ящик URBAN_WASTE 91 (92 - зеркало) и вся семья - вариант 2 (зерно 24902), выбор Vitali 23.10.

Основа: готовые кадры генерации (видеокарта не нужна)
    art/tickets/t249/gen_box/series/URBAN_WASTE.PCK/91_24902.png
    art/tickets/t249/gen_box/series92/92_24902.png
Что делается кодом:
  1. Нутро чуть темнее: классика темнее, поэтому по тёмной области классики кадра (x4, мягкая маска) яркость основы
     уменьшается на DARKEN (доля), рельеф досок остаётся; стенки и кромка - как у основы.
  2. Семья (ticket_family.py URBAN_WASTE:91 и :92; заготовка FAMILY в t249_box.py): все члены - копии классики или перекраска
     (URBAN:91/92), класс предмета у них один - ящик. Основа одна на кадр, у члена сдвиг ХРОМЫ среднего Lab к классике НАБОРА
     (как с колесом t249_wheel.py: средний Lab классики члена минус средний Lab классики URBAN_WASTE:кадр; у побайтных копий
     сдвиг нулевой, у перекрасок URBAN свой); яркость - как у основы.
  3. Альфа основы не меняется.

    py -3.13 tools/hdart/t249_box_series.py                  # кадры в art/tickets/t249/out_box2/TERRAIN/...
    py -3.13 tools/hdart/t249_box_series.py --install --yes  # + в мод hd через манифест (под очередью правок)
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts   # noqa: E402
import water_build as wb    # noqa: E402

SRC = {91: ROOT / "art" / "tickets" / "t249" / "gen_box" / "series" / "URBAN_WASTE.PCK" / "91_24902.png",
       92: ROOT / "art" / "tickets" / "t249" / "gen_box" / "series92" / "92_24902.png"}
OUT = ROOT / "art" / "tickets" / "t249" / "out_box2"
SET = "URBAN_WASTE"
FAMILY = {91: [("COMDECOR", 43), ("CRIBDECOR", 44), ("IDT_SNOWVILBAN", 87), ("URBANLUX", 91), ("URBANWAR", 91),
               ("URBAN_GOODS", 91), ("VILBAN", 87), ("URBAN", 91)],
          92: [("COMDECOR", 44), ("CRIBDECOR", 45), ("CULTDECOR", 20), ("IDT_SNOWVILBAN", 88), ("MADDECOR", 19),
               ("MADDECOR_WASTE", 18), ("SEAMADDECOR", 19), ("URBANLUX", 92), ("URBANWAR", 92), ("URBAN_GOODS", 92),
               ("VILBAN", 88), ("URBAN", 92)]}
DARK = 78.0              # яркость классики ниже - нутро
DARKEN = 0.22            # на сколько темнее нутро (доля L)
SS = 8
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def lab(rgb):
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.float32) / 255, cv2.COLOR_RGB2Lab)


def unlab(x):
    return np.clip(cv2.cvtColor(x.astype(np.float32), cv2.COLOR_Lab2RGB) * 255, 0, 255)


def load(p):
    return np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)


def classic_lab(s, f):
    try:
        cl = wb.read_set(s)[f]
    except (TypeError, IndexError):
        return None
    pal = wb.palette()
    return lab(pal[cl[cl > 0]][..., :3].astype(np.float32).reshape(-1, 1, 3)).reshape(-1, 3).mean(0)


def inner_mask(f):
    a = wb.read_set(SET)[f]
    pal = wb.palette()
    lum = pal[a][..., :3].astype(np.float32) @ LUMA
    dark = ((lum < DARK) & (a > 0)).astype(np.float32)
    dm = cv2.resize(dark, (128 * SS, 160 * SS), interpolation=cv2.INTER_LINEAR)
    dm = cv2.GaussianBlur(dm, (0, 0), 1.6 * SS)
    dm = cv2.resize(dm, (128, 160), interpolation=cv2.INTER_AREA)
    return np.clip((dm - 0.15) * 2.2, 0, 1)


def base_frame(f):
    src = load(SRC[f])
    L = lab(src[..., :3])
    dm = inner_mask(f)
    L[..., 0] *= 1 - DARKEN * dm
    out = src.copy()
    out[..., :3] = unlab(L)
    return out


def build_all():
    res = {}
    for f in (91, 92):
        base = base_frame(f)
        res[(SET, f)] = base
        c0 = classic_lab(SET, f)
        for s, ff in FAMILY[f]:
            c = classic_lab(s, ff)
            r = base.copy()
            if c is not None:
                d = c - c0
                d[0] = 0.0
                r[..., :3] = unlab(lab(base[..., :3]) + d)
            else:
                print("нет классики:", s, ff, "- без сдвига")
            res[(s, ff)] = r
    return res


def save_all(res):
    paths = {}
    if (OUT / "TERRAIN").exists():
        keep = {OUT / "TERRAIN" / (s + ".PCK") / ("%d.png" % f) for (s, f) in res}
        for old in (OUT / "TERRAIN").rglob("*.png"):
            if old not in keep:
                old.unlink()
    for (s, f), p in res.items():
        d = OUT / "TERRAIN" / (s + ".PCK")
        d.mkdir(parents=True, exist_ok=True)
        q = d / ("%d.png" % f)
        Image.fromarray(np.clip(p, 0, 255).round().astype(np.uint8), "RGBA").save(q)
        paths["TERRAIN/%s.PCK/%d.png" % (s, f)] = q
    return paths


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    res = build_all()
    paths = save_all(res)
    print("кадров: %d -> %s" % (len(res), OUT))
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(paths, "t249_box_series", "t249_box_series.py 23.10 вариант 2 (зерно 24902), нутро темнее, хрома по классике набора",
                         "Vitali 23.10 (XP-000249 ящик 91/92, вариант 2, зерно 24902); семья 22 кадра",
                         "t249: ящик URBAN_WASTE 91/92 и семья (22 кадра) - вариант 2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
