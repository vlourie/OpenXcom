#!/usr/bin/env python3
"""Pixel-art aware scaling of tiny sprites (xBRZ), and detail transfer from a model.

A 32x40 unit frame is not a photograph: nearly every pixel is a decision of the artist, so a
super-resolution model asked to make it four times bigger has little to work from and invents
things (dark line art around limbs, melted highlights, shifted colours). What does work on frames
this small is xBRZ - the same scaler the engine itself uses for sprites without a pack: it reads
the diagonal edges the pixels stand for and rebuilds them as straight, smooth lines, keeps single
pixels single, and never makes up a colour that was not in the frame.

This is a faithful port of xbrz.cpp (Zenju's xBRZ, the copy in src/Engine/Scalers), vectorised
with numpy over a batch of frames, in ARGB mode with the engine's settings, so a pack made here
starts from exactly what the engine would have drawn - and then improves on it.

A model can still help, but as a layer of texture on top: what is left of the model's picture
after a blur (its fine detail) is applied to the xBRZ picture as a change of brightness, clamped,
so the shapes, the silhouette and the colours stay xBRZ's.
"""

import numpy as np

# xbrz::ScalerCfg (src/Engine/Scalers/config.h)
LUMINANCE_WEIGHT = 1.0
EQUAL_COLOR_TOLERANCE = 30.0
DOMINANT_DIRECTION_THRESHOLD = 3.6
STEEP_DIRECTION_THRESHOLD = 2.2


def shift(a, dy, dx, fill=None):
    """The array shifted so out[y, x] = a[y + dy, x + dx]; edges repeated, or `fill` outside."""
    h, w = a.shape[1], a.shape[2]
    ys = np.arange(h) + dy
    xs = np.arange(w) + dx
    if fill is None:
        out = a[:, np.clip(ys, 0, h - 1)[:, None], np.clip(xs, 0, w - 1)[None, :]]
        return out
    out = np.full_like(a, fill)
    ya, yb = max(0, -dy), min(h, h - dy)
    xa, xb = max(0, -dx), min(w, w - dx)
    if ya < yb and xa < xb:
        out[:, ya:yb, xa:xb] = a[:, ya + dy:yb + dy, xa + dx:xb + dx]
    return out


def _dist(a, b):
    """xbrz ColorDistanceARGB: the YCbCr distance of the colours, weighted by the alphas."""
    rd = a[..., 0] - b[..., 0]
    gd = a[..., 1] - b[..., 1]
    bd = a[..., 2] - b[..., 2]
    k_b, k_r = 0.0593, 0.2627           # ITU-R BT.2020
    k_g = 1.0 - k_b - k_r
    y = k_r * rd + k_g * gd + k_b * bd
    c_b = (0.5 / (1.0 - k_b)) * (bd - y)
    c_r = (0.5 / (1.0 - k_r)) * (rd - y)
    d = np.sqrt((LUMINANCE_WEIGHT * y) ** 2 + c_b ** 2 + c_r ** 2)
    a1 = a[..., 3] / 255.0
    a2 = b[..., 3] / 255.0
    lo = np.minimum(a1, a2)
    return lo * d + 255.0 * np.abs(a1 - a2)


def _eq(a, b):
    return _dist(a, b) < EQUAL_COLOR_TOLERANCE


def _same(a, b):
    """Exact equality of two RGBA pixels (xbrz compares the packed values)."""
    return np.all(a == b, axis=-1)


