#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000492 (04.11): растения IDT_SNOWCULTIVAT:6 и :7 (кочан капусты на снегу) и мёрзлая земля :1, :4 - по 2 кандидата.
В МОД НИЧЕГО НЕ СТАВИТ: кандидаты - art/tickets/t492/plant/<вариант>/IDT_SNOWCULTIVAT_<кадр>.png (128x160 RGBA), сырьё -
art/tickets/t492/plant/<вариант>/raw/<кадр>_<зерно>.png, листы - art/_review/tickets_2026-11-04/t492_plant*.png.

Почему брак (нынешние :6 и :7): оба записаны как floor_material/object из пака до 25.09 (генератор не записан) и сделаны
как плитка пола: тон подогнан по среднему всего кадра, а в кадре много белого снега и ~56 (:6) / ~110 (:7) почти чёрных
пикселей растения - оно усреднено и сметено в белёсый рельеф (:6) или ржавый блок (:7).

Растения (:6, :7):
  * кусту даётся отдельная картинка: только тёмные пиксели классики на подложке (без снега, иначе модель рисует снег на кусте);
  * модель Qwen-2.1 strict (как t390_gen3) рисует куст ростом: стебли из одного корня (R-480), ракурс - battle_view;
  * кадр куста: t390_gen3.fit_sharp (уменьшение из сырого ответа один раз, R-600), тон - сдвиг среднего, альфа - ответ модели,
    ограниченный маской классики +2 пикс x4, силуэт НЕ заливается (между ветками виден снег);
  * снег: t492_build, стиль B2 (как поставленный :0), по индексам снега самого кадра (клетки куста закрыты ближайшим снегом),
    кромка ромба та же (diamond_alpha, перехлёст нижних рёбер, R-599/R-601). Кадр = снег B2, поверх куст.
Земля (:1, :4): без модели, по индексам классики; вероятностная крупа (build_ground), см. ниже.

    py -3.13 -P tools\hdart\t492_plant.py prompts
    py -3 tools\gpuq.py add --name t492-plant --prio 1 -- E:\OpenXCom\tools\hdart\.venv-qwen21\Scripts\python.exe E:\OpenXCom\tools\hdart\t492_plant.py render
    py -3.13 -P tools\hdart\t492_plant.py build       # кандидаты -> plant/<вариант>/
    py -3.13 -P tools\hdart\t492_plant.py sheet       # t492_plant.png
    py -3.13 -P tools\hdart\t492_plant.py scene       # t492_plant_scene.png
Установка (только по выбору Vitali, под очередью правок, обе копии hd): скрипт сам ничего не ставит.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image, ImageFilter                   # noqa: E402

import t405_409_gen as g                             # noqa: E402

REV = os.path.join(ROOT, "art", "_review", "tickets_2026-11-04")
PLANT = os.path.join(ROOT, "art", "tickets", "t492", "plant")
SET, FRAME = "IDT_SNOWCULTIVAT", 6
LUM_PLANT = 120          # пиксель классики темнее этого - куст, светлее - снег
PAD = 3
GROW = 2                 # маска классики для обрезки: +2 пикс x4 (R-089)

NEG_COMMON = ("heap, pile, mound, flat mat, nest, rock, stone, boulder, pebbles, snow, frost, ice, white, pale grey, "
              "leaves in green, flowers, fruit, berries, grass blades, log, wooden planks, fence, text, "
              "stone slab, paving tiles, base plate, floor tiles, ground square")


def _job(frame, variant, seeds, what, neg=NEG_COMMON):
    return dict(frame=frame, variant=variant, seeds=seeds, slab=False, neg=neg, what=what)


W6A = ("a small dead dry shrub, leafless: five or six thin brittle woody stems of very dark purple-black bark growing up "
       "and outward from one root point at the lower middle, each forking into thinner twigs with fine thorny side shoots "
       "and clear gaps of light between the stems, thickest and darkest at the base, with slightly lighter dull grey-brown "
       "thin tips, a couple of bare twigs sticking out sideways at the left; the whole shrub low and wide, about twice as "
       "wide as it is tall")
