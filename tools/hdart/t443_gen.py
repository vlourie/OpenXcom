#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000443 (Город гулей: между башнями-фермами балки, а не рельсы на шпалах). Вариант В (Vitali 30.10): три основы
Qwen strict и 12 кадров Химгорода - MILWAREGHOUL 47 48 49 50 52 54 и MILWARE 48 49 50 51 53 55 (у обоих наборов классика
побайтно одна и та же: MILWARE 48..51/53/55 = MILWAREGHOUL 47..50/52/54). Остальная семья (PORTROADS, WHITEBITS, XBITSUFO,
LINERSHIPC, XB3BITZ2, CULTAREA, MILURBAN) - рельсы, НЕ трогается.
В МОД НИЧЕГО НЕ СТАВИТ: кадры - art/tickets/t443/cand/<НАБОР>_<кадр>.png, листы - art/_review/tickets_2026-10-30/.

Основы (по клетке, как t435_gen): прямые балки 47 (49 - зеркало), узел с болтами 48 (50 - зеркало), рваные 52 (54 - зеркало).
Путь - t405_409_gen: Qwen-Image-2.1 strict, 40 шагов, cfg 4, 1 Мп, вход - классика bicubic x16 на подложке pick_background,
негатив probe_object + battle_view, cut_out (альфа - силуэт классики x4 со сглаживанием xBRZ, R-089/R-121), match_tone 0.7.
Ракурс и свет - только battle_view. R-485: ромб - невидимая направляющая, плиты нет. Описание - по картинке классики
(R-460): цвет классики - бледно-песочный розовато-бежевый, а не ржавый оранжевый, как и у башен-ферм рядом.

    py -3.13 tools\hdart\t443_gen.py prompts
    py -3 tools\gpuq.py add --name t443 --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t443_gen.py render
    py -3.13 tools\hdart\t443_gen.py seeds     # лист зёрен t443_seeds.png
    py -3.13 tools\hdart\t443_gen.py build     # кандидаты по BEST: 12 кадров в art/tickets/t443/cand
    py -3.13 tools\hdart\t443_gen.py sheets    # t443_cand.png и t443_cand_scene.png
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402

import t405_409_gen as g                             # noqa: E402

g.CAND = os.path.join(ROOT, "art", "tickets", "t443", "cand")
g.GEN = os.path.join(ROOT, "art", "tickets", "t443", "gen")
REV = g.REV
CAND = g.CAND

SLAB = "stone slab, paving tiles, diamond outline"
GIRDER_NEG = ("railway rails, railroad track, wooden sleepers, railway ties, cart, trolley, wheels, pipes, round tubes, "
              "wooden planks, bright orange rust, bright red, text")
