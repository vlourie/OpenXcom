"""Голоса пилотов на глобусе (тикет XP-000246): записать V901 (пилот летающей посудины) и V902 (водитель
наземной техники), с XP-000339 ещё мужские V903 (пилот) и V904 (водитель), по docs/research/voice-script-pilots.md
тем же путём, что голоса бойцов (gen_voicepack.py:
опорный голос по карточке VoxCPM2, реплики, распознавание). Сценарий бойцов не трогается: карточки читаются
из своего файла. Выход - art/sfx/voicepack/V901, V902; мод собирает tools/sfx/build_pilot_voices.py.

Только через очередь видеокарты, интерпретатор VoiceFactory абсолютным путём (R-097):
    py -3 tools/gpuq.py add --name pilot-voices-246 -- D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/gen_pilot_voices.py
    py -3 tools/gpuq.py add --name pilot-male-339 --prio 2 --preemptible -- D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/gen_pilot_voices.py --ids V903,V904
(--prio 2 - низкий приоритет, --preemptible - уступает карту заданию выше и продолжает с того же места)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import voice_script                              # noqa: E402

ROOT = HERE.parents[1]
PILOTS = ROOT / "docs/research/voice-script-pilots.md"
DEFAULT_IDS = "V901,V902,V903,V904"


def parse(path=None, extra=None, more=None, only=None):
    return voice_script._read(PILOTS, {})


if __name__ == "__main__":
    voice_script.parse = parse
    import gen_voicepack                         # noqa: E402  (окружение VoiceFactory)
    # --ids V903,V904 (XP-000339, мужские голоса): без него - все четыре, готовые голоса пропускаются; остальные
    # ключи gen_voicepack.py (--redo, --fix) идут как есть
    ids = DEFAULT_IDS
    rest = sys.argv[1:]
    for i, arg in enumerate(rest):
        if arg == "--ids" and i + 1 < len(rest):
            ids = rest[i + 1]
            rest = rest[:i] + rest[i + 2:]
            break
        if arg.startswith("--ids="):
            ids = arg.split("=", 1)[1]
            rest = rest[:i] + rest[i + 1:]
            break
    sys.argv = [sys.argv[0], "--ids", ids, "--no-more"] + rest
    gen_voicepack.main()
