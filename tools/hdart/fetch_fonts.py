#!/usr/bin/env python3
r"""Наборы шрифтов HD-интерфейса: скачать, свести к двум начертаниям, положить в мод.

Движок берёт шрифты из hd/UI/fonts: <Имя>-Big.ttf рисует крупный текст, <Имя>-Small.ttf
мелкий; опция oxceHdUiFont переключает наборы прямо в игре. Здесь только подготовка
файлов: переменные шрифты Google Fonts инстанцируются в вес 400 и 700 (у переменного
шрифта stb_truetype видит лишь начертание по умолчанию, поэтому жирный нужен отдельным
файлом), затем подрезаются до знаков, которые вообще встречаются в интерфейсе.

    py -3.13 tools\hdart\fetch_fonts.py                 - в user\mods\hd
    py -3.13 tools\hdart\fetch_fonts.py --dest <корень мода в установке игры>
    py -3.13 tools\hdart\fetch_fonts.py --check         - только покрытие знаков модов

Запускать для обеих копий мода hd (R-087). Кроме наборов кладёт Roboto (FontBig/FontSmall), DejaVu Sans
(FontFallback) и тексты лицензий: <набор>-OFL.txt у каждого семейства свой, ROBOTO-LICENSE.txt (Apache 2.0),
FONTS-LICENSE.txt (DejaVu), FONTS-SOURCES.txt - откуда взят каждый файл и что с ним сделано (docs/portal/HD_FONTS.md).
Источники закреплены: коммит google/fonts и SHA-256 каждого скачанного файла; не совпало - остановка.

Нужен fonttools: py -3.13 -m pip install fonttools brotli
"""
import argparse
import hashlib
import io
import os
import re
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import common

if hasattr(sys.stdout, "reconfigure"):   # консоль msys бывает cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ENC_W = "utf-8-sig"

RAW = "https://raw.githubusercontent.com/google/fonts/%s/ofl/%s/%s"

# Что качаем: имя набора, папка в google/fonts, коммит, исходники с SHA-256, веса, описание, переименование.
# weights: (обычный, жирный) для переменного шрифта, None у статических пар. Коммит - последний, что трогал
# папку семейства до сборки 21.09.2026: файлы мода пересобираются из него байт в байт (кроме метки времени head).
# rename: (зарезервированные имена из OFL.txt, новое имя). OFL 1.1 п. 3: изменённую версию (подрезка, вес
# из переменного - изменение, OFL FAQ 2.6) нельзя называть зарезервированным именем - ни в файле, ни в игре.
# copyright: строка авторов, если у семейства в google/fonts нет OFL.txt (M+: только METADATA.pb).
# Все наборы под OFL и все с кириллицей - покрытие проверяется тут же, при сборке.
FAMILIES = [
    dict(set="Curvy", folder="comfortaa", commit="db64f6bde4ced22493138096badb4fe2f7f8f7a0",
         sources={"Comfortaa[wght].ttf": "0fc3f45dc48b614db9c39181502544b37217ecbf8bee2fb35886992bc96c5bd3"},
         weights=(400, 700), about="самый круглый, мягкий геометрический (Comfortaa)",
         rename=(["Comfortaa"], "Curvy"), was="Comfortaa"),
    dict(set="Exo2", folder="exo2", commit="1796e34455b893092713d206e7f23e3e07699f00",
         sources={"Exo2[wght].ttf": "205a448676a2586f9c57c25f3d5c58ca8db7e6cf5edf7506783a010c6fe2bfb5"},
         weights=(400, 700), about="техно со скруглениями, ближе всего к оригиналу X-COM"),
    dict(set="Jura", folder="jura", commit="6e4b84c976cadb3c49a40fd9a1c203e4f7fcf2da",
         sources={"Jura[wght].ttf": "188b415d44810d68b4d6b4a8c281f864184c2b8edc5e88e6357c89f7b44075bf"},
         weights=(400, 700), about="узкий техно, влезает в тесные колонки"),
    dict(set="MPlusRounded", folder="mplusrounded1c", commit="84efd8ad78c3710ad14bd909e3bc407151885628",
         sources={"MPLUSRounded1c-Regular.ttf": "b75708b53e45b06d17d470aeeca5b766e3d1b3999f03f13ec4eb863ca846c14c",
                  "MPLUSRounded1c-Bold.ttf": "c358630584e8e2d8fbd6121d0f4693255ffef6d1e6d4f3441fd6e5a963a11f9e"},
         weights=None, about="круглые окончания штрихов",
         copyright="Copyright 2016 The Rounded M+ Project Authors."),
    dict(set="Pulse", folder="play", commit="51c6a423fbfbd78a5111241dfd07791644b4c5c6",
         sources={"Play-Regular.ttf": "eed0da79005cab35d6ed0eacab594ed67cc643be0b2632fa9e440b3bc5078dc4",
                  "Play-Bold.ttf": "45c572eccda4cf335165b750345258e753035bf48ee2fdf37faa07c7db88bce0"},
         weights=None, about="техно-гротеск, плотный (Play)",
         rename=(["Playtype Sans", "Playtype", "Play"], "Pulse"), was="Play"),
    dict(set="Rubik", folder="rubik", commit="8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5",
         sources={"Rubik[wght].ttf": "1b3a7437ba2af80e465e773ed60c5036d1ba6ace492d89046dbcf18fb31e4e88"},
         weights=(400, 700), about="гротеск со скруглёнными углами"),
    dict(set="Unbounded", folder="unbounded", commit="8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5",
         sources={"Unbounded[wght].ttf": "323b511be380c8d474ef030686b71aedde501f8d9cd46da558b7c40454372c3f"},
         weights=(400, 700), about="широкий геометрический, круглые О"),
]
# Имя набора - основа имени файла, а опция oxceHdUiFont - номер набора по алфавиту (HdUi::scanFontSets).
# Новые имена стоят на тех же местах, что прежние (Comfortaa -> Curvy, Play -> Pulse), выбор игрока не съезжает.

