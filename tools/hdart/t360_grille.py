#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000360 и XP-000359: решётка RUSTSHACKS 17 (цела), 18 (разрушена, dieMCD) и серый пол RUSTSHACKS 29 -
по маске и цветам своей классики, без видеокарты.

Классика: 17 и 18 - коричнево-красная шахматка с прорезями, серая рамка; в 17 в середине стоит плотный тёмный крест
(индексы 13/14 на месте прорезей), у 18 разбитые места. 29 - пятнистый серый пол. HD пака (sdxl_legacy до 21.09,
ни одного одобрения): поверх шахматки вязаные волны и блики, рваная серо-голубая кромка с бурыми бликами, поле 5x5 -
каша. Лечение - рецепт решётки LINERSHIPA 24/95 (cov44, одобрена Vitali 13.10), R-298, R-253, R-291:

  17, 18: pixel_lines --holes --dither с одним отличием. У лайнера подложкой nearest x4 идут одиночные пиксели
          шахматки, у RUSTSHACKS шахматка с тёмным заполнением (соседние пиксели) - xBRZ сводил её в лабиринт, как
          в заготовке b11 14.10. Поэтому подложкой nearest идёт вся внутренность решётки (dm <= RIM), прорези
          совпадают с классикой x4 по пикселю; рамка по ромбу - xBRZ поля копий с перехлёстом (R-291), как у лайнера.
  29:     pixel_lines без изменений (xBRZ поля копий x4: пятна классики, ровная кромка, без шва между клетками).

    py -3.13 tools/hdart/t360_grille.py                  # кадры в art/tickets/t360/out/TERRAIN/RUSTSHACKS.PCK
    py -3.13 tools/hdart/t360_grille.py --install --yes  # + в мод hd через манифест (по слову Vitali, под очередью правок)
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb          # noqa: E402
import ground_seam as gs          # noqa: E402
import pixel_lines as pl          # noqa: E402
import sprite_scale as ss         # noqa: E402
import contour_check as cc        # noqa: E402
import ticket_scene as ts         # noqa: E402

K, PAD = pl.K, pl.PAD
RIM = 0.84                        # рамка: ромб глубже 0.84 (две полосы классики по 1 пикс), дальше - решётка
OUT = ROOT / "art" / "tickets" / "t360" / "out"
SET = "RUSTSHACKS"


def interior(cl):
    b = gs.dmap()[K // 2::K, K // 2::K]
    return (cl > 0) & (b <= RIM)


def render_lattice(cl, pal):
    fld, (ox, oy) = pl.build_field(cl)
    sub = fld[oy - PAD:oy + 40 + PAD, ox - PAD:ox + 32 + PAD]
    ifl, _ = pl.build_field(np.where(interior(cl), cl, 0))
    isub = ifl[oy - PAD:oy + 40 + PAD, ox - PAD:ox + 32 + PAD]
    dith = isub > 0
    top = np.where(dith, 0, sub)
    a = (top > 0).astype(np.float32) * 255.0
    rgba = np.concatenate([pal[top], a[..., None]], -1)[None]
    up = ss.xbrz_scale(rgba, K)[0][PAD * K:-PAD * K, PAD * K:-PAD * K]
    lt, la = up[..., :3], up[..., 3:] / 255.0
    bsub = np.where(dith, sub, 0)[PAD:-PAD, PAD:-PAD]
    brgb = np.repeat(np.repeat(pal[bsub], K, 0), K, 1)
    ba = np.repeat(np.repeat((bsub > 0).astype(np.float32), K, 0), K, 1)[..., None]
    oa = la + ba * (1 - la)
    rgb = (lt * la + brgb * ba * (1 - la)) / np.maximum(oa, 1e-6)
    return rgb, np.minimum(oa[..., 0], pl.own_gate(cl, pal))


def build_grille(cl, pal):
    dm = gs.dmap()
    al = (dm <= 1.0 + pl.OVERLAP).astype(np.float32)
    rgb, ha = render_lattice(cl, pal)
    return pl.beyond_diamond(cl, pal, rgb, al * ha, dm)


def build_all():
    pal = wb.palette().astype(np.float32)
    fr = wb.read_set(SET)
    res = {}
    for f in (17, 18):
        res[f] = build_grille(fr[f], pal)
    res[29] = pl.build(fr[29], pal)
    return res


def save_all(res):
    files = {}
    for f, (rgb, fa) in sorted(res.items()):
        cl = wb.read_set(SET)[f]
        v, why = cc.verdict(cl, fa, wb.palette().astype(np.float32))
        if v != "ok":
            raise SystemExit("%s %d: %s" % (SET, f, why))
        gs.save_rgba(rgb, fa, str(OUT / "TERRAIN"), SET, str(f))
        files["TERRAIN/%s.PCK/%d.png" % (SET, f)] = OUT / "TERRAIN" / ("%s.PCK" % SET) / ("%d.png" % f)
    return files


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files = save_all(build_all())
    print("кадров: %d -> %s" % (len(files), OUT))
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(files, "t360_grille", "t360_grille.py 28.10 решётка по рецепту LINERSHIPA 24/95: подложка nearest x4, рамка xBRZ; пол 29 pixel_lines",
                         "Vitali 28.10 (XP-000359/XP-000360, вариант А процедурно, 3 кадра); лист art/_review/tickets_2026-10-28/t360_fix_sheet.png",
                         "t360: решётка RUSTSHACKS 17/18 и серый пол 29 по классике")
    return 0


if __name__ == "__main__":
    sys.exit(main())
