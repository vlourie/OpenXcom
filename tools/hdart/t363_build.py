# -*- coding: utf-8 -*-
r"""Тикет XP-000363 (выбор Vitali 28.10: вариант A): края куска асфальта по песку в пустыне - языки песка
XOPSDESERTRUINS 41-46 (побайтные копии XOPSDESERT 87-92) и воронка XOPSDESERTRUINS 37/38 (побайтные копии
ROADS_WASTE 18/19) - 16 файлов. Процедурно, без видеокарты. Вывод - art/_review/tickets_2026-10-28/t363_install/TERRAIN/...
+ MANIFEST.json; в мод - только --install --yes под очередью правок (CLAUDE.md).

Что было не так (разбор 28.10, лист t363_sheet.png):
  * язык песка (часть клетки 3 поверх асфальта) в HD - размытое кольцо альфы и ступени классики 8x4; асфальт под ним
    доведён до точного ромба (R-247), язык эту кромку не закрывал - по рёбрам ромба тёмный пунктир;
  * песок языка (sdxl_legacy) контрастнее песка земли (СКО 31-34 против 22) - каждый язык читался заплаткой-коробкой;
  * воронка 38 (= ROADS_WASTE:19) - скошенный люк с заклёпками, а в классике красноватое пятно по асфальту.

Лечение:
  41-46 / XOPSDESERT 87-92  альфа = мягкая маска классики x4 (blur 1.3), продолженная за ромб ближайшим значением (край
        клетки сплошной), и силуэт классики x4 плюс точный ромб, как у асфальта под языком (R-247); цвет - HD песок
        XOPSDESERT:42 в тех же координатах клетки (R-249), затенение у кромки - по яркости классики языка,
        множитель 0.80-1.06 (R-265: клетку целиком по низким частотам не переносить).
  37/38 / ROADS_WASTE 18/19  t352_build.build_crack: текстура асфальта 9 и красноватость трещин классики, затухающая
        к кромке ромба (шов с асфальтом 9 не виден).

    py -3.13 tools\hdart\t363_build.py                    # кадры + MANIFEST.json + проверки (без записи в мод)
    py -3.13 tools\hdart\t363_build.py --sheet            # + лист t363_fix_sheet.png (классика / было / стало, участок карты сейва)
    py -3.13 tools\hdart\t363_build.py --install --yes    # + в мод hd через манифест (ТОЛЬКО под очередью правок)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_seam as gs                  # noqa: E402
import t249_asphalt_edge as t249          # noqa: E402
import t352_build as t352                 # noqa: E402  (трещины 18/19)
import ticket_scene as ts                 # noqa: E402
import water_build as wb                  # noqa: E402

ROOT = HERE.parent.parent
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-28"
INST = REVIEW / "t363_install"
SAVE = ROOT / "census" / "tickets" / "XP-000363" / "files" / "02__autobattle_.asav"
TONGUES = list(range(41, 47))                       # XOPSDESERTRUINS 41-46
TWIN = {f: ("XOPSDESERT", f + 46) for f in TONGUES}  # побайтные копии классики: XOPSDESERT 87-92
CRACKS = {18: ("XOPSDESERTRUINS", 37), 19: ("XOPSDESERTRUINS", 38)}
SAND_REF = ("XOPSDESERT", 42)                       # чистый песок земли пустыни, HD
BLUR = 1.3                                          # мягкость маски языка, пикс HD
SHADE_MIN, SHADE_MAX = 0.80, 1.06
SHADE_SIG = 1.4


def tongue(f, tex=None):
    """Кадр языка песка по маске классики; tex - HD песок земли (RGB 160x128), по умолчанию XOPSDESERT:42."""
    pal = wb.palette()
    a = wb.read_set("XOPSDESERTRUINS")[f]
    ca = wb.read_set("XOPSDESERT")[SAND_REF[1]]
    fp = ca > 0                                     # след клетки в классике (ступенчатый ромб)
    m = (a > 0).astype(np.float32)
    idx = ndi.distance_transform_edt(~fp, return_distances=False, return_indices=True)
    m = m[idx[0], idx[1]]                           # маска продолжена за ромб: край клетки не размывается
    mask = wb.soft_mask(m, BLUR)
    inside = np.maximum(wb.blk(fp), (gs.dmap() <= 1.0).astype(np.float32))   # как альфа асфальта под языком (R-247)
    al = mask * inside
    if tex is None:
        tex = t249.extend(t249.load_hd(*SAND_REF))
    ref = float((pal[ca[ca > 0]][:, :3] @ gs.LUMA).mean())
    mm = (a > 0).astype(np.float32)
    luma = (pal[a][..., :3].astype(np.float32) @ gs.LUMA) * mm
    num = wb.gauss(luma, SHADE_SIG)
    den = np.maximum(wb.gauss(mm, SHADE_SIG), 1e-3)
    shade = np.clip(num / den / ref, SHADE_MIN, SHADE_MAX)
    shade = np.asarray(Image.fromarray(shade.astype(np.float32), "F").resize((128, 160), Image.BICUBIC))
    rgb = tex * shade[..., None]
    out = np.dstack([np.clip(rgb, 0, 255), al * 255]).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def build_all():
    # классика копий побайтно равна основе (ticket_family.py): один кадр кладётся в оба набора
    for f, (s2, f2) in TWIN.items():
        assert np.array_equal(wb.read_set("XOPSDESERTRUINS")[f], wb.read_set(s2)[f2]), "классика %d != %s:%d" % (f, s2, f2)
    for f, (s2, f2) in CRACKS.items():
        assert np.array_equal(wb.read_set("ROADS_WASTE")[f], wb.read_set(s2)[f2]), "классика ROADS_WASTE %d != %s:%d" % (f, s2, f2)
    tex_sand = t249.extend(t249.load_hd(*SAND_REF))
    tex_asph = t249.extend(t249.load_hd(*t249.ASPH_SRC))
    res = {}
    for f in TONGUES:
        im = tongue(f, tex_sand)
        res[("XOPSDESERTRUINS", f)] = im
        res[TWIN[f]] = im
    for f, (s2, f2) in CRACKS.items():
        im = t352.build_crack(f, tex_asph)
        res[("ROADS_WASTE", f)] = im
        res[(s2, f2)] = im
    return res


def save_all(res):
    files = {}
    for (s, f), im in sorted(res.items()):
        rel = "TERRAIN/%s.PCK/%d.png" % (s, f)
        p = INST / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        im.save(p, optimize=True)
        files[rel] = p
    man = {"ticket": "XP-000363", "generator": "t363_build.py", "variant": "A",
           "note": "языки песка XOPSDESERTRUINS 41-46 = XOPSDESERT 87-92; воронка XOPSDESERTRUINS 37/38 = ROADS_WASTE 18/19",
           "files": {r: hashlib.sha256(p.read_bytes()).hexdigest() for r, p in files.items()}}
    (INST / "MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    return files


def check(files):
    """Размер и режим, копии побайтно равны, альфа языков внутри клетки, цвет языка близок к песку земли."""
    ref = np.asarray(ts.Scene().hd(*SAND_REF)).astype(np.float32)
    ym = ref[..., 3] > 0
    yref = (ref[..., :3] @ gs.LUMA)[ym]
    for rel, p in files.items():
        im = Image.open(p)
        assert im.size == (128, 160) and im.mode == "RGBA", (rel, im.size, im.mode)
    for f in TONGUES:
        a = files["TERRAIN/XOPSDESERTRUINS.PCK/%d.png" % f].read_bytes()
        b = files["TERRAIN/%s.PCK/%d.png" % TWIN[f]].read_bytes()
        assert a == b, "копия языка %d не равна основе" % f
        arr = np.asarray(Image.open(files["TERRAIN/XOPSDESERTRUINS.PCK/%d.png" % f])).astype(np.float32)
        full = arr[..., 3] > 200
        y = (arr[..., :3] @ gs.LUMA)[full]
        out_cell = (arr[..., 3] > 0) & ~(np.maximum(wb.blk(wb.read_set("XOPSDESERT")[42] > 0), (gs.dmap() <= 1.0)) > 0)
        assert not out_cell.any(), "язык %d: альфа за клеткой" % f
        print("  язык %d: непрозрачных %d, Y %.1f (песок земли %.1f), СКО %.1f (земли %.1f)" % (f, full.sum(), y.mean(), yref.mean(), y.std(), yref.std()))
        assert abs(y.mean() - yref.mean()) < 12, "тон языка %d далёк от песка" % f
    for f, (s2, f2) in CRACKS.items():
        assert files["TERRAIN/ROADS_WASTE.PCK/%d.png" % f].read_bytes() == files["TERRAIN/%s.PCK/%d.png" % (s2, f2)].read_bytes()
    print("проверки: %d файлов, размер 128x160 RGBA, копии побайтно равны, альфа в клетке, тон языков = песок земли" % len(files))


def notches(files):
    """Впадины ступеней у рёбер ромба, где рядом песок классики: асфальт под языком там есть (R-247), язык обязан
    закрывать (прежний HD не закрывал - тёмный пунктир). Возвращает (всего, не закрыто было, не закрыто стало)."""
    d = gs.dmap()
    ca = wb.read_set("XOPSDESERT")[SAND_REF[1]] > 0
    fp4 = np.maximum(wb.blk(ca), (d <= 1.0)) > 0
    idx = ndi.distance_transform_edt(~ca, return_distances=False, return_indices=True)
    sc = ts.Scene()
    tot = [0, 0, 0]
    for f in TONGUES:
        a = wb.read_set("XOPSDESERTRUINS")[f]
        m = (a > 0).astype(np.uint8)[idx[0], idx[1]]
        notch = fp4 & ~(wb.blk(ca) > 0) & (np.kron(m, np.ones((4, 4), np.uint8)) > 0)
        old = np.asarray(sc.hd("XOPSDESERTRUINS", f))[..., 3]
        new = np.asarray(Image.open(files["TERRAIN/XOPSDESERTRUINS.PCK/%d.png" % f]))[..., 3]
        tot[0] += int(notch.sum())
        tot[1] += int((notch & (old < 128)).sum())
        tot[2] += int((notch & (new < 128)).sum())
    return tuple(tot)


# ---------------------------------------------------------------- лист: участок карты сейва XP-000363
def _cells(bt, data, x0, x1, y0, y1):
    out = []
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            for p in range(4):
                v = bt.part(0, y, x, p)
                if not v or v[0] < 0 or v[0] >= len(bt.sets):
                    continue
                name = bt.sets[v[0]]
                if name == "BLANKS":
                    continue
                recs = data.mcd(name)
                if v[1] < 0 or v[1] >= len(recs):
                    continue
                r = recs[v[1]]
                out.append((y, x, p, name, r["frames"][0], r["yoff"]))
    return out


def _render(sc, cl, mode, k, over=None):
    over = over or {}
    X = Y = 60
    im = Image.new("RGBA", (((X + Y) * 16 + 32) * k, ((X + Y) * 8 + 10 * 24 + 40) * k), ts.BG + (255,))
    ox, oy = Y * 16, 10 * 24 + 8
    for (y, x, p, name, fr, yoff) in cl:
        S = name.upper()
        if mode == "classic":
            spr = sc.classic(S, fr)
        else:
            spr = over.get((S, fr))
            if spr is None:
                spr = sc.hd(S, fr)
                if spr is not None and p == 0:
                    vs = sc.variants(S, fr)
                    if vs:
                        n = (x // 3 * 7919 + y // 3 * 104729) * 2654435761 % 4294967296
                        j = n % (len(vs) + 1)
                        spr = spr if j == 0 else vs[j - 1]
            if spr is None:
                spr = sc.classic(S, fr)
        if spr is None:
            continue
        if spr.width != 32 * k:
            spr = spr.resize((32 * k, 40 * k), Image.NEAREST if mode == "classic" else Image.LANCZOS)
        im.alpha_composite(spr, ((ox + (x - y) * 16) * k, (oy + (x + y) * 8 - yoff) * k))
    return im


def make_sheet(res):
    from PIL import ImageDraw
    sys.path.insert(0, str(HERE))
    import map_truth as mt
    bt = mt.Battle(SAVE)
    data = mt.Data(bt.mods)
    cl = _cells(bt, data, 6, 19, 34, 52)
    sc = ts.Scene()
    over = {k: v for k, v in res.items()}
    K = 4
    ims = [_render(sc, cl, "classic", K), _render(sc, cl, "hd", K), _render(sc, cl, "hd", K, over)]
    names = ["классика", "было (HD до правки)", "стало (вариант A)"]
    boxes = [(190 * K, 640 * K, 560 * K, 760 * K), (400 * K, 665 * K, 520 * K, 735 * K), (452 * K, 688 * K, 508 * K, 722 * K)]
    zoom = [1, 2, 6]
    caps = ["участок карты сейва (x4)", "край языков песка (x8)", "воронка 38, северо-восток (x24)"]
    W = 900
    rows = []
    fnt = ts.font(20)
    for box, z, cap in zip(boxes, zoom, caps):
        row = []
        for i, im in enumerate(ims):
            c = im.crop(box).convert("RGB")
            c = c.resize((W, int(c.height * W / c.width)), Image.NEAREST if (i == 0 or z >= 6) else Image.LANCZOS)
            d = ImageDraw.Draw(c)
            d.rectangle((0, 0, c.width, 26), fill=(15, 15, 18))
            d.text((6, 3), "%s - %s" % (names[i], cap), fill=(255, 220, 0), font=fnt)
            row.append(c)
        rows.append(row)
    G = 8
    H = sum(max(p.height for p in r) + G for r in rows) + G
    sheet = Image.new("RGB", (3 * W + 4 * G, H), (12, 12, 14))
    y = G
    for r in rows:
        for i, p in enumerate(r):
            sheet.paste(p, (G + i * (W + G), y))
        y += max(p.height for p in r) + G
    out = REVIEW / "t363_fix_sheet.png"
    sheet.save(out)
    return out, ims


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    res = build_all()
    files = save_all(res)
    print("кадров: %d, файлов: %d -> %s" % (len({id(v) for v in res.values()}), len(files), INST))
    check(files)
    n_all, n_old, n_new = notches(files)
    print("впадины у рёбер ромба (асфальт под языком, рядом песок классики): %d пикс, не закрыты языком: было %d, стало %d" % (n_all, n_old, n_new))
    assert n_new <= 0.02 * n_all, "язык не закрывает край клетки"
    if a.sheet:
        out, ims = make_sheet(res)
        print("лист:", out)
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только под очередью правок)")
        n = ts.install_files(files, "t363_build", "t363_build.py 28.10: языки песка по маске классики, песок HD XOPSDESERT:42; воронка - t352_build.build_crack",
                             "Vitali 28.10: вариант A по тикету XP-000363; лист art/_review/tickets_2026-10-28/t363_fix_sheet.png",
                             "t363: языки песка XOPSDESERTRUINS 41-46 / XOPSDESERT 87-92 и воронка 37/38 / ROADS_WASTE 18/19 - по маске классики")
        print("установлено файлов:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
