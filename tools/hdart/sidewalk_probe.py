r"""Проба первого задания пилота карт «тротуар ROADS с бордюрами» (sidewalk_job1): сборка кадров, швы, листы, игра.

Модель здесь не грузится - картинку материала рисует sidewalk_render.py (только через очередь gpuq). Этот скрипт из
её ответа собирает кадры ROADS 0, 0.v1..v3, 1, 2, 7, проверяет их стыки и показывает на настоящем перекрёстке,
поле 9 x 9 и в игровом кадре.

Материал (уточнение Vitali 07.10): «ровное крапчатое серое покрытие тротуара» - материал и тон из классики, мелкая
ненаправленная фактура, износ слабый, без крупных контрастных пятен; без плиточной кладки, кирпичей, борозд и
выпуклости клетки.

Сборка (build):
  1. ответ модели делится по яркости на зерно (высокие частоты) и износ (низкие, размытие --sigma-low);
  2. из четырёх непересекающихся участков ответа - четыре периодические клетки (варианты 0, v1, v2, v3).
     Участок складывается окном cos^2 по модулю периода, и сумма делится на корень суммы квадратов весов:
     разброс зерна одинаков в каждой точке клетки. Без этого деления сложенное зерно в середине клетки полное, а у
     четвертей вдвое слабее - узор с периодом клетки (первая сборка 07.10);
  3. зерно всех вариантов - один разброс (у классики), износ - один множитель до --wear-std, не больше --wear-max;
     тон - средний цвет классики ROADS:0, зерно и износ - только по яркости, оттенок классики;
  4. края клетки у всех вариантов - как у варианта 0: v_j = v0 cos(a) + v_j sin(a), a от 0 у края клетки до pi/2 в
     полосе --edge-band (разброс при этом не меняется). Бордюрные кадры берут тротуар варианта 0. Мера краёв
     (seams.json, раздел листа) сравнивает отдельные кадры с эталоном и о карте НЕ говорит: на игровом кадре
     пробы s7101 видны сетка и полосы, которых она не нашла (FAIL Vitali 07.10). Приёмка - только по дампу игры,
     tools/hdart/crossing_check.py; сборка всего перекрёстка - tools/hdart/crossing_build.py;
  5. полоса бордюра - в развёртке клетки: у 1 по u, у 2 по v, от U0 до края (U0 - доля тротуара в кадре
     классики, 168 из 256 = 0.656); у угла 7 - плечо по u с профилем 1 и плечо по v с профилем 2, стык по
     диагонали u = v: на общем крае 7 с 1 и с 2 профиль один и тот же. Край - прямая, покрытие пикселя x4 по 16
     подточкам. Тон поперёк полосы - профиль классики (рампа 15); материал камня - зерно и износ тротуара сильнее
     (--kerb-grain, --kerb-wear) и выщербины там, где зерно глубже --kerb-pit сигм;
  6. альфа - силуэт классики x4 без сглаживания (у края материала даёт лесенку базы - см. crossing_build.py).
  --synthetic: вместо ответа модели - процедурный шум (проверка сборки без видеокарты); листы помечены.

Лист (sheet): ответ модели 1:1 и клетки вариантов; кадры; перекрёсток STR_ERIDIAN_TERROR_139 и поле 9 x 9 с
вариантами раскладкой движка (ground_field - порт groundFrameFor) - классика | нынешний HD | новое, плюс то же поле
нового только кадром 0 (без смешения вариантов): если плохо, видно, кто испортил - модель (ответ), обработка
(клетки, поле одним кадром) или смешение (поле с вариантами против поля одним кадром). Числа - диагностика.

Игра (game): раскладка модов из соединений на установку, где своя только папка hd/TERRAIN/ROADS.PCK - копия пака
с кадрами пробы (установку не трогает, снимать соединения только rmdir, R-047); три невидимых прогона
game_hidden.py на копии сейва перекрёстка: классика (режим 0), нынешний HD и новое (режим 1, k=4) - кадр экрана
1920x1080, как его видит игрок. Лист game.png.

    py -3.13 tools/hdart/sidewalk_probe.py build --raw census/maps/pilot2/probe_sidewalk/raw_s7101.png
    py -3.13 tools/hdart/sidewalk_probe.py build --synthetic
    py -3.13 tools/hdart/sidewalk_probe.py sheet --tag s7101
    py -3.13 tools/hdart/sidewalk_probe.py game --tag s7101

Кладёт в census/maps/pilot2/probe_sidewalk/<метка>/: ROADS.PCK/<кадр>.png, uv_<j>.png, build.json, seams.json,
sheet.png, game/*.png, game.png. В пак мода НЕ идёт.
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ground_field as gf             # noqa: E402
import pilot2_job_sheet as js         # noqa: E402
import map_screen_check as msc        # noqa: E402

ROOT = js.ROOT
OUT = ROOT / "census" / "maps" / "pilot2" / "probe_sidewalk"
ENC = "utf-8-sig"
K = js.K
TOP = (16, 24)                        # верхняя вершина ромба пола в кадре 32x40
SIDE = 1024                           # ответ модели приводится к этому размеру
CENTRES = ((256, 256), (768, 256), (256, 768), (768, 768))   # участки вариантов 0, v1, v2, v3 - не пересекаются
NAMES = ("0", "0.v1", "0.v2", "0.v3")
KERB_FRAMES = (1, 2, 7)
ALL = NAMES + tuple(str(f) for f in KERB_FRAMES)
LUMA = np.array([0.299, 0.587, 0.114], np.float32)
GAME_MODS = js.INST / "user" / "mods"
SEAM_OK = 1.0                         # шов: у края кадр отходит от непрерывного эталона больше чем на 1 единицу RGB


# ------------------------------------------------------------------ геометрия клетки

def screen_to_uv(sx, sy):
    """Точка кадра 32x40 (k=1) -> оси клетки u, v (ромб пола - квадрат [0, 1)^2)."""
    return (sx - TOP[0]) / 32.0 + (sy - TOP[1]) / 16.0, -(sx - TOP[0]) / 32.0 + (sy - TOP[1]) / 16.0


def uv_to_screen(u, v):
    return TOP[0] + (u - v) * 16.0, TOP[1] + (u + v) * 8.0


def frame_uv(sub=1):
    """u, v центров (sub=1) или sub x sub подточек каждого пикселя кадра x4: массивы (FH, FW[, sub*sub])."""
    o = (np.arange(sub) + 0.5) / sub
    oy, ox = np.meshgrid(o, o, indexing="ij")
    py, px = np.mgrid[0:js.FH, 0:js.FW].astype(np.float32)
    sx = (px[..., None] + ox.ravel()) / K
    sy = (py[..., None] + oy.ravel()) / K
    u, v = screen_to_uv(sx, sy)
    return (u[..., 0], v[..., 0]) if sub == 1 else (u, v)


def kerb_start():
    """U0 по классике: доля тротуара (рампа 0) в ромбе кадров 1 и 2 - полоса бордюра идёт от U0 до края."""
    out = {}
    for f in (1, 2, 7):
        idx, _ = js.gm.classic("ROADS", f)
        fl = idx[24:]
        out[f] = (int(((fl > 0) & (fl < 16)).sum()), int((fl > 0).sum()))
    (w1, t1), (w2, t2), (w7, t7) = out[1], out[2], out[7]
    if (w1, t1) != (w2, t2):
        raise SystemExit("ширина бордюра 1 и 2 у классики разная: %s %s - полосу задавать по кадру" % (out[1], out[2]))
    u0 = w1 / t1
    # у угла тротуар - квадрат U0 x U0: проверка, что полосы правда прямые и одной ширины
    if abs(w7 / t7 - u0 * u0) > 0.03:
        raise SystemExit("угол 7: тротуар %.3f против U0^2 %.3f - полосы не прямые" % (w7 / t7, u0 * u0))
    return u0, out


def kerb_profile(f, u0, nb=24):
    """Средний цвет рампы 15 классики поперёк полосы бордюра кадра f (1 - по u, 2 - по v): nb ячеек на [u0, 1]."""
    i4 = js.classic_idx("ROADS", f)
    u, v = frame_uv(1)
    t = u if f == 1 else v
    m = (i4 >= 240) & (t >= u0) & (t < 1.0)
    b = np.clip(((t[m] - u0) / (1 - u0) * nb).astype(int), 0, nb - 1)
    rgb = js.PAL[i4[m]].astype(np.float64)
    cnt = np.bincount(b, minlength=nb).astype(float)
    prof = np.stack([np.bincount(b, rgb[:, c], minlength=nb) for c in range(3)], -1)
    have = cnt > 0
    if not have.any():
        raise SystemExit("у кадра %d нет пикселей бордюра в полосе" % f)
    prof[have] /= cnt[have, None]
    xs = np.arange(nb)
    for c in range(3):
        prof[:, c] = np.interp(xs, xs[have], prof[have, c])
    k = np.exp(-0.5 * (np.arange(-2, 3) / 1.0) ** 2)
    k /= k.sum()
    pad = np.pad(prof, ((2, 2), (0, 0)), mode="edge")
    return np.stack([np.convolve(pad[:, c], k, mode="valid") for c in range(3)], -1)


def profile_at(prof, t, u0):
    x = (np.clip(t, u0, 1 - 1e-6) - u0) / (1 - u0) * len(prof) - 0.5
    return np.stack([np.interp(x, np.arange(len(prof)), prof[:, ch]) for ch in range(3)], -1)


# ------------------------------------------------------------------ материал

def bilinear_wrap(arr, x, y):
    h, w = arr.shape[:2]
    x = x - 0.5
    y = y - 0.5
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = x - x0, y - y0
    if arr.ndim == 3:
        fx, fy = fx[..., None], fy[..., None]
    xa, xb, ya, yb = x0 % w, (x0 + 1) % w, y0 % h, (y0 + 1) % h
    a = arr[ya, xa] * (1 - fx) + arr[ya, xb] * fx
    b = arr[yb, xa] * (1 - fx) + arr[yb, xb] * fx
    return a * (1 - fy) + b * fy


def fold(field, p, cx, cy):
    """Периодическая клетка p x p из нулевого в среднем поля: окно cos^2 на 2 периода вокруг (cx, cy), сложенное по
    модулю; сумма делится на корень суммы квадратов весов - разброс одинаков в каждой точке клетки."""
    t = np.arange(-p, p) + 0.5
    w = np.cos(math.pi * t / (2 * p)) ** 2
    W = w[:, None] * w[None, :]
    blk = field[cy - p:cy + p, cx - p:cx + p] * W
    W2 = W * W

    def q(a):
        return a[:p, :p] + a[:p, p:] + a[p:, :p] + a[p:, p:]
    out = q(blk) / np.sqrt(q(W2))
    return np.roll(out, (cy % p, cx % p), axis=(0, 1))


def blur_wrap(arr, sigma):
    fy = np.fft.fftfreq(arr.shape[0])[:, None]
    fx = np.fft.fftfreq(arr.shape[1])[None, :]
    g = np.exp(-2 * (math.pi * sigma) ** 2 * (fx * fx + fy * fy))
    return np.real(np.fft.ifft2(np.fft.fft2(arr) * g))


def coherence(lum):
    """Направленность зерна: когерентность тензора структуры, 0 - ненаправленное, 1 - полосы."""
    gx = np.roll(lum, -1, 1) - np.roll(lum, 1, 1)
    gy = np.roll(lum, -1, 0) - np.roll(lum, 1, 0)
    jxx, jyy, jxy = (gx * gx).mean(), (gy * gy).mean(), (gx * gy).mean()
    return float(math.sqrt((jxx - jyy) ** 2 + 4 * jxy * jxy) / (jxx + jyy + 1e-9))


def cell_pattern(field, cells=4):
    """Узор с периодом клетки: разброс среднего по клетке (поле поля cells x cells копий, свёрнутое в одну клетку
    блоками 8x8) против разброса самого поля - у шума без узора около 1/sqrt(64) = 0.125."""
    p = field.shape[0]
    b = p // 8
    blocks = field[:b * 8, :b * 8].reshape(8, b, 8, b).mean((1, 3))
    return float(blocks.std() / (field.std() + 1e-9))


def classic_mean():
    idx, _ = js.gm.classic("ROADS", 0)
    px = js.PAL[idx[idx > 0]].astype(np.float32)
    return px.mean(0), float((px @ LUMA).std())


def synthetic(seed=1):
    """Процедурная замена ответа модели: мелкий крап + слабые пятна. Только для проверки сборки и листа."""
    rng = np.random.default_rng(seed)
    fine = blur_wrap(rng.normal(0, 1, (SIDE, SIDE)), 1.3)
    fine *= 18 / fine.std()
    spots = blur_wrap(rng.normal(0, 1, (SIDE, SIDE)), 40)
    spots *= 6 / spots.std()
    lum = 110 + fine + spots
    return np.clip(np.dstack([lum, lum, lum * 1.03]), 0, 255).astype(np.float32)


def edge_angle(p, band):
    """a(u, v) клетки p x p: 0 на краю клетки, pi/2 дальше band от всех четырёх краёв (гладко)."""
    c = (np.arange(p) + 0.5) / p
    d = np.minimum(np.minimum(c, 1 - c)[:, None], np.minimum(c, 1 - c)[None, :])
    s = np.clip(d / band, 0, 1)
    return math.pi / 2 * s * s * (3 - 2 * s)


def make_cells(tex, a, mean_rgb, grain_std):
    """Клетки вариантов: (rgb[4], зерно[4], износ[4], диагностика)."""
    p = a.period
    lum = tex @ LUMA
    low = blur_wrap(lum, a.sigma_low)
    grain_src, wear_src = lum - low, low - low.mean()
    grains = [fold(grain_src, p, cx, cy) for cx, cy in CENTRES]
    wears = [fold(wear_src, p, cx, cy) for cx, cy in CENTRES]
    w_mean = [float(w.mean()) for w in wears]
    # у каждого варианта средний износ 0: иначе клетка светлее или темнее соседей, а к краю сведена к 0 -
    # на поле облако размером в клетку (s7101: средние -1.12..+1.58)
    wears = [w - m for w, m in zip(wears, w_mean)] if a.wear_center else wears
    g_raw = [float(g.std()) for g in grains]
    w_raw = [float(w.std()) for w in wears]
    g_target = min(float(np.median(g_raw)), grain_std)
    gain = min(1.0, a.wear_std / max(max(w_raw), 1e-6))
    grains = [g * (g_target / max(float(g.std()), 1e-6)) for g in grains]
    wears = [np.clip(w * gain, -a.wear_max, a.wear_max) for w in wears]
    ang = edge_angle(p, a.edge_band)
    co, si = np.cos(ang), np.sin(ang)
    for j in range(1, 4):
        grains[j] = grains[0] * co + grains[j] * si
        wears[j] = wears[0] * co + wears[j] * si
    m_l = float(mean_rgb @ LUMA)
    cells = [np.clip(mean_rgb[None, None, :] * ((m_l + g + w) / m_l)[..., None], 0, 255) for g, w in zip(grains, wears)]
    diag = dict(grain_raw=g_raw, grain_std=g_target, wear_mean_raw=w_mean, wear_center=a.wear_center,
                wear_raw=w_raw, wear_gain=gain,
                wear_std_out=[float(w.std()) for w in wears], coherence=[coherence(g) for g in grains],
                cell_pattern=[cell_pattern(np.tile(c @ LUMA, (4, 4))) for c in cells])
    # контроль меры узора: прежняя складка без деления на корень весов на тех же участках
    t = np.arange(-p, p) + 0.5
    w1 = np.cos(math.pi * t / (2 * p)) ** 2
    W = w1[:, None] * w1[None, :]
    cx, cy = CENTRES[0]
    blk = grain_src[cy - p:cy + p, cx - p:cx + p] * W
    old = blk[:p, :p] + blk[:p, p:] + blk[p:, :p] + blk[p:, p:]
    var_map = np.sqrt(blur_wrap(old * old, 6))
    new_map = np.sqrt(blur_wrap(grains[0] * grains[0], 6))
    diag["grain_std_spread_old_fold"] = float(var_map.std() / var_map.mean())
    diag["grain_std_spread"] = float(new_map.std() / new_map.mean())
    return cells, grains, wears, diag


def build_frames(cells, grain0, wear0, u0, a, mean_rgb):
    """Кадры x4 RGBA: {"0", "0.v1".., "1", "2", "7"} - из клеток материала и полос бордюра."""
    p = cells[0].shape[0]
    u, v = frame_uv(1)
    su, sv = (u % 1.0) * p, (v % 1.0) * p
    out = {}
    alpha0 = np.where(js.classic_idx("ROADS", 0) > 0, 255, 0)
    for nm, c in zip(NAMES, cells):
        out[nm] = np.dstack([np.clip(bilinear_wrap(c, su, sv), 0, 255), alpha0]).astype(np.uint8)
    walk = bilinear_wrap(cells[0], su, sv)
    g = bilinear_wrap(grain0, su, sv)
    w = bilinear_wrap(wear0, su, sv)
    m_l = float(mean_rgb @ LUMA)
    gs = float(grain0.std())
    stone = 1 + a.kerb_grain * g / m_l + a.kerb_wear * w / m_l
    stone = stone * np.where(g < -a.kerb_pit * gs, 0.82, 1.0)          # выщербины - самые глубокие точки зерна
    prof = {1: kerb_profile(1, u0), 2: kerb_profile(2, u0)}
    us, vs = frame_uv(4)
    for f in KERB_FRAMES:
        idx4 = js.classic_idx("ROADS", f)
        if f == 1:
            kc, t_sub = profile_at(prof[1], u, u0), us
        elif f == 2:
            kc, t_sub = profile_at(prof[2], v, u0), vs
        else:
            # угол: плечо по u - профиль 1, плечо по v - профиль 2, стык по диагонали u = v (сглажен на 0.02)
            s = np.clip((u - v) / 0.04 + 0.5, 0, 1)
            kc = profile_at(prof[1], u, u0) * s[..., None] + profile_at(prof[2], v, u0) * (1 - s[..., None])
            t_sub = np.maximum(us, vs)
        kc = kc * stone[..., None]
        cover = (t_sub >= u0).mean(-1)[..., None]
        rgb = walk * (1 - cover) + kc * cover
        out[str(f)] = np.dstack([np.clip(rgb, 0, 255), np.where(idx4 > 0, 255, 0)]).astype(np.uint8)
    return out


# ------------------------------------------------------------------ швы
#
# ДИАГНОСТИКА, не приёмка: мера ниже сравнивает отдельные кадры с выбранным эталоном и пропустила видимые в игре
# сетку и полосы (s7101, FAIL Vitali 07.10). Приёмка - по дампу движка, crossing_check.py.
# Стык двух кадров без шва, если у общего края оба совпадают с одним непрерывным полем. Такие поля в задании есть
# по построению: тротуар - кадр 0 (периодическая клетка), камень бордюра - кадр 1 (полоса по u, вдоль v тот же
# профиль, клетка материала периодична) и кадр 2 (то же поперёк). Поэтому каждый кадр у каждого из четырёх краёв
# сравнивается попиксельно с эталоном своего вида в тех же пикселях x4 (геометрия кадров одна): отклонение у края
# около 0 - любой сосед из задания встаёт без шва. Сравнение пар областей (перепад через край против перепада
# внутри) мерить нельзя: две разные области материала расходятся сами, и на 70 пикселях края шов в 3 единицы тонет
# в этом разбросе (07.10, контроль «ярче на 3» не отличался от пары без шва).

SEAM_EPS = 0.03            # полоса у края, доли клетки (около двух пикселей x4)
SEAM_KERB_GAP = 0.03       # пиксели у линии бордюра (смесь тротуара и камня) не мерятся


def pixel_uv():
    u, v = frame_uv(1)
    return u, v


def ref_of(name, u, v, u0):
    """Эталон пикселя: "0" - тротуар, "1"/"2" - камень полосы по u / по v, "" - не мерится (у линии бордюра)."""
    if name in NAMES:
        return np.full(u.shape, "0", dtype=object)
    t = {"1": u, "2": v, "7": np.maximum(u, v)}[name]
    out = np.full(u.shape, "0", dtype=object)
    stone = t >= u0
    if name == "7":
        out[stone & (u >= v)] = "1"
        out[stone & (u < v)] = "2"
        out[stone & (np.abs(u - v) < 0.04)] = ""
    else:
        out[stone] = name
    out[np.abs(t - u0) < SEAM_KERB_GAP] = ""
    return out


def edge_dev(fr, name, frames, u0, fb=None):
    """Отклонение кадра от эталона у четырёх краёв: {край: (среднее |RGB|, наибольшее по 4 пикселям подряд, n)}.
    fb - подменить кадр (контроль меры)."""
    u, v = pixel_uv()
    f = (frames[name] if fb is None else fb).astype(np.float32)
    op = f[..., 3] > 0
    ref = ref_of(name, u, v, u0)
    res = {}
    for e, m_e in (("+u", u > 1 - SEAM_EPS), ("-u", u < SEAM_EPS), ("+v", v > 1 - SEAM_EPS), ("-v", v < SEAM_EPS)):
        devs, n = [], 0
        for r in ("0", "1", "2"):
            m = m_e & op & (ref == r) & (frames[r][..., 3] > 0)
            if not m.any():
                continue
            dv = np.abs(f[..., :3] - frames[r][..., :3].astype(np.float32)).mean(-1)[m]
            devs.append(dv)
            n += int(m.sum())
        if n < 12:
            res[e] = None
            continue
        dv = np.concatenate(devs)
        run = np.convolve(dv, np.ones(4) / 4, "valid").max() if len(dv) >= 4 else dv.max()
        res[e] = (float(dv.mean()), float(run), n)
    return res


def seam_table(frames, u0, unmatched=None):
    """Каждый кадр, каждый край: отклонение от эталона у края. Контроли, что мера видит шов: кадр 0 ярче на 3
    единицы, кадр 0 отражённый по горизонтали (чужое зерно), вариант 0.v1 без сведения краёв к 0."""
    res = {}
    for na in ALL:
        for e, r in edge_dev(frames[na], na, frames, u0).items():
            res["%s %s" % (na, e)] = r
    f0 = frames["0"]
    bright = f0.copy()
    bright[..., :3] = np.clip(f0[..., :3].astype(int) + 3, 0, 255).astype(np.uint8)
    ctl = {"0 ярче на 3": edge_dev(f0, "0", frames, u0, fb=bright),
           "0 отражённый": edge_dev(f0, "0", frames, u0, fb=f0[:, ::-1].copy())}
    if unmatched is not None:
        ctl["0.v1 без сведения краёв"] = edge_dev(unmatched, "0.v1", frames, u0, fb=unmatched)
    ctl = {k: max((x for x in v.values() if x), key=lambda x: x[0]) for k, v in ctl.items()}
    return res, ctl


# ------------------------------------------------------------------ build

def cmd_build(a):
    if a.synthetic:
        tag, tex = "_synthetic", synthetic()
        src = "синтетика (процедурный шум) - проверка сборки, не проба модели"
    else:
        raw = Path(a.raw)
        if not raw.exists():
            raise SystemExit("нет ответа модели %s - его рисует sidewalk_render.py через gpuq" % raw)
        tag = a.tag or raw.stem.replace("raw_", "")
        im = Image.open(raw).convert("RGB")
        tex = np.asarray(im.resize((SIDE, SIDE), Image.LANCZOS)).astype(np.float32)
        src = raw.resolve().relative_to(ROOT).as_posix()
    d = OUT / tag
    (d / "ROADS.PCK").mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(tex, 0, 255).astype(np.uint8), "RGB").save(d / "raw_1024.png")
    mean_rgb, cl_std = classic_mean()
    u0, counts = kerb_start()
    cells, grains, wears, diag = make_cells(tex, a, mean_rgb, cl_std * a.grain)
    frames = build_frames(cells, grains[0], wears[0], u0, a, mean_rgb)
    a_un = argparse.Namespace(**vars(a))
    a_un.edge_band = 1e-6                       # контроль меры швов: те же варианты без сведения краёв
    cells_un = make_cells(tex, a_un, mean_rgb, cl_std * a.grain)[0]
    unmatched = build_frames(cells_un, grains[0], wears[0], u0, a, mean_rgb)["0.v1"]
    for nm, fr in frames.items():
        Image.fromarray(fr, "RGBA").save(d / "ROADS.PCK" / (nm + ".png"))
    for j, c in enumerate(cells):
        Image.fromarray(c.astype(np.uint8), "RGB").save(d / ("uv_%d.png" % j))
    seams, ctl = seam_table(frames, u0, unmatched)
    (d / "seams.json").write_text(json.dumps(dict(edges=seams, controls=ctl), ensure_ascii=False, indent=1),
                                  encoding=ENC)
    Ls = {nm: js.light(frames[nm]) for nm in NAMES}
    walk_l = {}
    for f in KERB_FRAMES:
        i4 = js.classic_idx("ROADS", f)
        m = (i4 > 0) & (i4 < 16)
        m[:96] = False
        walk_l[str(f)] = [round(js.walk_light(f)[0], 2), round(float(js.lab(frames[str(f)][..., :3][m]).mean(0)[0]), 2)]
    bad = {k: v for k, v in seams.items() if v and v[0] > SEAM_OK}
    info = dict(source=src, tag=tag, period=a.period, sigma_low=a.sigma_low, grain=a.grain, wear_std=a.wear_std,
                wear_max=a.wear_max, edge_band=a.edge_band, kerb_grain=a.kerb_grain, kerb_wear=a.kerb_wear,
                kerb_pit=a.kerb_pit, u0=u0, kerb_counts={str(k): v for k, v in counts.items()},
                classic_mean_rgb=[round(float(x), 2) for x in mean_rgb], classic_grain_std=round(cl_std, 2),
                L_classic=round(js.light(js.rgba_classic(js.classic_idx("ROADS", 0))), 2),
                L_variants={k: round(v, 2) for k, v in Ls.items()}, L_walk_in_kerb=walk_l,
                seams_measured=sum(1 for v in seams.values() if v), seams_bad=sorted(bad),
                seam_worst=max(v[0] for v in seams.values() if v),
                seam_controls={k: [round(v[0], 2), round(v[1], 2)] for k, v in ctl.items()},
                **{k: ([round(x, 3) for x in v] if isinstance(v, list) else round(v, 3)) for k, v in diag.items()})
    (d / "build.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding=ENC)
    print("кадры: %s" % (d / "ROADS.PCK"))
    print("U0 %.4f (тротуар %s), тон классики %s, зерно классики %.2f" % (u0, counts, info["classic_mean_rgb"], cl_std))
    print("L* классики %.1f; вариантов %s" % (info["L_classic"], info["L_variants"]))
    print("тротуар внутри бордюрных кадров L* (классика, новое): %s" % walk_l)
    print("зерно: сырое %s -> %.2f; износ: сырой %s, множитель %.3f, итог %s" % (
        info["grain_raw"], info["grain_std"], info["wear_raw"], info["wear_gain"], info["wear_std_out"]))
    print("направленность зерна %s; узор клетки %s (шум без узора ~0.125)" % (info["coherence"], info["cell_pattern"]))
    print("неровность разброса зерна по клетке: %.3f (прежняя складка %.3f)" % (
        info["grain_std_spread"], info["grain_std_spread_old_fold"]))
    print("края кадров (диагностика, не приёмка): измерено %d из %d, отклонение > %.2f у %d %s" % (
        info["seams_measured"], len(seams), SEAM_OK, len(bad), ", ".join(sorted(bad))))
    print("худшее отклонение у края %.3f; контроль меры (среднее / 4 пикселя подряд, обязан быть больше %.1f): %s"
          % (info["seam_worst"], SEAM_OK, info["seam_controls"]))


# ------------------------------------------------------------------ лист

def load_frames(tag):
    d = OUT / tag / "ROADS.PCK"
    if not d.exists():
        raise SystemExit("нет кадров %s - сначала build" % d)
    return {p.stem: np.asarray(Image.open(p).convert("RGBA")) for p in d.glob("*.png")}


class Sheet:
    def __init__(self, width, title, synth):
        self.W = width
        self.im = Image.new("RGB", (width, 9000), js.BG)
        self.d = ImageDraw.Draw(self.im)
        self.f_t = ImageFont.truetype(js.FONT_B, 24)
        self.f_h = ImageFont.truetype(js.FONT_B, 17)
        self.f_s = ImageFont.truetype(js.FONT, 15)
        self.y = 10
        self.d.text((14, self.y), title, font=self.f_t, fill=(255, 255, 255))
        self.y += 36
        if synth:
            self.d.rectangle((10, self.y, width - 10, self.y + 30), fill=(150, 20, 20))
            self.d.text((18, self.y + 5), "СИНТЕТИКА: процедурный шум вместо ответа модели - проверка сборки и листа, "
                        "не проба", font=self.f_h, fill=(255, 255, 255))
            self.y += 40

    def para(self, t, fill=(240, 240, 240), step=20):
        line = ""
        for w in t.split(" "):
            if self.d.textlength(line + " " + w, font=self.f_s) > self.W - 40:
                self.d.text((14, self.y), line, font=self.f_s, fill=fill)
                self.y += step
                line = w
            else:
                line = (line + " " + w).strip()
        self.d.text((14, self.y), line, font=self.f_s, fill=fill)
        self.y += step

    def head(self, t):
        self.y += 6
        line = ""
        for w in t.split(" "):
            if line and self.d.textlength(line + " " + w, font=self.f_h) > self.W - 40:
                self.d.text((14, self.y), line, font=self.f_h, fill=(255, 255, 0))
                self.y += 22
                line = w
            else:
                line = (line + " " + w).strip()
        self.d.text((14, self.y), line, font=self.f_h, fill=(255, 255, 0))
        self.y += 26

    def row(self, items, gap=16):
        """items: [(подпись, PIL.Image)] в ряд; высота ряда - по самой высокой."""
        x = 14
        h = 0
        for lbl, im in items:
            self.d.text((x, self.y), lbl, font=self.f_s, fill=(255, 255, 255))
            if im.mode == "RGBA":
                self.im.paste(im, (x, self.y + 20), im)
            else:
                self.im.paste(im, (x, self.y + 20))
            x += im.width + gap
            h = max(h, im.height)
        self.y += 20 + h + 10

    def save(self, path):
        self.im.crop((0, 0, self.W, self.y + 8)).save(path)
        print("лист: %s (%d x %d)" % (path, self.W, self.y + 8))


def rgba(arr, crop=None, scale=1, resample=Image.NEAREST):
    im = Image.fromarray(arr)
    if crop:
        im = im.crop(crop)
    if scale != 1:
        im = im.resize((int(im.width * scale), int(im.height * scale)), resample)
    return im


def blotch(im, fw, fh, top):
    """Крупные пятна поля: std яркости середины поля 480 x 240 после гаусса 16 пикс x4 (четверть клетки)."""
    cx, cy = fw // 2, (fh + top) // 2
    c = im[cy - 120:cy + 120, cx - 240:cx + 240]
    if (c[..., 3] < 255).any():
        raise SystemExit("середина поля задела фон")
    lum = c[..., :3].astype(np.float64) @ LUMA          # в плавающей точке: размытие в 8 битах - шум округления
    t = np.arange(-48, 49)
    k = np.exp(-t * t / (2 * 16.0 ** 2))
    k /= k.sum()
    b = np.apply_along_axis(lambda r: np.convolve(r, k, "valid"), 1, lum)
    b = np.apply_along_axis(lambda r: np.convolve(r, k, "valid"), 0, b)
    return float(b.std())


def cmd_sheet(a):
    new = load_frames(a.tag)
    info = json.loads((OUT / a.tag / "build.json").read_text(encoding=ENC))
    seams = json.loads((OUT / a.tag / "seams.json").read_text(encoding=ENC))["edges"]
    sh = Sheet(2400, "Проба: тротуар ROADS с бордюрами (sidewalk_job1), метка %s - классика | нынешний HD | новое, "
               "один масштаб в каждой строке" % a.tag, a.tag.startswith("_synthetic"))
    sh.para("Материал: ровное крапчатое серое покрытие тротуара, тон классики. Источник: %s. Классика x4 - боевая "
            "палитра delicious_regular, тень 0; нынешний HD - мод hd в установке Пираток (его читает игра)."
            % info["source"])

    # 0. ответ модели и клетки - чтобы отделить брак модели от брака обработки
    sh.head("0. Ответ модели 1:1 (середина квадрата 1024) и периодические клетки вариантов после обработки (x2) - "
            "здесь видно, что нарисовала модель и что из этого сделала обработка")
    raw = Image.open(OUT / a.tag / "raw_1024.png")
    cells = [Image.open(OUT / a.tag / ("uv_%d.png" % j)) for j in range(4)]
    p = cells[0].width
    sh.row([("ответ, участок 640 x 640", raw.crop((192, 192, 832, 832)))] +
           [("клетка %s" % nm, c.resize((p * 2, p * 2), Image.NEAREST)) for nm, c in zip(NAMES, cells)])

    # 1. кадры
    sh.head("1. Кадры (пол - нижние 64 строки x4, показ x2)")
    crop = (0, 96, 128, 160)
    cols = [("0", "тротуар 0"), ("1", "бордюр 1"), ("2", "бордюр 2"), ("7", "угол 7"),
            ("0.v1", "вариант 0.v1"), ("0.v2", "вариант 0.v2"), ("0.v3", "вариант 0.v3")]
    blank = Image.new("RGBA", (256, 128), (0, 0, 0, 0))
    for lbl, src in (("классика x4", "c"), ("HD сейчас", "h"), ("новое", "n")):
        items = []
        for nm, cl in cols:
            if src == "c":
                im = blank if "." in nm else rgba(js.rgba_classic(js.classic_idx("ROADS", int(nm))), crop, 2)
            elif src == "h":
                im = rgba(js.rgba_hd("ROADS", nm), crop, 2)
            else:
                im = rgba(new[nm], crop, 2)
            items.append(("%s - %s" % (lbl, cl), im))
        sh.row(items, gap=40)

    # 2. перекрёсток
    bt = js.mt.Battle(js.CORNER)
    seed = gf.battle_seed(bt.X, bt.Y, bt.Z, bt.blocks)
    cx, cy, n = js.CORNER_AT
    corner = js.Blocks.battle_floor(js.CORNER, cx, cy, n)
    old_found = [js.rgba_hd("ROADS", nm) for nm in NAMES]
    new_found = [new[nm] for nm in NAMES]

    def new_pick(s, f, x, yy):
        if (s, f) == ("ROADS", 0):
            return gf.frame_for(new_found, cx + x, cy + yy, 0, seed, K)
        if s == "ROADS" and str(f) in new:
            return new[str(f)]
        return js.rgba_hd(s, str(f))
    sh.head("2. Перекрёсток: бой STR_ERIDIAN_TERROR_139, угол URBAN02 (клетки x %d..%d, y %d..%d, только пол), x4 в "
            "натуральную величину. Асфальт 9 и разметка 11 - старые (следующее задание)" % (cx, cx + n - 1, cy, cy + n - 1))
    cl, *_ = js.assemble(corner, lambda s, f, x, yy: js.rgba_classic(js.classic_idx(s, f)))
    old, *_ = js.assemble(corner, js.ground_pick(seed, cx, cy, old_found))
    nw, *_ = js.assemble(corner, new_pick)
    H, W = cl.shape[:2]
    top = 96
    sh.row([(lbl, rgba(im, (0, top, W, H))) for im, lbl in ((cl, "классика x4"), (old, "HD сейчас"), (nw, "новое"))])

    # 3. поле 9 x 9
    N = 9
    fx0, fy0 = cx - 4, cy - 4
    fl = [gf.field([js.rgba_classic(js.classic_idx("ROADS", 0))], n=N, seed=seed, x0=fx0, y0=fy0, k=K, bg=js.BG)[0],
          gf.field(old_found, n=N, seed=seed, x0=fx0, y0=fy0, k=K, bg=js.BG)[0],
          gf.field(new_found, n=N, seed=seed, x0=fx0, y0=fy0, k=K, bg=js.BG)[0],
          gf.field([new["0"]], n=N, seed=seed, x0=fx0, y0=fy0, k=K, bg=js.BG)[0]]
    fh, fw = fl[0].shape[:2]
    sh.head("3. Поле 9 x 9 тротуара ROADS:0 с вариантами раскладкой движка (клетки x %d..%d, y %d..%d того же боя, "
            "зерно узора %d), уменьшено вдвое у всех; четвёртое - новое ОДНИМ кадром 0, без смешения вариантов"
            % (fx0, fx0 + N - 1, fy0, fy0 + N - 1, seed))
    sh.row([(lbl, rgba(im, (0, top, fw, fh), 0.5, Image.LANCZOS)) for im, lbl in
            zip(fl, ("классика", "HD сейчас", "новое", "новое без вариантов"))], gap=12)
    cw, ch = 760, 460
    box = (fw // 2 - cw // 2, (fh + top) // 2 - ch // 2, fw // 2 + cw // 2, (fh + top) // 2 + ch // 2)
    sh.head("   середина того же поля x4 в натуральную величину")
    sh.row([(lbl, rgba(im, box)) for im, lbl in zip(fl[:3], ("классика", "HD сейчас", "новое"))])
    sh.para("Крупные пятна поля - разброс яркости после размытия на четверть клетки (гаусс 16 пикс x4), середина "
            "поля 480 x 240: " + ";   ".join("%s %.2f" % (lbl, blotch(im, fw, fh, top)) for im, lbl in
                                             zip(fl, ("классика", "HD сейчас", "новое", "новое без вариантов"))))

    # 4. швы
    sh.head("4. Края кадров (диагностика, НЕ приёмка): каждый кадр задания у каждого из четырёх краёв (полоса %.2f "
            "клетки) против эталона своего вида - тротуар против кадра 0, камень против кадра 1 или 2. О карте эта "
            "мера не говорит: на игровом кадре s7101 видны сетка и полосы, которых она не нашла; приёмка - дамп игры, "
            "crossing_check.py. Среднее |RGB| / худшие 4 пикселя подряд; порог %.1f" % (SEAM_EPS, SEAM_OK))
    ctl = json.loads((OUT / a.tag / "seams.json").read_text(encoding=ENC))["controls"]
    sh.para("Контроль, что мера видит шов: " + ";   ".join(
        "%s: %.2f / %.2f" % (k, v[0], v[1]) for k, v in ctl.items()), fill=(180, 220, 255))
    for nm in ALL:
        parts = []
        for e in ("+u", "-u", "+v", "-v"):
            r = seams.get("%s %s" % (nm, e))
            if not r:
                parts.append("%s: не мерится" % e)
            else:
                parts.append("%s: %.2f / %.2f%s" % (e, r[0], r[1], " ШОВ" if r[0] > SEAM_OK else ""))
        sh.para("кадр %-5s  %s" % (nm, ";   ".join(parts)), fill=(255, 140, 120) if "ШОВ" in "".join(parts) else
                (240, 240, 240))

    # 5. числа
    sh.head("5. Числа - диагностика, решает лист")
    old_L = {nm: js.light(fr) for nm, fr in zip(NAMES, old_found)}
    for t in (
        "L* пола: классика %.1f; HD сейчас %s; новое %s." % (
            info["L_classic"], ", ".join("%s %.1f" % kv for kv in old_L.items()),
            ", ".join("%s %.1f" % kv for kv in info["L_variants"].items())),
        "Тротуар внутри бордюрных кадров, L* (классика -> новое): %s; в нынешнем HD 17-18." % "; ".join(
            "%s: %.1f -> %.1f" % (k, v[0], v[1]) for k, v in info["L_walk_in_kerb"].items()),
        "Полоса бордюра: от U0 = %.4f до края клетки (у классики тротуар %s пикселей ромба); край - прямая, "
        "сглаживание по 16 подточкам пикселя x4; материал камня - зерно x%.1f, износ x%.1f, выщербины глубже %.1f сигм."
        % (info["u0"], info["kerb_counts"]["1"], info["kerb_grain"], info["kerb_wear"], info["kerb_pit"]),
        "Зерно: сырое по вариантам %s -> общее %.2f (у классики %.2f); неровность его разброса по клетке %.3f "
        "(прежняя складка без поправки %.3f). Износ: сырой %s, множитель %.3f, итог %s (потолок %.1f). "
        "Направленность зерна (0 - нет, 1 - полосы): %s. Узор с периодом клетки (около 0.125 - нет): %s." % (
            info["grain_raw"], info["grain_std"], info["classic_grain_std"], info["grain_std_spread"],
            info["grain_std_spread_old_fold"], info["wear_raw"], info["wear_gain"], info["wear_std_out"],
            info["wear_max"], info["coherence"], info["cell_pattern"]),
        "Края вариантов сведены к краю варианта 0 в полосе %.2f клетки (разброс при этом тот же)." % info["edge_band"],
    ):
        sh.para(t)
    sh.save(OUT / a.tag / "sheet.png")


# ------------------------------------------------------------------ игра

def junction(link, target):
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def layout(tag):
    """<метка>/mods: соединения на моды установки, hd - своя папка из соединений, кроме hd/TERRAIN/ROADS.PCK -
    копии пака, где кадры задания заменены кадрами пробы. Установку не трогает."""
    root = OUT / "_mods" / tag
    frames = OUT / tag / "ROADS.PCK"
    if root.exists():
        dst = root / "hd" / "hd" / "TERRAIN" / "ROADS.PCK"
        for nm in ALL:
            shutil.copy2(frames / (nm + ".png"), dst / (nm + ".png"))
        return root
    root.mkdir(parents=True)
    for m in GAME_MODS.iterdir():
        if m.name != "hd":
            junction(root / m.name, m)
    hd = root / "hd"
    src_hd = GAME_MODS / "hd"
    for sub_src, sub_dst, keep in ((src_hd, hd, "hd"), (src_hd / "hd", hd / "hd", "TERRAIN"),
                                   (src_hd / "hd" / "TERRAIN", hd / "hd" / "TERRAIN", "ROADS.PCK")):
        sub_dst.mkdir(parents=True, exist_ok=True)
        for e in sub_src.iterdir():
            if e.name == keep:
                continue
            if e.is_dir():
                junction(sub_dst / e.name, e)
            else:
                shutil.copy2(e, sub_dst / e.name)
    dst = hd / "hd" / "TERRAIN" / "ROADS.PCK"
    shutil.copytree(src_hd / "hd" / "TERRAIN" / "ROADS.PCK", dst)
    for nm in ALL:
        shutil.copy2(frames / (nm + ".png"), dst / (nm + ".png"))
    return root


GAME_AT = (49, 9, 0)   # клетка тротуара в окне CORNER_AT: выбранный юнит встаёт сюда, камера дампа - на угол


def game_save():
    """Копия сейва перекрёстка для игрового кадра: выбранный юнит на тротуаре (камера идёт за ним, иначе в кадре
    корабль), дым снят, клетки открыты, день (globalshade 0). Сам js.CORNER не меняется."""
    sav = OUT / "_game_ref" / "corner.sav"
    if not sav.exists():
        sav.parent.mkdir(parents=True, exist_ok=True)
        msc.prep(str(js.CORNER), str(sav), center=GAME_AT, clear_smoke=True)
        txt = sav.read_text(encoding="utf-8")
        txt2, k = re.subn(r"(?m)^  globalshade: \d+$", "  globalshade: 0", txt)
        if k != 1:
            raise SystemExit("globalshade: %d мест" % k)
        sav.write_text(txt2, encoding="utf-8")
    return sav


def run_game(out, mods_dir, mode, after, user_name):
    """user_name - своя папка пользователя на каждую метку: два прогона в одной папке делят options.cfg и лог."""
    if out.exists():
        print("есть:", out)
        return True
    sets = "oxceHdMode=%d;oxceHdScale=4;oxceHdGroundVariants=true" % mode
    user = OUT / "_users" / user_name
    cmd = [sys.executable, str(ROOT / "tools" / "game_hidden.py"), "--out", str(out), "--save", str(game_save()),
           "--after", str(after), "--user", str(user), "--set", sets]
    if mods_dir:
        cmd += ["--mods-dir", str(mods_dir)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(out.name, "код", r.returncode, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:],
          flush=True)
    return out.exists()


def cmd_game(a):
    if not (OUT / a.tag / "ROADS.PCK").exists():
        raise SystemExit("нет кадров %s - сначала build" % a.tag)
    ref = OUT / "_game_ref"
    ref.mkdir(parents=True, exist_ok=True)
    g = OUT / a.tag / "game"
    g.mkdir(parents=True, exist_ok=True)
    mods = layout(a.tag)
    new_png = g / "new.png"
    if new_png.exists() and a.force:
        new_png.unlink()
    ok = [run_game(ref / "classic.png", None, 0, a.after, "classic"),
          run_game(ref / "hd_now.png", None, 1, a.after, "hd_now"),
          run_game(new_png, mods, 1, a.after, "new_" + a.tag)]
    if not all(ok):
        raise SystemExit("не все кадры сняты - смотреть openxcom.log в %s" % (OUT / "_users"))
    ims = [Image.open(p).convert("RGB") for p in (ref / "classic.png", ref / "hd_now.png", new_png)]
    w, h = ims[0].size
    sh = Sheet(2400, "Игровой кадр: тротуар ROADS (sidewalk_job1), метка %s - экран 1920 x 1080 как у игрока, k=4"
               % a.tag, a.tag.startswith("_synthetic"))
    sh.para("Три невидимых прогона одной сборки на одной копии сейва перекрёстка STR_ERIDIAN_TERROR_139: классика "
            "(режим 0), нынешний HD и новое (режим 1, варианты пола включены). Новое отличается от нынешнего HD только "
            "кадрами ROADS 0, 0.v1-v3, 1, 2, 7. Юниты и анимация живые - между кадрами могут чуть отличаться.")
    cw, ch = 780, 560
    box = (w // 2 - cw // 2, h // 2 - ch // 2, w // 2 + cw // 2, h // 2 + ch // 2)
    sh.head("середина экрана 1:1")
    sh.row([(lbl, im.crop(box)) for im, lbl in zip(ims, ("классика", "HD сейчас", "новое"))], gap=12)
    sh.head("экран целиком, уменьшено вдвое")
    for im, lbl in zip(ims, ("классика", "HD сейчас", "новое")):
        sh.row([(lbl, im.resize((w // 2, h // 2), Image.LANCZOS))])
    sh.save(OUT / a.tag / "game.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="кадры из ответа модели (или --synthetic)")
    b.add_argument("--raw", default="", help="ответ sidewalk_render.py")
    b.add_argument("--tag", default="", help="метка папки; по умолчанию - имя ответа без raw_")
    b.add_argument("--synthetic", action="store_true", help="процедурный шум вместо ответа - проверка без видеокарты")
    b.add_argument("--period", type=int, default=160, help="сторона клетки в пикселях квадрата 1024 (6.4 клетки)")
    b.add_argument("--sigma-low", type=float, default=12.0, help="граница зерна и износа, пикс. квадрата")
    b.add_argument("--grain", type=float, default=1.0, help="потолок разброса зерна в долях разброса классики")
    b.add_argument("--wear-std", type=float, default=1.0, help="разброс износа по яркости, единиц 0..255")
    b.add_argument("--wear-max", type=float, default=3.0, help="предел отклонения износа")
    b.add_argument("--no-wear-center", dest="wear_center", action="store_false",
                   help="не центрировать износ вариантов (контроль: облака размером в клетку)")
    b.add_argument("--edge-band", type=float, default=0.25, help="полоса у края клетки, где варианты сведены к 0")
    b.add_argument("--kerb-grain", type=float, default=1.0, help="зерно на камне бордюра, в долях зерна тротуара")
    b.add_argument("--kerb-wear", type=float, default=2.5, help="износ на камне бордюра, в долях износа тротуара")
    b.add_argument("--kerb-pit", type=float, default=1.8, help="выщербины: зерно глубже стольких сигм")
    s = sub.add_parser("sheet", help="лист приёмки: ответ, клетки, кадры, перекрёсток, поле 9x9, швы")
    s.add_argument("--tag", required=True)
    gm_ = sub.add_parser("game", help="игровой кадр: классика | HD сейчас | новое, невидимо (game_hidden.py)")
    gm_.add_argument("--tag", required=True)
    gm_.add_argument("--after", type=int, default=110, help="секунд до кадра (загрузка сейва ~60-90)")
    gm_.add_argument("--force", action="store_true", help="переснять новое")
    a = ap.parse_args()
    if a.cmd == "build":
        if not a.synthetic and not a.raw:
            raise SystemExit("нужен --raw или --synthetic")
        cmd_build(a)
    elif a.cmd == "sheet":
        cmd_sheet(a)
    else:
        cmd_game(a)


if __name__ == "__main__":
    main()
