"""Пилот куклы бойца «по контуру» (Vitali 20.10: «она должна быть абсолютно одинакового размера - это эталон»).

Рисунок strict (doll_paint_pilot) держал форму только словами - фигура вышла стройнее классики, раскрой по маскам
развалился. Здесь форму держит механика, а не промпт:
  - Qwen-Image-2.1 + Fun-Controlnet-Union (tools/hdart/vx_control.py): карта контроля - серое (объём, тени и
    раскладка частей) классической куклы x8, control_context_scale 1.0;
  - маска силуэта классики (белое - рисовать, чёрное - не трогать) и сама кукла B2 на подложке как вход inpaint:
    за силуэтом модели рисовать нечего;
  - альфа итога - ровно силуэт классики x4 (ws.sil4), не ответ модели: контур совпадает с эталоном по построению;
    где модель внутри силуэта оставила подложку, ставится B2 (доля пишется в run.json).
Два итога каждого слоя:
  A - цвет модели, тон подогнан к классическому слою (match_tone 0.7);
  B - цвет классики (B2), от рисунка только мелкий рисунок яркости: Y = Y_рис - blur(Y_рис) + blur(Y_B2), CbCr - B2.
Слои: тело и голова - с манекена своей кожи, вещи - с рисунка брони целиком на первой коже; часть вещи под верхними
вещами в этой броне не видна - там B2. Память карты - счётчиком Windows после первого рисунка (R-213).

Выход art/doll/ctl_pilot/: raw/, layers_a/, layers_b/, sheet.png («классика x4 | B2 | A | B» на трёх кожах),
run.json.
  py -3 tools/gpuq.py add --name doll-ctl-pilot -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe \
      E:/OpenXCom/tools/hdart/doll_ctl_pilot.py
  --dry-run - без модели (рисунок = вход B2), проверка раскроя и листа.
"""
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")        # до импорта diffusers (R-145)
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import argparse                                     # noqa: E402
import json                                         # noqa: E402
import time                                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageFilter                  # noqa: E402

import doll_b2_render as db                         # noqa: E402
import doll_photo_pilot as dp                       # noqa: E402
import doll_paint_pilot as pp                       # noqa: E402
import unit_parts as upa                            # noqa: E402
import wall_section as ws                           # noqa: E402

OUT = os.path.join(db.ROOT, "art", "doll", "ctl_pilot")
RUN = {"steps": 40, "cfg": 4.0, "control": "gray", "control_scale": 1.0, "seed": 2711, "tone": 0.7,
       "detail_sigma4": 3.0}
PROMPT = ("Detailed hand-painted game artwork of {what}, a full-figure paper-doll portrait for the equipment screen "
          "of an X-COM-style strategy game, seen straight from the front, on a flat grey panel. Clear readable "
          "shapes, crisp edges, fine painted detail: skin, muscles, fabric folds, leather, seams, buckles, a "
          "detailed face. Soft light from the upper left. No ground, no shadow, no frame, no text.")


class Painter:
    def __init__(self):
        import vx_control as vc
        self.vc = vc
        self.p = vc.ControlPainter("model")
        self.first = True

    def paint(self, b2_8, classic_crop, mask8, what, seed):
        torch = self.p.torch
        W, H = b2_8.size
        ctl = self.vc.control_map(classic_crop, dp.Z, RUN["control"]).resize((W, H), Image.LANCZOS)
        c = np.asarray(ctl.convert("RGB"))
        t = torch.from_numpy(c.copy()).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        out = self.p.pipe(PROMPT.format(what=what), image=b2_8.convert("RGB"), mask_image=mask8,
                          control_image=t, negative_prompt=pp.NEGATIVE, height=H, width=W,
                          generator=torch.Generator("cuda").manual_seed(seed), true_cfg_scale=RUN["cfg"],
                          num_inference_steps=RUN["steps"], control_context_scale=RUN["control_scale"],
                          use_kv_cache=True).images[0]
        if self.first:
            dp.gpu_mem("первый рисунок")
            self.first = False
        import gc
        gc.collect()
        torch.cuda.empty_cache()
        bg = Image.new("RGBA", out.size, dp.PANEL + (255,))
        bg.alpha_composite(out.convert("RGBA"))
        return np.array(bg.convert("RGB").resize((W, H), Image.LANCZOS)), ctl


def b2_canvas(names):
    """B2 слоёв по порядку -> холст k=4 RGBA (нет B2 у слоя - классика NEAREST)."""
    out = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), (0, 0, 0, 0))
    for n in names:
        im, _m = dp.b2_layer(n)
        out.alpha_composite(im if im is not None else
                            dp.classic(FILES, PAL, [n]).resize(out.size, Image.NEAREST))
    return out


