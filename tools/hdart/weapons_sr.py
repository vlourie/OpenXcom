#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Оружие HD-BIGOBS без описаний (Vitali 03.10: «в оружии нам не нужно описание - нужно просто улучшить
качество»): верное увеличение самого кадра, ничего не придумывая. Три способа рядом, на все предметы партии
art/items/weapons100-v1 (list.tsv, cards/originals - кадр индексами и палитрой выгрузки движка):

    xbrz    xBRZ x4 - то, что игра рисует сейчас без пака (режим 2), точка отсчёта;
    detail  xBRZ x4 плюс мелкая фактура Real-ESRGAN x4plus как поправка яркости (upscale_units, как у юнитов);
    model   картинка Real-ESRGAN anime_6B целиком, альфа - гладкая маска оригинала (upscale_units --method model).

Выход: <out>/sr/<способ>/<ТИП>.png (k=4) и листы <out>/sr_NN.png (оригинал x4 | три способа, на тёмном).
В мод ничего не кладётся.

Модель грузится (spandrel, torch.load) - только через очередь:
    py -3.13 tools/gpuq.py add --name weapons100_sr --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv/Scripts/python.exe tools/hdart/weapons_sr.py
"""
import argparse
import csv
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import upscale_units as uu              # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(HERE))
MODELS = {"detail": "E:/models/RealESRGAN_x4plus.pth", "model": "E:/models/RealESRGAN_x4plus_anime_6B.pth"}
K = 4


def rows(path):
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def load(folder, t):
    """Кадр 32x48 индексами и палитра (256, 3)."""
    d = os.path.join(folder, "cards", "originals", t)
    im = Image.open(os.path.join(d, sorted(os.listdir(d))[0]))
    pal = np.asarray(im.getpalette()[:768], np.uint8).reshape(-1, 3)
    pal = np.vstack([pal, np.zeros((256 - len(pal), 3), np.uint8)]) if len(pal) < 256 else pal
    return np.asarray(im), pal


def settings(method):
    return SimpleNamespace(scale=K, method=method, detail=0.6, detail_limit=0.3, model_input="xbrz2",
                           dedither=0.0, pad=4, hard_alpha=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="art/items/weapons100-v1")
    a = ap.parse_args()
    os.chdir(ROOT)
    items = rows(os.path.join(a.out, "list.tsv"))
    frames = [load(a.out, r["type"]) for r in items]
    ups = {"xbrz": uu.Upscaler("")}
    for m, p in MODELS.items():
        ups[m] = uu.Upscaler(p)
    res = {}
    for m in ("xbrz", "detail", "model"):
        os.makedirs(os.path.join(a.out, "sr", m), exist_ok=True)
        for r, (idx, pal) in zip(items, frames):
            hd = uu.make_frames(ups[m], idx[None], pal, settings(m))[0]
            img = Image.fromarray(np.clip(hd + 0.5, 0, 255).astype(np.uint8), "RGBA")
            img.save(os.path.join(a.out, "sr", m, r["type"] + ".png"))
            res[(m, r["type"])] = img
        print("weapons_sr: %s - %d кадров" % (m, len(items)), flush=True)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    W, H = 32 * K, 48 * K
    CW, CH = 4 * (W + 4) + 16, H + 26
    for page in range(0, len(items), 10):
        sub = list(zip(items, frames))[page:page + 10]
        out = Image.new("RGB", (CW * 2, CH * 5 + 24), (20, 22, 30))
        d = ImageDraw.Draw(out)
        for c, name in enumerate(("оригинал x4", "xBRZ (сейчас в игре)", "xBRZ + ESRGAN", "ESRGAN anime")):
            for col in range(2):
                d.text((col * CW + 8 + c * (W + 4), 4), name, fill=(200, 200, 210), font=font)
        for i, (r, (idx, pal)) in enumerate(sub):
            X, Y = (i % 2) * CW + 8, (i // 2) * CH + 24
            orig = Image.fromarray(np.dstack([pal[idx], np.where(idx == 0, 0, 255).astype(np.uint8)]), "RGBA")
            cells = [orig.resize((W, H), Image.NEAREST)] + [res[(m, r["type"])] for m in ("xbrz", "detail", "model")]
            for c, im in enumerate(cells):
                tile = Image.new("RGBA", (W, H), (34, 36, 44, 255))
                tile.alpha_composite(im)
                out.paste(tile.convert("RGB"), (X + c * (W + 4), Y))
            d.text((X, Y + H + 4), "%s %s  %s" % (r["master"], r["cells"], r["en"][:40]), fill=(225, 225, 235), font=font)
        out.save(os.path.join(a.out, "sr_%02d.png" % (page // 10 + 1)))
    print("weapons_sr: листы sr_01..sr_%02d" % ((len(items) + 9) // 10), flush=True)


if __name__ == "__main__":
    main()
