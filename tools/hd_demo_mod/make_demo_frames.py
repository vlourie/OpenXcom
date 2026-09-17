#!/usr/bin/env python3
"""
Generates the demo HD frames of the hd_demo mod (stage 3c of the HD renderer).

    py -3 make_demo_frames.py [--smoke <path to Smoke_DIO.gif>] [--scale 4]

Two kinds of frames are made, both as RGBA PNGs the engine picks up from
hd/<set>/<index>.png when the frame size matches the k-scaled sprite:

  hd/CURSOR.PCK/0..5.png  - the battlescape cursor box, drawn as antialiased
                            lines (0/1/2: back half in red/yellow/blue,
                            3/4/5: front half). Synthetic: no original art used.
  hd/SMOKE.PCK/8..19.png  - the twelve smoke frames as soft translucent clouds,
                            derived from a smoke sprite sheet (the checkerboard
                            dithering of the palette art becomes real alpha).
                            Only made when --smoke points at a sheet of 32x40
                            frames, 10 per row (X-Piratez' Smoke_DIO.gif).

Requires Pillow.
"""
import argparse
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    print("error: Pillow is required (py -3 -m pip install pillow)")
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))


def make_cursor_frames(k, out_dir):
    """The wireframe box the classic cursor draws: a 32x40 frame holds a 32x16
    floor rhombus at the bottom, the same rhombus 24 pixels higher, and the
    four vertical edges between them. Frame 0-2: the edges behind a unit,
    3-5: the edges in front of it."""
    colors = {0: (255, 72, 72), 1: (255, 232, 96), 2: (96, 148, 255)}
    W, H = 32 * k, 40 * k
    ss = 4  # supersampling for the antialiasing
    L, T, R, B = (0, 32), (16, 24), (32, 32), (16, 40)
    up = 24

    def p(pt, dy=0):
        return ((pt[0]) * k * ss, (pt[1] - dy) * k * ss)

    back = [(L, T), (T, R), ((16, 0), (16, 24)), ((0, 8), (0, 32)), ((32, 8), (32, 32)),
            ((L[0], L[1] - up), (T[0], T[1] - up)), ((T[0], T[1] - up), (R[0], R[1] - up))]
    front = [(L, B), (B, R), ((16, 16), (16, 40)),
             ((L[0], L[1] - up), (B[0], B[1] - up)), ((B[0], B[1] - up), (R[0], R[1] - up))]
    width = max(2, int(round(1.4 * k * ss)))
    for frame in range(6):
        color = colors[frame % 3]
        edges = back if frame < 3 else front
        big = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        for a, b in edges:
            ax, ay = p(a)
            bx, by = p(b)
            # keep the line inside the frame
            ax = min(max(ax, width / 2), W * ss - width / 2 - 1)
            bx = min(max(bx, width / 2), W * ss - width / 2 - 1)
            ay = min(max(ay, width / 2), H * ss - width / 2 - 1)
            by = min(max(by, width / 2), H * ss - width / 2 - 1)
            d.line([(ax, ay), (bx, by)], fill=color + (255,), width=width)
            r = width / 2
            for cx, cy in ((ax, ay), (bx, by)):
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (255,))
        im = big.resize((W, H), Image.LANCZOS)
        # a faint dark halo so the box reads on bright ground too
        halo = im.split()[3].filter(ImageFilter.GaussianBlur(0.6 * k))
        halo_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        halo_img.putalpha(halo.point(lambda v: int(v * 0.45)))
        out = Image.alpha_composite(halo_img, im)
        out.save(os.path.join(out_dir, "%d.png" % frame))
    print("cursor: 6 frames, %dx%d" % (W, H))


def make_smoke_frames(k, sheet_path, out_dir):
    sheet = Image.open(sheet_path)
    pal = sheet.getpalette()
    idx = sheet.convert("P") if sheet.mode != "P" else sheet
    cols = sheet.size[0] // 32
    made = 0
    for frame in range(8, 20):
        x0, y0 = (frame % cols) * 32, (frame // cols) * 40
        cell = idx.crop((x0, y0, x0 + 32, y0 + 40))
        px = cell.load()
        # coverage and color of the palette art
        mask = Image.new("L", (32, 40), 0)
        rgb = Image.new("RGB", (32, 40), (0, 0, 0))
        mp, cp = mask.load(), rgb.load()
        for y in range(40):
            for x in range(32):
                i = px[x, y]
                if i:
                    mp[x, y] = 255
                    cp[x, y] = (pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2])
        W, H = 32 * k, 40 * k
        mask_k = mask.resize((W, H), Image.NEAREST)
        rgb_k = rgb.resize((W, H), Image.NEAREST)
        # soft coverage: the checkerboard (50 % of the pixels) blurs to half density
        sigma = 0.75 * k
        cov = mask_k.filter(ImageFilter.GaussianBlur(sigma))
        # color where there was no pixel: spread the neighbours' color over the holes
        weighted = Image.merge("RGB", [c.filter(ImageFilter.GaussianBlur(sigma)) for c in rgb_k.split()])
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        op = out.load()
        covp, wp = cov.load(), weighted.load()
        for y in range(H):
            for x in range(W):
                c = covp[x, y]
                if c < 8:
                    continue
                r, g, b = wp[x, y]
                # undo the coverage weighting of the color blur
                r, g, b = min(255, r * 255 // c), min(255, g * 255 // c), min(255, b * 255 // c)
                a = min(255, int(c * 1.45))
                a = int(a * 0.82)
                op[x, y] = (r, g, b, a)
        out.save(os.path.join(out_dir, "%d.png" % frame))
        made += 1
    print("smoke: %d frames, %dx%d" % (made, W, H))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--smoke", default="", help="smoke sprite sheet (32x40 frames, 10 per row) to make hd/SMOKE.PCK from")
    args = ap.parse_args()
    cursor_dir = os.path.join(HERE, "hd", "CURSOR.PCK")
    os.makedirs(cursor_dir, exist_ok=True)
    make_cursor_frames(args.scale, cursor_dir)
    if args.smoke:
        smoke_dir = os.path.join(HERE, "hd", "SMOKE.PCK")
        os.makedirs(smoke_dir, exist_ok=True)
        make_smoke_frames(args.scale, args.smoke, smoke_dir)


if __name__ == "__main__":
    main()
