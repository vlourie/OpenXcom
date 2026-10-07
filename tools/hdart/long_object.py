#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Длинный предмет одним куском (R-121): стойка бара, забор, перила - всё, что тянется по карте рядом клеток.

Зачем: obj_series рисует кадр отдельно, и модель у каждого края клетки рисует торец - на карте стойка
собрана из кубиков, стык виден через клетку. Здесь весь ряд клеток берётся с карты, как он стоит, и
рисуется одной картинкой; режется по клеткам (obj_series.split) - кайма и силуэт у ряда общие.

Кадр в игре один на все свои клетки (13 стоит пять раз подряд), а нарисованы у него пять разных кусков.
Поэтому у каждого кадра полосы у стыков заменяются содержимым ОДНОГО эталонного стыка (пара соседних
клеток ряда по той же оси): правая полоса любого кадра - как у левой клетки эталона, левая - как у
правой. Две любые клетки ряда встают встык так же, как эталонная пара, - без шва.

Вход модели (--input, можно несколько через запятую - одна загрузка модели):
    xbrz     оригинал ряда увеличен xBRZ x4, потом бикубикой: лесенки пикселей нет уже во входе,
             и модель её не повторяет (R-121: при бикубике она рисует ступени как форму)
    bicubic  как obj_series - для сравнения

    E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/long_object.py ^
        --terrain WESTOWN_LOKNAR --block WESTOWN_SALOON --set BRICKBAR --frames 12,13,14,16 ^
        --hint-key WESTOWN_SALOON:BRICKBAR --out art/objects/long/saloon_bar

Кладёт в --out/<вход>/: raw.png (ответ модели), whole.png (ряд x4 целиком, как нарисован),
series/<НАБОР>.PCK/<кадр>.png (кадры для пака), sheet.png (оригинал | целиком | из кадров),
map.png (нижний этаж карты с новыми кадрами). В пак НЕ идёт.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.dirname(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw                    # noqa: E402
import cv2                                          # noqa: E402
import probe_object as po                           # noqa: E402  (он же ставит HF_HOME)
import obj_series as osr                            # noqa: E402
import map_mockup as mm                             # noqa: E402
import pck_census as pc                             # noqa: E402
import sprite_scale as ss                           # noqa: E402

ENC = "utf-8-sig"
AXES = {"x": (1, 0), "y": (0, 1)}


def run_cells(world, terrain, block, want, frames, z, near=None):
    """Клетки этажа z с кадрами набора want из frames -> {(x, y): (набор, кадр, p_level)} и связные ряды
    (4-соседство), самый длинный первым; в ряду - порядок рисования (y, потом x), как у map_mockup.render.
    near=(x, y, r) - только клетки не дальше r от (x, y) по каждой оси."""
    sets = world.sets_of(terrain)
    sizes = {s: len(world.records(s)) for s in sets}
    _sx, _sy, _sz, cells = mm.read_block(world, block)
    found = {}
    for (x, y, zz), cell in cells.items():
        if zz != z:
            continue
        if near and (abs(x - near[0]) > near[2] or abs(y - near[1]) > near[2]):
            continue
        for part in (1, 2, 3):
            v = cell[part]
            if not v:
                continue
            s, rec = pc.resolve(v, sets, sizes)
            if s and s.upper() == want:
                r = world.records(s)[rec]
                if r["frame"] in frames:
                    found[(x, y)] = (s, r["frame"], r["p_level"])
    runs, seen = [], set()
    for start in sorted(found):
        if start in seen:
            continue
        stack, run = [start], []
        seen.add(start)
        while stack:
            c = stack.pop()
            run.append(c)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + dx, c[1] + dy)
                if n in found and n not in seen:
                    seen.add(n)
                    stack.append(n)
        runs.append(sorted(run, key=lambda c: (c[1], c[0])))
    return found, sorted(runs, key=len, reverse=True)


def make_comp(world, found, run, z):
    """Ряд как составной предмет obj_series: ключ - (НАБОР, кадр, x, y), у каждой клетки свой."""
    members, spr, pl = [], {}, {}
    for (x, y) in run:
        s, f, p = found[(x, y)]
        key = (s.upper(), f, x, y)
        members.append((key, ((x - y) * 16, (x + y) * 8 - z * 24, z)))
        spr[key] = world.sprite(s, f, None).convert("RGBA")
        pl[key] = p
    return {"members": members, "spr": spr, "pl": pl}


