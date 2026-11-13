#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000413, ВСЯ СЕМЬЯ (Vitali выбрал C2, командир 30.10): основы, которых нет в пилоте t413_gen.py (FORESTSWAMPBITS
4/5/6/7/9 - C2, уже есть). Здесь 11 новых основ: форма 7b (FORESTBITS3:7) и одиночные FORESTBITSRED 3-7, FORESTBITSWASTE 3-7.
В МОД НИЧЕГО НЕ СТАВИТ: готовое - art/tickets/t413/fam/gen/<основа>/, сборка семьи - t413_fam_build.py.

Путь - как t413_gen (C2) и t405_409_gen: Qwen-Image-2.1 strict, 40 шагов, cfg 4, 1 Мп, вход - классика bicubic x16 на
пурпурной подложке, NEGATIVE probe_object + негатив battle_view, cut_out (R-089), match_tone 0.7, post_edge пилота (кромка
~1 пикс x4). Ракурс и свет - ТОЛЬКО battle_view (view_sentence / light_sentence), как в пилоте; relief_object не
используется (R-390).

Отличие от пилота: у кадров, где в классике ромб земли входит в кадр (RED, WASTE), эскиз - ТОЛЬКО предмет (земля классики
на подложке, по индексам палитры пола набора), а земля в готовом кадре - HD-тайл пола того же террейна из пака
(перенос текстуры и цвета окружения: не плоская заплатка, R-545). Предмет сверху, у основания - слабая тень.

    py -3 tools\gpuq.py add --name t413-fam --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t413_fam.py render
    py -3.13 tools\hdart\t413_fam.py prompts [--jobs R3 W5]
    py -3.13 tools\hdart\t413_fam.py recut         # перевырезка из raw, без видеокарты
    py -3.13 tools\hdart\t413_fam.py seeds         # лист зёрен
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

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402

import t413_gen as T                                 # noqa: E402

REV = T.REV
GEN = os.path.join(ROOT, "art", "tickets", "t413", "fam", "gen")
PANEL = T.PANEL
STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = T.STEPS, T.CFG, T.MP, T.ZOOM, 0, T.SOFT, T.PAD, T.TONE

# палитра пола, у которого ромб входит в кадр предмета: (набор пола, кадры пола, правило отбора пикселей земли, HD-тайл)
GROUNDS = {
    "RED": dict(floor="FORESTRED", frames=[0, 4], rule="any", hd=("FORESTRED", 0)),
    "WASTE": dict(floor="FOREST_WASTE", frames=[0], rule="diamond", hd=("FOREST_WASTE", 0)),
}

# круг 1 (RED, без образца): плоские «векторные» серые глыбы без текстуры, у R4 - плиты-многогранники, у R3 тонкая «рука» из
# травинки эскиза. Круг 2: образец :3 вторым входом (текстура, трещины, мягкая светотень) без мха и лиан, "weathered granite",
# эскиз чистится открытием 3x3
STONE_R = ("dark grey rough weathered granite with visible grain, deep cracks and chipped edges, a lighter top and clearly "
           "darker shaded lower and right sides, no moss, no vines")
REF_R = (" Match the painting quality of <image2> (rough stone texture, fine cracks, soft shading, crisp painted detail) but "
         "draw only the object described above, in the shape, the place and with the number of stones of <image1>: do not "
         "copy the shape, the composition, the moss or the vines of <image2> - the new stone is bare dark grey granite with "
         "no moss and no vines at all, and keep the brown-pink clay bank only where <image1> has it.")
NEG_R = ("moss, vines, green, grass, flowers, snow, white marble, polka dots, round dots, speckles, dotted pattern, cube, "
         "box, brick wall, shiny, wet, blue tint, purple tint, magenta tint, pink tint, soil, dirt ground, "
         "diamond outline, outline of a tile, thin lines around the foot, egg shape, flat vector, cartoon, smooth plastic, "
         "flat slab, polygon, low detail")
NEG_W = ("grass, moss, flowers, green, snow, shiny chrome, glossy, blue tint, purple tint, magenta tint, soil, dirt ground, "
         "diamond outline, outline of a tile, thin lines around the foot, text, logo")
NOGROUND = " Draw no ground, no grass and no soil under or around the object: the object alone."

