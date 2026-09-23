#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Зеркальные кадры набора: не рисовать, а переворачивать.

В наборе часть кадров - точное горизонтальное отражение других: одна и та же стена,
повёрнутая на карте другой стороной. Отражение ПОБАЙТОВОЕ, значит и свет в оригинале
отражён вместе с рисунком, и перевёрнутый HD-кадр близнеца будет ровно тем, что нужно.

Рисовать их порознь нельзя по двум причинам. Дорого: 7.4 процента кадров TERRAIN
помечены зеркальными. И хуже - результат РАСХОДИТСЯ: замер по 78 парам нашего прогона
дал среднюю разницу 19 из 255 между кадром и перевёрнутым близнецом, при том что от
оригинала кадр уходит всего на 9.5. На карте это две разные вещи там, где в оригинале
одна, повёрнутая.

    py -3 tools/hdart/mirror_frames.py --in art/TERRAIN/COMMERCE.PCK/returned/lora_cut
    py -3 tools/hdart/mirror_frames.py --all --dry-run

Перезаписывает младшим кадром пары старший. Ключ --dry-run только показывает.
"""
import argparse
import glob
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                      # noqa: E402
from PIL import Image                                   # noqa: E402

import tile_forge as tf                                 # noqa: E402


def mirror_pairs(sh):
    """Пары (i, j), i < j, где кадр j - точное горизонтальное отражение кадра i."""
    exact = {}
    for i in sh.frames():
        a = np.asarray(sh.frame(i), np.uint8)
        if a[..., 3].max() < 128:
            continue
        exact.setdefault(hashlib.blake2b(a.tobytes(), digest_size=16).hexdigest(), i)
    pairs = set()
    for i in sh.frames():
        a = np.asarray(sh.frame(i), np.uint8)
        if a[..., 3].max() < 128:
            continue
        flip = hashlib.blake2b(np.ascontiguousarray(a[:, ::-1]).tobytes(), digest_size=16).hexdigest()
        j = exact.get(flip)
        if j is not None and j != i:
            pairs.add((min(i, j), max(i, j)))
    return sorted(pairs)


def lum(a):
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def relight_err(A, B):
    """Ошибка рецепта на оригиналах: перевернуть A и вернуть ему яркость B."""
    m = B[..., 3] > 127
    if m.sum() == 0:
        return 999.0
    Af = np.ascontiguousarray(A[:, ::-1].astype(np.float32))
    k = (lum(B.astype(np.float32)) + 2.0) / (lum(Af) + 2.0)
    relit = np.clip(Af[..., :3] * k[..., None], 0, 255)
    return float(np.abs(relit - B[..., :3].astype(np.float32))[m].mean())


def hue_gap(A, B):
    """Расхождение ТОНА двух кадров: средний цвет пятна, делённый на свою яркость.

    Нужен предохранитель: силуэт совпадает и у вещей, ничего общего не имеющих. В
    ICEKING_RUINS из 96 пар с совпавшим силуэтом 20 - это провал во льду против снежного
    пола: ромб есть ромб. Без проверки рецепт подставил бы одно вместо другого. Считается по
    среднему цвету, а не попиксельно: в тенях тон шумит и порог начинает врать.
    Замер по набору: у зеркал 0.4-41, у перекрашенных копий 125-142."""
    def tone(X):
        m = X[..., 3] > 127
        if m.sum() == 0:
            return np.zeros(3, np.float32)
        v = X[..., :3].astype(np.float32)[m].mean(0)
        return v / (v.mean() + 1e-6)
    return float(np.abs(tone(A) - tone(B)).sum() * 255.0)


def silhouette_pairs(sh, thr=60.0, hue_thr=70.0):
    """Пары (i, j, ошибка), где СИЛУЭТ j - точное отражение силуэта i.

    Побайтового совпадения тут нет и быть не может: художник отражал форму, а свет
    оставлял с той же стороны. Поэтому mirror_pairs такую пару не видит - а глазами это
    одна и та же вещь, повёрнутая другим боком, и рисовать её второй раз незачем (R-054).

    Годной считается пара, у которой СОВПАЛ ТОН (иначе это перекрашенная копия, а не
    поворот) и поворот со своим светом укладывается в thr. Порог по свету нарочно мягкий:
    лист приёмки показал, что выведенный кадр неотличим от нарисованного и при расхождении
    25-28, а два независимых заказа одной картинки расходятся на 19 сами по себе.
    Кандидат берётся ЛУЧШИЙ по свету, а не первый попавшийся: в наборе рядом лежат
    несколько кадров с одинаковым силуэтом, и жадный выбор путает пары."""
    arrs = {}
    for i in sh.frames():
        a = np.asarray(sh.frame(i), np.uint8)
        if a.shape[-1] != 4 or a[..., 3].max() < 128:
            continue
        arrs[i] = a
    by_mask = {}
    for i, a in arrs.items():
        h = hashlib.blake2b((a[..., 3] > 127).tobytes(), digest_size=12).hexdigest()
        by_mask.setdefault(h, []).append(i)
    out, taken = [], set()
    for i in sorted(arrs):
        if i in taken:
            continue
        fh = hashlib.blake2b(np.ascontiguousarray(arrs[i][:, ::-1, 3] > 127).tobytes(),
                             digest_size=12).hexdigest()
        best = None
        for j in by_mask.get(fh, []):
            if j <= i or j in taken:
                continue
            if arrs[i].tobytes() == np.ascontiguousarray(arrs[j][:, ::-1]).tobytes():
                best = (0.0, j)
                break
            if hue_gap(arrs[i], arrs[j]) >= hue_thr:
                continue                                # другой цвет - это не поворот
            e = relight_err(arrs[i], arrs[j])
            if e < thr and (best is None or e < best[0]):
                best = (e, j)
        if best is not None:
            out.append((i, best[1], best[0]))
            taken.add(best[1])
    return out


def relit_frame(drawn_i, orig_i, orig_j):
    """HD-кадр близнеца: перевернуть нарисованный и вернуть свет из СВОЕГО оригинала.

    Множитель скалярный, по яркости - поканальные отношения к почти-совпадающей картинке
    уводят тон (грабли R-030). Карта множителя считается на оригинале и растягивается
    гладко, иначе на кадре появится сетка из ступенек базового пикселя."""
    W, H = drawn_i.size
    Af = np.asarray(drawn_i.transpose(Image.FLIP_LEFT_RIGHT).convert("RGBA"), np.float32)
    oi = np.asarray(orig_i, np.float32)[:, ::-1]
    oj = np.asarray(orig_j, np.float32)
    k = (lum(oj) + 2.0) / (lum(oi) + 2.0)
    kim = Image.fromarray(np.clip(k * 64.0, 0, 255).astype(np.uint8))
    kk = np.asarray(kim.resize((W, H), Image.BILINEAR), np.float32) / 64.0
    out = Af.copy()
    out[..., :3] = np.clip(Af[..., :3] * kk[..., None], 0, 255)
    return Image.fromarray(out.astype(np.uint8))


def do_dir(sheets, name, d, dry):
    sh = tf.Sheet(sheets, name + ".PCK")
    made = skipped = relit = 0
    for i, j, err in silhouette_pairs(sh):
        src = os.path.join(d, "%d.png" % i)
        dst = os.path.join(d, "%d.png" % j)
        if not os.path.exists(src):
            skipped += 1
            continue
        if not dry:
            im = Image.open(src).convert("RGBA")
            if err > 0.0:
                im = relit_frame(im, sh.frame(i), sh.frame(j))
            else:
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            im.save(dst)
        made += 1
        if err > 0.0:
            relit += 1
    return made, skipped, relit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--name", default="lora_cut", help="имя папки с рисунками")
    ap.add_argument("--dry-run", dest="dry", action="store_true")
    args = ap.parse_args()

    dirs = ([args.in_dir] if args.in_dir else
            sorted(glob.glob(os.path.join(args.sheets, "*.PCK", "returned", args.name))))
    if not dirs:
        sys.exit("нечего переворачивать")
    total = miss = 0
    for d in dirs:
        name = os.path.basename(os.path.dirname(os.path.dirname(d)))[:-4]
        made, skipped, relit = do_dir(args.sheets, name, d, args.dry)
        total += made
        miss += skipped
        if made or skipped:
            print("  %-22s перевёрнуто %3d (из них со своим светом %3d), "
                  "близнец не нарисован %2d" % (name, made, relit, skipped))
    print("итого: %s %d кадров%s"
          % ("перевернул бы" if args.dry else "перевёрнуто", total,
             (", без пары %d" % miss) if miss else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
