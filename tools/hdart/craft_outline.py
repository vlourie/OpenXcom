#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""craft_outline.py - очертания НЛО и кораблей сверху для глобуса и воздушного боя.

Зачем. На глобусе корабль - маркер 7x7 на любом зуме, в воздушном бою - круглая клякса.
Вместо них HD-слой рисует маленький контур самого корабля. Контур берётся не с картинки
глоссария (там вид сбоку), а с карты корабля на поле боя: это точный план сверху.

Как снимается план (сверено с кодом движка):
  * террейн корабля - поле battlescapeTerrainData у НЛО и крафта, итог слияния рулсетов
    из .index/mod/Piratez/rul/values.tsv (чтение QUOTE_NONE, R-109);
  * блок .MAP раскладывается как BattlescapeGenerator::loadMAP (map_mockup.read_block),
    байт 0 части клетки - пусто, остальное - сквозная нумерация mapDataSets (pc.resolve);
  * у записи MCD 12 слоёв LOFT (байты 8..19) по два вокселя высоты, каждый слой - 16 строк
    по 16 бит LOFTEMPS.DAT; столбец вокселя x - это бит 15 - x (TileEngine::voxelCheck);
  * правки LOFTS из MCDPatches рулсетов применяются поверх MCD.
План - высота самого верхнего вокселя в каждом столбце, контур - край непустого плана.

Выход:
  * user/mods/hd/hd/OUTLINE/<тип>.png - маска сверху, длинная ось по горизонтали, нос
    вправо (курс 0), сторона до 128, белый с покрытием в альфе (сглажено); index.txt рядом -
    <тип> <множитель длины>, только у типов с контуром (обе копии мода hd, R-087);
  * art/outline/outline.tsv - тип, размер в клетках, заполненность, откуда;
  * art/outline/sheet_NN.png - лист приёмки: план, нынешний маркер, контур на шести зумах
    при k=4 в настоящих пикселях экрана, на океане и на суше.
Нос. Карта корабля стоит по сетке клеток, поэтому план только поворачивается на 0/90/180/270
(до 02.10 вертели по PCA, и знак оси был случайным - тестеры видели полёт боком и задом):
  * корабль игрока - картинка ангара (BASEBITS sprite + 33) нарисована сверху НОСОМ ВВЕРХ,
    у SIDEWAYS из gen_craft_lights - носом влево; план поворачивается так, чтобы лучше всего
    совпасть с её силуэтом (IoU по четырём поворотам и отражению, запас до второго - на листе);
  * корабль без карты боя (истребители) - силуэт самой картинки ангара, размер средний (1.0):
    картинки ангара нарисованы не в одном масштабе;
  * НЛО - длинная ось вдоль хода, нос - конец, дальний от центра площади (хвост и крылья
    тяжелее носа); точность правила печатается по кораблям игрока, где нос известен;
  * art/outline/orient.json {тип: доп. поворот по часовой, кратно 90} - поправка по листу.
На листе у каждого контура стрелка курса: нос обязан смотреть по стрелке.

    py -3.13 tools\hdart\craft_outline.py               # всё: маски, таблица, листы
    py -3.13 tools\hdart\craft_outline.py --only STR_VESSEL_FRIGATE --no-write
