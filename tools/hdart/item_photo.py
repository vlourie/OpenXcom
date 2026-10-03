#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот этапа 1 HD-BIGOBS (ТЗ docs/research/inventory-items-hd.md §8, §10): мастера M-01..M-20 предметной съёмкой.

Цикл рендера - struct_probe.Render как есть (прошёл PHOTO_STRUCT_ACCEPTANCE_V1, вариант C): эскиз struct_guide
первой картинкой, оригинал bicubic второй, Qwen-Image-2.1 по замку (RENDER_V1: 40 шагов, cfg 4, 1 Мп),
проверки photo_accept. Своё здесь:
  * промпт ITEM - предметная съёмка ортографически в ориентации оригинала, а не изометрия obj_photo.PHOTO
    (ТЗ §8 п.4: новый generator_rev, утверждается заново; obj_photo.py и photo_render.py не правятся);
  * вход - кадр BIGOBS 32x48 из cards/originals (индексы, 0 прозрачный - как движок, R-043);
  * подготовка по контракту v4 (docs/research/inventory-items-redraw-contract-v4.md §3): ответ модели на холст
    кропа x4 ОДНИМ известным преобразованием - обратным тому, которым вход растянут под размер рендера
    (struct_probe.run_multi), без подгонки по содержимому; вырезка cut_fixed - как photo_base.cut, но без fit
    (правка пропорций до 1.3) и без fit_shape; кадр k=4 - вырезка на месте оригинала x4, без уменьшения,
    сдвига и центрирования. Размер и место силуэта МОДЕЛИ против оригинала x4 - замер (model_geometry):
    больше 3 % по оси или край не на месте - REWORK, а не подгонка. Альфа по-прежнему из силуэта оригинала
    (R-089): где модель не дорисовала - подложка в теле, это видно на листе и в core_panel.
  * мастера BLOCKED_GEOMETRY (census/items/geometry/geometry.tsv, item_geometry.py) без записанного решения
    Vitali (census/items/geometry/decisions.tsv: мастер<TAB>решение) не рендерятся; --recut готовых - можно.
  * фото-эталон (REFS, решение 03.10): у мастера с фото настоящей вещи третья картинка - фото, габарит на
    габарит оригинала (ref_input), и текст ролей: фото - устройство и материалы, эскиз - размер и места частей,
    оригинал - цветовые зоны; тон к оригиналу выключен (ITEM_TONE 0) - пиксельный кадр не задаёт яркость.
Описания - census/items/cards/masters.md, принятые для пилота 04.10; здесь - их перевод для модели (WHAT).
M-06 не утверждён (стволы) - в пилот не идёт. M-19 - шаг 1: этикетка пустая, SOY - отдельным шагом.

Модель - только через очередь и под render_chunks.py (не больше 4 рендеров на процесс):
    py -3.13 tools/gpuq.py add --name items_pilot_v1 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
        --out art/items/pilot-v1 --max-renders 4 -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/item_photo.py
Без модели: --dry-run (план, эскизы, промпты, generator_rev), --recut (готовые raw; нет ответа - стоп, R-127).
Выход: <out>/pack/BIGOBS.PCK/<кадр>.<ТИП>.png (k=4, 128x192), <out>/meta/<ТИП>.json, <out>/sheet.png.
--out другой папки - чтобы не затереть прежний пилот (pilot-v1 - RECHECK_REQUIRED, лист и кадры прежней укладки).
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))
# --engine edit: веса только из кэша. Флаг ставится ДО импорта diffusers - он читает HF_HUB_OFFLINE один раз при
# импорте, а huggingface_hub - при каждом запросе: поставленный позже, флаг роняет загрузку шардов (OfflineModeIsEnabled)
if "edit" in [b for a, b in zip(sys.argv, sys.argv[1:]) if a == "--engine"]:
    os.environ["HF_HUB_OFFLINE"] = "1"

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw        # noqa: E402

import asset_rev as ar                  # noqa: E402
import item_asset_check as iac          # noqa: E402
import photo_base as pb                 # noqa: E402
import photo_render as pr               # noqa: E402
import struct_guide as sg               # noqa: E402
import struct_probe as sp               # noqa: E402

ENC = "utf-8-sig"
OUT = "art/items/pilot-v1"
CARDS = "census/items/cards"
GEOMETRY = "census/items/geometry/geometry.tsv"
DECISIONS = "census/items/geometry/decisions.tsv"
K = 4
TOL = 0.03                      # контракт v4 §3: размер по оси 100 % +-3 %
EDGE_MIN = K                    # край силуэта на месте: до пикселя базы (точность лесенки оригинала) ...
EDGE_TOL = 0.015                # ... или до половины допуска размера
CRUMB = 4 * K * K               # кусок силуэта модели меньше 4 пикселей базы - крошка матта, не часть предмета
PAD = pr.RENDER_V1["pad"]
SEED0 = 4100
ITEM_TONE = 0.0                 # тон к оригиналу: 0 - пиксельный кадр задаёт размещение, а не яркость поверхности
                                # (03.10: photo_base.TONE 0.7 гасил ответ модели - яркость -43 %, разброс -34 %)
HOLE_SD = 1.2                   # отверстие ответа: разброс яркости как у подложки (снаружи медиана 0.5, p95 0.7;
HOLE_DS = 16.0                  # серый металл цвета подложки - 4.2-4.7) и близко к ней с тенью (снаружи p95 9)
HOLE_EDGE = 22.0                # кромка отверстия - до этого расстояния до подложки, на HOLE_GROW пикселей ответа
HOLE_GROW = 3

ITEM = ("<image1> is a clean shape sketch of {what}, shown on a flat preview panel of colour RGB({r}, {g}, {b}). "
        "The panel is background, not part of the object. "
        "Make a photorealistic studio product photograph of this same real object: {what}. "
        "Orthographic view straight at the object, no perspective, the object in exactly the orientation, "
        "position and size of <image1>. Keep the silhouette, the proportions and the colour areas of <image1>. "
        "Real materials with natural surface detail and light wear, soft light from the upper left, sharp focus. "
        "Output one isolated object on the same flat panel. No hands, no straps, no other objects, "
        "no shadow outside the object, no frame, no text, no letters, no logos.")
NEGATIVE_EXTRA = ", hand, fingers, letters, logo, label text, perspective"

# Фото-эталон (решение 03.10, «75 % фото / 25 % описания» как разделение ролей): фото настоящей вещи нужной
# комплектации - устройство, объём, фактура, обработка, резкость; эскиз и оригинал - размер, ракурс, силуэт,
# места частей, цветовые зоны; описание - уточнения и запреты. Фото кладётся третьей картинкой на ту же подложку,
# по габариту оригинала (ref_input). Мастер без эталона рендерится как прежде.
REF_AK = ("<image3> is a studio photograph of the real object, already laid over the outline of <image1>: it is "
            "the main source for the construction and the material quality. Take from <image3> the volume, the "
            "shape and joints of every part, the wood grain, the metal finish, the sharpness and the reflections. "
            "Take from <image1> only the size, the view, the outline and the placement of the parts; <image2> "
            "gives only the colour areas. Keep the full size of <image1>: the muzzle at the top, the front sight, "
            "the edge of the magazine and the butt plate exactly where <image1> has them; the receiver, the "
            "barrel and the stock not thinner than <image1>. Do not copy the pixel steps or the simplified flat "
            "surfaces of <image2>. The wood is a saturated red-brown with clear grain and relief. The metal is "
            "solid and crisply drawn, with visible edges, joints and controlled highlights. The skeleton stock "
            "must read clearly against a dark background. No overall darkening, no blur, no cropped parts.")
REF_NEGATIVE = ", pixelated, stair-stepped edges, blurry, dull, underexposed, thin slim object, flat shading"
# v6 (рецензия 03.10 к v5): второй картинкой вместо размытого пиксельного оригинала - карта частей (part_map):
# гладкие зоны дерева и стали плоскими цветами, контур и контрольные точки частей, которые в v5 съехали
# (мушка, магазин, затыльник); материалы - по частям: цевьё как есть, рукоять - тёплое дерево с волокном и
# умеренным лаком (одно слово walnut делает дерево слишком тёмным), сталь - тёмные плоскости, светлые кромки
REF_AK_V6 = ("<image3> is a studio photograph of the real object, already laid over the outline of <image1>: it is "
             "the main source for the construction and the material quality. Take from <image3> the volume, the "
             "shape and joints of every part, the wood grain, the metal finish, the sharpness and the reflections. "
             "Take from <image1> the size, the view, the outline and the placement of the parts. <image2> is a part "
             "map of the same object: the red-brown zones are wood, the dark grey zones are steel, the thin dark "
             "line is the exact outline, and the small yellow dots are control points - they are guides only and "
             "are never drawn. The top of the muzzle, the left tip of the front sight, the tip and the lower right "
             "corner of the magazine, the end of the pistol grip and the two lower corners of the butt plate lie "
             "exactly on these dots; do not shift, shorten or lengthen any part. The handguard keeps the wood "
             "grain and the grooves of <image3>. The pistol grip is real wood, a warm red-brown, lighter than "
             "walnut and not bright red, with clearly visible lengthwise wood grain and a moderate satin lacquer "
             "sheen with one soft highlight; it must not look like plastic. The steel: the main flat surfaces are "
             "dark gunmetal, the edges and corners are worn bright, rounded parts carry small local reflections; "
             "no uniform light grey metal. The two struts of the skeleton stock are solid dark steel, thick enough "
             "to read at a small size, and the gap between them is fully open, the panel shows through it. "
             "Do not copy the pixel steps of any picture. No overall darkening, no blur, no cropped parts.")
REF_NEGATIVE_V6 = (REF_NEGATIVE + ", red plastic, glossy plastic grip, uniform light grey metal, yellow dots, "
                   "markers, outline drawn on the object")
