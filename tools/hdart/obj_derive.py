#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Члены семейства из нарисованной основы: перекраска и зеркало без нового заказа модели.

29.09 Vitali: синее и красное кресло - один предмет, стулья - один стул, повёрнутый. Нарисованные
порознь, они выходят разными вещами (партия made01: FRNITURE 8 и 9, 2 и 3). Здесь член семейства
(obj_families.py, связи «перекраска» и «зеркало») получается из HD-кадра основы:

  перекраска - яркость HD-пикселя умножается на отношение яркостей оригиналов (член / основа),
               цветность (Cb, Cr) сдвигается на разницу цветности оригиналов. Множитель по яркости
               скалярный (R-030), карты считаются на оригинале 32x40 и растягиваются гладко - сетки
               базового пикселя на кадре нет (как mirror_frames.relit_frame). Рисунок, складки и
               фактура - от основы, один в один;
  зеркало    - основа переворачивается, свет и цвет возвращаются тем же переносом от перевёрнутого
               оригинала основы к своему (R-054: художник отражал форму, свет оставлял на месте).

    py -3.13 tools/hdart/obj_derive.py --src art/objects/made01_turbo --out art/objects/derive_turbo
    py -3.13 tools/hdart/obj_derive.py --src ... --out ... --only 53,79

Кадры основы ищутся в --src (<НАБОР>.PCK/<кадр>.png), выведенные кладутся в --out под своими
номерами. В пак НЕ идёт: сначала лист.

