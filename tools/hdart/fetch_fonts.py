#!/usr/bin/env python3
r"""Наборы шрифтов HD-интерфейса: скачать, свести к двум начертаниям, положить в мод.

Движок берёт шрифты из hd/UI/fonts: <Имя>-Big.ttf рисует крупный текст, <Имя>-Small.ttf
мелкий; опция oxceHdUiFont переключает наборы прямо в игре. Здесь только подготовка
файлов: переменные шрифты Google Fonts инстанцируются в вес 400 и 700 (у переменного
шрифта stb_truetype видит лишь начертание по умолчанию, поэтому жирный нужен отдельным
файлом), затем подрезаются до знаков, которые вообще встречаются в интерфейсе.

    py -3 tools\hdart\fetch_fonts.py                 - в user\mods\hd
    py -3 tools\hdart\fetch_fonts.py --dest <корень мода в установке игры>
    py -3 tools\hdart\fetch_fonts.py --check         - только покрытие знаков модов

Нужен fonttools: py -3 -m pip install fonttools brotli
"""
import argparse
import io
import os
import sys
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):   # консоль msys бывает cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ENC_W = "utf-8-sig"

RAW = "https://raw.githubusercontent.com/google/fonts/main/ofl/"

# Что качаем. weights: (обычный, жирный) для переменного шрифта, None у статических пар.
# Все наборы под OFL и все с кириллицей - покрытие проверяется тут же, при сборке.
FAMILIES = [
    ("Comfortaa", "comfortaa", ["Comfortaa[wght].ttf"], (400, 700),
     "самый круглый, мягкий геометрический"),
    ("Exo2", "exo2", ["Exo2[wght].ttf"], (400, 700),
     "техно со скруглениями, ближе всего к оригиналу X-COM"),
    ("Jura", "jura", ["Jura[wght].ttf"], (400, 700),
     "узкий техно, влезает в тесные колонки"),
    ("MPlusRounded", "mplusrounded1c", ["MPLUSRounded1c-Regular.ttf", "MPLUSRounded1c-Bold.ttf"], None,
     "круглые окончания штрихов"),
    ("Play", "play", ["Play-Regular.ttf", "Play-Bold.ttf"], None,
     "техно-гротеск, плотный"),
    ("Rubik", "rubik", ["Rubik[wght].ttf"], (400, 700),
     "гротеск со скруглёнными углами"),
    ("Unbounded", "unbounded", ["Unbounded[wght].ttf"], (400, 700),
     "широкий геометрический, круглые О"),
]

# Знаки, которые остаются после подрезки: латиница с расширениями, греческий, кириллица,
# типографика, валюты, стрелки, геометрия и карточные масти (в текстах Пираток есть червы).
KEEP = [
    (0x0000, 0x024F), (0x0370, 0x03FF), (0x0400, 0x052F), (0x1E00, 0x1EFF),
    (0x2000, 0x206F), (0x20A0, 0x20CF), (0x2100, 0x214F), (0x2190, 0x21FF),
    (0x2200, 0x22FF), (0x2500, 0x257F), (0x2580, 0x259F), (0x25A0, 0x25FF),
    (0x2600, 0x26FF), (0x2700, 0x27BF), (0xFB00, 0xFB06),
]


def cache_dir():
    base = os.environ.get("TEMP") or os.environ.get("TMP") or "."
    path = os.path.join(base, "oxce-hd-fonts")
    os.makedirs(path, exist_ok=True)
    return path


def fetch(folder, name):
    """Качает файл из google/fonts один раз, дальше берёт из кэша."""
    dst = os.path.join(cache_dir(), name.replace("[", "_").replace("]", ""))
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        return dst
    url = RAW + folder + "/" + urllib.parse.quote(name)
    print("  качаю %s" % name)
    urllib.request.urlretrieve(url, dst)
    return dst


def face_name(font):
    """Имя гарнитуры из самого шрифта - его же показывает игра в списке опций."""
    for nid in (16, 1):
        rec = font["name"].getName(nid, 3, 1, 0x409)
        if rec:
            return str(rec)
    return ""


def build_face(src, weight, keep_unicodes):
    """Один файл начертания: инстанцируем вес, если шрифт переменный, и подрезаем."""
    from fontTools.ttLib import TTFont
    from fontTools import subset

    font = TTFont(src)
    if weight is not None and "fvar" in font:
        from fontTools.varLib import instancer
        axes = {a.axisTag: (a.minValue, a.maxValue) for a in font["fvar"].axes}
        low, high = axes["wght"]
        font = instancer.instantiateVariableFont(
            font, {"wght": max(low, min(high, weight))}, updateFontNames=False)
    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.notdef_outline = True
    options.recalc_bounds = True
    options.drop_tables = ["DSIG"]
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=keep_unicodes)
    subsetter.subset(font)
    return font


