#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000259: стена URBANWAR:70 — назад на вариант B2, в обе копии мода hd через манифест.

На кадре нарисован фасад: окно, пожарная лестница, ворота (wall_exact_C, 15.10, R-294). У классики там
обгоревшая стена без деталей. Vitali 22.10 выбрал откат на B2 с листа art/_review/tickets_2026-10-22/t259_sheet.png.
Ставить под очередью правок.

    py -3.13 tools/hdart/t259_wall_b2.py
    py -3.13 tools/hdart/t259_wall_b2.py --yes
"""
import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(os.path.dirname(os.path.dirname(HERE)))

import build_hd_pack as bp                           # noqa: E402

SRC = os.path.join("census", "walls", "exact", "render", "b2", "120ea0b18597767d.png")
REL = "TERRAIN/URBANWAR.PCK/70.png"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="записать в манифест и поставить в игру и в репозиторий")
    a = ap.parse_args()
    man = bp.load()
    old = man["files"].get(REL, {})
    new = bp.sha256_file(SRC)
    print("%s: %s -> %s (%s)" % (REL, old.get("sha256", "-")[:12], new[:12], SRC))
    if old.get("sha256") == new:
        print("уже B2")
        return 0
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод")
    bp.stage(man, REL, SRC, generator="wall_exact_B2", generator_version="census/walls/exact b2, откат t259 22.10",
             source_path=SRC.replace(os.sep, "/"), approved=True,
             approval="Vitali 22.10 t259: «Откатить на прошлую версию (B2)», art/_review/tickets_2026-10-22/t259_sheet.png")
    bp.save(man, why="t259: URBANWAR:70 назад на B2 - без нарисованного фасада")
    print("game:", bp.install(man, "game", only=[REL]))
    print("repo:", bp.install(man, "repo", only=[REL]))
    for root in bp.TARGETS.values():
        with open(os.path.join(root, REL), "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != new:
                raise SystemExit("РАСХОДИТСЯ %s %s" % (root, REL))
    print("сверено: обе копии")
    return 0


if __name__ == "__main__":
    sys.exit(main())
