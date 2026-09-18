#!/usr/bin/env python3
"""
gen_base.py - HD-картинки построек базы, с анимацией.

Берёт спрайты BASEBITS.PCK мода (кадры 32x32 или 32x40), увеличивает их в
`--scale` раз без мыла (Scale2x), накладывает процедурную анимацию (пульсация
огней, бегущий блик) и пишет пак для нашего движка:

    <мод>/hd/BASEBITS.PCK/<кадр>.png        - фаза 0
    <мод>/hd/BASEBITS.PCK/<кадр>.v1.png ... - остальные фазы

Движок (BaseView + HdBase) рисует такие клетки в HD-слое и перестаёт рисовать их
классические пиксели, поэтому картинка видна в разрешении экрана.

Пример (ангар Пираток - кадры 9..12):

    py -3 tools\\hdart\\gen_base.py ^--src "E:\\OpenXCom\\Пиратки\\Dioxine_XPiratez\\user\\mods\\Piratez" ^
        --out "E:\\OpenXCom\\Пиратки\\Dioxine_XPiratez\\user\\mods\\hd" --indices 9-12

(в PowerShell перенос строки - обратная кавычка, а не ^)
"""
import argparse
import math
import os
import re
import sys

import numpy as np
from PIL import Image


# ---------------------------------------------------------------- ruleset

def basebits_map(mod_dir):
    """{индекс кадра: путь к png} из extraSprites BASEBITS.PCK всех рулсетов мода."""
    out = {}
    rules = os.path.join(mod_dir, "Ruleset")
    folder = rules if os.path.isdir(rules) else mod_dir
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(".rul"):
            continue
        text = open(os.path.join(folder, name), encoding="utf-8", errors="replace").read()
        for block in re.finditer(r"\n  - type: BASEBITS\.PCK\n(.*?)(?=\n  - type: |\Z)", text, re.S):
            for line in block.group(1).splitlines():
                m = re.match(r"\s+(\d+):\s*(\S.*?)\s*$", line)
                if m:
                    out.setdefault(int(m.group(1)), os.path.join(mod_dir, m.group(2).replace("/", os.sep)))
    return out


def parse_indices(text):
    out = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


# ---------------------------------------------------------------- масштаб

def scale2x(idx):
    """Scale2x (AdvMAME2x) по индексам палитры: вдвое крупнее, без мыла и без ступенек на диагоналях."""
    h, w = idx.shape
    p = np.pad(idx, 1, mode="edge")
    c = p[1:-1, 1:-1]
    up, down, left, right = p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]
    e0, e1, e2, e3 = c.copy(), c.copy(), c.copy(), c.copy()
    diff = (up != down) & (left != right)
    e0 = np.where(diff & (left == up), left, e0)
    e1 = np.where(diff & (up == right), right, e1)
    e2 = np.where(diff & (down == left), left, e2)
    e3 = np.where(diff & (right == down), right, e3)
    out = np.empty((h * 2, w * 2), dtype=idx.dtype)
    out[0::2, 0::2], out[0::2, 1::2] = e0, e1
    out[1::2, 0::2], out[1::2, 1::2] = e2, e3
    return out