JOBS = {
    "beams47": dict(
        members=[("MILWAREGHOUL", 47, (0, 0, 0))], seeds=[4435, 4436, 4437, 4438],
        r1=[4431, 4432, 4433, 4434],     # круг 1: тонкие двутавры вполовину толщины классики, на карте - тонкая ломаная нить
        what=("four separate thick heavy straight steel box girders lying horizontally, all running from the upper left "
              "down to the lower right: one girder at the upper right, one long girder at the left that ends against a "
              "second girder in the middle right, and one girder at the lower left; every girder is chunky and deep, "
              "its body as tall as it is wide, with a broad flat pale tan-beige top face carrying a row of small round "
              "white rivet heads along its middle, a dark grey-brown stripe along its upper edge, a darker tan front "
              "side face with a few rivets, and flat square-cut ends"),
        neg=GIRDER_NEG + ", thin, slim, narrow, flimsy, rail, I-beam web with thin flanges", slab=False),
    "knot48": dict(
        members=[("MILWAREGHOUL", 48, (0, 0, 0))], seeds=[4449, 4450, 4451, 4452],
        r1=[4441, 4442, 4443, 4444, 4445, 4446, 4447, 4448],     # круг 1: тонкие двутавры, годно; круг 2 - те же толстые коробчатые балки, что у 47
        what=("a steel girder junction: in the centre a squat square pale tan-beige steel node block, its left-front face "
              "carries four round blue-grey bolt plates with dark bolt heads in two rows of two, its right face is a ribbed "
              "darker panel with small slots, its top is a light cream plate; four thick heavy chunky steel box girders, "
              "each as tall as it is wide with a row of small white rivets along its top, join the block: one rising "
              "from its top to the upper right, one coming from the upper left, one at the lower left and a short stub "
              "at the lower right"),
        neg=GIRDER_NEG + ", thin, slim, narrow, flimsy, rail, wheels, cart body, locomotive", slab=False),
    "torn52": dict(
        members=[("MILWAREGHOUL", 52, (0, 0, 0))], seeds=[4529, 4530, 4531, 4532],
        r1=[4521, 4522, 4523, 4524, 4525, 4526, 4527, 4528],  # круг 1: слитая масса пятен; круг 2: тонкие двутавры, как у прямых круга 1
        what=("four separate thick heavy straight steel box girders lying horizontally, all running from the upper left "
              "down to the lower right: one girder at the upper right, one long girder at the left that ends against a "
              "second girder in the middle right, and one girder at the lower left; every girder is chunky and deep, "
              "its body as tall as it is wide, pale tan-beige with a row of small white rivets along the top, but fire "
              "damaged: several stretches of the top faces and sides are burnt jet black with ragged soot-black holes"),
        neg=GIRDER_NEG + ", thin, slim, narrow, flimsy, rail, spotted camouflage, leopard print, fire flames, smoke", slab=False),
}
for _j in JOBS.values():
    _j["neg"] = _j["neg"] + ", " + SLAB
CLUSTERS = {"443": list(JOBS)}
BEST = {"beams47": 4438, "knot48": 4452, "torn52": 4530}

g.JOBS = JOBS
g.CLUSTERS = CLUSTERS
g.BEST = BEST

SETS = ("MILWAREGHOUL", "MILWARE")
# кадр MILWAREGHOUL -> кадр MILWARE (классика побайтно та же)
TWIN = {47: 48, 48: 49, 49: 50, 50: 51, 52: 53, 54: 55}
# кадр -> (основа, зеркало?)
PLAN = {47: ("beams47", 47, False), 49: ("beams47", 47, True), 48: ("knot48", 48, False), 50: ("knot48", 48, True),
        52: ("torn52", 52, False), 54: ("torn52", 52, True)}
IOU_MIN = 0.90
TORN = "qwen"          # "proc" - рваные 52/54 процедурно от прямых 47/49


def clip_smooth(im, sprite_k1):
    """Альфа не выходит за силуэт классики, сглаженный xBRZ x4 (R-121): край прямыми отрезками (как t435_gen)."""
    import probe_object as po
    m = Image.fromarray((np.asarray(sprite_k1)[..., 3] > 0).astype(np.uint8) * 255, "L")
    sil = np.asarray(po.smooth_silhouette(m, 4)) > 8
    a = np.asarray(im).copy()
    out = int(((a[..., 3] > 0) & ~sil).sum())
    a[~sil, 3] = 0
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA"), out


g.clip_to_classic = clip_smooth


def target_of(frame, base_img, base_frame, mirror):
    """Кадр цели из основы: копия классики - тот же рисунок; зеркало - зеркало основы и перенос цвета классики цели
    (свет у классики 49/50/54 падает с другой стороны, чем у 47/48/52)."""
    ob, ot = g.classic_of("MILWAREGHOUL", base_frame), g.classic_of("MILWAREGHOUL", frame)
    if not mirror:
        return base_img.copy(), "основа"
    fl = base_img.transpose(Image.FLIP_LEFT_RIGHT)
    obf = ob.transpose(Image.FLIP_LEFT_RIGHT)
    q = g.iou(obf, ot)
    if q < IOU_MIN:
        raise SystemExit("кадр %d: IoU зеркала %.2f < %.2f" % (frame, q, IOU_MIN))
    if g.same_px(obf, ot):
        return fl, "зеркало IoU %.2f" % q
    return g.colormap_transfer(fl, obf, ot), "зеркало+перенос цвета IoU %.2f" % q


