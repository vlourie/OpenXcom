"""Иконка лаунчера OXCE HD: векторный рисунок в палитре Skin.cs, без модели.

Рисуется по координатам (R-042: углы острые, края гладкие) в 2048 и уменьшается под каждый
размер .ico отдельно; на 16-32 мелочь (звёзды, рамка, подпись HD) не рисуется, обводка толще.

    py -3.13 tools/launcher_icon.py sheet [вариант...] # лист вариантов -> art/launcher_icon/sheet.png
    py -3.13 tools/launcher_icon.py ico oxce_globe       # portal/src/Xp.Launcher/Assets/app.ico
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "art" / "launcher_icon"
ICO = ROOT / "portal" / "src" / "Xp.Launcher" / "Assets" / "app.ico"
FONT = ROOT / "portal" / "src" / "Xp.Launcher" / "Assets" / "Fonts" / "Roboto-Medium.ttf"
SIZES = [256, 128, 64, 48, 40, 32, 24, 20, 16]
S = 2048

# Skin.cs
BG_TOP = (34, 10, 52)
BG_BOT = (10, 0, 14)
FRAME = (0x50, 0x78, 0x18)
LIME = (0x80, 0xD0, 0x00)
LIME_HI = (0xC8, 0xFF, 0x60)
LIME_LO = (0x4A, 0x80, 0x00)
DARK = (0x06, 0x0C, 0x00)
TEAL = (0x00, 0xC8, 0xB8)
TEAL_DEEP = (0x03, 0x2E, 0x30)
MAGENTA = (0xF0, 0x80, 0xE0)
MAGENTA_LO = (0x78, 0x28, 0x78)


def tile_mask(small):
    m = Image.new("L", (S, S), 0)
    pad = 0 if small else int(S * 0.03)
    ImageDraw.Draw(m).rounded_rectangle((pad, pad, S - 1 - pad, S - 1 - pad), radius=int(S * 0.2), fill=255)
    return m


def tile(small):
    """Фон: вертикальный градиент космоса, звёзды, лаймовая рамка окна игры."""
    bg = Image.new("RGB", (1, 256))
    for y in range(256):
        t = y / 255
        bg.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT)))
    img = bg.resize((S, S)).convert("RGBA")
    d = ImageDraw.Draw(img)
    if not small:
        stars = [(0.18, 0.16, 6), (0.30, 0.09, 4), (0.78, 0.13, 7), (0.88, 0.30, 4), (0.12, 0.42, 4),
                 (0.66, 0.07, 3), (0.50, 0.14, 4), (0.90, 0.55, 3), (0.08, 0.70, 3)]
        for x, y, r in stars:
            d.ellipse((x * S - r * 2, y * S - r * 2, x * S + r * 2, y * S + r * 2), fill=(220, 210, 255, 200))
    return img


def frame(img, small):
    if small:
        return
    pad = int(S * 0.03)
    w = int(S * 0.012)
    ImageDraw.Draw(img).rounded_rectangle((pad + w, pad + w, S - 1 - pad - w, S - 1 - pad - w),
                                          radius=int(S * 0.19), outline=FRAME + (255,), width=w)


def planet(img, cx, cy, r, small):
    """Край планеты: тёмно-бирюзовый диск, светлый ободок атмосферы, сетка геоскейпа."""
    lay = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((cx - r * 1.06, cy - r * 1.06, cx + r * 1.06, cy + r * 1.06), fill=TEAL + (110,))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.02))
    lay.alpha_composite(glow)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=TEAL_DEEP + (255,))
    if not small:
        grid = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        g = ImageDraw.Draw(grid)
        lw = int(S * 0.006)
        for k in (0.25, 0.55, 0.85):
            g.ellipse((cx - r * k, cy - r, cx + r * k, cy + r), outline=TEAL + (90,), width=lw)
        for k in (-0.6, -0.3, 0.0, 0.3, 0.6):
            y = cy + r * k
            hw = r * math.sqrt(1 - k * k)
            g.line((cx - hw, y, cx + hw, y), fill=TEAL + (90,), width=lw)
        disc = Image.new("L", (S, S), 0)
        ImageDraw.Draw(disc).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
        grid.putalpha(Image.composite(grid.getchannel("A"), Image.new("L", (S, S), 0), disc))
        lay.alpha_composite(grid)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=TEAL + (255,), width=int(S * (0.016 if small else 0.01)))
    img.alpha_composite(lay)


def place(pts, cx, cy, ang, flip):
    """Локальные (x поперёк, y вдоль клинка к острию) -> экран; ang - угол острия от вертикали."""
    dx, dy = math.sin(ang), -math.cos(ang)
    px, py = math.cos(ang), math.sin(ang)
    out = []
    for x, y in pts:
        X = cx + y * dx + x * px
        Y = cy + y * dy + x * py
        if flip:
            X = 2 * cx - X
        out.append((X, Y))
    return out


def sabre(img, cx, cy, ang, flip, small):
    """Абордажная сабля: изогнутый клинок, гарда маджента, рукоять и навершие."""
    d = ImageDraw.Draw(img)
    L, w0, bend, y0 = S * 0.66, S * (0.15 if small else 0.10), S * 0.11, S * 0.30
    edge, back, hi = [], [], []
    n = 64
    for i in range(n + 1):
        t = i / n
        c = bend * t * t
        w = w0 * (1 - 0.25 * t)
        if t > 0.78:  # острие: спинка сходится к режущей кромке
            w *= (1 - t) / 0.22
        nx, ny = 1.0, -2 * bend * t / L  # нормаль к (2*bend*t/L, 1)
        k = math.hypot(nx, ny)
        nx, ny = nx / k, ny / k
        yy = t * L - y0
        edge.append((c + nx * w * 0.5, yy + ny * w * 0.5))
        back.append((c - nx * w * 0.5, yy - ny * w * 0.5))
        hi.append((c + nx * w * 0.08, yy + ny * w * 0.08))
    blade = edge + back[::-1]
    shine = edge + hi[::-1]
    ow = int(S * (0.03 if small else 0.018))
    gy = -y0
    guard = [(-S * 0.13, gy - S * 0.022), (S * 0.13, gy - S * 0.022), (S * 0.13, gy + S * 0.022), (-S * 0.13, gy + S * 0.022)]
    grip = [(-S * 0.03, gy - S * 0.17), (S * 0.03, gy - S * 0.17), (S * 0.035, gy), (-S * 0.035, gy)]
    pc = place([(0, gy - S * 0.19)], cx, cy, ang, flip)[0]
    pr = S * 0.042
    for poly, fill in ((grip, (0x5A, 0x34, 0x22)), (blade, LIME), (guard, MAGENTA)):
        p = place(poly, cx, cy, ang, flip)
        d.polygon(p, fill=DARK + (255,), outline=DARK + (255,), width=ow * 2)
    d.ellipse((pc[0] - pr - ow, pc[1] - pr - ow, pc[0] + pr + ow, pc[1] + pr + ow), fill=DARK + (255,))
    d.polygon(place(grip, cx, cy, ang, flip), fill=(0x6E, 0x42, 0x2A, 255))
    d.polygon(place(blade, cx, cy, ang, flip), fill=LIME + (255,))
    if not small:
        d.polygon(place(shine, cx, cy, ang, flip), fill=LIME_HI + (255,))
        d.line(place(back, cx, cy, ang, flip)[4:-6], fill=LIME_LO + (255,), width=int(S * 0.008))
    d.polygon(place(guard, cx, cy, ang, flip), fill=MAGENTA + (255,))
    d.ellipse((pc[0] - pr, pc[1] - pr, pc[0] + pr, pc[1] + pr), fill=MAGENTA + (255,))


def bar_x(img, cx, cy, half, thick, small):
    """Жирная буква X из двух брусков со срезанными концами, с фаской сверху."""
    d = ImageDraw.Draw(img)
    ow = int(S * (0.03 if small else 0.02))
    bars = []
    for a in (math.pi / 4, -math.pi / 4):
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy, dx
        bars.append([(cx - dx * half + px * thick, cy - dy * half + py * thick),
                     (cx + dx * half + px * thick, cy + dy * half + py * thick),
                     (cx + dx * half - px * thick, cy + dy * half - py * thick),
                     (cx - dx * half - px * thick, cy - dy * half - py * thick)])
    for b in bars:
        d.polygon(b, fill=DARK + (255,), outline=DARK + (255,), width=ow * 2)
    for b in bars:
        d.polygon(b, fill=LIME + (255,))
    if not small:
        for b in bars:  # светлая грань по верхней половине бруска
            top = [b[0], b[1], ((b[1][0] + b[2][0]) / 2, (b[1][1] + b[2][1]) / 2), ((b[0][0] + b[3][0]) / 2, (b[0][1] + b[3][1]) / 2)]
            if (top[0][1] + top[1][1]) > (b[2][1] + b[3][1]):
                top = [b[3], b[2], top[2], top[3]]
            d.polygon(top, fill=LIME_HI + (255,))


def hd_tag(img, small):
    if small:
        return
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(str(FONT), int(S * 0.2))
    x, y = S * 0.62, S * 0.70
    box = d.textbbox((x, y), "HD", font=f)
    r = (box[0] - S * 0.035, box[1] - S * 0.03, box[2] + S * 0.035, box[3] + S * 0.03)
    d.rounded_rectangle(r, radius=int(S * 0.04), fill=DARK + (255,), outline=TEAL + (255,), width=int(S * 0.012))
    d.text((x, y), "HD", font=f, fill=TEAL + (255,))


def fit_text(d, text, width, stroke):
    """Шрифт такого размера, чтобы надпись с обводкой заняла ровно width."""
    size = 400
    f = ImageFont.truetype(str(FONT), size)
    b = d.textbbox((0, 0), text, font=f, stroke_width=int(size * stroke))
    size = int(size * width / (b[2] - b[0]))
    return ImageFont.truetype(str(FONT), size), int(size * stroke)


def text_c(img, text, cx, cy, width, fill, stroke=0.03, outline=0.07):
    """Надпись по центру (cx, cy): тёмная обводка, затем заливка, утолщённая своей обводкой."""
    d = ImageDraw.Draw(img)
    f, sw = fit_text(d, text, width, stroke)
    ow = sw + int(f.size * outline)
    b = d.textbbox((0, 0), text, font=f, stroke_width=sw)
    x = cx - (b[0] + b[2]) / 2
    y = cy - (b[1] + b[3]) / 2
    d.text((x, y), text, font=f, fill=DARK + (255,), stroke_width=ow, stroke_fill=DARK + (255,))
    d.text((x, y), text, font=f, fill=fill + (255,), stroke_width=sw, stroke_fill=fill + (255,))
    return d.textbbox((x, y), text, font=f, stroke_width=ow)


def oxce(img, small, globe):
    if globe:
        planet(img, S * 0.5, S * 0.5, S * 0.36, small)
    else:
        planet(img, S * 0.5, S * 1.40, S * 0.62, small)
    if small:
        text_c(img, "HD", S * 0.5, S * 0.5, S * 0.80, LIME, stroke=0.05)
        return
    b = text_c(img, "OXCE", S * 0.5, S * 0.37, S * 0.80, LIME)
    d = ImageDraw.Draw(img)
    f, sw = fit_text(d, "HD", S * 0.34, 0.02)
    tb = d.textbbox((0, 0), "HD", font=f, stroke_width=sw)
    h = tb[3] - tb[1]
    cy = b[3] + S * 0.05 + h / 2 + S * 0.03
    r = (S * 0.5 - S * 0.25, cy - h / 2 - S * 0.045, S * 0.5 + S * 0.25, cy + h / 2 + S * 0.045)
    d.rounded_rectangle(r, radius=int(S * 0.05), fill=DARK + (255,), outline=TEAL + (255,), width=int(S * 0.014))
    text_c(img, "HD", S * 0.5, cy, S * 0.34, TEAL, stroke=0.02, outline=0.0)


def draw(variant, small):
    img = tile(small)
    if variant == "sabres":
        planet(img, S * 0.5, S * 1.40, S * 0.62, small)
        sabre(img, S * 0.5, S * 0.44, math.radians(40), False, small)
        sabre(img, S * 0.5, S * 0.44, math.radians(40), True, small)
    elif variant == "sabres_globe":
        planet(img, S * 0.5, S * 0.47, S * 0.31, small)
        sabre(img, S * 0.5, S * 0.47, math.radians(40), False, small)
        sabre(img, S * 0.5, S * 0.47, math.radians(40), True, small)
    elif variant == "oxce_globe":
        oxce(img, small, True)
    elif variant == "oxce":
        oxce(img, small, False)
    elif variant == "globe":
        planet(img, S * 0.5, S * 0.5, S * 0.33, small)
        if not small:
            d = ImageDraw.Draw(img)
            ux, uy, ur = S * 0.70, S * 0.30, S * 0.035
            d.polygon([(ux, uy - ur * 1.6), (ux + ur, uy), (ux, uy + ur * 1.6), (ux - ur, uy)], fill=MAGENTA + (255,))
        bar_x(img, S * 0.5, S * 0.5, S * 0.40, S * (0.085 if small else 0.065), small)
    elif variant == "monogram":
        planet(img, S * 0.5, S * 1.35, S * 0.62, small)
        cy = S * (0.5 if small else 0.43)
        bar_x(img, S * (0.5 if small else 0.44), cy, S * (0.40 if small else 0.33), S * (0.09 if small else 0.075), small)
        hd_tag(img, small)
    else:
        raise SystemExit(f"нет варианта {variant}: {VARIANTS}")
    frame(img, small)
    m = tile_mask(small)
    img.putalpha(Image.composite(img.getchannel("A"), Image.new("L", (S, S), 0), m))
    return img


def render(variant, size):
    return draw(variant, size <= 32).resize((size, size), Image.LANCZOS)


VARIANTS = ["oxce_globe", "oxce", "sabres", "sabres_globe", "globe", "monogram"]


def sheet():
    OUT.mkdir(parents=True, exist_ok=True)
    show = [256, 64, 48, 32, 24, 16]
    cell = 280
    W = cell * len(show) + 40
    rows = []
    for v in VARIANTS:
        big = draw(v, False)
        small = draw(v, True)
        big.resize((512, 512), Image.LANCZOS).save(OUT / f"{v}_512.png")
        for bg in ((32, 32, 32), (238, 238, 238)):
            row = Image.new("RGBA", (W, cell), bg + (255,))
            x = 20
            for s in show:
                ic = (small if s <= 32 else big).resize((s, s), Image.LANCZOS)
                row.alpha_composite(ic, (x + (cell - 20 - s) // 2, (cell - s) // 2))
                x += cell
            rows.append((v, row))
    lab = 36
    out = Image.new("RGBA", (W, len(rows) * cell + len(VARIANTS) * lab), (20, 20, 20, 255))
    d = ImageDraw.Draw(out)
    f = ImageFont.truetype(str(FONT), 26)
    y = 0
    for i, (v, row) in enumerate(rows):
        if i % 2 == 0:
            d.text((20, y + 4), f"{i // 2 + 1}. {v}   (256, 64, 48, 32, 24, 16)", font=f, fill=(220, 220, 220, 255))
            y += lab
        out.alpha_composite(row, (0, y))
        y += cell
    out.save(OUT / "sheet.png")
    print("лист:", OUT / "sheet.png")


def ico(variant):
    imgs = [render(variant, s) for s in SIZES]
    ICO.parent.mkdir(parents=True, exist_ok=True)
    imgs[0].save(ICO, format="ICO", sizes=[(s, s) for s in SIZES], append_images=imgs[1:])
    OUT.mkdir(parents=True, exist_ok=True)
    render(variant, 256).save(OUT / f"app_{variant}_256.png")
    print("иконка:", ICO, ICO.stat().st_size, "байт;", "размеры", SIZES)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sheet"
    if cmd == "sheet":
        if len(sys.argv) > 2:
            VARIANTS[:] = sys.argv[2:]
        sheet()
    elif cmd == "ico":
        ico(sys.argv[2] if len(sys.argv) > 2 else "oxce_globe")
    else:
        raise SystemExit(__doc__)
