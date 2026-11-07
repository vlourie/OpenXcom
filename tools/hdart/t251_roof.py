#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000251: крыша дома URBAN_WASTE 52 (и побайтная копия URBAN_WASTE_WALLS 46) - без белых штрихов и без швов.

Что не так: HD 52 (sdxl_legacy, одобрения нет) на каждой клетке крыши несёт одни и те же белые штрихи, красные кружки и
чёрные точки - 453 клетки в блоке URBANWASTE62 дают решётку из одинаковых значков: «набор плиток», а не крыша. Первая
правка (23.10, лист t251_after.png) убрала штрихи, но оставила тёмный скос классики (индексы 10-13) по краю ромба - на
крыше он дал полосы между клетками. Vitali 23.10: скос убрать совсем, тон и фактура переходят с клетки на клетку без шва.

Лечение (процедурно, без генерации):
  1. Цвет - ровный серый индекс 9 классики (82,81,84), скоса и теней по краям нет вовсе: индексы 10-13 и точки
     (8, 89-91) в основе заменены на 9.
  2. Фактура - шум, ПЕРИОДИЧНЫЙ по решётке клеток (сдвиги (64,32) и (64,-32) в пикселях x4): тор 128x64 ground_seam,
     к которому добавлена его копия со сдвигом (64,32) - значение на стыке соседних клеток совпадает без шва.
     Два масштаба: зерно (мелко) и пятно покрытия (крупно); ни того, ни другого у края нет отдельной каймы.
  3. Ржавые пятнышки и светлые крапины: у 52.png - на местах классики, у вариантов .v1-.v3 - те же числа в других
     местах, шум другой. Движок раскладывает варианты по клеткам O_FLOOR узором (Canvas32); крыша дома - часть 0
     на z=2. Точки держатся в стороне от краёв ромба - через стык не идут.
  4. Альфа - точный ромб (ground_seam.classic_alpha).
Кадр 53 (дыры) не трогается: белых элементов у него нет.

    py -3.13 tools/hdart/t251_roof.py                  # кадры в art/tickets/t251/out/TERRAIN/...
    py -3.13 tools/hdart/t251_roof.py --sheet          # лист art/_review/tickets_2026-10-23/t251_after2.png
    py -3.13 tools/hdart/t251_roof.py --install --yes  # + в мод hd через манифест (по слову Vitali, под очередью правок)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ground_seam as gs            # noqa: E402
import ticket_scene as ts           # noqa: E402
import water_build as wb            # noqa: E402

SET, FR = "URBAN_WASTE", 52
COPIES = [("URBAN_WASTE_WALLS", 46)]
OUT = ROOT / "art" / "tickets" / "t251" / "out"
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-23"
GRAIN = 1.5                         # СКО зерна по яркости (мелко)
MOTTLE = 2.4                        # СКО пятна покрытия (крупно)
GRAIN_SIG, MOTTLE_SIG = 1.4, 9.0
BASE_IDX = 9
RUST = [(105, 77, 74), (92, 65, 64), (73, 49, 51)]     # цвета точек ржавчины классики (индексы 89-91)
LIGHT = (101, 99, 102)              # светлая крапина (индекс 8)


