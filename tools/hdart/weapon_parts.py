#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка конструкции оружия по частям (указание специалиста 05.10): размер, положение и направление КАЖДОЙ
детали ответа против оригинала, до любой ручной доводки.

Разметка частей оригинала - art/items/weapons100-v3/parts/<W>.json, пишется человеком (агентом) по кадру 32x48 с
сеткой и по описанию what_v2 (строки, столбцы деталей). Часть - прямоугольники в пикселях базы (столбцы и строки
включительно); пиксель оригинала берёт первая по списку часть, чей прямоугольник его накрывает. Часть со status
UNKNOWN (по кадру не опознать) - на REVIEW, генерацию не держит в «проверенных»; магазин несёт кадры боеприпаса
с карточки и форму словами (ammo).

Проверка: ответ ставится равномерным масштабом на габарит оригинала (как weapon_from_ref, без деформации). Для
каждой части ищется жёсткое преобразование ответа около её центра - сдвиг, поворот, масштаб вдоль оси части и
поперёк, - при котором ответ лучше всего совпадает с частью оригинала по покрытию (в пикселях базы, 4x4 выборки на
пиксель) и по цвету. Найденное преобразование и есть отличие детали: сдвиг - положение, масштаб - размер, поворот -
направление. Число - в пикселях базы на конце детали, а не в процентах: у детали в 6 пикселей 1 пиксель - 17 %.
Ответ при этом НЕ меняется: это мерка, не подгонка (R-208, R-226).

Направление, по которому сдвиг не меняет совпадения (деталь внутри корпуса того же цвета), не мерится - пишется
«не определяется», а не PASS. Лишнее (ответ там, где у оригинала пусто, дальше пикселя) - кусками от 3 пикселей
базы на REVIEW: это деталь, которой в оригинале нет.

Правка 05.10 (разбор специалиста: проверка давала и ложный FAIL, и ложный PASS):
- принадлежность пикселей (part_labels): прямоугольники разметки уточняются по материалу у границ деталей - пиксель
  у края уходит соседу, если его цвет ближе к ядру соседа. Разметка нужна для принадлежности, мерки по ответу
  лесенку оригинала не повторяют;
- стык: NOT_MEASURED (цвета близки, граница размыта у оригинала или ответа, стык не прямой, деталь-линия) - не PASS;
  AMBIGUOUS (стороны найденной границы ближе к чужим сторонам оригинала или контраст другой в 2 раза - найдена
  граница других материалов) - сдвигом не считается. Вторая правка 05.10: стыки и цвет детали меряются цветом, а
  цветовая мерка вспомогательная - они не дефект и не понижают итог, а становятся вопросами к независимой проверке
  (overall -> questions, решает weapon_accept). Итог - три раздельных: конструкция (покрытие, размер), размещение
  (placement), рисунок (weapon_accept);
- профиль длинной детали (клинок, ствол): ширина поперёк оси по срезам вдоль длины против оригинала; FAIL по доле
  срезов, по выбросам и по серии подряд (местное сужение острия);
- размер - по родной альфе ответа до нарезки, допуск ±3 % без поблажки в полпикселя; округление на сетке k=4 -
  отдельно, не вердикт;
- срез размещением (за кадром и за клетками) - самостоятельный дефект; делится на срезанное в габарите оригинала
  (оригинал сам заходит за клетки - средство метка .wide, решает Vitali) и за габаритом (ответ выступил дальше).
Контроль: tools/test_weapon_parts.py.

  py -3.13 tools/hdart/weapon_parts.py show --only W-013,W-014      лист разметки (сетка, части, боеприпас, текст)
  py -3.13 tools/hdart/weapon_parts.py check --only W-013 --cut <папка нарезки> [--tag t]
     --cut: нарезка weapon_from_ref (meta/<тип>.json: ref - ответ модели, file - кадр пака); проверяются оба:
     сырой ответ (равномерно на габарит, без среза клетками) и PNG пака.
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import item_asset_check as iac         # noqa: E402
import weapon_fit as wf                 # noqa: E402

ENC = "utf-8-sig"
PARTS = "art/items/weapons100-v3/parts"
WHAT2 = "art/items/weapons100-v1/describe/what_v2.tsv"
CARDS = "art/items/weapons100-v1/ammo_cards/cards.json"
EXPORT = "census/items/export/exp_piratez/BIGOBS.PCK.png"
K = 4
SUB = 4                                  # выборок на пиксель базы по оси

# пороги геометрии детали, пиксели базы (на конце детали)
POS_OK, POS_REVIEW = 1.0, 2.0
SIZE_OK, SIZE_REVIEW = 1.0, 2.0
TURN_OK, TURN_REVIEW = 1.0, 2.0
SHAPE_OK, SHAPE_REVIEW = 0.75, 0.60      # совпадение покрытия детали после лучшего жёсткого преобразования
SHAPE_THIN_REVIEW = 0.45                 # то же для тонкой детали (поперёк до 3 пикселей): ниже - FAIL
COLOR_REVIEW = 28.0                      # средняя разница цвета (Lab, яркость с весом 0.6) - другой материал
EXTRA_MIN = 3                            # лишнее: кусок от 3 пикселей базы
FLAT = 0.004                             # совпадение меняется меньше - направление не определяется
COLOR_W = 0.15                           # вес цвета в совпадении (покрытие - 1)

# Пороги ниже заданы ДО контрольных прогонов 05.10 (указание специалиста) и по их итогам не подгонялись.
# принадлежность пикселя: пиксель у края прямоугольника (до REFINE_RING пикселей) уходит соседней детали, если его
# цвет ближе к ядру соседа на REFINE_DE. Это разметка материалов, не повтор лесенки: мерки по ответу её не копируют
REFINE_DE, REFINE_RING = 10.0, 2
MIXED_MIN, MIXED_FRAC = 3, 0.10          # после уточнения в детали столько пикселей цвета соседа - вопрос разметки
# стык: контакт двух деталей - отрезок. Невязка прямой по серединам рёбер контакта, угол нормали прямой к средней
# нормали рёбер, длина контакта - иначе стык не прямой и не мерится
JOINT_RESID, JOINT_ANGLE, JOINT_MINLEN = 0.75, 30.0, 1.5
JOINT_CONTRAST = 2.0                     # контраст сторон ответа против оригинала больше в 2 раза (или меньше в 2) -
                                         # найдена граница других материалов
# профиль длинной детали: ширина поперёк оси по срезам в 1 пиксель базы, сглаживание окном 3, крайние срезы не в счёт
PROF_LEN, PROF_RATIO = 8.0, 2.5
PROF_REV, PROF_FAIL, PROF_FRAC = 0.5, 0.75, 0.25
PROF_SPIKE, PROF_SPIKE_N = 1.5, 2
# серия: столько срезов ПОДРЯД с отклонением от PROF_FAIL (PROF_REV) - FAIL (REVIEW), независимо от длины детали.
# Добавлено после контроля 05.10: сужение острия W-079 на пиксель (срезы 2-5, на 25-30 % ширины) проходило PASS -
# доля от всей длины клинка 3 из 18 меньше PROF_FRAC. Пороги отклонения прежние, длина серии задана до прогона
PROF_RUN = 3
# размер по родной альфе ответа (до нарезки), равномерная постановка на габарит оригинала, проценты; без поблажки
# в полпикселя оригинала. Допуск Vitali ±3 % - граница приёмки: за ним FAIL (прежняя полоса REVIEW 3-6 % была моей
# добавкой и отправляла предмет человеку, хотя допуск задан; убрана 05.10 по разбору специалиста)
SIZE_TOL, SIZE_FAIL = 3.0, 3.0
# срез размещением: альфа за холстом и за клетками предмета, в HD-пикселях (k=4). Пиксель базы - 16 HD-пикселей
CUT_MIN, CUT_FAIL = 1.0, 16.0

COLORS = [(230, 80, 80), (80, 200, 90), (80, 140, 240), (240, 200, 60), (200, 90, 220), (60, 210, 210),
          (250, 140, 40), (160, 160, 160), (140, 230, 140), (230, 140, 180), (120, 100, 230), (200, 200, 110)]
VERD = {"PASS": 0, "REVIEW": 1, "FAIL": 2}
NOT_MEASURED = "NOT_MEASURED"            # стык не измерен: не PASS, но и не дефект - вопрос к другому способу проверки


