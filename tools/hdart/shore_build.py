#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000511: берега болота FORESTSWAMP (и копии в FORESTSWAMPSTYX, LAVA_SWAMP, LAVA_SWAMPGREEN): трава по кромке воды без
ярких лезвий, цвет и маска классики, мягкая подложка, пушистая ровная кромка. Без видеокарты.

Что не так сейчас: суша брала фактуру тёмного пола-соседа, умноженную на яркость классики (water_build build_shore, land=...)
- вышли острые неоновые лезвия (55,158,29 против 94,158,57 классики), по кромке воды без подложки.
Новое, на каждый кадр берега: (1) суша - индексы 64..79 классики, цвет суши продолжен за кромку ближайшим пикселем суши
(нет тёмной каймы), мягкое x4; (2) граница суши и воды - сглаженная плотность суши, порог 0.5 с мелким шумом по кромке
(пух, но без зубцов, шум один на рисунок - 4 фазы воды совпадают); (3) подложка - сушу у воды темнее (тень под травой),
воду у суши темнее; (4) вода кадра - как в water_build (polar_water, тот же средний цвет); (5) альфа ромба - установленного
кадра (ровная кромка floor_edge 05.11 цела), цвет за кромкой не важен.
Заготовки: art/tickets/shore_swamp/<НАБОР>/<кадр>.png. Вся семья - одной командой.

    py -3.13 shore_build.py probe             # проба: FORESTSWAMP 54, 58, 60 (+ ещё рисунки), лист census/tickets/XP-000511/sheet_probe.png
    py -3.13 shore_build.py all [НАБОР...]    # вся семья в заготовки (по умолчанию все 4 набора)
    py -3.13 shore_build.py install [НАБОР..] --yes   # в обе копии мода через манифест; только по слову Vitali, под очередью правок
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hb_common as hc                  # noqa: E402
import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402
from scipy import ndimage               # noqa: E402

import build_hd_pack as bp              # noqa: E402
import water_build as wb                # noqa: E402

K = 4
OUT = os.path.join("art", "tickets", "shore_swamp")
SHEET = os.path.join("census", "tickets", "XP-000511", "sheet_probe.png")
SETS = ("FORESTSWAMP", "FORESTSWAMPSTYX", "LAVA_SWAMP", "LAVA_SWAMPGREEN")
OPEN = (56, 71, 86, 101)         # открытая вода (запись 68 раскладки), номера кадров FORESTSWAMP; у LAVA - на 44 меньше
WORD = "XP-000511, берег FORESTSWAMP: трава по маске и цвету классики, мягкая подложка (Vitali, вариант по листу)"
LAND = np.zeros(256, bool)
LAND[64:80] = True
P = dict(sh_blur=2.2, fuzz=0.10, edge_w=0.10, under=0.30, under_d=5.0, wunder=0.22, wunder_d=6.0, tex=0.08, col_blur=1.3)


def lum(c):
    return c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114


def aniso(shape, rng, sy, sx):
    n = ndimage.gaussian_filter(rng.standard_normal(shape).astype(np.float32), (sy, sx))
    return n / max(float(n.std()), 1e-6)


def frames_of(s):
    recs, _ = wb.records(s)
    anim = sorted({f for r in recs if len(set(r)) > 1 for f in r})
    assert len(anim) == 60, (s, len(anim))
    return anim


def water_mean(frames, pal, anim):
    """Средний цвет открытой воды набора: кадры записи 68 (4 фазы), всё, что не суша."""
    base = anim[0] + 5
    cols = []
    for k in range(4):
        a = frames[base + 15 * k]
        m = (a != 0) & ~LAND[a]
        cols.append(pal[a[m]].astype(np.float32))
    return np.concatenate(cols).mean(0)


def cur_alpha(s, f):
    p = os.path.join(hc.TERRAIN, s + ".PCK", "%d.png" % f)
    if not os.path.exists(p):
        return None
    return np.asarray(Image.open(p).convert("RGBA"))[..., 3]


def build(s, f, frames, pal, mean, pic):
    a = np.asarray(frames[f])
    nz = a != 0
    land = nz & LAND[a]
    if not land.any():
        return None
    # цвет воды: как water_build (кадр сам с собой на изорешётке)
    water = nz & ~land
    wat = wb.polar_water(a, pal, mean, 1.6, ~LAND)
    # классы: ближайший пиксель классики вне силуэта
    _, ind = ndimage.distance_transform_edt(~nz, return_indices=True)
    lab = land[ind[0], ind[1]].astype(np.float32)
    # цвет суши: ближайший пиксель суши
    _, il = ndimage.distance_transform_edt(~land, return_indices=True)
    lcol = pal[a][..., :3].astype(np.float32)[il[0], il[1]]
    up = lambda x, b: wb.up_float(np.pad(x, ((2, 2), (2, 2), (0, 0)), mode="edge"), b)[2 * K:-2 * K, 2 * K:-2 * K]   # noqa: E731
    L0 = np.clip(up(lab[..., None], P["sh_blur"])[..., 0], 0, 1)
    icol = up(lcol, P["col_blur"])
    rng = np.random.default_rng(5100 + pic)
    Lf = L0 + P["fuzz"] * aniso(L0.shape, rng, 1.2, 0.8) * (1 - np.abs(2 * L0 - 1))
    w = np.clip((Lf - 0.5) / P["edge_w"] + 0.5, 0, 1)
    # подложка: расстояние от кромки внутрь суши и внутрь воды
    inside = w > 0.5
    dl = ndimage.distance_transform_edt(inside)
    dw = ndimage.distance_transform_edt(~inside)
    under = 1.0 - P["under"] * np.exp(-dl / P["under_d"])
    wunder = 1.0 - P["wunder"] * np.exp(-dw / P["wunder_d"])
    tex = 1.0 + P["tex"] * aniso(L0.shape, rng, 1.4, 0.8)
    landc = icol * (under * tex)[..., None]
    watc = wat * wunder[..., None]
    col = watc * (1 - w[..., None]) + landc * w[..., None]
    alpha = cur_alpha(s, f)
    if alpha is None:
        return None
    return np.dstack([np.clip(col, 0, 255), alpha]).round().astype(np.uint8)


