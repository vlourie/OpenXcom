"""Пилот конвейера тел куклы (docs/research/doll-pipeline-2026-11-03.md, Vitali 03.11 «да, пилот»).

Тот же набор, что у doll_ctl_pilot 20.10 (UBERGAL, M0/M57/M51, ADVENTURER и AMAZON), чтобы сравнение было честным.
Отличия от ctl-пилота - три лечения трёх бед разбора:
  1. внешность уплывала (белое каре -> русые): inpaint VideoX-Fun обнуляет картинку внутри маски, модель видела
     только серую карту. Теперь цвет идёт и картинкой - старт из латентов B2, зашумлённых до sigma0 (img2img поверх
     inpaint, strength), - и словами: паспорт внешности (кожа, волосы, приметы - с классики в палитре игры);
  2. шов вещи и тела: вещи брони рисуются ПОВЕРХ готового HD-тела и головы (маска - только вещи), тело и голова
     в рисунке брони не перерисовываются - из него вырезаются только вещи;
  3. лицо, причёска и шея - отдельный кадр x20 (вырезка 40x40 базы от макушки), старт - сглаженная классика, маска -
     hair_zone: хвосты, косы и бусы лежат в слое тела, поэтому слой тела берёт их из этого же кадра (R-595).
Альфа каждого слоя - силуэт классики x4 (ws.sil4), не ответ модели (R-089, R-208).

Каждый рабочий процесс рисует подряд все недостающие кадры; падение (память карты) - выход 75, родитель запускает
новый процесс с первого недостающего кадра. Время загрузки модели и каждого кадра - в run.json (замер для оценки
конвейера, R-091).

Выход art/doll/pipe_pilot/: passports.json, raw/, layers/, sheet.png («классика x4 | ctl A 20.10 | новый»),
faces.png (головы крупно), run.json.
  py -3 tools/gpuq.py add --name doll-pipe-pilot -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe \
      E:/OpenXCom/tools/hdart/doll_pipe_pilot.py
  --dry-run - без модели (рисунок = вход), проверка входов, раскроя и листов.
"""
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")        # до импорта diffusers (R-145)
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import argparse                                     # noqa: E402
import colorsys                                     # noqa: E402
import json                                         # noqa: E402
import random                                       # noqa: E402
import subprocess                                   # noqa: E402
import time                                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter       # noqa: E402
import cv2                                          # noqa: E402

import doll_b2_render as db                         # noqa: E402
import doll_ctl_pilot as cp                         # noqa: E402
import doll_paint_pilot as pp                       # noqa: E402
import doll_photo_pilot as dp                       # noqa: E402
import wall_section as ws                           # noqa: E402

OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot")
CTL = os.path.join(db.ROOT, "art", "doll", "ctl_pilot", "layers_a")
RUN = {"steps": 40, "cfg": 4.0, "seed": 3110,
       "body": {"strength": 0.85, "control": 1.0},
       "head": {"strength": 0.75, "control": 1.0, "w": 40, "h": 40, "zoom": 20},
       "item": {"strength": 0.7, "control": 1.0, "w": 32, "h": 32, "zoom": 20},
       "armor": {"strength": 0.85, "control": 1.0, "grow8": 3}}
# стороны кадра кратны 32: иначе трансформер падает на repeat_interleave, и это видно только после загрузки модели
for _s in ("head", "item"):
    assert not (RUN[_s]["w"] * RUN[_s]["zoom"] % 32 or RUN[_s]["h"] * RUN[_s]["zoom"] % 32)
STYLE = ("Detailed hand-painted game artwork, a full-figure paper-doll portrait for the equipment screen of an X-COM-"
         "style strategy game, seen straight from the front, on a flat grey panel. Clear readable shapes, crisp "
         "edges, fine painted detail. Soft light from the upper left. No ground, no shadow, no frame, no text.")
BODY = ("{style} {who} with {skin} skin, bare smooth arms and legs, bare feet with clearly painted toes. Her hair lies only where it lies in the "
        "input, no extra locks on the chest or shoulders. {neck} {face}. A woman's figure with a full bust - "
        "never a man. She wears only minimal black underwear that any outfit covers: small round black pasties over "
        "the nipples and a narrow black thong. Keep the colours of the input exactly: the same skin colour, the same "
        "hair colour and cut. Painted detail of skin and muscles, a detailed face with clear eyes, brows and lips.")
HEAD = ("Close-up of the head and face of {who}, part of a hand-painted paper-doll portrait for an X-COM-style strategy "
        "game, seen straight from the front, soft light from the upper left. Repaint the low-resolution input in high "
        "detail without changing its design; the face stays the same size and the hairline stays where it is. "
        "Hair: {hair}. {head}{neck} Makeup: {makeup}; the bright colours around the eyes and on the lips of the input "
        "are cosmetics on bare skin: eyeshadow is soft and only on the eyelids, lipstick only on the lips, the eyes "
        "are natural and never glow, the skin around the mouth is clean. {skin_c} skin, {face}. A pretty young "
        "woman's face with smooth unlined skin and soft feminine features: clear eyes with irises and highlights, "
        "neat brows, a small nose, soft lips. Dark spots on the skin of the input are soft shading only. Painted "
        "game art, not a photo.")
ITEM = ("Close-up of the bare {skin} skin of {who}, part of a hand-painted paper-doll portrait for an X-COM-style "
        "strategy game, soft light from the upper left. Repaint the low-resolution mark of the input in high detail, in "
        "the same place, the same size and the same colours: {text}. The skin around it stays as it is in the input. "
        "Painted game art, not a photo.")
ARMOR = ("{style} {what}. Her skin, face and hair stay exactly as in the input; paint the clothing and gear: fabric "
         "folds, leather, seams, buckles, metal. Keep the colours of every item of the input.")
NEGATIVE = (pp.NEGATIVE + ", plastic skin, doll face, identical faces, extra fingers, "
            "man, male, masculine face, beard, stubble, flat male chest, "     # M51 вышла мужчиной (пилот 03.11)
            "old woman, middle-aged, mature face, wrinkles, nasolabial folds, sagging skin, tired face, "
            "child, teenager, underage, war paint, face paint stripes, scars, face tattoo, black marks on the skin")
WHO = "a fit athletic young adult woman, 20 years old"
# Что на голове на самом деле - глазами по классике x12, с поправками Vitali 04.11 (R-591). Цвет на лице классики -
# косметика, необычное на шее - кончики волос или тень: пиксели этого не различают, поэтому слова только отсюда.
with open(os.path.join(HERE, "doll_looks.json"), encoding="utf-8-sig") as _f:
    LOOKS = json.load(_f)
# вещь, которой нет в описании внешности, - в негатив: модель дорисовывала её из пятен классики
NEG_GEAR = ((("collar", "choker"), "collar, choker, neck guard, neck armour, scarf, high neck"),
            (("helmet",), "helmet, hard hat, wide-brimmed hat, cap, hood, headgear"),
            (("mask",), "mask, face mask, balaclava"),
            (("visor", "glasses", "pince-nez"), "goggles, visor, glasses, eyewear"),
            (("eyepatch",), "eyepatch"),
            (("implant",), "cybernetic eye, monocle, eyepiece"))
# кадр тела вещей не рисует: их кладёт кадр вещи на своё место (R-596); пластины и подошвы - F37, F45 серии #1095
NEG_BODY = (", tattoo, body art, bracelet, wristband, armband, bracer, gloves, armor plates, segmented body, robot, "
            "boots, shoes, sandals, soles")
# лицо UBERGAL на холсте 320x200 (x0, y0, x1, y1), один на все внешности: глаза - строка 53, подбородок - 60
FACE_BOX = (75, 50, 82, 60)
FACE_CX = 78
EYE_ROW = 53
# места на теле UBERGAL (база 320x200); другая раса задаёт свои: doll_race_bodies.py
THONG = [(67.5, 85), (79, 91), (90.5, 85), (90.5, 86.5), (81.5, 94), (80, 97.5), (78, 97.5), (76.5, 94), (67.5, 86.5)]
HAND_ROWS, HAND_X = (84, 100), (58, 100)
STRAP_ROWS = (82, 96)
CHEST_LINES = ((71.0, 64, 74), (91.5, 66, 78))
FEET_ROW = 140
FILL_EDGES = True       # щель между рисунком и силуэтом - заливать кожей; False - её обрезает сам скрипт расы
# сколько раз внешность перекинута на новый сид: брак белья или лица после серии, сверено глазами (03.11)
RESEED = {k: 1 for k in ("F0 F2 F12 F14 F27 F40 F42 F44 F48 F52 F55 F58 M4 M7 M35 M37 M42 M48 M52 M58 "
                         "F5 M5 M6 F35 M34 M53 M8").split()}
