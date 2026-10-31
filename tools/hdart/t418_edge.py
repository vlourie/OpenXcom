#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000418: чьи зубцы на нижней кромке будки. Сцена (ticket_scene.Scene, HD из установленного пака) с «вычитанием»: рисуется
весь блок, потом то же без выбранных клеток/частей; разница по кромке показывает, кто закрывает будку.
  render_skip(sc, terrain, block, k, skip, override, maxz) - как Scene.render (mode hd), но пропускает (x, y, z, part), где skip истинно."""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ticket_scene as ts            # noqa: E402
import map_mockup as mm              # noqa: E402
import pck_census as pc              # noqa: E402

BASE = ("PORTROADS", 34)


def render_skip(sc, terrain, block, k, skip, override=None, maxz=0, classic=False):
    override = override or {}
    sets = sc.w.sets_of(terrain)
    sizes = {s: len(sc.w.records(s)) for s in sets}
    sx, sy, sz, cells = mm.read_block(sc.w, block)
    wd = (sx + sy) * 16 + 32
    ht = (sx + sy) * 8 + sz * 24 + 40 + 16
    ox, oy = sy * 16, sz * 24 + 8
    im = Image.new("RGBA", (wd * k, ht * k), ts.BG + (255,))
    for z in range(min(sz, maxz + 1)):
        for y in range(sy):
            for x in range(sx):
                cell = cells.get((x, y, z))
                if not cell:
                    continue
                for part in range(4):
                    v = cell[part]
                    if not v or skip(x, y, z, part):
                        continue
                    s, rec = pc.resolve(v, sets, sizes)
                    if s is None:
                        continue
                    r = sc.w.records(s)[rec]
                    fr, S = r["frame"], s.upper()
                    spr = None if classic else override.get((S, fr))
                    if spr is None and not classic:
                        spr = sc.hd(S, fr)
                    if spr is None:
                        spr = sc.classic(S, fr)
                    if spr.width != 32 * k:
                        spr = spr.resize((32 * k, 40 * k), Image.NEAREST if classic else Image.LANCZOS)
                    px = ox + (x - y) * 16
                    py = oy + (x + y) * 8 - z * 24 - r["p_level"]
                    im.alpha_composite(spr, (px * k, py * k))
    return im