def font(sz):
    for p in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def read_tsv(p):
    with open(p, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def what2():
    return {r["master"]: r for r in read_tsv(WHAT2)}


def cards():
    with open(CARDS, encoding=ENC) as f:
        return {c["master"]: c for c in json.load(f)}


def load_parts(master):
    p = os.path.join(PARTS, master + ".json")
    if not os.path.exists(p):
        return None
    with open(p, encoding=ENC) as f:
        return json.load(f)


def label_map(spec, m):
    """Метки частей по пикселям оригинала: -1 пусто, -2 непрозрачное без части, i - номер части."""
    lab = np.full(m.shape, -1, np.int32)
    lab[m] = -2
    for i, p in enumerate(spec["parts"]):
        z = np.zeros(m.shape, bool)
        for c0, r0, c1, r1 in p["rects"]:
            z[r0:r1 + 1, c0:c1 + 1] = True
        lab[(lab == -2) & z] = i
    return lab


def de_w(a, b):
    """ΔE Lab с весом яркости 0.6 (как везде в проверке); a (...,3), b (3,) или (...,3)."""
    d = np.asarray(a, np.float32) - np.asarray(b, np.float32)
    return np.sqrt((0.6 * d[..., 0]) ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2)


N4 = ((0, 1), (0, -1), (1, 0), (-1, 0))


def part_labels(spec, m, lab_rgb):
    """Метки по прямоугольникам, уточнённые по материалу у границ деталей (до REFINE_RING пикселей от края):
    прямоугольник захватывает пиксели соседней детали (дерево рукояти в метке колодки W-024). Пиксель уходит
    соседу, если касается его и ближе к ядру соседа (медиана цвета вдали от границ) на REFINE_DE. Возвращает
    (метки, переназначенные [(x, y, из, в, ΔE своя, ΔE соседа)], смесь {деталь: (сосед, пикс)}).
    spec["refine"] = false - только прямоугольники."""
    lab = label_map(spec, m)
    n = len(spec["parts"])
    if spec.get("refine") is False or n < 2:
        return lab, [], {}
    H, W = m.shape
    core = []
    for i in range(n):
        z = lab == i
        far = z & ~wf.dilate((lab >= 0) & ~z, REFINE_RING)
        src = far if far.sum() >= 3 else z
        core.append(np.median(lab_rgb[src], 0) if src.any() else None)
    moved = []
    for _ring in range(REFINE_RING):
        new = lab.copy()
        for y, x in zip(*np.nonzero(lab >= 0)):
            i = lab[y, x]
            if core[i] is None:
                continue
            nb = {int(lab[y + dy, x + dx]) for dy, dx in N4 if 0 <= y + dy < H and 0 <= x + dx < W}
            nb = [j for j in nb if j >= 0 and j != i and core[j] is not None]
            if not nb:
                continue
            di = float(de_w(lab_rgb[y, x], core[i]))
            dj, j = min((float(de_w(lab_rgb[y, x], core[j])), j) for j in nb)
            if dj + REFINE_DE < di:
                new[y, x] = j
                moved.append((int(x), int(y), spec["parts"][i]["name"], spec["parts"][j]["name"], round(di, 1),
                              round(dj, 1)))
        if (new == lab).all():
            break
        lab = new
    # смесь: в детали остались пиксели цвета соседней детали (соседней по разметке) - разметку смотреть человеку
    mixed = {}
    for i in range(n):
        z = lab == i
        if core[i] is None or not z.any():
            continue
        touch = wf.dilate(z, 1)
        for j in range(n):
            if j == i or core[j] is None or not (touch & (lab == j)).any():
                continue
            k = int((z & (de_w(lab_rgb, core[j]) + REFINE_DE < de_w(lab_rgb, core[i]))).sum())
            if k >= MIXED_MIN and k >= MIXED_FRAC * z.sum():
                mixed[spec["parts"][i]["name"]] = (spec["parts"][j]["name"], k)
    return lab, moved, mixed


_SHEET = None


def ammo_frame(n):
    """Кадр боеприпаса BIGOBS из выгрузки движка (индекс 0 прозрачен), RGBA 32x48; пустой - None."""
    global _SHEET
    if _SHEET is None:
        sh = Image.open(EXPORT)
        _SHEET = (np.asarray(sh), np.asarray(sh.getpalette()[:768], np.uint8).reshape(-1, 3))
    idx, pal = _SHEET
    r, c = divmod(int(n), 16)
    t = idx[r * 48:(r + 1) * 48, c * 32:(c + 1) * 32]
    if not t.any():
        return None
    return Image.fromarray(np.dstack([pal[t], np.where(t == 0, 0, 255).astype(np.uint8)]), "RGBA")


def on_dark(im, bg=(28, 30, 34)):
    b = Image.new("RGBA", im.size, bg + (255,))
    b.alpha_composite(im.convert("RGBA"))
    return b.convert("RGB")


def wrap(d, text, f, w):
    out, line = [], ""
    for word in text.split():
        t = (line + " " + word).strip()
        if d.textlength(t, font=f) > w and line:
            out.append(line)
            line = word
        else:
            line = t
    if line:
        out.append(line)
    return out


# ------------------------------------------------------------------------------------------------- лист разметки

def show(masters, out):
    W2, C = what2(), cards()
    L = wf.list_rows()
    Z = 12
    f, fs = font(15), font(12)
    tiles = []
    for ms in masters:
        t = L[ms]["type"]
        rgb, m = wf.original(t)
        H, W = m.shape
        base = Image.fromarray(np.where(m[..., None], rgb, np.array([28, 30, 34], np.float32)).astype(np.uint8))
        big = base.resize((W * Z, H * Z), Image.NEAREST)
        d = ImageDraw.Draw(big)
        for x in range(W + 1):
            d.line([(x * Z, 0), (x * Z, H * Z)], fill=(70, 72, 80) if x % 4 else (120, 120, 60))
        for y in range(H + 1):
            d.line([(0, y * Z), (W * Z, y * Z)], fill=(70, 72, 80) if y % 4 else (120, 120, 60))
        spec = load_parts(ms)
        lab_im = None
        legend = []
        if spec:
            lab, moved, mixed = part_labels(spec, m, to_lab(rgb))
            ov = np.zeros((H, W, 3), np.uint8) + 28
            for i in range(len(spec["parts"])):
                ov[lab == i] = COLORS[i % len(COLORS)]
            ov[lab == -2] = (255, 255, 255)
            lab_im = Image.fromarray(ov).resize((W * Z, H * Z), Image.NEAREST)
            dl = ImageDraw.Draw(lab_im)
            # переназначенные по материалу пиксели - белая рамка: проверить глазом
            for x, y, *_ in moved:
                dl.rectangle([x * Z, y * Z, (x + 1) * Z - 1, (y + 1) * Z - 1], outline=(255, 255, 255), width=2)
            if moved:
                legend.append("рамка: %d пикс переназначены по материалу" % len(moved))
            for a_, (b_, k_) in mixed.items():
                legend.append("смесь: в %s %d пикс цвета %s" % (a_, k_, b_))
            for i, p in enumerate(spec["parts"]):
                ys, xs = np.nonzero(lab == i)
                if len(xs):
                    dl.text((xs.mean() * Z, ys.mean() * Z), str(i), fill=(0, 0, 0), font=f, anchor="mm")
                legend.append("%d %s (%s)%s%s" % (i, p["name"], p["kind"], " UNKNOWN" if p.get("status") == "UNKNOWN"
                                                  else "", (" - " + p["note"]) if p.get("note") else ""))
            nlab = int((lab == -2).sum())
            if nlab:
                legend.append("белое: %d пикс без части" % nlab)
        w2 = W2.get(ms, {})
        card = C.get(ms, {})
        ammo = []
        for sd in card.get("slots", []):
            for x in sd["ammo"]:
                if x.get("frame") is not None and len(ammo) < 4:
                    fr = ammo_frame(x["frame"])
                    if fr is not None:
                        ammo.append((x["en"], on_dark(fr).resize((32 * 5, 48 * 5), Image.NEAREST)))
        colw = 560
        tw = W * Z * (2 if lab_im else 1) + 30 + colw
        tile = Image.new("RGB", (tw, H * Z + 60 + (48 * 5 + 30 if ammo else 0)), (20, 21, 25))
        dt = ImageDraw.Draw(tile)
        dt.text((8, 6), "%s %s  %s" % (ms, t, w2.get("identity", "")), fill=(240, 220, 120), font=f)
        tile.paste(big, (8, 30))
        x = 8 + W * Z + 10
        if lab_im:
            tile.paste(lab_im, (x, 30))
            x += W * Z + 10
        y = 30
        for k in ("orientation", "magazine", "feed", "details", "materials", "identity_note"):
            for ln in wrap(dt, "%s: %s" % (k, w2.get(k, "")), fs, colw - 10)[:7]:
                dt.text((x, y), ln, fill=(205, 205, 210), font=fs)
                y += 15
            y += 4
        for ln in legend:
            for l2 in wrap(dt, ln, fs, colw - 10):
                dt.text((x, y), l2, fill=(150, 230, 150), font=fs)
                y += 15
        ax = 8
        for name, im in ammo:
            dt.text((ax, H * Z + 36), name[:30], fill=(200, 200, 205), font=fs)
            tile.paste(im, (ax, H * Z + 52))
            ax += im.width + 12
        tiles.append(tile)
    Wt = max(t.width for t in tiles)
    sheet = Image.new("RGB", (Wt, sum(t.height for t in tiles) + 10 * len(tiles)), (14, 15, 18))
    y = 0
    for t in tiles:
        sheet.paste(t, (0, y))
        y += t.height + 10
    sheet.save(out)
    print(out, sheet.size)


# ------------------------------------------------------------------------------------------------- проверка

def to_lab(rgb):
    return wf.to_lab(np.asarray(rgb, np.float32).reshape(-1, 3)).reshape(np.shape(rgb))


def bilinear(img, X, Y):
    """img HxWxC, X/Y в пикселях img (центр пикселя i - i+0.5); вне - 0."""
    H, W = img.shape[:2]
    x, y = X - 0.5, Y - 0.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    out = 0
    for dy, wy in ((0, 1 - fy), (1, fy)):
        for dx, wx in ((0, 1 - fx), (1, fx)):
            xi, yi = x0 + dx, y0 + dy
            ok = ((xi >= 0) & (xi < W) & (yi >= 0) & (yi < H))[..., None]
            v = img[np.clip(yi, 0, H - 1), np.clip(xi, 0, W - 1)]
            out = out + np.where(ok, v, 0) * wx * wy
    return out


class Answer:
    """Ответ в кадре k=4 (128x192): предумноженный цвет и альфа для выборки в координатах базы."""

    def __init__(self, rgba, off=0):
        """off - поле холста в пикселях базы: сырой ответ ставится с полем, чтобы вылезшее за кадр не срезалось."""
        a = rgba[..., 3:4].astype(np.float32) / 255.0
        self.pre = np.dstack([rgba[..., :3].astype(np.float32) * a, a])
        self.off = off

    def sample(self, bx, by):
        """bx, by - координаты базы (float); возвращает предумноженный RGB и альфу."""
        v = bilinear(self.pre, (bx + self.off) * K, (by + self.off) * K)
        return v[..., :3], v[..., 3]


def cell_avg(ans, px, py, T):
    """Средние по 4x4 выборкам в каждом пикселе базы (px, py - целые) после преобразования T."""
    cx, cy, ang, sa, sc, tx, ty, phi = T
    o = (np.arange(SUB) + 0.5) / SUB
    ox, oy = np.meshgrid(o, o)
    X = px[:, None] + ox.ravel()[None, :]
    Y = py[:, None] + oy.ravel()[None, :]
    # координаты в осях детали, масштаб, поворот, обратно
    dx, dy = X - cx, Y - cy
    ca, sa_ = np.cos(phi), np.sin(phi)
    u = dx * ca + dy * sa_
    v = -dx * sa_ + dy * ca
    u, v = u * sa, v * sc
    rx, ry = u * ca - v * sa_, u * sa_ + v * ca
    cr, sr = np.cos(ang), np.sin(ang)
    qx = cx + tx + rx * cr - ry * sr
    qy = cy + ty + rx * sr + ry * cr
    pre, al = ans.sample(qx, qy)
    al = al.mean(1)
    col = pre.mean(1) / np.maximum(al, 1e-4)[:, None]
    return col, al


def part_axis(ys, xs):
    """Ось детали (PCA): угол, длина вдоль и поперёк (пиксели базы)."""
    p = np.stack([xs + 0.5, ys + 0.5], 1)
    c = p.mean(0)
    if len(p) < 3:
        return c, 0.0, 1.0, 1.0
    w, v = np.linalg.eigh(np.cov((p - c).T))
    ax = v[:, 1]
    phi = float(np.arctan2(ax[1], ax[0]))
    q = p - c
    u = q @ ax
    vv = q @ np.array([-ax[1], ax[0]])
    return c, phi, float(u.max() - u.min() + 1), float(vv.max() - vv.min() + 1)


def register(ans, lab_o, i, m_o, lab_rgb):
    """Лучшее жёсткое преобразование ответа для детали i. Возвращает словарь мерок."""
    ys, xs = np.nonzero(lab_o == i)
    c, phi, Lu, Lv = part_axis(ys, xs)
    ring = wf.dilate(lab_o == i, 2) & ~m_o
    rys, rxs = np.nonzero(ring)
    px = np.concatenate([xs, rxs]).astype(np.float32)
    py = np.concatenate([ys, rys]).astype(np.float32)
    want_a = np.concatenate([np.ones(len(xs)), np.zeros(len(rxs))]).astype(np.float32)
    want_lab = lab_rgb[ys, xs]
    n_in = len(xs)

    def score(p):
        tx, ty, ang, sa, sc = p
        col, al = cell_avg(ans, px, py, (c[0], c[1], ang, sa, sc, tx, ty, phi))
        e_m = np.mean((al - want_a) ** 2)
        lab = to_lab(col[:n_in])
        dl = lab - want_lab
        de = np.sqrt((0.6 * dl[:, 0]) ** 2 + dl[:, 1] ** 2 + dl[:, 2] ** 2)
        e_c = np.mean(al[:n_in] * np.minimum(de / 40.0, 1.0) ** 2)
        # штраф - по сдвигу концов в пикселях базы, а не по масштабу: иначе рост одного конца ответ объясняет сдвигом
        tu = tx * np.cos(phi) + ty * np.sin(phi)
        tv = -tx * np.sin(phi) + ty * np.cos(phi)
        ends2 = ((tu + (sa - 1) * Lu / 2) ** 2 + (tu - (sa - 1) * Lu / 2) ** 2
                 + (tv + (sc - 1) * Lv / 2) ** 2 + (tv - (sc - 1) * Lv / 2) ** 2)
        reg = 0.00025 * ends2 + 0.02 * ang * ang
        # цвет - слабо: он нужен, чтобы различить стык двух деталей одного силуэта, а конец детали задаёт покрытие.
        # При 0.5 тёмный затыльник ответа на месте дерева оригинала тянул конец приклада W-015 внутрь на 2.9
        # при настоящих 1.3 (покрытие по строкам, контроль 05.10)
        return e_m + COLOR_W * e_c + reg, al, de

    best = None
    for tx in np.arange(-5, 5.01, 0.5):
        for ty in np.arange(-5, 5.01, 0.5):
            s = score((tx, ty, 0.0, 1.0, 1.0))[0]
            if best is None or s < best[0]:
                best = (s, np.array([tx, ty, 0.0, 1.0, 1.0]))
    p = best[1].copy()
    # направления спуска: сдвиг x, y, поворот и ход ОДНОГО конца детали при неподвижном другом (на 1 пиксель базы)
    q0 = np.stack([xs + 0.5 - c[0], ys + 0.5 - c[1]], 1)
    eu, ev = np.array([np.cos(phi), np.sin(phi)]), np.array([-np.sin(phi), np.cos(phi)])
    dirs = [np.array([1.0, 0, 0, 0, 0]), np.array([0, 1.0, 0, 0, 0]), np.array([0, 0, np.radians(6) / 0.5, 0, 0])]
    for e_vec, k_s in ((eu, 3), (ev, 4)):
        pr = q0 @ e_vec
        a0, a1 = float(pr.min() - 0.5), float(pr.max() + 0.5)
        for e0, e1 in ((a0, a1), (a1, a0)):
            d = np.zeros(5)
            d[k_s] = 1.0 / (e0 - e1)
            d[0], d[1] = -d[k_s] * e1 * e_vec[0], -d[k_s] * e1 * e_vec[1]
            dirs.append(d)
    lo = np.array([-8, -8, np.radians(-30), 0.5, 0.5])
    hi = np.array([8, 8, np.radians(30), 1.8, 1.8])
    cur = score(p)[0]
    step = 1.0
    for _ in range(6):                      # спуск по направлениям с убывающим шагом
        improved = True
        while improved:
            improved = False
            for d in dirs:
                for sgn in (1, -1):
                    q = np.clip(p + sgn * step * d, lo, hi)
                    s = score(q)[0]
                    if s < cur - 1e-7:
                        p, cur, improved = q, s, True
        step /= 2.0
    s0, al0, _ = score(np.array([0, 0, 0, 1.0, 1.0]))
    s1, al1, de1 = score(p)
    tx, ty, ang, sa, sc = [float(v) for v in p]

    def iou(al):
        inn, out = al[:n_in], al[n_in:]
        inter = inn.sum()
        return float(inter / (n_in + out.sum() + (n_in - inter) * 0 + 1e-6))
    # форма с допуском на контур (контроль ложных тревог 05.10): HD-рисунок проводит гладкий контур вместо лесенки и
    # скругляет углы, поэтому пиксель КРАЯ детали покрыт частично (0.5 и меньше), а соседний снаружи - частично
    # задет. Строгая форма у мелких деталей (петля, скоба, мушка) падала до 0.45-0.72 на оригинале со сглаженным
    # контуром. Здесь краевой пиксель детали покрыт наполовину - считается покрытым, соседний снаружи задет до
    # половины - считается пустым; внутренние и дальние - как есть. Сдвиг и размер меряют концы, не форма
    part = lab_o == i
    nb_out = np.zeros_like(part)
    nb_in = np.zeros_like(part)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nb_out |= np.roll(~part, (dy, dx), (0, 1))
        nb_in |= np.roll(part, (dy, dx), (0, 1))
    e_in = nb_out[ys, xs]
    e_out = nb_in[rys, rxs]

    def iou_tol(al):
        inn = np.where(e_in, np.clip(al[:n_in] / 0.5, 0, 1), al[:n_in])
        out = np.where(e_out, np.clip((al[n_in:] - 0.5) / 0.5, 0, 1), al[n_in:])
        return float(inn.sum() / (n_in + out.sum() + 1e-6))
    # чувствительность: насколько ухудшается совпадение при сдвиге на 1 пикс вдоль и поперёк оси
    flat = {}
    for nm, (ex, ey) in (("вдоль", (np.cos(phi), np.sin(phi))), ("поперёк", (-np.sin(phi), np.cos(phi)))):
        d = min(score(p + np.array([sgn * ex, sgn * ey, 0, 0, 0]))[0] for sgn in (1, -1)) - s1
        flat[nm] = float(d)
    # смещения на конце детали, пиксели базы
    t_along = tx * np.cos(phi) + ty * np.sin(phi)
    t_across = -tx * np.sin(phi) + ty * np.cos(phi)
    # концы детали: вдоль оси (u) и поперёк (v). Сдвиг конца = сдвиг детали + рост масштаба на плече конца. Сдвиг и
    # длину по отдельности у детали, один конец которой уходит в соседнюю деталь, не различить (контроль 05.10:
    # ствол, продлённый на 2 вверх, читался как «сдвиг -1.8, длина +0.4»), а положение свободного конца - различается.
    # Мерится конец, если его сдвиг на пиксель при неподвижном противоположном конце ухудшает совпадение.
    q = np.stack([xs + 0.5 - c[0], ys + 0.5 - c[1]], 1)
    ex, ey = np.array([np.cos(phi), np.sin(phi)]), np.array([-np.sin(phi), np.cos(phi)])
    uu, vv = q @ ex, q @ ey
    ext = {"u": (float(uu.min() - 0.5), float(uu.max() + 0.5)), "v": (float(vv.min() - 0.5), float(vv.max() + 0.5))}
    ends = []
    for ax_name, (a0, a1), sc_i, t_ax, e_vec in (("u", ext["u"], 3, t_along, ex), ("v", ext["v"], 4, t_across, ey)):
        scl = p[sc_i]
        for e0, e1 in ((a0, a1), (a1, a0)):
            disp = t_ax + (scl - 1.0) * e0
            dd = []
            for sgn in (1, -1):
                d_s = sgn / (e0 - e1)
                d_t = -d_s * e1
                qv = p.copy()
                qv[sc_i] += d_s
                qv[0] += d_t * e_vec[0]
                qv[1] += d_t * e_vec[1]
                dd.append(score(qv)[0] - s1)
            # направление конца на экране
            dirv = e_vec * np.sign(e0)
            # свободный конец: у пикселей детали у этого конца снаружи пусто. Конец-стык с соседней деталью по
            # ответу не отличить от продолжения соседа того же цвета (контроль: ствол М16, продлённый вверх,
            # давал «нижний конец -2.8» при неподвижном стыке) - он не валит деталь, только REVIEW
            pr = (q @ e_vec) * np.sign(e0)
            band = pr >= abs(e0) - 1.5
            nx = np.floor(xs[band] + 0.5 + dirv[0]).astype(int)
            ny = np.floor(ys[band] + 0.5 + dirv[1]).astype(int)
            H, W = m_o.shape
            inside = (nx >= 0) & (nx < W) & (ny >= 0) & (ny < H)
            empty = ~inside.copy()
            empty[inside] = ~m_o[ny[inside], nx[inside]]
            free = bool(empty.mean() >= 0.5) if len(empty) else True
            name = (("справа" if dirv[0] > 0 else "слева") if abs(dirv[0]) >= abs(dirv[1])
                    else ("снизу" if dirv[1] > 0 else "сверху"))
            # сдвиг конца наружу (+) или внутрь детали (-)
            ends.append({"axis": ax_name, "side": name, "out": round(float(disp * np.sign(e0)), 2),
                         "flat": round(float(min(dd)), 5), "free": free})
    return {"ends": ends,"center": [round(float(c[0]), 2), round(float(c[1]), 2)], "axis_deg": round(float(np.degrees(phi)), 1),
            "len_along": round(Lu, 1), "len_across": round(Lv, 1), "n_px": n_in,
            "shift": [round(tx, 2), round(ty, 2)], "shift_along": round(float(t_along), 2),
            "shift_across": round(float(t_across), 2), "turn_deg": round(float(np.degrees(ang)), 1),
            "scale_along": round(sa, 3), "scale_across": round(sc, 3),
            "size_px_along": round((sa - 1) * Lu, 2), "size_px_across": round((sc - 1) * Lv, 2),
            "turn_px": round(abs(ang) * Lu / 2.0, 2),
            "cover_asis": round(float(np.clip(al0[:n_in], 0, 1).mean()), 3), "iou_asis": round(iou(al0), 3),
            "iou_fit": round(iou(al1), 3), "iou_tol": round(iou_tol(al1), 3), "color_de": round(float(np.mean(de1[al1[:n_in] > 0.5]))
                                                          if (al1[:n_in] > 0.5).any() else 99.0, 1),
            "flat": {k: round(v, 5) for k, v in flat.items()}}


def owner_grid(lab_o):
    """Принадлежность выборок SUB x SUB на пиксель базы: метка детали, пустые выборки - ближайшей детали в пределах
    2 пикселей базы (кольцами), дальше -1. Ответ рисует деталь шире или уже оригинала - его альфа у края детали
    принадлежит ей, а не соседу."""
    own = np.repeat(np.repeat(lab_o, SUB, 0), SUB, 1).copy()
    own[own == -2] = -3                       # непрозрачное без разметки - ничьё, расти в него нельзя
    H, W = own.shape
    for _ in range(2 * SUB):
        cur = own.copy()
        hole = cur == -1
        if not hole.any():
            break
        for dy, dx in N4:
            src = np.full_like(cur, -1)
            src[max(dy, 0):H + min(dy, 0), max(dx, 0):W + min(dx, 0)] = \
                cur[max(-dy, 0):H + min(-dy, 0), max(-dx, 0):W + min(-dx, 0)]
            take = hole & (src >= 0) & (own == -1)
            own[take] = src[take]
    return own


def side_name(dx, dy):
    return (("справа" if dx > 0 else "слева") if abs(dx) >= abs(dy) else ("снизу" if dy > 0 else "сверху"))


def smooth3(w):
    k = np.ones(3)
    return np.convolve(w, k, "same") / np.convolve(np.ones_like(w), k, "same")


def profile(ans, lab_o, own, i):
    """Профиль длинной детали: ширина поперёк оси по срезам в 1 пиксель базы вдоль оси, у оригинала - по пикселям
    детали, у ответа - по альфе в своей полосе (выборки, принадлежащие детали, owner_grid). Ответ сдвигается вдоль
    оси на лучшее из -1..+1 (положение мерят концы), форма вдоль длины - нет. None - деталь не длинная."""
    ys, xs = np.nonzero(lab_o == i)
    if len(xs) < 3:
        return None
    c, phi, Lu, Lv = part_axis(ys, xs)
    if Lu < PROF_LEN or Lu / max(Lv, 1e-6) < PROF_RATIO:
        return None
    eu = np.array([np.cos(phi), np.sin(phi)])
    ev = np.array([-np.sin(phi), np.cos(phi)])
    q = np.stack([xs + 0.5 - c[0], ys + 0.5 - c[1]], 1)
    uu, vv = q @ eu, q @ ev
    u0, u1 = float(uu.min() - 0.5), float(uu.max() + 0.5)
    v0, v1 = float(vv.min() - 2.5), float(vv.max() + 2.5)
    n = max(1, int(round(u1 - u0)))
    su = u0 + (np.arange(n * SUB) + 0.5) / SUB * ((u1 - u0) / n)
    sv = v0 + (np.arange(int(np.ceil((v1 - v0) * SUB))) + 0.5) / SUB
    U, V = np.meshgrid(su, sv, indexing="ij")
    X, Y = c[0] + U * eu[0] + V * ev[0], c[1] + U * eu[1] + V * ev[1]
    H, W = lab_o.shape
    xi, yi = np.floor(X).astype(int), np.floor(Y).astype(int)
    inn = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
    o_lab = np.where(inn, lab_o[np.clip(yi, 0, H - 1), np.clip(xi, 0, W - 1)], -1)
    gx, gy = np.floor(X * SUB).astype(int), np.floor(Y * SUB).astype(int)
    gin = (gx >= 0) & (gx < W * SUB) & (gy >= 0) & (gy < H * SUB)
    mine = gin & (own[np.clip(gy, 0, H * SUB - 1), np.clip(gx, 0, W * SUB - 1)] == i)

    def slices(w):
        return w.reshape(n, SUB).mean(1)
    w_o = smooth3(slices((o_lab == i).sum(1) / SUB))
    inner = slice(1, n - 1) if n > 2 else slice(0, n)
    best = None
    for du in np.arange(-1.0, 1.001, 0.25):
        _, al = ans.sample((X + du * eu[0]).ravel(), (Y + du * eu[1]).ravel())
        w_a = smooth3(slices((al.reshape(X.shape) * mine).sum(1) / SUB))
        e = float(np.abs(w_a - w_o)[inner].mean())
        if best is None or e < best[0] - 1e-9:
            best = (e, float(du), w_a)
    _, du, w_a = best
    d = (w_a - w_o)[inner]
    ad = np.abs(d)
    f_rev, f_fail = float((ad >= PROF_REV).mean()), float((ad >= PROF_FAIL).mean())
    spikes = int((ad >= PROF_SPIKE).sum())

    def run_len(b):
        best_, cur = 0, 0
        for x in b:
            cur = cur + 1 if x else 0
            best_ = max(best_, cur)
        return best_
    run_fail, run_rev = run_len(ad >= PROF_FAIL), run_len(ad >= PROF_REV)
    v = ("FAIL" if f_fail >= PROF_FRAC or spikes >= PROF_SPIKE_N or run_fail >= PROF_RUN else
         ("REVIEW" if f_rev >= PROF_FRAC or run_rev >= PROF_RUN else "PASS"))
    k = int(np.argmax(ad))
    off = (inner.start or 0)
    start = side_name(-eu[0], -eu[1])            # с какого конца считаются срезы
    bad = np.nonzero(ad >= PROF_REV)[0] + off + 1
    why = ""
    if v != "PASS":
        why = "профиль: %s на %.1f (срез %d из %d от конца %s); ±%.1f и больше на %d из %d срезов%s" % (
            "уже" if d[k] < 0 else "шире", ad[k], k + off + 1, n, start, PROF_REV, len(bad), len(d),
            (" (%d-%d)" % (bad.min(), bad.max())) if len(bad) else "")
        if max(run_fail, run_rev) >= PROF_RUN:
            why += "; подряд %d срезов от %.2f, %d от %.1f" % (run_fail, PROF_FAIL, run_rev, PROF_REV)
    return {"verdict": v, "why": why, "n": n, "from": start, "du": round(du, 2), "w_orig": [round(float(x), 2) for x in w_o],
            "w_ans": [round(float(x), 2) for x in w_a], "max_dev": round(float(d[k]), 2), "frac_rev": round(f_rev, 2),
            "frac_fail": round(f_fail, 2), "spikes": spikes, "run_fail": run_fail, "run_review": run_rev}


def grade(v, ok, rev):
    v = abs(v)
    return "PASS" if v <= ok else ("REVIEW" if v <= rev else "FAIL")


def judge(p, r):
    """Вердикт детали и причины."""
    why, worst = [], "PASS"

    def add(g, txt):
        nonlocal worst
        if VERD[g] > VERD[worst]:
            worst = g
        if g != "PASS":
            why.append("%s %s" % (g, txt))
    # положение и размер - по концам детали: «конец сверху +2» - деталь в ответе на 2 пикселя базы дальше наружу
    notes = []
    for e in r["ends"]:
        if e["flat"] < FLAT:
            notes.append("конец %s не мерится" % e["side"])
            continue
        if not e["free"]:
            continue                       # стык с соседней деталью мерит joints() по цвету
        add(grade(e["out"], POS_OK, POS_REVIEW), "конец %s %+.1f" % (e["side"], e["out"]))
    if r["len_along"] >= 4:
        add(grade(r["turn_px"], TURN_OK, TURN_REVIEW), "поворот %+.0f° (%.1f на конце)" % (r["turn_deg"], r["turn_px"]))
    sh = r["iou_tol"]                       # форма с допуском на гладкий контур (register.iou_tol)
    # у тонкой детали (до 3 пикселей поперёк) пиксель сдвига - треть площади: форма валит её только ниже 0.45
    ok_, rev_ = (SHAPE_OK, SHAPE_REVIEW) if r["len_across"] > 3 else (SHAPE_REVIEW, SHAPE_THIN_REVIEW)
    add("PASS" if sh >= ok_ else ("REVIEW" if sh >= rev_ else "FAIL"), "форма %.2f" % sh)
    # цвет - вспомогательная мерка (указание специалиста 05.10): другой материал детали - вопрос к независимой
    # проверке, а не дефект; в вердикт детали не идёт
    if r["color_de"] > COLOR_REVIEW:
        notes.append("цвет %.0f (вспомогательно)" % r["color_de"])
    pf = r.get("profile")
    if pf and pf["verdict"] != "PASS":
        add(pf["verdict"], pf["why"])
    return worst, why, notes


def extra_bits(ans, m_o):
    """Лишнее: пиксели базы с покрытием ответа >= 0.5 дальше пикселя от оригинала, куски от EXTRA_MIN."""
    H, W = m_o.shape
    yy, xx = np.mgrid[0:H, 0:W]
    _, al = cell_avg(ans, xx.ravel().astype(np.float32), yy.ravel().astype(np.float32),
                     (0, 0, 0, 1, 1, 0, 0, 0))
    cov = al.reshape(H, W) >= 0.5
    far = cov & ~wf.dilate(m_o, 1)
    n = 0
    if far.any():
        lab, areas = wf.labels(far)
        n = len(areas) - 1
    bits = []
    for k in range(1, n + 1):
        z = lab == k
        if z.sum() >= EXTRA_MIN:
            ys, xs = np.nonzero(z)
            bits.append({"px": int(z.sum()), "box": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]})
    return bits, cov


