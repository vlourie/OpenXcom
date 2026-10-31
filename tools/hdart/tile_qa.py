#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Проверки кадра на карте рядом с другими (P1-B, замечания 30.09, R-136). Три разные проверки:

TILE_QA (только плитка, категория tileable) - копии обязаны стыковаться бесшовно:
  repeat_sheet - 3x3 копии по изометрической сетке клеток (как render в map_mockup: x - вправо-вниз,
                 y - влево-вниз), слева оригинал x4, справа HD; стык копий виден сразу;
  map_sheet    - карта, где кадр стоит на самом деле: HD-кадр из папки ответа, всё остальное - оригинал
                 x4; вырез вокруг всех мест кадра, отмечены пары копий вплотную. Слева та же карта в
                 оригинале.
  Вердикт TILE_PASS / TILE_FAIL ставит человек. TILE_FAIL у плитки - не провал Pipeline v2, а знак, что
  обычный генератор предметов этому типу не подходит и нужен свой режим.
ADJACENCY_QA (предмет, который часто стоит рядом со своей копией, но НЕ плитка - края не продолжаются):
  adjacency - копии не залезают друг на друга, нет искусственной общей тени, соседние экземпляры не
  сливаются, footprint сохранён, нет выступов за габарит оригинала. Числа (footprint) и тот же вырез карты.
COMPOSITE_SEAM_QA (составной, особенно выведенный зеркалом по кускам):
  composite_seam - куски собраны по местам на карте; щель и двойной край в полосе шва, перепад яркости
  на шве против перепада внутри, для выведенного - совпадение с перевёрнутым исходником. Провал только у
  выведенного при целом исходнике - DERIVE_MIRROR_COMPOSITE_FAIL (вывод), а не провал модели.
Числа - подсказка, куда смотреть (attention), вердикт всегда ставит человек (PENDING_HUMAN).

    py -3.13 tools/hdart/tile_qa.py NUKE2:10 --src user/mods/hd/hd/TERRAIN --map NUKE_CITY_NORAD_5/NUKECITY00
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                        # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

import cover_check as cc                  # noqa: E402
import map_mockup as mm                   # noqa: E402

K = 4
BG = (32, 32, 36, 255)
# соседние клетки на экране: по x (+16, +8) и по y (-16, +8) пикселей базы
NEIGHBOURS = ((16, 8), (-16, 8))
# пороги подсказки «посмотри сюда», не вердикт
ATTN = {"cover_min": 0.85, "spill_max": 0.05, "shadow_max": 0.02, "overflow_max": 1.0, "overlap_max": 0.02,
        "seam_hole_max": 0.03, "seam_double_max": 0.03, "seam_step_max": 1.6, "mirror_iou_drop_max": 0.05}


def grid(cell, n=3, k=K):
    """n x n копий кадра (32k x 40k) по изо-сетке клеток, от дальних к ближним."""
    w = (2 * (n - 1) * 16 + 32) * k
    h = (2 * (n - 1) * 8 + 40) * k
    im = Image.new("RGBA", (w, h), BG)
    ox = (n - 1) * 16 * k
    for s in range(2 * n - 1):                      # x + y по возрастанию - дальние раньше
        for x in range(n):
            y = s - x
            if 0 <= y < n:
                im.alpha_composite(cell, (ox + (x - y) * 16 * k, (x + y) * 8 * k))
    return im


def label(im, text):
    out = Image.new("RGBA", (im.width, im.height + 18), BG)
    out.alpha_composite(im, (0, 18))
    ImageDraw.Draw(out).text((4, 3), text, fill=(255, 255, 0))
    return out


def side(ims):
    w = sum(i.width for i in ims) + 8 * (len(ims) - 1)
    out = Image.new("RGBA", (w, max(i.height for i in ims)), BG)
    x = 0
    for i in ims:
        out.alpha_composite(i, (x, 0))
        x += i.width + 8
    return out


