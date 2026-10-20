"""Пилот фото куклы бойца (вариант C отчёта docs/research/doll-hd-2026-10-20.md): слои куклы UBERGAL - фото,
нарисованные вокруг одного HD-манекена расы. Вариант для мода hd - прикрытый (простое бельё), 18+ - только со слова
Vitali.

Порядок:
  1. манекен на трёх кожах: тело (слой 2, *_NUDE) + голова (слой 10) внешности -> Edit-2511 -> фото; тело и голова
     вырезаются каждое своей маской оригинала;
  2. одежда двух броней (ADVENTURER и AMAZON) слой за слоем по номеру: на вход - фото того, что уже лежит под слоем
     (манекен первой кожи и нижние вещи), сверху классический слой xBRZ; модель делает фото только этой вещи, из ответа
     берётся только маска слоя. Голова в контекст одежды не идёт: волосы у внешностей разной длины, и одежда под
     волосами одной внешности вышла бы цвета волос у другой;
  3. сборка куклы в порядке слоёв, как в игре, на всех трёх кожах (одежда снята на первой - это и есть проверка);
     лист «классика x4 | B2 | фото».

Геометрия - закон: ответ модели не растягивается (R-208), альфа - только маска оригинала x4 (R-089), подложку
внутри силуэта снимает unit_parts.panel_matte - кадр тоньше оригинала, но не шире (R-212). Части называются по
положению на картинке (R-212).

Выход: art/doll/photo_pilot/ - layers/<имя>.png (холст 1280x800, k=4, как у B2), raw/ (вход и ответ модели x8),
sheet.png, run.json (промпты, сиды, ревизия модели, доля подложки внутри силуэта по слоям).

  py -3 tools/gpuq.py add --name doll-photo-pilot -- <venv python> tools/hdart/doll_photo_pilot.py
  --dry-run - только входы и лист из классики, без модели (для проверки на процессоре).
"""
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")        # до импорта diffusers (R-145)

import argparse                                     # noqa: E402
import json                                         # noqa: E402
import time                                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

import doll_b2_render as db                         # noqa: E402
import unit_parts as upa                            # noqa: E402
import wall_section as ws                           # noqa: E402

ROOT = db.ROOT
OUT = os.path.join(ROOT, "art", "doll", "photo_pilot")
B2 = os.path.join(ROOT, "art", "doll", "b2")
RACE = "UBERGAL"
ARMORS = ("STR_ADVENTURER_OUTFIT_UC", "STR_AMAZON_ARMOR_UC")
CROP = (40, 32, 120, 160)       # тело куклы на холсте 320x200 (рамка тел UBERGAL 49..109 x 39..148 с полем)
Z = 8                           # увеличение входа модели: 80x128 -> 640x1024
K = db.K                        # итог - k=4, холст 1280x800
PANEL = upa.PANEL
EDIT_REV = "6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9"   # тот же снимок, что у item_photo (R-145)
RUN = {"steps": 8, "cfg": 1.0, "seed": 20261020}
BODY, HEAD = 2, 10

LIGHT = ("Front view, the camera straight in front of her at chest height, no perspective tilt. Even soft studio "
         "light from the front and slightly above, a soft shadow under the chin and the chest, no rim light, "
         "no coloured light.")
PANEL_TXT = ("The flat plain panel of colour RGB(%d, %d, %d) around her stays exactly as it is: no floor, no shadow "
             "on it, no other objects, no frame, no text." % PANEL)
KEEP = ("Keep exactly the pose, the outline, the size and the position of the whole figure as in <image1>: the arms, "
        "the hands, the legs and the feet stay where they are and as thick as they are; do not move, bend, shorten, "
        "lengthen, thin or crop anything.")
MANNEQUIN = ("<image1> is a pixel-art paper doll of a strong athletic young woman standing front-facing with her arms "
             "slightly away from the body. Turn it into a real studio photograph of the same woman: real skin with "
             "pores and natural tone in the same skin colour family as the drawing, real hair of the same colour, "
             "length and cut as drawn, the same face. She wears simple plain black seamless underwear - a bra and "
             "briefs - and nothing else, no jewellery, no weapons. " + KEEP + " " + LIGHT + " " + PANEL_TXT)
