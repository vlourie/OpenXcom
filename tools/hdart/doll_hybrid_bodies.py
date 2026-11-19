"""Тела HYBRID: перепись 07.11: форм две, F0 (8 тел) и M1 (8 тел), кожа у всех одна. По кадру на форму, ниже шеи и без головы (R-693).
На теле `hd` у женской формы наклейки и стринги, у мужской узкие чёрные плавки, голое только в `hd_18+`. Выход art/doll/pipe_pilot/hybrid/. В мод не ставит.

  py -3.13 tools/gpuq.py add --name doll_hybrid_bodies --prio 1 -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_hybrid_bodies.py
  --dry-run - без модели: вход кадра и лист.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_race_bodies as R                        # до numpy: пилот ставит окружение модели
import numpy as np
from PIL import ImageDraw
import doll_b2_render as db
import doll_ctl_pilot as cp
import doll_photo_pilot as dp
import vx_control as vc

P = R.P
RACE = "HYBRID"
OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", "hybrid")
HEAD_ROW = 64                                       # выше - голова, её кладёт кадр головы
NECK_ROW = 67
FACE_BOX = (73, 50, 88, 66)                         # сетка 07.11: глаза - строка 59, рот - 63, подбородок - 65
CHILD_NEG = ", chibi, baby face, childlike proportions, head, face, alien, grey alien, ball, sphere, black ball"
F_BODY = ("{style} {who} with {skin} skin, seen from the shoulders down, bare arms and legs, bare feet with clearly painted toes. "
          "A grown woman's figure with a natural bust of the same size and shape as in the input - never a man. She wears only minimal black "
          "underwear that any outfit covers: two small flat round black pasties, one on each nipple, and a narrow black thong. Her hands are bare "
          "and empty, nothing on the arms. Keep the colours of the input exactly: the same skin colour. Painted detail of skin and muscles.")
M_BODY = ("{style} {who} with {skin} skin, seen from the shoulders down, bare arms and legs, bare feet with clearly painted toes. "
          "A grown man's figure - never a woman. He wears only narrow plain black briefs. His hands are bare and empty, nothing on the arms. "
          "Keep the colours of the input exactly: the same skin colour. Painted detail of skin and muscles.")
# места на теле: сетка F0 и M1 крупно, 07.11
FORMS = {"F": {"who": "a lean strong adult woman, 30 years old", "body": F_BODY, "bust": ", huge breasts, breast implants, nude, genitals",
               "thong": [(71, 91), (80, 96), (89, 91), (89, 92.5), (81.5, 97), (81, 99.5), (79, 99.5), (78.5, 97), (71, 92.5)],
               "hands": ((95, 106), (65, 96)), "strap": (88, 99)},
         "M": {"who": "a lean muscular adult man, 30 years old", "body": M_BODY, "bust": ", nude, genitals, woman",
               "thong": [(68, 92.5), (80, 94), (92, 92.5), (93, 97), (86, 100), (82.5, 103.5), (77.5, 103.5), (74, 100), (67, 97)],
               "hands": ((95, 107), (64, 97)), "strap": (90, 105)}}
TORSO = {"F0": "A lean strong figure with a narrow waist, slim arms and long legs, a flat stomach with a clear centre line, exactly as in the input.",
         "M1": "A lean muscular build with broad shoulders, a narrow waist, sinewy arms and legs and defined abdominal muscles, exactly as in the input."}
NEGATIVE = {}
base_job, base_clean = R.job, P.clean_body


def place(look):
    """У расы две формы: места на теле и слова - свои у каждой."""
    f = FORMS[look[0]]
    P.WHO, P.BODY, P.THONG, P.STRAP_ROWS = f["who"], f["body"], f["thong"], f["strap"]
    P.HAND_ROWS, P.HAND_X = f["hands"]
    P.NEGATIVE = NEGATIVE[look[0]]
    R.BUST = f["bust"]


def clean_body(f4, look):
    place(look)
    return base_clean(f4, look)


def setup():
    dp.RACE = RACE
    P.FILES, P.PAL = db.sprite_files(), db.game_palette()
    cp.FILES, cp.PAL = P.FILES, P.PAL
    P.FACE_BOX = FACE_BOX
    P.CHEST_LINES = ()
    P.FEET_ROW = 136
    P.classic_marks = lambda look: np.zeros((db.H, db.W), bool)
    P.FILL_EDGES = False
    P.neck_text = lambda pz: ""
    P.STYLE = P.STYLE.replace("an X-COM-style strategy game", "a strategy game").replace(", no text.", ".")    # R-781
    assert "mature face, " in P.NEGATIVE
    old = "man, male, masculine face, beard, stubble, flat male chest, "
    assert old in P.NEGATIVE
    NEGATIVE["F"] = P.NEGATIVE.replace("mature face, ", "") + CHILD_NEG + ", young girl"
    NEGATIVE["M"] = P.NEGATIVE.replace(old, "woman, female, breasts, feminine face, ").replace("old woman", "old man").replace("mature face, ", "") + CHILD_NEG + ", boy"
    P.clean_body = clean_body


def job(i, look, s=None):
    place(look)
    j = base_job(i, look, s)
    sil = j["sil"].copy()
    sil[:HEAD_ROW] = False
    j["sil"], j["mask"] = sil, P.mask8(sil)
    # головы нет ни во входе, ни в контроле (R-693)
    init = j["init"].copy()
    ImageDraw.Draw(init).rectangle((0, 0, init.size[0], (HEAD_ROW - dp.CROP[1]) * dp.Z), fill=dp.PANEL + (255,))
    j["init"] = init
    cl = j["classic"].copy()
    ImageDraw.Draw(cl).rectangle((0, 0, cl.size[0], HEAD_ROW - 1), fill=(0, 0, 0, 0))
    j["control"] = vc.control_map(cl.crop(dp.CROP), dp.Z, "gray")
    return j


R.RACE = RACE
R.OUT = OUT
R.names_of = lambda look: ["%s__2__%s_NUDE" % (RACE, look)]
R.TORSO = TORSO
R.NEG_ABS = set()
R.RESEED = {"F0": 1}                                # лист 07.11: s0 и s2 - кубики и мужской торс; M1 s1 - полосы по коже
R.VARIANTS = {"F0": [0, 1, 2], "M1": [0, 1, 2]}
R.SHEET_BOX = (44, 54, 118, 150)
R.SHEET_TORSO = (52, 62, 108, 110)
R.setup = setup
R.job = job

if __name__ == "__main__":
    R.main()
