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
    # партия 7 (13.10): составные кусты, папоротники, кактусы и дерево, не взятые ни одним путём (batch7_pick.tsv,
    # раскладки batch7_layouts.json); не рисуются CP002 (травяной откос ISLANDURBAN2 - рельеф) и CP009 (поле травы
    # SAVANNABEACH, 1 место). Земля - только где она есть у классики (CP003 трава, CP001 оранжевый песок)
    "CP001": dict(
        main="one cactus clump of several tall upright green ribbed cactus stems of different heights with small "
             "yellow flower buds at their tips, standing on a small patch of orange sand",
        cut0="the lower part of one cactus clump whose upper part has been removed: several green ribbed cactus "
             "stems rise directly out of the base that is already drawn at the bottom, each with a flat cut top; "
             "they reach down to that base without a gap, one single clump only"),
    "CP003": dict(
        main="one young jungle plant of a few long arching broad bright and dark green leaves rising from the "
             "ground and bending to the right, growing out of flat green grass covering the ground"),
    "CP004": dict(
        main="one tall tropical tree with a thick pinkish grey brown trunk curving to the left near the base and "
             "flaring into roots, and a wide crown of drooping dark green fern-like fronds",
        cut0="the lower part of one thick pinkish grey brown tree trunk whose crown has been removed: the trunk "
             "rises directly out of the flared roots that are already drawn at the bottom, with a flat sawn top; "
             "it reaches down to those roots without a gap, one single trunk only"),
    "CP005": dict(
        main="one low fern with a rosette of broad bright green fronds with lighter green edges spreading in all "
             "directions, dark green at the centre"),
    "CP006": dict(
        main="one large dense cube-shaped bush of small dark and medium green leaves with one red flower on its "
             "front side",
        cut0="the lower part of one dense bush of small dark and medium green leaves whose upper part has been cut "
             "away: the leaves rise directly out of the leaves that are already drawn at the bottom, with a flat "
             "cut top showing the dense leaves from above; it reaches down to them without a gap, one single bush "
             "only"),
    "CP007": dict(
        main="one fan of a few long narrow bright green fern fronds with lighter green tips, spreading upward and "
             "sideways from one point"),
    "CP008": dict(
        main="one large dense rounded bush of black and very dark grey leaves with a few tiny red berries",
        cut0="the lower part of one dense bush of black and very dark grey leaves whose upper part has been cut "
             "away: the leaves rise directly out of the leaves that are already drawn at the bottom, with a flat "
             "cut top showing the dense leaves from above; it reaches down to them without a gap, one single bush "
             "only"),
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
# партия 4 (13.10): остаток одиночных; газона GRASS нет ни у одного - вставленный газон специалист браковал в
# партии 2 (TG047, TG065, TG086); TG098 CARGO1:50 по классике светильник, не растение - не рисуется
SINGLE_BATCH.update({f: 4 for f in ("TG020", "TG028", "TG056", "TG070", "TG074", "TG088", "TG093")})
# партия 5 (13.10): кусты, папоротники, кактусы - основы census/trees/trees.tsv по охвату (batch5_pick.tsv, BUnnn);
# не рисуются BU005, BU019, BU021 (край рельефа с травой, не куст), BU037 (GOTHIC:9 - ряд изгороди без одиночной
# раскладки), BU040 и BU050 (обрывки в несколько пикселей); земля в подсказке - только где она есть у классики
SINGLE_BATCH.update({"BU%03d" % i: 5 for i in range(1, 51) if i not in (5, 19, 21, 37, 40, 50)})
# партия 6 (13.10): остаток одиночных census/trees/trees.tsv прочих видов (деревья, лианы, бревна, пни, тростник,
# изгородь) и 4 перекраски, чья основа на картах не стоит (batch6_pick.tsv, OTnnn); не рисуются: куб изгороди
# XB3BITZ3:17 и ряды COMDECOR 31/32 (замощение, не предмет), куски кроны JUNGLE 70/72/77/79 (составное), блоки
# земли и края рельефа (OT009, OT024, OT047, OT058-OT061, OT064), гидрант ROADS:20, стеллаж MILWARE:14, навес
# LINERSHIPA:89, VR CULTIVAT_VR:9 (R-314), обрывки OT037 и OT045
SINGLE_BATCH.update({"OT%03d" % i: 6 for i in (2, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 25, 26, 27, 28,
                                               29, 30, 31, 32, 33, 34, 35, 36, 38, 39, 40, 41, 44, 48, 49, 50, 51,
                                               52, 53, 54, 55, 56, 57, 62, 63, 65, 66)})
