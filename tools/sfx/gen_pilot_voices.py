"""Голоса пилотов на глобусе (тикет XP-000246): записать V901 (пилот летающей посудины) и V902 (водитель
наземной техники) по docs/research/voice-script-pilots.md тем же путём, что голоса бойцов (gen_voicepack.py:
опорный голос по карточке VoxCPM2, реплики, распознавание). Сценарий бойцов не трогается: карточки читаются
из своего файла. Выход - art/sfx/voicepack/V901, V902; мод собирает tools/sfx/build_pilot_voices.py.

Только через очередь видеокарты, интерпретатор VoiceFactory абсолютным путём (R-097):
    py -3 tools/gpuq.py add --name pilot-voices-246 -- D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/gen_pilot_voices.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import voice_script                              # noqa: E402

ROOT = HERE.parents[1]
PILOTS = ROOT / "docs/research/voice-script-pilots.md"


def parse(path=None, extra=None, more=None, only=None):
    return voice_script._read(PILOTS, {})


if __name__ == "__main__":
    voice_script.parse = parse
    import gen_voicepack                         # noqa: E402  (окружение VoiceFactory)
    sys.argv = [sys.argv[0], "--ids", "V901,V902", "--no-more"] + sys.argv[1:]
    gen_voicepack.main()
