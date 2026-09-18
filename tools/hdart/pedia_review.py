#!/usr/bin/env python3
"""Puts every pedia picture next to the original it was made from, with the words of its article.

For each name it writes <out>\\<name>.png -- the mod's original on the left (x2, nearest, so the
pixels stay pixels) and the HD picture on the right, the same height -- and <out>\\<name>.txt with the
article's title and text (from pedia_text.py's json). A report.csv sorts them by how far the HD
picture drifted from the original: `colour` is the mean RGB distance after shrinking the HD picture
back to the classic size, `shape` is how well the two still agree on where the edges are (1 = the
same drawing, below ~0.5 = a different one).

    py -3 tools\\hdart\\pedia_text.py --mod "...\\mods\\Piratez" --out tools\\hdart\\pedia_text.json
    py -3 tools\\hdart\\pedia_review.py --hd "...\\mods\\hd\\hd\\UI" --orig "...\\mods\\Piratez\\Resources\\Pedia"
        --text tools\\hdart\\pedia_text.json --names rejected_files.txt --out review
"""
import argparse
import csv
import io
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

BASE_W, BASE_H = 320, 200


def flat(path, w=None, h=None):
    """The picture over black, RGB (the classic pictures keep index 0 transparent)."""
    im = Image.open(path)
    im = im.convert("RGBA")
    bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    if w and (im.width != w or im.height != h):
        im = im.resize((w, h), Image.LANCZOS)
    return im


def edges(a):
    g = np.asarray(a.convert("L").filter(ImageFilter.GaussianBlur(0.8)), dtype=np.float32)
    gy, gx = np.gradient(g)
    return np.hypot(gx, gy)


def drift(orig, hd):
    """(mean colour distance, edge correlation) of the HD picture shrunk back to the classic size."""
    small = hd.resize(orig.size, Image.LANCZOS)
    a = np.asarray(orig, dtype=np.float32)
    b = np.asarray(small, dtype=np.float32)
    colour = float(np.sqrt(((a - b) ** 2).sum(axis=2)).mean())
    ea, eb = edges(orig).ravel(), edges(small).ravel()
    ea = ea - ea.mean()
    eb = eb - eb.mean()
    den = float(np.sqrt((ea * ea).sum() * (eb * eb).sum()))
    shape = float((ea * eb).sum() / den) if den > 1e-6 else 0.0
    return colour, shape


def sheet(orig, hd, path, height=400):
    k = max(1, round(height / orig.height))
    left = orig.resize((orig.width * k, orig.height * k), Image.NEAREST)
    right = hd.resize((int(hd.width * left.height / hd.height), left.height), Image.LANCZOS)
    gap = 8
    out = Image.new("RGB", (left.width + gap + right.width, left.height), (24, 24, 24))
    out.paste(left, (0, 0))
    out.paste(right, (left.width + gap, 0))
    out.save(path)


def words_of(rec, langs):
    out = []
    for art in rec.get("articles", []):
        for code in langs:
            if art["title"].get(code):
                out.append("%s: %s" % (code, art["title"][code]))
        for code in langs:
            if art["text"].get(code):
                out.append("%s: %s" % (code, art["text"][code].replace("\n", " ")))
        out.append("")
    for s in rec.get("slides", []):
        for code in langs:
            if s["text"].get(code):
                out.append("slide %s: %s" % (code, s["text"][code].replace("\n", " ")))
    return "\n".join(out).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hd", required=True, help="folder with the HD pictures (hd\\UI)")
    ap.add_argument("--orig", required=True, help="folder with the mod's originals (Resources\\Pedia)")
    ap.add_argument("--text", default="", help="pedia_text.py's json (for the .txt next to each sheet)")
    ap.add_argument("--names", default="", help="only these pictures (a file with one name per line, or a comma list); default: all of --hd")
    ap.add_argument("--out", required=True, help="folder for the sheets")
    ap.add_argument("--lang", default="en-US,ru")
    ap.add_argument("--height", type=int, default=400, help="sheet height in pixels")
    ap.add_argument("--worst", type=int, default=0, help="keep only the N most drifted sheets")
    ap.add_argument("--no-sheets", action="store_true", help="only measure the drift, write report.csv")
    args = ap.parse_args()

    langs = [c.strip() for c in args.lang.split(",") if c.strip()]
    text = {}
    if args.text and os.path.exists(args.text):
        text = json.load(io.open(args.text, encoding="utf-8"))

    if args.names:
        if os.path.exists(args.names):
            names = [l.strip() for l in io.open(args.names, encoding="utf-8") if l.strip()]
        else:
            names = [n.strip() for n in args.names.split(",") if n.strip()]
    else:
        names = sorted(f for f in os.listdir(args.hd) if f.lower().endswith(".png") and not f.lower().endswith(".pal.txt"))

    origs = {}
    for f in os.listdir(args.orig):
        origs.setdefault(os.path.splitext(f)[0].lower(), f)
    hds = {}
    for f in os.listdir(args.hd):
        if f.lower().endswith(".png"):
            hds.setdefault(os.path.splitext(f)[0].lower(), f)

    os.makedirs(args.out, exist_ok=True)
    rows = []
    missing = []
    for n in names:
        key = os.path.splitext(n)[0].lower()
        h = hds.get(key)
        hd_path = os.path.join(args.hd, h) if h else ""
        o = origs.get(key)
        if not o or not h:
            missing.append(n)
            continue
        orig = flat(os.path.join(args.orig, o))
        hd = flat(hd_path)
        colour, shape = drift(orig, hd)
        rows.append({"name": key, "file": o, "colour": round(colour, 1), "shape": round(shape, 3),
                     "title": (text.get(key, {}).get("articles") or [{}])[0].get("title", {}).get("en-US", "")})
        if not args.no_sheets:
            sheet(orig, hd, os.path.join(args.out, key + ".png"), args.height)
            if key in text:
                with io.open(os.path.join(args.out, key + ".txt"), "w", encoding="utf-8") as f:
                    f.write(words_of(text[key], langs) + "\n")
    rows.sort(key=lambda r: r["shape"])
    if args.worst and not args.no_sheets:
        for r in rows[args.worst:]:
            for ext in (".png", ".txt"):
                p = os.path.join(args.out, r["name"] + ext)
                if os.path.exists(p):
                    os.remove(p)
        rows = rows[:args.worst]
    with io.open(os.path.join(args.out, "report.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "file", "colour", "shape", "title"])
        w.writeheader()
        w.writerows(rows)
    print("sheets: %d -> %s" % (len(rows), args.out))
    if missing:
        print("no original or no HD picture: %d (%s%s)" % (len(missing), ", ".join(missing[:10]),
                                                           " ..." if len(missing) > 10 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
