"""Ракурс и свет боевой карты для всех генераторов HD-арта: один источник чисел и фраз промпта.

Откуда числа: docs/research/battle-render.md (код Camera.cpp/Map.cpp и замер кадров UFO и Пираток).
Кто читает: агент view-keeper (.claude/agents/view-keeper.md), artist и gpu-forge перед любым рендером
графики боя, генераторы - импортом:

    from battle_view import prompt_block
    pb = prompt_block("object")          # None - вид не боевой, ракурс боя к нему не применяется
    prompt = f"{subject}. {pb['positive']}"; negative = f"{neg}, {pb['negative']}"

Слова промпта ракурс НЕ держат (R-160, R-204, R-211): геометрию задаёт вход - оригинал, эскиз, кадр правки.
Фраза здесь - добавка, чтобы модель не спорила с входом, а не замена ему.

Запуск:
    py -3.13 tools/hdart/battle_view.py brief object     # справка для человека и агента
    py -3.13 tools/hdart/battle_view.py prompt unit      # фразы промпта и негатива
    py -3.13 tools/hdart/battle_view.py facing 3         # как назвать направление юнита словами
    py -3.13 tools/hdart/battle_view.py audit            # какие генераторы с моделью уже берут фразы отсюда
"""
import argparse
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- числа проекции (базовые пиксели; HD - всё умножить на k) ------------------------------------
FRAME_W, FRAME_H = 32, 40          # кадр клетки, Map.h BASE_SPRITE_WIDTH/HEIGHT
TILE_W, TILE_H = 32, 16            # ромб пола на экране
LEVEL_PX = 24                      # этаж: (40 + 32/4) / 2, Camera::convertMapToScreen
VOXEL_XY, VOXEL_Z = 16, 24         # вокселей в клетке, Position::TileXY / TileZ
CAMERA_AZIMUTH_DEG = 45.0          # оси карты идут по диагоналям экрана
CAMERA_ELEVATION_DEG = math.degrees(math.asin(TILE_H / TILE_W))   # 30: ромб 2:1
EDGE_SLOPE_DEG = math.degrees(math.atan(TILE_H / TILE_W))         # 26.565: края клеток на экране
# Высота этажа к стороне клетки в мире: 24 пикселя этажа против честной проекции куба под 30 градусов.
LEVEL_TO_TILE = LEVEL_PX / (VOXEL_XY * math.sqrt(2) * math.cos(math.radians(CAMERA_ELEVATION_DEG)))  # sqrt(1.5)
FLOOR_ROWS = (24, 39)              # строки ромба пола в кадре 32x40
FLOOR_CENTER = (16, 32)            # опора предмета и юнита; так же Camera::inView
WALL_TOP = {"north corner": (16, 1), "west/east corner": 8}   # верх полной стены: этаж над ромбом

# Экранный шаг по направлению юнита, Pathfinding::dir_x/dir_y -> convertMapToScreen
DIR_SCREEN = {0: "up-right", 1: "right", 2: "down-right", 3: "down", 4: "down-left", 5: "left",
              6: "up-left", 7: "up"}
FACING = {
    0: "turned away from the viewer toward the upper right, three-quarter back view",
    1: "facing right, in profile",
    2: "facing the lower right, three-quarter front view",
    3: "facing the viewer, front view",
    4: "facing the lower left, three-quarter front view",
    5: "facing left, in profile",
    6: "turned away from the viewer toward the upper left, three-quarter back view",
    7: "turned away from the viewer, back view",
}

# --- фразы промпта (английский: промпты моделей на нём) -------------------------------------------
GEOMETRY = ("classic 2:1 isometric game view, orthographic camera with no perspective: rotated 45 degrees, "
            "looking down at 30 degrees above the horizon; parallel edges stay parallel, ground edges run at "
            "26.6 degrees (two pixels across for one pixel down), vertical edges stay exactly vertical")
LIGHT = ("even full daylight exposure, neutral white light; key light from the left of the picture, so faces "
         "turned to the left are slightly brighter than faces turned to the right; any shadow stays under the "
         "object, no long cast shadows")
NEGATIVE = ("perspective, vanishing point, foreshortening, fisheye, wide-angle lens, tilted camera, "
            "top-down view, front view, side view, light from the right, rim light, long cast shadow, "
            "night scene, dark exposure, colored light")

