"""Перепись соседей стен по всем картам: кто стоит рядом с картинкой стены на карте.

Для точного движка стен (wall_exact.py): стена увеличивается не одна, а вместе с соседями так, как они
стоят на карте, - тогда стык двух кадров считается как одна картинка, и шва нет.

Картинка - строка census/walls/wall_render_frames.tsv (хэш классики, все кадры с ней). Для каждого места
картинки на картах (часть клетки 1 west, 2 north, 3 объект; кадр анимации - Frame[0] записи MCD) берутся
стены в клетках вокруг: смещение (dx, dy, dz) в -1..1 и часть 1..3, в том числе другие части той же клетки.
Пол (часть 0) и не-стены (мебель) не берутся. Картинка, которой нет на картах (разрушенный вид, второе
состояние двери), получает соседей той записи, чьим die или alt она является.

  wall_neighbors.py [--out census/walls/exact/neighbors.json]

Выход: {картинка: {"n": мест, "parts": {часть: мест}, "nb": {"dx,dy,dz,часть": {картинка: мест}}}}.
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import map_mockup as mm                             # noqa: E402
import pck_census as pc                             # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(HERE))
FRAMES = "census/walls/wall_render_frames.tsv"


def pictures():
    """'НАБОР:кадр' (набор заглавными) -> картинка."""
    out = {}
    with open(os.path.join(ROOT, FRAMES), encoding=ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            for t in r["кадры"].split():
                s, n = t.rsplit(":", 1)
                out["%s:%s" % (s.upper(), n)] = r["картинка"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="census/walls/exact/neighbors.json")
    a = ap.parse_args()
    os.chdir(ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    pic = pictures()
    world = mm.World()
    n = Counter()
    parts = defaultdict(Counter)
    nb = defaultdict(lambda: defaultdict(Counter))
    inherit = defaultdict(Counter)        # картинка без мест -> картинка записи, чей die/alt она есть
    seen_sets = set()
    t0, blocks = time.time(), 0
    for t in sorted(world.terrains):
        sets = world.sets_of(t)
        sizes = {s: len(world.records(s)) for s in sets}
        for s in sets:
            if s.upper() in seen_sets:
                continue
            seen_sets.add(s.upper())
            recs = world.records(s)
            for r in recs:
                p0 = pic.get("%s:%d" % (s.upper(), r["frame"]))
                if p0 is None:
                    continue
                for link in (r["die"], r["alt"]):
                    if 0 < link < len(recs):
                        p1 = pic.get("%s:%d" % (s.upper(), recs[link]["frame"]))
                        if p1 and p1 != p0:
                            inherit[p1][p0] += 1
                for fr in r["frames"][1:]:              # фазы анимации - соседи кадра 0 записи
                    p1 = pic.get("%s:%d" % (s.upper(), fr))
                    if p1 and p1 != p0:
                        inherit[p1][p0] += 1
        for b in world.blocks_of(t):
            if not world.files.find(os.path.join("MAPS", b + ".MAP")):
                continue
            sx, sy, sz, cells = mm.read_block(world, b)
            blocks += 1
            grid = {}
            for (x, y, z), cell in cells.items():
                for part in (1, 2, 3):
                    v = cell[part]
                    if not v:
                        continue
                    s, rec = pc.resolve(v, sets, sizes)
                    if s is None:
                        continue
                    p = pic.get("%s:%d" % (s.upper(), world.records(s)[rec]["frame"]))
                    if p:
                        grid[(x, y, z, part)] = p
            for (x, y, z, part), p in grid.items():
                n[p] += 1
                parts[p][part] += 1
                for dz in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            for q in (1, 2, 3):
                                if dx == dy == dz == 0 and q == part:
                                    continue
                                o = grid.get((x + dx, y + dy, z + dz, q))
                                if o:
                                    nb[p]["%d,%d,%d,%d,%d" % (part, dx, dy, dz, q)][o] += 1
    out = {}
    for p in set(n) | set(inherit):
        if n[p]:
            out[p] = {"n": n[p], "parts": dict(parts[p]),
                      "nb": {k: dict(c.most_common(8)) for k, c in nb[p].items()}}
    for _round in range(3):                         # die от фазы анимации и т.п. - цепочкой
        for p, srcs in inherit.items():
            if p in out:
                continue
            src = next((q for q, _c in srcs.most_common() if q in out), None)
            if src:
                out[p] = dict(out[src], inherit=out[src].get("inherit", src))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding=ENC) as f:
        json.dump(out, f, ensure_ascii=False)
    print("блоков %d, картинок со соседями %d (по наследству %d) из %d, %.0f с" % (
        blocks, len(out), sum(1 for v in out.values() if "inherit" in v), len(set(pic.values())),
        time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
