#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Плитка целиком, по описанию: два прохода Qwen-Image-2.1 по одной клетке.

Другая постановка задачи, чем у gen_hd.py --painter qwen21. Там мы ПРОСИЛИ РЕСТАВРИРОВАТЬ
(«ничего не перерисовывай, это чертёж») - и модель честно не рисовала череп, потому что в 128
пикселях черепа нет, его можно только дорисовать. Здесь ей это прямо РАЗРЕШЕНО:

    проход 1 (красота): расшифруй грубые пиксели в чистую детальную игровую графику,
                        сохранив силуэт ромба, место и размер предмета, палитру;
    проход 2 (плоскость): убери кайму, бортик, «коврик» и свечение по краю - песок должен
                        быть сплошной ровной землёй до самых углов ромба.

Второй проход нужен потому, что после первого модель почти всегда делает из тайла отдельный
объёмный островок с бортиком - в игре это выглядит как плитка на столе.

Тексты промптов пола - Виталия, дословно (PROMPT_HD и PROMPT_FLAT ниже). Для стен ромбовые
тексты не годятся (там про «силуэт ромба», «плоскую сплошную землю», «четыре точки стыка»),
поэтому рядом лежит их стенной вариант: PROMPT_WALL_HD и PROMPT_WALL_FLAT - те же два прохода,
но геометрия заперта вертикальная, стык требуется вбок и вверх, а земля под стеной запрещена.
Какой набор взять, решает --kind (по умолчанию auto - по типу MCD из layout.json).

    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\gen_tile.py ^
        --sheets art/TERRAIN --set DESERT.PCK --frame 1 --tries 2

Кладёт в <sheets>\<набор>\tiles\:
    tile_<кадр>_t<n>_1hd.png    что вышло после первого прохода (2K, как нарисовала модель)
    tile_<кадр>_t<n>_2flat.png  после второго
    tile_<кадр>_t<n>_cut.png    вписанное в игровой след и обрезанное по альфе оригинала
    tiles_<кадр>.png            лист: оригинал | проход 1 | проход 2 | в игровом следе

В пак это пока НЕ идёт: сначала смотрим глазами.
"""
import argparse
import gc
import json
import math
import os
import sys
import time

def _utf8_console():
    """Под конвейером (| Tee-Object, > файл) Windows отдаёт stdout в cp1252, и первая же
    строка с кириллицей валит скрипт UnicodeEncodeError. Переводим вывод в utf-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_utf8_console()

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gen_hd                                       # noqa: E402  (он же ставит HF_HOME)
from PIL import Image, ImageDraw                    # noqa: E402

PROMPT_HD = (
    "Use case: sketch-to-render. "
    "Asset type: polished 4x HD terrain sprite for an X-COM-style isometric strategy game. "
    "Input image: exact structural reference for the terrain tile. Use the diamond-shaped tile and "
    "its small central feature as the edit target; the surrounding grey panel is preview UI and must "
    "not appear in the finished asset. "
    "Primary request: Create a genuinely beautiful high-detail HD restoration of this exact tile, not "
    "a nearest-neighbor pixel enlargement. Convert the coarse pixels into clean, smooth, richly "
    "detailed game artwork. The terrain should have fine natural granular texture, subtle small-scale "
    "tonal variation, and crisp professional game-asset rendering. Refine the small central feature "
    "into a clean detailed version of the same object while keeping its original identity and "
    "footprint. Maintain excellent readability when reduced to X-COM game scale. "
    "Style: polished late-1990s tactical strategy artwork remastered for modern HD; clean pre-rendered "
    "isometric 2D game asset; realistic matte materials; subtle hand-finished texture; sharp but not "
    "pixelated; no black outlines; not photorealistic. "
    "Locked geometry: preserve the exact diamond silhouette, width-to-height ratio, isometric angle, "
    "center point, central-object location, relative scale, color placement and overall composition "
    "from the reference. Do not move the tile or the central feature in any direction. Do not add or "
    "remove gameplay objects. "
    "Colors: retain the same palette. Improve shading and material detail without changing the palette "
    "identity or lighting direction. "
    "Seamless requirement: the terrain at every outer connection point must continue naturally into "
    "identical neighboring tiles on all sides. No visible rim, border, bevel, cliff, outline, drop "
    "shadow, gap, dark edge, or decorative feature along the tile boundary. Keep boundary color and "
    "brightness uniform for seamless repetition. "
    "Output: one clean isolated terrain tile only, centered, with a genuinely transparent background "
    "outside the diamond. No screenshot UI, no grey panel, no frame, no number, no text, no watermark. "
    "Avoid: large square pixels, simple nearest-neighbor enlargement, blurry upscaling, redesigned "
    "object, changed geometry, shifted center, changed palette, glossy plastic, cartoon, anime, vector "
    "art, excessive 3D depth, dramatic shadows, added stones, plants or props.")

