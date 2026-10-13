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
# совместная проба ели и пальмы (решение специалиста 13.10): модуль = свой рендер со своей главной раскладкой,
# проверочные - сочетания census/trees/groups/crown/combos.json своего набора из кадров модуля. Ствол со спилом -
# срез z0 под верхом (как столбы партии A); крона ели - один рендер без среза (на земле и над стволом 21)
MODULE_OUT = "census/trees/groups/crown/probe"
COMBOS = "census/trees/groups/crown/combos.json"
MODULES = {
    "SPRUCE": dict(                       # TG003: ствол 21 + верхушка 22 над ним (629 мест)
        set="FOREST", kind="spruce", frames=(21, 22),
        main="one tall spruce tree with a thin dark red brown trunk: the lower half has a few sparse dark green "
             "needle branches spreading sideways with the trunk visible between them, the upper half is a dense "
             "narrow cone of layered dark green needle branches with lighter green tips, dark roots at the base",
        cut0="the lower part of one thin dark red brown spruce trunk whose top has been removed: the trunk rises "
             "directly out of the dark roots that are already drawn at the bottom, with a few sparse dark green "
             "needle branches spreading sideways and a flat sawn light brown top; it reaches down to those roots "
             "without a gap, one single trunk only"),
    "SPRUCE_CROWN": dict(                 # TG019: крона 23-26 2x2 (над стволом 21 - 127 мест, на земле - 33)
        set="FOREST", kind="spruce", frames=(23, 24, 25, 26),
        sig=[[23, 3, 0, 0, 0], [24, 3, 0, 1, 0], [25, 3, 1, 1, 0], [26, 3, 1, 0, 0]],
        main="one very large dense rounded conifer crown of dark green needle foliage in many horizontal layered "
             "tiers with lighter green tips and deep dark shade between the tiers"),
    "PALM": dict(                         # TG004 + TG005: ствол 16 + крона 12-14 с пеньком 14 (97 мест)
        set="COMDECOR", kind="palm", frames=(12, 13, 14, 16),
        main="one palm tree with a thick light tan trunk with a dark brown shadow side, flaring into roots at the "
             "base, and a crown of drooping dark green fronds",
        cut0="the lower part of one thick light tan palm trunk whose crown has been removed: the trunk rises "
             "directly out of the flared roots that are already drawn at the bottom, with a dark brown shadow side "
             "and a flat sawn grey top; it reaches down to those roots without a gap, one single trunk only"),
    # общая сборка ели без рендера: кадры обоих модулей во ВСЕХ сочетаниях набора (127 ствол + крона, 33 - кадр
    # 23 на месте 25, 10 - смешанная пара), главная - самая частая (629)
    "SPRUCE_JOINT": dict(set="FOREST", kind="spruce", frames=(21, 22, 23, 24, 25, 26),
                         parts=("SPRUCE", "SPRUCE_CROWN"), main=""),
}
# TG060 VILFRNITURE 85-100 - побайтные копии FOREST 42-57: кадры из канона FOREST, рендера нет;
# VILFRNITURE:101 (пень) отличается от FOREST:58 - отдельное решение после SAFE (не здесь)
COPY_OF = {"TG060": dict(src="FOREST", shift=43,
                         frames="census/trees/forest42/render_v2/s2712/FOREST/comp/frames/FOREST.PCK")}
# партия 1 конвейера (решение специалиста 13.10): одиночные деревья в одну клетку и один этаж - один рендер MAIN,
# без срезов и кромок; раскладки - группы копий того же кадра по картам (batch1_layouts.json, строит перепись
# hits.pkl), главная - одна клетка. Пни die - отдельный класс STUMP, здесь не рисуются. Подсказки - по классике
SINGLE_OUT = "census/trees/groups/batch%d"
SINGLE_LAYOUTS = "census/trees/groups/batch%d_layouts.json"
# партия 2 (13.10): следующие 20 по классам переписи singles/classes.tsv - TREE и два куста джунглей BUSH;
# отложены до опознания TG056 (рыжий шар на голом стволе) и TG093 (пальма, обрезанная краем кадра)
SINGLE_BATCH = {f: 2 for f in ("TG014", "TG024", "TG045", "TG046", "TG047", "TG049", "TG050", "TG055", "TG064",
                               "TG065", "TG066", "TG067", "TG077", "TG080", "TG084", "TG085", "TG086", "TG091",
                               "TG094", "TG095")}
