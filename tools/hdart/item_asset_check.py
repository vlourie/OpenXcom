"""Приёмка HD-картинок предметов инвентаря ДО обрезки движком (docs/research/inventory-items-hd.md §5.3, §9.8).

Движок режет HD-кадр по клеткам предмета и по рамке руки, поэтому на экране лишнее не видно - и проверять
надо сам файл: непрозрачных пикселей (альфа > 0) вне допуска обязано быть ровно 0.

Файлы папки hd/BIGOBS.PCK:
  <кадр>.<ТИП>.png       - сетка: допуск [1, 16w - (w==2)) x [1, 16h - (h==3)) базы
  <кадр>.<ТИП>.hand.png  - рамка руки 32x48: допуск - клетки предмета после штатного сдвига руки
                           ((2-w)*8, (3-h)*8) внутри линий рамки [1, 31) x [1, 47); всю рамку получают
                           только 3x2 и 3x3 - они больше рамки
  <кадр>.png, <кадр>.hand.png - общий файл кадра: проверяется против КАЖДОГО предмета этого кадра
Без .hand предмет до 2x3 показывается в руке своей картинкой со штатным сдвигом: допуск тот же, поэтому
чистая сетка - чистая и в руке; у 3x2 и 3x3 без .hand в руке классика.
Масштаб: картинка ровно в k раз больше классического кадра (сетка - размер кадра из переписи, рука - 32x48).

  py -3.13 tools/hdart/item_asset_check.py <папка hd/BIGOBS.PCK> [--items census/items/items.tsv]
      [--frames census/items/bigobs_frames.tsv] [--out отчёт.tsv]
Код 1 - есть FAIL. Отчёт: файл, предмет, вариант, клетки, k, вне допуска, вердикт.
"""
import argparse, csv, re, sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ENC_R, ENC_W = "utf-8-sig", "utf-8-sig"
HAND_W, HAND_H = 32, 48
NAME = re.compile(r"^(\d+)(?:\.(.+?))?(\.hand)?\.png$", re.I)


def read_tsv(path):
    with open(path, encoding=ENC_R, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def grid_rect(w, h):
    return 1, 1, 16 * w - (1 if w == 2 else 0), 16 * h - (1 if h == 3 else 0)


def hand_rect(w, h):
    """Допуск .hand, как HdItems::pick (ТЗ §5.4): клетки после сдвига руки внутри линий рамки; 3x2 и 3x3 - вся рамка."""
    if w > 2 or h > 3:
        return 1, 1, HAND_W - 1, HAND_H - 1
    dx, dy = (2 - w) * 8, (3 - h) * 8
    return max(1, dx), max(1, dy), min(HAND_W - 1, dx + 16 * w), min(HAND_H - 1, dy + 16 * h)


def outside(alpha, rect, k):
    """Непрозрачные пиксели картинки вне прямоугольника базы rect (x0, y0, x1, y1), увеличенного в k раз."""
    x0, y0, x1, y1 = (v * k for v in rect)
    inside = np.zeros(alpha.shape, bool)
    inside[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    return int(((alpha > 0) & ~inside).sum())


def check_file(path, users, frame_size):
    """Строки отчёта по одному файлу. users - [(тип, w, h)] предметов, против которых он проверяется."""
    m = NAME.match(path.name)
    hand = bool(m.group(3))
    img = Image.open(path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    alpha = np.asarray(img)[:, :, 3]
    ih, iw = alpha.shape
    bw, bh = (HAND_W, HAND_H) if hand else frame_size
    rows = []
    k = iw // bw if bw else 0
    scale_ok = bw > 0 and iw % bw == 0 and ih % bh == 0 and iw // bw == ih // bh and k >= 1
    if not users:
        return [dict(file=path.name, item="-", variant="hand" if hand else "grid", cells="-", k=k,
                     outside="-", verdict="FAIL", note="нет предмета с этим кадром и типом")]
    for typ, w, h in users:
        row = dict(file=path.name, item=typ, variant="hand" if hand else "grid", cells=f"{w}x{h}", k=k)
        if not scale_ok:
            row.update(outside="-", verdict="FAIL", note=f"{iw}x{ih} не кратно кадру {bw}x{bh}")
        else:
            rect = hand_rect(w, h) if hand else grid_rect(w, h)
            n = outside(alpha, rect, k)
            note = ""
            if not hand:
                note = "в руке - со штатным сдвигом" if w <= 2 and h <= 3 else "в руке без .hand - классика"
            row.update(outside=n, verdict="PASS" if n == 0 else "FAIL", note=note)
        rows.append(row)
    return rows


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("folder")
    a.add_argument("--items", default=str(ROOT / "census" / "items" / "items.tsv"))
    a.add_argument("--frames", default=str(ROOT / "census" / "items" / "bigobs_frames.tsv"))
    a.add_argument("--out", default="")
    o = a.parse_args(argv)
    sizes = {}
    for r in read_tsv(o.frames):
        s = re.match(r"(\d+)x(\d+)", r.get("size", ""))
        if s:
            sizes[int(r["frame"])] = (int(s.group(1)), int(s.group(2)))
    by_frame = {}
    for r in read_tsv(o.items):
        try:
            f = int(r["bigSprite"])
        except (KeyError, ValueError):
            continue
        w, h = int(r.get("invWidth") or 1), int(r.get("invHeight") or 1)
        if f >= 0 and w > 0 and h > 0:
            by_frame.setdefault(f, []).append((r["type"], w, h))
    rows = []
    for p in sorted(Path(o.folder).iterdir()):
        m = NAME.match(p.name)
        if not m:
            continue
        frame, typ = int(m.group(1)), m.group(2)
        users = by_frame.get(frame, [])
        if typ:
            users = [u for u in users if u[0].lower() == typ.lower()]
        rows += check_file(p, users, sizes.get(frame, (HAND_W, HAND_H)))
    head = ["file", "item", "variant", "cells", "k", "outside", "verdict", "note"]
    sys.stdout.reconfigure(encoding="utf-8")
    for r in rows:
        print("\t".join(str(r.get(c, "")) for c in head))
    fails = sum(r["verdict"] == "FAIL" for r in rows)
    print(f"файлов {len({r['file'] for r in rows})}, строк {len(rows)}, FAIL {fails}")
    if o.out:
        with open(o.out, "w", encoding=ENC_W, newline="") as f:
            wr = csv.DictWriter(f, head, delimiter="\t", extrasaction="ignore")
            wr.writeheader()
            wr.writerows(rows)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
