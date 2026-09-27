"""Пробный прогон MMAudio на десяти звуках боя (этап 0, docs/AUDIO_ROADMAP.md).

Только текст -> звук, без видео. На каждое задание несколько вариантов с разным seed,
результат - FLAC 44,1 кГц в art/sfx/probe/mmaudio/ и probe.json с параметрами каждого файла:
по нему потом собирается страница прослушивания.

Запуск только через очередь видеокарты:
    py -3 tools/gpuq.py add --name sfx-probe-mmaudio -- tools/sfx/.venv/Scripts/python.exe tools/sfx/probe_mmaudio.py
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

import soundfile as sf
import torch

from mmaudio.eval_utils import ModelConfig, generate, setup_eval_logging
from mmaudio.model.flow_matching import FlowMatching
from mmaudio.model.networks import get_my_mmaudio
from mmaudio.model.utils.features_utils import FeaturesUtils

log = logging.getLogger("probe_mmaudio")

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = Path("E:/models/mmaudio")

from probe_tasks import NEGATIVE, SEED_BASE, TASKS


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ROOT / "art/sfx/probe/mmaudio"))
    p.add_argument("--variants", type=int, default=3)
    p.add_argument("--steps", type=int, default=25)
    p.add_argument("--cfg", type=float, default=4.5)
    p.add_argument("--only", default="", help="через запятую: имена заданий")
    a = p.parse_args()

    # под очередью вывод перенаправлен и без этого кодируется в cp1252 (R-001)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    setup_eval_logging()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    only = {s for s in a.only.split(",") if s}
    tasks = [t for t in TASKS if not only or t[0] in only]

    cfg = ModelConfig(model_name="large_44k_v2",
                      model_path=WEIGHTS / "weights/mmaudio_large_44k_v2.pth",
                      vae_path=WEIGHTS / "ext_weights/v1-44.pth",
                      bigvgan_16k_path=None,
                      mode="44k",
                      synchformer_ckpt=WEIGHTS / "ext_weights/synchformer_state_dict.pth")
    device, dtype = "cuda", torch.bfloat16
    t0 = time.time()
    net = get_my_mmaudio(cfg.model_name).to(device, dtype).eval()
    net.load_weights(torch.load(cfg.model_path, map_location=device, weights_only=True))
    feature_utils = FeaturesUtils(tod_vae_ckpt=cfg.vae_path, synchformer_ckpt=cfg.synchformer_ckpt,
                                  enable_conditions=True, mode=cfg.mode,
                                  bigvgan_vocoder_ckpt=None, need_vae_encoder=False)
    feature_utils = feature_utils.to(device, dtype).eval()
    seq_cfg = cfg.seq_cfg
    log.info("модель загружена за %.1f с, VRAM %.1f ГБ", time.time() - t0,
             torch.cuda.memory_allocated() / 2**30)

    manifest = []
    total = len(tasks) * a.variants
    done = 0
    for name, duration, prompt in tasks:
        seq_cfg.duration = duration
        net.update_seq_lengths(seq_cfg.latent_seq_len, seq_cfg.clip_seq_len, seq_cfg.sync_seq_len)
        for v in range(a.variants):
            seed = SEED_BASE + v
            rng = torch.Generator(device=device)
            rng.manual_seed(seed)
            fm = FlowMatching(min_sigma=0, inference_mode="euler", num_steps=a.steps)
            t1 = time.time()
            with torch.inference_mode():
                audio = generate(None, None, [prompt], negative_text=[NEGATIVE],
                                 feature_utils=feature_utils, net=net, fm=fm, rng=rng,
                                 cfg_strength=a.cfg)
            wav = audio.float().cpu()[0]
            if wav.dim() == 1:
                wav = wav.unsqueeze(0)
            path = out / f"{name}.v{v + 1}.flac"
            # не torchaudio.save: в 2.11 он идёт через torchcodec, а тому нужны DLL FFmpeg
            sf.write(str(path), wav.T.numpy(), seq_cfg.sampling_rate)
            secs = time.time() - t1
            done += 1
            log.info("%d/%d %s сек %.1f -> %s", done, total, name, secs, path.name)
            manifest.append({"task": name, "variant": v + 1, "seed": seed, "file": path.name,
                             "prompt": prompt, "negative": NEGATIVE, "duration": duration,
                             "steps": a.steps, "cfg": a.cfg, "gen_seconds": round(secs, 2),
                             "model": "MMAudio large_44k_v2"})
    with open(out / "probe.json", "w", encoding="utf-8-sig") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    log.info("готово: %d файлов за %.1f с", len(manifest), time.time() - t0)


if __name__ == "__main__":
    main()
