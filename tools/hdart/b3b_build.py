# -*- coding: utf-8 -*-
r"""XP-000510, куст JUNGLEBITS:3 «ближе к классике»: форма и цвет - классика (маска x4 xBRZ с дырами, цвет сглаженный x4),
листовая фактура - донор, ствол и ветки - процедурно по коричневым пикселям классики. Без видеокарты, в мод ничего не ставит.
    py -3.13 b3b_build.py   -> art/tickets/hb510_bush3/<зерно>/JUNGLEBITS_3.png"""
import os
import sys
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
os.chdir(r"E:\OpenXCom")
import numpy as np
from PIL import Image
from scipy import ndimage
import map_mockup as mm
import obj_derive as od
import sprite_scale
import ticket_scene as ts

HOLE = 3
MINWOOD, WSIG, WT0, WT1 = 4, 1.7, 0.40, 0.52
OUTD = os.path.join("art", "tickets", "hb510_bush3")


def classic():
    w = mm.World()
    return w.sprite("junglebits", 3, None).convert("RGBA")


def xbrz_mask(m, k=4):
    a = (m.astype(np.float32) * 255)
    rgba = np.stack([a, a, a, np.full_like(a, 255.0)], -1)[None]
    up = sprite_scale.xbrz_scale(rgba, k)[0][..., 0]
    return np.clip(up, 0, 255) / 255.0


def fup(v, k=4, mode=Image.BICUBIC):
    im = Image.fromarray(v.astype(np.float32), "F")
    return np.asarray(im.resize((v.shape[1] * k, v.shape[0] * k), mode), np.float32)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def clean_mask(m):
    """Одиночные пиксели и дыры в 1 пиксель - шум классики; возвращает (маска, что было заполнено/убрано)."""
    st8 = np.ones((3, 3), int)
    m = m.copy()
    lab, n = ndimage.label(m, st8)
    sz = ndimage.sum(m, lab, range(1, n + 1))
    for i, s_ in enumerate(sz):
        if s_ < 3:
            m[lab == i + 1] = False
    hl, hn = ndimage.label(~m)
    for i in range(1, hn + 1):
        hh = hl == i
        if hh.sum() <= HOLE and not (hh[0].any() or hh[-1].any() or hh[:, 0].any() or hh[:, -1].any()):
            m[hh] = True
    return m


