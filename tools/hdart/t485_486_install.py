#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка XP-000485 (Vitali 03.11, страница выбора: вариант Y; 04.11 в чате: ставить).

485: XBASEN_BEDS:5, :6 и копии XBASEN_BITS:40, :41 - альфа 255 внутри силуэта классики x4 (t485_486_alpha.py 485).
486 не ставится: Vitali 04.11 - вся лестница IDT_FARM перегенерацией одним стилем, отдельным выбором. Через манифест (stage + save + install в game и repo + сверка хэшей), резерв прежних -
art/_backup/tickets_2026-11-04/<путь пака>.

    py -3.13 tools\hdart\t485_486_install.py            сухой прогон
    py -3.13 tools\hdart\t485_486_install.py --yes      установить (под очередью правок)
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

BACKUP = os.path.join(ROOT, "art", "_backup", "tickets_2026-11-04")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
T485 = os.path.join(ROOT, "art", "tickets", "t485")
FRAMES = [("XBASEN_BEDS", 5, T485), ("XBASEN_BEDS", 6, T485), ("XBASEN_BITS", 40, T485), ("XBASEN_BITS", 41, T485)]


def collect():
    return {"TERRAIN/%s.PCK/%d.png" % (n, f): os.path.join(d, "%s_%d.png" % (n, f)) for n, f, d in FRAMES}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    yes = "--yes" in sys.argv
    files = collect()
    for rel, p in files.items():
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
    n = ts.install_files(files, "t485_486_install",
                         "XP-000485: шкафчики, альфа 255 внутри силуэта",
                         "Vitali: страница выбора 03.11 (485 Y), 04.11 в чате: ставить",
                         "t485: XBASEN_BEDS:5/6, XBASEN_BITS:40/41")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
