#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000417, круг 3: контейнер PORTROADS 81-86 рисуется ПРОЦЕДУРНО по геометрии классики (а не нейросетью).

Классика - скип-контейнер: усечённая призма (плоские стенки, борта вертикальные, торцы сужены книзу), открытый сверху, толстый бортик по
периметру, вертикальные швы-рёбра на длинных стенках, коричневые складки на углах дальнего торца. Параметры (P) подобраны по классике:
силуэт и линии совпадают с ромбом клеток 2x3 (левый угол основания в холсте (0,48), оси a=(16,-8) вдоль длинной стороны, b=(16,8) вдоль
короткой, z - вверх в пикселях базы). Цвета - те же семь цветов палитры классики с плавными переходами (свет слева-сверху).

Нарезка на кадры: каждый кадр - это КЛЕТКА (a, b) контейнера, нарисованная сама по себе (грани, обрезанные по границам клетки с запасом EPS;
закрывает только сама на себя), а закрытие клеток друг другом делает порядок рисования движка (дальние клетки раньше, ближние позже:
85, 86, 84, 83, 82, 81 - ровно по глубине). Поэтому:
  - 2x3 и 2x4 собираются из одних и тех же кадров без шва: средняя клетка (84/83) - срез бесконечной трубы, она одинакова в любой раскладке;
    торцевые тени, торцы и складки лежат в клетках 82/81 и 85/86, рёбра - в серединах клеток;
  - края: покрытие граней по меткам 8x8 на пиксель x4, внешний контур - отрезки 2:1, 1:1 и вертикали со сглаживанием, внутри альфа 255.

    py -3.13 tools\hdart\t417_proc.py build [--tag имя]      кадры -> art/tickets/t417/cand/p<тег>/ (холсты 2x3 и 2x4 рядом)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
import cv2                              # noqa: E402
from PIL import Image                   # noqa: E402

K = 4                                   # масштаб кадров x4
SS = 8                                  # сверхдискретизация покрытия граней
EPS = 0.04                              # запас клетки по a и b у соседей (в ячейках), ~0.6 пикс базы

# цвета классики (RGB)
A_ = np.array([252, 208, 0], np.float32)     # самый светлый: бортик, дно
B_ = np.array([236, 180, 0], np.float32)     # блик у ребра
C_ = np.array([224, 160, 0], np.float32)     # стенка
D_ = np.array([208, 136, 0], np.float32)     # тень под бортиком
E_ = np.array([136, 96, 51], np.float32)     # коричневый: торец, ребро, складка
F_ = np.array([82, 57, 23], np.float32)      # самый тёмный: край торца
HI_ = np.array([255, 228, 70], np.float32)   # блик на скруглённом бортике

P = dict(
    bm=0.125,        # поле от края клетки до наружной стенки (по b)
    zr=19.5,         # высота верха бортика над землёй, пикс базы
    zb=4.0,          # высота дна контейнера над землёй
    ta=0.65,         # на сколько торцы сужены книзу (в ячейках по a)
    dw=0.2,          # ширина бортика по b (толстый бортик)
    dn=0.2,          # то же по a (торцы)
    zf=6.0,          # высота внутреннего дна
    ribs=(0.7, 1.45, 2.2),   # положение рёбер по a (классика: шаг 0.75); в 2x4 вторая ячейка повторяется
    rib_w=0.07,      # ширина ребра, ячейки
    tex=0.02,        # сила фактуры металла
    ao=0.07,         # ширина тени у основания стенок, ячейки
)

# ячейка (a, b) -> кадр PORTROADS (раскладка 2x3: 82 (0,0) 81 (0,1) / 84 (1,0) 83 (1,1) / 85 (2,0) 86 (2,1))
CELL_FRAME = {(0, 0): 82, (0, 1): 81, (1, 0): 84, (1, 1): 83, (2, 0): 85, (2, 1): 86}


