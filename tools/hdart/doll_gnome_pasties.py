#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Чёрные кружки GNOME отдельным слоем, как у LOKNAR и UBERGAL (DECISIONS 2026-11-05, 06.11): тело чистое, круг - только голым броням.
Фигура у всех 48 внешностей одна (перепись 07.11), поэтому место круга одно - по ареолам основы F9; волосы и рука у рта
лежат в теле голых броней, круг под ними обрезается их HD-слоями. Брони с открытой грудью - по классике 07.11:
NUDE, NUDE_DREAMLAND, EXPERIMENT (лента под грудью), EXPLORER_SEA (шланг посередине). Без видеокарты.
Пишет art/doll/pipe_pilot/gnome/pasties/gnome__4__pasties_<внешность>.png и тела без ареол в pasties/bodies. В мод не ставит.

    py -3.13 tools/hdart/doll_gnome_pasties.py
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cv2
import doll_ubergal_pasties as U
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "art", "doll", "pipe_pilot", "gnome", "heads", "layers")
OUT = os.path.join(ROOT, "art", "doll", "pipe_pilot", "gnome", "pasties")
SPOTS = ((295.4, 321.7), (347.0, 320.9))            # центры ареол основы F9 в точках HD, лист gnome_nip 07.11
RADIUS = 8.5                                        # ареола - около 7, круг закрывает её с краем; у UBERGAL медиана 8.9
SLOT = 4                                            # у голых броней свободен, у EXPERIMENT слот 3 занят лентой
ARMORS = ("STR_GNOME_NUDE_UC", "STR_GNOME_NUDE_DREAMLAND_UC", "STR_GNOME_EXPERIMENT_UC", "STR_GNOME_EXPLORER_SEA_UC",
          "STR_GNOME_EXPLORER_UC")                  # шуба распахнута, грудь между полами (лист кадров 07.11), круг под шубой
LOOKS = ["%s%d" % (g, n) for g in "FM" for n in range(24)]
BODIES = os.path.join(OUT, "bodies")                # тела без ареол: их ставит armor_chosen вместо heads/layers
FADE = (13.0, 18.0)                                 # заливка целиком до 13 (ареола 7, тёмная кайма и светлый край), к 18 сходит на нет


def cover(look):
    """Доля закрытия круга волосами и слоем головы (рука у рта) этой внешности."""
    a = np.zeros((U.H, U.W), np.float32)
    for name in ("gnome__10__head_%s.png", "gnome__13__hair_%s.png"):
        p = os.path.join(SRC, name % look.lower())
        if os.path.exists(p):
            a = np.maximum(a, np.asarray(Image.open(p).convert("RGBA"))[..., 3] / 255.0)
    return a


def clean(look, c):
    """Тело без ареол, как у LOKNAR и UBERGAL («грудь без сосков»): ареола заливается кожей вокруг, волосы поверх груди не трогаются."""
    px = np.asarray(Image.open(os.path.join(SRC, "gnome__2__%s_nude.png" % look.lower())).convert("RGBA"))
    out = px.copy()
    rgb = px[..., :3].astype(np.float32)
    ok = (px[..., 3] > 230) & (c < 0.05)
    for cx, cy in SPOTS:                            # кожа тянется к центру с краёв (Telea): местный перелив груди сохраняется
        x0, y0 = int(cx) - 32, int(cy) - 32
        sl = (slice(y0, y0 + 64), slice(x0, x0 + 64))
        yy, xx = np.mgrid[sl]
        r = np.hypot(xx - cx, yy - cy)
        mask = ((r <= FADE[1]) | ~ok[sl]).astype(np.uint8) * 255  # волосы в маске: их цвет в кожу не затекает
        fill = cv2.GaussianBlur(cv2.inpaint(px[sl][..., :3].copy(), mask, 6, cv2.INPAINT_TELEA).astype(np.float32), (0, 0), 3.0)
        t = np.clip((r - FADE[0]) / (FADE[1] - FADE[0]), 0, 1)
        w = (0.5 + 0.5 * np.cos(np.pi * t)) * (1 - c[sl])
        out[sl][..., :3] = np.clip(rgb[sl] * (1 - w[..., None]) + fill * w[..., None] + 0.5, 0, 255).astype(np.uint8)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(BODIES, exist_ok=True)
    base = U.circles([(x, y) for x, y in SPOTS], RADIUS).astype(np.float32)
    cut = 0
    for look in LOOKS:
        px = base.copy()
        c = cover(look)
        Image.fromarray(clean(look, c), "RGBA").save(os.path.join(BODIES, "gnome__2__%s_nude.png" % look.lower()))
        px[..., 3] *= 1 - c
        cut += bool((base[..., 3] * c).max() > 0)
        Image.fromarray(np.clip(px + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, "gnome__%d__pasties_%s.png" % (SLOT, look.lower())))
    print("кругов", len(LOOKS), "обрезано волосами или рукой", cut)
    dst = os.path.join(OUT, "chosen")                # папка установки: тела и круги, doll_race_install.py --race gnome_pasties
    os.makedirs(dst, exist_ok=True)
    for d in (OUT, BODIES):
        for f in os.listdir(d):
            if f.endswith(".png"):
                shutil.copyfile(os.path.join(d, f), os.path.join(dst, f))


if __name__ == "__main__":
    main()
