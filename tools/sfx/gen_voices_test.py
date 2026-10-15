"""Тестовый набор: голоса бойцов на русском и английском - VoxCPM2 + Fish S2 Pro (VoiceFactory).

Два прохода в одном задании очереди:
1. VoxCPM2, режим design: голос персонажа по словесному описанию (test_set.VOICES[*].design),
   DESIGN_TAKES кандидатов опорной фразы. Опорный - тот, что распознаётся ближе к тексту.
2. Fish S2 Pro (модель интро, решение 2026-09-26): реплики голосом опорного кандидата, подача -
   тегом категории. Английский - тем же опорным русским голосом: персонаж один на оба языка.
   VOICE_TAKES дублей, лучший по распознаванию (faster-whisper из VoiceFactory) идёт в мод.

Выход: art/sfx/test_set/voices/refs/<голос>.d<N>.wav, voices/<язык>/<голос>/<кат>_<i>.t<k>.wav,
манифест art/sfx/test_set/voices.json.

Только через очередь видеокарты, интерпретатор VoiceFactory абсолютным путём (R-097):
    py -3 tools/gpuq.py add --name sfx-test-voices -- D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/gen_voices_test.py
"""
import argparse
import gc
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

VF = "D:/VoiceFactory"
os.environ.setdefault("HF_HOME", VF + "/models")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
sys.path.insert(0, VF)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import difflib                                   # noqa: E402
import numpy as np                               # noqa: E402
import soundfile as sf                           # noqa: E402

import test_set as T                             # noqa: E402
from vf import audio as A                        # noqa: E402
from vf import config as C                       # noqa: E402
from vf import qc as Q                           # noqa: E402
from vf.engines import create as create_engine   # noqa: E402
from vf.engines.base import GenParams, VoiceProfile   # noqa: E402

log = logging.getLogger("gen_voices_test")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "art/sfx/test_set/voices"
SEED_DESIGN = 7100
SEED_LINE = 7300


def norm(text):
    t = text.lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я]+", "", t)


def closeness(expected, heard):
    a, b = norm(expected), norm(heard)
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def post(wav, sr):
    """Тишина по краям - почти ноль (реплика не должна отставать от щелчка), громкость одна."""
    wav = np.asarray(wav, dtype=np.float32)
    wav = A.trim_silence(wav, sr, threshold_db=-45.0, lead_pad_ms=10, tail_pad_ms=60)
    wav = A.fade(wav, sr, ms=8)
    return A.loudness_normalize(wav, sr, target_lufs=-18.0, peak_ceiling_dbfs=-1.0)


def heard(path, lang):
    try:
        text, _ = Q.transcribe(str(path), language=lang)
        return text
    except Exception as e:                       # распознавание - только оценка, не повод падать
        log.warning("распознавание %s: %s", path, e)
        return ""


def engine(cfg, name, **over):
    ecfg = dict(cfg.get_path("engine.%s" % name, {}) or {})
    ecfg.update(over)
    eng = create_engine(name, ecfg)
    t0 = time.time()
    eng.load()
    log.info("движок %s готов за %.0f с, %d Гц", eng.model_version or name, time.time() - t0,
             eng.sample_rate)
    return eng


def free(eng):
    try:
        eng.unload()
    except Exception:
        pass
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


def design_pass(cfg, voices, manifest):
    refs_dir = OUT / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    local = VF + "/models/openbmb/VoxCPM2"
    eng = engine(cfg, "voxcpm2", local_dir=local if os.path.isdir(local) else "")
    for name in voices:
        v = T.VOICES[name]
        for k in range(T.DESIGN_TAKES):
            p = GenParams(instruction=v["design"], seed=SEED_DESIGN + k, cfg_value=2.0,
                          inference_timesteps=10)
            wav, sr, meta = eng.generate(v["ref_text"], None, p)
            wav = post(wav, sr)
            path = refs_dir / f"{name}.d{k + 1}.wav"
            sf.write(str(path), wav, sr, subtype="PCM_16")
            manifest["refs"].append({"voice": name, "take": k + 1, "file": rel(path),
                                     "dur": round(len(wav) / sr, 2), "mode": meta.get("mode")})
            log.info("голос %s, кандидат %d: %.1f с", name, k + 1, len(wav) / sr)
    free(eng)
    # опорный - ближе всех к тексту по распознаванию, длина 3-14 с
    for name in voices:
        best = None
        for r in manifest["refs"]:
            if r["voice"] != name:
                continue
            r["heard"] = heard(OUT.parent / r["file"], "ru")
            r["close"] = round(closeness(T.VOICES[name]["ref_text"], r["heard"]), 3)
            ok = 3.0 <= r["dur"] <= 14.0
            key = (ok, r["close"])
            if best is None or key > best[0]:
                best = (key, r)
        best[1]["chosen"] = True
        manifest["chosen_ref"][name] = best[1]["file"]
        log.info("опорный голос %s: кандидат %d, похожесть %.2f", name, best[1]["take"],
                 best[1]["close"])


