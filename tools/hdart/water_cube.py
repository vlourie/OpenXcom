"""HD-кадры водяного блока с петлёй анимации (LAM_FRN 6, 69, 70, 71 - вода деревни ламий), построенные по
классике всей петлёй (R-071) с вариантами .vN (R-039).

Классика: верх - ромб пола, поднятый на 14 пикселей базы, ровный индекс 132 с бликами 131/129; бок - градиент
132 -> 141, индекс растёт на 1 с каждой строкой ниже нижнего ребра верха. Фазы петли различаются только бликами.
Прежний пак: по верху сетка стыков клеток (у каждой клетки свой рисунок края), на боку тёмные вертикальные полосы.

Новое: верх - одно бесшовное поле (periodic) из верха пака кадра петли, тон - к верху классики (fit_tone);
блики - мягкие пятна по пикселям 131/129 классики своей фазы; бок - гладкий градиент по профилю глубины классики
под нижним ребром верха. Альфа - силуэт классики x4 плюс точная геометрия блока, каждый непрозрачный пиксель
получает цвет (R-295). Вариант k у всех фаз из поля periodic(var=k): движок выбирает вариант пола по месту
клетки (Canvas32::groundFrameFor), одинаково для всех фаз, поэтому петля не мигает.

    py -3.13 tools/hdart/water_cube.py --out art/ground/lamfrn-v1/TERRAIN [--set LAM_FRN --loop 6,69,70,71]
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb          # noqa: E402
import ground_seam as gs          # noqa: E402

K = gs.K
SPOT_SIG = 1.6        # блик: гаусс в пикселях x4 (пиксель базы - 4)
SPOT_GAIN = 0.85      # насколько блик доходит до цвета индекса блика
SEAM = 2.0            # мягкий шов верх|бок, пикселей x4 в каждую сторону
HIGHLIGHT = (131, 129)


def geometry(up):
    """Глубина под нижним ребром верха (x4, < 0 - верх) и точный силуэт блока."""
    y, x = np.mgrid[0:160, 0:128].astype(np.float32) + 0.5
    cyt = gs.CY - up
    ax = np.abs(x - gs.CX) / gs.HX
    depth = y - (cyt + gs.HY * (1.0 - ax))
    top = gs.dmap(cy=cyt) <= 1.0
    body = (ax <= 1.0) & (y >= cyt - gs.HY * (1.0 - ax)) & (y <= gs.CY + gs.HY * (1.0 - ax))
    return depth, top, top | body


def side_profile(cl, pal, depth):
    """Цвет бока по глубине: медиана классики x4 по строкам глубины, сглаженная. Возвращает функцию depth -> rgb."""
    c4 = np.repeat(np.repeat(pal[cl], K, 0), K, 1)
    m4 = np.repeat(np.repeat(cl != 0, K, 0), K, 1) & (depth > 0)
    d = np.floor(depth[m4]).astype(int)
    n = int(d.max()) + 1
    prof = np.zeros((n, 3), np.float32)
    have = np.zeros(n, bool)
    for i in range(n):
        s = d == i
        if s.sum() >= 4:
            prof[i] = np.median(c4[m4][s], axis=0)
            have[i] = True
    idx = np.arange(n)
    for c in range(3):
        prof[:, c] = np.interp(idx, idx[have], prof[have, c])
    # гладко по глубине: ступени строк базы (4 пикселя x4) уходят, градиент остаётся
    k = np.exp(-0.5 * (np.arange(-8, 9) / 2.5) ** 2)
    k /= k.sum()
    pad = np.pad(prof, ((8, 8), (0, 0)), mode="edge")
    sm = np.stack([np.convolve(pad[:, c], k, mode="valid") for c in range(3)], 1)

    def at(dd):
        dd = np.clip(dd, 0, n - 1)
        return np.stack([np.interp(dd, idx.astype(np.float32), sm[:, c]) for c in range(3)], -1)
    return at


def spots(cl, pal, base_rgb):
    """Блики фазы: пятна цвета индекса блика поверх base_rgb."""
    out = base_rgb.copy()
    for hi in HIGHLIGHT:
        m = np.repeat(np.repeat((cl == hi).astype(np.float32), K, 0), K, 1)
        if not m.any():
            continue
        w = wb.gauss(m, SPOT_SIG)
        w = np.clip(w / max(float(w.max()), 1e-6), 0, 1) * SPOT_GAIN
        out = out * (1 - w[..., None]) + pal[hi][None, None, :] * w[..., None]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--set", default="LAM_FRN")
    ap.add_argument("--loop", default="6,69,70,71")
    ap.add_argument("--src", type=int, default=None, help="кадр пака, чей верх даёт фактуру (по умолчанию первый)")
    ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--clip", type=float, default=1.5)
    a = ap.parse_args()
    s = a.set
    loop = [int(v) for v in a.loop.split(",")]
    src = a.src if a.src is not None else loop[0]
    pal = wb.palette().astype(np.float32)[:, :3]
    frames = wb.read_set(s)
    ups = {gs.top_up(frames[f]) for f in loop}
    if len(ups) != 1:
        raise SystemExit("подъём верха у фаз разный: %s" % sorted(ups))
    up = ups.pop()
    cyt = gs.CY - up
    base = frames[loop[0]]
    for f in loop[1:]:
        d = frames[f] != base
        bad = set(base[d].tolist()) | set(frames[f][d].tolist())
        if not bad <= set(HIGHLIGHT) | {132}:
            raise SystemExit("кадр %d отличается от %d не только бликами: %s" % (f, loop[0], sorted(bad)))
    depth, top, body = geometry(up)
    print("%s %s: подъём верха %d пикс x4" % (s, loop, up))

    # фактура верха: верх пака src на место ромба пола, без низких частот (как ground_seam.build_tops)
    p = gs.load_pack(s, src)
    ps = np.zeros_like(p)
    ps[up:] = p[:160 - up]
    tex, mean = gs.flatten(ps[..., :3], ((gs.dmap() < 0.85) * (ps[..., 3] > 127)).astype(np.float32), a.clip)
    c4 = np.repeat(np.repeat(pal[base], K, 0), K, 1)
    cls_top = c4[(gs.dmap(cy=cyt) < 0.95) & (np.repeat(np.repeat(base != 0, K, 0), K, 1))]
    # разброс - по верху классики с бликами (у ровного 132 разброса нет, цветность вышла бы 0/0), средний тон -
    # индекс 132 без бликов: блики кладутся отдельно своей фазой
    tone0 = gs.fit_tone(gs.periodic(tex, mean, h=256)[up:up + 160][gs.dmap(cy=cyt) < 0.95], cls_top)

    def tone(c):
        return tone0(c) - cls_top.mean(0) + pal[132]
    side = side_profile(base, pal, depth)(depth)
    sil = np.maximum(wb.blk(base != 0), body.astype(np.float32))
    t = np.clip((depth + SEAM) / (2 * SEAM), 0, 1)[..., None]       # 0 - верх, 1 - бок
    for var in range(a.variants + 1):
        fld = tone(gs.periodic(tex, mean, h=256, var=var)[up:up + 160])
        for f in loop:
            topc = spots(frames[f], pal, fld)
            rgb = topc * (1 - t) + side * t
            name = "%d" % f if var == 0 else "%d.v%d" % (f, var)
            gs.save_rgba(rgb, sil, a.out, s, name)
    # проверки: тон верха и бока против классики, нет ли непрозрачного без цвета
    print("верх: новое %s, классика %s" % (np.round(fld[top & (depth < -3)].mean(0)).astype(int).tolist(),
                                          np.round(cls_top.mean(0)).astype(int).tolist()))
    sm = (np.repeat(np.repeat(base != 0, K, 0), K, 1)) & (depth > 3)
    print("бок: новое %s, классика %s" % (np.round(side[sm].mean(0)).astype(int).tolist(),
                                         np.round(c4[sm].mean(0)).astype(int).tolist()))
    print("записано кадров: %d (%d фаз x %d)" % (len(loop) * (a.variants + 1), len(loop), a.variants + 1))


if __name__ == "__main__":
    main()
