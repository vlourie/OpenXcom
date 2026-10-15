"""Слой 1 предметов инвентаря: B2 на кадры BIGOBS оружия, боеприпасов, медицины и гранат (слово Vitali 15.10).

Способ тот же, что принят для стен и MI-24 (wall_restore, wall_final_render): кадр не перерисовывается, а
увеличивается x4 так, что геометрия остаётся пиксель в пиксель:
  A   xbrz    xBRZ x4 продолженного кадра (wall_restore.xbrz_rgb);
  B2  esrgan  A плюс мелкая фактура Real-ESRGAN x4plus поправкой яркости (wall_restore.detail, DETAIL).
Альфа - всегда маска оригинала, перо xBRZ без заливки дыр (wall_section.sil4): скоба и просвет приклада
остаются просветом. Поправка стыка стен (sil4_frame) здесь не нужна - у предмета нет соседа по стыку.

Классика - выгрузка движка census/items/export/exp_piratez/BIGOBS.PCK.png: индексы и палитра, индекс 0
прозрачен (R-043), номер кадра - номер в игре (R-082). Список кадров - таблицы подготовки census/items/redo/
(inv_redo_prep.py): weapons, ammo, meds, grenades.

B2 грузит Real-ESRGAN на видеокарту - запуск только через очередь gpuq. --no-model даёт один A.
Готовые картинки пропускаются, прогон можно повторять. В мод ничего не кладёт.

  item_b2_render.py [--out census/items/redo/b2] [--no-model] [--limit N]
  item_b2_render.py --sheets [--out census/items/redo/b2]

Выход:
  <out>/xbrz/<кадр>.png, <out>/esrgan/<кадр>.png - 128x192 RGBA (k=4);
  <out>/pack/BIGOBS.PCK/<кадр>.wide.png - B2 общим файлом кадра с меткой у всех (make_pack: обрезка ровно по
    кадру классики); --pack пересобирает его из готовых B2 без модели;
  <out>/render.tsv - кадр, класс, предметы, клетки, вылет, пикселей;
  --sheets: <out>/sheet_<класс>_NN.png - оригинал x4 | B2 на тёмном фоне в размере k=4, с сеткой клеток.
"""
import argparse
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFont         # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(HERE))
REDO = "census/items/redo"
ATLAS = "census/items/export/exp_piratez/BIGOBS.PCK.png"
NONSTD = "census/items/originals/nonstandard/manifest.tsv"
FW, FH, COLS, K = 32, 48, 16, 4
TABLES = (("weapons.tsv", None), ("ammo.tsv", "ammo"), ("meds.tsv", "medical"), ("grenades.tsv", "grenade"))
ORDER = ("firearm", "melee", "ammo", "medical", "grenade")


def read_tsv(path):
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def frame_list():
    """Кадр -> класс (первого пользователя по ORDER), типы, клетки, вылет хотя бы у одного."""
    fr = {}
    for fn, cl in TABLES:
        for r in read_tsv(os.path.join(REDO, fn)):
            c = cl or r["class"]
            n = int(r["frame"])
            e = fr.setdefault(n, {"class": c, "types": [], "cells": r["cells"], "over": False})
            if ORDER.index(c) < ORDER.index(e["class"]):
                e["class"] = c
            e["types"].append(r["type"])
            if r["over_px"] not in ("", "0"):
                e["over"] = True
    return fr