def lattice_noise(sig, seed):
    """Шум 160x128, непрерывный по решётке клеток: значение при сдвиге (64,32) и (64,-32) то же (нет шва на стыке)."""
    g = gs.grain_noise(128, sig=sig, seed=seed)
    t = g[gs.PER_Y0:gs.PER_Y0 + gs.PER_H]
    t = t + np.roll(np.roll(t, gs.PER_H // 2, 0), 64, 1)
    t = t / (t.std() + 1e-6)
    rows = (np.arange(160) - gs.PER_Y0) % gs.PER_H
    return t[rows]


def classic_spots(a):
    out = []
    for v, cl in ((89, "r"), (90, "r"), (91, "r"), (8, "l")):
        ys, xs = np.nonzero(a == v)
        out += [(y * 4 + 2, x * 4 + 2, cl) for y, x in zip(ys, xs)]
    return out


def random_spots(al, n_rust, n_light, rng):
    inner = ndi.binary_erosion(al > 0.5, iterations=16)
    ys, xs = np.nonzero(inner)
    pick = rng.choice(len(ys), n_rust + n_light, replace=False)
    return [(ys[i], xs[i], "r" if j < n_rust else "l") for j, i in enumerate(pick)]


def paint(rgb, pts, rng):
    yy, xx = np.mgrid[0:rgb.shape[0], 0:rgb.shape[1]].astype(np.float32)
    out = rgb.copy()
    for y, x, cl in pts:
        r = rng.uniform(2.2, 3.4)
        w = np.clip(1.4 - np.sqrt((yy - y) ** 2 + (xx - x) ** 2) / r, 0, 1) * 0.85
        col = np.array(RUST[rng.integers(0, 3)] if cl == "r" else LIGHT, np.float32)
        out = out * (1 - w[..., None]) + col * w[..., None]
    return out


def build_one(var):
    pal = wb.palette()
    a = wb.read_set(SET)[FR]
    al = gs.classic_alpha(a)
    base = pal[BASE_IDX][:3].astype(np.float32)
    lum = (lattice_noise(GRAIN_SIG, 70 + var) * GRAIN + lattice_noise(MOTTLE_SIG, 90 + var) * MOTTLE)
    rgb = np.clip(base[None, None, :] + lum[..., None], 0, 255)
    rng = np.random.default_rng(2510 + var)
    if var == 0:
        pts = classic_spots(a)
    else:
        pts = random_spots(al, int(np.isin(a, (89, 90, 91)).sum()), int((a == 8).sum()), rng)
    rgb = paint(rgb, pts, rng)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), al * 255]).round().astype(np.uint8), "RGBA")


def build_all():
    return {var: build_one(var) for var in range(4)}


def save_all(res):
    paths = {}
    for s, f in COPIES:
        if not np.array_equal(wb.read_set(s)[f], wb.read_set(SET)[FR]):
            raise SystemExit("%s:%d - классика не побайтно та же (R-272)" % (s, f))
    for s, f in [(SET, FR)] + COPIES:
        d = OUT / "TERRAIN" / (s + ".PCK")
        d.mkdir(parents=True, exist_ok=True)
        for var, im in res.items():
            name = "%d.png" % f if var == 0 else "%d.v%d.png" % (f, var)
            im.save(d / name)
            paths["TERRAIN/%s.PCK/%s" % (s, name)] = d / name
    return paths


def mockup(frames, n=3, seed=5, k=4):
    """Макет n x n соседних клеток крыши на сетке игры ((x-y)*16, (x+y)*8 базы), варианты по случайному узору."""
    rng = np.random.default_rng(seed)
    W, H = (2 * n) * 16 * k + 32 * k, (2 * n) * 8 * k + 40 * k
    im = Image.new("RGBA", (W, H), (22, 22, 26, 255))
    ox, oy = (n - 1) * 16 * k, 0
    order = [(x, y) for y in range(n) for x in range(n)]
    for x, y in order:
        fr = frames[int(rng.integers(0, len(frames)))]
        im.alpha_composite(fr, (ox + (x - y) * 16 * k, oy + (x + y) * 8 * k))
    return im


def stretch(im, gain=5.0):
    """Контраст вокруг среднего серого x gain - швы и полосы вылезают, если они есть."""
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    bg = (np.abs(a - np.array([22, 22, 26], np.float32)).sum(-1) < 1)
    m = a[~bg].mean(0)
    o = np.clip((a - m) * gain + 128, 0, 255)
    o[bg] = (40, 40, 44)
    return Image.fromarray(o.astype(np.uint8), "RGB")


def seam_metric(res):
    """Разрыв яркости на стыке: средний |перепад| между пикселями по две стороны от общей стороны ромба у соседних клеток,
    в сравнении с перепадом внутри клетки на том же расстоянии. Около 1 - шва нет."""
    rng = np.random.default_rng(11)
    out = []
    for var_a in range(4):
        for var_b in range(4):
            A = np.asarray(res[var_a].convert("L")).astype(np.float32)
            B = np.asarray(res[var_b].convert("L")).astype(np.float32)
            im = Image.new("L", (128 * 3, 160 * 3), 0)
            ca = Image.new("L", im.size, 0)
            ca.paste(Image.fromarray(A.astype(np.uint8)), (64, 0))
            ca.paste(Image.fromarray(B.astype(np.uint8)), (128, 32))     # соседка по (x+1, y): сдвиг (64, 32)
            msk = Image.new("L", im.size, 0)
            ma = np.asarray(res[var_a])[..., 3] > 250
            mb = np.asarray(res[var_b])[..., 3] > 250
            full = np.zeros(im.size[::-1], bool)
            full[0:160, 64:192] |= ma
            ov = np.zeros_like(full)
            ov[32:192, 128:256] = mb
            both = ndi.binary_dilation(full, iterations=2) & ndi.binary_dilation(ov, iterations=2)
            c = np.asarray(ca).astype(np.float32)
            gx = np.abs(np.diff(c, axis=1))
            gy = np.abs(np.diff(c, axis=0))
            gmag = np.zeros_like(c)
            gmag[:, :-1] += gx
            gmag[:-1, :] += gy
            inner = full & ov
            inner = ndi.binary_erosion(full, iterations=8) & ndi.binary_erosion(ov, iterations=8) | False
            seam = both & ~inner
            body = ndi.binary_erosion(full, iterations=8) | ndi.binary_erosion(ov, iterations=8)
            if seam.sum() and body.sum():
                out.append(gmag[seam].mean() / max(gmag[body].mean(), 1e-3))
    return float(np.mean(out)), float(np.max(out))


