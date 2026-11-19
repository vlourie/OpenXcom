#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000266: убрать из мода hd все наши версии картинки педии Sexy_Clinic («Магия Любви»).

На картинке среди взрослых в откровенной сцене стоит ребёнок (пришёл из исходного рисунка мода, все HD-версии
его повторили, а 18+ сделала фотореалистичным). Такое не распространяем: файлы уходят из обеих копий мода hd
(игра и репозиторий) в art/_backup/t266_<время>, записи - из манифеста, чтобы install их не вернул. Игра
показывает исходный рисунок мода Piratez. Новую версию - только без ребёнка и только по слову Vitali.

    py -3.13 tools/hdart/t266_pull_image.py
    py -3.13 tools/hdart/t266_pull_image.py --yes
"""
import argparse
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(os.path.dirname(os.path.dirname(HERE)))

import build_hd_pack as bp                           # noqa: E402
import common                                        # noqa: E402

NAME = "Sexy_Clinic"
ROOTS = {"game": common.GAME_HD, "repo": os.path.join("user", "mods", "hd")}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="убрать")
    a = ap.parse_args()
    found = []
    for target, root in ROOTS.items():
        for sub, _, files in os.walk(root):
            for f in files:
                if f.startswith(NAME + "."):
                    found.append((target, root, os.path.relpath(os.path.join(sub, f), root)))
    man = bp.load()
    rels = [r for r in man["files"] if os.path.basename(r).startswith(NAME + ".")]
    for t, _, rel in found:
        print("файл:", t, rel)
    for r in rels:
        print("манифест:", r)
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - убрать")
    backup = os.path.join("art", "_backup", "t266_" + time.strftime("%Y%m%d_%H%M%S"))
    for t, root, rel in found:
        dst = os.path.join(backup, t, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(os.path.join(root, rel), dst)
        bp.log("t266-pull:" + t, rel.replace(os.sep, "/"), "", dst)
    for r in rels:
        del man["files"][r]
    bp.save(man, why="t266: Sexy_Clinic убран - на картинке ребёнок")
    left = [(t, rel) for t, root, rel in found if os.path.exists(os.path.join(root, rel))]
    if left:
        raise SystemExit("ОСТАЛИСЬ: %s" % left)
    print("убрано файлов %d, записей манифеста %d, копия в %s" % (len(found), len(rels), backup))
    return 0


if __name__ == "__main__":
    sys.exit(main())