# партия 3 (13.10): пни и сломанные стволы STUMP, бревна LOG, кусты BUSH и TG096 из singles/classes.tsv;
# отложены горящие TG071 и TG092 (огонь - анимация, R-071), TG048 (отдельное решение), VR TG073 (R-314)
SINGLE_BATCH.update({f: 3 for f in ("TG013", "TG023", "TG031", "TG044", "TG053", "TG054", "TG058", "TG059", "TG061",
                                    "TG062", "TG063", "TG069", "TG072", "TG075", "TG078", "TG079", "TG082", "TG083",
                                    "TG087", "TG096")})
GRASS = ", standing on a square patch of green grass"
SINGLES = {
    "TG002": "one apple tree with a dense rounded crown of dark green leaves dotted with small red apples and a "
             "short dark brown trunk",
    "TG006": "one apple tree with a dense rounded crown of dark green leaves dotted with small red apples and a "
             "short dark brown trunk" + GRASS,
    "TG008": "one small slender fir tree with a narrow cone of dark blue green needle branches and a thin dark "
             "trunk",
    "TG012": "one broadleaf tree with a dense rounded crown of green leaves and a short dark brown trunk" + GRASS,
    "TG016": "one broadleaf tree with a dense rounded crown of light and dark green leaves and a thin dark brown "
             "trunk with a few branches below the crown" + GRASS,
    "TG017": "one small bare leafless sapling with a thin dark trunk and thin upright twigs covered with white "
             "snow, standing on a square patch of white snow",
    "TG018": "one small palm tree with a curved leaning light brown trunk and a crown of bright green fronds" + GRASS,
    "TG022": "one palm tree with a thin curved light grey brown trunk and a crown of long bright and dark green "
             "fronds" + GRASS,
    "TG025": "one small young fir tree with a narrow cone of very dark green needle branches with white snow on "
             "their upper surfaces and a thin dark trunk",
    "TG026": "one bare dead tree with a dark brown trunk and a few thin twisted bare branches, standing on a "
             "square patch of dark brown earth",
    "TG027": "one broadleaf tree with a broad dense crown of dark green leaves and a short dark brown trunk with "
             "roots",
    "TG029": "one tall broadleaf tree with a dense crown of dark green leaves and a short dark trunk with roots",
    "TG032": "one broadleaf tree with a rounded dense crown of green leaves and a short dark trunk with small "
             "dark red roots",
    "TG033": "one small bare dead tree with a black trunk forking into a few thin black bare branches",
    "TG034": "one tall thin bare dead tree with a straight dark grey trunk and short thin bare dark grey branches",
    "TG039": "one dead dry tree trunk leaning steeply to the left, pale orange brown wood with a few bare broken "
             "branches at the top, on a small patch of bright orange sand at its base",
    "TG040": "one bare dead tree with a twisted black trunk and twisted bare black branches, standing on a square "
             "patch of grey and tan dirt",
    "TG041": "one small round tree with a dense crown of bright and dark green leaves and a short dark brown trunk",
    "TG042": "one broadleaf tree with a dense crown of dark green leaves, a dark brown trunk with branches visible "
             "inside the crown" + GRASS,
    "TG043": "one burnt dead tree with a charred black trunk and a few bare charred branches, on a small patch "
             "of bright orange sand at its base",
    # партия 2
    "TG014": "one dense low jungle bush, a wide mound of large overlapping dark and bright green leaves filling the "
             "whole cell" + GRASS,
    "TG024": "one dense jungle bush of large dark and bright green leaves with thin reddish brown stems visible "
             "between the leaves" + GRASS,
    "TG045": "one broadleaf jungle tree with a wide dense crown of bright and dark green leaves and thin orange "
             "brown branches visible through the lower part of the crown",
    "TG046": "one tall thin bare dead tree with a straight dark grey trunk and short thin bare dark grey branches",
    "TG047": "one palm tree with a tall curved light pinkish brown ringed trunk and a crown of long bright green "
             "fronds" + GRASS,
    "TG049": "one small dense fir bush shaped like a rounded cone of dark green needles, with no visible trunk",
    "TG050": "one narrow fir tree with dark green needle branches heavily covered with white snow and a thin dark "
             "trunk",
    "TG055": "one broadleaf tree with a dense rounded crown of dark green leaves, brown branches visible inside the "
             "crown, and a short dark brown trunk",
    "TG064": "one bare dead tree with a thin black trunk and long thin black bare branches spreading sideways",
    "TG065": "one broadleaf tree with a dense crown of green leaves covered with many bright yellow flowers and a "
             "dark brown trunk" + GRASS,
    "TG066": "one small palm tree with a short curved light brown trunk and a wide crown of long bright and dark "
             "green fronds",
    "TG067": "one small palm with a very short light brown trunk and a wide low spreading crown of long bright "
             "green fronds",
    "TG077": "one palm tree with a tall curved light pinkish brown ringed trunk and a crown of long bright and dark "
             "green fronds",
    "TG080": "one bare dead tree with a twisted dark grey trunk and a few twisted bare branches, standing on a "
             "square patch of dark green grass",
    "TG084": "one bare dead tree with a twisted dark purplish black trunk and a few twisted bare branches, "
             "standing on a square patch of dark green grass",
    "TG085": "one bare dead tree with a twisted dark grey trunk and a few twisted bare branches",
    "TG086": "one palm tree with a curved light brown trunk leaning to the left and a crown of dark green fronds, "
             "standing on a square patch of green grass with a small dark green pond at its base",
    "TG091": "one bare dead tree with a split pale grey trunk leaning to the right and a few broken bare grey "
             "branches, on a small patch of brown dirt at its base",
    "TG094": "one tiny bare dead sapling with a dark grey forked trunk and a few short bare twigs",
    "TG095": "one bare dead tree with a dark brown black trunk forking into several long bare branches reaching "
             "upwards",
    # партия 3
    "TG013": "one fallen log lying on the ground, dark brown bark almost completely covered with a thick lumpy layer "
             "of white snow",
    "TG023": "one tall broken dead tree trunk, a hollow brown stump split into two jagged points at the top, dark "
             "reddish brown fallen leaves around its roots, standing on a small patch of green grass",
    "TG031": "one small dry dead bush, a few short twisted black bare branches, on a small patch of grey and pinkish "
             "brown dirt",
    "TG044": "a few fallen bare brown branches lying crossed on the ground, with white snow on their upper surfaces",
    "TG053": "one tall broken tree stump split into jagged points at the top, brown bark, dark reddish brown fallen "
             "leaves around its roots" + GRASS,
    "TG054": "one low broken brown tree stump with a dark green leafy bush growing on its left side, on a small "
             "patch of green grass",
    "TG058": "one tall broken tree stump split into jagged points at the top, brown bark, dark reddish brown fallen "
             "leaves around its roots, standing on a square patch of white snow",
    "TG059": "one fallen log broken into two pieces lying on the ground, brown bark with white snow on the top",
    "TG061": "one tall broken dead tree trunk split into jagged points at the top, brown bark, on a small patch of "
             "grey gravel",
    "TG062": "one tall broken dead tree trunk split into jagged points at the top, brown bark, on a small patch of "
             "brown mud",
    "TG063": "one tall broken dead tree trunk split into jagged points at the top, brown bark covered with white "
             "snow on its upper parts",
    "TG069": "one tall broken tree stump with a hollow top and a dark hole in its brown bark, dark reddish brown "
             "fallen leaves around its roots" + GRASS,
    "TG072": "one tall broken dead tree trunk split into jagged points at the top, reddish brown bark, on a small "
             "patch of pale grey gravel",
    "TG075": "one tall broken dead tree stump with very dark grey black bark, black thorny undergrowth around it and "
             "dark violet grey roots spreading on the ground",
    "TG078": "one low cut tree stump with a flat top, brown wood, on a small patch of brown mud",
    "TG079": "one low broken tree stump, brown wood with white snow on its top",
    "TG082": "one tall broken dead tree stump with very dark grey black bark split at the top and dark violet grey "
             "roots spreading on the ground around it",
    "TG083": "one tall cut tree stump with a flat top showing light wood, light brown bark with a dark hole, green "
             "jungle leaves around its base" + GRASS,
    "TG087": "one tall broken dead tree stump with very dark grey black bark, a dark hole in the trunk and dark "
             "violet grey roots spreading on the ground around it",
    "TG096": "one small bare dead sapling with a thin dark purplish brown trunk forking into two thin upright bare "
             "branches",
}

