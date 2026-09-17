#!/usr/bin/env python3
"""
A stand-in for the painted sheet: the original sheet upscaled with a smooth
filter and sharpened, so that the whole path sheet -> pack -> game can be
tried before any real HD art exists.

    py -3 placeholder_sheet.py --sheets <sheets folder> --set CULTIVAT.PCK [--out painted.png]
"""
import argparse
import json
import os

from PIL import Image, ImageFilter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheets", required=True)
    ap.add_argument("--set", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    set_dir = os.path.join(args.sheets, args.set.upper())
    with open(os.path.join(set_dir, "layout.json")) as f:
        info = json.load(f)
    k = info["scale"]
    orig = Image.open(os.path.join(set_dir, "original.png")).convert("RGBA")
    # premultiplied upscale so that transparent black does not darken the edges
    r, g, b, a = orig.split()
    pre = Image.merge("RGBA", [Image.composite(c, Image.new("L", c.size, 0), a) for c in (r, g, b)] + [a])
    big = pre.resize((orig.width * k, orig.height * k), Image.LANCZOS)
    br, bg, bb, ba = big.split()
    # un-premultiply
    px = {}
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    o = out.load()
    pr, pg, pb, pa = br.load(), bg.load(), bb.load(), ba.load()
    for y in range(big.height):
        for x in range(big.width):
            al = pa[x, y]
            if al:
                o[x, y] = (min(255, pr[x, y] * 255 // al), min(255, pg[x, y] * 255 // al), min(255, pb[x, y] * 255 // al), al)
    out = out.filter(ImageFilter.UnsharpMask(radius=k, percent=80, threshold=2))
    path = args.out or os.path.join(set_dir, "placeholder_x%d.png" % k)
    out.save(path)
    print("wrote", path, out.size)


if __name__ == "__main__":
    main()
