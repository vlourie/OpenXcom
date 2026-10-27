#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Мёртвые кадры джунглей JUNGLESTYX 62, 63, 64 (остаток живых растений 23/28 -> 62, 29 -> 63, 30 -> 64 после взрыва
или обрушения, Die_MCD; Vitali 23.10 «Арт разрешаю»). Семья (ticket_family.py): JUNGLEBITS:62-64 - перекраска, класс
тот же (тот же остаток), HD сейчас у них sdxl_legacy с оранжево-бурым тоном (у классики JUNGLEBITS другая рампа).

Путь генерации - ровно t_regen_obj.do_render (obj_series.paint, strict_ctl_v1): STYLE["strict"], NEGATIVE probe_object,
подложка pick_background, bicubic x16, Qwen-Image-2.1 40 шагов, cfg 4, 1 Мп, cut_out grow 2 / soft 40, match_tone 0.7,
pad 3. Блок ракурса и света - battle_view.prompt_block("object"), негатив ракурса дописан. Описание - по пикселям
классики (R-456): тёмно-бордовая и пепельно-серая палая листва, чёрно-зелёный клочок, светящиеся красные жилки и нити.
Альфа - по маске классики (cut_out: силуэт x4, R-089), не по фону ответа. На кадр 4 зерна, один процесс на кадр (R-215).

    py -3 tools\gpuq.py add --name jstump-62 --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t_jungle_stumps.py render 62
    (то же для 63 и 64)
    Листы, сборка и установка (без видеокарты) - t_jungle_stumps_build.py.
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

from PIL import Image                               # noqa: E402

STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 2, 40, 3, 0.7
SET = "JUNGLESTYX"
BASE = os.path.join(ROOT, "art", "tickets", "jungle_stumps")
GEN = os.path.join(BASE, "gen")
OUT = os.path.join(BASE, "out")
SEEDS = {62: [6201, 6202, 6203, 6204], 63: [6301, 6302, 6303, 6304], 64: [6401, 6402, 6403, 6404]}
LIVE = {62: [23, 28], 63: [29], 64: [30]}       # живые записи, чей остаток - кадр
FAMILY = [("JUNGLEBITS", 62), ("JUNGLEBITS", 63), ("JUNGLEBITS", 64)]

TAIL = ("; the dark material is the same burnt jungle plant, matte, soft light from the upper left; "
        "not a tree stump, no wood, no rocks, no fresh green leaves, no flowers, no blue parts")
WHAT = {
    62: ("the charred remains of an alien jungle plant: a clump of burnt, curled leaf pieces in dark maroon-brown and ash grey, "
         "a small dark green-black leaf mass at the left of the centre, glowing red-crimson veins on the leaves and thin "
         "red glowing tendrils stretching out to the left and to the right" + TAIL),
    63: ("the charred remains of an alien jungle plant: a low heap of burnt dark maroon-brown and ash grey leaf pieces, "
         "a glowing red ember core left of the centre, a dark green-black leaf at the right, thin crimson glowing "
         "tendrils trailing to the lower right" + TAIL),
    64: ("the charred remains of an alien jungle plant: a low flat heap of burnt dark brown-maroon leaf pieces with grey "
         "ash, glowing bright red-orange embers at the bottom front, one thin crimson tendril sticking out to the right" + TAIL),
}


def do_render(fr):
    import map_mockup as mm
    import probe_object as po
    import battle_view as bv
    sd = os.path.join(GEN, "series", SET + ".PCK")
    os.makedirs(os.path.join(GEN, "raw"), exist_ok=True)
    os.makedirs(sd, exist_ok=True)
    w = mm.World()
    ns = argparse.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS,
                            qwen21_cfg=CFG, qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model",
                            qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    blk = bv.prompt_block("object")
    po.gen_fire.NEGATIVE = po.NEGATIVE + ", " + blk["negative"] + ", tree stump, wood, fresh green leaves, flower, blue light"
    args = argparse.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    prompt = po.STYLE["strict"].replace("{what}", WHAT[fr]) + " " + blk["positive"]
    full = w.sprite(SET.lower(), fr, None).convert("RGBA")
    bb = full.split()[3].getbbox()
    box = (max(0, bb[0] - PAD), max(0, bb[1] - PAD), min(full.width, bb[2] + PAD), min(full.height, bb[3] + PAD))
    frame = full.crop(box)
    panel = po.pick_background(frame)
    src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
    flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
    flat.alpha_composite(src)
    t0 = time.time()
    for n, seed in enumerate(SEEDS[fr], 1):
        dst = os.path.join(sd, "%d_%d.png" % (fr, seed))
        if os.path.exists(dst):
            print("[%d/%d] кадр %d зерно %d уже есть" % (n, len(SEEDS[fr]), fr, seed), flush=True)
            continue
        hd = po.gen_fire.run_pass(painter, args, prompt, flat.convert("RGB"), seed)
        po.gen_hd.save_png(hd, os.path.join(GEN, "raw", "%d_%d.png" % (fr, seed)))
        part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT), frame, TONE)
        cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        po.gen_hd.save_png(cut, dst)
        print("[%d/%d] кадр %d зерно %d готово, %.0f с" % (n, len(SEEDS[fr]), fr, seed, time.time() - t0), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("frame", type=int, choices=[62, 63, 64])
    a = ap.parse_args()
    do_render(a.frame)
    return 0


if __name__ == "__main__":
    sys.exit(main())
