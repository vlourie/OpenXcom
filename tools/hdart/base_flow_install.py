#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Живая база 23.10 (раздел 11 docs/research/base-living-2026-10-22.md, выбор Vitali: вода A, трубы «все»,
лаборатория A) - в мод hd.

Стоящие сцены не собираются заново (огни из игры сохранены, как у install_emits.py): в .scene.txt клеток
правятся только строки этой работы, остальное - байт в байт.
    трубы      строки flow и карты <N>.flow.png (base_flow_bake.py); у декодера уходит glow - вместо него
               сгустки по кабелям в тот же приступ (cycle 60 10)
    вода       пруд метасада (503) - строка water с меньшим прудом (200 пикселей пака у него нет)
    лаборатория  искры GDX-лаборатории (385) убраны: учёные работают руками (HdBaseLife)

Выход - art/base_living/pack_flow, в манифест идут только изменившиеся файлы. Без --yes - сухой прогон.
Ставить под очередью правок (py -3.13 tools/editq.py wait ...).

    py -3.13 tools/hdart/base_flow_install.py
    py -3.13 tools/hdart/base_flow_install.py --yes
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

import base_flow_bake as fb                           # noqa: E402
import build_hd_pack as bp                            # noqa: E402

OUT = os.path.join("art", "base_living", "pack_flow")
SRC = fb.PACK
METAGARDEN = 503
POND = "water blue 0.75 1.00 1.00 100"
GDX = 385
DECODER = 32
APPROVAL = ("Vitali 23.10 на странице выбора живой базы: вода A, трубы «все», лаборатория A "
            "(docs/research/base-living-2026-10-22.md, раздел 11)")


def edit(n, lines, flow):
    """Строки сцены клетки n после этой работы."""
    out = []
    for ln in lines:
        w = ln.split()
        if not w:
            continue
        if w[0] == "flow":
            continue
        if n == DECODER and w[0] == "glow":
            continue
        if n == GDX and w[:2] == ["emit", "sparks"]:
            continue
        if n == METAGARDEN and w[0] == "water":
            continue
        out.append(ln)
    extra = []
    if flow:
        extra.append(flow)
    if n == METAGARDEN:
        extra.append(POND)
    # перед строкой walk - она последняя у сборщика
    at = next((i for i, ln in enumerate(out) if ln.startswith("walk ")), len(out))
    return out[:at] + extra + out[at:]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="записать в манифест и поставить в игру и в репозиторий")
    a = ap.parse_args()
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    flows = fb.write(list(fb.FLOW), OUT)
    dest = os.path.join(OUT, "hd", "BASEBITS.PCK")
    plan = ["BASEBITS.PCK/%d.flow.png" % n for n in flows]
    for n in sorted(set(flows) | {METAGARDEN, GDX, DECODER}):
        with open(os.path.join(SRC, "%d.scene.txt" % n), encoding="ascii") as f:
            lines = f.read().splitlines()
        new = edit(n, lines, flows.get(n))
        with open(os.path.join(dest, "%d.scene.txt" % n), "w", encoding="ascii", newline="\n") as f:
            f.write("\n".join(new) + "\n")
        plan.append("BASEBITS.PCK/%d.scene.txt" % n)
    man = bp.load()
    changed = []
    for rel in plan:
        p = os.path.join(OUT, "hd", rel)
        old = man["files"].get(rel, {}).get("sha256")
        if bp.sha256_file(p) != old:
            changed.append((rel, p))
            print("  %-30s %s" % (rel, "новый" if not old else "изменён"))
    print("файлов %d, изменилось %d" % (len(plan), len(changed)))
    if not a.yes or not changed:
        return 0
    for rel, p in changed:
        flow = rel.endswith(".flow.png")
        bp.stage(man, rel, p, generator="base_flow_bake.py" if flow else "base_flow_install.py",
                 generator_version="2026-10-23 water-pipes-lab", source_path=SRC.replace(os.sep, "/"), approved=True,
                 approval=APPROVAL, family="base_living",
                 source_frame=man["files"].get(rel, {}).get("source_frame") or "BASEBITS:" + rel.split("/")[1].split(".")[0])
    rels = [rel for rel, _p in changed]
    bp.save(man, why="живая база: вода A, трубы, лаборатория A - %d файлов" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    return 0


if __name__ == "__main__":
    sys.exit(main())
