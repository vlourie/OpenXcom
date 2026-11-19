#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000379 (верх печной трубы), XP-000388 (дверь дома), XP-000390 (бензоколонка и бак), XP-000391 (кучки мусора):
кандидаты арта по выбору Vitali 31.10 (вариант A у всех четырёх). В МОД НИЧЕГО НЕ СТАВИТ: кадры -
art/tickets/t<номер>/cand/<НАБОР>_<кадр>.png (запасные зёрна - cand/_seeds), листы - art/_review/tickets_2026-10-31/.

Основы (по одной на семью):
  379  chim9   WESTFLOOR:9 -> MEDIEVAL:25 (классика побайтно та же - тот же кадр)
  388  door5   WESTFLOOR:5 (закрыта) -> WESTFLOOR:6 (открыта = зеркало 5 с переносом цвета классики 6), IDT_BARNFLOOR:5/:6 (копии)
  390  pump85  URBAN_WASTE:85 -> MADDECOR_WASTE:49 (зеркало с перекраской), RUSTSHACKS2:51 (копия)
       bin23   URBITS_WASTE:23 -> CATACDECOR_CONC:23 (копия)
  391  junk97  URBAN_WASTE:97;  junk95  URBAN_WASTE:95 -> INDUSLUM:54, PORTURBITS:54 (копии);  junk96  URBAN_WASTE:96

Путь - t405_409_gen / t443_gen (тот же модуль, пути и задания подменены): Qwen-Image-2.1 strict, 40 шагов, cfg 4, 1 Мп, вход -
классика bicubic x16 на подложке pick_background, негатив probe_object + battle_view, cut_out, match_tone 0.7; альфа - силуэт
классики x4, сглаженный xBRZ (probe_object.smooth_silhouette, R-089/R-121/R-568), а не фон ответа. Ракурс и свет - только
battle_view. R-485: ромб - невидимая направляющая, плиты нет. Облик описан по картинке классики (R-460).

    py -3.13 tools\hdart\t379_391_gen.py prompts
    py -3 tools\gpuq.py add --name t379-391 --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t379_391_gen.py render
    py -3.13 tools\hdart\t379_391_gen.py seeds      # листы зёрен t<N>_seeds.png
    py -3.13 tools\hdart\t379_391_gen.py build      # кандидаты по BEST + семьи + листы t<N>_cand.png
    py -3.13 tools\hdart\t379_391_gen.py scene      # сцены на карте для 390/391 (и 379/388 при наличии блока)
