#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот HD-частей бойца GOV_4, направление 3: пять кадров листа, каждый перерисован на собранном бойце.

Боец в бою - стопка кадров 32x40 (drawRoutine0, unit_pilot.parts): ноги 19, торс 35, левая рука 243, правая
251 (стоит, двуручное) и 259 (целится), поверх - кадр HANDOB. Ноги и торс общие с позами без оружия, поэтому
каждая часть обязана быть целой там, где её закрывают соседи.

Как рисуется часть P (поправки специалиста 03.10):
  * холст - собранная поза, в которой P стоит ПОСЛЕДНЕЙ (поверх всех): модель видит P целиком, плечо, соседей
    и оружие у кисти; соседи - уже готовые новые кадры, иначе нынешний пак; HANDOB - xBRZ (только контекст);
  * Edit-2511 + Lightning, картинка 1 - этот холст, картинка 2 - эталон Vitali (облик и манера, не поза, R-211);
  * перерисовывается только маска P: латенты вне маски на каждом шаге заменяются зашумлённым холстом того же
    уровня шума (как QwenImageInpaintPipeline), на последнем - чистым. Шаги, у которых шум выше --start,
    целиком берутся с холста: это сила правки (структура нынешнего пака держит позу);
  * маска - силуэт P линиями (photo_base.sil_x4, R-121), расширенный на токен (16 пикселей холста);
  * в кадр идёт только P: альфа - его силуэт линиями, кромка - цвет внутренних соседей (R-089).
Прежде чем резать, проверяется ответ модели: краска за силуэтом там, где на холсте была подложка (кисть
длиннее оригинала - её срежет), и подложка внутри силуэта (дыры) - числа в part.json и контур на листе.

    py -3.13 tools/hdart/unit_parts.py prep        # входы, маски, лист - без модели
    py -3.13 tools/gpuq.py add --name unit_parts_gov4 -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe \
        E:/OpenXCom/tools/hdart/unit_parts.py render
    py -3.13 tools/hdart/unit_parts.py sheets      # сборки: оригинал | нынешний HD | новый HD, другое оружие

Выход art/units/pilot-gov4/parts/: <кадр>.ctx.png (картинка 1), <кадр>.mask.png, <кадр>.raw.png (ответ),
<кадр>.png (кадр 128x160 RGBA), <кадр>.json, листы sheet_*.png.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFilter   # noqa: E402

import unit_pilot as up                 # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join(up.OUT, "parts")
REF = os.path.join(up.OUT, "reference", "d3_p1.png")
OTHER_GUN = os.path.join(up.PZ, "Piratez", "Resources", "HANDOB", "BattleRifle.png")  # STR_BATTLE_RIFLE, 768, twoHanded
D = 3
PANEL = (118, 120, 124)                 # нейтральная подложка холста (R-089: не цвет тела)
TOKEN = 16                              # пикселей холста на токен латента (VAE 8 x упаковка 2x2)
MP = 1.0e6
SEED = 5300
START = 0.9                             # шаги с шумом не ниже этого целиком с холста (сила правки)
STEPS = 8
# (кадр листа, поза для холста, что это - для промпта)
# Части называются МЕСТОМ на картинке: «правая рука» модель читает как руку справа на картинке, а это левая
# рука бойца (кадр 259 первого прогона вернулся без единого изменения - модель правила не ту руку).
# В руках - только рукав, кожа и кулак: оружие - отдельный кадр поверх или под рукой, и деталь оружия в кадре
# руки останется при любом другом оружии (первый прогон: цевьё АК в 243, рукоять в 251).
ARM = (" Inside the outline of this arm draw only the sleeve, the skin and the hand closed into a fist; never draw "
       "any part of the rifle inside the arm - the rifle is a separate layer. The arm fills its whole outline in "
       "<image1>, as thick as there.")
PARTS = [
    (19, 1, "the legs and boots (the lower half of the figure, wide stance, feet turned outwards)",
     " The legs and boots fill their whole outline in <image1>: the boots as wide and as far apart as there."),
    (35, 1, "the torso, chest, shoulders and head (the middle of the figure)", ""),
    (243, 1, "the arm on the right side of the picture (the soldier's left arm), bent down to the rifle", ARM),
    (251, 1, "the arm on the left side of the picture (the soldier's right arm), bent down to the hip", ARM),
    (259, 2, "the arm on the left side of the picture (the soldier's right arm), raised and bent to aim the rifle",
     ARM),
]
PROMPT = ("<image1> is a soldier figure from a tactical game seen from above at the fixed isometric camera, on a "
          "flat grey panel: " + up.WHO + up.GUN + ". Repaint the whole figure of <image1> as a detailed "
          "hand-painted digital illustration in the manner of <image2>: the same face, hair, sunglasses, black "
          "flight coverall, red patches, boots and rifle as the woman in <image2>; the orange blobs of the arms "
          "become black sleeves and bare hands. Take particular care of {what}. Natural anatomy, clean sharp "
          "edges, light from the upper left. Keep exactly the pose, silhouette, size, camera angle and position of every part of "
          "<image1>; the pose comes only from <image1>, never from <image2>. Keep the rifle where it is. "
          "No pixel art, no outlines, no text.{extra}")
