#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000349 вариант B (без звезды): сверка вывода gen_combat_fx.py --ground-v2 --no-star с модом и лист «сейчас/после».
Ничего не пишет в мод. py -3.13 tools\hdart\t349_compare_sheet.py"""
import hashlib
import os
import sys
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(ROOT, "art", "_review", "tickets_2026-10-28")
NEW = os.path.join(D, "t349_install", "hd", "FX")
BEF = os.path.join(D, "t349_install", "_before", "FX")
MOD = os.path.join(ROOT, "user", "mods", "hd", "hd", "FX")


def h(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


clips = sorted(c for c in os.listdir(NEW) if os.path.isdir(os.path.join(NEW, c)))
same_before_mod = diff_before_mod = changed = same = frames_changed = 0
changed_clips = []
for c in clips:
    fr = sorted(f for f in os.listdir(os.path.join(NEW, c)) if f.endswith(".png"))
    ch = 0
    for f in fr:
        m = os.path.join(MOD, c, f)
        if not os.path.exists(m):
            print("нет в моде", c, f); continue
        if h(m) == h(os.path.join(BEF, c, f)):
            same_before_mod += 1
        else:
            diff_before_mod += 1
        if h(m) != h(os.path.join(NEW, c, f)):
            ch += 1
    frames_changed += ch
    if ch:
        changed_clips.append((c, ch, len(fr)))
print("клипов", len(clips), "изменяются", len(changed_clips), "кадров изменится", frames_changed)
print("генератор без --no-star совпадает с модом: кадров", same_before_mod, "расхождений", diff_before_mod)
for c, ch, n in changed_clips:
    print("  ", c, ch, "/", n)
# лишнее: клипы мода вне 42, не затрагиваются по построению (пишется только hd/FX/<42 клипа>)

pick = ["hit_cal1_grass", "hit_cal3_dirt", "hit_cal5_stone", "hit_cal4_snow", "hit_pellet_sand", "hit_cal2_wood"]
frames = [0, 1]
tiles = []
for c in pick:
    row = []
    for src in (MOD, NEW):
        for f in frames:
            row.append(Image.open(os.path.join(src, c, "%d.png" % f)).convert("RGBA"))
    tiles.append((c, row))
w = max(i.width for _, r in tiles for i in r)
hh = max(i.height for _, r in tiles for i in r)
S = 1
cw, ch_ = w * S, hh * S
LAB = 150
sheet = Image.new("RGBA", (LAB + 4 * cw, 24 + len(pick) * ch_), (60, 70, 60, 255))
dr = ImageDraw.Draw(sheet)
for j, t in enumerate(["now f0", "now f1", "after f0", "after f1"]):
    dr.text((LAB + j * cw + 4, 6), t, fill=(255, 255, 255, 255))
for i, (c, row) in enumerate(tiles):
    dr.text((4, 24 + i * ch_ + 4), c, fill=(255, 255, 255, 255))
    for j, im in enumerate(row):
        sheet.alpha_composite(im, (LAB + j * cw + (cw - im.width) // 2, 24 + i * ch_ + (ch_ - im.height) // 2))
out = os.path.join(D, "t349_B_sheet.png")
sheet.convert("RGB").save(out)
print(out, sheet.size, "клип", w, "x", hh)
