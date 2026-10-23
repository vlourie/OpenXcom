#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000277: впадины 2x2 (MOUNT* 7 наборов, 28 кадров) вышли плоскими - у ямы нет вала земли по краю.

Рецепт t262_pits.py (форма и цвет по классике целого холста 2x2, R-265) плюс вал и глубина:
  - вал: полоса отсыпанной земли снаружи края ямы (ширина ~9 пикселей HD, высота rim_h), цвет - смесь грунта и
    земли ямы по краю (rim_mix), свет сверху-слева: верхне-левый вал светлее, внутренний скат на той же стороне темнее;
  - глубина: скат внутрь по полю расстояния, круче (depth) и ещё тёмная тень у верхнего-левого внутреннего края;
  - общая высотная поверхность z (яма минус вал) освещается одним источником - вал и стенка читаются как рельеф.
Группы кадров, основы грунта и правила маски берутся из t262_pits.GROUPS (группа B каждого набора).

    py -3.13 tools/hdart/t277_pits_rim.py [--sets MOUNT,MOUNTMUD]    # кадры в art/tickets/t277_pits/out/<набор>/<кадр>.png
"""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import t262_pits as P  # noqa: E402

OUT = os.path.join(P.ROOT, "art", "tickets", "t277_pits", "out")
K, OFF, CW, CH, LUM, blur = P.K, P.OFF, P.CW, P.CH, P.LUM, P.blur


def render_pit2(setname, g, k=K, seed=11):
    cl = np.array(P.compose(g["frames"], lambda f: P.classic(setname, f), 1)).astype(np.float32)
    pit1 = P.pit_mask_classic(cl, g.get("rule", "pal"), g.get("keep_all", False))
    H, W = CH * k, CW * k
    m1 = blur(pit1.astype(np.float32), 0.8)
    m = cv2.resize(m1, (W, H), interpolation=cv2.INTER_CUBIC)
    m = m + 0.07 * P.smooth_noise((H, W), 5.0, seed)
    t = np.clip((m - 0.38) / 0.24, 0, 1)
    m = t * t * (3 - 2 * t)
    w = pit1.astype(np.float32)
    es = g.get("esig", 0.9)
    ec = np.zeros((CH, CW, 3), np.float32)
    idx = ndi.distance_transform_edt(~pit1, return_distances=False, return_indices=True)
    for c in range(3):
        ec[..., c] = blur(cl[..., c] * w, es) / np.maximum(blur(w, es), 1e-3)
        near = cl[..., c][idx[0], idx[1]]
        ec[..., c] = np.where(blur(w, es) > 0.15, ec[..., c], near)
    E = np.stack([cv2.resize(ec[..., c], (W, H), interpolation=cv2.INTER_CUBIC) for c in range(3)], -1)
    inside = m > 0.5
    Lc = E @ LUM
    Lm = float(Lc[inside].mean())
    shade = np.clip((Lc / Lm), 0.3, 1.8) ** g.get("contrast", 0.5)
    # --- рельеф: яма и вал
    d_in = ndi.distance_transform_edt(inside).astype(np.float32)
    d_out = ndi.distance_transform_edt(~inside).astype(np.float32)
    depth = g.get("depth_rim", 18.0)
    rim_h = g.get("rim_h", 8.0)
    r0, rw = g.get("rim_r0", 3.0), g.get("rim_w", 5.0)
    rim = np.exp(-((d_out - r0) / rw) ** 2) * (~inside)
    rim = rim * (0.85 + 0.3 * (0.5 + 0.5 * P.smooth_noise((H, W), 9.0, seed + 1)))     # вал неровный
    z = -(1 - np.exp(-d_in / 10.0)) * depth + rim_h * rim
    z = blur(z, 1.6)
    gy, gx = np.gradient(z)
    nz = 1 / np.sqrt(1 + gx * gx + gy * gy)
    lx, ly, lz = -0.55, -0.55, 0.65
    geo = np.clip(((-gx * lx - gy * ly + lz) * nz) / lz, 0.5, 1.45)
    det, _ = P.detail_field(setname, g, m, (H, W), seed)
    sd = det[inside].std() if inside.any() else 1.0
    det = det / (sd + 1e-6)
    earth = E * shade[..., None] * geo[..., None] * (1 + g.get("grain", 0.09) * det[..., None])
    gm = blur(m, 4.0)
    inner = np.clip(m * (1 - gm) * 2.0, 0, 1)
    earth = earth * (1 - 0.3 * inner[..., None])
    # --- грунт и вал
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for pos, f in g["base"].items():
        ox, oy = OFF[pos]
        base.alpha_composite(P.hd_open(setname, f), (ox * k, oy * k))
    B = np.array(base).astype(np.float32)
    # цвет вала - земля по краю ямы (ближайшие пиксели внутри), смешанная с грунтом
    edge_idx = ndi.distance_transform_edt(~inside, return_distances=False, return_indices=True)
    Eedge = E[edge_idx[0], edge_idx[1]] * 0.85
    mix = np.clip(rim * g.get("rim_mix", 0.42), 0, 1)[..., None]
    ground = B[..., :3] * (1 - mix) + Eedge * mix
    ground = ground * np.clip(geo, 0.6, 1.4)[..., None] ** 0.9 * (1 + g.get("lip", 0.0) * 0)
    ground = ground * (1 + 0.10 * det[..., None] * mix)
    rgb = np.clip(ground * (1 - m[..., None]) + earth * m[..., None], 0, 255)
    return rgb, B[..., 3] > 0, m


def run(sets=None):
    res = {}
    for setname, groups in P.GROUPS.items():
        if sets and setname not in sets:
            continue
        for g in groups:
            if g.get("name") != "B":
                continue
            rgb, cover, m = render_pit2(setname, g)
            outs = P.cut_frames(setname, g, rgb, cover)
            d = os.path.join(OUT, setname)
            os.makedirs(d, exist_ok=True)
            for f, im in outs.items():
                im.save(os.path.join(d, "%d.png" % f))
                res[(setname, f)] = os.path.join(d, "%d.png" % f)
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sets")
    a = ap.parse_args()
    res = run(a.sets.split(",") if a.sets else None)
    print("кадров: %d в %s" % (len(res), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
