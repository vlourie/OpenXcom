"""Полы природных покрытий без сетки и в цвете классики: процедурная правка пака, без генерации (07.10).

Брак пака у ковров травы, земли и песка (FOREST 0 и подобные): каждая клетка - свой ромб, к краю он темнеет
и рамкой выходит на поле (ромбическая сетка), а тон уведён (оливковый вместо зелёного). Рисунок мелкой
фактуры у пака при этом годный - его и оставляем.

Что делается с кадром-ковром (--carpet):
  1. Низкие частоты пака снимаются (нормированный гаусс внутри ромба, sigma FLAT): уходит потемнение к краю
     и пятна на всю клетку, остаётся фактура.
  2. Поле: фактура кладётся копиями на изорешётку и её полушаг (4 класса узлов), каждая копия - только своей
     серединой (вес cos^2 до d = BUMP от центра узла, d - ромбическая мера клетки), классы со сдвигом отсчёта,
     поэтому полушаг не повторяет рисунок. Смешение копий - с сохранением разброса (сумма весов на корень
     из суммы квадратов), иначе на стыках копий фактура блёкнет. Поле периодично по изорешётке: кадр сам с
     собой стыкуется без шва в любой точке.
  3. Цвет: средний цвет кадра - средний цвет классики; отклонения яркости и цветности - пака, умноженные на
     отношение разбросов классики и пака (в пределах SCALE_Y, SCALE_C). Преобразование подобрано по ковру и
     то же для всех кадров набора - тон связанных кадров (кочки, проплешины) согласован.
  4. Альфа: силуэт классики x4 плюс точный ромб; за ромбом - то же поле (то, что покажет сосед).
Прочие кадры-полы (--other): то же преобразование цвета; у ромба (d > EDGE) их цвет плавно переходит в поле
ковра - край клетки с кочкой или проплешиной продолжает соседнюю траву. Выступы над ромбом (стебли) не трогаются.

    py -3.13 tools/hdart/ground_seam.py --set FOREST --carpet 0 --other 1,2,3,4,5,6,7,8 --out <папка>/TERRAIN
Проверка - игровой кадр (game_hidden) классика | пак установки | новое и поле 9x9 с вариантами (ground_field).
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import water_build as wb          # noqa: E402

K = 4
CX, CY, HX, HY = 64.0, 130.0, 64.0, 32.0          # ромб пола x4: центр (16, 32.5) базы, полуоси 16 x 8
A, B = np.array([64.0, 32.0]), np.array([64.0, -32.0])
FLAT = 10.0
BUMP = 0.65
EDGE = 0.72
SCALE_Y = (0.7, 1.4)
SCALE_C = (0.5, 1.6)
HALF = [(0.0, 0.0), (32.0, 16.0), (32.0, -16.0), (64.0, 0.0)]
SHIFT = [(0.0, 0.0), (8.0, 4.0), (-8.0, 4.0), (0.0, -8.0)]
GAIN_MAX = 1.3            # потолок возврата разброса яркости после МНК (1.6 у мха болота - шум точками)
VAR_FLIP = [(1, 1), (-1, 1), (1, -1), (-1, -1)]     # отражения фактуры у вариантов ковра .v1-.v3
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def dmap(h=160, w=128, cx=CX, cy=CY):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    return np.abs(x - cx) / HX + np.abs(y - cy) / HY


def load_pack(s, f):
    p = wb.INST / "user" / "mods" / "hd" / "hd" / "TERRAIN" / (s + ".PCK") / ("%d.png" % f)
    return np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)


def flatten(rgb, w, clip=0.0):
    """Фактура без низких частот: rgb - (гаусс rgb*w / гаусс w) + среднее по w.
    clip > 0 - отклонение яркости больше clip сигм поджимается до clip сигм: одиночное пятно пака (ямка,
    камешек) иначе повторяется в каждом узле поля правильной решёткой точек (JUNGLEBITS 0)."""
    num = np.dstack([wb.gauss(rgb[..., c] * w, FLAT) for c in range(3)])
    den = wb.gauss(w, FLAT)[..., None]
    low = num / np.maximum(den, 1e-4)
    mean = (rgb * w[..., None]).sum((0, 1)) / w.sum()
    dev = rgb - low
    if clip > 0:
        dy = dev @ LUMA
        lim = clip * float(np.sqrt((dy * dy * w).sum() / w.sum()))
        k = np.where(np.abs(dy) > lim, lim / np.maximum(np.abs(dy), 1e-6), 1.0)[..., None]
        dev = dev * k
    return dev + mean, mean


def bilinear(img, x, y):
    h, w = img.shape[:2]
    x = np.clip(x - 0.5, 0, w - 1.001)
    y = np.clip(y - 0.5, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy)
            + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)


def periodic(tex, mean, h=160, w=128, var=0):
    """Поле фактуры на изорешётке (см. шапку, п. 2): кадр h x w, ромб клетки в (CX, CY).
    var > 0 - вариант: фактура отражена (VAR_FLIP), сдвиги классов узлов переставлены; тон и стык те же."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    acc = np.zeros((h, w, 3), np.float32)
    w2 = np.zeros((h, w), np.float32)
    # вариант: отражение фактуры (ромб симметричен - выборка остаётся внутри) и перестановка сдвигов между
    # классами узлов; сдвиг отсчёта больше нельзя - SHIFT уже на краю (BUMP + 0.25 = 0.9 ромба)
    fx, fy = VAR_FLIP[var % len(VAR_FLIP)]
    r = (var + var // 4) % 4          # var 4 не повторяет var 0: отражение то же, перестановка другая
    shifts = SHIFT[r:] + SHIFT[:r]
    for (hx, hy), (tx, ty) in zip(HALF, shifts):
        for i in range(-3, 4):
            for j in range(-3, 4):
                ox, oy = CX + hx + i * A[0] + j * B[0], CY + hy + i * A[1] + j * B[1]
                d = np.abs(x - ox) / HX + np.abs(y - oy) / HY
                wt = np.where(d < BUMP, np.cos(0.5 * np.pi * d / BUMP) ** 2, 0).astype(np.float32)
                if not wt.any():
                    continue
                smp = bilinear(tex, CX + fx * (x - ox + tx), CY + fy * (y - oy + ty))
                acc += wt[..., None] * (smp - mean)
                w2 += wt * wt
    return mean + acc / np.sqrt(np.maximum(w2, 1e-6))[..., None]


def stats(c):
    yv = c @ LUMA
    ch = c - yv[:, None]
    return c.mean(0), yv.std(), np.sqrt((ch ** 2).sum(1).mean() - (ch.mean(0) ** 2).sum())


def fit_tone(pack_px, classic_px):
    """Средний цвет - классики; отклонения яркости и цветности пака с отношением разбросов (в пределах)."""
    mp, syp, scp = stats(pack_px)
    mc, syc, scc = stats(classic_px)
    gy = float(np.clip(syc / max(syp, 1e-3), *SCALE_Y))
    gc = float(np.clip(scc / max(scp, 1e-3), *SCALE_C))
    print("  тон: пак %s -> классика %s, яркость x%.2f, цветность x%.2f" % (mp.round(1), mc.round(1), gy, gc))

    def tone(c):
        dev = c - mp
        dy = dev @ LUMA
        dc = dev - dy[..., None]
        return mc + gy * dy[..., None] + gc * dc
    return tone


def fit_map(s, fs, pal, frames):
    """Аффинная карта цвета пак -> классика по всем полам набора: пак, уменьшенный до базы, против классики
    на тех же местах (обе стороны размыты на пиксель базы - дизеринг классики не пара пикселю пака).
    Одна карта на набор: трава в зелень, земля в бурое, каждый цвет своим путём, а не общим сдвигом."""
    X, Y = [], []
    for f in fs:
        a = frames[f]
        p = load_pack(s, f)
        pb = p.reshape(40, K, 32, K, 4).mean((1, 3))
        m = (a != 0) & (pb[..., 3] > 250)
        c = pal[a].astype(np.float32) * (a != 0)[..., None]
        w = (a != 0).astype(np.float32)
        cb = np.dstack([wb.gauss(c[..., i], 1.0) for i in range(3)]) / np.maximum(wb.gauss(w, 1.0), 1e-3)[..., None]
        pp = pb[..., :3] * (pb[..., 3:] / 255.0)
        pw = pb[..., 3] / 255.0
        pbb = np.dstack([wb.gauss(pp[..., i], 1.0) for i in range(3)]) / np.maximum(wb.gauss(pw, 1.0), 1e-3)[..., None]
        X.append(pbb[m])
        Y.append(cb[m])
    X, Y = np.concatenate(X), np.concatenate(Y)
    Xa = np.hstack([X, np.ones((len(X), 1), np.float32)])
    # две аффинные карты: зелень и бурое (земля, песок) - одной прямой их не развести, вторая степень
    # перегибает бурое в красное; смешение по мягкому признаку пака warm()
    wd = warm(X)
    Ms = []
    for w in (1.0 - wd, wd):
        if w.sum() < 30:
            Ms.append(None)
            continue
        sw = np.sqrt(w)[:, None]
        Ms.append(np.linalg.lstsq(Xa * sw, Y * sw, rcond=None)[0])
    if Ms[1] is None:
        Ms[1] = Ms[0]
    if Ms[0] is None:
        Ms[0] = Ms[1]

    def apply(c):
        sh = c.shape
        c2 = c.reshape(-1, 3)
        ca = np.hstack([c2, np.ones((len(c2), 1), np.float32)])
        k = warm(c2)[:, None]
        return ((ca @ Ms[0]) * (1 - k) + (ca @ Ms[1]) * k).reshape(sh)
    pred = apply(X)
    # МНК сжимает разброс к среднему (пары шумные): разброс яркости возвращаем к разбросу классики
    gy = float(np.clip((Y @ LUMA).std() / max((pred @ LUMA).std(), 1e-3), 1.0, GAIN_MAX))
    mu = pred.mean(0)
    print("  карта цвета по %d пикселям (тёплых %.0f), ошибка %.1f, возврат разброса x%.2f"
          % (len(X), wd.sum(), np.abs(pred - Y).mean(), gy))

    def tone(c):
        return mu + (apply(c) - mu) * gy
    return tone


def warm(c):
    """Доля бурого в цвете пака: красный выше зелёного - земля, ниже - трава (мягко, ширина 30)."""
    return np.clip((c[:, 0] - c[:, 1] + 10.0) / 30.0, 0.0, 1.0).astype(np.float32)


def classic_alpha(a):
    return np.maximum(wb.blk(a != 0), (dmap() <= 1.0).astype(np.float32))


def save_rgba(rgb, al, out, s, name):
    p = Path(out) / (s + ".PCK") / (name + ".png")
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.dstack([np.clip(rgb, 0, 255), al * 255]).round().astype(np.uint8), "RGBA").save(p)


