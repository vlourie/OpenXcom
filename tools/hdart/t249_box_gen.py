#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000249: сломанный деревянный ящик URBAN_WASTE 91 - запасной путь, генерация Qwen-2.1 strict. НЕ ЗАПУЩЕН.

Нужен, только если процедурный сбор (t249_box.py, лист t249_box2.png) Vitali не примет. Одна основа на семью: рисуется
91, 92 - зеркало, копии семьи - Lab-сдвигом (t249_box.py: FAMILY/build_all, после выбора кадра подменить DONOR на
art/tickets/t249/gen_box/series/URBAN_WASTE.PCK/91_<зерно>.png).

Путь - ровно strict_ctl_v1.do_render (obj_series.paint): STYLE["strict"], NEGATIVE probe_object, pick_background, bicubic x16,
Qwen-Image-2.1 40 шагов, cfg 4, 1 Мп, cut_out grow 2 / soft 40, match_tone 0.7, pad 3. К описанию добавлен блок ракурса боя
battle_view.prompt_block("object") (не своими словами), к негативу - его negative. Четыре зерна на один кадр классики 91;
выбор - Vitali по листу (py -3.13 tools/hdart/t249_box_gen.py sheet).

    py -3 tools\gpuq.py add --name t249-box --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t249_box_gen.py render
    py -3.13 tools/hdart/t249_box_gen.py sheet
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image, ImageDraw, ImageFont         # noqa: E402

OUT = os.path.join(ROOT, "art", "tickets", "t249", "gen_box")
SEEDS = [24901, 24902, 24903, 24904]
WHAT = ("a wrecked wooden crate, the remains of a broken wooden box: the front and side walls are weathered planks of "
        "grey-brown wood with visible grain and nails, the top is smashed open with jagged broken plank ends, "
        "inside is a deep soft shadow, no loose splinters piled inside, no red parts, no lid")
STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 2, 40, 3, 0.7


def do_render():
    import map_mockup as mm
    import probe_object as po
    import battle_view as bv
    w = mm.World()
    os.makedirs(os.path.join(OUT, "raw"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "series", "URBAN_WASTE.PCK"), exist_ok=True)
    ns = argparse.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS,
                            qwen21_cfg=CFG, qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model",
                            qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    blk = bv.prompt_block("object")
    po.gen_fire.NEGATIVE = po.NEGATIVE + ", " + blk["negative"]
    args = argparse.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    full = w.sprite("urban_waste", 91, None).convert("RGBA")
    bb = full.split()[3].getbbox()
    box = (max(0, bb[0] - PAD), max(0, bb[1] - PAD), min(full.width, bb[2] + PAD), min(full.height, bb[3] + PAD))
    frame = full.crop(box)
    panel = po.pick_background(frame)
    src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
    flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
    flat.alpha_composite(src)
    prompt = po.STYLE["strict"].replace("{what}", WHAT) + " " + blk["positive"]
    t0 = time.time()
    for n, seed in enumerate(SEEDS, 1):
        hd = po.gen_fire.run_pass(painter, args, prompt, flat.convert("RGB"), seed)
        po.gen_hd.save_png(hd, os.path.join(OUT, "raw", "91_%d.png" % seed))
        part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT), frame, TONE)
        cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        po.gen_hd.save_png(cut, os.path.join(OUT, "series", "URBAN_WASTE.PCK", "91_%d.png" % seed))
        print("[%d/%d] зерно %d готово, %.0f с" % (n, len(SEEDS), seed, time.time() - t0), flush=True)


def do_sheet():
    import ticket_scene as ts
    sc = ts.Scene()
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    cells = [("классика", sc.classic("URBAN_WASTE", 91)), ("сейчас", sc.hd("URBAN_WASTE", 91))]
    for seed in SEEDS:
        p = os.path.join(OUT, "series", "URBAN_WASTE.PCK", "91_%d.png" % seed)
        if os.path.exists(p):
            cells.append(("зерно %d" % seed, Image.open(p).convert("RGBA")))
    k = 3
    sh = Image.new("RGB", (len(cells) * (128 * k // 1 + 8) + 8, 90 * k + 32), (18, 18, 18))
    d = ImageDraw.Draw(sh)
    for i, (t, im) in enumerate(cells):
        c = im.resize((128, 160), Image.NEAREST).crop((0, 70, 128, 160)).resize((128 * k, 90 * k), Image.NEAREST) \
            if im.width == 32 else im.crop((0, 70, 128, 160)).resize((128 * k, 90 * k), Image.LANCZOS)
        bg = Image.new("RGBA", c.size, (110, 110, 116, 255))
        bg.alpha_composite(c)
        sh.paste(bg.convert("RGB"), (8 + i * (128 * k + 8), 28))
        d.text((8 + i * (128 * k + 8), 4), t, fill=(255, 220, 0), font=font)
    p = os.path.join(OUT, "sheet.png")
    sh.save(p)
    print("лист:", p)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "sheet"])
    a = ap.parse_args()
    {"render": do_render, "sheet": do_sheet}[a.cmd]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