JOINT_SEP = 8.0                          # цвета двух деталей различимы: расстояние медиан у стыка, ΔE
JOINT_RANGE = 6.0                        # поиск стыка, пиксели базы в обе стороны
JOINT_SHARP = 4.0                        # стык, сдвинутый на 1.5 пикселя, хуже на выборку полосы хотя бы на столько, ΔE
# деталь-линия (тетива, проволока): площадь на длину не толще 1.3 пикселя базы. Стык с ней по цвету не мерится -
# у линии нет «своей стороны»: ответ рисует её тоньше, и разделение на два цвета находит тень соседней детали
# (лук W-001, 05.10: тетива|плечо +3.2 при верном рисунке). Положение линии видят её концы и форма
LINE_W, LINE_LEN = 1.3, 6.0


def de_min(lab_s, pal):
    """Расстояние каждого цвета lab_s (N,3) до ближайшего цвета палитры pal (M,3), яркость с весом 0.6."""
    d = lab_s[:, None, :] - pal[None, :, :]
    d[..., 0] *= 0.6
    return np.sqrt((d ** 2).sum(-1)).min(1)


def joints(ans, lab_o, m_o, lab_rgb, spec):
    """Стыки соседних деталей: положение границы двух деталей в ответе по цвету. Покрытие стык не видит (силуэт
    сплошной), поэтому граница ищется сдвигом прямой стыка вдоль нормали: выборки ответа по одну сторону должны
    быть цвета одной детали, по другую - другой (ближайший цвет детали оригинала). Сдвиг считается против того же
    поиска на самом оригинале (прямая - приближение границы). Мерится, если цвета деталей различимы."""
    H, W = m_o.shape
    out = []
    n = len(spec["parts"])
    o = (np.arange(SUB) + 0.5) / SUB
    ox, oy = [g.ravel() for g in np.meshgrid(o, o)]
    thick = []                      # толщина детали-линии; короткий выступ (мушка) линией не считается
    for i in range(n):
        ys, xs = np.nonzero(lab_o == i)
        lu = part_axis(ys, xs)[2] if len(ys) else 0.0
        thick.append(len(ys) / lu if lu >= LINE_LEN else 99.0)
    for i in range(n):
        for j in range(i + 1, n):
            zi, zj = lab_o == i, lab_o == j
            bi = zi & (wf.dilate(zj, 1))
            bj = zj & (wf.dilate(zi, 1))
            if bi.sum() < 1 or bj.sum() < 1:
                continue
            ct = contact(lab_o, i, j)
            if ct is None:
                continue
            nv, b0, geo_bad = ct["normal"], ct["point"], ct["bad"]
            # цвет детали - медиана её пикселей у стыка (до 4 пикселей от него): ближайший цвет всей палитры не
            # годится - контур и серые тона у соседних деталей общие, различимость выходила 0 у клинка и рукояти
            near = wf.dilate(bi | bj, 4)
            pal_i = np.median(lab_rgb[zi & near], 0)[None, :]
            pal_j = np.median(lab_rgb[zj & near], 0)[None, :]
            sep = float(de_min(pal_i, pal_j)[0])
            # область поиска шире хода стыка: иначе у края области стоимость плоская и стык «не мерится»
            reg = (zi | zj) & wf.dilate(bi | bj, int(JOINT_RANGE) + 2)
            ry, rx = np.nonzero(reg)
            X = (rx[:, None] + ox[None, :]).ravel()
            Y = (ry[:, None] + oy[None, :]).ravel()
            s = (X - b0[0]) * nv[0] + (Y - b0[1]) * nv[1]

            def best(col, al):
                """Положение стыка и его резкость: на сколько ΔE в среднем хуже выборки полосы ±1.5 пикселя, если
                стык сдвинуть на 1.5 пикселя (стоимость на выборку полосы, а не всей области - иначе широкая
                область разбавляет резкость до нуля)."""
                # граница - там, где меняется СВОЙ цвет картинки (два класса по обе стороны прямой, наименьший разброс
                # внутри классов), а не там, где цвет ближе к цветам оригинала: исполнение меняет тона (светлый
                # клинок ответа против тёмного у оригинала), и сличение с палитрой оригинала стык теряло
                ok = al > 0.5
                c = col[ok] * np.array([0.6, 1.0, 1.0])
                ss = s[ok]
                o = np.argsort(ss)
                ss, c = ss[o], c[o]
                cs, cs2 = np.cumsum(c, 0), np.cumsum((c ** 2).sum(1))
                N = len(ss)
                ds = np.arange(-JOINT_RANGE, JOINT_RANGE + 0.01, 0.25)
                cost, gap = [], []
                for d in ds:
                    m = int(np.searchsorted(ss, d))
                    if m < 3 or N - m < 3:
                        cost.append(np.inf)
                        gap.append(0.0)
                        continue
                    ma, mb = cs[m - 1] / m, (cs[-1] - cs[m - 1]) / (N - m)
                    va = cs2[m - 1] - m * (ma ** 2).sum()
                    vb = (cs2[-1] - cs2[m - 1]) - (N - m) * (mb ** 2).sum()
                    cost.append(va + vb)
                    gap.append(float(np.sqrt(((ma - mb) ** 2).sum())))
                cost = np.array(cost)
                k = int(np.argmin(cost))
                nb = max(1, int((np.abs(ss - ds[k]) < 1.5).sum()))
                side = [cost[np.argmin(np.abs(ds - (ds[k] + sg * 1.5)))] for sg in (1, -1)]
                sh = float(np.sqrt(max(0.0, min(side) - cost[k]) / nb * 2.0)) if np.isfinite(min(side)) else 0.0
                # средние цвета сторон (Lab, без веса) - для сверки состава сторон с оригиналом
                m = int(np.searchsorted(ss, ds[k]))
                w_ = np.array([1 / 0.6, 1.0, 1.0])
                ma = c[:m].mean(0) * w_ if m > 0 else None
                mb = c[m:].mean(0) * w_ if N - m > 0 else None
                return float(ds[k]), sh, gap[k], ma, mb
            # оригинал (nearest x4) - та же процедура, точка отсчёта
            oxi = np.clip(np.floor(X).astype(int), 0, W - 1)
            oyi = np.clip(np.floor(Y).astype(int), 0, H - 1)
            col_o = lab_rgb[oyi, oxi]
            al_o = m_o[oyi, oxi].astype(np.float32)
            d0, sharp0, gap0, ma0, mb0 = best(col_o, al_o)
            pre, al = ans.sample(X, Y)
            col = to_lab(pre / np.maximum(al, 1e-4)[:, None])
            d1, sharp, gap, ma, mb = best(col, al)
            sep = min(sep, gap)
            line = min(thick[i], thick[j]) <= LINE_W
            d = d1 - d0
            nm_i, nm_j = spec["parts"][i]["name"], spec["parts"][j]["name"]
            # почему не мерится - по порядку: устройство стыка, различимость цветов, резкость
            why_nm = ""
            if line:
                why_nm = "деталь-линия"
            elif geo_bad:
                why_nm = geo_bad
            elif sep < JOINT_SEP:
                why_nm = "цвета деталей близки (ΔE %.0f)" % sep
            elif sharp < JOINT_SHARP or sharp0 < JOINT_SHARP:
                why_nm = "граница по цвету размыта (%.2f/%.2f)" % (sharp0, sharp)
            # неоднозначно: найденная в ответе граница - не между теми же материалами, что в оригинале. Стороны
            # ответа переставлены относительно сторон оригинала, или контраст сторон другой в 2 раза
            amb = ""
            if not why_nm and all(x is not None for x in (ma, mb, ma0, mb0)):
                swap_a = de_w(ma, ma0) > de_w(ma, mb0)
                swap_b = de_w(mb, mb0) > de_w(mb, ma0)
                ratio = gap / max(gap0, 1e-3)
                if swap_a or swap_b:
                    amb = "стороны границы ответа ближе к чужим сторонам оригинала"
                elif ratio > JOINT_CONTRAST or ratio < 1.0 / JOINT_CONTRAST:
                    amb = "контраст сторон %.0f против %.0f у оригинала" % (gap, gap0)
            status = "NOT_MEASURED" if why_nm else ("AMBIGUOUS" if amb else "MEASURED")
            if status == "MEASURED":
                v = grade(d, POS_OK, POS_REVIEW)
                why = "%s стык %s|%s %+.1f (%s)" % (v, nm_i, nm_j, d, ("к " + nm_j) if d > 0 else ("к " + nm_i))
            elif status == "AMBIGUOUS":
                v = "REVIEW"
                why = "REVIEW стык %s|%s неоднозначен: %s (найдено %+.1f, сдвигом не считается)" % (nm_i, nm_j, amb, d)
            else:
                v = NOT_MEASURED
                why = "стык %s|%s не измерен: %s" % (nm_i, nm_j, why_nm)
            out.append({"a": nm_i, "b": nm_j, "shift": round(d, 2), "toward": nm_j if d > 0 else nm_i,
                        "sep": round(sep, 1), "sharp": round(sharp, 2), "sharp_orig": round(sharp0, 2),
                        "gap": round(gap, 1), "gap_orig": round(gap0, 1), "status": status,
                        "at_orig": round(d0, 2), "point": [round(float(v), 2) for v in b0],
                        "normal": [round(float(v), 4) for v in nv],
                        "measured": status == "MEASURED", "line": bool(line), "normal_deg": ct["normal_deg"],
                        "resid": ct["resid"], "angle": ct["angle"], "contact_len": ct["length"],
                        "verdict": v, "why": why})
    return out


