#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000302/329: поле пшеницы CULTIVAT:4 без шва между клетками (Vitali 26.10 ~23:00: «КРОМКИ МЕЖДУ КЛЕТКАМИ НЕ БЫЛО»).
Без видеокарты, без игры, в мод ничего не ставится.

Причина шва (измерена): светлый обод 2-3 px от подложки генерации (R-089) + рисунок не продолжается за край клетки.
Здесь кадр строится как ПЕРИОДИЧЕСКАЯ функция плоскости: цвет верхней грани в пикселе (X,Y) = P[класс(X,Y)], где класс -
вычет по решётке клеток (вектора (64,32) и (-64,32) при k=4, 4096 классов). Любые две клетки поля в одном месте плоскости
дают один и тот же пиксель - шва нет по построению, где бы ни стоял сосед.
  1. Основа - вариант a (art/_review/xp302/gen/CULTIVAT_4_a.png, как выбрал Vitali). Ромб верха = ровно по одному
     пикселю на класс. Кайма подложки (4 px от внешнего силуэта) и пиксели с альфой < 200 - недостоверные: заливаются
     и в разрезе (п. 3) получают штраф, то есть берутся только если иначе нельзя.
  2. Низкие частоты (освещение, sigma 7 px) снимаются с основы и возвращаются ей же, но посчитанные на торе (периодическое
     размытие): тон у основы a остаётся прежним (она светлее классики в ~1.4 раза - не дефект), без ступени на краю клетки.
  3. Рисунок делается периодичным (кандидаты):
       cut   - разрез: основа и она же, сдвинутая на полпериода вдоль стыка (в два прохода - по одному семейству стыков:
               линии u = x+2y и v = 2y-x). Около стыка своей копии берётся сдвинутая (там стыка нет), в стороне -
               несдвинутая, граница между ними - минимальный разрез графа (Kwatra 2003) по тёмным щелям между колосьями.
       blend - то же без разреза: граница - плавный переход (кросс-фейд), колосья на переходе двоятся.
       cut2  - как cut, но другой сдвиг (второй по цене разреза в каждом проходе), другой раскрой.
     Боковые грани (видны только по краю поля) - то же на цилиндре: период 64 px вдоль стены.
  4. Альфа: внутри контура куба (ромб + две грани, по центрам пикселей) - 255, снаружи (колосья над задней кромкой) -
     мягкая альфа основы a; цвет колосьев над кромкой берётся из периодической текстуры, не из каймы подложки.
  5. Перекраски PP / UBER - перенос цвета классики как в obj_derive.transfer (с приведением яркости), но поля цвета
     считаются периодическим размытием (иначе у перекраски свой шов по краю клетки).

    py -3.13 tools/hdart/t302_seam.py                # кандидаты, меры, листы art/_review/xp302/seam/
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_flow

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)

OUT = os.path.join(ROOT, "art", "_review", "xp302", "seam")
SRC_A = os.path.join(ROOT, "art", "_review", "xp302", "gen", "CULTIVAT_4_a.png")
SRC_C = os.path.join(ROOT, "art", "_review", "xp302", "edge", "CULTIVAT_4_C_wrap.png")

W, H = 128, 160            # кадр k=4
YC = 70                    # центр ромба верха по y (17.5 пикселя классики, R-403: вершина на 0.5 ниже края)
PX, PY = 128, 32           # область-представитель классов: 128 x 32, шаг по y сдвигает x на 64
RU = 59                    # высота грани в строках развёртки
LUMW = np.array([0.299, 0.587, 0.114], np.float32)
GRAY = (112, 112, 118)
SQ5 = np.sqrt(5.0)


# ---------- геометрия решётки ----------
def cidx(X, Y):
    """номер класса по решётке клеток; X, Y - целые массивы (любая плоскость)"""
    m = np.floor_divide(Y, PY)
    return (Y - PY * m) * PX + np.mod(X - 64 * m, PX)


Yg, Xg = np.mgrid[0:H, 0:W]
XC, YCc = Xg + 0.5, Yg + 0.5
EDGE = np.where(XC < 64, YC + XC / 2, YC + 32 - (XC - 64) / 2)       # нижние рёбра ромба
REG = np.where(YCc < EDGE, 0, np.where(Xg < 64, 1, 2))               # 0 верх (и колосья над кромкой), 1 левая грань, 2 правая
DIAMOND = (np.abs(XC - 64) / 64 + np.abs(YCc - YC) / 32) < 1
CIDX = cidx(Xg, Yg)
assert DIAMOND.sum() == 4096 and len(np.unique(CIDX[DIAMOND])) == 4096
LOW = np.where(XC < 64, 128 + XC / 2, 160 - (XC - 64) / 2)
HULLF = (REG > 0) & (YCc < LOW)                                      # пиксели граней внутри контура куба
HULL = DIAMOND | HULLF


