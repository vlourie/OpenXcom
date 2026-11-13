#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Проба Vitali 03.10: «эти 4 картинки с АК - эталон, остальное оружие сделать хотя бы на таком уровне,
попробуй 10 через 2511». Qwen-Image-Edit-2511 + Lightning 8 шагов (item_photo.EditPainter, папка снимка R-207).
Описаний нет: модель ПРАВИТ первую картинку - сам предмет.

Два варианта на предмет, один seed:
  A - один вход: оригинал (xBRZ x4 из weapons_sr, затем гладко до 1 Мп) на ровной подложке;
  B - два входа (R-205): тот же оригинал + эталон Vitali того же рода как образец ВЫДЕЛКИ, не формы
      (R-211: Edit-2511 тянет позу и детали у эталона - в промпте прямо сказано брать у него только манеру).
Эталоны: art/items/refs/vitali (Автоган, Уличный метла, Мутантский пулемёт - картинки Vitali) и
art/items/ak-final/finished_x16.png (АК). Меток во входе нет (R-204).

Ответ - как есть, плюс маска по подложке ответа только для замера и листа (в мод ничего не идёт):
силуэт IoU против оригинала, пропорции, цвет и яркость в масштабе оригинала.

Без модели (входы, эталоны, лист без ответа):
    py -3.13 tools/hdart/weapons_edit.py --dry-run
С моделью - только через очередь:
    py -3.13 tools/gpuq.py add --name weapons_edit10 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/weapons_edit.py
Выход art/items/weapons-edit-v1/: in/<ТИП>.png, ref/<эталон>.png, A/<ТИП>.png, B/<ТИП>.png, sheet_NN.png, check.tsv."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import csv                              # noqa: E402
import json                             # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ROOT = os.path.dirname(os.path.dirname(HERE))
ENC = "utf-8-sig"
BATCH = "art/items/weapons100-v1"
OUT = "art/items/weapons-edit-v1"
SEED = 4242
MP = 1.0
ONLY = ("W-012", "W-014", "W-015", "W-026", "W-033", "W-040", "W-055", "W-064", "W-073", "W-081")
REFS = {"autogun": "art/items/refs/vitali/autogun.png",
        "street_sweeper": "art/items/refs/vitali/street_sweeper.webp",
        "mutant_mg": "art/items/refs/vitali/mutant_mg.webp",
        "ak": "art/items/ak-final/finished_x16.png"}
REF_OF_KIND = {"mg": "autogun", "rifle": "autogun", "shotgun": "street_sweeper", "rl": "mutant_mg",
               "pistol": "ak", "melee": "ak"}

PROMPT_A = ("Redraw <image1> as a clean high-resolution painted game inventory item. It is exactly the same "
            "weapon: the same view, the same outline, the same size and proportions, the same colours, every "
            "part in the same place and of the same size, nothing added and nothing removed. Turn the blocky "
            "low-resolution drawing into crisp clean edges, fine painted detail and smooth shading, like "
            "high-quality hand-painted game art. Not a photo, no pixels, no blur. Keep the same flat "
            "background colour, no shadow, no text.")
PROMPT_B = ("<image1> is a low-resolution game sprite of a weapon. <image2> is an example of the wanted art "
            "quality. Redraw the weapon of <image1> as a clean high-resolution painted game inventory item "
            "with the same rendering quality as <image2>: crisp clean edges, fine painted detail, smooth "
            "shading. The shape, the parts, the outline, the size, the proportions and the colours come only "
            "from <image1>: it stays exactly the same weapon in the same view, every part in the same place, "
            "nothing added and nothing removed. Do not copy the shape, the parts or the colours of <image2>. "
            "Not a photo, no pixels. Keep the flat background colour of <image1>, no shadow, no text.")
# --literal (Vitali 04.10: «дай 2511 только тот текст без эталонов») - его текст дословно, один вход
PROMPT_LIT = ("улучши эти 3 фотки сохранив размер и цвета оригинала ничего не придумывая и сохранив мелкие детали")
LIT_OUT = "art/items/weapons-edit-v2-literal"
PREV_A = "art/items/weapons-edit-v1/A"


def rows():
    with open(os.path.join(BATCH, "list.tsv"), encoding=ENC, newline="") as f:
        return [r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE) if r["master"] in ONLY]


def original(t):
    """Кадр оригинала: RGB, маска непрозрачного."""
    d = os.path.join(BATCH, "cards", "originals", t)
    im = Image.open(os.path.join(d, sorted(os.listdir(d))[0]))
    idx = np.asarray(im)
    pal = np.asarray(im.getpalette()[:768], np.uint8).reshape(-1, 3)
    return pal[idx].astype(np.float32), idx != 0


