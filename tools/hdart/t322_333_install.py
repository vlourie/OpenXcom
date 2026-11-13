#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты 322-333 (выбор Vitali 26.10, decisions-2026-10-26.md): подключение арта в мод hd через манифест.

Что ставится (группы, ключ --only):
  t322   FLOOROB 1405 - яйцо набок (проба xp322, вариант A); в паке FLOOROB только pack.hdp, кадр кладётся
         отдельным файлом рядом (loadPack читает <индекс>.png после pack.hdp и он перекрывает кадр);
  t330   VILFRNITURE 85-100 <- одобренные FOREST 42-57 (копии классики побайтно); перекраски переносом цвета
         классики (R-030, obj_derive.transfer): FORESTRED 24-26 и 42-57, BLACKFOREST 15 кадров, FOREST_SNOW 45,
         FOREST 24-26 (старые копии 53-55);
  t305b  куст MOUNTMUD 20 (листва FOREST 19 в цветах классики 20, xp305/cand A);
  t327   URBANWAR 8, URBAN_GOODS 8 (xp327/cand);
  t323   MOUNTSAND 25, DESERTBITS 6, DESERTROCKS_RED 6, FORESTBITS_SNOW 6 и 7 (xp323/cand; без LAM_BASE 8,
         MOUNTSNOW2 25 - одобрены, без MOUNTMOON 25);
  t308   CUNTTRYROAD 13-16, 18 и CUNTTRYROAD_LT 13-16, 18 (xp308/cand);
  t324   клипы попаданий в землю --ground-v2: hit_cal1-5 и hit_pellet x grass/dirt/sand/stone/snow/wood/soft,
         42 клипа по 10 кадров (xp324/cand/FX, побайтно равны выводу gen_combat_fx.py --ground-v2);
  t304   MOUNTMUD 1 и 2 (xp304/gen, вариант b); t305g - MOUNTMUD 7 и 9 (xp305/gen, вариант b);
  t332   VILFRNITURE 71 и VILBAN 81 (xp332/gen, вариант f) + 10 членов семьи переносом цвета классики;
  t333   WESTFLOOR 7 и MEDIEVAL 1 (xp333/gen, вариант b), GRAVES_RED 12 - перенос цвета классики;
  t331   VILBAN 21 и 22 (xp331/gen, вариант d).

    py -3.13 tools\hdart\t322_333_install.py                # сухой прогон: сборка кадров в art/_review/tickets_2026-10-26/after и листы
    py -3.13 tools\hdart\t322_333_install.py --yes          # в мод hd (манифест, обе копии; под очередью правок, по слову Vitali)
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)
import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw                    # noqa: E402
import build_hd_pack as bp                          # noqa: E402

R = os.path.join(ROOT, "art", "_review")
OUT = os.path.join(R, "tickets_2026-10-26")
STAGE = os.path.join(OUT, "after")
_world = None


def world():
    global _world
    if _world is None:
        import map_mockup as mm
        _world = mm.World()
    return _world


def classic(s, f):
    im = world().sprite(s.lower(), f, None)
    if im is None:
        raise SystemExit("нет классики %s:%d" % (s, f))
    return im


def tpath(s, f):
    return "TERRAIN/%s.PCK/%d.png" % (s, f)


def game_png(rel):
    return os.path.join(bp.TARGETS["game"], rel)