def detail_tone(a, p, pal, sig=1.0, gain=1.0):
    """Цвет кадра с деталями: низкие частоты - классики (размыта на sig базы, дизеринг уходит), высокие -
    пака (пак минус его размытие тем же радиусом x4). Цвет каждого места - цвет классики на этом месте."""
    w = (a != 0).astype(np.float32)
    c = pal[a].astype(np.float32) * w[..., None]
    cb = np.dstack([wb.gauss(c[..., i], sig) for i in range(3)]) / np.maximum(wb.gauss(w, sig), 1e-3)[..., None]
    up = np.dstack([np.asarray(Image.fromarray(np.ascontiguousarray(cb[..., i], np.float32), "F")
                               .resize((32 * K, 40 * K), Image.BICUBIC)) for i in range(3)])
    pa = p[..., 3] / 255.0
    pp = p[..., :3].astype(np.float32) * pa[..., None]
    pb = np.dstack([wb.gauss(pp[..., i], sig * K) for i in range(3)]) / np.maximum(wb.gauss(pa, sig * K), 1e-3)[..., None]
    return up + gain * (p[..., :3] - pb)


def mat_mask(a, p_grass):
    """Доля травы по классике: у каждого индекса палитры - доля его встреч в кадре травы против кадра
    ковра (p_grass), сглажено внутри кадра (сигма 1.2 базы); x4 бикубикой и гауссом 2. По яркости нельзя:
    мох классики крапчатый, зелёные точки поднимают его яркость до травы."""
    w = (a != 0).astype(np.float32)
    ys = wb.gauss(p_grass[a] * w, 1.2) / np.maximum(wb.gauss(w, 1.2), 1e-3)
    m = np.clip((ys - 0.25) / 0.5, 0, 1)
    m = m * m * (3 - 2 * m)
    up = np.asarray(Image.fromarray(m.astype(np.float32), "F").resize((32 * K, 40 * K), Image.BICUBIC))
    return np.clip(wb.gauss(up, 2.0), 0, 1)