# --- виды ассетов ------------------------------------------------------------------------------
# iso: True - ракурс боя обязателен; False - не боевая изометрия, фразы отсюда не ставить.
KINDS = {
    "floor": dict(iso=True, canvas="32x40, рисуется ромб строк 24-39", anchor="ромб целиком, без выхода за край",
                  extra="a flat ground tile seen in that view, the diamond fills the tile edge to edge",
                  rules=["края ромба - ровно 2:1, стык с соседом без шва (R-005)",
                         "поле повторяется: нужен не один кадр, а варианты (R-039)"]),
    "wall": dict(iso=True, canvas="32x40: западная - левая половина, северная - правая",
                 anchor="низ стены по краю ромба, верх на 24 пикселя выше",
                 extra="one wall standing exactly on the tile edge, one storey high",
                 rules=["северная стена над западной рисуется только правой половиной - угловой столб у западной",
                        "западная стена смотрит вниз-вправо (темнее), северная вниз-влево (светлее)"]),
    "object": dict(iso=True, canvas="32x40 (BIGOBS-предметы карты - свой размер)", anchor="опора в центре ромба (16, 32)",
                   extra="the object stands on the tile diamond, as tall as it is in the original sprite",
                   rules=["высота в пикселях = высота в вокселях; полный этаж - 24",
                          "тень только внутри своей клетки: соседняя клетка рисуется позже и закроет вылет"]),
    "unit": dict(iso=True, canvas="32x40 на часть юнита (большой юнит 2x2 - четыре кадра)", anchor="ступни у центра ромба",
                 extra="a figure standing on the tile, full body in frame",
                 rules=["направление задавать словами FACING по положению на картинке, не стороной тела (R-212, R-217)",
                        "поза и ракурс - с оригинала спрайта, облик - с эталона (R-211)"]),
    "floor_item": dict(iso=True, canvas="32x40 (FLOOROB)", anchor="лежит в центре ромба", extra="an item lying on the ground",
                       rules=["лежит плашмя по плоскости пола, вытянутые вещи - вдоль края клетки 2:1"]),
    "hand_item": dict(iso=True, canvas="32x40 на направление (HANDOB)", anchor="в кисти юнита по оригиналу",
                      extra="an item held in the hand, seen in that view",
                      rules=["8 направлений, ствол по FACING; положение с оригинала кадра"]),
    "effect": dict(iso=True, canvas="SMOKE/HIT 32x40, X1 128x64", anchor="центр ромба; снаряды - по вокселям, ~4 px выше пола",
                   extra="the effect seen in that view", rules=["огонь рисуется без затемнения клетки - светит сам"]),
    "cursor": dict(iso=True, canvas="32x40 (CURSOR.PCK)", anchor="рамка по ромбу клетки", extra="",
                   rules=["рамка повторяет ромб 2:1 точно, линии строить координатами (R-042)"]),
    "inventory": dict(iso=False, canvas="BIGOBS инвентаря", anchor="-", extra="",
                      rules=["не боевая изометрия: ракурс брать с оригинала набора"]),
    "pedia": dict(iso=False, canvas="картинка статьи", anchor="-", extra="", rules=["иллюстрация, свой ракурс"]),
    "ui": dict(iso=False, canvas="экран интерфейса", anchor="-", extra="", rules=["плоский интерфейс"]),
    "base": dict(iso=False, canvas="BASEBITS 32x32", anchor="-", extra="", rules=["вид базы, не боевая изометрия"]),
    "geoscape": dict(iso=False, canvas="глобус, значки посудин", anchor="-", extra="", rules=["вид сверху на глобус"]),
    "portrait": dict(iso=False, canvas="кукла, портрет", anchor="-", extra="", rules=["вид спереди, не боевая изометрия"]),
}
COMMON_RULES = [
    "ракурс держит вход (оригинал, эскиз, правка оригинала), слова только помогают (R-160, R-204, R-211)",
    "рисовать при полном свете (shade 0): ночь и тень клетки движок наложит сам",
    "свет слева: замер UFO 115 против 104, Пиратки 93 против 83 (грани влево светлее грани вправо)",
    "в HD всё умножается на k: кадр 32k x 40k, этаж 24k, ромб 32k x 16k",
    "одобренный промпт серии не менять без слова Vitali (R-112): расхождение - показать, а не править",
]


