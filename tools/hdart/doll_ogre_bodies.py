"""Тело OGRE: перепись 07.11: контур ниже шеи у всех 32 внешностей один (расхождение до 2 точек), кож пять. Основа - одна, на бледной коже M14, ниже шеи и без головы (R-693).
На теле `hd` узкие чёрные плавки, голое только в `hd_18+`. Выход art/doll/pipe_pilot/ogre/. В мод не ставит.

  py -3.13 tools/gpuq.py add --name doll_ogre_body -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_ogre_bodies.py
  --dry-run - без модели: вход кадра и лист.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_mhuman_bodies as M                      # до numpy: пилот ставит окружение модели
from PIL import ImageDraw

R, P = M.R, M.P
dp, vc = R.dp, M.R.vc
RACE = "OGRE"
OUT = os.path.join(M.db.ROOT, "art", "doll", "pipe_pilot", "ogre")
BASE = "M14"
HEAD_ROW = 58                                       # выше - голова, её кладёт кадр головы
NECK_ROW = 60
FACE_BOX = (73, 46, 88, 60)                         # сетка 07.11: брови - строка 47, глаза - 49, рот - 57, подбородок - 59
WHO = "a huge hulking muscular adult male ogre, 35 years old"
TORSO = ("Massive powerful build with huge rounded shoulders, a barrel chest, thick bulging arms and thighs and a heavy muscular belly, "
         "exactly as in the input.")
BODY = ("{style} {who} with {skin} skin, seen from the shoulders down, bare arms and legs, huge hands with thick fingers, big bare feet with "
        "clearly painted toes. A massive male figure - never a woman. He wears only narrow plain black briefs. Keep the colours of the input "
        "exactly: the same skin colour. Painted detail of skin, veins and muscles.")
EXTRA_NEG = ", chibi, baby face, childlike proportions, body hair, fur, armor, belt, head, face"


def places():
    dp.RACE = RACE
    # места на теле: сетка M0 и F14 крупно, 07.11 (пах - строка 104, середина 80; кисти - строки 88..103)
    P.FACE_BOX = FACE_BOX
    P.THONG = [(65, 93), (80, 95), (96, 93), (97, 98), (87, 101), (83, 105), (78, 105), (74, 101), (64, 98)]
    P.HAND_ROWS, P.HAND_X = (88, 104), (60, 102)
    P.STRAP_ROWS = (90, 105)
    P.FEET_ROW = 136
    P.WHO = WHO


def setup():
    M.setup()
    places()
    P.BODY = BODY
    P.skin_name = lambda rgb: "pale pinkish-tan"
    R.BUST = ", nude, genitals, woman"


def job(i, look, s=None):
    j = M.job(i, look, s)
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
    j["negative"] += EXTRA_NEG
    return j


R.RACE = RACE
R.OUT = OUT
R.names_of = lambda look: ["%s__2__%s_NUDE" % (RACE, look)]
R.TORSO = {BASE: TORSO}
R.NEG_ABS = set()
R.RESEED = {BASE: 1}                                # s0 - плоский живот, s2 - плавки кирпичом; лист 07.11
R.VARIANTS = {BASE: [0, 1, 2]}
R.SHEET_BOX = (44, 54, 118, 150)
R.SHEET_TORSO = (50, 58, 110, 106)
R.setup = setup
R.job = job

if __name__ == "__main__":
    R.main()
