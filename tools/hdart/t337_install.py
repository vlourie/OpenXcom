#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000337 (двухтайловые койки): подключение варианта, выбранного Vitali. Кадры вариантов - art/tickets/t337/cand
(их делает t337_probe.py). Без --yes - сухой прогон, ничего не пишет (только читает манифест и обе копии мода).

Семья (R-457) - шесть кадров, ставятся ОДНИМ коммитом, в обе копии мода hd:
  XB1BR:52, XB1BR:53              койка спальных блоков XBASE (XBR_131/132/134/136-139), 33 + 30 блоков, 413 клеток
  LAM_BASE2:12, LAM_BASE2:14      перекраска той же койки у ламий (деревня), пара 14+12
  LAM_BASE2:18, LAM_BASE2:19      она же, зеркальная раскладка, пара 18+19

  --variant A|B|C   вариант для всех трёх пар (A_g_head, B_g_full, C_clean)
  --xb / --lam12 / --lam18 A|B|C   вариант отдельной пары (перекрывает --variant)
  --yes             записать в мод (манифест, обе копии, сверка хэшей) - только по слову Vitali и под очередью правок

В репозиторной копии (user/mods/hd) набор LAM_BASE2 сейчас почти пуст (лежит только 10.png), игровая копия (Пиратки)
полная: установка по манифесту добавит в репозиторную копию четыре кадра 12, 14, 18, 19 - как и записано в манифесте.

    py -3.13 tools\hdart\t337_install.py --variant B
    py -3.13 tools\hdart\t337_install.py --variant B --xb A
    py -3.13 tools\hdart\t337_install.py --variant B --yes
"""
import argparse
import hashlib
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[1]
os.chdir(ROOT)
CAND = ROOT / "art" / "tickets" / "t337" / "cand"
VDIR = {"A": "A_g_head", "B": "B_g_full", "C": "C_clean"}
PAIRS = {"xb": [("XB1BR", 52), ("XB1BR", 53)],
         "lam12": [("LAM_BASE2", 12), ("LAM_BASE2", 14)],
         "lam18": [("LAM_BASE2", 18), ("LAM_BASE2", 19)]}


def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=sorted(VDIR), required=True)
    for k in PAIRS:
        ap.add_argument("--" + k, choices=sorted(VDIR))
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    from PIL import Image
    files = {}
    for pair, frames in PAIRS.items():
        v = getattr(a, pair) or a.variant
        for s, f in frames:
            p = CAND / VDIR[v] / ("%s_%d.png" % (s, f))
            if not p.exists():
                raise SystemExit("нет файла %s (запусти t337_probe.py)" % p)
            im = Image.open(p)
            if im.size != (128, 160) or im.mode != "RGBA":
                raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
            files["TERRAIN/%s.PCK/%d.png" % (s, f)] = p
    import build_hd_pack as bp
    man = bp.load()
    for rel, p in files.items():
        old = man["files"].get(rel, {}).get("sha256", "")[:10] or "нет в манифесте"
        where = ["%s:%s" % (n, "есть" if os.path.exists(os.path.join(root, rel)) else "нет") for n, root in bp.TARGETS.items()]
        print("  %-34s <- %s/%s  (манифест %s; %s)" % (rel, p.parent.name, p.name, old, ", ".join(where)))
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (по слову Vitali, под очередью правок: editq wait/done)")
    import ticket_scene as ts
    n = ts.install_files(files, "t337_install", "t337_probe.py 27.10 процедурно по маске классики, цельная койка на две клетки",
                         "Vitali: выбор варианта по тикету XP-000337",
                         "t337: койка XB1BR 52/53 и перекраски LAM_BASE2 12/14, 18/19 цельной картинкой на обе клетки (%d кадров)" % len(files))
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