RESEED.update({"F5": 2, "F44": 2, "F37": 1, "F45": 1, "M4": 2, "M29": 1})   # смятые ноги, пластины, подошвы, лицо (#1095)
RESEED.update({"F0": 2, "F5": 3, "F53": 1, "M4": 3, "M35": 2, "M41": 1, "M42": 2, "M57": 1})   # подошвы, царапины, лица (#1103)
RESEED.update({"F9": 1, "M36": 1, "M33": 1, "F40": 2, "M12": 1, "M40": 1, "M24": 1, "M50": 1, "F8": 1, "F35": 2, "F39": 1,
               "M23": 1, "F19": 1, "M5": 2, "F2": 2, "F14": 2, "F18": 1, "M11": 1, "M15": 1, "M18": 1, "M38": 1, "M42": 3,
               "F45": 2, "F13": 1, "M53": 2, "F25": 1, "F47": 1})   # кожа сеткой, серые блики, ступни, очки (#1108)
RESEED.update({"F35": 3, "M36": 2, "M5": 3})   # шишки и бледные пятна на ступнях (#1109)
# тела без единой вещи (сверено разницей слоёв): разница с ними - вещи классики; ключ - полурампа кожи
CLEAN_BODY = {12: "F5", 20: "M42"}
FACE_TORSO = (66, 100, 60, 98)                          # face_to_body: строки и столбцы груди, откуда цвет
FACE_LIMIT = (30.0, 45.0)                               # и насколько цвет может быть далёк от щёк: лицо, шея


# --- паспорт внешности: с классики в палитре игры, без карты --------------------------------------------------------

