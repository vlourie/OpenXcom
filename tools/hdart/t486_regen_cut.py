#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000486: ответы модели t486_regen_gen.py -> кадры IDT_FARM:19/:18 и зеркала :15/:14 (без видеокарты, в мод не пишет).

1. вырезка как у серии (probe_object.cut_out: ключ по подложке, силуэт классики +2 px, сглаженный линиями xBRZ - R-121),
   тон к классике 0.7, нарезка по клеткам obj_series.split (составной 19+18, шва нет);
2. цвет под прозрачным и полупрозрачным: цвет ближайшего непрозрачного пикселя (не чёрная подложка модели);
3. :15/:14 - зеркало целой картинки; альфа режется силуэтом классики :15/:14 (тот же сглаженный путь, +2 px;
   классика :14 отличается от зеркала :18 на 0.5%);
4. отчёт: мелкие замкнутые дыры в альфе внутри силуэта (прямоугольные выемки), число непрозрачных пикселей.
Кандидаты: art/tickets/t486_regen/<вариант>/IDT_FARM_{14,15,18,19}.png

    py -3.13 tools/hdart/t486_regen_cut.py a
"""
import os
import sys

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

import map_mockup as mm                              # noqa: E402
import obj_series as osr                             # noqa: E402
import probe_object as po                            # noqa: E402

OUT = os.path.join(ROOT, "art", "tickets", "t486_regen")
K19, K18, K15, K14 = ("IDT_FARM", 19), ("IDT_FARM", 18), ("IDT_FARM", 15), ("IDT_FARM", 14)
M1819 = [(K19, (-16, -8, 0)), (K18, (0, 0, 0))]
M1415 = [(K15, (16, -8, 0)), (K14, (0, 0, 0))]
PAD, GROW, SOFT, TONE = 3, 2, 40, 0.7


def bleed(img):
    """RGB под альфой < 250 - от ближайшего надёжного пикселя; альфа не меняется."""
    a = np.asarray(img, np.uint8).copy()
    solid = a[..., 3] >= 250
    if not solid.any():
        return img
    _, idx = ndi.distance_transform_edt(~solid, return_indices=True)
    near = a[idx[0], idx[1], :3]
    weak = ~solid
    a[weak, :3] = near[weak]
    return Image.fromarray(a, "RGBA")


def comp_of(world, members):
    spr = {k: world.sprite(k[0], k[1], None).convert("RGBA") for k, _o in members}
    return {"members": members, "spr": spr, "pl": {k: 0 for k, _o in members}}


def small_holes(alpha, sil):
    """Замкнутые компоненты alpha<128 внутри силуэта классики, не касающиеся края: (площадь, bbox)."""
    h = (alpha < 128) & sil
    lab, n = ndi.label(h)
    out = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        area = int((lab[sl] == i).sum())
        out.append((area, (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop)))
    return sorted(out, reverse=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    var = sys.argv[1]
    raw = Image.open(os.path.join(OUT, "raw", "raw_idtfarm_%s.png" % var)).convert("RGB")
    world = mm.World()
    c1819 = comp_of(world, M1819)
    full, at = osr.compose(c1819)
    bb = full.split()[3].getbbox()
    box = (max(0, bb[0] - PAD), max(0, bb[1] - PAD), min(full.width, bb[2] + PAD), min(full.height, bb[3] + PAD))
    frame = full.crop(box)
    part = po.match_tone(po.cut_out(raw, frame, GROW, SOFT), frame, TONE)
    cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
    cut.paste(part, (box[0] * 4, box[1] * 4))
    pieces = osr.split(cut, c1819, at, GROW)
    d = os.path.join(OUT, var)
    os.makedirs(d, exist_ok=True)
    cut.save(os.path.join(d, "whole_1819.png"))
    res = {}
    for k in (K19, K18):
        res[k] = bleed(pieces[k])
    # зеркала: целая картинка отражается, силуэт - классика :15/:14 (сглаженный, как у cut_out)
    c1415 = comp_of(world, M1415)
    full2, at2 = osr.compose(c1415)
    assert full2.size == full.size, (full2.size, full.size)
    mir = ImageOps.mirror(bleed(cut))
    ma = np.asarray(mir, np.uint8).copy()
    sil = full2.split()[3].point(lambda v: 255 if v > 0 else 0)
    from PIL import ImageFilter
    sil = sil.filter(ImageFilter.MaxFilter(2 * GROW + 1))
    sm = np.asarray(po.smooth_silhouette(sil, 4), np.float32) / 255.0
    # альфа зеркала режется силуэтом классики :15/:14 (+2 px, как у cut_out); дострой не нужен: силуэт с запасом
    a0 = ma[..., 3].astype(np.float32) / 255.0
    ma[..., 3] = np.round(np.minimum(a0, sm) * 255).astype(np.uint8)
    mw = Image.fromarray(ma, "RGBA")
    pieces2 = osr.split(mw, c1415, at2, GROW)
    for k in (K15, K14):
        res[k] = bleed(pieces2[k])
    for k, im in res.items():
        im.save(os.path.join(d, "IDT_FARM_%d.png" % k[1]))
        a = np.asarray(im)[..., 3]
        cl = np.asarray(world.sprite(k[0], k[1], None).convert("RGBA"))[..., 3] > 0
        c4 = np.repeat(np.repeat(cl, 4, 0), 4, 1)
        holes = [h for h in small_holes(a, c4) if h[0] >= 12]
        print("%s:%d непрозрачных %d, вне силуэта x4 %d, замкнутых дыр в силуэте >=12px: %s" % (
            k[0], k[1], int((a >= 128).sum()), int(((a >= 128) & ~c4).sum()), holes[:6]))
    print("OK", d)


if __name__ == "__main__":
    main()
