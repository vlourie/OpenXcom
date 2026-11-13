#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000349 вариант B: поставить 42 клипа попаданий без звезды в мод hd (обе копии) через манифест.
Источник - art/_review/tickets_2026-10-28/t349_install/hd/FX (вывод gen_combat_fx.py --ground-v2 --no-star); clips.yml не ставится.

    py -3.13 tools\hdart\t349_install.py          # сухой прогон: сколько файлов изменится, ничего не пишет
    py -3.13 tools\hdart\t349_install.py --yes    # в мод (под очередью правок editq, по слову Vitali)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)
import build_hd_pack as bp                          # noqa: E402

SRC = os.path.join(ROOT, "art", "_review", "tickets_2026-10-28", "t349_install", "hd", "FX")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    man = bp.load()
    files = {}
    for d in sorted(os.listdir(SRC)):
        p = os.path.join(SRC, d)
        if not os.path.isdir(p):
            continue
        for fn in sorted(os.listdir(p)):
            if fn.endswith(".png"):
                files["FX/%s/%s" % (d, fn)] = os.path.join(p, fn)
    chg = [r for r, s in files.items() if man["files"].get(r, {}).get("sha256") != bp.sha256_file(s)]
    print("клипов %d, файлов в источнике %d, изменится %d" % (len({r.split('/')[1] for r in files}), len(files), len(chg)))
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод")
    import ticket_scene as ts
    n = ts.install_files(files, "t349_install", "gen_combat_fx.py --ground-v2 --no-star 28.10",
                         "Vitali: вариант B, тикет XP-000349 (звезду убрать совсем)",
                         "t349: клипы попаданий в землю без звезды (XP-000349, вариант B)")
    print("установлено файлов: %d" % n)


if __name__ == "__main__":
    main()
