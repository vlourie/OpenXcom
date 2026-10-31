#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000253: рельсы и шпалы PORTROADS 73/74 (+ побайтные копии METROBITS 2/3) - вариант 2, процедурно.

Что не так (по листам t253_row.png, t253_frames.png и цепочке кадров на карте):
  * классика: рельс - прямая полоса, одна на клетку; рельс идёт вдоль оси e = y - x/2 экрана (вниз-влево, наклон
    -1/2), поперёк оси w = y + x/2. Рельс 73 лежит на северо-западном краю ромба, рельс 74 - в соседней клетке
    (+16,+8), колея 20.5 пикселя базы по w. Шпала - одна на клетку, брус поперёк колеи: он проходит под рельсом 73,
    лежит в клетке 73 и продолжается в клетке 74;
  * HD сейчас: рельс у каждого кадра свой (наклон -0.509 против -0.480, у 74 -0.451), на стыке клеток он
    ломается и расходится; шпалы - пучки досок со ступенчатым краем, у 73 и 74 разные, на стыке узор рвётся.
  Прежний процедурный вариант (по маске классики, рельс и шпалы) Vitali отклонил: «рельсы неровные, в местах
  стыка расходятся».

Что делает скрипт (всё считается один раз для всех кадров, по общим числам):
  1. Геометрия - из маски классики (подгонка по пикселям): рельс - полоса w в [c, c+T], c = 31.5 (73) и 36.0 (74)
     (в системе кадра), T = 4.25, вдоль оси e от E_NE = 10.5 до E_SW = 33.0 (классика заходит на соседа так же).
     Одна и та же прямая во всех клетках цепочки: сосед сдвинут на (16,-8), у него та же прямая, поэтому рельс
     выходит на край ромба в той же точке и под тем же углом, что входит в соседний кадр. Шпала - прямоугольник
     e в [18.6, 26.3], w в [30, 62.25] (w - в системе кадра 73; кадр 74 сдвинут на w + 16), одна на клетку.
  2. Цвет и фактура - с текущего HD: цвет и разброс дерева, профиль рельса (светлая головка, тёмная шейка,
     светлая подошва), щебень кадра (в закрашенных местах - щебень из значений яркости и цвета этого же кадра).
  3. Стык: рельс и шпала считаются от ОБЩИХ координат (e, w), край сглажен аналитически, без лесенки. Куски
     соседей перекрываются (рельс - на 6.5 px базы, шпала 73/74 - на 4), в перекрытии рисуется одно и то же
     (рисунок зависит только от общих координат), поэтому шва нет.
  4. Старые рельс и шпалы HD закрашиваются щебнем кадра, новые кладутся поверх.
Семья: PORTROADS 73 -> METROBITS 2, PORTROADS 74 -> METROBITS 3 (побайтные копии классики и пака, ticket_family).
Кадры PORTROADS 28-33 и их перекраски - не рельсы, а балки конвейерной галереи (портовые карты): здесь не правятся.
Тележки 75-79 - другой исполнитель, не трогаются.

    py -3.13 tools/hdart/t253_rails.py                  # кадры в art/tickets/t253/out/TERRAIN/...
    py -3.13 tools/hdart/t253_rails.py --sheet          # лист и замеры стыков в art/_review/tickets_2026-10-23/
    py -3.13 tools/hdart/t253_rails.py --install --yes  # + в мод hd через манифест (по слову Vitali, под очередью правок)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.special import ndtr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts            # noqa: E402

K = 4
OUT = ROOT / "art" / "tickets" / "t253" / "out"
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-23"
G = 1.118034                          # |grad(e)| = |grad(w)|: расстояние до прямой e = const в пикселях = (e - e0) / G

# --- геометрия, общая для всех кадров (базовые пиксели; e = y - x/2, w = y + x/2 в системе кадра) -------------
RAIL_C = {73: 31.5, 74: 36.0}        # верхняя кромка рельса: w = c
RAIL_T = 4.25                         # толщина по вертикали
E_NE, E_SW = 10.5, 33.0               # концы полосы вдоль оси
W_SHIFT = {73: 0.0, 74: 16.0}         # сдвиг w кадра в системе кадра 73 (74 - сосед на (+16,+8))
SLP_E = (18.6, 26.3)                  # шпала по e (силуэт классики, верх + боковая грань)
SLP_W = (30.0, 62.25)                 # шпала по w в системе кадра 73
SLP_CUT = 47.5                        # граница клеток 73|74 по w
SLP_OV = 2.0                          # перекрытие кусков шпалы по w
SLP_H = 1.2                           # высота шпалы: боковые грани
DIA = (16.0, 32.5, 16.0, 8.0)         # ромб: центр и полуоси (базовые пиксели)

