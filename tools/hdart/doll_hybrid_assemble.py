"""16 тел HYBRID из двух основ (doll_hybrid_bodies.py): F0 - женская форма, M1 - мужская. Кожа у всех одна, тот же сборщик, что у других рас; пятна выключены: метки ниже шеи (бусы F2, F3) ставит кадр головы.
Выход art/doll/pipe_pilot/hybrid/: assembled/, assembled.json, asm_N.png. Мод не трогает.

  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_hybrid_assemble.py [внешности через запятую]
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

GROUPS = {"F0": ["F%d" % i for i in range(8)], "M1": ["M%d" % i for i in range(8)]}

A.RACE = "HYBRID"
A.OUT = os.path.join(A.ROOT, "hybrid")
A.ROW = 67
A.HEAD_ROW = 64
A.TORSO = (68, 100)
A.CROTCH = (89, 106, 62, 98)    # стринги и плавки
A.GROUPS = "hybrid_groups.json"
A.SPOT_MIN = 10 ** 6
A.SHEET_BOX = (44, 44, 118, 150)
A.BASE = {"F0": "F0", "M1": "M1"}
A.BASES = ("F0", "M1")
A.BY_EYE = {}
A.choose_base = lambda group_base, look: group_base     # формы разные, на чужую основу не переносить

with open(os.path.join(A.ROOT, A.GROUPS), "w", encoding="utf-8-sig") as f:
    json.dump(GROUPS, f, ensure_ascii=False, indent=0)


def clean_spots(n):
    """Голубая черта на груди основы: перекраска разносит её на все тела. Как у MHUMAN: меняется только цветность к местной цветности кожи."""
    fn = os.path.join(A.OUT, "bases", n.lower() + ".png")
    im = np.asarray(Image.open(fn).convert("RGBA")).copy()
    lab = cv2.cvtColor(im[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    core = cv2.erode((im[..., 3] > 250).astype(np.float32), np.ones((3, 3), np.uint8))
    near = [cv2.GaussianBlur(lab[..., c] * core, (0, 0), 14) / np.maximum(cv2.GaussianBlur(core, (0, 0), 14), 1e-3) for c in (1, 2)]
    w = np.clip((np.hypot(lab[..., 1] - near[0], lab[..., 2] - near[1]) - 3.0) / 3.0, 0, 1) * core
    w[:A.ROW * A.K] = 0
    w[A.CROTCH[0] * A.K - 12:A.CROTCH[1] * A.K + 8] = 0     # плавки чёрные, чистить только кожу
    w = cv2.GaussianBlur(w, (0, 0), 1.5)
    for i, c in enumerate((1, 2)):
        lab[..., c] += (near[i] - lab[..., c]) * w
    im[..., :3] = cv2.cvtColor(np.clip(lab + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    Image.fromarray(im, "RGBA").save(fn)
    print("основа %s: заплатка %d точек" % (n, int((w > 0.5).sum())), flush=True)


if __name__ == "__main__":
    for b in A.BASES:
        clean_spots(b)
    A.main()
