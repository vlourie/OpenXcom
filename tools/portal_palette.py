#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Палитра сайта берётся из палитры МЕНЮ ИГРЫ, а не подбирается на глаз.

Облик портала повторяет интерфейс X-Piratez, поэтому цвета обязаны быть теми же числами,
которыми их видит игрок, а не похожими (правило проекта 4: не угадывать форматы).

Откуда что берётся:

  индексы  - Piratez_Globals.rul, блок interfaces: у каждого экрана перечислены элементы
             (window, text, button) и номер цвета. Считаем, какими номерами игра пользуется
             чаще всего - это и есть её палитра интерфейса;
  цвета    - Resources/Pals/geo_CC_Dark.pal, он подставлен модом вместо PAL_GEOSCAPE
             (Recolr.rul), а на нём нарисованы все меню, кроме боевых.

Классическое окно X-COM красится не одним цветом, а рампой из шестнадцати: базовый индекс
и соседние дают и рамку, и заливку, и тень. Поэтому в CSS уходит не один цвет, а вся рампа
блока - без неё двойная рамка получится плоской.

    py -3 tools/portal_palette.py                      показать рампы и частоты
    py -3 tools/portal_palette.py --css portal/src/Xp.Portal/wwwroot/css/palette.css
"""
import argparse
import os
import re
import sys
from collections import Counter

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez")
PAL = os.path.join(MOD, "Resources", "Pals", "geo_CC_Dark.pal")
RUL = os.path.join(MOD, "Ruleset", "Piratez_Globals.rul")


def read_jasc(path):
    """JASC-PAL: заголовок из трёх строк, дальше 256 строк 'R G B'."""
    with open(path, encoding="latin-1") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if lines[0] != "JASC-PAL":
        raise SystemExit("не JASC-PAL: %s" % path)
    n = int(lines[2])
    out = []
    for ln in lines[3:3 + n]:
        r, g, b = (int(x) for x in ln.split()[:3])
        out.append((r, g, b))
    if len(out) != n:
        raise SystemExit("в палитре %d записей вместо %d" % (len(out), n))
    return out


def read_interface_colors(path):
    """Номера цветов из блока interfaces: {id элемента: Counter номеров}."""
    with open(path, encoding="latin-1") as f:
        text = f.read()
    start = text.find("\ninterfaces:")
    if start < 0:
        raise SystemExit("в рулсете нет блока interfaces:")
    block = text[start:]
    # следующий раздел верхнего уровня заканчивает блок
    m = re.search(r"\n(?=[a-zA-Z_]+:\s*$)", block[1:], re.M)
    if m:
        block = block[:m.start() + 1]
    by_id, by_color = {}, Counter()
    cur = None
    for ln in block.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            continue
        m = re.match(r"-?\s*id:\s*(\S+)", s)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"color2?:\s*(-?\d+)", s)
        if m and cur:
            c = int(m.group(1))
            if 0 <= c <= 255:
                by_id.setdefault(cur, Counter())[c] += 1
                by_color[c] += 1
    return by_id, by_color


def hexc(rgb):
    return "#%02x%02x%02x" % rgb


def ramp(pal, base):
    """Блок из шестнадцати, в котором лежит индекс: так их и красит движок."""
    lo = (base // 16) * 16
    return lo, pal[lo:lo + 16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pal", default=PAL)
    ap.add_argument("--rul", default=RUL)
    ap.add_argument("--css", default="", help="куда записать переменные CSS")
    args = ap.parse_args()

    pal = read_jasc(args.pal)
    by_id, by_color = read_interface_colors(args.rul)
    print("палитра: %s (%d цветов)" % (os.path.basename(args.pal), len(pal)))
    print("рулсет:  %s, элементов с цветом: %d" % (os.path.basename(args.rul), len(by_id)))

    print("\nчаще всего игра красит этими номерами:")
    for c, n in by_color.most_common(12):
        lo, _ = ramp(pal, c)
        print("  %3d  %s  x%-4d блок %3d..%3d" % (c, hexc(pal[c]), n, lo, lo + 15))

    for name in ("window", "text", "button", "button1", "button2", "heading"):
        if name in by_id:
            top = by_id[name].most_common(4)
            print("\n%-8s %s" % (name, "  ".join("%d=%s(x%d)" % (c, hexc(pal[c]), n) for c, n in top)))

    main_ui = by_color.most_common(1)[0][0]
    lo, block = ramp(pal, main_ui)
    print("\nрампа главного блока %d..%d (индекс %d):" % (lo, lo + 15, main_ui))
    for k, rgb in enumerate(block):
        print("  %3d  %s" % (lo + k, hexc(rgb)))

    if args.css:
        write_css(args.css, pal, main_ui, by_color)
        print("\nCSS: %s" % args.css)
    return 0


ELEMENT = 138          # window, text и button главного меню - самый частый номер в рулсете
ACCENT = 134           # бирюза того же блока, ею игра красит активное
SAND = 144             # песочный, 11 упоминаний - второй по частоте после блока 128
PURPLE = 89            # heading в newBattleMenu

# Как движок собирает виджет из одного номера. Перечислено ровно то, что рисует код:
# Window::draw без thinBorder кладёт пять колец C+3, C+2, C+1, C+2, C+3;
# TextButton::draw - C+1, C+5, C+2, C+4 и лицо C+3.
WINDOW_RINGS = (3, 2, 1, 2, 3)
BUTTON_RINGS = (1, 5, 2, 4)
BUTTON_FACE = 3


def write_css(path, pal, main_ui, by_color):
    lo, block = ramp(pal, main_ui)
    c = ELEMENT
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    out = []
    out.append("/* The game's own palette, not a look-alike.")
    out.append(" *")
    out.append(" * Generated by tools/portal_palette.py from the files X-Piratez itself reads:")
    out.append(" *   colours  Resources/Pals/geo_CC_Dark.pal  (Recolr.rul puts it in place of PAL_GEOSCAPE)")
    out.append(" *   indices  Ruleset/Piratez_Globals.rul, the interfaces: block")
    out.append(" *")
    out.append(" * A widget in X-COM is built from ONE index: the engine takes the shades around it.")
    out.append(" * The ring variables below repeat what src/Interface/Window.cpp and TextButton.cpp draw,")
    out.append(" * so a panel on the site bevels exactly like a panel in the game.")
    out.append(" *")
    out.append(" * Do not edit by hand - rerun the tool. */")
    out.append(":root {")
    out.append("    /* every shade of the block the menus are drawn with (indices %d..%d) */" % (lo, lo + 15))
    for k, rgb in enumerate(block):
        out.append("    --ui-%d: %s;   /* index %d */" % (k, hexc(rgb), lo + k))
    out.append("")
    out.append("    /* Window::draw, five nested rings from the outside in (element colour %d) */" % c)
    for k, d in enumerate(WINDOW_RINGS):
        out.append("    --win-ring-%d: %s;" % (k, hexc(pal[c + d])))
    out.append("    --win-face: %s;" % hexc(pal[c]))
    out.append("")
    out.append("    /* TextButton::draw, four rings and the face the caption sits on */")
    for k, d in enumerate(BUTTON_RINGS):
        out.append("    --btn-ring-%d: %s;" % (k, hexc(pal[c + d])))
    out.append("    --btn-face: %s;" % hexc(pal[c + BUTTON_FACE]))
    out.append("    --btn-ink: %s;   /* the caption keeps the element colour itself */" % hexc(pal[c]))
    out.append("")
    out.append("    /* roles, so pages name the meaning and never the number */")
    out.append("    --ink: %s;" % hexc(pal[lo + 1]))
    out.append("    --ink-dim: %s;" % hexc(pal[lo + 2]))
    out.append("    --ink-faint: %s;" % hexc(pal[lo + 3]))
    out.append("    --accent: %s;" % hexc(pal[ACCENT]))
    out.append("    --sand: %s;" % hexc(pal[SAND]))
    out.append("    --purple: %s;" % hexc(pal[PURPLE]))
    out.append("    --bg: %s;" % hexc(pal[lo + 5]))
    out.append("    --void: %s;" % hexc(pal[15]))
    out.append("}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    sys.exit(main())
