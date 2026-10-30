#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка кандидата 2 тикетов XP-000436/437 (Vitali 30.10 20:35: «Ставить всё: POLAR + семья»; ASHEN1 41-43 - не ставить).

  POLAR 34, BEACH 34, FORESTSWAMP_SNOW 23, ASHEN1 14 (5, 6, 48-59) - art/tickets/t436/cand/<НАБОР>/N.png (t436_build.py).
  ASHEN1 41-43 не ставятся: разлом 40-43 остаётся прежним одобренным, иначе он собран из разных рук.

Через манифест (build_hd_pack: stage + save + install в game и repo + сверка хэшей), резерв прежних файлов -
art/_backup/t436_20261030/<путь пака>.

    py -3.13 tools\hdart\t436_install.py            сухой прогон
    py -3.13 tools\hdart\t436_install.py --yes      установить (под очередью правок)
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

from PIL import Image                        # noqa: E402

BACKUP = os.path.join(ROOT, "art", "_backup", "t436_20261030")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
CAND = os.path.join(ROOT, "art", "tickets", "t436", "cand")
SETS = ("POLAR", "BEACH", "FORESTSWAMP_SNOW", "ASHEN1")
SKIP = {("ASHEN1", 41), ("ASHEN1", 42), ("ASHEN1", 43)}


def collect():
    files = {}
    for s in SETS:
        for name in sorted(os.listdir(os.path.join(CAND, s))):
            m = re.fullmatch(r"(\d+)\.png", name)
            if not m or (s, int(m.group(1))) in SKIP:
                continue
            files["TERRAIN/%s.PCK/%s" % (s, name)] = os.path.join(CAND, s, name)
    return files


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    yes = "--yes" in sys.argv
    files = collect()
    for rel, p in files.items():
        # with: незакрытый кадр пака держит файл, и os.replace при установке падает (Windows)
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
    n = ts.install_files(files, "t436_install", "XP-000436/437: снег POLAR и семья, кандидат 2 (t436_build)",
                         "Vitali: страница выбора, Ставить всё, ASHEN1 41-43 не ставить, 30.10 20:35",
                         "t436 разломы, проталины, камушки POLAR и семьи (BEACH, FORESTSWAMP_SNOW, ASHEN1) по рисунку классики")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
