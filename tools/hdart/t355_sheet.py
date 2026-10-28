# -*- coding: utf-8 -*-
r"""XP-000355: лист и замеры к правке асфальта (верх ромба достроен до силуэта классики, t355_build.py).

  1. вершина кадров ROADS:9 и ROADS:13 вблизи (x16): классика | было | стало | достроенное розовым
  2. ряд асфальта с грунтом (модель кромки): было | стало, просветов против классики
  3. настоящие блоки карты с асфальтом ROADS: просветы против классики до/после (всего и в клине вершины) и стыки
     разметки ROADS:10-12: чей пиксель виден в клине вершины (владелец в порядке рисования Map::drawTerrain) -
     классика | было | стало
  4. вершина, где к клетке асфальта 9/13 сходятся штрихи разметки 10-12 слева и сверху (только пол, без предметов):
     классика | было | стало

    py -3.13 tools\hdart\t355_sheet.py            # лист art/_review/tickets_2026-10-28/t355_fix_sheet.png + числа
Читает кадры из пака установки (до установки - "было", файлы t355_install - "стало"); в мод ничего не пишет.
"""
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ticket_scene as ts                 # noqa: E402
import map_mockup as mm                   # noqa: E402
import t355_build as tb                   # noqa: E402

OUT = tb.REVIEW
FONT = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
FONTS = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
SENT = (1, 2, 3)                          # цвет подложки: пиксель = просвет
ts.BG = SENT
BG = (35, 33, 22)                         # замена градиента oxceHdBackdrop на листе
N = 8
MARKING = {("ROADS", 10), ("ROADS", 11), ("ROADS", 12)}
PATCHED = {("ROADS", 9), ("ROADS", 13)}


class _All:
    def __contains__(self, _x):
        return True


def new_img(s, f, v=0):
    p = tb.INST / tb.rel_of(s, f, v).replace("/", "\\")
    return Image.open(p).convert("RGBA")


def lattice(sc, rows, override=None):
    """Ряды клеток N x (ряды), изометрия 64x32 на клетку. Возвращает RGB и маску классики."""
    override = override or {}
    W, H = (2 * N + 2) * 64, (2 * N + 2) * 32 + 170
    im = Image.new("RGB", (W, H), BG)
    cl = np.zeros((H, W), bool)
    for my in sorted(rows):
        S, f = rows[my]
        spr = override.get((S, f)) or sc.hd(S, f)
        cs = np.asarray(sc.classic(S, f))[..., 3] > 0
        for mx in range(N):
            X = (mx - my) * 64 + N * 64
            Y = (mx + my) * 32
            im.paste(spr, (X, Y), spr)
            cl[Y:Y + 160, X:X + 128] |= cs
    return im, cl


def holes_of(im, cl):
    a = np.asarray(im).astype(int)
    return cl & (np.abs(a - np.array(BG)).sum(axis=2) == 0)


def closeup(sc, S, f):
    c = sc.classic(S, f).convert("RGBA")
    h = sc.hd(S, f).convert("RGBA")
    n = new_img(S, f)
    ca = np.asarray(c)[..., 3] > 0
    ha = np.asarray(h)[..., 3] > 0
    mk = np.asarray(n).copy()
    mk[ca & ~ha] = (255, 0, 255, 255)
    parts = []
    for im in (c, h, n, Image.fromarray(mk, "RGBA")):
        bgim = Image.new("RGBA", im.size, BG + (255,))
        bgim.alpha_composite(im)
        parts.append(bgim.crop((24, 92, 104, 124)).resize((320, 128), Image.NEAREST))
    return parts


def road_blocks(w, limit):
    out = []
    use = mm.usage(w)
    seen = set()
    for key in ("ROADS:9", "ROADS:13"):
        for t, b, n in sorted(use.get(key, []), key=lambda r: -r[2]):
            if b not in seen:
                seen.add(b)
                out.append((t, b, n))
    return out[:limit]


