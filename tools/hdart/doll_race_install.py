#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Принятые слои куклы расы - в мод hd: тела, головы и волосы (art/doll/pipe_pilot/<раса>/heads/layers) в hd/UI.

Только по слову Vitali (арт сначала показать). Ставится через манифест build_hd_pack в обе копии мода.
Без .pal.txt: перекраска множителем даёт на кукле сиреневые пятна (R-634). Кукла в HD только при картинке у всех
её слоёв, поэтому слой чужого имени - отказ: без образа в рулсетах движок его не покажет.
Без --yes - сухой прогон: что изменится. Ставить под очередью правок (py -3.13 tools/editq.py wait ...).

    py -3.13 tools/hdart/doll_race_install.py --race fhuman --approval "Vitali 05.11: ..."
    py -3.13 tools/hdart/doll_race_install.py --race fhuman --approval "Vitali 05.11: ..." --yes
UBERGAL рисовался раньше и лежит в другой папке (art/doll/pipe_pilot/layers), остальные расы - как fhuman.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

import build_hd_pack as bp                           # noqa: E402
import doll_b2_render as db                          # noqa: E402
import doll_layers_rul as dl                         # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--race", required=True)
    ap.add_argument("--approval", required=True, help="чьё слово и когда - попадает в манифест")
    ap.add_argument("--yes", action="store_true", help="записать в манифест и поставить в игру и в репозиторий")
    a = ap.parse_args()
    src = os.path.join("art", "doll", "pipe_pilot", a.race.lower(), "heads", "layers")
    generator = "doll_race_heads.py"
    if a.race.lower() == "ubergal":
        src = os.path.join("art", "doll", "pipe_pilot", "layers")
        generator = "doll_pipe_pilot.py"
    if a.race.lower() == "armor_solo":              # брони одним слоем: выбранные сиды Vitali
        src = os.path.join("art", "doll", "pipe_pilot", "armor_solo", "chosen")
        generator = "doll_armor_solo.py"
    if a.race.lower() == "armor_over":              # брони из нескольких вещей: выбранные сиды Vitali
        src = os.path.join("art", "doll", "pipe_pilot", "armor_over", "chosen")
        generator = "doll_armor_over.py"
    if a.race.lower() in ("armor_batch", "armor_fhuman", "armor_mhuman", "armor_nekomimi", "armor_loknar", "armor_ogre", "armor_hybrid"):   # пачка броней поверх тел: запечатанные слои
        src = os.path.join("art", "doll", "pipe_pilot", a.race.lower(), "chosen")
        generator = "doll_armor_batch.py"
    if a.race.lower() == "ubergal_pasties":         # тела без кружков и круги слоем, выбор Vitali 06.11
        src = os.path.join("art", "doll", "pipe_pilot", "pasties_uber", "chosen")
        generator = "doll_ubergal_pasties.py"
    files = sorted(f for f in os.listdir(src) if f.endswith(".png"))
    if a.race.lower() == "ubergal":                 # тела теперь чистые, их ставит ubergal_pasties
        clean = set(os.listdir(os.path.join("art", "doll", "pipe_pilot", "pasties_uber", "chosen")))
        files = [f for f in files if f not in clean]
    images ={k.lower() for k in set(db.sprite_files()) | dl.layer_names()}
    alien = [f for f in files if f[:-4] not in images]
    if alien:
        raise SystemExit("нет образа в рулсетах: %d, например %s" % (len(alien), alien[:5]))
    man = bp.load()
    changed = []
    for f in files:
        rel = "UI/" + f
        if bp.sha256_file(os.path.join(src, f)) != man["files"].get(rel, {}).get("sha256"):
            changed.append(rel)
    print("слоёв %d, изменилось %d" % (len(files), len(changed)))
    if not a.yes or not changed:
        return 0
    for rel in changed:
        bp.stage(man, rel, os.path.join(src, rel[3:]), generator=generator, generator_version="2026-11-05",
                 source_path=src.replace(os.sep, "/"), approved=True, approval=a.approval, family="doll_" + a.race.lower())
    bp.save(man, why="куклы %s: %d слоёв" % (a.race, len(changed)))
    print("game:", bp.install(man, "game", only=changed))
    print("repo:", bp.install(man, "repo", only=changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