def index_share(a_dark, a_light):
    """Доля встреч индекса в светлом материале: частоты индексов в двух кадрах классики, нормированные
    на число пикселей; индекс, которого нет ни там, ни там, - 0.5."""
    hd = np.bincount(a_dark[a_dark != 0], minlength=256).astype(np.float32) / max((a_dark != 0).sum(), 1)
    hl = np.bincount(a_light[a_light != 0], minlength=256).astype(np.float32) / max((a_light != 0).sum(), 1)
    return np.where(hd + hl > 0, hl / np.maximum(hd + hl, 1e-9), 0.5).astype(np.float32)


def build(s, carpet, others, out, variants=3, alts=(), grass=None, mixes=(), recolor=(), clip=0.0):
    """carpet - ковёр (поле с вариантами), alts - другие кадры того же ковра (другим вариантом поля);
    others - полы с деталями: свой цвет, у ромба переход в поле травы (grass) или ковра;
    grass - (набор, кадр, собранный PNG) поля травы другого набора: им же продолжаются others и mixes;
    mixes - переходы ковёр | трава: смесь двух полей по классике (тёмное - ковёр, светлое - трава);
    recolor - только карта цвета (свои фактура и край)."""
    pal = wb.palette()
    frames = wb.read_set(s)
    d = dmap()
    inner = (d < 0.9).astype(np.float32)
    p0 = load_pack(s, carpet)
    tex, mean = flatten(p0[..., :3], inner * (p0[..., 3] > 127), clip)
    a0 = frames[carpet]
    tone = fit_map(s, [carpet] + list(alts), pal, frames)
    ftone = tone(periodic(tex, mean))
    al = classic_alpha(a0)
    save_rgba(ftone, al, out, s, "%d" % carpet)
    n = 1
    # варианты ковра (R-039): один кадр на всё поле - повтор; движок раскладывает .v1-.v3 пятнами
    for v in range(1, variants + 1):
        save_rgba(tone(periodic(tex, mean, var=v)), al, out, s, "%d.v%d" % (carpet, v))
        n += 1
    for k, f in enumerate(alts):
        save_rgba(tone(periodic(tex, mean, var=variants + 1 + k)), classic_alpha(frames[f]), out, s, "%d" % f)
        n += 1
    if grass:
        gs, gf, gpng = grass
        gfield = np.asarray(Image.open(gpng).convert("RGBA")).astype(np.float32)[..., :3]
        g_cls = wb.read_set(gs)[gf]
    else:
        gfield, g_cls = ftone, None
    if others:
        t = np.clip((d - EDGE) / (1.0 - EDGE), 0, 1)[..., None]
        for f in others:
            p = load_pack(s, f)
            # крупный тон - классики, мелкая фактура - пака (detail_tone); карта цвета на детали (камни,
            # кочки) не годится - аффинная карта по траве уводит серое и бежевое в розовое
            c = detail_tone(frames[f], p, pal)
            pa = p[..., 3:] / 255.0
            # у ромба (и за ним, где пак непрозрачен) - переход в поле травы; выше ромба (стебли) - свой цвет
            band = t * (d[..., None] <= 1.15) * (np.mgrid[0:160, 0:128][0][..., None] >= CY - HY)
            c = c * (1 - band) + gfield * band
            alpha = np.maximum(pa[..., 0], (d <= 1.0).astype(np.float32) * (frames[f] != 0).any())
            save_rgba(c, alpha, out, s, "%d" % f)
            n += 1
    if mixes:
        if g_cls is None:
            raise SystemExit("--mix без --grass: не с чем смешивать")
        share = index_share(a0, g_cls)
        for k, f in enumerate(mixes):
            m = mat_mask(frames[f], share)[..., None]
            print("  смесь %d: доля травы %.2f" % (f, float(m.mean())))
            c = tone(periodic(tex, mean, var=k % 4)) * (1 - m) + gfield * m
            save_rgba(c, classic_alpha(frames[f]), out, s, "%d" % f)
            n += 1
    if recolor:
        rtone = fit_map(s, list(recolor), pal, frames)
        for f in recolor:
            p = load_pack(s, f)
            save_rgba(rtone(p[..., :3]), p[..., 3] / 255.0, out, s, "%d" % f)
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--set", required=True)
    ap.add_argument("--carpet", type=int, default=0)
    ap.add_argument("--other", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--variants", type=int, default=3, help="вариантов ковра .v1..vN (R-039: не меньше трёх)")
    ap.add_argument("--alt", default="", help="другие кадры того же ковра")
    ap.add_argument("--grass", default="", help="НАБОР:кадр:собранный.png - поле травы соседнего набора")
    ap.add_argument("--mix", default="", help="переходы ковёр | трава")
    ap.add_argument("--recolor", default="", help="только карта цвета")
    ap.add_argument("--clip", type=float, default=0.0, help="поджать выбросы яркости фактуры ковра до N сигм")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    def ints(v):
        return [int(x) for x in v.split(",") if x]
    grass = None
    if a.grass:
        gs, gf, gp = a.grass.split(":", 2)
        grass = (gs, int(gf), gp)
    n = build(a.set, a.carpet, ints(a.other), a.out, a.variants, ints(a.alt), grass, ints(a.mix), ints(a.recolor), a.clip)
    print(a.set, "кадров", n, "->", Path(a.out) / (a.set + ".PCK"))


if __name__ == "__main__":
    main()
