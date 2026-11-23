"""128 тел MHUMAN из 32 основ doll_mhuman_bodies.py: тот же сборщик, что у FHUMAN, группы - торсы переписи census_bodies.json.
Основа у внешности только своя: 32 группы и так разведены по торсу, подбор другой основы тут незачем.
Выход art/doll/pipe_pilot/mhuman/: assembled/, assembled.json, asm_N.png. Мод не трогает.

  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_mhuman_assemble.py [внешности через запятую]
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cv2
import numpy as np
from PIL import Image
import doll_race_assemble as A

A.RACE = "MHUMAN"
A.OUT = os.path.join(A.ROOT, "mhuman")
A.ROW = 67              # шея: плечи MHUMAN начинаются на 2 строки выше, чем у FHUMAN (мерка 06.11)
A.HEAD_ROW = 64
A.CROTCH = (90, 105, 65, 96)    # плавки
A.GROUPS = "mhuman_groups.json"
A.S_MIN = 0.5           # основа M43 тёмная и контрастная: на светлом теле её тени выходили чёрными (F59, M53, Vitali 06.11)
PALE = ("F59", "F60", "F62", "M53")     # бледная кожа: основа тоже бледная
PALE_BASE = "F58"
LIFT_MAX = 14
LIFT_PART = 0.6         # подъём на всю разницу выводит блики на бледный верх кривой кожи: оранжевое тело становилось кремовым (M2, M44)
HAND_X = ((205, 250), (390, 435))
HAND_Y = (370, 440)

census = json.load(open(os.path.join(A.ROOT, "census_bodies.json"), encoding="utf-8-sig"))["MHUMAN"]["торсы"]
groups = {t["основа"].replace("_NUDE", ""): [n.replace("_NUDE", "") for n in t["имена"]] for t in census}
A.BASE = {g: g for g in groups}
A.BY_EYE = {n: g for g, m in groups.items() for n in m}
A.BY_EYE.update({n: PALE_BASE for n in PALE})
# своя основа вышла жёлто-оливковой, слова в промпте цвет не держат (Vitali 06.11): перекраска основы M6 с теми же волосами на груди по своей классике
ORANGE = ("M32", "F15", "M55", "F55")   # F55: своя основа с чёрным крестом на груди, на трёх сидах не ушёл
A.BY_EYE.update({n: "M6" for n in ORANGE})
A.BASES = tuple(g for g in groups if g not in ORANGE)

with open(os.path.join(A.ROOT, A.GROUPS), "w", encoding="utf-8-sig") as f:
    json.dump(groups, f, ensure_ascii=False, indent=0)

base_layer = A.base_layer
assemble = A.assemble


def whole_base(n):
    """Группа из одной внешности: перекрашивать не во что, основа как есть. Кожу по порогу считать и незачем: у мехового F49 её нет."""
    if len(groups.get(n, ())) == 1 and n != PALE_BASE:
        return np.asarray(Image.open(os.path.join(A.OUT, "bases", n.lower() + ".png")).convert("RGBA"), np.float32), None, None, None, None
    return base_layer(n)


def body_L(rgb, a, m):
    """Средняя светлота по торсу после размытия: дизеринг классики даёт две светлоты вместо одной."""
    return float(A.soft_lab(rgb, a)[..., 0][m].mean())


def lifted(base, look):
    """Медиана основы уводит тело темнее глаза: подъём по средней светлоте размытой классики и сборки (разница до 18 на F0, M2, M53)."""
    if base == look:
        return assemble(base, look)
    A.LIFT.pop(look, None)
    lay, neck, tint = assemble(base, look)
    idx = A.classic(look)
    m = cv2.erode((idx > 0).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    m[:A.ROW] = False
    m[A.CROTCH[0]:A.CROTCH[1], A.CROTCH[2]:A.CROTCH[3]] = False
    small = np.asarray(lay.resize((A.db.W, A.db.H), Image.BOX), np.float32) / 255.0
    d = body_L(A.PAL[idx] / 255.0, idx > 0, m) - body_L(small[..., :3], small[..., 3] > 0.5, m)
    A.LIFT[look] = float(np.clip(d * LIFT_PART, 0, LIFT_MAX))
    lay, neck, tint = assemble(base, look)
    return (black_hair(lay) if look == "F55" else lay), neck, tint


def black_hair(lay):
    """Волосы на груди основы M6 рыжие, на лиловой коже F55 выходят ржавчиной; в классике они чёрные. Тёплое на холодной коже - только они."""
    im = np.asarray(lay).copy()
    lab = cv2.cvtColor(im[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    w = np.clip((lab[..., 2] - 128) / 5, 0, 1)
    w = cv2.GaussianBlur(w, (0, 0), 1.0)[..., None]
    lab = lab * (1 - w) + np.dstack([lab[..., 0] * 0.6, np.full(w.shape[:2], 128.0), np.full(w.shape[:2], 126.0)]) * w
    im[..., :3] = cv2.cvtColor(np.clip(lab + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    return Image.fromarray(im, "RGBA")


def clean_spots(n):
    """Лиловое пятно у плеча и зелёные штрихи на груди основы: перекраска разносит их на все бледные тела чёрной чертой (F60, F62, M53).
    Меняется только цветность к местной цветности кожи: светлота с мышцами остаётся, фон в размытие не попадает."""
    fn = os.path.join(A.OUT, "bases", n.lower() + ".png")
    im = np.asarray(Image.open(fn).convert("RGBA")).copy()
    lab = cv2.cvtColor(im[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    core = cv2.erode((im[..., 3] > 250).astype(np.float32), np.ones((3, 3), np.uint8))
    near = [cv2.GaussianBlur(lab[..., c] * core, (0, 0), 14) / np.maximum(cv2.GaussianBlur(core, (0, 0), 14), 1e-3) for c in (1, 2)]
    w = np.clip((np.hypot(lab[..., 1] - near[0], lab[..., 2] - near[1]) - 3.0) / 3.0, 0, 1) * core
    w[:A.ROW * A.K] = 0
    w[A.CROTCH[0] * A.K - 12:] = 0
    w = cv2.GaussianBlur(w, (0, 0), 1.5)
    for i, c in enumerate((1, 2)):
        lab[..., c] += (near[i] - lab[..., c]) * w
    im[..., :3] = cv2.cvtColor(np.clip(lab + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    Image.fromarray(im, "RGBA").save(fn)
    print("основа %s: заплатка %d точек" % (n, int((w > 0.5).sum())), flush=True)


def clean_hands(fn):
    """Серый мазок в полости кисти: остаток фона ответа модели (R-089) на кистях основ. Сама дырка в ладони есть и в классике, она остаётся."""
    im = np.asarray(Image.open(fn).convert("RGBA")).copy()
    lab = cv2.cvtColor(im[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    grey = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128) < 9
    m = np.zeros(grey.shape, np.uint8)
    for x0, x1 in HAND_X:
        if np.median(grey[HAND_Y[0]:HAND_Y[0] + 20, x0:x1][im[HAND_Y[0]:HAND_Y[0] + 20, x0:x1, 3] > 250]) == 0:   # серокожую основу не трогать
            m[HAND_Y[0]:HAND_Y[1], x0:x1] = grey[HAND_Y[0]:HAND_Y[1], x0:x1] & (im[HAND_Y[0]:HAND_Y[1], x0:x1, 3] > 0) & (lab[HAND_Y[0]:HAND_Y[1], x0:x1, 0] > 70)
    if m.any():
        im[..., :3] = cv2.inpaint(im[..., :3], cv2.dilate(m, np.ones((3, 3), np.uint8)), 3, cv2.INPAINT_TELEA)
        Image.fromarray(im, "RGBA").save(fn)
    return int(m.sum())


def no_pale_spots(base, look, neck):
    """Тёмная разница классик на прессе бледных тел выходила ровным тёмным сердцем: косметики у них нет, пятна не нужны."""
    maps, cur, q = tint_maps(base, look, neck)
    return ([x * 0 for x in maps] if look in PALE else maps), cur, q


tint_maps = A.tint_maps
A.tint_maps = no_pale_spots
A.base_layer = whole_base
A.assemble = lifted

if __name__ == "__main__":
    clean_spots(PALE_BASE)
    print("кисти:", {os.path.basename(f): n for f in glob.glob(os.path.join(A.OUT, "bases", "*.png")) for n in [clean_hands(f)] if n})
    A.main()