def mod_texts(roots, langs):
    """Знаки строк интерфейса игры и модов - только тех языков, на которых играют.

    Языки со своей письменностью (японский, китайский) считать бессмысленно: их не
    покрывает ни один латинский шрифт, и классический слой рисует их своими FontBig_jp.
    """
    codes = set()
    files = 0
    for root in roots:
        for dirpath, _dirnames, filenames in os.walk(root):
            if os.path.basename(dirpath).lower() not in ("language", "languages"):
                continue
            for name in filenames:
                if not name.lower().endswith((".yml", ".yaml")):
                    continue
                if not any(name.lower().startswith(lang) for lang in langs):
                    continue
                try:
                    with io.open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as handle:
                        text = handle.read()
                except OSError:
                    continue
                files += 1
                codes.update(ord(ch) for ch in text)
    return codes, files


def font_codes(path):
    from fontTools.ttLib import TTFont
    font = TTFont(path, fontNumber=0, lazy=True)
    have = set(font.getBestCmap().keys())
    font.close()
    return have


def coverage(path, codes, fallback):
    """Каких знаков из текстов не нарисует никто: грабли R-020, такой знак молча выходит вопросом."""
    have = font_codes(path) | fallback
    # полноширинные формы движок складывает к ASCII сам (faceCode в HdFont.cpp)
    return sorted(c for c in codes if c > 0x20 and c not in have and not 0xFF01 <= c <= 0xFF5E)


