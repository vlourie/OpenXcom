"""96 тел NEKOMIMI (48 внешностей в двух позах) из 20 основ doll_neko_bodies.py: тот же сборщик, что у других рас.
Внешность "F0" - поза NUDE, "AF0" - поза NUDE_ALT. Особый окрас - своя основа, остальные перекрашены по своей классике с основы своего размера.
Выход art/doll/pipe_pilot/nekomimi/: assembled/, assembled.json, asm_N.png. Мод не трогает.

  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_neko_assemble.py [внешности через запятую]
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
import doll_neko_classic as NC
import doll_race_assemble as A

SPECIAL = {"M10": ("F6", "F18", "M10"), "M5": ("M5",), "M14": ("M14",), "F3": ("F3",), "F7": ("F7", "M11"), "F23": ("F23",), "M23": ("M23",)}
PLAIN = {"MAXI": "F0", "MIDI": "F1", "MINI": "F12"}
LIFT_MAX = 14
LIFT_PART = 0.6
GLOSS_OVER, GLOSS_KEEP, GLOSS_SOFT = 6, 0.25, 12    # блики светлой основы на смуглом теле белые: выше своей классики - прижать и тонировать

A.RACE = NC.RACE
A.OUT = NC.OUT
A.ROW = NC.NECK_ROW
A.HEAD_ROW, A.HEAD_X = NC.HEAD_ROW, NC.HEAD_X
A.CROTCH = (88, 100, 66, 92)
A.GROUPS = "nekomimi_groups.json"
A.S_MIN = 0.5
A.SHEET_BOX = (56, 40, 106, 146)
NC.bind(A.F)
NC.patch_b2(A.dp, A.F)

own = {k for v in SPECIAL.values() for k in v}
groups = {}
for s, g in PLAIN.items():
    m = [k for k in NC.KEYS if k not in own and NC.size_of(k) == s]
    groups[g] = m
    groups["A" + g] = ["A" + k for k in m]
for g, m in SPECIAL.items():
    groups[g] = list(m)
    groups["A" + g] = ["A" + k for k in m]
A.BASE = {g: g for g in groups}
A.BY_EYE = {n: g for g, m in groups.items() for n in m}
A.BASES = tuple(groups)
with open(os.path.join(A.ROOT, A.GROUPS), "w", encoding="utf-8-sig") as f:
    json.dump(groups, f, ensure_ascii=False, indent=0)

base_layer = A.base_layer
assemble = A.assemble


def whole_base(n):
    """Группа из одной внешности: перекрашивать не во что, основа как есть."""
    if len(groups.get(n, ())) == 1:
        return np.asarray(Image.open(os.path.join(A.OUT, "bases", n.lower() + ".png")).convert("RGBA"), np.float32), None, None, None, None
    return base_layer(n)


def body_L(rgb, a, m):
    return float(A.soft_lab(rgb, a)[..., 0][m].mean())


def gloss_down(lay, idx, m):
    """Точки светлее размытой классики внешности: светлота прижата, цвет ведётся к цвету кожи."""
    Lc = cv2.GaussianBlur(cv2.cvtColor((A.PAL[idx][..., :3] / 255.0).astype(np.float32), cv2.COLOR_RGB2Lab)[..., 0], (0, 0), 1)
    cap = np.percentile(Lc[m], 99) + GLOSS_OVER
    a = np.asarray(lay, np.float32).copy()
    lab = cv2.cvtColor(a[..., :3] / 255.0, cv2.COLOR_RGB2Lab)
    body = a[..., 3] > 128
    t = np.clip((lab[..., 0] - cap) / GLOSS_SOFT, 0, 1) * body
    for c in (1, 2):
        lab[..., c] += (np.median(lab[..., c][body]) - lab[..., c]) * t
    lab[..., 0] = np.where(body & (lab[..., 0] > cap), cap + (lab[..., 0] - cap) * GLOSS_KEEP, lab[..., 0])
    a[..., :3] = np.clip(cv2.cvtColor(lab, cv2.COLOR_Lab2RGB) * 255.0 + 0.5, 0, 255)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def lifted(base, look):
    """Как у MHUMAN: медиана основы уводит тело темнее глаза, подъём по средней светлоте размытой классики и сборки."""
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
    return gloss_down(lay, idx, m), neck, tint


A.base_layer = whole_base
A.assemble = lifted

if __name__ == "__main__":
    A.main()
