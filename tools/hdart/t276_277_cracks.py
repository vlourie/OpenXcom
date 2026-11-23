#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000276 (разрывы земли в траве MOUNTGRASS:61/62) и XP-000277 (разлом-крест 2x2 в наборах MOUNT*).

Рецепт тот же, что у ям t262_pits.py (форма по маске КЛАССИКИ, цвет и светотень - гладкое поле классики целого холста,
свет сверху-слева одно на весь 2x2, R-265; фактура - высокие частоты HD-набора; грунт вокруг - плоский HD набора),
но маска острее: разрыв тонкий и рваный, у креста лучи шириной в 1-2 пикселя базы, круглить их нельзя (R-042).
Что отличается от ям:
  - маска не по 'не трава', а по правилу набора: 'gr' (G - R <= 12), 'dark' (яркость ниже медианы грунта холста
    на долю thr), 'brown' (бурое на снегу);
  - размытие маски на базе 0.5 и мягкий порог ниже 0.5 - лучи не пропадают;
  - тёмная стенка у верхнего-левого края разлома и светлая кромка у нижнего-правого - скат по полю расстояния.

Номера кадров креста по MCD 11 (верх), 12 (лево), 13 (право), 14 (низ) каждого набора (Mod, записи MCD): MOUNTGRASS 10-13,
MOUNT 11-14, MOUNTROCK 11-14, MOUNTSNOW2 11-14, MOUNTWASTE2 10-13. У MOUNTMUD, MOUNTTROP и MOUNTSAND на этих MCD креста
нет (грязь, джунгли и песок с камнями) - их не трогаем; 32 кадра из первичной оценки оказались 20.

    py -3.13 tools/hdart/t276_277_cracks.py            # кадры в art/tickets/t276_277/out/<набор>/<кадр>.png
    py -3.13 tools/hdart/t276_277_cracks.py --only cross --sets MOUNT
