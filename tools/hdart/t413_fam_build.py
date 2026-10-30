#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000413, ВСЯ СЕМЬЯ (41 кадр): сборка заготовок по выбору Vitali (C2) и замечаниям пилота. В МОД НИЧЕГО НЕ СТАВИТ:
кадры - art/tickets/t413/fam/cand/<НАБОР>_<кадр>.png (имена под t413_install.py), листы - art/_review/tickets_2026-10-30/.

Основы (16): FORESTSWAMPBITS 4 5 6 7 9 - зёрна C2 из пилота (t413_gen.SETS["C2"]); FORESTBITS3:7 (форма 7b), FORESTBITSRED 3-7,
FORESTBITSWASTE 3-7 - t413_fam.py, зёрна BEST ниже. Правки пилота:
  - 6: ромб травы под камнем - HD-тайл пола FOREST:4 из пака (текстура и цвет земли окружения), камень вырезан по цвету
    земли; под камнем слабая тень;
  - 9: трава светлее одобренного 11 - перенос среднего и разброса цвета травы к 11 (края гладкие), бока чуть темнее;
  - 5/7 и 7b: глина - к цвету глины классики набора (оттенок и насыщенность, рисунок остаётся);
  - RED и WASTE: земля - HD-тайл пола своего террейна (FORESTRED:0, FOREST_WASTE:0), предмет сверху.
Остальные 25 кадров выводятся из основ: копия (классика кадров одна), зеркало или перенос цвета классики своего набора
(t405_409_gen.colormap_transfer, как в 405/409); FORESTBITS2:3 и FORESTBITS_SNOW:3 - из одобренного HD FORESTSWAMPBITS:3
(он не меняется). Срез по силуэту классики x4, внутри силуэта альфа 255 (R-439), кромка предмета ~1 пикс.

    py -3.13 tools\hdart\t413_fam_build.py build
    py -3.13 tools\hdart\t413_fam_build.py sheets
