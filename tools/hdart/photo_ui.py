#!/usr/bin/env python3
"""Drawn pictures of a mod (comic / anime Ufopaedia illustrations) re-rendered as photographs.

A picture keeps its size and its content — composition, pose, clothes, objects, colours and the flat
panel the article text is printed on — only the rendering changes: an image-editing model
(Qwen-Image-Edit-2511, 20B, Apache-2.0) is told to make a photograph of exactly the same scene.
Runs on one RTX 5090 (32 GB): the transformer is stored in fp8 (20 GB) and computed in bf16, the
text encoder waits in RAM between pictures (~36 GB of RAM in use).

Sources are the mod's original 320x200 indexed pictures (--dir, PNG/GIF); the model's input is the
4x Real-ESRGAN version from <mod>\\hd\\UI (upscale_ui.py) when it exists, else a smooth upscale.
The flat text panel is found in the original (a rectangle of one palette index at the border),
cut out before the model and put back exactly afterwards, so the article text lands on the same
colour as before; index 0 stays transparent.

Two modes:
  --refs NAME        one picture, every preset -> <refs-dir>\\<name>_<preset>.png + <name>_sheet.png
  --preset P         every picture of --dir (resumable) -> <out>\\<name>.png (+ .pal.txt)

    tools\\hdart\\.venv\\Scripts\\python.exe tools\\hdart\\photo_ui.py --dir <mod>\\Resources\\Pedia --mod user\\mods\\hd --refs AAP_002 --fast
    tools\\hdart\\.venv\\Scripts\\python.exe tools\\hdart\\photo_ui.py --dir <mod>\\Resources\\Pedia --mod user\\mods\\hd --refs AAP_002
    tools\\hdart\\.venv\\Scripts\\python.exe tools\\hdart\\photo_ui.py --dir <mod>\\Resources\\Pedia --mod user\\mods\\hd --preset cinema

--fast: the Lightning LoRA, 4 steps without CFG (~15 s a picture) instead of 40 steps with CFG 4
(~3-4 min a picture, better). Presets `studio` and `retro` also use the Anime-to-Photoreal LoRA.
--dry-run needs no model: it only writes <name>_layout.png showing what is kept flat and what is painted.
One-time setup: tools\\hdart\\setup_photo.ps1 (pip + ~58 GB of models into E:\\models).
"""
import argparse
import glob
import hashlib
import math
import os
import re
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

MODEL = "Qwen/Qwen-Image-Edit-2511"
LIGHTNING = ("lightx2v/Qwen-Image-Edit-2511-Lightning", ("4steps", "bf16"))
PHOTOREAL = ("Hyperccino/Qwen-Edit-2511-Anime-to-Photoreal-v1.1", ())

# What every preset asks for first: the same picture, only real.
KEEP = ("Turn this drawn illustration into a real photograph of exactly the same scene. Keep everything that is "
        "in the picture - every person, creature, object, weapon, vehicle, building, landscape and any text or "
        "lettering - with the same composition, framing, camera angle, poses, proportions, colours and background; "
        "do not add, remove, move, resize or crop anything. Clothing stays exactly as drawn, no more and no less: "
        "do not add clothes, armour, fabric or any covering that is not in the drawing - bare skin in the drawing "
        "stays bare skin, and what is covered stays covered the same way. Render each material as it is drawn, "
        "only real: skin with pores, hair, cloth, leather, metal, stone, glass, foliage, with realistic lighting, "
        "shadows and reflections. The background stays exactly what it is, with the same colour and brightness: "
        "a plain or empty background remains plain and empty (light stays light), a dark background stays dark, "
        "fog stays fog, ruins stay ruins - never invent new scenery, buildings, people or creatures. "
        "No outlines, no cel shading, no flat colours, no drawing look.")

PRESETS = {
    "cinema": dict(lora=0.0, style=(
        "The result is a cinematic film still from a live-action movie: 35 mm lens, dramatic natural light, "
        "shallow depth of field, rich colour grading, subtle film grain.")),
    "natural": dict(lora=0.0, style=(
        "The result is a candid photograph taken with a modern DSLR: even daylight, neutral true colours, "
        "sharp detail everywhere, documentary look, no stylisation.")),
    "studio": dict(lora=1.0, style=(
        "Kigurumi of the anime character, realistic details. The result is a professional studio photograph "
        "of a real person: softbox lighting, crisp detail, magazine quality, real human face and skin.")),
    "retro": dict(lora=0.6, style=(
        "The result is a vintage analog photograph from the 1990s on Kodak colour film: warm tones, "
        "soft highlights, light grain, a slightly faded print.")),
    "render": dict(lora=0.0, style=(
        "The result is a photorealistic cinematic render from a modern AAA video game: ray-traced lighting, "
        "ultra-detailed PBR materials, volumetric light, crisp and clean.")),
}
NEGATIVE = ("anime, manga, cartoon, comic, illustration, drawing, painting, sketch, cel shading, flat colours, "
            "outlines, lowres, blurry, deformed, extra limbs, extra fingers, text, watermark, logo")

# The Lightning LoRA wants this flow schedule (from lightx2v's README).
LIGHTNING_SCHEDULER = {
    "base_image_seq_len": 256, "base_shift": math.log(3), "invert_sigmas": False, "max_image_seq_len": 8192,
    "max_shift": math.log(3), "num_train_timesteps": 1000, "shift": 1.0, "shift_terminal": None,
    "stochastic_sampling": False, "time_shift_type": "exponential", "use_beta_sigmas": False,
    "use_dynamic_shifting": True, "use_exponential_sigmas": False, "use_karras_sigmas": False,
}


# ---------------------------------------------------------------- pictures and layout (no GPU)

