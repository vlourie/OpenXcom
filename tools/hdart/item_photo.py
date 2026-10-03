#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот этапа 1 HD-BIGOBS (ТЗ docs/research/inventory-items-hd.md §8, §10): мастера M-01..M-20 предметной съёмкой.

Цикл рендера - struct_probe.Render как есть (прошёл PHOTO_STRUCT_ACCEPTANCE_V1, вариант C): эскиз struct_guide
первой картинкой, оригинал bicubic второй, Qwen-Image-2.1 по замку (RENDER_V1: 40 шагов, cfg 4, 1 Мп), вырезка
photo_base.cut (альфа из силуэта оригинала, R-089), проверки photo_accept. Своё здесь:
  * промпт ITEM - предметная съёмка ортографически в ориентации оригинала, а не изометрия obj_photo.PHOTO
    (ТЗ §8 п.4: новый generator_rev, утверждается заново; obj_photo.py и photo_render.py не правятся);
  * вход - кадр BIGOBS 32x48 из cards/originals (индексы, 0 прозрачный - как движок, R-043);
  * укладка в прямоугольник §5.3 после вырезки, в HD: сдвиг, при нужде равномерное уменьшение, ориентация
    та же (уменьшать эскиз 32x48 нельзя - лесенка, R-160). Вне прямоугольника после укладки - 0 пикселей.
Описания - census/items/cards/masters.md, принятые для пилота 04.10; здесь - их перевод для модели (WHAT).
M-06 не утверждён (стволы) - в пилот не идёт. M-19 - шаг 1: этикетка пустая, SOY - отдельным шагом.

Модель - только через очередь и под render_chunks.py (не больше 4 рендеров на процесс):
    py -3.13 tools/gpuq.py add --name items_pilot_v1 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
        --out art/items/pilot-v1 --max-renders 4 -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/item_photo.py
Без модели: --dry-run (план, эскизы, промпты, generator_rev), --recut (готовые raw; нет ответа - стоп, R-127).
Выход: <out>/pack/BIGOBS.PCK/<кадр>.<ТИП>.png (k=4, 128x192), <out>/meta/<ТИП>.json, <out>/sheet.png.
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
ROOT = os.path.dirname(os.path.dirname(HERE))

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw        # noqa: E402

import asset_rev as ar                  # noqa: E402
import item_asset_check as iac          # noqa: E402
import photo_base as pb                 # noqa: E402
import photo_render as pr               # noqa: E402
import struct_guide as sg               # noqa: E402
import struct_probe as sp               # noqa: E402

ENC = "utf-8-sig"
OUT = "art/items/pilot-v1"
CARDS = "census/items/cards"
K = 4
PAD = pr.RENDER_V1["pad"]
SEED0 = 4100

ITEM = ("<image1> is a clean shape sketch of {what}, shown on a flat preview panel of colour RGB({r}, {g}, {b}). "
        "The panel is background, not part of the object. "
        "Make a photorealistic studio product photograph of this same real object: {what}. "
        "Orthographic view straight at the object, no perspective, the object in exactly the orientation, "
        "position and size of <image1>. Keep the silhouette, the proportions and the colour areas of <image1>. "
        "Real materials with natural surface detail and light wear, soft light from the upper left, sharp focus. "
        "Output one isolated object on the same flat panel. No hands, no straps, no other objects, "
        "no shadow outside the object, no frame, no text, no letters, no logos.")
NEGATIVE_EXTRA = ", hand, fingers, letters, logo, label text, perspective"

