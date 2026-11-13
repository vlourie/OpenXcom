"""Тела GNOME: перепись 07.11: ниже шеи фигура у всех 48 внешностей одна (F и M в имени - не пол, все женские), расходятся только пряди
волос из слоя тела и край в точку; кож две (полурампы 185 и 187). Основа одна - F9 (светлая кожа, волос на теле нет), ниже шеи и без головы (R-693).
Рука у рта - в слое головы (HEAD и HAIR) от плеча до кисти: её рисует кадр головы, тело даёт только плечо.
На теле `hd` наклейки и стринги, голое только в `hd_18+`. Выход art/doll/pipe_pilot/gnome/. В мод не ставит.

  py -3.13 tools/gpuq.py add --name doll_gnome_bodies --prio 1 -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_gnome_bodies.py
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
RACE = "GNOME"
OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", "gnome")
BASE = "F9"
HEAD_ROW = 73                                       # выше - голова, её кладёт кадр головы
NECK_ROW = 76
FACE_BOX = (75, 62, 86, 73)                         # сетка F9 07.11: глаза - строка 66, рот - 70, подбородок - 72; кисть у рта правее, x 82..89
CHILD_NEG = ", chibi, baby face, childlike proportions, head, face, ball, sphere, black ball"
WHO = "a slim adult woman, 30 years old"
BODY = ("{style} {who} with {skin} skin, seen from the shoulders down, bare arms and legs, bare feet with clearly painted toes. "
        "A grown woman's figure with a natural bust of the same size and shape as in the input - never a man. She wears only minimal black "
        "underwear that any outfit covers: two small flat round black pasties, one on each nipple, and a narrow black thong. Her hanging hand is "
        "bare and empty, with long dark red fingernails, nothing on the arms. Keep the colours of the input exactly: the same skin colour. "
        "Painted detail of skin and muscles.")
TORSO = ("A slim adult figure with a narrow waist, a full bust, slender arms and long legs; one arm hangs down, the other is bent with "
         "the forearm raised toward the top of the picture, exactly as in the input.")
base_job = R.job


def places():
    """Места на теле: сетка F9 крупно, 07.11 (бёдра - строка 94, пах - 103, висящая кисть - строки 96..105)."""
    dp.RACE = RACE
    P.FACE_BOX = FACE_BOX
    P.WHO = WHO
    P.THONG = [(72, 94), (80, 99), (89, 94), (89, 95.5), (81.5, 100), (81, 103), (79, 103), (78.5, 100), (72, 95.5)]
    P.HAND_ROWS, P.HAND_X = (96, 106), (54, 70)
    P.STRAP_ROWS = (91, 103)
    P.FEET_ROW = 142


def setup():
    P.FILES, P.PAL = db.sprite_files(), db.game_palette()
    cp.FILES, cp.PAL = P.FILES, P.PAL
    places()
    P.BODY = BODY
    P.CHEST_LINES = ()
    P.classic_marks = lambda look: np.zeros((db.H, db.W), bool)
    P.FILL_EDGES = False
    P.neck_text = lambda pz: ""
    P.STYLE = P.STYLE.replace("an X-COM-style strategy game", "a strategy game").replace(", no text.", ".")    # R-781
    assert "mature face, " in P.NEGATIVE
    P.NEGATIVE = P.NEGATIVE.replace("mature face, ", "") + CHILD_NEG + ", young girl, teenager"
    R.BUST = ", huge breasts, breast implants, nude, genitals"


def job(i, look, s=None):
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
R.TORSO = {BASE: TORSO}
R.NEG_ABS = set()
R.RESEED = {BASE: 1}                                # лист 07.11: s0 - стринги ниткой, s2 - ноги перекачаны
R.VARIANTS = {BASE: [0, 1, 2]}
R.SHEET_BOX = (44, 60, 112, 148)
R.SHEET_TORSO = (54, 70, 104, 108)
R.setup = setup
R.job = job

if __name__ == "__main__":
    R.main()
