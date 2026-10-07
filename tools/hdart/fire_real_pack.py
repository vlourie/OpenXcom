#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Огонь с объёмом в пак SMOKE.PCK: доводка ответов gen_fire_real.py и три стиля для опции oxceHdFire.

Без видеокарты. Берёт ответы модели (<вход>_s<зерно>.png на подложке) и входы gen_fire_real.py
(ровные кадры петли: f<первый кадр>_<фаза>.png, 8 фаз, 128x160), и кладёт в пак:

    стиль 1 «объёмный»             - кадры модели как есть      -> <i>.v2.png / <i>.v3.png
    стиль 2 «объёмный, вверх»      - кадры модели + волна вверх -> <i>.v4.png / <i>.v5.png
    стиль 3 «ровный, вверх»        - одна фаза модели + волна   -> <i>.v6.png / <i>.v7.png

Фаза t петли (тик 100 мс, 8 фаз): кадр i = первый + t // 2, чётная фаза - вариант 2s, нечётная - 2s + 1
(Map.cpp и UnitSprite.cpp: setFrameVariant(2 * oxceHdFire + tween)). Стиль 0 - прежние <i>.png и
<i>.v1.png, их скрипт не трогает.

Доводка: подложку снимаем по цвету углов (модель кладёт её своим тоном), силуэт не дальше 3 px от
входа, площадь всех фаз выровнена масштабом от основания пламени (без него огонь пульсирует), мелкие
дырки альфы внутри тела заделаны. Волна: смещение по синусу, фаза которого с ростом t уходит вверх,
выборка билинейная по премультипликации - рисунок не мутнеет; петля замыкается ровно за 8 фаз.

    py -3.13 tools/hdart/fire_real_pack.py --ai-in art/fx_smooth_preview/ai_in ^
        --ai-out art/fx_smooth_preview/ai_out --seed 1234 ^
        --pack user/mods/hd/hd/SMOKE.PCK --pack Пиратки/Dioxine_XPiratez/user/mods/hd/hd/SMOKE.PCK
