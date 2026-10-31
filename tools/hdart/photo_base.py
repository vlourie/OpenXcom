#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""PHOTO-база (01.10): фото-рендер на нейтральной подложке -> проверка геометрии -> управляемая альфа.

PHOTO v2 (вердикт Vitali вслепую, 30.09-01.10): вчерашний PHOTO (полный Qwen-Image-2.1, 40 шагов, cfg 4,
1 Мп, серая подложка, промпт obj_photo.PHOTO) лучше прямого RGBA на 6 из 8 - материал, край, без обводки
пиксельных ступеней. Специалист: база - PHOTO, а две его старые беды решать отдельно.
  1. Геометрия. Модель рисует свою вещь: другая ширина, лишние или пропавшие ножки, закрытые прорези.
     Прежде чем вырезать, ответ сверяется с силуэтом оригинала (conformity): охват, вылет, прорези,
     тонкие части, насколько пришлось править пропорции. FAIL - не вырезать и не прятать маской.
  2. Альфа. Раньше - заливка подложки по контуру (edge_matte) и умножение на силуэт: серое тело на
     серой подложке выедалось (semi, R-089), серый ободок оставался (R-067). Здесь - тримап от силуэта
     оригинала: ядро силуэта непрозрачно по определению (оригинал там сплошной), всё за полосой вокруг
     силуэта прозрачно по определению, и только полоса в полтора пикселя базы решается по ответу модели
     (его контур и расстояние до подложки). Цвет полупрозрачной кромки очищается от подложки:
     F = (C - (1 - a) B) / a. Подложка ядра, которую модель не закрасила (тело цвета подложки или дыра
     в рисунке), не маскируется - это метрика core_panel и повод на проверку.
Рендер пока - obj_photo.py с параметрами A (RENDER); свой запуск будет отдельным скриптом, не правкой
obj_photo.py: его код входит в generator_rev turbo (obj_gen_spec.CODE_PARTS), и любая правка снимает
утверждение пилота до нового smoke.

Без видеокарты, на готовых ответах made01 (#259, art/objects/made01_photo/raw):
    py -3.13 tools\hdart\photo_base.py regress        набор регрессии: 8 PHOTO v2 + по 2 на трудный случай
    py -3.13 tools\hdart\photo_base.py eval [--set regression|all] [--only q0006,q0040]
Кладёт в art/objects/generation/photo-base/: regression.json/.tsv, eval/<НАБОР>.PCK/<кадр>.png,
eval/eval.tsv (метрики и вердикт по кадру), eval/sheet.png. В пак НЕ идёт.
"""
import argparse
import json
import os
import sys
import time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter       # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("art", "objects", "generation", "photo-base")
MADE01_JOBS = os.path.join("art", "objects", "queue", "jobs_made01.json")
MADE01_OUT = os.path.join("art", "objects", "made01_photo")
PHOTO_V2 = os.path.join("art", "objects", "generation", "probes", "photo-v2")

# рендер базы = сторона A PHOTO v2 (gpuq #259); меняется только новой версией и новой приёмкой
RENDER = {"rev": "photo-render-2026-10-01.1", "engine": "qwen21", "steps": 40, "cfg": 4.0, "mp": 1.0,
          "zoom": 16, "pad": 3, "prompt": "obj_photo.PHOTO", "negative": "obj_photo.NEGATIVE",
          "input": "кадр bicubic x16 на подложке panel_for", "source": "made01 #259, PHOTO v2 A 6:2"}
# подложки: сначала нейтральные серые; предмет серый во всём диапазоне - цветная (R-089: серое тело на
# серой подложке контуром не отделить)
PANELS = [("grey_dark", (38, 38, 42)), ("grey_mid", (96, 96, 102)), ("grey_light", (176, 176, 182))]
CHROMA = [("green", (60, 150, 80)), ("blue", (70, 90, 200))]
MIN_MARGIN = 40.0       # 10-й перцентиль расстояния тела до подложки (худший канал); ниже - риск альфы
HOLE_NOISE = 4          # прозрачная дыра оригинала до N пикселей k=1 - шум индекса 0, заливается
BAND = 6                # полуширина полосы решения у края силуэта, пикселей x4 (1.5 пикселя базы)
TONE = 0.7              # тон к оригиналу, как у made01 (obj_photo --tone)
DARK_LUM = 60           # тёмное в пиксель-арте - щель или тень насквозь (решётка NUKE2 10)
POCKET_MIN = 24         # карман подложки меньше N пикселей x4 - шум, не окно
PANEL_NEAR = 14         # цвет ближе N к подложке (худший канал) - подложка
SHADOW_MIN = 0.6        # тень на подложке - не темнее 0.6 её яркости (глубже - уже тело)
GROW = 2                # кайма кусков составного (obj_series.split), как у obj_photo --grow
# пороги проверки геометрии - черновые, до калибровки на наборе регрессии
GEOM = {"cover_fail": 0.80, "cover_review": 0.92, "spill_review": 0.12, "thin_fail": 0.50,
        "holes_fail": 0.40, "aspect_review": 1.3, "aspect_fail": 1.6, "core_panel_review": 0.03,
        "rim_panel_review": 0.25}


# ---------------------------------------------------------------- маски без scipy

def morph(mask, op, size):
    """Сужение ("min") или расширение ("max") квадратом size x size."""
    im = Image.fromarray(mask.astype(np.uint8) * 255, "L")
    f = ImageFilter.MinFilter(size) if op == "min" else ImageFilter.MaxFilter(size)
    return np.asarray(im.filter(f)) > 127


def grow(mask, r):
    return morph(mask, "max", 2 * r + 1) if r > 0 else mask


def shrink(mask, r):
    return morph(mask, "min", 2 * r + 1) if r > 0 else mask


def label(mask, conn=4):
    """Связные куски: (массив номеров, число кусков); 0 - не маска."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    steps = ((1, 0), (-1, 0), (0, 1), (0, -1)) + (((1, 1), (1, -1), (-1, 1), (-1, -1)) if conn == 8 else ())
    n = 0
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]:
            continue
        n += 1
        lab[y0, x0] = n
        q = deque([(y0, x0)])
        while q:
            y, x = q.popleft()
            for dy, dx in steps:
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    q.append((yy, xx))
    return lab, n