# контрольные точки части - (x, y) в пикселях кадра k=1 от левого верхнего угла габарита оригинала, по краям
# пикселей (дамп маски BIGOBS 1168, габарит x 0-18 y 1-46): дуло, кончик мушки, кончик и нижний правый угол
# магазина, конец рукояти, нижние углы затыльника
CTRL_AK = ((4, 0), (0, 1.5), (18, 18), (19, 23), (15, 36), (2, 46), (10, 45))
PART_WOOD = (128, 62, 38)       # карта частей: тёплый красно-коричневый, не цвет пиксельного оригинала
PART_STEEL = (54, 56, 60)
# v7 (рецензия 03.10 к v6: размеры не те, жёлтые точки перенесены в ответ - R-204): части фото-эталона
# переставлены на места частей оригинала заранее (ref_parts_input), каждая - одним масштабом по обеим осям и
# поворотом; меток во входах модели нет, контрольные точки - только на проверочном листе (ref_check_sheet)
REF_AK_V7 = ("<image3> is a studio photograph of the real object whose parts are already arranged in their final "
             "places: it is the main source for the construction and the material quality. Keep the position, the "
             "size and the angle of the front sight, the magazine, the pistol grip, the two stock struts and the "
             "butt plate exactly as they are in <image3>; do not move, shorten, lengthen or straighten any part. "
             "Take from <image3> the volume, the joints, the wood grain, the metal finish, the sharpness and the "
             "reflections, and join the parts cleanly where they meet. <image1> gives the outline and the view. "
             "<image2> is a part map of the same object: the red-brown zones are wood, the dark grey zones are "
             "steel. The handguard keeps the wood grain and the grooves of <image3>. The pistol grip is real "
             "wood, a warm red-brown, lighter than walnut and not bright red, with clearly visible lengthwise "
             "wood grain and a moderate satin lacquer sheen with one soft highlight; it must not look like "
             "plastic. The steel: the main flat surfaces are dark gunmetal, the edges and corners are worn bright, "
             "rounded parts carry small local reflections; no uniform light grey metal. The two struts and the "
             "butt plate of the skeleton stock keep exactly the thickness they have in <image3>, and read clearly "
             "through light and shade: a bright worn highlight along one edge, a deep shadow along the other, "
             "crisp edges; the gap between the struts is fully open, the panel shows through it. "
             "Do not copy the pixel steps of any picture. No overall darkening, no blur, no cropped parts.")
# части M-01 (фото art/items/refs/M-01.png, пиксели фото; места - пиксели k=1 от угла габарита оригинала, по
# дампу маски BIGOBS 1168): keep - прямоугольник части на фото (тело - без магазина и рукояти); тело - масштаб
# по высоте дуло..хвост коробки (span: фото y0, y1 -> ряд), мушка - по ширине дуло..левое ухо (x_to), затыльник -
# по двум углам; магазин и рукоять - подбор масштаба и угла по силуэту оригинала в зоне (fit_part), корень не
# правее cap_x (стык с коробкой); стойки - от хвоста коробки до затыльника, середина вырезана (rod_part)
AK_PARTS = {
    "body": {"keep": (0, 100, 9999, 1333), "P": (262.5, 10), "Q": (4, 0), "span": (10, 1330, 35)},
    "front": {"keep": (0, 0, 9999, 106), "P": (262.5, 10), "Q": (4, 0), "x_to": (140, 0)},
    "magazine": {"keep": (355, 600, 9999, 983), "P": (355, 905), "zone": (8.5, -99, 99, 28), "cap_x": 6.2,
                 "cap_r": 19.0,     # правый край - не дальше габарита оригинала (допуск размера)
                 "pts": (((664, 677), CTRL_AK[2]), ((773, 762), CTRL_AK[3])),     # кончик и угол торца
                 # торец под оригинал (рецензия 03.10: кончик эталона v7 в 1.66 пикс базы от края): изгиб конца
                 # магазина, середина и корень стоят (anchors - верх и низ магазина у коробки и посередине)
                 "bend": {"sigma": 2.5, "anchors": ((7, 22), (7, 27), (11, 21.5), (11, 25.5))}},
    "grip": {"keep": (353, 1128, 9999, 1345), "P": (353, 1200), "zone": (8, 30, 99, 38), "cap_x": 6.2,
             "pts": (((580, 1322), CTRL_AK[4]),)},                                 # нижний угол торца рукояти
    "w_pts": 0.05,                  # цена пикселя базы между точкой части и контрольной точкой - в долях IoU
    "butt": {"keep": (0, 1706, 9999, 9999), "P": (193, 1768), "Q": (2, 46), "P2": (416, 1768), "Q2": (10, 45)},
    "struts": (((0, 1328, 290, 1706), (248.5, 1330), (242, 1706), 4.0),     # левая: ось фото, низ - x оригинала
               ((266, 1328, 9999, 1706), (333, 1335), (366, 1706), 7.0)),
    "fit_scale": (0.85, 1.6, 0.03), "fit_rot": (-24, 24, 2),        # от масштаба тела; градусы
    "stock_light": 1.3,             # светотень стоек и затыльника: отклонение от средней яркости части x1.3
}
REFS = {"M-01": ("art/items/refs/M-01.png", REF_AK_V7, CTRL_AK, AK_PARTS)}  # art/items/refs/README.txt - откуда фото

# --engine edit (решение 03.10 после v7: Qwen-2.1 сужает и вытягивает вещь при любом входе): Qwen-Image-Edit-2511 +
# Lightning ПРАВИТ собранный эталон (ref_parts_input), одна картинка на входе (R-205), свободной генерации нет.
# Задание - швы, свет, материалы; геометрия эталона - закон. LoRA Anime-to-Photoreal не грузится: вход уже фото.
# Веса - только из кэша (HF_HUB_OFFLINE), снимок main сверяется с EDIT_MODEL_REV (R-145)
EDIT_RUN = {"steps": 8, "cfg": 1.0, "mp": pr.RENDER_V1["mp"], "lora": 0.0, "lightning": "8steps-V1.0-bf16"}
EDIT_MODEL_REV = "6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9"
EDIT_ITEM = ("<image1> is a studio photograph of {what}, assembled from separate photos of its parts, on a flat "
             "panel of colour RGB({r}, {g}, {b}). Retouch it into one seamless real product photograph of the same "
             "object. Fix the seams where the parts were joined, make the lighting consistent over the whole object "
             "with soft light from the upper left, and improve the materials: the wood is a warm red-brown, lighter "
             "than walnut, with clear lengthwise grain and a moderate satin lacquer sheen; the steel is dark "
             "gunmetal with worn bright edges and small local reflections, crisp and solid. Do not change the "
             "geometry: keep exactly the outline, the size, the position and the thickness of every part - the "
             "muzzle, the front sight, the magazine, the pistol grip, the two stock struts and the butt plate stay "
             "exactly where they are in <image1>; do not move, bend, shorten, lengthen, thin or straighten "
             "anything, add nothing and remove nothing. Make the two struts and the butt plate of the skeleton "
             "stock read clearly through light and shade: a bright worn highlight along one edge, a deep shadow "
             "along the other, crisp edges. The gap between the struts stays fully open, the panel shows through "
             "it. Keep the flat plain panel exactly as it is: no shadow on it, no other objects, no frame, no text.")
EDIT_WHAT = {"M-01": "an old worn Kalashnikov-pattern assault rifle with a metal skeleton stock, standing vertically "
                     "with the muzzle at the top"}

