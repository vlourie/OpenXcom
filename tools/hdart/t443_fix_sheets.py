#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Листы переделки тикета XP-000443 (31.10): классика | у игроков | кандидат.

    py -3.13 tools\hdart\t443_fix_sheets.py            # art/_review/tickets_2026-10-31/t443_fix_*.png
Кандидаты - art/tickets/t443/fix (t443_fix.py build). В мод ничего не ставит.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402
from scipy.ndimage import binary_dilation, binary_erosion  # noqa: E402

import ticket_scene as ts                            # noqa: E402
import t443_fix as fx                                # noqa: E402

REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-31")
FIX = fx.OUT
NOW = fx.PACK
FRAMES = (47, 48, 49, 50, 52, 54)


def load(path):
    return Image.open(path).convert("RGBA")


def stats(arr, cm):
    al = arr[..., 3]
    op = al > 128
    cm2 = binary_dilation(cm, iterations=2)
    return float((op & cm).sum() / cm.sum()), int((op & ~cm2).sum())


def seam_min_alpha(img, sign, nx=8):
    """Минимум альфы по сердцевине полос в ряду из nx одинаковых клеток вдоль оси (щель между клетками)."""
    dx = 64 if sign < 0 else -64
    ox = 0 if sign < 0 else nx * 64
    W, H = nx * 64 + 192, nx * 32 + 160
    can = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for k in range(nx):
        can.alpha_composite(img, (ox + k * dx, k * 32))
    A = np.asarray(can, np.float32)[..., 3] / 255
    h, w = A.shape
    a2 = np.repeat(A, 2, axis=0)
    S = np.zeros((2 * h + w + 10, w), np.float32)
    for x in range(w):
        s = (w - x) if sign < 0 else x
        S[s:s + 2 * h, x] = a2[:, x]
    cols = S[:, 140:64 * 6]
    med = np.median(cols, axis=1)
    m = (med > 0.9).astype(int)
    d = np.diff(np.concatenate([[0], m, [0]]))
    worst, bad, tot = 1.0, 0, 0
    for a, b in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
        if b - a > 20:
            sub = cols[a + 5:b - 5]
            worst = min(worst, float(sub.min()))
            bad += int((sub < 0.98).sum())
            tot += sub.size
    return worst, bad, tot


def triple_sheet():
    panels = []
    rows = []
    for fr in FRAMES:
        _, c = fx.classic_sil("MILWAREGHOUL", fr)
        cm = np.kron(c, np.ones((4, 4), bool))
        now = load(os.path.join(NOW, "MILWAREGHOUL.PCK", "%d.png" % fr))
        new = load(os.path.join(FIX, "MILWAREGHOUL_%d.png" % fr))
        cls = ts.Scene().classic("MILWAREGHOUL", fr)
        sn, on = stats(np.asarray(now), cm)
        sf, of = stats(np.asarray(new), cm)
        rows.append((fr, sn, on, sf, of))
        sign = fx.SIGN.get(fr, -1 if fr == 48 else 1)
        wn = seam_min_alpha(now, sign)
        wf = seam_min_alpha(new, sign)
        rows[-1] += wn + wf
        ims = []
        for im in (cls, now, new):
            bg = Image.new("RGBA", im.size, (36, 36, 40, 255))
            bg.alpha_composite(im)
            ims.append(bg.resize((256, 320), Image.LANCZOS if im is not cls else Image.NEAREST))
        strip = Image.new("RGB", (256 * 3 + 12, 320), (12, 12, 14))
        for i, im in enumerate(ims):
            strip.paste(im.convert("RGB"), (i * 262, 0))
        panels.append(("GHOUL:%d (MILWARE:%d) силуэт %.0f%% > %.0f%%  [класс.|сейчас|канд.]"
                       % (fr, fx.TWIN[fr], sn * 100, sf * 100), strip))
    ts.sheet(panels, os.path.join(REV, "t443_fix_frames.png"), cols=2)
    return rows


def synth_sheet():
    """Ряд из клеток вдоль оси: сейчас | кандидат; стыки клеток крупно (синтетика, 6 клеток, увеличение x3)."""
    panels = []
    for fr in (47, 49, 52, 48, 50):
        sign = fx.SIGN.get(fr, -1 if fr == 48 else 1)
        pair = []
        for p in (os.path.join(NOW, "MILWAREGHOUL.PCK", "%d.png" % fr), os.path.join(FIX, "MILWAREGHOUL_%d.png" % fr)):
            im = load(p)
            nx, ny = 5, 3
            W = (nx + ny) * 64 + 128
            H = (nx + ny) * 32 + 160
            can = Image.new("RGBA", (W, H), ts.BG + (255,))
            for y in range(ny):
                for x in range(nx):
                    can.alpha_composite(im, (ny * 64 + (x - y) * 64, (x + y) * 32))
            pair.append(can.crop((0, 40, W, H - 20)))
        w = pair[0].width
        out = Image.new("RGB", (w * 2 + 10, pair[0].height), (12, 12, 14))
        out.paste(pair[0].convert("RGB"), (0, 0))
        out.paste(pair[1].convert("RGB"), (w + 10, 0))
        panels.append(("кадр %d, поле 5x3 клеток одного кадра: сейчас | кандидат" % fr, out))
    ts.sheet(panels, os.path.join(REV, "t443_fix_field.png"), cols=1)