CLOTH = ("<image1> is a studio photograph of a woman; one item on her is still drawn as pixel art: {what}. Turn that "
         "item into the real photographed thing worn by her, made of {mat}, with real seams, folds and wear, in the "
         "same colours as drawn. Keep the item exactly the outline, the size and the position it has in <image1>. "
         "Everything else - her body, the skin, the underwear and the other clothes - stays exactly as it is in "
         "<image1>. " + KEEP + " " + LIGHT + " " + PANEL_TXT)
NEGATIVE = ("anime, cartoon, illustration, drawing, painting, pixel art, cel shading, outlines, lowres, blurry, "
            "deformed, extra limbs, extra fingers, nude, nipples, text, watermark, logo")
# вещь -> (что это и где на картинке, материал); слева/справа - по картинке (R-212)
WHAT = {
    "PANTIES_HCUT_BLACK": ("black high-cut thong briefs on her hips", "thin black stretch fabric"),
    "SCABBARD_LH": ("a short knife scabbard hanging on the hip at the right side of the picture",
                    "dark leather with a red cord"),
    "GANGER_TOP": ("a short dark cropped top over her chest", "dark grey worn cotton"),
    "FINGERLESS_GLOVES": ("fingerless gloves on both hands", "black leather"),
    "ADVENTURER_MAIN": ("an adventurer's gear: a diagonal shoulder belt from the shoulder at the right side of the "
                        "picture across the chest to the hip, a loaded belt with pouches round the hips, a strap down "
                        "the thigh at the left side of the picture, and tall black boots",
                        "black leather, webbing and steel buckles"),
    "AMAZON_TOP": ("a small triangle bikini top with thin straps", "brown suede"),
    "TRIBAL_STRAP_RL": ("a narrow strap round the thigh at the left side of the picture", "brown rawhide"),
    "AMAZON_ARMOR": ("bracers on both forearms, a few leather strips on the shoulder at the right side of the picture, "
                     "and greaves on both shins", "hardened brown leather with pale fur trim"),
    "TRIBAL_LOINCLOTH": ("a small loincloth hanging from a cord round the hips", "brown suede with bone beads"),
    "AMAZON_SASH": ("a sash from the shoulder at the right side of the picture down across the chest, with a round "
                    "badge at the shoulder", "brown leather with a grey metal badge"),
}


def layer_mask(files, name):
    return db.load_indices(files[name]) != 0


def crop8(img):
    """Холст 320x200 (RGBA, k=1) -> вход модели: рамка CROP, xBRZ x4 и вдвое LANCZOS, на подложке."""
    part = img.crop(CROP)
    up = ws.xbrz(part, 4)
    up = up.resize((part.width * Z, part.height * Z), Image.LANCZOS)
    bg = Image.new("RGBA", up.size, PANEL + (255,))
    bg.alpha_composite(up)
    return bg


def classic(files, pal, names):
    """Слои по порядку -> холст 320x200 RGBA (k=1), как blitNShade без тона."""
    out = Image.new("RGBA", (db.W, db.H), (0, 0, 0, 0))
    for n in names:
        out.alpha_composite(Image.fromarray(db.to_rgba(db.load_indices(files[n]), pal), "RGBA"))
    return out


def cut(rgb8, mask):
    """Ответ модели x8 (рамка CROP) + маска слоя 320x200 -> слой k=4 на холсте 1280x800 RGBA и доля подложки
    внутри силуэта. Ответ только уменьшается, не растягивается (R-208)."""
    sil = ws.sil4(mask)                                       # 800x1280, 0..1
    x0, y0, x1, y1 = (v * K for v in CROP)
    rgb4 = np.asarray(Image.fromarray(rgb8).resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32)
    s = sil[y0:y1, x0:x1]
    matte = upa.panel_matte(rgb4, s)
    a = s * (1.0 - matte)
    rgb4 = upa.edge_fill(rgb4, a)
    inside = s > 0.5
    frac = float((matte[inside] > 0.5).mean()) if inside.any() else 0.0
    out = np.zeros((db.H * K, db.W * K, 4), np.float32)
    out[y0:y1, x0:x1, :3] = rgb4
    out[y0:y1, x0:x1, 3] = a * 255
    lost = float(sil.sum() - s.sum())
    assert lost < 1.0, "силуэт слоя выходит за рамку CROP на %.0f пикселей" % lost
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA"), round(frac, 4)


