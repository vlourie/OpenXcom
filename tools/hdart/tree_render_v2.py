"""TREE_RENDER_V2: исправление V1 по решению специалиста 09.10 - только четыре места, остальное из V1.

  * LAYER CANONICAL: один номер кадра - одна картинка. Кадр берётся из того состояния, где верна его
    собственная верхняя граница или срез, и дальше не меняется:
      42-47 и 53-55 - FULL (MAIN; 53-55 с места на этаже 2, в классике у них среза нет),
      48-52, 56     - Z1_EXPOSED (вид без этажа 2),
      57            - Z0_EXPOSED (вид без этажей 1-2).
    TREE_FULL / TREE_Z1_EXPOSED / TREE_Z0_EXPOSED - только источники, в игру не идут.
  * Срез z1 (FOREST и WASTE) перерисован ТЕМ ЖЕ промптом и сидом V1, но со структурным замком: в свободном
    месте до сигмы release латенты - зашумлённое условие, а в условии там классика вида z<=1 (число, место,
    размер и высота спилов - из классики, модель улучшает только материал). Кадры 53-55 на этаже 1 в замке
    - их канонические картинки, срез рисуется вокруг них.
  * Шов ствола z0 - без генерации: срез ствола V1 переносится по строкам в профиль ствола классики, у шва
    профиль и цвет сходятся к корням MAIN; корни - кадра 57, вторых корней и юбки нет, отрывков рядом нет.
  * Цвет ствола FOREST: сдвиг a*b* (Lab) к красно-бурому классики 57, форма и яркость не меняются.

  tree_render_v2.py --mask-only        холсты замка z1 и лист шва z0, без модели
  tree_render_v2.py [--max-renders 4]  рендер срезов z1 (только через gpuq)
  tree_render_v2.py --assemble         кадры, сборки T1/T1b/T2/T3, листы, ворота, без модели
  --dry                                вместо ответа модели взять условие (контроль тождества, R-299)

Ответы MAIN и CUT_Z0 - из V1 (--v1), не перерисовываются.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.dirname(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw                    # noqa: E402
import cv2                                          # noqa: E402
import probe_object as po                           # noqa: E402
import map_mockup as mm                             # noqa: E402
import tree_render as tr                            # noqa: E402

ENC = "utf-8-sig"
OUT = "census/trees/forest42/render_v2"
V1 = "census/trees/forest42/render_v1"
FULL_FRAMES = (42, 43, 44, 45, 46, 47, 53, 54, 55)
Z1_FRAMES = (48, 49, 50, 51, 52, 56)
LOCK_Z1 = (53, 54, 55)                 # на этаже 1 - канон FULL, срез вокруг них
CUT_SPOT_FRAMES = (48, 50, 51)
BLEND = 40                             # строк x4 над швом, где профиль ствола сходится к корням MAIN
TONE_DECAY = 48                        # строк x4 затухания поправки цвета над швом
TOP_FLAT = 4                           # строк k=1 под спилом, ширина которых держит верх ствола
SEAM_SOFT = 4                          # строк над и под швом z<=0, где волокна ствола размываются в корни
# составной срез z1 (--z1-composite): сдвиги клона тела яруса MAIN (x4) и материал крышек - пень FOREST:58 s2712
CLONE_SHIFTS = ((16, 0), (32, 0), (16, 16), (16, -16), (48, 0), (32, 32), (32, -32), (64, 0))
STUMP_SRC = "census/trees/forest42/render_v1/s2712/stumps/FOREST.PCK/58.png"
def _js(o):
    """numpy-скаляры (bool_, float32) в json."""
    return o.item() if hasattr(o, "item") else str(o)


STRAY_MAX = 400                       # оторванные от ствола куски в кадре 57 меньше этого (пикс x4) - прочь


# ---------------------------------------------------------------- общее

def untone(img, p, amount):
    """Обратное tr.apply_tone: вид (тон MAIN) -> цвета ответа модели, чтобы класть в холст замка."""
    ms, gain, mo = p
    c = np.asarray(img, np.float32).copy()
    k = 1.0 - amount + amount * gain
    c[..., :3] = np.clip((c[..., :3] - amount * (mo - ms * gain)) / k, 0, 255)
    return Image.fromarray(c.astype(np.uint8), "RGBA")


def pos_box(q):
    x, y = q["at"]
    return (x * 4, y * 4, x * 4 + 128, y * 4 + 160)


def frame_from(view, q):
    """Кадр x4: вид под маской рисования куска на его месте."""
    v = np.asarray(view, np.uint8).copy()
    v[..., 3] = (v[..., 3] * tr.rep4(q["draw"])).astype(np.uint8)
    return Image.fromarray(v).crop(pos_box(q))


def place(t, frame, q):
    c = Image.new("RGBA", (t.W * 4, t.H * 4), (0, 0, 0, 0))
    c.paste(frame, pos_box(q)[:2])
    return c


def runs(row):
    out, x, n = [], 0, len(row)
    while x < n:
        if row[x]:
            s = x
            while x < n and row[x]:
                x += 1
            out.append((s, x))
        else:
            x += 1
    return out


def run_at(row, cx):
    """Отрезок строки, содержащий cx или ближайший к нему: (x0, x1) или None."""
    best, bd = None, 1e9
    for a, b in runs(row):
        d = 0 if a <= cx < b else min(abs(cx - a), abs(cx - b + 1))
        if d < bd:
            best, bd = (a, b), d
    return best if bd <= 6 else None


def medfilt(v, k):
    v = np.asarray(v, np.float64)
    h = k // 2
    out = v.copy()
    for i in range(len(v)):
        w = v[max(0, i - h):i + h + 1]
        w = w[~np.isnan(w)]
        out[i] = np.median(w) if len(w) else np.nan
    return out


# ---------------------------------------------------------------- шов ствола z0 (без модели)

def classic_trunk(world, S):
    """Профиль ствола классики 57 в строках x4: x0, x1 (сглажено), верх ствола."""
    a = np.asarray(tr.sprite(world, S, 57), np.int16)
    r, g, al = a[..., 0], a[..., 1], a[..., 3]
    m = (al > 0) & ~(g > r + 8)
    cols = np.where(m.any(0))[0]
    cx = int(round(cols.mean()))
    x0 = np.full(40, np.nan)
    x1 = np.full(40, np.nan)
    for y in range(40):
        rr = run_at(m[y], cx)
        if rr:
            x0[y], x1[y] = rr
    x0, x1 = medfilt(x0, 7), medfilt(x1, 7)
    top = int(np.where(~np.isnan(x0))[0][0])
    ref = top + TOP_FLAT                # спил сверху уже ствола на пиксель-два: в HD это «губа», держим ширину
    x0[top:ref] = np.minimum(x0[top:ref], x0[ref])
    x1[top:ref] = np.maximum(x1[top:ref], x1[ref])
    X0 = np.repeat(x0, 4) * 4
    X1 = np.repeat(x1, 4) * 4
    return X0, X1, top * 4, cx * 4 + 2


def z0_trunk(job, world, v0, v2):
    """v0, v2 - виды x4 холста (V1 z<=0 и MAIN). Возвращает новый v0 и числа шва."""
    t = job.tree
    i57 = next(i for i, q in enumerate(t.pcs) if q["f"] == 57)
    q = t.pcs[i57]
    bx = pos_box(q)
    U, own, _F = job.masks(0)
    R = (tr.rep4(U) & (tr.rep4(own) == 0))[bx[1]:bx[3], bx[0]:bx[2]]
    c0 = np.asarray(v0, np.float32)[bx[1]:bx[3], bx[0]:bx[2]].copy()
    c2 = np.asarray(v2, np.float32)[bx[1]:bx[3], bx[0]:bx[2]]
    X0, X1, Tc, cx = classic_trunk(world, job.S)
    tcols = [x for x in range(128) if np.nanmin(X0) <= x < np.nanmax(X1)]
    seamcol = np.array([np.where(R[:, x])[0].max() if R[:, x].any() else -1 for x in range(128)])
    Ys = int(np.median([seamcol[x] for x in tcols if seamcol[x] >= 0]))
    # корни MAIN под швом
    ms = []
    # первые две строки: корни сразу расходятся, среднее по шести давало ствол шире корней - заплечик
    for y in range(Ys + 1, min(160, Ys + 3)):
        rr = run_at(c2[y, :, 3] > 128, cx)
        if rr:
            ms.append(rr)
    m0, m1 = np.mean([a for a, _ in ms]), np.mean([b for _, b in ms])
    # источник: срез ствола V1, только чистая часть (без юбки у корней)
    sx0 = np.full(160, np.nan)
    sx1 = np.full(160, np.nan)
    for y in range(0, Ys + 1):
        if not R[y].any():
            continue
        rr = run_at(c0[y, :, 3] > 128, (m0 + m1) / 2 if y > Ys - 8 else cx)
        if rr and rr[1] - rr[0] >= 10:
            sx0[y], sx1[y] = rr
    have = np.where(~np.isnan(sx0))[0]
    Tcut = int(have[0])
    sx0, sx1 = medfilt(sx0, 9), medfilt(sx1, 9)
    wid = sx1 - sx0
    mid = Tcut + (Ys - Tcut) // 2
    wmed = float(np.nanmedian(wid[Tcut + 4:mid]))
    Bcut = Ys
    for y in range(int(Tcut + 0.4 * (Ys - Tcut)), Ys + 1):
        if not np.isnan(wid[y]) and wid[y] > 1.25 * wmed:
            Bcut = y - 1
            break
    # края источника - прямая (устойчиво, без выбросов): скачок края у основания сучка
    # иначе сдвигает фактуру строк и даёт ступень поперёк ствола
    yy = np.arange(Tcut, Bcut + 1)
    for arr in (sx0, sx1):
        ok = ~np.isnan(arr[yy])
        ya, va = yy[ok], arr[yy][ok]
        for _ in range(3):
            p = np.polyfit(ya, va, 1)
            r = np.abs(np.polyval(p, ya) - va)
            sel = r <= max(2.0, 2.5 * float(np.median(r)))
            ya, va = ya[sel], va[sel]
        arr[yy] = np.polyval(p, yy)
    # карта переноса: строка цели -> строка источника, x цели -> x источника
    # только до шва: ниже Ys - корни MAIN (копия строки шва вниз дала плоскую полосу-ступеньку)
    mapx = np.full((160, 128), -1, np.float32)
    mapy = np.full((160, 128), -1, np.float32)
    tx0s, tx1s = np.full(160, np.nan), np.full(160, np.nan)
    for y in range(Tc, Ys + 1):
        yc = y
        wb = np.clip((yc - (Ys - BLEND)) / BLEND, 0.0, 1.0)
        tx0 = (1 - wb) * X0[yc] + wb * m0
        tx1 = (1 - wb) * X1[yc] + wb * m1
        if np.isnan(X0[yc]) or np.isnan(X1[yc]):
            continue
        ysrc = Tcut + (yc - Tc) * (Bcut - Tcut) / max(1, Ys - Tc)
        yi = int(round(ysrc))
        a, b = sx0[yi], sx1[yi]
        if np.isnan(a):
            continue
        tx0s[y], tx1s[y] = tx0, tx1
        xs = np.arange(128, dtype=np.float32)
        mapx[y] = a + (xs - tx0) * (b - a) / (tx1 - tx0)
        mapy[y] = ysrc
    pm = c0.copy()
    # источник - только сам ствол в строке (sx0..sx1 с полутора пикселями мягкого края):
    # основания веток V1 левее и правее перенос иначе вытягивает за край нового ствола
    xs1 = np.arange(128, dtype=np.float32)
    for y in range(160):
        if np.isnan(sx0[y]):
            continue
        d = np.maximum(sx0[y] - xs1, xs1 - sx1[y])
        pm[y, :, 3] *= np.clip(1.5 - d, 0.0, 1.0)
    pm[..., :3] *= pm[..., 3:4] / 255.0
    warped = cv2.remap(pm, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    valid = mapx >= 0
    warped[~valid] = 0
    # только то, что связано со стволом: обрывки рядом - прочь
    core = np.zeros((160, 128), bool)
    for y in range(160):
        if not np.isnan(tx0s[y]):
            core[y, int(tx0s[y]) + 2:int(tx1s[y]) - 2] = True
    n, lab = cv2.connectedComponents((warped[..., 3] > 32).astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[np.unique(lab[core & (warped[..., 3] > 32)])] = True
    keep[0] = False
    warped[~keep[lab]] = 0
    al = warped[..., 3:4]
    rgb = np.where(al > 0, warped[..., :3] / np.maximum(al, 1e-3) * 255.0, 0)
    # цвет у шва - к корням MAIN, затухает вверх
    up = np.zeros((160, 128), bool)
    dn = np.zeros((160, 128), bool)
    for y in range(Ys - 8, Ys + 1):
        if not np.isnan(tx0s[y]):
            up[y, int(tx0s[y]) + 4:int(tx1s[y]) - 4] = True
    for y in range(Ys + 1, min(160, Ys + 9)):
        dn[y, int(m0) + 4:int(m1) - 4] = True
    up &= al[..., 0] > 200
    dn &= c2[..., 3] > 200
    off = c2[..., :3][dn].mean(0) - rgb[up].mean(0) if up.any() and dn.any() else np.zeros(3)
    yy = np.arange(160, dtype=np.float32)[:, None, None]
    w = np.clip(1.0 - (Ys - yy) / TONE_DECAY, 0.0, 1.0)
    rgb = rgb + off * w
    # у самого шва - плавно в строку корней ниже
    row = c2[min(159, Ys + 1)]
    for y in range(Ys - 5, Ys + 1):
        k = 0.5 * (y - (Ys - 6)) / 6.0
        ok = (row[:, 3] > 128) & (al[y, :, 0] > 128)
        rgb[y][ok] = rgb[y][ok] * (1 - k) + row[:, :3][ok] * k
    out = c0.copy()
    # полоса ствола целиком (не только R): иначе выше R остаётся край среза V1 - ступенька под спилом.
    # зелёное V1 (сучок) вне нового ствола оставляем
    Rb = R.copy()
    for y in range(160):
        if not np.isnan(tx0s[y]):
            Rb[y, max(0, int(tx0s[y]) - 8):min(128, int(tx1s[y]) + 8)] = True
    # только яркая листва: оливковый край ствола V1 (g чуть больше r) - не сучок, иначе нитка вдоль ствола
    green = (c0[..., 1] > c0[..., 0] + 30) & (c0[..., 1] > c0[..., 2] + 20) & (c0[..., 3] > 32) & (al[..., 0] <= 32)
    Rb &= ~green
    out[Rb] = 0
    newp = np.concatenate([np.clip(rgb, 0, 255), al], -1)
    out[Rb] = newp[Rb]
    # ниже шва область среза V1 - корни кадра 57 из MAIN как есть
    below = R.copy()
    below[:Ys + 1] = False
    out[below] = c2[below]
    # сам шов: волокна ствола обрываются на строке Ys - размыть по вертикали +-SEAM_SOFT строк, только внутри ствола
    lo, hi = Ys - SEAM_SOFT, min(159, Ys + SEAM_SOFT + 1)
    band = out[lo - 3:hi + 4].copy()
    sm = cv2.GaussianBlur(band, (1, 7), sigmaX=0.1, sigmaY=1.5)
    for y in range(lo, hi + 1):
        j = y - (lo - 3)
        w = 1.0 - abs(y - Ys - 0.5) / (SEAM_SOFT + 1)
        ok = (out[y, :, 3] > 200) & (out[max(0, y - 1), :, 3] > 200) & (out[min(159, y + 1), :, 3] > 200)
        out[y, ok, :3] = out[y, ok, :3] * (1 - w) + sm[j, ok, :3] * w
    # оторванные обрывки во всём кадре 57 (не только в R): кусок, не связанный со стволом и корнями, - прочь
    n, lab, st, _c = cv2.connectedComponentsWithStats((out[..., 3] > 32).astype(np.uint8), connectivity=8)
    stray = 0
    if n > 2:
        big = 1 + int(np.argmax(st[1:, 4]))
        for j in range(1, n):
            if j != big and st[j, 4] < STRAY_MAX:
                out[lab == j] = 0
                stray += int(st[j, 4])
    v = np.asarray(v0, np.uint8).copy()
    v[bx[1]:bx[3], bx[0]:bx[2]] = out.astype(np.uint8)
    info = dict(seam_row=Ys, classic_top=Tc, cut_top=Tcut, cut_clean_bottom=Bcut,
                main_at_seam=[round(m0, 1), round(m1, 1)], classic_cx=cx, stray_px_removed=stray, colour_offset=[round(float(o), 1) for o in off])
    return Image.fromarray(v), info


def even_rows(world, S, view, q, Ys, sigma=10.0):
    """Полосы поперёк ствола z<=0: перенос растягивает строки V1 (основание сучка) в полосу цвета.
    Средний цвет середины ствола по строкам сводится к сглаженному (гаусс по строкам), прибавкой -
    фактура остаётся. Только от верха ствола до BLEND над швом: ниже цвет уже ведётся к корням MAIN.
    Возвращает вид и наибольшую снятую поправку (по каналу)."""
    X0, X1, Tc, _cx = classic_trunk(world, S)
    bx = pos_box(q)
    v = np.asarray(view, np.float32).copy()
    c = v[bx[1]:bx[3], bx[0]:bx[2]]
    y1 = Ys - BLEND // 2
    ys = np.arange(Tc, y1 + 1)
    means = np.full((len(ys), 3), np.nan)
    for i, y in enumerate(ys):
        a, b = int(X0[y]) + 4, int(X1[y]) - 4
        seg = c[y, a:b]
        ok = (seg[:, 3] > 200) & ~(seg[:, 1] > seg[:, 0] + 30)
        if ok.sum() > 8:
            means[i] = seg[ok, :3].mean(0)
    good = ~np.isnan(means[:, 0])
    if good.sum() < 10:
        return view, 0.0
    for ch in range(3):
        means[~good, ch] = np.interp(ys[~good], ys[good], means[good, ch])
    # гаусс ступень только размазывает (половина остаётся у самой ступени) - ведём к кубике по строкам
    smooth = np.stack([np.polyval(np.polyfit(ys[good], means[good, ch], 3), ys) for ch in range(3)], 1)
    off = smooth - means
    # к низу поправка затухает до нуля, чтобы не ломать подход цвета к корням
    fade = np.clip((y1 - ys) / 12.0, 0.0, 1.0)[:, None]
    off *= fade
    for i, y in enumerate(ys):
        m = (c[y, :, 3] > 0) & ~(c[y, :, 1] > c[y, :, 0] + 30)
        c[y, m, :3] = np.clip(c[y, m, :3] + off[i], 0, 255)
    v[bx[1]:bx[3], bx[0]:bx[2]] = c
    return Image.fromarray(v.astype(np.uint8), "RGBA"), round(float(np.abs(off).max()), 1)


def seam_numbers(view, q, Ys, cx):
    """Ствол у шва в виде z<=0: скачок ширины и цвета между 4 строками над швом и 4 под ним."""
    c = np.asarray(view, np.float32)[pos_box(q)[1]:pos_box(q)[3], pos_box(q)[0]:pos_box(q)[2]]

    def band(ys):
        ws, cols = [], []
        for y in ys:
            rr = run_at(c[y, :, 3] > 128, cx)
            if rr:
                ws.append(rr[1] - rr[0])
                cols.append(c[y, rr[0] + 3:rr[1] - 3, :3].mean(0))
        return (np.mean(ws), np.mean(cols, 0)) if ws else (np.nan, np.full(3, np.nan))
    wa, ca = band(range(Ys - 3, Ys + 1))
    wb, cb = band(range(Ys + 1, Ys + 5))
    return dict(width_above=round(float(wa), 1), width_below=round(float(wb), 1),
                width_jump=round(float(abs(wa - wb)), 1), colour_step=round(float(np.abs(ca - cb).max()), 1))


# ---------------------------------------------------------------- цвет ствола FOREST

def trunk_weight(rgb):
    r, g = rgb[..., 0], rgb[..., 1]
    return np.clip(1.0 - (g - r + 4.0) / 12.0, 0.0, 1.0)     # 1 там, где g <= r-4, 0 при g >= r+8


def lab_of(rgb):
    return cv2.cvtColor((rgb / 255.0).astype(np.float32)[None], cv2.COLOR_RGB2LAB)[0]


def trunk_shift(world, S, v0, q):
    """Сдвиг a*b* (Lab): классика 57 (не зелёное) минус ствол HD в кадре 57 вида z<=0."""
    a = np.asarray(tr.sprite(world, S, 57), np.float32)
    m = (a[..., 3] > 0) & ~(a[..., 1] > a[..., 0] + 8)
    lc = lab_of(a[..., :3][m])
    c = np.asarray(v0, np.float32)[pos_box(q)[1]:pos_box(q)[3], pos_box(q)[0]:pos_box(q)[2]]
    sel = c[..., 3] > 200
    rgb = c[..., :3][sel]
    w = trunk_weight(rgb)
    lh = lab_of(rgb)
    mh = (lh[:, 1:] * w[:, None]).sum(0) / max(w.sum(), 1e-3)
    return lc[:, 1:].mean(0) - mh, dict(classic_ab=[round(float(v), 1) for v in lc[:, 1:].mean(0)],
                                       hd_ab=[round(float(v), 1) for v in mh])


def recolour(view, mask4, d_ab):
    v = np.asarray(view, np.float32).copy()
    sel = mask4 & (v[..., 3] > 0)
    rgb = v[..., :3][sel]
    lab = lab_of(rgb)
    w = trunk_weight(rgb)
    lab[:, 1:] += d_ab[None] * w[:, None]
    back = cv2.cvtColor(lab[None], cv2.COLOR_LAB2RGB)[0] * 255.0
    v[..., :3][sel] = np.clip(back, 0, 255)
    return Image.fromarray(v.astype(np.uint8), "RGBA")


# ---------------------------------------------------------------- модель: замок со структурой

def paint_locked2(painter, args, known, cond, free, what, seed, release):
    """tr.paint_locked плюс структурный замок: в свободном месте, пока сигма выше release, латенты - зашумлённое
    условие (классика вида), дальше модель свободна; вне free - как V1, зашумлённый известный холст."""
    torch = painter.torch
    pipe = painter.pipe
    dev = pipe._execution_device
    W, H = known.size
    hl, wl = H // 16, W // 16

    def enc(img):
        with torch.no_grad():
            t = pipe.image_processor.preprocess(img.convert("RGBA"), H, W).unsqueeze(2).to(dev, pipe.vae.dtype)
            lat = pipe._encode_vae_image(t, generator=None)
            return pipe._pack_latents(lat, 1, lat.shape[1], lat.shape[3], lat.shape[4]).to(torch.bfloat16)
    init = enc(known)
    clat = enc(cond)
    if init.shape[1] != hl * wl:
        raise SystemExit("латентов %d, маска %d (%dx%d)" % (init.shape[1], hl * wl, wl, hl))
    g = torch.Generator("cuda").manual_seed(seed + 1)
    noise = torch.randn(init.shape, generator=g, device=dev, dtype=torch.float32).to(init.dtype)
    m = torch.from_numpy(free.reshape(1, -1, 1).astype(np.float32)).to(dev, init.dtype)

    def cb(pp, i, _t, kw):
        x = kw["latents"]
        sg = float(pp.scheduler.sigmas[i + 1])
        noised = sg * noise + (1.0 - sg) * init
        fr = x.to(init.dtype)
        if sg > release:
            fr = sg * noise + (1.0 - sg) * clat
        return {"latents": (m * fr + (1.0 - m) * noised).to(x.dtype)}

    kw = {"prompt": po.STYLE["strict"].replace("{what}", what), "num_inference_steps": args.steps,
          "image": cond, "generator": torch.Generator("cuda").manual_seed(seed),
          "negative_prompt": po.gen_fire.NEGATIVE, "true_cfg_scale": args.cfg, "width": W, "height": H,
          "callback_on_step_end": cb, "callback_on_step_end_tensor_inputs": ["latents"]}
    miss = [k for k in ("image", "negative_prompt", "true_cfg_scale", "callback_on_step_end")
            if k not in painter.accepts]
    if miss:
        raise SystemExit("конвейер не принимает %s" % miss)
    with torch.no_grad():
        return pipe(**kw).images[0].convert("RGB")


# ---------------------------------------------------------------- одно дерево

class Job2(tr.Job):
    def __init__(self, world, CL, hints, S, seed, args):
        a1 = argparse.Namespace(**vars(args))
        a1.out = args.v1
        super().__init__(world, CL, hints, S, seed, a1)
        self.args = args
        self.world = world
        self.d2 = os.path.join(args.out, "s%d" % seed, S)
        os.makedirs(self.d2, exist_ok=True)

    def raw_z1(self, rel):
        return os.path.join(self.d2, "raw_cut_z1_r%02d.png" % round(rel * 100))

    def base(self):
        """MAIN, вид z<=0 (V1 срез -> шов), перекраска ствола, канон FULL и Z0. Без модели."""
        t, b, args = self.tree, self.box, self.args
        hd, g, tp, main = self.main_cut()
        self._g, self._hd, self._tp = g, hd, tp
        canvas = lambda body: tr.paste4(body, b, t)       # noqa: E731
        v2 = canvas(main)
        raw0 = Image.open(self.raw_cut(0)).convert("RGB")
        cut0 = tr.apply_tone(tr.limit_alpha(tr.to_body(raw0, g), self.frame_z(0), args.grow), tp, args.tone)
        cut0 = np.asarray(canvas(cut0), np.uint8)
        U0, own0, _F = self.masks(0)
        U4, own4 = tr.rep4(U0), tr.rep4(own0)
        v = np.asarray(v2, np.uint8).copy()
        v[U4 & (own4 == 0)] = cut0[U4 & (own4 == 0)]
        v[U4 & (own4 < 0)] = 0
        v0_v1 = Image.fromarray(v)
        v0, zinfo = z0_trunk(self, self.world, v0_v1, v2)
        i57 = next(i for i, q in enumerate(t.pcs) if q["f"] == 57)
        q57 = t.pcs[i57]
        info = dict(z0=zinfo)
        info["z0"]["seam_v1"] = seam_numbers(v0_v1, q57, zinfo["seam_row"], zinfo["classic_cx"])
        if self.S == "FOREST" and args.recolour:
            d_ab, cinfo = trunk_shift(self.world, self.S, v0, q57)
            cinfo["shift_ab"] = [round(float(x), 1) for x in d_ab]
            info["trunk_colour"] = cinfo
            # z<=0: в рамке только кадр 57 - красим всю рамку (силуэт классики ниже верха HD-ствола: полоса цвета)
            m57 = np.zeros((v0.height, v0.width), bool)
            b57 = pos_box(q57)
            m57[b57[1]:b57[3], b57[0]:b57[2]] = True
            v0 = recolour(v0, m57, d_ab)
            v2 = recolour(v2, tr.rep4(t.lab[2] == i57), d_ab)
        v0, info["z0"]["row_band_max"] = even_rows(self.world, self.S, v0, q57, zinfo["seam_row"])
        if self.S in ("FOREST", "FOREST_WASTE") and args.recolour:
            v0, v2, info["f57"] = f57_details(self, v0, v2, q57, i57, shift=self.S == "FOREST")
        info["z0"]["seam_v2"] = seam_numbers(v0, q57, zinfo["seam_row"], zinfo["classic_cx"])
        frames, src = {}, {}
        for q in t.pcs:
            f = q["f"]
            if f in FULL_FRAMES and q["z"] == t.top:
                frames[f], src[f] = frame_from(v2, q), "FULL"
            elif f == 57:
                frames[f], src[f] = frame_from(v0, q), "Z0_EXPOSED"
        self.v0, self.v2, self.q57 = v0, v2, q57
        return frames, src, info

    def lock_z1(self, frames):
        """Холст x4: канон 53-55 на их местах этажа 1 (там, где в виде z<=1 владеют они) и маска замка."""
        t = self.tree
        c = np.zeros((t.H * 4, t.W * 4, 4), np.uint8)
        for j, q in enumerate(t.pcs):
            if q["z"] == 1 and q["f"] in LOCK_Z1:
                own = tr.rep4(t.lab[1] == j)
                p = np.asarray(place(t, frames[q["f"]], q), np.uint8)
                c[own] = p[own]
        return c, c[..., 3] >= 128

    def canvases1(self, frames):
        """Холст замка, условие и свободные клетки для CUT_Z1 (холст ответа MAIN)."""
        t, b, g, tp, hd, args = self.tree, self.box, self._g, self._tp, self._hd, self.args
        U, own, F = self.masks(1)
        lockc, lock4 = self.lock_z1(frames)

        def body(m4):
            return m4[b[1] * 4:b[3] * 4, b[0] * 4:b[2] * 4]
        bg = np.array([round(v) for v in g["bg"]], np.uint8)

        def to_raw(view4):
            """вид x4 (тон MAIN) -> холст ответа, подложка там, где прозрачно."""
            im = untone(Image.fromarray(body(np.asarray(view4, np.uint8))), tp, args.tone)
            flat = Image.new("RGBA", im.size, tuple(int(v) for v in bg) + (255,))
            flat.alpha_composite(im)
            return np.asarray(tr.body_to_raw(flat, g, Image.LANCZOS).convert("RGB"))
        U_r = tr.mask_raw(self.body4(U), g)
        known = np.asarray(hd, np.uint8).copy()
        known[U_r] = bg
        m0 = tr.mask_raw(self.body4(U & (own == 0)), g)
        known[m0] = to_raw(self.v0)[m0]
        L_r = tr.mask_raw(body(lock4), g)
        known[L_r] = to_raw(lockc)[L_r]
        cls = tr.xbrz(self.frame_z(1))
        flat = Image.new("RGBA", cls.size, tuple(int(v) for v in bg) + (255,))
        flat.alpha_composite(cls)
        cls_r = np.asarray(tr.body_to_raw(flat, g, Image.LANCZOS).convert("RGB"))
        F_r = tr.mask_raw(self.body4(F), g) & ~L_r
        cond = known.copy()
        cond[F_r] = cls_r[F_r]
        W, H = hd.size
        hl, wl = H // 16, W // 16
        f = cv2.resize(F_r.astype(np.float32), (wl, hl), interpolation=cv2.INTER_AREA) > 0
        lk = cv2.resize(L_r.astype(np.float32), (wl, hl), interpolation=cv2.INTER_AREA) > 0.5
        free = (cv2.dilate(f.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & ~lk
        return Image.fromarray(known), Image.fromarray(cond), free, F_r, lockc, lock4

    def view1(self, raw1, lockc, lock4):
        """Вид z<=1 x4: MAIN; на U_1 срез (куски этажа 1), вид z<=0 (кусок 57); канон 53-55 везде, где владеют."""
        t, b, g, tp, args = self.tree, self.box, self._g, self._tp, self.args
        cut = tr.apply_tone(tr.limit_alpha(tr.to_body(raw1, g), self.frame_z(1), args.grow), tp, args.tone)
        cut4 = np.asarray(tr.paste4(cut, b, t), np.uint8)
        U, own, _F = self.masks(1)
        U4, own4 = tr.rep4(U), tr.rep4(own)
        own53 = np.zeros_like(U4)
        for j, q in enumerate(t.pcs):
            if q["z"] == 1 and q["f"] in LOCK_Z1:
                own53 |= tr.rep4(t.lab[1] == j)
        v = np.asarray(self.v2, np.uint8).copy()
        m = U4 & (own4 == 1) & ~own53
        v[m] = cut4[m]
        m = U4 & (own4 == 0)
        v[m] = np.asarray(self.v0, np.uint8)[m]
        v[U4 & (own4 < 0)] = 0
        v[own53] = lockc[own53]
        return Image.fromarray(v), cut4

    def own53(self):
        t = self.tree
        m = np.zeros((t.H * 4, t.W * 4), bool)
        for j, q in enumerate(t.pcs):
            if q["z"] == 1 and q["f"] in LOCK_Z1:
                m |= tr.rep4(t.lab[1] == j)
        return m

    def z1_composite(self, seed_noise=7):
        """Срез z<=1 без модели (решение 09.10): хвоя и ветки - из MAIN, классика - только маска и места спилов.

        Земля кадров Z1_EXPOSED (под верхом и вне его): MAIN без ограничения силуэтом полного кадра, дыры
        внутри силуэта зоны - клон тела яруса MAIN со сдвигом вниз; альфа - гладкий силуэт классики z<=1,
        кромка растворяется пучками хвои; крышки спилов - по пятнам классики (число, место, размер),
        материал - древесина пня HD и кора ствола HD, RGB классики в срез не идёт. Возвращает x4 RGBA и землю.
        """
        t, b = self.tree, self.box
        U, own, F = self.masks(1)
        U4, own4 = tr.rep4(U), tr.rep4(own)
        main = np.asarray(self.v2, np.float32)
        H, W = main.shape[:2]
        sil = np.asarray(tr.sil_limit(self.frame_z(1), 2), np.float32)
        S4 = np.zeros((H, W), np.float32)
        S4[b[1] * 4:b[3] * 4, b[0] * 4:b[2] * 4] = sil
        zone = U4 & (own4 == 1)
        z1e = [j for j, q in enumerate(t.pcs) if q["z"] == 1 and q["f"] not in LOCK_Z1]
        terr = tr.rep4(np.isin(t.lab[1], z1e) | (t.lab[1] < 0)) & ~(U4 & (own4 < 0))
        # 1) хвоя: MAIN без limit_alpha (квадратная кайма MaxFilter давала прямоугольные вырезы)
        raw = tr.apply_tone(tr.to_body(self._hd, self._g), self._tp, self.args.tone)
        mraw = np.asarray(tr.paste4(raw, b, t), np.float32)
        col = np.where(terr[..., None], mraw[..., :3], main[..., :3])
        asrc = np.where(terr, mraw[..., 3], main[..., 3]) / 255.0
        fcol, fa = col.copy(), asrc.copy()
        have = (asrc > 0.8) | ~terr
        for dy, dx in CLONE_SHIFTS:
            sh = np.roll(np.roll(main, -dy, 0), -dx, 1)
            ok = (~have) & (sh[..., 3] > 230)
            fcol[ok] = sh[..., :3][ok]
            fa[ok] = sh[..., 3][ok] / 255.0
            have |= ok
        # заплатка только в зоне среза, вес плавный: граница зоны - блоки 4x4
        wf = np.clip((cv2.GaussianBlur(zone.astype(np.float32), (0, 0), 6.0) - 0.25) / 0.5, 0, 1)
        col = col + (fcol - col) * wf[..., None]
        asrc = asrc + (fa - asrc) * wf
        # слабая альфа ответа - подложка, а не хвоя (R-089)
        asrc = np.where(terr, np.clip((asrc - 0.35) / 0.5, 0, 1), asrc)
        # цвет полупрозрачной кромки - с плотных соседей (светлый пунктир - подложка в краю ответа)
        dense = asrc > 0.95
        for _ in range(6):
            cnt = cv2.blur(dense.astype(np.float32), (3, 3))
            acc = np.stack([cv2.blur(np.where(dense, col[..., c], 0).astype(np.float32), (3, 3))
                            for c in range(3)], -1)
            add = (~dense) & (cnt > 0)
            col[add] = acc[add] / cnt[add][:, None]
            dense = dense | add
        Y = col.mean(-1)
        # 2) альфа: знаковое расстояние до силуэта классики z<=1, сдвиг +-2.5 пикс по пучкам хвои
        inside = (S4 > 0.5).astype(np.uint8)
        sd = cv2.distanceTransform(inside, cv2.DIST_L2, 5) - cv2.distanceTransform(1 - inside, cv2.DIST_L2, 5)
        sd = cv2.GaussianBlur(sd.astype(np.float32), (0, 0), 4.0)
        tuft = cv2.GaussianBlur(Y, (0, 0), 1.5) - cv2.GaussianBlur(Y, (0, 0), 6)
        alpha = asrc * np.clip((sd + 2.5 * np.clip(tuft / 14.0, -1, 1)) / 1.6 + 0.5, 0, 1)
        # оторванные клочки прочь: на земле Z1 - только связное с телом дерева
        solid = ((alpha > 0.35) & terr) | ((main[..., 3] > 128) & ~terr)
        n, lb, stt, _c = cv2.connectedComponentsWithStats(solid.astype(np.uint8), 8)
        scraps = 0
        if n > 1:
            big = 1 + int(np.argmax(stt[1:, 4]))
            keep = cv2.dilate((lb == big).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            scraps = int((terr & ~keep & (alpha > 0.5)).sum())
            alpha[terr & ~keep] = 0
        alpha[~terr] = main[..., 3][~terr] / 255.0
        # 3) свет верха среза - скалярный множитель к классике, к границе зоны 1
        cl4 = np.asarray(t.compose(1, 4), np.float32)
        inner = zone & (S4 > 0.5)
        yc = cl4[..., :3].mean(-1)[inner & (cl4[..., 3] > 128)].mean()
        gain = float(np.clip(yc / max(Y[inner].mean(), 1), 0.85, 1.35))
        wg = np.clip(cv2.distanceTransform(zone.astype(np.uint8), cv2.DIST_L2, 3) / 24.0, 0, 1)
        col = col * (1 + (gain - 1) * wg)[..., None]
        # 4) крышки спилов: место и размер - пятна классики, материал - пень и кора HD
        st = np.asarray(Image.open(STUMP_SRC).convert("RGBA"), np.float32)
        wood = _lab8(st[(st[..., 3] > 200) & (st[..., :3].mean(-1) > 60)][:, :3])
        bx = pos_box(self.q57)
        tr57 = np.asarray(self.v0, np.float32)[bx[1]:bx[1] + 120, bx[0]:bx[2]]
        tm = (tr57[..., 3] > 200) & (np.abs(tr57[..., 1] - tr57[..., 0]) < 40) & (tr57[..., 0] >= tr57[..., 1])
        bm = _lab8(tr57[tm][:, :3]).mean(0)
        rng = np.random.default_rng(seed_noise)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        L0 = float(np.percentile(wood[:, 0], 60))
        caps = []
        out0 = np.concatenate([np.clip(col, 0, 255), (np.clip(alpha, 0, 1) * 255)[..., None]], -1).astype(np.uint8)
        capown = np.full((H, W), -1, np.int32)      # чья крышка: кусок яруса, где центр пятна классики
        for s in classic_spots(self):
            tgt = _lab8(s["mean"][None])[0]
            cx, cy = s["c"][0] * 4 + 2, s["c"][1] * 4 + 2
            rx, ry = max(s["w"] * 1.9, 3.5), max(s["h"] * 1.9, 2.5)
            box, crgb, wcap, rr = wood_face(xx, yy, cx, cy, rx, ry, L0, tgt[1:], bm, rng,
                                            self.S == "FOREST_WASTE")
            # иглы MAIN перекрывают внешний край крышки там, где у хвои светлый пучок
            wcap = wcap * (1 - np.clip((tuft - 2.0) / 6.0, 0, 1) * np.clip((rr - 0.72) / 0.28, 0, 1))
            wb = wcap[box][..., None]
            col[box] = col[box] * (1 - wb) + crgb * wb
            alpha[box] = np.maximum(alpha[box], wcap[box])
            j = int(t.lab[1][int(round(s["c"][1])), int(round(s["c"][0]))])
            capown[box & (wcap > 0)] = j
            caps.append([s["x"], s["y"], s["w"], s["h"], s["area"], j])
        out = np.concatenate([np.clip(col, 0, 255), (np.clip(alpha, 0, 1) * 255)[..., None]], -1).astype(np.uint8)
        return out, terr, dict(light_gain=round(gain, 3), caps_classic=caps, scraps_cut=scraps), out0, capown

    def view1_comp(self, comp, terr, lockc):
        """Вид z<=1 x4 по составному срезу: земля Z1 - срез, кусок 57 - вид z<=0, канон 53-55 на месте."""
        U, own, _F = self.masks(1)
        U4, own4 = tr.rep4(U), tr.rep4(own)
        v = np.asarray(self.v2, np.uint8).copy()
        v[terr] = comp[terr]
        m = U4 & (own4 == 0)
        v[m] = np.asarray(self.v0, np.uint8)[m]
        v[U4 & (own4 < 0)] = 0
        o53 = self.own53()
        v[o53] = lockc[o53]
        return Image.fromarray(v)


def f57_details(job, v0, v2, q57, i57, iters=3, shift=True):
    """Кадр 57 без модели (решение 09.10): ствол FOREST к пурпурно-бурому классики (остаток сдвига a*b* дожат),
    торец спила на верху HD-ствола (древесина пня HD, оттенок - торец классики), ветки - линии корой по
    пикселям веток классики (вне HD-ствола, выше корней), у FOREST на них хвоя MAIN по зелёным пятнам
    классики. Силуэт ствола и корней не меняется: торец только внутри непрозрачного, ветки только снаружи."""
    t = job.tree
    b57 = pos_box(q57)
    m57 = np.zeros((v0.height, v0.width), bool)
    m57[b57[1]:b57[3], b57[0]:b57[2]] = True
    own2 = tr.rep4(t.lab[2] == i57)
    res = []
    for _ in range(iters if shift else 0):      # вес trunk_weight < 1 недодаёт сдвиг - дожать остаток
        d_ab, ci = trunk_shift(job.world, job.S, v0, q57)
        res.append(ci["hd_ab"])
        if np.hypot(*d_ab) < 0.5:
            break
        v0 = recolour(v0, m57, d_ab)
        v2 = recolour(v2, own2, d_ab)
    _d, ci = trunk_shift(job.world, job.S, v0, q57)
    out = dict(trunk_ab_iter=res, trunk_ab_final=ci["hd_ab"], classic_ab=ci["classic_ab"])
    v = np.asarray(v0, np.float32).copy()
    fr = v[b57[1]:b57[3], b57[0]:b57[2]]        # вид, не копия: правки идут в v
    cl = np.asarray(tr.sprite(job.world, job.S, 57), np.int16)
    # торец: верх HD-ствола, ширина - ствол на 8 строк ниже верха
    a = fr[..., 3]
    rows = np.where((a > 200).sum(1) >= 8)[0]
    ht = int(rows[0])
    xs = np.where(a[ht + 8] > 200)[0]
    mid = int(np.median(xs))
    run = xs[np.abs(xs - mid) <= 64]
    x0, x1 = int(run.min()), int(run.max())
    clt = int(np.where(cl[..., 3].any(1))[0][0])
    top = cl[clt:clt + 4]
    om = (top[..., 3] > 0) & (top[..., 0] > top[..., 1] + 25)
    face_lab = _lab8(top[..., :3][om].astype(np.float32)).mean(0)
    st = np.asarray(Image.open(STUMP_SRC).convert("RGBA"), np.float32)
    wood = _lab8(st[(st[..., 3] > 200) & (st[..., :3].mean(-1) > 60)][:, :3])
    L0 = float(np.percentile(wood[:, 0], 60))
    tm = (a > 200) & (fr[..., 0] >= fr[..., 1])
    bm = _lab8(fr[..., :3][tm]).mean(0)
    rx = (x1 - x0) / 2.0 - 2.0
    ry = max(rx * 0.32, 5.0)
    cx, cy = (x0 + x1) / 2.0, ht + ry + 1.0
    yy, xx = np.mgrid[0:fr.shape[0], 0:fr.shape[1]].astype(np.float32)
    rng = np.random.default_rng(57)
    box, crgb, wcap, _rr = wood_face(xx, yy, cx, cy, rx, ry, L0, face_lab[1:], bm, rng)
    wcap = wcap * np.clip((a - 200) / 55.0, 0, 1)          # только внутри непрозрачного: силуэт прежний
    wb = wcap[box][..., None]
    fr[..., :3][box] = fr[..., :3][box] * (1 - wb) + crgb * wb
    out["cut_face"] = dict(top_row_x4=ht, x=[x0, x1], rx=round(rx, 1), ry=round(ry, 1),
                           ab=[round(float(face_lab[1] - 128), 1), round(float(face_lab[2] - 128), 1)])
    # веточки: зелёные пятна классики x4 (мягкий край), хвоя - клон MAIN с лучшим сдвигом
    gm = (cl[..., 3] > 0) & (cl[..., 1] > cl[..., 0] + 8)
    n, lb, sts, cen = cv2.connectedComponentsWithStats(gm.astype(np.uint8), 8)
    # ветки: пиксели классики, отстоящие от HD-ствола на 2+ пикс базы (ближе - край ствола классики, он у HD
    # шире или сдвинут), выше корней, вместе с хвоей (хвоя потом ложится клоном MAIN поверх). Внутри пятна -
    # остовное дерево соседей (без треугольников: полоса в 2 пикс не становится толстой лентой), рёбра -
    # тонкие отрезки корой между центрами пикселей x4 (лесенка классики становится прямой); ближний пиксель
    # пятна соединён отрезком с ближним пикселем ствола - ветка растёт из ствола
    smask = np.zeros(a.shape, np.float32)
    tr_on = a > 200
    hb, wb_ = cl.shape[:2]
    tr_cl = tr_on[:hb * 4, :wb_ * 4].reshape(hb, 4, wb_, 4).mean((1, 3)) >= 0.5
    tpts = np.argwhere(tr_cl)
    dist = cv2.distanceTransform((~tr_cl).astype(np.uint8), cv2.DIST_L2, 5)
    br = (cl[..., 3] > 0) & (dist >= 2)            # хвоя тоже: ветка идёт под ней, иначе рвётся на штрихи
    br[28:] = False
    br[:clt + 2] = False
    nb, lbb = cv2.connectedComponents(br.astype(np.uint8), connectivity=8)

    def seg(p0, p1, th):
        cv2.line(smask, (int(p0[1] * 16 + 8), int(p0[0] * 16 + 8)), (int(p1[1] * 16 + 8), int(p1[0] * 16 + 8)),
                 1.0, thickness=th, lineType=cv2.LINE_AA, shift=2)
    stems = []
    for j in range(1, nb):
        pts = np.argwhere(lbb == j)
        if len(pts) < 2:
            continue
        dd = np.hypot(*(pts[:, None, :] - pts[None, :, :]).transpose(2, 0, 1))
        dd[dd > 1.5] = np.inf                                  # только соседи по 8 направлениям
        r0i = int(np.argmin(dist[pts[:, 0], pts[:, 1]]))
        inn = np.zeros(len(pts), bool)
        inn[r0i] = True
        best = dd[r0i].copy()
        par = np.full(len(pts), r0i)
        ne = 0
        while True:                                            # Прим от пикселя у ствола
            c_ = np.where(~inn & np.isfinite(best))[0]
            if not len(c_):
                break
            k = c_[np.argmin(best[c_])]
            inn[k] = True
            ne += 1
            upd = ~inn & (dd[k] < best)
            best[upd] = dd[k][upd]
            par[upd] = k
        # остов -> цепочки между развилками и концами, каждая спрямлена (Дуглас-Пекер 0.8 пикс базы):
        # лесенка пикселей классики становится прямой или плавным изломом, а не ступенями
        par[r0i] = -1
        deg = np.zeros(len(pts), int)
        for k in range(len(pts)):
            if par[k] >= 0:
                deg[k] += 1
                deg[par[k]] += 1
        for k in range(len(pts)):
            if par[k] < 0 or deg[k] == 2:
                continue
            ch = [k]                                        # от конца или развилки вверх по остову
            while par[ch[-1]] >= 0:
                ch.append(par[ch[-1]])
                if deg[ch[-1]] != 2:
                    break
            poly = cv2.approxPolyDP(pts[ch][:, ::-1].astype(np.float32).reshape(-1, 1, 2), 0.8, False)
            poly = poly.reshape(-1, 2)[:, ::-1]
            for p0, p1 in zip(poly[:-1], poly[1:]):
                seg(p0, p1, 3)
        r0 = pts[r0i]
        t0 = tpts[np.argmin(((tpts - r0) ** 2).sum(1))]
        seg(r0, t0, 5)
        stems.append([int(len(pts)), ne, [int(r0[0]), int(r0[1])]])
    ssoft = np.clip(cv2.GaussianBlur(smask, (0, 0), 0.5), 0, 1) * (~tr_on)
    sy, sx = np.where(ssoft > 0.02)
    if len(sy):
        nz = cv2.GaussianBlur(rng.normal(0, 6, a.shape).astype(np.float32), (0, 0), 1.0)
        gb = cv2.GaussianBlur(smask, (0, 0), 1.2)
        lit = np.zeros_like(gb)
        lit[1:-1] = gb[2:] - gb[:-2]                   # верхняя кромка ветки светлее (свет сверху), нижняя темнее
        slab = np.stack([bm[0] - 8 + nz[sy, sx] + 14 * np.clip(lit[sy, sx], -1, 1),
                         np.full(len(sy), bm[1]), np.full(len(sy), bm[2])], -1)
        w = ssoft[sy, sx]
        fr[sy, sx, :3] = fr[sy, sx, :3] * (1 - w[:, None]) + _rgb8(slab) * w[:, None]
        fr[sy, sx, 3] = np.maximum(fr[sy, sx, 3], w * 255)
    out["stems"] = stems
    mv = np.asarray(v2, np.float32)
    dense = (mv[..., 3] > 235) & (mv[..., 1] > mv[..., 0] + 6) & ~own2
    twigs = []
    for j in range(1, n):
        if sts[j, 4] < 2:
            continue
        m4 = np.kron((lb == j).astype(np.float32), np.ones((4, 4), np.float32))
        soft = np.clip((cv2.GaussianBlur(m4, (0, 0), 1.6) - 0.3) / 0.4, 0, 1)
        ys, xs_ = np.where(soft > 0)
        gy, gx = ys + b57[1], xs_ + b57[0]
        best = None
        for dy in range(-240, 1, 4):            # хвоя яруса выше: сдвиг вверх
            for dx in range(-160, 161, 4):
                yy2, xx2 = gy + dy, gx + dx
                if yy2.min() < 0 or xx2.min() < 0 or yy2.max() >= dense.shape[0] or xx2.max() >= dense.shape[1]:
                    continue
                cov = dense[yy2, xx2].mean()
                if cov >= 0.97 and (best is None or abs(dy) + abs(dx) < best[0]):
                    best = (abs(dy) + abs(dx), dy, dx)
        if best is None:
            twigs.append([int(sts[j, 0]), int(sts[j, 1]), int(sts[j, 4]), None])
            continue
        _s, dy, dx = best
        src = mv[gy + dy, gx + dx]
        w = soft[ys, xs_] * src[:, 3] / 255.0
        cur = fr[ys, xs_]
        fr[ys, xs_, :3] = cur[:, :3] * (1 - w[:, None]) + src[:, :3] * w[:, None]
        fr[ys, xs_, 3] = np.maximum(cur[:, 3], w * 255)
        twigs.append([int(sts[j, 0]), int(sts[j, 1]), int(sts[j, 4]), [int(dy), int(dx)]])
    out["twigs"] = twigs
    return Image.fromarray(np.clip(v, 0, 255).astype(np.uint8), "RGBA"), v2, out


def wood_face(xx, yy, cx, cy, rx, ry, L0, ab, bark_lab, rng, charred=False):
    """Торец спила x4: древесина (кольца, свет сверху-слева, сердцевина) и обод коры 1.5 пикс.
    Яркость - от древесины пня HD (L0), a*b* - ab, кора - bark_lab. Возвращает рамку, RGB рамки, вес, rr."""
    rr = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    rimw = 1.5 / min(rx, ry)
    box = rr <= 1.0 + 2.5 * rimw
    face = rr <= 1.0
    nz = cv2.GaussianBlur(rng.normal(0, 4, rr.shape).astype(np.float32), (0, 0), 0.8)
    Lw = L0 + 5 * np.cos(rr * np.pi * max(2.0, rx / 4)) + nz              # годовые кольца
    Lw = Lw + 10 * ((xx - cx) * -0.5 + (yy - cy) * -1.0) / (rx + ry)      # свет сверху-слева
    Lw = Lw - 25 * np.clip(1 - rr / 0.12, 0, 1)                            # сердцевина
    if charred:
        Lw = Lw - 12 - 45 * np.clip((0.62 - rr) / 0.25, 0, 1)              # обугленная середина
    f_lab = np.stack([Lw, np.full_like(Lw, ab[0]), np.full_like(Lw, ab[1])], -1)
    Lb = bark_lab[0] - 8 + cv2.GaussianBlur(rng.normal(0, 5, rr.shape).astype(np.float32), (0, 0), 1.0)
    b_lab = np.stack([Lb, np.full_like(Lb, bark_lab[1]), np.full_like(Lb, bark_lab[2])], -1)
    crgb = _rgb8(np.where(face[..., None], f_lab, b_lab)[box])
    wcap = np.clip((1.0 + 2.5 * rimw - rr) / (1.2 * rimw), 0, 1)
    wcap = np.clip(wcap + 0.35 * nz / 4, 0, 1)
    return box, crgb, wcap, rr


def _lab8(rgb):
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8)[None], cv2.COLOR_RGB2LAB)[0].astype(np.float32)


def _rgb8(lab):
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8)[None], cv2.COLOR_LAB2RGB)[0].astype(np.float32)


def classic_spots(job):
    """Пятна спилов классики вида z<=1 в свободной зоне F (k=1): место, размер, средний цвет."""
    c1 = np.asarray(job.tree.compose(1), np.int16)
    r, g, al = c1[..., 0], c1[..., 1], c1[..., 3]
    thr = 90 if job.S == "FOREST" else 70
    m = (al > 128) & (r > g + 15) & (r > thr)
    n, lb, st, cen = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    _U, _own, F = job.masks(1)
    out = []
    for j in range(1, n):
        x, y, w, h, ar = st[j]
        if F[int(round(cen[j][1])), int(round(cen[j][0]))]:
            out.append(dict(x=int(x), y=int(y), w=int(w), h=int(h), area=int(ar),
                            c=(float(cen[j][0]), float(cen[j][1])), mean=c1[lb == j][:, :3].mean(0)))
    return out


# ---------------------------------------------------------------- ворота

def spots(rgba, S, scale):
    """Спилы по правилу цвета (как у классики): [(площадь в пикс k=1, центр k=1, высота k=1)]."""
    a = np.asarray(rgba, np.int16)
    r, g, al = a[..., 0], a[..., 1], a[..., 3]
    thr = 90 if S == "FOREST" else 70
    m = (al > 128) & (r > g + 15) & (r > thr)
    n, _lb, st, cen = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    minpx = 2 if scale == 1 else 8
    out = []
    for j in range(1, n):
        if st[j, 4] >= minpx:
            out.append((st[j, 4] / scale ** 2, (cen[j][0] / scale, cen[j][1] / scale), st[j, 3] / scale))
    return out


def spot_gate(world, S, frames):
    """Число, место, размер, высота спилов кадров 48/50/51 против классики."""
    rep = {}
    ok = True
    for f in CUT_SPOT_FRAMES:
        cl = spots(tr.sprite(world, S, f), S, 1)
        hd = spots(frames[f], S, 4)
        rows = []
        used = set()
        for ac, cc, hc in cl:
            best, bd = None, 1e9
            for j, (ah, ch, hh) in enumerate(hd):
                d = np.hypot(cc[0] - ch[0], cc[1] - ch[1])
                if j not in used and d < bd:
                    best, bd = j, d
            if best is None:
                rows.append(dict(classic=[round(ac), [round(v, 1) for v in cc]], hd=None, ok=False))
                ok = False
                continue
            used.add(best)
            ah, ch, hh = hd[best]
            good = bd <= 1.5 and 0.5 <= ah / ac <= 2.0 and hh <= hc + 2
            ok &= good
            rows.append(dict(classic=[round(ac), [round(v, 1) for v in cc], hc],
                             hd=[round(ah, 1), [round(v, 1) for v in ch], round(hh, 1)],
                             dist=round(float(bd), 2), area_ratio=round(ah / ac, 2), ok=bool(good)))
        extra = [dict(area=round(hd[j][0], 1), at=[round(v, 1) for v in hd[j][1]], h=round(hd[j][2], 1))
                 for j in range(len(hd)) if j not in used]
        if extra:
            ok = False
        rep[f] = dict(classic_n=len(cl), hd_n=len(hd), match=rows, extra=extra)
    return ok, rep


def z1_gates(job, raw1, cond, F_r, cut4):
    """Копия условия (R-219) и подложка внутри силуэта среза."""
    d = np.abs(np.asarray(raw1, np.int16) - np.asarray(cond, np.int16)).max(-1)
    copy = float(d[F_r].mean()) if F_r.any() else -1.0
    U, own, F = job.masks(1)
    sil = np.asarray(tr.xbrz(job.frame_z(1)))[..., 3] > 128
    b = job.box
    full = np.zeros((job.tree.H * 4, job.tree.W * 4), bool)
    full[b[1] * 4:b[3] * 4, b[0] * 4:b[2] * 4] = sil
    zone = full & tr.rep4(F)
    panel = float((cut4[..., 3][zone] < 128).mean()) if zone.any() else -1.0
    return dict(free_mean_abs_vs_cond=round(copy, 1), copy=bool(0 <= copy < 15),
                panel_in_silhouette=round(panel, 3))


def comp_gates(job, comp, v1):
    """Составной срез: подложка внутри силуэта классики, НЕ копия RGB классики, вид z<=1 против MAIN вне U."""
    U, own, F = job.masks(1)
    b = job.box
    sil = np.asarray(tr.xbrz(job.frame_z(1)))[..., 3] > 128
    full = np.zeros((job.tree.H * 4, job.tree.W * 4), bool)
    full[b[1] * 4:b[3] * 4, b[0] * 4:b[2] * 4] = sil
    zone = full & tr.rep4(F)
    panel = float((comp[..., 3][zone] < 128).mean()) if zone.any() else -1.0
    cls = np.asarray(tr.xbrz(job.frame_z(1)), np.int16)
    cl4 = np.zeros((job.tree.H * 4, job.tree.W * 4, 4), np.int16)
    cl4[b[1] * 4:b[3] * 4, b[0] * 4:b[2] * 4] = cls
    d = np.abs(comp[..., :3].astype(np.int16) - cl4[..., :3]).max(-1)
    vs_cls = float(d[zone].mean()) if zone.any() else -1.0
    out_u = ~tr.rep4(U)
    dv = tr.diff(Image.fromarray(np.where(out_u[..., None], np.asarray(v1), 0).astype(np.uint8)),
                 Image.fromarray(np.where(out_u[..., None], np.asarray(job.v2), 0).astype(np.uint8)))
    return dict(panel_in_silhouette=round(panel, 3), zone_mean_abs_vs_classic=round(vs_cls, 1),
                classic_copy=bool(0 <= vs_cls < 15), z1_view_vs_main_outside_U=dv)


# ---------------------------------------------------------------- рендер

def do_render(args, world, CL, hints):
    painter = None
    done = 0
    t0 = time.time()
    for seed in args.seeds:
        for S in tr.SETS:
            job = Job2(world, CL, hints, S, seed, args)
            for rel in args.release:
                p = job.raw_z1(rel)
                if os.path.exists(p):
                    continue
                if args.max_renders and done >= args.max_renders:
                    print("предел рендеров на процесс %d - выход (R-215)" % args.max_renders, flush=True)
                    return
                if not hasattr(job, "_hd"):
                    frames, _src, _info = job.base()
                    known, cond, free, _F_r, _lc, _l4 = job.canvases1(frames)
                if painter is None:
                    painter = tr.painter_new(args)
                cut = paint_locked2(painter, args, known, cond, free, tr.CUT_WHAT[(S, 1)],
                                    seed + tr.CUT_SEED[1], rel)
                po.gen_hd.save_png(cut, p)
                done += 1
                tr.check_shared("%s CUT_Z1 r%.2f s%d" % (S, rel, seed))
                print("  %s CUT_Z1 r%.2f s%d готов, свободно %.3f (%d за %.0f с)"
                      % (S, rel, seed, free.mean(), done, time.time() - t0), flush=True)
    print("рендер: всё на месте, новых %d" % done, flush=True)


# ---------------------------------------------------------------- сборка

def do_masks(args, world, CL, hints):
    for S in tr.SETS:
        for seed in args.seeds:
            job = Job2(world, CL, hints, S, seed, args)
            frames, src, info = job.base()
            known, cond, free, F_r, lockc, lock4 = job.canvases1(frames)
            known.save(os.path.join(job.d2, "known_z1.png"))
            cond.save(os.path.join(job.d2, "cond_z1.png"))
            tr.mask_sheet(os.path.join(job.d2, "mask_z1.png"), cond, known, free,
                          "%s CUT_Z1 s%d: free %.3f, locked 53-55 + z0" % (S, seed, free.mean()))
            z0_sheet(job, os.path.join(job.d2, "z0_seam.png"))
            print("  %s s%d: %s" % (S, seed, json.dumps(info, ensure_ascii=False)), flush=True)


def z0_sheet(job, path):
    """Кадр 57 крупно: классика | V1 z<=0 | V2 z<=0 | MAIN; и полоса шва x3."""
    t, q = job.tree, job.q57
    bx = pos_box(q)
    v1 = Image.open(os.path.join(job.d, "frames", job.S + ".PCK", "57.png")).convert("RGBA") \
        if os.path.exists(os.path.join(job.d, "frames", job.S + ".PCK", "57.png")) else Image.new("RGBA", (128, 160))
    ims = [tr.sprite(job.world, job.S, 57).resize((128, 160), Image.NEAREST), v1,
           job.v0.crop(bx), job.v2.crop(bx)]
    sh = Image.new("RGB", (4 * 136, 176), (30, 30, 34))
    dr = ImageDraw.Draw(sh)
    for j, (im, n) in enumerate(zip(ims, ("classic", "V1 57", "V2 z<=0", "MAIN"))):
        sh.paste(tr.on_floor(im), (j * 136, 16))
        dr.text((j * 136 + 2, 2), n, fill=(255, 255, 0))
    sh.resize((sh.width * 2, sh.height * 2), Image.NEAREST).save(path)


def do_assemble(args, world, CL, hints):
    summary = {}
    over = {S: [] for S in tr.SETS}
    suf = "_comp" if args.z1_composite else ""        # сводка V2 не затирается
    for seed in args.seeds:
        for S in tr.SETS:
            job = Job2(world, CL, hints, S, seed, args)
            frames0, src0, info = job.base()
            t = job.tree
            sig0 = CL[S]["sigs"][0]["sig"]
            olds = tr.old_frames(S)
            for rel in ([None] if args.z1_composite else args.release):
                if rel is None:                       # срез без модели: хвоя MAIN, крышки по пятнам классики
                    lockc, _lock4 = job.lock_z1(frames0)
                    comp, terr, cinfo, comp0, capown = job.z1_composite()
                    v1 = job.view1_comp(comp, terr, lockc)
                    v1n = np.asarray(job.view1_comp(comp0, terr, lockc), np.uint8)
                    tag = "comp"
                else:
                    p = job.raw_z1(rel)
                    known, cond, free, F_r, lockc, lock4 = job.canvases1(frames0)
                    if os.path.exists(p):
                        raw1 = Image.open(p).convert("RGB")
                        tag = "r%02d" % round(rel * 100)
                    elif args.dry:
                        raw1 = cond
                        tag = "dry"
                    else:
                        print("  %s s%d r%.2f: ответа нет - пропуск" % (S, seed, rel))
                        continue
                    v1, cut4 = job.view1(raw1, lockc, lock4)
                frames, src = dict(frames0), dict(src0)
                for j, q in enumerate(t.pcs):
                    if q["f"] in Z1_FRAMES:
                        vq = v1
                        if rel is None:     # крышка чужого куска в кайму кадра не идёт: в T2 48 и 50 меняются местами
                            alien = (capown >= 0) & (capown != j)
                            if alien.any():
                                a = np.asarray(v1, np.uint8).copy()
                                a[alien] = v1n[alien]
                                vq = Image.fromarray(a)
                        frames[q["f"]], src[q["f"]] = frame_from(vq, q), "Z1_EXPOSED"
                miss = [f for f in range(42, 58) if f not in frames]
                if miss:
                    raise SystemExit("нет канона кадров %s" % miss)
                od = os.path.join(job.d2, tag)
                fd = os.path.join(od, "frames", S + ".PCK")
                os.makedirs(fd, exist_ok=True)
                for f, im in frames.items():
                    po.gen_hd.save_png(im, os.path.join(fd, "%d.png" % f))
                V = {2: job.v2, 1: v1, 0: job.v0}
                st = dict(info)
                st["frame_source"] = {str(f): src[f] for f in sorted(src)}
                st["T1_assembled_vs_source"] = {"z<=%d" % z: tr.diff(tr.assemble(world, S, sig0, frames, z), V[z])
                                                for z in (2, 1, 0)}
                if rel is None:
                    st["z1"] = dict(cinfo, **comp_gates(job, comp, v1))
                else:
                    st["z1"] = z1_gates(job, raw1, cond, F_r, cut4)
                ok, sp = spot_gate(world, S, frames)
                st["cut_spots_ok"] = bool(ok)
                st["cut_spots"] = sp
                a0 = tr.assemble(world, S, sig0, frames, 0)
                Ys, cx = info["z0"]["seam_row"], info["z0"]["classic_cx"]
                st["z0"]["seam_assembled"] = seam_numbers(a0, job.q57, Ys, cx)
                summary["%s s%d %s" % (S, seed, tag)] = st
                # листы
                tr.grid([("whole", [("classic x4", job.whole.resize((t.W * 4, t.H * 4), Image.NEAREST)),
                                    ("old HD", tr.assemble(world, S, sig0, olds, 99)),
                                    ("MAIN (source)", job.v2),
                                    ("T1 from frames", tr.assemble(world, S, sig0, frames, 99))])],
                        os.path.join(od, "%s_whole.png" % S), "%s s%d %s: whole tree" % (S, seed, tag))
                rows = []
                for name, i in tr.LAYOUTS[S]:
                    sig = CL[S]["sigs"][i]["sig"]
                    ztop = max(e[4] for e in sig)
                    for kind, fr in (("classic", None), ("old", olds), ("new", frames)):
                        rows.append(("%s %s" % (name, kind),
                                     [("z<=%d" % z, tr.assemble(world, S, sig, fr, z)) for z in range(ztop, -1, -1)]))
                tr.grid(rows, os.path.join(od, "%s_layouts.png" % S),
                        "%s s%d %s: T1/T1b/T2/T3 from the SAME 16 frames; columns = all floors, upper hidden"
                        % (S, seed, tag), scale=0.5)
                frow = []
                for f in range(42, 58):
                    frow.append(("%d %s" % (f, src[f]), [("classic", tr.sprite(world, S, f).resize((128, 160),
                                                                                                Image.NEAREST)),
                                                         ("old", olds.get(f, Image.new("RGBA", (128, 160)))),
                                                         ("new", frames[f])]))
                half = (len(frow) + 1) // 2
                tr.grid([(a[0] + " | " + b[0], a[1] + b[1]) for a, b in zip(frow[:half], frow[half:])],
                        os.path.join(od, "%s_frames.png" % S), "%s s%d %s: frames classic | old | new" % (S, seed, tag))
                z0_sheet(job, os.path.join(od, "%s_z0.png" % S))
                over[S].append(("s%d %s" % (seed, tag),
                                [("z<=%d" % z, tr.assemble(world, S, sig0, frames, z)) for z in (2, 1, 0)]))
                print("  %s s%d %s: собрано, %s" % (S, seed, tag, json.dumps(st, ensure_ascii=False, default=_js))[:1500],
                      flush=True)
    for S, rows in over.items():
        if rows:
            sig0 = CL[S]["sigs"][0]["sig"]
            rows = [("classic", [("z<=%d" % z, tr.assemble(world, S, sig0, None, z)) for z in (2, 1, 0)]),
                    ("old", [("z<=%d" % z, tr.assemble(world, S, sig0, tr.old_frames(S), z)) for z in (2, 1, 0)])] + rows
            tr.grid(rows, os.path.join(args.out, "%s_T1_overview%s.png" % (S, suf)), "%s T1: all variants" % S, scale=0.5)
    stumps_common(args, world)
    with open(os.path.join(args.out, "summary%s.json" % suf), "w", encoding=ENC) as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1, default=_js)
    print("сборка: %s" % os.path.join(args.out, "summary%s.json" % suf))


def stumps_common(args, world):
    """Общий лист пней V1 (обе затравки рядом): классика | старый HD | s2711 | s2712."""
    rows = []
    for (S, f) in tr.STUMPS:
        spr = tr.sprite(world, S, f)
        old = os.path.join(tr.OLD, S + ".PCK", "%d.png" % f)
        r = [("classic", spr.resize((128, 160), Image.NEAREST)),
             ("old", Image.open(old).convert("RGBA") if os.path.exists(old) else Image.new("RGBA", (128, 160)))]
        for seed in (2711, 2712):
            p = os.path.join(args.v1, "s%d" % seed, "stumps", S + ".PCK", "%d.png" % f)
            if os.path.exists(p):
                r.append(("s%d" % seed, Image.open(p).convert("RGBA")))
        rows.append(("%s:%d" % (S, f), r))
    tr.grid(rows, os.path.join(args.out, "stumps_common.png"), "stumps: classic | old | s2711 | s2712")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--v1", default=V1)
    ap.add_argument("--seeds", default="2711,2712")
    ap.add_argument("--release", default="0.85,0.7", help="сигмы, до которых свободное держится классикой")
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--grow", type=int, default=2)
    ap.add_argument("--soft", type=int, default=40)
    ap.add_argument("--pad", type=int, default=3)
    ap.add_argument("--tone", type=float, default=0.7)
    ap.add_argument("--no-recolour", action="store_false", dest="recolour")
    ap.add_argument("--max-renders", type=int, default=4, dest="max_renders")
    ap.add_argument("--mask-only", action="store_true", dest="mask_only")
    ap.add_argument("--assemble", action="store_true")
    ap.add_argument("--dry", action="store_true", help="сборка с условием вместо ответа (контроль тождества)")
    ap.add_argument("--z1-composite", action="store_true", dest="z1_composite",
                    help="срез z1 без модели: хвоя из MAIN, классика - только маска и места спилов (папка comp)")
    args = ap.parse_args()
    args.seeds = [int(s) for s in args.seeds.split(",")]
    args.release = [float(s) for s in args.release.split(",")]
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(args.out, exist_ok=True)
    world = mm.World()
    CL = json.load(open(tr.CLUSTERS, encoding=ENC))
    hints = json.load(open(tr.HINTS, encoding=ENC))
    if args.mask_only:
        do_masks(args, world, CL, hints)
    elif args.assemble:
        do_assemble(args, world, CL, hints)
    else:
        do_render(args, world, CL, hints)


if __name__ == "__main__":
    main()