def sil_x4(mask):
    """Маска k=1 -> x4 линиями (R-121, R-042): xBRZ по чёрно-белой маске, край в долю пикселя. В отличие
    от probe_object.smooth_silhouette дыры не заливаются - это решает guide (HOLE_NOISE)."""
    import sprite_scale
    a = mask.astype(np.float32) * 255.0
    rgba = np.stack([a, a, a, np.full_like(a, 255.0)], -1)[None]
    up = sprite_scale.xbrz_scale(rgba, 4)[0][..., 0]
    im = Image.fromarray(np.clip(up, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.7))
    return np.asarray(im, np.float32) / 255.0


# ---------------------------------------------------------------- 1. геометрия оригинала

def guide(frame):
    """Что должно остаться от оригинала (кадр k=1 RGBA): силуэт, прорези, тонкие части, куски."""
    a = np.asarray(frame.convert("RGBA"))
    m = a[..., 3] > 0
    hole_lab, nh = label(~m)
    openings = np.zeros_like(m)
    noise = np.zeros_like(m)
    h, w = m.shape
    for i in range(1, nh + 1):
        c = hole_lab == i
        if c[0].any() or c[-1].any() or c[:, 0].any() or c[:, -1].any():
            continue                                # наружная пустота, не дыра
        (noise if c.sum() <= HOLE_NOISE else openings)[c] = True
    filled = m | noise
    thin = filled & ~grow(shrink(filled, 1), 1)     # что не переживает открытие 3x3: ножки, прутья, рейки
    _lab, comps = label(filled, 8)
    lum = a[..., :3][m].mean(-1) if m.any() else np.zeros(1)
    dark = m & (a[..., :3].mean(-1) < DARK_LUM)
    return {"m": filled, "openings": openings, "thin": thin, "comps": comps,
            "dark4": np.repeat(np.repeat(dark, 4, 0), 4, 1),
            "sil4": sil_x4(filled), "open4": sil_x4(openings) > 0.5 if openings.any() else np.zeros((h * 4, w * 4), bool),
            "thin4": np.repeat(np.repeat(thin, 4, 0), 4, 1),
            "px": int(filled.sum()), "open_px": int(openings.sum()), "thin_px": int(thin.sum()),
            "lum": float(lum.mean()), "lum_p90": float(np.percentile(lum, 90)), "lum_p10": float(np.percentile(lum, 10))}


def panel_for(frame):
    """Подложка рендера и её запас: (имя, цвет, запас). Запас - 10-й перцентиль расстояния тела до
    подложки по худшему каналу; меньше MIN_MARGIN у всех серых - цветная, у всех - риск альфы."""
    a = np.asarray(frame.convert("RGBA"), np.float64)
    px = a[..., :3][a[..., 3] > 128]
    if len(px) == 0:
        return PANELS[0][0], PANELS[0][1], 0.0

    def margin(bg):
        return float(np.percentile(np.abs(px - np.array(bg)).max(-1), 10))
    best = max(PANELS, key=lambda p: margin(p[1]))
    if margin(best[1]) < MIN_MARGIN:
        best = max(PANELS + CHROMA, key=lambda p: margin(p[1]))
    return best[0], best[1], round(margin(best[1]), 1)


# ---------------------------------------------------------------- 2. ответ модели в клетку оригинала

def render_matte(hd):
    """Грубая альфа ответа - только для проверки геометрии и выравнивания: своя прозрачность модели,
    иначе заливка подложки по контуру (obj_photo.edge_matte). И цвет подложки по краю ответа."""
    import obj_photo as op
    rgb = np.asarray(hd.convert("RGB"), np.float32)
    edge = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3),
                           rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3)])
    al = op.own_alpha(hd)
    m = al if al is not None else op.edge_matte(hd.convert("RGB"))
    return np.asarray(m, np.float32), np.median(edge, 0), al is not None


