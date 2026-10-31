#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Лист и замеры стыков для t253_rails.py: цепочка клеток 73|74 как в движке (z, y, x), смещение рельса на каждом стыке.

Цепочка: клетка (4, y) - кадр 73, клетка (5, y) - кадр 74, y = 0..N-1, шаг по y на экране (-16, +8). Порядок
рисования как в Map::drawTerrain: y по возрастанию, x по возрастанию, поэтому юго-западный сосед рисуется поверх
северо-восточного. Для каждого пикселя запоминается, какая клетка нарисовала его последней (непрозрачность >= 0.5):
стык - место, где рельс переходит от одной клетки к другой. На каждой видимой части рельса (одна клетка) по столбцам
берётся центр верхней светлой полоски (головка рельса, средняя по яркости), по ним - прямая; смещение на стыке -
разность двух прямых в точке перехода (HD-пиксели), плюс разность углов и разброс точек вокруг своей прямой.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ticket_scene as ts            # noqa: E402

K = 4
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-23"
RAIL_C73 = 31.5
N = 21                                # как самая длинная цепочка карты (PORTUFOHUGE01, x = 4..5, y = 0..20)


def compose_chain(f73, f74, n=N):
    """f73, f74 - RGBA uint8 128x160. Возвращает (картинка RGBA float, карта клеток: номер y нарисовавшей клетки
    +1 для 73 и +1000 для 74, 0 - пусто)."""
    ox = 20 * K
    W = (16 * n + 90) * K
    H = (8 * 2 * n + 80) * K
    img = np.zeros((H, W, 4), np.float32)
    who = np.zeros((H, W), np.int32)
    for y in range(n):
        for x, fr in ((0, f73), (1, f74)):
            px = ox + 16 * (x - y) * K + 16 * (n - 1) * K
            py = 20 * K + 8 * (x + y) * K
            a = fr.astype(np.float32)
            reg = img[py:py + 160, px:px + 128]
            sa = a[..., 3:4] / 255.0
            da = reg[..., 3:4] / 255.0
            oa = sa + da * (1 - sa)
            rgb = np.where(oa > 1e-6, (a[..., :3] * sa + reg[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6), 0)
            reg[..., :3] = rgb
            reg[..., 3:4] = oa * 255.0
            wreg = who[py:py + 160, px:px + 128]
            wreg[a[..., 3] >= 128] = (y + 1) + (1000 if x else 0)
    return img, who


def rail_head_centres(img, who, code):
    """По столбцам: центр рельса (пиксели рельса в окне 22 HD px от верхнего), нарисованного клеткой code. -> {x: y}"""
    rgb = img[..., :3]
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    mask = (who == code) & (img[..., 3] > 200) & (rgb[..., 2] - rgb[..., 0] >= 10) & (lum > 35)
    out = {}
    ys, xs = np.nonzero(mask)
    for x in np.unique(xs):
        col = np.sort(ys[xs == x])
        # пиксели рельса в окне 22 HD px от верхнего (рельс 17 px по вертикали)
        sel = col[col < col[0] + 22]
        out[int(x)] = float(sel.mean() + 0.5)
    return out


def fit(pts, trim=22):
    xs = sorted(pts)
    xs = xs[trim:-trim] if len(xs) > 2 * trim + 8 else xs
    if len(xs) < 6:
        return None
    X = np.array(xs, float)
    Y = np.array([pts[x] for x in xs], float)
    a, b = np.polyfit(X, Y, 1)
    res = Y - (a * X + b)
    return a, b, float(np.abs(res).max()), len(xs), float(X.min()), float(X.max())


def measure(f73, f74, n=N):
    """Таблица стыков: для каждого рельса (73, 74) и каждой пары соседних клеток."""
    img, who = compose_chain(f73, f74, n)
    rows = []
    for name, off in (("73", 0), ("74", 1000)):
        fits = {}
        for y in range(n):
            pts = rail_head_centres(img, who, (y + 1) + off)
            r = fit(pts)
            if r:
                fits[y] = r
        ys = sorted(fits, reverse=True)       # от юго-запада (больше y рисуется позже) к северо-востоку
        for y in ys:
            if y - 1 not in fits:
                continue
            a1, b1, m1, _, x0a, x1a = fits[y]        # юго-западная клетка y
            a2, b2, m2, _, x0b, x1b = fits[y - 1]    # северо-восточная клетка y-1
            # точка перехода - между видимой частью y (правый конец) и y-1 (левый конец)
            xj = (x1a + x0b) / 2
            d = (a1 * xj + b1) - (a2 * xj + b2)
            rows.append((name, y, xj, d, np.degrees(np.arctan(a1) - np.arctan(a2)), max(m1, m2)))
    return rows, img, who


def summary(rows):
    out = {}
    for name in ("73", "74"):
        d = [abs(r[3]) for r in rows if r[0] == name]
        s = [abs(r[4]) for r in rows if r[0] == name]
        m = [r[5] for r in rows if r[0] == name]
        out[name] = (len(d), max(d), float(np.mean(d)), max(s), max(m))
    return out


def zone_dev(img, rows, half=16, n=N):
    """Отклонение центра и обеих кромок рельса от ОДНОЙ общей прямой на всю цепочку, по итоговой картинке (то, что видит игрок), в зонах
    +-half HD px вокруг каждого стыка, без обрезки концов кусков: именно там у плохого кадра ступенька.
    Рельс отбирается по общей координате w = y + x/2 (у цепочки она одна). -> {рельс: (макс, среднее)}"""
    rgb = img[..., :3]
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    mask = (img[..., 3] > 200) & (rgb[..., 2] - rgb[..., 0] >= 10) & (lum > 35)
    ys, xs = np.nonzero(mask)
    w_abs = ys + 0.5 + (xs + 0.5) / 2
    ox = 20 * K + 16 * (n - 1) * K
    oy = 20 * K
    w73 = oy + RAIL_C73 * K + ox / 2
    out = {}
    for name, w0 in (("73", w73), ("74", w73 + 20.5 * K)):
        sel = (w_abs > w0 - 8) & (w_abs < w0 + 17 + 8)
        px, py = xs[sel], ys[sel]
        pts = {}
        for x in np.unique(px):
            col = py[px == x]
            pts[int(x)] = float(col.mean() + 0.5)
        X = np.array(sorted(pts), float)
        Y = np.array([pts[int(x)] for x in X], float)
        top = np.array([float(py[px == int(x)].min()) for x in X])
        bot = np.array([float(py[px == int(x)].max() + 1) for x in X])
        keep = (X > X.min() + 40) & (X < X.max() - 40)
        zone = np.zeros(len(X), bool)
        for r in rows:
            if r[0] == name:
                zone |= np.abs(X - r[2]) <= half
        zone &= keep
        dmax, dmean = 0.0, 0.0
        for V in (Y, top, bot):
            a_, b_ = np.polyfit(X[keep], V[keep], 1)
            dev = np.abs(V - (a_ * X + b_))
            dmax = max(dmax, float(dev[zone].max()))
            dmean = max(dmean, float(dev[zone].mean()))
        out[name] = (dmax, dmean)
    return out


def sleeper_joint_diff(f73, f74):
    """Кусок шпалы 73|74 в перекрытии: расхождение цвета двух кадров в зоне, где оба непрозрачны (HD пиксели,
    кадр 74 сдвинут на (+16,+8) базы). Возвращает (число пикселей, максимум, среднее)."""
    a = np.zeros((160 + 8 * K, 128 + 16 * K, 4), np.float32)
    b = np.zeros_like(a)
    a[:160, :128] = f73
    b[8 * K:8 * K + 160, 16 * K:16 * K + 128] = f74
    # зона: коричневое дерево обоих (шпала), оба непрозрачны
    def wood(p):
        return (p[..., 3] > 250) & (p[..., 0] > p[..., 1] + 15) & (p[..., 1] > p[..., 2] + 10) & (p[..., 0] > 70)
    m = wood(a) & wood(b)
    if not m.any():
        return 0, 0.0, 0.0
    d = np.abs(a[..., :3] - b[..., :3]).max(-1)[m]
    return int(m.sum()), float(d.max()), float(d.mean())


def text_panel(lines, width, size=20, bg=(15, 15, 18)):
    f = ts.font(size)
    h = (size + 8) * len(lines) + 16
    im = Image.new("RGB", (width, h), bg)
    d = ImageDraw.Draw(im)
    for i, (t, c) in enumerate(lines):
        d.text((12, 8 + i * (size + 8)), t, fill=c, font=f)
    return im


def write_tsv(path, tables):
    lines = ["вариант\tрельс\tклетка y\tx стыка HD\tсмещение HD px\tсмещение px базы\tразность углов град\tразброс HD px"]
    for tag, rows in tables:
        for name, y, xj, d, da, m in rows:
            lines.append("%s\t%s\t%d\t%.1f\t%+.2f\t%+.3f\t%+.3f\t%.2f" % (tag, name, y, xj, d, d / K, da, m))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def cell_origin(x, y, n=N):
    """Левый верхний угол кадра клетки (x, y) цепочки в compose_chain, HD пиксели."""
    return 20 * K + 16 * (x - y) * K + 16 * (n - 1) * K, 20 * K + 8 * (x + y) * K


def chain_picture(f73, f74):
    img, _ = compose_chain(f73, f74)
    base = Image.new("RGBA", (img.shape[1], img.shape[0]), (26, 26, 30, 255))
    base.alpha_composite(Image.fromarray(np.clip(img, 0, 255).round().astype(np.uint8), "RGBA"))
    return base


def crop_at(pic, x, y, fx, fy, w, h, width=470):
    ox, oy = cell_origin(x, y)
    cx, cy = ox + fx * K, oy + fy * K
    box = (int(cx - w * K / 2), int(cy - h * K / 2), int(cx + w * K / 2), int(cy + h * K / 2))
    c = pic.crop(box).convert("RGB")
    sc_ = width / c.width
    return c.resize((width, int(c.height * sc_)), Image.NEAREST if sc_ > 3.5 and pic.info.get("nearest") else Image.LANCZOS)


def make(res):
    sc = ts.Scene()
    f73n = res[("PORTROADS", 73)].round().astype(np.uint8)
    f74n = res[("PORTROADS", 74)].round().astype(np.uint8)
    f73o = np.asarray(sc.hd("PORTROADS", 73))
    f74o = np.asarray(sc.hd("PORTROADS", 74))
    f73c = np.asarray(sc.classic("PORTROADS", 73))
    f74c = np.asarray(sc.classic("PORTROADS", 74))
    rows_o, img_o, who_o = measure(f73o, f74o)
    rows_n, img_n, who_n = measure(f73n, f74n)
    zo, zn = zone_dev(img_o, rows_o), zone_dev(img_n, rows_n)
    so, sn = summary(rows_o), summary(rows_n)
    write_tsv(REVIEW / "t253_joints.tsv", [("прежний HD", rows_o), ("новый", rows_n)])
    sj_o = sleeper_joint_diff(f73o, f74o)
    sj_n = sleeper_joint_diff(f73n, f74n)

    # --- сцена: реальный блок, цепочка 21 клетка (PORTUFOHUGE01, x = 4..5), движок рисует клетки как в игре
    over = {("PORTROADS", 73): Image.fromarray(f73n, "RGBA"), ("PORTROADS", 74): Image.fromarray(f74n, "RGBA"),
            ("METROBITS", 2): Image.fromarray(f73n, "RGBA"), ("METROBITS", 3): Image.fromarray(f74n, "RGBA")}
    terr, block = "PORTUFO", "PORTUFOHUGE01"
    cls, found = sc.render(terr, block, "classic", k=K, marks={("PORTROADS", 73), ("PORTROADS", 74)})
    old, _ = sc.render(terr, block, "hd", k=K)
    new, _ = sc.render(terr, block, "hd", override=over, k=K)
    ch = [f for f in found if f[4][0] in (4, 5) and f[4][1] <= 20]
    box = (min(f[2][0] for f in ch) - 40, min(f[2][1] for f in ch) - 60, max(f[2][2] for f in ch) + 40, max(f[2][3] for f in ch) + 40)
    scene_panels = [("классика: блок PORTUFOHUGE01 (карты PORTUFO, PORTTFTD5-7), цепочка 21 клетка, масштаб игры x4", ts.crop_pad(cls, box)),
                    ("HD прежний (тележки и балки галереи - не мои, как есть)", ts.crop_pad(old, box)),
                    ("HD новый t253_rails.py (те же тележки и балки)", ts.crop_pad(new, box))]
    mt, mb = "METRO", "METRO_NS10"
    mo, mf = sc.render(mt, mb, "hd", k=K, maxz=0, marks={("METROBITS", 2), ("METROBITS", 3)})
    mn, _ = sc.render(mt, mb, "hd", override=over, k=K, maxz=0)
    mch = [f for f in mf if f[4][0] in (4, 5)]
    mbox = (min(f[2][0] for f in mch) - 30, min(f[2][1] for f in mch) - 30, max(f[2][2] for f in mch) + 30, max(f[2][3] for f in mch) + 30)
    scene_panels.append(("метро METRO_NS10 (METROBITS 2/3, побайтные копии 73/74): прежний HD", ts.crop_pad(mo, mbox)))
    scene_panels.append(("метро METRO_NS10: новый HD", ts.crop_pad(mn, mbox)))
    # --- крупно: стыки на чистой цепочке 21 клетка (без тележек и балок): классика | прежний | новый
    pics = [("классика", chain_picture(f73c, f74c), True), ("HD прежний", chain_picture(f73o, f74o), False),
            ("HD новый", chain_picture(f73n, f74n), False)]
    jb = [("стык рельса 73 (клетки y=10|9, вход рельса на край ромба)", 0, 10, 15.0, 24.0, 22, 15),
          ("стык рельса 74 (клетки y=10|9)", 1, 10, 19.5, 26.25, 22, 15),
          ("стык шпалы 73|74 (клетки x=4|5, y=10)", 0, 10, 26.0, 35.5, 30, 20)]
    zrow = []
    for t, x, y, fx, fy, w, h in jb:
        row = []
        for nm, pic, nearest in pics:
            pic.info["nearest"] = nearest
            row.append(ts.label(crop_at(pic, x, y, fx, fy, w, h), "%s: %s" % (t, nm), 15))
        zrow.append(row)
    # --- таблица
    fm = "%s: стыков %d | прежний: макс %.2f, ср %.2f HD px | новый: макс %.2f, ср %.2f HD px"
    ln = [("Смещение рельса на стыке клеток цепочки 21, как рисует движок (HD px, 4 HD px = 1 px базы; цель 0-1)", (255, 220, 0)),
          (fm % ("рельс 73", so["73"][0], so["73"][1], so["73"][2], sn["73"][1], sn["73"][2]), (230, 230, 230)),
          (fm % ("рельс 74", so["74"][0], so["74"][1], so["74"][2], sn["74"][1], sn["74"][2]), (230, 230, 230)),
          ("отклонение от общей прямой цепочки в зоне +-16 HD px у стыка (макс/ср): рельс 73 прежний %.2f/%.2f новый %.2f/%.2f; рельс 74 прежний %.2f/%.2f новый %.2f/%.2f" % (
              zo["73"][0], zo["73"][1], zn["73"][0], zn["73"][1], zo["74"][0], zo["74"][1], zn["74"][0], zn["74"][1]), (230, 230, 230)),
          ("шпала 73|74 в зоне перекрытия кадров: прежний %d px, макс расхождение цвета %.0f | новый %d px, макс %.1f" % (
              sj_o[0], sj_o[1], sj_n[0], sj_n[1]), (230, 230, 230)),
          ("все стыки по одному - t253_joints.tsv (там же разность углов и разброс точек у каждой клетки)", (170, 170, 170))]
    W = 1480
    parts = [text_panel(ln, W, 16)]
    for t, im in scene_panels:
        parts.append(ts.label(im.convert("RGB").copy(), t, 20))
    H = sum(p.height for p in parts) + sum(max(p.height for p in r) for r in zrow) + 8 * (len(parts) + len(zrow) + 1)
    sheet = Image.new("RGB", (W, H), (12, 12, 14))
    y = 8
    for p in parts:
        sheet.paste(p, (8, y))
        y += p.height + 8
    for r in zrow:
        x = 8
        for p in r:
            sheet.paste(p, (x, y))
            x += p.width + 8
        y += max(p.height for p in r) + 8
    sheet.save(REVIEW / "t253_rails_v2.png")
    print("лист:", REVIEW / "t253_rails_v2.png", sheet.size)
    print("рельс 73 прежний: стыков %d макс %.2f среднее %.2f; новый макс %.2f среднее %.2f" % (so["73"][0], so["73"][1], so["73"][2], sn["73"][1], sn["73"][2]))
    print("рельс 74 прежний: стыков %d макс %.2f среднее %.2f; новый макс %.2f среднее %.2f" % (so["74"][0], so["74"][1], so["74"][2], sn["74"][1], sn["74"][2]))
    print("зона стыка (макс/ср) 73 прежний %.2f/%.2f новый %.2f/%.2f; 74 прежний %.2f/%.2f новый %.2f/%.2f" % (zo["73"] + zn["73"] + zo["74"] + zn["74"]))
    print("шпала в перекрытии: прежний", sj_o, "новый", sj_n)
    return so, sn
