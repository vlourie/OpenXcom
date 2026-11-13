#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты 248, 253, 264 (23.10, выбор Vitali «перегенерировать моделью»): перерисовка кадров Qwen-2.1 strict, варианты на выбор.
Ничего в мод не ставит: кадры - в art/tickets/<задание>/gen/series/<НАБОР>.PCK/<кадр>_<зерно>.png (128x160, альфа),
листы - art/_review/tickets_2026-10-23/gen_XP-000NNN.png. Арт подключается только после выбора Vitali.

Путь - ровно strict_ctl_v1.do_render (obj_series.paint): STYLE["strict"], NEGATIVE probe_object, подложка pick_background,
bicubic x16, Qwen-Image-2.1 40 шагов, cfg 4, 1 Мп, cut_out grow 2 / soft 40, match_tone 0.7, pad 3 (как t249_box_gen.py).
Блок ракурса и света - battle_view.prompt_block("object"), не своими словами; негатив ракурса дописан к NEGATIVE.
Описание - по пикселям классики (R-456, R-221): назван только тот материал и узор, что читается на кадре.
Один процесс - одно задание (4 зерна на кадр; R-215: много рендеров за процесс не копим).

Задания: t264 (ящик CONTAINERS:2), t248 (бак URBAN_WASTE:98), t253_75 ... t253_79 (тележка PORTROADS:75-79).
t249 (ящик URBAN_WASTE:91/92) рисует свой скрипт t249_box_gen.py (render), здесь только лист (зеркало 91 -> 92 по маске классики 92).

    py -3 tools\gpuq.py add --name t264-crate --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t_regen_obj.py render t264
    py -3.13 tools\hdart\t_regen_obj.py sheet t264        # лист gen_XP-000264.png (без видеокарты)
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

STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 2, 40, 3, 0.7
REVIEW = os.path.join(ROOT, "art", "_review", "tickets_2026-10-23")

CART = ("a part of a dark steel mine cart (an ore trolley made of angular sheet steel, matte charcoal-black and dark grey "
        "steel with thin lighter metal edges, standing on a single thin rail): ")
SEEDS_CART = [25301, 25302, 25303, 25304]
JOBS = {
    "t264": dict(ticket="XP-000264", set="CONTAINERS", frames=[2], seeds=[26401, 26402, 26403, 26404],
                 what=("a cube-shaped open-slat wooden crate, a lattice cage of near-black charred wooden battens with wide gaps; "
                       "a warm orange-amber glow lights the inside of the crate and shows through the gaps between the battens; "
                       "no lid, no label, no rope"),
                 scene=("WESTOWN_WASTE", "WESTOWN_13")),
    "t264v2": dict(ticket="XP-000264_v2", set="CONTAINERS", frames=[2], seeds=[26411, 26412, 26413, 26414],
                   what=("an old wooden crate built of horizontal planks, light warm golden-brown wood with visible grain, bright tan and orange-brown highlights on the top and the left face, narrow dark gaps between the planks, a cube with the proportions of a standard crate, plain dry wood"),
                   neg="glow, light inside, lantern, metal cage, iron, grid, black frame, charred wood, fire, embers",
                   scene=("WESTOWN_WASTE", "WESTOWN_13")),
    "t264v3": dict(ticket="XP-000264_v3", set="CONTAINERS", frames=[2], seeds=[26421, 26422, 26423, 26424],
                   what=("an old worn wooden crate built of horizontal planks, warm golden-brown wood with visible grain, WIDE DARK gaps between the planks, dark stains and wear on all faces, scuffed and weathered; thin iron strapping, narrow flat metal bands along the edges and corners of the cube; a cube with the proportions of a standard crate"),
                   neg="glow, light inside, lantern, cage, grid, fire, embers, charred wood",
                   scene=("WESTOWN_WASTE", "WESTOWN_13")),
    "t248": dict(ticket="XP-000248", set="URBAN_WASTE", frames=[98], seeds=[24801, 24802, 24803, 24804],
                 what=("an old rusty metal trash bin with a rounded dome-shaped top: dark charcoal-grey and rusty brown-red "
                       "battered metal, scuffed and dented, a dark rectangular opening in the lower right of its front, "
                       "short feet at the bottom, no lid handle, no trash spilling out"),
                 scene=("URBAN_WASTE", "URBANWASTE03")),
    "t253_75": dict(ticket="XP-000253", set="PORTROADS", frames=[75], seeds=SEEDS_CART,
                    what=(CART + "the front end of the cart, an angular dark steel body, a round steel wheel with a hub at the "
                          "lower right, and at the left an opening with a yellow-and-black hazard-striped grating")),
    "t253_76": dict(ticket="XP-000253", set="PORTROADS", frames=[76], seeds=SEEDS_CART,
                    what=(CART + "a low flat sloping dark steel plate, the lower floor part of the cart, with a lighter metal "
                          "edge along the top, no wheel, no stripes")),
    "t253_77": dict(ticket="XP-000253", set="PORTROADS", frames=[77], seeds=SEEDS_CART,
                    what=(CART + "one large slanted dark steel side panel of the cart with a light metal rim, the edge of a "
                          "wheel peeking out at the bottom right, no stripes")),
    "t253_78": dict(ticket="XP-000253", set="PORTROADS", frames=[78], seeds=SEEDS_CART,
                    what=(CART + "the other end of the cart, an angular dark steel body with a round steel wheel with a hub at "
                          "the lower left and a yellow-and-black hazard-striped grating in an opening")),
    "t253_79": dict(ticket="XP-000253", set="PORTROADS", frames=[79], seeds=SEEDS_CART,
                    what=(CART + "a tall flat dark steel panel standing upright, the back wall of the cart, with a flat low "
                          "dark steel base plate at the bottom right, no wheel, no stripes")),
}


