#!/usr/bin/env python3
"""Faithful super-resolution of a mod's pictures (Ufopaedia illustrations, screens) into hd/UI.

Every PNG/GIF of --dir (or the files of --files) becomes hd/UI/<name>.png (+ <name>.pal.txt) in --mod:
the picture --scale times its size, made with a Real-ESRGAN-type model (loaded by spandrel from the
--model file). Such a model is a deterministic upscaler: it sharpens and adds fine detail but keeps the
content as it is (no diffusion, nothing is invented: text, faces, layout stay). Without a model
(--no-model, or no torch) the picture is a smooth upscale.

The engine finds a picture by the image's name in the mod (an extraSprites type) or by the file name of
a single-image sprite, so a picture of Resources/Pedia/AAP_002.png is hd/UI/AAP_002.png.

    tools\\hdart\\.venv\\Scripts\\python.exe tools\\hdart\\upscale_ui.py --dir <mod>\\Resources\\Pedia --mod user\\mods\\hd --model E:\\models\\RealESRGAN_x4plus.pth

Model: RealESRGAN_x4plus.pth from https://github.com/xinntao/Real-ESRGAN/releases (v0.1.0), or any 4x
model spandrel loads (4x-UltraSharp, RealESRGAN_x4plus_anime_6B for drawn pictures...). Install once:
    tools\\hdart\\.venv\\Scripts\\python.exe -m pip install spandrel

--scale 4 is what the game shows on a 1080p-1440p display (a 320x200 picture at 1280x800); --scale 8
(two passes, 2560x1600) is for 4K displays and costs four times the disk. --dedither melts the palette
dithering of the sources a little before the model sees it (0 = off).
"""
import argparse
import glob
import os
import sys
import time

import numpy as np
from PIL import Image, ImageFilter


def load_indexed(path):
    """An image as (indices HxW uint8 or None, palette 256x3 or None, rgb HxWx3, alpha HxW or None)."""
    im = Image.open(path)
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    if im.mode == "P":
        pal = im.getpalette() or []
        pal = (pal + [0] * 768)[:768]
        palette = np.array(pal, dtype=np.uint8).reshape(256, 3)
        idx = np.array(im, dtype=np.uint8)
        rgb = palette[idx]
        return idx, palette, rgb, None
    if im.mode in ("RGBA", "LA"):
        rgba = np.array(im.convert("RGBA"))
        return None, None, rgba[:, :, :3].copy(), rgba[:, :, 3].copy()
    rgb = np.array(im.convert("RGB"))
    return None, None, rgb, None


class Upscaler:
    """A spandrel model (x4) on the GPU, or nothing (smooth upscale)."""

    def __init__(self, model_path, want):
        self.model = None
        self.factor = 1
        self.device = "cpu"
        if not model_path:
            return
        import torch
        from spandrel import ModelLoader
        desc = ModelLoader().load_from_file(model_path)
        self.factor = int(desc.scale)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        desc = desc.to(self.device).eval()
        self.half = self.device == "cuda" and desc.supports_half
        if self.half:
            desc = desc.half()
        self.model = desc
        self.torch = torch
        print("model:", os.path.basename(model_path), "x%d" % self.factor, "on", self.device, "(fp16)" if self.half else "")

    def run(self, rgb):
        """One pass of the model over an RGB uint8 image (tiled when big)."""
        torch = self.torch
        h, w = rgb.shape[:2]
        tile, overlap = 512, 16
        if max(h, w) <= tile + overlap:
            return self._run_tile(rgb)
        f = self.factor
        out = np.zeros((h * f, w * f, 3), dtype=np.uint8)
        for y0 in range(0, h, tile):
            for x0 in range(0, w, tile):
                y1, x1 = min(y0 + tile, h), min(x0 + tile, w)
                ya, xa = max(y0 - overlap, 0), max(x0 - overlap, 0)
                yb, xb = min(y1 + overlap, h), min(x1 + overlap, w)
                part = self._run_tile(rgb[ya:yb, xa:xb])
                out[y0 * f:y1 * f, x0 * f:x1 * f] = part[(y0 - ya) * f:(y1 - ya) * f, (x0 - xa) * f:(x1 - xa) * f]
        return out

    def _run_tile(self, rgb):
        torch = self.torch
        t = torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1).float().div(255.0).unsqueeze(0).to(self.device)
        if self.half:
            t = t.half()
        with torch.no_grad():
            o = self.model(t)
        o = o.squeeze(0).float().clamp(0, 1).mul(255.0).round().byte().permute(1, 2, 0).cpu().numpy()
        return o