def fit(hd, matte, frame, max_aspect=1.3):
    """Габарит ответа -> габарит оригинала x4, как probe_object.cut_out, но цвет и альфа тянутся
    порознь: цвет под полупрозрачной кромкой нужен целым, для очистки от подложки."""
    cw, ch = frame.width * 4, frame.height * 4
    ob = frame.split()[3].getbbox()
    mi = Image.fromarray((np.clip(matte, 0, 1) * 255).astype(np.uint8), "L")
    ab = Image.fromarray((matte > 0.5).astype(np.uint8) * 255, "L").filter(ImageFilter.MinFilter(5)).getbbox()
    info = {"aspect_raw": None, "aspect_fix": 1.0}
    if not (ob and ab):
        return (np.asarray(hd.convert("RGB").resize((cw, ch), Image.LANCZOS), np.float32),
                np.asarray(mi.resize((cw, ch), Image.LANCZOS), np.float32) / 255.0, info)
    ab = (max(0, ab[0] - 2), max(0, ab[1] - 2), min(hd.width, ab[2] + 2), min(hd.height, ab[3] + 2))
    ox0, oy0, ox1, oy1 = [v * 4 for v in ob]
    sw, sh = (ox1 - ox0) / (ab[2] - ab[0]), (oy1 - oy0) / (ab[3] - ab[1])
    s = (sw * sh) ** 0.5
    info["aspect_raw"] = round(max(sw, sh) / min(sw, sh), 3)     # во сколько раз модель сплющила или вытянула
    sw2 = min(max(sw, s / max_aspect), s * max_aspect)
    sh2 = min(max(sh, s / max_aspect), s * max_aspect)
    info["aspect_fix"] = round(max(sw2, sh2) / min(sw2, sh2), 3)
    size = (max(1, round((ab[2] - ab[0]) * sw2)), max(1, round((ab[3] - ab[1]) * sh2)))
    M = max(size)
    pos = (M + round((ox0 + ox1 - size[0]) / 2), M + oy1 - size[1])
    out = []
    for im, mode in ((hd.convert("RGB"), "RGB"), (mi, "L")):
        piece = im.crop(ab).resize(size, Image.LANCZOS)
        big = Image.new(mode, (cw + 2 * M, ch + 2 * M), 0)
        big.paste(piece, pos)
        out.append(np.asarray(big.crop((M, M, M + cw, M + ch)), np.float32))
    info["scale"] = round(s, 4)
    return out[0], out[1] / 255.0, info


def fit_shape(hd, matte, frame, sil4, steps=5):
    """Ответ в пропорциях модели, для проверки формы: единый масштаб от меньшего до большего из двух
    (по ширине и по высоте), низ, верх или середина по габариту оригинала - берётся положение с лучшим
    совпадением с силуэтом. Правка пропорций (fit) растягивает тело на место пропавшей ножки, а единый
    масштаб по среднему сдвигает тело и валит проверку не на той детали; здесь чего нет - того нет."""
    cw, ch = frame.width * 4, frame.height * 4
    ob = frame.split()[3].getbbox()
    ab = Image.fromarray((matte > 0.5).astype(np.uint8) * 255, "L").filter(ImageFilter.MinFilter(5)).getbbox()
    if not (ob and ab):
        return fit(hd, matte, frame, 1.0)[:2] + ({"anchor": None},)
    ab = (max(0, ab[0] - 2), max(0, ab[1] - 2), min(hd.width, ab[2] + 2), min(hd.height, ab[3] + 2))
    ox0, oy0, ox1, oy1 = [v * 4 for v in ob]
    sw, sh = (ox1 - ox0) / (ab[2] - ab[0]), (oy1 - oy0) / (ab[3] - ab[1])
    mi = Image.fromarray((np.clip(matte, 0, 1) * 255).astype(np.uint8), "L").crop(ab)
    s_ref = sil4 > 0.5

    def place(im, mode, size, pos):
        M = max(size) + max(cw, ch)
        big = Image.new(mode, (cw + 2 * M, ch + 2 * M), 0)
        big.paste(im.resize(size, Image.LANCZOS), (M + pos[0], M + pos[1]))
        return np.asarray(big.crop((M, M, M + cw, M + ch)), np.float32)

    best = None
    for s in np.linspace(min(sw, sh), max(sw, sh), steps):
        size = (max(1, round((ab[2] - ab[0]) * s)), max(1, round((ab[3] - ab[1]) * s)))
        x = round((ox0 + ox1 - size[0]) / 2)
        for anchor, y in (("bottom", oy1 - size[1]), ("top", oy0), ("middle", round((oy0 + oy1 - size[1]) / 2))):
            m = place(mi, "L", size, (x, y)) > 127
            iou = float((m & s_ref).sum()) / max(1, int((m | s_ref).sum()))
            if best is None or iou > best[0]:
                best = (iou, s, size, (x, y), anchor)
    iou, s, size, pos, anchor = best
    rgb = place(hd.convert("RGB").crop(ab), "RGB", size, pos)
    m = place(mi, "L", size, pos) / 255.0
    return rgb, m, {"anchor": anchor, "shape_scale": round(float(s), 4), "shape_iou": round(iou, 4)}