# Холст без оружия (--no-item): у 243 все прогоны с АК на холсте давали дерево или рукоять под кулаком -
# модель дорисовывает в кисть то, что видит рядом. Оружие из промпта тоже убирается (в up.GUN - деревянное цевьё).
BARE = (" There is no weapon anywhere in <image1> and none must be drawn: the hand is an empty closed fist with "
        "nothing in it - no wood, no stock, no grip, no metal.")
POSE_PAIR = (1, 2)                      # позы рамки холста и листов (up.POSES)
NO_CASE = False                         # силуэт кадров левой руки стоя - без чемодана (unit_turnaround.drop_case)
TITLE = "GOV_4, направление 3"

# --unit agent (специалист 05.10): игровой пилот на удачном листе AGENT (art/units/turnaround, bv2c), направление 2.
# Лист GOV_1 (броня GOVT_ARMOR_P1: drawingRoutine 0, без групп перекраски и selectUnitSprite), торс мужской
# (BattleUnit.cpp:493 - у врага пол всегда мужской, forcedTorso нет). Эталон - клетка 2 листа bv2c (одна фигура,
# R-218). Чемодан кадра 2 не рисуется (Vitali 04.10: без чемодана): силуэт кадра 2 - после drop_case.
AGENT_OUT = os.path.join(up.ROOT, "art", "units", "pilot-agent")
AGENT_SHEET_SRC = os.path.join(up.ROOT, "art", "units", "turnaround", "STR_GOVT_AGENT", "raw_bv2c.s5200.png")
AGENT_WHO = ("a male government secret agent with short brown hair and dark sunglasses, in a black business suit "
             "with a white shirt collar and a black tie, black shoes")
AGENT_ARM = (" Inside the outline of this arm draw only the black suit sleeve, a thin white shirt cuff and the bare "
             "hand closed into a fist. The arm fills its whole outline in <image1>, as thick as there.")
AGENT_PARTS = [
    (18, 0, "the legs and black shoes (the lower half of the figure)",
     " The legs and shoes fill their whole outline in <image1>: the shoes as wide and as far apart as there."),
    (34, 0, "the torso, shoulders and head with the face and sunglasses (the upper middle of the figure)", ""),
    (2, 0, "the arm on the right side of the picture (the agent's left arm), hanging down by the body, the hand "
     "empty, nothing carried", AGENT_ARM),
    (10, 0, "the arm on the left side of the picture (the agent's right arm), hanging down", AGENT_ARM),
    (242, 1, "the arm on the right side of the picture (the agent's left arm), bent forward, the fist in front of "
     "the waist", AGENT_ARM),
    (250, 1, "the arm on the left side of the picture (the agent's right arm), bent forward, the fist in front of "
     "the waist", AGENT_ARM),
]


def agent_prompt():
    import battle_view as bv
    return ("<image1> is a figure from a tactical game on a flat grey panel: " + AGENT_WHO + ", " +
            bv.facing(2) + ". " + bv.prompt_block("unit")["positive"][0].upper() +
            bv.prompt_block("unit")["positive"][1:] + ". Repaint the whole figure of <image1> as a detailed "
            "hand-painted digital illustration in the manner of <image2>: the same face, short brown hair, dark "
            "sunglasses, black suit, white shirt collar, black tie and black shoes as the man in <image2>; the orange "
            "blobs of the hands become bare hands. Take particular care of {what}. Natural anatomy, clean sharp "
            "edges. Keep exactly the pose, silhouette, size and position of every part of <image1>; the pose comes "
            "only from <image1>, never from <image2>. No pixel art, no outlines, no text.{extra}")


def use_unit(name):
    """Профиль: gov4 (как было) или agent. Ставит лист и пак для up.Sources и константы пилота."""
    global D, OUT, REF, PARTS, PROMPT, POSE_PAIR, NO_CASE, TITLE
    if name == "gov4":
        return
    up.SHEET = os.path.join(up.PZ, "Piratez", "Resources", "Sprites", "GOV_1.png")
    up.PACK = os.path.join(up.PZ, "hd", "hd", "GOV_1.PCK", "pack.hdp")
    D, OUT, PARTS, POSE_PAIR, NO_CASE = 2, os.path.join(AGENT_OUT, "parts"), AGENT_PARTS, (0, 1), True
    REF = os.path.join(AGENT_OUT, "reference", "agent_bv2c_d2.png")
    PROMPT = agent_prompt()
    TITLE = "STR_GOVT_AGENT (GOV_1), направление 2"
    if not os.path.exists(REF):
        # клетка 2 (верхний ряд, третья) листа 4x2 удачного разворота - одна фигура на подложке листа
        raw = Image.open(AGENT_SHEET_SRC).convert("RGB")
        cw, ch = raw.width // 4, raw.height // 2
        os.makedirs(os.path.dirname(REF), exist_ok=True)
        raw.crop((2 * cw, 0, 3 * cw, ch)).save(REF)


