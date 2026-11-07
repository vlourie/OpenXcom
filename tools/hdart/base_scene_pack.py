#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пак «Живой базы» (docs/research/base-living-2026-10-22.md, раздел 7а): новые картинки построек по клеткам
и файл сцены каждой клетки для HdBaseScene.

На клетку N (кадр BASEBITS, как BaseView::hdTileIndex) пишутся:
    <N>.png          картинка клетки 128x128 (k = 4), альфа - силуэт классики
    <N>.scene.txt    сцена: что за постройка и огни, центры которых лежат в этой клетке

    # base_scene_pack.py
    size 128 128                   размер картинки клетки в паке
    gate lab                      от чего горит: lab (учёные), work (инженеры), home (жильё гаснет ночью), none
    light 61.5 40.2 38.0 screen 0.45 0.85 1.00 1.70 0.31
          x y (пиксели пака от угла клетки, могут выходить за клетку), радиус, вид (steady, blink, pulse,
          screen, flicker), цвет 0..1, период с и фаза 0..1 (у blink и pulse; у прочих 0 0)

Огни ищет base_lights.py по картинке 512 на клетку (art/base_living/pilot/painted/<ТИП>@512.png).
Старые .anim.txt и фазы .v/.b движок у клетки со сценой не берёт (HdBase), поэтому их не трогаем.

В мод не пишет: выход в --out (по умолчанию art/base_living/pack), ставить - build_hd_pack (stage + install)
под очередью правок, и только постройки, выбранные Vitali (--only).

    py -3.13 tools/hdart/base_scene_pack.py --only STR_ACCESS_LIFT,STR_HANGAR