W6B = ("a low winter bramble shrub of dry thorny canes: a few arching dark charcoal-black canes with a purple tint, thick at "
       "the root and curving up and sideways in shallow arcs, thin forked twigs with small sharp thorns branching off them, "
       "dull rusty-brown highlights on the upper sides of the canes facing the left, deep black shade between them, wide and "
       "low, leafless and without any foliage")
W7A = ("a single round head of cabbage standing in a winter garden bed: a tight dense ball of broad leaves wrapped over "
       "each other in overlapping layers, each leaf with visible paler veins and slightly ruffled curled edges, very dark "
       "green almost black with a purple-black tint, a few larger outer leaves flaring out at the base, a faint cold "
       "blue-grey sheen on the leaf surfaces facing the left")
W7B = ("a dark winter cabbage: a heavy round compact head of thick wrinkled leaves folded one over another, strongly "
       "visible pale midribs and veins on every leaf, the colour of dark bottle-green fading to black in the creases, "
       "wide dark outer leaves cupping the head from below, small cold blue-grey highlights on the upper left leaves")
NEG7 = ("heap, pile, flat mat, nest, rock, stone, boulder, pebbles, snow, frost, ice, white, pale grey, light green, "
        "bright green, pale green, lettuce, shrub, bush, twigs, branches, flowers, metal, ball, fruit, text, "
        "stone slab, paving tiles, base plate, floor tiles, ground square")
JOBS = {
    "6v1": _job(6, "v1", [4921, 4922, 4923], W6A),
    "6v2": _job(6, "v2", [4931, 4932, 4933], W6B),
    "7v1": _job(7, "v1", [4941, 4942, 4943], W7A, NEG7),
    "7v2": _job(7, "v2", [4951, 4952, 4953], W7B, NEG7),
}
g.JOBS = JOBS
g.CLUSTERS = {}
BEST = {"6v1": 4921, "6v2": 4931, "7v1": 4942, "7v2": 4951}   # выбрано по листу зёрен t492_plant_seeds.png


# ---------------------------------------------------------------------------------------------------------------
def classic_k1(frame=FRAME):
    """Классика k=1 RGBA 32x40 и маска куста (темнее LUM_PLANT)."""
    cl = g.classic_of(SET, frame)
    a = np.asarray(cl.convert("RGBA"))
    lum = a[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    plant = (a[..., 3] > 0) & (lum < LUM_PLANT)
    return cl, plant


def plant_sprite(frame=FRAME):
    """Кадр только куста: пиксели классики куста, остальное прозрачно."""
    cl, plant = classic_k1(frame)
    a = np.asarray(cl.convert("RGBA")).copy()
    a[~plant] = 0
    return Image.fromarray(a, "RGBA")


def padded_box(img, pad=PAD):
    bb = img.split()[3].getbbox()
    return (max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad))


def closed_plant(frame=FRAME):
    from scipy import ndimage as ndi
    _cl, plant = classic_k1(frame)
    return ndi.binary_closing(plant, structure=np.ones((3, 3), bool), iterations=1) | plant


def plant_target(frame=FRAME):
    """Силуэт куста классики x4 128x160 float 0..255: дыры между ветками закрыты (силуэт куста, не веток), край - xBRZ
    (без лесенки x4, R-121)."""
    import probe_object as po
    m = Image.fromarray(closed_plant(frame).astype(np.uint8) * 255, "L")
    return np.asarray(po.smooth_silhouette(m, 4)).astype(np.float32)


def clip_mask(frame=FRAME, grow=GROW):
    """Для обрезки: маска куста классики x4, закрытая и расширенная на grow пикс x4, bool 160x128."""
    m = Image.fromarray(closed_plant(frame).astype(np.uint8) * 255, "L").resize((128, 160), Image.NEAREST)
    m = m.filter(ImageFilter.MaxFilter(2 * grow + 1))
    return np.asarray(m) > 0


