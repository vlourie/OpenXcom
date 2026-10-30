#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Подрезка выступа плоских полов с сохранением шва (тикет XP-000407, решение Vitali 30.10: «плоские полы, с сохранением
шва»). Правило - floors_overhang.cut_safe: альфа 0 вне силуэта классики x4 в верхней половине ромба (y < 128), кроме
пикселей, без которых в замощении 3x3 пропадает покрытие. Плоский пол - классика не выше строки 22 (rim_alpha.FLAT_TOP).
Каждый вариант пола <кадр>.vN.png режется своим cut_safe (op - маска классики того же кадра).

  партия 1 - плоские полы, стоящие на картах (usage.json > 0)
  партия 2 - остальные плоские

Заготовки: art/tickets/floors_cut/batch<N>/<НАБОР>_<кадр>[.vN].png (RGBA 128x160), список batch_list.tsv. Не ставится:
  * неплоские (ступени, камни, кусты - срез съедает контур);
  * исключения rim_alpha_skip.txt (решётки, задуманная расшивка, чужой rgb кромки);
  * MOUNTTROP 0-3, 10-14, 28-39 и FORESTRED:4 - их перерисовывает исполнитель по траве (тикет 410);
  * кадры, у которых после среза новый просвет шва R-439 или потеря покрытия замощения.

    py -3.13 tools\hdart\floors_cut_build.py build          # заготовки обеих партий + batch_list.tsv
    py -3.13 tools\hdart\floors_cut_build.py verify         # до установки: разбор rim_alpha check по заготовкам
    py -3.13 tools\hdart\floors_cut_build.py sheet          # лист 3x3: 10 случайных полов партии 1, было | после
