#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000515 (бочка XB2BR:24), XP-000516 (ракеты XB2BR:10, 11), XP-000517 (кресла U_WALL_G 37, 39): заготовки
по выбору Vitali 05.11. В МОД НИЧЕГО НЕ СТАВИТ: основы - art/tickets/hb517/gen/<задание>/<зерно>.png, кадры кандидатов
и семьи - art/tickets/hb517/cand/<вариант>/<НАБОР>_<кадр>.png, листы - art/tickets/hb517/sheets/ (hb517_build.py).

Путь генерации - как t405_409_gen / ticket_q21_probe: Qwen-Image-2.1 strict, 40 шагов, cfg 4, 1 Мп, вход - классика
bicubic x16 на подложке pick_background, негатив probe_object + battle_view, cut_out (R-089: альфа - силуэт классики
x4 со сглаживанием xBRZ, R-121, а не фон ответа), match_tone 0.7. Ракурс и свет - ТОЛЬКО battle_view.
Отличия от t405_409_gen: (1) у кресел вторым входом идёт опора - одобренный HD U_WALL_G:38 (тот же кадр, что и
классика, на той же подложке и в том же масштабе; порядок ref-last: кадр первым, R-044); (2) ракеты 10 и 11 - ОДНОЙ
картинкой (две классики рядом), чтобы это был один предмет с двух сторон; режется по кадрам.

    py -3 tools\gpuq.py add --name hb517-gen --prio 1 -- E:\OpenXCom\tools\hdart\.venv-qwen21\Scripts\python.exe E:\OpenXCom\tools\hdart\hb517_gen.py render
    py -3.13 tools\hdart\hb517_gen.py prompts          # тексты, без модели
    py -3.13 tools\hdart\hb517_gen.py recut            # перевырезка из raw без видеокарты
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
os.chdir(ROOT)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402

STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 2, 40, 3, 0.7
GEN = os.path.join(ROOT, "art", "tickets", "hb517", "gen")
GAME = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd", "TERRAIN")

CHAIR_COMMON = ("a swivel chair of the same ship set: warm golden-tan lacquered metal, a thick round cushioned seat "
                "disc, a tall flat backrest panel with a perfectly straight smooth top edge, and a round dark-brown "
                "bronze base disc with a ring of small round rivets along its rim. The backrest is one solid piece "
                "with a gently embossed relief on it only: no holes, no dots, no lights, no notches, no cut-outs")
REF_NOTE = ("<image2> is the approved reference of the very same swivel chair seen from the opposite side: copy its "
            "material, golden-tan colour, soft shading and the riveted bronze base from it, but NOT its pose; the "
            "pose is the one of <image1>. ")