# ---------------------------------------------------------------------------------------------------------------
def do_render(jobs):
    import argparse as ap2
    import probe_object as po
    ns = ap2.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=g.STEPS, qwen21_cfg=g.CFG,
                       qwen21_mp=g.MP, qwen21_strength=0.0, qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="",
                       qwen21_ref_mp=1.0, qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    args = ap2.Namespace(steps=g.STEPS, cfg=g.CFG, mp=g.MP)
    t0, n = time.time(), 0
    for job in jobs:
        J = JOBS[job]
        full = plant_sprite(J["frame"])
        box = padded_box(full)
        frame = full.crop(box)
        panel = po.pick_background(frame)
        sd = os.path.join(PLANT, J["variant"])
        os.makedirs(os.path.join(sd, "raw"), exist_ok=True)
        text, neg = g.build_prompt(job)
        print("[%s]\n  PROMPT: %s\n  NEG: %s" % (job, text, neg), flush=True)
        po.gen_fire.NEGATIVE = neg
        src = frame.resize((frame.width * g.ZOOM, frame.height * g.ZOOM), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        flat.convert("RGB").save(os.path.join(sd, "raw", "input_%d.png" % J["frame"]))
        for seed in J["seeds"]:
            dst = os.path.join(sd, "raw", "%d_%d.png" % (J["frame"], seed))
            if os.path.exists(dst):
                print("[%s] зерно %d уже есть" % (job, seed), flush=True)
                continue
            hd = po.gen_fire.run_pass(painter, args, text, flat.convert("RGB"), seed)
            po.gen_hd.save_png(hd, dst)
            n += 1
            print("[%s] зерно %d готово (%d), %.0f с" % (job, seed, n, time.time() - t0), flush=True)



# ---------------------------------------------------------------------------------------------------------------
# дальше - без видеокарты
# ---------------------------------------------------------------------------------------------------------------
SNOW_SEED = 492 + 0          # как у :0 B2 (warp=0, зерно не влияет)
TONE_AMOUNT = 0.8
CLEAN_PLANT = (6, 7)
GROUND = (1, 4)


def lum_of(a):
    return a[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)


def snow_base(frame):
    """Снег кадра: стиль B2 (как поставленный :0) по индексам самого кадра, клетки растения закрыты ближайшим снегом."""
    import t492_build as tb
    import water_build as wb
    P = wb.read_set(SET)[frame].astype(np.int32)
    _cl, plant = classic_k1(frame)
    P[plant] = 0
    u, n = np.unique(P[P > 0], return_counts=True)
    for c in u[n <= 2]:
        P[P == c] = u[n.argmax()]
    rgb = tb.render(tb.fill_parent(P), "B2", SNOW_SEED + frame, True)
    out = np.zeros((tb.H, tb.W, 4), np.uint8)
    out[..., :3] = np.rint(rgb).astype(np.uint8)
    out[..., 3] = np.rint(tb.diamond_alpha() * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def shift_lum(im, target, amount=TONE_AMOUNT):
    """Тон: сдвиг среднего ЯРКОСТИ всех каналов одинаково (оттенок листвы не теряется, размах не режется)."""
    c = np.asarray(im, np.float32).copy()
    body = c[..., 3] > 128
    cur = float(lum_of(c)[body].mean())
    d = (target - cur) * amount
    c[..., :3] = np.clip(c[..., :3] + d, 0, 255)
    return Image.fromarray(c.astype(np.uint8), "RGBA"), cur, d


def soft_clip(im, frame):
    """Альфа обрезается маской классики +2 пикс x4, край маски мягкий (ветки у границы не рубятся прямой)."""
    from scipy import ndimage as ndi
    m = clip_mask(frame).astype(np.float32)
    b = ndi.gaussian_filter(m, 1.6)
    f = np.clip(b * 2.0, 0, 1)
    a = np.asarray(im).copy()
    a[..., 3] = np.rint(a[..., 3] * f).astype(np.uint8)
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA")


def sharpen_rgb(im, radius=1.0, percent=70):
    """Лёгкий unsharp по цвету (цвет за краем растягивается spread, чтобы нулевой цвет не тянул край в чёрное)."""
    import obj_derive as od
    a = np.asarray(im).astype(np.float32).copy()
    rel = a[..., 3] >= 250
    for c in range(3):
        a[..., c] = od.spread(a[..., c], rel, 8)
    rgb = Image.fromarray(np.clip(a[..., :3], 0, 255).astype(np.uint8), "RGB")
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=2))
    out = np.asarray(im).copy()
    out[..., :3] = np.asarray(rgb)
    out[out[..., 3] == 0, :3] = 0
    return Image.fromarray(out, "RGBA")


