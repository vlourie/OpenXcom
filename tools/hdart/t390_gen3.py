#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000390 (заправка, блок URBANWASTE12), третий круг кандидатов 04.11. В МОД НИЧЕГО НЕ СТАВИТ: кадры - art/tickets/t390/cand3/
(второй вариант - cand3/alt), сырьё - art/tickets/t390/gen3/, листы - art/_review/tickets_2026-11-04/. cand и cand2 не трогаются.

Что сказал Vitali про круг 2: бензоколонка - настоящая старая топливораздаточная колонка (высокий шкаф со скруглённым верхом,
голова с табло, панель, пистолет в держателе и чёрный шланг петлёй на боковой грани, цоколь с отсеком); ведро - круглое
металлическое, по кругу равные вертикальные выемки; кадры кандидатов мягкие - брак.

Чем отличается от t390_gen2.py:
  * колонка: новое описание по настоящей колонке (слов tall slim нет, пропорция 0,6 числом), два варианта описания;
  * ведро: основа - ГЕОМЕТРИЧЕСКАЯ ОТРИСОВКА цилиндра с N равными выемками в проекции боевого вида (2:1, 30 градусов, свет
    сверху-слева, battle_view); вариант 1 - её перерисовывает модель (вход вместо эскиза классики), вариант 2 - сама отрисовка;
  * РЕЗКОСТЬ: прежняя подгонка делала аффинное преобразование BILINEAR по уже готовому кадру 128x160 (лишняя передискретизация,
    мягче), match_tone срезал контраст (gain<1), заливка spread размазывала цвет. Здесь предмет уменьшается из сырого ответа
    ОДИН раз Lanczos до 2x кадра, остаточная подгонка BICUBIC на 2x, потом Lanczos вдвое; тон - только сдвиг среднего (без
    потери контраста); внутренность не трогается, край - по маске (xBRZ силуэт, R-121); лёгкий unsharp по внутренности.
  * числа резкости - mask_audit.sharp_of / edge_width (те же, что в аудите 29.10), сравнение с одобренным qwen21_strict.

    py -3.13 tools\hdart\t390_gen3.py prompts
    py -3 tools\gpuq.py add --name t390-cand3 --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t390_gen3.py render
    py -3.13 tools\hdart\t390_gen3.py seeds        # листы зёрен + таблица (IoU, резкость)
    py -3.13 tools\hdart\t390_gen3.py build [--alt]
    py -3.13 tools\hdart\t390_gen3.py sheet        # t390_cand3.png (классика / сейчас / кандидат, NEAREST)
    py -3.13 tools\hdart\t390_gen3.py scene        # t390_cand3_scene.png + полный размер
