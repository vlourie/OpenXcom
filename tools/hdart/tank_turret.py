#!/usr/bin/env python3
"""A 2x2 tank whose turret is drawn into the hull (drawingRoutine 5: the turret turns with the hull) made
into a drawingRoutine 2 tank whose turret turns on its own. Everything is cut out of OUR sprite, no pixel
is invented except the deck under the removed gun barrel, and that is copied from the hull's own deck.

The turret is given by masks (tank_masks.json: polygons drawn by hand for the X-Piratez pirate tank;
image models could not separate it on this pixel art):
  dome    the turret body. It turns; the hull keeps its own dome under it as the turret base, so no
          big hole has to be painted (a turned dome covers most of it, the rest reads as the base).
  barrel  the gun. It turns and is taken off the hull: where it lay on the deck the deck is filled with
          the best matching pieces of the hull's own deck, where it stuck out over the background it goes.
The masks are written as editable pictures (<work>/<sheet>/mask_d<N>.png: our tank, dome painted pure
red, barrel pure blue) and read back from them, so a mask can be fixed in any paint program.

The turret stands on the rear of the hull, so its place moves with the hull: the turret frames are
8 hull directions x 8 turret directions (the turret of direction t moved from its own mount to the mount
of hull h; the mount is fitted from the 8 dome masks), 96x96 each, and a selectUnitSprite script in the
armor picks base + hull*8 + turret. The routine-5 walking frames get the new hulls too and the script
keeps the track animation.

Stages (--stage, default all):
  masks   mask pictures from the polygons (hand-edited pictures are kept) + <work>/<sheet>/review.png
  build   hulls (standing and walking), mount (<work>/<sheet>/mount.json), turret frames, sheet, mod,
          previews

The turret frames are bigger than a unit cell: they need the engine change in UnitSprite::drawRoutine2
(a big turret frame is centred on the tank and drawn with every part).

    tools\\hdart\\.venv\\Scripts\\python.exe tools\\hdart\\tank_turret.py

Output mod: <out-mod> (default Пиратки\\Dioxine_XPiratez\\user\\mods\\piratez_tank_turret): the sheets
with new hulls, the turret frames, a ruleset switching the armors to drawingRoutine 2 with the script
and giving their guns turretType 0; previews in <work>.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CELL_W, CELL_H = 32, 40
CANVAS_W, CANVAS_H = 64, 80
# where each part's 32x40 frame lies on the tank canvas (parts: 0 top, 1 right, 2 left, 3 bottom tile)
PART_POS = {0: (16, 8), 1: (32, 16), 2: (0, 16), 3: (16, 24)}
# the big turret frame: the part of the screen a standing 2x2 unit may draw on (the canvas lies at (16, 8));
# the engine centres it on the tank
BIG_W, BIG_H, BIG_X, BIG_Y = 96, 96, 16, 8
DOME_RGB = (255, 0, 0)
BARREL_RGB = (0, 0, 255)

HERE = os.path.dirname(os.path.abspath(__file__))
PIRATEZ = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez")

# world directions of the 8 unit directions (0 = north ... 7 = north-west) and their screen projection
DIR_VEC = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


def screen_dir(d):
    """Screen offset (px) of one tile length along unit direction d."""
    dx, dy = DIR_VEC[d % 8]
    n = (dx * dx + dy * dy) ** 0.5
    dx, dy = dx / n, dy / n
    return np.array([16.0 * (dx - dy), 8.0 * (dx + dy)])


# ---------------------------------------------------------------- sheets and the tank canvas

class Sheet:
    """An indexed sprite sheet of 32x40 cells."""

    def __init__(self, path, cols=None):
        im = Image.open(path)
        if im.mode != "P":
            raise SystemExit("%s is not an indexed (palette) image" % path)
        self.path = path
        self.image = im
        self.a = np.array(im, dtype=np.uint8)
        pal = (im.getpalette() or []) + [0] * 768
        self.palette = np.array(pal[:768], dtype=np.uint8).reshape(256, 3)
        self.cols = cols or im.width // CELL_W
        self.rows = im.height // CELL_H

    def frame(self, i):
        r, c = divmod(i, self.cols)
        return self.a[r * CELL_H:(r + 1) * CELL_H, c * CELL_W:(c + 1) * CELL_W]

    def set_frame(self, i, f):
        r, c = divmod(i, self.cols)
        self.a[r * CELL_H:(r + 1) * CELL_H, c * CELL_W:(c + 1) * CELL_W] = f

    def save(self, path):
        save_indexed(self.a, self.palette, path)


def save_indexed(a, palette, path):
    im = Image.fromarray(a.astype(np.uint8), "P")
    im.putpalette(palette.reshape(-1).tolist())
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    im.save(path, transparency=0, optimize=False)


def compose(sheet, index_of_part):
    """The tank on the 64x80 canvas from four part frames: (indices, owner part -1..3, per-part coverage)."""
    cv = np.zeros((CANVAS_H, CANVAS_W), np.uint8)
    owner = np.full((CANVAS_H, CANVAS_W), -1, np.int8)
    cover = np.zeros((4, CANVAS_H, CANVAS_W), bool)
    for p in range(4):
        x, y = PART_POS[p]
        f = sheet.frame(index_of_part(p))
        m = f != 0
        cv[y:y + CELL_H, x:x + CELL_W][m] = f[m]
        owner[y:y + CELL_H, x:x + CELL_W][m] = p
        cover[p, y:y + CELL_H, x:x + CELL_W] = m
    return cv, owner, cover


def assemble(sheet, d):
    """The standing tank of direction d (frames part*8 + d)."""
    return compose(sheet, lambda p: p * 8 + d)


def walk_index(d, p, k):
    return 32 + d * 16 + p * 4 + k


def walk_canvas(sheet, d, k):
    """The walking tank (drawingRoutine 5: frame 32 + dir*16 + part*4 + phase) of direction d, phase k."""
    return compose(sheet, lambda p: walk_index(d, p, k))


def has_walk(sheet):
    """drawingRoutine 5 walking frames (32..159) present?"""
    if sheet.rows * sheet.cols < 160:
        return False
    return all((sheet.frame(i) != 0).any() for i in range(32, 160))


def split(orig_frames, hull, owner, changed):
    """The new hull canvas back into the four 32x40 part frames. Outside `changed` the frames stay byte
    for byte. Inside it every part is cleared and each hull pixel goes to one part: the one that owns the
    nearest unchanged hull pixel and whose cell holds it."""
    frames = [f.copy() for f in orig_frames]
    keep_owner = np.where(changed, -1, owner)
    ys, xs = np.nonzero(keep_owner >= 0)
    new_owner = np.full(hull.shape, -1, np.int8)
    for y, x in zip(*np.nonzero(changed & (hull != 0))):
        done = False
        if len(ys):
            dist = (ys - y) ** 2 + (xs - x) ** 2
            for i in np.argsort(dist, kind="stable")[:64]:
                p = int(keep_owner[ys[i], xs[i]])
                px, py = PART_POS[p]
                if px <= x < px + CELL_W and py <= y < py + CELL_H:
                    new_owner[y, x] = p
                    done = True
                    break
        if not done:
            for p in (3, 1, 2, 0):
                px, py = PART_POS[p]
                if px <= x < px + CELL_W and py <= y < py + CELL_H:
                    new_owner[y, x] = p
                    break
    for p in range(4):
        px, py = PART_POS[p]
        region = (slice(py, py + CELL_H), slice(px, px + CELL_W))
        frames[p][changed[region]] = 0
        add = new_owner[region] == p
        frames[p][add] = hull[region][add]
    return frames


def to_big(a):
    out = np.zeros((BIG_H, BIG_W), a.dtype)
    out[BIG_Y:BIG_Y + CANVAS_H, BIG_X:BIG_X + CANVAS_W] = a[:BIG_H - BIG_Y, :]
    return out


def shift(a, dx, dy):
    out = np.zeros_like(a)
    h, w = a.shape
    ys, ye = max(0, dy), min(h, h + dy)
    xs, xe = max(0, dx), min(w, w + dx)
    out[ys:ye, xs:xe] = a[ys - dy:ye - dy, xs - dx:xe - dx]
    return out


# ---------------------------------------------------------------- masks

def dilate(m, r=1):
    out = m.copy()
    h, w = m.shape
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy or dx:
                out |= shift(m, dx, dy)
    return out


def poly_mask(poly, w=CANVAS_W, h=CANVAS_H, ss=4):
    """Pixels covered (>= 38 %) by a polygon of pixel centres."""
    im = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(im).polygon([((x + 0.5) * ss, (y + 0.5) * ss) for x, y in poly], fill=255, outline=255)
    return np.asarray(im.resize((w, h), Image.BOX)) >= 96


class MaskBook:
    """tank_masks.json: dome and barrel polygons per sheet and direction."""

    def __init__(self, path):
        self.path = path
        self.data = json.load(open(path, encoding="utf-8"))

    def has(self, name):
        return name in self.data

    def entry(self, name):
        e = self.data[name]
        return self.data[e["same_as"]] if "same_as" in e else e

    def sibling(self, name):
        e = self.data[name]
        return e["same_as"] if e.get("barrel_grows_by_difference") else None

    def masks(self, name, d, opaque):
        e = self.entry(name)
        mirror = {int(k): int(v) for k, v in e.get("mirror", {}).items()}
        if d in mirror:
            dm, bm = self.masks(name, mirror[d], opaque[:, ::-1])
            return dm[:, ::-1], bm[:, ::-1]
        if str(d) not in e["dome"]:
            raise SystemExit("%s: no dome polygon for direction %d in %s" % (name, d, self.path))
        bm = poly_mask(e["barrel"][str(d)]) & opaque if str(d) in e.get("barrel", {}) else np.zeros_like(opaque)
        dm = poly_mask(e["dome"][str(d)]) & opaque & ~bm
        return dm, bm


def md5_file(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def write_mask_png(path, canvas, palette, dome, barrel):
    rgb = palette[canvas].copy()
    rgb[canvas == 0] = (0, 0, 0)
    rgb[dome] = DOME_RGB
    rgb[barrel] = BARREL_RGB
    Image.fromarray(rgb).save(path)
    with open(path[:-4] + ".key", "w") as f:
        f.write(md5_file(path) + "\n")


def mask_edited(path):
    key = path[:-4] + ".key"
    return (os.path.exists(path) and os.path.exists(key)
            and open(key).read().strip() != md5_file(path))


def read_mask_png(path, opaque):
    rgb = np.asarray(Image.open(path).convert("RGB"))
    if rgb.shape[:2] != (CANVAS_H, CANVAS_W):
        raise SystemExit("%s: must be %dx%d" % (path, CANVAS_W, CANVAS_H))
    dome = np.all(rgb == DOME_RGB, axis=2) & opaque
    barrel = np.all(rgb == BARREL_RGB, axis=2) & opaque & ~dome
    return dome, barrel


# ---------------------------------------------------------------- the hull under the barrel

def convex_fill(m):
    """The filled convex hull of a mask."""
    ys, xs = np.nonzero(m)
    pts = sorted(set(zip(xs.tolist(), ys.tolist())))
    if len(pts) < 3:
        return m.copy()

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    im = Image.new("L", (m.shape[1], m.shape[0]), 0)
    ImageDraw.Draw(im).polygon(lo[:-1] + hi[:-1], fill=255, outline=255)
    return np.asarray(im) > 0


def exemplar_fill(cv, target, known, palette, avoid, r=2, near=0.02):
    """Fill the target pixels with palette indices copied from known pixels whose neighbourhood matches
    best (outside in, nearby pieces preferred): the deck keeps its own pixel texture and lines."""
    h, w = cv.shape
    rgb = palette[cv].astype(np.float32)
    out = cv.copy()
    known = known.copy()
    todo = target.copy()
    offs = [(dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1) if dy or dx]
    ys, xs = np.nonzero(known & ~avoid)
    ok = (ys >= r) & (ys < h - r) & (xs >= r) & (xs < w - r)
    ys, xs = ys[ok], xs[ok]
    if not len(ys):
        return out
    src_rgb = np.stack([rgb[ys + dy, xs + dx] for dy, dx in offs], 1)
    src_known = np.stack([known[ys + dy, xs + dx] for dy, dx in offs], 1)
    while todo.any():
        cnt = sum(shift(known, dx, dy).astype(int) for dy, dx in offs)
        cnt = np.where(todo, cnt, -1)
        for py, px in zip(*np.nonzero(cnt == cnt.max())):
            kk, vals = [], []
            for i, (dy, dx) in enumerate(offs):
                y, x = py + dy, px + dx
                if 0 <= y < h and 0 <= x < w and known[y, x]:
                    kk.append(i)
                    vals.append(rgb[y, x])
            if kk:
                diff = ((src_rgb[:, kk, :] - np.array(vals)[None]) ** 2).sum(2)
                diff = np.where(src_known[:, kk], diff, 3 * 255.0 ** 2).sum(1) / len(kk)
                j = int(np.argmin(diff + near * 255 * ((ys - py) ** 2 + (xs - px) ** 2)))
            else:
                j = int(np.argmin((ys - py) ** 2 + (xs - px) ** 2))
            out[py, px] = cv[ys[j], xs[j]]
            rgb[py, px] = rgb[ys[j], xs[j]]
            known[py, px] = True
            todo[py, px] = False
    return out


def make_hull(cv, palette, dome, barrel):
    """The hull of one direction: the barrel taken off (deck filled where it lay on the hull, transparent
    where it stuck out), the dome kept as the turret base. -> (hull, filled, removed)"""
    opaque = cv != 0
    rest = opaque & ~dome & ~barrel
    inside = convex_fill(rest)
    fill = barrel & inside
    gone = barrel & ~inside
    hull = cv.copy()
    hull[gone] = 0
    hull = exemplar_fill(hull, fill, opaque & ~barrel, palette, avoid=dome | ~opaque)
    return hull, fill, gone


# ---------------------------------------------------------------- the mount

def fit_mount(points, lateral=True):
    """points {dir: (x, y)} of something fixed on the tank -> centre C, forward offset u, lateral offset v
    (tiles) with point(d) = C + u*screen_dir(d) + v*screen_dir(d+2), and the residuals."""
    A, B = [], []
    for d, (x, y) in points.items():
        f, r = screen_dir(d), screen_dir(d + 2)
        A.append([1, 0, f[0]] + ([r[0]] if lateral else []))
        B.append(x)
        A.append([0, 1, f[1]] + ([r[1]] if lateral else []))
        B.append(y)
    sol = np.linalg.lstsq(np.array(A), np.array(B), rcond=None)[0]
    cx, cy, u = sol[:3]
    v = sol[3] if lateral else 0.0
    res = {}
    for d, (x, y) in points.items():
        m = np.array([cx, cy]) + u * screen_dir(d) + v * screen_dir(d + 2)
        res[d] = float(np.hypot(x - m[0], y - m[1]))
    return (float(cx), float(cy), float(u), float(v)), res


def robust_fit(points, max_off=3.0, min_keep=5):
    """fit_mount without the worst points while they are more than max_off px off -> (model, off, kept)"""
    keep = dict(points)
    while True:
        model, res = fit_mount(keep, lateral=True)
        worst = max(res, key=res.get)
        if res[worst] <= max_off or len(keep) <= min_keep:
            break
        del keep[worst]
    cx, cy, u, v = model
    off = {d: float(np.hypot(*(np.array(p) - (np.array([cx, cy]) + u * screen_dir(d) + v * screen_dir(d + 2)))))
           for d, p in points.items()}
    return model, off, sorted(keep)


def load_mount(path):
    try:
        m = json.load(open(path, encoding="utf-8"))
        return m if m.get("manual") else None
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- previews

def show(canvas, palette, z=4, bg=(84, 104, 84)):
    rgb = palette[canvas].copy()
    rgb[canvas == 0] = bg
    return Image.fromarray(rgb).resize((canvas.shape[1] * z, canvas.shape[0] * z), Image.NEAREST)


def show_big(hull_canvas, big, palette, z):
    """A hull canvas with a 96x96 turret frame on top, as the engine puts them, cut to what is drawn."""
    cv = to_big(hull_canvas)
    m = big != 0
    cv[m] = big[m]
    cv[BIG_Y + 64:, :] = 0  # below the last tile nothing is drawn
    return show(cv[:BIG_Y + 64 + 4], palette, z)


def overlay(canvas, palette, dome, barrel, z=4):
    rgb = palette[canvas].astype(np.float32)
    rgb[canvas == 0] = (84, 104, 84)
    rgb[dome] = rgb[dome] * 0.4 + np.array(DOME_RGB) * 0.6
    rgb[barrel] = rgb[barrel] * 0.4 + np.array((40, 140, 255)) * 0.6
    return Image.fromarray(rgb.astype(np.uint8)).resize((CANVAS_W * z, CANVAS_H * z), Image.NEAREST)


def font(size=14):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def grid(images, cols, labels=None, pad=4, bg=(30, 30, 30)):
    w = max(i.width for i in images)
    h = max(i.height for i in images)
    lh = 18 if labels else 0
    rows = (len(images) + cols - 1) // cols
    out = Image.new("RGB", (cols * (w + pad) + pad, rows * (h + lh + pad) + pad), bg)
    d = ImageDraw.Draw(out)
    f = font()
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        x, y = pad + c * (w + pad), pad + r * (h + lh + pad)
        if labels:
            d.text((x + 2, y + 1), labels[i], fill=(235, 235, 235), font=f)
        out.paste(im, (x, y + lh))
    return out


def mark(img, xy, z, color, r=2):
    if xy is None:
        return
    d = ImageDraw.Draw(img)
    x, y = (xy[0] + 0.5) * z, (xy[1] + 0.5) * z
    d.line((x - r * z, y, x + r * z, y), fill=color, width=max(1, z // 2))
    d.line((x, y - r * z, x, y + r * z), fill=color, width=max(1, z // 2))


# ---------------------------------------------------------------- rulesets

def find_armors(ruleset_paths, sheet_type):
    """Armors drawn from a sheet: [(type, drawingRoutine, [builtInWeapons])] by a plain line scan."""
    found = []
    for path in ruleset_paths:
        if not os.path.exists(path):
            continue
        lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
        section = None
        cur = None
        for line in lines:
            m = re.match(r"^([A-Za-z]\w*):\s*$", line)
            if m:
                section = m.group(1)
                cur = None
                continue
            if section != "armors":
                continue
            m = re.match(r"^  - type:\s*(\S+)", line)
            if m:
                cur = dict(type=m.group(1), sheet=None, routine=None, weapons=[], inweap=False)
                found.append(cur)
                continue
            if cur is None:
                continue
            m = re.match(r"^    spriteSheet:\s*(\S+)", line)
            if m:
                cur["sheet"] = m.group(1)
            m = re.match(r"^    drawingRoutine:\s*(\d+)", line)
            if m:
                cur["routine"] = int(m.group(1))
            if re.match(r"^    builtInWeapons:\s*$", line):
                cur["inweap"] = True
                continue
            if cur["inweap"]:
                m = re.match(r"^      - (\S+)", line)
                if m:
                    cur["weapons"].append(m.group(1))
                else:
                    cur["inweap"] = False
    return [(a["type"], a["routine"], a["weapons"]) for a in found if a["sheet"] == sheet_type]


def make_script(rear, walk, base):
    """selectUnitSprite for drawingRoutine 2: the turret frame from base + [hull dir * 8] + turret dir,
    the hull from the routine-5 walking frames while walking. None = the engine's default is enough."""
    if not rear and not walk:
        return None
    L = ["var int hull_dir;"]
    if walk:
        L += ["var int part;", "var int phase;", "var int walking;"]
    L += ["unit.getDirection hull_dir;",
          "if eq blit_part blit_large_turret;",
          "  set sprite_index sprite_offset;"]
    if rear:
        L += ["  mul hull_dir 8;", "  add sprite_index hull_dir;"]
    L += ["  add sprite_index %d;" % base, "  return sprite_index;", "end;"]
    if walk:
        L += ["unit.isWalking walking;",
              "if eq walking 1;",
              "  set part blit_part;",
              "  sub part blit_large_torso_0;",
              "  unit.getWalkingPhase phase;",
              "  div phase 2;",
              "  mod phase 4;",
              "  mul hull_dir 16;",
              "  mul part 4;",
              "  set sprite_index 32;",
              "  add sprite_index hull_dir;",
              "  add sprite_index part;",
              "  add sprite_index phase;",
              "  return sprite_index;",
              "end;"]
    L += ["add sprite_index sprite_offset;", "return sprite_index;"]
    return "\n".join(L) + "\n"


