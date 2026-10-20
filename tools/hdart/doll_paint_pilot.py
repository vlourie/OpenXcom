"""Пилот рисованной куклы бойца (после «фотки голимые» Vitali 20.10): не фото по слою, а рисунок целой куклы путём
strict, одобренным для предметов карты (DECISIONS 2026-09-27: Qwen-Image-2.1 из шума, оригинал - эскиз формы и
палитры, cfg 4, 40 шагов), и раскрой рисунка по маскам слоёв.

Почему так: фото Edit-2511 перерисовывало всю фигуру - другие волосы, другая кожа, другой контур; вырезка по маске
оригинала резала голову и оставляла серую кайму. Слой отдельно модель не видит в контексте, а кукла целиком
держит свет, кожу и складки одним рисунком.

Порядок:
  1. манекен каждой кожи (тело + голова) - рисунок strict; тело и голова вырезаются своими масками;
  2. каждая броня целиком (манекен первой кожи + все вещи) - рисунок strict; вещь берётся из рисунка в той части
     своей маски, где её видно; часть вещи под верхними вещами в этой броне не видна - там B2 этой вещи;
  3. каждый слой подгоняется по тону к своему классическому слою (match_tone, доля 0.7 - как у предметов);
  4. лист «классика x4 | B2 | рисунок» на трёх кожах, как у фото-пилота.
Альфа - только маска оригинала x4 (R-089), ответ не растягивается (R-208). Память карты - счётчиком Windows после
первого рисунка, shared > 0,5 ГБ - стоп (R-213).

Выход art/doll/paint_pilot/: layers/, raw/, sheet.png, run.json.
  py -3 tools/gpuq.py add --name doll-paint-pilot -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe \
      E:/OpenXCom/tools/hdart/doll_paint_pilot.py
  --dry-run - без модели (вместо рисунка - вход), проверка раскроя и листа.
"""
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")        # до импорта diffusers (R-145)
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")   # дробление памяти карты

import argparse                                     # noqa: E402
import json                                         # noqa: E402
import time                                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

import doll_b2_render as db                         # noqa: E402
import doll_photo_pilot as dp                       # noqa: E402
import wall_section as ws                           # noqa: E402

OUT = os.path.join(db.ROOT, "art", "doll", "paint_pilot")
RUN = {"steps": 40, "cfg": 4.0, "mp": 1.0, "seed": 2711, "tone": 0.7, "offload": "model"}

STRICT = ("<image1> is the low-resolution original paper-doll sprite of {what}, shown on a flat grey preview panel. "
          "The panel is interface, not part of the sprite. "
          "Use case: sketch-to-render. Asset type: polished 4x HD paper-doll portrait for the equipment screen of an "
          "X-COM-style strategy game, the whole figure seen straight from the front. "
          "Redraw this same figure as detailed hand-painted game artwork: {what}. Keep the pose, the position, the "
          "size, the silhouette and the palette of <image1>: the same skin colour, the same hair colour, length and "
          "cut, the same colours of every item, even if they are unusual. Clear readable shapes, crisp edges, fine "
          "painted detail, soft light from the upper left. "
          "Output one isolated figure on the same flat panel. No ground, no shadow, no other objects, no frame, "
          "no text.")
NEGATIVE = ("pixel art, pixelated, blocky, jagged stair-stepped edges, dithering, blurry, smudged, blob, noise, "
            "low detail, ground, floor, panel frame, border, drop shadow, text, watermark, photo, photograph, "
            "nude, nipples")
MANNEQUIN = ("a strong athletic young woman standing front-facing with her arms slightly away from the body, "
             "wearing only plain black underwear - a bra and briefs")
ARMOR_WHAT = {
    "STR_ADVENTURER_OUTFIT_UC": "a strong athletic young woman in adventurer's gear: a dark cropped top, black "
                                "high-cut briefs, a diagonal shoulder belt, a loaded belt with pouches, a knife "
                                "scabbard on the hip, fingerless gloves and tall black boots",
    "STR_AMAZON_ARMOR_UC": "a strong athletic young woman in tribal amazon armour: a small brown suede bikini top, "
                           "a loincloth on a cord, leather bracers and greaves with pale fur trim, a sash across "
                           "the chest with a round metal badge and a strap round the thigh",
}


