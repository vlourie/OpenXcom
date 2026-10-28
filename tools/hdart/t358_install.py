#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000358 (машина «Возьмёрка», судно V8, CADILLAC:3..13): подключение кадров варианта A (выбор Vitali 28.10).
Кадры - art/tickets/t358/cand (их делает t358_build.py). Без --yes - сухой прогон, ничего не пишет.

Семья (R-457) - одиннадцать кадров одного набора, ставятся ОДНИМ коммитом в обе копии мода hd:
  CADILLAC:3..12   объектные клетки машины по MAPS/CADILLAC.MAP, CADILLAC:13 - в слоте стены (задний левый угол)
  CADILLAC:1, 2 (зелёный пол) не трогаются.

    py -3.13 tools\hdart\t358_install.py          # сухой прогон
    py -3.13 tools\hdart\t358_install.py --yes    # записать (под очередью правок: editq wait/done)
"""
import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[1]
os.chdir(ROOT)
CAND = ROOT / "art" / "tickets" / "t358" / "cand"
FRAMES = list(range(3, 14))


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
            raise SystemExit("нет файла %s (запусти t358_build.py)" % p)
        im = Image.open(p)
        if im.size != (128, 160) or im.mode != "RGBA":
            raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
        files["TERRAIN/CADILLAC.PCK/%d.png" % f] = p
    import build_hd_pack as bp
    man = bp.load()
    for rel, p in files.items():
        old = man["files"].get(rel, {}).get("sha256", "")[:10] or "нет в манифесте"
        where = ["%s:%s" % (n, "есть" if os.path.exists(os.path.join(root, rel)) else "нет") for n, root in bp.TARGETS.items()]
        print("  %-30s <- %s  (манифест %s; %s)" % (rel, p.name, old, ", ".join(where)))
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (под очередью правок: editq wait/done)")
    import ticket_scene as ts
    n = ts.install_files(files, "t358_install", "t358_build.py 28.10 процедурно: тон классики + фактура прежнего HD, одна машина на холсте",
                         "Vitali 28.10, XP-000358, вариант A, лист xp358_fix_sheet.png",
                         "t358: машина V8 CADILLAC:3..13 цельной картинкой на холсте, нарезка по маскам классики (%d кадров)" % len(files))
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
