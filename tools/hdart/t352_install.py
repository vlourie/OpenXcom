# -*- coding: utf-8 -*-
r"""Тикет XP-000352 (выбор Vitali: вариант A по обоим пунктам): кромка шоссе ROADS_WASTE 0-8 и трещины 18/19 с побайтными
копиями XOPSDESERTRUINS 37 = 18, 38 = 19 - 13 файлов в обе копии мода hd через манифест.
Готовые файлы делает t352_build.py (art/_review/tickets_2026-10-28/t352_install/TERRAIN/... + MANIFEST.json).
Установка - ticket_scene.install_files (stage + save манифеста + install в game и repo + сверка хешей), как t351.
В репо-копии нет ROADS_WASTE.PCK - ставится через манифест, как 349/351.

    py -3.13 tools\hdart\t352_install.py          # сухой прогон: проверка 13 файлов и список
    py -3.13 tools\hdart\t352_install.py --yes    # записать (ТОЛЬКО под очередью правок и по слову Vitali)
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)
SRC = os.path.join(ROOT, "art", "_review", "tickets_2026-10-28", "t352_install")
EXPECT = ["TERRAIN/ROADS_WASTE.PCK/%d.png" % f for f in (0, 1, 2, 3, 4, 5, 6, 7, 8, 18, 19)] + \
         ["TERRAIN/XOPSDESERTRUINS.PCK/37.png", "TERRAIN/XOPSDESERTRUINS.PCK/38.png"]


def collect():
    from PIL import Image
    with open(os.path.join(SRC, "MANIFEST.json"), encoding="utf-8-sig") as fh:
        man = json.load(fh)
    assert sorted(man["files"]) == sorted(EXPECT), "состав манифеста не тот: %s" % sorted(man["files"])
    files = {}
    for rel in EXPECT:
        p = os.path.join(SRC, rel.replace("/", os.sep))
        with open(p, "rb") as fh:
            h = hashlib.sha256(fh.read()).hexdigest()
        assert h == man["files"][rel], rel + ": хэш не совпал с MANIFEST.json (пересобери t352_build.py)"
        im = Image.open(p)
        assert im.size == (128, 160) and im.mode == "RGBA", (rel, im.size, im.mode)
        files[rel] = p
    # копии побайтно равны основе
    for a, b in (("ROADS_WASTE.PCK/18.png", "XOPSDESERTRUINS.PCK/37.png"), ("ROADS_WASTE.PCK/19.png", "XOPSDESERTRUINS.PCK/38.png")):
        assert man["files"]["TERRAIN/" + a] == man["files"]["TERRAIN/" + b], "копия не равна основе: " + b
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files = collect()
    # Vitali 28.10 по листу t352_B_sheet: края ставить как есть, трещины 18/19 (и копии 37/38) - оставить нынешние
    files = {r: p for r, p in files.items() if r.startswith("TERRAIN/ROADS_WASTE.PCK/") and int(r.rsplit("/", 1)[1][:-4]) <= 8}
    print("файлов:", len(files))
    for r in files:
        print("  ", r)
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (по слову Vitali, под очередью правок)")
    import ticket_scene as ts
    n = ts.install_files(files, "t352_build", "t352_build.py 28.10: 0 - щебёнка по маске классики, 1-8 - t249 (маска классики)",
                         "Vitali 28.10: края ставить как есть, трещины оставить нынешние; тикет XP-000352; лист art/_review/tickets_2026-10-28/t352_B_sheet.png",
                         "t352: кромка шоссе ROADS_WASTE 0-8 - по маске классики, текстура асфальта 9 и песка 16")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
