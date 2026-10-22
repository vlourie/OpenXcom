"""Ход записи «сотни» (docs/research/voice-direction.md): сколько реплик записано и распознано из сценария.

    D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/voice100_progress.py
Одна строка: реплик записано / всего (RU+EN), голосов готово (распознаны), опорных из игры; без видеокарты.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voice_script                              # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "art/sfx/voicepack"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    voices = voice_script.parse(more=voice_script.MORE100)
    total = rec = ready = orig = 0
    for v in voices:
        want = {(lang, ln["n"]) for ln in v["lines"] for lang in ("ru", "en")}
        total += len(want)
        p = OUT / v["id"] / "voice.json"
        if not p.exists():
            continue
        st = json.loads(p.read_text(encoding="utf-8-sig"))
        rec += len(want & {(it["lang"], it["n"]) for it in st["lines"] if "file" in it})
        ready += bool(st.get("asr_done")) and len(st.get("script") or []) == len(v["lines"])
        orig += str(st.get("ref_src", "")).startswith("game:")
    print(f"{time.strftime('%H:%M')} реплик записано {rec}/{total} ({100 * rec / total:.1f} %), осталось {total - rec}; "
          f"голосов готово {ready}/{len(voices)}; опорных из игры {orig}/20", flush=True)


if __name__ == "__main__":
    main()
