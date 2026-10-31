"""Перепись горок по всем блокам карт всех террейнов Пираток (не только по сейвам).

Горка - рельеф из объектов MCD с ненулевым terrainLevel: куб (terrainLevel -24, block), склон или уступ
(другой ненулевой, slope), объект с terrainLevel 0 в стопке объектов своего набора (stack: грани пирамиды
MARS 24-32), и пол этажа z >= 1, лежащий на объекте нижнего этажа (top). Блок карты читается
как в движке (MapScript/RuleTerrain): заголовок - y, x, z; этажи сверху вниз; байт клетки - сквозной номер
записи по mapDataSets террейна (pck_census.resolve).

По кадру PCK (SET:кадр): клеток по всем блокам, роли, блоков, террейнов; HD-кадр установки - дата и
расхождение с классикой (HD, уменьшенный до базы, против классики в палитре боя): dY - средняя яркость,
dC - сдвиг цветности, расх_силуэта - доля пикселей, где непрозрачность HD и классики расходится.
По террейну - сколько клеток горок и каких наборов.

    py -3.13 tools/hdart/hill_census.py [--out art/ground/hills]
Выход (utf-8-sig): frames.tsv, terrains.tsv.
"""
import argparse
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import pck_census as pc   # noqa: E402
import water_build as wb  # noqa: E402

ROOT = HERE.parents[1]
INST = ROOT / "Пиратки" / "Dioxine_XPiratez"
GAME = INST / "user" / "mods" / "hd" / "hd" / "TERRAIN"
B_TLEVEL = 48


def mcd(files, s, cache):
    if s in cache:
        return cache[s]
    p = files.find(os.path.join("TERRAIN", s + ".MCD"))
    recs = []
    if p:
        b = open(p, "rb").read()
        for i in range(0, len(b) - pc.MCD_RECORD + 1, pc.MCD_RECORD):
            recs.append({"f0": b[i], "tl": int.from_bytes(b[i + B_TLEVEL:i + B_TLEVEL + 1], "little", signed=True)})
    cache[s] = recs
    return recs


def blocks_of(files, terrains):
    """(террейн, блок, sets, ячейки [z][y][x] = (пол, з, с, объект))"""
    for tname, t in sorted(terrains.items()):
        sets = list(t.get("mapDataSets") or [])
        for b in t.get("mapBlocks") or []:
            bname = b.get("name") if isinstance(b, dict) else None
            mp = bname and files.find(os.path.join("MAPS", bname + ".MAP"))
            if not mp:
                continue
            data = open(mp, "rb").read()
            if len(data) < 3:
                continue
            sy, sx, sz = data[0], data[1], data[2]
            body = data[3:]
            g = {}
            k = 0
            for zi in range(sz):
                z = sz - 1 - zi
                for y in range(sy):
                    for x in range(sx):
                        if k + 4 <= len(body):
                            g[(x, y, z)] = tuple(body[k:k + 4])
                        k += 4
            yield tname, bname, sets, g


