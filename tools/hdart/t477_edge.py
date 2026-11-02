# -*- coding: utf-8 -*-
r"""Тикет XP-000477, низ :10 и звено :8: верхняя грань кадра скрыта кадром над ним (на уровень выше), видна лишь кромка по V -
линии от угла (0, 32) к вершине (64, 64) в пикселях x4 - светлая полоска фаски верхней грани. Полоса [V - up, V + down] по
вертикали перекрашивается отражением от V + down + 1 (кирпич грани ниже кромки), верхние 6 строк полосы - плавным переходом
(иначе ступень на границе полосы); яркие крапинки в полосе обрезаются по p97 кирпича под ней. Альфа не меняется, силуэт тот же."""
import numpy as np
from PIL import Image


def _vy(x):
    return 32 + int(round((63.5 - abs(x - 63.5)) / 2.0))     # 32 у края, 64 у вершины


def repaint_v(im, up=14, down=7, ramp=6):
    a = np.asarray(im).copy()
    H, W = a.shape[:2]
    src = a.astype(np.float32)
    out = src.copy()
    for x in range(W):
        vy = _vy(x)
        c = vy + down + 1
        for y in range(vy - up, vy + down + 1):
            s = 2 * c - y
            if 0 <= y < H and s < H and a[y, x, 3] > 0 and a[s, x, 3] > 0:
                w = min(1.0, (y - (vy - up) + 1) / float(ramp))
                out[y, x, :3] = src[y, x, :3] * (1 - w) + src[s, x, :3] * w
    # крапинки: в полосе не светлее p97 кирпича под ней (окно +-8 столбцов, строки V+down+2 .. V+down+30)
    lim = np.full((W, 3), 255.0, np.float32)
    for x in range(W):
        vy = _vy(x)
        x0, x1 = max(0, x - 8), min(W, x + 9)
        y0, y1 = vy + down + 2, min(H, vy + down + 30)
        blk = out[y0:y1, x0:x1]
        m = blk[..., 3] > 250
        if m.sum() > 20:
            lim[x] = np.percentile(blk[m][:, :3], 97, axis=0)
    for x in range(W):
        vy = _vy(x)
        for y in range(max(0, vy - up), min(H, vy + down + 1)):
            if out[y, x, 3] > 0:
                out[y, x, :3] = np.minimum(out[y, x, :3], lim[x])
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def defringe(im, depth=4):
    """Светлая кайма по краю силуэта (остаток подложки в cut_out): цвет полосы шириной depth пикселей x4 по краю альфы
    заменяется цветом ближайшего пикселя глубже. Альфа не меняется."""
    from scipy import ndimage as ndi
    a = np.asarray(im).copy()
    mask = a[..., 3] > 128
    dist = ndi.distance_transform_edt(mask)
    inner = mask & (dist > depth)
    idx = ndi.distance_transform_edt(~inner, return_distances=False, return_indices=True)
    band = (a[..., 3] > 0) & ~inner
    a[band, :3] = a[idx[0][band], idx[1][band], :3]
    return Image.fromarray(a, "RGBA")
