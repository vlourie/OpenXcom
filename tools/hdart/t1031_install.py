#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка кандидатов тикетов 379, 383, 388, 391, 394 (выбор Vitali 31.10, страница выбора, пункты c1031b_NNN).

Новый арт не генерирует: берёт готовые кадры из art/tickets/t<N>/cand/<НАБОР>_<кадр>.png (их написали
t379_391_gen.py, t383_gen.py, t394_395_gen.py по BEST-зёрнам) и ставит через манифест
(ticket_scene.install_files: stage + save + install в game и repo + сверка хэшей).
Резерв нынешних кадров - art/_backup/t<N>_2026-10-31/<путь пака>.

  379  WESTFLOOR:9, MEDIEVAL:25                                       (зерно 3802, ключ Y)
  388  WESTFLOOR:5/6, IDT_BARNFLOOR:5/6                               (зерно 3890, ключ Y)
  391  URBAN_WASTE:95/96/97 (3945/3964/3974), INDUSLUM:54, PORTURBITS:54  (ключ Y, все три)
  383  PORTROADS:23 и боковая лесенка семьёй - 38 кадров (ключ Y)
  394  CULTIVAT_UBER:12, CULTIVAT:12, GOTHIC:22 (зерно 3941); CULTIVAT_PP:12 и кадры 395 НЕ ставятся

    py -3.13 tools\hdart\t1031_install.py --ticket 379                  сухой прогон
    py -3.13 tools\hdart\t1031_install.py --ticket 379 --install --yes  установить (под очередью правок)
"""
import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

from PIL import Image                        # noqa: E402

REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
ART = os.path.join(ROOT, "art", "tickets")

# тикет -> (число кадров, список кадров или None = все png папки cand, пункт страницы, описание)
TICKETS = {
    "379": (2, ["WESTFLOOR_9", "MEDIEVAL_25"], "c1031b_379: верх печной трубы, зерно 3802, Y",
            "XP-000379: верх печной трубы WESTFLOOR:9 + MEDIEVAL:25 (t379_391_gen, Qwen strict)", "t379_391_gen"),
    "388": (4, ["WESTFLOOR_5", "WESTFLOOR_6", "IDT_BARNFLOOR_5", "IDT_BARNFLOOR_6"], "c1031b_388: дверь дома, зерно 3890, Y",
            "XP-000388: дверь дома WESTFLOOR 5/6 + IDT_BARNFLOOR 5/6 (t379_391_gen, Qwen strict)", "t379_391_gen"),
    "391": (5, ["URBAN_WASTE_95", "URBAN_WASTE_96", "URBAN_WASTE_97", "INDUSLUM_54", "PORTURBITS_54"],
            "c1031b_391: кучки мусора 97/95/96, Y",
            "XP-000391: кучки мусора URBAN_WASTE 95/96/97 + INDUSLUM:54 + PORTURBITS:54 (t379_391_gen, Qwen strict)", "t379_391_gen"),
    "383": (38, None, "c1031b_383: PORTROADS:23 и боковая лесенка семьёй, 38 кадров, Y",
            "XP-000383: PORTROADS:23 и боковая лесенка, 38 кадров семьёй (t383_gen, Qwen strict)", "t383_gen"),
    "394": (3, ["CULTIVAT_UBER_12", "CULTIVAT_12", "GOTHIC_22"], "c1031b_394: дерево, зерно 3941, Y",
            "XP-000394: дерево CULTIVAT_UBER:12, CULTIVAT:12, GOTHIC:22 (t394_395_gen, Qwen strict)", "t394_395_gen"),
}


def collect(t):
    n, names, _ap, _why, _gen = TICKETS[t]
    cand = os.path.join(ART, "t" + t, "cand")
    if names is None:
        names = sorted(os.path.splitext(f)[0] for f in os.listdir(cand) if f.lower().endswith(".png"))
    files = {}
    for nm in names:
        m = re.fullmatch(r"(.+)_(\d+)", nm)
        files["TERRAIN/%s.PCK/%s.png" % (m.group(1), m.group(2))] = os.path.join(cand, nm + ".png")
    if len(files) != n:
        raise SystemExit("ждали %d кадров, а %d" % (n, len(files)))
    return files


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", required=True, choices=sorted(TICKETS))
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    t = a.ticket
    files = collect(t)
    for rel, p in files.items():
        # with: незакрытый кадр пака держит файл, и os.replace при установке падает (R-567)
        old_p = os.path.join(REPO_PACK, rel)
        if not os.path.exists(old_p):          # набор в копии repo неполный (R-257): размер сверяем с установкой игры
            import build_hd_pack as bp
            old_p = os.path.join(bp.TARGETS["game"], rel)
        with Image.open(p) as im, Image.open(old_p) as old:
            if im.mode != "RGBA" or im.size != old.size:
                raise SystemExit("%s: ждали RGBA %s, а %s %s" % (p, old.size, im.mode, im.size))
    print("тикет %s, файлов к установке: %d" % (t, len(files)))
    for rel in files:
        print("  ", rel)
    if not (a.install and a.yes):
        print("сухой прогон; --install --yes - записать в мод (под очередью правок)")
        return
    import build_hd_pack as bp
    backup = os.path.join(ROOT, "art", "_backup", "t%s_2026-10-31" % t)
    for rel in files:
        dst = os.path.join(backup, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            src = os.path.join(REPO_PACK, rel)
            if not os.path.exists(src):
                src = os.path.join(bp.TARGETS["game"], rel)
            shutil.copyfile(src, dst)
    print("резерв:", backup)
    # R-257: в копии repo нет набора целиком (или он неполный) - ставим набор из манифеста ЦЕЛИКОМ, не только кадры тикета
    man = bp.load()
    for pck in sorted({rel.split("/")[1] for rel in files}):
        want = [k for k in man["files"] if k.startswith("TERRAIN/%s/" % pck)]
        have = os.listdir(os.path.join(REPO_PACK, "TERRAIN", pck)) if os.path.isdir(os.path.join(REPO_PACK, "TERRAIN", pck)) else []
        if len(have) < len(want):
            print("repo: набор %s неполный (%d из %d) - ставлю целиком" % (pck, len(have), len(want)))
            bp.install(man, "repo", only=want)
            have = os.listdir(os.path.join(REPO_PACK, "TERRAIN", pck))
            if len(have) != len(want):
                raise SystemExit("набор %s в repo: %d из %d" % (pck, len(have), len(want)))
    import ticket_scene as ts
    _n, _names, approval, why, gen = TICKETS[t]
    n = ts.install_files(files, "t1031_install", gen, "Vitali 31.10, страница выбора, пункт " + approval, why)
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
