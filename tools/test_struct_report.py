#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""struct_report: мерка лесенки (nearest x4 - 1.0, спрямлённый - 0.0) и ворота STRUCT_GUIDE_V1
(починено, новые классы против A того же предмета). Без модели.

    py -3.13 tools/test_struct_report.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import struct_guide as sg               # noqa: E402
import struct_report as sr              # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


n = 20
fr = np.zeros((n, n, 4), np.uint8)
fr[np.fromfunction(lambda y, x: (y >= x) & (y < n - 1) & (x > 0), (n, n)).astype(bool)] = (120, 90, 60, 255)
sprite = Image.fromarray(fr, "RGBA")
near, smooth, zone = sr.stair_zone(sprite)
check("зона лесенки есть (%d)" % zone.sum(), zone.sum() > 0)


def piece(mask):
    a = np.zeros(mask.shape + (4,), np.uint8)
    a[mask] = (120, 90, 60, 255)
    return Image.fromarray(a, "RGBA")


check("край по пикселям - 1.0", sr.stair_follow(sprite, piece(near))[0] == 1.0)
check("край ровный - 0.0", sr.stair_follow(sprite, piece(smooth))[0] == 0.0)

P = "PIXEL_STEP_TRACING"
groups = {"p1": "primary", "p2": "primary", "p3": "primary", "s1": "secondary"}
ver = {"p1": {"A": ("FAIL", {P}), "B": ("PASS", set()), "C": ("PARTIAL", {"DETAIL_LOSS"})},
       "p2": {"A": ("FAIL", {P}), "B": ("FAIL", {P}), "C": ("FAIL", {"MAJOR_GEOMETRY"})},
       "p3": {"A": ("FAIL", {P, "MAJOR_GEOMETRY"}), "B": ("PARTIAL", {"MAJOR_GEOMETRY"}),
              "C": ("PASS", set())},
       "s1": {"A": ("FAIL", {"WRONG_IDENTITY", P}), "B": ("FAIL", {"WRONG_IDENTITY"}),
              "C": ("PASS", {"WRONG_IDENTITY"})}}
g = sr.gate(ver, groups)
check("B: починено p1 и p3, лесенка осталась у p2", g["B"]["fixed"] == ["p1", "p3"] and g["B"]["still_pixel"] == ["p2"])
check("B: геометрия у p3 была и у A - не новая", g["B"]["new_major_geometry"] == [])
check("C: новая геометрия у p2", g["C"]["new_major_geometry"] == ["p2"])
check("опознание вторичного не новое, если у A оно уже было", g["C"]["new_wrong_identity"] == [])
check("FAIL без лесенки не считается починенным", "p2" not in g["C"]["fixed"])
check("ворота при 2 из 3 - FAIL (нужно 5)", g["B"]["gate"] == "FAIL")
sr.GATE["primary_fixed_min"] = 2
check("при пороге 2: B PASS, C FAIL из-за новой геометрии",
      sr.gate(ver, groups)["B"]["gate"] == "PASS" and sr.gate(ver, groups)["C"]["gate"] == "FAIL")

print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