JOBS = {
    # форма 7b (FORESTBITS3:7): купол мха с глиной слева - как FORESTSWAMPBITS:7, образец стиля :3 вторым входом
    "B7B": dict(set="FORESTBITS3", frame=7, ground=None, ref=True, seeds=[4771, 4772, 4773],
                what=("one wide low rounded boulder, " + T.STONE + ", with a small dull dusty brown-pink clay earth bank "
                      "against its lower left side, standing on a little dark green grass"),
                neg=T.ROCK_NEG + ", slab under the boulder, base plate"),
    "R3": dict(set="FORESTBITSRED", frame=3, ground="RED", ref=True, ref_text=REF_R, opening=3,
               seeds=[5831, 5832, 5833], old=[4831, 4832, 4833],
               what=("two big rounded rough boulders touching side by side, a bigger one on the left and a smaller one "
                     "on the right, " + STONE_R),
               neg=NEG_R + ", one single stone"),
    "R4": dict(set="FORESTBITSRED", frame=4, ground="RED", ref=True, ref_text=REF_R, opening=3,
               seeds=[5841, 5842, 5843], old=[4841, 4842, 4843],
               what="one low lumpy boulder with a rounded top, wider than it is tall, " + STONE_R,
               neg=NEG_R + ", two boulders, several rocks"),
    "R5": dict(set="FORESTBITSRED", frame=5, ground="RED", ref=True, ref_text=REF_R, opening=3,
               seeds=[5851, 5852, 5853], old=[4851, 4852, 4853],
               what="one big rounded boulder, as wide as it is tall, " + STONE_R,
               neg=NEG_R + ", two boulders, several rocks"),
    "R6": dict(set="FORESTBITSRED", frame=6, ground="RED", ref=True, ref_text=REF_R, opening=3,
               seeds=[5861, 5862, 5863], old=[4861, 4862, 4863],
               what=("one small compact dark grey pointed rock, about as tall as it is wide, very dark shaded sides and a "
                     "mid grey top, rough granite, no moss, no vines"),
               neg=NEG_R + ", tall pillar, thin spire, obelisk, tower, tree trunk, column, two boulders"),
    "R7": dict(set="FORESTBITSRED", frame=7, ground="RED", ref=True, ref_text=REF_R, opening=3,
               seeds=[5871, 5872, 5873], old=[4871, 4872, 4873],
               what=("one big wide low dome-shaped boulder, " + STONE_R + ", with a small dull dusty brown-pink clay earth "
                     "bank against its lower left side"),
               neg=NEG_R + ", two boulders, several rocks"),
    "W3": dict(set="FORESTBITSWASTE", frame=3, ground="WASTE", ref=False, seeds=[4931, 4932, 4933],
               what=("one big lumpy angular chunk of charred black rock and burnt concrete, tilted slightly, almost black "
                     "with dark grey faces and a few lighter grey edge highlights, a scorched wasteland rubble block"),
               neg=NEG_W + ", cube with perfect edges, crate, wooden box, two objects"),
    "W4": dict(set="FORESTBITSWASTE", frame=4, ground="WASTE", ref=False, seeds=[4941, 4942, 4943],
               what=("one old rusty upright oil drum, a plain cylinder with a flat top rim, weathered brownish-gold rust "
                     "with dark brown streaks and lighter tan highlights"),
               neg=NEG_W + ", wooden barrel, hay, stump, several barrels, lid with handle"),
    "W5": dict(set="FORESTBITSWASTE", frame=5, ground="WASTE", ref=False, seeds=[4951, 4952, 4953],
               what=("one neat stack of four black rubber car tires piled on top of each other, dull black rubber with dark "
                     "grey highlights, a small grey wheel hub visible in the opening of the top tire"),
               neg=NEG_W + ", wheel rims on all tires, two stacks, leaning tower, shiny wet rubber"),
    "W6": dict(set="FORESTBITSWASTE", frame=6, ground="WASTE", ref=False, seeds=[4961, 4962, 4963],
               what=("one small half-buried black rubber tire standing on its edge, with a round dark opening in the middle "
                     "where a short rusty brown post stands, small and low"),
               neg=NEG_W + ", tall tower, big pile, several tires, barrel"),
    "W7": dict(set="FORESTBITSWASTE", frame=7, ground="WASTE", ref=False, seeds=[4971, 4972, 4973],
               what=("one big tall heap of black rubber car tires: three big tires standing on their edge at the bottom "
                     "and several more tires piled on top, dull black rubber with dark grey highlights"),
               neg=NEG_W + ", wheel rims, two heaps, shiny wet rubber"),
}

# --- кадры классики ----------------------------------------------------------------------------------------
_SC = []
_IDX = {}


def scene():
    import ticket_scene as ts
    if not _SC:
        _SC.append(ts.Scene())
    return _SC[0]


