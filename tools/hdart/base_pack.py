#!/usr/bin/env python3
"""
base_pack.py - запись HD-клеток базы (hd/BASEBITS.PCK) в формате с неподвижной картинкой.

Постройка пишется тремя слоями, движок (HdBase::draw) кладёт их друг на друга:

    <N>.png            - неподвижная чистая картинка клетки, без эффектов
    <N>.v1..v16.png    - постоянная петля (вода, пузыри): только прямоугольник, где она меняет клетку
    <N>.b1..bM.png     - вспышка раз в `every` секунд: тоже прямоугольник, в нём и петля
    <N>.anim.txt       - размер клетки, прямоугольники петли и вспышки, период вспышки

Прямоугольник кратен пикселю классики (K = 4 пикселя пака) и с запасом в один такой пиксель:
тогда при любом масштабе экрана он ложится на целые пиксели. Фазы по 200 мс (BaseView::blink).
Вспышка начинается с фазы 0 петли, поэтому петля внутри вспышки идёт тем же счётом.
"""
import os
import re

import numpy as np
from PIL import Image

K = 4
ENC_W = "utf-8-sig"


def _rect(frames, base, alpha):
    """Прямоугольник [x0, y0, x1, y1), где хоть одна фаза отличается от base, или None."""
    diff = np.zeros(alpha.shape, bool)
    for f in frames:
        diff |= (np.abs(f - base).max(-1) > 0.5 / 255) & (alpha > 0)
    ys, xs = np.nonzero(diff)
    if not len(xs):
        return None
    h, w = alpha.shape
    x0 = max(0, (xs.min() // K - 1) * K)
    y0 = max(0, (ys.min() // K - 1) * K)
    x1 = min(w, (xs.max() // K + 2) * K)
    y1 = min(h, (ys.max() // K + 2) * K)
    return x0, y0, x1, y1


def _rgba(f, alpha):
    return np.concatenate([np.clip(f * 255 + 0.5, 0, 255), alpha[..., None] * 255], 2).astype(np.uint8)


def clean(dest, index):
    """Снимает прежние файлы клетки: иначе от старой петли останется хвост фаз."""
    pat = re.compile(r"^%d\.(?:[vb]\d+\.png|png|anim\.txt)$" % index)
    for name in os.listdir(dest):
        if pat.match(name):
            os.remove(os.path.join(dest, name))


def write(out_dir, indices, cols, tile_w, tile_h, alpha, still, loop=None, burst=None, every=0, source=""):
    """Пишет постройку: still - кадр без эффектов (h, w, 3), loop - 16 кадров постоянной петли или
    None, burst - кадры вспышки (уже с петлёй и огибающей) или None; every - период вспышки, с.
    Клетки - строка за строкой, как в BaseView. Возвращает число записанных файлов."""
    dest = os.path.join(out_dir, "hd", "BASEBITS.PCK")
    os.makedirs(dest, exist_ok=True)
    written = 0
    for n, index in enumerate(indices):
        y, x = divmod(n, cols)
        sy, sx = slice(y * tile_h, (y + 1) * tile_h), slice(x * tile_w, (x + 1) * tile_w)
        a = alpha[sy, sx]
        s = still[sy, sx]
        clean(dest, index)
        Image.fromarray(_rgba(s, a), "RGBA").save(os.path.join(dest, "%d.png" % index))
        written += 1
        lines = ["# " + (source or "base_pack.py") + " - see tools/hdart/base_pack.py",
                 "size %d %d" % (tile_w, tile_h)]
        loop_t = [f[sy, sx] for f in loop] if loop else None
        burst_t = [f[sy, sx] for f in burst] if burst else None
        if loop_t:
            r = _rect(loop_t, s, a)
            if r:
                x0, y0, x1, y1 = r
                for p, f in enumerate(loop_t, 1):
                    Image.fromarray(_rgba(f, a)[y0:y1, x0:x1], "RGBA").save(os.path.join(dest, "%d.v%d.png" % (index, p)))
                    written += 1
                lines.append("loop %d %d %d %d" % (x0, y0, x1 - x0, y1 - y0))
        if burst_t and every > 0:
            # вспышка сравнивается с тем, что под ней: петлёй той же фазы, иначе неподвижной
            under = [loop_t[q % len(loop_t)] for q in range(len(burst_t))] if loop_t else [s] * len(burst_t)
            diff = [b - u + s for b, u in zip(burst_t, under)]
            r = _rect(diff, s, a)
            if r:
                x0, y0, x1, y1 = r
                for q, f in enumerate(burst_t, 1):
                    Image.fromarray(_rgba(f, a)[y0:y1, x0:x1], "RGBA").save(os.path.join(dest, "%d.b%d.png" % (index, q)))
                    written += 1
                lines.append("burst %d %d %d %d" % (x0, y0, x1 - x0, y1 - y0))
                lines.append("every %d" % every)
        with open(os.path.join(dest, "%d.anim.txt" % index), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        written += 1
    return written


def envelope(q, total, ramp=3):
    """Сила вспышки в фазе q из total: нарастает и гаснет за ramp фаз, края - ноль."""
    return float(np.clip(min(q, total - 1 - q) / float(ramp), 0.0, 1.0))