def write_mod(out_mod, master, sheets_info):
    os.makedirs(os.path.join(out_mod, "Ruleset"), exist_ok=True)
    with open(os.path.join(out_mod, "metadata.yml"), "w", encoding="utf-8") as f:
        f.write('name: "Piratez tanks: turning turret"\n')
        f.write('version: "1.2"\n')
        f.write('description: "The pirate tanks (PIR_TANK*) drawn as real tanks (drawingRoutine 2) with a turret that turns on its own, '
                'mounted where it is drawn (at the rear). Needs the OXCE HD build with big turret frames (UnitSprite::drawRoutine2)."\n')
        f.write('author: "Vitali + Claude"\n')
        f.write("id: piratez_tank_turret\n")
        f.write("master: %s\n" % master)
    lines = ["extraSprites:"]
    for s in sheets_info:
        lines += [
            "  - type: %s" % s["type"],
            "    subX: %d" % CELL_W,
            "    subY: %d" % CELL_H,
            "    width: %d" % s["width"],
            "    height: %d" % s["height"],
            "    files:",
            "      0: %s" % s["sheet_file"],
            "      %d: %s" % (s["turret_base"], s["turret_dir"]),
        ]
    lines.append("armors:")
    for s in sheets_info:
        for a in s["armors"]:
            lines += ["  - type: %s" % a, "    drawingRoutine: 2"]
            if s["script"]:
                lines += ["    scripts:", "      selectUnitSprite: |"]
                lines += ["        " + l for l in s["script"].rstrip("\n").split("\n")]
    lines.append("items:")
    done = set()
    for s in sheets_info:
        for w in s["weapons"]:
            if w not in done:
                done.add(w)
                lines += ["  - type: %s" % w, "    turretType: %d" % s["turret_type"]]
    with open(os.path.join(out_mod, "Ruleset", "tank_turret.rul"), "w", encoding="utf-8") as f:
        f.write("# made by tools/hdart/tank_turret.py\n" + "\n".join(lines) + "\n")


