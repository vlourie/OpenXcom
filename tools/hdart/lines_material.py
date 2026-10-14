"""HD-кадр пола: геометрия pixel_lines плюс материал - рельеф и мелкая фактура (лист 14.10).

pixel_lines держит рисунок классики (швы, плиты, камни), но заливает места плоскими цветами палитры:
металл - серая полоса, доски - коричневый узор, камни - условные пятна (вердикт 14.10: PLANE 61, SEAMSUNK1 36,
MARS 2-4, BRAIN2 29). Здесь поверх той же геометрии, без сдвига деталей:

  1. Рельеф. Высота - яркость поля копий x4, размытая на --rsig пикселей x4; свет сверху и слева
     (battle_view.LIGHT): склон к свету светлее, от света темнее. Множитель скалярный по яркости (R-030) -
     тон не уходит. Считается на поле копий с полями PAD до среза: у соседних клеток рельеф стыка один.
  2. Фактура. Прежний HD-пак кадра без низких частот (ground_seam.flatten, выбросы поджаты --clip), разложен
     по изорешётке (ground_seam.periodic) - бесшовно, пятна пака не повторяются клеткой (R-265); кладётся
     отношением яркостей с силой --detail. Пака нет - шум зерна (ground_seam.grain_noise) силой --grain.
  3. Альфа и выступы за ромбом - как pixel_lines (R-291, R-326), проверка контура та же.

    py -3.13 tools/hdart/lines_material.py --out <папка>/TERRAIN --frames PLANE:61 --relief 0.5 --detail 0.8
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb          # noqa: E402
import ground_seam as gs          # noqa: E402
import sprite_scale as ss         # noqa: E402
import contour_check as cc        # noqa: E402
import pixel_lines as pl          # noqa: E402

K, PAD = pl.K, pl.PAD
LUMA = gs.LUMA


def despeckle(f, passes):
    """Дизеринг классики в одиночных пикселях: pixel_lines обводит каждую крапину, и доски и металл выходят
    лабиринтом (вердикт 14.10, PLANE 61, SEAMSUNK1 36). Пиксель, у которого среди 8 соседей не больше одного
    своего индекса, получает самый частый индекс соседей; швы и края плит - длинные линии, у них своих соседей
    два и больше, они остаются. Индекс 0 не трогается и не ставится. Мелкую фактуру потом возвращает пак."""
    f = f.copy()
    h, w = f.shape
    for _ in range(passes):
        p = np.pad(f, 1)
        nb = np.stack([p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
                       for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])
        same = (nb == f[None]).sum(0)
        cand = (same <= 1) & (f > 0)
        if not cand.any():
            break
        ys, xs = np.nonzero(cand)
        new = f.copy()
        for y, x in zip(ys, xs):
            v = nb[:, y, x]
            v = v[v > 0]
            if v.size:
                vals, cnt = np.unique(v, return_counts=True)
                new[y, x] = vals[cnt.argmax()]
        f = new
    return f


def render_padded(cl, pal, holes=False, desp=0):
    """Как pixel_lines.render, но x4 с полями PAD*K: рельеф считается по соседям поля, срез потом."""
    fld, (ox, oy) = pl.build_field(cl)
    if desp:
        fld = despeckle(fld, desp)
    sub = fld[oy - PAD:oy + 40 + PAD, ox - PAD:ox + 32 + PAD]
    rh = gs.dmap()[K // 2::K, K // 2::K] <= 0.97
    if not holes and ((sub[PAD:-PAD, PAD:-PAD][cl > 0] == 0).any() or (sub[PAD:-PAD, PAD:-PAD][rh] == 0).any()):
        raise SystemExit("поле не закрывает кадр (нужен --holes)")
    a = (sub > 0) if holes else np.ones(sub.shape, bool)
    rgba = np.concatenate([pal[sub], (a * 255.0).astype(np.float32)[..., None]], -1)[None]
    return ss.xbrz_scale(rgba, K)[0]


def relief(up, k, sig):
    """Множитель света: 1 + k * наклон к свету, наклон нормирован на разброс высоты кадра."""
    a = up[..., 3] / 255.0
    y = (up[..., :3] @ LUMA) * a
    h = wb.gauss(y, sig) / np.maximum(wb.gauss(a, sig), 1e-3)
    gy, gx = np.gradient(h)
    s = -(gx + gy) / np.sqrt(2.0)          # свет сверху слева: высота растёт к нему - склон светлее
    c = PAD * K
    core = s[c:-c, c:-c]
    sd = float(core[a[c:-c, c:-c] > 0.5].std()) if (a[c:-c, c:-c] > 0.5).any() else 1.0
    return np.clip(1.0 + k * np.clip(s / max(sd, 1e-3), -2.5, 2.5) / 2.5, 0.5, 1.5)


def detail_field(s, f, clip, var=0):
    """Отношение яркости фактуры пака к её среднему, 160 x 128, периодично по изорешётке; None - пака нет."""
    try:
        p = gs.load_pack(s, f)
    except FileNotFoundError:
        return None
    w = (p[..., 3] / 255.0 * (gs.dmap() <= 0.95)).astype(np.float32)
    if w.sum() < 500:
        return None
    tex, mean = gs.flatten(p[..., :3], w, clip)
    fld = gs.periodic(tex, mean, var=var)
    ym = float(mean @ LUMA)
    return (fld @ LUMA) / max(ym, 1.0)


def build(cl, pal, s, f, holes, k_rel, rsig, k_det, k_grain, clip, desp=0):
    up = render_padded(cl, pal, holes, desp)
    sh = relief(up, k_rel, rsig) if k_rel > 0 else 1.0
    c = PAD * K
    up = up[c:-c, c:-c]
    sh = sh[c:-c, c:-c] if k_rel > 0 else 1.0
    rgb = up[..., :3] * (sh[..., None] if k_rel > 0 else 1.0)
    ha = up[..., 3] / 255.0
    if holes:
        ha = np.minimum(ha, pl.own_gate(cl, pal))
    tx = detail_field(s, f, clip) if k_det > 0 else None
    if tx is not None:
        r = 1.0 + k_det * (tx - 1.0)
    elif k_grain > 0:
        g = gs.grain_noise(sig=1.2)
        r = 1.0 + k_grain * g / max(float(g.std()), 1e-3) * 0.08
    else:
        r = None
    if r is not None:
        rgb = rgb * np.clip(r, 0.6, 1.4)[..., None]
    dm = gs.dmap()
    al = (dm <= 1.0 + pl.OVERLAP).astype(np.float32)
    rgb, fa = pl.beyond_diamond(cl, pal, rgb, al * ha, dm)
    return np.clip(rgb, 0, 255), fa, ("пак" if tx is not None else ("зерно" if r is not None else "нет"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--holes", action="store_true", help="как у pixel_lines: прозрачное классики - сквозное")
    ap.add_argument("--relief", type=float, default=0.35, help="сила рельефа (0 - без)")
    ap.add_argument("--rsig", type=float, default=3.0, help="размытие высоты, пикселей x4")
    ap.add_argument("--detail", type=float, default=0.7, help="сила фактуры прежнего пака (0 - без)")
    ap.add_argument("--grain", type=float, default=0.0, help="шум зерна, если пака нет")
    ap.add_argument("--clip", type=float, default=2.0, help="поджать выбросы фактуры пака (сигм)")
    ap.add_argument("--despeckle", type=int, default=0, help="проходов чистки одиночных пикселей дизеринга (0 - без)")
    ap.add_argument("--pack-root", default="", help="папка прежнего пака вместо установки")
    a = ap.parse_args()
    if a.pack_root:
        gs.PACK_ROOT = a.pack_root
    pal = wb.palette().astype(np.float32)
    dm = gs.dmap()
    al = (dm <= 1.0 + pl.OVERLAP).astype(np.float32)
    for it in a.frames.split(","):
        s, f = it.split(":")
        cl = wb.read_set(s)[int(f)]
        rgb, fa, src = build(cl, pal, s, int(f), a.holes, a.relief, a.rsig, a.detail, a.grain, a.clip, a.despeckle)
        v, why = cc.verdict(cl, fa, pal)
        if v != "ok":
            raise SystemExit("%s %s: %s" % (s, f, why))
        gs.save_rgba(rgb, fa, a.out, s, f)
        print("%s %s: фактура %s, средний цвет нового %s, классики %s, сквозного в ромбе %.3f" % (
            s, f, src, np.round(rgb[fa > 0.5].mean(axis=0)).astype(int).tolist(),
            np.round(pal[cl[cl > 0]].mean(axis=0)).astype(int).tolist(), float((fa[al > 0] < 0.5).mean())))


if __name__ == "__main__":
    main()
