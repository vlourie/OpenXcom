#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000410, путь FLD: поле клеток одной картинкой вместо отдельных ромбов.

Эскиз - поле n x n клеток классики (кадры 0/1/2 как на карте), модель (Qwen-Image-2.1 strict, путь t405_409_gen) рисует ОДНО
поле; кадры режутся из внутренних клеток. Края ромба у внутренней клетки - середина травы, а не край картинки: каймы по
ромбу нет. Поля:
  g - все клетки кадр 0 (трава), s - все клетки кадр 2 (земля со стеблями), m - вперемешку 0/1/2 (внешнее кольцо 0).

    py -3 tools\gpuq.py add --name t410-fld -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t410_fld.py render --fields g s
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402

import t410_gen as g                                 # noqa: E402

N, PAD, S = 6, 4, 5.5
SEEDS = {"g": [4401, 4402], "s": [4411, 4412], "m": [4321, 4322], "p": [4431, 4432]}
LAYOUT_SEED = 7
PANEL = (110, 110, 116)
WHAT = {
    "g": ("a continuous meadow of dense lush upright green grass blades of many shades from deep green to bright light "
          "green, with a few red-brown specks and a few thin grey-pink dry stalks, all exactly where the sketch shows "
          "them; the grass blades rise upward on the screen"),
    "s": ("a continuous field of bare brown earth with sparse thin upright green grass stalks and a few dry stems "
          "standing up from it, all exactly where the sketch shows them"),
    "p": ("a continuous meadow of lush upright green grass blades of many shades from deep green to bright light "
          "green with a few red-brown specks and a few thin grey-pink dry stalks, and between the grass tufts bare "
          "brown earth with sparse thin green stalks, all exactly where the sketch shows them; the grass blades "
          "rise upward on the screen"),
    "m": ("a continuous meadow of a tropical plain: lush upright green grass blades of many shades from deep green to "
          "bright light green with a few red-brown specks and a few thin grey-pink dry stalks, and patches of bare "
          "brown earth with sparse thin green stalks standing up, all exactly where the sketch shows them; the grass "
          "blades rise upward on the screen"),
}
TAIL = ("Output one single continuous field of ground on the same flat panel: the same ground runs across the cells "
        "without any border, grid line, diamond outline, tile edge or dark rim between the cells; the field ends in a "
        "ragged uneven outline against the panel. No other objects, no frame, no text.")
NEG = ("grid lines, tile borders, diamond outlines, cell edges, separated tiles, dark lines between cells, dark rim, "
       "vignette, flowers, mushrooms, rocks, stones, bush, flat mowed lawn, straight cut edge, "
       "separate squares, checkerboard")


def layout(kind, n=N, seed=LAYOUT_SEED):
    """{(i, j): кадр классики}."""
    if kind == "g":
        return {(i, j): 0 for i in range(n) for j in range(n)}
    if kind == "s":
        return {(i, j): 2 for i in range(n) for j in range(n)}
    if kind == "p":
        return {(i, j): 1 for i in range(n) for j in range(n)}
    rng = np.random.RandomState(seed)
    inner = [(i, j) for i in range(1, n - 1) for j in range(1, n - 1)]
    rng.shuffle(inner)
    lay = {(i, j): 0 for i in range(n) for j in range(n)}
    for c in inner[:4]:
        lay[c] = 1
    for c in inner[4:8]:
        lay[c] = 2
    return lay


def xy(i, j):
    """Левый верхний угол кадра клетки (i, j) в базовых пикселях поля."""
    return PAD + 16 * (N - 1) + 16 * (i - j), PAD + 8 * (i + j)


def canvas():
    return 32 * N + 2 * PAD, 16 * N + 24 + 2 * PAD


def mirror_cells(kind, n=N):
    """Клетки эскиза, нарисованные зеркалом (R-118: пятна классики с периодом клетки дают решётку). Поля g/s/p: примерно
    половина клеток; в поле s вместо зеркала кадр 3 классики. Поле m - как есть (его раскладка и так неровная)."""
    if kind == "m":
        return set()
    rng = np.random.RandomState(5)
    return {(i, j) for i in range(n) for j in range(n) if rng.rand() < 0.5}


def window_cells(kind, count=4):
    """Клетки окон кадров: внутренние, не зеркальные, ближе к середине поля."""
    mir = mirror_cells(kind)
    cells = [(i, j) for i in range(1, N - 1) for j in range(1, N - 1) if (i, j) not in mir]
    cells.sort(key=lambda c: abs(c[0] - (N - 1) / 2) + abs(c[1] - (N - 1) / 2))
    return cells[:count]


