"""Пробный прогон Stable Audio 3 на десяти звуках боя (этап 0, docs/AUDIO_ROADMAP.md).

Веса SA3 - формат stable-audio-tools, не diffusers, поэтому своё окружение tools/sfx/.venv-sa3
(библиотека stable-audio-3 требует torch 2.7.1, MMAudio - numpy < 2.1). Задания общие с
MMAudio (probe_tasks.py). Результат - FLAC в art/sfx/probe/stable_audio_3_<модель>/ и probe.json.

  --model sfx     Stable Audio 3 Small SFX, E:/models/stable-audio-3-small-sfx
  --model medium  Stable Audio 3 Medium,    E:/models/stable-audio-3-medium

Модели дистиллированы под 8 шагов и CFG 1; при CFG 1 негатив не действует (R-040), поэтому
он передаётся только с --cfg больше 1.

Запуск только через очередь видеокарты, интерпретатор - абсолютным путём (R-097):
    py -3.13 tools/gpuq.py add --name sfx-probe-sa3 -- E:/OpenXCom/tools/sfx/.venv-sa3/Scripts/python.exe tools/sfx/probe_sa3.py --model sfx
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# веса лежат на диске целиком; без этого библиотека полезет в HF Hub за конфигом и энкодером
os.environ["HF_HUB_OFFLINE"] = "1"

import soundfile as sf
import torch

from probe_tasks import NEGATIVE, SEED_BASE, TASKS

log = logging.getLogger("probe_sa3")

ROOT = Path(__file__).resolve().parents[2]
FADE_MS = 20
SAT_LEVEL = 0.9   # у годного звука выше этого меньше 10 процентов выборок, у шума - половина
SAT_WARN = 20.0
MODELS = {
    "sfx": ("E:/models/stable-audio-3-small-sfx", "Stable Audio 3 Small SFX"),
    "medium": ("E:/models/stable-audio-3-medium", "Stable Audio 3 Medium"),
}


def localize(node, root):
    """Ссылки конфига на HF-репозиторий (repo_id) направить в локальную папку весов."""
    if isinstance(node, dict):
        if "repo_id" in node:
            node["model_path"] = root
        for v in node.values():
            localize(v, root)
    elif isinstance(node, list):
        for v in node:
            localize(v, root)


def load(root):
    from stable_audio_3.loading_utils import load_diffusion_cond
    from stable_audio_3.model import StableAudioModel
    with open(Path(root) / "model_config.json", encoding="utf-8") as f:
        config = json.load(f)
    localize(config, root)
    model = load_diffusion_cond(config, str(Path(root) / "model.safetensors"),
                                device="cuda", model_half=True)
    model.use_lora = False
    model.lora_names = []
    return StableAudioModel(model, config, "cuda", True), config["sample_rate"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=sorted(MODELS), default="sfx")
    p.add_argument("--out", default="")
    p.add_argument("--variants", type=int, default=3)
    p.add_argument("--steps", type=int, default=8)
    p.add_argument("--cfg", type=float, default=1.0)
    p.add_argument("--only", default="", help="через запятую: имена заданий")
    # на части длин Small SFX отдаёт перегруженный шум (проба 2026-09-26: 60 процентов выборок
    # выше 0.9, спектральная плоскость 0.7): сломались 0.8, 0.9, 1.3, 1.5, 1.6 и 2.2 с, целы
    # 1.0, 2.0, 2.4, 2.5, 3.0 и 4.0. Рисуем не короче min-gen и режем до длины задания
    # с затуханием, чтобы не щёлкало
    p.add_argument("--min-gen", type=float, default=3.0)
    a = p.parse_args()

    # под очередью вывод перенаправлен и без этого кодируется в cp1252 (R-001)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    root, title = MODELS[a.model]
    out = Path(a.out or ROOT / "art/sfx/probe" / f"stable_audio_3_{a.model}")
    out.mkdir(parents=True, exist_ok=True)
    only = {s for s in a.only.split(",") if s}
    tasks = [t for t in TASKS if not only or t[0] in only]
    negative = NEGATIVE if a.cfg > 1 else None

    t0 = time.time()
    model, rate = load(root)
    log.info("%s загружена за %.1f с, VRAM %.1f ГБ, %d Гц, негатив %s", title, time.time() - t0,
             torch.cuda.memory_allocated() / 2**30, rate, "есть" if negative else "не действует (CFG 1)")

    manifest = []
    total = len(tasks) * a.variants
    done = 0
    for name, duration, prompt in tasks:
        for v in range(a.variants):
            seed = SEED_BASE + v
            t1 = time.time()
            gen_len = max(duration, a.min_gen)
            audio = model.generate(prompt=prompt, negative_prompt=negative, duration=gen_len,
                                   steps=a.steps, cfg_scale=a.cfg, seed=seed)
            wav = audio.float().cpu()
            if wav.dim() == 3:
                wav = wav[0]
            keep = int(round(duration * rate))
            if wav.shape[-1] > keep:
                wav = wav[:, :keep].clone()
                fade = min(keep, int(rate * FADE_MS / 1000))
                wav[:, keep - fade:] *= torch.linspace(1.0, 0.0, fade)
            file = out / f"{name}.v{v + 1}.flac"
            sf.write(str(file), wav.T.numpy(), rate)
            secs = time.time() - t1
            sat = float((wav.mean(dim=0).abs() > SAT_LEVEL).float().mean()) * 100
            if sat > SAT_WARN:
                log.warning("%s: %.0f процентов выборок выше %.1f - похоже на перегруженный шум",
                            file.name, sat, SAT_LEVEL)
            done += 1
            log.info("%d/%d %s сек %.1f -> %s (%.2f с звука)", done, total, name, secs, file.name,
                     wav.shape[-1] / rate)
            manifest.append({"task": name, "variant": v + 1, "seed": seed, "file": file.name,
                             "prompt": prompt, "negative": negative or "", "duration": duration,
                             "gen_length": gen_len,
                             "steps": a.steps, "cfg": a.cfg, "gen_seconds": round(secs, 2),
                             "model": title})
    with open(out / "probe.json", "w", encoding="utf-8-sig") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    log.info("готово: %d файлов за %.1f с", len(manifest), time.time() - t0)


if __name__ == "__main__":
    main()
