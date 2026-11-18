#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пробы тикетов про картинку: Qwen-Image-2.1 strict по эскизу классики (путь obj_series.paint), ракурс и свет -
только блок battle_view.prompt_block. В мод НЕ пишет: кадры идут в art/_review/xpNNN/gen/.

Одобренный промпт серии (probe_object.STYLE["strict"]) переписан со своими словами про ракурс и свет на
фразы battle_view; остальное - как в серии: подложка pick_background, bicubic x16, 40 шагов, cfg 4, 1 Мп,
вырезка cut_out по силуэту классики, match_tone 0.7, запас pad 3 (R-112: настройки не менять).

Каждая задача - свой процесс (R-215: Qwen-2.1 копит память на длинной партии). Готовое пропускается.

    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\ticket_q21_probe.py --job wheat
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image, ImageOps                      # noqa: E402

import battle_view as bv                             # noqa: E402
import map_mockup as mm                              # noqa: E402
import obj_series as osr                             # noqa: E402
import probe_object as po                            # noqa: E402

PANEL_HINT = ("<image1> is the low-resolution original sprite of {what}, shown on a flat grey preview panel. "
              "The panel is interface, not part of the sprite. "
              "Use case: sketch-to-render. Asset type: polished 4x HD sprite for an X-COM-style strategy game. ")
KEEP = ("Redraw this same {noun} as detailed hand-painted game artwork: {what}. Keep the position, the size, "
        "the silhouette and the palette of <image1>. Clear readable shapes, crisp edges, fine painted detail. ")
TAIL_OBJ = ("The tile diamond named above is only an invisible placement guide: draw no slab, no paving and no "
            "base plate under the object. Output one isolated object on the same flat panel. No ground, no tile, "
            "no other objects, no frame, no text.")
SLAB_NEG = "stone slab, paving tiles, base plate, floor tiles, ground square"
TAIL_FLOOR = ("Output one isolated ground tile on the same flat panel: the ground fills the whole diamond to its "
              "edges, evenly, with no border and no frame. No other objects, no text.")

SHADE = ("Keep the shading of <image1>: the top is brightest and the lower and side parts fall into deep shade. ")

