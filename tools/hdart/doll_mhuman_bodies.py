"""Тела MHUMAN: по кадру на торс (32 группы мерки doll_body_census.py), тот же рисовальщик, что у doll_race_bodies.py.

На теле `hd` мужчины в узких чёрных плавках, голое только в `hd_18+`. Метки торса (волосы на груди, татуировки) словами, форму держит контроль.
Выход art/doll/pipe_pilot/mhuman/. В мод не ставит.

  py -3.13 tools/gpuq.py add --name doll_mhuman_bodies -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_mhuman_bodies.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_race_bodies as R                        # до numpy: пилот ставит окружение модели
import numpy as np
import doll_b2_render as db
import doll_ctl_pilot as cp
import doll_photo_pilot as dp

P = R.P
STRONG = "Heavily muscular build, broad chest, thick arms and thighs, defined abdominal muscles, exactly as in the input."
HAIRY = " Dark chest hair down the middle of the chest and stomach, as in the input."
MARK = " The dark marks of the input stay in the same place: %s."
WIDE_HAIR = " Thick dark chest hair in a wide patch across the chest and a line down the stomach to the navel, as in the input."
PLAIN = ("M43", "M11", "M15", "M37", "M45", "M1", "M38", "M41")
CHEST_HAIR = ("M18", "F25", "M9", "F5")
TORSO = {k: STRONG for k in PLAIN}
TORSO.update({k: STRONG + HAIRY for k in CHEST_HAIR})
MARKS = {"M36": "a blue tattoo emblem on the chest",
         "M3": "a dark purple tattoo across the chest", "F39": "a small dark tattoo in the middle of the chest",
         "F42": "two mirrored dark blue line-art fish tattoos facing each other across the chest",
         "M63": "small dark tattoos on the chest and one arm", "F33": "a small dark cross tattoo on the chest",
         "M16": "black leather straps around the chest and the neck, joined by a silver metal ring at the centre of the upper chest, and a black bracer on one forearm"}
TORSO.update({k: STRONG + MARK % v for k, v in MARKS.items()})
# заметки Vitali 06.11: тёмные пятна на груди классики - волосы, а не краска и не татуировки
TORSO.update({"F45": STRONG + " Mottled yellow-olive skin, as in the input.",
              "M55": STRONG + " Mottled rust-orange skin with ochre patches, brown hair on the chest, as in the input.",
              "F55": STRONG + " Pale silver-lilac synthetic skin, as in the input. Black chest hair only on the upper chest, the stomach and the waist are smooth bare skin.",
              "F47": "Heavy stocky strong build with a thick firm waist, thick arms and thighs, as in the input.",
              "F49": STRONG + " The whole body is covered in coarse reddish-brown fur with lighter tips, as in the input.",
              "F58": STRONG + " Pale pink skin. Bare shoulders with no hair on them.",
              "F61": STRONG + " Pale pink skin. Dense dark body hair on the chest, the stomach, the arms and the legs, as in the input.",
              "F37": STRONG + WIDE_HAIR,
              "F46": STRONG + WIDE_HAIR,
              "M6": STRONG + " Patchy dark chest hair spreading across the chest and down the stomach, as in the input.",
              "M32": STRONG + " Warm orange-tan skin." + WIDE_HAIR,
              "M39": STRONG + " Sparse dark chest hair in the middle of the chest.",
              "M42": STRONG + " A narrow line of dark chest hair down the middle of the chest and stomach with a little hair across the chest, as in the input."})
SKIP_NEG = (", tattoo, body art", ", black marks on the skin", ", symbols, circuit pattern, printed pattern on the skin")
EXTRA_NEG = {"F47": ", fat belly, beer belly, big round belly", "F49": ", black fur", "F58": ", long hair on the shoulders, locks of hair on the chest",
             "F61": ", green hair, green skin", "M32": ", olive skin, green skin, yellow skin", "M55": ", green skin, acid yellow skin, red spots, green spots",
             "F37": ", purple mark, purple stripe", "F46": ", purple mark", "M39": ", blue tattoo", "M42": ", cross tattoo", "F55": ", black armor plate, fur at the waist, hair on the stomach, fur skirt"}
base_job = R.job


def setup():
    R.dp.RACE = "MHUMAN"
    P.FILES, P.PAL = db.sprite_files(), db.game_palette()
    cp.FILES, cp.PAL = P.FILES, P.PAL
    # места на теле MHUMAN: замер по строкам 06.11 (пах - строка 102, середина 80; кисти - строки 94..106)
    P.FACE_BOX = (76, 55, 85, 67)
    P.THONG = [(67, 92.5), (80, 94), (93, 92.5), (94, 97), (86, 100), (82.5, 103.5), (77.5, 103.5), (74, 100), (66, 97)]
    P.HAND_ROWS, P.HAND_X = (94, 106), (62, 99)
    P.STRAP_ROWS = (88, 104)
    P.CHEST_LINES = ()
    P.FEET_ROW = 136
    P.classic_marks = lambda look: np.zeros((db.H, db.W), bool)
    P.FILL_EDGES = False
    P.WHO = "a fit muscular adult man, 30 years old"
    P.BODY = ("{style} {who} with {skin} skin, bare arms and legs, bare feet with clearly painted toes. His hair lies only where it lies in the "
              "input. {neck} {face}. A man's figure - never a woman. He wears only narrow plain black briefs. Keep the colours of the input exactly: "
              "the same skin colour, the same hair colour and cut. Painted detail of skin and muscles, a detailed face with clear eyes and brows.")
    P.neck_text = lambda pz: "Around his neck: %s." % pz["neck"] if pz["neck"] else "His neck is bare."
    old = "man, male, masculine face, beard, stubble, flat male chest, "
    assert old in P.NEGATIVE
    P.NEGATIVE = P.NEGATIVE.replace(old, "woman, female, breasts, feminine face, ").replace("old woman", "old man")
    R.BUST = ", nude, genitals"
    R.NEG_ABS = set()


def job(i, look, s=None):
    j = base_job(i, look, s)
    if look in MARKS or look in ("F45", "M55"):
        for x in SKIP_NEG:
            j["negative"] = j["negative"].replace(x, "")
    j["negative"] += EXTRA_NEG.get(look, "")
    return j


R.RACE = "MHUMAN"
R.OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", "mhuman")
R.HAIR = 13                                         # слоя волос нет: names_of отбрасывает его сам
R.TORSO = TORSO
R.RESEED = {k: 1 for k in ("F37", "F46", "F42", "F47", "F49", "F55", "F58", "F61", "M16", "M39", "M42", "M55", "M32", "M6", "M3")}   # заметки Vitali 06.11
R.RESEED["F55"] = 2                                 # s1: чёрный мех вокруг плавок
R.VARIANTS = {}
R.setup = setup
R.job = job

if __name__ == "__main__":
    assert len(TORSO) == 32, len(TORSO)
    R.main()