def out_dir(job):
    return os.path.join(ROOT, "art", "tickets", job, "gen")


def do_render(job):
    import map_mockup as mm
    import probe_object as po
    import battle_view as bv
    j = JOBS[job]
    od = out_dir(job)
    sd = os.path.join(od, "series", j["set"] + ".PCK")
    os.makedirs(os.path.join(od, "raw"), exist_ok=True)
    os.makedirs(sd, exist_ok=True)
    w = mm.World()
    ns = argparse.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS,
                            qwen21_cfg=CFG, qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model",
                            qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    blk = bv.prompt_block("object")
    po.gen_fire.NEGATIVE = po.NEGATIVE + ", " + blk["negative"] + (", " + j["neg"] if j.get("neg") else "")
    args = argparse.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    prompt = po.STYLE["strict"].replace("{what}", j["what"]) + " " + blk["positive"]
    t0 = time.time()
    n = 0
    total = len(j["frames"]) * len(j["seeds"])
    for fr in j["frames"]:
        full = w.sprite(j["set"].lower(), fr, None).convert("RGBA")
        bb = full.split()[3].getbbox()
        box = (max(0, bb[0] - PAD), max(0, bb[1] - PAD), min(full.width, bb[2] + PAD), min(full.height, bb[3] + PAD))
        frame = full.crop(box)
        panel = po.pick_background(frame)
        src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        for seed in j["seeds"]:
            dst = os.path.join(sd, "%d_%d.png" % (fr, seed))
            n += 1
            if os.path.exists(dst):
                print("[%d/%d] %d зерно %d уже есть" % (n, total, fr, seed), flush=True)
                continue
            hd = po.gen_fire.run_pass(painter, args, prompt, flat.convert("RGB"), seed)
            po.gen_hd.save_png(hd, os.path.join(od, "raw", "%d_%d.png" % (fr, seed)))
            part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT), frame, TONE)
            cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
            cut.paste(part, (box[0] * 4, box[1] * 4))
            po.gen_hd.save_png(cut, dst)
            print("[%d/%d] кадр %d зерно %d готово, %.0f с" % (n, total, fr, seed, time.time() - t0), flush=True)


# ----------------------------------------------------------------------------------------------- листы
def font(n=20):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", n)
    except OSError:
        return ImageFont.load_default()


DARK, GREY, LIGHT = (24, 20, 18), (110, 110, 116), (222, 222, 226)


def on(im, bg, box, k):
    c = im.crop(box)
    c = c.resize((int(c.width * k), int(c.height * k)), Image.LANCZOS)
    out = Image.new("RGBA", c.size, bg + (255,))
    out.alpha_composite(c)
    return out


