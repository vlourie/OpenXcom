#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000431 / XP-000429 (склоны бугров MOUNTTROP 27-39, верх куба 41, их копии в FORESTJUNGLESTYX), вариант A
по выбору Vitali 30.10: поверхность - процедурно из ПРИНЯТЫХ полей пушистой травы тикета 410 (поле g - трава, поле s - земля,
зёрна 4401/4411, art/tickets/t410/gen/fld_*/raw), без видеокарты. В МОД НИЧЕГО НЕ СТАВИТ: кандидаты -
art/tickets/t431/cand/<имя>/<НАБОР>_<кадр>.png (RGBA 128x160).

Кадр собирается так (все слои x4):
  1. пласт «растение / камень» по цвету классики (зелень, красные пятна, сухие стебли, земля - растение; серое и тёмное цоколя - камень);
  2. поверхность - смесь окон полей g и s по маске земли классики кадра (маска - по MOUNTTROP, у STYX те же кадры другой землёй);
  3. рельеф и тень классики: цвет окна приводится к классике ЛОКАЛЬНО (отношение сглаженных цветов классики и окна по растению,
     сигма SIGMA_REL) - форма бугра, затенённость 30/31/33/36/37 и общий тон - классики, стебли и земля - поля 410;
  4. цоколь (камень) - из текущего HD кадра; граница растения и камня - по маске классики, край смены по рисунку травы;
  5. альфа - силуэт классики x4, края спрямлены сглаживанием (R-121), не шире силуэта классики на 2 пикселя.

    py -3.13 tools\hdart\t431_slopes.py build --name A1
    py -3.13 tools\hdart\t431_slopes.py sheet --name A1 --out art\_review\tickets_2026-10-30\t431_cand.png
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import numpy as np                                   # noqa: E402
from PIL import Image, ImageDraw                     # noqa: E402
from scipy import ndimage                            # noqa: E402

import t410_gen as g                                 # noqa: E402
import t410_fld as fl                                # noqa: E402
import t410_build as b                               # noqa: E402

CAND = os.path.join(g.ROOT, "art", "tickets", "t431", "cand")
REV = g.REV
FRAMES = list(range(27, 40)) + [41]
SETS = ["MOUNTTROP", "FORESTJUNGLESTYX"]
SG, SS = 4401, 4411
CELLS = fl.window_cells("g")
SOIL = set(b.SOIL) | {(148, 110, 62), (163, 128, 74), (63, 35, 16), (41, 20, 9), (48, 25, 11)}
K4 = np.ones((4, 4), bool)


def plant_mask(cl):
    """Растение (зелень, красные пятна, сухие стебли, земля) против серого камня и тёмной тени цоколя."""
    a = cl[..., :3].astype(np.int32)
    r, gg, bb = a[..., 0], a[..., 1], a[..., 2]
    green = (gg >= r - 4) & (gg > bb + 6)
    red = (r > gg + 14) & (r > bb + 14)
    return (green | red) & (cl[..., 3] > 0)


def soil_mask(set_, f):
    """Доля земли (x4, размыта) по MOUNTTROP той же кадра - раскладка у STYX та же, меняется только цвет земли."""
    a = np.asarray(g.classic("MOUNTTROP", f))
    m = np.zeros(a.shape[:2], np.float32)
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            if a[y, x, 3] and tuple(int(v) for v in a[y, x, :3]) in SOIL:
                m[y, x] = 1.0
    return ndimage.gaussian_filter(np.kron(m, np.ones((4, 4), np.float32)), 2.5)


def smooth_alpha(sil4, sigma=2.4):
    """Силуэт x4 со спрямлёнными краями (R-121): размытие и мягкий порог; не шире силуэта классики на 2 пикселя."""
    s = ndimage.gaussian_filter(sil4.astype(np.float32), sigma)
    a = np.clip((s - 0.5) * 6.0 + 0.5, 0.0, 1.0)
    return np.where(ndimage.binary_dilation(sil4, iterations=2), a, 0.0)


def norm_blur(x, w, sigma):
    num = np.stack([ndimage.gaussian_filter(x[..., c] * w, sigma) for c in range(x.shape[-1])], -1)
    return num / np.maximum(ndimage.gaussian_filter(w, sigma)[..., None], 1e-3)


