#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Серия бикини UBERGAL: 240 вещей, 3 силуэта, 106 разных верхов - одна вещь в разных раскрасках (сплошная, двухцветная, полоски).
Модель рисует кадр на каждый разный верх, способ выбран на странице 05.11 (правило 13). Чёрное тела не прикрывается, простое наложение.

Верх с теми же точками и низ BIKINI_BOTTOM (точная вырезка верха) берут уже нарисованный кадр: варианты кадра, карта на них не нужна.
Верх с теми же точками рисуется отдельно, только если волосы кадра закрывают точки, которые у него открыты.

    py -3.13 tools\gpuq.py add --name doll_bikini -- E:\OpenXCom\tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\doll_bikini.py
"""
import argparse
import collections
import colorsys
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_armor_batch as B
import doll_b2_render as db
import numpy as np

OUT = os.path.join(B.OUT, "bikini")
ARMOR = "STR_BIKINI_UC"
CROP, ZOOM = (56, 48, 104, 112), 16                 # вещь мала: кадр грудь-бёдра, стороны входа 768x1024 кратны 32
WHO = "a fit athletic young adult woman, 20 years old"
CUT = ("string bikini: a small triangle top with thin cords and a small matching bottom with thin side ties, "
       "smooth swimsuit fabric with fine stitched hems")
PLAIN = "plain fabric only: no logo, no emblem, no letters, no numbers, no badge, no buckle, no ornament, no printed pattern"
SAMPLES = [("F0", "dark brown and orange striped"), ("F1", "blue with red cups,"), ("F21", "red and white striped"),
           ("F27", "teal"), ("F40", "pale grey"), ("F52", "black"), ("F24", "lime green"), ("F51", "green")]
STRIPES = 0.55                                      # смен цвета по вертикали на точку: выше - полоски, ниже - части разного цвета
CHECKER = 0.4                                      # смен цвета по горизонтали на точку: выше - клетка
SHARE = 0.12                                        # доля точек, ниже которой цвет словом не называется
RAMP_DARK = 0.7                                     # в чёрной линейке палитры на точку чёрного столько серого, остальной серый - светлая линейка


def word(rgb):
    h, s, v = colorsys.rgb_to_hsv(*(float(c) / 255 for c in rgb))
    h *= 360
    if v < 0.2:
        return "black"
    if s < 0.2:
        return "grey"
    if h < 15 or h >= 300:
        return "red"
    if h < 40:
        return "orange" if v > 0.6 else "brown"
    if h < 65:
        return "yellow"
    if h < 95:
        return "lime green"
    if h < 160:
        return "green"
    if h < 200:
        return "teal"
    if h < 255:
        return "blue" if v > 0.5 else "navy blue"
    return "purple"


def colour(i, pal):
    """Индексы вещи -> цвет словами. Оттенки одной линейки палитры считаются одним цветом."""
    rgb = db.to_rgba(i, pal)[..., :3]
    m = i != 0
    w = np.empty(i.shape, dtype=object)
    for y, x in zip(*np.nonzero(m)):
        w[y, x] = word(rgb[y, x])
    n = int(m.sum())
    c = collections.Counter(w[m])
    share = {k: v / n for k, v in c.items()}
    black, grey = share.pop("black", 0), share.pop("grey", 0)
    dark = black + min(grey, RAMP_DARK * black)
    pale = grey - min(grey, RAMP_DARK * black)
    orange, brown = share.pop("orange", 0), share.pop("brown", 0)
    blue, navy = share.pop("blue", 0), share.pop("navy blue", 0)
    fam = dict(share)
    fam.update({"black": dark, "pale grey": pale, "brown" if brown > orange * 1.2 else "orange": orange + brown,
                "navy blue" if navy > blue else "blue": blue + navy})
    if fam.get("lime green", 0) and fam.get("green", 0):    # соседние оттенки одной линейки
        fam["lime green"] += fam.pop("green")
    top = [k for k, v in sorted(fam.items(), key=lambda kv: -kv[1]) if v >= SHARE][:2]
    if len(top) < 2:
        return top[0]
    jump = sum(1 for y, x in zip(*np.nonzero(m[:-1] & m[1:])) if w[y, x] != w[y + 1, x]) / n
    side = sum(1 for y, x in zip(*np.nonzero(m[:, :-1] & m[:, 1:])) if w[y, x] != w[y, x + 1]) / n
    return "%s and %s %s" % (top[0], top[1], "checkered" if side >= CHECKER else "striped" if jump >= STRIPES else "two-tone")


def plan():
    """Первые кадры - проба SAMPLES, их номера не менять: готовые кадры лежат в raw по номеру."""
    import doll_photo_pilot as dp
    d = db.armor_layers()[ARMOR]
    files = db.sprite_files()
    pal = db.game_palette()
    known = dict(SAMPLES)
    looks = sorted(d, key=lambda k: (k not in known, list(known).index(k) if k in known else 0, k[0], int(k[1:])))
    frames, texts, same = [], {}, {}

    def head(look):
        return dp.layer_mask(files, d[look][-1])

    for look in looks:
        item = "UBERGAL__3__BIKINI_" + look
        assert item in d[look], d[look]
        i = db.load_indices(files[item])
        key = i.tobytes()
        low = "UBERGAL__3__BIKINI_BOTTOM_" + look
        bottom = [d[look][0], low, d[look][-1]]              # низ на своём теле, без вещей брони поверх: кадр рисовался без них
        for fr in same.get(key, ()):
            if not (head(fr["key"]) & (i != 0) & ~head(look)).any():
                fr["variants"][item] = d[look]
                fr["variants"][low] = bottom
                break
        else:
            k = len(frames)
            fr = {"id": k, "armor": ARMOR, "key": look, "stack": d[look], "paint": [item], "variants": {low: bottom}, "real": 0}
            frames.append(fr)
            same.setdefault(key, []).append(fr)
            texts[str(k)] = "%s, in a %s %s" % (WHO, known.get(look) or colour(i, pal), CUT)
    return {"frames": frames}, texts


def draw():
    import doll_photo_pilot as dp
    p, texts = plan()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "texts.json"), "w", encoding="utf-8-sig") as f:
        json.dump(texts, f, ensure_ascii=False, indent=0)
    B.OUT = OUT
    dp.CROP, dp.Z = CROP, ZOOM
    B.draw_all(p, texts)


def redo(ids, seeds):
    """Брак первого прохода: те же кадры другими сидами, папка redo/s<сид>. Выбор на странице (правило 13)."""
    import doll_photo_pilot as dp
    p, texts = plan()
    texts = {k: "%s, %s" % (v, PLAIN) for k, v in texts.items()}
    B.OUT = OUT
    dp.CROP, dp.Z = CROP, ZOOM
    keep = {}
    for s in seeds:
        B.draw_all(p, texts, only=set(ids), seed=s, keep=keep)


def items():
    return sorted(x for x in db.sprite_files() if re.fullmatch(r"UBERGAL__3__BIKINI(_BOTTOM)?_[MF]\d+", x))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--redo", help="номера кадров через запятую: перерисовать")
    ap.add_argument("--seeds", default="11,12", help="сиды перерисовки через запятую")
    ns = ap.parse_args()
    if ns.redo:
        redo([int(x) for x in ns.redo.split(",")], [int(x) for x in ns.seeds.split(",")])
    else:
        draw()


if __name__ == "__main__":
    main()