def hsv(rgb):
    r, g, b = (float(v) / 255 for v in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360, s, v


def hair_name(rgb):
    h, s, v = hsv(rgb)
    if s < 0.18:
        return "platinum white" if v > 0.72 else ("grey" if v > 0.35 else "black")
    if v < 0.2:
        return "black"
    if v > 0.75 and s < 0.35 and h < 70:                # кремовые и белые волосы F27, F40 звались «brown» (03.11)
        return "platinum blonde"
    if h < 15 or h >= 330:
        if s > 0.55:
            return "crimson red" if v >= 0.3 else "dark brown"
        return "dusty pink" if v > 0.6 else "auburn"    # розово-бежевые F35, M8 модель рисовала рыжими
    if h < 40:
        return "copper ginger" if s > 0.6 and v > 0.55 else ("brown" if v > 0.35 else "dark brown")
    if h < 70:
        return "golden blonde" if v > 0.6 else "dark blonde"
    if h < 170:
        return "green"
    if h < 260:
        return "blue"
    return "pink" if v > 0.7 and s < 0.6 else "purple"


def skin_name(rgb):
    h, s, v = hsv(rgb)
    if 70 <= h < 300 and s > 0.15:
        return "%s-tinted" % hair_name(rgb).split()[-1]
    if s > 0.6 and v > 0.7:
        return "bright bronze-orange"
    if v < 0.4:
        return "very dark brown"
    if v < 0.6:
        return "deep dark brown"                    # «brown» модель рисовала средним загаром (L 34-39 -> 46-55)
    if s < 0.3:
        return "pale"
    return "tanned"


def mode_colour(px):
    """Самый частый цвет среди светлых 85 % пикселей (контур тёмный)."""
    if not len(px):
        return None
    lum = px.mean(1)
    px = px[lum >= np.percentile(lum, 15)]
    q = (px // 24).astype(np.int32)
    keys, inv, cnt = np.unique(q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2], return_inverse=True, return_counts=True)
    return px[inv == cnt.argmax()].mean(0)


def colour_word(rgb):
    h, s, v = hsv(rgb)
    if v < 0.25:
        return "black"
    return hair_name(rgb).split()[-1] if s >= 0.18 else ("white" if v > 0.72 else "grey")


def gear_colour(rgb):
    """Цвет вещи: слова волос «blonde» и «ginger» про пластик и металл не говорят."""
    return {"blonde": "yellow", "ginger": "orange", "auburn": "dark red"}.get(colour_word(rgb), colour_word(rgb))


def split_gear(hair_m, idx, rgb):
    """Вещи на лице, слипшиеся с волосами в одно пятно (10 внешностей 03.11: маска на рот M42, очки на лбу F59,
    визор F42 и F57). Пятно делится по полурампам палитры: главная полурампа - волосы; другая полурампа, которая
    больше чем наполовину лежит в рамке лица или тонкой полосой во всю ширину над ней, - вещь. Рамка - FACE_BOX,
    не по пикселям кожи: у бронзовых тел на рампах кожи лежат и волосы (F52). Прядь того же оттенка, что волосы,
    - не вещь (M2). -> (маска вещей, [(пикселей, текст)])"""
    import photo_base as pb
    fx0, fy0, fx1, fy1 = FACE_BOX
    fw = fx1 - fx0
    cols = (FACE_CX, FACE_CX + 1)
    r = idx // 8
    top = np.bincount(r[hair_m], minlength=32).argmax()
    th, ts, _tv = hsv(rgb[hair_m & (r == top)].mean(0))
    groups = {}
    for h in np.unique(r[hair_m]):
        if h == top:
            continue
        sel = hair_m & (r == h)
        ys, xs = np.nonzero(sel)
        inside = ((ys >= fy0) & (ys <= fy1) & (xs >= fx0) & (xs <= fx1)).mean()
        band = ys.max() - ys.min() <= 3 and xs.max() - xs.min() >= 0.6 * fw and ys.max() < EYE_ROW
        mean = rgb[sel].mean(0)
        c = gear_colour(mean)
        gh, gs, _gv = hsv(mean)
        if band:
            c = "band:" + c
        elif inside <= 0.5 or c == "brown":
            continue                                        # бурое в лице - тени кожи и брови (M57, F37)
        elif ts > 0.25 and gs > 0.25 and min(abs(gh - th), 360 - abs(gh - th)) < 25:
            continue
        groups[c] = groups.get(c, np.zeros_like(sel)) | sel
    gm = np.zeros_like(hair_m)
    out = []
    for c, sel in groups.items():
        k = int(sel.sum())
        if k < 8:
            continue                                        # глаза и губы в пятне волос
        ys, xs = np.nonzero(sel)
        t = (ys.mean() - fy0) / float(fy1 - fy0)
        bridge = sel[:, cols[0]] | sel[:, cols[1]]          # переносица: у радужек M34 по центру пусто
        if c.startswith("band:"):
            if c == "band:black":
                continue                                    # чёрное над глазами - брови и поля шляпы (M53)
            what = "%s goggles pushed up on the forehead" % c[5:]
        elif ys.max() - ys.min() <= 3 and t < 0.55 and ys.min() <= EYE_ROW <= ys.max():   # чёлка и раскраска у глаз
            if bridge.any() and xs.min() < cols[0] and xs.max() > cols[1]:
                what = "a %s visor over the eyes" % c
            else:
                lab, n = pb.label(sel, 8)
                if c == "black" or max((lab == i).sum() for i in range(1, n + 1)) < 6:
                    continue                                # два пятна по бокам - глаза (M53, F6, F43)
                what = "a %s eyepiece over one eye" % c
        elif t >= 0.55 and k >= 15 and int(bridge[fy0 + 6:fy1 + 1].sum()) >= 3:  # закрывает рот, а не кудри (F43)
            what = "a %s mask over the mouth and jaw" % c
        else:
            continue
        gm |= sel
        out.append((k, what))
    return gm, out


def passport(files, pal, look):
    """Паспорт внешности по классике: кожа, волосы (цвет, длина - по подбородку), приметы - связные пятна не цвета
    кожи с местом на теле (соски и пах - не приметы). Лицо - признаки, записанные один раз на внешность."""
    import photo_base as pb
    body = "%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look)
    head = "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look)
    bi, hi = db.load_indices(files[body]), db.load_indices(files[head])
    bm, hm = bi != 0, hi != 0
    idx = np.where(hm, hi, bi)
    rgb = pal[idx].astype(np.float32)
    allm = bm | hm
    skin = mode_colour(pal[bi][bm].astype(np.float32))
    # метки на теле паспорт не считает: цвет и место давали «татуировку на правой руке» вместо повязки (R-596)
    # кожа - полурампы палитры (по 8 цветов), на которых нарисовано тело (у UBERGAL M0 их четыре: блик, тон и две
    # тени); тень кожи - не примета
    hy_ = np.nonzero(hm)[0]
    torso = bm.copy()
    torso[:hy_.max() + 6] = False                       # слой тела рисует и волосы - кожу считать ниже головы
    halves = np.bincount(bi[torso] // 8, minlength=32) / float(torso.sum())
    skin_halves = np.nonzero(halves >= 0.02)[0]
    odd = allm & ~np.isin(idx // 8, skin_halves) & (idx != 0)
    # контур (сосед прозрачный) - не примета
    pad = np.pad(allm, 1)
    inner = pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    odd &= inner
    # волосы: самое большое пятно в слое головы
    lab, n = pb.label(odd & hm, 8)
    sizes = [(int((lab == i).sum()), i) for i in range(1, n + 1)]
    hair_m = np.zeros_like(hm)
    if sizes:
        hair_m = lab == max(sizes)[1]
        # то же пятно цвета волос, разорванное лицом (чёлка и пряди)
        hc = rgb[hair_m].mean(0)
        hair_m |= odd & hm & (np.abs(rgb - hc).sum(-1) < 90)
    gear_m, gear = split_gear(hair_m, idx, rgb) if hair_m.any() else (np.zeros_like(hm), [])
    hair_m &= ~gear_m
    # у бронзовых тел жёлтые и платиновые волосы лежат на рампах кожи (F52, M21, F5, F12, M41) и в пятно не попали:
    # кожа головы вне лица и выше подбородка - это волосы
    fx0, fy0, fx1, fy1 = FACE_BOX
    yy, xx = np.indices(hm.shape)
    off_face = (xx < fx0 - 1) | (xx > fx1 + 2) | (yy < fy0)
    on_skin = hm & inner & np.isin(idx // 8, skin_halves) & off_face & (yy <= fy1)
    if on_skin.sum() >= 15:
        hair_m = hair_m | on_skin
    # цвет волос - без мелких чужих полурамп: золотая заколка F55, красная полоса M42
    tone_m = hair_m.copy()
    if hair_m.any():
        r_ = idx // 8
        cnt_ = np.bincount(r_[hair_m], minlength=32)
        top_ = cnt_.argmax()
        th_, ts_, _v = hsv(rgb[hair_m & (r_ == top_)].mean(0))
        for h_ in np.nonzero(cnt_)[0]:
            if h_ == top_ or cnt_[h_] >= 0.15 * hair_m.sum():
                continue
            gh_, gs_, _v = hsv(rgb[hair_m & (r_ == h_)].mean(0))
            if gs_ >= 0.25 and (ts_ < 0.18 or min(abs(gh_ - th_), 360 - abs(gh_ - th_)) > 40):
                tone_m &= r_ != h_
    hp = rgb[tone_m]
    hair = hp[hp.mean(1) >= np.median(hp.mean(1))].mean(0) if hair_m.sum() > 8 else None   # тон, не тень
    rnd = random.Random("face:" + dp.RACE + look)
    face = ", ".join([                                  # все молодые: без тяжёлых черт, хмурых взглядов и шрамов (04.11)
        rnd.choice(["an oval face", "a heart-shaped face", "a round face", "a face with high cheekbones"]),
        rnd.choice(["large", "almond-shaped", "narrow"]) + " " + rnd.choice(["brown", "dark brown", "hazel"]) + " eyes",
        rnd.choice(["a straight nose", "a small upturned nose", "a button nose"]),
        rnd.choice(["full lips", "soft lips", "a wide mouth"]),
        rnd.choice(["a confident look", "a slight smirk", "a calm look", "a wry half-smile"]),
    ])
    if look not in LOOKS:
        raise SystemExit("нет описания внешности %s в doll_looks.json: описать глазами по классике" % look)
    d = LOOKS[look]
    return {"look": look, "skin": skin_name(skin), "skin_rgb": [int(v) for v in skin],
            "hair": d["hair"], "hair_rgb": [int(v) for v in hair] if hair is not None else None,
            "face": face, "head": d["head"], "makeup": d["makeup"], "neck": d["neck"], "items": d.get("items", []),
            "recolor": d.get("recolor", []), "face_to_body": d.get("face_to_body", False)}


def neck_text(pz):
    return "Around her neck: %s." % pz["neck"] if pz["neck"] else "Her neck is bare."


def head_text(pz):
    lips = "" if "lipstick" in pz["makeup"] else " and natural lips without lipstick"   # яркие губы F10, F11, F42
    return HEAD.format(who=WHO, skin_c=pz["skin"].capitalize(), hair=pz["hair"], face=pz["face"], neck=neck_text(pz),
                       makeup=pz["makeup"] + lips, head="She has %s. " % pz["head"] if pz["head"] else "")


def body_text(pz):
    return BODY.format(style=STYLE, who=WHO, skin=pz["skin"], face=pz["face"], neck=neck_text(pz))


def item_text(pz, it):
    return ITEM.format(who=WHO, skin=pz["skin"], text=it["text"])


def negative_for(pz):
    t = " ".join((pz["hair"], pz["head"], pz["neck"]))
    return NEGATIVE + NEG_BODY + "".join(", " + neg for keys, neg in NEG_GEAR if not any(k in t for k in keys))


# --- рисовальщик: ControlNet Union + inpaint + старт из латентов --------------------------------------------------

class Painter:
    """Две фазы в одном процессе (R-213): трансформер 14 ГБ и текстовая модель 17 ГБ вместе в карту 32 ГБ не входят,
    а выгрузка model_cpu_offload гоняет их туда-обратно - shared 0,5-0,6 ГБ на каждом кадре (#1066 снят сторожем).
    Фаза 1 - на карте только текстовая модель: все промпты пилота в RAM, модель удаляется. Фаза 2 - трансформер с
    веткой контроля и VAE на карте целиком, без выгрузки."""

    def __init__(self, prompts):
        import gc
        import torch
        from diffusers import FlowMatchEulerDiscreteScheduler
        from huggingface_hub import hf_hub_download, try_to_load_from_cache
        from safetensors.torch import load_file
        import vx_control as vc
        t = time.time()
        self.torch = torch
        Pipe, Ctl, Vae, TE, Proc = vc.load_vx()
        self.mod = sys.modules["videox_fun.pipeline.pipeline_qwenimage21_control"]
        idx = try_to_load_from_cache(vc.BASE_REPO, "model_index.json")
        if not isinstance(idx, str):
            raise SystemExit("нет %s в кэше HF" % vc.BASE_REPO)
        base, dt, dev = os.path.dirname(idx), torch.bfloat16, torch.device("cuda")
        vae = Vae.from_pretrained(base, subfolder="vae").to(dt)
        proc = Proc.from_pretrained(base, subfolder="processor")
        sch = FlowMatchEulerDiscreteScheduler.from_pretrained(base, subfolder="scheduler")
        te = TE.from_pretrained(base, subfolder="text_encoder", torch_dtype=dt).to(dev)
        pipe = Pipe(vae=vae, text_encoder=te, processor=proc, transformer=None, scheduler=sch)
        dp.gpu_mem("фаза 1: текстовая модель")
        self.emb = {}
        with torch.no_grad():
            for p in sorted(set(prompts) | {NEGATIVE}):
                pe, pm, _ipm = pipe._get_qwen_prompt_embeds([p], None, dev)
                self.emb[p] = (pe.to("cpu"), None if pm is None else pm.to("cpu"))
        pipe.register_modules(text_encoder=None)
        del te
        gc.collect()
        torch.cuda.empty_cache()
        print("фаза 1: %d промптов за %.0f с" % (len(self.emb), time.time() - t), flush=True)
        cn = hf_hub_download(vc.CN_REPO, vc.CN_FILE, local_files_only=True)
        tr = Ctl.from_pretrained(base, subfolder="transformer", low_cpu_mem_usage=True, torch_dtype=dt,
                                 transformer_additional_kwargs=vc.CONTROL_KW).to(dt)
        sd = load_file(cn)
        sd = sd.get("state_dict", sd)
        missing, unexpected = tr.load_state_dict(sd, strict=False)
        lost = [k for k in tr.state_dict() if k.startswith("control_") and k in missing]
        if unexpected or lost:
            raise SystemExit("ControlNet лёг не на свои места (R-087): лишние %s, пропали %s"
                             % (unexpected[:5], lost[:5]))
        del sd
        tr.to(dev)
        vae.to(dev)
        vae.enable_tiling()                             # кадр 640x1024 целиком в декодере - пик сверх 32 ГБ
        self.peak = {}
        dec = vae.decode

        def decode(*a, **kw):                           # пик расшумления и пик декодера - порознь
            self.peak["denoise"] = round(torch.cuda.max_memory_allocated() / 2 ** 30, 1)
            self.peak["before_decode"] = round(torch.cuda.memory_allocated() / 2 ** 30, 1)
            torch.cuda.reset_peak_memory_stats()
            r = dec(*a, **kw)
            self.peak["decode"] = round(torch.cuda.max_memory_allocated() / 2 ** 30, 1)
            return r
        vae.decode = decode
        fwd = tr.forward

        def forward(*a, **kw):                          # первые два прохода: сколько держит до и берёт сверху
            k = self.peak.setdefault("calls", 0)
            if k < 2:
                self.peak["fwd%d_in" % k] = round(torch.cuda.memory_allocated() / 2 ** 30, 1)
                torch.cuda.reset_peak_memory_stats()
            r = fwd(*a, **kw)
            if k < 2:
                self.peak["fwd%d_peak" % k] = round(torch.cuda.max_memory_allocated() / 2 ** 30, 1)
                self.peak["fwd%d_out" % k] = round(torch.cuda.memory_allocated() / 2 ** 30, 1)
            self.peak["calls"] = k + 1
            return r
        tr.forward = forward
        print("после загрузки: allocated %.1f ГБ" % (torch.cuda.memory_allocated() / 2 ** 30), flush=True)
        pipe.register_modules(transformer=tr)
        gc.collect()
        dp.gpu_mem("фаза 2: трансформер")
        self.p = argparse.Namespace(pipe=pipe)
        self.load_s = round(time.time() - t)
        self.n = 0

    def paint(self, *a):
        # без no_grad кодер VAE для img2img строит граф и держит активации весь кадр: +8 ГБ, shared (#1068)
        with self.torch.no_grad():
            return self._paint(*a)

    def _paint(self, init, mask, control, prompt, seed, strength, scale, negative):
        """init, control - PIL RGB WxH; mask - L (белое - рисовать). -> np RGB WxH."""
        torch, pipe = self.torch, self.p.pipe
        W, H = init.size
        steps = RUN["steps"]
        c = np.asarray(control.convert("RGB").resize((W, H), Image.LANCZOS))
        ctl = torch.from_numpy(c.copy()).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        g = torch.Generator("cuda").manual_seed(seed)
        sig = np.linspace(1.0, 1.0 / steps, steps)
        start = int(round(steps * (1.0 - strength)))
        tail = sig[start:]
        f = pipe.vae_scale_factor * 2
        lh, lw = 2 * (H // f), 2 * (W // f)
        sch = pipe.scheduler.config
        mu = self.mod.calculate_shift(lh * lw, sch.get("base_image_seq_len", 256), sch.get("max_image_seq_len", 4096),
                                      sch.get("base_shift", 0.5), sch.get("max_shift", 1.15))
        pipe.scheduler.set_timesteps(sigmas=list(tail), mu=mu, device="cuda")
        s0 = float(pipe.scheduler.sigmas[0])
        dev = pipe._execution_device
        x = pipe.image_processor.preprocess(init.convert("RGB"), height=H, width=W)
        x = torch.cat([x, torch.ones_like(x[:, :1])], dim=1).unsqueeze(2).to(dev, torch.bfloat16)
        x0 = pipe._encode_vae_image(x, g)
        noise = torch.randn(x0.shape, generator=g, device=x0.device, dtype=x0.dtype)
        lat = pipe._pack_latents(s0 * noise + (1.0 - s0) * x0, 1, x0.shape[1], x0.shape[3], x0.shape[4])
        pe, pm = (v if v is None else v.to(dev) for v in self.emb[prompt])
        ne, nm = (v if v is None else v.to(dev) for v in self.emb[negative])
        torch.cuda.reset_peak_memory_stats()
        out = pipe(prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm, negative_prompt_embeds=ne,
                   negative_prompt_embeds_mask=nm, image=init.convert("RGB"), mask_image=mask, control_image=ctl,
                   height=H, width=W, generator=g, true_cfg_scale=RUN["cfg"], sigmas=list(tail), latents=lat,
                   num_inference_steps=len(tail), control_context_scale=scale, use_kv_cache=True).images[0]
        self.n += 1
        print("пик torch %dx%d: %s" % (W, H, json.dumps(self.peak)), flush=True)
        self.peak = {}
        if self.n <= 2:
            dp.gpu_mem("кадр %d" % self.n)
        import gc
        gc.collect()
        torch.cuda.empty_cache()
        bg = Image.new("RGBA", out.size, dp.PANEL + (255,))
        bg.alpha_composite(out.convert("RGBA"))
        return np.array(bg.convert("RGB").resize((W, H), Image.LANCZOS)), round(s0, 3)


# --- геометрия -------------------------------------------------------------------------------------------------------

def to8(canvas4):
    x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
    size = ((x1 - x0) * dp.Z // dp.K, (y1 - y0) * dp.Z // dp.K)
    bg = Image.new("RGBA", size, dp.PANEL + (255,))
    bg.alpha_composite(canvas4.crop((x0, y0, x1, y1)).resize(size, Image.LANCZOS))
    return bg


def mask8(mask, grow=0):
    x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
    s4 = ws.sil4(mask)[y0:y1, x0:x1]
    size = ((x1 - x0) * dp.Z // dp.K, (y1 - y0) * dp.Z // dp.K)
    m = Image.fromarray((s4 > 0.5).astype(np.uint8) * 255).resize(size, Image.NEAREST)
    return m.filter(ImageFilter.MaxFilter(2 * grow + 1)) if grow else m


def head_box(files, look):
    hm = dp.layer_mask(files, "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look))
    bm = dp.layer_mask(files, "%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look))
    xs = np.nonzero(hm)[1]
    w, h = RUN["head"]["w"], RUN["head"]["h"]
    cx, top = int(xs.min() + xs.max() + 1) // 2, int(np.nonzero(hm | bm)[0].min()) - 1
    return cx - w // 2, top, cx - w // 2 + w, top + h


def thong_on(canvas8):
    """Стринги - тёмной фигурой во входе кадра тела: словами модель теряла их у трети тел (R-588). Поза у всех тел
    одна; координаты - база 320x200, сняты с удачного кадра F45."""
    pts = THONG
    s = 4                                               # край без лесенки
    size = canvas8.size
    m = Image.new("L", (size[0] * s, size[1] * s), 0)
    ImageDraw.Draw(m).polygon([((x - dp.CROP[0]) * dp.Z * s, (y - dp.CROP[1]) * dp.Z * s) for x, y in pts], fill=255)
    out = canvas8.copy()
    out.paste((16, 16, 18, 255), (0, 0), m.resize(size, Image.LANCZOS))
    return out


def _blur_in(rgb, cover, sigma):
    """Размытие цвета только внутри cover (премульт, R-035): фон за краем в цвет не затекает."""
    m = cover.astype(np.float32)
    c = cv2.GaussianBlur(m, (0, 0), sigma)
    out = cv2.GaussianBlur(np.ascontiguousarray(rgb, np.float32) * m[..., None], (0, 0), sigma)
    return out / np.maximum(c, 1e-3)[..., None], c


def tone_lock(rgb4_full, names, mask, sigma=6.0, lo=10.0, hi=25.0, shrink=dp.K):
    """Крупный тон вещи - от классики, мазок и детали - от модели. Сравниваются размытые (sigma px k=4) Lab
    рисунка и классики x4 внутри силуэта; где расходятся больше lo по dE, низкие частоты рисунка сдвигаются к
    классике (полностью с hi). Пилот 03.11: «мех по краю» модель сделала белыми поножами целиком, у классики они
    серо-коричневые. -> (холст, dE до, dE после) - средние по силуэту."""
    import build_pack as bp
    sil = ws.sil4(mask) > 0.5
    if not sil.any():
        return rgb4_full, 0.0, 0.0
    cl = np.asarray(dp.classic(FILES, PAL, names).resize((db.W * dp.K, db.H * dp.K), Image.NEAREST), np.float32)
    # тёмный контур классики (пиксель по краю) в тон не берём, иначе край рисунка темнеет полосой
    cover = cv2.erode((sil & (cl[..., 3] > 128)).astype(np.uint8), np.ones((3, 3), np.uint8),
                      iterations=shrink) > 0
    hd_lo, _ = _blur_in(rgb4_full, sil, sigma)
    cl_lo, ccl = _blur_in(cl[..., :3], cover, sigma)
    lab = bp._rgb_to_lab(rgb4_full / 255.0)
    lab_hd, lab_cl = bp._rgb_to_lab(hd_lo / 255.0), bp._rgb_to_lab(cl_lo / 255.0)
    de = np.linalg.norm(lab_hd - lab_cl, axis=-1)
    sil = sil & (ccl > 0.1)                             # тонкие ремни без нутра классики - как нарисованы
    if not sil.any():
        return rgb4_full, 0.0, 0.0
    w = (np.clip((de - lo) / (hi - lo), 0, 1) * sil)[..., None]
    out = rgb4_full.copy()
    out[sil] = (bp._lab_to_rgb(lab + w * (lab_cl - lab_hd)) * 255.0)[sil]
    after = np.linalg.norm(bp._rgb_to_lab(_blur_in(out, sil, sigma)[0] / 255.0) - lab_cl, axis=-1)
    return out, round(float(de[sil].mean()), 1), round(float(after[sil].mean()), 1)


def _classic_parts(look):
    """(маска тела, маска головы, нутро без контура, на полурампах кожи) - те же правила, что в passport."""
    body = db.load_indices(FILES["%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look)])
    head = db.load_indices(FILES["%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look)])
    bm, hm = body != 0, head != 0
    idx = np.where(hm, head, body)
    torso = bm.copy()
    torso[:np.nonzero(hm)[0].max() + 6] = False
    halves = np.nonzero(np.bincount(body[torso] // 8, minlength=32) / float(torso.sum()) >= 0.02)[0]
    allm = bm | hm
    pad = np.pad(allm, 1)
    inner = pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    return bm, hm, inner, np.isin(idx // 8, halves)


def skin_cover(look):
    """Кожа классики (k=1): пиксели тела и головы на полурампах кожи, без контура."""
    bm, hm, inner, ramps = _classic_parts(look)
    return (bm | hm) & inner & ramps


def hair_zone(look, box):
    """Что рисует кадр головы (k=1): слой головы, всё выше ключиц и крупные пятна не цвета кожи, начинающиеся у шеи -
    хвосты, косы, бусы: они лежат в слое тела, и кадр всего тела рисовал их мелко и по словам (хвосты F31, R-595).
    Соски (мелкие пятна) и кожа торса остаются кадру тела: на нём наклейки."""
    import photo_base as pb
    bm, hm, inner, ramps = _classic_parts(look)
    neck = FACE_BOX[3] + 3
    zone = hm.copy()
    zone[:FACE_BOX[3] - 2] |= bm[:FACE_BOX[3] - 2]      # плечи (от строки 59) - кадру тела: грязная полоса F11, F55
    zone[:neck, FACE_BOX[0] - 2:FACE_BOX[2] + 4] |= bm[:neck, FACE_BOX[0] - 2:FACE_BOX[2] + 4]    # шея
    lab, n = pb.label((bm | hm) & inner & ~ramps, 8)
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() >= 10 and np.nonzero(m)[0].min() <= neck + 5:
            zone |= m
    keep = np.zeros_like(zone)
    keep[box[1]:box[3], box[0]:box[2]] = True
    return zone & keep


def skin_match(rgb4_full, look, region, sample=None, near=None):
    """Тон кожи - к классике одним сдвигом Lab на всю кожу (10 внешностей 03.11: модель сжимала кожу к среднему
    загару - тёмные тела светлели на 10-17 L, бронзовые темнели на 6-18). Сдвиг = медиана классики минус медиана
    рисунка по коже классики; вес пикселя - близость к цвету кожи рисунка, так что бельё (чёрное), белки глаз,
    губы, волосы и ошейники не сдвигаются. Мазок и светотень - от модели (tone_lock по размытию на теле давал
    пятна и стирал бельё). region - маска k=1, где править; sample - где мерить (по умолчанию там же). У бронзовых
    тел волосы лежат на рампах кожи и сдвигали лицо в жёлтое (F12, M41: a -33): голову мерить только по лицу.
    -> (холст, [dL, da, db])"""
    import build_pack as bp
    cov1 = skin_cover(look) & region
    cov = ws.sil4(cov1 if sample is None else cov1 & sample) > 0.5
    cov = cv2.erode(cov.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=2) > 0
    names = ["%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look), "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look)]
    names = [n for n in names if n in FILES]            # у LOKNAR голова в слое тела, слоя головы нет
    cl = np.asarray(dp.classic(FILES, PAL, names).resize((db.W * dp.K, db.H * dp.K), Image.NEAREST).convert("RGB"),
                    np.float32)
    lab = bp._rgb_to_lab(rgb4_full / 255.0)
    sel = cov & (lab[..., 0] > 22)                      # чёрное бельё в медиану не берётся
    if sel.sum() < 100:                                 # 200 при эрозии на K не набирали 9 голов из 13
        return rgb4_full, None
    ref = np.median(lab[sel], 0)
    d = np.median(bp._rgb_to_lab(cl / 255.0)[cov], 0) - ref
    if near is not None:                                # голова - не дальше 8 от сдвига тела: F58 давала b +112 по
        d = np.clip(d, np.array(near) - (8, 4, 4), np.array(near) + (8, 4, 4))   # раскраске щёк, F5 и M4 зеленели на
                                                        # a -20 (04.11); a, b при 8 - жёлтая шея F13, M4 (серия #1095)
    dist =np.sqrt((lab[..., 1] - ref[1]) ** 2 + (lab[..., 2] - ref[2]) ** 2 + (0.3 * (lab[..., 0] - ref[0])) ** 2)
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    area = cv2.GaussianBlur((ws.sil4(region & (cv2.dilate(cov1.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0))
                             > 0.5).astype(np.float32), (0, 0), 3.0)
    w = np.clip((40 - dist) / 15, 0, 1) * np.clip((chroma - 6) / 8, 0, 1) * np.clip(area * 2, 0, 1)
    out = bp._lab_to_rgb(lab + w[..., None] * d) * 255.0
    return out.astype(np.float32), [round(float(v), 1) for v in d]


def face_to_body(fh, f4):
    """Цвет кожи лица и шеи - к цвету груди (a, b Lab), светлота и мазок остаются. Лицо M5, M8, M9 желтее тела, шея M9 и
    M13 оливковая (Vitali 04.11): классика держит этот цвет. Цель - цвет торса при той же светлоте: середина груди
    бледнее и зеленит. Сдвиг плавный, у щёк и шеи он разный; губы и тени далеки от кожи по цвету, вес их обходит."""
    import build_pack as bp
    k = dp.K
    x0, y0, x1, y1 = FACE_BOX
    lab = bp._rgb_to_lab(fh / 255.0)
    torso = bp._rgb_to_lab(f4[FACE_TORSO[0] * k:FACE_TORSO[1] * k, FACE_TORSO[2] * k:FACE_TORSO[3] * k] / 255.0).reshape(-1, 3)
    torso = torso[(torso[..., 0] > 22) & (np.hypot(torso[..., 1], torso[..., 2]) > 10)]
    bins = [b for b in range(22, 100, 4) if (np.abs(torso[..., 0] - b) < 4).sum() > 50]
    curve = np.array([np.median(torso[np.abs(torso[..., 0] - b) < 4], 0) for b in bins])
    ref = np.median(lab[(y0 + 4) * k:y1 * k, x0 * k:(x1 + 1) * k].reshape(-1, 3), 0)
    dist = np.hypot(lab[..., 1] - ref[1], lab[..., 2] - ref[2])
    limit = np.full(dist.shape, FACE_LIMIT[0], np.float32)
    limit[y1 * k:] = FACE_LIMIT[1]                      # на шее нет косметики, а оливковая тень дальше от щёк, чем губы
    w = np.clip((limit - dist) / 12, 0, 1) * np.clip((np.hypot(lab[..., 1], lab[..., 2]) - 6) / 8, 0, 1) * (lab[..., 0] > 22)
    box = np.zeros(w.shape, np.float32)
    box[(y0 - 1) * k:(y1 + 5) * k, (x0 - 1) * k:(x1 + 3) * k] = 1
    low, _c = _blur_in(lab, (box > 0) & (w > 0.5), 1.0 * k)
    target = np.dstack([np.interp(low[..., 0], curve[:, 0], curve[:, c]) for c in (1, 2)])
    w = (w * np.minimum(cv2.GaussianBlur(box, (0, 0), 0.75 * k), box))[..., None]
    lab[..., 1:] += w * (target - low[..., 1:])
    return (bp._lab_to_rgb(lab) * 255.0).astype(np.float32)


def classic_marks(look):
    """Что нарисовано на теле классики поверх чистого тела (k=1): вещи, кончики волос, бусы, волосы в паху."""
    body = db.load_indices(FILES["%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look)])
    y = body[70:100]
    ref = db.load_indices(FILES["%s__%d__%s_NUDE" % (dp.RACE, dp.BODY,
                                                     CLEAN_BODY[int(np.bincount(y[y != 0] // 8, minlength=32).argmax())])])
    return body != ref


def clean_body(rgb4, look):
    """Кадр тела после рисунка, ниже шеи. 1) Двойной контур: модель рисует ногу уже силуэта, между ними подложка и
    призрачная линия, альфа силуэта показывает это серой каймой (серия #1095, R-089). Серое и тонкое вдоль края
    заполняется цветом ближайшей кожи. Кисти - без размыкания, пальцы тоньше линии. 2) Бледная черта на груди, на всех
    телах в одном месте, и её зеркало: полоса заменяется переходом между кожей слева и справа от неё, сверху вниз
    светотень сохраняется."""
    import build_pack as bp
    k = dp.K
    body = dp.layer_mask(FILES, "%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look))
    sil = ws.sil4(body) > 0.5
    below = np.zeros(sil.shape, bool)
    below[(FACE_BOX[3] + 3) * k:] = True
    lab = bp._rgb_to_lab(rgb4 / 255.0)
    grey = (np.hypot(lab[..., 1], lab[..., 2]) < 10) & (lab[..., 0] > 38)
    # с запасом: переход серое-кожа иначе остаётся пунктиром по шву (лист 04.11)
    core = (sil & ~(cv2.dilate((grey & sil).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0)).astype(np.uint8)
    keep = cv2.morphologyEx(core, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0
    hands = np.zeros(sil.shape, bool)
    hands[HAND_ROWS[0] * k:HAND_ROWS[1] * k, :HAND_X[0] * k] = hands[HAND_ROWS[0] * k:HAND_ROWS[1] * k, HAND_X[1] * k:] = True
    keep |= (core > 0) & hands
    marks = ws.sil4(cv2.dilate(classic_marks(look).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) > 0.5
    edge = cv2.distanceTransform(sil.astype(np.uint8), cv2.DIST_L2, 5) <= 4 * k     # блики на наклейках - не кайма
    strap = np.zeros(sil.shape, np.uint8)               # завязки стрингов тоньше размыкания: не кайма (пятна на бёдрах)
    strap[STRAP_ROWS[0] * k:STRAP_ROWS[1] * k] = lab[STRAP_ROWS[0] * k:STRAP_ROWS[1] * k, :, 0] <= 32   # только строки завязок: ниже так уцелеет контур бедра
    strap = cv2.dilate(strap, np.ones((5, 5), np.uint8)) > 0
    fill = sil & ~keep & below & ~marks & edge & ~strap
    out = rgb4.copy()
    dark = cv2.morphologyEx((lab[..., 0] <= 25).astype(np.uint8), cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))     # тонкий контур тела - не наклейка
    skin = cv2.dilate(dark, np.ones((9, 9), np.uint8)) == 0                             # наклейки и их блики - мимо
    src = (cv2.erode(keep.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & skin
    if FILL_EDGES and fill.any() and src.any():
        _d, near = cv2.distanceTransformWithLabels((~src).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        table = np.zeros((near.max() + 1, 3), np.float32)
        table[near[src]] = rgb4[src]
        out[fill] = table[near[fill]]
        soft, _c = _blur_in(out, sil & skin, 2.0)
        seam = cv2.GaussianBlur((cv2.dilate(fill.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0).astype(np.float32), (0, 0), 1.5)
        seam = np.clip(seam * 2, 0, 1)[..., None] * (sil & ~marks & skin & ~strap)[..., None]
        out = out * (1 - seam) + soft * seam
    light = cv2.dilate((lab[..., 0] <= 25).astype(np.uint8), np.ones((9, 9), np.uint8)) == 0
    ok = (light & sil & ~marks).astype(np.float32)
    for xc, y0, y1 in CHEST_LINES:                          # толщина черты - 4 точки k=4 (замер 04.11); шире - заплатка
        x0, x1, y0, y1 = int(xc * k) - 5, int(xc * k) + 6, y0 * k, y1 * k
        t = np.linspace(0, 1, x1 - x0, dtype=np.float32)[None, :, None]
        band = out[y0:y1, x0 - 2:x0].mean(1, keepdims=True) * (1 - t) + out[y0:y1, x1:x1 + 2].mean(1, keepdims=True) * t
        band = cv2.GaussianBlur(band, (0, 0), sigmaX=0.1, sigmaY=2.0)
        rows = (ok[y0:y1, x0 - 2:x0].min(1) * ok[y0:y1, x1:x1 + 2].min(1))[:, None]     # край наклейки в образец не брать
        w = np.zeros(sil.shape, np.float32)
        w[y0:y1, x0:x1] = np.minimum(np.sin(t[..., 0] * np.pi) * 2.5, 1) * ok[y0:y1, x0:x1] * rows
        w = np.minimum(cv2.GaussianBlur(w, (0, 0), 0.8), ok)[..., None]
        whole = out.copy()
        whole[y0:y1, x0:x1] = band
        out = out * (1 - w) + whole * w
    # белый ноготь большого пальца: пятно ярче ступни вокруг, у всех тёмных тел с нарисованными пальцами (#1109)
    feet = np.zeros(sil.shape, bool)
    feet[FEET_ROW * k:] = True
    wide, _c = _blur_in(out, sil, 3.0 * k)
    near, _c = _blur_in(out, sil, 1.5 * k)
    nail = (out.mean(2) - wide.mean(2) > 35) & feet & sil
    w = cv2.GaussianBlur(cv2.dilate(nail.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32), (0, 0), 1.0)
    w = (w * sil)[..., None]
    return out * (1 - w) + near * w


def layer_from(rgb4_full, mask, edge=3.0):
    """Холст k=4 RGB (весь 1280x800) + маска слоя -> слой RGBA с альфой силуэта классики x4.
    Полоса edge px у края берёт цвет изнутри: модель рисует по контуру светлую кайму (пилот 03.11, R-089)."""
    sil = ws.sil4(mask)
    rgb = rgb4_full
    if edge:
        d = cv2.distanceTransform((sil > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
        inner = d > edge
        fill, c = _blur_in(rgb, inner, edge)
        t = (np.clip(1 - (d - 1) / edge, 0, 1) * (c > 0.05) * (sil > 0))[..., None]
        rgb = rgb * (1 - t) + fill * t
    a = np.zeros(sil.shape + (4,), np.float32)
    a[..., :3] = rgb
    a[..., 3] = sil * 255
    return Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), "RGBA")


def full4(rgb8):
    """Ответ x8 рамки CROP -> холст k=4 RGB 1280x800 (вне рамки - подложка)."""
    x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
    out = np.empty((db.H * dp.K, db.W * dp.K, 3), np.float32)
    out[:] = dp.PANEL
    out[y0:y1, x0:x1] = np.asarray(Image.fromarray(rgb8).resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32)
    return out


# --- листы -----------------------------------------------------------------------------------------------------------

def tile(canvas4, box4, bgc=(40, 42, 50)):
    bg = Image.new("RGBA", (box4[2] - box4[0], box4[3] - box4[1]), bgc + (255,))
    bg.alpha_composite(canvas4.crop(box4))
    return bg.convert("RGB")


def ctl_layer(n):
    p = os.path.join(CTL, n.lower() + ".png")
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None


def grid(rows, path):
    tw, th = rows[0][0].size
    out = Image.new("RGB", (max(len(r) for r in rows) * tw, len(rows) * th), (20, 20, 24))
    for j, r in enumerate(rows):
        for i, t in enumerate(r):
            out.paste(t, (i * tw, j * th))
    out.save(path)
    return path


FILES = PAL = None


def main():
    global FILES, PAL
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--looks", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redraw", action="store_true")
    ap.add_argument("--worker", action="store_true", help="(служебное) рисовать недостающие кадры подряд")
    ns = ap.parse_args()
    for d in ("raw", "layers"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    FILES, PAL = db.sprite_files(), db.game_palette()
    cp.FILES, cp.PAL = FILES, PAL
    arms = db.armor_layers()
    keys = [k for k in arms[dp.ARMORS[0]] if all(k in arms[a] for a in dp.ARMORS)]
    looks = ns.looks.split(",") if ns.looks else dp.pick_looks(FILES, keys)
    outfits = {a: {k: [n for n in arms[a][k] if n] for k in looks} for a in dp.ARMORS}
    pas = {k: passport(FILES, PAL, k) for k in looks}
    with open(os.path.join(OUT, "passports.json"), "w", encoding=db.ENC) as f:
        json.dump(pas, f, ensure_ascii=False, indent=1)
    if not ns.worker:
        for k in looks:
            print("паспорт %s: %s" % (k, json.dumps(pas[k], ensure_ascii=False)), flush=True)

    state = {"painter": None}
    run = {"race": dp.RACE, "armors": dp.ARMORS, "looks": looks, "engine": RUN, "dry_run": ns.dry_run,
           "passports": pas, "renders": {}}
    t0 = time.time()

    def draw(tag, init, mask, control, prompt, seed, stage, negative=NEGATIVE):
        """-> np RGB ответа (размер init). Родитель - запускает рабочий процесс; рабочий - рисует."""
        raw = os.path.join(OUT, "raw")
        init.convert("RGB").save(os.path.join(raw, tag + "_in.png"))
        mask.save(os.path.join(raw, tag + "_mask.png"))
        done = os.path.join(raw, tag + "_out.png")
        info = os.path.join(raw, tag + "_render.json")
        if ns.dry_run:
            return np.asarray(init.convert("RGB"))
        if ns.redraw and not ns.worker and not run.get("redrawn"):
            for fn in os.listdir(raw):
                if fn.endswith(("_out.png", "_render.json")):
                    os.remove(os.path.join(raw, fn))
            run["redrawn"] = True
        if not os.path.exists(done):
            if not ns.worker:
                for attempt in range(3):
                    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--worker"]
                                       + (["--looks", ns.looks] if ns.looks else []))
                    if os.path.exists(done):
                        break
                    print("рабочий процесс вышел с кодом %s, кадра %s нет (попытка %d)" % (r.returncode, tag,
                                                                                          attempt + 1), flush=True)
                if not os.path.exists(done):
                    raise SystemExit("кадр %s не нарисован" % tag)
            else:
                if state["painter"] is None:              # все тексты пилота - до трансформера (две фазы)
                    texts = [ARMOR.format(style=STYLE, what=pp.ARMOR_WHAT[a]) for a in dp.ARMORS]
                    for pz in pas.values():
                        texts += [body_text(pz), head_text(pz), negative_for(pz)]
                        texts += [item_text(pz, it) for it in pz["items"]]
                    state["painter"] = Painter(texts)
                    print("модель загружена за %d с" % state["painter"].load_s, flush=True)
                p = state["painter"]
                t = time.time()
                try:
                    rgb, s0 = p.paint(init, mask, control, prompt, seed, RUN[stage]["strength"],
                                      RUN[stage]["control"], negative)
                except Exception as e:                      # память карты: новый процесс продолжит
                    print("кадр %s упал: %s" % (tag, str(e)[:300]), flush=True)
                    sys.exit(75)
                Image.fromarray(rgb).save(done)
                with open(info, "w", encoding=db.ENC) as f:
                    json.dump({"seconds": round(time.time() - t), "sigma0": s0, "load_s": p.load_s,
                               "nth_in_process": p.n, "stage": stage, "prompt": prompt}, f, ensure_ascii=False)
                print("  %s: %.0f с (кадр %d в процессе)" % (tag, time.time() - t, p.n), flush=True)
        if os.path.exists(info):
            with open(info, encoding=db.ENC) as f:
                run["renders"][tag] = json.load(f)
        return np.asarray(Image.open(done).convert("RGB"))

    def b2(names):
        return cp.b2_canvas(names)

    def save(n, im, how):
        layers[n] = im
        im.save(os.path.join(OUT, "layers", n.lower() + ".png"))
        run.setdefault("layers", {})[n] = how

    import vx_control as vc
    layers = {}
    # ступень 2: тело (и черновик головы) каждой внешности
    for i, look in enumerate(looks):
        pz = pas[look]
        seed = RUN["seed"] + 1000 * RESEED.get(look, 0) + i
        body = "%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look)
        head = "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look)
        names = [body, head]
        cl = dp.classic(FILES, PAL, names)
        sil = dp.layer_mask(FILES, body) | dp.layer_mask(FILES, head)
        ctl = vc.control_map(cl.crop(dp.CROP), dp.Z, "gray")
        rgb8 = draw("body_" + look, thong_on(to8(b2(names))), mask8(sil), ctl, body_text(pz), seed, "body",
                    negative_for(pz))
        # tone_lock на теле и голове не ставить (пилот 03.11): стирает бельё (у классики там голая кожа),
        # тянет в пятна раскраску лица и тёмный контур классики (стопа M51); тон кожи - skin_match
        f4, sd = skin_match(full4(rgb8), look, sil)
        run.setdefault("skin_shift", {})["body_" + look] = sd
        f4 = clean_body(f4, look)

        # вещи на теле - кадром поверх готовой кожи, каждая на своём месте: словами модель ставила их куда придётся (R-596)
        for j, it in enumerate(pz["items"]):
            ix0, iy0, ix1, iy1 = it["box"]
            iw, ih, iz = RUN["item"]["w"], RUN["item"]["h"], RUN["item"]["zoom"]
            bx, by = (ix0 + ix1) // 2 - iw // 2, (iy0 + iy1) // 2 - ih // 2
            ib = (bx * dp.K, by * dp.K, (bx + iw) * dp.K, (by + ih) * dp.K)
            im = np.zeros_like(classic_marks(look))
            im[iy0:iy1, ix0:ix1] = classic_marks(look)[iy0:iy1, ix0:ix1]
            grown = ws.sil4(cv2.dilate(im.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
            mark4 = dp.classic(FILES, PAL, [body]).resize((db.W * dp.K, db.H * dp.K), Image.NEAREST)
            mark4.putalpha(Image.fromarray((ws.sil4(im) > 0.5).astype(np.uint8) * 255))
            start = Image.fromarray(np.clip(f4 + 0.5, 0, 255).astype(np.uint8)).convert("RGBA")
            start.alpha_composite(mark4)
            init_i = start.crop(ib).resize((iw * iz, ih * iz), Image.LANCZOS)
            mi = Image.fromarray((grown[ib[1]:ib[3], ib[0]:ib[2]] > 0.5).astype(np.uint8) * 255).resize((iw * iz, ih * iz),
                                                                                                        Image.NEAREST)
            ctl_i = vc.control_map(cl.crop((bx, by, bx + iw, by + ih)), iz, "gray")
            rgbi = draw("item_%s_%d" % (look, j), init_i, mi, ctl_i, item_text(pz, it), seed + 60 + j, "item")
            i4 = np.asarray(Image.fromarray(rgbi).resize((ib[2] - ib[0], ib[3] - ib[1]), Image.LANCZOS), np.float32)
            a = cv2.GaussianBlur((grown > 0.5).astype(np.float32), (0, 0), 1.5)[ib[1]:ib[3], ib[0]:ib[2], None]
            f4[ib[1]:ib[3], ib[0]:ib[2]] = f4[ib[1]:ib[3], ib[0]:ib[2]] * (1 - a) + i4 * a

        # ступень 3: голова, причёска и шея - отдельным кадром поверх тела
        bx0, by0, bx1, by1 = head_box(FILES, look)
        z = RUN["head"]["zoom"]
        hb4 = (bx0 * dp.K, by0 * dp.K, bx1 * dp.K, by1 * dp.K)
        hsize = ((bx1 - bx0) * z, (by1 - by0) * z)
        # старт - классика, не кадр тела: там голова мелкая, косы, маски и причёски уже потеряны (R-590, проба #1085)
        start_h = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), dp.PANEL + (255,))
        start_h.alpha_composite(b2(names))
        init_h = start_h.crop(hb4).resize(hsize, Image.LANCZOS)
        hm = dp.layer_mask(FILES, head)
        zone = hair_zone(look, (bx0, by0, bx1, by1))
        hs = ws.sil4(zone)[hb4[1]:hb4[3], hb4[0]:hb4[2]]
        mh = Image.fromarray((hs > 0.5).astype(np.uint8) * 255).resize(hsize, Image.NEAREST)
        ctl_h = vc.control_map(cl.crop((bx0, by0, bx1, by1)), z, "gray")
        rgbh = draw("head_" + look, init_h, mh, ctl_h, head_text(pz), seed + 50, "head", negative_for(pz))
        h4 = np.asarray(Image.fromarray(rgbh).resize((hb4[2] - hb4[0], hb4[3] - hb4[1]), Image.LANCZOS), np.float32)
        fh = f4.copy()
        fh[hb4[1]:hb4[3], hb4[0]:hb4[2]] = h4
        cheeks = np.zeros_like(hm)                         # ниже глаз: чёлка и визор сюда не доходят
        cheeks[FACE_BOX[1] + 4:FACE_BOX[3] + 1, FACE_BOX[0]:FACE_BOX[2] + 1] = True
        fh, sd = skin_match(fh, look, zone, cheeks, run["skin_shift"]["body_" + look])
        run["skin_shift"]["head_" + look] = sd
        # цвет волос - к классике по низким частотам: слово цвета модель понимала по-своему (F44, F51, хвосты F31).
        # Лицо и кожу не трогать; выше подбородка и вне лица - волосы и на рампах кожи (жёлтые F0, F5, F52)
        yy, xx = np.indices(hm.shape)
        fx0, fy0, fx1, fy1 = FACE_BOX
        off_face = ((xx < fx0 - 1) | (xx > fx1 + 2) | (yy < fy0)) & (yy <= fy1)
        fface = (xx >= fx0) & (xx <= fx1) & (yy >= fy0) & (yy <= fy1)
        fh, d0, d1 = tone_lock(fh, names, zone & (~skin_cover(look) | off_face) & ~fface)
        run.setdefault("tone_dE", {})["hair_" + look] = [d0, d1]
        if pz["face_to_body"]:
            fh = face_to_body(fh, f4)
        # слой тела: в зоне кадр головы, наружу плавно уходит в кадр тела
        w = np.clip(cv2.GaussianBlur((ws.sil4(zone) > 0.5).astype(np.float32), (0, 0), 4.0) * 2, 0, 1)[..., None]
        whole = f4 * (1 - w) + fh * w
        # тонкие пряди на плечах: модель красит их бурым (лиловые F51) или придумывает (F50), эрозия tone_lock их съедает
        for x0, y0, x1, y1 in pz["recolor"]:
            part = np.zeros_like(hm)
            part[y0:y1, x0:x1] = dp.layer_mask(FILES, body)[y0:y1, x0:x1]
            whole, _d0, _d1 = tone_lock(whole, names, part, sigma=3.0, lo=6.0, hi=15.0, shrink=0)
        save(body, layer_from(whole, dp.layer_mask(FILES, body)), {"from": ["body_" + look, "head_" + look]})
        save(head, layer_from(fh, hm), {"from": "head_" + look, "box": [bx0, by0, bx1, by1]})
        print("внешность %s (%d/%d), %.0f с" % (look, i + 1, len(looks), time.time() - t0), flush=True)

    # ступень 4: вещи брони поверх готового HD-тела первой внешности
    base = looks[0]
    for j, arm in enumerate(dp.ARMORS):
        names = outfits[arm][base]
        todo = [n for n in names if n not in layers]
        canvas = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), (0, 0, 0, 0))
        for n in names:
            if n in layers:
                canvas.alpha_composite(layers[n])
            else:
                bl, _m = dp.b2_layer(n)
                canvas.alpha_composite(bl if bl is not None else
                                       dp.classic(FILES, PAL, [n]).resize(canvas.size, Image.NEAREST))
        um = np.zeros((db.H, db.W), bool)
        for n in todo:
            um |= dp.layer_mask(FILES, n)
        cl = dp.classic(FILES, PAL, names)
        ctl = vc.control_map(cl.crop(dp.CROP), dp.Z, "gray")
        prompt = ARMOR.format(style=STYLE, what=pp.ARMOR_WHAT[arm])
        rgb8 = draw("armor_" + arm, to8(canvas), mask8(um, RUN["armor"]["grow8"]), ctl, prompt,
                    RUN["seed"] + 100 + j, "armor")
        f4, d0, d1 = tone_lock(full4(rgb8), names, um)
        run.setdefault("tone_dE", {})["armor_" + arm] = [d0, d1]
        masks = {n: dp.layer_mask(FILES, n) for n in names}
        for k, n in enumerate(names):
            if n in layers:
                continue
            im = layer_from(f4, masks[n])
            above = np.zeros_like(masks[n])
            for m in names[k + 1:]:
                above |= masks[m]
            hid = ws.sil4(masks[n] & above) > 0.5          # под верхними вещами в этой броне не видно - B2
            bl, _m = dp.b2_layer(n)
            if bl is not None and hid.any():
                a = np.asarray(im).copy()
                a[hid, :3] = np.asarray(bl)[hid, :3]
                im = Image.fromarray(a, "RGBA")
            save(n, im, {"from": "armor_" + arm, "hidden_px_from_b2": int(hid.sum())})
        print("%s: %d вещей, %.0f с" % (arm, len(todo), time.time() - t0), flush=True)

    if ns.worker:
        sys.exit(0)

    if len(looks) > 13:                                 # лист в строку на 50+ внешностей - 60 000 px шириной
        run["seconds"] = round(time.time() - t0)
        with open(os.path.join(OUT, "run.json"), "w", encoding=db.ENC) as f:
            json.dump(run, f, ensure_ascii=False, indent=1)
        print("слои готовы, листов нет (внешностей %d > 13), за %.0f с" % (len(looks), time.time() - t0))
        return

    # листы
    x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
    box = (x0, y0, x1, y1)
    rows = []
    sets = [("nude", lambda k: ["%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, k), "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, k)])]
    sets += [(a, lambda k, a=a: outfits[a][k]) for a in dp.ARMORS]
    for _tag, fn in sets:
        r = []
        for k in looks:
            names = fn(k)
            cl4 = dp.classic(FILES, PAL, names).resize((db.W * dp.K, db.H * dp.K), Image.NEAREST)
            old = [ctl_layer(n) for n in names]
            r.append(tile(cl4, box))
            r.append(tile(dp.compose([o for o in old if o is not None]), box))
            r.append(tile(dp.compose([layers[n] for n in names if n in layers]), box))
        rows.append(r)
    run["sheet"] = grid(rows, os.path.join(OUT, "sheet.png"))
    frows = []
    for k in looks:
        bx0, by0, bx1, by1 = head_box(FILES, k)
        hb = (bx0 * dp.K, by0 * dp.K, bx1 * dp.K, by1 * dp.K)
        names = ["%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, k), "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, k)]
        cl4 = dp.classic(FILES, PAL, names).resize((db.W * dp.K, db.H * dp.K), Image.NEAREST)
        old = dp.compose([o for o in (ctl_layer(n) for n in names) if o is not None])
        new = dp.compose([layers[n] for n in names if n in layers])
        frows.append([tile(c, hb).resize(((hb[2] - hb[0]) * 3, (hb[3] - hb[1]) * 3), Image.LANCZOS)
                      for c in (cl4, old, new)])
    run["faces"] = grid(frows, os.path.join(OUT, "faces.png"))
    run["seconds"] = round(time.time() - t0)
    with open(os.path.join(OUT, "run.json"), "w", encoding=db.ENC) as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    print("листы:", run["sheet"], run["faces"], "за %.0f с" % (time.time() - t0))


if __name__ == "__main__":
    main()
