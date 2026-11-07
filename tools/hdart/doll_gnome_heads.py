"""Головы GNOME: тот же конвейер, что у FHUMAN (doll_race_heads.py), описания doll_looks_gnome.json. F и M в имени не пол: все - взрослые женщины.
У всех широкая улыбка с зубами и рука у рта: кисть с длинными тёмно-красными ногтями у угла губ, предплечье и плечо - в слоях HEAD и HAIR,
поэтому кадр выше обычного (до локтя). Рога и крылья волос (F14..F16, M5, M6) шире кадра лица - для них кадр шире и мельче.
Выход art/doll/pipe_pilot/gnome/heads/. В мод не ставит.

  py -3.13 tools/gpuq.py add --name doll_gnome_heads --prio 1 -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_gnome_heads.py --paint --looks F9,F14,M5,M13
  --dry-run - без модели: входы кадров и зоны на листе.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_gnome_bodies as O                       # до numpy: пилот ставит окружение модели
import doll_race_heads as H
import numpy as np

P = H.P
SKIN_ROW = 88                                       # кожу тела мерить ниже: рука у рта и пряди в слое головы доходят до строки 87 и ниже (F7, F12) - торса выше слоя головы нет
FACE = ("a wide toothy grin showing white teeth; her raised hand is at her mouth, the fingertips with long dark red nails touching "
        "the corner of her lips, the hand is empty and holds nothing, the bare forearm coming up from below exactly as in the input")
FRAME = {"w": 40, "h": 48, "zoom": 20}               # до локтя руки у рта: строка 87; стороны кадра кратны 32 (800x960)
WIDE = {"w": 64, "h": 48, "zoom": 14}                # 896x672
WIDE_LOOKS = {"F14", "F15", "F16", "M5", "M6"}
TALL = {"F7": {"w": 40, "h": 96, "zoom": 12}}       # прядь F7 до строки 138: в кадр 48 не влезала, вне кадра серое пятно у бедра (480x1152)
NEG = (", chibi, baby face, childlike proportions, young girl, glowing eyes, beard, fantasy hat, pointed hat, "
       "food, meat, pizza, fruit, holding an object")    # проба 07.11: F14 держала у рта кусок мяса, в классике кисть пустая
base_setup, base_job, base_passport, base_neg = H.setup, H.job, P.passport, P.negative_for


def setup(looks_file):
    base_setup(looks_file)
    O.places()
    P.HEAD = P.HEAD.replace("an X-COM-style strategy game", "a strategy game")    # R-781, как у MHUMAN
    assert "X-COM" not in P.HEAD
    P.passport = passport
    P.negative_for = negative_for


def classic_parts(look):
    """Как H.classic_parts, но кожа - тело ниже SKIN_ROW вне слоёв головы и волос."""
    bn, hn, rn = H.names_of(look)
    body = H.db.load_indices(P.FILES[bn])
    head = H.db.load_indices(P.FILES[hn])
    hair = H.db.load_indices(P.FILES[rn]) if rn in P.FILES else np.zeros_like(head)
    bm, hm = body != 0, (head != 0) | (hair != 0)
    idx = np.where(hair != 0, hair, np.where(head != 0, head, body))
    torso = bm & ~hm
    torso[:SKIN_ROW] = False
    halves = np.nonzero(np.bincount(body[torso] // 8, minlength=32) / float(torso.sum()) >= 0.02)[0]
    allm = bm | hm
    pad = np.pad(allm, 1)
    inner = pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    return bm, hm, inner, np.isin(idx // 8, halves)


def passport(files, pal, look):
    """Паспорт мерит кожу ниже слоя головы: слой головы для него обрезан по шее (рука и пряди ниже - не голова)."""
    hp = files["%s__10__HEAD_%s" % (O.RACE, look)]
    load = P.db.load_indices

    def cut(p):
        a = load(p)
        if p == hp:
            a = a.copy()
            a[O.NECK_ROW + 2:] = 0
        return a
    P.db.load_indices = cut
    try:
        pz = base_passport(files, pal, look)
    finally:
        P.db.load_indices = load
    pz["face"] = FACE
    return pz


def negative_for(pz):
    return base_neg(pz) + NEG


def job(i, look):
    P.RUN["head"].update(TALL.get(look) or (WIDE if look in WIDE_LOOKS else FRAME))
    return base_job(i, look)


H.RACE = O.RACE
H.OUT = O.OUT
H.BODIES = os.path.join(H.OUT, "assembled")
H.HEADS = os.path.join(H.OUT, "heads")
H.FACE_BOX = O.FACE_BOX
H.NECK_ROW = O.NECK_ROW
H.RESEED = {"F14": 100, "M5": 100, "M20": 100, "M19": 100, "M14": 100}     # лист 07.11: лицо разъехалось (F14, M5, M20), белое пятно у рта (M19), бурые пятна в волосах (M14)
H.SHEET_CLOSE = (56, 42, 106, 92)
H.SHEET_FULL = (44, 40, 118, 148)
H.setup = setup
H.job = job
H.classic_parts = classic_parts

if __name__ == "__main__":
    H.main()
