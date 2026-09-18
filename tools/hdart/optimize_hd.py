#!/usr/bin/env python3
r"""
Makes the HD mod's pictures smaller without changing what the game shows.

    <venv>\Scripts\python.exe tools\hdart\optimize_hd.py --mod user\mods\hd [--dry-run]
        [--mode palette|lossless] [--min-psnr 34] [--only UI] [--skip GLOBE] [--jobs 16] [--level 3]

Three things, in this order, for every PNG under <mod>\hd - and for every picture inside a
`pack.hdp` (the one-file pack of a unit set, which is rebuilt with the smaller pictures):

1. A picture with no transparent pixel keeps its alpha channel for nothing - it is written without one
   (a quarter less data before compression). A picture whose colours already fit a palette (256 or
   fewer) is written as a palette PNG: same pixels, smaller file.
2. `--mode palette` (the default) also gives the remaining pictures a 256-colour palette with
   dithering. The engine reads the file the same way (lodepng converts any PNG to RGBA), and the
   error is measured before the file is kept: the picture is composited over grey exactly where
   something is drawn and compared with the original, and a picture that comes out worse than
   `--min-psnr` decibels keeps its full colours. `--mode lossless` never quantizes.
3. Everything is recompressed losslessly (oxipng when `pip install pyoxipng` is there, else zlib at
   its strongest through Pillow).

Nothing else changes: the size of the picture, the frame it belongs to and its name stay as they are,
and the `.pal.txt` files next to the interface pictures are left alone. The run is safe to repeat -
a file that cannot be made smaller is left as it is - and `--dry-run` only measures.

Typical: the ufopaedia pictures (hd\UI, ~1.2 MB each) come down to about a quarter, terrain frames to
about an eighth, the unit packs to about two thirds; photographs (hd\GLOBE) are only recompressed,
since a palette would band them.
"""
import argparse
import io
import os
import shutil
import struct
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import numpy as np
from PIL import Image

try:
    import oxipng
except ImportError:
    oxipng = None

try:
    import imagequant          # libimagequant, the palettes of pngquant without the .exe
except ImportError:
    imagequant = None

# photographs: a palette would band them, so these folders are only recompressed
PHOTO_DIRS = ("GLOBE",)


def visible_psnr(orig, test):
    """How far two pictures are apart where something is drawn, composited over grey as the game
    shows them (dB; 99 = the same picture)."""
    a = np.asarray(orig.convert("RGBA"), np.float32)
    b = np.asarray(test.convert("RGBA"), np.float32)
    if a.shape != b.shape:
        return 0.0
    bg = np.float32(128.0)
    ca = a[..., :3] * (a[..., 3:] / 255) + bg * (1 - a[..., 3:] / 255)
    cb = b[..., :3] * (b[..., 3:] / 255) + bg * (1 - b[..., 3:] / 255)
    vis = a[..., 3] > 8
    if not vis.any():
        return 99.0
    mse = float(((ca - cb)[vis] ** 2).mean())
    return 99.0 if mse <= 0 else float(10 * np.log10(255 * 255 / mse))


def to_png(im, level=1):
    """PNG bytes. The default level is the fast one: this is only the picture on its way to the
    quantizer and to oxipng, which pack it properly at the end."""
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=(level >= 9), compress_level=level)
    return buf.getvalue()


def squeeze(data, level):
    """The last lossless pass over the file's bytes."""
    if oxipng is None:
        return data
    try:
        return oxipng.optimize_from_memory(data, level=level, strip=oxipng.StripChunks.safe())
    except Exception:
        return data


def quantize(im, raw, colors, pngquant):
    """The picture with at most `colors` colours, as PNG bytes (None when it cannot be done). Best first:
    libimagequant (pip install imagequant), then pngquant on the machine, then Pillow's own quantizer -
    Pillow is the fastest but the coarsest, the other two keep about 1.5 dB more."""
    if imagequant is not None:
        try:
            return to_png(imagequant.quantize_pil_image(im.convert("RGBA"), dithering_level=1.0, max_colors=colors))
        except Exception:
            pass
    if pngquant:
        try:
            r = subprocess.run([pngquant, "--quality", "0-100", "--speed", "1", "--force", str(colors), "-"],
                               input=raw, capture_output=True, timeout=120)
            if r.returncode == 0 and r.stdout[:8] == b"\x89PNG\r\n\x1a\n":
                return r.stdout
        except Exception:
            pass
    try:
        method = Image.MEDIANCUT if im.mode == "RGB" else Image.FASTOCTREE
        return to_png(im.quantize(colors=colors, method=method, dither=Image.FLOYDSTEINBERG))
    except Exception:
        return None


