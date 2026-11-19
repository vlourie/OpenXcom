#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Ровная кромка плоских полов (правило 12, R-121, R-601; разбор XP-000497, вариант 3 Vitali 05.11). Только перепись и проба.

Видимая линия между двумя полами - верхняя кромка пола, нарисованного позже. Поэтому чинится она у всех сразу:
  верх (y < 128) - прямая по ромбу, вписанному в силуэт классики x4: не выступает за силуэт, решение 30.10 (XP-000407) цело;
  низ (y >= 128) - точный ромб с перехлёстом t492_build.OVER_LOW: закрывает зубцы, снятые с верха соседа (R-599), цвет под ним - ближайший.
Плоские полы с целым ромбом классики - верх и низ. Целый ромб с кочками (трава): верх как есть, только низ - иначе дыра у соседа.
Неполные полы (воронки с дырой, плиты с пустотой) не трогаем.

    py -3.13 tools\hdart\floor_edge.py census   # сколько кадров заденет -> art/_review/tickets_2026-11-05/floor_edge_census.tsv
    py -3.13 tools\hdart\floor_edge.py probe    # сцены было/стало на сейвах 496, 497 -> floor_edge_car.png, floor_edge_city.png
    py -3.13 tools\hdart\floor_edge.py check    # страж сетки 3x3 (R-439) по всем полам после правки
    py -3.13 tools\hdart\floor_edge.py install [НАБОР...] [--yes]   # в мод только с --yes, под очередью правок; решение Vitali 05.11 - все полы
