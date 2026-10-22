#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Вылет корабля, механизм 3: один кадр из двух. Vitali 22.10 про ховертанк: «сид 1400 чистка 22 самый норм по
выезду из базы, а сид 8200 чистка 22 сам танк крутой». Гараж с воротами и пандусом - из первого кадра, танк - из
второго: Edit-2511 + Lightning перерисовывает только маску на месте танка (unit_parts.Inpainter), образец
<image2> - танк, вырезанный из второго кадра. Проект: docs/research/craft-launch-2026-10-22.md.

Только через очередь:
    py -3.13 tools/gpuq.py add --name craft-launch-swap --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/craft_launch_swap.py
Выход art/craft_launch/frames/STR_MBT_swap_s<старт>_r<сид>.png и лист art/craft_launch/frames_sheet_swap.png."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFont     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

F = os.path.join(ROOT, "art", "craft_launch", "frames")
SCENE = "STR_MBT_1400_patch22"          # гараж, ворота, пандус
TANK = "STR_MBT_8200_patch22"           # сам танк
TANK_BOX = (280, 290, 910, 560)         # танк во втором кадре (по сетке 22.10)
MASK_BOX = (260, 270, 910, 560)         # место танка в первом кадре, с запасом под подушку и свечение
TOKEN = 16
SEEDS = (31, 42, 53)
STARTS = (1.0, 0.9)

PROMPT = (
    "Edit <image1>. Inside the marked area paint the hover tank exactly as it is in <image2>: the same angular pale "
    "sand-coloured hull, the same flat hover skirts along the sides, the same turret covered with rows of tiled "
    "armour plates and the light chevron emblem, the same long gun, the same rusty dark hover cushion and the blue "
    "glow of the air cushion underneath. The tank floats half a metre above the round brass turntable of <image1>, "
    "in the same place, size and direction as the tank in <image1>, the gun pointing to the left. All hatches are "
    "closed, nobody on the tank. Keep the garage, the gate, the tunnel ramp, the lamps and the light of <image1> "
    "untouched, the same realistic painted style. No tracks, no wheels, no people.")


def mask_tokens(size, box):
    w, h = size
    tok = np.zeros((h // TOKEN, w // TOKEN), np.float32)
    x0, y0, x1, y1 = box
    tok[y0 // TOKEN:(y1 + TOKEN - 1) // TOKEN, x0 // TOKEN:(x1 + TOKEN - 1) // TOKEN] = 1
    return tok


def sheet(paths):
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    W, H = 640, 400
    cols = 3
    rows = (len(paths) + cols - 1) // cols
    im = Image.new("RGB", (cols * (W + 8), rows * (H + 30)), (24, 24, 24))
    d = ImageDraw.Draw(im)
    for i, (label, p) in enumerate(paths):
        x, y = (i % cols) * (W + 8), (i // cols) * (H + 30)
        if os.path.exists(p):
            im.paste(Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS), (x, y + 26))
        d.text((x + 4, y + 4), label, fill=(230, 210, 150), font=font)
    out = os.path.join(ROOT, "art", "craft_launch", "frames_sheet_swap.png")
    im.save(out)
    print("лист:", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--sheet-only", action="store_true", dest="sheet_only")
    a = ap.parse_args()
    os.chdir(ROOT)
    ctx = Image.open(os.path.join(F, SCENE + ".png")).convert("RGB")
    ref = Image.open(os.path.join(F, TANK + ".png")).convert("RGB").crop(TANK_BOX)
    ref = ref.resize((ref.width * 2, ref.height * 2), Image.LANCZOS)
    tok = mask_tokens(ctx.size, MASK_BOX)
    outs = [("гараж 1400", os.path.join(F, SCENE + ".png")), ("танк 8200", os.path.join(F, TANK + ".png"))]
    if not a.sheet_only:
        import gen_hd
        import unit_parts as uparts
        models = a.models or gen_hd.DEFAULT_MODELS_DIR
        uparts.STEPS = 8
        paint = uparts.Inpainter(models, [(ctx, ref, PROMPT)])
        for seed in SEEDS:
            for st in STARTS:
                t0 = time.time()
                raw, _log = paint.run(0, ctx, tok, seed, st)
                p = os.path.join(F, "STR_MBT_swap_s%02d_r%d.png" % (round(st * 100), seed))
                raw.save(p)
                print("  сид %d старт %.2f: %.0f с" % (seed, st, time.time() - t0), flush=True)
    for seed in SEEDS:
        for st in STARTS:
            outs.append(("сид %d, старт %.2f" % (seed, st),
                         os.path.join(F, "STR_MBT_swap_s%02d_r%d.png" % (round(st * 100), seed))))
    sheet(outs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