# (мастер, тип, кадр, описание для модели) - по masters.md; M-06 нет до решения о стволах
WHAT = [
    ("M-01", "STR_RIFLE_AK", 1168,
     "an old worn Kalashnikov-pattern assault rifle standing vertically with the muzzle at the top, blued steel "
     "rubbed to grey in places, a dark red-brown wooden handguard with lengthwise grooves, a curved banana "
     "magazine and a pistol grip sticking out to the right in the lower half, the stock at the bottom; no scope, "
     "no rails, no suppressor, no modern plastic"),
    ("M-02", "STR_RIFLE_AK_CLIP", 1169,
     "a curved steel 30-round rifle magazine lying horizontally, dark blued metal with stiffening ribs; "
     "no loose cartridges, no bright plastic"),
    ("M-03", "STR_PISTOL", 3,
     "a massive self-loading pistol pointing up, a big angular slide as a vertical bar along the left edge, the "
     "grip at the bottom going to the right in an L-shaped silhouette, light grey matte steel with dark slots and "
     "serrations on the slide, a dark grip; no chrome, no gold, no flashlight, no laser"),
    ("M-04", "STR_PISTOL_CLIP", 4,
     "a straight narrow pistol magazine standing vertically, grey metal body, the brass-orange case of the top "
     "cartridge visible at the top as the only coloured spot"),
    ("M-05", "STR_SHOTGUN", 1134,
     "a semi-automatic military shotgun standing vertically with the barrel at the top, a long barrel, a ribbed "
     "handguard with crosswise ribs in the upper third, the grip and stock at the bottom with the bottom of the "
     "stock going to the right, black and dark grey metal, a matte polymer grip; no wood, not double-barrelled"),
    ("M-07", "STR_CHAINGUN", 1256,
     "a heavy multi-barrel UAC chaingun standing vertically, a rotating grey cylinder of vertical barrels at the "
     "top, a boxy body in the middle with two rust-orange perforated panels one above the other, a handle with "
     "a small red indicator light at the bottom and a dark rounded box on the right, darkened gunmetal grey; "
     "no ammunition belts"),
    ("M-08", "STR_FLAMETHROWER", 1140,
     "a handheld flamethrower standing vertically with the nozzle at the top, a narrow nozzle tube with a small "
     "brass pilot burner in the upper third, a bright red painted fuel tank on the right in the middle, grips and "
     "stock below, black metal; no flame, no smoke"),
    ("M-09", "STR_GRENADE", 19,
     "a small hand-held high-explosive grenade, compact and smaller than its frame, a dark reddish-brown metal "
     "body, a light steel fuse and ring at the top left catching a highlight"),
    ("M-10", "STR_EMP_GRENADE", 2051,
     "a disc-shaped EMP device lying horizontally, a saturated bright blue rounded dome of glossy enamel, a matte "
     "silver-grey metal rim below with dark slots, a small dark hole on top; no lightning, no sparks"),
    ("M-11", "STR_SATCHEL_CHARGE", 1284,
     "a bulky worn brown leather satchel stuffed with explosives, with stitched seams and a dark flap on top, a "
     "small black plastic detonator with a red light and an antenna at the top left, a brass buckle or ring at "
     "the lower right of the front"),
    ("M-12", "STR_MEDI_KIT", 1665,
     "a bottle of rum standing upright with the neck at the top, thick dark brown glass with a highlight and dark "
     "rum inside, a green cap on the neck with a red rag ribbon tied around it whose ends flutter to the right, a "
     "label band around the middle with a pink-violet pattern and no readable writing; not a medical kit, no red "
     "cross, no bandages"),
    ("M-13", "STR_OXYGEN_TANK", 1865,
     "a steel oxygen cylinder standing vertically over its full height, used grey painted steel, a turquoise band "
     "of two or three ring lines in the upper third, a valve with a red handle on top, a black rubber hose coming "
     "out of the top and looping down the right side to the bottom"),
    ("M-14", "STR_LONG_KNIFE", 2081,
     "a ritual long knife pointing down: the pommel and a dark grip at the top, a straight symmetrical silver "
     "cross guard below them, a long straight mirror-polished steel blade down to the point with a highlight "
     "along it; no blood, no engraving, not curved"),
    ("M-15", "STR_BATTLE_AX", 4056,
     "a battle axe standing vertically with the head at the top, a half-moon crescent blade on the right and a "
     "sharp beak-shaped back spike on the left, steel with a cold violet-grey sheen, a long dark metal haft "
     "going down, the lower third of the haft wrapped crosswise in dark red leather, a pommel at the bottom"),
    ("M-16", "STR_POTATO_SACK", 1617,
     "a standing sack of rough earthy brown burlap with greenish earth stains, the neck at the top tied with a "
     "grey-blue string with the cloth ends sticking out, a rounded belly; nothing visible inside, no potatoes, "
     "no vegetables, no writing"),
    ("M-17", "STR_SCROLL_E4", 4183,
     "an unrolled parchment scroll standing almost vertically and slightly tilted, rolled into tubes at the top "
     "and bottom, light cream-yellow parchment with reddish-golden edges and tube ends, a single dark brown ink "
     "spiral in the centre as the only sign; no text, no characters, no seals"),
    ("M-18", "STR_PIR_ASSAULT", 1607,
     "a folded protective suit of armour lying as a shapeless wide stack, dark blue quilted and plated pieces, "
     "black straps and inserts, a few greenish edge highlights; no helmet with a face, no emblems, no writing, no "
     "person"),
    ("M-19", "STR_FOOD_BAG", 1609,
     "a rectangular food ration pack turned with a corner towards the viewer, its top face and front side "
     "visible, grey-lilac foil with a fine dark pattern on the top face, a dark label area on the front that is "
     "completely blank and even with no letters and no signs"),
    ("M-20", "STR_JUNK_PILE", 1617,
     "a low pile of salvage junk with a wide base and an uneven top, earthy brown and rusty: rusty metal sheets "
     "and scraps, a bent pipe, a bundle of copper wire, a dented chemical canister, dust and earth; not a sack, no "
     "whole machines, no bones, no skulls, no fire"),
]
CODE = (
    ("item_photo.py", ("ITEM", "NEGATIVE_EXTRA", "WHAT", "item_prompt", "load_frame", "place")),
    ("photo_render.py", ("RENDER_V1", "PANEL_TEXT", "flat_input", "detect_panel")),
    ("struct_probe.py", ("C_TEXT", "run_multi", "inputs")),
    ("obj_photo.py", ("NEGATIVE",)),
    ("gen_hd.py", ("QWEN21_REPO", "Qwen21Painter", "qwen21_size", "save_png")),
    ("model_lock.py", ("pin", "check_runtime")),
)