# профиль рельса поперёк, s - HD-пиксели от верхней кромки (по вертикали); цвета с текущего HD (головка 203,217,230;
# грань 185,197,204; шейка 39..52; подошва 171,186,208)
PROFILE = [(0.0, (232, 240, 247)), (1.4, (214, 226, 238)), (5.2, (168, 183, 200)), (6.8, (100, 109, 124)),
           (8.2, (58, 64, 76)), (10.8, (62, 69, 82)), (12.4, (150, 166, 188)), (14.6, (176, 191, 211)),
           (16.0, (92, 100, 113)), (17.0, (44, 48, 57))]
WOOD = np.array([120.0, 82.0, 50.0])  # медиана дерева HD
SC = None


def scene():
    global SC
    if SC is None:
        SC = ts.Scene()
    return SC


def hd_frame(f):
    return np.asarray(scene().hd("PORTROADS", f)).astype(np.float32)


def grid(h=160, w=128):
    X, Y = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    return X, Y


def cov_range(v, a, b):
    """Покрытие отрезка [a, b] вдоль координаты v (базовые), край сглажен на пиксель HD."""
    d = np.minimum(v - a, b - v) * K / G
    return np.clip(0.5 + d, 0.0, 1.0)


def noise_field(seed, shape, sig_e, sig_w):
    """Шум, вытянутый вдоль w (вдоль шпалы): общий массив в (e, w), по которому читают оба кадра."""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(shape)
    n = ndi.gaussian_filter(n, (sig_e, sig_w), mode="wrap")
    return n / n.std()


# --- общие текстуры шпалы: индекс - HD-координаты (e*K, w*K) в системе кадра 73, со сдвигом на начало -------------
E0_T = int((SLP_E[0] - 2) * K)
W0_T = int((SLP_W[0] - 2) * K)
TEX_H = int((SLP_E[1] - SLP_E[0] + 6) * K)
TEX_W = int((SLP_W[1] - SLP_W[0] + 6) * K)
GRAIN = noise_field(253, (TEX_H, TEX_W), 0.8, 14.0)
SPECK = noise_field(254, (TEX_H, TEX_W), 0.7, 1.2)
PLANK = noise_field(255, (TEX_H, TEX_W), 2.5, 40.0)


def sample_tex(tex, e_b, w_b):
    ie = e_b * K - E0_T
    iw = w_b * K - W0_T
    return ndi.map_coordinates(tex, [ie, iw], order=1, mode="nearest")


def gravel_pool(a, bad):
    """Яркости и цвета щебня кадра (не дерево, не рельс, внутри ромба), по возрастанию яркости."""
    X, Y = grid(a.shape[0], a.shape[1])
    xb, yb = X / K, Y / K
    inside = np.abs(xb - DIA[0]) / DIA[2] + np.abs(yb - DIA[1]) / DIA[3] <= 0.97
    ok = inside & (a[..., 3] > 250) & ~bad
    px = a[ok][:, :3]
    L = px @ np.array([0.299, 0.587, 0.114], np.float32)
    return px[np.argsort(L)]


def fill_gravel(a, f):
    """Старые рельс и шпалы HD закрашены щебнем: значения из пула кадра по рангу шума (зерно щебня кадра)."""
    h, w = a.shape[:2]
    X, Y = grid(h, w)
    xb, yb = X / K, Y / K
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    alpha = a[..., 3]
    brown = (r > g) & (g > b) & (r - b > 12) & (alpha > 0)
    wd = Y + X / 2
    c = RAIL_C[f] * K
    band = (wd > c - 12) & (wd < c + RAIL_T * K + 12) & (alpha > 0)
    bad = ndi.binary_dilation(brown, iterations=3) | band
    inside = np.abs(xb - DIA[0]) / DIA[2] + np.abs(yb - DIA[1]) / DIA[3] <= 1.0 + 1.2 / 8
    pool = gravel_pool(a, bad)
    rng = np.random.default_rng(1000 + f)
    nz = ndi.gaussian_filter(rng.standard_normal((h, w)), 1.0) * 0.75 + ndi.gaussian_filter(rng.standard_normal((h, w)), 2.4) * 0.65
    nz = (nz - nz.mean()) / nz.std()
    rank = np.clip((ndtr(nz) * (len(pool) - 1)).astype(int), 0, len(pool) - 1)
    synth = pool[rank]
    out = a.copy()
    rep = bad & inside
    soft = ndi.gaussian_filter(rep.astype(np.float32), 0.8)
    soft = np.where(rep, np.maximum(soft, 0.85), soft * (alpha > 0))
    out[..., :3] = a[..., :3] * (1 - soft[..., None]) + synth * soft[..., None]
    out[..., 3] = np.where(rep, 255.0, alpha)
    kill = bad & ~inside
    out[..., 3] = np.where(kill, 0.0, out[..., 3])
    return out


def over(dst, rgb, cov):
    """Положить rgb с покрытием cov на RGBA dst (прямая альфа, 0..255)."""
    da = dst[..., 3:4] / 255.0
    ca = cov[..., None]
    oa = ca + da * (1 - ca)
    num = rgb * ca + dst[..., :3] * da * (1 - ca)
    dst[..., :3] = np.where(oa > 1e-6, num / np.maximum(oa, 1e-6), 0.0)
    dst[..., 3:4] = oa * 255.0
    return dst


