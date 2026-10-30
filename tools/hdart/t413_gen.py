#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000413 (валуны со мхом FORESTSWAMPBITS мыльные), вариант C, ПИЛОТ (Vitali 30.10): кандидаты на пять кадров
FORESTSWAMPBITS 4, 5, 6, 7, 9 в стиле одобренного FORESTSWAMPBITS:3 (qwen21_strict, 28.09: «two large pale grey boulders
overgrown with dark green moss and vines»). В МОД НИЧЕГО НЕ СТАВИТ: заготовки - art/tickets/t413/cand/<вариант>/
FORESTSWAMPBITS_<кадр>.png (RGBA 128x160), листы - art/_review/tickets_2026-10-30/t413_cand.png и t413_scene.png.
Одобренный :3 и блоки 10-14 не трогаются; остальная семья (41 кадр) - после одобрения пилота.

Путь - как t405_409_gen: Qwen-Image-2.1 strict, 40 шагов, cfg 4, 1 Мп, вход - классика bicubic x16 на подложке
pick_background, NEGATIVE probe_object + негатив battle_view, cut_out (R-089: альфа - силуэт классики x4, сглаженный
xBRZ, а не фон ответа), match_tone 0.7. Ракурс и свет - ТОЛЬКО battle_view (view_sentence / light_sentence). relief_object
на валунах запрещён (R-390). Пилот отличается от 405/409 постобработкой кромки (post_edge): альфа по краю сжата в
~1 пиксель x4 (у HD сейчас 8-12% полупрозрачных - часть «мыла»), контур гладкий (силуэт xBRZ, не лесенка 4x4),
вне силуэта классики x4 альфа 0, дыры внутри тела заливаются (fix_holes). Три зерна на кадр, лучшее - BEST после листа.

    py -3 tools\gpuq.py add --name t413-rocks --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t413_gen.py render --frames 4
    py -3.13 tools\hdart\t413_gen.py recut      # перевырезка из raw (без видеокарты)
    py -3.13 tools\hdart\t413_gen.py build      # кандидаты по BEST + лист t413_cand.png + проверки
    py -3.13 tools\hdart\t413_gen.py scene      # t413_scene.png (три валуна 5/6/7 на карте) и t413_scene_b.png (блоки 9)