def _patterns(k):
    """The blend patterns of xbrz's Scaler<k>x as (k, k) weight arrays: how much of the blended
    colour each pixel of the output block takes. Ported from xbrz.cpp."""
    z = lambda: np.zeros((k, k), dtype=np.float32)
    corner, diagonal, shallow, steep, both = z(), z(), z(), z(), z()
    if k == 2:
        corner[1, 1] = 21.0 / 100.0
        diagonal[1, 0] = 0.5; diagonal[0, 1] = 0.5; diagonal[1, 1] = 1.0
        shallow[1, 0] = 0.25; shallow[0, 1] = 0.25; shallow[1, 1] = 1.0
        steep[:] = shallow
        both[:] = shallow
    elif k == 3:
        corner[2, 2] = 45.0 / 100.0; corner[2, 1] = 14.0 / 1000.0; corner[1, 2] = 14.0 / 1000.0
        diagonal[2, 1] = 0.5; diagonal[1, 2] = 0.5; diagonal[2, 2] = 1.0
        shallow[2, 0] = 0.25; shallow[1, 2] = 0.25; shallow[2, 1] = 0.75; shallow[2, 2] = 1.0
        steep[0, 2] = 0.25; steep[2, 1] = 0.25; steep[1, 2] = 0.75; steep[2, 2] = 1.0
        both[2, 0] = 0.25; both[0, 2] = 0.25; both[2, 1] = 0.75; both[1, 2] = 0.75; both[2, 2] = 1.0
    elif k == 4:
        corner[3, 3] = 68.0 / 100.0; corner[3, 2] = 9.0 / 100.0; corner[2, 3] = 9.0 / 100.0
        diagonal[3, 2] = 0.5; diagonal[2, 3] = 0.5; diagonal[3, 3] = 1.0
        shallow[3, 0] = 0.25; shallow[2, 2] = 0.25; shallow[3, 1] = 0.75; shallow[2, 3] = 0.75
        shallow[3, 2] = 1.0; shallow[3, 3] = 1.0
        steep[0, 3] = 0.25; steep[2, 2] = 0.25; steep[1, 3] = 0.75; steep[3, 2] = 0.75
        steep[2, 3] = 1.0; steep[3, 3] = 1.0
        both[3, 1] = 0.75; both[1, 3] = 0.75; both[3, 0] = 0.25; both[0, 3] = 0.25
        both[2, 2] = 1.0 / 3.0; both[3, 3] = 1.0; both[3, 2] = 1.0; both[2, 3] = 1.0
    elif k == 5:
        corner[4, 4] = 1.0; corner[4, 3] = 0.25; corner[3, 4] = 0.25
        diagonal[4, 3] = 0.5; diagonal[3, 4] = 0.5; diagonal[4, 4] = 1.0
        shallow[4, 0] = 0.25; shallow[3, 2] = 0.25; shallow[2, 4] = 0.25
        shallow[4, 1] = 0.75; shallow[3, 3] = 0.75
        shallow[4, 2] = 1.0; shallow[4, 3] = 1.0; shallow[4, 4] = 1.0; shallow[3, 4] = 1.0
        steep[0, 4] = 0.25; steep[2, 3] = 0.25; steep[4, 2] = 0.25
        steep[1, 4] = 0.75; steep[3, 3] = 0.75
        steep[2, 4] = 1.0; steep[3, 4] = 1.0; steep[4, 4] = 1.0; steep[4, 3] = 1.0
        both[4, 0] = 0.25; both[0, 4] = 0.25; both[4, 1] = 0.75; both[1, 4] = 0.75
        both[4, 2] = 1.0; both[2, 4] = 1.0; both[4, 3] = 1.0; both[3, 4] = 1.0
        both[4, 4] = 1.0; both[3, 3] = 1.0
    elif k == 6:
        corner[5, 5] = 1.0; corner[5, 4] = 0.25; corner[4, 5] = 0.25
        diagonal[5, 4] = 0.5; diagonal[4, 5] = 0.5; diagonal[5, 5] = 1.0
        shallow[5, 0] = 0.25; shallow[4, 2] = 0.25; shallow[3, 4] = 0.25
        shallow[5, 1] = 0.75; shallow[4, 3] = 0.75; shallow[3, 5] = 0.75
        for c in range(2, 6):
            shallow[5, c] = 1.0
        shallow[4, 4] = 1.0; shallow[4, 5] = 1.0
        steep[0, 5] = 0.25; steep[2, 4] = 0.25; steep[4, 3] = 0.25
        steep[1, 5] = 0.75; steep[3, 4] = 0.75; steep[5, 3] = 0.75
        for r in range(2, 6):
            steep[r, 5] = 1.0
        steep[4, 4] = 1.0; steep[5, 4] = 1.0
        both[5, 1] = 0.75; both[1, 5] = 0.75; both[5, 0] = 0.25; both[0, 5] = 0.25
        both[4, 4] = 1.0 / 3.0
        for c in (2, 3, 4, 5):
            both[5, c] = 1.0
        for r in (2, 3, 4, 5):
            both[r, 5] = 1.0
    else:
        raise ValueError("scale %d: xbrz does 2..6" % k)
    return corner, diagonal, shallow, steep, both


