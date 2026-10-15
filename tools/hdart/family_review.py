#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Листы проверки семейств Pipeline v2 (docs/HD_PIPELINE_V2.md, раздел 6): человек отвечает только
«это один объект?», красоту здесь не судят.

Строка листа - семейство вокруг канонического кадра: CANONICAL (жёлтая рамка) | AUTO MEMBERS
(зелёная; HUMAN_APPROVED - голубая) | REVIEW REQUIRED (красная). Под кадром: набор:кадр, связь,
direct/indirect, числа против канонического (IoU силуэта, рисунок яркости, края). Оригиналы x3 на
тёмном полу боя; составной - кусками подряд в своём порядке. Номер строки листа слева - по нему
ответ Vitali переносится в art/objects/families/decisions.tsv.

Листы (--what):
  chain - indirect_chain_review: семейства, где кто-то попал в компоненту только цепочкой;
  weak  - слабые зеркала (свет на своей стороне);
  view  - кандидаты «другой бок»;
  batch - все семейства, задевающие партию --batch.

    py -3.13 tools/hdart/family_review.py --what chain --out art/_review/families_v2
    py -3.13 tools/hdart/family_review.py --what batch --batch 1 --out art/_review/families_v2
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image, ImageDraw, ImageFont       # noqa: E402

import map_mockup as mm                           # noqa: E402

ENC = "utf-8-sig"
S = 3
TILE_W = 156
PER_LINE = 12
PAGE_H = 3200
FLOOR = (24, 22, 20)
BG = (40, 40, 44)
COL = {"canonical": (240, 200, 60), "AUTO": (90, 200, 90), "HUMAN_APPROVED": (90, 170, 240),
       "REVIEW_REQUIRED": (230, 70, 60)}
RU_REASON = {"indirect_chain": "цепочкой", "weak_mirror": "слабое зеркало",
             "alternate_view_candidate": "другой бок?"}


def font(n):
    for p in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, n)
    return ImageFont.load_default()


F13, F16 = font(13), font(16)


def pieces(world, keys):
    ims = []
    for k in keys:
        s, f = k.split(":")
        im = world.sprite(s.lower(), int(f), None)
        if im is None:
            im = Image.new("RGBA", (32, 40), (255, 0, 255, 255))
        bg = Image.new("RGBA", im.size, FLOOR + (255,))
        bg.alpha_composite(im.convert("RGBA"))
        ims.append(bg.resize((im.width * S, im.height * S), Image.NEAREST).convert("RGB"))
    out = Image.new("RGB", (sum(i.width for i in ims) + 2 * (len(ims) - 1), max(i.height for i in ims)), BG)
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + 2
    return out


def caption(m, part):
    e = m.get("evidence", {})
    if m["relation"] == "canonical":
        rel = "CANONICAL"
    elif part == "review":
        rel = "%s · indirect" % RU_REASON.get(m.get("reason", ""), m.get("reason", ""))
    else:
        rel = "%s · direct%s" % (m["relation"], " · человек" if m["decision"] == "HUMAN_APPROVED" else "")
    if "iou" in e:
        nums = "IoU %.2f r %.2f e %.2f" % (e["iou"], e["corr"], e["edge_corr"])
    elif "color_hist" in e:
        nums = "цвета %.2f" % e["color_hist"]
    else:
        nums = ""
    lines = ["#%d %s" % (m["rank"], m["keys"][0]), rel, nums]
    if m.get("tile"):
        lines.append("плитка " + m["tile"])
    return lines


