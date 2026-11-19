#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000300, вариант A Vitali (26.10): колючий куст MOUNTGRASS:15 «растёт вверх» В СТАРОЙ МАСКЕ кадра.
Кандидаты - только art/tickets/t300a/gen (в мод ничего не ставится, подключение после выбора Vitali).

Отличия от вариантов раньше:
  - t276_gen bush15 (v1, куча): вход - апскейл классики, что нарисовано - «heap of dead brushwood» (R-480);
  - t300_gen (вариант B): новая маска, новый силуэт. Здесь маски НЕТ новой: альфа - силуэт классики x4 (R-089,
    cut_out grow 2 / soft 40, как у v1), габарит 32x25 и поведение у соседей прежние.
Что нарисовано - стебли из одного корня веером вверх и в стороны, темнее у основания, светлые кончики, просветы;
негатив «pile, heap, flat mat, nest, tangle». Ракурс и свет - battle_view.prompt_block("object").
Вход модели - эскиз стеблей, обрезанный по маске классики (+1 px): рост вверх не помещается в апскейл плоской
классики (вариант «C»-вход - апскейл классики, но с новым промптом - для сравнения). Путь - как t276_gen.do_render:
STYLE["strict"], NEGATIVE probe_object, Qwen-Image-2.1 40 шагов, cfg 4, 1 Мп, bicubic x16, match_tone 0.7, pad 3.
Контактную тень не добавляем (она вышла бы за маску классики).

    tools\hdart\.venv\Scripts\python.exe tools\hdart\t300a_gen.py preview
    py -3 tools\gpuq.py add --name xp300a -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t300a_gen.py render
    py -3.13 tools\hdart\t300a_gen.py sheet 3101 3201 3301 3401      # лист art/_review/xp300/a/sheet_300a.png
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

STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 2, 40, 3, 0.7
OUT = os.path.join(ROOT, "art", "tickets", "t300a")
GEN = os.path.join(OUT, "gen")
REV = os.path.join(ROOT, "art", "_review", "xp300", "a")

# (вход, зерно): F7 - веер 7 стеблей, F5 - 5 стеблей реже, F9 - 9 стеблей гуще, C - апскейл классики
SEEDS = [("F7", 3101), ("F7", 3102), ("F5", 3201), ("F5", 3202), ("F9", 3301), ("F9", 3302),
         ("C", 3401), ("C", 3402)]

WHAT = ("a dry thorny bush growing upward: several woody stems rising from one root point at the bottom centre, "
        "fanning up and sideways into thin thorny branches in rusty orange-brown and dark maroon, dense and darkest "
        "near the base, lighter orange twig tips at the top, black gaps and depth between the branches, "
        "wider than it is tall")
NEG = (", green leaves, flowers, stripes, maze pattern, spiral, rocks, wooden planks, fence, net, bright colors, "
       "pile, heap, flat mat, nest, tangle, haystack")

DARK, MID, RUST, TIP = (40, 14, 10), (92, 32, 16), (158, 66, 24), (232, 134, 48)
ROOT_PT = (16.0, 35.0)       # корень, k=1 (кадр 32x40; классика занимает строки 11..36)
FANS = {
    "F7": dict(tips=[(2, 20), (6, 13), (11, 11), (16, 11), (21, 11), (26, 13), (30, 20)],
               bends=[-4, -3, -2, 0.5, 2, 3, 4], sides=(0.45, 0.65)),
    "F5": dict(tips=[(4, 18), (10, 11), (16, 11), (22, 11), (28, 18)],
               bends=[-4, -2, 0.5, 2, 4], sides=(0.5, 0.7)),
    "F9": dict(tips=[(1, 24), (4, 16), (8, 12), (12, 11), (16, 11), (20, 11), (24, 12), (28, 16), (31, 24)],
               bends=[-4, -3.5, -2.5, -1, 0.5, 1.5, 2.5, 3.5, 4], sides=(0.4, 0.58, 0.75)),
}


def lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def classic_k1():
    """Классика MOUNTGRASS:15, k=1 RGBA 32x40 (как у t276_gen.classic_stack)."""
    import map_mockup as mm
    w = mm.World()
    return w.sprite("mountgrass", 15, None).convert("RGBA")


