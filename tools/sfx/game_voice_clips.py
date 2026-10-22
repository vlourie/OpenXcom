"""Голоса, которые уже есть в Пиратках (Vitali 21.10: «у многих героев уже есть голоса - подобрать такие же
или максимально похожие»): клипы паники, берсерка, смерти и откликов типов бойцов - что сказано и какой высоты.

    D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/game_voice_clips.py
-> art/sfx/voicepack/game_clips.tsv: папка, файл, длина, F0 медиана, распознанный текст (английский).
Только процессор (whisper int8 на CPU): видеокарту не занимает.
"""
import csv
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HOME", "D:/VoiceFactory/models")
import librosa                                   # noqa: E402
import numpy as np                               # noqa: E402
from faster_whisper import WhisperModel          # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SND = ROOT / "Пиратки/Dioxine_XPiratez/user/mods/Piratez/Resources/Sounds"
# папки голосов типов бойцов (tools/sfx: soldiers.*Male/Female по census/sounds.tsv)
DIRS = ["Distress/Gal Panic", "Distress/Gal Berserk", "Distress/PEA Panic", "Distress/PEA Berserk",
        "Distress/SS Panic", "Distress/SS Berserk", "Distress/SS Extra", "Distress/Gnome Panic",
        "Distress/Gnome Berserk", "Distress/Hybrid F Panic", "Distress/Hybrid F Berserk", "Distress/Hybrid M Panic",
        "Distress/Hybrid M Berserk", "Distress/Loknar Panic", "Distress/Loknar Berserk", "Catgrrrls/Neko Panic",
        "Catgrrrls/Neko Berserk", "Catgrrrls/Neko Death", "Caleb", "KB", "XENF", "Distress", "Catgrrrls"]
OUT = ROOT / "art/sfx/voicepack/game_clips.tsv"


def f0(wav, sr):
    f, ok, _ = librosa.pyin(wav, fmin=60, fmax=900, sr=sr)
    f = f[ok & ~np.isnan(f)] if f is not None else []
    return round(float(np.median(f)), 1) if len(f) else 0.0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    m = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    rows = []
    for d in DIRS:
        for p in sorted((SND / d).glob("*")):
            if p.suffix.lower() not in (".wav", ".ogg") or not p.is_file():
                continue
            wav, sr = librosa.load(str(p), sr=16000, mono=True)
            segs, _ = m.transcribe(wav, language="en", beam_size=5, vad_filter=False)
            text = " ".join(s.text.strip() for s in segs).strip()
            rows.append([d, p.name, round(len(wav) / sr, 2), f0(wav, sr), text])
            print(f"{d:26} {p.name:28} {rows[-1][2]:5} {rows[-1][3]:6}  {text}", flush=True)
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["dir", "file", "dur", "f0", "heard"])
        w.writerows(rows)
    print("клипов", len(rows), "->", OUT)


if __name__ == "__main__":
    main()