def model_input(frame, zoom, how):
    """Эскиз для модели на ровной подложке. xbrz - без лесенки пикселей (R-121), bicubic - как obj_series."""
    panel = po.pick_background(frame)
    # прозрачные пиксели внутри предмета (бутылка на стойке - индекс 0) модель читает как дыру и рисует
    # мойку: заливаем их цветом соседей
    a = np.asarray(frame.convert("RGBA")).copy()
    solid = a[..., 3] > 0
    holes = (np.asarray(po.fill_holes(Image.fromarray(solid.astype(np.uint8) * 255, "L"))) > 0) & ~solid
    if holes.any():
        a[..., :3] = cv2.inpaint(np.ascontiguousarray(a[..., :3]), holes.astype(np.uint8), 2, cv2.INPAINT_TELEA)
        a[holes, 3] = 255
        frame = Image.fromarray(a, "RGBA")
    if how == "xbrz":
        up = ss.xbrz_scale(np.asarray(frame.convert("RGBA"), np.float32)[None], 4)[0]
        big = Image.fromarray(np.clip(up, 0, 255).astype(np.uint8), "RGBA")
        src = big.resize((frame.width * zoom, frame.height * zoom), Image.BICUBIC)
    else:
        src = frame.resize((frame.width * zoom, frame.height * zoom), Image.BICUBIC)
    flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
    flat.alpha_composite(src)
    return flat.convert("RGB")


def label_map(comp, at, shape):
    """Что игра показывает в каждой точке ряда при k=1: номер последней нарисованной клетки, непрозрачной там."""
    lab = np.full(shape, -1, np.int32)
    for i, (key, _o) in enumerate(comp["members"]):
        x, y = at[key]
        m = np.asarray(comp["spr"][key])[..., 3] > 0
        sub = lab[y:y + 40, x:x + 32]
        sub[m] = i
    return lab


def joint_weight(lab4, i_self, i_other, xy, band):
    """Полоса клетки i_self у стыка с i_other в своих координатах (128x160): 1 у стыка, 0 на глубине band."""
    other = (lab4 == i_other).astype(np.uint8)
    d = cv2.distanceTransform(1 - other, cv2.DIST_L2, 5)
    w = np.clip(1.0 - d / float(band), 0.0, 1.0) * (lab4 == i_self)
    x, y = xy
    return w[y * 4:y * 4 + 160, x * 4:x * 4 + 128]


