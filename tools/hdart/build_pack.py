#!/usr/bin/env python3
"""
Cuts a painted HD sheet back into the frames of an HD pack.

    py -3 build_pack.py --sheets <sheets folder> --set CULTIVAT.PCK --hd <painted sheet.png> --mod <mod folder>
                        [--pack-path TERRAIN] [--alpha original|painted|both] [--feather 2] [--frames 0 3 7]
                        [--variants auto|off] [--variant-tone 1.0] [--no-preview]

The sheet must have the layout of <sheets>/<SET>/layout.json (extract_pck.py wrote it) at the
layout's scale: 1280x960 for CULTIVAT at 4x. Every frame is written as
<mod>/hd/<pack-path>/<SET>/<index>.png, RGBA, exactly (frame size x scale), which is what the engine
looks for (hd/TERRAIN/CULTIVAT.PCK/12.png for terrain, hd/XCOM_0.PCK/40.png for the other sets).

Alpha: painted output usually has an opaque background where the original was transparent, so the
frame's alpha is taken from the original's coverage (`original`, default: the mask feathered by a few
pixels, so that the painted edge is kept but nothing outside the sprite's silhouette leaks in),
from the painted sheet itself (`painted`), or from their product (`both`).

Color: the painter drifts in tone (a dark green tree comes back olive, the whole frame darker or
lighter), and neighbouring tiles must agree with each other and with the classic palette the rest of
the scene uses, so `--color-match 0.8` pulls every frame's per-channel mean and spread (over the
sprite's pixels) 80% of the way back to the original's.

Ground variants: when gen_hd.py painted variants (variants.json in the set's folder and
<painted>.v1.png ... next to the painted sheet), every varied floor also gets <index>.v<n>.png, with
the frame's alpha, the same floor sharing as the base painting (a floor that repeats another takes
that floor's variant n) and colours matched to the original recoloured by the variant's look
(`--variant-tone` scales that recolouring: 0 = the base painting's colours). variants_field.png in the
set's folder shows a field of floors without and with the variants, laid out by the engine's pattern.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xcom_sprites as xs  # noqa: E402


def color_match(painted, original, mask, amount):
    """Moves the painted frame's per-channel mean and standard deviation (over the sprite's pixels)
    toward the original's; amount 1 = exactly the original's statistics."""
    sel = np.array(mask) > 128
    if sel.sum() < 16:
        return painted
    p = np.asarray(painted).astype(np.float32)
    o = np.asarray(original).astype(np.float32)
    out = p.copy()
    for c in range(3):
        pm, ps = p[:, :, c][sel].mean(), p[:, :, c][sel].std()
        om, os_ = o[:, :, c][sel].mean(), o[:, :, c][sel].std()
        if ps < 1e-3:
            continue
        matched = (p[:, :, c] - pm) * (os_ / ps) + om
        out[:, :, c] = p[:, :, c] + amount * (matched - p[:, :, c])
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


_M_RGB2XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                       [0.2126729, 0.7151522, 0.0721750],
                       [0.0193339, 0.1191920, 0.9503041]], np.float64)
_M_XYZ2RGB = np.linalg.inv(_M_RGB2XYZ)
_WHITE = np.array([0.95047, 1.0, 1.08883], np.float64)
_E, _K = 216.0 / 24389.0, 24389.0 / 27.0


def _rgb_to_lab(rgb):
    """rgb 0..1 -> CIELAB. Своя реализация: build_pack запускается системным
    python, тащить в него scikit-image ради одной формулы не нужно."""
    c = np.clip(rgb, 0, 1)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _M_RGB2XYZ.T / _WHITE
    f = np.where(xyz > _E, np.cbrt(xyz), (_K * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16,
                     500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def _lab_to_rgb(lab):
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    def inv(v):
        v3 = v ** 3
        return np.where(v3 > _E, v3, (116 * v - 16) / _K)
    y = np.where(L > _K * _E, fy ** 3, L / _K)
    xyz = np.stack([inv(fx), y, inv(fz)], -1) * _WHITE
    lin = xyz @ _M_XYZ2RGB.T
    srgb = np.where(lin <= 0.0031308, lin * 12.92,
                    1.055 * np.maximum(lin, 0) ** (1 / 2.4) - 0.055)
    return np.clip(srgb, 0, 1)


def chroma_lock(painted, original, mask, amount, c_lo=8.0, c_hi=40.0,
                w_lo=0.25, w_hi=0.92, blur=2.0):
    """Яркость (детали, объём, фактура) остаётся от художника, цветность берётся
    у оригинала.

    Зачем: color_match двигает среднее и разброс по каналу для ВСЕГО кадра, и
    локальный насыщенный цвет им не вернуть. У X-Piratez, например, рампа 192-207
    палитры - от розового к фиолетовому; художник считает такой цвет ошибкой и
    перекрашивает панели в бежевый. Для игрока это потеря, а не улучшение.

    Чем насыщеннее цвет оригинала, тем жёстче привязка: именно он несёт смысл.
    Малонасыщенному (песок, серые панели) оставляем художнику свободу.
    Цветность низкочастотна, поэтому оригинал берём размытым - иначе на месте
    пикселей оригинала проступит сетка."""
    if amount <= 0:
        return painted
    sel = np.array(mask) > 128
    if sel.sum() < 16:
        return painted
    o = original.convert("RGB").filter(ImageFilter.GaussianBlur(blur))
    p_arr = np.asarray(painted.convert("RGB"), np.float64) / 255.0
    o_arr = np.asarray(o, np.float64) / 255.0
    lp, lo = _rgb_to_lab(p_arr), _rgb_to_lab(o_arr)
    chroma = np.hypot(lo[..., 1], lo[..., 2])
    w = (np.clip((chroma - c_lo) / (c_hi - c_lo), 0.0, 1.0) * (w_hi - w_lo) + w_lo)
    w = w * sel.astype(np.float64) * float(amount)
    out = lp.copy()
    out[..., 1] = lp[..., 1] + w * (lo[..., 1] - lp[..., 1])
    out[..., 2] = lp[..., 2] + w * (lo[..., 2] - lp[..., 2])
    rgb = (_lab_to_rgb(out) * 255.0 + 0.5).astype(np.uint8)
    res = np.asarray(painted.convert("RGBA")).copy()
    res[..., :3] = rgb
    return Image.fromarray(res, "RGBA")


def chroma_error(a, b, mask):
    """Отличие по цвету без учёта яркости: её художник вправе менять."""
    sel = np.array(mask) > 128
    if sel.sum() < 16:
        return 0.0
    la = _rgb_to_lab(np.asarray(a.convert("RGB"), np.float64) / 255.0)
    lb = _rgb_to_lab(np.asarray(b.convert("RGB"), np.float64) / 255.0)
    return float(np.hypot(la[..., 1] - lb[..., 1], la[..., 2] - lb[..., 2])[sel].mean())


def tint(rgba, tone, amount=1.0):
    """Recolours an image like gen_hd.tint (brightness, saturation, warmth), `amount` of the way; keeps alpha."""
    b, sat, warm = tone
    b, sat, warm = 1.0 + (b - 1.0) * amount, 1.0 + (sat - 1.0) * amount, warm * amount
    a = np.asarray(rgba.convert("RGBA")).astype(np.float32)
    rgb = a[:, :, :3]
    luma = (rgb * np.array([0.299, 0.587, 0.114], np.float32)).sum(axis=2, keepdims=True)
    rgb = (luma + (rgb - luma) * sat) * b * np.array([1.0 + warm, 1.0, 1.0 - warm], np.float32)
    a[:, :, :3] = rgb
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


# the engine's ground pattern (HdCanvas.cpp, "Ground variants"), for the preview
GROUND_WAVE, GROUND_WAVE2, GROUND_EDGE, GROUND_RAGGED = 6.0, 2.5, 0.16, 0.22


def _hash(seed, x, y, z):
    u = np.uint32
    h = np.full(np.shape(x), (seed ^ 0x9E3779B9) & 0xFFFFFFFF, dtype=np.uint64)
    m = np.uint64(0xFFFFFFFF)

    def rotl13(v):
        return ((v << np.uint64(13)) | (v >> np.uint64(19))) & m
    xs_ = np.asarray(x).astype(np.int64).astype(np.uint64) & m
    ys_ = np.asarray(y).astype(np.int64).astype(np.uint64) & m
    h ^= (xs_ * np.uint64(0x85EBCA6B)) & m
    h = (rotl13(h) * np.uint64(5) + np.uint64(0xE6546B64)) & m
    h ^= (ys_ * np.uint64(0xC2B2AE35)) & m
    h = (rotl13(h) * np.uint64(5) + np.uint64(0xE6546B64)) & m
    h ^= np.uint64((z * 0x27D4EB2F) & 0xFFFFFFFF)
    h ^= h >> np.uint64(16)
    h = (h * np.uint64(0x85EBCA6B)) & m
    h ^= h >> np.uint64(13)
    h = (h * np.uint64(0xC2B2AE35)) & m
    h ^= h >> np.uint64(16)
    return h.astype(u)


def _noise(seed, x, y, z=0):
    fx, fy = np.floor(x), np.floor(y)
    ix, iy = fx.astype(np.int64), fy.astype(np.int64)
    tx, ty = x - fx, y - fy
    tx = tx ** 3 * (tx * (tx * 6 - 15) + 10)
    ty = ty ** 3 * (ty * (ty * 6 - 15) + 10)

    def at(a, b):
        return (_hash(seed, a, b, z) & np.uint32(0xFFFFFF)).astype(np.float64) / 16777215.0
    v00, v10, v01, v11 = at(ix, iy), at(ix + 1, iy), at(ix, iy + 1), at(ix + 1, iy + 1)
    a = v00 + (v10 - v00) * tx
    b = v01 + (v11 - v01) * tx
    return a + (b - a) * ty


def ground_field(frames, cells=8, scale=4, seed=12345):
    """A field of `cells` x `cells` map cells of one floor, drawn as the engine draws it: `frames` =
    [base, v1, v2, ...] (RGBA, HD), laid on the scale the engine uses (base in the middle) and blended
    along the pattern's patch edges. One frame = no variants."""
    k = scale
    bw, bh = frames[0].width // k, frames[0].height // k
    count = len(frames)
    mid = count // 2
    order = [None] * count
    order[mid] = frames[0]
    for j in range(1, count):
        order[mid - (j + 1) // 2 if j % 2 else mid + j // 2] = frames[j]
    stack = np.stack([np.asarray(f.convert("RGBA")).astype(np.float32) for f in order])  # (count, H, W, 4)
    w = (cells * 2) * 16 * k
    h = cells * 16 * k + bh * k
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    by, bx = np.mgrid[0:bh, 0:bw].astype(np.float64)
    dx = bx + 0.5 - bw * 0.5
    ext = np.maximum(0.0, 8.0 - np.abs(dx) * 0.5)
    dy = np.clip(by + 0.5 - (bh - 8.0), -ext, ext)
    py, px = np.mgrid[0:bh * k, 0:bw * k].astype(np.float64)
    fx = np.clip((px + 0.5) / k - 0.5, 0, bw - 1)
    fy = np.clip((py + 0.5) / k - 0.5, 0, bh - 1)
    x0 = np.minimum(bw - 2, fx.astype(np.int64))
    y0 = np.minimum(bh - 2, fy.astype(np.int64))
    tx, ty = fx - x0, fy - y0

    def sample(grid):
        a = grid[y0, x0] + (grid[y0, x0 + 1] - grid[y0, x0]) * tx
        b = grid[y0 + 1, x0] + (grid[y0 + 1, x0 + 1] - grid[y0 + 1, x0]) * tx
        return a + (b - a) * ty
    for s in range(2 * cells - 1):
        for cx in range(cells):
            cy = s - cx
            if cy < 0 or cy >= cells:
                continue
            ox = (cx - cy) * 16 * k + (cells - 1) * 16 * k
            oy = (cx + cy) * 8 * k
            if count == 1:
                out.alpha_composite(frames[0], (ox, oy))
                continue
            u = cx + 0.5 + (dx / 16.0 + dy / 8.0) * 0.5
            v = cy + 0.5 + (dy / 8.0 - dx / 16.0) * 0.5
            n = 0.62 * _noise(seed, u / GROUND_WAVE, v / GROUND_WAVE) + \
                0.38 * _noise(seed + 101, u / GROUND_WAVE2 + 0.37, v / GROUND_WAVE2 + 0.71)
            level = np.clip((n - 0.5) * 2.4 + 0.5, 0, 1) * (count - 1)
            ragged = 0.6 * _noise(seed + 7, u * 5.0, v * 5.0) + 0.4 * _noise(seed + 13, u * 13.0, v * 13.0)
            p = sample(level)
            i = np.clip(np.floor(p).astype(np.int64), 0, count - 2)
            t = p - i + GROUND_RAGGED * (sample(ragged) - 0.5)
            t = np.clip((t - (0.5 - GROUND_EDGE)) / (2 * GROUND_EDGE), 0, 1)
            t = (t * t * (3 - 2 * t))[..., None]
            A = np.take_along_axis(stack, i[None, ..., None].repeat(4, axis=3), axis=0)[0]
            B = np.take_along_axis(stack, (i + 1)[None, ..., None].repeat(4, axis=3), axis=0)[0]
            fa, fb = (1 - t) * A[..., 3:], t * B[..., 3:]
            alpha = fa + fb
            rgb = (A[..., :3] * fa + B[..., :3] * fb) / np.maximum(alpha, 1e-6)
            cell = np.concatenate([rgb, (1 - t) * A[..., 3:] + t * B[..., 3:]], axis=2)
            out.alpha_composite(Image.fromarray(np.clip(cell, 0, 255).astype(np.uint8), "RGBA"), (ox, oy))
    return out


def field_preview(path, out_dir, vinfo, scale, cells=12):
    """variants_field.png: for a few varied floors (one per kind; plain ground first - a floor with
    something on it is not laid as a field) a field without and with the variants, at half size."""
    from PIL import ImageDraw
    frames = vinfo["frames"]

    def plain(key):
        hint = frames[key].get("hint", "")
        return " with " not in hint and " on " not in hint
    keys = sorted(frames, key=lambda key: (not plain(key), int(key)))
    picked, kinds = [], set()
    for key in keys:
        if frames[key]["kind"] not in kinds:
            kinds.add(frames[key]["kind"])
            picked.append(int(key))
    for key in keys:
        if len(picked) >= 3:
            break
        if int(key) not in picked and plain(key):
            picked.append(int(key))
    picked = picked[:3]
    rows = []
    for i in picked:
        base = os.path.join(out_dir, "%d.png" % i)
        vs = [os.path.join(out_dir, "%d.v%d.png" % (i, n)) for n in range(1, vinfo["count"] + 1)]
        if not os.path.exists(base) or not all(os.path.exists(v) for v in vs):
            continue
        frames = [Image.open(base).convert("RGBA")] + [Image.open(v).convert("RGBA") for v in vs]
        a = ground_field(frames[:1], cells, scale)
        b = ground_field(frames, cells, scale)
        half = (a.width // 2, a.height // 2)
        a, b = a.resize(half, Image.LANCZOS), b.resize(half, Image.LANCZOS)
        row = Image.new("RGB", (a.width * 2 + 16, a.height), (40, 40, 40))
        row.paste(a, (0, 0), a)
        row.paste(b, (a.width + 16, 0), b)
        d = ImageDraw.Draw(row)
        looks = " | ".join("v%d %s" % (n + 1, w) for n, (w, _) in enumerate(vinfo["frames"][str(i)]["looks"]))
        d.rectangle((0, 0, 12 + 6 * max(40, len(looks) + 20), 34), fill=(0, 0, 0))
        d.text((6, 4), "floor %d (%s): without variants | with them" % (i, vinfo["frames"][str(i)]["kind"]), fill=(255, 255, 0))
        d.text((6, 18), looks, fill=(255, 255, 255))
        rows.append(row)
    if not rows:
        return None
    sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height + 16 for r in rows) - 16), (40, 40, 40))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + 16
    sheet.save(path)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheets", required=True)
    ap.add_argument("--set", required=True, help="set name, e.g. CULTIVAT.PCK")
    ap.add_argument("--hd", required=True, help="the painted sheet (RGB or RGBA PNG)")
    ap.add_argument("--mod", required=True, help="mod folder to write hd/... into")
    ap.add_argument("--pack-path", default="", help="TERRAIN for terrain sets, empty for the rest")
    ap.add_argument("--alpha", choices=["original", "painted", "both"], default="original")
    ap.add_argument("--feather", type=float, default=1.5, help="softness (HD pixels) of object silhouettes outside the floor zone")
    ap.add_argument("--floor-under", type=float, default=1.0, help="0..1: how much of the set's own painted floor tile "
                    "replaces the floor pixels under objects that stand on it (0: keep the painted frame)")
    ap.add_argument("--grow", type=int, default=0, help="grow the original's coverage by this many HD pixels before feathering")
    ap.add_argument("--frames", nargs="*", type=int, default=[], help="only these frame indices")
    ap.add_argument("--color-match", type=float, default=0.8, help="0..1: how far each frame's mean and spread "
                    "per channel are pulled back to the original's (0 = keep the painter's colors)")
    ap.add_argument("--chroma-lock", type=float, default=1.0,
                    help="0..1: насколько цветность кадра притягивается к оригиналу при сохранении "
                         "яркости художника. Лечит потерю насыщенных цветов мода (0 = выключить)")
    ap.add_argument("--variants", choices=["auto", "off"], default="auto", help="auto: also write the ground variants "
                    "gen_hd.py painted (<index>.v<n>.png); off: none, and remove old ones")
    ap.add_argument("--variant-tone", type=float, default=1.0, help="how much of a variant's recolouring is kept "
                    "(0 = the base painting's colours, 1 = as its look says, 2 = twice as strong)")
    ap.add_argument("--no-preview", action="store_true", help="skip variants_field.png")
    ap.add_argument("--skip-empty", action="store_true", default=True)
    args = ap.parse_args(argv)

    set_name = args.set.upper()
    set_dir = os.path.join(args.sheets, set_name)
    with open(os.path.join(set_dir, "layout.json")) as f:
        info = json.load(f)
    scale = info["scale"]
    sheet = xs.Sheet(info["frame_w"], info["frame_h"], info["count"], info["columns"], info["margin"])
    painted = Image.open(args.hd).convert("RGBA")
    want = sheet.size(scale)
    if painted.size != want:
        print("error: %s is %dx%d, the layout wants %dx%d" % (args.hd, painted.width, painted.height, want[0], want[1]))
        sys.exit(1)
    # ground variants painted by gen_hd.py: variants.json + <painted>.v<n>.png
    vinfo, vsheets = None, {}
    keep_old_variants = False   # variants wanted but their sheets are not usable: leave the pack's as they are
    meta = os.path.join(set_dir, "variants.json")
    if args.variants == "auto" and os.path.exists(meta):
        with open(meta, encoding="utf-8") as f:
            vinfo = json.load(f)
        stem = os.path.splitext(args.hd)[0]
        for n in range(1, vinfo["count"] + 1):
            vpath = "%s.v%d.png" % (stem, n)
            if not os.path.exists(vpath):
                print("warning: %s is missing - no variants written, the pack's old ones stay "
                      "(run gen_hd.py --only variants --variants %d)" % (vpath, vinfo["count"]))
                vinfo, vsheets, keep_old_variants = None, {}, True
                break
            sheet_v = Image.open(vpath).convert("RGBA")
            if sheet_v.size != want:
                print("warning: %s is %dx%d, the layout wants %dx%d - no variants written, the pack's old ones stay"
                      % (vpath, sheet_v.width, sheet_v.height, want[0], want[1]))
                vinfo, vsheets, keep_old_variants = None, {}, True
                break
            vsheets[n] = sheet_v
    vframes = {int(k): v for k, v in vinfo["frames"].items()} if vinfo else {}
    mask = Image.open(os.path.join(set_dir, "mask_x%d.png" % scale)).convert("L")
    original = Image.open(os.path.join(set_dir, "original_x%d.png" % scale)).convert("RGBA")
    small_rgba = Image.open(os.path.join(set_dir, "original.png")).convert("RGBA")
    hard_mask = mask.copy()
    # objects get a smooth silhouette (the 1x coverage scaled with a filter, so the edge of a tree crown
    # is a curve, not a staircase), feathered a little; but wherever a frame meets its neighbours -
    # the rim of the floor diamond and the floor zone around it (floors, walls, an object's own ground
    # diamond) - the silhouette stays pixel-exact: a soft edge there lets the background through and
    # draws the tile grid over every field
    small = small_rgba.split()[3]
    smooth = small.resize((small.width * scale, small.height * scale), Image.LANCZOS).point(
        lambda a: max(0, min(255, (a - 96) * 3)))
    if args.grow > 0:
        smooth = smooth.filter(ImageFilter.MaxFilter(2 * args.grow + 1))
    if args.feather > 0:
        smooth = smooth.filter(ImageFilter.GaussianBlur(args.feather * 0.5))
    exact = Image.new("L", mask.size, 0)
    rim = xs.rim_zone(info["frame_w"], info["frame_h"]).resize((info["frame_w"] * scale, info["frame_h"] * scale), Image.NEAREST)
    for i in range(info["count"]):
        x, y, w, h = sheet.cell(i, scale)
        exact.paste(rim, (x, y))
    alpha_sheet = Image.composite(hard_mask, smooth, exact)
    ground = info.get("ground") or [False] * info["count"]
    base = info.get("base") or [False] * info["count"]
    types = info.get("types") or [-1] * info["count"]

    # the set's floors (1x), to find what an object stands on
    floors = [(i, sheet.cut(small_rgba, i, 1)) for i in range(info["count"])
              if types[i] == xs.MCD_FLOOR and ground[i] and sheet.cut(small_rgba, i, 1).getbbox() is not None]

    chroma_before, chroma_after = [], []

    def process(i):
        """The painted frame i, colour-matched, RGB only (alpha added by the caller)."""
        frame = sheet.cut(painted, i, scale)
        orig_i = sheet.cut(original, i, scale)
        mask_i = sheet.cut(hard_mask, i, scale)
        if args.color_match > 0:
            frame = color_match(frame, orig_i, mask_i, args.color_match)
        if args.chroma_lock > 0:
            before = chroma_error(frame, orig_i, mask_i)
            frame = chroma_lock(frame, orig_i, mask_i, args.chroma_lock)
            chroma_before.append(before)
            chroma_after.append(chroma_error(frame, orig_i, mask_i))
        return frame

    def process_variant(i, n):
        """Variant n of floor i, colour-matched to the original recoloured by the variant's look."""
        frame = sheet.cut(vsheets[n], i, scale)
        if args.color_match > 0 or args.chroma_lock > 0:
            target = tint(sheet.cut(original, i, scale), vframes[i]["looks"][n - 1][1], args.variant_tone)
            mask_i = sheet.cut(hard_mask, i, scale)
            if args.color_match > 0:
                frame = color_match(frame, target, mask_i, args.color_match)
            if args.chroma_lock > 0:
                # вариант привязываем к ПЕРЕКРАШЕННОМУ оригиналу, иначе вернём исходный цвет
                frame = chroma_lock(frame, target, mask_i, args.chroma_lock)
        return frame

    processed = {}
    processed_v = {n: {} for n in vsheets}

    def painting(j, n):
        """The finished painting of frame j for variant n (0 = base): what a floor passes on."""
        if n == 0 or j not in vframes:
            if j not in processed:
                processed[j] = process(j)
            return processed[j]
        if j not in processed_v[n]:
            processed_v[n][j] = process_variant(j, n)
        return processed_v[n][j]

    out_dir = os.path.join(args.mod, "hd", args.pack_path, set_name) if args.pack_path else os.path.join(args.mod, "hd", set_name)
    os.makedirs(out_dir, exist_ok=True)
    written = 0
    floored = 0
    faded = 0
    varied = 0
    removed = 0
    existing = [n for n in os.listdir(out_dir) if n.count(".") == 2 and n.endswith(".png") and ".v" in n]
    indices = args.frames if args.frames else range(info["count"])

    def rim_mean(frame_1x):
        """The mean colour of a frame's floor diamond rim (d >= 0.75), or None."""
        a = np.asarray(frame_1x).astype(np.float32)
        hh, ww = a.shape[:2]
        ys, xs_ = np.mgrid[0:hh, 0:ww]
        dd = np.abs(xs_ - (ww - 1) / 2.0) / (ww / 2.0) + np.abs(ys - (hh - 8.5)) / 8.0
        sel = (ys >= hh - 16) & (dd >= 0.75) & (dd <= 1.0) & (a[:, :, 3] > 0)
        if sel.sum() < 8:
            return None
        return a[:, :, :3][sel].mean(axis=0)
    for i in indices:
        frame_mask = sheet.cut(alpha_sheet, i, scale)
        if args.skip_empty and frame_mask.getbbox() is None:
            continue
        frame = process(i)
        # an object standing on one of the set's floors: the sprite carries that floor's pixels, and the
        # painter painted them again, differently from the floor tile next to it (a lighter or darker
        # patch under every tree and rock); so those pixels are taken from the floor's own painted tile.
        # The same for a floor with something drawn on it (a skull, a hole, a bush in the sand): it was
        # painted as a field of its own, and its plain part came out a shade apart from the plain floor
        # next to it; it takes the plain floor's painting (the floor of the lowest index it repeats, so
        # that a whole set's floors share one painting of the ground)
        floor_case = base[i] and not ground[i]
        ground_case = ground[i] and types[i] == xs.MCD_FLOOR
        plan = None   # (the floor whose painting is taken, weight HxWx1)
        if (floor_case or ground_case) and args.floor_under > 0:
            candidates = floors if floor_case else [(j, fl) for j, fl in floors if j < i]
            # a real match repeats a good part of the floor, not just a rim that happens to be the same
            need = 48 if floor_case else 128
            f, n = xs.floor_match(sheet.cut(small_rgba, i, 1), candidates, min_pixels=need)
            if f is not None and not floor_case:
                # the lowest index among the floors it repeats as well as the best one
                for j, fl in candidates:
                    if j >= f:
                        break
                    if xs.floor_match(sheet.cut(small_rgba, i, 1), [(j, fl)], min_pixels=need)[1] >= max(need, n * 3 // 4):
                        f = j
                        break
            if f is not None:
                take = xs.floor_pixels(sheet.cut(small_rgba, i, 1), sheet.cut(small_rgba, f, 1))
                obj = np.asarray(sheet.cut(small_rgba, i, 1).split()[3]) > 0
                obj = obj & ~take
                # keep a pixel of the object's own painted edge around it
                obj_img = Image.fromarray(np.where(obj, 255, 0).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(3))
                take = take & ~(np.asarray(obj_img) > 0)
                w = Image.fromarray(np.where(take, 255, 0).astype(np.uint8), "L").resize(
                    (frame.width, frame.height), Image.NEAREST).filter(ImageFilter.GaussianBlur(scale * 0.5))
                plan = (f, np.asarray(w).astype(np.float32)[..., None] / 255.0 * args.floor_under)
                floored += 1
            elif ground_case and candidates:
                # a floor of its own kind (a dune, a hollow, a different ground): where its edge is the
                # same ground as another floor (the rim colours agree), the edge fades into that floor's
                # painting, so that it rises out of the field instead of sitting on it as a diamond
                rim_i = rim_mean(sheet.cut(small_rgba, i, 1))
                best, best_d = None, None
                for j, fl in candidates:
                    rim_j = rim_mean(fl)
                    if rim_i is None or rim_j is None:
                        continue
                    dist = float(np.linalg.norm(rim_i - rim_j))
                    if best_d is None or dist < best_d:
                        best, best_d = j, dist
                if best is not None and best_d < 40:
                    hh, ww = frame.height, frame.width
                    ys, xs_ = np.mgrid[0:hh, 0:ww]
                    cx, cy = (ww - 1) / 2.0, hh - 8.5 * scale
                    dd = np.abs(xs_ - cx) / (ww / 2.0) + np.abs(ys - cy) / (8.0 * scale)
                    t = np.clip((dd - 0.7) / 0.3, 0, 1)
                    plan = (best, (t * t * (3 - 2 * t))[..., None] * args.floor_under * (ys >= hh - 16 * scale)[..., None])
                    faded += 1

        def finish(frame, n):
            """The painting with the plan's floor blended in (variant n of both, 0 = base)."""
            if plan is None:
                return frame
            fa = np.asarray(frame).astype(np.float32)
            ff = np.asarray(painting(plan[0], n)).astype(np.float32)
            wf = plan[1]
            fa[:, :, :3] = fa[:, :, :3] * (1 - wf) + ff[:, :, :3] * wf
            return Image.fromarray(np.clip(fa, 0, 255).astype(np.uint8), "RGBA")
        frame = finish(frame, 0)
        processed[i] = frame   # a floor that took another's painting passes that on
        r, g, b, a = frame.split()
        if args.alpha == "original":
            a = frame_mask
        elif args.alpha == "both":
            # the product of the painted alpha and the original's coverage
            pa, pm = a.load(), frame_mask.load()
            for y in range(a.height):
                for x in range(a.width):
                    pa[x, y] = pa[x, y] * pm[x, y] // 255
        out = Image.merge("RGBA", (r, g, b, a))
        out.save(os.path.join(out_dir, "%d.png" % i))
        written += 1
        # the ground variants of the floor, with the same alpha; stale ones go
        wanted = set()
        if i in vframes:
            for n in sorted(vsheets):
                vframe = finish(process_variant(i, n), n)
                processed_v[n][i] = vframe
                vr, vg, vb, _ = vframe.split()
                Image.merge("RGBA", (vr, vg, vb, a)).save(os.path.join(out_dir, "%d.v%d.png" % (i, n)))
                wanted.add("%d.v%d.png" % (i, n))
            varied += 1
        for name in ([] if keep_old_variants else existing):
            if name.startswith("%d.v" % i) and name not in wanted and name.split(".")[0] == str(i):
                os.remove(os.path.join(out_dir, name))
                removed += 1
    if floored:
        print("%s: %d objects got the set's floor under them" % (set_name, floored))
    if faded:
        print("%s: %d floors fade into another floor's painting at the edge" % (set_name, faded))
    if chroma_before:
        b_avg = sum(chroma_before) / len(chroma_before)
        a_avg = sum(chroma_after) / len(chroma_after)
        rough = sum(1 for v in chroma_after if v > 15)
        print("%s: цвет подтянут к оригиналу, отличие %.1f -> %.1f%s"
              % (set_name, b_avg, a_avg,
                 ("; кадров с грубым расхождением: %d - посмотри их глазами" % rough) if rough else ""))
    print("%s: %d frames -> %s" % (set_name, written, out_dir))
    if varied:
        print("%s: %d floors with %d variant(s) each (<index>.v<n>.png)" % (set_name, varied, len(vsheets)))
    if removed:
        print("%s: removed %d old variant file(s)" % (set_name, removed))
    if varied and not args.no_preview:
        preview = field_preview(os.path.join(set_dir, "variants_field.png"), out_dir, vinfo, scale)
        if preview:
            print("%s: field preview -> %s" % (set_name, preview))


if __name__ == "__main__":
    main()