def mirror_to(cut, classic92):
    """Зеркало кадра 91 -> 92: цвет зеркалится, альфа - мягкая маска классики 92; за кромкой зеркала цвет дотянут от ближних."""
    import numpy as np
    from scipy import ndimage as ndi
    import probe_object as po
    m = cut.transpose(Image.FLIP_LEFT_RIGHT)
    a = np.asarray(m, np.float32)
    own = a[..., 3] > 100
    idx = ndi.distance_transform_edt(~own, return_distances=False, return_indices=True)
    rgb = a[..., :3][idx[0], idx[1]]
    mask = classic92.resize((32, 40), Image.NEAREST).split()[3].point(lambda v: 255 if v else 0)
    al = np.asarray(po.smooth_silhouette(mask, 4), np.float32)
    return Image.fromarray(np.clip(np.dstack([rgb, al]), 0, 255).astype(np.uint8), "RGBA")


def cands(job):
    j = JOBS[job]
    res = {}
    for fr in j["frames"]:
        res[fr] = []
        for s in j["seeds"]:
            p = os.path.join(out_dir(job), "series", j["set"] + ".PCK", "%d_%d.png" % (fr, s))
            if os.path.exists(p):
                res[fr].append((s, Image.open(p).convert("RGBA")))
    return res


def cell_of(im, box, zb, zs):
    big, dk, lt = on(im, GREY, box, zb), on(im, DARK, box, zs), on(im, LIGHT, box, zs)
    cell = Image.new("RGB", (big.width, big.height + dk.height + 4), (12, 12, 14))
    cell.paste(big.convert("RGB"), (0, 0))
    cell.paste(dk.convert("RGB"), (0, big.height + 4))
    cell.paste(lt.convert("RGB"), (dk.width, big.height + 4))
    return cell


def compose(rows):
    f = font(20)
    ch = max(c.height for r in rows for _t, c in r)
    cw = max(c.width for r in rows for _t, c in r)
    ncol = max(len(r) for r in rows)
    out = Image.new("RGB", (ncol * (cw + 8) + 8, len(rows) * (ch + 34) + 8), (12, 12, 14))
    d = ImageDraw.Draw(out)
    for y, r in enumerate(rows):
        for x, (t, c) in enumerate(r):
            ox, oy = 8 + x * (cw + 8), 8 + y * (ch + 34)
            d.text((ox, oy), t, fill=(255, 220, 0), font=f)
            out.paste(c, (ox, oy + 28))
    return out


