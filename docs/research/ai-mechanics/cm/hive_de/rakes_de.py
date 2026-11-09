"""DECISION ENGINE FOUNDATION: the rakes of this stage, one rake.py call each. Skips what docs/RAKES.md already holds."""
import subprocess
import sys
from pathlib import Path

AN = "docs/research/ai-mechanics/cm/hive_de/"
RAKES = [
    ("[AICAND] идёт после своего [AIDECIDE] и один раз на бой: разбор журнала приписал достижимость не тому решению",
     AN + "de_plug.py",
     "Таблица занятых проходов дала reach=1 у бойца с большим списком клеток, все числа первого прохода оказались неверны. После первой правки часть решений снова без списка.",
     "Строки кандидатов пишутся после [AIDECIDE], а повторный список с тем же хэшем не пишется вовсе (movesWritten, actsWritten в AiProbe).",
     "Кандидатов решения брать только по хэшам cand.moves и cand.acts из его [AIREC], собрав словарь по всему журналу заранее."),
    ("В списке атак t=6 это бросок: его линия не выстрел, обмен целями посчитался через гранату на 34 клетки",
     AN + "de_swap.py",
     "Лучший эпизод обмена (M2_s1 ход 4) держался на шансе 82 по цели, куда у винтовки линии не было, это был бросок EMP-гранаты. После фильтра огнестрельных обмены 180 → 129, урон 306 → 223, эпизод сменился.",
     "Сводный шанс брался как максимум по всем строкам цели, а бросок попадает в список с линией на любой дистанции. Номера BA_* были записаны по памяти.",
     "Варианты действий сравнивать только внутри одного типа: 7, 8, 9 для выстрела. Перед выводом по эпизоду смотреть строку списка глазами, номера типов брать из RuleItem.h."),
]
book = Path("docs/RAKES.md").read_text(encoding="utf-8-sig")
for title, files, symptom, cause, rule in RAKES:
    if title in book:
        print("exists:", title[:50])
        continue
    r = subprocess.run([sys.executable, "tools/rake.py", "add", "--title", title, "--files", files, "--symptom", symptom, "--cause", cause, "--rule", rule, "--area", "aibench"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.returncode, r.stdout.strip()[:200], r.stderr.strip()[:200])
r = subprocess.run([sys.executable, "tools/rake.py", "hit", "R-709"], capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.returncode, r.stdout.strip()[:200], r.stderr.strip()[:200])
