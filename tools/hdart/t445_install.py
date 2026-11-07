#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка кандидата тикета XP-000445 (Vitali 30.10 23:04: «Ставить MOUNTGRASS», FOREST и BLACKFOREST не трогать).

  Склоны MOUNTGRASS 27-39, 41 из мозаики своего HD-пола MOUNTGRASS (art/tickets/t445/cand/A1, t445_slopes.py), 14 кадров.

Через манифест (build_hd_pack: stage + save + install в game и repo + сверка хэшей), резерв прежних файлов -
art/_backup/t445_20261030/<путь пака>.

    py -3.13 tools\hdart\t445_install.py            сухой прогон
    py -3.13 tools\hdart\t445_install.py --yes      установить (под очередью правок)
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

from PIL import Image                        # noqa: E402

BACKUP = os.path.join(ROOT, "art", "_backup", "t445_20261030")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
CAND = os.path.join(ROOT, "art", "tickets", "t445", "cand", "A1")
FRAMES = list(range(27, 40)) + [41]


def collect():
    return {"TERRAIN/MOUNTGRASS.PCK/%d.png" % f: os.path.join(CAND, "MOUNTGRASS_%d.png" % f) for f in FRAMES}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    yes = "--yes" in sys.argv
    files = collect()
    for rel, p in files.items():
        # with: незакрытый кадр пака держит файл, и os.replace при установке падает (R-567)
        with Image.open(p) as im, Image.open(os.path.join(REPO_PACK, rel)) as old:
            if im.mode != "RGBA" or im.size != old.size:
                raise SystemExit("%s: ждали RGBA %s, а %s %s" % (p, old.size, im.mode, im.size))
    print("файлов к установке: %d" % len(files))
    if not yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (под очередью правок)")
    for rel in files:
        src = os.path.join(REPO_PACK, rel)
        dst = os.path.join(BACKUP, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            shutil.copyfile(src, dst)
    print("резерв:", BACKUP)
    import ticket_scene as ts
    n = ts.install_files(files, "t445_install", "XP-000445: склоны MOUNTGRASS из своей травы (t445_slopes A1)",
                         "Vitali: страница выбора, Ставить MOUNTGRASS, 30.10 23:04",
                         "t445 склоны MOUNTGRASS 27-39, 41 из своей травы")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
