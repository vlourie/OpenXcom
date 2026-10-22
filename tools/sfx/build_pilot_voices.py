"""Голоса пилотов на глобусе (тикет XP-000246) -> мод hd: hd/PILOT/<air|ground>/<событие>/<ru|en>_<N>.ogg.

Источник - записанные голоса art/sfx/voicepack/V901 (пилот, летающая техника) и V902 (водитель, наземная),
tools/sfx/gen_pilot_voices.py по docs/research/voice-script-pilots.md; берётся выбранный дубль (chosen) каждой
реплики. Звук - как из рации: полоса 300-3400 Гц, лёгкое сжатие, громкость к общей. Номера в папке события
идут подряд с 1 - движок (HdPilotVoice) перебирает их до первого пропуска.

    py -3.13 tools/sfx/build_pilot_voices.py              # перегнать в art/sfx/pilot_pack/PILOT/
    py -3.13 tools/sfx/build_pilot_voices.py --install    # + в мод hd через манифест (обе копии)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "art/sfx/voicepack"
OUT = ROOT / "art/sfx/pilot_pack/PILOT"
KINDS = {"V901": "air", "V902": "ground"}
EVENTS = ("select", "order", "attack", "escort", "return", "rebase", "wing", "cancel", "damaged", "noammo")
RADIO = ("highpass=f=300,lowpass=f=3400,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,"
         "loudnorm=I=-18:TP=-2:LRA=7")


def encode(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", RADIO,
                    "-ac", "1", "-ar", "22050", "-c:a", "libvorbis", "-q:a", "4", str(dst)], check=True)


def plan():
    out = []
    for vid, kind in KINDS.items():
        st = json.loads((SRC / vid / "voice.json").read_text(encoding="utf-8-sig"))
        if not st.get("asr_done"):
            raise SystemExit(f"{vid}: голос не дописан (asr_done нет) - сначала gen_pilot_voices.py")
        chosen = [ln for ln in st["lines"] if ln.get("chosen")]
        for lang in ("ru", "en"):
            for ev in EVENTS:
                lines = sorted((ln for ln in chosen if ln["lang"] == lang and ln["part"] == ev), key=lambda ln: ln["n"])
                if not lines:
                    raise SystemExit(f"{vid} {lang} {ev}: нет ни одной реплики")
                for i, ln in enumerate(lines, 1):
                    rel = f"PILOT/{kind}/{ev}/{lang}_{i}.ogg"
                    out.append((rel, SRC / ln["file"], vid, ln))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="в мод hd через манифест build_hd_pack")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    items = plan()
    if OUT.exists():
        shutil.rmtree(OUT)
    for rel, src, _vid, _ln in items:
        encode(src, OUT.parent / rel)
    size = sum((OUT.parent / rel).stat().st_size for rel, *_ in items)
    print(f"{len(items)} реплик, {size / 1e6:.1f} МБ -> {OUT}")
    if not a.install:
        return
    sys.path.insert(0, str(ROOT / "tools/hdart"))
    import build_hd_pack as bp
    man = bp.load()
    for rel, src, vid, ln in items:
        bp.stage(man, rel, str(OUT.parent / rel), generator="pilot_voices",
                 generator_version="build_pilot_voices.py 22.10 radio q4",
                 source_path=str(src.relative_to(ROOT)).replace("\\", "/"), approved=True,
                 approval="Vitali 22.10: «сегодняшние все нужно исправить» - тикет XP-000246",
                 source_frame=f"{vid}:{ln['lang']}:{ln['n']}")
    rels = [rel for rel, *_ in items]
    bp.save(man, why=f"pilot_voices: {len(rels)} реплик пилотов и водителей (XP-000246)")
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))


if __name__ == "__main__":
    main()
