#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000514: сухое деревце FOREST:8 и копии - ствол без перелома, край ровный, без видеокарты.

Брак: FOREST:8, FORESTJUNGLESTYX:8, FLORASET:24, IDT_ASIA:57, JUNGLE:57 (последние три - один файл побайтно).
Ряды 98-107 залиты травой поперёк ствола (ground_seam --other 07.10 принял кадр с деревом за плоский пол, R-433),
выше ромба края - лесенка x4 (FOREST:8). Не трогаем: FOREST_WASTE:8, FORESTRED:8, NEOJUNGLE:57.

Сборка (всё кодом, без модели):
  дерево А (выбор Vitali): ствол и крона от FOREST_WASTE:8 (tree_render), перекрашены под тон дерева классики
     (средний цвет и разброс яркости индексов дерева классики 10..13, 93..95); в ромбе ствол вырезан по цвету
     (серо-фиолетовое против красноватой золы), мягкий край.
  дерево Б (запасное, по итогам сверки силуэта): крона - гладкая крона FORESTJUNGLESTYX:8 (она по маске классики),
     ствол в ромбе - тот же ствол FOREST_WASTE:8, сдвинут по x под ствол кроны, стык кроссфейдом.
  дерево В (запрос командира): дерево целиком, с корнями и тёмным пятном, от NEOJUNGLE:57 (крона гладкая по маске
     классики, IoU 0.92, лесенки нет); в ромбе ствол и корни вырезаны по цвету (R-G мал), цвет - в тон дерева
     классики зелёных наборов (оттенок классики, свет и тень от кадра, красная кайма почвы убрана);
     тёмное пятно почвы под деревом - множителем на пол набора.
  пол: свой текущий кадр набора, корни прежнего дерева убраны (цвет корней: не мох) и закрыты мхом кадра FOREST:0.
  альфа ромба: ровный край пола FOREST:0 (одна полупрозрачная точка на ряд, как у остальных кадров набора).

    py -3.13 forest_tree_fix.py            # заготовки: art/tickets/forest_tree/<НАБОР>/<кадр>.png (А),
                                           #            art/tickets/forest_tree_b/<НАБОР>/<кадр>.png (Б)
    py -3.13 forest_tree_fix.py --sheet    # лист census/tickets/XP-000514/sheet_new.png
    py -3.13 forest_tree_fix.py --yes [--variant a|b|c]   # в обе копии мода через манифест (только по слову Vitali,
                                                       # под очередью правок)
