#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000300, «под эталон» (Vitali отверг A1-A4 как веер-фонтан): куст MOUNTGRASS:15 повторяет КЛАССИКУ -
низкая плотная бордово-бурая масса с колючими отростками во все стороны, растёт вширь, - но в HD-детализации.
Кандидаты - только art/tickets/t300r/gen (в мод ничего не ставится).

Вход модели - классика (x16 bicubic, как у v1; "B" - та же классика, сглаженная: шахматка пикселей убрана, остаётся
масса и цвет), промпт про плотный колючий кустарник с бордовой листвой БЕЗ веера, плетения и кучи хвороста.
Конвейер Qwen-Image-2.1 силы изменения не принимает (strength нет) - форму держат вход и слова "keep the silhouette".
Альфа - силуэт классики x4 (R-089), как у v1. Путь как t276_gen: strict, 40 шагов, cfg 4, cut_out grow 2 / soft 40, pad 3.
Мерка схожести (metrics): IoU силуэта с классикой x4 (альфа > 128) и средний цвет непрозрачной части (RGB и расстояние).

    py -3 tools\gpuq.py add --name xp300r --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t300r_gen.py render
    py -3.13 tools\hdart\t300r_gen.py metrics                      # числа по всем зёрнам, плюс v1 и A4
    py -3.13 tools\hdart\t300r_gen.py sheet 4101 4201 4301 4401    # art/_review/xp300/ref/sheet_300ref(.png, _flat.png)
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

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter       # noqa: E402

import t300a_gen as ta                              # noqa: E402

STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 2, 40, 3, 0.85
OUT = os.path.join(ROOT, "art", "tickets", "t300r")
GEN = os.path.join(OUT, "gen")
REV = os.path.join(ROOT, "art", "_review", "xp300", "ref")

WHAT_P1 = ("a dense low thorny shrub: one compact wide rounded mass of dark maroon-brown foliage and thorny twigs, "
           "much wider than tall, darkest deep inside, rusty orange-brown highlights on top, short sharp thorny "
           "spikes sticking out in all directions at the edges and a few at the bottom")
WHAT_P2 = ("a compact dark burgundy-brown thorny bramble bush: thick clumps of small dark red-brown leaves and "
           "prickly twigs packed into one low wide mound, black shadows deep inside, orange-brown lit tops, "
           "stiff short thorns radiating outward on all sides")
NEG = (", fan, fountain, stems rising from one point, weaving, wicker, basket, twig tangle, net, pile of sticks, "
       "haystack, tall tree, green leaves, flowers, stripes, maze pattern, spiral, rocks, wooden planks, fence, "
       "bright colors")

# (вход, описание, зерно)
SEEDS = [("A", "P1", 4101), ("A", "P1", 4102), ("B", "P1", 4201), ("B", "P1", 4202),
         ("A", "P2", 4301), ("A", "P2", 4302), ("B", "P2", 4401), ("B", "P2", 4402)]
WHATS = {"P1": WHAT_P1, "P2": WHAT_P2}


def smooth_input(src):
    """Классика x16 RGBA -> сглаженная: пиксельная шахматка стёрта, масса и цвет остались; альфа та же."""
    rgb = src.convert("RGB").filter(ImageFilter.GaussianBlur(ZOOM * 0.9))
    out = rgb.convert("RGBA")
    out.putalpha(src.split()[3])
    return out


