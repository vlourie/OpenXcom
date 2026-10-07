#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""STRUCT_GUIDE_V1 - чистая геометрия кадра 32x40 для входа PHOTO вместо bicubic (R-160).

Не размытие и не ESRGAN: контур маски и границы цветовых частей обходятся по рёбрам пикселей, и только
РЕГУЛЯРНАЯ лесенка в 1 пиксель (дискретная диагональ или кривая) заменяется линией через середины ступеней.
Всё нерегулярное остаётся прямоугольным, как в оригинале:
  * уступ в 1 пиксель на длинном крае (R10 D1 R10) - одна ступень, не лесенка: меньше MIN_CORNERS углов подряд;
  * ступени 2x2 и больше (лестница, зубцы) - ни у одной стороны ступени нет единичного прогона;
  * зубцы, прутья, ножки - направления не чередуются двумя (R D L), угол острый;
  * длинный прямой край между двумя лесенками - срез у него не больше половины соседних ступеней, середина
    остаётся прямой (R1 D1 R1 D1 R15 D1 R1).
Дыры: прозрачное внутри до photo_base.HOLE_NOISE пикселей - шум индекса 0, заливается (как photo_base.guide);
крупнее - контур дыры, спрямляется так же. Части - кластеры цвета (median cut, детерминированно), крапинки
меньше SPECK пикселей вливаются в соседа; часть закрашена своим средним цветом - без фактуры и материала.

Выход - картинка того же размера, что flat_input у photo_render (кадр x zoom на подложке), чтобы B и C
отличались от A только содержимым входа.

    py -3.13 tools/hdart/struct_guide.py --jobs art/objects/generation/probes/photo-accept-v1/jobs.json \
        --only C_INT:25 --out <папка>        # лист оригинал | bicubic | guide, без модели
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

ENC = "utf-8-sig"
GUIDE_V1 = {"name": "struct_guide_v1", "min_corners": 3, "colors": 6, "speck": 2, "ss": 4, "ratio": 2.0, "outlier": 48.0,
            "unit": "регулярная лесенка - единичный прогон у каждого угла, углов подряд не меньше min_corners"}
OUTLIER = GUIDE_V1["outlier"]   # расстояние RGB до палитры, дальше - свой цвет части
RATIO = GUIDE_V1["ratio"]   # соседние ступени лесенки различаются не больше чем вдвое (или на 1)
DIRS = {(1, 0): "R", (0, 1): "D", (-1, 0): "L", (0, -1): "U"}


# ---------------------------------------------------------------- контуры по рёбрам пикселей

def loops(mask):
    """Замкнутые контуры маски по рёбрам пикселей: список списков вершин (x, y) в углах пикселей.
    Тело всегда справа по ходу (экранные координаты, y вниз): наружный контур по часовой, дыра против.
    В седле (два пикселя касаются углом) тело связно по диагонали - поворот налево, на соседний пиксель."""
    h, w = mask.shape
    m = np.pad(mask.astype(bool), 1)
    out = defaultdict(list)
    for y, x in zip(*np.nonzero(mask)):
        yy, xx = y + 1, x + 1
        if not m[yy - 1, xx]:
            out[(x, y)].append((1, 0))
        if not m[yy, xx + 1]:
            out[(x + 1, y)].append((0, 1))
        if not m[yy + 1, xx]:
            out[(x + 1, y + 1)].append((-1, 0))
        if not m[yy, xx - 1]:
            out[(x, y + 1)].append((0, -1))
    used = set()
    res = []
    for v0 in sorted(out):
        for d0 in out[v0]:
            if (v0, d0) in used:
                continue
            loop = []
            v, d = v0, d0
            while (v, d) not in used:
                used.add((v, d))
                loop.append(v)
                v = (v[0] + d[0], v[1] + d[1])
                opts = [e for e in out[v] if (v, e) not in used]
                if not opts:
                    break
                if len(opts) > 1:
                    left = (d[1], -d[0])                # налево в экранных координатах
                    d = left if left in opts else opts[0]
                else:
                    d = opts[0]
            res.append(loop)
    return res