# задача: куда, вид боя, что рисуем, кадры (набор, кадр) - первый рисуется, остальные - его копии/зеркала
JOBS = {
    "wheat": dict(
        out="art/_review/xp302/gen", kind="object", noun="object",
        what="a cube-shaped block of ripe golden wheat, dense upright stalks with wheat ears; the sunlit top is "
             "bright golden, the lower part and the side faces are deep brown shade",
        frames=[("CULTIVAT", 4)], copies=[("VILROADS", 1)], mirrors=[],
        variants=[("a", 2715, ""), ("b", 3311, ""), ("c", 4717, SHADE)],
        neg_extra="roof tiles, shingles, bricks, flat texture, fence"),
    "grass1": dict(
        out="art/_review/xp304/gen", kind="floor", noun="ground tile",
        what="a ground tile of brown earth with sparse thin green grass blades and a few pink-brown dry shoots "
             "standing up from it",
        frames=[("MOUNTMUD", 1)], copies=[], mirrors=[("MOUNTMUD", 2)],
        variants=[("a", 2712, ""), ("b", 3312, ""), ("c", 4712, "")], neg_extra=""),
    "grass7": dict(
        out="art/_review/xp305/gen", kind="floor", noun="ground tile",
        what="a ground tile of brown earth thickly covered with upright green grass blades, red-brown specks "
             "and pink-grey dry stems standing up from it",
        frames=[("MOUNTMUD", 7)], copies=[], mirrors=[],
        variants=[("a", 2717, ""), ("b", 3317, ""), ("c", 4717, "")], neg_extra=""),
    "grass9": dict(
        out="art/_review/xp305/gen", kind="floor", noun="ground tile",
        what="a ground tile of brown earth thickly covered with upright green grass blades, red-brown specks "
             "and pink-grey dry stems standing up from it",
        frames=[("MOUNTMUD", 9)], copies=[], mirrors=[],
        variants=[("a", 2719, ""), ("b", 3319, ""), ("c", 4719, "")], neg_extra=""),
    "stairs2": dict(
        out="art/_review/xp331/gen", kind="object", noun="object",
        what="a broad, short, straight wooden staircase with about nine wide tan plank steps climbing from the "
             "lower left to the upper right, as wide as the block it stands in; at the top right it joins a solid "
             "wooden block of vertical planks with a small dark hollow under the top steps and a thin dark "
             "plinth at the base",
        frames=[("VILBAN", 22), ("VILBAN", 21)], copies=[], mirrors=[], composite=True,
        variants=[("d", 2733, ""), ("e", 3333, ""), ("f", 4733, "")], neg_extra="long thin ramp, narrow stairs"),
    "pump": dict(
        out="art/_review/xp332/gen", kind="object", noun="object",
        what="a grey-lilac metal gas pump with a green display on top, a yellow label with a red emblem on the "
             "front and a black fuel hose hanging on its right side",
        frames=[("VILFRNITURE", 71)], copies=[], mirrors=[("VILBAN", 81)],
        variants=[("a", 2771, ""), ("b", 3371, ""), ("c", 4771, "")], neg_extra=""),
    "pump2": dict(
        out="art/_review/xp332/gen", kind="object", noun="object",
        what="a grey-lilac metal gas pump with a green display on top, a yellow label with a red emblem on the "
             "front and a black fuel hose hanging on its right side",
        frames=[("VILFRNITURE", 71)], copies=[], mirrors=[("VILBAN", 81)],
        variants=[("d", 2781, "Draw only the pump itself, its foot rests directly on the panel: no diamond outline, no outline of a tile and no thin lines around its foot."), ("e", 3381, "Draw only the pump itself, its foot rests directly on the panel: no diamond outline, no outline of a tile and no thin lines around its foot."), ("f", 4781, "Draw only the pump itself, its foot rests directly on the panel: no diamond outline, no outline of a tile and no thin lines around its foot.")],
        neg_extra="diamond outline, outline of a tile, thin lines around the foot, shadow ellipse"),
    "well": dict(
        out="art/_review/xp333/gen", kind="object", noun="object",
        what="a squat, wide well of rough dark charcoal-grey stones with a black opening, filling the whole width, "
             "with a wooden crane in front of it: two brown posts at the far left and the far right, a crossbeam "
             "between them rising to the right, and a pale rope hanging from the middle of the beam into the well",
        frames=[("WESTFLOOR", 7)], copies=[("MEDIEVAL", 1)], mirrors=[],
        variants=[("a", 2707, ""), ("b", 3307, ""), ("c", 4707, "")], neg_extra=""),
    # XP-000596: камни пустыни - в классике тёмно-серый камень, у HD была жёлтая песчаная ямка сверху
    "rock23": dict(
        out="art/_review/xp596/gen", kind="object", noun="object",
        what="one solid rough desert boulder of dark charcoal-grey stone with a rounded top, the upper right "
             "edge lighter grey with a few pale grey-tan highlights, the lower left part in deep near-black "
             "shade, a few small loose orange sand grains at its foot",
        frames=[("XOPSDESERT", 23)], copies=[("DESERT", 23)], mirrors=[],
        variants=[("a", 2723, ""), ("b", 3323, ""), ("c", 4723, "")],
        neg_extra="yellow sand on top, sand pit, hollow, crater, bowl, orange centre, egg shape"),
    "rock25": dict(
        out="art/_review/xp596/gen", kind="object", noun="object",
        what="two solid rough desert boulders of dark charcoal-grey stone lying side by side and touching, "
             "a wide low pair, their rounded tops lighter grey with a few pale grey-tan highlights, the lower "
             "parts in deep near-black shade, a few small loose orange sand grains at their foot",
        frames=[("XOPSDESERT", 25)], copies=[("DESERT", 25)], mirrors=[],
        variants=[("a", 2725, ""), ("b", 3325, ""), ("c", 4725, "")],
        neg_extra="yellow sand on top, sand pit, hollow, crater, bowl, orange centre, egg shape"),
    "stairs": dict(
        out="art/_review/xp331/gen", kind="object", noun="object",
        what="one long straight wooden staircase of tan planks rising from the lower left to the upper right, "
             "ending in a solid wooden box with a dark hollow opening under the steps",
        frames=[("VILBAN", 22), ("VILBAN", 21)], copies=[], mirrors=[], composite=True,
        variants=[("a", 2722, ""), ("b", 3322, ""), ("c", 4722, "")], neg_extra=""),
}