def do_build():
    import csv
    new = {}
    for job in JOBS:
        if job == "torn52" and TORN == "proc":
            continue
        for seed in g.all_seeds(job):
            if seed == BEST[job] or not os.path.exists(os.path.join(g.GEN, job, "%d.png" % seed)):
                continue
            for k, im in g.pieces_of(job, seed).items():
                d = os.path.join(CAND, "_seeds")
                os.makedirs(d, exist_ok=True)
                im.save(os.path.join(d, "%s_%d_s%d.png" % (k[0], k[1], seed)))
        for k, im in g.pieces_of(job, BEST[job]).items():
            new[k] = im
    out = {}
    os.makedirs(CAND, exist_ok=True)
    done = {}
    for frame, (job, bf, mirror) in PLAN.items():
        base = new.get(("MILWAREGHOUL", bf))
        if job == "torn52" and TORN == "proc":
            # рваные: силуэт 52 = 47, 54 = 49 побайтно; обугленность - перенос цвета классики на прямые балки
            import obj_derive as od
            src = 47 if frame == 52 else 49
            im = od.transfer(done[src], g.classic_of("MILWAREGHOUL", src), g.classic_of("MILWAREGHOUL", frame))
            kind = "процедурно от %d (перенос цвета классики)" % src
        else:
            im, kind = target_of(frame, base, bf, mirror)
        done[frame] = im
        cls = g.classic_of("MILWAREGHOUL", frame)
        g.check("443", "MILWAREGHOUL", frame, im, cls)
        im2, cut = clip_smooth(im, cls)
        for s, f in (("MILWAREGHOUL", frame), ("MILWARE", TWIN[frame])):
            im2.save(os.path.join(CAND, "%s_%d.png" % (s, f)))
            out[(s, f)] = im2
        print("%d <- %s: %s, срезано за силуэтом %d пикс." % (frame, job, kind, cut))
    with open(os.path.join(REV, "t443_checks.tsv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["вариант", "набор", "кадр", "за силуэтом классики x4 до среза, пикс", "дыры внутри (доля альфа<200)",
                    "яркость новое", "яркость классика", "яркость сейчас"])
        w.writerows(g.CHECK_ROWS)
    return out


def load_cand():
    ov = {}
    for fn in sorted(os.listdir(CAND)):
        if fn.endswith(".png"):
            s, f = fn[:-4].rsplit("_", 1)
            ov[(s, int(f))] = Image.open(os.path.join(CAND, fn)).convert("RGBA")
    return ov


def do_seeds():
    import ticket_scene as ts
    panels = []
    for job in JOBS:
        comp, full, at = g.comp_of(job)
        panels.append(("%s классика x4" % job, g.on_dark(full.resize((full.width * 4, full.height * 4), Image.NEAREST))))
        for seed in g.all_seeds(job):
            p = os.path.join(g.GEN, job, "%d.png" % seed)
            if os.path.exists(p):
                panels.append(("зерно %d" % seed, g.on_dark(Image.open(p).convert("RGBA"))))
    ts.sheet(panels, os.path.join(REV, "t443_seeds.png"), cols=5)
    print("лист:", os.path.join(REV, "t443_seeds.png"))


def do_sheets():
    """t443_cand.png: для каждого из 12 кадров классика | сейчас | кандидат; t443_cand_scene.png: сцена сейва."""
    import ticket_scene as ts
    ov = load_cand()
    panels = []
    for s, frames in (("MILWAREGHOUL", [47, 48, 49, 50, 52, 54]), ("MILWARE", [48, 49, 50, 51, 53, 55])):
        for f in frames:
            panels.append(("%s:%d" % (s, f), g.triple(s, f, ov[(s, f)])))
    ts.sheet(panels, os.path.join(REV, "t443_cand.png"), cols=3)
    print("лист:", os.path.join(REV, "t443_cand.png"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "recut", "prompts", "seeds", "build", "sheets"])
    ap.add_argument("--jobs", nargs="*", default=list(JOBS), choices=sorted(JOBS))
    ap.add_argument("--torn", choices=["qwen", "proc"], default="qwen")
    a = ap.parse_args()
    global TORN
    TORN = a.torn
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
        do_sheets()
    return 0


if __name__ == "__main__":
    sys.exit(main())