def contact(lab_o, i, j):
    """Контакт деталей i и j: рёбра между их пикселями (4-соседство). Прямая по серединам рёбер даёт нормаль стыка
    (от i к j) и точку отсчёта. Стык не прямой (угол, охват - ствол кончается внутри колодки), если невязка прямой
    больше JOINT_RESID, нормаль прямой уходит от средней нормали рёбер дальше JOINT_ANGLE или контакт короче
    JOINT_MINLEN - тогда bad - причина, и стык не мерится."""
    H, W = lab_o.shape
    pts, nrm = [], []
    a, b = lab_o[:, :-1], lab_o[:, 1:]
    for s, (p, q) in ((1.0, (a == i, b == j)), (-1.0, (a == j, b == i))):
        ys, xs = np.nonzero(p & q)
        pts += [(x + 1.0, y + 0.5) for y, x in zip(ys, xs)]
        nrm += [(s, 0.0)] * len(ys)
    a, b = lab_o[:-1, :], lab_o[1:, :]
    for s, (p, q) in ((1.0, (a == i, b == j)), (-1.0, (a == j, b == i))):
        ys, xs = np.nonzero(p & q)
        pts += [(x + 0.5, y + 1.0) for y, x in zip(ys, xs)]
        nrm += [(0.0, s)] * len(ys)
    if not pts:
        return None                             # касаются только углом
    P, Nm = np.array(pts), np.array(nrm)
    mean_n = Nm.mean(0)
    if np.hypot(*mean_n) < 1e-6:
        mean_n = np.array([1.0, 0.0])
    mean_n = mean_n / np.hypot(*mean_n)
    c = P.mean(0)
    if len(P) >= 2:
        w, v = np.linalg.eigh(np.cov((P - c).T) + 1e-9 * np.eye(2))
        t = v[:, 1]
        nv = np.array([-t[1], t[0]])
        resid = float(np.sqrt(max(w[0], 0.0)))
        length = float(np.ptp((P - c) @ t)) + 1.0
    else:
        nv, resid, length = mean_n.copy(), 0.0, 1.0
    if nv @ mean_n < 0:
        nv = -nv
    ang = float(np.degrees(np.arccos(np.clip(nv @ mean_n, -1, 1))))
    bad = ""
    if length < JOINT_MINLEN:
        bad = "контакт короче %.1f пикселя" % JOINT_MINLEN
    elif resid > JOINT_RESID:
        bad = "стык не прямой (невязка %.2f)" % resid
    elif ang > JOINT_ANGLE:
        bad = "стык не прямой (угол %.0f°)" % ang
    return {"normal": nv, "point": c, "bad": bad, "resid": round(resid, 2), "angle": round(ang, 1),
            "length": round(length, 1), "normal_deg": round(float(np.degrees(np.arctan2(nv[1], nv[0]))), 1)}


