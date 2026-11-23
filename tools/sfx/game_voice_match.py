"""Сопоставление голосов игры (game_clips.tsv) с нашими голосами: тип бойца -> папка клипов -> наш голос.

    D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/game_voice_match.py
-> docs/research/game-voices-match.md: по каждой паре - высота речи игры и нашего опорного, примеры фраз.
Речь - клип, где распознано хотя бы два слова из букв (крики «ах-ах» и дыхание не в счёт).
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CLIPS = ROOT / "art/sfx/voicepack/game_clips.tsv"
VP = ROOT / "art/sfx/voicepack"
OUT = ROOT / "docs/research/game-voices-match.md"
# тип бойца в игре (soldiers.*Male/Female, census/sounds.tsv) -> папки его голоса -> наши голоса (voicepack_map.tsv)
GROUPS = [
    ("Пиратка (STR_SOLDIER и S/V/W/X/R/M)", ["Distress/Gal Panic", "Distress/Gal Berserk"],
     ["V001", "V002", "V003", "V004", "V005"]),
    ("Раб, чистокровный, герой (SLAVE, PUREBLOOD, HERO)", ["Distress/SS Panic", "Distress/SS Berserk",
                                                           "Distress/SS Extra"], ["V006", "V007"]),
    ("Крестьянка, барышня (PEASANT, DAMSEL)", ["Distress/PEA Panic", "Distress/PEA Berserk"], ["V008", "V009"]),
    ("Гибрид мужской (HYBRID)", ["Distress/Hybrid M Panic", "Distress/Hybrid M Berserk"], ["V010"]),
    ("Гибрид женский (HYBRID)", ["Distress/Hybrid F Panic", "Distress/Hybrid F Berserk"], ["V011"]),
    ("Локнар (LOKNAR)", ["Distress/Loknar Panic", "Distress/Loknar Berserk"], ["V012"]),
    ("Гномка (GNOME)", ["Distress/Gnome Panic", "Distress/Gnome Berserk"], ["V013"]),
    ("Кошкодевочки (NEKOMIMI, _O, _W, _H)", ["Catgrrrls/Neko Panic", "Catgrrrls/Neko Berserk",
                                             "Catgrrrls/Neko Death", "Catgrrrls"], ["V014", "V015", "V016", "V017"]),
    ("Огр (OGRE)", ["Caleb"], ["V018"]),
    ("Киллбот (KILLBOT)", ["KB"], ["V025"]),
    ("Ксенфорсер (XENFORCER)", ["XENF"], ["V026"]),
]


def speech(t):
    return len(re.findall(r"[A-Za-z]{2,}", t)) >= 2 and not re.fullmatch(r"[\W\s]*((h?a+h?|o+h?|u+h?|ugh)\W*)+", t, re.I)


def ref_f0(vid):
    import json
    st = json.loads((VP / vid / "voice.json").read_text(encoding="utf-8-sig"))
    if not st.get("ref"):
        return 0.0, st["name"]
    wav, sr = librosa.load(str(VP / st["ref"]), sr=16000, mono=True)
    f, ok, _ = librosa.pyin(wav, fmin=60, fmax=900, sr=sr)
    f = f[ok & ~np.isnan(f)]
    return (round(float(np.median(f)), 1) if len(f) else 0.0), st["name"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    clips = defaultdict(list)
    with open(CLIPS, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            clips[r["dir"]].append(r)
    L = ["# Голоса игры и наши голоса", "",
         "Vitali 21.10: «в игре на английском у многих героев уже есть голоса — подобрать такие же или максимально "
         "похожие». Клипы — `art/sfx/voicepack/game_clips.tsv` (`tools/sfx/game_voice_clips.py`), "
         "сопоставление — `tools/sfx/game_voice_match.py`. Высота — медиана F0 речи, Гц.", ""]
    L += ["| Тип бойца | Клипов (речь) | Речи, с | F0 игры | Наш голос | F0 нашего |", "|---|---|---|---|---|---|"]
    detail = []
    for title, dirs, ours in GROUPS:
        rows = [r for d in dirs for r in clips.get(d, [])]
        sp = [r for r in rows if speech(r["heard"])]
        f0s = [float(r["f0"]) for r in sp if float(r["f0"]) > 0]
        gf = round(float(np.median(f0s)), 1) if f0s else 0.0
        sec = round(sum(float(r["dur"]) for r in sp), 1)
        mine = [(v, *ref_f0(v)) for v in ours]
        L.append(f"| {title} | {len(rows)} ({len(sp)}) | {sec} | {gf} | "
                 + "<br>".join(f"{v} {n}" for v, _, n in mine) + " | " + "<br>".join(str(x) for _, x, _ in mine) + " |")
        detail += ["", f"### {title}", ""] + [f"- `{r['dir']}/{r['file']}` {r['dur']} с, {r['f0']} Гц — {r['heard']}"
                                              for r in rows]
    OUT.write_text("\n".join(L + detail) + "\n", encoding="utf-8-sig")
    print("\n".join(L))


if __name__ == "__main__":
    main()
