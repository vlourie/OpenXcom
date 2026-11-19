#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000485 и XP-000486: правка альфы HD-кадров без видеокарты (Vitali 03.11, страница выбора: 485 вариант Y, 486 вариант F).

485: альфа 255 внутри силуэта классики x4 (отступ 3 px) у шкафчиков XBASEN_BEDS:5/:6 и копий XBASEN_BITS:40/:41.
  Кромка (3 px внутрь от силуэта) и всё вне силуэта не тронуты. RGB не трогается, кроме одиночных чёрных пикселей (rgb=0 при
  альфе <250 внутри маски - подложка модели): им цвет ближайшего надёжного пикселя, иначе после подъёма альфы это чёрные точки.
486: IDT_FARM:19 - две дыры в альфе (bbox x=104..117 y=74..92 и x=94..117 y=102..121): RGB под ними чёрный (подложка),
  цвет достраивается вдоль оси ступени (2,-1), альфа по спрямлённому силуэту классики (R-121). IDT_FARM:15 - зеркало :19,
  IDT_FARM:14 - зеркало :18, обоим альфа по силуэту классики x4 этого же кадра, спрямлённому.

    py -3.13 tools/hdart/t485_486_alpha.py 485     кандидаты art/tickets/t485/
    py -3.13 tools/hdart/t485_486_alpha.py 486     кандидаты art/tickets/t486/
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

FRAMES485 = [("XBASEN_BEDS", 5), ("XBASEN_BEDS", 6), ("XBASEN_BITS", 40), ("XBASEN_BITS", 41)]
OUT485 = os.path.join(ROOT, "art", "tickets", "t485")
OUT486 = os.path.join(ROOT, "art", "tickets", "t486")
SHIFT, BLUR = 0.8, 1.5
SLOPE = 255.0 * 0.399 / BLUR


def fix485(sc, s, f):
    c = np.asarray(sc.classic(s, f))[..., 3] > 0
    hd = np.asarray(sc.hd(s, f)).copy()
    a = hd[..., 3]
    m = ndi.binary_erosion(c, iterations=3, border_value=0)
    low = m & (a < 250)
    solid = a >= 250
    _, idx = ndi.distance_transform_edt(~solid, return_indices=True)
    near = hd[idx[0], idx[1], :3]
    black = low & (hd[..., :3].sum(2) == 0)
    hd[black, :3] = near[black]
    hd[m, 3] = 255
    return Image.fromarray(hd, "RGBA")


def smooth_alpha(c1):
    """Силуэт классики k=1 (bool 40x32) -> альфа x4 прямыми отрезками (xBRZ + размытие), как t463_edge."""
    from PIL import ImageFilter
    import sprite_scale
    import probe_object as po
    f = np.asarray(po.fill_holes(Image.fromarray(c1.astype(np.uint8) * 255, "L")), np.float32)
    up = sprite_scale.xbrz_scale(np.stack([f, f, f, np.full_like(f, 255.0)], -1)[None], 4)[0][..., 0]
    sm = np.asarray(Image.fromarray(np.clip(up, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(BLUR)),
                    np.float32)
    return np.clip((sm - 127.5) / SLOPE + 0.5 - SHIFT, 0, 1)


def classic1(sc, s, f):
    return np.asarray(sc.classic(s, f))[::4, ::4, 3] > 0


def fix19(sc, hd):
    """hd - RGBA ndarray 160x128 кадра IDT_FARM:19."""
    hd = hd.copy()
    a = hd[..., 3].astype(np.float32)
    c = np.asarray(sc.classic("IDT_FARM", 19))[..., 3] > 0
    m = ndi.binary_erosion(c, iterations=3)
    h = m & (a < 250)
    lab, n = ndi.label(h)
    sel = np.zeros_like(h)
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        ys, xs = sl
        if (lab[sl] == i).sum() < 100:
            continue
        for bx0, bx1, by0, by1 in ((95, 120, 103, 121), (104, 120, 75, 90)):
            if xs.start < bx1 and xs.stop > bx0 and ys.start < by1 and ys.stop > by0:
                sel |= lab == i
    sel = ndi.binary_dilation(sel, iterations=1)
    sm = smooth_alpha(classic1(sc, "IDT_FARM", 19))
    solid = a >= 250
    out = hd.copy()
    ys, xs = np.nonzero(sel & ~solid)
    H, W = a.shape
    done = np.zeros_like(solid)
    for y, x in zip(ys, xs):
        for sx, sy in ((2, -1), (-2, 1)):
            for t in range(1, 60):
                px, py = x + sx * t, y + sy * t
                if not (0 <= px < W and 0 <= py < H):
                    break
                if solid[py, px] and hd[py, px, :3].sum() > 60:
                    out[y, x, :3] = hd[py, px, :3]
                    done[y, x] = True
                    break
            if done[y, x]:
                break
    _, idx = ndi.distance_transform_edt(~solid, return_indices=True)
    near = hd[idx[0], idx[1], :3]
    left = sel & ~solid & ~done
    out[left, :3] = near[left]
    na = np.maximum(a, np.where(sel, sm * 255.0, 0))
    out[..., 3] = np.round(na).astype(np.uint8)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    import ticket_scene as ts
    sc = ts.Scene()
    what = sys.argv[1:]
    if what == ["485"]:
        os.makedirs(OUT485, exist_ok=True)
        for s, f in FRAMES485:
            fix485(sc, s, f).save(os.path.join(OUT485, "%s_%d.png" % (s, f)))
            print("OK", s, f)
    elif what == ["486a"]:
        os.makedirs(OUT486, exist_ok=True)
        hd = np.asarray(sc.hd("IDT_FARM", 19)).copy()
        Image.fromarray(fix19(sc, hd), "RGBA").save(os.path.join(OUT486, "IDT_FARM_19.png"))
        print("OK IDT_FARM 19")


if __name__ == "__main__":
    main()