def lines_pass(cfg, voices, langs, manifest):
    eng = engine(cfg, "fish", compile=False)
    jobs = []
    for name in voices:
        v = T.VOICES[name]
        prof = VoiceProfile(name, "fish", {"neutral": [
            {"wav": str(OUT.parent / manifest["chosen_ref"][name]), "text": v["ref_text"]}]})
        for lang in langs:
            for cat in T.CATEGORIES:
                for i, text in enumerate(v["lines"][lang][cat]):
                    jobs.append((name, prof, lang, cat, i + 1, text))
    total = len(jobs) * T.VOICE_TAKES
    done = 0
    t0 = last = time.time()
    for name, prof, lang, cat, i, text in jobs:
        d = OUT / lang / name
        d.mkdir(parents=True, exist_ok=True)
        for k in range(T.VOICE_TAKES):
            p = GenParams(instruction=T.CATEGORY_TAG[cat], seed=SEED_LINE + k)
            item = {"voice": name, "lang": lang, "cat": cat, "line": i, "take": k + 1,
                    "text": text}
            try:
                wav, sr, _ = eng.generate(text, prof, p)
                wav = post(wav, sr)
                path = d / f"{cat}_{i}.t{k + 1}.wav"
                sf.write(str(path), wav, sr, subtype="PCM_16")
                item.update(file=rel(path), dur=round(len(wav) / sr, 2))
            except Exception as e:
                item.update(error=str(e)[:300])
                log.warning("%s %s %s %d: %s", name, lang, cat, i, e)
            manifest["lines"].append(item)
            done += 1
            if time.time() - last > 60:
                log.info("реплики: %d/%d за %.0f с", done, total, time.time() - t0)
                last = time.time()
    free(eng)
    save(manifest)          # если распознавание упадёт, сгенерированное не потеряется
    # лучший дубль: влез по длине, ближе к тексту, короче
    groups = {}
    for it in manifest["lines"]:
        if "file" not in it:
            continue
        it["heard"] = heard(OUT.parent / it["file"], it["lang"])
        it["close"] = round(closeness(it["text"], it["heard"]), 3)
        groups.setdefault((it["voice"], it["lang"], it["cat"], it["line"]), []).append(it)
    for takes in groups.values():
        best = max(takes, key=lambda t: (t["dur"] <= T.VOICE_MAX_S, t["close"], -t["dur"]))
        best["chosen"] = True


def save(manifest):
    with open(OUT.parent / "voices.json", "w", encoding="utf-8-sig") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)


def rel(path):
    return str(Path(path).relative_to(OUT.parent)).replace("\\", "/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voices", default="", help="через запятую; пусто - все")
    ap.add_argument("--langs", default="ru,en")
    ap.add_argument("--skip-design", action="store_true", help="опорные голоса взять из voices.json")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    voices = [v for v in (a.voices.split(",") if a.voices else T.VOICES) if v]
    langs = [x for x in a.langs.split(",") if x]
    cfg = C.load(VF)
    mpath = OUT.parent / "voices.json"
    manifest = {"refs": [], "chosen_ref": {}, "lines": []}
    if a.skip_design:
        with open(mpath, encoding="utf-8-sig") as f:
            old = json.load(f)
        manifest["refs"], manifest["chosen_ref"] = old["refs"], old["chosen_ref"]
    t0 = time.time()
    if not a.skip_design:
        design_pass(cfg, voices, manifest)
    lines_pass(cfg, voices, langs, manifest)
    Q.free_asr()
    save(manifest)
    bad = sum(1 for it in manifest["lines"] if "error" in it)
    log.info("готово за %.0f с: реплик %d, ошибок %d", time.time() - t0, len(manifest["lines"]), bad)


if __name__ == "__main__":
    main()