# Повтор брака партии 1 (один на семейство, --retry, папка SINGLE_OUT + "_retry"): описание по классике кадра, а не
# по слову (R-007). TG006 - яблоки шли полосами; TG012 - круглый дуб вместо дерева джунглей; TG017 - чёрные ветки,
# у классики светло-серые в инее; TG022 - бледный ствол, у классики бурый; TG026 - гладкая плита вместо комковатой земли
RETRY = {
    "TG006": "one apple tree with a dense rounded crown of dark green leaves, small single round red apples scattered "
             "sparsely and unevenly over the whole crown, and a short dark brown trunk" + GRASS,
    "TG012": "one jungle tree with an irregular ragged crown made of separate clumps of pointed dark green leaves, "
             "thin brown branches visible between the clumps, and a short brown trunk" + GRASS,
    "TG017": "one small bare leafless sapling with a light grey frosted trunk and many thin upright pale grey twigs "
             "coated with white frost, standing on a square patch of white snow",
    "TG022": "one palm tree with a thin curved dark brown trunk and a crown of long bright and dark green fronds"
             + GRASS,
    "TG026": "one bare dead tree with a dark brown trunk and a few thin twisted bare branches, standing on a "
             "square patch of rough lumpy dark reddish brown earth",
    "TG016": "one jungle tree with an irregular ragged crown made of separate clumps of dark green leaves with a few "
             "lighter green tips, and a short dark brown trunk forking low into a few thick roots" + GRASS,
    "TG032": "one jungle tree with an irregular ragged crown made of separate clumps of dark green leaves with a few "
             "lighter green tips, and a short dark purplish brown trunk forking low into a few thick roots",
    "TG042": "one broadleaf tree with a dense solid crown of dark green leaves filling it completely, thick dark "
             "brown branches visible inside the crown, and a straight dark brown trunk" + GRASS,
    # TG034 - голый шест с тремя сучками, у классики ветки парами по всей высоте; TG039 - тонкая палка, у классики
    # толстый ствол с расщепом и ветками у вершины
    "TG034": "one tall bare dead tree with a straight dark grey trunk and many short bare dark grey branches sticking "
             "out in pairs on both sides along the whole height of the trunk, from the bottom to the top",
    "TG039": "one thick fallen dead tree trunk leaning steeply to the left, as thick as a log, pale orange brown wood "
             "with split ends, several bare broken branches forking at the top end, and a small patch of bright "
             "orange sand at its base",
    # партия 2 (папка batch2_retry): TG014 - круглые шары с полом между ними, у классики сплошной полог;
    # TG024 - выдуманные доски поверх куста; TG045 - светло-зелёный, у классики тёмный; TG046 - голый шест без сучков;
    # TG067 - симметричная розетка, у классики низкая крона вбок
    "TG014": "a flat-topped dense mass of large overlapping dark and bright green jungle leaves in horizontal layers, "
             "filling the whole cell from edge to edge like a piece of a continuous jungle canopy",
    "TG024": "one dense jungle bush of large dark and bright green leaves layered in tiers, with a thin twisted "
             "reddish brown trunk visible in the lower middle" + GRASS,
    "TG045": "one broadleaf jungle tree with a wide dense crown of dark green leaves with a few lighter green "
             "highlights, and thin orange brown branches visible through the lower part of the crown",
    "TG046": "one tall bare dead tree with a thin straight dark grey trunk and many short broken bare branch stubs "
             "alternating left and right along the whole height of the trunk",
    "TG067": "one small palm with a very short light brown trunk and a low crown of long drooping bright green fronds "
             "spreading sideways to the left and right, much wider than tall",
}


