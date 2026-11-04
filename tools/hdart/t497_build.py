#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000497 (песок у упавшего самолёта): кандидаты взамен неудачных кадров sdxl_legacy, без модели и видеокарты.

Кадры - только те, где в HD вместо песка рамка с трубками: DESERTPLANE:18 (воронка), :21 (ровный песок) и такие же
POLARPLANE:18, :21, SANDS:21. Кромка у всех - точный ромб и перехлёст нижних рёбер (t492_build.diamond_alpha, R-599).
Воронка:
  1 - рисунок классики, Scale2x дважды (стиль B1 сборщика XP-000492);
  2 - готовая воронка SANDS:18 из мода (та же яма в классике, одобрена), перекрашенная по цветам классики нужного кадра.
Ровный песок:
  1 - кадр :20 того же набора из мода (классика совпадает на 94,5%): стыкуется с соседями без пятна;
  2 - круглое зерно из индексов классики (стиль B2).
Лист: классика, нынешний HD, 1, 2 и сцена 5x5 - кандидат в центре, вокруг кадр :20 того же набора из мода, на пурпуре.
Дыры сцены считаются внутри ромбов трёх центральных рядов; соседи при этом те же, что и в игре сейчас (R-599, R-601).

    py -3.13 tools\hdart\t497_build.py   # -> art/tickets/t497/cand/1|2/<НАБОР>/<кадр>.png, art/_review/tickets_2026-11-05/t497_cand.png
Видеокарту не трогает, в мод ничего не ставит.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import rim_alpha as ra      # noqa: E402
import t492_build as tb     # noqa: E402
import water_build as wb    # noqa: E402

JOBS = [("DESERTPLANE", 18, "pit"), ("DESERTPLANE", 21, "flat"), ("POLARPLANE", 18, "pit"),
        ("POLARPLANE", 21, "flat"), ("SANDS", 21, "flat")]
HD = ROOT / "user" / "mods" / "hd" / "hd" / "TERRAIN"
OUT = ROOT / "art" / "tickets" / "t497" / "cand"
SHEET = ROOT / "art" / "_review" / "tickets_2026-11-05" / "t497_cand.png"
K, W, H = tb.K, tb.W, tb.H
N = 5
STEP_X, STEP_Y = 16 * K, 8 * K
MAGENTA = (255, 0, 255, 255)


def hd_frame(s, f):
    return Image.open(HD / (s + ".PCK") / ("%d.png" % f)).convert("RGBA")


def classic_rgba(s, f):
    P = wb.read_set(s)[f].astype(np.int32)
    pal = wb.palette()[:, :3].astype(np.uint8)
    a = np.zeros(P.shape + (4,), np.uint8)
    a[..., :3] = pal[P]
    a[..., 3] = (P > 0) * 255
    return Image.fromarray(a, "RGBA").resize((W, H), Image.NEAREST)


def refit(rgb_src, alpha_src):
    """Цвет занятой части на пустое (ближайшим) и точный ромб вместо прежней кромки."""
    _, ind = ndimage.distance_transform_edt(alpha_src < 250, return_indices=True)
    out = np.zeros((H, W, 4), np.uint8)
    out[..., :3] = rgb_src[ind[0], ind[1]]
    out[..., 3] = np.rint(tb.diamond_alpha() * 255).astype(np.uint8)
    return out


def match_colors(rgb, mask, target):
    """Перекраска поканально: квантили кадра - в квантили классики, кривая сглажена, чтобы не было ступеней."""
    q = np.linspace(0, 1, 513)
    out = rgb.astype(np.float32).copy()
    for c in range(3):
        src_q = np.quantile(rgb[..., c][mask], q)
        dst_q = ndimage.gaussian_filter1d(np.quantile(target[..., c], q), 10, mode="nearest")
        out[..., c] = np.interp(rgb[..., c], src_q + np.arange(513) * 1e-6, dst_q)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def pit_recolor(s, f):
    src = np.asarray(hd_frame("SANDS", 18))
    cl = np.asarray(classic_rgba(s, f))
    rgb = match_colors(src[..., :3], src[..., 3] > 250, cl[..., :3][cl[..., 3] > 0])
    return refit(rgb, src[..., 3])


