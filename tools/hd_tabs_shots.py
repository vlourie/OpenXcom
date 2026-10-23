# Снимки вкладок опций HD невидимо (тикет XP-000263 / вкладки): главное меню -> Настройки -> HD -> вкладка [-> прокрутка].
# Пример: py -3.13 tools/hd_tabs_shots.py v2 0 1 2 3 4 5   (имя серии, номера вкладок; "0:1" - вкладка 0 после 1 прокрутки вниз пачкой)
# Игра грузится 90-120 с на снимок; снимки идут параллельно по три. Кадры: art/_review/tickets_2026-10-23/hd_tabs_<серия>_<вкладка>.png
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABS = {0: (206, 49), 1: (274, 49), 2: (342, 49), 3: (206, 62), 4: (274, 62), 5: (342, 62)}
DOWN = (230, 100)       # колесо вниз над списком (у стрелки вниз щелчок не листает)
OUT = ROOT / "art" / "_review" / "tickets_2026-10-23"

series = sys.argv[1]
jobs = []
for spec in sys.argv[2:]:
    tab, _, pages = spec.partition(":")
    clicks = "290,151;128,170;%d,%d" % TABS[int(tab)]
    clicks += (";d%d,%d" % DOWN) * int(pages or 0)
    jobs.append((spec.replace(":", "p"), clicks))
env = dict(os.environ, PYTHONIOENCODING="utf-8")
for i in range(0, len(jobs), 3):
    procs = []
    for name, clicks in jobs[i:i + 3]:
        user = Path(tempfile.gettempdir()) / ("oxce_hidden_user_tab_" + name)
        out = OUT / ("hd_tabs_%s_%s.png" % (series, name))
        procs.append(subprocess.Popen(
            ["py", "-3.13", str(ROOT / "tools" / "game_hidden.py"), "--out", str(out), "--save", "", "--after", str(150 + int(1.3 * (clicks.count(";") + 1))),
             "--clicks", clicks, "--user", str(user), "--set", "oxceHdMode=2;oxceHdScale=4"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=str(ROOT)))
    for p in procs:
        p.wait()
    print("batch", i // 3, "done", flush=True)
