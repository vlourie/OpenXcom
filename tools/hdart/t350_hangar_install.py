#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000350, ангар живой базы (Vitali 28.10, вариант B): вместо кольца из 12 бегущих огней - пульсация четырёх стрелок
площадки (вид огня swell, VIDEO_LIGHTS["STR_HANGAR"] в base_scene_pack.py); жёлтые огни по углам остались.

Сцены клеток ангара (кадры BASEBITS 9-12) собираются в art/base_living/pack_t350 и ставятся в мод hd в обе копии
(установка Пираток и user/mods/hd) через манифест; в манифест идут только файлы, чьи байты изменились.
Движок со swell - сборка с этой же правки: пак ставить последним шагом перед editq done (R-464).

    py -3.13 tools\hdart\t350_hangar_install.py          # сухой прогон: что изменится, ничего не пишет
    py -3.13 tools\hdart\t350_hangar_install.py --yes    # в мод (под очередью правок editq)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)

import base_scene_pack as sp                         # noqa: E402
import build_hd_pack as bp                           # noqa: E402

TYPE = "STR_HANGAR"
OUT = os.path.join("art", "base_living", "pack_t350")
APPROVAL = "Vitali 28.10, тикет XP-000350: вариант B - пульсация стрелок площадки вместо бегущего кольца ангара"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="поставить в игру и в репозиторий")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    rules, _ = sp.load_rules()
    sprites = sp.sprites_map()
    rels = sp.build(TYPE, rules[TYPE], sprites, a.out, 0.6, 0, sp.ART)
    man = bp.load()
    files = {}
    for rel in rels:
        p = os.path.join(a.out, "hd", rel)
        if man["files"].get(rel, {}).get("sha256") != bp.sha256_file(p):
            files[rel] = p
            print("  изменён:", rel)
    print("файлов в сцене %d, изменилось %d" % (len(rels), len(files)))
    if not a.yes or not files:
        return 0
    import ticket_scene as ts
    n = ts.install_files(files, "base_scene_pack.py", "2026-10-28 xp350", APPROVAL,
                         "живая база XP-000350: ангар - пульсация стрелок вместо бегущего кольца")
    print("установлено файлов: %d" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