def bbox(m):
    ys, xs = np.nonzero(m)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def target_size(w, h, mp=MP, mult=32):
    s = (mp * 1e6 / float(w * h)) ** 0.5
    return max(mult, int(round(w * s / mult)) * mult), max(mult, int(round(h * s / mult)) * mult)


def panel_for(rgb, m):
    """Подложка, контрастная к предмету: тёмному - светлая, светлому - тёмная (R-157)."""
    return (205, 205, 205) if rgb[m].mean() < 110 else (52, 54, 60)


def make_input(t, rgb, m):
    """xBRZ x4 (weapons_sr) по габариту оригинала с полем, гладко до ~1 Мп, на подложке."""
    x0, y0, x1, y1 = bbox(m)
    pad = 3
    x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(m.shape[1], x1 + pad), min(m.shape[0], y1 + pad)
    xb = Image.open(os.path.join(BATCH, "sr", "xbrz", t + ".png")).convert("RGBA")
    k = xb.width // m.shape[1]
    crop = xb.crop((x0 * k, y0 * k, x1 * k, y1 * k))
    W, H = target_size(crop.width, crop.height)
    panel = panel_for(rgb, m)
    big = crop.resize((W, H), Image.LANCZOS)
    flat = Image.new("RGBA", (W, H), panel + (255,))
    flat.alpha_composite(big)
    return flat.convert("RGB"), panel, (x0, y0, x1, y1)