def candidates(s, f, kind):
    if kind == "pit":
        return tb.build_one(s, f, "B1", 497 + f, 0, ground=False), pit_recolor(s, f)
    g = np.asarray(hd_frame(s, 20))
    return refit(g[..., :3], g[..., 3]), tb.build_one(s, f, "B2", 497 + f, 0, ground=True)


def tile_xy(i, j):
    return (i - j + N - 1) * STEP_X, (i + j) * STEP_Y


def scene(center, ground):
    """Поле NxN на пурпуре: центр - кандидат, остальное - сосед из мода."""
    w, h = (2 * N - 2) * STEP_X + W, (2 * N - 2) * STEP_Y + H
    im = Image.new("RGBA", (w, h), MAGENTA)
    for t in range(2 * N - 1):
        for i in range(N):
            j = t - i
            if 0 <= j < N:
                fr = center if i == j == N // 2 else ground
                im.alpha_composite(fr, tile_xy(i, j))
    return im


def holes(im):
    """Пурпур внутри ромбов трёх центральных рядов (сквозь него видна подложка)."""
    d, _, _ = ra.diamond(K)
    a = np.asarray(im).astype(np.int32)
    bad = (a[..., 0] > 200) & (a[..., 1] < 60) & (a[..., 2] > 200)
    count = 0
    for i in range(1, N - 1):
        for j in range(1, N - 1):
            x, y = tile_xy(i, j)
            view = bad[y:y + H, x:x + W]
            count += int((view & (d <= 1.0)).sum())
    return count


def on_grey(im):
    bg = Image.new("RGBA", im.size, (40, 40, 44, 255))
    bg.alpha_composite(im)
    return bg


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    crop = (2 * STEP_X, 3 * STEP_Y, 2 * STEP_X + 6 * STEP_X, 3 * STEP_Y + 8 * STEP_Y)
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    sw, sh = 4 * W + 2 * cw + 7 * 8, 30 + (ch + 30) * len(JOBS)
    sheet = Image.new("RGBA", (sw, sh), (24, 24, 28, 255))
    dr = ImageDraw.Draw(sheet)
    x = 8
    for t, w_ in (("классика", W), ("сейчас", W), ("1", W), ("2", W), ("сцена 1", cw), ("сцена 2", cw)):
        dr.text((x, 6), t, font=font, fill=(235, 235, 235))
        x += w_ + 8
    for r, (s, f, kind) in enumerate(JOBS):
        y = 30 + r * (ch + 30)
        ground = hd_frame(s, 20)
        cells = [classic_rgba(s, f), hd_frame(s, f)]
        line = ["%s:%d" % (s, f), "дыр без кандидата %d" % holes(scene(ground, ground))]
        for n, a in enumerate(candidates(s, f, kind)):
            d = OUT / str(n + 1) / s
            d.mkdir(parents=True, exist_ok=True)
            fr = Image.fromarray(a, "RGBA")
            fr.save(d / ("%d.png" % f))
            cells.append(fr)
            sc = scene(fr, ground)
            line.append("%d: дыр %d" % (n + 1, holes(sc)))
            sheet.alpha_composite(sc.crop(crop), (8 + 4 * (W + 8) + n * (cw + 8), y))
        print(" | ".join(line))
        for c, cell in enumerate(cells):
            sheet.alpha_composite(on_grey(cell), (8 + c * (W + 8), y))
        dr.text((8, y + H + 4), "%s:%d" % (s, f), font=font, fill=(235, 235, 235))
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(SHEET)
    print(SHEET)


if __name__ == "__main__":
    main()