def sha256_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def item_prompt(what, name, rgb):
    """Вместо pr.prompt_for: подложка названа цветом (R-157), фраза специалиста про подложку - в конце."""
    r, g, b = [int(v) for v in rgb]
    kind = "neutral " if name.startswith("grey") else ""
    return ITEM.format(what=what, r=r, g=g, b=b) + " " + pr.PANEL_TEXT.format(kind=kind, r=r, g=g, b=b)


def generator_rev(lock):
    import obj_gen_spec as ogs
    return ar.h12({"params": pr.RENDER_V1, "prompt": ITEM, "negative_extra": NEGATIVE_EXTRA, "c_text": sp.C_TEXT,
                   "lock_rev": ogs.lock_rev(lock), "code": ogs.code_parts(CODE)})


def load_frame(t, frame):
    """Кадр BIGOBS как движок: индексы, 0 прозрачный (R-043), палитра своего файла -> RGBA 32x48."""
    d = os.path.join(CARDS, "originals", t)
    src = [f for f in sorted(os.listdir(d)) if f.startswith("BIGOBS_%d__" % frame)]
    if len(src) != 1:
        raise SystemExit("%s: кадр BIGOBS %d - файлов %d" % (t, frame, len(src)))
    im = Image.open(os.path.join(d, src[0]))
    if im.mode != "P" or im.size != (iac.HAND_W, iac.HAND_H):
        raise SystemExit("%s: %s %s, ждал P 32x48" % (t, im.mode, im.size))
    idx = np.asarray(im)
    pal = np.asarray(im.getpalette()[:768], np.uint8).reshape(-1, 3)
    rgba = np.dstack([pal[idx], np.where(idx == 0, 0, 255).astype(np.uint8)])
    return Image.fromarray(rgba, "RGBA"), src[0]


