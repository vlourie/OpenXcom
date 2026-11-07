#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000410: трава тропиков, кандидат A (зёрна G4401S4411), выбор Vitali 30.10. Вся семья одним разом:
MOUNTTROP 0-3 (+ .v1-.v3 у каждого) и FORESTRED:4 - 17 файлов из art/tickets/t410/cand/G4401S4411/.
Ставит через ticket_scene.install_files: манифест, обе копии мода hd, сверка хэшей. Прежние кадры остаются в хранилище
art/store/blobs (по sha из поля replaced манифеста) и в art/manifest/history; кроме того копируются в
art/_backup/t410_before/.

    py -3.13 tools\hdart\t410_install.py                 # проверка
    py -3.13 tools\hdart\t410_install.py --install --yes # под очередью правок
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts   # noqa: E402

SRC = ROOT / "art" / "tickets" / "t410" / "cand" / "G4401S4411"


def rel_of(name):
    m = re.match(r"^(.+)_(\d+)(\.v\d+)?\.png$", name)
    if not m:
        raise SystemExit("странное имя: " + name)
    return "TERRAIN/%s.PCK/%d%s.png" % (m.group(1), int(m.group(2)), m.group(3) or "")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files = {}
    for p in sorted(SRC.glob("*.png")):
        im = Image.open(p)
        assert im.size == (128, 160) and im.mode == "RGBA", (p, im.size, im.mode)
        files[rel_of(p.name)] = p
    assert len(files) == 17, len(files)
    for rel in files:
        print(rel)
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        bk = ROOT / "art" / "_backup" / "t410_before"
        root = ROOT / "user" / "mods" / "hd" / "hd"
        for rel in files:
            src = root / rel
            if src.exists():
                dst = bk / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    shutil.copyfile(src, dst)
        ts.install_files(files, "t410_grass", "t410_build.py 30.10 зёрна G4401S4411 (поля травы 4401, земли 4411), ковёр .v1-.v3",
                         "Vitali 30.10 (XP-000410 трава тропиков, кандидат A G4401S4411, варианты ковра .v1-.v3)",
                         "t410: трава тропиков MOUNTTROP 0-3 (+.v1-.v3) и FORESTRED:4, кандидат A")
    return 0


if __name__ == "__main__":
    sys.exit(main())
