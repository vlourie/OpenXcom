#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""map_mockup.py - блок карты X-Piratez, собранный из тайлов так же, как его рисует игра.

Зачем. Кадр террейна - это кусок чего-то большего: стена амбара, ступень трапа, угол ангара.
По одному кадру 32x40 модель этого не видит и не может знать, как кадр должен сойтись с
соседями. Здесь блок .MAP раскладывается по клеткам ровно как в движке, и получается:
  * лист блока: «оригинал | прежний пак | мод сейчас» на тёмном полу;
  * макет кадра: вырез блока вокруг клетки, где кадр стоит, с рамкой на нём, - то, что можно
    дать модели вторым изображением («вот эта стена - часть вот этого амбара»);
  * где стоит кадр: блоки и клетки, в которых встречается запись MCD с этим кадром.

Всё сверено с кодом, а не по памяти:
  * .MAP: 3 байта (y, x, z), дальше по 4 байта на клетку (пол, стена З, стена С, объект),
    x быстрее всего, потом y, уровни сверху вниз (BattlescapeGenerator::loadMAP);
  * байт клетки -> набор и запись по сквозной нумерации mapDataSets террейна
    (RuleTerrain::getMapData, у нас pck_census.resolve);
  * экран: x = (mx - my)*16, y = (mx + my)*8 - mz*24 (Camera::convertMapToScreen), спрайт
    поднимается на P_Level (байт 49 MCD, MapData::setYOffset);
  * порядок: z, потом y, потом x; в клетке пол, стена З, стена С, объект (Map::drawTerrain).
Тени, свет, юниты и полустены (северная стена при западной) не рисуются - это макет.

    py -3 tools\hdart\map_mockup.py --find BARN:16
    py -3 tools\hdart\map_mockup.py --block FARM07 --terrain FARM
    py -3 tools\hdart\map_mockup.py --mockup BARN:16
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image, ImageDraw                        # noqa: E402

import pck_census as pc                                 # noqa: E402
import tile_forge as tf                                 # noqa: E402

ENC = "utf-8-sig"
INSTALL = os.path.join("Пиратки", "Dioxine_XPiratez")
SHEETS = os.path.join("art", "TERRAIN")
OLD_PACK = os.path.join("art", "_backup", "TERRAIN_before_lora_20260924_1057")
OUT = os.path.join("art", "maps")
CACHE = os.path.join(OUT, "usage.json")
FLOOR_BG = (38, 38, 42)
P_LEVEL = 49


class World:
    """Террейны, записи MCD и файлы установки - один раз на запуск."""

    def __init__(self, install=INSTALL, mod="Piratez", master="xcom1"):
        mod_dir = os.path.join(install, "user", "mods", mod)
        self.files = pc.Files([mod_dir, os.path.join(install, "standard", master),
                               os.path.join(install, "UFO")])
        self.terrains = pc.collect_terrains(mod_dir)
        self.mcd = {}
        self.sheets = {}
        self.hd = {}

    def records(self, s):
        if s not in self.mcd:
            path = self.files.find(os.path.join("TERRAIN", s + ".MCD"))
            recs = []
            if path:
                with open(path, "rb") as f:
                    data = f.read()
                recs = [{"frame": data[i], "frames": list(data[i:i + 8]),
                         "p_level": data[i + P_LEVEL], "type": data[i + 53],
                         "die": data[i + 44], "alt": data[i + 46]}
                        for i in range(0, len(data) - pc.MCD_RECORD + 1, pc.MCD_RECORD)]
            self.mcd[s] = recs
        return self.mcd[s]

    def sets_of(self, terrain):
        return [str(s) for s in (self.terrains[terrain].get("mapDataSets") or [])]

    def blocks_of(self, terrain):
        return [b["name"] for b in (self.terrains[terrain].get("mapBlocks") or [])
                if isinstance(b, dict) and b.get("name")]

    def sheet(self, s):
        name = s.upper() + ".PCK"
        if name not in self.sheets:
            try:
                self.sheets[name] = tf.Sheet(SHEETS, name)
            except Exception:                                   # noqa: BLE001
                self.sheets[name] = None
        return self.sheets[name]

    def sprite(self, s, frame, source):
        """Кадр набора: оригинал (source=None, 32x40) или клетка HD-пака (128x160)."""
        if source is None:
            sh = self.sheet(s)
            if sh is None or frame >= sh.lay["count"]:
                return None
            return sh.frame(frame).convert("RGBA")
        key = (source, s, frame)
        if key not in self.hd:
            p = os.path.join(source, s.upper() + ".PCK", "%d.png" % frame)
            self.hd[key] = Image.open(p).convert("RGBA") if os.path.exists(p) else None
        return self.hd[key]

    def variants(self, s, frame, source):
        """Варианты клетки пола <кадр>.v1.png, v2... в HD-паке (как их ищет движок: без пропусков)."""
        out = []
        while True:
            key = (source, s, frame, len(out) + 1)
            if key not in self.hd:
                p = os.path.join(source, s.upper() + ".PCK", "%d.v%d.png" % (frame, len(out) + 1))
                self.hd[key] = Image.open(p).convert("RGBA") if os.path.exists(p) else None
            if self.hd[key] is None:
                return out
            out.append(self.hd[key])