def sketch(kind, classic):
    """Эскиз x16 (512x640) RGBA: стебли из одного корня, тёмные внизу, светлее к кончикам; обрезан по маске классики."""
    Z = ZOOM
    big = Image.new("RGBA", (32 * Z, 40 * Z), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    fan = FANS[kind]
    rx, ry = ROOT_PT
    n = 18
    for (tx, ty), b in zip(fan["tips"], fan["bends"]):
        p0 = (rx + (tx - 16) * 0.12, ry)
        pts = []
        for i in range(n + 1):
            t = i / n
            x = p0[0] + (tx - p0[0]) * t + b * np.sin(np.pi * t)
            y = p0[1] + (ty - p0[1]) * t
            pts.append((x * Z, y * Z))
        for i in range(n):
            t = i / n
            wd = max(2, int(round((1.5 - 1.1 * t) * Z * 0.5)))
            col = lerp(DARK, TIP, (t - 0.1) ** 1.3 / 0.85 ** 1.3) if t > 0.1 else DARK
            d.line([pts[i], pts[i + 1]], fill=col + (255,), width=wd)
        for s in fan["sides"]:
            k = int(s * n)
            x, y = pts[k]
            dx = 5 * Z if tx >= 16 else -5 * Z
            c1 = lerp(RUST, TIP, s)
            c2 = lerp(MID, RUST, s)
            d.line([(x, y), (x + dx * 0.9, y - 4.2 * Z)], fill=c1 + (255,), width=max(2, Z // 6))
            d.line([(x, y), (x - dx * 0.5, y - 3.2 * Z)], fill=c2 + (255,), width=max(2, Z // 7))
    big = big.filter(ImageFilter.GaussianBlur(0.8))
    m = classic.split()[3].point(lambda v: 255 if v else 0).filter(ImageFilter.MaxFilter(3))
    m = m.resize(big.size, Image.NEAREST)
    a = np.minimum(np.asarray(big.split()[3]), np.asarray(m))
    out = np.asarray(big).copy()
    out[..., 3] = a
    return Image.fromarray(out, "RGBA")


def padded_box(img, pad=PAD):
    bb = img.split()[3].getbbox()
    return (max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad))


def do_preview():
    cl = classic_k1()
    os.makedirs(OUT, exist_ok=True)
    tiles = []
    for kind in ("F7", "F5", "F9"):
        sk = sketch(kind, cl)
        bg = Image.new("RGBA", sk.size, (110, 110, 116, 255))
        bg.alpha_composite(sk)
        tiles.append(bg.resize((256, 320), Image.LANCZOS).convert("RGB"))
    sheet = Image.new("RGB", (3 * 260, 320), (20, 20, 24))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * 260, 0))
    p = os.path.join(OUT, "preview_sketch.png")
    sheet.save(p)
    print("эскизы:", p, "bbox классики", cl.split()[3].getbbox())


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
    prompt = po.STYLE["strict"].replace("{what}", WHAT) + " " + blk["positive"]
    cl = classic_k1()
    box = padded_box(cl)
    frame = cl.crop(box)                           # k=1, альфа - классика (R-089)
    panel = po.pick_background(frame)
    src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
    flat_c = Image.new("RGBA", src.size, tuple(panel) + (255,))
    flat_c.alpha_composite(src)
    t0 = time.time()
    for n, (kind, seed) in enumerate(SEEDS, 1):
        dst = os.path.join(GEN, "%d.png" % seed)
        if os.path.exists(dst):
            print("[%d/%d] зерно %d уже есть" % (n, len(SEEDS), seed), flush=True)
            continue
        if kind == "C":
            flat = flat_c
        else:
            sk = sketch(kind, cl).crop((box[0] * ZOOM, box[1] * ZOOM, box[2] * ZOOM, box[3] * ZOOM))
            flat = Image.new("RGBA", sk.size, tuple(panel) + (255,))
            flat.alpha_composite(sk)
        raw_in = os.path.join(GEN, "raw", "input_%s.png" % kind)
        if not os.path.exists(raw_in):
            flat.save(raw_in)
        hd = po.gen_fire.run_pass(painter, args, prompt, flat.convert("RGB"), seed)
        po.gen_hd.save_png(hd, os.path.join(GEN, "raw", "%d.png" % seed))
        part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT), frame, TONE)
        cut = Image.new("RGBA", (32 * 4, 40 * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        po.gen_hd.save_png(cut, dst)
        print("[%d/%d] вход %s зерно %d готово, %.0f с" % (n, len(SEEDS), kind, seed, time.time() - t0), flush=True)


def font(n=16):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", n)
    except OSError:
        return ImageFont.load_default()


def do_sheet(seeds):
    import ticket_scene as ts
    TERRAIN, BLOCK, CENTER, W, H, K = "WESTOWN_GRASS", "PLAINS12", (440, 262), 170, 120, 4
    sc = ts.Scene()
    os.makedirs(REV, exist_ok=True)
    cx, cy = CENTER
    box = ((cx - W // 2) * K, (cy - H // 2) * K, (cx + W // 2) * K, (cy + H // 2) * K)
    cands = []
    for i, s in enumerate(seeds, 1):
        cands.append(("A%d (зерно %d)" % (i, s), Image.open(os.path.join(GEN, "%d.png" % s)).convert("RGBA")))
    panels = [("классика", "classic", None), ("нынешний HD (v1)", "hd", None)]
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
    d.text((8, 8), "XP-000300 куст MOUNTGRASS:15 - вариант A: растёт вверх, СТАРАЯ маска классики (%s %s, k=4)"
           % (TERRAIN, BLOCK), fill=(140, 200, 255), font=font(18))
    for i, (t, c) in enumerate(ims):
        x, y = 8 + (i % cols) * (pw + 8), 40 + (i // cols) * (ph + 30)
        d.text((x, y), t, fill=(255, 220, 0), font=font(16))
        top.paste(c, (x, y + 24))
    p = os.path.join(REV, "sheet_300a.png")
    top.save(p)
    print("лист:", p, top.size)

    # плоско: каждый на сером с ромбом и контуром маски классики
    cl = sc.classic("MOUNTGRASS", 15)
    v1 = sc.hd("MOUNTGRASS", 15)
    flats = [("классика", cl), ("нынешний HD", v1)] + cands
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
        d.text((x, y), t, fill=(255, 220, 0), font=font(16))
    p2 = os.path.join(REV, "sheet_300a_flat.png")
    sheet.save(p2)
    print("лист:", p2, sheet.size)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["preview", "render", "sheet"])
    ap.add_argument("seeds", nargs="*", type=int)
    a = ap.parse_args()
    if a.cmd == "preview":
        do_preview()
    elif a.cmd == "render":
        do_render()
    else:
        do_sheet(a.seeds or [3101, 3201, 3301, 3401])
    return 0


if __name__ == "__main__":
    sys.exit(main())