def sources():
    """up.Sources плюс unit_sil - кадры для силуэта части (без чемодана при NO_CASE)."""
    s = up.Sources()
    s.unit_sil = list(s.unit)
    if NO_CASE:
        import unit_turnaround as ut
        ut.drop_case(s.unit_sil, s.pal)
    return s


def cut_case(s, n, im):
    """Кадр пака части, у которой силуэт без чемодана, обрезается по этому силуэту (x4 nearest)."""
    if im is None or not np.any(s.unit_sil[n] != s.unit[n]):
        return im
    keep = np.kron(s.unit_sil[n] > 0, np.ones((4, 4), bool))
    a = np.asarray(im).copy()
    a[..., 3] = np.where(keep, a[..., 3], 0)
    return Image.fromarray(a, "RGBA")


def bare_prompt(prompt):
    for a, b in ((up.GUN, ""), (" Keep the rifle where it is.", ""), ("boots and rifle as", "and boots as"),
                 (", bent down to the rifle", ", bent down"), (" to aim the rifle", ""),
                 ("; never draw any part of the rifle inside the arm - the rifle is a separate layer.", ".")):
        prompt = prompt.replace(a, b)
    return prompt + BARE


# ---------------------------------------------------------------- холст

def item_smooth(s, src):
    """Кадр HANDOB x4 через xBRZ - только для контекста модели (в игре он nearest)."""
    import sprite_scale
    idx = s.ak[src[1]]
    if not idx.any():
        return None
    a = np.asarray(up.rgba(idx, s.pal), np.float32)
    big = sprite_scale.xbrz_scale(a[None], 4)[0]
    return Image.fromarray(np.clip(big + 0.5, 0, 255).astype(np.uint8), "RGBA")


def blur(a, r):
    """Почти гаусс: три прохода скользящего среднего шириной 2r+1 по обеим осям (без scipy)."""
    out = a.astype(np.float32)
    for ax in (0, 1):
        for _ in range(3):
            pad = [(0, 0)] * out.ndim
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(out, pad, mode="edge"), axis=ax)
            n = out.shape[ax]
            out = (np.take(c, range(2 * r + 1, 2 * r + 1 + n), axis=ax) - np.take(c, range(0, n), axis=ax)) / (2 * r + 1)
    return out


def ycc(rgb):
    y = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    return y, rgb - y[..., None]


def pack_in_battle_colours(s, src):
    """Кадр пака для холста: яркость и фактура - пака, цвет - оригинала. Цвет пака у GOV_4 чужой (серый
    жилет, жёлтое лицо - палитра листа, R-030), с ним модель рисовала бы не того бойца. Цветность оригинала
    размыта (r 3 пикселя x4) - лесенки nearest в цвете нет; уровень яркости - к оригиналу по крупному (r 4)."""
    hd = s.current(src, 4)
    cl = s.classic(src, 4)
    if hd is None or cl is None or src[0] != "unit" or src[1] not in s.pack:
        return hd
    h = np.asarray(hd, np.float32)
    c = np.asarray(cl, np.float32)
    ah, ac = h[..., 3:] / 255.0, c[..., 3:] / 255.0
    yh, _ = ycc(h[..., :3])
    yc, cc = ycc(c[..., :3])
    eps = 1e-3
    bah, bac = blur(ah[..., 0], 4) + eps, blur(ac[..., 0], 3) + eps
    chroma = blur(cc * ac, 3) / bac[..., None]
    lvl_c = blur(yc * ac[..., 0], 4) / (blur(ac[..., 0], 4) + eps)
    lvl_h = blur(yh * ah[..., 0], 4) / bah
    y = yh * (lvl_c + 2.0) / (lvl_h + 2.0)
    rgb = np.clip(y[..., None] + chroma, 0, 255)
    out = np.dstack([rgb, h[..., 3]])
    return Image.fromarray((out + 0.5).astype(np.uint8), "RGBA")


def load_new():
    out = {}
    for fr, _p, _w, _e in PARTS:
        p = os.path.join(OUT, "%d.png" % fr)
        if os.path.exists(p):
            out[fr] = Image.open(p).convert("RGBA")
    return out


def getter(s, new, item="smooth"):
    def get(src, k):
        kind, n = src
        if kind == "unit":
            if n in new:
                return new[n]
            return cut_case(s, n, pack_in_battle_colours(s, src) if item == "smooth" else s.current(src, k))
        return item_smooth(s, src) if item == "smooth" else s.classic(src, k)
    return get


def on_top(layers, frame):
    me = [L for L in layers if L[1] == ("unit", frame)]
    return [L for L in layers if L[1] != ("unit", frame)] + me


