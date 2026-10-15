#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Проба Vitali 04.10: его текст дословно, исправленный («улучши картинку ...», без «фотки»), Edit-2511 без LoRA.
Тот же гладкий вход и те же стволы, что в weapons_probe3/4, 40 шагов, cfg 4, негатива нет (пробел - только чтобы
CFG было с чем сравнивать). Лист: оригинал | гладкий вход | N2 (probe4, мой промпт) | V (текст Vitali).

Без модели: py -3.13 tools/hdart/weapons_probe5.py --dry-run
С моделью - только через очередь:
    py -3.13 tools/gpuq.py add --name weapons_probe5 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/weapons_probe5.py
Выход art/items/weapons-probe5/: V/<ТИП>.png, sheet.png, check.tsv, meta.json."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import csv                              # noqa: E402
import json                             # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

from PIL import Image                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import weapons_edit as we               # noqa: E402
import weapons_probe3 as p3             # noqa: E402

ENC = "utf-8-sig"
OUT = "art/items/weapons-probe5"
P4 = "art/items/weapons-probe4"
FULL = {"steps": 40, "cfg": 4.0}
PROMPT = "улучши картинку сохранив размер и цвета оригинала ничего не придумывая и сохранив мелкие детали"
NEGATIVE = " "


def load(items, folder, v):
    for it in items:
        pth = os.path.join(folder, v, it["row"]["type"] + ".png")
        if os.path.exists(pth):
            it[v] = Image.open(pth).convert("RGB")
            it[v + "_rep"], it[v + "_mask"] = p3.check(it[v], *it["orig"])


def gpu_mem(tag):
    """Память карты этого процесса по счётчикам Windows: Shared обязана быть около нуля (Vitali 04.10)."""
    import subprocess
    import torch
    ps = ("$p='pid_%d_';(Get-Counter '\\GPU Process Memory(*)\\Shared Usage','\\GPU Process Memory(*)\\Dedicated Usage')"
          ".CounterSamples|?{$_.InstanceName -like ($p+'*')}|%%{'{0} {1}' -f $_.Path.Split('\\')[-1],$_.CookedValue}"
          % os.getpid())
    sh = de = 0.0
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             timeout=60).stdout
        for line in out.splitlines():
            k, _s, v = line.rpartition(" ")
            k = k.lower()
            if "shared" in k:
                sh += float(v)
            elif "dedicated" in k:
                de += float(v)
    except Exception as e:
        print("счётчики не прочитаны:", e, flush=True)
    print("память [%s]: dedicated %.1f ГБ, shared %.1f ГБ, torch %.1f ГБ (пик %.1f)"
          % (tag, de / 2 ** 30, sh / 2 ** 30, torch.cuda.memory_reserved() / 2 ** 30,
             torch.cuda.max_memory_reserved() / 2 ** 30), flush=True)
    return sh / 2 ** 30


