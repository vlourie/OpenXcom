"""Пилот лиц куклы: лица героинь видеоинтро (F:\\AIStudio\\Escape\\cast\\M1..M6, только чтение) на головах кукол
UBERGAL (слой 10, HEAD_<внешность>). Контур головы - закон: альфа - силуэт слоя классики x4 ровно (как doll_ctl_pilot),
от модели берётся только рисунок внутри него.

Каждой героине - внешность с похожими волосами (волосы остаются классическими по форме и цвету, меняется лицо):
M1 белое каре -> M0, M2 светлый хвост -> M56, M3 каштановые с заколкой -> F36, M4 тёмная кожа, чёрные локоны -> F22,
M5 медные -> F8, M6 чёрные, хвост -> F4.

Edit-2511 в две фазы (R-213, Model как у doll_photo_pilot), два входа: <image1> - B2 головы с плечами x24 на подложке,
<image2> - лицо героини. Варианты: A - ответ как есть, B - общий тон подтянут к B2 головы (match_tone 0.7),
чтобы лицо сошлось с кожей тела.

Выход: art/doll/face_pilot/ - raw/ (входы и ответы), layers_a|b/<слой>.png (холст 1280x800, k=4), sheet.png,
run.json. В мод ничего не ставит.

  py -3 tools/gpuq.py add --name doll-face-pilot -- <venv python> tools/hdart/doll_face_pilot.py
"""
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")        # до импорта diffusers (R-145)
sys.stdout.reconfigure(encoding="utf-8")

import json                                         # noqa: E402
import time                                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw                    # noqa: E402

import doll_b2_render as db                         # noqa: E402
import doll_photo_pilot as dp                       # noqa: E402
import probe_object as po                           # noqa: E402
import unit_parts as upa                            # noqa: E402
import wall_section as ws                           # noqa: E402

OUT = os.path.join(db.ROOT, "art", "doll", "face_pilot")
CAST = r"F:\AIStudio\Escape\cast"
CAST_LOOK = (("M1", "M0"), ("M2", "M56"), ("M3", "F36"), ("M4", "F22"), ("M5", "F8"), ("M6", "F4"))
HCROP = (60, 32, 100, 72)           # голова с плечами на холсте 320x200; головы этих внешностей - x 70..88, y 42..68
ZH = 24                             # 40x40 -> 960x960
SEEDS = (20261021, 777)
TONE = 0.7
PROMPT = ("<image1> is a hand-painted game portrait: the head and bare shoulders of a young woman, front view, on a "
          "flat plain grey panel. <image2> is a photo of another woman's face. Repaint only the face in <image1> so "
          "that it becomes the face of the woman in <image2>: her face shape, her eyes and eye colour, brows, nose, "
          "lips and calm expression. Keep everything else of <image1> exactly as it is: the hair - its colour, length "
          "and outline; the head size, position and tilt; the neck and the shoulders; the skin colour of <image1>; "
          "the framing and the flat grey panel. Detailed hand-painted game artwork with soft painted shading, "
          "clean and sharp, not a photograph, no pixel art.")


def face_ref(m):
    for f in ("face_front_APPROVED.png", "source_face_crop.png"):
        p = os.path.join(CAST, m, f)
        if os.path.exists(p):
            return Image.open(p).convert("RGB"), f
    raise SystemExit("нет лица героини %s" % m)


def b2_canvas(files, pal, names):
    out = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), (0, 0, 0, 0))
    for n in names:
        im, _m = dp.b2_layer(n)
        out.alpha_composite(im if im is not None else dp.classic(files, pal, [n]).resize(out.size, Image.NEAREST))
    return out


def box4():
    return tuple(v * dp.K for v in HCROP)


def to_model(canvas4):
    x0, y0, x1, y1 = box4()
    size = ((HCROP[2] - HCROP[0]) * ZH, (HCROP[3] - HCROP[1]) * ZH)
    im = Image.new("RGBA", size, dp.PANEL + (255,))
    im.alpha_composite(canvas4.crop((x0, y0, x1, y1)).resize(size, Image.LANCZOS))
    return im


