"""NATURAL GATE: the rakes of this stage, one rake.py call each. Skips what docs/RAKES.md and docs/rakes already hold."""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
AN = "docs/research/ai-mechanics/cm/tts_gate/"
RAKES = [
    ("Решатель считает заблокированным выстрел с открытой линией: lineNow требует ещё и visible",
     "docs/research/ai-mechanics/cm/tts/TurnSolver.cpp",
     "В M10 решатель записал 28 случаев «товарищ на линии», а в 5 из них в списке движка у B по той же цели lof 1.",
     "lineNow = visible + canTargetUnit, а lof в [AICAND] acts - только canTargetUnit. Цель дальше дальности обзора, вероятно, даёт отказ по visible, и его принимают за перекрытие. Причина правдоподобна по коду и журналу, отдельно не доказана.",
     "Прежде чем считать выстрел заблокированным товарищем, разделять отказы: нет видимости и нет линии - разные причины. По журналу сверять с lof в [AICAND] acts."),
    ("Косвенная улика перекрытия линии почти всегда ложна: A видит цель и стоит рядом с B, но движок и без него говорит lof 0",
     AN + "use.py",
     "Из 467 случаев, где A на луче, сам видит цель и стоит в 3 клетках от B, проверить можно 53: линия открылась в 12, осталась закрытой в 41. На M10 улику дают 18 случаев, решатель подтверждает 3.",
     "Плоская линия не знает этажей и стен, а lof 0 часто даёт местность. Что A может стрелять в цель, ничего не говорит о линии из клетки B.",
     "Перекрытие считать доказанным только открытием (тот же B и T, те же клетки, lof 0 при товарище и 1 после его ухода) или проверкой движка без A. Случай с ушедшим товарищем и lof 0 считать опровержением."),
    ("Открытая линия не значит полезный выстрел: цепочка A → B бывает в D0 сама, а урона нет",
     AN + "use.py",
     "Перед совместным выбором ждали выигрыша от освобождения линии. В 34 открытиях с TU первое решение B: 19 атак, ран 0, урона 0, по своим 9.",
     "Использование линии решает think, а результат - оружие, броня и дальность. Меткость в [AICAND] acts без падения по дальности: 38 превращается в 6, 41 - в минус.",
     "Ценность возможности считать по меткости с calculateLimits, опасности цели и записи оружия. Отдельно проверять, что D0 не делает этого сам. Число блокировок мерой возможности не считать."),
]
book = Path("docs/RAKES.md").read_text(encoding="utf-8-sig")
book += "".join(p.read_text(encoding="utf-8-sig") for p in Path("docs/rakes").glob("*.md"))
for title, files, symptom, cause, rule in RAKES:
    if title in book:
        print("exists:", title[:50])
        continue
    r = subprocess.run([sys.executable, "tools/rake.py", "add", "--title", title, "--files", files, "--symptom", symptom, "--cause", cause, "--rule", rule, "--area", "aibench"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.returncode, r.stdout.strip()[:200], r.stderr.strip()[:200])
