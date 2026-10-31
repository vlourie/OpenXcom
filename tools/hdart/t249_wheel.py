#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000249: колесо URBAN_WASTE 86 и вся его семья - гладкий край вместо ступенчатой альфы. Без генерации.

Vitali 23.10: «это колесо, предмет, у него не должно быть квадратов по краям». У текущего HD (sdxl_legacy) и у кадра g0922 URBAN:86
одна и та же ступенчатая альфа (классика x4: ступеньки в 4 пикселя HD, тёмные квадраты в нижней части покрышки).

Что делается:
  1. Основа - g0922 URBAN:86 (art/_backup/hd_TERRAIN_2026-09-22/URBAN.PCK/86.png): литой диск со спицами, чистая покрышка;
     содержимое внутри силуэта не трогается (ни размытия, ни резкости).
  2. Новый силуэт: маска бывшей альфы на сетке x8, гладкая по радиусу SIG (ступеньки в 4 пикселя HD уходят,
     контур - плавная овальная кривая), порог по середине, край мягкий (гаусс EDGE, около полутора пикселей HD).
  3. Цвет у края: старая кайма (ступени и квадраты) в 3 пикселя от края выбрасывается, на её место цвет тянется
     от ядра ближайшим пикселем (нет квадратов, нет ореола); внутри ядра цвет - оригинал.
  4. Тон под набор: сдвиг среднего Lab основы к классике НАБОРА так же, как у нынешних кадров семьи: у каждого члена
     (перекраски, R-457) нынешнее среднее Lab минус нынешнее среднее Lab URBAN_WASTE:86, добавленное к новой основе.
     Побайтные копии классики (DUSKURBAN, MILURBAN, URBAN_GOODS, IDT_SNOWVILBAN:82) получают тот же сдвиг своего набора.

    py -3.13 tools/hdart/t249_wheel.py                  # кадры в art/tickets/t249/out_wheel/TERRAIN/...
    py -3.13 tools/hdart/t249_wheel.py --sheet          # лист art/_review/tickets_2026-10-23/t249_wheel2.png
    py -3.13 tools/hdart/t249_wheel.py --install --yes  # + в мод hd через манифест (по слову Vitali, под очередью правок)
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts           # noqa: E402
import water_build as wb            # noqa: E402

DONOR = ROOT / "art" / "_backup" / "hd_TERRAIN_2026-09-22" / "URBAN.PCK" / "86.png"
OUT = ROOT / "art" / "tickets" / "t249" / "out_wheel"
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-23"
BASE = ("URBAN_WASTE", 86)
# семья классики 86 (ticket_family.py URBAN_WASTE:86, 11 членов + основа). 23.10 Vitali: колесо на ВСЕ кадры семьи, в том числе
# те, где нынешний HD - другой предмет своей темы (CULTAREA, DAWNURBAN - светящаяся плита, DUSKURBAN и MILURBAN - люк,
# IDT_SNOWVILBAN:82 - шестигранник, NUKE1:18 - лава (в классике колесо с оранжево-красным диском), SEAURBANDIO - бирюзовая плита, URBAN:86 - куча обломков): классика у всех -
# одно колесо (побайтная копия или перекраска). Тон члена: у URBANWAR, URBAN_GOODS, VILBAN - по нынешнему HD (как задумано
# раньше), у остальных - по палитре КЛАССИКИ набора (SEAURBANDIO бирюзовое, NUKE1 тёпло-рыжее, прочие серые, как основа);
# у DUSKURBAN и MILURBAN листа классики в art/TERRAIN нет - сдвиг по нынешнему HD (только хрома).
FAMILY = [("URBANWAR", 86), ("URBAN_GOODS", 86), ("VILBAN", 82)]
FAMILY_ALL = [("URBAN", 86), ("CULTAREA", 86), ("DAWNURBAN", 86), ("DUSKURBAN", 86), ("IDT_SNOWVILBAN", 82), ("MILURBAN", 86),
              ("SEAURBANDIO", 86), ("NUKE1", 18)]
DISC_DARK = 0.22                     # диск (спицы, ступица) чуть темнее: L -= DISC_DARK * max(L - DISC_L0, 0)
DISC_L0 = 25.0
SS = 8                               # сетка сглаживания силуэта
SIG = 2.0                            # радиус сглаживания контура, пикс HD
GROW = 3.0                           # отступ наружу от ядра, пикс HD
EDGE = 1.0                           # мягкость края, пикс HD
RIM = 3                              # выбрасываемая кайма у старого края, пикс HD


