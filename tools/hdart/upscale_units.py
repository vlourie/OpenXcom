#!/usr/bin/env python3
"""HD packs of a mod's unit (and hand-object) sprites: every frame of a set upscaled to 32-bit, faithfully.

Two ways in:

  --rul <mod>\\Ruleset\\Piratez_Resources.rul   the sprite sheets straight from the mod: every extraSprites set cut
      from a sheet (subX/subY, e.g. Resources/Sprites/*.png of X-Piratez, 698 sets) is read from its file, the frames
      numbered as the game numbers them (row by row, plus the file's index offset); the set's name comes from the
      ruleset (65 of the Piratez sets are not named after their file: SUCCUBUS.PCK is VDD_00.png). The palette is
      the sheet's own. By default only the single-file sets of Resources/Sprites; --sheets all takes every
      subdivided set of the ruleset (HANDOB.PCK: 369 files with offsets).
  --export <folder>   sheets the game wrote with OXCE_HD_EXPORT (for sets that are not PNG sheets: vanilla PCK
      sets, sets patched by several mods): one 8-bit PNG per set + <set>.png.txt with the layout.

    tools\\hdart\\.venv\\Scripts\\python.exe tools\\hdart\\upscale_units.py --rul <mod>\\Ruleset\\Piratez_Resources.rul --mod <install>\\user\\mods\\hd --model E:\\models\\RealESRGAN_x4plus_anime_6B.pth

Output: <mod>/hd/<set>/pack.hdp - one file per set holding an RGBA PNG of every non-empty frame at --scale
times its size. The game registers the pack's table when the set is first drawn and reads a frame's
picture only when that frame is drawn (and drops the ones not drawn for long), so 700 sets of HD units
cost the memory of the units on the map. A frame's transparent pixels (index 0) stay transparent; the
alpha edge is smooth (--hard-alpha keeps it blocky). A 4x pack is shown at any HD scale (resampled).

Model: any 4x super-resolution model spandrel loads. For drawn sprites RealESRGAN_x4plus_anime_6B (clean
lines, keeps the pixel art's look) or RealESRGAN_x4plus (softer, more "painted") - both from
https://github.com/xinntao/Real-ESRGAN/releases. The model is deterministic: it sharpens and adds detail
but invents nothing (no diffusion). Without a model (--no-model) the frames are a smooth (Lanczos)
upscale - still 32-bit, no palette steps, but no new detail.

--preview <set>[,<set>] writes <out>/preview/<set>.png (classic pixels beside the HD frames) for a look
before an hour-long run; --sets picks sets; --pngs writes loose hd/<set>/<i>.png instead of the pack.
"""
import argparse
import glob
import io
import os
import struct
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprite_scale

PACK_MAGIC = b"OXHDPCK1"

# Sets of the base game whose frames a mod does not number freely: the engine keeps the vanilla
# frames "shared" and moves every index a mod adds above them into the range it gave that mod
# (Mod.cpp "update number of shared indexes", ExtraSprites::getFrame). A ruleset index is
# therefore not the frame number the game ends up drawing, and only the game itself can say what
# is - so these sets are made from what the game exports (OXCE_HD_EXPORT), never from a ruleset.
SHARED_SETS = {
    "BIGOBS.PCK", "FLOOROB.PCK", "HANDOB.PCK", "SMOKE.PCK", "HIT.PCK", "BASEBITS.PCK",
    "INTICON.PCK", "CustomArmorPreviews", "CustomItemPreviews", "Projectiles", "UnitResponseSounds",
}

# Where the recommended models live (any 4x model spandrel loads works; --model takes a path).
MODEL_URLS = {
    "RealESRGAN_x4plus_anime_6B": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
    "RealESRGAN_x4plus": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
}


def read_layout(path):
    """The layout of an exported sheet: dict(frames, width, height, cols)."""
    layout = {}
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                layout[parts[0]] = int(parts[1])
    for key in ("frames", "width", "height", "cols"):
        if key not in layout:
            raise ValueError("%s: no '%s'" % (path, key))
    return layout


def load_sheet(png_path):
    """An exported sheet as (indices HxW uint8, palette 256x3 uint8, layout)."""
    layout = read_layout(png_path + ".txt")
    im = Image.open(png_path)
    if im.mode != "P":
        raise ValueError("%s: not an 8-bit indexed PNG (export it with OXCE_HD_EXPORT)" % png_path)
    pal = im.getpalette() or []
    pal = (pal + [0] * 768)[:768]
    palette = np.array(pal, dtype=np.uint8).reshape(256, 3)
    idx = np.array(im, dtype=np.uint8)
    return idx, palette, layout


