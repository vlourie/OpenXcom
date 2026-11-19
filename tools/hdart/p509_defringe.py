# -*- coding: utf-8 -*-
"""Снять светло-бежевую кайму подложки у края сгенерированного кадра (R-089): у края (до BAND пикселей HD) светлые малонасыщенные
пиксели - не рисунок, а остаток подложки и тень модели. Альфа там гасится мягко, цвет остатка - цвет ближайшего внутри."""
import numpy as np
from PIL import Image
from scipy import ndimage

BAND = 7


def hsv(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1)
    return mx / 255.0, np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0.0)


def defringe(im, vmin=0.50, smax=0.30, band=BAND, verbose=False):
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    al = a[..., 3] / 255.0
    solid = al > 0.5
    dist = ndimage.distance_transform_edt(solid)          # внутри: расстояние до края
    v, s = hsv(a[..., :3])
    cand = solid & (dist <= band) & (v > vmin) & (s < smax)
    # только связные с краем куски: одиночные блики внутри листа не трогаем
    lab, n = ndimage.label(cand)
    keep = np.zeros_like(cand)
    edge = dist <= 1.5
    for i in range(1, n + 1):
        m = lab == i
        if (m & edge).any() and m.sum() >= 2:
            keep |= m
    keep = ndimage.binary_dilation(keep, iterations=1)
    kill = ndimage.gaussian_filter(keep.astype(np.float32), 0.9)
    out = a.copy()
    out[..., 3] = al * 255.0 * np.clip(1.0 - kill * 1.4, 0, 1)
    # цвет оставшихся краевых пикселей, что были рядом с каймой: из глубины (ближайший непрозрачный не-кайма)
    core = solid & ~ndimage.binary_dilation(keep, iterations=2)
    _, ind = ndimage.distance_transform_edt(~core, return_indices=True)
    near = (kill > 0.05) & (out[..., 3] > 8)
    out[..., :3][near] = a[..., :3][ind[0], ind[1]][near]
    if verbose:
        print("кайма: пикселей %d, цвет заменён %d" % (int(keep.sum()), int(near.sum())))
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8), "RGBA")
