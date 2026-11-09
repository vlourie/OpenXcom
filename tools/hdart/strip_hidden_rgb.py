#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Обнулить RGB под нулевой альфой в HD-арте и пересохранить PNG плотнее (видимые пиксели не меняются).

Куклы (hd/UI/<раса>__N__*.png) и террейн (hd/TERRAIN/**.png): 79 % / 36 % веса - цвет в полностью прозрачных
пикселях. Движок масштабирует кадры в предумноженной альфе (HdSprites::resample), декодер -
lodepng LCT_RGBA 8 (HdSprites::decodePng), поэтому цвет при альфе 0 не виден (аудит 09.11, 40-size.md).

Группы: dolls, terrain - всегда; cards (прочие PNG в hd/UI, педия и экраны) - только с --cards и только
файлы RGBA с альфой 255 везде: пересохраняются как RGB (lodepng при чтении даёт тот же RGBA с альфой 255).
Файл другого режима/глубины (палитра, RGB, 16 бит) пропускается. Новый файл не меньше старого - не пишется.
Запись через временный файл рядом и os.replace; с --verify новые байты перечитываются до подмены:
альфа побайтно та же, RGB там, где альфа>0 побайтно тот же (для cards - всё RGBA равно), иначе файл
остаётся прежним и попадает в отчёт со статусом VERIFY_FAIL.

    py -3.13 tools/hdart/strip_hidden_rgb.py --dry-run --sample 200
    py -3.13 tools/hdart/strip_hidden_rgb.py --verify --report out.tsv           (куклы и террейн)
    py -3.13 tools/hdart/strip_hidden_rgb.py --root <другая копия мода hd>/hd --verify
Править игру под очередью editq; после - Ctrl+F8 и hdtest_compare.py (k=1 и k=4).
"""
import argparse
import io
import os
import re
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

DOLL = re.compile(r"__\d+__", re.I)
DEFAULT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "user", "mods", "hd", "hd")


def collect(root, groups):
    files = {g: [] for g in groups}
    ui = os.path.join(root, "UI")
    if os.path.isdir(ui):
        for n in sorted(os.listdir(ui)):
            if not n.lower().endswith(".png"):
                continue
            g = "dolls" if DOLL.search(n) else "cards"
            if g in files:
                files[g].append(os.path.join(ui, n))
    if "terrain" in files:
        for d, _, ns in os.walk(os.path.join(root, "TERRAIN")):
            files["terrain"] += [os.path.join(d, n) for n in sorted(ns) if n.lower().endswith(".png")]
    return files


def encode(img):
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True, compress_level=9)
    return buf.getvalue()


def process(args):
    """-> (path, status, before, after). status: OK, SKIP_xxx, NOGAIN, VERIFY_FAIL, ERR:..."""
    path, group, write, verify = args
    try:
        before = os.path.getsize(path)
        with Image.open(path) as im:
            im.load()
            if im.mode != "RGBA":
                return path, "SKIP_" + im.mode, before, before
            arr = np.array(im, dtype=np.uint8)
        if group == "cards":
            if not (arr[..., 3] == 255).all():
                return path, "SKIP_ALPHA", before, before
            new_img = Image.fromarray(arr[..., :3], "RGB")
        else:
            out = arr.copy()
            out[arr[..., 3] == 0, :3] = 0
            new_img = Image.fromarray(out, "RGBA")
        data = encode(new_img)
        if len(data) >= before:
            return path, "NOGAIN", before, before
        if not write:
            return path, "OK", before, len(data)
        if verify:
            with Image.open(io.BytesIO(data)) as chk:
                chk.load()
                back = np.array(chk.convert("RGBA"), dtype=np.uint8)
            if back.shape != arr.shape or not np.array_equal(back[..., 3], arr[..., 3]):
                return path, "VERIFY_FAIL", before, before
            if group == "cards":
                same = np.array_equal(back, arr)
            else:
                vis = arr[..., 3] > 0
                same = np.array_equal(back[vis], arr[vis])
            if not same:
                return path, "VERIFY_FAIL", before, before
        tmp = path + ".tmp_strip"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return path, "OK", before, len(data)
    except Exception as e:  # noqa: BLE001
        try:
            os.remove(path + ".tmp_strip")
        except OSError:
            pass
        return path, "ERR:%s" % e, 0, 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=DEFAULT_ROOT, help="папка hd (с UI и TERRAIN)")
    ap.add_argument("--groups", default="dolls,terrain", help="dolls,terrain,cards")
    ap.add_argument("--cards", action="store_true", help="добавить cards (RGBA непрозрачные -> RGB)")
    ap.add_argument("--dry-run", action="store_true", help="только подсчёт байт на выборке, файлы не пишутся")
    ap.add_argument("--sample", type=int, default=200, help="размер выборки на группу при --dry-run (0 = все)")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--report", help="TSV: путь, байт до, байт после (+ статус)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    groups = [g for g in a.groups.split(",") if g]
    if a.cards and "cards" not in groups:
        groups.append("cards")
    root = os.path.abspath(a.root)
    files = collect(root, groups)
    t0 = time.time()
    rows = []
    with ProcessPoolExecutor(a.workers) as ex:
        for g in groups:
            lst = files[g]
            if a.dry_run and a.sample and len(lst) > a.sample:
                lst = random.Random(20261109).sample(lst, a.sample)
            jobs = [(p, g, not a.dry_run, a.verify) for p in lst]
            res = list(ex.map(process, jobs, chunksize=16))
            rows += [(g,) + r for r in res]
            b = sum(r[2] for r in res)
            n = sum(r[3] for r in res)
            st = {}
            for r in res:
                k = r[1].split(":")[0]
                st[k] = st.get(k, 0) + 1
            print("%-8s файлов %6d  до %9.1f МиБ  после %9.1f МиБ  (%+.1f %%)  %s" % (
                g, len(res), b / 1048576, n / 1048576, (n - b) * 100.0 / b if b else 0, st))
    print("время %.1f с, %d процессов, %s" % (time.time() - t0, a.workers, "сухой прогон" if a.dry_run else "запись"))
    if a.report:
        with open(a.report, "w", encoding="utf-8-sig", newline="") as f:
            f.write("path\tbefore\tafter\tstatus\tgroup\n")
            for g, p, s, b, n in rows:
                f.write("%s\t%d\t%d\t%s\t%s\n" % (os.path.relpath(p, root), b, n, s, g))
    bad = [r for r in rows if r[2].startswith(("VERIFY_FAIL", "ERR"))]
    if bad:
        print("НЕ ПРОШЛИ: %d" % len(bad))
        for r in bad[:20]:
            print("  ", r[1], r[2])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