def frames_of(idx, layout):
    """Yields (index, frame indices h x w) for every non-empty frame of the sheet."""
    w, h, cols = layout["width"], layout["height"], layout["cols"]
    for i in range(layout["frames"]):
        x, y = (i % cols) * w, (i // cols) * h
        if y + h > idx.shape[0] or x + w > idx.shape[1]:
            break
        f = idx[y:y + h, x:x + w]
        if (f != 0).any():
            yield i, f


def read_ruleset_sheets(rul_path):
    """The subdivided extraSprites sets of a ruleset file (or of every .rul in a folder): a list of
    dict(name, subX, subY, width, height, files=[(index, relative path)]) in ruleset order."""
    import re
    paths = [rul_path]
    if os.path.isdir(rul_path):
        paths = sorted(glob.glob(os.path.join(rul_path, "*.rul")))
    sets = {}
    order = []
    for path in paths:
        text = open(path, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"^(\s*)- type: (\S+)\s*\n((?:\1  .*\n|\s*\n)*)", text, re.M):
            indent, name, body = m.group(1), m.group(2), m.group(3)
            sub_x = re.search(r"^\s+subX: (\d+)", body, re.M)
            sub_y = re.search(r"^\s+subY: (\d+)", body, re.M)
            if not sub_x or not sub_y:
                continue
            files = [(int(i), f) for i, f in re.findall(r"^\s+(\d+): (\S+)$", body, re.M)]
            if not files:
                single = re.search(r"^\s+fileSingle: (\S+)", body, re.M)
                if not single:
                    continue
                files = [(0, single.group(1))]
            width = re.search(r"^\s+width: (\d+)", body, re.M)
            height = re.search(r"^\s+height: (\d+)", body, re.M)
            entry = dict(name=name, subX=int(sub_x.group(1)), subY=int(sub_y.group(1)),
                         width=int(width.group(1)) if width else 0, height=int(height.group(1)) if height else 0,
                         files=files)
            if name in sets:
                # a later entry of the same set adds or replaces frames (as the game loads them)
                known = dict(sets[name]["files"])
                known.update(dict(files))
                sets[name]["files"] = sorted(known.items())
            else:
                sets[name] = entry
                order.append(name)
    return [sets[n] for n in order]


def load_sheet_file(path):
    """A mod's sheet (PNG/GIF, first frame) as (indices HxW uint8, palette 256x3 uint8)."""
    im = Image.open(path)
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    if im.mode != "P":
        raise ValueError("%s: not an 8-bit indexed image (the game reads only those)" % path)
    pal = im.getpalette() or []
    pal = (pal + [0] * 768)[:768]
    return np.array(im, dtype=np.uint8), np.array(pal, dtype=np.uint8).reshape(256, 3)


def frames_of_ruleset_set(entry, mod_root):
    """The frames of a ruleset set, cut exactly as the game cuts them: the file is laid into a
    sheet of the size the ruleset declares (bigger is cropped, smaller leaves the rest empty) and
    that sheet is divided into width/subX by height/subY frames, numbered row by row from the
    file's index (ExtraSprites::loadSprite).
    @return (frames [(index, h x w indices)], palette, w, h)
    """
    w, h = entry["subX"], entry["subY"]
    frames = []
    palette = None
    notes = []
    for offset, rel in entry["files"]:
        path = os.path.join(mod_root, rel.replace("/", os.sep))
        if not os.path.exists(path):
            notes.append("missing %s" % rel)
            continue
        idx, pal = load_sheet_file(path)
        if palette is None:
            palette = pal
        sheet_w = entry["width"] or idx.shape[1]
        sheet_h = entry["height"] or idx.shape[0]
        if idx.shape[1] != sheet_w or idx.shape[0] != sheet_h:
            notes.append("%s is %dx%d, the ruleset says %dx%d - cut as the ruleset says, like the game"
                         % (rel, idx.shape[1], idx.shape[0], sheet_w, sheet_h))
            sheet = np.zeros((sheet_h, sheet_w), dtype=np.uint8)
            take_h, take_w = min(sheet_h, idx.shape[0]), min(sheet_w, idx.shape[1])
            sheet[:take_h, :take_w] = idx[:take_h, :take_w]
            idx = sheet
        cols, rows = sheet_w // w, sheet_h // h
        for i in range(cols * rows):
            x, y = (i % cols) * w, (i // cols) * h
            f = idx[y:y + h, x:x + w]
            if (f != 0).any():
                frames.append((offset + i, f))
    return frames, palette, w, h, notes


class Upscaler:
    """A spandrel model (x4) on the GPU, or nothing (smooth upscale)."""

    def __init__(self, model_path, pixels_per_frame=96 * 112, share=1):
        self.model = None
        self.factor = 1
        self.device = "cpu"
        self.torch = None
        if not model_path:
            return
        if not os.path.exists(model_path):
            raise SystemExit(
                "no model file at %s\n"
                "Download one (PowerShell, any folder - pass it as --model):\n"
                "  Invoke-WebRequest -Uri %s -OutFile %s\n"
                "or run with --no-model for a smooth upscale without a model." % (model_path, MODEL_URLS["RealESRGAN_x4plus_anime_6B"], model_path))
        import torch
        from spandrel import ModelLoader
        desc = ModelLoader().load_from_file(model_path)
        self.factor = int(desc.scale)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        desc = desc.to(self.device).eval()
        self.half = self.device == "cuda" and desc.supports_half
        if self.half:
            desc = desc.half()
        self.channels_last = False
        if self.device == "cuda":
            # every batch has the same shape, so cudnn may pick its kernels once and keep them;
            # a convolution net in half precision runs its tensor cores on channels-last data
            torch.backends.cudnn.benchmark = True
            torch.backends.cudnn.allow_tf32 = True
            torch.backends.cuda.matmul.allow_tf32 = True
            try:
                desc = desc.to(memory_format=torch.channels_last)
                self.channels_last = True
            except Exception:
                pass
        self.model = desc
        self.torch = torch
        self.max_batch = 1 << 30
        if self.device == "cuda":
            self.max_batch = self.fit_batch(pixels_per_frame, 1 << 30, share)
        print("model:", os.path.basename(model_path), "x%d" % self.factor, "on", self.device,
              "(fp16)" if self.half else "", "(channels-last)" if self.channels_last else "",
              "up to %d frame(s) per pass" % self.max_batch if self.max_batch < (1 << 30) else "")

    def fit_batch(self, pixels_per_frame, wanted, share=1):
        """How many frames fit in the video memory that is free now. A convolution net keeps tens
        of feature maps of the whole batch alive at once, so the memory grows with the batch, and
        several worker processes share one card: each takes a share of what it finds free when it
        starts, which is why the later ones ask for less."""
        torch = self.torch
        try:
            free, total = torch.cuda.mem_get_info()
        except Exception:
            return wanted
        bytes_per_frame = max(1, pixels_per_frame) * 64 * (2 if self.half else 4) * 24
        # the workers start together and each would otherwise see the whole card as free
        fits = int(free * 0.5 / max(1, share) / bytes_per_frame)
        return max(2, min(wanted, fits))

    def run(self, batch):
        """The model over a batch of RGB uint8 images (B, H, W, 3) -> (B, fH, fW, 3), in as many
        passes as the card has room for: a batch too big for the free memory is halved and retried
        rather than taking the machine down with it."""
        if batch.shape[0] > self.max_batch:
            parts = [self.run(batch[i:i + self.max_batch]) for i in range(0, batch.shape[0], self.max_batch)]
            return np.concatenate(parts, axis=0)
        try:
            return self._run(batch)
        except Exception as e:
            if "out of memory" not in str(e).lower() or batch.shape[0] < 2:
                raise
            self.torch.cuda.empty_cache()
            self.max_batch = max(1, batch.shape[0] // 2)
            print("  not enough video memory for %d frame(s) at once, %d from now on"
                  % (batch.shape[0], self.max_batch), flush=True)
            return self.run(batch)

    def _run(self, batch):
        torch = self.torch
        t = torch.from_numpy(np.ascontiguousarray(batch)).permute(0, 3, 1, 2).float().div(255.0).to(self.device)
        if self.half:
            t = t.half()
        if self.channels_last:
            t = t.contiguous(memory_format=torch.channels_last)
        with torch.inference_mode():
            o = self.model(t)
        return o.float().clamp(0, 1).mul(255.0).round().byte().permute(0, 2, 3, 1).contiguous().cpu().numpy()


def dedither(rgb, sigma):
    """A slight 3x3 blur (batched) that melts checkerboard dithering before the model sees it."""
    if sigma <= 0:
        return rgb
    g = float(np.exp(-1.0 / (2.0 * sigma * sigma)))
    k = np.array([g, 1.0, g], dtype=np.float32)
    k /= k.sum()
    out = rgb
    for axis in (1, 2):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (1, 1)
        p = np.pad(out, pad, mode="edge")
        sl = lambda o: tuple(slice(1 + o, (p.shape[axis] - 1 + o)) if a == axis else slice(None) for a in range(out.ndim))
        out = p[sl(-1)] * k[0] + p[sl(0)] * k[1] + p[sl(1)] * k[2]
    return out


def smooth_mask(mask, k, hard):
    """The alpha of a frame at k times its size: nearest (hard) or a smooth threshold of the resized mask."""
    h, w = mask.shape
    if hard:
        return np.repeat(np.repeat(mask.astype(np.uint8) * 255, k, axis=0), k, axis=1)
    im = Image.fromarray((mask * 255).astype(np.uint8), "L").resize((w * k, h * k), Image.BICUBIC)
    m = np.asarray(im, dtype=np.float32) / 255.0
    a = np.clip((m - 0.5) * 3.0 + 0.5, 0.0, 1.0)
    return (a * 255.0 + 0.5).astype(np.uint8)


def shrink(batch, factor):
    """A batch of pictures made `factor` times smaller by averaging blocks (an exact whole-number
    step, which is what the model's picture needs - far cheaper than a resample per frame)."""
    b, h, w = batch.shape[:3]
    c = batch.shape[3] if batch.ndim == 4 else 1
    out = batch.reshape(b, h // factor, factor, w // factor, factor, c).mean(axis=(2, 4))
    return out


def resize_batch(batch, width, height):
    """A batch of RGB pictures at another size: block averaging when it divides exactly, a
    resample otherwise."""
    b, h, w = batch.shape[:3]
    if width and height and h % height == 0 and w % width == 0 and h // height == w // width:
        return np.clip(shrink(batch.astype(np.float32), h // height) + 0.5, 0, 255).astype(np.uint8)
    out = np.zeros((b, height, width, batch.shape[3]), dtype=np.uint8)
    for i in range(b):
        out[i] = np.asarray(Image.fromarray(np.clip(batch[i], 0, 255).astype(np.uint8), "RGB")
                            .resize((width, height), Image.LANCZOS))
    return out


def upscale_batch(up, rgb_batch, mask_batch, scale, pad, sigma):
    """HD RGB of a batch of frames: (B,h,w,3) uint8 and (B,h,w) bool -> (B, h*scale, w*scale, 3) uint8."""
    B, h, w, _ = rgb_batch.shape
    rgb = rgb_batch.astype(np.float32)
    padded = np.pad(rgb, ((0, 0), (pad, pad), (pad, pad), (0, 0)))
    pmask = np.pad(mask_batch, ((0, 0), (pad, pad), (pad, pad)))
    src = sprite_scale.fill_outside(padded, pmask)
    src = dedither(src, sigma)
    src8 = np.clip(src + 0.5, 0, 255).astype(np.uint8)
    if up.model is None:
        out = np.zeros((B, h * scale, w * scale, 3), dtype=np.uint8)
        for i in range(B):
            im = Image.fromarray(src8[i]).resize(((w + 2 * pad) * scale, (h + 2 * pad) * scale), Image.LANCZOS)
            out[i] = np.asarray(im)[pad * scale:(pad + h) * scale, pad * scale:(pad + w) * scale]
        return out
    have = 1
    cur = src8
    while have * up.factor <= scale:
        cur = up.run(cur)
        have *= up.factor
    if have < scale:
        cur = up.run(cur)
        have *= up.factor
    if have != scale:
        cur = resize_batch(cur, (w + 2 * pad) * scale, (h + 2 * pad) * scale)
    return cur[:, pad * scale:(pad + h) * scale, pad * scale:(pad + w) * scale]


def make_frames(up, f_batch, palette, args):
    """The HD pictures of a batch of frames as (B, h*scale, w*scale, 4) float RGBA.

    The shapes come from xBRZ - the scaler the engine itself uses, so the pack starts from what
    the engine would have drawn - and a model, when given, adds its fine detail on top as a
    change of brightness (--detail). --method model is the plain model picture instead.
    """
    mask = f_batch != 0
    rgb = palette[f_batch].astype(np.float32)
    rgba = np.concatenate([rgb, (mask * 255.0)[..., None]], axis=3)
    k = args.scale
    model_rgb = None
    wants_model = args.method == "model" or (args.method == "detail" and args.detail > 0)
    if wants_model and (up.model is not None or args.method == "model"):
        if args.model_input == "xbrz2" and args.method != "model":
            # the model does better on a picture than on 32x40 of pixel art: it gets the xBRZ
            # picture at twice the size and its detail is scaled back down to the frame's
            pre = sprite_scale.xbrz_scale(rgba, 2)
            big = upscale_batch(up, np.clip(pre[..., :3], 0, 255).astype(np.uint8), pre[..., 3] > 127,
                                max(1, k // 2), args.pad * 2, args.dedither).astype(np.float32)
            model_rgb = resize_batch(big, rgb.shape[2] * k, rgb.shape[1] * k).astype(np.float32)
        else:
            model_rgb = upscale_batch(up, rgb.astype(np.uint8), mask, k, args.pad, args.dedither).astype(np.float32)
    if args.method == "model":
        alpha = np.stack([smooth_mask(m, k, args.hard_alpha) for m in mask]).astype(np.float32)
        return np.concatenate([model_rgb, alpha[..., None]], axis=3)
    # xBRZ does 2..6; a bigger scale is xBRZ at 4 and a smooth step up
    kb = k if k <= 6 else 4
    base = sprite_scale.xbrz_scale(rgba, kb)
    if kb != k:
        base = np.stack([np.asarray(Image.fromarray(np.clip(b, 0, 255).astype(np.uint8), "RGBA")
                                    .resize((b.shape[1] * k // kb, b.shape[0] * k // kb), Image.LANCZOS), dtype=np.float32)
                         for b in base])
    if args.hard_alpha:
        base[..., 3] = np.stack([smooth_mask(m, k, True) for m in mask]).astype(np.float32)
    if model_rgb is not None and args.detail > 0:
        base = sprite_scale.add_detail(base, model_rgb, args.detail, args.detail_limit, k)
    return base


def encode_rgba(frame):
    """One HD frame (h, w, 4 float) as PNG bytes."""
    a = np.clip(frame, 0, 255).astype(np.uint8)
    b = io.BytesIO()
    Image.fromarray(a, "RGBA").save(b, "PNG", compress_level=6)
    return b.getvalue()


def settings_of(args, up):
    """The settings a pack was made with, as one line; a pack whose line differs is remade."""
    parts = ["scale=%d" % args.scale, "method=%s" % args.method, "hard_alpha=%d" % int(args.hard_alpha)]
    if args.method != "xbrz":
        parts += ["model=%s" % os.path.basename(args.model), "model_input=%s" % args.model_input,
                  "pad=%d" % args.pad, "dedither=%.3g" % args.dedither]
    if args.method == "detail":
        parts += ["detail=%.3g" % args.detail, "detail_limit=%.3g" % args.detail_limit]
    return " ".join(parts)


def pack_is_current(set_dir, settings):
    """True when the pack in this folder was made with these settings (or with unknown ones - a
    pack from before this file existed is kept as it is; --force remakes it)."""
    path = os.path.join(set_dir, "settings.txt")
    if not os.path.exists(path):
        return True, False
    try:
        return open(path).read().strip() == settings, True
    except OSError:
        return True, False


def write_pack(path, scale, base_w, base_h, blobs):
    """blobs: list of (index, png bytes)."""
    header = PACK_MAGIC + struct.pack("<IIII", scale, base_w, base_h, len(blobs))
    offset = len(header) + 12 * len(blobs)
    table = b""
    for index, blob in blobs:
        table += struct.pack("<III", index, offset, len(blob))
        offset += len(blob)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(header)
        f.write(table)
        for _, blob in blobs:
            f.write(blob)
    os.replace(tmp, path)


def preview_sheet(path, frames, palette, columns, scale, count=18):
    """A sheet of the first frames: the classic pixels and every column of `columns`
    (label -> list of HD frames), side by side on a dark checker."""
    n_show = min(count, len(frames), *(len(c[1]) for c in columns)) if columns else 0
    if n_show <= 0:
        return
    h, w = frames[0][1].shape
    cw, ch = w * scale, h * scale
    ncol = 1 + len(columns)
    gap, top = 8, 20
    cell_w = ncol * (cw + 4) + 8
    cell_h = ch + gap
    cols = max(1, min(3, 1800 // cell_w))
    rows = (n_show + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell_w, top + rows * cell_h + gap), (38, 38, 40, 255))
    checker = Image.new("RGBA", (cw, ch), (52, 52, 54, 255))
    px = checker.load()
    for y in range(ch):
        for x in range(cw):
            if ((x // 8) + (y // 8)) % 2:
                px[x, y] = (66, 66, 68, 255)
    draw = ImageDraw.Draw(sheet)
    labels = ["classic x%d" % scale] + [c[0] for c in columns]
    for group in range(cols):
        for c, label in enumerate(labels):
            draw.text((group * cell_w + 8 + c * (cw + 4) + 2, 5), label, fill=(230, 230, 230, 255))
    for n in range(n_show):
        index, f = frames[n]
        cx = (n % cols) * cell_w + 8
        cy = top + (n // cols) * cell_h + 4
        classic = Image.fromarray(f, "P")
        classic.putpalette(palette.flatten().tolist())
        classic = classic.convert("RGBA")
        classic.putalpha(Image.fromarray(np.where(f == 0, 0, 255).astype(np.uint8), "L"))
        pictures = [classic.resize((cw, ch), Image.NEAREST)]
        for _, frames_hd in columns:
            pictures.append(Image.fromarray(np.clip(frames_hd[n], 0, 255).astype(np.uint8), "RGBA"))
        for c, pic in enumerate(pictures):
            cell = checker.copy()
            cell.alpha_composite(pic)
            sheet.paste(cell, (cx + c * (cw + 4), cy))
    sheet.save(path)


def process_set(up, name, frames, palette, w, h, out_root, args, preview_dir):
    """Makes the pack (or loose PNGs) of one set from its frames [(index, h x w indices)].
    @return (frames made, frames that already existed, the preview sheet's path or "")."""
    if not frames:
        return 0, 0, ""
    set_dir = os.path.join(out_root, name)
    pack_path = os.path.join(set_dir, "pack.hdp")
    settings = "%s frames=%d" % (args.settings, len(frames))
    if not args.force and not args.preview_only:
        current, known = pack_is_current(set_dir, settings)
        if args.pngs:
            if current and all(os.path.exists(os.path.join(set_dir, "%d.png" % i)) for i, _ in frames):
                return 0, len(frames), ""
        elif os.path.exists(pack_path) and current:
            return 0, len(frames), ""
        elif os.path.exists(pack_path) and not current:
            print("  %s: made with other settings, remaking" % name)
    blobs = []
    preview_final, preview_base = [], []
    want_preview = preview_dir is not None
    todo = frames[:18] if args.preview_only else frames
    batch = max(1, args.batch)
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        f_batch = np.stack([f for _, f in chunk])
        hd = make_frames(up, f_batch, palette, args)
        if want_preview and len(preview_final) < 18:
            preview_final.extend(hd[:18 - len(preview_final)])
            if args.method == "detail" and up.model is not None:
                base = make_frames(up, f_batch[:18 - len(preview_base)], palette, _Args(args, detail=0.0))
                preview_base.extend(base)
        if not args.preview_only:
            for n, (index, _) in enumerate(chunk):
                blobs.append((index, encode_rgba(hd[n])))
    preview_path = ""
    if want_preview:
        os.makedirs(preview_dir, exist_ok=True)
        preview_path = os.path.join(preview_dir, name + ".png")
        columns = []
        if preview_base:
            columns.append(("xBRZ", preview_base))
            columns.append(("xBRZ + detail", preview_final))
        else:
            columns.append((args.method, preview_final))
        preview_sheet(preview_path, frames, palette, columns, args.scale)
    if args.preview_only:
        return 0, 0, preview_path
    os.makedirs(set_dir, exist_ok=True)
    if args.pngs:
        for index, blob in blobs:
            with open(os.path.join(set_dir, "%d.png" % index), "wb") as f:
                f.write(blob)
    else:
        write_pack(pack_path, args.scale, w, h, blobs)
    with open(os.path.join(set_dir, "settings.txt"), "w") as f:
        f.write(settings + "\n")
    return len(blobs), 0, preview_path


class _Args(object):
    """The parsed options with a field changed (for the preview's plain-xBRZ column)."""

    def __init__(self, base, **changes):
        self.__dict__["_base"] = base
        self.__dict__.update(changes)

    def __getattr__(self, name):
        return getattr(self.__dict__["_base"], name)


def frame_pixels(args):
    """How many pixels of one frame the model is shown (the padded picture it gets)."""
    w, h = 32, 40   # the usual unit frame; the estimate only has to be in the right ballpark
    if args.model_input == "xbrz2" and args.method != "model":
        w, h, pad = w * 2, h * 2, args.pad * 2
    else:
        pad = args.pad
    return (w + 2 * pad) * (h + 2 * pad)


def palette_of_file(path):
    """The palette an indexed image carries, or None."""
    try:
        im = Image.open(path)
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        if im.mode != "P":
            return None
        pal = (im.getpalette() or []) + [0] * 768
        return np.array(pal[:768], dtype=np.uint8).reshape(256, 3)
    except Exception:
        return None


def battle_palette(todo, args):
    """The palette the game will draw these sprites with.

    A sprite file carries a palette of its own, but the engine keeps only its pixel indices
    (Surface::loadImage copies them as they are) and draws them through the battlescape palette, so
    that is the palette the HD picture of a frame must be made with. Mods are not tidy about it -
    in X-Piratez most files carry the battlescape palette but a few carry something else entirely -
    so the palette of the run is the one most of the files agree on (--palette overrides it).
    @return (palette 256x3 or None, names of the sets whose files disagree)
    """
    if args.palette:
        pal = palette_of_file(args.palette)
        if pal is None:
            raise SystemExit("--palette %s: not an 8-bit indexed image" % args.palette)
        return pal, []
    counts = {}
    first = {}
    for name, spec in todo:
        if spec["kind"] != "rul":
            continue
        files = spec["entry"]["files"]
        if not files:
            continue
        # a set of many files (HANDOB: one per weapon) is sampled, not judged by its first file
        step = max(1, len(files) // 8)
        keys = []
        for _, rel in files[::step][:8]:
            pal = palette_of_file(os.path.join(spec["root"], rel.replace("/", os.sep)))
            if pal is None:
                continue
            key = pal.tobytes()
            keys.append(key)
            counts[key] = counts.get(key, 0) + 1
            first.setdefault(key, pal)
        if keys:
            spec["palette_key"] = max(set(keys), key=keys.count)
    if not counts:
        return None, []
    best = max(counts, key=lambda k: counts[k])
    odd = [name for name, spec in todo if spec.get("palette_key", best) != best]
    return first[best], odd


def mod_root_of(args):
    """The folder a ruleset's file paths are relative to."""
    if args.mod_root:
        return args.mod_root
    here = os.path.abspath(args.rul if os.path.isdir(args.rul) else os.path.dirname(args.rul))
    return os.path.dirname(here) if os.path.basename(here).lower() == "ruleset" else here


def sources(args):
    """(set name, spec) for every set to make; a spec is plain data, so a worker process can take
    it over the wire and read the frames itself (see load_spec)."""
    out = []
    if args.rul:
        root = mod_root_of(args)
        entries = read_ruleset_sheets(args.rul)
        if args.sheets != "all":
            folder = args.sheets.replace("\\", "/").rstrip("/").lower() + "/"
            entries = [e for e in entries if all(f.replace("\\", "/").lower().startswith(folder) for _, f in e["files"])]
        refused = []
        for e in entries:
            if e["name"] in SHARED_SETS:
                refused.append(e["name"])
                continue
            out.append((e["name"], {"kind": "rul", "entry": e, "root": root}))
        if refused:
            print("not from the ruleset, the game renumbers their frames - export them instead "
                  "(OXCE_HD_EXPORT, see --help): " + ", ".join(refused))
    if args.export:
        for png_path in sorted(glob.glob(os.path.join(args.export, "*.png"))):
            if os.path.exists(png_path + ".txt"):
                out.append((os.path.basename(png_path)[:-4], {"kind": "sheet", "path": png_path}))
    return out


def load_spec(spec):
    """The frames of a set: (frames [(index, h x w indices)], palette, w, h, notes)."""
    if spec["kind"] == "rul":
        return frames_of_ruleset_set(spec["entry"], spec["root"])
    idx, palette, layout = load_sheet(spec["path"])
    return list(frames_of(idx, layout)), palette, layout["width"], layout["height"], []


# One set in a worker process: the model and the options are set up once per process (a worker
# holds its own model on the GPU - the picture work is numpy on one core, so several processes
# together keep the card busy where one could not).
_WORKER = {}


def _worker_init(args, model_path):
    _WORKER["args"] = args
    _WORKER["up"] = Upscaler(model_path, frame_pixels(args), args.jobs)


def _worker_set(job):
    name, spec, preview_dir = job
    args = _WORKER["args"]
    try:
        frames, palette, w, h, notes = load_spec(spec)
        if args.palette_colors is not None:
            palette = args.palette_colors
        count, old, preview_path = process_set(_WORKER["up"], name, frames, palette, w, h,
                                               os.path.join(args.mod, "hd"), args, preview_dir)
        return name, count, old, preview_path, "", notes
    except Exception as e:
        return name, 0, 0, "", str(e), []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rul", default="", help="a ruleset file (or Ruleset folder) whose extraSprites sheets to read straight from the mod")
    ap.add_argument("--mod-root", default="", help="the mod folder the ruleset's paths are relative to (default: the Ruleset folder's parent)")
    ap.add_argument("--sheets", default="Resources/Sprites", help="with --rul: only sets whose files are in this folder, or 'all' (HANDOB.PCK etc.)")
    ap.add_argument("--export", default="", help="folder with sheets the game exported (OXCE_HD_EXPORT)")
    ap.add_argument("--mod", required=True, help="mod folder to write hd/<set>/ into")
    ap.add_argument("--model", default="", help="a spandrel-loadable 4x super-resolution model (.pth/.safetensors)")
    ap.add_argument("--no-model", action="store_true", help="smooth (Lanczos) upscale only")
    ap.add_argument("--scale", type=int, default=4, help="2, 4 (default) or 8 times the frame size")
    ap.add_argument("--method", default="", help="how a frame is made: xbrz (the scaler alone), detail (xbrz plus the model's detail, the default with --model), model (the model's picture alone)")
    ap.add_argument("--detail", type=float, default=0.6, help="how much of the model's fine detail goes on the xBRZ picture (0..1)")
    ap.add_argument("--model-input", default="xbrz2", help="what the model is shown: xbrz2 (the xBRZ picture at twice the size - a model reads a picture better than pixel art) or raw (the frame itself)")
    ap.add_argument("--detail-limit", type=float, default=0.3, help="the largest change of brightness the detail may make (a fraction)")
    ap.add_argument("--dedither", type=float, default=0.0, help="blur sigma that melts dithering before the model (0 = off; sprites this small have no dithering to melt)")
    ap.add_argument("--pad", type=int, default=8, help="pixels of colour continued around a frame for the model")
    ap.add_argument("--hard-alpha", action="store_true", help="blocky (nearest) alpha edge instead of a smooth one")
    ap.add_argument("--batch", type=int, default=32, help="frames per model pass (the model keeps tens of feature maps of the whole batch in video memory, so this is capped by what the card has free - raise it only with --jobs 1)")
    ap.add_argument("--sets", default="", help="only these sets (comma-separated, e.g. PIR_570.PCK,HANDOB.PCK)")
    ap.add_argument("--preview", default="", help="write <mod>/hd/preview/<set>.png for these sets (comma-separated, or 'all')")
    ap.add_argument("--preview-only", action="store_true", help="only the previews, no packs")
    ap.add_argument("--pngs", action="store_true", help="loose hd/<set>/<index>.png files instead of pack.hdp")
    ap.add_argument("--palette", default="", help="an 8-bit image whose palette the HD frames are coloured with (default: the palette most of the mod's sheets agree on - the one the game draws them through)")
    ap.add_argument("--jobs", type=int, default=0, help="worker processes (0 = pick from the number of cores; the picture work is one core per frame, so several processes are what keeps a big GPU busy)")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many sets")
    ap.add_argument("--force", action="store_true", help="remake packs that exist")
    args = ap.parse_args()

    if args.scale not in (2, 3, 4, 5, 6, 8):
        ap.error("--scale must be 2, 3, 4, 5, 6 or 8")
    if args.jobs <= 0:
        cores = os.cpu_count() or 4
        args.jobs = max(1, min(4, cores // 4)) if not args.preview_only else 1
    if not args.method:
        args.method = "detail" if (args.model and not args.no_model) else "xbrz"
    if args.method not in ("xbrz", "detail", "model"):
        ap.error("--method must be xbrz, detail or model")
    if args.method != "xbrz" and (args.no_model or not args.model):
        print("--method %s needs a model: falling back to xbrz (the scaler alone)" % args.method)
        args.method = "xbrz"
    if not args.rul and not args.export:
        ap.error("--rul <ruleset> or --export <folder> is required")
    todo = list(sources(args))
    if args.sets:
        wanted = {s.strip().lower() for s in args.sets.split(",") if s.strip()}
        todo = [t for t in todo if t[0].lower() in wanted]
    if not todo:
        print("no sets found (see --help)")
        return 1
    preview_sets = set()
    if args.preview:
        preview_sets = {s.strip().lower() for s in args.preview.split(",") if s.strip()}
    if args.preview_only and not preview_sets:
        preview_sets = {"all"}
    model_path = "" if args.method == "xbrz" else args.model
    if args.method == "xbrz":
        print("xBRZ only: shapes and colours of the frame, sharpened - no model" +
              (" (--method detail adds a model's texture)" if not args.model else ""))
    args.palette_colors, odd_palettes = battle_palette(todo, args)
    if odd_palettes:
        print("%d set(s) carry a palette of their own, coloured with the mod's instead (as the game does): %s"
              % (len(odd_palettes), ", ".join(odd_palettes[:8]) + (" ..." if len(odd_palettes) > 8 else "")))
    up = Upscaler(model_path, frame_pixels(args)) if args.jobs == 1 else Upscaler("")
    args.settings = settings_of(args, up)
    out_root = os.path.join(args.mod, "hd")
    preview_root = os.path.join(out_root, "preview")
    done_sets = made = skipped = previews = 0
    t0 = time.time()
    jobs = [(name, spec, preview_root if ("all" in preview_sets or name.lower() in preview_sets) else None)
            for name, spec in todo]
    if args.limit:
        jobs = jobs[:args.limit] if args.preview_only else jobs
    print("%d set(s) to do%s" % (len(jobs), "" if args.jobs == 1 else " on %d process(es)" % args.jobs))

    def report(n, name, count, old, preview_path, error, notes=()):
        for note in notes:
            print("  %s: %s" % (name, note), flush=True)
        el = time.time() - t0
        rate = made / el if el > 0 and made else 0
        if error:
            what = "failed: " + error
        elif args.preview_only:
            what = "preview -> %s" % preview_path if preview_path else "nothing to preview"
        elif old:
            what = "%d frame(s) already there (--force remakes them)" % old
        else:
            what = "%d frame(s), %.0f frames/s" % (count, rate)
        print("%d/%d %s: %s" % (n, len(jobs), name, what), flush=True)

    if args.jobs == 1:
        for n, job in enumerate(jobs):
            try:
                frames, palette, w, h, notes = load_spec(job[1])
                if args.palette_colors is not None:
                    palette = args.palette_colors
                count, old, preview_path = process_set(up, job[0], frames, palette, w, h, out_root, args, job[2])
                name, error = job[0], ""
            except Exception as e:
                name, count, old, preview_path, error, notes = job[0], 0, 0, "", str(e), []
            if count:
                made += count
                done_sets += 1
            if preview_path:
                previews += 1
            skipped += old
            report(n + 1, name, count, old, preview_path, error, notes)
            if args.limit and (done_sets >= args.limit or (args.preview_only and previews >= args.limit)):
                break
    else:
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        with ctx.Pool(args.jobs, initializer=_worker_init, initargs=(args, model_path)) as pool:
            for n, (name, count, old, preview_path, error, notes) in enumerate(pool.imap_unordered(_worker_set, jobs, chunksize=1)):
                if count:
                    made += count
                    done_sets += 1
                if preview_path:
                    previews += 1
                skipped += old
                report(n + 1, name, count, old, preview_path, error, notes)
    if args.preview_only:
        print("done: %d preview sheet(s) -> %s (no packs written: --preview-only)" % (previews, preview_root))
    else:
        print("done: %d set(s), %d frame(s) made, %d frame(s) existed -> %s" % (done_sets, made, skipped, out_root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
