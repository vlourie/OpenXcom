#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка ровного края склонов (Vitali 31.10 00:29: «Ставить новый край склонов, выпускать»).

  MOUNTTROP, FORESTJUNGLESTYX (тикеты XP-000429/431) и MOUNTGRASS (XP-000445), кадры 27-39, 41 - 42 кадра:
  альфа по маске классики, спрямлённой xBRZ, у ромба - покрытие прямой (t_slope_edge.py, R-568), цвет прежний.
  art/tickets/t431/cand/A1e и art/tickets/t445/cand/A1e.

Через манифест (build_hd_pack: stage + save + install в game и repo + сверка хэшей), резерв нынешних (A1) -
art/_backup/t_slope_edge_20261031/<путь пака>.

    py -3.13 tools\hdart\t_slope_edge_install.py            сухой прогон
    py -3.13 tools\hdart\t_slope_edge_install.py --yes      установить (под очередью правок)
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

BACKUP = os.path.join(ROOT, "art", "_backup", "t_slope_edge_20261031")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
SETS = {"MOUNTTROP": "t431", "FORESTJUNGLESTYX": "t431", "MOUNTGRASS": "t445"}
FRAMES = list(range(27, 40)) + [41]


def collect():
    return {"TERRAIN/%s.PCK/%d.png" % (s, f): os.path.join(ROOT, "art", "tickets", t, "cand", "A1e", "%s_%d.png" % (s, f))
            for s, t in SETS.items() for f in FRAMES}


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
    n = ts.install_files(files, "t_slope_edge_install", "XP-000429/431/445: ровный край склонов (t_slope_edge A1e)",
                         "Vitali: страница выбора, Ставить новый край склонов, 31.10 00:29",
                         "ровный край склонов MOUNTTROP, FORESTJUNGLESTYX, MOUNTGRASS")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
