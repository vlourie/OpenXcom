#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Разворот героя GOV_4 (Vitali 04.10): одна картинка - стоящая фигура во всех 8 направлениях, одним заказом
модели, чтобы лицо, одежда и причёска были одни и те же во всех ракурсах. Пять частей направления 3 (unit_parts)
это не решали: каждый ракурс отдельным заказом - каждый раз другой человек, спина и профиль выдуманы.

Вход 1 - восемь фигур оригинала (поза «стоит» без оружия, собраны как движок - unit_pilot.compose), сетка 4x2,
один масштаб на всех, bicubic на подложке; порядок направлений 0..7 слева направо, сверху вниз. Меток и подписей во
входе нет (R-204). Вход 2 - эталон Vitali d3_p1 (облик и манера письма). Входов два, ~1 Мп (R-205).
Модель - Qwen-Image-Edit-2511 + Lightning (item_photo.EditPainter), как unit_direct. Ответ - как есть, без вырезки:
это проба разворота, не игровой ассет. Не выдержала модель ракурсы - записать, а не чинить (R-208).

Без модели (входы, промпт, лист без ответа):
    py -3.13 tools/hdart/unit_turnaround.py --dry-run
С моделью - только через очередь:
    py -3.13 tools/gpuq.py add --name gov4_turnaround --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/unit_turnaround.py
Выход art/units/pilot-gov4/turnaround/: in1.png, in2.png, prompt.txt, raw.s<seed>.png, sheet.s<seed>.png
(оригинал nearest | ответ, в одном масштабе; и ряд по направлениям), meta.s<seed>.json."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import json                             # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import item_photo as ip                 # noqa: E402
import unit_pilot as up                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ENC = "utf-8-sig"
OUT = os.path.join("art", "units", "pilot-gov4", "turnaround")
REF = os.path.join("art", "units", "pilot-gov4", "reference", "d3_p1.png")
PANEL = (176, 176, 182)                 # как unit_direct
COLS, ROWS = 4, 2
SIZE = (1152, 896)                      # ~1 Мп, кратно 32, пропорция сетки 4x2
POSE = 0                                # «стоит», без оружия: оружие - свой слой HANDOB
DIRS = ["0 вверх-вправо", "1 вправо", "2 вниз-вправо", "3 к зрителю",
        "4 вниз-влево", "5 влево", "6 вверх-влево", "7 от зрителя"]
# причёска - по ракурсам 0, 1, 5, 6, 7 листа: длинный светлый хвост на затылке, не короткая стрижка (up.WHO судил по
# виду спереди)
WHO = up.WHO.replace(", bare hands", "").replace("short blond hair", "blond hair pulled back into a long ponytail")
PROMPT = ("<image1> is a character turnaround sheet from a tactical game: eight tiny low-resolution pixel sprites, "
          "enlarged, of ONE and the same standing person, arranged in two rows of four on a flat panel of colour "
          "RGB({r}, {g}, {b}). All eight are seen from above at the same fixed isometric camera of the game; the "
          "person turns in steps of 45 degrees: top row from left to right - facing up-right away from the viewer, "
          "facing right in profile, facing down-right towards the viewer, facing the viewer; bottom row - facing "
          "down-left towards the viewer, facing left in profile, facing up-left away from the viewer, facing "
          "straight away from the viewer with the back turned. <image2> is the finished artwork of this same person "
          "seen from the front. Redraw the whole sheet of <image1> as a finished character turnaround of the same "
          "quality and the same painting style as <image2>: in all eight figures exactly the same person as "
          "<image2> - {who}. Where a figure turns away, show the back of her head with the long blond ponytail "
          "hanging down between the shoulder blades and the back of the black coverall; in profile the ponytail is "
          "seen behind her head. She holds no weapon: empty relaxed hands at her sides. Keep for every one "
          "of the eight figures exactly its position, size, orientation, pose and silhouette from <image1>, the "
          "same camera from above, the light from the upper left. Natural human anatomy. Keep the flat plain panel "
          "of colour RGB({r}, {g}, {b}) between the figures: no floor, no shadows on the panel, no other objects, "
          "no frames, no labels, no text.")


# --restyle (Vitali 04.10): второй проход - согласованный по ракурсам разворот (raw.s<seed>.png) перерисовать
# в манере эталона. Первый проход взял пиксельную манеру спрайта (R-211): вход A - разворот как есть, B - он же
# с размытием, чтобы лесенки, которую модель обводит (R-160), на входе не было
RESTYLE_PROMPT = ("<image1> is a rough draft of a character turnaround sheet: eight views of one and the same "
                  "standing woman in two rows of four on a flat panel of colour RGB({r}, {g}, {b}); the draft has "
                  "blocky low-detail edges and flat orange skin. <image2> is the finished artwork of this same woman "
                  "seen from the front. Repaint every one of the eight figures of <image1> as a finished artwork of "
                  "the quality and the painting style of <image2>: smooth clean outlines, painted shading, the "
                  "natural light skin tone of <image2>, real fabric folds of the black flight coverall, the same "
                  "dark aviator sunglasses as <image2>, the long blond ponytail. Keep for every figure exactly its "
                  "position, size, orientation, pose and silhouette from <image1>, the red patches where they are, "
                  "no weapon, empty hands. Keep the flat plain panel of colour RGB({r}, {g}, {b}) between the "
                  "figures: no floor, no shadows on the panel, no other objects, no frames, no labels, no text.")
RESTYLE_BLUR = 3.0                      # радиус размытия входа B в пикселях рендера (фигура x12.4 базы)

# --refonly (Vitali 04.10): тот же разворот, но вход один - эталон d3_p1, без спрайтов: пиксельной лесенки, которую
# модель держит как форму (R-160, R-211), на входе нет вовсе. Ракурсы - только словами. Полный режим без Lightning
# (40 шагов, cfg 4): на 8 шагах при cfg 1 модель к промпту почти глуха (R-008). Память - две фазы weapons_probe5
# (R-213): текстовая модель и трансформер на карте не вместе
REFONLY_PROMPT = ("<image1> is the finished artwork of one person seen from the front: {who}. Redraw it as a "
                  "character turnaround sheet for a tactical game, in the same quality and the same painting style "
                  "as <image1>: eight full-body views of ONE and the same standing person, arranged in two rows of "
                  "four on a flat panel of colour RGB({r}, {g}, {b}), all eight figures the same size and standing "
                  "on the same baseline, all seen slightly from above at the same fixed isometric camera of the "
                  "game. The person turns in steps of 45 degrees: top row from left to right - facing up-right away "
                  "from the viewer, facing right in profile, facing down-right towards the viewer, facing the "
                  "viewer; bottom row - facing down-left towards the viewer, facing left in profile, facing up-left "
                  "away from the viewer, facing straight away from the viewer with the back turned. In all eight "
                  "figures exactly the same person, face, hair, sunglasses, coverall, patches and boots as <image1>. "
                  "Where a figure turns away, show the back of her head with the long blond ponytail hanging down "
                  "between the shoulder blades and the back of the black coverall; in profile the ponytail is seen "
                  "behind her head. She holds no weapon: empty relaxed hands at her sides. The light from the upper "
                  "left. Natural human anatomy. Keep the flat plain panel of colour RGB({r}, {g}, {b}) between the "
                  "figures: no floor, no shadows on the panel, no other objects, no frames, no labels, no text.")
REFONLY_NEG = ("pixel art, blocky stair-stepped edges, low resolution, different people, different clothes, extra "
               "figures, missing figures, weapon, floor, cast shadow, frames, labels, text")
REFONLY_RUN = {"steps": 40, "cfg": 4.0, "lora": 0.0, "lightning": None}