# ---------------------------------------------------------------- 3. проверка геометрии

def shadow_dist(rgb, bg):
    """Расстояние до подложки или её тени (t * подложка, t от SHADOW_MIN до 1), худший канал. Одно на
    проверку прорезей и на альфу в прорезях - иначе проверка и вырезка расходятся."""
    B = np.asarray(bg, np.float32)
    t = np.clip((rgb @ B) / float(B @ B), SHADOW_MIN, 1.0)[..., None]
    return np.abs(rgb - t * B).max(-1)


def big_comps(mask, n_sil):
    """Куски маски больше процента площади силуэта (мелочь - шум матта, а не лишняя деталь)."""
    lab, n = label(mask, 8)
    if not n:
        return 0
    return int((np.bincount(lab.ravel())[1:] >= max(4, 0.01 * n_sil)).sum())


def conformity(g, m_al, info, margin=None, rgb=None, bg=None):
    """Ответ против силуэта оригинала, до всякой вырезки. Доли - от площади силуэта x4. Допуск 2 пикселя
    x4 (полпикселя базы) в обе стороны: край оригинала сам по себе лесенка, тонкое в 1 пиксель базы
    без допуска не покрыть. margin - запас подложки, на которой рисовали, против тела оригинала: меньше
    MIN_MARGIN - матт тело от подложки не отделяет, и низкий охват говорит об альфе, а не о форме."""
    s = g["sil4"] > 0.5
    b = m_al > 0.5
    b2 = grow(b, 2)
    s_in = shrink(s, 2)
    if not s_in.any():
        s_in = s
    n = max(1, int(s_in.sum()))
    r = {"cover": round(float((s_in & b2).sum()) / n, 4),
         "spill": round(float((b & ~grow(s, 8)).sum()) / max(1, int(s.sum())), 4),
         "iou": round(float((s & b).sum()) / max(1, int((s | b).sum())), 4),
         "aspect_raw": info.get("aspect_raw"), "aspect_fix": info.get("aspect_fix"),
         "panel_margin": margin}
    t = g["thin4"] & s
    r["thin_cover"] = round(float((t & b2).sum()) / t.sum(), 4) if t.any() else None
    o = shrink(g["open4"], 2)
    see = ~b
    if rgb is not None:                 # закрытый карман подложки (и её тени) - тоже прорезь, матт не достал
        see = see | (shadow_dist(rgb, bg) < PANEL_NEAR)
    r["holes_kept"] = round(float((o & see).sum()) / o.sum(), 4) if o.any() else None
    r["comps_render"] = big_comps(b, int(s.sum()))
    r["comps_orig"] = big_comps(s, int(s.sum()))
    fail, review = [], []
    if r["cover"] < GEOM["cover_fail"]:
        fail.append("cover %.2f" % r["cover"])
    elif r["cover"] < GEOM["cover_review"]:
        review.append("cover %.2f" % r["cover"])
    if r["spill"] > GEOM["spill_review"]:
        review.append("spill %.2f" % r["spill"])
    if r["thin_cover"] is not None and r["thin_cover"] < GEOM["thin_fail"]:
        fail.append("thin %.2f" % r["thin_cover"])
    if r["holes_kept"] is not None and r["holes_kept"] < GEOM["holes_fail"]:
        fail.append("holes %.2f" % r["holes_kept"])
    # пропорции fit правит до max_aspect 1.3 (как cut_out); больше - остаток уже виден охватом,
    # сильно больше - модель нарисовала другую вещь (столб вместо колонны)
    if r["aspect_raw"] and r["aspect_raw"] > GEOM["aspect_fail"]:
        fail.append("aspect %.2f" % r["aspect_raw"])
    elif r["aspect_raw"] and r["aspect_raw"] > GEOM["aspect_review"]:
        review.append("aspect %.2f" % r["aspect_raw"])
    if r["comps_render"] != r["comps_orig"]:
        review.append("comps %d/%d" % (r["comps_render"], r["comps_orig"]))
    if r["aspect_raw"] and GEOM["aspect_review"] < r["aspect_raw"] <= GEOM["aspect_fail"] and fail:
        # пропорции модели другие: тонкое и прорези в них съезжают с места, и FAIL по деталям - следствие
        # пропорций, а не пропажи (лампа FRNITURE 10, 1.48, у Vitali A лучше). Решает человек
        review, fail = fail + review, []
    matte_hit = [w for w in fail if w.split()[0] in ("cover", "thin", "comps")]
    if margin is not None and margin < MIN_MARGIN and matte_hit and not any(w.startswith("aspect") for w in fail):
        # тело цвета подложки, и недобор - там, где матт мог не отделить тело: форма неизвестна
        r["geometry"] = "UNVERIFIABLE"
        r["geometry_why"] = "panel margin %.0f < %.0f: %s" % (margin, MIN_MARGIN, "; ".join(fail + review))
        return r
    r["geometry"] = "FAIL" if fail else ("REVIEW" if review else "PASS")
    r["geometry_why"] = "; ".join(fail + review)
    return r


