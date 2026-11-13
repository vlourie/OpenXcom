#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Проба Vitali 03.10: Qwen-Image-2.1 с промптом дословно, без наших добавок. На вход - кадр оригинала
(bicubic x16 на ровной серой подложке, как photo_render.flat_input), промпт PROMPT как сказан, негатива нет,
ответ модели показывается как есть - без вырезки и проверок. Модель по замку (struct_probe.Render: 40 шагов,
cfg 4, 1 Мп).

Выход: <out>/<ТИП>.png - ответ модели, <out>/sheet.png - оригинал x16 | ответ.
Модель - только через очередь:
    py -3.13 tools/gpuq.py add --name qwen_literal5 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/qwen_literal.py
"""
import argparse
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import photo_render as pr               # noqa: E402
import struct_probe as sp               # noqa: E402

PROMPT = ("улучши эти 3 фотки сохранив размер и цвета оригинала ничего не придумывая и сохранив мелкие детали")
ONLY = ("W-014", "W-015", "W-033", "W-057", "W-081")
BATCH = "art/items/weapons100-v1"
PANEL = (128, 128, 128)
SEED = 4242


def frame_of(t):
    d = os.path.join(BATCH, "cards", "originals", t)
    im = Image.open(os.path.join(d, sorted(os.listdir(d))[0]))
    idx = np.asarray(im)
    pal = np.asarray(im.getpalette()[:768], np.uint8).reshape(-1, 3)
    return Image.fromarray(np.dstack([pal[idx], np.where(idx == 0, 0, 255).astype(np.uint8)]), "RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="art/items/qwen-literal-v1")
    a = ap.parse_args()
    os.chdir(os.path.dirname(os.path.dirname(HERE)))
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(BATCH, "list.tsv"), encoding="utf-8-sig", newline="") as f:
        items = [r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE) if r["master"] in ONLY]
    R = sp.Render(a.out)
    R.check_lock()
    import gen_fire
    import gen_hd
    gen_fire.NEGATIVE = R.po.gen_fire.NEGATIVE = " "     # негатива нет: промпт дословно
    painter = gen_hd.Qwen21Painter(R.ns, {"ground": ("", "")})
    print("промпт:", PROMPT, flush=True)
    shown = []
    for r in items:
        fr = frame_of(r["type"])
        src = pr.flat_input(fr, PANEL, pr.RENDER_V1["zoom"])
        ts = time.time()
        hd = sp.run_multi(painter, R.run, PROMPT, [src], SEED)
        hd.save(os.path.join(a.out, r["type"] + ".png"))
        src.save(os.path.join(a.out, r["type"] + ".input.png"))
        print("%s %s: %.0f с" % (r["master"], r["type"], time.time() - ts), flush=True)
        shown.append((r, src, hd.convert("RGB")))
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    H = 640
    cols = []
    for r, src, hd in shown:
        a1 = src.resize((round(src.width * H / src.height), H), Image.LANCZOS)
        a2 = hd.resize((round(hd.width * H / hd.height), H), Image.LANCZOS)
        cols.append((r, a1, a2))
    W = sum(c[1].width + c[2].width + 30 for c in cols) + 10
    sheet = Image.new("RGB", (W, H + 40), (20, 22, 30))
    d = ImageDraw.Draw(sheet)
    x = 10
    for r, a1, a2 in cols:
        sheet.paste(a1, (x, 30))
        sheet.paste(a2, (x + a1.width + 4, 30))
        d.text((x, 6), "%s %s: вход | ответ" % (r["master"], r["en"]), fill=(225, 225, 235), font=font)
        x += a1.width + a2.width + 30
    sheet.save(os.path.join(a.out, "sheet.png"))
    print("лист:", os.path.join(a.out, "sheet.png"), flush=True)


if __name__ == "__main__":
    main()
