#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""AGENT направление 2: прицел и присед цельной фигурой, кисти рук с AK без потерь (специалист 05.10, вторая
записка). Продолжение agent_full.py: основа - ответ 5401 и его пак.

Движок (UnitSprite::drawRoutine0, dir 2) кладёт стопку: левая рука, ноги, торс, предмет, правая рука.
  стоит с AK         242, 18, 34, AK 1354, 250
  целится            242, 18, 34, AK 1356 (кадр направления 4) со сдвигом (7, 0), 258
  присел             ноги 26 на месте, всё остальное (руки, торс, предмет) +4 по y
Кадры 242 и 34 общие с позой стоя - новые 258, 26 и 1356 рисуются под них.

Три правки Edit-2511 по маске (unit_parts.Inpainter), все без оружия на холсте и без слова об оружии (R-212):
  hands  F_a без автомата модели: кисти и манжеты целиком (кулаки) - чистка автомата съела пальцы и часть кисти;
  aim    F_a, правая рука - эскиз к рукояти автомата в позе прицела. Рукоять перенесена из позы стоя через сам
         автомат (затыльник и дуло кадра dir 2 -> кадра dir 4 со сдвигом), поэтому кисть встаёт на HD-рукоять;
  kneel  верх F_a опущен на 4, ноги - эскиз по силуэту классического кадра 26, сглаженный (без лесенки, R-160).
         Клякса по силуэту читалась моделью как тень на полу (поднятое бедро стало тенью), поэтому рабочий холст -
         kneel3: ноги цилиндрами со светом по точкам кадра 26 (только эскиз позы, не эталон формы, R-208).
Маска оригинала фигуру не режет: силуэт 26 - только эскиз позы, кадр берётся из нарисованной фигуры. В сборке ноги
выше полы пиджака - всё, что не закрыто торсом и руками позы с AK; серая тень пола под фигурой снимается по яркости.

    tools/hdart/.venv/Scripts/python.exe tools/hdart/agent_pose.py prep
    py -3.13 tools/gpuq.py add --name agent_pose -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe \
        E:/OpenXCom/tools/hdart/agent_pose.py render --jobs hands,aim,kneel3 --seeds 5501,5502,5503
    (рука прицела под поднятый автомат AIM_RAISE: --jobs aim --seeds 5511,5512,5513,5514, выбран 5512)
    tools/hdart/.venv/Scripts/python.exe tools/hdart/agent_pose.py build --hands 5504 --aim 5512 \
        --kneel-job kneel3 --kneel 5603 [--mod <тестовый мод>]

Выход art/units/pilot-agent/full/pose/.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFont          # noqa: E402

import agent_full as af                              # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join(af.OUT, "pose")
RAW0 = os.path.join(af.OUT, "raw", "ak.s90.r5401.png")
GOV_SHEET = af.GOV
AK_SHEET = os.path.join(af.PZ, "Piratez", "Resources", "HANDOB", "AK.png")
Z = af.Z
T = af.TOKEN
CELL = (32 * Z, 40 * Z)
# классика AK.png кадр 4: затыльник слева вверху (8, 15-17), дуло справа внизу (18-19, 21-22) - края пикселей.
# HD-автомат в 3 раза тоньше классического (цевьё 1.2 пикселя базы против 3-4), и на тех же точках кулак дальней руки
# 242 (общий с позой стоя) висел над цевьём с просветом 0.7-1 пиксель. Поднят на 1.5: цевьё закрывает низ кулака -
# дальняя рука держит его с той стороны, как в классике, где толстый ствол накрывает кулак (специалист 05.10)
AIM_RAISE = 1.5
BUTT4, MUZZLE4 = (8.0, 16.3 - AIM_RAISE), (20.0, 22.0 - AIM_RAISE)
AIM_OFF = (7, 0)                # UnitSprite offX[2], offY[2]
KNEEL_DY = 4                    # offYKneel
AIM_FRAME = 1356                # 352 + 4 + сдвиг мастер-мода 1000 (R-082)
KNEEL_LEGS = 26                 # legsKneel 24 + направление
AIM_ARM = 258                   # rarmShoot 256 + направление
# эскиз ног: тон по уровню рампы классики (11 светлее, 13 темнее), 252 - ботинки
LEG_TONE = {11: (46, 46, 50), 12: (37, 37, 41), 13: (29, 29, 33), 252: (14, 14, 16)}

