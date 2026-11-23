#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000445 (склоны холмов MOUNTGRASS 27-39, 41 и их родня FOREST, BLACKFOREST), вариант A по выбору Vitali 30.10:
приём тикета 431 (t431_slopes.py), но поле травы - свой HD-пол MOUNTGRASS (кадр 0 и варианты 0.v1-0.v7), мозаикой.
В МОД НИЧЕГО НЕ СТАВИТ: кандидаты - art/tickets/t445/cand/<НАБОР>_<кадр>.png (RGBA 128x160, как нынешний HD). Без видеокарты.

Кадр собирается так (все слои x4):
  1. мозаика: поле клеток 11x11, в каждой случайный вариант пола 0 / 0.v1-0.v7 (HD сейчас), по сетке игры (шаг 64x32);
     окно кадра - вырез 128x160 по клетке в середине поля, поэтому трава над ромбом - продолжение соседних клеток, шва нет;
  2. пласт «растение / цоколь» по цвету классики СВОЕГО набора (MOUNTGRASS, FOREST - зелень против песка; BLACKFOREST -
     тёмное против светло-серого);
  3. рельеф и тень классики: цвет окна приводится к классике ЛОКАЛЬНО (сигма SIGMA_REL x4 пикселей по растению) - форма
     бугра и затенённость - классики, фактура и стебли - пола MOUNTGRASS; BLACKFOREST - только яркостью фактуры (травы
     зелёной на чёрной земле нет, оттенок классики);
  4. цоколь - из нынешнего HD кадра, граница по маске классики, край смены по рисунку травы;
  5. альфа - силуэт классики x4, края спрямлены сглаживанием (R-121), не шире силуэта классики на 2 пикселя.

    py -3.13 tools\hdart\t445_slopes.py build --name A1
    py -3.13 tools\hdart\t445_slopes.py sheet --name A1 --out art\_review\tickets_2026-10-30\t445_cand.png
    py -3.13 tools\hdart\t445_slopes.py checks --name A1
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import numpy as np                                   # noqa: E402
from PIL import Image, ImageDraw, ImageFont          # noqa: E402
from scipy import ndimage                            # noqa: E402

import t410_gen as g                                 # noqa: E402

ROOT = g.ROOT
REV = g.REV
CAND = os.path.join(ROOT, "art", "tickets", "t445", "cand")
TERR = os.path.join(ROOT, "user", "mods", "hd", "hd", "TERRAIN")
FONT = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 15)
FRAMES = list(range(27, 40)) + [41]
SETS = ["MOUNTGRASS", "FOREST", "BLACKFOREST"]
VARIANTS = ["0"] + ["0.v%d" % i for i in range(1, 8)]
N = 11
K4 = np.ones((4, 4), bool)
LUM_ONLY = {"BLACKFOREST"}


def hd_now(s, f):
    p = os.path.join(TERR, s + ".PCK", "%s.png" % f)
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None


# --- поле: мозаика HD-пола MOUNTGRASS ------------------------------------------------------------------------------
def mosaic(seed=4451):
    """Поле клеток N x N из вариантов пола MOUNTGRASS 0/0.v1-0.v7 по сетке игры (шаг 64x32 при k = 4). Возвращает RGB и
    положения клеток {(i, j): (x, y)} - левый верх кадра 128x160 клетки."""
    rng = np.random.RandomState(seed)
    tiles = [hd_now("MOUNTGRASS", v) for v in VARIANTS]
    W, H = (2 * N) * 64 + 128, (2 * N) * 32 + 160
    cv = Image.new("RGBA", (W, H), (53, 115, 30, 255))
    pos = {}
    order = sorted(((i, j) for i in range(N) for j in range(N)), key=lambda c: (c[0] + c[1], c[0]))
    for i, j in order:
        x, y = (i - j + N - 1) * 64, (i + j) * 32
        pos[(i, j)] = (x, y)
        cv.alpha_composite(tiles[rng.randint(len(tiles))], (x, y))
    return cv.convert("RGB"), pos


def window_cells(pos):
    mid = (N - 1) / 2
    cells = [(i, j) for i in range(4, N - 3) for j in range(4, N - 3)]
    cells.sort(key=lambda c: (abs(c[0] - mid) + abs(c[1] - mid), c))
    return cells[:4]


