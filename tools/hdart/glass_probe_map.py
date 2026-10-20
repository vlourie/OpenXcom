"""Проба стекла кабины на настоящей карте корабля (к glass_alpha.py): блок раскладывается map_mockup.render
из HD-пака игры, где у выбранных кадров стекло (apply_object, холодный цвет) сделано полупрозрачным, - видно,
что движок нарисует за стеклом: салон с клеток позади или пустоту. Пишет только в art/_review/glass/maps/.

  glass_probe_map.py --block KITSUNE --frames KITSUNE:7 [--terrain FIREFOX] [--level 1]
"""
import argparse
import os
import shutil
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import glass_alpha as ga  # noqa: E402
import map_mockup as mm  # noqa: E402

OUT = os.path.join(ga.REVIEW, "maps")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", required=True)
    ap.add_argument("--terrain")
    ap.add_argument("--frames", nargs="+", required=True, help="НАБОР:кадр[@с-по] - стекло по холодному цвету")
    ap.add_argument("--level", type=int)
    ap.add_argument("--k", type=int, default=2)
    a = ap.parse_args()
    os.chdir(ga.ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    world = mm.World()
    t = mm.terrain_for(world, a.block, a.terrain)
    game = os.path.join(ga.GAME, "TERRAIN")
    src = os.path.join(OUT, "_src_" + a.block)
    if os.path.isdir(src):
        shutil.rmtree(src)
    for s in world.sets_of(t):
        d = os.path.join(game, s.upper() + ".PCK")
        if os.path.isdir(d):
            shutil.copytree(d, os.path.join(src, s.upper() + ".PCK"))
    for spec in a.frames:
        key, _, rows = spec.partition("@")
        s, f = key.rsplit(":", 1)
        rows = tuple(int(v) for v in rows.split("-")) if rows else None
        p = os.path.join(src, s.upper() + ".PCK", "%s.png" % f)
        hd = np.array(Image.open(p).convert("RGBA"))
        new, n = ga.apply_object(hd, rows)
        Image.fromarray(new, "RGBA").save(p)
        print(key, "пикселей стекла", n)
    before, _ = mm.render(world, t, a.block, os.path.join(game), k=a.k, maxz=a.level)
    after, _ = mm.render(world, t, a.block, src, k=a.k, maxz=a.level)
    w, h = before.size
    sheet = Image.new("RGBA", (w * 2 + 8, h), (20, 20, 20, 255))
    sheet.paste(before, (0, 0))
    sheet.paste(after, (w + 8, 0))
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, "%s__%s.png" % (t, a.block))
    sheet.save(out)
    shutil.rmtree(src)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
