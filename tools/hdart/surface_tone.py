"""Тон кадров пака (копия мода hd в установке, её читает игра - R-087) против классики по группе покрытий.
Кадр пака уменьшается до 32x40 (box по альфе), сравнивается средний цвет непрозрачного: dY (яркость) и
dE (RGB-евклид, ловит увод оттенка и насыщенности при той же яркости), доля клеток с dY < -15 (заметно
темнее). Взвешено клетками на картах (census/frames.tsv). Только чтение, без видеокарты.

    py -3.13 tools/hdart/surface_tone.py water          # группа из GROUPS
    py -3.13 tools/hdart/surface_tone.py --sets POLAR,BEACH --name probe
Выход: census/maps/surfaces/tone_<группа>.tsv (по кадрам) и сводка по наборам в консоль и tone_<группа>_sets.tsv.
"""
import argparse
import csv
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path("E:/OpenXCom")
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import pck_census as pc          # noqa: E402
import xcom_sprites as xs        # noqa: E402

INST = ROOT / "Пиратки" / "Dioxine_XPiratez"
HD = INST / "user" / "mods" / "hd" / "hd" / "TERRAIN"
PAL = INST / "user" / "mods" / "Piratez" / "Resources" / "Pals" / "delicious_regular.pal"
pal = np.array(xs.load_palette_file(str(PAL)), dtype=np.float32)[:256]
LUMA = np.array([0.299, 0.587, 0.114], np.float32)
# Группы покрытий (решение специалиста 07.10): вода и берега -> земля и песок -> лес и джунгли -> полы и крыши.
# Состав «воды» - анимированные полы с водой по листу кадров (census/maps/surfaces/README.md), не по имени набора.
GROUPS = {"water": ["FORESTSWAMP", "FORESTSWAMP_SNOW", "FORESTSWAMP_WASTE", "FORESTSWAMPSTYX", "FORESTSWAMPBITS",
                    "LAVA_SWAMP", "LAVA_SWAMPGREEN", "POLAR", "BEACH", "SAVANNABEACH", "SEAURBAN", "LAM_FRN",
                    "IDT_FARM_WATER", "NUKE_WATER_2", "ATLANTSEASHORT", "MUSTYX"]}
ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("group", nargs="?", default="water")
ap.add_argument("--sets", help="наборы через запятую вместо группы")
ap.add_argument("--name", help="имя выхода при --sets")
args = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8")
SETS = args.sets.split(",") if args.sets else GROUPS[args.group]
TAG = (args.name or "sets") if args.sets else args.group

cells = {}
with open(ROOT / "census" / "frames.tsv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
        if r["раздел"] == "TERRAIN" and r["набор"] in SETS:
            cells[(r["набор"], int(r["кадр"]))] = int(r["клеток"] or 0)

files = pc.Files([str(INST / "user" / "mods" / "Piratez"), str(INST / "standard" / "xcom1"), str(INST / "UFO")])
OUTD = ROOT / "census" / "maps" / "surfaces"
OUTD.mkdir(parents=True, exist_ok=True)
out = OUTD / ("tone_%s.tsv" % TAG)
rows, summ = [], []
print("%-18s %6s %6s %7s %7s %6s %8s" % ("набор", "кадров", "без_hd", "dY", "dE", "темнее", "клеток"))
for s in SETS:
    frames, _ = pc.read_set(files, os.path.join("TERRAIN", s + ".PCK"))
    if frames is None:
        continue
    acc = []
    nohd = 0
    for fr, a in enumerate(frames):
        a = np.asarray(a)
        n = cells.get((s, fr), 0)
        if n <= 0 or (a != 0).sum() < 32:
            continue
        p = HD / (s + ".PCK") / ("%d.png" % fr)
        if not p.exists():
            nohd += 1
            continue
        h = np.asarray(Image.open(p).convert("RGBA"), np.float32)
        hh, hw = h.shape[:2]
        k = hw // 32
        h = h[:40 * k, :32 * k].reshape(40, k, 32, k, 4)
        al = h[..., 3:4] / 255.0
        w = al.sum((1, 3))
        rgb = (h[..., :3] * al).sum((1, 3)) / np.maximum(w, 1e-6)
        m = (a != 0) & (w[..., 0] > 0.5 * k * k)
        if m.sum() < 16:
            continue
        c = pal[a][m].mean(0)
        d = rgb[m].mean(0)
        dy = float((d - c) @ LUMA)
        de = float(np.linalg.norm(d - c))
        acc.append((n, dy, de))
        rows.append((s, fr, n, round(dy, 1), round(de, 1)))
    if not acc:
        print("%-18s нет кадров" % s)
        continue
    W = np.array([t[0] for t in acc], np.float64)
    dy = np.array([t[1] for t in acc])
    de = np.array([t[2] for t in acc])
    t = (s, len(acc), nohd, (W * dy).sum() / W.sum(), (W * de).sum() / W.sum(), 100 * W[dy < -15].sum() / W.sum(),
         int(W.sum()))
    summ.append(t)
    print("%-18s %6d %6d %7.1f %7.1f %5.0f%% %8d" % t)
with open(OUTD / ("tone_%s_sets.tsv" % TAG), "w", encoding="utf-8-sig", newline="") as f:
    f.write("набор\tкадров\tбез_hd\tdY\tdE\tтемнее_%\tклеток\n")
    for t in sorted(summ, key=lambda t: -t[4]):
        f.write("%s\t%d\t%d\t%.1f\t%.1f\t%.0f\t%d\n" % t)
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    f.write("набор\tкадр\tклеток\tdY\tdE\n")
    for r in sorted(rows, key=lambda t: -t[2]):
        f.write("\t".join(map(str, r)) + "\n")
