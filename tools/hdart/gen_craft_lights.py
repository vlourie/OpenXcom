#!/usr/bin/env python3
"""
gen_craft_lights.py - проблесковые огни кораблей в ангаре базы.

Ставит огни по силуэту картинки корабля в ангаре (кадр BASEBITS.PCK = sprite + 33
у корабля, у скина свой номер) и пишет для движка (HdCraftLights):

    <мод hd>/hd/BASEBITS.PCK/<кадр>.lights.txt

    red    - левая законцовка крыла, горит ровно
    green  - правая законцовка
    strobe - хвост, белая двойная вспышка
    beacon - маячок по центру корпуса, медленно пульсирует красным
    blink #rrggbb - огонь, уже нарисованный на картинке (PAINTED): у такого корабля
             светятся только нарисованные места, своим цветом

Тень спрайта (тёмно-серая кромка справа и снизу) в поиск краёв не входит.
Наземная техника и следы экспедиций (кадр 200 и прочие из SKIP) огней не получают.
Уже существующий файл не перезаписывается без --force: правленные руками точки целы.

--preview пишет GIF со всеми кораблями и огнями по тем же формулам, что в движке,
чтобы принять разметку глазами до игры.

    py -3 tools/hdart/gen_craft_lights.py --src "E:/OpenXCom/Пиратки/Dioxine_XPiratez/user/mods/Piratez"
        --out "E:/OpenXCom/Пиратки/Dioxine_XPiratez/user/mods/hd" --preview art/_review/craft_lights.gif
"""
import argparse
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_base import basebits_map  # noqa: E402

ENC_W = "utf-8-sig"
# наземное и не летает: следы экспедиций, машины, байки, танк; 33 - обломки корабля
SKIP = {33, 200, 238, 239, 240, 241, 263, 277, 178, 280, 284, 255}
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
VANILLA_PCK = os.path.join(ROOT, "bin", "UFO", "GEOGRAPH", "BASEBITS.PCK")
VANILLA_PAL = os.path.join(ROOT, "bin", "UFO", "GEODATA", "PALETTES.DAT")
PAL_BASESCAPE = 1

# Огни, уже нарисованные на картинке корабля (X-Piratez): кадр -> [(x, y, цвет пятна)].
# Отобраны глазами по листу кандидатов (пятно заметно другого цвета, чем корпус вокруг;
# блик на стекле кабины - не огонь), координаты - центр пятна, цвет - его средний цвет.
# У такого корабля светятся ТОЛЬКО эти места: вид blink, цвет - свой, осветлённый.
PAINTED = {
    35: [(15.5, 10.1, "#931a1a"), (5.2, 24.2, "#9c2020"), (25.8, 24.2, "#a42525")],
    55: [(10.5, 26.5, "#e8a800"), (20.5, 26.5, "#e8a800")],
    57: [(9.5, 30.5, "#28600c"), (22.5, 30.5, "#28600c")],
    58: [(12.0, 17.0, "#a02222"), (19.0, 17.0, "#a02222"), (12.5, 23.5, "#9c2020"), (18.5, 23.5, "#9c2020")],
    60: [(7.5, 20.2, "#c46b4d"), (20.5, 20.2, "#b45d44"), (4.5, 27.0, "#c64141"), (23.5, 26.0, "#d85050")],
    61: [(11.5, 32.5, "#901818"), (17.5, 32.5, "#901818")],
    155: [(27.5, 20.5, "#806050"), (3.6, 21.1, "#806050")],
    156: [(14.5, 6.0, "#c03e3e"), (7.1, 25.4, "#a22525"), (23.0, 25.5, "#a02424"), (15.0, 32.5, "#a82a2a")],
    157: [(6.5, 28.5, "#f06868"), (22.5, 28.5, "#d85050")],
    160: [(9.5, 1.5, "#8c3c10"), (21.5, 1.5, "#8c3c10")],
    161: [(15.0, 12.0, "#8e1717")],
    177: [(15.5, 13.5, "#fcd000")],
    179: [(12.0, 18.5, "#9c3800"), (18.2, 18.8, "#aa6849"), (8.5, 32.5, "#842000"), (21.5, 32.5, "#842000")],
    184: [(11.0, 9.0, "#e2c484")],
    203: [(15.3, 6.1, "#5a84bf")],
    204: [(11.5, 10.5, "#fcfcfc")],
    209: [(13.0, 8.5, "#fcfcfc"), (18.0, 8.5, "#fcfcfc")],
    233: [(15.5, 19.5, "#b43030")],
    235: [(7.9, 20.3, "#68944d"), (20.0, 20.5, "#709c34"), (4.5, 27.0, "#6e9e2a"), (23.5, 27.0, "#6e9e2a")],
    236: [(7.9, 20.3, "#945d9f"), (20.0, 20.5, "#8a66b8"), (4.5, 27.0, "#7f5aac"), (23.5, 27.0, "#7f5aac")],
    243: [(10.5, 26.0, "#fcbaba"), (20.5, 26.0, "#fcbaba")],
    279: [(14.3, 11.9, "#b83434")],
    1289: [(10.5, 11.5, "#cc4444"), (21.5, 11.5, "#cc4444")],
}


