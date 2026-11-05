"""Куклы Локк'Наар (LOKNAR): одна основа и 16 голов; настройки расы поверх общих скриптов doll_race_bodies, _assemble, _heads.

Перепись 05.11: силуэт всех 16 внешностей совпадает попиксельно, тело одно, кож четыре (F0-3 графит, F4-7 бледно-лиловая, M0-3 бирюза,
M4-7 красная; M в имени - тоже женская фигура). Слоя головы нет: голова и волосы лежат в слое тела, поэтому кадр головы идёт в слой NUDE.
Основа рисуется на самой светлой коже F4, остальные кожи - кривой светлота -> цвет (doll_race_assemble). Выход art/doll/pipe_pilot/loknar/.

  py -3 tools/gpuq.py add --name doll_loknar_base -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_race_loknar.py bodies
  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_race_loknar.py assemble
  py -3 tools/gpuq.py add --name doll_loknar_heads -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_race_loknar.py heads --looks F4,F0,M0,M4
  --dry-run - без модели: входы кадров и зоны на листах.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_pipe_pilot as P                         # до numpy: пилот ставит окружение модели
import cv2
import numpy as np
from PIL import Image
import build_pack as bp
import doll_b2_render as db
import doll_ctl_pilot as cp
import doll_photo_pilot as dp
import doll_race_bodies as rb
import doll_race_heads as rh
import photo_base as pb
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
REDRAW, VARIANTS = 3, []
# у классики этих кож много тёмной тени и яркие блики: по медиане тело выходит темнее, чем видит глаз, и темнее лица (лист #1134)
LIFT = {"F0": 5, "M0": 8, "M4": 6}
BODY_FROM_ROW = 74                                  # выше кадр тела не рисует
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


def body_job(i, look, s=None):
    """Только от шеи вниз: голову кладёт кадр головы, а здесь она выходила детской."""
    j = rb.job(i, look, s)
    below = j["sil"].copy()
    below[:BODY_FROM_ROW] = False
    j["mask"] = P.mask8(below)
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


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=("bodies", "assemble", "heads"))
    ap.add_argument("--looks", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--worker", action="store_true", help="(служебное) рисовать недостающие кадры подряд")
    ns = ap.parse_args()
    if ns.stage == "bodies":
        bodies(ns)
    elif ns.stage == "assemble":
        assemble()
    else:
        heads(ns)


if __name__ == "__main__":
    main()