class Model:
    """3D -> экран. a, b - в ячейках, z - в пикселях базы; p00 - левый угол основания (пикс базы в холсте)."""

    def __init__(self, n, p00, par=None):
        self.par = dict(P)
        if par:
            self.par.update(par)
        self.n = n                               # длина в ячейках: 3 (2x3) или 4 (2x4)
        self.p00 = p00
        p = self.par
        self.A = n - p["bm"]                     # верх бортика по a: от 0 до A
        self.k = p["ta"] / (p["zr"] - p["zb"])   # сужение торца на пиксель высоты
        ribs = list(p["ribs"])
        if n == 4:
            ribs = [ribs[0], ribs[1], ribs[1] + 1.0, ribs[2] + 1.0]
        self.ribs = ribs

    def scr(self, a, b, z):
        return (self.p00[0] + 16.0 * (a + b), self.p00[1] - 8.0 * a + 8.0 * b - z)

    def a_left(self, z, off=0.0):
        return self.k * (self.par["zr"] - z) + off

    def a_right(self, z, off=0.0):
        return self.A - self.k * (self.par["zr"] - z) - off

    def inv_const_z(self, X, Y, z):
        xp, yp = X - self.p00[0], Y - self.p00[1]
        s, d = xp / 16.0, (yp + z) / 8.0
        return (s - d) / 2.0, (s + d) / 2.0        # a, b

    def inv_const_b(self, X, Y, b):
        xp, yp = X - self.p00[0], Y - self.p00[1]
        a = xp / 16.0 - b
        z = -8.0 * a + 8.0 * b - yp
        return a, z

    def inv_end(self, X, Y, c0, kk):
        """плоскость a = c0 + kk z: возвращает (b, z)"""
        xp, yp = X - self.p00[0], Y - self.p00[1]
        z = (xp / 2.0 - 16.0 * c0 - yp) / (1.0 + 16.0 * kk)
        a = c0 + kk * z
        b = xp / 16.0 - a
        return b, z


