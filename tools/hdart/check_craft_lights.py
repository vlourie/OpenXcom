#!/usr/bin/env python3
"""
check_craft_lights.py - проверка огней кораблей в ангаре без запуска игры.

Повторяет то, что делает движок (грабли R-082):
  * RuleCraft: sprite и skinSprites через Mod::getOffset(id, 4) - всё больше 4
    получает сдвиг мастер-мода (1000), кадр в ангаре = спрайт + 33;
  * ExtraSprites: ключ BASEBITS.PCK меньше числа кадров ванильного набора (54)
    ложится без сдвига, остальные - со сдвигом мода;
  * HdCraftLights::lightsOf: файл <кадр>.lights.txt, иначе <кадр - 1000>.lights.txt.

Для каждого корабля и скина печатает: номер кадра в игре, найдена ли картинка,
найден ли файл огней в ОБЕИХ копиях мода hd (R-081) и совпадают ли они, стоит ли
каждый огонь на корпусе. Код выхода 1, если хоть один летающий корабль без огней.

    py -3 tools/hdart/check_craft_lights.py --sheet art/_review/craft_lights_check.png
"""
import argparse
import os
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_base import basebits_map  # noqa: E402
from gen_craft_lights import SKIP, load_frame, read_lights, kind_color, glow  # noqa: E402

ENC_W = "utf-8-sig"
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PIRATEZ = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez")
HD_COPIES = [os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd"),
             os.path.join(ROOT, "user", "mods", "hd")]
MASTER_OFFSET = 1000


def vanilla_frames():
    """Число кадров ванильного BASEBITS.PCK так, как его считает SurfaceSet::loadPck."""
    tab = open(os.path.join(ROOT, "bin", "UFO", "GEOGRAPH", "BASEBITS.TAB"), "rb").read()
    first = int.from_bytes(tab[:2], "little")
    return len(tab) // 2 if first == 0 else len(tab) // 4


def crafts(mod_dir):
    """[(тип, спрайт из рулсета, скин ли)] - последнее определение типа побеждает."""
    found = {}
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
            entry = found.setdefault(c.group(1), {"sprite": None, "skins": []})
            s = re.search(r"\n    sprite: (\d+)", c.group(2))
            if s:
                entry["sprite"] = int(s.group(1))
            skins = re.search(r"\n    skinSprites: \[([^\]]*)\]", c.group(2))
            if skins:
                entry["skins"] = [int(v) for v in skins.group(1).split(",") if v.strip().isdigit()]
    out = []
    for t, e in found.items():
        if e["sprite"] is not None:
            out.append((t, e["sprite"], False))
        for v in e["skins"]:
            out.append((t, v, True))
    return out


def game_index(sprite):
    """Кадр BASEBITS, который зовёт BaseView: getOffset(sprite, 4) + 33."""
    return (sprite + MASTER_OFFSET if sprite > 4 else sprite) + 33


def sprite_key(index, shared):
    """Ключ extraSprites мастер-мода, который ляжет в кадр index; None - не ляжет никакой."""
    if index < shared:
        return index
    if index - MASTER_OFFSET >= shared:
        return index - MASTER_OFFSET
    return None


def lights_file(hd, index):
    d = os.path.join(hd, "hd", "BASEBITS.PCK")
    for i in (index, index - MASTER_OFFSET):
        p = os.path.join(d, "%d.lights.txt" % i)
        if i >= 0 and os.path.exists(p):
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description="проверка огней кораблей без игры")
    ap.add_argument("--sheet", default="", help="PNG: все корабли с огнями на полу ангара, k=4")
    args = ap.parse_args()

    shared = vanilla_frames()
    sprites = basebits_map(PIRATEZ)
    rows, bad, tiles, seen = [], 0, [], set()
    for t, s, skin in crafts(PIRATEZ):
        idx = game_index(s)
        if idx in seen:
            continue
        seen.add(idx)
        key = sprite_key(idx, shared)
        name = t + (" (скин)" if skin else "")
        if key is not None and key in SKIP:
            rows.append((name, idx, "наземный или обломки, огни не положены"))
            continue
        loaded = load_frame(key, sprites) if key is not None else None
        if loaded is None:
            rows.append((name, idx, "ОШИБКА: кадр %d никто не заполняет" % idx))
            bad += 1
            continue
        pix, pal = loaded
        files = [lights_file(hd, idx) for hd in HD_COPIES]
        if not files[0]:
            rows.append((name, idx, "ОШИБКА: огней нет, файл %d.lights.txt не найден" % key))
            bad += 1
            continue
        lights = read_lights(files[0])
        note = []
        if not files[1]:
            note.append("ОШИБКА: нет во второй копии hd")
            bad += 1
        elif open(files[0], "rb").read() != open(files[1], "rb").read():
            note.append("ОШИБКА: копии hd расходятся")
            bad += 1
        body = pix != 0
        off = []
        for x, y, kind in lights:
            xi, yi = int(x), int(y)
            y0, y1, x0, x1 = max(yi - 1, 0), yi + 2, max(xi - 1, 0), xi + 2
            if not body[y0:y1, x0:x1].any():
                off.append("(%.1f,%.1f)" % (x, y))
        if off:
            note.append("ОШИБКА: мимо корпуса " + " ".join(off))
            bad += 1
        rows.append((name, idx, "%d огней из %s%s" % (len(lights), os.path.basename(files[0]),
                                                    ("; " + "; ".join(note)) if note else "")))
        tiles.append((name, idx, pix, pal, lights))

    for name, idx, text in rows:
        print("%-34s кадр %4d: %s" % (name, idx, text))
    print("кораблей и скинов: %d, с огнями: %d, ошибок: %d" % (len(rows), len(tiles), bad))

    if args.sheet and tiles:
        k, cols = 4, 10
        cw, ch = 32 * k + 8, 40 * k + 8
        rws = (len(tiles) + cols - 1) // cols
        img = np.zeros((rws * ch, cols * cw, 3), np.float32) + 22
        for n, (name, idx, pix, pal, lights) in enumerate(tiles):
            x0, y0 = (n % cols) * cw + 4, (n // cols) * ch + 4
            h, w = min(pix.shape[0], 40), min(pix.shape[1], 32)
            rgb = np.repeat(np.repeat(pal[pix[:h, :w]].astype(np.float32), k, 0), k, 1)
            am = np.repeat(np.repeat(pix[:h, :w] != 0, k, 0), k, 1)
            sub = img[y0:y0 + h * k, x0:x0 + w * k]
            sub[am] = rgb[am]
            for x, y, kind in lights:
                own = "#" in kind
                kind, col = kind_color(kind)
                glow(sub, x * k, y * k, k, col, 1.0, own)
        out = os.path.join(ROOT, args.sheet) if not os.path.isabs(args.sheet) else args.sheet
        os.makedirs(os.path.dirname(out), exist_ok=True)
        Image.fromarray(img.astype(np.uint8)).save(out)
        print("лист:", out)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