def sketch(lay, kind="m"):
    from PIL import ImageOps
    w, h = canvas()
    cv = Image.new("RGBA", (w, h), PANEL + (255,))
    mir = mirror_cells(kind)
    cls = {f: g.classic("MOUNTTROP", f) for f in set(lay.values())}
    cls[3] = g.classic("MOUNTTROP", 3)
    for (i, j) in sorted(lay, key=lambda c: (c[0] + c[1], c[0])):
        f = lay[(i, j)]
        im = cls[f]
        if (i, j) in mir:
            im = cls[3] if f == 2 else ImageOps.mirror(im)
        cv.alpha_composite(im, xy(i, j))
    return cv


def raw_path(kind, seed):
    return os.path.join(g.GEN, "fld_" + kind, "raw", "%d.png" % seed)


def field_x4(kind, seed):
    """Ответ модели -> поле на сетке x4 (RGB), размер canvas()*4."""
    w, h = canvas()
    return Image.open(raw_path(kind, seed)).convert("RGB").resize((w * 4, h * 4), Image.LANCZOS)


def window(fld, i, j):
    """Окно кадра клетки (i, j) в поле x4: RGB 128x160."""
    x, y = xy(i, j)
    return fld.crop((x * 4, y * 4, x * 4 + 128, y * 4 + 160))


def prompt(kind):
    import battle_view as bv
    import probe_object as po
    import ticket_q21_probe as q
    pb = bv.prompt_block("floor")
    what = WHAT[kind]
    text = (q.PANEL_HINT.replace("{what}", what) + bv.view_sentence("floor") + " "
            + q.KEEP.replace("{noun}", "field of ground").replace("{what}", what) + bv.light_sentence("floor") + " " + TAIL)
    neg = po.NEGATIVE.replace("ground, grass tile, floor, ", "") + ", " + pb["negative"] + ", " + NEG
    return text, neg


def do_render(kinds, seeds_over):
    import argparse as ap2
    import probe_object as po
    ns = ap2.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=g.STEPS, qwen21_cfg=g.CFG,
                       qwen21_mp=g.MP, qwen21_strength=0.0, qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="",
                       qwen21_ref_mp=1.0, qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    args = ap2.Namespace(steps=g.STEPS, cfg=g.CFG, mp=g.MP)
    t0 = time.time()
    for kind in kinds:
        sd = os.path.join(g.GEN, "fld_" + kind)
        os.makedirs(os.path.join(sd, "raw"), exist_ok=True)
        text, neg = prompt(kind)
        print("[fld %s]\n  PROMPT: %s\n  NEG: %s" % (kind, text, neg), flush=True)
        po.gen_fire.NEGATIVE = neg
        sk = sketch(layout(kind), kind)
        sk = sk.resize((int(sk.width * S), int(sk.height * S)), Image.BICUBIC)
        sk.convert("RGB").save(os.path.join(sd, "sketch.png"))
        for seed in (seeds_over or SEEDS[kind]):
            raw = raw_path(kind, seed)
            if os.path.exists(raw):
                print("[fld %s] зерно %d уже есть" % (kind, seed), flush=True)
                continue
            hd = po.gen_fire.run_pass(painter, args, text, sk.convert("RGB"), seed)
            po.gen_hd.save_png(hd, raw)
            print("[fld %s] зерно %d готово, %.0f с" % (kind, seed, time.time() - t0), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "prompt", "sketch"])
    ap.add_argument("--fields", nargs="*", default=["g", "s", "m", "p"], choices=["g", "s", "m", "p"])
    ap.add_argument("--seeds", nargs="*", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "prompt":
        for k in a.fields:
            t, n = prompt(k)
            print("[%s] PROMPT:" % k, t, "\nNEG:", n)
    elif a.cmd == "sketch":
        for k in a.fields:
            os.makedirs(os.path.join(g.GEN, "fld_" + k), exist_ok=True)
            sk = sketch(layout(k), k)
            sk.resize((int(sk.width * S), int(sk.height * S)), Image.BICUBIC).convert("RGB").save(
                os.path.join(g.GEN, "fld_" + k, "sketch.png"))
        print(canvas())
    else:
        do_render(a.fields, a.seeds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
