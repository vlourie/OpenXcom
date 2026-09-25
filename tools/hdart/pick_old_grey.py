# -*- coding: utf-8 -*-
"""Кандидаты в датасет дообучения из ПРЕЖНЕГО пака (до LoRA) - там, где LoRA проваливается.

LoRA, обученная на DESERT и FORESTSWAMP, перекрашивает серое и гладкое в тёплую грязь и дерево:
серые оригиналы у неё годны на 8%, у прежнего пака на 65%. Лучших кадров батча на серое просто
нет, поэтому цели для серого, металла и гладкого берём из прежнего пака, оценённого теми же мерками
(score_batch.py --mod <резерв> --out <папка>).

Отбор: оригинал серый (sat_orig < --grey) или ровный по тону, прежний пак годен, LoRA нет,
площадь не меньше --min-area, не больше --per-set на набор, одна картинка один раз.
Пишет picked_old.tsv и листы оригинал | прежний | LoRA в sheets_old/.

  python tools/hdart/pick_old_grey.py --pick 150
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw                                     # noqa: E402

import build_dataset as bd                                            # noqa: E402
import score_batch as sb                                              # noqa: E402
import tile_forge as tf                                               # noqa: E402

ENC = "utf-8-sig"


def read(p):
    with open(p, encoding=ENC, newline="") as f:
        return {(r["набор"], r["кадр"]): r for r in csv.DictReader(f, delimiter="\t")}


def sheet(sel, old_mod, out_dir, per=40):
    os.makedirs(out_dir, exist_ok=True)
    W, H, cols = 128, 160, 4
    cw = 3 * W + 20
    paths = []
    for k in range(0, len(sel), per):
        part = sel[k:k + per]
        im = Image.new("RGB", (cols * cw + 10, ((len(part) + cols - 1) // cols) * (H + 22) + 10),
                       (26, 26, 30))
        d = ImageDraw.Draw(im)
        for n, r in enumerate(part):
            name, i = r["набор"], r["кадр"]
            sh = tf.Sheet("art/TERRAIN", name)
            x, y = 5 + (n % cols) * cw, 5 + (n // cols) * (H + 22)
            imgs = [sh.frame(int(i)).resize((W, H), Image.NEAREST)]
            for root in (old_mod, sb.MOD):
                imgs.append(Image.open(os.path.join(root, name, i + ".png")).convert("RGBA")
                            .resize((W, H), Image.LANCZOS))
            for j, t in enumerate(imgs):
                bg = Image.new("RGBA", (W, H), (38, 38, 42, 255))
                im.paste(Image.alpha_composite(bg, t).convert("RGB"), (x + j * (W + 4), y))
            d.text((x, y + H + 3), "%d %s %s %s" % (k + n + 1, name[:-4][:20], i, r["подпись_вид"][0]),
                   fill=(220, 220, 150), font=bd.font())
        p = os.path.join(out_dir, "old_%02d.png" % (k // per + 1))
        im.save(p)
        paths.append(p)
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", default="art/_review/batch_score/score.tsv")
    ap.add_argument("--old", default="art/_review/batch_score_old/score.tsv")
    ap.add_argument("--old-mod", default="art/_backup/TERRAIN_before_lora_20260924_1057", dest="old_mod")
    ap.add_argument("--out", default="art/_review/batch_score")
    ap.add_argument("--pick", type=int, default=150)
    ap.add_argument("--per-set", type=int, default=3, dest="per_set")
    ap.add_argument("--grey", type=float, default=0.08, help="порог насыщенности серого оригинала")
    ap.add_argument("--min-area", type=float, default=0.10, dest="min_area")
    ap.add_argument("--exclude", default="", help="файл 'НАБОР кадр' - брак глазами у прежнего пака")
    a = ap.parse_args()
    new, old = read(a.new), read(a.old)
    bad = set()
    if a.exclude and os.path.exists(a.exclude):
        with open(a.exclude, encoding=ENC) as f:
            for line in f:
                p = line.split()
                if len(p) >= 2 and not line.startswith("#"):
                    bad.add((p[0].upper() if p[0].upper().endswith(".PCK") else p[0].upper() + ".PCK", p[1]))
    pool = []
    for k, o in old.items():
        n = new.get(k)
        if n is None or k in bad:
            continue
        if not (float(o["sat_orig"]) < a.grey and o["годен"] == "1" and n["годен"] == "0"):
            continue
        if float(o["area"]) < a.min_area:
            continue
        pool.append(o)
    pool.sort(key=lambda r: -float(r["балл"]))
    per, seen, sel = {}, set(), []
    quota = {"floor": a.pick // 3, "wall": a.pick // 3, "object": a.pick - 2 * (a.pick // 3)}
    got = {"floor": 0, "wall": 0, "object": 0}
    for r in pool:
        kind = r["подпись_вид"]
        if got[kind] >= quota[kind] or per.get(r["набор"], 0) >= a.per_set:
            continue
        if r["hash"] and r["hash"] in seen:
            continue
        sel.append(r)
        got[kind] += 1
        per[r["набор"]] = per.get(r["набор"], 0) + 1
        if r["hash"]:
            seen.add(r["hash"])
    # недобор одного вида добираем другими
    for r in pool:
        if len(sel) >= a.pick:
            break
        if r in sel or per.get(r["набор"], 0) >= a.per_set or (r["hash"] and r["hash"] in seen):
            continue
        sel.append(r)
        per[r["набор"]] = per.get(r["набор"], 0) + 1
        if r["hash"]:
            seen.add(r["hash"])
    out = os.path.join(a.out, "picked_old.tsv")
    with open(out, "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sel[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(sel)
    kinds = {}
    for r in sel:
        kinds[r["подпись_вид"]] = kinds.get(r["подпись_вид"], 0) + 1
    print("пул: %d, отобрано %d из %d наборов, %s" % (len(pool), len(sel), len(per), kinds))
    for p in sheet(sel, a.old_mod, os.path.join(a.out, "sheets_old")):
        print("  лист:", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
