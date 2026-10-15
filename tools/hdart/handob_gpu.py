#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот хвата: шесть HD-кадров HANDOB на видеокарте, без Codex (указание Vitali 06.10).

STR_OLD_SNIPER_RIFLE, STR_SAW, STR_TOMMYGUN - кадры handSprite+2 и +4 (стойка и прицел взгляда d2). MP40 исключён.
Массовой генерации, судей и правок движка нет.

Генератор - Edit-2511 без LoRA, 40 шагов, cfg 4 (лучший на Томпсоне в weapons_probe4 N2: IoU 0.994, пропорции
-0.6 %). Память - в две фазы weapons_probe5.two_phase: текстовая модель и трансформер на карте не вместе (R-213),
shared больше 0.5 ГБ - стоп. Вход - ОДНА картинка: кадр HANDOB на подложке, гладко до ~1 Мп (bicubic и размытие
на полпикселя, R-004); второй картинкой BIGOBS не подаётся - Edit-2511 берёт ракурс у второй картинки (R-211).
Конструкция и материалы - словами по BIGOBS и боеприпасу (handob_codex.WHAT), только то, что у ствола есть (R-221).

Целевые зоны заморожены до генерации (target_zones.json, handob_codex prep); здесь они только читаются, хэши
zones.json и tasks.json сверяются.

    py -3.13 tools/hdart/handob_gpu.py --dry-run          входы и промпты, без модели
    py -3.13 tools/gpuq.py add --name handob_pilot --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/handob_gpu.py
    py -3.13 tools/hdart/handob_gpu.py fit                кадры 128x160, сверка рамки, дула и зон, лист
Выход art/items/weapons100-v1/grip_pilot/gpu/: inputs/, raw/<тип>.<кадр>.png, hd/<тип>/<кадр>.png, check.json,
sheet.png, meta.json."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import json                             # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import battle_view as bv                # noqa: E402
import handob_codex as hc               # noqa: E402
import weapons_edit as we               # noqa: E402
import weapons_probe3 as p3             # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join(hc.PILOT, "gpu")
FULL = {"steps": 40, "cfg": 4.0}
SEED = 4242
PAD = 2                                 # поле вокруг рисунка, пикс базы

PROMPT = ("Redraw <image1> at high resolution as a detailed hand-painted game sprite of a weapon held in the hand, "
          "seen from the battle camera: {view}. It is exactly the same weapon in the same view: the same outline, "
          "length, size, proportions and colours, the barrel pointing the same way, the muzzle and the butt end at "
          "the same places, every part in the same place and of the same size, nothing added and nothing removed. "
          "What the weapon is: {what}. {special}Give it clear volume and convincing materials with soft highlights "
          "along the edges, crisp clean continuous edges, small parts readable. Only the weapon: no hands, no arms, "
          "no soldier. Keep the same plain flat background colour, no shadow, no text.")
NEGATIVE = p3.NEGATIVE + ", hands, fingers, arm, soldier, " + bv.prompt_block("hand_item")["negative"]


def frames():
    with open(hc.FREEZE, encoding=ENC) as f:
        frozen = json.load(f)
    if hc.sha(os.path.join(hc.PILOT, "zones.json")) != frozen["zones_json_sha256"]:
        raise SystemExit("zones.json изменён после заморозки - зоны не двигаются")
    if hc.sha(os.path.join(hc.PILOT, "tasks.json")) != frozen["tasks_json_sha256"]:
        raise SystemExit("tasks.json изменён после заморозки")
    return frozen["frames"]


