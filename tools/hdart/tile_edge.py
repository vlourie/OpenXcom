"""Плиточные полы без сетки: профиль яркости пака у края клетки подгоняется к классике (07.10, без генерации).

Брак пака у рисованной плитки (U_BASE 67 - пол базы пришельцев и подобные): каждая клетка нарисована отдельной
плитой с фаской и тёмным ободом, и на поле обод выходит ромбической сеткой. У классики шов между плитками есть,
но слабый - на тон-два темнее. Рисунок плитки внутри (крест, швы панелей) у пака годный - его не трогаем.

Что делается с кадром:
  1. e - расстояние до края ромба пола в ромбической мере (0 на краю, 1 в центре); край - один из четырёх
     (верх-лево, верх-право, низ-лево, низ-право) по знакам x - CX, y - CY.
  2. Профиль: средняя яркость по полосам e шириной BIN у каждого края, отдельно у пака и у классики x4;
     от профиля отнимается средняя яркость середины (e от INNER до 0.6). Профиль классики сглажен по
     полосам (nearest x4 - ступени по 4 пикселя).
  3. Яркость пикселя пака в полосе e < INNER (и за ромбом, до -OUT) сдвигается на разность профилей
     классика минус пак, с плавным уходом к INNER. Цвет - множителем (Y' + 2) / (Y + 2), как R-030.
Альфа не меняется. Проверка - поле 4x4 копий (frame_zoom) и игровой кадр классика | пак установки | новое.

    py -3.13 tools/hdart/tile_edge.py --set U_BASE --frames 67 --out <папка>/TERRAIN
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ground_seam as gs          # noqa: E402
import water_build as wb          # noqa: E402

BIN = 1.0 / 64
INNER = 0.30
OUT = 0.08
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def edge_geom(h=160, w=128):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    e = 1.0 - gs.dmap(h, w)
    q = (x >= gs.CX).astype(np.int32) + 2 * (y >= gs.CY).astype(np.int32)
    return e, q


def classic_x4(s, f, pal):
    fr = wb.read_set(s)[f]
    rgb = pal[fr].astype(np.float32)
    a = fr > 0
    return np.repeat(np.repeat(rgb, gs.K, 0), gs.K, 1), np.repeat(np.repeat(a, gs.K, 0), gs.K, 1)


def profile(Y, m, e, q, smooth=0.0):
    nb = int(round((INNER + OUT) / BIN)) + 1
    idx = np.clip(np.floor((e + OUT) / BIN).astype(np.int32), 0, nb - 1)
    mid = m & (e >= INNER) & (e < 0.6)
    base = float(Y[mid].mean()) if mid.any() else float(Y[m].mean())
    P = np.zeros((4, nb), np.float32)
    for k in range(4):
        for b in range(nb):
            s = m & (q == k) & (idx == b)
            P[k, b] = Y[s].mean() - base if s.sum() >= 3 else np.nan
        row = P[k]
        ok = ~np.isnan(row)
        if ok.any():
            row[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), row[ok])
        else:
            row[:] = 0.0          # у края нет пикселей (обломок) - профиль не трогаем
        if smooth > 0:
            r = int(3 * smooth)
            kx = np.exp(-0.5 * (np.arange(-r, r + 1) / smooth) ** 2)
            kx /= kx.sum()
            row[:] = np.convolve(np.pad(row, r, mode="edge"), kx, mode="valid")
        row[(np.arange(nb) * BIN - OUT) >= INNER] = 0.0
    return P, idx


def dechroma(rgb, a, e, band):
    """Чужой рыжий у края (кайма пака, которой нет в классике): цветность середины кадра, яркость своя."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    rust = a & (e < band) & (r > b + 12) & (r > g + 20)
    mid = a & (e > INNER) & ~rust
    if mid.sum() < 50:
        mid = a & ~rust           # обломок без середины - цветность всего нерыжего
    if not mid.any():
        return rgb, 0
    Y = rgb @ LUMA
    c_mid = np.median(rgb[mid] - Y[mid, None], axis=0)
    w = np.clip((band - e) / 0.04, 0.0, 1.0)[..., None]
    rgb = rgb.copy()
    rgb[rust] = (rgb * (1 - w) + (Y[..., None] + c_mid[None, None, :]) * w)[rust]
    return np.clip(rgb, 0, 255), int(rust.sum())