def crop_job(full):
    """Как photo_base.job_frame: кроп по габариту с полями PAD (кадр сначала расширен на PAD прозрачным)."""
    big = Image.new("RGBA", (full.width + 2 * PAD, full.height + 2 * PAD), (0, 0, 0, 0))
    big.paste(full, (PAD, PAD))
    bb = big.split()[3].getbbox()
    box = (max(0, bb[0] - PAD), max(0, bb[1] - PAD), min(big.width, bb[2] + PAD), min(big.height, bb[3] + PAD))
    return big.crop(box), box


def place(cut4, box, w, h):
    """Вырезка x4 кропа -> кадр k=4 128x192 в прямоугольнике §5.3: сдвиг, при нужде равномерное уменьшение
    (на премультиплицированном), ориентация та же. -> (RGBA, отчёт)."""
    W, H = iac.HAND_W * K, iac.HAND_H * K
    canvas = Image.new("RGBA", ((iac.HAND_W + 2 * PAD) * K, (iac.HAND_H + 2 * PAD) * K), (0, 0, 0, 0))
    canvas.paste(cut4, (box[0] * K, box[1] * K))
    whole = canvas.crop((PAD * K, PAD * K, PAD * K + W, PAD * K + H))
    lost = int((np.asarray(canvas)[..., 3] > 0).sum() - (np.asarray(whole)[..., 3] > 0).sum())
    x0, y0, x1, y1 = (v * K for v in iac.grid_rect(w, h))
    bb = canvas.split()[3].getbbox()
    obj = canvas.crop(bb)
    bw, bh = obj.size
    s = min(1.0, (x1 - x0) / bw, (y1 - y0) / bh)
    if s < 1.0:
        a = np.asarray(obj, np.float32) / 255.0
        pm = np.dstack([a[..., :3] * a[..., 3:], a[..., 3:]])
        nw, nh = max(1, int(bw * s)), max(1, int(bh * s))
        ch = [np.asarray(Image.fromarray((pm[..., i] * 255).astype(np.float32), "F").resize((nw, nh), Image.LANCZOS))
              for i in range(4)]
        al = np.clip(ch[3], 0, 255)
        rgb = np.dstack([np.where(al > 0, np.clip(c, 0, 255) * 255.0 / np.maximum(al, 1e-3), 0) for c in ch[:3]])
        obj = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), al]).astype(np.uint8), "RGBA")
        bw, bh = nw, nh
    # место - как было (центр габарита в кадре), затем ближайшее внутри прямоугольника
    cx, cy = (bb[0] + bb[2]) / 2 - PAD * K, (bb[1] + bb[3]) / 2 - PAD * K
    px = int(round(min(max(cx - bw / 2, x0), x1 - bw)))
    py = int(round(min(max(cy - bh / 2, y0), y1 - bh)))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(obj, (px, py))
    alpha = np.asarray(out)[..., 3]
    return out, {"scale": round(s, 3), "shift": [px - int(round(cx - bw / 2)), py - int(round(cy - bh / 2))],
                 "outside_px": iac.outside(alpha, iac.grid_rect(w, h), K), "lost_off_frame_px": lost}


