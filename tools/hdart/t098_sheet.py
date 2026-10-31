# -*- coding: utf-8 -*-
r"""Тикет XP-000098: листы выбора фона инвентаря. Без модели и без игры: кадры инвентаря уже сняты стендом
(art/_review/tickets_2026-10-31/_inv_cur.png - боец без вещей, с новыми кнопками; art/_review/tickets_2110/t098_inv.png -
боец с вещами; предметы по прямоугольникам слотов берутся из второго).

    py -3.13 tools\hdart\t098_sheet.py           # gen -> cand 1280x800, t098_seeds.png и t098_cand.png в art/_review/tickets_2026-10-31/

Наложение: кандидат кладётся под всё, что на кадре не чёрное (сетки, подписи, значки предметов, кукла, кнопки):
альфа фона = 1 - smoothstep(max(R,G,B) кадра, 0..LOW). Кадр инвентаря 1920x1080 (k = 4 при 480x270 базы), экран
1280x800 со смещением (320, 140).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-31")
CAND = os.path.join(ROOT, "art", "tickets", "t098", "cand")
NEW = os.path.join(REV, "_inv_cur.png")
OLD = os.path.join(ROOT, "art", "_review", "tickets_2110", "t098_inv.png")
BOX = (320, 140, 1600, 940)
# слоты с вещами на кадре с вещами (в координатах кадра 1920x1080): П.Плечо, П.Рука, Бедро, Пояс, Л.Нога
ITEM_RECTS = [(440, 280, 520, 360), (315, 390, 452, 590), (960, 410, 1035, 548), (980, 560, 1250, 700),
              (828, 615, 970, 692)]
LOW = 64.0
FONT = "C:/Windows/Fonts/arial.ttf"
THEMES = [("armory", "оружейная"), ("ship", "оружейная на корабле"), ("tarp", "походный брезент"),
          ("tarpc", "брезент крупно")]


def frame():
    new = np.array(Image.open(NEW).convert("RGB"))
    old = np.array(Image.open(OLD).convert("RGB"))
    for x0, y0, x1, y1 in ITEM_RECTS:
        new[y0:y1, x0:x1] = old[y0:y1, x0:x1]
    return new[BOX[1]:BOX[3], BOX[0]:BOX[2]]


def overlay(fr, cand):
    f = fr.astype(np.float32)
    m = f.max(axis=2) / LOW
    m = np.clip(m, 0, 1)
    alpha = 1.0 - m * m * (3 - 2 * m)
    out = f + cand.astype(np.float32) * alpha[..., None]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def seeds_of(name):
    return sorted(f for f in os.listdir(CAND) if f.startswith(name + "_") and f.endswith(".png"))


def label(im, text, size=18):
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, size)
    w = d.textlength(text, font=f)
    d.rectangle((0, 0, w + 14, size + 8), fill=(0, 0, 0))
    d.text((7, 3), text, font=f, fill=(255, 200, 112))


def sheets():
    fr = frame()
    cols = len(THEMES)
    files = {t: seeds_of(t) for t, _ in THEMES}
    rows = max(len(v) for v in files.values())
    tw, th = 640, 400
    # лист зёрен: без наложения
    sw, sh = 480, 300
    sb = Image.new("RGB", (cols * (sw + 4) + 4, rows * (sh + 4) + 4), (16, 10, 6))
    for ci, (t, ru) in enumerate(THEMES):
        for ri, f in enumerate(files[t]):
            im = Image.open(os.path.join(CAND, f)).convert("RGB").resize((sw, sh), Image.LANCZOS)
            label(im, "%s  %s" % (ru, f.rsplit("_", 1)[1].split(".")[0]), 16)
            sb.paste(im, (4 + ci * (sw + 4), 4 + ri * (sh + 4)))
    sb.save(os.path.join(REV, "t098_seeds.png"))
    # лист выбора: слева сверху - чёрный как сейчас, затем по теме в столбце
    board = Image.new("RGB", (cols * (tw + 4) + 4, (rows + 1) * (th + 4) + 4), (16, 10, 6))
    base = Image.fromarray(fr).resize((tw, th), Image.LANCZOS)
    label(base, "чёрный (как сейчас)")
    board.paste(base, (4, 4))
    for ci, (t, ru) in enumerate(THEMES):
        for ri, f in enumerate(files[t]):
            cand = np.array(Image.open(os.path.join(CAND, f)).convert("RGB"))
            im = overlay(fr, cand).resize((tw, th), Image.LANCZOS)
            label(im, "%s  %s" % (ru, f.rsplit("_", 1)[1].split(".")[0]))
            board.paste(im, (4 + ci * (tw + 4), 4 + (ri + 1) * (th + 4)))
    board.save(os.path.join(REV, "t098_cand.png"))
    print("листы:", os.path.join(REV, "t098_seeds.png"), os.path.join(REV, "t098_cand.png"))


def make_cand():
    """Сырые кадры art/tickets/t098/gen (1792x1120) -> кандидаты 1280x800 (LANCZOS), без модели."""
    gen = os.path.join(ROOT, "art", "tickets", "t098", "gen")
    os.makedirs(CAND, exist_ok=True)
    for f in sorted(os.listdir(gen)):
        if f.endswith(".png"):
            Image.open(os.path.join(gen, f)).convert("RGB").resize((1280, 800), Image.LANCZOS).save(os.path.join(CAND, f))


def full(name):
    """Один кандидат в полный размер 1280x800 с наложением: t098_full_<name>.png."""
    fr = frame()
    cand = np.array(Image.open(os.path.join(CAND, name + ".png")).convert("RGB"))
    overlay(fr, cand).save(os.path.join(REV, "t098_full_%s.png" % name))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "full":
        for n in sys.argv[2:]:
            full(n)
    else:
        make_cand()
        sheets()
