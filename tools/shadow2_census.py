#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0 HD-теней v2: летуны в воздухе и предметы на полу.

Проект - docs/research/hd-shadows-v2-2026-10-30.md. Только чтение.

1. Бои (сейвы census\collapse\battles, каждый --stride-й, и сейвы установки): юниты с `floating: true`
   (висят без пола, тени сейчас нет), на сколько уровней ниже первый пол; предметы на земле
   (inventoryslot STR_GROUND) - сколько и на скольких клетках. Внимание: census - бои модели обрушения,
   пол там выбит искусственно, висящие в них - следы обрушения, а не летуны; мерка летунов - п. 3.
3. Рулсеты Пираток: броня с movementType: 1 и виды юнитов в ней.
   Пол клетки - деталь пола есть (mapDataID[0] в binTiles, раскладка - SavedBattleGame::save / Tile::saveBinary);
   флаг MCD «нет пола» и подставка terrainLevel -24 снизу (Tile::hasNoFloor) не учтены - это редкость.
2. Кадры предметов на полу - pack.hdp набора FLOOROB.PCK мода hd: площадь силуэта и «мягкие тёмные» пиксели
   вне силуэта (запечённая тень: альфа 16-200, яркость < 80, дальше 2 пикселей от сплошных, пятно от 6k^2).

    py -3.13 tools\shadow2_census.py
    py -3.13 tools\shadow2_census.py --stride 1

