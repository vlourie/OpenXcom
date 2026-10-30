#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка кандидатов тикетов XP-000425, XP-000433, XP-000438 (Vitali 30.10 20:21: «Ставить» на странице выбора).

  425: BASEBITS.PCK/300.png и 300.spin.png (стволы рельсовой ПВО параллельны; art/tickets/t425, t425_proc.py);
  433: лестница лифта, 9 кадров семьи (art/tickets/t433/cand, t433_proc.py);
  438: CADILLAC 3-13, 11 кадров (art/tickets/t438/cand, t438_proc.py).

Через манифест (art/manifest, build_hd_pack: stage + save + install в game и repo + сверка хэшей), резерв прежних файлов -
art/_backup/t425_433_438_20261030/<путь пака>. Для 425 те же два файла ложатся в art/base_living/pilot/painted/STR_GAUSS_DEFENSES.png и
.spin.png (их читает base_scene_pack.py при перепаковке): иначе перепаковка вернёт стволы V. Прежние - в тот же резерв.

    py -3.13 tools\hdart\t425_433_438_install.py            сухой прогон
    py -3.13 tools\hdart\t425_433_438_install.py --yes      установить (под очередью правок)
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

from PIL import Image                        # noqa: E402

BACKUP = os.path.join(ROOT, "art", "_backup", "t425_433_438_20261030")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
PAINTED = os.path.join(ROOT, "art", "base_living", "pilot", "painted")
FAM25 = [("XB3BITZ2", 25), ("METRO1", 67), ("NINJATECH", 69), ("RUSTSHACKS", 49), ("URBAN_WASTE_WALLS", 77)]
FAM26 = [("METRO1", 68), ("RUSTSHACKS", 48), ("URBAN_WASTE", 114), ("URBAN_WASTE_WALLS", 79)]


def collect():
    files = {}
    t425 = os.path.join(ROOT, "art", "tickets", "t425")
    files["BASEBITS.PCK/300.png"] = os.path.join(t425, "300.png")
    files["BASEBITS.PCK/300.spin.png"] = os.path.join(t425, "300.spin.png")
    t433 = os.path.join(ROOT, "art", "tickets", "t433", "cand")
    for s, f in FAM25 + FAM26:
        files["TERRAIN/%s.PCK/%d.png" % (s, f)] = os.path.join(t433, "%s_%d.png" % (s, f))
    t438 = os.path.join(ROOT, "art", "tickets", "t438", "cand")
    for f in range(3, 14):
        files["TERRAIN/CADILLAC.PCK/%d.png" % f] = os.path.join(t438, "%d.png" % f)
    return files


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    yes = "--yes" in sys.argv
    files = collect()
    for rel, p in files.items():
        im = Image.open(p)
        want = (128, 128) if rel.startswith("BASEBITS") else (128, 160)
        if im.size != want or im.mode != "RGBA":
            raise SystemExit("%s: ждали RGBA %s, а %s %s" % (p, want, im.mode, im.size))
    print("файлов к установке: %d" % len(files))
    if not yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (под очередью правок)")
    # резерв прежнего
    for rel in files:
        src = os.path.join(REPO_PACK, rel)
        if os.path.exists(src):
            dst = os.path.join(BACKUP, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                shutil.copyfile(src, dst)
    for name, rel in (("STR_GAUSS_DEFENSES.png", "BASEBITS.PCK/300.png"), ("STR_GAUSS_DEFENSES.spin.png", "BASEBITS.PCK/300.spin.png")):
        src = os.path.join(PAINTED, name)
        dst = os.path.join(BACKUP, "painted", name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            shutil.copyfile(src, dst)
        shutil.copyfile(files[rel], src)       # источник перепаковки base_scene_pack.py - те же пиксели
    print("резерв:", BACKUP)
    import ticket_scene as ts
    n = ts.install_files(files, "t425_433_438_install", "XP-000425/433/438: процедурные кандидаты (t425_proc, t433_proc, t438_proc)",
                         "Vitali: страница выбора, Ставить, 30.10 20:21",
                         "t425 ПВО стволы параллельны; t433 лестница лифта XB3BITZ2:25 и семья; t438 CADILLAC 3-13 ровный контур")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
