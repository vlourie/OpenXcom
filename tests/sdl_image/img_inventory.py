# Инвентаризация картинок по фактической сигнатуре, а не по расширению.
# Запуск: img_inventory.py <выход.tsv> <корень>...   Пишет таблицу и сводку.
import os, sys, struct, collections, zlib
from concurrent.futures import ThreadPoolExecutor

EXTS = {"png", "gif", "bmp", "pcx", "lbm", "iff", "ilbm", "tga", "xpm", "xcf", "tif", "tiff", "jpg", "jpeg",
        "webp", "pnm", "pbm", "pgm", "ppm", "ico", "cur", "xv"}


def sniff(b):
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    if b[:2] == b"BM":
        return "BMP"
    if b[:3] == b"\xff\xd8\xff":
        return "JPG"
    if b[:4] == b"FORM" and b[8:12] in (b"ILBM", b"PBM "):
        return "LBM"
    if b[:4] in (b"II*\x00", b"MM\x00*"):
        return "TIF"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "WEBP"
    if b[:9] == b"gimp xcf ":
        return "XCF"
    if b[:9] == b"/* XPM */":
        return "XPM"
    if b[:1] == b"P" and b[1:2] in b"123456" and b[2:3] in b" \t\r\n":
        return "PNM"
    if b[:4] in (b"\x00\x00\x01\x00", b"\x00\x00\x02\x00") and len(b) > 6:
        return "ICO" if b[2] == 1 else "CUR"
    if len(b) > 4 and b[0] == 10 and b[1] in (0, 2, 3, 4, 5) and b[2] in (0, 1):
        return "PCX"
    return "?"


def detail(kind, path, head, size):
    try:
        if kind == "PNG":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", head[16:29])
            trns = plte = 0
            with open(path, "rb") as f:
                f.seek(8)
                while True:
                    hd = f.read(8)
                    if len(hd) < 8:
                        break
                    ln, tag = struct.unpack(">I4s", hd)
                    if tag == b"tRNS":
                        trns = ln
                    elif tag == b"PLTE":
                        plte = ln // 3
                    elif tag in (b"IDAT", b"IEND"):
                        break
                    f.seek(ln + 4, 1)
            name = {0: "gray", 2: "rgb", 3: "pal", 4: "graya", 6: "rgba"}.get(ctype, "c%d" % ctype)
            return "%s%d%s%s" % (name, depth, " tRNS" if trns else "", " interlace" if inter else ""), w, h, plte
        if kind == "GIF":
            w, h, flags = struct.unpack("<HHB", head[6:11])
            ncol = 2 << (flags & 7) if flags & 0x80 else 0
            with open(path, "rb") as f:
                body = f.read(min(size, 1 << 16))
            transp = b"\x21\xf9\x04" in body and any(
                body[i + 3] & 1 for i in range(len(body) - 4) if body[i:i + 3] == b"\x21\xf9\x04")
            return "gif%s%s" % (head[3:6].decode(), " transp" if transp else ""), w, h, ncol
        if kind == "BMP":
            hsz = struct.unpack("<I", head[14:18])[0]
            if hsz == 12:
                w, h, _, bpp = struct.unpack("<HHHH", head[18:26])
                comp = 0
            else:
                w, h, _, bpp, comp = struct.unpack("<iiHHI", head[18:34])
            return "bmp%d hdr%d comp%d" % (bpp, hsz, comp), w, abs(h), 0
        if kind == "PCX":
            bpp = head[3]
            x0, y0, x1, y1 = struct.unpack("<HHHH", head[4:12])
            planes = head[65]
            return "pcx v%d %dbpp x%d planes enc%d" % (head[1], bpp, planes, head[2]), x1 - x0 + 1, y1 - y0 + 1, 0
        if kind == "LBM":
            return "lbm " + head[8:12].decode().strip(), 0, 0, 0
    except Exception as e:
        return "ошибка разбора: %s" % e, 0, 0, 0
    return "", 0, 0, 0


def one(path):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(128)
    except OSError as e:
        return path, "", "нет доступа", str(e), 0, 0, 0, 0
    ext = path.rsplit(".", 1)[-1].lower()
    kind = sniff(head)
    if kind == "?" and ext == "tga":
        kind = "TGA?"
    d, w, h, pal = detail(kind, path, head, size)
    return path, ext, kind, d, w, h, pal, size


def main():
    out = sys.argv[1]
    files = []
    for root in sys.argv[2:]:
        for dp, dn, fn in os.walk(root):
            for n in fn:
                if "." in n and n.rsplit(".", 1)[-1].lower() in EXTS:
                    files.append(os.path.join(dp, n))
    with ThreadPoolExecutor(16) as ex:
        rows = list(ex.map(one, files, chunksize=256))
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        f.write("path\text\tkind\tdetail\tw\th\tpalette\tsize\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")
    cross = collections.Counter((r[1], r[2]) for r in rows)
    print("файлов:", len(rows))
    print("расширение -> фактический формат:")
    for (e, k), n in sorted(cross.items(), key=lambda x: (-x[1])):
        print("  .%-5s %-5s %7d%s" % (e, k, n, "" if e.upper()[:3] == k[:3] or (e, k) in (("jpeg", "JPG"), ("tiff", "TIF"), ("iff", "LBM")) else "   <-- не совпадает"))
    det = collections.Counter((r[2], r[3]) for r in rows)
    print("свойства:")
    for (k, d), n in sorted(det.items(), key=lambda x: (x[0][0], -x[1])):
        print("  %-5s %-34s %7d" % (k, d, n))
    big = sorted(rows, key=lambda r: -(r[4] * r[5]))[:3]
    for r in big:
        print("  крупнейший: %dx%d %s %s" % (r[4], r[5], r[2], r[0][-70:]))
    mism = [r for r in rows if r[2] != "?" and r[1].upper()[:3] != r[2][:3] and (r[1], r[2]) not in (("jpeg", "JPG"), ("tiff", "TIF"), ("iff", "LBM"))]
    for r in mism[:25]:
        print("  не совпадает: .%s -> %s  %s" % (r[1], r[2], r[0][-90:]))
    unk = [r for r in rows if r[2] in ("?", "нет доступа")]
    for r in unk[:25]:
        print("  не распознан: %s (%d байт)" % (r[0][-90:], r[7]))


main()