def two_phase(models, jobs):
    """jobs: [(картинка PIL, промпт, негатив)] -> пайплайн и вложения. Фаза 1: на карте ТОЛЬКО текстовая
    модель (fp8, как в photo_ui.Painter), без pin_memory; все вложения в RAM; модель удаляется целиком.
    Фаза 2: трансформер fp8 и VAE на карту. Вместе на карте они не лежат никогда."""
    import gc
    import torch
    from diffusers import QwenImageEditPlusPipeline, QwenImageTransformer2DModel
    from diffusers.hooks import apply_layerwise_casting
    from transformers import Qwen2_5_VLForConditionalGeneration
    import photo_ui as pu
    pu.models_env(models)
    dev = torch.device("cuda")
    t0 = time.time()
    te = Qwen2_5_VLForConditionalGeneration.from_pretrained(pu.MODEL, subfolder="text_encoder",
                                                            torch_dtype=torch.bfloat16)
    apply_layerwise_casting(te, storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16,
                            skip_modules_pattern=("embed", "norm", "lm_head", "rotary"))
    te.to(dev)
    pipe = QwenImageEditPlusPipeline.from_pretrained(pu.MODEL, transformer=None, text_encoder=te,
                                                     torch_dtype=torch.bfloat16)
    from diffusers.pipelines.qwenimage import pipeline_qwenimage_edit_plus as m
    print("фаза 1: текстовая модель на карте за %.0f с" % (time.time() - t0), flush=True)
    if gpu_mem("текстовая модель") > 0.5:
        raise SystemExit("текстовая модель ушла в shared - стоп")
    embeds = []
    with torch.no_grad():
        for img, prompt, neg in jobs:
            dims = m.calculate_dimensions(m.CONDITION_IMAGE_SIZE, img.width / float(img.height))
            cond = [pipe.image_processor.resize(img, int(dims[1]), int(dims[0]))]
            pe, pm = pipe._get_qwen_prompt_embeds(prompt, cond, dev, torch.bfloat16)
            npe, npm = pipe._get_qwen_prompt_embeds(neg, cond, dev, torch.bfloat16)
            embeds.append(tuple(t.to("cpu") for t in (pe, pm, npe, npm)))
    gpu_mem("после кодирования")
    pipe.register_modules(text_encoder=None)
    del te
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    gpu_mem("текстовая модель выгружена")
    t1 = time.time()
    tr = QwenImageTransformer2DModel.from_pretrained(pu.MODEL, subfolder="transformer", torch_dtype=torch.bfloat16)
    skip = ("pos_embed", "patch_embed", "norm", r"^proj_in$", r"^proj_out$", "lora")
    tr.enable_layerwise_casting(storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16,
                                skip_modules_pattern=skip)
    tr.to(dev)
    pipe.register_modules(transformer=tr)
    pipe.vae.to(dev)
    pipe.set_progress_bar_config(disable=True)
    gc.collect()
    print("фаза 2: трансформер на карте за %.0f с" % (time.time() - t1), flush=True)
    if gpu_mem("трансформер") > 0.5:
        raise SystemExit("трансформер ушёл в shared - стоп")
    return pipe, embeds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--models", default="")
    ap.add_argument("--seed", type=int, default=p3.SEED)
    a = ap.parse_args()
    os.chdir(we.ROOT)
    cols = (("N2", "N2 мой промпт, без LoRA"), ("V", "V ваш текст, без LoRA"))
    os.makedirs(os.path.join(OUT, "V"), exist_ok=True)
    we.ONLY = p3.ONLY
    items = []
    for r in we.rows():
        rgb, m = we.original(r["type"])
        sm = Image.open(os.path.join(p3.OUT, "in_smooth", r["type"] + ".png")).convert("RGB")
        it = {"row": r, "orig": (rgb, m), "smooth": sm}
        it["smooth_rep"], it["smooth_mask"] = p3.check(sm, rgb, m)
        items.append(it)
    with open(os.path.join(OUT, "prompt.txt"), "w", encoding=ENC) as f:
        f.write("V (без негатива):\n%s\n" % PROMPT)
    p3.OUT = OUT                        # лист пишется в свою папку
    if a.dry_run:
        load(items, P4, "N2")
        p3.sheet(items, cols)
        print("dry-run: модель не грузилась ->", OUT)
        return
    import gen_hd
    import item_photo as ip
    import photo_ui as pu
    import torch
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
    print("промпт:", PROMPT, flush=True)
    t0 = time.time()
    pipe, embeds = two_phase(models, [(it["smooth"], PROMPT, NEGATIVE) for it in items])
    loaded = pipe.get_list_adapters() if hasattr(pipe, "get_list_adapters") else "?"
    print("LoRA в модели: %s" % (loaded or "нет"), flush=True)
    if loaded:
        raise SystemExit("LoRA загружена - проба не про то")
    dev = torch.device("cuda")
    for n, (it, emb) in enumerate(zip(items, embeds), 1):
        ts = time.time()
        img = it["smooth"]
        pe, pm, npe, npm = (t.to(dev) for t in emb)
        g = torch.Generator("cuda").manual_seed(a.seed)
        with torch.no_grad():
            raw = pipe(image=[img], prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                       negative_prompt_embeds=npe, negative_prompt_embeds_mask=npm, true_cfg_scale=FULL["cfg"],
                       num_inference_steps=FULL["steps"], height=img.height, width=img.width,
                       generator=g).images[0].convert("RGB")
        if gpu_mem("кадр %d" % n) > 0.5:
            raise SystemExit("ушло в shared - стоп")
        raw.save(os.path.join(OUT, "V", it["row"]["type"] + ".png"))
        it["V"] = raw
        it["V_rep"], it["V_mask"] = p3.check(raw, *it["orig"])
        print("[%d/%d] %s %s V: %.0f с, %s" % (n, len(items), it["row"]["master"], it["row"]["type"],
                                              time.time() - ts, json.dumps(it["V_rep"], ensure_ascii=False)), flush=True)
    load(items, P4, "N2")
    p3.sheet(items, cols)
    with open(os.path.join(OUT, "check.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["master", "type", "variant", "iou", "aspect_pct", "dcol", "lum", "lum_orig", "miss", "extra", "orig_px"])
        for it in items:
            for v, _h in cols:
                rep = it.get(v + "_rep") or {}
                w.writerow([it["row"]["master"], it["row"]["type"], v] +
                           [rep.get(k) for k in ("iou", "aspect_pct", "dcol", "lum", "lum_orig", "miss", "extra", "orig_px")])
    meta = {"seed": a.seed, "full": FULL, "lora": "нет", "model_rev": ip.EDIT_MODEL_REV, "prompt": PROMPT,
            "negative": "", "items": list(p3.ONLY), "seconds": round(time.time() - t0),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(OUT, "meta.json"), "w", encoding=ENC) as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print("готово за %.0f с -> %s" % (time.time() - t0, OUT), flush=True)


if __name__ == "__main__":
    main()
