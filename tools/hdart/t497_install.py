#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка XP-000497 (песок у упавшего самолёта; Vitali 05.11: «2, песок 1»).

Воронка, вариант 2: DESERTPLANE:18, POLARPLANE:18. Ровный песок, вариант 1: DESERTPLANE:21, POLARPLANE:21, SANDS:21.
Кадры строит t497_build.py. Прочие члены семьи (ticket_family.py, R-457) чистые и не меняются.
Прежние кадры - art/_backup/tickets_2026-11-05/<путь пака>.

    py -3.13 tools\hdart\t497_install.py         сухой прогон
    py -3.13 tools\hdart\t497_install.py --yes   установить (под очередью правок)
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

BACKUP = os.path.join(ROOT, "art", "_backup", "tickets_2026-11-05")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
CAND = os.path.join(ROOT, "art", "tickets", "t497", "cand")
JOBS = (("2", "DESERTPLANE", 18), ("2", "POLARPLANE", 18), ("1", "DESERTPLANE", 21), ("1", "POLARPLANE", 21), ("1", "SANDS", 21))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    files = {"TERRAIN/%s.PCK/%d.png" % (s, f): os.path.join(CAND, v, s, "%d.png" % f) for v, s, f in JOBS}
    for rel, p in files.items():
        with Image.open(p) as im:
            if im.mode != "RGBA" or im.size != (128, 160):
                raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
    print("файлов к установке: %d" % len(files))
    if "--yes" not in sys.argv:
        raise SystemExit("сухой прогон; --yes - записать в мод (под очередью правок)")
    for rel in files:
        src = os.path.join(REPO_PACK, rel)
        dst = os.path.join(BACKUP, rel)
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
    print("резерв:", BACKUP)
    import ticket_scene as ts
    n = ts.install_files(files, "t497_install",
                         "XP-000497: воронка - SANDS:18, перекрашенная по классике; ровный песок - кадр :20 своего набора",
                         "Vitali 05.11 в чате: «2, песок 1»",
                         "t497: воронка и ровный песок DESERTPLANE, POLARPLANE, SANDS")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