def read_block(world, block):
    path = world.files.find(os.path.join("MAPS", block + ".MAP"))
    if not path:
        raise SystemExit("нет MAPS/%s.MAP" % block)
    with open(path, "rb") as f:
        data = f.read()
    sy, sx, sz = data[0], data[1], data[2]
    cells = {}
    body = data[3:]
    x = y = 0
    z = sz - 1
    for i in range(0, len(body) - 3, 4):
        cells[(x, y, z)] = tuple(body[i:i + 4])
        x += 1
        if x == sx:
            x, y = 0, y + 1
        if y == sy:
            y, z = 0, z - 1
    return sx, sy, sz, cells


def terrain_for(world, block, hint=None):
    if hint:
        return hint
    for t in sorted(world.terrains):
        if block in world.blocks_of(t):
            return t
    raise SystemExit("блок %s не найден ни в одном террейне" % block)


def render(world, terrain, block, source=None, k=1, mark=None, fallback=True, maxz=None):
    """Блок целиком. mark = (набор, кадр): такие клетки попадают в список рамок.

    source - папка HD-пака; кадра нет в паке -> оригинал nearest xk (fallback).
    Возвращает картинку и список (набор, кадр, прямоугольник) для отмеченных клеток.
    """
    sets = world.sets_of(terrain)
    sizes = {s: len(world.records(s)) for s in sets}
    sx, sy, sz, cells = read_block(world, block)
    w = (sx + sy) * 16 + 32
    h = (sx + sy) * 8 + sz * 24 + 40 + 16
    ox, oy = sy * 16, sz * 24 + 8
    im = Image.new("RGBA", (w * k, h * k), FLOOR_BG + (255,))
    marks = []
    # maxz: срез этажа, как в игре при переключении уровня - всё выше не рисуется
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
                    spr = world.sprite(s, r["frame"], source) if source else None
                    if spr is not None and part == 0:
                        # варианты пола пятнами по 3x3 клетки; движок ещё и смешивает край пятна,
                        # здесь край резкий - стык на макете виднее, чем в игре
                        vs = world.variants(s, r["frame"], source)
                        if vs:
                            n = (x // 3 * 7919 + y // 3 * 104729 + z * 31) * 2654435761 % 4294967296
                            j = n % (len(vs) + 1)
                            spr = spr if j == 0 else vs[j - 1]
                    if spr is None:
                        spr = world.sprite(s, r["frame"], None)
                        if spr is None:
                            continue
                        if not fallback and source:
                            continue
                        if k > 1:
                            spr = spr.resize((spr.width * k, spr.height * k), Image.NEAREST)
                    elif source and spr.width != 32 * k:
                        spr = spr.resize((32 * k, 40 * k), Image.LANCZOS)
                    px = ox + (x - y) * 16
                    py = oy + (x + y) * 8 - z * 24 - r["p_level"]
                    im.alpha_composite(spr, (px * k, py * k))
                    if mark and s.upper() == mark[0] and r["frame"] == mark[1]:
                        marks.append((s, r["frame"], (px * k, py * k, (px + 32) * k, (py + 40) * k), z))
    return im, marks


# ------------------------------------------------------------------ где стоит кадр

def usage(world):
    """(набор, кадр) -> список [террейн, блок, клеток]. Считается один раз и кладётся в кэш."""
    if os.path.exists(CACHE):
        with open(CACHE, encoding=ENC) as f:
            return json.load(f)
    out = {}
    for t in sorted(world.terrains):
        sets = world.sets_of(t)
        sizes = {s: len(world.records(s)) for s in sets}
        for b in world.blocks_of(t):
            p = world.files.find(os.path.join("MAPS", b + ".MAP"))
            if not p:
                continue
            count = {}
            for cell in pc.read_map(p):
                for v in cell:
                    if not v:
                        continue
                    s, rec = pc.resolve(v, sets, sizes)
                    if s is None:
                        continue
                    key = "%s:%d" % (s.upper(), world.records(s)[rec]["frame"])
                    count[key] = count.get(key, 0) + 1
            for key, n in count.items():
                out.setdefault(key, []).append([t, b, n])
    os.makedirs(OUT, exist_ok=True)
    with open(CACHE, "w", encoding=ENC) as f:
        json.dump(out, f, ensure_ascii=False)
    return out


def parse_frame(text):
    s, i = text.split(":")
    s = s.upper()
    return (s[:-4] if s.endswith(".PCK") else s), int(i)


# ------------------------------------------------------------------ листы

def label(im, text):
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, im.width, 18), fill=(20, 20, 24))
    d.text((6, 3), text, fill=(255, 220, 0))
    return im


