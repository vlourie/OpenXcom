#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""obj_struct: класс кадра (пол / строение / предмет) и «другой бок» по строению, а не по гистограмме цвета
(docs/HD_PIPELINE_V2.md, P1-A). Синтетические записи, без карт.

  * asset_class: покров пола - floor_like, дерево на записи пола - предмет; диагональ и сторона со Stop_LOS -
    стена; сторона без Stop_LOS (терминал у стены) - предмет; дверь - строение; негорючий холм - рельеф,
    горючий (травяной холм или кресло) - не решено, вопрос человеку; куб-ящик - предмет;
  * alt_view: несимметричный объём, повёрнутый на 90 градусов, при том же тоне - HIGH; куб (объём
    симметричен) - никогда не HIGH; другой цвет - REJECT; другая физика вещи - REJECT.

    py -3.13 tools/test_obj_struct.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))

import numpy as np                      # noqa: E402

import obj_struct as os_                # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def vox(fill_layers):
    """Объём: слой z заполнен квадратом с заданным числом клеток (упрощённо - по строкам сверху)."""
    v = np.zeros((12, 16, 16), bool)
    for z, n in enumerate(fill_layers):
        rows = n // 16
        v[z, :rows, :] = True
    return v


def info(**kw):
    base = {"area": 300, "h": 16, "in_floor": 0.5, "cover": 0.5, "tile_type": 3,
            "phys": {"tu_walk": 255, "flammable": 255, "big_wall": 0}, "vox": vox([256, 256])}
    phys = dict(base["phys"], **kw.pop("phys", {}))
    base.update(kw)
    base["phys"] = phys
    return base


C = os_.asset_class
check("покров на записи пола - floor_like", C(info(tile_type=0, in_floor=0.9, cover=0.8, h=12))[0] == "floor_like")
check("дерево на записи пола (31 px) - предмет", C(info(tile_type=0, in_floor=0.89, cover=0.8, h=31))[0] == "object")
check("диагональ корпуса - стена", C(info(phys={"big_wall": 3}))[0] == "structural")
check("сторона со Stop_LOS - стена", C(info(phys={"big_wall": 5, "stop_los": 1}))[0] == "structural")
check("сторона без Stop_LOS (терминал) - предмет", C(info(phys={"big_wall": 5}))[0] == "object")
check("дверь - строение", C(info(phys={"door": 1}))[0] == "structural")
hill = [256] * 6 + [224, 192, 144, 128, 80]
check("негорючий холм - рельеф",
      C(info(phys={"tu_walk": 4, "flammable": 255}, vox=vox(hill)))[0] == "structural")
check("горючий холм или кресло - вопрос человеку",
      C(info(phys={"tu_walk": 2, "flammable": 30}, vox=vox([256, 256, 256, 144, 112, 112])))[0] == os_.UNCERTAIN)
check("куб-ящик, по которому ходят, - предмет",
      C(info(phys={"tu_walk": 4}, vox=vox([256] * 8)))[0] == "object")
check("камешки: в ромбе, но закрывают крохи - предмет",
      C(info(in_floor=0.95, cover=0.1, h=8, vox=vox([64])))[0] == "object")
check("класс не решён - всё равно конвейер предметов", os_.UNCERTAIN in os_.OBJECTISH)


def sil_info(mask, v, phys=None, col=(120, 90, 60)):
    d = os_.silhouette(mask)
    d.update(rec=True, vox=v, phys=dict({"armor": 20, "tu_walk": 255, "flammable": 30, "t_level": 0,
                                         "footstep": 1}, **(phys or {})), col=np.array(col, float))
    return d


# кадр-«стул»: несимметричный силуэт и L-образный объём (спинка у одного края)
m = np.zeros((40, 32), bool)
m[14:38, 8:14] = True               # спинка
m[26:38, 8:24] = True               # сиденье
chair = np.zeros((12, 16, 16), bool)
chair[:4, 4:12, 4:12] = True        # сиденье
chair[4:10, 4:12, 4:6] = True       # спинка у края x
turned = np.rot90(chair, 1, (1, 2))
a = sil_info(m, chair)
b = sil_info(m[:, ::-1].copy(), turned)
cls, score, why = os_.alt_view(a, b, 0.8)
check("повёрнутый несимметричный объём, тот же тон - HIGH (%s)" % cls, cls == os_.ALT_HIGH)
cube = np.zeros((12, 16, 16), bool)
cube[:8, 2:14, 2:14] = True
cls, score, why = os_.alt_view(sil_info(m, cube), sil_info(m[:, ::-1].copy(), cube), 0.8)
check("куб: объём симметричен - не HIGH (%s)" % cls, cls != os_.ALT_HIGH)
cls, _s, _w = os_.alt_view(a, sil_info(m[:, ::-1].copy(), turned, col=(200, 40, 200)), 0.1)
check("другой цвет - REJECT", cls == os_.ALT_REJECT)
cls, _s, _w = os_.alt_view(a, sil_info(m[:, ::-1].copy(), turned, phys={"armor": 60, "flammable": 255}), 0.8)
check("другая физика вещи (броня и горючесть) - REJECT", cls == os_.ALT_REJECT)
print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
