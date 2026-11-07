#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Лист приёмки XP-000364: бочка и труба - классика / было / стало, вид из сейва игрока, крышка и труба крупно,
кадры по одному, мерки (шов между кадрами, перекрытия, тон, силуэт).

    py -3.13 tools\hdart\t364_sheet.py            # art/_review/tickets_2026-10-28/t364_fix_sheet.png
    py -3.13 tools\hdart\t364_sheet.py --live     # "стало" берётся из установленного пака, а не из art/tickets/t364/cand
"""
import base64
import re
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import t364_build as tb  # noqa: E402

ts = tb.ts
ROOT = tb.ROOT
SAVE = ROOT / "census" / "tickets" / "XP-000364" / "files" / "02__autobattle_.asav"
OUT = ROOT / "art" / "_review" / "tickets_2026-10-28"
K = 4
BG = (150, 120, 60)
LUMW = np.array([0.299, 0.587, 0.114], np.float32)
BARREL_FRAMES = (43, 44, 45, 46)
PIPE_FRAMES = (3, 4, 5, 7, 9, 11)
ALL = BARREL_FRAMES + PIPE_FRAMES


def read_save(path=SAVE):
    f = open(path, "rb").read().decode("utf-8", "replace")
    b = base64.b64decode(re.search(r"binTiles: (\S+)", f).group(1))
    sets = [s.strip()[2:] for s in re.search(r"mapdatasets:\n((?:    - .*\n)+)", f).group(1).split("\n") if s.strip()]
    tiles = {}
    for i in range(0, len(b), 23):
        idx = struct.unpack("<I", b[i:i + 4])[0]
        ids = struct.unpack("<4h", b[i + 4:i + 12])
        sid = struct.unpack("<4h", b[i + 12:i + 20])
        tiles[(idx % 60, (idx // 60) % 60, idx // 3600)] = (ids, sid)
    return tiles, sets


class Src:
    """Источник кадров: 'classic', 'old' (art/tickets/t364/old), 'new' (cand) или 'live' (пак установки)."""

    def __init__(self, sc, mode, cand=None):
        self.sc, self.mode = sc, mode
        self.cand = cand or tb.CAND

    def get(self, S, f):
        if self.mode == "classic":
            return self.sc.classic(S, f)
        if S == tb.SET and f in ALL:
            if self.mode == "old":
                return Image.open(tb.OLD / ("%d.png" % f)).convert("RGBA")
            if self.mode == "new":
                return Image.open(self.cand / ("%d.png" % f)).convert("RGBA")
        h = self.sc.hd(S, f)
        return h if h is not None else self.sc.classic(S, f)


def render_area(tiles, sets, sc, src, x0, x1, y0, y1):
    W = ((x1 - x0) + (y1 - y0)) * 16 + 64
    H = ((x1 - x0) + (y1 - y0)) * 8 + 120
    ox, oy = (y1 - y0) * 16 + 16, 60
    im = Image.new("RGBA", (W * K, H * K), BG + (255,))
    recs = {}
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            t = tiles.get((x, y, 0))
            if not t:
                continue
            ids, sid = t
            for p in range(4):
                if ids[p] < 0 or sid[p] < 0 or sets[sid[p]] == "BLANKS":
                    continue
                S = sets[sid[p]]
                R = recs.get(S) or recs.setdefault(S, sc.w.records(S))
                r = R[ids[p]]
                spr = src.get(S, r["frame"])
                if spr is None:
                    continue
                if spr.width != 32 * K:
                    spr = spr.resize((32 * K, 40 * K), Image.NEAREST)
                im.alpha_composite(spr, ((ox + ((x - x0) - (y - y0)) * 16) * K,
                                         (oy + ((x - x0) + (y - y0)) * 8 - r["p_level"]) * K))
    return im


def lab(im, t, n=20):
    return ts.label(im.convert("RGB").copy(), t, n)


def row(panels, gap=10):
    H = max(p.height for p in panels)
    out = Image.new("RGB", (sum(p.width for p in panels) + gap * (len(panels) + 1), H), (20, 20, 24))
    x = gap
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def zoom(im, box, z):
    c = im.crop(box)
    return c.resize((int(c.width * z), int(c.height * z)), Image.NEAREST)


def barrel(src, sc, S=tb.SET, fr=(46, 44, 45, 43)):
    im = Image.new("RGBA", (64 * K, 72 * K), BG + (255,))
    for f, (ox, oy) in zip(fr, ((16, 0), (32, 8), (0, 8), (16, 16))):
        s = src.get(S, f)
        if s.width != 32 * K:
            s = s.resize((32 * K, 40 * K), Image.NEAREST)
        im.alpha_composite(s, (ox * K, oy * K))
    return im


def lum(a):
    return np.asarray(a, np.float32)[..., :3] @ LUMW


def arrangement(src, sc, items):
    """Холст x4 из клеток (x, y, кадр) в порядке движка: цвет, владелец пикселя (кадр, нарисованный последним) и маска."""
    cv = tb.Canvas(sc, [(x, y, f, None) for x, y, f in items])
    H, W = cv.ch * K, cv.cw * K
    own = -np.ones((H, W), int)
    L = np.zeros((H, W), np.float32)
    inst = -np.ones((H, W), int)
    for n, it in enumerate(cv.items):
        ox, oy = cv.pos(it)
        a = np.asarray(src.get(tb.SET, it[2]).convert("RGBA").resize((32 * K, 40 * K), Image.NEAREST))
        m = a[..., 3] >= 200
        sl = (slice(oy * K, oy * K + 40 * K), slice(ox * K, ox * K + 32 * K))
        own[sl][m] = it[2]
        inst[sl][m] = n
        L[sl][m] = lum(a)[m]
    return own, inst, L


def seam_stats(src, sc, items):
    """Средний перепад яркости через границу двух КЛЕТОК (экземпляров кадров) и внутри клетки, x4; отношение.
    Клетки одного кадра рядом (прямая труба 11-11) тоже граница - в классике там такая же ступень."""
    own, inst, L = arrangement(src, sc, items)
    inner, cross = [], []
    for dy, dx in ((0, 1), (1, 0)):
        a = inst[:inst.shape[0] - dy, :inst.shape[1] - dx]
        b = inst[dy:, dx:]
        d = np.abs(L[:L.shape[0] - dy, :L.shape[1] - dx] - L[dy:, dx:])
        ok = (a >= 0) & (b >= 0)
        inner.append(d[ok & (a == b)])
        cross.append(d[ok & (a != b)])
    inner, cross = np.concatenate(inner), np.concatenate(cross)
    return float(cross.mean()), float(inner.mean()), float(cross.mean() / inner.mean())


def lid_line(img):
    """Вертикальная линия по крышке: наибольший вертикально-когерентный перепад яркости в полосе +-6 пикселей базы
    около середины крышки / медиана по ширине крышки (1.0 - линии нет). Крышка - верхняя треть-пятая части бочки."""
    a = np.asarray(img.convert("RGBA"), np.float32)
    al = a[..., 3] > 0
    ys = np.nonzero(al.any(axis=1))[0]
    y0, y1 = ys.min(), ys.max()
    # фон листа - не прозрачный: берём пиксели, отличные от фона
    L = a[..., :3] @ LUMW
    bgm = np.abs(a[..., :3] - np.array(BG, np.float32)).sum(axis=2) < 6
    obj = ~bgm
    ys = np.nonzero(obj.any(axis=1))[0]
    y0, y1 = ys.min(), ys.max()
    r0, r1 = y0 + int(0.12 * (y1 - y0)), y0 + int(0.33 * (y1 - y0))
    xs = np.nonzero(obj[r0:r1].all(axis=0))[0]
    if xs.size < 40:
        xs = np.nonzero(obj[r0:r1].any(axis=0))[0]
    cx = int(xs.mean())
    prof = {}
    for c in range(int(xs.min()) + 8, int(xs.max()) - 8):
        d = np.abs(L[r0:r1, c] - 0.5 * (L[r0:r1, c - 3] + L[r0:r1, c + 3]))
        prof[c] = float(d.mean())
    med = float(np.median(list(prof.values())))
    pk = max(v for c, v in prof.items() if abs(c - cx) <= 6 * K)
    return pk / max(med, 1e-6)


def tone_composite(src, sc, items):
    """Средняя яркость видимых пикселей раскладки / то же у классики (тон целого)."""
    own, inst, L = arrangement(src, sc, items)
    return float(L[own >= 0].mean())


def tone_rows(old, new, sc):
    rows = []
    for f in ALL:
        c = np.asarray(sc.classic(tb.SET, f)).astype(float)
        mc = c[..., 3] > 0
        r = [f]
        for src in (old, new):
            a = np.asarray(src.get(tb.SET, f)).astype(float)
            ma = a[..., 3] > 128
            r += [int((ma & ~mc).sum()), 100.0 * (ma & mc).sum() / mc.sum(), int((~ma & mc).sum())]
        rows.append(r)
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    live = "--live" in sys.argv
    sc = ts.Scene()
    tiles, sets = read_save()
    cls, old = Src(sc, "classic"), Src(sc, "old")
    new = Src(sc, "live" if live else "new")
    x0, x1, y0, y1 = 17, 33, 30, 38
    area = {n: render_area(tiles, sets, sc, s, x0, x1, y0, y1) for n, s in (("c", cls), ("o", old), ("n", new))}
    # окно: бочка (21..22,34..35) и труба (22..27,33) в координатах render_area
    cx0 = ((21 - x0) - (35 - y0)) * 16 + ((y1 - y0) * 16 + 16) - 4
    box = (cx0 * K, 240 * K // 4 * 1, (cx0 + 190) * K, (240 + 80) * K // 4 * 1 + 120)
    shot = Image.open(ROOT / "census" / "tickets" / "XP-000364" / "files" / "01_shot.png").convert("RGB").crop((1190, 530, 1690, 790))
    # вид из сейва: окно подбирается по положению бочки
    bx = (((21 - x0) - (34 - y0)) * 16 + (y1 - y0) * 16 + 16) * K
    by = (60 + ((21 - x0) + (34 - y0)) * 8) * K
    win = (bx - 70 * K, by - 40 * K, bx + 230 * K, by + 95 * K)
    W3 = 640
    views = [lab(zoom(area[n], win, W3 / (win[2] - win[0])), t) for n, t in (("c", "классика (вид из сейва, x4)"), ("o", "было (HD до правки)"), ("n", "стало"))]
    r1 = row(views)
    # крышка крупно
    barrels = {n: barrel(s, sc) for n, s in (("c", cls), ("o", old), ("n", new))}
    lid = (24, 10, 232, 150)
    r2 = row([lab(zoom(barrels[n], lid, 3.2), t) for n, t in (("c", "крышка: классика"), ("o", "крышка: было (крест, заклёпки, зубцы)"), ("n", "крышка: стало"))])
    # труба крупно
    px0 = (((22 - x0) - (33 - y0)) * 16 + (y1 - y0) * 16 + 16 - 4) * K
    py0 = (60 + ((22 - x0) + (33 - y0)) * 8 - 8) * K
    pwin = (px0, py0, px0 + 232 * K, py0 + 70 * K)
    r3 = row([lab(zoom(area[n], pwin, 640 / (232 * K)), t) for n, t in (("c", "труба: классика"), ("o", "труба: было"), ("n", "труба: стало"))])
    # кадры по одному
    def cell(src, f, t):
        s = src.get(tb.SET, f)
        bgi = Image.new("RGBA", (128, 160), (70, 70, 76, 255))
        if s.width != 128:
            s = s.resize((128, 160), Image.NEAREST)
        bgi.alpha_composite(s)
        return lab(bgi, "%d %s" % (f, t), 14)
    fr = []
    for f in ALL:
        fr += [cell(cls, f, "кл"), cell(old, f, "было"), cell(new, f, "стало")]
    r4a = row(fr[:15], gap=4)
    r4b = row(fr[15:], gap=4)
    # мерки
    bar = [(21, 34, 46), (22, 34, 44), (21, 35, 45), (22, 35, 43)]
    pipe = [(x, y, f) for x, y, f in tb.PIPE_RAW if f != 8]      # тройник 8 одобрен, в мерки не идёт
    lines = []
    lines.append("вертикальная линия по середине крышки (пик / медиана перепада яркости, 1.0 - линии нет): классика %.2f; было %.2f; стало %.2f; донор MADDECOR_WASTE 75-78 %.2f" % (
        lid_line(barrels["c"]), lid_line(barrels["o"]), lid_line(barrels["n"]), lid_line(barrel(old, sc, "MADDECOR_WASTE", (75, 76, 77, 78)))))
    for nm_, items in (("бочка 2x2", bar), ("сеть труб блока DSRTREFI_12 (без тройника 8)", pipe)):
        st = [seam_stats(s_, sc, items) for s_ in (cls, old, new)]
        tn = [tone_composite(s_, sc, items) for s_ in (cls, old, new)]
        lines.append("%s: перепад яркости через границу клеток / внутри клетки (отношение): классика %.1f / %.1f (%.2fx); было %.1f / %.1f (%.2fx); стало %.1f / %.1f (%.2fx)" % (nm_, *st[0], *st[1], *st[2]))
        lines.append("%s: средняя яркость видимых пикселей: классика %.1f, было %.1f (x%.2f), стало %.1f (x%.2f)" % (nm_, tn[0], tn[1], tn[1] / tn[0], tn[2], tn[2] / tn[0]))
    for r in tone_rows(old, new, sc):
        lines.append("кадр %2d: пикселей вне силуэта классики x4 - было %d (покрытие %.1f%%, дыр %d), стало %d (покрытие %.1f%%, дыр %d)" % tuple(r))
    fnt = ts.font(16)
    r5 = Image.new("RGB", (max(r.width for r in (r1, r2, r3, r4a, r4b)), 24 * len(lines) + 12), (20, 20, 24))
    d = ImageDraw.Draw(r5)
    for i, t in enumerate(lines):
        d.text((10, 6 + 24 * i), t, fill=(230, 230, 210), font=fnt)
    rows = [r1, r2, r3, r4a, r4b, r5]
    W = max(r.width for r in rows)
    H = sum(r.height for r in rows) + 10 * (len(rows) + 1)
    sheet = Image.new("RGB", (W, H), (12, 12, 14))
    y = 10
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + 10
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "t364_fix_sheet.png"
    sheet.save(p)
    print(p, sheet.size)
    for t in lines:
        print(t)


if __name__ == "__main__":
    main()
