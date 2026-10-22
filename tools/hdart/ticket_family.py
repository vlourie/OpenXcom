#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Вся семья кадра перед правкой по тикету: копии, зеркала и перекраски во ВСЕХ наборах, с их HD.

22.10 Vitali: «мы же вчера эти 2 красных компа делали - а ты не исправляешь в 1 месте, не исправляя во всех
остальных паках?» Тикет 167 поставил новый URBAN_WASTE 109, а его зеркало 108 осталось старым, хотя
art/objects/families/families.tsv знала пару (108 mirror AUTO). Таблица семей к тому же неполная: рельсы
PORTROADS 28-33 живут перекрасками ещё в восьми наборах (CULTAREA, MILURBAN, MILWARE, MILWAREGHOUL, WHITEBITS,
XBITSUFO, LINERSHIPC, XB3BITZ2), а в families.tsv их нет. Поэтому здесь три источника сразу:

  families.tsv              - решения семейств (AUTO, HUMAN_APPROVED, REVIEW_REQUIRED);
  census/frame_hash.tsv     - побайтные копии классики (R-296);
  перебор всех наборов      - силуэт (IoU масок, как есть и зеркалом) >= --iou и рисунок яркости внутри
                              силуэта (корреляция) >= --corr: перекраска и зеркало с другим числом оттенков.

Для каждого члена: связь, числа, генератор и одобрение в манифесте, есть ли файл в копии игры и в репо.
Правило (грабли R-457): HD по тикету ставится сразу на всю семью - копия, зеркало (ImageOps.mirror),
перекраска переносом цвета классики; член с одобренным своим HD - только по слову Vitali.

    py -3.13 tools/hdart/ticket_family.py URBAN_WASTE:109 PORTROADS:28 [--iou 0.97 --corr 0.85] [--tsv out.tsv]
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(ROOT)
import glass_alpha as ga       # noqa: E402
import build_hd_pack as bp     # noqa: E402


def key(s):
    a, b = s.rsplit(":", 1)
    return a, int(b)


def gray(rgb):
    return rgb @ np.array([0.299, 0.587, 0.114], np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", nargs="+")
    ap.add_argument("--iou", type=float, default=0.97)
    ap.add_argument("--corr", type=float, default=0.85)
    ap.add_argument("--tsv", default="")
    o = ap.parse_args()
    want = [key(a) for a in o.frames]
    man = bp.load()

    found = {w: {} for w in want}       # член -> (связь, числа)

    def add(w, m, rel, info):
        if m != w and m not in found[w]:
            found[w][m] = (rel, info)

    # 1. семейства
    fam = ROOT / "art" / "objects" / "families" / "families.tsv"
    if fam.exists():
        rows = [r.split("\t") for r in fam.read_text(encoding="utf-8-sig").splitlines()[1:]]
        by_fam = {}
        for r in rows:
            by_fam.setdefault(r[0], []).append(r)
        for w in want:
            ws = "%s:%d" % w
            for fid, rs in by_fam.items():
                keys = [k for r in rs for k in r[5].split()]
                if ws in keys or ws == fid:
                    for r in rs:
                        for k in r[5].split():
                            add(w, key(k), "families:" + r[6], r[7])
    # 2. побайтные копии
    by_h, of = {}, {}
    for line in (ROOT / "census" / "frame_hash.tsv").read_text(encoding="utf-8-sig").splitlines()[1:]:
        s, f, h = line.split("\t")[:3]
        by_h.setdefault(h, []).append((s, int(f)))
        of[(s, int(f))] = h
    for w in want:
        for m in by_h.get(of.get(w), []):
            add(w, m, "copy", "побайтно")
    # 3. перебор всех наборов
    ref = {}
    for s, f in want:
        S = ga.SetSheet(s)
        fr = S.frame(f)
        ref[(s, f)] = (S.opaque(fr), gray(S.pal[fr].astype(np.float32)), S.pal[fr].astype(np.float32))
    for d in sorted(os.listdir(ga.SHEETS)):
        if not d.endswith(".PCK") or not os.path.exists(os.path.join(ga.SHEETS, d, "original.png")):
            continue
        try:
            S = ga.SetSheet(d[:-4])
        except SystemExit:
            continue
        if S.frame(0).shape != (40, 32):
            continue
        for f in range(S.count):
            fr = S.frame(f)
            op = S.opaque(fr)
            if op.sum() < 40:
                continue
            g = gray(S.pal[fr].astype(np.float32))
            c = S.pal[fr].astype(np.float32)
            for w, (m0, g0, c0) in ref.items():
                for flip in (False, True):
                    m = m0[:, ::-1] if flip else m0
                    uni = (op | m).sum()
                    iou = (op & m).sum() / uni if uni else 0
                    if iou < o.iou:
                        continue
                    both = op & m
                    a = g[both]
                    b = (g0[:, ::-1] if flip else g0)[both]
                    corr = float(np.corrcoef(a, b)[0, 1]) if a.std() > 1 and b.std() > 1 else 0.0
                    same = float((np.abs(c - (c0[:, ::-1] if flip else c0)).sum(-1)[both] < 8).mean())
                    if same > 0.98 and not flip:
                        rel = "copy"
                    elif same > 0.98:
                        rel = "mirror"
                    elif corr >= o.corr:
                        rel = "mirror+recolor" if flip else "recolor"
                    else:
                        continue
                    add(w, (d[:-4], f), rel, "IoU %.2f рисунок %.2f цвет %.2f" % (iou, corr, same))
    out = ["кадр\tчлен\tсвязь\tчисла\tгенератор\tодобрен\tигра\tрепо"]
    for w in want:
        print("== %s:%d - членов %d" % (w[0], w[1], len(found[w])))
        for m, (rel, info) in sorted(found[w].items()):
            rp = "TERRAIN/%s.PCK/%d.png" % m
            e = man["files"].get(rp, {})
            g = os.path.exists(os.path.join(bp.TARGETS["game"], rp))
            r = os.path.exists(os.path.join(bp.TARGETS["repo"], rp))
            line = "%s:%d\t%s:%d\t%s\t%s\t%s\t%s\t%s\t%s" % (w[0], w[1], m[0], m[1], rel, info, e.get("generator", "-"),
                                                       "да" if e.get("approved") else "", "да" if g else "НЕТ", "да" if r else "НЕТ")
            out.append(line)
            print("  " + line.split("\t", 1)[1].replace("\t", " | "))
    if o.tsv:
        Path(o.tsv).write_text("\n".join(out) + "\n", encoding="utf-8-sig")


if __name__ == "__main__":
    main()
