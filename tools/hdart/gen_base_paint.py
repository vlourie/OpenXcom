#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот «Живой базы» (docs/research/base-living-2026-10-22.md, шаг 0): постройки базы, перерисованные моделью.

Путь strict, одобренный для предметов карты (DECISIONS 2026-09-27): Qwen-Image-2.1 рисует с нуля, классика -
эскиз формы, раскладки и палитры, cfg 4, 40 шагов. Вход - постройка целиком так, как её собирает
gen_base_anim.Facility (форма + картинка, Scale2x x4), на ровной серой подложке. Один seed на постройку во всех
стилях - чтобы стили сравнивались на одной раскладке.

Стили (STYLES): painted - рисованная диорама, diorama - фото макета, pixel - HD-пиксель.
Альфа - только силуэт классики (R-089): ответ модели не вырезается по своей подложке.

Выход art/base_living/pilot/:
    in/<ТИП>.png                       вход модели (без модели --dry-run пишет только его)
    <стиль>/raw/<ТИП>.png              ответ модели как есть
    <стиль>/<ТИП>.png                  128 на клетку (как пак при k = 4), альфа по силуэту
    <стиль>/<ТИП>@512.png              512 на клетку - запас для превью и будущего k
    <стиль>/_rock.png                  скала под базой этого стиля
    sheet_<стиль>.png, run.json

    py -3.13 tools/hdart/gen_base_paint.py --dry-run
    py -3.13 tools/gpuq.py add --name base-paint-pilot --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/gen_base_paint.py
