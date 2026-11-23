"""Ракурс и свет боевой карты для всех генераторов HD-арта: один источник чисел и фраз промпта.

Откуда числа: docs/research/battle-render.md (код Camera.cpp/Map.cpp и замер кадров UFO и Пираток).
Кто читает: агент view-keeper (.claude/agents/view-keeper.md), artist и gpu-forge перед любым рендером
графики боя, генераторы - импортом:

    import battle_view as bv
    pb = bv.prompt_block("object")       # None - вид не боевой, ракурс боя к нему не применяется
    prompt = f"{subject}. {pb['positive']}"; negative = f"{neg}, {pb['negative']}"
    bv.view_sentence("object"), bv.light_sentence("object")   # по отдельности - вставить в свои места текста
    bv.short("object")                   # то же коротко - для SDXL (CLIP режет на 77 токенах)
    bv.facing(3)                         # направление юнита словами

Слова промпта ракурс НЕ держат (R-160, R-204, R-211): геометрию задаёт вход - оригинал, эскиз, кадр правки.
Фраза здесь - добавка, чтобы модель не спорила с входом, а не замена ему.
Негатив действует только при cfg больше 1 (R-040): у turbo и edit с cfg 1 работает лишь позитив.

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
LIGHT = ("even full daylight exposure, neutral white light from above and from the left of the picture, so faces "
         "turned to the left are slightly brighter than faces turned to the right; any shadow stays under the "
         "object, no long cast shadows")
LIGHT_SELF = "the effect carries all its own light and glow; no outside light, no cast shadow"
# Негатив ракурса. Без "front view" и "side view": у юнита это направления 3, 1 и 5 (FACING), а не камера.
NEG_VIEW = ("perspective distortion, vanishing point, converging lines, fisheye, wide-angle lens, tilted camera, "
            "eye-level camera, straight top-down view")
NEG_LIGHT = "light from the right, rim light, long cast shadow, night scene, dark exposure, colored light"
NEGATIVE = NEG_VIEW + ", " + NEG_LIGHT

# Пол-развёртка: текстура рисуется строго сверху и потом аффинно ложится в ромб (probe_floor, floor_group,
# make_ref, gen_hd поле). Изометрия ей противоречит - свои фразы.
UNROLLED_VIEW = ("seamless ground texture seen straight from above, flat orthographic top-down view with no "
                 "perspective; it is mapped onto the 2:1 isometric floor diamond of the game afterwards")
UNROLLED_LIGHT = "flat even daylight, no directional light, no cast shadows"
UNROLLED_NEG = "perspective, horizon, sky, side view, isometric view, tilted camera, cast shadow, vignette"

# Коротко для SDXL: CLIP режет промпт на 77 токенах, полный блок (~80 слов) не влезает.
SHORT_VIEW = "orthographic 2:1 isometric game view, camera 30 degrees above, no perspective"
SHORT_LIGHT = "daylight from the left"
SHORT_NEG = "perspective, vanishing point, fisheye, eye-level camera, light from the right, long cast shadow"
SHORT_UNROLLED = ("seamless top-down texture seen straight from above, flat even light",
                  "perspective, horizon, sky, side view, isometric view")

# --- виды ассетов ------------------------------------------------------------------------------
# iso: True - ракурс боя обязателен; "unrolled" - боевой пол, но рисуется развёрткой сверху;
# False - не боевая изометрия, фразы отсюда не ставить. light: "day" - свет боя, "self" - светит сам, None - нет.
KINDS = {
    "floor": dict(iso=True, light="day", canvas="32x40, рисуется ромб строк 24-39",
                  anchor="ромб целиком, без выхода за край",
                  extra="a flat ground tile seen in that view, the diamond fills the tile edge to edge",
                  rules=["края ромба - ровно 2:1, стык с соседом без шва (R-005)",
                         "поле повторяется: нужен не один кадр, а варианты (R-039)"]),
    "floor_unrolled": dict(iso="unrolled", light="day", canvas="квадрат развёртки, потом аффинно в ромб 32x16",
                           anchor="вся площадь, без края", extra="",
                           rules=["рисуется строго сверху: изометрию и свет слева сюда не ставить",
                                  "периодичность развёртки - решётка на поле (R-118)"]),
    "wall": dict(iso=True, light="day", canvas="32x40: западная - левая половина, северная - правая",
                 anchor="низ стены по краю ромба, верх на 24 пикселя выше",
                 extra="one wall standing exactly on the tile edge, one storey high",
                 rules=["северная стена над западной рисуется только правой половиной - угловой столб у западной",
                        "западная стена смотрит вниз-вправо (темнее), северная вниз-влево (светлее)"]),
    "object": dict(iso=True, light="day", canvas="32x40 (BIGOBS-предметы карты - свой размер)",
                   anchor="опора в центре ромба (16, 32)",
                   extra="the object stands on the tile diamond, as tall as it is in the original sprite",
                   rules=["высота в пикселях = высота в вокселях; полный этаж - 24",
                          "тень только внутри своей клетки: соседняя клетка рисуется позже и закроет вылет"]),
    "unit": dict(iso=True, light="day", canvas="32x40 на часть юнита (большой юнит 2x2 - четыре кадра)",
                 anchor="ступни у центра ромба", extra="a figure standing on the tile, full body in frame",
                 rules=["направление задавать словами FACING по положению на картинке, не стороной тела (R-212, R-217)",
                        "поза и ракурс - с оригинала спрайта, облик - с эталона (R-211)"]),
    "floor_item": dict(iso=True, light="day", canvas="32x40 (FLOOROB)", anchor="лежит в центре ромба",
                       extra="an item lying on the ground",
                       rules=["лежит плашмя по плоскости пола, вытянутые вещи - вдоль края клетки 2:1"]),
    "hand_item": dict(iso=True, light="day", canvas="32x40 на направление (HANDOB)", anchor="в кисти юнита по оригиналу",
                      extra="an item held in the hand, seen in that view",
                      rules=["8 направлений, ствол по FACING; положение с оригинала кадра"]),
    "effect": dict(iso=True, light="self", canvas="SMOKE/HIT 32x40, X1 128x64",
                   anchor="центр ромба; снаряды - по вокселям, ~4 px выше пола",
                   extra="the effect seen in that view", rules=["огонь рисуется без затемнения клетки - светит сам"]),
    "cursor": dict(iso=True, light=None, canvas="32x40 (CURSOR.PCK)", anchor="рамка по ромбу клетки", extra="",
                   rules=["рамка повторяет ромб 2:1 точно, линии строить координатами (R-042)"]),
    "inventory": dict(iso=False, light=None, canvas="BIGOBS инвентаря", anchor="-", extra="",
                      rules=["не боевая изометрия: ракурс брать с оригинала набора"]),
    "pedia": dict(iso=False, light=None, canvas="картинка статьи", anchor="-", extra="",
                  rules=["иллюстрация, свой ракурс"]),
    "ui": dict(iso=False, light=None, canvas="экран интерфейса", anchor="-", extra="", rules=["плоский интерфейс"]),
    "base": dict(iso=False, light=None, canvas="BASEBITS 32x32", anchor="-", extra="",
                 rules=["вид базы, не боевая изометрия"]),
    "geoscape": dict(iso=False, light=None, canvas="глобус, значки посудин", anchor="-", extra="",
                     rules=["вид сверху на глобус"]),
    "portrait": dict(iso=False, light=None, canvas="кукла, портрет", anchor="-", extra="",
                     rules=["вид спереди, не боевая изометрия"]),
}
# Для хэшей ревизий генераторов (obj_gen_spec.CODE_PARTS, photo_render.CODE ...): генератор берёт текст
# отсюда вызовом, и хэш его собственного исходника правку фраз не увидит - эти имена хэшируются отдельно.
CODE_PART = ("battle_view.py", ("GEOMETRY", "LIGHT", "LIGHT_SELF", "NEG_VIEW", "NEG_LIGHT", "NEGATIVE",
                                "UNROLLED_VIEW", "UNROLLED_LIGHT", "UNROLLED_NEG", "SHORT_VIEW", "SHORT_LIGHT",
                                "SHORT_NEG", "SHORT_UNROLLED", "FACING", "KINDS", "view", "light", "negative",
                                "_sentence", "view_sentence", "light_sentence", "prompt_block", "short", "facing"))
COMMON_RULES = [
    "ракурс держит вход (оригинал, эскиз, правка оригинала), слова только помогают (R-160, R-204, R-211)",
    "рисовать при полном свете (shade 0): ночь и тень клетки движок наложит сам",
    "свет слева: замер UFO 115 против 104, Пиратки 93 против 83 (грани влево светлее грани вправо)",
    "в HD всё умножается на k: кадр 32k x 40k, этаж 24k, ромб 32k x 16k",
    "одобренный промпт серии не менять без слова Vitali (R-112): расхождение - показать, а не править",
]


def view(kind):
    """Фраза ракурса вида `kind` (строчная, без точки); None для не боевых видов."""
    k = KINDS[kind]
    if not k["iso"]:
        return None
    if k["iso"] == "unrolled":
        return UNROLLED_VIEW
    return (k["extra"] + ", " + GEOMETRY) if k["extra"] else GEOMETRY


def light(kind):
    """Фраза света вида `kind` (строчная, без точки); "" - свет не задаётся (курсор); None - не боевой вид."""
    k = KINDS[kind]
    if not k["iso"]:
        return None
    if k["iso"] == "unrolled":
        return UNROLLED_LIGHT
    return {"day": LIGHT, "self": LIGHT_SELF, None: ""}[k["light"]]


def negative(kind):
    """Негатив ракурса и света вида `kind` через запятую; None для не боевых видов."""
    k = KINDS[kind]
    if not k["iso"]:
        return None
    if k["iso"] == "unrolled":
        return UNROLLED_NEG
    return NEGATIVE if k["light"] == "day" else NEG_VIEW


def _sentence(text):
    return (text[0].upper() + text[1:] + ".") if text else ""


def view_sentence(kind):
    """Ракурс отдельным предложением: с заглавной буквы и точкой."""
    v = view(kind)
    return None if v is None else _sentence(v)


def light_sentence(kind):
    """Свет отдельным предложением; "" - свет не задаётся."""
    s = light(kind)
    return None if s is None else _sentence(s)


def prompt_block(kind):
    """Фразы ракурса и света для промпта вида `kind`: dict(positive, negative); None для не боевых видов."""
    v = view(kind)
    if v is None:
        return None
    s = light(kind)
    return {"positive": v + ("; " + s if s else ""), "negative": negative(kind)}


def short(kind):
    """Короткий блок для SDXL (лимит CLIP 77 токенов): dict(positive, negative); None для не боевых видов."""
    k = KINDS[kind]
    if not k["iso"]:
        return None
    if k["iso"] == "unrolled":
        return {"positive": SHORT_UNROLLED[0], "negative": SHORT_UNROLLED[1]}
    pos = SHORT_VIEW + (", " + SHORT_LIGHT if k["light"] == "day" else "")
    return {"positive": pos, "negative": SHORT_NEG}


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
    pb, sh = prompt_block(kind), short(kind)
    lines += ["Промпт +: " + pb["positive"], "Негатив +: " + pb["negative"],
              "SDXL коротко +: " + sh["positive"], "SDXL негатив +: " + sh["negative"]]
    return "\n".join(lines)


# --- аудит генераторов ------------------------------------------------------------------------
# Скрипты с моделью из tools/gpu_scripts.txt, к которым ракурс боя не применяется, - с причиной.
NOT_BATTLE = {
    "gen_promo.py": "промо лаунчера и сайта",
    "photo_ui.py": "педия; его Painter.edit - движок для других, промпты свои у вызывающих",
    "pedia_ab.py": "педия", "pedia_batch.py": "педия", "pedia_nudecheck.py": "педия, проверка",
    "upscale_ui.py": "интерфейс, без промпта",
    "item_photo.py": "предметы инвентаря BIGOBS", "weapons_batch.py": "оружие инвентаря",
    "weapons_sr.py": "оружие инвентаря, без промпта", "qwen_literal.py": "инвентарь, текст Vitali дословно",
    "weapons_edit.py": "оружие инвентаря", "weapons_probe3.py": "оружие инвентаря",
    "weapons_probe4.py": "оружие инвентаря", "weapons_probe5.py": "оружие инвентаря",
}
NO_PROMPT = {
    "upscale_units.py": "ESRGAN, промпта нет",
    "describe_modules.py": "текстовая модель, описания кода",
    "check_triton.py": "проверка окружения",
    "identity_propose.py": "VLM опознаёт предмет, картинку не рисует",
    "arbiter.py": "VLM-арбитр, картинку не рисует", "arbiter_v2.py": "VLM-арбитр, картинку не рисует",
}
# Боевые, но текст переводить нельзя: смена слов ломает обученное или заданное дословно.
PROTECTED = {
    "gen_lora_test.py": "CAPTION - подпись, на которой обучена LoRA; другие слова - другой триггер",
    "gen_lora_batch.py": "CAPTION из gen_lora_test - подпись обучения LoRA",
}
OWN_WORDS = re.compile(r"isometric|изометр|from the upper left|seen from above|top-down", re.I)
IMPORT_RX = re.compile(r"^\s*(?:import|from)\s+(\w+)", re.M)
HDART = ROOT / "tools" / "hdart"


def _uses(path, seen):
    """Берёт ли модуль фразы отсюда: сам импортирует battle_view или наследует промпт через свой модуль."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    mods = set(IMPORT_RX.findall(text))
    if "battle_view" in mods:
        return "direct"
    for m in sorted(mods):
        p = HDART / f"{m}.py"
        if m in seen or not p.exists():
            continue
        seen.add(m)
        if _uses(p, seen):
            return "via " + m
    return None


