#!/usr/bin/env python3
"""
facility_sheet.py - таблица Excel всех построек базы: название, картинка, описание.

Постройки собираются так же, как их видит игра: ванильный xcom1, поверх него рулсеты
Piratez, поверх - XPZ RU-patch (delete снимает постройку, поля мода перекрывают поля ванили).
Картинка собирается как в BaseView::draw: клетки строка за строкой, сначала форма
(spriteShape + номер клетки), поверх - картинка постройки (spriteFacility + номер), если
она включена (маленькая постройка или spriteEnabled). Кадр ищется в extraSprites
BASEBITS.PCK модов, иначе - в ванильном BASEBITS.PCK (gen_craft_lights.load_frame).

Названия и описания - из Language/*.yml: ваниль, Piratez, RU-patch; описание - текст статьи
педии, у которой id совпадает с постройкой (или которая ссылается на неё в requires нет -
только по id). Колонка «HD сейчас» говорит, есть ли у клетки HD-картинка и сколько фаз.

    py -3 tools/hdart/facility_sheet.py --out art/_review/base_facilities.xlsx
"""
import argparse
import io
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from gen_base import basebits_map  # noqa: E402
from gen_craft_lights import load_frame  # noqa: E402
import yaml  # noqa: E402
from pck_census import Tolerant, load_yaml  # noqa: E402


def _plain(loader, suffix, node):
    """Теги OXCE (!add, !remove, !info) - берём значение как есть."""
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


for _loader in (yaml.CSafeLoader, Tolerant):
    yaml.add_multi_constructor("!", _plain, Loader=_loader)

GAME = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez")
VANILLA = os.path.join(GAME, "standard", "xcom1")
MODS = [os.path.join(GAME, "user", "mods", m) for m in ("Piratez", "XPZ RU-patch")]
HD = os.path.join(GAME, "user", "mods", "hd", "hd", "BASEBITS.PCK")
ENC_W = "utf-8-sig"


def rul_files(folder):
    rules = os.path.join(folder, "Ruleset")
    folder = rules if os.path.isdir(rules) else folder
    return [os.path.join(folder, n) for n in sorted(os.listdir(folder)) if n.lower().endswith(".rul")]


def load_rules():
    """(постройки по type в порядке загрузки, статьи педии по id)."""
    facilities, articles = {}, {}
    files = [os.path.join(VANILLA, "facilities.rul"), os.path.join(VANILLA, "ufopaedia.rul")]
    for mod in MODS:
        files += rul_files(mod)
    for path in files:
        data = load_yaml(path) or {}
        if not isinstance(data, dict):
            continue
        for entry in data.get("facilities") or []:
            if "delete" in entry:
                facilities.pop(entry["delete"], None)
                continue
            t = entry.get("type")
            if t:
                facilities.setdefault(t, {}).update(entry)
        for entry in data.get("ufopaedia") or []:
            if "delete" in entry:
                articles.pop(entry["delete"], None)
                continue
            i = entry.get("id")
            if i:
                articles.setdefault(i, {}).update(entry)
    return facilities, articles


def load_strings(lang):
    out = {}
    paths = [os.path.join(VANILLA, "Language", lang + ".yml")]
    paths += [os.path.join(m, "Language", lang + ".yml") for m in MODS]
    for path in paths:
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8-sig", errors="replace").read()
        # в строках встречаются управляющие коды цвета (0x01..0x1F), yaml их не пропускает
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        try:
            data = yaml.load(text, Loader=yaml.CSafeLoader) or {}
        except yaml.YAMLError:
            data = yaml.load(text, Loader=Tolerant) or {}
        for v in data.values():
            if isinstance(v, dict):
                out.update({k: s for k, s in v.items() if isinstance(s, str)})
    return out


