#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот AGENT цельной фигурой (специалист 05.10): кадры частей режутся из нормально нарисованного тела, а не
вырезаются маской оригинального спрайта.

Направление 2, стоит. Движок кладёт кадры стопкой (UnitSprite.cpp:636): левая рука, ноги, торс, предмет, правая
рука - всё со сдвигом 0. Ноги 18 и торс 34 общие у позы без оружия (руки 2 и 10) и с двуручным (руки 242 и 250),
поэтому фигура рисуется дважды и кадры собираются так, чтобы обе стопки давали свою фигуру:

  * F_b - без оружия: эталон agent_bv2c_d2 (одобренная клетка разворота), вписанный в клетку по голове
    и ногам оригинала (y 5..33). Пропорции эталона, а не пиксельного спрайта.
  * F_a - с AK: тот же эталон, руки перерисованы Edit-2511 по маске (unit_parts.Inpainter): холст - F_b без рук,
    новый HD-автомат (HANDOB 1354, из принятого M-01) на месте классики, эскиз рук к рукояти и цевью;
    вне маски латенты - холст, автомат вне рук не трогается.

Кадры (x4, 128x160):
  10  правая рука без оружия (поверх всего) = F_b в области NB;
  2   левая рука без оружия (под торсом)    = F_b в области FB с перекрытием под торс;
  34/18 торс и ноги                         = F_b вне рук; под NB (там, где в позе с AK рука ушла) - F_a;
                                              граница торс/ноги по полам пиджака с перекрытием;
  250 правая рука с AK                      = F_a в области NA (без пикселей, совпавших с автоматом);
  242 левая рука с AK (под торсом и автоматом) = F_a в области FA с перекрытием;
  HANDOB 1354                               = автомат (gun_frame).
Альфа - из самой фигуры (подложка за контуром), кромка - цвет внутренних соседей (R-089); маска оригинала
не участвует.

    py -3.13 tools/hdart/agent_full.py gun        # HANDOB 1354 из M-01 (без модели)
    tools/hdart/.venv/Scripts/python.exe tools/hdart/agent_full.py prep    # холст, маска, лист
    py -3.13 tools/gpuq.py add --name agent_full_ak -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe \
        E:/OpenXCom/tools/hdart/agent_full.py render --seeds 5401,5402,5403,5404
    tools/hdart/.venv/Scripts/python.exe tools/hdart/agent_full.py build --pick 5401 --mod <папка мода>

