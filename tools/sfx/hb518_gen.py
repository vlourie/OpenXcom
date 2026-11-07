"""XP-000518: варианты звука падения дерева на Stable Audio 3 (выбор Vitali 05.11, заметка на странице).

В игру ничего не ставит: FLAC в art/sfx/hb518/<модель>/. Загрузка и генерация как в probe_sa3.py.
Длина по эталону игры (R-100): wall_destroy.wav 3,75 с, заказ 4 с.

Только через очередь видеокарты, интерпретатор абсолютным путём (R-097):
    py -3.13 tools/gpuq.py add --name hb518-sfx --prio 1 -- E:/OpenXCom/tools/sfx/.venv-sa3/Scripts/python.exe tools/sfx/hb518_gen.py
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"

import soundfile as sf
import torch

from probe_sa3 import FADE_MS, MODELS, SAT_LEVEL, load

log = logging.getLogger("hb518")

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "art/sfx/hb518"
DURATION = 4.0
SEEDS = [5181, 5182, 5183]
PROMPTS = {
    "fall": "a large tree falling in a forest: wood creaking and cracking, the trunk crashes down with a heavy dull thud on soft ground, branches and leaves rustle, outdoors, sound effect",
    "snap": "a thick wooden tree trunk snapping with a sharp crack, splintering wood, then branches crashing to the ground, short, sound effect",
    "thud": "felled timber hitting the forest floor, one deep wooden thump, broken branches and leaves settling, no rocks, sound effect",
}


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    manifest = []
    for key in ("sfx", "medium"):
        root, title = MODELS[key]
        out = OUT / key
        out.mkdir(parents=True, exist_ok=True)
        model, rate = load(root)
        for name, prompt in PROMPTS.items():
            for seed in SEEDS:
                audio = model.generate(prompt=prompt, negative_prompt=None, duration=DURATION,
                                       steps=8, cfg_scale=1.0, seed=seed)
                wav = audio.float().cpu()
                if wav.dim() == 3:
                    wav = wav[0]
                keep = int(round(DURATION * rate))
                if wav.shape[-1] > keep:
                    wav = wav[:, :keep].clone()
                fade = min(wav.shape[-1], int(rate * FADE_MS / 1000))
                wav[:, wav.shape[-1] - fade:] *= torch.linspace(1.0, 0.0, fade)
                file = out / f"{name}_{seed}.flac"
                sf.write(str(file), wav.T.numpy(), rate)
                sat = float((wav.mean(dim=0).abs() > SAT_LEVEL).float().mean()) * 100
                log.info("%s %s насыщение %.1f", key, file.name, sat)
                manifest.append({"model": title, "key": key, "file": str(file.relative_to(OUT)), "name": name,
                                 "seed": seed, "prompt": prompt, "rate": rate, "saturation": round(sat, 1)})
        del model
        torch.cuda.empty_cache()
    with open(OUT / "done.json", "w", encoding="utf-8-sig") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    log.info("готово, %d файлов, %s", len(manifest), time.strftime("%H:%M:%S"))


if __name__ == "__main__":
    main()
