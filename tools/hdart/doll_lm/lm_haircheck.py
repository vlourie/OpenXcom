"""Волосы HD по маске волос классики (слой LAMIA__13__HAIR_<в>): доля точек маски, где HD по цвету ближе к коже лица
этой внешности, чем к цвету волос классики (на k=1). Большая доля - причёска не на месте классики."""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import cv2
import numpy as np
from PIL import Image
import doll_b2_render as db
import doll_photo_pilot as dp
L = r"E:\tmp\doll_ingame\lm\layers"
F, PAL = db.sprite_files(), db.game_palette()


def lab(rgb):
    return cv2.cvtColor(np.ascontiguousarray(rgb.astype(np.uint8)), cv2.COLOR_RGB2LAB).astype(np.float32)


for lk in ["F%d" % i for i in range(8)] + ["M%d" % i for i in range(8)]:
    hm = dp.layer_mask(F, "LAMIA__13__HAIR_%s" % lk)
    body = db.to_rgba(db.load_indices(F["LAMIA__2__%s_NUDE" % lk]), PAL)
    hair = db.to_rgba(db.load_indices(F["LAMIA__13__HAIR_%s" % lk]), PAL)
    hd = np.asarray(Image.open(os.path.join(L, "lamia__13__hair_%s.png" % lk.lower())).convert("RGBA"), np.float32)
    hd1 = cv2.resize(hd, (db.W, db.H), interpolation=cv2.INTER_AREA)
    a = hd1[..., 3:4] / 255.0
    hd1 = hd1[..., :3] * a + 128 * (1 - a)
    face = dp.layer_mask(F, "LAMIA__10__HEAD_%s" % lk) & ~hm
    skin = lab(body[..., :3])[face].mean(0)
    hl, cl = lab(hd1), lab(hair[..., :3])
    ds = np.sqrt(((hl - skin) ** 2).sum(-1))
    dh = np.sqrt(((hl - cl) ** 2).sum(-1))
    bad = hm & (ds < dh)
    print("%s волос в классике %4d, в HD похоже на кожу %3.0f%%" % (lk, hm.sum(), 100.0 * bad.sum() / max(1, hm.sum())))
