"""Подготовка перерисовки предметов инвентаря: оружие, боеприпасы, медицина (15.10).

Только читает перепись census/items/ и пишет таблицы и листы оригиналов в census/items/redo/.
Модель не грузит, в мод ничего не кладёт.

  inv_redo_prep.py [--out census/items/redo] [--per-page 30]

Выход:
  weapons.tsv     ствол или холодное: кадр, клетки, выход за клетки, кадры руки и пола, боеприпасы с их кадрами
  ammo.tsv        боеприпас: кадр, клетки, стволы, семейство силуэта (mask_md5) и его основа
  ammo_families.tsv  семейства боеприпасов с общим силуэтом: основа, члены, перекраска ли (recolor_of)
  meds.tsv        медицина (battleType medikit): кадр, клетки, имя
  grenades.tsv    гранаты и мины: то же
  summary.json    числа по классам: предметов, кадров, разных силуэтов, выход за клетки
  sheet_weapons_NN.png  ствол слева, его боеприпасы справа, классика x3 на тёмном фоне, подпись тип и имя
  sheet_melee_NN.png, sheet_meds_NN.png, sheet_grenades_NN.png, sheet_ammo_orphan_NN.png
"""
import argparse
import collections
import csv
import json
import os
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ITEMS = "census/items/items.tsv"
CP = "census/items/cp_status.tsv"
FRAMES = "census/items/bigobs_frames.tsv"
ATLAS = "census/items/export/exp_piratez/BIGOBS.PCK.png"
FW, FH, COLS = 32, 48, 16
SCALE = 3
BG = (24, 26, 30, 255)
CLASSES = ("firearm", "melee", "ammo", "medical", "grenade")