def check_one(ms, t, rgba, spec, rgb_o, m_o, off=0, labels=None):
    """labels - (метки, переназначенные, смесь) из part_labels; по умолчанию считаются тут."""
    ans = Answer(rgba, off)
    lab_rgb = to_lab(rgb_o)
    lab_o, moved, mixed = labels or part_labels(spec, m_o, lab_rgb)
    own = owner_grid(lab_o)
    res = []
    for i, p in enumerate(spec["parts"]):
        if not (lab_o == i).any():
            res.append({"part": p["name"], "kind": p["kind"], "verdict": "REVIEW", "why": ["REVIEW пустая разметка"]})
            continue
        r = register(ans, lab_o, i, m_o, lab_rgb)
        r["profile"] = profile(ans, lab_o, own, i)
        v, why, notes = judge(p, r)
        if p["name"] in mixed:
            notes.append("смесь: %d пикс цвета %s" % (mixed[p["name"]][1], mixed[p["name"]][0]))
        r.update({"part": p["name"], "kind": p["kind"], "verdict": v, "why": why, "notes": notes})
        res.append(r)
    bits, cov = extra_bits(ans, m_o)
    unl = int((lab_o == -2).sum())
    return res, bits, unl, joints(ans, lab_o, m_o, lab_rgb, spec)


