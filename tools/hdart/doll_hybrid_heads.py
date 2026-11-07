"""Головы HYBRID: тот же конвейер, что у MHUMAN (doll_mhuman_heads.py), описания doll_looks_hybrid.json. F - женское лицо, M - мужское, все взрослые.
Гибрид - помесь пришельца и человека (Vitali 07.11, R-838): большие тёмные раскосые глаза, широкий череп, узкий подбородок; карикатуру с глазами в пол-лица не брать (R-834).
Выход art/doll/pipe_pilot/hybrid/heads/. В мод не ставит.

  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_hybrid_heads.py --looks F0,M1 [--dry-run]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_mhuman_heads as MH                      # до numpy: пилот ставит окружение модели
import doll_hybrid_bodies as O
import cv2
import numpy as np
from PIL import Image

H, P = MH.H, MH.P
RACE = O.RACE
K = H.dp.K
WHO = {"F": "a bald adult alien-human hybrid woman, 30 years old, with a high domed hairless head", "M": "a bald lean adult alien-human hybrid man, 40 years old, with a high domed hairless head"}
MALE_FACE = "A rugged adult man's face with masculine features: clear eyes with irises and highlights, strong brows, a strong nose and jaw, natural lips."
HUMAN_EYES = "natural eyes of ordinary size"
EYES = "large dark slanted almond-shaped eyes, wider than human eyes and tilted up toward the temples, set in dark sunken sockets, no eyebrows"
FACE = {"F": "A grown half-alien woman's face, half human and half alien, with mature features, a broad cranium tapering to a narrow jaw and a small pointed chin: " + EYES + ", a small narrow nose, small natural lips.",
        "M": "A grown half-alien man's lean face, half human and half alien, with hard features, a broad cranium tapering to a narrow jaw and a small pointed chin: " + EYES + ", a small narrow nose, thin natural lips."}
MALE_NEG = "woman, female, breasts, feminine face, "
FEMALE_NEG = "man, male, masculine face, "
NEG = (", ordinary human face, cartoon alien, eyes filling half the face, insect eyes, head hair, eyebrows, "
       "dark outline around the head, chibi, baby face, childlike proportions, teenager, young girl, boy")
NECK_MARKS = {"F2": "F0", "F3": "F0"}               # что есть в теле классики и нет в теле соседа ниже шеи - бусы
CODE_MARKS = {"F2"}
OUTLINE = 9                                         # чёрный контур классики вокруг лысой головы: модель его срисовывает, толщина k=4
OUTLINE_L = 105                                     # контур и его переход к коже, светлота LAB
EYE_BAND = (51, 55, 63, 66)                         # строки: над глазами контур снимается глубоко, на уровне глаз только край, ниже - до SIDE_CUT * 2
OUTLINE_AB = 24
CHIN_ROW = 64
SIDE_CUT = 4
RIM = 3
SKIN_AB = 8                                         # лицо у модели желтее тела: кроме светлоты цветность тоже к классике
base_setup = MH.setup
base_text, base_neg, base_pass, base_skin = MH.head_text, MH.negative_for, MH.passport, MH.skin_match
base_compose = H.compose


def form(pz):
    return "F" if "woman" in pz["who"] else "M"


def passport(files, pal, look):
    pz = base_pass(files, pal, look)
    pz["who"] = WHO[look[0]]
    return pz


def head_text(pz):
    f = form(pz)
    t = base_text(pz).replace(MALE_FACE, FACE[f])
    assert HUMAN_EYES in t
    t = t.replace(HUMAN_EYES, "dark slanted eyes")
    return t.replace("He has ", "She has ") if f == "F" else t


def negative_for(pz):
    neg = base_neg(pz) + NEG
    if form(pz) == "F":
        assert MALE_NEG in neg
        neg = neg.replace(MALE_NEG, FEMALE_NEG) + ", beard"
    return neg


def skin_match(rgb, look, region, sample=None, near=None):
    return base_skin(rgb, look, region, sample, None if near is None else (near[0], SKIN_AB, SKIN_AB))


def neck_mark(look):
    m = np.zeros((H.db.H, H.db.W), bool)
    if look in NECK_MARKS:
        a = H.db.load_indices(P.FILES["%s__2__%s_NUDE" % (RACE, look)])
        b = H.db.load_indices(P.FILES["%s__2__%s_NUDE" % (RACE, NECK_MARKS[look])])
        m = a != b
        m[:O.NECK_ROW - 1] = False
        m[O.NECK_ROW + 12:] = False
        m = cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    return m


def outline_cut(im):
    """Доля альфы выше шеи без чёрного контура классики. Отступ по цвету, а не на ровное число точек: контур снимается, уши и ширина головы остаются."""
    a = np.asarray(im)
    solid = (a[..., 3] > 128).astype(np.uint8)
    lab = cv2.cvtColor(a[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    d = cv2.distanceTransform(solid, cv2.DIST_L2, 5)
    rows = np.arange(a.shape[0])[:, None]
    grey = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128) < OUTLINE_AB      # контур без цвета: серьги F0 цветные
    depth = np.interp(rows, [e * K for e in EYE_BAND], [OUTLINE, RIM, RIM, SIDE_CUT * 2])   # у глаз глазница сливается с контуром: срез вошёл бы в кожу и уши
    dark = ((lab[..., 0] < OUTLINE_L) & grey & (d <= depth)).astype(np.uint8)
    cut = (d < np.interp(rows, [e * K for e in EYE_BAND], [RIM, RIM, RIM, SIDE_CUT])).astype(np.uint8)     # бледная полоска снаружи контура
    for _ in range(OUTLINE):                        # только тёмное, что идёт от края: глазницы и брови внутри не трогает
        cut = cv2.dilate(cut, np.ones((3, 3), np.uint8)) & (dark | cut)
    cut[CHIN_ROW * K:] = (d[CHIN_ROW * K:] < SIDE_CUT)  # ниже подбородка тёмное - шея, там снимать только край
    cut |= 1 - solid
    keep = (cut == 0).astype(np.float32)
    keep = cv2.erode(keep, np.ones((3, 3), np.uint8))   # бледная кайма между контуром и кожей
    t = np.clip((cv2.GaussianBlur(keep, (0, 0), 2.2) - 0.35) / 0.3, 0, 1)
    t[(O.NECK_ROW - 1) * K:] = 1
    return t


def code_mark(body, look):
    """Метка классики ниже шеи кодом, цветом классики: модель её теряет (лента F2 за четыре сида)."""
    w, h = H.db.W * K, H.db.H * K
    a = H.db.load_indices(P.FILES["%s__2__%s_NUDE" % (RACE, look)])
    b = H.db.load_indices(P.FILES["%s__2__%s_NUDE" % (RACE, NECK_MARKS[look])])
    rgb = H.db.to_rgba(a, P.PAL)[..., :3].astype(np.float32)
    m = (a != b) & (np.arange(H.db.H)[:, None] >= O.NECK_ROW - 1) & (np.arange(H.db.H)[:, None] < O.NECK_ROW + 12)
    m &= rgb[..., 1] > rgb[..., 0] + 25             # у соседа тени другие: метка только там, где цвет не кожи
    t = cv2.resize(m.astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)[..., None]
    t = np.clip((cv2.GaussianBlur(t, (0, 0), 1.2)[..., None] - 0.3) / 0.3, 0, 1)
    c = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_NEAREST)
    keep = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
    col = c[keep].mean(0)                           # один цвет метки, светотень берём от кожи под ней
    s = np.asarray(body, np.float32).copy()
    lit = (s[..., :3].mean(-1, keepdims=True) / max(s[..., :3][keep].mean(), 1)).clip(0.75, 1.2)
    s[..., :3] = s[..., :3] * (1 - t) + col * lit * t
    return Image.fromarray((s + 0.5).clip(0, 255).astype(np.uint8), "RGBA")


def compose(j, rgb):
    body, head, hair, rep = base_compose(j, rgb)
    def cut(im):                                    # у каждого слоя свой край: шея есть только в слое тела
        a = np.asarray(im).copy()
        a[..., 3] = (a[..., 3] * outline_cut(im) + 0.5).astype(np.uint8)
        return Image.fromarray(a, "RGBA")
    body = cut(body)
    if j["look"] in CODE_MARKS:
        body = code_mark(body, j["look"])
    return body, cut(head), hair, rep


def setup(looks_file):
    base_setup(looks_file)
    assert MALE_FACE in P.HEAD
    P.dp.RACE = RACE
    P.FACE_BOX = O.FACE_BOX
    P.head_text, P.negative_for, P.passport, P.skin_match = head_text, negative_for, passport, skin_match


H.RACE = RACE
H.OUT = O.OUT
H.BODIES = os.path.join(H.OUT, "assembled")
H.HEADS = os.path.join(H.OUT, "heads")
H.FACE_BOX = O.FACE_BOX
H.NECK_ROW = O.NECK_ROW
H.NECK_SEAM = 48
H.NECK_MARK = neck_mark
H.RESEED = {"M0": 100, "F1": 200, "F2": 100, "F6": 100, "M2": 200}   # точки на лбу, цепочка, пятно у рта, плоский верх
H.SHEET_CLOSE = (58, 40, 104, 84)
H.SHEET_FULL = (44, 40, 118, 150)
H.compose = compose
H.setup = setup

if __name__ == "__main__":
    H.main()
