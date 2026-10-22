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
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

import base_lights                                  # noqa: E402
from facility_sheet import load_rules, sprites_map  # noqa: E402
from gen_base_anim import Facility                  # noqa: E402

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
    "STR_WORKSHOP": [("sparks", .38, .40, .62, .64, 1.0, .75, .35)],
    "STR_FACTORY": [("sparks", .25, .28, .55, .55, 1.0, .75, .35), ("sparks", .50, .55, .80, .85, 1.0, .75, .35)],
    "STR_INDUSTRIAL_PRINTER": [("sparks", .12, .22, .45, .50, .55, .80, 1.0),
                               ("sparks", .45, .55, .80, .85, .55, .80, 1.0)],
    "STR_RED_FORGE": [("sparks", .25, .38, .42, .55, 1.0, .65, .25), ("embers", .22, .35, .45, .58, 1.0, .45, .15)],
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
    "STR_LABORATORY": [_e("bubbles", (.28, .30, .42, .70), CYAN), _e("bubbles", (.60, .30, .74, .70), CYAN)],
    "STR_GENERAL_STORES": [_e("dust", ROOM, DUSTC)],
    "STR_SMALL_RADAR_SYSTEM": [_e("sweep", WIDE, GREEN)],
    "STR_LASER_DEFENSES": [_e("sweep", (.25, .25, .75, .75), RED)],
    "STR_MED_BAY": [_e("dust", ROOM, DUSTC)],
    "STR_PRISON": [_e("dust", ROOM, DUSTC), _e("flies", (.35, .25, .65, .75), (.08, .07, .06))],
    "STR_GYM_ROOM": [_e("dust", ROOM, DUSTC)],
    "STR_ONSEN": [_e("ripple", (.62, .40, .85, .85), WATER)],
    "STR_LARGE_RADAR_SYSTEM": [_e("sweep", WIDE, GREEN)],
    "STR_GRAV_SHIELD": [_e("ripple", WIDE, VIOLET)],
    "STR_BEAST_DEN": [_e("flies", (.25, .20, .60, .55), (.08, .07, .05))],
    "STR_LIVING_QUARTERS_LARGE": [_e("dust", ROOM, DUSTC)],
    "STR_LIVING_QUARTERS_ADVANCED_LARGE": [_e("ripple", (.42, .20, .58, .80), WATER), _e("dust", ROOM, DUSTC)],
    "STR_BUNKER_FACILITY_DAMAGED2": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_WAR_BARRACKS_DAMAGED3": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_GENERAL_STORES_XLARGE": [_e("dust", ROOM, DUSTC)],
    "STR_JAIL_DOUBLE": [_e("dust", ROOM, DUSTC)],
    "STR_ALENIUM_CHAMBER": [_e("ripple", WIDE, CYAN), _e("bubbles", MID, CYAN)],
    "STR_TACTICAL_CENTER_DAMAGED": [_e("steam", MID, SMOKE)],
    "STR_FLAK_TOWER_DAMAGED": [_e("steam", MID, SMOKE)],
    "STR_GAUSS_DEFENSES": [_e("sweep", MID, CYAN)],
    "STR_LUXURY_SPA": [_e("ripple", (.32, .32, .66, .70), WATER)],
    "STR_DRUG_DEN": [_e("steam", (.40, .35, .60, .65), (.85, .70, .95))],
    "STR_LOVE_CLINIC": [_e("dust", ROOM, (1.0, .75, .85))],
    "STR_TRAP_ROOM": [_e("embers", WIDE, (1.0, .35, .20))],
    "STR_HYDROPONICS_WEED": [_e("dust", ROOM, POLLEN), _e("flies", WIDE, (.10, .10, .06))],
    "STR_BODY_FARM_E": [_e("bubbles", (.15, .10, .75, .65), GREEN)],
    "STR_MINT": [_e("sparks", (.35, .40, .65, .60), (1.0, .85, .35))],
    "STR_PERSONAL_LABS": [_e("bubbles", (.15, .15, .35, .50), CYAN), _e("bubbles", (.60, .15, .80, .50), CYAN)],
    "STR_STUDY_ROOM": [_e("dust", ROOM, DUSTC)],
    "STR_ASTROSENSORIUM": [_e("orbit", WIDE, VIOLET)],
    "STR_BLACK_TOWER": [_e("orbit", MID, RED)],
    "STR_MISSILE_DEFENSES": [_e("steam", (.30, .30, .60, .70), (.95, .95, .95))],
    "STR_MIND_SHIELD": [_e("ripple", WIDE, VIOLET)],
    "STR_LIVING_QUARTERS_SMALL": [_e("dust", ROOM, DUSTC)],
    "STR_LIVING_QUARTERS_LARGE_DAMAGED": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_LIVING_QUARTERS_ADVANCED_LARGE_DAMAGED": [_e("ripple", (.45, .20, .60, .60), WATER), _e("steam", MID, SMOKE)],
    "STR_WAR_BARRACKS": [_e("dust", ROOM, DUSTC)],
    "STR_GENERAL_STORES_DAMAGED": [_e("steam", MID, SMOKE), _e("dust", ROOM, DUSTC)],
    "STR_GENERAL_STORES_ARMORED": [_e("dust", ROOM, DUSTC)],
    "STR_CRYO_PRISON": [_e("steam", WIDE, (.80, .95, 1.0))],
    "STR_EYE_OF_HORUS": [_e("orbit", MID, ORANGE)],
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
    "STR_NONPROFIT_LAB": [_e("ripple", MID, GREEN)],
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
    "STR_CLONING_CENTRE": [_e("bubbles", (.30, .30, .80, .80), (1.0, .60, .70))],
    "STR_GAS_CHAMBER": [_e("steam", WIDE, (.60, 1.0, .40))],
    "STR_HYDROPONICS_BOOM_HARVEST": [_e("dust", ROOM, (.95, .70, 1.0))],
    "STR_CASINO": [_e("sweep", MID, (1.0, .85, .40))],
    "STR_WELL": [_e("ripple", (.41, .36, .65, .60), GREEN)],
    "STR_POWER_PLANT": [_e("sparks", (.30, .30, .60, .60), (.55, .80, 1.0))],
    "STR_GREAT_LIBRARY": [_e("dust", ROOM, DUSTC)],
    "STR_COMPUTER_CORE": [_e("orbit", (.15, .25, .55, .75), CYAN)],
    "STR_GDX_LAB": [_e("sparks", (.10, .40, .35, .85), (1.0, .80, .30))],
    "STR_FUSION_BALL_DEFENSES": [_e("orbit", WIDE, ORANGE)],
    "STR_HYPER_WAVE_DECODER": [_e("orbit", (.25, .25, .75, .75), VIOLET)],
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
    "STR_DISRUPTOR_SHROUD": [_e("ripple", WIDE, VIOLET)],
    "STR_HYDROPONICS": [_e("dust", ROOM, POLLEN)],
    "STR_BODY_FARM": [_e("bubbles", (.15, .10, .75, .65), GREEN)],
    "STR_FUSION_REACTOR": [_e("orbit", (.38, .40, .58, .60), ORANGE)],
    "STR_SURGERY_ROOM": [_e("dust", ROOM, DUSTC)],
    "STR_WITCH_CAVE": [_e("embers", MID, GREEN), _e("steam", MID, (.55, .85, .45))],
    "STR_RED_TOWER": [_e("ripple", MID, RED), _e("sweep", WIDE, RED)],
}
for _t, _l in MORE.items():
    EMITS.setdefault(_t, []).extend(_l)