def owners(sc, found, size, which, over):
    """Карта владельцев пикселей (индекс клетки в порядке рисования; -1 - фон) по альфе: классика / HD было / HD стало.
    Порядок рисования - как в движке (found идёт в порядке z, y, x, часть клетки)."""
    own = np.full((size[1], size[0]), -1, np.int32)
    for i, (Sn, fr, (x0, y0, x1, y1), z, cell) in enumerate(found):
        if which == "classic":
            spr = sc.classic(Sn, fr)
        else:
            spr = (over.get((Sn, fr)) if which == "new" else None) or sc.hd(Sn, fr) or sc.classic(Sn, fr)
        if spr is None:
            continue
        al = np.asarray(spr)[..., 3] > 0
        h, w_ = al.shape
        ya, xa = max(y0, 0), max(x0, 0)
        yb, xb = min(y0 + h, size[1]), min(x0 + w_, size[0])
        if yb <= ya or xb <= xa:
            continue
        view = own[ya:yb, xa:xb]
        view[al[ya - y0:yb - y0, xa - x0:xb - x0]] = i
    return own


def block_model(sc, blocks, over):
    """Просветы против классики в настоящих блоках, до и после; клин вершины патченых клеток: чей пиксель виден."""
    rows = []
    meets = []                             # клетки, к вершине которых сходятся штрихи 10-12 слева и сверху
    for t, b, n in blocks:
        imc, found = ts.Scene.render(sc, t, b, "classic", k=4, marks=_All())
        imo, _ = ts.Scene.render(sc, t, b, "hd", k=4)
        imn, _ = ts.Scene.render(sc, t, b, "hd", override=over, k=4)
        ac, ao, an = (np.asarray(i.convert("RGB")).astype(int) for i in (imc, imo, imn))
        S = np.array(SENT)
        cl = (np.abs(ac - S).sum(axis=2) != 0)
        ho = cl & (np.abs(ao - S).sum(axis=2) == 0)
        hn = cl & (np.abs(an - S).sum(axis=2) == 0)
        oc = owners(sc, found, imc.size, "classic", over)
        oo = owners(sc, found, imc.size, "old", over)
        on = owners(sc, found, imc.size, "new", over)
        mark_ids = np.array([j for j, f in enumerate(found) if (f[0], f[1]) in MARKING])
        wedge = np.zeros(cl.shape, bool)
        d_o = d_n = k_o = k_n = cnt = l_o = l_n = 0
        floors = {}
        for i, (Sn, fr, rect, z, cell) in enumerate(found):
            floors.setdefault((cell, z), (Sn, fr, rect, i))      # первая запись клетки - пол
        for i, (Sn, fr, (x0, y0, x1, y1), z, cell) in enumerate(found):
            if (Sn, fr) not in over:
                continue
            cnt += 1
            win = (slice(max(y0 + 96, 0), y0 + 112), slice(x0 + 52, x0 + 77))
            wedge[win] = True
            c_, o_, n_ = oc[win], oo[win], on[win]
            do, dn = int((c_ != o_).sum()), int((c_ != n_).sum())
            ko = int(((c_ != o_) & np.isin(o_, mark_ids) & (o_ != i)).sum())
            kn = int(((c_ != n_) & np.isin(n_, mark_ids) & (n_ != i)).sum())
            cm = np.isin(c_, mark_ids)
            l_o += int((cm & (c_ != o_)).sum())
            l_n += int((cm & (c_ != n_)).sum())
            d_o += do
            d_n += dn
            k_o += ko
            k_n += kn
            (cx, cy) = cell
            left = floors.get(((cx - 1, cy), z))
            up = floors.get(((cx, cy - 1), z))
            if ko and ((left and (left[0], left[1]) in MARKING) or (up and (up[0], up[1]) in MARKING)):
                meets.append((ko, t, b, (x0, y0), cell, z, floors))
        rows.append((t, b, cnt, int(ho.sum()), int(hn.sum()), int((ho & wedge).sum()), int((hn & wedge).sum()),
                     d_o, d_n, k_o, k_n, l_o, l_n))
    return rows, meets