# ---------------------------------------------------------------- 4. управляемая альфа и кромка

def managed_alpha(g, rgb, m_al, bg, band=BAND):
    """Тримап от силуэта оригинала: ядро (силуэт, сужённый на band, без прорезей) - 1; снаружи
    (силуэт, расширенный на band) и в глубине прорезей - 0; полоса - по ответу: его альфа, но не дальше
    силуэта, расширенного на band. Возвращает (альфа, тримап 0/1/2 = фон/полоса/ядро)."""
    s = g["sil4"] > 0.5
    op4 = g["open4"]
    core = shrink(s, band) & ~grow(op4, band // 2)
    out = ~grow(s, band) | shrink(op4, band // 2)
    tri = np.ones(s.shape, np.uint8)
    tri[core] = 2
    tri[out & ~core] = 0
    # в полосе: альфа ответа, ограниченная мягким силуэтом, расширенным на band (край модели, если он
    # в полосе, иначе край оригинала); цвет, неотличимый от подложки, - фон
    soft = np.asarray(Image.fromarray((g["sil4"] * 255).astype(np.uint8), "L")
                      .filter(ImageFilter.MaxFilter(2 * (band // 2) + 1)), np.float32) / 255.0
    dist = np.abs(rgb - np.asarray(bg, np.float32)).max(-1)
    colour = np.clip((dist - 6.0) / 24.0, 0.0, 1.0)             # 6 - шум подложки, 30 - уже тело
    a_band = np.minimum(np.maximum(m_al, colour * (m_al > 0.05)), soft)
    # прорези оригинала: матт по контуру (edge_matte) до закрытых карманов подложки не доходит, и они
    # оставались серыми окнами внутри решётки. Здесь - только по цвету: подложка - фон, тело - тело
    # подложка в тени самого предмета (NUKE2 10: серое 0.6-0.8 яркости подложки в окнах решётки) - тоже
    # подложка; только в прорезях, где оригинал говорит, что там пусто
    d_shadow = shadow_dist(rgb, bg)
    # тень - только в самой прорези оригинала; вокруг неё серое тело (распорки PORTROADS 66) похоже на
    # подложку в тени, там - только сама подложка (R-062: серый металл выгрызался)
    ring = grow(op4, band) & ~core & ~op4
    a_band = np.where(ring, np.minimum(colour, soft), a_band)
    a_band = np.where(op4 & ~core, np.minimum(np.clip((d_shadow - 6.0) / 24.0, 0.0, 1.0), soft), a_band)
    alpha = np.where(tri == 2, 1.0, np.where(tri == 0, 0.0, a_band))
    # карманы подложки внутри тела: ровное пятно цвета подложки. Над тёмным оригинала - щель, которую
    # модель нарисовала насквозь: прозрачно. Над светлым - тело не нарисовано: не прячем, это core_panel
    from obj_photo import local_std
    flat = local_std(rgb.mean(-1), 2) < 3.0
    pocket = s & (dist < PANEL_NEAR) & flat
    lab, n = label(pocket, 4)
    cut_px = 0
    for i in range(1, n + 1):
        c = lab == i
        k = int(c.sum())
        if k >= POCKET_MIN and g["dark4"][c].mean() >= 0.5:
            c = grow(c, 1) & (dist < 2 * PANEL_NEAR)
            alpha = np.where(c, 0.0, alpha)
            tri = np.where(c, 0, tri).astype(np.uint8)
            cut_px += int(c.sum())
    core = tri == 2
    # крошки: куски полупрозрачного без связи с силуэтом (не с ядром: у тонкой антенны ядра нет вовсе)
    anchor = shrink(s, 1) if shrink(s, 1).any() else s
    lab, n = label(alpha > 0.1, 8)
    keep = np.zeros(n + 1, bool)
    keep[np.unique(lab[anchor & (lab > 0)])] = True
    keep[0] = False
    alpha = np.where(keep[lab], alpha, 0.0)
    im = Image.fromarray((alpha * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.5))
    alpha = np.where(tri == 2, 1.0, np.asarray(im, np.float32) / 255.0)
    return alpha.astype(np.float32), tri, cut_px


def decontaminate(rgb, alpha, bg):
    """Цвет полупрозрачной кромки без подложки: C = a F + (1 - a) B -> F. Где альфа почти 0, цвет не
    важен; где почти 1 - оставляем как есть."""
    B = np.asarray(bg, np.float32)
    a = alpha[..., None]
    F = (rgb - (1.0 - a) * B) / np.maximum(a, 1e-3)
    mix = ((alpha > 0.03) & (alpha < 0.97))[..., None]
    return np.where(mix, np.clip(F, 0, 255), rgb)


def qa(g, rgb, alpha, tri, bg):
    """Метрики итога: охват и вылет против силуэта, полупрозрачное внутри, подложка в ядре, подложка
    по кромке (серый ободок R-067)."""
    s = g["sil4"] > 0.5
    n = max(1, int(s.sum()))
    b = alpha >= 0.5
    dist = np.abs(rgb - np.asarray(bg, np.float32)).max(-1)
    from obj_photo import local_std
    flat = local_std(rgb.mean(-1), 2) < 3.0
    core = tri == 2
    rim = b & ~shrink(b, 2)
    r = {"cover_final": round(float((s & b).sum()) / n, 4),
         "spill_final": round(float((b & ~s).sum()) / n, 4),
         "semi": round(float((s & (alpha > 0) & (alpha < 0.5)).sum()) / n, 4),
         "core_panel": round(float((core & (dist < 14) & flat).sum()) / max(1, int(core.sum())), 4),
         "rim_panel": round(float((rim & (dist < 20)).sum()) / max(1, int(rim.sum())), 4)}
    why = []
    if r["core_panel"] > GEOM["core_panel_review"]:
        why.append("panel in body %.2f" % r["core_panel"])
    if r["rim_panel"] > GEOM["rim_panel_review"]:
        why.append("panel on rim %.2f" % r["rim_panel"])
    r["alpha"] = "REVIEW" if why else "PASS"
    r["alpha_why"] = "; ".join(why)
    return r


def cut(frame, hd, asked=None):
    """Кадр k=1 (кроп с полями, как obj_photo.paint) и ответ модели -> (RGBA x4, отчёт). asked - подложка,
    поданная рендеру (photo_render); без неё - po.pick_background, как подавал made01."""
    import probe_object as po
    g = guide(frame)
    m_raw, bg, own = render_matte(hd)
    rgb, m_al, info = fit(hd, m_raw, frame)
    rep = {"panel_rgb": [round(float(v), 1) for v in bg], "own_alpha": own,
           "px": g["px"], "open_px": g["open_px"], "thin_px": g["thin_px"], "lum": round(g["lum"], 1)}
    a = np.asarray(frame.convert("RGBA"), np.float64)
    body = a[..., :3][a[..., 3] > 128]
    margin = round(float(np.percentile(np.abs(body - bg).max(-1), 10)), 1) if len(body) else None
    rep["panel_should"] = "%s %.0f" % (panel_for(frame)[0], panel_for(frame)[2])
    # made01: подана подложка po.pick_background, а модель вернула свою (светло-серую почти всегда);
    # рендер базы обязан держать подложку, это проверяется здесь
    asked = np.asarray(po.pick_background(frame) if asked is None else asked, np.float64)
    rep["panel_drift"] = round(float(np.abs(bg - asked).max()), 1)
    # форму проверять в пропорциях модели: правка пропорций до 1.3 растягивает тело на место пропавшей
    # ножки и прячет её (синтетика test_photo_base: без ножки охват тонкого 1.0 после правки)
    rgb_u, m_u, shape = fit_shape(hd, m_raw, frame, g["sil4"])
    rep.update(shape)
    rep.update(conformity(g, m_u, info, margin, rgb_u, bg))
    alpha, tri, rep["pockets_cut"] = managed_alpha(g, rgb, m_al, bg)
    clean = decontaminate(rgb, alpha, bg)
    rep.update(qa(g, clean, alpha, tri, bg))
    rgba = np.dstack([clean, alpha * 255.0]).clip(0, 255).astype(np.uint8)
    im = po.match_tone(Image.fromarray(rgba, "RGBA"), frame, TONE)
    # FAIL - форма не та, вырезке не чинится; RERENDER - форма неизвестна, тело цвета подложки
    rep["verdict"] = {"FAIL": "FAIL", "UNVERIFIABLE": "RERENDER"}.get(rep["geometry"]) or (
        "REVIEW" if "REVIEW" in (rep["geometry"], rep["alpha"]) else "PASS")
    return im, rep, g, m_u


# ---------------------------------------------------------------- задания made01

def load(path):
    with open(path, encoding=ENC) as f:
        return json.load(f)


def dump(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def job_frame(world, j):
    """Как obj_photo.paint: составной по местам -> целиком -> кроп по габариту с полями pad."""
    import obj_photo as op
    import obj_series as osr
    comp = op.pieces_at(world, j["map"], j["at"])
    whole, at = osr.compose(comp)
    bb = whole.split()[3].getbbox()
    p = RENDER["pad"]
    box = (max(0, bb[0] - p), max(0, bb[1] - p), min(whole.width, bb[2] + p), min(whole.height, bb[3] + p))
    return comp, whole, at, box, whole.crop(box)


def single_jobs():
    """Задания made01 в один кусок, у которых есть вчерашний ответ."""
    out = []
    for i, j in enumerate(load(MADE01_JOBS)):
        if len(j.get("take", [])) != 1 or len(j.get("at", [])) != 1:
            continue
        if not os.path.exists(os.path.join(MADE01_OUT, "raw", j["name"] + ".png")):
            continue
        key = j["take"][0].split("@")[0]
        s, f = key.split(":")
        out.append(dict(j, index=i, asset_id=key, rel="%s.PCK/%s.png" % (s.upper(), f)))
    return out


CATEGORIES = [
    # (имя, признак по guide/итогу A, по убыванию, что это)
    ("thin_legs", lambda f: f["thin_share"], "тонкие ножки, прутья, стойки"),
    ("openings", lambda f: f["open_px"], "дырки и прорези"),
    ("dark", lambda f: -f["lum"], "тёмный предмет (кайма на тёмном полу)"),
    ("light", lambda f: f["lum"], "светлый предмет"),
    ("problem_edge", lambda f: f["a_semi"] + (1 - f["a_cover"]), "проблемный край у A: полупрозрачное или недобор"),
]


def regress(per=2):
    import map_mockup as mm
    world = mm.World()
    v2 = {j["asset_id"] for j in load(os.path.join(PHOTO_V2, "batch_jobs.json"))}
    verdict = {}
    vt = os.path.join(PHOTO_V2, "verdicts_vitali.tsv")
    if os.path.exists(vt):
        with open(vt, encoding=ENC) as f:
            head = f.readline().rstrip("\n").split("\t")
            for line in f:
                r = dict(zip(head, line.rstrip("\n").split("\t")))
                verdict[r["asset_id"]] = r["outcome"]
    feats = []
    for j in single_jobs():
        _c, _w, _a, _b, frame = job_frame(world, j)
        g = guide(frame)
        a_path = os.path.join(MADE01_OUT, j["rel"])
        a_cover = a_semi = 0.0
        if os.path.exists(a_path):
            spr = world.sprite(j["asset_id"].split(":")[0].lower(), int(j["asset_id"].split(":")[1]), None)
            s4 = sil_x4(np.asarray(spr.convert("RGBA"))[..., 3] > 0) > 0.5
            al = np.asarray(Image.open(a_path).convert("RGBA"))[..., 3]
            n = max(1, int(s4.sum()))
            a_cover = float((s4 & (al >= 128)).sum()) / n
            a_semi = float((s4 & (al > 0) & (al < 128)).sum()) / n
        feats.append({"asset_id": j["asset_id"], "job": j["name"], "what": j["what"], "px": g["px"],
                      "thin_share": round(g["thin_px"] / max(1, g["px"]), 3), "open_px": g["open_px"],
                      "lum": round(g["lum"], 1), "comps": g["comps"], "a_cover": round(a_cover, 3),
                      "a_semi": round(a_semi, 3), "v2": verdict.get(j["asset_id"], "") if j["asset_id"] in v2 else ""})
    chosen, rows = set(), []
    for f in feats:
        if f["asset_id"] in v2:
            chosen.add(f["asset_id"])
            rows.append(dict(f, category="photo_v2", reason="PHOTO v2: %s" % (f["v2"] or "без вердикта")))
    for name, key, what in CATEGORIES:
        pool = sorted((f for f in feats if f["asset_id"] not in chosen and f["px"] >= 60), key=key, reverse=True)
        for f in pool[:per]:
            chosen.add(f["asset_id"])
            rows.append(dict(f, category=name, reason="%s: %s" % (what, key(f))))
    # хорошие простые: A лучше в PHOTO v2 уже есть; добавить по охвату A без полупрозрачного
    pool = sorted((f for f in feats if f["asset_id"] not in chosen and f["thin_share"] < 0.05 and not f["open_px"]),
                  key=lambda f: f["a_cover"] - f["a_semi"], reverse=True)
    for f in pool[:per]:
        chosen.add(f["asset_id"])
        rows.append(dict(f, category="good_simple", reason="простой, A cover %.3f semi %.3f" % (f["a_cover"], f["a_semi"])))
    dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "source": MADE01_JOBS, "render": RENDER,
          "items": rows}, os.path.join(OUT, "regression.json"))
    cols = ["asset_id", "job", "category", "reason", "px", "thin_share", "open_px", "lum", "comps", "a_cover",
            "a_semi", "v2", "what"]
    with open(os.path.join(OUT, "regression.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]).replace("\t", " ") for c in cols) + "\n")
    print("набор регрессии: %d из %d заданий made01 в один кусок" % (len(rows), len(feats)))
    for r in rows:
        print("  %-12s %-20s %s  %s" % (r["category"], r["asset_id"], r["job"], r["reason"]))
    return rows


def overlay(g, m_al):
    """Сверка геометрии цветом: белое - совпало, красное - есть у оригинала, нет у ответа, синее - наоборот,
    жёлтое - прорезь оригинала, закрашенная ответом."""
    s = g["sil4"] > 0.5
    b = m_al > 0.5
    im = np.zeros(s.shape + (3,), np.uint8) + 24
    im[s & b] = (220, 220, 220)
    im[s & ~b] = (230, 40, 40)
    im[b & ~s] = (60, 110, 255)
    im[g["open4"] & b] = (250, 220, 40)
    return Image.fromarray(im, "RGB")


def evaluate(names=None, which="regression", sub="eval"):
    import map_mockup as mm
    import obj_series as osr
    world = mm.World()
    jobs = {j["name"]: j for j in single_jobs()}
    if which == "regression":
        reg = load(os.path.join(OUT, "regression.json"))["items"]
        order = [(r["job"], r["category"]) for r in reg]
    else:
        order = [(n, "") for n in jobs]
    if names:
        order = [o for o in order if o[0] in names]
    out = os.path.join(OUT, sub)
    rows, cells = [], []
    for name, cat in order:
        j = jobs[name]
        comp, whole, at, box, frame = job_frame(world, j)
        hd = Image.open(os.path.join(MADE01_OUT, "raw", name + ".png"))
        hd = hd.convert("RGBA" if hd.mode in ("RGBA", "LA", "P") else "RGB")
        im, rep, g, m_al = cut(frame, hd)
        canvas = Image.new("RGBA", (whole.width * 4, whole.height * 4), (0, 0, 0, 0))
        canvas.paste(im, (box[0] * 4, box[1] * 4))
        pieces = osr.split(canvas, comp, at, GROW)
        key = [k for k, _o in comp["members"]][0]
        d = os.path.join(out, key[0] + ".PCK")
        os.makedirs(d, exist_ok=True)
        piece = pieces[key]
        piece.save(os.path.join(d, "%d.png" % key[1]))
        rows.append(dict(rep, asset_id=j["asset_id"], job=name, category=cat))
        cells.append((j, piece, g, m_al, rep, cat))
        print("%-20s %-12s %-6s geom %-6s %-28s alpha %-6s %s" % (j["asset_id"], cat, rep["verdict"], rep["geometry"],
                                                              rep["geometry_why"][:28], rep["alpha"], rep["alpha_why"]),
              flush=True)
    cols = ["asset_id", "job", "category", "verdict", "geometry", "geometry_why", "alpha", "alpha_why", "cover",
            "spill", "iou", "thin_cover", "holes_kept", "aspect_raw", "aspect_fix", "comps_render", "comps_orig",
            "cover_final", "spill_final", "semi", "core_panel", "rim_panel", "px", "open_px", "thin_px", "lum",
            "panel_rgb", "panel_margin", "panel_should", "panel_drift", "pockets_cut", "own_alpha"]
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "eval.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
    sheet(world, cells, os.path.join(out, "sheet.png"))
    n = {v: sum(r["verdict"] == v for r in rows) for v in ("PASS", "REVIEW", "RERENDER", "FAIL")}
    print("итог: %s; eval.tsv и sheet.png в %s" % (", ".join("%s %d" % kv for kv in n.items()), out))
    return rows


def sheet(world, cells, path):
    """Строка на предмет: оригинал x4 | A (made01) | новый | геометрия | новый на пурпурном, на тёмном полу."""
    import obj_series as osr
    cw, ch = 128, 160
    im = Image.new("RGB", (5 * (cw + 4), len(cells) * (ch + 18)), (32, 32, 36))
    dr = ImageDraw.Draw(im)
    for r, (j, piece, g, m_al, rep, cat) in enumerate(cells):
        s, f = j["asset_id"].split(":")
        y = r * (ch + 18)
        orig = world.sprite(s.lower(), int(f), None).convert("RGBA").resize((cw, ch), Image.NEAREST)
        a_path = os.path.join(MADE01_OUT, j["rel"])
        cols = [osr.on_floor(orig, (cw, ch))]
        cols.append(osr.on_floor(Image.open(a_path).convert("RGBA"), (cw, ch)) if os.path.exists(a_path) else None)
        cols.append(osr.on_floor(piece, (cw, ch)))
        ov = overlay(g, m_al)
        cols.append(ov.resize((cw, round(ov.height * cw / ov.width)), Image.NEAREST) if ov.width > cw else ov)
        mg = Image.new("RGBA", piece.size, (255, 0, 255, 255))
        mg.alpha_composite(piece)
        cols.append(mg.convert("RGB"))
        for c, cell in enumerate(cols):
            if cell is not None:
                im.paste(cell, (c * (cw + 4), y + 16))
        dr.text((2, y + 2), "%s %s %s | geom %s %s | alpha %s %s" % (
            j["asset_id"], cat, rep["verdict"], rep["geometry"], rep["geometry_why"], rep["alpha"], rep["alpha_why"]),
            fill=(255, 255, 0))
    im.save(path)
    print("ЛИСТ %s" % path)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["regress", "eval"])
    ap.add_argument("--set", default="regression", choices=["regression", "all"])
    ap.add_argument("--only", default="")
    ap.add_argument("--sub", default="", help="папка итога в photo-base (по умолчанию eval, для --set all - eval_all)")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.cmd == "regress":
        regress()
    else:
        evaluate(set(a.only.split(",")) if a.only else None, a.set,
                 a.sub or ("eval_all" if a.set == "all" else "eval"))


if __name__ == "__main__":
    main()
