#!/usr/bin/env python3
"""
gen_base_bubbles.py - бурлящая жижа в постройке базы (HD-анимация клеток BASEBITS).

Собирает постройку из её клеток (2x2 и т.п., порядок как в BaseView: строка за строкой),
увеличивает Scale2x так же, как gen_base.py, находит жидкость - самый крупный связный
кусок пикселей заданного цвета (по умолчанию зелёный хеллерий) - и рисует по фазам:

    * рябь - медленное колыхание яркости жидкости;
    * пузыри - вздуваются три фазы и лопаются кольцом, которое расходится и гаснет.

Каждый пузырь живёт по кругу фаз, поэтому петля бесшовная. Движок листает фазы раз в
200 мс (BaseView::blink), 16 фаз - петля в 3.2 с. Клетки пишутся как у gen_base.py:

    <мод hd>/hd/BASEBITS.PCK/<кадр>.png, <кадр>.v1.png ... v15.png

Номер кадра - как в рулсете мода (без сдвига 1000: движок ищет и так, см. HdBase).

    py -3 tools/hdart/gen_base_bubbles.py --src "E:/OpenXCom/Пиратки/Dioxine_XPiratez/user/mods/Piratez"
        --indices 608-611 --size 2x2 --out <мод hd> --out <вторая копия мода hd>
        --preview art/_review/hplant_bubbles.gif
"""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_base import basebits_map, parse_indices, scale2x  # noqa: E402


def load_tiles(sprites, indices, cols, rows):
    """Клетки -> (индексы, палитра) всей постройки в классическом размере."""
    tiles, pal = [], None
    for i in indices:
        im = Image.open(sprites[i])
        a = np.array(im, dtype=np.int16)
        trans = im.info.get("transparency")
        if isinstance(trans, int) and trans != 0:
            a = np.where(a == trans, 0, a)
        tiles.append(a)
        if pal is None:
            raw = im.getpalette()[:768]
            pal = np.array(raw + [0] * (768 - len(raw)), np.float32).reshape(-1, 3) / 255.0
    th, tw = tiles[0].shape
    big = np.zeros((rows * th, cols * tw), np.int16)
    for n, t in enumerate(tiles):
        y, x = divmod(n, cols)
        big[y * th:(y + 1) * th, x * tw:(x + 1) * tw] = t
    return big, pal, (tw, th)


def largest_component(mask):
    """Самый крупный 4-связный кусок маски (чтобы капли на полу не бурлили)."""
    h, w = mask.shape
    seen = np.zeros_like(mask, bool)
    best = None
    for y0 in range(h):
        for x0 in range(w):
            if not mask[y0, x0] or seen[y0, x0]:
                continue
            stack, part = [(y0, x0)], []
            seen[y0, x0] = True
            while stack:
                y, x = stack.pop()
                part.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if best is None or len(part) > len(best):
                best = part
    out = np.zeros_like(mask, bool)
    for y, x in best or []:
        out[y, x] = True
    return out


def erode(mask, r):
    out = mask.copy()
    for _ in range(r):
        m = out.copy()
        m[1:, :] &= out[:-1, :]
        m[:-1, :] &= out[1:, :]
        m[:, 1:] &= out[:, :-1]
        m[:, :-1] &= out[:, 1:]
        out = m
    return out


def smooth_noise(h, w, cells, rng):
    """Гладкий шум: случайная решётка cells x cells, билинейно на h x w."""
    g = rng.random((cells + 1, cells + 1)).astype(np.float32)
    im = Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
    return np.array(im, np.float32) / 255.0


def disc(h, w, cx, cy, r, soft=0.8):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2)
    return np.clip((r - d) / soft + 0.5, 0.0, 1.0), d


def render(rgb, liquid, phase, phases, bubbles, ripple, amp):
    h, w, _ = rgb.shape
    t = phase / float(phases)
    out = rgb.copy()
    # рябь: у каждой точки жидкости своя фаза колыхания из гладкого шума
    wave = 1.0 + amp * np.sin(2.0 * math.pi * (t + ripple))
    out[liquid] = np.clip(out[liquid] * wave[liquid][:, None], 0.0, 1.0)
    light = np.array([0.80, 0.93, 0.42], np.float32)
    dark = np.array([0.22, 0.42, 0.08], np.float32)
    for bx, by, rmax, start, life in bubbles:
        age = (phase - start) % phases
        if age >= life:
            continue
        grow = life - 2
        if age < grow:
            # вздувается: светлый купол с тёмной кромкой и бликом
            r = rmax * (age + 1) / grow
            body, d = disc(h, w, bx, by, r)
            rim = np.clip(1.0 - np.abs(d - r) / 1.1, 0.0, 1.0) * (d <= r + 0.6)
            glint, _ = disc(h, w, bx - r * 0.35, by - r * 0.35, max(r * 0.28, 0.7))
            m = liquid[..., None]
            out = np.where(m, out * (1 - body[..., None] * 0.85) + light * body[..., None] * 0.85, out)
            out = np.where(m, out * (1 - rim[..., None] * 0.6) + dark * rim[..., None] * 0.6, out)
            out = np.where(m, out * (1 - glint[..., None] * 0.8) + 1.0 * glint[..., None] * 0.8, out)
        else:
            # лопнул: кольцо расходится и гаснет
            k = age - grow + 1
            r = rmax * (1.0 + 0.45 * k)
            fade = 0.7 if k == 1 else 0.35
            _, d = disc(h, w, bx, by, r)
            ring = np.clip(1.0 - np.abs(d - r) / 1.0, 0.0, 1.0) * fade
            m = liquid[..., None]
            out = np.where(m, out * (1 - ring[..., None]) + light * ring[..., None], out)
    return np.clip(out, 0.0, 1.0)


