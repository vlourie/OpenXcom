"""Звуки погоды в бою на Stable Audio 3 (docs/research/battle-weather-2026-11-11.md, раздел «Звук»).

В игру ничего не ставит: FLAC в art/sfx/weather/<модель>/<звук>_<сид>.flac и done.json. Петли рисуются
длиннее петли (LOOP_GEN) - weather_sfx_build.py вырезает из середины кусок и сшивает конец с началом.
Выбор вариантов - ухом Vitali на странице, ставится только выбранное.

Только через очередь видеокарты, интерпретатор абсолютным путём (R-097):
    py -3.13 tools/gpuq.py add --name weather-sfx --prio 1 -- E:/OpenXCom/tools/sfx/.venv-sa3/Scripts/python.exe tools/sfx/weather_sfx_gen.py
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

log = logging.getLogger("weather_sfx")

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "art/sfx/weather"
SEEDS = [8801, 8802]
LOOP_GEN = 24.0
TAIL = ", continuous ambience, no music, no voices, no footsteps, outdoors, field recording"

# имя -> (длина, промпт); петли - LOOP_GEN, одиночные - своя длина
SOUNDS = {
    "drizzle": (LOOP_GEN, "light drizzle, soft fine rain pattering gently on the ground and on leaves, calm, quiet" + TAIL),
    "rain": (LOOP_GEN, "steady moderate rain falling on the ground, dense patter of raindrops, water dripping" + TAIL),
    "downpour": (LOOP_GEN, "heavy torrential downpour, intense dense rain roaring on the ground and roofs, water splashing and gushing" + TAIL),
    "fog": (LOOP_GEN, "still foggy morning, very quiet low hum of the air, distant faint water drips, eerie calm" + TAIL),
    "flakes": (LOOP_GEN, "light snow falling on a calm winter day, very soft gentle breeze, hushed quiet air" + TAIL),
    "snowfall": (LOOP_GEN, "steady snowfall in winter, soft cold wind blowing gently, muffled snowy hush" + TAIL),
    "blizzard": (LOOP_GEN, "fierce blizzard, strong howling icy wind with gusts, snow hissing and whipping past" + TAIL),
    "whiteout": (LOOP_GEN, "extreme arctic snowstorm, roaring screaming wind, relentless blowing snow, violent gusts" + TAIL),
    "wind": (LOOP_GEN, "dry gusty wind blowing over an open plain, whooshing gusts rising and falling, rustling dry grass" + TAIL),
    "sandstorm": (LOOP_GEN, "desert sandstorm, strong roaring wind, sand grains hissing and blasting, gusts" + TAIL),
    "tornado": (LOOP_GEN, "distant tornado, deep low rumbling roar of a twister, swirling wind, debris whirling" + TAIL),
    "thunder_near": (6.0, "a close lightning strike: a sharp loud thunder crack then a heavy rolling boom fading away, in the rain, sound effect"),
    "thunder_far": (8.0, "distant thunder, long low rolling rumble far away across the sky, fading slowly, sound effect"),
    "tumbleweed": (4.0, "a dry tumbleweed rolling and bouncing over dusty ground, crackling dry twigs, light scraping, sound effect"),
    "dustdevil": (5.0, "a small dust devil whirlwind passing by: a swirling whoosh of wind and sand rising and fading, sound effect"),
}


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    only = {s for s in sys.argv[1:] if s in SOUNDS}
    manifest = []
    t0 = time.time()
    for key in ("sfx", "medium"):
        root, title = MODELS[key]
        out = OUT / key
        out.mkdir(parents=True, exist_ok=True)
        model, rate = load(root)
        for name, (duration, prompt) in SOUNDS.items():
            if only and name not in only:
                continue
            for seed in SEEDS:
                t1 = time.time()
                audio = model.generate(prompt=prompt, negative_prompt=None, duration=duration,
                                       steps=8, cfg_scale=1.0, seed=seed)
                wav = audio.float().cpu()
                if wav.dim() == 3:
                    wav = wav[0]
                keep = int(round(duration * rate))
                if wav.shape[-1] > keep:
                    wav = wav[:, :keep].clone()
                fade = min(wav.shape[-1], int(rate * FADE_MS / 1000))
                wav[:, wav.shape[-1] - fade:] *= torch.linspace(1.0, 0.0, fade)
                file = out / f"{name}_{seed}.flac"
                sf.write(str(file), wav.T.numpy(), rate)
                sat = float((wav.mean(dim=0).abs() > SAT_LEVEL).float().mean()) * 100
                log.info("%s %s %.1f с, насыщение %.1f, %.1f с работы", key, file.name, wav.shape[-1] / rate, sat,
                         time.time() - t1)
                manifest.append({"model": title, "key": key, "file": str(file.relative_to(OUT)).replace("\\", "/"),
                                 "name": name, "seed": seed, "prompt": prompt, "rate": rate,
                                 "seconds": round(wav.shape[-1] / rate, 2), "saturation": round(sat, 1)})
        del model
        torch.cuda.empty_cache()
    with open(OUT / "done.json", "w", encoding="utf-8-sig") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    log.info("готово, %d файлов за %.0f с, %s", len(manifest), time.time() - t0, time.strftime("%H:%M:%S"))


if __name__ == "__main__":
    main()
