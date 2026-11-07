"""Головы OGRE: тот же конвейер, что у MHUMAN (doll_mhuman_heads.py), описания doll_looks_ogre.json.
F и M в имени у этой расы не пол: фигура у всех одна. Выход art/doll/pipe_pilot/ogre/heads/. В мод не ставит.

  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_ogre_heads.py --looks M14,F14 [--dry-run]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_ogre_bodies as O                        # до numpy: пилот ставит окружение модели
import doll_mhuman_heads as MH

H, P = MH.H, MH.P
base_setup = MH.setup


def setup(looks_file):
    base_setup(looks_file)
    O.places()


H.RACE = O.RACE
H.OUT = O.OUT
H.BODIES = os.path.join(H.OUT, "assembled")
H.HEADS = os.path.join(H.OUT, "heads")
H.FACE_BOX = O.FACE_BOX
H.NECK_ROW = O.NECK_ROW
H.NECK_SEAM = 48
H.NECK_SPOTS = {"M10": [(72, 56, 4)], "F8": [(92, 57, 4), (68, 58, 2)], "F1": [(83, 62, 3)], "M9": [(82, 62, 3)], "M7": [(79, 61, 3)]}
H.SHEET_CLOSE = (58, 34, 104, 84)
H.SHEET_FULL = (44, 34, 118, 150)
H.setup = setup

if __name__ == "__main__":
    H.main()
