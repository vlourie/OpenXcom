#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000509 / XP-000510, генерация по выбору Vitali 05.11 (вариант «генерация одной основы на семью»), только через очередь видеокарты:

    py -3 tools\gpuq.py add --name hb-flower --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\p509_gen.py render flower
    (то же: liana, bush3)
    без модели: p509_gen.py prep  - вход (классика на подложке) и описания, для проверки.

Путь - как t_jungle_stumps.do_render (obj_series.paint, strict_ctl_v1): STYLE["strict"], NEGATIVE probe_object, подложка
pick_background, bicubic x16, Qwen-Image-2.1 40 шагов, cfg 4, 1 Мп, cut_out grow 2 / soft 40, match_tone 0.7, pad 3.
Блок ракурса и света - battle_view.prompt_block("object"). Цветок - ОДНА картинка 2x2 (классика четырёх клеток по
раскладке карты: 24 сверху, 26 справа, 23 слева, 25 снизу), режется по клеткам (obj_series.split).
Альфа - по маске классики (R-089). Результат: art/tickets/hb509/gen/<имя>/<зерно>.png (RGBA x4, габарит классики).
"""
import argparse
import os
import sys
import time

HERE = r"E:\OpenXCom\tools\hdart"
ROOT = r"E:\OpenXCom"
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
os.chdir(ROOT)

from PIL import Image                               # noqa: E402

STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 2, 40, 3, 0.7
GEN = os.path.join(ROOT, "art", "tickets", "hb509", "gen")
SEEDS = {"flower": [5091, 5092, 5093, 5094], "liana": [5171, 5172, 5173, 5174], "bush3": [5103, 5104, 5105, 5106]}

TAIL = ", matte, soft light from the upper left, drawn in the same hand-painted style as the dark green jungle plants around"
WHAT = {
    "flower": ("one alien jungle flower lying on the ground, seen from above at an angle: a medium round red-crimson flower head with layered petals and a bright orange-yellow glowing centre in the middle of the sprite, a small cyan-blue dewdrop at the upper left of the head, broad dark-green and almost black leaves spread around the head, and several thin brown bendy tendrils that reach far out from under the leaves to the upper left, the upper right, the lower right and the bottom" + TAIL +
               "; one single plant, no pot, no stem going up, no other flowers, no blue flower"),
    "liana": ("a low tangle of thin green jungle vines lying flat on the ground, bright lime-green and darker green thin curling "
              "stems with a few tiny leaves, spreading mostly sideways, a few small light-green highlights" + TAIL +
              "; thin stems only, no flowers, no big leaves, no rocks"),
    "bush3": ("a round dense jungle bush with a visible thin orange-brown twisting trunk at the bottom, the crown made of "
              "overlapping rows of medium green and dark green leaves with a few small orange-red dots among the leaves" + TAIL +
              "; one plant, no flowers, no fruits other than the tiny orange dots"),
}


def classic_frame(w, s, f):
    return w.sprite(s.lower(), f, None).convert("RGBA")


def flower_whole(w):
    """Классика 2x2 цветка одной картинкой: (картинка 64x56, {кадр: (x, y)})."""
    at = {24: (16, 0), 26: (32, 8), 23: (0, 8), 25: (16, 16)}
    im = Image.new("RGBA", (64, 56), (0, 0, 0, 0))
    for f in (24, 23, 26, 25):
        im.alpha_composite(classic_frame(w, "JUNGLEBITS", f), at[f])
    return im, at


def whole_for(w, name):
    if name == "flower":
        return flower_whole(w)[0]
    if name == "liana":
        return classic_frame(w, "MUJUNGLE", 17)
    return classic_frame(w, "JUNGLEBITS", 3)


def do_render(name, prep_only=False):
    import map_mockup as mm
    import probe_object as po
    import battle_view as bv
    w = mm.World()
    sd = os.path.join(GEN, name)
    os.makedirs(os.path.join(GEN, "raw"), exist_ok=True)
    os.makedirs(sd, exist_ok=True)
    blk = bv.prompt_block("object")
    prompt = po.STYLE["strict"].replace("{what}", WHAT[name]) + " " + blk["positive"]
    full = whole_for(w, name)
    bb = full.split()[3].getbbox()
    box = (max(0, bb[0] - PAD), max(0, bb[1] - PAD), min(full.width, bb[2] + PAD), min(full.height, bb[3] + PAD))
    frame = full.crop(box)
    panel = po.pick_background(frame)
    src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
    flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
    flat.alpha_composite(src)
    if prep_only:
        flat.save(os.path.join(GEN, "raw", "in_%s.png" % name))
        print(name, "вход", flat.size, "панель", panel, "\n", prompt)
        return
    ns = argparse.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS,
                            qwen21_cfg=CFG, qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model",
                            qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    po.gen_fire.NEGATIVE = po.NEGATIVE + ", " + blk["negative"] + ", pot, vase, stem going up, extra flowers, blue flower"
    args = argparse.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    t0 = time.time()
    for n, seed in enumerate(SEEDS[name], 1):
        dst = os.path.join(sd, "%d.png" % seed)
        if os.path.exists(dst):
            print("[%d/%d] %s зерно %d уже есть" % (n, len(SEEDS[name]), name, seed), flush=True)
            continue
        hd = po.gen_fire.run_pass(painter, args, prompt, flat.convert("RGB"), seed)
        po.gen_hd.save_png(hd, os.path.join(GEN, "raw", "%s_%d.png" % (name, seed)))
        part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT), frame, TONE)
        cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        po.gen_hd.save_png(cut, dst)
        print("[%d/%d] %s зерно %d готово, %.0f с" % (n, len(SEEDS[name]), name, seed, time.time() - t0), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render", "prep"])
    ap.add_argument("name", nargs="?", default="")
    a = ap.parse_args()
    if a.cmd == "prep":
        for n in WHAT:
            do_render(n, True)
        return 0
    do_render(a.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