def draw_sleeper(out, f):
    h, w = out.shape[:2]
    X, Y = grid(h, w)
    e_b = (Y - X / 2) / K
    w_b = (Y + X / 2) / K + W_SHIFT[f]
    e0, e1 = SLP_E
    w0, w1 = SLP_W
    if f == 73:
        wa, wb_ = w0 - 1, SLP_CUT + SLP_OV
    else:
        wa, wb_ = SLP_CUT - SLP_OV, w1 + 1
    cov = cov_range(e_b, e0, e1) * cov_range(w_b, w0, w1)
    # кусок режется жёстко внутри перекрытия: там оба кадра рисуют одно и то же
    cov = cov * ((w_b >= wa) & (w_b <= wb_))
    top = (e_b <= e1 - SLP_H) & (w_b <= w1 - SLP_H)
    g = sample_tex(GRAIN, e_b, w_b)
    sp = sample_tex(SPECK, e_b, w_b)
    pl = sample_tex(PLANK, e_b, w_b)
    m = 1.0 + 0.13 * g + 0.06 * sp + 0.05 * pl
    col = WOOD[None, None, :] * m[..., None]
    sw = (e_b > e1 - SLP_H)                       # юго-западная боковая грань: темнее
    se = (w_b > w1 - SLP_H) & ~sw                 # юго-восточный торец: чуть светлее
    col = np.where(sw[..., None], col * 0.52, col)
    col = np.where(se[..., None], col * 0.66, col)
    edge = (top & ((e_b - e0) * K / G < 1.3)) | (top & ((w_b - w0) * K / G < 1.3))
    col = np.where(edge[..., None], np.minimum(col * 1.22, 255), col)
    return over(out, np.clip(col, 0, 255), cov)


def rail_color(s):
    xs = [p[0] for p in PROFILE]
    cs = np.array([p[1] for p in PROFILE], np.float32)
    sc_ = np.clip(s, 0, xs[-1])
    return np.stack([np.interp(sc_, xs, cs[:, i]) for i in range(3)], -1)


def draw_rail(out, f):
    h, w = out.shape[:2]
    X, Y = grid(h, w)
    e_b = (Y - X / 2) / K
    wd = Y + X / 2
    s = wd - RAIL_C[f] * K
    T = RAIL_T * K
    cov_s = np.clip(0.5 + np.minimum(s, T - s) / G, 0, 1)
    cov_e = cov_range(e_b, E_NE, E_SW)
    cov = cov_s * cov_e
    col = rail_color(s)
    # торцевая грань с юго-запада: темнее; её закрывает следующий кадр цепочки
    endf = np.clip((e_b - (E_SW - 1.5)) * K / G + 0.5, 0, 1)
    col = col * (1 - 0.45 * endf[..., None])
    return over(out, col, cov)


def drop_specks(out, min_px=40):
    """Одиночные точки и обрывки вне основного пятна (остатки края старого кадра) убираются."""
    lab, n = ndi.label(out[..., 3] > 8, structure=np.ones((3, 3)))
    if n:
        size = ndi.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
        for i in np.nonzero(size < min_px)[0]:
            out[lab == i + 1, 3] = 0
    return out


def build_frame(f):
    a = hd_frame(f)
    out = fill_gravel(a, f)
    out = draw_sleeper(out, f)
    out = draw_rail(out, f)
    out = drop_specks(out)
    return np.clip(out, 0, 255)


def build_all():
    return {("PORTROADS", f): build_frame(f) for f in (73, 74)}


COPIES = {("PORTROADS", 73): ("METROBITS", 2), ("PORTROADS", 74): ("METROBITS", 3)}


def save_all(res):
    paths = {}
    for (s, f), p in res.items():
        for (ss, ff) in ((s, f), COPIES[(s, f)]):
            d = OUT / "TERRAIN" / (ss + ".PCK")
            d.mkdir(parents=True, exist_ok=True)
            q = d / ("%d.png" % ff)
            Image.fromarray(np.clip(p, 0, 255).round().astype(np.uint8), "RGBA").save(q)
            paths["TERRAIN/%s.PCK/%d.png" % (ss, ff)] = q
    return paths


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    res = build_all()
    paths = save_all(res)
    print("кадров: %d (с копиями %d) -> %s" % (len(res), len(paths), OUT))
    if a.sheet:
        import t253_sheet
        t253_sheet.make(res)
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(paths, "t253_rails", "t253_rails.py 23.10 рельсы и шпалы по классике, общие стыки",
                         "Vitali (XP-000253); лист art/_review/tickets_2026-10-23/t253_rails_v2.png",
                         "t253: рельсы и шпалы PORTROADS 73/74 и METROBITS 2/3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