def frame_box(s):
    """Рамка холста в пикселях базы (по обеим позам) и размер холста модели: около MP, стороны кратны TOKEN
    (масштаб по осям может разойтись на долю процента - вырезка возвращает рамку в x4 тем же resize)."""
    m = np.zeros(((up.H + 2 * up.PAD), (up.W + 2 * up.PAD)), bool)
    for n in POSE_PAIR:
        full, _o = up.compose(s.layers(up.POSES[n], D), s.classic, 1)
        m |= np.asarray(full)[..., 3] > 0
    ys, xs = np.where(m)
    x0, y0, x1, y1 = xs.min() - 3, ys.min() - 3, xs.max() + 4, ys.max() + 4
    w, h = x1 - x0, y1 - y0
    z = (MP / (w * h)) ** 0.5
    size = (int(w * z / TOKEN) * TOKEN, int(h * z / TOKEN) * TOKEN)
    return (int(x0), int(y0), int(w), int(h)), size


def part_mask(s, pose, frame):
    """Маска P в пикселях базы холста (H+2PAD x W+2PAD)."""
    for _n, src, ox, oy in s.layers(up.POSES[pose], D):
        if src == ("unit", frame):
            m = np.zeros(((up.H + 2 * up.PAD), (up.W + 2 * up.PAD)), bool)
            idx = s.unit_sil[frame]
            m[up.PAD + oy:up.PAD + oy + up.H, up.PAD + ox:up.PAD + ox + up.W] = idx > 0
            return m, (ox, oy)
    raise SystemExit("кадра %d нет в позе %d" % (frame, pose))


def build(s, new, fr, pose, box, z, item=True):
    """Холст для модели (RGB, размер z), маска токенов (z/16), силуэт P на холсте модели; item=False - без оружия."""
    import photo_base as pb
    x0, y0, w, h = box
    L = on_top(s.layers(up.POSES[pose], D), fr)
    if not item:
        L = [x for x in L if x[1][0] == "unit"]
    can, _o = up.compose(L, getter(s, new), 4)
    flat = Image.new("RGBA", can.size, PANEL + (255,))
    flat.alpha_composite(can)
    crop = Image.new("RGB", (w * 4, h * 4), PANEL)
    crop.paste(flat.convert("RGB"), (-x0 * 4, -y0 * 4))
    ctx = crop.resize(z, Image.LANCZOS)
    m, off = part_mask(s, pose, fr)
    sil = pb.sil_x4(m)                                   # (H+2PAD)*4 x (W+2PAD)*4
    sil_c = _paste(sil, x0, y0, w, h)
    big = np.asarray(Image.fromarray((sil_c * 255).astype(np.uint8), "L").resize(z, Image.BILINEAR),
                     np.float32) / 255.0
    th, tw = z[1] // TOKEN, z[0] // TOKEN
    frac = big.reshape(th, TOKEN, tw, TOKEN).mean((1, 3))
    tok = frac > 0.02
    grow = tok.copy()                                    # +1 токен вокруг: кисть и кромка могут выйти за пиксель
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grow |= np.roll(np.roll(tok, dy, 0), dx, 1)
    return ctx, grow, big, off


def _paste(sil, x0, y0, w, h):
    out = np.zeros((h * 4, w * 4), np.float32)
    H4, W4 = sil.shape
    sx0, sy0 = max(0, x0 * 4), max(0, y0 * 4)
    sx1, sy1 = min(W4, (x0 + w) * 4), min(H4, (y0 + h) * 4)
    out[sy0 - y0 * 4:sy1 - y0 * 4, sx0 - x0 * 4:sx1 - x0 * 4] = sil[sy0:sy1, sx0:sx1]
    return out


def mask_view(ctx, tok, big):
    """Холст с маской токенов (синим) и контуром силуэта P (жёлтым) - для листа подготовки."""
    a = np.asarray(ctx, np.float32).copy()
    m = np.kron(tok, np.ones((TOKEN, TOKEN))).astype(bool)
    a[m] = a[m] * 0.6 + np.array([40, 80, 220]) * 0.4
    edge = np.asarray(Image.fromarray(((big > 0.5) * 255).astype(np.uint8)).filter(ImageFilter.FIND_EDGES)) > 0
    a[edge] = (255, 220, 0)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def reference():
    ref = Image.open(REF).convert("RGBA")
    flat = Image.new("RGBA", ref.size, PANEL + (255,))
    flat.alpha_composite(ref)
    return flat.convert("RGB")


# ---------------------------------------------------------------- вырезка