def read_tsv(path):
    with open(os.path.join(ROOT, path), encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def write_tsv(path, header, rows):
    with open(path, "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def names(field):
    """Список типов из поля переписи вида [\\"A\\", \\"B\\"]."""
    return re.findall(r"[A-Za-z0-9_]+", field.replace('\\"', " "))


class Atlas:
    """Выгрузка движка индексами и палитрой; индекс 0 прозрачен, как в игре (R-043)."""

    def __init__(self):
        im = Image.open(os.path.join(ROOT, ATLAS))
        assert im.mode == "P", im.mode
        self.idx = np.asarray(im)
        self.pal = np.array(im.getpalette()[:768], dtype=np.uint8).reshape(-1, 3)
        h, w = self.idx.shape
        self.n = (w // FW) * (h // FH)

    def frame(self, n):
        n = int(n)
        if n < 0 or n >= self.n:
            return None
        x, y = (n % COLS) * FW, (n // COLS) * FH
        i = self.idx[y:y + FH, x:x + FW]
        rgba = np.zeros((FH, FW, 4), np.uint8)
        rgba[..., :3] = self.pal[i]
        rgba[..., 3] = np.where(i == 0, 0, 255)
        return Image.fromarray(rgba, "RGBA")


def font(size):
    for p in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def tile(atlas, frame, cells):
    """Кадр x3 с сеткой своих клеток (16x16 пикселей базы на клетку)."""
    im = atlas.frame(frame)
    w, h = FW * SCALE, FH * SCALE
    out = Image.new("RGBA", (w, h), BG)
    d = ImageDraw.Draw(out)
    cw, ch = cells
    for i in range(cw):
        for j in range(ch):
            x0, y0 = i * 16 * SCALE, j * 16 * SCALE
            d.rectangle((x0, y0, x0 + 16 * SCALE - 1, y0 + 16 * SCALE - 1), outline=(70, 74, 82, 255))
    if im is not None:
        out.alpha_composite(im.resize((w, h), Image.NEAREST))
    return out


def cells_of(r):
    try:
        return int(r["invWidth"] or 1), int(r["invHeight"] or 1)
    except ValueError:
        return 1, 1


def sheet(path, rows, atlas, ftitle, fsmall, title):
    """rows: [(главный ряд: (кадр, клетки, подпись), [(кадр, клетки, подпись), ...]), ...]"""
    tw, th = FW * SCALE, FH * SCALE
    maxk = max((len(r[1]) for r in rows), default=0)
    side = min(maxk, 8)
    lw = 230
    W = 12 + tw + lw + (12 + side * (tw + 6) if side else 0) + 12
    rowh = th + 12
    H = 40 + len(rows) * rowh + 8
    out = Image.new("RGBA", (W, H), (14, 15, 18, 255))
    d = ImageDraw.Draw(out)
    d.text((12, 10), title, font=ftitle, fill=(230, 230, 230, 255))
    y = 40
    for (fr, cl, lab), kids in rows:
        out.alpha_composite(tile(atlas, fr, cl), (12, y))
        tx = 12 + tw + 8
        for k, line in enumerate(lab.split("\n")[:7]):
            d.text((tx, y + 2 + k * 18), line[:34], font=fsmall, fill=(220, 220, 200, 255) if k == 0 else (160, 165, 175, 255))
        x = 12 + tw + lw + 12
        for kfr, kcl, klab in kids[:side]:
            out.alpha_composite(tile(atlas, kfr, kcl), (x, y))
            d.text((x + 2, y + th - 16), klab[:14], font=fsmall, fill=(150, 200, 255, 255))
            x += tw + 6
        if len(kids) > side:
            d.text((x - tw + 4, y + 4), f"+{len(kids) - side}", font=ftitle, fill=(255, 180, 90, 255))
        y += rowh
    out.convert("RGB").save(path)


def pages(rows, n):
    return [rows[i:i + n] for i in range(0, len(rows), n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="census/items/redo")
    ap.add_argument("--per-page", type=int, default=30)
    a = ap.parse_args()
    out = os.path.join(ROOT, a.out)
    os.makedirs(out, exist_ok=True)

    items = read_tsv(ITEMS)
    by_type = {r["type"]: r for r in items}
    cp = {r["type"]: r for r in read_tsv(CP)}
    frames = {r["frame"]: r for r in read_tsv(FRAMES)}
    scope = [r for r in items if r["hd_scope"] == "True" and r["class"] in CLASSES]

    def name_ru(t):
        return (cp.get(t) or {}).get("name_ru", "")

    def status(t):
        return (cp.get(t) or {}).get("status", "")

    # боеприпас -> стволы (по compatibleAmmo стволов, а не по полю ammo_for: оно и есть обратная ссылка)
    guns_of = collections.defaultdict(list)
    for r in scope:
        if r["class"] in ("firearm", "melee"):
            for am in names(r["compatibleAmmo"]):
                guns_of[am].append(r["type"])

    # семейства силуэта боеприпасов
    ammo = [r for r in scope if r["class"] == "ammo"]
    fam = collections.defaultdict(list)
    for r in ammo:
        fam[r["mask_md5"]].append(r)
    fam_id = {}
    fam_rows = []
    for k, (m, rr) in enumerate(sorted(fam.items(), key=lambda kv: (-len(kv[1]), kv[0]))):
        rr.sort(key=lambda r: int(r["bigSprite"]))
        base = rr[0]
        fid = f"AF-{k + 1:03d}"
        recol = sum(1 for r in rr if (frames.get(r["bigSprite"]) or {}).get("recolor_of"))
        for r in rr:
            fam_id[r["type"]] = (fid, base["type"])
        fam_rows.append([fid, len(rr), base["type"], base["bigSprite"], f'{base["invWidth"]}x{base["invHeight"]}',
                         recol, ",".join(r["type"] for r in rr), ",".join(r["bigSprite"] for r in rr)])
    write_tsv(os.path.join(out, "ammo_families.tsv"),
              ["family", "n", "base_type", "base_frame", "cells", "marked_recolor", "types", "frames"], fam_rows)

    write_tsv(os.path.join(out, "ammo.tsv"),
              ["type", "name_ru", "status", "frame", "cells", "over_px", "family", "family_base", "guns", "costBuy"],
              [[r["type"], name_ru(r["type"]), status(r["type"]), r["bigSprite"], f'{r["invWidth"]}x{r["invHeight"]}',
                r["over_px"], *fam_id[r["type"]], ",".join(guns_of.get(r["type"], [])), r["costBuy"]]
               for r in sorted(ammo, key=lambda r: int(r["bigSprite"]))])

    def amm_list(r):
        return [t for t in names(r["compatibleAmmo"]) if t in by_type]

    wrows = []
    for r in sorted((r for r in scope if r["class"] in ("firearm", "melee")), key=lambda r: (r["class"], int(r["bigSprite"]))):
        al = amm_list(r)
        wrows.append([r["type"], r["class"], name_ru(r["type"]), status(r["type"]), r["bigSprite"],
                      f'{r["invWidth"]}x{r["invHeight"]}', r["over_px"], r["twoHanded"], r["handSprite"], r["hand_frames"],
                      r["floorSprite"], len(al), ",".join(al), ",".join(by_type[t]["bigSprite"] for t in al),
                      ",".join(sorted({fam_id[t][0] for t in al if t in fam_id})), r["costBuy"]])
    write_tsv(os.path.join(out, "weapons.tsv"),
              ["type", "class", "name_ru", "status", "frame", "cells", "over_px", "twoHanded", "handSprite", "hand_frames",
               "floorSprite", "n_ammo", "ammo", "ammo_frames", "ammo_families", "costBuy"], wrows)

    for cl, fn in (("medical", "meds.tsv"), ("grenade", "grenades.tsv")):
        rr = sorted((r for r in scope if r["class"] == cl), key=lambda r: int(r["bigSprite"]))
        write_tsv(os.path.join(out, fn), ["type", "name_ru", "status", "bt_name", "frame", "cells", "over_px",
                                         "handSprite", "floorSprite", "costBuy"],
                  [[r["type"], name_ru(r["type"]), status(r["type"]), r["bt_name"], r["bigSprite"],
                    f'{r["invWidth"]}x{r["invHeight"]}', r["over_px"], r["handSprite"], r["floorSprite"], r["costBuy"]]
                   for r in rr])

    summ = {}
    for cl in CLASSES:
        rr = [r for r in scope if r["class"] == cl]
        summ[cl] = {
            "items": len(rr),
            "frames": len({r["bigSprite"] for r in rr}),
            "silhouettes": len({r["mask_md5"] for r in rr}),
            "overflow": sum(1 for r in rr if r["over_px"] not in ("", "0")),
            "cells": dict(collections.Counter(f'{r["invWidth"]}x{r["invHeight"]}' for r in rr).most_common()),
        }
    summ["ammo_families"] = len(fam_rows)
    summ["ammo_families_multi"] = sum(1 for f in fam_rows if f[1] > 1)
    summ["firearm_no_ammo"] = sum(1 for w in wrows if w[1] == "firearm" and w[11] == 0)
    summ["ammo_orphan"] = sum(1 for r in ammo if not guns_of.get(r["type"]))
    with open(os.path.join(out, "summary.json"), "w", encoding=ENC) as f:
        json.dump(summ, f, ensure_ascii=False, indent=1)

    # листы
    atlas = Atlas()
    ft, fs = font(20), font(14)

    def lab(r, extra=""):
        t = r["type"]
        s = f'{t}\n{name_ru(t)}\nкадр {r["bigSprite"]}  {r["invWidth"]}x{r["invHeight"]}'
        if r["over_px"] not in ("", "0"):
            s += f'\nза клетки {r["over_px"]} пикс'
        if extra:
            s += "\n" + extra
        return s

    def kid(t):
        r = by_type[t]
        return (r["bigSprite"], cells_of(r), fam_id.get(t, ("", ""))[0] or t)

    for cl, stem in (("firearm", "weapons"), ("melee", "melee")):
        rr = [by_type[w[0]] for w in wrows if w[1] == cl]
        rows = [((r["bigSprite"], cells_of(r), lab(r, f'патронов {len(amm_list(r))}' if cl == "firearm" else "")),
                 [kid(t) for t in amm_list(r)]) for r in rr]
        for i, pg in enumerate(pages(rows, a.per_page)):
            sheet(os.path.join(out, f"sheet_{stem}_{i + 1:02d}.png"), pg, atlas, ft, fs,
                  f"{stem}: стр. {i + 1}, слева ствол, справа его боеприпасы (AF - семейство силуэта)")
    for cl, stem in (("medical", "meds"), ("grenade", "grenades")):
        rr = sorted((r for r in scope if r["class"] == cl), key=lambda r: int(r["bigSprite"]))
        rows = [((r["bigSprite"], cells_of(r), lab(r, r["bt_name"])), []) for r in rr]
        for i, pg in enumerate(pages(rows, a.per_page)):
            sheet(os.path.join(out, f"sheet_{stem}_{i + 1:02d}.png"), pg, atlas, ft, fs, f"{stem}: стр. {i + 1}")
    # семейства боеприпасов: основа слева, члены справа
    rows = []
    for f in fam_rows:
        if f[1] < 2:
            continue
        base = by_type[f[2]]
        rows.append(((base["bigSprite"], cells_of(base), lab(base, f"{f[0]}: {f[1]} кадров, общий силуэт")),
                     [(by_type[t]["bigSprite"], cells_of(by_type[t]), t.replace("STR_", "")) for t in f[6].split(",")[1:]]))
    for i, pg in enumerate(pages(rows, a.per_page)):
        sheet(os.path.join(out, f"sheet_ammo_families_{i + 1:02d}.png"), pg, atlas, ft, fs,
              f"боеприпасы, семейства одного силуэта: стр. {i + 1} (слева основа)")
    print(json.dumps(summ, ensure_ascii=False))


if __name__ == "__main__":
    main()