PROMPT_FLAT = (
    "Use case: precise-object-edit. "
    "Asset type: final polished 4x HD X-COM isometric terrain tile. "
    "Primary request: Keep the beautiful detailed texture, the exact palette, the centered feature, "
    "its size, and the overall diamond geometry from the input. Make only one correction: remove the "
    "raised mound, carpet, bevel, lip, rim, thickness, glow and bright outline around the outer "
    "diamond. The ground must read as a perfectly flat continuous surface, not an isolated floating "
    "platform. Let its fine texture and brightness continue evenly all the way to every connection "
    "edge so neighboring copies meet naturally without a visible boundary. Keep the four diamond "
    "connection points precisely aligned and at the same positions. Preserve the central feature "
    "exactly where it is and keep the subtle disturbed-ground area around it. "
    "Output one clean isolated tile with genuine transparency outside the diamond. No background, "
    "frame, label, text or watermark. "
    "Do not otherwise redesign, recolor, shift, crop, rotate, resize or add anything. No cliffs, side "
    "faces, drop shadows, edge shadows, edge highlights, border or outline.")

WHAT = " What is drawn on this tile: {hint}."

NEGATIVE = ("large square pixels, nearest-neighbor enlargement, blurry upscaling, redesigned object, "
            "changed geometry, shifted center, changed palette, glossy plastic, cartoon, anime, "
            "vector art, excessive 3D depth, dramatic shadows, added stones, plants, props, rim, "
            "bevel, border, outline, drop shadow, floating platform, background, frame, text, "
            "watermark, interface")


PROMPT_WALL_HD = (
    "Use case: sketch-to-render. "
    "Asset type: polished 4x HD wall sprite for an X-COM-style isometric strategy game. "
    "Input image: exact structural reference for one wall segment. Use the wall slab as the edit "
    "target; the surrounding grey panel is preview UI and must not appear in the finished asset. "
    "Primary request: Create a genuinely beautiful high-detail HD restoration of this exact wall "
    "segment, not a nearest-neighbor pixel enlargement. Convert the coarse pixels into clean, smooth, "
    "richly detailed game artwork. Give the wall face real material texture - masonry, concrete, "
    "panelling, rust, grain, wear - with fine small-scale variation and crisp professional game-asset "
    "rendering. Refine any window, door, opening, pipe or fitting into a clean detailed version of the "
    "same element, keeping its original identity, position and size. Maintain excellent readability "
    "when reduced to X-COM game scale. "
    "Style: polished late-1990s tactical strategy artwork remastered for modern HD; clean pre-rendered "
    "isometric 2D game asset; realistic matte materials; subtle hand-finished texture; sharp but not "
    "pixelated; no black outlines; not photorealistic. "
    "Locked geometry: this is a VERTICAL wall standing on the ground, seen from a fixed isometric "
    "camera. Preserve the exact silhouette, the slope and angle of every edge, the height, the "
    "thickness, the position of the top edge and of the base line, the position and size of every "
    "opening, the color placement and the overall composition from the reference. Do not rotate the "
    "wall, do not change which side it faces, do not move it in any direction, do not lean or taper "
    "it. Do not add or remove gameplay objects. "
    "Colors: retain the same palette. Improve shading and material detail without changing the palette "
    "identity or lighting direction. "
    "Seamless requirement: this segment repeats. The wall face must continue naturally into an "
    "identical segment placed next to it along the same line and into an identical segment stacked "
    "directly above it. Keep the texture, color and brightness uniform right up to the left, right and "
    "top cut edges, with no fading, no vignette, no darkening and no highlight along them. "
    "Output: one clean isolated wall segment only, with a genuinely transparent background around it. "
    "No ground, no floor, no terrain, no cast shadow on the ground, no grey panel, no screenshot UI, "
    "no frame, no number, no text, no watermark. "
    "Avoid: large square pixels, simple nearest-neighbor enlargement, blurry upscaling, redesigned "
    "wall, changed geometry, changed proportions, shifted or resized openings, changed palette, glossy "
    "plastic, cartoon, anime, vector art, dramatic shadows, added props, added ground.")