"""
import argparse
import csv
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402

import t405_409_gen as g                             # noqa: E402

ART = os.path.join(ROOT, "art", "tickets")
g.GEN = os.path.join(ART, "t379_391", "gen")
g.REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-31")
REV = g.REV
GEN = g.GEN

SLAB = "stone slab, paving tiles, diamond outline"
GLOSS = "glossy, shiny, plastic, specular highlights, wet look, chrome, clean new, cartoon outline"
JOBS = {
    "chim9": dict(
        t="379", nofix=True, members=[("WESTFLOOR", 9, (0, 0, 0))], seeds=[3797, 3798, 3799, 3800, 3801, 3802],
        r1=[3791, 3792, 3793, 3794, 3795, 3796],   # круг 1: венец нависает над стволом, ствол уже классики - у краёв заливка (fix_holes), кирпич розовый
        what=("a square brick chimney stack that fills the whole tile, a plain block with flush sides: two side "
              "faces of dark wine-red maroon bricks with dark mortar lines, deeply shaded (the left face a little "
              "brighter than the right); the top is a narrow cap of dark grey-black rough stone slabs whose outer "
              "edge is exactly flush with the brick faces below, with no overhang and no ledge; in the middle of "
              "the top, inside the stone rim, a square dark open flue mouth, sooty jet black inside, clearly a hole"),
        neg=("solid slab without hole, closed top, lid, grate, flat cobblestone top, overhanging cornice, ledge, "
             "flared top, pink brick, salmon, orange brick, bright red, smoke, fire, grass, snow, text"), slab=False),
    "door5": dict(
        t="388", nofix=True, members=[("WESTFLOOR", 5, (0, 0, 0))], seeds=[3887, 3888, 3889, 3890, 3891, 3892],
        r1=[3881, 3882, 3883, 3884, 3885, 3886],   # круг 1: годно, но нет узкой тёмной торцевой грани справа - у краёв заливка, окно шире классики
        what=("a light orange-brown wooden house door leaf standing on its own: a stout plank frame with a wide thick "
              "post on each side and thick rails, the top rail a broad sloping board with an olive-tan top edge, "
              "a short wide window opening in the upper middle, in the lower half vertical planks with dark gaps "
              "and a tiny black handle on the right post; on the far right edge a narrow dark brown vertical side "
              "face showing the thickness of the door; sun-bleached orange wood with darker grain"),
        neg=("wall, brick wall, stone wall, house, glass pane, curtain, metal door, double door, door frame with "
             "wall around it, floor, bright saturated orange, tall window, text"), slab=False),
    "pump85": dict(
        t="390", members=[("URBAN_WASTE", 85, (0, 0, 0))], seeds=[3901, 3902, 3903, 3904, 3905, 3906], r1=[],
        what=("a tall slim old petrol pump column of dull lilac-violet painted metal: a rounded grey metal cap on "
              "top, below it at the upper right a large black rounded window opening, in the middle of the front "
              "a small dark square panel with a faded brown emblem, at the lower front a black nozzle bay, a "
              "narrow dark left side face and a little rubble and dust at its foot; the paint is scuffed, matte "
              "and weathered"),
        neg=GLOSS + ", fuel nozzle hose, screen with digits, bin, trash can, vending machine, text", slab=False),
    "bin23": dict(
        t="390", members=[("URBITS_WASTE", 23, (0, 0, 0))], seeds=[3921, 3922, 3923, 3924, 3925, 3926],
        r1=[3911, 3912, 3913, 3914, 3915, 3916],   # круг 1: круглая бочка с буквами XOM - у классики короб, слов нет
        what=("a squat dark charcoal-grey square-section steel waste bin, a box and not a drum: a flat dark lid with a "
              "thin pale grey worn rim along its top edge, a narrow lighter grey left side face and a wider front "
              "face with vertical rolled ribs, on the front a patch of rust-brown and orange grime with maroon "
              "streaks; matte, scratched, weathered steel, no letters and no markings"),
        neg=GLOSS + (", round drum, cylinder, barrel, oil drum, circular rim, round lid, lettering, letters, X, "
                     "logo, stencil, wooden staves, plastic bin, wheels, handle, text"), slab=False),
    "junk97": dict(
        t="391", members=[("URBAN_WASTE", 97, (0, 0, 0))], seeds=[3971, 3972, 3973, 3974, 3975, 3976], r1=[],
        what=("a small low flat heap of discarded street rubbish lying on the ground: a dark green glass bottle "
              "lying slanted with its neck pointing up at the right, grey-black broken concrete and metal scraps on "
              "the left, a few tan cardboard and pale pink cloth scraps, a tiny teal scrap and a lilac rag at the "
              "front; everything dusty, dull, scuffed and worn"),
        neg=GLOSS + ", big pile, tall mound, bag, barrel, sack, text", slab=False),
    "junk95": dict(
        t="391", members=[("URBAN_WASTE", 95, (0, 0, 0))], seeds=[3941, 3942, 3943, 3944, 3945, 3946],
        r1=[3951, 3952, 3953, 3954, 3955, 3956],   # круг 1: белая масса вышла серым камнем с зелёными пятнами - у классики белая бумага
        what=("a small low heap of discarded street rubbish lying on the ground: at the back crumpled white paper "
              "sheets and pale grey rags standing up in a ragged mass, a dark green glass bottle beside them, in "
              "front a row of tan cardboard and pale peach cloth scraps, rusty orange crushed can pieces, small dark "
              "green glass shards and grey pebbles; everything dusty, dull, scuffed and worn"),
        neg=GLOSS + ", big pile, tall mound, barrel, rock, boulder, spotted camouflage, polka dots, text", slab=False),
    "junk96": dict(
        t="391", members=[("URBAN_WASTE", 96, (0, 0, 0))], seeds=[3961, 3962, 3963, 3964, 3965, 3966], r1=[],
        what=("two small dark green glass bottles lying on the ground: one standing slanted with its neck up above, "
              "one lying flat in front, with a tan scrap of label paper; dull, dusty, scuffed glass, no shine"),
        neg=GLOSS + ", pile, mound, bag, barrel, text", slab=False),
}
for _j in JOBS.values():
    _j["neg"] = _j["neg"] + ", " + SLAB
BEST = {"chim9": 3802, "door5": 3890, "pump85": 3901, "bin23": 3924, "junk97": 3974, "junk95": 3945, "junk96": 3964}
# запасное зерно (то, что хуже лучшего, но годно) - заполняется после просмотра листа
SPARE = {"chim9": 3799, "door5": 3889, "pump85": 3903, "bin23": 3926, "junk97": 3971, "junk95": 3943, "junk96": 3963}

g.JOBS = JOBS
g.CLUSTERS = {}
g.BEST = BEST

# семья: основа -> [(набор, кадр)]; сам кадр основы тоже в списке (первым)
FAMILY = {
    "chim9": [("WESTFLOOR", 9), ("MEDIEVAL", 25)],
    "door5": [("WESTFLOOR", 5), ("WESTFLOOR", 6), ("IDT_BARNFLOOR", 5), ("IDT_BARNFLOOR", 6)],
    "pump85": [("URBAN_WASTE", 85), ("MADDECOR_WASTE", 49), ("RUSTSHACKS2", 51)],
    "bin23": [("URBITS_WASTE", 23), ("CATACDECOR_CONC", 23)],
    "junk97": [("URBAN_WASTE", 97)],
    "junk95": [("URBAN_WASTE", 95), ("INDUSLUM", 54), ("PORTURBITS", 54)],
    "junk96": [("URBAN_WASTE", 96)],
}
TICKETS = {"379": ["chim9"], "388": ["door5"], "390": ["pump85", "bin23"], "391": ["junk97", "junk95", "junk96"]}
IOU_MIN = 0.90


def cdir(t, sub=""):
    d = os.path.join(ART, "t" + t, "cand", sub)
    os.makedirs(d, exist_ok=True)
    return d


def clip_smooth(im, sprite_k1):
    """Альфа не выходит за силуэт классики, сглаженный xBRZ x4 (R-121, R-568), как t443_gen.clip_smooth."""
    import probe_object as po
    m = Image.fromarray((np.asarray(sprite_k1)[..., 3] > 0).astype(np.uint8) * 255, "L")
    sil = np.asarray(po.smooth_silhouette(m, 4)) > 8
    a = np.asarray(im).copy()
    out = int(((a[..., 3] > 0) & ~sil).sum())
    a[~sil, 3] = 0
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA"), out


g.clip_to_classic = clip_smooth


def pieces(job, seed):
    """Кадр задания из зерна. nofix: без g.fix_holes - у цельного куба трубы и у двери с окном заливка снаружи модельного
    силуэта (низ-угол куба, проём окна шире классики) растягивала соседний цвет полосами/клином; здесь альфа - ответ модели
    (проём остаётся прозрачным), срез по силуэту классики делает clip_smooth."""
    if JOBS[job].get("nofix"):
        k = JOBS[job]["members"][0][:2]
        cut = Image.open(os.path.join(GEN, job, "%d.png" % seed)).convert("RGBA")
        return {k: cut.crop((0, 0, 128, 160))}
    return g.pieces_of(job, seed)


def recolor_any(base_img, base_key, tgt_key, force_mirror=False):
    """Копия классики - тот же кадр; зеркало (в том числе с другим цветом) - зеркало основы и перенос цвета по таблице цветов
    классики цели; иначе перенос цвета. Возвращает (кадр, вид, IoU) или (None, '', IoU)."""
    ob, ot = g.classic_of(*base_key), g.classic_of(*tgt_key)
    if g.same_px(ob, ot):
        return base_img.copy(), "копия", 1.0
    flip = force_mirror or g.mirror_closer(ob, ot)
    if flip:
        base_img = base_img.transpose(Image.FLIP_LEFT_RIGHT)
        ob = ob.transpose(Image.FLIP_LEFT_RIGHT)
    q = g.iou(ob, ot)
    if q < IOU_MIN:
        return None, "", q
    if g.same_px(ob, ot):
        return base_img, "зеркало", q
    return g.colormap_transfer(base_img, ob, ot), ("зеркало+перенос цвета" if flip else "перенос цвета"), q


def do_build():
    new, notes = {}, []
    for t, jobs in TICKETS.items():
        sd = cdir(t, "_seeds")
        for fn in os.listdir(sd):
            os.remove(os.path.join(sd, fn))
        for job in jobs:
            for seed in g.all_seeds(job):
                if seed == BEST[job] or not os.path.exists(os.path.join(GEN, job, "%d.png" % seed)):
                    continue
                for k, im in pieces(job, seed).items():
                    im2, _ = clip_smooth(im, g.classic_of(*k))
                    im2.save(os.path.join(sd, "%s_%d_s%d.png" % (k[0], k[1], seed)))
            base_key = FAMILY[job][0]
            base_img = pieces(job, BEST[job])[base_key]
            for key in FAMILY[job]:
                if key == base_key:
                    im, kind, q = base_img, "основа", 1.0
                else:
                    im, kind, q = recolor_any(base_img, base_key, key, force_mirror=(job == "door5" and key[1] == 6))
                    if im is None:
                        notes.append((job, key, "ПРОПУСК IoU %.2f" % q))
                        continue
                cls = g.classic_of(*key)
                g.check(t, key[0], key[1], im, cls)
                im2, cut = clip_smooth(im, cls)
                im2.save(os.path.join(cdir(t), "%s_%d.png" % key))
                new[key] = im2
                notes.append((job, key, "%s IoU %.2f, срезано за силуэтом %d" % (kind, q, cut)))
    for n in notes:
        print(*n)
    with open(os.path.join(REV, "t379_391_checks.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["тикет", "набор", "кадр", "за силуэтом классики x4 до среза, пикс", "дыры внутри (доля альфа<200)",
                    "яркость новое", "яркость классика", "яркость сейчас"])
        w.writerows(g.CHECK_ROWS)
    make_sheets(new)


def union_box(ims, margin=6):
    """Прямоугольник вокруг непрозрачного во всех картинках (RGBA одного размера), с полем."""
    bbs = [i.split()[3].getbbox() for i in ims if i is not None and i.split()[3].getbbox()]
    x0 = min(b[0] for b in bbs); y0 = min(b[1] for b in bbs)
    x1 = max(b[2] for b in bbs); y1 = max(b[3] for b in bbs)
    W, H = ims[0].size
    return (max(0, x0 - margin), max(0, y0 - margin), min(W, x1 + margin), min(H, y1 + margin))


def fit(im, box, width):
    c = im.convert("RGBA").crop(box)
    c = c.resize((width, int(round(c.height * width / c.width))), Image.LANCZOS)
    return g.on_dark(c)


def triple_big(s, f, new, width=420):
    """Классика | HD сейчас | кандидат, вырезка по объекту, крупно (классика - NEAREST, без сглаживания)."""
    cl = g.classic_of(s, f).resize((128, 160), Image.NEAREST)
    cur = g.hd_now(s, f) or Image.new("RGBA", (128, 160))
    box = union_box([cl, cur, new])
    c = cl.convert("RGBA").crop(box)
    c = c.resize((width, int(round(c.height * width / c.width))), Image.NEAREST)
    ims = [g.on_dark(c), fit(cur, box, width), fit(new, box, width)]
    H = max(i.height for i in ims)
    out = Image.new("RGB", (width * 3 + 12, H + 36), (14, 14, 16))
    for i, im in enumerate(ims):
        out.paste(im, (i * (width + 6), 36))
    return out


def make_sheets(new):
    import ticket_scene as ts
    for t, jobs in TICKETS.items():
        panels = []
        for job in jobs:
            for key in FAMILY[job]:
                if key in new:
                    panels.append(("%s:%d - классика | сейчас | кандидат" % key, triple_big(key[0], key[1], new[key])))
        ts.sheet(panels, os.path.join(REV, "t%s_cand.png" % t), cols=1 if t != "388" else 2)
        print("лист:", os.path.join(REV, "t%s_cand.png" % t))


def do_seeds():
    import ticket_scene as ts
    for t, jobs in TICKETS.items():
        panels = []
        for job in jobs:
            comp, full, at = g.comp_of(job)
            cls = full.resize((full.width * 4, full.height * 4), Image.NEAREST)
            seeds = [(s, Image.open(os.path.join(GEN, job, "%d.png" % s)).convert("RGBA")) for s in g.all_seeds(job)
                     if os.path.exists(os.path.join(GEN, job, "%d.png" % s))]
            box = union_box([cls] + [im for _s, im in seeds])
            w = 360
            panels.append(("%s классика x4" % job, fit(cls, box, w)))
            for s, im in seeds:
                panels.append(("зерно %d" % s, fit(im, box, w)))
        ts.sheet(panels, os.path.join(REV, "t%s_seeds.png" % t), cols=4)
        print("лист:", os.path.join(REV, "t%s_seeds.png" % t))


def load_cand():
    ov = {}
    for t in TICKETS:
        d = cdir(t)
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".png"):
                s, f = fn[:-4].rsplit("_", 1)
                ov[(s, int(f))] = Image.open(os.path.join(d, fn)).convert("RGBA")
    return ov


SCENES = [  # лист, терренбокс, блок, нужные кадры, окно (w, h) пикс базы
    ("t390_cand_scene.png", "URBAN_WASTE", "URBANWASTE12", [("URBAN_WASTE", 85), ("URBITS_WASTE", 23)], (200, 140)),
    ("t391_cand_scene.png", "URBAN_WASTE", None, [("URBAN_WASTE", 97), ("URBAN_WASTE", 95), ("URBAN_WASTE", 96)], (110, 70)),
]


def do_scene():
    import ticket_scene as ts
    sc = ts.Scene()
    ov = load_cand()
    for name, terrain, block, keys, (w, h) in SCENES:
        blocks = [block] if block else sorted(sc.w.blocks_of(terrain))
        found, use, bestn = None, None, (0, 0)
        for b in blocks:
            f = ts.find_cells(sc, terrain, b, keys)
            n = (len({(x[0], x[1]) for x in f}), len(f))
            if f and n > bestn:
                found, use, bestn = f, b, n
        if not found:
            print("нет клеток", name)
            continue
        print(name, "блок", use, "кадры", bestn)
        cell = max(found, key=lambda f: (-f[3], f[2][1]))
        cx, cy = (cell[2][0] + cell[2][2]) / 2, (cell[2][1] + cell[2][3]) / 2
        sel = found if block else [f for f in found if f[3] == cell[3] and
                                    abs((f[2][0] + f[2][2]) / 2 - cx) < 50 and abs((f[2][1] + f[2][3]) / 2 - cy) < 30]
        box = ts.window([(f[0], f[1], tuple(v * 4 for v in f[2])) for f in sel], w, h, 4)
        maxz = max(f[3] for f in found)
        panels = []
        for title, mode, o in (("классика", "classic", None), ("HD сейчас", "hd", None), ("кандидат", "hd", ov)):
            im, _f = sc.render(terrain, use, mode, override=o, k=4, maxz=maxz)
            cr = ts.crop_pad(im, box)
            if not block:
                cr = cr.resize((cr.width * 2, cr.height * 2), Image.NEAREST if mode == "classic" else Image.LANCZOS)
            panels.append(("%s (%s)" % (title, use), cr))
        ts.sheet(panels, os.path.join(REV, name), cols=1)
        print("лист:", os.path.join(REV, name))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts", "seeds", "build", "scene"])
    ap.add_argument("--jobs", nargs="*", default=list(JOBS), choices=sorted(JOBS))
    a = ap.parse_args()
    if a.cmd == "prompts":
        for j in a.jobs:
            t, n = g.build_prompt(j)
            print("[%s]\n  PROMPT: %s\n  NEG: %s" % (j, t, n))
    elif a.cmd == "render":
        g.do_render(a.jobs)
    elif a.cmd == "recut":
        g.recut(a.jobs)
    elif a.cmd == "seeds":
        do_seeds()
    elif a.cmd == "build":
        do_build()
    else:
        do_scene()
    return 0


if __name__ == "__main__":
    sys.exit(main())
