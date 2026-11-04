#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000492 (снежная деревня IDT_SNOWVILLAGE): чёткие процедурные полы по индексам классики, без видеокарты.

Почему нынешние полы мягкие: SNOWBARN:0, SNOWCULTIVAT:0/:4 - ответ диффузионной модели (sdxl_legacy, латент 8x),
сжатый LANCZOS до кадра 128 и подогнанный по тону размытым образцом (probe_floor tone_low): мелкого зерна 1-2 пикселя у
модели нет, а уменьшение и подгонка тона срезают то, что есть. FOREST_SNOW:0 (relief_object) - тот же класс: зерно
расплывчатое и вдвое контрастнее классики. Здесь модели нет: каждый кадр строится из индексов классики (цвет - палитра
Пираток, как есть), зерно получается жёсткой пересборкой индексов, края - выбор класса по max (без размытия цвета).

Стили:
  S1 «округлое зерно» - one-hot классики, бикубика с лёгким искажением координат, выбор класса argmax, 2x суперсэмпл;
  S2 «мелкая крупа» (ВЫБРАН Vitali 04.11 для земли) - зерно вдвое мельче классики (2x2 HD): каждая клетка 2x2 берёт класс
     родителя либо соседа, затем выбор по ближайшему с искажением координат.
  B1 «чистая классика» (кадры B) - Scale2x (EPX) дважды: рисунок классики пиксель в пиксель, одиночные точки целы, углы 45
     скошены, без шума и размытия;
  B2 «круглое зерно без искажения» (кадры B) - бикубика one-hot + argmax, суперсэмпл 3x, искажения нет.
Кадры с рисунком (плитки :4, грядка :1): линии рисунка не гнём.
Варианты земли v1-v3 (R-039): родительская карта - выборка по гистограмме классики (классика - белый шум); v0 - карта
классики как есть.
Кромка ромба: точный ромб x4 (rim_alpha.diamond), верхние рёбра - альфа 1 до d=1, спад до 0 к d=1.03 (R-291); нижние
рёбра (y >= 128) - до d=1+OVER_LOW: соседи floors_cut_safe держат у верхней кромки пустую полосу под выступ ступеней
классики, а он доходит до d=1.1016, меньше - в стыке тёмный пунктир (R-599). Остаток: кадр 128 px обрезает выступ у
боковых вершин и у низа - то же, что у самой классики (её нижний ряд 4 px), см. report.md тикета.

    py -3.13 tools\hdart\t492_build.py cand     # кандидаты 04.11 -> art/tickets/t492/cand/S1|S2/<НАБОР>/<кадр>[.vN].png
    py -3.13 tools\hdart\t492_build.py final    # семья земли S2 -> art/tickets/t492/final/<НАБОР>/<кадр>[.vN].png
    py -3.13 tools\hdart\t492_build.py b        # кадры B -> art/tickets/t492/candB/B1|B2/<НАБОР>/<кадр>[.vN].png
