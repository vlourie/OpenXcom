"""Кукла бойца, слой 1: B2 на каждый слой куклы инвентаря (docs/research/doll-hd-2026-10-20.md, слово Vitali 20.10).

Способ тот же, что принят для предметов инвентаря и стен (item_b2_render, wall_restore): слой не перерисовывается,
а увеличивается x4 на своём месте холста 320x200, так что все слои одной расы садятся друг на друга пиксель
в пиксель (тела расы - один манекен, общая одежда одна на все внешности):
  A   xbrz    xBRZ x4 продолженного слоя (wall_restore.xbrz_rgb);
  B2  esrgan  A плюс мелкая фактура Real-ESRGAN x4plus поправкой яркости (wall_restore.detail).
Альфа - всегда маска оригинала, перо xBRZ (wall_section.sil4), без заливки дыр.

Классика - картинки слоёв из рулсетов Пираток (extraSprites typeSingle), читаются ИНДЕКСАМИ (R-043): индекс 0
прозрачен, цвет - палитра боя Пираток (палитра выгрузки BIGOBS = delicious_regular, её же берёт инвентарь,
setStandardPalette("PAL_BATTLESCAPE")), а не палитра GIF-файла - в файле кожа жёлтая, в игре коричневая.
Список слоёв - те, что берут брони (layersDefinition после слияния, .index/mod/Piratez/rul/values.tsv).

B2 грузит Real-ESRGAN на видеокарту - запуск только через очередь gpuq. --no-model даёт один A.
Готовые картинки пропускаются, прогон можно повторять. В мод ничего не кладёт без --install.

  doll_b2_render.py --list                          таблица слоёв census/dolls/layers.tsv
  doll_b2_render.py [--no-model] [--limit N] [--names a,b]   рендер в art/doll/b2/<способ>/
  doll_b2_render.py --sheets [--armors A:F0,B:M3]   листы сравнения art/doll/b2/sheet_NN.png
  doll_b2_render.py --install <мод> [--method esrgan] картинки и .pal.txt в <мод>/hd/UI (после выбора Vitali)

Выход рендера: <out>/<способ>/<имя слоя в нижнем регистре>.png - 1280x800 RGBA (k=4, весь холст: движок берёт
картинку целым кратным классики, HdUiArt), <out>/palette.pal.txt - палитра, с которой они сделаны.
"""
import argparse
import csv
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFont         # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(HERE))
MOD = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez")
VALUES = os.path.join(ROOT, ".index", "mod", "Piratez", "rul", "values.tsv")
PALETTE_SRC = os.path.join(ROOT, "census", "items", "export", "exp_piratez", "BIGOBS.PCK.png")
OUT = os.path.join(ROOT, "art", "doll", "b2")
TABLE = os.path.join(ROOT, "census", "dolls", "layers.tsv")
W, H, K = 320, 200, 4
MARGIN = 8                # поле вокруг рамки слоя при увеличении, пикселей базы
# листы по умолчанию: частые расы, открытые и закрытые брони (доля кожи и одежды разная)
SHEET_ARMORS = ("STR_ADVENTURER_OUTFIT_UC:F0", "STR_AMAZON_ARMOR_UC:M5", "STR_AGGRESSOR_ARMOR_UC:F3",
                "STR_ANNIHILATOR_ARMOR_SEA_UC:M2")


def sprite_files():
    """Имя картинки (typeSingle) -> путь файла, по всем рулсетам мода."""
    res = {}
    rdir = os.path.join(MOD, "Ruleset")
    for fn in sorted(os.listdir(rdir)):
        if not fn.endswith(".rul"):
            continue
        txt = open(os.path.join(rdir, fn), encoding=ENC, errors="replace").read()
        for t, f in re.findall(r"typeSingle:\s*(\S+)\s*\n\s*fileSingle:\s*(\S+)", txt):
            res[t] = os.path.join(MOD, f.strip("'\""))
    return res


def armor_layers():
    """Броня -> {ключ внешности: [имена слоёв по порядку]} - так же, как Armor::afterLoad склеивает имя."""
    defs, prefix, specific = {}, {}, {}
    with open(VALUES, encoding=ENC) as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4 or p[0] != "armors":
                continue
            if p[2] == "layersDefinition":
                defs[p[1]] = json.loads(p[3])
            elif p[2] == "layersDefaultPrefix":
                prefix[p[1]] = json.loads(p[3])
            elif p[2] == "layersSpecificPrefix":
                specific[p[1]] = {int(k): v for k, v in json.loads(p[3]).items()}
    res = {}
    for arm, d in defs.items():
        if not prefix.get(arm):
            continue
        res[arm] = {key: ["%s__%d__%s" % (specific.get(arm, {}).get(i, prefix[arm]), i, it)
                          for i, it in enumerate(items) if it] for key, items in d.items()}
    return res