def inputs(names):
    """-> (B2 куклы x8 на подложке, классика k=1 рамки CROP, маска силуэта x8 L)."""
    b2 = b2_canvas(names)
    x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
    size = ((x1 - x0) * dp.Z // dp.K, (y1 - y0) * dp.Z // dp.K)
    b2_8 = Image.new("RGBA", size, dp.PANEL + (255,))
    b2_8.alpha_composite(b2.crop((x0, y0, x1, y1)).resize(size, Image.LANCZOS))
    cl = dp.classic(FILES, PAL, names)
    sil = np.zeros((db.H, db.W), bool)
    for n in names:
        sil |= dp.layer_mask(FILES, n)
    s4 = ws.sil4(sil)[y0:y1, x0:x1]
    m8 = Image.fromarray((s4 > 0.5).astype(np.uint8) * 255).resize(size, Image.NEAREST)
    return b2_8, b2, cl.crop(dp.CROP), m8


def cut(rgb8, mask, b2):
    """Ответ x8 -> слой k=4: альфа - силуэт слоя классики x4 ровно; подложка внутри силуэта -> B2."""
    sil = ws.sil4(mask)
    x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
    rgb4 = np.asarray(Image.fromarray(rgb8).resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32)
    s = sil[y0:y1, x0:x1]
    matte = upa.panel_matte(rgb4, s)
    hole = (matte > 0.5) & (s > 0.5)
    b = np.asarray(b2, np.float32)[y0:y1, x0:x1, :3]
    rgb4[hole] = b[hole]
    out = np.zeros((db.H * dp.K, db.W * dp.K, 4), np.float32)
    out[y0:y1, x0:x1, :3] = rgb4
    out[..., 3] = sil * 255
    inside = s > 0.5
    frac = float(hole[inside].mean()) if inside.any() else 0.0
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA"), round(frac, 4)


def on_classic_colour(layer, b2):
    """B: цвет B2, от рисунка - только мелкий рисунок яркости."""
    a = np.asarray(layer.convert("RGBA"))
    p = np.asarray(Image.fromarray(a[..., :3]).convert("YCbCr"), np.float32)
    q = np.asarray(Image.fromarray(np.asarray(b2)[..., :3]).convert("YCbCr"), np.float32)
    al = (a[..., 3:4] / 255.0).astype(np.float32)

    def blur(y):
        num = np.asarray(Image.fromarray(np.clip(y * al[..., 0], 0, 255).astype(np.uint8))
                         .filter(ImageFilter.GaussianBlur(RUN["detail_sigma4"])), np.float32)
        den = np.asarray(Image.fromarray((al[..., 0] * 255).astype(np.uint8))
                         .filter(ImageFilter.GaussianBlur(RUN["detail_sigma4"])), np.float32) / 255.0
        return num / np.maximum(den, 1e-3)

    y = p[..., 0] - blur(p[..., 0]) + blur(q[..., 0])
    ycc = np.dstack([np.clip(y, 0, 255), q[..., 1], q[..., 2]]).astype(np.uint8)
    rgb = np.asarray(Image.fromarray(ycc, "YCbCr").convert("RGB"))
    return Image.fromarray(np.dstack([rgb, a[..., 3]]), "RGBA")


def sheet(looks, outfits, la, lb):
    x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
    tw, th = x1 - x0, y1 - y0
    rows = []
    for arm in dp.ARMORS:
        tiles = []
        for look in looks:
            names = outfits[arm][look]
            cl = dp.classic(FILES, PAL, names).resize((db.W * dp.K, db.H * dp.K), Image.NEAREST)
            for im in (cl, b2_canvas(names), dp.compose([la[n] for n in names if n in la]),
                       dp.compose([lb[n] for n in names if n in lb])):
                bg = Image.new("RGBA", (tw, th), (40, 42, 50, 255))
                bg.alpha_composite(im.crop((x0, y0, x1, y1)))
                tiles.append(bg.convert("RGB"))
        rows.append(tiles)
    out = Image.new("RGB", (max(len(r) for r in rows) * tw, len(rows) * th))
    for j, r in enumerate(rows):
        for i, t in enumerate(r):
            out.paste(t, (i * tw, j * th))
    path = os.path.join(OUT, "sheet.png")
    out.save(path)
    return path


FILES = PAL = None


def main():
    global FILES, PAL
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--looks", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redraw", action="store_true", help="рисовать заново и то, что уже есть в raw/")
    ap.add_argument("--only", default="", help="(служебное) нарисовать один рисунок с этой меткой и выйти")
    ns = ap.parse_args()
    for d in ("raw", "layers_a", "layers_b"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    FILES, PAL = db.sprite_files(), db.game_palette()
    arms = db.armor_layers()
    keys = [k for k in arms[dp.ARMORS[0]] if all(k in arms[a] for a in dp.ARMORS)]
    looks = ns.looks.split(",") if ns.looks else dp.pick_looks(FILES, keys)
    outfits = {a: {k: [n for n in arms[a][k] if n] for k in looks} for a in dp.ARMORS}
    painter = Painter() if ns.only else None
    run = {"race": dp.RACE, "armors": dp.ARMORS, "looks": looks, "engine": RUN, "dry_run": ns.dry_run,
           "prompt": PROMPT, "negative": pp.NEGATIVE, "layers": {}, "renders": {}}
    la, lb, t0 = {}, {}, time.time()

    def draw(tag, names, what, seed):
        b2_8, b2, cl, m8 = inputs(names)
        b2_8.convert("RGB").save(os.path.join(OUT, "raw", tag + "_in.png"))
        m8.save(os.path.join(OUT, "raw", tag + "_mask.png"))
        done = os.path.join(OUT, "raw", tag + "_out.png")
        if ns.dry_run:
            return np.asarray(b2_8.convert("RGB")), b2
        if ns.only and tag != ns.only:
            return None, b2
        if not ns.only:
            if not os.path.exists(done) or ns.redraw:
                # каждый рисунок - свой процесс: второй рисунок в одном процессе дважды падал по памяти карты
                # (20.10, #750 и #751), процесс отдаёт всю память при выходе
                import subprocess
                subprocess.run([sys.executable, os.path.abspath(__file__), "--only", tag], check=True)
            rp = os.path.join(OUT, "raw", tag + "_render.json")
            if os.path.exists(rp):
                with open(rp, encoding=db.ENC) as f:
                    run["renders"][tag] = json.load(f)
            return np.asarray(Image.open(done).convert("RGB")), b2
        t = time.time()
        rgb, ctl = painter.paint(b2_8, cl, m8, what, seed)
        Image.fromarray(rgb).save(done)
        ctl.save(os.path.join(OUT, "raw", tag + "_ctl.png"))
        # насколько модель заполнила силуэт сама (до подстановки B2)
        m = np.asarray(m8) > 127
        pm = upa.panel_matte(rgb.astype(np.float32), m.astype(np.float32)) > 0.5
        info = {"seconds": round(time.time() - t), "panel_inside_silhouette": round(float(pm[m].mean()), 4)}
        with open(os.path.join(OUT, "raw", tag + "_render.json"), "w", encoding=db.ENC) as f:
            json.dump(info, f)
        print("  %s: %.0f с, подложка внутри силуэта %.1f %%" % (tag, time.time() - t, 100 * pm[m].mean()), flush=True)
        sys.exit(0)

    def keep(n, im, b2, how):
        bl, _m = dp.b2_layer(n)
        bl = bl if bl is not None else dp.classic(FILES, PAL, [n]).resize(im.size, Image.NEAREST)
        la[n] = pp.tone(im, FILES, PAL, n)
        lb[n] = on_classic_colour(im, bl)
        la[n].save(os.path.join(OUT, "layers_a", n.lower() + ".png"))
        lb[n].save(os.path.join(OUT, "layers_b", n.lower() + ".png"))
        run["layers"][n] = how

    for i, look in enumerate(looks):
        names = ["%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look), "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look)]
        rgb, b2 = draw("mannequin_" + look, names, pp.MANNEQUIN, RUN["seed"] + i)
        if rgb is None:
            continue
        for n in names:
            im, frac = cut(rgb, dp.layer_mask(FILES, n), b2)
            keep(n, im, b2, {"from": "mannequin_" + look, "b2_holes": frac})
        print("манекен %s (%d/%d), %.0f с" % (look, i + 1, len(looks), time.time() - t0), flush=True)

    base = looks[0]
    for arm in dp.ARMORS:
        names = outfits[arm][base]
        rgb, b2 = draw(arm, names, pp.ARMOR_WHAT[arm], RUN["seed"] + 100)
        if rgb is None:
            continue
        masks = [dp.layer_mask(FILES, n) for n in names]
        for j, n in enumerate(names):
            if n in la:
                continue
            above = np.zeros_like(masks[j])
            for m in masks[j + 1:]:
                above |= m
            im, frac = cut(rgb, masks[j], b2)
            hid = ws.sil4(masks[j] & above) > 0.5
            bl, how = dp.b2_layer(n)
            if bl is not None and hid.any():
                a = np.asarray(im).copy()
                a[hid, :3] = np.asarray(bl)[hid, :3]
                im = Image.fromarray(a, "RGBA")
            keep(n, im, b2, {"from": arm, "b2_holes": frac, "hidden_px_from_b2": int(hid.sum())})
        print("%s: %d слоёв, %.0f с" % (arm, len(names), time.time() - t0), flush=True)

    run["sheet"], run["seconds"] = sheet(looks, outfits, la, lb), round(time.time() - t0)
    with open(os.path.join(OUT, "run.json"), "w", encoding=db.ENC) as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    print("лист:", run["sheet"], "за %.0f с" % (time.time() - t0))


if __name__ == "__main__":
    main()
