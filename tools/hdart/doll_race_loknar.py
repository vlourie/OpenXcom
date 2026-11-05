"""Куклы Локк'Наар (LOKNAR): одна основа и 16 голов; настройки расы поверх общих скриптов doll_race_bodies, _assemble, _heads.

Перепись 05.11: силуэт всех 16 внешностей совпадает попиксельно, тело одно, кож четыре (F0-3 графит, F4-7 бледно-лиловая, M0-3 бирюза,
M4-7 красная; M в имени - тоже женская фигура). Слоя головы нет: голова и волосы лежат в слое тела, поэтому кадр головы идёт в слой NUDE.
Основа рисуется на самой светлой коже F4, остальные кожи - кривой светлота -> цвет (doll_race_assemble). Выход art/doll/pipe_pilot/loknar/.

  py -3 tools/gpuq.py add --name doll_loknar_base -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_race_loknar.py bodies
  py -3 tools/gpuq.py add --name doll_loknar_feet -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_race_loknar.py feet
  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_race_loknar.py fixbase
  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_race_loknar.py assemble
  py -3 tools/gpuq.py add --name doll_loknar_heads -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_race_loknar.py heads --looks F4,F0,M0,M4
  py -3 tools/gpuq.py add --name doll_loknar_armor -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_race_loknar.py armor
  --dry-run - без модели: входы кадров и зоны на листах.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_pipe_pilot as P                         # до numpy: пилот ставит окружение модели
import cv2
import numpy as np
from PIL import Image, ImageDraw
import build_pack as bp
import doll_b2_render as db
import doll_ctl_pilot as cp
import doll_photo_pilot as dp
import doll_race_bodies as rb
import doll_race_heads as rh
import photo_base as pb
import vx_control as vc
import wall_section as ws

RACE = "LOKNAR"
OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", RACE.lower())
BASE = "F4"
LOOKS = ["F%d" % i for i in range(8)] + ["M%d" % i for i in range(8)]
# места на теле: сетка по F4 крупно, 05.11; глаза - строки 63-66, рот - 71-74, подбородок - 76, ключицы - 80, пах - 110, середина 77
FACE_BOX = (71, 60, 83, 76)
NECK_ROW = 79
THONG = [(67.5, 101), (77, 106), (90, 101), (90, 102.5), (79, 108), (78.5, 111), (76.5, 111), (75.5, 108), (67.5, 102.5)]
HAND_ROWS, HAND_X = (102, 114), (67, 92)
STRAP_ROWS = (99, 110)
FEET_ROW = 140
CROTCH = (100, 113, 64, 94)
HAIR_FROM_ROW, HAIR_TO_ROW = 74, 94                 # где искать волосы на плечах
# большая голова классики сбивает модель в детские пропорции (#1129, #1131): возраст выше, чем у людей, и голову кадр тела не рисует
WHO = "a slender adult woman of an elf-like alien race, in her mid-twenties"
TORSO = ("Slender build with a narrow waist and wide hips. A smooth flat belly with a navel. Smooth skin with soft satin "
         "highlights on the shoulders, chest, belly and thighs, exactly as in the input.")
HAIR = "long wavy %s hair with a side-swept fringe, thick locks falling down to the shoulders on both sides"
MAKEUP = "dark eyeliner and a soft dark eyeshadow on the eyelids"
SKIN = {"F0": "dark charcoal-grey", "F4": "pale lilac-grey", "M0": "vivid teal-blue", "M4": "vivid crimson red"}
# другой шаблон, чем у людей: яркие глаза у этой расы настоящие, а не косметика; ухо - примета расы, голова чуть наклонена
HEAD = ("Close-up of the head and face of {who}, part of a hand-painted paper-doll portrait for an X-COM-style strategy "
        "game, soft light from the upper left. Repaint the low-resolution input in high detail without changing its "
        "design; the face stays the same size, in the same place and with the same slight tilt, the hairline stays "
        "where it is. Hair: {hair}. {head}{neck} Makeup: {makeup}. {skin_c} skin all over the face, the neck and the "
        "ear, {face}. One long pointed elf ear rises from the side of her head on the right of the picture, the same "
        "size and shape as in the input. A pretty adult woman's face with defined cheekbones, smooth unlined skin and "
        "feminine features: clear eyes with irises and highlights, neat brows, a small nose, soft lips. Dark spots on the skin "
        "of the input are soft shading only. Painted game art, not a photo.")
NEGATIVE_RACE = (", round human ears, natural human skin colour, tanned skin, text, letters, glyphs, runes, printed pattern on the skin, "
                 "glowing eyes, neon glow, ring of light around the iris, fangs, sharp teeth, open mouth, "
                 "chibi, baby face, childlike proportions, sphere, ball, dome, button")
# #1129: наклейки-шары; сид 1 (#1131): стринги широкими трусами; сид 2 (#1133): блик кольцом вокруг наклейки, читается как глаз
PASTIES = "small flat matte black pasties lying flush on the skin over the nipples"
PASTY_AT, PASTY_R = ((68.5, 87.5), (76.5, 88.5)), 1.7    # вершины груди: блики классики, на строку ниже - по складке груди основы; база 320x200
PASTY_ZONE = (82, 94, 62, 84)                       # строки и столбцы, где искать наклейки модели
PASTY_LAYER = RACE + "__3__PASTIES"                 # слот 3 пустой у всех голых броней
GROIN_SHADOW, GROIN_DEPTH = (77.5, 113.0, 2.2, 4.0), 0.6    # просвет между бёдер у классики: столбец 77, строки 107-114
REDRAW, VARIANTS = 3, []
FEET_AT = {"L": (44, 122, "right"), "R": (69, 122, "left")}    # левый верхний угол кадра 32x32, с какой стороны картинки большой палец
FEET_FROM = 136                                     # кадр ступни рисует отсюда вниз: выше голень основы
FEET_SEEDS, FEET_SEED, FEET_STRENGTH = [0, 1], 0, 0.85
FEET_GREY, FEET_CHROMA = (12, 25), 0.3              # цветность и светлота подложки кадра; доля цветности кадра, что остаётся
FEET_TEXT = ("Close-up of one bare foot of {who} with {skin} skin, part of a hand-painted paper-doll portrait for an X-COM-style "
             "strategy game, soft light from the upper left, on a flat grey panel. The foot stands flat, seen from the front, toes "
             "towards the viewer at the bottom of the picture, the same size and in the same place as in the input. It has exactly "
             "five clearly separated toes with rounded tips and dark creases between them, the big toe on the {big} of the "
             "picture, small neat toenails in the same colour as the skin. A slim feminine foot with a visible ankle and instep. "
             "Smooth skin with soft satin highlights. Painted game art, not a photo. No ground, no shadow, no text.")
GLOSSLESS_FEET = ", paw, hoof, mitten, sock, shoe, sandal, claws, talons, webbed toes, merged toes, white nails, painted nails, extra toes"
# у классики этих кож много тёмной тени и яркие блики: по медиане тело выходит темнее, чем видит глаз, и темнее лица (лист #1134)
LIFT = {"F0": 5, "M0": 8, "M4": 6}
BODY_FROM_ROW = 74                                  # выше кадр тела не рисует
# костюм: одна поднятая рука своя, опущенную руку голого тела классика закрывает чёрным клином; окно на груди показывает кожу внешности
SUIT = RACE + "__7__SYNTH_SUIT"
SUIT_SEEDS = [0, 1]
SUIT_WEDGE_MIN = 100                                # чёрное пятно больше этого в точках 320x200 - клин, рисует код; мелкие - тени костюма
SUIT_STRENGTH = 0.7                                 # 0.85: фигура уже силуэта и надутая игрушка (#1147)
SUIT_PANEL = (14, 14, 18, 255)                      # подложка кадра: то, что модель оставит внутри силуэта, читается контуром, а не серой каймой (R-089)
SUIT_RIM = (22, 8, 10, 136)                         # кайма: цветность меньше, светлота больше, от края не дальше (k=4), выше строки сапог (там блики тоже серые)
SUIT_CLEAN = False                                  # Vitali 05.11: слой на слой как есть; True - зелёное и кайму убирает код
SUIT_TEXT = ("{style} {who}, wearing a skin-tight one-piece muscle suit of wet-looking dark blue-steel synthetic polymer with sharp "
             "silvery-blue specular highlights: sculpted bulging muscles on the arms, broad shoulders and thick thighs, fibrous muscle "
             "strands running along them, filling the outline of the input completely. "
             "Glossy violet-magenta parts of the same material: the high collar at the throat, the broad band under the bust, the "
             "raised fist and the other hand. Heavy glossy black boots with violet edges. Her right arm is raised and bent with "
             "the fist at the height of her head, exactly as in the input. "
             "Her skin, face, hair and the open window of the suit over the bust stay exactly as in the input. "
             "Realistic material, painted game art, not a photo.")
SUIT_NEGATIVE = (", leather, buckles, pouches, belts, straps, zipper, pockets, logo, text, metal plates, robot, mechanical joints, cape, "
                 "cloth folds, toy, balloon, inflated, plastic figurine, cartoon, horizontal stripes, green, grey outline")
_low_hair = None


def skin_of(look):
    return SKIN[look[0] + str(int(look[1:]) // 4 * 4)]


def classic_parts(look):
    """Слоя головы нет: голова - всё выше шеи в слое тела."""
    body = db.load_indices(P.FILES["%s__2__%s_NUDE" % (RACE, look)])
    bm = body != 0
    hm = bm.copy()
    hm[NECK_ROW:] = False
    torso = bm.copy()
    torso[:NECK_ROW + 5] = False
    halves = np.nonzero(np.bincount(body[torso] // 8, minlength=32) / float(torso.sum()) >= 0.02)[0]
    pad = np.pad(bm, 1)
    inner = pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    return bm, hm, inner, np.isin(body // 8, halves)


def low_hair():
    """Волосы на плечах - общие у всех 16, у чёрных волос по полурампам не найти (чёрное есть и в контуре торса): объединение
    пятен всех внешностей, идущих от шеи вниз. Основа F4 под ними остаётся чёрной, кадр головы всегда их закрывает."""
    global _low_hair
    if _low_hair is None:
        out = np.zeros((db.H, db.W), bool)
        for look in LOOKS:
            bm, _h, inner, ramps = classic_parts(look)
            cand = bm & inner & ~ramps
            cand[:HAIR_FROM_ROW] = False
            cand[HAIR_TO_ROW:] = False
            lab, n = pb.label(cand, 8)
            for i in range(1, n + 1):
                m = lab == i
                if m.sum() >= 10 and np.nonzero(m)[0].min() <= NECK_ROW + 5:
                    out |= m
        _low_hair = out
    return _low_hair


_hair_zone = P.hair_zone


def hair_zone(look, box):
    keep = np.zeros((db.H, db.W), bool)
    keep[box[1]:box[3], box[0]:box[2]] = True
    return _hair_zone(look, box) | (low_hair() & keep)


def passport(files, pal, look):
    d = P.LOOKS[look]
    return {"look": look, "skin": skin_of(look), "skin_rgb": None, "hair": HAIR % d["hair"], "hair_rgb": None,
            "face": "an oval face, large almond-shaped eyes with %s irises, dark pupils and small highlights, a small straight nose, soft lips, a slight smile" % d["eyes"],
            "head": "", "makeup": MAKEUP, "neck": "", "items": [], "recolor": [],
            "face_to_body": skin_of(look) == SKIN["M4"]}      # бурая тень классики на красной коже: модель рисует половину лица бурой (#1130)


def common():
    dp.RACE, dp.BODY, dp.HEAD = RACE, 2, 10
    P.FILES, P.PAL = db.sprite_files(), db.game_palette()
    cp.FILES, cp.PAL = P.FILES, P.PAL
    P.WHO = WHO
    P.NEGATIVE = P.NEGATIVE + NEGATIVE_RACE
    P.FACE_BOX = rh.FACE_BOX = FACE_BOX
    P._classic_parts = rh.classic_parts = classic_parts
    P.hair_zone = hair_zone
    P.passport = passport
    P.THONG = THONG
    P.HAND_ROWS, P.HAND_X = HAND_ROWS, HAND_X
    P.STRAP_ROWS = STRAP_ROWS
    P.CHEST_LINES = ()
    P.FEET_ROW = FEET_ROW
    P.classic_marks = lambda look: np.zeros((db.H, db.W), bool)
    P.FILL_EDGES = False
    P.FACE_TORSO = (82, 100, 64, 92)
    P.FACE_LIMIT = (45.0, 45.0)


def setup_bodies():
    common()
    P.skin_name = lambda rgb: SKIN[BASE]
    P.BODY = P.BODY.replace("A woman's figure with a full bust - never a man.",
                            "A woman's figure with a natural bust of the same size and shape as in the input - never a man.")
    P.BODY = P.BODY.replace("small round black pasties over the nipples", PASTIES)
    P.BODY = P.BODY.replace(", a detailed face with clear eyes, brows and lips", "")
    assert "natural bust" in P.BODY and PASTIES in P.BODY and "detailed face" not in P.BODY


def pasties_on(canvas8):
    """Наклейки тёмными кругами на входе кадра, как стринги в P.thong_on: без них модель кладёт левую на край груди и торчит за контур."""
    s = 4                                           # край без лесенки
    m = Image.new("L", (canvas8.size[0] * s, canvas8.size[1] * s), 0)
    d = ImageDraw.Draw(m)
    for x, y in PASTY_AT:
        r = PASTY_R * dp.Z * s
        cx, cy = (x - dp.CROP[0]) * dp.Z * s, (y - dp.CROP[1]) * dp.Z * s
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    out = canvas8.copy()
    out.paste((16, 16, 18, 255), (0, 0), m.resize(canvas8.size, Image.LANCZOS))
    return out


def body_job(i, look, s=None):
    """Только от шеи вниз: голову кладёт кадр головы, а здесь она выходила детской."""
    j = rb.job(i, look, s)
    below = j["sil"].copy()
    below[:BODY_FROM_ROW] = False
    j["mask"] = P.mask8(below)
    j["init"] = pasties_on(j["init"])
    return j


def red_input(j, look):
    """Красная кожа: тени классики на лице и ухе лежат на бурой рампе, и модель рисовала половину лица бурой (#1130, #1132).
    На вход кадра эта рампа идёт красной; маска - по M4, у него чёрные волосы, форма волос у всех одна."""
    idx = db.load_indices(P.FILES["%s__2__M4_NUDE" % RACE])
    rgb = np.asarray(P.PAL)[:, :3].astype(np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    brown = (r > g) & (g > b) & (g / np.maximum(r, 1e-3) > 0.3) & (r < 0.8)
    m = brown[idx] & P.skin_cover("M4")
    only = np.zeros(m.shape, bool)                  # только лицо с шеей и ухо: в волосах M4 тоже есть бурое, на блондинке M6 оно вышло красным пятном
    only[60:NECK_ROW, 68:86] = only[54:68, 84:97] = True
    m &= only
    b4 = j["b4"]
    w = cv2.GaussianBlur((ws.sil4(m) > 0.5).astype(np.float32), (0, 0), 2.0)[b4[1]:b4[3], b4[0]:b4[2]]
    im = j["init"].convert("RGB")
    w = cv2.resize(w, im.size, interpolation=cv2.INTER_LINEAR)[..., None]
    lab = bp._rgb_to_lab(np.asarray(im, np.float32) / 255.0)
    t = np.clip(lab[..., 0] / 50, 0.4, 1)
    red = np.dstack([lab[..., 0], 70 * t, 45 * t])
    out = bp._lab_to_rgb(lab * (1 - w) + red * w)
    j["init"] = Image.fromarray(np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8), "RGB")
    return j


def run_stage(stage, flags, frames, raw):
    """Рабочий процесс на недостающие кадры: память карты кончится - новый продолжит."""
    for attempt in range(3):
        if all(os.path.exists(os.path.join(raw, j["tag"] + "_out.png")) for j in frames):
            break
        r = subprocess.run([sys.executable, os.path.abspath(__file__), stage, "--worker"] + flags)
        print("рабочий процесс вышел с кодом %s (попытка %d)" % (r.returncode, attempt + 1), flush=True)
    missing = [j["tag"] for j in frames if not os.path.exists(os.path.join(raw, j["tag"] + "_out.png"))]
    if missing:
        raise SystemExit("не нарисованы: %s" % missing)


def bodies(ns):
    rb.RACE, rb.OUT = RACE, OUT
    rb.TORSO = {BASE: TORSO}
    rb.NEG_ABS = {BASE}
    rb.RESEED = {BASE: REDRAW}
    rb.SHEET_BOX = (50, 44, 110, 152)
    rb.SHEET_TORSO = (54, 78, 106, 124)
    for d in ("raw", "bases"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    setup_bodies()
    jobs = [body_job(0, BASE)] + [body_job(0, BASE, s) for s in VARIANTS]
    if ns.worker:
        rb.worker(jobs)
        return
    if not ns.dry_run:
        run_stage("bodies", [], jobs, os.path.join(OUT, "raw"))
    rb.finish(jobs, ns.dry_run)
    if not ns.dry_run:
        shutil.copy2(os.path.join(OUT, "bases", BASE.lower() + ".png"), os.path.join(OUT, "bases", "f4_body.png"))    # дальше fixbase


def feet_jobs(seeds=None):
    """Ступень отдельным кадром: в кадре всего тела она 40-50 точек, и модель рисует лапу, сколько пальцев ни проси."""
    rb.RACE, rb.OUT = RACE, OUT
    common()
    base = Image.open(os.path.join(OUT, "bases", "f4_body.png")).convert("RGBA")
    names = [n for n in rb.names_of(BASE) if n in P.FILES]
    cl = dp.classic(P.FILES, P.PAL, names)
    sil = dp.layer_mask(P.FILES, names[0])
    w, h, z = P.RUN["item"]["w"], P.RUN["item"]["h"], P.RUN["item"]["zoom"]
    pz = {"skin": SKIN[BASE], "face": "a calm look", "neck": "", "hair": "", "head": ""}
    out = []
    for side, (x, y, big) in FEET_AT.items():
        box = (x, y, x + w, y + h)
        b4 = tuple(v * dp.K for v in box)
        m = sil.copy()
        m[:FEET_FROM] = False
        m4 = ws.sil4(m)[b4[1]:b4[3], b4[0]:b4[2]] > 0.5
        start = Image.new("RGBA", base.size, dp.PANEL + (255,))
        start.alpha_composite(base)
        for s in seeds if seeds is not None else FEET_SEEDS:
            out.append({"tag": "feet_%s_s%d" % (side, s), "side": side, "kind": "item", "box": box, "b4": b4, "seed": P.RUN["seed"] + 700 + s,
                        "prompt": FEET_TEXT.format(who=WHO, skin=SKIN[BASE], big=big), "negative": P.negative_for(pz) + GLOSSLESS_FEET,
                        "init": start.crop(b4).resize((w * z, h * z), Image.LANCZOS),
                        "mask": Image.fromarray(m4.astype(np.uint8) * 255).resize((w * z, h * z), Image.NEAREST),
                        "control": vc.control_map(cl.crop(box), z, "gray")})
    return out


def feet_worker(jobs):
    raw = os.path.join(OUT, "raw")
    painter = None
    for j in jobs:
        done = os.path.join(raw, j["tag"] + "_out.png")
        if os.path.exists(done):
            continue
        if painter is None:
            painter = P.Painter([x["prompt"] for x in jobs] + [x["negative"] for x in jobs])
            print("модель загружена за %d с" % painter.load_s, flush=True)
        try:
            rgb, _s0 = painter.paint(j["init"], j["mask"], j["control"], j["prompt"], j["seed"], j.get("strength", FEET_STRENGTH), P.RUN["item"]["control"], j["negative"])
        except Exception as e:                      # память карты: новый процесс продолжит
            print("кадр %s упал: %s" % (j["tag"], str(e)[:300]), flush=True)
            sys.exit(75)
        Image.fromarray(rgb).save(done)
        print("  %s готов" % j["tag"], flush=True)


def feet(ns):
    jobs = feet_jobs()
    if ns.worker:
        feet_worker(jobs)
        return
    run_stage("feet", [], jobs, os.path.join(OUT, "raw"))
    feet_sheet(jobs)


def feet_sheet(jobs):
    tiles = [Image.open(os.path.join(OUT, "raw", j["tag"] + "_out.png")).convert("RGB").resize((320, 320), Image.LANCZOS) for j in jobs]
    sheet = Image.new("RGB", (320 * len(tiles), 320))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * 320, 0))
    sheet.save(os.path.join(OUT, "feet.png"))


def strip_pasties(rgb, alpha):
    """Наклейки модели -> кожа. Модель кладёт левую на край груди и раздувает, если нарисовать её на входе (#1137), поэтому свои рисуются поверх."""
    k = dp.K
    lab = bp._rgb_to_lab(rgb / 255.0)
    dark = np.zeros(alpha.shape, np.uint8)
    y0, y1, x0, x1 = (v * k for v in PASTY_ZONE)
    dark[y0:y1, x0:x1] = lab[y0:y1, x0:x1, 0] <= 30
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))     # контур тела тоньше, левая наклейка у края узкая
    n, lb, st, _c = cv2.connectedComponentsWithStats(dark, connectivity=8)
    round_ = np.zeros(alpha.shape, np.uint8)
    for i in range(1, n):
        bw, bh, area = st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT], st[i, cv2.CC_STAT_AREA]
        if max(bw, bh) <= 1.6 * min(bw, bh) and area >= 0.5 * bw * bh:     # складка под грудью - дуга, её не трогать: левая наклейка срезана краем, заполнение 0.55
            round_[lb == i] = 1
    hole = cv2.dilate(round_, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
    known = (alpha > 0.9) & ~hole
    fill, c = P._blur_in(rgb, known, 3.0)
    for s in (8.0, 20.0):
        f2, c2 = P._blur_in(rgb, known, s)
        a = np.clip(c / 0.2, 0, 1)[..., None]
        fill, c = fill * a + f2 * (1 - a), np.maximum(c, c2)
    d = cv2.distanceTransform((alpha > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    fill = fill * (0.7 + 0.3 * np.clip(d / 10, 0, 1))[..., None]      # у края тело темнеет, как везде: иначе плоское пятно до контура; глубже - бурая тень на красной коже
    w = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 2.0)[..., None]
    w = np.maximum(w, hole[..., None].astype(np.float32))
    return rgb * (1 - w) + fill * w, int(hole.sum())


def pasties_layer():
    """Кружки отдельным слоем: тело без них, слой только у голых броней (Vitali 05.11). Круг со сглаженным краем, верх чуть светлее."""
    k, s = dp.K, 4
    out = np.zeros((db.H * k, db.W * k, 4), np.float32)
    for x, y in PASTY_AT:
        cx, cy, r = x * k, y * k, PASTY_R * k
        x0, y0, x1, y1 = int(cx - r - 3), int(cy - r - 3), int(cx + r + 4), int(cy + r + 4)
        yy, xx = np.mgrid[y0:y1:1.0 / s, x0:x1:1.0 / s]
        inside = np.hypot((xx + 0.125 - cx), (yy + 0.125 - cy)) <= r
        cov = cv2.resize(inside.astype(np.float32), (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
        tone = np.clip(1 - (np.arange(y0, y1) - (cy - r)) / (2 * r), 0, 1)[:, None, None]
        out[y0:y1, x0:x1, :3] = np.array((16, 16, 19), np.float32) + tone * 12
        out[y0:y1, x0:x1, 3] = cov * 255
    os.makedirs(os.path.join(OUT, "pasties"), exist_ok=True)
    Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, "pasties", PASTY_LAYER.lower() + ".png"))


def groin_shadow(rgb):
    """Между бёдер под стрингами у классики тёмное, модель кладёт туда светлый штрих."""
    k = dp.K
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy, rx, ry = GROIN_SHADOW
    t = np.clip(1 - np.hypot((xx - cx * k) / (rx * k), (yy - cy * k) / (ry * k)), 0, 1)
    t = np.clip(t * 2.2, 0, 1) ** 1.2
    return rgb * (1 - GROIN_DEPTH * t)[..., None]


def paste_foot(rgb, alpha, j):
    """Кадр ступни на основу: тон по щиколотке, шов мягкий, альфа - силуэт классики минус подложка кадра (R-620)."""
    k = dp.K
    x0, y0, x1, y1 = j["b4"]
    fr8 = np.asarray(Image.open(os.path.join(OUT, "raw", j["tag"] + "_out.png")).convert("RGB"), np.float32)
    fr = cv2.resize(fr8, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
    sil4 = alpha[y0:y1, x0:x1]
    band = np.zeros(sil4.shape, bool)
    band[(FEET_FROM + 1) * k - y0:(FEET_FROM + 4) * k - y0] = True
    band &= sil4 > 0.9
    lab_f, lab_b = bp._rgb_to_lab(fr / 255.0), bp._rgb_to_lab(rgb[y0:y1, x0:x1] / 255.0)
    grey = (np.hypot(lab_f[..., 1], lab_f[..., 2]) < FEET_GREY[0]) & (lab_f[..., 0] > FEET_GREY[1])     # подложка - по цвету кадра, до сдвига тона
    target = np.median(lab_b[band], axis=0)
    lab_n = lab_f + (target - np.median(lab_f[band], axis=0))
    lab_n[..., 1:] = target[1:] + (lab_n[..., 1:] - target[1:]) * FEET_CHROMA      # розовые кончики и голубой подъём: кожа одна
    fr = bp._lab_to_rgb(lab_n) * 255.0
    ramp = np.clip((np.arange(y0, y1) - (FEET_FROM + 1) * k) / (4.0 * k), 0, 1)[:, None]
    outside = sil4 <= 0.5
    _n, lb = cv2.connectedComponents((grey | outside).astype(np.uint8), connectivity=4)
    touch = np.unique(lb[outside])
    cut = np.isin(lb, touch[touch > 0]) & ~outside
    keep = cv2.morphologyEx((~cut & ~outside).astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    fig = np.clip((cv2.GaussianBlur(keep.astype(np.float32), (0, 0), 0.8) - 0.35) / 0.3, 0, 1)
    out, a = rgb.copy(), alpha.copy()
    t = ramp[..., None]
    out[y0:y1, x0:x1] = rgb[y0:y1, x0:x1] * (1 - t) + fr * t
    a[y0:y1, x0:x1] = alpha[y0:y1, x0:x1] * (1 - ramp) + sil4 * fig * ramp
    return out, a


def fixbase():
    """f4_body.png (как нарисовала модель) -> f4.png: свои наклейки, тень в паху, ступни с пальцами. Без видеокарты."""
    im =np.asarray(Image.open(os.path.join(OUT, "bases", "f4_body.png")).convert("RGBA"), np.float32)
    rgb, alpha = im[..., :3].copy(), im[..., 3] / 255.0
    rgb, n = strip_pasties(rgb, alpha)
    print("под наклейками модели точек:", n)
    rgb = groin_shadow(rgb)                         # наклейки - после перекраски (assemble): кривая кожи делает их край зубчатым
    jobs = {(j["side"], j["tag"]): j for j in feet_jobs([FEET_SEED])}
    for (_side, tag), j in jobs.items():
        if os.path.exists(os.path.join(OUT, "raw", tag + "_out.png")):
            rgb, alpha = paste_foot(rgb, alpha, j)
        else:
            print("кадра нет, ступня прежняя:", tag)
    out = np.dstack([rgb, alpha * 255])
    Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, "bases", BASE.lower() + ".png"))


def assemble():
    import doll_race_assemble as ra
    ra.RACE, ra.OUT = RACE, OUT
    ra.BASE, ra.BASES, ra.BY_EYE = {BASE: BASE}, (BASE,), {}
    ra.ROW, ra.HEAD_ROW = NECK_ROW, FACE_BOX[3]
    ra.TORSO = (84, 110)
    ra.CROTCH = CROTCH
    ra.SPOT_MIN = 10 ** 6                           # пятна на бёдрах классики здесь рамповая тень, не косметика: выходили синяками
    ra.WIDE_SKIN = True                             # иначе глубокая тень основы лиловым ореолом на чужой коже, блики белыми (#1130, #1132)
    ra.LIFT = {n: LIFT.get(n[0] + str(int(n[1:]) // 4 * 4), 0) for n in LOOKS}
    ra.SHEET_BOX = (50, 44, 110, 152)
    ra.GROUPS = "loknar_groups.json"
    with open(os.path.join(ra.ROOT, ra.GROUPS), "w", encoding="utf-8-sig") as f:
        json.dump({BASE: LOOKS}, f)
    sys.argv = sys.argv[:1]
    ra.main()
    pasties_layer()


def heads(ns):
    rh.RACE, rh.OUT = RACE, OUT
    rh.BODIES = os.path.join(OUT, "assembled")
    rh.HEADS = os.path.join(OUT, "heads")
    rh.NECK_ROW = NECK_ROW
    rh.SHEET_CLOSE = (58, 44, 100, 96)
    rh.SHEET_FULL = (50, 44, 110, 152)
    for d in ("raw", "layers"):
        os.makedirs(os.path.join(rh.HEADS, d), exist_ok=True)
    rh.setup(os.path.join(HERE, "doll_looks_loknar.json"))
    common()
    P.HEAD = HEAD
    looks = ns.looks.split(",") if ns.looks else LOOKS
    jobs = [rh.job(LOOKS.index(look), look) for look in looks]
    jobs = [red_input(j, j["look"]) if skin_of(j["look"]) == SKIN["M4"] else j for j in jobs]
    if ns.worker:
        rh.worker(jobs)
        return
    if not ns.dry_run:
        run_stage("heads", ["--looks", ",".join(looks)], rh.frames(jobs), os.path.join(rh.HEADS, "raw"))
    rh.finish(jobs, ns.dry_run)


def suit_masks():
    """-> весь слой, клин: большое чёрное пятно классики. Модель его не рисует, иначе в нём появятся складки и блики."""
    idx = db.load_indices(P.FILES[SUIT])
    dark = (idx != 0) & (db.to_rgba(idx, P.PAL)[..., :3].sum(2) < 24)
    n, lb, st, _c = cv2.connectedComponentsWithStats(dark.astype(np.uint8), connectivity=8)
    wedge = np.zeros(dark.shape, bool)
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] >= SUIT_WEDGE_MIN:
            wedge |= lb == i
    return idx != 0, wedge


def body_layer(look):
    return Image.open(os.path.join(OUT, "heads", "layers", "%s__2__%s_nude.png" % (RACE.lower(), look.lower()))).convert("RGBA")


def armor_jobs():
    """Кадр брони как ступень 4 пилота: вход - готовая кукла F4 и B2 костюма, маска - костюм без клина, контроль - классика серым."""
    common()
    whole, wedge = suit_masks()
    canvas = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), SUIT_PANEL)
    canvas.alpha_composite(body_layer(BASE))
    bl, _m = dp.b2_layer(SUIT)
    canvas.alpha_composite(bl)
    ctl = vc.control_map(dp.classic(P.FILES, P.PAL, ["%s__2__%s_NUDE" % (RACE, BASE), SUIT]).crop(dp.CROP), dp.Z, "gray")
    return [{"tag": "armor_synth_s%d" % s, "seed": P.RUN["seed"] + 100 + s, "strength": SUIT_STRENGTH,
             "prompt": SUIT_TEXT.format(style=P.STYLE, who=WHO), "negative": P.NEGATIVE + SUIT_NEGATIVE,
             "init": P.to8(canvas), "mask": P.mask8(whole & ~wedge, P.RUN["armor"]["grow8"]), "control": ctl} for s in SUIT_SEEDS]


def suit_rim(rgb, lab, whole):
    """Модель рисует фигуру уже силуэта: у края бледная муть. Альфу не трогать (под ней голое тело), муть -> тёмный контур, как у классики."""
    chroma, light, far, row = SUIT_RIM
    d = cv2.distanceTransform((ws.sil4(whole) > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    rim = (np.hypot(lab[..., 1], lab[..., 2]) < chroma) & (lab[..., 0] > light) & (d > 0) & (d <= far)
    rim[row * dp.K:] = False
    n, lb = cv2.connectedComponents(rim.astype(np.uint8), connectivity=8)
    touch = np.unique(lb[rim & (d <= 2)])
    w = cv2.GaussianBlur(np.isin(lb, touch[touch > 0]).astype(np.float32), (0, 0), 1.5)[..., None]
    return rgb * (1 - w) + np.array(SUIT_PANEL[:3], np.float32) * w


def armor_layer(rgb8):
    """Ответ кадра -> слой: тон от классики, альфа и окно - силуэт классики x4, клин чёрный со сглаженным краем."""
    whole, wedge = suit_masks()
    names = ["%s__2__%s_NUDE" % (RACE, BASE), SUIT]
    f4, d0, d1 = P.tone_lock(P.full4(rgb8), names, whole & ~wedge)
    if SUIT_CLEAN:
        lab = bp._rgb_to_lab(f4 / 255.0)
        lab[..., 1] = np.maximum(lab[..., 1], 0.0)  # зелёных цветов в костюме нет, модель кладёт их в блики
        f4 = bp._lab_to_rgb(lab) * 255.0
        f4 = suit_rim(f4, lab, whole)
    layer = np.asarray(P.layer_from(f4, whole), np.float32).copy()
    w = ws.sil4(wedge)[..., None]
    col = np.median(db.to_rgba(db.load_indices(P.FILES[SUIT]), P.PAL)[wedge][:, :3], axis=0)
    layer[..., :3] = layer[..., :3] * (1 - w) + col * w
    return Image.fromarray(np.clip(layer + 0.5, 0, 255).astype(np.uint8), "RGBA"), d0, d1


def armor(ns):
    jobs = armor_jobs()
    if ns.worker:
        feet_worker(jobs)
        return
    raw, out = os.path.join(OUT, "raw"), os.path.join(OUT, "armor")
    os.makedirs(out, exist_ok=True)
    for j in jobs:
        j["init"].convert("RGB").save(os.path.join(raw, j["tag"] + "_in.png"))
        j["mask"].save(os.path.join(raw, j["tag"] + "_mask.png"))
    if not ns.dry_run:
        run_stage("armor", [], jobs, raw)
    box = tuple(v * dp.K for v in (40, 44, 110, 152))
    W, H = box[2] - box[0], box[3] - box[1]
    bg = (40, 42, 50, 255)

    def on(look, layer):
        c = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), bg)
        c.alpha_composite(body_layer(look))
        c.alpha_composite(layer)
        return c.crop(box).convert("RGB")

    classic = dp.classic(P.FILES, P.PAL, ["%s__2__%s_NUDE" % (RACE, BASE), SUIT]).resize((db.W * dp.K, db.H * dp.K), Image.NEAREST)
    cl = Image.new("RGBA", classic.size, bg)
    cl.alpha_composite(classic)
    rows = [[cl.crop(box).convert("RGB")]]
    for j in jobs:
        rgb8 = np.asarray(j["init"].convert("RGB")) if ns.dry_run else np.asarray(Image.open(os.path.join(raw, j["tag"] + "_out.png")).convert("RGB"))
        layer, d0, d1 = armor_layer(rgb8)
        layer.save(os.path.join(out, j["tag"] + ".png"))
        print("%s: тон dE %.1f -> %.1f" % (j["tag"], d0, d1), flush=True)
        rows.append([on(look, layer) for look in (BASE, "F0", "M0", "M4")])
    sheet = Image.new("RGB", (W * 4, H * len(rows)), bg[:3])
    for y, row in enumerate(rows):
        for x, t in enumerate(row):
            sheet.paste(t, (x * W, y * H))
    sheet.save(os.path.join(out, "armor_synth.png"))
    print("лист:", os.path.join(out, "armor_synth.png"), sheet.size, flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=("bodies", "feet", "fixbase", "assemble", "heads", "armor"))
    ap.add_argument("--looks", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--worker", action="store_true", help="(служебное) рисовать недостающие кадры подряд")
    ns = ap.parse_args()
    if ns.stage == "bodies":
        bodies(ns)
    elif ns.stage == "feet":
        feet(ns)
    elif ns.stage == "fixbase":
        fixbase()
    elif ns.stage == "assemble":
        assemble()
    elif ns.stage == "armor":
        armor(ns)
    else:
        heads(ns)


if __name__ == "__main__":
    main()