PROMPT_WALL_FLAT = (
    "Use case: precise-object-edit. "
    "Asset type: final polished 4x HD X-COM isometric wall segment. "
    "Primary request: Keep the beautiful detailed texture, the exact palette, every opening and "
    "fitting, their sizes and positions, and the overall wall geometry from the input. Make only one "
    "correction: remove everything that turns this segment into a standalone object. Remove the bevel, "
    "lip, rounded corner, bright rim, dark border, outline, drop shadow and glow along the left, right "
    "and top cut edges, and remove any patch of ground, floor, base plinth or cast shadow at the "
    "bottom. The wall face must read as one continuous surface cut out of a longer, taller wall: its "
    "material and brightness continue evenly all the way to every cut edge, so copies placed side by "
    "side and stacked on top of each other meet without a visible seam. Keep the top edge straight and "
    "at exactly the same height, keep the base line where it is, and keep the vertical corner edges "
    "precisely aligned. "
    "Output one clean isolated wall segment with genuine transparency around it. No ground, no "
    "background, no frame, no label, no text, no watermark. "
    "Do not otherwise redesign, recolor, shift, crop, rotate, resize or add anything. No extra side "
    "faces, no edge shadows, no edge highlights, no border, no outline.")

WHAT_WALL = " What this wall segment is: {hint}."

NEGATIVE_WALL = ("large square pixels, nearest-neighbor enlargement, blurry upscaling, redesigned wall, "
                 "changed geometry, changed proportions, shifted openings, changed palette, glossy "
                 "plastic, cartoon, anime, vector art, dramatic shadows, added props, ground, floor, "
                 "terrain, grass, cast shadow, base plinth, rim, bevel, border, outline, drop shadow, "
                 "standalone object, background, frame, text, watermark, interface")

MCD_FLOOR, MCD_WEST_WALL, MCD_NORTH_WALL = 0, 1, 2


def kind_of(lay, i, forced="auto"):
    """floor / wall / object - по типу MCD из layout.json."""
    if forced != "auto":
        return forced
    types = lay.get("types") or []
    t = types[i] if i < len(types) else None
    if t in (MCD_WEST_WALL, MCD_NORTH_WALL):
        return "wall"
    if t == MCD_FLOOR:
        return "floor"
    return "object"


def prompts_for(kind):
    """Тексты под вид клетки. Объект пока идёт по стенному набору: он тоже вертикальный."""
    if kind == "floor":
        return PROMPT_HD, PROMPT_FLAT, WHAT, NEGATIVE
    return PROMPT_WALL_HD, PROMPT_WALL_FLAT, WHAT_WALL, NEGATIVE_WALL


def parse_frames(text, hints, count, skip_text=""):
    """--frame понимает: all | 0,3,7 | 2-9 | 0-5,12,40-65. Пусто - все кадры с подсказкой,
    а если подсказок нет - первый кадр. --skip вычитается из результата."""
    def expand(t):
        got = []
        for part in t.replace(" ", "").split(","):
            if not part:
                continue
            if part in ("all", "все", "*"):
                got += list(range(count)); continue
            if "-" in part[1:]:
                a, b = part.split("-", 1)
                a, b = int(a), int(b)
                got += list(range(min(a, b), max(a, b) + 1)); continue
            got.append(int(part))
        return got
    want = expand(text) if text.strip() else (sorted(hints) or [0])
    drop = set(expand(skip_text))
    out, seen = [], set()
    for i in want:
        if i in drop or i in seen:
            continue
        if not 0 <= i < count:
            raise SystemExit("кадра %d в наборе нет, всего кадров %d" % (i, count))
        seen.add(i); out.append(i)
    if not out:
        raise SystemExit("после --skip не осталось ни одного кадра")
    return out