Видеокарту не трогает, в мод ничего не ставит.
"""
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
os.chdir(ROOT)
import rim_alpha as ra      # noqa: E402
import water_build as wb    # noqa: E402

CAND = ROOT / "art" / "tickets" / "t492" / "cand"
FINAL = ROOT / "art" / "tickets" / "t492" / "final"
CAND_B = ROOT / "art" / "tickets" / "t492" / "candB"
K = 4
W, H = 32 * K, 40 * K
OVER = 0.03
OVER_LOW = 0.132

# семья IDT_SNOWBARN:0 (ticket_family 04.11): классика побайтно та же, кроме ICEKING_VILLAGE:61 (1 пиксель) - по своим индексам
FAMILY = ([("IDT_SNOWBARN", 0)] + [("FORESTSWAMP_SNOW", f) for f in [4, 22] + list(range(111, 123)) + [137, 138, 139]]
          + [("FOREST_SNOW", 0), ("ICEKING_VILLAGE", 61)])
# кадр: (набор, кадр, число вариантов земли)
JOBS = [("IDT_SNOWBARN", 0, 3), ("IDT_SNOWCULTIVAT", 0, 3), ("IDT_SNOWCULTIVAT", 4, 0), ("IDT_SNOWCULTIVAT", 1, 0)]
STYLE = {
    "S1": dict(warp=1.1, wsig=5.0, jit=2.0, ss=2),
    "S2": dict(warp=1.5, wsig=4.0, jit=2.5, ss=1, dither=0.38),
    "B2": dict(warp=0.0, wsig=6.0, jit=0.0, ss=3),
}
# кадры с рисунком: линии рисунка не гнём
STRUCT = {
    "S1": dict(warp=0.35, wsig=6.0, jit=1.2, ss=3),
    "S2": dict(warp=0.8, wsig=5.0, jit=2.0, ss=2),
    "B2": dict(warp=0.0, wsig=6.0, jit=0.0, ss=3),
}
_PAL = None


def palette():
    global _PAL
    if _PAL is None:
        _PAL = wb.palette()
    return _PAL


def diamond_alpha():
    d, _, _ = ra.diamond(K)
    Y = np.arange(H)[:, None] * np.ones((1, W))
    t = np.where(Y >= 32 * K, OVER_LOW, OVER)
    return np.clip((1.0 + t - d) / OVER, 0, 1).astype(np.float32)


def fill_parent(P):
    """Пустые клетки классики (индекс 0) - ближайшим занятым: цвет для кромки и перехлёста."""
    m = P > 0
    _, ind = ndimage.distance_transform_edt(~m, return_indices=True)
    return P[ind[0], ind[1]]


def synth_parent(P, rng):
    """Новая карта: выборка по гистограмме классики (классика - белый шум)."""
    vals = P[P > 0]
    return rng.choice(vals, size=P.shape).astype(P.dtype)


def noise(shape, sig, rng):
    n = ndimage.gaussian_filter(rng.standard_normal(shape).astype(np.float32), sig)
    return n / (n.std() + 1e-6)


def epx2(P):
    """Scale2x (EPX) по массиву индексов."""
    h, w = P.shape
    Q = np.pad(P, 1, mode="edge")
    A, B = Q[:-2, 1:-1], Q[1:-1, 2:]
    C, D = Q[1:-1, :-2], Q[2:, 1:-1]
    o = np.empty((h * 2, w * 2), P.dtype)
    o[0::2, 0::2] = np.where((C == A) & (C != D) & (A != B), A, P)
    o[0::2, 1::2] = np.where((A == B) & (A != C) & (B != D), B, P)
    o[1::2, 0::2] = np.where((D == C) & (D != B) & (C != A), C, P)
    o[1::2, 1::2] = np.where((B == D) & (B != A) & (D != C), D, P)
    return o


def render_epx(P):
    idx = epx2(epx2(fill_parent(P)))
    return palette()[:, :3].astype(np.float32)[idx]


def render(P, style, seed, ground=True):
    cfg = STYLE[style] if ground else STRUCT[style]
    rng = np.random.default_rng(seed)
    pal = palette()[:, :3].astype(np.float32)
    P = fill_parent(P)
    cls = np.unique(P)
    ss = cfg["ss"]
    hh, ww = H * ss, W * ss
    Y, X = np.mgrid[0:hh, 0:ww].astype(np.float32)
    wx = noise((hh, ww), cfg["wsig"] * ss, rng) * cfg["warp"] * ss
    wy = noise((hh, ww), cfg["wsig"] * ss, rng) * cfg["warp"] * ss
    if cfg.get("dither"):
        # зерно вдвое мельче: часть клеток 2x2 берёт класс случайного соседа родителя
        F = np.kron(P, np.ones((2, 2), P.dtype))
        dy = rng.integers(-1, 2, F.shape)
        dx = rng.integers(-1, 2, F.shape)
        take = rng.random(F.shape) < cfg["dither"]
        yy = np.clip(np.arange(F.shape[0])[:, None] + dy * 2, 0, F.shape[0] - 1)
        xx = np.clip(np.arange(F.shape[1])[None, :] + dx * 2, 0, F.shape[1] - 1)
        F = np.where(take, F[yy, xx], F)
        mx = ((X + wx + 0.5) / (K / 2.0) - 0.5).astype(np.float32)
        my = ((Y + wy + 0.5) / (K / 2.0) - 0.5).astype(np.float32)
        idx = cv2.remap(F.astype(np.float32), mx, my, cv2.INTER_NEAREST, borderMode=cv2.BORDER_REPLICATE)
        idx = np.rint(idx).astype(np.int32)
    else:
        mx = ((X + wx + 0.5) / (K * ss) - 0.5).astype(np.float32)
        my = ((Y + wy + 0.5) / (K * ss) - 0.5).astype(np.float32)
        best = np.full((hh, ww), -1e9, np.float32)
        idx = np.zeros((hh, ww), np.int32)
        for c in cls:
            oh = (P == c).astype(np.float32)
            r = cv2.remap(oh, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            u = r > best
            best[u] = r[u]
            idx[u] = c
    rgb = pal[idx]
    if ss > 1:
        rgb = cv2.resize(rgb, (W, H), interpolation=cv2.INTER_AREA)
    if cfg["jit"]:
        j = noise((H, W), 0.55, rng) * cfg["jit"]
        rgb = rgb + j[..., None]
    return np.clip(rgb, 0, 255)


def build_one(s, f, style, seed, variant, ground=True):
    P = wb.read_set(s)[f].astype(np.int32)
    if ground:
        # единичные пиксели других цветов (рыжая точка белого снега) - в основной цвет: у зерна их быть не должно
        u, n = np.unique(P[P > 0], return_counts=True)
        for c in u[n <= 2]:
            P[P == c] = u[n.argmax()]
    if variant:
        P = synth_parent(P, np.random.default_rng(seed * 101 + variant))
    if style == "B1":
        rgb = np.clip(render_epx(P), 0, 255)
    else:
        rgb = render(P, style, seed * 977 + variant, ground)
    out = np.zeros((H, W, 4), np.uint8)
    out[..., :3] = np.rint(rgb).astype(np.uint8)
    out[..., 3] = np.rint(diamond_alpha() * 255).astype(np.uint8)
    return out


def name_of(f, v):
    return "%d.png" % f if v == 0 else "%d.v%d.png" % (f, v)


def main_cand():
    for style in ("S1", "S2"):
        for s, f, nv in JOBS:
            d = CAND / style / s
            d.mkdir(parents=True, exist_ok=True)
            for v in range(nv + 1):
                a = build_one(s, f, style, 492 + f, v, ground=(nv > 0))
                Image.fromarray(a, "RGBA").save(d / name_of(f, v))
                print(style, s, name_of(f, v))


def main_final():
    """Вся семья IDT_SNOWBARN:0: S2, основа + .v1-.v3 у каждого члена (R-039). Зерно у членов своё (seed по номеру)."""
    for i, (s, f) in enumerate(FAMILY):
        d = FINAL / s
        d.mkdir(parents=True, exist_ok=True)
        seed = 492 if i == 0 else 492 + 1000 + i * 13
        for v in range(4):
            a = build_one(s, f, "S2", seed, v, ground=True)
            Image.fromarray(a, "RGBA").save(d / name_of(f, v))
        print(s, f, "seed", seed)


def main_b():
    """Кадры B: B1 (EPX x2 x2) и B2 (бикубика argmax без искажения). Белый снег :0 - ещё варианты .v1-.v3 (ковёр)."""
    for style in ("B1", "B2"):
        for s, f, nv in JOBS[1:]:
            d = CAND_B / style / s
            d.mkdir(parents=True, exist_ok=True)
            for v in range(nv + 1):
                a = build_one(s, f, style, 492 + f, v, ground=(nv > 0))
                Image.fromarray(a, "RGBA").save(d / name_of(f, v))
                print(style, s, name_of(f, v))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "cand"
    {"cand": main_cand, "final": main_final, "b": main_b}[mode]()