def _corner_blends(s):
    """xbrz preProcessCorners over a batch: for every pixel, how the corner between it and its
    right, lower and lower-right neighbours blends. Returns (blend_f, blend_g, blend_j, blend_k),
    each (B, h, w) of 0 (none), 1 (normal), 2 (dominant)."""
    a = shift(s, -1, -1); b = shift(s, -1, 0); c = shift(s, -1, 1); d = shift(s, -1, 2)
    e = shift(s, 0, -1);  f = s;               g = shift(s, 0, 1);  h = shift(s, 0, 2)
    i = shift(s, 1, -1);  j = shift(s, 1, 0);  k = shift(s, 1, 1);  l = shift(s, 1, 2)
    m = shift(s, 2, -1);  n = shift(s, 2, 0);  o = shift(s, 2, 1);  p = shift(s, 2, 2)
    del a, d, m, p  # part of the kernel's naming, not used by the rule
    flat = (_same(f, g) & _same(j, k)) | (_same(f, j) & _same(g, k))
    jg = _dist(i, f) + _dist(f, c) + _dist(n, k) + _dist(k, h) + 4.0 * _dist(j, g)
    fk = _dist(e, j) + _dist(j, o) + _dist(b, g) + _dist(g, l) + 4.0 * _dist(f, k)
    blend_f = np.zeros(s.shape[:3], dtype=np.uint8)
    blend_g = np.zeros_like(blend_f)
    blend_j = np.zeros_like(blend_f)
    blend_k = np.zeros_like(blend_f)
    jg_wins = (jg < fk) & ~flat
    dom = np.where(jg_wins, DOMINANT_DIRECTION_THRESHOLD * jg < fk, False)
    blend_f[jg_wins & ~_same(f, g) & ~_same(f, j)] = 1
    blend_k[jg_wins & ~_same(k, j) & ~_same(k, g)] = 1
    fk_wins = (fk < jg) & ~flat
    dom2 = np.where(fk_wins, DOMINANT_DIRECTION_THRESHOLD * fk < jg, False)
    blend_j[fk_wins & ~_same(j, f) & ~_same(j, k)] = 1
    blend_g[fk_wins & ~_same(g, f) & ~_same(g, k)] = 1
    for arr, mask in ((blend_f, dom), (blend_k, dom), (blend_j, dom2), (blend_g, dom2)):
        arr[(arr == 1) & mask] = 2
    return blend_f, blend_g, blend_j, blend_k


def _pixel_corners(s):
    """The four corner flags of every pixel (top-left, top-right, bottom-right, bottom-left), as
    xbrz assembles them from the corner preprocessing of the neighbouring kernels."""
    blend_f, blend_g, blend_j, blend_k = _corner_blends(s)
    bottom_r = blend_f
    bottom_l = shift(blend_g[..., None], 0, -1, fill=0)[..., 0]
    top_r = shift(blend_j[..., None], -1, 0, fill=0)[..., 0]
    top_l = shift(blend_k[..., None], -1, -1, fill=0)[..., 0]
    return top_l, top_r, bottom_r, bottom_l