def make_sheet(res):
    sc = ts.Scene()
    key = (SET, FR)
    terr, block = "URBAN_WASTE", "URBANWASTE62"
    now = sc.render(terr, block, "hd", k=4, maxz=2)[0]
    cls = sc.render(terr, block, "classic", k=4, maxz=2)[0]
    saved = {v: sc._hd.get((SET, FR, v)) for v in range(5)}
    for var in range(4):
        sc._hd[(SET, FR, var)] = res[var]
    sc._hd[(SET, FR, 4)] = None
    new = sc.render(terr, block, "hd", k=4, maxz=2)[0]
    for var in range(5):
        sc._hd[(SET, FR, var)] = saved[var]
    found = [f for f in ts.find_cells(sc, terr, block, [key]) if f[3] == 2]
    cxs = sorted((f[2][0] + f[2][2]) / 2 for f in found)
    cys = sorted((f[2][1] + f[2][3]) / 2 for f in found)
    cx, cy = cxs[len(cxs) // 2] * 4, cys[len(cys) // 2] * 4
    box = (int(cx - 1000), int(cy - 700), int(cx + 400), int(cy + 100))
    frames = [res[v] for v in range(4)]
    mk = mockup(frames, n=3)
    old = [Image.open(ts.PACK / (SET + ".PCK") / "52.png").convert("RGBA")]
    mk_old = mockup(old, n=3)
    mk_cls = mockup([sc.classic(SET, FR)], n=3)
    mk9 = mockup(frames, n=4, seed=9)
    sm, sx = seam_metric(res)
    print("шов: средний перепад на стыке / внутри клетки = %.2f, худший %.2f (около 1 - шва нет)" % (sm, sx))
    panels = [("макет 3x3: классика", mk_cls), ("макет 3x3: HD сейчас (один кадр на всё)", mk_old),
              ("макет 3x3: новое, .png + .v1-.v3", mk),
              ("макет 3x3: новое, контраст x5 (швы вылезли бы здесь)", stretch(mk)),
              ("макет 4x4 (16 клеток): новое", mk9), ("макет 4x4: новое, контраст x5", stretch(mk9)),
              ("блок URBANWASTE62: классика", ts.crop_pad(cls, box)),
              ("блок URBANWASTE62: HD сейчас", ts.crop_pad(now, box)),
              ("блок URBANWASTE62: HD новое (без скоса, швов нет)", ts.crop_pad(new, box))]
    ts.sheet(panels, REVIEW / "t251_after2.png", cols=2, width=1000)
    col = Image.new("RGBA", (6 * 136, 164), (60, 60, 66, 255))
    for i, im in enumerate([sc.classic(SET, FR), sc.hd(SET, FR)] + [res[v] for v in range(4)]):
        col.alpha_composite(im, (i * 136, 0))
    ts.sheet([("URBAN_WASTE 52: классика | сейчас | новое .png .v1 .v2 .v3", col)], REVIEW / "t251_frames2.png", cols=1)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    res = build_all()
    paths = save_all(res)
    print("файлов: %d -> %s" % (len(paths), OUT))
    if a.sheet:
        make_sheet(res)
        print("лист:", REVIEW / "t251_after2.png")
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(paths, "t251_roof", "t251_roof.py 23.10 крыша без скоса, шум по решётке клеток + варианты",
                         "Vitali 23.10 (XP-000251); лист art/_review/tickets_2026-10-23/t251_after2.png",
                         "t251: крыша URBAN_WASTE 52 (+ WALLS 46) без белых штрихов и швов, варианты .v1-.v3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
