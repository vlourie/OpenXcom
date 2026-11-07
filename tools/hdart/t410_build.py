#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000410: сборка КАНДИДАТОВ из ответов полей t410_fld.py, проверки и листы. В МОД НИЧЕГО НЕ СТАВИТ.

Варианты (папка art/tickets/t410/cand/<вариант>/<НАБОР>_<кадр>.png, RGBA 128x160; варианты ковра - <НАБОР>_<кадр>.v1.png):
  M<зерно>        кадры режутся из внутренних клеток поля вперемешку 0/1/2 (fld_m): рисунок и стыки - модели;
  G<зерно>S<зерно> смесь двух полей: трава (fld_g) и земля (fld_s) по маске земли классики кадра; окна - разные клетки
                  полей, поэтому кадр 0, его варианты и кадры 1/2 - одной манеры, а соседей нет вовсе (нет заимствованных стеблей).
Во всех: альфа - силуэт классики x4 (вне 0), внутри 255; тон - match_tone к классике кадра 0.7; кадр 3 - зеркало 2 тем же
путём (альфа и тон - классики 3); FORESTRED:4 - перенос цвета классики своего набора (obj_derive.transfer).

    py -3.13 tools\hdart\t410_build.py build --variants M4321 G4301S4311
    py -3.13 tools\hdart\t410_build.py sheet --variants ...      # лист t410_cand.png
    py -3.13 tools\hdart\t410_build.py scene --variants ...      # листы t410_scene*.png, проверка швов
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import numpy as np                                   # noqa: E402
from PIL import Image, ImageDraw, ImageOps           # noqa: E402
from scipy import ndimage                            # noqa: E402

import t410_gen as g                                 # noqa: E402
import t410_fld as fl                                # noqa: E402
from PIL import ImageFont                            # noqa: E402

FONT = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 15)