def plant_layer(job, seed):
    """Растение из сырого ответа: fit_sharp -> тон -> unsharp -> обрезка по классике. Возвращает (RGBA 128x160, числа)."""
    import t390_gen3 as t3
    g.JOBS = JOBS                    # t390_gen3 при импорте подменяет g.JOBS
    J = JOBS[job]
    fr = J["frame"]
    raw = Image.open(os.path.join(PLANT, J["variant"], "raw", "%d_%d.png" % (fr, seed))).convert("RGB")
    cut, iou0, iou1 = t3.fit_sharp(raw, plant_target(fr))
    cl, plant = classic_k1(fr)
    tgt = float(lum_of(np.asarray(cl))[plant].mean()) + 6.0
    cut, cur, d = shift_lum(cut, tgt)
    cut = sharpen_rgb(cut)
    cut = soft_clip(cut, fr)
    return cut, dict(iou0=iou0, iou1=iou1, lum_raw=cur, lum_target=tgt)


def compose(frame, layer):
    base = snow_base(frame)
    base.alpha_composite(layer)
    return base


# --- земля :1, :4: вероятностная крупа по индексам классики ---------------------------------------------------
def _merge_small(P, pal, keep=3):
    P = P.copy()
    u, n = np.unique(P[P > 0], return_counts=True)
    big = [c for c, k in zip(u, n) if k > keep]
    for c, k in zip(u, n):
        if k <= keep:
            P[P == c] = big[int(np.argmin([np.abs(pal[c] - pal[b]).sum() for b in big]))]
    return P


def _rank_uniform(a):
    r = a.ravel().argsort().argsort().astype(np.float32)
    return (r / (r.size - 1)).reshape(a.shape)


GSTYLE = {
    "v1": dict(sig=3.2, grain=2, low=0.0, jit=2.0),     # мелкая крупа 2x2
    "v2": dict(sig=4.0, grain=3, low=0.35, jit=3.0),    # крупа 3x3 комками (мёрзлые комья)
}