# (мастер, тип, кадр, описание для модели) - по masters.md; M-06 нет до решения о стволах
WHAT = [
    ("M-01", "STR_RIFLE_AK", 1168,
     "an old worn Kalashnikov-pattern assault rifle standing vertically with the muzzle at the top and the front "
     "sight sticking out to the left near the muzzle, blued steel rubbed to grey in places, a bright red-brown "
     "wooden handguard with crosswise grooves under the barrel, a curved banana magazine and a bright red-brown "
     "wooden pistol grip sticking out to the right in the lower half; at the bottom a METAL skeleton stock: two "
     "parallel thin steel struts with an open gap between them, ending in a wide flat steel butt plate at the very "
     "bottom, exactly the outline of <image1>; the full width and height of <image1>, not slimmer; no wooden "
     "stock, no solid stock, no scope, no rails, no suppressor, no modern plastic"),
    ("M-02", "STR_RIFLE_AK_CLIP", 1169,
     "a curved steel 30-round rifle magazine lying horizontally, dark blued metal with stiffening ribs; "
     "no loose cartridges, no bright plastic"),
    ("M-03", "STR_PISTOL", 3,
     "a massive self-loading pistol pointing up, a big angular slide as a vertical bar along the left edge, the "
     "grip at the bottom going to the right in an L-shaped silhouette, light grey matte steel with dark slots and "
     "serrations on the slide, a dark grip; no chrome, no gold, no flashlight, no laser"),
    ("M-04", "STR_PISTOL_CLIP", 4,
     "a straight narrow pistol magazine standing vertically, grey metal body, the brass-orange case of the top "
     "cartridge visible at the top as the only coloured spot"),
    ("M-05", "STR_SHOTGUN", 1134,
     "a semi-automatic military shotgun standing vertically with the barrel at the top, a long barrel, a ribbed "
     "handguard with crosswise ribs in the upper third, the grip and stock at the bottom with the bottom of the "
     "stock going to the right, black and dark grey metal, a matte polymer grip; no wood, not double-barrelled"),
    ("M-07", "STR_CHAINGUN", 1256,
     "a heavy multi-barrel UAC chaingun standing vertically, a rotating grey cylinder of vertical barrels at the "
     "top, a boxy body in the middle with two rust-orange perforated panels one above the other, a handle with "
     "a small red indicator light at the bottom and a dark rounded box on the right, darkened gunmetal grey; "
     "no ammunition belts"),
    ("M-08", "STR_FLAMETHROWER", 1140,
     "a handheld flamethrower standing vertically with the nozzle at the top, a narrow nozzle tube with a small "
     "brass pilot burner in the upper third, a bright red painted fuel tank on the right in the middle, grips and "
     "stock below, black metal; no flame, no smoke"),
    ("M-09", "STR_GRENADE", 19,
     "a small hand-held high-explosive grenade, compact and smaller than its frame, a dark reddish-brown metal "
     "body, a light steel fuse and ring at the top left catching a highlight"),
    ("M-10", "STR_EMP_GRENADE", 2051,
     "a disc-shaped EMP device lying horizontally, a saturated bright blue rounded dome of glossy enamel, a matte "
     "silver-grey metal rim below with dark slots, a small dark hole on top; no lightning, no sparks"),
    ("M-11", "STR_SATCHEL_CHARGE", 1284,
     "a bulky worn brown leather satchel stuffed with explosives, with stitched seams and a dark flap on top, a "
     "small black plastic detonator with a red light and an antenna at the top left, a brass buckle or ring at "
     "the lower right of the front"),
    ("M-12", "STR_MEDI_KIT", 1665,
     "a bottle of rum standing upright with the neck at the top, thick dark brown glass with a highlight and dark "
     "rum inside, a green cap on the neck with a red rag ribbon tied around it whose ends flutter to the right, a "
     "label band around the middle with a pink-violet pattern and no readable writing; not a medical kit, no red "
     "cross, no bandages"),
    ("M-13", "STR_OXYGEN_TANK", 1865,
     "a steel oxygen cylinder standing vertically over its full height, used grey painted steel, a turquoise band "
     "of two or three ring lines in the upper third, a valve with a red handle on top, a black rubber hose coming "
     "out of the top and looping down the right side to the bottom"),
    ("M-14", "STR_LONG_KNIFE", 2081,
     "a ritual long knife pointing down: the pommel and a dark grip at the top, a straight symmetrical silver "
     "cross guard below them, a long straight mirror-polished steel blade down to the point with a highlight "
     "along it; no blood, no engraving, not curved"),
    ("M-15", "STR_BATTLE_AX", 4056,
     "a battle axe standing vertically with the head at the top, a half-moon crescent blade on the right and a "
     "sharp beak-shaped back spike on the left, steel with a cold violet-grey sheen, a long dark metal haft "
     "going down, the lower third of the haft wrapped crosswise in dark red leather, a pommel at the bottom"),
    ("M-16", "STR_POTATO_SACK", 1617,
     "a standing sack of rough earthy brown burlap with greenish earth stains, the neck at the top tied with a "
     "grey-blue string with the cloth ends sticking out, a rounded belly; nothing visible inside, no potatoes, "
     "no vegetables, no writing"),
    ("M-17", "STR_SCROLL_E4", 4183,
     "an unrolled parchment scroll standing almost vertically and slightly tilted, rolled into tubes at the top "
     "and bottom, light cream-yellow parchment with reddish-golden edges and tube ends, a single dark brown ink "
     "spiral in the centre as the only sign; no text, no characters, no seals"),
    ("M-18", "STR_PIR_ASSAULT", 1607,
     "a folded protective suit of armour lying as a shapeless wide stack, dark blue quilted and plated pieces, "
     "black straps and inserts, a few greenish edge highlights; no helmet with a face, no emblems, no writing, no "
     "person"),
    ("M-19", "STR_FOOD_BAG", 1609,
     "a rectangular food ration pack turned with a corner towards the viewer, its top face and front side "
     "visible, grey-lilac foil with a fine dark pattern on the top face, a dark label area on the front that is "
     "completely blank and even with no letters and no signs"),
    ("M-20", "STR_JUNK_PILE", 1617,
     "a low pile of salvage junk with a wide base and an uneven top, earthy brown and rusty: rusty metal sheets "
     "and scraps, a bent pipe, a bundle of copper wire, a dented chemical canister, dust and earth; not a sack, no "
     "whole machines, no bones, no skulls, no fire"),
]
CODE = (
    ("item_photo.py", ("ITEM", "NEGATIVE_EXTRA", "WHAT", "item_prompt", "load_frame", "REF_AK", "REF_NEGATIVE",
                       "REFS", "ref_input", "item_inputs", "REF_AK_V6", "REF_NEGATIVE_V6", "CTRL_AK",
                       "PART_WOOD", "PART_STEEL", "part_map", "REF_AK_V7", "AK_PARTS", "part_affine", "place_part",
                       "keep_part", "fit_part", "rod_part", "ref_parts_input", "bend_part", "part_point",
                       "light_part")),
    ("struct_guide.py", ("GUIDE_V1", "coverage", "smooth_loop", "loops")),
    ("photo_render.py", ("RENDER_V1", "PANEL_TEXT", "flat_input", "detect_panel")),
    ("struct_probe.py", ("C_TEXT", "run_multi", "inputs")),
    ("obj_photo.py", ("NEGATIVE",)),
    ("gen_hd.py", ("QWEN21_REPO", "Qwen21Painter", "qwen21_size", "save_png")),
    ("model_lock.py", ("pin", "check_runtime")),
)
# вырезка - своя ревизия (cut_rev): перевырезка готового ответа не меняет generator_rev
CUT_CODE = (
    ("item_photo.py", ("canvas_map", "model_geometry", "model_holes", "cut_fixed", "place_fixed", "ITEM_TONE",
                       "HOLE_SD", "HOLE_DS", "HOLE_EDGE", "HOLE_GROW")),
)


def sha256_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def item_prompt(what, name, rgb):
    """Вместо pr.prompt_for: подложка названа цветом (R-157), фраза специалиста про подложку - в конце."""
    r, g, b = [int(v) for v in rgb]
    kind = "neutral " if name.startswith("grey") else ""
    return ITEM.format(what=what, r=r, g=g, b=b) + " " + pr.PANEL_TEXT.format(kind=kind, r=r, g=g, b=b)


def generator_rev(lock, engine="qwen21"):
    import obj_gen_spec as ogs
    refs = {m: [sha256_file(r[0])[:12]] + list(r[1:]) for m, r in sorted(REFS.items())}
    d = {"params": pr.RENDER_V1, "prompt": ITEM, "negative_extra": NEGATIVE_EXTRA, "c_text": sp.C_TEXT,
         "refs": refs, "ref_negative": REF_NEGATIVE, "ref_negative_v6": REF_NEGATIVE_V6,
         "lock_rev": ogs.lock_rev(lock), "code": ogs.code_parts(CODE)}
    if engine == "edit":
        d.update(engine={"run": EDIT_RUN, "model_rev": EDIT_MODEL_REV, "prompt": EDIT_ITEM, "what": EDIT_WHAT,
                         "code": ogs.code_parts((("item_photo.py", ("EditPainter", "edit_prompt", "edit_inputs",
                                                                     "edit_model_check")),
                                                 ("photo_ui.py", ("MODEL", "LIGHTNING", "Painter"))))})
    return ar.h12(d)


def edit_prompt(what, name, rgb):
    """Вместо pr.prompt_for при --engine edit: подложка названа цветом (R-157)."""
    r, g, b = [int(v) for v in rgb]
    return EDIT_ITEM.format(what=what, r=r, g=g, b=b)


def edit_inputs(ref):
    """Вместо struct_probe.inputs при --engine edit: одна картинка - собранный эталон (R-205), без эскиза и карты."""
    def inputs(variant, frame, rgb):
        im, rrep = ref_parts_input(ref[0], frame, rgb, pr.RENDER_V1["zoom"], ref[3])
        return [im], "", {"ref": rrep, "inputs": "ref_parts_input"}
    return inputs


def edit_model_check(models):
    """Снимок Edit-2511 в кэше - тот, что записан в EDIT_MODEL_REV; качать нечего и нельзя (R-145)."""
    p = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "refs", "main")
    got = open(p).read().strip() if os.path.exists(p) else ""
    if got != EDIT_MODEL_REV:
        raise SystemExit("Edit-2511 в кэше %s, ждал %s - не рисую (R-145)" % (got or "нет", EDIT_MODEL_REV))
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        raise SystemExit("HF_HUB_OFFLINE не выставлен до импорта - не рисую (R-145)")


class EditPainter:
    """Переходник photo_ui.Painter (Edit-2511 + Lightning) под struct_probe.run_multi: pipe(**kw).images[0].
    Модель грузится при первом рендере; --dry-run и --recut её не трогают."""
    accepts = ("image", "negative_prompt", "true_cfg_scale", "width")

    def __init__(self, models):
        self.models, self.p = models, None

    @property
    def torch(self):
        import torch
        return torch

    def pipe(self, prompt, image, num_inference_steps, generator, negative_prompt="", true_cfg_scale=1.0,
             width=None, height=None):
        import photo_ui as pu
        if self.p is None:
            # папка снимка, а не имя репозитория: diffusers 0.41 и при HF_HUB_OFFLINE спрашивает HF про шарды
            # (model_info в _get_checkpoint_shard_files), а локальную папку читает без сети - и ревизия ровно та
            pu.MODEL = os.path.join(self.models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots",
                                    EDIT_MODEL_REV)
            self.p = pu.Painter(self.models, fast=True, steps=EDIT_RUN["steps"], photoreal=EDIT_RUN["lora"] > 0)
        ims = image if isinstance(image, list) else [image]
        out = self.p.edit(ims, prompt, negative_prompt, generator.initial_seed(), num_inference_steps,
                          true_cfg_scale, width, height, photoreal=EDIT_RUN["lora"])
        return argparse.Namespace(images=[Image.fromarray(out)])