def fix_frame(hd, cl_rgb, cl_a, smooth=2.0, grout=0.0, rust_band=0.0):
    rgb = hd[..., :3].astype(np.float32)
    a = hd[..., 3] > 0
    e, q = edge_geom(*a.shape)
    if rust_band > 0:
        rgb, n_rust = dechroma(rgb, a, e, rust_band)
        print("  рыжих у края перекрашено:", n_rust)
    Yh = rgb @ LUMA
    Yc = cl_rgb @ LUMA
    Ph, idx = profile(Yh, a, e, q)
    Pc, _ = profile(Yc, cl_a, e, q, smooth=smooth)
    if grout > 0:
        # шов - своя полоса, профиль классики в ней не нужен: фаска пака у шва снимается до середины
        Pc = np.where((np.arange(Pc.shape[1]) * BIN - OUT)[None, :] < grout + 0.03, 0.0, Pc)
    dY = (Pc - Ph)[q, idx]
    w = np.clip((INNER - e) / 0.06, 0.0, 1.0) * (e > -OUT)
    Yn = np.clip(Yh + dY * w, 0, 255)
    out = hd.copy()
    new = np.clip(rgb * ((Yn + 2) / (Yh + 2))[..., None], 0, 255)
    if grout > 0:
        # шов классики: самые тёмные полосы у края ромба (до 2 пикселей базы), средний цвет
        band = cl_a & (e < 2.0 / 32) & (e > -0.02)
        yb = Yc[band]
        sel = band.copy()
        sel[band] = yb <= np.percentile(yb, 40)
        g_rgb = cl_rgb[sel].mean(0)
        tex = (Yn - Yn[a & (e > INNER)].mean()) * 0.25
        g_col = np.clip(g_rgb[None, None, :] + tex[..., None], 0, 255)
        wg = np.clip((grout + 0.012 - e) / 0.024, 0.0, 1.0)[..., None]
        new = new * (1 - wg) + g_col * wg
    out[..., :3] = np.clip(new, 0, 255).astype(np.uint8)
    out[..., 3] = hd[..., 3]
    return out, Ph, Pc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--frames", required=True, help="кадры через запятую; варианты .vN кадра берутся тоже")
    ap.add_argument("--out", required=True)
    ap.add_argument("--smooth", type=float, default=2.0, help="сглаживание профиля классики, полос")
    ap.add_argument("--grout", type=float, default=0.0,
                    help="шов цветом затирки классики до e < N с каждой стороны (1/32 - полпикселя базы)")
    ap.add_argument("--rust", type=float, default=0.0,
                    help="рыжая кайма пака у края до e < N - цветность середины кадра (XOPSUFOSMFLOOR: 0.2)")
    ap.add_argument("--pack-root", default="")
    a = ap.parse_args()
    if a.pack_root:
        gs.PACK_ROOT = a.pack_root
    pal = wb.palette()
    od = Path(a.out) / (a.set + ".PCK")
    od.mkdir(parents=True, exist_ok=True)
    for f in [int(v) for v in a.frames.split(",")]:
        cl_rgb, cl_a = classic_x4(a.set, f, pal)
        for p in sorted(gs.pack_dir(a.set).glob("%d.*png" % f)):
            if p.name.split(".")[0] != str(f):
                continue
            hd = np.array(Image.open(p).convert("RGBA"))
            out, Ph, Pc = fix_frame(hd, cl_rgb, cl_a, a.smooth, a.grout, a.rust)
            Image.fromarray(out).save(od / p.name)
            near = int(round(OUT / BIN))
            print("%s:%s %s  у края (e 0..%.2f) пак %s | классика %s" % (
                a.set, f, p.name, 3 * BIN,
                " ".join("%+.0f" % Ph[k, near:near + 3].mean() for k in range(4)),
                " ".join("%+.0f" % Pc[k, near:near + 3].mean() for k in range(4))))


if __name__ == "__main__":
    main()