# ---------------------------------------------------------------- main

def sheet_masks(args, book, name, sheet, work, tanks):
    """The mask pictures of one sheet (written from the polygons unless edited by hand) -> {d: (dome, barrel)}"""
    sib = None
    if book.sibling(name):
        sib = Sheet(os.path.join(args.mod_dir, args.sprites, book.sibling(name) + ".png"), 8)
    out = {}
    for d in range(8):
        cv = tanks[d][0]
        opaque = cv != 0
        path = os.path.join(work, "mask_d%d.png" % d)
        if os.path.exists(path) and mask_edited(path) and not args.remask:
            out[d] = read_mask_png(path, opaque)
            print("  d%d: mask edited by hand, kept (%s)" % (d, path))
            continue
        dome, barrel = book.masks(name, d, opaque)
        if sib is not None:
            diff = cv != assemble(sib, d)[0]
            barrel = barrel | (diff & dilate(barrel, 2) & opaque & ~dome)
        write_mask_png(path, cv, sheet.palette, dome, barrel)
        out[d] = (dome, barrel)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mod-dir", default=PIRATEZ, help="the mod with the sheets and rulesets (X-Piratez)")
    ap.add_argument("--sheets", default="PIR_TANK,PIR_TANK_L", help="sheet names (Resources/Sprites/<name>.png, set <name>.PCK)")
    ap.add_argument("--sprites", default="Resources/Sprites", help="where the sheets are, inside --mod-dir")
    ap.add_argument("--masks", default=os.path.join(HERE, "tank_masks.json"), help="dome/barrel polygons")
    ap.add_argument("--work", default="tank_work", help="work folder (mask pictures, previews)")
    ap.add_argument("--out-mod", default=os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "piratez_tank_turret"))
    ap.add_argument("--master", default="piratez")
    ap.add_argument("--stage", default="all", choices=["all", "masks", "build"])
    ap.add_argument("--remask", action="store_true", help="overwrite hand-edited mask pictures with the polygons")
    ap.add_argument("--mount", default="model", choices=["model", "measured", "center"],
                    help="where the turret stands on each hull: model = fitted rear mount (64 frames + script), "
                         "measured = where the dome is drawn on that hull, center = one place (8 frames)")
    ap.add_argument("--walk", default="auto", choices=["auto", "on", "off"], help="keep the track animation (routine-5 walking frames, script)")
    ap.add_argument("--turret-type", type=int, default=0, help="turretType given to the guns")
    args = ap.parse_args()
    stages = ["masks", "build"] if args.stage == "all" else [args.stage]
    book = MaskBook(args.masks)
    rulesets = [os.path.join(args.mod_dir, "Ruleset", n) for n in ("Piratez.rul", "Piratez_Armors.rul")]
    sheets_info = []
    t_start = time.time()

    for name in [s.strip() for s in args.sheets.split(",") if s.strip()]:
        if not book.has(name):
            raise SystemExit("%s: no masks for %s" % (args.masks, name))
        sheet_path = os.path.join(args.mod_dir, args.sprites, name + ".png")
        sheet = Sheet(sheet_path, 8)
        work = os.path.join(args.work, name)
        os.makedirs(work, exist_ok=True)
        tanks = {d: assemble(sheet, d) for d in range(8)}
        print("== %s: %dx%d sheet" % (name, sheet.image.width, sheet.image.height))
        masks = sheet_masks(args, book, name, sheet, work, tanks)
        if "masks" in stages:
            tiles, labels = [], []
            for d in range(8):
                cv = tanks[d][0]
                tiles += [show(cv, sheet.palette, 4), overlay(cv, sheet.palette, *masks[d])]
                labels += ["d%d" % d, "mask_d%d" % d]
            grid(tiles, 4, labels).save(os.path.join(work, "review.png"))
            print("  masks: %s (red = dome, blue = barrel), review.png" % os.path.join(work, "mask_d0..7.png"))
        if "build" not in stages:
            continue

        walk = has_walk(sheet) if args.walk == "auto" else args.walk == "on"
        if walk and not has_walk(sheet):
            raise SystemExit("--walk on: %s has no walking frames 32..159" % name)
        new = Sheet(sheet_path, 8)
        hulls, turret_frames, centres = {}, {}, {}
        for d in range(8):
            cv, owner, _ = tanks[d]
            dome, barrel = masks[d]
            if not dome.any():
                raise SystemExit("%s d%d: the dome mask is empty" % (name, d))
            hull, fill, gone = make_hull(cv, sheet.palette, dome, barrel)
            hulls[d] = hull
            changed = fill | gone
            for p, f in enumerate(split([sheet.frame(p * 8 + d) for p in range(4)], hull, owner, changed)):
                new.set_frame(p * 8 + d, f)
            if walk:
                # the tracks keep moving: every walking frame loses the barrel the same way
                for k in range(4):
                    wc, wo, _ = walk_canvas(sheet, d, k)
                    nw = wc.copy()
                    nw[fill] = hull[fill]
                    nw[gone] = 0
                    orig = [sheet.frame(walk_index(d, p, k)) for p in range(4)]
                    for p, f in enumerate(split(orig, nw, wo, changed)):
                        new.set_frame(walk_index(d, p, k), f)
            turret_frames[d] = np.where(dome | barrel, cv, 0).astype(np.uint8)
            ys, xs = np.nonzero(dome)
            centres[d] = (float(xs.mean()), float(ys.mean()))

        rear = args.mount != "center"
        target = None
        if rear:
            mount_file = os.path.join(work, "mount.json")
            manual = load_mount(mount_file)
            if manual:
                model = (manual["C"][0], manual["C"][1], manual["u"], manual.get("v", 0.0))
                source, off = "manual (%s)" % mount_file, {}
            else:
                model, off, kept = robust_fit(centres)
                source = "the dome masks"
            cx, cy, u, v = model
            print("  turret mount from %s: centre (%.1f, %.1f), %.2f tile %s, %.2f tile to the side" % (
                source, cx, cy, abs(u), "back" if u < 0 else "forward", v))
            for d, r in sorted(off.items()):
                if r > 3.0:
                    print("  !! d%d: that dome mask is %.1f px off the others - check mask_d%d.png" % (d, r, d))
            M = {d: np.array([cx, cy]) + u * screen_dir(d) + v * screen_dir(d + 2) for d in range(8)}
            if args.mount == "measured":
                M = {d: np.array(centres[d]) for d in range(8)}
            target = {d: (float(M[d][0]), float(M[d][1])) for d in range(8)}
            if not manual:
                json.dump(dict(manual=False, C=[round(cx, 2), round(cy, 2)], u=round(u, 4), v=round(v, 4), source=source,
                               dome_centres={str(d): [round(p[0], 2), round(p[1], 2)] for d, p in centres.items()},
                               off_px={str(d): round(r, 2) for d, r in off.items()},
                               note="turret pivot on hull d = C + u*screen_dir(d) + v*screen_dir(d+2) (tiles; u < 0 = rear). "
                                    "Set manual: true to use your own C/u/v, then run --stage build."),
                          open(mount_file, "w", encoding="utf-8"), indent=1)
            big, clipped = {}, 0
            for h in range(8):
                for t in range(8):
                    tb = to_big(turret_frames[t])
                    dx, dy = (int(round(M[h][0] - M[t][0])), int(round(M[h][1] - M[t][1])))
                    big[h * 8 + t] = shift(tb, dx, dy) if (dx or dy) else tb
                    clipped += int((tb != 0).sum() - (big[h * 8 + t] != 0).sum())
            if clipped:
                print("  note: %d turret pixels fall off the %dx%d frame in some combinations" % (clipped, BIG_W, BIG_H))
        else:
            big = {h * 8 + t: to_big(turret_frames[t]) for h in range(8) for t in range(8)}
        # turret frames: after the sheet when the walking frames stay in use, else the engine's own place
        # (64 + 8 * turretType; the engine checks that frame exists before the script runs)
        base = (max(160, sheet.rows * sheet.cols) + 7) // 8 * 8 if walk else 64 + 8 * args.turret_type
        script = make_script(rear, walk, base)

        res_dir = os.path.join(args.out_mod, "Resources", "TankTurret")
        new.save(os.path.join(res_dir, name + ".png"))
        tdir = os.path.join(res_dir, name + "_turret")
        os.makedirs(tdir, exist_ok=True)
        for fn in os.listdir(tdir):
            if fn.lower().endswith(".png"):
                os.remove(os.path.join(tdir, fn))
        if rear:
            for i in range(64):
                save_indexed(big[i], sheet.palette, os.path.join(tdir, "%02d.png" % i))
        else:
            for d in range(8):
                save_indexed(big[d * 8 + d], sheet.palette, os.path.join(tdir, "%d.png" % d))
        with open(os.path.join(work, "selectUnitSprite.txt"), "w", encoding="utf-8") as f:
            f.write(script or "(no script: the engine's default)\n")
        armors = find_armors(rulesets, name + ".PCK")
        sheets_info.append(dict(
            type=name + ".PCK", width=sheet.image.width, height=sheet.image.height,
            sheet_file="Resources/TankTurret/%s.png" % name, turret_dir="Resources/TankTurret/%s_turret/" % name,
            turret_type=args.turret_type, turret_base=base, script=script,
            armors=[a for a, r, w in armors],
            weapons=sorted({guns[0] for a, r, guns in armors if guns})))
        print("  armors on %s.PCK: %s" % (name, ", ".join("%s (routine %s, gun %s)" % (a, r, w[0] if w else "-") for a, r, w in armors) or "none found"))
        print("  turret frames %d..%d (%s), track animation %s" % (
            base, base + (63 if rear else 7), "turret on the rear of every hull" if rear else "one place", "kept" if walk else "none"))

        # previews
        rebuilt = Sheet(os.path.join(res_dir, name + ".png"), 8)
        z = 4
        tiles, labels = [], []
        for d in range(8):
            hull_img = show(assemble(rebuilt, d)[0], sheet.palette, z)
            if target:
                mark(hull_img, target[d], z, (0, 230, 255))
            tiles += [show(tanks[d][0], sheet.palette, z), hull_img, show(turret_frames[d], sheet.palette, z)]
            labels += ["d%d was" % d, "hull %d" % d, "turret %d" % d]
        grid(tiles, 6, labels).save(os.path.join(work, "preview_parts.png"))
        combos, labels = [], []
        for h in range(8):
            for t in range(8):
                combos.append(show_big(assemble(rebuilt, h)[0], big[h * 8 + t], sheet.palette, 2))
                labels.append("h%d t%d" % (h, t))
        grid(combos, 8, labels).save(os.path.join(work, "preview_grid.png"))
        seq = [(1, t) for t in range(8)] + [(h, 1) for h in range(1, 8)] + [(0, 1)] + [(h, h) for h in range(8)]
        frames = []
        for h, t in seq:
            im = show_big(assemble(rebuilt, h)[0], big[h * 8 + t], sheet.palette, 5)
            ImageDraw.Draw(im).text((4, 2), "hull %d  turret %d" % (h, t), fill=(255, 255, 255), font=font(12))
            frames.append(im)
        frames[0].save(os.path.join(work, "preview_turn.gif"), save_all=True, append_images=frames[1:], duration=350, loop=0)
        if walk:
            frames = []
            for h in (1, 3, 5, 7):
                for rep in range(3):
                    for k in range(4):
                        frames.append(show_big(walk_canvas(rebuilt, h, k)[0], big[h * 8 + h], sheet.palette, 5))
            frames[0].save(os.path.join(work, "preview_walk.gif"), save_all=True, append_images=frames[1:], duration=120, loop=0)
        print("  -> %s, %s (previews in %s)" % (os.path.join(res_dir, name + ".png"), tdir, work))

    if sheets_info:
        write_mod(args.out_mod, args.master, sheets_info)
        print("mod: %s (enable it after X-Piratez; needs the HD build with big turret frames)" % args.out_mod)
    print("done in %.0f s" % (time.time() - t_start))
    return 0


if __name__ == "__main__":
    sys.exit(main())
