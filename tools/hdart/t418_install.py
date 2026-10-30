#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000418: подключение будки (5 кадров) после выбора зерна Vitali. БЕЗ --yes - сухой прогон, ничего не пишет.
Заготовки - art/tickets/t418/cand/B/<НАБОР>_<кадр>.png (t418_booth.py build). Альфа заднего стекла (B2) запечена в самих
кадрах, glass_alpha_objects.txt трогать не надо (и нельзя: object_mask там берёт цвет и умножил бы альфу второй раз).

  PORTROADS:34 - основа; MILURBITSEXT:18, MILWARE:45, MILWAREGHOUL:44, XBITSUFO:44 - перенос цвета классики (R-457).
  Обломки PORTROADS:35 и их перекраски (5 кадров) НЕ берутся - слово Vitali.

Ставится одним коммитом, в обе копии мода hd, под очередью правок (py -3 tools/editq.py wait; после проверки done):
    py -3.13 tools\hdart\t418_install.py          # сухой прогон
    py -3.13 tools\hdart\t418_install.py --yes
"""
import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[1]
os.chdir(ROOT)
CAND = ROOT / "art" / "tickets" / "t418" / "cand" / "B"
KEYS = [("PORTROADS", 34), ("MILURBITSEXT", 18), ("MILWARE", 45), ("MILWAREGHOUL", 44), ("XBITSUFO", 44)]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    from PIL import Image
    files = {}
    for s, f in KEYS:
        p = CAND / ("%s_%d.png" % (s, f))
        if not p.exists():
            raise SystemExit("нет заготовки %s" % p)
        im = Image.open(p)
        if im.size != (128, 160) or im.mode != "RGBA":
            raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
        files["TERRAIN/%s.PCK/%d.png" % (s, f)] = p
    import build_hd_pack as bp
    man = bp.load()
    for rel, p in files.items():
        old = man["files"].get(rel, {}).get("sha256", "")[:10] or "нет в манифесте"
        print("  %-36s <- %s  (манифест %s)" % (rel, p.name, old))
    if not a.yes:
        raise SystemExit("сухой прогон, кадров %d; --yes - записать в мод (под очередью правок)" % len(files))
    import ticket_scene as ts
    n = ts.install_files(files, "t418_booth", "будка PORTROADS 34 и семья: Qwen strict + перенос цвета классики, стекло B2",
                         "Vitali 30.10: вариант B (будка с деталями, 5 кадров, без обломков) и стекло B2",
                         "t418: будка пропускная PORTROADS:34 и 4 перекраски (%d кадров)" % len(files))
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
