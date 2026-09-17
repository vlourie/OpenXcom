#!/usr/bin/env python3
"""
X-COM sprite files for the HD art pipeline: palettes, PCK/TAB sprite sets and
PNG sheets. Pure Python + Pillow, no game engine needed.

  Palette      - PALETTES.DAT (6-bit RGB, 5 palettes of 768 bytes at 774-byte
                 strides); the battlescape palette is number 4 with the last
                 16 entries replaced by OpenXcom's grey gradient.
  read_pck     - a PCK/TAB set as a list of 8-bit index arrays (frames may be
                 missing: None). Frame width comes from the caller (32 for
                 everything battlescape but X1.PCK (128x64) and BIGOBS (32x48));
                 the height is whatever the RLE stream fills.
  Sheet        - frames laid out on a grid with a transparent margin around
                 each, saved as an indexed PNG (palette + alpha 0 for index 0)
                 or as RGBA, and cut back into frames from a same-size image.

Format notes (ufopaedia.org, Image_Formats): each PCK frame starts with a byte
= number of empty rows; then bytes are pixel indices, 0xFE n = n transparent
pixels, 0xFF = end of frame. TAB holds 16-bit little-endian frame offsets
(UFO) or 32-bit (TFTD).
"""
import os
import struct

from PIL import Image

PAL_STRIDE = 774
PAL_BATTLESCAPE = 4

# OpenXcom: the last 16 colors of the battlescape palette are a greyish gradient
BATTLESCAPE_TAIL = [
    (140, 152, 148), (132, 136, 140), (116, 124, 132), (108, 116, 124),
    (92, 104, 108), (84, 92, 100), (76, 80, 92), (56, 68, 84),
    (48, 56, 68), (40, 48, 56), (32, 36, 48), (24, 28, 32),
    (16, 20, 24), (8, 12, 16), (3, 4, 8), (3, 3, 6)]


def load_palette(palettes_dat, index=PAL_BATTLESCAPE, battlescape_fix=True):
    """Returns 256 (r, g, b) tuples."""
    with open(palettes_dat, "rb") as f:
        f.seek(PAL_STRIDE * index)
        raw = f.read(768)
    pal = [(raw[i * 3] * 4, raw[i * 3 + 1] * 4, raw[i * 3 + 2] * 4) for i in range(256)]
    if battlescape_fix and index == PAL_BATTLESCAPE:
        for i, c in enumerate(BATTLESCAPE_TAIL):
            pal[224 + 16 + i] = c
    return pal


