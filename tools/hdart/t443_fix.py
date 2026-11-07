#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000443, переделка 31.10 (Vitali: «Править все три»): балки Города гулей.

Приёмка 31.10c нашла у кадров MILWAREGHOUL 47 48 49 50 52 54 (и MILWARE 48-51/53/55, классика та же):
  (а) кадры уже силуэта классики: покрытие 0.59-0.78, между полосами виден тёмный пол;
  (б) на стыках клеток видны торцы секций и тонкая щель;
  (в) на концах плеч узлов 48/50 бело-розовые пятна.

Правка нынешних кадров, без видеокарты. Балка - выдавленная вдоль оси: в «сдвинутом» пространстве (u = x,
v = y -+ x/2) она горизонтальная полоса и не меняется вдоль u. Для каждой полосы:
  1. берём из нынешнего кадра тело балки без торцов, масштабируем так, чтобы высота профиля стала высотой полосы
     силуэта классики (заливка до силуэта, (а));
  2. тело собираем в бесшовную плитку периода 64 по u (шаг клетки 64 пикселя HD вдоль оси): кадр соседней клетки
     получает ту же картину внахлёст - торцов нет (б);
  3. альфа - силуэт классики x4, сглаженный xBRZ (R-121), растянутый вдоль оси на 3 пикселя: соседние клетки
     перекрываются целиком, а не встык, щели нет (б); по длинным краям - сглаженный силуэт без лесенки.
Узел 48/50: балки по полосам силуэта + блок узла нынешнего кадра, ужатый/увеличенный под блок классики (в).

    py -3.13 tools\hdart\t443_fix.py build     # art/tickets/t443/fix/<НАБОР>_<кадр>.png
    py -3.13 tools\hdart\t443_fix.py sheets
В МОД НИЧЕГО НЕ СТАВИТ.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402
from scipy.ndimage import gaussian_filter1d, maximum_filter1d  # noqa: E402

PACK = os.path.join(ROOT, "user", "mods", "hd", "hd", "TERRAIN")
OUT = os.path.join(ROOT, "art", "tickets", "t443", "fix")
PERIOD = 64          # шаг клетки вдоль оси в пикселях HD по u
XFADE = 8            # перекрытие склейки плитки
END_GROW = 1
SH_PAD = 130


def sheared_dims(h):
    return 2 * h + SH_PAD


def shear(a, sign):
    """вертикаль x2 (повтор), столбец x сдвинут на x строк вдоль оси (sign<0: оси вниз-вправо)."""
    h, w = a.shape[:2]
    a2 = np.repeat(a, 2, axis=0)
    out = np.zeros((sheared_dims(h),) + a.shape[1:], a.dtype)
    for x in range(w):
        s = (128 - x) if sign < 0 else x
        out[s:s + 2 * h, x] = a2[:, x]
    return out


def unshear(b, sign, h, w):
    out = np.zeros((h, w) + b.shape[2:], np.float32)
    for x in range(w):
        s = (128 - x) if sign < 0 else x
        col = b[s:s + 2 * h, x].astype(np.float32)
        out[:, x] = (col[0::2] + col[1::2]) * 0.5
    return out


def classic_sil(set_name, frame):
    """Силуэт классики x4, сглаженный xBRZ (как clip_smooth t443_gen), float 0..1, 160x128."""
    import xcom_sprites as xs
    import probe_object as po
    base = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "TERRAIN", set_name)
    fr = xs.read_pck(base + ".PCK", base + ".TAB")
    c = np.asarray(fr[frame]) > 0
    m = Image.fromarray(c.astype(np.uint8) * 255, "L")
    return np.asarray(po.smooth_silhouette(m, 4), np.float32) / 255.0, c


def runs(col, thr):
    """список (начало, конец-искл.) отрезков col>thr."""
    m = col > thr
    d = np.diff(np.concatenate([[0], m.astype(np.int8), [0]]))
    st, en = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    return list(zip(st, en))


