#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Сцена для листов по тикетам: блок карты Пираток, выложенный как движок, - классика | HD сейчас | HD новое.

Сейв тикета (_quick_.asav) - сейв геоскейпа, боя в нём нет (binTiles нет), поэтому map_truth.Battle клеток не
даёт. Сцена берёт тот блок MAP, где стоят те же кадры (map_mockup --find НАБОР:кадр), и вырезает окно вокруг
нужных клеток. Рисование - как map_mockup.render: z, y, x, четыре части клетки, сдвиг на P_Level, варианты пола
пятнами 3x3 клетки (как в mockup). Отличия: классика красится палитрой Пираток (water_build.palette, не листы
art/TERRAIN - R-444), HD берётся из пака УСТАНОВКИ игры, а подмена кадров (новые, ещё не в паке) - словарём
override {(НАБОР, кадр): PIL RGBA 128x160}; подмена закрывает и варианты кадра.

    import ticket_scene as ts
    sc = ts.Scene()
    im = sc.render("URBAN_WASTE", "URBANWASTE62", mode="classic", k=4)
    im = sc.render("URBAN_WASTE", "URBANWASTE62", mode="hd", override={("URBAN_WASTE", 52): img}, k=4)
    ts.sheet([("классика", a), ("сейчас", b)], box, out_path, shot=<PIL>)
