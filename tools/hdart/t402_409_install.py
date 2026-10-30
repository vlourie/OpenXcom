#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000402, 403, 406, 407, 408 (защита базы, 30.10): подключение заготовок, выбранных командиром по слову
Vitali «делай как считаешь нужным» (30.10). Заготовки - art/tickets/t402_409/cand/<вариант>/<НАБОР>_<кадр>.png
(t402_409_cand.py и скрипты исполнителей). Без --yes - сухой прогон: ничего не пишет.

  402B  стул XB1BR 54-57: синее кресло XBASE1 54-57, перекрашенное в серый классики (55-57 были коричневой глыбой)
  403A  растение XB3BITZ3:22 и копии: одобренный HD A_BASE:48 с ярким кончиком; перекраска SGR_CAVE:57
        (синие LAM_BASE:35, ICEKING_VILLAGE:45, MUMMY_VILLAGE:45 не ставятся: кончик у них выходит вдвое мельче классики)
  406A  стол XB1BR:58: доски из снимка пака 22.09 вместо плетёнки
  407A  чёрточки на матрасе коек рисует пол следующей клетки (XB1BR:10 и семья, 16 кадров): у пола срезан выступ
        за силуэт классики x4 в верхней половине ромба (y < 128); нижний выступ и всё внутри силуэта - как было
  408A  раковина XB3BITZ1:19 и семья (28 кадров): форма одобренной MAG:19 в керамике классики

Ставится одним коммитом, в обе копии мода hd (R-457), под очередью правок.

    py -3.13 tools\hdart\t402_409_install.py
    py -3.13 tools\hdart\t402_409_install.py --yes
"""
import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[1]
os.chdir(ROOT)
CAND = ROOT / "art" / "tickets" / "t402_409" / "cand"
SKIP = {"403A": {"LAM_BASE_35", "ICEKING_VILLAGE_45", "MUMMY_VILLAGE_45"}}


def frames(variant):
    """{'TERRAIN/НАБОР.PCK/N.png': путь} для всех заготовок варианта (имя файла - НАБОР_кадр, набор может содержать _)."""
    out = {}
    for p in sorted((CAND / variant).glob("*.png")):
        if p.stem in SKIP.get(variant, ()):
            continue
        s, f = p.stem.rsplit("_", 1)
        out["TERRAIN/%s.PCK/%d.png" % (s, int(f))] = p
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bed", default="407A", help="вариант пола под койками (папка в cand); пусто - без него")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    from PIL import Image
    files = {}
    for v in [x for x in ("402B", "403A", "406A", a.bed, "408A") if x]:
        part = frames(v)
        if not part:
            raise SystemExit("нет заготовок %s" % v)
        print("%s: %d кадров" % (v, len(part)))
        files.update(part)
    for rel, p in files.items():
        im = Image.open(p)
        if im.size != (128, 160) or im.mode != "RGBA":
            raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
    import build_hd_pack as bp
    man = bp.load()
    for rel, p in files.items():
        old = man["files"].get(rel, {}).get("sha256", "")[:10] or "нет в манифесте"
        print("  %-38s <- %s/%s  (манифест %s)" % (rel, p.parent.name, p.name, old))
    if not a.yes:
        raise SystemExit("сухой прогон, кадров %d; --yes - записать в мод (под очередью правок)" % len(files))
    import ticket_scene as ts
    n = ts.install_files(files, "t402_409_install", "заготовки 30.10: откат/перекраска/вывод семьи по маске классики",
                         "Vitali 30.10: «делай как считаешь нужным» по тикетам защиты базы",
                         "t402_409: стул, растение, стол, пол под койками, раковина защиты базы (%d кадров)" % len(files))
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