class Source:
    """A mod picture: rgb HxWx3; labels HxW (palette index, or a number per distinct colour for a
    true-colour file) for the layout; palette 256x3 and idx for indexed files (index 0 = transparent),
    else alpha HxW or None."""

    def __init__(self, path):
        im = Image.open(path)
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        self.mode = im.mode
        self.palette = self.idx = self.alpha = None
        if im.mode == "P":
            pal = im.getpalette() or []
            pal = (pal + [0] * 768)[:768]
            self.palette = np.array(pal, dtype=np.uint8).reshape(256, 3)
            self.idx = np.array(im, dtype=np.uint8)
            self.rgb = self.palette[self.idx]
            self.labels = self.idx.astype(np.int32)
        else:
            rgba = np.array(im.convert("RGBA"))
            self.rgb = np.ascontiguousarray(rgba[:, :, :3])
            if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
                self.alpha = rgba[:, :, 3].copy()
            flat = self.rgb.reshape(-1, 3)
            _, inv = np.unique(flat, axis=0, return_inverse=True)
            self.labels = inv.reshape(self.rgb.shape[:2]).astype(np.int32)
            pal_txt = os.path.splitext(path)[0] + ".pal.txt"
            if os.path.exists(pal_txt):
                try:
                    rows = [tuple(int(v) for v in l.split()[:3]) for l in open(pal_txt) if l.strip()]
                    self.palette = np.array(rows[:256], dtype=np.uint8)
                except Exception:
                    pass
        self.h, self.w = self.rgb.shape[:2]


def max_rect(b):
    """The largest all-True axis-aligned rectangle of a bool matrix: (area, x0, y0, x1, y1), inclusive."""
    h, w = b.shape
    best = (0, 0, 0, -1, -1)
    hist = np.zeros(w, dtype=np.int32)
    for y in range(h):
        hist = np.where(b[y], hist + 1, 0)
        hl = hist.tolist() + [0]
        stack = []
        for x in range(w + 1):
            cur = hl[x]
            start = x
            while stack and stack[-1][1] >= cur:
                sx, sh = stack.pop()
                area = sh * (x - sx)
                if area > best[0]:
                    best = (int(area), int(sx), int(y - sh + 1), int(x - 1), int(y))
                start = sx
            stack.append((start, cur))
    return best


def near(rgb, c, tol):
    """Pixels within tol of colour c on every channel."""
    return np.abs(rgb.astype(np.int16) - np.asarray(c, dtype=np.int16)).max(axis=2) <= tol


def flat_panels(src, mode="auto", min_frac=0.05, tol=None):
    """The flat text panels of a picture — rectangles of one colour: the uniform margins at the border
    first, then the biggest uniform full-height or full-width strips (>= min_frac of the picture). Returns (mask HxW bool, fill HxWx3): fill is the picture with every panel made one exact
    colour (indexed files are exact already; a true-colour file, e.g. an upscale, is matched within tol
    and its panel colour snapped to the palette of <name>.pal.txt when there is one).
    mode: auto | none | l,t,r,b (pixels)."""
    h, w = src.h, src.w
    rgb = src.rgb
    mask = np.zeros((h, w), dtype=bool)
    fill = rgb.copy()
    if mode == "none":
        return mask, fill
    exact = src.idx is not None
    if tol is None:
        tol = 0 if exact else 14
    rects = []
    if mode != "auto":
        l, t, r, b = [int(v) for v in mode.split(",")]
        if l:
            rects.append((0, 0, l - 1, h - 1))
        if t:
            rects.append((0, 0, w - 1, t - 1))
        if r:
            rects.append((w - r, 0, w - 1, h - 1))
        if b:
            rects.append((0, h - b, w - 1, h - 1))
    else:
        min_area = int(min_frac * h * w)
        # 1. margins: full columns / rows of the corner's colour
        for side in range(4):
            a = np.rot90(rgb, side)  # the side to test is now the left edge
            c = np.median(a[:8, :8].reshape(-1, 3), axis=0) if not exact else a[0, 0]
            ok = near(a, c, tol)
            n = 0
            while n < a.shape[1] and ok[:, n].all():
                n += 1
            if n * a.shape[0] >= min_area:
                m = np.zeros(a.shape[:2], dtype=bool)
                m[:, :n] = True
                m = np.rot90(m, -side)
                ys, xs = np.nonzero(m)
                rects.append((int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())))
                mask |= m
        # 2. the biggest uniform rectangles outside what is marked (a panel that does not reach a corner)
        for _ in range(3):
            rest = ~mask
            if not rest.any():
                break
            if exact:
                counts = np.bincount(src.labels[rest].ravel())
                cands = [src.palette[c] for c in np.nonzero(counts >= min_area)[0]]
            else:
                q = (rgb[rest] // 12).astype(np.int32)
                keys = q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]
                uk, cnt = np.unique(keys, return_counts=True)
                cands = []
                for key in uk[np.argsort(-cnt)[:6]]:
                    sel = rgb[rest][keys == key]
                    if len(sel) >= min_area // 2:
                        cands.append(np.median(sel, axis=0))
            best = (0,)
            for c in cands:
                r = max_rect(near(rgb, c, tol) & rest)
                if r[0] > best[0]:
                    best = r
            if best[0] < min_area:
                break
            area, x0, y0, x1, y1 = best
            strip = (y0 == 0 and y1 == h - 1) or (x0 == 0 and x1 == w - 1)
            if not strip:
                break  # a uniform patch inside the drawing (a dark corner), not a text panel
            rects.append((x0, y0, x1, y1))
            mask[y0:y1 + 1, x0:x1 + 1] = True
    for x0, y0, x1, y1 in rects:
        mask[y0:y1 + 1, x0:x1 + 1] = True
        if not exact:
            c = np.median(rgb[y0:y1 + 1, x0:x1 + 1].reshape(-1, 3), axis=0)
            if src.palette is not None:
                c = src.palette[np.abs(src.palette.astype(np.int16) - c).sum(axis=1).argmin()]
            fill[y0:y1 + 1, x0:x1 + 1] = np.asarray(c, dtype=np.uint8)
    return mask, fill