def face_xy(side):
    """развёртка грани: (r, s) -> кадр (X, Y); s - вдоль стены (период 64), r - вглубь грани"""
    s = np.arange(64)[None, :]
    r = np.arange(RU)[:, None]
    if side == 1:
        return s + 0 * r, YC + ((s + 1) >> 1) + r
    return 64 + s + 0 * r, YC + 32 - ((s + 1) >> 1) + r


FACE = {1: face_xy(1), 2: face_xy(2)}


def to_U(img, side):
    X, Y = FACE[side]
    ok = Y < H
    return img[np.minimum(Y, H - 1), X], ok


def put_U(out, U, side):
    """развёртка -> кадр для пикселей своей грани (r вне развёртки зажимается)"""
    Y0 = FACE[side][1][0]
    m = REG == side
    s = np.clip(Xg - (0 if side == 1 else 64), 0, 63)
    r = np.clip(Yg - Y0[s], 0, RU - 1)
    out[m] = U[r[m], s[m]]


# ---------- периодическое размытие ----------
def blur_top(v, w, sigma):
    C = v.shape[2]
    num = np.zeros((4096, C), np.float32)
    den = np.zeros(4096, np.float32)
    d = DIAMOND
    num[CIDX[d]] = v[d] * w[d][:, None]
    den[CIDX[d]] = w[d]
    pad = int(3 * sigma) + 2
    Xw, Yw = np.meshgrid(np.arange(-pad, PX + pad), np.arange(-pad, PY + pad))
    ci = cidx(Xw, Yw)
    nw, dw = num[ci], den[ci]
    nb = np.stack([cv2.GaussianBlur(nw[..., c], (0, 0), sigma) for c in range(C)], -1)
    db = cv2.GaussianBlur(dw, (0, 0), sigma)
    res = (nb / np.maximum(db, 1e-4)[..., None])[pad:pad + PY, pad:pad + PX].reshape(4096, C)
    out = np.zeros_like(v)
    m = REG == 0
    out[m] = res[CIDX[m]]
    return out


def blur_face(v, w, sigma, side):
    U, ok = to_U(v, side)
    wu, _ = to_U(w[..., None], side)
    wu = wu[..., 0] * ok
    C = v.shape[2]
    Ut = np.tile(U * wu[..., None], (1, 3, 1))
    wt = np.tile(wu, (1, 3))
    nb = np.stack([cv2.GaussianBlur(Ut[..., c], (0, 0), sigma) for c in range(C)], -1)[:, 64:128]
    db = cv2.GaussianBlur(wt, (0, 0), sigma)[:, 64:128]
    Ub = nb / np.maximum(db, 1e-4)[..., None]
    out = np.zeros_like(v)
    put_U(out, Ub, side)
    return out


def smooth_frame(v, w, sigma):
    """периодическое размытие всего кадра: верх - по решётке клеток, грани - по циклу вдоль стены. v (H,W,C), w (H,W)"""
    v = v.astype(np.float32)
    w = w.astype(np.float32)
    o = blur_top(v, w, sigma)
    for side in (1, 2):
        b = blur_face(v, w, sigma, side)
        m = REG == side
        o[m] = b[m]
    return o


# ---------- минимальный разрез ----------
INF = 10 ** 8
SC = 400.0


def mincut(nb_a, nb_b, un0, un1, wpair):
    """узлы 0..n-1; рёбра (nb_a, nb_b) с ёмкостью wpair; un0/un1 - цена метки 0/1. Метка 1 = сторона истока."""
    n = len(un0)
    S, T = n, n + 1
    rows = np.concatenate([nb_a, nb_b, np.full(n, S), np.arange(n)])
    cols = np.concatenate([nb_b, nb_a, np.arange(n), np.full(n, T)])
    cap = np.minimum(np.concatenate([wpair, wpair, un0, un1]).astype(np.int64), INF).astype(np.int32)
    keep = cap > 0
    g = csr_matrix((cap[keep], (rows[keep], cols[keep])), shape=(n + 2, n + 2))
    g.sum_duplicates()
    res = maximum_flow(g, S, T)
    resid = (g - res.flow).tocsr()
    resid.data[resid.data < 0] = 0
    resid.eliminate_zeros()
    seen = np.zeros(n + 2, bool)
    seen[S] = True
    stack = [S]
    ip, ind = resid.indptr, resid.indices
    while stack:
        a = stack.pop()
        for b in ind[ip[a]:ip[a + 1]]:
            if not seen[b]:
                seen[b] = True
                stack.append(b)
    return seen[:n].astype(np.uint8), res.flow_value