def runs(loop):
    """Вершины контура -> прогоны [(направление, длина, вершина начала)], начиная с поворота."""
    n = len(loop)
    steps = [(loop[(i + 1) % n][0] - loop[i][0], loop[(i + 1) % n][1] - loop[i][1]) for i in range(n)]
    k0 = next((i for i in range(n) if steps[i] != steps[i - 1]), 0)
    out = []
    for i in range(n):
        s = steps[(k0 + i) % n]
        if out and out[-1][0] == s:
            out[-1][1] += 1
        else:
            out.append([s, 1, loop[(k0 + i) % n]])
    return [tuple(r) for r in out]


def smooth_corners(rs, min_corners=GUIDE_V1["min_corners"]):
    """Какие углы контура - ступени регулярной лесенки. Угол i - между прогонами i и i+1 (по кругу).
    Кандидат: у угла есть прогон длины 1, и это ступень, а не зубец: прогоны по обе стороны от него одного
    направления (R D1 R - ступень, U R1 D - макушка прута). Лесенка - не меньше min_corners кандидатов подряд."""
    n = len(rs)
    d = [r[0] for r in rs]
    ln = [r[1] for r in rs]

    def step(u):
        if ln[u] != 1 or d[(u - 1) % n] != d[(u + 1) % n]:
            return False
        a, b = sorted((ln[(u - 1) % n], ln[(u + 1) % n]))
        return b - a <= 1 or b <= RATIO * a        # кривая меняет шаг плавно; 1, 4, 1, 5 - рваный край

    cand = [step(i) or step((i + 1) % n) for i in range(n)]
    if all(cand):
        return [True] * n
    smooth = [False] * n
    s = next(i for i in range(n) if not cand[i])
    chain = []
    for t in range(1, n + 1):
        k = (s + t) % n
        if cand[k]:
            chain.append(k)
            continue
        if len(chain) >= min_corners:
            for c in chain:
                smooth[c] = True
        chain = []
    return smooth


def smooth_loop(loop, min_corners=GUIDE_V1["min_corners"]):
    """Контур -> многоугольник (float): острые углы на месте, лесенка - через середины прогонов.
    Срез прогона у угла лесенки - половина его длины, но не больше половины соседнего прогона той же оси
    в лесенке: длинный прямой край между ступенями остаётся прямым посередине."""
    rs = runs(loop)
    n = len(rs)
    if n < 4:
        return [tuple(map(float, v)) for v in loop]
    sm = smooth_corners(rs, min_corners)
    ln = [r[1] for r in rs]
    pts = []
    for i, (dv, L, v0) in enumerate(rs):
        start_s = sm[(i - 1) % n]           # угол перед прогоном
        end_s = sm[i]                       # угол после прогона
        nb = []
        if start_s:
            nb.append(ln[(i - 2) % n])
        if end_s:
            nb.append(ln[(i + 2) % n])
        typ = max(nb) if nb else L
        a = min(L / 2.0, typ / 2.0) if start_s else 0.0
        b = min(L / 2.0, typ / 2.0) if end_s else 0.0
        p0 = (v0[0] + dv[0] * a, v0[1] + dv[1] * a)
        p1 = (v0[0] + dv[0] * (L - b), v0[1] + dv[1] * (L - b))
        pts.append(p0)
        if L - b - a > 1e-6:
            pts.append(p1)
    out = []
    for p in pts:
        if not out or abs(out[-1][0] - p[0]) + abs(out[-1][1] - p[1]) > 1e-9:
            out.append(p)
    return out


def coverage(polys, w, h, scale, ss=GUIDE_V1["ss"]):
    """Доля покрытия пикселя x scale многоугольниками (правило ненулевой обмотки), ss x ss отсчётов."""
    W, H = w * scale * ss, h * scale * ss
    k = scale * ss
    edges = []
    for P in polys:
        for i in range(len(P)):
            x0, y0 = P[i]
            x1, y1 = P[(i + 1) % len(P)]
            if y0 != y1:
                edges.append((x0 * k, y0 * k, x1 * k, y1 * k))
    hi = np.zeros((H, W), np.uint8)
    if not edges:
        return np.zeros((h * scale, w * scale), np.float32)
    e = np.array(edges, np.float64)
    xs = np.arange(W) + 0.5
    for row in range(H):
        yc = row + 0.5
        y0, y1 = e[:, 1], e[:, 3]
        hit = ((y0 <= yc) & (y1 > yc)) | ((y1 <= yc) & (y0 > yc))
        if not hit.any():
            continue
        ee = e[hit]
        t = (yc - ee[:, 1]) / (ee[:, 3] - ee[:, 1])
        xc = ee[:, 0] + t * (ee[:, 2] - ee[:, 0])
        wd = np.where(ee[:, 3] > ee[:, 1], 1, -1)
        o = np.argsort(xc)
        xc, wd = xc[o], wd[o]
        wind = np.cumsum(wd)
        idx = np.searchsorted(xc, xs)
        win = np.concatenate([[0], wind])[idx]
        hi[row] = win != 0
    return hi.reshape(h * scale, ss, w * scale, ss).mean((1, 3)).astype(np.float32)


