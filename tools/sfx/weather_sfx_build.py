"""Звуки погоды в игру: выбранные варианты art/sfx/weather -> hd/SOUND/WEATHER/*.ogg в обе копии мода hd.

Петли (дождь, ветер, буря, смерч...) - стерео, 20 с без шва: из сгенерированных 24 с берётся 22 с, последние 2 с
сшиваются с первыми равной мощностью, так что конец переходит в начало без щелчка и без провала. Одиночные (гром,
перекати-поле, вихрь) - моно (движок ставит их по месту на экране), тишина в начале срезается до 10 мс.
Громкость выравнивается по EBU R128 (ffmpeg ebur128): петли -24 LUFS, одиночные -18 LUFS, пик не выше -1 dBFS;
в игре поверх идёт множитель вида (HdWeatherExtras.cpp, loopOf).

Выбор - art/sfx/weather/picks.json: {"rain": "medium/rain_8801", "thunder_near": ["medium/thunder_near_8801", ...]};
без файла - пробный набор (medium, сид 8801; у одиночных оба сида).

    E:/OpenXCom/tools/sfx/.venv-sa3/Scripts/python.exe tools/sfx/weather_sfx_build.py [--out <папка hd>] [--dry]
"""
import argparse
import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

log = logging.getLogger("weather_sfx_build")

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "art/sfx/weather"
OUTS = [ROOT / "user/mods/hd/hd", ROOT / "Пиратки/Dioxine_XPiratez/user/mods/hd/hd"]
LOOPS = ["drizzle", "rain", "downpour", "fog", "flakes", "snowfall", "blizzard", "whiteout", "wind", "sandstorm", "tornado"]
ONCE = ["thunder_near", "thunder_far", "tumbleweed", "dustdevil"]
LOOP_LUFS, ONCE_LUFS, PEAK_DB = -24.0, -18.0, -1.0
CROSS, BODY, LEAD = 2.0, 20.0, 1.0


def default_picks():
    picks = {n: f"medium/{n}_8801" for n in LOOPS}
    picks.update({n: [f"medium/{n}_8801", f"medium/{n}_8802"] for n in ONCE})
    return picks


def lufs(wav, rate, tmp):
    path = Path(tmp) / "measure.wav"
    sf.write(str(path), wav, rate)
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    found = re.findall(r"I:\s+(-?[\d.]+) LUFS", out)
    return float(found[-1]) if found else -70.0


def seamless(wav, rate):
    """22 с из середины, последние CROSS секунд сшиты с первыми: длина BODY, конец переходит в начало."""
    a = int(LEAD * rate)
    body, cross = int(BODY * rate), int(CROSS * rate)
    x = wav[a:a + body + cross]
    if len(x) < body + cross:
        raise ValueError("коротко для петли")
    t = np.linspace(0, np.pi / 2, cross)[:, None]
    out = x[:body].copy()
    out[:cross] = x[:cross] * np.sin(t) + x[body:body + cross] * np.cos(t)
    return out


def trim(wav, rate):
    mono = np.abs(wav).max(axis=1)
    above = np.nonzero(mono > 10 ** (-50 / 20))[0]
    start = max(0, int(above[0]) - int(0.01 * rate)) if len(above) else 0
    out = wav[start:].copy()
    fade = min(len(out), int(0.05 * rate))
    out[len(out) - fade:] *= np.linspace(1, 0, fade)[:, None]
    return out


def level(wav, rate, target, tmp):
    """К целевой громкости; редкие пики (щелчок капли, треск ветки) - мягким ограничителем, а не общим понижением."""
    cap = 10 ** (PEAK_DB / 20)
    out = wav
    for _ in range(3):
        out = out * 10 ** ((target - lufs(out, rate, tmp)) / 20)
        knee = cap * 0.7
        big = np.abs(out) > knee
        out = np.where(big, np.sign(out) * (knee + (cap - knee) * np.tanh((np.abs(out) - knee) / (cap - knee))), out)
    return out


def encode(wav, rate, dest, tmp):
    path = Path(tmp) / "out.wav"
    sf.write(str(path), wav.astype(np.float32), rate, subtype="FLOAT")
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-c:a", "libvorbis", "-q:a", "4", str(dest)],
                   check=True)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--out", action="append", default=[])
    p.add_argument("--dry", action="store_true")
    a = p.parse_args()
    picks_file = SRC / "picks.json"
    picks = json.loads(picks_file.read_text(encoding="utf-8-sig")) if picks_file.exists() else default_picks()
    outs = [Path(o) for o in a.out] or OUTS
    report = []
    with tempfile.TemporaryDirectory() as tmp:
        built = {}
        for name in LOOPS + ONCE:
            chosen = picks.get(name)
            if not chosen:
                log.warning("%s: не выбран, пропускаю", name)
                continue
            files = chosen if isinstance(chosen, list) else [chosen]
            for i, rel in enumerate(files):
                wav, rate = sf.read(str(SRC / (rel + ".flac")), always_2d=True)
                if name in LOOPS:
                    wav = level(seamless(wav, rate), rate, LOOP_LUFS, tmp)
                    out_name = f"{name}.ogg"
                else:
                    wav = level(trim(wav.mean(axis=1, keepdims=True), rate), rate, ONCE_LUFS, tmp)
                    out_name = f"{name}_{i + 1}.ogg"
                built[out_name] = (wav, rate)
                report.append(f"{out_name} <- {rel}: {len(wav) / rate:.1f} с, {lufs(wav, rate, tmp):.1f} LUFS, пик {20 * np.log10(np.abs(wav).max() + 1e-9):.1f} dB")
                log.info(report[-1])
        if a.dry:
            return
        for out in outs:
            folder = out / "SOUND" / "WEATHER"
            # то, чего нет в выборе, убираем: игра берёт <имя>_1, _2 ... до первого пропуска
            if folder.exists():
                for old in folder.glob("*.ogg"):
                    if old.name not in built:
                        old.unlink()
            for out_name, (wav, rate) in built.items():
                encode(wav, rate, folder / out_name, tmp)
            log.info("%s: %d файлов", folder, len(built))
    (SRC / "build.txt").write_text("\n".join(report) + "\n", encoding="utf-8-sig")


if __name__ == "__main__":
    main()