WHO = af.WHO
TAIL = ("Keep the head, torso, size and position of the figure of <image1>; the pose comes only from <image1>, never "
        "from <image2>. Clean sharp edges. No pixel art, no outlines, no text.")


def head():
    import battle_view as bv
    blk = bv.prompt_block("unit")["positive"]
    return ("<image1> is a figure from a tactical game on a flat light grey panel: " + WHO + ", " + bv.facing(2) +
            ". " + blk[0].upper() + blk[1:] + ". Repaint the figure of <image1> as one detailed hand-painted "
            "digital illustration in the manner of <image2>: the same face, short brown hair, dark sunglasses, "
            "black suit, white shirt collar, black tie and black shoes as the man in <image2>. ")


PROMPTS = {
    "hands": ("Both hands are whole and natural, as large as the hands of the man in <image2>: the hand on the left "
              "side of the picture is closed into a fist in front of his hip, and its white shirt cuff joins the "
              "hand directly, with no gap; the hand on the right side of the picture is closed into a loose fist, "
              "palm up, in front of his waist. The hands hold nothing. Keep the arms, legs and everything else "
              "exactly as in <image1>. "),
    "aim": ("The arm on the left side of the picture (his right arm) is bent at the elbow, the elbow at his side and "
            "the forearm held forward at waist height, its hand closed into a fist; the arm on the right side of the "
            "picture (his left arm) stays exactly as it is in <image1>. Both arms are whole, natural and as thick as "
            "the arms of the man in <image2>: black suit sleeves, white shirt cuffs, bare hands. The hands hold "
            "nothing. Keep the legs as in <image1>. "),
    "kneel": ("The agent kneels: the leg on the left side of the picture (his right leg) has its knee on the ground "
              "and its lower leg lies behind him, with the black shoe at the far left; the leg on the right side of "
              "the picture (his left leg) is bent, its knee raised forward and its black shoe flat on the ground "
              "under the knee. Black suit trousers, black shoes, both legs whole and natural. Keep the arms exactly "
              "as in <image1>. "),
    # v2: в v1 поднятое бедро (у классики уходит вправо к колену) модель нарисовала тенью на полу
    "kneel2": ("The agent kneels on one knee. The leg on the left side of the picture (his right leg): its knee rests "
               "on the ground under his hips and its lower leg lies on the ground behind him, the black shoe at the "
               "far left. The leg on the right side of the picture (his left leg): the thigh points forward to the "
               "lower right of the picture, almost level, so the bent knee is the rightmost point of the figure, at "
               "the height of the lower edge of the jacket; from the knee the lower leg goes down to the black shoe "
               "standing flat on the ground a little to the left of the knee. Black suit trousers with soft folds, "
               "black shoes, both legs whole, solid and natural, as thick as the legs of the man in <image2>. The "
               "panel around the figure stays flat light grey: no shadow on the ground, no floor. Keep the arms "
               "exactly as in <image1>. "),
}
PROMPTS["kneel3"] = PROMPTS["kneel2"]
JOBS = ("hands", "aim", "kneel", "kneel2", "kneel3")


# ---------------------------------------------------------------- геометрия

def carry(p, frm, to):
    """Точка p при переносе автомата: подобие, заданное (затыльник, дуло) -> (затыльник, дуло)."""
    (b0, m0), (b1, m1) = frm, to
    z = complex(p[0] - b0[0], p[1] - b0[1]) / complex(m0[0] - b0[0], m0[1] - b0[1]) * \
        complex(m1[0] - b1[0], m1[1] - b1[1])
    return b1[0] + z.real, b1[1] + z.imag


def aim_gun_pts():
    return (BUTT4[0] + AIM_OFF[0], BUTT4[1] + AIM_OFF[1]), (MUZZLE4[0] + AIM_OFF[0], MUZZLE4[1] + AIM_OFF[1])


def aim_shift():
    """Сдвиг кисти правой руки: центр кисти стоя -> та же точка автомата в позе прицела."""
    c = tuple(np.mean(np.asarray(af.NA_HAND), axis=0))
    p = carry(c, (af.BUTT, af.MUZZLE), aim_gun_pts())
    return p[0] - c[0], p[1] - c[1]


def shift_arm(pts):
    """Рука прицела: плечо и локоть (x до 11) на месте, предплечье и кисть (x от 15) сдвинуты целиком."""
    dx, dy = aim_shift()
    out = []
    for x, y in pts:
        w = min(1.0, max(0.0, (x - 11.0) / 4.0))
        out.append((x + w * dx, y + w * dy))
    return out