def put(files, rel, img_or_path):
    """Положить готовый кадр в STAGE/rel; сверить размер с тем, что стоит."""
    dst = os.path.join(STAGE, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if isinstance(img_or_path, str):
        shutil.copyfile(img_or_path, dst)
    else:
        img_or_path.save(dst, optimize=True)
    cur = game_png(rel)
    if os.path.exists(cur):
        a, b = Image.open(dst).size, Image.open(cur).size
        if a != b:
            raise SystemExit("размер не совпадает %s: новый %s, стоит %s" % (rel, a, b))
    files[rel] = dst


def iou(a, b):
    ma = np.asarray(a.convert("RGBA"))[..., 3] > 0
    mb = np.asarray(b.convert("RGBA"))[..., 3] > 0
    return (ma & mb).sum() / max(1, (ma | mb).sum())


def same_pixels(a, b):
    return np.array_equal(np.asarray(a.convert("RGBA")), np.asarray(b.convert("RGBA")))


def derive(files, base, member, hd_path=None, how_log=None):
    """Член семьи из HD основы: побайтная копия, если классика та же, иначе перенос цвета классики."""
    import obj_derive as od
    bs, bf = base
    ms, mf = member
    hd = Image.open(hd_path or game_png(tpath(bs, bf))).convert("RGBA")
    cb, cm = classic(bs, bf), classic(ms, mf)
    if same_pixels(cb, cm):
        put(files, tpath(ms, mf), hd_path or game_png(tpath(bs, bf)))
        how = "копия"
    else:
        put(files, tpath(ms, mf), od.transfer(hd, cb, cm))
        how = "перенос цвета (IoU %.2f)" % iou(cb, cm)
    if how_log is not None:
        how_log.append((base, member, how))
    return how


# ---------------------------------------------------------------- группы
def g_t322():
    f = {}
    put(f, "FLOOROB.PCK/1405.png", os.path.join(R, "xp322", "probe_1405_lying_egg.png"))
    return f, "t322: яйцо набок (FLOOROB 1405)"


def g_t330():
    f, log = {}, []
    for k in range(42, 58):                                   # копии на VILFRNITURE
        derive(f, ("FOREST", k), ("VILFRNITURE", k + 43), how_log=log)
    for k in range(42, 58):                                   # красный лес
        derive(f, ("FOREST", k), ("FORESTRED", k), how_log=log)
    for k, b in ((24, 53), (25, 54), (26, 55)):               # старые копии 24-26 и их перекраски
        derive(f, ("FOREST", b), ("FORESTRED", k), how_log=log)
        derive(f, ("FOREST", b), ("BLACKFOREST", k), how_log=log)
        derive(f, ("FOREST", b), ("FOREST", k), how_log=log)
    for k in (42, 43, 44, 45, 46, 47, 49, 52, 53, 54, 55, 56):  # чёрный лес
        derive(f, ("FOREST", k), ("BLACKFOREST", k), how_log=log)
    derive(f, ("FOREST", 45), ("FOREST_SNOW", 45), how_log=log)
    g_t330.log = log
    return f, "t330: VILFRNITURE 85-100 <- FOREST 42-57 и перекраски FORESTRED/BLACKFOREST/FOREST_SNOW/FOREST 24-26"


def cand_group(sub, names_skip=(), only=None):
    f = {}
    d = os.path.join(R, sub, "cand")
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".png"):
            continue
        b = fn[:-4]
        if b in names_skip or (only and b not in only):
            continue
        s, fr = b.rsplit("_", 1)
        put(f, tpath(s, int(fr)), os.path.join(d, fn))
    return f


def g_t305b():
    f = {}
    put(f, tpath("MOUNTMUD", 20), os.path.join(R, "xp305", "cand", "MOUNTMUD_20_A_leaf_rank.png"))
    return f, "t305: куст MOUNTMUD 20 жёлтой листвой"


def g_t327():
    return cand_group("xp327"), "t327: URBANWAR 8, URBAN_GOODS 8"


def g_t323():
    return (cand_group("xp323", names_skip=("LAM_BASE_8", "MOUNTSNOW2_25", "MOUNTMOON_25")),
            "t323: двойной камень MOUNTSAND 25 и перекраски")


def g_t308():
    return cand_group("xp308"), "t308: колея CUNTTRYROAD 13-16, 18 и CUNTTRYROAD_LT"


def g_t324():
    f = {}
    root = os.path.join(R, "xp324", "cand", "FX")
    for d in sorted(os.listdir(root)):
        p = os.path.join(root, d)
        if not os.path.isdir(p):
            continue
        for fn in sorted(os.listdir(p)):
            put(f, "FX/%s/%s" % (d, fn), os.path.join(p, fn))
    return f, "t324: клипы попаданий в землю v2 (42 клипа)"


def gen_group(spec):
    f = {}
    for sub, name, fr, var in spec:
        put(f, tpath(name, fr), os.path.join(R, sub, "gen", "%s_%d_%s.png" % (name, fr, var)))
    return f


def g_t304():
    return gen_group([("xp304", "MOUNTMUD", 1, "b"), ("xp304", "MOUNTMUD", 2, "b")]), "t304: трава MOUNTMUD 1 и 2"


