#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000463: ровный край подставки кулера (R-121, правило 12 CLAUDE.md). Рисунок внутри не трогается.

Вариант D (art/tickets/t463/cand2/D) имел альфу подставки лесенкой x4 (маска классики x4 без спрямления). Здесь альфа
ниже линии стыка с бутылью (ROW0..ROW1, x4) берётся из силуэта k=1 этого же кадра, спрямлённого xBRZ x4
(probe_object.smooth_silhouette, как в 379/443), а выше - прежняя альфа бутыли (она круглая и ровная). Цвет в пикселях,
ставших непрозрачными, - от ближайшего прежнего непрозрачного пикселя (без полос и каймы). Семья: XBASEN_BITS:39 +
побайтная копия FREIGHTER_COMMAND_2:30 - один результат на оба.

    py -3.13 tools/hdart/t463_edge.py            кандидаты в art/tickets/t463/cand2/D_edge/
    py -3.13 tools/hdart/t463_edge.py sheet      лист art/_review/tickets_2026-11-02/install_463_edge.png
"""
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)

SRC = os.path.join(ROOT, "art", "tickets", "t463", "cand2", "D")
OUT = os.path.join(ROOT, "art", "tickets", "t463", "cand2", "D_edge")
FRAMES = [("XBASEN_BITS", 39), ("FREIGHTER_COMMAND_2", 30)]
SHIFT = 0.8
BLUR = 1.5
SLOPE = 255.0 * 0.399 / BLUR
ROW0, ROW1 = 60, 74       # строки x4: выше - прежняя альфа, ниже - спрямлённая, между - плавный переход


def straighten(im):
    import probe_object as po
    rgba = np.asarray(im.convert("RGBA")).copy()
    a = rgba[..., 3].astype(np.float32)
    h, w = a.shape
    m1 = (a.reshape(h // 4, 4, w // 4, 4).mean(axis=(1, 3)) >= 127.5)
    from PIL import ImageFilter
    import sprite_scale
    f = np.asarray(po.fill_holes(Image.fromarray(m1.astype(np.uint8) * 255, "L")), np.float32)
    up = sprite_scale.xbrz_scale(np.stack([f, f, f, np.full_like(f, 255.0)], -1)[None], 4)[0][..., 0]
    # xBRZ спрямляет косые (2:1) и вертикали; размытие 1.5 даёт линейный профиль края +-1.9 px для сдвига и сглаживания 1 px
    sm = np.asarray(Image.fromarray(np.clip(up, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(BLUR)), np.float32)
    wy = np.clip((np.arange(h, dtype=np.float32) - ROW0) / float(ROW1 - ROW0), 0, 1)[:, None]
    # граница бутыли над стыком - прежняя; ниже - не шире спрямлённой, не уже её: берём её целиком
    # край 1 px, сдвинут внутрь на SHIFT px (без светлой каймы поверх тёмной кромки)
    sm = np.clip((sm - 127.5) / SLOPE + 0.5 - SHIFT, 0, 1) * 255.0
    new = a * (1 - wy) + sm * wy
    new = np.clip(new, 0, 255)
    # цвет: где альфа выросла (прежний пиксель прозрачный/полупрозрачный) - от ближайшего надёжного
    solid = a >= 250
    solid = ndi.binary_erosion(solid, iterations=1)
    _, idx = ndi.distance_transform_edt(~solid, return_indices=True)
    near = rgba[idx[0], idx[1], :3]
    need = (a < 250) & (new > a)
    out = rgba.copy()
    out[need, :3] = near[need]
    out[..., 3] = np.round(new).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    return Image.fromarray(out, "RGBA")


LOC = (1224, 352)        # кулер в census/tickets/XP-000463/files/01_shot.png (как в t463_build2)
CEN = os.path.join(ROOT, "census", "tickets", "XP-000463", "files")
REVIEW = os.path.join(ROOT, "art", "_review", "tickets_2026-11-02", "install_463_edge.png")


def sheet():
    """Лист «было D | стало»: сцена 3x3 клетки, масштаб игры 1:1, края подставки x8 (право-верх, низ ромба, лево)."""
    from PIL import ImageDraw
    import ticket_scene as ts
    fnt = ts.font(16)
    bg = (60, 70, 80, 255)
    old = Image.open(os.path.join(SRC, "XBASEN_BITS_39.png")).convert("RGBA")
    new = Image.open(os.path.join(OUT, "XBASEN_BITS_39.png")).convert("RGBA")

    def on(im):
        b = Image.new("RGBA", im.size, bg)
        b.alpha_composite(im)
        return b

    def scene(im):
        """Кулеры на клетках 3x3 по полу (ромбы 32x16 px x4), масштаб игры k=4; смотрим x2."""
        k, n = 4, 3
        W, H = (2 * n) * 16 * k + 32 * k, (2 * n) * 8 * k + 40 * k
        sc = Image.new("RGBA", (W, H), (84, 90, 92, 255))
        dd = ImageDraw.Draw(sc)
        for y in range(n):
            for x in range(n):
                cx, cy = n * 16 * k + (x - y) * 16 * k + 16 * k, (x + y) * 8 * k + 24 * k + 16 * k
                dd.polygon([(cx, cy - 8 * k), (cx + 16 * k, cy), (cx, cy + 8 * k), (cx - 16 * k, cy)],
                           fill=(104, 108, 106, 255), outline=(70, 74, 74, 255))
        for y in range(n):
            for x in range(n):
                sc.alpha_composite(im, (n * 16 * k + (x - y) * 16 * k, (x + y) * 8 * k))
        return sc.resize((W * 2 // 2, H * 2 // 2)).convert("RGB")

    rows = [scene(old), scene(new)]
    crops = [("право-верх x8", (64, 60, 120, 120)), ("низ ромба x8", (30, 110, 120, 160)), ("лево x8", (8, 60, 64, 140))]
    k = 8
    pans = []
    for _, bx in crops:
        w, h = bx[2] - bx[0], bx[3] - bx[1]
        pans.append(tuple(on(im).crop(bx).resize((w * k, h * k), Image.NEAREST).convert("RGB") for im in (old, new)))
    W = max(rows[0].width * 2 + 30, sum(p[0].width for p in pans[:1]) * 2 + 30)
    H = 60 + rows[0].height + 20 + sum(p[0].height + 30 for p in pans)
    out = Image.new("RGB", (max(W, 2 * rows[0].width + 30, 2 * pans[1][0].width + 30), H), (12, 12, 14))
    d = ImageDraw.Draw(out)
    d.text((10, 6), "XBASEN_BITS:39 (+ копия FREIGHTER_COMMAND_2:30): сцена 3x3 клетки, масштаб игры 1:1", fill=(255, 220, 60), font=fnt)
    d.text((10, 28), "было (D)", fill=(255, 220, 60), font=fnt)
    d.text((rows[0].width + 20, 28), "стало (ровный край)", fill=(255, 220, 60), font=fnt)
    out.paste(rows[0], (10, 52))
    out.paste(rows[1], (rows[0].width + 20, 52))
    y = 52 + rows[0].height + 12
    for (t, _), (a, b) in zip(crops, pans):
        d.text((10, y), "было - " + t, fill=(255, 220, 60), font=fnt)
        d.text((a.width + 20, y), "стало - " + t, fill=(255, 220, 60), font=fnt)
        out.paste(a, (10, y + 14))
        out.paste(b, (a.width + 20, y + 14))
        y += a.height + 30
    out.crop((0, 0, out.width, y)).save(REVIEW)
    print("лист:", REVIEW)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "sheet":
        return sheet()
    os.makedirs(OUT, exist_ok=True)
    done = {}
    for s, f in FRAMES:
        src = Image.open(os.path.join(SRC, "%s_%d.png" % (s, f))).convert("RGBA")
        key = src.tobytes()
        if key not in done:
            done[key] = straighten(src)
        done[key].save(os.path.join(OUT, "%s_%d.png" % (s, f)))
        print("OK", s, f)


if __name__ == "__main__":
    main()
