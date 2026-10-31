#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты 302 (пшеница) и 329 (рожь): бесшовное поле, вариант cut (выбор Vitali 26.10 ~23:40) -> мод hd через манифест.
Кромка C (ticket_q21_edge.py, d214fb930) заменяется.

Кадры - art/_review/xp302/seam/*_cut.png (t302_seam.py: периодическая функция плоскости, разрез графа, перекраски
переносом цвета классики с периодическими полями, тон UBER не подстраивался):
  CULTIVAT:4     - CULTIVAT_4_cut.png;
  VILROADS:1     - побайтная копия классики CULTIVAT:4 -> тот же кадр;
  CULTIVAT_PP:4, CULTIVAT_UBER:4 - CULTIVAT_PP_4_cut.png, CULTIVAT_UBER_4_cut.png.
Найденные семьёй, но не ставятся: GOTHIC:8 (классика на 96 % та же, свой HD lora_oxcehd_v1) - в отчёте.

    py -3.13 tools\hdart\t302_install.py          # сухой прогон: кадры в art/_review/tickets_2026-10-26/after и лист sheet_t302.png
    py -3.13 tools\hdart\t302_install.py --yes    # в мод hd (манифест, обе копии; под очередью правок)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)
import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw                    # noqa: E402
import build_hd_pack as bp                          # noqa: E402

R = os.path.join(ROOT, "art", "_review")
OUT = os.path.join(R, "tickets_2026-10-26")
STAGE = os.path.join(OUT, "after")
SEAM = os.path.join(R, "xp302", "seam")
FLOOR = (24, 20, 18)
_world = None


def world():
    global _world
    if _world is None:
        import map_mockup as mm
        _world = mm.World()
    return _world


def classic(s, f):
    return world().sprite(s.lower(), f, None).convert("RGBA")


def tpath(s, f):
    return "TERRAIN/%s.PCK/%d.png" % (s, f)


def game_png(rel):
    return os.path.join(bp.TARGETS["game"], rel)


def level(hd, cb):
    """Яркость основы C (светлее классики в ~1.3 раза) приводится к средней яркости классики перед переносом цвета:
    иначе у светлой перекраски (UBER) каналы упираются в 255 и оттенок уходит в кремовый."""
    a = np.asarray(hd, np.float32).copy()
    c = np.asarray(cb, np.float32)
    w = np.array([0.299, 0.587, 0.114], np.float32)
    ya = (a[..., :3] @ w)[a[..., 3] > 200].mean()
    yc = (c[..., :3] @ w)[c[..., 3] > 200].mean()
    a[..., :3] = np.clip(a[..., :3] * (yc / ya), 0, 255)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def build():
    hd = Image.open(os.path.join(SEAM, "CULTIVAT_4_cut.png")).convert("RGBA")
    cb = classic("CULTIVAT", 4)
    out = {("CULTIVAT", 4): hd}
    cv = classic("VILROADS", 1)
    if not np.array_equal(np.asarray(cb), np.asarray(cv)):
        raise SystemExit("VILROADS:1 уже не копия классики CULTIVAT:4")
    out[("VILROADS", 1)] = hd
    for s in ("CULTIVAT_PP", "CULTIVAT_UBER"):
        out[(s, 4)] = Image.open(os.path.join(SEAM, "%s_4_cut.png" % s)).convert("RGBA")
    files = {}
    for (s, f), im in out.items():
        rel = tpath(s, f)
        dst = os.path.join(STAGE, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        im.save(dst, optimize=True)
        cur = game_png(rel)
        if os.path.exists(cur) and Image.open(cur).size != im.size:
            raise SystemExit("размер не совпадает " + rel)
        files[rel] = dst
    return files


def field(tile, rows=4, cols=5, k=4):
    w = (rows + cols) * 16 * k + 32 * k
    h = (rows + cols) * 8 * k + 40 * k
    im = Image.new("RGBA", (w, h), FLOOR + (255,))
    ox = rows * 16 * k
    for y in range(rows):
        for x in range(cols):
            im.alpha_composite(tile, (ox + (x - y) * 16 * k, (x + y) * 8 * k))
    return im.convert("RGB").resize((w // 2, h // 2), Image.LANCZOS)


def sheet(files):
    rows = []
    for rel, new in files.items():
        s = rel.split("/")[1][:-4]
        fr = int(os.path.basename(rel)[:-4])
        old = Image.open(game_png(rel)).convert("RGBA")
        cl = classic(s, fr).resize((128, 160), Image.NEAREST)
        rows.append(("%s:%d" % (s, fr), [field(cl), field(old), field(Image.open(new).convert("RGBA"))]))
    fw, fh = rows[0][1][0].size
    sh = Image.new("RGB", (3 * fw + 16, len(rows) * (fh + 18) + 6), (14, 14, 18))
    d = ImageDraw.Draw(sh)
    for i, (lab, ims) in enumerate(rows):
        y0 = 4 + i * (fh + 18)
        d.text((6, y0), lab + "   classic | was | now (field 5x4, k=4, sheet x0.5)", fill=(255, 220, 80))
        for j, im in enumerate(ims):
            sh.paste(im, (4 + j * (fw + 4), y0 + 14))
    p = os.path.join(OUT, "sheet_t302.png")
    sh.save(p)
    print("лист:", p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files = build()
    for rel in files:
        print(rel)
    sheet(files)
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (по слову Vitali, под очередью правок)")
    import ticket_scene as ts
    n = ts.install_files(files, "t302_install", "t302_install.py 26.10 (t302_seam.py, cut)",
                         "Vitali: выбор cut (бесшовное поле) 26.10 ~23:40, взамен кромки C",
                         "t302: пшеница/рожь без швов CULTIVAT 4, VILROADS 1, CULTIVAT_PP 4, CULTIVAT_UBER 4 (cut)")
    print("установлено файлов: %d" % n)


if __name__ == "__main__":
    main()
