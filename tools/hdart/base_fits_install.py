#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Живая база 22.10: приступы построек (тикеты XP-000237..245) и ракетная шахта стоймя (XP-000254) - в мод hd.

Приступы: строки cycle/glow/lid/sink/burst, которые пишет base_scene_pack.py (CYCLE, GLOW, LID, SINK, BURST),
понимает HdBaseScene с той же правки. Шахта: Vitali 22.10 выбрал сид 6300 с листа art/tickets/t254/silo_sheet.png
(«последняя самая лучшая») - картинка art/base_living/pilot/painted_silo6300/ встаёт в painted/, прежняя уходит
в art/_backup/painted_silo_<время>/.

Пак собирается в art/base_living/pack_fits (не в общий pack), в манифест идут только файлы, чьи байты
изменились, - у прочих происхождение не трогается. Без --yes - сухой прогон: что изменится. Ставить под
очередью правок (py -3.13 tools/editq.py wait ...).

    py -3.13 tools/hdart/base_fits_install.py
    py -3.13 tools/hdart/base_fits_install.py --yes
"""
import argparse
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

import base_scene_pack as sp                         # noqa: E402
import build_hd_pack as bp                           # noqa: E402

FITS = ["STR_GRAV_SHIELD", "STR_FUSION_BALL_DEFENSES", "STR_LASER_DEFENSES", "STR_GAUSS_DEFENSES",
        "STR_EYE_OF_HORUS", "STR_HYPER_WAVE_DECODER", "STR_ACCESS_LIFT", "STR_SAM_DEFENSES"]
SILO = "STR_MISSILE_DEFENSES"
SILO_SRC = os.path.join("art", "base_living", "pilot", "painted_silo6300")
OUT = os.path.join("art", "base_living", "pack_fits")
APPROVAL = {
    "fits": "тикеты XP-000237..245 (командир тикетов 22.10); Vitali 22.10 «живая база - картбланш», плазменная без "
            "приступа («пучок синего света»)",
    "silo": "Vitali 22.10 t254: «последняя самая лучшая» - сид 6300, art/tickets/t254/silo_sheet.png",
}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="записать в манифест и поставить в игру и в репозиторий")
    a = ap.parse_args()
    for t in FITS:
        missing = [k for k, d in (("CYCLE", sp.CYCLE),) if t not in d]
        if missing:
            raise SystemExit("%s: нет в %s - черновик base_scene_pack.py не тот" % (t, missing))
    if "STR_PLASMA_DEFENSES" in sp.CYCLE or "STR_PLASMA_DEFENSES" in sp.SPIN:
        raise SystemExit("плазменной не качаться и без приступа (тикет 238 закрыт пучком)")
    painted = sp.ART
    for name in (SILO + ".png", SILO + "@512.png"):
        src, dst = os.path.join(SILO_SRC, name), os.path.join(painted, name)
        if bp.sha256_file(src) == bp.sha256_file(dst):
            continue
        print("шахта:", src, "->", dst)
        if a.yes:
            keep = os.path.join("art", "_backup", "painted_silo_" + time.strftime("%Y%m%d_%H%M%S"))
            os.makedirs(keep, exist_ok=True)
            shutil.copyfile(dst, os.path.join(keep, name))
            shutil.copyfile(src, dst)
    if not a.yes and bp.sha256_file(os.path.join(SILO_SRC, SILO + "@512.png")) != bp.sha256_file(
            os.path.join(painted, SILO + "@512.png")):
        print("сухой прогон: шахта собирается из прежней картинки, новая встанет с --yes")
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    rules, _ = sp.load_rules()
    sprites = sp.sprites_map()
    plan = []
    for t in FITS + [SILO]:
        for rel in sp.build(t, rules[t], sprites, OUT, 0.6, 0, painted):
            plan.append((t, rel))
    man = bp.load()
    changed = []
    for t, rel in plan:
        p = os.path.join(OUT, "hd", rel)
        old = man["files"].get(rel, {}).get("sha256")
        if bp.sha256_file(p) != old:
            changed.append((t, rel, p))
            print("  %-26s %-28s %s" % (t, rel, "новый" if not old else "изменён"))
    print("файлов %d, изменилось %d" % (len(plan), len(changed)))
    if not a.yes or not changed:
        return 0
    for t, rel, p in changed:
        bp.stage(man, rel, p, generator="base_scene_pack.py", generator_version="2026-10-22 fits",
                 source_path=(SILO_SRC if t == SILO else painted).replace(os.sep, "/"), approved=True,
                 approval=APPROVAL["silo" if t == SILO else "fits"], family="base_living",
                 source_frame=man["files"].get(rel, {}).get("source_frame") or "BASEBITS:" + rel.split("/")[1].split(".")[0])
    rels = [rel for _t, rel, _p in changed]
    bp.save(man, why="живая база: приступы 237-245 и шахта t254 - %d файлов" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    return 0


if __name__ == "__main__":
    sys.exit(main())