def g_t305g():
    return gen_group([("xp305", "MOUNTMUD", 7, "b"), ("xp305", "MOUNTMUD", 9, "b")]), "t305: трава MOUNTMUD 7 и 9"


def g_t332():
    f = gen_group([("xp332", "VILFRNITURE", 71, "f"), ("xp332", "VILBAN", 81, "f")])
    log = []
    members = [("CULTAREA", 87), ("CULTDECOR", 53), ("DAWNURBAN", 85), ("DUSKURBAN", 85), ("MADDECOR", 52),
               ("MILURBAN", 87), ("ROADSGREEN", 21), ("SEAMADDECOR", 52), ("URBAN", 85), ("URBAN_GOODS", 85)]
    bases = [("VILFRNITURE", 71), ("VILBAN", 81)]
    for m in members:
        cm = classic(*m)
        best = max(bases, key=lambda b: iou(classic(*b), cm))
        derive(f, best, m, hd_path=f[tpath(*best)], how_log=log)
    g_t332.log = log
    return f, "t332: бензоколонка VILFRNITURE 71, VILBAN 81 и 10 членов семьи"


def g_t333():
    f = gen_group([("xp333", "WESTFLOOR", 7, "b"), ("xp333", "MEDIEVAL", 1, "b")])
    log = []
    derive(f, ("WESTFLOOR", 7), ("GRAVES_RED", 12), hd_path=f[tpath("WESTFLOOR", 7)], how_log=log)
    g_t333.log = log
    return f, "t333: колодец WESTFLOOR 7, MEDIEVAL 1, GRAVES_RED 12"


def g_t331():
    return gen_group([("xp331", "VILBAN", 21, "d"), ("xp331", "VILBAN", 22, "d")]), "t331: лестница VILBAN 21+22"


GROUPS = {"t322": g_t322, "t330": g_t330, "t305b": g_t305b, "t327": g_t327, "t323": g_t323, "t308": g_t308,
          "t324": g_t324, "t304": g_t304, "t305g": g_t305g, "t332": g_t332, "t333": g_t333, "t331": g_t331}


def sheet(name, files, only_frames=None, cell=160):
    """Лист: на каждый кадр - классика (x4 ближайшим), было, стало, на сером."""
    rows = []
    for rel, new in files.items():
        if not rel.startswith("TERRAIN/"):
            continue
        s = rel.split("/")[1][:-4]
        fr = int(os.path.basename(rel)[:-4])
        old = game_png(rel)
        ims = [classic(s, fr).resize((128, 160), Image.NEAREST),
               Image.open(old).convert("RGBA") if os.path.exists(old) else Image.new("RGBA", (128, 160)),
               Image.open(new).convert("RGBA")]
        rows.append(("%s:%d" % (s, fr), ims))
    if not rows:
        return
    cols = 4
    nrow = (len(rows) + cols - 1) // cols
    W, H = 140 * 3, 178
    sh = Image.new("RGB", (cols * W, nrow * H), (96, 96, 100))
    d = ImageDraw.Draw(sh)
    for i, (lab, ims) in enumerate(rows):
        x0, y0 = (i % cols) * W, (i // cols) * H
        d.text((x0 + 4, y0 + 2), lab + "  классика | было | стало", fill=(255, 220, 80))
        for j, im in enumerate(ims):
            sh.paste(im, (x0 + j * 140 + 6, y0 + 16), im)
    p = os.path.join(OUT, "sheet_%s.png" % name)
    sh.save(p)
    print("лист:", p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    want = [g for g in a.only.split(",") if g] or list(GROUPS)
    built = {}
    for g in want:
        files, why = GROUPS[g]()
        built[g] = (files, why)
        print("%-6s %4d файлов  %s" % (g, len(files), why))
        for lg in (getattr(GROUPS[g], "log", None) or []):
            print("      %s:%d -> %s:%d  %s" % (lg[0][0], lg[0][1], lg[1][0], lg[1][1], lg[2]))
        sheet(g, files)
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (по слову Vitali, под очередью правок)")
    import ticket_scene as ts
    total = 0
    for g, (files, why) in built.items():
        total += ts.install_files(files, "t322_333_install", "t322_333_install.py 26.10, группа " + g,
                                  "Vitali: страница выбора 26.10 (decisions-2026-10-26.md)", why)
    print("установлено файлов: %d" % total)


if __name__ == "__main__":
    main()
