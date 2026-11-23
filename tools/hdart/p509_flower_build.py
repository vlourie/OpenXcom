# -*- coding: utf-8 -*-
r"""XP-000509: красный цветок 2x2 JUNGLEBITS:23-26 + копии JUNGLESTYX:23-26. Берёт сгенерированное (art/tickets/hb509/gen/flower/<зерно>.png),
снимает кайму подложки, режет по клеткам (obj_series.split), JUNGLESTYX - переносом цвета классики (obj_derive.transfer).
В МОД НИЧЕГО НЕ СТАВИТ: art/tickets/hb509/flower/<зерно>/<НАБОР>_<кадр>.png."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p509_common as pc
import p509_defringe as df
import numpy as np
from PIL import Image
import ticket_scene as ts
import obj_series as osr
import obj_derive as od

GEN = os.path.join("art", "tickets", "hb509", "gen", "flower")
OUT = os.path.join("art", "tickets", "hb509", "flower")
AT = {24: (16, 0, 0), 26: (32, 8, 0), 23: (0, 8, 0), 25: (16, 16, 0)}
ORDER = [24, 23, 26, 25]


def small(im):
    return Image.fromarray(np.ascontiguousarray(np.asarray(im)[::4, ::4]), "RGBA")


def comp_of(sc):
    spr = {}
    for f in ORDER:
        spr[("JUNGLEBITS", f)] = sc.classic("JUNGLEBITS", f).resize((32, 40), Image.NEAREST)
    return {"members": [(("JUNGLEBITS", f), AT[f]) for f in ORDER], "spr": spr, "pl": {k: 0 for k in spr}}


def build(seed):
    sc = ts.Scene()
    comp = comp_of(sc)
    whole, at = osr.compose(comp)
    cut = df.defringe(Image.open(os.path.join(GEN, "%d.png" % seed)).convert("RGBA"))
    pieces = osr.split(cut, comp, at, 2)
    d = os.path.join(OUT, str(seed))
    os.makedirs(d, exist_ok=True)
    for (s, f), im in pieces.items():
        im.save(os.path.join(d, "%s_%d.png" % (s, f)))
        # копия JUNGLESTYX: тот же кусок, цвет классики своего набора
        ot = sc.classic("JUNGLESTYX", f)
        if ot is None:
            print("JUNGLESTYX:%d классики нет" % f)
            continue
        ob = sc.classic(s, f)
        same = (np.asarray(ob)[..., 3] > 0) == (np.asarray(ot)[..., 3] > 0)
        if not same.all():
            print("JUNGLESTYX:%d маска отличается на %d пикселей x4" % (f, int((~same).sum())))
        new = od.transfer(im, small(ob), small(ot))
        a = np.asarray(new).copy()
        a[..., 3] = np.asarray(im)[..., 3]
        Image.fromarray(a, "RGBA").save(os.path.join(d, "JUNGLESTYX_%d.png" % f))
    print("зерно %d: 8 кадров ->" % seed, d)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for a in sys.argv[1:] or ["5092", "5093"]:
        build(int(a))