def module_layouts(M):
    """Главная раскладка модуля (своя sig или самое частое сочетание ровно из его кадров) и проверочные -
    сочетания combos.json своего набора, собранные только из кадров модуля."""
    C = json.load(open(COMBOS, encoding=ENC))[M["kind"]]
    own = [c for c in C if M["set"] in c["sets"] and {e[0] for e in c["full"]} <= set(M["frames"])]
    # главная - самое частое сочетание из ВСЕХ кадров модуля (у пальмы чаще всего один ствол 16 - он проверочный)
    own.sort(key=lambda c: ({e[0] for e in c["full"]} != set(M["frames"]), -c["sets"][M["set"]]))
    out = [{"sig": c["full"], "n": c["sets"][M["set"]]} for c in own]
    if "parts" in M:                     # общая сборка: главная - просто самая частая
        out.sort(key=lambda L: -L["n"])
    elif "sig" in M:
        out.insert(0, {"sig": M["sig"], "n": 0})
    elif not out or {e[0] for e in out[0]["sig"]} != set(M["frames"]):
        raise SystemExit("модуль %s: главной раскладки из кадров %s в %s нет" % (M["set"], M["frames"], COMBOS))
    return out


def load(fams):
    """CL - на семейство: у модулей ели два семейства в одном наборе FOREST."""
    D = json.load(open(LAYOUTS, encoding=ENC))
    for b in sorted({SINGLE_BATCH.get(f, 1) for f in fams if f in SINGLES}):
        D.update(json.load(open(SINGLE_LAYOUTS % b, encoding=ENC)))
    CLs, sets = {}, {}
    for fid in fams:
        if fid in MODULES:
            S = MODULES[fid]["set"]
            CLs[fid] = {S: {"sigs": module_layouts(MODULES[fid])}}
        else:
            S = D[fid]["set"]
            CLs[fid] = {S: {"sigs": [{"sig": L["sig"], "n": L["n"]} for L in D[fid]["layouts"]]}}
        sets[fid] = S
    return D, CLs, sets