def size_native(a_ref, m_o):
    """Размер по родной альфе ответа (файл модели в своём разрешении, альфа >= 0.5) против габарита оригинала в
    пикселях базы: ширина при равной высоте, высота при равной ширине, равномерная постановка (как нарезка)."""
    ys, xs = np.nonzero(a_ref >= 0.5)
    bw, bh = float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1)
    b = wf.bbox(m_o)
    tw, th = float(b[2] - b[0]), float(b[3] - b[1])
    s = np.sqrt(tw / bw * th / bh)
    dw_u, dh_u = 100 * (bw * s / tw - 1), 100 * (bh * s / th - 1)
    worst = max(abs(dw_u), abs(dh_u))
    v = "PASS" if worst <= SIZE_TOL else ("REVIEW" if worst <= SIZE_FAIL else "FAIL")
    rep = {"ref_alpha_px": [int(bw), int(bh)], "orig_px": [int(tw), int(th)],
           "w_at_equal_h_pct": round(100 * (bw * th / bh / tw - 1), 2),
           "h_at_equal_w_pct": round(100 * (bh * tw / bw / th - 1), 2),
           "uniform_dw_pct": round(dw_u, 2), "uniform_dh_pct": round(dh_u, 2),
           "uniform_dw_base_px": round(bw * s - tw, 2), "uniform_dh_base_px": round(bh * s - th, 2), "verdict": v}
    rep["why"] = "" if v == "PASS" else (
        "%s размер по родной альфе %+.1f/%+.1f%% (%+.2f/%+.2f пикс базы; ширина при равной высоте %+.1f%%, "
        "высота при равной ширине %+.1f%%), допуск ±%.0f%%" % (
            v, dw_u, dh_u, rep["uniform_dw_base_px"], rep["uniform_dh_base_px"], rep["w_at_equal_h_pct"],
            rep["h_at_equal_w_pct"], SIZE_TOL))
    return rep, s


def k4_rounding(meta, a_ref, m_o, png_a):
    """Округление на сетке k=4 - отдельно от размера: точный габарит равномерной постановки в HD-пикселях против
    того, что поставила нарезка (целые пиксели), и габарит альфы PNG пака (после среза клетками)."""
    ys, xs = np.nonzero(a_ref >= 0.5)
    bw, bh = float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1)
    b = wf.bbox(m_o)
    tw, th = float(b[2] - b[0]) * K, float(b[3] - b[1]) * K
    s = np.sqrt(tw / bw * th / bh)
    pl = meta.get("report", {}).get("place", {})
    rep = {"exact_hd": [round(bw * s, 2), round(bh * s, 2)], "orig_hd": [int(tw), int(th)],
           "placed_hd": pl.get("placed_px"), "placed_dw_pct": pl.get("placed_dw_pct"),
           "placed_dh_pct": pl.get("placed_dh_pct")}
    if pl.get("placed_px"):
        # placed_px - габарит файла после масштаба; у ответа без полей он и есть габарит альфы
        rep["round_hd"] = [round(pl["placed_px"][0] - bw * s, 2), round(pl["placed_px"][1] - bh * s, 2)]
    if (png_a >= 0.5).any():
        py_, px_ = np.nonzero(png_a >= 0.5)
        rep["png_alpha_hd"] = [int(px_.max() - px_.min() + 1), int(py_.max() - py_.min() + 1)]
    return rep


def cut_check(meta, a_raw=None, off=0, m_o=None):
    """Срез размещением - самостоятельный дефект, даже когда итоговый габарит проходит: альфа ответа за холстом
    кадра и за клетками предмета (weapon_from_ref: lost_off_canvas_alpha, cut_by_cells_alpha), HD-пиксели.
    С сырым ответом (a_raw - альфа на холсте с полем off пикселей базы, та же постановка, что в нарезке) срез
    делится по габариту оригинала x4 (средство зависит от габарита, а не от совпадения пикселей):
      orig - срезанное ВНУТРИ габарита оригинала: оригинал сам заходит за клетки, ответ лишь повторяет его
             протяжённость - средство метка .wide (допуск шире клеток), решает Vitali;
      wider - срезанное ЗА габаритом оригинала: ответ выступил дальше оригинала (пропорции, деталь) - средство
             перезаказ, это дефект ответа;
      wide_left - сколько осталось бы срезано с допуском .wide (iac.wide_rect).
    Вердикт - по сумме (пороги CUT_MIN, CUT_FAIL), части только называют причину."""
    pl = meta.get("report", {}).get("place", {})
    lost = float(pl.get("lost_off_canvas_alpha", 0.0) or 0.0)
    cells = float(pl.get("cut_by_cells_alpha", 0.0) or 0.0)
    tot = lost + cells
    rep = {"lost_off_canvas": lost, "cut_by_cells": cells, "total_hd": round(tot, 1), "clip": pl.get("clip", "grid")}
    if a_raw is not None and m_o is not None:
        cw, ch = meta["cells"]
        H, W = m_o.shape
        x0, y0, x1, y1 = (iac.wide_rect(cw, ch, (W, H)) if rep["clip"] == "wide" else iac.grid_rect(cw, ch))
        p = off * K
        keep = np.zeros_like(a_raw, dtype=bool)
        keep[p + y0 * K:p + y1 * K, p + x0 * K:p + x1 * K] = True
        b = wf.bbox(m_o)
        mo = np.zeros_like(keep)
        mo[p + b[1] * K:p + b[3] * K, p + b[0] * K:p + b[2] * K] = True
        out = a_raw * ~keep
        o_orig, o_wide = float(out[mo].sum()), float(out[~mo].sum())
        wx0, wy0, wx1, wy1 = iac.wide_rect(cw, ch, (W, H))
        kw = np.zeros_like(keep)
        kw[p + wy0 * K:p + wy1 * K, p + wx0 * K:p + wx1 * K] = True
        ys, xs = np.nonzero(m_o)
        inside = (xs >= x0) & (xs < x1) & (ys >= y0) & (ys < y1)
        rep.update({"rect": [x0, y0, x1, y1], "orig_px_outside_rect": int((~inside).sum()),
                    "cut_orig_hd": round(o_orig, 1), "cut_wider_hd": round(o_wide, 1),
                    "raw_total_hd": round(o_orig + o_wide, 1),
                    "wide_left_hd": round(float((a_raw * ~kw).sum()), 1)})
    v = "PASS" if tot < CUT_MIN else ("REVIEW" if tot < CUT_FAIL else "FAIL")
    why = ""
    if v != "PASS":
        why = "%s размещение срезало предмет: %.1f HD-пикс (за кадром %.1f, клетками %.1f; %.1f пикс базы)" % (
            v, tot, lost, cells, tot / (K * K))
        if "cut_orig_hd" in rep:
            why += "; из них в габарите оригинала (сам оригинал заходит за клетки: %d пикс базы) %.1f - средство " \
                   "метка .wide, решает Vitali, с ней осталось бы %.1f; за габаритом оригинала (ответ выступил " \
                   "дальше) %.1f" % (rep["orig_px_outside_rect"], rep["cut_orig_hd"], rep["wide_left_hd"],
                                     rep["cut_wider_hd"])
    rep.update({"verdict": v, "why": why})
    return rep