"""
import argparse
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image, ImageFilter                   # noqa: E402

SET = "FORESTSWAMPBITS"
STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 0, 40, 3, 0.7
SMOOTH_SIGMA = 3.0
EDGE_GAIN = 4.0                                      # крутизна альфы по кромке: ~2 пикс x4 -> ~1
GEN = os.path.join(ROOT, "art", "tickets", "t413", "gen")
CAND = os.path.join(ROOT, "art", "tickets", "t413", "cand")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-30")
GAME = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd", "TERRAIN")

# слова про камень - как у одобренного :3 («pale grey boulders overgrown with dark green moss and vines»).
# Круг 1 (13:00): подложка pick_background (светло-серая 176) съела белый камень - дыры сверху, камень вышел белым яйцом
# в сетке лиан, нарисован контур ромба. Круг 2 (13:15): подложка пурпурная (камень и мох от неё далеки), "light grey, not
# white", лиан мало, контур ромба в негатив - читаемо, но светлее и реже мхом, чем образец :3; столбик 6 тонкий и высокий;
# :5 зерно 4252 - с плитой под камнем. Круг 3: "mid grey", мох густо (около трети поверхности), столбик 6 - приземистый
# камень, у 9 - нейтральный серый без лилового. Сырые ответы круга 1 - gen/_r1, круга 2 лежат рядом с кругом 3 (R2).
PANEL = (190, 50, 190)
ROCK_NEG = ("two boulders, several rocks, pebbles, polka dots, round dots, speckles, dotted pattern, spotted noise, "
            "cube, box, brick wall, cracked glass, shiny, wet, blue tint, snow, mushrooms, flowers, white marble, "
            "snow-white stone, egg shape, net of vines, diamond outline, outline of a tile, thin lines around the foot, "
            "magenta tint, pink tint, purple tint")
STONE = ("mid grey rough stone with a lighter top and clearly darker grey shaded lower and right sides, overgrown "
         "with dense dark green moss in irregular patches covering about a third of the surface, and a few thin vines")
JOBS = {
    4: dict(seeds=[4331, 4332, 4333], r2=[4231, 4232, 4233], slab=False,
            what=("one big lumpy boulder built of a few rounded stone ledges, " + STONE +
                  ", with a little dark green grass at its foot"),
            neg=ROCK_NEG),
    5: dict(seeds=[4351, 4352, 4353], r2=[4251, 4252, 4253], slab=False,
            what=("one big rounded boulder, as wide as it is tall, " + STONE +
                  ", with a small dull dusty brown-pink clay earth bank against its lower right side"),
            neg=ROCK_NEG + ", slab under the boulder, base plate"),
    6: dict(seeds=[4361, 4362, 4363], r2=[4261, 4262, 4263], slab=True,
            what=("one small squat rock, about as tall as it is wide, " + STONE +
                  ", standing on a flat diamond-shaped patch of mid green short grass with darker and lighter green "
                  "patches, the rock covers only the middle of the grass"),
            neg=ROCK_NEG + ", tall pillar, thin spire, obelisk, tower, tree trunk, column, bare ground, flat uniform lawn"),
    7: dict(seeds=[4371, 4372, 4373], r2=[4271, 4272, 4273], slab=False,
            what=("one wide low rounded boulder, " + STONE +
                  ", with a small dull dusty brown-pink clay earth bank against its lower left side"),
            neg=ROCK_NEG + ", slab under the boulder, base plate"),
    9: dict(seeds=[4391, 4392, 4393], r2=[4291, 4292, 4293], slab=True,
            what=("one low square stepped block: its flat top is a diamond of short mid green grass with darker and "
                  "lighter green patches, its two visible side faces are rough neutral mid grey stone with a few "
                  "darker stone ledges and irregular dense patches of dark green moss"),
            neg="dirt top, bare soil, sand, bricks, wooden planks, shiny, wet, blue tint, snow, flowers, mushrooms, "
                "polka dots, speckles, dotted pattern, tall grass blades sticking out of the sides, diamond outline, "
                "outline of a tile, thin lines around the foot, magenta tint, pink tint, purple tint, lilac stone, "
                "white marble, flat uniform lawn"),
}
# лучшие зёрна по листу t413_seeds.png. C1 - "пятна мха" (круг 3: крупные пятна моха на среднем сером камне, одна глыба);
# C2 - "стиль образца :3" (круг 4-5: образец <image2>, трещины камня и лианы; у 4 и 7 модель повторила пару камней образца -
# форма двухглыбовая, не как у классики)
SETS = {
    "C1": {4: 4331, 5: 4352, 6: 4361, 7: 4373, 9: 4392},
    "C2": {4: 4531, 5: 4451, 6: 4461, 7: 4571, 9: 4491},
}
SETNAME = {"C1": "C1 пятна мха", "C2": "C2 стиль :3, лианы"}


# круг 4 (по образцу :3 вторым входом, <image2>): по два зерна на кадр
# 4431/4432 и 4471/4472 скопировали пару камней образца - круг 5 (4531/4532, 4571/4572): в тексте "ОДНА глыба"
REF_SEEDS = {4: [4431, 4432, 4531, 4532], 5: [4451, 4452], 6: [4461, 4462], 7: [4471, 4472, 4571, 4572],
             9: [4491, 4492]}
REF_TEXT = (" Match the painting style of <image2> (rough stone texture, dark green moss and creeping vines) but draw only "
            "the single object described above, in the shape and place of <image1>: do not copy the shape, the "
            "composition or the number of objects of <image2>, and keep the brown-pink clay bank only where <image1> has it. The result is ONE single "
            "stone mass with one rounded top, not two stones side by side.")


def all_seeds(f):
    return list(JOBS[f].get("r2", [])) + list(JOBS[f]["seeds"]) + REF_SEEDS[f]


def sprite(f):
    import map_mockup as mm
    return mm.World().sprite(SET.lower(), f, None).convert("RGBA")


def padded_box(img, pad=PAD):
    bb = img.split()[3].getbbox()
    return (max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad))


def build_prompt(f, ref=False):
    """Как t405_409_gen.build_prompt (R-485): ракурс и свет - фразы battle_view; ромб - невидимая направляющая."""
    import battle_view as bv
    import probe_object as po
    import ticket_q21_probe as q
    J = JOBS[f]
    pb = bv.prompt_block("object")
    what = J["what"]
    tail = q.TAIL_OBJ if not J["slab"] else (
        "Output one isolated object on the same flat panel, nothing else: no ground beyond what is described, no other "
        "objects, no frame, no text.")
    text = (q.PANEL_HINT.replace("{what}", what).replace("flat grey preview panel", "flat magenta preview panel")
            + bv.view_sentence("object") + " "
            + q.KEEP.replace("{noun}", "object").replace("{what}", what) + bv.light_sentence("object") + " " + tail
            + " Draw only the object itself: no diamond outline, no outline of a tile and no thin lines around its foot.")
    if ref:
        text = text.replace(" The tile diamond named above", REF_TEXT + " The tile diamond named above", 1) \
            if " The tile diamond named above" in text else text.replace(
                " Output one isolated object", REF_TEXT + " Output one isolated object", 1)
    neg = po.NEGATIVE + ("" if J["slab"] else ", " + q.SLAB_NEG) + ", " + pb["negative"] + ", " + J["neg"]
    if J["slab"]:                    # у кадров 6 и 9 трава - содержание кадра
        neg = neg.replace("ground, grass tile, floor, ", "")
    if ref:                          # у образца :3 лианы - его стиль
        neg = neg.replace("net of vines, ", "")
    return text, neg


# --- кромка ----------------------------------------------------------------------------------------------
def classic_mask(sprite_k1, size):
    m = (np.asarray(sprite_k1)[..., 3] > 0).astype(np.uint8) * 255
    return np.asarray(Image.fromarray(m).resize(size, Image.NEAREST)) > 0


def post_edge(im, sprite_k1):
    """Кадр x4 RGBA -> заготовка: дыры внутри тела залиты, альфа по кромке сжата (мутная кайма -> ~1 пиксель), вне силуэта
    классики x4 альфа 0, цвет под нулевой альфой обнулён. Возвращает (кадр, пикс. вне силуэта до среза)."""
    import t405_409_gen as T
    im, _n = T.fix_holes(im)
    a = np.asarray(im).astype(np.float32).copy()
    al = a[..., 3] / 255.0
    al = np.clip((al - 0.5) * EDGE_GAIN + 0.5, 0.0, 1.0)
    a[..., 3] = al * 255.0
    m = classic_mask(sprite_k1, (a.shape[1], a.shape[0]))
    # допуск 2 пикс x4 = полпикселя классики: xBRZ-сглаживание контура сдвигает его не дальше; срез по самому NEAREST-силуэту
    # оставлял ступенчатую кромку 4x4 там, где ответ модели шире классики
    m = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(5))) > 0
    out = int(((a[..., 3] > 0) & ~m).sum())
    a[~m, 3] = 0
    # гладкий контур: маска классики не NEAREST x4 (лесенка 4x4), а bicubic + размытие 2 пикс x4 и порог 0.5 с крутизной 8 (кромка ~1 пикс)
    # (там, где ответ модели шире классики, кромку держит эта маска; ступеньки классики 1 пикс сглаживаются в линию)
    big = Image.fromarray((np.asarray(sprite_k1)[..., 3] > 0).astype(np.uint8) * 255).resize(
        (a.shape[1], a.shape[0]), Image.BICUBIC).filter(ImageFilter.GaussianBlur(SMOOTH_SIGMA))
    sm = np.clip((np.asarray(big, np.float32) / 255.0 - 0.5) * 8.0 + 0.5, 0.0, 1.0)
    a[..., 3] = a[..., 3] * sm
    a = np.rint(a).astype(np.uint8)
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA"), out


def cut_seed(f, seed):
    """Сырой ответ gen/<f>/raw/<seed>.png -> кадр x4 с альфой, без видеокарты."""
    import probe_object as po
    full = sprite(f)
    box = padded_box(full)
    frame = full.crop(box)
    hd = Image.open(os.path.join(GEN, str(f), "raw", "%d.png" % seed)).convert("RGB")
    part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT), frame, TONE)
    cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
    cut.paste(part, (box[0] * 4, box[1] * 4))
    cut, _out = post_edge(cut, full)
    cut.save(os.path.join(GEN, str(f), "%d.png" % seed))


def run_pass_ref(painter, args, prompt, image, ref, seed):
    """gen_fire.run_pass с двумя входами: <image1> - эскиз кадра, <image2> - образец стиля (одобренный :3)."""
    import gen_hd
    torch = painter.torch
    W, H = gen_hd.qwen21_size(image.width, image.height, args.mp)
    src = image.convert("RGB").resize((W, H), Image.LANCZOS)
    kw = {"prompt": prompt, "num_inference_steps": args.steps, "generator": torch.Generator("cuda").manual_seed(seed)}
    kw["image"] = [src, ref]
    if "negative_prompt" in painter.accepts:
        import probe_object as po
        kw["negative_prompt"] = po.gen_fire.NEGATIVE
    if "true_cfg_scale" in painter.accepts:
        kw["true_cfg_scale"] = args.cfg
    elif "guidance_scale" in painter.accepts:
        kw["guidance_scale"] = args.cfg
    if "width" in painter.accepts:
        kw["width"], kw["height"] = W, H
    return painter.pipe(**kw).images[0]


def do_render(frames, ref=False):
    import argparse as ap2
    import map_mockup as mm   # noqa: F401
    import probe_object as po
    ns = ap2.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS, qwen21_cfg=CFG,
                       qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="",
                       qwen21_ref_mp=1.0, qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    args = ap2.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    t0, n = time.time(), 0
    for f in frames:
        J = JOBS[f]
        sd = os.path.join(GEN, str(f))
        os.makedirs(os.path.join(sd, "raw"), exist_ok=True)
        text, neg = build_prompt(f, ref)
        print("[%d]\n  PROMPT: %s\n  NEG: %s" % (f, text, neg), flush=True)
        po.gen_fire.NEGATIVE = neg
        full = sprite(f)
        box = padded_box(full)
        frame = full.crop(box)
        panel = PANEL                # круг 2: пурпурная подложка (серая 176 съела светлый камень)
        src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        refimg = None
        if ref:
            r3 = hd_now(3)
            rb = Image.new("RGBA", r3.size, tuple(PANEL) + (255,))
            rb.alpha_composite(r3)
            refimg = rb.convert("RGB").resize((r3.width * 4, r3.height * 4), Image.LANCZOS)
        for seed in (REF_SEEDS[f] if ref else J["seeds"]):
            dst = os.path.join(sd, "%d.png" % seed)
            if os.path.exists(dst):
                print("[%d] зерно %d уже есть" % (f, seed), flush=True)
                continue
            if ref:
                hd = run_pass_ref(painter, args, text, flat.convert("RGB"), refimg, seed)
            else:
                hd = po.gen_fire.run_pass(painter, args, text, flat.convert("RGB"), seed)
            po.gen_hd.save_png(hd, os.path.join(sd, "raw", "%d.png" % seed))
            cut_seed(f, seed)
            n += 1
            print("[%d] зерно %d готово (%d), %.0f с" % (f, seed, n, time.time() - t0), flush=True)


# --- без видеокарты ---------------------------------------------------------------------------------------
def on_dark(im, bg=(30, 66, 30)):
    b = Image.new("RGBA", im.size, bg + (255,))
    b.alpha_composite(im.convert("RGBA"))
    return b.convert("RGB")


def hd_now(f, s=SET):
    p = os.path.join(GAME, s + ".PCK", "%d.png" % f)
    return Image.open(p).convert("RGBA") if os.path.exists(p) else Image.new("RGBA", (128, 160))


def classic4(f):
    return sprite(f).resize((128, 160), Image.NEAREST)


def metrics(im, cls):
    """Доля полупрозрачных (1..254), IoU силуэта с классикой x4, цветов (по телу), резкость (средняя |градиент| яркости
    внутри тела, сжатого на 3 пикс), доля альфы вне силуэта классики."""
    a = np.asarray(im.convert("RGBA"))
    al = a[..., 3]
    body = al > 0
    semi = float(((al > 0) & (al < 255)).sum() / max(1, body.sum()))
    cm = classic_mask(cls, (a.shape[1], a.shape[0]))
    iou = float((body & cm).sum() / max(1, (body | cm).sum()))
    lum = a[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    gy, gx = np.gradient(lum)
    g = np.hypot(gx, gy)
    core = np.asarray(Image.fromarray((al == 255).astype(np.uint8) * 255).filter(ImageFilter.MinFilter(7))) > 0
    sharp = float(g[core].mean()) if core.any() else 0.0
    ncol = len(np.unique(a[body][:, :3], axis=0))
    cm2 = np.asarray(Image.fromarray(cm.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(5))) > 0
    hard = float(((al > 0) & (al < 255)).sum())
    return dict(semi=semi, iou=iou, colors=ncol, sharp=sharp, outside=int(((al > 0) & ~cm2).sum()),
                outside_nearest=int((body & ~cm).sum()), semi_px=int(hard))


def hstack(ims, gap=6, top=0):
    W = sum(i.width for i in ims) + gap * (len(ims) - 1)
    H = max(i.height for i in ims)
    out = Image.new("RGB", (W, H + top), (14, 14, 16))
    x = 0
    for i in ims:
        out.paste(i, (x, top))
        x += i.width + gap
    return out


def load_cand(variant):
    ov = {}
    d = os.path.join(CAND, variant)
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".png"):
                n, f = fn[:-4].rsplit("_", 1)
                ov[(n, int(f))] = Image.open(os.path.join(d, fn)).convert("RGBA")
    return ov


def do_recut(frames):
    for f in frames:
        for seed in all_seeds(f):
            if os.path.exists(os.path.join(GEN, str(f), "raw", "%d.png" % seed)):
                cut_seed(f, seed)
        print("перевырезано:", f)


def seeds_sheet():
    import ticket_scene as ts
    panels = []
    for f in JOBS:
        panels.append(("FSB:%d классика x4" % f, on_dark(classic4(f))))
        panels.append(("FSB:%d сейчас" % f, on_dark(hd_now(f))))
        for seed in all_seeds(f):
            p = os.path.join(GEN, str(f), "%d.png" % seed)
            if os.path.exists(p):
                panels.append(("зерно %d" % seed, on_dark(Image.open(p).convert("RGBA"))))
    ts.sheet(panels, os.path.join(REV, "t413_seeds.png"), cols=10)
    print("лист:", os.path.join(REV, "t413_seeds.png"))


def do_build():
    import shutil
    import ticket_scene as ts
    for v in SETS:
        shutil.rmtree(os.path.join(CAND, v), ignore_errors=True)
        os.makedirs(os.path.join(CAND, v))
    rows = []
    sample = hd_now(3)
    panels = []
    for f in JOBS:
        cls = sprite(f)
        cur = hd_now(f)
        ims = [on_dark(classic4(f)), on_dark(cur)]
        mc = metrics(cur, cls)
        for v, best in SETS.items():
            new = Image.open(os.path.join(GEN, str(f), "%d.png" % best[f])).convert("RGBA")
            new.save(os.path.join(CAND, v, "%s_%d.png" % (SET, f)))
            mn = metrics(new, cls)
            rows.append([f, v, best[f], "%.3f" % mc["semi"], "%.3f" % mn["semi"], "%.3f" % mc["iou"], "%.3f" % mn["iou"],
                         mc["colors"], mn["colors"], "%.1f" % mc["sharp"], "%.1f" % mn["sharp"], mn["outside"],
                         mn["outside_nearest"]])
            ims.append(on_dark(new))
        ims.append(on_dark(sample))
        row = hstack(ims, top=0)
        panels.append(("FSB:%d: классика x4 | HD сейчас | C1 (зерно %d) | C2 (зерно %d) | образец :3 (одобрен)"
                       % (f, SETS["C1"][f], SETS["C2"][f]), row.resize((row.width * 2, row.height * 2), Image.LANCZOS)))
    ts.sheet(panels, os.path.join(REV, "t413_cand.png"), cols=1)
    print("лист:", os.path.join(REV, "t413_cand.png"))
    mc3 = metrics(hd_now(3), sprite(3))
    with open(os.path.join(REV, "t413_cand_checks.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["кадр", "вариант", "зерно", "полупрозр. сейчас", "полупрозр. кандидат", "IoU сейчас", "IoU кандидат",
                    "цветов сейчас", "цветов кандидат", "резкость сейчас", "резкость кандидат",
                    "альфа вне силуэта классики x4 с допуском 2 пикс (кандидат), пикс",
                    "альфа вне NEAREST-силуэта классики x4 (кандидат), пикс - полоса сглаженного контура"])
        w.writerows(rows)
        w.writerow(["3 (образец)", "-", "-", "%.3f" % mc3["semi"], "", "%.3f" % mc3["iou"], "", mc3["colors"], "",
                    "%.1f" % mc3["sharp"], "", "", ""])
    for r in rows:
        print(r)


def do_scene():
    import ticket_scene as ts
    sc = ts.Scene()
    ovs = {v: load_cand(v) for v in SETS}
    jobs = [
        ("t413_scene.png", "FINNIKFOREST05", [(SET, 5), (SET, 6), (SET, 7)], (110, 80)),
        ("t413_scene_b.png", "FINNIKFOREST05", [(SET, 9)], (110, 80)),
    ]
    for name, block, keys, (w, h) in jobs:
        found = ts.find_cells(sc, "FORESTSWAMP", block, keys)
        if not found:
            print("нет клеток", name)
            continue
        box = ts.window([(c[0], c[1], tuple(v * 4 for v in c[2])) for c in found], w, h, 4)
        panels = []
        specs = [("классика", "classic", None), ("HD сейчас", "hd", None)] + \
                [(SETNAME[v], "hd", ovs[v]) for v in SETS]
        for title, mode, o in specs:
            im, _f = sc.render("FORESTSWAMP", block, mode, override=o, k=4, maxz=0)
            panels.append((title, ts.crop_pad(im, box)))
        ts.sheet(panels, os.path.join(REV, name), cols=2)
        print("лист:", os.path.join(REV, name), "клеток", len(found), [c[4] for c in found])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts", "seeds", "build", "scene"])
    ap.add_argument("--frames", nargs="*", type=int, default=list(JOBS), choices=sorted(JOBS))
    ap.add_argument("--ref", action="store_true", help="круг 4: образец :3 вторым входом")
    a = ap.parse_args()
    if a.cmd == "prompts":
        for f in a.frames:
            t, n = build_prompt(f, a.ref)
            print("[%d]\n  PROMPT: %s\n  NEG: %s" % (f, t, n))
    elif a.cmd == "render":
        do_render(a.frames, a.ref)
    elif a.cmd == "recut":
        do_recut(a.frames)
    elif a.cmd == "seeds":
        seeds_sheet()
    elif a.cmd == "build":
        do_build()
    else:
        do_scene()
    return 0


if __name__ == "__main__":
    sys.exit(main())