def classic_k1(s, f):
    """Классика кадра палитрой Пираток (R-444), RGBA 32x40."""
    return Image.fromarray(np.asarray(scene().classic(s, f))[::4, ::4].copy(), "RGBA")


def index_frame(s, f):
    import water_build as wb
    if s not in _IDX:
        _IDX[s] = wb.read_set(s)
    return _IDX[s][f]


def ground_masks(s, f, g):
    """(предмет, земля) - bool 40x32 по индексам палитры пола. g - ключ GROUNDS."""
    from scipy import ndimage as ndi
    G = GROUNDS[g]
    a = index_frame(s, f)
    fl = set()
    for ff in G["frames"]:
        b = index_frame(G["floor"], ff)
        fl |= set(np.unique(b[b > 0]).tolist())
    yy, xx = np.mgrid[0:40, 0:32]
    diamond = (np.abs(xx - 15.5) / 16.0 + np.abs(yy - 31.5) / 8.5) <= 1.0
    opaque = a > 0
    ground = opaque & np.isin(a, list(fl))
    if G["rule"] == "diamond":
        ground &= diamond
    lab, n = ndi.label(ground)
    for i in range(1, n + 1):
        if (lab == i).sum() <= 4:
            ground[lab == i] = False
    obj = opaque & ~ground
    lab, n = ndi.label(obj)
    for i in range(1, n + 1):
        if (lab == i).sum() <= 4:
            ground[lab == i] = True
    return opaque & ~ground, ground


SK = os.path.join(ROOT, "art", "tickets", "t413", "fam", "sketch")


def obj_sprite(name):
    """Эскиз-предмет из файла sketch/<имя>.png (в venv Qwen нет scipy - файлы готовит команда sketches под py -3.13)."""
    p = os.path.join(SK, name + ".png")
    if os.path.exists(p):
        return Image.open(p).convert("RGBA")
    im = make_obj_sprite(name)
    os.makedirs(SK, exist_ok=True)
    im.save(p)
    return im


def make_obj_sprite(name):
    """Классика, с которой работает генерация: у кадров с землёй - только предмет (земля прозрачна). Тёмный низ предмета
    делит индексы палитры с тенями пола - маску предмета замыкаем по вертикали (closing 5x3) и пробелы красим цветом
    ближайшего пикселя предмета."""
    from scipy import ndimage as ndi
    J = JOBS[name]
    full = classic_k1(J["set"], J["frame"])
    if not J["ground"]:
        return full
    o, _g = ground_masks(J["set"], J["frame"], J["ground"])
    n_open = J.get("opening", 2)
    o = ndi.binary_opening(o, structure=np.ones((n_open, n_open), bool))
    a = np.asarray(full).copy()
    opaque = a[..., 3] > 0
    o2 = ndi.binary_closing(np.pad(o, 4), structure=np.ones((5, 3), bool))[4:-4, 4:-4] & opaque
    o2 |= o
    near = ndi.distance_transform_edt(~o, return_distances=False, return_indices=True)
    fill = o2 & ~o
    a[fill, :3] = a[near[0][fill], near[1][fill], :3]
    a[~o2, 3] = 0
    a[o2, 3] = 255
    return Image.fromarray(a, "RGBA")


def all_seeds(name):
    return list(JOBS[name].get("old", [])) + list(JOBS[name]["seeds"])


def build_prompt(name):
    """Как t413_gen.build_prompt / t405_409_gen.build_prompt (R-485): ракурс и свет - фразы battle_view; ромб - невидимая
    направляющая, плиты нет; у кадров с землёй - предмет один, без земли."""
    import battle_view as bv
    import probe_object as po
    import ticket_q21_probe as q
    J = JOBS[name]
    pb = bv.prompt_block("object")
    what = J["what"]
    tail = q.TAIL_OBJ + (NOGROUND if J["ground"] else "")
    text = (q.PANEL_HINT.replace("{what}", what).replace("flat grey preview panel", "flat magenta preview panel")
            + bv.view_sentence("object") + " "
            + q.KEEP.replace("{noun}", "object").replace("{what}", what) + bv.light_sentence("object") + " " + tail
            + " Draw only the object itself: no diamond outline, no outline of a tile and no thin lines around its foot.")
    if J["ref"]:
        text = text.replace(" The tile diamond named above", J.get("ref_text", T.REF_TEXT) + " The tile diamond named above", 1)
    neg = po.NEGATIVE + ", " + q.SLAB_NEG + ", " + pb["negative"] + ", " + J["neg"]
    if J["ref"]:
        neg = neg.replace("net of vines, ", "")
    return text, neg


