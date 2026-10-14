"""HD-кадр пола с рисунком из тонких линий (фаски, швы, канавки) - xBRZ по полю классики (R-298).

DREAD_BASE 61 (пол базы, 27 тысяч клеток): восьмиугольные плиты и плитки между ними, разделённые тёмными
канавками, со светлой фаской. Линии рисунка в классике толщиной в пиксель и идут только по горизонтали,
вертикали и изо-наклону 2:1. Прежний пак потерял рисунок и рисовал тёмное поле с шумом.

Почему не отрезками: проба 12.10 - цепочки пикселей классики, спрямлённые Дугласом-Пекером с доворотом к трём
направлениям, на стыках плит дали ложные ветви и галочки (тёмные косые штрихи там, где классика сводит три
канавки в точку). xBRZ x4 спрямляет лесенку 2:1 и держит прямые углы, а рисунок не выдумывает.

Что делается:
  1. Поле 5x5 копий классики (порядок рисования - по x + y), рисунок периодичен по сетке клеток.
  2. Кадр средней копии с полями PAD пикселей базы из поля - xBRZ x4, поля срезаются: соседние клетки
     увеличены по тем же соседям, стык совпадает сам.
  3. Альфа - точный ромб с перехлёстом (R-291) плюс сглаженный силуэт своей классики за ромбом: верх
     приподнятой плиты, боковина, торец крыши остаются на своём месте и своего размера (R-326).

    py -3.13 tools/hdart/pixel_lines.py --out art/ground/dread-v1/TERRAIN --frames DREAD_BASE:61
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb          # noqa: E402
import ground_seam as gs          # noqa: E402
import sprite_scale as ss         # noqa: E402
import contour_check as cc        # noqa: E402

K = 4
OVERLAP = 0.04
N = 5                    # копий поля по каждой оси
PAD = 4                  # поле вокруг кадра для xBRZ, пикселей базы
GATE = 3                 # с --holes непрозрачное не дальше GATE пикс x4 от своей копии (own_gate)


def build_field(cl):
    f = np.zeros((16 * N + 48, 32 * N + 32), np.int32)
    cells = sorted(((x, y) for x in range(N) for y in range(N)), key=lambda t: (t[0] + t[1], t[0]))
    for x, y in cells:
        px, py = (x - y) * 16 + (N - 1) * 16, (x + y) * 8
        m = cl > 0
        f[py:py + 40, px:px + 32][m] = cl[m]
    c = N // 2
    ox, oy = (N - 1) * 16, (c + c) * 8           # начало кадра средней копии
    # своя копия поверх всех: у приподнятой плиты (URBAN_WASTE 82, TAVERN 32) копии ниже рисуются позже и
    # закрывали свою боковину внутри ромба. Кадр рисует себя, соседи - только контекст xBRZ и заливка
    # своих прозрачных мест; кто кого закрывает на карте, решает порядок рисования игры (R-326)
    m = cl > 0
    f[oy:oy + 40, ox:ox + 32][m] = cl[m]
    return f, (ox, oy)


def render(cl, pal, holes=False):
    """RGB x4 и прозрачность x4 (0..1). Без holes прозрачность - 1: поле закрывает ромб целиком. С holes индекс 0
    внутри поля - сквозная дыра решётки: xBRZ смешивает в премультиплицированном цвете, края дыр без каймы."""
    fld, (ox, oy) = build_field(cl)
    sub = fld[oy - PAD:oy + 40 + PAD, ox - PAD:ox + 32 + PAD]
    if not holes and (sub[PAD:-PAD, PAD:-PAD][cl > 0] == 0).any():
        raise SystemExit("поле не закрывает кадр")
    # кадр края или обломков (XB1BR 8, U_EXT_G 27): поле копий оставляет пустое внутри ромба, а без holes оно
    # непрозрачно с цветом индекса 0 - чёрная заливка там, где у классики прозрачно
    rh = gs.dmap()[K // 2::K, K // 2::K] <= 0.97
    if not holes and (sub[PAD:-PAD, PAD:-PAD][rh] == 0).any():
        raise SystemExit("поле не закрывает кадр: пусто внутри ромба")
    a = (sub > 0) if holes else np.ones(sub.shape, bool)
    rgba = np.concatenate([pal[sub], (a * 255.0).astype(np.float32)[..., None]], -1)[None]
    up = ss.xbrz_scale(rgba, K)[0][PAD * K:-PAD * K, PAD * K:-PAD * K]
    ha = up[..., 3] / 255.0
    if holes:
        ha = np.minimum(ha, own_gate(cl, pal))
    return up[..., :3], ha


def own_render(cl, pal):
    """Своя копия без поля: RGB x4 и прозрачность x4 (0..1). Это силуэт кадра, каким его сглаживает xBRZ, и цвет
    за ромбом: выступ рисуется своим цветом, а не краем соседней копии (R-326)."""
    own = np.pad(cl, PAD)
    rgba = np.concatenate([pal[own], ((own > 0) * 255.0).astype(np.float32)[..., None]], -1)[None]
    up = ss.xbrz_scale(rgba, K)[0][PAD * K:-PAD * K, PAD * K:-PAD * K]
    return up[..., :3], up[..., 3] / 255.0


def own_gate(cl, pal, r=GATE):
    """Кадр обломков или края (CRASHEDPLANE 40, XB1BR 8): копии соседей в поле кладут свой край на рёбра ромба, и
    перехлёст R-291 рисует рамку, которой у классики нет. Непрозрачное оставлять только в r пикс x4 от своей копии;
    у решётки свои пиксели идут по всем рёбрам, и перехлёст между одинаковыми плитками остаётся."""
    m = own_render(cl, pal)[1] > 0
    p = np.pad(m, r)
    g = np.zeros_like(m)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                g |= p[r + dy:r + dy + m.shape[0], r + dx:r + dx + m.shape[1]]
    return g.astype(np.float32)


def render_dither(cl, pal):
    """Решётка с мелкой сеткой шахматкой в пиксель (LINERSHIPA 24): xBRZ сводит шахматку с дырами в лабиринт.
    Одиночный непрозрачный пиксель среди четырёх дыр - сетка: она идёт подложкой nearest x4 (как классика),
    а xBRZ сглаживает только остальной рисунок (рамки, балки) и кладётся поверх в премультиплицированном цвете."""
    fld, (ox, oy) = build_field(cl)
    sub = fld[oy - PAD:oy + 40 + PAD, ox - PAD:ox + 32 + PAD]
    op = sub > 0
    p = np.pad(op, 1)
    nb = p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    dith = op & ~nb
    top = np.where(dith, 0, sub)
    a = (top > 0).astype(np.float32) * 255.0
    rgba = np.concatenate([pal[top], a[..., None]], -1)[None]
    up = ss.xbrz_scale(rgba, K)[0][PAD * K:-PAD * K, PAD * K:-PAD * K]
    lt, la = up[..., :3], up[..., 3:] / 255.0
    bsub = np.where(dith, sub, 0)[PAD:-PAD, PAD:-PAD]
    brgb = np.repeat(np.repeat(pal[bsub], K, 0), K, 1)
    ba = np.repeat(np.repeat((bsub > 0).astype(np.float32), K, 0), K, 1)[..., None]
    oa = la + ba * (1 - la)
    rgb = (lt * la + brgb * ba * (1 - la)) / np.maximum(oa, 1e-6)
    print("  сетка шахматкой: %d пикс базы подложкой nearest" % int(dith[PAD:-PAD, PAD:-PAD].sum()))
    return rgb, np.minimum(oa[..., 0], own_gate(cl, pal))


def own_edge(rgb, d, edge=0.97, src=0.95):
    """Кадр края материала (бортик крыши, кромка у другого пола): поле копий кладёт рядом ТАКОЙ ЖЕ кадр, и у стыка
    xBRZ и перехлёст несут его рисунок - на карте, где сосед другой, это светлая нитка по краю (R-256). Пиксели у
    границы ромба (d > edge) берут цвет своей клетки по лучу от центра на глубине src."""
    h, w = d.shape
    y, x = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    m = d > edge
    k = src / np.maximum(d, 1e-6)
    sx = np.clip((gs.CX + (x - gs.CX) * k).astype(int), 0, w - 1)
    sy = np.clip((gs.CY + (y - gs.CY) * k).astype(int), 0, h - 1)
    out = rgb.copy()
    out[m] = rgb[sy[m], sx[m]]
    print("  край своей клеткой: %d пикс x4" % int(m.sum()))
    return out


def beyond_diamond(cl, pal, rgb, fa, dm):
    """Ромб клетки - не граница картинки (R-326): верх приподнятой плиты, боковина, торец крыши лежат за ним.
    За ромбом с перехлёстом кадр рисует свою копию без поля - её силуэт xBRZ и её цвет; внутри - поле, как было.
    PIXEL_LINES_DIAMOND_ONLY=1 - прежняя альфа по ромбу, только для контроля теста."""
    if os.environ.get("PIXEL_LINES_DIAMOND_ONLY") == "1":
        return rgb, fa
    orgb, oa = own_render(cl, pal)
    # перехлёст нижних сторон тоже свой: там поле несёт верх соседней плиты, и на краю площадки без соседа это
    # светлая нитка вдоль кромки. На карте его закрывает сосед, который рисуется позже; просвет вершины четырёх
    # клеток закрывает перехлёст верхних сторон того же соседа (R-291)
    y = np.mgrid[0:dm.shape[0], 0:dm.shape[1]][0] + 0.5
    out = (dm > 1.0 + OVERLAP) | ((dm > 1.0) & (y > gs.CY))
    n = int((out & (oa > 0.5)).sum())
    if n:
        print("  за ромбом своя копия: %d пикс x4" % n)
    return np.where(out[..., None], orgb, rgb), np.where(out, oa, fa)


def build(cl, pal, holes=False, dither=False, edge=False):
    """Кадр целиком: RGB x4 и прозрачность x4 (0..1)."""
    dm = gs.dmap()
    al = (dm <= 1.0 + OVERLAP).astype(np.float32)
    rgb, ha = render_dither(cl, pal) if dither else render(cl, pal, holes)
    if edge:
        rgb = own_edge(rgb, dm)
    return beyond_diamond(cl, pal, rgb, al * ha, dm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default="DREAD_BASE:61")
    ap.add_argument("--holes", action="store_true",
                    help="решётка: прозрачные пиксели классики остаются сквозными (иначе ромб сплошной)")
    ap.add_argument("--dither", action="store_true",
                    help="решётка с сеткой шахматкой в пиксель: сетка nearest x4, рамки xBRZ (с --holes)")
    ap.add_argument("--own-edge", action="store_true",
                    help="кадр края материала: у границы ромба цвет своей клетки, а не копии соседа из поля")
    a = ap.parse_args()
    if a.dither and not a.holes:
        raise SystemExit("--dither только вместе с --holes")
    pal = wb.palette().astype(np.float32)
    dm = gs.dmap()
    al = (dm <= 1.0 + OVERLAP).astype(np.float32)
    for it in a.frames.split(","):
        s, f = it.split(":")
        cl = wb.read_set(s)[int(f)]
        rgb, fa = build(cl, pal, a.holes, a.dither, a.own_edge)
        v, why = cc.verdict(cl, fa, pal)
        if v != "ok":
            raise SystemExit("%s %s: %s" % (s, f, why))
        gs.save_rgba(rgb, fa, a.out, s, f)
        print("%s %s: средний цвет нового %s, классики %s, сквозного в ромбе %.3f" % (
            s, f, np.round(rgb[fa > 0.5].mean(axis=0)).astype(int).tolist(),
            np.round(pal[cl[cl > 0]].mean(axis=0)).astype(int).tolist(), float((fa[al > 0] < 0.5).mean())))


if __name__ == "__main__":
    main()