def to8(layer4):
    """Слой k=4 на холсте -> рамка CROP x8 (для контекста следующего слоя)."""
    x0, y0, x1, y1 = (v * K for v in CROP)
    return layer4.crop((x0, y0, x1, y1)).resize(((x1 - x0) * Z // K, (y1 - y0) * Z // K), Image.LANCZOS)


def pick_looks(files, keys, n=3):
    """Внешности с самой светлой, средней и тёмной кожей: средняя яркость тела ниже головы."""
    pal = db.game_palette()
    lum = []
    for k in keys:
        nm = "%s__%d__%s_NUDE" % (RACE, BODY, k)
        if nm not in files or "%s__%d__HEAD_%s" % (RACE, HEAD, k) not in files:
            continue
        idx = db.load_indices(files[nm])[80:140]
        m = idx != 0
        lum.append((float(pal[idx][m].mean()), k))
    lum.sort()
    return [lum[-1][1], lum[len(lum) // 2][1], lum[0][1]][:n]


class Model:
    def __init__(self, models):
        self.models, self.p = models, None

    def edit(self, img, prompt, seed):
        if self.p is None:
            import photo_ui as pu
            ref = os.path.join(self.models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "refs", "main")
            got = open(ref).read().strip() if os.path.exists(ref) else ""
            if got != EDIT_REV:
                raise SystemExit("Edit-2511 в кэше %s, ждал %s - не рисую (R-145)" % (got or "нет", EDIT_REV))
            pu.MODEL = os.path.join(self.models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", EDIT_REV)
            self.p = pu.Painter(self.models, fast=True, steps=RUN["steps"], photoreal=False)
        rgb = img.convert("RGB")
        return self.p.edit([rgb], prompt, NEGATIVE, seed, RUN["steps"], RUN["cfg"], rgb.width, rgb.height)


def save_layer(name, im):
    im.save(os.path.join(OUT, "layers", name.lower() + ".png"))


def b2_layer(name):
    for m in ("esrgan", "xbrz"):
        p = os.path.join(B2, m, name.lower() + ".png")
        if os.path.exists(p):
            return Image.open(p).convert("RGBA"), m
    return None, None


def compose(layers):
    out = Image.new("RGBA", (db.W * K, db.H * K), (0, 0, 0, 0))
    for im in layers:
        out.alpha_composite(im)
    return out


def sheet(files, pal, looks, outfits, photo):
    """Ряды - брони, на каждой три кожи; в ряду по коже: классика x4 | B2 | фото."""
    x0, y0, x1, y1 = (v * K for v in CROP)
    tw, th = x1 - x0, y1 - y0
    rows = []
    b2m = set()
    for arm in ARMORS:
        tiles = []
        for look in looks:
            names = outfits[arm][look]
            cl = classic(files, pal, names).resize((db.W * K, db.H * K), Image.NEAREST)
            b2s = []
            for n in names:
                im, m = b2_layer(n)
                if im is not None:
                    b2s.append(im)
                    b2m.add(m)
            ph = [photo[n] for n in names if n in photo]
            for im in (cl, compose(b2s), compose(ph)):
                bg = Image.new("RGBA", (tw, th), (40, 42, 50, 255))
                bg.alpha_composite(im.crop((x0, y0, x1, y1)))
                tiles.append(bg.convert("RGB"))
        rows.append(tiles)
    cols = max(len(r) for r in rows)
    out = Image.new("RGB", (cols * tw, len(rows) * th), (0, 0, 0))
    for j, r in enumerate(rows):
        for i, t in enumerate(r):
            out.paste(t, (i * tw, j * th))
    path = os.path.join(OUT, "sheet.png")
    out.save(path)
    return path, sorted(b2m)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default=os.environ.get("HD_MODELS", "E:\\models"))
    ap.add_argument("--looks", default="", help="внешности через запятую (по умолчанию светлая, средняя, тёмная)")
    ap.add_argument("--dry-run", action="store_true", help="только входы x8 и лист, без модели")
    ns = ap.parse_args()
    for d in ("layers", "raw"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    files = db.sprite_files()
    pal = db.game_palette()
    arms = db.armor_layers()
    keys = [k for k in arms[ARMORS[0]] if all(k in arms[a] for a in ARMORS)]
    looks = ns.looks.split(",") if ns.looks else pick_looks(files, keys)
    outfits = {a: {k: [n for n in arms[a][k] if n] for k in looks} for a in ARMORS}
    model = None if ns.dry_run else Model(ns.models)
    run = {"race": RACE, "armors": ARMORS, "looks": looks, "crop": CROP, "zoom": Z, "engine": RUN,
           "model_rev": EDIT_REV, "panel": PANEL, "dry_run": ns.dry_run, "layers": {}}
    photo = {}
    t0 = time.time()

    def step(tag, inp, prompt, seed):
        inp.convert("RGB").save(os.path.join(OUT, "raw", tag + "_in.png"))
        if model is None:
            return np.asarray(inp.convert("RGB"))
        t = time.time()
        rgb = model.edit(inp, prompt, seed)
        Image.fromarray(rgb).save(os.path.join(OUT, "raw", tag + "_out.png"))
        print("  %s: %.0f с" % (tag, time.time() - t), flush=True)
        return rgb

    # 1. манекен на трёх кожах
    for i, look in enumerate(looks):
        body = "%s__%d__%s_NUDE" % (RACE, BODY, look)
        head = "%s__%d__HEAD_%s" % (RACE, HEAD, look)
        rgb = step("mannequin_" + look, crop8(classic(files, pal, [body, head])), MANNEQUIN, RUN["seed"] + i)
        for n in (body, head):
            photo[n], frac = cut(rgb, layer_mask(files, n))
            save_layer(n, photo[n])
            run["layers"][n] = {"panel_inside": frac, "prompt": "mannequin"}
        print("манекен %s готов (%d/%d), %.0f с с начала" % (look, i + 1, len(looks), time.time() - t0), flush=True)

    # 2. одежда двух броней на первой коже, снизу вверх
    base_look = looks[0]
    for arm in ARMORS:
        names = outfits[arm][base_look]
        under = [n for n in names if n in photo and not n.endswith("HEAD_" + base_look)]
        for j, n in enumerate(names):
            if n in photo:
                continue
            item = n.split("__", 2)[2]
            what, mat = WHAT[item]
            ctx = Image.new("RGBA", to8(photo[under[0]]).size, PANEL + (255,))
            for u in under:
                ctx.alpha_composite(to8(photo[u]))
            top = crop8(classic(files, pal, [n]))
            m8 = np.asarray(ws.xbrz(Image.fromarray((layer_mask(files, n) * 255).astype(np.uint8)).convert("RGBA")
                                    .crop(CROP), 4).resize(ctx.size, Image.LANCZOS))[..., 0] > 127
            arr = np.asarray(ctx).copy()
            arr[m8] = np.asarray(top)[m8]
            prompt = CLOTH.format(what=what, mat=mat)
            rgb = step("%s_%s" % (arm, item), Image.fromarray(arr, "RGBA"), prompt, RUN["seed"] + 100 + j)
            photo[n], frac = cut(rgb, layer_mask(files, n))
            save_layer(n, photo[n])
            run["layers"][n] = {"panel_inside": frac, "prompt": prompt}
            under.append(n)
            print("%s: %s готов, %.0f с с начала" % (arm, item, time.time() - t0), flush=True)

    path, b2m = sheet(files, pal, looks, outfits, photo)
    run["sheet"], run["b2_method"], run["seconds"] = path, b2m, round(time.time() - t0)
    with open(os.path.join(OUT, "run.json"), "w", encoding=db.ENC) as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    print("лист:", path, "B2:", ",".join(b2m) or "нет", "за %.0f с" % (time.time() - t0))


if __name__ == "__main__":
    main()
