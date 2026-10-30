#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка кандидатов тикета XP-000435 (Vitali 30.10 20:42: «Ставить зёрна со звёздочкой + семья»).

  Стойка CULTDECOR:22 (зерно 4351), раковина CULTEXTRA:31 (4363), кулер CULTDECOR:51 (4383) и их семья - 19 кадров
  art/tickets/t435/cand/435/<НАБОР>_<кадр>.png (t435_gen.py). Вторая основа раковины (435b) - отдельно.

Через манифест (build_hd_pack: stage + save + install в game и repo + сверка хэшей), резерв прежних файлов -
art/_backup/t435_20261030/<путь пака>.

    py -3.13 tools\hdart\t435_install.py            сухой прогон
    py -3.13 tools\hdart\t435_install.py --yes      установить (под очередью правок)
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

BACKUP = os.path.join(ROOT, "art", "_backup", "t435_20261030")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
CAND = os.path.join(ROOT, "art", "tickets", "t435", "cand", "435")


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
    n = ts.install_files(files, "t435_install", "XP-000435: стойка 4351, раковина 4363, кулер 4383 + семья (t435_gen, Qwen strict)",
                         "Vitali: страница выбора, Ставить зёрна со звёздочкой + семья, 30.10 20:42",
                         "t435 мебель притона: стойка с бутылками, раковина, кулер и семья")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
