"""Лица героинь интро на головах кукол - перерисовкой: вклейка doll_face_paste (лицо героини по трём точкам в лицо
классики) идёт не в слой, а в карту контроля - яркость формы. Qwen-Image-2.1 + Fun-ControlNet-Union (как
doll_ctl_pilot) рисует заново только голову: маска - силуэт слоя головы классики x8, тело остаётся B2.
Альфа слоя - силуэт классики x4 ровно; тон - к классике головы (match_tone 0.7), как вариант A ctl-пилота.

Выход: art/doll/face_ctl/ - raw/, layers/<слой>.png (холст 1280x800, k=4), sheet.png. В мод ничего не ставит.
Каждый рисунок - свой процесс (как doll_ctl_pilot: второй в одном процессе падал по памяти карты).

  py -3 tools/gpuq.py add --name doll-face-ctl -- <venv-qwen21 python> tools/hdart/doll_face_ctl.py
"""
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")        # до импорта diffusers (R-145)

import argparse                                     # noqa: E402
import subprocess                                   # noqa: E402
import time                                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

import doll_b2_render as db                         # noqa: E402
import doll_photo_pilot as dp                       # noqa: E402
import doll_face_pilot as fp                        # noqa: E402
import doll_paint_pilot as pp                       # noqa: E402
import probe_object as po                           # noqa: E402
import wall_section as ws                           # noqa: E402

OUT = os.path.join(db.ROOT, "art", "doll", "face_ctl")
PASTE = os.path.join(db.ROOT, "art", "doll", "face_paste", "layers")
RUN = {"steps": 40, "cfg": 4.0, "control_scale": 1.0, "seed": 4242, "tone": 0.7}
WHO = {"M1": "a pale young woman with grey-blue eyes, straight brows and full lips",
       "M2": "a young woman with blue eyes, a strong jaw and full lips",
       "M3": "a young woman with brown eyes, dark brows and a slim face",
       "M4": "a young woman with very dark brown skin, dark eyes, broad nose and full lips",
       "M5": "a young woman with green eyes, freckles and a narrow nose",
       "M6": "a young East Asian woman with dark almond eyes, straight brows and a soft oval face"}
PROMPT = ("Detailed hand-painted game artwork of the head and bare shoulders of {who}, front view, calm expression, "
          "a paper-doll portrait for the equipment screen of an X-COM-style strategy game, on a flat grey panel. "
          "A clearly drawn face: eyes with pupils and highlights, brows, nose, lips. Clear readable shapes, crisp "
          "edges, fine painted detail of skin and hair. Soft light from the upper left. No text, no frame.")


def doll(files, pal, m, look):
    """-> (холст k=4: B2 тела + голова со вклейкой, имя слоя головы, имя тела)."""
    body = "%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look)
    head = "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look)
    c = fp.b2_canvas(files, pal, [body])
    c.alpha_composite(Image.open(os.path.join(PASTE, "%s_t10.png" % head.lower())).convert("RGBA"))
    return c, head, body


def crop8(canvas4):
    x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
    size = ((x1 - x0) * dp.Z // dp.K, (y1 - y0) * dp.Z // dp.K)
    return canvas4.crop((x0, y0, x1, y1)).resize(size, Image.LANCZOS)


def gray_ctl(im8):
    """Карта контроля gray, как vx_control.control_map: яркость на чёрном поле."""
    a = np.asarray(im8.convert("RGBA"), np.float32)
    rgb = a[..., :3] * (a[..., 3:4] / 255.0)
    g = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114).astype(np.uint8)
    return Image.fromarray(g, "L").convert("RGB")


