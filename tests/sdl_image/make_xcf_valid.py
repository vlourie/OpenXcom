# -*- coding: utf-8 -*-
"""Well-formed XCF files laid out the way GIMP writes them: every structure once, one after another, every tile with
its own offset. They are for one question: does the read budget of IMG_xcf.c (OXCE patch 7) cut a file that is in
order - the decoder before the patch and after it must give the same surface. Not written by GIMP: by this script,
after the description of the format (devel-docs/xcf.txt of GIMP).

  py -3 tests/sdl_image/make_xcf_valid.py <folder>     writes the files and list.txt
"""
import random, struct, sys
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
rnd = random.Random(20261119)


def be(*v):
    return struct.pack(">%dI" % len(v), *v)


def rle_channel(vals):
    res, i, n = bytearray(), 0, len(vals)
    while i < n:
        j = i
        while j < n and vals[j] == vals[i] and j - i < 2000:
            j += 1
        run = j - i
        if run >= 3:
            if run <= 127:
                res += bytes([run - 1, vals[i]])
            else:
                res += bytes([127, run >> 8, run & 255, vals[i]])
            i = j
        else:
            j = i
            while j < n and j - i < 127 and not (j + 2 < n and vals[j] == vals[j + 1] == vals[j + 2]):
                j += 1
            j = max(j, i + 1)
            res += bytes([256 - (j - i)]) + bytes(vals[i:j])
            i = j
    return bytes(res)


def tile_data(w, h, bpp, compr, kind):
    px = w * h
    if kind == 0:
        chans = [[rnd.randrange(256)] * px for _ in range(bpp)]
    elif kind == 1:
        chans = [[rnd.randrange(256) for _ in range(px)] for _ in range(bpp)]
    else:
        chans = [[(x // 7 + c * 40) & 255 for x in range(px)] for c in range(bpp)]
    if compr:
        return b"".join(rle_channel(c) for c in chans)
    return bytes(chans[c][p] for p in range(px) for c in range(bpp))


class File:
    def __init__(self):
        self.b = bytearray()

    def at(self):
        return len(self.b)

    def put(self, data):
        self.b += data

    def hole(self, n):
        pos = len(self.b)
        self.b += bytes(4 * n)
        return pos

    def fill(self, pos, *vals):
        self.b[pos:pos + 4 * len(vals)] = be(*vals)


def hierarchy(f, w, h, bpp, compr):
    start = f.at()
    f.put(be(w, h, bpp))
    lv = f.hole(1)
    f.put(be(0))
    f.fill(lv, f.at())
    f.put(be(w, h))
    n = ((w + 63) // 64) * ((h + 63) // 64)
    offs = f.hole(n)
    f.put(be(0))
    k = 0
    for ty in range(0, h, 64):
        for tx in range(0, w, 64):
            f.fill(offs + 4 * k, f.at())
            f.put(tile_data(min(64, w - tx), min(64, h - ty), bpp, compr, rnd.randrange(3)))
            k += 1
    return start


def name(s):
    s = s.encode() + b"\0"
    return be(len(s)) + s


def image(path, w, h, layers, compr, alpha, channels=0):
    f = File()
    f.put(b"gimp xcf file\0" + be(w, h, 0))
    f.put(be(17, 1) + bytes([compr]) + be(0, 0))
    lo = f.hole(len(layers)); f.put(be(0))
    co = f.hole(channels); f.put(be(0))
    for i, (lw, lh, ox, oy) in enumerate(layers):
        f.fill(lo + 4 * i, f.at())
        f.put(be(lw, lh, 1 if alpha else 0) + name("layer %d" % i))
        f.put(be(8, 4, 1) + be(15, 8, ox, oy) + be(6, 4, 255) + be(0, 0))
        ho = f.hole(1); f.put(be(0))
        f.fill(ho, hierarchy(f, lw, lh, 4 if alpha else 3, compr))
    for i in range(channels):
        f.fill(co + 4 * i, f.at())
        f.put(be(w, h) + name("channel %d" % i))
        f.put(be(8, 4, 1) + be(6, 4, 120) + be(16, 3) + bytes([200, 30, 30]) + be(0, 0))
        ho = f.hole(1)
        f.fill(ho, hierarchy(f, w, h, 1, compr))
    path.write_bytes(bytes(f.b))


names = []
n = 0
for w, h in ((1, 1), (63, 65), (64, 64), (200, 130), (1024, 768), (1500, 900)):
    for compr in (0, 1):
        for nl, alpha, ch in ((1, 0, 0), (3, 1, 1)):
            layers = [(w, h, 0, 0)] + [(max(1, w // (i + 1)), max(1, h // (i + 2)), i * 3, i * 5) for i in range(1, nl)]
            p = out / ("valid_%02d_%dx%d_c%d_l%d.xcf" % (n, w, h, compr, nl))
            image(p, w, h, layers, compr, alpha, ch)
            names.append(p); n += 1
# the tightest cases for the budget: many layers of one pixel, and many small layers over a large image
for w, h, nl, compr in ((1, 1, 500, 1), (1, 1, 500, 0), (300, 300, 200, 1), (2, 2, 3000, 1)):
    p = out / ("valid_%02d_many_%dx%d_c%d_l%d.xcf" % (n, w, h, compr, nl))
    image(p, w, h, [(1 + (i % 3 == 0) * min(w - 1, 70), 1 + (i % 5 == 0) * min(h - 1, 70), i % w, i % h) for i in range(nl)], compr, 1)
    names.append(p); n += 1
(out / "list.txt").write_text("\n".join(str(p).replace("\\", "/") for p in names) + "\n", encoding="utf-8")
print("%d files in %s" % (len(names), out))