def cut(rgb, mask, b2head):
    """Ответ x24 -> слой головы k=4: альфа - силуэт классики x4 ровно; подложка внутри силуэта -> B2 головы."""
    sil = ws.sil4(mask)
    x0, y0, x1, y1 = box4()
    rgb4 = np.asarray(Image.fromarray(rgb).resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32)
    s = sil[y0:y1, x0:x1]
    assert float(sil.sum() - s.sum()) < 1.0, "голова выходит за рамку HCROP"
    matte = upa.panel_matte(rgb4, s)
    hole = (matte > 0.5) & (s > 0.5)
    b = np.asarray(b2head, np.float32)[y0:y1, x0:x1, :3]
    rgb4[hole] = b[hole]
    out = np.zeros((db.H * dp.K, db.W * dp.K, 4), np.float32)
    out[y0:y1, x0:x1, :3] = rgb4
    out[..., 3] = sil * 255
    inside = s > 0.5
    frac = float(hole[inside].mean()) if inside.any() else 0.0
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA"), round(frac, 4)


class Model(dp.Model):
    """Model doll_photo_pilot, но у задания несколько картинок: [(картинки, промпт, сид)]."""

    def run(self, jobs):
        import gc
        import torch
        from diffusers import FlowMatchEulerDiscreteScheduler, QwenImageEditPlusPipeline, QwenImageTransformer2DModel
        from diffusers.hooks import apply_layerwise_casting
        from diffusers.pipelines.qwenimage import pipeline_qwenimage_edit_plus as m
        from transformers import Qwen2_5_VLForConditionalGeneration
        pu, dev = self.pu, torch.device("cuda")
        t0 = time.time()
        te = Qwen2_5_VLForConditionalGeneration.from_pretrained(pu.MODEL, subfolder="text_encoder",
                                                                torch_dtype=torch.bfloat16)
        apply_layerwise_casting(te, storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16,
                                skip_modules_pattern=("embed", "norm", "lm_head", "rotary"))
        te.to(dev)
        pipe = QwenImageEditPlusPipeline.from_pretrained(pu.MODEL, transformer=None, text_encoder=te,
                                                         torch_dtype=torch.bfloat16)
        print("фаза 1: текстовая модель на карте за %.0f с" % (time.time() - t0), flush=True)
        dp.gpu_mem("текстовая модель")
        embeds = []
        with torch.no_grad():
            for imgs, prompt, _s in jobs:
                cond = []
                for img in imgs:
                    w, h = m.calculate_dimensions(m.CONDITION_IMAGE_SIZE, img.width / float(img.height))
                    cond.append(pipe.image_processor.resize(img, int(h), int(w)))
                pe, pm = pipe._get_qwen_prompt_embeds(prompt, cond, dev, torch.bfloat16)
                embeds.append((pe.to("cpu"), pm.to("cpu")))
        pipe.register_modules(text_encoder=None)
        del te
        gc.collect()
        torch.cuda.empty_cache()
        dp.gpu_mem("текстовая модель выгружена")
        t1 = time.time()
        tr = QwenImageTransformer2DModel.from_pretrained(pu.MODEL, subfolder="transformer", torch_dtype=torch.bfloat16)
        pipe.register_modules(transformer=tr)
        path = pu.pick_lora(pu.LIGHTNING[0], ("8steps", "bf16"))
        pipe.load_lora_weights(os.path.dirname(path), weight_name=os.path.basename(path), adapter_name="lightning")
        tr.enable_layerwise_casting(storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16,
                                    skip_modules_pattern=("pos_embed", "patch_embed", "norm", r"^proj_in$",
                                                          r"^proj_out$", "lora"))
        tr.to(dev)
        pipe.vae.to(dev)
        pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(pu.LIGHTNING_SCHEDULER)
        pipe.set_progress_bar_config(disable=True)
        gc.collect()
        print("фаза 2: трансформер на карте за %.0f с (%s)" % (time.time() - t1, os.path.basename(path)), flush=True)
        dp.gpu_mem("трансформер")
        out = []
        with torch.no_grad():
            for n, ((imgs, _p, seed), (pe, pm)) in enumerate(zip(jobs, embeds), 1):
                t = time.time()
                g = torch.Generator("cuda").manual_seed(seed)
                res = pipe(image=imgs, prompt=None, prompt_embeds=pe.to(dev), prompt_embeds_mask=pm.to(dev),
                           true_cfg_scale=dp.RUN["cfg"], num_inference_steps=dp.RUN["steps"], height=imgs[0].height,
                           width=imgs[0].width, generator=g).images[0]
                out.append(np.array(res.convert("RGB")))
                print("кадр %d/%d за %.0f с" % (n, len(jobs), time.time() - t), flush=True)
                if n == 1:
                    dp.gpu_mem("кадр 1")
        del pipe, tr
        gc.collect()
        torch.cuda.empty_cache()
        return out


