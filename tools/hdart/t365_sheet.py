#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Лист разбора XP-000365: пол вышки связи (C_INT:6, пятно света от ламп) - классика / HD сейчас / предпросмотр A.

Только чтение: ничего в мод не ставит. Предпросмотр A - процедурный (бикубика палитровой картинки классики x4 с
мягким доводом резкости точек, ромб с перехлёстом), на видеокарте не считается; в игру не подключён.

    py -3.13 tools\hdart\t365_sheet.py        # art/_review/tickets_2026-10-29/t365_sheet.png (+ t365_scene_*.png)
"""
import base64
import re
import struct
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ticket_scene as ts  # noqa: E402
import water_build as wb  # noqa: E402

ROOT = ts.ROOT
SAVE = ROOT / "census" / "tickets" / "XP-000365" / "files" / "02__autobattle_.asav"
SHOT = ROOT / "census" / "tickets" / "XP-000365" / "files" / "01_shot.png"
OUT = ROOT / "art" / "_review" / "tickets_2026-10-29"
K = 4
BG = (60, 52, 44)
FAMILY = ["C_INT:6", "C_INT_HALF:6", "C_INT_HALF_XCOM:6", "C_INT_SMALL:6", "C_INT_XCOM:6", "C_INT_THIRD:6",
          "CORP:36", "C_INT_XCOM_GOLD:6", "FREIGHTER_MAIN:13"]


def read_save(path=SAVE):
    f = open(path, "rb").read().decode("utf-8", "replace")
    b = base64.b64decode(re.search(r"binTiles: (\S+)", f).group(1))
    sets = [s.strip()[2:] for s in re.search(r"mapdatasets:\n((?:    - .*\n)+)", f).group(1).split("\n") if s.strip()]
    tiles = {}
    for i in range(0, len(b), 23):
        idx = struct.unpack("<I", b[i:i + 4])[0]
        ids = struct.unpack("<4h", b[i + 4:i + 12])
        sid = struct.unpack("<4h", b[i + 12:i + 20])
        tiles[(idx % 60, (idx // 60) % 60, idx // 3600)] = (ids, sid)
    return tiles, sets


def preview_a(S, f):
    """Предпросмотр A: классика кадра -> RGBA 128x160 без GPU. Тон классики (градиент свечения) цел."""
    a = np.asarray(wb.read_set(S)[f])
    pal = wb.palette()
    m = a > 0
    rgb = pal[a][..., :3].astype(np.float32)
    idx = ndi.distance_transform_edt(~m, return_distances=False, return_indices=True)
    rgb = rgb[idx[0], idx[1]]                       # прозрачное - соседним цветом, без чёрного края
    big = cv2.resize(rgb, (32 * K, 40 * K), interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(big, (0, 0), 3.0)
    big = np.clip(big + 0.9 * (big - blur), 0, 255)  # точки (дырки) не расплываются
    yy, xx = np.mgrid[0:40 * K, 0:32 * K]
    d = np.abs((xx + 0.5) / K - 16) / 16 + np.abs((yy + 0.5) / K - 32) / 8
    al = np.where(d <= 1.04, 255, 0).astype(np.uint8)
    out = np.dstack([big.astype(np.uint8), al])
    return Image.fromarray(out, "RGBA")


class Src:
    def __init__(self, sc, mode):
        self.sc, self.mode, self._a = sc, mode, {}

    def get(self, S, f):
        if self.mode == "classic":
            return self.sc.classic(S, f)
        if self.mode == "A" and S == "C_INT" and f == 6:
            if f not in self._a:
                self._a[f] = preview_a(S, f)
            return self._a[f]
        h = self.sc.hd(S, f)
        return h if h is not None else self.sc.classic(S, f)


def render_area(tiles, sets, sc, src, x0, x1, y0, y1, zmax=0):
    W = ((x1 - x0) + (y1 - y0)) * 16 + 64
    H = ((x1 - x0) + (y1 - y0)) * 8 + 120
    ox, oy = (y1 - y0) * 16 + 16, 60
    im = Image.new("RGBA", (W * K, H * K), BG + (255,))
    recs = {}
    for z in range(zmax + 1):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                t = tiles.get((x, y, z))
                if not t:
                    continue
                ids, sid = t
                for p in range(4):
                    if ids[p] < 0 or sid[p] < 0 or sets[sid[p]] == "BLANKS":
                        continue
                    S = sets[sid[p]]
                    R = recs.get(S) or recs.setdefault(S, sc.w.records(S))
                    r = R[ids[p]]
                    spr = src.get(S, r["frame"])
                    if spr is None:
                        continue
                    if spr.width != 32 * K:
                        spr = spr.resize((32 * K, 40 * K), Image.NEAREST)
                    im.alpha_composite(spr, ((ox + ((x - x0) - (y - y0)) * 16) * K,
                                             (oy + ((x - x0) + (y - y0)) * 8 - z * 24 - r["p_level"]) * K))
    return im


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sc = ts.Scene()
    tiles, sets = read_save()
    box = (29, 40, 49, 60)                                  # вышка связи: x 30..38, y 50..58 по сейву
    views = {}
    for m in ("classic", "hd", "A"):
        views[m] = render_area(tiles, sets, sc, Src(sc, m), 30, 38, 50, 58)
        views[m].convert("RGB").save(OUT / ("t365_scene_%s.png" % m))
    # окно сцены: клетки пола вышки
    w, h = views["hd"].size
    crop = (int(w * 0.05), int(h * 0.20), int(w * 0.95), int(h * 0.92))
    pan = [ts.label(views[m].crop(crop).convert("RGB"), t, 24)
           for m, t in (("classic", "классика (оригинал)"), ("hd", "HD сейчас (пак установки)"),
                        ("A", "предпросмотр A (процедурно, не подключён)"))]
    shot = Image.open(SHOT).convert("RGB").crop((1000, 700, 2200, 1200))
    shot = ts.label(shot, "скриншот игрока, mode 1 scale 4", 24)
    # кадры семьи: классика / HD
    cells = []
    for key in FAMILY:
        S, f = key.rsplit(":", 1)
        f = int(f)
        for t, im in (("классика", sc.classic(S, f)), ("HD сейчас", sc.hd(S, f)), ("A", preview_a(S, f))):
            if im is None:
                im = Image.new("RGBA", (128, 160), (0, 0, 0, 0))
            p = Image.new("RGBA", (128, 160), (52, 46, 40, 255))
            p.alpha_composite(im)
            p = p.crop((0, 96, 128, 160)).resize((256, 128), Image.NEAREST)
            cells.append((key if t == "классика" else "", t, p.convert("RGB")))
    colw = 256 + 8
    rows = len(FAMILY)
    fam = Image.new("RGB", (colw * 3 + 8, rows * (128 + 30) + 40), (14, 14, 16))
    d = ImageDraw.Draw(fam)
    font = ts.font(18)
    for i, key in enumerate(FAMILY):
        for j in range(3):
            k, t, p = cells[i * 3 + j]
            x, y = 8 + j * colw, 36 + i * (128 + 30)
            fam.paste(p, (x, y + 26))
            d.text((x, y + 2), ("%s  " % key if j == 0 else "") + t, fill=(255, 220, 0), font=font)
    top = ts.sheet([("скриншот игрока", shot)] + [(p_t, p_i) for p_t, p_i in
                                                  (("классика (оригинал)", views["classic"].crop(crop)),
                                                   ("HD сейчас", views["hd"].crop(crop)),
                                                   ("A: процедурно по классике (предпросмотр)", views["A"].crop(crop)))],
                   OUT / "_t365_top.png", cols=2, width=1200)
    top = Image.open(OUT / "_t365_top.png").convert("RGB")
    W = max(top.width, fam.width)
    out = Image.new("RGB", (W, top.height + fam.height + 40), (12, 12, 14))
    out.paste(top, (0, 0))
    out.paste(ts.label(fam, "Семья кадра C_INT:6 (низ кадра x2): классика | HD сейчас | предпросмотр A", 22), (0, top.height + 8))
    out.save(OUT / "t365_sheet.png")
    (OUT / "_t365_top.png").unlink()
    print("OK", OUT / "t365_sheet.png", out.size)


if __name__ == "__main__":
    main()
