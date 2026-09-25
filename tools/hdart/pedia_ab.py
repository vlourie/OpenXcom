#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pedia_ab.py - картинки педии по заданию jobs.json одной из двух моделей, для сравнения.

Модели:
  old  Qwen-Image-Edit-2511 (diffusers, photo_ui.Painter) - окружение tools\hdart\.venv
  new  Qwen-Image-2.1 edit (DiffSynth, gen_lora_test.build_pipe) - окружение E:\train\.venv-train

Разметка (панель под текст, прозрачное, рамка) и сборка кадра - из photo_ui.py, как у прежнего
прогона. Вход модели - чистое ESRGAN-увеличение оригинала (--hd, hd\UI_esrgan), а НЕ прежнее
«фото» из hd\UI: иначе модель перерисовывает чужой ответ со всеми его выдумками.

jobs.json - список {"file": "Bike_3.png", "variants": {"photo_hd": {"prompt": "...", "neg": "..."}, ...}}.
Выход: <out>\<имя>__<вариант>__<модель>.png - готовые кадры x4, в мод ничего не пишет.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\pedia_ab.py --model old --jobs art\_refs\pedia_ab\jobs.json
    E:\train\.venv-train\Scripts\python.exe tools\hdart\pedia_ab.py --model new --jobs art\_refs\pedia_ab\jobs.json
