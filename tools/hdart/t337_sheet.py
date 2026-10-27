#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000337: листы разбора в art/_review/xp337 - пары коек в сборе (классика / HD сейчас / варианты) и срезы блоков
XBASE/XBR_131 и LAMIA_VILLAGE/LAM_VILLAGE_E01 с каждым вариантом. Кадры вариантов - art/tickets/t337/cand (t337_probe.py);
если их нет, считаются на лету. В мод ничего не ставится.

    py -3.13 tools\hdart\t337_sheet.py
Листы (art/_review/xp337):
  t337_variants.png        пары на две клетки в сборе: XB1BR 52+53, LAM_BASE2 14+12, 19+18 - классика / HD сейчас / A / B / C
  t337_cut_XBR_131.png     срез спального блока XBASE/XBR_131 (игровая раскладка, x4) - то же пятью колонками
  t337_cut_LAM_E01.png     срез LAMIA_VILLAGE/LAM_VILLAGE_E01 (там стоят пары 12/14 и 18/19)
  t337_block_XBR_131.png, t337_block_LAM_E01.png   блоки целиком (x2)
"""
import os
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)
import ticket_scene as ts  # noqa: E402
import t337_probe as pr  # noqa: E402

REV = ROOT / "art" / "_review" / "xp337"
SHOW = 8    # масштаб пары в сборе на листе: 48x48 базы x 8 = 384


def load_variants(sc):
    res = {}
    for v, d in pr.VDIR.items():
        frames = {}
        for pair, spec in pr.PAIRS.items():
            for s, f, _ox, _oy in spec["cells"]:
                p = pr.CAND / d / ("%s_%d.png" % (s, f))
                if not p.exists():
                    return pr.build(sc)
                frames[(s, f)] = Image.open(p).convert("RGBA")
        res[v] = frames
    return res


def hd_now(sc, pair):
    return {(s, f): sc.hd(s, f) for s, f, _a, _b in pr.PAIRS[pair]["cells"]}


def classic_now(sc, pair):
    return {(s, f): sc.classic(s, f) for s, f, _a, _b in pr.PAIRS[pair]["cells"]}


def pair_panel(frames, pair, k=SHOW):
    im = pr.assemble(frames, pair, 4)
    return im.resize((pr.CW * k, pr.CH * k), Image.LANCZOS)


def local_window(found, w, h, near=70):
    """Окно (в пикселях x4) вокруг клеток коек, ближайших к центру их облака (а не вокруг всех сразу).
    found - от find_cells (рисует k=1, прямоугольники в пикселях базы)."""
    cs = [((f[2][0] + f[2][2]) / 2, (f[2][1] + f[2][3]) / 2) for f in found]
    mx = sorted(c[0] for c in cs)[len(cs) // 2]
    my = sorted(c[1] for c in cs)[len(cs) // 2]
    a = min(found, key=lambda f: (((f[2][0] + f[2][2]) / 2 - mx) ** 2 + ((f[2][1] + f[2][3]) / 2 - my) ** 2))
    ax, ay = (a[2][0] + a[2][2]) / 2, (a[2][1] + a[2][3]) / 2
    sel = [f for f, c in zip(found, cs) if abs(c[0] - ax) < near and abs(c[1] - ay) < near]
    return tuple(v * 4 for v in ts.window(sel, w, h, 1))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sc = ts.Scene()
    REV.mkdir(parents=True, exist_ok=True)
    res = load_variants(sc)
    names = [("классика", None), ("HD сейчас", "now")] + [("вариант " + pr.VARIANTS[v], v) for v in "ABC"]
    # --- пары в сборе
    panels = []
    for pair, spec in pr.PAIRS.items():
        for t, key in names:
            fr = classic_now(sc, pair) if key is None else hd_now(sc, pair) if key == "now" else res[key]
            panels.append(("%s - %s" % (spec["label"], t), pair_panel(fr, pair)))
    ts.sheet(panels, REV / "t337_variants.png", cols=5)
    # --- срезы блоков (игровая раскладка, k=4) и блок целиком (k=2)
    ov = {v: {(s.upper(), f): im for (s, f), im in res[v].items()} for v in res}
    cases = [("XBASE", "XBR_131", [("XB1BR", 52), ("XB1BR", 53)], "XBR_131", "XBR_131", 150, 90, None),
             ("LAMIA_VILLAGE", "LAM_VILLAGE_E01",
              [("LAM_BASE2", 12), ("LAM_BASE2", 14), ("LAM_BASE2", 18), ("LAM_BASE2", 19)], "LAM_VILLAGE_E01", "LAM_E01", 150, 90, 1)]    # у деревни ламий койки на z=1 под скалой: уровни выше не рисуем
    for terrain, block, keys, short, tag, w, h, maxz in cases:
        found = ts.find_cells(sc, terrain, block, keys)
        box = local_window(found, w, h)
        pan, whole = [], []
        for t, key in names:
            o = None if key in (None, "now") else ov[key]
            mode = "classic" if key is None else "hd"
            im, _ = sc.render(terrain, block, mode, override=o, k=4, maxz=maxz)
            pan.append(("%s - %s" % (short, t), ts.crop_pad(im, box)))
            whole.append((short + " - " + t, im.resize((im.width // 2, im.height // 2), Image.LANCZOS)))
        ts.sheet(pan, REV / ("t337_cut_%s.png" % tag), cols=3)
        ts.sheet(whole, REV / ("t337_block_%s.png" % tag), cols=3)
    print("листы:", REV)


if __name__ == "__main__":
    main()