def mix_tex(gfld, sfld, set_, f, edge_noise=0.18):
    """Окно травы и земли по маске земли классики кадра; край смены материала - по рисунку травы."""
    ci = f % 4
    gw = np.asarray(fl.window(gfld, *CELLS[ci]), np.float32)
    sw = np.asarray(fl.window(sfld, *CELLS[(ci + 1) % 4]), np.float32)
    m = soil_mask(set_, f)
    lum = gw @ np.array([0.299, 0.587, 0.114], np.float32)
    hp = lum - ndimage.gaussian_filter(lum, 5.0)
    hp = hp / (hp.std() + 1e-6)
    mm = np.clip((m - 0.5 + edge_noise * hp) / 0.30 + 0.5, 0.0, 1.0)[..., None]
    return gw * (1 - mm) + sw * mm, hp


def build_frame(gfld, sfld, set_, f, sigma_rel=9.0, edge_noise=0.18, alpha_sigma=2.4):
    cl = np.asarray(g.classic(set_, f))
    op = cl[..., 3] > 0
    pl = plant_mask(cl)
    st = op & ~pl
    pl4, st4, sil4 = np.kron(pl, K4), np.kron(st, K4), np.kron(op, K4)
    tex, hp = mix_tex(gfld, sfld, set_, f)
    c4 = np.kron(cl[..., :3].astype(np.float32), np.ones((4, 4, 1), np.float32))
    w = pl4.astype(np.float32)
    lc = norm_blur(c4, w, sigma_rel)
    lt = norm_blur(tex, w, sigma_rel)
    ratio = np.clip(lc / np.maximum(lt, 3.0), 0.2, 5.0)
    tex2 = np.clip(tex * ratio, 0, 255)
    # цоколь - из текущего HD кадра
    hd = b.hd_now(set_, str(f))
    hd_rgb = np.asarray(hd.convert("RGB"), np.float32)
    ms = ndimage.gaussian_filter(st4.astype(np.float32), 2.5)
    mm = np.clip((ms - 0.5 + edge_noise * hp) / 0.30 + 0.5, 0.0, 1.0)[..., None]
    rgb = tex2 * (1 - mm) + hd_rgb * mm
    al = smooth_alpha(sil4, alpha_sigma)
    out = np.zeros((160, 128, 4), np.uint8)
    out[..., :3] = np.where(al[..., None] > 0, np.rint(np.clip(rgb, 0, 255)), 0).astype(np.uint8)
    out[..., 3] = np.rint(al * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def build(name, **kw):
    gfld, sfld = fl.field_x4("g", SG), fl.field_x4("s", SS)
    d = os.path.join(CAND, name)
    os.makedirs(d, exist_ok=True)
    for s in SETS:
        for f in FRAMES:
            build_frame(gfld, sfld, s, f, **kw).save(os.path.join(d, "%s_%d.png" % (s, f)))
    print(name, ":", len(SETS) * len(FRAMES), "кадров ->", d)


def load(name, s, f):
    p = os.path.join(CAND, name, "%s_%d.png" % (s, f))
    return Image.open(p).convert("RGBA") if os.path.exists(p) else Image.new("RGBA", (128, 160))


def sheet(name, out, sets=("MOUNTTROP",), sc=2):
    cw, ch = 128 * sc, 160 * sc
    top = 20
    cols = ["классика x4", "HD сейчас", "кандидат " + name]
    rows = [(s, f) for s in sets for f in FRAMES]
    per = 3
    ncol_blocks = per
    nrow = (len(rows) + per - 1) // per
    bw = 3 * (cw + 2) + 10
    sh = Image.new("RGB", (per * bw, nrow * (ch + top + 4)), (12, 12, 14))
    d = ImageDraw.Draw(sh)
    for k, (s, f) in enumerate(rows):
        bx, by = (k % per) * bw, (k // per) * (ch + top + 4)
        d.text((bx + 2, by + 3), "%s:%d   классика | сейчас | кандидат" % (s, f), fill=(255, 220, 0), font=b.FONT)
        cls = Image.fromarray(np.kron(np.asarray(g.classic(s, f)), np.ones((4, 4, 1), np.uint8)))
        for ci, im in enumerate([cls, b.hd_now(s, str(f)), load(name, s, f)]):
            sh.paste(b.on_dark(im, scale=sc), (bx + ci * (cw + 2), by + top))
    sh.save(out)
    print("лист:", out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "sheet"])
    ap.add_argument("--name", default="A1")
    ap.add_argument("--out", default=os.path.join(REV, "t431_cand.png"))
    ap.add_argument("--sigma", type=float, default=9.0)
    ap.add_argument("--asigma", type=float, default=2.4)
    ap.add_argument("--sets", nargs="+", default=["MOUNTTROP"])
    ap.add_argument("--scale", type=int, default=2)
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.name, sigma_rel=a.sigma, alpha_sigma=a.asigma)
    else:
        sheet(a.name, a.out, tuple(a.sets), a.scale)
    return 0


if __name__ == "__main__":
    sys.exit(main())