def extent(arr, cols, rows, thr):
    """медианные верх и низ отрезка arr>thr в окне столбцов cols и строк rows (в сдвинутом пространстве)."""
    tops, bots = [], []
    for u in range(cols[0], cols[1]):
        col = arr[rows[0]:rows[1], u]
        rr = runs(col, thr)
        if not rr:
            continue
        # самый длинный отрезок
        s, e = max(rr, key=lambda t: t[1] - t[0])
        tops.append(s + rows[0])
        bots.append(e + rows[0])
    if not tops:
        raise ValueError("пусто: cols %s rows %s" % (cols, rows))
    return int(np.median(tops)), int(np.median(bots))


class Strip:
    def __init__(self, name, hint, body, silcols, urange=(0, 128)):
        self.name, self.hint, self.body, self.silcols, self.urange = name, hint, body, silcols, urange


def make_tile(seg, period, xfade):
    """seg HxWx3 (float) -> плитка HxPx3, бесшовная по краям."""
    H, W = seg.shape[:2]
    start = max(0, (W - (period + xfade)) // 2)
    B = seg[:, start:start + period + xfade]
    if B.shape[1] < period + xfade:
        raise ValueError("тело короче плитки: %d < %d" % (seg.shape[1], period + xfade))
    T = B[:, :period].copy()
    for u in range(xfade):
        a = (u + 0.5) / xfade
        T[:, u] = (1 - a) * B[:, u + period] + a * B[:, u]
    return T


def build_tiles(cur, sil, sign, strips, period=PERIOD):
    """Плитки тела балок из кадра cur (RGBA uint8 160x128): по одной на полосу.
    Возвращает список (T, P, s0, s1, строка отчёта); s0..s1 - полоса силуэта в сдвинутом пространстве."""
    cs = shear(cur.astype(np.float32), sign)
    ss = shear(sil, sign)
    alpha_c = cs[..., 3] / 255.0
    tex = []
    for st in strips:
        b0, b1 = extent(alpha_c, st.body, st.hint, 0.5)
        s0, s1 = extent(ss, st.silcols, st.hint, 0.5)
        f = (s1 - s0) / float(b1 - b0)
        # тело: строки b0+1..b1-1 (края с полупрозрачностью не берём), столбцы body
        rgb = cs[b0 + 1:b1 - 1, st.body[0]:st.body[1], :3]
        Hn = s1 - s0
        Wn = int(round(rgb.shape[1] * f))
        big = np.asarray(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).resize((Wn, Hn), Image.LANCZOS),
                         np.float32)
        P = period
        if Wn < P + XFADE:
            P = 32
        T = make_tile(big, P, XFADE)
        tex.append((T, P, s0, s1, "%s: балка %d..%d (%d), силуэт %d..%d (%d), масштаб %.2f, плитка %d" % (
            st.name, b0, b1, b1 - b0, s0, s1, s1 - s0, f, P)))
    return tex


def compose(tex, urange, sil, sign, h=160, w=128, grow=END_GROW):
    """Сборка кадра из плиток по полосам. urange - диапазоны u по полосам. Возвращает RGBA uint8."""
    ss = shear(sil, sign)
    R = ss.shape[0]
    sd = maximum_filter1d(ss, size=2 * grow + 1, axis=1)
    out = np.zeros((R, w, 4), np.float32)
    centers = [(s0 + s1) / 2.0 for (_, _, s0, s1, _) in tex]
    order = np.argsort(centers)
    uu = np.arange(w)
    owner = np.full((R, w), -1, np.int32)
    for i in order:                       # сверху вниз: нижняя (ближняя) полоса перекрывает
        T, P, s0, s1, _ = tex[i]
        u0, u1 = urange[i]
        rows = np.arange(max(0, s0 - 2), min(R, s1 + 2))
        sel = (uu >= u0) & (uu < u1)
        owner[np.ix_(rows, uu[sel])] = i
    need = (sd > 0.02) & (owner < 0)
    if need.any():
        ry, rx = np.nonzero(need)
        cs_arr = np.array(centers)
        owner[ry, rx] = np.argmin(np.abs(ry[:, None] - cs_arr[None, :]), axis=1)
    for i, (T, P, s0, s1, _) in enumerate(tex):
        ry, rx = np.nonzero(owner == i)
        k = np.clip(ry - s0, 0, T.shape[0] - 1)
        out[ry, rx, :3] = T[k, rx % P]
    # альфа: длинные края - прямые линии по строкам полосы (R-121, ровный край без лесенки), торцы - по силуэту
    # классики, растянутому вдоль оси; вертикаль силуэта шире на 1 пиксель, чтобы неровность его края не резала
    rect = np.zeros((R, w), np.float32)
    for (T, P, s0, s1, _) in tex:
        rect[max(0, s0 - 2):s1, :] = 1.0
    rect = gaussian_filter1d(rect, 1.2, axis=0)
    sil_b = maximum_filter1d(sd, size=5, axis=0)
    out[..., 3] = np.minimum(rect, sil_b)
    out[owner < 0, 3] = 0
    return out, owner, sd


