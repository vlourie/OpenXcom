# -*- coding: utf-8 -*-
r"""Тикет XP-000365 (пол вышки связи: пятна света от ламп C_INT:6) - вариант A, выбор Vitali 29.10.
Процедурно по классике, без видеокарты. Семья (R-457), девять кадров, три разных классики:
  C_INT:6, C_INT_HALF:6, C_INT_HALF_XCOM:6, C_INT_SMALL:6, C_INT_XCOM:6, C_INT_THIRD:6, CORP:36  (классика побайтно одна)
  C_INT_XCOM_GOLD:6   (та же раскладка, золотая рампа 144-151)
  FREIGHTER_MAIN:13   (та же раскладка, тусклый центр 241-247)
Вариантов .v1-.v3 у этих кадров нет. C_INT:7 (ровный пол, pixel_lines, одобрен) не трогается.

Что было не так (разбор 29.10): в HD вместо пятна света нарисована впадина с бортиком (sdxl_legacy), у FREIGHTER_MAIN:13
почти чёрный кадр без свечения. pixel_lines на мягком свечении нельзя (R-325: вложенные кольца).

Рецепт:
  * основа - рампа свечения классики БЕЗ перфорации: точки перфорации (пара пикселей L, L-1, где L = 245..247 по
    рампе набора) заменены средним цветом пикселей над и под; бикубика x4 (cv2.INTER_CUBIC) по RGB, вне классики -
    ближайшим цветом (без чёрного края); доводки резкости на поле нет, ступени классики сглаживаются в плавный градиент;
  * точки - отдельные чёткие штампы 8x4 пикс HD (супер-эллипс, сглаживание 8x), цвет по горизонтали от цвета левого
    пикселя пары к цвету правого - как у точек C_INT:7 (одобрен: 7x4 с градиентом 30-46 на поле 50);
  * альфа - ромб dmap <= 1.04 (перехлёст R-291), побайтно как у C_INT:7: стык без ступени и без просветов;
  * тон - палитра Пираток по индексам классики СВОЕГО набора: золото по 144-151, FREIGHTER по 241-247.

    py -3.13 tools\hdart\t365_build.py                    # кадры + MANIFEST.json + проверки (без записи в мод)
    py -3.13 tools\hdart\t365_build.py --sheet            # + лист art/_review/tickets_2026-10-29/t365_after.png
    py -3.13 tools\hdart\t365_build.py --install --yes    # + в мод hd через манифест (ТОЛЬКО под очередью правок)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_seam as gs        # noqa: E402
import ticket_scene as ts       # noqa: E402
import water_build as wb        # noqa: E402

ROOT = HERE.parent.parent
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-29"
INST = REVIEW / "t365_install"
K = 4
OVERLAP = 1.04                  # как у C_INT:7: dmap <= 1.04 (R-291)
# семья: (набор, кадр) -> база рампы в палитре (0-я ступень рампы)
FAMILY = [("C_INT", 6, 240), ("C_INT_HALF", 6, 240), ("C_INT_HALF_XCOM", 6, 240), ("C_INT_SMALL", 6, 240),
          ("C_INT_XCOM", 6, 240), ("C_INT_THIRD", 6, 240), ("CORP", 36, 240),
          ("C_INT_XCOM_GOLD", 6, 144), ("FREIGHTER_MAIN", 13, 240)]
STAMP_W, STAMP_H = 8, 4         # точка: пара пикселей классики = 8x4 пикс HD
P_SUPER = 2.4                   # форма точки: |x/4|^p + |y/2|^p <= 1


def hole_pairs():
    """Позиции точек (строка, левый столбец) по классике C_INT:6: пара (L, L-1), L = 245..247."""
    a = wb.read_set("C_INT")[6].astype(int)
    out = []
    for r in range(a.shape[0]):
        for c in range(a.shape[1] - 1):
            if 245 <= a[r, c] <= 247 and a[r, c + 1] == a[r, c] - 1:
                out.append((r, c))
    return out


def stamp_cov():
    """Покрытие точки 8x4 (сглаживание сверхвыборкой 8x), 0..1."""
    S = 8
    ys, xs = np.mgrid[0:STAMP_H * S, 0:STAMP_W * S].astype(np.float32)
    x = (xs + 0.5) / S - STAMP_W / 2
    y = (ys + 0.5) / S - STAMP_H / 2
    inside = (np.abs(x / (STAMP_W / 2)) ** P_SUPER + np.abs(y / (STAMP_H / 2)) ** P_SUPER) <= 1.0
    return inside.reshape(STAMP_H, S, STAMP_W, S).mean(axis=(1, 3)).astype(np.float32)


def build(S, f, base):
    pal = wb.palette()
    a = wb.read_set(S)[f].astype(int)
    holes = hole_pairs()
    rgb = pal[a][..., :3].astype(np.float32)
    opaque = a > 0
    hole = np.zeros(a.shape, bool)
    for r, c in holes:
        # раскладка точек общая у всей семьи: проверка по рампе набора (соседние ступени рампы 3..7; у FREIGHTER на правых точках порядок зеркальный)
        assert abs(a[r, c + 1] - a[r, c]) == 1 and base + 3 <= min(a[r, c], a[r, c + 1]) and max(a[r, c], a[r, c + 1]) <= base + 7, (S, f, r, c, a[r, c], a[r, c + 1])
        hole[r, c] = hole[r, c + 1] = True
    assert hole.sum() == 2 * len(holes)
    bg = rgb.copy()
    for r, c in holes:
        for cc in (c, c + 1):
            acc = []
            for rr in (r - 1, r + 1):
                if 0 <= rr < a.shape[0] and opaque[rr, cc] and not hole[rr, cc]:
                    acc.append(rgb[rr, cc])
            if not acc:
                for c2 in (c - 1, c + 2):
                    if 0 <= c2 < a.shape[1] and opaque[r, c2] and not hole[r, c2]:
                        acc.append(rgb[r, c2])
            bg[r, cc] = np.mean(acc, 0)
    near = ndi.distance_transform_edt(~opaque, return_distances=False, return_indices=True)
    bg = bg[near[0], near[1]]                                  # за классикой - ближайшим цветом, без чёрного края
    big = cv2.resize(bg, (32 * K, 40 * K), interpolation=cv2.INTER_CUBIC)
    big = np.clip(big, bg.reshape(-1, 3).min(0), bg.reshape(-1, 3).max(0))
    cov = stamp_cov()
    t = np.clip((np.arange(STAMP_W) - 1.5) / 4.0, 0, 1).astype(np.float32)[None, :, None]
    for r, c in holes:
        cl, cr = rgb[r, c], rgb[r, c + 1]
        col = cl[None, None, :] * (1 - t) + cr[None, None, :] * t              # 1 x 8 x 3
        y0, x0 = r * K, c * K
        reg = big[y0:y0 + STAMP_H, x0:x0 + STAMP_W]
        m = cov[..., None]
        big[y0:y0 + STAMP_H, x0:x0 + STAMP_W] = reg * (1 - m) + col * m
    al = np.where(gs.dmap() <= OVERLAP, 255, 0).astype(np.uint8)
    assert big.shape[:2] == al.shape
    out = np.dstack([np.round(big).astype(np.uint8), al])
    return Image.fromarray(out, "RGBA")


def build_all():
    res = {}
    base_img = None
    for S, f, base in FAMILY:
        im = build(S, f, base)
        if base == 240 and S not in ("FREIGHTER_MAIN",):
            if base_img is None:
                base_img = im
            else:
                assert im.tobytes() == base_img.tobytes(), "копии C_INT:6 обязаны совпасть"
        res[(S, f)] = im
    return res


def save_all(res):
    files = {}
    for (s, f), im in sorted(res.items()):
        rel = "TERRAIN/%s.PCK/%d.png" % (s, f)
        p = INST / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        im.save(p, optimize=True)
        files[rel] = p
    man = {"ticket": "XP-000365", "generator": "t365_build.py", "variant": "A",
           "note": "пятно света C_INT:6 и семья: по рампе классики, точки перфорации отдельными штампами",
           "files": {r: hashlib.sha256(p.read_bytes()).hexdigest() for r, p in files.items()}}
    (INST / "MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    return files


def check(res):
    """Размер, альфа = ромб 1.04 (равна C_INT:7), вне него 0, тон = палитра классики своего набора, стык с C_INT:7."""
    pal = wb.palette()
    d = gs.dmap()
    ref7 = np.asarray(ts.Scene().hd("C_INT", 7))[..., 3]
    assert ((d <= OVERLAP) == (ref7 > 0)).all(), "ромб C_INT:7 не равен dmap <= 1.04"
    for (S, f), im in res.items():
        arr = np.asarray(im)
        assert im.size == (128, 160) and im.mode == "RGBA"
        assert (arr[..., 3] == np.where(d <= OVERLAP, 255, 0)).all()
        a = wb.read_set(S)[f]
        m4 = wb.blk(a > 0) > 0
        # тон: средний цвет по следу классики близок палитре классики (допуск 6 из 255)
        cm = arr[..., :3][m4].astype(float).mean(0)
        pm = pal[a[a > 0]][:, :3].astype(float).mean(0)
        dd = np.abs(cm - pm).max()
        print("  %-18s:%-3d непрозрачных %d, средний цвет HD %s, классики %s, разница %.1f"
              % (S, f, (arr[..., 3] > 0).sum(), cm.round(1), pm.round(1), dd))
        assert dd < 6.0, (S, f, dd)
    # тона на стыке: край кадра C_INT:6 против C_INT:7 (HD, одобрен)
    h7 = np.asarray(ts.Scene().hd("C_INT", 7)).astype(float)
    n6 = np.asarray(res[("C_INT", 6)]).astype(float)
    edge = (d > 0.90) & (d <= 1.0)
    print("  кромка ромба (0.90<d<=1): C_INT:6 новое %s, C_INT:7 HD %s" % (n6[edge][:, :3].mean(0).round(1), h7[edge][:, :3].mean(0).round(1)))
    return True


# ---------------------------------------------------------------- лист после
def make_sheet(res):
    import t365_sheet as t3
    from PIL import ImageDraw
    sc = ts.Scene()
    tiles, sets = t3.read_save()

    class Src(t3.Src):
        def get(self, S, f):
            if self.mode == "new" and (S, f) in res:
                return res[(S, f)]
            return super().get(S, f)

    views = {m: t3.render_area(tiles, sets, sc, Src(sc, m), 30, 38, 50, 58) for m in ("classic", "hd", "new")}
    w, h = views["hd"].size
    crop = (int(w * 0.05), int(h * 0.20), int(w * 0.95), int(h * 0.92))
    pan = [ts.label(views[m].crop(crop).convert("RGB"), t, 24)
           for m, t in (("classic", "классика (оригинал)"), ("hd", "HD было"), ("new", "HD стало (вариант A)"))]
    # крупно: стык C_INT:6 и C_INT:7, окно вокруг двух клеток пола вышки
    zoom_box = (int(w * 0.46), int(h * 0.50), int(w * 0.70), int(h * 0.74))
    zooms = []
    for m, t in (("classic", "классика"), ("hd", "было"), ("new", "стало")):
        z = views[m].crop(zoom_box).convert("RGB")
        z = z.resize((z.width * 2, z.height * 2), Image.NEAREST if m == "classic" else Image.LANCZOS)
        zooms.append(ts.label(z, "стык C_INT:6 / C_INT:7 крупно - " + t, 22))
    # семья: классика / было / стало
    font = ts.font(18)
    colw, rowh = 264, 158
    fam = Image.new("RGB", (colw * 3 + 8, len(FAMILY) * rowh + 8), (14, 14, 16))
    d = ImageDraw.Draw(fam)
    for i, (S, f, _b) in enumerate(FAMILY):
        for j, (t, im) in enumerate((("классика", sc.classic(S, f)), ("было", sc.hd(S, f)), ("стало", res[(S, f)]))):
            p = Image.new("RGBA", (128, 160), (52, 46, 40, 255))
            if im is not None:
                p.alpha_composite(im)
            p = p.crop((0, 96, 128, 160)).resize((256, 128), Image.NEAREST if j == 0 else Image.LANCZOS)
            x, y = 4 + j * colw, 4 + i * rowh
            fam.paste(p.convert("RGB"), (x, y + 26))
            d.text((x, y + 2), ("%s:%d  " % (S, f) if j == 0 else "") + t, fill=(255, 220, 0), font=font)
    W = 1400
    blocks = []
    for p in pan:
        blocks.append(p.resize((W, int(p.height * W / p.width)), Image.LANCZOS))
    zrow_w = sum(z.width for z in zooms) + 8 * 2
    zrow = Image.new("RGB", (zrow_w, max(z.height for z in zooms)), (12, 12, 14))
    x = 0
    for z in zooms:
        zrow.paste(z, (x, 0))
        x += z.width + 8
    zrow = zrow.resize((W, int(zrow.height * W / zrow.width)), Image.LANCZOS)
    famL = ts.label(fam, "Семья кадра C_INT:6 (низ кадра x2): классика | было | стало", 22)
    H = sum(b.height for b in blocks) + zrow.height + famL.height + 40
    out = Image.new("RGB", (W, H), (12, 12, 14))
    y = 0
    for b in blocks + [zrow, famL]:
        out.paste(b, (0, y))
        y += b.height + 8
    p = REVIEW / "t365_after.png"
    out.save(p)
    for m in ("new",):
        views[m].convert("RGB").save(REVIEW / "t365_scene_new.png")
    return p, out.size


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    print("точек перфорации в раскладке:", len(hole_pairs()))
    res = build_all()
    files = save_all(res)
    print("кадров: %d -> %s" % (len(files), INST))
    check(res)
    if a.sheet:
        print("лист:", *make_sheet(res))
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только под очередью правок)")
        n = ts.install_files(files, "t365_build", "t365_build.py 29.10: рампа свечения классики x4 + точки штампами, ромб 1.04",
                             "Vitali 29.10: вариант A по тикету XP-000365; лист art/_review/tickets_2026-10-29/t365_after.png",
                             "t365: пятно света пола C_INT:6 и семья (9 кадров) - по классике, точки перфорации штампами")
        print("установлено файлов:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