Выход - census\ao\shadow2_*.tsv и census\ao\shadow2_floorob_sheet.png (census в гит не идёт).
"""
import argparse
import base64
import glob
import io
import os
import re
import sys
import time
from collections import Counter

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unit_shadow_census import dilate, read_pack   # noqa: E402

ENC = "utf-8-sig"
STATUS_OUT = {"5", "6", "7"}   # DEAD, UNCONSCIOUS, IGNORE_ME (BattleUnit.h, UnitStatus)


def save_key(text, name):
    m = re.search(rf"(?m)^  {name}: (.+)$", text)
    if not m:
        return None
    v = m.group(1).strip()
    return int(v) if v.lstrip("-").isdigit() else ord(bytes(v.strip('"'), "ascii").decode("unicode_escape"))


def floors(text):
    """Множество индексов клеток (z*Y*X + y*X + x), у которых есть деталь пола; размеры карты."""
    X, Y, Z = save_key(text, "width"), save_key(text, "length"), save_key(text, "height")
    m = re.search(r"(?m)^  binTiles: (\S+)$", text)
    if not (m and X and Y and Z):
        return None, None
    idx, total, idsz = save_key(text, "tileIndexSize"), save_key(text, "tileTotalBytesPer"), save_key(text, "tileIDSize")
    data = base64.b64decode(m.group(1))
    none = (1 << (8 * idsz)) - 1
    out = set()
    for p in range(0, len(data), total):
        i = int.from_bytes(data[p:p + idx], "little")
        if int.from_bytes(data[p + idx:p + idx + idsz], "little") != none:
            out.add(i)
    return out, (X, Y, Z)


def units(text):
    sec = re.search(r"(?ms)^  units:\n(.*?)(?=^  [A-Za-z])", text)
    if not sec:
        return []
    out = []
    for block in re.split(r"(?m)^    - id: ", sec.group(1))[1:]:
        def f(name):
            m = re.search(rf"(?m)^      {name}: (.+)$", block)
            return m.group(1).strip() if m else ""
        pos = re.findall(r"-?\d+", f("position"))
        out.append({"type": f("genUnitType") or f("type"), "faction": f("faction"), "status": f("status"),
                    "floating": f("floating") == "true", "pos": tuple(map(int, pos)) if len(pos) == 3 else None})
    return out


def ground_items(text):
    sec = re.search(r"(?ms)^  items:\n(.*?)(?=^  [A-Za-z])", text)
    if not sec:
        return []
    out = []
    for block in re.split(r"(?m)^    - id: ", sec.group(1))[1:]:
        if re.search(r"(?m)^      inventoryslot: STR_GROUND$", block):
            m = re.search(r"(?m)^      position: \[(-?\d+),(-?\d+),(-?\d+)\]", block)
            t = re.search(r"(?m)^      type: (.+)$", block)
            if m:
                out.append((t.group(1).strip() if t else "?", tuple(map(int, m.groups()))))
    return out


def battles(paths):
    rows, fliers, types = [], [], Counter()
    for path in paths:
        text = open(path, encoding="utf-8", errors="replace").read()
        if "\n  units:" not in text:
            continue
        fl, dims = floors(text)
        if fl is None:
            continue
        X, Y, Z = dims
        us = units(text)
        alive = [u for u in us if u["status"] not in STATUS_OUT and u["pos"] and u["pos"][0] >= 0]
        n_float = 0
        for u in alive:
            if not u["floating"]:
                continue
            n_float += 1
            x, y, z = u["pos"]
            drop = next((z - zz for zz in range(z, -1, -1) if zz * Y * X + y * X + x in fl), None)
            fliers.append((os.path.basename(path), u["type"], u["faction"], z, drop))
        items = ground_items(text)
        tiles = {p for _, p in items}
        types.update(t for t, _ in items)
        rows.append((os.path.basename(path), X, Y, Z, len(alive), n_float, len(items), len(tiles)))
    return rows, fliers, types


def fly_armors(ruleset):
    """Броня с movementType: 1 и юниты в ней. Построчно по всем разделам всех файлов (комментарий с первой
    колонки раздел не сбрасывает)."""
    entries = {}
    for f in sorted(glob.glob(os.path.join(ruleset, "**", "*.rul"), recursive=True)):
        section, name = None, None
        for line in open(f, encoding="utf-8", errors="replace").read().splitlines():
            if re.match(r"^[A-Za-z]", line):
                section, name = line.split(":", 1)[0], None
                continue
            m = re.match(r"^  - (?:type|name): (\S+)", line)
            if m:
                name = m.group(1)
                continue
            m = re.match(r"^    (movementType|armor): (\S+)", line)
            if m and name and section in ("armors", "units"):
                entries.setdefault((section, name), {})[m.group(1)] = m.group(2)
    armors = [n for s, n in entries if s == "armors"]
    fly = {n for (s, n), v in entries.items() if s == "armors" and v.get("movementType") == "1"}
    users = [n for (s, n), v in entries.items() if s == "units" and v.get("armor") in fly]
    return len(armors), len(fly), users


def floorob(root, k_sheet=48):
    p = os.path.join(root, "FLOOROB.PCK", "pack.hdp")
    k, frames = read_pack(p)
    rows = []
    for index, blob in frames:
        im = Image.open(io.BytesIO(blob)).convert("RGBA")
        rgba = np.asarray(im)
        a = rgba[:, :, 3].astype(int)
        lum = rgba[:, :, 0] * 0.3 + rgba[:, :, 1] * 0.59 + rgba[:, :, 2] * 0.11
        solid = a >= 230
        if not solid.any():
            rows.append((index, 0, 0, 0, 0, False, im))
            continue
        ys, xs = np.nonzero(solid)
        soft = (a >= 16) & (a <= 200) & (lum < 80) & ~dilate(solid, 2)
        n_soft = int(soft.sum())
        rows.append((index, int(solid.sum()) // (k * k), int(xs.max() - xs.min() + 1) // k, int(ys.max() - ys.min() + 1) // k,
                     n_soft // (k * k), n_soft >= 6 * k * k, im))
    return k, rows


def sheet(k, rows, path, n=48):
    used = [r for r in rows if r[1] > 0]
    blob = [r for r in used if r[5]][:n // 2]
    step = max(1, len(used) // (n - len(blob)))
    pick = sorted({r[0]: r for r in blob + used[::step][:n - len(blob)]}.values(), key=lambda r: r[0])
    cw, ch = 32 * k, 40 * k
    cols = 8
    try:
        font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"), 16)
    except OSError:
        font = ImageFont.load_default()
    out = Image.new("RGB", (cols * (cw + 6) + 6, ((len(pick) + cols - 1) // cols) * (ch + 6) + 6), (200, 200, 200))
    d = ImageDraw.Draw(out)
    for i, r in enumerate(pick):
        x, y = 6 + (i % cols) * (cw + 6), 6 + (i // cols) * (ch + 6)
        bg = Image.new("RGBA", r[6].size, (200, 200, 200, 255))
        bg.alpha_composite(r[6])
        out.paste(bg.convert("RGB"), (x, y))
        d.text((x + 2, y + 2), "#%d%s" % (r[0], " *" if r[5] else ""), fill=(160, 0, 0), font=font)
    out.save(path)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--battles", default=os.path.join("census", "collapse", "battles"))
    ap.add_argument("--stride", type=int, default=4)
    ap.add_argument("--extra", default=os.path.join("Пиратки", "Dioxine_XPiratez", "user", "piratez"))
    ap.add_argument("--root", default=os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd"))
    ap.add_argument("--ruleset", default=os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "Ruleset"))
    ap.add_argument("--out", default=os.path.join("census", "ao"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()

    paths = sorted(glob.glob(os.path.join(args.battles, "*.sav")))[::args.stride]
    paths += sorted(glob.glob(os.path.join(args.extra, "*.sav")) + glob.glob(os.path.join(args.extra, "*.asav")))
    rows, fliers, types = battles(paths)
    with open(os.path.join(args.out, "shadow2_battles.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("save\tX\tY\tZ\talive\tfloating\tground_items\titem_tiles\n")
        for r in rows:
            f.write("\t".join(map(str, r)) + "\n")
    with open(os.path.join(args.out, "shadow2_fliers.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("save\ttype\tfaction\tz\tdrop\n")
        for r in fliers:
            f.write("\t".join(map(str, r)) + "\n")
    with_fl = sum(1 for r in rows if r[5])
    drops = Counter(r[4] for r in fliers)
    print(f"боёв {len(rows)}; с висящими юнитами {with_fl} ({with_fl / max(1, len(rows)):.0%}); висящих {len(fliers)}, "
          f"из {sum(r[4] for r in rows)} живых")
    print("  высота до пола (уровней):", ", ".join(f"{d}: {n}" for d, n in sorted(drops.items(), key=lambda x: (x[0] is None, x[0] or 0))))
    print("  по сторонам:", dict(Counter(r[2] for r in fliers)), " типы:", Counter(r[1] for r in fliers).most_common(8))
    gi = sorted(r[6] for r in rows)
    gt = sorted(r[7] for r in rows)
    print(f"  предметов на земле: медиана {gi[len(gi) // 2]}, p90 {gi[int(len(gi) * 0.9)]}, макс {gi[-1]}; "
          f"клеток с предметами: медиана {gt[len(gt) // 2]}, p90 {gt[int(len(gt) * 0.9)]}, макс {gt[-1]}")
    print("  частые на земле:", types.most_common(10))

    n_arm, n_fly, users = fly_armors(args.ruleset)
    print(f"броня Пираток: {n_arm}, летает (movementType 1): {n_fly}; видов юнитов в ней: {len(users)}, например "
          + ", ".join(users[:8]))

    k, frames = floorob(args.root)
    with open(os.path.join(args.out, "shadow2_floorob.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("frame\tsolid_px\tbox_w\tbox_h\tsoft_px\tblob\n")
        for r in frames:
            f.write("\t".join(map(str, r[:6])) + "\n")
    used = [r for r in frames if r[1] > 0]
    ws, hs = sorted(r[2] for r in used), sorted(r[3] for r in used)
    print(f"FLOOROB: k={k}, кадров {len(frames)}, с силуэтом {len(used)}, с пятном {sum(1 for r in used if r[5])}; "
          f"рамка силуэта (базовые пикс.) ширина медиана {ws[len(ws) // 2]} p90 {ws[int(len(ws) * 0.9)]}, "
          f"высота медиана {hs[len(hs) // 2]} p90 {hs[int(len(hs) * 0.9)]}")
    sp = os.path.join(args.out, "shadow2_floorob_sheet.png")
    sheet(k, frames, sp)
    print(f"-> {args.out} ({time.time() - t0:.0f} с)")


if __name__ == "__main__":
    main()