"""
import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import hb_common as hc                  # noqa: E402,F401  (chdir в корень репозитория)
import numpy as np                      # noqa: E402
import cv2                              # noqa: E402
from PIL import Image                   # noqa: E402

import build_hd_pack as bp              # noqa: E402
import water_build as wb                # noqa: E402

K = 4
OUT_A = os.path.join("art", "tickets", "forest_tree")
OUT_B = os.path.join("art", "tickets", "forest_tree_b")
OUT_C = os.path.join("art", "tickets", "forest_tree_c")
SHEET2 = os.path.join("census", "tickets", "XP-000514", "sheet_new2.png")
SHEET = os.path.join("census", "tickets", "XP-000514", "sheet_new.png")
TERR = hc.TERRAIN
WORD = "XP-000514, сухое деревце FOREST:8 и копии: ствол и крона FOREST_WASTE:8, перекрас, пол набора (Vitali, вариант по листу)"
# набор, кадр, образец пола-копии (None - своя сборка); IDT_ASIA:57 и JUNGLE:57 - побайтные копии FLORASET:24
FRAMES = [("FOREST", 8), ("FORESTJUNGLESTYX", 8), ("FLORASET", 24), ("IDT_ASIA", 57), ("JUNGLE", 57)]
COPIES = {("IDT_ASIA", 57): ("FLORASET", 24), ("JUNGLE", 57): ("FLORASET", 24)}
UNTOUCHED = [("FOREST_WASTE", 8), ("FORESTRED", 8), ("NEOJUNGLE", 57)]
TREE_IDX = (10, 11, 12, 13, 93, 94, 95)       # индексы дерева классики (серое и бордовое)
LUMA = np.array([0.299, 0.587, 0.114], np.float32)
JOIN = 94                                      # дерево Б: выше - крона набора, ниже - ствол WASTE
SHADE_MIN = 0.55                               # дерево В: самое тёмное пятно под деревом - не ниже x0.55 пола
PATCH_GAIN = 1.6                               # дерево В: пятно мха по классике - усиление и глубина
PATCH_DARK = 0.55
TRUNK_SQUEEZE = 0.6                            # дерево Б: ствол WASTE сужен по x
YV = 98                                        # верх ромба клетки x4 (центр 130, полуось 32)


def load(s, f):
    return np.asarray(Image.open(os.path.join(TERR, s + ".PCK", "%d.png" % f)).convert("RGBA")).astype(np.float32)


def lum(c):
    return c[..., :3] @ LUMA


def gb(a, sg):
    return cv2.GaussianBlur(a.astype(np.float32), (0, 0), sg)


DCX, DCY, DHX, DHY = 64.0, 132.0, 64.0, 32.0      # ромб клетки как у FOREST:0 (МНК по его покрытию): верх на ряду 100, середина 132, наклон 1:2


def floor_alpha(ss=8):
    """Ровный край пола: точное покрытие ромба (сетка ss x ss на пиксель). У FOREST:0 край - одна полупрозрачная
    точка на ряд (шаг в пиксель, 0/133/255); покрытие даёт плавный наклон, положение края то же."""
    y = (np.arange(160 * ss, dtype=np.float64) + 0.5) / ss
    x = (np.arange(128 * ss, dtype=np.float64) + 0.5) / ss
    d = np.abs(x[None, :] - DCX) / DHX + np.abs(y[:, None] - DCY) / DHY
    m = (d <= 1.0).astype(np.float32)
    c = m.reshape(160, ss, 128, ss).mean((1, 3))
    # боковые вершины: у FOREST:0 ряды 128..132 непрозрачны во всю ширину (перехлёст вершин, R-291) - так и здесь
    f0 = load("FOREST", 0)[..., 3] / 255.0
    c[128:133] = np.maximum(c[128:133], f0[128:133])
    return c


def classic_tree_stats(s, f):
    """Средний цвет и разброс яркости дерева классики: индексы 10..13, 93..95 по всему кадру."""
    a = wb.read_set(s)[f]
    m = np.isin(a, TREE_IDX)
    pal = np.asarray(wb.palette())[..., :3].astype(np.float32)
    c = pal[a[m]]
    return c.mean(0), float(lum(c).std()), int(m.sum())


def waste_matte(w):
    """Ствол FOREST_WASTE:8 в ромбе: серо-фиолетовое против красноватой золы (R-G мал, темно), компонента со
    стволом, мягкий край. Выше ромба (ряды < YV-1) ствол и крона - по альфе кадра."""
    rgb = w[..., :3]
    rg = gb(rgb[..., 0] - rgb[..., 1], 1.2)
    lb = gb(lum(w), 1.2)
    m = ((rg < 11) & (lb < 50) & (w[..., 3] > 128)).astype(np.uint8)
    m[:YV - 2] = 0
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    seed = lab[112, 66]
    if seed <= 0:
        raise SystemExit("ствол WASTE:8 в ромбе не найден")
    mm = (lab == seed).astype(np.float32)
    mm = cv2.morphologyEx(mm, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return np.clip((gb(mm, 1.4) - 0.25) / 0.5, 0, 1)


def trunk_cx(alpha, y, x0=48, x1=96):
    """Середина ствола кадра на ряду y: центр самого широкого куска альфы около оси клетки."""
    xs = np.where(alpha[y, x0:x1] > 0.5)[0]
    return float(xs.mean() + x0) if len(xs) else 66.0


def shift_x(a, dx):
    """Сдвиг по x на целое число пикселей (края - прозрачные)."""
    out = np.zeros_like(a)
    if dx >= 0:
        out[:, dx:] = a[:, :a.shape[1] - dx]
    else:
        out[:, :dx] = a[:, -dx:]
    return out


def tree_layer(variant, s_cur_crown):
    """Дерево: RGB (160,128,3) и альфа (160,128) до перекраса."""
    w = load("FOREST_WASTE", 8)
    M = waste_matte(w)
    wa = w[..., 3] / 255.0
    yy = np.arange(160, dtype=np.float32)[:, None] * np.ones((1, 128), np.float32)
    if variant == "a":
        t = np.clip((yy - (YV + 1)) / 3.0, 0, 1)
        al = wa * (1 - t) + np.minimum(wa, M) * t
        return w[..., :3], al
    # Б: крона набора выше JOIN, ствол WASTE ниже: сужен по x (толщина ствола классики - 2 пикселя базы) и сдвинут
    # под ось ствола кроны; выше ромба берётся только полоса ствола (без веток WASTE)
    cr = s_cur_crown
    ca = cr[..., 3] / 255.0
    cxc = trunk_cx(ca, YV - 1, 56, 80)
    cxw = trunk_cx(M, YV + 5, 40, 100)
    A = np.float32([[TRUNK_SQUEEZE, 0, cxc - TRUNK_SQUEEZE * cxw], [0, 1, 0]])
    pm = np.dstack([w[..., :3] * wa[..., None], wa, M]).astype(np.float32)
    pw = cv2.warpAffine(pm, A, (128, 160), flags=cv2.INTER_LINEAR, borderValue=0)
    wa2 = pw[..., 3]
    M2 = pw[..., 4]
    w2 = pw[..., :3] / np.maximum(wa2, 1e-3)[..., None]
    xx = np.arange(128, dtype=np.float32)[None, :] * np.ones((160, 1), np.float32)
    band = np.clip(1.0 - (np.abs(xx - cxc) - 6.0) / 2.0, 0, 1)
    t = np.clip((yy - (YV + 1)) / 3.0, 0, 1)
    wal = wa2 * (1 - t) * band + np.minimum(wa2, M2) * t
    c = np.clip((yy - (JOIN - 3)) / 6.0, 0, 1)          # 0 - крона набора, 1 - ствол WASTE
    al = ca * (1 - c) + wal * c
    rgb = cr[..., :3] * (1 - c[..., None]) + w2 * c[..., None]
    return rgb, al


def recolor(rgb, al, target_mean, target_std):
    """Тон дерева - под классику: средний цвет и разброс яркости (разброс - не выше x1.5 и не ниже x0.7)."""
    m = al > 0.6
    mu = rgb[m].mean(0)
    sd = float(lum(rgb[m]).std())
    g = float(np.clip(target_std / max(sd, 1e-3), 0.7, 1.5))
    return np.clip(target_mean + (rgb - mu) * g, 0, 255)


def clean_floor(cur):
    """Пол набора без корней прежнего дерева: не мох (G не выше R/B больше чем на 6) и темнее 60 - маска,
    закрыта мхом кадра FOREST:0 (его мелкая фактура) на низких частотах пола вокруг."""
    rgb = cur[..., :3]
    gr = rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2])
    l = lum(cur)
    inside = cur[..., 3] > 128
    yy = np.arange(160)[:, None] * np.ones((1, 128))
    m = ((gr < 6) & (l < 60) & inside & (yy >= YV)).astype(np.uint8)
    m = cv2.dilate(m, np.ones((5, 5), np.uint8))
    m = (m > 0) & inside & (yy >= YV)
    keep = (~m) & inside
    # низкие частоты: нормированное размытие по сохранённым пикселям
    low = np.zeros(rgb.shape, np.float32)
    done = np.zeros(rgb.shape[:2], bool)
    for sg in (3.0, 8.0, 20.0):          # меньший радиус, где хватает пикселей вокруг, иначе больший
        wgt = gb(keep.astype(np.float32), sg)
        lo = np.dstack([gb(rgb[..., i] * keep, sg) for i in range(3)]) / np.maximum(wgt, 1e-3)[..., None]
        ok = (wgt > 0.3) & ~done
        low[ok] = lo[ok]
        done |= ok
    low[~done] = lo[~done]
    g0 = load("FOREST", 0)[..., :3]
    g0l = np.dstack([gb(g0[..., i], 6.0) for i in range(3)])
    fill = low + (g0 - g0l)
    mf = np.clip(gb(m.astype(np.float32), 2.0) * 1.5, 0, 1)[..., None]
    out = rgb * (1 - mf) + fill * mf
    return out, m


def compose(tree_rgb, tree_al, floor_rgb, fa):
    at = np.clip(tree_al, 0, 1)
    a = at + fa * (1 - at)
    p = tree_rgb * at[..., None] + floor_rgb * (fa * (1 - at))[..., None]
    rgb = p / np.maximum(a, 1e-4)[..., None]
    return np.dstack([np.clip(rgb, 0, 255), np.clip(a, 0, 1) * 255]).round().astype(np.uint8)


def drop_specks(al, min_area=40):
    """Одиночные точки отдельно от дерева (мусор генерации, меньше min_area пикселей x4) - убрать из альфы."""
    m = (al > 0.08).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, 4] >= min_area
    return al * keep[lab]


def nblur(vals, w, sigmas=(3.0, 8.0, 20.0), thr=0.3):
    """Нормированное размытие vals по весам w; меньший радиус, где хватает весов, иначе больший."""
    out = np.zeros(vals.shape, np.float32)
    done = np.zeros(vals.shape[:2], bool)
    last = None
    for sg in sigmas:
        ww = gb(w, sg)
        if vals.ndim == 3:
            lo = np.dstack([gb(vals[..., i] * w, sg) for i in range(vals.shape[2])]) / np.maximum(ww, 1e-3)[..., None]
        else:
            lo = gb(vals * w, sg) / np.maximum(ww, 1e-3)
        ok = (ww > thr) & ~done
        out[ok] = lo[ok]
        done |= ok
        last = lo
    out[~done] = last[~done]
    return out


def neo_tree():
    """Дерево В: NEOJUNGLE:57. -> RGB, альфа дерева (выше ромба по альфе кадра, в ромбе - по цвету: ствол и корни
    серо-фиолетовые, почва красноватая), множитель тёмного пятна почвы под деревом."""
    n = load("NEOJUNGLE", 57)
    rgb = n[..., :3]
    na = n[..., 3] / 255.0
    yy = np.arange(160, dtype=np.float32)[:, None] * np.ones((1, 128), np.float32)
    xx = np.arange(128, dtype=np.float32)[None, :] * np.ones((160, 1), np.float32)
    rg = gb(rgb[..., 0] - rgb[..., 1], 0.8)
    m = np.clip((30.0 - rg) / 16.0, 0, 1)
    d = np.abs(xx + 0.5 - DCX) / DHX + np.abs(yy + 0.5 - DCY) / DHY
    inner = ((d <= 0.93) | (np.abs(xx - 66.0) <= 12.0)).astype(np.float32)             # кайма ромба почвы (тёмный контур ступеней) - не дерево
    # у шеи ствола (полоса +-12 от оси, ряды 95..98) тоже по цвету: верх ромба почвы (светлая ступень) - не ствол
    t = np.where(np.abs(xx - 66.0) <= 12.0, np.clip((yy - (YV - 3)) / 3.0, 0, 1), np.clip((yy - (YV + 2)) / 3.0, 0, 1))
    al = na * (1 - t) + na * gb(m, 0.7) * inner * t
    al = drop_specks(al, 25)
    # тёмное пятно: низкие частоты яркости почвы вне дерева, к типичной яркости почвы
    soil = ((al < 0.05) & (na > 0.98) & (d <= 0.93) & (yy >= YV + 2)).astype(np.float32)
    ll = nblur(lum(n)[..., None] * np.ones((1, 1, 1), np.float32), soil)[..., 0]
    ref = float(np.percentile(ll[soil > 0.5], 50))
    shade = np.clip(ll / ref, SHADE_MIN, 1.0)
    shade = np.where(yy >= YV, shade, 1.0)
    return rgb, al, shade


def recolor_c(rgb, al, target_mean, target_std):
    """Тон дерева В: оттенок - классики (серо-фиолетовый), свет и тень - от кадра; кайма с цветом почвы убрана
    (яркость краевых точек не выше яркости ближнего нутра)."""
    l = lum(rgb)
    solid = (al > 0.97).astype(np.float32)
    l_in = nblur(l[..., None], solid, (2.0, 4.0, 8.0), 0.2)[..., 0]
    l = np.where(al < 0.97, np.minimum(l, l_in), l)
    m = al > 0.6
    mu, sd = float(l[m].mean()), float(l[m].std())
    g = float(np.clip(target_std / max(sd, 1e-3), 0.7, 1.5))
    dirv = target_mean / max(float(lum(target_mean[None, None, :])[0, 0]), 1.0)
    return np.clip(target_mean + (l - mu)[..., None] * g * dirv, 0, 255)


def classic_patch(s, f):
    """Тёмное пятно мха под деревом по классике кадра: доля тёмного пола (яркость ниже 75-го перцентиля пола кадра),
    пиксели дерева - по соседям; мягко x4 (гаусс 5 пикселей x4). -> (160,128) 0..1."""
    a = wb.read_set(s)[f]
    pal = np.asarray(wb.palette())[..., :3].astype(np.float32)
    l = lum(pal[a])
    floor = (a != 0) & ~np.isin(a, TREE_IDX)
    floor[:24] = False
    ref = float(np.percentile(l[floor], 75))
    w0 = np.clip((ref - l) / ref, 0, 1) * floor
    wf = nblur(w0[..., None].astype(np.float32), floor.astype(np.float32), (1.5, 3.0, 6.0), 0.3)[..., 0]
    up = np.asarray(Image.fromarray(wf.astype(np.float32), "F").resize((128, 160), Image.BICUBIC))
    return np.clip(gb(up, 5.0) * PATCH_GAIN, 0, 1)


def build_frame_c(s, f):
    cur = load(s, f)
    floor_rgb, _m = clean_floor(cur)
    trgb, tal, shade = neo_tree()
    mean, std, _n = classic_tree_stats(s, f)
    trgb = recolor_c(trgb, tal, mean, std)
    patch = classic_patch(s, f)
    k = np.minimum(shade, 1.0 - PATCH_DARK * patch)
    return compose(trgb, tal, floor_rgb * k[..., None], floor_alpha())


def build_frame(s, f, variant):
    if variant == "c":
        return build_frame_c(s, f)
    cur = load(s, f)
    floor_rgb, _m = clean_floor(cur)
    fa = floor_alpha()
    crown = load("FORESTJUNGLESTYX", 8)
    trgb, tal = tree_layer(variant, crown)
    tal = drop_specks(tal)
    mean, std, _n = classic_tree_stats(s, f)
    trgb = recolor(trgb, tal, mean, std)
    return compose(trgb, tal, floor_rgb, fa)


def metrics(img):
    """Числа по альфе: жёсткие шаги (соседи >=240 и <=15) на кромке выше ромба и по ромбу, полупрозрачные точки."""
    a = img[..., 3].astype(np.int32)
    yy = np.arange(160)[:, None] * np.ones((1, 128), int)
    cross = np.zeros(a.shape, bool)
    hard = np.zeros(a.shape, bool)
    for ax in (0, 1):
        for sh in (1, -1):
            b = np.roll(a, sh, ax)
            cross |= ((a >= 128) & (b < 128))
            hard |= ((a >= 240) & (b <= 15))
    up = yy < YV
    return dict(
        cross_up=int((cross & up).sum()), hard_up=int((hard & up).sum()),
        cross_dm=int((cross & ~up).sum()), hard_dm=int((hard & ~up).sum()),
        partial=int(((a > 15) & (a < 240)).sum()))


def classic_top_iou(s, f, img):
    cm = np.kron((wb.read_set(s)[f] > 0).astype(np.uint8), np.ones((K, K), np.uint8)) > 0
    hm = img[..., 3] >= 128
    up = np.zeros_like(cm)
    up[:YV] = True
    return float((hm & cm & up).sum()) / max(int(((hm | cm) & up).sum()), 1)


def hole(im):
    """Ряды 98-107 на оси ствола (x 64..71): ряд - ствол, если там непрозрачно и цвет не травяной (G не выше
    R и B больше чем на 8). Ряд с травой или прозрачностью поперёк ствола - перелом."""
    a = im[YV:108, 64:72].astype(np.float32)
    gr = a[..., 1] - np.maximum(a[..., 0], a[..., 2])
    bad = int((((a[..., 3] < 200).mean(1) > 0.5) | (((gr > 8) & (a[..., 3] >= 200)).mean(1) > 0.5)).sum())
    return "ствол сплошной (рядов с травой или прозрачностью 0 из 10)" if bad == 0 else "ПЕРЕЛОМ: %d из 10 рядов" % bad


def edge_dev(img):
    """Отклонение края ромба от прямой, пикселей x4: край в ряду - по покрытию (сумма альфы в окне слева x 0..48
    и справа x 80..128), прямая по МНК отдельно для четырёх сторон (ряды 110..125 и 135..151), максимум |остаток|."""
    a = img[..., 3].astype(np.float64) / 255.0
    ys = np.r_[110:126, 135:152]          # без полосы боковых вершин 126..134
    left = 48.0 - a[ys, :48].sum(1)
    right = 80.0 + a[ys, 80:].sum(1)
    out = []
    for e in (left, right):
        for sel in (ys < 130, ys >= 130):
            yy, ee = ys[sel].astype(np.float64), e[sel]
            k = np.polyfit(yy, ee, 1)
            out.append(float(np.abs(ee - np.polyval(k, yy)).max()))
    return out


def make():
    out = {}
    for variant, root in (("a", OUT_A), ("b", OUT_B), ("c", OUT_C)):
        built = {}
        for s, f in FRAMES:
            src = COPIES.get((s, f))
            if src:
                im = built[src]                       # побайтная копия
            else:
                im = build_frame(s, f, variant)
            built[(s, f)] = im
            p = os.path.join(root, s, "%d.png" % f)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            Image.fromarray(im, "RGBA").save(p)
            out[(variant, s, f)] = p
    return out


def report(paths):
    pal = np.asarray(wb.palette())[..., :3].astype(np.float32)
    for variant in ("a", "b", "c"):
        for s, f in FRAMES:
            p = paths[(variant, s, f)]
            im = np.asarray(Image.open(p).convert("RGBA"))
            mt = metrics(im)
            a = wb.read_set(s)[f]
            mean, std, n = classic_tree_stats(s, f)
            # цвет дерева в новом кадре: пиксели, где классика - дерево (выше ромба)
            cm = im[..., 3] > 200
            cm[YV:] = False
            col = im[cm][..., :3].mean(0)
            # цвет пола вне ствола: ромб ниже ряда 110, правая и левая части
            nz = a != 0
            floor_idx = nz & ~np.isin(a, TREE_IDX)
            fm = np.kron(floor_idx.astype(np.uint8), np.ones((K, K), np.uint8)) > 0
            fm[:YV + 6] = False
            fm &= (im[..., 3] > 250)
            fm[:, 40:90] = False
            fcol = im[fm][..., :3].mean(0)
            fcls = pal[a[floor_idx]].mean(0)
            cur = load(s, f)
            fm2 = fm & (cur[..., 3] > 250)
            curfl = cur[fm2][..., :3].mean(0)
            print("%s %s:%d: IoU верха с классикой x4 %.2f; жёстких шагов выше ромба %d из %d, по ромбу %d из %d; полупрозрачных %d; "
                  "край ромба: отклонение от прямой %s px; ряды 98-107: %s; дерево выше ромба RGB %s (классика %s); пол по краям RGB %s (классика %s, сейчас %s)"
                  % (variant.upper(), s, f, classic_top_iou(s, f, im), mt["hard_up"], mt["cross_up"], mt["hard_dm"], mt["cross_dm"],
                     mt["partial"], np.round(edge_dev(im), 2).tolist(), hole(im),
                     np.round(col, 1).tolist(), np.round(mean, 1).tolist(), np.round(fcol, 1).tolist(), np.round(fcls, 1).tolist(),
                     np.round(curfl, 1).tolist()))
    # побайтное равенство тройки
    h = {k: hashlib.sha1(open(paths[("a",) + k], "rb").read()).hexdigest()[:10] for k in FRAMES}
    print("sha А:", h)
    print("тройка FLORASET:24 = IDT_ASIA:57 = JUNGLE:57 побайтно:", len({h[("FLORASET", 24)], h[("IDT_ASIA", 57)], h[("JUNGLE", 57)]}) == 1)
    # прежние числа тех же метрик
    for s, f in FRAMES + UNTOUCHED:
        im = load(s, f).astype(np.uint8)
        mt = metrics(im)
        print("сейчас %s:%d: IoU %.2f, жёстких шагов выше ромба %d из %d, по ромбу %d из %d, край отклонение %s px, ряды 98-107: %s"
              % (s, f, classic_top_iou(s, f, im), mt["hard_up"], mt["cross_up"], mt["hard_dm"], mt["cross_dm"],
                 np.round(edge_dev(im), 2).tolist(), hole(im)))


# ---------------------------------------------------------------- лист
PW, PH = 400, 400          # панель: картинка
SW, SH = 200, 250          # малая панель (картинка 200 x 200 + подпись)
BGN = (60, 60, 70)
KS = 6                     # масштаб сцены на листе (кадр x6, окно 66 x 66 клеточных пикселей)


def fit(im, w, h, bg=BGN):
    out = Image.new("RGB", (w, h), bg)
    out.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return out


def sprite_panel(img, w, h, scale):
    """Кадр 128x160 x scale на нейтральном фоне; рамка: ряды 32..160 (дерево и ромб)."""
    im = img.convert("RGBA").crop((0, 32, 128, 160))
    im = im.resize((int(128 * scale), int(128 * scale)), Image.NEAREST if getattr(img, "_nearest", False) else Image.LANCZOS)
    return fit(hc.on_bg(im), w, h)


def classic_img(sc, s, f):
    im = sc.classic(s, f)
    im._nearest = True
    return im


def sheet(paths):
    import ticket_scene as ts
    sc = ts.Scene()
    keyset = ("FOREST", 8)
    pan = {}                                     # (строка, колонка) -> (координаты, PIL)
    titles = ["оригинал (классика x4)", "сейчас", "новое А: ствол и крона WASTE", "новое Б: крона по классике"]
    # --- ряд 1: один кадр FOREST:8 крупно
    cur = sc.hd("FOREST", 8)
    A = Image.open(paths[("a", "FOREST", 8)]).convert("RGBA")
    B = Image.open(paths[("b", "FOREST", 8)]).convert("RGBA")
    cls = sc.classic("FOREST", 8)
    imgs = [sprite_panel(cls, PW, PH, 3.0), sprite_panel(cur, PW, PH, 3.0), sprite_panel(A, PW, PH, 3.0), sprite_panel(B, PW, PH, 3.0)]
    row1 = [hc.title_bar(im, "FOREST:8  " + t, 17) for im, t in zip(imgs, titles)]
    # --- ряд 2: сцена на блоке карты
    tb = hc.best_blocks(sc, [keyset], None)
    (t, b), n = tb[0]
    found = ts.find_cells(sc, t, b, [keyset])
    zmin = min(x[3] for x in found)
    found = sorted([x for x in found if x[3] == zmin], key=lambda x: (x[4][0], x[4][1]))
    pick = found[min(1, len(found) - 1)]
    box = ts.window([(pick[0], pick[1], tuple(v * KS for v in pick[2]))], PW / KS, PH / KS, KS)
    ov_a = {("FOREST", 8): A}
    ov_b = {("FOREST", 8): B}
    row2 = []
    for title, mode, o in zip(titles, ("classic", "hd", "hd", "hd"), (None, None, ov_a, ov_b)):
        im, _f = sc.render(t, b, mode, override=o, k=KS, maxz=zmin)
        row2.append(hc.title_bar(ts.crop_pad(im, box), "сцена %s, блок %s  %s" % (t, b, title), 17))
    # --- ряды 3-6: все наборы семьи, малые панели
    fam = FRAMES[:3] + [FRAMES[3], FRAMES[4]] + UNTOUCHED
    rows = []
    for label, kind in (("классика", "c"), ("сейчас", "n"), ("новое А", "a"), ("новое Б", "b")):
        r = []
        for s, f in fam:
            if kind == "c":
                im = classic_img(sc, s, f)
            elif kind == "n":
                im = sc.hd(s, f)
            else:
                if (s, f) in UNTOUCHED:
                    im = sc.hd(s, f)
                else:
                    im = Image.open(paths[(kind, s, f)]).convert("RGBA")
            tt = "%s:%d %s" % (s, f, label if kind in "cn" else label + (" (не трогаем)" if (s, f) in UNTOUCHED else ""))
            r.append(hc.title_bar(sprite_panel(im, SW, SH - 40, 1.5), tt, 11))
        rows.append(r)
    # --- сборка ровной сеткой, с координатами
    G = 10
    W = max(4 * (PW + G) + G, 8 * (SW + G) + G)
    out = Image.new("RGB", (W, 20), (12, 12, 14))
    y = G
    coords = {}
    layout = []
    for name, r, cw in (("основной ряд кадр", row1, PW), ("основной ряд сцена", row2, PW)):
        layout.append((name, r, cw))
    for i, r in enumerate(rows):
        layout.append(("малые ряд %d" % (i + 1), r, SW))
    total_h = G + sum(max(p.height for p in r) + G for _n, r, _w in layout)
    out = Image.new("RGB", (W, total_h), (12, 12, 14))
    for name, r, cw in layout:
        x = G
        for j, p in enumerate(r):
            out.paste(p, (x, y))
            coords[(name, j)] = (x, y, x + p.width, y + p.height)
            x += p.width + G
        y += max(p.height for p in r) + G
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    out.save(SHEET)
    print("лист:", SHEET, out.size)
    for (name, j), c in coords.items():
        print("  %s, колонка %d: x %d..%d, y %d..%d" % (name, j + 1, c[0], c[2], c[1], c[3]))


def sheet2(paths):
    """Лист 2: оригинал | сейчас | А | Б | В - кадр FOREST:8 крупно и сцена на лесном блоке (FOREST / CIVFOREST00), потом
    малые ряды по пяти наборам (классика, сейчас, В)."""
    import ticket_scene as ts
    sc = ts.Scene()
    titles = ["оригинал (классика x4)", "сейчас", "новое А (WASTE)", "новое Б (крона + WASTE)", "новое В (NEOJUNGLE:57)"]
    ims = {k: Image.open(paths[(k, "FOREST", 8)]).convert("RGBA") for k in ("a", "b", "c")}
    seq = [classic_img(sc, "FOREST", 8), sc.hd("FOREST", 8), ims["a"], ims["b"], ims["c"]]
    row1 = [hc.title_bar(sprite_panel(im, PW, PH, 3.0), "FOREST:8  " + t, 17) for im, t in zip(seq, titles)]
    terr, block = "FOREST", "CIVFOREST00"
    found = ts.find_cells(sc, terr, block, [("FOREST", 8)])
    zmin = min(x[3] for x in found)
    pick = sorted([x for x in found if x[3] == zmin], key=lambda x: (x[4][0], x[4][1]))[0]
    box = ts.window([(pick[0], pick[1], tuple(v * KS for v in pick[2]))], PW / KS, PH / KS, KS)
    row2 = []
    for t, mode, o in zip(titles, ("classic", "hd", "hd", "hd", "hd"),
                          (None, None, {("FOREST", 8): ims["a"]}, {("FOREST", 8): ims["b"]}, {("FOREST", 8): ims["c"]})):
        im, _f = sc.render(terr, block, mode, override=o, k=KS, maxz=zmin)
        row2.append(hc.title_bar(ts.crop_pad(im, box), "%s %s" % (block, t), 17))
    rows = []
    for label, kind in (("классика", "cls"), ("сейчас", "now"), ("новое В", "c")):
        r = []
        for s_, f_ in FRAMES:
            if kind == "cls":
                im = classic_img(sc, s_, f_)
            elif kind == "now":
                im = sc.hd(s_, f_)
            else:
                im = Image.open(paths[("c", s_, f_)]).convert("RGBA")
            r.append(hc.title_bar(sprite_panel(im, SW, SH - 40, 1.5), "%s:%d %s" % (s_, f_, label), 11))
        rows.append(r)
    G = 10
    layout = [("основной ряд кадр", row1), ("основной ряд сцена", row2)] + [("малые ряд %d" % (i + 1), r) for i, r in enumerate(rows)]
    W = 5 * (PW + G) + G
    H = G + sum(max(p.height for p in r) + G for _n, r in layout)
    out = Image.new("RGB", (W, H), (12, 12, 14))
    y = G
    coords = []
    for name, r in layout:
        x = G
        for j, pn in enumerate(r):
            out.paste(pn, (x, y))
            coords.append("  %s, колонка %d: x %d..%d, y %d..%d" % (name, j + 1, x, x + pn.width, y, y + pn.height))
            x += pn.width + G
        y += max(p.height for p in r) + G
    os.makedirs(os.path.dirname(SHEET2), exist_ok=True)
    out.save(SHEET2)
    print("лист 2:", SHEET2, out.size)
    print("\n".join(coords))


def install(paths, variant):
    if variant != "c":
        raise SystemExit("Vitali выбрал вариант В (страница 05.11): --variant c")
    word = "XP-000514, сухое деревце FOREST:8 и копии: дерево с корнями NEOJUNGLE:57, пол набора (Vitali, страница 05.11: вариант В)"
    man = bp.load()
    rels = []
    for s, f in FRAMES:
        rel = "TERRAIN/%s.PCK/%d.png" % (s, f)
        path = paths[(variant, s, f)]
        bp.stage(man, rel, path, generator="forest_tree_fix",
                 generator_version="forest_tree_fix 05.11: вариант В, дерево с корнями NEOJUNGLE:57, тёмное пятно классики, пол набора, ровный край",
                 source_path=path.replace(os.sep, "/"), approved=True, approval=word)
        rels.append(rel)
    bp.save(man, why="FOREST:8 и копии: сухое деревце без перелома (%s)" % word)
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for root in bp.TARGETS.values():
        for rel in rels:
            with open(os.path.join(root, rel), "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != man["files"][rel]["sha256"]:
                    raise SystemExit("РАСХОДИТСЯ %s %s" % (root, rel))
    print("сверено: обе копии, файлов", len(rels))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    paths = make()
    print("заготовки:", OUT_A, OUT_B, OUT_C)
    report(paths)
    if "--sheet" in sys.argv:
        sheet(paths)
    if "--sheet2" in sys.argv:
        sheet2(paths)
    if "--yes" in sys.argv:
        v = sys.argv[sys.argv.index("--variant") + 1].lower() if "--variant" in sys.argv else "a"
        if v not in ("a", "b", "c"):
            raise SystemExit("--variant a|b|c")
        install(paths, v)