В пак ничего не пишется (арт - сначала показать Vitali).
"""
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")        # до импорта diffusers (R-145)
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import argparse                                     # noqa: E402
import json                                         # noqa: E402
import time                                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageFilter                  # noqa: E402

from facility_sheet import load_rules, sprites_map  # noqa: E402
from gen_base_anim import Facility, K               # noqa: E402
from gen_craft_lights import load_frame             # noqa: E402
from gen_base import scale2x                        # noqa: E402

OUT = os.path.join(ROOT, "art", "base_living", "pilot")
RUN = {"steps": 40, "cfg": 4.0, "mp": 1.0, "offload": "model"}
PANEL = (118, 118, 122)
MASTER = 512                                        # пикселей на клетку в запасной картинке

# Витрина: стартовая база Пираток, всё, что показывает состояние базы, и три «героя» (вода, пар, свечение).
PILOT = ["STR_ACCESS_LIFT", "STR_HANGAR", "STR_LIVING_QUARTERS", "STR_BURROW", "STR_CORRIDOR",
         "STR_LABORATORY", "STR_WORKSHOP", "STR_GENERAL_STORES", "STR_SMALL_RADAR_SYSTEM", "STR_LASER_DEFENSES",
         "STR_MED_BAY", "STR_PRISON", "STR_GYM_ROOM", "STR_ONSEN", "STR_SUMMONING_CIRCLE", "STR_HELLERIUM_PLANT"]

STYLES = {
    "painted": ("Style: premium hand-painted digital illustration for the base-building screen of a modern strategy "
                "game - crisp confident brushwork, rich believable materials (scuffed steel plates, poured concrete, "
                "worn paint, rubber cables, glass, brass), fine readable detail, warm practical lamps, gentle "
                "ambient occlusion in the corners."),
    "diorama": ("Style: a sharp studio photograph of a highly detailed tabletop miniature diorama of this room, "
                "real scale-model materials (styrene plates, etched metal, resin, tiny cables and decals), "
                "weathering washes, soft even studio light from above, everything in focus."),
    "pixel": ("Style: high-resolution modern pixel art like the best contemporary indie games - deliberate clean "
              "pixel clusters, rich but limited palette, crisp hand-placed highlights, no blur, no dithering noise."),
}

COMMON = ("<image1> is the low-resolution original sprite of one room of an underground pirate base, seen straight "
          "from above, shown on a flat grey preview panel. The panel is interface, not part of the room. "
          "Use case: sketch-to-render. Asset type: 4x HD top-down plan view of the room for the base screen of an "
          "X-COM-style strategy game: orthographic, camera exactly overhead, no perspective, the room cut open "
          "with no ceiling. What the room is for, from the game's encyclopedia: {purpose} "
          "Redraw this same room as {what}. Keep the outline, the thick beveled brass-gold outer wall, the "
          "position and size of every piece of furniture and machinery and the colours of <image1>. Add nothing "
          "that the room would not have: no computer desks or screens unless they are named above. {style} "
          "Soft even light from above, no strong cast shadows. No people, no characters, no text, no labels. "
          "Output the room alone on the same flat panel.")
NEGATIVE = ("perspective, isometric, tilted camera, side view, 3d render of a building exterior, blurry, smudged, "
            "jagged stair-stepped edges, noise, low detail, people, characters, person, woman, man, text, letters, "
            "watermark, logo, frame, border, drop shadow, nude")
NEGATIVE_PIXEL = NEGATIVE.replace("jagged stair-stepped edges, ", "")
NEGATIVE_BIG = ", inner walls, partition walls, room divided into several rooms, dividing walls along the grid"

# Что за комната - tools/hdart/base_rooms.tsv: purpose - пересказ статьи педии мода (art/base_living/census.tsv),
# what - что видно на классике (art/base_living/in/). Без назначения модель видит в лифте «комнату с шахтой и
# пультами», а в ангаре - четыре комнаты, где корабль не сядет (R-445).
ROOMS = os.path.join(HERE, "base_rooms.tsv")


def load_rooms():
    import csv
    purpose, what = {}, {}
    with open(ROOMS, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("type") and row.get("purpose") and row.get("what"):
                purpose[row["type"]] = row["purpose"].strip()
                what[row["type"]] = row["what"].strip()
    return purpose, what


PURPOSE, WHAT = load_rooms()
assert set(PURPOSE) >= set(PILOT), "у постройки нет назначения из педии или описания вида (R-445)"

ROCK_WHAT = ("<image1> is a rough colour sketch. Top-down texture of the natural bedrock an underground base is "
             "carved into, seen straight from above: dark grey-brown rock with cracks, strata, loose gravel and "
             "chisel marks, one continuous surface without repeating patterns. Only rock - no metal, no plates, no "
             "machinery, no cables, no lamps, no objects. {style}")
# Скале - только манера стиля, без его материалов (первый пилот: сталь, кабели и лампы стиля пролезли в камень).
ROCK_STYLE = {
    "painted": "Style: premium hand-painted digital illustration, crisp confident brushwork, subtle colour variation.",
    "diorama": "Style: a sharp studio photograph of the textured rock base of a tabletop miniature diorama, "
               "everything in focus.",
    "pixel": "Style: high-resolution modern pixel art, deliberate clean pixel clusters, rich but limited palette.",
}


def facility_input(fac):
    """Вход модели: постройка x4 на ровной подложке (RGB) и её силуэт x4 (0..1)."""
    a = fac.alpha[..., None]
    rgb = fac.rgb * 255.0 * a + np.array(PANEL, np.float32) * (1 - a)     # Facility.rgb - доли 0..1
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB"), fac.alpha


def rock_input(sprites):
    """Скала классики (кадр сетки базы 0) - одна клетка без рамки, размыто: только цвет, не узор
    (плитка 3x3 в первом пилоте дала модели повтор, и она его нарисовала)."""
    got = load_frame(0, sprites)
    if got is None:
        return Image.new("RGB", (384, 384), (70, 64, 58))
    idx, pal = got
    idx = idx[2:30, 2:30]                           # без зелёной рамки клетки сетки
    hi = scale2x(scale2x(idx))
    tile = Image.fromarray(pal[hi].astype(np.uint8), "RGB").resize((384, 384), Image.BICUBIC)
    return tile.filter(ImageFilter.GaussianBlur(radius=10))


def footprint(alpha4, size):
    """Силуэт классики под размер `size` (w, h): гладкий край без ступенек Scale2x."""
    im = Image.fromarray((alpha4 * 255).astype(np.uint8), "L").resize(size, Image.LANCZOS)
    im = im.filter(ImageFilter.GaussianBlur(radius=max(0.6, size[0] / 1024)))
    a = np.asarray(im, np.float32) / 255.0
    return np.clip((a - 0.5) * 3.0 + 0.5, 0, 1)


def finish(raw, alpha4, cols, rows, per_cell):
    size = (cols * per_cell, rows * per_cell)
    rgb = np.asarray(raw.convert("RGB").resize(size, Image.LANCZOS), np.float32)
    a = footprint(alpha4, size)
    return Image.fromarray(np.dstack([rgb, a * 255]).astype(np.uint8), "RGBA")


class Painter:
    def __init__(self, models):
        import gen_hd
        import gen_fire
        ns = argparse.Namespace(models=models, qwen21_model="", qwen21_steps=RUN["steps"], qwen21_cfg=RUN["cfg"],
                                qwen21_mp=RUN["mp"], qwen21_strength=0.0, qwen21_offload=RUN["offload"],
                                qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                                qwen21_hint="off", qwen21_ref_order="ref-first")
        self.p = gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
        self.gf = gen_fire
        self.args = argparse.Namespace(steps=RUN["steps"], cfg=RUN["cfg"], mp=RUN["mp"])
        self.first = True

    def paint(self, img, prompt, negative, seed):
        self.gf.NEGATIVE = negative                 # run_pass берёт негатив из модуля gen_fire
        out = self.gf.run_pass(self.p, self.args, prompt, img, seed)
        if self.first:
            import doll_photo_pilot as dp
            dp.gpu_mem("первый рисунок")
            self.first = False
        import gc
        gc.collect()
        self.p.torch.cuda.empty_cache()
        return out


def sheet(style, items):
    """Лист: классика x4 | стиль, по постройке в строке (ширина по самой широкой)."""
    cell = 256
    rows = []
    for t, fac in items:
        a = Image.open(os.path.join(OUT, "in", t + ".png")).convert("RGB")
        p = os.path.join(OUT, style, t + "@512.png")
        h = fac.rows * cell
        left = a.resize((fac.cols * cell, h), Image.NEAREST)
        row = Image.new("RGB", (2 * 2 * cell + 16, max(h, cell)), (16, 16, 20))
        row.paste(left, (0, 0))
        if os.path.exists(p):
            b = Image.open(p).convert("RGBA").resize((fac.cols * cell, h), Image.LANCZOS)
            bg = Image.new("RGBA", b.size, (16, 16, 20, 255))
            bg.alpha_composite(b)
            row.paste(bg.convert("RGB"), (2 * cell + 16, 0))
        rows.append(row)
    out = Image.new("RGB", (rows[0].width * 2 + 16, sum(r.height for r in rows[::2]) + 8 * len(rows)), (8, 8, 10))
    y = [0, 0]
    for i, r in enumerate(rows):
        col = i % 2
        out.paste(r, (col * (r.width + 16), y[col]))
        y[col] += r.height + 8
    out = out.crop((0, 0, out.width, max(y)))
    out.save(os.path.join(OUT, "sheet_%s.png" % style))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default=os.environ.get("HD_MODELS", "E:\\models"))
    ap.add_argument("--styles", default=",".join(STYLES))
    ap.add_argument("--only", default="")
    ap.add_argument("--seed", type=int, default=4100)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redraw", action="store_true", help="рисовать заново и то, что уже есть в raw/")
    ap.add_argument("--rock-only", action="store_true", dest="rock_only", help="только скалы (заново)")
    ns = ap.parse_args()
    styles = [s for s in ns.styles.split(",") if s]
    types = [t for t in (ns.only.split(",") if ns.only else PILOT) if t]
    lost = [t for t in types if t not in WHAT]
    if lost:
        sys.exit("нет описания в %s (R-445): %s" % (ROOMS, ", ".join(lost)))
    rules, _ = load_rules()
    sprites = sprites_map()
    os.makedirs(os.path.join(OUT, "in"), exist_ok=True)
    items = []
    for t in types:
        fac = Facility(rules[t], sprites)
        if fac.missing:
            print("!! %s: нет кадров %s" % (t, fac.missing))
            continue
        img, _a = facility_input(fac)
        img.save(os.path.join(OUT, "in", t + ".png"))
        items.append((t, fac))
        print("%-26s %dx%d клеток, кадры %s" % (t, fac.cols, fac.rows, fac.indices))
    rock = rock_input(sprites)
    rock.save(os.path.join(OUT, "in", "_rock.png"))
    painter = None if ns.dry_run else Painter(ns.models)
    run = {"engine": RUN, "seed": ns.seed, "styles": STYLES, "prompt": COMMON, "negative": NEGATIVE,
           "what": WHAT, "purpose": PURPOSE, "dry_run": ns.dry_run, "times": {}}
    t0 = time.time()
    for style in styles:
        d = os.path.join(OUT, style)
        os.makedirs(os.path.join(d, "raw"), exist_ok=True)
        neg = NEGATIVE_PIXEL if style == "pixel" else NEGATIVE
        # с --only скала не трогается (её перерисовывает --rock-only)
        jobs = ([("_rock", None)] if ns.rock_only or not ns.only else []) + ([] if ns.rock_only else items)
        for n, (t, fac) in enumerate(jobs):
            raw_path = os.path.join(d, "raw", t + ".png")
            again = ns.redraw or (ns.rock_only and fac is None)
            if painter is not None and (again or not os.path.exists(raw_path)):
                tt = time.time()
                if fac is None:
                    raw = painter.paint(rock, ROCK_WHAT.format(style=ROCK_STYLE[style]), neg, ns.seed + 999)
                else:
                    img, _a = facility_input(fac)
                    prompt = COMMON.format(what=WHAT[t], purpose=PURPOSE[t], style=STYLES[style])
                    # большая постройка - один зал: модель делит 2x2 на четыре комнаты по сетке клеток
                    big = fac.cols * fac.rows > 1
                    raw = painter.paint(img, prompt, neg + (NEGATIVE_BIG if big else ""), ns.seed + n)
                raw.save(raw_path)
                run["times"]["%s/%s" % (style, t)] = round(time.time() - tt, 1)
                print("  %s/%s: %.0f с (всего %.0f мин)" % (style, t, time.time() - tt, (time.time() - t0) / 60),
                      flush=True)
            if not os.path.exists(raw_path):
                continue
            raw = Image.open(raw_path)
            if fac is None:
                raw.convert("RGB").resize((768, 768), Image.LANCZOS).save(os.path.join(d, "_rock.png"))
                continue
            _img, a4 = facility_input(fac)
            finish(raw, a4, fac.cols, fac.rows, 32 * K).save(os.path.join(d, t + ".png"))
            finish(raw, a4, fac.cols, fac.rows, MASTER).save(os.path.join(d, t + "@512.png"))
        sheet(style, items)
    with open(os.path.join(OUT, "run.json"), "w", encoding="utf-8-sig") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    print("готово: %s (%.0f мин)" % (OUT, (time.time() - t0) / 60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