def build_ground(frame, variant, seed=77):
    """Земля: классы классики (цвет - палитра Пираток), поле вероятностей - сглаженный one-hot (бикубика + Гаусс), класс в пикселе
    выбирает зерно u по накопленной вероятности (классы по яркости): границы - зернистый переход, а не уступ индексов (B2:
    argmax бикубики дал крупные пятна-индексы). Одиночные пиксели и тёмные точки у вершин (индекс 93 в :4) в соседний класс.
    Кромка ромба - t492_build.diamond_alpha (как у :0 B2: точный ромб, перехлёст нижних рёбер)."""
    import cv2
    import t492_build as tb
    import water_build as wb
    from scipy import ndimage as ndi
    pal = wb.palette()[:, :3].astype(np.float32)
    P = tb.fill_parent(_merge_small(wb.read_set(SET)[frame].astype(np.int32), pal))
    cls = sorted(np.unique(P), key=lambda c: float(lum_of(pal[c][None])[0]))
    st = GSTYLE[variant]
    rng = np.random.default_rng(seed + frame)
    Y, X = np.mgrid[0:160, 0:128].astype(np.float32)
    mx, my = ((X + 0.5) / 4 - 0.5).astype(np.float32), ((Y + 0.5) / 4 - 0.5).astype(np.float32)
    pr = []
    for c in cls:
        r = cv2.remap((P == c).astype(np.float32), mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        pr.append(cv2.GaussianBlur(np.clip(r, 0, 1), (0, 0), st["sig"]))
    pr = np.stack(pr, 0)
    pr /= np.maximum(pr.sum(0, keepdims=True), 1e-6)
    cum = np.cumsum(pr, 0)
    gr = st["grain"]
    white = np.kron(rng.random((160 // gr + 1, 128 // gr + 1)).astype(np.float32), np.ones((gr, gr), np.float32))[:160, :128]
    if st["low"]:
        low = ndi.gaussian_filter(rng.standard_normal((160, 128)).astype(np.float32), 3.0)
        u = _rank_uniform((1 - st["low"]) * _rank_uniform(white) + st["low"] * _rank_uniform(low))
    else:
        u = white
    idx = np.clip((cum < u[None]).sum(0), 0, len(cls) - 1)
    rgb = pal[np.array(cls)[idx]]
    j = ndi.gaussian_filter(rng.standard_normal((160, 128)).astype(np.float32), 0.6)
    rgb = rgb + (j / (j.std() + 1e-6) * st["jit"])[..., None]
    out = np.zeros((160, 128, 4), np.uint8)
    out[..., :3] = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    out[..., 3] = np.rint(tb.diamond_alpha() * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


# --- резкость ----------------------------------------------------------------------------------------------------
def sharp_numbers(im, er=None):
    """mask_audit.sharp_of по альфе >= 128 (er=None: как в аудите, отступ 6 px; у тонких предметов функция даёт None) и тот же
    расчёт с отступом er (для тонких веток и деревьев :9, :12 - одинаково для всех, цифры сравнимы между собой)."""
    import mask_audit as ma
    from scipy import ndimage as ndi
    a = np.asarray(im.convert("RGBA"))
    full = a[..., 3] >= 128
    lum = lum_of(a)
    if er is None:
        return ma.sharp_of(lum, full)
    m = full.astype(np.float32)
    inner = ndi.binary_erosion(full, iterations=er)
    if inner.sum() < 120:
        return None
    b1, b2 = ma._mblur(lum, m, 2.0), ma._mblur(lum, m, 8.0)
    ph = float(((lum - b1)[inner] ** 2).mean())
    pm = float(((b1 - b2)[inner] ** 2).mean())
    return ph / (ph + pm + 1e-6)


def sharp_hull(im, er=2):
    """Резкость по ровной оболочке предмета (щели между ветками внутри), отступ er; для растений без снега."""
    import mask_audit as ma
    from scipy import ndimage as ndi
    a = np.asarray(im.convert("RGBA"))
    solid = ndi.binary_fill_holes(ndi.binary_closing(a[..., 3] >= 128, iterations=4))
    return sharp_numbers(Image.fromarray(np.dstack([a[..., :3], (solid * 255).astype(np.uint8)]), "RGBA"), er)


def lap_p95(im):
    """p95 градиента и среднее |лапласиана| яркости по непрозрачному (отступ 4 px), как в t492_cand_sharp.tsv."""
    import cv2
    a = np.asarray(im.convert("RGBA"))
    L = lum_of(a)
    m = a[..., 3] >= 250
    from scipy import ndimage as ndi
    inner = ndi.binary_erosion(m, iterations=4)
    gx, gy = cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3) / 8, cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3) / 8
    gr = np.hypot(gx, gy)
    lp = np.abs(cv2.Laplacian(L, cv2.CV_32F))
    if inner.sum() < 50:
        return None
    return float(np.percentile(gr[inner], 95)), float(lp[inner].mean())


# --- сборка кандидатов ---------------------------------------------------------------------------------------------
def out_path(variant, frame):
    d = os.path.join(PLANT, variant)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "IDT_SNOWCULTIVAT_%d.png" % frame)


def do_build(pick=None):
    import csv
    pick = pick or BEST
    rows = [["кадр", "вариант", "основа", "IoU после подгонки", "яркость сырая", "яркость цель", "sharp_of", "sharp(er2)",
             "sharp(оболочка er2)", "p95 градиента", "лапласиан"]]
    for variant in ("v1", "v2"):
        for fr in GROUND:
            im = build_ground(fr, variant)
            im.save(out_path(variant, fr))
            gp = lap_p95(im)
            rows.append(["%d" % fr, variant, "крупа", "", "", "", "%s" % sharp_numbers(im), "%s" % sharp_numbers(im, 2), "",
                         "%.1f" % gp[0], "%.1f" % gp[1]])
        for fr in CLEAN_PLANT:
            job = "%dv%s" % (fr, variant[1])
            seed = pick[job]
            layer, d = plant_layer(job, seed)
            Image.fromarray(np.asarray(layer), "RGBA").save(os.path.join(PLANT, variant, "layer_%d.png" % fr))
            im = compose(fr, layer)
            im.save(out_path(variant, fr))
            gp = lap_p95(layer)
            rows.append(["%d" % fr, variant, "%s/%d" % (job, seed), "%.3f" % d["iou1"], "%.1f" % d["lum_raw"],
                         "%.1f" % d["lum_target"], "%s" % sharp_numbers(layer), "%s" % sharp_numbers(layer, 2),
                         "%s" % sharp_hull(layer, 2), "%.1f" % gp[0] if gp else "", "%.1f" % gp[1] if gp else ""])
    os.makedirs(REV, exist_ok=True)
    with open(os.path.join(REV, "t492_plant_checks.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh, delimiter="\t").writerows(rows)
    for r in rows:
        print(*r)


# --- листы -------------------------------------------------------------------------------------------------------------
PACK_ROOT = os.path.join(ROOT, "user", "mods", "hd", "hd", "TERRAIN", "IDT_SNOWCULTIVAT.PCK")


def cand_img(variant, frame):
    return Image.open(out_path(variant, frame)).convert("RGBA")


def now_img(frame):
    return Image.open(os.path.join(PACK_ROOT, "%d.png" % frame)).convert("RGBA")


def do_sheet(k=5):
    import ticket_scene as ts
    panels = []
    for fr in (1, 4, 6, 7):
        cl = g.classic_of(SET, fr).resize((128, 160), Image.NEAREST)
        ims = [cl, now_img(fr), cand_img("v1", fr), cand_img("v2", fr)]
        box = (0, 70, 128, 160) if fr in GROUND else (0, 62, 128, 160)
        tiles = []
        for im in ims:
            c = im.crop(box)
            b = Image.new("RGBA", c.size, (70, 75, 85, 255))
            b.alpha_composite(c)
            tiles.append(b.convert("RGB").resize((c.width * k, c.height * k), Image.NEAREST))
        row = Image.new("RGB", (sum(t.width for t in tiles) + 6 * 3, tiles[0].height), (14, 14, 16))
        x = 0
        for t in tiles:
            row.paste(t, (x, 0))
            x += t.width + 6
        panels.append(("IDT_SNOWCULTIVAT:%d - классика x4 | сейчас в паке | вариант 1 | вариант 2 (NEAREST x%d)" % (fr, k), row))
    p = os.path.join(REV, "t492_plant.png")
    ts.sheet(panels, p, cols=1)
    print("лист:", p)


def do_scene():
    import ticket_scene as ts
    sc = ts.Scene()
    panels = []
    for block, frames in (("IDT_SNOWVILLAGE08", (1, 4, 6)), ("IDT_SNOWVILLAGE12", (7,))):
        keys = [(SET, f) for f in frames]
        found = ts.find_cells(sc, "IDT_SNOWVILLAGE", block, keys)
        fx = [f for f in found if f[1] in frames]
        if block.endswith("12"):
            fx = [f for f in found if f[1] == 7]
        box = ts.window([(f[0], f[1], tuple(v * 4 for v in f[2])) for f in fx], 200, 140, 4)
        maxz = max(f[3] for f in found)
        cols = []
        for title, mode, ov in (("классика", "classic", None), ("сейчас", "hd", None),
                                ("вариант 1", "hd", {(SET, f): cand_img("v1", f) for f in (1, 4, 6, 7)}),
                                ("вариант 2", "hd", {(SET, f): cand_img("v2", f) for f in (1, 4, 6, 7)})):
            im, _f = sc.render("IDT_SNOWVILLAGE", block, mode, override=ov, k=4, maxz=maxz)
            c = ts.crop_pad(im, box)
            cols.append((title + " (%s)" % block, c))
            if title.startswith("вариант"):
                c.save(os.path.join(REV, "t492_plant_scene_%s_%s.png" % (block[-2:], title[-1])))
        panels += cols
    p = os.path.join(REV, "t492_plant_scene.png")
    ts.sheet(panels, p, cols=4)
    print("лист:", p)



def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "prompts", "build", "sheet", "scene"])
    ap.add_argument("--jobs", nargs="*", default=list(JOBS), choices=sorted(JOBS))
    a = ap.parse_args()
    if a.cmd == "prompts":
        for j in a.jobs:
            tx, n = g.build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, tx, n))
    elif a.cmd == "render":
        do_render(a.jobs)
    elif a.cmd == "build":
        do_build()
    elif a.cmd == "sheet":
        do_sheet()
    else:
        do_scene()
    return 0


if __name__ == "__main__":
    sys.exit(main())