Выход art/units/pilot-agent/full/.
"""
import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont   # noqa: E402

ENC = "utf-8-sig"
PZ = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods")
GOV = os.path.join(PZ, "Piratez", "Resources", "Sprites", "GOV_1.png")
AK_X16 = os.path.join(ROOT, "art", "items", "ak-final", "finished_x16.png")
OUT = os.path.join(ROOT, "art", "units", "pilot-agent", "full")
REF = os.path.join(ROOT, "art", "units", "pilot-agent", "reference", "agent_bv2c_d2.png")
REF_PANEL = (175, 175, 180)
FONT = "C:/Windows/Fonts/arial.ttf"

# автомат: классика AK.png кадр 2 - затыльник (13, 20), дуло (25, 15) в краях пикселей базы
BUTT, MUZZLE = (13.0, 20.0), (25.0, 15.0)
HANDOB_FRAME = 1354                    # 352 + 2 + сдвиг мастер-мода 1000 (R-082)
# холст модели: клетка x32, кусок базы (4,2)-(28,37) -> 768x1120, токен 16 = полпикселя базы
Z = 32
CROP = (4, 2, 28, 37)
TOKEN = 16
STEPS = 8
START = 0.9

# Области в координатах эталона (288x448), сняты по листу с сеткой. NB с запасом (рука над пиджаком и кисть
# у бедра - лишнее уйдёт в торс из F_a), FB впритык к боку пиджака (лишнее отсюда стало бы дырой в боку).
NB = [(84, 122), (101, 122), (111, 134), (115, 160), (114, 186), (113, 215), (110, 248), (106, 262), (117, 284),
      (117, 302), (101, 313), (80, 313), (61, 301), (57, 265), (59, 235), (63, 200), (69, 170), (76, 144)]
FB = [(197, 127), (204, 129), (209, 154), (216, 177), (222, 197), (225, 217), (227, 240), (223, 263), (204, 265),
      (195, 253), (193, 227), (196, 215), (197, 190), (197, 158)]
# пиджак под правой рукой (на холст F_a вместо руки; модель перерисует)
JACKET_UNDER = [(96, 124), (112, 128), (117, 160), (116, 262), (108, 262), (108, 200), (103, 160)]
# полы пиджака: выше - торс, ниже - ноги; перекрытие ног вверх под пиджак
HEM_REF_Y = 262
LEG_OVERLAP = 2.0                      # пикселей базы

# Руки с AK в координатах базы: правая (слева на картинке) - плечо, локоть у бока, предплечье вперёд к рукояти
# (17.0, 20.2); левая (справа) - плечо за торсом, кисть под цевьём (21.4, 16.5). Места - по кадрам 250/242.
NA = [(10.9, 12.4), (13.3, 12.6), (13.6, 15.2), (13.6, 17.3), (15.2, 18.3), (16.4, 18.6), (18.2, 19.0),
      (18.4, 20.4), (17.9, 21.6), (16.2, 21.8), (14.6, 20.9), (12.6, 20.0), (11.0, 19.3), (10.2, 17.6),
      (10.2, 14.2)]
# правая рука в ответе 5401 (снято по листу сырого ответа с сеткой базы): низ предплечья и кисти по рисунку,
# без приклада и рукояти, которые модель нарисовала под ними
NA_TIGHT = [(10.9, 12.4), (13.3, 12.6), (13.6, 15.2), (13.6, 17.3), (15.2, 18.3), (16.4, 18.6), (18.2, 19.0),
            (18.3, 20.2), (17.9, 21.15), (16.0, 21.15), (15.0, 20.7), (14.3, 20.45), (12.6, 19.95),
            (11.2, 19.4), (10.2, 17.6), (10.2, 14.2)]
NA_CUFF = [(15.0, 18.3), (15.6, 18.5), (15.4, 20.9), (14.8, 20.7)]
NA_HAND = [(15.5, 18.5), (17.4, 18.7), (18.3, 19.2), (18.4, 20.4), (17.9, 21.6), (16.2, 21.7), (15.4, 20.9)]
FA = [(19.4, 12.2), (20.7, 12.4), (21.4, 14.0), (21.9, 15.8), (22.9, 16.6), (23.1, 18.2), (22.3, 19.0),
      (20.6, 18.9), (20.2, 17.6), (19.9, 15.9), (19.3, 14.4)]
FA_CUFF = [(20.0, 16.3), (22.3, 16.2), (22.2, 16.9), (20.1, 17.0)]
FA_HAND = [(20.2, 16.9), (22.5, 16.7), (23.1, 18.2), (22.3, 19.0), (20.6, 18.9)]
SLEEVE, CUFF, SKIN = (28, 28, 31), (226, 226, 224), (196, 146, 122)

WHO = ("a male government secret agent with short brown hair and dark sunglasses, in a black business suit with "
       "a white shirt collar and a black tie, black shoes")


def prompt():
    import battle_view as bv
    blk = bv.prompt_block("unit")["positive"]
    return ("<image1> is a figure from a tactical game on a flat light grey panel: " + WHO + ", " + bv.facing(2) +
            ". " + blk[0].upper() + blk[1:] + ". Repaint the figure of <image1> as one detailed hand-painted "
            "digital illustration in the manner of <image2>: the same face, short brown hair, dark sunglasses, "
            "black suit, white shirt collar, black tie and black shoes as the man in <image2>. The agent holds an "
            "assault rifle low in front of the hips with both hands, its muzzle to the upper right: the arm on the "
            "left side of the picture (his right arm) is bent at the elbow and its hand grips the red pistol grip "
            "of the rifle; the arm on the right side of the picture (his left arm) hangs by his side and its hand "
            "holds the red wooden handguard from below. Both arms are whole, natural and as thick as the arms of "
            "the man in <image2>: black suit sleeves, white shirt cuffs, bare hands with fingers closed around the "
            "rifle. Keep the rifle exactly where and as it is in <image1>. Keep the head, torso, legs, size and "
            "position of the figure of <image1>; the pose comes only from <image1>, never from <image2>. Clean "
            "sharp edges. No pixel art, no outlines, no text.")


# ---------------------------------------------------------------- геометрия

class Fit:
    """Эталон -> база. Вписывание снято наложением на клетку оригинала (голова с y 5, низ ног 33, руки на месте
    кадров 2 и 10): при x8 масштаб 0.632, сдвиг (36, 14)."""

    def __init__(self):
        self.s = 0.632 / 8
        self.ox = 36 / 8.0
        self.oy = 14 / 8.0

    def base(self, pts):
        return [(x * self.s + self.ox, y * self.s + self.oy) for x, y in pts]


def poly_mask(pts, scale, size, origin=(0.0, 0.0), sub=4):
    """Многоугольник в координатах базы -> маска size (w, h) при масштабе scale, сглаживание sub x sub."""
    w, h = size
    im = Image.new("L", (w * sub, h * sub), 0)
    ImageDraw.Draw(im).polygon([((x - origin[0]) * scale * sub, (y - origin[1]) * scale * sub) for x, y in pts],
                               fill=255)
    return np.asarray(im.resize((w, h), Image.BOX), np.float32) / 255.0


def dilate(m, r):
    if r <= 0:
        return m
    im = Image.fromarray((m * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.MaxFilter(2 * r + 1)), np.float32) / 255.0


def edge_fill(rgb, alpha, inner=0.97, rounds=6):
    have = alpha >= inner
    out = rgb.copy()
    need = (alpha > 0) & ~have
    for _ in range(rounds):
        if not need.any():
            break
        acc = np.zeros_like(out)
        cnt = np.zeros(alpha.shape, np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                hv = np.roll(np.roll(have, dy, 0), dx, 1)
                acc += np.roll(np.roll(out, dy, 0), dx, 1) * hv[..., None]
                cnt += hv
        ok = need & (cnt > 0)
        out[ok] = acc[ok] / cnt[ok][:, None]
        have = have | ok
        need = need & ~ok
    return out


def matte(rgb, panel, tol=22.0):
    """Подложка - связная с краем картинки область цвета панели; альфа 1 внутри, кромка мягкая по расстоянию
    цвета; цвет кромки - внутренние соседи (без подложки, R-089)."""
    import cv2
    d = np.abs(rgb - np.asarray(panel, np.float32)).max(axis=2)
    like = (d < tol).astype(np.uint8)
    n, lab = cv2.connectedComponents(like, connectivity=4)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bg = np.isin(lab, border[border > 0]) & (like > 0)
    # просвет внутри фигуры (между рукой и боком) - тоже подложка, если цвет почти точно её и пятно не точка
    tight = ((d < 10) & ~bg).astype(np.uint8)
    n2, lab2, st, _c = cv2.connectedComponentsWithStats(tight, connectivity=4)
    big = np.nonzero(st[1:, cv2.CC_STAT_AREA] >= 12)[0] + 1
    bg = bg | np.isin(lab2, big)
    alpha = (~bg).astype(np.float32)
    # кромка: пиксель тела у подложки - смесь; альфа по расстоянию цвета до панели против соседей тела
    ring = (dilate(bg.astype(np.float32), 1) > 0) & ~bg
    alpha[ring] = np.clip(d[ring] / 70.0, 0.35, 1.0)
    rgb2 = edge_fill(rgb, alpha)
    return rgb2, alpha


def premul_resize(rgb, alpha, size):
    pm = np.concatenate([rgb * alpha[..., None], alpha[..., None]], axis=2)
    ch = [np.asarray(Image.fromarray(pm[..., c].astype(np.float32), mode="F").resize(size, Image.LANCZOS))
          for c in range(4)]
    out = np.stack(ch, axis=2)
    a = np.clip(out[..., 3], 0, 1)
    rgb = np.where(a[..., None] > 1e-4, out[..., :3] / np.maximum(a[..., None], 1e-4), 0)
    return np.clip(rgb, 0, 255), a


def ref_in_cell(fit, scale):
    """Эталон в клетке 32x40 при масштабе scale (пикс на базу): rgb, alpha."""
    ref = np.asarray(Image.open(REF).convert("RGB")).astype(np.float32)
    rgb, a = matte(ref, REF_PANEL)
    k = fit.s * scale
    w, h = int(round(ref.shape[1] * k)), int(round(ref.shape[0] * k))
    r2, a2 = premul_resize(rgb, a, (w, h))
    W, H = 32 * scale, 40 * scale
    out_rgb = np.zeros((H, W, 3), np.float32)
    out_a = np.zeros((H, W), np.float32)
    ox, oy = int(round(fit.ox * scale)), int(round(fit.oy * scale))
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(W, ox + w), min(H, oy + h)
    out_rgb[y0:y1, x0:x1] = r2[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    out_a[y0:y1, x0:x1] = a2[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    return out_rgb, out_a


def down(rgb, a, k):
    """Усреднение блоков k x k (альфа - среднее, цвет - по альфе)."""
    h, w = a.shape
    ab = a.reshape(h // k, k, w // k, k)
    pm = (rgb * a[..., None]).reshape(h // k, k, w // k, k, 3).sum(axis=(1, 3))
    asum = ab.sum(axis=(1, 3))
    return pm / np.maximum(asum[..., None], 1e-6), asum / (k * k)


# ---------------------------------------------------------------- автомат

def gun_x16():
    """M-01 x16 -> клетка x16 подобием по двум точкам (затыльник, дуло); rgb, alpha."""
    src = np.asarray(Image.open(AK_X16).convert("RGBA")).astype(np.float32) / 255.0
    op = src[..., 3] > 0.5
    ys = np.nonzero(op.any(axis=1))[0]
    top, bot = ys.min(), ys.max()
    m0 = (np.nonzero(op[top:top + 6].any(axis=0))[0].mean() + 0.5, float(top))
    b0 = (np.nonzero(op[bot - 5:bot + 1].any(axis=0))[0].mean() + 0.5, float(bot + 1))
    m1, b1 = (MUZZLE[0] * 16, MUZZLE[1] * 16), (BUTT[0] * 16, BUTT[1] * 16)
    s = math.hypot(m1[0] - b1[0], m1[1] - b1[1]) / math.hypot(m0[0] - b0[0], m0[1] - b0[1])
    rot = math.atan2(m1[1] - b1[1], m1[0] - b1[0]) - math.atan2(m0[1] - b0[1], m0[0] - b0[0])
    c, sn = math.cos(rot), math.sin(rot)
    ia, ib, idd, ie = c / s, sn / s, -sn / s, c / s
    inv = (ia, ib, b0[0] - (ia * b1[0] + ib * b1[1]), idd, ie, b0[1] - (idd * b1[0] + ie * b1[1]))
    pm = src.copy()
    pm[..., :3] *= pm[..., 3:4]
    ch = [np.asarray(Image.fromarray(pm[..., i], mode="F").transform((512, 640), Image.AFFINE, inv,
                                                                     resample=Image.BICUBIC)) for i in range(4)]
    o = np.clip(np.stack(ch, axis=2), 0, 1)
    a = o[..., 3]
    rgb = np.where(a[..., None] > 1e-4, o[..., :3] / np.maximum(a[..., None], 1e-4), 0) * 255.0
    return np.clip(rgb, 0, 255), a


def cmd_gun(a):
    os.makedirs(OUT, exist_ok=True)
    rgb, al = gun_x16()
    r4, a4 = down(rgb, al, 4)
    save_rgba(r4, a4, os.path.join(OUT, "%d.png" % HANDOB_FRAME))
    save_rgba(rgb, al, os.path.join(OUT, "gun_x16.png"))
    ys, xs = np.nonzero(a4 > 0.5)
    print("HANDOB %d: база x %.2f-%.2f y %.2f-%.2f" % (HANDOB_FRAME, xs.min() / 4, (xs.max() + 1) / 4,
                                                      ys.min() / 4, (ys.max() + 1) / 4))


def save_rgba(rgb, a, path):
    arr = np.concatenate([np.clip(rgb, 0, 255), np.clip(a, 0, 1)[..., None] * 255], axis=2)
    Image.fromarray(arr.round().astype(np.uint8), "RGBA").save(path)


def load_rgba(path):
    x = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
    return x[..., :3], x[..., 3] / 255.0


# ---------------------------------------------------------------- холст

def crop_size():
    return (CROP[2] - CROP[0]) * Z, (CROP[3] - CROP[1]) * Z


def over(dst_rgb, dst_a, rgb, a):
    out_a = a + dst_a * (1 - a)
    out = (rgb * a[..., None] + dst_rgb * dst_a[..., None] * (1 - a[..., None])) / np.maximum(out_a[..., None], 1e-6)
    return out, out_a


def sketch_arm(poly, cuff, hand, scale, size, origin):
    """Эскиз руки: рукав, манжета, кисть - мягкие края (модель не обводит лесенку, R-160)."""
    w, h = size
    rgb = np.zeros((h, w, 3), np.float32)
    a = poly_mask(poly, scale, size, origin)
    rgb[:] = SLEEVE
    for pts, col in ((cuff, CUFF), (hand, SKIN)):
        m = poly_mask(pts, scale, size, origin)
        rgb = rgb * (1 - m[..., None]) + np.asarray(col, np.float32) * m[..., None]
        a = np.maximum(a, m)
    # объём: светлее к верхнему левому краю
    blur = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(scale * 0.6)),
                      np.float32) / 255.0
    sh = np.roll(np.roll(blur, int(scale * 0.4), 0), int(scale * 0.4), 1)
    rgb = rgb * (0.85 + 0.3 * np.clip(blur - sh + 0.5, 0, 1)[..., None])
    return np.clip(rgb, 0, 255), a


def build_ctx(fit):
    """Холст F_a и маска токенов."""
    W, H = crop_size()
    org = (CROP[0], CROP[1])
    cell_rgb, cell_a = ref_in_cell(fit, Z)
    cr = cell_rgb[CROP[1] * Z:CROP[3] * Z, CROP[0] * Z:CROP[2] * Z]
    ca = cell_a[CROP[1] * Z:CROP[3] * Z, CROP[0] * Z:CROP[2] * Z]
    nb = poly_mask(fit.base(NB), Z, (W, H), org)
    fb = poly_mask(fit.base(FB), Z, (W, H), org)
    body_a = ca * (1 - np.maximum(nb, fb))
    ju = poly_mask(fit.base(JACKET_UNDER), Z, (W, H), org)
    body_rgb = cr * (1 - ju[..., None]) + np.asarray((30, 30, 33), np.float32) * ju[..., None]
    body_a = np.maximum(body_a, ju * (1 - fb))
    rgb = np.zeros((H, W, 3), np.float32)
    al = np.zeros((H, W), np.float32)
    far = sketch_arm(FA, FA_CUFF, FA_HAND, Z, (W, H), org)
    rgb, al = over(rgb, al, *far)
    rgb, al = over(rgb, al, body_rgb, body_a)
    g_rgb, g_a = gun_x16()
    g2 = premul_resize(g_rgb, g_a, (32 * Z, 40 * Z))
    gr = g2[0][CROP[1] * Z:CROP[3] * Z, CROP[0] * Z:CROP[2] * Z]
    ga = g2[1][CROP[1] * Z:CROP[3] * Z, CROP[0] * Z:CROP[2] * Z]
    rgb, al = over(rgb, al, gr, ga)
    near = sketch_arm(NA, NA_CUFF, NA_HAND, Z, (W, H), org)
    rgb, al = over(rgb, al, *near)
    panel = np.asarray(REF_PANEL, np.float32)
    ctx = rgb * al[..., None] + panel * (1 - al[..., None])
    # маска: руки обеих поз с запасом в токен; автомат вне рук не перерисовывается
    arms = np.maximum.reduce([nb, fb, poly_mask(NA, Z, (W, H), org), poly_mask(FA, Z, (W, H), org)])
    arms = dilate((arms > 0.05).astype(np.float32), TOKEN)
    tok = arms.reshape(H // TOKEN, TOKEN, W // TOKEN, TOKEN).max(axis=(1, 3))
    return Image.fromarray(np.clip(ctx, 0, 255).astype(np.uint8)), (tok > 0.5).astype(np.float32), (gr, ga)


def cmd_prep(a):
    os.makedirs(OUT, exist_ok=True)
    fit = Fit()
    ctx, tok, _g = build_ctx(fit)
    ctx.save(os.path.join(OUT, "ctx.png"))
    view = np.asarray(ctx).astype(np.float32)
    big = np.kron(tok, np.ones((TOKEN, TOKEN)))
    view = view * (1 - 0.35 * big[..., None]) + np.asarray((40, 90, 255)) * 0.35 * big[..., None]
    Image.fromarray(view.astype(np.uint8)).save(os.path.join(OUT, "ctx_mask.png"))
    print("эталон -> база: %.4f базы на пиксель, сдвиг (%.2f, %.2f)" % (fit.s, fit.ox, fit.oy))
    print("холст %dx%d, токенов в маске %d из %d" % (ctx.width, ctx.height, int(tok.sum()), tok.size))


# ---------------------------------------------------------------- модель

def cmd_render(a):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ.setdefault("HF_HOME", a.models)
    os.environ.setdefault("HF_HUB_CACHE", os.path.join(a.models, "hub"))
    import unit_parts as uparts
    uparts.STEPS = STEPS
    fit = Fit()
    ctx, tok, _g = build_ctx(fit)
    ref = Image.open(REF).convert("RGB")
    p = prompt()
    paint = uparts.Inpainter(a.models, [(ctx, ref, p)])
    raw_dir = os.path.join(OUT, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    for seed in [int(x) for x in a.seeds.split(",")]:
        for st in [float(x) for x in a.starts.split(",")]:
            tag = "ak.s%02d.r%d" % (round(st * 100), seed)
            t0 = time.time()
            raw, log = paint.run(0, ctx, tok, seed, st)
            raw.save(os.path.join(raw_dir, tag + ".png"))
            rec = {"seed": seed, "start": st, "steps": STEPS, "prompt": p, "seconds": round(time.time() - t0, 1),
                   "ref": os.path.relpath(REF, ROOT), "log": log}
            with open(os.path.join(raw_dir, tag + ".json"), "w", encoding=ENC) as f:
                json.dump(rec, f, ensure_ascii=False, indent=1)
            print("%s: %.0f с" % (tag, rec["seconds"]), flush=True)


# ---------------------------------------------------------------- сборка кадров

def f_a_cell(raw_path):
    """Ответ модели (кусок x32) -> клетка x4: rgb, alpha."""
    raw = np.asarray(Image.open(raw_path).convert("RGB")).astype(np.float32)
    edge = np.concatenate([raw[:6].reshape(-1, 3), raw[-6:].reshape(-1, 3), raw[:, :6].reshape(-1, 3),
                           raw[:, -6:].reshape(-1, 3)])
    panel = np.median(edge, axis=0)
    rgb, al = matte(raw, panel)
    W, H = 32 * Z, 40 * Z
    full_rgb = np.zeros((H, W, 3), np.float32)
    full_a = np.zeros((H, W), np.float32)
    full_rgb[CROP[1] * Z:CROP[3] * Z, CROP[0] * Z:CROP[2] * Z] = rgb
    full_a[CROP[1] * Z:CROP[3] * Z, CROP[0] * Z:CROP[2] * Z] = al
    return full_rgb, full_a, panel


def arm_label(poly, f_rgb, f_a, gun_rgb, gun_a, scale):
    """Рука в F_a: многоугольник с запасом, только тело (альфа), без пикселей, совпавших с автоматом холста."""
    W, H = 32 * scale, 40 * scale
    m = dilate((poly_mask(poly, scale, (W, H)) > 0.5).astype(np.float32), max(1, scale // 8))
    gun_like = (gun_a > 0.5) & (np.abs(f_rgb - gun_rgb).max(axis=2) < 40)
    cuff = np.maximum(poly_mask(NA_CUFF, scale, (W, H)), poly_mask(FA_CUFF, scale, (W, H)))
    return (m > 0.5) & (f_a > 0.05) & ~gun_like & ~gun_colour(f_rgb, cuff)


def gun_colour(rgb, cuff=None):
    """Пиксели оружия, которое модель дорисовала сама (деревянный приклад, металл): серый металл и красное дерево.
    Рукав чёрный, манжета белая, кожа - r-g до 60. В кадрах рук их быть не должно: с другим оружием они висели бы
    в воздухе (R-212)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    metal = (mx - mn < 28) & (mx > 85) & (mn < 190)
    if cuff is not None:
        metal &= ~(dilate((cuff > 0.3).astype(np.float32), 2) > 0.5)
    wood = (r - g >= 70) & (r >= 110) & (g < 125)
    # кромка дерева смешана с рукавом (r-g меньше) - пиксель вокруг тоже, но не кожа
    near = (dilate(wood.astype(np.float32), 1) > 0.5) & (r - g >= 25) & (g < 110)
    return metal | wood | near