def glow_color(hexc):
    """Цвет пятна -> цвет свечения: тот же тон, насыщенность не ниже 0.8, яркость полная
    (краска тёмная и бледная, огонь нет). Белое пятно остаётся белым."""
    import colorsys
    r, g, b = (int(hexc[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s > 0.2:
        s = max(s, 0.8)
    r, g, b = colorsys.hsv_to_rgb(h, s, 1.0)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def craft_frames(mod_dir):
    """[(имя, кадр)] всех кораблей из рулсетов мода: sprite + 33 и скины."""
    out = []
    rules = os.path.join(mod_dir, "Ruleset")
    for name in sorted(os.listdir(rules)):
        if not name.lower().endswith(".rul"):
            continue
        text = open(os.path.join(rules, name), encoding="utf-8", errors="replace").read()
        m = re.search(r"\ncrafts:\n", text)
        if not m:
            continue
        end = re.search(r"\n[a-zA-Z]", text[m.end():])
        block = text[m.end(): m.end() + end.start()] if end else text[m.end():]
        for c in re.finditer(r"(?:^|\n)  - type: (\S+)(.*?)(?=\n  - type: |\Z)", block, re.S):
            s = re.search(r"\n    sprite: (\d+)", c.group(2))
            if s:
                out.append((c.group(1), int(s.group(1)) + 33))
            skins = re.search(r"\n    skinSprites: \[([^\]]*)\]", c.group(2))
            if skins:
                for v in skins.group(1).split(","):
                    if v.strip().isdigit():
                        out.append((c.group(1) + "_skin", int(v) + 33))
    seen, uniq = set(), []
    for n, i in out:
        if i not in seen:
            seen.add(i)
            uniq.append((n, i))
    return uniq


def load_frame(frame, sprites):
    """(индексы, палитра) картинки корабля так, как её видит игра, или None.
    Картинка мода: прозрачный индекс из tRNS обнуляется, как в Surface::FixTransparent
    (у X35 и МиГа фон - индекс 127 и 255, без этого весь кадр считался корпусом).
    Кадра нет в моде, но он из ванильного набора (33-37) - берётся из BASEBITS.PCK UFO."""
    png = sprites.get(frame)
    if png and os.path.exists(png):
        im = Image.open(png)
        if im.mode != "P":
            return None
        idx = np.array(im)
        trans = im.info.get("transparency")
        if isinstance(trans, int) and trans != 0:
            idx = np.where(idx == trans, 0, idx).astype(np.uint8)
        raw = im.getpalette()[:768]
        pal = np.array(raw + [0] * (768 - len(raw)), np.uint8).reshape(-1, 3)
        return idx, pal
    from xcom_sprites import read_pck, load_palette
    frames = read_pck(VANILLA_PCK)
    if frame < len(frames) and frames[frame] is not None:
        idx = np.array(frames[frame], np.uint8)
        pal = np.array(load_palette(VANILLA_PAL, PAL_BASESCAPE), np.uint8).reshape(-1, 3)
        return idx, pal
    return None


def body_mask(idx, pal):
    """Силуэт без тени: тень - тёмно-серая кромка справа и снизу, снимаем её слоями (до 3)."""
    rgb = pal[idx].astype(np.int32)
    gray = (np.abs(rgb[..., 0] - rgb[..., 1]) < 12) & (np.abs(rgb[..., 1] - rgb[..., 2]) < 12) & (rgb.sum(-1) < 3 * 130)
    body = idx != 0
    for _ in range(3):
        right = np.zeros_like(body)
        right[:, :-1] = ~body[:, 1:]
        right[:, -1] = True
        down = np.zeros_like(body)
        down[:-1, :] = ~body[1:, :]
        down[-1, :] = True
        rim = body & gray & (right | down)
        if not rim.any():
            break
        body = body & ~rim
    return body


def place(idx, pal, frame=None):
    """Огни по силуэту: [(x, y, вид)] в пикселях кадра (центр пикселя = .5).
    Если огни на картинке уже нарисованы (PAINTED) - только они, вид 'blink #цвет'."""
    if frame in PAINTED:
        return [(x, y, "blink " + glow_color(c)) for x, y, c in PAINTED[frame]]
    body = body_mask(idx, pal)
    ys, xs = np.nonzero(body)
    if len(xs) < 12:
        return []
    xl, xr = xs.min(), xs.max()
    # середина столбца, но на самом корпусе: у лопастей вертолёта столбец рваный,
    # и медиана попадает в пустоту между пикселями (огонь висел в воздухе)
    def on_column(x):
        col = ys[xs == x]
        return int(col[np.argmin(np.abs(col - np.median(col)))])
    yl = on_column(xl)
    yr = on_column(xr)
    cx = (xl + xr) / 2.0
    yb = ys.max()
    row = np.nonzero(body[yb])[0]
    xb = row[np.argmin(np.abs(row - cx))]
    my, mx = ys.mean(), xs.mean()
    lights = []
    if xr - xl >= 8:
        lights.append((xl + 0.5, yl + 0.5, "red"))
        lights.append((xr + 0.5, yr + 0.5, "green"))
    lights.append((xb + 0.5, yb + 0.5, "strobe"))
    by = int(round(my)) - 2
    col = np.nonzero(body[:, int(round(mx))])[0]
    if len(col):
        by = int(col[np.argmin(np.abs(col - by))])
    lights.append((round(mx) + 0.5, by + 0.5, "beacon"))
    return lights


def write_lights(path, name, lights):
    with open(path, "w", encoding=ENC_W, newline="\n") as f:
        f.write("# %s - gen_craft_lights.py; x y kind [period s] [offset s]\n" % name)
        for x, y, kind in lights:
            f.write("%5.1f %5.1f  %s\n" % (x, y, kind))


def read_lights(path):
    out = []
    for line in open(path, encoding="utf-8-sig"):
        # комментарий - '#' в начале строки или '# ' с пробелом; '#rrggbb' - цвет огня
        line = re.split(r"^\s*#|#(?=\s|$)", line, maxsplit=1)[0].split()
        if len(line) >= 3:
            kind = line[2]
            colour = [t for t in line[3:] if t.startswith("#")]
            out.append((float(line[0]), float(line[1]), kind + (" " + colour[0] if colour else "")))
    return out


# --- превью: те же формулы, что в HdCraftLights.cpp
COLORS = {"red": (1.0, 0.12, 0.08), "green": (0.10, 1.0, 0.30), "white": (1, 1, 1),
          "strobe": (1, 1, 1), "beacon": (1.0, 0.10, 0.05)}
PERIOD = {"strobe": 1.3, "beacon": 1.0, "blink": 1.2}


def kind_color(kind):
    """'blink #ffc0a0' -> ('blink', (1, .75, .63)); без цвета - цвет вида."""
    parts = kind.split()
    if len(parts) > 1 and parts[1].startswith("#"):
        h = parts[1]
        return parts[0], tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    return parts[0], COLORS.get(parts[0], (1, 1, 1))


def intensity(kind, t):
    if kind in ("red", "green", "white"):
        return 1.0
    p = PERIOD[kind]
    phase = (t % p) / p
    if kind == "strobe":
        ms = phase * p * 1000.0
        return 1.0 if ms < 60 or 160 <= ms < 220 else 0.0
    s = math.sin(phase * 2 * math.pi)
    return s * s if s > 0 else 0.0


def glow(img, cx, cy, k, rgb, amount, own=False):
    """Стоковый огонь складывается с картинкой (белая сердцевина). Огонь со своим цветом
    (own) картинку ПЕРЕКРЫВАЕТ: пиксель тянется к цвету огня, иначе на светлом корпусе
    сложение упирается в 255 и любой цвет выходит белым."""
    h, w, _ = img.shape
    halo, core = 1.4 * k, 0.45 * k
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d2 = (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2
    hh = amount * np.exp(-d2 / (halo * halo))
    cc = amount * np.exp(-d2 / (core * core))
    if own:
        a = np.minimum(0.85 * hh + cc, 1.0)
        for c in range(3):
            img[..., c] = img[..., c] * (1 - a) + 255.0 * rgb[c] * a
        return
    for c in range(3):
        img[..., c] = np.minimum(img[..., c] + 255.0 * (rgb[c] * hh + cc), 255.0)


def preview(path, items, k=4, fps=25, seconds=2.6):
    cols = 8
    cw, ch = 32 * k + 8, 40 * k + 8
    rows = (len(items) + cols - 1) // cols
    base = np.zeros((rows * ch, cols * cw, 3), np.float32) + 22
    tiles = []
    for n, (idx, pal, lights) in enumerate(items):
        rgb = pal[idx].astype(np.float32)
        a = idx != 0
        big = np.repeat(np.repeat(rgb, k, 0), k, 1)
        am = np.repeat(np.repeat(a, k, 0), k, 1)
        x0, y0 = (n % cols) * cw + 4, (n // cols) * ch + 4
        hh, ww = idx.shape[:2]
        sub = base[y0:y0 + min(hh, 40) * k, x0:x0 + min(ww, 32) * k]
        sub[am[:sub.shape[0], :sub.shape[1]]] = big[:sub.shape[0], :sub.shape[1]][am[:sub.shape[0], :sub.shape[1]]]
        tiles.append((x0, y0, lights, n))
    frames = []
    for f in range(int(fps * seconds)):
        t = f / fps
        img = base.copy()
        for x0, y0, lights, n in tiles:
            sub = img[y0:y0 + 40 * k, x0:x0 + 32 * k]
            tt = t + (n * 7 % 997) * 0.0371
            for x, y, kind in lights:
                own = "#" in kind
                kind, rgb = kind_color(kind)
                amt = intensity(kind, tt)
                if amt > 0:
                    glow(sub, x * k, y * k, k, rgb, amt, own)
        frames.append(Image.fromarray(img.astype(np.uint8)))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0)


def main():
    ap = argparse.ArgumentParser(description="огни кораблей в ангаре")
    ap.add_argument("--src", required=True, help="папка мода со спрайтами и рулсетами кораблей")
    ap.add_argument("--out", required=True, help="папка мода hd")
    ap.add_argument("--only", default="", help="кадры через запятую (по умолчанию все корабли)")
    ap.add_argument("--force", action="store_true", help="перезаписать готовые .lights.txt")
    ap.add_argument("--preview", default="", help="GIF со всеми кораблями и огнями")
    args = ap.parse_args()

    sprites = basebits_map(args.src)
    dest = os.path.join(args.out, "hd", "BASEBITS.PCK")
    os.makedirs(dest, exist_ok=True)
    only = {int(v) for v in args.only.split(",") if v.strip()}
    items, written, kept = [], 0, 0
    for name, frame in craft_frames(args.src):
        if frame in SKIP or (only and frame not in only):
            continue
        loaded = load_frame(frame, sprites)
        if loaded is None:
            continue
        idx, pal = loaded
        path = os.path.join(dest, "%d.lights.txt" % frame)
        if os.path.exists(path) and not args.force:
            lights = read_lights(path)
            kept += 1
        else:
            lights = place(idx, pal, frame)
            if not lights:
                continue
            write_lights(path, name, lights)
            written += 1
        items.append((idx, pal, lights))
        print("%-26s кадр %4d: %d огней" % (name, frame, len(lights)))
    print("записано %d, оставлено как было %d -> %s" % (written, kept, dest))
    if args.preview and items:
        preview(args.preview, items)
        print("превью:", args.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