def tile(world, m, part):
    im = pieces(world, m["src"])
    lines = caption(m, part)
    w = max(TILE_W, im.width + 8)
    th = 16 * len(lines) + 4
    out = Image.new("RGB", (w, im.height + th + 8), BG)
    d = ImageDraw.Draw(out)
    col = COL["canonical"] if m["relation"] == "canonical" else COL[m["decision"]]
    d.rectangle((0, 0, w - 1, out.height - 1), outline=col, width=3)
    out.paste(im, ((w - im.width) // 2, 4))
    for i, t in enumerate(lines):
        d.text((6, im.height + 6 + 16 * i), t, font=F13, fill=col if i == 1 else (225, 225, 225))
    return out


def family_block(world, n, fm, review_filter):
    rev = [m for m in fm["review"] if review_filter(m)]
    groups = [("CANONICAL", [(m, "members") for m in fm["members"][:1]]),
              ("AUTO MEMBERS", [(m, "members") for m in fm["members"][1:]]),
              ("REVIEW REQUIRED", [(m, "review") for m in rev])]
    tiles = []
    for title, ms in groups:
        if not ms:
            continue
        for j, (m, part) in enumerate(ms):
            tiles.append((title if j == 0 else "", tile(world, m, part)))
    lines, cur = [], []
    for t in tiles:
        if len(cur) == PER_LINE:
            lines.append(cur)
            cur = []
        cur.append(t)
    lines.append(cur)
    head = 22
    w = 190 + sum(PER_LINE * [TILE_W + 6]) + 20
    hs = [max(t[1].height for t in ln) + head for ln in lines]
    out = Image.new("RGB", (w, sum(hs) + 10), (28, 28, 30))
    d = ImageDraw.Draw(out)
    d.text((8, 8), "%d." % n, font=F16, fill=(255, 255, 255))
    d.text((8, 30), fm["family_id"], font=F13, fill=(230, 230, 230))
    d.text((8, 48), "ревизия %d" % fm["revision"], font=F13, fill=(170, 170, 170))
    d.text((8, 66), "членов %d, проверка %d" % (len(fm["members"]) - 1, len(rev)), font=F13, fill=(170, 170, 170))
    y = 0
    for ln, h in zip(lines, hs):
        x = 190
        for title, im in ln:
            if title:
                d.text((x, y + 3), title, font=F13, fill=(255, 255, 255))
            out.paste(im, (x, y + head))
            x += im.width + 6
        y += h
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--families", default="art/objects/families/families.json")
    ap.add_argument("--what", choices=("chain", "weak", "view", "batch"), default="chain")
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--out", default="art/_review/families_v2")
    a = ap.parse_args()
    with open(a.families, encoding=ENC) as f:
        fams = json.load(f)
    reason = {"chain": "indirect_chain", "weak": "weak_mirror", "view": "alternate_view_candidate"}.get(a.what)
    if reason:
        pick = [fm for fm in fams if any(m["reason"] == reason for m in fm["review"])]

        def flt(m):
            return m["reason"] == reason
        name = {"chain": "indirect_chain_review", "weak": "weak_mirror_review", "view": "alternate_view_review"}[a.what]
    else:
        pick = [fm for fm in fams if any(m["batch"] == a.batch for m in fm["members"] + fm["review"])]

        def flt(_m):
            return True
        name = "families_batch%02d" % a.batch
    os.makedirs(a.out, exist_ok=True)
    world = mm.World()
    pages, cur, h = [], [], 0
    index = []
    for n, fm in enumerate(pick, 1):
        b = family_block(world, n, fm, flt)
        if cur and h + b.height > PAGE_H:
            pages.append(cur)
            cur, h = [], 0
        cur.append(b)
        h += b.height + 4
        index.append((n, len(pages) + 1, fm))
    if cur:
        pages.append(cur)
    for i, pg in enumerate(pages, 1):
        w = max(b.width for b in pg)
        sheet = Image.new("RGB", (w, sum(b.height + 4 for b in pg)), (16, 16, 18))
        y = 0
        for b in pg:
            sheet.paste(b, (0, y))
            y += b.height + 4
        p = os.path.join(a.out, "%s_%02d.png" % (name, i))
        sheet.save(p)
        print(p, sheet.size, flush=True)
    with open(os.path.join(a.out, name + ".tsv"), "w", encoding=ENC, newline="") as f:
        f.write("строка\tлист\tсемейство\tревизия\tкадр\tномер\tсвязь\tпричина\tчерез\tрешение Vitali\n")
        for n, pg, fm in index:
            for m in fm["review"]:
                if flt(m):
                    f.write("%d\t%d\t%s\t%d\t%s\t%d\t%s\t%s\t%s\t\n" % (
                        n, pg, fm["family_id"], fm["revision"], m["keys"][0], m["rank"], m["relation"],
                        m["reason"], "; ".join(m.get("via", []))))
    print("семейств: %d, листов: %d" % (len(pick), len(pages)))


if __name__ == "__main__":
    main()
