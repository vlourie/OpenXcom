"""Головы MHUMAN: тот же конвейер, что у FHUMAN (doll_race_heads.py), лицо мужское, описания doll_looks_mhuman.json.
Выход art/doll/pipe_pilot/mhuman/heads/. В мод не ставит.

В описании внешности необязательные поля (заметки Vitali 06.11): who - кто он (возраст, европеец, азиат), skin - кожа словами вместо замера, neg - что запретить.

  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_mhuman_heads.py --looks M43,F25 [--dry-run]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_mhuman_bodies as M                      # до numpy: пилот ставит окружение модели
import build_pack as bp
import cv2
import doll_race_heads as H
import numpy as np

P = M.P
FEMALE_MAKEUP = ("Makeup: {makeup}; the bright colours around the eyes and on the lips of the input "
                 "are cosmetics on bare skin: eyeshadow is soft and only on the eyelids, lipstick only on the lips, the eyes "
                 "are natural and never glow, the skin around the mouth is clean.")
FEMALE_FACE = ("A pretty young "
               "woman's face with smooth unlined skin and soft feminine features: clear eyes with irises and highlights, "
               "neat brows, a small nose, soft lips.")
FACIAL = ("beard", "moustache", "mustache", "stubble", "goatee", "sideburns")
MARKS = (("scar", ", scars"), ("tattoo", ", face tattoo"), ("paint", ", war paint, face paint stripes"))
YOUTH_NEG = "old man, middle-aged, mature face, wrinkles, nasolabial folds, sagging skin, tired face, "
FACE_NEG = ", smile, grin, smirk, open mouth, teeth, big eyes, large eyes, wide eyes, bulging eyes"
NO_GLOW = "the eyes are natural and never glow"
SKIN_L = 8                                          # центр окна ±8 у skin_match: лицо только светлеет, до 16. Медиана лица классики занижена бородой и дизерингом, затемнение давало лицо чернее тела (M35, F29, Vitali 06.11; F8, F20, M38)
SKIN_LIT = 12                                       # сверх SKIN_L: самое тёмное лицо светлеет не больше чем на 12
LIT_PCT = 65
base_setup = H.setup
base_passport = P.passport
base_skin_match = P.skin_match


def passport(files, pal, look):
    """Случайные слова лица из паспорта звали улыбку и большие глаза (a slight smirk, large eyes): у мужчин лицо одно, строгое."""
    pz = base_passport(files, pal, look)
    d = P.LOOKS[look]
    pz["face"] = "a stern calm look, a closed mouth, natural eyes of ordinary size"
    pz["skin"] = d.get("skin", pz["skin"])
    pz["who"] = d.get("who", P.WHO)
    pz["neg"] = d.get("neg", "")
    return pz


def head_text(pz):
    t = P.HEAD.format(who=pz["who"], skin_c=pz["skin"].capitalize(), hair=pz["hair"], face=pz["face"], neck=P.neck_text(pz),
                      makeup=pz["makeup"], head="He has %s. " % pz["head"] if pz["head"] else "")
    return t.replace("; " + NO_GLOW, "") if "glowing" in pz["head"] else t


def negative_for(pz):
    t = " ".join((pz["hair"], pz["head"], pz["neck"], pz["makeup"]))
    neg = base_negative(pz)
    assert YOUTH_NEG in neg
    neg = neg.replace(YOUTH_NEG, "") + FACE_NEG + (", " + pz["neg"] if pz["neg"] else "")
    for key, words in MARKS:
        if key in t:
            neg = neg.replace(words, "")
    return neg if any(k in t for k in FACIAL) else neg + ", beard, moustache, stubble"


base_negative = H.P.negative_for


def skin_match(rgb, look, region, sample=None, near=None):
    if near is None:
        return base_skin_match(rgb, look, region, sample)
    _o, d = base_skin_match(rgb, look, region, sample)
    if d is None:
        return base_skin_match(rgb, look, region, sample, near)
    lift = float(np.clip(lit_gap(rgb, look, region, sample), 0, SKIN_LIT))
    return base_skin_match(rgb, look, region, sample, (SKIN_L + lift, near[1], near[2]))


def lit_gap(rgb, look, region, sample):
    """На сколько освещённая кожа лица классики светлее рисунка: нижний край окна сдвига. Медиана на тёмном лице с бородой этого не видит (F6, F8, F20)."""
    dp = P.dp
    cov1 = P.skin_cover(look) & region
    cov = P.ws.sil4(cov1 if sample is None else cov1 & sample) > 0.5
    cov = cv2.erode(cov.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=2) > 0
    names = [n for n in ("%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look), "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look)) if n in P.FILES]
    cl = np.asarray(dp.classic(P.FILES, P.PAL, names).resize((P.db.W * dp.K, P.db.H * dp.K), P.Image.NEAREST).convert("RGB"), np.float32)
    Lc = cv2.GaussianBlur(bp._rgb_to_lab(cl / 255.0)[..., 0], (0, 0), dp.K)
    Ld = bp._rgb_to_lab(rgb / 255.0)[..., 0]
    sel = cov & (Ld > 22)
    if sel.sum() < 100:
        return 0.0
    return np.percentile(Lc[cov], LIT_PCT) - np.percentile(Ld[sel], LIT_PCT)


def setup(looks_file):
    base_setup(looks_file)
    M.setup()
    assert FEMALE_MAKEUP in P.HEAD and FEMALE_FACE in P.HEAD
    P.HEAD = P.HEAD.replace(FEMALE_MAKEUP, "Colours on the face: {makeup}; " + NO_GLOW + ".").replace(
        FEMALE_FACE, "A rugged adult man's face with masculine features: clear eyes with irises and highlights, strong brows, a strong nose and jaw, natural lips.")
    # «X-COM-style» модель написала буквами на лбу M4 (R-781)
    P.HEAD = P.HEAD.replace("an X-COM-style strategy game", "a strategy game")
    assert "X-COM" not in P.HEAD
    P.head_text = head_text
    P.negative_for = negative_for
    P.passport = passport
    P.skin_match = skin_match


H.RACE = "MHUMAN"
H.OUT = os.path.join(H.db.ROOT, "art", "doll", "pipe_pilot", "mhuman")
H.BODIES = os.path.join(H.OUT, "assembled")
H.HEADS = os.path.join(H.OUT, "heads")
H.FACE_BOX = (76, 55, 85, 67)
H.NECK_ROW = 67
H.setup = setup

if __name__ == "__main__":
    H.main()
