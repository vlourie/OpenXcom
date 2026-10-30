#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000435 (мебель CULTHOUSE08): кандидаты по выбору Vitali 30.10 «три предмета» - стойка CULTDECOR:22 (семья 5),
раковина с двумя кранами CULTEXTRA:31 (семья 19, перенос цвета на перекраски), кулер с большой бутылью CULTDECOR:51 (1).
В МОД НИЧЕГО НЕ СТАВИТ: кадры - art/tickets/t435/cand/, листы - art/_review/tickets_2026-10-30/.

Путь - как t405_409_gen (тот же модуль, пути и задания подменены): Qwen-Image-2.1 strict, 40 шагов, cfg 4, 1 Мп, вход -
классика bicubic x16 на подложке pick_background, негатив probe_object + battle_view, cut_out (альфа - силуэт классики x4,
R-089), match_tone 0.7. Ракурс и свет - только battle_view. R-485: ромб - невидимая направляющая, плиты нет. Описание
облика - по картинке классики, не по имени кадра (R-460: «стойка с пробирками» на деле стеллаж с бутылями и бочками).

    py -3 tools\gpuq.py add --name t435 --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t435_gen.py render
    py -3.13 tools\hdart\t435_gen.py prompts
    py -3.13 tools\hdart\t435_gen.py seeds      # лист зёрен t435_seeds.png
    py -3.13 tools\hdart\t435_gen.py build      # кандидаты по BEST, семья, лист t435_cand.png
    py -3.13 tools\hdart\t435_gen.py scene      # комната CULTHOUSE08: было / стало
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

g.CAND = os.path.join(ROOT, "art", "tickets", "t435", "cand")
g.GEN = os.path.join(ROOT, "art", "tickets", "t435", "gen")
REV = g.REV

SLAB = "stone slab, paving tiles, diamond outline"
JOBS = {
    "stand22": dict(
        members=[("CULTDECOR", 22, (0, 0, 0))], seeds=[4351, 4352, 4353, 4354], r1=[],
        what=("a three-tier dark charcoal-grey steel shelving rack on thin posts: the top tier is a dense field of upright "
              "dark green glass bottles seen from above, the middle tier a row of small orange and olive-green flasks "
              "lying on their sides, the bottom tier a block of bright blue plastic barrels with two round dark "
              "red-brown barrel ends on its left face"),
        neg="bookshelf, wooden crate, plants, cabbage, vegetables, supermarket shelf, labels, text", slab=False),
    "sink31": dict(
        members=[("CULTEXTRA", 31, (0, 0, 0))], seeds=[4361, 4362, 4363, 4364], r1=[],
        what=("a squat kitchen sink cabinet of dark charcoal-grey metal with a flat top, a rectangular cream-white basin "
              "sunk into the top and TWO separate small chrome faucet taps standing side by side at the back edge of the "
              "basin, each with its own arched spout; the right front face has two panel doors with small handles, the "
              "left front face is plain dark grey"),
        neg="single faucet, one tap, bathtub, toilet, mixer with one spout, drawers, wooden cabinet, bright cyan, text",
        slab=False),
    "cooler51": dict(
        members=[("CULTDECOR", 51, (0, 0, 0))], seeds=[4381, 4382, 4383, 4384],
        # круг 1 (4371-74): под кулером серая плита (R-485); круг 2 (4375-78): без плиты, но подложка (светлая) совпала с белым
        # корпусом и стеклом - левая грань и бутыль полупрозрачны (R-089); круг 3: тёмная подложка, стекло матовое
        r1=[4371, 4372, 4373, 4374, 4375, 4376, 4377, 4378],
        panel=(58, 60, 70),
        what=("a slim office water cooler: on top a large frosted pale blue-white water jug bottle with a flat lid, "
              "nearly opaque, below it a square off-white and light-grey cabinet column as wide as the jug, with a few "
              "small beige stains; the cabinet has no foot, no plinth and no base, its lower end is a plain flat cut "
              "standing directly on the panel"),
        neg=("vending machine, fridge, dispenser tap, coloured drink, bottle cap, pedestal, base plate, grey platform, "
             "diamond shaped shadow, narrow thin column, transparent glass, see-through, text"), slab=False),
}
for _j in JOBS.values():
    _j["neg"] = _j["neg"] + ", " + SLAB
CLUSTERS = {"435": ["stand22", "sink31", "cooler51"]}
BEST = {"stand22": 4351, "sink31": 4363, "cooler51": 4383}

g.JOBS = JOBS


def clip_smooth(im, sprite_k1):
    """Альфа не выходит за силуэт классики, сглаженный xBRZ x4 (R-121, как cut_out): край прямыми отрезками, а не лесенкой
    NEAREST x4 (g.clip_to_classic). Возвращает (кадр, сколько пикселей срезано)."""
    import probe_object as po
    m = Image.fromarray((np.asarray(sprite_k1)[..., 3] > 0).astype(np.uint8) * 255, "L")
    sil = np.asarray(po.smooth_silhouette(m, 4)) > 8
    a = np.asarray(im).copy()
    out = int(((a[..., 3] > 0) & ~sil).sum())
    a[~sil, 3] = 0
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA"), out