# ---------------------------------------------------------------- части по цвету

def dither(lab):
    """Шахматка - фактура, не форма: у пикселя нет своих соседей по стороне, а по диагонали своих 3-4.
    Такие пиксели (все цвета шахматки разом, по исходной карте) - одна новая часть на связный кусок, её
    цвет потом - среднее. Тонкая диагональная линия так не теряется: своих по диагонали у неё не больше
    двух, и они напротив друг друга. У края тела (сосед по стороне - пустота) шахматке хватает двух своих
    по диагонали с одной стороны."""
    import photo_base as pb
    h, w = lab.shape

    def at(yy, xx):
        return lab[yy, xx] if 0 <= yy < h and 0 <= xx < w else -1

    dz = np.zeros((h, w), bool)
    for y in range(h):
        for x in range(w):
            c = lab[y, x]
            if c < 0:
                continue
            body = [s for s in (at(y - 1, x), at(y + 1, x), at(y, x - 1), at(y, x + 1)) if s >= 0]
            if c in body or len(body) < 2:
                continue
            dg = [(dy, dx) for dy, dx in ((-1, -1), (-1, 1), (1, -1), (1, 1)) if at(y + dy, x + dx) == c]
            one_side = len(dg) == 2 and (dg[0][0] == dg[1][0] or dg[0][1] == dg[1][1])
            dz[y, x] = len(dg) >= 3 or (len(body) < 4 and one_side)
    cl, nc = pb.label(dz, 8)
    top = int(lab.max()) + 1
    for i in range(1, nc + 1):
        lab[cl == i] = top + i - 1
    return lab


def median_cut(px, colors):
    """Палитра median cut (PIL, без дизеринга) из пикселей Nx3 - детерминированно."""
    strip = Image.fromarray(px.reshape(1, -1, 3).astype(np.uint8), "RGB")
    n = min(colors, len(np.unique(px.reshape(-1, 3), axis=0)))
    q = strip.quantize(colors=n, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    return np.array(q.getpalette()[:3 * n], np.float32).reshape(-1, 3)


def parts(frame, colors=GUIDE_V1["colors"], speck=GUIDE_V1["speck"]):
    """Карта частей кадра: (lab HxW, -1 вне тела; список средних цветов). Median cut по телу; пиксели дальше
    OUTLIER от всей палитры - малый, но другой цвет - получают ещё до трёх своих цветов. Крапинки
    меньше speck пикселей (8-связно) - в самого частого соседа. Дыры-шум залиты, как photo_base.guide."""
    import photo_base as pb
    a = np.asarray(frame.convert("RGBA"))
    g = pb.guide(frame)
    m = g["m"]
    h, w = m.shape
    rgb = a[..., :3].copy()
    alive = a[..., 3] > 0
    if (m & ~alive).any():                  # залитый шум - цвет соседа по телу
        ys, xs = np.nonzero(m & ~alive)
        for y, x in zip(ys, xs):
            nb = [rgb[yy, xx] for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1))
                  if 0 <= yy < h and 0 <= xx < w and alive[yy, xx]]
            rgb[y, x] = np.mean(nb, 0) if nb else (128, 128, 128)
    px = rgb[m]
    lab = np.full((h, w), -1, np.int32)
    if not len(px):
        return lab, [], m
    pal = median_cut(px, colors)
    far = np.sqrt(((px[:, None, :].astype(np.float32) - pal[None]) ** 2).sum(-1)).min(1) > OUTLIER
    if far.any():                           # малый, но другой цвет (жёлтый знак на сером) - своя часть
        pal = np.concatenate([pal, median_cut(px[far], 3)])
    lab[m] = np.sqrt(((px[:, None, :].astype(np.float32) - pal[None]) ** 2).sum(-1)).argmin(1)
    dither(lab)
    for _ in range(4):                      # крапинки вливаются, пока есть
        changed = False
        for c in np.unique(lab[lab >= 0]):
            cl, nc = pb.label(lab == c, 8)
            for i in range(1, nc + 1):
                comp = cl == i
                if comp.sum() >= speck:
                    continue
                ring = pb.grow(comp, 1) & ~comp & (lab >= 0) & (lab != c)
                if not ring.any():
                    continue
                lab[comp] = Counter(lab[ring].tolist()).most_common(1)[0][0]
                changed = True
        if not changed:
            break
    keep = sorted(np.unique(lab[lab >= 0]).tolist())
    remap = {c: i for i, c in enumerate(keep)}
    out = np.full_like(lab, -1)
    cols = []
    for c in keep:
        out[lab == c] = remap[c]
        cols.append(tuple(int(v) for v in rgb[lab == c].mean(0).round()))
    return out, cols, m


