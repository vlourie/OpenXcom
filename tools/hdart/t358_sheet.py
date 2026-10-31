#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Лист приёмки XP-000358: машина целиком классика x4 | было | стало, швы (пурпур), таблицы мерок."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import t358_build as tb  # noqa: E402

K = 4
OUT = tb.ROOT / "art" / "_review" / "tickets_2026-10-28"
LUM = tb.LUM
sc = tb.ts.Scene()
ITEMS = tb.ITEMS


def lum(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def classic_f(f):
    return sc.classic(tb.SET, f)


def old_f(f):
    return tb.hd_old(f)


def mk_new(frames):
    return lambda f: frames[f]


def compose(getf, k, bg=(120, 110, 100)):
    W, H = tb.CW * k, tb.CH * k
    base = Image.new("RGBA", (W, H), bg + (255,))
    for it in ITEMS:
        ox, oy = tb.pos(it)
        base.alpha_composite(getf(it[4]), (ox * k, oy * k))
    return base


def owner_map(getf, k):
    own = -np.ones((tb.CH * k, tb.CW * k), int)
    L = np.zeros((tb.CH * k, tb.CW * k))
    for it in ITEMS:
        f = it[4]
        im = np.array(getf(f)).astype(float)
        if im.shape[0] != 40 * k:
            raise SystemExit("размер")
        ox, oy = tb.pos(it)
        m = im[..., 3] >= 200
        sl = (slice(oy * k, oy * k + 40 * k), slice(ox * k, ox * k + 32 * k))
        own[sl][m] = f
        L[sl][m] = lum(im)[m]
    return own, L


def seams(getf, k):
    """как в xp358.py: средний перепад яркости через границу владельцев по парам кадров, и внутри кадра."""
    own, L = owner_map(getf, k)
    pairs, inner = {}, []
    for dy, dx in ((0, 1), (1, 0)):
        a = own[:own.shape[0] - dy, :own.shape[1] - dx]
        b = own[dy:, dx:]
        la = L[:L.shape[0] - dy, :L.shape[1] - dx]
        lb = L[dy:, dx:]
        ok = (a >= 0) & (b >= 0)
        same = ok & (a == b)
        diff = ok & (a != b)
        inner.append(np.abs(la - lb)[same])
        for fa, fb, v in zip(a[diff], b[diff], np.abs(la - lb)[diff]):
            pairs.setdefault(tuple(sorted((int(fa), int(fb)))), []).append(v)
    return np.concatenate(inner).mean(), {kk: (float(np.mean(v)), len(v)) for kk, v in pairs.items()}, own, L


def seam_overlay(base, own, L, thr):
    arr = np.array(base).copy()
    for dy, dx in ((0, 1), (1, 0)):
        a = own[:own.shape[0] - dy, :own.shape[1] - dx]
        b = own[dy:, dx:]
        la = L[:L.shape[0] - dy, :L.shape[1] - dx]
        lb = L[dy:, dx:]
        m = (a >= 0) & (b >= 0) & (a != b) & (np.abs(la - lb) >= thr)
        ys, xs = np.nonzero(m)
        for y, x in zip(ys, xs):
            arr[y, x] = (255, 0, 255, 255)
            arr[y + dy, x + dx] = (255, 0, 255, 255)
    return Image.fromarray(arr)


def tone_table(frames):
    rows = []
    for it in ITEMS:
        f = it[4]
        c = np.array(classic_f(f)).astype(float)
        o = np.array(old_f(f)).astype(float)
        n = np.array(frames[f]).astype(float)
        mc = c[..., 3] > 0
        lc = lum(c)[mc].mean()
        r = {"frame": f, "lumC": lc}
        for nm, a in (("old", o), ("new", n)):
            ma = a[..., 3] > 128
            r["lum_" + nm] = lum(a)[ma].mean()
            r["ratio_" + nm] = r["lum_" + nm] / lc
            r["out_" + nm] = int((ma & ~mc).sum())
            r["cover_" + nm] = 100.0 * (ma & mc).sum() / mc.sum()
            r["std_" + nm] = lum(a)[ma].std()
        r["std_C"] = lum(c)[mc].std()
        rows.append(r)
    return rows


def overlap_check(getf):
    """Число пикселей холста x4, лежащих под масками >=2 кадров, и наибольшая разница их цветов между кадрами."""
    H, W = tb.CH * K, tb.CW * K
    cnt = np.zeros((H, W), int)
    mn = np.full((H, W, 3), 1e9)
    mx = np.full((H, W, 3), -1e9)
    for it in ITEMS:
        f = it[4]
        ox, oy = tb.pos(it)
        c = np.array(classic_f(f)).astype(float)
        a = np.array(getf(f)).astype(float)
        m = c[..., 3] > 0
        sl = (slice(oy * K, oy * K + 40 * K), slice(ox * K, ox * K + 32 * K))
        cnt[sl] += m
        v = a[..., :3]
        mn[sl] = np.where(m[..., None], np.minimum(mn[sl], v), mn[sl])
        mx[sl] = np.where(m[..., None], np.maximum(mx[sl], v), mx[sl])
    two = cnt >= 2
    d = (mx - mn)[two]
    return int(two.sum()), float(d.max()), float(d.mean())


def font(s):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", s)
    except Exception:
        return ImageFont.load_default()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    frames, low, out, mk = tb.build()
    getn = mk_new(frames)
    res = {}
    for nm, g in (("classic", classic_f), ("old", old_f), ("new", getn)):
        kk = 1 if nm == "classic" else K
        gg = (lambda f, g=g: g(f).resize((32, 40), Image.NEAREST)) if nm == "classic" else g
        # классика меряется как в xp358.py: в родном масштабе k=1; здесь холст у неё x4 NEAREST, поэтому берём base
        res[nm] = seams(gg, kk)
    res1 = {}
    for nm, g in (("old", old_f), ("new", getn)):
        res1[nm] = seams(lambda f, g=g: g(f).resize((32, 40), Image.BOX), 1)
    print("перепад внутри кадра: классика %.2f, было %.2f, стало %.2f (k=1: было %.2f, стало %.2f)" % (res["classic"][0], res["old"][0], res["new"][0], res1["old"][0], res1["new"][0]))
    keys = sorted(set(res["old"][1]) | set(res["new"][1]) | set(res["classic"][1]))
    table = []
    print("%-8s %12s %12s %12s   (n)" % ("шов", "классика", "было", "стало"))
    ok_all = True
    for key in keys:
        c = res["classic"][1].get(key, (float("nan"), 0))
        o = res["old"][1].get(key, (float("nan"), 0))
        n = res["new"][1].get(key, (float("nan"), 0))
        good = (n[0] <= c[0]) if c[1] else True
        # у HD пиксель в 4 раза мельче: честное сравнение - перепад на ПИКСЕЛЬ классики, то есть x4
        o1 = res1["old"][1].get(key, (float("nan"), 0))
        n1 = res1["new"][1].get(key, (float("nan"), 0))
        table.append({"pair": "%d-%d" % key, "classic": c[0], "old": o[0], "new": n[0], "old_k1": o1[0], "new_k1": n1[0],
                      "nC": c[1], "nO": o[1], "nN": n[1]})
        good1 = (n1[0] <= c[0]) if c[1] else True
        print("%-8s %12.1f %12.1f %12.1f   | k=1 (4x4->1): было %6.1f стало %6.1f  %d/%d/%d  %s" % ("%d-%d" % key, c[0], o[0], n[0], o1[0], n1[0], c[1], o[1], n[1], "" if (good and good1) else "<-- хуже классики"))
        ok_all &= good and good1
    rows = tone_table(frames)
    print("%-5s %7s | %7s %6s %7s %6s | %7s %6s %7s %6s | std C" % ("кадр", "lumC", "было", "отн", "вышло", "покр", "стало", "отн", "вышло", "покр"))
    for r in rows:
        print("%-5d %7.1f | %7.1f %6.3f %7d %5.1f%% | %7.1f %6.3f %7d %5.1f%% | %.1f (было %.1f, стало %.1f)" % (
            r["frame"], r["lumC"], r["lum_old"], r["ratio_old"], r["out_old"], r["cover_old"], r["lum_new"], r["ratio_new"], r["out_new"], r["cover_new"], r["std_C"], r["std_old"], r["std_new"]))
    json.dump({"inner": [res[k][0] for k in ("classic", "old", "new")], "seams": table, "tone": rows}, open(OUT / "xp358_fix_stats.json", "w"), ensure_ascii=False, indent=1, default=float)
    print("все швы не хуже классики:", ok_all)
    for nm, g in (("было", old_f), ("стало", getn)):
        print("перекрытия кадров (пиксели, закрытые >=2 кадрами по маске классики):", nm, overlap_check(g))

    # ---- лист
    F, FS = font(22), font(16)
    Cc = compose(lambda f: classic_f(f), K)
    Oc = compose(old_f, K)
    Nc = compose(getn, K)
    own_o, L_o = res["old"][2], res["old"][3]
    own_n, L_n = res["new"][2], res["new"][3]
    own_c, L_c = seams(lambda f: classic_f(f), K)[2:]
    O_s = seam_overlay(Oc, own_o, L_o, 10)
    N_s = seam_overlay(Nc, own_n, L_n, 10)
    C_s = seam_overlay(Cc, own_c, L_c, 10)
    pad = 12

    def row(its):
        w = sum(i[1].width for i in its) + pad * (len(its) + 1)
        h = max(i[1].height for i in its)
        r = Image.new("RGBA", (w, h + 34), (35, 35, 40, 255))
        dr = ImageDraw.Draw(r)
        x = pad
        for t, im in its:
            dr.text((x, 4), t, font=F, fill=(255, 255, 255, 255))
            r.alpha_composite(im, (x, 30))
            x += im.width + pad
        return r
    r1 = row([("Классика x4", Cc), ("Было (HD 15.10)", Oc), ("Стало (вариант A)", Nc)])
    r2 = row([("Швы классики (скачок >=10)", C_s), ("Швы было", O_s), ("Швы стало", N_s)])
    s = Image.new("RGBA", (max(r1.width, r2.width), r1.height + r2.height), (35, 35, 40, 255))
    s.alpha_composite(r1, (0, 0))
    s.alpha_composite(r2, (0, r1.height))
    s.convert("RGB").save(OUT / "xp358_fix_sheet.png")
    print("лист", s.size)
    # крупно: крыша и капот, было | стало
    box = (20 * K, 10 * K, 100 * K, 70 * K)

    def crop(im):
        return im.crop((box[0], box[1], box[2] + 0, box[3])).resize(((box[2] - box[0]) * 2, (box[3] - box[1]) * 2), Image.LANCZOS)
    box2 = (0, 40 * K, 90 * K, 104 * K)
    big = row([("Крыша: было", Oc.crop((30 * K, 20 * K, 110 * K, 60 * K))), ("Крыша: стало", Nc.crop((30 * K, 20 * K, 110 * K, 60 * K))),
               ("Крыша: классика", Cc.crop((30 * K, 20 * K, 110 * K, 60 * K)))])
    big2 = row([("Капот/колесо: было", Oc.crop((0, 50 * K, 70 * K, 104 * K))), ("стало", Nc.crop((0, 50 * K, 70 * K, 104 * K))),
                ("классика", Cc.crop((0, 50 * K, 70 * K, 104 * K)))])
    s2 = Image.new("RGBA", (max(big.width, big2.width), big.height + big2.height), (35, 35, 40, 255))
    s2.alpha_composite(big, (0, 0))
    s2.alpha_composite(big2, (0, big.height))
    s2.convert("RGB").save(OUT / "xp358_fix_detail.png")


if __name__ == "__main__":
    main()
