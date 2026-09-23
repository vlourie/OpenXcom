#!/usr/bin/env python3
"""
hdtest_compare.py - compare two HD-render test dumps made with the in-game
hotkey (Options: keyBattleHdTestDump, default F8, pressed with Ctrl).

A dump is three files in the OpenXcom user folder:
    hdtestNNN_map.png    map surface, base resolution, before any scaling
    hdtestNNN_frame.png  whole base-resolution frame (UI included, no cursor)
    hdtestNNN.json       state that produced them (camera, resolution, k, mods)

Usage (PowerShell):
    python tools\\hdtest_compare.py <dumpA> <dumpB> [options]

<dumpA>/<dumpB> are dump prefixes (path without extension, e.g.
"C:\\Users\\user\\Documents\\OpenXcom\\hdtest000") or two PNG files.

Options:
    --scale N      nearest-neighbour upscale dump A by N before comparing
                   (stage 2 check: baseline k=1 vs. new build at k=N)
    --map-only     compare only the *_map.png pair (skip UI frame)
    --frame-only   compare only the *_frame.png pair
    --out DIR      where to write diff images (default: next to dump B)
    --no-diff      do not write diff images
    --quiet        print only the verdict lines

Exit code: 0 = identical, 1 = differences found, 2 = error.

Only Pillow is required:  pip install pillow
"""
import argparse
import json
import os
import sys

try:
    from PIL import Image, ImageChops
except ImportError:
    print("error: Pillow is required:  pip install pillow", file=sys.stderr)
    sys.exit(2)


def load_rgb(path):
    im = Image.open(path)
    return im.convert("RGB")


def resolve_pair(a, b):
    """Return list of (label, pathA, pathB) pairs to compare and the json paths."""
    if a.lower().endswith(".png") or b.lower().endswith(".png"):
        return [("image", a, b)], None, None
    pairs = []
    for suffix in ("_map.png", "_frame.png"):
        pa, pb = a + suffix, b + suffix
        if os.path.exists(pa) and os.path.exists(pb):
            pairs.append((suffix[1:-4], pa, pb))
        elif os.path.exists(pa) != os.path.exists(pb):
            print("warning: %s exists only on one side" % suffix, file=sys.stderr)
    return pairs, a + ".json", b + ".json"


def compare_json(ja, jb, quiet, scale=1):
    if not (ja and jb and os.path.exists(ja) and os.path.exists(jb)):
        return True
    with open(ja, "r", encoding="utf-8") as f:
        da = json.load(f)
    with open(jb, "r", encoding="utf-8") as f:
        db = json.load(f)
    # keys that make a pixel comparison meaningless when they differ
    critical = ("master", "mods", "save", "cameraOffsetX", "cameraOffsetY", "cameraOffsetZ",
                "viewLevel", "showAllLayers", "baseWidth", "baseHeight", "iconHeight",
                "nightVision", "debugVisionMode", "fadeShade", "globalShade", "turn", "side", "debugMode")
    # with --scale N the world-pixel values of A are expected to be N times smaller
    scaled = ("cameraOffsetX", "cameraOffsetY", "spriteWidth", "spriteHeight", "mapSurfaceWidth", "mapSurfaceHeight", "k", "worldScale")
    ok = True
    # stage 3c: the HD mode of the canvas; dumps from before it exist were always "nearest" (0),
    # and any other mode changes the picture on purpose, so it cannot be compared
    for d in (da, db):
        d.setdefault("hdMode", 0)
    if da["hdMode"] != 0 or db["hdMode"] != 0:
        print("!! hdMode A=%r B=%r: only HD mode 0 (nearest) is meant to be pixel-identical (F9 cycles the mode)" % (da["hdMode"], db["hdMode"]))
        ok = False
    for key in sorted(set(da) | set(db)):
        if key in ("drawMs", "flipMs", "hdThreads"):
            continue  # profiling figures, not state
        va, vb = da.get(key), db.get(key)
        if scale > 1 and key in scaled and isinstance(va, int) and isinstance(vb, int):
            if key in ("k", "worldScale"):
                va = (va or 1) * scale
            else:
                va = va * scale
        if key == "mods" and isinstance(va, list) and isinstance(vb, list):
            # the HD test mod only switches the scale, it is not a content difference
            va = [m for m in va if m not in ("hd_test", "hd_demo")]
            vb = [m for m in vb if m not in ("hd_test", "hd_demo")]
        if va != vb:
            flag = "!!" if key in critical else "  "
            if key in critical:
                ok = False
            if not quiet or key in critical:
                print("%s %-18s A=%r  B=%r" % (flag, key, va, vb))
    if not ok:
        print("!! critical state differs (camera/save/mods/resolution) - pixel diff below is not meaningful")
    return ok


