# -*- coding: utf-8 -*-
r"""Тикет XP-000477: тон кирпича кадра камина по одобренному верху WESTFLOOR:9 (3802). Модель Qwen рисует низ и звено
светлее и розовее верха (match_tone 0.7 держит тон к классике, а не к соседнему кадру), на стыке видна полоса.
tone_match(im, ref, regions): по пикселям кирпича (насыщенное красное) считает коэффициент по каналам "верх / кадр" на гранях
(левая, правая) и умножает на него кирпич; серый камень (арка) гасится мягче - корнем из среднего коэффициента.
Альфа не меняется. Только цвет."""
import numpy as np
from PIL import Image


def _brick(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    sat = (r - g) / np.maximum(r, 1.0)
    return np.clip((sat - 0.30) / 0.15, 0.0, 1.0)


def _mean(im, box):
    x0, x1, y0, y1 = box
    a = np.asarray(im).astype(np.float32)[y0:y1, x0:x1]
    w = _brick(a) * (a[..., 3] > 250)
    if w.sum() < 50:
        return None
    return (a[..., :3] * w[..., None]).sum((0, 1)) / w.sum()


def tone_match(im, ref, ref_boxes, im_boxes):
    """ref_boxes / im_boxes - списки пар (x0, x1, y0, y1) одной грани в эталоне и в кадре."""
    gains = []
    for rb, ib in zip(ref_boxes, im_boxes):
        r, c = _mean(ref, rb), _mean(im, ib)
        if r is not None and c is not None:
            gains.append(r / c)
    gain = np.mean(gains, 0)
    a = np.asarray(im).astype(np.float32).copy()
    w = _brick(a)[..., None]
    stone = float(np.sqrt(gain.mean()))
    rgb = a[..., :3]
    out = w * (rgb * gain) + (1 - w) * (rgb * stone)
    a[..., :3] = np.clip(out, 0, 255)
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a.astype(np.uint8), "RGBA"), gain


# эталон - верх WESTFLOOR:9 из установки (3802); грани кадров: (x0, x1, y0, y1) в пикселях x4
REF_BOXES = [(8, 60, 70, 140), (70, 120, 70, 140)]
FRAME_BOXES = {10: [(8, 60, 40, 58), (70, 120, 70, 150)], 8: [(8, 60, 70, 140), (70, 120, 70, 140)]}
_REF = []


def tone(im, f, report=None):
    import t405_409_gen as g
    if not _REF:
        _REF.append(g.hd_now("WESTFLOOR", 9).convert("RGBA"))
    out, gain = tone_match(im, _REF[0], REF_BOXES, FRAME_BOXES[f])
    if report is not None:
        report.append((f, [round(float(x), 3) for x in gain]))
    return out