"""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import t262_pits as P  # noqa: E402

OUT = os.path.join(P.ROOT, "art", "tickets", "t276_277", "out")
K = P.K
OFF, CW, CH, LUM, blur = P.OFF, P.CW, P.CH, P.LUM, P.blur


def _x(name, frames, base, **kw):
    g = {"name": name, "frames": frames, "base": base}
    g.update(kw)
    return g


FLAT = {"top": "0.v1", "right": "0.v3", "left": "0.v2", "bottom": "0"}
CROSS = lambda a: {"top": a, "left": a + 1, "right": a + 2, "bottom": a + 3}  # noqa: E731

GROUPS = {
    "MOUNTGRASS": [
        # разрывы в траве (276): бурая щель с тёмным нутром и светлой нижней губой
        _x("W61", {"top": 61}, {"top": "0.v4", "right": "0.v5", "left": "0.v2", "bottom": "0.v1"}, rule="gr2", extra=[63],
           depth=12.0, contrast=0.7, grain=0.16, msig=0.5, mthr=0.38, mw=0.22, noise=0.03, kind="worm"),
        _x("W62", {"top": 62}, {"top": "0.v2", "right": "0.v5", "left": "0.v2", "bottom": "0.v1"}, rule="gr2", extra=[63],
           depth=12.0, contrast=0.7, grain=0.16, msig=0.5, mthr=0.38, mw=0.22, noise=0.03, kind="worm"),
        # крест (277)
        _x("X", CROSS(10), {"top": "0.v6", "right": "0.v5", "left": "0.v2", "bottom": "0.v1"}, rule="dark", thr=0.8, extra=[63],
           depth=7.0, contrast=0.35, bright=1.0, innerdark=0.05, lmin=32.0, grain=0.12, msig=0.5, mthr=0.5, mw=0.22, noise=0.03, kind="cross"),
    ],
    "MOUNT": [_x("X", CROSS(11), FLAT, rule="dark", thr=0.88, ground="heal", extra=[0], depth=14.0, contrast=0.6, bright=1.25, grain=0.12, msig=0.5, mthr=0.36,
                 mw=0.22, noise=0.03, kind="cross", lip=0.05)],
    "MOUNTROCK": [_x("X", CROSS(11), FLAT, rule="dark", thr=0.80, minpx=10, ground="heal", extra=[0], depth=14.0, contrast=0.6, bright=1.25, grain=0.12, msig=0.5, mthr=0.36,
                     mw=0.22, noise=0.03, kind="cross", lip=0.04)],
    "MOUNTSNOW2": [_x("X", CROSS(11), FLAT, rule="dark", thr=0.72, extra=[], depth=10.0, grain=0.10, msig=0.5, mthr=0.36,
                      mw=0.22, noise=0.03, kind="cross", lip=0.0, esig=0.7)],
    "MOUNTWASTE2": [_x("X", CROSS(10), FLAT, rule="dark", thr=0.88, ground="heal", ground_sub={"bottom": ("mirror", 12)}, extra=[0], depth=12.0, grain=0.12, msig=0.5,
                       mthr=0.5, mw=0.22, noise=0.03, healgrow=3, healsig=0.8, healnoise=0.45, kind="cross", lip=0.04)],
}


def crack_mask_classic(arr, g):
    a = arr[..., 3] > 0
    rule = g["rule"]
    if rule == "gr":
        return P.pit_mask_classic(arr, "gr", True)
    if rule == "gr2":
        # как 'gr', но без раскрытия 2x2: у тонкой щели оно съедает концы (до 20 процентов длины)
        rgb = arr[..., :3].astype(np.int32)
        m = a & (rgb[..., 1] - rgb[..., 0] <= P.GR_MAX)
        m = ndi.binary_closing(m, structure=np.ones((2, 2)))
        m = ndi.binary_fill_holes(m)
        lab, n = ndi.label(m, structure=np.ones((3, 3)))
        if n > 1:
            sizes = ndi.sum(m, lab, range(1, n + 1))
            m = np.isin(lab, [i + 1 for i, sz in enumerate(sizes) if sz >= 4])
        return m & a
    rgb = arr[..., :3].astype(np.float32)
    L = rgb @ LUM
    L = cv2.GaussianBlur(L, (0, 0), 0.6)
    ref = float(np.median(L[a]))
    inner = ndi.binary_erosion(a, iterations=3)       # кайма плитки в классике темнее - не разлом
    m = inner & (L < ref * g.get("thr", 0.8))
    m = ndi.binary_closing(m, structure=np.ones((2, 2)))
    lab, n = ndi.label(m, structure=np.ones((3, 3)))
    if n > 1:
        sizes = ndi.sum(m, lab, range(1, n + 1))
        keep = [i + 1 for i, s in enumerate(sizes) if s >= g.get("minpx", 6)]
        m = np.isin(lab, keep)
    return m & a


def heal(cur, m, g, seed=5):
    a = np.array(cur)
    al = a[..., 3] > 0
    rgb = a[..., :3].copy()
    alf = al.astype(np.float32)
    Lh = cv2.GaussianBlur((rgb.astype(np.float32) @ LUM) * alf, (0, 0), 3.0) / np.maximum(cv2.GaussianBlur(alf, (0, 0), 3.0), 1e-3)
    ref = float(np.median(Lh[al]))
    inner = ndi.binary_erosion(al, iterations=5)      # кайма плитки остаётся как есть
    old = inner & (Lh < ref * g.get("healthr", 0.78))
    hm = ndi.binary_dilation(old | (m > 0.15), iterations=g.get("healgrow", 6)) & inner
    hm8 = (hm * 255).astype(np.uint8)
    fill = rgb.copy()
    fill[~al] = np.median(rgb[al], axis=0).astype(np.uint8)
    inp = cv2.inpaint(fill, hm8, 6, cv2.INPAINT_TELEA)
    # зерно: высокие частоты неповреждённого грунта, нормированные, в залитую область
    hp = rgb.astype(np.float32) @ LUM
    hp = hp - cv2.GaussianBlur(hp, (0, 0), 3.0)
    good = al & ~ndi.binary_dilation(hm, iterations=3)
    sd = float(hp[good].std()) if good.any() else 4.0
    n = P.smooth_noise(hp.shape, g.get("healsig", 1.1), seed) * sd * g.get("healnoise", 1.0)
    inp = inp.astype(np.float32) + n[..., None] * hm[..., None]
    inp = cv2.GaussianBlur(inp, (0, 0), 0.0001) if False else inp
    out = np.where(hm[..., None], inp, rgb.astype(np.float32)).clip(0, 255).astype(np.uint8)
    res = np.dstack([out, a[..., 3]])
    return Image.fromarray(res, "RGBA")


def render(setname, g, k=K, seed=11):
    cl = np.array(P.compose(g["frames"], lambda f: P.classic(setname, f), 1)).astype(np.float32)
    m1c = crack_mask_classic(cl, g)
    H, W = CH * k, CW * k
    m1 = blur(m1c.astype(np.float32), g.get("msig", 0.5))
    m = cv2.resize(m1, (W, H), interpolation=cv2.INTER_CUBIC)
    m = m + g.get("noise", 0.03) * P.smooth_noise((H, W), 4.0, seed)
    t = np.clip((m - g.get("mthr", 0.4)) / g.get("mw", 0.22), 0, 1)
    m = t * t * (3 - 2 * t)
    w = m1c.astype(np.float32)
    es = g.get("esig", 0.8)
    ec = np.zeros((CH, CW, 3), np.float32)
    idx = ndi.distance_transform_edt(~m1c, return_distances=False, return_indices=True)
    for c in range(3):
        ec[..., c] = blur(cl[..., c] * w, es) / np.maximum(blur(w, es), 1e-3)
        near = cl[..., c][idx[0], idx[1]]
        ec[..., c] = np.where(blur(w, es) > 0.15, ec[..., c], near)
    E = np.stack([cv2.resize(ec[..., c], (W, H), interpolation=cv2.INTER_CUBIC) for c in range(3)], -1)
    inside = m > 0.5
    Lc = E @ LUM
    Lm = float(Lc[inside].mean()) if inside.any() else 1.0
    shade = np.clip(Lc / Lm, 0.3, 1.8) ** g.get("contrast", 0.5)
    d = ndi.distance_transform_edt(inside).astype(np.float32)
    z = -(1 - np.exp(-d / 6.0)) * g.get("depth", 10.0)
    z = blur(z, 1.2)
    gy, gx = np.gradient(z)
    nz = 1 / np.sqrt(1 + gx * gx + gy * gy)
    lx, ly, lz = -0.55, -0.55, 0.65
    geo = np.clip(((-gx * lx - gy * ly + lz) * nz) / lz, 0.55, 1.25)
    det, _ = P.detail_field(setname, g, m, (H, W), seed)
    sd = det[inside].std() if inside.any() else 1.0
    det = det / (sd + 1e-6)
    earth = E * shade[..., None] * geo[..., None] * (1 + g.get("grain", 0.12) * det[..., None])
    gm = blur(m, 3.0)
    inner = np.clip(m * (1 - gm) * 2.0, 0, 1)
    earth = earth * (1 - g.get("innerdark", 0.25) * inner[..., None]) * g.get("bright", 1.0)
    if "lmin" in g:
        # пол яркости: самое тёмное в классике внутри маски - не чернее (кайма креста не плотнее классики)
        Le = earth @ LUM
        up_ = np.maximum(g["lmin"] / np.maximum(Le, 1e-3), 1.0)
        earth = earth * up_[..., None]
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if g.get("ground") == "heal":
        # грунт - текущие кадры пака; старый разлом и свежий - залиты по соседним пикселям, зерно добавлено
        cur = Image.new("RGBA", (CW * k, CH * k), (0, 0, 0, 0))
        for pos, f in g["frames"].items():
            ox, oy = OFF[pos]
            tile = P.hd_open(setname, f)
            sub = g.get("ground_sub", {}).get(pos)
            if sub:
                # старый фон клетки (полосы) заменяется чистой клеткой пака, зеркально, альфа остаётся своя
                src = P.hd_open(setname, sub[1])
                if sub[0] == "mirror":
                    src = src.transpose(Image.FLIP_LEFT_RIGHT)
                ta = np.array(tile)
                sa = np.array(src)
                ta[..., :3] = sa[..., :3]
                tile = Image.fromarray(ta, "RGBA")
            cur.alpha_composite(tile, (ox * k, oy * k))
        base = heal(cur, m, g)
    else:
        for pos, f in g["base"].items():
            ox, oy = OFF[pos]
            base.alpha_composite(P.hd_open(setname, f), (ox * k, oy * k))
    B = np.array(base).astype(np.float32)
    outer = np.clip((1 - m) * gm * 2.0, 0, 1)
    ground = B[..., :3] * (1 + g.get("lip", 0.08) * outer[..., None])
    rgb = np.clip(ground * (1 - m[..., None]) + earth * m[..., None], 0, 255)
    return rgb, B[..., 3] > 0, m, m1c


def run(sets=None, only=None):
    res = {}
    for setname, groups in GROUPS.items():
        if sets and setname not in sets:
            continue
        for g in groups:
            if only and g["kind"] not in only:
                continue
            rgb, cover, m, m1c = render(setname, g)
            outs = P.cut_frames(setname, g, rgb, cover)
            d = os.path.join(OUT, setname)
            os.makedirs(d, exist_ok=True)
            for f, im in outs.items():
                im.save(os.path.join(d, "%d.png" % f))
                res[(setname, f)] = os.path.join(d, "%d.png" % f)
            Image.fromarray(np.dstack([rgb, np.where(cover, 255, 0)]).astype(np.uint8), "RGBA").save(
                os.path.join(d, "_comp_%s.png" % g["name"]))
            Image.fromarray((m1c * 255).astype(np.uint8)).resize((CW * 4, CH * 4), Image.NEAREST).save(
                os.path.join(d, "_mask_%s.png" % g["name"]))
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sets")
    ap.add_argument("--only", help="worm,cross")
    a = ap.parse_args()
    res = run(a.sets.split(",") if a.sets else None, a.only.split(",") if a.only else None)
    print("кадров: %d в %s" % (len(res), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