"""
import argparse
import csv
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
import t379_391_gen as t                             # noqa: E402

REV = os.path.join(ROOT, "art", "_review", "tickets_2026-11-04")
GEN = os.path.join(ROOT, "art", "tickets", "t390", "gen3")
CAND = os.path.join(ROOT, "art", "tickets", "t390", "cand3")
g.GEN, g.REV, t.GEN, t.REV = GEN, REV, GEN, REV

GLOSS = "glossy, shiny, plastic, specular highlights, wet look, chrome, clean new, cartoon outline"
PUMP_NEG = (GLOSS + ", trash can, garbage bin, swing lid, round lid on top, dome cap, vending machine, plain smooth box, "
            "lettering, letters, digits, numbers, logo, text, tall slim column, thin tower")
BIN_NEG = (GLOSS + ", square box, rectangular box, cube, wooden staves, plastic bin, wheels, handle, lid, flat lid, "
           "uneven grooves, irregular spacing, smooth plain cylinder, lettering, letters, X, logo, emblem, text")
PUMP_WHAT_C = (
    "a vintage petrol pump, an old roadside fuel dispenser: a tall rectangular cabinet of dull lilac-violet painted sheet "
    "metal with a smoothly rounded top, about three fifths as wide as it is tall; at the top of the front face a head "
    "housing with a dark glass dial window in a riveted metal frame with a soft glass highlight; below it a smaller panel "
    "with a faded brown rust-coloured emblem blotch; on the narrow left side face a holster holding a fuel nozzle gun, "
    "with a thick black rubber hose hanging from it in a loop; at the bottom a dark plinth with a dark service compartment "
    "opening; riveted panel seams, scuffed and chipped paint, worn metal edges")
PUMP_WHAT_D = (
    "an old petrol station fuel pump column made of dull lilac-violet painted steel, a tall boxy cabinet with a rounded "
    "shoulder at the top and a flat narrow top ridge, about three fifths as wide as it is tall: in the upper part of the "
    "front face a dark glass gauge window in a thick riveted frame with a faint reflection streak, under it a small dark "
    "square plate with a faded brown rust blotch, a black rubber hose looping down the narrow left side face from a nozzle "
    "gun hung in a metal holder, a dark recessed bay and a plinth at the foot; panel joints with rivets, scratched paint, "
    "rust at the corners")
BIN_WHAT = (
    "a round steel pail, a small dark charcoal-grey metal bucket shaped as an upright cylinder seen from above: a round "
    "rolled rim on top with a dark empty inside, and a ring of straight vertical flutes, narrow grooves of identical width "
    "and perfectly even spacing, running all the way round the body from the rim down to the base; patches of "
    "rust-brown and orange corrosion and maroon streaks over the lower part, scratched weathered matte steel, no letters "
    "and no markings")
JOBS = {
    "pumpC": dict(members=[("URBAN_WASTE", 85, (0, 0, 0))], seeds=[4301, 4302, 4303], r1=[], aspect=2.2, what=PUMP_WHAT_C,
                  neg=PUMP_NEG, slab=False),
    "pumpD": dict(members=[("URBAN_WASTE", 85, (0, 0, 0))], seeds=[4311, 4312, 4313], r1=[], aspect=2.2, what=PUMP_WHAT_D,
                  neg=PUMP_NEG, slab=False),
    "binG": dict(members=[("URBITS_WASTE", 23, (0, 0, 0))], seeds=[4321, 4322, 4323], r1=[], aspect=2.2, what=BIN_WHAT,
                 neg=BIN_NEG, slab=False, geom=True),
}
for _j in JOBS.values():
    _j["neg"] = _j["neg"] + ", " + t.SLAB
g.JOBS = JOBS
g.CLUSTERS = {}
BEST = {"pump": ("pumpC", 4301), "bin": ("binG", 4323)}      # выбрано по листу зёрен 04.11
SPARE = {"pump": ("pumpD", 4313), "bin": ("proc", 0)}
ALT = False
FAM = {
    "pump": [("URBAN_WASTE", 85), ("MADDECOR_WASTE", 49), ("RUSTSHACKS2", 51)],
    "bin": [("URBITS_WASTE", 23), ("CATACDECOR_CONC", 23)],
}
BASE_KEY = {"pump": ("URBAN_WASTE", 85), "bin": ("URBITS_WASTE", 23)}
NGROOVE = 14
EDGE_GAIN = 4.0   # крутизна края после сглаживания контура (около 1,2 пикс шириной)
LAM = 0.8      # вес штрафа за выход предмета за маску при подгонке (0 - только покрытие маски, 1 - почти IoU)


# ---------------------------------------------------------------------------------------------------------------
# геометрическая основа ведра
# ---------------------------------------------------------------------------------------------------------------
def _fbm(h, w, scale, rng, octaves=4):
    """Гладкий шум 0..1 размера (h, w): сумма уровней, мелкий уровень - клетка scale пикс."""
    acc = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        s = max(2, int(scale / (2 ** o)))
        small = rng.random((h // s + 2, w // s + 2)).astype(np.float32)
        up = np.asarray(Image.fromarray(small).resize((w + 2 * s, h + 2 * s), Image.BICUBIC))[:h, :w]
        acc += amp * up
        tot += amp
        amp *= 0.55
    acc /= tot
    return (acc - acc.min()) / max(acc.max() - acc.min(), 1e-6)


def bin_render(S=16, n=NGROOVE, seed=7, clean=False):
    """Круглое ведро-цилиндр в боевом ракурсе (ортография, наклон 30 град: верхний круг - эллипс 2:1), свет сверху-слева.
    Холст 32x40 пикселей классики, S пикселей на пиксель классики. Размеры - по классике URBITS_WASTE:23 (bbox 9..22 x 17..35):
    радиус 7, центр верхнего эллипса y=20,5, центр нижнего y=32,5. Возвращает (rgb float HxWx3, alpha float 0..1)."""
    W, H = 32 * S, 40 * S
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    X, Y = (xs + 0.5) / S, (ys + 0.5) / S
    cx, R, e = 16.0, 7.0, 0.5
    ytop, ybase = 20.5, 32.5
    dx = X - cx
    inside = np.sqrt(np.maximum(R * R - dx * dx, 0.0))
    r2 = (dx / R) ** 2 + ((Y - ytop) / (e * R)) ** 2
    top = r2 <= 1.0
    ft = ytop + e * inside                                   # передняя дуга верхнего эллипса
    body = (np.abs(dx) <= R) & (Y > ft) & (Y <= ybase + e * inside)
    alpha = (top | body).astype(np.float32)
    rgb = np.zeros((H, W, 3), np.float32)

    # --- стенка: углы вокруг оси, выемки с равным шагом ---
    th = np.arcsin(np.clip(dx / R, -1, 1))
    P = 2 * np.pi / n
    cc = th / P + 0.5
    cc = cc - np.round(cc)                                    # -0.5..0.5, выемка в cc = 0
    gw = 0.21
    inn = np.abs(cc) < gw
    dep = np.where(inn, 0.5 * (1 + np.cos(np.pi * cc / gw)), 0.0)
    ddc = np.where(inn, -0.5 * (np.pi / gw) * np.sin(np.pi * cc / gw), 0.0)
    v = np.clip((Y - ft) / (ybase - ytop), 0, 1)
    gmask = np.clip((v - 0.10) / 0.04, 0, 1)                   # выемки - от кромки до дна
    thn = th + 0.20 * ddc * gmask
    lam = -0.62 * np.sin(thn) + 0.35 * np.cos(thn)
    light = 0.30 + 0.85 * np.clip(lam / 0.7, 0, 1.15)
    light = light * (1 - 0.55 * dep * gmask) * (1 - 0.14 * v)
    steel = np.array([70, 73, 80], np.float32)
    grain = _fbm(H, W, 6 * S / 4, rng, 3)
    fine = (rng.random((H, W)).astype(np.float32) - 0.5)
    f8 = Image.fromarray(np.clip(fine * 255 + 128, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(S / 8))
    fine = (np.asarray(f8).astype(np.float32) - 128.0) / 255.0 * 3.0
    shade = light * (0.94 + 0.12 * grain) + fine * 0.12
    col = steel[None, None, :] * shade[..., None]
    # ржавчина как у классики: оранжево-бурая справа и внизу, бордовые потёки слева
    if not clean:
        big = _fbm(H, W, 7 * S, rng, 5)
        streak = np.asarray(Image.fromarray(rng.random((H // 40 + 2, W // 3 + 2)).astype(np.float32))
                            .resize((W, H), Image.BICUBIC))
        rm = np.clip((big * 0.9 + 0.30 * (dx / R) + 0.25 * v - 0.70) * 6.0, 0, 1) * gmask
        mm = np.clip((streak * 0.9 + 0.30 * (-dx / R) - 0.80) * 7.0, 0, 1) * gmask * (1 - rm)
        rust = np.array([158, 84, 34], np.float32)
        rust2 = np.array([104, 52, 30], np.float32)
        mix = _fbm(H, W, 2 * S, rng, 3)[..., None]
        rcol = (rust[None, None, :] * (0.55 + 0.45 * mix) + rust2[None, None, :] * (0.45 - 0.45 * mix))
        mar = np.array([108, 40, 52], np.float32)
        lit = np.clip(light, 0.45, 1.1)[..., None]
        col = col * (1 - rm[..., None] * 0.92) + rcol * lit * (rm[..., None] * 0.92)
        col = col * (1 - mm[..., None] * 0.85) + mar[None, None, :] * lit * (mm[..., None] * 0.85)
    # --- верхняя закатка (бортик) ---
    bead = body & (v < 0.10)
    bl = np.clip(0.55 + 0.45 * np.cos(np.clip(v / 0.10, 0, 1) * np.pi), 0, 1)       # светлый верх, тёмный низ
    bshade = (0.55 + 0.75 * np.clip(lam / 0.7, 0, 1)) * (0.65 + 0.55 * bl)
    bcol = np.array([112, 116, 124], np.float32)[None, None, :] * bshade[..., None]
    col = np.where(bead[..., None], bcol, col)
    # тёмная кромка у самого дна (стык с землёй)
    foot = body & (Y > ybase + e * inside - 0.35)
    col = np.where(foot[..., None], col * 0.55, col)
    # --- верх: бортик-кольцо и тёмная внутренность ---
    wrim = 0.14
    ring = top & (r2 > (1 - wrim) ** 2)
    ang = np.arctan2((Y - ytop) / (e * R), dx / R)
    rl = 0.72 + 0.28 * np.cos(ang - np.deg2rad(215))          # кольцо светлее со стороны источника (верх-лево)
    rcl = np.array([128, 132, 140], np.float32)[None, None, :] * (rl[..., None])
    rcl = rcl * (0.92 + 0.16 * grain[..., None])
    ins = top & ~ring
    yy = np.clip(-(Y - ytop) / (e * R), -1, 1)                  # + к дальней стенке
    ic = np.clip(16 + 30 * np.clip(yy, 0, 1) ** 1.5 + 6 * np.clip(-dx / R, 0, 1), 6, 60)
    icol = np.stack([ic * 1.0, ic * 1.02, ic * 1.08], -1)
    col = np.where(ring[..., None], rcl, col)
    col = np.where(ins[..., None], icol, col)
    rgb[...] = np.clip(col, 0, 255)
    return rgb, alpha


def reduce_rgba(rgb, alpha, f):
    """Уменьшение в f раз усреднением блоков (площадь), цвет - с весом альфы: край ровный, внутренность не мылится."""
    H, W = alpha.shape
    h, w = H // f, W // f
    a = alpha[:h * f, :w * f].reshape(h, f, w, f).mean((1, 3))
    c = (rgb[:h * f, :w * f] * alpha[:h * f, :w * f, None]).reshape(h, f, w, f, 3).sum((1, 3))
    n = np.maximum(alpha[:h * f, :w * f].reshape(h, f, w, f).sum((1, 3)), 1e-6)
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = np.clip(c / n[..., None], 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    return Image.fromarray(out, "RGBA")


def bin_procedural():
    rgb, al = bin_render(16)
    return reduce_rgba(rgb, al, 4)


def bin_geom_sil():
    """Силуэт геометрии ведра на холсте 128x160, float 0..255 (аналитические дуги, лесенки нет)."""
    _rgb, al = bin_render(16, clean=True)
    H, W = al.shape
    return al.reshape(H // 4, 4, W // 4, 4).mean((1, 3)) * 255.0


# ---------------------------------------------------------------------------------------------------------------
# подгонка под маску без потери резкости
# ---------------------------------------------------------------------------------------------------------------
def sil_classic(cls_k1):
    import probe_object as po
    m = Image.fromarray((np.asarray(cls_k1)[..., 3] > 0).astype(np.uint8) * 255, "L")
    return np.asarray(po.smooth_silhouette(m, 4)).astype(np.float32)


def key_raw(hd, soft=40, floor=0.30):
    """Ответ модели -> RGBA с альфой по краю подложки (как в po.cut_out) на полном разрешении ответа."""
    import probe_object as po
    a = np.asarray(hd.convert("RGB"), np.float32)
    edge = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
    bg = tuple(float(v) for v in np.median(edge, axis=0))
    rgba = po.gen_fire.unpanel(hd, bg, soft)
    al = np.asarray(rgba.split()[3], np.float32) / 255.0
    al = np.clip((al - floor) / (1.0 - floor), 0.0, 1.0)
    rgba.putalpha(Image.fromarray((al * 255).astype(np.uint8), "L"))
    return rgba, al


def _affine_apply(img, prm, size, k):
    sx, sy, shx, shy, tx, ty = prm
    cx, cy = size[0] / 2, size[1] / 2
    a1, b1 = 1.0 / sx, -shx / sy
    d1, e1 = -shy / sx, 1.0 / sy
    Tx, Ty = tx * k, ty * k
    c1 = cx - a1 * (cx + Tx) - b1 * (cy + Ty)
    f1 = cy - d1 * (cx + Tx) - e1 * (cy + Ty)
    return img.transform(size, Image.AFFINE, (a1, b1, c1, d1, e1, f1), Image.BICUBIC)


def affine_search(al8, sil_bool):
    """Остаточное аффинное преобразование (масштаб по осям, наклон, сдвиг) по IoU альфы с маской; поиск на 1/4 холста."""
    h, w = al8.shape
    s = 4
    small_sil = np.asarray(Image.fromarray(sil_bool.astype(np.uint8) * 255).resize((w // s, h // s), Image.BILINEAR)) > 128
    small_al = Image.fromarray(al8).resize((w // s, h // s), Image.BILINEAR)

    def score(prm):
        m = np.asarray(_affine_apply(small_al, prm, small_al.size, 1)) > 128
        n = small_sil.sum()
        # покрытие маски минус штраф за выход за маску (за маской всё равно срезается): заливки цветом меньше, чем при IoU
        return ((m & small_sil).sum() - LAM * (m & ~small_sil).sum()) / n if n else 0.0

    prm = [1.0, 1.0, 0.0, 0.0, 0.0, 0.0]
    best = score(prm)
    steps = [0.08, 0.08, 0.08, 0.04, 3.0, 3.0]
    for _ in range(40):
        moved = False
        for i in range(6):
            for sgn in (1, -1):
                q = list(prm)
                q[i] += sgn * steps[i]
                sc = score(q)
                if sc > best + 1e-5:
                    prm, best, moved = q, sc, True
        if not moved:
            steps = [v / 2 for v in steps]
            if steps[0] < 0.004:
                break
    return prm, best


def fit_sharp(raw_rgb, target_a, mode="affine"):
    """Сырой ответ -> RGBA 128x160 под маску target_a (float 0..255, 128x160).
    1) габарит ответа -> габарит маски ОДНИМ Lanczos на холст 2x (256x320), 2) остаточная аффинная подгонка BICUBIC на 2x,
    3) Lanczos вдвое. Возвращает (RGBA без заливки, IoU до подгонки, IoU после)."""
    rgba, al = key_raw(raw_rgb)
    ab = Image.fromarray((al > 0.5).astype(np.uint8) * 255, "L").filter(ImageFilter.MinFilter(5)).getbbox()
    ab = (max(0, ab[0] - 2), max(0, ab[1] - 2), min(raw_rgb.width, ab[2] + 2), min(raw_rgb.height, ab[3] + 2))
    tb = Image.fromarray((target_a > 128).astype(np.uint8) * 255, "L").getbbox()
    tb2 = tuple(v * 2 for v in tb)
    piece = rgba.crop(ab).resize((tb2[2] - tb2[0], tb2[3] - tb2[1]), Image.LANCZOS)
    canvas = Image.new("RGBA", (256, 320), (0, 0, 0, 0))
    canvas.paste(piece, (tb2[0], tb2[1]))
    sil2 = np.asarray(Image.fromarray(target_a.astype(np.uint8)).resize((256, 320), Image.BILINEAR)) > 128
    a0 = np.asarray(canvas)[..., 3] > 128
    iou0 = float((a0 & sil2).sum() / (a0 | sil2).sum())
    prm = [1.0, 1.0, 0.0, 0.0, 0.0, 0.0]
    if mode == "affine":
        prm, _b = affine_search(np.asarray(canvas)[..., 3], sil2)
    pm = np.asarray(canvas).astype(np.float32).copy()
    pm[..., :3] *= pm[..., 3:4] / 255.0
    chans = [_affine_apply(Image.fromarray(np.clip(pm[..., c], 0, 255).astype(np.uint8)), prm, (256, 320), 4) for c in range(4)]
    # уменьшение вдвое по каналам отдельно (премноженный цвет и альфа), чтобы Pillow не премножал второй раз
    red = np.stack([np.asarray(c.resize((128, 160), Image.LANCZOS)) for c in chans], -1).astype(np.float32)
    al1 = red[..., 3]
    rgb = np.where(al1[..., None] > 1, red[..., :3] * 255.0 / np.maximum(al1[..., None], 1.0), 0)
    res = np.concatenate([np.clip(rgb, 0, 255), al1[..., None]], -1).astype(np.uint8)
    im = Image.fromarray(res, "RGBA")
    a1 = res[..., 3] > 128
    sil1 = target_a > 128
    iou1 = float((a1 & sil1).sum() / (a1 | sil1).sum())
    return im, iou0, iou1


def shift_tone(im, cls_k1, amount=0.7):
    """Тон к классике: сдвиг среднего каждого канала по непрозрачному, БЕЗ изменения размаха (контраст не режем)."""
    o = np.asarray(cls_k1.convert("RGBA"), np.float32)
    o = o[..., :3][o[..., 3] > 128]
    c = np.asarray(im, np.float32).copy()
    body = c[..., 3] > 128
    if len(o) == 0 or body.sum() == 0:
        return im
    d = (o.mean(0) - c[..., :3][body].mean(0)) * amount
    c[..., :3] = np.clip(c[..., :3] + d, 0, 255)
    return Image.fromarray(c.astype(np.uint8), "RGBA")


def fill_target(cut, target_a, unsharp=(1.0, 70)):
    """Альфа = маска (сглаженная, края прямые), цвет - ответ модели, а где его нет - ближайший надёжный (od.spread, до 24 пикс).
    Лёгкий unsharp - по цвету, не по краю. Возвращает (RGBA, число пикселей маски без цвета ответа)."""
    import obj_derive as od
    a = np.asarray(cut).astype(np.float32).copy()
    rel = (a[..., 3] >= 250)
    rel = np.asarray(Image.fromarray(rel.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(3))) > 0
    need = (target_a > 128) & ~rel
    for c in range(3):
        a[..., c] = od.spread(a[..., c], rel, 24)
    rgb = Image.fromarray(np.clip(a[..., :3], 0, 255).astype(np.uint8), "RGB")
    if unsharp:
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=unsharp[0], percent=unsharp[1], threshold=2))
    out = np.zeros(a.shape, np.uint8)
    out[..., :3] = np.asarray(rgb)
    out[..., 3] = np.clip(target_a, 0, 255).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    return Image.fromarray(out, "RGBA"), int(need.sum())


def fill_hybrid(cut, target_a, grow=8, near=0, unsharp=(1.0, 70), edge_sigma=2.5):
    """Силуэт - СВОЙ силуэт предмета модели (гладкие дуги, лесенки нет), без заливки по всей маске: альфа предмета обрезается
    классической маской, расширенной на grow пикс x4 (R-089), а пробелы маски дальше near пикс x4 от предмета остаются
    прозрачными (заливка spread размазывала цвет и мылила низ). Пробелы ближе near - закрываются цветом от ближайших пикселей,
    с краем по силуэту классики (xBRZ). Возвращает (RGBA, число залитых пикселей x4, число пикселей маски без закрытия)."""
    import obj_derive as od
    a = np.asarray(cut).astype(np.float32).copy()
    al = a[..., 3]
    m8 = Image.fromarray((target_a > 128).astype(np.uint8) * 255)
    mg = np.asarray(m8.filter(ImageFilter.MaxFilter(2 * grow + 1))) > 0
    rel = (al >= 250)
    rel_e = np.asarray(Image.fromarray(rel.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(3))) > 0
    nearm = np.asarray(Image.fromarray((al > 128).astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * near + 1))) > 0
    for c in range(3):
        a[..., c] = od.spread(a[..., c], rel_e, 24)
    rgb = Image.fromarray(np.clip(a[..., :3], 0, 255).astype(np.uint8), "RGB")
    if unsharp:
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=unsharp[0], percent=unsharp[1], threshold=2))
    keep = np.where(mg, al, 0.0)
    gap = np.where(nearm, target_a, 0.0)                 # пробел маски рядом с предметом - край по силуэту классики
    alpha = np.maximum(keep, gap * (al < 250))
    alpha = np.where(mg | (target_a > 0), alpha, 0.0)
    if edge_sigma:
        # контур предмета модели чуть волнистый (ключ по подложке): гауссово сглаживание двоичной маски и обратная резкость
        # перепада даёт ровные дуги и отрезки с краем шириной около пикселя; внутренность (цвет) не затрагивается
        from scipy import ndimage as ndi
        binm = alpha > 128
        solid = ndi.binary_fill_holes(binm)                     # внешний контур вместе со сквозными просветами (петля шланга)
        b = Image.fromarray(solid.astype(np.uint8) * 255, "L").filter(ImageFilter.GaussianBlur(edge_sigma))
        b = np.asarray(b).astype(np.float32) / 255.0
        outer = np.clip(0.5 + EDGE_GAIN * (b - 0.5), 0, 1) * 255.0
        hole = solid & ~binm
        lab, nl = ndi.label(hole)                              # мелкие дыры (блик цвета подложки на металле) - закрыть, R-089
        if nl:
            sz = ndi.sum(hole, lab, range(1, nl + 1))
            core = np.asarray(Image.fromarray(hole.astype(np.uint8) * 255, "L").filter(ImageFilter.MinFilter(3))) > 0
            thick = set(np.unique(lab[core]).tolist()) - {0}      # просвет шире 2 пикс; тонкий шов блика - не просвет
            big = np.isin(lab, [i + 1 for i, v in enumerate(sz) if v >= 60 and (i + 1) in thick])
            hole = big
        hole = np.asarray(Image.fromarray(hole.astype(np.uint8) * 255, "L").filter(ImageFilter.MaxFilter(3))) > 0
        # внутри просвета (между шлангом и корпусом) альфа - как у модели, без сглаживания: там виден пол
        alpha = np.where(hole, np.minimum(outer, alpha), outer)
    out = np.zeros(a.shape, np.uint8)
    out[..., :3] = np.asarray(rgb)
    out[..., 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    filled = int(((target_a > 128) & (al < 128) & nearm).sum())
    uncovered = int(((target_a > 128) & (out[..., 3] < 128)).sum())
    return Image.fromarray(out, "RGBA"), filled, uncovered


# ---------------------------------------------------------------------------------------------------------------
# резкость: числа mask_audit
# ---------------------------------------------------------------------------------------------------------------
def sharp_numbers(im):
    """(sharp, edge_w) по mask_audit: доля высокочастотной энергии внутри контура и ширина перепада на краях, px HD."""
    import mask_audit as ma
    a = np.asarray(im.convert("RGBA"))
    full = a[..., 3] >= 128
    lum = a[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    s = ma.sharp_of(lum, full)
    ew, _n = ma.edge_width(lum, full, 4)
    return (0.0 if s is None else s), ew


# ---------------------------------------------------------------------------------------------------------------
# задания: вход для модели
# ---------------------------------------------------------------------------------------------------------------
def geom_frame():
    """RGBA кадр 32x40 (k=1 по размеру холста, x4 пикселей) для рамки задания ведра: геометрия x4 с альфой."""
    rgb, al = bin_render(16, clean=False)
    return reduce_rgba(rgb, al, 4)


def do_render(jobs):
    import argparse as ap2
    import map_mockup as mm   # noqa: F401
    import probe_object as po
    ns = ap2.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=g.STEPS, qwen21_cfg=g.CFG,
                       qwen21_mp=g.MP, qwen21_strength=0.0, qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="",
                       qwen21_ref_mp=1.0, qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    args = ap2.Namespace(steps=g.STEPS, cfg=g.CFG, mp=g.MP)
    t0, n = time.time(), 0
    for job in jobs:
        J = JOBS[job]
        sd = os.path.join(GEN, job)
        os.makedirs(os.path.join(sd, "raw"), exist_ok=True)
        text, neg = g.build_prompt(job)
        print("[%s]\n  PROMPT: %s\n  NEG: %s" % (job, text, neg), flush=True)
        po.gen_fire.NEGATIVE = neg
        _comp, full, _at = g.comp_of(job)
        box = g.padded_box(full)
        if J.get("geom"):                     # вход - отрисованная геометрия (выемки с равным шагом), а не эскиз классики
            full = geom_frame()
        frame = full.crop(box)
        panel = po.pick_background(frame)
        src = frame.resize((frame.width * g.ZOOM, frame.height * g.ZOOM), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        flat.convert("RGB").save(os.path.join(sd, "raw", "input.png"))
        for seed in J["seeds"]:
            dst = os.path.join(sd, "raw", "%d.png" % seed)
            if os.path.exists(dst):
                print("[%s] зерно %d уже есть" % (job, seed), flush=True)
                continue
            hd = po.gen_fire.run_pass(painter, args, text, flat.convert("RGB"), seed)
            po.gen_hd.save_png(hd, dst)
            n += 1
            print("[%s] зерно %d готово (%d), %.0f с" % (job, seed, n, time.time() - t0), flush=True)


def raw_of(job, seed):
    return Image.open(os.path.join(GEN, job, "raw", "%d.png" % seed)).convert("RGB")


def target_for(fam):
    if fam == "pump":
        return sil_classic(g.classic_of(*BASE_KEY["pump"]))
    return bin_geom_sil()


def make_base(fam, job, seed):
    """Кадр основы 128x160 + таблица чисел."""
    cls = g.classic_of(*BASE_KEY[fam])
    if job == "proc":
        im = bin_procedural()
        return im, dict(iou0=1.0, iou1=1.0, fill=0)
    tgt = target_for(fam)
    cut, iou0, iou1 = fit_sharp(raw_of(job, seed), tgt)
    cut = shift_tone(cut, cls)
    if fam == "pump":
        im, nfill, unc = fill_hybrid(cut, tgt)
    else:
        im, nfill = fill_target(cut, tgt)
        unc = 0
    return im, dict(iou0=iou0, iou1=iou1, fill=nfill, unc=unc)


def clip_to_classic_grow(im, cls_k1, grow=2):
    """R-089: альфа не выходит за силуэт классики x4, расширенный на grow пикс x4."""
    m = Image.fromarray((np.asarray(cls_k1)[..., 3] > 0).astype(np.uint8) * 255).resize((128, 160), Image.NEAREST)
    m = m.filter(ImageFilter.MaxFilter(2 * grow + 1))
    a = np.asarray(im).copy()
    a[np.asarray(m) == 0, 3] = 0
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA")


def classic_iou(im, cls_k1):
    sil = sil_classic(cls_k1) > 128
    a = np.asarray(im)[..., 3] > 128
    return float((a & sil).sum() / (a | sil).sum())


def do_seeds():
    import ticket_scene as ts
    rows = [["основа", "задание", "зерно", "IoU до подгонки", "IoU после подгонки", "IoU с маской классики", "дорисовано, пикс x4",
             "sharp", "edge_w"]]
    panels = []
    for fam, jobs in (("pump", ["pumpC", "pumpD"]), ("bin", ["binG"])):
        cls = g.classic_of(*BASE_KEY[fam])
        panels.append(("классика %s:%d" % BASE_KEY[fam], g.on_dark(cls.resize((128, 160), Image.NEAREST).resize((384, 480), Image.NEAREST))))
        if fam == "bin":
            im = bin_procedural()
            sh, ew = sharp_numbers(im)
            rows.append([fam, "proc", 0, "1", "1", "%.3f" % classic_iou(im, cls), 0, "%.3f" % sh, "%.2f" % ew])
            panels.append(("proc sharp %.2f" % sh, g.on_dark(im.resize((384, 480), Image.NEAREST))))
        for job in jobs:
            for s in JOBS[job]["seeds"]:
                if not os.path.exists(os.path.join(GEN, job, "raw", "%d.png" % s)):
                    continue
                im, d = make_base(fam, job, s)
                sh, ew = sharp_numbers(im)
                ci = classic_iou(im, cls)
                rows.append([fam, job, s, "%.3f" % d["iou0"], "%.3f" % d["iou1"], "%.3f" % ci, d["fill"], "%.3f" % sh, "%.2f" % ew])
                panels.append(("%s %d IoU %.2f->%.2f sharp %.2f" % (job, s, d["iou0"], d["iou1"], sh),
                               g.on_dark(im.resize((384, 480), Image.NEAREST))))
    os.makedirs(REV, exist_ok=True)
    with open(os.path.join(REV, "t390_cand3_seeds.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh, delimiter="\t").writerows(rows)
    for r in rows:
        print(*r)
    ts.sheet(panels, os.path.join(REV, "t390_cand3_seeds.png"), cols=5)


def cdir():
    d = os.path.join(CAND, "alt") if ALT else CAND
    os.makedirs(d, exist_ok=True)
    return d


def do_build():
    cdir()
    new, rows = {}, [["кадр", "вид", "основа", "IoU после подгонки", "IoU с маской классики", "дорисовано, пикс x4",
                      "sharp", "edge_w"]]
    for fam, keys in FAM.items():
        job, seed = (SPARE if ALT else BEST)[fam]
        bk = BASE_KEY[fam]
        base, d = make_base(fam, job, seed)
        base = clip_to_classic_grow(base, g.classic_of(*bk)) if fam == "bin" else base
        for key in keys:
            if key == bk:
                im, kind = base, "основа"
            else:
                ob, ot = g.classic_of(*bk), g.classic_of(*key)
                if g.same_px(ob, ot):
                    im, kind = base.copy(), "копия"
                else:
                    flip = g.mirror_closer(ob, ot)
                    b2, o2 = (base.transpose(Image.FLIP_LEFT_RIGHT), ob.transpose(Image.FLIP_LEFT_RIGHT)) if flip else (base, ob)
                    im = g.colormap_transfer(b2, o2, ot) if not g.same_px(o2, ot) else b2
                    kind = "зеркало+перенос цвета" if flip else "перенос цвета"
                    im, _n, _u = fill_hybrid(im, sil_classic(ot), unsharp=None)
            sh, ew = sharp_numbers(im)
            im.save(os.path.join(cdir(), "%s_%d.png" % key))
            new[key] = im
            rows.append(["%s:%d" % key, kind, "%s/%d" % (job, seed), "%.3f" % d["iou1"], "%.3f" % classic_iou(im, g.classic_of(*key)),
                         d["fill"], "%.3f" % sh, "%.2f" % ew])
    with open(os.path.join(REV, "t390_cand3%s_checks.tsv" % ("_alt" if ALT else "")), "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh, delimiter="\t").writerows(rows)
    for r in rows:
        print(*r)


def load_cand():
    ov = {}
    for fn in sorted(os.listdir(cdir())):
        if fn.endswith(".png"):
            s, f = fn[:-4].rsplit("_", 1)
            ov[(s, int(f))] = Image.open(os.path.join(cdir(), fn)).convert("RGBA")
    return ov


def nearest_panel(im, box, k):
    c = im.convert("RGBA").crop(box)
    return g.on_dark(c.resize((c.width * k, c.height * k), Image.NEAREST))


def do_sheet(k=5):
    """Лист: на каждый кадр - классика | сейчас | кандидат, увеличение NEAREST целым k (лист мягкости не добавляет)."""
    import ticket_scene as ts
    ov = load_cand()
    panels = []
    for fam, keys in FAM.items():
        for key in keys:
            cl = g.classic_of(*key).resize((128, 160), Image.NEAREST)
            cur = g.hd_now(*key) or Image.new("RGBA", (128, 160))
            new = ov[key]
            box = t.union_box([cl, cur, new], margin=4)
            ims = [nearest_panel(cl, box, k), nearest_panel(cur, box, k), nearest_panel(new, box, k)]
            H = max(i.height for i in ims)
            row = Image.new("RGB", (sum(i.width for i in ims) + 12, H), (14, 14, 16))
            x = 0
            for i in ims:
                row.paste(i, (x, 0))
                x += i.width + 6
            panels.append(("%s:%d - классика | сейчас | кандидат 3 (NEAREST x%d)%s" % (key + (k, " (вариант 2)" if ALT else "")), row))
    name = "t390_cand3%s.png" % ("_alt" if ALT else "")
    ts.sheet(panels, os.path.join(REV, name), cols=1)
    print("лист:", os.path.join(REV, name))


def do_scene():
    import ticket_scene as ts
    sc = ts.Scene()
    ov = load_cand()
    keys = [("URBAN_WASTE", 85), ("URBITS_WASTE", 23)]
    found = ts.find_cells(sc, "URBAN_WASTE", "URBANWASTE12", keys)
    box = ts.window([(f[0], f[1], tuple(v * 4 for v in f[2])) for f in found], 200, 140, 4)
    maxz = max(f[3] for f in found)
    panels = []
    sfx = "_alt" if ALT else ""
    for title, mode, o in (("классика", "classic", None), ("HD сейчас", "hd", None), ("кандидат 3" + (" (вариант 2)" if ALT else ""), "hd", ov)):
        im, _f = sc.render("URBAN_WASTE", "URBANWASTE12", mode, override=o, k=4, maxz=maxz)
        panels.append(("%s (URBANWASTE12)" % title, ts.crop_pad(im, box)))
        if o:
            im.crop(box).save(os.path.join(REV, "t390_cand3%s_scene_full.png" % sfx))
    ts.sheet(panels, os.path.join(REV, "t390_cand3%s_scene.png" % sfx), cols=1)
    print("лист:", os.path.join(REV, "t390_cand3%s_scene.png" % sfx))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "prompts", "seeds", "build", "sheet", "scene", "geom"])
    ap.add_argument("--alt", action="store_true", help="второй вариант (SPARE) -> cand3/alt")
    ap.add_argument("--jobs", nargs="*", default=list(JOBS), choices=sorted(JOBS))
    a = ap.parse_args()
    global ALT
    ALT = a.alt
    if a.cmd == "prompts":
        for j in a.jobs:
            tx, n = g.build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, tx, n))
    elif a.cmd == "render":
        do_render(a.jobs)
    elif a.cmd == "geom":
        im = bin_procedural()
        os.makedirs(GEN, exist_ok=True)
        im.save(os.path.join(GEN, "bin_proc.png"))
        rgb, al = bin_render(16)
        Image.fromarray(np.dstack([rgb, al * 255]).astype(np.uint8), "RGBA").save(os.path.join(GEN, "bin_geom_x16.png"))
        print("sharp/edge_w:", sharp_numbers(im))
    elif a.cmd == "seeds":
        do_seeds()
    elif a.cmd == "build":
        do_build()
    elif a.cmd == "sheet":
        do_sheet()
    else:
        do_scene()
    return 0


if __name__ == "__main__":
    sys.exit(main())