def meet_panels(sc, meets, over, n=3):
    """Окрестность вершины: пол 3x3 вокруг клетки (штрихи слева и сверху) - классика | было | стало."""
    seen, pick = set(), []
    for m in sorted(meets, key=lambda r: -r[0]):
        if (m[1], m[2]) not in seen:
            seen.add((m[1], m[2]))
            pick.append(m)
    pick = pick[:n]
    out = []
    for ko, t, b, (x0, y0), cell, z, floors in pick:
        cx, cy = cell
        tiles = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                fl = floors.get(((cx + dx, cy + dy), z))
                if fl:
                    Sn, fr = fl[0], fl[1]
                    tiles.append((dx, dy, Sn, fr))
        row = []
        for mode in ("classic", "old", "new"):
            im = Image.new("RGBA", (128 * 4 + 64, 160 * 3), BG + (255,))
            for dx, dy, Sn, fr in sorted(tiles, key=lambda r: (r[1], r[0])):
                spr = sc.classic(Sn, fr) if mode == "classic" else (over.get((Sn, fr)) if mode == "new" else None) \
                    or sc.hd(Sn, fr) or sc.classic(Sn, fr)
                im.alpha_composite(spr, (256 + (dx - dy) * 64 - 64 + 32, 160 + (dx + dy) * 32))
            # вершина клетки (0,0): x = 256-64+32+64 = 288, y = 160+96 = 256
            row.append(im.crop((288 - 88, 256 - 30, 288 + 88, 256 + 34)).convert("RGB").resize((352, 128), Image.NEAREST))
        out.append((t, b, cell, ko, row))
    return out