def grid(panels, cols=3):
    f = font(20)
    pw, ph = panels[0][1].width, panels[0][1].height
    nr = (len(panels) + cols - 1) // cols
    g = Image.new("RGB", (cols * (pw + 8) + 8, nr * (ph + 34) + 8), (12, 12, 14))
    d = ImageDraw.Draw(g)
    for i, (t, p) in enumerate(panels):
        ox, oy = 8 + (i % cols) * (pw + 8), 8 + (i // cols) * (ph + 34)
        d.text((ox, oy), t, fill=(255, 220, 0), font=f)
        g.paste(p.convert("RGB"), (ox, oy + 28))
    return g


def stack(a, b, path):
    W = max(a.width, b.width)
    out = Image.new("RGB", (W, a.height + b.height), (12, 12, 14))
    out.paste(a, (0, 0))
    out.paste(b, (0, a.height))
    os.makedirs(REVIEW, exist_ok=True)
    out.save(path)
    print("лист:", path, out.size)


def rows_for(sc, setname, frames, cand, zb, zs, tag=False):
    rows = []
    for fr in frames:
        cl, cu = sc.classic(setname, fr), sc.hd(setname, fr)
        bb = cl.split()[3].getbbox()
        box = (max(0, bb[0] - 6), max(0, bb[1] - 6), min(128, bb[2] + 6), min(160, bb[3] + 6))
        cells = [("классика", cl), ("сейчас", cu)] + [("вар. %d (зерно %d)" % (i + 1, s), im) for i, (s, im) in enumerate(cand[fr])]
        rows.append([("%s %d" % (t, fr) if tag else t, cell_of(im, box, zb, zs)) for t, im in cells])
    return rows


def scene_panels(sc, terrain, block, setname, frames, cand, w=200, h=120, k=4):
    import ticket_scene as ts
    keys = [(setname, f) for f in frames]
    found = ts.find_cells(sc, terrain, block, keys)
    if not found:
        print("в блоке %s нет кадров %s" % (block, keys))
        return []
    found = [(f[0], f[1], tuple(v * k for v in f[2]), f[3], f[4]) for f in found]    # find_cells считает при k=1
    box = ts.window(found, w, h, k)
    out = []
    im, _ = sc.render(terrain, block, "classic", k=k)
    out.append(("сцена: классика", ts.crop_pad(im, box)))
    im, _ = sc.render(terrain, block, "hd", k=k)
    out.append(("сцена: HD сейчас", ts.crop_pad(im, box)))
    nvar = max(len(v) for v in cand.values()) if cand else 0
    for i in range(nvar):
        ov = {(setname, f): cand[f][i][1] for f in frames if i < len(cand[f])}
        im, _ = sc.render(terrain, block, "hd", override=ov, k=k)
        out.append(("сцена: вар. %d" % (i + 1), ts.crop_pad(im, box)))
    return out


def do_sheet(job):
    import ticket_scene as ts
    sc = ts.Scene()
    if job == "t249":
        return sheet_t249(sc)
    j = JOBS[job]
    tk = j["ticket"]
    cand, frames = {}, []
    for g in JOBS:
        if JOBS[g]["ticket"] == tk:
            cand.update(cands(g))
            frames += JOBS[g]["frames"]
    setname = j["set"]
    zb, zs = (3.0, 1.5) if len(frames) == 1 else (2.0, 1.0)
    top = compose(rows_for(sc, setname, frames, cand, zb, zs, tag=len(frames) > 1))
    terrain, block = j.get("scene", ("PORTUFO", "PORTUFO20"))
    sp = scene_panels(sc, terrain, block, setname, frames, cand)
    stack(top, grid(sp), os.path.join(REVIEW, "gen_%s.png" % tk))


def sheet_t249(sc):
    import t249_box as tb
    set_ = "URBAN_WASTE"
    seeds = [24901, 24902, 24903, 24904]
    dd = os.path.join(ROOT, "art", "tickets", "t249", "gen_box", "series", set_ + ".PCK")
    c91, c92 = [], []
    for s in seeds:
        p = os.path.join(dd, "91_%d.png" % s)
        if os.path.exists(p):
            im = Image.open(p).convert("RGBA")
            c91.append((s, im))
            c92.append((s, mirror_to(im, sc.classic(set_, 92))))
    out92 = os.path.join(ROOT, "art", "tickets", "t249", "gen_box", "series92")
    os.makedirs(out92, exist_ok=True)
    for s, im in c92:
        im.save(os.path.join(out92, "92_%d.png" % s))
    rows = []
    for fr, cd in ((91, c91), (92, c92)):
        cl, cu = sc.classic(set_, fr), sc.hd(set_, fr)
        bb = cl.split()[3].getbbox()
        box = (max(0, bb[0] - 6), max(0, bb[1] - 6), min(128, bb[2] + 6), min(160, bb[3] + 6))
        cells = [("классика %d" % fr, cl), ("сейчас %d" % fr, cu)] + [("вар. %d (зерно %d)" % (i + 1, s), im) for i, (s, im) in enumerate(cd)]
        rows.append([(t, cell_of(im, box, 3.0, 1.5)) for t, im in cells])
    top = compose(rows)
    a, box = tb.scene_overlay(sc, [sc.classic(set_, 91), sc.classic(set_, 92)])
    b, _ = tb.scene_overlay(sc, [sc.hd(set_, 91), sc.hd(set_, 92)])
    sp = [("сцена: классика", ts_crop(a, box)), ("сцена: HD сейчас", ts_crop(b, box))]
    for i in range(len(c91)):
        n, _ = tb.scene_overlay(sc, [c91[i][1], c92[i][1]])
        sp.append(("сцена: вар. %d" % (i + 1), ts_crop(n, box)))
    stack(top, grid(sp), os.path.join(REVIEW, "gen_XP-000249.png"))


def ts_crop(im, box):
    import ticket_scene as ts
    return ts.crop_pad(im, box)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "sheet"])
    ap.add_argument("job", choices=list(JOBS) + ["t249"])
    a = ap.parse_args()
    if a.cmd == "render":
        if a.job == "t249":
            raise SystemExit("t249 рисует t249_box_gen.py render")
        do_render(a.job)
    else:
        do_sheet(a.job)
    return 0


if __name__ == "__main__":
    sys.exit(main())