JOBS = {
    "chair39": dict(
        members=[("U_WALL_G", 39)], seeds=[5391, 5392, 5393], ref=("U_WALL_G", 38, False),
        what=(CHAIR_COMMON + ". Seen from behind at an angle: the tall backrest stands in the FOREGROUND on the left, "
              "nearest to the viewer, and its back hides the left part of the seat; the round seat cushion shows behind "
              "the backrest, to its right"),
        neg=("backrest behind the seat, seat in front of the backrest, jagged top, notched top edge, glowing lights, "
             "dots, lamps, holes, cut-outs, armrests, wheels, legs, pedestal stem"), note=REF_NOTE),
    "chair37": dict(
        members=[("U_WALL_G", 37)], seeds=[5371, 5372, 5373], ref=("U_WALL_G", 38, False),
        what=(CHAIR_COMMON + ". Seen from the front: the tall backrest stands BEHIND the seat on the upper left, the "
              "round seat cushion in front of it, lower and to the right"),
        neg=("backrest in front of the seat, jagged top, notched top edge, glowing lights, dots, lamps, holes, "
             "cut-outs, armrests, wheels, legs, pedestal stem"), note=REF_NOTE),
    "barrel24": dict(
        members=[("XB2BR", 24)], seeds=[5241, 5242, 5243], ref=None,
        what=("a straight upright cylindrical steel drum for fuel or toxic liquid, perfectly straight vertical sides "
              "with no bulge, dull grey-lilac brushed metal, exactly two raised horizontal rolled ribs around the body "
              "(one near the top, one near the bottom), a flat round lid on top with a raised rim; a clean industrial "
              "metal barrel"),
        neg=("wooden barrel, wooden staves, planks, wood grain, bulging belly, curved sides, cask, keg, iron hoops, "
             "pallet, rack, text, label"), note=""),
    "rockets": dict(
        members=[("XB2BR", 10), ("XB2BR", 11)], seeds=[5111, 5112, 5113, 5114], ref=None, at=[(0, 0), (40, 0)],
        what=("one big bundle of six identical rockets stacked in two rows of three, lashed in an orange-gold metal "
              "cradle frame with thin crossbars, shown twice side by side as the same object from two sides. The "
              "rockets are painted metal: deep dark bottle-green with near-black green shadows and a narrow pale-green "
              "glossy highlight along the top of each body, exactly the dark greens of the input. The bundle fills the "
              "whole outline of the input, both rows are visible in both pictures. LEFT picture: the rocket noses point "
              "toward the lower left, each nose is a round closed smooth dark-green dome head (a rounded cone, not an "
              "open tube), and the bodies run back to the upper right inside the orange frame; every nose fits whole "
              "inside the outline. RIGHT picture: the same bundle turned, lying sideways, the long rockets run from the "
              "lower left to the upper right with round domed noses at one end and plain closed rounded tails at the "
              "other end, the orange frame crossbars under them; the tails are whole, simple, without flared bells, "
              "nozzles or open tubes, and nothing is cut off at the picture edge"),
        neg=("bright green, saturated lime green, plastic toy, glossy plastic, sausages, two rockets only, small "
             "bundle, open tube ends, hollow pipe ends, flared nozzle, bell-shaped tail, exhaust cone, cut off at the "
             "edge, single rocket, wooden crate, text"), note=""),
}
ORDER = ["chair39", "chair37", "barrel24", "rockets"]


def classic_k1(s, f):
    import map_mockup as mm
    return mm.World().sprite(s.lower(), f, None).convert("RGBA")


def comp_of(job):
    """Классика задания одной картинкой (RGBA k=1) и положение кадров на ней."""
    J = JOBS[job]
    at = J.get("at") or [(0, 0)] * len(J["members"])
    wd = max(a[0] for a in at) + 32
    full = Image.new("RGBA", (wd, 40), (0, 0, 0, 0))
    for (s, f), a in zip(J["members"], at):
        full.alpha_composite(classic_k1(s, f), a)
    return full, at


def padded_box(img, pad=PAD):
    bb = img.split()[3].getbbox()
    return (max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad))


def hd_now(s, f):
    p = os.path.join(GAME, s + ".PCK", "%d.png" % f)
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None


def ref_image(job, box, panel, size):
    """Опора: HD-кадр одобренного кресла на подложке, в том же окне и масштабе, что вход."""
    s, f, mir = JOBS[job]["ref"]
    hd = hd_now(s, f)
    if mir:
        hd = hd.transpose(Image.FLIP_LEFT_RIGHT)
    crop = hd.crop((box[0] * 4, box[1] * 4, box[2] * 4, box[3] * 4)).resize(size, Image.LANCZOS)
    flat = Image.new("RGBA", size, tuple(panel) + (255,))
    flat.alpha_composite(crop)
    return flat.convert("RGB")


def build_prompt(job):
    import battle_view as bv
    import probe_object as po
    import ticket_q21_probe as q
    J = JOBS[job]
    pb = bv.prompt_block("object")
    what = J["what"]
    text = (q.PANEL_HINT.replace("{what}", what) + J["note"] + bv.view_sentence("object") + " "
            + q.KEEP.replace("{noun}", "object").replace("{what}", what) + bv.light_sentence("object") + " " + q.TAIL_OBJ)
    neg = po.NEGATIVE + ", " + q.SLAB_NEG + ", " + pb["negative"] + ", " + J["neg"]
    return text, neg