def compare_images(label, pa, pb, scale, out_dir, write_diff, quiet):
    a = load_rgb(pa)
    b = load_rgb(pb)
    if scale > 1:
        a = a.resize((a.width * scale, a.height * scale), Image.NEAREST)
    if a.size != b.size:
        print("[%s] size differs: A=%dx%d  B=%dx%d  -> DIFFERENT" % (label, a.width, a.height, b.width, b.height))
        return False

    diff = ImageChops.difference(a, b)
    bbox = diff.getbbox()
    if bbox is None:
        print("[%s] IDENTICAL  (%dx%d)" % (label, a.width, a.height))
        return True

    # count differing pixels: max over channels, then non-zero count
    r, g, bch = diff.split()
    mask = ImageChops.lighter(ImageChops.lighter(r, g), bch).point(lambda v: 255 if v else 0)
    hist = mask.histogram()
    changed = hist[255]
    total = a.width * a.height
    print("[%s] DIFFERENT: %d of %d pixels (%.3f%%), bbox x=%d..%d y=%d..%d"
          % (label, changed, total, 100.0 * changed / total, bbox[0], bbox[2] - 1, bbox[1], bbox[3] - 1))

    if not quiet:
        # coarse map of where the differences are (16x16 cells of the image)
        cols, rows = 16, 8
        cw, ch = max(1, a.width // cols), max(1, a.height // rows)
        small = mask.resize((cols, rows), Image.BOX)
        px = small.load()
        print("    diff map (%dx%d px cells, '#' = many, '.' = few, ' ' = none):" % (cw, ch))
        for y in range(rows):
            line = "".join("#" if px[x, y] > 64 else ("." if px[x, y] > 0 else " ") for x in range(cols))
            print("    |" + line + "|")

    if write_diff:
        base = os.path.splitext(os.path.basename(pb))[0]
        out_dir = out_dir or os.path.dirname(os.path.abspath(pb))
        out = os.path.join(out_dir, base + "_diff.png")
        # side by side: A | B | highlighted differences on darkened B
        dark = b.point(lambda v: v // 3)
        red = Image.new("RGB", b.size, (255, 0, 0))
        hl = Image.composite(red, dark, mask)
        sheet = Image.new("RGB", (a.width * 3, a.height), (0, 0, 0))
        sheet.paste(a, (0, 0))
        sheet.paste(b, (a.width, 0))
        sheet.paste(hl, (a.width * 2, 0))
        sheet.save(out)
        print("    diff image: %s  (A | B | differences)" % out)
    return False


def main():
    ap = argparse.ArgumentParser(description="Compare two HD-render test dumps.")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--map-only", action="store_true")
    ap.add_argument("--frame-only", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-diff", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    pairs, ja, jb = resolve_pair(args.a, args.b)
    if args.map_only:
        pairs = [p for p in pairs if p[0] == "map"]
    if args.frame_only:
        pairs = [p for p in pairs if p[0] == "frame"]
    if not pairs:
        print("error: nothing to compare (check the prefixes: expected <prefix>_map.png / _frame.png)", file=sys.stderr)
        return 2

    state_ok = compare_json(ja, jb, args.quiet, args.scale)
    all_same = True
    for label, pa, pb in pairs:
        try:
            same = compare_images(label, pa, pb, args.scale, args.out, not args.no_diff, args.quiet)
        except Exception as e:
            print("error comparing %s: %s" % (label, e), file=sys.stderr)
            return 2
        all_same = all_same and same

    if all_same and state_ok:
        print("RESULT: IDENTICAL")
        return 0
    print("RESULT: DIFFERENT")
    return 1


if __name__ == "__main__":
    sys.exit(main())