# --units (Vitali 04.10): по эталону одному модель повороты на 45 градусов не умеет (#363: только спереди, профиль
# и спина). Ракурсы держит лист спрайтов - вход 1 как у первого черновика (8 фигур bicubic, сетка 4x2), но для
# остальных юнитов рас STR_GOVT* и Смышленой девки; эталона у них нет, вход один. Полный режим 40 шагов cfg 4 с
# негативом против пиксель-арта (первый черновик шёл Lightning cfg 1 - негатив не действовал, R-008), память - две
# фазы (R-213). Пилот GOV_4 - контроль того же режима против черновика 1
UNITS_OUT = os.path.join("art", "units", "turnaround")
VALUES = os.path.join(".index", "mod", "Piratez", "rul", "values.tsv")
# облик - по листу 8 направлений каждого юнита (in1.png), смотрел глазами 04.10; на 32x40 детали условны (R-125)
LOOKS = {
    # чемодана нет (Vitali 04.10: в оригинале его нет; на кукле его нет, в боевом листе он в кадрах левой руки)
    "STR_GOVT_AGENT": ("a male government secret agent with short brown hair and dark sunglasses, in a black business "
                       "suit with a white shirt collar and a black tie, black shoes, empty hands"),
    # --faces: «камуфляж» и «сегменты» модель рисовала пятнами без формы (#370) - броня названа гладкими пластинами
    "STR_GOVT_ENFORCER": ("a government trooper in smooth matte dark charcoal-grey combat armour made of large clean "
                          "solid plates, a full closed helmet with two small green glowing eye lenses, armoured gloves "
                          "and heavy boots, no camouflage pattern"),
    "STR_GOVT_ELITE": ("a government special forces soldier in bulky smooth matte dark-grey heavy combat armour made "
                       "of large clean solid plates with big rounded shoulder pads, a full closed helmet with three "
                       "round green glowing lenses on one side, armoured gloves and heavy boots, no camouflage "
                       "pattern"),
    "STR_GOVT_MP": ("a government military policeman in a black uniform and a black helmet with a black face mask "
                    "that leaves only the mouth and chin bare, bare hands, black boots"),
    # голова в спрайте - группа лица (кожа); ref: оранжевая лысина в 7 клетках из 8 - кожа названа явно
    "STR_GOVT_GENERAL": ("a heavy-set bald male general with the same natural skin on the whole bald head and the "
                         "face in every figure, in a black heavy armoured uniform with big rounded shoulder "
                         "plates and a small green badge on the chest, black gloves and black boots"),
    "STR_GOVT_SIREN": ("a fit woman with long black hair, fair skin and bare muscular arms, in a black sleeveless "
                       "top, black trousers and black boots"),
    "STR_GOVT_ROGUE_COLONEL": ("a bald male colonel in smooth matte dark-grey heavy combat armour made of large clean "
                               "solid plates, big shoulder plates with red markings, armoured gloves and heavy "
                               "boots"),
    "STR_HUMAN_FEMALE_4": ("a sturdy woman with shoulder-length auburn hair, in a black leather jacket, brown "
                           "trousers and black boots"),
    # руки рабочих в спрайте - группа 6, та же, что лицо (spriteFaceGroup 6, BattleUnit::setRecolor перекрашивает её
    # по облику); на кукле рукава закатаны выше локтя - это голая кожа, а не оранжевые перчатки (bv2: сзади перчатки)
    "STR_HUMAN_LABOURER": ("a male construction labourer in a yellow hard hat and a brown work coverall with the "
                           "short sleeves rolled up above the elbows, bare forearms and bare hands of the same natural "
                           "skin as his face in every figure, no gloves, brown work boots"),
    "STR_HUMAN_LABOURER_FEM": ("a woman, a female labourer with a feminine face and figure and short platinum blond "
                               "hair, in a brown work coverall with the short sleeves rolled up above the elbows, bare "
                               "forearms and bare hands of the same natural skin as her face in every figure, no "
                               "gloves, brown work boots"),
    "STR_HUMAN_MALE_3": ("a burly man with a shaved head and a dark beard, bare muscular arms, an open red "
                         "sleeveless vest over a grey shirt, dark brown trousers and boots"),
    # --faces: по кукле (in2_doll) - золотистый комбинезон и кудри до плеч, а не хаки и хвост
    "STR_HUMAN_CITY_GIRL": ("a young woman with tanned skin and shoulder-length curly brown hair, in a shiny "
                            "golden-yellow one-piece jumpsuit with a zip down the front and wide baggy trousers, "
                            "golden-yellow boots"),
    "STR_GOVT_PILOT": WHO,
}
UNITS_PROMPT = ("<image1> is a character turnaround sheet from a tactical game: eight tiny low-resolution pixel "
                "sprites, enlarged, of ONE and the same standing person, arranged in two rows of four on a flat panel "
                "of colour RGB({r}, {g}, {b}). All eight are seen from above at the same fixed isometric camera of "
                "the game; the person turns in steps of 45 degrees: top row from left to right - facing up-right away "
                "from the viewer, facing right in profile, facing down-right towards the viewer, facing the viewer; "
                "bottom row - facing down-left towards the viewer, facing left in profile, facing up-left away from "
                "the viewer, facing straight away from the viewer with the back turned. The person is {who}. Repaint "
                "the whole sheet as a finished, detailed character turnaround in a realistic painted illustration "
                "style: smooth clean outlines, painted shading, natural skin tones, real fabric folds and materials, "
                "natural human anatomy and proportions. In all eight figures exactly the same person, face, hair and "
                "clothes. Keep for every one of the eight figures its place on the sheet, its size, the direction it "
                "faces, its pose and its colour areas from <image1>; the same camera from above, the light from the "
                "upper left. Keep the flat plain panel of colour RGB({r}, {g}, {b}) between the figures: no floor, no "
                "shadows on the panel, no other objects, no frames, no labels, no text.")
UNITS_NEG = ("pixel art, blocky stair-stepped edges, jagged outline, low resolution, flat orange skin, different "
             "people, different clothes, extra figures, missing figures, weapon, floor, cast shadow, frames, labels, "
             "text")


# --units --pixel (Vitali 04.10, после #365): нужен пиксель-арт, как у первого черновика - режим черновика 1
# (Lightning 8 шагов, cfg 1, промпт черновика без эталона), но с двумя фазами памяти (R-213): EditPainter держит
# текстовую модель в закреплённой RAM, это shared карты. Выход raw_px/sheet_px, #365 не затирается
PIXEL_PROMPT = ("<image1> is a character turnaround sheet from a tactical game: eight tiny low-resolution pixel "
                "sprites, enlarged, of ONE and the same standing person, arranged in two rows of four on a flat panel "
                "of colour RGB({r}, {g}, {b}). All eight are seen from above at the same fixed isometric camera of "
                "the game; the person turns in steps of 45 degrees: top row from left to right - facing up-right away "
                "from the viewer, facing right in profile, facing down-right towards the viewer, facing the viewer; "
                "bottom row - facing down-left towards the viewer, facing left in profile, facing up-left away from "
                "the viewer, facing straight away from the viewer with the back turned. Redraw the whole sheet of "
                "<image1> as a finished character turnaround: in all eight figures exactly the same person - {who}. "
                "Keep for every one of the eight figures exactly its position, size, orientation, pose and silhouette "
                "from <image1>, the same camera from above, the light from the upper left. Natural human anatomy. "
                "Keep the flat plain panel of colour RGB({r}, {g}, {b}) between the figures: no floor, no shadows on "
                "the panel, no other objects, no frames, no labels, no text.")
PIXEL_RUN = {"steps": 8, "cfg": 1.0, "lora": 0.0, "lightning": "8steps bf16"}


# --units --doll (Vitali 04.10): «как первый экземпляр» - вход как у черновика 1: лист спрайтов плюс вид спереди
# второй картинкой. У черновика это был эталон d3_p1, у остальных эталона нет - вид спереди даёт кукла инвентаря
# юнита (armors.spriteInv). Генератор, seed, шаги, размер - те же (pixel_phases); промпт - черновика 1 без
# примет пилота. Контроль: пилот с d3_p1 и промптом черновика 1 обязан повторить raw.s5200.png черновика
DOLL_PROMPT = ("<image1> is a character turnaround sheet from a tactical game: eight tiny low-resolution pixel "
               "sprites, enlarged, of ONE and the same standing person, arranged in two rows of four on a flat panel "
               "of colour RGB({r}, {g}, {b}). All eight are seen from above at the same fixed isometric camera of the "
               "game; the person turns in steps of 45 degrees: top row from left to right - facing up-right away "
               "from the viewer, facing right in profile, facing down-right towards the viewer, facing the viewer; "
               "bottom row - facing down-left towards the viewer, facing left in profile, facing up-left away from "
               "the viewer, facing straight away from the viewer with the back turned. <image2> is the picture of "
               "this same person seen from the front. Redraw the whole sheet of <image1> as a finished character "
               "turnaround of the same quality and the same painting style as <image2>: in all eight figures exactly "
               "the same person as <image2> - {who}. Where a figure turns away, show the back of the head and the "
               "back of the clothes. The person holds nothing: empty relaxed hands at the sides. Keep for every one "
               "of the eight figures exactly its position, size, orientation, pose and silhouette from <image1>, the "
               "same camera from above, the light from the upper left. Natural human anatomy. Keep the flat plain "
               "panel of colour RGB({r}, {g}, {b}) between the figures: no floor, no shadows on the panel, no other "
               "objects, no frames, no labels, no text.")
# --units --doll --faces (Vitali 04.10, после #370): у 7 юнитов из 13 клетка 3 (к зрителю) вышла затылком, у рабочих
# спиной все 8 (R-217) - лицо в спрайте 32x40 в 2-3 пикселя, модель его не видит. Здесь ракурс каждой клетки назван
# словами вместе с тем, что в ней видно (лицо или затылок); меток на входе нет (R-204). Входы, сид, генератор - как --doll
FACES_PROMPT = ("<image1> is a character turnaround sheet from a tactical game: eight tiny low-resolution pixel "
                "sprites, enlarged, of ONE and the same standing person, arranged in two rows of four on a flat panel "
                "of colour RGB({r}, {g}, {b}), all seen from above at the same fixed isometric camera of the game. "
                "<image2> is the picture of this same person seen from the front. Redraw the whole sheet of <image1> "
                "as a finished character turnaround of the same quality and the same painting style as <image2>: in "
                "all eight figures exactly the same person as <image2> - {who}. Each figure faces its own direction, "
                "draw exactly this: top row, first figure - three-quarter back view turned to the upper right, we "
                "see the back of the head and the back of the clothes, the face is hidden; top row, second figure - "
                "right side profile, the face seen from the side; top row, third figure - three-quarter front view "
                "turned to the lower right, the face is visible; top row, fourth figure - full front view, the face "
                "and the chest look straight at the viewer, exactly like <image2>; bottom row, first figure - "
                "three-quarter front view turned to the lower left, the face is visible; bottom row, second figure - "
                "left side profile, the face seen from the side; bottom row, third figure - three-quarter back view "
                "turned to the upper left, we see the back of the head, the face is hidden; bottom row, fourth "
                "figure - full back view, only the back of the head and the back of the clothes, no face. Three "
                "figures show the face, two show the profile, three show the back of the head. The person "
                "holds nothing: empty relaxed hands at the sides. Keep for every one of the eight figures exactly its "
                "position, size, pose and silhouette from <image1>, the same camera from above, the light from the "
                "upper left. Natural human anatomy. Keep the flat plain panel of colour RGB({r}, {g}, {b}) between "
                "the figures: no floor, no shadows on the panel, no other objects, no frames, no labels, no text.")