def placement(cu):
    """Пригодность размещения - отдельный итог, рисунок и конструкцию не валит (указание специалиста 05.10).
      PASS          - ничего не срезано, или срезано меньше пикселя базы в сумме (CUT_FAIL HD-пикс) - отмечается;
      DECISION_WIDE - срез уходит с допуском .wide: оригинал сам заходит за клетки. Метку автоматически НЕ ставим,
                      решает Vitali (.wide или меньший масштаб);
      FAIL          - срезано и с .wide (строки 0 и 47 у 1x3 метка не открывает): средство - масштаб или перерисовка.
    Срез за габаритом оригинала (ответ шире) - следствие размера и концов деталей, его считает конструкция; здесь
    он только называется."""
    tot = cu["total_hd"]
    left = cu.get("wide_left_hd", tot)
    wider = cu.get("cut_wider_hd", 0.0)
    if tot < CUT_FAIL:
        v = "PASS"
        why = "" if tot < CUT_MIN else "срезано %.1f HD-пикс - меньше пикселя базы" % tot
    elif left < CUT_FAIL:
        v = "DECISION_WIDE"
        why = "срезано %.1f HD-пикс (оригинал сам заходит за клетки: %s пикс базы); с .wide осталось бы %.1f - " \
              "решает Vitali" % (tot, cu.get("orig_px_outside_rect", "?"), left)
    else:
        v = "FAIL"
        why = "срезано %.1f HD-пикс, с .wide осталось бы %.1f - средство масштаб или перерисовка" % (tot, left)
    if wider >= CUT_FAIL:
        why += "; из них за габаритом оригинала %.1f - ответ шире оригинала (см. конструкцию)" % wider
    return {"verdict": v, "why": why, "total_hd": tot, "wide_left_hd": left, "cut_wider_hd": wider}


def moved_mask(lab_o, i, r, Z):
    """Маска детали i, перенесённая найденным преобразованием, в масштабе Z (для листа)."""
    H, W = lab_o.shape
    im = Image.new("L", (W * Z, H * Z), 0)
    d = ImageDraw.Draw(im)
    cx, cy = r["center"]
    phi = np.radians(r["axis_deg"])
    ang = np.radians(r["turn_deg"])
    sa, sc = r["scale_along"], r["scale_across"]
    tx, ty = r["shift"]
    ca, sn, cr, sr = np.cos(phi), np.sin(phi), np.cos(ang), np.sin(ang)
    for y, x in zip(*np.nonzero(lab_o == i)):
        pts = []
        for qx, qy in ((x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)):
            dx, dy = qx - cx, qy - cy
            u, v = (dx * ca + dy * sn) * sa, (-dx * sn + dy * ca) * sc
            rx, ry = u * ca - v * sn, u * sn + v * ca
            pts.append(((cx + tx + rx * cr - ry * sr) * Z, (cy + ty + rx * sr + ry * cr) * Z))
        d.polygon(pts, fill=255)
    return np.asarray(im) > 0


def edge(mk):
    e = mk.copy()
    e[1:] &= mk[:-1]
    e[:-1] &= mk[1:]
    e[:, 1:] &= mk[:, :-1]
    e[:, :-1] &= mk[:, 1:]
    return mk & ~e


