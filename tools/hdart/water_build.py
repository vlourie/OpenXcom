"""Вода семейства SEAURBAN: процедурная сборка HD-кадров из классики, без генерации (07.10).

Наборы и что с ними делается:
  SEAURBAN (144 кадра, 18 записей по 8 фаз) - море. Одна текстура на 3x3 клетки: запись по (x%3, y%3) = ARR
    (так стоят CARGO00, LINERT00), записи 9..17 - та же раскладка в тёмной гамме. Для каждой фазы и гаммы
    собирается периодическое поле классики (порядок рисования y, потом x), поле мягко увеличивается x4
    целиком, и кадр каждой записи берёт цвет из поля там, где стоит. Соседние клетки дают один цвет
    в любой точке - стыков и ромбов нет, рябь идёт через границы клеток, фазы замыкаются как в классике.
    Силуэт: на силуэте классики непрозрачен, гладкая кромка наружу; низ (строки 32..39 базы, юбка 143) -
    лесенка классики x4 как есть (геометрия берега и края карты).
  SEABITS (3 кадра) - статичная вода, плоский ромб. Поле: кадр в середине, вокруг одна и та же смесь трёх
    кадров, мягкое x4; край кадра из общего окружения, поэтому разные кадры стыкуются по тону.
  CARGO2_IND 31..46 (записи 7 и 8) - пена у борта. Premultiplied: бикубика плюс гаусс над цветом,
    умноженным на альфу, и над альфой, потом деление; альфа поднята (gain), чтобы капля в один пиксель
    классики осталась каплей. Корпус и остальные кадры набора не трогаются.

    py -3.13 tools/hdart/water_build.py --out <папка>/TERRAIN [--sets SEAURBAN,SEABITS,CARGO2_IND]
Проверка - игровой кадр моря у борта (сейв пиратского круиза), а не лист кадров.
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import pck_census as pc          # noqa: E402
import xcom_sprites as xs        # noqa: E402
import link_frames as lf         # noqa: E402

INST = ROOT / "Пиратки" / "Dioxine_XPiratez"
PAL = INST / "user" / "mods" / "Piratez" / "Resources" / "Pals" / "delicious_regular.pal"
K = 4
ARR = {(0, 0): 0, (1, 0): 2, (2, 0): 5, (0, 1): 1, (1, 1): 4, (2, 1): 7, (0, 2): 3, (1, 2): 6, (2, 2): 8}
SKIRT = 143
FOAM = range(31, 47)


def palette():
    return np.array(xs.load_palette_file(str(PAL)), dtype=np.uint8)[:256]


def read_set(s):
    files = pc.Files([str(INST / "user" / "mods" / "Piratez"), str(INST / "standard" / "xcom1"), str(INST / "UFO")])
    frames, _ = pc.read_set(files, os.path.join("TERRAIN", s + ".PCK"))
    return [np.asarray(f) for f in frames]


def records(s):
    mcd = lf.find_mcd([str(INST / "user" / "mods" / "Piratez" / "TERRAIN"), str(INST / "UFO" / "TERRAIN")], s)
    data = open(mcd, "rb").read()
    return [list(data[i:i + 8]) for i in range(0, len(data) - 61, 62)], [data[i + 49] for i in range(0, len(data) - 61, 62)]


def up_smooth(img, blur):
    """Мягкое увеличение x4: бикубика плюс гаусс (в пикселях HD)."""
    im = Image.fromarray(img).resize((img.shape[1] * K, img.shape[0] * K), Image.BICUBIC)
    if blur > 0:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(im).astype(np.float32)


def soft_mask(m, blur=1.2):
    """Гладкая маска x4 с краем в полтора пикселя HD."""
    f = up_smooth((m * 255).astype(np.uint8), blur) / 255.0
    return np.clip((f - 0.5) * 2.2 + 0.5, 0, 1)


def blk(m):
    return np.kron(m.astype(np.float32), np.ones((K, K), np.float32))


def iso_field(span, pick):
    """Поле классики: pick(x, y) -> кадр; -> индексы и функция начала клетки на поле."""
    n = len(span)
    ox, oy = n * 16 + 8, 8
    idx = np.zeros((2 * n * 8 + 64, 2 * n * 16 + 64), np.uint8)
    org = lambda x, y: (ox + (x - y) * 16, oy + (x - span[0] + y - span[0]) * 8)   # noqa: E731
    for y in span:
        for x in span:
            a = pick(x, y)
            px, py = org(x, y)
            m = a != 0
            idx[py:py + 40, px:px + 32][m] = a[m]
    return idx, org


def save(o, out, s, f):
    p = Path(out) / (s + ".PCK") / ("%d.png" % f)
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(o, "RGBA").save(p)


def build_seaurban(pal, out, blur=1.6):
    s = "SEAURBAN"
    frames = read_set(s)
    recs, plev = records(s)
    assert len(frames) == 144 and all(recs[r] == list(range(r * 8, r * 8 + 8)) for r in range(18)), "не та раскладка"
    assert all(p == 0 for p in plev), plev
    skirt = pal[SKIRT].astype(np.float32)
    span = range(-6, 9)
    n = 0
    for group in (0, 9):
        for phase in range(8):
            idx, org = iso_field(span, lambda x, y: frames[recs[group + ARR[(x % 3, y % 3)]][phase]])
            cx, cy = org(0, 0)
            core = idx[cy + 8:cy + 56, cx - 32:cx + 64]
            assert not ((core == SKIRT) | (core == 0)).any(), "раскладка 3x3 не закрывает середину поля"
            hd = up_smooth(pal[idx], blur)
            for (dx, dy), r in ARR.items():
                f = recs[group + r][phase]
                a = frames[f]
                px, py = org(dx, dy)
                col = hd[py * K:(py + 40) * K, px * K:(px + 32) * K]
                surf = (a != 0) & (a != SKIRT)
                # на силуэте классики непрозрачен целиком (иначе сквозь кромку видна юбка заднего соседа)
                sm = np.minimum(np.maximum(soft_mask(surf), blk(surf)), 1)
                low = blk(a != 0)
                allm = np.maximum(soft_mask(a != 0), low)
                allm[32 * K:] = low[32 * K:]
                sm = np.minimum(sm, allm)
                # поверхность - цвет поля, к юбке переход только там, где поверхность встречает юбку
                t = np.where(allm > 1e-3, sm / np.maximum(allm, 1e-3), 0)
                c = col * t[..., None] + skirt * (1 - t[..., None])
                save(np.dstack([np.clip(c, 0, 255), allm * 255]).round().astype(np.uint8), out, s, f)
                n += 1
    return n


def build_seabits(pal, out, blur=1.6):
    s = "SEABITS"
    frames = read_set(s)
    span = range(-4, 5)
    rng = np.random.default_rng(5)
    mix = {(x, y): int(rng.integers(len(frames))) for x in span for y in span}
    for f in range(len(frames)):
        idx, org = iso_field(span, lambda x, y: frames[f if (x, y) == (0, 0) else mix[(x, y)]])
        px, py = org(0, 0)
        col = up_smooth(pal[idx], blur)[py * K:(py + 40) * K, px * K:(px + 32) * K]
        a = frames[f]
        alpha = np.maximum(soft_mask(a != 0), blk(a != 0))
        save(np.dstack([np.clip(col, 0, 255), alpha * 255]).round().astype(np.uint8), out, s, f)
    return len(frames)


def gauss(a, sg):
    r = int(np.ceil(3 * sg))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sg) ** 2)
    k /= k.sum()
    p = np.pad(a, r, mode="edge")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 0, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 1, p)


def up_float(img, blur):
    h, w = img.shape[:2]
    out = []
    for c in range(img.shape[2]):
        im = np.asarray(Image.fromarray(img[..., c].astype(np.float32), "F").resize((w * K, h * K), Image.BICUBIC))
        out.append(gauss(im, blur) if blur > 0 else im)
    return np.dstack(out)


def build_foam(pal, out, blur=1.0, gain=1.6):
    s = "CARGO2_IND"
    frames = read_set(s)
    recs, _ = records(s)
    assert recs[7] == list(range(31, 39)) and recs[8] == list(range(39, 47)), (recs[7], recs[8])
    for f in FOAM:
        a = frames[f]
        al = (a != 0).astype(np.float32)
        pre = np.dstack([pal[a].astype(np.float32) * al[..., None], al[..., None]])
        u = up_float(np.pad(pre, ((2, 2), (2, 2), (0, 0))), blur)[2 * K:-2 * K, 2 * K:-2 * K]
        A = np.clip(u[..., 3], 0, 1)
        col = u[..., :3] / np.maximum(A[..., None], 1e-3)
        alpha = np.clip(A * gain, 0, 1)
        alpha[alpha < 0.04] = 0
        save(np.dstack([np.clip(col, 0, 255), alpha * 255]).round().astype(np.uint8), out, s, f)
    return len(FOAM)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sets", default="SEAURBAN,SEABITS,CARGO2_IND")
    a = ap.parse_args()
    pal = palette()
    fn = {"SEAURBAN": build_seaurban, "SEABITS": build_seabits, "CARGO2_IND": build_foam}
    for s in a.sets.split(","):
        print(s, "кадров", fn[s](pal, a.out), "->", Path(a.out) / (s + ".PCK"))


if __name__ == "__main__":
    main()