def mark_level(world, terrain, block, mark):
    """Этаж первой клетки с отмеченным кадром - по нему режется всё, что выше."""
    _im, marks = render(world, terrain, block, None, 1, mark)
    return marks[0][3] if marks else None


def block_sheet(world, terrain, block, mark=None, k=2, level=None):
    """«оригинал | прежний пак | мод сейчас» - все в одном масштабе k (оригинал nearest).
    level: срез этажа; при отмеченном кадре по умолчанию его этаж."""
    import score_batch as sb
    if level is None and mark:
        level = mark_level(world, terrain, block, mark)
    cols = [("оригинал", None), ("прежний пак (SDXL)", OLD_PACK), ("мод сейчас", sb.MOD)]
    pics = []
    for title, src in cols:
        if src is None:
            im, marks = render(world, terrain, block, None, 1, mark, maxz=level)
            im = im.resize((im.width * k, im.height * k), Image.NEAREST)
            marks = [(s, f, tuple(v * k for v in r)) for s, f, r, _z in marks]
        else:
            im, marks = render(world, terrain, block, src, 4, mark, maxz=level)
            im = im.resize((im.width * k // 4, im.height * k // 4), Image.LANCZOS)
            marks = [(s, f, tuple(v * k // 4 for v in r)) for s, f, r, _z in marks]
        d = ImageDraw.Draw(im)
        for _s, _f, r in marks:
            d.rectangle(r, outline=(255, 40, 40), width=2)
        pics.append(label(im.convert("RGB"), "%s  %s / %s" % (title, terrain, block)))
    w = sum(p.width for p in pics) + 6 * (len(pics) + 1)
    h = max(p.height for p in pics) + 12
    out = Image.new("RGB", (w, h), (20, 20, 24))
    x = 6
    for p in pics:
        out.paste(p, (x, 6))
        x += p.width + 6
    return out


def mockup(world, frame_key, terrain, block, radius=3):
    """Макет кадра: блок в оригинале x4 (гладко, без ступенек), вырез вокруг первой клетки
    с этим кадром, рамка на клетке. Это второе изображение для модели."""
    s, f = frame_key
    im, marks = render(world, terrain, block, None, 1, (s, f),
                       maxz=mark_level(world, terrain, block, (s, f)))
    if not marks:
        return None
    x0, y0, x1, y1 = marks[0][2]
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    rw, rh = 32 * radius, 40 * radius
    box = (max(0, cx - rw), max(0, cy - rh), min(im.width, cx + rw), min(im.height, cy + rh))
    crop = im.crop(box).resize(((box[2] - box[0]) * 4, (box[3] - box[1]) * 4), Image.NEAREST)
    d = ImageDraw.Draw(crop)
    d.rectangle(((x0 - box[0]) * 4, (y0 - box[1]) * 4, (x1 - box[0]) * 4, (y1 - box[1]) * 4),
                outline=(255, 40, 40), width=4)
    return crop.convert("RGB")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--find", help="НАБОР:кадр - в каких блоках стоит")
    ap.add_argument("--block", help="блок карты: лист «оригинал | прежний пак | мод»")
    ap.add_argument("--terrain", help="террейн блока (по умолчанию первый, где блок есть)")
    ap.add_argument("--mark", help="НАБОР:кадр - обвести на листе блока")
    ap.add_argument("--mockup", help="НАБОР:кадр - макет вокруг кадра в самом ходовом блоке")
    ap.add_argument("--k", type=int, default=2, help="масштаб листа блока")
    ap.add_argument("--level", type=int, help="срез: этажи выше не рисуются")
    args = ap.parse_args(argv)

    world = World()
    os.makedirs(OUT, exist_ok=True)
    if args.find:
        key = "%s:%d" % parse_frame(args.find)
        rows = sorted(usage(world).get(key, []), key=lambda r: -r[2])
        print("%s стоит в %d блоках, клеток %d" % (key, len(rows), sum(r[2] for r in rows)))
        for t, b, n in rows[:30]:
            print("  %-24s %-20s %d" % (t, b, n))
    if args.block:
        t = terrain_for(world, args.block, args.terrain)
        mark = parse_frame(args.mark) if args.mark else None
        out = block_sheet(world, t, args.block, mark, args.k, args.level)
        p = os.path.join(OUT, "%s__%s.png" % (t, args.block))
        out.save(p)
        print(p, out.size)
    if args.mockup:
        fk = parse_frame(args.mockup)
        rows = sorted(usage(world).get("%s:%d" % fk, []), key=lambda r: -r[2])
        if not rows:
            raise SystemExit("кадр %s:%d ни в одном блоке не стоит" % fk)
        t, b, _n = rows[0]
        im = mockup(world, fk, t, b)
        p = os.path.join(OUT, "mockup_%s_%d.png" % fk)
        im.save(p)
        print(p, "из", t, b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