def best_png(rgba, args, pngquant, photo=False):
    """The smallest bytes of one picture: without the alpha channel when nothing is transparent, with a
    palette when that costs less than --min-psnr, packed by oxipng at the end."""
    opaque = rgba.getextrema()[3][0] == 255      # nothing transparent: the alpha channel is dead weight
    plain = rgba.convert("RGB") if opaque else rgba
    raw = to_png(plain)
    few = plain.getcolors(maxcolors=256) is not None   # fits a palette as it is: no loss at all
    if not photo and (few or args.mode == "palette"):
        pal = quantize(plain, raw, 256, pngquant)
        if pal and len(pal) < len(raw):
            need = 60.0 if few else args.min_psnr
            if visible_psnr(rgba, Image.open(io.BytesIO(pal))) >= need:
                return squeeze(pal, args.level), ("same colours" if few else "palette")
    return squeeze(raw, args.level), "packed"


PACK_MAGIC = b"OXHDPCK1"


def optimize_bytes(blob, args, pngquant, photo=False):
    """One picture's bytes, made smaller; the old bytes when nothing helps."""
    try:
        im = Image.open(io.BytesIO(blob))
        im.load()
    except Exception:
        return blob
    best, _ = best_png(im.convert("RGBA"), args, pngquant, photo)
    return best if len(best) < len(blob) else blob


def optimize_pack(path, args, pngquant):
    """A unit set's pack.hdp: every picture in it is made smaller and the pack is written again
    (same frames, same order, new offsets)."""
    old = os.path.getsize(path)
    data = open(path, "rb").read()
    if len(data) < 24 or data[:8] != PACK_MAGIC:
        return old, old, "not a pack"
    scale, base_w, base_h, count = struct.unpack_from("<4I", data, 8)
    table_end = 24 + count * 12
    if count == 0 or table_end > len(data):
        return old, old, "pack is cut short"
    entries = [struct.unpack_from("<3I", data, 24 + i * 12) for i in range(count)]
    blobs, seen = [], {}
    for index, off, size in entries:
        if off + size > len(data) or size == 0:
            return old, old, "pack is cut short"
        key = (off, size)
        if key not in seen:
            seen[key] = optimize_bytes(data[off:off + size], args, pngquant)
        blobs.append((index, key))
    out = bytearray(data[:24])
    body, offsets, pos = bytearray(), {}, table_end
    for key, blob in seen.items():
        offsets[key] = pos
        body += blob
        pos += len(blob)
    for index, key in blobs:
        out += struct.pack("<3I", index, offsets[key], len(seen[key]))
    out += body
    if len(out) >= old:
        return old, old, "already small (%d frames)" % count
    if not args.dry_run:
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(out)
        os.replace(tmp, path)
    return old, len(out), "%d frames" % count


def optimize_file(path, args, pngquant):
    """Returns (old size, new size, what was done)."""
    old = os.path.getsize(path)
    try:
        im = Image.open(path)
        im.load()
    except Exception as e:
        return old, old, "not a picture (%s)" % e
    photo = any(part.upper() in PHOTO_DIRS for part in os.path.normpath(path).split(os.sep))
    best, note = best_png(im.convert("RGBA"), args, pngquant, photo)
    if len(best) >= old:
        return old, old, "already small"
    if not args.dry_run:
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(best)
        os.replace(tmp, path)
    return old, len(best), note


_ARGS = None
_PNGQUANT = None


def _init_worker(args, pngquant):
    global _ARGS, _PNGQUANT
    _ARGS, _PNGQUANT = args, pngquant