def extract(s, raw, box, z, pose, fr):
    """Ответ модели -> кадр P 128x160 RGBA: альфа - силуэт P линиями, кромка - цвет внутренних соседей."""
    import photo_base as pb
    x0, y0, w, h = box
    k4 = raw.resize((w * 4, h * 4), Image.LANCZOS)
    m, (ox, oy) = part_mask(s, pose, fr)
    full = Image.new("RGB", ((up.W + 2 * up.PAD) * 4, (up.H + 2 * up.PAD) * 4), PANEL)
    full.paste(k4, (x0 * 4, y0 * 4))
    fx, fy = (up.PAD + ox) * 4, (up.PAD + oy) * 4
    rgb = np.asarray(full.crop((fx, fy, fx + up.W * 4, fy + up.H * 4)), np.float32)
    sil = pb.sil_x4(s.unit_sil[fr] > 0)
    bg = panel_matte(rgb, sil)
    alpha = sil * (1.0 - bg)
    rgb = edge_fill(rgb, alpha)
    out = np.dstack([rgb, alpha * 255.0])
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")


def panel_matte(rgb, sil):
    """Подложка, которую модель оставила внутри силуэта (рука или нога тоньше оригинала): серые пиксели
    цвета подложки и её тени, связные с подложкой за силуэтом. Внутренние серые пятна, не касающиеся
    наружной подложки, остаются телом. Кадр выходит тоньше классического силуэта, но не шире (R-089)."""
    import photo_base as pb
    P = np.asarray(PANEL, np.float32)
    lum = rgb.mean(-1)
    chroma = rgb.max(-1) - rgb.min(-1)
    like = (chroma < 18) & (lum > 0.6 * P.mean()) & (lum < P.mean() + 20)
    lab, n = pb.label(like, 4)
    seed = np.unique(lab[like & (sil < 0.5)])
    bg = np.isin(lab, seed[seed > 0]).astype(np.float32)
    soft = np.asarray(Image.fromarray((bg * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)),
                      np.float32) / 255.0
    return np.maximum(bg, soft) * (sil > 0)


def edge_fill(rgb, alpha, inner=0.97, rounds=4):
    """Кромка (0 < альфа < inner) берёт средний цвет внутренних соседей 3x3, слоями от тела наружу (R-089):
    в кадр не попадает ни подложка, ни сосед, который стоял за краем силуэта на холсте."""
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


def content_check(ctx, raw, big):
    """До вырезки: краска за силуэтом P там, где на холсте была подложка (её срежет - кисть длиннее?),
    и подложка внутри силуэта (дыра в теле). Доли от площади силуэта."""
    c = np.asarray(ctx, np.float32)
    r = np.asarray(raw, np.float32)
    P = np.asarray(PANEL, np.float32)
    sil = big > 0.5
    ring = np.zeros_like(sil)
    for dy in range(-6, 7, 2):
        for dx in range(-6, 7, 2):
            ring |= np.roll(np.roll(sil, dy * 2, 0), dx * 2, 1)
    ring &= ~sil
    was_panel = np.abs(c - P).max(-1) < 14
    now_ink = np.abs(r - P).max(-1) > 40
    area = max(1, int(sil.sum()))
    return {"ink_outside": round(float((ring & was_panel & now_ink).sum()) / area, 4),
            "panel_inside": round(float((sil & (np.abs(r - P).max(-1) < 14)).sum()) / area, 4)}


# ---------------------------------------------------------------- модель

class Inpainter:
    """Edit-2511 + Lightning (папка снимка, R-207) с подменой латентов вне маски. Загрузка в две фазы
    (unit_turnaround.pixel_phases, R-213): текстовая модель кодирует все промпты с картинками заранее и выгружается,
    потом трансформер - без закреплённой памяти. Прежний photo_ui.Painter держал текстовую модель в pinned RAM -
    16,7 ГБ shared. Поэтому холсты всех частей одного процесса строятся до загрузки: соседи - то, что готово к старту."""

    def __init__(self, models, jobs):
        import torch
        import item_photo as ip
        import photo_ui as pu
        import unit_turnaround as ut
        ip.edit_model_check(models)
        pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
        self.torch = torch
        self.ref_of = [ref for _c, ref, _p in jobs]
        self.pipe, self.embeds = ut.pixel_phases(models, [([ctx, ref], prompt) for ctx, ref, prompt in jobs])

    def run(self, i, ctx, tok, seed, start):
        import weapons_probe5 as w5
        torch = self.torch
        pipe = self.pipe
        pe, pm = (t.to("cuda") for t in self.embeds[i])
        W, H = ctx.size
        dev = torch.device("cuda")
        with torch.no_grad():
            t = pipe.image_processor.preprocess(ctx, H, W).unsqueeze(2).to(dev, torch.bfloat16)
            lat = pipe._encode_vae_image(t, generator=None)
            C = pipe.transformer.config.in_channels // 4
            init = pipe._pack_latents(lat, 1, C, lat.shape[3], lat.shape[4])
        g = torch.Generator("cuda").manual_seed(seed + 1)
        noise = torch.randn(init.shape, generator=g, device=dev, dtype=torch.float32).to(init.dtype)
        m = torch.from_numpy(tok.reshape(1, -1, 1).astype(np.float32)).to(dev, init.dtype)
        if m.shape[1] != init.shape[1]:
            raise SystemExit("маска %d токенов, латентов %d" % (m.shape[1], init.shape[1]))
        log = []

        def cb(pp, i, _t, kw):
            x = kw["latents"]
            sg = float(pp.scheduler.sigmas[i + 1])
            noised = sg * noise + (1.0 - sg) * init
            if sg >= start:
                x = noised
                log.append("шаг %d: шум %.3f - холст целиком" % (i, sg))
            else:
                x = m * x + (1.0 - m) * noised
                log.append("шаг %d: шум %.3f - маска" % (i, sg))
            return {"latents": x}

        with torch.no_grad():
            out = pipe(image=[ctx, self.ref_of[i]], prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                       true_cfg_scale=1.0, num_inference_steps=STEPS, height=H, width=W,
                       generator=torch.Generator("cuda").manual_seed(seed),
                       callback_on_step_end=cb, callback_on_step_end_tensor_inputs=["latents"]).images[0]
        shared = w5.gpu_mem("кадр %d сид %d" % (i, seed))
        if shared > 0.5:
            raise SystemExit("ушло в shared (%.1f ГБ) - стоп" % shared)
        return out.convert("RGB"), log


