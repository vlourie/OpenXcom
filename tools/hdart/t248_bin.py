#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000248: URBAN_WASTE:98 - вариант 4 (зерно 24804), выбор Vitali 23.10. Один кадр, семьи нет (ticket_family: членов 0).

Кадр берётся как есть из art/tickets/t248/gen/series/URBAN_WASTE.PCK/98_24804.png (128x160 RGBA, видеокарта не нужна).

    py -3.13 tools/hdart/t248_bin.py                  # проверка файла
    py -3.13 tools/hdart/t248_bin.py --install --yes  # в мод hd через манифест (под очередью правок)
"""
import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts   # noqa: E402

SRC = ROOT / "art" / "tickets" / "t248" / "gen" / "series" / "URBAN_WASTE.PCK" / "98_24804.png"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    im = Image.open(SRC)
    assert im.size == (128, 160) and im.mode == "RGBA", (im.size, im.mode)
    print("кадр:", SRC)
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files({"TERRAIN/URBAN_WASTE.PCK/98.png": SRC}, "t248_bin", "t248_bin.py 23.10 вариант 4 (зерно 24804)",
                         "Vitali 23.10 (XP-000248 URBAN_WASTE:98, вариант 4, зерно 24804)",
                         "t248: URBAN_WASTE 98 - вариант 4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
