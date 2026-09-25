#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""map_paint.py - опыт: тайлы рисуются не по одному, а в составе своей карты.

Прежние конвейеры давали модели кадр 32x40 и больше ничего. Модель не знала, что стена - часть
амбара, а три такие стены стоят подряд, и соседние тайлы на карте не сходились. Здесь блок
.MAP собирается как в игре (map_mockup.py), и модель рисует СЦЕНУ, а тайлы вырезаются обратно.

Два режима:
  whole    каждый этаж блока (всё, что ниже, тоже видно) рисуется одной картинкой x4; клетки
           этажа вырезаются по карте владельцев пикселя. Кадр стоит в блоке много раз - берётся
           место, где его видно больше всего, дыры (закрыто соседом) - из других мест, остаток -
           из прежнего пака (доля остатка печатается);
  context  на каждый кадр свой вырез карты вокруг него (соседи видны), кадр дорисован поверх
           всего, чтобы был виден целиком; рисуется x8 и уменьшается до x4, как в gen_hd.

Модель та же, что у прежнего пака: SDXL Juggernaut + ControlNet tile и canny (gen_hd).
Альфа клетки - силуэт оригинала x4 (R-062). В мод ничего не пишется: клетки ложатся в
art\maps\paint\<режим>\<НАБОР>.PCK\<кадр>.png, листы - в art\maps\paint.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\map_paint.py --terrain CULTA_UBER --block CULTAFARM01 --mode whole,context
"""
import argparse
import json
import os
import sys
import time
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                      # noqa: E402
from PIL import Image, ImageDraw, ImageFilter           # noqa: E402

import map_mockup as mm                                 # noqa: E402
import pck_census as pc                                 # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("art", "maps", "paint")

# CLIP читает 77 токенов: сцена короткая, иначе хвост стиля отрезается (так было в первом прогоне)
SCENES = {
    "CULTAFARM01": "an old farm barn, wooden plank floor, sandstone brick base, "
                   "weathered vertical wooden boards, dark roof, green grass around | straw hay bales, "
                   "wooden staircase",
    "CARGO00": "a cargo ship deck at sea, green painted steel deck, helipad, metal railings, "
               "blue sea water | shipping containers, barrels, cabin with windows",
    "DESERT05": "a sandy desert, pale orange sand with small ripples |green saguaro cacti, "
                "dead dry trees, small desert bushes",
    "CULTASOLHUGE01": "a large farm warehouse, sandstone brick walls, dark corrugated roof, grey gravel "
                      "yard, green grass | stacked straw hay bales, yellow farm tractors, small wooden shed",
    # лотки A_PODS - по словам Vitali, основание разбитой капсулы; по MCD это отдельный предмет (R-071)
    # «red ribs» в прежней теме дали красные трещины на всех стенах (R-016); по листу оригинала стены -
    # сиреневый камень с бурыми прожилками
    "UBASE_00": "alien base room, pale lavender floor tiles, dark purple rock floor, purple organic stone "
                "walls with dark brown veins | red spherical pods on blue pipes, amber glass panels "
                "in pale frames, broken capsule bases with green sprouts",
    # пилот по картам: описания по макетам art/maps/<ТЕРРЕЙН>__<КАРТА>.png
    "URBAN06": "a city block building, flat roof of light grey gravel and concrete, grey plaster walls "
               "with small windows, grey concrete pillars, grey paved sidewalk | glass shop fronts, "
               "shop shelves with goods, cardboard boxes",
    "JUNGLE04": "a tropical jungle clearing, lush bright green grass | big broadleaf trees, "
                "ferns, small palms, tropical flowers",
    "CATACOMBS_33": "ancient jungle catacombs, rough brown earth and rock, grey cobblestone floor, "
                    "dark grey stone brick walls with green moss | creeping vines",
}
STYLE = ("isometric view of {scene}, pre-rendered 3D game art, realistic matte materials, "
         "detailed textures, soft light from the upper left, sharp focus")

def scene_prompts(scene):
    """Тема «поверхности | предметы» (R-016): всё, что названо в теме, модель рисует на каждом кадре.
    Возвращает (промпт участка - обе части, промпт поля полов и стен - только поверхности)."""
    # делить по голой черте: « |green» без пробела в DESERT05 не делилось, и поле песка получало
    # «сухие деревья, кустики» - на каждой клетке пустыни выросла веточка
    surf, _bar, things = (p.strip() for p in scene.partition("|"))
    return (STYLE.replace("{scene}", ", ".join(p for p in (surf, things) if p)),
            STYLE.replace("{scene}", surf))


# подсказка к кадру (R-007): участок, где кадр стоит, получает её В НАЧАЛО промпта. Описание -
# по кадру оригинала x4, а не по памяти (R-040). Коротко: хвост промпта режется по 77 токенам CLIP
FRAME_HINTS = {
    # прогон 8: окна растворились в досках, прогон 6: стали ставнями с косым крестом.
    # Слово cross модель читает как косой крест X (прогон 9) - в оригинале четыре стекла 2x2
    ("BARN", 7): "small window, four grey glass panes in dark wood frame",
    ("BARN", 8): "small window, four grey glass panes in dark wood frame",
    ("BARN", 12): "open dark window hole in brick",
    ("BARN", 13): "open dark window hole in brick",
}


# ------------------------------------------------------------------ сборка с владельцами пикселей

def layout(world, terrain, block, maxz=None, top=None, frame_of=None):
    """Экземпляры спрайтов блока в порядке рисования и карта владельцев пикселя (k=1).

    top = номер экземпляра, который рисуется поверх всех (режим context).
    frame_of = {номер экземпляра: кадр} - показать экземпляр другим кадром своей анимации.
    Возвращает (картинка RGBA, owner int32, список экземпляров, начало координат).
    """
    sets = world.sets_of(terrain)
    sizes = {s: len(world.records(s)) for s in sets}
    sx, sy, sz, cells = mm.read_block(world, block)
    w = (sx + sy) * 16 + 32
    h = (sx + sy) * 8 + sz * 24 + 40 + 16
    ox, oy = sy * 16, sz * 24 + 8
    inst = []
    for z in range(sz if maxz is None else min(sz, maxz + 1)):
        for y in range(sy):
            for x in range(sx):
                cell = cells.get((x, y, z))
                if not cell:
                    continue
                for part in range(4):
                    v = cell[part]
                    if not v:
                        continue
                    s, rec = pc.resolve(v, sets, sizes)
                    if s is None:
                        continue
                    r = world.records(s)[rec]
                    spr = world.sprite(s, r["frame"], None)
                    if spr is None:
                        continue
                    inst.append({"set": s.upper(), "frame": r["frame"], "z": z, "part": part,
                                 "x": ox + (x - y) * 16, "y": oy + (x + y) * 8 - z * 24 - r["p_level"],
                                 "spr": spr, "frames": r["frames"], "rec": rec, "p_level": r["p_level"]})
    for i, f in (frame_of or {}).items():
        # f - кадр той же записи или (кадр, P_Level) другой записи на том же месте (обломки, открытая дверь)
        d = inst[i]
        f, pl = f if isinstance(f, tuple) else (f, d["p_level"])
        spr = world.sprite(d["set"], f, None)
        if spr is not None:
            inst[i] = dict(d, frame=f, spr=spr, y=d["y"] + d["p_level"] - pl, p_level=pl)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    owner = np.full((h, w), -1, np.int32)
    order = list(range(len(inst)))
    if top is not None:
        order = [i for i in order if i != top] + [top]
    for i in order:
        d = inst[i]
        im.alpha_composite(d["spr"], (d["x"], d["y"]))
        a = np.asarray(d["spr"])[..., 3] > 0
        sub = owner[d["y"]:d["y"] + 40, d["x"]:d["x"] + 32]
        sub[a[:sub.shape[0], :sub.shape[1]]] = i
    return im, owner, inst


# ------------------------------------------------------------------ рисование

class Brush:
    def __init__(self, args):
        import gen_hd
        self.gh = gen_hd
        pipe = gen_hd.load_pipeline()
        # спереди: негатив тоже режется по 77 токенам CLIP, хвост NEGATIVE уже у предела
        neg = (args.neg_extra + ", " if args.neg_extra else "") + gen_hd.NEGATIVE
        self.painter = gen_hd.Painter(pipe, {}, neg, {})
        self.args = args

    def paint(self, rgba, g, prompt, seed, under=None, opts=None):
        """Картинка k=1 (RGBA) -> рисунок xg (RGB): два прохода, как Painter.paint в gen_hd.

        under - уже нарисованные клетки участка xg (RGBA): ложатся на вход поверх увеличенного
        оригинала, и новая клетка продолжает их тон и кладку, а не рисует свою.
        opts - свои настройки вместо общих (поле полов и стен, ключ --field)."""
        gh, a = self.gh, opts or self.args
        base = gh.fill_background(rgba, radius=3, blur=1.0)
        # только гладкое увеличение: xBRZ на входе проверен прогоном 7 и дал кляксы вместо досок (R-004)
        filled = gh.smooth_upscale(base, g)
        if under is not None:
            m = under.split()[3].filter(ImageFilter.GaussianBlur(g * 0.5))
            filled = Image.composite(under.convert("RGB"), filled.convert("RGB"), m)
        tile = filled.filter(ImageFilter.GaussianBlur(g * a.tile_blur))
        canny = gh.canny_image(filled, 20, 60)
        run_args = SimpleNamespace(cfg=a.cfg)
        first = self.painter.run(run_args, prompt, filled, [tile, canny], [a.tile, a.canny],
                                 a.strength, a.steps, seed)
        if a.refine <= 0:
            return first
        return self.painter.run(run_args, prompt, first, [first, gh.canny_image(first)],
                                [a.tile, a.canny], a.refine, a.steps, seed + 1000)


def silhouette(spr, k=4, soft=False):
    """Альфа оригинала xk. soft - без лесенки: бикубика и крутая ступень вокруг 0.5 (кромка резкая,
    диагональ ровная). Полам soft не давать - стык ромбов обязан быть точным (R-005)."""
    a = spr.split()[3]
    if not soft:
        return a.resize((spr.width * k, spr.height * k), Image.NEAREST)
    if EDGE_BLUR > 0:
        # размыв ступенчатой маски на EDGE_BLUR пикселей оригинала: лесенка уходит, листва - плавной кромкой
        big = a.resize((spr.width * k, spr.height * k), Image.NEAREST)
        m = np.asarray(big.filter(ImageFilter.GaussianBlur(EDGE_BLUR * k))).astype(np.float32) / 255
        m = np.clip((m - 0.5) * 4 + 0.5, 0, 1)
        return Image.fromarray((m * 255).astype(np.uint8))
    m = np.asarray(a.resize((spr.width * k, spr.height * k), Image.BICUBIC)).astype(np.float32) / 255
    m = np.clip((m - 0.5) * 4 + 0.5, 0, 1)
    return Image.fromarray((m * 255).astype(np.uint8))


def cell_from(painted, g, d, k=4):
    """Вырез клетки экземпляра d из рисунка xg, уменьшенный до xk."""
    box = (d["x"] * g, d["y"] * g, (d["x"] + 32) * g, (d["y"] + 40) * g)
    c = painted.crop(box)
    return c if g == k else c.resize((32 * k, 40 * k), Image.LANCZOS)


TONE = 0.7


def match_tone(rgb, spr, amount):
    """Средний цвет тела клетки -> средний цвет тела оригинала, множителем на канал.

    Каждый кадр рисуется в своём вырезе и получает свой оттенок: куски одной кирпичной стены
    выходили розоватыми пятнами. Сдвигается только СРЕДНЕЕ, фактура и перепады остаются от модели;
    amount 0 - не трогать, 1 - средний цвет ровно как у оригинала.
    """
    if amount <= 0:
        return rgb
    body = np.asarray(silhouette(spr)) > 0
    if body.sum() < 16:
        return rgb
    a = np.asarray(rgb.convert("RGB")).astype(np.float32)
    o = np.asarray(spr.convert("RGB")).astype(np.float32)[np.asarray(spr)[..., 3] > 0]
    gain = (o.mean(0) + 4) / (a[body].mean(0) + 4)
    gain = np.clip(gain, 0.6, 1.6) ** amount
    return Image.fromarray(np.clip(a * gain, 0, 255).astype(np.uint8))


SOFT_EDGE = False
EDGE_BLUR = 0.0


SAME_MIN = 0.5


SAME_MIN_OBJ = 0.3   # предмет на полу: дерево NEOJUNGLE 58 - это 46 процентов пола 0 под ним
SAME_ADD = 0.1       # вторая и третья основа - если добавляют хотя бы столько тела
SAME_MAX_BASES = 3


def same_base(world, root, s, f, spr, done, cache, part=1, avoid=()):
    """Готовые кадры, с которыми оригинал совпадает пиксель в пиксель на заметной доле тела.

    Окно BARN 13 - это стена BARN 11 плюс окошко (93 процента пикселей те же). Нарисованное своим
    участком, оно выходит заплаткой: кладка своя, не как у стены полем (прогон 14). То же у предметов:
    художник рисовал их поверх клетки пола или стены, и часто ЧУЖОГО набора (стена GOTHIC 13 - это
    ACHURCH2 4 плюс плющ, 94 процента; коряга MOUNT 15 стоит на полу MOUNT 10; перепись
    census/over_base.tsv). Основы берутся жадно: лучшая, затем та, что покрывает больше оставшегося,
    до SAME_MAX_BASES. Возвращает [(клетка x4 RGB float, маска своих пикселей 40x32, (набор, кадр),
    доля)] или None."""
    a = np.asarray(spr)
    body = a[..., 3] > 0
    n = body.sum()
    if n < 16:
        return None
    cand = []
    for s2, f2 in done:
        if (s2, f2) == (s, f) or (s2, f2) in avoid:
            continue
        o = world.sprite(s2, f2, None)
        if o is None or o.size != spr.size:
            continue
        b = np.asarray(o)
        same = body & (b[..., 3] > 0) & (np.abs(a[..., :3].astype(int) - b[..., :3].astype(int)).sum(-1) == 0)
        if same.sum() >= SAME_ADD * n:
            cand.append(((s2, f2), same))
    left = body.copy()
    got = []
    while cand and len(got) < SAME_MAX_BASES:
        # свой набор впереди при равенстве: окно BARN 13 и дальше собирается из BARN 11
        key, same = max(cand, key=lambda c: ((c[1] & left).sum(), c[0][0] == s))
        mine = same & left
        r = mine.sum() / n
        if r < (SAME_ADD if got else (SAME_MIN_OBJ if part == 3 else SAME_MIN)):
            break
        got.append((key, mine, r))
        left &= ~mine
        cand = [c for c in cand if c[0] != key]
    if not got:
        return None
    out = []
    for key, mine, r in got:
        if key not in cache:
            p = os.path.join(root, key[0] + ".PCK", "%d.png" % key[1])
            cache[key] = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)
        out.append((cache[key], mine, key, r))
    return out


def reuse_base(world, root, s, f, cell, spr, done, cache, k=4, part=1, avoid=()):
    """Совпавшие с готовыми кадрами пиксели - из них; своё рисование только там, где кадр другой,
    с переходом внутрь отличий (как верх стены в paint_tiled). Тон подгоняется ДО вставки: иначе
    match_tone по оригиналу с тёмным окошком затемняет и чужую, уже подогнанную кладку.
    Возвращает (картинка, [(набор, кадр)], доля тела из готовых) или None."""
    got = same_base(world, root, s, f, spr, done, cache, part, avoid)
    if got is None:
        return None
    own = np.asarray(match_tone(Image.fromarray(cell), spr, TONE).convert("RGB")).astype(np.float32)
    base = own.copy()
    same = np.zeros(np.asarray(spr).shape[:2], bool)
    for b, mine, _key, _r in got:
        m4 = np.kron(mine, np.ones((k, k), bool))
        base[m4] = b[m4]
        same |= mine
    # переход узкий, в обе стороны: щель окошка в оригинале 1-2 пикселя, широкий переход внутрь её
    # отличий гасил (первая проба - окно бледным пятном)
    # отличие - только внутри тела кадра: пустота вокруг силуэта отличием не считается, иначе край стены
    # тоже подмешивал свой рисунок (тест - 1949 пикселей мимо готовой стены)
    diff4 = np.kron((np.asarray(spr)[..., 3] > 0) & ~same, np.ones((k, k), bool))
    m = Image.fromarray((diff4 * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(k / 2))
    # хвост размытия срезан: дальше пары пикселей от отличий - ровно готовая стена, до байта
    wgt = np.clip(np.asarray(m).astype(np.float32) / 255 * 1.6 - 0.1, 0, 1)[..., None]
    out = base * (1 - wgt) + own * wgt
    return (Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), [g[2] for g in got],
            sum(g[3] for g in got))


def save_cell(root, s, f, rgb, spr, part=0, variant=0, tone=True):
    if tone:
        rgb = match_tone(rgb, spr, TONE)
    out = rgb.convert("RGBA")
    out.putalpha(silhouette(spr, soft=SOFT_EDGE and part != 0))
    d = os.path.join(root, s + ".PCK")
    os.makedirs(d, exist_ok=True)
    # вариант пола - <кадр>.v<n>.png, движок раскладывает их пятнами (Canvas32::groundFrameFor)
    out.save(os.path.join(d, ("%d.v%d.png" % (f, variant)) if variant else ("%d.png" % f)))


def run_whole(world, brush, args, prompt, root):
    """Этаж за этажом: рисуем срез, из него режем клетки ЭТОГО этажа."""
    _sx, _sy, sz, _c = mm.read_block(world, args.block)
    have = {}                               # (set, frame) -> [пиксели (y, x, rgb) по местам]
    specimen = {}
    for z in range(sz):
        im, owner, inst = layout(world, args.terrain, args.block, maxz=z)
        mine = [i for i, d in enumerate(inst) if d["z"] == z]
        if not mine:
            continue
        bb = im.getbbox()
        pad = 8
        bx0, by0 = max(0, bb[0] - pad), max(0, bb[1] - pad)
        bx1, by1 = min(im.width, bb[2] + pad), min(im.height, bb[3] + pad)
        crop = im.crop((bx0, by0, bx1, by1))
        t0 = time.time()
        painted = brush.paint(crop, args.g_whole, prompt, args.seed + z)
        full = Image.new("RGB", (im.width * args.g_whole, im.height * args.g_whole))
        full.paste(painted, (bx0 * args.g_whole, by0 * args.g_whole))
        painted.save(os.path.join(root, "_level%d.png" % z))
        print("  этаж %d: %dx%d x%d, %.0f с" % (z, crop.width, crop.height, args.g_whole, time.time() - t0),
              flush=True)
        for i in mine:
            d = inst[i]
            key = (d["set"], d["frame"])
            specimen[key] = d["spr"]
            vis = np.zeros((40, 32), bool)
            sub = owner[d["y"]:d["y"] + 40, d["x"]:d["x"] + 32]
            vis[:sub.shape[0], :sub.shape[1]] = sub == i
            vis &= np.asarray(d["spr"])[..., 3] > 0
            have.setdefault(key, []).append((vis, cell_from(full, args.g_whole, d)))
    old = mm.OLD_PACK
    stats = []
    for (s, f), places in sorted(have.items()):
        spr = specimen[(s, f)]
        body = np.asarray(spr)[..., 3] > 0
        places.sort(key=lambda p: -p[0].sum())
        out = np.asarray(places[0][1].convert("RGB")).copy()
        got = places[0][0].copy()
        for vis, c in places[1:]:
            add = vis & ~got
            if add.any():
                m4 = np.kron(add, np.ones((4, 4), bool))
                out[m4] = np.asarray(c.convert("RGB"))[m4]
                got |= add
        hole = body & ~got
        if hole.any():
            p = os.path.join(old, s + ".PCK", "%d.png" % f)
            if os.path.exists(p):
                o = np.asarray(Image.open(p).convert("RGB").resize((128, 160), Image.LANCZOS))
                m4 = np.kron(hole, np.ones((4, 4), bool))
                out[m4] = o[m4]
        share = hole.sum() / max(1, body.sum())
        stats.append(share)
        save_cell(root, s, f, Image.fromarray(out), spr)
    print("  whole: кадров %d, в среднем закрыто соседями %.0f%% (взято из прежнего пака)"
          % (len(stats), 100 * float(np.mean(stats) if stats else 0)), flush=True)


def run_context(world, brush, args, prompt, root):
    """Кадр в окружении: вырез карты вокруг места, где кадра видно больше всего."""
    _sx, _sy, sz, _c = mm.read_block(world, args.block)
    best = {}                               # (набор, запись) -> (видно пикселей, этаж, экземпляр)
    for z in range(sz):
        _im, owner, inst = layout(world, args.terrain, args.block, maxz=z)
        for i, d in enumerate(inst):
            if d["z"] != z:
                continue
            sub = owner[d["y"]:d["y"] + 40, d["x"]:d["x"] + 32]
            n = int((sub == i).sum())
            key = (d["set"], d["rec"])
            if key not in best or n > best[key][0]:
                best[key] = (n, z, i)
    # Задания: стоящие записи, плюс то, во что они превращаются - обломки (Die_MCD) и открытая дверь
    # (Alt_MCD), по цепочке. Таких записей на карте нет, рисуются на месте родителя.
    name = {x.upper(): x for x in world.sets_of(args.terrain)}
    jobs = [(s, r, z, i, "") for (s, r), (_n, z, i) in sorted(best.items())]
    seen = set(best)
    for s, r, z, i, _w in list(jobs):
        recs = world.records(name[s])
        chain = [(r, "")]
        while chain:
            cur, _why = chain.pop()
            for nxt, why in ((recs[cur]["die"], "обломки"), (recs[cur]["alt"], "дверь")):
                if nxt and nxt < len(recs) and (s, nxt) not in seen:
                    seen.add((s, nxt))
                    jobs.append((s, nxt, z, i, why))
                    chain.append((nxt, why))
    g = args.g_context
    rw, rh = args.window
    t_all = time.time()
    done = set()
    count = {"анимация": 0, "обломки": 0, "дверь": 0}
    for k, (s, r, z, i, why) in enumerate(jobs, 1):
        im, _owner, inst = layout(world, args.terrain, args.block, maxz=z, top=i)
        d = inst[i]
        cx, cy = d["x"] + 16, d["y"] + 20
        x0 = max(0, min(im.width - rw, cx - rw // 2))
        y0 = max(0, min(im.height - rh, cy - rh // 2))
        rec = world.records(name[s])[r]
        # Анимация (R-071): все кадры записи рисуются в том же месте, тем же описанием и тем же seed -
        # иначе в игре новый кадр сменяется старыми и предмет мигает.
        for fa in dict.fromkeys(rec["frames"]):
            if (s, fa) in done:
                continue
            if args.only_missing and os.path.exists(os.path.join(root, s + ".PCK", "%d.png" % fa)):
                done.add((s, fa))
                continue
            if why or fa != d["frame"]:
                im, _owner, inst = layout(world, args.terrain, args.block, maxz=z, top=i,
                                          frame_of={i: (fa, rec["p_level"])})
                d = inst[i]
                count[why or "анимация"] += 1
            crop = im.crop((x0, y0, x0 + rw, y0 + rh))
            painted = brush.paint(crop, g, prompt, args.seed + k)
            local = dict(d, x=d["x"] - x0, y=d["y"] - y0)
            save_cell(root, s, fa, cell_from(painted, g, local), d["spr"], d["part"])
            done.add((s, fa))
        if k == 1 or k % 10 == 0:
            el = time.time() - t_all
            print("  context: %d из %d, осталось ~%.0f мин" % (k, len(jobs), el / k * (len(jobs) - k) / 60),
                  flush=True)
    print("  context: дорисовано кадров анимации %(анимация)d, обломков %(обломки)d, открытых дверей %(дверь)d"
          % count, flush=True)


def done_under(root, inst, top, box, g, done, cache):
    """Готовые клетки участка xg поверх прозрачного: в порядке рисования, как layout; клетка, которой
    ещё нет, стирает то, что под ней, - там модель видит увеличенный оригинал.

    Без этого участок рядом с готовыми кадрами рисуется с нуля: окно BARN 13 вышло тёмной
    заплаткой на стене из BARN 11, нарисованного полем (прогон 12)."""
    k = 4
    x0, y0, x1, y1 = box
    can = np.zeros(((y1 - y0) * k, (x1 - x0) * k, 4), np.uint8)
    order = [i for i in range(len(inst)) if i != top] + ([top] if top is not None else [])
    any_done = False
    for i in order:
        d = inst[i]
        if d["x"] + 32 <= x0 or d["x"] >= x1 or d["y"] + 40 <= y0 or d["y"] >= y1:
            continue
        key = (d["set"], d["frame"])
        cx, cy = (d["x"] - x0) * k, (d["y"] - y0) * k
        sx0, sy0 = max(0, -cx), max(0, -cy)
        sx1, sy1 = min(32 * k, can.shape[1] - cx), min(40 * k, can.shape[0] - cy)
        dst = can[cy + sy0:cy + sy1, cx + sx0:cx + sx1]
        if key in done:
            if key not in cache:
                p = os.path.join(root, key[0] + ".PCK", "%d.png" % key[1])
                cache[key] = np.asarray(Image.open(p).convert("RGBA")) if os.path.exists(p) else None
            c = cache[key]
            if c is not None:
                src = c[sy0:sy1, sx0:sx1]
                on = src[..., 3] > 127
                dst[on] = src[on]
                dst[on, 3] = 255
                any_done = any_done or bool(on.any())
                continue
        m = np.kron(np.asarray(d["spr"])[..., 3] > 0, np.ones((k, k), bool))[sy0:sy1, sx0:sx1]
        dst[m] = 0
    if not any_done:
        return None
    im = Image.fromarray(can, "RGBA")
    return im if g == k else im.resize((im.width * g // k, im.height * g // k), Image.BICUBIC)


STEPS = ((16, 8), (-16, 8), (0, -24))     # соседняя клетка по x, по y, этаж выше - сдвиг на экране, k=1


def tile_lattice(inst_all, key):
    """Сдвиги, по которым кадр повторяется на карте: те из STEPS, вдоль которых стоит хотя бы три пары
    копий. Стена - вдоль себя и этажами, пол - ромбом; одиночный кадр - пусто."""
    pos = {(d["x"], d["y"]) for d in inst_all if (d["set"], d["frame"]) == key}
    return [st for st in STEPS if sum((x + st[0], y + st[1]) in pos for x, y in pos) >= 3]


PART_STEPS = {0: ((16, 8), (-16, 8)), 1: ((-16, 8), (0, -24)), 2: ((16, 8), (0, -24))}


def like_frequent(world, key, spr, t_uses):
    """Кадр совпадает хотя бы на SAME_MIN пикселей с более частым кадром того же набора."""
    a = np.asarray(spr)
    body = a[..., 3] > 0
    if body.sum() < 16:
        return False
    for (s2, f2), n2 in t_uses.items():
        if s2 != key[0] or f2 == key[1] or n2 <= t_uses.get(key, 0):
            continue
        o = world.sprite(s2, f2, None)
        if o is None or o.size != spr.size:
            continue
        b = np.asarray(o)
        same = body & (b[..., 3] > 0) & (np.abs(a[..., :3].astype(int) - b[..., :3].astype(int)).sum(-1) == 0)
        if same.sum() >= SAME_MIN * body.sum():
            return True
    return False


def terrain_tiling(world, terrain):
    """По ВСЕМ картам террейна: сколько раз стоит кадр и сколько пар соседних копий по каждому сдвигу.

    По одной карте решать нельзя: пол BARN 1 на амбаре лежит 2 раза и рисовался участком, а на складе
    CULTASOLHUGE01 застилает весь второй этаж - и вышел ромбической чешуёй (прогон 15). Так же и сетка:
    стена, что на первой карте в один этаж, на следующей стоит в два. Считается за полсекунды."""
    uses, pairs = {}, {}
    for b in world.blocks_of(terrain):
        try:
            _im, _o, inst = layout(world, terrain, b)
        except Exception:                                   # noqa: BLE001
            continue
        pos = {}
        for d in inst:
            key = (d["set"], d["frame"])
            uses[key] = uses.get(key, 0) + 1
            pos.setdefault(key, set()).add((d["x"], d["y"]))
        for key, ps in pos.items():
            pk = pairs.setdefault(key, {})
            for st in STEPS:
                pk[st] = pk.get(st, 0) + sum((x + st[0], y + st[1]) in ps for x, y in ps)
    return uses, pairs


def paint_tiled(world, brush, args, prompt, seed, spr, part, lattice):
    """Кадр, который повторяется на карте, рисуется полем из своих же копий и стыкуется сам с собой.

    Вырезанный из участка кадр со своими копиями не стыкуется: на длинной стене склада один BARN 11
    стоит вдоль и в два этажа, и каждый стык - линия, а между этажами - шов (прогон 11); на траве -
    косые полосы. Здесь поле копий рисуется одним рисунком, и клетка собирается как периодическая:
    пиксель = сумма по сдвигам решётки L рисунка в точке q+L с весом W(q+L), где W - размытая область
    центральной копии. Сумма по всем сдвигам решётки от сдвига не зависит - значит край клетки равен
    продолжению соседней копии. Закрытое соседями (верх стены под этажом выше) - из рисунка, где центр
    поверх всех, тем же seed.
    """
    # поле - своими настройками (--field): вольные направляющие предметов рисуют стык плиток рамкой -
    # крыша URBAN06 при x8 и tile 0.45 вышла сеткой светлых швов
    fa = getattr(args, "field_args", args)
    g = fa.g_context
    k = 4
    reach = 1 if len(lattice) > 1 else 2
    rng = range(-reach, reach + 1)
    offs = [(0, 0)]
    for n in rng:
        for m in (rng if len(lattice) > 1 else [0]):
            if (n, m) != (0, 0):
                offs.append((n, m))
    vec = lambda n, m: (n * lattice[0][0] + (m * lattice[1][0] if len(lattice) > 1 else 0),
                        n * lattice[0][1] + (m * lattice[1][1] if len(lattice) > 1 else 0))
    pts = [vec(n, m) for n, m in offs]
    pad = 8
    x_lo = min(p[0] for p in pts) - pad
    y_lo = min(p[1] for p in pts) - pad
    w = max(p[0] for p in pts) + 32 + pad - x_lo
    h = max(p[1] for p in pts) + 40 + pad - y_lo
    cx, cy = -x_lo, -y_lo                       # место центральной копии в поле

    def zlev(i):
        # этаж - по номеру копии вдоль шага (0, -24), а не по высоте на экране: сдвиг вдоль стены тоже
        # меняет высоту, и нижнюю копию рисовало раньше верхней - открывался тёмный торец кадра
        n, m = offs[i]
        if lattice[0] == (0, -24):
            return n
        return m if len(lattice) > 1 and lattice[1] == (0, -24) else 0

    def mosaic(top):
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        owner = np.full((h, w), -1, np.int32)
        order = sorted(range(len(pts)), key=lambda i: (zlev(i), pts[i][1], pts[i][0]))
        if top:
            order = [i for i in order if i != 0] + [0]
        a = np.asarray(spr)[..., 3] > 0
        for i in order:
            x, y = cx + pts[i][0], cy + pts[i][1]
            im.alpha_composite(spr, (x, y))
            owner[y:y + 40, x:x + 32][a] = i
        return im, owner

    im, owner = mosaic(False)
    painted = brush.paint(im, g, prompt, seed, opts=fa)
    P = np.asarray(painted.convert("RGB").resize((w * k, h * k), Image.LANCZOS)).astype(np.float32)
    # область центральной копии x4 (маска, не вход модели) и её размытие - вес W
    mine = Image.fromarray(((owner == 0) * 255).astype(np.uint8)).resize((w * k, h * k), Image.NEAREST)
    W = np.asarray(mine.filter(ImageFilter.GaussianBlur(3 * k))).astype(np.float32) / 255
    H, Wd = W.shape
    ys, xs = np.mgrid[0:40 * k, 0:32 * k]
    ys, xs = ys + cy * k, xs + cx * k
    acc = np.zeros((40 * k, 32 * k, 3), np.float32)
    wsum = np.zeros((40 * k, 32 * k), np.float32)
    lat = [vec(n, m) for n in range(-2, 3) for m in (range(-2, 3) if len(lattice) > 1 else [0])]
    for lx, ly in lat:
        yy, xx = ys + ly * k, xs + lx * k
        ok = (yy >= 0) & (yy < H) & (xx >= 0) & (xx < Wd)
        yc, xc = np.clip(yy, 0, H - 1), np.clip(xx, 0, Wd - 1)
        wt = np.where(ok, W[yc, xc], 0)
        acc += wt[..., None] * P[yc, xc]
        wsum += wt
    own = P[ys, xs]
    cell = np.where(wsum[..., None] > 1e-3, acc / np.maximum(wsum, 1e-3)[..., None], own)
    # закрытое соседями по полю: верх стены показывается у верхнего этажа и в конце ряда
    body = np.asarray(spr)[..., 3] > 0
    vis = owner[cy:cy + 40, cx:cx + 32] == 0
    hidden = body & ~vis
    repainted = 0
    if hidden.sum() > 0.02 * max(1, body.sum()):
        along = [v for v in lattice if v != (0, -24)]
        if len(lattice) > 1 and len(along) == 1:
            # стена этажами: верх виден у верхнего этажа, и там он стоит в ряду таких же копий - значит
            # и он обязан стыковаться вдоль стены. Берётся из ряда копий без этажа выше, собранного так же
            top_cell, _r = paint_tiled(world, brush, args, prompt, seed, spr, part, along)
            p2 = np.asarray(top_cell).astype(np.float32)
        else:
            im2, _o2 = mosaic(True)
            p2 = np.asarray(brush.paint(im2, g, prompt, seed, opts=fa).convert("RGB")
                            .resize((w * k, h * k), Image.LANCZOS)).astype(np.float32)[ys, xs]
        # переход - только ВНУТРЬ закрытого: видимые пиксели остаются из сборки, иначе у стыка с этажом
        # выше в них попадает другой рисунок и стык ломается (тест: 4.0 вместо 1.0)
        hid4 = np.kron(hidden, np.ones((k, k), bool))
        hm = Image.fromarray((hid4 * 255).astype(np.uint8))
        a = np.asarray(hm.filter(ImageFilter.GaussianBlur(2 * k))).astype(np.float32) / 255
        a = (np.clip((a - 0.5) * 2, 0, 1) * hid4)[..., None]
        cell = cell * (1 - a) + p2 * a
        repainted = 1
    return Image.fromarray(np.clip(cell, 0, 255).astype(np.uint8)), repainted


def run_regions(world, brush, args, prompt, root):
    """Участками: один рисунок на участок карты, из него режутся ВСЕ клетки, что в нём целиком.

    В режиме context каждый кадр рисовался в своём вырезе, и соседние кадры одной стены выходили с
    разным кирпичом, а пролёт лестницы - из разнобойных досок. Здесь соседи берутся из одного рисунка.
    Участок строится вокруг первой ещё не взятой клетки; что закрыто соседями спереди - дорисовывается
    тем же участком и тем же seed, но с клеткой поверх всех. Анимация, обломки и открытые двери - так же.
    """
    _sx, _sy, sz, _c = mm.read_block(world, args.block)
    g = args.g_context
    rw, rh = args.region
    name = {x.upper(): x for x in world.sets_of(args.terrain)}
    # место каждой записи - там, где её видно больше всего (как в context)
    best = {}
    for z in range(sz):
        _im, owner, inst = layout(world, args.terrain, args.block, maxz=z)
        for i, d in enumerate(inst):
            if d["z"] != z:
                continue
            sub = owner[d["y"]:d["y"] + 40, d["x"]:d["x"] + 32]
            n = int((sub == i).sum())
            key = (d["set"], d["rec"])
            if key not in best or n > best[key][0]:
                best[key] = (n, z, i)
    # сколько раз кадр пола лежит на карте: частому нужны варианты, иначе поле - решётка (R-039)
    _im, _o, inst_all = layout(world, args.terrain, args.block)
    uses = {}
    for d in inst_all:
        if d["part"] == 0:
            uses[(d["set"], d["frame"])] = uses.get((d["set"], d["frame"]), 0) + 1
    var_sets = {s.strip().upper() for s in args.variant_sets.split(",") if s.strip()}
    # что уже нарисовано на прошлых картах (общая папка --root) - не рисуется второй раз
    done = set()
    for d in inst_all:
        if os.path.exists(os.path.join(root, d["set"] + ".PCK", "%d.png" % d["frame"])):
            done.add((d["set"], d["frame"]))
    count = {"участков": 0, "дорисовок": 0, "анимация": 0, "обломки": 0, "дверь": 0,
             "вариантов": 0, "подсказок": 0, "новых": 0, "полем": 0, "из готовых": 0}
    cells_cache = {}
    base_cache = {}
    # основы для reuse_base - всё готовое в --root, любого набора и с любой карты (не только эта карта)
    pool = set()
    for dn in (os.listdir(root) if os.path.isdir(root) else ()):
        if dn.upper().endswith(".PCK"):
            for fn in os.listdir(os.path.join(root, dn)):
                if fn.endswith(".png") and fn[:-4].isdigit():
                    pool.add((dn[:-4].upper(), int(fn[:-4])))
    users = {}    # основа -> кадры, собранные из неё: обратно из них её не собираем
    late = {}     # нарисованные своими - повторная попытка в конце, когда готово больше
    t_all = time.time()
    # частые полы и стены - полем своих копий, чтобы стыковались сами с собой (прогон 11: шов по стене)
    if args.tile_min:
        # частота и сетка - по всем картам террейна (--tile-terrain 1), иначе по этой
        t_uses, t_pairs = terrain_tiling(world, args.terrain) if args.tile_terrain else ({}, {})
        first = {}
        for d in inst_all:
            key = (d["set"], d["frame"])
            first.setdefault(key, d)
            uses_all = first[key].setdefault("_n", 0)
            first[key]["_n"] = uses_all + 1
        for key, d in first.items():
            if key in t_uses:
                d["_n"] = t_uses[key]
        for j, (key, d) in enumerate(sorted(first.items())):
            if key in done or d["_n"] < args.tile_min or d["part"] == 3:
                continue
            if key in t_pairs:
                # у каждой части свои сдвиги: полы разных этажей не стыкуются (верхний закрывает нижний),
                # а параллельные ряды стен - не продолжение стены
                allowed = PART_STEPS.get(d["part"], STEPS)
                lattice = [st for st in STEPS if st in allowed and t_pairs[key].get(st, 0) >= 3]
                # стена с окошком - почти стена: её соберёт reuse_base из частой стены, а не поле
                if d["part"] != 0 and args.reuse_same and like_frequent(world, key, d["spr"], t_uses):
                    continue
            else:
                lattice = tile_lattice(inst_all, key)
            if not lattice:
                continue
            fp = getattr(args, "prompt_surf", prompt)
            tp = ", ".join([FRAME_HINTS[key], fp]) if key in FRAME_HINTS else fp
            print("  regions: подсказка поля %s %d: %s" % (key[0], key[1], tp), flush=True)
            cell, rep = paint_tiled(world, brush, args, tp, args.seed + 500 + j, d["spr"], d["part"], lattice)
            save_cell(root, key[0], key[1], cell, d["spr"], d["part"])
            done.add(key)
            count["полем"] += 1
            count["новых"] += 1
            count["дорисовок"] += rep
            if d["part"] == 0 and key[0] in var_sets:
                for v in range(1, args.variants + 1):
                    vc, _r = paint_tiled(world, brush, args, tp, args.seed + 500 + j + 100 * v,
                                         d["spr"], d["part"], lattice)
                    save_cell(root, key[0], key[1], vc, d["spr"], d["part"], variant=v)
                    count["вариантов"] += 1
            print("  regions: полем %s %d (на карте %d раз, сетка %s), %.0f с"
                  % (key[0], key[1], d["_n"], lattice, time.time() - t_all), flush=True)
    pending = sorted(best.items(), key=lambda kv: (kv[1][1], kv[0]))
    # запись, у которой готовы кадр, анимация, обломки и дверь - участка не заказывает
    def ready(key):
        s, r = key
        recs = world.records(name[s])
        todo, seen = [r], set()
        while todo:
            cur = todo.pop()
            if cur in seen or not cur or cur >= len(recs):
                continue
            seen.add(cur)
            if any((s, f) not in done for f in recs[cur]["frames"]):
                return False
            todo += [recs[cur]["die"], recs[cur]["alt"]]
        return (s, recs[r]["frame"]) in done
    left = {k for k, _v in pending if not ready(k)}
    n_todo = len(left)
    print("  regions: записей %d, уже нарисовано на прошлых картах %d, к рисованию %d"
          % (len(best), len(best) - n_todo, n_todo), flush=True)
    for key, (_n, z, i0) in pending:
        if key not in left:
            continue
        im, owner, inst = layout(world, args.terrain, args.block, maxz=z)
        d0 = inst[i0]
        x0 = max(0, min(im.width - rw, d0["x"] + 16 - rw // 2))
        y0 = max(0, min(im.height - rh, d0["y"] + 20 - rh // 2))
        count["участков"] += 1
        seed = args.seed + count["участков"]
        box = (x0, y0, x0 + rw, y0 + rh)
        # кто из оставшихся на этом этаже поместился в участок целиком - берётся отсюда
        here = []
        for k2 in list(left):
            _n2, z2, i2 = best[k2]
            if z2 != z:
                continue
            d = inst[i2]
            # solo - только предметам: полы, нарисованные каждый в своём участке, легли лоскутами
            if args.solo and k2 != key and inst[i2]["part"] != 0:
                continue
            # пол со своей подсказкой - предмет на земле (DESERT 7 - опунция): в чужом участке он
            # получал чужую подсказку и выходил змеёй соседа
            if args.solo and k2 != key and (inst[i2]["set"], inst[i2]["frame"]) in FRAME_HINTS:
                continue
            if x0 <= d["x"] and d["x"] + 32 <= x0 + rw and y0 <= d["y"] and d["y"] + 40 <= y0 + rh:
                here.append((k2, i2))
        # первой - подсказка предмета, вокруг которого строится участок: here собран из множества,
        # и без этого участку доставалась подсказка случайного соседа
        hints = list(dict.fromkeys(FRAME_HINTS[(inst[i]["set"], inst[i]["frame"])]
                                   for _k, i in sorted(here, key=lambda h: h[1] != i0)
                                   if (inst[i]["set"], inst[i]["frame"]) in FRAME_HINTS))
        # одна подсказка на участок: с двумя хвост про свет уходит за 77 токенов, а свет обязан быть
        # у всех участков один
        # solo: в участке один предмет - список предметов сцены он рисует на себе (красные наклейки
        # «товаров» на ящике URBAN06 88, R-016), поэтому только поверхности и своя подсказка
        base_p = getattr(args, "prompt_surf", prompt) if args.solo else prompt
        rprompt = ", ".join(hints[:1] + [base_p]) if hints else base_p
        count["подсказок"] += bool(hints)
        print("  regions: участок вокруг %s %d, в нём %s: %s"
              % (key[0], key[1], " ".join("%s:%d" % k for k, _i in here), rprompt), flush=True)

        def ud(inst_, top=None):
            # готовые клетки на вход: новые продолжают их тон и кладку (прогон 12, окно на стене)
            return done_under(root, inst_, top, box, g, done, cells_cache) if args.use_done else None
        painted = brush.paint(im.crop(box), g, rprompt, seed, ud(inst))
        # варианты частых полов этого участка: тот же участок другим seed, клетка режется оттуда же
        # варианты - только природной земле (--variant-sets): у досок и крыши они лоскутные (прогон 9)
        floors = [(k2, i) for k2, i in here
                  if inst[i]["part"] == 0 and inst[i]["set"] in var_sets
                  and (inst[i]["set"], inst[i]["frame"]) not in done
                  and uses.get((inst[i]["set"], inst[i]["frame"]), 0) >= args.variant_min]
        under0 = ud(inst) if floors else None
        var_paint = [brush.paint(im.crop(box), g, rprompt, seed + 100 * v, under0)
                     for v in range(1, args.variants + 1)] if floors else []
        for (s, r), i in here:
            left.discard((s, r))
            d = inst[i]
            local = dict(d, x=d["x"] - x0, y=d["y"] - y0)
            cell = np.asarray(cell_from(painted, g, local).convert("RGB")).copy()
            body = np.asarray(d["spr"])[..., 3] > 0
            vis = np.zeros((40, 32), bool)
            sub = owner[d["y"]:d["y"] + 40, d["x"]:d["x"] + 32]
            vis[:sub.shape[0], :sub.shape[1]] = sub == i
            hidden = body & ~vis
            m4 = np.kron(hidden, np.ones((4, 4), bool))
            if (s, d["frame"]) not in done and hidden.sum() > 0.02 * max(1, body.sum()):
                im2, _o2, _i2 = layout(world, args.terrain, args.block, maxz=z, top=i)
                own = FRAME_HINTS.get((s, d["frame"]))
                p2 = brush.paint(im2.crop(box), g, ", ".join([own, base_p]) if own else rprompt, seed, ud(_i2, i))
                cell[m4] = np.asarray(cell_from(p2, g, local).convert("RGB"))[m4]
                count["дорисовок"] += 1
            if (s, d["frame"]) not in done:
                # пол с вариантами - частый, его варианты рисуются своими, основу ему не подкладываем
                is_var = any(i == fi for _k, fi in floors) and var_paint
                rb = reuse_base(world, root, s, d["frame"], cell, d["spr"], pool | done, base_cache, part=d["part"],
                                avoid=users.get((s, d["frame"]), ())) \
                    if args.reuse_same and not is_var else None
                if rb is not None:
                    save_cell(root, s, d["frame"], rb[0], d["spr"], d["part"], tone=False)
                    count["из готовых"] += 1
                    for bk in rb[1]:
                        users.setdefault(bk, set()).add((s, d["frame"]))
                    print("  regions: %s %d - из готового %s (совпадает %.0f%%)"
                          % (s, d["frame"], " + ".join("%s %d" % bk for bk in rb[1]), 100 * rb[2]), flush=True)
                else:
                    save_cell(root, s, d["frame"], Image.fromarray(cell), d["spr"], d["part"])
                    if args.reuse_same and not is_var:
                        # основа может дорисоваться позже (пол под предметом - в соседнем участке)
                        late[(s, d["frame"])] = (cell, d["spr"], d["part"])
                pool.add((s, d["frame"]))
                done.add((s, d["frame"]))
                count["новых"] += 1
                if any(i == fi for _k, fi in floors):
                    for v, pv in enumerate(var_paint, 1):
                        vc = np.asarray(cell_from(pv, g, local).convert("RGB")).copy()
                        vc[m4] = cell[m4]     # закрытое соседями - из основной клетки, чтобы не рисовать ещё раз
                        save_cell(root, s, d["frame"], Image.fromarray(vc), d["spr"], d["part"], variant=v)
                        count["вариантов"] += 1
            # анимация этой записи, затем обломки и открытая дверь по цепочке - на этом же месте
            extra = [(r, "")]
            chain = [r]
            while chain:
                cur = chain.pop()
                cr = world.records(name[s])[cur]
                for nxt, why in ((cr["die"], "обломки"), (cr["alt"], "дверь")):
                    if nxt and nxt < len(world.records(name[s])) and all(nxt != e[0] for e in extra):
                        extra.append((nxt, why))
                        chain.append(nxt)
            for rr, why in extra:
                er = world.records(name[s])[rr]
                for fa in dict.fromkeys(er["frames"]):
                    if (s, fa) in done:
                        continue
                    im3, _o3, inst3 = layout(world, args.terrain, args.block, maxz=z, top=i,
                                             frame_of={i: (fa, er["p_level"])})
                    # обломки с подсказкой целого предмета выходили целым предметом (DESERT 11, 13, 15 -
                    # снова кактусы): у обломков и двери своя подсказка, без неё - «остатки» предмета
                    own3 = FRAME_HINTS.get((s, fa))
                    if own3 and why:
                        p3_prompt = ", ".join([own3, base_p])
                    elif why == "обломки":
                        p3_prompt = ", ".join(["broken wrecked remains and scattered pieces"] + hints[:1] + [base_p])
                    else:
                        p3_prompt = rprompt
                    p3 = brush.paint(im3.crop(box), g, p3_prompt, seed, ud(inst3, i))
                    d3 = inst3[i]
                    loc3 = dict(d3, x=d3["x"] - x0, y=d3["y"] - y0)
                    c3 = np.asarray(cell_from(p3, g, loc3).convert("RGB")).copy()
                    rb = reuse_base(world, root, s, fa, c3, d3["spr"], pool | done, base_cache, part=d3["part"],
                                    avoid=users.get((s, fa), ())) if args.reuse_same else None
                    if rb is not None:
                        save_cell(root, s, fa, rb[0], d3["spr"], d3["part"], tone=False)
                        count["из готовых"] += 1
                        for bk in rb[1]:
                            users.setdefault(bk, set()).add((s, fa))
                    else:
                        save_cell(root, s, fa, Image.fromarray(c3), d3["spr"], d3["part"])
                        if args.reuse_same:
                            late[(s, fa)] = (c3, d3["spr"], d3["part"])
                    done.add((s, fa))
                    count[why or "анимация"] += 1
                    count["новых"] += 1
        el = time.time() - t_all
        taken = n_todo - len(left)
        print("  regions: участок %d, записей взято %d из %d, осталось ~%.0f мин"
              % (count["участков"], taken, n_todo, el / max(1, taken) * len(left) / 60), flush=True)
    # второй заход: предмет рисовался раньше пола под ним - теперь пол готов
    for (s, f), (cell, spr, part) in late.items():
        rb = reuse_base(world, root, s, f, cell, spr, pool | done, base_cache, part=part,
                        avoid=users.get((s, f), ()))
        if rb is None:
            continue
        save_cell(root, s, f, rb[0], spr, part, tone=False)
        base_cache.pop((s, f), None)
        count["из готовых"] += 1
        for bk in rb[1]:
            users.setdefault(bk, set()).add((s, f))
        print("  regions: %s %d - из готового %s (совпадает %.0f%%), вторым заходом"
              % (s, f, " + ".join("%s %d" % bk for bk in rb[1]), 100 * rb[2]), flush=True)
    print("  regions: участков %(участков)d, дорисовок закрытого %(дорисовок)d, анимации %(анимация)d, "
          "обломков %(обломки)d, открытых дверей %(дверь)d, участков с подсказкой %(подсказок)d, "
          "вариантов пола %(вариантов)d, кадров полем %(полем)d, из готовых %(из готовых)d" % count,
          flush=True)
    el = time.time() - t_all
    print("  regions: новых кадров %d за %.0f с - %.1f с на кадр (варианты в счёт не входят)"
          % (count["новых"], el, el / max(1, count["новых"])), flush=True)


# ------------------------------------------------------------------ лист

def sheet(world, args, cols, level, path, k=2):
    pics = []
    for title, src in cols:
        if src is None:
            im, _m = mm.render(world, args.terrain, args.block, None, 1, maxz=level)
            im = im.resize((im.width * k, im.height * k), Image.NEAREST)
        else:
            im, _m = mm.render(world, args.terrain, args.block, src, 4, maxz=level)
            im = im.resize((im.width * k // 4, im.height * k // 4), Image.LANCZOS)
        pics.append(mm.label(im.convert("RGB"), title))
    w = sum(p.width for p in pics) + 6 * (len(pics) + 1)
    out = Image.new("RGB", (w, max(p.height for p in pics) + 12), (20, 20, 24))
    x = 6
    for p in pics:
        out.paste(p, (x, 6))
        x += p.width + 6
    out.save(path)
    print(path, out.size, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--terrain", required=True)
    ap.add_argument("--block", required=True)
    ap.add_argument("--mode", default="whole,context")
    ap.add_argument("--scene", default="", help="описание сцены; по умолчанию из SCENES")
    ap.add_argument("--g-whole", type=int, default=4, dest="g_whole")
    ap.add_argument("--g-context", type=int, default=8, dest="g_context")
    ap.add_argument("--window", default="160,128", help="вырез вокруг кадра в режиме context, пиксели k=1")
    ap.add_argument("--strength", type=float, default=0.65)
    ap.add_argument("--refine", type=float, default=0.45)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--cfg", type=float, default=6.5)
    ap.add_argument("--tile", type=float, default=0.6)
    ap.add_argument("--tile-blur", type=float, default=0.35, dest="tile_blur")
    ap.add_argument("--canny", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--sheet-only", action="store_true", dest="sheet_only")
    ap.add_argument("--tone", type=float, default=TONE,
                    help="подтянуть средний цвет клетки к оригиналу: 0 - нет, 1 - полностью")
    ap.add_argument("--tag", default="", help="приписка к папке результата, чтобы не затирать прошлый прогон")
    ap.add_argument("--soft-edge", action="store_true", dest="soft_edge",
                    help="кромка стен и предметов без лесенки (полы остаются точными)")
    ap.add_argument("--neg-extra", default="", dest="neg_extra", help="добавить к негативу")
    ap.add_argument("--pre", default="", help="не используется: вход модели только гладкий (R-004)")
    ap.add_argument("--region", default="96,80", help="участок режима regions, пиксели k=1")
    ap.add_argument("--variants", type=int, default=0,
                    help="режим regions: сколько вариантов .v1..vN рисовать частым полам (R-039: не меньше 3)")
    ap.add_argument("--variant-min", type=int, default=6, dest="variant_min",
                    help="пол получает варианты, если лежит на карте не меньше стольких раз")
    ap.add_argument("--variant-sets", default="", dest="variant_sets",
                    help="наборы через запятую, чьим полам можно варианты: природная земля, не доски и не крыша")
    ap.add_argument("--tile-min", type=int, default=0, dest="tile_min",
                    help="режим regions: пол и стену, что стоят на карте не меньше стольких раз, рисовать полем "
                         "своих копий, чтобы стыковались сами с собой; 0 - не рисовать")
    ap.add_argument("--use-done", type=int, default=1, dest="use_done",
                    help="режим regions: 1 - готовые клетки участка идут на вход модели поверх оригинала")
    ap.add_argument("--tile-terrain", type=int, default=1, dest="tile_terrain",
                    help="режим regions: частоту и сетку кадра для --tile-min считать по всем картам террейна, "
                         "а не по этой (пол, редкий здесь, на соседней карте застилает этаж)")
    ap.add_argument("--reuse-same", type=int, default=1, dest="reuse_same",
                    help="режим regions: стена, совпадающая с готовым кадром на половину пикселей и больше, "
                         "берёт совпавшее из него (окно в стене - стена плюс окошко)")
    ap.add_argument("--root", default="",
                    help="общая папка клеток для серии карт: уже нарисованное в ней не рисуется второй раз")
    ap.add_argument("--edge-blur", type=float, default=0.0, dest="edge_blur",
                    help="с --soft-edge: размыть силуэт предмета на столько пикселей оригинала (0 - как было)")
    ap.add_argument("--field", default="",
                    help="свои настройки поля полов и стен: g=16,tile=0.6,canny=0.2,strength=0.65,tile_blur=0")
    ap.add_argument("--solo", action="store_true",
                    help="regions: с участка берётся только запись в его центре - каждой свой участок и своя подсказка")
    ap.add_argument("--hints", default="", help="json подсказок на кадр {\"НАБОР:кадр\": \"текст\"}")
    ap.add_argument("--only-missing", action="store_true", dest="only_missing",
                    help="рисовать только кадры, которых в папке результата ещё нет")
    args = ap.parse_args(argv)
    if args.pre:
        # xBRZ и nearest оставляют пятна оригинала, и модель рисует их как содержание:
        # прогон 7 амбара - пол из клякс вместо досок; прогон 8 без него - доски (R-004)
        raise SystemExit("--pre %s: вход модели только гладкий, фильтры перед моделью запрещены (R-004)"
                         % args.pre)
    globals()["TONE"] = args.tone
    globals()["SOFT_EDGE"] = args.soft_edge
    globals()["EDGE_BLUR"] = args.edge_blur
    fa = dict(vars(args))
    for kv in filter(None, args.field.split(",")):
        name, val = kv.split("=")
        name = {"g": "g_context"}.get(name.strip(), name.strip().replace("-", "_"))
        if name not in fa:
            raise SystemExit("--field: нет такой настройки %s" % name)
        fa[name] = type(fa[name])(val)
    args.field_args = SimpleNamespace(**fa)
    args.window = tuple(int(v) for v in args.window.split(","))
    args.region = tuple(int(v) for v in args.region.split(","))

    world = mm.World()
    scene = args.scene or SCENES.get(args.block, "")
    if not scene:
        raise SystemExit("нет описания сцены: --scene")
    prompt, args.prompt_surf = scene_prompts(scene)
    if args.hints:
        # подсказки на кадр из файла {"НАБОР:кадр": "что нарисовано"} - поверх FRAME_HINTS (R-007)
        with open(args.hints, encoding="utf-8-sig") as f:
            for k, v in json.load(f).items():
                s, fr = k.rsplit(":", 1)
                FRAME_HINTS[(s.upper(), int(fr))] = v
    modes =[m.strip() for m in args.mode.split(",") if m.strip()]
    if not args.sheet_only:
        brush = Brush(args)
        for m in modes:
            root = args.root or os.path.join(OUT, "%s_%s%s" % (args.block, m, args.tag))
            os.makedirs(root, exist_ok=True)
            print("=== %s %s" % (args.block, m), flush=True)
            {"whole": run_whole, "context": run_context, "regions": run_regions}[m](world, brush, args, prompt, root)

    import score_batch as sb
    cols = [("оригинал", None), ("прежний пак", mm.OLD_PACK), ("мод сейчас", sb.MOD)]
    cols += [("новый: %s" % m, args.root or os.path.join(OUT, "%s_%s%s" % (args.block, m, args.tag)))
             for m in modes]
    sx, sy, sz, _c = mm.read_block(world, args.block)
    # большой блок - один лист целиком, у маленького - срез каждого этажа
    levels = range(sz) if sx + sy <= 24 else [sz - 1]
    for level in levels:
        sheet(world, args, cols, level,
              os.path.join(OUT, "%s%s_level%d.png" % (args.block, args.tag, level)),
              k=2 if sx + sy <= 24 else 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