def build_prompt(job, extra):
    pb = bv.prompt_block(job["kind"])
    tail = TAIL_FLOOR if job["kind"] == "floor" else TAIL_OBJ
    what = job["what"]
    text = (PANEL_HINT.replace("{what}", what) + bv.view_sentence(job["kind"]) + " "
            + KEEP.replace("{noun}", job["noun"]).replace("{what}", what) + bv.light_sentence(job["kind"]) + " "
            + (extra + " " if extra else "") + tail)
    neg = po.NEGATIVE
    if job["kind"] == "floor":
        # у пола земля и трава - содержание кадра
        neg = neg.replace("ground, grass tile, floor, ", "")
    if job["kind"] == "object":
        neg = neg + ", " + SLAB_NEG
    neg = neg + ", " + pb["negative"] + (", " + job["neg_extra"] if job["neg_extra"] else "")
    return text, neg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True, choices=sorted(JOBS))
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--grow", type=int, default=2)
    ap.add_argument("--soft", type=int, default=40)
    ap.add_argument("--pad", type=int, default=3)
    ap.add_argument("--tone", type=float, default=0.7)
    ap.add_argument("--offload", default="model")
    ap.add_argument("--dry-run", action="store_true", dest="dry")
    args = ap.parse_args()
    job = JOBS[args.job]
    out = job["out"]
    os.makedirs(out, exist_ok=True)
    world = mm.World()
    spr = {k: world.sprite(k[0], k[1], None).convert("RGBA")
           for k in job["frames"] + job["copies"] + job["mirrors"]}

    comp = None
    if job.get("composite"):
        # нижний марш (21) лежит на (-16, +8) от верхнего (22): клетки (37,49) и (37,48), один этаж
        k22, k21 = ("VILBAN", 22), ("VILBAN", 21)
        comp = {"members": [(k22, (0, 0, 0)), (k21, (-16, 8, 0))], "spr": {k22: spr[k22], k21: spr[k21]},
                "pl": {k22: 0, k21: 0}}
        full, at = osr.compose(comp)
    else:
        full = spr[job["frames"][0]]
    key0 = "%s_%d" % job["frames"][0]

    for suffix, seed, extra in job["variants"]:
        text, neg = build_prompt(job, extra)
        print("[%s %s] seed %d\n  PROMPT: %s\n  NEG: %s" % (args.job, suffix, seed, text, neg), flush=True)
    if args.dry:
        return

    import argparse as ap2
    ns = ap2.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=args.steps,
                       qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0, qwen21_offload=args.offload,
                       qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                       qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    run_args = ap2.Namespace(mp=args.mp, steps=args.steps, cfg=args.cfg)

    bb = full.split()[3].getbbox()
    box = (max(0, bb[0] - args.pad), max(0, bb[1] - args.pad),
           min(full.width, bb[2] + args.pad), min(full.height, bb[3] + args.pad))
    frame = full.crop(box)
    t0, n = time.time(), 0
    for suffix, seed, extra in job["variants"]:
        final = os.path.join(out, "%s_%s.png" % (key0, suffix))
        if os.path.exists(final) or (comp and os.path.exists(os.path.join(out, "VILBAN_21_%s.png" % suffix))):
            print("готово, пропуск:", args.job, suffix, flush=True)
            continue
        text, neg = build_prompt(job, extra)
        po.gen_fire.NEGATIVE = neg
        panel = po.pick_background(frame)
        src = frame.resize((frame.width * args.zoom, frame.height * args.zoom), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        hd = po.gen_fire.run_pass(painter, run_args, text, flat.convert("RGB"), seed)
        po.gen_hd.save_png(hd, os.path.join(out, "raw_%s_%s.png" % (args.job, suffix)))
        part = po.match_tone(po.cut_out(hd, frame, args.grow, args.soft), frame, args.tone)
        cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        if comp:
            pieces = osr.split(cut, comp, at, args.grow)
            po.gen_hd.save_png(cut, os.path.join(out, "whole_%s.png" % suffix))
            for (s, f), im in ((k, pieces[k]) for k in (k22, k21)):
                po.gen_hd.save_png(im, os.path.join(out, "%s_%d_%s.png" % (s, f, suffix)))
        else:
            po.gen_hd.save_png(cut, final)
            for (s, f) in job["copies"]:
                po.gen_hd.save_png(cut, os.path.join(out, "%s_%d_%s.png" % (s, f, suffix)))
            for (s, f) in job["mirrors"]:
                # зеркало основы; тон - к классике зеркального кадра (у перекраски свой цвет)
                m = po.match_tone(ImageOps.mirror(cut), spr[(s, f)], args.tone)
                po.gen_hd.save_png(m, os.path.join(out, "%s_%d_%s.png" % (s, f, suffix)))
        n += 1
        el = time.time() - t0
        print("[%s %s] готово %d/%d, %s" % (args.job, suffix, n, len(job["variants"]), po.gen_hd.human_time(el)),
              flush=True)
    print("готово за %s" % po.gen_hd.human_time(time.time() - t0))


if __name__ == "__main__":
    main()