def lab(rgb):
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.float32) / 255, cv2.COLOR_RGB2Lab)


def unlab(x):
    return np.clip(cv2.cvtColor(x.astype(np.float32), cv2.COLOR_Lab2RGB) * 255, 0, 255)


def load(p):
    return np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)


def game(s, f):
    return load(ts.PACK / (s + ".PCK") / ("%d.png" % f))


def smooth_alpha(alpha):
    """Гладкий мягкий силуэт 160x128 по ступенчатой альфе: покрышка выпуклая. Берётся ядро (старый силуэт без каймы
    RIM - в нём цвет настоящий), его сглаженная выпуклая оболочка и отступ наружу на GROW пикселей по кругу
    (скруглённый контур без углов многоугольника); край мягкий."""
    m = (alpha > 127).astype(np.float32)
    lab_, n = ndi.label(m)
    if n > 1:
        sizes = ndi.sum(m, lab_, range(1, n + 1))
        m = (lab_ == 1 + int(np.argmax(sizes))).astype(np.float32)
    m = ndi.binary_fill_holes(m > 0.5)
    core = ndi.binary_erosion(m, iterations=RIM).astype(np.float32)
    hi = cv2.resize(core, (128 * SS, 160 * SS), interpolation=cv2.INTER_LINEAR)
    g = cv2.GaussianBlur(hi, (0, 0), SIG * SS)
    b = (g > 0.5).astype(np.uint8)
    cnts, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    pts = max(cnts, key=cv2.contourArea)
    f = np.zeros_like(b)
    (ex, ey), (ea, eb), ang = cv2.fitEllipse(pts)
    cv2.ellipse(f, (int(round(ex)), int(round(ey))), (int(round(ea / 2)), int(round(eb / 2))), ang, 0, 360, 1, -1)
    miss = float(((b > 0) & (f == 0)).sum()) / float(b.sum())
    print("овал: центр (%.1f, %.1f) оси %.1f x %.1f угол %.1f, ядро вне овала %.1f%%" % (ex / SS, ey / SS, ea / SS, eb / SS, ang, 100 * miss))
    if miss > 0.04:                          # овал не накрывает ядро - берём выпуклую оболочку
        f = np.zeros_like(b)
        cv2.fillPoly(f, [cv2.convexHull(pts)], 1)
    dist = ndi.distance_transform_edt(f == 0)
    grown = (dist <= GROW * SS).astype(np.float32)
    soft = cv2.GaussianBlur(grown, (0, 0), EDGE * SS * 0.7)
    a = cv2.resize(soft, (128, 160), interpolation=cv2.INTER_AREA)
    return np.clip(a, 0, 1)


def clean_color(rgba, new_a):
    """Цвет: ядро (старый силуэт без каймы RIM) - оригинал, дальше - ближайший цвет ядра."""
    m = rgba[..., 3] > 127
    core = ndi.binary_erosion(m, iterations=RIM)
    idx = ndi.distance_transform_edt(~core, return_distances=False, return_indices=True)
    ext = rgba[..., :3][idx[0], idx[1]]
    # шов между ядром и вытянутым цветом: чуть размыть только вытянутую часть
    far = ndi.gaussian_filter(ext, (1.2, 1.2, 0))
    w = ndi.gaussian_filter((~core).astype(np.float32), 0.8)[..., None]
    return rgba[..., :3] * (1 - w) + (far * 0.5 + ext * 0.5) * w


def mean_lab(rgba):
    m = rgba[..., 3] > 127
    return lab(rgba[..., :3])[m].mean(0)


def classic_lab(s, f):
    """Среднее Lab классики кадра (палитра Пираток) или None, если листа набора нет в art/TERRAIN."""
    try:
        cl = wb.read_set(s)[f]
    except TypeError:
        return None
    pal = wb.palette()
    return lab(pal[cl[cl > 0]][..., :3].astype(np.float32).reshape(-1, 1, 3)).reshape(-1, 3).mean(0)


def base_new():
    d = load(DONOR)
    a = smooth_alpha(d[..., 3])
    rgb = clean_color(d, a)
    return np.dstack([rgb, a * 255]), d


