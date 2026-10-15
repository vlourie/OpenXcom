"""W-015: локальная доводка магазина cg4 до габарита оригинала без новой генерации, и замер частей на полном размере.

Магазин (коробка правее кольца крепления) пересэмплируется в целевой прямоугольник: левый край у кольца
закреплён, правый край и высота - по кадру ствола 1233. Кольцо, ствол, приклад и всё левее x 320 не трогаются.
Замер - по строкам базы на картинке 1024x1536 до маски и уменьшения: края тела в каждой строке против краёв
оригинала, переведённых той же сеткой.

    py -3.13 tools/hdart/w015_mag_fit.py
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
ROOT = "E:/OpenXCom"
RAW = ROOT + "/art/items/weapons-chatgpt-v1/raw/STR_COMBAT_SHOTGUN."
OUT = ROOT + "/art/items/weapons-chatgpt-v1"
SHEET = ROOT + "/census/items/export/exp_piratez/BIGOBS.PCK.png"
FRAME = 1233
# сетка база -> рабочая картинка (по неизменным частям cg3: тело y 33..1482 на 48 строк, x 77..453 на 12 столбцов)
Y0, SY = 33.0, (1482 - 33) / 48.0
X0, SX = 77.0, (453 - 77) / 12.0
COL0 = 1                       # левый столбец тела в кадре
MAG = (320, 395, 484, 576)     # цель коробки: x0, y0, x1, y1 (правый и нижний край исключены)
BG_T = 30                      # порог отличия от фона для коробки и тела
PARTS = [("дуло", 0, 1), ("ствол над держателем", 2, 6), ("держатель под дулом", 7, 8), ("ствол под держателем", 9, 11),
         ("магазин и кольцо", 12, 17), ("цевьё", 18, 27), ("спуск и рукоять", 28, 32), ("шейка приклада", 33, 37),
         ("приклад", 38, 47)]


def bx(c):
    return X0 + (c - COL0) * SX


def by(r):
    return Y0 + r * SY


def base_frame():
    idx = np.asarray(Image.open(SHEET))
    r, c = divmod(FRAME, 16)
    return idx[r * 48:(r + 1) * 48, c * 32:(c + 1) * 32]


def body_mask(a, bg):
    return np.abs(a - bg).max(2) > BG_T


def box_bbox(m):
    """Коробка магазина - тело правее 322 в полосе строк 12-17 с запасом."""
    z = m[360:620, 322:620]
    ys, xs = np.nonzero(z)
    return xs.min() + 322, ys.min() + 360, xs.max() + 323, ys.max() + 361


def fit(a, bg, src, dst):
    """Перенос коробки src -> dst (x0, y0, x1, y1): левый край закреплён, остальное масштабом, фон вокруг тем же
    сэмплом. Вырез с запасом по фону справа и сверху-снизу, чтобы шов лёг в ровный фон."""
    sx = (dst[2] - dst[0]) / (src[2] - src[0])
    sy = (dst[3] - dst[1]) / (src[3] - src[1])
    pad = 40
    cx0, cy0, cx1, cy1 = src[0], src[1] - pad, src[2] + pad, src[3] + pad
    crop = Image.fromarray(np.clip(a[cy0:cy1, cx0:cx1], 0, 255).astype(np.uint8))
    w = round((cx1 - cx0) * sx)
    h = round((cy1 - cy0) * sy)
    res = np.asarray(crop.resize((w, h), Image.LANCZOS)).astype(float)
    ox = dst[0]
    oy = round(dst[1] - pad * sy)
    out = a.copy()
    # растушёвка только по фону: справа, сверху и снизу; левый край у кольца - без смешения (там стык коробки)
    f = 8
    wy = np.ones(h)
    wy[:f] = np.linspace(0, 1, f)
    wy[-f:] = np.linspace(1, 0, f)
    wx = np.ones(w)
    wx[-f:] = np.linspace(1, 0, f)
    wgt = (wy[:, None] * wx[None, :])[..., None]
    reg = out[oy:oy + h, ox:ox + w]
    out[oy:oy + h, ox:ox + w] = reg * (1 - wgt) + res * wgt
    # фон, освобождённый сжатием по ширине (полоса за правым краем выреза), остаётся исходным - это фон
    return out, (ox, oy, ox + w, oy + h), (sx, sy)


def profile(m, f):
    """По каждой строке базы: края оригинала (сетка) и края тела на картинке (средняя половина полосы строки)."""
    rows = []
    for r in range(48):
        xs = np.nonzero(f[r])[0]
        y0, y1 = by(r), by(r + 1)
        q0, q1 = int(y0 + (y1 - y0) * 0.25), int(y0 + (y1 - y0) * 0.75)
        band = m[q0:q1]
        cols = np.nonzero(band.any(0))[0]
        rows.append({"row": r, "base_l": float(bx(xs.min())), "base_r": float(bx(xs.max() + 1)),
                     "hi_l": int(cols.min()) if len(cols) else None, "hi_r": int(cols.max() + 1) if len(cols) else None})
    return rows


def vert_extent(m, x0, x1):
    """Верх и низ тела в столбцах x0..x1."""
    ys = np.nonzero(m[:, int(x0):int(x1)].any(1))[0]
    return int(ys.min()), int(ys.max() + 1)


def report(name, a, bg, f):
    m = body_mask(a, bg)
    rows = profile(m, f)
    b = box_bbox(m)
    res = {"box": b, "rows": rows, "parts": []}
    print("== %s" % name)
    print("  магазин: x %d..%d, y %d..%d (длина %d, толщина %d); цель x %d..%d, y %d..%d (%d, %d)" % (
        b[0], b[2], b[1], b[3], b[2] - b[0], b[3] - b[1], MAG[0], MAG[2], MAG[1], MAG[3], MAG[2] - MAG[0], MAG[3] - MAG[1]))
    print("  по длине %+.1f %%, по толщине %+.1f %%; края против цели: прав %+d, верх %+d, низ %+d пикс" % (
        100.0 * ((b[2] - b[0]) / (MAG[2] - MAG[0]) - 1), 100.0 * ((b[3] - b[1]) / (MAG[3] - MAG[1]) - 1),
        b[2] - MAG[2], b[1] - MAG[1], b[3] - MAG[3]))
    for nm, r0, r1 in PARTS:
        sel = [x for x in rows[r0:r1 + 1] if x["hi_l"] is not None]
        dl = max((abs(x["hi_l"] - x["base_l"]) for x in sel), default=0) / SX
        dr = max((abs(x["hi_r"] - x["base_r"]) for x in sel), default=0) / SX
        ml = np.mean([x["hi_l"] - x["base_l"] for x in sel]) / SX
        mr = np.mean([x["hi_r"] - x["base_r"] for x in sel]) / SX
        res["parts"].append({"part": nm, "rows": [r0, r1], "mean_left": ml, "mean_right": mr, "max_left": dl, "max_right": dr})
        print("  %-22s строки %2d-%2d: левый край %+.2f (худш %.2f), правый %+.2f (худш %.2f) столбца базы" % (
            nm, r0, r1, ml, dl, mr, dr))
    # вертикаль: верх дула, держатель (строки, где тело шире ствола), низ приклада
    top, bot = vert_extent(m, X0, bx(14))
    wide = [x["row"] for x in rows if x["hi_l"] is not None and x["hi_l"] < bx(3) - SX * 0.5 and x["row"] < 12]
    hold = [i for i in range(140, 420) if m[i, int(X0):int(bx(3) - SX * 0.5)].any()]
    print("  дуло: верх тела y %d, по сетке %.0f (%+.2f строки)" % (top, by(0), (top - by(0)) / SY))
    print("  приклад: низ y %d, по сетке %.0f (%+.2f строки); правый край в строках 44-46 - см. таблицу" % (
        bot, by(48), (bot - by(48)) / SY))
    if hold:
        print("  держатель: y %d..%d, по сетке %.0f..%.0f (верх %+.2f, низ %+.2f строки)" % (
            hold[0], hold[-1] + 1, by(7), by(9), (hold[0] - by(7)) / SY, (hold[-1] + 1 - by(9)) / SY))
        res["holder"] = [hold[0], hold[-1] + 1]
    res["muzzle_top"], res["stock_bottom"] = top, bot
    return res


def sheet(a0, a1, b0, b1, p):
    box = (240, 340, 560, 620)
    ims = []
    for a, b in ((a0, b0), (a1, b1)):
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).crop(box)
        im = im.resize(((box[2] - box[0]) * 2, (box[3] - box[1]) * 2), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        d.rectangle([(MAG[0] - box[0]) * 2, (MAG[1] - box[1]) * 2, (MAG[2] - box[0]) * 2, (MAG[3] - box[1]) * 2],
                    outline=(0, 255, 0), width=2)
        d.rectangle([(b[0] - box[0]) * 2, (b[1] - box[1]) * 2, (b[2] - box[0]) * 2, (b[3] - box[1]) * 2],
                    outline=(255, 80, 80), width=1)
        ims.append(im)
    whole = [Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((256, 384), Image.LANCZOS) for a in (a0, a1)]
    W = sum(i.width for i in ims + whole) + 12 * 5
    out = Image.new("RGB", (W, ims[0].height + 40), (24, 24, 26))
    dr = ImageDraw.Draw(out)
    fnt = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
    x = 12
    for lab, im in zip(["cg4 целиком", "cg4fit целиком", "cg4: зелёная - цель, красная - коробка",
                        "cg4fit: доводка без генерации"], whole + ims):
        out.paste(im, (x, 30))
        dr.text((x, 8), lab, fill=(230, 230, 230), font=fnt)
        x += im.width + 12
    out.save(p)


def main():
    f = base_frame()
    a = np.asarray(Image.open(RAW + "cg4.region.png").convert("RGB")).astype(float)
    bg = np.median(np.concatenate([a[:20, :20].reshape(-1, 3), a[:20, -20:].reshape(-1, 3), a[-20:, -20:].reshape(-1, 3)]), 0)
    r0 = report("cg4.region (до доводки)", a, bg, f)
    src = r0["box"]
    out, reg, (sx, sy) = fit(a, bg, src, MAG)
    diff = np.abs(out - a).max(2) > 0
    outside = diff.copy()
    outside[reg[1]:reg[3], reg[0]:reg[2]] = False
    print("доводка: масштаб по длине %.3f, по толщине %.3f; область x %d..%d y %d..%d; изменено вне области: %d пикс" % (
        sx, sy, reg[0], reg[2], reg[1], reg[3], int(outside.sum())))
    assert outside.sum() == 0
    left = np.abs(out[:, :MAG[0]] - a[:, :MAG[0]]).max()
    print("левее x %d (кольцо, ствол, приклад) изменено: %.1f" % (MAG[0], left))
    assert left == 0
    p = RAW + "cg4fit.png"
    Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8)).save(p)
    print("записано", p)
    r1 = report("cg4fit (после доводки)", out, bg, f)
    sheet(a, out, src, r1["box"], OUT + "/compare_magfit_STR_COMBAT_SHOTGUN.png")
    json.dump({"grid": {"Y0": Y0, "SY": SY, "X0": X0, "SX": SX, "COL0": COL0}, "target": MAG, "scale": [sx, sy],
               "region": reg, "before": r0, "after": r1}, open(OUT + "/magfit_STR_COMBAT_SHOTGUN.json", "w",
                                                              encoding="utf-8-sig"), ensure_ascii=False, indent=1,
              default=lambda o: o.item() if hasattr(o, "item") else list(o))


if __name__ == "__main__":
    main()