def ref_input(path, frame, rgb, zoom):
    """Фото-эталон -> картинка размером кадр x zoom на той же подложке: габарит фото (альфа > 128) ложится на
    габарит оригинала x zoom - части фото попадают на места частей оригинала. Масштаб по осям свой: у
    стилизованного кадра пропорции не как у настоящей вещи, место части важнее её пропорций на фото; сколько
    растянуто - в отчёте (stretch_pct, + шире). -> (RGB, отчёт)."""
    ph = Image.open(path).convert("RGBA")
    pa_ = np.asarray(ph)[..., 3] > 128
    ys, xs = np.nonzero(pa_)
    pbb = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    ob = main_bbox(np.asarray(frame.convert("RGBA"))[..., 3] > 0, 4)
    tw, th = (ob[2] - ob[0]) * zoom, (ob[3] - ob[1]) * zoom
    part = ph.crop(pbb).resize((tw, th), Image.LANCZOS)
    flat = Image.new("RGBA", (frame.width * zoom, frame.height * zoom), tuple(int(v) for v in rgb) + (255,))
    flat.alpha_composite(part, (ob[0] * zoom, ob[1] * zoom))
    sx, sy = tw / (pbb[2] - pbb[0]), th / (pbb[3] - pbb[1])
    return flat.convert("RGB"), {"photo": path.replace("\\", "/"), "photo_sha256": sha256_file(path)[:12],
                                 "photo_bbox": list(pbb), "orig_bbox": list(ob),
                                 "stretch_pct": round(100 * (sx / sy - 1), 1)}


def part_affine(P, Q, s, th, res, ob):
    """Обратное отображение PIL AFFINE: холст кропа (res пикселей на пиксель базы) -> фото. Вперёд: точка фото P
    -> Q (пиксели k=1 от угла габарита ob), масштаб s (база на пиксель фото) по обеим осям, поворот th градусов
    по часовой на экране: out = Q + R(th) (in - P) s, R(th) = [[c, -s], [s, c]]."""
    c, sn = math.cos(math.radians(th)), math.sin(math.radians(th))
    qx, qy, k = (ob[0] + Q[0]) * res, (ob[1] + Q[1]) * res, 1.0 / (s * res)
    a, b, d, e = c * k, sn * k, -sn * k, c * k
    return (a, b, P[0] - a * qx - b * qy, d, e, P[1] - d * qx - e * qy)


def part_point(p, P, Q, s, th):
    """Точка фото p -> место (пиксели k=1 от угла габарита) тем же преобразованием, что part_affine."""
    c, sn = math.cos(math.radians(th)), math.sin(math.radians(th))
    dx, dy = (p[0] - P[0]) * s, (p[1] - P[1]) * s
    return Q[0] + c * dx - sn * dy, Q[1] + sn * dx + c * dy


def place_part(img, P, Q, s, th, res, ob, size):
    """Часть фото (RGBA) на прозрачный холст size: умноженная альфа, чтобы край не тянул цвет фона фото."""
    out = img.convert("RGBa").transform(size, Image.AFFINE, part_affine(P, Q, s, th, res, ob), resample=Image.BICUBIC)
    return out.convert("RGBA")


def keep_part(pa, keep, minus=(), sel=None):
    """Фото с альфой только в прямоугольнике keep (x0, y0, x1, y1) без прямоугольников minus и вне маски sel."""
    h, w = pa.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    inside = lambda r: (xs >= r[0]) & (ys >= r[1]) & (xs < r[2]) & (ys < r[3])
    m = inside(keep)
    for r in minus:
        m &= ~inside(r)
    if sel is not None:
        m &= sel
    a = pa.copy()
    a[..., 3] = np.where(m, a[..., 3], 0)
    return Image.fromarray(a, "RGBA")


