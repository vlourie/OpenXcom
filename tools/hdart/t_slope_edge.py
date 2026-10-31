#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Правка края склонов 27-39, 41 наборов MOUNTTROP, FORESTJUNGLESTYX (t431), MOUNTGRASS (t445) - перед выпуском 2026.10.31
(приёмка, замечание 2): край лесенкой.

Причины (две, обе в АЛЬФЕ кандидатов A1):
  1. альфа A1 = силуэт классики x4 (np.kron), размытый гауссом сигма 2.4 - лесенка 2x1 пикселя классики (8x4 HD) остаётся
     (R-121);
  2. шов с соседями (t445: rim_alpha.fixed) делает полосу у линии ромба непрозрачной ТОЧНЫМ ромбом (альфа 0 или 255:
     лесенка 2x1 пикселя HD на каждой косой линии) и всю классику середины ромба - 255 (классическая лесенка там, где
     xBRZ её срезал). У t431 шва не было вовсе.
Здесь ТОЛЬКО альфа: цвет - прежними генераторами (t431_slopes.build_frame, t445_slopes.build_frame; цоколь - из резерва
прежних кадров, а не из уже установленного A1), альфа - силуэт классики, сглаженный xBRZ x4 (как t443_gen.clip_smooth),
не шире силуэта классики на 2 пикселя; у линии ромба - покрытие пикселя прямой (smooth_fixed), середина - своя альфа.
В МОД НИЧЕГО НЕ СТАВИТ: art/tickets/t431/cand/A1e и art/tickets/t445/cand/A1e.

    py -3.13 tools\hdart\t_slope_edge.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402
from scipy import ndimage                            # noqa: E402

import t410_gen as g                                 # noqa: E402
import t431_slopes as s431                           # noqa: E402
import t445_slopes as s445                           # noqa: E402
import probe_object as po                            # noqa: E402

ROOT = g.ROOT
FRAMES = s431.FRAMES
NAME = "A1e"
_CUR = {}
GW = 0.0349 * 1.3      # ширина перехода покрытия в мере ромба при k=4: 0.0349 - шаг меры на пиксель HD по нормали к линии; 1.3 пикселя


def straight_alpha(set_, f):
    """Силуэт классики кадра -> альфа x4 (0..1): xBRZ-спрямление + размытие 0.7, не шире силуэта на 2 пикселя."""
    cl = np.asarray(g.classic(set_, f))
    op = cl[..., 3] > 0
    m = Image.fromarray(op.astype(np.uint8) * 255, "L")
    a = np.asarray(po.smooth_silhouette(m, 4), np.float32) / 255.0
    sil4 = np.kron(op, np.ones((4, 4), bool))
    return np.where(ndimage.binary_dilation(sil4, iterations=2), a, 0.0)


def _backup_now(bk):
    """Цоколь прежних генераторов - из нынешнего HD кадра, а он уже заменён A1: берём резерв прежних (до установки)."""
    def f(s, n):
        p = os.path.join(ROOT, "art", "_backup", bk, "TERRAIN", s + ".PCK", "%s.png" % n)
        if os.path.exists(p):
            return Image.open(p).convert("RGBA")
        return None
    return f


def _patched(sil4, sigma=2.4):
    return straight_alpha(*_CUR["k"])


def smooth_fixed(cur, op, k=4, fw=32, fh=40):
    """Шов с соседями (как rim_alpha.fixed: R-247, R-291), но край ромба - со сглаживанием, а не сплошной лесенкой.
    У rim_alpha.fixed полоса шва непрозрачна по точному ромбу (альфа 0 или 255 - лесенка 2x1 пикселя HD на каждой косой
    линии), и вся классика середины ромба тоже 255 (лесенка 8x4 там, где xBRZ её срезал). Здесь: у линии ромба
    (мера 1 + перехлёст) альфа - покрытие пикселя прямой шириной около пикселя; середина - своя альфа (xBRZ);
    клинья вершин - как у rim_alpha."""
    import rim_alpha as ra
    d, u, v = ra.diamond(k, fw, fh)
    near = np.kron(ndimage.binary_dilation(op, structure=np.ones((1, 5), bool)), np.ones((k, k), bool))
    sil = ra.silhouette(op, k)
    band = (d >= ra.BAND) & (d < 99)
    wedge = (u < ra.WEDGE) & (v < ra.WEDGE)
    hi_u, hi_v = u > 1 - ra.WEDGE, v > 1 - ra.WEDGE
    tip = band & sil & ((hi_u & hi_v) | (hi_u & (v < ra.WEDGE)) | (hi_v & (u < ra.WEDGE)))
    gw = GW * 4.0 / k
    edge = 1.0 + ra.OVERLAP
    cov = np.clip((edge + gw / 2.0 - d) / gw, 0.0, 1.0)
    zone = band & near & ~wedge & (d <= edge + gw / 2.0)
    a1 = cur[..., 3].astype(np.float32) / 255.0
    a1[zone] = np.maximum(a1[zone], cov[zone])
    keep = tip | (band & wedge & sil)
    a1[keep] = 1.0
    new = cur.copy()
    new[..., 3] = np.rint(np.clip(a1, 0, 1) * 255).astype(np.uint8)
    # цвет: почти прозрачным (rgb - мусор) - тон середины рядом, как в rim_alpha.fixed
    need = (new[..., 3] > 0) & (cur[..., 3] < ra.OWN_A)
    if need.any():
        rgb = ra.fill(cur)
        new[..., :3][need] = np.clip(np.rint(rgb[need]), 0, 255).astype(np.uint8)
    new[..., :3][new[..., 3] == 0] = 0
    return new, int(need.sum())


def _seam(im, s, f):
    import rim_alpha as ra
    frames, _t, fw, fh = ra.classic(s)
    arr, _n = smooth_fixed(np.asarray(im).copy(), frames[f] != 0, 4, fw, fh)
    return Image.fromarray(arr, "RGBA")


def build_all(seam431=True):
    import rim_alpha as ra
    ra.fixed = smooth_fixed          # t445_slopes.build_frame зовёт rim_alpha.fixed
    s431.smooth_alpha = _patched
    old431 = _backup_now("t431_20261030")
    old445 = _backup_now("t445_20261030")
    cur445 = s445.hd_now
    s431.b.hd_now = old431
    s445.hd_now = lambda s, n: (old445(s, n) or cur445(s, n)) if str(n).isdigit() else cur445(s, n)
    s445.smooth_alpha = _patched
    out = {}
    d431 = os.path.join(s431.CAND, NAME)
    d445 = os.path.join(s445.CAND, NAME)
    os.makedirs(d431, exist_ok=True)
    os.makedirs(d445, exist_ok=True)
    gfld, sfld = s431.fl.field_x4("g", s431.SG), s431.fl.field_x4("s", s431.SS)
    for s in s431.SETS:
        for f in FRAMES:
            _CUR["k"] = (s, f)
            im = s431.build_frame(gfld, sfld, s, f)
            if seam431:
                im = _seam(im, s, f)
            im.save(os.path.join(d431, "%s_%d.png" % (s, f)))
            out[(s, f)] = im
    field, pos = s445.mosaic()
    cells = s445.window_cells(pos)
    for f in FRAMES:
        _CUR["k"] = ("MOUNTGRASS", f)
        im = s445.build_frame(field, pos, cells, "MOUNTGRASS", f)
        im.save(os.path.join(d445, "MOUNTGRASS_%d.png" % f))
        out[("MOUNTGRASS", f)] = im
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    r = build_all()
    print("кадров:", len(r))