def do_render():
    import map_mockup as mm   # noqa: F401
    import probe_object as po
    import battle_view as bv
    os.makedirs(os.path.join(GEN, "raw"), exist_ok=True)
    ns = argparse.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS,
                            qwen21_cfg=CFG, qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model",
                            qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    blk = bv.prompt_block("object")
    po.gen_fire.NEGATIVE = po.NEGATIVE + ", " + blk["negative"] + NEG
    args = argparse.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    cl = ta.classic_k1()
    box = ta.padded_box(cl)
    frame = cl.crop(box)                           # k=1, альфа - классика (R-089)
    panel = po.pick_background(frame)
    src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.NEAREST if False else Image.BICUBIC)
    inputs = {}
    for kind, im in (("A", src), ("B", smooth_input(src))):
        flat = Image.new("RGBA", im.size, tuple(panel) + (255,))
        flat.alpha_composite(im)
        inputs[kind] = flat
        flat.save(os.path.join(GEN, "raw", "input_%s.png" % kind))
    t0 = time.time()
    for n, (kind, wk, seed) in enumerate(SEEDS, 1):
        dst = os.path.join(GEN, "%d.png" % seed)
        if os.path.exists(dst):
            print("[%d/%d] зерно %d уже есть" % (n, len(SEEDS), seed), flush=True)
            continue
        prompt = po.STYLE["strict"].replace("{what}", WHATS[wk]) + " " + blk["positive"]
        hd = po.gen_fire.run_pass(painter, args, prompt, inputs[kind].convert("RGB"), seed)
        po.gen_hd.save_png(hd, os.path.join(GEN, "raw", "%d.png" % seed))
        part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT), frame, TONE)
        cut = Image.new("RGBA", (32 * 4, 40 * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        po.gen_hd.save_png(cut, dst)
        print("[%d/%d] вход %s описание %s зерно %d готово, %.0f с" % (n, len(SEEDS), kind, wk, seed, time.time() - t0),
              flush=True)


# --- мерка схожести -------------------------------------------------------------------------------------------
def classic_mask4(cl):
    return np.asarray(cl.split()[3].resize((128, 160), Image.NEAREST)) > 0


def metrics_of(im, mask_c, col_c):
    a = np.asarray(im.convert("RGBA").resize((128, 160), Image.LANCZOS) if im.size != (128, 160) else im.convert("RGBA"))
    m = a[..., 3] > 128
    inter, uni = (m & mask_c).sum(), (m | mask_c).sum()
    iou = inter / max(1, uni)
    col = a[..., :3][m].mean(0) if m.any() else np.zeros(3)
    dist = float(np.sqrt(((col - col_c) ** 2).sum()))
    return iou, col, dist, m.sum() / max(1, mask_c.sum())


def classic_rgba4(sc):
    return sc.classic("MOUNTGRASS", 15)


def do_metrics(seeds=None, quiet=False):
    import ticket_scene as ts
    sc = ts.Scene()
    cl4 = classic_rgba4(sc)
    mask_c = classic_mask4(cl4)
    a = np.asarray(cl4)
    col_c = a[..., :3][a[..., 3] > 128].mean(0)
    rows = [("классика", col_c, 1.0, 0.0, 1.0)]
    items = [("v1 нынешний HD", sc.hd("MOUNTGRASS", 15))]
    p = os.path.join(ROOT, "art", "tickets", "t300a", "gen", "3401.png")
    if os.path.exists(p):
        items.append(("A4 (3401, отвергнут)", Image.open(p).convert("RGBA")))
    seeds = seeds or [s for _k, _w, s in SEEDS if os.path.exists(os.path.join(GEN, "%d.png" % s))]
    for s in seeds:
        items.append(("зерно %d" % s, Image.open(os.path.join(GEN, "%d.png" % s)).convert("RGBA")))
    res = {}
    for name, im in items:
        iou, col, dist, area = metrics_of(im, mask_c, col_c)
        rows.append((name, col, iou, dist, area))
        res[name] = (iou, dist, area, col)
    if not quiet:
        print("%-24s %-16s %6s %7s %6s" % ("кадр", "средний RGB", "IoU", "dRGB", "площадь"))
        for name, col, iou, dist, area in rows:
            print("%-24s %3d %3d %3d       %6.3f %7.1f %6.2f" % (name, col[0], col[1], col[2], iou, dist, area))
    return res


def do_sheet(seeds):
    import ticket_scene as ts
    TERRAIN, BLOCK, CENTER, W, H, K = "WESTOWN_GRASS", "PLAINS12", (440, 262), 170, 120, 4
    sc = ts.Scene()
    os.makedirs(REV, exist_ok=True)
    met = do_metrics([int(s) for s in seeds], quiet=True)
    cx, cy = CENTER
    box = ((cx - W // 2) * K, (cy - H // 2) * K, (cx + W // 2) * K, (cy + H // 2) * K)
    cands = []
    for i, s in enumerate(seeds, 1):
        m = met["зерно %d" % s]
        cands.append(("R%d (зерно %d)  IoU %.2f  dRGB %.0f" % (i, s, m[0], m[1]),
                      Image.open(os.path.join(GEN, "%d.png" % s)).convert("RGBA")))
    mv = met["v1 нынешний HD"]
    panels = [("классика", "classic", None), ("v1 нынешний HD  IoU %.2f  dRGB %.0f" % (mv[0], mv[1]), "hd", None)]
    panels += [(t, "hd", {("MOUNTGRASS", 15): im}) for t, im in cands]
    ims = []
    for title, mode, ov in panels:
        im, _ = sc.render(TERRAIN, BLOCK, mode, override=ov, k=K)
        c = im.crop(box).convert("RGB")
        ims.append((title, c.resize((c.width * 3 // 4, c.height * 3 // 4), Image.LANCZOS)))
    pw, ph = ims[0][1].size
    cols = 3
    rows = (len(ims) + cols - 1) // cols
    top = Image.new("RGB", (cols * (pw + 8) + 8, rows * (ph + 30) + 40), (12, 12, 14))
    d = ImageDraw.Draw(top)
    d.text((8, 8), "XP-000300 куст MOUNTGRASS:15 - под эталон: масса и силуэт классики, HD-детализация (%s %s, k=4)"
           % (TERRAIN, BLOCK), fill=(140, 200, 255), font=ta.font(18))
    for i, (t, c) in enumerate(ims):
        x, y = 8 + (i % cols) * (pw + 8), 40 + (i // cols) * (ph + 30)
        d.text((x, y), t, fill=(255, 220, 0), font=ta.font(16))
        top.paste(c, (x, y + 24))
    p = os.path.join(REV, "sheet_300ref.png")
    top.save(p)
    print("лист:", p, top.size)

    cl = sc.classic("MOUNTGRASS", 15)
    v1 = sc.hd("MOUNTGRASS", 15)
    flats = [("классика", cl), ("v1 нынешний HD", v1)] + cands
    fw, fh = 256, 320
    mk = np.asarray(cl.split()[3]) > 0
    edge = mk & ~(np.roll(mk, 4, 0) & np.roll(mk, -4, 0) & np.roll(mk, 4, 1) & np.roll(mk, -4, 1))
    ncol = 3
    nrow = (len(flats) + ncol - 1) // ncol
    sheet = Image.new("RGB", (ncol * (fw + 8) + 8, nrow * (fh + 28) + 8), (12, 12, 14))
    d = ImageDraw.Draw(sheet)
    for i, (t, im) in enumerate(flats):
        x, y = 8 + (i % ncol) * (fw + 8), 8 + (i // ncol) * (fh + 28)
        bg = Image.new("RGBA", (128, 160), (110, 110, 116, 255))
        bg.alpha_composite(im.convert("RGBA"))
        big = bg.resize((fw, fh), Image.LANCZOS).convert("RGB")
        dd = ImageDraw.Draw(big)
        dd.polygon([(fw // 2, 24 * 8), (fw, 32 * 8), (fw // 2, 40 * 8 - 2), (0, 32 * 8)], outline=(255, 220, 0))
        ys, xs = np.nonzero(edge)
        for yy, xx in zip(ys, xs):
            dd.point((xx * 2, yy * 2), fill=(0, 220, 255))
        sheet.paste(big, (x, y + 24))
        d.text((x, y), t, fill=(255, 220, 0), font=ta.font(14))
    p2 = os.path.join(REV, "sheet_300ref_flat.png")
    sheet.save(p2)
    print("лист:", p2, sheet.size)
    do_metrics([int(s) for s in seeds])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "metrics", "sheet"])
    ap.add_argument("seeds", nargs="*", type=int)
    a = ap.parse_args()
    if a.cmd == "render":
        do_render()
    elif a.cmd == "metrics":
        do_metrics(a.seeds or None)
    else:
        do_sheet(a.seeds or [4101, 4201, 4301, 4401])
    return 0


if __name__ == "__main__":
    sys.exit(main())