def patch(fid, S, CL):
    """Подсказки и пни одного семейства в ядро V1; свободный срез z1 не рисуется (S в tr.DERIVED -> только z0).
    Модуль без среза (крона ели на одном этаже) - DERIVED пуст, срезов нет вовсе."""
    F = FAMILIES.get(fid) or MODULES.get(fid) or dict(main=SINGLES[fid])
    tr.TREE_WHAT.clear()
    tr.CUT_WHAT.clear()
    tr.STUMPS.clear()
    tr.TREE_WHAT[S] = F["main"]
    if "cut0" in F:
        tr.CUT_WHAT[(S, 0)] = F["cut0"]
    for f, what in F.get("stumps", {}).items():
        tr.STUMPS[(S, f)] = what
    tr.DERIVED = (S,) if "cut0" in F else ()


def count_png(d):
    return sum(len([f for f in fs if f.endswith(".png") and (f.startswith("raw_") or f.startswith("stump_"))])
               for _r, _d, fs in os.walk(d)) if os.path.isdir(d) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fam", default=",".join(FAMILIES), help="семейства через запятую (или модули %s)"
                    % ",".join(MODULES))
    ap.add_argument("--out", default=None, help="по умолчанию %s, у модулей %s" % (OUT, MODULE_OUT))
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
    ap.add_argument("--retry", action="store_true", help="повтор брака: описания RETRY, папка batchN_retry")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    fams = [f for f in args.fam.split(",") if f]
    batches = {SINGLE_BATCH.get(f, 1) for f in fams if f in SINGLES or f in RETRY}
    if len(batches) > 1:
        raise SystemExit("одиночные разных партий %s - разными запусками" % sorted(batches))
    batch = batches.pop() if batches else 1
    if args.retry:
        miss = [f for f in fams if f not in RETRY]
        if miss:
            raise SystemExit("--retry: нет описания повтора у %s" % miss)
        SINGLES.update({f: RETRY[f] for f in fams})
        if args.out is None:
            args.out = SINGLE_OUT % batch + "_retry"
    bad = [f for f in fams if f not in FAMILIES and f not in MODULES and f not in SINGLES
           and not (args.assemble and f in COPY_OF)]
    if bad:
        raise SystemExit("неизвестные семейства %s" % bad)
    mods = [f for f in fams if f in MODULES]
    if mods and len(mods) != len(fams):
        raise SystemExit("модули пробы %s и семейства партии - разными запусками" % mods)
    singles = [f for f in fams if f in SINGLES]
    if singles and len(singles) != len(fams):
        raise SystemExit("одиночные %s и семейства партии A - разными запусками" % singles)
    if args.out is None:
        args.out = MODULE_OUT if mods else SINGLE_OUT % batch if singles else OUT
    args.seeds = [int(s) for s in args.seeds.split(",")]
    args.stumps = set()
    D, CLs, sets = load(fams)
    world = tr.mm.World()
    hints = json.load(open(tr.HINTS, encoding=ENC))
    root, left = args.out, args.max_renders
    for fid in fams:                     # своя папка на семейство: JUNGLE живёт и в TG011, и в TG010
        S, CL = sets[fid], CLs[fid]
        args.sets, args.out = [S], os.path.join(root, fid)
        os.makedirs(args.out, exist_ok=True)
        if fid in COPY_OF:               # копия канона: без рендера и без подсказок
            import tree_family_asm
            tree_family_asm.assemble_copy(args, fid, S, world, CL, COPY_OF[fid])
            continue
        patch(fid, S, CL)
        print("== %s %s: раскладок %d, главная на %d мест" % (fid, S, len(CL[S]["sigs"]), CL[S]["sigs"][0]["n"]),
              flush=True)
        if "parts" in MODULES.get(fid, {}):   # общая сборка модулей: рендера и масок нет
            if args.assemble:
                import tree_family_asm
                tree_family_asm.assemble_joint(args, fid, S, world, CL,
                                               [os.path.join(root, p) for p in MODULES[fid]["parts"]])
            continue
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