"""
import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

import base_flow_bake                               # noqa: E402
import base_lights                                  # noqa: E402
from facility_sheet import load_rules, sprites_map  # noqa: E402
from gen_base_anim import Facility                  # noqa: E402
from gen_base_paint import PILOT                    # noqa: E402

ART = os.path.join(ROOT, "art", "base_living", "pilot", "painted")
TILE = 128
ENC = "utf-8-sig"


def gate_of(rule):
    """От чего горит постройка - по тому, что она даёт базе (рулсет), а не по имени."""
    # лаборатория и мастерская - где это главное дело постройки, а не пара мест в придачу (лазарет - 1 учёный,
    # склад - 5 мест, хеллерий - 3 учёных при 75 рабочих); поле рулсета - labs (RuleBaseFacility)
    if int(rule.get("labs", 0) or 0) >= 10:
        return "lab"
    if int(rule.get("workshops", 0) or 0) >= 20:
        return "work"
    if int(rule.get("personnel", 0) or 0) > 0:
        return "home"
    return "none"


def budget(lights, cover, most):
    """Бюджет огней клетки: светлую мебель детектор берёт за лампы и ночью заливает комнату как днём (лист
    ночи 98, 22.10). Огни идут от крупных к мелким; берём, пока сумма r^2 не выйдет за cover клетки и их не
    больше most. Одобренные 16 почти все укладываются в 0.6 и 6 (кроме хеллерия - он светится задуманно)."""
    keep, s = [], 0.0
    for L in lights:
        r = float(L.split()[3]) / TILE
        if len(keep) >= most or (keep and s + r * r > cover):
            continue
        keep.append(L)
        s += r * r
    return keep


# Частицы построек (HdBaseScene::drawParticles), доли постройки u0 v0 u1 v1 по листу emit_sheet.png 22.10, цвет
# 0..1. Искры горят, только пока мастерская работает (gate work), пар тонируется светом комнаты.
EMITS = {
    "STR_ONSEN": [("steam", .15, .20, .60, .75, .95, .95, 1.0)],
    "STR_LUXURY_SPA": [("steam", .30, .30, .68, .72, .85, .90, .95)],
    "STR_HOTEL": [("steam", .60, .58, .78, .78, .95, .95, 1.0)],
    "STR_HELLERIUM_PLANT": [("bubbles", .36, .30, .60, .54, .60, 1.0, .30)],
    "STR_SLUDGE_VATS": [("bubbles", u - .07, v - .07, u + .07, v + .07, .65, 1.0, .25)
                        for u, v in ((.30, .27), (.65, .27), (.30, .63), (.65, .63))],
    "STR_WELL": [("bubbles", .41, .36, .65, .60, .65, 1.0, .30)],
    # тикет XP-000336 (27.10, Vitali «искры убрать»): искр нет нигде, у мастерской, фабрики, принтера, Кузни и
    # Монетного двора их место занимает движение «по делу» - блок XP336 ниже
    "STR_RED_FORGE": [("embers", .22, .35, .45, .58, 1.0, .45, .15)],
    "STR_STILL": [("steam", .20, .22, .65, .36, .95, .92, .85)],
    "STR_MESS_HALL": [("steam", .38, .36, .62, .62, .95, .92, .88)],
    "STR_BURROW": [("embers", .45, .40, .55, .50, 1.0, .55, .20)],
    "STR_SUMMONING_CIRCLE": [("orbit", .22, .16, .82, .76, 1.0, .40, .15)],
}

# Своя анимация у каждой постройки (Vitali 22.10: «самое главное анимации каждой комнаты») - по листам
# art/base_living/all_a/b/c.png: локаторы и турели - луч (sweep), вода - круги (ripple), склады, жильё, залы -
# пылинки в свете (dust), звери, пчёлы, фермы - мошкара (flies), разрушенное - дым (steam тёмный).
GREEN, RED, CYAN, VIOLET, ORANGE = (.45, 1.0, .55), (1.0, .30, .25), (.45, .90, 1.0), (.75, .45, 1.0), (1.0, .60, .20)
DUSTC, POLLEN, SMOKE, WATER = (1.0, .92, .75), (.85, 1.0, .45), (.30, .29, .28), (.75, .92, 1.0)


def _e(kind, box, col):
    return (kind,) + tuple(box) + tuple(col)


MID, WIDE, ROOM = (.30, .30, .70, .70), (.20, .20, .80, .80), (.15, .15, .85, .85)
MORE = {
    "STR_ACCESS_LIFT": [_e("dust", ROOM, DUSTC)],
    "STR_HANGAR": [_e("dust", ROOM, DUSTC)],
    "STR_LIVING_QUARTERS": [_e("dust", ROOM, DUSTC)],
    "STR_CORRIDOR": [_e("dust", MID, DUSTC)],
    "STR_LABORATORY": [_e("dust", ROOM, DUSTC)],
    "STR_GENERAL_STORES": [_e("dust", ROOM, DUSTC)],
    "STR_SMALL_RADAR_SYSTEM": [_e("sweep", WIDE, GREEN)],
    "STR_LASER_DEFENSES": [_e("sweep", (.25, .25, .75, .75), RED)],
    "STR_MED_BAY": [_e("dust", ROOM, DUSTC)],
    "STR_PRISON": [_e("dust", ROOM, DUSTC), _e("flies", (.35, .25, .65, .75), (.08, .07, .06))],
    "STR_GYM_ROOM": [_e("dust", ROOM, DUSTC)],
    "STR_ONSEN": [_e("ripple", (.62, .40, .85, .85), WATER)],
    "STR_LARGE_RADAR_SYSTEM": [_e("sweep", WIDE, GREEN)],
    "STR_BEAST_DEN": [_e("flies", (.25, .20, .60, .55), (.08, .07, .05))],
    "STR_LIVING_QUARTERS_LARGE": [_e("dust", ROOM, DUSTC)],
    "STR_LIVING_QUARTERS_ADVANCED_LARGE": [_e("ripple", (.42, .20, .58, .80), WATER), _e("dust", ROOM, DUSTC)],
    "STR_BUNKER_FACILITY_DAMAGED2": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_WAR_BARRACKS_DAMAGED3": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_GENERAL_STORES_XLARGE": [_e("dust", ROOM, DUSTC)],
    "STR_JAIL_DOUBLE": [_e("dust", ROOM, DUSTC)],
    "STR_ALENIUM_CHAMBER": [],          # тикет XP-000336: без воды и пузырей, только мягкая пульсация (блок XP336)
    "STR_TACTICAL_CENTER_DAMAGED": [_e("steam", MID, SMOKE)],
    "STR_FLAK_TOWER_DAMAGED": [_e("steam", MID, SMOKE)],
    "STR_GAUSS_DEFENSES": [_e("sweep", MID, CYAN)],
    "STR_LUXURY_SPA": [_e("ripple", (.32, .32, .66, .70), WATER)],
    "STR_DRUG_DEN": [_e("steam", (.40, .35, .60, .65), (.85, .70, .95))],
    "STR_LOVE_CLINIC": [_e("dust", ROOM, (1.0, .75, .85))],
    "STR_TRAP_ROOM": [_e("embers", WIDE, (1.0, .35, .20))],
    "STR_HYDROPONICS_WEED": [_e("dust", ROOM, POLLEN), _e("flies", WIDE, (.10, .10, .06))],
    "STR_BODY_FARM_E": [_e("embers", (.15, .10, .75, .65), GREEN)],
    "STR_PERSONAL_LABS": [_e("dust", ROOM, DUSTC)],
    "STR_STUDY_ROOM": [_e("dust", ROOM, DUSTC)],
    "STR_ASTROSENSORIUM": [_e("orbit", WIDE, VIOLET)],
    "STR_BLACK_TOWER": [_e("orbit", MID, RED)],
    "STR_MISSILE_DEFENSES": [_e("steam", (.30, .30, .60, .70), (.95, .95, .95))],
    "STR_MIND_SHIELD": [_e("orbit", WIDE, VIOLET)],
    "STR_LIVING_QUARTERS_SMALL": [_e("dust", ROOM, DUSTC)],
    "STR_LIVING_QUARTERS_LARGE_DAMAGED": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_LIVING_QUARTERS_ADVANCED_LARGE_DAMAGED": [_e("ripple", (.45, .20, .60, .60), WATER), _e("steam", MID, SMOKE)],
    "STR_WAR_BARRACKS": [_e("dust", ROOM, DUSTC)],
    "STR_GENERAL_STORES_DAMAGED": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_GENERAL_STORES_ARMORED": [_e("dust", ROOM, DUSTC)],
    "STR_CRYO_PRISON": [_e("steam", WIDE, (.80, .95, 1.0))],
    "STR_HANGAR_DAMAGED": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_FLAK_DEFENSES": [_e("sweep", MID, ORANGE)],
    "STR_ARMORY": [_e("dust", ROOM, DUSTC)],
    "STR_VIP_CLUB_FAC": [_e("sweep", (.30, .30, .75, .75), (1.0, .45, .85))],
    "STR_HOTEL": [_e("ripple", (.60, .58, .78, .78), WATER)],
    "STR_METAGARDEN": [_e("ripple", (.10, .65, .30, .85), WATER), _e("dust", ROOM, POLLEN)],
    "STR_FIRE_PIT": [_e("embers", MID, (1.0, .55, .20)), _e("steam", MID, SMOKE)],
    "STR_HYDROPONICS_WEED_HARVEST": [_e("dust", ROOM, POLLEN)],
    "STR_BEE_HIVE": [_e("flies", (.15, .25, .85, .85), (.95, .75, .10))],
    "STR_REFINERY": [_e("steam", (.45, .15, .75, .45), (.95, .92, .88))],
    "STR_LIBRARY": [_e("dust", ROOM, DUSTC)],
    "STR_DATA_CENTER": [_e("orbit", (.35, .30, .60, .55), CYAN)],
    "STR_NONPROFIT_LAB": [_e("dust", ROOM, DUSTC)],
    "STR_RUBBLE": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_PLASMA_DEFENSES": [_e("sweep", MID, VIOLET)],
    "STR_PSIONIC_LABORATORY": [_e("orbit", (.55, .25, .85, .80), VIOLET)],
    "STR_CAPSULE_QUARTERS": [_e("dust", ROOM, DUSTC)],
    "STR_LIVING_QUARTERS_ADVANCED": [_e("dust", ROOM, DUSTC)],
    "STR_BUNKER_FACILITY": [_e("dust", ROOM, DUSTC)],
    "STR_WAR_BARRACKS_DAMAGED1": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_GENERAL_STORES_LARGE": [_e("dust", ROOM, DUSTC)],
    "STR_GENERAL_STORES_ARMORED_DAMAGED": [_e("steam", MID, SMOKE)],
    "STR_DUNGEON": [_e("flies", WIDE, (.08, .07, .06)), _e("dust", ROOM, DUSTC)],
    "STR_SPACE_RADIO": [_e("sweep", (.25, .25, .75, .75), CYAN)],
    "STR_IRRADIATOR_TOWER": [_e("steam", (.35, .45, .70, .75), (.70, 1.0, .55))],
    "STR_VULCAN_DEFENSES": [_e("sweep", (.25, .30, .75, .70), ORANGE)],
    "STR_ARMORY_DAMAGED_1": [_e("steam", MID, SMOKE)],
    "STR_MASH": [_e("flies", (.10, .10, .60, .60), (.08, .07, .06))],
    "STR_CLONING_CENTRE": [_e("embers", (.30, .30, .80, .80), (1.0, .60, .70))],
    "STR_GAS_CHAMBER": [_e("steam", WIDE, (.60, 1.0, .40))],
    "STR_HYDROPONICS_BOOM_HARVEST": [_e("dust", ROOM, (.95, .70, 1.0))],
    "STR_CASINO": [_e("sweep", MID, (1.0, .85, .40))],
    "STR_WELL": [_e("ripple", (.41, .36, .65, .60), GREEN)],
    "STR_GREAT_LIBRARY": [_e("dust", ROOM, DUSTC)],
    "STR_COMPUTER_CORE": [_e("orbit", (.15, .25, .55, .75), CYAN)],
    "STR_LIVING_QUARTERS_DAMAGED": [_e("steam", MID, SMOKE)],
    "STR_LIVING_QUARTERS_ADVANCED_DAMAGED": [_e("steam", MID, SMOKE)],
    "STR_BUNKER_FACILITY_DAMAGED1": [_e("steam", MID, SMOKE)],
    "STR_WAR_BARRACKS_DAMAGED2": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_GENERAL_STORES_LARGE_DAMAGED": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_JAIL": [_e("dust", ROOM, DUSTC)],
    "STR_NINE_CIRCLES": [_e("orbit", (.25, .25, .75, .75), RED), _e("embers", (.42, .42, .58, .58), ORANGE)],
    "STR_TACTICAL_CENTER": [_e("orbit", (.40, .40, .65, .65), CYAN)],
    "STR_FLAK_TOWER": [_e("sweep", WIDE, ORANGE)],
    "STR_SAM_DEFENSES": [_e("sweep", MID, RED)],
    "STR_ARMORY_DAMAGED_2": [_e("steam", MID, SMOKE)],
    "STR_MESS_HALL_ADV": [_e("steam", (.55, .25, .80, .55), (.95, .92, .88)), _e("ripple", (.30, .25, .75, .70), WATER)],
    "STR_DISRUPTOR_SHROUD": [_e("orbit", WIDE, VIOLET)],
    "STR_HYDROPONICS": [_e("dust", ROOM, POLLEN)],
    "STR_BODY_FARM": [_e("embers", (.15, .10, .75, .65), GREEN)],
    "STR_FUSION_REACTOR": [_e("orbit", (.38, .40, .58, .60), ORANGE)],
    "STR_SURGERY_ROOM": [_e("dust", ROOM, DUSTC)],
    "STR_WITCH_CAVE": [_e("embers", MID, GREEN), _e("steam", MID, (.55, .85, .45))],
    "STR_RED_TOWER": [_e("ripple", MID, RED), _e("sweep", WIDE, RED)],
}
# Как в одобренном ролике (base_scene_preview.py, Vitali 22.10 «делай как в ролике»): в ролике не было ни пыли, ни
# мошкары, ни лучей и колец - тарелки и турели крутятся сами (SPIN), вода рябит и бликует (WATER). Из MORE идут
# только виды ролика: пар (и тёмный дым разрушенного), пузыри, искры, угли, вихрь.
VIDEO_KINDS = ("steam", "bubbles", "sparks", "embers", "orbit")
EMITS["STR_ONSEN"] = [("steam", .12, .20, .67, .85, .95, .95, 1.0)]
EMITS["STR_SUMMONING_CIRCLE"] = [("orbit", .16, .16, .84, .84, 1.0, .35, .50)]
for _t, _l in MORE.items():
    EMITS.setdefault(_t, []).extend(e for e in _l if e[0] in VIDEO_KINDS)
# Тикет XP-000235 (22.10): молнии между трансформаторами электростанции и между угловыми разрядниками
# хеллериевой - от точки u0 v0 до u1 v1. Воде онсэна и спа кругов ряби не даём: Vitali 22.10 - «не рябь, а еле
# видные волны», они уже есть (WATER ниже, смещение в HdBaseScene::drawMotion)
ARC = (.65, .82, 1.0)
EMITS.setdefault("STR_POWER_PLANT", []).append(_e("arc", (.185, .165, .72, .165), ARC))
EMITS["STR_HELLERIUM_PLANT"].append(_e("arc", (.098, .093, .86, .093), (.75, 1.0, .55)))

# Вода: оттенок на картинке и цвет бликов (HdBaseScene::bake ищет её по оттенку внутри стен; лист motion_sheet.png)
WATER = {t: ("blue", (.75, 1.0, 1.0)) for t in (
    "STR_ONSEN", "STR_LUXURY_SPA", "STR_HOTEL", "STR_LIVING_QUARTERS_ADVANCED_LARGE",
    "STR_LIVING_QUARTERS_ADVANCED_LARGE_DAMAGED")}      # алениевая - без воды (тикет XP-000336)
# хеллерий - без волн, хватает пузырей (тикет XP-000235)
WATER.update({t: ("green", (.8, 1.0, .4)) for t in ("STR_WELL", "STR_SLUDGE_VATS")})
# пруд метасада (раздел 11, 23.10): 144 пикселя пака - меньше 200, с которых движок берёт воду; свой порог
WATER["STR_METAGARDEN"] = ("blue", (.75, 1.0, 1.0))
WATER_LEAST = {"STR_METAGARDEN": 100}
# Вращение: центр u v и радиус в долях ширины постройки; ("spin", оборотов в с) или ("swing", градусов, период с).
# Только где тарелка или турель целиком в круге (motion_sheet.png): иначе круг режет ствол.
# Поворачивается круг картинки целиком (HdBaseScene::drawMotion), поэтому только там, где в круге одна тарелка
# или турель на ровном полу. Лазерная, гаусс и плазменная убраны (22.10, модель swing_sim и проба в игре): стволы
# и лапы у них доходят до внутренних углов креста - малый круг оставляет концы стволов на месте, большой крутит
# стены. Им нужен отдельный слой турели. Малый локатор - только тарелка с мачтой, без кабелей и ящиков вокруг
SPIN = {
    # тикет XP-000236: только тарелка качается на креплении к мачте (слой base_spin_layer.py: ось 70 51, деталь
    # до 12.8 px), мачта и пол стоят
    "STR_SMALL_RADAR_SYSTEM": (70 / 128, 51 / 128, 14 / 128, "swing", 32, 6.0),
    "STR_LARGE_RADAR_SYSTEM": (.5, .5, .34, "spin", .12),
    "STR_SAM_DEFENSES": (.5, .5, .2, "swing", 30, 9.0),
    # 22.10 (Vitali: «остальные 2 принимаю»): ствол лазерной и рельсовой качается отдельным слоем
    # (base_turret_split.py: ось - центр шара, размах и середина - до стен креста с запасом 2°, angles.json);
    # 7-е число - середина качания, градусы по часовой
    "STR_LASER_DEFENSES": (64.5 / 128, 65.5 / 128, 43.4 / 128, "swing", 19.5, 8.0, -3.5),
    "STR_GAUSS_DEFENSES": (64.0 / 128, 66.25 / 128, 45.7 / 128, "swing", 9.75, 8.0, -9.75),
}
# Плазменная не качается: шар - дуло, заряд стягивается в его центр и бьёт синий пучок вверх до края клетки
# (Vitali 22.10 «пучок синего света», проба plasma_beam_preview.py - «супер»; тикет 238 закрыт этим); emit beam - шар в (u1, v1)
EMITS.setdefault("STR_PLASMA_DEFENSES", []).append(("beam", .5, 0.0, .5, 250 / 512, .35, .65, 1.0))
# Живая база по тикетам 237-245 (22.10). Движения постройки идут не всё время, а приступами (HdBaseScene::tick):
# CYCLE - период, с, и сколько длится приступ, с; одновременно движутся не больше трёх построек базы, период у
# каждой своей постройки свой, 30-60 с (тикет 244). Пиксели - пака 128 одноклеточной постройки.
CYCLE = {
    "STR_GRAV_SHIELD": (45, 10),             # 237: точки на перекрестиях фиолет -> тёмный -> фиолет, дважды
    "STR_FUSION_BALL_DEFENSES": (45, 8),     # 237: шары гаснут до тёмно-оранжевого по четыре, волной по лучам
    "STR_LASER_DEFENSES": (45, 16),          # 244: два качания ствола (период 8 с) раз в 45 с
    "STR_GAUSS_DEFENSES": (45, 16),
    "STR_EYE_OF_HORUS": (30, 5),             # 239: веко три раза за 5 с
    "STR_HYPER_WAVE_DECODER": (60, 10),      # 240: блик на шаре; с 23.10 сгустки по кабелям (flow fit), не разгорание
    "STR_ACCESS_LIFT": (50, 4),              # 241: квадрат проседает дважды по 2 с
    "STR_SAM_DEFENSES": (58, 18),            # 245: два качания (период 9 с) и 40 с покоя
}
# Пульсация цвета: рамка x y w h, оттенок и допуск в градусах, насыщенность от, множитель яркости в пике (<1 гаснет,
# >1 разгорается), пульсов за приступ, групп по углу вокруг центра рамки (волна по кругу)
GLOW = {
    # точки на перекрестиях - каждая своей рамкой (glow_blobs): в общей рамке гасла и лавандовая кайма постройки
    "STR_GRAV_SHIELD": [(12, 12, 104, 104, 285, 35, .08, .25, 2, 1, "blobs", 22.7, 21.5, 24.0)],
    "STR_FUSION_BALL_DEFENSES": [(13, 13, 88, 88, 18, 14, .60, .55, 1, 4)],
}
# декодер 23.10 (Vitali, «трубы - все»): вместо разгорания кабелей - сгустки по ним от бака, вид flow (FLOW ниже)
# Веко: центр, полуоси, морганий за приступ (белок и зрачок внутри оранжевой каймы, сетка 22.10); цвет века -
# металл купола над глазом (движок берёт его с картинки над эллипсом)
LID = {"STR_EYE_OF_HORUS": [(63.0, 63.5, 14.5, 8.0, 3)]}
# Лифт: красная площадка (x y w h) проседает и темнеет, внутренний квадрат поднимается и краснеет; пульсов за приступ
# (рамки по сетке 22.10: площадка 46-81 x 44-80, люк 55-73 x 54-72)
SINK = {"STR_ACCESS_LIFT": [(46, 44, 35, 36, 55, 54, 18, 18, 2)]}
# Блик, который горит только в приступ: x y, радиус, цвет, пульсов - зелёный на шаре декодера со стороны кабелей
BURST = {"STR_HYPER_WAVE_DECODER": [(67.7, 67.4, 9.0, (.55, 1.0, .45), 2)]}
# радиус света одной стрелки площадки ангара, в клетках постройки (тикет XP-000350)
SWELL_REACH = .24
# Огни ролика, которых детектор на рисунке не видит (base_scene_preview.py LIGHTS по SPECIAL): u v в долях постройки,
# вид, цвет, радиус в клетках, период, число огней в кольце (chase). Кольцо ангара - вокруг посадочного круга.
VIDEO_LIGHTS = {
    # тикет XP-000350 (Vitali 28.10, вариант B): кольцо из 12 бегущих огней убрано; вместо него четыре стрелки
    # посадочной площадки (центры по art/base_living/pilot/painted/STR_HANGAR@512.png: верх, право, низ, лево) плавно
    # разгораются до жёлтого за 5 с и гаснут за 2 с (вид swell, период 7 с); у разных ангаров фаза своя - движок
    # сдвигает её по клетке постройки. Занятый кораблём ангар стрелок не зажигает (BaseView). Жёлтые огни по углам - как были
    "STR_HANGAR": [(u, v, "swell", (1, .85, .15), SWELL_REACH, 7.0, 0, 0)
                   for u, v in ((.5, .369), (.617, .488), (.5, .610), (.381, .488))]
                  + [(.15, .15, "steady", (1, .8, .55), .9, 0, 0, 0), (.15, .85, "steady", (1, .8, .55), .9, 0, 0, 0)],
    "STR_HELLERIUM_PLANT": [(.45, .5, "pulse", (.6, 1, .25), 1.0, 2.7, 0, 0)],
    "STR_SUMMONING_CIRCLE": [(.5, .5, "pulse", (1, .15, .35), 1.1, 3.2, 0, 0)]
                            + [(.5 + .33 * math.cos(a * math.pi / 4), .5 + .33 * math.sin(a * math.pi / 4), "flicker",
                                (1, .55, .2), .25, 0, 0, 0) for a in range(8)],
    "STR_ONSEN": [(.75, .6, "pulse", (.3, .8, 1), .6, 6.0, 0, 0)],
    "STR_WORKSHOP": [(.5, .52, "weld", (.7, .85, 1), .7, 0, 0, 0)],
    "STR_CORRIDOR": [(.5, .5, "night", (1, .7, .4), .7, 0, 0, 0)],
    "STR_LIVING_QUARTERS": [(.8, .22, "tv", (.5, .65, 1), .45, 0, 0, 0), (.5, .55, "night", (1, .6, .35), .5, 0, 0, 0)],
    "STR_MED_BAY": [(.5, .38, "pulse", (1, .35, .35), .55, 1.1, 0, 0)],
    "STR_BURROW": [(.5, .5, "flicker", (1, .55, .2), .7, 0, 0, 0)],
    "STR_SMALL_RADAR_SYSTEM": [(.5, .5, "pulse", (.4, 1, .55), .6, 4.0, 0, 0)],
}
# Огни, которых детектор не видит: сердце реактора, руна круга (u v, радиус в долях, вид, цвет, период)
LIGHTS = {
    "STR_FUSION_REACTOR": [(.48, .50, .45, "pulse", 1.0, .55, .15, 2.6)],
    "STR_LOVE_CLINIC": [(.50, .35, .30, "pulse", 1.0, .45, .65, 1.4)],
    "STR_EYE_OF_HORUS": [(.50, .50, .30, "pulse", 1.0, .55, .20, 2.2)],
    "STR_NONPROFIT_LAB": [(.50, .50, .25, "pulse", .45, 1.0, .45, 1.8)],
    "STR_RED_TOWER": [(.50, .50, .30, "pulse", 1.0, .25, .20, 2.4)],
    "STR_PLASMA_DEFENSES": [(.50, .50, .22, "pulse", .75, .45, 1.0, 1.5)],
}


# Тикет XP-000336 (27.10, Vitali «искры убери, добавь всякого, вместо - конвейеры в мастерских»): вместо искр у каждой
# постройки своё движение. Новые виды emit (в движке ещё нет, образец - base_scene_xp336.py):
#   belt / beltrev  x y w h цвет   лента: по длинной стороне коробки едут детали цвета (вперёд - вправо или вниз,
#                                  beltrev - назад), по ленте скользят блики роликов; едут, пока работает постройка
#   roll            x y w h цвет   валик: полосы блика бегут поперёк короткой стороны (поверхность цилиндра)
#   shuttle         x y w h цвет   каретка печатной головы ходит вдоль длинной стороны туда-обратно, сопло светится
#   heat            x y w h цвет   раскалённый металл дышит: мягкое пятно света ~3,6 с на вдох-выдох, фаза у каждого своя
# и новый вид огня light marquee (как chase, но горит и днём: gain .75 + .25 ночью), им казино
# Ленты рисунка (доли постройки, по картинке painted@512): мастерская - нижняя; фабрика - четыре (две вертикальные
# едут вниз и вливаются в горизонтальные, те едут влево); принтер - четыре балки с головами; Монетный двор -
# лента слитков внизу и валик пресса; Кузня - пульс раскалённой плиты поверх углей; электростанция - дыхание котлов.
PART, PART2, GOLD = (.90, .62, .30), (.66, .58, .80), (1.0, .82, .35)
EMITS["STR_WORKSHOP"] = [("belt", .205, .787, .87, .86) + PART]
EMITS["STR_FACTORY"] = [("belt", .505, .035, .575, .475) + PART2, ("beltrev", .105, .478, .525, .552) + PART2,
                        ("belt", .835, .045, .905, .800) + PART2, ("beltrev", .110, .810, .865, .885) + PART2]
EMITS["STR_INDUSTRIAL_PRINTER"] = [("shuttle", .17, .300, .385, .375, .60, .85, 1.0),
                                   ("shuttle", .575, .300, .790, .375, .60, .85, 1.0),
                                   ("shuttle", .150, .710, .370, .785, .60, .85, 1.0),
                                   ("shuttle", .545, .725, .770, .795, .60, .85, 1.0)]
EMITS["STR_MINT"] = [("belt", .156, .650, .86, .722) + GOLD, ("roll", .40, .30, .615, .49, 1.0, .93, .78)]
VIDEO_LIGHTS["STR_WORKSHOP"] = []          # вспышки сварки без искр - просто мигание; убраны вместе с ними
EMITS["STR_RED_FORGE"].append(("heat", .17, .17, .50, .52, 1.0, .55, .20))
EMITS["STR_POWER_PLANT"] += [("heat", .08, .10, .31, .34, 1.0, .65, .25), ("heat", .58, .10, .81, .34, 1.0, .65, .25)]
VIDEO_LIGHTS["STR_POWER_PLANT"] = [(.22, .72, "screen", (.45, .80, 1.0), .35, 0, 0, 0)]
# Казино: автоматы - огни бегут сверху вниз по шести экранам; кольцо огней по рамке вывески; рулетка - диск
# крутится, по ободу бежит шарик (кольцо из 8 огней); красные лампы справа уже мигают (base_lights)
_SLOTS = ((.247, (1, .35, .30)), (.313, (1, .80, .30)), (.384, (.40, 1, .50)),
          (.629, (1, .35, .30)), (.697, (1, .80, .30)), (.768, (.40, 1, .50)))
_MARQUEE = []
for _i in range(28):
    _s = _i / 28.0 * 4                                  # по периметру прямоугольника по часовой, от левого верха
    _L, _R, _T, _B = .10, .88, .10, .875
    _side, _f = int(_s) % 4, _s - int(_s)
    _u, _v = ((_L + (_R - _L) * _f, _T), (_R, _T + (_B - _T) * _f),
              (_R - (_R - _L) * _f, _B), (_L, _B - (_B - _T) * _f))[_side]
    _MARQUEE.append((_u, _v, "marquee", (1.0, .85, .40), .09, 5.0, _i / 28.0, 28))
VIDEO_LIGHTS["STR_CASINO"] = ([(.186, _v, "marquee", _c, .22, 3.0, _k / 6.0, 6) for _k, (_v, _c) in enumerate(_SLOTS)]
                              + _MARQUEE
                              + [(.504 + .066 * math.cos(a * math.pi / 4), .495 + .066 * math.sin(a * math.pi / 4),
                                  "marquee", (1.0, 1.0, .90), .07, 1.6, a / 8.0, 8) for a in range(8)])
SPIN["STR_CASINO"] = (.504, .495, .055, "spin", .25)       # диск рулетки (серый круг с клевером), без ободка
# Придумано сверх выбора Vitali («прикольные вещи» тикета, 27.10) - ставится с --extra у base_live_install.py:
#   cart   x y w h цвет   тележка с грузом едет вдоль длинной стороны, разгружается, возвращается пустой, ждёт
#   ticker x y w h цвет   бегущая строка: чёрточки на экране ползут вдоль длинной стороны и гаснут у краёв
# Склад - тележка по левому проходу (между стеной и перегородкой); тактический центр - бегущая строка на картах стола
EXTRA_TYPES = ["STR_GENERAL_STORES", "STR_TACTICAL_CENTER"]
EMITS.setdefault("STR_GENERAL_STORES", []).append(("cart", .078, .31, .188, .59, .50, .56, .66))
EMITS.setdefault("STR_TACTICAL_CENTER", []).append(("ticker", .61, .28, .73, .65, 1.0, .85, .40))
# Алениевая: воды нет; раз в 45 с мягкое голубое свечение из центра, один вдох-выдох за 5 с (вариант A тикета)
CYCLE["STR_ALENIUM_CHAMBER"] = (45, 5)
BURST["STR_ALENIUM_CHAMBER"] = [(64.0, 64.0, 72.0, (.45, .80, 1.0), 1)]


# во сколько раз реже мигают лампы вида blink у постройки (период в сценах .scene.txt растёт во столько же раз)
BLINK_SLOWER = {"STR_LIVING_QUARTERS_LARGE": 3}

WALK = 8          # клеток сетки экипажа на клетку базы (HdBaseLife::SUB)
FLOOR_TOL = 64    # насколько цвет может отойти от цвета пола (RGB 0..255), чтобы считаться полом
FLOOR_SHARE = 0.70
EDGE = 18         # перепад яркости соседних пикселей, с которого это край предмета


def floor_colour(img):
    """Цвет пола постройки: самая частая грубая корзина цвета внутри стен (кант и торец срезаны), медиана
    корзины. img - картинка 512 на клетку, RGBA."""
    a = img[..., 3] > 128
    h, w = a.shape
    m = 72
    inner = np.zeros_like(a)
    inner[m:h - m, m:w - m] = True
    px = img[..., :3][inner & a].astype(np.int32)
    if not len(px):
        return None
    key = (px[:, 0] // 48) * 36 + (px[:, 1] // 48) * 6 + px[:, 2] // 48
    top = np.bincount(key).argmax()
    return np.median(px[key == top], axis=0)


def walk_mask(img, cols, rows):
    """Где экипаж может стоять: {(cx, cy): строка WALK*WALK из 0/1 по строкам}. Квадрат - пол, если почти весь
    он цвета пола (Vitali 22.10: «людишки... только там где есть на них место»). Края постройки - стена:
    проходы между комнатами движок открывает сам посередине общей стороны (HdBaseLife::doorway)."""
    floor = floor_colour(img)
    out = {}
    cell = img.shape[1] // cols
    q = cell // WALK
    near = None
    if floor is not None:
        near = (np.abs(img[..., :3].astype(np.int32) - floor).max(-1) <= FLOOR_TOL) & (img[..., 3] > 128)
        # у мебели и машин резкие края (светлый стол на светлом полу цветом проходит, краями - нет)
        lum = img[..., :3].astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
        edge = np.zeros(lum.shape, bool)
        edge[:, :-1] |= np.abs(np.diff(lum, axis=1)) > EDGE
        edge[:-1, :] |= np.abs(np.diff(lum, axis=0)) > EDGE
        near &= ~edge
    for cy in range(rows):
        for cx in range(cols):
            bits = []
            for sy in range(WALK):
                for sx in range(WALK):
                    gx, gy = cx * WALK + sx, cy * WALK + sy
                    edge = gx == 0 or gy == 0 or gx == cols * WALK - 1 or gy == rows * WALK - 1
                    ok = False
                    if near is not None and not edge:
                        # с полями в четверть квадрата: фигурка шире квадрата и не должна задевать мебель
                        y0, x0 = cy * cell + sy * q - q // 4, cx * cell + sx * q - q // 4
                        win = near[max(0, y0):y0 + q + q // 2, max(0, x0):x0 + q + q // 2]
                        ok = win.size > 0 and win.mean() >= FLOOR_SHARE
                    bits.append("1" if ok else "0")
            out[(cx, cy)] = "".join(bits)
    return out


# Места экипажа (тикет XP-000336, 27.10): строка сцены `post <вид> x y куда номер` (HdBaseScene::Post). Берутся из маски
# пола: инженеры - у лент мастерских (belt, beltrev из EMITS), в казино у каждого стола дилер и до трёх мест игроков.
# Стол казино - островок не-пола в маске вокруг клетки-зерна (квадраты сетки постройки, WALK на клетку).
# Мастерская (XP-000336): по цвету пола в ней нет ни одного квадрата, инженерам некуда встать. Рукой - свободные
# квадраты сетки 8x8 (art/_review/xp336/ingame/workshop_grid.png): средина комнаты и клочок у ленты
WALK_FLOOR = {"STR_WORKSHOP": [(3, 2), (3, 3), (3, 4), (4, 4), (4, 5), (5, 3), (5, 4)]}
CASINO_TABLES = {"STR_CASINO": [(5, 5), (9, 5), (5, 9), (9, 9)]}
CASINO_ROOM = (4, 3, 12, 12)        # внутренность казино в квадратах (x0, y0, x1, y1): островки ищутся только в ней
SQ = TILE / WALK


def facility_walk(walk, cols, rows):
    """Маска пола всей постройки g[y][x] из масок клеток."""
    g = [[0] * (cols * WALK) for _ in range(rows * WALK)]
    for (cx, cy), bits in walk.items():
        for i, ch in enumerate(bits):
            g[cy * WALK + i // WALK][cx * WALK + i % WALK] = int(ch)
    return g


def _face_to(sx, sy, tx, ty):
    """Куда смотреть из точки s на точку t: 0 вправо, 1 вниз, 2 влево, 3 вверх."""
    vx, vy = tx - sx, ty - sy
    if abs(vx) >= abs(vy):
        return 0 if vx > 0 else 2
    return 1 if vy > 0 else 3


def belt_posts(t, g, cols, rows):
    """Где инженеру стоять у лент постройки: по два места у каждой ленты, на полу рядом с её длинной стороной."""
    W, H = cols * TILE, rows * TILE
    out, used = [], set()
    for e in EMITS.get(t, []):
        kind, u0, v0, u1, v1 = e[:5]
        if kind not in ("belt", "beltrev"):
            continue
        x0, x1, y0, y1 = u0 * W, u1 * W, v0 * H, v1 * H
        horiz = (x1 - x0) >= (y1 - y0)
        for f in (.28, .72):
            px, py = ((x0 + (x1 - x0) * f, (y0 + y1) / 2) if horiz else ((x0 + x1) / 2, y0 + (y1 - y0) * f))
            best = None
            for gy in range(len(g)):
                for gx in range(len(g[0])):
                    if not g[gy][gx] or any(abs(gx - ux) < 2 and abs(gy - uy) < 2 for ux, uy in used):
                        continue
                    cx, cy = (gx + .5) * SQ, (gy + .5) * SQ
                    if x0 <= cx <= x1 and y0 <= cy <= y1:
                        continue
                    d = math.hypot(max(x0 - cx, 0, cx - x1), max(y0 - cy, 0, cy - y1))
                    if d > 2.2 * SQ:
                        continue
                    score = d + .15 * math.hypot(cx - px, cy - py)
                    if best is None or score < best[0]:
                        best = (score, gx, gy, cx, cy)
            if best:
                _, gx, gy, cx, cy = best
                used.add((gx, gy))
                face = _face_to(cx, cy, min(max(cx, x0), x1), min(max(cy, y0), y1))
                out.append(("belt", gx, gy, face, 0))
    return out


def casino_posts(t, g):
    """У каждого стола казино: дилер на стороне прохода (к середине постройки) и до трёх мест игроков вокруг."""
    out = []
    x0, y0, x1, y1 = CASINO_ROOM
    for n, seed in enumerate(CASINO_TABLES.get(t, [])):
        island, todo = set(), [seed]
        while todo:
            x, y = todo.pop()
            if (x, y) in island or not (x0 <= x <= x1 and y0 <= y <= y1) or g[y][x]:
                continue
            island.add((x, y))
            todo += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        if not island:
            print("   %s: стол %d - острова нет, мест нет" % (t, n))
            continue
        mx, my = sum(x for x, _ in island) / len(island), sum(y for _, y in island) / len(island)
        mid = (x0 + x1) / 2
        near = {}
        for x, y in island:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                s = (x + dx, y + dy)
                if s not in island and x0 <= s[0] <= x1 and y0 <= s[1] <= y1 and g[s[1]][s[0]]:
                    near[s] = _face_to(s[0], s[1], x, y)
        if not near:
            continue
        side = 1 if mx < mid else -1               # дилер - со стороны прохода посередине
        dealer = min(near, key=lambda s: (-(s[0] - mx) * side, abs(s[1] - my)))
        taken = [dealer]
        out.append(("dealer", dealer[0], dealer[1], near[dealer], n))
        for s in sorted(near, key=lambda s: ((s[0] - mx) * side, abs(s[1] - my))):
            if len([p for p in out if p[0] == "seat" and p[4] == n]) >= 3:
                break
            if all(max(abs(s[0] - a), abs(s[1] - b)) >= 2 for a, b in taken):
                taken.append(s)
                out.append(("seat", s[0], s[1], near[s], n))
    return out


def post_lines(t, g, cols, rows):
    """Строки post по клеткам {(cx, cy): [строки]}."""
    lines = {}
    for kind, gx, gy, face, group in belt_posts(t, g, cols, rows) + casino_posts(t, g):
        key = (gx // WALK, gy // WALK)
        lines.setdefault(key, []).append("post %s %.1f %.1f %d %d" % (kind, (gx % WALK + .5) * SQ, (gy % WALK + .5) * SQ, face, group))
    return lines


LIQUID_MIN = 0.006   # доля картинки постройки: меньше - не жидкость, а блик или лампа


def liquid_box(img, box, col):
    """Пузыри и круги - только на жидкости (Vitali 22.10: в игре кольца летали по столам и полу, в ролике -
    только в жидкости). Ищет в коробке, расширенной вдвое, насыщенные яркие пиксели оттенка цвета частиц,
    берёт самое большое пятно; его рамка, ужатая на 15%, - новая коробка. Нет пятна - None, частицы не ставятся."""
    from scipy import ndimage
    h, w = img.shape[:2]
    u0, v0, u1, v1 = box
    du, dv = (u1 - u0) / 2, (v1 - v0) / 2
    x0, x1 = int(max(0, u0 - du) * w), int(min(1, u1 + du) * w)
    y0, y1 = int(max(0, v0 - dv) * h), int(min(1, v1 + dv) * h)
    rgb = img[y0:y1, x0:x1, :3].astype(np.float32) / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1e-3)
    c = np.array(col, np.float32)
    # оттенок: направление цвета без серого, косинус с цветом частиц
    a = rgb - rgb.mean(-1, keepdims=True)
    cc = c - c.mean()
    cos = (a @ cc) / (np.linalg.norm(a, axis=-1) * np.linalg.norm(cc) + 1e-6)
    m = (sat > 0.40) & (mx > 0.40) & (cos > 0.80) & (img[y0:y1, x0:x1, 3] > 128)
    m = ndimage.binary_opening(m, iterations=2)
    lab, n = ndimage.label(m)
    if not n:
        return None
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    best = int(sizes.argmax()) + 1
    if sizes[best - 1] < LIQUID_MIN * h * w:
        return None
    ys, xs = np.nonzero(lab == best)
    bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
    sx, sy = (bx1 - bx0) * 0.15, (by1 - by0) * 0.15
    return ((x0 + bx0 + sx) / w, (y0 + by0 + sy) / h, (x0 + bx1 - sx) / w, (y0 + by1 - sy) / h)


def glow_blobs(img, cols, g):
    """Рамки пятен оттенка glow в его рамке (пиксели пака 128): круглые пятна до 16 px - точки на перекрестиях щита;
    длинная кайма постройки того же цвета в них не попадает."""
    from scipy import ndimage
    x, y, w, h, hue, tol, sat = g[:7]
    k = img.shape[1] / (cols * TILE)
    x0, y0, x1, y1 = int(x * k), int(y * k), int((x + w) * k), int((y + h) * k)
    rgb = img[y0:y1, x0:x1, :3].astype(np.float32) / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    s = (mx - mn) / np.maximum(mx, 1e-3)
    d = np.maximum(mx - mn, 1e-6)
    r, gg, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hh = np.where(mx == r, (gg - b) / d % 6, np.where(mx == gg, (b - r) / d + 2, (r - gg) / d + 4)) * 60
    dh = np.minimum(abs(hh - hue), 360 - abs(hh - hue))
    mask = (s >= sat) & (dh <= tol) & (mx > .45) & (img[y0:y1, x0:x1, 3] > 128)
    # точки - сетка перекрестий (центр первой и шаг из g[11:14], сетка 22.10 по рисунку): рамка 14 px вокруг узла,
    # если в ней есть пятно цвета (по углам октагона узлов нет); пятна по порогу то рвались, то сливались с каймой
    gx, gy, step = g[11:14]
    out = []
    for j in range(8):
        for i in range(8):
            cx, cy = gx + i * step, gy + j * step
            if not (x <= cx < x + w and y <= cy < y + h):
                continue
            # пятно - в середине узла (6 x 6), кайма октагона туда не доходит
            sx0, sy0 = int((cx - 3 - x) * k), int((cy - 3 - y) * k)
            cell = mask[max(0, sy0):max(0, sy0 + int(6 * k)), max(0, sx0):max(0, sx0 + int(6 * k))]
            if cell.mean() >= .40:             # у точек 0.45-0.71, у пультов и каймы в углах 0.25-0.32 (22.10)
                out.append((cx - 7, cy - 7, 14, 14))
    print("   glow_blobs: %d точек" % len(out))
    return out


def extra_lines(t, cols, rows, img=None):
    """Ручные строки сцены (emit и light) по клеткам {(cx, cy): [строки]}: строка идёт в клетку, где лежит
    центр коробки или огня; координаты от угла этой клетки, за край клетки выходить могут. С картинкой img
    пузыри и круги садятся на жидкость (liquid_box) или пропадают."""
    W, H = cols * TILE, rows * TILE
    out = {}

    def tile(x, y):
        cx, cy = min(cols - 1, int(x // TILE)), min(rows - 1, int(y // TILE))
        return (cx, cy), x - cx * TILE, y - cy * TILE

    for kind, u0, v0, u1, v1, r, g, b in EMITS.get(t, []):
        if kind in ("bubbles", "ripple") and img is not None:
            box = liquid_box(img, (u0, v0, u1, v1), (r, g, b))
            if box is None:
                print("   %s: %s - жидкости нет, не ставлю" % (t, kind))
                continue
            u0, v0, u1, v1 = box
        key, x, y = tile((u0 + u1) / 2 * W, (v0 + v1) / 2 * H)
        w, h = (u1 - u0) * W, (v1 - v0) * H
        out.setdefault(key, []).append("emit %s %.1f %.1f %.1f %.1f %.2f %.2f %.2f" %
                                       (kind, x - w / 2, y - h / 2, w, h, r, g, b))
    for u, v, rad, kind, r, g, b, period in LIGHTS.get(t, []):
        key, x, y = tile(u * W, v * H)
        out.setdefault(key, []).append("light %.1f %.1f %.1f %s %.2f %.2f %.2f %.2f %.2f" %
                                       (x, y, rad * min(W, H), kind, r, g, b, period, 0.0))
    for u, v, kind, (r, g, b), cells, period, phase, count in VIDEO_LIGHTS.get(t, []):
        key, x, y = tile(u * W, v * H)
        out.setdefault(key, []).append("light %.1f %.1f %.1f %s %.2f %.2f %.2f %.2f %.3f%s" %
                                       (x, y, cells * TILE, kind, r, g, b, period, phase,
                                        " %d" % count if count else ""))
    if t in WATER:
        hue, (r, g, b) = WATER[t]
        out.setdefault((0, 0), []).append("water %s %.2f %.2f %.2f" % (hue, r, g, b)
                                          + (" %d" % WATER_LEAST[t] if t in WATER_LEAST else ""))
    if t in SPIN:
        u, v, rad, how = SPIN[t][:4]
        key, x, y = tile(u * W, v * H)
        if how == "spin":
            out.setdefault(key, []).append("spin %.1f %.1f %.1f %.3f" % (x, y, rad * W, SPIN[t][4]))
        else:
            line = "swing %.1f %.1f %.1f %.1f %.2f" % (x, y, rad * W, SPIN[t][4], SPIN[t][5])
            if len(SPIN[t]) > 6:
                line += " %.2f" % SPIN[t][6]
            out.setdefault(key, []).append(line)
    # приступы и их движения (тикеты 237-245) - одноклеточные постройки, клетка 0 0
    if t in CYCLE:
        out.setdefault((0, 0), []).append("cycle %.1f %.1f" % CYCLE[t])
    for g in GLOW.get(t, []):
        x, y, w, h, hue, tol, sat, peak, pulses, groups = g[:10]
        boxes = glow_blobs(img, cols, g) if len(g) > 10 and g[10] == "blobs" and img is not None else [(x, y, w, h)]
        for bx, by, bw, bh in boxes:
            out.setdefault((0, 0), []).append("glow %.1f %.1f %.1f %.1f %.1f %.1f %.2f %.2f %d %d"
                                              % (bx, by, bw, bh, hue, tol, sat, peak, pulses, groups))
    for x, y, rx, ry, blinks in LID.get(t, []):
        out.setdefault((0, 0), []).append("lid %.1f %.1f %.1f %.1f %d" % (x, y, rx, ry, blinks))
    for sink in SINK.get(t, []):
        out.setdefault((0, 0), []).append("sink %.1f %.1f %.1f %.1f %.1f %.1f %.1f %.1f %d" % sink)
    for x, y, rad, (r, g, b), pulses in BURST.get(t, []):
        out.setdefault((0, 0), []).append("light %.1f %.1f %.1f burst %.2f %.2f %.2f %.2f %.2f" % (x, y, rad, r, g, b, pulses, 0.0))
    return out


def build(t, rule, sprites, out, cover=0.0, most=0, art=ART):
    fac = Facility(rule, sprites)
    pic = os.path.join(art, t + ".png")
    master = os.path.join(art, t + "@512.png")
    if fac.missing or not os.path.exists(pic) or not os.path.exists(master):
        print("!! %s: нет картинки или кадров" % t)
        return []
    im = np.asarray(Image.open(pic).convert("RGBA"))
    if im.shape[:2] != (fac.rows * TILE, fac.cols * TILE):
        print("!! %s: размер %s, ждали %dx%d" % (t, im.shape[:2], fac.cols * TILE, fac.rows * TILE))
        return []
    big = np.asarray(Image.open(master).convert("RGBA"))
    found = base_lights.lights(big, fac.cols, fac.rows)
    piece = os.path.join(art, t + ".spin.png")
    if t in SPIN and os.path.exists(piece):
        # огонь на качающейся детали (полосы ствола) стоял бы на месте, а деталь уходит - снять; у оси - оставить
        pa = np.asarray(Image.open(piece).convert("RGBA"))[..., 3]
        H, W = pa.shape
        px, py = SPIN[t][0] * W, SPIN[t][1] * H
        found = [f for f in found if not (pa[min(H - 1, int(f[1] * H)), min(W - 1, int(f[0] * W))] > 128
                                          and math.hypot(f[0] * W - px, f[1] * H - py) > 6)]
    walk = walk_mask(big, fac.cols, fac.rows)
    for gx, gy in WALK_FLOOR.get(t, ()):
        # рукой: пол, который по цвету не найден (мастерская - серый пол в пятнах, края везде); квадрат сетки постройки
        row = list(walk[(gx // WALK, gy // WALK)])
        row[(gy % WALK) * WALK + gx % WALK] = "1"
        walk[(gx // WALK, gy // WALK)] = "".join(row)
    gate = gate_of(rule)
    per_tile = {}
    for u, v, kind, col, rad, _area in found:
        x, y = u * fac.cols * TILE, v * fac.rows * TILE
        cx, cy = min(fac.cols - 1, int(x // TILE)), min(fac.rows - 1, int(y // TILE))
        # жильё и нора - лампы ровные и гаснут ночью; огонь в норе, онсэне и круге - пламя
        if kind == "steady" and t in ("STR_BURROW", "STR_ONSEN", "STR_SUMMONING_CIRCLE"):
            kind = "flicker"
        period = phase = 0.0
        if kind in ("blink", "pulse"):
            period, phase = 1.4 + (u * 7 + v * 3) % 1.2, (u * 13 + v * 5) % 1
            if kind == "blink":
                period *= BLINK_SLOWER.get(t, 1)   # тикет XP-000269: в большом кубрике свет в каютах моргал слишком часто
        per_tile.setdefault((cx, cy), []).append(
            "light %.1f %.1f %.1f %s %.2f %.2f %.2f %.2f %.2f" %
            (x - cx * TILE, y - cy * TILE, rad * TILE, kind, col[0], col[1], col[2], period, phase))
    dest = os.path.join(out, "hd", "BASEBITS.PCK")
    os.makedirs(dest, exist_ok=True)
    written = []
    extra = extra_lines(t, fac.cols, fac.rows, big)
    for key, ls in post_lines(t, facility_walk(walk, fac.cols, fac.rows), fac.cols, fac.rows).items():
        extra.setdefault(key, []).extend(ls)
    # трубы (раздел 11, 23.10): карты <N>.flow.png и строка flow - base_flow_bake.py
    flows = {}
    if t in base_flow_bake.FLOW:
        flows = base_flow_bake.write([t], out)
        written += ["BASEBITS.PCK/%d.flow.png" % n for n in flows]
    num = 0
    for cy in range(fac.rows):
        for cx in range(fac.cols):
            n = fac.indices[num]
            tile = im[cy * TILE:(cy + 1) * TILE, cx * TILE:(cx + 1) * TILE]
            Image.fromarray(tile, "RGBA").save(os.path.join(dest, "%d.png" % n), optimize=True)
            # слой поворота (base_spin_layer.py): деталь и картинка без неё - HdBase::layer
            for part in ("under", "spin"):
                lp = os.path.join(art, "%s.%s.png" % (t, part))
                if os.path.exists(lp):
                    la = np.asarray(Image.open(lp).convert("RGBA"))[cy * TILE:(cy + 1) * TILE, cx * TILE:(cx + 1) * TILE]
                    Image.fromarray(la, "RGBA").save(os.path.join(dest, "%d.%s.png" % (n, part)), optimize=True)
                    written.append("BASEBITS.PCK/%d.%s.png" % (n, part))
            here = per_tile.get((cx, cy), [])
            # 16 построек ролика - все огни рисунка, как в нём (lights_of); бюджет - остальным
            if most and t not in PILOT:
                here = budget(here, cover, most)
            lines = (["# base_scene_pack.py %s %d,%d" % (t, cx, cy), "size %d %d" % (TILE, TILE), "gate " + gate]
                     + here + extra.get((cx, cy), []) + ([flows[n]] if n in flows else [])
                     + ["walk %d %s" % (WALK, walk[(cx, cy)])])
            with open(os.path.join(dest, "%d.scene.txt" % n), "w", encoding="ascii", newline="\n") as f:
                f.write("\n".join(lines) + "\n")
            written += ["BASEBITS.PCK/%d.png" % n, "BASEBITS.PCK/%d.scene.txt" % n]
            num += 1
    print("%-30s %dx%d  огней %2d  gate %s  кадры %s" % (t, fac.cols, fac.rows, len(found), gate, fac.indices))
    return written


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="типы через запятую (только выбранные Vitali)")
    ap.add_argument("--out", default=os.path.join(ROOT, "art", "base_living", "pack"))
    ap.add_argument("--cover", type=float, default=0.6, help="бюджет клетки: сумма r^2 в долях клетки")
    ap.add_argument("--most", type=int, default=0, help="не больше огней на клетку (0 - без бюджета, как у 16)")
    ap.add_argument("--art", default=ART, help="папка картинок (painted_doors - с проёмами, gen_base_paint --doors)")
    ap.add_argument("--list", default="", help="файл с типами через запятую или по строке (вместо --only)")
    ns = ap.parse_args()
    if ns.list:
        with open(ns.list, encoding="utf-8-sig") as f:
            ns.only = ",".join(s.strip() for s in f.read().replace("\n", ",").split(",") if s.strip())
    rules, _ = load_rules()
    sprites = sprites_map()
    files = []
    for t in [s for s in ns.only.split(",") if s]:
        files += build(t, rules[t], sprites, ns.out, ns.cover, ns.most, ns.art)
    with open(os.path.join(ns.out, "files.txt"), "w", encoding=ENC) as f:
        f.write("\n".join(files) + "\n")
    print("файлов %d -> %s" % (len(files), ns.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