def window(field, pos, cell):
    x, y = pos[cell]
    return np.asarray(field.crop((x, y, x + 128, y + 160)), np.float32)


# --- кадр ----------------------------------------------------------------------------------------------------------
def ground_mask(set_, cl):
    """Растение (верх бугра) против цоколя классики своего набора."""
    a = cl[..., :3].astype(np.int32)
    r, gg, bb = a[..., 0], a[..., 1], a[..., 2]
    op = cl[..., 3] > 0
    if set_ in LUM_ONLY:
        return op & ((r + gg + bb) / 3.0 < 110)
    green = (gg >= r - 4) & (gg > bb + 6)
    return green & op


def smooth_alpha(sil4, sigma=2.4):
    """Силуэт x4 со спрямлёнными краями (R-121): размытие и мягкий порог; не шире силуэта классики на 2 пикселя."""
    s = ndimage.gaussian_filter(sil4.astype(np.float32), sigma)
    a = np.clip((s - 0.5) * 6.0 + 0.5, 0.0, 1.0)
    return np.where(ndimage.binary_dilation(sil4, iterations=2), a, 0.0)


def norm_blur(x, w, sigma):
    num = np.stack([ndimage.gaussian_filter(x[..., c] * w, sigma) for c in range(x.shape[-1])], -1)
    return num / np.maximum(ndimage.gaussian_filter(w, sigma)[..., None], 1e-3)


def build_frame(field, pos, cells, set_, f, sigma_rel=9.0, edge_noise=0.18, alpha_sigma=2.4):
    cl = np.asarray(g.classic(set_, f))
    op = cl[..., 3] > 0
    pl = ground_mask(set_, cl)
    st = op & ~pl
    pl4, st4, sil4 = np.kron(pl, K4), np.kron(st, K4), np.kron(op, K4)
    tex = window(field, pos, cells[f % 4])
    lum = tex @ np.array([0.299, 0.587, 0.114], np.float32)
    hp = lum - ndimage.gaussian_filter(lum, 5.0)
    hp = hp / (hp.std() + 1e-6)
    c4 = np.kron(cl[..., :3].astype(np.float32), np.ones((4, 4, 1), np.float32))
    w = pl4.astype(np.float32)
    lc = norm_blur(c4, w, sigma_rel)
    if set_ in LUM_ONLY:
        # оттенок и тон - классики, у фактуры берётся только отношение яркости к своему локальному среднему
        lt = norm_blur(lum[..., None], w, sigma_rel)[..., 0]
        rel = np.clip(lum / np.maximum(lt, 3.0), 0.4, 2.5)
        tex2 = np.clip(lc * rel[..., None], 0, 255)
    else:
        lt = norm_blur(tex, w, sigma_rel)
        tex2 = np.clip(tex * np.clip(lc / np.maximum(lt, 3.0), 0.2, 5.0), 0, 255)
    hd = hd_now(set_, str(f))
    hd_rgb = np.asarray(hd.convert("RGB"), np.float32)
    ms = ndimage.gaussian_filter(st4.astype(np.float32), 2.5)
    mm = np.clip((ms - 0.5 + edge_noise * hp) / 0.30 + 0.5, 0.0, 1.0)[..., None]
    rgb = tex2 * (1 - mm) + hd_rgb * mm
    al = smooth_alpha(sil4, alpha_sigma)
    out = np.zeros((160, 128, 4), np.uint8)
    out[..., :3] = np.where(al[..., None] > 0, np.rint(np.clip(rgb, 0, 255)), 0).astype(np.uint8)
    out[..., 3] = np.rint(al * 255).astype(np.uint8)
    # шов с соседними клетками (R-439/R-247, rim_alpha): у ромба клетки альфа сплошная по точному ромбу, лесенки нет
    import rim_alpha as ra
    frames, _t, fw, fh = ra.classic(set_)
    out, _n = ra.fixed(out, frames[f] != 0, 4, fw, fh)
    return Image.fromarray(out, "RGBA")


