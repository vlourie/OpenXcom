"""Лист пачки точного движка стен: каждая картинка в поле своих соседей, как на карте, тремя источниками -
ТЕКУЩИЙ ПАК | ТОЧНЫЙ A | ТОЧНЫЙ B2. Соседи в сцене - из того же источника, поэтому шов на стыке виден таким,
каким его покажет игра. Плюс предложение по картинке и общий план установки пачки.

  wall_exact_sheet.py --batch N [--size 100] [--out census/walls/exact/render] [--per-page 10]

Выход: <out>/sheets/b<NNN>_<стр>.png, <out>/plan_b<NNN>.tsv (картинка, кадры, места, прежний выбор,
предложение, причина). В мод ничего не ставится.
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFont         # noqa: E402
import map_mockup as mm                             # noqa: E402
import wall_exact as we                             # noqa: E402
import wall_final_render as wf                      # noqa: E402
import wall_final_select as fs                      # noqa: E402

ENC = "utf-8-sig"
SELECT = "census/walls/final_select/select.tsv"
CROP = 224               # вырез сцены вокруг кадра, пикселей x4
FLOOR = (34, 34, 40, 255)
SRC = ("ТЕКУЩИЙ ПАК", "ТОЧНЫЙ A", "ТОЧНЫЙ B2")


def font(n):
    for f in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, n)
    return ImageFont.load_default()


class Source:
    """Картинка -> HD 128x160 RGBA одного источника. Нет готового точного - считает A на месте (без модели)."""

    def __init__(self, kind, out, pics, nb):
        self.kind, self.out, self.pics, self.nb, self.cache = kind, out, pics, nb, {}

    def get(self, q):
        if q in self.cache:
            return self.cache[q]
        im = None
        if self.kind == "cur":
            for s, n in self.pics.frames.get(q, []):
                p = fs.find_cur("%s:%d" % (s, n))
                if p:
                    im = Image.open(p).convert("RGBA")
                    break
        else:
            sub = "xbrz" if self.kind == "A" else "b2"
            p = os.path.join(self.out, sub, q + ".png")
            if not os.path.exists(p):
                p = os.path.join(self.out, "xbrz", q + ".png")
            if os.path.exists(p):
                im = Image.open(p).convert("RGBA")
            elif self.pics.idx(q) is not None:
                im = we.render(q, self.nb, self.pics, None)[0]["xbrz"]
        self.cache[q] = im
        return im


def scene(p, members, src):
    """Сцена: соседи в игровом порядке, сам кадр сверху, всё из одного источника. Возвращает вырез и число
    соседей, которых в источнике нет. Шов судится глазами по листу: мера перепада на стыке (и против классики,
    и за вычетом своей фактуры) видимый шов от контура и фактуры не отделила - R-342."""
    xs = [m[4] for m in members]
    ys = [m[5] for m in members]
    x0, y0 = -min(xs) + 8, -min(ys) + 8
    W, H = (max(xs) - min(xs) + 48) * we.K, (max(ys) - min(ys) + 56) * we.K
    can = Image.new("RGBA", (W, H), FLOOR)
    miss = 0
    for *_k, sx, sy, q in members:
        im = src.get(q)
        if im is None:
            miss += 1
            continue
        can.alpha_composite(im, ((x0 + sx) * we.K, (y0 + sy) * we.K))
    cx, cy = (x0 + 16) * we.K, (y0 + 20) * we.K
    box = (cx - CROP // 2, cy - CROP // 2, cx + CROP // 2, cy + CROP // 2)
    out = Image.new("RGBA", (CROP, CROP), FLOOR)
    out.alpha_composite(can.crop((max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3]))),
                        (max(0, -box[0]), max(0, -box[1])))
    return out.convert("RGB"), miss


def propose(frames, sel):
    """По прежнему выбору (WALL_FINAL_SELECT). Фактурный текущий меняется только по слову Vitali (DECISIONS 08.10)."""
    got = [sel.get(k) for k in frames if sel.get(k)]
    if not got:
        return "B2", "прежнего выбора нет"
    meth = {r["выбор"] for r in got}
    if any(r["причина"].startswith("OWNED") for r in got):
        return "ТЕКУЩИЙ", "OWNED: кадр другой работы"
    if meth <= {"B2"}:
        return "B2", "прежде B2 по кадру - точный B2 без швов"
    if meth <= {"A"}:
        return "A", "прежде A по кадру - точный A без швов"
    if meth == {"CURRENT_HD"}:
        mat = {r["материал"] for r in got}
        if mat == {"smooth"}:
            return "ТЕКУЩИЙ", "гладкий, текущий прошёл ворота"
        return "ТЕКУЩИЙ", "фактурный, текущий сохраняем (DECISIONS 08.10) - смотреть шов"
    return "B2", "кадры одной картинки стоят разными источниками (%s) - один точный" % "/".join(sorted(meth))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, required=True)
    ap.add_argument("--size", type=int, default=100)
    ap.add_argument("--out", default="census/walls/exact/render")
    ap.add_argument("--per-page", type=int, default=10)
    ap.add_argument("--only-current", action="store_true",
                    help="на лист только фактурный ТЕКУЩИЙ - решение Vitali, менять ли на B2 (лист b<NNN>_cur_<стр>)")
    a = ap.parse_args()
    os.chdir(we.ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    nb = json.load(open(we.NEIGHBORS, encoding=ENC))
    cl = wf.Classic(mm.World())
    rs = we.rows()
    pics = we.Pics(cl, rs)
    part = rs[(a.batch - 1) * a.size:a.batch * a.size]
    with open(SELECT, encoding=ENC, newline="") as f:
        sel = {r["кадр"]: r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}
    srcs = [Source("cur", a.out, pics, nb), Source("A", a.out, pics, nb), Source("B2", a.out, pics, nb)]
    os.makedirs(os.path.join(a.out, "sheets"), exist_ok=True)
    plan, rows = [], []
    for i, r in enumerate(part):
        p = r["картинка"]
        if pics.idx(p) is None:
            continue
        frames = ["%s:%d" % (s.upper(), n) for s, n in pics.frames[p]]
        prop, why = propose(frames, sel)
        prev = "/".join(sorted({sel[k]["выбор"] for k in frames if k in sel})) or "-"
        plan.append([p, " ".join(frames), r["вес_мест"], prev, prop, why])
        if a.only_current and not why.startswith("фактурный"):
            continue
        members = we.field_members(p, nb)
        cells = [scene(p, members, s) for s in srcs]
        rows.append((i + 1 + (a.batch - 1) * a.size, p, frames, r["вес_мест"], prev, prop, why, cells))
    with open(os.path.join(a.out, "plan_b%03d.tsv" % a.batch), "w", encoding=ENC, newline="") as f:
        f.write("\t".join(["картинка", "кадры", "мест", "прежде", "предложение", "причина"]) + "\n")
        for row in plan:
            f.write("\t".join(row) + "\n")
    f1, f2 = font(15), font(12)
    LW, gap = 230, 6
    for pg in range(0, len(rows), a.per_page):
        chunk = rows[pg:pg + a.per_page]
        W = LW + 3 * (CROP + gap)
        H = 30 + len(chunk) * (CROP + gap)
        sh = Image.new("RGB", (W, H), (16, 16, 20))
        d = ImageDraw.Draw(sh)
        for j, t in enumerate(SRC):
            d.text((LW + j * (CROP + gap) + 4, 6), t, fill=(230, 230, 230), font=f1)
        for k, (n, p, frames, mest, prev, prop, why, cells) in enumerate(chunk):
            y = 30 + k * (CROP + gap)
            d.text((6, y + 2), "#%d  %s" % (n, frames[0]), fill=(255, 220, 120), font=f1)
            ty = y + 22
            for line in [", ".join(frames[1:4]) + (" ..." if len(frames) > 4 else ""),
                         "мест %s" % mest, "прежде: %s" % prev, "предложение: %s" % prop]:
                d.text((6, ty), line, fill=(210, 210, 210), font=f2)
                ty += 16
            words, line = why.split(), ""
            for w in words:
                if len(line) + len(w) > 32:
                    d.text((6, ty), line, fill=(150, 200, 255), font=f2)
                    ty += 15
                    line = ""
                line += w + " "
            d.text((6, ty), line, fill=(150, 200, 255), font=f2)
            hi = {"ТЕКУЩИЙ": 0, "A": 1, "B2": 2}[prop]
            for j, (im, miss) in enumerate(cells):
                x = LW + j * (CROP + gap)
                sh.paste(im, (x, y))
                if j == hi:
                    d.rectangle((x - 2, y - 2, x + CROP + 1, y + CROP + 1), outline=(80, 220, 80), width=2)
                if miss:
                    d.text((x + 4, y + CROP - 16), "нет соседей: %d" % miss, fill=(255, 120, 120), font=f2)
        path = os.path.join(a.out, "sheets", "b%03d_%s%02d.png" % (a.batch, "cur_" if a.only_current else "",
                                                                   pg // a.per_page + 1))
        sh.save(path)
        print(path)
    cnt = {}
    for row in plan:
        cnt[row[4]] = cnt.get(row[4], 0) + 1
    print("пачка %d: картинок %d, предложение %s" % (a.batch, len(plan), cnt))


if __name__ == "__main__":
    main()