class Painter:
    def __init__(self, models):
        import gen_hd
        import gen_fire
        ns = argparse.Namespace(models=models, qwen21_model="", qwen21_steps=RUN["steps"], qwen21_cfg=RUN["cfg"],
                                qwen21_mp=RUN["mp"], qwen21_strength=0.0, qwen21_offload=RUN["offload"],
                                qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                                qwen21_hint="off", qwen21_ref_order="ref-first")
        self.p = gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
        gen_fire.NEGATIVE = NEGATIVE                # run_pass берёт негатив из модуля gen_fire
        self.gf = gen_fire
        self.args = argparse.Namespace(steps=RUN["steps"], cfg=RUN["cfg"], mp=RUN["mp"])
        self.first = True

    def paint(self, img, what, seed):
        rgb = img.convert("RGB")
        out = self.gf.run_pass(self.p, self.args, STRICT.format(what=what), rgb, seed)
        if self.first:
            dp.gpu_mem("первый рисунок")
            self.first = False
        import gc
        gc.collect()
        self.p.torch.cuda.empty_cache()         # 4-й рисунок 20.10 упал по нехватке памяти карты
        return np.array(out.convert("RGB").resize(rgb.size, Image.LANCZOS))


def tone(layer4, files, pal, name):
    """Тон слоя - к его классическому слою (как предметы: среднее и разброс каналов, доля RUN['tone'])."""
    import probe_object as po
    return po.match_tone(layer4, dp.classic(files, pal, [name]), RUN["tone"])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default=os.environ.get("HD_MODELS", "E:\\models"))
    ap.add_argument("--looks", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redraw", action="store_true", help="рисовать заново и то, что уже есть в raw/")
    ns = ap.parse_args()
    for d in ("layers", "raw"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    files, pal, arms = db.sprite_files(), db.game_palette(), db.armor_layers()
    keys = [k for k in arms[dp.ARMORS[0]] if all(k in arms[a] for a in dp.ARMORS)]
    looks = ns.looks.split(",") if ns.looks else dp.pick_looks(files, keys)
    outfits = {a: {k: [n for n in arms[a][k] if n] for k in looks} for a in dp.ARMORS}
    painter = None if ns.dry_run else Painter(ns.models)
    run = {"race": dp.RACE, "armors": dp.ARMORS, "looks": looks, "engine": RUN, "dry_run": ns.dry_run,
           "prompt": STRICT, "negative": NEGATIVE, "layers": {}}
    photo, t0 = {}, time.time()

    def draw(tag, inp, what, seed):
        inp.convert("RGB").save(os.path.join(OUT, "raw", tag + "_in.png"))
        if painter is None:
            return np.asarray(inp.convert("RGB"))
        done = os.path.join(OUT, "raw", tag + "_out.png")
        if os.path.exists(done) and not ns.redraw:
            return np.asarray(Image.open(done).convert("RGB"))
        t = time.time()
        rgb = painter.paint(inp, what, seed)
        Image.fromarray(rgb).save(done)
        print("  %s: %.0f с" % (tag, time.time() - t), flush=True)
        return rgb

    def keep(n, im, how):
        photo[n] = tone(im, files, pal, n)
        photo[n].save(os.path.join(OUT, "layers", n.lower() + ".png"))
        run["layers"][n] = how

    # 1. манекены
    for i, look in enumerate(looks):
        body = "%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look)
        head = "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look)
        rgb = draw("mannequin_" + look, dp.crop8(dp.classic(files, pal, [body, head])), MANNEQUIN, RUN["seed"] + i)
        for n in (body, head):
            im, frac = dp.cut(rgb, dp.layer_mask(files, n))
            keep(n, im, {"from": "mannequin_" + look, "panel_inside": frac})
        print("манекен %s (%d/%d), %.0f с" % (look, i + 1, len(looks), time.time() - t0), flush=True)

    # 2. брони целиком на первой коже, раскрой по маскам
    base = looks[0]
    for arm in dp.ARMORS:
        names = outfits[arm][base]
        rgb = draw(arm, dp.crop8(dp.classic(files, pal, names)), ARMOR_WHAT[arm], RUN["seed"] + 100)
        masks = [dp.layer_mask(files, n) for n in names]
        for j, n in enumerate(names):
            if n in photo:
                continue
            above = np.zeros_like(masks[j])
            for m in masks[j + 1:]:
                above |= m
            im, frac = dp.cut(rgb, masks[j])
            hid = ws.sil4(masks[j] & above) > 0.5
            b2, how = dp.b2_layer(n)
            if b2 is not None and hid.any():
                a = np.asarray(im).copy()
                a[hid, :3] = np.asarray(b2)[hid, :3]
                im = Image.fromarray(a, "RGBA")
            keep(n, im, {"from": arm, "panel_inside": frac, "hidden_px_from_b2": int(hid.sum()), "b2": how})
        print("%s: %d слоёв, %.0f с" % (arm, len(names), time.time() - t0), flush=True)

    dp.OUT = OUT                                    # лист фото-пилота пишет в свою папку
    path, b2m = dp.sheet(files, pal, looks, outfits, photo)
    run["sheet"], run["seconds"] = path, round(time.time() - t0)
    with open(os.path.join(OUT, "run.json"), "w", encoding=db.ENC) as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    print("лист:", path, "за %.0f с" % (time.time() - t0))


if __name__ == "__main__":
    main()
