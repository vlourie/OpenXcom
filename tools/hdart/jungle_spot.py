#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000510: пятно JUNGLEROCKS:12 и :13 (пол) - трава HD JUNGLEBITS:0 плюс камушки по маске классики, без видеокарты.

Классика: ромб травы с тёмными камушками. HD сейчас: дыры и чёрная обводка (12), у 13 HD нет вовсе.
Новое: целый ромб травы (кадр JUNGLEBITS:0 из пака, его ровная кромка), камни - индексы классики вне зелёной рампы
68..79 мягким x4 по плотности, зернистые, со светом сверху слева; под камнями тень травы (тёмные зелёные
индексы классики 74..79 и мягкая подложка вокруг камня).

    py -3.13 jungle_spot.py           # заготовки в art/tickets/jungle_spot (12.png, 13.png)
    py -3.13 jungle_spot.py --sheet   # лист census/tickets/XP-000510/sheet_spot_new.png
    py -3.13 jungle_spot.py --yes     # в обе копии мода через манифест (только по слову Vitali, под очередью правок)
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hb_common as hc                  # noqa: E402,F401
import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import build_hd_pack as bp              # noqa: E402
import water_build as wb                # noqa: E402

K = 4
OUT = os.path.join("art", "tickets", "jungle_spot")
SHEET = os.path.join("census", "tickets", "XP-000510", "sheet_spot_new.png")
FRAMES = (12, 13)
WORD = "XP-000510, пятно JUNGLEROCKS 12, 13: трава JUNGLEBITS 0 + камни по маске классики (Vitali, вариант по листу)"
GRASS = np.zeros(256, bool)
GRASS[68:80] = True
P = dict(blur=1.1, edge0=0.47, edgew=0.10, tex1=0.26, tex2=0.20, halo=0.34, lit=0.5)


def load(*p):
    return np.asarray(Image.open(os.path.join(*p)).convert("RGBA")).astype(np.float32)


def lum(c):
    return c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114


def noise(shape, rng, sg):
    n = wb.gauss(rng.standard_normal(shape).astype(np.float32), sg)
    return n / max(float(n.std()), 1e-6)


def build(f, frames, pal, grass):
    a = np.asarray(frames[f])
    nz = a != 0
    stone = nz & ~GRASS[a]
    rgb = pal[a][..., :3].astype(np.float32)
    ch = np.dstack([rgb * stone[..., None], stone.astype(np.float32)])
    u = wb.up_float(np.pad(ch, ((2, 2), (2, 2), (0, 0))), P["blur"])[2 * K:-2 * K, 2 * K:-2 * K]
    d = np.clip(u[..., 3], 0, 1)
    icol = u[..., :3] / np.maximum(d[..., None], 1e-3)
    ref = float(lum(pal[72][:3].astype(np.float32)))
    sh = np.where(nz & GRASS[a] & (a >= 74), np.clip(lum(rgb) / ref, 0.0, 1.0), 1.0).astype(np.float32)
    shu = np.clip(wb.up_float(np.pad(sh[..., None], ((2, 2), (2, 2), (0, 0)), mode="edge"), 1.5)[2 * K:-2 * K, 2 * K:-2 * K, 0], 0, 1)
    halo = np.clip(wb.gauss(d, 5.0) * 1.6, 0, 1)
    under = 1.0 - P["halo"] * halo
    w = np.clip((d - P["edge0"]) / P["edgew"], 0, 1)
    rng = np.random.default_rng(1200 + f)
    tex = 1.0 + P["tex1"] * noise(d.shape, rng, 0.8) + P["tex2"] * noise(d.shape, rng, 2.5)
    ds = wb.gauss(d, 2.2)
    gy, gx = np.gradient(ds)
    lit = np.clip(-(gx + gy) * 6.0, -1, 1) * np.clip(ds * 3, 0, 1) * (1 - np.clip(ds - 0.7, 0, 1) * 2)
    stc = icol * tex[..., None] * (1.0 + P["lit"] * lit[..., None])
    stc = stc + 9.0 * np.clip(lit, 0, 1)[..., None]
    col = grass[..., :3] * (shu * under)[..., None] * (1 - w[..., None]) + stc * w[..., None]
    return np.dstack([np.clip(col, 0, 255), grass[..., 3]]).round().astype(np.uint8)


def make():
    os.makedirs(OUT, exist_ok=True)
    pal = np.asarray(wb.palette())
    frames = wb.read_set("JUNGLEROCKS")
    grass = load(hc.TERRAIN, "JUNGLEBITS.PCK", "0.png")
    paths = {}
    for f in FRAMES:
        im = build(f, frames, pal, grass)
        p = os.path.join(OUT, "%d.png" % f)
        Image.fromarray(im, "RGBA").save(p)
        paths[f] = p
    return paths


def sheet(paths):
    import ticket_scene as ts
    sc = ts.Scene()
    rows = []
    for f in FRAMES:
        cls = sc.classic("JUNGLEROCKS", f).crop((0, 76, 128, 160)).resize((384, 252), Image.NEAREST)
        cur = sc.hd("JUNGLEROCKS", f)
        cur = cur.crop((0, 76, 128, 160)).resize((384, 252), Image.LANCZOS) if cur is not None else Image.new("RGBA", (384, 252), (0, 0, 0, 0))
        new = Image.open(paths[f]).convert("RGBA").crop((0, 76, 128, 160)).resize((384, 252), Image.LANCZOS)
        panels = [hc.title_bar(hc.on_bg(cls), "классика JUNGLEROCKS:%d" % f, 22),
                  hc.title_bar(hc.on_bg(cur), "сейчас" if f == 12 else "сейчас: HD нет (классика)", 22),
                  hc.title_bar(hc.on_bg(new), "новое: трава + камни по классике", 22)]
        rows.append(hc.hstack(panels))
    ov = {("JUNGLEROCKS", f): Image.open(paths[f]).convert("RGBA") for f in FRAMES}
    scenes = []
    for f in FRAMES:
        keys = [("JUNGLEROCKS", f)]
        tb = hc.best_blocks(sc, keys, "JUNGLETEMPLE")
        (t, b), n = tb[0]
        pans, nf = hc.scene_panels(sc, t, b, keys, ov, size=(150, 90), which=0)
        scenes.append(hc.hstack([hc.title_bar(im, tt + "  JUNGLEROCKS:%d, блок %s" % (f, b), 22) for tt, im in pans]))
    out = hc.vstack(rows + scenes)
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    out.save(SHEET)
    print("лист:", SHEET, out.size)


def install(paths):
    man = bp.load()
    rels = []
    for f, path in paths.items():
        rel = "TERRAIN/JUNGLEROCKS.PCK/%d.png" % f
        bp.stage(man, rel, path, generator="jungle_spot", generator_version="jungle_spot 05.11: трава JUNGLEBITS:0 + камни по маске классики",
                 source_path=path.replace(os.sep, "/"), approved=True, approval=WORD)
        rels.append(rel)
    bp.save(man, why="JUNGLEROCKS 12, 13: пятно по маске классики (%s)" % WORD)
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for root in bp.TARGETS.values():
        for rel in rels:
            with open(os.path.join(root, rel), "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != man["files"][rel]["sha256"]:
                    raise SystemExit("РАСХОДИТСЯ %s %s" % (root, rel))
    print("сверено: обе копии, файлов", len(rels))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    paths = make()
    print("заготовки:", OUT)
    if "--sheet" in sys.argv:
        sheet(paths)
    if "--yes" in sys.argv:
        install(paths)