g.clip_to_classic = clip_smooth
g.CLUSTERS = CLUSTERS
g.BEST = BEST

FAM_STAND = [("DECORLUX", 21), ("MADDECOR", 21), ("SEAMADDECOR", 21), ("VILFRNITURE", 43)]
FAM_SINK = [("CITYFRNITURE", 13), ("CITYFRNITURE", 15), ("COMFRN", 13), ("COMFRN", 15), ("COMFRN2", 9), ("COMMERCE", 91),
            ("COMMERCE_MAG", 91), ("FRNITURE", 13), ("FRNITURE", 15), ("FRNITURE_WASTE", 13), ("FRNITURE_WASTE", 15),
            ("LINERSHIPC", 15), ("MILBARR", 15), ("MILBARR", 25), ("MILBARRGHOUL", 16), ("MILBARRGHOUL", 26),
            ("VILFRNITURE", 12), ("VILFRNITURE", 14)]
IOU_MIN = 0.90


def recolor_any(base_img, base_key, tgt_key):
    """Перекраска: точная копия классики - тот же кадр; зеркало (в том числе с другим цветом) - зеркало основы и перенос цвета
    по таблице цветов классики; иначе перенос цвета без привязки к раскладке. Возвращает (кадр, вид, IoU) или None."""
    ob, ot = g.classic_of(*base_key), g.classic_of(*tgt_key)
    if g.same_px(ob, ot):
        return base_img.copy(), "копия", 1.0
    flip = g.mirror_closer(ob, ot)
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
    for v in CLUSTERS:
        shutil.rmtree(os.path.join(g.CAND, v), ignore_errors=True)
    new, note = {}, []
    for job in JOBS:
        for seed in g.all_seeds(job):
            if not os.path.exists(os.path.join(g.GEN, job, "%d.png" % seed)):
                continue
            for k, im in g.pieces_of(job, seed).items():
                d = os.path.join(g.CAND, "435", "_seeds")
                os.makedirs(d, exist_ok=True)
                im.save(os.path.join(d, "%s_%d_s%d.png" % (k[0], k[1], seed)))
        for k, im in g.pieces_of(job, BEST[job]).items():
            new[k] = g.finish("435", k[0], k[1], im)
    fam = {}
    for base, members in ((("CULTDECOR", 22), FAM_STAND), (("CULTEXTRA", 31), FAM_SINK)):
        for key in members:
            im, kind, q = recolor_any(new[base], base, key)
            if im is None:
                note.append((key, base, "ПРОПУСК: IoU %.2f < %.2f - другой рисунок (угловая раковина), основа не годится" % (q, IOU_MIN)))
                continue
            new[key] = g.finish("435", key[0], key[1], im)
            fam.setdefault(base, []).append(key)
            note.append((key, base, "%s IoU %.2f" % (kind, q)))
    for key, base, s in note:
        print("435 %s <- %s: %s" % (key, base, s))
    with open(os.path.join(REV, "t435_checks.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["вариант", "набор", "кадр", "за силуэтом классики x4 до среза, пикс", "дыры внутри (доля альфа<200)",
                    "яркость новое", "яркость классика", "яркость сейчас"])
        w.writerows(g.CHECK_ROWS)
    make_sheet(new, fam, note)


def make_sheet(new, fam, note):
    import ticket_scene as ts
    main = [("%s:%d" % k, g.triple(k[0], k[1], new[k])) for k in (("CULTDECOR", 22), ("CULTEXTRA", 31), ("CULTDECOR", 51))]
    ts.sheet(main, os.path.join(REV, "_t435_top.png"), cols=3)
    fm = [("%s:%d" % k, g.triple(k[0], k[1], new[k])) for base in fam for k in fam[base]]
    ts.sheet(fm, os.path.join(REV, "_t435_fam.png"), cols=4)
    parts = [Image.open(os.path.join(REV, n)) for n in ("_t435_top.png", "_t435_fam.png")]
    W = max(p.width for p in parts)
    sheet = Image.new("RGB", (W, sum(p.height for p in parts)), (12, 12, 14))
    y = 0
    for p in parts:
        sheet.paste(p, (0, y))
        y += p.height
    sheet.save(os.path.join(REV, "t435_cand_family.png"))
    for n in ("_t435_top.png", "_t435_fam.png"):
        os.remove(os.path.join(REV, n))
    print("лист:", os.path.join(REV, "t435_cand_family.png"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts", "seeds", "build"])
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
        import ticket_scene as ts
        panels = []
        for job in JOBS:
            comp, full, at = g.comp_of(job)
            panels.append(("%s классика x4" % job, g.on_dark(full.resize((full.width * 4, full.height * 4), Image.NEAREST))))
            for seed in g.all_seeds(job):
                p = os.path.join(g.GEN, job, "%d.png" % seed)
                if os.path.exists(p):
                    panels.append(("зерно %d" % seed, g.on_dark(Image.open(p).convert("RGBA"))))
        ts.sheet(panels, os.path.join(REV, "t435_seeds.png"), cols=5)
        print("лист:", os.path.join(REV, "t435_seeds.png"))
    else:
        do_build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