# Огни, которых детектор не видит: сердце реактора, руна круга (u v, радиус в долях, вид, цвет, период)
LIGHTS = {
    "STR_FUSION_REACTOR": [(.48, .50, .45, "pulse", 1.0, .55, .15, 2.6)],
    "STR_SUMMONING_CIRCLE": [(.52, .46, .48, "pulse", 1.0, .35, .15, 3.2), (.52, .46, .31, "flicker", 1.0, .62, .30, 0)],
    "STR_ACCESS_LIFT": [(.50, .50, .20, "blink", 1.0, .55, .20, 1.6)],
    "STR_MED_BAY": [(.50, .40, .25, "pulse", 1.0, .30, .30, 1.2)],
    "STR_LOVE_CLINIC": [(.50, .35, .30, "pulse", 1.0, .45, .65, 1.4)],
    "STR_EYE_OF_HORUS": [(.50, .50, .30, "pulse", 1.0, .55, .20, 2.2)],
    "STR_NONPROFIT_LAB": [(.50, .50, .25, "pulse", .45, 1.0, .45, 1.8)],
    "STR_RED_TOWER": [(.50, .50, .30, "pulse", 1.0, .25, .20, 2.4)],
    "STR_PLASMA_DEFENSES": [(.50, .50, .22, "pulse", .75, .45, 1.0, 1.5)],
}


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


def extra_lines(t, cols, rows):
    """Ручные строки сцены (emit и light) по клеткам {(cx, cy): [строки]}: строка идёт в клетку, где лежит
    центр коробки или огня; координаты от угла этой клетки, за край клетки выходить могут."""
    W, H = cols * TILE, rows * TILE
    out = {}

    def tile(x, y):
        cx, cy = min(cols - 1, int(x // TILE)), min(rows - 1, int(y // TILE))
        return (cx, cy), x - cx * TILE, y - cy * TILE

    for kind, u0, v0, u1, v1, r, g, b in EMITS.get(t, []):
        key, x, y = tile((u0 + u1) / 2 * W, (v0 + v1) / 2 * H)
        w, h = (u1 - u0) * W, (v1 - v0) * H
        out.setdefault(key, []).append("emit %s %.1f %.1f %.1f %.1f %.2f %.2f %.2f" %
                                       (kind, x - w / 2, y - h / 2, w, h, r, g, b))
    for u, v, rad, kind, r, g, b, period in LIGHTS.get(t, []):
        key, x, y = tile(u * W, v * H)
        out.setdefault(key, []).append("light %.1f %.1f %.1f %s %.2f %.2f %.2f %.2f %.2f" %
                                       (x, y, rad * min(W, H), kind, r, g, b, period, 0.0))
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
    walk = walk_mask(big, fac.cols, fac.rows)
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
        per_tile.setdefault((cx, cy), []).append(
            "light %.1f %.1f %.1f %s %.2f %.2f %.2f %.2f %.2f" %
            (x - cx * TILE, y - cy * TILE, rad * TILE, kind, col[0], col[1], col[2], period, phase))
    dest = os.path.join(out, "hd", "BASEBITS.PCK")
    os.makedirs(dest, exist_ok=True)
    written = []
    extra = extra_lines(t, fac.cols, fac.rows)
    num = 0
    for cy in range(fac.rows):
        for cx in range(fac.cols):
            n = fac.indices[num]
            tile = im[cy * TILE:(cy + 1) * TILE, cx * TILE:(cx + 1) * TILE]
            Image.fromarray(tile, "RGBA").save(os.path.join(dest, "%d.png" % n), optimize=True)
            here = per_tile.get((cx, cy), [])
            if most:
                here = budget(here, cover, most)
            lines = (["# base_scene_pack.py %s %d,%d" % (t, cx, cy), "size %d %d" % (TILE, TILE), "gate " + gate]
                     + here + extra.get((cx, cy), []) + ["walk %d %s" % (WALK, walk[(cx, cy)])])
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