def sheet(cells, path):
    """Оригинал x4 | эскиз | HD на тёмном фоне инвентаря с рамкой прямоугольника §5.3 | HD в сетке 1:1 (k=4)."""
    W, H, gap, top = iac.HAND_W * K, iac.HAND_H * K, 8, 18
    im = Image.new("RGB", (gap + len(cells) * (W + gap), top + 4 * (H + gap)), (24, 24, 30))
    d = ImageDraw.Draw(im)
    for n, (label, orig, guide, hd, rect) in enumerate(cells):
        x = gap + n * (W + gap)
        d.text((x, 3), label, fill=(230, 230, 230))
        o = orig.resize((W, H), Image.NEAREST)
        im.paste(o, (x, top), o)
        gd = guide.copy()
        gd.thumbnail((W, H))
        im.paste(gd.convert("RGB"), (x, top + H + gap))
        for row in (2, 3):
            y = top + row * (H + gap)
            bg = Image.new("RGBA", (W, H), (16, 18, 26, 255))
            if row == 3:                    # сетка инвентаря: линии клеток 16 px базы
                g = ImageDraw.Draw(bg)
                for v in range(0, W + 1, 16 * K):
                    g.line([(v, 0), (v, H)], fill=(70, 80, 100))
                for v in range(0, H + 1, 16 * K):
                    g.line([(0, v), (W, v)], fill=(70, 80, 100))
            bg.alpha_composite(hd)
            im.paste(bg.convert("RGB"), (x, y))
            if row == 2:
                x0, y0, x1, y1 = (v * K for v in rect)
                d.rectangle([x + x0, y + y0, x + x1 - 1, y + y1 - 1], outline=(200, 60, 60))
    im.save(path)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--only", default="", help="мастера или типы через запятую")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--recut", action="store_true")
    ap.add_argument("--models", default=None)
    ap.add_argument("--max-renders", type=int, default=0, dest="max_renders")
    args = ap.parse_args()
    os.chdir(ROOT)
    only = set(filter(None, args.only.split(",")))
    jobs = []
    for n, (m, t, frame, what) in enumerate(WHAT):
        if only and m not in only and t not in only:
            continue
        with open(os.path.join(CARDS, t + ".json"), encoding=ENC) as f:
            card = json.load(f)
        w, h = int(card["rules"]["invWidth"]["value"]), int(card["rules"]["invHeight"]["value"])
        full, src = load_frame(t, frame)
        crop, box = crop_job(full)
        jobs.append({"asset_id": t, "name": t, "master": m, "frame": frame, "cells": [w, h], "what": what,
                     "seed": SEED0 + n, "src": src, "full": full, "crop": crop, "box": box})

    R = sp.Render(args.out, args.models, args.max_renders, args.recut)
    import gen_fire
    import obj_photo as op
    gen_fire.NEGATIVE = R.po.gen_fire.NEGATIVE = op.NEGATIVE + NEGATIVE_EXTRA
    pr.prompt_for = item_prompt              # Render.job зовёт pr.prompt_for - здесь свой промпт
    R.grev = generator_rev(R.lock)
    print("items_pilot_v1: generator_rev %s, guide_rev %s, cut_rev %s, мастеров %d" % (
        R.grev, R.guide_rev, R.cut_rev, len(jobs)), flush=True)
    gd = os.path.join(args.out, "guide")
    os.makedirs(gd, exist_ok=True)
    plan = []
    for j in jobs:
        panels = pr.panels_by_margin(j["crop"])
        g, rep = sg.build(j["crop"], pr.RENDER_V1["zoom"], panels[0][1])
        g.save(os.path.join(gd, j["name"] + ".png"))
        plan.append((j, panels, g))
        print("%-5s %-20s %dx%d seed %d подложка %s guide %s" % (j["master"], j["asset_id"], j["cells"][0],
                                                                j["cells"][1], j["seed"], panels[0][0], rep), flush=True)
    if args.dry_run:
        with open(os.path.join(args.out, "plan.md"), "w", encoding=ENC) as f:
            f.write("# items_pilot_v1 - план (generator_rev %s)\n\n" % R.grev)
            f.write("negative: %s\n\n" % gen_fire.NEGATIVE)
            for j, panels, _g in plan:
                f.write("## %s %s, кадр %d, %dx%d\n\n%s %s\n\n" % (
                    j["master"], j["asset_id"], j["frame"], j["cells"][0], j["cells"][1],
                    item_prompt(j["what"], panels[0][0], panels[0][1]), sp.C_TEXT))
        print("план: %s" % os.path.join(args.out, "plan.md"))
        return
    raw_dir, meta_dir = os.path.join(args.out, "raw"), os.path.join(args.out, "meta")
    pack = os.path.join(args.out, "pack", "BIGOBS.PCK")
    missing = [j["asset_id"] for j, *_r in plan if not os.path.exists(os.path.join(raw_dir, j["name"] + ".a0.png"))]
    if args.recut and missing:                      # R-127
        raise SystemExit("--recut, а ответа нет у %d: %s" % (len(missing), missing[:5]))
    if missing:
        R.check_lock()
    for d in (raw_dir, meta_dir, pack):
        os.makedirs(d, exist_ok=True)
    t0, cells = time.time(), []
    try:
        for n, (j, panels, g) in enumerate(plan, 1):
            final, attempts = R.job("C", j, j["crop"], panels, raw_dir)
            if final is None:
                print("%-20s нет ответа (--recut)" % j["asset_id"], flush=True)
                continue
            im, rep, _g, _m, c, verdict = final
            hd, prep = place(im, j["box"], *j["cells"])
            if prep["outside_px"]:
                raise SystemExit("%s: после укладки вне прямоугольника %d px" % (j["asset_id"], prep["outside_px"]))
            pp = os.path.join(pack, "%d.%s.png" % (j["frame"], j["asset_id"]))
            hd.save(pp)
            meta = {"asset_id": j["asset_id"], "master": j["master"], "frame": j["frame"], "cells": j["cells"],
                    "what": j["what"], "src": j["src"], "generator_rev": R.grev, "guide_rev": R.guide_rev,
                    "cut_rev": R.cut_rev, "attempts": attempts, "report": rep,
                    "checks": {x: list(c[x]) for x in sp.pa.MACHINE_CHECKS}, "machine": verdict,
                    "outcome": sp.pa.outcome(verdict, len(attempts)), "place": prep,
                    "file": pp.replace("\\", "/"), "sha256": sha256_file(pp), "status": "AGENT_PROPOSED",
                    "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with open(os.path.join(meta_dir, j["name"] + ".json"), "w", encoding=ENC) as f:
                json.dump(meta, f, ensure_ascii=False, indent=1)
            cells.append(("%s %s" % (j["master"], meta["outcome"]), j["full"], g, hd, iac.grid_rect(*j["cells"])))
            print("%-5s %-20s %-16s попыток %d, укладка x%.2f | готово %d из %d, прошло %.0f мин" % (
                j["master"], j["asset_id"], meta["outcome"], len(attempts), prep["scale"], n, len(plan),
                (time.time() - t0) / 60), flush=True)
    except sp.Budget:
        print("лимит процесса: новых рендеров %d из %d - выхожу, продолжит новый процесс" % (R.renders, R.max),
              flush=True)
        sys.exit(sp.EXIT_MORE)
    if cells:
        sheet(cells, os.path.join(args.out, "sheet.png"))
    ex = {"generator_rev": R.grev, "guide_rev": R.guide_rev, "guide": sg.GUIDE_V1, "cut_rev": R.cut_rev,
          "params": pr.RENDER_V1, "prompt": ITEM, "negative": gen_fire.NEGATIVE, "c_text": sp.C_TEXT,
          "items": len(plan), "renders_last_process": R.renders, "gpuq_job": os.environ.get("GPUQ_JOB_ID", ""),
          "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if not args.recut:
        with open(os.path.join(args.out, "execution.json"), "w", encoding=ENC) as f:
            json.dump(ex, f, ensure_ascii=False, indent=1)
    print("готово: мастеров %d, новых рендеров в этом процессе %d" % (len(cells), R.renders), flush=True)


if __name__ == "__main__":
    main()
