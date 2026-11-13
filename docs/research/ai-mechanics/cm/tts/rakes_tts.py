"""TACTICAL TURN SOLVER V0: the rakes of this stage, one rake.py call each. Skips what docs/RAKES.md already holds."""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
AN = "docs/research/ai-mechanics/cm/tts/"
RAKES = [
    ("Имя прогона ai_probe без хвоста _w0: pack_logs находит 0 логов, хотя прогон прошёл",
     AN + "load_tts.py",
     "Запуск закончился с кодом 0, а pack_logs написал logs 0 и zip оказался пустым; журнал лежал на рабочей машине в другой папке.",
     "pack_logs.py ищет work/oxce_ai_probe/arena_<prefix>_*_w0, а --name у ai_probe становится именем папки как есть.",
     "В --name прямого запуска ai_probe всегда писать arena_<prefix>_<плечо>_<сцена>_s<зерно>_w0. После первого запуска смотреть строку logs N до разбора."),
    ("В binTiles сейва нет пустых клеток: правка по индексу падает, а новая стена должна создать запись",
     AN + "make_scene.py",
     "Скрипт сцены упал с KeyError на клетке этажа выше коридора.",
     "SavedBattleGame::save пишет только клетки, где isVoid ложно, поэтому индекс есть не у каждой клетки карты.",
     "Читать клетки сейва через get: нет записи - клетка пуста. Для новой стены создавать запись со всеми частями -1 и обновлять totalTiles."),
]
book = Path("docs/RAKES.md").read_text(encoding="utf-8-sig")
book += "".join(p.read_text(encoding="utf-8-sig") for p in Path("docs/rakes").glob("*.md"))
for title, files, symptom, cause, rule in RAKES:
    if title in book:
        print("exists:", title[:50])
        continue
    r = subprocess.run([sys.executable, "tools/rake.py", "add", "--title", title, "--files", files, "--symptom", symptom, "--cause", cause, "--rule", rule, "--area", "aibench"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.returncode, r.stdout.strip()[:200], r.stderr.strip()[:200])