def audit():
    """Генераторы с моделью (tools/gpu_scripts.txt): берут ли фразы отсюда. Строки (имя, статус, пояснение)."""
    names = [l.strip() for l in (ROOT / "tools" / "gpu_scripts.txt").read_text(encoding="utf-8-sig").splitlines()
             if l.strip() and not l.startswith("#") and l.strip().endswith(".py")]
    out = []
    for n in names:
        path = next((p for p in (HDART / n, ROOT / "tools" / n) if p.exists()), None)
        if path is None:
            continue
        if n in NOT_BATTLE:
            out.append((n, "NOT_BATTLE", NOT_BATTLE[n]))
            continue
        if n in NO_PROMPT:
            out.append((n, "NO_PROMPT", NO_PROMPT[n]))
            continue
        if n in PROTECTED:
            out.append((n, "PROTECTED", PROTECTED[n]))
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        how = _uses(path, {path.stem})
        if how == "direct":
            out.append((n, "USES", "импорт battle_view"))
        elif OWN_WORDS.search(text):
            out.append((n, "MISSING", "ракурс своими словами"))     # даже если модуль-основа уже переведён
        elif how:
            out.append((n, "USES", how))
        else:
            # ни своих слов, ни переведённого модуля: проверка по тексту, не по смыслу - смотреть глазами
            out.append((n, "no-words", "ракурса в тексте нет"))
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
    s.add_argument("--strict", action="store_true", help="код 1, если есть MISSING или no-words")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "brief":
        print(brief(a.kind))
    elif a.cmd == "prompt":
        pb, sh = prompt_block(a.kind), short(a.kind)
        if pb is None:
            print("не боевой вид: фраз нет")
        else:
            print(f"positive: {pb['positive']}\nnegative: {pb['negative']}\n"
                  f"short positive: {sh['positive']}\nshort negative: {sh['negative']}")
    elif a.cmd == "facing":
        print(f"dir {a.dir % 8} ({DIR_SCREEN[a.dir % 8]} on screen): {facing(a.dir)}")
    else:
        rows = audit()
        for n, st, why in rows:
            print(f"{st:10} {n:24} {why}")
        cnt = {}
        for _, st, _ in rows:
            cnt[st] = cnt.get(st, 0) + 1
        print(", ".join(f"{k} {v}" for k, v in sorted(cnt.items())) + f" из {len(rows)}")
        if a.strict and (cnt.get("MISSING") or cnt.get("no-words")):
            sys.exit(1)


if __name__ == "__main__":
    main()