def read_tab(path):
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 4 or data[2:4] != b"\x00\x00":
        # 16-bit offsets: the second entry's high word is not zero for UFO files this small
        return list(struct.unpack("<%dH" % (len(data) // 2), data[: len(data) // 2 * 2]))
    # 32-bit offsets (TFTD)
    return list(struct.unpack("<%dI" % (len(data) // 4), data[: len(data) // 4 * 4]))


def read_pck(pck_path, tab_path=None, width=32, height=40):
    """Decodes every frame; returns a list of lists of rows (each row = list of
    palette indices, `width` long, `height` rows)."""
    with open(pck_path, "rb") as f:
        data = f.read()
    if tab_path is None:
        tab_path = os.path.splitext(pck_path)[0] + ".TAB"
    offsets = read_tab(tab_path) if os.path.exists(tab_path) else [0]
    frames = []
    for off in offsets:
        pos = off
        if pos >= len(data):
            frames.append(None)
            continue
        pixels = [0] * (width * height)
        i = data[pos] * width  # empty rows
        pos += 1
        while pos < len(data):
            v = data[pos]
            pos += 1
            if v == 0xFF:
                break
            if v == 0xFE:
                i += data[pos]
                pos += 1
                continue
            if i < len(pixels):
                pixels[i] = v
            i += 1
        frames.append([pixels[y * width:(y + 1) * width] for y in range(height)])
    return frames


def frame_to_image(frame, palette, mode="RGBA"):
    """An indexed frame as a Pillow image: 'P' keeps the indices (palette + index 0 transparent), 'RGBA' converts."""
    h = len(frame)
    w = len(frame[0]) if h else 0
    if mode == "P":
        im = Image.new("P", (w, h))
        flat = []
        for row in frame:
            flat.extend(row)
        im.putdata(flat)
        im.putpalette([c for rgb in palette for c in rgb])
        im.info["transparency"] = 0
        return im
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = im.load()
    for y, row in enumerate(frame):
        for x, idx in enumerate(row):
            if idx:
                r, g, b = palette[idx]
                px[x, y] = (r, g, b, 255)
    return im


class Sheet:
    """A grid of frames with a margin around each (so that painting one frame
    never bleeds into its neighbour), the same layout for the original and the
    HD version. Cell = (w + 2 m) x (h + 2 m) at scale 1; multiply by k for HD."""

    def __init__(self, frame_w, frame_h, count, columns=8, margin=4):
        self.frame_w, self.frame_h, self.count = frame_w, frame_h, count
        self.columns = max(1, columns)
        self.margin = margin
        self.rows = (count + self.columns - 1) // self.columns

    def cell(self, index, scale=1):
        cw = (self.frame_w + 2 * self.margin) * scale
        ch = (self.frame_h + 2 * self.margin) * scale
        x = (index % self.columns) * cw + self.margin * scale
        y = (index // self.columns) * ch + self.margin * scale
        return x, y, self.frame_w * scale, self.frame_h * scale

    def size(self, scale=1):
        return ((self.frame_w + 2 * self.margin) * self.columns * scale,
                (self.frame_h + 2 * self.margin) * self.rows * scale)

    def compose(self, frames, palette, scale=1, mode="RGBA"):
        """Frames (index arrays or None) onto one image, nearest-scaled by `scale`."""
        w, h = self.size(scale)
        if mode == "P":
            sheet = Image.new("P", (w, h), 0)
            sheet.putpalette([c for rgb in palette for c in rgb])
            sheet.info["transparency"] = 0
        else:
            sheet = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for i, frame in enumerate(frames):
            if frame is None or i >= self.count:
                continue
            im = frame_to_image(frame, palette, mode)
            if scale != 1:
                im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
            x, y, _, _ = self.cell(i, scale)
            sheet.paste(im, (x, y))
        return sheet

    def cut(self, image, index, scale=1):
        x, y, w, h = self.cell(index, scale)
        return image.crop((x, y, x + w, y + h))

    def describe(self):
        return {"frame_w": self.frame_w, "frame_h": self.frame_h, "count": self.count,
                "columns": self.columns, "margin": self.margin, "rows": self.rows}


MCD_RECORD = 62
MCD_FLOOR, MCD_WEST_WALL, MCD_NORTH_WALL, MCD_OBJECT = 0, 1, 2, 3


def read_mcd(path):
    """The terrain's MCD records as dicts: bytes 0-7 the sprite frames (animation), byte 39 the
    walking cost (255 = impassable), byte 53 the tile type (0 floor, 1 west wall, 2 north wall, 3 object)."""
    with open(path, "rb") as f:
        data = f.read()
    return [{"frames": list(data[i:i + 8]), "tu_walk": data[i + 39], "type": data[i + 53],
             "t_level": struct.unpack("b", data[i + 48:i + 49])[0]}
            for i in range(0, len(data) - MCD_RECORD + 1, MCD_RECORD)]


def frame_types(records, count):
    """Per sprite frame: (tile type, walkable, raised) - type -1 when no record uses the frame; a frame
    used by several records gets the lowest type (floor wins)."""
    types = [-1] * count
    walkable = [True] * count
    raised = [False] * count  # terrain level != 0: slopes, stairs, things one climbs onto
    for rec in records:
        for fr in rec["frames"]:
            if fr < count and (types[fr] < 0 or rec["type"] < types[fr]):
                types[fr] = rec["type"]
                walkable[fr] = rec["tu_walk"] != 255
                raised[fr] = rec["t_level"] != 0
    return types, walkable, raised


def diamond_coverage(frame, width=32, height=40):
    """How much of the floor diamond (the bottom 32x16 of a 32x40 tile) the frame's pixels cover."""
    inside = drawn = 0
    for y in range(height - 16, height):
        for x in range(width):
            if abs(x - (width - 1) / 2) / (width / 2) + abs(y - (height - 8.5)) / 8 <= 1:
                inside += 1
                if frame[y][x]:
                    drawn += 1
    return drawn / inside if inside else 0.0


# frame sizes of the battlescape sets that are not 32x40
FRAME_SIZES = {
    "X1.PCK": (128, 64),
    "BIGOBS.PCK": (32, 48),
}


def frame_size_for(set_name):
    return FRAME_SIZES.get(set_name.upper(), (32, 40))


def diamond_distance(width=32, height=40):
    """Per pixel of a frame: the "diamond distance" of the floor diamond (0 at its centre, 1 on its
    outline, larger outside) as a float array; rows above the floor zone get a large value."""
    import numpy as np
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    d = np.abs(xs - (width - 1) / 2.0) / (width / 2.0) + np.abs(ys - (height - 8.5)) / 8.0
    d[ys < height - 16] = 99.0
    return d


def rim_zone(width=32, height=40, inner=0.7):
    """The part of a frame whose silhouette must stay pixel-exact: the floor zone (bottom 16 rows)
    except the diamond's interior, so that floors, walls and an object's ground diamond meet their
    neighbours exactly as in the classic art (a soft edge there shows the background through as a seam).
    Returns an "L" image, 255 = exact."""
    from PIL import Image
    import numpy as np
    d = diamond_distance(width, height)
    zone = (d >= inner) & (d < 99.0)
    return Image.fromarray(np.where(zone, 255, 0).astype(np.uint8), "L")


def floor_match(frame, floors, tolerance=0, min_pixels=16):
    """Which floor the object stands on. X-COM objects that sit on a ground diamond carry that
    floor's own pixels in the sprite, so the floor whose pixels the frame repeats the most (inside the
    floor zone) is the one under it. `floors` is a list of (index, RGBA frame). Returns
    (index, matches) or (None, 0)."""
    import numpy as np
    a = np.asarray(frame.convert("RGBA")).astype(np.int32)
    h = a.shape[0]
    best, best_n = None, 0
    for i, floor in floors:
        b = np.asarray(floor.convert("RGBA")).astype(np.int32)
        if b.shape != a.shape:
            continue
        both = (a[:, :, 3] > 0) & (b[:, :, 3] > 0)
        both[:h - 16] = False
        eq = both & (np.abs(a[:, :, :3] - b[:, :, :3]).max(axis=2) <= tolerance)
        n = int(eq.sum())
        if n > best_n:
            best, best_n = i, n
    if best_n < min_pixels:
        return None, 0
    return best, best_n


def floor_pixels(frame, floor, tolerance=8):
    """Boolean array: the frame's pixels (in the floor zone) that are the floor's pixels."""
    import numpy as np
    a = np.asarray(frame.convert("RGBA")).astype(np.int32)
    b = np.asarray(floor.convert("RGBA")).astype(np.int32)
    both = (a[:, :, 3] > 0) & (b[:, :, 3] > 0)
    both[:a.shape[0] - 16] = False
    return both & (np.abs(a[:, :, :3] - b[:, :, :3]).max(axis=2) <= tolerance)