def object_mask(rgb, bg=None, thr=20.0):
    """Предмет на ровном фоне: расстояние до цвета фона (медиана края, если не задан), медиана 5,
    дыры внутри - всё, куда не дотекла заливка фона от края."""
    rgb = np.asarray(rgb, np.float32)
    h, w = rgb.shape[:2]
    if bg is None:
        e = 8
        edge = np.concatenate([rgb[:e].reshape(-1, 3), rgb[-e:].reshape(-1, 3),
                               rgb[:, :e].reshape(-1, 3), rgb[:, -e:].reshape(-1, 3)])
        bg = np.median(edge, 0)
    m = np.sqrt(((rgb - np.asarray(bg, np.float32)) ** 2).sum(2)) > thr
    m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5))) > 127
    inv = Image.fromarray(np.where(m, 0, 255).astype(np.uint8), "L").copy()
    for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (0, h // 2), (w - 1, h // 2), (w // 2, 0), (w // 2, h - 1)):
        if inv.getpixel(p) == 255:
            ImageDraw.floodfill(inv, p, 128)
    return np.asarray(inv) != 128, bg


def ref_image(name):
    """Эталон: предмет вырезан по фону (подписи сверху и снизу отрезаны), с полем, ~1 Мп."""
    os.makedirs(os.path.join(OUT, "ref"), exist_ok=True)
    out = os.path.join(OUT, "ref", name + ".png")
    if os.path.exists(out):
        return Image.open(out).convert("RGB")
    im = Image.open(REFS[name])
    if im.mode == "RGBA" and np.asarray(im)[..., 3].min() < 128:
        a = np.asarray(im)[..., 3] > 128
        rgb = np.asarray(im.convert("RGB"))
        bg = None
    else:
        rgb = np.asarray(im.convert("RGB"))
        h = rgb.shape[0]
        a, bg = object_mask(rgb)
        band = int(h * 0.05)
        a[:band] = False
        a[-band:] = False
    x0, y0, x1, y1 = bbox(a)
    pad = max(8, (x1 - x0) // 20)
    x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(rgb.shape[1], x1 + pad), min(rgb.shape[0], y1 + pad)
    crop = Image.fromarray(np.where(a[..., None], rgb, 128).astype(np.uint8)[y0:y1, x0:x1])
    W, H = target_size(crop.width, crop.height)
    crop = crop.resize((W, H), Image.LANCZOS)
    crop.save(out)
    return crop


def check(raw, panel, rgb, m):
    """Ответ против оригинала в масштабе оригинала: IoU силуэта, пропорции, цвет, яркость; маска ответа."""
    rm, _bg = object_mask(np.asarray(raw), bg=panel, thr=24.0)
    if not rm.any():
        return None, rm
    x0, y0, x1, y1 = bbox(rm)
    ox0, oy0, ox1, oy1 = bbox(m)
    ow, oh = ox1 - ox0, oy1 - oy0
    small = np.asarray(Image.fromarray(np.asarray(raw)[y0:y1, x0:x1]).resize((ow, oh), Image.BOX), np.float32)
    sm = np.asarray(Image.fromarray((rm[y0:y1, x0:x1] * 255).astype(np.uint8)).resize((ow, oh), Image.BOX)) > 127
    o = m[oy0:oy1, ox0:ox1]
    org = rgb[oy0:oy1, ox0:ox1]
    both = sm & o
    rep = {"iou": round(float((sm & o).sum() / max(1, (sm | o).sum())), 3),
           "aspect_pct": round(100 * (((x1 - x0) / (y1 - y0)) / (ow / oh) - 1), 1),
           "dcol": round(float(np.abs(small[both] - org[both]).mean()), 1) if both.any() else None,
           "lum": round(float(small[sm].mean()), 0) if sm.any() else None,
           "lum_orig": round(float(org[o].mean()), 0),
           "miss": int((o & ~sm).sum()), "extra": int((sm & ~o).sum()), "orig_px": int(o.sum())}
    return rep, rm


def view(raw, rm, size):
    """Ответ по маске на тёмном полу, по габариту предмета, вписан в size."""
    if raw is None or rm is None or not rm.any():
        return Image.new("RGB", size, (34, 36, 44))
    x0, y0, x1, y1 = bbox(rm)
    rgba = np.dstack([np.asarray(raw), (rm * 255).astype(np.uint8)])[y0:y1, x0:x1]
    im = Image.fromarray(rgba, "RGBA")
    s = min(size[0] / im.width, size[1] / im.height)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    tile = Image.new("RGBA", size, (34, 36, 44, 255))
    tile.alpha_composite(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    return tile.convert("RGB")


def sheets(items, cols=(("A", "A: только оригинал"), ("B", "B: + эталон")), ref_col=True):
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    CW, CH = 240, 400
    heads = ("оригинал", "вход (xBRZ)") + tuple(h for _v, h in cols) + (("эталон B",) if ref_col else ())
    for page in range(0, len(items), 5):
        sub = items[page:page + 5]
        out = Image.new("RGB", (len(heads) * (CW + 6) + 10, len(sub) * (CH + 52) + 30), (20, 22, 30))
        d = ImageDraw.Draw(out)
        for k, hname in enumerate(heads):
            d.text((10 + k * (CW + 6), 6), hname, fill=(200, 200, 210), font=font)
        for i, it in enumerate(sub):
            Y = 28 + i * (CH + 52)
            rgb, m = it["orig"]
            x0, y0, x1, y1 = bbox(m)
            oi = Image.fromarray(np.dstack([rgb, m * 255]).astype(np.uint8)[y0:y1, x0:x1], "RGBA")
            s = min(CW / oi.width, CH / oi.height)
            s = max(1, int(s))
            oi = oi.resize((oi.width * s, oi.height * s), Image.NEAREST)
            tile = Image.new("RGBA", (CW, CH), (34, 36, 44, 255))
            tile.alpha_composite(oi, ((CW - oi.width) // 2, (CH - oi.height) // 2))
            cells = [tile.convert("RGB"), view(it["input"], it["in_mask"], (CW, CH))] + [
                view(it.get(v), it.get(v + "_mask"), (CW, CH)) for v, _h in cols]
            if ref_col:
                r4 = it["ref"]
                s4 = min(CW / r4.width, CH / r4.height)
                c4 = Image.new("RGB", (CW, CH), (34, 36, 44))
                c4.paste(r4.resize((round(r4.width * s4), round(r4.height * s4)), Image.LANCZOS), (0, 0))
                cells.append(c4)
            for k, c in enumerate(cells):
                out.paste(c, (10 + k * (CW + 6), Y))
            r = it["row"]
            d.text((10, Y + CH + 4), "%s %s (%s)" % (r["master"], r["en"], r["type"]), fill=(225, 225, 235), font=font)
            for k, v in ((2 + j, v) for j, (v, _h) in enumerate(cols)):
                rep = it.get(v + "_rep")
                if rep:
                    d.text((10 + k * (CW + 6), Y + CH + 4), "IoU %.3f  ш/в %+.1f%%" % (rep["iou"], rep["aspect_pct"]),
                           fill=(225, 225, 235), font=font)
                    d.text((10 + k * (CW + 6), Y + CH + 22), "цвет %s  ярк %s/%s" % (rep["dcol"], rep["lum"], rep["lum_orig"]),
                           fill=(170, 170, 185), font=font)
        out.save(os.path.join(OUT, "sheet_%02d.png" % (page // 5 + 1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--models", default="")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--literal", action="store_true", help="только текст Vitali дословно, без эталонов")
    a = ap.parse_args()
    os.chdir(ROOT)
    global OUT
    if a.literal:
        OUT = LIT_OUT
        variants = (("L", PROMPT_LIT, False),)
        cols, ref_col = (("L", "текст Vitali дословно"), ("A", "A прошлый (v1)")), False
    else:
        variants = (("A", PROMPT_A, False), ("B", PROMPT_B, True))
        cols, ref_col = (("A", "A: только оригинал"), ("B", "B: + эталон")), True
    for sub in ("in",) + tuple(v for v, _p, _r in variants):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    items = []
    for r in rows():
        rgb, m = original(r["type"])
        inp, panel, box = make_input(r["type"], rgb, m)
        inp.save(os.path.join(OUT, "in", r["type"] + ".png"))
        refname = REF_OF_KIND.get(r["kind"], "autogun")
        it = {"row": r, "orig": (rgb, m), "input": inp, "panel": panel, "box": box, "refname": refname,
              "ref": ref_image(refname)}
        it["in_rep"], it["in_mask"] = check(inp, panel, rgb, m)
        prev = os.path.join(PREV_A, r["type"] + ".png")
        if a.literal and os.path.exists(prev):
            it["A"] = Image.open(prev).convert("RGB")
            it["A_rep"], it["A_mask"] = check(it["A"], panel, rgb, m)
        print("%s %s: вход %dx%d, подложка %s, эталон %s, вход против оригинала IoU %s" % (
            r["master"], r["type"], inp.width, inp.height, panel, refname,
            it["in_rep"] and it["in_rep"]["iou"]), flush=True)
        items.append(it)
    with open(os.path.join(OUT, "prompt.txt"), "w", encoding=ENC) as f:
        f.write("".join("%s:\n%s\n\n" % (v, p) for v, p, _r in variants))
    if a.dry_run:
        sheets(items, cols, ref_col)
        print("dry-run: модель не грузилась ->", OUT)
        return
    import gen_hd
    import item_photo as ip
    import torch
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    painter = ip.EditPainter(models)
    t0 = time.time()
    n, total = 0, len(variants) * len(items)
    for it in items:
        t = it["row"]["type"]
        for v, prompt, with_ref in variants:
            ims = [it["input"], it["ref"]] if with_ref else [it["input"]]
            ts = time.time()
            res = painter.pipe(prompt=prompt, image=ims, num_inference_steps=ip.EDIT_RUN["steps"],
                               generator=torch.Generator("cpu").manual_seed(a.seed),
                               true_cfg_scale=ip.EDIT_RUN["cfg"], width=it["input"].width, height=it["input"].height)
            raw = res.images[0].convert("RGB")
            raw.save(os.path.join(OUT, v, t + ".png"))
            it[v] = raw
            it[v + "_rep"], it[v + "_mask"] = check(raw, it["panel"], *it["orig"])
            n += 1
            print("[%d/%d] %s %s %s: %.0f с, %s" % (n, total, it["row"]["master"], t, v, time.time() - ts,
                                                    json.dumps(it[v + "_rep"], ensure_ascii=False)), flush=True)
    sheets(items, cols, ref_col)
    with open(os.path.join(OUT, "check.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["master", "type", "variant", "ref", "iou", "aspect_pct", "dcol", "lum", "lum_orig", "miss", "extra", "orig_px"])
        for it in items:
            for v, _p, _r in variants:
                rep = it.get(v + "_rep") or {}
                w.writerow([it["row"]["master"], it["row"]["type"], v, it["refname"] if v == "B" else ""] +
                           [rep.get(k) for k in ("iou", "aspect_pct", "dcol", "lum", "lum_orig", "miss", "extra", "orig_px")])
    meta = {"seed": a.seed, "run": ip.EDIT_RUN, "model_rev": ip.EDIT_MODEL_REV,
            "prompts": {v: p for v, p, _r in variants}, "refs": REFS, "ref_of_kind": REF_OF_KIND, "items": list(ONLY),
            "seconds": round(time.time() - t0), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(OUT, "meta.json"), "w", encoding=ENC) as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    if torch.cuda.is_available():
        print("пик памяти карты %.1f ГБ" % (torch.cuda.max_memory_allocated() / 2 ** 30), flush=True)
    print("готово за %.0f с -> %s" % (time.time() - t0, OUT), flush=True)


if __name__ == "__main__":
    main()