def save(im, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    im.convert("RGB").save(path)
    return path


def repeat_sheet(src, key, out, world=None):
    world = world or mm.World()
    s, f = key.rsplit(":", 1)
    orig = world.sprite(s.lower(), int(f), None).resize((32 * K, 40 * K), Image.NEAREST)
    hd = Image.open(src).convert("RGBA")
    if hd.size != (32 * K, 40 * K):
        hd = hd.resize((32 * K, 40 * K), Image.LANCZOS)
    sheet = side([label(grid(orig), "%s original x4, 3x3" % key), label(grid(hd), "%s HD, 3x3" % key)])
    return {"kind": "tile_qa_3x3", "key": key, "sheet": save(sheet, out)}


def adjacent_pairs(marks, k):
    """Пары мест кадра в соседних клетках одного этажа: сдвиг (+-16, +-8) пикселей базы."""
    boxes = [(m[2][0], m[2][1], m[3]) for m in marks]
    return [(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1:]
            if a[2] == b[2] and abs(a[0] - b[0]) == 16 * k and abs(a[1] - b[1]) == 8 * k]


def pick_map(world, key, where, tries=12):
    """Карта, где копии кадра стоят вплотную: сначала данная, потом самые частые места кадра (usage)."""
    s, f = key.rsplit(":", 1)
    mark = (s.upper(), int(f))
    cands = [where] + ["%s/%s" % (t, b) for t, b, _n in sorted(mm.usage(world).get("%s:%s" % mark, []),
                                                                key=lambda r: -r[2])]
    best = (where, 0, None)
    for w in list(dict.fromkeys(cands))[:tries]:
        t, b = w.split("/")
        _im, marks = mm.render(world, t, b, None, 1, mark)
        adj = adjacent_pairs(marks, 1)
        if len(adj) > best[1]:
            best = (w, len(adj), adj[0][0][2])     # этаж пары: выше него карта срезается, как в игре
        if len(adj) >= 2:
            break
    return best[0], best[2]


def map_sheet(src_dir, key, where, out, world=None, margin=48):
    """Карта (данная или ближайшая, где копии стоят вплотную): HD-кадр из src_dir, остальное оригинал."""
    world = world or mm.World()
    where, level = pick_map(world, key, where)
    terrain, block = where.split("/")
    s, f = key.rsplit(":", 1)
    mark = (s.upper(), int(f))
    hd, marks = mm.render(world, terrain, block, src_dir, K, mark, maxz=level)
    base, _m = mm.render(world, terrain, block, None, K, mark, maxz=level)
    if not marks:
        return {"kind": "tile_qa_map", "key": key, "sheet": None, "places": 0, "adjacent_pairs": 0,
                "note": "кадра нет на карте %s" % where}
    adj = adjacent_pairs(marks, K)
    pairs, places = len(adj), len(marks)
    if adj:                                          # вырез - вокруг пар вплотную, а не всех мест
        marks = [m for m in marks if any((m[2][0], m[2][1], m[3]) in p for p in adj)]
    x0 = max(0, min(m[2][0] for m in marks) - margin * K)
    y0 = max(0, min(m[2][1] for m in marks) - margin * K)
    x1 = min(hd.width, max(m[2][2] for m in marks) + margin * K)
    y1 = min(hd.height, max(m[2][3] for m in marks) + margin * K)
    box = (x0, y0, x1, y1)
    cut_b, cut_h = base.crop(box), hd.crop(box)
    if cut_h.width > 2400:                          # огромная карта - вырез уменьшить, стык всё равно виден
        r = 2400 / cut_h.width
        cut_b = cut_b.resize((int(cut_b.width * r), int(cut_b.height * r)), Image.LANCZOS)
        cut_h = cut_h.resize((int(cut_h.width * r), int(cut_h.height * r)), Image.LANCZOS)
    sheet = side([label(cut_b, "%s original, %s" % (key, where)),
                  label(cut_h, "%s HD on map: %d places, %d adjacent pairs, level %s" % (key, places, pairs, level))])
    return {"kind": "tile_qa_map", "key": key, "map": where, "level": level, "places": places,
            "adjacent_pairs": pairs, "sheet": save(sheet, out)}


def shift(m, dx, dy):
    """Маска, сдвинутая на (dx, dy) пикселей; ушедшее за край пропадает, пришедшее - пусто."""
    out = np.zeros_like(m)
    h, w = m.shape
    if abs(dx) >= w or abs(dy) >= h:
        return out
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[yd, xd] = m[ys, xs]
    return out


def grow(m, px):
    if px <= 0:
        return m
    im = Image.fromarray(m.astype(np.uint8) * 255, "L").filter(ImageFilter.MaxFilter(2 * px + 1))
    return np.asarray(im) > 0


def bbox(m):
    ys, xs = np.nonzero(m)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if len(xs) else None


def orig_x4(world, key):
    s, f = key.rsplit(":", 1)
    return world.sprite(s.lower(), int(f), None).convert("RGBA").resize((32 * K, 40 * K), Image.NEAREST)


def load_hd(path):
    hd = Image.open(path).convert("RGBA")
    return hd if hd.size == (32 * K, 40 * K) else hd.resize((32 * K, 40 * K), Image.LANCZOS)


def footprint(orig4, hd, k=K):
    """ADJACENCY_QA числами по кадру (оригинал x4 против HD, оба 32k x 40k), всё в долях силуэта оригинала:
    cover / spill / semi (cover_check); shadow - полупрозрачное вне силуэта с запасом в пиксель базы (общая
    тень между копиями); overflow_px - на сколько пикселей базы HD вышел за габарит оригинала по сторонам;
    overlap_excess - насколько копия в соседней клетке перекрывается больше, чем у оригинала (залезают);
    touch_excess - насколько больше мест, где копии смыкаются вплотную (сливаются)."""
    a, b = cc.alpha(orig4), cc.alpha(hd)
    na = np.asarray(hd.convert("RGBA"))[:, :, 3]
    n = max(1, int(a.sum()))
    cover, spill, semi = cc.score(orig4, hd)
    shadow = float(((na > 16) & (na < 200) & ~grow(a, k)).sum() / n)
    ba, bb = bbox(a), bbox(b)
    over = dict.fromkeys(("left", "top", "right", "bottom"), 0.0)
    if ba and bb:
        over = {"left": max(0, ba[0] - bb[0]) / k, "top": max(0, ba[1] - bb[1]) / k,
                "right": max(0, bb[2] - ba[2]) / k, "bottom": max(0, bb[3] - ba[3]) / k}
    overlap, touch = {}, {}
    for dx, dy in NEIGHBOURS:
        d = "%+d,%+d" % (dx, dy)
        sa, sb = shift(a, dx * k, dy * k), shift(b, dx * k, dy * k)
        overlap[d] = max(0, int((b & sb).sum()) - int((a & sa).sum())) / n
        touch[d] = max(0, int((grow(b, k // 2) & sb & ~b).sum()) - int((grow(a, k // 2) & sa & ~a).sum())) / n
    m = {"cover": round(float(cover), 3), "spill": round(float(spill), 3), "semi": round(float(semi), 3),
         "shadow": round(shadow, 3), "overflow_px": {s: round(v, 1) for s, v in over.items()},
         "overlap_excess": {d: round(v, 3) for d, v in overlap.items()},
         "touch_excess": {d: round(v, 3) for d, v in touch.items()}}
    attn = []
    if m["cover"] < ATTN["cover_min"]:
        attn.append("footprint: закрыто %.2f силуэта оригинала" % m["cover"])
    if m["spill"] > ATTN["spill_max"]:
        attn.append("вылет за силуэт: spill %.2f" % m["spill"])
    if m["shadow"] > ATTN["shadow_max"]:
        attn.append("полупрозрачное вокруг - общая тень: %.2f" % m["shadow"])
    if max(over.values()) > ATTN["overflow_max"]:
        attn.append("выступ за габарит: %s" % {s: v for s, v in m["overflow_px"].items() if v})
    if max(overlap.values()) > ATTN["overlap_max"]:
        attn.append("копии залезают друг на друга: %s" % m["overlap_excess"])
    if max(touch.values()) > ATTN["overlap_max"]:
        attn.append("копии смыкаются - могут слиться: %s" % m["touch_excess"])
    m["attention"] = attn
    return m


ADJACENCY_CHECKS = ["копии не залезают друг на друга", "нет искусственной общей тени",
                    "соседние экземпляры не сливаются", "footprint сохранён", "нет выступов за габарит"]
SEAM_CHECKS = ["две половины совпадают", "нет щели", "нет перекрытия (двойного края)",
               "высота матраса и рамы не разошлась", "край одеяла идёт одинаково",
               "точка соединения после зеркала верная", "в игре на месте - без шва"]


def adjacency(src_dir, key, where, out, world=None):
    """ADJACENCY_QA: предмет не плитка, но стоит рядом со своей копией - числа по кадру и вырез карты."""
    world = world or mm.World()
    s, f = key.rsplit(":", 1)
    m = footprint(orig_x4(world, key), load_hd(os.path.join(src_dir, s.upper() + ".PCK", f + ".png")))
    r = map_sheet(src_dir, key, where, out, world)
    r.update(kind="adjacency_qa", checks=ADJACENCY_CHECKS, footprint=m)
    return r


def assemble(frames, placed, k=K):
    """Куски составного по местам на карте, в порядке рисования (этаж, потом глубина).
    frames = {ключ: кадр 32k x 40k}, placed = [(ключ, (x, y, z))] - места как у render / items.at.
    -> (картинка, [(ключ, (x, y) левого верха куска в пикселях k)])"""
    order = sorted(placed, key=lambda p: (p[1][2], p[1][1], p[1][0]))
    x0 = min(p[1][0] for p in order)
    y0 = min(p[1][1] for p in order)                 # y места уже с учётом этажа (render: py - z*24)
    pos = [(key, ((x - x0) * k, (y - y0) * k)) for key, (x, y, _z) in order]
    w = max(x for _k, (x, _y) in pos) + 32 * k
    h = max(y for _k, (_x, y) in pos) + 40 * k
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for key, xy in pos:
        im.alpha_composite(frames[key], xy)
    return im, pos


def piece_masks(frames, pos, size):
    out = []
    for key, (x, y) in pos:
        m = np.zeros((size[1], size[0]), bool)
        a = cc.alpha(frames[key])
        m[y:y + a.shape[0], x:x + a.shape[1]] = a
        out.append(m)
    return out


def seam_numbers(orig_frames, hd_frames, placed, k=K):
    """Шов составного: щель и двойной край в полосе шва, перепад яркости на шве против перепада внутри
    кусков (у оригинала - как база), расхождение пикселей там, где куски HD перекрываются."""
    O, pos = assemble(orig_frames, placed, k)
    H, _ = assemble(hd_frames, placed, k)
    so = piece_masks(orig_frames, pos, O.size)
    sh = piece_masks(hd_frames, pos, H.size)
    band = np.zeros_like(so[0])
    for i in range(len(so)):
        for j in range(i + 1, len(so)):
            band |= grow(so[i], 2 * k) & grow(so[j], 2 * k)
    a, b = cc.alpha(O), cc.alpha(H)
    nb = max(1, int((a & band).sum()))
    hole = float((a & ~b & band).sum() / nb)
    double = float(sum(int((sh[i] & sh[j] & ~(so[i] & so[j]) & band).sum())
                       for i in range(len(sh)) for j in range(i + 1, len(sh))) / nb)
    def mismatch(frames, masks, size):
        # куски там, где оба непрозрачны: игра покажет верхний; разница с нижним видна только краем.
        # У оригинала своя разница (куски рисовали по клетке) - база, помечается только превышение
        out = []
        for i in range(len(masks)):
            for j in range(i + 1, len(masks)):
                both = masks[i] & masks[j]
                if both.any():
                    pi = np.zeros(size[::-1] + (4,), np.int16)
                    pj = np.zeros_like(pi)
                    (ki, (xi, yi)), (kj, (xj, yj)) = pos[i], pos[j]
                    pi[yi:yi + 40 * k, xi:xi + 32 * k] = np.asarray(frames[ki], np.int16)
                    pj[yj:yj + 40 * k, xj:xj + 32 * k] = np.asarray(frames[kj], np.int16)
                    out.append(float(np.abs(pi[both][:, :3] - pj[both][:, :3]).mean() / 255))
        return max(out) if out else None

    mism = mismatch(hd_frames, sh, H.size)
    mism_o = mismatch(orig_frames, so, O.size)

    def step(im, masks):
        # владелец пикселя - кусок, нарисованный последним; шов - соседи с разными владельцами
        own = np.full(masks[0].shape, -1)
        for i, m in enumerate(masks):
            own[m] = i
        lum = np.asarray(im.convert("L"), np.float32)
        seam, inner = [], []
        for dy, dx in ((0, 1), (1, 0)):
            o1, o2 = own[:own.shape[0] - dy, :own.shape[1] - dx], own[dy:, dx:]
            l1, l2 = lum[:lum.shape[0] - dy, :lum.shape[1] - dx], lum[dy:, dx:]
            ok = (o1 >= 0) & (o2 >= 0)
            d = np.abs(l1 - l2)
            seam.append(d[ok & (o1 != o2)])
            inner.append(d[ok & (o1 == o2) & ~band[:band.shape[0] - dy, :band.shape[1] - dx]])
        s, i = np.concatenate(seam), np.concatenate(inner)
        return float(s.mean()) if len(s) else 0.0, float(i.mean()) if len(i) else 0.0

    so_s, so_i = step(O, so)
    hd_s, hd_i = step(H, sh)
    r = {"hole": round(hole, 3), "double": round(double, 3),
         "overlap_mismatch": {"orig": None if mism_o is None else round(mism_o, 3),
                              "hd": None if mism is None else round(mism, 3)},
         "seam_step": {"orig": round(so_s / max(so_i, 1e-3), 2), "hd": round(hd_s / max(hd_i, 1e-3), 2)}}
    attn = []
    if hole > ATTN["seam_hole_max"]:
        attn.append("щель в шве: %.3f" % hole)
    if double > ATTN["seam_double_max"]:
        attn.append("двойной край в шве: %.3f" % double)
    if mism is not None and mism > (mism_o or 0) + 0.05:
        attn.append("куски расходятся там, где перекрываются: %.3f против %.3f у оригинала" % (mism, mism_o or 0))
    if r["seam_step"]["hd"] > max(ATTN["seam_step_max"], r["seam_step"]["orig"] * 1.25):
        attn.append("перепад на шве %.2f против %.2f у оригинала" % (r["seam_step"]["hd"], r["seam_step"]["orig"]))
    r["attention"] = attn
    return r, O, H


def mirror_iou(src_img, der_img):
    """Совпадение силуэта выведенного составного с перевёрнутым исходным (по габариту)."""
    a = cc.alpha(src_img.transpose(Image.FLIP_LEFT_RIGHT))
    b = cc.alpha(der_img)
    ba, bb = bbox(a), bbox(b)
    if not ba or not bb:
        return 0.0
    a = a[ba[1]:ba[3], ba[0]:ba[2]]
    b = b[bb[1]:bb[3], bb[0]:bb[2]]
    h, w = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])
    A = np.zeros((h, w), bool)
    B = np.zeros((h, w), bool)
    A[:a.shape[0], :a.shape[1]] = a
    B[:b.shape[0], :b.shape[1]] = b
    return float((A & B).sum() / max(1, (A | B).sum()))


def marked(H, O, placed_frames, pos, k=K):
    """HD-сборка с пометками: щель - пурпур, двойной край - голубой."""
    so = piece_masks(placed_frames, pos, O.size)
    a, b = cc.alpha(O), cc.alpha(H)
    band = np.zeros_like(a)
    for i in range(len(so)):
        for j in range(i + 1, len(so)):
            band |= grow(so[i], 2 * k) & grow(so[j], 2 * k)
    im = np.asarray(H.convert("RGBA")).copy()
    im[a & ~b & band] = (255, 0, 255, 255)
    return Image.fromarray(im, "RGBA")


def place_sheet(src_dir, where, placed, out, label_text):
    """Вырез карты вокруг составного на своём месте: слева оригинал, справа HD из src_dir; срез по этажу."""
    world = mm.World()
    t, b = where.split("/")
    z = max(p[1][2] for p in placed)
    hd, _m = mm.render(world, t, b, src_dir, K, None, maxz=z)
    base, _m = mm.render(world, t, b, None, K, None, maxz=z)
    xs = [p[1][0] for p in placed]
    ys = [p[1][1] for p in placed]
    m = 40
    box = (max(0, (min(xs) - m) * K), max(0, (min(ys) - m) * K),
           min(hd.width, (max(xs) + 32 + m) * K), min(hd.height, (max(ys) + 40 + m) * K))
    save(side([label(base.crop(box), "original, %s" % where), label(hd.crop(box), label_text)]), out)
    return out


def composite_seam(src_hd, der_hd, src_placed, der_placed, where, der_dir, out_dir, name, world=None):
    """COMPOSITE_SEAM_QA: исходный составной (ответ модели) и выведенный по кускам (зеркало / перекраска).
    src_hd / der_hd = {ключ: путь HD}; *_placed = [(ключ, (x, y, z))]; where / der_dir - карта выведенного
    и папка с выведенными файлами (для выреза на месте)."""
    world = world or mm.World()
    so = {k: orig_x4(world, k) for k, _p in src_placed}
    do = {k: orig_x4(world, k) for k, _p in der_placed}
    sh = {k: load_hd(p) for k, p in src_hd.items()}
    dh = {k: load_hd(p) for k, p in der_hd.items()}
    s_num, s_O, s_H = seam_numbers(so, sh, src_placed)
    d_num, d_O, d_H = seam_numbers(do, dh, der_placed)
    base_iou, hd_iou = mirror_iou(s_O, d_O), mirror_iou(s_H, d_H)
    d_num["mirror_iou"] = {"orig": round(base_iou, 3), "hd": round(hd_iou, 3)}
    if base_iou - hd_iou > ATTN["mirror_iou_drop_max"]:
        d_num["attention"].append("точка соединения после зеркала: совпадение %.2f против %.2f у оригинала"
                                  % (hd_iou, base_iou))
    if d_num["attention"] and not s_num["attention"]:
        suspect = "DERIVE_MIRROR_COMPOSITE_FAIL"      # исходник цел - ломает вывод по кускам, а не модель
    elif s_num["attention"]:
        suspect = "COMPOSITE_FAIL"                    # шов уже в ответе модели
    else:
        suspect = None
    _i, s_pos = assemble(so, src_placed)
    _i, d_pos = assemble(do, der_placed)
    rows = []
    for tag, O, H, frames, pos in (("source", s_O, s_H, so, s_pos), ("derived", d_O, d_H, do, d_pos)):
        rows.append(side([label(O, "%s original x4" % tag), label(H, "%s HD" % tag),
                          label(marked(H, O, frames, pos), "%s HD, hole=magenta" % tag)]))
    w = max(r.width for r in rows)
    sheet = Image.new("RGBA", (w, sum(r.height + 8 for r in rows)), BG)
    y = 0
    for r in rows:
        sheet.alpha_composite(r, (0, y))
        y += r.height + 8
    p1 = save(sheet, os.path.join(out_dir, "%s_seam.png" % name))
    p2 = place_sheet(der_dir, where, der_placed, os.path.join(out_dir, "%s_seam_map.png" % name),
                     "derived HD on map, %s" % where)
    return {"kind": "composite_seam_qa", "keys": [k for k, _p in der_placed], "from": [k for k, _p in src_placed],
            "checks": SEAM_CHECKS, "source": s_num, "derived": d_num, "suspect": suspect,
            "sheet": p1, "map_sheet": p2}


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("key")
    p.add_argument("--src", required=True, help="папка с <НАБОР>.PCK/<кадр>.png")
    p.add_argument("--map", required=True, dest="where", help="ТЕРРЕЙН/БЛОК")
    p.add_argument("--out", default="art/_review/tile_qa")
    p.add_argument("--mode", default="tile", choices=["tile", "adjacency"],
                   help="tile - TILE_QA (3x3 и карта), adjacency - ADJACENCY_QA (числа по кадру и карта)")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    world = mm.World()
    s, f = a.key.rsplit(":", 1)
    name = "%s_%s" % (s.upper(), f)
    if a.mode == "adjacency":
        rs = [adjacency(a.src, a.key, a.where, os.path.join(a.out, name + "_adjacency.png"), world)]
    else:
        rs = [repeat_sheet(os.path.join(a.src, s.upper() + ".PCK", f + ".png"), a.key,
                           os.path.join(a.out, name + "_3x3.png"), world),
              map_sheet(a.src, a.key, a.where, os.path.join(a.out, name + "_map.png"), world)]
    for r in rs:
        print(r)


if __name__ == "__main__":
    main()
