"""Зелень пака ушла в олив против классики - вернуть оттенок, не трогая форму, альфу и мелочь пака.

Для кадра: средний оттенок/насыщенность/яркость зелёных пикселей классики (палитра) и пака (PNG установки);
пикселям пака в зелёном поясе оттенка оттенок сдвигается на разницу, насыщенность и яркость умножаются на
отношение (с пределами). Вес плавный по оттенку (пояс 50-165, края до 30 и 185) и по насыщенности, чтобы
не было соли на границе (R-195); дерево, металл, кора и цветы вне пояса остаются как были.
Одно смещение на кадр, без масок по месту - спрайт пака против классики сдвинут (R-319).

    tools/hdart/.venv/Scripts/python.exe tools/hdart/green_tone.py --set URBITS --frames 12,13,15,19 --out <партия>/TERRAIN
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import water_build as wb  # noqa: E402

GAME = Path("E:/OpenXCom/Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN")


def frames(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def rgb2hsv(a):
    """a: N x 3 в 0..1 -> h (градусы), s, v."""
    mx, mn = a.max(1), a.min(1)
    d = mx - mn
    h = np.zeros(len(a))
    r, g, b = a[:, 0], a[:, 1], a[:, 2]
    nz = d > 1e-6
    m = nz & (mx == r)
    h[m] = ((g - b)[m] / d[m]) % 6
    m = nz & (mx == g) & (mx != r)
    h[m] = (b - r)[m] / d[m] + 2
    m = nz & (mx == b) & (mx != r) & (mx != g)
    h[m] = (r - g)[m] / d[m] + 4
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return h * 60, s, mx


def hsv2rgb(h, s, v):
    h = (h % 360) / 60
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    sel = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]
    out = np.zeros((len(h), 3))
    for k, (r, g, b) in enumerate(sel):
        m = i == k
        out[m] = np.stack([r[m], g[m], b[m]], 1)
    return out


def band(h, s):
    """Вес зелёного пояса: 1 внутри 50-165, линейно к 0 на 30 и 185; насыщенность 0.08 -> 0, 0.2 -> 1."""
    w = np.clip((h - 30) / 20, 0, 1) * np.clip((185 - h) / 20, 0, 1)
    return w * np.clip((s - 0.08) / 0.12, 0, 1)


def stats(rgb, w):
    h, s, v = rgb2hsv(rgb)
    sw = w.sum()
    if sw < 1:
        return None
    ang = np.deg2rad(h)
    hm = np.rad2deg(np.arctan2((np.sin(ang) * w).sum(), (np.cos(ang) * w).sum())) % 360
    return hm, (s * w).sum() / sw, (v * w).sum() / sw, sw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", required=True, help="папка TERRAIN партии")
    ap.add_argument("--vmax", type=float, default=1.25, help="предел множителя яркости")
    ap.add_argument("--smax", type=float, default=1.6, help="предел множителя насыщенности")
    ap.add_argument("--min-dh", type=float, default=8, help="кадр с меньшим сдвигом оттенка не пишется")
    ap.add_argument("--both", action="store_true",
                    help="сдвигать и к жёлтому (по умолчанию только олив -> зелень: пак зеленее классики не трогается)")
    a = ap.parse_args()
    pal = wb.palette().astype(np.float64) / 255
    cl = wb.read_set(a.set)
    od = Path(a.out) / ("%s.PCK" % a.set)
    n = 0
    for f in frames(a.frames):
        src = GAME / ("%s.PCK" % a.set) / ("%d.png" % f)
        if f >= len(cl) or not src.exists():
            print("%s:%d нет кадра" % (a.set, f))
            continue
        c = cl[f]
        crgb = pal[c[c > 0]]
        ch, cs, cv = rgb2hsv(crgb)
        st_c = stats(crgb, band(ch, cs))
        im = np.asarray(Image.open(src).convert("RGBA")).astype(np.float64)
        al = im[..., 3]
        op = al > 0
        prgb = im[..., :3][op] / 255
        ph, ps, pv = rgb2hsv(prgb)
        wp = band(ph, ps)
        st_p = stats(prgb[al[op] > 128], wp[al[op] > 128])
        if st_c is None or st_p is None:
            print("%s:%d нет зелени" % (a.set, f))
            continue
        dh = (st_c[0] - st_p[0] + 180) % 360 - 180
        ks = float(np.clip(st_c[1] / max(st_p[1], 1e-3), 1 / a.smax, a.smax))
        kv = float(np.clip(st_c[2] / max(st_p[2], 1e-3), 1 / a.vmax, a.vmax))
        if abs(dh) < a.min_dh or (dh < 0 and not a.both):
            print("%s:%d сдвиг %.1f - мал или к жёлтому, пропуск" % (a.set, f, dh))
            continue
        nh = ph + dh * wp
        ns = np.clip(ps * (1 + (ks - 1) * wp), 0, 1)
        nv = np.clip(pv * (1 + (kv - 1) * wp), 0, 1)
        out = im.copy()
        out[..., :3][op] = np.clip(hsv2rgb(nh, ns, nv) * 255 + 0.5, 0, 255)
        od.mkdir(parents=True, exist_ok=True)
        Image.fromarray(out.astype(np.uint8), "RGBA").save(od / ("%d.png" % f))
        n += 1
        print("%s:%d оттенок %.0f->%.0f (%+.0f), s x%.2f, v x%.2f" % (a.set, f, st_p[0], st_c[0], dh, ks, kv))
    print("записано %d кадров в %s" % (n, od))


if __name__ == "__main__":
    main()
