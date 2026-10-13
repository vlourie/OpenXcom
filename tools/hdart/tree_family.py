"""TREE_RENDER_V2 на производственные семейства деревьев (решение специалиста 13.10: первая партия из 9
семейств, без нового METHOD CHECK). Ядро - tree_render (V1): MAIN одним рендером, срез z0 с замком латентов.
Свободный рендер среза z1 не запускается (решение 09.10): у трёхэтажных семейств вид z<=1 собирается кодом.

Семейство = одна производственная единица: набор, главная раскладка по переписи
census/trees/groups/batchA_layouts.json (все раскладки - для проверки), подсказки только по классике.

  tree_family.py --mask-only [--fam TG011,...]   листы классики и масок срезов, модель не грузится
  tree_family.py --assemble [--fam TG011,...]    кадры, все раскладки, сканер швов, листы (CPU, без модели)
  tree_family.py [--max-renders 4]               рендер того, чего нет (возобновляемо; только через gpuq)

Модель - только через очередь видеокарты (tools/gpu_scripts.txt).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.dirname(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import tree_render as tr                            # noqa: E402

ENC = "utf-8-sig"
OUT = "census/trees/groups/batchA"
LAYOUTS = "census/trees/groups/batchA_layouts.json"

# подсказки - только то, что есть на классике (R-016, R-040); срез z0 - только недостающая часть и её связь
# с закреплённым (R-305): ствол растёт из уже нарисованного основания, без зазора, один
FAMILIES = {
    "TG035": dict(
        # 13.10 перерисовка по вердикту специалиста: «bright green» дал крону светлее классики на dL +15 (R-016),
        # «twisted» - тонкий витой ствол вместо толстого прямого (кадр 57); слова - по классике
        main="one large dense broadleaf jungle tree with a rounded crown of dense dark green leaves in deep shade, "
             "only small lighter green highlights on the upper leaves, two or three thin dark red branches barely "
             "visible deep inside the leaves, and a short thick crimson red trunk widening into crimson roots, "
             "low green grass around the base",
        cut0="the lower part of one short thick crimson red trunk whose leafy crown has been removed: the trunk "
             "rises directly out of the crimson roots that are already drawn at the bottom, almost straight and "
             "as thick as those roots, with a flat sawn top and one short red branch stub on its right side; "
             "it reaches down to those roots without a gap, one single trunk only",
        stumps={58: "a broken short crimson red tree stump with twisted crimson roots"}),
    "TG011": dict(
        main="one tall tropical tree with a curved grey brown trunk and a crown of wide drooping dark green fern "
             "fronds, standing on a small grass patch",
        cut0="the lower part of one curved grey brown tree trunk whose crown has been removed: the trunk rises "
             "directly out of the trunk base and grass patch that are already drawn at the bottom, with a flat "
             "sawn top; it reaches down to that base without a gap, one single trunk only"),
    "TG015": dict(
        main="one tall palm tree with a straight upright light brown ringed trunk flaring into roots at the base "
             "and a crown of green fronds",
        cut0="the lower part of one straight light brown ringed palm trunk whose crown has been removed: the trunk "
             "rises directly out of the flared roots that are already drawn at the bottom, with a flat sawn top; "
             "it reaches down to those roots without a gap, one single trunk only"),
    "TG009": dict(
        main="one tall dead bare tree with a thin dark grey trunk and bare dark grey twisted branches, no leaves",
        cut0="the lower part of one thin dark grey dead tree trunk whose upper part has been removed: the trunk "
             "rises directly out of the base that is already drawn at the bottom, with a flat sawn top and one or "
             "two short bare branch stubs; it reaches down to that base without a gap, one single trunk only"),
    "TG021": dict(
        main="one tall palm tree with a slightly leaning light tan brown trunk flaring into big roots at the base "
             "and a crown of dark green fronds",
        cut0="the lower part of one slightly leaning light tan brown palm trunk whose crown has been removed: the trunk rises "
             "directly out of the flared roots that are already drawn at the bottom, with a flat sawn top; it "
             "reaches down to those roots without a gap, one single trunk only"),
    "TG036": dict(
        main="one tall dead bare tree with a dark purplish brown trunk and bare thin dark twisted branches, no "
             "leaves",
        cut0="the lower part of one dark purplish brown dead tree trunk whose upper part has been removed: the "
             "trunk rises directly out of the base that is already drawn at the bottom, with a flat sawn top and "
             "one or two short bare branch stubs; it reaches down to that base without a gap, one single trunk "
             "only"),
    "TG037": dict(
        main="one round leafy deciduous tree with a dense rounded crown of dark green leaves and a thin dark brown "
             "trunk",
        cut0="the lower part of one thin dark brown tree trunk whose leafy crown has been removed: the trunk rises "
             "directly out of the base that is already drawn at the bottom, with a flat sawn top and a few short "
             "leafy branch stubs; it reaches down to that base without a gap, one single trunk only"),
    "TG038": dict(
        main="one tall fir tree with dark green needle branches covered with white snow on their upper surfaces "
             "and a thin dark brown trunk",
        cut0="the lower part of one thin dark brown fir trunk whose upper part has been removed: the trunk rises "
             "directly out of the base that is already drawn at the bottom, with a flat sawn top and a few short "
             "snowy branch stubs; it reaches down to that base without a gap, one single trunk only"),
}
# TG060 VILFRNITURE 85-100 - побайтные копии FOREST 42-57: кадры из канона FOREST, рендера нет;
# VILFRNITURE:101 (пень) отличается от FOREST:58 - отдельное решение после SAFE (не здесь)
COPY_OF = {"TG060": dict(src="FOREST", shift=43,
                         frames="census/trees/forest42/render_v2/s2712/FOREST/comp/frames/FOREST.PCK")}


def load(fams):
    D = json.load(open(LAYOUTS, encoding=ENC))
    CL, sets = {}, {}
    for fid in fams:
        d = D[fid]
        S = d["set"]
        if S in CL:
            raise SystemExit("набор %s в двух семействах партии" % S)
        CL[S] = {"sigs": [{"sig": L["sig"], "n": L["n"]} for L in d["layouts"]]}
        sets[fid] = S
    return D, CL, sets


def patch(fid, S, CL):
    """Подсказки и пни одного семейства в ядро V1; свободный срез z1 не рисуется (S в tr.DERIVED -> только z0)."""
    F = FAMILIES[fid]
    tr.TREE_WHAT.clear()
    tr.CUT_WHAT.clear()
    tr.STUMPS.clear()
    tr.TREE_WHAT[S] = F["main"]
    tr.CUT_WHAT[(S, 0)] = F["cut0"]
    for f, what in F.get("stumps", {}).items():
        tr.STUMPS[(S, f)] = what
    tr.DERIVED = (S,)


def count_png(d):
    return sum(len([f for f in fs if f.endswith(".png") and (f.startswith("raw_") or f.startswith("stump_"))])
               for _r, _d, fs in os.walk(d)) if os.path.isdir(d) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fam", default=",".join(FAMILIES), help="семейства через запятую")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--seeds", default="2712")
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--grow", type=int, default=2)
    ap.add_argument("--soft", type=int, default=40)
    ap.add_argument("--pad", type=int, default=3)
    ap.add_argument("--tone", type=float, default=0.7)
    ap.add_argument("--max-renders", type=int, default=4, dest="max_renders")
    ap.add_argument("--mask-only", action="store_true", dest="mask_only", help="листы масок, без модели")
    ap.add_argument("--assemble", action="store_true", help="кадры, все раскладки, сканер швов - без модели")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    fams = [f for f in args.fam.split(",") if f]
    bad = [f for f in fams if f not in FAMILIES and not (args.assemble and f in COPY_OF)]
    if bad:
        raise SystemExit("неизвестные семейства %s" % bad)
    args.seeds = [int(s) for s in args.seeds.split(",")]
    args.stumps = set()
    D, CL, sets = load(fams)
    world = tr.mm.World()
    hints = json.load(open(tr.HINTS, encoding=ENC))
    root, left = args.out, args.max_renders
    for fid in fams:                     # своя папка на семейство: JUNGLE живёт и в TG011, и в TG010
        S = sets[fid]
        args.sets, args.out = [S], os.path.join(root, fid)
        os.makedirs(args.out, exist_ok=True)
        if fid in COPY_OF:               # копия канона: без рендера и без подсказок
            import tree_family_asm
            tree_family_asm.assemble_copy(args, fid, S, world, CL, COPY_OF[fid])
            continue
        patch(fid, S, CL)
        print("== %s %s: раскладок %d, главная на %d мест" % (fid, S, len(CL[S]["sigs"]), CL[S]["sigs"][0]["n"]),
              flush=True)
        if args.mask_only:
            tr.do_masks(args, world, CL, hints)
            continue
        if args.assemble:
            import tree_family_asm
            tree_family_asm.assemble_family(args, fid, S, world, CL, hints)
            continue
        before = count_png(args.out)
        args.max_renders = left          # общий предел рендеров на процесс (R-215), а не на семейство
        tr.do_render(args, world, CL, hints)
        if root and left:
            left -= count_png(args.out) - before
            if left <= 0:
                print("предел рендеров на процесс - выход (R-215)", flush=True)
                return


if __name__ == "__main__":
    main()
