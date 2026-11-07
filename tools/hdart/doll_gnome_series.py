#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Серии GNOME без видеокарты - копии готовой HD-головы, как в классике (перепись 07.11):
HEADBM_<внешность> (слот 10 брони MASTERBLASTER) - окно 12x13 в шлеме: лицо тела+головы+волос, сдвинутое на (131, -23)
(у 34 из 48 совпадение точка в точку, у M0 сдвиг по строкам -24; F15 и M3 в классике перерисованы, у них тот же сдвиг);
GLASSES_<внешность> (слот 12, CAMO_PAINT, 6 внешностей) - глаза тела поверх маски: те же точки HD-головы.
Под HD кладётся классика x4, чтобы полупрозрачный край волос не дал дыр. Пишет art/doll/pipe_pilot/gnome/series/. В мод не ставит.

    py -3.13 tools/hdart/doll_gnome_series.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cv2
import doll_b2_render as db
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "art", "doll", "pipe_pilot", "gnome", "heads", "layers")
OUT = os.path.join(ROOT, "art", "doll", "pipe_pilot", "gnome", "series")
K = 4
SHIFT = (131, -23)
SHIFT_OF = {"M0": (131, -24)}                        # подбор сдвига по классике 07.11
SOFT = 1.5                                          # край очков без лесенки x4 (R-121)
LOOKS = ["%s%d" % (g, n) for g in "FM" for n in range(24)]


def hd_face(look):
    """HD тело, голова и волосы внешности одним RGBA 1280x800."""
    c = Image.new("RGBA", (db.W * K, db.H * K), (0, 0, 0, 0))
    for n in ("gnome__2__%s_nude", "gnome__10__head_%s", "gnome__13__hair_%s"):
        p = os.path.join(SRC, (n % look.lower()) + ".png")
        if os.path.exists(p):
            c.alpha_composite(Image.open(p).convert("RGBA"))
    return np.asarray(c, np.float32)


def big(idx, pal):
    return cv2.resize(db.to_rgba(idx, pal).astype(np.float32), (db.W * K, db.H * K), interpolation=cv2.INTER_NEAREST)


def under(top, bottom):
    """top поверх bottom, оба RGBA float."""
    a = top[..., 3:] / 255.0
    rgb = top[..., :3] * a + bottom[..., :3] * (1 - a)
    return np.dstack([rgb, np.maximum(top[..., 3], bottom[..., 3])])


def headbm(look, files, pal):
    idx = db.load_indices(files["GNOME__10__HEADBM_" + look])
    m = idx != 0
    dx, dy = SHIFT_OF.get(look, SHIFT)
    face = hd_face(look)
    moved = np.zeros_like(face)
    sx, sy = dx * K, dy * K
    H, W = face.shape[:2]
    moved[max(0, sy):H + min(0, sy), max(0, sx):W + min(0, sx)] = face[max(0, -sy):H - max(0, sy), max(0, -sx):W - max(0, sx)]
    res = under(moved, big(idx, pal))
    m4 = cv2.resize(m.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0     # окно - прямоугольник, край прямой
    res[~m4] = 0
    res[m4, 3] = 255
    return res


def glasses(look, files, pal):
    idx = db.load_indices(files["GNOME__12__GLASSES_" + look])
    m = (idx != 0).astype(np.float32)
    face = hd_face(look)
    H, W = face.shape[:2]
    a = cv2.GaussianBlur(cv2.resize(m, (W, H), interpolation=cv2.INTER_NEAREST), (0, 0), SOFT)
    res = under(face, big(idx, pal))
    res[..., 3] = np.minimum(res[..., 3], a * 255)
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    files, pal = db.sprite_files(), db.game_palette()
    n = 0
    for look in LOOKS:
        for key, fn in (("GNOME__10__HEADBM_", headbm), ("GNOME__12__GLASSES_", glasses)):
            if key + look not in files or not (db.load_indices(files[key + look]) != 0).any():
                continue
            px = fn(look, files, pal)
            Image.fromarray(np.clip(px + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, (key + look).lower() + ".png"))
            n += 1
    print("серий", n, "в", OUT)


if __name__ == "__main__":
    main()
