# -*- coding: utf-8 -*-
"""Эталон разбора наборов: тип плитки, сплошное поле и ромб подложки — по кадрам установленной игры.

Нужен, чтобы приёмка в лаунчере (C#) судила о тех же кадрах, что конвейер рисования (python).
Сверять с листами art/TERRAIN нельзя: они собраны в разное время и из разных установок — лист
JUNGLE, например, собран из ванильных bin/UFO, а не из Пираток (грабли R-015), и эталон
получился бы врущим. Поэтому эталон снимается прямо с данных, по которым идёт приёмка.

    py -3 tools\\hdart\\ground_dump.py
    py -3 tools\\hdart\\ground_dump.py --data bin\\UFO --out census\\ground_ufo.tsv
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xcom_sprites as xs  # noqa: E402
import extract_pck  # noqa: E402

ENC = "utf-8-sig"
DEFAULT_DATA = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez")


def dump_set(folder, name):
    """Строки эталона для одного набора; пустой список, если набора или MCD нет."""
    pck = extract_pck.find_ci(folder, name)
    if not pck:
        return []
    stem = os.path.splitext(os.path.basename(pck))[0]
    tab = extract_pck.find_ci(folder, stem + ".TAB") or os.path.splitext(pck)[0] + ".TAB"
    fw, fh = xs.frame_size_for(name)
    frames = xs.read_pck(pck, tab, fw, fh)
    types, walkable, raised = [-1] * len(frames), [True] * len(frames), [False] * len(frames)
    mcd = extract_pck.find_ci(folder, stem + ".MCD")
    if mcd:
        types, walkable, raised = xs.frame_types(xs.read_mcd(mcd), len(frames))
    ground, base = extract_pck.ground_flags(frames, types, walkable, raised, fw, fh)
    rows = []
    for i, frame in enumerate(frames):
        rows.append((name.upper(), i, "1" if frame is None else "0", types[i],
                     int(ground[i]), int(base[i])))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DEFAULT_DATA, help="папка данных (в ней TERRAIN, UNITS, ...)")
    ap.add_argument("--section", default="TERRAIN")
    ap.add_argument("--out", default=os.path.join("census", "ground.tsv"))
    a = ap.parse_args(argv)

    folder = os.path.join(a.data, a.section)
    if not os.path.isdir(folder):
        print("нет папки:", folder)
        return 1
    names = sorted({f.upper() for f in os.listdir(folder) if f.upper().endswith(".PCK")})
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    sets = frames = 0
    with open(a.out, "w", encoding=ENC, newline="") as f:
        f.write("раздел\tнабор\tкадр\tпусто\tтип\tполе\tподложка\n")
        for name in names:
            rows = dump_set(folder, name)
            if not rows:
                continue
            sets += 1
            frames += len(rows)
            for r in rows:
                f.write("%s\t%s\t%d\t%s\t%d\t%d\t%d\n" % ((a.section,) + r))
    print("наборов %d, кадров %d -> %s" % (sets, frames, a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