"""
import argparse
import math
import os

import numpy as np
from PIL import Image, ImageFilter

K = 4
LOOPS = ((0, True), (4, False))              # огонь клетки (кадры 0-3) и огонь на юните (4-7)
PHASES = 8


def base_y(big):
    """Основание пламени в пикселях HD: от него масштаб площади и высота волны."""
    return (36.5 if big else 29.5) * K


def unpanel(im, soft=48.0):
    a = np.asarray(im.convert("RGB"), dtype=np.float32)
    c = 24
    corners = np.concatenate([a[:c, :c].reshape(-1, 3), a[:c, -c:].reshape(-1, 3),
                              a[-c:, :c].reshape(-1, 3), a[-c:, -c:].reshape(-1, 3)])
    panel = np.median(corners, axis=0)
    d = np.abs(a - panel).max(axis=2)
    alpha = np.clip((d - 6.0) / soft, 0, 1)
    rgb = np.clip(panel + (a - panel) / np.maximum(alpha, 1e-3)[..., None], 0, 255)
    return rgb / 255.0, alpha


def unpremul(pm):
    al = pm[..., 3]
    rgb = np.where(al[..., None] > 1e-3, pm[..., :3] / np.maximum(al, 1e-3)[..., None], 0)
    return np.dstack([rgb, al]).astype(np.float32)


def cut(src, raw):
    """Ответ модели -> RGBA кадра (не премультиплицирован), силуэт не дальше 3 px HD от входа."""
    rgb, al = unpanel(raw)
    pm = np.dstack([rgb * al[..., None], al])
    ch = [np.asarray(Image.fromarray(pm[..., c].astype(np.float32), "F").resize(src.size, Image.LANCZOS),
                     dtype=np.float32) for c in range(4)]
    pm = np.clip(np.stack(ch, -1), 0, 1)
    m = src.split()[3].point(lambda v: 255 if v > 20 else 0).filter(ImageFilter.MaxFilter(7))
    m = np.asarray(m.filter(ImageFilter.GaussianBlur(1.5)), dtype=np.float32) / 255.0
    return unpremul(pm * m[..., None])


def scale_about(a, s, cx, cy):
    h, w = a.shape[:2]
    pm = a.copy()
    pm[..., :3] *= pm[..., 3:]
    coeffs = (1 / s, 0, cx - cx / s, 0, 1 / s, cy - cy / s)
    ch = [np.asarray(Image.fromarray(pm[..., c].astype(np.float32), "F")
                     .transform((w, h), Image.AFFINE, coeffs, resample=Image.BICUBIC), dtype=np.float32)
          for c in range(4)]
    return unpremul(np.clip(np.stack(ch, -1), 0, 1))


def level_area(frames, big):
    """Площадь всех фаз к средней - масштабом от основания, языки остаются резкими."""
    areas = [f[..., 3].sum() for f in frames]
    mean = np.mean(areas)
    out = []
    for f, ar in zip(frames, areas):
        al = f[..., 3]
        cx = (al.sum(0) * np.arange(f.shape[1])).sum() / al.sum()
        out.append(scale_about(f, math.sqrt(mean / ar), cx, base_y(big)))
    return out


def fill_holes(a):
    """Мелкие дырки альфы внутри тела (модель оставила подложку между языками) - цветом соседей."""
    im = Image.fromarray(np.clip(a[..., 3] * 255 + 0.5, 0, 255).astype(np.uint8))
    al = a[..., 3] * 255
    med = np.asarray(im.filter(ImageFilter.MedianFilter(9)), dtype=np.float32)
    hole = (al < 0.6 * med) & (med > 200)
    if not hole.any():
        return a, 0
    pm = a.copy()
    pm[..., :3] *= pm[..., 3:]
    g = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2)
    g /= g.sum()
    blur = pm
    for ax in (0, 1):
        blur = np.apply_along_axis(lambda v: np.convolve(v, g, mode="same"), ax, blur)
    fill = unpremul(blur)
    out = a.copy()
    out[hole, :3] = fill[hole, :3]
    out[hole, 3] = med[hole] / 255.0
    return out, int(hole.sum())


def sample(pm, sx, sy):
    h, w = pm.shape[:2]
    x0 = np.floor(sx).astype(int)
    y0 = np.floor(sy).astype(int)
    fx = (sx - x0)[..., None]
    fy = (sy - y0)[..., None]
    out = np.zeros_like(pm)
    for dy, wy in ((0, 1 - fy), (1, fy)):
        for dx, wx in ((0, 1 - fx), (1, fx)):
            xx, yy = x0 + dx, y0 + dy
            ok = (xx >= 0) & (xx < w) & (yy >= 0) & (yy < h)
            out += pm[np.clip(yy, 0, h - 1), np.clip(xx, 0, w - 1)] * ok[..., None] * wx * wy
    return out


def phase_noise(w, seed):
    """Своя фаза волны у каждого языка: гладкий шум вдоль x с шагом 16 px."""
    rng = np.random.default_rng(seed)
    pts = rng.random(w // 16 + 3) * 2 * math.pi
    xs = np.arange(w) / 16.0
    i = xs.astype(int)
    f = xs - i
    f = f * f * (3 - 2 * f)
    return pts[i] * (1 - f) + pts[i + 1] * f


def lick(a, t, n, big, amp=1.0, lam=38.0, sway=1.0, seed=5):
    """Волна вверх: при росте t постоянная фаза синуса уходит к меньшим y. Вверху сильнее, у основания почти 0."""
    pm = a.copy()
    pm[..., :3] *= pm[..., 3:]
    h, w = pm.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    top = (2.0 if big else 0.5) * K
    height = np.clip((base_y(big) - ys) / (base_y(big) - top), 0, 1)
    ph = phase_noise(w, seed)[None, :]
    ph2 = phase_noise(w, seed + 7)[None, :]
    tt = 2 * math.pi * t / n
    dy = amp * (1.5 + 5.0 * height) * np.sin(2 * math.pi * ys / lam + tt + ph)
    dx = sway * (0.5 + 3.5 * height) * np.sin(2 * math.pi * ys / (lam * 1.6) + tt + ph2)
    return unpremul(sample(pm, xs + dx, ys + dy))


def to_img(a):
    return Image.fromarray(np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8), "RGBA")


def area_spread(frames):
    areas = [f[..., 3].sum() for f in frames]
    return (max(areas) - min(areas)) / np.mean(areas) * 100


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ai-in", required=True, help="входы gen_fire_real.py: f<lo>_<фаза>.png")
    ap.add_argument("--ai-out", required=True, help="ответы gen_fire_real.py: f<lo>_<фаза>_s<зерно>.png")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--pack", action="append", default=[], help="папка hd/SMOKE.PCK (можно несколько)")
    ap.add_argument("--preview", default="", help="куда положить кадры стилей для просмотра, без пака")
    args = ap.parse_args()
    if not args.pack and not args.preview:
        raise SystemExit("некуда класть: нужен --pack или --preview")

    out = {}                                          # имя файла -> картинка
    for lo, big in LOOPS:
        frames = []
        for t in range(PHASES):
            name = "f%d_%d" % (lo, t)
            src = Image.open(os.path.join(args.ai_in, name + ".png")).convert("RGBA")
            raw = Image.open(os.path.join(args.ai_out, "%s_s%d.png" % (name, args.seed)))
            frames.append(cut(src, raw))
        holes = 0
        for t in range(PHASES):
            frames[t], n = fill_holes(frames[t])
            holes += n
        frames = level_area(frames, big)
        # волна чуть меняет площадь на краях - выровнять ещё раз, иначе огонь дышит
        styles = {
            1: frames,
            2: level_area([lick(frames[t], t, PHASES, big) for t in range(PHASES)], big),
            3: level_area([lick(frames[0], t, PHASES, big, amp=1.2) for t in range(PHASES)], big),
        }
        for s, seq in styles.items():
            print("кадры %d-%d, стиль %d: площадь ±%.1f%%" % (lo, lo + 3, s, area_spread(seq)))
            for t, f in enumerate(seq):
                out["%d.v%d.png" % (lo + t // 2, 2 * s + t % 2)] = to_img(f)
        print("кадры %d-%d: заделано дырок альфы %d px" % (lo, lo + 3, holes))

    for d in args.pack + ([args.preview] if args.preview else []):
        if d in args.pack and not os.path.isdir(d):
            raise SystemExit("нет папки пака: %s" % d)
        os.makedirs(d, exist_ok=True)
        for n, im in out.items():
            im.save(os.path.join(d, n))
        print("%s: %d файлов" % (d, len(out)))


if __name__ == "__main__":
    main()
