"""SIDE-FIRST COMBAT V0.1: the rakes of this step, one rake.py call each. Skips what docs/RAKES.md and docs/rakes already hold."""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
AN = "docs/research/ai-mechanics/cm/side_first_v0/"
RAKES = [
    ("Выбытие выбранного юнита перезапускает обход хода с начала списка: младшие id получают лишний заход",
     AN + "restarts.py",
     "M3 s2: хризалиды 5 заходов и 10 раундов за ход при 3 заходах и 6 раундах у D0. Раундов на заход по-прежнему не больше 2, ОВ не растут.",
     "Выбранный юнит выбыл в своём действии, например от реакции: выбранного нет, selectPlayerUnit идёт с начала списка, secondPassWrapped не вызывается и метка второго прохода не ставится. Так же и в D0. Если стрелки чаще гибнут в своём действии, заходов младших id больше.",
     "Заходы младших id считать вместе с числом выбытий выбранного (restarts.py). Рост раундов не приписывать правке счётчика, пока это не сверено. Порог по раундам ставить с учётом этого механизма."),
    ("Возврат выбора через SWITCH обнулял счётчик раундов: юнит получал два новых раунда think",
     AN + "SideCombatDirector_V01.cpp",
     "Первая сборка V0.1, M3 s1: 4,55 раунда на юнит-ход у хризалид против 3,75 у D0. Журнал act.extra молчал, потому что счётчик не доходил до 3.",
     "handleAI ставил _AIActionCounter в 0 на любом SWITCH, а COUNTER_FIX ещё и сбрасывал счётчик, когда последним действовал другой юнит.",
     "Запоминать счётчик при уходе от курсора и возвращать при возврате (roundsAfterSwitch), counterOwn вызывать сразу. Проверка: раундов на заход не больше 2 у юнитов без директора."),
]
book = Path("docs/RAKES.md").read_text(encoding="utf-8-sig")
book += "".join(p.read_text(encoding="utf-8-sig") for p in Path("docs/rakes").glob("*.md"))
for title, files, symptom, cause, rule in RAKES:
    if title in book:
        print("exists:", title[:50])
        continue
    r = subprocess.run([sys.executable, "tools/rake.py", "add", "--title", title, "--files", files, "--symptom", symptom, "--cause", cause, "--rule", rule, "--area", "aibench"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.returncode, r.stdout.strip()[:200], r.stderr.strip()[:200])
