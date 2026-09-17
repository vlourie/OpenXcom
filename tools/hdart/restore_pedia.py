#!/usr/bin/env python3
"""Rebuilds a mod's 8-bit pictures from the HD (x4, 32-bit) pictures upscale_ui.py made of them.

For when the originals are gone: every <name>.png of --hd (a 32-bit picture, a whole multiple of the
classic size) becomes the classic-size 8-bit indexed image again, with the palette from <name>.pal.txt
(next to the picture, or in --pal). Each block of k x k HD pixels becomes one pixel: transparent blocks
(the original's index 0) stay index 0, the others take the nearest palette colour. The result is close
to the original (same size, same palette, same layout) but not pixel-exact: the super-resolution model
melted the dithering, so dithered gradients come back as flat nearest colours.

The original file names (with their .png / .gif extensions) come from --names, a text file with one
name per line, so a picture that was AIRCAR_CPAL.gif is written as AIRCAR_CPAL.gif again; without the
list everything is written as .png.

    py -3 tools\\hdart\\restore_pedia.py --hd <folder with the HD pictures> --pal user\\mods\\hd\\hd\\UI --names tools\\hdart\\pedia_names.txt --out Pedia_restored
"""
import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image


def load_palette(path):
    pal = []
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3:
                pal.append([int(parts[0]), int(parts[1]), int(parts[2])])
    if len(pal) != 256:
        return None
    return np.array(pal, dtype=np.int32)


def restore(hd_path, palette, base_w=320, base_h=200):
    im = Image.open(hd_path).convert("RGBA")
    if im.width % base_w != 0 or im.height % base_h != 0 or im.width // base_w != im.height // base_h:
        # not a whole multiple of 320x200: guess the factor from the width
        k = max(1, round(im.width / base_w))
    else:
        k = im.width // base_w
    w, h = im.width // k, im.height // k
    a = np.asarray(im, dtype=np.float32)[:h * k, :w * k]
    # the mean of each k x k block (colour and alpha)
    blocks = a.reshape(h, k, w, k, 4).mean(axis=(1, 3))
    rgb = blocks[:, :, :3]
    alpha = blocks[:, :, 3]
    # nearest palette colour (indices 1..255; index 0 is the transparent one), squared distance
    flat = rgb.reshape(-1, 3)
    pal = palette[1:].astype(np.float32)
    idx = np.empty(flat.shape[0], dtype=np.uint8)
    step = 16384
    for i in range(0, flat.shape[0], step):
        chunk = flat[i:i + step]
        d = ((chunk[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)
        idx[i:i + step] = d.argmin(axis=1).astype(np.uint8) + 1
    idx = idx.reshape(h, w)
    idx[alpha < 128] = 0
    out = Image.fromarray(idx, "P")
    out.putpalette(palette.astype(np.uint8).flatten().tolist())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hd", required=True, help="folder with the HD pictures (<name>.png)")
    ap.add_argument("--pal", default="", help="folder with the <name>.pal.txt palettes (default: next to the pictures)")
    ap.add_argument("--names", default="", help="text file with the original file names, one per line (for .gif / .png)")
    ap.add_argument("--out", required=True, help="folder for the rebuilt 8-bit images")
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--height", type=int, default=200)
    args = ap.parse_args()

    originals = {}
    if args.names and os.path.exists(args.names):
        for line in open(args.names, encoding="utf-8"):
            n = line.strip()
            if n:
                originals[os.path.splitext(n)[0].lower()] = n
    os.makedirs(args.out, exist_ok=True)
    files = sorted(glob.glob(os.path.join(args.hd, "*.png")))
    done = 0
    missing_pal = []
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        pal_path = os.path.join(args.pal or args.hd, name + ".pal.txt")
        palette = load_palette(pal_path) if os.path.exists(pal_path) else None
        if palette is None:
            missing_pal.append(name)
            continue
        out_name = originals.get(name.lower(), name + ".png")
        out = restore(path, palette, args.width, args.height)
        out_path = os.path.join(args.out, out_name)
        if out_name.lower().endswith(".gif"):
            # optimize=False keeps the palette order (the game maps indices to its own palette)
            out.save(out_path, format="GIF", optimize=False)
        else:
            out.save(out_path, format="PNG", optimize=True)
        done += 1
        if done % 100 == 0:
            print("%d/%d" % (done, len(files)))
    print("done: %d rebuilt -> %s" % (done, args.out))
    if missing_pal:
        print("no palette (.pal.txt) for %d picture(s), skipped:" % len(missing_pal), ", ".join(missing_pal[:20]), "..." if len(missing_pal) > 20 else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