Видеокарту не трогает.
"""
import contextlib
import io
import os
import sys
from collections import Counter
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

import numpy as np                  # noqa: E402
from PIL import Image               # noqa: E402
from scipy import ndimage           # noqa: E402

import build_hd_pack as bp          # noqa: E402
import floors_overhang as fo        # noqa: E402
import rim_alpha as ra              # noqa: E402
import t492_build as tb             # noqa: E402

K = 4
W, H = 32 * K, 40 * K
OUT = os.path.join("art", "_review", "tickets_2026-11-05")
MAGENTA = (255, 0, 255, 255)
SOFT = 0.03
RIM_D = 0.97        # отсюда к краю снизу цвет можно заменить: рамка кадра начинается не раньше
RIM_RATIO = 0.85    # кромка темнее середины заметно сильнее, чем в классике, - это рамка HD, а не рисунок
RIM_GAIN = 3.0      # потолок осветления кольца: тёмный почти до чёрного край не должен превратиться в шум
CAND = os.path.join("art", "tickets", "floor_edge")
WORD = "по слову Vitali 05.11: ровная кромка всех полов (XP-000497)"
FULL_D = 0.85       # целый ромб: классика занята вся до этой меры
FLAT_D = 1.11       # плоский: дальше этой меры у классики ничего нет (ступени доходят до 1.1016, R-601)
DIAM = ra.diamond(K)[0]
ROW = np.arange(H)[:, None] * np.ones((1, W))
TOP = (ROW < 32 * K)


def inner_d(op):
    """Мера вписанного ромба: наименьшая d среди пикселей верхней половины вне силуэта классики."""
    sil = ra.silhouette(op, K)
    out = TOP & ~sil & (DIAM < 2.0)
    return float(DIAM[out].min()) if out.any() else 1.0


def is_whole(op):
    """Целый ромб: классика занята вся до FULL_D; кочки и холмы над ним не мешают."""
    return bool(ra.silhouette(op, K)[DIAM <= FULL_D].all())


def is_full(op):
    """Плоский пол с целым ромбом: классика не выходит за перехлёст; трава с кочками и холмы - нет."""
    return is_whole(op) and not ra.silhouette(op, K)[DIAM > FLAT_D].any()


def ladder(alpha):
    """Лесенка верхней кромки: левая граница по рядам идёт скачками от 6 пикселей."""
    rows = [y for y in range(32 * K) if (alpha[y] > 128).any()]
    if len(rows) < 8:
        return False
    left = np.array([int(np.argmax(alpha[y] > 128)) for y in rows])
    return int((np.abs(np.diff(left)) >= 6).sum()) >= 3


def straight(cur, op, flat=True):
    """-> новый кадр RGBA: низ - точный ромб с перехлёстом; верх - прямой по вписанному ромбу, у пола с кочками как есть."""
    # сплошной перехлёст снизу должен доходить до конца мягкого края соседа сверху, иначе на шве тёмная сетка (R-439)
    low = np.clip((1.0 + tb.OVER_LOW + SOFT - DIAM) / tb.OVER, 0, 1)
    was = cur[..., 3] / 255.0
    if flat:
        a = np.where(TOP, np.clip((min(inner_d(op), 1.0) - DIAM) / SOFT, 0, 1), low)
    else:
        a = np.where(TOP, was, np.maximum(was, low))
    keep = DIAM < FULL_D    # середина кадра как есть: у стекла и воды своя прозрачность
    a = np.where(keep, was, a)
    solid = (cur[..., 3] >= 250) | keep
    _, ind = ndimage.distance_transform_edt(~solid, return_indices=True)
    new = np.zeros_like(cur)
    new[..., :3] = cur[..., :3][ind[0], ind[1]]
    new[..., :3][solid] = cur[..., :3][solid]
    new[..., 3] = np.rint(a * 255).astype(np.uint8)
    return new


def work(job):
    s, f, rel, sha = job
    cs = ra.classic(s)
    op = cs[0][f] != 0
    a = np.asarray(Image.open(os.path.join(ra.GAME, rel)).convert("RGBA"))[..., 3]
    return s, f, rel, sha, is_full(op), ladder(a), round(inner_d(op), 4), is_whole(op)


def cmd_census():
    man = bp.load()
    js = [(s, f, rel, sha) for s, f, rel, sha, _a, _b in fo.floors(man)]
    with Pool(max(2, (os.cpu_count() or 4) - 2)) as p:
        rows = p.map(work, js, 40)
    us = fo.usage()
    print("полов MCD тип 0 с HD:", len(rows), "разных файлов:", len({r[3] for r in rows}))
    full = [r for r in rows if r[4]]
    tuft = [r for r in rows if r[7] and not r[4]]
    print("плоских с целым ромбом:", len(full), "целый ромб с кочками (только низ):", len(tuft), "разных файлов:", len({r[3] for r in tuft}),
          "неполных (не трогаем):", len(rows) - len(full) - len(tuft))
    lad = [r for r in full if r[5]]
    print("из целых - с лесенкой сверху:", len(lad), "разных файлов:", len({r[3] for r in lad}))
    print("вписанный ромб, частые значения:", Counter(r[6] for r in full).most_common(6))
    # варианты .vN у этих кадров
    nv = 0
    for r in full + tuft:
        base = os.path.join(ra.GAME, r[2])[:-4]
        nv += sum(os.path.exists("%s.v%d.png" % (base, v)) for v in range(1, 8))
    print("файлов вариантов .vN у целых и с кочками:", nv)
    with open(os.path.join(OUT, "floor_edge_census.tsv"), "w", encoding="utf-8-sig") as fh:
        fh.write("набор\tкадр\tцелый\tлесенка\tвписанный\n")
        for r in rows:
            fh.write("%s\t%d\t%s\t%s\t%s\n" % (r[0], r[1], "да" if r[4] else "нет", "да" if r[5] else "нет", r[6]))
    print("usage записей:", len(us))
    # полы без HD: классика останется лесенкой и не закроет снятые зубцы соседа
    have = {(r[0], r[1]) for r in rows}
    miss = Counter()
    pck = os.path.join(ra.GAME, "..", "..", "Piratez", "TERRAIN")
    for name in sorted(os.listdir(pck)):
        if not name.upper().endswith(".PCK"):
            continue
        s = name[:-4]
        cs = ra.classic(s)
        if cs is None or (cs[2], cs[3]) != (32, 40):
            continue
        for f, tp in enumerate(cs[1]):
            if f < len(cs[0]) and cs[0][f] is not None and 0 in tp and (s, f) not in have:
                if is_full(cs[0][f] != 0):
                    miss[s] += 1
    print("полов с целым ромбом без HD:", sum(miss.values()), "наборов:", len(miss), miss.most_common(5))


def guard(job):
    """Страж R-439 на новом кадре: просвет сетки 3x3 до и после правки."""
    s, f, rel, _sha = job
    op = ra.classic(s)[0][f] != 0
    if not is_whole(op):
        return None
    cur = np.asarray(Image.open(os.path.join(ra.GAME, rel)).convert("RGBA"))
    return s, f, ra.leak(cur[..., 3], op, K)[0], ra.leak(straight(cur, op, is_full(op))[..., 3], op, K)[0]


def cmd_check():
    js = [(s, f, rel, sha) for s, f, rel, sha, _a, _b in fo.floors(bp.load())]
    with Pool(max(2, (os.cpu_count() or 4) - 2)) as p:
        rows = [r for r in p.map(guard, js, 40) if r]
    bad = [r for r in rows if r[3] > 0]
    print("проверено:", len(rows), "просвет сейчас:", sum(r[2] > 0 for r in rows), "просвет после правки:", len(bad), "из них новых:", sum(r[2] == 0 for r in bad))
    print("примеры:", bad[:12])


def rim_tone(new, fr):
    """Тёмная рамка снизу, которой нет в классике: лесенка её рвала, ровная кромка сделала бы сплошной полосой.
    -> (кадр, правился ли): кромка темнее классики - цвет кромки от середины клетки."""
    lum = lambda v: v[..., :3].astype(float) @ np.array([0.299, 0.587, 0.114])
    inner, outer = (~TOP) & (DIAM >= 0.75) & (DIAM < RIM_D), (~TOP) & (DIAM >= 1.0) & (DIAM < 1.1)
    cl = ra.classic_rgba(fr, K)
    seen = cl[..., 3] > 128
    if not (inner & seen).any() or not (outer & seen).any():
        return new, False
    hd = lum(new)
    tone = hd[outer].mean() / max(1.0, hd[inner].mean())
    base = lum(cl)
    if tone >= RIM_RATIO * base[outer & seen].mean() / max(1.0, base[inner & seen].mean()):
        return new, False
    # свой рисунок, только светлее, кольцо за кольцом: протянутый цвет даёт мазки, зеркало удваивает линии у края
    want = new[..., :3][inner].mean(axis=0) * base[outer & seen].mean() / max(1.0, base[inner & seen].mean())
    out = new.astype(float)
    for d0 in np.arange(RIM_D, 1.2, 0.02):
        ring = (~TOP) & (DIAM >= d0) & (DIAM < d0 + 0.02)
        if ring.any():
            out[..., :3][ring] *= np.minimum(RIM_GAIN, want / np.maximum(1.0, new[..., :3][ring].mean(axis=0)))
    return np.clip(np.rint(out), 0, 255).astype(np.uint8), True


def build(job):
    """Новый кадр из блоба манифеста -> (rel, путь, просвет до, просвет после, рамка правилась); не целый ромб -> None."""
    rel, sha, s, f = job
    fr = ra.classic(s)[0][f]
    op = fr != 0
    if not is_whole(op):
        return None
    with Image.open(bp.blob_path(sha, rel)) as im:
        cur = np.asarray(im.convert("RGBA"))
    if cur.shape != (H, W, 4):
        return None
    out, toned = rim_tone(straight(cur, op, is_full(op)), fr)
    path = os.path.join(CAND, s, os.path.basename(rel))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(out, "RGBA").save(path, "PNG", optimize=True)
    return rel, path, ra.leak(cur[..., 3], op, K)[0], ra.leak(out[..., 3], op, K)[0], toned


def cmd_install():
    """floor_edge.py install [НАБОР...] [--yes]: заготовки в art/tickets/floor_edge; с --yes - в мод. Откат - manifest/history и хранилище.
    Как floors_cut_install: approved/approval кадра не повышаются, прежний генератор пишется в версию."""
    import hashlib
    sets = {a for a in sys.argv[2:] if not a.startswith("--")}
    man = bp.load()
    fs = man["files"]
    js = []
    for s, f, rel, sha, _a, skip in fo.floors(man):
        if skip or (sets and s not in sets):
            continue
        for r in [rel] + [rel[:-4] + ".v%d.png" % v for v in range(1, 8)]:
            if r in fs:     # уже правленный строим заново из кадра до правки, повторный прогон ничего лишнего не пишет
                done = fs[r].get("generator") == "floor_edge"
                js.append((r, fs[r]["replaced"] if done else fs[r]["sha256"], s, f))
    print("кандидатов (кадры и варианты):", len(js))
    with Pool(max(2, (os.cpu_count() or 4) - 2)) as p:
        rows = [r for r in p.imap_unordered(build, js, 20) if r]
    bad = [r for r in rows if r[3] > 0 and r[3] > r[2]]
    print("целых:", len(rows), "просвет сейчас:", sum(r[2] > 0 for r in rows), "после:", sum(r[3] > 0 for r in rows), "стало хуже:", len(bad), bad[:8])
    print("тёмная рамка снята:", sum(r[4] for r in rows), "примеры:", [r[0][8:] for r in rows if r[4]][:10])
    rows = [r for r in rows if bp.sha256_file(r[1]) != fs[r[0]]["sha256"]]
    print("к установке:", len(rows), "объём заготовок, МБ: %.1f" % (sum(os.path.getsize(r[1]) for r in rows) / 1e6))
    if "--yes" not in sys.argv:
        raise SystemExit("сухой прогон; --yes - записать в мод (под очередью правок)")
    if bad:
        raise SystemExit("стало хуже - не ставлю")
    rels = []
    for rel, path, _b, _a, _t in sorted(rows):
        old = fs[rel]
        done = old.get("generator") == "floor_edge"
        bp.stage(man, rel, path, generator="floor_edge",
                 generator_version=old.get("generator_version") if done else
                 "floor_edge 05.11: верх по вписанному ромбу, низ с перехлёстом; было: %s %s" % (old.get("generator"), old.get("generator_version") or ""),
                 source_path=path.replace(os.sep, "/"), approved=old.get("approved", False),
                 approval=old.get("approval") if done else "%s; %s" % (old.get("approval") or "", WORD), derived_from=old.get("derived_from"))
        if done:
            fs[rel]["replaced"] = old["replaced"]
        rels.append(rel)
    bp.save(man, why="полы: ровная кромка (%d файлов) %s" % (len(rels), WORD))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for root in bp.TARGETS.values():
        for rel in rels:
            with open(os.path.join(root, rel), "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != fs[rel]["sha256"]:
                    raise SystemExit("РАСХОДИТСЯ %s %s" % (root, rel))
    print("сверено: обе копии, файлов", len(rels))


def cmd_probe():
    import map_truth as mt
    import ticket_scene as ts
    sc = ts.Scene()
    cache = {}

    def edged(sn, f, spr):
        key = (sn, f)
        if key not in cache:
            cs = ra.classic(sn)
            cache[key] = None
            if cs is not None and f < len(cs[0]) and cs[0][f] is not None and 0 in cs[1][f] and is_whole(cs[0][f] != 0):
                cache[key] = Image.fromarray(straight(np.asarray(spr.convert("RGBA")), cs[0][f] != 0, is_full(cs[0][f] != 0)), "RGBA")
        return cache[key] or spr

    def render(B, D, box, new, bg=MAGENTA):
        x0, x1, y0, y1 = box
        wd, ht = ((x1 - x0) + (y1 - y0)) * 16 + 32, ((x1 - x0) + (y1 - y0)) * 8 + 80
        im = Image.new("RGBA", (wd * K, ht * K), bg)
        ox = (y1 - y0) * 16
        for y in range(y0, y1):
            for x in range(x0, x1):
                for p in range(4):
                    c = B.part(0, y, x, p)
                    if c is None:
                        continue
                    sn, mid = B.sets[c[0]], c[1]
                    if mid >= len(D.mcd(sn)):
                        continue
                    r = D.mcd(sn)[mid]
                    f = r["frames"][0]
                    spr = sc.hd(sn, f)
                    if spr is None:
                        spr = sc.classic(sn, f)
                    if spr is None:
                        continue
                    if spr.width != W:
                        spr = spr.resize((W, H), Image.NEAREST)
                    elif new and p == 0:
                        spr = edged(sn, f, spr)
                    im.alpha_composite(spr.convert("RGBA"), ((ox + ((x - x0) - (y - y0)) * 16) * K, (((x - x0) + (y - y0)) * 8 - r["yoff"] + 20) * K))
        return im

    crop = {"car": (480, 400), "city": (800, 300)}
    for name, save, box in (("car", "census/tickets/XP-000497/files/02__autobattle_.asav", (37, 50, 38, 50)),
                            ("city", "census/tickets/XP-000496/files/02_snapshot.sav", (12, 28, 12, 28))):
        B = mt.Battle(save)
        with contextlib.redirect_stdout(io.StringIO()):
            D = mt.Data(B.mods)
        a, b = render(B, D, box, False), render(B, D, box, True)
        # просвет - и полный, и частичный: пиксель зависит от цвета фона
        blk = (0, 0, 0, 255)
        thru = lambda v, w: (np.abs(np.asarray(v).astype(int) - np.asarray(w).astype(int)).max(axis=2) > 8)
        fresh = thru(b, render(B, D, box, True, blk)) & ~thru(a, render(B, D, box, False, blk))
        # внешняя кромка вырезки не считается: за ней сосед просто не нарисован
        x0, x1, y0, y1 = box
        ox = (y1 - y0) * 16
        inner = np.zeros(fresh.shape, bool)
        for y in range(y0 + 1, y1):
            for x in range(x0 + 1, x1):
                px, py = (ox + ((x - x0) - (y - y0)) * 16) * K, (((x - x0) + (y - y0)) * 8 + 20) * K
                inner[py:py + H, px:px + W] |= DIAM < 1.0
        rim = int((fresh & ~inner).sum())
        fresh &= inner
        print(name, "размер", a.size, "кадров заменено:", sum(v is not None for v in cache.values()), "новых дыр внутри px:", int(fresh.sum()),
              "связных:", int(ndimage.label(fresh)[1]), "по внешней кромке вырезки px:", rim)
        cx, cy = crop[name]
        pair = Image.new("RGB", (2 * 800 + 12, 560), (24, 24, 28))
        pair.paste(a.crop((cx, cy, cx + 800, cy + 560)).convert("RGB"), (0, 0))
        pair.paste(b.crop((cx, cy, cx + 800, cy + 560)).convert("RGB"), (812, 0))
        pair.save(os.path.join(OUT, "floor_edge_%s.png" % name))
        vis = np.asarray(b.convert("RGB")).copy()
        vis[ndimage.binary_dilation(fresh, iterations=3)] = (255, 255, 0)
        Image.fromarray(vis).save(os.path.join(OUT, "floor_edge_%s_holes.png" % name))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"census": cmd_census, "probe": cmd_probe, "check": cmd_check, "install": cmd_install}[sys.argv[1]]()