def sheet(rows):
    """Ряд на героиню: лицо героини | классика x4 | B2 | A и B по сидам; всё - голова с плечами, x3."""
    x0, y0, x1, y1 = box4()
    S = (x1 - x0) * 3
    head = ["heroine", "classic", "B2"] + ["%s seed %d" % (v, i + 1) for i in range(len(SEEDS)) for v in "AB"]
    out = Image.new("RGB", (S * len(head), (S + 22) * len(rows) + 22), (24, 25, 30))
    d = ImageDraw.Draw(out)
    for i, h in enumerate(head):
        d.text((i * S + 6, 5), h, fill=(230, 230, 230))
    for r, (label, tiles) in enumerate(rows):
        y = 22 + r * (S + 22)
        d.text((6, y + S + 4), label, fill=(230, 230, 230))
        for i, t in enumerate(tiles):
            if t.size != (x1 - x0, y1 - y0):
                t = t.copy()
                t.thumbnail((S, S), Image.LANCZOS)
                bg = Image.new("RGB", (S, S), (24, 25, 30))
                bg.paste(t, ((S - t.width) // 2, (S - t.height) // 2))
                out.paste(bg, (i * S, y))
                continue
            bg = Image.new("RGBA", t.size, dp.PANEL + (255,))
            bg.alpha_composite(t.convert("RGBA"))
            out.paste(bg.convert("RGB").resize((S, S), Image.LANCZOS if i > 1 else Image.NEAREST), (i * S, y))
    return out


def main():
    for d in ("raw", "layers_a", "layers_b"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    files, pal = db.sprite_files(), db.game_palette()
    x0, y0, x1, y1 = box4()
    plan, jobs = [], []
    for m, look in CAST_LOOK:
        body = "%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look)
        head = "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look)
        b2 = b2_canvas(files, pal, [body, head])
        img1 = to_model(b2).convert("RGB")
        ref, ref_name = face_ref(m)
        img1.save(os.path.join(OUT, "raw", "%s_%s_in.png" % (m, look)))
        for s in SEEDS:
            jobs.append(([img1, ref], PROMPT, s))
        plan.append((m, look, body, head, ref, ref_name))
    t0 = time.time()
    if "--dry-run" in sys.argv:                     # без модели: ответ = вход, проверка вырезки и листа
        res = [np.asarray(j[0][0]) for j in jobs]
    else:
        res = Model(os.environ.get("OXCE_MODELS", r"E:\models")).run(jobs)
    run = {"prompt": PROMPT, "seeds": SEEDS, "edit_rev": dp.EDIT_REV, "steps": dp.RUN["steps"], "cfg": dp.RUN["cfg"],
           "zoom": ZH, "crop": HCROP, "tone": TONE, "seconds": round(time.time() - t0), "heads": {}}
    rows = []
    for i, (m, look, body, head, ref, ref_name) in enumerate(plan):
        b2head = b2_canvas(files, pal, [head])
        b2body = b2_canvas(files, pal, [body])
        mask = dp.layer_mask(files, head)
        cl = dp.classic(files, pal, [body, head]).resize((db.W * dp.K, db.H * dp.K), Image.NEAREST)
        tiles = [ref, cl.crop((x0, y0, x1, y1)), b2_canvas(files, pal, [body, head]).crop((x0, y0, x1, y1))]
        info = {"look": look, "ref": ref_name, "panel_inside": []}
        for j, s in enumerate(SEEDS):
            rgb = res[i * len(SEEDS) + j]
            Image.fromarray(rgb).save(os.path.join(OUT, "raw", "%s_%s_s%d_out.png" % (m, look, j + 1)))
            la, frac = cut(rgb, mask, b2head)
            lb = po.match_tone(la, b2head, TONE)
            info["panel_inside"].append(frac)
            for v, lay in (("a", la), ("b", lb)):
                lay.save(os.path.join(OUT, "layers_%s" % v, "%s_s%d.png" % (head.lower(), j + 1)))
                doll = b2body.copy()
                doll.alpha_composite(lay)
                tiles.append(doll.crop((x0, y0, x1, y1)))
        run["heads"][m] = info
        rows.append(("%s -> %s" % (m, look), tiles))
    sheet(rows).save(os.path.join(OUT, "sheet.png"))
    with open(os.path.join(OUT, "run.json"), "w", encoding="utf-8-sig") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    print("готово:", os.path.join(OUT, "sheet.png"), flush=True)


if __name__ == "__main__":
    main()
