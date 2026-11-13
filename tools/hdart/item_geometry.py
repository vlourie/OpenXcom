#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Замер геометрии мастеров HD-BIGOBS по контракту v4 (docs/research/inventory-items-redraw-contract-v4.md, §3, §5, §7 п.2).

До расхода видеокарты: габарит оригинала, совместимость размера 100% +-3% с допуском клеток и руки (§3.3),
защищённые области (значок взвода гранаты, §5), кандидат дульного среза (§5.1), карта цветовых зон (§4).
Если есть готовый HD (--hd <папка pack>), то же снимается с него без подгонки: одно известное преобразование
база -> HD (умножение на k), размер по основному силуэту (альфа >= 128), сдвиг, пиксели вне допуска ДО обрезки.

Числа здесь - замер, а не приёмка: порогов цвета нет (§4 - до калибровки на принятых примерах), вердикт по размеру
и положению - по контракту (3 %, дуло 0), остальное решает человек по листу.

    py -3.13 tools/hdart/item_geometry.py [--hd art/items/pilot-v1/pack/BIGOBS.PCK] [--out census/items/geometry]
Выход: <out>/geometry.tsv, zones.tsv, recheck.tsv (если --hd), cards.md, sheet.png
"""
import argparse
import colorsys
import csv
import json
import os
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))

import item_asset_check as iac          # noqa: E402

ENC = "utf-8-sig"
CARDS = "census/items/cards"
K = 4
TOL = 0.03
PRIMER = 4                              # SCANG.DAT кадр 6, 4x4, в (x, y) предмета - Inventory::drawItems primers()
# мастер, тип, кадр, клетки, стреляет (ось ствола - вверх у всех вертикальных стволов; дуло - кандидат, подтвердить)
MASTERS = [
    ("M-01", "STR_RIFLE_AK", 1168, (1, 3), True), ("M-02", "STR_RIFLE_AK_CLIP", 1169, (1, 1), False),
    ("M-03", "STR_PISTOL", 3, (1, 2), True), ("M-04", "STR_PISTOL_CLIP", 4, (1, 1), False),
    ("M-05", "STR_SHOTGUN", 1134, (1, 3), True), ("M-06", "STR_SAWED_OFF", 1180, (1, 2), True),
    ("M-07", "STR_CHAINGUN", 1256, (1, 3), True), ("M-08", "STR_FLAMETHROWER", 1140, (1, 3), True),
    ("M-09", "STR_GRENADE", 19, (1, 1), False), ("M-10", "STR_EMP_GRENADE", 2051, (2, 1), False),
    ("M-11", "STR_SATCHEL_CHARGE", 1284, (2, 2), False), ("M-12", "STR_MEDI_KIT", 1665, (1, 2), False),
    ("M-13", "STR_OXYGEN_TANK", 1865, (1, 3), False), ("M-14", "STR_LONG_KNIFE", 2081, (1, 2), False),
    ("M-15", "STR_BATTLE_AX", 4056, (1, 3), False), ("M-16", "STR_POTATO_SACK", 1617, (1, 1), False),
    ("M-17", "STR_SCROLL_E4", 4183, (2, 2), False), ("M-18", "STR_PIR_ASSAULT", 1607, (2, 2), False),
    ("M-19", "STR_FOOD_BAG", 1609, (2, 3), False), ("M-20", "STR_JUNK_PILE", 1617, (2, 3), False),
]
PRIMED = {"M-09", "M-10", "M-11"}       # гранаты и заряды: у взведённого движок рисует значок взвода (fuse timer)
HUES = (("red", 0, 18), ("orange", 18, 42), ("yellow", 42, 70), ("green", 70, 170), ("cyan", 170, 200),
        ("blue", 200, 260), ("violet", 260, 330), ("red", 330, 361))


def load_frame(t, frame):
    """Кадр BIGOBS как движок: индексы, 0 прозрачный (R-043) -> RGBA 32x48 и имя файла."""
    d = os.path.join(CARDS, "originals", t)
    src = [f for f in sorted(os.listdir(d)) if f.startswith("BIGOBS_%d__" % frame)]
    if len(src) != 1:
        raise SystemExit("%s: кадр BIGOBS %d - файлов %d" % (t, frame, len(src)))
    im = Image.open(os.path.join(d, src[0]))
    if im.mode != "P" or im.size != (iac.HAND_W, iac.HAND_H):
        raise SystemExit("%s: %s %s, ждал P 32x48" % (t, im.mode, im.size))
    idx = np.asarray(im)
    pal = np.asarray(im.getpalette()[:768], np.uint8).reshape(-1, 3)
    return np.dstack([pal[idx], np.where(idx == 0, 0, 255).astype(np.uint8)]), src[0]


def bbox(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def largest(mask):
    """Самая большая 8-связная часть маски (основной силуэт без отдельных усиков)."""
    seen = np.zeros(mask.shape, bool)
    best = None
    h, w = mask.shape
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        comp, q = [], deque([(y0, x0)])
        seen[y0, x0] = True
        while q:
            y, x = q.popleft()
            comp.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        q.append((yy, xx))
        if best is None or len(comp) > len(best):
            best = comp
    out = np.zeros(mask.shape, bool)
    for y, x in best or []:
        out[y, x] = True
    return out


def hue_family(rgb):
    """Цветовое семейство пикселя: neutral (серое, чёрное, белое) или тон по кругу."""
    r, g, b = (c / 255.0 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.22 or v < 0.12:
        return "neutral"
    deg = h * 360
    for name, a, z in HUES:
        if a <= deg < z:
            return name
    return "red"


def lum(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def zones(rgba, scale=1, alpha_min=1):
    """Цветовые зоны: семейство -> площадь (в пикселях базы), габарит в базе, средний цвет, средняя яркость."""
    a = rgba[..., 3] >= alpha_min
    fam = {}
    for y, x in zip(*np.nonzero(a)):
        fam.setdefault(hue_family(rgba[y, x, :3]), []).append((y, x))
    out = {}
    for name, pts in fam.items():
        ys = np.array([p[0] for p in pts])
        xs = np.array([p[1] for p in pts])
        cols = rgba[ys, xs, :3].astype(float)
        mean = cols.mean(0)
        out[name] = {"area": round(len(pts) / scale ** 2, 1),
                     "bbox": [int(xs.min() // scale), int(ys.min() // scale), int(xs.max() // scale) + 1,
                              int(ys.max() // scale) + 1],
                     "rgb": [int(round(c)) for c in mean], "lum": round(lum(mean), 1)}
    return out


def fit(b, rect):
    """Размер 100 % против прямоугольника: нужное уменьшение и сдвиг без уменьшения, если он возможен."""
    w, h = b[2] - b[0], b[3] - b[1]
    rw, rh = rect[2] - rect[0], rect[3] - rect[1]
    need = min(1.0, rw / w, rh / h)
    out_ = b[0] < rect[0] or b[1] < rect[1] or b[2] > rect[2] or b[3] > rect[3]
    shift = None
    if w <= rw and h <= rh:
        dx = max(rect[0] - b[0], 0) - max(b[2] - rect[2], 0)
        dy = max(rect[1] - b[1], 0) - max(b[3] - rect[3], 0)
        shift = (dx, dy)
    return need, out_, shift


def status(need, out_, shift):
    if not out_:
        return "OK"
    if need >= 1 - TOL:
        return "SHIFT_DECISION"         # размер влезает, но нужен перенос - только явным решением (§3.2)
    return "BLOCKED_GEOMETRY"


def muzzle(mask):
    """Кандидат дульного среза для вертикального ствола: верхняя строка силуэта (x0..x1, y). Подтверждать глазом."""
    ys, xs = np.nonzero(mask)
    y = int(ys.min())
    row = xs[ys == y]
    return int(row.min()), y, int(row.max()) + 1


def measure_hd(path, m, b0, rect_g, rect_h, cells, muz):
    hd = np.asarray(Image.open(path).convert("RGBA"))
    a = hd[..., 3]
    main = largest(a >= 128)
    bm = bbox(main)
    ball = bbox(a > 0)
    w0, h0 = (b0[2] - b0[0]) * K, (b0[3] - b0[1]) * K
    dw, dh = (bm[2] - bm[0]) / w0 - 1, (bm[3] - bm[1]) / h0 - 1
    sx, sy = bm[0] - b0[0] * K, bm[1] - b0[1] * K
    dx, dy = (2 - cells[0]) * 8 * K, (3 - cells[1]) * 8 * K
    hand = np.zeros((iac.HAND_H * K, iac.HAND_W * K), np.uint8)
    ys, xs = np.nonzero(a)
    ys2, xs2 = ys + dy, xs + dx
    ok = (ys2 >= 0) & (ys2 < hand.shape[0]) & (xs2 >= 0) & (xs2 < hand.shape[1])
    hand[ys2[ok], xs2[ok]] = 255
    lost_hand = int((~ok).sum())
    r = {"master": m, "hd_w": bm[2] - bm[0], "hd_h": bm[3] - bm[1], "want_w": w0, "want_h": h0,
         "dw_pct": round(100 * dw, 1), "dh_pct": round(100 * dh, 1),
         "shift_x": sx, "shift_y": sy, "bbox_all": ball, "bbox_main": bm,
         "out_grid": iac.outside(a, rect_g, K), "out_hand": iac.outside(hand, rect_h, K) + lost_hand}
    if muz:
        hx0, hy, hx1 = muzzle(main)
        r["muzzle_shift"] = (round((hx0 + hx1) / 2 - (muz[0] + muz[2]) / 2 * K, 1), hy - muz[1] * K)
    why = []
    if abs(dw) > TOL or abs(dh) > TOL:
        why.append("размер %+.1f%% / %+.1f%% (допуск 3%%)" % (100 * dw, 100 * dh))
    if sx or sy:
        why.append("сдвиг %+d, %+d HD-пикс" % (sx, sy))
    if muz and r["muzzle_shift"] != (0, 0):
        why.append("дуло сдвинуто %+.1f, %+d HD-пикс (допуск 0)" % r["muzzle_shift"])
    if r["out_grid"]:
        why.append("вне клеток до обрезки %d пикс" % r["out_grid"])
    if r["out_hand"]:
        why.append("вне допуска руки до обрезки %d пикс" % r["out_hand"])
    r["geometry"] = "REWORK" if why else "GEOMETRY_OK"
    r["why"] = "; ".join(why)
    return r, hd


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hd", default="", help="папка BIGOBS.PCK с готовыми <кадр>.<ТИП>.png для пересверки")
    ap.add_argument("--out", default="census/items/geometry")
    args = ap.parse_args()
    os.chdir(ROOT)
    os.makedirs(args.out, exist_ok=True)
    geo, zrows, rec, tiles = [], [], [], []
    for m, t, frame, cells, gun in MASTERS:
        rgba, src = load_frame(t, frame)
        a = rgba[..., 3] > 0
        b0, bmain = bbox(a), bbox(largest(a))
        rg, rh = iac.grid_rect(*cells), iac.hand_rect(*cells)
        dx, dy = (2 - cells[0]) * 8, (3 - cells[1]) * 8
        bh = (b0[0] + dx, b0[1] + dy, b0[2] + dx, b0[3] + dy)
        ng, og, sg_ = fit(b0, rg)
        nh, oh, sh = fit(bh, rh)
        st = "BLOCKED_GEOMETRY" if "BLOCKED_GEOMETRY" in (status(ng, og, sg_), status(nh, oh, sh)) else \
            ("SHIFT_DECISION" if "SHIFT_DECISION" in (status(ng, og, sg_), status(nh, oh, sh)) else "OK")
        muz = muzzle(a) if gun else None
        if gun and st == "SHIFT_DECISION":
            st = "BLOCKED_GEOMETRY"      # перенос стреляющего двигает дуло: допуск 0 (§5.1)
        row = {"master": m, "type": t, "frame": frame, "src": src, "cells": "%dx%d" % cells,
               "w0": b0[2] - b0[0], "h0": b0[3] - b0[1], "bbox0": list(b0), "bbox_main0": list(bmain),
               "grid_rect": list(rg), "grid_out": int(iac.outside(a.astype(np.uint8), rg, 1)),
               "grid_need_scale": round(ng, 3), "grid_shift": sg_,
               "hand_rect": list(rh), "hand_shift_engine": [dx, dy], "hand_need_scale": round(nh, 3),
               "hand_shift": sh, "status": st,
               "muzzle": list(muz) if muz else "", "primer_box": [0, 0, PRIMER, PRIMER] if m in PRIMED else ""}
        geo.append(row)
        for name, z in sorted(zones(rgba).items(), key=lambda kv: -kv[1]["area"]):
            zrows.append({"master": m, "source": "original", "family": name, **{k: z[k] for k in z}})
        hd = None
        if args.hd:
            p = os.path.join(args.hd, "%d.%s.png" % (frame, t))
            if os.path.exists(p):
                r, hd = measure_hd(p, m, b0, rg, rh, cells, muz)
                rec.append(r)
                hz = zones(hd, scale=K, alpha_min=128)
                for name, z in sorted(hz.items(), key=lambda kv: -kv[1]["area"]):
                    zrows.append({"master": m, "source": "hd", "family": name, **{k: z[k] for k in z}})
        tiles.append((row, rgba, hd))
        print("%-5s %-19s %s  %2dx%-2d  клетки %s: нужно x%.2f%s; рука: x%.2f%s  -> %s" % (
            m, t, row["cells"], row["w0"], row["h0"], row["grid_rect"], ng,
            "" if not og else (" сдвиг %s" % (sg_,) if sg_ else " сдвига нет"), nh,
            "" if not oh else (" сдвиг %s" % (sh,) if sh else " сдвига нет"), st))
    write(os.path.join(args.out, "geometry.tsv"), geo)
    write(os.path.join(args.out, "zones.tsv"), zrows)
    if rec:
        write(os.path.join(args.out, "recheck.tsv"), rec)
        for r in rec:
            print("%-5s %s %s" % (r["master"], r["geometry"], r["why"]))
    sheet(tiles, {r["master"]: r for r in rec}, os.path.join(args.out, "sheet.png"))
    cards(geo, os.path.join(args.out, "cards.md"))


def sides(b, rect):
    """Насколько силуэт выходит за прямоугольник с каждой стороны, в пикселях базы."""
    out = {"слева": rect[0] - b[0], "сверху": rect[1] - b[1], "справа": b[2] - rect[2], "снизу": b[3] - rect[3]}
    return ", ".join("%s %d" % (k, v) for k, v in out.items() if v > 0) or "нет"


def cards(geo, path):
    """Карточки конфликта геометрии (контракт v4 §3.3): только факты и варианты, решение - за Vitali."""
    L = ["# Карточки конфликта геометрии HD-BIGOBS",
         "",
         "Строит `tools/hdart/item_geometry.py` по контракту v4 (`docs/research/inventory-items-redraw-contract-v4.md`,",
         "§3.3). Руками не править - перезапустить скрипт.",
         "",
         "Допуск клеток - `item_asset_check.grid_rect`, руки - `hand_rect` после штатного сдвига "
         "`RuleItem::getHandSpriteOffX/Y` ((2 - w) * 8, (3 - h) * 8). Классика спрайт BIGOBS по клеткам не обрезает "
         "(`Inventory::drawItems`: `executeBlit(frame, _items, x, y)` на весь слой инвентаря) - всё, что ниже "
         "выходит за допуск, игрок сейчас видит поверх соседних клеток и рамки.",
         "",
         "Статусы: **OK** - 100 % помещается на своём месте; **SHIFT_DECISION** - помещается в допуске 3 % или "
         "переносом, нужен явный выбор; **BLOCKED_GEOMETRY** - 100 % +-3 % на месте не помещается. У стреляющего "
         "перенос двигает дульный срез (допуск 0, §5.1), поэтому перенос для него тоже конфликт.",
         "",
         "| Мастер | Тип | Клетки | Оригинал, баз. пикс | Вне клеток | Нужно для клеток | Нужно для руки | Статус |",
         "|---|---|---|---|---|---|---|---|"]
    for r in geo:
        L.append("| %s | `%s` | %s | %dx%d | %s | x%.2f | x%.2f | %s |" % (
            r["master"], r["type"], r["cells"], r["w0"], r["h0"],
            sides(r["bbox0"], r["grid_rect"]), r["grid_need_scale"], r["hand_need_scale"], r["status"]))
    for r in geo:
        if r["status"] == "OK":
            continue
        rg, rh, sh = r["grid_rect"], r["hand_rect"], r["hand_shift_engine"]
        bh = [r["bbox0"][0] + sh[0], r["bbox0"][1] + sh[1], r["bbox0"][2] + sh[0], r["bbox0"][3] + sh[1]]
        L += ["", "## %s `%s` - %s" % (r["master"], r["type"], r["status"]), "",
              "- Кадр BIGOBS %d (`%s`), клетки %s." % (r["frame"], r["src"], r["cells"]),
              "- Силуэт оригинала: габарит x %d..%d, y %d..%d = **%dx%d** базовых пикселей (при k=4 - %dx%d HD)." % (
                  r["bbox0"][0], r["bbox0"][2], r["bbox0"][1], r["bbox0"][3], r["w0"], r["h0"],
                  4 * r["w0"], 4 * r["h0"]),
              "- Допуск клеток x %d..%d, y %d..%d (%dx%d); оригинал за ним: %s; пикселей оригинала за допуском - %d." % (
                  rg[0], rg[2], rg[1], rg[3], rg[2] - rg[0], rg[3] - rg[1], sides(r["bbox0"], rg), r["grid_out"]),
              "- Допуск руки x %d..%d, y %d..%d; оригинал после штатного сдвига %s: за допуском %s." % (
                  rh[0], rh[2], rh[1], rh[3], tuple(sh), sides(bh, rh)),
              "- Требуемое равномерное уменьшение: клетки **x%.2f**, рука **x%.2f** (контракт: не больше 3 %%)." % (
                  r["grid_need_scale"], r["hand_need_scale"]),
              "- Сдвиг без уменьшения: %s." % (
                  "клетки %s, рука %s базовых пикселей" % (r["grid_shift"], r["hand_shift"])
                  if r["grid_shift"] or r["hand_shift"] else "невозможен - габарит больше допуска")]
        if r["muzzle"]:
            L.append("- Стреляющее: кандидат дульного среза - верхняя строка силуэта x %d..%d, y %d (подтвердить по "
                     "листу); любой перенос двигает его." % tuple(r["muzzle"]))
        if r["primer_box"]:
            L.append("- Защищённая область: значок взвода 4x4 в левом верхнем углу кадра (x 0..4, y 0..4).")
        L += ["- Варианты (не выбраны): (а) разрешить HD этого предмета выходить за клетки так же, как классика, "
              "по силуэту оригинала; (б) уменьшение сверх 3 % - контракт запрещает без решения; (в) перенос - "
              "только явным решением, у стреляющего двигает дуло; (г) другая клетка, ракурс или конструкция - "
              "меняет предмет."]
    with open(path, "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")


def write(path, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, keys, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, tuple, dict)) else v
                        for k, v in r.items()})


def sheet(tiles, rec, path):
    """Оригинал x4 | HD | наложение контура оригинала x4 на HD, с допуском клеток (красный), допуском руки
    в координатах файла (оранжевый), значком взвода (жёлтый), дулом (голубой)."""
    W, H, G, T = iac.HAND_W * K, iac.HAND_H * K, 10, 330
    f = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 14)
    fb = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 15)
    im = Image.new("RGB", (G + 3 * (W + G) + T, 26 + len(tiles) * (H + G)), (40, 40, 48))
    d = ImageDraw.Draw(im)
    for i, c in enumerate(("оригинал x4", "HD как есть", "HD + контур оригинала")):
        d.text((G + i * (W + G), 5), c, font=f, fill=(220, 220, 220))
    d.text((G + 3 * (W + G), 5), "замер", font=f, fill=(220, 220, 220))
    for n, (row, rgba, hd) in enumerate(tiles):
        y = 26 + n * (H + G)
        o = Image.fromarray(rgba, "RGBA").resize((W, H), Image.NEAREST)
        a4 = np.asarray(o)[..., 3] > 0
        edge = a4 & ~(np.roll(a4, 1, 0) & np.roll(a4, -1, 0) & np.roll(a4, 1, 1) & np.roll(a4, -1, 1))
        for i in range(3):
            bg = Image.new("RGBA", (W, H), (16, 18, 26, 255))
            if i == 0:
                bg.alpha_composite(o)
            elif hd is not None:
                bg.alpha_composite(Image.fromarray(hd, "RGBA"))
            if i == 2:
                arr = np.array(bg)
                arr[edge] = (255, 0, 255, 255)
                bg = Image.fromarray(arr, "RGBA")
            g = ImageDraw.Draw(bg)
            x0, y0, x1, y1 = (v * K for v in row["grid_rect"])
            g.rectangle([x0, y0, x1 - 1, y1 - 1], outline=(220, 60, 60))
            dx, dy = (v * K for v in row["hand_shift_engine"])
            hx0, hy0, hx1, hy1 = (v * K for v in row["hand_rect"])
            g.rectangle([hx0 - dx, hy0 - dy, hx1 - dx - 1, hy1 - dy - 1], outline=(240, 150, 40))
            if row["primer_box"]:
                g.rectangle([0, 0, PRIMER * K - 1, PRIMER * K - 1], outline=(250, 230, 60))
            if row["muzzle"]:
                mx0, my, mx1 = row["muzzle"]
                g.line([(mx0 * K, my * K), (mx1 * K, my * K)], fill=(80, 220, 255), width=3)
            im.paste(bg.convert("RGB"), (G + i * (W + G), y))
        tx = G + 3 * (W + G)
        d.text((tx, y), "%s %s %s" % (row["master"], row["type"], row["cells"]), font=fb, fill=(230, 230, 230))
        col = {"OK": (110, 200, 110), "SHIFT_DECISION": (230, 190, 80)}.get(row["status"], (230, 90, 80))
        d.text((tx, y + 20), row["status"], font=fb, fill=col)
        lines = ["оригинал %dx%d баз. пикс" % (row["w0"], row["h0"]),
                 "клетки: нужно x%.2f%s" % (row["grid_need_scale"],
                                             " или сдвиг %s" % (row["grid_shift"],) if row["grid_shift"] and
                                             row["grid_need_scale"] >= 1 and row["grid_out"] else ""),
                 "рука: нужно x%.2f" % row["hand_need_scale"]]
        r = rec.get(row["master"])
        if r:
            lines += ["HD %dx%d при нужных %dx%d" % (r["hd_w"], r["hd_h"], r["want_w"], r["want_h"]),
                      "пилот: " + r["geometry"]]
            lines += [s for s in r["why"].split("; ") if s]
        yy = y + 42
        for s in lines:
            d.text((tx, yy), s, font=f, fill=(200, 200, 205))
            yy += 17
    im.save(path)


if __name__ == "__main__":
    main()