def torus_graph():
    c = np.arange(4096)
    X, Y = c % PX, c // PX
    return np.concatenate([c, c]), np.concatenate([cidx(X + 1, Y), cidx(X, Y + 1)])


def cyl_graph(h, w=64):
    n = h * w
    c = np.arange(n).reshape(h, w)
    return (np.concatenate([c.ravel(), c[:-1].ravel()]), np.concatenate([np.roll(c, -1, 1).ravel(), c[1:].ravel()]))


def dist_fam(fam):
    """расстояние (px) каждого класса до линий стыка семейства: 'u' (u = X+2Y = 12 mod 128) или 'v' (v = 2Y-X = 12)"""
    c = np.arange(4096)
    X, Y = c % PX, c // PX
    q = (X + 2 * Y) if fam == "u" else (2 * Y - X)
    return np.abs(((q - 12 + 64) % 128) - 64) / SQ5


def shift_idx(dx, dy):
    c = np.arange(4096)
    return cidx(c % PX + dx, c // PX + dy)


def pair_weights(A, B, a, b, grad=True):
    d = np.abs(A - B).sum(1)
    pw = d[a] + d[b]
    if grad:
        ga = np.abs(A[a] - A[b]).sum(1) + np.abs(B[a] - B[b]).sum(1)
        pw = pw / (1.0 + 4.0 * ga)
    return np.rint(pw * SC).astype(np.int64) + 1


def cut_pass(P0, bad0, fam, s, w1=5.0, lam=40.0):
    """один проход: убрать стык семейства fam; s=(dx,dy) - сдвиг вдоль линий другого семейства. Возврат (P, bad, метки, цена)"""
    sh = shift_idx(*s)
    d = dist_fam(fam)
    near0 = d < w1
    near1 = d[sh] < w1
    if (near0 & near1).any():
        return None
    A, B = P0, P0[sh]
    a, b = torus_graph()
    wp = pair_weights(A, B, a, b)
    un0 = np.zeros(4096, np.int64)
    un1 = np.zeros(4096, np.int64)
    un0[near0] = INF
    un1[near1] = INF
    un0[bad0 & ~near0] += int(lam * SC)
    un1[bad0[sh] & ~near1] += int(lam * SC)
    lab, cost = mincut(a, b, un0, un1, wp)
    P = np.where(lab[:, None] == 1, B, A)
    bad = np.where(lab == 1, bad0[sh], bad0)
    return P, bad, lab, cost / SC


def shifts_for(fam, step=4, span=24):
    """сдвиги, которые двигают стык семейства fam на полпериода (+-span) и оставляют линии другого семейства на месте"""
    out = []
    for a in range(-span, span + 1, step):
        if fam == "u":      # du = 64 + a, dv = 0
            du, dv = 64 + a, 0
        else:
            du, dv = 0, 64 + a
        if (du - dv) % 2 or (du + dv) % 4:
            continue
        out.append(((du - dv) // 2, (du + dv) // 4))
    return out


def two_pass(Et, bad, pick=0, w1=5.0):
    """pick: 0 - лучший сдвиг каждого прохода, 1 - второй по цене, и т.д. Возврат (P, bad, описание, цена)"""
    desc, tot = [], 0.0
    P, bd = Et, bad
    for fam in ("u", "v"):
        res = []
        for s in shifts_for(fam):
            r = cut_pass(P, bd, fam, s, w1)
            if r is not None:
                res.append((r[3], s, r))
        res.sort(key=lambda t: t[0])
        cost, s, r = res[min(pick, len(res) - 1)]
        P, bd = r[0], r[1]
        desc.append("%s: сдвиг %s цена %.1f" % (fam, s, cost))
        tot += cost
    return P, bd, "; ".join(desc), tot


def blend_two(Et, d0=4.0, d1=13.0):
    """кросс-фейд в два прохода: P' = t*P + (1-t)*P(+s), t - плавная ступень по расстоянию до стыка"""
    P = Et
    for fam in ("u", "v"):
        s = shifts_for(fam)[len(shifts_for(fam)) // 2]
        sh = shift_idx(*s)
        t = np.clip((dist_fam(fam) - d0) / (d1 - d0), 0, 1)
        t = (t * t * (3 - 2 * t))[:, None]
        P = P * t + P[sh] * (1 - t)
    return P


def cut_face(Un, bad, dx=32, w1=5, lam=40.0):
    """Un (RU,64,3) -> периодично по s. Возврат: Up, метки, цена"""
    h = Un.shape[0]
    B = np.roll(Un, -dx, 1)
    s = np.arange(64)
    near0 = np.broadcast_to(np.minimum(s, 64 - s) < w1, (h, 64)).ravel()
    near1 = np.broadcast_to(np.abs(((s - dx + 32) % 64) - 32) < w1, (h, 64)).ravel()
    a, b = cyl_graph(h)
    Af, Bf = Un.reshape(-1, 3), B.reshape(-1, 3)
    wp = pair_weights(Af, Bf, a, b)
    un0 = np.zeros(h * 64, np.int64)
    un1 = np.zeros(h * 64, np.int64)
    un0[near0] = INF
    un1[near1] = INF
    bf = bad.reshape(-1)
    bs = np.roll(bad, -dx, 1).reshape(-1)
    un0[bf & ~near0] += int(lam * SC)
    un1[bs & ~near1] += int(lam * SC)
    lab, cost = mincut(a, b, un0, un1, wp)
    lab = lab.reshape(h, 64)
    return np.where(lab[..., None] == 1, B, Un), lab, cost / SC


def blend_face(Un, dx=32, d0=3.0, d1=12.0):
    s = np.arange(64)
    t = np.clip((np.minimum(s, 64 - s).astype(np.float32) - d0) / (d1 - d0), 0, 1)
    t = (t * t * (3 - 2 * t))[None, :, None]
    return Un * t + np.roll(Un, -dx, 1) * (1 - t)


# ---------- основа ----------
def load(p):
    return np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)


def lum(a):
    return a[..., :3] @ LUMW


def classic_of(sname, frame=4):
    import map_mockup as mm
    w = getattr(classic_of, "_w", None)
    if w is None:
        w = classic_of._w = mm.World()
    c = np.asarray(w.sprite(sname, frame, None).convert("RGBA")).astype(np.float32)
    return c


def up4(c):
    return np.kron(c, np.ones((4, 4, 1), np.float32))


def e_valid(a, band=4):
    """достоверные пиксели основы: альфа >= 200 и не ближе band px к внешнему фону (кайма подложки R-089)"""
    al = a[..., 3]
    lab, n = ndi.label(al < 128)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bg = np.isin(lab, border[border > 0])
    d = ndi.distance_transform_edt(~bg)
    return (al >= 200) & (d > band)


def fill_invalid(a, ok):
    rgb = np.clip(a[..., :3], 0, 255).astype(np.uint8)
    f = cv2.inpaint(rgb, (~ok).astype(np.uint8) * 255, 6, cv2.INPAINT_TELEA)
    o = a.copy()
    o[..., :3] = f
    return o


def build_base(sigma=7.0):
    a = load(SRC_A)
    ok = e_valid(a)
    af = fill_invalid(a, ok)
    lp_e = smooth_frame(lum(af)[..., None], ok.astype(np.float32), sigma)[..., 0]
    En = af[..., :3] / np.maximum(lp_e, 4.0)[..., None]
    return dict(a=a, ok=ok, En=En, tone=lp_e)


def assemble(base, mode, pick=0, info=None):
    """периодический кадр RGB без тона (H,W,3)"""
    En, ok = base["En"], base["ok"]
    out = np.zeros_like(En)
    Et = np.zeros((4096, 3), np.float32)
    bad = np.ones(4096, bool)
    Et[CIDX[DIAMOND]] = En[DIAMOND]
    bad[CIDX[DIAMOND]] = ~ok[DIAMOND]
    if mode == "blend":
        P = blend_two(Et)
        d = "кросс-фейд"
        cost = 0.0
    else:
        P, bd, d, cost = two_pass(Et, bad, pick)
    m = REG == 0
    out[m] = P[CIDX[m]]
    fcost = 0.0
    for side in (1, 2):
        Un, okU = to_U(En, side)
        Uok, _ = to_U(ok[..., None].astype(np.float32), side)
        bU = (Uok[..., 0] < 0.5) | ~okU
        if mode == "blend":
            Up = blend_face(Un)
        else:
            Up, lab, c = cut_face(Un, bU, 32 if pick == 0 else 24 + 16 * (side - 1))
            fcost += c
        put_U(out, Up, side)
    if info is not None:
        info.update(desc=d, top_cost=cost, face_cost=fcost)
    return out


def frame_rgba(base, pn):
    rgb = np.clip(pn * base["tone"][..., None], 0, 255)
    al = np.where(HULL, 255.0, base["a"][..., 3])
    return np.dstack([rgb, al]).astype(np.float32)


# ---------- поле и меры ----------
def field(tiles, gw=6, gh=5, bg=GRAY, pick=None):
    """tiles - RGBA float (h,w,4); pick(gx,gy)->индекс. Возврат: картинка RGBA, карта клеток (id там, где ромб верха)"""
    th, tw = tiles[0].shape[0], tiles[0].shape[1]
    s = tw // 32
    cw = (gw + gh) * 16 * s + tw
    ch = (gw + gh) * 8 * s + th
    ox = gh * 16 * s
    im = Image.new("RGBA", (cw, ch), bg + (255,))
    ident = np.full((ch, cw), -1, np.int32)
    yy, xx = np.mgrid[0:th, 0:tw] + 0.5
    dm = (np.abs(xx - tw / 2) / (tw / 2) + np.abs(yy - 17.5 * s) / (8 * s)) < 1
    for _, gx, gy in sorted(((gx + gy, gx, gy) for gx in range(gw) for gy in range(gh))):
        t = tiles[pick(gx, gy) if pick else 0]
        x0, y0 = ox + (gx - gy) * 16 * s, (gx + gy) * 8 * s
        im.alpha_composite(Image.fromarray(np.clip(t, 0, 255).astype(np.uint8), "RGBA"), (x0, y0))
        ident[y0:y0 + th, x0:x0 + tw][dm] = gx + 100 * gy
    return im, ident


def seam_ratio(im, ident, s=4, cellvar=None, mode=None):
    """перепад яркости на парах соседних пикселей разных клеток (стык) / внутри клетки далеко от стыка (>= 3 s px);
    только ромбы верха. Возврат: (стык, внутри, отношение, контраст полосы +-3 px у стыка / внутри)"""
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    L = a @ LUMW
    gx_, gy_ = np.abs(np.diff(L, axis=1)), np.abs(np.diff(L, axis=0))
    bx = (ident[:, 1:] != ident[:, :-1]) & (ident[:, 1:] >= 0) & (ident[:, :-1] >= 0)
    by = (ident[1:, :] != ident[:-1, :]) & (ident[1:, :] >= 0) & (ident[:-1, :] >= 0)
    bnd = np.zeros(ident.shape, np.uint8)
    bnd[:, 1:][bx] = 1
    bnd[1:, :][by] = 1
    if cellvar is not None:
        vm = np.full(ident.max() + 2, -1, np.int32)
        for k_, v_ in cellvar.items():
            vm[k_] = v_
        same_x = vm[ident[:, 1:]] == vm[ident[:, :-1]]
        same_y = vm[ident[1:, :]] == vm[ident[:-1, :]]
        want = (mode == "same")
        bx = bx & (same_x == want)
        by = by & (same_y == want)
    r = 3 * s
    far = cv2.dilate(bnd, np.ones((2 * r + 1, 2 * r + 1), np.uint8)) == 0
    inx = far[:, 1:] & far[:, :-1] & (ident[:, 1:] >= 0) & (ident[:, 1:] == ident[:, :-1])
    iny = far[1:, :] & far[:-1, :] & (ident[1:, :] >= 0) & (ident[1:, :] == ident[:-1, :])
    gb = np.concatenate([gx_[bx], gy_[by]]).mean()
    gi = np.concatenate([gx_[inx], gy_[iny]]).mean()
    hp = np.abs(L - cv2.GaussianBlur(L, (0, 0), 2.0 * s / 4))
    band = cv2.dilate(bnd, np.ones((2 * max(1, 3 * s // 4) + 1,) * 2, np.uint8)) > 0
    hb = hp[band & (ident >= 0)].mean()
    hi = hp[far & (ident >= 0)].mean()
    return float(gb), float(gi), float(gb / (gi + 1e-3)), float(hb / (hi + 1e-3))


def tint_step(im, ident):
    """скачок цветности (cb+cr) на стыке и внутри клетки"""
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    y = a @ LUMW
    c = np.abs(np.diff(0.564 * (a[..., 2] - y), axis=1)), np.abs(np.diff(0.713 * (a[..., 0] - y), axis=1))
    r = np.abs(np.diff(0.564 * (a[..., 2] - y), axis=0)), np.abs(np.diff(0.713 * (a[..., 0] - y), axis=0))
    cx, cy = c[0] + c[1], r[0] + r[1]
    bx = (ident[:, 1:] != ident[:, :-1]) & (ident[:, 1:] >= 0) & (ident[:, :-1] >= 0)
    by = (ident[1:, :] != ident[:-1, :]) & (ident[1:, :] >= 0) & (ident[:-1, :] >= 0)
    ix = (ident[:, 1:] == ident[:, :-1]) & (ident[:, 1:] >= 0)
    iy = (ident[1:, :] == ident[:-1, :]) & (ident[1:, :] >= 0)
    return float(np.concatenate([cx[bx], cy[by]]).mean()), float(np.concatenate([cx[ix], cy[iy]]).mean())


def periodic_error(tile):
    """проверка периодичности: пиксели верха (и колосья над кромкой), у которых p + (64,32) тоже верх кадра"""
    t = tile[..., :3]
    m = (REG == 0)
    m2 = np.zeros_like(m)
    m2[:-32, :-64] = m[32:, 64:]
    both = m & m2
    d = np.abs(t[:-32, :-64] - t[32:, 64:]).max(-1)
    return float(d[both[:-32, :-64]].max()), int(both.sum())


# ---------- перекраски ----------
def ycc(a):
    y = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    return y, 0.564 * (a[..., 2] - y), 0.713 * (a[..., 0] - y)


def rgb_of(y, cb, cr):
    r = y + 1.403 * cr
    b = y + 1.773 * cb
    g = (y - 0.299 * r - 0.114 * b) / 0.587
    return np.stack([r, g, b], -1)


def recolor(frame, cb_up, ct_up, sigma=2.0):
    """перенос цвета классики как obj_derive.transfer, поля - периодическим размытием; яркость основы сперва приводится
    к средней яркости классики (t302_install.level)"""
    m = ((cb_up[..., 3] > 0) & (ct_up[..., 3] > 0)).astype(np.float32)
    yb, cbb, crb = ycc(cb_up)
    yt, cbt, crt = ycc(ct_up)
    st = lambda v: smooth_frame(v[..., None], m, sigma)[..., 0]
    yb, cbb, crb, yt, cbt, crt = (st(v) for v in (yb, cbb, crb, yt, cbt, crt))
    k = (yt + 2.0) / (yb + 2.0)
    dcb, dcr = cbt - cbb, crt - crb
    a = frame.copy()
    w0 = a[..., 3] > 200
    a[..., :3] = np.clip(a[..., :3] * (lum(cb_up)[cb_up[..., 3] > 200].mean() / lum(a)[w0].mean()), 0, 255)
    y, cb, cr = ycc(a)
    wgt = np.clip((np.hypot(dcb, dcr) - 8.0) / 16.0, 0.0, 1.0)
    o = a.copy()
    o[..., :3] = np.clip(rgb_of(y * k, (1 - wgt) * (cb + dcb) + wgt * cbt, (1 - wgt) * (cr + dcr) + wgt * crt), 0, 255)
    return o


# ---------- вывод ----------
def to_img(f):
    return Image.fromarray(np.clip(f, 0, 255).astype(np.uint8), "RGBA")


def lab_(im, x, y, t, col=(255, 230, 80)):
    d = ImageDraw.Draw(im)
    d.rectangle((x - 2, y - 1, x + 7 * len(t) + 2, y + 12), fill=(20, 20, 24))
    d.text((x, y), t, fill=col)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="через запятую: cut,blend,cut2")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    base = build_base()
    print("достоверных пикселей ромба: %.0f%%" % (100 * base["ok"][DIAMOND].mean()))
    cands, info = {}, {}
    for name, mode, pick in (("cut", "cut", 0), ("blend", "blend", 0), ("cut2", "cut", 1)):
        if args.only and name not in args.only.split(","):
            continue
        inf = {}
        cands[name] = frame_rgba(base, assemble(base, mode, pick, inf))
        info[name] = inf
        to_img(cands[name]).save(os.path.join(OUT, "CULTIVAT_4_%s.png" % name))
        print(name, inf, "периодичность (макс. разница пикселей p и p+(64,32)):", periodic_error(cands[name]))
    cl4 = classic_of("CULTIVAT")
    cu = up4(cl4)
    cur = load(SRC_C)
    rows = []
    for name, tile in [("classic", cl4), ("now C", cur), ("a (pre-C)", base["a"])] + list(cands.items()):
        im, ident = field([tile])
        gb, gi, r, hb = seam_ratio(im, ident, tile.shape[1] // 32)
        rows.append(dict(name=name, seam=gb, inside=gi, ratio=r, band=hb))
        print("%-10s стык %.2f внутри %.2f отношение %.2f контраст-полосы %.2f" % (name, gb, gi, r, hb))
    # перекраски
    recs = {}
    for cn, tile in cands.items():
        for sname in ("CULTIVAT_PP", "CULTIVAT_UBER"):
            recs[(cn, sname)] = recolor(tile, cl4_up(cl4), up4(classic_of(sname)))
            to_img(recs[(cn, sname)]).save(os.path.join(OUT, "%s_4_%s.png" % (sname, cn)))
    json.dump(dict(rows=rows, info={k: {a: b for a, b in v.items() if not isinstance(b, np.ndarray)} for k, v in info.items()}),
              open(os.path.join(OUT, "seam_metrics.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rec_rows = sheets(base, cands, rows, recs)
    json.dump(dict(rows=rows, recolor=rec_rows, info={k: {a: b for a, b in v.items() if not isinstance(b, np.ndarray)} for k, v in info.items()}),
              open(os.path.join(OUT, 'seam_metrics.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=float)


def cl4_up(c):
    return up4(c)

def mixed_pick(seed=7, n=3):
    rng = np.random.RandomState(seed)
    g = rng.randint(0, n, size=(6, 5))
    return lambda gx, gy: int(g[gx, gy])


def stage_tile(sname):
    p = os.path.join(ROOT, "art", "_review", "tickets_2026-10-26", "after", "TERRAIN", sname + ".PCK", "4.png")
    return load(p) if os.path.exists(p) else None


def sheets(base, cands, rows, recs):
    cl = {s: classic_of(s) for s in ("CULTIVAT", "CULTIVAT_PP", "CULTIVAT_UBER")}
    now = {"CULTIVAT": load(SRC_C), "CULTIVAT_PP": stage_tile("CULTIVAT_PP"), "CULTIVAT_UBER": stage_tile("CULTIVAT_UBER")}
    big = lambda im: im.resize((im.width * 4, im.height * 4), Image.NEAREST)
    f = {}
    f["classic"] = big(field([cl["CULTIVAT"]])[0])
    f["now C"] = field([now["CULTIVAT"]])[0]
    for n, t in cands.items():
        f[n] = field([t])[0]
    fw, fh = f["classic"].size
    names = ["classic", "now C"] + list(cands)
    notes = {"classic": "classic (x4 nearest)", "now C": "now: edge C (in mod, d214fb930)",
             "cut": "NEW cut (min-cut, 2 passes)", "blend": "NEW blend (cross-fade)", "cut2": "NEW cut2 (other shift)"}
    # лист 1: поля 6x5 и крупно стык
    cw, chh = 3 * fw + 16, 2 * (fh + 18) + 2 * (360 + 18) + 4 * 14 + 40
    sh = Image.new("RGB", (cw, chh), (14, 14, 18))
    d = ImageDraw.Draw(sh)
    d.text((8, 4), "XP302 seam: 6x5 identical cells, k=4, gray background, 1:1; then joint close-up x3 (crop 200x120 of the same field)",
           fill=(150, 200, 255))
    y = 22
    for i, n in enumerate(names):
        x, yy = 4 + (i % 3) * (fw + 4), y + (i // 3) * (fh + 18)
        lab_(sh, x, yy, notes[n])
        sh.paste(f[n].convert("RGB"), (x, yy + 14))
    # таблица мер в свободной клетке
    tx, ty = 4 + 2 * (fw + 4) + (fw if len(names) <= 5 else 0) * 0, y + (fh + 18)
    if len(names) <= 5:
        tx, ty = 4 + 2 * (fw + 4), y + (fh + 18) + 14
        d.text((tx, ty), "metrics (luminance gradient joint / inside the cell, 6x5 field):", fill=(255, 230, 80))
        for j, r in enumerate(rows):
            d.text((tx, ty + 22 + j * 18), "%-10s joint %5.2f  inside %5.2f  ratio %.2f  band-contrast %.2f" %
                   (r["name"], r["seam"], r["inside"], r["ratio"], r["band"]), fill=(230, 230, 230))
    y2 = y + 2 * (fh + 18) + 4
    for i, n in enumerate(names):
        im = f[n].convert("RGB").crop((300, 150, 500, 270)) if n != "classic" else f[n].convert("RGB").crop((300, 150, 500, 270))
        im = im.resize((600, 360), Image.NEAREST)
        x, yy = 4 + (i % 3) * 608, y2 + (i // 3) * (360 + 18)
        lab_(sh, x, yy, notes[n] + " - joint x3")
        sh.paste(im, (x, yy + 14))
    p = os.path.join(OUT, "sheet_seam.png")
    sh.crop((0, 0, cw, y2 + 2 * (360 + 18) + 4)).save(p)
    print("лист:", p)
    # лист 2: перекраски PP / UBER и смешанное поле
    rr = []
    out = {}
    def put(title, tiles, pick, key):
        im, ident = field(tiles, pick=pick)
        gb, gi, r, hb = seam_ratio(im, ident, tiles[0].shape[1] // 32)
        ts_b, ts_i = tint_step(im, ident)
        if pick is not None:
            cv = {gx + 100 * gy: pick(gx, gy) for gx in range(6) for gy in range(5)}
            s_ = tiles[0].shape[1] // 32
            same = seam_ratio(im, ident, s_, cv, "same")
            diff = seam_ratio(im, ident, s_, cv, "diff")
            print("   стык одинаковых клеток: %.2f / внутри %.2f = %.2f;  стык разных вариантов: %.2f = %.2f" % (same[0], same[1], same[2], diff[0], diff[2]))
            out[key + "_same"] = dict(seam=same[0], inside=same[1], ratio=same[2], band=same[3])
            out[key + "_diff"] = dict(seam=diff[0], inside=diff[1], ratio=diff[2], band=diff[3])
        out[key] = dict(seam=gb, inside=gi, ratio=r, band=hb, tint_joint=ts_b, tint_inside=ts_i)
        print("%-28s стык %.2f внутри %.2f отн. %.2f полоса %.2f | цветность стык %.2f внутри %.2f" % (title, gb, gi, r, hb, ts_b, ts_i))
        return title, im
    cells = []
    pk = mixed_pick()
    cells.append(put("classic mixed base/PP/UBER (x4)", [cl["CULTIVAT"], cl["CULTIVAT_PP"], cl["CULTIVAT_UBER"]], pk, "classic_mixed"))
    cells[-1] = (cells[-1][0], big(cells[-1][1]))
    cells.append(put("now C mixed", [now["CULTIVAT"], now["CULTIVAT_PP"], now["CULTIVAT_UBER"]], pk, "C_mixed"))
    for n in cands:
        cells.append(put("NEW %s mixed" % n, [cands[n], recs[(n, "CULTIVAT_PP")], recs[(n, "CULTIVAT_UBER")]], pk, n + "_mixed"))
    for sname, tag in (("CULTIVAT_PP", "PP"), ("CULTIVAT_UBER", "UBER")):
        cells.append(put("now C pure %s" % tag, [now[sname]], None, "C_" + tag))
        for n in cands:
            cells.append(put("NEW %s pure %s" % (n, tag), [recs[(n, sname)]], None, "%s_%s" % (n, tag)))
    cols = 3
    nrow = (len(cells) + cols - 1) // cols
    sh2 = Image.new("RGB", (cols * (fw + 4) + 4, nrow * (fh + 18) + 24), (14, 14, 18))
    ImageDraw.Draw(sh2).text((8, 4), "XP302 seam: recolours PP and UBER (colour transfer from classic, periodic fields), mixed field = random base/PP/UBER cells",
                             fill=(150, 200, 255))
    for i, (t, im) in enumerate(cells):
        x, yy = 4 + (i % cols) * (fw + 4), 22 + (i // cols) * (fh + 18)
        lab_(sh2, x, yy, t)
        sh2.paste(im.convert("RGB"), (x, yy + 14))
    p2 = os.path.join(OUT, "sheet_seam_recolor.png")
    sh2.save(p2)
    print("лист:", p2)
    return out



if __name__ == "__main__":
    main()
