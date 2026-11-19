#!/usr/bin/env python3
"""Свет вспышек, этап 0 (docs/research/hd-flash-light-2026-10-30.md): сколько света даёт каждый кадр боевых клипов HD.

Светит только яркое: вес пикселя = альфа x max(0, (яркость - порог) / (1 - порог)), яркость - максимум канала.
Кровь, пыль и дым тёмные и почти не светят; огонь, искры и энергия - светят. Для кадра:
  E    - светящая площадь в классических пикселях (сумма весов / 16: клипы лежат в 4x),
  rgb  - цвет света: среднее по весам, нормированное на максимум канала.
Выход: census/flash_light/frames.tsv (кадр за строкой) и сводка по семьям клипов в консоль.

  py -3.13 tools/flash_light_census.py [--fx <папка hd/FX>] [--knee 0.55]
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods" / "hd" / "hd" / "FX"
OUT = ROOT / "census" / "flash_light"
ENC = "utf-8-sig"  # R-001
DARK = ("blood_", "stab_", "swing_", "collapse_")  # не свет: кровь, удары, пыль обрушения


def frame_light(path, knee):
    a = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32) / 255.0
    rgb, alpha = a[..., :3], a[..., 3]
    lum = rgb.max(axis=2)
    w = alpha * np.clip((lum - knee) / (1.0 - knee), 0.0, 1.0)
    s = float(w.sum())
    if s <= 0:
        return 0.0, (0.0, 0.0, 0.0)
    col = (rgb * w[..., None]).reshape(-1, 3).sum(axis=0) / s
    col = col / max(1e-6, float(col.max()))
    return s / 16.0, tuple(round(float(c), 3) for c in col)


def family(clip):
    """boom_plasma_green -> boom_plasma, flash_cannon_3 -> flash_cannon, hit_cal2_metal -> hit_cal2."""
    p = clip.split("_")
    return "_".join(p[:2])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fx", default=str(FX))
    ap.add_argument("--knee", type=float, default=0.55)
    a = ap.parse_args()
    fx = Path(a.fx)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for clip in sorted(p.name for p in fx.iterdir() if p.is_dir()):
        if clip.startswith(DARK):
            continue
        frames = sorted(fx.glob(f"{clip}/*.png"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
        for f in frames:
            e, col = frame_light(f, a.knee)
            rows.append((clip, int(f.stem), round(e, 1), col))
    with open(OUT / "frames.tsv", "w", encoding=ENC) as out:
        out.write("clip\tframe\tE\tr\tg\tb\n")
        for clip, i, e, col in rows:
            out.write(f"{clip}\t{i}\t{e}\t{col[0]}\t{col[1]}\t{col[2]}\n")
    fams = {}
    for clip, i, e, col in rows:
        fams.setdefault(family(clip), []).append((clip, i, e))
    print(f"{'семья':24} {'клипов':>6} {'кадров':>6} {'E пик med':>9} {'E пик max':>9} {'кадр пика':>9}")
    for fam, rs in sorted(fams.items()):
        peaks = {}
        for clip, i, e in rs:
            if e > peaks.get(clip, (-1, 0))[0]:
                peaks[clip] = (e, i)
        pk = sorted(v[0] for v in peaks.values())
        at = sorted(v[1] for v in peaks.values())
        print(f"{fam:24} {len(peaks):6d} {len(rs):6d} {pk[len(pk) // 2]:9.1f} {pk[-1]:9.1f} {at[len(at) // 2]:9d}")
    print("ok", OUT / "frames.tsv", len(rows), "кадров")


if __name__ == "__main__":
    sys.exit(main())
