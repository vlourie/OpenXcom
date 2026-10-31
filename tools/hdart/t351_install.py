# -*- coding: utf-8 -*-
r"""Тикет XP-000351 (выбор Vitali: вариант S, готовые посевы 22.10): варианты .v1-.v3 пола
URBAN_WASTE:80 и побайтной копии URBAN_WASTE_WALLS:74 - 6 файлов в обе копии мода hd через манифест.
  v1 = s22112, v2 = s22113, v3 = зеркало s22112 по вертикальной оси ромба.
Готовые файлы делает t351_build.py (art/_review/tickets_2026-10-28/t351_install/TERRAIN/...).
Установка - ticket_scene.install_files (stage + save манифеста + install в game и repo + сверка хешей),
как у XP-000220 / t343.

    py -3.13 tools\hdart\t351_install.py          # сухой прогон: проверка 6 файлов и список
    py -3.13 tools\hdart\t351_install.py --yes    # записать (ТОЛЬКО под очередью правок и по слову Vitali)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)
SRC = os.path.join(ROOT, "art", "_review", "tickets_2026-10-28", "t351_install")
SETS = (("URBAN_WASTE", 80), ("URBAN_WASTE_WALLS", 74))


def collect():
    from PIL import Image
    files = {}
    for s, n in SETS:
        base = Image.open(os.path.join(ROOT, "user", "mods", "hd", "hd", "TERRAIN", s + ".PCK", "%d.png" % n)).convert("RGBA")
        bm = base.getchannel("A").point(lambda a: 255 if a else 0).tobytes()
        for v in (1, 2, 3):
            rel = "TERRAIN/%s.PCK/%d.v%d.png" % (s, n, v)
            p = os.path.join(SRC, rel.replace("/", os.sep))
            im = Image.open(p)
            assert im.size == (128, 160) and im.mode == "RGBA", (rel, im.size, im.mode)
            assert im.getchannel("A").point(lambda a: 255 if a else 0).tobytes() == bm, rel + ": маска не как у основы"
            files[rel] = p
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files = collect()
    print("файлов:", len(files))
    for r in files:
        print("  ", r)
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (по слову Vitali, под очередью правок)")
    import ticket_scene as ts
    n = ts.install_files(files, "t351_install", "t351: варианты v1-v3 из посевов 22.10 (s22112, s22113, зеркало s22112)",
                         "Vitali: вариант S (готовые посевы 22.10), тикет XP-000351",
                         "t351: варианты пола URBAN_WASTE:80 и URBAN_WASTE_WALLS:74 - плитчатые вместо гладких floor_tone")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
