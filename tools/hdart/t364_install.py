#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000364 (бочка 2x2 и труба, RUSTSHACKS2): подключение кадров варианта A (выбор Vitali 28.10).
Кадры - art/tickets/t364/cand (их делает t364_build.py). Без --yes - сухой прогон, ничего не пишет.

Семья (R-457) - десять кадров одного набора, ставятся ОДНИМ коммитом в обе копии мода hd:
  RUSTSHACKS2:43, 44, 45, 46   бочка 2x2 (передняя, правая, левая, задняя)
  RUSTSHACKS2:3, 4, 5, 7, 9, 11   труба (заглушки, прямые, колена)
Не трогаются: RUSTSHACKS2:8 (тройник, одобрен Vitali 15.10, wall_exact_C), 6/10/12, 42 (одиночная бочка и её
18 перекрасок), MADDECOR_WASTE 75-78 (одобренный HD, донор фактуры - только чтение).

    py -3.13 tools\hdart\t364_install.py          # сухой прогон
    py -3.13 tools\hdart\t364_install.py --yes    # записать (под очередью правок: editq wait/done)
"""
import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[1]
os.chdir(ROOT)
CAND = ROOT / "art" / "tickets" / "t364" / "cand"
FRAMES = [3, 4, 5, 7, 9, 11, 43, 44, 45, 46]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    from PIL import Image
    files = {}
    for f in FRAMES:
        p = CAND / ("%d.png" % f)
        if not p.exists():
            raise SystemExit("нет файла %s (запусти t364_build.py)" % p)
        im = Image.open(p)
        if im.size != (128, 160) or im.mode != "RGBA":
            raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
        files["TERRAIN/RUSTSHACKS2.PCK/%d.png" % f] = p
    import build_hd_pack as bp
    man = bp.load()
    for rel, p in files.items():
        old = man["files"].get(rel, {}).get("sha256", "")[:10] or "нет в манифесте"
        where = ["%s:%s" % (n, "есть" if os.path.exists(os.path.join(root, rel)) else "нет") for n, root in bp.TARGETS.items()]
        print("  %-34s <- %s  (манифест %s; %s)" % (rel, p.name, old, ", ".join(where)))
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (под очередью правок: editq wait/done)")
    import ticket_scene as ts
    n = ts.install_files(files, "t364_install", "t364_build.py 28.10 процедурно: бочка 2x2 и трубы RUSTSHACKS2 на одном холсте, тон классики + фактура донора",
                         "Vitali 28.10, XP-000364, вариант A, лист t364_fix_sheet.png",
                         "t364: бочка 2x2 RUSTSHACKS2:43-46 и трубы 3/4/5/7/9/11 цельной картинкой на холсте, нарезка по маскам классики (%d кадров)" % len(files))
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
