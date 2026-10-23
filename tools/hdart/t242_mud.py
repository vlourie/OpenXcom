#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикеты XP-000242 (MOUNTMUD:5, «яркие куски») и XP-000243 (MOUNTMUD:48, «яркий пень») - варианты, выбранные Vitali 23.10.

  242, вариант C: MOUNTMUD:5 и варианты .v1-.v3 - рисунок и альфа текущего HD, цвета по рангу яркости берутся из классики
     (подгонка по гистограмме: тот же материал, но без бледно-жёлтых пятен, которых в классике нет).
     Семья по байтам классики - MOUNTSAND:5 и GOTHIC:5 - не трогается: их HD уже тусклый и годный (разбор 242), а подгонка
     дала бы им тот же результат без пользы; в отчёте они названы.
  243, вариант D: MOUNTMUD:48 - пень MOUNT:50 (хороший), серое основание перекрашено в тон земли MOUNTMUD (средний цвет HD
     MOUNTMUD:0; яркость основания сохраняется). Семья MOUNTMUD:48 уникальна по байтам классики; MOUNT:50 - соседний набор,
     его кадр не меняется.

    py -3.13 tools/hdart/t242_mud.py                  # кадры в art/tickets/t242/out/TERRAIN/MOUNTMUD.PCK
    py -3.13 tools/hdart/t242_mud.py --install --yes  # + в мод hd через манифест (под очередью правок)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts  # noqa: E402

OUT = ROOT / "art" / "tickets" / "t242" / "out" / "TERRAIN" / "MOUNTMUD.PCK"
W = np.array([0.299, 0.587, 0.114])


def hist_match(hd, classic):
    """hd, classic: RGBA PIL 128x160. Форма и альфа HD, цвета - по рангу яркости из классики."""
    h = np.asarray(hd.convert("RGBA")).copy()
    c = np.asarray(classic.convert("RGBA"))
    mh = h[..., 3] > 0
    mc = c[..., 3] > 0
    lh = h[mh][:, :3] @ W
    cc = c[mc][:, :3].astype(float)
    cc_sorted = cc[np.argsort(cc @ W)]
    oh = np.argsort(np.argsort(lh, kind="stable"), kind="stable")
    idx = (oh * (len(cc_sorted) - 1) / max(1, len(lh) - 1)).astype(int)
    res = h.copy()
    res[mh, :3] = cc_sorted[idx].round().astype(np.uint8)
    return Image.fromarray(res, "RGBA")


def recolor_base(src, ref_ground):
    """Серая подложка пня перекрашивается под грязь: яркость сохраняется, тон - средний цвет пола MOUNTMUD:0."""
    a = np.asarray(src.convert("RGBA")).astype(float)
    rgb = a[..., :3]
    mx, mn = rgb.max(-1), rgb.min(-1)
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    w = np.clip((0.30 - s) / 0.15, 0, 1)[..., None]
    g = (rgb @ W)[..., None]
    sel = (a[..., 3] > 128) & (w[..., 0] > 0.5)
    gm = g[sel].mean() if sel.any() else 128
    col = np.clip(np.array(ref_ground, float) * (g / gm), 0, 255)
    out = a.copy()
    out[..., :3] = w * col + (1 - w) * rgb
    return Image.fromarray(out.round().astype(np.uint8), "RGBA")


def build():
    sc = ts.Scene()
    res = {}
    cls5 = sc.classic("MOUNTMUD", 5)
    res["5.png"] = hist_match(sc.hd("MOUNTMUD", 5), cls5)
    for i, v in enumerate(sc.variants("MOUNTMUD", 5), 1):
        res["5.v%d.png" % i] = hist_match(v, cls5)
    g = np.asarray(sc.hd("MOUNTMUD", 0)).reshape(-1, 4)
    ground = g[g[:, 3] > 128][:, :3].mean(0)
    res["48.png"] = recolor_base(sc.hd("MOUNT", 50), ground)
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    res = build()
    OUT.mkdir(parents=True, exist_ok=True)
    files = {}
    for n, im in res.items():
        im.save(OUT / n)
        files["TERRAIN/MOUNTMUD.PCK/" + n] = OUT / n
    print("кадров: %d -> %s" % (len(files), OUT))
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(files, "t242_mud", "t242_mud.py 23.10 MOUNTMUD:5 по гистограмме классики (C), MOUNTMUD:48 пень MOUNT:50 (D)",
                         "Vitali 23.10 (XP-000242 вариант C, XP-000243 вариант D); листы t242_scene_PLAINS12.png, t243_scene_PLAINS00.png",
                         "t242/t243: MOUNTMUD 5 (+v1-v3) по гистограмме, MOUNTMUD 48 пень")
    return 0


if __name__ == "__main__":
    sys.exit(main())