def build(donor, gain=1.0, dsig=5.0, seed=1, wood_boost=1.0, wsig=None, tile=None):
    """donor - RGBA 128x160, лист HD-куста; возвращает RGBA 128x160."""
    wsig = wsig or WSIG
    C = np.array(classic(), np.float32)
    m0 = C[..., 3] > 0
    m = clean_mask(m0)
    r, g = C[..., 0], C[..., 1]
    st8 = np.ones((3, 3), int)
    brr = m0 & m & (r > g + 5)
    brc = ndimage.binary_closing(np.pad(brr, 2), st8)[2:-2, 2:-2] & m0
    lab, n = ndimage.label(brc, st8)
    sz = ndimage.sum(brc, lab, range(1, n + 1))
    br = np.zeros_like(brr)
    for i, s_ in enumerate(sz):
        if s_ >= MINWOOD + 1:
            br |= lab == i + 1
    fo = m0 & m & ~brr         # листовые пиксели классики (мелкие коричневые клочки - тоже листва)
    # --- цвет листвы: Y, Cb, Cr классики, дизеринг смягчён, за силуэт и под ветки - от ближайших листьев
    Y, Cb, Cr = od.ycc(C)
    Ys, Cbs, Crs = (od.spread(od.soft(v, fo), fo, 8) for v in (Y, Cb, Cr))
    Yu, Cbu, Cru = (fup(v) for v in (Ys, Cbs, Crs))
    # --- фактура листа: отношение яркости донора к его размытию (рельеф листьев без своего света)
    d = np.asarray(donor.convert("RGBA"), np.float32)
    da = d[..., 3] > 128
    dy = od.ycc(d)[0]
    if tile:
        # за пределами листа донора - сдвинутые куски его же внутренности (без зеркала: рисунок не симметричен)
        ok = ndimage.binary_erosion(da, iterations=5)
        dyf = np.where(ok, dy, np.nan)
        for oy, ox in ((52, 0), (0, 34), (52, 34), (0, -34), (52, -34), (-30, 0), (-30, 34), (80, 0), (80, 30)):
            sh = np.full_like(dy, np.nan)
            ys = slice(max(0, -oy), min(160, 160 - oy)); xs_ = slice(max(0, -ox), min(128, 128 - ox))
            yd = slice(max(0, oy), min(160, 160 + oy)); xd = slice(max(0, ox), min(128, 128 + ox))
            sh[ys, xs_] = dy[yd, xd]
            sok = np.full(dy.shape, False)
            sok[ys, xs_] = ok[yd, xd]
            fill = np.isnan(dyf) & sok
            dyf[fill] = sh[fill]
        dyf = np.where(np.isnan(dyf), np.nanmean(dyf), dyf)
        bl = ndimage.gaussian_filter(dyf, 0.8)
        seam = ndimage.binary_dilation(~ok, iterations=2) & ok
        dyf = np.where(~ok | seam, bl, dyf)
    else:
        dyf = od.spread(dy, da, 12)
    low = ndimage.gaussian_filter(dyf, dsig)
    mult = np.clip(dyf / np.maximum(low, 1.0), 0.45, 1.7)
    mult = 1.0 + (mult - 1.0) * gain
    Yo = Yu * mult
    col = np.clip(od.rgb(Yo, Cbu, Cru), 0, 255)
    # --- силуэт классики x4, дыры сохранены
    sil = xbrz_mask(m)
    sil = ndimage.gaussian_filter(sil, 0.8)
    alpha = smoothstep(0.35, 0.65, sil)
    # --- дерево: коричневые пиксели классики -> гладкие штрихи
    wm = ndimage.gaussian_filter(xbrz_mask(br), wsig)
    wa = smoothstep(WT0, WT1, wm)
    wcol = np.zeros((40, 32, 3), np.float32)
    for c in range(3):
        wcol[..., c] = od.spread(C[..., c], brr & br, 10)
    wcol = np.stack([fup(wcol[..., c], 4, Image.BILINEAR) for c in range(3)], -1)
    rng = np.random.default_rng(seed)
    nz = ndimage.gaussian_filter(rng.standard_normal((160, 128)), (3.0, 0.9))
    nz = nz / (np.abs(nz).max() + 1e-6)
    gx = ndimage.sobel(ndimage.gaussian_filter(wm, 1.2), axis=1) / 8.0
    shade = 0.55 + 0.50 * smoothstep(WT0 - 0.08, 0.72, wm) + 0.16 * nz - 0.9 * gx
    shade = shade * wood_boost
    wrgb = np.clip(wcol * shade[..., None], 0, 255)
    # --- сборка
    rgb = col * (1 - wa[..., None]) + wrgb * wa[..., None]
    A = np.maximum(alpha, wa)
    xs = np.arange(128, dtype=np.float32)[None, :]
    A = A * smoothstep(0.0, 6.0, xs) * smoothstep(0.0, 6.0, 127.0 - xs)
    out = np.zeros((160, 128, 4), np.uint8)
    out[..., :3] = np.rint(np.clip(rgb, 0, 255)).astype(np.uint8)
    out[..., 3] = np.rint(A * 255).astype(np.uint8)
    out[..., :3][out[..., 3] == 0] = 0
    return Image.fromarray(out, "RGBA")


def main():
    sc = ts.Scene()
    hd4 = sc.hd("JUNGLE", 4)
    os.makedirs(os.path.join(OUTD, "A"), exist_ok=True)
    build(hd4, 1.0, tile=(36, 140, 36, 100)).save(os.path.join(OUTD, "A", "JUNGLEBITS_3.png"))
    raw = Image.open(os.path.join("art", "tickets", "hb509", "gen", "raw", "bush3_5104.png")).convert("RGBA")
    crop = raw.crop((250, 330, 570, 730)).resize((128, 160), Image.LANCZOS)
    crop.save(os.path.join(OUTD, "donorB.png"))
    os.makedirs(os.path.join(OUTD, "B"), exist_ok=True)
    build(crop, 1.7, dsig=3.0, seed=7).save(os.path.join(OUTD, "B", "JUNGLEBITS_3.png"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
