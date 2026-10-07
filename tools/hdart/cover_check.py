"""Сколько силуэта оригинала закрыл нарисованный кадр серии предметов - без видеокарты.

Модель перерисовывает форму: лестницу-клин рисует тонким пролётом, откос - полоской цветов, и часть
силуэта оригинала остаётся пустой. На листе в уменьшении это не видно, на карте - дыра в предмете.
Считаем по каждому кадру серии (и по составному целиком):
  cover - доля непрозрачных пикселей оригинала x4, которые непрозрачны и в новом кадре;
  spill - непрозрачное в новом там, где у оригинала пусто, в долях силуэта оригинала.
Строки с cover ниже порога - в брак (<out>/cover.tsv, по возрастанию cover).

  py -3.13 tools/hdart/cover_check.py [--out art/objects] [--min 0.85]
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import map_mockup as mm          # noqa: E402
import obj_series as os_         # noqa: E402

ENC = "utf-8-sig"


def alpha(im, thr=128):
    return np.asarray(im.convert("RGBA"))[:, :, 3] >= thr


def score(orig, new):
    """(cover, spill, semi): semi - полупрозрачное (1..127) внутри силуэта оригинала - вырезана как фон
    часть тела цвета подложки (тёмное одеяло на тёмной панели, R-089)."""
    a, b = alpha(orig), alpha(new)
    na = np.asarray(new.convert("RGBA"))[:, :, 3]
    n = max(1, int(a.sum()))
    return (a & b).sum() / n, (b & ~a).sum() / n, (a & (na > 0) & (na < 128)).sum() / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="art/objects")
    ap.add_argument("--maps", type=int, default=47)
    ap.add_argument("--min", type=float, default=0.85, dest="min_cover")
    ap.add_argument("--semi", type=float, default=0.10, dest="max_semi")
    args = ap.parse_args()
    series = os.path.join(args.out, "series")
    world = mm.World()
    rows, mass, singles = [], set(), {}
    for t, b, _h, fobj in os_.map_list(args.maps):
        try:
            objs, _anim, field = os_.objects_of(world, t, b, fobj)
        except Exception:                                       # noqa: BLE001
            continue
        rows.append((t, b))
        mass |= set(field)
        for key, d in objs.items():
            singles.setdefault(key, d["spr"])
    comps = os_.composites(world, rows, mass)
    in_comp = {k for c in comps for k, _o in c["members"]}

    def load(key):
        p = os.path.join(series, "%s.PCK" % key[0], "%d.png" % key[1])
        return Image.open(p).convert("RGBA") if os.path.exists(p) else None

    res = []
    for c in comps:
        keys = [k for k, _o in c["members"]]
        got = {k: load(k) for k in keys}
        if any(v is None for v in got.values()):
            continue
        res.append(score(os_.compose(c, None, 4)[0], os_.compose(c, got, 4)[0])
                   + ("составной", "%s:%d" % keys[0], len(keys)))
    for key, spr in singles.items():
        if key in in_comp or key in mass:
            continue
        new = load(key)
        if new is None:
            continue
        res.append(score(spr.convert("RGBA").resize((128, 160), Image.NEAREST), new)
                   + ("одиночный", "%s:%d" % key, 1))
    res.sort()
    bad = [r for r in res if r[0] < args.min_cover]
    holes = [r for r in res if r[2] >= args.max_semi]
    path = os.path.join(args.out, "cover.tsv")
    with open(path, "w", encoding=ENC) as f:
        f.write("cover\tspill\tsemi\tвид\tкадр\tкусков\n")
        for r in res:
            f.write("%.3f\t%.3f\t%.3f\t%s\t%s\t%d\n" % r)
    print("проверено %d, cover < %.2f: %d, semi >= %.2f: %d -> %s"
          % (len(res), args.min_cover, len(bad), args.max_semi, len(holes), path))
    for r in bad[:40]:
        print("  cover %.3f  spill %.3f  semi %.3f  %s %s (%d)" % r)
    print("полупрозрачное в теле:")
    for r in sorted(holes, key=lambda r: -r[2])[:30]:
        print("  cover %.3f  spill %.3f  semi %.3f  %s %s (%d)" % r)


if __name__ == "__main__":
    main()