def finish(out, sign, h=160, w=128):
    """out: сдвинутый RGB (0..255) + альфа 0..1 -> RGBA uint8 в экранных координатах."""
    o = out.copy()
    o[..., :3] *= o[..., 3:4]                       # предумножение: края не темнеют при усреднении строк
    o[..., 3] *= 255.0
    res = unshear(o, sign, h, w)
    a = res[..., 3:4]
    res[..., :3] = res[..., :3] / np.maximum(a, 1e-3) * 255.0
    res = np.clip(res, 0, 255).astype(np.uint8)
    res[res[..., 3] == 0, :3] = 0
    return res


def fix_beams(cur, sil, sign, strips, urange=None):
    tex = build_tiles(cur, sil, sign, strips)
    urange = urange or [s.urange for s in strips]
    out, owner, sd = compose(tex, urange, sil, sign)
    return finish(out, sign), [t[4] for t in tex]


# ---- конфигурация полос (строки сдвинутого пространства удвоены; окна - по листам shgrid)
STRIPS_47 = [Strip("S1", (60, 150), (62, 108), (62, 108)),
             Strip("S2", (150, 236), (8, 56), (6, 38), urange=(0, 128)),
             Strip("S3", (190, 285), (72, 108), (90, 120), urange=(0, 128)),
             Strip("S4", (280, 372), (8, 56), (8, 56))]
STRIPS_49 = [Strip("C", (60, 150), (22, 66), (22, 66)),
             Strip("A", (150, 240), (66, 112), (90, 120), urange=(0, 128)),
             Strip("B", (190, 285), (20, 64), (6, 44), urange=(0, 128)),
             Strip("D", (280, 372), (66, 112), (66, 112))]
SIGN = {47: -1, 52: -1, 49: 1, 54: 1}
STRIPS = {47: STRIPS_47, 52: STRIPS_47, 49: STRIPS_49, 54: STRIPS_49}


# ---- узел 48/50: балки по полосам силуэта + блок узла нынешнего кадра, подогнанный под блок классики
KNOT_ROWS = [(68, 131), (165, 228), (200, 263), (293, 356)]   # полосы силуэта 48/50 в сдвинутом пространстве
CUBE_POLY_48 = [(31, 60), (38, 54), (60, 38), (66, 38), (78, 46), (93, 56), (96, 62), (96, 82), (84, 98), (64, 113),
                (56, 111), (46, 101), (36, 93), (31, 88)]
CUBE_SRC_C = (64.0, 76.0)           # центр блока в нынешнем кадре 48
CUBE_DST_C = (58.0, 75.0)           # центр блока классики 48
CUBE_SCALE = (1.30, 1.15)


def poly_mask(poly, h=160, w=128, blur=0.8):
    from PIL import ImageDraw, ImageFilter
    m = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(m).polygon([(x * 4, y * 4) for x, y in poly], fill=255)
    m = m.resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(m, np.float32) / 255.0