def build(frame, zoom, panel_rgb, params=GUIDE_V1):
    """Guide кадра: RGB размером кадр x zoom на подложке panel_rgb (как flat_input) и отчёт."""
    lab, cols, m = parts(frame, params["colors"], params["speck"])
    h, w = m.shape
    sil = coverage([smooth_loop(L, params["min_corners"]) for L in loops(m)], w, h, zoom, params["ss"])
    cov = np.stack([coverage([smooth_loop(L, params["min_corners"]) for L in loops(lab == i)], w, h, zoom,
                             params["ss"]) for i in range(len(cols))]) if cols else np.zeros((1, h * zoom, w * zoom))
    win = cov.argmax(0)
    pal = np.array(cols or [(128, 128, 128)], np.float32)
    body = pal[win]
    a = sil[..., None]
    out = body * a + np.asarray(panel_rgb, np.float32) * (1 - a)
    stair = 0
    for L in loops(m):
        stair += sum(smooth_corners(runs(L), params["min_corners"])) if len(runs(L)) >= 4 else 0
    rep = {"parts": len(cols), "loops": len(loops(m)), "stair_corners": int(stair), "px": int(m.sum())}
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGB"), rep


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--zoom", type=int, default=16)
    args = ap.parse_args()
    os.chdir(ROOT)
    import map_mockup as mm
    import photo_base as pb
    import photo_render as pr
    with open(args.jobs, encoding=ENC) as f:
        jobs = json.load(f)
    if args.only:
        names = args.only.split(",")
        jobs = sorted((j for j in jobs if j["asset_id"] in names), key=lambda j: names.index(j["asset_id"]))
    world = mm.World()
    os.makedirs(args.out, exist_ok=True)
    rows = []
    for j in jobs:
        _c, _w, _a, _b, frame = pb.job_frame(world, j)
        name, rgb, _m = pr.panels_by_margin(frame)[0]
        g, rep = build(frame, args.zoom, rgb)
        a = pr.flat_input(frame, rgb, args.zoom)
        near = frame.resize((frame.width * args.zoom, frame.height * args.zoom), Image.NEAREST)
        n = Image.new("RGB", near.size, tuple(int(v) for v in rgb))
        n.paste(near, (0, 0), near.convert("RGBA"))
        g.save(os.path.join(args.out, j["asset_id"].replace(":", "_") + ".guide.png"))
        rows.append((j["asset_id"], [n, a, g]))
        print("%-24s %s" % (j["asset_id"], rep), flush=True)
    if rows:
        cw = max(r[1][0].width for r in rows)
        chh = max(r[1][0].height for r in rows)
        sheet = Image.new("RGB", (cw * 3 + 40, (chh + 10) * len(rows)), (40, 40, 40))
        for k, (_aid, ims) in enumerate(rows):
            for c, im in enumerate(ims):
                sheet.paste(im, (c * (cw + 20), k * (chh + 10)))
        sheet.save(os.path.join(args.out, "guide_sheet.png"))


if __name__ == "__main__":
    main()