def all_frames(s):
    return frames_of(s)


def run(sets, only=None, save=True):
    pal = np.asarray(wb.palette())
    res = {}
    for s in sets:
        frames = wb.read_set(s)
        anim = frames_of(s)
        mean = water_mean(frames, pal, anim)
        for f in anim:
            pic = (f - anim[0]) % 15
            if only and (s, f) not in only:
                continue
            im = build(s, f, frames, pal, mean, pic)
            if im is None:
                continue
            res[(s, f)] = im
            if save:
                p = os.path.join(OUT, s, "%d.png" % f)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                Image.fromarray(im, "RGBA").save(p)
    return res


def classic_img(s, f):
    pal = wb.palette()
    a = wb.read_set(s)[f]
    rgba = np.zeros((40, 32, 4), np.uint8)
    m = a > 0
    rgba[m, :3] = pal[a[m]][:, :3]
    rgba[m, 3] = 255
    return Image.fromarray(rgba, "RGBA").resize((128, 160), Image.NEAREST)


def probe():
    import ticket_scene as ts
    sc = ts.Scene()
    picks = [54, 58, 60, 63, 66]
    only = {("FORESTSWAMP", f) for f in picks}
    res = run(["FORESTSWAMP"], only)
    rows = []
    box = (0, 76, 128, 160)
    for f in picks:
        if ("FORESTSWAMP", f) not in res:
            continue
        cls = classic_img("FORESTSWAMP", f).crop(box).resize((384, 252), Image.NEAREST)
        cur = sc.hd("FORESTSWAMP", f).crop(box).resize((384, 252), Image.LANCZOS)
        new = Image.fromarray(res[("FORESTSWAMP", f)], "RGBA").crop(box).resize((384, 252), Image.LANCZOS)
        rows.append(hc.hstack([hc.title_bar(hc.on_bg(cls), "классика FORESTSWAMP:%d" % f, 20), hc.title_bar(hc.on_bg(cur), "сейчас", 20),
                               hc.title_bar(hc.on_bg(new), "новое", 20)]))
    ov = {k: Image.fromarray(v, "RGBA") for k, v in res.items()}
    # сцена настоящего блока с берегом: блок с наибольшим числом проб-кадров
    keys = list(ov.keys())
    tb = hc.best_blocks(sc, keys, "FORESTSWAMP", top=3)
    print("блоки:", tb)
    scenes = []
    for (t, b), n in tb[:2]:
        pans, nf = hc.scene_panels(sc, t, b, keys, ov, size=(190, 100), which=0)
        scenes.append(hc.hstack([hc.title_bar(im, tt + " (блок %s, k=4)" % b, 22) for tt, im in pans]))
    top = hc.vstack(rows[:3])
    top2 = hc.vstack(rows[3:]) if len(rows) > 3 else None
    out = hc.vstack([hc.hstack([top] + ([top2] if top2 else []))] + scenes)
    out.save(SHEET)
    print("лист:", SHEET, out.size)


def install(sets):
    man = bp.load()
    rels = []
    for s in sets:
        d = os.path.join(OUT, s)
        for fn in sorted(os.listdir(d)):
            f = int(fn[:-4])
            rel = "TERRAIN/%s.PCK/%d.png" % (s, f)
            old = man["files"].get(rel, {})
            bp.stage(man, rel, os.path.join(d, fn), generator="shore_build",
                     generator_version="shore_build 05.11: берег по маске и цвету классики; было: %s %s" % (old.get("generator"), old.get("generator_version") or ""),
                     source_path=os.path.join(d, fn).replace(os.sep, "/"), approved=True, approval=WORD)
            rels.append(rel)
    bp.save(man, why="берега FORESTSWAMP (%d файлов): %s" % (len(rels), WORD))
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
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    names = [a for a in sys.argv[2:] if not a.startswith("--")] or list(SETS)
    if cmd == "probe":
        probe()
    elif cmd == "all":
        r = run(names)
        print("кадров:", len(r), "в", OUT)
    elif cmd == "install":
        if "--yes" not in sys.argv:
            raise SystemExit("нужен --yes (только по слову Vitali, под очередью правок)")
        install(names)
