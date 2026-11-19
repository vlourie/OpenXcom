# -*- coding: utf-8 -*-
r"""XP-000510: куст JUNGLEBITS:4 и родня (NEOJUNGLE:4, IDT_ASIA:4) - HD принятого JUNGLE:4, цвет классики своего набора
(obj_derive.transfer, R-030, как t384_bush.py). Рисунок классики JUNGLEBITS:4 = JUNGLE:4 без 49 пикселей травы у основания
(индексы общих 777 пикселей совпадают), у NEOJUNGLE:4 и IDT_ASIA:4 маска равна JUNGLE:4. Альфа: HD основы, у JUNGLEBITS:4 -
по своей маске классики. Без видеокарты. В МОД НИЧЕГО НЕ СТАВИТ: art/tickets/hb509/bush4/<НАБОР>_<кадр>.png."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p509_common as pc
import numpy as np
from PIL import Image
from scipy import ndimage
import ticket_scene as ts
import obj_derive as od
import probe_object as po

OUT = os.path.join("art", "tickets", "hb509", "bush4")
BASE = ("JUNGLE", 4)
MEMBERS = [("JUNGLEBITS", 4), ("NEOJUNGLE", 4), ("IDT_ASIA", 4)]


def small(im):
    return Image.fromarray(np.ascontiguousarray(np.asarray(im)[::4, ::4]), "RGBA")


def main():
    sc = ts.Scene()
    hd = sc.hd(*BASE)
    ob = sc.classic(*BASE)
    os.makedirs(OUT, exist_ok=True)
    for s, f in MEMBERS:
        ot = sc.classic(s, f)
        new = od.transfer(hd, small(ob), small(ot))
        a = np.asarray(new).copy()
        mt = np.asarray(ot)[..., 3] > 0
        mb = np.asarray(ob)[..., 3] > 0
        if (mt != mb).any():
            # своя маска: xBRZ-спрямление x4, не шире силуэта классики на 2 пикселя HD; перед этим убрать из неё травяную каёмку
            sm = np.asarray(po.smooth_silhouette(small(ot).split()[3].point(lambda v: 255 if v else 0), 4), np.float32) / 255.0
            sil4 = np.kron(mt[::4, ::4], np.ones((4, 4), bool))
            sm = np.where(ndimage.binary_dilation(sil4, iterations=2), sm, 0.0)
            a[..., 3] = np.rint(a[..., 3] * np.clip(sm, 0, 1)).astype(np.uint8)
        Image.fromarray(a, "RGBA").save(os.path.join(OUT, "%s_%d.png" % (s, f)))
        print(s, f, "маска совпала с основой" if not (mt != mb).any() else "маска своя, убрано пикселей классики: %d" % int((mb & ~mt).sum() // 16))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