def paint_one(m, look):
    import gc
    import vx_control as vc
    files, pal = db.sprite_files(), db.game_palette()
    canvas, head, _body = doll(files, pal, m, look)
    c8 = crop8(canvas)
    W, H = c8.size
    img = Image.new("RGBA", c8.size, dp.PANEL + (255,))
    img.alpha_composite(c8)
    x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
    s4 = ws.sil4(dp.layer_mask(files, head))[y0:y1, x0:x1]
    m8 = Image.fromarray((s4 > 0.5).astype(np.uint8) * 255).resize((W, H), Image.NEAREST)
    ctl = gray_ctl(c8)
    tag = "%s_%s" % (m, look)
    img.convert("RGB").save(os.path.join(OUT, "raw", tag + "_in.png"))
    ctl.save(os.path.join(OUT, "raw", tag + "_ctl.png"))
    p = vc.ControlPainter("model")
    torch = p.torch
    t = torch.from_numpy(np.asarray(ctl).copy()).permute(2, 0, 1).unsqueeze(0).float() / 255.0
    t0 = time.time()
    out = p.pipe(PROMPT.format(who=WHO[m]), image=img.convert("RGB"), mask_image=m8, control_image=t,
                 negative_prompt=pp.NEGATIVE, height=H, width=W,
                 generator=torch.Generator("cuda").manual_seed(RUN["seed"]), true_cfg_scale=RUN["cfg"],
                 num_inference_steps=RUN["steps"], control_context_scale=RUN["control_scale"],
                 use_kv_cache=True).images[0]
    dp.gpu_mem("рисунок " + tag)
    bg = Image.new("RGBA", out.size, dp.PANEL + (255,))
    bg.alpha_composite(out.convert("RGBA"))
    bg.convert("RGB").resize((W, H), Image.LANCZOS).save(os.path.join(OUT, "raw", tag + "_out.png"))
    print("  %s: %.0f с" % (tag, time.time() - t0), flush=True)
    del p
    gc.collect()


def layer(files, pal, m, look):
    """Ответ x8 -> слой головы k=4: альфа - силуэт классики x4, подложка внутри силуэта -> вклейка, тон к классике."""
    import doll_ctl_pilot as dc
    canvas, head, body = doll(files, pal, m, look)
    rgb = np.asarray(Image.open(os.path.join(OUT, "raw", "%s_%s_out.png" % (m, look))).convert("RGB"))
    paste = Image.open(os.path.join(PASTE, "%s_t10.png" % head.lower())).convert("RGBA")
    lay, frac = dc.cut(rgb, dp.layer_mask(files, head), paste)
    return po.match_tone(lay, dp.classic(files, pal, [head]), RUN["tone"]), head, body, frac


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="(служебное) нарисовать одну героиню M1..M6 и выйти")
    ap.add_argument("--redraw", action="store_true")
    ns = ap.parse_args()
    for d in ("raw", "layers"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    if ns.only:
        paint_one(ns.only, dict(fp.CAST_LOOK)[ns.only])
        sys.exit(0)
    for m, look in fp.CAST_LOOK:
        if ns.redraw or not os.path.exists(os.path.join(OUT, "raw", "%s_%s_out.png" % (m, look))):
            subprocess.run([sys.executable, os.path.abspath(__file__), "--only", m], check=True)
    files, pal = db.sprite_files(), db.game_palette()
    x0, y0, x1, y1 = fp.box4()
    rows = []
    for m, look in fp.CAST_LOOK:
        lay, head, body, frac = layer(files, pal, m, look)
        lay.save(os.path.join(OUT, "layers", head.lower() + ".png"))
        b2body = fp.b2_canvas(files, pal, [body])
        canvas, _h, _b = doll(files, pal, m, look)
        d = b2body.copy()
        d.alpha_composite(lay)
        cl = dp.classic(files, pal, [body, head]).resize((db.W * dp.K, db.H * dp.K), Image.NEAREST)
        ref, _n = fp.face_ref(m)
        rows.append(("%s -> %s  hole %.3f" % (m, look, frac),
                     [ref, cl.crop((x0, y0, x1, y1)), fp.b2_canvas(files, pal, [body, head]).crop((x0, y0, x1, y1)),
                      canvas.crop((x0, y0, x1, y1)), d.crop((x0, y0, x1, y1))]))
    fp.SEEDS = (0,)
    sh = fp.sheet(rows)
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sh)
    S = (x1 - x0) * 3
    for i, t in enumerate(("guide (paste)", "painted head")):
        dr.rectangle((S * (3 + i), 0, S * (4 + i), 20), fill=(24, 25, 30))
        dr.text((S * (3 + i) + 6, 5), t, fill=(230, 230, 230))
    sh.save(os.path.join(OUT, "sheet.png"))
    print("готово:", os.path.join(OUT, "sheet.png"), flush=True)


if __name__ == "__main__":
    main()