def fit_part(img, P, om, ob, zone, cap_x, scales, rots, res=4, cap_r=None, pts=(), w_pts=0.0):
    """Подбор места части по силуэту оригинала: для каждой пары (масштаб, угол) сдвиг - по взаимной корреляции
    (FFT) маски части с маской оригинала в зоне (x0, y0, x1, y1 от угла габарита); мера - IoU внутри зоны минус
    w_pts x среднее расстояние (пиксели базы) точек части pts ((точка фото, контрольная точка), ...) до своих
    мест; левый край части не правее cap_x (корень у коробки, а не в воздухе), правый - не правее cap_r.
    -> (мера, s, th, Q точки P, iou, расстояния точек)."""
    H, W = om.shape[0] * res, om.shape[1] * res
    ys, xs = np.mgrid[0:H, 0:W]
    bx, by = xs / res - ob[0], ys / res - ob[1]
    zm = (bx >= zone[0]) & (by >= zone[1]) & (bx < zone[2]) & (by < zone[3])
    T = (np.repeat(np.repeat(om, res, 0), res, 1) & zm).astype(float)
    S = (3 * H, 3 * W)
    FT, FZ = np.fft.rfft2(T, s=S), np.fft.rfft2(zm.astype(float), s=S)
    c0 = (S[1] // 2, S[0] // 2)
    q0 = (c0[0] / res - ob[0], c0[1] / res - ob[1])
    dy = np.arange(S[0]); dy = np.where(dy > S[0] // 2, dy - S[0], dy)
    dx = np.arange(S[1]); dx = np.where(dx > S[1] // 2, dx - S[1], dx)
    best = None
    for s in scales:
        for th in rots:
            A = np.asarray(place_part(img, P, q0, s, th, res, ob, (S[1], S[0])))[..., 3] > 127
            if not A.any():
                continue
            FA = np.fft.rfft2(A.astype(float))
            I = np.fft.irfft2(np.conj(FA) * FT, s=S)        # I[d] = сумма A[x] T[x + d]
            AZ = np.fft.irfft2(np.conj(FA) * FZ, s=S)
            iou = I / np.maximum(AZ + T.sum() - I, 1.0)
            cols = np.nonzero(A.any(0))[0]
            ok = cols.min() + dx <= (ob[0] + cap_x) * res
            if cap_r is not None:
                ok &= cols.max() + 1 + dx <= (ob[0] + cap_r) * res
            dist = np.zeros(S)
            for p, t in pts:                                 # точка части при сдвиге d: место при нуле + d / res
                q = part_point(p, P, q0, s, th)
                dist += np.sqrt((q[0] + dx[None, :] / res - t[0]) ** 2 + (q[1] + dy[:, None] / res - t[1]) ** 2)
            dist /= max(1, len(pts))
            score = np.where(ok[None, :], iou - w_pts * dist, -1.0)
            iy, ix = np.unravel_index(np.argmax(score), score.shape)
            if best is None or score[iy, ix] > best[0]:
                best = (float(score[iy, ix]), float(s), float(th),
                        (float((c0[0] + dx[ix]) / res - ob[0]), float((c0[1] + dy[iy]) / res - ob[1])),
                        float(iou[iy, ix]), float(dist[iy, ix]))
    return best


def rod_part(img, top, bot, Qtop, Qbot, s, res, ob, size, cut=0.35):
    """Стойка приклада: ось фото top -> bot ставится от Qtop к Qbot одним масштабом s по обеим осям, поворот - по
    направлению оси; лишняя длина вырезается одним куском из середины (с доли cut от верха), толщина и концы
    стойки - как на фото. -> (холст, отчёт)."""
    ang_p = math.degrees(math.atan2(bot[0] - top[0], bot[1] - top[1]))
    ang_q = math.degrees(math.atan2(Qbot[0] - Qtop[0], Qbot[1] - Qtop[1]))
    th = ang_p - ang_q
    Lp = math.hypot(bot[0] - top[0], bot[1] - top[1])
    Lq = math.hypot(Qbot[0] - Qtop[0], Qbot[1] - Qtop[1]) / s
    drop = max(0.0, Lp - Lq)
    split = cut * Lp
    ux, uy = (bot[0] - top[0]) / Lp, (bot[1] - top[1]) / Lp
    a = np.asarray(img)
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    u = (xs - top[0]) * ux + (ys - top[1]) * uy
    f = split / max(Lp - drop, 1e-6)
    P2 = (top[0] + ux * (split + drop), top[1] + uy * (split + drop))
    Q2 = (Qtop[0] + (Qbot[0] - Qtop[0]) * f, Qtop[1] + (Qbot[1] - Qtop[1]) * f)
    cv = Image.new("RGBA", size, (0, 0, 0, 0))
    for sel, P, Q in ((u < split, top, Qtop), (u >= split + drop, P2, Q2)):
        b = a.copy()
        b[..., 3] = np.where(sel, b[..., 3], 0)
        cv.alpha_composite(place_part(Image.fromarray(b, "RGBA"), P, Q, s, th, res, ob, size))
    return cv, {"rot": round(th, 2), "cut_photo_px": round(drop, 1)}


def bend_part(layer, moves, anchors, sigma, res, ob, iters=24):
    """Местный изгиб поставленной части (торец магазина под торец оригинала): точки части moves ((откуда, куда),
    пиксели k=1 от угла габарита) сдвигаются в свои места, точки anchors стоят. Поле сдвига - гауссовы ядра sigma
    (пиксели базы) с весами, решёнными так, чтобы поле точно давало эти сдвиги; картинка тянется гладко, пиксели
    части не перерисовываются, а переезжают - фактура и светотень те же. Обратное отображение - подбор x = y - d(x)
    (сдвиг на пиксель базы меньше sigma - сходится), выборка билинейная по умноженной альфе. -> RGBA."""
    a = np.asarray(layer.convert("RGBa"), np.float32)
    H, W = a.shape[:2]
    C = np.asarray([s for s, _t in moves] + list(anchors), np.float64)
    D = np.asarray([(t[0] - s[0], t[1] - s[1]) for s, t in moves] + [(0.0, 0.0)] * len(anchors), np.float64)
    K = np.exp(-((C[:, None] - C[None]) ** 2).sum(-1) / (2 * sigma ** 2))
    Wt = np.linalg.solve(K, D)
    ys, xs = np.mgrid[0:H, 0:W]
    yb = np.stack([(xs + 0.5) / res - ob[0], (ys + 0.5) / res - ob[1]], -1)
    x = yb.copy()
    for _ in range(iters):
        g = np.exp(-((x[..., None, :] - C) ** 2).sum(-1) / (2 * sigma ** 2))
        x = yb - g @ Wt
    px, py = (x[..., 0] + ob[0]) * res - 0.5, (x[..., 1] + ob[1]) * res - 0.5
    x0, y0 = np.floor(px).astype(int), np.floor(py).astype(int)
    fx, fy = (px - x0)[..., None], (py - y0)[..., None]
    pad = np.pad(a, ((1, 1), (1, 1), (0, 0)))
    at = lambda yy, xx: pad[np.clip(yy + 1, 0, H + 1), np.clip(xx + 1, 0, W + 1)]
    out = (at(y0, x0) * (1 - fx) * (1 - fy) + at(y0, x0 + 1) * fx * (1 - fy) +
           at(y0 + 1, x0) * (1 - fx) * fy + at(y0 + 1, x0 + 1) * fx * fy)
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBa").convert("RGBA")


def light_part(img, k):
    """Светотень части: отклонение яркости от средней по непрозрачному - x k (цветность та же)."""
    a = np.asarray(img).astype(np.float32)
    op = a[..., 3] > 127
    if k == 1 or not op.any():
        return img
    lum = a[..., :3] @ np.asarray([0.2126, 0.7152, 0.0722], np.float32)
    m = float(lum[op].mean())
    nl = m + (lum - m) * k
    a[..., :3] *= (np.maximum(nl, 0) / np.maximum(lum, 1.0))[..., None]
    a[..., :3] = np.clip(a[..., :3], 0, 255)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


_PARTS_CACHE = {}


def ref_parts_input(path, frame, rgb, zoom, spec):
    """Фото-эталон, собранный по частям на местах частей оригинала (v7): тело одним масштабом по высоте дуло..
    хвост коробки, мушка - по ширине до левого уха, магазин и рукоять - подбор масштаба и угла по силуэту
    оригинала (fit_part), затыльник - по двум углам, стойки - от хвоста коробки до затыльника (rod_part); всё
    одним масштабом по обеим осям у каждой части, растяжения нет. -> (RGB кадр x zoom на подложке, отчёт)."""
    key = (path, tuple(int(v) for v in rgb), zoom, frame.tobytes(), json.dumps(spec, sort_keys=True))
    if key in _PARTS_CACHE:
        return _PARTS_CACHE[key]
    pa = np.asarray(Image.open(path).convert("RGBA"))
    om = np.asarray(frame.convert("RGBA"))[..., 3] > 0
    ob = main_bbox(om, 4)
    size = (frame.width * zoom, frame.height * zoom)
    b = spec["body"]
    g = b["span"][2] / float(b["span"][1] - b["span"][0])
    rep = {"photo": path.replace("\\", "/"), "photo_sha256": sha256_file(path)[:12], "orig_bbox": list(ob),
           "body_scale": round(g, 5)}
    sc = np.arange(*spec["fit_scale"]) * g
    rt = np.arange(spec["fit_rot"][0], spec["fit_rot"][1] + 1e-6, spec["fit_rot"][2])
    fits = {}
    for n in ("magazine", "grip"):
        p = spec[n]
        img = keep_part(pa, p["keep"])
        fits[n] = (img,) + fit_part(img, p["P"], om, ob, p["zone"], p["cap_x"], sc, rt, cap_r=p.get("cap_r"),
                                    pts=p.get("pts", ()), w_pts=spec.get("w_pts", 0.0))
        rep[n] = {"iou": round(fits[n][5], 3), "pts_dist": round(fits[n][6], 2),
                  "scale_vs_body": round(fits[n][2] / g, 3), "rot": fits[n][3],
                  "at": [round(v, 2) for v in fits[n][4]]}
    bt = spec["butt"]
    vp = (bt["P2"][0] - bt["P"][0], bt["P2"][1] - bt["P"][1])
    vq = (bt["Q2"][0] - bt["Q"][0], bt["Q2"][1] - bt["Q"][1])
    sb = math.hypot(*vq) / math.hypot(*vp)
    thb = math.degrees(math.atan2(vq[1], vq[0]) - math.atan2(vp[1], vp[0]))
    light = spec.get("stock_light", 1.0)
    cv = Image.new("RGBA", size, tuple(int(v) for v in rgb) + (255,))
    img, _sc, s, th, Q = fits["magazine"][:5]
    mag = place_part(img, spec["magazine"]["P"], Q, s, th, zoom, ob, size)
    bend = spec["magazine"].get("bend")
    if bend:                    # торец фото косой, у оригинала почти отвесный: кончик и угол - на точки оригинала
        mv = [(part_point(p, spec["magazine"]["P"], Q, s, th), t) for p, t in spec["magazine"]["pts"]]
        mag = bend_part(mag, mv, bend["anchors"], bend["sigma"], zoom, ob)
        rep["magazine"]["bend"] = [[round(t[0] - q[0], 2), round(t[1] - q[1], 2)] for q, t in mv]
    cv.alpha_composite(mag)
    rep["struts"] = []
    for keep, top, bot, xb in spec["struts"]:
        qt = part_point(top, b["P"], b["Q"], g, 0)             # верх - хвост коробки тела
        # низ - верх затыльника под x оригинала: точку фото на верхней кромке ищем по x места
        cand = [part_point((x, keep[3]), bt["P"], bt["Q"], sb, thb) for x in range(int(bt["P"][0]), int(bt["P2"][0]) + 1)]
        qb = min(cand, key=lambda q: abs(q[0] - xb))
        rod, rr = rod_part(light_part(keep_part(pa, keep), light), top, bot, qt, (xb, qb[1]), sb, zoom, ob, size)
        cv.alpha_composite(rod)
        rep["struts"].append(dict(rr, top=[round(v, 2) for v in qt], bottom=[xb, round(qb[1], 2)]))
    cv.alpha_composite(place_part(light_part(keep_part(pa, bt["keep"]), light), bt["P"], bt["Q"], sb, thb, zoom, ob,
                                  size))
    rep["stock"] = {"scale_vs_body": round(sb / g, 3), "butt_rot": round(thb, 2), "light": light}
    body = keep_part(pa, b["keep"], (spec["magazine"]["keep"], spec["grip"]["keep"]))
    cv.alpha_composite(place_part(body, b["P"], b["Q"], g, 0, zoom, ob, size))
    img, _sc, s, th, Q = fits["grip"][:5]
    cv.alpha_composite(place_part(img, spec["grip"]["P"], Q, s, th, zoom, ob, size))
    f = spec["front"]
    sf = (f["Q"][0] - f["x_to"][1]) / float(f["P"][0] - f["x_to"][0])
    cv.alpha_composite(place_part(keep_part(pa, f["keep"]), f["P"], f["Q"], sf, 0, zoom, ob, size))
    rep["front"] = {"scale_vs_body": round(sf / g, 3)}
    _PARTS_CACHE[key] = (cv.convert("RGB"), rep)
    return _PARTS_CACHE[key]


def ref_check_sheet(ref, frame, ctrl, zoom):
    """Проверочный лист эталона (во вход модели не идёт): эталон | эталон + контур оригинала и контрольные
    точки | оригинал x zoom + контур силуэта эталона; -> (картинка, числа охвата)."""
    om = np.asarray(frame.convert("RGBA"))[..., 3] > 0
    ob = main_bbox(om, 4)
    O = np.repeat(np.repeat(om, zoom, 0), zoom, 1)
    oe = O & ~pb.shrink(O, 2)
    a = np.asarray(ref).astype(int)
    panel = np.median(np.concatenate([a[:4].reshape(-1, 3), a[-4:].reshape(-1, 3)]), 0)
    rm = np.abs(a - panel).sum(2) > 18
    re = rm & ~pb.shrink(rm, 2)
    c2 = np.asarray(ref).copy()
    c2[oe] = (255, 40, 40)
    c2 = Image.fromarray(c2)
    d = ImageDraw.Draw(c2)
    for x, y in ctrl:
        cx, cy = (ob[0] + x) * zoom, (ob[1] + y) * zoom
        d.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), outline=(255, 230, 0), width=2)
    o = Image.new("RGBA", frame.size, tuple(int(v) for v in panel) + (255,))
    o.alpha_composite(frame.convert("RGBA"))
    o = np.asarray(o.convert("RGB").resize(ref.size, Image.NEAREST)).copy()
    o[re] = (0, 220, 255)
    W, H = ref.size
    s = Image.new("RGB", (3 * (W + 12) + 12, H + 24), (12, 12, 12))
    for i, im in enumerate((ref, c2, Image.fromarray(o))):
        s.paste(im, (12 + i * (W + 12), 12))
    ys, xs = np.nonzero(rm)
    num = {"ref_bbox": [round(float(v), 2) for v in (xs.min() / zoom - ob[0], ys.min() / zoom - ob[1],
                                                       (xs.max() + 1) / zoom - ob[0], (ys.max() + 1) / zoom - ob[1])],
           "orig_bbox": [0, 0, ob[2] - ob[0], ob[3] - ob[1]],
           "iou": round(float((rm & O).sum() / (rm | O).sum()), 3)}
    return s, num


def item_inputs(base, ref):
    """struct_probe.inputs с фото-эталоном третьей картинкой (ref - (путь, текст[, точки[, части]]) или None)."""
    def inputs(variant, frame, rgb):
        ims, extra, rep = base(variant, frame, rgb)
        if ref is None or variant == "B":
            return ims, extra, rep
        zoom = pr.RENDER_V1["zoom"]
        im, rrep = ref_parts_input(ref[0], frame, rgb, zoom, ref[3]) if len(ref) > 3 else \
            ref_input(ref[0], frame, rgb, zoom)
        if len(ref) > 2:                     # вторая картинка - карта частей (зоны материала, без меток - R-204)
            ims = [ims[0], part_map(frame, rgb, zoom)] + ims[2:]
            extra = ""                       # C_TEXT говорит про пиксельный оригинал, его здесь нет
        return ims + [im], extra + " " + ref[1], dict(rep, ref=rrep)
    return inputs


def part_map(frame, rgb, zoom):
    """Карта частей кропа (гладкие контуры, как struct_guide.build: кадр x zoom на подложке rgb), но зоны -
    плоскими цветами материала: дерево - пиксели оригинала красноватее серого (R - G от 10, R - B от 5 - не
    сиреневый блик стойки (125,113,146): бордовое дерево
    BIGOBS 1168 от (29,15,18) до (156,121,103); median cut частей смешивает его с серым), остальное сталь.
    Ни контура линией, ни точек: метки во входе Qwen переносятся в ответ (R-204)."""
    P = sg.GUIDE_V1
    a0 = np.asarray(frame.convert("RGBA")).astype(int)
    m = pb.guide(frame)["m"]
    wood = m & (a0[..., 3] > 0) & (a0[..., 0] - a0[..., 1] >= 10) & (a0[..., 0] - a0[..., 2] >= 5)
    h, w = m.shape
    sil = sg.coverage([sg.smooth_loop(L, P["min_corners"]) for L in sg.loops(m)], w, h, zoom, P["ss"])
    cw = sg.coverage([sg.smooth_loop(L, P["min_corners"]) for L in sg.loops(wood)], w, h, zoom, P["ss"])[..., None]
    a = sil[..., None]
    body = np.asarray(PART_WOOD, np.float32) * cw + np.asarray(PART_STEEL, np.float32) * (1 - cw)
    out = body * a + np.asarray(rgb, np.float32) * (1 - a)
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGB")


def load_frame(t, frame):
    """Кадр BIGOBS как движок: индексы, 0 прозрачный (R-043), палитра своего файла -> RGBA 32x48."""
    d = os.path.join(CARDS, "originals", t)
    src = [f for f in sorted(os.listdir(d)) if f.startswith("BIGOBS_%d__" % frame)]
    if len(src) != 1:
        raise SystemExit("%s: кадр BIGOBS %d - файлов %d" % (t, frame, len(src)))
    im = Image.open(os.path.join(d, src[0]))
    if im.mode != "P" or im.size != (iac.HAND_W, iac.HAND_H):
        raise SystemExit("%s: %s %s, ждал P 32x48" % (t, im.mode, im.size))
    idx = np.asarray(im)
    pal = np.asarray(im.getpalette()[:768], np.uint8).reshape(-1, 3)
    rgba = np.dstack([pal[idx], np.where(idx == 0, 0, 255).astype(np.uint8)])
    return Image.fromarray(rgba, "RGBA"), src[0]


def crop_job(full):
    """Как photo_base.job_frame: кроп по габариту с полями PAD (кадр сначала расширен на PAD прозрачным)."""
    big = Image.new("RGBA", (full.width + 2 * PAD, full.height + 2 * PAD), (0, 0, 0, 0))
    big.paste(full, (PAD, PAD))
    bb = big.split()[3].getbbox()
    box = (max(0, bb[0] - PAD), max(0, bb[1] - PAD), min(big.width, bb[2] + PAD), min(big.height, bb[3] + PAD))
    return big.crop(box), box


def canvas_map(hd, frame):
    """Ответ модели -> холст кропа x4 одним преобразованием, не глядя на содержимое: вход (кроп x zoom)
    run_multi растянул под размер рендера (qwen21_size, кратность 32), здесь - ровно обратно. Небольшая
    анизотропия - от округления размера рендера, она у входа и у ответа одна и та же, это не правка
    пропорций предмета. -> (RGB float32, матт ответа 0..1, отчёт)."""
    cw, ch = frame.width * K, frame.height * K
    m_raw, bg, own = pb.render_matte(hd)
    rgb = np.asarray(hd.convert("RGB").resize((cw, ch), Image.LANCZOS), np.float32)
    mi = Image.fromarray((np.clip(m_raw, 0, 1) * 255).astype(np.uint8), "L").resize((cw, ch), Image.LANCZOS)
    info = {"render": list(hd.size), "canvas": [cw, ch],
            "anisotropy_pct": round(100 * ((hd.width / hd.height) / (cw / ch) - 1), 2)}
    return rgb, np.asarray(mi, np.float32) / 255.0, m_raw, bg, own, info


def main_bbox(mask, crumb):
    """Габарит силуэта без крошек: 8-связные куски от crumb пикселей (тонкий ствол и антенна остаются)."""
    lab, n = pb.label(mask, 8)
    if not n:
        return None
    sizes = np.bincount(lab.ravel())
    keep = np.isin(lab, [i for i in range(1, n + 1) if sizes[i] >= crumb])
    ys, xs = np.nonzero(keep)
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def model_geometry(m_c, frame):
    """Размер и место силуэта МОДЕЛИ (матт ответа на холсте x4) против оригинала x4 - то, что прежде
    правил fit. Края - x0, y0, x1, y1 в пикселях HD, + вправо и вниз."""
    ob = main_bbox(np.asarray(frame)[..., 3] > 0, 4)
    mb = main_bbox(m_c > 0.5, CRUMB)
    r = {"orig_bbox4": [v * K for v in ob] if ob else None, "model_bbox4": list(mb) if mb else None}
    if not (ob and mb):
        r.update(geometry="REWORK", geometry_why="силуэт модели не найден")
        return r
    o = [v * K for v in ob]
    w0, h0 = o[2] - o[0], o[3] - o[1]
    dw, dh = (mb[2] - mb[0]) / w0 - 1, (mb[3] - mb[1]) / h0 - 1
    edges = [mb[i] - o[i] for i in range(4)]
    tol = [max(EDGE_MIN, EDGE_TOL * (w0 if i % 2 == 0 else h0)) for i in range(4)]
    r.update(dw_pct=round(100 * dw, 1), dh_pct=round(100 * dh, 1), edges=edges,
             edge_tol=[round(t, 1) for t in tol])
    why = []
    if abs(dw) > TOL or abs(dh) > TOL:
        why.append("размер %+.1f%% / %+.1f%% (допуск 3%%)" % (100 * dw, 100 * dh))
    bad = ["%s %+d" % (n, e) for n, e, t in zip(("лево", "верх", "право", "низ"), edges, tol) if abs(e) > t]
    if bad:
        why.append("края не на месте: %s HD-пикс" % ", ".join(bad))
    r["geometry"] = "REWORK" if why else "GEOMETRY_OK"
    r["geometry_why"] = "; ".join(why)
    return r


def model_holes(hd, cw, ch, bg):
    """Сквозные отверстия, которые нарисовала модель (просвет рамочного приклада, спусковая скоба): ответ - RGB
    на подложке, своей прозрачности нет, а альфа managed_alpha идёт от силуэта оригинала и закрывает их подложкой.
    Отверстие - кусок подложки в ответе: гладкий как подложка снаружи (local_std, HOLE_SD) и близкий к ней с тенью
    (shadow_dist, HOLE_DS); замкнутый внутри предмета, от POCKET_MIN пикселей холста, или связанный с краем кадра
    (там модель предмет просто не нарисовала). Тёмное углубление (окно мушки, нарисованное глухим) - не отверстие.
    Ищется на разрешении ответа, кромка - расширением по близкому к подложке, на холст x4 - усреднением: доля
    отверстия 0..1. -> (доля на холсте, отчёт)."""
    import obj_photo as op
    a = np.asarray(hd.convert("RGB"), np.float32)
    ds = pb.shadow_dist(a, bg)
    sd = op.local_std(a.mean(-1), 3)
    seed = (ds < HOLE_DS) & (sd < HOLE_SD)
    lab, n = pb.label(seed, 4)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    px_min = pb.POCKET_MIN * (a.shape[0] * a.shape[1]) / float(cw * ch)
    keep = sizes >= px_min
    keep[border] = True
    keep[0] = False
    hole = pb.grow(keep[lab], HOLE_GROW) & (ds < HOLE_EDGE)
    frac = np.asarray(Image.fromarray(hole.astype(np.uint8) * 255, "L").resize((cw, ch), Image.BOX),
                      np.float32) / 255.0
    inner = [i for i in range(1, n + 1) if keep[i] and i not in set(border.tolist())]
    sx, sy = cw / float(a.shape[1]), ch / float(a.shape[0])
    rep = []
    for i in inner:
        ys, xs = np.nonzero(lab == i)
        rep.append({"bbox4": [round(xs.min() * sx), round(ys.min() * sy), round((xs.max() + 1) * sx),
                              round((ys.max() + 1) * sy)], "px4": round(float(sizes[i]) * sx * sy)})
    return frac, rep


def cut_fixed(frame, hd, asked):
    """photo_base.cut без подгонки по содержимому: canvas_map вместо fit (правка пропорций до 1.3, низ к низу,
    центр к центру) и вместо fit_shape (лучший масштаб и якорь). Проверки формы - на том же холсте, где ответ
    лежит на самом деле. Альфа, очистка кромки и тон - как в photo_base.cut. -> (RGBA x4, отчёт, g, матт)."""
    import probe_object as po
    g = pb.guide(frame)
    rgb, m_c, m_raw, bg, own, info = canvas_map(hd, frame)
    rep = {"panel_rgb": [round(float(v), 1) for v in bg], "own_alpha": own, "canvas_map": info,
           "px": g["px"], "open_px": g["open_px"], "thin_px": g["thin_px"], "lum": round(g["lum"], 1)}
    a = np.asarray(frame.convert("RGBA"), np.float64)
    body = a[..., :3][a[..., 3] > 128]
    margin = round(float(np.percentile(np.abs(body - bg).max(-1), 10)), 1) if len(body) else None
    rep["panel_should"] = "%s %.0f" % (pb.panel_for(frame)[0], pb.panel_for(frame)[2])
    rep["panel_drift"] = round(float(np.abs(bg - np.asarray(asked, np.float64)).max()), 1)
    rep.update(pb.conformity(g, m_c, {"aspect_raw": None, "aspect_fix": 1.0}, margin, rgb, bg))
    rep["model"] = model_geometry(m_c, frame)
    alpha, tri, rep["pockets_cut"] = pb.managed_alpha(g, rgb, m_c, bg)
    # отверстия ответа сильнее силуэта оригинала: просвет, нарисованный моделью, прозрачен и там, где оригинал сплошной
    hole, rep["model_holes"] = model_holes(hd, rgb.shape[1], rgb.shape[0], bg)
    rep["holes_cut_px"] = int(((hole > 0.5) & (alpha > 0.5)).sum())
    alpha = alpha * (1.0 - hole)
    tri = np.where(hole > 0.5, 0, tri).astype(np.uint8)
    clean = pb.decontaminate(rgb, alpha, bg)
    rep.update(pb.qa(g, clean, alpha, tri, bg))
    rgba = np.dstack([clean, alpha * 255.0]).clip(0, 255).astype(np.uint8)
    im = po.match_tone(Image.fromarray(rgba, "RGBA"), frame, ITEM_TONE)
    rep["verdict"] = {"FAIL": "FAIL", "UNVERIFIABLE": "RERENDER"}.get(rep["geometry"]) or (
        "REVIEW" if "REVIEW" in (rep["geometry"], rep["alpha"]) else "PASS")
    return im, rep, g, m_c


def place_fixed(cut4, box, w, h, full, inherit):
    """Вырезка x4 кропа -> кадр k=4 128x192 на месте оригинала x4: ни уменьшения, ни сдвига, ни обрезки.
    Вне клеток и вне допуска руки - замер до обрезки движком, не правка. Решение Vitali 03.10 разрешает выход
    за клетки только унаследованный от оригинала (census/items/geometry/decisions.tsv): вне клеток HD не дальше
    контура оригинала x4 (sil_x4, как у вырезки, плюс полпикселя базы) - кромка срезается по нему
    (contour_clip_px), дальше полосы вырезки - beyond_orig_px, REWORK. -> (RGBA, отчёт)."""
    W, H = iac.HAND_W * K, iac.HAND_H * K
    canvas = Image.new("RGBA", ((iac.HAND_W + 2 * PAD) * K, (iac.HAND_H + 2 * PAD) * K), (0, 0, 0, 0))
    canvas.paste(cut4, (box[0] * K, box[1] * K))
    out = canvas.crop((PAD * K, PAD * K, PAD * K + W, PAD * K + H))
    lost = int((np.asarray(canvas)[..., 3] > 0).sum() - (np.asarray(out)[..., 3] > 0).sum())
    x0, y0, x1, y1 = (v * K for v in iac.grid_rect(w, h))
    cells = np.zeros((H, W), bool)
    cells[y0:y1, x0:x1] = True
    contour = pb.grow(pb.sil_x4(np.asarray(full)[..., 3] > 0) > 0.5, K // 2)
    # кромка вырезки (полоса managed_alpha и размытие) вне разрешённого - срезается явно, с числом в отчёте;
    # разрешено - клетки, а с решением inherit ещё и контур оригинала. Дальше полосы вырезки от контура быть
    # нечему - это уже не кромка, REWORK
    a = np.asarray(out).copy()
    fringe = (a[..., 3] > 0) & ~(cells | contour) if inherit else (a[..., 3] > 0) & ~cells
    beyond = int((fringe & ~pb.grow(contour, pb.BAND)).sum())
    a[..., 3][fringe] = 0
    out = Image.fromarray(a, "RGBA")
    alpha = a[..., 3]
    dx, dy = (2 - w) * 8 * K, (3 - h) * 8 * K          # сдвиг руки, RuleItem::getHandSpriteOffX/Y
    hand = np.zeros_like(alpha)
    ys, xs = np.nonzero(alpha)
    ok = (ys + dy >= 0) & (ys + dy < H) & (xs + dx >= 0) & (xs + dx < W)
    hand[ys[ok] + dy, xs[ok] + dx] = 255
    return out, {"scale": 1.0, "shift": [0, 0], "lost_off_frame_px": lost,
                 "contour_clip_px": int(fringe.sum()), "beyond_orig_px": beyond,
                 "outside_grid_px": iac.outside(alpha, iac.grid_rect(w, h), K),
                 "outside_hand_px": iac.outside(hand, iac.hand_rect(w, h), K) + int((~ok).sum())}


def geometry_gate():
    """{мастер: (статус замера оригинала, решение Vitali или '')} - item_geometry.py и decisions.tsv."""
    import csv
    st, dec = {}, {}
    with open(GEOMETRY, encoding=ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            st[r["master"]] = r["status"]
    if os.path.exists(DECISIONS):
        with open(DECISIONS, encoding=ENC) as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 2 and p[0].startswith("M-"):
                    dec[p[0]] = p[1].strip()
    return {m: (s, dec.get(m, "")) for m, s in st.items()}


def sheet(cells, path):
    """Оригинал x4 | ответ модели на холсте кадра тем же преобразованием, что и в вырезке (зелёная рамка -
    габарит оригинала x4, красная - габарит модели) | HD на тёмном фоне с рамкой клеток §5.3 | HD в сетке
    инвентаря 1:1 (k=4). Подпись - статус и размер модели по ширине / высоте."""
    W, H, gap, top = iac.HAND_W * K, iac.HAND_H * K, 8, 30
    im = Image.new("RGB", (gap + len(cells) * (W + gap), top + 4 * (H + gap)), (24, 24, 30))
    d = ImageDraw.Draw(im)
    for n, (label, j, raw, hd, mg) in enumerate(cells):
        x = gap + n * (W + gap)
        d.text((x, 3), label, fill=(230, 230, 230))
        d.text((x, 15), "%s / %s %%" % (mg.get("dw_pct"), mg.get("dh_pct")), fill=(230, 200, 120))
        o = j["full"].resize((W, H), Image.NEAREST)
        im.paste(o, (x, top), o)
        rgb = canvas_map(Image.open(raw).convert("RGB"), j["crop"])[0]
        mod = Image.new("RGB", ((iac.HAND_W + 2 * PAD) * K, (iac.HAND_H + 2 * PAD) * K), (60, 60, 60))
        mod.paste(Image.fromarray(rgb.clip(0, 255).astype(np.uint8), "RGB"), (j["box"][0] * K, j["box"][1] * K))
        mod = mod.crop((PAD * K, PAD * K, PAD * K + W, PAD * K + H))
        md = ImageDraw.Draw(mod)
        for bb, col in ((mg.get("orig_bbox4"), (60, 220, 60)), (mg.get("model_bbox4"), (230, 50, 50))):
            if bb:
                ox, oy = (j["box"][0] - PAD) * K, (j["box"][1] - PAD) * K
                md.rectangle([ox + bb[0], oy + bb[1], ox + bb[2] - 1, oy + bb[3] - 1], outline=col)
        im.paste(mod, (x, top + H + gap))
        rect = iac.grid_rect(*j["cells"])
        for row in (2, 3):
            y = top + row * (H + gap)
            bg = Image.new("RGBA", (W, H), (16, 18, 26, 255))
            if row == 3:                    # сетка инвентаря: линии клеток 16 px базы
                g = ImageDraw.Draw(bg)
                for v in range(0, W + 1, 16 * K):
                    g.line([(v, 0), (v, H)], fill=(70, 80, 100))
                for v in range(0, H + 1, 16 * K):
                    g.line([(0, v), (W, v)], fill=(70, 80, 100))
            bg.alpha_composite(hd)
            im.paste(bg.convert("RGB"), (x, y))
            if row == 2:
                x0, y0, x1, y1 = (v * K for v in rect)
                d.rectangle([x + x0, y + y0, x + x1 - 1, y + y1 - 1], outline=(200, 60, 60))
    im.save(path)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--only", default="", help="мастера или типы через запятую")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--recut", action="store_true")
    ap.add_argument("--models", default=None)
    ap.add_argument("--max-renders", type=int, default=0, dest="max_renders")
    ap.add_argument("--engine", default="qwen21", choices=("qwen21", "edit"),
                    help="qwen21 - рендер по эскизу (RENDER_V1); edit - правка собранного эталона Edit-2511 (EDIT_RUN)")
    args = ap.parse_args()
    os.chdir(ROOT)
    only = set(filter(None, args.only.split(",")))
    jobs = []
    for n, (m, t, frame, what) in enumerate(WHAT):
        if only and m not in only and t not in only:
            continue
        with open(os.path.join(CARDS, t + ".json"), encoding=ENC) as f:
            card = json.load(f)
        w, h = int(card["rules"]["invWidth"]["value"]), int(card["rules"]["invHeight"]["value"])
        full, src = load_frame(t, frame)
        crop, box = crop_job(full)
        jobs.append({"asset_id": t, "name": t, "master": m, "frame": frame, "cells": [w, h], "what": what,
                     "seed": SEED0 + n, "src": src, "full": full, "crop": crop, "box": box})

    gate = geometry_gate()
    for j in jobs:
        st, dec = gate.get(j["master"], ("нет замера", ""))
        j["geometry_orig"], j["geometry_decision"] = st, dec
        if st != "OK" and not dec and not args.dry_run:
            raw =os.path.join(args.out, "raw", j["name"] + ".a0.png")
            if args.recut and os.path.exists(raw):
                print("%-5s %s: %s - только перевырезка готового ответа, статус не меняется" % (
                    j["master"], j["asset_id"], st), flush=True)
                continue
            raise SystemExit("%s %s: %s, решения Vitali в %s нет - рендер запрещён (контракт v4 §3); "
                             "--only без него" % (j["master"], j["asset_id"], st, DECISIONS))

    R = sp.Render(args.out, args.models, args.max_renders, args.recut)
    import gen_fire
    import obj_photo as op
    neg0 = op.NEGATIVE + NEGATIVE_EXTRA
    gen_fire.NEGATIVE = R.po.gen_fire.NEGATIVE = neg0
    base_inputs = sp.inputs                  # Render.job зовёт sp.inputs - на задание с эталоном своя обёртка
    pr.prompt_for = item_prompt              # Render.job зовёт pr.prompt_for - здесь свой промпт
    pb.cut = cut_fixed                       # и pb.cut - здесь вырезка без подгонки по содержимому
    R.grev = generator_rev(R.lock, args.engine)
    edit = args.engine == "edit"
    if edit:
        bad = [j["master"] for j in jobs if not (REFS.get(j["master"]) and len(REFS[j["master"]]) > 3)
               or j["master"] not in EDIT_WHAT]
        if bad:
            raise SystemExit("--engine edit - только мастера с собранным эталоном и EDIT_WHAT, а не %s" % bad)
        for j in jobs:
            j["what"] = EDIT_WHAT[j["master"]]
        pr.prompt_for = edit_prompt
        R.run = argparse.Namespace(mp=EDIT_RUN["mp"], steps=EDIT_RUN["steps"], cfg=EDIT_RUN["cfg"])
        R.painter = EditPainter(R.ns.models)
        if not args.dry_run:
            edit_model_check(R.ns.models)
    import obj_gen_spec as ogs
    R.cut_rev = ar.h12({"photo_base": R.cut_rev, "code": ogs.code_parts(CUT_CODE)})
    print("items_pilot_v1: generator_rev %s, guide_rev %s, cut_rev %s, мастеров %d" % (
        R.grev, R.guide_rev, R.cut_rev, len(jobs)), flush=True)
    gd = os.path.join(args.out, "guide")
    os.makedirs(gd, exist_ok=True)
    plan = []
    for j in jobs:
        panels = pr.panels_by_margin(j["crop"])
        g, rep = sg.build(j["crop"], pr.RENDER_V1["zoom"], panels[0][1])
        g.save(os.path.join(gd, j["name"] + ".png"))
        j["ref"] = REFS.get(j["master"])
        if j["ref"]:
            zoom = pr.RENDER_V1["zoom"]
            if len(j["ref"]) > 3:
                ri, j["ref_rep"] = ref_parts_input(j["ref"][0], j["crop"], panels[0][1], zoom, j["ref"][3])
            else:
                ri, j["ref_rep"] = ref_input(j["ref"][0], j["crop"], panels[0][1], zoom)
            ri.save(os.path.join(gd, j["name"] + ".ref.png"))
            if len(j["ref"]) > 2:
                part_map(j["crop"], panels[0][1], zoom).save(os.path.join(gd, j["name"] + ".parts.png"))
                ck, j["ref_rep"]["check"] = ref_check_sheet(ri, j["crop"], j["ref"][2], zoom)
                ck.save(os.path.join(gd, j["name"] + ".ref_check.png"))
            print("      эталон %s" % j["ref_rep"], flush=True)
        plan.append((j, panels, g))
        print("%-5s %-20s %dx%d seed %d подложка %s guide %s" % (j["master"], j["asset_id"], j["cells"][0],
                                                                j["cells"][1], j["seed"], panels[0][0], rep), flush=True)
    if args.dry_run:
        with open(os.path.join(args.out, "plan.md"), "w", encoding=ENC) as f:
            f.write("# items_pilot_v1 - план (generator_rev %s)\n\n" % R.grev)
            f.write("negative: %s\n\n" % neg0)
            for j, panels, _g in plan:
                if edit:
                    f.write("## %s %s, кадр %d, %dx%d - Edit-2511 %s\n\nвход 1: эталон %s\n\n%s\n\n" % (
                        j["master"], j["asset_id"], j["frame"], j["cells"][0], j["cells"][1], EDIT_RUN,
                        j["ref_rep"], edit_prompt(j["what"], panels[0][0], panels[0][1])))
                    continue
                f.write("## %s %s, кадр %d, %dx%d\n\n%s %s%s\n\n" % (
                    j["master"], j["asset_id"], j["frame"], j["cells"][0], j["cells"][1],
                    item_prompt(j["what"], panels[0][0], panels[0][1]),
                    "" if j["ref"] and len(j["ref"]) > 2 else sp.C_TEXT, " " + j["ref"][1] if j["ref"] else ""))
                if j["ref"]:
                    v6 = len(j["ref"]) > 2
                    f.write("входов 3, эталон %s%s; negative + `%s`\n\n" % (
                        j["ref_rep"], ", вторая - карта частей без меток, точки только на листе %s" % (j["ref"][2],) if v6 else "",
                        REF_NEGATIVE_V6 if v6 else REF_NEGATIVE))
        print("план: %s" % os.path.join(args.out, "plan.md"))
        return
    raw_dir, meta_dir = os.path.join(args.out, "raw"), os.path.join(args.out, "meta")
    pack = os.path.join(args.out, "pack", "BIGOBS.PCK")
    missing = [j["asset_id"] for j, *_r in plan if not os.path.exists(os.path.join(raw_dir, j["name"] + ".a0.png"))]
    if args.recut and missing:                      # R-127
        raise SystemExit("--recut, а ответа нет у %d: %s" % (len(missing), missing[:5]))
    if missing:
        R.check_lock()
    for d in (raw_dir, meta_dir, pack):
        os.makedirs(d, exist_ok=True)
    t0, cells = time.time(), []
    try:
        for n, (j, panels, g) in enumerate(plan, 1):
            sp.inputs = edit_inputs(j["ref"]) if edit else item_inputs(base_inputs, j["ref"])
            gen_fire.NEGATIVE = R.po.gen_fire.NEGATIVE = neg0 + ((REF_NEGATIVE_V6 if len(j["ref"]) > 2 else REF_NEGATIVE) if j["ref"] else "")
            final, attempts = R.job("C", j, j["crop"], panels, raw_dir)
            if final is None:
                print("%-20s нет ответа (--recut)" % j["asset_id"], flush=True)
                continue
            im, rep, _g, m_c, c, verdict = final
            hd, prep = place_fixed(im, j["box"], *j["cells"], j["full"],
                                   j["geometry_decision"] == "inherit_overflow")
            pp = os.path.join(pack, "%d.%s.png" % (j["frame"], j["asset_id"]))
            hd.save(pp)
            mg = rep["model"]
            blocked = j["geometry_orig"] != "OK" and not j["geometry_decision"]
            # статус контракта v4 §7: BLOCKED_GEOMETRY - до решения Vitali; REWORK - размер или место модели не
            # те, или HD вне клеток при оригинале в клетках; иначе CANDIDATE - смотреть глазами, не приёмка
            over = prep["beyond_orig_px"]
            if over:
                mg["geometry_why"] = "; ".join(filter(None, [mg["geometry_why"],
                                                             "вне клеток дальше контура оригинала %d пикс" % over]))
            status = ("BLOCKED_GEOMETRY" if blocked else
                      "REWORK" if mg["geometry"] == "REWORK" or over else "CANDIDATE")
            meta = {"asset_id": j["asset_id"], "master": j["master"], "frame": j["frame"], "cells": j["cells"],
                    "what": j["what"], "src": j["src"], "generator_rev": R.grev, "guide_rev": R.guide_rev,
                    "cut_rev": R.cut_rev, "attempts": attempts, "report": rep,
                    "checks": {x: list(c[x]) for x in sp.pa.MACHINE_CHECKS}, "machine": verdict,
                    "outcome": sp.pa.outcome(verdict, len(attempts)), "place": prep,
                    "geometry_orig": j["geometry_orig"], "geometry_decision": j["geometry_decision"],
                    "ref": j.get("ref_rep"), "negative": gen_fire.NEGATIVE,
                    "file": pp.replace("\\", "/"), "sha256": sha256_file(pp), "status": status,
                    "status_why": mg["geometry_why"] if status == "REWORK" else "",
                    "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with open(os.path.join(meta_dir, j["name"] + ".json"), "w", encoding=ENC) as f:
                json.dump(meta, f, ensure_ascii=False, indent=1)
            cells.append(("%s %s" % (j["master"], status), j, attempts[-1]["raw"], hd, mg))
            print("%-5s %-20s %-16s модель %s / %s, края %s, вне клеток %d, дальше оригинала %d | готово %d из %d, прошло %.0f мин" % (
                j["master"], j["asset_id"], status, mg.get("dw_pct"), mg.get("dh_pct"), mg.get("edges"),
                prep["outside_grid_px"], prep["beyond_orig_px"], n, len(plan), (time.time() - t0) / 60), flush=True)
    except sp.Budget:
        print("лимит процесса: новых рендеров %d из %d - выхожу, продолжит новый процесс" % (R.renders, R.max),
              flush=True)
        sys.exit(sp.EXIT_MORE)
    if cells:
        sheet(cells, os.path.join(args.out, "sheet.png"))
    ex = {"generator_rev": R.grev, "guide_rev": R.guide_rev, "guide": sg.GUIDE_V1, "cut_rev": R.cut_rev,
          "params": pr.RENDER_V1, "prompt": ITEM, "negative": gen_fire.NEGATIVE, "c_text": sp.C_TEXT,
          "items": len(plan), "renders_last_process": R.renders, "gpuq_job": os.environ.get("GPUQ_JOB_ID", ""),
          "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if edit:
        ex.update(engine="edit", params=EDIT_RUN, model_rev=EDIT_MODEL_REV, prompt=EDIT_ITEM, c_text="")
    if not args.recut:
        with open(os.path.join(args.out, "execution.json"), "w", encoding=ENC) as f:
            json.dump(ex, f, ensure_ascii=False, indent=1)
    print("готово: мастеров %d, новых рендеров в этом процессе %d" % (len(cells), R.renders), flush=True)


if __name__ == "__main__":
    main()
