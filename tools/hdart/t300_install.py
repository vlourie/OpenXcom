#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000300 (выбор Vitali 26.10: R1, зерно 4301 - куст MOUNTGRASS:15 «под эталон»): подключение семьи из 8 кадров.

  MOUNTGRASS:15 - R1 (art/tickets/t300r/gen/4301.png);
  FOREST:17, FORESTRED:17, MOUNTROCK:16 - копии, если классика побайтно равна MOUNTGRASS:15 (иначе перенос цвета);
  ABUNKER:7, BLACKFOREST:17, FOREST_WASTE:17, MOUNTMUD:14 - перенос цвета классики (obj_derive.transfer, R-030).
Механика - как tools/hdart/t322_333_install.py (put/derive/sheet/install_files, манифест, обе копии мода hd).

    py -3.13 tools\hdart\t300_install.py          # сухой прогон: кадры в art/_review/tickets_2026-10-26/after, лист sheet_t300.png
    py -3.13 tools\hdart\t300_install.py --yes    # в мод hd (под очередью правок, по слову Vitali)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import t322_333_install as ti                       # noqa: E402

ROOT = ti.ROOT
BASE = ("MOUNTGRASS", 15)
SRC = os.path.join(ROOT, "art", "tickets", "t300r", "gen", "4301.png")
MEMBERS = [("FOREST", 17), ("FORESTRED", 17), ("MOUNTROCK", 16),
           ("ABUNKER", 7), ("BLACKFOREST", 17), ("FOREST_WASTE", 17), ("MOUNTMUD", 14)]


def build():
    files, log = {}, []
    ti.put(files, ti.tpath(*BASE), SRC)
    for m in MEMBERS:
        ti.derive(files, BASE, m, hd_path=files[ti.tpath(*BASE)], how_log=log)
    return files, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files, log = build()
    print("файлов:", len(files))
    for b, m, how in log:
        print("   %s:%d -> %s:%d  %s" % (b[0], b[1], m[0], m[1], how))
    ti.sheet("t300", files)
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (по слову Vitali, под очередью правок)")
    import ticket_scene as ts
    n = ts.install_files(files, "t300_install", "t300_install.py 26.10", "Vitali: выбор R1 (зерно 4301) 26.10",
                         "t300: куст MOUNTGRASS 15 под эталон и семья из 8 кадров")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