# ---------------------------------------------------------------- команды

def cmd_prep(a):
    s = sources()
    os.makedirs(OUT, exist_ok=True)
    box, z = frame_box(s)
    new = load_new()
    cells = []
    for fr, pose, what, _e in PARTS:
        ctx, tok, big, off = build(s, new, fr, pose, box, z)
        ctx.save(os.path.join(OUT, "%d.ctx.png" % fr))
        Image.fromarray((np.kron(tok, np.ones((TOKEN, TOKEN))) * 255).astype(np.uint8)).save(
            os.path.join(OUT, "%d.mask.png" % fr))
        cells.append(("кадр %d (поза %d): %s" % (fr, pose, what.split(",")[0]), mask_view(ctx, tok, big)))
        print("кадр %d: холст %dx%d (%s), токенов в маске %d из %d, сдвиг %s" % (
            fr, ctx.width, ctx.height, z, int(tok.sum()), tok.size, off))
    sheet(cells, os.path.join(OUT, "sheet_prep.png"), "Холсты частей: часть поверх всех, синее - что модель "
          "перерисует, жёлтое - силуэт части (в кадр идёт только он)", scale=0.5)
    print("box", box, "z", z)


def cmd_render(a):
    os.environ["HF_HUB_OFFLINE"] = "1"
    # кэш HF - до первого импорта huggingface_hub (edit_model_check): иначе scan_cache_dir смотрит в ~/.cache
    # и pick_lora офлайн не находит Lightning
    os.environ.setdefault("HF_HOME", a.models)
    os.environ.setdefault("HF_HUB_CACHE", os.path.join(a.models, "hub"))
    s = sources()
    os.makedirs(OUT, exist_ok=True)
    box, z = frame_box(s)
    ref = reference()
    only = set(int(x) for x in a.only.split(",")) if a.only else None
    starts = [float(x) for x in a.starts.split(",")] if a.starts else [a.start]
    seeds = [int(x) for x in a.seeds.split(",")] if a.seeds else [a.seed]
    # холсты всех частей - до загрузки модели (две фазы, R-213): соседи - то, что готово к старту процесса
    todo = []
    new = load_new()
    for fr, pose, what, extra in PARTS:
        if only and fr not in only:
            continue
        mine = dict(new)
        if a.no_item:
            mine.pop(fr, None)    # прежний свой кадр несёт дерево под кулаком - на холст сама часть из пака
        own = os.path.join(a.own, "%d.png" % fr) if a.own else ""
        if own and os.path.exists(own):
            mine[fr] = Image.open(own).convert("RGBA")   # свой кадр, исправленный до рендера (цвет кистей, штрих)
        elif own:
            raise SystemExit("нет исправленного кадра %s" % own)
        ctx, tok, big, off = build(s, mine, fr, pose, box, z, item=not a.no_item)
        ctx.save(os.path.join(OUT, "%d%s%s.ctx.png" % (fr, ".n" if a.no_item else "", ".o" if a.own else "")))
        prompt = PROMPT.format(what=what, extra=extra)
        if a.no_item:
            prompt = bare_prompt(prompt)
        todo.append((fr, pose, ctx, tok, big, prompt))
    if not todo:
        raise SystemExit("нет частей для --only %s" % a.only)
    paint = Inpainter(a.models, [(ctx, ref, prompt) for _f, _p, ctx, _t, _b, prompt in todo])
    for i, (fr, pose, ctx, tok, big, prompt) in enumerate(todo):
        for st, seed in [(st, sd) for st in starts for sd in seeds]:
            # с --variants кадр пишется как <кадр>[.n].s<сила>[.r<зерно>], основной <кадр>.png не трогается
            tag = "%d%s%s.s%02d" % (fr, ".n" if a.no_item else "", ".o" if a.own else "",
                                    round(st * 100)) if a.variants else "%d" % fr
            if a.variants and a.seeds:
                tag += ".r%d" % seed
            t0 = time.time()
            raw, log = paint.run(i, ctx, tok, seed, st)
            dt = time.time() - t0
            raw.save(os.path.join(OUT, tag + ".raw.png"))
            chk = content_check(ctx, raw, big)
            frame = extract(s, raw, box, z, pose, fr)
            frame.save(os.path.join(OUT, tag + ".png"))
            rec = {"frame": fr, "pose": up.POSES[pose][0], "dir": D, "box": box, "size": z, "seed": seed,
                   "start": st, "steps": STEPS, "prompt": prompt, "check": chk, "seconds": round(dt, 1),
                   "log": log, "ref": os.path.relpath(REF, up.ROOT),
                   "context": "часть поверх, соседи - новые/пак" + (", без оружия" if a.no_item else "")}
            with open(os.path.join(OUT, tag + ".json"), "w", encoding=ENC) as f:
                json.dump(rec, f, ensure_ascii=False, indent=1)
            print("%s: %.0f с, краска за силуэтом %.3f, подложка в силуэте %.3f" % (
                tag, dt, chk["ink_outside"], chk["panel_inside"]), flush=True)