def padded_box(img, pad=PAD):
    return T.padded_box(img, pad)


def cut_seed(name, seed):
    """Сырой ответ gen/<name>/raw/<seed>.png -> кадр x4 с альфой (только предмет), без видеокарты."""
    import probe_object as po
    cls = obj_sprite(name)
    box = padded_box(cls)
    frame = cls.crop(box)
    hd = Image.open(os.path.join(GEN, name, "raw", "%d.png" % seed)).convert("RGB")
    part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT), frame, TONE)
    cut = Image.new("RGBA", (cls.width * 4, cls.height * 4), (0, 0, 0, 0))
    cut.paste(part, (box[0] * 4, box[1] * 4))
    cut, _out = T.post_edge(cut, cls)
    cut.save(os.path.join(GEN, name, "%d.png" % seed))


def do_render(names):
    import argparse as ap2
    import probe_object as po
    ns = ap2.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS, qwen21_cfg=CFG,
                       qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="",
                       qwen21_ref_mp=1.0, qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    args = ap2.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    t0, n = time.time(), 0
    for name in names:
        J = JOBS[name]
        sd = os.path.join(GEN, name)
        os.makedirs(os.path.join(sd, "raw"), exist_ok=True)
        text, neg = build_prompt(name)
        print("[%s]\n  PROMPT: %s\n  NEG: %s" % (name, text, neg), flush=True)
        po.gen_fire.NEGATIVE = neg
        cls = obj_sprite(name)
        box = padded_box(cls)
        frame = cls.crop(box)
        src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(PANEL) + (255,))
        flat.alpha_composite(src)
        refimg = None
        if J["ref"]:
            r3 = T.hd_now(3)
            rb = Image.new("RGBA", r3.size, tuple(PANEL) + (255,))
            rb.alpha_composite(r3)
            refimg = rb.convert("RGB").resize((r3.width * 4, r3.height * 4), Image.LANCZOS)
        flat.convert("RGB").save(os.path.join(sd, "sketch.png"))
        for seed in J["seeds"]:
            dst = os.path.join(sd, "%d.png" % seed)
            if os.path.exists(dst):
                print("[%s] зерно %d уже есть" % (name, seed), flush=True)
                continue
            if J["ref"]:
                hd = T.run_pass_ref(painter, args, text, flat.convert("RGB"), refimg, seed)
            else:
                hd = po.gen_fire.run_pass(painter, args, text, flat.convert("RGB"), seed)
            po.gen_hd.save_png(hd, os.path.join(sd, "raw", "%d.png" % seed))
            cut_seed(name, seed)
            n += 1
            print("[%s] зерно %d готово (%d), %.0f с" % (name, seed, n, time.time() - t0), flush=True)


def do_recut(names):
    for name in names:
        for seed in all_seeds(name):
            if os.path.exists(os.path.join(GEN, name, "raw", "%d.png" % seed)):
                cut_seed(name, seed)
        print("перевырезано:", name)


def hd_floor(g):
    s, f = GROUNDS[g]["hd"]
    return T.hd_now(f, s)


def seeds_sheet(names):
    import ticket_scene as ts
    panels = []
    for name in names:
        J = JOBS[name]
        cls = obj_sprite(name)
        panels.append(("%s %s:%d классика x4 (предмет)" % (name, J["set"], J["frame"]),
                       T.on_dark(cls.resize((128, 160), Image.NEAREST))))
        cur = T.hd_now(J["frame"], J["set"])
        panels.append(("сейчас", T.on_dark(cur)))
        for seed in all_seeds(name):
            p = os.path.join(GEN, name, "%d.png" % seed)
            if os.path.exists(p):
                panels.append(("зерно %d" % seed, T.on_dark(Image.open(p).convert("RGBA"))))
    out = os.path.join(REV, "t413_fam_seeds.png")
    ts.sheet(panels, out, cols=5)
    print("лист:", out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts", "seeds", "sketches"])
    ap.add_argument("--jobs", nargs="*", default=list(JOBS), choices=sorted(JOBS))
    a = ap.parse_args()
    if a.cmd == "prompts":
        for j in a.jobs:
            t, n = build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, t, n))
    elif a.cmd == "sketches":
        for j in a.jobs:
            os.makedirs(SK, exist_ok=True)
            make_obj_sprite(j).save(os.path.join(SK, j + ".png"))
            print("эскиз", j)
    elif a.cmd == "render":
        do_render(a.jobs)
    elif a.cmd == "recut":
        do_recut(a.jobs)
    else:
        seeds_sheet(a.jobs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