def picture_box(mask):
    """Bounding box (x0, y0, x1, y1 inclusive) of what is painted, or None when nothing is."""
    ys, xs = np.nonzero(~mask)
    if len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def big_regions(mask, min_area):
    """Only the connected regions of a bool mask with at least min_area pixels (speckles dropped)."""
    if not mask.any():
        return mask
    try:
        import cv2
        n, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=4)
        counts = np.bincount(labels.ravel())
        keep_ids = np.nonzero(counts >= min_area)[0]
        return np.isin(labels, keep_ids[keep_ids != 0])
    except ImportError:
        pass
    try:
        from scipy import ndimage
        labels, n = ndimage.label(mask)
        counts = np.bincount(labels.ravel())
        keep_ids = np.nonzero(counts >= min_area)[0]
        return np.isin(labels, keep_ids[keep_ids != 0])
    except ImportError:
        pass
    # neither: grow regions with numpy (slow but rare)
    out = np.zeros_like(mask)
    rest = mask.copy()
    while rest.any():
        ys, xs = np.nonzero(rest)
        comp = np.zeros_like(rest)
        comp[ys[0], xs[0]] = True
        while True:
            grown = comp.copy()
            grown[1:, :] |= comp[:-1, :]
            grown[:-1, :] |= comp[1:, :]
            grown[:, 1:] |= comp[:, :-1]
            grown[:, :-1] |= comp[:, 1:]
            grown &= rest
            if grown.sum() == comp.sum():
                break
            comp = grown
        if comp.sum() >= min_area:
            out |= comp
        rest &= ~comp
    return out


def transparent_regions(src, min_frac=0.005):
    """The big transparent areas of a source (index 0 / alpha 0): what stays clear in the output.
    Single transparent pixels inside a drawing (index 0 used as black) are not transparent here."""
    if src.idx is not None:
        t = src.idx == 0
    elif src.alpha is not None:
        t = src.alpha == 0
    else:
        return np.zeros((src.h, src.w), dtype=bool)
    return big_regions(t, int(min_frac * src.h * src.w))


def line_peelable(src, line, keep_line, tol, share=0.9):
    """A row/column on the edge of the painted box that is not picture: kept already, or (apart from kept
    pixels) one colour for at least `share` of it - a frame line with a few corner pixels."""
    if keep_line.mean() >= 0.95:
        return True
    rest = line[~keep_line]
    if len(rest) == 0:
        return True
    if src.idx is not None:
        _, counts = np.unique(rest.reshape(-1, 3), axis=0, return_counts=True)
        return counts.max() >= share * len(rest)
    c = np.median(rest.reshape(-1, 3), axis=0)
    return (np.abs(rest.astype(np.int16) - c).max(axis=1) <= tol).mean() >= share


def opened(mask, r):
    """Morphological opening of a bool mask with a (2r+1)-square: thin lines and specks vanish."""
    try:
        import cv2
        k = np.ones((2 * r + 1, 2 * r + 1), np.uint8)
        return cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, k) > 0
    except ImportError:
        pass
    try:
        from scipy import ndimage
        return ndimage.binary_opening(mask, structure=np.ones((2 * r + 1, 2 * r + 1), bool))
    except ImportError:
        pass
    pad = np.pad(mask, r, constant_values=False)
    ero = np.ones_like(mask)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            ero &= pad[r + dy:r + dy + mask.shape[0], r + dx:r + dx + mask.shape[1]]
    pad = np.pad(ero, r, constant_values=False)
    dil = np.zeros_like(mask)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            dil |= pad[r + dy:r + dy + mask.shape[0], r + dx:r + dx + mask.shape[1]]
    return dil


def layout(src, mode="auto", tol=None, frame=6):
    """What is painted and what is kept. keep = flat text panels + big transparent areas (index 0 / alpha 0)
    + frame lines (rows/columns of one colour on the edges of the picture area - the border of an award, up
    to `frame` a side). The painted box is the picture proper: the bounding box of what is neither kept nor
    a thin line (an opening of radius 3), grown back by 3 px and peeled of frame lines. Whatever lies outside
    the box stays as the input picture. Returns (keep HxW bool, fill HxWx3, box or None, parts)."""
    mask, fill = flat_panels(src, mode, tol=tol)
    if tol is None:
        tol = 0 if src.idx is not None else 14
    clear = transparent_regions(src)
    keep = mask | clear
    framed = 0
    if mode == "none":
        box = picture_box(keep)
    else:
        r = 3
        body = opened(~keep, r)
        box = picture_box(~body)
        if box is not None:
            outer = picture_box(keep)
            x0, y0, x1, y1 = box
            x0, y0 = max(x0 - r, outer[0]), max(y0 - r, outer[1])
            x1, y1 = min(x1 + r, outer[2]), min(y1 + r, outer[3])
            peeled = [0, 0, 0, 0]
            while x1 - x0 >= 8 and y1 - y0 >= 8:
                changed = False
                for side in range(4):
                    if side == 0:
                        sl = (slice(y0, y1 + 1), slice(x0, x0 + 1))
                    elif side == 1:
                        sl = (slice(y0, y1 + 1), slice(x1, x1 + 1))
                    elif side == 2:
                        sl = (slice(y0, y0 + 1), slice(x0, x1 + 1))
                    else:
                        sl = (slice(y1, y1 + 1), slice(x0, x1 + 1))
                    line, kl = src.rgb[sl].reshape(-1, 3), keep[sl].reshape(-1)
                    coloured = kl.mean() < 0.95
                    if coloured and peeled[side] >= frame:
                        continue
                    if not line_peelable(src, line, kl, tol):
                        continue
                    keep[sl] = True
                    changed = True
                    if coloured:
                        peeled[side] += 1
                        framed += 1
                    if side == 0:
                        x0 += 1
                    elif side == 1:
                        x1 -= 1
                    elif side == 2:
                        y0 += 1
                    else:
                        y1 -= 1
                    if x1 - x0 < 8 or y1 - y0 < 8:
                        break
                if not changed:
                    break
            box = (x0, y0, x1, y1)
            # the picture is the box: nothing outside it is painted
            outside = np.ones_like(keep)
            outside[y0:y1 + 1, x0:x1 + 1] = False
            keep |= outside
    parts = []
    if mask.any():
        parts.append("panel %.0f%%" % (100.0 * mask.mean()))
    if clear.any():
        parts.append("clear %.0f%%" % (100.0 * clear.mean()))
    if framed:
        parts.append("frame %d lines" % framed)
    return keep, fill, box, ", ".join(parts) or "none"


