#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Qwen-Image-2.1 + Fun-Controlnet-Union (alibaba-pai, 23.09.2026): рисует с нуля, но по КОНТУРУ.

Партия фото из шума (R-125) держала форму только словами промпта: лишние ступени, тумбочка стала
холодильником. Здесь форму держит карта контура оригинала (canny, серое, lineart): одна ветка на 16
вставок в 32 блока DiT, control_context_scale 1.0 - самая сильная привязка.

Код - VideoX-Fun (не diffusers): git clone https://github.com/aigc-apps/VideoX-Fun в E:\models\src.
Весь пакет videox_fun тянет видео-модели с triton, librosa и прочим, которых на Windows нет; сюда
подгружаются только модули 2.1 (пакеты models и pipeline подменены пустыми, ядро разреженного
внимания - заглушкой: 2.1 его не зовёт). Окружение - tools\hdart\.venv-qwen21 (+ einops, omegaconf).

Проверка загрузки: unexpected keys обязано быть 0, а ключей ветки контроля в модели - столько же,
сколько в файле (карточка: чужой конфиг МОЛЧА теряет веса).
"""
import importlib
import os
import sys
import types
from dataclasses import dataclass

import numpy as np
from PIL import Image

VX_ROOT = os.environ.get("VIDEOX_FUN", r"E:\models\src\VideoX-Fun")
BASE_REPO = "Qwen/Qwen-Image-2.1"
CN_REPO = "alibaba-pai/Qwen-Image-2.1-Fun-Controlnet-Union"
CN_FILE = "Qwen-Image-2.1-Fun-Controlnet-Union.safetensors"
# карточка: config/qwenimage21/qwenimage21_control.yaml (в репозитории его нет) - вставки через блок, вход 129
CONTROL_KW = {"control_layers": list(range(0, 32, 2)), "control_in_dim": 129}


def _stub_package(name, path):
    m = types.ModuleType(name)
    m.__path__ = [path]
    m.__package__ = name
    sys.modules[name] = m
    parent, _, child = name.rpartition(".")
    if parent:
        setattr(sys.modules[parent], child, m)
    return m


def load_vx():
    """-> (QwenImage21ControlPipeline, QwenImage21ControlTransformer2DModel, AutoencoderKLQwenImage21,
    Qwen3VLForConditionalGeneration, Qwen3VLProcessor)."""
    os.environ.setdefault("VIDEOX_ATTENTION_TYPE", "SDPA")
    if VX_ROOT not in sys.path:
        sys.path.insert(0, VX_ROOT)
    import videox_fun                                           # noqa: F401 - сам пакет лёгкий
    root = os.path.join(VX_ROOT, "videox_fun")
    models = _stub_package("videox_fun.models", os.path.join(root, "models"))
    kernel = types.ModuleType("videox_fun.models.attention_kernel")
    kernel._sparse_linear_attention = None
    kernel.get_block_map = None
    sys.modules[kernel.__name__] = kernel
    t2d = importlib.import_module("videox_fun.models.qwenimage21_transformer2d")
    ctl = importlib.import_module("videox_fun.models.qwenimage21_transformer2d_control")
    vae = importlib.import_module("videox_fun.models.qwenimage21_vae")
    from transformers import Qwen3VLForConditionalGeneration, Qwen3VLProcessor
    for k in ("QwenImage21KVCache", "QwenImage21Transformer2DModel"):
        setattr(models, k, getattr(t2d, k))
    models.QwenImage21ControlTransformer2DModel = ctl.QwenImage21ControlTransformer2DModel
    models.AutoencoderKLQwenImage21 = vae.AutoencoderKLQwenImage21
    models.Qwen3VLForConditionalGeneration = Qwen3VLForConditionalGeneration
    models.Qwen3VLProcessor = Qwen3VLProcessor

    _stub_package("videox_fun.pipeline", os.path.join(root, "pipeline"))
    from diffusers.utils import BaseOutput

    @dataclass
    class QwenImagePipelineOutput(BaseOutput):
        images: list

    out = types.ModuleType("videox_fun.pipeline.pipeline_qwenimage")
    out.QwenImagePipelineOutput = QwenImagePipelineOutput
    sys.modules[out.__name__] = out
    pipe = importlib.import_module("videox_fun.pipeline.pipeline_qwenimage21_control")
    return (pipe.QwenImage21ControlPipeline, ctl.QwenImage21ControlTransformer2DModel,
            vae.AutoencoderKLQwenImage21, Qwen3VLForConditionalGeneration, Qwen3VLProcessor)


class ControlPainter:
    """run(prompt, control, W, H, ...) -> PIL RGBA (VAE 2.1 декодирует четыре канала)."""

    def __init__(self, offload="model"):
        import torch
        from huggingface_hub import hf_hub_download, try_to_load_from_cache
        from safetensors.torch import load_file
        from diffusers import FlowMatchEulerDiscreteScheduler
        self.torch = torch
        Pipe, Ctl, Vae, TE, Proc = load_vx()
        # snapshot_download в офлайне требует ВСЕ файлы репозитория (README и прочее), а в кэше только веса
        idx = try_to_load_from_cache(BASE_REPO, "model_index.json")
        if not isinstance(idx, str):
            raise SystemExit("нет %s в кэше HF (%s)" % (BASE_REPO, os.environ.get("HF_HUB_CACHE", "")))
        base = os.path.dirname(idx)
        cn = hf_hub_download(CN_REPO, CN_FILE, local_files_only=True)
        dt = torch.bfloat16
        print("Qwen-Image-2.1 + ControlNet Union: %s" % cn, flush=True)
        tr = Ctl.from_pretrained(base, subfolder="transformer", low_cpu_mem_usage=True, torch_dtype=dt,
                                 transformer_additional_kwargs=CONTROL_KW).to(dt)
        sd = load_file(cn)
        sd = sd.get("state_dict", sd)
        missing, unexpected = tr.load_state_dict(sd, strict=False)
        mine = [k for k in tr.state_dict() if k.startswith("control_")]
        lost = [k for k in mine if k in missing]
        print("   ветка контроля: в файле %d ключей, в модели %d, не загружено %d, лишних %d"
              % (len(sd), len(mine), len(lost), len(unexpected)), flush=True)
        if unexpected or lost:
            raise SystemExit("ControlNet лёг не на свои места (R-087): лишние %s, пропали %s"
                             % (unexpected[:5], lost[:5]))
        del sd
        vae = Vae.from_pretrained(base, subfolder="vae").to(dt)
        proc = Proc.from_pretrained(base, subfolder="processor")
        te = TE.from_pretrained(base, subfolder="text_encoder", torch_dtype=dt)
        sch = FlowMatchEulerDiscreteScheduler.from_pretrained(base, subfolder="scheduler")
        self.pipe = Pipe(vae=vae, text_encoder=te, processor=proc, transformer=tr, scheduler=sch)
        if offload == "none":
            self.pipe.to("cuda")
        else:
            self.pipe.enable_model_cpu_offload()

    def run(self, prompt, control, W, H, steps=40, cfg=1.0, seed=0, scale=1.0, negative=" "):
        torch = self.torch
        c = np.asarray(control.convert("RGB").resize((W, H), Image.LANCZOS))
        t = torch.from_numpy(c.copy()).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        return self.pipe(prompt, negative_prompt=negative, height=H, width=W,
                         generator=torch.Generator("cuda").manual_seed(seed),
                         true_cfg_scale=cfg, num_inference_steps=steps, control_image=t,
                         control_context_scale=scale, use_kv_cache=True).images[0]


def smooth_ref(frame, zoom, sa=0.75, sc=0.5, sharp=True):
    """Кадр k=1 -> x zoom без ступеней пикселей (R-004): цвет размыт через премульт (без каймы фона).
    Силуэт при sharp - линиями с острыми углами (probe_object.smooth_silhouette, xBRZ по МАСКЕ, R-121/
    R-042); без sharp - альфа размыта на sa пикселя кадра и срезана по порогу: ступень прямая, но и
    каждый угол скруглён радиусом ~12 пикселей x16 - проба 28.09 вышла мебелью-подушкой. Размытие
    слабее (zoom/3) модель рисовала волнистыми рёбрами - ступени читались как форма."""
    from PIL import ImageFilter
    big = frame.convert("RGBA").resize((frame.width * zoom, frame.height * zoom), Image.BICUBIC)
    a = np.asarray(big, np.float32) / 255.0
    al = a[..., 3]

    def blur(x, s):
        im = Image.fromarray((np.clip(x, 0, 1) * 255).astype(np.uint8))
        return np.asarray(im.filter(ImageFilter.GaussianBlur(s)), np.float32) / 255.0

    rgb = blur(a[..., :3] * al[..., None], zoom * sc) / np.maximum(blur(al, zoom * sc), 1e-3)[..., None]
    if sharp:
        import probe_object
        k = 4 if zoom % 4 == 0 else 2
        sil = probe_object.smooth_silhouette(frame.split()[3].point(lambda v: 255 if v > 0 else 0), k)
        sil = sil.resize(big.size, Image.BICUBIC)    # сглаженный край растянут, порог вернёт резкость
        na = np.clip((np.asarray(sil, np.float32) / 255.0 - 0.4) / 0.2, 0, 1)
        # цвет у нового края брался с размытой альфы - за силуэтом оригинала его может не быть
        rgb = np.where(al[..., None] > 0.02, rgb, blur(a[..., :3] * al[..., None], zoom * 1.5)
                       / np.maximum(blur(al, zoom * 1.5), 1e-3)[..., None])
    else:
        na = np.clip((blur(al, zoom * sa) - 0.42) / 0.16, 0, 1)
    return Image.fromarray((np.dstack([np.clip(rgb, 0, 1), na]) * 255).astype(np.uint8), "RGBA")


def control_map(frame, zoom, kind):
    """Карта контроля из кадра k=1 (RGBA) по smooth_ref: canny - контур и рёбра, gray - яркость
    (форма и тени без цвета), на чёрном поле."""
    import cv2
    a = np.asarray(smooth_ref(frame, zoom), np.float32)
    rgb = a[..., :3] * (a[..., 3:4] / 255.0)                  # на чёрном: силуэт - самое сильное ребро
    gray = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114).astype(np.uint8)
    if kind == "gray":
        return Image.fromarray(gray, "L").convert("RGB")
    edges = cv2.Canny(gray, 6, 18)                           # слабые швы ящиков тоже рёбра
    return Image.fromarray(edges, "L").convert("RGB")
