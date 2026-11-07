"""Тела NEKOMIMI: по кадру на позу и особый окрас, ниже шеи и без головы (R-693: большая голова классики даёт детские пропорции).

У расы 96 тел, но поз две, размера фигуры три (MAXI, MIDI, MINI), а особых окрасов семь (мерка 07.11). На теле `hd` наклейки и стринги, голое только в `hd_18+`.
Выход art/doll/pipe_pilot/nekomimi/. В мод не ставит.

  py -3.13 tools/gpuq.py add --name doll_neko_bodies -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_neko_bodies.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_race_bodies as R                        # до numpy: пилот ставит окружение модели
import cv2
import numpy as np
from PIL import Image, ImageDraw
import doll_b2_render as db
import doll_ctl_pilot as cp
import doll_neko_classic as NC
import doll_photo_pilot as dp
import vx_control as vc

P = R.P
FIG = ("A strong curvy adult figure: wide hips, a narrow waist, muscular thighs, a soft belly with a navel, "
       "%s, exactly as in the input.")
BUST = {"MAXI": "a natural large full bust", "MIDI": "a natural full bust", "MINI": "a natural small bust"}
FOLDED = " Both arms are folded across her chest and cover it, exactly as in the input."
GLOVED = (" Sheer tan nylon bodystocking from under the bust down to the ankles, dark purple-black long evening gloves on both arms up to the "
          "upper arms, dark purple-black thigh-high boots on both legs, exactly as in the input.")
TIGER = " Golden-yellow skin with dark red-brown tiger stripes across the thighs, the hips and the arms, exactly as in the input."
BANDS = " Pale pink skin with charcoal-grey tiger stripe markings across the thighs and the shins, exactly as in the input."
BLACK = " Charcoal-black smooth matte skin with soft grey highlights from the shoulders down to the toes, exactly as in the input."
BLUE = " Deep blue skin. Dark charcoal-grey knee-high boots, exactly as in the input."
INDIGO = " Deep blue skin that darkens to indigo on the shins and the feet, exactly as in the input."
VIOLET = " Dusky violet skin that darkens on the shins and the feet, exactly as in the input."
SPECIAL = {"M10": GLOVED, "M5": TIGER, "M14": BANDS, "F3": BLACK, "F7": BLUE, "F23": INDIGO, "M23": VIOLET}
PLAIN = ("F1", "F0", "F12")                         # по основе на размер: остальные кошки перекрашены с них
TORSO = {k: FIG % BUST[NC.size_of(k)] for k in PLAIN}
TORSO.update({k: FIG % BUST[NC.size_of(k)] + v for k, v in SPECIAL.items()})
TORSO.update({"A" + k: v + FOLDED for k, v in list(TORSO.items())})
TORSO["AF7"] = FIG % BUST["MINI"] + INDIGO + FOLDED     # сапоги у F7 только в позе NUDE
# #1206: M10 одна перчатка и один сапог; F3 рыжие голени; F7 светлые сапоги; M5, AM14 обрывки по прядям на плечах, у AM14 чёрные знаки
# #1207, #1208: чёрный шар на кисти у F0, F12, AF0, AF12, M23, AF7, AM14 и надпись X-COM у M10 (R-781); M14 s1 без торса - остался s0
# #1209: M10 s2 короткие перчатки и сапоги - взят s1 (надпись над плечами в зоне волос), F12 s1 и AF12 s1 смазаны по прядям, AM14 s2 без руки на груди
# #1214: M10 s1 плечи срезаны у закрашенной надписи (R-805), M23 s1 светлые кисти; M10 s3 надписи, s5 короткие перчатки; M23 s2 шар на кисти (R-804)
RESEEDS = {"F3": 1, "F7": 1, "M5": 1, "AM5": 1, "F0": 1, "F12": 2, "AF0": 1, "AF12": 2, "M23": 4, "M10": 4, "AF7": 2, "AM14": 2}
NO_HAIR = ("M5", "AM5", "AM14", "F12", "AF12")      # пряди лежат на плечах и груди, волосы всё равно ставит кадр головы
EXTRA_NEG = {"F3": ", brown boots, brown legs, orange legs"}
SKIP_NEG = {"M10": (", bracelet", ", gloves", ", boots"), "M5": (", tattoo, body art", ", black marks on the skin", ", printed pattern on the skin"),
            "M14": (", tattoo, body art", ", black marks on the skin", ", printed pattern on the skin"), "F3": (), "F7": (", boots",)}
THONGS = {"": [(71, 90), (79.5, 94.5), (88, 90), (88, 91.5), (81, 96.5), (80.5, 98.5), (78.5, 98.5), (78, 96.5), (71, 91.5)],
          "A": [(70, 91), (79, 94.5), (85.5, 91), (85.5, 92.5), (80.5, 96.5), (80, 98.5), (78.5, 98.5), (77.5, 96.5), (70, 92.5)]}
base_job = R.job


def without_hair(j, look):
    """Вход и контроль без прядей слоя волос ниже шеи: модель видит на их месте кожу."""
    hair = db.load_indices(P.FILES[NC.real_hair(look)]) != 0
    hair[:NC.HEAD_ROW] = False
    sil = j["sil"] & ~hair
    sil |= (cv2.morphologyEx(sil.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0) & hair   # щель между ног не трогать: назад только пряди
    sil[:NC.HEAD_ROW] = j["sil"][:NC.HEAD_ROW]
    j["sil"] = sil
    x0, y0, x1, y1 = dp.CROP
    init = np.asarray(j["init"].convert("RGB")).copy()
    big = cv2.resize(hair[y0:y1, x0:x1].astype(np.uint8), (init.shape[1], init.shape[0]), interpolation=cv2.INTER_NEAREST)
    big = cv2.dilate(big, np.ones((3, 3), np.uint8))
    j["init"] = Image.fromarray(np.dstack([cv2.inpaint(init, big, 5, cv2.INPAINT_TELEA), np.full(init.shape[:2], 255, np.uint8)]), "RGBA")
    a = np.asarray(j["classic"].convert("RGBA")).copy()
    a[..., :3] = cv2.inpaint(a[..., :3], hair.astype(np.uint8), 2, cv2.INPAINT_TELEA)
    a[..., 3] = sil * 255
    j["classic"] = Image.fromarray(a, "RGBA")


def setup():
    dp.RACE, dp.BODY, dp.HEAD = NC.RACE, 2, 10
    P.FILES, P.PAL = NC.bind(db.sprite_files()), db.game_palette()
    cp.FILES, cp.PAL = P.FILES, P.PAL
    NC.patch_b2(dp, P.FILES)
    P.FACE_BOX = NC.FACE_BOX
    P.HAND_ROWS, P.HAND_X = (59, 86), (71, NC.HEAD_X)
    P.STRAP_ROWS = (88, 99)
    P.CHEST_LINES = ()
    P.FEET_ROW = 136
    P.classic_marks = lambda look: np.zeros((db.H, db.W), bool)
    P.FILL_EDGES = False
    P.WHO = "a fit athletic adult woman, 28 years old"
    P.BODY = ("{style} {who} with {skin} skin, seen from the neck down, bare arms and legs, bare feet with clearly painted toes. {neck} "
              "A grown woman's figure with a natural bust of the same size and shape as in the input - never a man. "
              "She wears only minimal black underwear that any outfit covers: two small flat round black pasties, one on each nipple, and a "
              "narrow black thong. Her hands are bare and empty, nothing on the arms. Keep the colours of the input exactly: the same skin "
              "colour. Painted detail of skin and muscles.")
    P.STYLE = P.STYLE.replace("an X-COM-style strategy game", "a strategy game").replace(", no text.", ".")    # R-781
    assert "mature face, " in P.NEGATIVE
    P.NEGATIVE = P.NEGATIVE.replace("mature face, ", "") + ", chibi, baby face, childlike proportions, young girl, ball, sphere, black ball"
    P.neck_text = lambda pz: ""


def job(i, look, s=None):
    P.THONG = THONGS["A" if look[0] == "A" else ""]
    j = base_job(i, look, s)
    if look in NO_HAIR:
        without_hair(j, look)
    sil = j["sil"].copy()
    sil[:NC.HEAD_ROW, :NC.HEAD_X] = False
    j["sil"], j["mask"] = sil, P.mask8(sil)
    # головы нет ни во входе, ни в контроле: только так модель не читает её пропорции (R-693)
    w, h = (NC.HEAD_X - dp.CROP[0]) * dp.Z, (NC.HEAD_ROW - dp.CROP[1]) * dp.Z
    init = j["init"].copy()
    ImageDraw.Draw(init).rectangle((0, 0, w, h), fill=dp.PANEL + (255,))
    j["init"] = init
    cl = j["classic"].copy()
    ImageDraw.Draw(cl).rectangle((0, 0, NC.HEAD_X - 1, NC.HEAD_ROW - 1), fill=(0, 0, 0, 0))
    j["control"] = vc.control_map(cl.crop(dp.CROP), dp.Z, "gray")
    for x in SKIP_NEG.get(NC.key_of(look), ()):
        j["negative"] = j["negative"].replace(x, "")
    j["negative"] += EXTRA_NEG.get(look, "")
    return j


R.RACE = NC.RACE
R.OUT = NC.OUT
R.names_of = lambda look: ["%s__2__%s_NUDE" % (NC.RACE, look)]
R.TORSO = TORSO
R.RESEED = RESEEDS
R.NEG_ABS = set(TORSO)
R.BUST = ", huge breasts, breast implants, nude, genitals"
R.VARIANTS = {}
R.SHEET_BOX = (56, 60, 106, 146)
R.SHEET_TORSO = (60, 66, 100, 104)
R.setup = setup
R.job = job

if __name__ == "__main__":
    assert len(TORSO) == 20, len(TORSO)
    R.main()