def load_set(sheets, set_name):
    set_dir = os.path.join(sheets, set_name)
    with open(os.path.join(set_dir, "layout.json"), encoding="utf-8-sig") as f:
        lay = json.load(f)
    hints = {}
    hp = os.path.join(set_dir, "hints.json")
    if os.path.exists(hp):
        with open(hp, encoding="utf-8-sig") as f:
            hints = {int(k): v for k, v in json.load(f).items()}
    sheet = Image.open(os.path.join(set_dir, "original.png")).convert("RGBA")
    return set_dir, lay, hints, sheet


def frame_of(sheet, lay, i):
    """Кадр i из листа, в исходных пикселях, с прозрачностью."""
    fw, fh, m, cols = lay["frame_w"], lay["frame_h"], lay["margin"], lay["columns"]
    r, c = divmod(i, cols)
    x, y = m + c * (fw + 2 * m), m + r * (fh + 2 * m)
    return sheet.crop((x, y, x + fw, y + fh))


def on_panel(frame, zoom, panel=(90, 90, 96)):
    """Клетка одна, крупно, на ровной серой подложке - ровно то, что человек кидает в чат."""
    big = frame.resize((frame.width * zoom, frame.height * zoom), Image.NEAREST)
    out = Image.new("RGBA", big.size, panel + (255,))
    out.alpha_composite(big)
    return out.convert("RGB")


GROUP_HEAD = ("This image shows {n} cells of the SAME object, side by side, separated by plain grey "
              "gutters. They are {n} frames of one animation of that object. Redraw all {n} cells. "
              "Every cell must use exactly the same material, the same surface texture, the same "
              "palette and the same light direction, as if all {n} were cut out of one single "
              "rendering - if the cells differ in material the object will flicker in the game. "
              "Only what actually differs between the input cells may differ in your output. Keep the "
              "grey gutters plain and keep every cell in its own place: do not shift, swap, merge or "
              "reorder the cells, and do not let one cell bleed into another. ")


def grid_for(n):
    """Как разложить пачку. Четвёрку кладём 2x2: длинная сторона холста задаёт
    output_resolution, поэтому квадратная раскладка даёт больше пикселей на клетку,
    чем полоса, при том же времени счёта."""
    if n <= 1: return 1, 1
    if n == 2: return 2, 1
    if n == 3: return 3, 1
    if n == 4: return 2, 2
    if n <= 6: return 3, 2
    if n <= 9: return 3, 3
    cols = int(math.ceil(math.sqrt(n)))
    return cols, int(math.ceil(n / float(cols)))


def group_panel(frames, zoom, gap_cells=1, panel=(90, 90, 96)):
    """Клетки пачки на общей серой подложке. Возвращает холст и доли каждой клетки
    (x0,y0,x1,y1 от 0 до 1) - по ним потом режем выход, какого бы он ни был размера."""
    n = len(frames)
    cols, rows = grid_for(n)
    cw, ch = frames[0].width * zoom, frames[0].height * zoom
    gap = max(1, gap_cells) * zoom
    W = cols * cw + (cols + 1) * gap
    H = rows * ch + (rows + 1) * gap
    out = Image.new("RGBA", (W, H), panel + (255,))
    boxes = []
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        x = gap + c * (cw + gap)
        y = gap + r * (ch + gap)
        out.alpha_composite(f.resize((cw, ch), Image.NEAREST), (x, y))
        boxes.append((x / float(W), y / float(H), (x + cw) / float(W), (y + ch) / float(H)))
    return out.convert("RGB"), boxes


def split_panel(painted, boxes):
    """Нарезать выход обратно по тем же долям."""
    W, H = painted.size
    return [painted.crop((int(round(a * W)), int(round(b * H)),
                          int(round(c * W)), int(round(d * H)))) for a, b, c, d in boxes]


def load_groups(set_dir, count):
    """groups.json от link_frames.py. Нет файла - каждый кадр сам по себе."""
    p = os.path.join(set_dir, "groups.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8-sig") as f:
        g = json.load(f)
    out = []
    for grp in g.get("groups") or []:
        keep = [i for i in grp if 0 <= i < count]
        if keep: out.append(keep)
    return out or None

