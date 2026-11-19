# Набор образцов для imgdecode: корректные (все форматы SDL_image) и повреждённые (мутации).
# make_corpus.py <папка набора> <папка тестов upstream> [доп. настоящие файлы...]
import os, sys, struct, random, shutil, pathlib
from PIL import Image

out = pathlib.Path(sys.argv[1])
good = out / "good"
bad = out / "bad"
shutil.rmtree(out, ignore_errors=True)
good.mkdir(parents=True)
bad.mkdir(parents=True)

# --- 1. образцы upstream (ветка main, каталог test) ---
for p in pathlib.Path(sys.argv[2]).iterdir():
    if p.suffix.lower() in (".bmp", ".gif", ".png", ".pcx", ".pnm", ".tga", ".tif", ".webp", ".xcf", ".xpm",
                            ".jpg", ".ico", ".cur"):
        shutil.copy(p, good / ("up_" + p.name))

# --- 2. свои: индексированные, палитры, прозрачность, ключ, размеры ---
rnd = random.Random(505)


def pal_image(w, h, colors):
    im = Image.new("P", (w, h))
    pal = []
    for i in range(256):
        pal += [(i * 7) % 256, (i * 13 + 40) % 256, (255 - i * 3) % 256]
    im.putpalette(pal)
    im.putdata([(x * 3 + y * 5 + (x * y) % 7) % colors for y in range(h) for x in range(w)])
    return im


sizes = [(1, 1), (7, 3), (32, 40), (320, 200), (257, 129)]
for w, h in sizes:
    tag = "%dx%d" % (w, h)
    im = pal_image(w, h, 256)
    im.save(good / ("pal8_%s.bmp" % tag))
    im.save(good / ("pal8_%s.pcx" % tag))
    im.save(good / ("pal8_%s.gif" % tag))
    im.save(good / ("pal8t_%s.gif" % tag), transparency=0)
    im.save(good / ("pal8_%s.png" % tag))
    im.save(good / ("pal8t_%s.png" % tag), transparency=0)
    im.save(good / ("pal8t5_%s.png" % tag), transparency=5)
    im.save(good / ("pal8_%s.tga" % tag))
    im.save(good / ("pal8rle_%s.tga" % tag), compression="tga_rle")
    im.save(good / ("pal8_%s.tif" % tag))
    rgb = im.convert("RGB")
    rgb.save(good / ("rgb_%s.bmp" % tag))
    rgb.save(good / ("rgb_%s.pcx" % tag))
    rgb.save(good / ("rgb_%s.png" % tag))
    rgb.save(good / ("rgb_%s.tga" % tag))
    rgb.save(good / ("rgbrle_%s.tga" % tag), compression="tga_rle")
    rgb.save(good / ("rgb_%s.ppm" % tag))
    rgb.save(good / ("rgb_%s.jpg" % tag), quality=90)
    rgb.save(good / ("rgb_%s.tif" % tag))
    rgb.save(good / ("rgb_%s.webp" % tag), lossless=True)
    rgba = im.convert("RGBA")
    rgba.putalpha(Image.new("L", (w, h), 128))
    rgba.save(good / ("rgba_%s.png" % tag))
    rgba.save(good / ("rgba_%s.tga" % tag))
    rgba.save(good / ("rgba_%s.bmp" % tag))
    rgba.save(good / ("rgba_%s.webp" % tag), lossless=True)
    gray = im.convert("L")
    gray.save(good / ("gray_%s.png" % tag))
    gray.save(good / ("gray_%s.pgm" % tag))
    gray.save(good / ("gray_%s.tga" % tag))
    gray.save(good / ("gray_%s.bmp" % tag))
    one = gray.point(lambda v: 255 if v > 127 else 0).convert("1")
    one.save(good / ("mono_%s.png" % tag))
    one.save(good / ("mono_%s.pbm" % tag))
    one.save(good / ("mono_%s.bmp" % tag))
    one.save(good / ("mono_%s.pcx" % tag))
    for colors, bits in ((2, 1), (4, 2), (16, 4)):
        small = pal_image(w, h, colors)
        small.save(good / ("pal%d_%s.png" % (bits, tag)), bits=bits)
        small.save(good / ("pal%dt_%s.png" % (bits, tag)), bits=bits, transparency=0)
        if bits != 2:
            small.save(good / ("pal%d_%s.bmp" % (bits, tag)), bits=bits)
im = pal_image(64, 48, 256)
im.save(good / "pal8_interlace.png", interlace=True) if False else None
im.save(good / "pal8_interlace.gif", interlace=True)
im.convert("RGB").save(good / "rgb_progressive.jpg", progressive=True)

