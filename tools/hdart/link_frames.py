#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Какие кадры набора нельзя рисовать порознь.

В MCD байты 0..7 записи - это восемь кадров её анимации: один и тот же предмет во времени.
Если рисовать их по отдельности, модель каждый раз придумает материал заново, и предмет
будет мигать прямо в игре. Плюс кадр, попавший в две записи, связывает их обе (закрытая
дверь - это одновременно кадр стены).

Отдельно ловятся близнецы: один предмет как западная и как северная стена - это две записи,
одинаковые во всех байтах кроме типа и кадров.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\link_frames.py ^
        --sheets art/TERRAIN --set U_WALL02.PCK --mcd bin\UFO\TERRAIN

Кладёт в <sheets>\<набор>\groups.json:
    {"groups": [[0,1,2,3], [41,43,45,47], [27]], "twins": 1}
Кадры внутри пачки gen_tile.py --groups рисует одним вызовом на общем холсте.
"""
import argparse
import collections
import json
import os
import sys

RECORD = 62
F_UFO_DOOR, F_DOOR, F_TU_WALK, F_TLEVEL, F_TYPE = 30, 35, 39, 48, 53
TYPE_NAME = {0: "пол", 1: "зап.стена", 2: "сев.стена", 3: "объект"}


def find_mcd(where, set_name):
    """MCD набора: ищем <имя>.MCD в перечисленных папках, регистр не важен."""
    stem = os.path.splitext(set_name)[0].upper()
    for folder in where:
        if not os.path.isdir(folder):
            continue
        for n in os.listdir(folder):
            base, ext = os.path.splitext(n)
            if base.upper() == stem and ext.upper() == ".MCD":
                return os.path.join(folder, n)
    return None


def read_records(path):
    with open(path, "rb") as f:
        data = f.read()
    out = []
    for i in range(0, len(data) - RECORD + 1, RECORD):
        b = data[i:i + RECORD]
        frames = []
        for v in b[0:8]:
            if v not in frames:
                frames.append(v)
        out.append({"i": len(out), "frames": frames, "type": b[F_TYPE],
                    "ufo_door": b[F_UFO_DOOR], "door": b[F_DOOR],
                    "rest": bytes(b[8:F_TYPE]) + bytes(b[F_TYPE + 1:])})
    return out


def frame_of(sheet, lay, i):
    fw, fh, mg, cols = lay["frame_w"], lay["frame_h"], lay["margin"], lay["columns"]
    r, c = divmod(i, cols)
    x, y = mg + c * (fw + 2 * mg), mg + r * (fh + 2 * mg)
    return sheet.crop((x, y, x + fw, y + fh))


def mirror_pairs(sheets, set_name, count):
    """Западная и северная версии одной вещи в изометрии - горизонтальное отражение.
    Ловим их по ПИКСЕЛЯМ: силуэт кадра, отражённый по горизонтали, совпадает с силуэтом
    другого кадра. Сравнивать байты MCD бесполезно - у таких записей обычно разная броня,
    стоимость хода и прочее, и они не совпадают.

    Свет при этом НЕ отзеркален: в обеих версиях он падает слева. Поэтому вторую версию
    нельзя просто отразить скриптом - её надо рисовать, но рисовать ВМЕСТЕ с первой,
    тогда модель сама выставит свет и материал совпадёт."""
    import hashlib
    try:
        from PIL import Image
    except ImportError:
        print("нет Pillow - поиск зеркал пропущен")
        return []
    import json as _json
    set_dir = os.path.join(sheets, set_name)
    with open(os.path.join(set_dir, "layout.json"), encoding="utf-8-sig") as f:
        lay = _json.load(f)
    sheet = Image.open(os.path.join(set_dir, "original.png")).convert("RGBA")
    sil = {}
    for i in range(count):
        a = frame_of(sheet, lay, i).split()[3].point(lambda v: 255 if v > 0 else 0)
        if not a.getbbox():
            continue
        sil[i] = (hashlib.blake2b(a.tobytes(), digest_size=12).digest(),
                  hashlib.blake2b(a.transpose(Image.FLIP_LEFT_RIGHT).tobytes(),
                                  digest_size=12).digest())
    by = collections.defaultdict(list)
    for i, (h, _) in sil.items():
        by[h].append(i)
    out = []
    used = set()
    for i in sorted(sil):
        if i in used:
            continue
        h, hm = sil[i]
        if h == hm:                       # сам себе зеркало, пары нет
            continue
        for j in by.get(hm, ()):
            if j != i and j not in used:
                used.add(i); used.add(j); out.append((i, j))
                break
    return out


class Union:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build(records, count, twins_on=True, mirrors=()):
    u = Union()
    for r in records:
        for f in r["frames"]:
            if f < count:
                u.join(r["frames"][0], f)
    twins = 0
    if twins_on:
        same = collections.defaultdict(list)
        for r in records:
            if r["type"] in (1, 2):
                same[r["rest"]].append(r)
        for rs in same.values():
            if len(rs) > 1 and {r["type"] for r in rs} == {1, 2}:
                twins += 1
                for r in rs[1:]:
                    u.join(rs[0]["frames"][0], r["frames"][0])
    for i, j in mirrors:
        if i < count and j < count:
            u.join(i, j)
    bag = collections.defaultdict(set)
    for r in records:
        for f in r["frames"]:
            if f < count:
                bag[u.find(f)].add(f)
    groups = sorted((sorted(v) for v in bag.values()), key=lambda v: v[0])
    seen = {f for g in groups for f in g}
    loose = [f for f in range(count) if f not in seen]      # кадры, не занятые ни одной записью
    return groups, loose, twins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheets", default="art/TERRAIN")
    ap.add_argument("--set", dest="set_name", required=True)
    ap.add_argument("--mcd", action="append", default=[],
                    help="где искать MCD; можно повторять. По умолчанию bin\\UFO\\TERRAIN")
    ap.add_argument("--no-mirror", action="store_true", dest="no_mirror",
                    help="не связывать зеркальные пары (западная и северная версия одной вещи)")
    ap.add_argument("--max-cells", type=int, default=9,
                    help="предупредить, если в пачке больше стольких клеток")
    ap.add_argument("--no-twins", action="store_true", dest="no_twins",
                    help="не связывать западную и северную версии одного предмета")
    ap.add_argument("--dry", action="store_true", help="только показать, ничего не писать")
    args = ap.parse_args()

    set_dir = os.path.join(args.sheets, args.set_name)
    with open(os.path.join(set_dir, "layout.json"), encoding="utf-8-sig") as f:
        lay = json.load(f)
    count = int(lay.get("count") or len(lay.get("types") or []))

    where = args.mcd or [os.path.join("bin", "UFO", "TERRAIN")]
    path = find_mcd(where, args.set_name)
    if not path:
        raise SystemExit("MCD набора %s не найден в: %s" % (args.set_name, ", ".join(where)))

    records = read_records(path)
    mir = [] if args.no_mirror else mirror_pairs(args.sheets, args.set_name, count)
    groups, loose, twins = build(records, count, not args.no_twins, mir)
    multi = [g for g in groups if len(g) > 1]

    print("MCD: %s (%d записей)" % (path, len(records)))
    print("кадров в листе: %d | занято записями: %d | ничейных: %d"
          % (count, sum(len(g) for g in groups), len(loose)))
    print("пачек больше одного кадра: %d, в них кадров: %d" % (len(multi), sum(len(g) for g in multi)))
    print("зеркальных пар по пикселям: %d | близнецов по байтам MCD: %d" % (len(mir), twins))
    big = [g for g in multi if len(g) > args.max_cells]
    if big:
        print("ВНИМАНИЕ: пачки крупнее %d клеток - на общем холсте каждой достанется мало "
              "пикселей: %s" % (args.max_cells, "; ".join(",".join(map(str, g)) for g in big)))
    if multi:
        print("\nсвязанные кадры (рисовать только вместе):")
        for g in multi:
            kinds = set()
            for r in records:
                if set(r["frames"]) & set(g):
                    kinds.add("дверь НЛО" if r["ufo_door"] else
                              ("дверь" if r["door"] else TYPE_NAME.get(r["type"], "?")))
            print("   %-28s %s" % (",".join(map(str, g)), ", ".join(sorted(kinds))))
    if loose:
        print("\nкадры, не занятые ни одной записью MCD (в игре не видны): %s"
              % ",".join(map(str, loose)))

    if args.dry:
        return
    out = os.path.join(set_dir, "groups.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"groups": groups, "loose": loose, "twins": twins,
                   "mirrors": [list(p) for p in mir],
                   "mcd": os.path.basename(path)}, f, ensure_ascii=False, indent=1)
    print("\nзаписано: %s" % out)


if __name__ == "__main__":
    main()