class Upscaler:
    """A spandrel super-resolution model (x4, e.g. RealESRGAN_x4plus.pth) on the GPU, or nothing."""

    def __init__(self, model_path):
        self.model = None
        self.factor = 1
        if not model_path or not os.path.exists(model_path):
            return
        try:
            import torch
            from spandrel import ModelLoader
        except ImportError:
            print("no spandrel in the venv: sources without an hd/UI picture get a smooth upscale (pip install spandrel)")
            return
        desc = ModelLoader().load_from_file(model_path)
        self.factor = int(desc.scale)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        desc = desc.to(self.device).eval()
        self.half = self.device == "cuda" and desc.supports_half
        if self.half:
            desc = desc.half()
        self.model = desc
        self.torch = torch
        print("upscaler:", os.path.basename(model_path), "x%d" % self.factor)

    def run(self, rgb):
        torch = self.torch
        t = torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1).float().div(255.0).unsqueeze(0).to(self.device)
        if self.half:
            t = t.half()
        with torch.no_grad():
            o = self.model(t)
        return o.squeeze(0).float().clamp(0, 1).mul(255.0).round().byte().permute(1, 2, 0).cpu().numpy()

    def up(self, rgb, k, dedither=0.45):
        """rgb k times bigger: model passes and a resize to the exact factor."""
        src = rgb
        if dedither > 0:
            src = np.array(Image.fromarray(rgb).filter(ImageFilter.GaussianBlur(dedither)))
        out, have = src, 1
        while have < k:
            out = self.run(out)
            have *= self.factor
        if have != k:
            out = np.array(Image.fromarray(out).resize((rgb.shape[1] * k, rgb.shape[0] * k), Image.LANCZOS))
        return out


def hd_input(src, path, hd_dir, scale, upscaler=None):
    """The model's input and its factor k over the source: the source itself when it is big already
    (an hd/UI picture), else the 4x Real-ESRGAN picture of hd/UI when there is one, else the upscaler
    (Real-ESRGAN in this process), else a smooth upscale."""
    if src.w >= 640 and not scale:
        return src.rgb, 1, "source"
    name = os.path.splitext(os.path.basename(path))[0]
    hd_path = os.path.join(hd_dir, name + ".png") if hd_dir else ""
    if hd_path and os.path.exists(hd_path) and not os.path.samefile(hd_path, path):
        im = Image.open(hd_path).convert("RGB")
        k = scale or max(1, int(round(im.width / float(src.w))))
        if im.size != (src.w * k, src.h * k):
            im = im.resize((src.w * k, src.h * k), Image.LANCZOS)
        return np.array(im), k, "hd/UI"
    k = scale or 4
    if k == 1:
        return src.rgb, 1, "source"
    if upscaler is not None and upscaler.model is not None:
        return upscaler.up(src.rgb, k), k, "esrgan x%d" % k
    return np.array(Image.fromarray(src.rgb).resize((src.w * k, src.h * k), Image.LANCZOS)), k, "smooth x%d" % k


def match_tone(gen, ref, amount):
    """Pull the mean and spread of every channel of gen towards ref (amount 0..1)."""
    if amount <= 0:
        return gen
    g = gen.astype(np.float32)
    r = ref.astype(np.float32)
    out = np.empty_like(g)
    for c in range(3):
        gm, gs = g[..., c].mean(), g[..., c].std() + 1e-3
        rm, rs = r[..., c].mean(), r[..., c].std() + 1e-3
        fixed = (g[..., c] - gm) / gs * rs + rm
        out[..., c] = g[..., c] * (1 - amount) + fixed * amount
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def compose(hd, gen, box, k, mask, fill, src, tone):
    """The finished RGBA picture: the painted box inside the hd input, flat panels exactly the source's
    colours, transparency (index 0 / alpha) as in the source."""
    out = hd.copy()
    size = (out.shape[1], out.shape[0])
    if box is not None and gen is not None:
        x0, y0, x1, y1 = box
        X0, Y0, X1, Y1 = x0 * k, y0 * k, (x1 + 1) * k, (y1 + 1) * k
        crop = out[Y0:Y1, X0:X1]
        if gen.shape[:2] != crop.shape[:2]:
            gen = np.array(Image.fromarray(gen).resize((crop.shape[1], crop.shape[0]), Image.LANCZOS))
        out[Y0:Y1, X0:X1] = match_tone(gen, crop, tone)
    if mask.any():
        big_mask = np.array(Image.fromarray(mask.astype(np.uint8) * 255, "L").resize(size, Image.NEAREST)) > 0
        big_fill = np.array(Image.fromarray(fill).resize(size, Image.NEAREST))
        out[big_mask] = big_fill[big_mask]
    pic = Image.fromarray(out).convert("RGBA")
    clear = transparent_regions(src)
    if clear.any():
        a = np.where(clear, 0, 255).astype(np.uint8)
        if src.alpha is not None:
            a = np.minimum(a, np.where(src.alpha == 0, 255, src.alpha))  # soft edges of a true-colour alpha stay
        pic.putalpha(Image.fromarray(a, "L").resize(size, Image.NEAREST))
    return pic