def run_pass(painter, args, prompt, image, seed, negative=NEGATIVE):
    torch = painter.torch
    W, H = gen_hd.qwen21_size(image.width, image.height, args.mp)
    src = image.convert("RGB").resize((W, H), Image.LANCZOS)
    kw = {"prompt": prompt, "num_inference_steps": args.steps,
          "generator": torch.Generator("cuda").manual_seed(seed)}
    if "image" in painter.accepts:
        kw["image"] = src
    elif "images" in painter.accepts:
        kw["images"] = [src]
    # 2.1 приводит и вход, и выход к output_resolution. Не передашь - он молча возьмёт
    # свою тысячу двадцать четыре, на которой у конвейера открытый баг с ореолом.
    if "output_resolution" in painter.accepts:
        kw["output_resolution"] = args.res
    # при true_cfg_scale = 1.0 модель идёт без наводки и негатив просто не считается,
    # а время на него тратится. Отдаём его только когда наводка включена.
    if negative and args.cfg > 1.0 and "negative_prompt" in painter.accepts:
        kw["negative_prompt"] = negative
    if "true_cfg_scale" in painter.accepts:
        kw["true_cfg_scale"] = args.cfg
    elif "guidance_scale" in painter.accepts:
        kw["guidance_scale"] = args.cfg
    if "width" in painter.accepts:
        kw["width"], kw["height"] = W, H
    out = painter.pipe(**kw).images[0]
    return out


def free_vram(painter):
    """Между вызовами память фрагментируется, и через десяток заданий очередной вызов
    падает с out of memory, хотя картинка не больше предыдущих. Чистим явно."""
    try:
        gc.collect()
        painter.torch.cuda.empty_cache()
        painter.torch.cuda.ipc_collect()
    except Exception:
        pass


def is_oom(err):
    t = ("%s" % err).lower()
    return "out of memory" in t or "cuda error" in t or "alloc" in t


def pass_or_retry(painter, args, prompt, image, seed, negative, what):
    """Проход с повтором на пониженном разрешении, если не хватило видеопамяти.
    Один упавший кадр не должен убивать трёхчасовой прогон."""
    try:
        return run_pass(painter, args, prompt, image, seed, negative)
    except Exception as err:
        if not is_oom(err):
            raise
        free_vram(painter)
        low = max(1024, int(args.res * 0.75) // 32 * 32)
        print("  не хватило видеопамяти на %s, чищу и повторяю на res %d" % (what, low), flush=True)
        keep = args.res
        try:
            args.res = low
            return run_pass(painter, args, prompt, image, seed, negative)
        finally:
            args.res = keep


def to_footprint(painted, frame, scale):
    """Вписать нарисованное в игровой след: размер кадра * scale, маска - альфа оригинала.
    Ромб режется ровно по оригиналу, так что проходимость и стык не зависят от художника."""
    cw, ch = frame.width * scale, frame.height * scale
    body = painted.convert("RGB").resize((cw, ch), Image.LANCZOS)
    alpha = frame.split()[3].resize((cw, ch), Image.NEAREST)
    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    out.paste(body, (0, 0), alpha)
    return out


def side_strip(ims):
    """Готовые клетки пачки в один ряд - чтобы на листе было видно, совпали ли они."""
    W = sum(i.width for i in ims); H = max(i.height for i in ims)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0)); x = 0
    for i in ims:
        out.alpha_composite(i, (x, 0)); x += i.width
    return out


