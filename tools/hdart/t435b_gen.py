#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000435, вторая основа раковины: шесть кадров другого вида (одна дверца и конфорка) - CITYFRNITURE:15, COMFRN:15,
COMFRN2:9, FRNITURE:15, FRNITURE_WASTE:15, VILFRNITURE:14. Их классики попиксельно одинаковы (голубой шкаф), поэтому одна
основа и шесть копий; перекраска по классике своего набора - тот же кадр (recolor_any даёт «копия», IoU 1.00).
Путь - t435_gen (модуль g подменён: те же Qwen-2.1 strict, battle_view, подложка вручную R-089, гладкий срез R-121).
Кадры - art/tickets/t435/cand/435b (папку 435 не трогает), лист - art/_review/tickets_2026-10-30/t435b_cand.png.
В МОД НИЧЕГО НЕ СТАВИТ.

    py -3 tools\gpuq.py add --name t435b --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t435b_gen.py render
    py -3.13 tools\hdart\t435b_gen.py prompts | build | sheet
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from PIL import Image                                  # noqa: E402

import t435_gen as t                                   # noqa: E402

g = t.g
REV = t.REV
VARIANT = "435b"
JOBS = {
    "stove15": dict(
        members=[("CITYFRNITURE", 15, (0, 0, 0))], seeds=[4395, 4396, 4397, 4398],
        # круг 1 (4391-94, подложка тёмная 58,60,70): тёмно-лавандовая столешница принята ключом за фон - полупрозрачна (R-089);
        # круг 2: тёплая песочная подложка, не родня ни голубому, ни лавандовому
        r1=[4391, 4392, 4393, 4394],
        panel=(200, 172, 120),
        what=("a squat cube-shaped kitchen stove cabinet in bright turquoise-cyan enamel: a lavender-grey counter top "
              "with a dark grey round cooking pot with a lid standing on a burner at the back left, and two small round "
              "burner rings with dark knobs at the front right; the left front face is light cyan with one small panel "
              "door with a pink-lilac knob near its right corner, the right front face is a plain darker cyan"),
        neg=("sink, faucet, tap, two doors, drawers, oven window, wooden cabinet, refrigerator, steam, flames, text, "
             "stone slab, paving tiles, diamond outline"), slab=False),
}
BEST = {"stove15": 4395}
FAMILY = [("COMFRN", 15), ("COMFRN2", 9), ("FRNITURE", 15), ("FRNITURE_WASTE", 15), ("VILFRNITURE", 14)]
BASE = ("CITYFRNITURE", 15)

g.JOBS = JOBS
SOFT_B = 16         # допуск ключа подложки: при 40 светлая лавандовая столешница (близка к серой подложке ответа 203) полупрозрачна


def cut_seed_b(job, seed):
    """Как g.cut_seed (cut_out + match_tone), но ключ мягче (SOFT_B) и тонкие остатки подложки - контур ромба, который модель
    нарисовала у основания (линия тоньше 5 пикселей x4) - срезаются раскрытием альфы 5x5. Модель всегда перерисовывает подложку
    в серый 185-230, какого бы цвета ни был вход, поэтому цвет подложки на входе тут ничего не решает."""
    import numpy as np
    from PIL import ImageFilter
    import probe_object as po
    J = JOBS[job]
    _comp, full, _at = g.comp_of(job)
    box = g.padded_box(full)
    frame = full.crop(box)
    hd = Image.open(os.path.join(g.GEN, job, "raw", "%d.png" % seed)).convert("RGB")
    part = po.match_tone(po.cut_out(hd, frame, g.GROW, SOFT_B, max_aspect=J.get("aspect", 1.3)), frame, g.TONE)
    a = part.split()[3]
    op = a.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))
    a = Image.fromarray(np.minimum(np.asarray(a), np.asarray(op)), "L")
    part.putalpha(a)
    cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
    cut.paste(part, (box[0] * 4, box[1] * 4))
    cut.save(os.path.join(g.GEN, job, "%d.png" % seed))