def _blend_weights(s, corners, k):
    """The weight of the blended colour in every pixel of every output block, and that colour, for
    the bottom-right corner of every pixel (xbrz blendPixel, ROT_0). `corners` is (top_r,
    bottom_r, bottom_l) in this frame."""
    top_r, bottom_r, bottom_l = corners
    e = s
    b = shift(s, -1, 0); c = shift(s, -1, 1); d = shift(s, 0, -1)
    f = shift(s, 0, 1);  g = shift(s, 1, -1); h = shift(s, 1, 0); i = shift(s, 1, 1)
    blend = bottom_r >= 1
    line = bottom_r >= 2
    keep_corner = ((top_r != 0) & ~_eq(e, g)) | ((bottom_l != 0) & ~_eq(e, c))
    l_shape = ~_eq(e, i) & _eq(g, h) & _eq(h, i) & _eq(i, f) & _eq(f, c)
    line = line | (~keep_corner & ~l_shape)
    fg = _dist(f, g)
    hc = _dist(h, c)
    shallow = (STEEP_DIRECTION_THRESHOLD * fg <= hc) & ~_same(e, g) & ~_same(d, g)
    steep = (STEEP_DIRECTION_THRESHOLD * hc <= fg) & ~_same(e, c) & ~_same(b, c)
    p_corner, p_diag, p_shallow, p_steep, p_both = _patterns(k)
    take_corner = blend & ~line
    take_both = blend & line & shallow & steep
    take_shallow = blend & line & shallow & ~steep
    take_steep = blend & line & steep & ~shallow
    take_diag = blend & line & ~shallow & ~steep
    w = (take_corner[..., None, None] * p_corner + take_diag[..., None, None] * p_diag
         + take_shallow[..., None, None] * p_shallow + take_steep[..., None, None] * p_steep
         + take_both[..., None, None] * p_both)
    px = np.where((_dist(e, f) <= _dist(e, h))[..., None], f, h)
    return w.astype(np.float32), px


def xbrz_scale(rgba, k):
    """Scales a batch of RGBA sprites by a whole factor (2..6) with xBRZ.
    @param rgba (B, h, w, 4) float, straight alpha (0 = transparent).
    @return (B, h*k, w*k, 4) float, straight alpha.
    """
    src = np.ascontiguousarray(rgba.astype(np.float32))
    b, h, w, _ = src.shape

    def premul(a):
        return np.concatenate([a[..., :3] * (a[..., 3:4] / 255.0), a[..., 3:4]], axis=-1)

    # blends happen in premultiplied colour, so a blend across the silhouette keeps its colour
    blocks = np.repeat(np.repeat(premul(src)[:, :, :, None, None, :], k, axis=3), k, axis=4)
    # the corner decisions are made once: they belong to the corner, not to the pixel that reads
    # them, and the rule is the same under rotation (xbrz rotates the flags, rotateBlendInfo)
    top_l, top_r, bottom_r, bottom_l = _pixel_corners(src)
    rotated = {0: (top_r, bottom_r, bottom_l),
               1: (bottom_r, bottom_l, top_l),
               2: (bottom_l, top_l, top_r),
               3: (top_l, top_r, bottom_r)}
    for rot in range(4):
        s = np.ascontiguousarray(np.rot90(src, rot, axes=(1, 2)))
        corners = tuple(np.ascontiguousarray(np.rot90(a, rot, axes=(1, 2))) for a in rotated[rot])
        weight, px = _blend_weights(s, corners, k)
        # back to the unrotated frame: the picture turns, and so does each block
        weight = np.rot90(np.rot90(weight, -rot, axes=(1, 2)), -rot, axes=(3, 4))[..., None]
        color = premul(np.rot90(px, -rot, axes=(1, 2)))[:, :, :, None, None, :]
        blocks *= (1.0 - weight)
        blocks += color * weight
    out = blocks.transpose(0, 1, 3, 2, 4, 5).reshape(b, h * k, w * k, 4)
    alpha = np.clip(out[..., 3:4], 0.0, 255.0)
    rgb = np.where(alpha > 0.5, out[..., :3] / np.maximum(alpha / 255.0, 1e-6), 0.0)
    return np.concatenate([np.clip(rgb, 0.0, 255.0), alpha], axis=3)