def prompt_block(kind):
    """Фразы ракурса и света для промпта вида `kind`: dict(positive, negative); None для не боевых видов."""
    k = KINDS[kind]
    if not k["iso"]:
        return None
    pos = GEOMETRY + "; " + LIGHT
    if k["extra"]:
        pos = k["extra"] + ", " + pos
    return {"positive": pos, "negative": NEGATIVE}


def facing(direction):
    """Направление юнита 0..7 словами для промпта (по положению на картинке)."""
    return FACING[direction % 8]


def brief(kind):
    """Справка по виду для агента и человека, по-русски."""
    k = KINDS[kind]
    lines = [f"Вид: {kind} | кадр: {k['canvas']} | опора: {k['anchor']}"]
    if not k["iso"]:
        lines.append("Ракурс боя НЕ применяется - фразы battle_view в промпт не ставить.")
        lines += ["- " + r for r in k["rules"]]
        return "\n".join(lines)
    lines += [
        f"Камера: ортографическая, азимут {CAMERA_AZIMUTH_DEG:.0f}°, вниз {CAMERA_ELEVATION_DEG:.0f}° к горизонту; "
        f"края клеток {EDGE_SLOPE_DEG:.3f}° (2:1); этаж {LEVEL_PX} px; клетка в мире 1x1x{LEVEL_TO_TILE:.4f}",
        f"Кадр {FRAME_W}x{FRAME_H}: ромб пола строки {FLOOR_ROWS[0]}-{FLOOR_ROWS[1]}, центр {FLOOR_CENTER}; "
        f"верх полной стены {WALL_TOP}",
    ]
    lines += ["- " + r for r in k["rules"] + COMMON_RULES]
    pb = prompt_block(kind)
    lines += ["Промпт +: " + pb["positive"], "Негатив +: " + pb["negative"]]
    return "\n".join(lines)


ISO_WORDS = re.compile(r"isometric|изометр", re.I)


def audit():
    """Генераторы с моделью (tools/gpu_scripts.txt): берут ли фразы отсюда. Строки (имя, статус)."""
    names = [l.strip() for l in (ROOT / "tools" / "gpu_scripts.txt").read_text(encoding="utf-8-sig").splitlines()
             if l.strip() and not l.startswith("#") and l.strip().endswith(".py")]
    out = []
    for n in names:
        path = next((p for p in (ROOT / "tools" / "hdart" / n, ROOT / "tools" / n) if p.exists()), None)
        if path is None:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if "battle_view" in text:
            out.append((n, "USES"))
        elif ISO_WORDS.search(text):
            out.append((n, "MISSING"))      # пишет изометрию своими словами
        else:
            # слов изометрии в самом файле нет: педия, звук - или промпт берётся из другого модуля.
            # Проверка по тексту, не по смыслу: такой скрипт агент смотрит глазами.
            out.append((n, "no-words"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("brief", "prompt"):
        s = sub.add_parser(c)
        s.add_argument("kind", choices=sorted(KINDS))
    s = sub.add_parser("facing")
    s.add_argument("dir", type=int)
    s = sub.add_parser("audit")
    s.add_argument("--strict", action="store_true", help="код 1, если есть MISSING")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "brief":
        print(brief(a.kind))
    elif a.cmd == "prompt":
        pb = prompt_block(a.kind)
        print("не боевой вид: фраз нет" if pb is None else f"positive: {pb['positive']}\nnegative: {pb['negative']}")
    elif a.cmd == "facing":
        print(f"dir {a.dir % 8} ({DIR_SCREEN[a.dir % 8]} on screen): {facing(a.dir)}")
    else:
        rows = audit()
        for n, st in rows:
            print(f"{st:8} {n}")
        miss = sum(1 for _, st in rows if st == "MISSING")
        print(f"берут отсюда {sum(1 for _, st in rows if st == 'USES')}, своими словами {miss}, "
              f"без слов изометрии {sum(1 for _, st in rows if st == 'no-words')} из {len(rows)}")
        if a.strict and miss:
            sys.exit(1)


if __name__ == "__main__":
    main()