g.cut_seed = cut_seed_b
g.CLUSTERS = {VARIANT: ["stove15"]}
g.BEST = BEST


def do_build():
    shutil.rmtree(os.path.join(g.CAND, VARIANT), ignore_errors=True)
    new = {}
    for seed in g.all_seeds("stove15"):
        if os.path.exists(os.path.join(g.GEN, "stove15", "%d.png" % seed)):
            for k, im in g.pieces_of("stove15", seed).items():
                d = os.path.join(g.CAND, VARIANT, "_seeds")
                os.makedirs(d, exist_ok=True)
                im.save(os.path.join(d, "%s_%d_s%d.png" % (k[0], k[1], seed)))
    for k, im in g.pieces_of("stove15", BEST["stove15"]).items():
        new[k] = g.finish(VARIANT, k[0], k[1], im)
    for key in FAMILY:
        im, kind, q = t.recolor_any(new[BASE], BASE, key)
        if im is None:
            print("ПРОПУСК", key, q)
            continue
        new[key] = g.finish(VARIANT, key[0], key[1], im)
        print("435b %s <- %s: %s IoU %.2f" % (key, BASE, kind, q))
    for r in g.CHECK_ROWS:
        print("  ", r)
    return new


def do_sheet():
    import ticket_scene as ts
    from PIL import ImageDraw
    Z = 1.5
    cw, ch = int(128 * Z), int(160 * Z)
    gap, hdr = 6, 34

    def sc(im):
        return im.resize((int(im.width * Z), int(im.height * Z)), Image.LANCZOS)

    def row(title, items, n):
        r = Image.new("RGB", (n * (cw + gap) + gap, ch + hdr + 4), (12, 12, 14))
        for i, (lab, im) in enumerate(items):
            r.paste(ts.label(sc(im).convert("RGB"), lab, 15), (gap + i * (cw + gap), hdr))
        ImageDraw.Draw(r).text((8, 6), title, fill=(255, 255, 255), font=ts.font(20))
        return r

    k0 = BASE
    first = [("классика x4", g.on_dark(g.classic_of(*k0).resize((128, 160), Image.NEAREST))),
             ("HD сейчас", g.on_dark(g.hd_now(*k0)))]
    for s in JOBS["stove15"]["seeds"]:
        first.append(("зерно %d%s" % (s, " *" if s == BEST["stove15"] else ""),
                      g.on_dark(Image.open(os.path.join(g.GEN, "stove15", "%d.png" % s)).convert("RGBA"))))
    keys = [BASE] + FAMILY
    cur = [("%s:%d" % k, g.on_dark(g.hd_now(*k))) for k in keys]
    nw = [("%s:%d" % k, g.on_dark(Image.open(os.path.join(g.CAND, VARIANT, "%s_%d.png" % k)).convert("RGBA"))) for k in keys]
    rows = [row("CITYFRNITURE:15: классика | сейчас | зёрна (* - совет)", first, 6),
            row("шестёрка, HD сейчас", cur, 6), row("шестёрка, новое (зерно %d *)" % BEST["stove15"], nw, 6)]
    W = max(r.width for r in rows)
    out = Image.new("RGB", (W, sum(r.height for r in rows)), (12, 12, 14))
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height
    p = os.path.join(REV, "t435b_cand.png")
    out.save(p)
    print("лист:", p, out.size)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts", "build", "sheet"])
    a = ap.parse_args()
    if a.cmd == "prompts":
        tx, ng = g.build_prompt("stove15")
        print("PROMPT:", tx, "\nNEG:", ng)
    elif a.cmd == "render":
        g.do_render(["stove15"])
    elif a.cmd == "recut":
        g.recut(["stove15"])
    elif a.cmd == "build":
        do_build()
    else:
        do_sheet()
    return 0


if __name__ == "__main__":
    sys.exit(main())
