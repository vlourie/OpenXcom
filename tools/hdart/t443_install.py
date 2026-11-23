#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка кандидата тикета XP-000443 (Vitali 30.10 23:42: «Ставить все 12»).

  Балки Города гулей: прямые 4438, узел 4452, обугленные 4530 (Qwen strict, t443_gen.py), зеркала с переносом цвета
  классики - MILWAREGHOUL 47 48 49 50 52 54 и MILWARE 48 49 50 51 53 55 (классика наборов побайтно одна),
  art/tickets/t443/cand/<НАБОР>_<кадр>.png, 12 кадров.

Через манифест (build_hd_pack: stage + save + install в game и repo + сверка хэшей), резерв прежних файлов -
art/_backup/t443_20261030/<путь пака>.

    py -3.13 tools\hdart\t443_install.py            сухой прогон
    py -3.13 tools\hdart\t443_install.py --yes      установить (под очередью правок)
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

BACKUP = os.path.join(ROOT, "art", "_backup", "t443_20261030")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
CAND = os.path.join(ROOT, "art", "tickets", "t443", "cand")


def collect():
    files = {}
    for name in sorted(os.listdir(CAND)):
        m = re.fullmatch(r"(.+)_(\d+)\.png", name)
        if m:
            files["TERRAIN/%s.PCK/%s.png" % (m.group(1), m.group(2))] = os.path.join(CAND, name)
    return files


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    yes = "--yes" in sys.argv
    files = collect()
    if len(files) != 12:
        raise SystemExit("ждали 12 кадров, а %d" % len(files))
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
    n = ts.install_files(files, "t443_install", "XP-000443: балки Города гулей 4438/4452/4530 + зеркала (t443_gen, Qwen strict)",
                         "Vitali: страница выбора, Ставить все 12, 30.10 23:42",
                         "t443 балки MILWAREGHOUL и MILWARE вместо рельсов со шпалами")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