def joint_zoom():
    """Стык двух клеток вдоль оси, x6: сейчас | кандидат, для 47 и 49 (две оси) и 52."""
    panels = []
    for fr in (47, 49, 52):
        sign = fx.SIGN[fr]
        dx = 64 if sign < 0 else -64
        pair = []
        for p in (os.path.join(NOW, "MILWAREGHOUL.PCK", "%d.png" % fr), os.path.join(FIX, "MILWAREGHOUL_%d.png" % fr)):
            im = load(p)
            W, H = 128 + 3 * 64, 160 + 3 * 32
            ox = 0 if sign < 0 else 3 * 64
            can = Image.new("RGBA", (W, H), ts.BG + (255,))
            for k in range(4):
                can.alpha_composite(im, (ox + k * dx, k * 32))
            # стык клеток 1 и 2: рамка вокруг линии стыка у верхней полосы
            cx = ox + 1 * dx + (128 if sign < 0 else 0)
            box = (max(0, cx - 120), 60, min(W, cx + 120), 190) if sign < 0 else (max(0, ox + 2 * dx + 10), 60, min(W, ox + 2 * dx + 250), 190)
            c = can.crop(box)
            pair.append(c.resize((c.width * 4, c.height * 4), Image.NEAREST))
        out = Image.new("RGB", (pair[0].width * 2 + 10, pair[0].height), (12, 12, 14))
        out.paste(pair[0].convert("RGB"), (0, 0))
        out.paste(pair[1].convert("RGB"), (pair[0].width + 10, 0))
        panels.append(("стык клеток, кадр %d, x4: сейчас | кандидат" % fr, out))
    ts.sheet(panels, os.path.join(REV, "t443_fix_joint.png"), cols=1)


def scene_sheets():
    import t443_scene as sc
    ov = {}
    for s, mp in (("MILWAREGHOUL", None), ("MILWARE", None)):
        pass
    for fn in sorted(os.listdir(FIX)):
        if fn.endswith(".png"):
            s, f = fn[:-4].rsplit("_", 1)
            ov[(s, int(f))] = load(os.path.join(FIX, fn))
    ims = {}
    for title, mode, o in (("классика", "classic", None), ("у игроков", "hd", None), ("кандидат", "hd", ov)):
        im = sc.render(0, 24, 38, 50, 1, mode, k=3, override=o).convert("RGB")
        im = im.crop((300, 150, 1900, 1000))
        ims[title] = im
    full = [("1. сцена по карте сейва: классика", ims["классика"].resize((1000, int(850 * 1000 / 1600)), Image.LANCZOS)),
            ("2. сцена по карте сейва: у игроков", ims["у игроков"].resize((1000, int(850 * 1000 / 1600)), Image.LANCZOS)),
            ("3. сцена по карте сейва: кандидат", ims["кандидат"].resize((1000, int(850 * 1000 / 1600)), Image.LANCZOS))]
    ts.sheet(full, os.path.join(REV, "t443_fix_scene.png"), cols=1)
    z = (330, 160, 1030, 560)
    ts.sheet([("классика (крупно)", ims["классика"].crop(z)), ("у игроков (крупно)", ims["у игроков"].crop(z)),
              ("кандидат (крупно)", ims["кандидат"].crop(z))], os.path.join(REV, "t443_fix_scene_zoom.png"), cols=1)
    # то же в k=6, кусок со стыками клеток
    big = {}
    for title, mode, o in (("классика", "classic", None), ("у игроков", "hd", None), ("кандидат", "hd", ov)):
        im = sc.render(8, 16, 40, 46, 1, mode, k=6, override=o).convert("RGB")
        big[title] = im
    ts.sheet([(t + " (k=6)", big[t]) for t in ("классика", "у игроков", "кандидат")],
             os.path.join(REV, "t443_fix_scene_k6.png"), cols=1)


def main():
    os.makedirs(REV, exist_ok=True)
    rows = triple_sheet()
    print("кадр | покрытие сейчас | вне силуэта сейчас | покрытие кандидат | вне | щель сейчас (мин.альфа, пикс<0.98, всего) | щель кандидат")
    for r in rows:
        print(r)
    synth_sheet()
    joint_zoom()
    scene_sheets()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