# PNM текстом
(good / "ascii.pbm").write_bytes(b"P1\n# c\n4 2\n0 1 0 1\n1 0 1 0\n")
(good / "ascii.pgm").write_bytes(b"P2\n3 2\n255\n0 128 255\n10 20 30\n")
(good / "ascii.ppm").write_bytes(b"P3\n2 2\n255\n255 0 0  0 255 0\n0 0 255  9 9 9\n")
# XPM
xpm = ['/* XPM */', 'static char *t[] = {', '"8 4 3 1",', '"  c None",', '". c #FF0000",', '"X c #0000FF",',
       '"  ..XX  ",', '" ..XX.. ",', '"..XX..XX",', '"XX..XX.."', '};']
(good / "small.xpm").write_bytes("\n".join(xpm).encode())
xpm2 = ['/* XPM */', 'static char *t[] = {', '"4 2 4 2",', '"aa c #102030",', '"ab c black",', '"ba c white",',
        '"bb c None",', '"aaabbabb",', '"bbbaabaa"', '};']
(good / "cpp2.xpm").write_bytes("\n".join(xpm2).encode())
# XV (P7 332)
(good / "thumb.xv").write_bytes(b"P7 332\n#IMGINFO:8x2 Indexed\n#END_OF_COMMENTS\n8 2 255\n" + bytes(range(16)))


# LBM: ILBM без сжатия и со сжатием ByteRun1, 4 плоскости; PBM 8 бит
def chunk(tag, data):
    return tag + struct.pack(">I", len(data)) + data + (b"\x00" if len(data) & 1 else b"")


def lbm(kind, w, h, planes, compress):
    bmhd = struct.pack(">HHhhBBBBHBBhh", w, h, 0, 0, planes, 0, compress, 0, 0, 1, 1, w, h)
    cmap = bytes((i * 11) % 256 for i in range(3 * (1 << planes)))
    rows = b""
    for y in range(h):
        px = [(x + y) % (1 << planes) for x in range(w)]
        if kind == b"PBM ":
            line = bytes(px) + (b"\x00" if w & 1 else b"")
            lines = [line]
        else:
            bpr = ((w + 15) // 16) * 2
            lines = []
            for pl in range(planes):
                b = bytearray(bpr)
                for x in range(w):
                    if px[x] >> pl & 1:
                        b[x // 8] |= 0x80 >> (x % 8)
                lines.append(bytes(b))
        for line in lines:
            if compress:
                i = 0
                while i < len(line):
                    part = line[i:i + 128]
                    rows += bytes([len(part) - 1]) + part
                    i += 128
            else:
                rows += line
    body = kind + chunk(b"BMHD", bmhd) + chunk(b"CMAP", cmap) + chunk(b"BODY", rows)
    return b"FORM" + struct.pack(">I", len(body)) + body


(good / "ilbm4.lbm").write_bytes(lbm(b"ILBM", 33, 9, 4, 0))
(good / "ilbm4rle.lbm").write_bytes(lbm(b"ILBM", 33, 9, 4, 1))
(good / "ilbm8.lbm").write_bytes(lbm(b"ILBM", 320, 20, 8, 1))
(good / "pbm8.lbm").write_bytes(lbm(b"PBM ", 31, 7, 8, 0))
(good / "pbm8rle.lbm").write_bytes(lbm(b"PBM ", 320, 200, 8, 1))

# настоящие файлы из игры и модов (по одному-два на вид), копией
for i, p in enumerate(sys.argv[3:]):
    p = pathlib.Path(p)
    shutil.copy(p, good / ("real%02d%s" % (i, p.suffix.lower())))

# --- 3. повреждённые: усечения, крайние значения полей заголовка, случайные байты ---
n = 0
for p in sorted(good.iterdir()):
    data = p.read_bytes()
    if len(data) > 300000:
        continue
    muts = []
    L = len(data)
    for cut in sorted(set([0, 1, 2, 4, 8, 12, 16, 24, 32, 54, 64, 128, L // 4, L // 2, L * 3 // 4, L - 1])):
        if 0 <= cut < L:
            muts.append(data[:cut])
    for pos in range(min(L, 72)):
        for v in (0x00, 0xFF, 0x7F, 0x80):
            if data[pos] != v:
                muts.append(data[:pos] + bytes([v]) + data[pos + 1:])
    for k in range(120):
        b = bytearray(data)
        for _ in range(rnd.choice((1, 2, 4, 16))):
            b[rnd.randrange(L)] = rnd.randrange(256)
        muts.append(bytes(b))
    for k in range(20):   # вставка и вырезка куска
        a = rnd.randrange(L)
        ln = rnd.randrange(1, 64)
        muts.append(data[:a] + data[a + ln:])
        muts.append(data[:a] + bytes(rnd.randrange(256) for _ in range(ln)) + data[a:])
    sub = bad / p.suffix.lower().lstrip(".")
    sub.mkdir(exist_ok=True)
    for i, m in enumerate(muts):
        (sub / ("%s_%04d%s" % (p.stem, i, p.suffix))).write_bytes(m)
        n += 1
print("корректных:", len(list(good.iterdir())), "повреждённых:", n)