def window_region(spr, brown=15):
    """Окно в дощатой стене k=1 -> (всё окно, его внутренность), bool 40x32. Доски коричневые (R-B не меньше
    brown), рама и прутья серо-синие, стекла у оригинала нет - прозрачные дыры (NUKE3 7). Окно - связные
    области не-досок, не касающиеся края кадра; внутренность - окно без рамы в 2 пикселя."""
    a = np.asarray(spr.convert("RGBA")).astype(np.int32)
    plank = (a[..., 3] > 0) & (a[..., 0] - a[..., 2] >= brown)
    n, lab = cv2.connectedComponents((~plank).astype(np.uint8), connectivity=4)
    win = np.zeros(plank.shape, bool)
    for c in range(1, n):
        m = lab == c
        ys, xs = np.nonzero(m)
        if ys.min() > 0 and xs.min() > 0 and ys.max() < m.shape[0] - 1 and xs.max() < m.shape[1] - 1 \
                and m.sum() >= 20:
            win |= m
    win = cv2.morphologyEx(win.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
    win = np.asarray(po.fill_holes(Image.fromarray(win.astype(np.uint8) * 255, "L"), 400)) > 0
    inner = cv2.erode(win.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    return win, inner


def split_smooth(cut, comp, at, grow):
    """Как obj_series.split, но край куска по своему силуэту - линией, а не лесенкой x4 (R-121).
    Кадр один на все свои клетки: кусок, снятый с середины ряда, у стыка обрезан лесенкой пикселей, и там,
    где тот же кадр стоит в конце ряда (стойка упирается в стену), лесенка открыта. Поэтому свой силуэт
    расширяется на пиксель и спрямляется: у стыка лишнее уходит под соседа (у них одна общая картинка), а у
    открытого конца край - прямая."""
    whole, _ = osr.compose(comp)
    h, w = whole.height, whole.width
    sil, lab = {}, np.full((h, w), -1, np.int32)
    for i, (key, _o) in enumerate(comp["members"]):
        m = np.zeros((h, w), bool)
        x, y = at[key]
        m[y:y + 40, x:x + 32] = np.asarray(comp["spr"][key])[..., 3] > 0
        sil[key] = m
        lab[m & (lab < 0)] = i
    any_sil = lab >= 0
    alpha = np.asarray(cut.split()[3], np.float32)
    # Кран модель рисует выше оригинала, и макушка вне всех силуэтов доставалась ближайшей клетке - голой 13
    # позади, а с ней висела в воздухе над каждой 13. Выступ сначала забирают клетки-украшения (их кадр
    # окружён по ряду чужими: 14 между 13, угол 12) - по сплошной краске от своего силуэта, до 12 пикселей
    solid1 = alpha.reshape(h, 4, w, 4).mean((1, 3)) > 128
    keys = [k for k, _o in comp["members"]]
    idx = {(k[2], k[3]): i for i, k in enumerate(keys)}
    decor = set()
    for i, k in enumerate(keys):
        nb = [idx[(k[2] + dx, k[3] + dy)] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
              if (k[2] + dx, k[3] + dy) in idx]
        if len(nb) >= 2 and all(keys[j][1] != k[1] for j in nb):
            decor.add(i)
    # Где стоит украшение: оригинал клетки против оригинала голого соседа, с запасом вширь и вверх (кран
    # нарисован выше оригинала), по сплошной краске. Это забирает кадр украшения, а у остальных - грязь
    obj = {}
    for i in decor:
        k = keys[i]
        nbk = next(keys[idx[(k[2] + dx, k[3] + dy)]] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                   if (k[2] + dx, k[3] + dy) in idx)
        d = np.any(np.asarray(comp["spr"][k]) != np.asarray(comp["spr"][nbk]), -1).astype(np.uint8)
        d = cv2.dilate(d, np.ones((7, 7), np.uint8))
        m = np.zeros((h, w), bool)
        x, y = at[k]
        m[y:y + 40, x:x + 32] = d > 0
        up = m.copy()
        for s in range(1, 13):
            up[:-s] |= m[s:]
        obj[i] = up & solid1
    obj_all = np.zeros((h, w), bool)
    for m in obj.values():
        obj_all |= m
    split_smooth.dirty = {}
    if decor:
        dl = np.where(np.isin(lab, list(decor)), lab, -1)
        for _ in range(12):
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                src = np.roll(dl, (dy, dx), (0, 1))
                take = (dl < 0) & (src >= 0) & ~any_sil & solid1
                dl[take] = src[take]
        claim = (dl >= 0) & ~any_sil
        lab[claim] = dl[claim]
    for _ in range(grow + 2):
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(lab, (dy, dx), (0, 1))
            take = (lab < 0) & (src >= 0)
            lab[take] = src[take]
    out = {}
    for i, (key, _o) in enumerate(comp["members"]):
        own = cv2.dilate(sil[key].astype(np.uint8), np.ones((3, 3), np.uint8)) * 255
        own4 = np.asarray(po.smooth_silhouette(Image.fromarray(own, "L"), 4), np.float32) / 255.0
        rim = (lab == i) & ~any_sil
        if i in obj:
            rim = rim | obj[i]
        m4 = np.maximum(own4, np.repeat(np.repeat(rim, 4, 0), 4, 1).astype(np.float32))
        piece = np.asarray(cut, np.uint8).copy()
        piece[..., 3] = (alpha * m4).astype(np.uint8)
        x, y = at[key]
        out[key] = Image.fromarray(piece, "RGBA").crop((x * 4, y * 4, x * 4 + 128, y * 4 + 160))
        dirty = obj_all & ~obj.get(i, np.zeros_like(obj_all))
        d4 = cv2.GaussianBlur(np.repeat(np.repeat(dirty, 4, 0), 4, 1).astype(np.float32), (0, 0), 3.0)
        split_smooth.dirty[key] = np.clip(d4 * 1.5, 0, 1)[y * 4:y * 4 + 160, x * 4:x * 4 + 128]
    return out


def differs4(a, b, grow=2):
    """Где два оригинала k=1 (32x40) различаются - кран и бутылка на кадре 14 против голой стойки 13, -
    маска x4 0..1, расширенная на grow пикселей."""
    d = np.any(np.asarray(a.convert("RGBA")) != np.asarray(b.convert("RGBA")), -1).astype(np.uint8)
    d = cv2.dilate(d, np.ones((2 * grow + 1, 2 * grow + 1), np.uint8))
    up = cv2.resize(d.astype(np.float32), (d.shape[1] * 4, d.shape[0] * 4), interpolation=cv2.INTER_LINEAR)
    return np.clip(cv2.GaussianBlur(up, (0, 0), 2.0), 0, 1)


def unify(comp, at, pieces, band):
    """Один кадр на все его клетки ряда; полосы у стыков - из эталонной пары своей оси.
    Возвращает ({(НАБОР, кадр): картинка}, {ось: (ключ левой, ключ правой)})."""
    keys = [k for k, _o in comp["members"]]
    whole, _ = osr.compose(comp)
    lab4 = np.repeat(np.repeat(label_map(comp, at, (whole.height, whole.width)), 4, 0), 4, 1)
    idx = {(k[2], k[3]): i for i, k in enumerate(keys)}
    frame_of = {i: (k[0], k[1]) for i, k in enumerate(keys)}
    refs, has = {}, {}
    for axis, (dx, dy) in AXES.items():
        pairs = [(i, idx[(c[0] + dx, c[1] + dy)]) for c, i in idx.items() if (c[0] + dx, c[1] + dy) in idx]
        for a, b in pairs:
            has.setdefault((frame_of[a], axis, +1), True)
            has.setdefault((frame_of[b], axis, -1), True)
        if not pairs:
            continue
        # эталон - пара одинаковых кадров самого частого кадра ряда (у него больше всего стыков), из середины
        cnt = Counter(frame_of[a] for a, b in pairs if frame_of[a] == frame_of[b])
        same = [(a, b) for a, b in pairs if cnt and frame_of[a] == frame_of[b] == cnt.most_common(1)[0][0]]
        pool = same or pairs
        refs[axis] = pool[len(pool) // 2]
    # опорный экземпляр кадра - медоида: клетка, ближе всех к остальным своим копиям. Край высокого соседа
    # (верх пивной колонки над 14) уходит в кайму соседней клетки, и кадр, стоящий пять раз, повторил бы
    # обрывок крана на каждой; у медоиды такого нет - обрывок есть не у всех копий
    # Но прежде: (1) не конец ряда - торец стойки у стены повторялся на каждом стыке голых клеток;
    # (2) без чужого соседа, нарисованного РАНЬШЕ: поддон крана 14 лежит на стыке в куске следующей за ним 13,
    # и такой 13 повторял поддон на каждой голой клетке; чужой сосед, нарисованный позже, стык закрывает сам
    arr = {i: np.asarray(pieces[keys[i]], np.float32) for i in range(len(keys))}
    inv = {i: c for c, i in idx.items()}
    near4 = ((1, 0), (-1, 0), (0, 1), (0, -1))

    def rank(i, inst):
        c = inv[i]
        nb = [idx[(c[0] + dx, c[1] + dy)] for dx, dy in near4 if (c[0] + dx, c[1] + dy) in idx]
        before = sum(1 for j in nb if frame_of[j] != frame_of[i] and j < i)     # members - в порядке рисования
        after = sum(1 for j in nb if frame_of[j] != frame_of[i] and j > i)
        return (len(nb) < 2, before, after, sum(float(np.abs(arr[i] - arr[j]).mean()) for j in inst))
    base = {}
    for f in set(frame_of.values()):
        inst = [i for i in range(len(keys)) if frame_of[i] == f]
        base[f] = min(inst, key=lambda i: rank(i, inst))
    out = {}
    dirty = getattr(split_smooth, "dirty", {})
    for f, i in base.items():
        img = np.asarray(pieces[keys[i]], np.float32).copy()
        # грязь - чужое украшение в куске (макушка крана над голой 13): это место берём у другой копии
        # того же кадра, где оно чистое; копии - в том же порядке предпочтения
        left = dirty.get(keys[i], np.zeros(img.shape[:2], np.float32))
        inst = sorted((j for j in range(len(keys)) if frame_of[j] == f and j != i),
                      key=lambda j: rank(j, [j]))
        for j in inst:
            if left.max() < 0.02:
                break
            dj = dirty.get(keys[j], np.zeros_like(left))
            wt = (left * (1.0 - dj))[..., None]
            img = img * (1.0 - wt) + np.asarray(pieces[keys[j]], np.float32) * wt
            left = left * dj
        for axis, (a, b) in refs.items():
            for side, (me, other, src) in ((+1, (a, b, a)), (-1, (b, a, b))):
                if not has.get((f, axis, side)):
                    continue
                w = joint_weight(lab4, me, other, at[keys[me]], band)[..., None]
                # полоса стыка берётся у эталона только там, где оригиналы кадров совпадают: кран на 14 стоит
                # у самого стыка, и эталонная пара голой стойки стирала ему основание и носики
                if frame_of[src] != f:
                    w = w * (1.0 - differs4(comp["spr"][keys[i]], comp["spr"][keys[src]]))[..., None]
                ref = np.asarray(pieces[keys[src]], np.float32)
                img = img * (1.0 - w) + ref * w
        out[f] = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGBA")
    return out, {ax: (keys[a], keys[b]) for ax, (a, b) in refs.items()}


def on_floor(im):
    bg = Image.new("RGBA", im.size, po.FLOOR + (255,))
    bg.alpha_composite(im)
    return bg.convert("RGB")


def xbrz4(img):
    return ss.xbrz_scale(np.asarray(img.convert("RGBA"), np.float32)[None], 4)[0]


def anim_neutral(origs):
    """Кадры анимации k=1 -> один нейтральный: цвет - медиана по кадрам (огонь, горящий в одном кадре из
    четырёх, уходит), альфа - общая часть (звуковые штрихи, которые есть не во всех кадрах, уходят)."""
    a = np.stack([np.asarray(o.convert("RGBA")) for o in origs]).astype(np.float32)
    out = np.median(a, 0)
    out[..., 3] = a[..., 3].min(0)
    out[out[..., 3] == 0] = 0
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def anim_frames(base, origs, neutral):
    """Нарисованный нейтральный кадр x4 -> кадры анимации (R-071: тело одно на все кадры, иначе мигает).
    Где кадр анимации отличается от нейтрального (огни, штрихи), цвет берётся из оригинала кадра, увеличенного
    xBRZ, а яркость - из рисунка: множитель по яркости, как R-030, - тон не уводит. Вне тела (звуковые штрихи)
    - сам оригинал xBRZ."""
    lum = lambda v: v[..., 0] * 0.299 + v[..., 1] * 0.587 + v[..., 2] * 0.114   # noqa: E731
    b = np.asarray(base.convert("RGBA"), np.float32)
    n0 = np.asarray(neutral, np.int16)
    upn = xbrz4(neutral)
    res = []
    for o in origs:
        ok = np.asarray(o.convert("RGBA"), np.int16)
        diff = np.any(ok != n0, -1).astype(np.float32) * 255
        mk = Image.fromarray(np.dstack([diff] * 3 + [np.full_like(diff, 255)]).astype(np.uint8), "RGBA")
        m = cv2.GaussianBlur(np.clip(xbrz4(mk)[..., 0] / 255.0, 0, 1), (0, 0), 1.2)[..., None]
        upk = xbrz4(o)
        ratio = ((lum(b) + 2) / (lum(upn) + 2))[..., None]
        recol = np.clip(upk[..., :3] * ratio, 0, 255)
        img = b.copy()
        img[..., :3] = b[..., :3] * (1 - m) + recol * m
        # вне тела - штрихи оригинала кадра поверх
        la = np.clip(upk[..., 3:4] * m, 0, 255) * (b[..., 3:4] < 128)
        a0 = img[..., 3:4]
        a1 = la + a0 * (1 - la / 255.0)
        img[..., :3] = np.where(a1 > 0, (upk[..., :3] * la + img[..., :3] * a0 * (1 - la / 255.0)) / np.maximum(a1, 1e-3),
                                img[..., :3])
        img[..., 3:4] = a1
        res.append(Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGBA"))
    return res


def map_preview(terrain, block, frames, z, keys, path, k=4):
    """Нижний этаж карты с новыми кадрами поверх пака, который читает игра (R-087), кроп вокруг ряда."""
    w = mm.World()
    sp = w.sprite
    w.sprite = lambda s, f, src: sp(s.upper() if src else s, f, src)    # R-117: ключ - заглавное имя
    for (s, f), im in frames.items():
        w.hd[(po.MOD_TERRAIN, s, f)] = im
    im, _m = mm.render(w, terrain, block, po.MOD_TERRAIN, k, None, maxz=z)
    old = mm.render(mm.World(), terrain, block, po.MOD_TERRAIN, k, None, maxz=z)[0]
    _sx, sy, sz, _c = mm.read_block(w, block)
    ox, oy = sy * 16, sz * 24 + 8
    xs = [ox + (x - y) * 16 for (_s, _f, x, y) in keys]
    ys = [oy + (x + y) * 8 - z * 24 for (_s, _f, x, y) in keys]
    box = ((min(xs) - 48) * k, (min(ys) - 32) * k, (max(xs) + 80) * k, (max(ys) + 64) * k)
    a, b = old.crop(box).convert("RGB"), im.crop(box).convert("RGB")
    sheet = Image.new("RGB", (a.width, a.height * 2 + 30), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    d.text((4, 2), "game now", fill=(255, 255, 0))
    sheet.paste(a, (0, 14))
    d.text((4, a.height + 16), "one piece", fill=(255, 255, 0))
    sheet.paste(b, (0, a.height + 30))
    sheet.save(path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--terrain", required=True)
    ap.add_argument("--block", required=True)
    ap.add_argument("--set", required=True, dest="set_name")
    ap.add_argument("--frames", required=True, help="кадры предмета через запятую: 12,13,14,16")
    ap.add_argument("--z", type=int, default=0, help="этаж карты")
    ap.add_argument("--run", type=int, default=0, help="какой ряд брать: 0 - самый длинный")
    ap.add_argument("--hint", default="")
    ap.add_argument("--hint-key", default="", dest="hint_key", help="ключ в --hints")
    ap.add_argument("--hints", default="art/objects/long_hints.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--input", default="xbrz", help="xbrz,bicubic - вход модели, можно оба")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run", help="только раскладка и входы, без модели")
    ap.add_argument("--recut", action="store_true", help="нарезать заново из сохранённого <вход>/raw.png, без модели")
    ap.add_argument("--near", default="", help="x,y,r - ряд только из клеток рядом с (x, y): окно в длинной стене")
    ap.add_argument("--keep", default="", help="кадры набора, которые остаются из пака игры (рисуются для связи, "
                                               "не выходят; стыки нового кадра сводятся к ним)")
    ap.add_argument("--overlay", type=int, default=None, help="кадр голой стены того же набора: новый кадр "
                                                                "кладётся на него из пака только там, где оригинал "
                                                                "от неё отличается (окно в стене)")
    ap.add_argument("--glass", default="", help="R,G,B - с --overlay: внутренность окна в эскизе ровным стеклом")
    ap.add_argument("--glass-alpha", type=float, default=190, dest="glass_alpha",
                    help="непрозрачность стекла в готовом кадре (у оригинала там дыра)")
    ap.add_argument("--anim", default="", help="кадры анимации записи через запятую (18,19,20,21): рисуется один "
                                               "нейтральный, кадры - перекраской огней (R-071)")
    ap.add_argument("--seed", type=int, default=2711)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=2.0, help="ряд длинный: родные для Qwen-2.1 2 Мп, не 1")
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--grow", type=int, default=2)
    ap.add_argument("--soft", type=int, default=40)
    ap.add_argument("--pad", type=int, default=3)
    ap.add_argument("--tone", type=float, default=0.7)
    ap.add_argument("--band", type=int, default=24, help="ширина полосы у стыка, пикселей x4")
    ap.add_argument("--models", default=None)
    ap.add_argument("--model", default="")
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    args = ap.parse_args()

    what = args.hint
    if not what and args.hint_key:
        with open(args.hints, encoding=ENC) as f:
            what = json.load(f).get(args.hint_key, "")
    if not what and not args.dry_run:
        raise SystemExit("нет описания предмета (--hint или --hint-key в %s) - R-007" % args.hints)
    world = mm.World()
    frames = {int(v) for v in args.frames.split(",") if v}
    near = tuple(int(v) for v in args.near.split(",")) if args.near else None
    found, runs = run_cells(world, args.terrain, args.block, args.set_name.upper(), frames, args.z, near)
    if not runs:
        raise SystemExit("на карте нет клеток %s %s" % (args.set_name, sorted(frames)))
    for n, r in enumerate(runs):
        print("ряд %d: %d клеток: %s" % (n, len(r), " ".join("%d,%d:%d" % (x, y, found[(x, y)][1]) for x, y in r)),
              flush=True)
    run = runs[args.run]
    comp = make_comp(world, found, run, args.z)
    S = args.set_name.upper()
    kept = {}
    for f in (int(v) for v in args.keep.split(",") if v):
        kept[(S, f)] = Image.open(os.path.join(po.MOD_TERRAIN, S + ".PCK", "%d.png" % f)).convert("RGBA")
    anim, anim_orig, neutral = [int(v) for v in args.anim.split(",") if v], [], None
    if anim:
        if len(run) != 1:
            raise SystemExit("--anim - только для предмета в одну клетку, в ряду %d" % len(run))
        akey = comp["members"][0][0]
        anim_orig = [world.sprite(found[run[0]][0], f, None).convert("RGBA") for f in anim]
        neutral = anim_neutral(anim_orig)
        comp["spr"][akey] = neutral
    whole, at = osr.compose(comp)
    if args.glass and args.overlay is not None:
        # эскиз окна без перекладин: модель повторяет эскиз, и доски оригинала сквозь стекло возвращались.
        # Внутренность окна (отличие от голой стены, без рамки в 2 пикселя) - ровным цветом стекла
        g = tuple(int(v) for v in args.glass.split(",")) + (255,)
        wa = np.asarray(whole).copy()
        for key, _o in comp["members"]:
            _win, inner = window_region(comp["spr"][key])
            x, y = at[key]
            wa[y:y + 40, x:x + 32][inner] = g
        whole = Image.fromarray(wa, "RGBA")
    bb = whole.split()[3].getbbox()
    box = (max(0, bb[0] - args.pad), max(0, bb[1] - args.pad),
           min(whole.width, bb[2] + args.pad), min(whole.height, bb[3] + args.pad))
    frame = whole.crop(box)
    hows = [h for h in args.input.split(",") if h]
    os.makedirs(args.out, exist_ok=True)
    whole.resize((whole.width * 4, whole.height * 4), Image.NEAREST).save(os.path.join(args.out, "orig_x4.png"))
    for how in hows:
        os.makedirs(os.path.join(args.out, how), exist_ok=True)
        model_input(frame, args.zoom, how).save(os.path.join(args.out, how, "input.png"))
    print("ряд %dx%d (k=1), входы: %s; описание: %s" % (whole.width, whole.height, ", ".join(hows), what[:90]),
          flush=True)
    if args.dry_run:
        return

    ns = argparse.Namespace(models=args.models or po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model=args.model,
                            qwen21_steps=args.steps, qwen21_cfg=args.cfg, qwen21_mp=args.mp,
                            qwen21_strength=0.0, qwen21_offload=args.offload, qwen21_thrifty=False,
                            qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    # --recut: нарезка заново из сохранённого raw.png, без модели
    painter = None if args.recut else po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    po.gen_fire.NEGATIVE = po.NEGATIVE
    prompt = po.STYLE["strict"].replace("{what}", what)
    for how in hows:
        t0 = time.time()
        d = os.path.join(args.out, how)
        if painter is None:
            hd = Image.open(os.path.join(d, "raw.png")).convert("RGB")
        else:
            hd = po.gen_fire.run_pass(painter, args, prompt, model_input(frame, args.zoom, how), args.seed)
            po.gen_hd.save_png(hd, os.path.join(d, "raw.png"))
        part = po.match_tone(po.cut_out(hd, frame, args.grow, args.soft), frame, args.tone)
        cut = Image.new("RGBA", (whole.width * 4, whole.height * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        on_floor(cut).save(os.path.join(d, "whole.png"))
        pieces = split_smooth(cut, comp, at, args.grow)
        for key in pieces:
            if (key[0], key[1]) in kept:
                pieces[key] = kept[(key[0], key[1])]
        out, refs = unify(comp, at, pieces, args.band)
        out.update(kept)
        if args.overlay is not None:
            # отдельный предмет на стене: кладётся на кадр пака игры только там, где оригинал отличается
            # от голой стены, - доски вокруг остаются те же, что у соседних клеток
            # (кадры голой стены и стены с окном различаются тенями досок везде, поэтому окно ищется по цвету)
            plain = Image.open(os.path.join(po.MOD_TERRAIN, S + ".PCK", "%d.png" % args.overlay)).convert("RGBA")
            for (s, f) in list(out):
                if (s, f) in kept or f == args.overlay:
                    continue
                win, inner = window_region(world.sprite(found[run[0]][0], f, None))
                win = cv2.dilate(win.astype(np.uint8), np.ones((3, 3), np.uint8)) * 255
                m = np.asarray(po.smooth_silhouette(Image.fromarray(win, "L"), 4), np.float32)[..., None] / 255.0
                mix = np.asarray(plain, np.float32) * (1 - m) + np.asarray(out[(s, f)], np.float32) * m
                if args.glass:
                    # у оригинала сквозь окно видно, что за стеной: стекло полупрозрачное
                    gi = np.asarray(po.smooth_silhouette(Image.fromarray(inner.astype(np.uint8) * 255, "L"), 4),
                                    np.float32) / 255.0
                    mix[..., 3] = mix[..., 3] * (1 - gi) + np.minimum(mix[..., 3], args.glass_alpha) * gi
                out[(s, f)] = Image.fromarray(np.clip(mix, 0, 255).astype(np.uint8), "RGBA")
        if anim:
            base_f = (S, found[run[0]][1])
            for f, im in zip(anim, anim_frames(out[base_f], anim_orig, neutral)):
                out[(S, f)] = im
        for (s, f), im in out.items():
            if (s, f) in kept:
                continue
            os.makedirs(os.path.join(d, "series", s + ".PCK"), exist_ok=True)
            po.gen_hd.save_png(im, os.path.join(d, "series", s + ".PCK", "%d.png" % f))
        built = osr.compose(comp, {k: out[(k[0], k[1])] for k, _o in comp["members"]}, 4)[0]
        o4 = whole.resize((whole.width * 4, whole.height * 4), Image.NEAREST)
        sheet = Image.new("RGB", (o4.width, o4.height * 3 + 48), (30, 30, 34))
        dr = ImageDraw.Draw(sheet)
        for j, (im, t) in enumerate(((o4, "original x4"), (cut, "painted as one piece"),
                                     (built, "assembled from frames (one frame per all its cells)"))):
            dr.text((4, j * (o4.height + 16) + 2), t, fill=(255, 255, 0))
            sheet.paste(on_floor(im), (0, j * (o4.height + 16) + 14))
        sheet.save(os.path.join(d, "sheet.png"))
        mp = map_preview(args.terrain, args.block, out, args.z, [k for k, _o in comp["members"]],
                         os.path.join(d, "map.png"))
        print("%s: кадров %d (%s), эталоны стыков %s, %s; %s" % (
            how, len(out), " ".join("%d" % f for _s, f in sorted(out)),
            {ax: "%d,%d|%d,%d" % (a[2], a[3], b[2], b[3]) for ax, (a, b) in refs.items()},
            po.gen_hd.human_time(time.time() - t0), mp), flush=True)


if __name__ == "__main__":
    main()