def clean(text):
    text = text.replace("{NEWLINE}", "\n").replace("{SMALLLINE}", "\n").replace("{ALT}", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def sprites_map():
    out = {}
    for mod in MODS:
        out.update(basebits_map(mod))
    return out


def picture(fac, sprites, scale):
    sx = int(fac.get("sizeX", fac.get("size", 1)))
    sy = int(fac.get("sizeY", fac.get("size", 1)))
    small = sx == 1 and sy == 1
    enabled = small or bool(fac.get("spriteEnabled", False))
    shape = int(fac.get("spriteShape", -1))
    graphic = int(fac.get("spriteFacility", -1))
    img = np.zeros((sy * 32, sx * 32, 3), np.uint8)
    img[:] = (24, 24, 28)
    missing = []
    num = 0
    for y in range(sy):
        for x in range(sx):
            layers = [shape + num] if shape >= 0 else []
            if enabled and graphic >= 0:
                layers.append(graphic + num)
            for frame in layers:
                got = load_frame(frame, sprites)
                if got is None:
                    missing.append(frame)
                    continue
                idx, pal = got
                h, w = idx.shape
                tile = img[y * 32:y * 32 + min(h, 32), x * 32:x * 32 + min(w, 32)]
                part = idx[:tile.shape[0], :tile.shape[1]]
                mask = part != 0
                tile[mask] = pal[part][mask]
            num += 1
    # все картинки в одну клетку box x box: 1x1 увеличивается, большие уменьшаются
    im = Image.fromarray(img)
    k = scale / float(max(im.width, im.height))
    size = (max(1, round(im.width * k)), max(1, round(im.height * k)))
    whole = size[0] % im.width == 0 and size[1] % im.height == 0
    im = im.resize(size, Image.NEAREST if whole else Image.LANCZOS)
    hd_index = graphic if enabled else shape
    return im, (sx, sy), enabled, hd_index, missing


def hd_state(first, tiles):
    phases = []
    for n in range(tiles):
        idx = first + n
        if not os.path.exists(os.path.join(HD, "%d.png" % idx)):
            phases.append(0)
            continue
        p = 1
        while os.path.exists(os.path.join(HD, "%d.v%d.png" % (idx, p))):
            p += 1
        phases.append(p)
    if not any(phases):
        return "нет"
    if max(phases) > 1:
        return "анимация, %d фаз" % max(phases)
    return "HD-картинка без анимации"


def main():
    ap = argparse.ArgumentParser(description="таблица построек базы")
    ap.add_argument("--out", default=os.path.join(ROOT, "art", "_review", "base_facilities.xlsx"))
    ap.add_argument("--pic", type=int, default=96, help="сторона картинки в пикселях, одна на все постройки")
    ap.add_argument("--ideas", help="TSV 'код<TAB>идея анимации' - заполняет колонку идей")
    args = ap.parse_args()

    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XlImage
    from openpyxl.styles import Alignment, Font, PatternFill

    facilities, articles = load_rules()
    ru, en = load_strings("ru"), load_strings("en-US")
    sprites = sprites_map()
    ideas = {}
    if args.ideas:
        for line in open(args.ideas, encoding=ENC_W):
            if "\t" in line:
                k, v = line.rstrip("\n").split("\t", 1)
                ideas[k.strip()] = v.strip()

    rows = sorted(facilities.values(), key=lambda f: (int(f.get("listOrder", 0)), f["type"]))
    wb = Workbook()
    ws = wb.active
    ws.title = "Постройки"
    head = ["№", "Название", "Картинка", "Идея анимации", "Name (EN)", "Размер",
            "Описание (педия)", "Код", "Кадры BASEBITS", "HD сейчас"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="3A3A48")
        c.alignment = Alignment(vertical="center", wrap_text=True)
    widths = [5, 24, args.pic / 7.0 + 2, 60, 22, 7, 80, 28, 18, 18]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = "D2"

    tmp = os.path.join(os.path.dirname(os.path.abspath(args.out)), "_facility_pics")
    os.makedirs(tmp, exist_ok=True)
    no_text = []
    for n, fac in enumerate(rows, 1):
        t = fac["type"]
        im, (sx, sy), enabled, hd_index, missing = picture(fac, sprites, args.pic)
        art = articles.get(t, {})
        key = art.get("text") or (t + "_UFOPEDIA")
        desc = clean(ru.get(key) or en.get(key) or "")
        if not desc:
            no_text.append(t)
        frames = "форма %s" % fac.get("spriteShape", "-")
        if enabled:
            frames += ", картинка %s" % fac.get("spriteFacility", "-")
        if missing:
            frames += "\nнет кадров: %s" % ", ".join(map(str, missing))
        r = n + 1
        ws.append([n, clean(ru.get(t, t)), None, ideas.get(t, ""), clean(en.get(t, t)), "%dx%d" % (sx, sy), desc,
                   t, frames, hd_state(hd_index, sx * sy) if hd_index >= 0 else "нет"])
        path = os.path.join(tmp, "%03d.png" % n)
        im.save(path)
        xl = XlImage(path)
        ws.add_image(xl, "C%d" % r)
        ws.row_dimensions[r].height = args.pic * 0.75 + 6
        for c in ws[r]:
            c.alignment = Alignment(vertical="top", wrap_text=True)
        ws.cell(r, 4).fill = PatternFill("solid", fgColor="FFF6D5")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    wb.save(args.out)
    print("построек: %d -> %s" % (len(rows), args.out))
    if args.ideas:
        lost = [f["type"] for f in rows if f["type"] not in ideas]
        print("идей: %d, без идеи: %s" % (len(rows) - len(lost), ", ".join(lost) or "нет"))
    if no_text:
        print("без описания (%d): %s" % (len(no_text), ", ".join(no_text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