def noise_tile(seed, ny, nx, octs=3):
    """гладкая «металлическая» фактура, периодическая по x (x = a mod 1)"""
    rng = np.random.default_rng(seed)
    out = np.zeros((ny, nx), np.float32)
    amp = 1.0
    for o in range(octs):
        gy, gx = 6 * 2 ** o, 4 * 2 ** o
        g = rng.standard_normal((gy, gx)).astype(np.float32)
        g = np.concatenate([g, g[:, :1]], axis=1)
        up = cv2.resize(g, (nx + nx // gx, ny), interpolation=cv2.INTER_CUBIC)[:, :nx]
        out += amp * up
        amp *= 0.5
    out -= out.mean()
    out /= max(1e-6, float(np.abs(out).max()))
    return out


def lerp(c0, c1, t):
    t = np.clip(t, 0.0, 1.0)[..., None]
    return c0 * (1.0 - t) + c1 * t


def full(c, shp):
    return np.broadcast_to(np.asarray(c, np.float32), shp + (3,)).copy()


_TEX = {}


def face_colours(model, X, Y, seed=4171):
    """цвет каждой грани в точках (X, Y) окна (пикс базы), продолженный за грань: словарь метка -> (h, w, 3).
    Метки: 1 ближняя длинная стенка (снаружи), 2 левый торец (снаружи), 3 бортик, 5 дальняя стенка (внутри), 6 дальний торец (внутри), 7 дно."""
    p = model.par
    shp = X.shape
    bm, dw, dn, zr, zb, zf, A = p["bm"], p["dw"], p["dn"], p["zr"], p["zb"], p["zf"], model.A
    k = model.k
    b0, b1 = bm, 2.0 - bm
    bi0, bi1 = bm + dw, 2.0 - bm - dw
    if seed not in _TEX:
        _TEX[seed] = noise_tile(seed, 256, 96)
    tex = _TEX[seed]
    tx = p["tex"]

    def texv(a, z):
        ix = (np.mod(a, 1.0) * 96.0).astype(np.float32)
        iy = np.mod(z * 7.0, 256.0).astype(np.float32)
        return cv2.remap(tex, ix, iy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)

    def ribs_of(a):
        core = np.zeros_like(a)
        hi = np.zeros_like(a)
        w = p["rib_w"]
        for r in model.ribs:
            d = a - r
            core = np.maximum(core, np.clip(1.0 - np.abs(d) / (w * 0.5), 0, 1) ** 0.7)
            hi = np.maximum(hi, np.clip(1.0 - np.abs(d + w * 0.95) / (w * 0.75), 0, 1))
        return core, hi

    col = {}
    # 1 ближняя стенка
    a, z = model.inv_const_b(X, Y, b1)
    t = np.clip((zr - z) / (zr - zb), 0, 1)
    c = lerp(full(C_, shp), full([204, 144, 0], shp), t ** 1.4 * 0.85)
    c = lerp(c, full(D_, shp), np.clip(1.0 - (zr - z) / 2.4, 0, 1) ** 1.6 * 0.9)
    c = lerp(c, full(E_, shp), np.clip(1.0 - np.abs(zr - z - 0.5) / 0.5, 0, 1) * 0.5)           # тень от губы бортика
    core, hi = ribs_of(a)
    ribz = ((z < zr - 1.6) & (z > zb + 0.3)).astype(np.float32)
    c = lerp(c, full(B_, shp), hi * 0.6 * ribz)
    c = lerp(c, full(E_, shp), core * 0.92 * ribz)
    col[1] = c * (1.0 + tx * texv(a, z)[..., None])
    # 2 левый торец
    b, z = model.inv_end(X, Y, k * zr, -k)
    t = np.clip((zr - z) / (zr - zb), 0, 1)
    c = lerp(full([146, 104, 44], shp), full([112, 78, 33], shp), t)
    c = lerp(c, full(D_ * 0.78, shp), np.clip(1.0 - (zr - z) / 2.4, 0, 1) * 0.55)
    edge = np.clip(1.0 - np.minimum(b - b0, 0.3) / 0.3, 0, 1)
    c = lerp(c, full(F_, shp), edge ** 3 * 0.85)
    col[2] = c * (1.0 + 1.5 * tx * texv(b * 2.0, z)[..., None])
    # 3 бортик: от наружного края к внутреннему - блик, светлая плоскость, внутренняя кромка
    a, b = model.inv_const_z(X, Y, zr)
    dist_out = np.minimum.reduce([b - b0, b1 - b, (a - 0.0) * (dw / dn), (A - a) * (dw / dn)])
    t = np.clip(dist_out / dw, 0, 1)
    c = lerp(full(HI_, shp), full(A_, shp), np.clip(t * 4.0, 0, 1))
    c = lerp(c, full(B_, shp), np.clip((t - 0.7) / 0.3, 0, 1) * 0.55)
    col[3] = c * (1.0 + tx * texv(a, b * 10.0)[..., None])
    # 5 дальняя длинная стенка (внутри)
    a, z = model.inv_const_b(X, Y, bi0)
    t = np.clip((zr - z) / (zr - zf), 0, 1)
    c = lerp(full(C_, shp), full([234, 174, 0], shp), t ** 1.2)
    c = lerp(c, full(D_, shp), np.clip(1.0 - (zr - z) / 3.0, 0, 1) ** 1.5 * 0.9)
    c = lerp(c, full(E_, shp), np.clip(1.0 - np.abs(zr - z - 0.4) / 0.45, 0, 1) * 0.5)
    core, hi = ribs_of(a)
    ribz = ((z < zr - 2.2) & (z > zf + 0.2)).astype(np.float32)
    c = lerp(c, full(B_, shp), hi * 0.6 * ribz)
    c = lerp(c, full(E_, shp), core * 0.92 * ribz)
    col[5] = c * (1.0 + tx * texv(a, z)[..., None])
    # 6 дальний торец (внутри): складки на углах коричневые
    b, z = model.inv_end(X, Y, A - dn - k * zr, k)
    t = np.clip((zr - z) / (zr - zf), 0, 1)
    c = lerp(full([228, 166, 0], shp), full([238, 182, 0], shp), t ** 1.3)
    c = lerp(c, full(D_, shp), np.clip(1.0 - (zr - z) / 3.0, 0, 1) ** 1.5 * 0.9)
    c = lerp(c, full(E_, shp), np.clip(1.0 - np.abs(zr - z - 0.4) / 0.45, 0, 1) * 0.5)
    c = lerp(c, full(E_, shp), np.clip(1.0 - np.abs(b - bi0) / 0.045, 0, 1) * 0.85)        # складка с дальней стенкой
    c = lerp(c, full(E_, shp), np.clip(1.0 - np.abs(z - zf) / 0.6, 0, 1) * 0.8)           # складка со дном
    col[6] = c * (1.0 + tx * texv(b * 2.0, z)[..., None])
    # 7 дно
    a, b = model.inv_const_z(X, Y, zf)
    af1 = model.a_right(zf, dn)
    af0 = model.a_left(zf, dn)
    c = full(A_, shp)
    w_ao = p["ao"]
    ao = np.clip(1.0 - (b - bi0) / w_ao, 0, 1) ** 1.5 * 0.9
    ao = np.maximum(ao, np.clip(1.0 - (af1 - a) / w_ao, 0, 1) ** 1.5 * 0.9)
    ao = np.maximum(ao, np.clip(1.0 - (a - af0) / (w_ao * 1.5), 0, 1) ** 1.5 * 0.8)
    ao = np.maximum(ao, np.clip(1.0 - (bi1 - b) / w_ao, 0, 1) ** 1.5 * 0.5)
    c = lerp(c, full(B_ * 0.96, shp), ao)
    col[7] = c * (1.0 + tx * texv(a, b * 10.0)[..., None])
    return col


def faces3d(model):
    """грани в трёх измерениях (a, b, z), в порядке рисования: (метка, [вершины])"""
    p = model.par
    bm, dw, dn, zr, zb, zf, A = p["bm"], p["dw"], p["dn"], p["zr"], p["zb"], p["zf"], model.A
    b0, b1 = bm, 2.0 - bm
    bi0, bi1 = bm + dw, 2.0 - bm - dw
    al_f, ar_f = model.a_left(zf, dn), model.a_right(zf, dn)
    return [
        (5, [(al_f, bi0, zf), (ar_f, bi0, zf), (A - dn, bi0, zr), (dn, bi0, zr)]),                           # дальняя стенка внутри
        (6, [(ar_f, bi0, zf), (ar_f, bi1, zf), (A - dn, bi1, zr), (A - dn, bi0, zr)]),                       # дальний торец внутри
        (7, [(al_f, bi0, zf), (ar_f, bi0, zf), (ar_f, bi1, zf), (al_f, bi1, zf)]),                           # дно
        (3, [(0, b0, zr), (A, b0, zr), (A, bi0, zr), (0, bi0, zr)]),                                           # бортик дальний
        (3, [(0, bi1, zr), (A, bi1, zr), (A, b1, zr), (0, b1, zr)]),                                           # бортик ближний
        (3, [(0, bi0, zr), (dn, bi0, zr), (dn, bi1, zr), (0, bi1, zr)]),                                       # бортик левый
        (3, [(A - dn, bi0, zr), (A, bi0, zr), (A, bi1, zr), (A - dn, bi1, zr)]),                               # бортик правый
        (1, [(0, b1, zr), (A, b1, zr), (model.a_right(zb), b1, zb), (model.a_left(zb), b1, zb)]),            # ближняя стенка снаружи
        (2, [(0, b0, zr), (0, b1, zr), (model.a_left(zb), b1, zb), (model.a_left(zb), b0, zb)]),             # левый торец снаружи
    ]


def clip_box(poly, amin, amax, bmin, bmax):
    """обрезка выпуклого многоугольника в 3D по ящику в (a, b): Сазерленд-Ходжман по четырём плоскостям"""
    def clip(pts, axis, val, keep_ge):
        out = []
        n = len(pts)
        for i in range(n):
            p0, p1 = pts[i], pts[(i + 1) % n]
            in0 = (p0[axis] >= val) if keep_ge else (p0[axis] <= val)
            in1 = (p1[axis] >= val) if keep_ge else (p1[axis] <= val)
            if in0:
                out.append(p0)
            if in0 != in1:
                t = (val - p0[axis]) / (p1[axis] - p0[axis])
                out.append(tuple(p0[j] + t * (p1[j] - p0[j]) for j in range(3)))
        return out
    pts = list(poly)
    for axis, val, ge in ((0, amin, True), (0, amax, False), (1, bmin, True), (1, bmax, False)):
        if not pts:
            break
        pts = clip(pts, axis, val, ge)
    return pts


def render_window(model, x0, y0, w, h, box, seed=4171):
    """одна клетка (box = (amin, amax, bmin, bmax)) в окне (x0, y0, w, h) пикс базы: RGBA uint8 (h*K, w*K, 4); None-края - без обрезки"""
    shp = (h * K, w * K)
    yy, xx = np.mgrid[0:h * K, 0:w * K].astype(np.float32)
    X, Y = x0 + (xx + 0.5) / K, y0 + (yy + 0.5) / K
    big = np.zeros((h * K * SS, w * K * SS), np.uint8)
    for lab, poly in faces3d(model):
        pts = clip_box(poly, *box)
        if len(pts) < 3:
            continue
        sp = [model.scr(*q) for q in pts]
        arr = np.round((np.asarray(sp, np.float64) - (x0, y0)) * K * SS).astype(np.int32)
        cv2.fillPoly(big, [arr], int(lab))
    lab = big.reshape(h * K, SS, w * K, SS)
    col = face_colours(model, X, Y, seed)
    rgb = np.zeros(shp + (3,), np.float32)
    al = np.zeros(shp, np.float32)
    for L, c in col.items():
        wgt = (lab == L).mean(axis=(1, 3)).astype(np.float32)
        rgb += c * wgt[..., None]
        al += wgt
    out = np.zeros(shp + (4,), np.uint8)
    out[..., :3] = np.clip(rgb / np.maximum(al, 1e-6)[..., None] * (al[..., None] > 1e-6), 0, 255).astype(np.uint8)
    out[..., 3] = np.rint(np.clip(al, 0, 1) * 255).astype(np.uint8)
    return out


def cell_box(model, ia, ib, eps=EPS):
    big = 1e9
    return (ia - eps if ia > 0 else -big, ia + 1 + eps if ia < model.n - 1 else big,
            ib - eps if ib > 0 else -big, ib + 1 + eps if ib < 1 else big)


def layout_geometry(n):
    """размер холста и левый угол основания для 2x3 (n=3) и 2x4 (n=4) по таблице раскладок"""
    import t417_container_gen as g
    cells = g.C23 if n == 3 else g.C24
    items, W, H = g.make_items(cells)
    it = min(items, key=lambda i: (i["x"], -i["y"]))
    return items, W, H, (it["x"], it["y"] + 32)


def build_frames(par=None, seed=4171):
    """шесть кадров 128x160 из клеток модели 2x3 (кадр = клетка в своём окне 32x40)"""
    items, W, H, p00 = layout_geometry(3)
    model = Model(3, p00, par)
    frames = {}
    for it in items:
        cell = [c for c, f in CELL_FRAME.items() if f == it["f"]][0]
        rgba = render_window(model, it["x"], it["y"], 32, 40, cell_box(model, *cell), seed)
        frames[it["f"]] = Image.fromarray(rgba, "RGBA")
    return frames, model


def truth_canvas(n, par=None, seed=4171):
    """эталон раскладки: всё в одном окне, рисуется сразу целиком (видимая поверхность), для сверки сборки из кадров"""
    items, W, H, p00 = layout_geometry(n)
    model = Model(n, p00, par)
    big = -1e9, 1e9, -1e9, 1e9
    rgba = render_window(model, 0, 0, W, H, big, seed)
    return rgba, items, W, H, model


def build(tag="a", par=None, seed=4171):
    import t417_container_gen as g
    d = os.path.join(g.CAND, "p" + tag)
    os.makedirs(d, exist_ok=True)
    frames, _m = build_frames(par, seed)
    for f, im in frames.items():
        im.save(os.path.join(d, "%s_%d.png" % (g.SET, f)))
    return d, frames


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("--tag", default="a")
    a = ap.parse_args()
    d, _ = build(a.tag)
    print("кадры:", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
