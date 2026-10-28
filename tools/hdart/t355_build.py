# -*- coding: utf-8 -*-
r"""Тикет XP-000355 (выбор Vitali: вариант A): прорезь у верхнего края асфальта и пунктир в тумане.

Причина (art): у HD-кадров асфальта ROADS:9 и ROADS:13 (и перекрасок-копий в 8 наборах) нет верха ромба - 96 HD-пикселей
(ряды 100-107 по x 56-71 в кадре 128x160), где классика непрозрачна. Клетка выше обычно закрывает дыру своим выступом, но на
кромке асфальт|земля над клеткой нет соседа-асфальта - виден фон (при oxceHdBackdrop - градиент, в тумане пунктиром).

Лечение: альфа верхушки дополнена до силуэта классики (классика непрозрачна, а HD прозрачна), ничего больше не меняется.
Цвет новых пикселей - по соседям (нормированная свёртка непрозрачных пикселей кадра, как кромка ROADS_WASTE 0-8 в XP-000352),
зерно асфальта - остаток (пиксель минус размытие) с лежащего ниже участка кадра, не копирование столбца: вертикального
штриха нет. Остальные пиксели кадра (в том числе RGB прозрачных) не трогаются - работа идемпотентна.

Семья (ticket_family.py, R-457) - 12 кадров и все варианты .v1-.v3 = 48 файлов, из 8 разных картинок (две основы x 4 версии):
  A (md5 b5b57373): ROADS:9, ROADSGREEN:8, ROADSLUX:9, CYBERWAREAN:9, FREIGHTER_MAIN:0, METRO1:9, RUSTSHACKS:19,
                    THULBASES03:93, XOPSDESERTRUINS:33
  B (md5 f83f46ed): ROADS:13, ROADSGREEN:12, ROADSLUX:13
Кадры 10-12 (разметка) не трогаются. Копии выводятся из одной картинки группы побайтно (проверка в конце).

    py -3.13 tools\hdart\t355_build.py            # кадры в art/_review/tickets_2026-10-28/t355_install/ + MANIFEST.json
    py -3.13 tools\hdart\t355_build.py --install --yes   # + в мод hd через манифест (по слову Vitali, под очередью правок)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ticket_scene as ts                 # noqa: E402

ROOT = HERE.parent.parent
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-28"
INST = REVIEW / "t355_install"

GROUPS = {
    "A": [("ROADS", 9), ("ROADSGREEN", 8), ("ROADSLUX", 9), ("CYBERWAREAN", 9), ("FREIGHTER_MAIN", 0), ("METRO1", 9),
          ("RUSTSHACKS", 19), ("THULBASES03", 93), ("XOPSDESERTRUINS", 33)],
    "B": [("ROADS", 13), ("ROADSGREEN", 12), ("ROADSLUX", 13)],
}
VARIANTS = (0, 1, 2, 3)               # 0 - сам кадр, 1-3 - .v1-.v3
SIG_FILL = 3.5                        # размытие цвета по соседям, пикс HD
SIG_GRAIN = 1.6                       # зерно = пиксель минус такое размытие
GRAIN_DY = 8                          # откуда брать зерно: на столько строк ниже, со сдвигом по x в сторону от оси
GRAIN_DX = 14


def rel_of(s, f, v):
    return "TERRAIN/%s.PCK/%s" % (s, "%d.png" % f if v == 0 else "%d.v%d.png" % (f, v))


def _norm_conv(img, w, sig):
    """Нормированная свёртка: img (H,W,3), w (H,W) 0/1 - среднее по известным пикселям."""
    num = np.dstack([ndi.gaussian_filter(img[..., c] * w, sig, mode="constant") for c in range(3)])
    den = ndi.gaussian_filter(w, sig, mode="constant")
    return num / np.maximum(den, 1e-6)[..., None], den


def patch(hd, cls_alpha):
    """hd - RGBA uint8 128x160 (HD кадр), cls_alpha - bool 160x128 (классика x4 непрозрачна).
    -> (новый RGBA, маска достроенных пикселей)."""
    hd = hd.copy()
    known = hd[..., 3] > 0
    miss = cls_alpha & ~known
    if not miss.any():
        return hd, miss
    rgb = hd[..., :3].astype(np.float32)
    w = known.astype(np.float32)
    base, den = _norm_conv(rgb, w, SIG_FILL)
    # там, где известных рядом совсем мало - большее размытие
    far, _ = _norm_conv(rgb, w, SIG_FILL * 3)
    base = np.where((den < 0.02)[..., None], far, base)
    # зерно асфальта: остаток известных пикселей (пиксель минус размытие), с участка ниже, в сторону от оси x=64
    blur, _ = _norm_conv(rgb, w, SIG_GRAIN)
    res = (rgb - blur) * w[..., None]
    ys, xs = np.where(miss)
    out = hd.copy()
    for y, x in zip(ys, xs):
        sx = x - GRAIN_DX if x < 64 else x + GRAIN_DX
        sy = y + GRAIN_DY
        g = res[sy, sx] if known[sy, sx] else 0.0
        out[y, x, :3] = np.clip(base[y, x] + g, 0, 255).round().astype(np.uint8)
        out[y, x, 3] = 255
    return out, miss


def build():
    sc = ts.Scene()
    INST.mkdir(parents=True, exist_ok=True)
    files, report = {}, []
    for g, members in GROUPS.items():
        cls = np.asarray(sc.classic(*members[0]))[..., 3] > 0
        for v in VARIANTS:
            src = sc.hd(members[0][0], members[0][1], v)
            assert src is not None, (g, v)
            new, miss = patch(np.asarray(src).copy(), cls)
            report.append((g, v, int(miss.sum())))
            # все члены группы с этим вариантом должны быть побайтно одной картинкой
            for s, f in members:
                other = sc.hd(s, f, v)
                assert np.array_equal(np.asarray(other), np.asarray(src)), ("члены группы разошлись", s, f, v)
                rel = rel_of(s, f, v)
                p = INST / rel.replace("/", "\\")
                p.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(new, "RGBA").save(p, optimize=False)
                files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    for g, v, n in report:
        print("группа %s вариант %d: достроено %d пикс" % (g, v, n))
    (INST / "MANIFEST.json").write_text(json.dumps({"files": files}, ensure_ascii=False, indent=0, sort_keys=True),
                                        encoding="utf-8-sig")
    # побайтные копии внутри группы и версии
    for g, members in GROUPS.items():
        for v in VARIANTS:
            hs = {files[rel_of(s, f, v)] for s, f in members}
            assert len(hs) == 1, (g, v, hs)
    print("файлов %d, копии внутри группы побайтно равны" % len(files))
    return files


def install(yes):
    from PIL import Image as _I
    with open(INST / "MANIFEST.json", encoding="utf-8-sig") as fh:
        man = json.load(fh)
    files = {}
    for rel, h in man["files"].items():
        p = INST / rel.replace("/", "\\")
        assert hashlib.sha256(p.read_bytes()).hexdigest() == h, rel + ": хэш не совпал (пересобери t355_build.py)"
        im = _I.open(p)
        assert im.size == (128, 160) and im.mode == "RGBA", (rel, im.size, im.mode)
        files[rel] = p
    assert len(files) == 48, len(files)
    print("файлов:", len(files))
    if not yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (по слову Vitali, под очередью правок)")
    n = ts.install_files(files, "t355_build",
                         "t355_build.py 28.10: верх ромба асфальта достроен до силуэта классики, цвет по соседям",
                         "Vitali 28.10: вариант A по тикету XP-000355; лист art/_review/tickets_2026-10-28/t355_fix_sheet.png",
                         "t355: асфальт ROADS:9/13 и копии (12 кадров, 48 файлов) - верх ромба по классике")
    print("установлено файлов:", n)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    build()
    if a.install:
        install(a.yes)