"""
import argparse
import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                      # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

import map_mockup as mm                                 # noqa: E402
import obj_struct as ost                                # noqa: E402
import pck_census as pc                                 # noqa: E402
from gen_base import basebits_map                       # noqa: E402
from gen_craft_lights import SIDEWAYS, body_mask, load_frame  # noqa: E402

ENC = "utf-8-sig"
VALUES = os.path.join(".index", "mod", "Piratez", "rul", "values.tsv")
OUT_DIR = os.path.join("art", "outline")
MOD_OUT = [os.path.join("user", "mods", "hd", "hd", "OUTLINE"),
           os.path.join(mm.INSTALL, "user", "mods", "hd", "hd", "OUTLINE")]
MASK_SIDE = 128

# длина контура в пикселях базового экрана по зумам 0..5 для корабля в 5 клеток длиной;
# k=4 - четыре настоящих пикселя на базовый
ZOOM_LEN = [4, 5, 6, 8, 10, 12]
K = 4
OCEAN = (20, 44, 96)
LAND = (62, 84, 46)


def load_values(path=VALUES):
    csv.field_size_limit(1 << 30)
    out = {}
    with open(path, encoding=ENC, newline="") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(row) < 4 or row[0] not in ("ufos", "crafts", "MCDPatches", "alienMissions", "ufoTrajectories"):
                continue
            try:
                v = json.loads(row[3])
            except ValueError:
                v = row[3]
            out.setdefault((row[0], row[1]), {})[row[2]] = v
    return out


def flying_ufos(vals):
    """НЛО, которые хоть в одной волне миссии летят: первая точка траектории выше земли
    (высота 0 - это место на земле, CA_SPAWN и подобные; таким остаётся маркер)."""
    traj = {k[1]: v for k, v in vals.items() if k[0] == "ufoTrajectories"}
    out = set()
    for (sec, _), f in vals.items():
        if sec != "alienMissions":
            continue
        for w in f.get("waves") or []:
            if not isinstance(w, dict) or not w.get("ufo"):
                continue
            wp = (traj.get(w.get("trajectory")) or {}).get("waypoints") or []
            if wp and len(wp[0]) > 1 and wp[0][1] > 0:
                out.add(w["ufo"])
    return out


class Plan:
    """План сверху по вокселям LOFT; MCDPatches накладываются на записи."""

    def __init__(self, world, patches):
        self.st = ost.Struct(world)
        self.patches = patches
        self.recs = {}

    def records(self, s):
        key = s.upper()
        if key not in self.recs:
            recs = [bytearray(r) for r in self.st.records(s)]
            for p in self.patches.get(s, []) + (self.patches.get(key, []) if key != s else []):
                i = p.get("MCDIndex")
                if isinstance(i, int) and 0 <= i < len(recs) and isinstance(p.get("LOFTS"), list):
                    for j, v in enumerate(p["LOFTS"][:12]):
                        recs[i][8 + j] = int(v) & 0xFF
            self.recs[key] = recs
        return self.recs[key]

    def block(self, sets, block):
        sx, sy, sz, cells = mm.read_block(self.st.world, block)
        sizes = {s: len(self.records(s)) for s in sets}
        h = np.zeros((sy * 16, sx * 16), np.int16)
        loft = self.st.loft[:, :, ::-1]                       # бит 15 - x -> столбец x
        nl = len(loft)
        for (x, y, z), parts in cells.items():
            for v in parts:
                if not v:
                    continue
                s, i = pc.resolve(v, sets, sizes)
                if s is None:
                    continue
                rec = self.records(s)[i]
                for layer in range(12):
                    lid = rec[8 + layer]
                    if not lid or lid >= nl:
                        continue
                    top = z * 12 + layer + 1
                    win = h[y * 16:(y + 1) * 16, x * 16:(x + 1) * 16]
                    np.maximum(win, np.where(loft[lid], top, 0), out=win)
        return sx, sy, sz, h


def principal_angle(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) < 3:
        return 0.0
    x = xs - xs.mean()
    y = ys - ys.mean()
    cov = np.cov(np.stack([x, y]))
    w, v = np.linalg.eigh(cov)
    vx, vy = v[:, 1]
    if w[1] < w[0] * 1.15:                                    # почти круглый - не вертим
        return 0.0
    return math.degrees(math.atan2(vy, vx))


def fill_holes(mask):
    """Всё, до чего пустота не дотекает от края, - внутри корабля. На размере в десяток
    пикселей внутренний двор кольца - лишняя черта, на глобусе нужен только силуэт."""
    out = np.zeros(mask.shape, bool)
    out[0, :], out[-1, :], out[:, 0], out[:, -1] = ~mask[0, :], ~mask[-1, :], ~mask[:, 0], ~mask[:, -1]
    free = ~mask
    while True:
        p = np.pad(out, 1)
        grown = (p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & free
        if (grown == out).all():
            return ~out
        out = grown


def main_part(mask):
    """Доля площади у самого крупного связного куска (по сетке 4x4 вокселя, 8 соседей).
    Пеший патруль, колонна машин, лагерь - россыпь, один контур её не опишет."""
    hh, ww = mask.shape
    g = mask[:hh - hh % 4, :ww - ww % 4].reshape(hh // 4, 4, ww // 4, 4).any(axis=(1, 3))
    seen = np.zeros(g.shape, bool)
    total = int(g.sum())
    best = 0
    keep = np.zeros(g.shape, bool)
    for y0, x0 in zip(*np.nonzero(g)):
        if seen[y0, x0]:
            continue
        seen[y0, x0] = True
        stack, part = [(y0, x0)], []
        while stack:
            y, x = stack.pop()
            part.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < g.shape[0] and 0 <= xx < g.shape[1] and g[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        stack.append((yy, xx))
        best = max(best, len(part))
        if len(part) >= 0.1 * total:                       # куски меньше десятой доли - мусор плана
            ys, xs = zip(*part)
            keep[list(ys), list(xs)] = True
    full = np.zeros(mask.shape, bool)
    full[:hh - hh % 4, :ww - ww % 4] = np.repeat(np.repeat(keep, 4, 0), 4, 1)
    return (best / total if total else 0.0), mask & full


def crop(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return mask
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def variants(mask):
    """[(k, flip, маска)]: четыре поворота np.rot90 и их отражения слева направо.
    Отражение не меняет, где нос (верх остаётся верхом)."""
    out = []
    for k in range(4):
        r = np.rot90(mask, k)
        out.append((k, False, r))
        out.append((k, True, r[:, ::-1]))
    return out


def fit_iou(a, b, side=48):
    """IoU двух масок, вписанных по большей стороне в квадрат side с сохранением пропорций и
    поставленных по центру: неверный поворот вытянутого корабля проигрывает и формой, и боком."""
    def norm(m):
        m = crop(m)
        f = side / max(m.shape)
        im = Image.fromarray((m * 255).astype(np.uint8))
        im = im.resize((max(1, round(m.shape[1] * f)), max(1, round(m.shape[0] * f))), Image.BILINEAR)
        out = np.zeros((side, side), np.float32)
        y0, x0 = (side - im.height) // 2, (side - im.width) // 2
        out[y0:y0 + im.height, x0:x0 + im.width] = np.asarray(im, np.float32) / 255.0
        return out
    pa, pb = norm(a), norm(b)
    inter = np.minimum(pa, pb).sum()
    union = np.maximum(pa, pb).sum()
    return float(inter / union) if union else 0.0


def nose_by_hangar(mask, hangar):
    """План носом вверх по совпадению с силуэтом ангара (нос вверх).
    -> (маска носом вверх, лучший IoU, запас до лучшего поворота с ДРУГИМ носом)."""
    scored = sorted(((fit_iou(m, hangar), k, fl, m) for k, fl, m in variants(mask)),
                    key=lambda t: -t[0])
    best = scored[0]
    other = max((s for s in scored if s[1] != best[1]), key=lambda t: t[0])
    return best[3], best[0], best[0] - other[0]


def nose_by_centroid(mask):
    """План носом вверх для НЛО: длинная сторона габарита вертикально, нос - конец, дальний от
    самого широкого места. Почти квадратный план - та же проверка по обоим поворотам.
    -> (маска носом вверх, сдвиг широкого места от середины в долях длины)."""
    best = None
    for k in range(4):
        m = crop(np.rot90(mask, k))
        hh, ww = m.shape
        if hh < ww * 0.87:                                  # длинная ось лежит поперёк хода
            continue
        # самое широкое место (полоса от 90% наибольшей ширины) ближе к хвосту: крылья, оперение
        # и двигатели тяжелее носа. Проверено на кораблях игрока с известным носом: 29 из 34,
        # центр площади - 23, узкий конец - 18-23 (craft_outline печатает итог при каждом прогоне)
        wp = m.sum(1)
        skew = (np.nonzero(wp >= wp.max() * 0.9)[0].mean() - (hh - 1) / 2.0) / hh   # >0: ближе к низу
        cand = (hh / max(ww, 1), skew, m)
        if best is None or (cand[0], cand[1]) > (best[0], best[1]):
            best = cand
    return best[2], best[1]


def hangar_mask(f, sprites):
    """Силуэт картинки ангара корабля носом вверх (bool) или None. Тень снимается body_mask."""
    s = f.get("sprite")
    if not isinstance(s, int):
        return None
    loaded = load_frame(s + 33, sprites)
    if loaded is None:
        return None
    body = body_mask(*loaded)
    if s + 33 in SIDEWAYS:
        body = body.T                                       # нос влево -> вверх
    return crop(body) if body.any() else None


def nose_up_to_right(m):
    return np.rot90(m, -1)                                  # по часовой: верх уходит вправо


def canonical(mask_right, extra=0):
    """Маска сверху носом вправо (bool), сглаженная, в коробке со стороной до MASK_SIDE.
    extra - доп. поворот по часовой, кратно 90 (orient.json)."""
    filled = fill_holes(mask_right)
    filled = np.rot90(filled, -int(round(extra / 90.0)) % 4)
    mask = Image.fromarray((crop(filled) * 255).astype(np.uint8))
    up = max(4, int(math.ceil(MASK_SIDE * 4 / max(mask.size))))   # картинка ангара 32x40 - x16
    big = mask.resize((mask.width * up, mask.height * up), Image.NEAREST)
    ang = 0.0
    # ступеньки вокселей и пикселей ангара стираем размытием примерно в пиксель исходника
    big = big.filter(ImageFilter.GaussianBlur(max(3.0, max(big.size) / MASK_SIDE * 1.2, up * 0.6)))
    a = np.asarray(big).astype(np.float32) / 255.0
    a = np.clip((a - 0.5) * 3 + 0.5, 0, 1)                    # обратно к краю, но мягко
    ys, xs = np.nonzero(a > 0.02)
    if not len(xs):
        return None, ang
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    im = Image.fromarray((a * 255).astype(np.uint8))
    f = MASK_SIDE / max(im.size)
    im = im.resize((max(1, round(im.width * f)), max(1, round(im.height * f))), Image.LANCZOS)
    return im, ang


def render(mask, length, angle, color, ring=1.0, fill=0.22, shimmer=None, ss=4):
    """Контур длиной length настоящих пикселей, повёрнутый на angle (0 - нос вправо, по часовой).
    То же, что будет делать движок: опрос маски с суперсэмплингом, кольцо = покрытие минус
    его сжатие на пиксель, внутри слабая заливка. shimmer - фаза блика (радианы) или None."""
    m = np.asarray(mask).astype(np.float32) / 255.0
    mh, mw = m.shape
    scale = length / max(mw, mh)
    side = int(math.ceil(length * 1.1)) + 4
    c = (side - 1) / 2.0
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    off = (np.arange(ss) + 0.5) / ss - 0.5
    yy, xx = np.mgrid[0:side, 0:side].astype(np.float32)
    acc = np.zeros((side, side), np.float32)
    for oy in off:
        for ox in off:
            dx, dy = xx + ox - c, yy + oy - c
            u = (ca * dx + sa * dy) / scale + mw / 2.0       # обратный поворот
            v = (-sa * dx + ca * dy) / scale + mh / 2.0
            ui = np.clip(np.floor(u).astype(int), 0, mw - 1)
            vi = np.clip(np.floor(v).astype(int), 0, mh - 1)
            inside = (u >= 0) & (u < mw) & (v >= 0) & (v < mh)
            acc += np.where(inside, m[vi, ui], 0)
    a = acc / (ss * ss)
    pad = np.pad(a, 1)
    ero = np.min(np.stack([pad[1 + dy:1 + dy + side, 1 + dx:1 + dx + side]
                           for dy in (-1, 0, 1) for dx in (-1, 0, 1)]), 0)
    edge = np.clip((a - ero) * 1.6 * ring, 0, 1)
    lum = np.ones_like(a)
    if shimmer is not None:
        th = np.arctan2(yy - c, xx - c)
        lum = 0.65 + 0.35 * np.clip(np.cos(th - shimmer), 0, 1) ** 3 * 1.0 + 0.0
    alpha = np.clip(edge + a * fill, 0, 1)
    col = np.array(color, np.float32)[None, None, :]
    rgb = np.clip(col * lum[..., None] + (255 - col) * (lum[..., None] - 0.65).clip(0) * 0.8, 0, 255)
    out = np.dstack([rgb, alpha * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def tile_len(h):
    """Длина корабля в клетках по маске (вдоль главной оси)."""
    mask = h > 0
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return 0.0
    ang = math.radians(principal_angle(mask))
    p = xs * math.cos(ang) + ys * math.sin(ang)
    return (p.max() - p.min() + 1) / 16.0


def size_factor(tiles):
    return float(np.clip(math.sqrt(max(tiles, 0.5) / 5.0), 0.6, 1.5))


# ------------------------------------------------------------------ лист

def marker_frames(world):
    p = os.path.join(mm.INSTALL, "user", "mods", "Piratez", "Resources", "UnitUI", "UFO_Icons.png")
    if not os.path.exists(p):
        return None
    return Image.open(p).convert("RGBA")


def cell_bg(w, h):
    im = Image.new("RGBA", (w, h), OCEAN + (255,))
    ImageDraw.Draw(im).rectangle([w // 2, 0, w, h], fill=LAND + (255,))
    return im


def arrow(d, x, y, angle, n=10, color=(255, 230, 80, 255)):
    """Стрелка курса: куда летит контур, повёрнутый на angle (0 - вправо, по часовой)."""
    a = math.radians(angle)
    x2, y2 = x + n * math.cos(a), y + n * math.sin(a)
    d.line([(x, y), (x2, y2)], fill=color, width=1)
    for s in (2.6, -2.6):
        d.line([(x2, y2), (x2 - 4 * math.cos(a + s * 0.25), y2 - 4 * math.sin(a + s * 0.25))], fill=color, width=1)


def nose_sheet(rows, path, cols=12, side=72):
    """Лист приёмки носа: каждый контур носом ВВЕРХ (стрелка над ним), номер и откуда нос.
    Зелёная рамка - нос по картинке ангара, жёлтая - по правилу ширины, оранжевая -
    неуверенно (симметричный план или малый запас). Поправка - orient.json по номеру строки."""
    items = [r for r in rows if r["mask"] is not None]
    W, H = side + 16, side + 40
    im = Image.new("RGB", (cols * W, ((len(items) + cols - 1) // cols) * H), (14, 14, 18))
    d = ImageDraw.Draw(im)
    for n, r in enumerate(items):
        x, y = (n % cols) * W, (n // cols) * H
        sure = "нос неуверенно" not in r["note"]
        frame = ((90, 200, 110) if r.get("nose", "").startswith(("ангар", "силуэт")) else (220, 200, 80)) \
            if sure else (240, 140, 60)
        d.rectangle([x + 2, y + 2, x + W - 3, y + H - 3], outline=frame)
        o = render(r["mask"], side * 0.86, -90, r["color"])
        im.paste(o.convert("RGB"), (x + (W - o.width) // 2, y + 18 + (side - o.height) // 2), o)
        arrow(d, x + W // 2, y + 16, -90, n=10)
        d.text((x + 5, y + 3), str(n + 1), fill=(230, 230, 230))
        d.text((x + 5, y + H - 15), r["type"].replace("STR_VESSEL_", "").replace("STR_", "")[:13],
               fill=(200, 200, 200))
    im.save(path)
    return items


def sheet(rows, markers, path):
    lab_w, plan_w, cell = 230, 110, 84
    W = lab_w + plan_w + 40 + cell * 6 + cell * 2
    H = 22 + len(rows) * (cell + 6)
    im = Image.new("RGB", (W, H), (12, 12, 16))
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "arial.ttf"), 12)
    except OSError:
        font = None
    d.text((lab_w + plan_w + 46, 4), "зум 0..5 при k=4, пиксель в пиксель; справа x4 зум 2 и 5",
           fill=(200, 200, 200), font=font)
    for n, r in enumerate(rows):
        y = 22 + n * (cell + 6)
        d.text((4, y + 4), r["type"][:34], fill=(230, 230, 230), font=font)
        d.text((4, y + 20), "%s  %.1f кл.  %s" % (r["size"], r["tiles"], r["kind"]), fill=(150, 150, 150), font=font)
        d.text((4, y + 36), "блок %s  запол. %.2f" % (r["block"], r["fill"]), fill=(150, 150, 150), font=font)
        if r.get("note"):
            d.text((4, y + 52), r["note"], fill=(240, 160, 90), font=font)
        if r.get("nose"):
            d.text((4, y + 68), "нос: " + r["nose"], fill=(150, 200, 150), font=font)
        # слева план носом вверх, справа картинка ангара носом вверх: обязаны совпасть
        for j, pm in enumerate((r.get("up"), r.get("hangar"))):
            if pm is None or not pm.any():
                continue
            pim = Image.fromarray((pm * 200 + 30).astype(np.uint8)).convert("RGB")
            f = min((plan_w / 2 - 4) / pim.width, cell / pim.height)
            pim = pim.resize((max(1, int(pim.width * f)), max(1, int(pim.height * f))), Image.NEAREST)
            im.paste(pim, (lab_w + j * plan_w // 2, y))
        mk = r.get("marker")
        if markers is not None and mk is not None and 0 <= mk * 7 < markers.width:
            fr = markers.crop((mk * 7, 0, mk * 7 + 7, 7)).resize((7 * K, 7 * K), Image.NEAREST)
            bg = cell_bg(36, 36)
            bg.alpha_composite(fr, (4, 4))
            im.paste(bg.convert("RGB"), (lab_w + plan_w, y))
        if r["mask"] is None:
            continue
        for z in range(6):
            L = ZOOM_LEN[z] * K * r["factor"]
            bg = cell_bg(cell, cell)
            o = render(r["mask"], L, -30, r["color"], shimmer=1.0)
            bg.alpha_composite(o, ((cell - o.width) // 2, (cell - o.height) // 2))
            arrow(ImageDraw.Draw(bg), 14, cell - 14, -30)
            im.paste(bg.convert("RGB"), (lab_w + plan_w + 40 + z * cell, y))
        for j, z in enumerate((2, 5)):
            L = ZOOM_LEN[z] * K * r["factor"]
            o = render(r["mask"], L, -30, r["color"], shimmer=1.0)
            bg = cell_bg(o.width, o.height)
            bg.alpha_composite(o)
            f = max(1, min(4, (cell - 2) // max(o.size)))
            bg = bg.resize((bg.width * f, bg.height * f), Image.NEAREST)
            if bg.width > cell or bg.height > cell:
                bg = bg.crop((0, 0, min(cell, bg.width), min(cell, bg.height)))
            im.paste(bg.convert("RGB"), (lab_w + plan_w + 40 + 6 * cell + j * cell, y))
    im.save(path)


# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="типы НЛО/крафтов")
    ap.add_argument("--no-write", action="store_true", help="не писать маски в мод")
    ap.add_argument("--rows", type=int, default=24, help="строк на лист")
    a = ap.parse_args(argv)

    vals = load_values()
    patches = {k[1]: (v.get("data") or []) for k, v in vals.items() if k[0] == "MCDPatches"}
    world = mm.World()
    plan = Plan(world, patches)
    os.makedirs(OUT_DIR, exist_ok=True)
    orient_p = os.path.join(OUT_DIR, "orient.json")
    orient = json.load(open(orient_p, encoding=ENC)) if os.path.exists(orient_p) else {}
    skip_p = os.path.join(OUT_DIR, "skip.json")
    skip = set(json.load(open(skip_p, encoding=ENC)).get("skip", [])) if os.path.exists(skip_p) else set()

    sprites = basebits_map(os.path.join(mm.INSTALL, "user", "mods", "Piratez"))
    fly = flying_ufos(vals)
    rows, grounded = [], []
    for (sec, typ), f in sorted(vals.items(), key=lambda kv: (kv[0][0] != "crafts", kv[0][1])):
        if sec not in ("ufos", "crafts"):
            continue
        if a.only and typ not in a.only:
            continue
        if sec == "ufos" and typ not in fly:
            grounded.append(typ)
            continue
        t = f.get("battlescapeTerrainData")
        r = {"type": typ, "kind": "НЛО" if sec == "ufos" else "корабль",
             "size": str(f.get("size", "")).replace("STR_", ""), "marker": f.get("marker"),
             "block": "", "tiles": 0.0, "fill": 0.0, "mask": None, "height": None, "factor": 1.0,
             "color": (255, 120, 90) if sec == "ufos" else (120, 230, 255), "note": ""}
        if sec == "ufos" and r["marker"] is None:
            r["marker"] = 2
        r["body"] = None
        r["hangar"] = None
        if sec == "crafts":
            if not f.get("speedMax"):
                r["note"] = "не летает"
                rows.append(r)
                continue
            r["hangar"] = hangar_mask(f, sprites)
        if not isinstance(t, dict) or not t.get("mapBlocks"):
            r["note"] = "нет карты боя"
            rows.append(r)
            continue
        sets = [str(s) for s in t.get("mapDataSets") or []]
        blk = t["mapBlocks"][0].get("name") if isinstance(t["mapBlocks"][0], dict) else None
        r["block"] = blk or ""
        try:
            sx, sy, sz, h = plan.block(sets, blk)
        except SystemExit as e:
            r["note"] = str(e)
            rows.append(r)
            continue
        mask = h > 0
        r["height"] = h
        if mask.any():
            ys, xs = np.nonzero(mask)
            box = (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)
            r["fill"] = float(mask.sum()) / box
            if r["fill"] > 0.93 and box >= (sx * 16) * (sy * 16) * 0.9:
                r["note"] = "весь блок - не корабль?"
        r["tiles"] = tile_len(h)
        r["factor"] = size_factor(r["tiles"])
        r["part"], body = main_part(mask) if mask.any() else (0.0, mask)
        if not body.any():
            r["note"] = "пустой план"
        elif r["part"] < 0.5:
            r["note"] = "россыпь (%.0f%%) - маркер" % (r["part"] * 100)
        else:
            r["body"] = body
        rows.append(r)

    # длина в клетках у кораблей без карты: по отношению длины плана к длине картинки ангара
    ratio = [r["tiles"] / max(crop(r["hangar"]).shape) for r in rows
             if r["body"] is not None and r["hangar"] is not None and r["hangar"].sum() >= 60]
    per_px = float(np.median(ratio)) if ratio else 0.25
    print("клеток на пиксель ангара: %.3f (по %d кораблям)" % (per_px, len(ratio)))

    # НЛО - тот же аппарат, что корабль игрока (STR_VESSEL_POL_DROPSHIP и STR_DROPSHIP):
    # нос по картинке ангара близнеца, если силуэт с ней уверенно совпадает
    by_name = {r["type"].replace("STR_", ""): r for r in rows
               if r["kind"] == "корабль" and r["hangar"] is not None}
    twins = {}
    for r in rows:
        if r["kind"] != "НЛО":
            continue
        s = r["type"].replace("STR_VESSEL_", "")
        for p in ("CC_", "CE_", "CI_", "NIN_", "POL_", "BANDIT_"):
            if s.startswith(p):
                s = s[len(p):]
        if s in by_name:
            twins[r["type"]] = (by_name[s]["type"], by_name[s]["hangar"])

    hits = total = 0
    for r in rows:
        typ = r["type"]
        up = None
        if r["body"] is not None and r["hangar"] is not None:
            up, iou, margin = nose_by_hangar(r["body"], r["hangar"])
            r["nose"] = "ангар %.2f, запас %.2f" % (iou, margin)
            if margin < 0.03 or iou < 0.45:
                r["note"] = "нос неуверенно"
            # проверка правила НЛО на корабле, где нос известен
            guess, _ = nose_by_centroid(r["body"])
            if margin >= 0.03 and iou >= 0.45:
                total += 1
                hits += fit_iou(guess, up) > fit_iou(guess, np.rot90(up, 2))
        elif r["body"] is not None:
            twin = twins.get(typ)
            if twin is not None:
                up, iou, margin = nose_by_hangar(r["body"], twin[1])
                if iou >= 0.6 and margin >= 0.03:
                    r["nose"] = "ангар %s %.2f, запас %.2f" % (twin[0].replace("STR_", ""), iou, margin)
                else:
                    twin = None
            if twin is None:
                up, skew = nose_by_centroid(r["body"])
                r["nose"] = "широкое место %+.2f" % skew
                if abs(skew) < 0.04:
                    r["note"] = "нос неуверенно"
        elif r["hangar"] is not None and r["note"] == "нет карты боя" and r["hangar"].sum() >= 60:
            part, hb = main_part(np.pad(r["hangar"], 4))
            if part >= 0.5:
                up = crop(hb)
                # картинки ангара нарисованы не в одном масштабе: истребитель в ней не меньше
                # драккара, и длина по ней - только для таблицы; на глобусе - средний размер
                r["tiles"] = max(up.shape) * per_px
                r["factor"] = 1.0
                r["nose"] = "силуэт ангара"
                r["note"] = ""
        if up is None:
            continue
        if typ in skip:
            r["note"] = "skip.json - маркер"
            continue
        if typ in orient:
            r["nose"] += ", orient.json %+d" % int(orient[typ])
        r["up"] = up
        r["mask"], _ = canonical(nose_up_to_right(up), float(orient.get(typ, 0)))
        if r["mask"] is None:
            r["note"] = "пустой план"
    for r in rows:
        print("%-40s %-8s %5.1f кл. запол. %.2f  %-26s %s" % (r["type"], r["kind"], r["tiles"], r["fill"],
                                                          r.get("nose", ""), r["note"]))
    if total:
        print("правило носа НЛО на кораблях с ангаром: верно %d из %d" % (hits, total))

    with open(os.path.join(OUT_DIR, "outline.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["type", "kind", "size", "block", "tiles", "factor", "fill", "nose", "note"])
        for r in rows:
            w.writerow([r["type"], r["kind"], r["size"], r["block"], "%.2f" % r["tiles"],
                        "%.2f" % r["factor"], "%.2f" % r["fill"], r.get("nose", ""), r["note"]])
        for typ in grounded:
            w.writerow([typ, "НЛО", "", "", "", "", "", "", "не летает - маркер"])
    if not a.no_write and not a.only:
        # обе копии мода hd (R-087): репозиторная и та, что в установке, - игра читает вторую
        for d in MOD_OUT:
            os.makedirs(d, exist_ok=True)
            for name in os.listdir(d):
                if name.endswith(".png") or name == "index.txt":
                    os.remove(os.path.join(d, name))
            with open(os.path.join(d, "index.txt"), "w", encoding="ascii", newline="\n") as f:
                f.write("# craft_outline.py: <ufo or craft type> <length factor>; mask <type>.png, nose right\n")
                for r in rows:
                    if r["mask"] is not None:
                        # движок читает PNG как RGBA (HdSprites::decodePng): покрытие - в альфе
                        white = Image.new("L", r["mask"].size, 255)
                        Image.merge("RGBA", (white, white, white, r["mask"])).save(
                            os.path.join(d, r["type"] + ".png"))
                        f.write("%s %.3f\n" % (r["type"], r["factor"]))
            print("маски:", d)
    items = nose_sheet(rows, os.path.join(OUT_DIR, "nose_review.png"))
    with open(os.path.join(OUT_DIR, "nose_review.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["n", "type", "kind", "nose", "note"])
        for n, r in enumerate(items):
            w.writerow([n + 1, r["type"], r["kind"], r.get("nose", ""), r["note"]])
    print("лист носа", os.path.join(OUT_DIR, "nose_review.png"), len(items))
    markers = marker_frames(world)
    for n in range(0, len(rows), a.rows):
        p = os.path.join(OUT_DIR, "sheet_%02d.png" % (n // a.rows + 1))
        sheet(rows[n:n + a.rows], markers, p)
        print("лист", p)
    print("летают %d, с контуром %d; на земле (маркер) %d"
          % (len(rows), sum(1 for r in rows if r["mask"] is not None), len(grounded)))


if __name__ == "__main__":
    main()