"""
import argparse
import csv
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image, ImageFilter                   # noqa: E402
from scipy import ndimage as ndi                     # noqa: E402

import t413_gen as T                                 # noqa: E402
import t413_fam as F                                 # noqa: E402
import t405_409_gen as G                             # noqa: E402

REV = T.REV
FAM = os.path.join(ROOT, "art", "tickets", "t413", "fam")
CAND = os.path.join(FAM, "cand")
FSB = "FORESTSWAMPBITS"

# лучшие зёрна новых основ (по листу t413_fam_seeds.png)
BEST = {"B7B": 4771, "R3": 5832, "R4": 5841, "R5": 5851, "R6": 5861, "R7": 5872,
        "W3": 4931, "W4": 4941, "W5": 4951, "W6": 4961, "W7": 4971}

# основа -> ключ кадра (набор, кадр)
BASE_KEY = {"B7B": ("FORESTBITS3", 7), "R3": ("FORESTBITSRED", 3), "R4": ("FORESTBITSRED", 4), "R5": ("FORESTBITSRED", 5),
            "R6": ("FORESTBITSRED", 6), "R7": ("FORESTBITSRED", 7), "W3": ("FORESTBITSWASTE", 3),
            "W4": ("FORESTBITSWASTE", 4), "W5": ("FORESTBITSWASTE", 5), "W6": ("FORESTBITSWASTE", 6),
            "W7": ("FORESTBITSWASTE", 7)}

# производные: цель -> основа (по силуэту классики, IoU >= 0.93, см. t413_rocks_all.tsv)
DERIVED = {
    (FSB, 4): [("FORESTBITS3", 4), ("BLACKFORESTBITS", 4), ("FORESTBITS2", 4), ("FORESTBITS_SNOW", 4), ("JUNGLEROCKS", 15)],
    (FSB, 5): [("FORESTBITS3", 5), ("BLACKFORESTBITS", 5), ("FORESTBITS2", 5), ("FORESTBITS_SNOW", 5), ("JUNGLEROCKS", 16)],
    (FSB, 6): [("FORESTBITS3", 6), ("BLACKFORESTBITS", 6), ("FORESTBITS2", 6), ("JUNGLEROCKS", 17)],
    ("FORESTBITS3", 7): [("BLACKFORESTBITS", 7), ("FORESTBITS2", 7), ("JUNGLEROCKS", 18)],
    (FSB, 9): [("FORESTBITS3", 9), ("BLACKFORESTBITS", 9), ("FORESTBITS2", 9), ("FORESTBITSRED", 9),
               ("FORESTBITS_SNOW", 9), ("FORESTBITSWASTE", 9)],
    (FSB, 3): [("FORESTBITS2", 3), ("FORESTBITS_SNOW", 3)],        # основа - одобренный HD :3 из пака, не меняется
}


def fam_keys():
    """Все 41 кадр семьи: основы и производные."""
    keys = [(FSB, 4), (FSB, 5), (FSB, 6), (FSB, 7), (FSB, 9)] + list(BASE_KEY.values())
    for ts_ in DERIVED.values():
        keys += ts_
    return keys


# --- правки основ ----------------------------------------------------------------------------------------
def arr(im):
    return np.asarray(im.convert("RGBA"), np.float32)


def img(a):
    return Image.fromarray(np.rint(np.clip(a, 0, 255)).astype(np.uint8), "RGBA")


def hsv_arrays(rgb):
    x = rgb / 255.0
    mx, mn = x.max(-1), x.min(-1)
    return mx, (mx - mn) / np.maximum(mx, 1e-3)


def fix_clay(im, s, f, strength=1.0):
    """Глина (розоватая насыщенная) - к цвету глины классики набора: среднее и разброс по классике (кадр s:f), рисунок HD
    остаётся (отклонение от среднего глины HD, умноженное на 0.8)."""
    a = arr(im)
    c = np.asarray(F.classic_k1(s, f)).astype(np.float32)
    cm = (c[..., 3] > 0) & (c[..., 0] > c[..., 1] + 12) & (c[..., 0] > c[..., 2] + 8)
    if cm.sum() < 8:
        return im
    target = c[cm][:, :3].mean(0)
    rgb = a[..., :3]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, sat = hsv_arrays(rgb)
    hit = (a[..., 3] > 200) & (r > g) & (r >= b) & (sat > 0.18) & (r - g > 14)
    # мох и тени камня не розовые: от клея к камню - по яркости и насыщенности; мягкая маска
    soft = ndi.gaussian_filter(hit.astype(np.float32), 1.0) * hit
    mean = rgb[hit].mean(0)
    new = target + (rgb - mean) * 0.8
    out = a.copy()
    out[..., :3] = rgb + (new - rgb) * (soft[..., None] * strength)
    return img(out)


def darken_to_11(im):
    """Блок 9: трава сверху - к траве одобренного 11 (среднее и разброс по каналам, не усиливая разброс), бока - к бокам 11
    по среднему. Маска травы - ярко-зелёное по HD, мягкая."""
    ref = arr(T.hd_now(11))
    a = arr(im)

    def masks(x):
        r, g, b = x[..., 0], x[..., 1], x[..., 2]
        top = (x[..., 3] > 250) & (g > r * 1.25) & (g > b * 1.9) & (g > 88)
        return top

    # у 11 тот же признак (его верх - трава)
    top_r, top_a = masks(ref), masks(a)
    side_r = (ref[..., 3] > 250) & ~top_r
    side_a = (a[..., 3] > 250) & ~top_a
    out = a.copy()
    mr, sr = ref[top_r][:, :3].mean(0), ref[top_r][:, :3].std(0) + 1e-3
    ma, sa = a[top_a][:, :3].mean(0), a[top_a][:, :3].std(0) + 1e-3
    gain = np.minimum(sr / sa, 1.0)
    new = (a[..., :3] - ma) * gain + mr
    w = ndi.gaussian_filter(top_a.astype(np.float32), 1.2)
    w = np.clip(w * 1.0, 0, 1)
    out[..., :3] = a[..., :3] + (new - a[..., :3]) * w[..., None]
    msr, msa = ref[side_r][:, :3].mean(0), a[side_a][:, :3].mean(0)
    ws = (1.0 - w) * (a[..., 3] > 250)
    out[..., :3] = out[..., :3] + (msr - msa) * ws[..., None] * 0.9
    # бока светлее боков 11 на карте (кладка светло-серая, у 11 тёмный мшистый камень): ещё на 14 процентов темнее
    out[..., :3] = out[..., :3] * (1.0 - 0.14 * ws[..., None])
    return img(out)


def floor_hd(g):
    s, f = F.GROUNDS[g]["hd"] if isinstance(g, str) else g
    return T.hd_now(f, s)


def solid_ground(floor, cls_k1):
    """Слой земли из HD-тайла пола: внутри силуэта классики x4 и тайла альфа 255 (R-439; цвет полупрозрачной кромки тайла
    заливается ближайшим надёжным пикселем), вне силуэта 0."""
    fa = arr(floor)
    sil = T.classic_mask(cls_k1, (128, 160))
    good = fa[..., 3] >= 250
    near = ndi.distance_transform_edt(~good, return_distances=False, return_indices=True)
    rgb = fa[..., :3][near[0], near[1]]
    out = np.zeros_like(fa)
    out[..., :3] = np.where(good[..., None], fa[..., :3], rgb)
    # земля только там, где есть сам тайл пола (над ромбом классика кадра шире HD-предмета - не заливать воздух)
    ga = np.where(fa[..., 3] >= 40, 255.0, fa[..., 3])
    out[..., 3] = np.where(sil, ga, 0)
    out[out[..., 3] == 0, :3] = 0
    return out


def compose(obj, ground_arr, shadow=0.32):
    """Предмет (RGBA x4) поверх слоя земли; у основания предмета - слабая тень по земле (не выходит за силуэт земли)."""
    o = arr(obj)
    g = ground_arr.copy()
    al = o[..., 3] / 255.0
    ys, xs = np.nonzero(al > 0.5)
    if len(ys):
        y1 = ys.max()
        low = np.zeros_like(al)
        sel = (np.arange(al.shape[0])[:, None] >= y1 - 28)
        low[sel[:, 0]] = al[sel[:, 0]]
        sh = ndi.gaussian_filter(low, 7.0)
        sh = np.roll(sh, 3, axis=0)
        sh = np.clip(sh * 1.6, 0, 1) * shadow * (1 - al)
        g[..., :3] = g[..., :3] * (1 - sh[..., None])
    out = g.copy()
    out[..., :3] = g[..., :3] * (1 - al[..., None]) + o[..., :3] * al[..., None]
    out[..., 3] = np.maximum(g[..., 3], o[..., 3])
    return img(out)


def split_rock(im, tol=26.0):
    """Кадр 6 пилота: камень отделён от плоской травы по цвету травы (мягкая альфа камня). Возвращает RGBA камня."""
    a = arr(im)
    al = a[..., 3] > 250
    H, W = al.shape
    yy, xx = np.mgrid[0:H, 0:W]
    diamond = (np.abs(xx - 63.5) / 64.0 + np.abs(yy - 127.5) / 34.0) <= 1.0
    ring = diamond & al & (yy > 118)
    # цвет травы - медиана по нижней части ромба, ярко-зелёное
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    green = ring & (g > r * 1.3) & (g > b * 1.8)
    gc = np.median(a[green][:, :3], axis=0)
    d = np.sqrt(((a[..., :3] - gc) ** 2).sum(-1))
    ground = (d < tol) & al
    # земля - связная область, касающаяся края ромба; всё остальное предмет
    lab, n = ndi.label(ground)
    edge = diamond & ~(ndi.binary_erosion(diamond, np.ones((9, 9), bool)))
    keep = np.zeros(n + 1, bool)
    for i in np.unique(lab[edge & ground]):
        if i:
            keep[i] = True
    ground = keep[lab]
    rock = al & ~ground
    rock = ndi.binary_opening(rock, np.ones((3, 3), bool))
    lab, n = ndi.label(rock)
    if n > 1:
        sizes = ndi.sum(rock, lab, range(1, n + 1))
        rock = lab == (1 + int(np.argmax(sizes)))
    rock = ndi.binary_fill_holes(rock)
    # цвет вне ядра камня (кайма, остатки травы) - от ближайшего пикселя ядра; альфа каймы - по цвету травы и по альфе пилота
    near = ndi.distance_transform_edt(~rock, return_distances=False, return_indices=True)
    rgb = a[..., :3][near[0], near[1]]
    ring = ndi.binary_dilation(rock, np.ones((5, 5), bool)) & ~rock
    soft = rock.astype(np.float32)
    soft[ring] = np.clip((d[ring] - 12.0) / 28.0, 0, 1) * (a[..., 3][ring] / 255.0)
    out = np.zeros_like(a)
    out[..., :3] = rgb
    out[..., 3] = ndi.gaussian_filter(soft, 0.6) * 255.0
    out[..., 3][rock] = 255.0
    out[..., 3][~ndi.binary_dilation(rock, np.ones((7, 7), bool))] = 0
    out[out[..., 3] == 0, :3] = 0
    return img(out), rock


def _ramp(cols, win_div=20):
    n = len(cols)
    win = max(3, n // win_div)
    k = np.ones(win) / win
    return np.stack([np.convolve(np.pad(cols[:, c], (win, win), mode="edge"), k, mode="same")[win:-win]
                     for c in range(3)], 1)


def _clay(rgb):
    return (rgb[..., 0] > rgb[..., 1] + 12) & (rgb[..., 0] > rgb[..., 2] + 20)


def _grass(rgb):
    return (rgb[..., 1] > rgb[..., 0] + 10) & (rgb[..., 1] > rgb[..., 2] + 10)


def ramp_transfer(hd, ot):
    """Цель без мха (серый камень FORESTBITS2 / FORESTBITS_SNOW, тёмный BLACKFORESTBITS): оттенок не сдвигается от зелёной
    основы (призрак лиан), а берётся по яркости: ранг яркости пикселя HD среди своей группы -> цвет классики цели с тем же
    рангом яркости (сглаженная лесенка цветов). Группы две: камень и глина (розоватая насыщенная). Зелёное классики цели
    (трава у основания) в ряд камня не берётся - иначе на сером камне зелёный налёт. Рисунок и перепады яркости HD остаются."""
    w = np.array([0.299, 0.587, 0.114], np.float32)
    a = arr(hd)
    t = arr(ot)
    body = a[..., 3] > 0
    tb = t[..., 3] > 0
    L = a[..., :3] @ w
    tL = t[..., :3] @ w
    t_clay = tb & _clay(t[..., :3])
    t_rock = tb & ~t_clay & ~_grass(t[..., :3])
    if t_rock.sum() < 20:
        t_rock = tb & ~t_clay
    h_clay = body & _clay(a[..., :3]) & (a[..., 0] - a[..., 1] > 14)
    out = a.copy()

    def run(hmask, tmask):
        if hmask.sum() == 0 or tmask.sum() == 0:
            return
        order = np.argsort(tL[tmask], kind="stable")
        ramp = _ramp(t[tmask][order][:, :3])
        n = len(ramp)
        Lb = L[hmask]
        rank = np.empty(len(Lb))
        rank[np.argsort(Lb, kind="stable")] = np.arange(len(Lb))
        q = rank / max(1, len(Lb) - 1)
        out[hmask, :3] = ramp[np.clip((q * (n - 1)).astype(int), 0, n - 1)]

    use_clay = t_clay.sum() >= 10 and h_clay.sum() >= 10
    run(body & ~h_clay if use_clay else body, t_rock)
    if use_clay:
        run(h_clay, t_clay)
    return img(out)


def derive6_ramp(rock, tkey, gname):
    """Кадр 6 серых и тёмных наборов: камень пилота (без земли) - по яркости в цвета камня классики цели (без травы
    ромба), земля - HD-тайл пола террейна цели."""
    ot = F.classic_k1(*tkey)
    a = np.asarray(ot).astype(np.float32)
    yy, xx = np.mgrid[0:40, 0:32]
    ring = (np.abs(xx - 15.5) / 16.0 + np.abs(yy - 31.5) / 8.5)
    edge = (a[..., 3] > 0) & (ring > 0.7) & (ring <= 1.0) & (yy > 28)
    gcols = set(map(tuple, a[edge][:, :3].astype(int).tolist()))
    ground = np.array([tuple(c) in gcols for c in a[..., :3].astype(int).reshape(-1, 3).tolist()]).reshape(40, 32)
    rockm = (a[..., 3] > 0) & ~ground
    ot_rock = ot.copy()
    arr_o = np.asarray(ot_rock).copy()
    arr_o[~rockm] = 0
    ot_rock = Image.fromarray(arr_o, "RGBA")
    col = ramp_transfer(rock, ot_rock)
    return compose(col, solid_ground(hd_tile(gname), ot))


def hd_tile(g):
    s, f = g
    return T.hd_now(f, s)


SIX_RAMP = {("FORESTBITS2", 6): ("FOREST", 4), ("BLACKFORESTBITS", 6): ("BLACKFOREST", 0)}
ROCK6 = None
RAMP = {"BLACKFORESTBITS", "FORESTBITS2", "FORESTBITS_SNOW"}


def base_cls(key):
    return F.classic_k1(*key)


# --- сборка ------------------------------------------------------------------------------------------------
def pilot_base(f):
    return Image.open(os.path.join(T.CAND, "C2", "%s_%d.png" % (FSB, f))).convert("RGBA")


def despill(im):
    """Пурпурная подложка (190,50,190) подмешана в кайму ответа: пиксель, где красный и синий оба заметно выше зелёного, -
    пурпур, а не глина (у глины синий ниже зелёного) и не мох. Красный и синий тянутся к зелёному."""
    a = arr(im)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    spill = np.clip(np.minimum(r - g, b - g) / 40.0, 0, 1) * (b > r * 0.6)
    spill = ndi.gaussian_filter(spill, 0.5)
    for c in (0, 2):
        a[..., c] = a[..., c] + (g * 1.0 - a[..., c]) * spill * 0.85
    return img(a)


def gen_base(name):
    seed = BEST[name]
    return despill(Image.open(os.path.join(F.GEN, name, "%d.png" % seed)).convert("RGBA"))


def derive(base_im, bkey, tkey, base_cls_im=None):
    """Цель из основы: копия / зеркало / перенос цвета классики. Возвращает (кадр, способ)."""
    ob = base_cls_im if base_cls_im is not None else F.classic_k1(*bkey)
    ot = F.classic_k1(*tkey)
    if G.same_px(ob, ot):
        out, how = base_im.copy(), "копия"
    elif tkey[0] in RAMP and tkey[1] in (3, 4, 5, 7):
        out, how = ramp_transfer(base_im, ot), "перенос цвета по яркости"
    else:
        out, how = G.colormap_transfer(base_im, ob, ot), "перенос цвета"
    out, _cut = G.clip_to_classic(out, ot)
    return out, how


def finish_base(im, key):
    """Срез по силуэту классики x4 для основ пилота (у новых с землёй сборка уже по силуэту)."""
    out, _n = G.clip_to_classic(im, F.classic_k1(*key))
    return out


def build_bases():
    """-> {ключ: RGBA} основ (с правками пилота)."""
    out = {}
    out[(FSB, 4)] = despill(pilot_base(4))
    out[(FSB, 5)] = despill(fix_clay(pilot_base(5), FSB, 5))
    out[(FSB, 7)] = despill(fix_clay(pilot_base(7), FSB, 7))
    out[(FSB, 9)] = darken_to_11(pilot_base(9))
    # 6: камень пилота на земле окружения
    rock, _m = split_rock(pilot_base(6))
    global ROCK6
    ROCK6 = rock
    cls6 = F.classic_k1(FSB, 6)
    out[(FSB, 6)] = compose(rock, solid_ground(T.hd_now(4, "FOREST"), cls6))
    for name, key in BASE_KEY.items():
        if BEST.get(name) is None:
            continue
        im = gen_base(name)
        J = F.JOBS[name]
        if name == "B7B":
            im = despill(fix_clay(im, *key))
        if J["ground"]:
            gnd = solid_ground(F.hd_floor(J["ground"]), F.classic_k1(*key))
            im = compose(im, gnd)
        out[key] = im
    return out


def build_all(save=True):
    bases = build_bases()
    res = dict(bases)
    how = {k: "основа" for k in bases}
    for bkey, targets in DERIVED.items():
        if bkey == (FSB, 3):
            bim = T.hd_now(3)                        # одобренный HD :3 из пака
        elif bkey in bases:
            bim = bases[bkey]
        else:
            print("нет основы", bkey)
            continue
        for tkey in targets:
            if bkey != (FSB, 3) and bkey not in bases:
                continue
            if tkey in SIX_RAMP:
                res[tkey], how[tkey] = derive6_ramp(ROCK6, tkey, SIX_RAMP[tkey]), "перенос цвета по яркости (камень) + пол"
                res[tkey], _c = G.clip_to_classic(res[tkey], F.classic_k1(*tkey))
            else:
                res[tkey], how[tkey] = derive(bim, bkey, tkey)
    for k in list(res):
        if k in bases and k[0] == FSB:
            res[k] = finish_base(res[k], k)
    if save:
        shutil.rmtree(CAND, ignore_errors=True)
        os.makedirs(CAND)
        for (s, f), im in res.items():
            im.save(os.path.join(CAND, "%s_%d.png" % (s, f)))
    return res, how


# --- листы, сцены, проверки ----------------------------------------------------------------------------
ORDER = [(FSB, 4), ("FORESTBITS3", 4), ("BLACKFORESTBITS", 4), ("FORESTBITS2", 4), ("FORESTBITS_SNOW", 4), ("JUNGLEROCKS", 15),
         (FSB, 5), ("FORESTBITS3", 5), ("BLACKFORESTBITS", 5), ("FORESTBITS2", 5), ("FORESTBITS_SNOW", 5), ("JUNGLEROCKS", 16),
         (FSB, 6), ("FORESTBITS3", 6), ("BLACKFORESTBITS", 6), ("FORESTBITS2", 6), ("JUNGLEROCKS", 17),
         (FSB, 7), ("FORESTBITS3", 7), ("BLACKFORESTBITS", 7), ("FORESTBITS2", 7), ("JUNGLEROCKS", 18),
         (FSB, 9), ("FORESTBITS3", 9), ("BLACKFORESTBITS", 9), ("FORESTBITS2", 9), ("FORESTBITSRED", 9),
         ("FORESTBITS_SNOW", 9), ("FORESTBITSWASTE", 9),
         ("FORESTBITS2", 3), ("FORESTBITS_SNOW", 3),
         ("FORESTBITSRED", 3), ("FORESTBITSRED", 4), ("FORESTBITSRED", 5), ("FORESTBITSRED", 6), ("FORESTBITSRED", 7),
         ("FORESTBITSWASTE", 3), ("FORESTBITSWASTE", 4), ("FORESTBITSWASTE", 5), ("FORESTBITSWASTE", 6),
         ("FORESTBITSWASTE", 7)]


def load_cand():
    out = {}
    for fn in sorted(os.listdir(CAND)):
        if fn.endswith(".png"):
            n, f = fn[:-4].rsplit("_", 1)
            out[(n, int(f))] = Image.open(os.path.join(CAND, fn)).convert("RGBA")
    return out


def how_map():
    _res, how = build_all(save=False)
    return how


def do_family_sheet():
    import ticket_scene as ts
    cand = load_cand()
    how = how_map()
    panels = []
    for k in ORDER:
        if k not in cand:
            continue
        cls = F.classic_k1(*k).resize((128, 160), Image.NEAREST)
        cur = T.hd_now(k[1], k[0])
        row = T.hstack([T.on_dark(cls), T.on_dark(cur), T.on_dark(cand[k])], top=0)
        row = row.resize((int(row.width * 1.5), int(row.height * 1.5)), Image.LANCZOS)
        panels.append(("%s:%d  %s" % (k[0], k[1], how.get(k, "")), row))
    out = os.path.join(REV, "t413_family.png")
    ts.sheet(panels, out, cols=3)
    print("лист:", out, "кадров", len(panels))


def best_block(world, keys, terrain_hint=None):
    """Блок карты (террейн, блок) с наибольшим числом клеток кадров keys."""
    import map_mockup as mm
    use = mm.usage(world)
    score = {}
    for k in keys:
        for t, b, n in use.get("%s:%d" % k, []):
            if terrain_hint and t != terrain_hint:
                continue
            score[(t, b)] = score.get((t, b), 0) + n
    return sorted(score.items(), key=lambda kv: -kv[1])


SCENES = [
    # имя листа, террейн (None - любой), нужные кадры, окно
    ("t413_scene.png", "FORESTSWAMP", [(FSB, 5), (FSB, 6), (FSB, 7)], (110, 80), "FINNIKFOREST05"),
    ("t413_scene_b.png", "FORESTSWAMP", [(FSB, 9)], (110, 80), "FINNIKFOREST05"),
    ("t413_scene_red.png", "FORESTRED", [("FORESTBITSRED", 3), ("FORESTBITSRED", 4), ("FORESTBITSRED", 5),
                                          ("FORESTBITSRED", 6), ("FORESTBITSRED", 7)], (110, 80), None),
    ("t413_scene_waste.png", "FORESTWASTE", [("FORESTBITSWASTE", 3), ("FORESTBITSWASTE", 4), ("FORESTBITSWASTE", 5),
                                              ("FORESTBITSWASTE", 6), ("FORESTBITSWASTE", 7)], (110, 80), None),
    ("t413_scene_grey.png", "FOREST", [("FORESTBITS2", 4), ("FORESTBITS2", 5), ("FORESTBITS2", 6), ("FORESTBITS2", 7)],
     (110, 80), None),
    ("t413_scene_black.png", "FOREST2BLACK", [("BLACKFORESTBITS", 4), ("BLACKFORESTBITS", 5), ("BLACKFORESTBITS", 6),
                                              ("BLACKFORESTBITS", 7)], (110, 80), None),
    ("t413_scene_styx.png", "STYXSWAMP", [("FORESTBITS3", 4), ("FORESTBITS3", 5), ("FORESTBITS3", 6), ("FORESTBITS3", 7)],
     (110, 80), None),
    ("t413_scene_jungle.png", "JUNGLETEMPLE", [("JUNGLEROCKS", 15), ("JUNGLEROCKS", 16), ("JUNGLEROCKS", 17),
                                                ("JUNGLEROCKS", 18)], (110, 80), None),
]


def do_scene(only=None):
    import ticket_scene as ts
    sc = ts.Scene()
    cand = load_cand()
    for name, terrain, keys, (w, h), block in SCENES:
        if only and name not in only:
            continue
        keys = [k for k in keys if k in cand]
        if not keys:
            continue
        if block is None:
            ranked = best_block(sc.w, keys, terrain)
            if not ranked:
                print("нет блока", name)
                continue
            block = ranked[0][0][1]
        found = ts.find_cells(sc, terrain, block, keys)
        if not found:
            print("нет клеток", name, block)
            continue
        # окно - вокруг найденных клеток нижнего этажа
        zmin = min(f[3] for f in found)
        found = [f for f in found if f[3] == zmin]
        box = ts.window([(c[0], c[1], tuple(v * 4 for v in c[2])) for c in found], w, h, 4)
        panels = []
        for title, mode, o in (("классика", "classic", None), ("HD сейчас", "hd", None), ("новое (семья)", "hd", cand)):
            im, _f = sc.render(terrain, block, mode, override=o, k=4, maxz=zmin)
            panels.append((title, ts.crop_pad(im, box)))
        ts.sheet(panels, os.path.join(REV, name), cols=2)
        print("лист:", os.path.join(REV, name), terrain, block, "клеток", len(found), [c[4] for c in found])


def do_checks():
    """По каждому кадру: альфа вне силуэта классики x4 (допуск 2 пикс), полупрозрачных доля сейчас/новое, просвет шва 3x3
    (rim_alpha.leak, R-439) сейчас/новое, непрозрачность внутри силуэта ромба земли (для кадров с землёй), IoU, резкость."""
    import rim_alpha as ra
    cand = load_cand()
    rows = []
    for k in ORDER:
        if k not in cand:
            continue
        new = cand[k]
        cur = T.hd_now(k[1], k[0])
        cls = F.classic_k1(*k)
        mn = T.metrics(new, cls)
        mc = T.metrics(cur, cls) if cur.getbbox() else None
        op = index_frame_k(k)
        ln = ra.leak(np.asarray(new)[..., 3], op, 4)
        lc = ra.leak(np.asarray(cur)[..., 3], op, 4) if mc else ("-", "-")
        rows.append([k[0], k[1], mn["outside"], "%.3f" % mn["semi"], "%.3f" % mc["semi"] if mc else "-",
                     ln[0], ln[1], lc[0], lc[1], "%.2f" % mn["iou"], "%.1f" % mn["sharp"],
                     "%.1f" % mc["sharp"] if mc else "-"])
    out = os.path.join(REV, "t413_family_checks.tsv")
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["набор", "кадр", "альфа вне силуэта классики x4 (допуск 2 пикс), пикс", "полупрозрачных новое",
                    "полупрозрачных сейчас", "просвет шва 3x3 новое, пикс", "из них закрыто классикой",
                    "просвет сейчас, пикс", "закрыто классикой", "IoU силуэта", "резкость новое", "резкость сейчас"])
        w.writerows(rows)
    bad = [r for r in rows if r[2] > 0 or r[5] > 0]
    print("проверено %d, с альфой вне силуэта или просветом шва: %d" % (len(rows), len(bad)))
    for r in rows:
        print("  ", r)
    print("таблица:", out)


def index_frame_k(k):
    return F.index_frame(*k)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "sheet", "scene", "checks"])
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    if a.cmd == "build":
        res, how = build_all()
        print("кадров:", len(res))
        for k in sorted(res):
            print("  %s:%d %s" % (k[0], k[1], how[k]))
    elif a.cmd == "sheet":
        do_family_sheet()
    elif a.cmd == "scene":
        do_scene(a.only)
    else:
        do_checks()
    return 0


if __name__ == "__main__":
    sys.exit(main())