def layout_preview(hd, mask, box, k, path):
    """hd with the flat panels tinted and the painted box outlined — what --dry-run shows."""
    im = Image.fromarray(hd).convert("RGBA")
    if mask.any():
        m = Image.fromarray(mask.astype(np.uint8) * 110, "L").resize(im.size, Image.NEAREST)
        tint = Image.new("RGBA", im.size, (0, 200, 255, 0))
        tint.putalpha(m)
        im = Image.alpha_composite(im, tint)
    d = ImageDraw.Draw(im)
    if box:
        x0, y0, x1, y1 = box
        d.rectangle([x0 * k, y0 * k, (x1 + 1) * k - 1, (y1 + 1) * k - 1], outline=(255, 60, 60, 255), width=3)
        d.text((x0 * k + 8, y0 * k + 6), "painted %dx%d" % ((x1 - x0 + 1) * k, (y1 - y0 + 1) * k), fill=(255, 60, 60, 255))
    if mask.any():
        d.text((8, 6), "kept as is (panel / transparent / frame)", fill=(0, 200, 255, 255))
    im.save(path)


def contact_sheet(tiles, path, box=None, k=1, longest=720):
    """tiles: list of (label, PIL image) -> one PNG, 3 columns; only the painted box of each when given."""
    if box:
        x0, y0, x1, y1 = box
        tiles = [(l, im.crop((x0 * k, y0 * k, (x1 + 1) * k, (y1 + 1) * k))) for l, im in tiles]
    w, h = tiles[0][1].size
    s = longest / float(max(w, h))
    cell = (max(1, int(w * s)), max(1, int(h * s)))
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    cw, ch = cell
    sheet = Image.new("RGB", (cols * cw, rows * (ch + 24)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:
        font = ImageFont.load_default()
    for i, (label, im) in enumerate(tiles):
        r, c = divmod(i, cols)
        x, y = c * cw, r * (ch + 24)
        d.text((x + 6, y + 4), label, fill=(240, 240, 240), font=font)
        sheet.paste(im.convert("RGB").resize(cell, Image.LANCZOS), (x, y + 24))
    sheet.save(path)


def target_size(w, h, mp, mult=32):
    """Generation size: aspect kept, ~mp megapixels, multiples of mult."""
    s = math.sqrt(mp * 1e6 / float(w * h))
    W = max(mult, int(round(w * s / mult)) * mult)
    H = max(mult, int(round(h * s / mult)) * mult)
    return W, H


def seed_of(name, seed):
    if seed:
        return seed
    return int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16) & 0x7FFFFFFF


# ---------------------------------------------------------------- the model

def models_env(models_dir):
    os.environ.setdefault("HF_HOME", models_dir)
    os.environ.setdefault("HF_HUB_CACHE", os.path.join(models_dir, "hub"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.makedirs(os.environ["HF_HUB_CACHE"], exist_ok=True)


def pick_lora(repo, words):
    """The local path of the repo's LoRA file whose name has all the words (else the first .safetensors)."""
    from huggingface_hub import hf_hub_download
    try:
        from huggingface_hub import list_repo_files
        files = list_repo_files(repo)
    except Exception as e:
        # offline: whatever of the repo is in the cache
        from huggingface_hub import scan_cache_dir
        try:
            files = [f.file_name for r in scan_cache_dir().repos if r.repo_id == repo for rev in r.revisions for f in rev.files]
        except Exception:
            files = []
        if not files:
            raise RuntimeError("%s: not reachable and not in the cache (%s)" % (repo, e))
    files = [f for f in files if f.endswith(".safetensors")]
    good = [f for f in files if all(w in f for w in words)] or files
    if not good:
        raise RuntimeError("no .safetensors in " + repo)
    good.sort(key=lambda f: (f.count("/"), len(f)))
    return hf_hub_download(repo, good[0])


def download(models_dir, with_lora=True):
    models_env(models_dir)
    from huggingface_hub import snapshot_download
    print("== %s (about 57 GB, once) -> %s" % (MODEL, os.environ["HF_HUB_CACHE"]))
    snapshot_download(MODEL, allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.py"])
    print("== Lightning LoRA:", pick_lora(*LIGHTNING))
    if with_lora:
        print("== Anime-to-Photoreal LoRA:", pick_lora(*PHOTOREAL))
    print("done")


class Swapper:
    """A module whose weights wait in pinned RAM and are copied to the GPU only while it works: weights
    never change, so 'offloading' is just pointing the parameters back at the pinned copies."""

    def __init__(self, module, torch):
        self.module, self.torch = module, torch
        self.cpu = {}
        for n, prm in module.named_parameters():
            prm.data = prm.data.pin_memory()
            self.cpu[n] = prm.data
        for buf in module.buffers():
            buf.data = buf.data.to("cuda")

    def to_gpu(self):
        for n, prm in self.module.named_parameters():
            prm.data = self.cpu[n].to("cuda", non_blocking=True)
        self.torch.cuda.synchronize()

    def to_cpu(self):
        for n, prm in self.module.named_parameters():
            prm.data = self.cpu[n]
        self.torch.cuda.empty_cache()


class Painter:
    """Qwen-Image-Edit-2511 on the GPU: transformer stored fp8 / computed bf16 and resident, the text
    encoder (fp8 too) swapped in from pinned RAM for the prompt of every picture (--offload swap), or
    everything resident (none), or diffusers' model offloading of every part (all, the slow way)."""

    def __init__(self, models_dir, fast, steps, quant="fp8", gguf="", photoreal=True, offload="swap"):
        models_env(models_dir)
        import torch
        from diffusers import FlowMatchEulerDiscreteScheduler, QwenImageEditPlusPipeline, QwenImageTransformer2DModel
        from transformers import Qwen2_5_VLForConditionalGeneration
        self.torch = torch
        self.fast = fast
        self.offload = offload
        t0 = time.time()
        print("loading %s (%s, offload %s)..." % (MODEL, quant, offload))
        # Order matters for RAM: the 41 GB bf16 transformer first, LoRA into it, shrink it to fp8 (20 GB),
        # only then the 17 GB text encoder (shrunk to 8 GB) — about 30 GB of RAM instead of a 58 GB peak.
        if quant == "gguf":
            from diffusers import GGUFQuantizationConfig
            if not gguf:
                raise SystemExit("--quant gguf needs --gguf <file.gguf> (a Q8_0 of the 2511 transformer)")
            tr = QwenImageTransformer2DModel.from_single_file(
                gguf, quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
                config=MODEL, subfolder="transformer", torch_dtype=torch.bfloat16)
        else:
            tr = QwenImageTransformer2DModel.from_pretrained(MODEL, subfolder="transformer", torch_dtype=torch.bfloat16)
        pipe = QwenImageEditPlusPipeline.from_pretrained(MODEL, transformer=tr, text_encoder=None, torch_dtype=torch.bfloat16)
        self.base_scheduler = pipe.scheduler
        self.fast_scheduler = FlowMatchEulerDiscreteScheduler.from_config(LIGHTNING_SCHEDULER)
        self.adapters = []
        if photoreal:
            path = pick_lora(*PHOTOREAL)
            pipe.load_lora_weights(os.path.dirname(path), weight_name=os.path.basename(path), adapter_name="photoreal")
            self.adapters.append("photoreal")
        if fast:
            words = ("%dsteps" % (8 if steps >= 8 else 4), "bf16")
            path = pick_lora(LIGHTNING[0], words)
            pipe.load_lora_weights(os.path.dirname(path), weight_name=os.path.basename(path), adapter_name="lightning")
            self.adapters.append("lightning")
            print("Lightning LoRA:", os.path.basename(path))
        if quant == "fp8":
            # weights live as fp8 (20 GB), every layer is cast to bf16 for its forward; LoRA layers stay bf16
            skip = ("pos_embed", "patch_embed", "norm", r"^proj_in$", r"^proj_out$", "lora")
            tr.enable_layerwise_casting(storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16,
                                        skip_modules_pattern=skip)
        elif quant == "none":
            pass  # bf16 everywhere: 41 GB of VRAM for the transformer alone
        te = Qwen2_5_VLForConditionalGeneration.from_pretrained(MODEL, subfolder="text_encoder", torch_dtype=torch.bfloat16)
        pipe.register_modules(text_encoder=te)
        self.swap = None
        if offload == "all":
            pipe.enable_model_cpu_offload()
        else:
            from diffusers.hooks import apply_layerwise_casting
            apply_layerwise_casting(te, storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16,
                                    skip_modules_pattern=("embed", "norm", "lm_head", "rotary"))
            pipe.transformer.to("cuda")
            pipe.vae.to("cuda")
            if offload == "none":
                te.to("cuda")
            else:
                self.swap = Swapper(te, torch)
        pipe.set_progress_bar_config(disable=True)
        self.pipe = pipe
        print("model ready in %.0f s; LoRA: %s" % (time.time() - t0, ", ".join(self.adapters) or "none"))

    def condition_image(self, img):
        """The picture as the pipeline shows it to the text encoder (its own resize rule)."""
        from diffusers.pipelines.qwenimage import pipeline_qwenimage_edit_plus as m
        dims = m.calculate_dimensions(m.CONDITION_IMAGE_SIZE, img.width / float(img.height))
        cw, ch = int(dims[0]), int(dims[1])
        return self.pipe.image_processor.resize(img, ch, cw)

    def encode(self, prompt, cond, dev):
        """Prompt + picture through the text encoder -> (embeds, mask) in bf16 (the encoder's fp8 storage
        must not become the embeddings' dtype)."""
        torch = self.torch
        fn = getattr(self.pipe, "_get_qwen_prompt_embeds", None)
        if fn is not None:
            try:
                return fn(prompt, cond, dev, torch.bfloat16)
            except TypeError:
                pass
        pe, pm = self.pipe.encode_prompt(prompt=prompt, image=cond, device=dev)
        return pe.to(torch.bfloat16), pm

    def edit(self, images, prompt, negative, seed, steps, cfg, W, H, photoreal=0.0):
        """One instruction edit: images (PIL, the first is edited, the rest are references) -> RGB array WxH."""
        torch = self.torch
        if self.adapters:
            weights = [photoreal if a == "photoreal" else 1.0 for a in self.adapters]
            self.pipe.set_adapters(self.adapters, weights)
        self.pipe.scheduler = self.fast_scheduler if self.fast else self.base_scheduler
        g = torch.Generator("cuda").manual_seed(seed)
        if self.offload == "all":
            out = self.pipe(image=list(images), prompt=prompt, negative_prompt=negative if cfg > 1 else None,
                            true_cfg_scale=cfg, num_inference_steps=steps, height=H, width=W, generator=g).images[0]
            return np.array(out.convert("RGB"))
        # the prompt (with the pictures) through the text encoder while it is on the GPU, then the rest
        dev = torch.device("cuda")
        cond = [self.condition_image(im) for im in images]
        if self.swap:
            self.swap.to_gpu()
        try:
            with torch.no_grad():
                pe, pm = self.encode(prompt, cond, dev)
                npe = npm = None
                if cfg > 1:
                    npe, npm = self.encode(negative, cond, dev)
        except torch.cuda.OutOfMemoryError:
            raise SystemExit("out of GPU memory while encoding the prompt: run with --offload all (slower) or close what else uses the GPU")
        finally:
            if self.swap:
                self.swap.to_cpu()
        out = self.pipe(image=list(images), prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                        negative_prompt_embeds=npe, negative_prompt_embeds_mask=npm,
                        true_cfg_scale=cfg, num_inference_steps=steps, height=H, width=W, generator=g).images[0]
        return np.array(out.convert("RGB"))

    def paint(self, rgb, preset, seed, steps, cfg, mp, hint="", neg=""):
        p = PRESETS[preset]
        prompt = KEEP + " " + p["style"] + ((" " + hint.strip()) if hint and hint.strip() else "")
        negative = NEGATIVE + ((", " + neg.strip()) if neg and neg.strip() else "")
        h, w = rgb.shape[:2]
        W, H = target_size(w, h, mp)
        src = Image.fromarray(rgb).resize((W, H), Image.LANCZOS)
        return self.edit([src], prompt, negative, seed, steps, cfg, W, H, photoreal=p["lora"])


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="", help="folder(s) of the pictures, comma-separated: the mod's originals (320x200 PNG/GIF) or the 4x hd\\UI pictures themselves")
    ap.add_argument("--exclude", default="", help="skip files whose name starts with any of these (comma-separated, e.g. UPed_)")
    ap.add_argument("--esrgan", default="", help="Real-ESRGAN model for the 4x input of originals without an hd\\UI picture (default <models>\\RealESRGAN_x4plus.pth if present); `none` = smooth upscale")
    ap.add_argument("--mod", default="user\\mods\\hd", help="mod with hd\\UI (the 4x inputs); outputs go next to it")
    ap.add_argument("--hd", default="", help="folder of the 4x inputs (default <mod>\\hd\\UI)")
    ap.add_argument("--out", default="", help="batch output folder (default <mod>\\hd\\UI_photo, or <dir>_photo when --dir holds the 4x pictures)")
    ap.add_argument("--refs-dir", default="photo_refs", help="where --refs writes")
    ap.add_argument("--refs", default="", help="name of one picture: every preset + a contact sheet")
    ap.add_argument("--preset", default="", help="batch mode with this preset: " + ", ".join(PRESETS))
    ap.add_argument("--presets", default=",".join(PRESETS), help="presets for --refs (comma-separated)")
    ap.add_argument("--fast", action="store_true", help="Lightning LoRA: 4 steps, no CFG (~10x faster, a bit rougher); --steps 8 takes the 8-step LoRA")
    ap.add_argument("--steps", type=int, default=0, help="denoising steps (40, or 4 with --fast)")
    ap.add_argument("--cfg", type=float, default=0, help="true CFG scale (4.0, or 1.0 with --fast)")
    ap.add_argument("--mp", type=float, default=1.0, help="megapixels the model paints at (1.0; 1.5 = finer, slower)")
    ap.add_argument("--tone", type=float, default=0.0, help="pull colours back towards the drawing, 0..1")
    ap.add_argument("--hint", default="", help="extra words for the prompt of every picture of this run (e.g. what the model keeps getting wrong)")
    ap.add_argument("--neg", default="", help="extra negative words for this run (only count without --fast, i.e. with CFG)")
    ap.add_argument("--hints", default="", help="file of per-picture hints, one per line `NAME: words | negative words` (`*: ...` = all); default tools\\hdart\\photo_hints.txt if it exists; `none` = ignore it")
    ap.add_argument("--panel", default="auto", help="flat text panel: auto | none | l,t,r,b (pixels of the source picture)")
    ap.add_argument("--tol", type=int, default=None, help="colour tolerance for a panel in a true-colour source (14; indexed files: exact)")
    ap.add_argument("--scale", type=int, default=0, help="force the output factor (default: the hd/UI picture's, or 4)")
    ap.add_argument("--seed", type=int, default=0, help="0 = a fixed seed per picture name")
    ap.add_argument("--names", default="", help="only these files (comma-separated, with or without extension), or @file.txt with one name per line")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many pictures")
    ap.add_argument("--force", action="store_true", help="remake pictures that exist")
    ap.add_argument("--no-lora", action="store_true", help="do not load the Anime-to-Photoreal LoRA (presets use it at 0)")
    ap.add_argument("--quant", default="fp8", choices=["fp8", "none", "gguf"], help="how the 20B transformer fits: fp8 storage (default), none (40 GB VRAM), gguf")
    ap.add_argument("--offload", default="swap", choices=["swap", "none", "all"], help="swap (default): transformer resident, text encoder swapped in per picture; none: all resident (tight in 32 GB); all: diffusers offloading of every part (slow)")
    ap.add_argument("--gguf", default="", help="a Q8_0 .gguf of the 2511 transformer for --quant gguf")
    ap.add_argument("--models", default=os.environ.get("HD_MODELS", "E:\\models"), help="HF cache root (setup_gen.ps1 uses E:\\models)")
    ap.add_argument("--download-only", action="store_true", help="fetch the models and exit")
    ap.add_argument("--dry-run", action="store_true", help="no model: only <name>_layout.png (panel + painted box)")
    args = ap.parse_args()

    if args.download_only:
        download(args.models, not args.no_lora)
        return 0
    if not args.dir:
        ap.error("--dir is required")
    if not args.refs and not args.preset and not args.dry_run:
        ap.error("--refs NAME or --preset P (or --dry-run)")
    if args.preset and args.preset not in PRESETS:
        ap.error("unknown preset %s; presets: %s" % (args.preset, ", ".join(PRESETS)))
    presets = [p for p in args.presets.split(",") if p]
    for p in presets:
        if p not in PRESETS:
            ap.error("unknown preset " + p)
    steps = args.steps or (4 if args.fast else 40)
    cfg = args.cfg or (1.0 if args.fast else 4.0)

    dirs = [d for d in args.dir.split(",") if d.strip()]
    files = []
    for d in dirs:
        files += sorted(f for f in glob.glob(os.path.join(d.strip(), "*")) if f.lower().endswith((".png", ".gif")))
    excl = tuple(e.strip().lower() for e in args.exclude.split(",") if e.strip())
    if excl:
        files = [f for f in files if not os.path.basename(f).lower().startswith(excl)]
    wanted = set()
    if args.refs:
        wanted = {os.path.splitext(args.refs)[0].lower()}
    elif args.names:
        if args.names.startswith("@"):
            # a list file: one name per line (comments with #), e.g. what to redo after a look
            with open(args.names[1:], encoding="utf-8") as f:
                items = [l.split("#", 1)[0].strip() for l in f]
        else:
            items = args.names.split(",")
        wanted = {os.path.splitext(os.path.basename(n))[0].lower() for n in items if n}
    if wanted:
        files = [f for f in files if os.path.splitext(os.path.basename(f))[0].lower() in wanted]
    if not files:
        print("nothing to do (no such picture in %s)" % ", ".join(dirs))
        return 1

    hd_dir = args.hd or os.path.join(args.mod, "hd", "UI")
    if args.refs or args.dry_run:
        out_dir = args.refs_dir
    elif args.out:
        out_dir = args.out
    else:
        probe = Image.open(files[0])
        out_dir = os.path.normpath(dirs[0]) + "_photo" if probe.width >= 640 else os.path.join(args.mod, "hd", "UI_photo")
    if any(os.path.normcase(os.path.abspath(out_dir)) == os.path.normcase(os.path.abspath(d.strip())) for d in dirs):
        ap.error("--out is a source folder itself; pictures would overwrite their inputs")
    os.makedirs(out_dir, exist_ok=True)

    esrgan = "" if args.esrgan.lower() == "none" else (args.esrgan or os.path.join(args.models, "RealESRGAN_x4plus.pth"))
    upscaler = Upscaler(esrgan) if not args.dry_run else None
    painter = None
    if not args.dry_run:
        need_lora = not args.no_lora and any(PRESETS[p]["lora"] > 0 for p in (presets if args.refs else [args.preset]))
        painter = Painter(args.models, args.fast, steps, args.quant, args.gguf, photoreal=need_lora, offload=args.offload)
        if args.fast:
            print("fast: %d steps, cfg %.1f" % (steps, cfg))
        else:
            print("quality: %d steps, cfg %.1f" % (steps, cfg))

    hints = {}
    hints_path = args.hints or os.path.join(os.path.dirname(os.path.abspath(__file__)), "photo_hints.txt")
    if args.hints.lower() == "none":
        hints_path = ""
    if hints_path and os.path.exists(hints_path):
        with open(hints_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                key, text = line.split(":", 1)
                pos, _, neg = text.partition("|")
                hints[os.path.splitext(key.strip())[0].lower()] = (pos.strip(), neg.strip())
        print("hints: %d from %s" % (len(hints), hints_path))
    if (args.neg or any(n for _, n in hints.values())) and cfg <= 1:
        print("note: negative words only act without --fast (CFG is off in the fast mode)")

    def hint_for(name):
        own = hints.get(name.lower(), ("", ""))
        shared = hints.get("*", ("", ""))
        pos = " ".join(t for t in (args.hint, shared[0], own[0]) if t)
        neg = ", ".join(t for t in (args.neg, shared[1], own[1]) if t)
        return pos, neg

    done = skipped = 0
    t0 = time.time()
    for i, path in enumerate(files):
        name = os.path.splitext(os.path.basename(path))[0]
        final = os.path.join(out_dir, name + ".png")
        if args.preset and os.path.exists(final) and not args.force:
            skipped += 1
            continue
        try:
            src = Source(path)
        except Exception as e:
            print(name, ": cannot read:", e)
            continue
        mask, fill, box, parts = layout(src, args.panel, tol=args.tol)
        hd, k, src_kind = hd_input(src, path, hd_dir, args.scale, upscaler)
        about = "%s: %s %dx%d, input %s %dx%d, kept: %s, painted box %s" % (
            name, src.mode, src.w, src.h, src_kind, hd.shape[1], hd.shape[0], parts,
            "%dx%d" % ((box[2] - box[0] + 1) * k, (box[3] - box[1] + 1) * k) if box else "none")
        if args.dry_run:
            layout_preview(hd, mask, box, k, os.path.join(out_dir, name + "_layout.png"))
            print(about, "-> %s_layout.png" % name)
            done += 1
            if args.limit and done >= args.limit:
                break
            continue
        if box is None:
            # a flat picture: nothing to paint, the input goes through
            print(about, "(flat, copied)")
            pic = compose(hd, None, None, k, mask, fill, src, 0)
            pic.save(final, compress_level=6)
            done += 1
            continue
        x0, y0, x1, y1 = box
        crop = hd[y0 * k:(y1 + 1) * k, x0 * k:(x1 + 1) * k]
        seed = seed_of(name, args.seed)
        if args.refs:
            print(about)
            tiles = [("original (%s)" % src_kind, Image.fromarray(hd))]
            for p in presets:
                t1 = time.time()
                gen = painter.paint(crop, p, seed, steps, cfg, args.mp, *hint_for(name))
                pic = compose(hd, gen, box, k, mask, fill, src, args.tone)
                out = os.path.join(out_dir, "%s_%s.png" % (name, p))
                pic.save(out, compress_level=6)
                tiles.append((p + (" (LoRA %.1f)" % PRESETS[p]["lora"] if PRESETS[p]["lora"] and painter.adapters else ""), pic))
                print("%s %s: %.0f s -> %s" % (name, p, time.time() - t1, out))
            sheet = os.path.join(out_dir, name + "_sheet.png")
            contact_sheet(tiles, sheet, box, k)
            print("sheet:", sheet)
            done += 1
        else:
            gen = painter.paint(crop, args.preset, seed, steps, cfg, args.mp, *hint_for(name))
            pic = compose(hd, gen, box, k, mask, fill, src, args.tone)
            pic.save(final, compress_level=6)
            pal_txt = os.path.join(out_dir, name + ".pal.txt")
            if src.palette is not None and not os.path.exists(pal_txt):
                with open(pal_txt, "w") as f:
                    f.write("\n".join("%d %d %d" % tuple(c) for c in src.palette) + "\n")
            done += 1
            el = time.time() - t0
            left = (len(files) - i - 1) * el / max(done, 1)
            print("%d/%d %s -> %dx%d, %.0f s/picture, ~%d min left" % (i + 1, len(files), name, pic.width, pic.height, el / done, left / 60))
        if args.limit and done >= args.limit:
            break
    print("done: %d made, %d skipped (exist) -> %s" % (done, skipped, out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