def overlay(rgba, spec, m_o, res, Z=12, labels=None):
    """Ответ на тёмном (масштаб Z к базе), поверх: контур детали оригинала тонкой линией и контур детали ответа
    (найденное положение) толстой линией того же цвета; номер детали."""
    H, W = m_o.shape
    lab_o = labels if labels is not None else label_map(spec, m_o)
    im = on_dark(Image.fromarray(rgba, "RGBA")).resize((W * Z, H * Z), Image.LANCZOS)
    a = np.asarray(im).copy()
    for i, r in enumerate(res):
        if "center" not in r:
            continue
        col = np.array(COLORS[i % len(COLORS)], np.uint8)
        om = np.asarray(Image.fromarray(((lab_o == i) * 255).astype(np.uint8)).resize((W * Z, H * Z), Image.NEAREST)) > 0
        a[edge(om)] = col // 2 + 60
        mm = moved_mask(lab_o, i, r, Z)
        e = edge(mm)
        e = e | np.roll(e, 1, 0) | np.roll(e, 1, 1)
        a[e] = col
    out = Image.fromarray(a)
    d = ImageDraw.Draw(out)
    f = font(14)
    for i, r in enumerate(res):
        if "center" in r:
            x, y = r["center"]
            d.text(((x + r["shift"][0]) * Z, (y + r["shift"][1]) * Z), str(i), fill=(255, 255, 255), font=f,
                   anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
    return out


RAW_PAD = 4                              # поле холста сырого ответа, пиксели базы


def place_raw(meta, m_full):
    """Сырой ответ равномерно на габарит оригинала в кадре k=4 (как weapon_from_ref.place), без среза клетками и
    без среза краем кадра: холст шире кадра на RAW_PAD пикселей базы с каждой стороны. -> (rgba, поле, альфа файла)."""
    import weapon_from_ref as wr
    rgb, a, _bg = wr.ref_matte(meta["ref"])
    b = wf.bbox(m_full)
    box = (b[0] + RAW_PAD, b[1] + RAW_PAD, b[2] + RAW_PAD, b[3] + RAW_PAD)
    c4, a4, _rep = wr.place(rgb, a, box, K, (m_full.shape[1] + 2 * RAW_PAD) * K, (m_full.shape[0] + 2 * RAW_PAD) * K)
    return np.dstack([c4, a4 * 255.0]).clip(0, 255).astype(np.uint8), RAW_PAD, a


def perturb(lab, i, mode):
    """Разметка детали i со сдвинутой на пиксель границей с ДРУГИМИ деталями (силуэт не трогается): grow - соседние
    пиксели чужих деталей отходят ей, shrink - её пиксели у чужих деталей отходят соседу."""
    out = lab.copy()
    H, W = lab.shape
    for dy, dx in N4:
        nb = np.full_like(lab, -1)
        nb[max(dy, 0):H + min(dy, 0), max(dx, 0):W + min(dx, 0)] = \
            lab[max(-dy, 0):H + min(-dy, 0), max(-dx, 0):W + min(-dx, 0)]
        if mode == "grow":
            out[(lab >= 0) & (lab != i) & (nb == i)] = i
        else:
            take = (lab == i) & (nb >= 0) & (nb != i) & (out == i)
            out[take] = nb[take]
    return out


def label_check(ans, spec, m_o, lab_rgb, labels, res):
    """Достоверность мерки детали (указание специалиста 05.10): FAIL детали доказан, только если разметка детали не
    под вопросом (предмет REVIEW, деталь UNKNOWN, в детали цвет соседа) И вердикт FAIL держится, когда граница детали
    с соседними деталями сдвинута на пиксель наружу и внутрь и когда разметка - голые прямоугольники без уточнения
    по материалу. Иначе мерка зависит от выделения детали: это вопрос к независимой проверке, а не дефект.
    Синтетический контроль (detect) этого не доказывает: он ставит дефект по той же разметке, по которой мерит.
    -> {деталь: {robust, variants, doubt}} для деталей с FAIL."""
    lab0, _moved, mixed = labels
    rect = label_map(spec, m_o)
    out = {}
    for k, (r, p) in enumerate(zip(res, spec["parts"])):
        if r["verdict"] != "FAIL" or "center" not in r:
            continue
        doubt = []
        if spec.get("status") == "REVIEW":
            doubt.append("разметка предмета REVIEW")
        if p.get("status") == "UNKNOWN":
            doubt.append("деталь не опознана")
        if p["name"] in mixed:
            doubt.append("в детали цвет соседа %s (%d пикс)" % tuple(mixed[p["name"]]))
        var = {}
        for nm, lab in (("grow", perturb(lab0, k, "grow")), ("shrink", perturb(lab0, k, "shrink")), ("rects", rect)):
            if (lab == lab0).all():
                continue                    # границы с соседями нет / уточнение ничего не меняло - вариант тот же
            if (lab == k).sum() < 2:
                var[nm] = "NOT_MEASURED"
                continue
            rr = register(ans, lab, k, m_o, lab_rgb)
            rr["profile"] = profile(ans, lab, owner_grid(lab), k)
            var[nm] = judge(p, rr)[0]
        robust = not doubt and all(v == "FAIL" for v in var.values())
        out[p["name"]] = {"robust": robust, "variants": var, "doubt": doubt}
    return out


def overall(res, bits, unl, spec, jn=()):
    """Итог конструкции одного источника по ДОКАЗАТЕЛЬНЫМ меркам - покрытию: концы, поворот, форма и профиль
    детали. Всё остальное - вопросы к независимой проверке (weapon_accept: визуальная проверка ИИ), а не дефект
    (указание специалиста 05.10, отменяет прежнее «неизмеренное - итог не выше REVIEW»):
      JOINT_NOT_MEASURED - стык не мерится цветом; это свойство замера, а не предмета;
      JOINT_AMBIGUOUS    - найдена граница других материалов;
      JOINT_COLOR        - стык по цвету сдвинут: цветовая мерка вспомогательная (у W-055 она назвала рычаг курком);
      COLOR              - другой материал детали;
      UNKNOWN_PART       - деталь не опознана разметкой;
      EXTRA              - ответ там, где у оригинала пусто: добавлена ли деталь, решает проверка смысла.
    Вопросы разметки (пиксели без детали, разметка REVIEW) - отдельным списком label_issues: это работа над
    разметкой, а не вопрос к предмету. -> (вердикт, причины, вопросы, вопросы разметки)."""
    worst = "PASS"
    why = []
    for r in res:
        if "center" not in r:
            continue                       # пустая разметка детали - вопрос разметки ниже
        if VERD[r["verdict"]] > VERD[worst]:
            worst = r["verdict"]
        if r["verdict"] != "PASS":
            why.append("%s: %s" % (r["part"], "; ".join(r["why"])))
    qs = []
    for j in jn:
        if j["status"] == NOT_MEASURED:
            qs.append({"kind": "JOINT_NOT_MEASURED", "parts": [j["a"], j["b"]], "what": j["why"]})
        elif j["status"] == "AMBIGUOUS":
            qs.append({"kind": "JOINT_AMBIGUOUS", "parts": [j["a"], j["b"]], "what": j["why"]})
        elif j["verdict"] != "PASS":
            qs.append({"kind": "JOINT_COLOR", "parts": [j["a"], j["b"]], "what": j["why"],
                       "level": j["verdict"], "toward": j["toward"]})
    for r, p in zip(res, spec["parts"]):
        if any("(вспомогательно)" in n for n in r.get("notes", [])):
            qs.append({"kind": "COLOR", "parts": [r["part"]], "what": "цвет детали %.0f ΔE" % r["color_de"]})
        if p.get("status") == "UNKNOWN":
            qs.append({"kind": "UNKNOWN_PART", "parts": [r["part"]], "what": "деталь не опознана разметкой"})
    for b in bits:
        qs.append({"kind": "EXTRA", "parts": [], "what": "%d пикс базы там, где у оригинала пусто, у %d,%d" % (
            b["px"], b["box"][0], b["box"][1]), "box": b["box"]})
    li = []
    if unl > 2:
        li.append("%d пикс оригинала без разметки" % unl)
    if spec.get("status") == "REVIEW":
        li.append("разметка: " + spec.get("note", "REVIEW"))
    li += ["%s: пустая разметка" % r["part"] for r in res if "center" not in r]
    return worst, why, qs, li


def check(masters, cut, tag):
    L = wf.list_rows()
    rows, report = [], {}
    for ms in masters:
        t = L[ms]["type"]
        spec = load_parts(ms)
        if spec is None:
            print("%s: разметки частей нет (%s) - REVIEW" % (ms, PARTS))
            rows.append([ms, t, "both", "REVIEW", "нет разметки частей", ""])
            continue
        mp = os.path.join(cut, "meta", t + ".json")
        with open(mp, encoding=ENC) as f:
            meta = json.load(f)
        rgb_o, m_o = wf.original(t)
        labels = part_labels(spec, m_o, to_lab(rgb_o))
        out = {"labels_moved": [list(x) for x in labels[1]],
               "labels_mixed": {k: list(v) for k, v in labels[2].items()}}
        png_a = None
        for src in ("raw", "png"):
            if src == "raw":
                rgba, off, a_ref = place_raw(meta, m_o)
                raw_alpha, raw_off = rgba[..., 3].astype(np.float32) / 255.0, off
                view = rgba[off * K:rgba.shape[0] - off * K, off * K:rgba.shape[1] - off * K]
            else:
                rgba, off = np.asarray(Image.open(meta["file"]).convert("RGBA")), 0
                view = rgba
                png_a = rgba[..., 3].astype(np.float32) / 255.0
            res, bits, unl, jn = check_one(ms, t, rgba, spec, rgb_o, m_o, off, labels)
            v, why, qs, li = overall(res, bits, unl, spec, jn)
            out[src] = {"verdict": v, "why": why, "questions": qs, "label_issues": li, "parts": res, "joints": jn,
                        "extra": bits, "unlabeled": unl,
                        "joints_measured": [sum(j["status"] == "MEASURED" for j in jn), len(jn)]}
            if src == "raw":
                out[src]["label_check"] = label_check(Answer(rgba, off), spec, m_o, to_lab(rgb_o), labels, res)
            os.makedirs(os.path.join(cut, "parts"), exist_ok=True)
            overlay(view, spec, m_o, res, labels=labels[0]).save(
                os.path.join(cut, "parts", "%s.%s.%s.png" % (ms, src, tag)))
            for r in res:
                ends = " ".join("%s %s %+.1f%s" % ("конец" if e["free"] else "стык", e["side"], e["out"],
                                                    "?" if e["flat"] < FLAT else "") for e in r.get("ends", []))
                pf = r.get("profile")
                rows.append([ms, t, src, r["verdict"], r["part"], "; ".join(r.get("why", []) + r.get("notes", [])),
                             ends, r.get("turn_deg", ""), r.get("iou_asis", ""), r.get("iou_fit", ""),
                             r.get("color_de", ""), ("%+.2f %s" % (pf["max_dev"], pf["verdict"])) if pf else ""])
            for j in jn:
                rows.append([ms, t, src, j["verdict"], "%s|%s" % (j["a"], j["b"]), j["why"],
                             "стык %+.1f к %s (%s)" % (j["shift"], j["toward"], j["status"]), "", "", "", "", ""])
        size, _s = size_native(a_ref, m_o)
        out["size"] = size
        out["k4_rounding"] = k4_rounding(meta, a_ref, m_o, png_a)
        out["cut"] = cut_check(meta, raw_alpha, raw_off, m_o)
        for nm_, r_ in (("size", out["size"]), ("cut", out["cut"])):
            rows.append([ms, t, "item", r_["verdict"], nm_, r_["why"], "", "", "", "", "", ""])
        # три итога раздельно (указание специалиста 05.10): конструкция - по сырому ответу (то, что нарисовано) и
        # размеру; размещение - срез клетками и кадром (W-072: обрезанный край - не довод против рисунка); рисунок -
        # weapon_accept. PNG пака - справка: он отличается от сырого только срезом и округлением k=4
        con = max(out["raw"]["verdict"], out["size"]["verdict"], key=VERD.get)
        # надёжное нарушение (указание специалиста 05.10) - число, не зависящее от выделения детали: габарит по
        # родной альфе вне ±3 %, и FAIL детали, устойчивый к разметке (label_check). Остальные FAIL деталей -
        # зависят от разметки: вопрос, а не доказанный дефект. Допуски те же
        proven, sens = [], []
        if size["verdict"] == "FAIL":
            proven.append({"kind": "SIZE", "part": "", "why": size["why"]})
        lc = out["raw"]["label_check"]
        for r in out["raw"]["parts"]:
            if r["verdict"] != "FAIL":
                continue
            c_ = lc.get(r["part"], {"robust": False, "variants": {}, "doubt": ["нет проверки разметки"]})
            row = {"kind": "PART", "part": r["part"], "why": "; ".join(r["why"]), "variants": c_["variants"],
                   "doubt": c_["doubt"]}
            (proven if c_["robust"] else sens).append(row)
        out["construction"] = {"verdict": "FAIL" if proven else ("REVIEW" if con != "PASS" else "PASS"),
                               "measures_verdict": con, "proven": proven, "label_sensitive": sens,
                               "why": out["raw"]["why"] + ([size["why"]] if size["why"] else []),
                               "questions": out["raw"]["questions"], "label_issues": out["raw"]["label_issues"]}
        out["placement"] = placement(out["cut"])
        report[ms] = {"type": t, **out}
        kr = out["k4_rounding"]
        cu = out["cut"]
        print("%s %-22s конструкция %-6s (вопросов %d) | размещение %-8s | размер %s %+.1f/%+.1f%% | срез %.1f "
              "(в габарите оригинала %s, за ним %s, с .wide осталось бы %s) | %s" % (
            ms, t, con, len(out["raw"]["questions"]), out["placement"]["verdict"], size["verdict"],
            size["uniform_dw_pct"], size["uniform_dh_pct"], cu["total_hd"], cu.get("cut_orig_hd", "-"),
            cu.get("cut_wider_hd", "-"), cu.get("wide_left_hd", "-"), "; ".join(out["construction"]["why"])))
        print("    k=4 (округление, не вердикт): точно %.2fx%.2f HD, поставлено %s, PNG по альфе %s, оригинал %s" % (
            kr["exact_hd"][0], kr["exact_hd"][1], kr.get("placed_hd"), kr.get("png_alpha_hd"), kr["orig_hd"]))
        for r in out["png"]["parts"]:
            if r["verdict"] != "PASS":
                print("    %-10s %-12s %s %s" % (r["verdict"], r["part"], "; ".join(r.get("why", [])),
                                               ("(" + ", ".join(r.get("notes", [])) + ")") if r.get("notes") else ""))
    os.makedirs(os.path.join(cut, "parts"), exist_ok=True)
    tp = os.path.join(cut, "parts", "parts_%s.tsv" % tag)
    with open(tp, "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["master", "type", "src", "verdict", "part", "why", "ends", "turn_deg", "iou_asis", "iou_fit",
                    "color_de", "profile"])
        w.writerows(rows)
    jp = os.path.join(cut, "parts", "parts_%s.json" % tag)
    with open(jp, "w", encoding=ENC) as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("-> %s, %s" % (tp, jp))
    return report


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["show", "check"])
    ap.add_argument("--only", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--cut", default="")
    ap.add_argument("--tag", default="check")
    a = ap.parse_args()
    os.chdir(ROOT)
    masters = a.only.split(",")
    if a.cmd == "show":
        show(masters, a.out or os.path.join(PARTS, "show_%s.png" % masters[0]))
    else:
        if not a.cut:
            raise SystemExit("--cut обязателен")
        check(masters, a.cut, a.tag)


if __name__ == "__main__":
    main()
