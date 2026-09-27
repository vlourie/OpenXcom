"""Пробный прогон Stable Audio на десяти звуках боя (этап 0, docs/AUDIO_ROADMAP.md).

Задания общие с MMAudio (probe_tasks.py). Результат - FLAC в art/sfx/probe/<модель>/ и
probe.json с параметрами каждого файла.

  --model open   Stable Audio Open 1.0, веса E:/models/stable-audio-open-1.0 (100 шагов, CFG 7)

Stable Audio 3 (Small SFX, Medium) - не здесь: формат не diffusers, своё окружение, probe_sa3.py.

Запуск только через очередь видеокарты:
    py -3 tools/gpuq.py add --name sfx-probe-sao -- tools/sfx/.venv/Scripts/python.exe tools/sfx/probe_stable_audio.py --model open
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

import soundfile as sf
import torch

from probe_tasks import NEGATIVE, SEED_BASE, TASKS

log = logging.getLogger("probe_stable_audio")

ROOT = Path(__file__).resolve().parents[2]
MODELS = {
    "open": ("E:/models/stable-audio-open-1.0", "Stable Audio Open 1.0"),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=sorted(MODELS), default="open")
    p.add_argument("--out", default="")
    p.add_argument("--variants", type=int, default=3)
    p.add_argument("--steps", type=int, default=0, help="0 - по умолчанию модели (open: 100)")
    p.add_argument("--cfg", type=float, default=0.0, help="0 - по умолчанию модели (open: 7)")
    p.add_argument("--only", default="", help="через запятую: имена заданий")
    a = p.parse_args()

    # под очередью вывод перенаправлен и без этого кодируется в cp1252 (R-001)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    path, title = MODELS[a.model]
    out = Path(a.out or ROOT / "art/sfx/probe" / "stable_audio_open")
    out.mkdir(parents=True, exist_ok=True)
    only = {s for s in a.only.split(",") if s}
    tasks = [t for t in TASKS if not only or t[0] in only]

    t0 = time.time()
    from diffusers import StableAudioPipeline
    pipe = StableAudioPipeline.from_pretrained(path, dtype=torch.float16)
    pipe = pipe.to("cuda")
    rate = pipe.vae.config.sampling_rate
    log.info("%s загружена за %.1f с, VRAM %.1f ГБ, %d Гц", title, time.time() - t0,
             torch.cuda.memory_allocated() / 2**30, rate)

    manifest = []
    total = len(tasks) * a.variants
    done = 0
    for name, duration, prompt in tasks:
        for v in range(a.variants):
            seed = SEED_BASE + v
            gen = torch.Generator("cuda").manual_seed(seed)
            kw = {"prompt": prompt, "negative_prompt": NEGATIVE, "generator": gen,
                  "audio_end_in_s": duration, "num_inference_steps": a.steps or 100,
                  "guidance_scale": a.cfg or 7.0}
            t1 = time.time()
            with torch.inference_mode():
                audio = pipe(**kw).audios
            wav = audio[0].T.float().cpu().numpy()
            file = out / f"{name}.v{v + 1}.flac"
            sf.write(str(file), wav, rate)
            secs = time.time() - t1
            done += 1
            log.info("%d/%d %s сек %.1f -> %s", done, total, name, secs, file.name)
            manifest.append({"task": name, "variant": v + 1, "seed": seed, "file": file.name,
                             "prompt": prompt, "negative": NEGATIVE, "duration": duration,
                             "steps": kw.get("num_inference_steps"), "cfg": kw.get("guidance_scale"),
                             "gen_seconds": round(secs, 2), "model": title})
    with open(out / "probe.json", "w", encoding="utf-8-sig") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    log.info("готово: %d файлов за %.1f с", len(manifest), time.time() - t0)


if __name__ == "__main__":
    main()