def fill_outside(rgb, mask, steps=2):
    """Gives every pixel outside `mask` the colour of the visible pixels near it, so a model shown
    the frame sees the sprite's own colours continue outward instead of a hard edge into nothing.

    Push-pull: the picture is averaged down to a single pixel (colour weighted by coverage) and
    pulled back up, each level filling what the level below it left empty. That is a handful of
    array operations whatever the size of the canvas - the flood fill it replaces cost one pass per
    pixel of distance, which on a padded frame was most of the work of the whole tool.

    @param rgb (B, H, W, 3) float, mask (B, H, W) bool, steps how many times the filled result is
    smoothed near the edge (0 = none).
    @return (B, H, W, 3) float
    """
    rgb = rgb.astype(np.float32)
    weight = mask.astype(np.float32)[..., None]
    pyramid = [(rgb * weight, weight)]
    while min(pyramid[-1][0].shape[1], pyramid[-1][0].shape[2]) > 1:
        c, w = pyramid[-1]
        # pad to even, then average 2x2 blocks
        py, px = c.shape[1] % 2, c.shape[2] % 2
        if py or px:
            c = np.pad(c, ((0, 0), (0, py), (0, px), (0, 0)))
            w = np.pad(w, ((0, 0), (0, py), (0, px), (0, 0)))
        b, h2, w2 = c.shape[0], c.shape[1] // 2, c.shape[2] // 2
        c = c.reshape(b, h2, 2, w2, 2, 3).sum(axis=(2, 4))
        w = w.reshape(b, h2, 2, w2, 2, 1).sum(axis=(2, 4))
        pyramid.append((c, w))
    out_c, out_w = pyramid[-1]
    for level in range(len(pyramid) - 2, -1, -1):
        c, w = pyramid[level]
        up_c = np.repeat(np.repeat(out_c, 2, axis=1), 2, axis=2)[:, :c.shape[1], :c.shape[2]]
        up_w = np.repeat(np.repeat(out_w, 2, axis=1), 2, axis=2)[:, :c.shape[1], :c.shape[2]]
        # what this level knows wins; the level above fills the rest
        have = w > 0
        out_c = np.where(have, c, up_c * 0.25)
        out_w = np.where(have, w, up_w * 0.25)
    filled = out_c / np.maximum(out_w, 1e-6)
    for _ in range(max(0, steps)):
        smooth = (filled + shift(filled, -1, 0) + shift(filled, 1, 0) + shift(filled, 0, -1) + shift(filled, 0, 1)) / 5.0
        filled = np.where(mask[..., None], filled, smooth)
    return np.where(mask[..., None], rgb, filled)


def blur(a, sigma):
    """A separable Gaussian blur of (B, H, W, C), edges repeated."""
    if sigma <= 0:
        return a
    radius = max(1, int(sigma * 3))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    kern = np.exp(-(x ** 2) / (2.0 * sigma * sigma))
    kern /= kern.sum()
    out = a
    for axis in (0, 1):
        acc = np.zeros_like(out)
        for offset, weight in zip(x.astype(int), kern):
            acc += (shift(out, offset, 0) if axis == 0 else shift(out, 0, offset)) * weight
        out = acc
    return out


def add_detail(base, model_rgb, strength, limit=0.35, scale=4, sigma=None):
    """The model's fine detail as a change of brightness on the scaled sprite.
    @param base (B, H, W, 4) the xBRZ picture (straight alpha), model_rgb (B, H, W, 3) the model's
    picture of the same frames, strength 0..1, limit the largest change as a fraction, sigma what
    counts as detail (default: half an original pixel).
    """
    if strength <= 0:
        return base
    if sigma is None:
        sigma = max(1.0, scale * 0.5)
    y = (0.299 * model_rgb[..., 0] + 0.587 * model_rgb[..., 1] + 0.114 * model_rgb[..., 2])[..., None]
    low = blur(y, sigma)
    factor = 1.0 + strength * (y - low) / np.maximum(low, 24.0)
    factor = np.clip(factor, 1.0 - limit, 1.0 + limit)
    rgb = np.clip(base[..., :3] * factor, 0.0, 255.0)
    return np.concatenate([rgb, base[..., 3:4]], axis=3)