def load_frame(path, scale):
    """PNG постройки -> (rgb float 0..1, alpha 0/1) в `scale` раз крупнее."""
    im = Image.open(path)
    if im.mode != "P":
        im = im.convert("P", palette=Image.ADAPTIVE)
    idx = np.array(im, dtype=np.int16)
    palette = np.array(im.getpalette() or [], dtype=np.float32).reshape(-1, 3) / 255.0
    if palette.shape[0] < 256:
        palette = np.vstack([palette, np.zeros((256 - palette.shape[0], 3), np.float32)])
    k = 1
    while k < scale:
        idx = scale2x(idx)
        k *= 2
    if k != scale:                       # 3x и прочие: добиваем ближайшим соседом
        im2 = Image.fromarray(idx.astype(np.uint8), "L").resize(
            (idx.shape[1] * scale // k, idx.shape[0] * scale // k), Image.NEAREST)
        idx = np.array(im2, dtype=np.int16)
    rgb = palette[np.clip(idx, 0, 255)]
    alpha = (idx != 0).astype(np.float32)
    return rgb, alpha


# ---------------------------------------------------------------- анимация

def animate(rgb, alpha, phase, phases, effects, amp, seed):
    """Одна фаза: пульсация ярких пикселей + бегущий по диагонали блик."""
    h, w = alpha.shape
    t = phase / float(phases)
    out = rgb.copy()
    luma = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    visible = alpha > 0

    if "lights" in effects and visible.any():
        # огни - самые яркие пиксели постройки; дышат в противофазе группами,
        # чтобы это читалось как лампы, а не как мигание всей картинки
        thr = np.percentile(luma[visible], 90.0)
        lights = visible & (luma >= max(thr, 0.35))
        if lights.any():
            rng = np.random.default_rng(seed)
            groups = rng.integers(0, 3, size=(h, w))
            for g in range(3):
                m = lights & (groups == g)
                if not m.any():
                    continue
                f = 1.0 + amp * math.sin(2.0 * math.pi * (t + g / 3.0))
                out[m] = np.clip(out[m] * f, 0.0, 1.0)

    if "sweep" in effects:
        # мягкая полоса света, проходящая по клетке (блик от вращающегося маяка)
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        d = (xs / max(w - 1, 1) + ys / max(h - 1, 1)) * 0.5
        band = np.exp(-((((d - (t * 1.4 - 0.2)) % 1.0) - 0.0) ** 2) / (2 * 0.06 ** 2))
        out = np.clip(out * (1.0 + 0.18 * amp * band[..., None]), 0.0, 1.0)

    return out


def write_png(path, rgb, alpha):
    data = np.concatenate([np.clip(rgb * 255.0 + 0.5, 0, 255), alpha[..., None] * 255.0], axis=2)
    Image.fromarray(data.astype(np.uint8), "RGBA").save(path)


# ---------------------------------------------------------------- главное

def main():
    ap = argparse.ArgumentParser(description="HD-картинки и анимация построек базы")
    ap.add_argument("--src", required=True, help="папка мода со спрайтами (например ...\\mods\\Piratez)")
    ap.add_argument("--out", required=True, help="папка мода hd, куда писать (например ...\\mods\\hd)")
    ap.add_argument("--indices", default="9-12", help="кадры BASEBITS.PCK: 9-12 или 9,10,11,12")
    ap.add_argument("--scale", type=int, default=4, help="во сколько раз крупнее классики (по экрану)")
    ap.add_argument("--phases", type=int, default=8, help="кадров анимации (1 = просто HD-картинка)")
    ap.add_argument("--effects", default="lights,sweep", help="lights, sweep (через запятую)")
    ap.add_argument("--amp", type=float, default=0.35, help="сила эффекта (0..1)")
    ap.add_argument("--preview", default="", help="сохранить лист со всеми фазами сюда")
    args = ap.parse_args()

    sprites = basebits_map(args.src)
    if not sprites:
        print("В рулсетах мода нет extraSprites BASEBITS.PCK:", args.src)
        return 1
    effects = [e.strip() for e in args.effects.split(",") if e.strip()]
    dest = os.path.join(args.out, "hd", "BASEBITS.PCK")
    os.makedirs(dest, exist_ok=True)

    sheets = []
    for index in parse_indices(args.indices):
        path = sprites.get(index)
        if not path or not os.path.exists(path):
            print("кадр %d: нет файла (%s)" % (index, path))
            continue
        rgb, alpha = load_frame(path, args.scale)
        row = []
        for phase in range(args.phases):
            out = animate(rgb, alpha, phase, args.phases, effects, args.amp, seed=index)
            name = "%d.png" % index if phase == 0 else "%d.v%d.png" % (index, phase)
            write_png(os.path.join(dest, name), out, alpha)
            row.append((out, alpha))
        sheets.append(row)
        print("кадр %d: %s -> %d фаз %dx%d" % (index, os.path.basename(path), args.phases,
                                               alpha.shape[1], alpha.shape[0]))

    if args.preview and sheets:
        h, w = sheets[0][0][1].shape
        sheet = Image.new("RGBA", (w * len(sheets[0]), h * len(sheets)), (0, 0, 0, 255))
        for y, row in enumerate(sheets):
            for x, (rgb, alpha) in enumerate(row):
                tile = Image.new("RGBA", (w, h))
                data = np.concatenate([np.clip(rgb * 255 + 0.5, 0, 255), alpha[..., None] * 255], axis=2)
                tile = Image.fromarray(data.astype(np.uint8), "RGBA")
                sheet.paste(tile, (x * w, y * h), tile)
        sheet.save(args.preview)
        print("лист фаз:", args.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