"""
import argparse
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                      # noqa: E402
from PIL import Image                                   # noqa: E402

import photo_ui as pu                                   # noqa: E402

PIR = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods")
ORIG = os.path.join(PIR, "Piratez", "Resources", "Pedia")
HD_IN = os.path.join(PIR, "hd", "hd", "UI_esrgan")
OUT = os.path.join("art", "_refs", "pedia_ab")


class Old:
    def __init__(self, args):
        self.p = pu.Painter(args.models, fast=False, steps=args.steps, photoreal=False)
        self.args = args

    def __call__(self, img, prompt, neg, seed):
        W, H = img.size
        return self.p.edit([img], prompt, neg, seed, self.args.steps, self.args.cfg, W, H)


class New:
    def __init__(self, args):
        import gen_lora_test as glt
        self.pipe = glt.build_pipe(args.models_json, "", args.vram_limit, offload=True)
        self.args = args

    def __call__(self, img, prompt, neg, seed, strength=1.0):
        W, H = img.size
        if strength < 1.0:
            return np.array(self.img2img(img, prompt, neg, seed, strength).convert("RGB"))
        kw = dict(edit_image=[img], seed=seed, height=H, width=W,
                  num_inference_steps=self.args.steps, cfg_scale=self.args.cfg)
        if self.args.cfg > 1.0 and neg:
            kw["negative_prompt"] = neg
        out = self.pipe(prompt, **kw)
        if isinstance(out, (list, tuple)):
            out = out[0]
        return np.array(out.convert("RGB"))

    def img2img(self, img, prompt, neg, seed, strength):
        """То же, что QwenImage21Pipeline.__call__, но старт не с чистого шума, а с латентов самой
        картинки под шумом силы strength: поза, взгляд и ракурс берутся из рисунка, а не
        придумываются заново. У конвейера такого ключа нет - __call__ не пробрасывает
        denoising_strength, а InputImageEmbedder кодирует картинку только при обучении."""
        import torch
        pipe, a = self.pipe, self.args
        W, H = img.size
        shared = {"cfg_scale": a.cfg, "edit_image": [img], "height": H, "width": W, "seed": seed,
                  "rand_device": "cpu", "tiled": False, "tile_size": 256, "tile_stride": 192,
                  "use_kv_cache": True}
        posi = {"prompt": prompt}
        nega = {"negative_prompt": neg if (a.cfg > 1.0 and neg) else " "}
        with torch.no_grad():
            for unit in pipe.units:
                shared, posi, nega = pipe.unit_runner(unit, pipe, shared, posi, nega)
            lat = shared["latents"]
            pipe.scheduler.set_timesteps(a.steps, denoising_strength=strength,
                                         dynamic_shift_len=lat.shape[2] * lat.shape[3])
            pipe.load_models_to_device(["vae"])
            x0 = pipe.vae.encode(pipe.preprocess_image(img.convert("RGBA")))
            shared["latents"] = pipe.scheduler.add_noise(x0.to(lat.dtype), shared["noise"],
                                                         pipe.scheduler.timesteps[0])
            pipe.load_models_to_device(pipe.in_iteration_models)
            models = {n: getattr(pipe, n) for n in pipe.in_iteration_models}
            for pid, t in enumerate(pipe.scheduler.timesteps):
                t = t.reshape(1).to(dtype=pipe.torch_dtype, device=pipe.device)
                pred = pipe.cfg_guided_model_fn(pipe.model_fn, a.cfg, shared, posi, nega,
                                                **models, timestep=t, progress_id=pid)
                shared["latents"] = pipe.step(pipe.scheduler, progress_id=pid, noise_pred=pred, **shared)
            pipe.load_models_to_device(["vae"])
            out = pipe.vae.decode(shared["latents"])
            out = pipe.vae_output_to_image(out)
            pipe.load_models_to_device([])
        return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", choices=["old", "new"], required=True)
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--orig", default=ORIG)
    ap.add_argument("--hd", default=HD_IN)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--names", default="", help="только эти картинки, через запятую")
    ap.add_argument("--variants", default="", help="только эти варианты, через запятую")
    ap.add_argument("--steps", type=int, default=0, help="0: old 40, new 30")
    ap.add_argument("--cfg", type=float, default=4.0, help="больше 1 - иначе негатив не действует (R-040)")
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--models", default=os.environ.get("HD_MODELS", "E:\\models"))
    ap.add_argument("--models-json", dest="models_json", default=r"E:\train\model_paths.json")
    ap.add_argument("--vram-limit", dest="vram_limit", type=float, default=26.0)
    ap.add_argument("--strength", type=float, default=1.0,
                    help="только new: меньше 1 - старт с латентов картинки (img2img), поза и взгляд держатся")
    ap.add_argument("--tag", default="", help="метка в имени файла вместо имени модели")
    args = ap.parse_args()
    if not args.steps:
        args.steps = 40 if args.model == "old" else 30

    with io.open(args.jobs, encoding="utf-8-sig") as f:
        jobs = json.load(f)
    only = {n.strip().lower() for n in args.names.split(",") if n.strip()}
    only_v = {v.strip() for v in args.variants.split(",") if v.strip()}
    os.makedirs(args.out, exist_ok=True)

    todo = []
    for job in jobs:
        name = os.path.splitext(job["file"])[0]
        if only and name.lower() not in only:
            continue
        for var, spec in job["variants"].items():
            if only_v and var not in only_v:
                continue
            dst = os.path.join(args.out, "%s__%s__%s.png" % (name, var, args.tag or args.model))
            if os.path.exists(dst) and not args.force:
                continue
            todo.append((job, name, var, spec, dst))
    print("модель %s, шагов %d, cfg %.1f: заданий %d" % (args.model, args.steps, args.cfg, len(todo)), flush=True)
    if not todo:
        return 0

    t0 = time.time()
    gen = Old(args) if args.model == "old" else New(args)
    print("модель загружена за %.0f с" % (time.time() - t0), flush=True)

    t0 = time.time()
    for i, (job, name, var, spec, dst) in enumerate(todo):
        path = os.path.join(args.orig, job["file"])
        src = pu.Source(path)
        mask, fill, box, parts = pu.layout(src, job.get("panel", "auto"))
        hd, k, kind = pu.hd_input(src, path, args.hd, 0)
        if box is None:
            print("%s: рисовать нечего (%s)" % (name, parts))
            continue
        x0, y0, x1, y1 = box
        crop = hd[y0 * k:(y1 + 1) * k, x0 * k:(x1 + 1) * k]
        W, H = pu.target_size(crop.shape[1], crop.shape[0], args.mp)
        img = Image.fromarray(crop).resize((W, H), Image.LANCZOS)
        t1 = time.time()
        seed = pu.seed_of(name, args.seed)
        strength = float(spec.get("strength", args.strength))
        if args.model == "new":
            out = gen(img, spec["prompt"], spec.get("neg", ""), seed, strength)
        else:
            out = gen(img, spec["prompt"], spec.get("neg", ""), seed)
        pic = pu.compose(hd, out, box, k, mask, fill, src, 0)
        pic.save(dst, compress_level=6)
        el = time.time() - t0
        print("%d/%d %s %s: %.0f с (вход %s, панель %s) -> %s; осталось ~%.0f мин" % (
            i + 1, len(todo), name, var, time.time() - t1, kind, parts, dst,
            (len(todo) - i - 1) * el / (i + 1) / 60), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