def cut_seed(job, seed):
    import probe_object as po
    full, _at = comp_of(job)
    box = padded_box(full)
    frame = full.crop(box)
    hd = Image.open(os.path.join(GEN, job, "raw", "%d.png" % seed)).convert("RGB")
    part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT), frame, TONE)
    cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
    cut.paste(part, (box[0] * 4, box[1] * 4))
    cut.save(os.path.join(GEN, job, "%d.png" % seed))


def run_pass2(painter, prompt, neg, images, seed):
    """Как gen_fire.run_pass, но с несколькими входами: кадр первым, опора после (ref-last, R-044)."""
    torch = painter.torch
    import gen_hd
    W, H = gen_hd.qwen21_size(images[0].width, images[0].height, MP)
    srcs = [im.convert("RGB").resize((W, H), Image.LANCZOS) for im in images]
    kw = {"prompt": prompt, "num_inference_steps": STEPS, "generator": torch.Generator("cuda").manual_seed(seed)}
    if "image" in painter.accepts:
        kw["image"] = srcs if len(srcs) > 1 else srcs[0]
    elif "images" in painter.accepts:
        kw["images"] = srcs
    if "negative_prompt" in painter.accepts:
        kw["negative_prompt"] = neg
    if "true_cfg_scale" in painter.accepts:
        kw["true_cfg_scale"] = CFG
    elif "guidance_scale" in painter.accepts:
        kw["guidance_scale"] = CFG
    if "width" in painter.accepts:
        kw["width"], kw["height"] = W, H
    return painter.pipe(**kw).images[0]


def do_render(jobs):
    import argparse as ap2
    import probe_object as po
    ns = ap2.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS, qwen21_cfg=CFG,
                       qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="",
                       qwen21_ref_mp=1.0, qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    t0, n = time.time(), 0
    for job in jobs:
        J = JOBS[job]
        sd = os.path.join(GEN, job)
        os.makedirs(os.path.join(sd, "raw"), exist_ok=True)
        text, neg = build_prompt(job)
        print("[%s]\n  PROMPT: %s\n  NEG: %s" % (job, text, neg), flush=True)
        full, _at = comp_of(job)
        box = padded_box(full)
        frame = full.crop(box)
        panel = po.pick_background(frame)
        src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        flat = flat.convert("RGB")
        imgs = [flat]
        if J["ref"]:
            rimg = ref_image(job, box, panel, flat.size)
            rimg.save(os.path.join(sd, "raw", "ref.png"))
            imgs.append(rimg)
            text = text.replace("<image1>", "<image1>")      # кадр - первый вход, опора - <image2>
        flat.save(os.path.join(sd, "raw", "input.png"))
        for seed in J["seeds"]:
            dst = os.path.join(sd, "%d.png" % seed)
            if os.path.exists(dst):
                print("[%s] зерно %d уже есть" % (job, seed), flush=True)
                continue
            hd = run_pass2(painter, text, neg, imgs, seed)
            po.gen_hd.save_png(hd, os.path.join(sd, "raw", "%d.png" % seed))
            cut_seed(job, seed)
            n += 1
            print("[%s] зерно %d готово (%d), %.0f с" % (job, seed, n, time.time() - t0), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts"])
    ap.add_argument("--jobs", nargs="*", default=ORDER, choices=ORDER)
    a = ap.parse_args()
    if a.cmd == "prompts":
        for j in a.jobs:
            t, n = build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, t, n))
    elif a.cmd == "render":
        do_render(a.jobs)
    else:
        for j in a.jobs:
            for s in JOBS[j]["seeds"]:
                if os.path.exists(os.path.join(GEN, j, "raw", "%d.png" % s)):
                    cut_seed(j, s)
            print("перевырезано:", j)
    return 0


if __name__ == "__main__":
    sys.exit(main())
