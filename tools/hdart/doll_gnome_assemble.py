"""48 тел GNOME из основы F9 (doll_gnome_bodies.py): тот же сборщик, что у других рас, кожа внешности - кривой светлота -> цвет (полурампы 185 и 187).
Пятна выключены: пряди волос на теле классики (F12, F13, F17..F21) кладёт кадр головы. Рука у рта - в зоне кадра головы, тело даёт только плечо.
Выход art/doll/pipe_pilot/gnome/: assembled/, assembled.json, asm_N.png. Мод не трогает.

  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_gnome_assemble.py [внешности через запятую]
"""
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

BASE = "F9"
LOOKS = ["F%d" % i for i in range(24)] + ["M%d" % i for i in range(24)]
LIFT_MAX = 14
LIFT_PART = 0.6

A.RACE = "GNOME"
A.OUT = os.path.join(A.ROOT, "gnome")
A.ROW = 76
A.HEAD_ROW = 73
A.TORSO = (78, 100)
A.CROTCH = (92, 105, 70, 92)    # стринги
A.GROUPS = "gnome_groups.json"
A.SPOT_MIN = 10 ** 6
A.SHEET_BOX = (44, 50, 118, 148)
A.BASE = {BASE: BASE}
A.BASES = (BASE,)
A.BY_EYE = {}

with open(os.path.join(A.ROOT, A.GROUPS), "w", encoding="utf-8-sig") as f:
    json.dump({BASE: LOOKS}, f, ensure_ascii=False, indent=0)

assemble = A.assemble


def body_L(rgb, a, m):
    return float(A.soft_lab(rgb, a)[..., 0][m].mean())


def lifted(base, look):
    """Как у OGRE: медиана основы уводит тело темнее глаза, подъём по средней светлоте размытой классики и сборки."""
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
    return assemble(base, look)


def clean_spots(n):
    """Цветные черты на коже основы: перекраска разносит их на все тела. Как у OGRE: меняется только цветность к местной цветности кожи."""
    fn = os.path.join(A.OUT, "bases", n.lower() + ".png")
    im = np.asarray(Image.open(fn).convert("RGBA")).copy()
    lab = cv2.cvtColor(im[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    core = cv2.erode((im[..., 3] > 250).astype(np.float32), np.ones((3, 3), np.uint8))
    near = [cv2.GaussianBlur(lab[..., c] * core, (0, 0), 14) / np.maximum(cv2.GaussianBlur(core, (0, 0), 14), 1e-3) for c in (1, 2)]
    w = np.clip((np.hypot(lab[..., 1] - near[0], lab[..., 2] - near[1]) - 3.0) / 3.0, 0, 1) * core
    w[:A.ROW * A.K] = 0
    w[A.CROTCH[0] * A.K - 12:A.CROTCH[1] * A.K + 8] = 0     # стринги чёрные, чистить только кожу
    w[96 * A.K:107 * A.K, :70 * A.K] = 0                    # красные ногти висящей кисти - классика, не черта
    w = cv2.GaussianBlur(w, (0, 0), 1.5)
    for i, c in enumerate((1, 2)):
        lab[..., c] += (near[i] - lab[..., c]) * w
    im[..., :3] = cv2.cvtColor(np.clip(lab + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    Image.fromarray(im, "RGBA").save(fn)
    print("основа %s: заплатка %d точек" % (n, int((w > 0.5).sum())), flush=True)


A.assemble = lifted

if __name__ == "__main__":
    clean_spots(BASE)
    A.main()