Pipeline v2: семейства - art/objects/families/families.json (obj_families.py). Член выводится только
из канонического кадра и только при решении AUTO или HUMAN_APPROVED; кандидаты на проверке не
выводятся. В --out/derived.json на каждый файл - из чего выведен, семейство, его ревизия и sha256:
по ним manifest отличит вывод устаревшей ревизии (раздел 36).
"""
import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageFilter                  # noqa: E402

import asset_rev as ar                             # noqa: E402
import map_mockup as mm                             # noqa: E402

ENC = "utf-8-sig"
# версия алгоритма вывода: меняется при любой правке transfer/derive - все выведенные кадры станут STALE
# (asset_rev, derive_rev)
DERIVE_VERSION = "derive-2026-09-29.1"


def ycc(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return y, 0.564 * (b - y), 0.713 * (r - y)


def rgb(y, cb, cr):
    r = y + 1.403 * cr
    b = y + 1.773 * cb
    g = (y - 0.299 * r - 0.114 * b) / 0.587
    return np.stack([r, g, b], -1)


def spread(v, m, n=6):
    """Значения за силуэтом - от ближайших внутри: кайма HD-кадра шире силуэта оригинала."""
    v, m = v.copy(), m.copy()
    for _ in range(n):
        acc, cnt = np.zeros_like(v), np.zeros_like(v)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            acc += np.roll(np.where(m, v, 0), (dy, dx), (0, 1))
            cnt += np.roll(m.astype(np.float32), (dy, dx), (0, 1))
        grow = ~m & (cnt > 0)
        v[grow] = acc[grow] / cnt[grow]
        m = m | grow
    return v


def soft(v, m):
    """Среднее по окну 3x3 внутри силуэта: сглаживает дизеринг, не подмешивая фон."""
    acc, cnt = np.zeros_like(v), np.zeros_like(v)
    mf = m.astype(np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            wgt = 1.0 if dy == 0 and dx == 0 else 0.5
            acc += wgt * np.roll(v * mf, (dy, dx), (0, 1))
            cnt += wgt * np.roll(mf, (dy, dx), (0, 1))
    return np.where(cnt > 0, acc / np.maximum(cnt, 1e-6), v)


def up(v, size):
    lo, hi = float(v.min()), float(v.max())
    span = max(hi - lo, 1e-3)
    im = Image.fromarray(((v - lo) / span * 65535).astype(np.uint16).astype(np.int32), "I")
    big = np.asarray(im.resize(size, Image.BILINEAR), np.float32) / 65535 * span + lo
    return big


def transfer(hd, ob, ot):
    """HD-кадр основы hd (RGBA x4), оригинал основы ob и оригинал члена ot (RGBA 32x40, в том же
    положении, что hd) -> HD-кадр члена."""
    a = np.asarray(hd.convert("RGBA"), np.float32)
    b = np.asarray(ob.convert("RGBA"), np.float32)
    t = np.asarray(ot.convert("RGBA"), np.float32)
    m = (b[..., 3] > 0) & (t[..., 3] > 0)
    # дизеринг оригинала: отношение попиксельно даёт пятна на HD (туалет 13 из 14) - сначала сгладить
    yb, cbb, crb = (soft(v, m) for v in ycc(b))
    yt, cbt, crt = (soft(v, m) for v in ycc(t))
    k = spread(np.where(m, (yt + 2.0) / (yb + 2.0), 1.0), m)
    dcb = spread(np.where(m, cbt - cbb, 0.0), m)
    dcr = spread(np.where(m, crt - crb, 0.0), m)
    tcb = spread(np.where(m, cbt, 0.0), m)
    tcr = spread(np.where(m, crt, 0.0), m)
    size = (a.shape[1], a.shape[0])
    k, dcb, dcr, tcb, tcr = (up(v, size) for v in (k, dcb, dcr, tcb, tcr))
    y, cb, cr = ycc(a)
    # сдвиг цветности держит рисунок, пока цвет близок (зеркало); при перекраске голубое -> красное
    # насыщенность основы у модели своя, сдвиг оставляет голубую кайму - там цветность члена целиком
    w = np.clip((np.hypot(dcb, dcr) - 8.0) / 16.0, 0.0, 1.0)
    cb2 = (1 - w) * (cb + dcb) + w * tcb
    cr2 = (1 - w) * (cr + dcr) + w * tcr
    out = a.copy()
    out[..., :3] = np.clip(rgb(y * k, cb2, cr2), 0, 255)
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def derive(hd, ob, ot, how):
    if how == "зеркало":
        return transfer(hd.transpose(Image.FLIP_LEFT_RIGHT), ob.transpose(Image.FLIP_LEFT_RIGHT), ot)
    return transfer(hd, ob, ot)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--families", default="art/objects/families/families.json")
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="", help="места членов через запятую")
    a = ap.parse_args()
    only = {int(v) for v in a.only.split(",") if v}
    world = mm.World()
    with open(a.families, encoding=ENC) as f:
        fams = json.load(f)

    def key(k):
        s, fr = k.split(":")
        return s.upper(), int(fr)

    def src_path(k):
        s, fr = key(k)
        return os.path.join(a.src, s + ".PCK", "%d.png" % fr)

    # запись о выводе на каждый файл: из чего, какой связью, какой ревизии семейства (раздел 15)
    rpath = os.path.join(a.out, "derived.json")
    records = {}
    if os.path.exists(rpath):
        with open(rpath, encoding=ENC) as f:
            records = json.load(f)
    made = 0
    fh = ar.frame_hashes()
    ident = ar.read_identity()
    for fm in fams:
        can = fm["members"][0]
        # только прямые члены: выводятся из канонического, никогда из соседа по цепочке (Pipeline v2,
        # раздел 3); на проверке (review) - не выводятся вовсе
        for m in fm["members"][1:]:
            if m["decision"] not in ("AUTO", "HUMAN_APPROVED") or m["relation"] not in ("recolor", "mirror"):
                continue
            if only and m["rank"] not in only:
                continue
            if len(m["src"]) != len(can["src"]):
                continue
            how = "зеркало" if m["relation"] == "mirror" else "перекраска"
            for kb, kt in zip(can["src"], m["src"]):
                p = src_path(kb)
                if not os.path.exists(p):
                    continue
                sb, fb = key(kb)
                st, ft = key(kt)
                im = derive(Image.open(p), world.sprite(sb.lower(), fb, None), world.sprite(st.lower(), ft, None), how)
                # одиночный предмет: тот же файл на все копии в других наборах (R-049)
                for kk in (m["keys"] if len(m["src"]) == 1 else [kt]):
                    d = os.path.join(a.out, key(kk)[0] + ".PCK")
                    os.makedirs(d, exist_ok=True)
                    out = os.path.join(d, "%d.png" % key(kk)[1])
                    im.save(out)
                    # входы вывода по отдельности (asset_rev): канонический HD (derived_from_sha256),
                    # семейство, опознание ассета, оригиналы основы и члена, версия алгоритма
                    inp = ar.inputs(fm, ident.get(fm["family_id"]), can["src"], m["src"], fh,
                                    derive=DERIVE_VERSION)
                    records["%s.PCK/%d.png" % key(kk)] = {
                        "generator": "derive_" + m["relation"], "generator_version": DERIVE_VERSION,
                        "derived_from": "%s.PCK/%d.png" % (sb, fb),
                        "derived_from_sha256": sha256(p), "source_frame": "%s:%d" % key(kk),
                        "family": fm["family_id"], "revision": fm["revision"], "relation": m["relation"],
                        "decision": m["decision"], "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "inputs": inp, "input_hash": ar.input_hash(inp), "sha256": sha256(out)}
                made += 1
                print("#%d %s:%d <- %s %s (ревизия %d)" % (m["rank"], st, ft, how, fm["family_id"], fm["revision"]),
                      flush=True)
    os.makedirs(a.out, exist_ok=True)
    with open(rpath, "w", encoding=ENC) as f:
        json.dump(records, f, ensure_ascii=False, indent=1, sort_keys=True)
    print("выведено кадров: %d; записи - %s" % (made, rpath))


if __name__ == "__main__":
    main()