NUKE = ("NUKE1", 18)
NUKE_EL = ((64.0, 115.0), (21.5, 15.5), -6.0)     # диск колеса в кадре HD: центр, полуоси, угол
NUKE_SOFT = 1.6                                   # мягкость края диска, пикс HD
NUKE_LK = 0.9                                     # доля рельефа (спицы, обод) диска основы


def nuke_disc(base):
    """NUKE1:18: в классике шина тёмно-серая, как у остальных, а в диске оранжево-красное пятно (индексы 20, 39-43, 101-105).
    Шина остаётся как у основы (серая, без сдвига тона); диск и ступица перекрашиваются: цвет (хрома и средняя яркость) -
    по оранжево-красным пикселям классики, растянутым x4 и расплывшимся на весь диск, рельеф спиц и обода - от основы."""
    cl = wb.read_set(NUKE[0])[NUKE[1]]
    pal = wb.palette()
    hot = (cl == 20) | ((cl >= 39) & (cl <= 43)) | ((cl >= 101) & (cl <= 105))
    rgb = np.zeros(cl.shape + (3,), np.float32)
    rgb[cl > 0] = pal[cl[cl > 0]][:, :3]
    # цвет пятна: ближайший горячий пиксель классики, x4 и размытие - сплошное поле цвета на весь диск
    idx = ndi.distance_transform_edt(~hot, return_distances=False, return_indices=True)
    near = rgb[idx[0], idx[1]]
    up = cv2.resize(near, (128, 160), interpolation=cv2.INTER_CUBIC)
    up = cv2.GaussianBlur(up, (0, 0), 3.0)
    hl = lab(up)
    # маска диска
    m = np.zeros((160 * SS, 128 * SS), np.float32)
    (cx, cy), (ra, rb), ang = NUKE_EL
    cv2.ellipse(m, (int(cx * SS), int(cy * SS)), (int(ra * SS), int(rb * SS)), ang, 0, 360, 1.0, -1)
    m = cv2.resize(cv2.GaussianBlur(m, (0, 0), NUKE_SOFT * SS), (128, 160), interpolation=cv2.INTER_AREA)[..., None]
    bl = lab(base[..., :3])
    disc = m[..., 0] > 0.5
    # яркость: средняя по пятну классики + рельеф основы
    hot_l = lab(rgb)[hot][:, 0].mean()
    bmean = bl[..., 0][disc].mean()
    out = bl.copy()
    newL = hot_l + NUKE_LK * (bl[..., 0] - bmean)
    new = np.dstack([newL, hl[..., 1], hl[..., 2]])
    out = bl * (1 - m) + new * m
    r = base.copy()
    r[..., :3] = unlab(out)
    return r


def build_all():
    new, donor = base_new()
    cur0 = game(*BASE)
    # тон основы - к тону нынешнего URBAN_WASTE:86 по цвету покрышки: сдвиг только a, b и среднего L не трогаем резко
    cls = wb.read_set(BASE[0])[BASE[1]]
    pal = wb.palette()
    cm = pal[cls[cls > 0]][..., :3].astype(np.float32)
    c_lab = lab(cm.reshape(-1, 1, 3)).reshape(-1, 3).mean(0)
    n_lab = mean_lab(new)
    shift0 = np.array([0.0, c_lab[1] - n_lab[1], c_lab[2] - n_lab[2]], np.float32)       # хрома - к классике, яркость своя
    L = lab(new[..., :3]) + shift0
    base = new.copy()
    base[..., :3] = unlab(L)
    L = lab(base[..., :3])
    L[..., 0] -= DISC_DARK * np.maximum(L[..., 0] - DISC_L0, 0)
    base[..., :3] = unlab(L)
    res = {BASE: base}
    ref = mean_lab(cur0)
    base_cls = classic_lab(*BASE)
    for s, f in FAMILY + FAMILY_ALL:
        if (s, f) == NUKE:   # шина как у основы, диск оранжево-красный по классике
            res[(s, f)] = nuke_disc(base)
            continue
        c = None if (s, f) in FAMILY else classic_lab(s, f)
        if c is None:        # нет листа классики (или член по HD) - по нынешнему HD, только хрома
            d = mean_lab(game(s, f)) - ref
            d[0] = 0.0       # яркость - как у основы: у членов семьи разброс L небольшой, а чистая яркость - лицо диска
        else:
            d = c - base_cls
        L = lab(base[..., :3]) + d
        r = base.copy()
        r[..., :3] = unlab(L)
        res[(s, f)] = r
    return res