# --units --bv (Vitali 04.10, после #372: «броня пиксельная, ботинки не у всех нормальные - попробуй с графическим
# движком»): ракурс, свет и направления - из battle_view (вид unit, facing 0-7), лицо или затылок по клетке - как
# FACES_PROMPT (R-217). Вход 2 - вид спереди #365, как --ref365. Вход 1 - лист спрайтов, размытый на BV_BLUR:
# дизеринг брони спрайта модель переносила шумом (R-004 - вход только гладкий). --full: 40 шагов, cfg 4, негатив
# battle_view плюс BV_NEG (на Lightning cfg 1 негатив не действует, R-008)
BV_BLUR = 4.0                           # пикселей рендера; клетка базы ~x12
BV_SEEN = {0: "only the back of the head, no face", 1: "the face seen from the side",
           2: "the face is visible", 3: "the face and the chest look straight at the viewer, exactly like <image2>",
           4: "the face is visible", 5: "the face seen from the side",
           6: "only the back of the head, no face",
           7: "seen strictly from behind: the back of the head, the hair and the back of the clothes, no eyes, "
              "no nose, no mouth"}
BV_PROMPT = ("<image1> is a character turnaround sheet from a tactical game: eight small blurred sprites of ONE and "
             "the same standing person, arranged in two rows of four on a flat panel of colour RGB({r}, {g}, {b}). "
             "<image2> is the finished artwork of this same person seen from the front. Redraw the whole sheet of "
             "<image1> as a finished character turnaround of the same quality and the same painting style as "
             "<image2>: in all eight figures exactly the same person as <image2> - {who}. Every figure: {view}. "
             "Each figure faces its own direction, draw exactly this: {dirs}. Three figures show the face, two "
             "show the profile, three show the back of the head. Clean smooth surfaces and crisp "
             "outlines like <image2>: armour plates, cloth and leather are painted as solid smooth materials with "
             "clear edges and soft shading, no pixel noise, no dithering, no blocky stair-stepped edges. Both feet "
             "in a complete matching pair of boots or shoes, soles flat on the ground, natural human anatomy, the "
             "natural skin tone of <image2>. The person holds nothing: empty relaxed hands. Keep for every one of "
             "the eight figures exactly its position, size, pose and silhouette from <image1>. Keep the flat plain "
             "panel of colour RGB({r}, {g}, {b}) between the figures: no floor, no shadows on the panel, no other "
             "objects, no frames, no labels, no text. Do not write any letters, digits or numbers anywhere on "
             "the sheet.")
BV_NEG = ("pixel art, pixelated, dithering, noise, blocky stair-stepped edges, jagged outline, low resolution, flat "
          "orange skin, missing feet, broken boots, mismatched shoes, deformed legs, extra limbs, different people, "
          "different clothes, weapon, briefcase, bag, floor, frame, text")
BV_FULL_RUN = {"steps": 40, "cfg": 4.0, "lora": 0.0, "lightning": None}
# --bv --solid (04.10, после #374): броня ENFORCER вышла оплывшими буграми без конструкции - просим цельные
# поверхности С конструкцией (пластины, швы, сочленения). Что кубики от шахматки спрайта - гипотеза, не довод.
# Вид сзади и спиной 3/4 - по критерию приёмки: ракурс тела, затылок, ни лица, ни глаз; руки и кисти - как в
# спрайте (не задаём тыльную сторону кистей - 04.10, положение кистей следует исходнику)
BV_SEEN_SOLID = {
    0: "the body turned away: we see the back of the head, the back and the shoulder blades, arms and hands in the "
       "same position as in <image1>, no face, no eyes",
    1: "the face seen from the side", 2: "the face is visible",
    3: "the face and the chest look straight at the viewer, exactly like <image2>", 4: "the face is visible",
    5: "the face seen from the side",
    6: "the body turned away: we see the back of the head, the back and the shoulder blades, arms and hands in the "
       "same position as in <image1>, no face, no eyes",
    7: "the body turned straight away: we see the back of the head and the hair and the whole back, arms and hands "
       "in the same position as in <image1>, no face, no eyes, no nose, no mouth"}
BV_SOLID = ("Every surface keeps the real construction of the outfit of <image2>: armour is made of separate rigid "
            "plates, each plate one solid continuous surface with straight or evenly curved edges, clear seams and "
            "joints between the plates, plates follow the body and the limbs; cloth and leather are solid continuous "
            "materials with clear seams and folds; soft painted shading, crisp outlines.")
BV_SOLID_NEG = ", melted shapes, lumpy blobs, shapeless armour, faces on the back, eyes on the back of the head"


def bv_prompt(who, solid=False):
    import battle_view as bv
    order = ["top row, first figure", "top row, second figure", "top row, third figure", "top row, fourth figure",
             "bottom row, first figure", "bottom row, second figure", "bottom row, third figure",
             "bottom row, fourth figure"]
    seen = BV_SEEN_SOLID if solid else BV_SEEN
    dirs = "; ".join("%s - %s, %s" % (order[d], bv.facing(d), seen[d]) for d in range(8))
    blk = bv.prompt_block("unit")
    prompt = BV_PROMPT.format(r=PANEL[0], g=PANEL[1], b=PANEL[2], who=who, view=blk["positive"], dirs=dirs)
    neg = blk["negative"] + ", " + BV_NEG
    if solid:
        prompt = prompt.replace("Clean smooth surfaces and crisp outlines like <image2>: armour plates, cloth and "
                                "leather are painted as solid smooth materials with clear edges and soft shading, no "
                                "pixel noise, no dithering, no blocky stair-stepped edges.", BV_SOLID)
        assert BV_SOLID in prompt
        neg += BV_SOLID_NEG
    return prompt, neg


RESOURCES = os.path.join(up.PZ, "Piratez", "Ruleset", "Piratez_Resources.rul")
# в боевом листе GOV_1 чемодан нарисован в кадрах левой руки стоя (LARM_STAND 0-7), на кукле агента его нет
NO_CASE = {"STR_GOVT_AGENT"}


