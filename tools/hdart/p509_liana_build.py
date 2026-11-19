# -*- coding: utf-8 -*-
r"""XP-000509: лианы MUJUNGLE:17 (поверх пола дорожки) и перекраски: берёт art/tickets/hb509/gen/liana/<зерно>.png (основа), цвет члена -
obj_derive.transfer по классике (R-030). Члены без своего одобренного HD: MUJUNGLE, MUCONCRETE, WHITECASTLE, CATACOMB, SIETCH (:17).
Члены со своим одобренным HD (MUJUNGLE_2:17 relief_object, SIETCH_DARK:17 wall_exact_B2) НЕ трогаются без слова Vitali (R-457).
В МОД НИЧЕГО НЕ СТАВИТ: art/tickets/hb509/liana/<зерно>/<НАБОР>_17.png."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p509_common as pc
import numpy as np
from PIL import Image
import ticket_scene as ts
import obj_derive as od

GEN = os.path.join("art", "tickets", "hb509", "gen", "liana")
OUT = os.path.join("art", "tickets", "hb509", "liana")
MEMBERS = ["MUCONCRETE", "WHITECASTLE", "CATACOMB", "SIETCH"]


def small(im):
    return Image.fromarray(np.ascontiguousarray(np.asarray(im)[::4, ::4]), "RGBA")


def build(seed):
    sc = ts.Scene()
    base = Image.open(os.path.join(GEN, "%d.png" % seed)).convert("RGBA")
    ob = sc.classic("MUJUNGLE", 17)
    d = os.path.join(OUT, str(seed))
    os.makedirs(d, exist_ok=True)
    base.save(os.path.join(d, "MUJUNGLE_17.png"))
    mb = np.asarray(ob)[..., 3] > 0
    for s in MEMBERS:
        ot = sc.classic(s, 17)
        mt = np.asarray(ot)[..., 3] > 0
        if (mt != mb).any():
            print(s, "маска отличается на пикселей x4:", int((mt != mb).sum()))
        new = od.transfer(base, small(ob), small(ot))
        a = np.asarray(new).copy()
        a[..., 3] = np.asarray(base)[..., 3]
        Image.fromarray(a, "RGBA").save(os.path.join(d, "%s_17.png" % s))
    print("зерно %d: %d кадров ->" % (seed, 1 + len(MEMBERS)), d)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for a in sys.argv[1:] or ["5171", "5172"]:
        build(int(a))
