#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000280 (песок MOUNTSAND:4/5 с золотыми кляксами): подключение варианта, выбранного Vitali.
Кадры вариантов - art/tickets/t280/cand (их делает t280_probe.py). Без --yes - сухой прогон, ничего не пишет.

  --four A|B|C   MOUNTSAND:4 = MOUNTSAND_4_<вариант>.png (A_grain3, B_grit_mud5, C_sandv1_tone)
  --five A|B|C   MOUNTSAND:5 = MOUNTSAND_5_<вариант>.png (A_copy_MOUNTMUD5, B_grain3, C_sandv1_tone); пусто - 5 не трогать
  --yes          записать в мод hd (манифест, обе копии, сверка хэшей) - только по слову Vitali и под очередью правок

Семья: MOUNTMUD:4 (перекраска классики 4, HD - другой рисунок, годный) и GOTHIC:5, MOUNTMUD:5 (копии классики 5, HD
годные) не трогаются; MOUNTSAND:3 и :6 годные.

    py -3.13 tools\hdart\t280_install.py --four B --five A
    py -3.13 tools\hdart\t280_install.py --four B --five A --yes
"""
import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[1]
os.chdir(ROOT)
CAND = ROOT / "art" / "tickets" / "t280" / "cand"
NAMES4 = {"A": "4_A_grain3", "B": "4_B_grit_mud5", "C": "4_C_sandv1_tone"}
NAMES5 = {"A": "5_A_copy_MOUNTMUD5", "B": "5_B_grain3", "C": "5_C_sandv1_tone"}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--four", choices=sorted(NAMES4), required=True)
    ap.add_argument("--five", choices=sorted(NAMES5))
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files = {"TERRAIN/MOUNTSAND.PCK/4.png": CAND / ("MOUNTSAND_%s.png" % NAMES4[a.four])}
    if a.five:
        files["TERRAIN/MOUNTSAND.PCK/5.png"] = CAND / ("MOUNTSAND_%s.png" % NAMES5[a.five])
    for rel, p in files.items():
        print("  %s <- %s (%s)" % (rel, p.name, "есть" if p.exists() else "НЕТ ФАЙЛА"))
        if not p.exists():
            raise SystemExit(1)
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (по слову Vitali, под очередью правок)")
    import ticket_scene as ts
    n = ts.install_files(files, "t280_install", "t280_install.py 27.10", "Vitali: выбор варианта по тикету XP-000280",
                         "t280: песок MOUNTSAND 4%s без золотых клякс" % (" и 5" if a.five else ""))
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
