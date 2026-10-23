#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000276 (сухая трава MOUNTGRASS:8, CULTIVAT:11), XP-000278 (колючий куст MOUNTGRASS:15), XP-000279
(ель MOUNTGRASS:64+65 одним деревом) - генерация, Vitali 23.10 «Арт разрешаю». Только кандидаты в
art/tickets/t276_278_279/gen: в мод ничего не ставится (подключение - после выбора Vitali, t276_build.py).

Путь генерации - ровно t_jungle_stumps.do_render (obj_series.paint, strict_ctl_v1): STYLE["strict"], NEGATIVE
probe_object, подложка pick_background, bicubic x16, Qwen-Image-2.1 40 шагов, cfg 4, 1 Мп, cut_out grow 2 / soft 40,
match_tone 0.7, pad 3. Ракурс и свет - battle_view.prompt_block("object"). Описание - по пикселям классики (R-456).
Альфа - по маске классики (cut_out: силуэт x4, R-089), не по фону ответа. Один процесс на задание (R-215).

Ель: вход - классика стопкой 64 (z0, на 24 пикселя ниже) + 65 (z1) одним холстом 32x64; ответ - ОДНО дерево, которое
build режет по маскам классики на 64 и 65 (стык не рисуется заново - срезов нет).

    py -3 tools\gpuq.py add --name t276-grass8 --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t276_gen.py render grass8
    (то же: grass11, flowers9, bush15, spruce)
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
BASE = os.path.join(ROOT, "art", "tickets", "t276_278_279")
GEN = os.path.join(BASE, "gen")

JOBS = {
    # кадр(ы): [(набор, кадр, dy)] - dy в пикселях k=1 от верха холста; сиды; описание
    "grass8": dict(
        parts=[("MOUNTGRASS", 8, 0)], seeds=[8101, 8102, 8103, 8104, 8105, 8106],
        what=("a low clump of dry dead wild grass: thin brittle stalks and blades in very dark purple-black with "
              "grey-lilac dry tips, a little dark green-black deep inside the clump, many stalks sticking up and "
              "slightly outward, and a small patch of bare light brown dirt at the lower tips of the clump"),
        neg=", fresh green grass, flowers, rocks, stones, logs, mushrooms, bright colors"),
    "grass11": dict(
        parts=[("CULTIVAT", 11, 0)], seeds=[1101, 1102, 1103, 1104, 1105, 1106],
        what=("a tall clump of dry dead wild grass: thin brittle stalks and blades in very dark purple-black with "
              "grey-lilac dry tips, a few long stalks sticking up at the top and sides, a little dark green-black "
              "deep inside the clump, and a small patch of bare light brown dirt at the lower tips of the clump"),
        neg=", fresh green grass, flowers, rocks, stones, logs, mushrooms, bright colors"),
    "flowers9": dict(
        parts=[("MOUNTGRASS", 9, 0)], seeds=[9101, 9102, 9103, 9104, 9105, 9106],
        what=("a loose low bush of green grass blades and leaves in several shades of green, darker deep inside and "
              "lighter at the tips, with only a few tiny sparse flowers on it: four small pale blue-cyan flowers, "
              "four small red flowers and two small pink flowers, scattered between the blades, the flowers much "
              "smaller than the bush"),
        neg=", stones, pebbles, rocks, gems, balls, dense flowerbed, big flowers, bouquet, flower field, fruit, berries"),
    "bush15": dict(
        parts=[("MOUNTGRASS", 15, 0)], seeds=[1501, 1502, 1503, 1504, 1505, 1506],
        what=("a dense tangle of dry thorny bramble branches: many thin crossing dead twigs in rusty orange-brown "
              "and dark maroon, with black gaps between them, a few twigs sticking out at the left and at the "
              "bottom, a heap of dead brushwood"),
        neg=", green leaves, flowers, stripes, maze pattern, spiral, rocks, wooden planks, fence, net, bright colors"),
    "spruce": dict(
        parts=[("MOUNTGRASS", 64, 24), ("MOUNTGRASS", 65, 0)], seeds=[6401, 6402, 6403, 6404, 6405, 6406],
        what=("one tall spruce tree with a thin dark red brown trunk: the lower half has a few sparse dark green "
              "needle branches spreading sideways with the trunk visible between them, the upper half is a dense "
              "narrow cone of layered dark green needle branches with lighter green tips, dark roots at the base"),
        neg=", cut tree, tree stump, sawn trunk, two trees, snow, orange leaves"),
}


def classic_stack(job):
    """Классика задания k=1 RGBA: один кадр или стопка этажей (z1 выше на 24, P_Level у обоих 0)."""
    import map_mockup as mm
    w = mm.World()
    parts = JOBS[job]["parts"]
    H = 40 + max(dy for _s, _f, dy in parts)
    out = Image.new("RGBA", (32, H), (0, 0, 0, 0))
    for s, f, dy in sorted(parts, key=lambda p: -p[2]):     # нижний этаж (больший dy) рисуется первым
        out.alpha_composite(w.sprite(s.lower(), f, None).convert("RGBA"), (0, dy))
    return out


def padded_box(img, pad=PAD):
    bb = img.split()[3].getbbox()
    return (max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad))


def do_render(job):
    import map_mockup as mm   # noqa: F401  (World внутри classic_stack)
    import probe_object as po
    import battle_view as bv
    J = JOBS[job]
    sd = os.path.join(GEN, job)
    os.makedirs(os.path.join(sd, "raw"), exist_ok=True)
    ns = argparse.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS,
                            qwen21_cfg=CFG, qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model",
                            qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    blk = bv.prompt_block("object")
    po.gen_fire.NEGATIVE = po.NEGATIVE + ", " + blk["negative"] + J["neg"]
    args = argparse.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    prompt = po.STYLE["strict"].replace("{what}", J["what"]) + " " + blk["positive"]
    full = classic_stack(job)
    box = padded_box(full)
    frame = full.crop(box)
    panel = po.pick_background(frame)
    src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
    flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
    flat.alpha_composite(src)
    t0 = time.time()
    for n, seed in enumerate(J["seeds"], 1):
        dst = os.path.join(sd, "%d.png" % seed)
        if os.path.exists(dst):
            print("[%d/%d] %s зерно %d уже есть" % (n, len(J["seeds"]), job, seed), flush=True)
            continue
        hd = po.gen_fire.run_pass(painter, args, prompt, flat.convert("RGB"), seed)
        po.gen_hd.save_png(hd, os.path.join(sd, "raw", "%d.png" % seed))
        part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT), frame, TONE)
        cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        po.gen_hd.save_png(cut, dst)
        print("[%d/%d] %s зерно %d готово, %.0f с" % (n, len(J["seeds"]), job, seed, time.time() - t0), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("job", choices=sorted(JOBS))
    a = ap.parse_args()
    do_render(a.job)
    return 0


if __name__ == "__main__":
    sys.exit(main())