def build(name, sets=SETS, **kw):
    field, pos = mosaic()
    cells = window_cells(pos)
    d = os.path.join(CAND, name)
    os.makedirs(d, exist_ok=True)
    n = 0
    for s in sets:
        for f in FRAMES:
            build_frame(field, pos, cells, s, f, **kw).save(os.path.join(d, "%s_%d.png" % (s, f)))
            n += 1
    field.save(os.path.join(d, "_field.png"))
    print(name, ":", n, "кадров ->", d)


def load(name, s, f):
    p = os.path.join(CAND, name, "%s_%d.png" % (s, f))
    return Image.open(p).convert("RGBA") if os.path.exists(p) else Image.new("RGBA", (128, 160))


def on_dark(im, bg=(36, 36, 40), scale=2):
    b = Image.new("RGBA", im.size, bg + (255,))
    b.alpha_composite(im.convert("RGBA"))
    return b.convert("RGB").resize((im.width * scale, im.height * scale), Image.NEAREST)


def sheet(name, out, sets=("MOUNTGRASS",), sc=2):
    cw, ch = 128 * sc, 160 * sc
    top = 20
    rows = [(s, f) for s in sets for f in FRAMES]
    per = 2
    nrow = (len(rows) + per - 1) // per
    bw = 3 * (cw + 2) + 10
    sh = Image.new("RGB", (per * bw, nrow * (ch + top + 4)), (12, 12, 14))
    d = ImageDraw.Draw(sh)
    for k, (s, f) in enumerate(rows):
        bx, by = (k % per) * bw, (k // per) * (ch + top + 4)
        d.text((bx + 2, by + 3), "%s:%d   классика x4 | сейчас | кандидат %s" % (s, f, name), fill=(255, 220, 0), font=FONT)
        cls = Image.fromarray(np.kron(np.asarray(g.classic(s, f)), np.ones((4, 4, 1), np.uint8)))
        for ci, im in enumerate([cls, hd_now(s, str(f)), load(name, s, f)]):
            sh.paste(on_dark(im, scale=sc), (bx + ci * (cw + 2), by + top))
    sh.save(out)
    print("лист:", out, sh.size)


def checks(name, out=None):
    """Как t410_build.checks: просвет шва 3x3 (должен быть 0), шов к середине, альфа внутри силуэта классики <255, вне >0."""
    import rim_alpha as ra
    out = out or os.path.join(REV, "t445_cand_checks.tsv")
    rows = [["набор", "кадр", "просвет шва", "шов к середине", "внутри силуэта alpha<255", "вне силуэта alpha>0"]]
    d = os.path.join(CAND, name)
    for s in SETS:
        for f in FRAMES:
            p = os.path.join(d, "%s_%d.png" % (s, f))
            if not os.path.exists(p):
                continue
            cur = np.asarray(Image.open(p).convert("RGBA"))
            frames, _t, fw, fh = ra.classic(s)
            op = frames[f] != 0
            lk, _cov = ra.leak(cur[..., 3], op, 4, fw, fh)
            sr = ra.seam_ratio(cur, 4, fw, fh)
            sil = ra.silhouette(op, 4)
            rows.append([s, f, lk, "%.2f" % sr, int(((cur[..., 3] < 255) & sil).sum()), int(((cur[..., 3] > 0) & ~sil).sum())])
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh, delimiter="\t").writerows(rows)
    print("проверено кадров: %d, наибольший просвет шва: %d пикс; таблица: %s" % (len(rows) - 1, max(r[2] for r in rows[1:]), out))
    for r in sorted(rows[1:], key=lambda r: float(r[3]))[:4]:
        print("  самый тёмный шов:", r)
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "sheet", "checks"])
    ap.add_argument("--name", default="A1")
    ap.add_argument("--out", default=os.path.join(REV, "t445_cand.png"))
    ap.add_argument("--sigma", type=float, default=9.0)
    ap.add_argument("--asigma", type=float, default=2.4)
    ap.add_argument("--sets", nargs="+", default=["MOUNTGRASS"])
    ap.add_argument("--scale", type=int, default=2)
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.name, sigma_rel=a.sigma, alpha_sigma=a.asigma)
    elif a.cmd == "checks":
        checks(a.name, None if a.out == os.path.join(REV, "t445_cand.png") else a.out)
    else:
        sheet(a.name, a.out, tuple(a.sets), a.scale)
    return 0


if __name__ == "__main__":
    sys.exit(main())
