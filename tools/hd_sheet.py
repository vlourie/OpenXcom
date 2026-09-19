# -*- coding: utf-8 -*-
r"""Лист сравнения «оригинал | как вышло» по ГОТОВЫМ кадрам мода.

    python tools\hd_sheet.py --sets BEACH,GDXOPSFLOORS
    python tools\hd_sheet.py --random 8
    python tools\hd_sheet.py --sets ASHEN1 --frames 0,1,63,70

Пути по умолчанию — под X-Piratez, менять ключами --data / --hd / --palette.

Зачем: painted_x4.png в hdart_sheets — это лист ДО build_pack, то есть до маски оригинала и
до chroma lock. По нему нельзя судить ни о цвете, ни о силуэте: пол там выглядит позеленевшим
или расплывшимся, а в готовом паке всё на месте. Сверять надо по кадрам в самом моде
(<hd>\hd\TERRAIN\<НАБОР>.PCK\<N>.png) — их и собирает этот скрипт.

Результат кладётся в _cmp\<НАБОР>.png: папка неглубокая, её видно через мост Cowork,
в отличие от кадров мода (восемь уровней вложенности, мост берёт семь).
"""

import argparse
import os
import random
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import xcom_sprites as xs  # noqa: E402

PZ = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods")
BG = (40, 40, 46)


def original_frames(data, name):
    """Кадры набора из мода, в его палитре."""
    for ext in (".PCK", ".pck"):
        pck = os.path.join(data, "TERRAIN", name + ext)
        if os.path.exists(pck):
            tab = os.path.join(data, "TERRAIN", name + (".TAB" if ext == ".PCK" else ".tab"))
            return xs.read_pck(pck, tab if os.path.exists(tab) else None)
    return []


def packed_dir(hd, name):
    return os.path.join(hd, "hd", "TERRAIN", name + ".PCK")


def on_bg(img, size=None):
    if size and img.size != size:
        img = img.resize(size, Image.LANCZOS)
    b = Image.new("RGBA", img.size, BG + (255,))
    b.alpha_composite(img.convert("RGBA"))
    return b.convert("RGB")


def build(name, data, hd, pal, frames_wanted, max_w, max_h):
    pdir = packed_dir(hd, name)
    if not os.path.isdir(pdir):
        return None, "нет покрашенного набора: %s" % pdir
    orig = original_frames(data, name)
    if not orig:
        return None, "нет исходного набора %s в %s" % (name, data)

    have = []
    for i in range(len(orig)):
        p = os.path.join(pdir, "%d.png" % i)
        if os.path.exists(p) and orig[i]:
            have.append(i)
    if frames_wanted:
        have = [i for i in have if i in frames_wanted]
    if not have:
        return None, "%s: нечего показывать" % name

    first = Image.open(os.path.join(pdir, "%d.png" % have[0]))
    W, H = first.size
    cols = max(1, min(8, (max_w - 8) // (2 * W)))
    rows = (len(have) + cols - 1) // cols
    pair = 2 * W
    im = Image.new("RGB", (cols * pair + (cols - 1) * 6, rows * H), (12, 12, 12))
    for n, i in enumerate(have):
        x = (n % cols) * (pair + 6)
        y = (n // cols) * H
        o = xs.frame_to_image(orig[i], pal).convert("RGBA").resize((W, H), Image.NEAREST)
        im.paste(on_bg(o), (x, y))
        im.paste(on_bg(Image.open(os.path.join(pdir, "%d.png" % i)), (W, H)), (x + W, y))
    k = min(1.0, float(max_w) / im.width, float(max_h) / im.height)
    if k < 1:
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    return im, "%s: %d кадр(ов), пар в ряду %d" % (name, len(have), cols)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(PZ, "Piratez"), help="папка мода-источника")
    ap.add_argument("--hd", default=os.path.join(PZ, "hd"), help="папка HD-мода")
    ap.add_argument("--palette", default=os.path.join(PZ, "Piratez", "Resources", "Pals", "delicious_regular.pal"))
    ap.add_argument("--sets", default="", help="через запятую")
    ap.add_argument("--random", type=int, default=0, help="взять N случайных уже покрашенных наборов")
    ap.add_argument("--frames", default="", help="только эти кадры, через запятую")
    ap.add_argument("--out", default="_cmp")
    ap.add_argument("--max-width", type=int, default=1400, dest="max_w")
    ap.add_argument("--max-height", type=int, default=2400, dest="max_h")
    args = ap.parse_args(argv)

    pal = xs.load_palette_file(args.palette, battlescape_fix=True) if args.palette else xs.load_palette()
    names = [s.strip().upper().replace(".PCK", "") for s in args.sets.split(",") if s.strip()]
    if args.random:
        root = os.path.join(args.hd, "hd", "TERRAIN")
        pool = sorted(d[:-4] for d in os.listdir(root)
                      if d.upper().endswith(".PCK") and os.path.isdir(os.path.join(root, d)))
        names += random.sample(pool, min(args.random, len(pool)))
    if not names:
        raise SystemExit("нужен --sets или --random")
    frames_wanted = set(int(v) for v in args.frames.split(",") if v.strip()) if args.frames else None

    os.makedirs(args.out, exist_ok=True)
    for name in names:
        im, msg = build(name, args.data, args.hd, pal, frames_wanted, args.max_w, args.max_h)
        if im is None:
            print(msg)
            continue
        p = os.path.join(args.out, name + ".png")
        im.save(p)
        print("%s -> %s" % (msg, p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