# Поля таблицы name, которые называют шрифт: в них не должно остаться зарезервированного имени.
# Остальные (0 copyright, 7 trademark, 8-12 авторы и ссылки, 13-14 лицензия) - атрибуция, их не трогаем.
NAMING_IDS = (1, 3, 4, 6, 16, 17, 18, 20, 21, 25)

# Неизменённые файлы: Roboto 2.138 (Apache 2.0) и DejaVu Sans 2.37 (лицензия Bitstream Vera). Путь в архиве,
# куда в моде, SHA-256 файла. Шрифты в моде - эти файлы байт в байт (сверено 02.10.2026, HD_FONTS.md).
ARCHIVES = [
    dict(name="Roboto 2.138", license="Apache License 2.0",
         url="https://github.com/googlefonts/roboto-2/releases/download/v2.138/roboto-android.zip",
         sha="c825453253f590cfe62557733e7173f9a421fff103b00f57d33c4ad28ae53baf",
         files=[("Roboto-Medium.ttf", "hd/UI/FontBig.ttf", "7984aafeaf43"),
                ("Roboto-Regular.ttf", "hd/UI/FontSmall.ttf", "797e35f7f5d6"),
                ("LICENSE", "ROBOTO-LICENSE.txt", "c71d239df917")]),
    dict(name="DejaVu Sans 2.37", license="Bitstream Vera Fonts license (DejaVu changes are in the public domain)",
         url="https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.tar.bz2",
         sha="fa9ca4d13871dd122f61258a80d01751d603b4d3ee14095d65453b4e846e17d7",
         files=[("dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf", "hd/UI/FontFallback.ttf", "7da195a74c55"),
                ("dejavu-fonts-ttf-2.37/LICENSE", "FONTS-LICENSE.txt", "7a083b136e64")]),
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


def sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def download(url, dst, sha=None):
    """Качает файл один раз, дальше берёт из кэша; с sha - сверяет и в кэше, и после загрузки."""
    if not (os.path.exists(dst) and (sha is None or sha256(dst) == sha)):
        print("  качаю %s" % url)
        urllib.request.urlretrieve(url, dst + ".part")
        os.replace(dst + ".part", dst)
    if sha is not None and sha256(dst) != sha:
        sys.exit("%s: SHA-256 %s, а закреплён %s - источник сменился, сверить и закрепить заново" % (url, sha256(dst), sha))
    return dst


def fetch(fam, name, sha=None):
    """Файл семейства из google/fonts на закреплённом коммите.
    Ключ кэша - коммит, папка семейства и имя: OFL.txt у каждого семейства свой (раньше все брали первый - Comfortaa)."""
    dst = os.path.join(cache_dir(), "%s__%s__%s" % (fam["commit"][:12], fam["folder"], name.replace("[", "_").replace("]", "")))
    return download(RAW % (fam["commit"], fam["folder"], urllib.parse.quote(name)), dst, sha)


def ofl_text(fam):
    """OFL.txt семейства. У M+ в google/fonts его нет: строка авторов из METADATA.pb (copyright в FAMILIES)
    и текст OFL 1.1 с первой строки после авторов, взятый у другого семейства."""
    try:
        path = fetch(fam, "OFL.txt")
    except urllib.error.HTTPError as error:
        if error.code != 404 or "copyright" not in fam:
            raise
        body = io.open(fetch(FAMILIES[1], "OFL.txt"), encoding="utf-8").read()
        start = body.index("This Font Software is licensed")
        return fam["copyright"] + "\n\n" + body[start:]
    return io.open(path, encoding="utf-8").read()


def rename_face(font, reserved, new):
    """Зарезервированное имя -> новое в полях, которые называют шрифт (OFL 1.1 п. 3). Проверяет, что не осталось."""
    rx = re.compile("|".join(re.escape(name) for name in reserved), re.I)
    for record in font["name"].names:
        if record.nameID in NAMING_IDS:
            record.string = rx.sub(new, record.toUnicode())
    left = [(record.nameID, record.toUnicode()) for record in font["name"].names
            if record.nameID in NAMING_IDS and rx.search(record.toUnicode())]
    if left:
        sys.exit("зарезервированное имя осталось: %r" % left)


def same_font(a, b):
    """Те же таблицы байт в байт; у head без метки сохранения (fontTools пишет время записи)."""
    from fontTools.ttLib import TTFont
    fa, fb = TTFont(a), TTFont(b)
    try:
        if sorted(fa.keys()) != sorted(fb.keys()):
            return False
        fb["head"].modified = fa["head"].modified
        fb["head"].checkSumAdjustment = fa["head"].checkSumAdjustment
        return all(fa.getTableData(tag) == fb.getTableData(tag) for tag in fa.keys() if tag not in ("GlyphOrder", "head")) \
            and fa["head"].compile(fa) == fb["head"].compile(fb)
    finally:
        fa.close()
        fb.close()


def put(dst, data=None, font=None):
    """Запись через временный файл и замену имени: жёсткие ссылки раскладок (hd_layout) на прежний файл
    остаются на прежнем содержимом, а не меняются вместе с модом. Метка времени head остаётся от исходника
    (recalcTimestamp выключен): сборка воспроизводима байт в байт, обе копии мода и SHA-256 в FONTS-SOURCES
    совпадают. Прежний файл, отличный только меткой, переписывается один раз с пометкой 'метка времени'.
    Возвращает 'новый', 'тот же' или 'метка времени'."""
    tmp = dst + ".tmp"
    if font is not None:
        font.recalcTimestamp = False
        font.save(tmp)
        with open(tmp, "rb") as handle:
            data = handle.read()
    if os.path.exists(dst):
        with open(dst, "rb") as handle:
            if handle.read() == data:
                if font is not None:
                    os.remove(tmp)
                return "тот же"
    if font is None:
        with open(tmp, "wb") as handle:
            handle.write(data)
    state = "метка времени" if font is not None and os.path.exists(dst) and same_font(dst, tmp) else "новый"
    os.replace(tmp, dst)
    return state


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

    for name in ["FontBig.ttf"] + ["%s-Big.ttf" % fam["set"] for fam in FAMILIES]:
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
    texts = args.texts if args.texts else ["bin", common.INSTALL]
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

    from fontTools.ttLib import TTFont
    notes = ["Fonts of the HD interface: where each file comes from and what was done to it.",
             "Written by tools/hdart/fetch_fonts.py; every source is pinned by commit or release and SHA-256.", ""]

    # неизменённые: Roboto и DejaVu из архивов выпуска, тексты их лицензий оттуда же
    for arc in ARCHIVES:
        print(arc["name"])
        path = download(arc["url"], os.path.join(cache_dir(), os.path.basename(arc["url"])), arc["sha"])
        for member, rel, pin in arc["files"]:
            if path.endswith(".zip"):
                with zipfile.ZipFile(path) as archive:
                    data = archive.read(member)
            else:
                with tarfile.open(path) as archive:
                    data = archive.extractfile(member).read()
            digest = hashlib.sha256(data).hexdigest()
            if not digest.startswith(pin):
                sys.exit("%s в %s: SHA-256 %s, ожидался %s..." % (member, arc["url"], digest, pin))
            dst = os.path.join(args.dest, *rel.split("/"))
            print("  %-26s %s" % (rel, put(dst, data=data)))
            if rel.endswith(".ttf"):
                notes += [rel, "  %s, unmodified (SHA-256 %s)" % (arc["name"], digest),
                          "  from %s (SHA-256 %s), file %s" % (arc["url"], arc["sha"], member),
                          "  licence: %s - %s" % (arc["license"], arc["files"][-1][1]), ""]

    for fam in FAMILIES:
        setname = fam["set"]
        print("%s - %s" % (setname, fam["about"]))
        names = list(fam["sources"])
        if fam["weights"] is None:
            faces = [(fetch(fam, names[0], fam["sources"][names[0]]), None, "Small"),
                     (fetch(fam, names[1], fam["sources"][names[1]]), None, "Big")]
        else:
            src = fetch(fam, names[0], fam["sources"][names[0]])
            faces = [(src, fam["weights"][0], "Small"), (src, fam["weights"][1], "Big")]
        source = TTFont(faces[0][0], lazy=True)
        version = "%s %s" % (face_name(source), str(source["name"].getName(5, 3, 1, 0x409)).replace("Version ", ""))
        source.close()
        shown = ""
        built = []
        for src, weight, role in faces:
            font = build_face(src, weight, keep)
            if "rename" in fam:
                rename_face(font, *fam["rename"])
            shown = shown or face_name(font)
            dst = os.path.join(out, "%s-%s.ttf" % (setname, role))
            state = put(dst, font=font)
            font.close()
            built.append("%s-%s.ttf" % (setname, role))
            print("  %-6s %-28s %6.0f КБ  %s" % (role, os.path.basename(dst), os.path.getsize(dst) / 1024.0, state))
        print("  %-6s %-28s %s" % ("OFL", setname + "-OFL.txt",
                                    put(os.path.join(out, setname + "-OFL.txt"), data=ofl_text(fam).encode(ENC_W))))
        # прежние файлы под зарезервированным именем - вон, иначе движок покажет их отдельным набором
        for role in ("Big", "Small", "OFL"):
            old = os.path.join(out, "%s-%s.%s" % (fam.get("was"), role, "txt" if role == "OFL" else "ttf"))
            if fam.get("was") and os.path.exists(old):
                os.remove(old)
                print("  убран прежний %s" % os.path.basename(old))
        done = "weight %d / %d instanced from the variable font, " % fam["weights"] if fam["weights"] else ""
        if "rename" in fam:
            done += "renamed \"%s\" (Reserved Font Name %s, OFL 1.1 clause 3), " % (
                fam["rename"][1], ", ".join('"%s"' % name for name in fam["rename"][0]))
        notes += [", ".join("hd/UI/fonts/" + name for name in built),
                  "  %s, modified: %sglyphs reduced to Latin, Greek, Cyrillic and symbols" % (version, done),
                  "  SHA-256 " + ", ".join(sha256(os.path.join(out, name))[:12] for name in built)]
        for name, sha in fam["sources"].items():
            notes.append("  from https://github.com/google/fonts/blob/%s/ofl/%s/%s (SHA-256 %s)" % (
                fam["commit"], fam["folder"], urllib.parse.quote(name), sha))
        notes += ["  licence: SIL Open Font License 1.1 - hd/UI/fonts/%s-OFL.txt" % setname
                  + (" (copyright line from METADATA.pb: google/fonts has no OFL.txt for this family)"
                     if "copyright" in fam else ""), ""]
        missing = coverage(os.path.join(out, "%s-Big.ttf" % setname), codes, fallback)
        print("  игра зовёт его %s, нет %d знаков из текстов%s" % (
            shown or setname, len(missing),
            (": " + " ".join("U+%04X" % c for c in missing[:10])) if missing else ""))
    print("FONTS-SOURCES.txt", put(os.path.join(args.dest, "FONTS-SOURCES.txt"), data="\n".join(notes).encode(ENC_W)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
