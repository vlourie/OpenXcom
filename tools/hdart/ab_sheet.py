#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ab_sheet.py - лист и сводка опыта: одни и те же кадры в нескольких вариантах paint3.

Каждый вариант paint3 пишет клетки в art\TERRAIN\<НАБОР>.PCK\returned\<sub>\<N>.png и свой
report.tsv в <out>. Лист: строка на кадр, столбцы «оригинал | мод сейчас | вариант 1 ... N» на
тёмном полу боя (R-041). Сводка: годных по меркам, средний балл и секунд на кадр по варианту -
но выбирать вариант по листу глазами, мерки материала не видят (R-063).

    py -3 tools\hdart\ab_sheet.py --list art\gen3\pilot.txt --variants V1=ab_v1,V2=ab_v2 --ab art\gen3\ab
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PIL import Image, ImageDraw                        # noqa: E402

import score_batch as sb                                # noqa: E402
import tile_forge as tf                                 # noqa: E402

ENC = "utf-8-sig"
FLOOR_BG = (38, 38, 42)


def read_list(path):
    out = []
    with open(path, encoding=ENC) as f:
        for line in f:
            p = line.split()
            if len(p) >= 2 and not line.startswith("#"):
                out.append((p[0].upper() if p[0].upper().endswith(".PCK") else p[0].upper() + ".PCK",
                            int(p[1])))
    return out


def cell(path, size):
    if not os.path.exists(path):
        return None
    im = Image.open(path).convert("RGBA")
    return im if im.size == size else im.resize(size, Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--variants", required=True, help="Имя=sub через запятую")
    ap.add_argument("--ab", default=os.path.join("art", "gen3", "ab"),
                    help="папка опыта: отчёты вариантов лежат в <ab>/<sub>/report.tsv")
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--per-sheet", type=int, default=8, dest="per_sheet")
    args = ap.parse_args()

    variants = [v.split("=", 1) for v in args.variants.split(",") if v.strip()]
    frames = read_list(args.list)

    # сводка по отчётам
    reports = {}
    for name, sub in variants:
        p = os.path.join(args.ab, sub, "report.tsv")
        rows = {}
        if os.path.exists(p):
            with open(p, encoding=ENC, newline="") as f:
                for r in csv.DictReader(f, delimiter="\t"):
                    rows[(r["набор"].upper(), int(r["кадр"]))] = r
        reports[name] = rows
    lines = ["вариант\tкадров\tгодных\tсредний балл\tс/кадр"]
    for name, _sub in variants:
        rs = [reports[name].get(k) for k in frames]
        rs = [r for r in rs if r]
        if not rs:
            lines.append("%s\t0\t-\t-\t-" % name)
            continue
        good = sum(int(r["годен"]) for r in rs)
        ball = sum(float(r["балл"]) for r in rs) / len(rs)
        sec = sum(float(r["с"]) for r in rs) / len(rs)
        lines.append("%s\t%d\t%d (%.0f%%)\t%.3f\t%.0f" % (name, len(rs), good, 100.0 * good / len(rs), ball, sec))
    summary = "\n".join(lines)
    print(summary)
    with open(os.path.join(args.ab, "summary.tsv"), "w", encoding=ENC) as f:
        f.write(summary + "\n")

    # листы по per_sheet кадров
    sheets = {}
    cols = ["оригинал", "мод сейчас"] + [n for n, _ in variants]
    for start in range(0, len(frames), args.per_sheet):
        chunk = frames[start:start + args.per_sheet]
        cw, ch = 128, 160
        head = 18
        im = Image.new("RGB", (len(cols) * (cw + 6) + 6, head + len(chunk) * (ch + 16) + 6), (20, 20, 24))
        d = ImageDraw.Draw(im)
        for k, t in enumerate(cols):
            d.text((8 + k * (cw + 6), 3), t, fill=(255, 220, 0))
        for r, (name, i) in enumerate(chunk):
            sh = sheets.get(name) or tf.Sheet(args.sheets, name)
            sheets[name] = sh
            size = (sh.fw * 4, sh.fh * 4)
            pics = [sh.frame(i).convert("RGBA").resize(size, Image.NEAREST),
                    cell(os.path.join(sb.MOD, name, "%d.png" % i), size)]
            for _n, sub in variants:
                pics.append(cell(os.path.join(args.sheets, name, "returned", sub, "%d.png" % i), size))
            y = head + r * (ch + 16)
            for k, p in enumerate(pics):
                if p is None:
                    continue
                t = Image.new("RGBA", size, FLOOR_BG + (255,))
                t.alpha_composite(p)
                t = t.convert("RGB")
                if t.size != (cw, ch):
                    t = t.resize((cw, ch), Image.LANCZOS)
                im.paste(t, (6 + k * (cw + 6), y))
            marks = []
            for vn, _sub in variants:
                rr = reports[vn].get((name, i))
                if rr:
                    marks.append("%s:%s" % (vn, "+" if rr["годен"] == "1" else "-"))
            d.text((8, y + ch + 1), ("%s %d  " % (name.replace(".PCK", ""), i)) + " ".join(marks),
                   fill=(190, 190, 190))
        path = os.path.join(args.ab, "sheet_%02d.png" % (start // args.per_sheet + 1))
        im.save(path)
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