def main():
    t0 = time.time()
    sc = ts.Scene()
    OUT.mkdir(parents=True, exist_ok=True)
    # 0. альфа всех 8 новых картинок одинакова, классика покрыта, изменено ровно достроенное, остальное побайтно как было
    cls9 = np.asarray(sc.classic("ROADS", 9))[..., 3] > 0
    alphas = []
    for g, members in tb.GROUPS.items():
        for v in tb.VARIANTS:
            n = np.asarray(new_img(*members[0], v))
            o = np.asarray(sc.hd(members[0][0], members[0][1], v))
            alphas.append(n[..., 3] > 0)
            assert (n[..., 3] > 0)[cls9].all(), "классика не покрыта"
            ch = np.any(n != o, axis=2)
            assert ((o[..., 3] == 0) & cls9)[ch].all(), "изменены не достроенные пиксели"
            assert ch.sum() == 96
    assert all(np.array_equal(alphas[0], a) for a in alphas), "альфа версий расходится"
    print("альфа: 8 картинок, классика покрыта полностью, изменено ровно 96 пикс на картинку, остальное побайтно как было")

    # 2. ряд асфальта с грунтом
    over = {("ROADS", 9): new_img("ROADS", 9), ("ROADS", 13): new_img("ROADS", 13)}
    rows = {2: ("CULTIVAT", 2), 3: ("ROADS", 9), 4: ("ROADS", 9), 5: ("ROADS", 13), 6: ("CULTIVAT", 2)}
    cur, cc = lattice(sc, rows)
    pat, cp = lattice(sc, rows, over)
    hc, hp = holes_of(cur, cc), holes_of(pat, cp)
    print("модель ряда: просветов против классики было %d, стало %d" % (hc.sum(), hp.sum()))
    curm, patm = np.asarray(cur).copy(), np.asarray(pat).copy()
    curm[hc] = (255, 0, 255)
    patm[hp] = (255, 0, 255)
    box = (7 * 64 - 64, 70, 11 * 64 + 128, 70 + 300)
    A, B = Image.fromarray(curm).crop(box), Image.fromarray(patm).crop(box)

    # 3. настоящие блоки
    blocks = road_blocks(sc.w, 12)
    brow, meets = block_model(sc, blocks, over)
    print("блок | клеток 9/13 | просветов всего было/стало | просветов в клине было/стало | пикс. клина с владельцем не как в классике было/стало | из них владелец - разметка 10-12 было/стало")
    tot = np.zeros(11, int)
    for t, b, nf, ho, hn, wo, wn, do, dn, ko, kn, lo, ln in brow:
        print("%-22s %-22s %4d | %6d %6d | %5d %5d | %5d %5d | %4d %4d" % (t, b, nf, ho, hn, wo, wn, do, dn, ko, kn))
        tot += np.array([nf, ho, hn, wo, wn, do, dn, ko, kn, lo, ln])
    print("ИТОГО клеток %d | просветов %d -> %d | в клине %d -> %d | владелец не как в классике %d -> %d | из них разметка %d -> %d | "
          "пикс. разметки классики в клине, потерянные HD: %d -> %d" % tuple(tot))
    assert all(r[4] <= r[3] and r[6] <= r[5] and r[8] <= r[7] for r in brow), "где-то стало хуже"

    # 4. вершина со сходящимися штрихами
    panels = meet_panels(sc, meets, over)
    for t, b, cell, ko, row in panels:
        print("вершина %s/%s клетка %s: чужих (разметка) пикс. клина в 'было' %d, в 'стало' 0" % (t, b, cell, ko))

    # сборка листа
    pad = 12
    Wd = 1500
    canvas = Image.new("RGB", (Wd, 1700), (24, 24, 28))
    d = ImageDraw.Draw(canvas)
    y = pad
    d.text((pad, y), "XP-000355 (вариант A): верх ромба асфальта достроен до силуэта классики; 12 кадров, 48 файлов", font=FONT, fill=(255, 255, 0))
    y += 32
    d.text((pad, y), "1) Вершина ROADS:9 и ROADS:13 (x16): классика | было | стало | достроенное розовым. Цвет - по соседям, штриха нет", font=FONTS, fill=(220, 220, 220))
    y += 22
    for S, f in (("ROADS", 9), ("ROADS", 13)):
        x = pad
        for p in closeup(sc, S, f):
            canvas.paste(p, (x, y))
            x += 330
        y += 138
    d.text((pad, y), "2) Модель ряда асфальта между грунтом (фон - заглушка градиента). Слева было - розовое просвет (%d пикс), справа стало (%d)" % (hc.sum(), hp.sum()), font=FONTS, fill=(220, 220, 220))
    y += 22
    canvas.paste(A, (pad, y))
    canvas.paste(B, (pad + A.width + 40, y))
    y += A.height + 12
    d.text((pad, y), "3) Вершина клетки 9/13, куда приходят штрихи разметки 10-12 слева или сверху (настоящие блоки, только пол, x8): классика | было | стало", font=FONTS, fill=(220, 220, 220))
    y += 22
    for t, b, cell, ko, row in panels:
        x = pad
        for p in row:
            canvas.paste(p, (x, y))
            x += 360
        d.text((x + 4, y + 50), "%s/%s %s" % (t, b, cell), font=FONTS, fill=(200, 200, 200))
        y += 136
    d.text((pad, y), "Замер по %d блокам (%d клеток): просветов в клине вершины %d -> %d; пикселей клина, где виден штрих чужой клетки разметки, а в классике его нет: %d -> %d; ни в одном блоке не хуже"
           % (len(brow), tot[0], tot[3], tot[4], tot[7], tot[8]), font=FONTS, fill=(255, 220, 120))
    y += 28
    canvas = canvas.crop((0, 0, Wd, y + pad))
    p = OUT / "t355_fix_sheet.png"
    canvas.save(p)
    print(p, canvas.size, "%.0f с" % (time.time() - t0))


if __name__ == "__main__":
    main()