SOIL = {(136, 96, 51), (90, 52, 25), (124, 82, 43), (112, 72, 35), (103, 61, 30), (77, 45, 21)}
TONE_B = 1.0           # средний цвет кадра - классики (0.7 у предметов оставляло траву на +12 по зелёному)
GAME = os.path.join(g.ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd", "TERRAIN")
VARIANT_CELLS = fl.window_cells("g")       # окна основы и трёх вариантов ковра в полях g/s/p (клетки без зеркала в эскизе)


def tone_to(im, f, set_="MOUNTTROP"):
    """Средний цвет - классики кадра, отдельно для земли и для травы (одним средним земля краснела от зелени стеблей);
    разброс яркости не раздувается выше своего (как probe_object.match_tone)."""
    cl = np.asarray(g.classic(set_, f))
    op = cl[..., 3] > 0
    soil = np.zeros(op.shape, bool)
    for y, x in zip(*np.nonzero(op)):
        soil[y, x] = tuple(int(v) for v in cl[y, x, :3]) in SOIL
    a = np.asarray(im.convert("RGBA"), np.float32).copy()
    k = np.ones((4, 4), bool)
    for reg in (soil & op, ~soil & op):
        if reg.sum() < 12:
            continue
        reg4 = np.kron(reg, k) & (a[..., 3] > 128)
        if reg4.sum() < 200:
            continue
        o = cl[..., :3][reg].astype(np.float32)
        src = a[..., :3][reg4]
        ms, ss = src.mean(0), src.std(0) + 1e-3
        mo, so = o.mean(0), o.std(0) + 1e-3
        gain = np.minimum(so / ss, 1.0)
        a[..., :3][reg4] = np.clip((src - ms) * gain + mo, 0, 255)
    return Image.fromarray(np.rint(a).astype(np.uint8), "RGBA")


def sil4(f, set_="MOUNTTROP"):
    return np.kron(np.asarray(g.classic(set_, f))[..., 3] > 0, np.ones((4, 4), bool))


def with_alpha(rgb, f, set_="MOUNTTROP"):
    a = np.dstack([np.asarray(rgb.convert("RGB")), np.zeros((160, 128), np.uint8)])
    m = sil4(f, set_)
    a[..., 3] = np.where(m, 255, 0)
    a[~m, :3] = 0
    return Image.fromarray(a, "RGBA")


def soil_mask(f):
    """Доля земли по классике кадра f (x4, размыта): 0 - трава, 1 - земля."""
    a = np.asarray(g.classic("MOUNTTROP", f))
    m = np.zeros(a.shape[:2], np.float32)
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            if a[y, x, 3] and tuple(int(v) for v in a[y, x, :3]) in SOIL:
                m[y, x] = 1.0
    m4 = np.kron(m, np.ones((4, 4), np.float32))
    return ndimage.gaussian_filter(m4, 2.5)


def mix_frame(gfld, sfld, f, cell_g, cell_s, edge_noise=0.18):
    """Кадр f из окон полей травы и земли по маске земли классики; край смены материала - по рисунку травы."""
    gw = np.asarray(fl.window(gfld, *cell_g), np.float32)
    sw = np.asarray(fl.window(sfld, *cell_s), np.float32)
    m = soil_mask(f)
    lum = gw @ np.array([0.299, 0.587, 0.114], np.float32)
    hp = lum - ndimage.gaussian_filter(lum, 5.0)
    hp = hp / (hp.std() + 1e-6)
    mm = np.clip((m - 0.5 + edge_noise * hp) / 0.30 + 0.5, 0.0, 1.0)[..., None]
    rgb = gw * (1 - mm) + sw * mm
    return Image.fromarray(np.clip(np.rint(rgb), 0, 255).astype(np.uint8), "RGB")


def cands_mixed(seed):
    """{(кадр, номер варианта): RGBA} из поля m."""
    cells = fl.layout("m")
    fld = fl.field_x4("m", seed)
    by = {}
    for (i, j), f in sorted(cells.items()):
        if 1 <= i <= fl.N - 2 and 1 <= j <= fl.N - 2:
            by.setdefault(f, []).append((i, j))
    out = {}
    for f, lst in by.items():
        for v, c in enumerate(lst[:4]):
            out[(f, v)] = tone_to(with_alpha(fl.window(fld, *c), f), f)
    # кадр 0 в поле m: 8 внутренних клеток; берём 4 - первые
    return out


def cands_mix(sg, ss):
    gfld, sfld = fl.field_x4("g", sg), fl.field_x4("s", ss)
    out = {}
    for f in (0, 1, 2):
        for v in range(4):
            cell = VARIANT_CELLS[v if f == 0 else (v + f) % 4]
            img = mix_frame(gfld, sfld, f, cell, VARIANT_CELLS[(v + 1 + f) % 4])
            out[(f, v)] = tone_to(with_alpha(img, f), f)
    return out


def cands_pure(sg, ss, sp=None):
    """Кадры из окон однородных полей: 0 - поле g (все клетки кадр 0), 2 - поле s (все кадр 2); кадр 1 - смесь окон g и s по
    маске земли классики 1 (sp=None) либо окно поля p (все клетки кадр 1). Рисунок стеблей и земли - классики (эскиз
    поля), у клетки соседи того же вида: стеблей чужих кадров в окне нет."""
    gf, sf = fl.field_x4("g", sg), fl.field_x4("s", ss)
    pf = fl.field_x4("p", sp) if sp else None
    out = {}
    for v in range(4):
        c = VARIANT_CELLS[v]
        out[(0, v)] = tone_to(with_alpha(fl.window(gf, *c), 0), 0)
        out[(2, v)] = tone_to(with_alpha(fl.window(sf, *c), 2), 2)
        if pf is not None:
            out[(1, v)] = tone_to(with_alpha(fl.window(pf, *c), 1), 1)
        else:
            out[(1, v)] = tone_to(with_alpha(mix_frame(gf, sf, 1, c, VARIANT_CELLS[(v + 1) % 4]), 1), 1)
    return out


def derive_forestred(img2):
    """FORESTRED:4 - член семьи 2, но классика отличается по пятнам (182 пикселя): перенос цвета без привязки к раскладке
    (t405_409_gen.colormap_transfer: таблица цветов классики основа -> цель), альфа - силуэт классики FORESTRED:4."""
    import t405_409_gen as t4
    a = np.asarray(img2.convert("RGBA")).copy()
    idx = ndimage.distance_transform_edt(a[..., 3] == 0, return_indices=True)[1]
    a[..., :3] = a[..., :3][idx[0], idx[1]]           # цвет за силуэтом основы - ближайший: у FORESTRED:4 силуэт другой
    a[..., 3] = 255
    img2 = Image.fromarray(a, "RGBA")
    ob = Image.fromarray(np.asarray(g.classic("MOUNTTROP", 2)))
    ot = Image.fromarray(np.asarray(g.classic("FORESTRED", 4)))
    new = t4.colormap_transfer(img2, ob, ot)
    return with_alpha(new.convert("RGB"), 4, "FORESTRED")


def variant_files(name, c):
    """{(набор, имя файла без .png): RGBA} кандидата: 0-2 и варианты, 3 - зеркало 2, FORESTRED:4."""
    files = {}
    for (f, v), im in c.items():
        suffix = "" if v == 0 else ".v%d" % v
        files[("MOUNTTROP", "%d%s" % (f, suffix))] = im
    for (f, v), im in list(c.items()):
        if f == 2:
            suffix = "" if v == 0 else ".v%d" % v
            files[("MOUNTTROP", "3%s" % suffix)] = tone_to(with_alpha(ImageOps.mirror(im.convert("RGB")), 3), 3)
    files[("FORESTRED", "4")] = derive_forestred(c[(2, 0)])
    return files


def build(names):
    rows = []
    for name in names:
        if name.startswith("M"):
            c = cands_mixed(int(name[1:]))
        elif name.startswith("W"):          # W<g>-<s> (кадр 1 смесью) или W<g>-<s>-<p> (кадр 1 из поля p)
            parts = [int(x) for x in name[1:].split("-")]
            c = cands_pure(parts[0], parts[1], parts[2] if len(parts) > 2 else None)
        else:
            sg, ss = name[1:].split("S")
            c = cands_mix(int(sg), int(ss))
        files = variant_files(name, c)
        d = os.path.join(g.CAND, name)
        os.makedirs(d, exist_ok=True)
        for (s, n), im in files.items():
            im.save(os.path.join(d, "%s_%s.png" % (s, n)))
        print(name, ":", len(files), "кадров ->", d)
    return rows


def load(name, s, n):
    p = os.path.join(g.CAND, name, "%s_%s.png" % (s, n))
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None


def hd_now(s, n):
    p = os.path.join(GAME, s + ".PCK", "%s.png" % n)
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None


def on_dark(im, bg=(36, 36, 40), scale=2):
    b = Image.new("RGBA", im.size, bg + (255,))
    b.alpha_composite(im.convert("RGBA"))
    return b.convert("RGB").resize((im.width * scale // 1, im.height * scale // 1), Image.LANCZOS if scale < 1 else Image.NEAREST)


def sheet(names, out=None):
    out = out or os.path.join(g.REV, "t410_cand.png")
    rows = [("MOUNTTROP", "0"), ("MOUNTTROP", "1"), ("MOUNTTROP", "2"), ("MOUNTTROP", "3"), ("FORESTRED", "4")]
    cols = ["классика x4", "HD сейчас"] + list(names)
    sc = 2
    cw, ch = 128 * sc, 160 * sc
    top = 22
    W, H = len(cols) * (cw + 6), len(rows) * (ch + top + 6) + top
    sh = Image.new("RGB", (W, H), (12, 12, 14))
    d = ImageDraw.Draw(sh)
    for ci, cn in enumerate(cols):
        d.text((ci * (cw + 6) + 2, 4), cn, fill=(255, 220, 0), font=FONT)
    for ri, (s, n) in enumerate(rows):
        f = int(n)
        y = top + ri * (ch + top + 6)
        d.text((2, y + 2), "%s:%s" % (s, n), fill=(120, 200, 255), font=FONT)
        cls = Image.fromarray(np.asarray(g.classic(s, f))).resize((128, 160), Image.NEAREST)
        ims = [cls, hd_now(s, n) or Image.new("RGBA", (128, 160))] + [load(nm, s, n) or Image.new("RGBA", (128, 160)) for nm in names]
        for ci, im in enumerate(ims):
            sh.paste(on_dark(im, scale=sc), (ci * (cw + 6), y + 16))
    sh.save(out)
    print("лист:", out)


# --- сцена: поле 8x8 клеток вперемешку ------------------------------------------------------------------------------
def arrangement(n=8, seed=11, weights=(0.63, 0.21, 0.09, 0.07)):
    rng = np.random.RandomState(seed)
    return rng.choice(4, size=(n, n), p=list(weights))


def pick_variant(frames, f, i, j):
    """Как движок: вариант по месту; здесь - по хэшу клетки среди имеющихся (основа и v1-v3)."""
    lst = frames[f]
    return lst[(i * 7 + j * 13 + (i ^ j)) % len(lst)]


def render_scene(frames, arr, bg=(20, 20, 20)):
    n = arr.shape[0]
    W, H = (2 * n - 1) * 64 + 128, (2 * n - 1) * 32 + 160
    cv = Image.new("RGBA", (W, H), bg + (255,))
    order = sorted(((i, j) for i in range(n) for j in range(n)), key=lambda c: (c[0] + c[1], c[0]))
    for (i, j) in order:
        x, y = (n - 1) * 64 + (i - j) * 64, (i + j) * 32
        im = pick_variant(frames, int(arr[i, j]), i, j)
        cv.alpha_composite(im, (x, y))
    return cv


def seam_stat(cv, arr):
    """Перепад яркости через общий край соседних клеток против перепада внутри клеток (та же длина и направление).
    Отношение около 1 - границ клеток не видно; заметно выше - границы."""
    n = arr.shape[0]
    lum = np.asarray(cv.convert("RGB"), np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    ys, xs = lum.shape

    def at(x, y):
        return lum[np.clip(np.rint(y).astype(int), 0, ys - 1), np.clip(np.rint(x).astype(int), 0, xs - 1)]

    edge, inner = [], []
    rng = np.random.RandomState(3)
    nv = np.array([1.0, 2.0]) / np.sqrt(5.0) * 3.0          # шаг через край 2:1, 3 пикселя в каждую сторону
    t = np.linspace(-0.85, 0.85, 24)
    for i in range(n):
        for j in range(n):
            cx, cy = (n - 1) * 64 + (i - j) * 64 + 64, (i + j) * 32 + 130
            # края с правым-нижним и левым-нижним соседом (дальше от верха - не закрыты стеблями ниже стоящих клеток нет:
            # меряем всё, как оно видно)
            for mx, my, dx, dy, nx, ny in ((cx + 32, cy + 16, -32, 16, nv[0], nv[1]), (cx - 32, cy + 16, 32, 16, -nv[0], nv[1])):
                px, py = mx + t * dx, my + t * dy
                edge.append(np.abs(at(px + nx, py + ny) - at(px - nx, py - ny)).mean())
                # внутри: та же пара, сдвинутая в центр клетки на случайную точку в ромбе d < 0.5
                for _ in range(2):
                    ox, oy = (rng.rand() - 0.5) * 60, (rng.rand() - 0.5) * 28
                    px2, py2 = cx + ox + t * dx * 0.4, cy + oy + t * dy * 0.4
                    inner.append(np.abs(at(px2 + nx, py2 + ny) - at(px2 - nx, py2 - ny)).mean())
    return float(np.mean(edge)), float(np.mean(inner))


def scene(names, seed=11, name="t410_scene.png", weights=(0.63, 0.21, 0.09, 0.07)):
    arr = arrangement(8, seed, weights)
    cur = {f: [hd_now("MOUNTTROP", str(f))] for f in range(4)}
    clsf = {f: [Image.fromarray(np.kron(np.asarray(g.classic("MOUNTTROP", f)), np.ones((4, 4, 1), np.uint8)))] for f in range(4)}
    panels = [("классика x4", render_scene(clsf, arr)), ("HD сейчас", render_scene(cur, arr))]
    for nm in names:
        fr = {f: [load(nm, "MOUNTTROP", str(f))] + [x for x in (load(nm, "MOUNTTROP", "%d.v%d" % (f, v)) for v in (1, 2, 3)) if x]
              for f in range(4)}
        panels.append(("кандидат " + nm, render_scene(fr, arr)))
    stats = []
    for t, im in panels:
        e, i_ = seam_stat(im, arr)
        stats.append((t, e, i_, e / i_))
        print("шов: %-22s край %.2f  внутри %.2f  отношение %.2f" % (t, e, i_, e / i_))
    W = panels[0][1].width
    H = panels[0][1].height
    cols = 2
    rows = (len(panels) + cols - 1) // cols
    sh = Image.new("RGB", (cols * (W + 8), rows * (H + 26)), (12, 12, 14))
    d = ImageDraw.Draw(sh)
    for k, ((t, im), st) in enumerate(zip(panels, stats)):
        x, y = (k % cols) * (W + 8), (k // cols) * (H + 26)
        d.text((x + 4, y + 6), "%s   шов край/внутри %.2f" % (t, st[3]), fill=(255, 220, 0), font=FONT)
        sh.paste(im.convert("RGB"), (x, y + 24))
    out = os.path.join(g.REV, name)
    sh.save(out)
    print("лист:", out)
    return stats


def checks(names, out=None):
    """Проверка швов кандидатов (R-439/R-247, rim_alpha): просвет сетки 3x3 у шва (пикселей, должно быть 0), яркость шва к
    середине на чёрном (около 1 и выше - тёмной сетки нет), альфа внутри силуэта классики ниже 255 и вне силуэта выше 0."""
    import rim_alpha as ra
    out = out or os.path.join(g.REV, "t410_checks.tsv")
    rows = [["вариант", "набор", "кадр", "просвет шва, пикс", "шов к середине", "внутри силуэта альфа<255", "вне силуэта альфа>0"]]
    worst = 0
    for nm in names:
        d = os.path.join(g.CAND, nm)
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".png"):
                continue
            st, n = fn[:-4].split("_", 1)
            f = int(n.split(".")[0])
            cur = np.asarray(Image.open(os.path.join(d, fn)).convert("RGBA"))
            frames, _types, fw, fh = ra.classic(st)
            op = frames[f] != 0
            lk, cov = ra.leak(cur[..., 3], op, 4, fw, fh)
            sr = ra.seam_ratio(cur, 4, fw, fh)
            sil = ra.silhouette(op, 4)
            inside = int(((cur[..., 3] < 255) & sil).sum())
            outside = int(((cur[..., 3] > 0) & ~sil).sum())
            worst = max(worst, lk)
            rows.append([nm, st, n, lk, "%.2f" % sr, inside, outside])
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh, delimiter="\t").writerows(rows)
    print("проверено кадров: %d, наибольший просвет шва: %d пикс; таблица: %s" % (len(rows) - 1, worst, out))
    bad = [r for r in rows[1:] if r[3] or r[5] or r[6]]
    for r in bad[:10]:
        print("  нарушение:", r)
    lo = sorted(rows[1:], key=lambda r: float(r[4]))[:3]
    print("  самый тёмный шов:", [(r[0], r[1], r[2], r[4]) for r in lo])
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "sheet", "scene", "checks"])
    ap.add_argument("--variants", nargs="+", required=True)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default=None)
    ap.add_argument("--stress", action="store_true", help="доли кадров 0/1/2/3 выровнены: больше стыков разных кадров")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.variants)
    elif a.cmd == "checks":
        checks(a.variants, a.out)
    elif a.cmd == "sheet":
        sheet(a.variants, a.out)
    else:
        scene(a.variants, a.seed, a.out or "t410_scene.png", (0.35, 0.30, 0.20, 0.15) if a.stress else (0.63, 0.21, 0.09, 0.07))
    return 0


if __name__ == "__main__":
    sys.exit(main())