class Atlas:
    """Кадр как в игре. Нестандартный одиночный файл (не 32x48) движок грузит своим размером
    (Surface::loadImage пересоздаёт поверхность, ExtraSprites.cpp:257), а HdItems ждёт картинку размера
    классики x k (HdItems.cpp:331) - такие кадры берутся из архива переписи originals/nonstandard своим
    размером: выгрузка их не содержит (ленивая загрузка, R-182) или обрезала до 32x48. Цвет - палитра
    выгрузки: индексы файла красит палитра набора, а не палитра файла."""

    def __init__(self):
        im = Image.open(ATLAS)
        assert im.mode == "P", im.mode
        self.idx = np.asarray(im)
        self.pal = np.array(im.getpalette()[:768], np.uint8).reshape(-1, 3)
        self.nonstd = {}
        for r in read_tsv(NONSTD):
            if r["set"] == "BIGOBS":
                self.nonstd[int(r["frame"])] = os.path.join("census/items", r["archive_file"])

    def frame(self, n):
        if n in self.nonstd:
            im = Image.open(self.nonstd[n])
            assert im.mode == "P", (n, im.mode)
            i = np.asarray(im)
        else:
            x, y = (n % COLS) * FW, (n // COLS) * FH
            i = self.idx[y:y + FH, x:x + FW]
        rgba = np.zeros(i.shape + (4,), np.uint8)
        rgba[..., :3] = self.pal[i]
        rgba[..., 3] = np.where(i == 0, 0, 255)
        return rgba


def to_img(rgb, alpha):
    return Image.fromarray(np.clip(np.dstack([rgb, alpha]) + 0.5, 0, 255).astype(np.uint8), "RGBA")


def render(a):
    import wall_restore as wr
    import wall_section as ws
    methods = ("xbrz",) if a.no_model else ("xbrz", "esrgan")
    for m in methods:
        os.makedirs(os.path.join(a.out, m), exist_ok=True)
    up = None
    if not a.no_model:
        import upscale_units as uu
        up = uu.Upscaler(wr.MODELS["esrgan"])
    at = Atlas()
    fr = frame_list()
    keys = sorted(fr)
    if a.limit:
        keys = keys[:a.limit]
    rows, done, t0 = [], 0, time.time()
    for i, n in enumerate(keys):
        e = fr[n]
        rgba = at.frame(n)
        mask = rgba[..., 3] > 0
        rows.append([str(n), e["class"], ",".join(e["types"]), e["cells"], "1" if e["over"] else "0", str(int(mask.sum()))])
        if not mask.any():
            continue
        paths = {m: os.path.join(a.out, m, "%d.png" % n) for m in methods}
        if all(os.path.exists(p) for p in paths.values()):
            continue
        src, _m = wr.filled(Image.fromarray(rgba, "RGBA"))
        alpha = np.clip(ws.sil4(mask) * 255.0, 0, 255)
        base = wr.xbrz_rgb(src)
        to_img(base, alpha).save(paths["xbrz"])
        if up is not None:
            b2 = to_img(wr.detail(base, wr.model_rgb(up, src), wr.DETAIL[0], wr.DETAIL[1], alpha), alpha)
            b2.save(paths["esrgan"])
        done += 1
        if (i + 1) % 200 == 0:
            print("кадров %d из %d (новых %d), %.0f с" % (i + 1, len(keys), done, time.time() - t0), flush=True)
    with open(os.path.join(a.out, "render.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("\t".join(["frame", "class", "types", "cells", "wide", "opaque_px"]) + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    empty = [r[0] for r in rows if r[5] == "0"]
    print("готово: кадров %d, новых %d, пустых %d, .wide %d, %.0f с" % (
        len(rows), done, len(empty), sum(1 for r in rows if r[4] == "1"), time.time() - t0), flush=True)
    if empty:
        # у предметов набора пустых кадров нет: пустой - дыра выгрузки (R-182), а не прозрачный предмет
        raise SystemExit("пустые кадры (нет в выгрузке и в originals/nonstandard, R-182): " + " ".join(empty))
    if up is not None:
        make_pack(a)


def make_pack(a):
    """Пак из готовых B2: каждый кадр - общий <кадр>.wide.png. B2 повторяет классику, а классика в сетке
    рисуется без обрезки и в 512 кадрах заходит на линии клеток; без метки HdItems режет картинку по клеткам
    за вычетом линий (setClip 1..xMax, HdItems.cpp), и HD потерял бы края, которые классика показывает.
    С меткой обрезка - ровно кадр классики: вылет только унаследованный от оригинала (решение Vitali 03.10)."""
    import item_asset_check as iac
    pack = os.path.join(a.out, "pack", "BIGOBS.PCK")
    os.makedirs(pack, exist_ok=True)
    # все пользователи кадра (любого класса, как в item_asset_check): допуск .wide должен держаться у каждого
    users = {}
    for r in read_tsv("census/items/items.tsv"):
        try:
            f, w, h = int(r["bigSprite"]), int(r["invWidth"] or 1), int(r["invHeight"] or 1)
        except ValueError:
            continue
        if f >= 0 and w > 0 and h > 0:
            users.setdefault(f, []).append((w, h))
    at = Atlas()
    keys = sorted(frame_list())
    have, trimmed = 0, 0
    for n in keys:
        src = os.path.join(a.out, "esrgan", "%d.png" % n)
        if not os.path.exists(src):
            raise SystemExit("нет B2 кадра %d - сначала рендер" % n)
        img = np.asarray(Image.open(src).convert("RGBA")).copy()
        o = at.frame(n)
        oh, ow = o.shape[:2]
        # перо B2 не дальше классики: за допуском .wide (рамка руки после сдвига) альфа остаётся только там,
        # где есть пиксель оригинала - движок там режет одинаково и классику-HD, и B2
        keep = np.zeros(img.shape[:2], bool)
        x0, y0, x1, y1 = 0, 0, ow, oh
        for w, h in users.get(n, []):
            rx0, ry0, rx1, ry1 = iac.wide_rect(w, h, (ow, oh))
            x0, y0, x1, y1 = max(x0, rx0), max(y0, ry0), min(x1, rx1), min(y1, ry1)
        keep[max(0, y0) * K:max(0, y1) * K, max(0, x0) * K:max(0, x1) * K] = True
        keep |= np.repeat(np.repeat(o[..., 3] > 0, K, 0), K, 1)
        cut = (img[..., 3] > 0) & ~keep
        if cut.any():
            trimmed += 1
            img[..., 3] = np.where(keep, img[..., 3], 0)
        for old in ("%d.png" % n, "%d.wide.png" % n):
            p = os.path.join(pack, old)
            if os.path.exists(p):
                os.remove(p)
        Image.fromarray(img, "RGBA").save(os.path.join(pack, "%d.wide.png" % n))
        have += 1
    print("пак: %d файлов <кадр>.wide.png в %s, перо подрезано до классики у %d" % (have, pack, trimmed), flush=True)


def font(size):
    for p in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def sheets(a, per_row=8, rows_per=5):
    """Оригинал x4 (NEAREST) и B2 рядом, тёмный фон инвентаря, сетка клеток 64x64 на k=4."""
    at = Atlas()
    fr = frame_list()
    ft, fs = font(22), font(15)
    # ячейка под самый широкий и высокий нестандартный кадр (44x53): вылет за 32x48 виден, а не обрезан
    tw, th, gap, lab = 44 * K, 53 * K, 10, 36
    cellw = 2 * tw + 6 + gap * 2
    cellh = th + lab + gap
    bg, grid = (22, 24, 28, 255), (60, 64, 72, 255)

    def tile(img, cells):
        t = Image.new("RGBA", (tw, th), bg)
        d = ImageDraw.Draw(t)
        cw, ch = (int(v) for v in cells.split("x"))
        d.rectangle((FW * K, 0, tw - 1, th - 1), fill=(17, 18, 21, 255))   # за кадром 32x48
        d.rectangle((0, FH * K, tw - 1, th - 1), fill=(17, 18, 21, 255))
        for x in range(cw):
            for y in range(ch):
                d.rectangle((x * 64, y * 64, x * 64 + 63, y * 64 + 63), outline=grid)
        t.alpha_composite(img, (0, 0))
        return t

    made = []
    for cl in ORDER:
        keys = [n for n in sorted(fr) if fr[n]["class"] == cl]
        per = per_row * rows_per
        for p in range(0, len(keys), per):
            chunk = keys[p:p + per]
            W = per_row * cellw + gap
            H = 44 + ((len(chunk) + per_row - 1) // per_row) * cellh
            out = Image.new("RGBA", (W, H), (12, 13, 16, 255))
            d = ImageDraw.Draw(out)
            pg = p // per + 1
            d.text((gap, 10), "%s, стр. %d: в каждой паре слева оригинал x4, справа B2 (k=4, размер в игре на 2560x1440)"
                   % (cl, pg), font=ft, fill=(235, 235, 235, 255))
            for j, n in enumerate(chunk):
                e = fr[n]
                x, y = gap + (j % per_row) * cellw, 44 + (j // per_row) * cellh
                o = at.frame(n)
                orig = Image.fromarray(o, "RGBA").resize((o.shape[1] * K, o.shape[0] * K), Image.NEAREST)
                p2 = os.path.join(a.out, "esrgan", "%d.png" % n)
                b2 = Image.open(p2).convert("RGBA") if os.path.exists(p2) else Image.new("RGBA", (tw, th))
                out.alpha_composite(tile(orig, e["cells"]), (x, y))
                out.alpha_composite(tile(b2, e["cells"]), (x + tw + 6, y))
                name = e["types"][0].replace("STR_", "")
                more = " +%d" % (len(e["types"]) - 1) if len(e["types"]) > 1 else ""
                d.text((x, y + th + 2), "%d%s %s" % (n, " wide" if e["over"] else "", e["cells"]), font=fs,
                       fill=(255, 190, 110, 255) if e["over"] else (160, 165, 175, 255))
                d.text((x, y + th + 18), (name + more)[:34], font=fs, fill=(220, 220, 200, 255))
            path = os.path.join(a.out, "sheet_%s_%02d.png" % (cl, pg))
            out.convert("RGB").save(path)
            made.append(path)
    print("листов %d" % len(made))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REDO, "b2"))
    ap.add_argument("--no-model", action="store_true", help="только A, модель не грузится")
    ap.add_argument("--limit", type=int, default=0, help="только первые N кадров (проба)")
    ap.add_argument("--sheets", action="store_true", help="только листы по готовым картинкам")
    ap.add_argument("--pack", action="store_true", help="только пак из готовых B2, модель не грузится")
    a = ap.parse_args()
    os.chdir(ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    if a.sheets:
        sheets(a)
    elif a.pack:
        make_pack(a)
    else:
        render(a)


if __name__ == "__main__":
    main()
