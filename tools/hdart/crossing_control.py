"""Контрольный кадр ROADS после двух последних правок (специалист 07.10): выступ за ромбом - материал края своей
клетки, боковой конец разметки - срез классики (плоский низ V). Один чистый лист: край карты (второй участок e2c,
ряд y = 59) и перекрёсток (ракурс v3, вершина V и углы) - классика | new до правки | new после.

Источник - shot.png (кадр игры без пара заморозки, R-251) из _dumps/<метка>; «до правки» - резерв
_backup_before_edgefix_20261007/dumps/new_<ракурс>. Числа края - Y выступа у ряда y = 59 против тела клетки.

    py -3.13 tools/hdart/crossing_control.py        # census/maps/pilot2/probe_crossing/control.png, control.json
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crossing_build as cb         # noqa: E402

D = cb.OUT / "_dumps"
BK = cb.OUT / "_backup_before_edgefix_20261007" / "dumps"
FONT = ImageFont.truetype(cb.sp.js.FONT, 18)
LUMA = cb.LUMA
# (ракурс, подпись, узлы сетки рамки (gx0, gy0, gx1, gy1), увеличение)
CROPS = [("e2c", "край карты: ряд y = 59 (кадр 0 тротуара) и решётки у края", (24, 54, 38, 60), 1),
         ("v3", "перекрёсток: вершина V (55,12), разметка, углы бордюра", (50, 9, 59, 16), 1),
         ("v3", "крупно: вершина V и концы штрихов", (53, 10, 57, 14), 2),
         ("e2c", "крупно: край карты у x 29-33", (28, 57, 34, 60), 2)]


def shot(path):
    js_d = json.loads((path.parent / "dump.json").read_text(encoding=cb.ENC))
    k = int(js_d["k"])
    cam = (int(js_d["cameraOffsetX"]) // k, int(js_d["cameraOffsetY"]) // k, int(js_d["cameraOffsetZ"]))
    return np.asarray(Image.open(path).convert("RGB")), k, cam


def box(nodes, k, cam, H, W):
    gx0, gy0, gx1, gy1 = nodes
    pts = [cb.grid_xy(x, y, k, cam) for x in (gx0, gx1) for y in (gy0, gy1)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    m = 6 * k
    return (int(max(0, min(xs) - m)), int(max(0, min(ys) - 12 * k)), int(min(W, max(xs) + m)), int(min(H, max(ys) + m)))


def edge_numbers(im, k, cam, xs=range(26, 37), gy=59):
    """Y экрана сразу за краем карты (выступ, ниже ребра +v) и тела у края, по клеткам ряда gy."""
    H, W = im.shape[:2]
    Yi, Xi = np.mgrid[0:H, 0:W].astype(np.float32)
    sx, sy = (Xi + 0.5) / k - cam[0] - 16, (Yi + 0.5) / k - cam[1] - 24
    gu, gv = (sx / 16 + sy / 8) / 2, (sy / 8 - sx / 16) / 2
    lum = im.astype(np.float32) @ LUMA
    sel = (gu >= xs.start) & (gu < xs.stop)
    out_m = sel & (gv >= gy + 1) & (gv < gy + 1 + 0.25)
    body = sel & (gv >= gy + 0.75) & (gv < gy + 1)
    lit = lum > 3                                       # за краем карты - чёрный фон; непрозрачный выступ светлее
    return dict(tooth_px=int((out_m & lit).sum()), tooth_y=round(float(lum[out_m & lit].mean()), 1) if (out_m & lit).any()
                else None, body_y=round(float(lum[body].mean()), 1))


def main():
    rows, info = [], {}
    for view, label, nodes, z in CROPS:
        srcs = [("классика", D / ("classic_%s" % view) / "shot.png"), ("new до правки", BK / ("new_%s" % view) / "shot.png"),
                ("new после", D / ("new_%s" % view) / "shot.png")]
        ims = [(n,) + shot(p) for n, p in srcs]
        _n, im0, k, cam = ims[0]
        b = box(nodes, k, cam, *im0.shape[:2])
        tiles = []
        for n, im, kk, cc_ in ims:
            if (kk, cc_) != (k, cam):
                raise SystemExit("%s: камера %s против %s" % (n, (kk, cc_), (k, cam)))
            c = Image.fromarray(im[b[1]:b[3], b[0]:b[2]])
            if z > 1:
                c = c.resize((c.width * z, c.height * z), Image.NEAREST)
            t = Image.new("RGB", (c.width, c.height + 26), (24, 24, 28))
            ImageDraw.Draw(t).text((4, 3), n, font=FONT, fill=(255, 255, 255))
            t.paste(c, (0, 26))
            tiles.append(t)
            if view == "e2c" and z == 1:
                info[n] = edge_numbers(im, k, cam)
        horiz = tiles[0].width * 3 <= 4200
        w = tiles[0].width * 3 + 16 if horiz else tiles[0].width
        h = tiles[0].height + 30 if horiz else 3 * (tiles[0].height + 8) + 30
        row = Image.new("RGB", (w, h), (24, 24, 28))
        ImageDraw.Draw(row).text((6, 4), "%s (ракурс %s)" % (label, view), font=FONT, fill=(255, 220, 120))
        for i, t in enumerate(tiles):
            row.paste(t, ((i * (t.width + 8), 30) if horiz else (0, 30 + i * (t.height + 8))))
        rows.append(row)
    W = max(r.width for r in rows)
    out = Image.new("RGB", (W, sum(r.height + 10 for r in rows) + 34), (24, 24, 28))
    ImageDraw.Draw(out).text((8, 6), "ROADS: контрольный кадр после правок края карты и концов разметки - кадры игры "
                             "без пара, k=4", font=FONT, fill=(255, 255, 255))
    y = 34
    for r in rows:
        out.paste(r, (0, y))
        y += r.height + 10
    out.save(cb.OUT / "control.png")
    (cb.OUT / "control.json").write_text(json.dumps(dict(edge_row_y59=info), ensure_ascii=False, indent=1),
                                         encoding=cb.ENC)
    for n, v in info.items():
        print("край y=59, %s: %s" % (n, v))
    print(cb.OUT / "control.png", out.size)


if __name__ == "__main__":
    main()
