"""SIDE-FIRST COMBAT V0.1 final check: the rakes of this step, one rake.py call each. Skips what docs/RAKES.md and docs/rakes already hold."""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
AN = "docs/research/ai-mechanics/cm/side_first_v0/"
RAKES = [
    ("Подписи пси в разборе перепутаны: код 13 это захват, 14 паника",
     AN + "final_stats.py",
     "Отчёт V0 назвал 0,50 на бой пси-атаками и 1,25 захватами. Захват успешно давал faction=1 только там, где разбор писал пси.",
     "Коды действий записаны в словарь разбора по памяти. В движке BA_MINDCONTROL = 13, BA_PANIC = 14 (RuleItem.h:75).",
     "Коды действий брать из RuleItem.h и проверять по следствию в журнале. Результат пси считать по faction цели и решениям захваченных (psi_effects.py), а не по подписи."),
    ("Шлюз по частоте на 4 сидах держится на одном бою базы",
     AN + "FINAL_PLAN_V01.md",
     "Шлюз L8: D0 1,27 пси-действия на ход, 24 из 28 дал s1 и 22 из 24 по одному бойцу. Без s1 у D0 0,33, а порог половины D0 вышел 0,64.",
     "Порог поставлен от суммы по сидам, без взгляда на распределение по боям.",
     "Перед записью порога смотреть базу по сидам и по целям. Порог после результатов не менять, наблюдение указывать рядом."),
    ("Директор ведёт бойца мимо reselectAllowed: пометка dontReselect не останавливает его действие",
     AN + "SideCombatDirector_V01.cpp",
     "Кодом: isReady проверяет только ОВ и статус, scdLeads пропускает проверку reselectAllowed в handleAI. В D0 помеченный боец в этот ход не действует. Журнал пометку не пишет, числа нет.",
     "Новый цикл добавил свой путь выбора перед штатной проверкой, а условие пометки в него не перенесено.",
     "Новый путь выбора юнита сверять со всеми условиями штатного: reselectAllowed, оглушение, счётчик. Пометку писать в журнал."),
]
book = Path("docs/RAKES.md").read_text(encoding="utf-8-sig")
book += "".join(p.read_text(encoding="utf-8-sig") for p in Path("docs/rakes").glob("*.md"))
for title, files, symptom, cause, rule in RAKES:
    if title in book:
        print("exists:", title[:50])
        continue
    r = subprocess.run([sys.executable, "tools/rake.py", "add", "--title", title, "--files", files, "--symptom", symptom, "--cause", cause, "--rule", rule, "--area", "aibench"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.returncode, r.stdout.strip()[:200], r.stderr.strip()[:200])
