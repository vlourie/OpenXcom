#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка капусты XP-000455 (Vitali 02.11, страница выбора: вариант A55 = cab7d_3982_f55, кочан 55% ширины ромба).

4 кадра: CULTIVAT_UBER:7, CULTIVAT:7, CULTIVAT_PP:7, VILFRNITURE:104. Через манифест (build_hd_pack: stage + save +
install в game и repo + сверка хэшей), резерв прежних - art/_backup/t455_2026-11-02/<путь пака>.

    py -3.13 tools\hdart\t455_install.py            сухой прогон
    py -3.13 tools\hdart\t455_install.py --yes      установить (под очередью правок)
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

BACKUP = os.path.join(ROOT, "art", "_backup", "t455_2026-11-02")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
CAND = os.path.join(ROOT, "art", "tickets", "t455", "cab7d_3982_f55")
FRAMES = [("CULTIVAT_UBER", 7), ("CULTIVAT", 7), ("CULTIVAT_PP", 7), ("VILFRNITURE", 104)]


def collect():
    return {"TERRAIN/%s.PCK/%d.png" % (n, f): os.path.join(CAND, "%s_%d.png" % (n, f)) for n, f in FRAMES}


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
    n = ts.install_files(files, "t455_install", "XP-000455: капуста A55 (кочан 55%% ромба, земля вокруг)",
                         "Vitali: страница выбора, вариант A55, 02.11",
                         "t455 капуста A55: CULTIVAT_UBER:7, CULTIVAT:7, CULTIVAT_PP:7, VILFRNITURE:104")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