Только чтение; ничего в мод не пишет.
"""
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)
import map_mockup as mm            # noqa: E402
import pck_census as pc            # noqa: E402
import water_build as wb           # noqa: E402

BG = (26, 26, 30)
FONT = "C:/Windows/Fonts/arial.ttf"
PACK = wb.INST / "user" / "mods" / "hd" / "hd" / "TERRAIN"


class Scene:
    def __init__(self):
        self.w = mm.World()
        self.pal = wb.palette()
        self._cls = {}
        self._hd = {}

    # --- кадры
    def classic(self, s, f):
        key = (s, f)
        if key not in self._cls:
            if s not in self._cls:
                self._cls[s] = wb.read_set(s)
            fr = self._cls[s]
            if f >= len(fr):
                self._cls[key] = None
            else:
                a = fr[f]
                rgba = np.zeros((40, 32, 4), np.uint8)
                m = a > 0
                rgba[m, :3] = self.pal[a[m]][:, :3]
                rgba[m, 3] = 255
                im = Image.fromarray(rgba, "RGBA")
                self._cls[key] = im.resize((128, 160), Image.NEAREST)
        return self._cls[key]

    def hd(self, s, f, var=0):
        key = (s, f, var)
        if key not in self._hd:
            name = "%d.png" % f if var == 0 else "%d.v%d.png" % (f, var)
            p = PACK / (s + ".PCK") / name
            self._hd[key] = Image.open(p).convert("RGBA") if p.exists() else None
        return self._hd[key]

    def variants(self, s, f):
        out, i = [], 1
        while self.hd(s, f, i) is not None:
            out.append(self.hd(s, f, i))
            i += 1
        return out

    # --- рисование
    def render(self, terrain, block, mode="hd", override=None, k=4, maxz=None, marks=()):
        """Блок целиком, k - масштаб (HD 4). marks - набор (НАБОР, кадр): вернуть ещё их прямоугольники."""
        override = override or {}
        sets = self.w.sets_of(terrain)
        sizes = {s: len(self.w.records(s)) for s in sets}
        sx, sy, sz, cells = mm.read_block(self.w, block)
        wd = (sx + sy) * 16 + 32
        ht = (sx + sy) * 8 + sz * 24 + 40 + 16
        ox, oy = sy * 16, sz * 24 + 8
        im = Image.new("RGBA", (wd * k, ht * k), BG + (255,))
        found = []
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
                        r = self.w.records(s)[rec]
                        fr = r["frame"]
                        S = s.upper()
                        if mode == "classic":
                            spr = self.classic(S, fr)
                        else:
                            spr = override.get((S, fr))
                            if spr is None:
                                spr = self.hd(S, fr)
                                if spr is not None and part == 0:
                                    vs = self.variants(S, fr)
                                    if vs:
                                        n = (x // 3 * 7919 + y // 3 * 104729 + z * 31) * 2654435761 % 4294967296
                                        j = n % (len(vs) + 1)
                                        spr = spr if j == 0 else vs[j - 1]
                            if spr is None:
                                spr = self.classic(S, fr)
                        if spr is None:
                            continue
                        if spr.width != 32 * k:
                            spr = spr.resize((32 * k, 40 * k), Image.NEAREST if mode == "classic" else Image.LANCZOS)
                        px = ox + (x - y) * 16
                        py = oy + (x + y) * 8 - z * 24 - r["p_level"]
                        im.alpha_composite(spr, (px * k, py * k))
                        if (S, fr) in marks:
                            found.append((S, fr, (px * k, py * k, (px + 32) * k, (py + 40) * k), z, (x, y)))
        return im, found


def find_cells(scene, terrain, block, keys):
    """Прямоугольники клеток с кадрами keys (список (НАБОР, кадр)) - по классике, быстро."""
    _im, found = scene.render(terrain, block, "classic", k=1, marks=set(keys))
    return found


def window(found, w, h, k=4, pad=(0, 0)):
    """Окно w x h (в пикселях базы, x k) вокруг середины отмеченных клеток."""
    xs = [(f[2][0] + f[2][2]) / 2 for f in found]
    ys = [(f[2][1] + f[2][3]) / 2 for f in found]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    return (int(cx - w * k / 2), int(cy - h * k / 2), int(cx + w * k / 2), int(cy + h * k / 2))


def font(n=22):
    try:
        return ImageFont.truetype(FONT, n)
    except OSError:
        return ImageFont.load_default()


def label(im, text, n=22):
    d = ImageDraw.Draw(im)
    f = font(n)
    d.rectangle((0, 0, im.width, n + 10), fill=(15, 15, 18))
    d.text((8, 4), text, fill=(255, 220, 0), font=f)
    return im


def crop_pad(im, box):
    """Вырез box, за краем картинки - фон."""
    out = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), BG + (255,))
    out.alpha_composite(im, (-box[0], -box[1]))
    return out


def sheet(panels, out_path, cols=0, gap=8, width=0):
    """panels - список (подпись, картинка); раскладка в cols колонок (по умолчанию все в ряд)."""
    cols = cols or len(panels)
    pics = []
    for t, im in panels:
        im = im.convert("RGB")
        if width and im.width != width:
            im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
        pics.append(label(im, t))
    rows = [pics[i:i + cols] for i in range(0, len(pics), cols)]
    W = max(sum(p.width for p in r) + gap * (len(r) + 1) for r in rows)
    H = sum(max(p.height for p in r) + gap for r in rows) + gap
    out = Image.new("RGB", (W, H), (12, 12, 14))
    y = gap
    for r in rows:
        x = gap
        for p in r:
            out.paste(p, (x, y))
            x += p.width + gap
        y += max(p.height for p in r) + gap
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path)
    return out


def install_files(files, generator, version, approval, why):
    """Поставить файлы в мод hd через манифест: stage + save + install в game и repo + сверка хэшей.
    files - {относительный путь пака 'TERRAIN/НАБОР.PCK/N.png': путь к готовому png}. Только по слову Vitali
    и под очередью правок (CLAUDE.md); скрипты тикетов зовут это лишь с --install --yes."""
    import hashlib
    import build_hd_pack as bp
    man = bp.load()
    rels = []
    for rel, src in files.items():
        old = man["files"].get(rel, {})
        new = bp.sha256_file(src)
        if old.get("sha256") == new:
            continue
        bp.stage(man, rel, str(src), generator=generator, generator_version=version,
                 source_path=str(src).replace(os.sep, "/"), approved=True, approval=approval)
        rels.append(rel)
    if not rels:
        print("уже стоит")
        return 0
    bp.save(man, why=why)
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for root in bp.TARGETS.values():
        for rel in rels:
            with open(os.path.join(root, rel), "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != man["files"][rel]["sha256"]:
                    raise SystemExit("РАСХОДИТСЯ %s %s" % (root, rel))
    print("сверено: обе копии, файлов %d" % len(rels))
    return len(rels)
