"""Тестовый набор: шаги по классам обуви и голоса догов - Stable Audio 3 Small SFX.

Данные заданий - test_set.py. Модель рисует не короче 2 с (R-100: на коротком заказе Small SFX
отдаёт перегруженный шум), из рисунка вырезается одно событие: самый громкий удар с началом
не позже 3 мс до атаки, хвост - пока огибающая не упала на 40 dB, затухание 20 мс.
Кандидаты оцениваются числом (одно событие, насыщение, плоскость спектра), лучшие идут в мод;
все кандидаты остаются для страницы прослушивания.

Выход: art/sfx/test_set/steps/<класс>/<материал>.c<N>.wav, art/sfx/test_set/doge/<категория>/...,
манифест art/sfx/test_set/steps.json.

Только через очередь видеокарты, интерпретатор абсолютным путём (R-097):
    py -3 tools/gpuq.py add --name sfx-test-steps -- E:/OpenXCom/tools/sfx/.venv-sa3/Scripts/python.exe tools/sfx/gen_steps_test.py
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"

import numpy as np
import soundfile as sf
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_set as T                      # noqa: E402
from probe_sa3 import MODELS, load        # noqa: E402

log = logging.getLogger("gen_steps_test")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "art/sfx/test_set"
SEED_BASE = 4200
GEN_S = 2.0


def envelope(x, rate, win_ms=5):
    n = max(1, int(rate * win_ms / 1000))
    k = len(x) // n
    return np.sqrt(np.mean(x[:k * n].reshape(k, n) ** 2, axis=1) + 1e-12), n


def cut_event(x, rate, max_s):
    """Одно событие: от атаки самого громкого удара до спада на 40 dB, не длиннее max_s."""
    env, n = envelope(x, rate)
    peak_i = int(np.argmax(env))
    peak = env[peak_i]
    floor = peak * 10 ** (-30 / 20)
    i = peak_i
    back = int(0.06 * rate / n)                 # атака шага короче 60 мс
    while i > 0 and peak_i - i < back and env[i - 1] > floor:
        i -= 1
    start = max(0, i * n - int(0.003 * rate))
    tail_floor = peak * 10 ** (-40 / 20)
    j = peak_i
    limit = min(len(env), (start + int(max_s * rate)) // n)
    quiet = 0
    while j < limit - 1:
        j += 1
        quiet = quiet + 1 if env[j] < tail_floor else 0
        if quiet * n > 0.03 * rate:
            break
    end = min(len(x), j * n, start + int(max_s * rate))
    seg = x[start:end].copy()
    fade = min(len(seg), int(rate * 0.02))
    if fade > 0:
        seg[-fade:] *= np.linspace(1.0, 0.0, fade)
    return seg


def score(seg, rate):
    """Меньше - лучше. Штраф за второй удар, насыщение, шумовой спектр, тишину."""
    if len(seg) < rate * 0.05:
        return 99.0, {"reason": "short"}
    env, n = envelope(seg, rate)
    peak = float(env.max())
    if peak < 1e-4:
        return 99.0, {"reason": "silent"}
    # второй удар: локальный максимум выше -10 dB от пика дальше 80 мс от первого
    first = int(np.argmax(env))
    gap = int(0.08 * rate / n)
    loud = np.where(env > peak * 10 ** (-10 / 20))[0]
    hits = 1 + int(np.sum(np.abs(loud - first) > gap) > 0)
    sat = float(np.mean(np.abs(seg) > 0.9))
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) + 1e-9
    flat = float(np.exp(np.mean(np.log(spec))) / np.mean(spec))
    s = (hits - 1) * 3 + sat * 20 + flat * 2
    return s, {"hits": hits, "sat": round(sat, 3), "flat": round(flat, 3)}


def to_mono(audio):
    wav = audio.float().cpu()
    if wav.dim() == 3:
        wav = wav[0]
    return wav.mean(dim=0).numpy()


def normalize(seg, peak_db=-3.0):
    p = float(np.max(np.abs(seg))) or 1.0
    return (seg * (10 ** (peak_db / 20) / p)).astype(np.float32)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", default="", help="steps, doge или пусто - всё")
    p.add_argument("--steps", type=int, default=8)
    a = p.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    root, title = MODELS["sfx"]
    t0 = time.time()
    model, rate = load(root)
    log.info("%s загружена за %.1f с", title, time.time() - t0)

    jobs = []   # (группа, подпапка, имя, промпт, длина, кандидатов)
    if a.only in ("", "steps"):
        for cls, _, foot, _ in T.STEP_CLASSES:
            for _, mat, surface in T.MATERIALS:
                jobs.append(("steps", f"steps/{cls}", mat, f"{foot} on {surface}{T.STEP_TAIL}",
                             T.STEP_MAX_S, T.STEP_CANDIDATES))
    if a.only in ("", "doge"):
        for cat, prompts in T.DOGE["sfx"].items():
            for k, prompt in enumerate(prompts):
                jobs.append(("doge", f"doge/{cat}", f"p{k + 1}", prompt + T.SFX_TAIL,
                             T.DOGE_MAX_S, T.DOGE_CANDIDATES))

    manifest = []
    total = sum(j[5] for j in jobs)
    done = 0
    last_report = time.time()
    for group, sub, name, prompt, max_s, cands in jobs:
        out = OUT / sub
        out.mkdir(parents=True, exist_ok=True)
        for c in range(cands):
            seed = SEED_BASE + c
            audio = model.generate(prompt=prompt, negative_prompt=None, duration=GEN_S,
                                   steps=a.steps, cfg_scale=1.0, seed=seed)
            x = to_mono(audio)
            seg = normalize(cut_event(x, rate, max_s))
            s, info = score(seg, rate)
            file = out / f"{name}.c{c + 1}.wav"
            sf.write(str(file), seg, rate, subtype="PCM_16")
            manifest.append({"group": group, "dir": sub, "name": name, "cand": c + 1, "seed": seed,
                             "file": str(file.relative_to(OUT)).replace("\\", "/"),
                             "prompt": prompt, "dur": round(len(seg) / rate, 3),
                             "score": round(s, 3), **info})
            done += 1
            if time.time() - last_report > 60:
                log.info("%d/%d, %.0f с", done, total, time.time() - t0)
                last_report = time.time()
    with open(OUT / "steps.json", "w", encoding="utf-8-sig") as f:
        json.dump({"model": title, "rate": rate, "items": manifest}, f, ensure_ascii=False, indent=1)
    log.info("готово: %d файлов за %.0f с", len(manifest), time.time() - t0)


if __name__ == "__main__":
    main()
