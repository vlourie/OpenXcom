#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка XP-000492 (снежная деревня): земля IDT_SNOWBARN:0 и вся её семья (Vitali 04.11: вариант 1, стиль S2).

Семья (ticket_family.py, R-457): IDT_SNOWBARN:0, FORESTSWAMP_SNOW 4, 22, 111-122, 137-139, FOREST_SNOW:0,
ICEKING_VILLAGE:61 - 20 кадров, у каждого основа и варианты .v1-.v3 (R-039), 80 файлов. Кадры строит t492_build.py final
по индексам классики КАЖДОГО члена (классика побайтно та же, у ICEKING_VILLAGE:61 отличается 1 пиксель).
Кадры B (белый снег :0, плитки :4, грядка :1 набора IDT_SNOWCULTIVAT) - только по слову Vitali: --b1 или --b2.
Прежние кадры - art/_backup/tickets_2026-11-04/<путь пака>.

    py -3.13 tools\hdart\t492_install.py                 сухой прогон (земля)
    py -3.13 tools\hdart\t492_install.py --yes           установить землю (под очередью правок)
    py -3.13 tools\hdart\t492_install.py --b1 [--yes]    кадры B, вариант B1 (чистая классика)
    py -3.13 tools\hdart\t492_install.py --b2 [--yes]    кадры B, вариант B2 (круглое зерно)
    py -3.13 tools\hdart\t492_install.py --plant [--yes] перерисовка IDT_SNOWCULTIVAT 1, 4, 6, 7, вариант 2 (Vitali 04.11: «все 2»)
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

import numpy as np                           # noqa: E402
from PIL import Image                        # noqa: E402

import t492_build as tb                      # noqa: E402
import water_build as wb                     # noqa: E402

BACKUP = os.path.join(ROOT, "art", "_backup", "tickets_2026-11-04")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
PLANT = (1, 4, 6, 7)     # 6 - куст, 7 - кочан: нарисованы заново, средний цвет сверять только у земли 1 и 4


def collect(style):
    files = {}
    if style == "plant":
        for f in PLANT:
            files["TERRAIN/IDT_SNOWCULTIVAT.PCK/%d.png" % f] = os.path.join(
                ROOT, "art", "tickets", "t492", "plant", "v2", "IDT_SNOWCULTIVAT_%d.png" % f)
    elif style is None:
        for s, f in tb.FAMILY:
            for v in range(4):
                n = tb.name_of(f, v)
                files["TERRAIN/%s.PCK/%s" % (s, n)] = str(tb.FINAL / s / n)
    else:
        s = "IDT_SNOWCULTIVAT"
        for f, nv in ((0, 3), (4, 0), (1, 0)):
            for v in range(nv + 1):
                n = tb.name_of(f, v)
                files["TERRAIN/%s.PCK/%s" % (s, n)] = str(tb.CAND_B / style / s / n)
    return files


def check(files):
    """RGBA 128x160; цвет не чужой: средний цвет внутри ромба против классики члена (палитра Пираток) - не больше 6 из 255."""
    pal = wb.palette()
    for rel, p in files.items():
        with Image.open(p) as im:
            if im.mode != "RGBA" or im.size != (128, 160):
                raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
            a = np.asarray(im).astype(float)
        sname, name = rel.split("/")[1][:-4], rel.split("/")[2]
        f = int(name.split(".")[0])
        if sname == "IDT_SNOWCULTIVAT" and f in (6, 7):
            continue
        P = wb.read_set(sname)[f]
        m = P > 0
        cl = pal[P[m]][:, :3].mean(0)
        mm = np.kron(m, np.ones((4, 4), bool)) & (a[..., 3] > 250)
        nw = a[..., :3][mm].mean(0)
        d = np.abs(cl - nw).max()
        if ".v" not in name and d > 6:
            raise SystemExit("%s: средний цвет отличается от классики на %.1f" % (rel, d))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    yes = "--yes" in sys.argv
    style = "B1" if "--b1" in sys.argv else "B2" if "--b2" in sys.argv else "plant" if "--plant" in sys.argv else None
    files = collect(style)
    check(files)
    print("файлов к установке: %d (%s)" % (len(files), style or "земля, семья S2"))
    if not yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (под очередью правок)")
    for rel in files:
        src = os.path.join(REPO_PACK, rel)
        dst = os.path.join(BACKUP, rel)
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
    print("резерв:", BACKUP)
    import ticket_scene as ts
    if style == "plant":
        n = ts.install_files(files, "t492_plant",
                             "XP-000492: IDT_SNOWCULTIVAT 1, 4 земля крупой, 6 куст, 7 кочан капусты, вариант 2",
                             "Vitali 04.11 в чате: «все 2»",
                             "t492: растения и земля IDT_SNOWCULTIVAT, вариант 2")
    elif style is None:
        n = ts.install_files(files, "t492_install",
                             "XP-000492: земля S2, семья IDT_SNOWBARN:0 (20 кадров с вариантами v1-v3)",
                             "Vitali 04.11 в чате: вариант 1 (земля S2)",
                             "t492: земля IDT_SNOWBARN:0 и семья FORESTSWAMP_SNOW, FOREST_SNOW:0, ICEKING_VILLAGE:61")
    else:
        n = ts.install_files(files, "t492_install",
                             "XP-000492: IDT_SNOWCULTIVAT 0/4/1, " + style,
                             "Vitali: кадры B, " + style,
                             "t492: белый снег, плитки, грядка IDT_SNOWCULTIVAT, " + style)
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