def sheet(cells, path, title, scale=1.0, cols=None):
    f = up.font(14)
    ims = [im if scale == 1.0 else im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
           for _t, im in cells]
    cols = cols or len(ims)
    rows = (len(ims) + cols - 1) // cols
    cw = max(i.width for i in ims)
    ch = max(i.height for i in ims)
    gap, top = 10, 22
    out = Image.new("RGB", (gap + cols * (cw + gap), 30 + rows * (ch + top + gap)), (24, 24, 24))
    dr = ImageDraw.Draw(out)
    dr.text((gap, 6), title, fill=(230,) * 3, font=f)
    for i, ((t, _im), im) in enumerate(zip(cells, ims)):
        x = gap + (i % cols) * (cw + gap)
        y = 30 + (i // cols) * (ch + top + gap)
        dr.text((x, y + 2), t, fill=(220,) * 3, font=f)
        out.paste(im.convert("RGB"), (x, y + top))
    out.save(path)
    print(path, out.size)


def assemble(s, pose, get, box=None):
    """Сборка позы k=4 на полу боя; box - рамка в пикселях базы (frame_box), поле вокруг - 3 пикселя."""
    full, _o = up.compose(s.layers(up.POSES[pose], D), get, 4)
    bg = up.bg_tile(*full.size)
    bg.alpha_composite(full)
    if box:
        x0, y0, w, h = box
        bg = bg.crop(((x0 - 3) * 4, (y0 - 3) * 4, (x0 + w + 3) * 4, (y0 + h + 3) * 4))
    return bg


def cmd_sheets(a):
    s = sources()
    new = load_new()
    if not new:
        raise SystemExit("новых кадров нет: сначала render")
    box, _z = frame_box(s)
    game_new = getter(s, new, item="classic")
    rows = []
    for pose in POSE_PAIR:
        for name, get in (("оригинал", s.classic), ("нынешний HD", s.current), ("новый HD", game_new)):
            rows.append(("%s - %s" % (up.POSES[pose][0], name), assemble(s, pose, get, box)))
    sheet(rows, os.path.join(OUT, "sheet_game.png"), TITLE + ": в игровом масштабе (k=4, 1:1)", cols=3)
    big = [(t, im.resize((im.width * 3, im.height * 3), Image.NEAREST)) for t, im in rows]
    sheet(big, os.path.join(OUT, "sheet_zoom.png"), TITLE + ": увеличенно x3", cols=3)
    # части по отдельности
    parts = []
    for fr, _p, what, _e in PARTS:
        for name, im in (("оригинал", s.classic(("unit", fr), 4)), ("нынешний", s.current(("unit", fr), 4)),
                         ("новый", new.get(fr))):
            bg = up.bg_tile(up.W * 4, up.H * 4)
            if im is not None:
                bg.alpha_composite(im)
            parts.append(("%d %s" % (fr, name), bg.resize((up.W * 12, up.H * 12), Image.NEAREST)))
    sheet(parts, os.path.join(OUT, "sheet_parts.png"), "Части x3: оригинал | нынешний пак | новый", cols=6)
    # другое двуручное оружие: руки без остатков AK
    gun = up.load_frames(OTHER_GUN)
    keep = s.ak
    s.ak = gun
    try:
        rows2 = []
        for pose in POSE_PAIR:
            for name, get in (("оригинал", s.classic), ("новый HD", game_new)):
                im = assemble(s, pose, get, box)
                rows2.append(("%s, боевая винтовка - %s" % (up.POSES[pose][0], name),
                              im.resize((im.width * 3, im.height * 3), Image.NEAREST)))
        sheet(rows2, os.path.join(OUT, "sheet_other_gun.png"),
              "Те же руки с другим двуручным (HANDOB BattleRifle, STR_BATTLE_RIFLE), x3", cols=2)
    finally:
        s.ak = keep
    # руки без оружия поверх - чистые ли под ним
    arms = []
    for fr in [p[0] for p in PARTS[2:]]:
        if fr in new:
            bg = up.bg_tile(up.W * 4, up.H * 4)
            bg.alpha_composite(new[fr])
            arms.append(("кадр %d без оружия" % fr, bg.resize((up.W * 12, up.H * 12), Image.NEAREST)))
    if arms:
        sheet(arms, os.path.join(OUT, "sheet_arms_bare.png"), "Новые руки без оружия поверх, x3")


ENGINE_REF = ("src/Battlescape/UnitSprite.cpp drawRoutine0: номера 305-317 и 361-457 (ноги 16, руки 0/8, торс 32, "
              "двуручное 240/248), предмет 461-525 (HANDOB handSprite + dir, смещение 0 стоя), высота 593-601 "
              "(22 - standHeight), порядок 619-646; торс мужской - BattleUnit.cpp:493")


def cmd_map(a):
    """Шаг 1: точная карта кадров направления D - что, со смещением и в каком порядке кладёт drawRoutine0."""
    s = sources()
    os.makedirs(OUT, exist_ok=True)
    rec = {"title": TITLE, "dir": D, "engine": ENGINE_REF, "poses": []}
    md = ["# Карта кадров: %s" % TITLE, "", "Источник: " + ENGINE_REF + ".", "",
          "Кадр пака = номер кадра листа (у тел сдвига нет). Порядок - снизу вверх: следующий кладётся поверх.", ""]
    cells = []
    for pose in POSE_PAIR:
        L = s.layers(up.POSES[pose], D)
        rows = []
        md += ["## %s" % up.POSES[pose][0], "", "| # | часть | лист | кадр | offX | offY | пикселей | без чемодана |",
               "|---|---|---|---|---|---|---|---|"]
        acc = []
        for i, (name, (kind, n), ox, oy) in enumerate(L):
            idx = (s.unit if kind == "unit" else s.ak)[n]
            sil = (s.unit_sil[n] if kind == "unit" else idx)
            cut = int((idx > 0).sum() - (sil > 0).sum())
            sheet_name = os.path.basename(up.SHEET if kind == "unit" else up.HANDOB_AK)
            rows.append({"order": i, "part": name, "sheet": sheet_name, "frame": n if kind == "unit" else
                         "%d (HANDOB %d)" % (n, 352 + n), "offX": ox, "offY": oy, "pixels": int((idx > 0).sum()),
                         "case_pixels_cut": cut})
            md.append("| %d | %s | %s | %s | %d | %d | %d | %s |" % (
                i, name, sheet_name, rows[-1]["frame"], ox, oy, rows[-1]["pixels"], "-%d" % cut if cut else ""))
            acc.append(L[i])
            full, _o = up.compose(acc, s.classic, 4)
            bg = up.bg_tile(*full.size)
            bg.alpha_composite(full)
            cells.append(("%s: +%s %s" % (up.POSES[pose][0], name, rows[-1]["frame"]), bg))
        rec["poses"].append({"pose": up.POSES[pose][0], "layers": rows})
        md.append("")
    with open(os.path.join(OUT, "map.json"), "w", encoding=ENC) as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "map.md"), "w", encoding=ENC) as f:
        f.write("\n".join(md) + "\n")
    sheet(cells, os.path.join(OUT, "sheet_map.png"), TITLE + ": сборка по шагам, классика x4 (порядок движка)",
          scale=0.75, cols=5)
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--unit", choices=("gov4", "agent"), default="gov4", help="профиль пилота (по умолчанию GOV_4)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("map")
    sub.add_parser("prep")
    r = sub.add_parser("render")
    r.add_argument("--models", default=os.environ.get("HD_MODELS", "E:\\models"))
    r.add_argument("--seed", type=int, default=SEED)
    r.add_argument("--start", type=float, default=START)
    r.add_argument("--only", default="", help="кадры через запятую")
    r.add_argument("--starts", default="", help="несколько сил через запятую (с --variants)")
    r.add_argument("--seeds", default="", help="несколько зёрен через запятую (с --variants: <кадр>.s<сила>.r<зерно>)")
    r.add_argument("--variants", action="store_true", help="писать <кадр>.s<сила>.*, основной кадр не трогать")
    r.add_argument("--no-item", action="store_true", help="холст и промпт без оружия (<кадр>.n.s<сила>.*)")
    r.add_argument("--own", default="", help="папка с исправленными своими кадрами: на холст своя часть оттуда "
                   "(<кадр>[.n].o.s<сила>.*)")
    sub.add_parser("sheets")
    a = ap.parse_args()
    use_unit(a.unit)
    {"map": cmd_map, "prep": cmd_prep, "render": cmd_render, "sheets": cmd_sheets}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
