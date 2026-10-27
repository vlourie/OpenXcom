#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Живая база, тикет XP-000336 (27.10): сцены восьми построек по решению Vitali (вариант A у каждой) - в мод hd.

Мастерская, фабрика, принтер, Монетный двор, электростанция, Красная Кузня, алениевая камера и казино: движения
ленты, каретки, валика, дыхание металла, огни вывески, свечение камеры (таблицы блока XP336 base_scene_pack.py) и
места экипажа - строки post (инженеры у лент, дилеры и игроки у столов казино).

Пак собирается в art/base_living/pack_t336 (не в общий pack), в манифест идут только файлы, чьи байты изменились.
Без --yes - сухой прогон: что изменится. Ставить под очередью правок (py -3.13 tools/editq.py wait ...).
Дополнительно к восьми - постройки из EXTRA (то, что придумано сверх выбора Vitali): --extra.

    py -3.13 tools/hdart/base_live_install.py
    py -3.13 tools/hdart/base_live_install.py --yes
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

import base_scene_pack as sp                         # noqa: E402
import build_hd_pack as bp                           # noqa: E402

TYPES = ["STR_WORKSHOP", "STR_FACTORY", "STR_INDUSTRIAL_PRINTER", "STR_MINT", "STR_POWER_PLANT", "STR_RED_FORGE",
         "STR_ALENIUM_CHAMBER", "STR_CASINO"]
EXTRA = list(getattr(sp, "EXTRA_TYPES", []))
OUT = os.path.join("art", "base_living", "pack_t336")
APPROVAL = ("Vitali 27.10 по тикету XP-000336 (живая база): вариант A у мастерской, фабрики, принтера, Монетного двора, "
            "электростанции, Красной Кузни, алениевой камеры и казино; люди у конвейера и у столов казино")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="записать в манифест и поставить в игру и в репозиторий")
    ap.add_argument("--extra", action="store_true", help="и постройки сверх выбора Vitali (EXTRA_TYPES)")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    types = TYPES + (EXTRA if a.extra else [])
    import shutil
    if os.path.isdir(a.out):
        shutil.rmtree(a.out)
    rules, _ = sp.load_rules()
    sprites = sp.sprites_map()
    plan = []
    for t in types:
        for rel in sp.build(t, rules[t], sprites, a.out, 0.6, 0, sp.ART):
            plan.append((t, rel))
    man = bp.load()
    changed = []
    for t, rel in plan:
        p = os.path.join(a.out, "hd", rel)
        old = man["files"].get(rel, {}).get("sha256")
        if bp.sha256_file(p) != old:
            changed.append((t, rel, p))
            print("  %-26s %-28s %s" % (t, rel, "новый" if not old else "изменён"))
    print("файлов %d, изменилось %d" % (len(plan), len(changed)))
    if not a.yes or not changed:
        return 0
    for t, rel, p in changed:
        bp.stage(man, rel, p, generator="base_scene_pack.py", generator_version="2026-10-27 xp336",
                 source_path=sp.ART.replace(os.sep, "/"), approved=True, approval=APPROVAL, family="base_living",
                 source_frame=man["files"].get(rel, {}).get("source_frame") or "BASEBITS:" + rel.split("/")[1].split(".")[0])
    rels = [rel for _t, rel, _p in changed]
    bp.save(man, why="живая база XP-000336: сцены 8 построек и места экипажа - %d файлов" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    return 0


if __name__ == "__main__":
    sys.exit(main())