def zone(pts, scale=Z, dy=0.0):
    return af.poly_mask([(x, y + dy) for x, y in pts], scale, (32 * scale, 40 * scale)) > 0.5


def grow(m, r):
    return af.dilate(m.astype(np.float32), int(r)) > 0.5 if r > 0 else m


def shift_y(x, d):
    if d <= 0:
        return x
    out = np.zeros_like(x)
    out[d:] = x[:-d]
    return out


def crop(x):
    return x[af.CROP[1] * Z:af.CROP[3] * Z, af.CROP[0] * Z:af.CROP[2] * Z]


def to_ctx(rgb, a):
    panel = np.asarray(af.REF_PANEL, np.float32)
    c = crop(rgb) * crop(a)[..., None] + panel * (1 - crop(a)[..., None])
    return Image.fromarray(np.clip(c, 0, 255).astype(np.uint8))


def tokens(m):
    c = crop(m).astype(np.float32)
    h, w = c.shape
    return (c.reshape(h // T, T, w // T, T).max(axis=(1, 3)) > 0.5).astype(np.float32)


def hem_y():
    fit = af.Fit()
    return af.HEM_REF_Y * fit.s + fit.oy


def classic_idx(sheet_path, n):
    sheet = Image.open(sheet_path)
    cols = sheet.width // 32
    x, y = n % cols * 32, n // cols * 40
    return np.asarray(sheet.crop((x, y, x + 32, y + 40)))


# ---------------------------------------------------------------- автомат

def gun_at(butt, muzzle, scale=16):
    """M-01 в клетку x scale подобием по двум точкам (как agent_full.gun_x16, но с любыми точками)."""
    import math
    src = np.asarray(Image.open(af.AK_X16).convert("RGBA")).astype(np.float32) / 255.0
    op = src[..., 3] > 0.5
    ys = np.nonzero(op.any(axis=1))[0]
    top, bot = ys.min(), ys.max()
    m0 = (np.nonzero(op[top:top + 6].any(axis=0))[0].mean() + 0.5, float(top))
    b0 = (np.nonzero(op[bot - 5:bot + 1].any(axis=0))[0].mean() + 0.5, float(bot + 1))
    m1, b1 = (muzzle[0] * scale, muzzle[1] * scale), (butt[0] * scale, butt[1] * scale)
    s = math.hypot(m1[0] - b1[0], m1[1] - b1[1]) / math.hypot(m0[0] - b0[0], m0[1] - b0[1])
    rot = math.atan2(m1[1] - b1[1], m1[0] - b1[0]) - math.atan2(m0[1] - b0[1], m0[0] - b0[0])
    c, sn = math.cos(rot), math.sin(rot)
    ia, ib, idd, ie = c / s, sn / s, -sn / s, c / s
    inv = (ia, ib, b0[0] - (ia * b1[0] + ib * b1[1]), idd, ie, b0[1] - (idd * b1[0] + ie * b1[1]))
    pm = src.copy()
    pm[..., :3] *= pm[..., 3:4]
    ch = [np.asarray(Image.fromarray(pm[..., i], mode="F").transform((32 * scale, 40 * scale), Image.AFFINE, inv,
                                                                     resample=Image.BICUBIC)) for i in range(4)]
    o = np.clip(np.stack(ch, axis=2), 0, 1)
    a = o[..., 3]
    rgb = np.where(a[..., None] > 1e-4, o[..., :3] / np.maximum(a[..., None], 1e-4), 0) * 255.0
    return np.clip(rgb, 0, 255), a


# ---------------------------------------------------------------- холсты

def fa_clean32():
    rgb, a, _panel = af.f_a_cell(RAW0)
    g_rgb, g_a = af.gun_x16()
    g32 = af.premul_resize(g_rgb, g_a, CELL)
    rgb, a, _gun, _keep = af.clean_fa(rgb, a, g32[1], Z)
    # где автомат модели уходил в прозрачность, внутри фигуры остаётся дыра цвета подложки - под холст кладётся
    # тело F_b (эталон без оружия) без его рук
    fit = af.Fit()
    b_rgb, b_a = af.ref_in_cell(fit, Z)
    b_a = b_a * ~(zone(fit.base(af.NB)) | zone(fit.base(af.FB)))
    return af.over(b_rgb, b_a, rgb, a)


def hand_zone():
    return grow(zone(af.NA_HAND) | zone(af.NA_CUFF) | zone(af.FA_HAND) | zone(af.FA_CUFF), Z * 0.6)


def canvas_hands(fa):
    rgb, a = fa
    m = hand_zone()
    return to_ctx(rgb, a), tokens(m)


def canvas_aim(fa):
    rgb, a = fa
    W, H = CELL
    xx = np.arange(W)[None, :] * np.ones((H, 1))
    na = grow(zone(af.NA), Z // 4)
    # под прежней рукой: перед торсом (правее локтя) - тёмный пиджак, левее - фон; модель перерисует
    front = na & (xx >= 11.5 * Z)
    rgb2 = np.where(front[..., None], np.asarray((30, 30, 33), np.float32), rgb)
    a2 = np.where(na, front.astype(np.float32), a)
    ns, nc, nh = shift_arm(af.NA), shift_arm(af.NA_CUFF), shift_arm(af.NA_HAND)
    s_rgb, s_a = af.sketch_arm(ns, nc, nh, Z, CELL, (0.0, 0.0))
    rgb3, a3 = af.over(rgb2, a2, s_rgb, s_a)
    m = grow(na | zone(ns), Z // 2) & ~zone(af.FA)
    return to_ctx(rgb3, a3), tokens(m)


def legs_sketch(lit=False):
    """Ноги приседа: силуэт классического кадра 26 x32, сглаженный на 0.7 пикселя базы, тон по рампе.
    lit - свет сверху-слева по краю силуэта (верх бедра светлее), чтобы плоское пятно не читалось тенью на полу."""
    import cv2
    idx = classic_idx(GOV_SHEET, KNEEL_LEGS)
    col = np.zeros((40, 32, 3), np.float32)
    for v, c in LEG_TONE.items():
        col[idx == v] = c
    col[(idx > 0) & (col.sum(axis=2) == 0)] = LEG_TONE[12]
    m = (idx > 0).astype(np.float32)
    big_m = np.kron(m, np.ones((Z, Z), np.float32))
    big_c = np.kron(col, np.ones((Z, Z, 1), np.float32))
    sg = 0.7 * Z
    bm = cv2.GaussianBlur(big_m, (0, 0), sg)
    bc = cv2.GaussianBlur(big_c * big_m[..., None], (0, 0), sg) / np.maximum(bm[..., None], 1e-4)
    a = np.clip((bm - 0.5) * 6 + 0.5, 0, 1)
    if lit:
        gy, gx = np.gradient(cv2.GaussianBlur(big_m, (0, 0), 1.2 * Z))
        light = np.clip((gy + 0.6 * gx) * Z * 1.6, 0, 1)
        bc = bc + light[..., None] * 34.0
    return np.clip(bc, 0, 255), a


# эскиз ног приседа цилиндрами по точкам классического кадра 26 (база): (от, до, радиус, тон). Порядок - дальняя
# нога (его левая, справа на картинке) раньше: у фигуры лицом вниз-вправо к камере ближе правый бок
KNEEL_CAPS = [
    ((16.6, 25.4), (23.0, 24.6), 2.1, (34, 34, 38)),     # левое бедро вперёд к колену
    ((23.0, 24.6), (19.8, 30.4), 1.7, (34, 34, 38)),     # левая голень вниз к ботинку
    ((19.0, 30.7), (21.6, 31.4), 1.2, (16, 16, 18)),     # левый ботинок на земле
    ((14.4, 25.6), (15.2, 31.6), 2.1, (34, 34, 38)),     # правое бедро вниз к колену на земле
    ((15.2, 31.6), (11.0, 30.2), 1.6, (34, 34, 38)),     # правая голень назад по земле
    ((11.0, 30.2), (9.4, 30.4), 1.4, (16, 16, 18)),      # правый ботинок слева
]


def legs_caps():
    """Ноги приседа цилиндрами со светом сверху-слева (эскиз позы для холста, не эталон формы, R-208)."""
    import cv2
    W, H = CELL
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32) / Z + 0.5 / Z
    rgb = np.zeros((H, W, 3), np.float32)
    al = np.zeros((H, W), np.float32)
    L = np.asarray((-0.6, -0.8), np.float32)
    for (x0, y0), (x1, y1), r, tone in KNEEL_CAPS:
        vx, vy = x1 - x0, y1 - y0
        t = np.clip(((xx - x0) * vx + (yy - y0) * vy) / (vx * vx + vy * vy), 0, 1)
        dx, dy = xx - (x0 + t * vx), yy - (y0 + t * vy)
        dist = np.sqrt(dx * dx + dy * dy)
        inside = dist < r
        shade = 0.5 + 0.5 * (dx * L[0] + dy * L[1]) / r
        col = np.asarray(tone, np.float32)[None, None, :] * (0.55 + 0.9 * shade[..., None])
        rgb = np.where(inside[..., None], col, rgb)
        al = np.maximum(al, inside.astype(np.float32))
    sg = 0.15 * Z
    am = cv2.GaussianBlur(al, (0, 0), sg)
    rgb = cv2.GaussianBlur(rgb * al[..., None], (0, 0), sg) / np.maximum(am[..., None], 1e-4)
    return np.clip(rgb, 0, 255), np.clip(am * 1.5 - 0.25, 0, 1)


def canvas_kneel(fa, lit=False, caps=False):
    rgb, a = fa
    W, H = CELL
    yy = np.arange(H)[:, None] * np.ones((1, W))
    hem = hem_y()
    up_a = a * (yy < hem * Z)
    d = KNEEL_DY * Z
    up_rgb, up_a = shift_y(rgb, d), shift_y(up_a, d)
    l_rgb, l_a = legs_caps() if caps else legs_sketch(lit)
    c_rgb, c_a = af.over(l_rgb, l_a, up_rgb, up_a)
    m = yy >= (hem + KNEEL_DY - 1.5) * Z
    return to_ctx(c_rgb, c_a), tokens(m)


def canvases():
    fa = fa_clean32()
    return {"hands": canvas_hands(fa), "aim": canvas_aim(fa), "kneel": canvas_kneel(fa),
            "kneel2": canvas_kneel(fa, lit=True), "kneel3": canvas_kneel(fa, caps=True)}


def cmd_prep(a):
    os.makedirs(OUT, exist_ok=True)
    cv = canvases()
    tiles = []
    for name in JOBS:
        ctx, tok = cv[name]
        ctx.save(os.path.join(OUT, "ctx_%s.png" % name))
        view = np.asarray(ctx).astype(np.float32)
        big = np.kron(tok, np.ones((T, T)))
        view = view * (1 - 0.35 * big[..., None]) + np.asarray((40, 90, 255)) * 0.35 * big[..., None]
        tiles.append(Image.fromarray(view.astype(np.uint8)))
        print("%s: токенов в маске %d из %d" % (name, int(tok.sum()), tok.size))
    w, h = tiles[0].size
    sheet = Image.new("RGB", (len(tiles) * (w + 10), h), (24, 24, 24))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * (w + 10), 0))
    sheet.resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS).save(os.path.join(OUT, "ctx_sheet.png"))
    print("сдвиг кисти в прицеле (база): (%.2f, %.2f)" % aim_shift())


