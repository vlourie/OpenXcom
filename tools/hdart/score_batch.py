#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оценка каждого кадра, нарисованного LoRA: таблица на весь батч и отбор лучших для дообучения.

Судим не по ответу модели и не по промежуточному листу, а по КЛЕТКЕ МОДА - тому, что читает
игра (R-019): <мод>\\hd\\TERRAIN\\<набор>\\<N>.png после tile_forge fit. В оценку идут только кадры
из returned\\lora - это то, что модель нарисовала сама; копии и зеркала лежат в lora_cut и
оценивать их отдельно незачем, они повторяют своих источников.

Мерки - те же, что у build_dataset.py (measure/verdict: след, фактура, крупный рисунок, тон,
край), плюс три своих:
  spill   доля непрозрачного там, где у оригинала пусто (предмет нарисован крупнее, R-050)
  miss    доля силуэта оригинала, оставшаяся пустой (предмет недорисован)
  corr    корреляция яркости с оригиналом в базовом размере, внутри силуэта: сохранён ли
          рисунок, а не выдуман новый (R-007)

    E:\\train\\.venv-train\\Scripts\\python.exe tools\\hdart\\score_batch.py
    ... score_batch.py --pick 300 --per-set 3          плюс отбор и листы для глаз

Пишет art\\_review\\batch_score\\: score.tsv (все кадры), picked.tsv (отобранные), sheets\\*.png.
"""
import argparse
import csv
import glob
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                      # noqa: E402
from PIL import Image, ImageDraw, ImageFilter           # noqa: E402

import build_dataset as bd                              # noqa: E402
import dupe_plan as dup                                 # noqa: E402
import tile_forge as tf                                 # noqa: E402

ENC = "utf-8-sig"
MOD = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd", "TERRAIN")
FIELDS = ["набор", "кадр", "вид", "подпись_вид", "прогон", "area", "iou", "det", "low_orig", "low_cell",
          "low_ratio", "tone", "rim_own", "rim_after", "sat_orig", "sat_cell", "spill", "miss", "corr", "flags",
          "годен", "балл", "hash", "hint"]


def base_lum(im, frame, panel):
    """Клетка, приведённая к размеру оригинала и положенная на подложку, как яркость."""
    small = im.convert("RGBA").resize(frame.size, Image.BOX)
    flat = Image.alpha_composite(Image.new("RGBA", frame.size, panel + (255,)), small)
    return bd.lum(np.asarray(flat.convert("RGB"), np.float64))


def score_frame(sh, i, cell, scale, args):
    frame = sh.frame(i)
    kind = bd.kind_of(sh, i, "type")
    mt = bd.measure(sh, i, cell, scale)

    mask = frame.split()[3].resize((frame.width * scale, frame.height * scale), Image.NEAREST)
    rim, inner = tf.rim_masks(mask)
    own = tf.rim_delta(frame.resize(mask.size, Image.NEAREST), rim, inner)
    after = tf.rim_delta(Image.alpha_composite(
        Image.new("RGBA", cell.size, bd.PANEL + (255,)), cell), rim, inner)
    info = {"kind": kind, "rim_own": own, "rim_after": after}
    flags = bd.verdict(mt, info, args)

    a = np.asarray(cell)[..., 3]
    keep = np.asarray(mask) > 128
    if a.shape != keep.shape:
        return None
    # полосу в 3 пикселя по краю силуэта не считаем ни туда, ни сюда: сглаженный край ромба
    # сам по себе даёт около 7 процентов площади при k=4, и мерка ловила бы его, а не брак
    core = np.asarray(mask.filter(ImageFilter.MinFilter(7))) > 128
    empty = ~(np.asarray(mask.filter(ImageFilter.MaxFilter(7))) > 128)
    spill = float((a[empty] > 64).mean()) if empty.any() else 0.0
    miss = float((a[core] < 64).mean()) if core.any() else 0.0

    m = np.asarray(frame)[..., 3] > 250
    # рисунок сравниваем на ПОЛОВИНЕ базового размера: в базовом у оригинала сидит дизеринг
    # (шахматка пикселей), и гладкий HD-пол с ним не коррелирует по определению
    half = (max(2, frame.width // 2), max(2, frame.height // 2))
    mh = np.asarray(frame.resize(half, Image.BOX))[..., 3] > 250
    corr = 0.0
    if mh.sum() >= 8:
        o = bd.lum(np.asarray(frame.convert("RGB").resize(half, Image.BOX), np.float64))[mh]
        c = base_lum(cell, frame, bd.PANEL)
        c = np.asarray(Image.fromarray(np.clip(c, 0, 255).astype(np.uint8)).resize(half, Image.BOX),
                       np.float64)[mh]
        if o.std() > 1.0 and c.std() > 1.0:
            corr = float(np.corrcoef(o, c)[0, 1])
        else:
            corr = 1.0 if abs(o.mean() - c.mean()) < 20 else 0.0   # ровный кадр: судим по тону

    # насыщенность: серый металл, перекрашенный в дерево или песчаник, проходит и по тону,
    # и по рисунку (яркость та же), а по насыщенности виден сразу. Это главный перекос LoRA,
    # выученной на двух наборах - пустыне и болоте
    sat_o = sat_c = 0.0
    if m.sum() >= 8:
        so = np.asarray(frame.convert("RGB").convert("HSV"), np.float64)[..., 1][m] / 255.0
        small = cell.convert("RGBA").resize(frame.size, Image.BOX)
        flat = Image.alpha_composite(Image.new("RGBA", frame.size, bd.PANEL + (255,)), small)
        sc = np.asarray(flat.convert("RGB").convert("HSV"), np.float64)[..., 1][m] / 255.0
        sat_o, sat_c = float(so.mean()), float(sc.mean())
    if sat_c - sat_o > args.max_sat:
        flags.append("цвет стал насыщеннее +%.2f" % (sat_c - sat_o))

    if spill > args.max_spill:
        flags.append("вылез за силуэт %.0f%%" % (100 * spill))
    if miss > args.max_miss:
        flags.append("недорисован %.0f%%" % (100 * miss))
    if corr < args.min_corr:
        flags.append("рисунок не сохранён r=%.2f" % corr)
    if not (args.det_lo <= mt["det"] <= args.det_hi):
        flags.append("фактура x%.2f" % mt["det"])

    # балл - чем ближе к оригиналу по рисунку и тону, тем лучше; фактура чуть выше
    # оригинала поощряется (ради неё и рисуем), но не больше полутора (R-039)
    det_pen = abs(min(mt["det"], 2.0) - 1.25)
    score = (corr - 0.004 * mt["tone"] - 0.5 * det_pen - 2.0 * spill - 2.0 * miss
             + 0.3 * min(mt["iou"], 1.0))
    return {"вид": kind, "подпись_вид": bd.prompt_kind(sh, i),
            "area": float(keep.mean()), "iou": mt["iou"],
            "det": mt["det"], "low_orig": mt["low_orig"], "low_cell": mt["low_cell"],
            "low_ratio": mt["low_ratio"], "tone": mt["tone"], "rim_own": own,
            "rim_after": after, "sat_orig": sat_o, "sat_cell": sat_c, "spill": spill, "miss": miss, "corr": corr,
            "flags": "; ".join(flags), "годен": 0 if flags else 1, "балл": score}


def fmt(v):
    return "%.3f" % v if isinstance(v, float) else str(v)


def pick(rows, n, per_set, per_hash_seen, min_area=0.08):
    """Лучшие по баллу, с разнообразием: не больше per_set из набора, одна картинка - один раз,
    и доли полов, стен и предметов примерно поровну, насколько хватает годных. Кадры, где
    рисунка почти нет (черта, тонкий столбик), модель ничему не учат - их не берём."""
    good = sorted((r for r in rows if r["годен"] == 1 and r["area"] >= min_area),
                  key=lambda r: -r["балл"])
    by_kind = defaultdict(list)
    for r in good:
        by_kind[r["подпись_вид"]].append(r)
    quota = {k: n // max(1, len(by_kind)) for k in by_kind}
    out, per, seen = [], Counter(), set(per_hash_seen)

    flat_cap = max(1, int(0.15 * n))                 # ровные нужны (учат не выдумывать, R-017),
    flat = [0]                                       # но в массе учат только заливке

    def take(r):
        if per[r["набор"]] >= per_set or r["hash"] in seen:
            return False
        if r["low_orig"] < 2.0:
            if flat[0] >= flat_cap:
                return False
            flat[0] += 1
        out.append(r)
        per[r["набор"]] += 1
        seen.add(r["hash"])
        return True

    for k, lst in by_kind.items():
        got = 0
        for r in lst:
            if got >= quota[k]:
                break
            got += take(r)
    for r in good:                                   # добор, если какого-то вида не хватило
        if len(out) >= n:
            break
        if r not in out:
            take(r)
    return out


def sheets(picked, sheets_dir, mod, out_dir, per=40):
    os.makedirs(out_dir, exist_ok=True)
    W, H = 128, 160
    cols = 5
    cache = {}
    paths = []
    for k in range(0, len(picked), per):
        part = picked[k:k + per]
        rows_n = (len(part) + cols - 1) // cols
        cw = 2 * W + 16
        im = Image.new("RGB", (cols * cw + 10, rows_n * (H + 22) + 10), (26, 26, 30))
        d = ImageDraw.Draw(im)
        for n, r in enumerate(part):
            sh = cache.get(r["набор"]) or tf.Sheet(sheets_dir, r["набор"])
            cache[r["набор"]] = sh
            x, y = 5 + (n % cols) * cw, 5 + (n // cols) * (H + 22)
            o = sh.frame(r["кадр"]).resize((W, H), Image.NEAREST)
            c = Image.open(os.path.join(mod, r["набор"], "%d.png" % r["кадр"])).convert("RGBA")
            c = c.resize((W, H), Image.LANCZOS)
            for j, t in enumerate((o, c)):
                bg = Image.new("RGBA", (W, H), (38, 38, 42, 255))
                im.paste(Image.alpha_composite(bg, t).convert("RGB"), (x + j * (W + 4), y))
            d.text((x, y + H + 3), "%d %s %d %s" % (k + n + 1, r["набор"][:-4][:16], r["кадр"],
                                                   r["подпись_вид"][0]),
                   fill=(220, 220, 150), font=bd.font())
        p = os.path.join(out_dir, "picked_%02d.png" % (k // per + 1))
        im.save(p)
        paths.append(p)
    return paths


def export(picked_tsv, sheets_dir, mod, out, trigger, base=""):
    """Пары для тренера DiffSynth из отобранного: control - вход ровно как в gen_lora_batch
    (make_control, zoom 24, подложка), image - клетка мода на той же подложке, подпись - тот же
    CAPTION. Пары прошлого датасета (base) дописываются в начало манифеста как есть: без них
    модель забудет то, на чём училась (пустыня и болото)."""
    img_dir, ctl_dir = os.path.join(out, "images"), os.path.join(out, "control")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(ctl_dir, exist_ok=True)
    meta = []
    if base:
        with open(os.path.join(base, "metadata.csv"), encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                for k in ("image", "edit_image"):
                    src = os.path.join(base, r[k])
                    dst = os.path.join(out, r[k])
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    Image.open(src).save(dst)
                meta.append((r["image"], r["edit_image"], r["prompt"]))
    n_base = len(meta)
    with open(picked_tsv, encoding=ENC, newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    cache = {}
    for r in rows:
        name, i = r["набор"], int(r["кадр"])
        sh = cache.get(name) or tf.Sheet(sheets_dir, name)
        cache[name] = sh
        control = bd.make_control(sh, i, glt_zoom(), bd.PANEL)
        cell = Image.open(os.path.join(mod, name, "%d.png" % i)).convert("RGBA")
        target = bd.on_panel(cell, control.size, bd.PANEL)
        slug = "%s_%03d" % (bd.slug(name), i)
        if any(m[0] == "images/%s.png" % slug for m in meta[:n_base]):
            continue                                   # пара уже есть в прошлом датасете
        control.save(os.path.join(ctl_dir, slug + ".png"))
        target.save(os.path.join(img_dir, slug + ".png"))
        cap = CAPTION.format(trigger=trigger, kind=bd.prompt_kind(sh, i),
                             hint=sh.hints.get(i) or "terrain tile")
        meta.append(("images/%s.png" % slug, "control/%s.png" % slug, cap))
    # манифест читает тренер, а не PowerShell: без спецификации (исключение R-001)
    with open(os.path.join(out, "metadata.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image", "edit_image", "prompt"])
        w.writerows(meta)
    print("датасет: %s - пар %d (прошлых %d, новых %d)" % (out, len(meta), n_base, len(meta) - n_base))


CAPTION = "{trigger}X-COM isometric {kind} tile, {hint}"     # = gen_lora_test.CAPTION


def glt_zoom():
    return 24                                                  # = gen_lora_test.ZOOM


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="", help="собрать пары для тренера из picked.tsv в эту папку")
    ap.add_argument("--base", default="", help="прошлый датасет, его пары взять в новый как есть")
    ap.add_argument("--trigger", default="oxcehd, ")
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--mod", default=MOD)
    ap.add_argument("--out", default=os.path.join("art", "_review", "batch_score"))
    ap.add_argument("--since", default="2026-09-23 14:05",
                    help="кадры новее этого - прогон 'batch2', старше - 'ранее'")
    ap.add_argument("--max-spill", type=float, default=0.03, dest="max_spill")
    ap.add_argument("--max-miss", type=float, default=0.05, dest="max_miss")
    ap.add_argument("--min-corr", type=float, default=0.70, dest="min_corr")
    ap.add_argument("--max-sat", type=float, default=0.10, dest="max_sat",
                    help="на сколько кадр может стать насыщеннее оригинала (серое -> дерево)")
    # нижнего предела у фактуры нет: гладкий HD-кадр против дизеринга оригинала всегда ниже
    # единицы, а настоящее замыливание крупного рисунка ловит low_ratio из build_dataset
    ap.add_argument("--det-lo", type=float, default=0.0, dest="det_lo")
    ap.add_argument("--det-hi", type=float, default=1.60, dest="det_hi")
    ap.add_argument("--pick", type=int, default=0, help="сколько отобрать для дообучения")
    ap.add_argument("--per-set", type=int, default=3, dest="per_set")
    ap.add_argument("--min-area", type=float, default=0.08, dest="min_area",
                    help="доля кадра под рисунком, ниже - в отбор не берём")
    ap.add_argument("--exclude", default="", help="файл 'НАБОР кадр' - уже отбракованные глазами")
    args, _ = ap.parse_known_args()
    if args.export:
        export(os.path.join(args.out, "picked.tsv"), args.sheets, args.mod, args.export,
               args.trigger, args.base)
        return 0
    # пороги build_dataset.verdict - его же умолчания, чтобы отбор совпадал с прошлым датасетом
    bdargs = bd.build_parser().parse_args([])
    for k in ("max_spill", "max_miss", "min_corr", "det_lo", "det_hi", "max_sat"):
        setattr(bdargs, k, getattr(args, k))

    os.makedirs(args.out, exist_ok=True)
    since = time.mktime(time.strptime(args.since, "%Y-%m-%d %H:%M"))
    by_frame, _ = dup.load(args.sheets)
    exclude = set()
    if args.exclude and os.path.exists(args.exclude):
        with open(args.exclude, encoding=ENC) as f:
            for line in f:
                p = line.split()
                if len(p) >= 2 and not line.startswith("#"):
                    # "НАБОР *" - весь набор: модель портит его целиком (гладкое стало деревом)
                    exclude.add((p[0].upper() if p[0].upper().endswith(".PCK")
                                 else p[0].upper() + ".PCK", "*" if p[1] == "*" else int(p[1])))

    rows, t0 = [], time.time()
    dirs = sorted(glob.glob(os.path.join(args.sheets, "*.PCK", "returned", "lora")))
    for n, d in enumerate(dirs, 1):
        name = os.path.basename(os.path.dirname(os.path.dirname(d)))
        try:
            sh = tf.Sheet(args.sheets, name)
        except Exception:                               # noqa: BLE001
            continue
        for p in glob.glob(os.path.join(d, "*.png")):
            b = os.path.basename(p)[:-4]
            if not b.isdigit():
                continue
            i = int(b)
            cp = os.path.join(args.mod, name, "%d.png" % i)
            if i >= sh.lay["count"] or not os.path.exists(cp):
                continue
            cell = Image.open(cp).convert("RGBA")
            r = score_frame(sh, i, cell, sh.scale, bdargs)
            if r is None:
                continue
            r.update({"набор": name, "кадр": i,
                      "прогон": "batch2" if os.path.getmtime(p) >= since else "ранее",
                      "hash": by_frame.get((name[:-4], i), ""),
                      "hint": sh.hints.get(i, "")})
            if (name, i) in exclude or (name, "*") in exclude:
                r["годен"] = 0
                r["flags"] = (r["flags"] + "; " if r["flags"] else "") + "брак глазами"
            rows.append(r)
        if n % 50 == 0:
            print("  %d/%d наборов, кадров %d, %.0f с" % (n, len(dirs), len(rows), time.time() - t0),
                  flush=True)

    # брак глазами переходит на все копии той же картинки в других наборах (R-049):
    # модель рисовала их одним заказом, значит и ответ у них один
    bad = {r["hash"] for r in rows if r["hash"] and "брак глазами" in r["flags"]}
    for r in rows:
        if r["hash"] in bad and "брак глазами" not in r["flags"]:
            r["годен"] = 0
            r["flags"] = (r["flags"] + "; " if r["flags"] else "") + "брак глазами"

    with open(os.path.join(args.out, "score.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(FIELDS)
        for r in sorted(rows, key=lambda r: (r["набор"], r["кадр"])):
            w.writerow([fmt(r[k]) for k in FIELDS])

    good = [r for r in rows if r["годен"]]
    print("кадров оценено: %d (batch2 %d), годных: %d (%.1f%%)"
          % (len(rows), sum(r["прогон"] == "batch2" for r in rows), len(good),
             100.0 * len(good) / max(1, len(rows))))
    reasons = Counter()
    for r in rows:
        for fl in filter(None, r["flags"].split("; ")):
            reasons[" ".join(w for w in fl.split(" ")[:3] if not any(ch.isdigit() for ch in w))] += 1
    for k, v in reasons.most_common(12):
        print("   %-28s %d" % (k, v))

    if args.pick:
        picked = pick(rows, args.pick, args.per_set, (), args.min_area)
        with open(os.path.join(args.out, "picked.tsv"), "w", encoding=ENC, newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["№"] + FIELDS)
            for k, r in enumerate(picked, 1):
                w.writerow([k] + [fmt(r[x]) for x in FIELDS])
        c = Counter(r["подпись_вид"] for r in picked)
        print("отобрано: %d из %d наборов; %s" % (len(picked), len({r["набор"] for r in picked}),
                                                  ", ".join("%s %d" % kv for kv in c.items())))
        for p in sheets(picked, args.sheets, args.mod, os.path.join(args.out, "sheets")):
            print("  лист:", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