def main():
    ap = argparse.ArgumentParser(description="бурлящая жижа в постройке базы")
    ap.add_argument("--src", required=True, help="папка мода со спрайтами (…/mods/Piratez)")
    ap.add_argument("--indices", required=True, help="клетки постройки BASEBITS: 608-611")
    ap.add_argument("--size", default="2x2", help="клеток по ширине x высоте")
    ap.add_argument("--out", action="append", default=[], help="папка мода hd (можно несколько)")
    ap.add_argument("--phases", type=int, default=16, help="фаз анимации (не больше 16)")
    ap.add_argument("--bubbles", type=int, default=12, help="пузырей на петлю")
    ap.add_argument("--amp", type=float, default=0.06, help="сила ряби")
    ap.add_argument("--min-green", type=int, default=30, help="насколько зелёный канал выше красного и синего")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--preview", default="", help="GIF петли (и .png - лист фаз рядом)")
    args = ap.parse_args()

    phases = max(1, min(args.phases, 16))
    cols, rows = (int(v) for v in args.size.lower().split("x"))
    indices = parse_indices(args.indices)
    sprites = basebits_map(args.src)
    idx, pal, (tw, th) = load_tiles(sprites, indices, cols, rows)

    rgb8 = (pal * 255).astype(np.int32)
    green = (rgb8[:, 1] > rgb8[:, 0] + args.min_green) & (rgb8[:, 1] > rgb8[:, 2] + args.min_green)
    pool = largest_component(green[np.clip(idx, 0, 255)] & (idx != 0))

    scale = 4
    hi = scale2x(scale2x(idx))
    rgb = pal[np.clip(hi, 0, 255)]
    alpha = (hi != 0).astype(np.float32)
    pool_hi = np.repeat(np.repeat(pool, scale, 0), scale, 1)
    liquid = pool_hi & green[np.clip(hi, 0, 255)]
    h, w = liquid.shape
    print("жидкость: %d пикселей классики, %d в HD" % (pool.sum(), liquid.sum()))

    rng = np.random.default_rng(args.seed)
    ripple = smooth_noise(h, w, 6, rng)
    inner = erode(liquid, 8)
    ys, xs = np.nonzero(inner)
    bubbles = []
    life = 5
    for n in range(args.bubbles):
        j = rng.integers(len(xs))
        start = (n * phases) // args.bubbles + int(rng.integers(0, 2))
        bubbles.append((xs[j] + 0.5, ys[j] + 0.5, float(rng.uniform(4.0, 7.5)), start % phases, life))

    frames = [render(rgb, liquid, p, phases, bubbles, ripple, args.amp) for p in range(phases)]

    for out_dir in args.out:
        dest = os.path.join(out_dir, "hd", "BASEBITS.PCK")
        os.makedirs(dest, exist_ok=True)
        for p, f in enumerate(frames):
            data = np.concatenate([np.clip(f * 255.0 + 0.5, 0, 255), alpha[..., None] * 255.0], axis=2).astype(np.uint8)
            for n, index in enumerate(indices):
                y, x = divmod(n, cols)
                tile = data[y * th * scale:(y + 1) * th * scale, x * tw * scale:(x + 1) * tw * scale]
                name = "%d.png" % index if p == 0 else "%d.v%d.png" % (index, p)
                Image.fromarray(tile, "RGBA").save(os.path.join(dest, name))
        print("%d клеток x %d фаз -> %s" % (len(indices), phases, dest))

    if args.preview:
        os.makedirs(os.path.dirname(os.path.abspath(args.preview)), exist_ok=True)
        imgs = [Image.fromarray((f * 255 + 0.5).astype(np.uint8)) for f in frames]
        imgs[0].save(args.preview, save_all=True, append_images=imgs[1:], duration=200, loop=0)
        sheet = Image.new("RGB", (w * 4, h * ((phases + 3) // 4)))
        for p, im in enumerate(imgs):
            sheet.paste(im, ((p % 4) * w, (p // 4) * h))
        sheet.save(os.path.splitext(args.preview)[0] + ".png")
        print("превью:", args.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