def cube_layer(cur, mirror, scale=CUBE_SCALE, dst=CUBE_DST_C):
    """Блок узла из нынешнего кадра: вырезан по многоугольнику, масштаб scale вокруг центра, сдвиг в dst."""
    poly = CUBE_POLY_48
    sc, dc = CUBE_SRC_C, dst
    if mirror:
        poly = [(127 - x, y) for x, y in poly]
        sc = (127 - sc[0], sc[1])
        dc = (127 - dc[0], dc[1])
    m = poly_mask(poly)
    a = cur.astype(np.float32)
    al = a[..., 3] / 255.0 * m
    pm = np.dstack([a[..., :3] * al[..., None], al * 255.0])
    im = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8), "RGBA")
    sx, sy = scale
    # выход(x,y) = источник((x-dc)/s + sc)
    coef = (1 / sx, 0, sc[0] - dc[0] / sx, 0, 1 / sy, sc[1] - dc[1] / sy)
    big = im.transform(im.size, Image.AFFINE, coef, Image.BICUBIC)
    b = np.asarray(big, np.float32)
    al2 = b[..., 3] / 255.0
    rgb = b[..., :3] / np.maximum(al2[..., None], 1e-3)
    return np.clip(rgb, 0, 255), al2


def build_knot(frame):
    """48 (ось вниз-вправо, sign -1, плитки из 47) и 50 (sign +1, плитки из 49)."""
    src = 47 if frame == 48 else 49
    sign = -1 if frame == 48 else 1
    srcsil, _ = classic_sil("MILWAREGHOUL", src)
    tex = build_tiles(load_now("MILWAREGHOUL", src), srcsil, sign, STRIPS[src])
    tex = [(T, P, r0, r1, info) for (T, P, _, _, info), (r0, r1) in zip(tex, KNOT_ROWS)]
    sil, _ = classic_sil("MILWAREGHOUL", frame)
    out, owner, sd = compose(tex, [(0, 128)] * 4, sil, sign)
    beams = finish(out, sign).astype(np.float32)
    cur = load_now("MILWAREGHOUL", frame)
    crgb, cal = cube_layer(cur, mirror=(frame == 50))
    # блок не выходит за силуэт классики (шире на 1 пиксель)
    from scipy.ndimage import maximum_filter
    silb = maximum_filter(sil, size=3)
    cal = cal * np.clip(silb * 1.5, 0, 1)
    ba = beams[..., 3] / 255.0
    oa = cal + ba * (1 - cal)
    orgb = (crgb * cal[..., None] + beams[..., :3] * (ba * (1 - cal))[..., None]) / np.maximum(oa[..., None], 1e-3)
    res = np.dstack([orgb, oa * 255.0])
    res = np.clip(res, 0, 255).astype(np.uint8)
    res[res[..., 3] == 0, :3] = 0
    return res


def load_now(set_name, frame):
    return np.asarray(Image.open(os.path.join(PACK, set_name + ".PCK", "%d.png" % frame)).convert("RGBA"))


def build_straight():
    os.makedirs(OUT, exist_ok=True)
    res = {}
    for fr in (47, 49, 52, 54):
        cur = load_now("MILWAREGHOUL", fr)
        sil, _ = classic_sil("MILWAREGHOUL", fr)
        im, info = fix_beams(cur, sil, SIGN[fr], STRIPS[fr])
        print(fr)
        for s in info:
            print("   ", s)
        res[fr] = Image.fromarray(im, "RGBA")
    return res


TWIN = {47: 48, 48: 49, 49: 50, 50: 51, 52: 53, 54: 55}      # MILWAREGHOUL -> MILWARE (классика наборов побайтно одна)


def build_all():
    os.makedirs(OUT, exist_ok=True)
    r = build_straight()
    for fr in (48, 50):
        r[fr] = Image.fromarray(build_knot(fr), "RGBA")
    for k, v in r.items():
        v.save(os.path.join(OUT, "MILWAREGHOUL_%d.png" % k))
        v.save(os.path.join(OUT, "MILWARE_%d.png" % TWIN[k]))
    return r


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    build_all()
    print("кадры:", OUT)