# ---------------------------------------------------------------- модель

def cmd_render(a):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ.setdefault("HF_HOME", a.models)
    os.environ.setdefault("HF_HUB_CACHE", os.path.join(a.models, "hub"))
    import unit_parts as uparts
    uparts.STEPS = af.STEPS
    names = a.jobs.split(",")
    cv = canvases()
    ref = Image.open(af.REF).convert("RGB")
    prompts = [head() + PROMPTS[n] + TAIL for n in names]
    paint = uparts.Inpainter(a.models, [(cv[n][0], ref, p) for n, p in zip(names, prompts)])
    raw_dir = os.path.join(OUT, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    for i, n in enumerate(names):
        ctx, tok = cv[n]
        for seed in [int(x) for x in a.seeds.split(",")]:
            tag = "%s.r%d" % (n, seed)
            t0 = time.time()
            raw, log = paint.run(i, ctx, tok, seed, af.START)
            raw.save(os.path.join(raw_dir, tag + ".png"))
            rec = {"job": n, "seed": seed, "start": af.START, "steps": af.STEPS, "prompt": prompts[i],
                   "seconds": round(time.time() - t0, 1), "ref": os.path.relpath(af.REF, af.ROOT), "log": log}
            with open(os.path.join(raw_dir, tag + ".json"), "w", encoding=ENC) as f:
                json.dump(rec, f, ensure_ascii=False, indent=1)
            print("%s: %.0f с" % (tag, rec["seconds"]), flush=True)


# ---------------------------------------------------------------- сборка

def raw_cell(path):
    rgb, a, _p = af.f_a_cell(path)
    return rgb, a


def fixed_raw(seed):
    """Ответ 5401 с кистями из ответа hands (мягкий шов 4 пикселя x32): дальше его чистит agent_full build."""
    import cv2
    raw0 = np.asarray(Image.open(RAW0).convert("RGB")).astype(np.float32)
    h = np.asarray(Image.open(os.path.join(OUT, "raw", "hands.r%d.png" % seed)).convert("RGB")).astype(np.float32)
    m = cv2.GaussianBlur(crop(hand_zone()).astype(np.float32), (0, 0), 4.0)[..., None]
    out = h * m + raw0 * (1 - m)
    path = os.path.join(OUT, "raw", "ak_hands.r%d.png" % seed)
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(path)
    return path


def x4(rgb32, a32):
    return af.down(rgb32, a32, Z // 4)


def ld(path):
    return af.load_rgba(path)


def stack(layers, offs=None):
    """Слои x4 со сдвигами в пикселях базы (dx, dy)."""
    rgb = np.zeros((160, 128, 3), np.float32)
    al = np.zeros((160, 128), np.float32)
    for i, (r, a) in enumerate(layers):
        dx, dy = (offs or {}).get(i, (0, 0))
        if dx or dy:
            r2 = np.zeros_like(r)
            a2 = np.zeros_like(a)
            sx, sy = int(dx * 4), int(dy * 4)
            r2[sy:, sx:] = r[:160 - sy, :128 - sx]
            a2[sy:, sx:] = a[:160 - sy, :128 - sx]
            r, a = r2, a2
        rgb, al = af.over(rgb, al, r, a)
    return rgb, al


def holes(ref_a, al, name):
    import cv2
    hole = ((ref_a > 0.5) & (al < 0.5)).astype(np.uint8)
    n, _lab, st, cen = cv2.connectedComponentsWithStats(hole, connectivity=8)
    spots = ["%d@(%.1f,%.1f)" % (st[i, cv2.CC_STAT_AREA], cen[i][0] / 4, cen[i][1] / 4) for i in range(1, n)]
    print("%s: дырок %d пикселей x4 (фигура %d); пятна: %s" % (name, int(hole.sum()), int((ref_a > 0.5).sum()),
                                                              " ".join(spots) or "нет"))
    return hole > 0


def cmd_build(a):
    import cv2
    os.makedirs(OUT, exist_ok=True)
    pack0 = os.path.join(af.OUT, "pack")
    # 1. кисти: стоящая поза пересобирается agent_full из ответа 5401 с новыми кистями (та же чистка автомата)
    keep_old = os.path.join(OUT, "pack_before_hands")
    if not os.path.isdir(keep_old):
        shutil.copytree(pack0, keep_old)
    raw_h = fixed_raw(a.hands)
    r = subprocess.run([sys.executable, os.path.join(HERE, "agent_full.py"), "build", "--pick", "5401",
                        "--raw", raw_h], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout.strip())
    if r.returncode:
        raise SystemExit(r.stderr)
    fr = {n: ld(os.path.join(pack0, "GOV_1.PCK", "%d.png" % n)) for n in (2, 10, 18, 34, 242, 250)}
    g2 = ld(os.path.join(pack0, "HANDOB.PCK", "%d.png" % af.HANDOB_FRAME))
    # 2. автомат прицела: кадр направления 4 (в позе прицела движок сдвигает его на AIM_OFF)
    g4 = x4(*gun_at(BUTT4, MUZZLE4, Z))
    g4_aim = x4(*gun_at(*aim_gun_pts(), scale=Z))
    # 3. рука прицела 258 из ответа aim
    a_rgb, a_a = raw_cell(os.path.join(OUT, "raw", "aim.r%d.png" % a.aim))
    ns = grow(zone(shift_arm(af.NA)), Z // 8) & (a_a > 0.05)
    junk = af.gun_colour(a_rgb, zone(shift_arm(af.NA_CUFF)).astype(np.float32)) & ns
    print("рука прицела: пикселей цвета оружия x32 %d (из %d)" % (int(junk.sum()), int(ns.sum())))
    a4_rgb, a4_a = x4(a_rgb, a_a)
    ns4 = x4(np.zeros(ns.shape + (3,), np.float32), (ns & ~junk).astype(np.float32))[1] > 0.5
    fr[AIM_ARM] = (a4_rgb, a4_a * ns4)
    # просветы прицела против цельной фигуры aim: в 242 (нижний слой, под торсом и рукой)
    aim_ref = np.maximum(a4_a, g4_aim[1])
    nog = stack([fr[242], fr[18], fr[34], fr[AIM_ARM]])[1] > 0.5
    close = cv2.morphologyEx(nog.astype(np.uint8), cv2.MORPH_CLOSE,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    gap = (a4_a > 0.5) & ~nog & close
    c242, a242 = fr[242]
    fr[242] = (np.where(gap[..., None], a4_rgb, c242), np.where(gap, a4_a, a242))
    print("просветов прицела закрыто кадром 242: %d пикселей x4" % int(gap.sum()))
    # 4. ноги приседа 26 из ответа kneel: ниже полы пиджака (с перекрытием под торс), у рук - только под полой
    k_rgb, k_a = raw_cell(os.path.join(OUT, "raw", "%s.r%d.png" % (a.kneel_job, a.kneel)))
    k4_rgb, k4_a = x4(k_rgb, k_a)
    hem4 = (hem_y() + KNEEL_DY) * 4
    yy = np.arange(160)[:, None] * np.ones((1, 128))
    fit = af.Fit()
    arms = np.zeros((160, 128), bool)
    for pts in (fit.base(af.NB), fit.base(af.FB), af.NA_TIGHT, af.FA):
        arms |= zone(pts, 4, KNEEL_DY)
    kd = {0: (0, KNEEL_DY), 2: (0, KNEEL_DY), 3: (0, KNEEL_DY)}
    legs = (yy >= hem4 - af.LEG_OVERLAP * 4) & ~((yy < hem4) & grow(arms, 2))
    # поднятое бедро уходит выше полы пиджака: там ноги - всё, что не закрыто торсом и руками позы с AK (с запасом
    # в 2 пикселя): в ответе kneel руки - из этой позы. Руки без оружия не исключают: дальняя 2 лежит под ногами,
    # ближняя 10 поверх них
    cover = stack([fr[242], fr[34], fr[250]], {0: (0, KNEEL_DY), 1: (0, KNEEL_DY), 2: (0, KNEEL_DY)})[1] > 0.3
    legs |= (yy >= (hem_y() + KNEEL_DY - 4) * 4) & ~grow(cover, 2)
    # тень на полу, которую модель рисует под фигурой: серое светлее брюк (брюки и ботинки темнее 60)
    lum = (k4_rgb * np.asarray((0.3, 0.59, 0.11), np.float32)).sum(axis=2)
    sat = k4_rgb.max(axis=2) - k4_rgb.min(axis=2)
    shade = np.where(sat < 16, np.clip((78.0 - lum) / 12.0, 0, 1), 1.0)
    print("тень пола в ответе приседа: снято %d пикселей x4" % int(((shade < 0.5) & legs & (k4_a > 0.3)).sum()))
    fr[KNEEL_LEGS] = (k4_rgb, k4_a * legs * shade)
    nog = stack([fr[242], fr[KNEEL_LEGS], fr[34], fr[250]], kd)[1] > 0.5
    close = cv2.morphologyEx(nog.astype(np.uint8), cv2.MORPH_CLOSE,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0
    gap = (k4_a > 0.5) & ~nog & close & (yy >= hem4 - af.LEG_OVERLAP * 4)
    fr[KNEEL_LEGS] = (k4_rgb, np.where(gap, k4_a, fr[KNEEL_LEGS][1]))
    print("просветов приседа закрыто кадром 26: %d пикселей x4" % int(gap.sum()))
    # 5. пак
    pack = os.path.join(OUT, "pack")
    for sub in ("GOV_1.PCK", "HANDOB.PCK"):
        os.makedirs(os.path.join(pack, sub), exist_ok=True)
    for n, (rgb, al) in fr.items():
        af.save_rgba(af.edge_fill(rgb, al), al, os.path.join(pack, "GOV_1.PCK", "%d.png" % n))
    af.save_rgba(*g2, os.path.join(pack, "HANDOB.PCK", "%d.png" % af.HANDOB_FRAME))
    af.save_rgba(af.edge_fill(*g4), g4[1], os.path.join(pack, "HANDOB.PCK", "%d.png" % AIM_FRAME))
    with open(os.path.join(pack, "GOV_1.PCK", "color.txt"), "w", encoding="utf-8-sig") as f:
        f.write("colorAuthority: pack\nframes: %s\n" % " ".join(str(n) for n in sorted(fr)))
    with open(os.path.join(pack, "HANDOB.PCK", "color.txt"), "w", encoding="utf-8-sig") as f:
        f.write("colorAuthority: pack\nframes: %d %d\n" % (af.HANDOB_FRAME, AIM_FRAME))
    info = {"hands": a.hands, "aim": a.aim, "kneel": a.kneel, "kneel_job": a.kneel_job, "aim_shift": [round(v, 2) for v in aim_shift()],
            "aim_gun": aim_gun_pts(), "hem_kneel_x4": round(hem4, 1)}
    with open(os.path.join(pack, "build.json"), "w", encoding=ENC) as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    print(info)
    if a.mod:
        for sub in ("GOV_1.PCK", "HANDOB.PCK"):
            dst = os.path.join(a.mod, "hd", sub)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(os.path.join(pack, sub), dst)
        print("в мод:", a.mod)
    # 6. дырки против цельных фигур тех же поз
    holes(aim_ref, stack([fr[242], fr[18], fr[34], g4, fr[AIM_ARM]], {3: AIM_OFF})[1], "целится с AK")
    holes(k4_a, stack([fr[242], fr[KNEEL_LEGS], fr[34], fr[250]], kd)[1], "присел, руки AK без оружия")
    sheet(fr, g2, g4)


POSES = [
    ("стоит", lambda f, g2, g4: ([f[2], f[18], f[34], f[10]], {})),
    ("стоит, AK", lambda f, g2, g4: ([f[242], f[18], f[34], g2, f[250]], {})),
    ("целится, AK", lambda f, g2, g4: ([f[242], f[18], f[34], g4, f[AIM_ARM]], {3: AIM_OFF})),
    ("присел", lambda f, g2, g4: ([f[2], f[KNEEL_LEGS], f[34], f[10]], {0: (0, 4), 2: (0, 4), 3: (0, 4)})),
    ("присел, AK", lambda f, g2, g4: ([f[242], f[KNEEL_LEGS], f[34], g2, f[250]],
                                      {0: (0, 4), 2: (0, 4), 3: (0, 4), 4: (0, 4)})),
    ("целится с колена, AK", lambda f, g2, g4: ([f[242], f[KNEEL_LEGS], f[34], g4, f[AIM_ARM]],
                                                {0: (0, 4), 2: (0, 4), 3: (7, 4), 4: (0, 4)})),
    ("руки AK без оружия", lambda f, g2, g4: ([f[242], f[18], f[34], f[250]], {})),
    ("руки прицела без оружия", lambda f, g2, g4: ([f[242], f[18], f[34], f[AIM_ARM]], {})),
    ("стоит, Battle Rifle", lambda f, g2, g4: ([f[242], f[18], f[34], af.battle_rifle_x4(), f[250]], {})),
]


def sheet(fr, g2, g4, path=None, k=3):
    """Позы целиком: игровой размер (пак x4 1:1) и увеличение x k, на полу боя (тёмная плитка)."""
    f = ImageFont.truetype(af.FONT, 14)
    cw = 128 + 8 + 128 * k
    im = Image.new("RGB", (len(POSES) * (cw + 14), 160 * k + 30), (24, 24, 24))
    d = ImageDraw.Draw(im)
    for i, (t, fn) in enumerate(POSES):
        layers, offs = fn(fr, g2, g4)
        r, a = stack(layers, offs)
        bg = np.zeros((160, 128, 3), np.float32) + (np.indices((160, 128)).sum(0) // 8 % 2)[..., None] * 10 + 58
        c = Image.fromarray(np.clip(r * a[..., None] + bg * (1 - a[..., None]), 0, 255).astype(np.uint8))
        x = i * (cw + 14)
        im.paste(c, (x, 30))
        im.paste(c.resize((128 * k, 160 * k), Image.NEAREST), (x + 136, 30))
        d.text((x + 2, 8), t, fill=(230, 230, 230), font=f)
    im.save(path or os.path.join(OUT, "sheet_poses.png"))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prep")
    r = sub.add_parser("render")
    r.add_argument("--models", default=os.environ.get("HD_MODELS", "E:\\models"))
    r.add_argument("--seeds", default="5501,5502,5503")
    r.add_argument("--jobs", default=",".join(JOBS))
    b = sub.add_parser("build")
    b.add_argument("--hands", type=int, required=True)
    b.add_argument("--aim", type=int, required=True)
    b.add_argument("--kneel", type=int, required=True)
    b.add_argument("--kneel-job", default="kneel2", help="kneel (v1) или kneel2 (эскиз со светом)")
    b.add_argument("--mod", default="", help="папка тестового мода: hd/GOV_1.PCK и hd/HANDOB.PCK заменяются")
    a = ap.parse_args()
    {"prep": cmd_prep, "render": cmd_render, "build": cmd_build}[a.cmd](a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