def _work(path):
    if path.lower().endswith(".hdp"):
        return optimize_pack(path, _ARGS, _PNGQUANT)
    return optimize_file(path, _ARGS, _PNGQUANT)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mod", required=True, help="the mod folder (its hd\\ subfolder is walked)")
    ap.add_argument("--mode", choices=["palette", "lossless"], default="palette",
                    help="palette: also give big pictures a 256-colour palette when it costs less than "
                         "--min-psnr; lossless: never change a pixel")
    ap.add_argument("--min-psnr", type=float, default=34.0,
                    help="how close a palette version must stay (dB over the drawn pixels); higher = more careful")
    ap.add_argument("--only", default="", help="only these subfolders of hd\\, comma separated (UI, TERRAIN, ...)")
    ap.add_argument("--skip", default="", help="skip these subfolders of hd\\")
    ap.add_argument("--jobs", type=int, default=0, help="how many pictures at a time (default: one per core)")
    ap.add_argument("--level", type=int, default=1, help="oxipng effort 0-6; 1 is within about 1%% of 3 and "
                    "runs three times faster, 6 is very slow")
    ap.add_argument("--dry-run", action="store_true", help="only measure, write nothing")
    args = ap.parse_args()

    root = os.path.join(args.mod, "hd")
    if not os.path.isdir(root):
        ap.error("no %s - point --mod at the mod folder (the one with metadata.yml)" % root)
    only = {p.strip().upper() for p in args.only.split(",") if p.strip()}
    skip = {p.strip().upper() for p in args.skip.split(",") if p.strip()}
    files = []
    for folder, _, names in os.walk(root):
        rel = os.path.relpath(folder, root)
        top = rel.split(os.sep)[0].upper() if rel != "." else ""
        if (only and top not in only) or (top and top in skip):
            continue
        files.extend(os.path.join(folder, n) for n in names
                     if n.lower().endswith(".png") or n.lower() == "pack.hdp")
    if not files:
        print("no pictures under", root)
        return 0
    pngquant = shutil.which("pngquant") or None
    jobs = args.jobs or (os.cpu_count() or 4)
    quantizer = ("imagequant" if imagequant is not None else
                 ("pngquant" if pngquant else "Pillow (coarser: pip install imagequant)"))
    print("%d file(s) under %s | quantizer: %s | oxipng: %s | mode: %s | %d job(s)%s" % (
        len(files), root, quantizer,
        "yes" if oxipng else "no (pip install pyoxipng for smaller files)", args.mode,
        jobs, " (dry run)" if args.dry_run else ""))
    t0 = time.time()
    total_old = total_new = 0
    done = 0
    per_dir = {}
    # one process per job: Pillow and the quantizer hold the interpreter lock, so threads would all
    # sit on one core (Windows: the workers import this file again, which is why the work is a plain function)
    try:
        pool = ProcessPoolExecutor(max_workers=jobs, initializer=_init_worker, initargs=(args, pngquant))
    except Exception as e:
        print("  (no process pool: %s; falling back to threads)" % e)
        _init_worker(args, pngquant)
        pool = ThreadPoolExecutor(max_workers=jobs)
    with pool:
        for path, (old, new, note) in zip(files, pool.map(_work, files, chunksize=4)):
            total_old += old
            total_new += new
            rel = os.path.relpath(path, root)
            top = rel.split(os.sep)[0]
            d = per_dir.setdefault(top, [0, 0, 0])
            d[0] += old
            d[1] += new
            d[2] += 1
            done += 1
            if done <= 5 or done % 200 == 0:
                print("  %-44s %8d -> %8d  %s" % (rel[-44:], old, new, note))
    print("\n%-14s %10s %10s %7s %6s" % ("folder", "before", "after", "saved", "files"))
    for top, (old, new, n) in sorted(per_dir.items(), key=lambda kv: -kv[1][0]):
        print("%-14s %9.1fM %9.1fM %6.0f%% %6d" % (top or ".", old / 1e6, new / 1e6,
                                                   100 - new * 100 / max(old, 1), n))
    print("%-14s %9.1fM %9.1fM %6.0f%% %6d   in %.0f s" % ("all", total_old / 1e6, total_new / 1e6,
                                                           100 - total_new * 100 / max(total_old, 1), len(files), time.time() - t0))
    if args.dry_run:
        print("dry run: nothing was written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