def classic(fr):
    """Кадр HANDOB: RGB float, маска, рамка рисунка в базе (по маске, сверяется с заморозкой)."""
    a = hc.handob_rgba(fr["frame"])
    m = a[..., 3] > 0
    box = we.bbox(m)
    want = tuple(v // 4 for v in fr["bbox_x4"][:2]) + tuple((v + 1) // 4 for v in fr["bbox_x4"][2:])
    if box != want:
        raise SystemExit("%s.%d: рамка кадра %s, в заморозке %s" % (fr["type"], fr["frame"], box, want))
    return a[..., :3].astype(np.float32), m, box


def make_input(fr):
    rgb, m, (x0, y0, x1, y1) = classic(fr)
    h, w = m.shape
    box = (max(0, x0 - PAD), max(0, y0 - PAD), min(w, x1 + PAD), min(h, y1 + PAD))
    size = we.target_size(box[2] - box[0], box[3] - box[1])
    panel = we.panel_for(rgb, m)
    return p3.smooth_input(rgb, m, box, size, panel), panel, box


def prompt_of(fr):
    what, special = hc.WHAT[fr["type"]]
    special = special.replace("image 1 and image 2", "image 1").replace("image 1", "<image1>")
    special = " ".join(s.strip("- ;") for s in special.splitlines() if s.strip())
    return PROMPT.format(view=bv.prompt_block("hand_item")["positive"], what=what,
                         special=(special[0].upper() + special[1:] + ". ") if special else "")


def render(items, a):
    import gen_hd
    import item_photo as ip
    import photo_ui as pu
    import torch
    import weapons_probe5 as p5
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
    t0 = time.time()
    todo = [it for it in items if a.force or not os.path.exists(it["raw"])]
    print("кадров к рисованию: %d из %d" % (len(todo), len(items)), flush=True)
    if not todo:
        return
    pipe, embeds = p5.two_phase(models, [(it["inp"], it["prompt"], NEGATIVE) for it in todo])
    loaded = pipe.get_list_adapters() if hasattr(pipe, "get_list_adapters") else "?"
    print("LoRA в модели: %s" % (loaded or "нет"), flush=True)
    if loaded:
        raise SystemExit("LoRA загружена - не тот генератор")
    dev = torch.device("cuda")
    for n, (it, emb) in enumerate(zip(todo, embeds), 1):
        ts = time.time()
        img = it["inp"]
        pe, pm, npe, npm = (t.to(dev) for t in emb)
        g = torch.Generator("cuda").manual_seed(a.seed)
        with torch.no_grad():
            raw = pipe(image=[img], prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                       negative_prompt_embeds=npe, negative_prompt_embeds_mask=npm, true_cfg_scale=FULL["cfg"],
                       num_inference_steps=FULL["steps"], height=img.height, width=img.width,
                       generator=g).images[0].convert("RGB")
        if p5.gpu_mem("кадр %d" % n) > 0.5:
            raise SystemExit("ушло в shared - стоп")
        raw.save(it["raw"])
        print("[%d/%d] %s: %.0f с" % (n, len(todo), it["key"], time.time() - ts), flush=True)
    meta = {"seed": a.seed, "full": FULL, "lora": "нет", "model_rev": ip.EDIT_MODEL_REV, "negative": NEGATIVE,
            "prompts": {it["key"]: it["prompt"] for it in items}, "pad_base": PAD,
            "seconds": round(time.time() - t0), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(OUT, "meta.json"), "w", encoding=ENC) as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print("готово за %.0f с" % (time.time() - t0), flush=True)


def fit_one(it):
    """Ответ -> RGBA 128x160: один масштаб по длине (без растяжки, R-208), место по рамке классики x4.
    Альфа - маска самого ответа (подложка известна), уменьшение BOX даёт мягкий край."""
    fr = it["fr"]
    raw = np.asarray(Image.open(it["raw"]).convert("RGB"))
    rm, bg = we.object_mask(raw, bg=None, thr=24.0)
    rx0, ry0, rx1, ry1 = we.bbox(rm)
    bx0, by0, bx1, by1 = fr["bbox_x4"]
    tw, th = bx1 - bx0 + 1, by1 - by0 + 1
    s = tw / float(rx1 - rx0)
    nh = max(1, int(round((ry1 - ry0) * s)))
    a = rm[ry0:ry1, rx0:rx1].astype(np.float32)
    rgb = raw[ry0:ry1, rx0:rx1].astype(np.float32)
    pre = np.dstack([rgb * a[..., None], a * 255]).astype(np.float32)
    small = np.asarray(Image.fromarray(np.clip(pre, 0, 255).astype(np.uint8), "RGBA").resize((tw, nh), Image.BOX),
                       np.float32)
    al = small[..., 3:4] / 255.0
    col = np.where(al > 0, small[..., :3] / np.maximum(al, 1e-3) * 1.0, 0)  # BOX усредняет и цвет, и альфу
    col = np.clip(col, 0, 255)
    out = np.zeros((160, 128, 4), np.float32)
    oy = by0 + (th - nh) // 2
    y0, y1 = max(0, oy), min(160, oy + nh)
    out[y0:y1, bx0:bx0 + tw, :3] = col[y0 - oy:y1 - oy]
    out[y0:y1, bx0:bx0 + tw, 3] = small[y0 - oy:y1 - oy, :, 3]
    out[..., 3] = np.where(out[..., 3] < 20, 0, out[..., 3])
    hd = out.astype(np.uint8)
    op = hd[..., 3] > 0
    ys, xs = np.nonzero(op)
    got = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    size = [got[2] - got[0] + 1, got[3] - got[1] + 1]
    mx, my = fr["muzzle_x4"][:2]
    d_mz = float(np.sqrt(((xs - mx) ** 2 + (ys - my) ** 2).min()))
    zones = {}
    for role in ("grip", "support", "unidentified"):
        zs = fr["zones"].get(role) or []
        zones[role] = [round(float(op[r[1]:r[3] + 1, r[0]:r[2] + 1].mean()), 2) for r in zs]
    hands = {}
    for role, h in fr["pose_hands"].items():
        d = min(float(np.sqrt(((xs - (px * 4 + 1.5)) ** 2 + (ys - (py * 4 + 1.5)) ** 2).min())) for px, py in h["skin"])
        hands[role] = {"dist_x4": round(d, 1), "dist_base": round(d / 4, 1),
                       "classic_base": h["dist_geom_classic"]}
    tol = fr["size_tolerance_px_x4"]
    rep = {"bbox_x4": got, "bbox_x4_target": fr["bbox_x4"], "size": size, "size_target": fr["size_x4"],
           "size_ok": abs(size[0] - fr["size_x4"][0]) <= tol[0] and abs(size[1] - fr["size_x4"][1]) <= tol[1],
           "height_scaled_pct": round(100.0 * (nh / float(th) - 1), 1),
           "aspect_raw_pct": round(100.0 * (((rx1 - rx0) / float(ry1 - ry0)) / (tw / float(th)) - 1), 1),
           "muzzle_target": fr["muzzle_x4"], "muzzle_dist_x4": round(d_mz, 1),
           "muzzle_ok": d_mz <= fr["muzzle_tolerance_px_x4"],
           "zone_fill": zones, "pose_hands": hands, "raw_bg": [round(float(v)) for v in bg]}
    return hd, rep


def draw_marks(img, fr, k):
    d = ImageDraw.Draw(img)
    cols = {"grip": (60, 200, 255), "support": (255, 220, 40), "unidentified": (255, 90, 200)}
    for role, c in cols.items():
        for r in fr["zones"].get(role) or []:
            d.rectangle([r[0] * k, r[1] * k, (r[2] + 1) * k - 1, (r[3] + 1) * k - 1], outline=c, width=2)
    for role, c in (("main", (40, 120, 255)), ("support", (40, 220, 90))):
        h = fr["pose_hands"].get(role)
        if h:
            x0, y0, x1, y1 = h["bbox_x4"]
            d.rectangle([x0 * k, y0 * k, (x1 + 1) * k - 1, (y1 + 1) * k - 1], outline=c, width=1)
    mx, my = fr["muzzle_x4"][:2]
    d.line([(mx - 3) * k, my * k, (mx + 3) * k, my * k], fill=(255, 40, 40), width=2)
    d.line([mx * k, (my - 3) * k, mx * k, (my + 3) * k], fill=(255, 40, 40), width=2)


def sheet(items):
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    K = 3
    CW, CH = 128 * K, 160 * K
    heads = ("классика x4 (nearest, только показ)", "вход модели", "HD-кадр", "HD-кадр + зоны")
    out = Image.new("RGB", (len(heads) * (CW + 8) + 10, len(items) * (CH + 44) + 30), (20, 22, 30))
    d = ImageDraw.Draw(out)
    for c, hname in enumerate(heads):
        d.text((10 + c * (CW + 8), 6), hname, fill=(200, 200, 210), font=font)
    floor = (58, 60, 66)
    for i, it in enumerate(items):
        Y = 28 + i * (CH + 44)
        fr = it["fr"]
        a = hc.handob_rgba(fr["frame"])
        cl = Image.new("RGBA", (32, 40), floor + (255,))
        cl.alpha_composite(Image.fromarray(a, "RGBA"))
        out.paste(cl.convert("RGB").resize((CW, CH), Image.NEAREST), (10, Y))
        inp = it["inp"].copy()
        inp.thumbnail((CW, CH))
        out.paste(inp, (10 + CW + 8, Y))
        if it.get("hd") is not None:
            for c, marks in ((2, False), (3, True)):
                bg = Image.new("RGBA", (128, 160), floor + (255,))
                bg.alpha_composite(Image.fromarray(it["hd"], "RGBA"))
                big = bg.convert("RGB").resize((CW, CH), Image.LANCZOS)
                if marks:
                    draw_marks(big, fr, K)
                out.paste(big, (10 + c * (CW + 8), Y))
            r = it["rep"]
            txt = "%s  размер %s/%s %s  дуло %.1f %s  высота %+.1f%%" % (
                it["key"], r["size"], r["size_target"], "ок" if r["size_ok"] else "МИМО", r["muzzle_dist_x4"],
                "ок" if r["muzzle_ok"] else "МИМО", r["height_scaled_pct"])
        else:
            txt = it["key"] + "  (ответа нет)"
        d.text((10, Y + CH + 6), txt, fill=(220, 220, 230), font=font)
    out.save(os.path.join(OUT, "sheet.png"))
    print("лист:", os.path.join(OUT, "sheet.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="render", choices=("render", "fit"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="перерисовать готовые ответы")
    ap.add_argument("--models", default="")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()
    os.chdir(hc.ROOT)
    for sub in ("inputs", "raw", "hd"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    items = []
    for k, fr in frames().items():
        inp, panel, box = make_input(fr)
        it = {"key": k, "fr": fr, "inp": inp, "panel": panel, "box": box, "prompt": prompt_of(fr),
              "raw": os.path.join(OUT, "raw", k + ".png")}
        inp.save(os.path.join(OUT, "inputs", k + ".png"))
        with open(os.path.join(OUT, "inputs", k + ".prompt.txt"), "w", encoding=ENC) as f:
            f.write(it["prompt"] + "\n\nnegative:\n" + NEGATIVE + "\n")
        items.append(it)
    print("кадров: %d (%s)" % (len(items), ", ".join(it["key"] for it in items)))
    if a.cmd == "render" and not a.dry_run:
        render(items, a)
    if a.dry_run:
        print("dry-run: модель не грузилась; входы ->", os.path.join(OUT, "inputs"))
    reps = {}
    for it in items:
        if os.path.exists(it["raw"]):
            it["hd"], it["rep"] = fit_one(it)
            dst = os.path.join(OUT, "hd", it["fr"]["type"])
            os.makedirs(dst, exist_ok=True)
            Image.fromarray(it["hd"], "RGBA").save(os.path.join(dst, "%d.png" % it["fr"]["frame"]))
            reps[it["key"]] = it["rep"]
            print(it["key"], json.dumps(it["rep"], ensure_ascii=False))
    if reps:
        with open(os.path.join(OUT, "check.json"), "w", encoding=ENC) as f:
            json.dump(reps, f, ensure_ascii=False, indent=1)
    sheet(items)


if __name__ == "__main__":
    main()