def tone(s, f, pal, sets_cache):
    p = GAME / ("%s.PCK" % s) / ("%d.png" % f)
    if not p.exists():
        return ["нет", "", "", ""]
    d = time.strftime("%m-%d", time.localtime(os.path.getmtime(p)))
    if s not in sets_cache:
        try:
            sets_cache[s] = wb.read_set(s)
        except Exception:                                   # noqa: BLE001
            sets_cache[s] = []
    fr = sets_cache[s]
    if f >= len(fr):
        return [d, "", "", ""]
    cl = fr[f]
    im = np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)
    H, W = cl.shape
    k = im.shape[0] // H
    if k < 1 or im.shape[1] < W * k:
        return [d, "", "", "размер"]
    im = im[:H * k, :W * k].reshape(H, k, W, k, 4)
    a = im[..., 3].mean(axis=(1, 3))
    rgb = (im[..., :3] * im[..., 3:4]).sum(axis=(1, 3)) / np.maximum(im[..., 3].sum(axis=(1, 3)), 1)[..., None]
    m = (cl > 0) & (a > 128)
    if m.sum() < 20:
        return [d, "", "", "мало"]
    c, h = pal[cl][m], rgb[m]
    yv = np.array([0.299, 0.587, 0.114], np.float32)
    dy = float((h @ yv - c @ yv).mean())
    dc = float(np.linalg.norm(((h - (h @ yv)[:, None]) - (c - (c @ yv)[:, None])).mean(axis=0)))
    cov = float(((a > 128) & (cl == 0)).sum() + ((a <= 128) & (cl > 0)).sum()) / max(1, int((cl > 0).sum()))
    return [d, "%.1f" % dy, "%.1f" % dc, "%.2f" % cov]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "art" / "ground" / "hills"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    mod_dir = INST / "user" / "mods" / "Piratez"
    files = pc.Files([str(mod_dir), str(INST / "standard" / "xcom1"), str(INST / "UFO")])
    terrains = pc.collect_terrains(str(mod_dir))
    cache, sizes = {}, {}
    fr_cells = Counter()
    fr_roles = defaultdict(Counter)
    fr_blocks = defaultdict(set)
    fr_terr = defaultdict(Counter)
    terr_cells = defaultdict(Counter)
    nb = 0
    for tname, bname, sets, g in blocks_of(files, terrains):
        nb += 1
        for s in sets:
            if s not in sizes:
                sizes[s] = len(mcd(files, s, cache))

        def rec(v):
            s, r = pc.resolve(v, sets, sizes)
            if s is None:
                return None
            rr = mcd(files, s, cache)
            return (s, rr[r]) if r < len(rr) else None

        for (x, y, z), cell in g.items():
            hits = []
            if cell[3]:
                q = rec(cell[3])
                if q and q[1]["tl"] != 0:
                    hits.append((q[0], q[1]["f0"], "block" if q[1]["tl"] == -24 else "slope"))
                elif q:
                    # стопка: объект того же набора прямо над или под ним (пирамида MARS 24-32 - terrainLevel 0)
                    for dz in (1, -1):
                        o = g.get((x, y, z + dz), (0, 0, 0, 0))[3]
                        q2 = rec(o) if o else None
                        if q2 and q2[0] == q[0]:
                            hits.append((q[0], q[1]["f0"], "stack"))
                            break
            if z and cell[0] and g.get((x, y, z - 1), (0, 0, 0, 0))[3]:
                q = rec(cell[0])
                if q:
                    hits.append((q[0], q[1]["f0"], "top"))
            for s, f, role in hits:
                k = "%s:%d" % (s, f)
                fr_cells[k] += 1
                fr_roles[k][role] += 1
                fr_blocks[k].add(bname)
                fr_terr[k][tname] += 1
                terr_cells[tname][s] += 1
    print("блоков карт %d, кадров горок %d, клеток %d" % (nb, len(fr_cells), sum(fr_cells.values())))
    pal = wb.palette().astype(np.float32)
    sc = {}
    with open(out / "frames.tsv", "w", encoding="utf-8-sig") as fo:
        fo.write("кадр\tклеток\tроли\tблоков\tтеррейнов\thd_дата\tdY\tdC\tрасх_силуэта\tтеррейны\n")
        for k, n in fr_cells.most_common():
            s, f = k.split(":")
            t = tone(s, int(f), pal, sc)
            fo.write("\t".join([k, str(n), ",".join("%s %d" % kv for kv in fr_roles[k].most_common()),
                                str(len(fr_blocks[k])), str(len(fr_terr[k]))] + t +
                               [", ".join("%s %d" % kv for kv in fr_terr[k].most_common(5))]) + "\n")
    with open(out / "terrains.tsv", "w", encoding="utf-8-sig") as fo:
        fo.write("террейн\tклеток\tнаборы\n")
        for tname, c in sorted(terr_cells.items(), key=lambda kv: -sum(kv[1].values())):
            fo.write("%s\t%d\t%s\n" % (tname, sum(c.values()), ", ".join("%s %d" % kv for kv in c.most_common(6))))
    print("записано", out / "frames.tsv", out / "terrains.tsv")


if __name__ == "__main__":
    main()