def save_all(res):
    paths = {}
    keep = {OUT / "TERRAIN" / (s + ".PCK") / ("%d.png" % f) for (s, f) in res}
    for old in (OUT / "TERRAIN").rglob("*.png") if (OUT / "TERRAIN").exists() else []:     # свой каталог вывода: старые кадры прочь
        if old not in keep:
            old.unlink()
    for (s, f), p in res.items():
        d = OUT / "TERRAIN" / (s + ".PCK")
        d.mkdir(parents=True, exist_ok=True)
        q = d / ("%d.png" % f)
        Image.fromarray(np.clip(p, 0, 255).round().astype(np.uint8), "RGBA").save(q)
        paths["TERRAIN/%s.PCK/%d.png" % (s, f)] = q
    return paths


def on_grey(im, k=6, bg=(110, 110, 116)):
    box = (20, 90, 104, 160)
    c = im.crop(box).resize(((box[2] - box[0]) * k, (box[3] - box[1]) * k), Image.NEAREST)
    out = Image.new("RGBA", c.size, bg + (255,))
    out.alpha_composite(c)
    return out


def make_sheet(res):
    from PIL import ImageDraw
    sc = ts.Scene()
    cls = sc.classic(*BASE)
    now = sc.hd(*BASE)
    new = Image.fromarray(np.clip(res[BASE], 0, 255).round().astype(np.uint8), "RGBA")
    panels = [("классика x4", on_grey(cls)), ("HD сейчас", on_grey(now)), ("HD новое (g0922 + гладкий силуэт)", on_grey(new))]
    ts.sheet(panels, REVIEW / "t249_wheel2.png", cols=3)
    # крупно в игровом масштабе на светлой и тёмной земле и в сцене
    terr, block = "URBAN_WASTE", "URBANWASTE62"
    found = ts.find_cells(sc, terr, block, [BASE])
    over = {(s.upper(), f): Image.fromarray(np.clip(p, 0, 255).round().astype(np.uint8), "RGBA") for (s, f), p in res.items()
            if s == BASE[0]}
    cx, cy = [(found[0][2][0] + found[0][2][2]) / 2 * 4, (found[0][2][1] + found[0][2][3]) / 2 * 4]
    box = (int(cx - 300), int(cy - 220), int(cx + 300), int(cy + 140))
    a = sc.render(terr, block, "classic", k=4, maxz=0)[0]
    b = sc.render(terr, block, "hd", k=4, maxz=0)[0]
    c = sc.render(terr, block, "hd", override=over, k=4, maxz=0)[0]
    sc_panels = [("сцена URBANWASTE62: классика", ts.crop_pad(a, box)), ("сейчас", ts.crop_pad(b, box)),
                 ("новое", ts.crop_pad(c, box))]
    ts.sheet(sc_panels, REVIEW / "t249_wheel2_scene.png", cols=3)
    # сводная лента: лист 1 над листом 2
    s1 = Image.open(REVIEW / "t249_wheel2.png")
    s2 = Image.open(REVIEW / "t249_wheel2_scene.png")
    W = max(s1.width, s2.width)
    out = Image.new("RGB", (W, s1.height + s2.height), (12, 12, 14))
    out.paste(s1, (0, 0))
    out.paste(s2, (0, s1.height))
    out.save(REVIEW / "t249_wheel2.png")
    (REVIEW / "t249_wheel2_scene.png").unlink()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    res = build_all()
    paths = save_all(res)
    print("кадров: %d -> %s" % (len(res), OUT))
    if a.sheet:
        make_sheet(res)
        print("лист:", REVIEW / "t249_wheel2.png")
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(paths, "t249_wheel", "t249_wheel.py 23.10 g0922 URBAN:86, гладкий силуэт",
                         "Vitali 23.10 (XP-000249 колесо); лист art/_review/tickets_2026-10-23/t249_wheel2.png",
                         "t249: колесо URBAN_WASTE 86 и семья - гладкий край")
    return 0


if __name__ == "__main__":
    sys.exit(main())