def _morph(m, r, op):
    import cv2
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.morphologyEx(m.astype(np.uint8), op, k) > 0


def hands_keep(rgb, scale):
    """Кисти и манжеты в F_a: кожа в зоне кистей (щели между пальцами закрыты), белое в зоне манжет. Их чистка
    автомата не трогает - пальцы поверх оружия и есть хват."""
    import cv2
    W, H = 32 * scale, 40 * scale
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # кожа: g/r 0.6-0.85; тёмное дерево, смешанное с рукавом, по r-g похоже на кожу, но g/r у него ниже
    skin = (r - g >= 12) & (r - g < 70) & (r > 100) & (b < g + 12) & (g > 0.58 * r)
    # у кромки цевья смесь кожи с деревом: рядом с деревом кожа только светлая по g/r, иначе над пальцами
    # остаётся рыжая полоска цевья
    wood = (r - g >= 70) & (r >= 100)
    skin &= ~(_morph(wood, max(1, scale // 4), cv2.MORPH_DILATE) & (g < 0.64 * r))
    hz = np.maximum(poly_mask(NA_HAND, scale, (W, H)), poly_mask(FA_HAND, scale, (W, H))) > 0.3
    hz = _morph(hz, int(scale * 0.4), cv2.MORPH_DILATE)
    # манжета только у правой руки: у левой в ответе её нет, а светлое там - цевьё модели
    cz = poly_mask(NA_CUFF, scale, (W, H)) > 0.3
    cz = _morph(cz, int(scale * 0.3), cv2.MORPH_DILATE)
    hand = _morph(skin & hz, max(1, scale // 5), cv2.MORPH_CLOSE)
    return hand | ((rgb.min(axis=2) > 165) & cz)


def model_gun(rgb, gun_a, scale):
    """Автомат, который модель нарисовала сама (кадр x scale): место HD-автомата с запасом, красное дерево,
    светлый металл у автомата, тёмные накладки приклада. Цвет один не отделяет магазин от костюма - нужна форма."""
    import cv2
    r, g = rgb[..., 0], rgb[..., 1]
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    yy = np.arange(rgb.shape[0])[:, None]
    hd = gun_a > 0.3
    wood = (r - g >= 70) & (r >= 100) & (yy > 15 * scale)
    wood = _morph(wood, max(1, scale // 16), cv2.MORPH_DILATE)        # кромка дерева смешана с соседями
    metal = (mx - mn < 30) & (mx >= 75) & (mn < 190) & _morph(hd, scale, cv2.MORPH_DILATE)
    stock = (mx < 75) & (mx - mn < 30) & _morph(wood, max(1, scale // 3), cv2.MORPH_DILATE)
    m = _morph(hd, max(1, scale * 3 // 16), cv2.MORPH_DILATE) | wood | metal | stock
    return _morph(m, max(1, scale // 6), cv2.MORPH_CLOSE)


def clean_fa(rgb, al, gun_a, scale):
    """F_a без автомата модели: его место (кроме кистей и манжет) закрашено из соседей - костюм под автоматом;
    альфа закрашивается так же, поэтому за краем фигуры автомат уходит в прозрачность."""
    import cv2
    keep = hands_keep(rgb, scale)
    inp = (model_gun(rgb, gun_a, scale) & ~keep).astype(np.uint8)
    rgb_c = cv2.inpaint(np.clip(rgb, 0, 255).astype(np.uint8), inp, 5, cv2.INPAINT_TELEA).astype(np.float32)
    # закраска - только там, где её замыкает костюм (вогнутость силуэта костюма без кистей до базы): магазин
    # и приклад поверх пиджака и брюк становятся костюмом, автомат за контуром фигуры - прозрачностью; у кистей
    # (ниже) - тоже прозрачность: кисть в этой позе всегда держит оружие, закраска размазала бы там кожу
    suit = (al > 0.5) & (inp == 0) & ~keep
    a_c = _morph(suit, scale, cv2.MORPH_CLOSE).astype(np.float32)
    W, H = 32 * scale, 40 * scale
    hz = _morph(poly_mask(NA_HAND, scale, (W, H)) > 0.3, int(scale * 0.5), cv2.MORPH_DILATE)
    hz |= _morph(poly_mask(FA_HAND, scale, (W, H)) > 0.3, int(scale * 0.9), cv2.MORPH_DILATE)
    a_c[hz] = 0.0
    al2 = np.where(inp > 0, a_c, al)
    # у кистей из нетронутого остаётся только кожа, манжета и тёмный рукав: тёмно-красная кромка цевья
    # смешана с рукавом и в маску автомата не попадает
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sleeve = (mx < 70) & (mx - mn < 25)
    al2[hz & (inp == 0) & ~keep & ~sleeve] = 0.0
    # левое предплечье за цевьём: у модели его закрывал её автомат, HD-автомат лежит чуть иначе, и между
    # пиджаком и кистью проступал фон. Мост от костюма к кисти - рукав, цвет закраской только от костюма
    body = al2 > 0.5
    fz = _morph(poly_mask(FA, scale, (W, H)) > 0.3, int(scale * 0.3), cv2.MORPH_DILATE)
    bridge = _morph(body, int(scale * 0.6), cv2.MORPH_CLOSE) & ~body & fz
    src = np.where(body[..., None] & ~keep[..., None], rgb_c, 0).astype(np.uint8)
    fill = cv2.inpaint(src, (bridge | keep).astype(np.uint8), 7, cv2.INPAINT_TELEA).astype(np.float32)
    rgb_c = np.where(bridge[..., None], fill, rgb_c)
    al2 = np.where(bridge, 1.0, al2)
    return rgb_c, al2, inp > 0, keep


def cmd_build(a):
    fit = Fit()
    os.makedirs(OUT, exist_ok=True)
    tag = "ak.s%02d.r%d" % (round(a.start * 100), a.pick)
    raw = a.raw or os.path.join(OUT, "raw", tag + ".png")
    if a.raw:
        tag += "+" + os.path.basename(a.raw)
    # F_a и автомат в клетке x32 - метки рук там, кадры - x4
    fa_rgb32, fa_a32, panel = f_a_cell(raw)
    g_rgb, g_a = gun_x16()
    g32 = premul_resize(g_rgb, g_a, (32 * Z, 40 * Z))
    # автомат модели убирается из F_a целиком: в кадрах рук и тела остаются костюм, манжеты и кисти, а оружие -
    # только HD-кадр 1354 (иначе с другим оружием куски этого автомата висели бы в воздухе, R-212)
    fa_rgb32, fa_a32, gun32, keep32 = clean_fa(fa_rgb32, fa_a32, g32[1], Z)
    W32 = (32 * Z, 40 * Z)
    hand_zone = poly_mask(NA_HAND, Z, W32) > 0.5
    na32 = (poly_mask(NA_TIGHT, Z, W32) > 0.5) & (fa_a32 > 0.05) & (~hand_zone | keep32)
    fa32 = dilate((poly_mask(FA, Z, W32) > 0.5).astype(np.float32), max(1, Z // 8)) > 0.5
    fa32 &= fa_a32 > 0.05
    fa_rgb, fa_a = down(fa_rgb32, fa_a32, Z // 4)
    save_rgba(*down(fa_rgb32, fa_a32, Z // 4), os.path.join(OUT, "fa_clean_x4.png"))
    Image.fromarray((gun32 * 255).astype(np.uint8)).save(os.path.join(OUT, "fa_gun_mask_x32.png"))
    na4 = down(np.zeros(na32.shape + (3,), np.float32), na32.astype(np.float32), Z // 4)[1] > 0.5
    fal4 = down(np.zeros(fa32.shape + (3,), np.float32), fa32.astype(np.float32), Z // 4)[1] > 0.5
    fb_rgb, fb_a = ref_in_cell(fit, 4)
    S4 = (128, 160)
    nb4 = poly_mask(fit.base(NB), 4, S4) > 0.5
    fbm4 = poly_mask(fit.base(FB), 4, S4) > 0.5
    hem = (HEM_REF_Y * fit.s + fit.oy) * 4
    yy = np.arange(160)[:, None] * np.ones((1, 128))
    upper = yy < hem
    lower = yy >= hem - LEG_OVERLAP * 4
    # тело (торс + ноги): F_b вне рук без оружия; под правой рукой - F_a без самой руки (рука - в 250, иначе
    # её локоть торчал бы из-за руки 10 в позе без оружия)
    # приклад, который модель дорисовала у бедра, уже закрашен костюмом (clean_fa)
    own = nb4
    body_rgb = np.where(own[..., None], fa_rgb, fb_rgb)
    body_a = np.where(own, fa_a * ~na4, np.where(fbm4 | nb4, 0.0, fb_a))
    # левая рука с AK - всё F_a в зоне обеих левых рук: в FB торс пуст, и что не взято сюда, стало бы дырой
    far_zone = dilate((fal4 | fbm4).astype(np.float32), 3) > 0.5
    frames = {
        10: (fb_rgb, fb_a * nb4),
        2: (fb_rgb, fb_a * (dilate(fbm4.astype(np.float32), 3) > 0.5)),
        34: (body_rgb, body_a * upper),
        18: (body_rgb, body_a * lower),
        250: (fa_rgb, fa_a * na4),
        242: (fa_rgb, fa_a * far_zone),
    }
    # просветы позы с оружием: где у цельной F_a тело, а стопка 242+18+34+250 пуста внутри фигуры (закрытие на
    # 2 пикселя x4) - добираются в 242: он нижний и ничего не перекрывает. Фон самой F_a (промежуток между рукой
    # и телом, между ногами) не трогается - там альфа F_a мала
    import cv2
    nog = stack([frames[242], frames[18], frames[34], frames[250]])[1] > 0.5
    close = cv2.morphologyEx(nog.astype(np.uint8), cv2.MORPH_CLOSE,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    gap = (fa_a > 0.5) & ~nog & close & (dilate((far_zone | na4).astype(np.float32), 3) > 0.5)
    frames[242] = (fa_rgb, np.where(gap, fa_a, frames[242][1]))
    print("просветов позы с оружием закрыто кадром 242: %d пикселей x4" % int(gap.sum()))
    # островки рук с оружием: тёмный обрывок под кистью - остаток магазина модели, закрашенный костюмом
    # руки без оружия не трогаются: полоска F_b у кисти кадра 10 закрывает бок брюк (без неё 2 дырки против F_b)
    for n in (242, 250):
        c, fa_n = frames[n]
        k, lab, st, _ = cv2.connectedComponentsWithStats((fa_n > 0.05).astype(np.uint8), connectivity=8)
        if k > 2:
            big = st[1:, cv2.CC_STAT_AREA].max()
            # кисть с манжетой бывает отделена от рукава щелью - островок с кожей или белым остаётся
            cr, cg = c[..., 0], c[..., 1]
            light = ((cr - cg >= 12) & (cr > 100)) | (c.min(axis=2) > 165)
            drop = [i for i in range(1, k) if st[i, cv2.CC_STAT_AREA] < big * 0.25 and not light[lab == i].any()]
            fa_n = np.where(np.isin(lab, drop), 0.0, fa_n)
            print("кадр %d: убрано островков %d (%d пикселей x4)" % (n, len(drop),
                                                                    int(st[drop, cv2.CC_STAT_AREA].sum()) if drop else 0))
            frames[n] = (c, fa_n)
    pack = os.path.join(OUT, "pack", "GOV_1.PCK")
    os.makedirs(pack, exist_ok=True)
    for n, (rgb, al) in frames.items():
        rgb2 = edge_fill(rgb, al)
        save_rgba(rgb2, al, os.path.join(pack, "%d.png" % n))
    hand = os.path.join(OUT, "pack", "HANDOB.PCK")
    os.makedirs(hand, exist_ok=True)
    g4 = down(g_rgb, g_a, 4)
    save_rgba(g4[0], g4[1], os.path.join(hand, "%d.png" % HANDOB_FRAME))
    with open(os.path.join(pack, "color.txt"), "w", encoding="utf-8-sig") as f:
        f.write("colorAuthority: pack\nframes: 2 10 18 34 242 250\n")
    with open(os.path.join(hand, "color.txt"), "w", encoding="utf-8-sig") as f:
        f.write("colorAuthority: pack\nframes: %d\n" % HANDOB_FRAME)
    info = {"pick": tag, "panel": [round(float(x), 1) for x in panel], "hem_x4": round(hem, 1),
            "near_arm_px": int(na4.sum()), "far_arm_px": int(fal4.sum())}
    with open(os.path.join(OUT, "pack", "build.json"), "w", encoding=ENC) as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    print(info)
    if a.mod:
        import shutil
        for sub in ("GOV_1.PCK", "HANDOB.PCK"):
            dst = os.path.join(a.mod, "hd", sub)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(os.path.join(OUT, "pack", sub), dst)
        print("в мод:", a.mod)
    # дырки: стопка кадров против цельной фигуры (F_b без оружия, F_a с AK)
    import cv2
    bare = stack([frames[2], frames[18], frames[34], frames[10]])
    ak = stack([frames[242], frames[18], frames[34], g4, frames[250]])
    nogun = stack([frames[242], frames[18], frames[34], frames[250]])
    # дырки - против собранной фигуры той же позы: без оружия - F_b, с оружием - F_a без автомата модели
    # (плюс HD-автомат для стопки с ним); пятна в пикселях x4 с местом в базе
    fa_gun = np.maximum(fa_a, g4[1])
    for name, (_r, al), ref_a in (("без оружия", bare, fb_a), ("с AK", ak, fa_gun), ("руки AK без оружия", nogun, fa_a)):
        hole = ((ref_a > 0.5) & (al < 0.5)).astype(np.uint8)
        extra = int(((ref_a < 0.5) & (al > 0.5)).sum())
        n, lab, st, cen = cv2.connectedComponentsWithStats(hole, connectivity=8)
        spots = ["%d@(%.1f,%.1f)" % (st[i, cv2.CC_STAT_AREA], cen[i][0] / 4, cen[i][1] / 4) for i in range(1, n)]
        print("%s: дырок %d, лишнего %d пикселей x4 (фигура %d); пятна: %s" % (
            name, int(hole.sum()), extra, int((ref_a > 0.5).sum()), " ".join(spots) or "нет"))
    sheet_build(frames, g4)


def battle_rifle_x4():
    """Классический Battle Rifle (HANDOB 768, направление 2) nearest x4 - чужое оружие для проверки рук."""
    im = Image.open(os.path.join(PZ, "Piratez", "Resources", "HANDOB", "BattleRifle.png"))
    idx = np.asarray(im)[:, 64:96]
    # палитра листа - не боевая; для проверки покрытия хватит тона по уровню рампы
    tone = (16 - (idx % 16)).astype(np.float32) / 16.0
    rgb = np.kron(tone[..., None] * np.asarray((150, 110, 80), np.float32) + 30, np.ones((4, 4, 1)))
    a = np.kron((idx > 0).astype(np.float32), np.ones((4, 4)))
    return rgb, a


def stack(layers):
    rgb = np.zeros((160, 128, 3), np.float32)
    al = np.zeros((160, 128), np.float32)
    for r, a in layers:
        rgb, al = over(rgb, al, r, a)
    return rgb, al


def sheet_build(fr, gun):
    bare = stack([fr[2], fr[18], fr[34], fr[10]])
    ak = stack([fr[242], fr[18], fr[34], gun, fr[250]])
    cells = [("без оружия: 2+18+34+10", bare), ("с AK: 242+18+34+AK+250", ak),
             ("с Battle Rifle", stack([fr[242], fr[18], fr[34], battle_rifle_x4(), fr[250]])),
             ("руки AK, без оружия", stack([fr[242], fr[18], fr[34], fr[250]]))]
    for n in (2, 10, 18, 34, 242, 250):
        cells.append(("кадр %d" % n, fr[n]))
    cells.append(("AK 1354", gun))
    k = 3
    f = ImageFont.truetype(FONT, 14)
    W = len(cells) * (128 * k + 8)
    sheet = Image.new("RGB", (W, 160 * k + 30), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for i, (t, (r, a)) in enumerate(cells):
        bg = np.zeros((160, 128, 3), np.float32) + (np.indices((160, 128)).sum(0) // 4 % 2)[..., None] * 18 + 52
        im = r * a[..., None] + bg * (1 - a[..., None])
        im = Image.fromarray(np.clip(im, 0, 255).astype(np.uint8)).resize((128 * k, 160 * k), Image.NEAREST)
        sheet.paste(im, (i * (128 * k + 8), 30))
        d.text((i * (128 * k + 8) + 4, 8), t, fill=(230, 230, 230), font=f)
    sheet.save(os.path.join(OUT, "sheet_build.png"))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gun")
    sub.add_parser("prep")
    r = sub.add_parser("render")
    r.add_argument("--models", default=os.environ.get("HD_MODELS", "E:\\models"))
    r.add_argument("--seeds", default="5401")
    r.add_argument("--starts", default=str(START))
    b = sub.add_parser("build")
    b.add_argument("--pick", type=int, required=True, help="зерно выбранного ответа")
    b.add_argument("--start", type=float, default=START)
    b.add_argument("--mod", default="", help="папка тестового мода: hd/GOV_1.PCK и hd/HANDOB.PCK заменяются")
    b.add_argument("--raw", default="", help="другой ответ вместо raw/<pick> (agent_pose: 5401 с новыми кистями)")
    a = ap.parse_args()
    {"gun": cmd_gun, "prep": cmd_prep, "render": cmd_render, "build": cmd_build}[a.cmd](a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