# партия 7 (13.10): составные CP (FAMILIES, папка batch7) и три одиночных другого вида из batch5_recolors
SINGLE_BATCH.update({f: 7 for f in ("CP001", "CP003", "CP004", "CP005", "CP006", "CP007", "CP008",
                                    "OT067", "OT068", "OT069")})
GROUND = ", growing out of flat green grass covering the ground"
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
    # партия 4
    "TG020": "one small mutant shrub, many thin dark blue grey stems spreading outward from a dark root in all "
             "directions, every stem ending in small glowing pink and red buds",
    "TG028": "one alien plant with a short dark green stem and broad pointed dark and bright green leaves spreading "
             "outward like a star, a thin yellow stalk rising straight up from the centre",
    "TG056": "one small bare dead tree with a thin twisted dark grey trunk and a few short bare twigs, a round ball "
             "of rust orange dry leaves at the very top, standing on a square patch of white snow",
    "TG070": "one long fallen log lying on the ground, reddish brown bark, a thick lumpy layer of white snow along "
             "its top, the cut end showing light wood",
    "TG074": "a low heap of fallen broken dry brown branches and torn bark lying flat on the ground",
    "TG088": "a few fallen broken grey and brown branches lying crossed on the ground, with white snow on their upper "
             "surfaces",
    "TG093": "one small palm with a thin pinkish brown trunk leaning from the lower right up to the upper left and a "
             "crown of long drooping dark green fronds hanging down",
    # партия 5
    "BU001": "a low dense rectangular bush filling the cell, many small dark and bright green leaves dotted with "
             "small red and light blue flowers",
    "BU002": "a low dry thorny bush of many thin bare dark purplish grey twigs",
    "BU003": "a low dense clump of long thin green leaves filling the cell, with many orange lily flowers on top",
    "BU004": "one small low plant of a few broad dark teal green leaves",
    "BU006": "one tall dense bush of dark green leaves filling the cell, dotted with small dark red berries",
    "BU007": "one low clump of thin bright orange and yellow spikes radiating outward like a sea coral",
    "BU008": "a low wide dense bush of dark green leaves, two rounded mounds side by side",
    "BU009": "one fern with long arching bright green fronds and a few small dark blue berries at the centre" + GROUND,
    "BU010": "a low dry thorny bush of many thin bare black and dark purple twigs",
    "BU011": "one jungle plant with long arching dark green leaves and four large dark blue flowers in the middle"
             + GROUND,
    "BU012": "one tall dense bush of layered dark and bright green leaves, a thin dark trunk visible at the bottom",
    "BU013": "a low wide tangle of thin dry rust orange and dark brown twigs",
    "BU014": "a low wide tangle of thin dark brown twigs heavily covered with white snow",
    "BU015": "one small low plant with a few broad bright green leaves" + GROUND,
    "BU016": "a low flat rectangular hedge of dark green leaves with small red berries, a small grey rock at its left "
             "end",
    "BU017": "one agave plant with a rosette of long broad pointed bright green leaves" + GROUND,
    "BU018": "a low pyramid shaped mound of dense green and brown leaves with a few small red berries",
    "BU020": "a low small dense bush of dark green leaves, two rounded clumps side by side",
    "BU022": "one fern with arching dark green fronds in a grey metal pot, a few small dark teal and cyan spots on "
             "the fronds",
    "BU023": "a low rectangular block of dense dark green leaves with small red berries, on top of a low grey stone "
             "wall base",
    "BU024": "a low cluster of small bright crimson red flower heads with dark red shadows, close to the ground",
    "BU025": "one tall jungle plant with a few long broad leaning light green leaves" + GROUND,
    "BU026": "a low rectangular block of dense green and brown leaves with small red berries, on top of a low grey "
             "stone wall base",
    "BU027": "a low rectangular grey stone wall base with a sparse row of small green plants and dark red stems on "
             "top",
    "BU028": "one large fern with many long bright light green fronds spreading wide",
    "BU029": "one tall narrow column of many bright yellow and orange round blossoms with dark red centres and a few "
             "green leaves",
    "BU030": "one tall green saguaro cactus with two short arms, small yellow and orange flowers on the tips, a little "
             "orange soil at its base",
    "BU031": "one small low round bush of dark teal green leaves with a short thin brown stem",
    "BU032": "one large jungle plant with long bright green leaves and one tall red flower spike rising from the "
             "centre",
    "BU033": "a low wide tangle of thin dark red brown twigs heavily covered with white snow",
    "BU034": "a low wide dense bush of very dark green broad leaves, two rounded mounds side by side",
    "BU035": "one prickly pear cactus of a few flat green pads with small red fruits on the edges, a little orange "
             "soil at its base",
    "BU036": "two tall narrow columns of many bright yellow and orange round blossoms with dark red centres on thin "
             "green stems",
    "BU038": "one dense tropical bush of bright green leaves on twisted orange brown branches, with small yellow and "
             "red berries",
    "BU039": "a low flat patch of short green grass tufts on grey gravel",
    "BU041": "one small low plant of a few curling bright green leaves with a dark red centre",
    "BU042": "one tall plant of a few long upright broad light green leaves",
    "BU043": "one low jungle plant with a few broad dark green leaves and pinkish grey cupped leaf tips, growing out "
             "of flat dark green grass covering the ground",
    "BU044": "a tall narrow column densely overgrown with small green leaves over dark grey and brownish purple stone",
    "BU045": "one strange jungle plant with a thick curved pinkish grey stalk bending to the left and several dark and "
             "bright green leaves",
    "BU046": "one large dry plant of many long thin pinkish grey brown leaves radiating from a dark centre",
    "BU047": "one low clump of tall thin dark green leaves standing in shallow dark teal water edged with green grass",
    "BU048": "one dark purplish black plant with long pointed leaves radiating from the centre, on flat pink sand",
    "BU049": "one black plant with long pointed leaves with dark blue violet edges radiating from the centre, on flat "
             "dark ground",
    "OT002": "one apple tree with a dense rounded crown of dark green leaves dotted with small red apples, a short "
             "thin dark purplish brown trunk and a small round dark green shadow of grass at its foot",
    "OT010": "one dead thorny bush of many thin twisted bare branches, very dark purplish black with a few dark red "
             "brown tints, no leaves",
    "OT011": "one bare dead tree with a dark grey trunk and many thin bare dark grey branches, a few dark red streaks "
             "on the bark, no leaves",
    "OT012": "a loose net of thin bright green vines with small leaves hanging down in separate strands",
    "OT013": "a dense net of thin green vines with small dark and bright green leaves hanging down in many strands",
    "OT014": "several thin bright green vines hanging straight down in long separate strands",
    "OT015": "one small low tuft of thin green creeping vine with tiny leaves",
    "OT016": "a few thick strands of glossy bright green leafy vines hanging straight down, dark gaps between them",
    "OT017": "one tall thin bare dead tree with a straight dark grey trunk and short bare dark grey branches, a few "
             "dark red streaks on the bark, no leaves",
    "OT018": "a few thin green creeping vines with tiny leaves trailing diagonally down to the left",
    "OT019": "a curtain of thin green vines with small leaves hanging down from a horizontal strand along the top",
    "OT020": "one small dark green palm plant with broad pointed fronds spreading in all directions and one pale "
             "green shoot rising from the centre",
    "OT021": "one large broken hollow brown tree stump with a jagged top and a dark hollow in its side, thick "
             "spreading roots, dark green leafy plants around its base" + GRASS,
    "OT022": "one tall broken hollow brown tree stump split into two jagged prongs at the top, dark holes in its "
             "bark, dark green leafy plants around its base" + GRASS,
    "OT025": "one short fallen hollow brown log lying on its side with dark open ends",
    "OT026": "one solid cube of trimmed dark green hedge with a few small pale pink and orange flowers on its sides",
    "OT027": "one jungle plant with long arching green leaves and a few small blue flowers at the centre, standing "
             "on a square patch of dark brown earth scattered with small green and reddish leaves",
    "OT028": "a curtain of glossy bright green leafy vines hanging down in many short strands from a horizontal "
             "strand along the top, a few dark red buds",
    "OT029": "a small pile of dark brown logs stacked in two layers with light tan cut ends",
    "OT030": "one small tuft of thin green creeping vine with tiny leaves spreading diagonally",
    "OT031": "a square patch of brown mud densely covered with short green reeds and pale grey pink dry stalks",
    "OT032": "one short fallen hollow brown log lying on its side with a dark open end and a dark hole in its side",
    "OT033": "one short fallen hollow brown log lying on its side with dark open ends, white snow lying on top of it",
    "OT034": "one short fallen hollow brown log lying on its side with a dark open end, a small streak of pale grey "
             "ash beside it",
    "OT035": "one broken tree trunk lying fallen diagonally with a split light brown end and two thick bare branches "
             "pointing up, small dark green fir shrubs dusted with snow around it, on a square patch of white snow "
             "strewn with dark red needles",
    "OT036": "one small clump of bright green leafy vine with glossy leaves",
    "OT038": "a square patch of brown mud sparsely covered with short green reeds and pale grey pink dry stalks",
    "OT039": "one short fallen hollow reddish brown log lying on its side with broken branch stubs and a dark open "
             "end",
    "OT040": "one fallen light brown log lying diagonally with rough bark and dark hollow openings",
    "OT041": "one small broken charred black and dark purplish brown tree stump with spreading roots",
    "OT044": "one long fallen brown log lying horizontally with rough cracked bark, dark knot holes and splintered "
             "ends",
    "OT048": "one broken brown tree stump with splintered wood split and spread low, on a square patch of pale grey "
             "gravel",
    "OT049": "one cattail plant with a bunch of long pale green leaves and three tall brown seed heads on thin "
             "stalks",
    "OT050": "one dead dark grey tree with a short thick trunk and twisted bare dark branches spreading wide, "
             "standing on a square patch of dark green moss",
    "OT051": "one broken brown log lying on the ground with a split end and a short broken branch",
    "OT052": "one large dense round bush of bright and dark green leaves filling the cell",
    "OT053": "a hanging tangle of thin glowing purple and violet branching vines",
    "OT054": "one thin upright brown stalk wrapped in pink and purple vines, thin roots spreading at its base",
    "OT055": "one thin brown stalk wrapped in a pink vine, topped by a glowing pale yellow green cup shaped flower "
             "with small red edges",
    "OT056": "one burnt black tree stump leaning to the right, standing on a small round patch of scorched orange "
             "sand",
    "OT057": "one fallen broken brown tree stump with a thick split trunk and a bare broken branch, lying on a square "
             "patch of pale grey gravel",
    "OT062": "one tall plant with long pointed dark green leaves spreading in four directions from a thin green "
             "stalk, small yellow green buds at the leaf tips",
    "OT063": "one dense tall jungle bush of bright light green leaves with dark red and orange berries and small "
             "orange flowers in its lower part",
    "OT065": "one solid block of trimmed dark green hedge with a few dark purple flower petals on top and two small "
             "orange flowers on its side",
    "OT066": "one dark jungle plant of large dark blue violet and black leaves curling upward, growing out of a "
             "square patch of black earth",
    "OT067": "a small flat scattered heap of dry black and dark grey broken twigs lying on the ground",
    "OT068": "one small green ribbed cactus with two short upright arms and a few red flowers on top, standing on "
             "a small patch of bright orange sand",
    "OT069": "one jungle plant with several thick bare pale pinkish grey stems spreading sideways and broad dark "
             "green leaves at its base" + GRASS,
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
    # партия 5 (папка batch5_retry, вердикт специалиста 14.10): BU001 - густой разноцветный крап, зелень теряется;
    # BU006 - правильный конус; BU008/BU034 - два стриженых шара; BU012 - круглая изгородь вместо саженца; BU013 -
    # тёмный клубок вместо оранжевой массы; BU014/BU033 - пятнистый пиксельный снег; BU016/BU023/BU026 - клумбы
    # с кирпичной кладкой вместо камней; BU018 - правильная пирамида; BU027 - блок с палками; BU029 - колонка
    # плоских розеток; BU039 - плоская подложка; BU043 - тёмное пятно с грибом; BU044 - прямоугольная колонна;
    # BU045 - розовые завитки главным; BU046 - густая колючая розетка; BU047 - пропала вода
    "BU001": "a low flat bed of dense small green leaves filling the cell, mostly green, with only about ten tiny red "
             "and light blue flowers here and there",
    "BU006": "one tall uneven ragged bush of dark green leaves with a lumpy irregular outline, many small dark red "
             "berries all over it",
    "BU008": "a low wide sprawling bush of dark green leaves with a ragged outline, leafy branches reaching out to "
             "the sides, the top dipping slightly in the middle",
    "BU034": "a low wide sprawling bush of very dark green broad pointed leaves with a ragged outline, leaves hanging "
             "outward over the sides, the top dipping slightly in the middle",
    "BU012": "one tall narrow jungle sapling with a thin dark brown trunk and a few uneven tiers of dark and bright "
             "green leaves on short branches, the trunk visible between the tiers",
    "BU013": "a low wide dense mass of dry twigs and dead leaves in bright rust orange and reddish brown, the orange "
             "filling the whole mass",
    "BU014": "a low wide tangle of thin dark brown twigs, every twig coated in smooth solid white snow and frost, "
             "mostly white with thin dark gaps",
    "BU033": "a low wide tangle of thin dark red brown twigs, every twig coated in smooth solid white and light grey "
             "snow, mostly white with thin dark red lines",
    "BU016": "a low flat uneven carpet of dense dark green leaves with many small red berries lying on the ground, "
             "one small rough grey rock at its left end, soft ragged edges",
    "BU023": "a dense mound of dark green leaves with small red berries growing over a few rough natural grey "
             "boulders, uneven rubble stones, the leaves hanging over the edges of the stones",
    "BU026": "a dense mound of green and brown leaves with small red berries growing over a few rough natural grey "
             "boulders, uneven rubble stones, the leaves hanging over the edges of the stones",
    "BU018": "a low uneven rounded lumpy mound of green and brown leaves with a few small red berries",
    "BU027": "a ledge of rough natural grey stones, its top completely covered by a dense layer of green plants with "
             "dark red stems",
    "BU029": "one tall narrow flower spike densely covered with small round fluffy yellow and orange blossom clusters "
             "of different sizes like a bunch of grapes, dark red shadows between them",
    "BU039": "one low dense clump of upright green grass and leafy weeds on a small patch of grey gravel",
    "BU043": "one low jungle plant with a few broad dark green leaves spread apart and five pale pinkish grey curled "
             "tips at the ends of the leaves, growing out of flat dark green grass covering the ground",
    "BU044": "one tall upright oval bush with a rounded top, small green leaves mixed with dark brownish purple and "
             "grey dry leaves",
    "BU045": "one jungle plant made mostly of dark and bright green leaves, with one thin pinkish grey bare branch "
             "curving up to the left",
    "BU046": "one dry dead plant, about eight thick bare pinkish grey brown branches spreading out from a dark centre, "
             "sparse with wide gaps between them",
    "BU047": "a square patch of shallow dark teal water edged with grass, a low clump of thin dark green reeds "
             "standing in the water at one side, the water clearly visible",
    # партия 6 (папка batch6_retry, вердикт 14.10): OT012 - нитки вместо лиан, у классики плети в два пикселя
    "OT012": "a loose net of thick hanging jungle vines, every vine a thick rope densely covered with overlapping "
             "small green and dark green leaves, the vines branching and hanging down in separate strands with "
             "wide dark gaps between them",
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
    for b in sorted({SINGLE_BATCH.get(f, 1) for f in fams if f in SINGLES or f in SINGLE_BATCH}):
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
    ap.add_argument("--fam", default=",".join(f for f in FAMILIES if f not in SINGLE_BATCH), help="семейства через запятую (или модули %s)"
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
    batches = {SINGLE_BATCH.get(f, 1) for f in fams if f in SINGLES or f in RETRY or f in SINGLE_BATCH}
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
        # составные партий конвейера (CP, партия 7) - в папку своей партии, партия A - в OUT
        args.out = MODULE_OUT if mods else SINGLE_OUT % batch if singles or batch != 1 else OUT
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
