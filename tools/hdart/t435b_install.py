#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка второй основы тикета XP-000435 (Vitali 30.10 23:23: «Ставить 4395 во все шесть»).

  Голубая угловая плита (кастрюля и две конфорки) зерном 4395 - один кадр на шесть наборов с одинаковой классикой:
  CITYFRNITURE:15, COMFRN:15, COMFRN2:9, FRNITURE:15, FRNITURE_WASTE:15, VILFRNITURE:14
  (art/tickets/t435/cand/435b/<НАБОР>_<кадр>.png, t435b_gen.py).

Через манифест (build_hd_pack: stage + save + install в game и repo + сверка хэшей), резерв прежних файлов -
art/_backup/t435b_20261030/<путь пака>.

    py -3.13 tools\hdart\t435b_install.py            сухой прогон
    py -3.13 tools\hdart\t435b_install.py --yes      установить (под очередью правок)
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

BACKUP = os.path.join(ROOT, "art", "_backup", "t435b_20261030")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
CAND = os.path.join(ROOT, "art", "tickets", "t435", "cand", "435b")


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
    new = []
    for rel, p in files.items():
        # with: незакрытый кадр пака держит файл, и os.replace при установке падает (R-567)
        with Image.open(p) as im:
            if im.mode != "RGBA" or im.size != (128, 160):
                raise SystemExit("%s: ждали RGBA (128, 160), а %s %s" % (p, im.mode, im.size))
        if not os.path.exists(os.path.join(REPO_PACK, rel)):
            new.append(rel)
    print("файлов к установке: %d, из них новых (HD не было): %d %s" % (len(files), len(new), " ".join(new)))
    if not yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (под очередью правок)")
    for rel in files:
        src = os.path.join(REPO_PACK, rel)
        dst = os.path.join(BACKUP, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copyfile(src, dst)
    print("резерв:", BACKUP)
    import ticket_scene as ts
    n = ts.install_files(files, "t435b_install", "XP-000435: плита зерном 4395 в шесть наборов (t435b_gen, Qwen strict)",
                         "Vitali: страница выбора, Ставить 4395 во все шесть, 30.10 23:23",
                         "t435b голубая угловая плита в шести наборах мебели")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
