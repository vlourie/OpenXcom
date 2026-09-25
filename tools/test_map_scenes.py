# -*- coding: utf-8 -*-
"""Тема карты в map_paint делится на «поверхности | предметы» (R-016).

Поле полов и стен и участок solo получают только левую часть. Тема без черты или с чертой,
которую разбор не узнал, отдаёт полю весь список предметов - и модель рисует их на каждой
клетке: веточка на всём песке DESERT05, папоротники вместо деревьев JUNGLE04 (2026-09-25).
Без видеокарты:  py -3 tools/test_map_scenes.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import map_paint as mp  # noqa: E402

bad = []
for name, scene in mp.SCENES.items():
    if "|" not in scene:
        bad.append("%s: нет черты - поле получит все предметы темы" % name)
        continue
    full, surf = mp.scene_prompts(scene)
    things = scene.partition("|")[2].strip()
    if not things or things in surf:
        bad.append("%s: предметы попали в промпт поля" % name)
    if " ," in surf or "  " in surf:
        bad.append("%s: разбор оставил лишний пробел: %s" % (name, surf))
# разбор не зависит от пробелов вокруг черты
for s in ("a | b", "a |b", "a| b", "a|b"):
    full, surf = mp.scene_prompts(s)
    if "b" in surf.replace("isometric view of a", "").split(",")[0]:
        bad.append("черта без пробела не делит тему: %r" % s)

for b in bad:
    print("ОШИБКА", b)
print("итог:", "всё верно" if not bad else "ошибок %d" % len(bad))
sys.exit(1 if bad else 0)
