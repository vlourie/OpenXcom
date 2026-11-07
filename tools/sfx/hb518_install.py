"""XP-000518: звук падения дерева, вариант H (выбор Vitali на странице 05.11) - файл и правило в мод hd, обе копии.

Звук: art/sfx/hb518/medium/fall_5181.flac (hb518_gen.py), та же обрезка, что на странице, под формат соседа в BATTLE.CAT
(wall_destroy.wav: 22050 Гц, моно, 16 бит). Новые звуки были тише нынешнего на 15-20 дБ: мягкое сжатие и предел по пику.
Номер звука движок берёт из правила STR_HD_TREE_FALL (R-382: номер из рулсета получает смещение мода); ни с кем в бою
этот unit не встречается, правило только держит номер, как горгулья держит грохот обвала.

    py -3.13 tools/sfx/hb518_install.py          # собрать и сказать замеры
    py -3.13 tools/sfx/hb518_install.py --yes    # в обе копии мода
"""
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "art/sfx/hb518/medium/fall_5181.flac"
REF = ROOT / "Пиратки/Dioxine_XPiratez/user/mods/Piratez/Resources/Sounds/wall_destroy.wav"
OUT = ROOT / "art/sfx/hb518/tree_fall.wav"
TARGETS = [ROOT / "user/mods/hd", ROOT / "Пиратки/Dioxine_XPiratez/user/mods/hd"]
INDEX = 900     # внутри reservedSpace мода hd, выше общих номеров BATTLE.CAT
RULE = f"""# OXCE-HD: the fall of a tree (ticket XP-000518), made by tools/sfx/hb518_install.py. This unit never enters a battle:
# it only holds the runtime number of the sound for CollapsePilot, the way STR_STYGIAN_GARGOYLE holds the rumble.
extraSounds:
  - type: BATTLE.CAT
    files:
      {INDEX}: SOUND/tree_fall.wav
units:
  - type: STR_HD_TREE_FALL
    armor: STYGIAN_GARGOYLE_ARMOR
    capturable: false
    deathSound: {INDEX}
"""


def read(path):
    tmp = OUT.with_suffix(".tmp.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "22050", "-sample_fmt", "s16", str(tmp)], check=True)
    with wave.open(str(tmp)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    tmp.unlink()
    return a


def stats(a):
    return "пик %.2f, RMS %.1f дБ, %.2f с" % (float(np.abs(a).max()), 20 * np.log10(float(np.sqrt(np.mean(a ** 2))) + 1e-9), len(a) / 22050)


def build():
    a = read(SRC)
    peak, sr = float(np.abs(a).max()), 22050
    start = max(int(np.where(np.abs(a) > peak * 0.05)[0][0]) / sr - 0.005, 0.0)
    win = int(sr * 0.05)
    env = np.array([np.sqrt(np.mean(a[i:i + win] ** 2)) for i in range(0, len(a) - win, win)])
    end = min((np.where(env > env.max() * 0.03)[0][-1] + 1) * win / sr + 0.25, len(a) / sr)
    dur = end - start
    fade = min(0.2, dur / 3)
    af = ("atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS,volume=%.3f,"
          "acompressor=threshold=0.06:ratio=5:attack=10:release=300:makeup=9,alimiter=limit=0.95:level=false,"
          "afade=t=out:st=%.3f:d=%.3f" % (start, end, 0.95 / peak, dur - fade, fade))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(SRC), "-af", af, "-ac", "1", "-ar", "22050", "-sample_fmt", "s16", str(OUT)], check=True)
    print("нынешний:", stats(read(REF)))
    print("новый:   ", stats(read(OUT)))


def install():
    for t in TARGETS:
        (t / "SOUND").mkdir(exist_ok=True)
        shutil.copyfile(OUT, t / "SOUND/tree_fall.wav")
        (t / "Ruleset/hd_sounds.rul").write_text(RULE, encoding="utf-8", newline="\n")
        print("поставлено:", t)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    build()
    if "--yes" in sys.argv:
        install()