Видеокарту и игру не трогает; в мод не пишет (ставит floors_cut_install.py).
"""
import argparse
import hashlib
import os
import random
import re
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
os.chdir(ROOT)

import numpy as np                  # noqa: E402
from PIL import Image, ImageDraw    # noqa: E402

import floors_overhang as fo        # noqa: E402
import rim_alpha as ra              # noqa: E402

OUT = os.path.join("art", "tickets", "floors_cut")
LIST = os.path.join(OUT, "batch_list.tsv")
REVIEW = os.path.join("art", "_review", "tickets_2026-10-30")
# кадры, которые перерисовывает исполнитель по траве (410) - в партию не входят
HOLD = {("MOUNTTROP", f) for f in list(range(0, 4)) + list(range(10, 15)) + list(range(28, 40))} | {("FORESTRED", 4)}
COLS = ["партия", "файл", "набор", "кадр", "вариант", "клеток_на_картах", "выступ_до", "выступ_остаток",
        "просвет_до", "просвет_после", "потеря_покрытия", "одобрен", "решение", "причина", "sha_источника"]


def one(cur, op, k):
    """-> (новый кадр, выступ до, остаток, просвет до, просвет после, потеря покрытия)."""
    top = fo.overhang(cur, op, k)[0]
    new, rest = fo.cut_safe(cur, op, k)
    lb = ra.leak(cur[..., 3], op, k)[0]
    la = ra.leak(new[..., 3], op, k)[0]
    return new, top, rest, lb, la, fo.lost_cover(cur[..., 3], new[..., 3], k)


def work(job):
    s, f, rel, _sha, approved, skip = job
    d = os.path.dirname(os.path.join(ra.GAME, rel))
    cur = np.array(Image.open(os.path.join(ra.GAME, rel)).convert("RGBA"))
    k = cur.shape[1] // 32
    frames = ra.classic(s)[0]
    op = frames[f] != 0
    flat = int(np.nonzero(op.any(1))[0].min() >= ra.FLAT_TOP)
    files = [("", os.path.join(ra.GAME, rel))]
    n = 1
    while os.path.exists(os.path.join(d, "%d.v%d.png" % (f, n))):
        files.append((".v%d" % n, os.path.join(d, "%d.v%d.png" % (f, n))))
        n += 1
    res = []
    lim = ra.LEAK * k * k
    for var, path in files:
        im = np.array(Image.open(path).convert("RGBA"))
        if im.shape != cur.shape or k != 4:
            res.append({"var": var, "bad": "размер %s" % (im.shape,), "top": 0})
            continue
        new, top, rest, lb, la, lost = one(im, op, k)
        with open(path, "rb") as fh:
            src = hashlib.sha256(fh.read()).hexdigest()
        r = {"var": var, "src": src, "top": top, "rest": rest, "lb": lb, "la": la, "lost": lost, "img": new,
             "changed": bool((new[..., 3] != im[..., 3]).any())}
        if la > lim and la > lb:
            r["bad"] = "новый просвет шва R-439 (%d -> %d px)" % (lb, la)
        elif lost > 0:
            r["bad"] = "потеря покрытия замощения %d px" % lost
        res.append(r)
    return {"s": s, "f": f, "flat": flat, "approved": approved, "skip": skip, "res": res}


def cmd_build(a):
    bp, man = ra.manifest()
    fl = fo.floors(man)
    us = fo.usage()
    with Pool(a.procs) as pool:
        out = pool.map(work, fl, chunksize=32)
    rows, batches = [], {1: 0, 2: 0}
    per_set = {1: 0, 2: 0}
    st = {"всего полов": len(out), "плоских": 0, "плоских с выступом": 0, "неплоских с выступом": 0,
          "исключения rim_alpha_skip": 0, "держим (410)": 0, "отбракованы проверкой": 0}
    for o in out:
        s, f = o["s"], o["f"]
        cells = sum(x[2] for x in us.get("%s:%d" % (s, f), []))
        todo = [r for r in o["res"] if r.get("top", 0) > 0 and r.get("changed")]
        if not todo:
            continue
        if not o["flat"]:
            st["неплоских с выступом"] += 1
            continue
        st["плоских с выступом"] += 1
        for r in todo:
            batch = 1 if cells > 0 else 2
            name = "%s_%d%s.png" % (s, f, r["var"])
            reason = ""
            if o["skip"]:
                reason = "исключение rim_alpha_skip.txt"
            elif (s, f) in HOLD:
                reason = "перерисовывает исполнитель по траве (410)"
            elif r.get("bad"):
                reason = r["bad"]
            if reason:
                st["исключения rim_alpha_skip"] += reason.startswith("исключение")
                st["держим (410)"] += reason.startswith("перерисовывает")
                st["отбракованы проверкой"] += not reason.startswith(("исключение", "перерисовывает"))
            row = {"партия": batch, "файл": name, "набор": s, "кадр": f, "вариант": r["var"].lstrip("."),
                   "клеток_на_картах": cells, "выступ_до": r["top"], "выступ_остаток": r["rest"],
                   "просвет_до": r["lb"], "просвет_после": r["la"], "потеря_покрытия": r["lost"],
                   "одобрен": {True: "да", False: "нет"}.get(o["approved"], ""),
                   "решение": "нет" if reason else "да", "причина": reason, "sha_источника": r["src"]}
            rows.append(row)
            if not reason:
                d = os.path.join(OUT, "batch%d" % batch)
                os.makedirs(d, exist_ok=True)
                Image.fromarray(r["img"], "RGBA").save(os.path.join(d, name))
                batches[batch] += 1
    rows.sort(key=lambda r: (r["партия"], r["набор"], r["кадр"], r["вариант"]))
    fo.write_tsv(rows, LIST, COLS)
    st["плоских"] = sum(1 for o in out if o["flat"])
    for k_, v in st.items():
        print("%-28s %s" % (k_, v))
    for b in (1, 2):
        mains = sum(1 for r in rows if r["партия"] == b and r["решение"] == "да" and not r["вариант"])
        vars_ = sum(1 for r in rows if r["партия"] == b and r["решение"] == "да" and r["вариант"])
        print("партия %d: файлов %d (основных %d, вариантов %d), не в партии %d" % (
            b, batches[b], mains, vars_, sum(1 for r in rows if r["партия"] == b and r["решение"] == "нет")))
    print("->", LIST)
    return 0


# ----------------------------------------------------------------------------- лист 3x3

def board(tile, item, k=4):
    """Замощение 3x3 на тёмном фоне: пол в каждой клетке, предмет в средней клетке рисуется после пола средней клетки,
    пол следующих клеток (по порядку отрисовки) ложится поверх основания предмета."""
    h, w = tile.shape[:2]
    W, H = 32 * k, 8 * k
    cv = Image.new("RGBA", (w + 2 * W, h + 4 * H), (18, 18, 22, 255))
    for r in range(3):
        for c in range(3):
            pos = (W + (c - r) * W // 2, (c + r) * H)
            cv.alpha_composite(Image.fromarray(tile, "RGBA"), pos)
            if (r, c) == (1, 1) and item is not None:
                cv.alpha_composite(Image.fromarray(item, "RGBA"), pos)
    return cv.convert("RGB")


def cmd_sheet(a):
    rows = fo.read_tsv(LIST)
    pool_ = [r for r in rows if r["партия"] == "1" and r["решение"] == "да" and not r["вариант"]]
    rnd = random.Random(30103)
    rnd.shuffle(pool_)
    picked, seen = [], set()
    for r in pool_:
        if r["набор"] not in seen:
            seen.add(r["набор"])
            picked.append(r)
        if len(picked) == 10:
            break
    item = np.array(Image.open(os.path.join(ra.GAME, "TERRAIN", "XB1BR.PCK", "52.png")).convert("RGBA"))
    fnt = ImageDraw.ImageDraw(Image.new("RGB", (1, 1))).getfont()
    from ticket_scene import font
    fnt = font(22)
    tiles = []
    for r in picked:
        cur = np.array(Image.open(os.path.join(ra.GAME, "TERRAIN", "%s.PCK" % r["набор"], "%s.png" % r["кадр"])).convert("RGBA"))
        new = np.array(Image.open(os.path.join(OUT, "batch1", r["файл"])).convert("RGBA"))
        tiles.append((r, board(cur, item), board(new, item)))
    bw, bh = tiles[0][1].size
    cols = 2
    cw, ch = bw * 2 + 12, bh + 36
    nrows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cw + 12) + 12, nrows * (ch + 12) + 12), (10, 10, 12))
    d = ImageDraw.Draw(sheet)
    for i, (r, was, after) in enumerate(tiles):
        x0, y0 = 12 + (i % cols) * (cw + 12), 12 + (i // cols) * (ch + 12)
        d.text((x0, y0 + 4), "%s:%s  выступ %s -> %s px, клеток %s   (было | после)" % (
            r["набор"], r["кадр"], r["выступ_до"], r["выступ_остаток"], r["клеток_на_картах"]),
            fill=(255, 220, 0), font=fnt)
        sheet.paste(was, (x0, y0 + 32))
        sheet.paste(after, (x0 + bw + 12, y0 + 32))
    os.makedirs(REVIEW, exist_ok=True)
    p = os.path.join(REVIEW, "floors_batch1_3x3.png")
    sheet.save(p, optimize=True)
    print("лист ->", p, sheet.size, [("%s:%s" % (r["набор"], r["кадр"])) for r, *_ in tiles])
    return 0


def cmd_verify(a):
    """До установки: тот же разбор, что rim_alpha.py check, но по заготовкам основных кадров (оверлей вместо игры)."""
    import shutil
    import tempfile
    rows = [r for r in fo.read_tsv(LIST) if r["решение"] == "да" and not r["вариант"]]
    tmp = tempfile.mkdtemp(prefix="floors_cut_verify_")
    jobs, skip = [], ra.load_skip()
    for r in rows:
        rel = "TERRAIN/%s.PCK/%s.png" % (r["набор"], r["кадр"])
        dst = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(OUT, "batch%s" % r["партия"], r["файл"]), dst)
        jobs.append((r["набор"], int(r["кадр"]), rel, "floors_cut_safe", "0" * 12))
    ra.GAME = tmp
    bad = 0
    for j in jobs:
        m = ra.measure(j)
        if m["класс"] in ("fix", "review") and "%s:%s" % (j[0], j[1]) not in skip:
            bad += 1
            print("R-439 просвет шва: %s:%s %s просвет %s" % (j[0], j[1], m["класс"], m["просвет"]))
    print("заготовок основных кадров проверено: %d, новых просветов R-439: %d" % (len(jobs), bad))
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "sheet", "verify"])
    ap.add_argument("--procs", type=int, default=10)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    return {"build": cmd_build, "sheet": cmd_sheet, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