def game_palette():
    im = Image.open(PALETTE_SRC)
    assert im.mode == "P", im.mode
    return np.array((im.getpalette() + [0] * 768)[:768], np.uint8).reshape(256, 3)


def load_indices(path):
    im = Image.open(path)
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    assert im.mode == "P", (path, im.mode)
    idx = np.asarray(im)
    assert idx.shape == (H, W), (path, idx.shape)
    return idx


def to_rgba(idx, pal):
    rgba = np.zeros(idx.shape + (4,), np.uint8)
    rgba[..., :3] = pal[idx]
    rgba[..., 3] = np.where(idx == 0, 0, 255)
    return rgba


def used_layers(files):
    arms = armor_layers()
    use = {}
    for arm, keys in arms.items():
        for key, names in keys.items():
            for n in names:
                use.setdefault(n, set()).add(arm)
    missing = sorted(n for n in use if n not in files or not os.path.exists(files[n]))
    return use, missing


def cmd_list(a):
    files = sprite_files()
    use, missing = used_layers(files)
    os.makedirs(os.path.dirname(TABLE), exist_ok=True)
    rows = []
    for n in sorted(use):
        if n in missing:
            continue
        idx = load_indices(files[n])
        ys, xs = np.nonzero(idx)
        bbox = "%d,%d,%d,%d" % (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1) if len(xs) else ""
        race, layer = n.split("__")[0], n.split("__")[1]
        rows.append([n, race, layer, str(len(use[n])), str(len(xs)), bbox, os.path.relpath(files[n], MOD)])
    with open(TABLE, "w", encoding=ENC, newline="") as f:
        f.write("\t".join(["name", "race", "layer", "armors", "opaque_px", "bbox", "file"]) + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    print("слоёв %d (пустых %d), нет файла %d: %s" % (len(rows), sum(1 for r in rows if r[4] == "0"),
                                                       len(missing), " ".join(missing[:10])))


def render_layer(rgba, up, wr, ws):
    """Слой 320x200 RGBA -> {способ: RGBA 1280x800}: увеличивается только рамка слоя с полем."""
    mask = rgba[..., 3] > 0
    ys, xs = np.nonzero(mask)
    x0, y0 = max(0, xs.min() - MARGIN), max(0, ys.min() - MARGIN)
    x1, y1 = min(W, xs.max() + 1 + MARGIN), min(H, ys.max() + 1 + MARGIN)
    crop = rgba[y0:y1, x0:x1]
    src, cmask = wr.filled(Image.fromarray(crop, "RGBA"))
    alpha = np.clip(ws.sil4(cmask) * 255.0, 0, 255)
    base = wr.xbrz_rgb(src)
    res = {"xbrz": base}
    if up is not None:
        res["esrgan"] = wr.detail(base, wr.model_rgb(up, src), wr.DETAIL[0], wr.DETAIL[1], alpha)
    out = {}
    for m, rgb in res.items():
        canvas = np.zeros((H * K, W * K, 4), np.uint8)
        canvas[y0 * K:y1 * K, x0 * K:x1 * K] = np.clip(np.dstack([rgb, alpha]) + 0.5, 0, 255).astype(np.uint8)
        out[m] = canvas
    return out


def cmd_render(a):
    import wall_restore as wr
    import wall_section as ws
    files = sprite_files()
    use, missing = used_layers(files)
    names = sorted(n for n in use if n not in missing)
    if a.names:
        want = set(a.names.split(","))
        names = [n for n in names if n in want]
    if a.armors:
        arms = armor_layers()
        want = {n for p in a.armors.split(",") for n in arms[p.split(":")[0]][p.split(":")[1]]}
        names = [n for n in names if n in want]
    if a.limit:
        names = names[:a.limit]
    methods = ("xbrz",) if a.no_model else ("xbrz", "esrgan")
    for m in methods:
        os.makedirs(os.path.join(a.out, m), exist_ok=True)
    pal = game_palette()
    with open(os.path.join(a.out, "palette.pal.txt"), "w", encoding="ascii", newline="\n") as f:
        f.write("".join("%d %d %d\n" % tuple(c) for c in pal))
    up = None
    if not a.no_model:
        import upscale_units as uu
        up = uu.Upscaler(wr.MODELS["esrgan"])
    t0, done, empty = time.time(), 0, 0
    for i, n in enumerate(names):
        paths = {m: os.path.join(a.out, m, n.lower() + ".png") for m in methods}
        if all(os.path.exists(p) for p in paths.values()):
            continue
        rgba = to_rgba(load_indices(files[n]), pal)
        if not (rgba[..., 3] > 0).any():
            empty += 1   # лысые причёски: пустая картинка - пустая и в HD (движку нужен файл у каждого слоя)
            for p in paths.values():
                Image.new("RGBA", (W * K, H * K)).save(p, optimize=True)
            continue
        for m, img in render_layer(rgba, up, wr, ws).items():
            Image.fromarray(img, "RGBA").save(paths[m], optimize=True)
        done += 1
        if (i + 1) % 100 == 0:
            el = time.time() - t0
            print("слоёв %d из %d (новых %d), %.0f с, осталось ~%.0f мин" % (
                i + 1, len(names), done, el, el / (i + 1) * (len(names) - i - 1) / 60), flush=True)
    print("готово: слоёв %d, новых %d, пустых %d, нет файла %d, %.0f с" % (
        len(names), done, empty, len(missing), time.time() - t0), flush=True)


def over(dst, src):
    a = src[..., 3:4].astype(np.float32) / 255.0
    dst[..., :3] = src[..., :3] * a + dst[..., :3] * (1 - a)
    dst[..., 3:4] = np.maximum(dst[..., 3:4], src[..., 3:4])


def font(size):
    for p in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def cmd_sheets(a):
    import wall_section as ws
    files = sprite_files()
    arms = armor_layers()
    pal = game_palette()
    picks = (a.armors.split(",") if a.armors else list(SHEET_ARMORS))
    methods = [m for m in ("xbrz", "esrgan") if os.path.isdir(os.path.join(a.out, m))]
    cols = ["классика x4", "сейчас (xBRZ склейки)"] + ["слои: " + m for m in methods]
    # рамка фигуры на холсте: x 40-140, y 0-160 базы покрывают все расы (doll-hd-2026-10-20.md)
    cx0, cy0, cx1, cy1 = 36, 0, 140, 160
    tw, th = (cx1 - cx0) * K, (cy1 - cy0) * K
    tiles = []
    for pick in picks:
        arm, key = pick.split(":")
        names = arms[arm][key]
        comp = np.zeros((H, W, 4), np.float32)
        layers = {m: np.zeros((H * K, W * K, 4), np.float32) for m in methods}
        for n in names:
            over(comp, to_rgba(load_indices(files[n]), pal).astype(np.float32))
            for m in methods:
                p = os.path.join(a.out, m, n.lower() + ".png")
                if os.path.exists(p):
                    over(layers[m], np.asarray(Image.open(p).convert("RGBA"), np.float32))
        c8 = Image.fromarray(np.clip(comp, 0, 255).astype(np.uint8), "RGBA")
        row = [c8.resize((W * K, H * K), Image.NEAREST), ws.xbrz(c8, K)]
        row += [Image.fromarray(np.clip(layers[m] + 0.5, 0, 255).astype(np.uint8), "RGBA") for m in methods]
        tiles.append((pick, row))
    sheet = Image.new("RGB", (tw * len(cols), (th + 24) * len(tiles) + 24), (16, 15, 20))
    d = ImageDraw.Draw(sheet)
    f = font(14)
    for j, c in enumerate(cols):
        d.text((j * tw + 8, 6), c, fill=(220, 220, 220), font=f)
    for i, (pick, row) in enumerate(tiles):
        y = 24 + i * (th + 24)
        d.text((8, y + 4), pick, fill=(200, 190, 140), font=f)
        for j, t in enumerate(row):
            bg = Image.new("RGBA", t.size, (24, 22, 30, 255))
            bg.alpha_composite(t)
            sheet.paste(bg.crop((cx0 * K, cy0 * K, cx1 * K, cy1 * K)).convert("RGB"), (j * tw, y + 20))
    os.makedirs(a.out, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(a.out, "sheet_%02d.png" % n)):
        n += 1
    p = os.path.join(a.out, "sheet_%02d.png" % n)
    sheet.save(p)
    print(p)


def cmd_install(a):
    """Картинки способа в <мод>/hd/UI: <имя>.png и <имя>.pal.txt (палитра, с которой сделаны: движок
    перекрашивает их в палитру экрана - педия, погода боя). Только после выбора Vitali."""
    src = os.path.join(a.out, a.method)
    dst = os.path.join(a.install, "hd", "UI")
    os.makedirs(dst, exist_ok=True)
    pal = open(os.path.join(a.out, "palette.pal.txt"), encoding="ascii").read()
    n = 0
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".png"):
            continue
        shutil.copyfile(os.path.join(src, fn), os.path.join(dst, fn))
        with open(os.path.join(dst, fn[:-4] + ".pal.txt"), "w", encoding="ascii", newline="\n") as f:
            f.write(pal)
        n += 1
    print("в %s положено %d картинок" % (dst, n))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--sheets", action="store_true")
    ap.add_argument("--armors", default="")
    ap.add_argument("--install", default="")
    ap.add_argument("--method", default="esrgan")
    ap.add_argument("--no-model", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--names", default="")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.list:
        cmd_list(a)
    elif a.sheets:
        cmd_sheets(a)
    elif a.install:
        cmd_install(a)
    else:
        cmd_render(a)


if __name__ == "__main__":
    main()
