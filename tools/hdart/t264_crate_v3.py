#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000264: ящик CONTAINERS:2 и DOOM_BASE2:9 - третий проход, вариант 1 (зерно 26421), выбор Vitali 23.10.

Кадр: art/tickets/t264v3/gen/series/CONTAINERS.PCK/2_26421.png (видеокарта не нужна). Семья (ticket_family.py CONTAINERS:2):
DOOM_BASE2:9 - побайтная копия классики. Тон: у члена сдвиг хромы среднего Lab классики набора относительно CONTAINERS:2
(в классике они побайтно равны, сдвиг получается нулевой - печатается).

    py -3.13 tools/hdart/t264_crate_v3.py                  # кадры в art/tickets/t264v3/out/TERRAIN/...
    py -3.13 tools/hdart/t264_crate_v3.py --install --yes  # + в мод hd через манифест (под очередью правок)
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts   # noqa: E402
import water_build as wb    # noqa: E402

SRC = ROOT / "art" / "tickets" / "t264v3" / "gen" / "series" / "CONTAINERS.PCK" / "2_26421.png"
OUT = ROOT / "art" / "tickets" / "t264v3" / "out"
FAMILY = [("CONTAINERS", 2), ("DOOM_BASE2", 9)]


def lab(rgb):
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.float32) / 255, cv2.COLOR_RGB2Lab)


def unlab(x):
    return np.clip(cv2.cvtColor(x.astype(np.float32), cv2.COLOR_Lab2RGB) * 255, 0, 255)


def classic_lab(s, f):
    cl = wb.read_set(s)[f]
    pal = wb.palette()
    return lab(pal[cl[cl > 0]][..., :3].astype(np.float32).reshape(-1, 1, 3)).reshape(-1, 3).mean(0)


def build_all():
    base = np.asarray(Image.open(SRC).convert("RGBA")).astype(np.float32)
    c0 = classic_lab(*FAMILY[0])
    res = {FAMILY[0]: base}
    for s, f in FAMILY[1:]:
        d = classic_lab(s, f) - c0
        d[0] = 0.0
        print("%s:%d сдвиг хромы по классике: a %.3f b %.3f" % (s, f, d[1], d[2]))
        r = base.copy()
        if np.abs(d).max() > 1e-6:
            r[..., :3] = unlab(lab(base[..., :3]) + d)
        res[(s, f)] = r
    return res


def save_all(res):
    paths = {}
    for (s, f), p in res.items():
        d = OUT / "TERRAIN" / (s + ".PCK")
        d.mkdir(parents=True, exist_ok=True)
        q = d / ("%d.png" % f)
        Image.fromarray(np.clip(p, 0, 255).round().astype(np.uint8), "RGBA").save(q)
        paths["TERRAIN/%s.PCK/%d.png" % (s, f)] = q
    return paths


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    paths = save_all(build_all())
    print("кадров: %d -> %s" % (len(paths), OUT))
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(paths, "t264_crate_v3", "t264_crate_v3.py 23.10 третий проход, вариант 1 (зерно 26421)",
                         "Vitali 23.10 (XP-000264 ящик, третий проход, вариант 1, зерно 26421)",
                         "t264: ящик CONTAINERS 2 и DOOM_BASE2 9 - вариант 1 третьего прохода")
    return 0


if __name__ == "__main__":
    sys.exit(main())