def sheet(out, dest, path):
    """Лист сравнения: строка классическим шрифтом игры и та же строка каждым набором.

    Классическая строка собирается из FontBig.png так же, как её собирает движок:
    ячейка 16x16 начиная с '!', обрезанная по чернильной коробке. Это единственный
    честный способ увидеть, насколько набор попадает в характер оригинала.
    """
    from PIL import Image, ImageDraw, ImageFont

    big_png = os.path.join("bin", "common", "Language", "FontBig.png")
    cell = 16
    scale = 3
    cap = 8 * scale          # высота заглавной классического шрифта, в пикселях листа
    line_lat = "AIMED SHOT 47% BRAVERY"
    line_cyr = "ПРИЦЕЛЬНЫЙ ВЫСТРЕЛ 47%"

    rows = []
    if os.path.exists(big_png):
        # лист лежит в палитре, и прозрачное - это индекс 0, а не какой-то цвет;
        # считать фоном цвет левого верхнего пикселя нельзя, он уже раскрашен палитрой
        face = Image.open(big_png)
        if face.mode != "P":
            face = face.convert("P")
        parts = []
        for char in line_lat:
            if char == " ":
                parts.append(Image.new("L", (5, cell), 255))
                continue
            index = ord(char) - 0x21
            glyph = face.crop(((index % 16) * cell, (index // 16) * cell,
                               (index % 16) * cell + cell, (index // 16) * cell + cell))
            pixels = glyph.load()
            left, right = cell, -1
            for y in range(cell):
                for x in range(cell):
                    if pixels[x, y] != 0:
                        left = min(left, x)
                        right = max(right, x)
            if right < 0:
                parts.append(Image.new("L", (5, cell), 255))
                continue
            ink = Image.new("L", (right - left + 1, cell), 255)
            draw_pixels = ink.load()
            for y in range(cell):
                for x in range(left, right + 1):
                    if pixels[x, y] != 0:
                        draw_pixels[x - left, y] = 0
            parts.append(ink)
        strip = Image.new("L", (sum(part.width + 1 for part in parts), cell), 255)
        pen = 0
        for part in parts:
            strip.paste(part, (pen, 0))
            pen += part.width + 1
        strip = strip.convert("RGB").resize((strip.width * scale, strip.height * scale), Image.NEAREST)
        rows.append(("classic (game font)", strip))

    for name in ["FontBig.ttf"] + ["%s-Big.ttf" % family[0] for family in FAMILIES]:
        file = os.path.join(dest, "hd", "UI", name) if name == "FontBig.ttf" else os.path.join(out, name)
        if not os.path.exists(file):
            continue
        size = cap * 2.0
        for _ in range(12):     # размер, при котором заглавная ровно той же высоты
            probe = ImageFont.truetype(file, int(round(size)))
            box = probe.getbbox("H")
            if box[3] - box[1] <= 0:
                break
            size = size * cap / (box[3] - box[1])
        font = ImageFont.truetype(file, int(round(size)))
        strip = Image.new("RGB", (1000, int(cap * 3.2)), (255, 255, 255))
        draw = ImageDraw.Draw(strip)
        draw.text((0, int(cap * 1.3)), line_lat, font=font, fill=(0, 0, 0), anchor="ls")
        draw.text((0, int(cap * 2.8)), line_cyr, font=font, fill=(0, 0, 0), anchor="ls")
        from fontTools.ttLib import TTFont
        shown = face_name(TTFont(file, lazy=True))
        rows.append((shown or name, strip))

    label = 170
    board = Image.new("RGB", (label + 1010, sum(row[1].height + 12 for row in rows) + 12), (255, 255, 255))
    draw = ImageDraw.Draw(board)
    small = ImageFont.load_default()
    top = 6
    for name, strip in rows:
        draw.text((6, top + strip.height // 2 - 5), name, font=small, fill=(20, 20, 120))
        board.paste(strip, (label, top))
        top += strip.height + 12
    board.save(path)
    print("лист сравнения: %s" % path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", default=os.path.join("user", "mods", "hd"),
                        help="корень мода, куда лягут наборы")
    parser.add_argument("--check", action="store_true",
                        help="только отчёт покрытия по текстам модов")
    parser.add_argument("--sheet", default=None,
                        help="нарисовать лист сравнения с классическим шрифтом в этот PNG и выйти")
    parser.add_argument("--texts", nargs="*", default=None,
                        help="где искать Language/*.yml для проверки покрытия")
    parser.add_argument("--langs", nargs="*", default=["en-", "ru"],
                        help="начала имён языковых файлов, по которым проверять покрытие")
    args = parser.parse_args()

    out = os.path.join(args.dest, "hd", "UI", "fonts")
    texts = args.texts if args.texts else ["bin", os.path.join("Пиратки", "Dioxine_XPiratez")]
    codes, files = mod_texts([root for root in texts if os.path.isdir(root)], args.langs)
    print("знаков в текстах игры и модов (%s): %d из %d файлов" % (
        " ".join(args.langs), len(codes), files))

    # запасная гарнитура закрывает то, чего нет в основной: в отчёте это не пропажа
    spare = os.path.join(args.dest, "hd", "UI", "FontFallback.ttf")
    fallback = font_codes(spare) if os.path.exists(spare) else set()

    if args.sheet:
        sheet(out, args.dest, args.sheet)
        return 0

    if args.check:
        names = sorted(os.listdir(out)) if os.path.isdir(out) else []
        for name in names:
            if name.lower().endswith(".ttf"):
                missing = coverage(os.path.join(out, name), codes, fallback)
                print("  %-28s нет %d знаков %s" % (
                    name, len(missing), " ".join("U+%04X" % c for c in missing[:12])))
        return 0

    os.makedirs(out, exist_ok=True)
    keep = set()
    for low, high in KEEP:
        keep.update(range(low, high + 1))

    for setname, folder, sources, weights, about in FAMILIES:
        print("%s - %s" % (setname, about))
        if weights is None:
            faces = [(fetch(folder, sources[0]), None, "Small"), (fetch(folder, sources[1]), None, "Big")]
        else:
            src = fetch(folder, sources[0])
            faces = [(src, weights[0], "Small"), (src, weights[1], "Big")]
        shown = ""
        for src, weight, role in faces:
            font = build_face(src, weight, keep)
            shown = shown or face_name(font)
            dst = os.path.join(out, "%s-%s.ttf" % (setname, role))
            font.save(dst)
            font.close()
            print("  %-6s %-28s %6.0f КБ" % (role, os.path.basename(dst), os.path.getsize(dst) / 1024.0))
        with io.open(fetch(folder, "OFL.txt"), encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        with io.open(os.path.join(out, "%s-OFL.txt" % setname), "w", encoding=ENC_W) as handle:
            handle.write(text)
        missing = coverage(os.path.join(out, "%s-Big.ttf" % setname), codes, fallback)
        print("  игра зовёт его %s, нет %d знаков из текстов%s" % (
            shown or setname, len(missing),
            (": " + " ".join("U+%04X" % c for c in missing[:10])) if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
