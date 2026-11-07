#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка XP-000390 (Vitali 04.11 в чате: «ведро - 1 ... колонка - 2»).

Колонка: вариант 2 t390_gen3 (cand3/alt, зерно 4313) - URBAN_WASTE:85, MADDECOR_WASTE:49, RUSTSHACKS2:51.
Ведро: вариант 1 t390_gen3 (cand3, зерно 4323) - URBITS_WASTE:23, CATACDECOR_CONC:23. Вся семья одним коммитом, R-457.
Прежние кадры - art/_backup/tickets_2026-11-04/<путь пака>.

    py -3.13 tools\hdart\t390_install.py            сухой прогон
    py -3.13 tools\hdart\t390_install.py --yes      установить (под очередью правок)
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
CAND = os.path.join(ROOT, "art", "tickets", "t390", "cand3")
PUMP = os.path.join(CAND, "alt")
FRAMES = [("URBAN_WASTE", 85, PUMP), ("MADDECOR_WASTE", 49, PUMP), ("RUSTSHACKS2", 51, PUMP),
          ("URBITS_WASTE", 23, CAND), ("CATACDECOR_CONC", 23, CAND)]


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
    n = ts.install_files(files, "t390_install",
                         "XP-000390: колонка pumpD 4313, ведро binG 4323",
                         "Vitali 04.11 в чате: ведро 1, колонка 2",
                         "t390: URBAN_WASTE:85, MADDECOR_WASTE:49, RUSTSHACKS2:51, URBITS_WASTE:23, CATACDECOR_CONC:23")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