def checker(im, step=16):
    """Прозрачность на шахматке - иначе на чёрном фоне ничего не понять."""
    bg = Image.new("RGB", im.size, (110, 110, 110))
    d = ImageDraw.Draw(bg)
    for y in range(0, im.height, step):
        for x in range(0, im.width, step):
            if (x // step + y // step) % 2 == 0:
                d.rectangle((x, y, x + step - 1, y + step - 1), fill=(140, 140, 140))
    bg.paste(im.convert("RGBA"), (0, 0), im.convert("RGBA"))
    return bg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=gen_hd.DEFAULT_MODELS_DIR)
    ap.add_argument("--sheets", default="art/TERRAIN")
    ap.add_argument("--set", dest="set_name", required=True)
    ap.add_argument("--frame", default="",
                    help="кадры: all, или 0,1,7, или 2-9, или 0-5,12,40-65. "
                         "Пусто - все кадры, у которых есть подсказка в hints.json")
    ap.add_argument("--skip", default="", help="какие кадры не трогать, тот же формат")
    ap.add_argument("--tries", type=int, default=1, help="сколько раз нарисовать каждый кадр")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=1.0,
                    help="true_cfg_scale. 2.1 сделана под 1.0 (без наводки); больше 1.0 - вдвое дольше и включает негатив")
    ap.add_argument("--res", type=int, default=2048,
                    help="output_resolution конвейера: по нему он приводит и вход, и выход. На 1024 у 2.1 открытый баг с ореолом")
    ap.add_argument("--mp", type=float, default=2.0, help="мегапикселей на проход (2.0 - родные 2K)")
    ap.add_argument("--zoom", type=int, default=24, help="во сколько раз увеличить клетку на входе")
    ap.add_argument("--scale", type=int, default=4, help="масштаб пака для готовой клетки")
    ap.add_argument("--no-flat", action="store_true", dest="no_flat",
                    help="только первый проход (без снятия бортика)")
    ap.add_argument("--no-hint", action="store_true", dest="no_hint",
                    help="не дописывать к промпту, что нарисовано в кадре")
    ap.add_argument("--resume", action="store_true",
                    help="пропускать задания, у которых все клетки уже нарисованы "
                         "(продолжить прерванный прогон)")
    ap.add_argument("--groups", action="store_true",
                    help="кадры одной анимации рисовать одним вызовом на общем холсте "
                         "(нужен groups.json от link_frames.py)")
    ap.add_argument("--kind", default="auto", choices=["auto", "floor", "wall", "object"],
                    help="какой набор текстов брать. auto - по типу MCD из layout.json")
    ap.add_argument("--tag", default="",
                    help="метка варианта в именах файлов: tile_5__<метка>_t1_1hd.png. "
                         "Нужна, чтобы прогоны с разными настройками не затирали друг друга")
    ap.add_argument("--model", default="")
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    args = ap.parse_args()

    set_dir, lay, hints, sheet = load_set(args.sheets, args.set_name)
    tag = ("_" + args.tag.strip()) if args.tag.strip() else ""
    out_dir = os.path.join(set_dir, "tiles")
    os.makedirs(out_dir, exist_ok=True)
    count = int(lay.get("count") or len(lay.get("types") or []))
    frames = parse_frames(args.frame, hints, count, args.skip)

    # задание = либо одна клетка, либо пачка связанных кадров
    jobs = []
    if args.groups:
        groups = load_groups(set_dir, count)
        if not groups:
            raise SystemExit("нет groups.json в %s - сначала прогони link_frames.py" % set_dir)
        want = set(frames)
        taken = set()
        pulled = []
        for g in groups:
            if not (set(g) & want):
                continue
            extra = [i for i in g if i not in want]
            if extra:
                pulled += extra          # кадр из пачки нельзя бросить: разъедется анимация
            jobs.append(list(g)); taken.update(g)
        for i in frames:
            if i not in taken:
                jobs.append([i])
        jobs.sort(key=lambda g: g[0])
        if pulled:
            print("добраны из пачек (их нельзя рисовать отдельно): %s"
                  % ",".join(map(str, sorted(set(pulled)))))
    else:
        jobs = [[i] for i in frames]

    if args.resume:
        def ready(job):
            return all(os.path.exists(os.path.join(out_dir, "tile_%d%s_t%d_cut.png"
                                                   % (k, tag, t + 1)))
                       for k in job for t in range(args.tries))
        had = len(jobs)
        jobs = [j for j in jobs if not ready(j)]
        if had != len(jobs):
            print("продолжаем: готовых заданий %d, осталось %d" % (had - len(jobs), len(jobs)))
        if not jobs:
            raise SystemExit("всё уже нарисовано")

    cells = sum(len(j) for j in jobs)
    passes = len(jobs) * args.tries * (1 if args.no_flat else 2)
    print("клеток %d в %d заданиях (попыток %d, всего проходов %d)"
          % (cells, len(jobs), args.tries, passes))

    ns = argparse.Namespace(models=args.models, qwen21_model=args.model, qwen21_steps=args.steps,
                            qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0,
                            qwen21_offload=args.offload, qwen21_thrifty=False,
                            qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = gen_hd.Qwen21Painter(ns, {"ground": ("", "")})

    t0 = time.time()
    total = len(jobs) * args.tries
    done = 0
    skipped = []
    for job in jobs:
        i = job[0]
        cells_in = [frame_of(sheet, lay, k) for k in job]
        if len(job) > 1:
            src, boxes = group_panel(cells_in, args.zoom)
        else:
            src, boxes = on_panel(cells_in[0], args.zoom), [(0.0, 0.0, 1.0, 1.0)]
            src = src if isinstance(src, Image.Image) else src
        hint = hints.get(i, "") or next((hints.get(k, "") for k in job if hints.get(k)), "")
        kind = kind_of(lay, i, args.kind)
        t_hd, t_flat, t_what, neg = prompts_for(kind)
        tail = "" if args.no_hint or not hint else t_what.replace("{hint}", hint)
        head = GROUP_HEAD.replace("{n}", str(len(job))) if len(job) > 1 else ""
        p1, p2 = head + t_hd + tail, head + t_flat + tail
        KIND_RU = {"floor": "пол", "wall": "стена", "object": "объект"}
        who = "кадр %d" % i if len(job) == 1 else "пачка %s" % ",".join(map(str, job))
        print("%s [%s]: %s | вход %dx%d"
              % (who, KIND_RU.get(kind, kind), hint or "без подсказки", src.width, src.height))
        panels = [checker(src.convert("RGBA"))] if len(job) > 1 else \
                 [checker(cells_in[0].resize(src.size, Image.NEAREST))]
        failed = False
        for t in range(args.tries):
            if failed:
                break
            seed = args.seed + t * 7919
            try:
                hd = pass_or_retry(painter, args, p1, src, seed, neg, who)
            except Exception as err:
                free_vram(painter)
                skipped.append(who)
                print("  ПРОПУЩЕНО (%s): %s" % (who, err), flush=True)
                failed = True
                continue
            free_vram(painter)
            gen_hd.save_png(hd, os.path.join(out_dir, "tile_%d%s_t%d_1hd.png" % (i, tag, t + 1)))
            flat = hd
            if not args.no_flat:
                try:
                    flat = pass_or_retry(painter, args, p2, hd, seed + 101, neg, who)
                except Exception as err:
                    # первый проход уже есть, второй только снимает бортик - не теряем работу
                    print("  второй проход не удался (%s): %s - беру первый" % (who, err), flush=True)
                    flat = hd
                else:
                    gen_hd.save_png(flat, os.path.join(out_dir,
                                    "tile_%d%s_t%d_2flat.png" % (i, tag, t + 1)))
                free_vram(painter)
            parts = split_panel(flat, boxes)
            cuts = []
            for k, part in zip(job, parts):
                cut = to_footprint(part, frame_of(sheet, lay, k), args.scale)
                gen_hd.save_png(cut, os.path.join(out_dir,
                                "tile_%d%s_t%d_cut.png" % (k, tag, t + 1)))
                cuts.append(cut)
            strip = cuts[0] if len(cuts) == 1 else side_strip(cuts)
            panels += [hd.convert("RGB"), flat.convert("RGB"),
                       checker(strip.resize(src.size, Image.NEAREST))]
            done += 1
            el = time.time() - t0
            print("  попытка %d/%d (зерно %d) | %s, осталось ~%s"
                  % (t + 1, args.tries, seed, gen_hd.human_time(el),
                     gen_hd.human_time(el / done * (total - done))), flush=True)
        h = 560
        small = [p.resize((max(1, round(h * p.width / p.height)), h), Image.LANCZOS) for p in panels]
        names = ["оригинал"] + sum([["проход 1 (%d)" % (t + 1), "проход 2 (%d)" % (t + 1),
                                     "в следе (%d)" % (t + 1)] for t in range(args.tries)], [])
        small = [gen_hd.label(p, n) for p, n in zip(small, names)]
        if tag:
            names[0] = "%s | шагов %d, res %d, cfg %g%s" % (
                args.tag.strip(), args.steps, args.res, args.cfg,
                ", один проход" if args.no_flat else "")
            small[0] = gen_hd.label(small[0].copy(), names[0])
        sheet_path = os.path.join(out_dir, "tiles_%s%s.png"
                                  % ("_".join(map(str, job)) if len(job) > 1 else str(i), tag))
        gen_hd.save_png(gen_hd.side_by_side(small), sheet_path)
        print("  лист: %s" % sheet_path)

    print("готово за %s" % gen_hd.human_time(time.time() - t0))
    if skipped:
        print("НЕ НАРИСОВАНО (%d): %s" % (len(skipped), "; ".join(skipped)))
        print("запусти ту же команду с --resume, она возьмёт только их")


if __name__ == "__main__":
    main()