def smooth_up(rgb, k):
    im = Image.fromarray(rgb)
    return np.array(im.resize((im.width * k, im.height * k), Image.LANCZOS))


def upscale(up, rgb, k, dedither):
    """The picture k times bigger: model passes (x4 each) and a resize to the exact factor."""
    src = rgb
    if dedither > 0:
        src = np.array(Image.fromarray(rgb).filter(ImageFilter.GaussianBlur(dedither)))
    if up.model is None:
        return smooth_up(src, k)
    have = 1
    out = src
    while have * up.factor <= k:
        out = up.run(out)
        have *= up.factor
    if have < k:
        # the rest by resampling (a model pass would overshoot)
        out = up.run(out)
        have *= up.factor
    if have != k:
        im = Image.fromarray(out)
        out = np.array(im.resize((rgb.shape[1] * k, rgb.shape[0] * k), Image.LANCZOS))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="", help="a folder of PNG/GIF images (all of them)")
    ap.add_argument("--files", default="", help="comma-separated image files instead of --dir")
    ap.add_argument("--mod", required=True, help="mod folder to write hd/UI/ into")
    ap.add_argument("--model", default="", help="a spandrel-loadable super-resolution model (.pth/.safetensors)")
    ap.add_argument("--no-model", action="store_true", help="smooth upscale only")
    ap.add_argument("--scale", type=int, default=4, help="4 (default) or 8")
    ap.add_argument("--dedither", type=float, default=0.45, help="Gaussian radius that melts palette dithering before the model (0 = off)")
    ap.add_argument("--names", default="", help="only these files (comma-separated names, with or without extension)")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many pictures (a test)")
    ap.add_argument("--force", action="store_true", help="remake pictures that exist")
    args = ap.parse_args()

    if args.files:
        files = [f for f in args.files.split(",") if f]
    elif args.dir:
        files = sorted(f for f in glob.glob(os.path.join(args.dir, "*")) if f.lower().endswith((".png", ".gif")))
    else:
        ap.error("--dir or --files is required")
    if args.names:
        wanted = {os.path.splitext(n)[0].lower() for n in args.names.split(",") if n}
        files = [f for f in files if os.path.splitext(os.path.basename(f))[0].lower() in wanted]
    if not files:
        print("nothing to do")
        return 1
    if args.scale not in (2, 4, 6, 8):
        ap.error("--scale must be 2, 4, 6 or 8")

    out_dir = os.path.join(args.mod, "hd", "UI")
    os.makedirs(out_dir, exist_ok=True)
    model_path = "" if args.no_model else args.model
    if not args.no_model and not model_path:
        print("no --model given: smooth upscale (a Real-ESRGAN model adds detail, see --help)")
    up = Upscaler(model_path, args.scale)
    done = skipped = 0
    t0 = time.time()
    for i, path in enumerate(files):
        name = os.path.splitext(os.path.basename(path))[0]
        out = os.path.join(out_dir, name + ".png")
        if os.path.exists(out) and not args.force:
            skipped += 1
            continue
        try:
            idx, palette, rgb, alpha = load_indexed(path)
        except Exception as e:
            print(name, ": cannot read:", e)
            continue
        pic = Image.fromarray(upscale(up, rgb, args.scale, args.dedither)).convert("RGBA")
        if idx is not None:
            # the image's transparent pixels (index 0) stay transparent, block by block
            a = Image.fromarray(np.where(idx == 0, 0, 255).astype(np.uint8), "L").resize(pic.size, Image.NEAREST)
            pic.putalpha(a)
        elif alpha is not None:
            pic.putalpha(Image.fromarray(alpha, "L").resize(pic.size, Image.LANCZOS))
        pic.save(out, compress_level=6)
        if palette is not None:
            with open(os.path.join(out_dir, name + ".pal.txt"), "w") as f:
                f.write("\n".join("%d %d %d" % tuple(c) for c in palette) + "\n")
        done += 1
        if done % 10 == 0 or done == 1:
            el = time.time() - t0
            left = (len(files) - i - 1) * el / max(done, 1)
            print("%d/%d %s -> %dx%d, %.1f s/picture, ~%d min left" % (i + 1, len(files), name, pic.width, pic.height, el / done, left / 60))
        if args.limit and done >= args.limit:
            break
    print("done: %d made, %d skipped (exist) -> %s" % (done, skipped, out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