def doll_input(arm, V):
    """Кукла инвентаря брони (spriteInv) вписана по высоте в SIZE на подложке, как ref_input. Фон куклы - цвет
    угла (чёрный или зелёный) -> подложка."""
    import re
    import numpy as np
    name = V[("armors", arm, "spriteInv")]
    with open(RESOURCES, encoding="utf-8") as f:
        m = re.search(r"typeSingle: %s\s*\n\s*fileSingle: (\S+)" % re.escape(name), f.read())
    if not m:
        raise SystemExit("нет файла куклы %s в %s" % (name, RESOURCES))
    path = os.path.join(up.PZ, "Piratez", m.group(1))
    rgb = np.asarray(Image.open(path).convert("RGB")).copy()
    fg = np.any(rgb != rgb[0, 0], axis=2)
    ys, xs = np.nonzero(fg)
    a = np.where(fg, 255, 0).astype(np.uint8)
    fig = Image.fromarray(np.dstack([rgb, a]), "RGBA").crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    k = min(SIZE[0] * 0.9 / fig.width, SIZE[1] * 0.9 / fig.height)
    fig = fig.resize((round(fig.width * k), round(fig.height * k)), Image.LANCZOS)
    flat = Image.new("RGBA", SIZE, PANEL + (255,))
    flat.alpha_composite(fig, ((SIZE[0] - fig.width) // 2, (SIZE[1] - fig.height) // 2))
    return flat.convert("RGB"), path


def front365_input(out):
    """--ref365 (Vitali 04.10, после #371): вид спереди - клетка 3 готового рисунка #365 (raw.s5200.png, 40 шагов
    cfg 4), как d3_p1 у черновика 1, а не пиксельная кукла. У агента - front365_clean.png (чемодан стёрт руками).
    Фон клетки - заливкой от краёв по близости к медиане края; фигура вписана по высоте в SIZE на подложке."""
    import numpy as np
    clean = os.path.join(out, "front365_clean.png")
    src = clean if os.path.isfile(clean) else os.path.join(out, "raw.s5200.png")
    im = Image.open(src).convert("RGB")
    if src != clean:
        cw, ch = SIZE[0] // COLS, SIZE[1] // ROWS
        im = im.crop((3 * cw, 0, 4 * cw, ch))
    a = np.asarray(im).astype(int)
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    near = np.abs(a - np.median(edge, axis=0)).max(axis=2) <= 18
    # copy(): floodfill по картинке из fromarray молча ничего не заливает - буфер numpy
    m = Image.fromarray(np.where(near, 0, 255).astype(np.uint8)).copy()
    for xy in ((0, 0), (m.width - 1, 0), (0, m.height - 1), (m.width - 1, m.height - 1)):
        ImageDraw.floodfill(m, xy, 128)
    alpha = Image.fromarray(np.where(np.asarray(m) == 128, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
    fig = im.convert("RGBA")
    fig.putalpha(alpha)
    fig = fig.crop(alpha.point(lambda v: 255 if v > 128 else 0).getbbox())
    k = min(SIZE[0] * 0.9 / fig.width, SIZE[1] * 0.9 / fig.height)
    fig = fig.resize((round(fig.width * k), round(fig.height * k)), Image.LANCZOS)
    flat = Image.new("RGBA", SIZE, PANEL + (255,))
    flat.alpha_composite(fig, ((SIZE[0] - fig.width) // 2, (SIZE[1] - fig.height) // 2))
    return flat.convert("RGB"), src


def drop_case(frames, pal):
    """Стереть чемодан из кадров левой руки стоя: всё ниже нижней строки кожи и светло-серое без оттенка."""
    import numpy as np
    for d in range(8):
        idx = frames[up.LARM_STAND + d].copy()
        rgb = np.asarray(up.rgba(idx, pal))[..., :3].astype(int)
        on = idx > 0
        skin = on & (rgb[..., 0] > rgb[..., 2] + 40)
        if not skin.any():
            continue
        rows = np.nonzero(skin.any(axis=1))[0]
        idx[rows.max() + 1:, :] = 0
        # светло-серое - только на строках кисти: выше это блики рукава, их стирание дырявит руку
        grey = on & ~skin & (np.abs(rgb[..., 0] - rgb[..., 2]) < 20) & (rgb.sum(axis=2) > 3 * 70)
        grey[:rows.min(), :] = False
        idx[grey] = 0
        frames[up.LARM_STAND + d] = idx


def pixel_phases(models, jobs, lightning=True):
    """Две фазы, как weapons_probe5.two_phase, но с Lightning LoRA (подключается до fp8, как photo_ui.Painter) и
    без негатива (cfg 1). jobs: [(картинка или список картинок, промпт)] -> пайплайн и вложения (pe, pm) в RAM.
    lightning=False (--bv --full): без LoRA, job (картинки, промпт, негатив) -> вложения (pe, pm, npe, npm)."""
    import gc
    import torch
    from diffusers import FlowMatchEulerDiscreteScheduler, QwenImageEditPlusPipeline, QwenImageTransformer2DModel
    from diffusers.hooks import apply_layerwise_casting
    from transformers import Qwen2_5_VLForConditionalGeneration
    import photo_ui as pu
    import weapons_probe5 as w5
    pu.models_env(models)
    dev = torch.device("cuda")
    te = Qwen2_5_VLForConditionalGeneration.from_pretrained(pu.MODEL, subfolder="text_encoder",
                                                            torch_dtype=torch.bfloat16)
    apply_layerwise_casting(te, storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16,
                            skip_modules_pattern=("embed", "norm", "lm_head", "rotary"))
    te.to(dev)
    pipe = QwenImageEditPlusPipeline.from_pretrained(pu.MODEL, transformer=None, text_encoder=te,
                                                     torch_dtype=torch.bfloat16)
    from diffusers.pipelines.qwenimage import pipeline_qwenimage_edit_plus as m
    if w5.gpu_mem("текстовая модель") > 0.5:
        raise SystemExit("текстовая модель ушла в shared - стоп")
    embeds = []
    with torch.no_grad():
        for job in jobs:
            imgs, prompt = job[0], job[1]
            cond = []
            for img in (imgs if isinstance(imgs, list) else [imgs]):
                dims = m.calculate_dimensions(m.CONDITION_IMAGE_SIZE, img.width / float(img.height))
                cond.append(pipe.image_processor.resize(img, int(dims[1]), int(dims[0])))
            ts = pipe._get_qwen_prompt_embeds(prompt, cond, dev, torch.bfloat16)
            if len(job) > 2:
                ts = ts + pipe._get_qwen_prompt_embeds(job[2], cond, dev, torch.bfloat16)
            embeds.append(tuple(t.to("cpu") for t in ts))
    pipe.register_modules(text_encoder=None)
    del te
    gc.collect()
    torch.cuda.empty_cache()
    w5.gpu_mem("текстовая модель выгружена")
    tr = QwenImageTransformer2DModel.from_pretrained(pu.MODEL, subfolder="transformer", torch_dtype=torch.bfloat16)
    pipe.register_modules(transformer=tr)
    if lightning:
        path = pu.pick_lora(pu.LIGHTNING[0], ("8steps", "bf16"))
        pipe.load_lora_weights(os.path.dirname(path), weight_name=os.path.basename(path), adapter_name="lightning")
        pipe.set_adapters(["lightning"], [1.0])
        print("Lightning LoRA:", os.path.basename(path), flush=True)
    tr.enable_layerwise_casting(storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16,
                                skip_modules_pattern=("pos_embed", "patch_embed", "norm", r"^proj_in$",
                                                      r"^proj_out$", "lora"))
    tr.to(dev)
    pipe.vae.to(dev)
    if lightning:
        pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(pu.LIGHTNING_SCHEDULER)
    pipe.set_progress_bar_config(disable=True)
    gc.collect()
    if w5.gpu_mem("трансформер") > 0.5:
        raise SystemExit("трансформер ушёл в shared - стоп")
    return pipe, embeds


def rul_values():
    import csv
    csv.field_size_limit(10 ** 9)
    V = {}
    with open(VALUES, encoding=ENC, newline="") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):     # R-109
            if len(row) >= 4:
                try:
                    V[tuple(row[:3])] = json.loads(row[3])
                except ValueError:
                    V[tuple(row[:3])] = row[3]
    return V


class RulUnit:
    """Лист юнита по рулсету Пираток и перекраска брони (BattleUnit::setRecolor, вид 0): как up.Sources для figures."""
    layers = up.Sources.layers

    def __init__(self, uid, V, pal, no_case=False):
        import numpy as np
        arm = V[("units", uid, "armor")]
        self.arm = arm
        self.sheet = V[("armors", arm, "spriteSheet")].replace(".PCK", "")
        self.frames = up.load_frames(os.path.join(up.PZ, "Piratez", "Resources", "Sprites", self.sheet + ".png"))
        self.pal = pal
        if no_case:
            drop_case(self.frames, pal)
        t = np.arange(256)
        for g, c in (("spriteFaceGroup", "spriteFaceColor"), ("spriteHairGroup", "spriteHairColor"),
                     ("spriteUtileGroup", "spriteUtileColor"), ("spriteRankGroup", "spriteRankColor")):
            gv, cv = V.get(("armors", arm, g)), V.get(("armors", arm, c))
            if gv and cv and cv[0] > 0:
                t = np.where((t & 0xF0) == gv << 4, (t & 15) + cv[0], t)
        self.table = np.clip(t, 0, 255).astype(np.uint8)

    def classic(self, src, k):
        idx = self.frames[src[1]]
        if not idx.any():
            return None
        return up.rgba(self.table[idx], self.pal).resize((up.W * k, up.H * k), Image.NEAREST)


def units(a):
    V, pal = rul_values(), up.load_palette()
    jobs = []
    for uid, who in LOOKS.items():
        if a.only and uid not in a.only:
            continue
        u = RulUnit(uid, V, pal)
        figs = figures(u)
        in1 = grid(figs, Image.BICUBIC)
        out = os.path.join(UNITS_OUT, uid)
        os.makedirs(out, exist_ok=True)
        in1.save(os.path.join(out, "in1.png"))
        if a.pixel:
            prompt = PIXEL_PROMPT.format(r=PANEL[0], g=PANEL[1], b=PANEL[2], who=who or "?")
            with open(os.path.join(out, "prompt_px.txt"), "w", encoding=ENC) as f:
                f.write(prompt + "\n")
        else:
            prompt = UNITS_PROMPT.format(r=PANEL[0], g=PANEL[1], b=PANEL[2], who=who or "?")
            with open(os.path.join(out, "prompt.txt"), "w", encoding=ENC) as f:
                f.write(prompt + "\n\nnegative: " + UNITS_NEG + "\n")
        print("%s: лист %s, облик %s" % (uid, u.sheet, "есть" if who else "НЕТ"), flush=True)
        jobs.append((uid, u.sheet, figs, in1, prompt, out))
    if a.dry_run:
        return
    missing = [j[0] for j in jobs if not LOOKS[j[0]]]
    if missing:
        raise SystemExit("нет облика: %s" % ", ".join(missing))
    import gen_hd
    import photo_ui as pu
    import torch
    import weapons_probe5 as w5
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
    if a.pixel:
        pixel_units(a, models, jobs)
        return
    pipe, embeds = w5.two_phase(models, [(j[3], j[4], UNITS_NEG) for j in jobs])
    for (uid, sheet_name, figs, in1, prompt, out), emb in zip(jobs, embeds):
        pe, pm, npe, npm = (t.to("cuda") for t in emb)
        for seed in a.seeds:
            t0 = time.time()
            with torch.no_grad():
                raw = pipe(image=[in1], prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                           negative_prompt_embeds=npe, negative_prompt_embeds_mask=npm,
                           true_cfg_scale=REFONLY_RUN["cfg"], num_inference_steps=REFONLY_RUN["steps"],
                           width=SIZE[0], height=SIZE[1],
                           generator=torch.Generator("cuda").manual_seed(seed)).images[0].convert("RGB")
            if w5.gpu_mem("%s сид %d" % (uid, seed)) > 0.5:
                raise SystemExit("ушло в shared - стоп")
            raw.save(os.path.join(out, "raw.s%d.png" % seed))
            sheet(figs, raw, os.path.join(out, "sheet.s%d.png" % seed),
                  "%s (%s), разворот по листу спрайтов, 40 шагов cfg 4, seed %d" % (uid, sheet_name, seed))
            meta = {"unit": uid, "sheet": sheet_name, "seed": seed, "size": SIZE, "panel": PANEL,
                    "run": REFONLY_RUN, "model_rev": ip.EDIT_MODEL_REV, "prompt": prompt, "negative": UNITS_NEG,
                    "inputs": ["in1.png: 8 фигур оригинала bicubic, сетка 4x2, перекраска брони"],
                    "seconds": round(time.time() - t0, 1), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with open(os.path.join(out, "meta.s%d.json" % seed), "w", encoding=ENC) as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=1)
            print("%s сид %d: %.0f с" % (uid, seed, time.time() - t0), flush=True)


def doll_units(a):
    """--units --doll: лист спрайтов + кукла, как черновик 1. Выход raw_doll/sheet_doll/meta_doll/in2_doll; первым -
    контроль: пилот входами черновика 1 (d3_p1, PROMPT) -> STR_GOVT_PILOT/raw_draft1, сверка с черновиком."""
    import numpy as np
    V, pal = rul_values(), up.load_palette()
    jobs = []
    kind = "ref" if a.ref365 else "face" if a.faces else "doll"
    if (not a.only and not a.faces and not a.ref365) or (a.only and "draft1" in a.only):
        figs = figures(up.Sources())
        out = os.path.join(UNITS_OUT, "STR_GOVT_PILOT")
        os.makedirs(out, exist_ok=True)
        jobs.append(("draft1", "GOV_4", figs, [grid(figs, Image.BICUBIC), ref_input()],
                     PROMPT.format(r=PANEL[0], g=PANEL[1], b=PANEL[2], who=WHO), out, REF))
    for uid, who in LOOKS.items():
        if a.only and uid not in a.only:
            continue
        u = RulUnit(uid, V, pal, no_case=uid in NO_CASE)
        figs = figures(u)
        in1 = grid(figs, Image.BICUBIC)
        out = os.path.join(UNITS_OUT, uid)
        os.makedirs(out, exist_ok=True)
        in2, doll = front365_input(out) if a.ref365 else doll_input(u.arm, V)
        in1.save(os.path.join(out, "in1_doll.png"))
        in2.save(os.path.join(out, "in2_%s.png" % kind))
        prompt = (FACES_PROMPT if (a.faces or a.ref365) else DOLL_PROMPT).format(r=PANEL[0], g=PANEL[1], b=PANEL[2], who=who)
        with open(os.path.join(out, "prompt_%s.txt" % kind), "w", encoding=ENC) as f:
            f.write(prompt + "\n")
        print("%s: лист %s, кукла %s%s" % (uid, u.sheet, os.path.basename(doll),
                                         ", чемодан стёрт" if uid in NO_CASE else ""), flush=True)
        jobs.append((uid, u.sheet, figs, [in1, in2], prompt, out, doll))
    if a.dry_run:
        return
    import gen_hd
    import photo_ui as pu
    import torch
    import weapons_probe5 as w5
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
    pipe, embeds = pixel_phases(models, [(j[3], j[4]) for j in jobs])
    for (uid, sheet_name, figs, ins, prompt, out, src2), emb in zip(jobs, embeds):
        pe, pm = (t.to("cuda") for t in emb)
        for seed in a.seeds:
            t0 = time.time()
            with torch.no_grad():
                raw = pipe(image=ins, prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                           true_cfg_scale=PIXEL_RUN["cfg"], num_inference_steps=PIXEL_RUN["steps"],
                           width=SIZE[0], height=SIZE[1],
                           generator=torch.Generator("cuda").manual_seed(seed)).images[0].convert("RGB")
            if w5.gpu_mem("%s сид %d" % (uid, seed)) > 0.5:
                raise SystemExit("ушло в shared - стоп")
            tag = "draft1" if uid == "draft1" else kind
            raw.save(os.path.join(out, "raw_%s.s%d.png" % (tag, seed)))
            if uid == "draft1":
                old = os.path.join(OUT, "raw.s%d.png" % seed)
                if os.path.isfile(old):
                    d = np.abs(np.asarray(raw, float) - np.asarray(Image.open(old).convert("RGB"), float))
                    print("контроль черновика 1, сид %d: средняя разница %.2f из 255, макс %.0f"
                          % (seed, d.mean(), d.max()), flush=True)
            else:
                sheet(figs, raw, os.path.join(out, "sheet_%s.s%d.png" % (kind, seed)),
                      "%s (%s), лист спрайтов + %s, %s (Lightning 8 шагов), seed %d"
                      % (uid, sheet_name, "вид спереди #365" if a.ref365 else "кукла",
                         "ракурсы словами" if (a.faces or a.ref365) else "как черновик 1", seed))
            meta = {"unit": uid, "sheet": sheet_name, "seed": seed, "size": SIZE, "panel": PANEL,
                    "run": PIXEL_RUN, "model_rev": ip.EDIT_MODEL_REV, "prompt": prompt,
                    "inputs": ["лист 8 фигур оригинала bicubic, сетка 4x2" +
                               (", чемодан стёрт" if uid in NO_CASE else ""), "вид спереди: " + src2],
                    "seconds": round(time.time() - t0, 1), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with open(os.path.join(out, "meta_%s.s%d.json" % (tag, seed)), "w", encoding=ENC) as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=1)
            print("%s сид %d: %.0f с" % (uid, seed, time.time() - t0), flush=True)


def bv_units(a):
    """--units --bv [--full]: лист спрайтов, размытый на BV_BLUR, + вид спереди #365; промпт bv_prompt (battle_view).
    Выход raw_bv/raw_bvfull, sheet_*, meta_*, prompt_*, in1_bv.png."""
    from PIL import ImageFilter
    V, pal = rul_values(), up.load_palette()
    kind = a.tag or ("bvfull" if a.full else "bv")
    run = BV_FULL_RUN if a.full else PIXEL_RUN
    blur = BV_BLUR if a.blur is None else a.blur
    jobs = []
    for uid, who in LOOKS.items():
        if a.only and uid not in a.only:
            continue
        u = RulUnit(uid, V, pal, no_case=uid in NO_CASE)
        figs = figures(u)
        in1 = grid(figs, Image.BICUBIC).filter(ImageFilter.GaussianBlur(blur))
        out = os.path.join(UNITS_OUT, uid)
        os.makedirs(out, exist_ok=True)
        in2, src2 = front365_input(out)
        in1.save(os.path.join(out, "in1_%s.png" % kind))
        prompt, neg = bv_prompt(who, solid=a.solid)
        with open(os.path.join(out, "prompt_%s.txt" % kind), "w", encoding=ENC) as f:
            f.write(prompt + ("\n\nnegative: " + neg if a.full else "") + "\n")
        print("%s: лист %s, вид спереди %s" % (uid, u.sheet, os.path.basename(src2)), flush=True)
        jobs.append((uid, u.sheet, figs, [in1, in2], prompt, neg, out, src2))
    if a.dry_run:
        print(jobs[0][4] if jobs else "", flush=True)
        return
    import gen_hd
    import photo_ui as pu
    import torch
    import weapons_probe5 as w5
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
    pipe, embeds = pixel_phases(models, [(j[3], j[4], j[5]) if a.full else (j[3], j[4]) for j in jobs],
                                lightning=not a.full)
    for (uid, sheet_name, figs, ins, prompt, neg, out, src2), emb in zip(jobs, embeds):
        emb = [t.to("cuda") for t in emb]
        extra = {"negative_prompt_embeds": emb[2], "negative_prompt_embeds_mask": emb[3]} if a.full else {}
        for seed in a.seeds:
            t0 = time.time()
            with torch.no_grad():
                raw = pipe(image=ins, prompt=None, prompt_embeds=emb[0], prompt_embeds_mask=emb[1],
                           true_cfg_scale=run["cfg"], num_inference_steps=run["steps"],
                           width=SIZE[0], height=SIZE[1], **extra,
                           generator=torch.Generator("cuda").manual_seed(seed)).images[0].convert("RGB")
            if w5.gpu_mem("%s сид %d" % (uid, seed)) > 0.5:
                raise SystemExit("ушло в shared - стоп")
            raw.save(os.path.join(out, "raw_%s.s%d.png" % (kind, seed)))
            sheet(figs, raw, os.path.join(out, "sheet_%s.s%d.png" % (kind, seed)),
                  "%s (%s), battle_view, вход 1 размыт %.0f, вид спереди #365, %s, seed %d"
                  % (uid, sheet_name, blur, "40 шагов cfg 4" if a.full else "Lightning 8 шагов", seed))
            meta = {"unit": uid, "sheet": sheet_name, "seed": seed, "size": SIZE, "panel": PANEL, "run": run,
                    "model_rev": ip.EDIT_MODEL_REV, "prompt": prompt, "negative": neg if a.full else None,
                    "inputs": ["лист 8 фигур оригинала bicubic, размытие %.1f, сетка 4x2" % blur +
                               (", чемодан стёрт" if uid in NO_CASE else ""), "вид спереди: " + src2],
                    "seconds": round(time.time() - t0, 1), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with open(os.path.join(out, "meta_%s.s%d.json" % (kind, seed)), "w", encoding=ENC) as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=1)
            print("%s сид %d: %.0f с" % (uid, seed, time.time() - t0), flush=True)


# --fix-cell (Vitali 04.10, после #380): у FEMALE_4 клетка 7 (спиной) повторила вид спереди (R-217). Перерисовать
# одну клетку: вход 1 - исходная клетка спрайта (как в листе --bv: bicubic, размытие BV_BLUR, тот же layout), вход 2 -
# удачные задние виды этого же ответа (--ref-cells), вида спереди во входах нет. Клетка рисуется целиком в
# FIX_SIZE (клетка x2.5, та же доля) и вставляется в лист клеткой, без растяжки и склейки тела. Остальные 7 - как были
FIX_SIZE = (720, 1120)                  # клетка 288x448 x2.5, кратно 16
FIX_PROMPT = ("<image1> is one small blurred sprite from a tactical game: {who}, {facing}, on a flat panel of colour "
              "RGB({r}, {g}, {b}). <image2> shows finished artwork of this same person seen "
              "{angles}. The result is a single picture of exactly one person, alone, in the place of <image1>; "
              "do not repeat the figures of <image2>. Redraw <image1> as finished artwork of the same quality and the same painting "
              "style as <image2>: exactly the same person, the same hair, the same clothes, armour and boots as "
              "<image2>. {seen}. Keep exactly the pose of <image1>: the same wide stance of the feet, the same "
              "position of the arms and the hands, the same size and position of the figure in the picture. "
              "Camera: {view}. {solid} Both feet in a complete matching pair of boots, soles flat on the ground, "
              "natural human anatomy. The person holds nothing. Keep the flat plain panel of colour RGB({r}, {g}, "
              "{b}) around the figure: no floor, no shadows on the panel, no other objects, no frames, no text.")
FIX_NEG = ", face, eyes, nose, mouth, front view, chest, the figure facing the viewer"
# #383: опора из двух фигур рядом - в ответе три фигуры на белом фоне (модель повторила раскладку входа 2)
FIX_NEG_MANY = (", two people, three people, several figures, multiple views, character turnaround sheet, "
                "white background, gradient background")
# #386: опора - целая фигура спиной 3/4 (клетка 6), и клетка 7 вышла её копией: тот же поворот, ноги вразнобой (R-211).
# --ref-upper: в опору только верх клетки (голова, волосы, куртка до пояса) - ног и стойки во входе 2 нет
FIX_UPPER = 0.58                        # доля высоты клетки: голова и куртка до пояса у всех фигур листа
FIX_POSE = (" <image2> shows only the head and the upper body: take from it only the hair, the clothes and the armour. The pose, "
            "the turn of the body, the stance of the legs and the camera come only from <image1>.")
# #387: опора без ног, а поворот 3/4 и низкая камера всё равно с опоры, вокруг пол и стена/небо (R-211).
# --start S: старт с латентов входа 1 (клетка спрайта), пока шум >= S холст держится на нём (как unit_parts.run) -
# стойку, камеру и подложку задаёт клетка, а не опора. Несколько значений через запятую
FIX_NEG_SCENE = ", floor tiles, wall, room, sky, horizon, landscape"
FIX_NEG_TURN = ", three-quarter view, turned body, narrow stance, feet together"


def panel_fill(cell, panel):
    """Подложка ответа, связанная с краем клетки (близость к медиане края <= 18), - цветом panel; фигура не трогается.
    Модель правки отдаёт клетку на своей подложке (#386: тёмно-серая и голубая), в листе она выпадает."""
    import cv2
    import numpy as np
    a = np.asarray(cell.convert("RGB")).astype(int)
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    near = (np.abs(a - np.median(edge, axis=0)).max(axis=2) <= 18).astype(np.uint8)
    _, lab = cv2.connectedComponents(near, connectivity=4)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bg = (np.isin(lab, list(border)) & (near > 0)).astype(np.float32)
    al = cv2.GaussianBlur(bg, (5, 5), 0)[..., None]
    out = a * (1 - al) + np.array(panel, float) * al
    return Image.fromarray(out.round().astype(np.uint8), "RGB")


def fix_cell(a):
    """--units --fix-cell D --tag T --only U [--ref-cells 0,6]: перерисовать клетку D ответа raw_T. Выход:
    raw_T_cellD (клетка FIX_SIZE), raw_TfD (лист с новой клеткой), fixD_T.png (оригинал -> было -> стало)."""
    import battle_view as bv
    from PIL import ImageFilter
    V, pal = rul_values(), up.load_palette()
    d, kind, uid = a.fix_cell, a.tag, a.only[0]
    refs = [int(x) for x in a.ref_cells.split(",")]
    who = LOOKS[uid]
    u = RulUnit(uid, V, pal, no_case=uid in NO_CASE)
    figs = figures(u)
    out = os.path.join(UNITS_OUT, uid)
    raw = Image.open(os.path.join(out, "raw_%s.s5200.png" % kind)).convert("RGB").resize(SIZE, Image.LANCZOS)
    cw, ch = SIZE[0] // COLS, SIZE[1] // ROWS
    box = lambda c: ((c % COLS) * cw, (c // COLS) * ch, (c % COLS + 1) * cw, (c // COLS + 1) * ch)  # noqa: E731
    blur = BV_BLUR if a.blur is None else a.blur
    sprite = grid(figs, Image.BICUBIC).filter(ImageFilter.GaussianBlur(blur)).crop(box(d))
    in1 = sprite.resize(FIX_SIZE, Image.BICUBIC)
    rh = round(ch * FIX_UPPER) if a.ref_upper else ch
    in2 = Image.new("RGB", (cw * len(refs), rh), PANEL)
    for i, c in enumerate(refs):
        in2.paste(raw.crop(box(c)).crop((0, 0, cw, rh)), (i * cw, 0))
    in2 = in2.resize((in2.width * 2, in2.height * 2), Image.LANCZOS)
    cid = "%d%s" % (d, a.fix_suffix)       # имя пробы: клетка и суффикс, прежние пробы не затираются
    in1.save(os.path.join(out, "in1_%s_cell%s.png" % (kind, cid)))
    in2.save(os.path.join(out, "in2_%s_cell%s.png" % (kind, cid)))
    blk = bv.prompt_block("unit")
    # с какой стороны видна опора; запрет лица (FIX_NEG) - только клеткам спиной (0, 6, 7), у прочих лицо видно
    angles = ("from different angles" if len(refs) > 1 else
              {7: "from behind at a straight back view", 0: "from behind at a three-quarter angle",
               6: "from behind at a three-quarter angle", 3: "from the front",
               2: "from the front at a three-quarter angle", 4: "from the front at a three-quarter angle",
               1: "from the side, in profile", 5: "from the side, in profile"}[refs[0]])
    prompt = FIX_PROMPT.format(who=who, facing=bv.facing(d), r=PANEL[0], g=PANEL[1], b=PANEL[2], angles=angles,
                               seen=BV_SEEN_SOLID[d][0].upper() + BV_SEEN_SOLID[d][1:], view=blk["positive"],
                               solid=BV_SOLID)
    if a.ref_upper:
        prompt = prompt.replace("do not repeat the figures of <image2>.",
                                "do not repeat the figures of <image2>." + FIX_POSE)
    neg = blk["negative"] + ", " + BV_NEG + BV_SOLID_NEG + (FIX_NEG if d in (0, 6, 7) else "") + FIX_NEG_MANY
    if a.start:
        neg += FIX_NEG_SCENE + (FIX_NEG_TURN if d in (3, 7) else "")
    starts = [float(x) for x in a.start.split(",")] if a.start else [None]
    with open(os.path.join(out, "prompt_%s_cell%s.txt" % (kind, cid)), "w", encoding=ENC) as f:
        f.write(prompt + "\n\nnegative: " + neg + "\n")
    print("%s: клетка %d, опоры %s" % (uid, d, refs), flush=True)
    if a.dry_run:
        print(prompt, flush=True)
        return
    import gen_hd
    import photo_ui as pu
    import torch
    import weapons_probe5 as w5
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
    pipe, embeds = pixel_phases(models, [([in1, in2], prompt, neg)], lightning=False)
    emb = [t.to("cuda") for t in embeds[0]]
    run = BV_FULL_RUN
    init = None
    if a.start:
        dev = torch.device("cuda")
        with torch.no_grad():
            t = pipe.image_processor.preprocess(in1, FIX_SIZE[1], FIX_SIZE[0]).unsqueeze(2).to(dev, torch.bfloat16)
            lat = pipe._encode_vae_image(t, generator=None)
            C = pipe.transformer.config.in_channels // 4
            init = pipe._pack_latents(lat, 1, C, lat.shape[3], lat.shape[4])
            # доказательство: init обратно через VAE - это клетка спрайта, а не что-то иное
            std = torch.tensor(pipe.vae.config.latents_std).view(1, -1, 1, 1, 1).to(dev, lat.dtype)
            mean = torch.tensor(pipe.vae.config.latents_mean).view(1, -1, 1, 1, 1).to(dev, lat.dtype)
            back = pipe.vae.decode(lat * std + mean, return_dict=False)[0][:, :, 0]   # как в конце pipe.__call__
            pipe.image_processor.postprocess(back, output_type="pil")[0].save(
                os.path.join(out, "init_%s_cell%s.png" % (kind, cid)))
        print("init: латенты клетки %s, упакованы %s" % (tuple(lat.shape), tuple(init.shape)), flush=True)
    for start, seed in [(s, sd) for s in starts for sd in a.seeds]:
        t0 = time.time()
        kw = {}
        if start is not None:
            g = torch.Generator("cuda").manual_seed(seed + 1)
            noise = torch.randn(init.shape, generator=g, device=init.device, dtype=torch.float32).to(init.dtype)
            held = []

            # после шага i латенты стоят на сигме sigmas[i+1]; пока она >= start, ответ модели выбрасывается и
            # латенты ставятся заново: sg * шум + (1 - sg) * init (прямой зашумитель flow matching)
            def cb(pp, i, _t, k, noise=noise, start=start, held=held):
                if i == 0 and k["latents"].shape != init.shape:
                    raise SystemExit("латенты конвейера %s, init %s - не совпали" % (tuple(k["latents"].shape),
                                                                                    tuple(init.shape)))
                sg = float(pp.scheduler.sigmas[i + 1])
                if sg >= start:
                    held.append((i, sg))
                    return {"latents": sg * noise + (1.0 - sg) * init}
                return {"latents": k["latents"]}
            kw = {"callback_on_step_end": cb, "callback_on_step_end_tensor_inputs": ["latents"]}
        with torch.no_grad():
            cell = pipe(image=[in1, in2], prompt=None, prompt_embeds=emb[0], prompt_embeds_mask=emb[1],
                        negative_prompt_embeds=emb[2], negative_prompt_embeds_mask=emb[3],
                        true_cfg_scale=run["cfg"], num_inference_steps=run["steps"],
                        width=FIX_SIZE[0], height=FIX_SIZE[1],
                        generator=torch.Generator("cuda").manual_seed(seed), **kw).images[0].convert("RGB")
        if start is not None:
            print("старт %.2f: латенты заменялись клеткой на шагах 0..%d (%d из %d), отпущены на сигме %.4f - "
                  "доля клетки %.3f, шума %.3f" % (start, held[-1][0], len(held), run["steps"], held[-1][1],
                                                    1 - held[-1][1], held[-1][1]), flush=True)
        if w5.gpu_mem("%s клетка %d сид %d" % (uid, d, seed)) > 0.5:
            raise SystemExit("ушло в shared - стоп")
        cid = "%d%s%s" % (d, a.fix_suffix, "" if start is None else "st%02d" % round(start * 100))
        cell.save(os.path.join(out, "raw_%s_cell%s.s%d.png" % (kind, cid, seed)))
        sheet_new = raw.copy()
        sheet_new.paste(panel_fill(cell, PANEL).resize((cw, ch), Image.LANCZOS), box(d)[:2])
        sheet_new.save(os.path.join(out, "raw_%sf%s.s%d.png" % (kind, cid, seed)))
        # оригинал -> было -> стало, по высоте FIX_SIZE
        f = up.font(18)
        cmp_ = Image.new("RGB", (FIX_SIZE[0] * 3 + 40, FIX_SIZE[1] + 30), (24, 24, 24))
        dr = ImageDraw.Draw(cmp_)
        panes = [("оригинал (nearest)", grid(figs, Image.NEAREST).crop(box(d)).resize(FIX_SIZE, Image.NEAREST)),
                 ("было (%s)" % kind, raw.crop(box(d)).resize(FIX_SIZE, Image.LANCZOS)), ("стало", cell)]
        for i, (t, im) in enumerate(panes):
            cmp_.paste(im, (10 + i * (FIX_SIZE[0] + 10), 30))
            dr.text((10 + i * (FIX_SIZE[0] + 10), 6), t, fill=(230, 230, 230), font=f)
        cmp_.save(os.path.join(out, "fix%s_%s.s%d.png" % (cid, kind, seed)))
        meta = {"unit": uid, "cell": d, "seed": seed, "size": FIX_SIZE, "run": run, "model_rev": ip.EDIT_MODEL_REV,
                "prompt": prompt, "negative": neg, "ref_cells": refs, "source": "raw_%s.s5200.png" % kind,
                "start": start, "ref_upper": bool(a.ref_upper),
                "held": None if start is None else {"steps": [h[0] for h in held], "release_sigma": held[-1][1]},
                "inputs": ["клетка %d спрайта bicubic, размытие %.1f, layout листа, x2.5" % (d, blur),
                           "клетки %s ответа %s рядом, x2" % (refs, kind)],
                "seconds": round(time.time() - t0, 1), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with open(os.path.join(out, "meta_%s_cell%s.s%d.json" % (kind, cid, seed)), "w", encoding=ENC) as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=1)
        print("%s клетка %d сид %d: %.0f с" % (uid, d, seed, time.time() - t0), flush=True)


def pixel_units(a, models, jobs):
    import torch
    import weapons_probe5 as w5
    pipe, embeds = pixel_phases(models, [(j[3], j[4]) for j in jobs])
    for (uid, sheet_name, figs, in1, prompt, out), emb in zip(jobs, embeds):
        pe, pm = (t.to("cuda") for t in emb)
        for seed in a.seeds:
            t0 = time.time()
            with torch.no_grad():
                raw = pipe(image=[in1], prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                           true_cfg_scale=PIXEL_RUN["cfg"], num_inference_steps=PIXEL_RUN["steps"],
                           width=SIZE[0], height=SIZE[1],
                           generator=torch.Generator("cuda").manual_seed(seed)).images[0].convert("RGB")
            if w5.gpu_mem("%s сид %d" % (uid, seed)) > 0.5:
                raise SystemExit("ушло в shared - стоп")
            raw.save(os.path.join(out, "raw_px.s%d.png" % seed))
            sheet(figs, raw, os.path.join(out, "sheet_px.s%d.png" % seed),
                  "%s (%s), разворот по листу спрайтов, режим черновика 1 (Lightning 8 шагов), seed %d"
                  % (uid, sheet_name, seed))
            meta = {"unit": uid, "sheet": sheet_name, "seed": seed, "size": SIZE, "panel": PANEL,
                    "run": PIXEL_RUN, "model_rev": ip.EDIT_MODEL_REV, "prompt": prompt,
                    "inputs": ["in1.png: 8 фигур оригинала bicubic, сетка 4x2, перекраска брони"],
                    "seconds": round(time.time() - t0, 1), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with open(os.path.join(out, "meta_px.s%d.json" % seed), "w", encoding=ENC) as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=1)
            print("%s сид %d: %.0f с" % (uid, seed, time.time() - t0), flush=True)


def refonly(a):
    figs = figures(up.Sources())
    in1 = ref_input()
    prompt = REFONLY_PROMPT.format(r=PANEL[0], g=PANEL[1], b=PANEL[2], who=WHO)
    with open(os.path.join(OUT, "refonly_prompt.txt"), "w", encoding=ENC) as f:
        f.write(prompt + "\n\nnegative: " + REFONLY_NEG + "\n")
    in1.save(os.path.join(OUT, "refonly_in1.png"))
    print("refonly: вход - только эталон %s, сиды %s" % (REF, a.seeds), flush=True)
    if a.dry_run:
        return
    import gen_hd
    import photo_ui as pu
    import torch
    import weapons_probe5 as w5
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
    pipe, embeds = w5.two_phase(models, [(in1, prompt, REFONLY_NEG)])
    pe, pm, npe, npm = (t.to("cuda") for t in embeds[0])
    for seed in a.seeds:
        t0 = time.time()
        with torch.no_grad():
            raw = pipe(image=[in1], prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                       negative_prompt_embeds=npe, negative_prompt_embeds_mask=npm,
                       true_cfg_scale=REFONLY_RUN["cfg"], num_inference_steps=REFONLY_RUN["steps"],
                       width=SIZE[0], height=SIZE[1],
                       generator=torch.Generator("cuda").manual_seed(seed)).images[0].convert("RGB")
        if w5.gpu_mem("сид %d" % seed) > 0.5:
            raise SystemExit("ушло в shared - стоп")
        raw.save(os.path.join(OUT, "refonly_raw.s%d.png" % seed))
        sheet(figs, raw, os.path.join(OUT, "refonly_sheet.s%d.png" % seed),
              "GOV_4, разворот: вход - только эталон d3_p1, 40 шагов cfg 4, seed %d" % seed)
        meta = {"seed": seed, "size": SIZE, "panel": PANEL, "run": REFONLY_RUN, "model_rev": ip.EDIT_MODEL_REV,
                "prompt": prompt, "negative": REFONLY_NEG, "inputs": ["refonly_in1.png: эталон " + REF],
                "seconds": round(time.time() - t0, 1), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with open(os.path.join(OUT, "refonly_meta.s%d.json" % seed), "w", encoding=ENC) as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=1)
        print("сид %d: %.0f с" % (seed, time.time() - t0), flush=True)


def restyle(a):
    from PIL import ImageFilter
    src = Image.open(os.path.join(OUT, "raw.s%d.png" % a.src_seed)).convert("RGB").resize(SIZE, Image.LANCZOS)
    ins = {"A": src, "B": src.filter(ImageFilter.GaussianBlur(RESTYLE_BLUR))}
    in2 = ref_input()
    prompt = RESTYLE_PROMPT.format(r=PANEL[0], g=PANEL[1], b=PANEL[2])
    for v, im in ins.items():
        im.save(os.path.join(OUT, "restyle_in1_%s.png" % v))
    with open(os.path.join(OUT, "restyle_prompt.txt"), "w", encoding=ENC) as f:
        f.write(prompt + "\n")
    print("restyle: вход raw.s%d.png, варианты %s" % (a.src_seed, ",".join(ins)), flush=True)
    if a.dry_run:
        return
    import gen_hd
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    painter = ip.EditPainter(models)
    import torch
    outs = []
    for v, im in ins.items():
        t0 = time.time()
        res = painter.pipe(prompt=prompt, image=[im, in2], num_inference_steps=ip.EDIT_RUN["steps"],
                           generator=torch.Generator("cpu").manual_seed(a.seed), true_cfg_scale=ip.EDIT_RUN["cfg"],
                           width=SIZE[0], height=SIZE[1])
        raw = res.images[0].convert("RGB")
        raw.save(os.path.join(OUT, "restyle_%s.s%d.png" % (v, a.seed)))
        outs.append((v, raw))
        print("вариант %s: %.0f с" % (v, time.time() - t0), flush=True)
    # лист: черновик | A | B, по направлениям
    cw, ch = SIZE[0] // COLS, SIZE[1] // ROWS
    rows = [("черновик (проход 1)", src)] + [("вариант %s" % v, r) for v, r in outs]
    gap, top, f = 10, 30, up.font(14)
    tw, th = cw * 2 // 3, ch * 2 // 3
    out = Image.new("RGB", (gap + 8 * (tw + gap), top + 20 + len(rows) * (th + 26)), (24, 24, 24))
    dr = ImageDraw.Draw(out)
    dr.text((gap, 6), "GOV_4, разворот: проход 2 в манере эталона (A - черновик как есть, B - размыт), seed %d"
            % a.seed, fill=(230, 230, 230), font=f)
    for d in range(8):
        dr.text((gap + d * (tw + gap), top), DIRS[d], fill=(200, 200, 200), font=up.font(12))
    y = top + 20
    for label, im in rows:
        dr.text((gap, y), label, fill=(255, 220, 120), font=up.font(13))
        y += 20
        for d in range(8):
            cx, cy = (d % COLS) * cw, (d // COLS) * ch
            out.paste(im.crop((cx, cy, cx + cw, cy + ch)).resize((tw, th), Image.LANCZOS),
                      (gap + d * (tw + gap), y))
        y += th + 6
    out.save(os.path.join(OUT, "restyle_sheet.s%d.png" % a.seed))
    meta = {"src": "raw.s%d.png" % a.src_seed, "seed": a.seed, "blur_B": RESTYLE_BLUR, "prompt": prompt,
            "run": ip.EDIT_RUN, "model_rev": ip.EDIT_MODEL_REV, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(OUT, "restyle_meta.s%d.json" % a.seed), "w", encoding=ENC) as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    if torch.cuda.is_available():
        print("пик памяти карты %.1f ГБ" % (torch.cuda.max_memory_allocated() / 2 ** 30), flush=True)


def figures(s):
    """Восемь фигур оригинала (кроп общего габарита, чтобы ступни стояли на одной линии)."""
    full = [up.compose(s.layers(up.POSES[POSE], d), s.classic, 1)[0] for d in range(8)]
    box = None
    for im in full:
        bb = im.split()[3].getbbox()
        box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]), max(box[2], bb[2]), max(box[3], bb[3]))
    return [im.crop(box) for im in full]


def layout(figs):
    """Сетка 4x2 в размере SIZE: клетка, масштаб (один на всех) и левый верхний угол каждой фигуры."""
    cw, ch = SIZE[0] // COLS, SIZE[1] // ROWS
    fw, fh = figs[0].size
    z = min(cw / fw, ch / fh) * 0.86
    w, h = round(fw * z), round(fh * z)
    at = [((d % COLS) * cw + (cw - w) // 2, (d // COLS) * ch + (ch - h) // 2) for d in range(8)]
    return z, (w, h), at


def grid(figs, resample):
    z, (w, h), at = layout(figs)
    out = Image.new("RGBA", SIZE, PANEL + (255,))
    for im, xy in zip(figs, at):
        out.alpha_composite(im.resize((w, h), resample), xy)
    return out.convert("RGB")


def ref_input():
    """Эталон целиком, вписан по высоте в SIZE на подложке."""
    ref = Image.open(REF).convert("RGBA")
    fig = ref.crop(ref.split()[3].point(lambda v: 255 if v > 128 else 0).getbbox())
    k = min(SIZE[0] * 0.9 / fig.width, SIZE[1] * 0.9 / fig.height)
    fig = fig.resize((round(fig.width * k), round(fig.height * k)), Image.LANCZOS)
    flat = Image.new("RGBA", SIZE, PANEL + (255,))
    flat.alpha_composite(fig, ((SIZE[0] - fig.width) // 2, (SIZE[1] - fig.height) // 2))
    return flat.convert("RGB")


def sheet(figs, raw, path, title):
    """Верх: оригинал nearest | ответ во весь размер. Низ: по направлениям - оригинал над ответом, вырезка клетки."""
    orig = grid(figs, Image.NEAREST)
    panes = [("оригинал (nearest)", orig)] + ([("ответ модели", raw.resize(SIZE, Image.LANCZOS))] if raw else [])
    gap, top, f = 12, 28, up.font(15)
    cw, ch = SIZE[0] // COLS, SIZE[1] // ROWS
    pairs = len(panes)
    W = max(len(panes) * SIZE[0] + (len(panes) + 1) * gap, 8 * (cw // 2 + gap) + gap)
    H = top + SIZE[1] + gap + 22 + pairs * (ch // 2 + 4) + gap
    out = Image.new("RGB", (W, H), (24, 24, 24))
    dr = ImageDraw.Draw(out)
    dr.text((gap, 6), title, fill=(230, 230, 230), font=f)
    for i, (t, im) in enumerate(panes):
        x = gap + i * (SIZE[0] + gap)
        out.paste(im, (x, top))
        dr.text((x + 4, top + 4), t, fill=(20, 20, 20), font=f)
    y0 = top + SIZE[1] + gap
    for d in range(8):
        x = gap + d * (cw // 2 + gap)
        dr.text((x, y0), DIRS[d], fill=(230, 230, 230), font=up.font(13))
        cx, cy = (d % COLS) * cw, (d // COLS) * ch
        for j, (_t, im) in enumerate(panes):
            c = im.crop((cx, cy, cx + cw, cy + ch)).resize((cw // 2, ch // 2), Image.LANCZOS)
            out.paste(c, (x, y0 + 22 + j * (ch // 2 + 4)))
    out.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=up.SEED)
    ap.add_argument("--models", default=None)
    ap.add_argument("--dry-run", action="store_true", help="входы, промпт и лист без ответа; модель не грузится")
    ap.add_argument("--restyle", action="store_true", help="проход 2: разворот raw.s<src-seed> в манере эталона")
    ap.add_argument("--src-seed", type=int, default=up.SEED)
    ap.add_argument("--refonly", action="store_true", help="разворот только по эталону, без спрайтов на входе")
    ap.add_argument("--seeds", type=lambda s: [int(x) for x in s.split(",")], default=[up.SEED, up.SEED + 1])
    ap.add_argument("--units", action="store_true", help="разворот остальных юнитов STR_GOVT* по листу спрайтов")
    ap.add_argument("--only", type=lambda s: s.split(","), default=None, help="--units: только эти юниты")
    ap.add_argument("--pixel", action="store_true", help="--units: режим черновика 1 (Lightning), пиксель-арт")
    ap.add_argument("--doll", action="store_true", help="--units: лист спрайтов + кукла инвентаря, как черновик 1")
    ap.add_argument("--faces", action="store_true",
                    help="--doll: ракурс каждой клетки назван словами (FACES_PROMPT), выход *_face, без контроля draft1")
    ap.add_argument("--ref365", action="store_true",
                    help="--doll: вход 2 - вид спереди из рисунка #365 (front365_input), FACES_PROMPT, выход *_ref")
    ap.add_argument("--bv", action="store_true",
                    help="--units: ракурс и свет из battle_view, вход 1 размыт, вход 2 - вид спереди #365, выход *_bv")
    ap.add_argument("--full", action="store_true", help="--bv: 40 шагов, cfg 4, с негативом, выход *_bvfull")
    ap.add_argument("--solid", action="store_true",
                    help="--bv: конструкция брони и критерии вида сзади (BV_SOLID, BV_SEEN_SOLID); задавать с --tag")
    ap.add_argument("--blur", type=float, default=None, help="--bv: размытие входа 1 (по умолчанию BV_BLUR)")
    ap.add_argument("--fix-cell", type=int, default=None,
                    help="--units --tag T --only U: перерисовать одну клетку ответа raw_T (fix_cell), 40 шагов cfg 4")
    ap.add_argument("--ref-cells", default="0,6", help="--fix-cell: клетки того же ответа - опора одежды и волос")
    ap.add_argument("--ref-upper", action="store_true",
                    help="--fix-cell: в опору только верх клеток (голова и куртка до пояса), без ног и стойки")
    ap.add_argument("--start", default="",
                    help="--fix-cell: старт с латентов клетки спрайта, пока шум >= S (0.9,0.95 - по пробе на каждое)")
    ap.add_argument("--fix-suffix", default="", help="--fix-cell: суффикс имени пробы (7b), прежние не затираются")
    ap.add_argument("--tag", default=None, help="--bv: имя выхода вместо bv/bvfull (raw_<tag>, sheet_<tag>...)")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.units and a.fix_cell is not None:
        fix_cell(a)
        return
    if a.units and a.bv:
        bv_units(a)
        return
    if a.units and a.doll:
        doll_units(a)
        return
    if a.units:
        units(a)
        return
    if a.refonly:
        refonly(a)
        return
    if a.restyle:
        restyle(a)
        return
    s = up.Sources()
    figs = figures(s)
    z, wh, _at = layout(figs)
    in1, in2 = grid(figs, Image.BICUBIC), ref_input()
    prompt = PROMPT.format(r=PANEL[0], g=PANEL[1], b=PANEL[2], who=WHO)
    os.makedirs(OUT, exist_ok=True)
    in1.save(os.path.join(OUT, "in1.png"))
    in2.save(os.path.join(OUT, "in2.png"))
    with open(os.path.join(OUT, "prompt.txt"), "w", encoding=ENC) as f:
        f.write(prompt + "\n")
    title = "GOV_4, разворот 8 направлений, поза «стоит» без оружия, seed %d - Edit-2511, вход 2 - эталон d3_p1" % a.seed
    print("фигура %dx%d базы, масштаб x%.1f -> %dx%d, рендер %dx%d" % (figs[0].width, figs[0].height, z, wh[0], wh[1],
                                                                       SIZE[0], SIZE[1]), flush=True)
    if a.dry_run:
        sheet(figs, None, os.path.join(OUT, "sheet.dry.png"), title)
        print("dry-run: модель не грузилась ->", OUT)
        return
    import gen_hd
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    painter = ip.EditPainter(models)
    import torch
    t0 = time.time()
    res = painter.pipe(prompt=prompt, image=[in1, in2], num_inference_steps=ip.EDIT_RUN["steps"],
                       generator=torch.Generator("cpu").manual_seed(a.seed), true_cfg_scale=ip.EDIT_RUN["cfg"],
                       width=SIZE[0], height=SIZE[1])
    raw = res.images[0].convert("RGB")
    dt = time.time() - t0
    raw.save(os.path.join(OUT, "raw.s%d.png" % a.seed))
    sheet(figs, raw, os.path.join(OUT, "sheet.s%d.png" % a.seed), title)
    meta = {"pose": POSE, "dirs": DIRS, "seed": a.seed, "size": SIZE, "zoom": round(z, 2), "panel": PANEL,
            "run": ip.EDIT_RUN, "model_rev": ip.EDIT_MODEL_REV, "prompt": prompt,
            "inputs": ["in1.png: 8 фигур оригинала bicubic, сетка 4x2", "in2.png: эталон " + REF],
            "seconds": round(dt, 1), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(OUT, "meta.s%d.json" % a.seed), "w", encoding=ENC) as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    if torch.cuda.is_available():
        print("пик памяти карты %.1f ГБ" % (torch.cuda.max_memory_allocated() / 2 ** 30), flush=True)
    print("готово за %.0f с (с загрузкой модели) -> %s" % (dt, OUT), flush=True)


if __name__ == "__main__":
    main()
