"""REINFORCEMENT INTELLIGENCE V0: the rakes of this stage into docs/rakes/aibench.md through tools/rake.py, one call per rake."""
import subprocess
import sys

AN = "docs/research/ai-mechanics/cm/hive_reinforcement/"
RAKES = [
    ("PO_HOLD после прибытия обнуляет _toNode, откат режимов доходит до ESCAPE и заканчивает ход бойца с остатком TU",
     AN + "patch_ri.py",
     "Под HIVE решений с режимом 3 без действия сотни за бой: cc6 292 после прибытия при 3 по кубику; без HIVE (cc3, D0) таких 0. Простой 5000-7000 TU за бой.",
     "patrol() отдаёт PO_HOLD, _toNode = 0, evaluateAIMode идёт COMBAT, PATROL, AMBUSH и при _ambushTUs 0 в ESCAPE; case AI_ESCAPE ставит finalAction.",
     "Стояние в режиме 3 под HIVE не считать решением think и побегом: сначала проверять приказ штаба (rollback.py). Пришедшего бойца отпускать через PO_NONE."),
    ("Подсчёт способных помогать считал любой узел достижимым, поэтому назначение не зависело от огневой позиции (уточняет R-677)",
     AN + "patch_ri.py",
     "M6 s1 ход 1: able=6 при нуле огневых позиций; в архиве 86 из 117 бойцо-ходов без огневой позиции.",
     "able проверял оружие, TU и наличие какого-нибудь узла. R-677 приписала это побегу, но побег по кубику единицы решений на бой, основное HOLD.",
     "Пригодность считать по конкретной цели: выстрел, дальность, линия с места или с узла в пределах хода. Причину из R-677 не повторять."),
    ("Цена заливки на плане и цена пути в ход бойца расходятся в разы, путь path_now тоже не равен потраченным TU",
     AN + "analysis/spend.py",
     "Приказы fire: 5 из 18 отменены, план 30-60 TU, путь 56-158. По 228 пришедшим приказам потрачено ровно по плану 147, ровно по path_now 58.",
     "Заливка считается в начале хода стороны, calculate в ход бойца и сначала пробует прямой путь. Точная причина не установлена; sneakyAI выключен, надбавки за скрытность нет.",
     "Цену на плане не считать гарантией, прибытие и выстрел проверять по факту. Разрыв от 20 TU годится как сигнал отказа, не как цифра."),
    ("Статика по журналу завышает отбор: позиции в журнале созданы теми приказами, которые отбор убирает",
     AN + "analysis/replay.py",
     "По статике 10 назначений и 11 атак по контакту в 5 из них, в боях 11 назначений и 5 атак в 3; бойцо-ходов на M6 69 стало 9.",
     "replay брал позиции из боёв CC, часть которых создана приказами approach, убранными фильтром; вклад этого не измерен.",
     "Вывод статики по журналу помечать как верхнюю оценку и не принимать порог только по ней; первый бой сразу сверять с прогнозом."),
    ("Счёт атак помощника только в ходы с записью ORDER занижает: боец действует и в ходы без новой записи",
     AN + "analysis/assign_eval.py",
     "ri4: ri_eval дал 3 атаки по контакту, по всему сроку назначения 4, а HELP_RESULT ATTACK 5.",
     "ri_eval связывает атаки с парой ход и боец из ORDER; разные счётчики считают разные множества.",
     "Для сравнения плеч брать один скрипт на оба плеча по всему сроку назначения и называть его в отчёте."),
    ("Поиск сбоев по слову CRASH срабатывает на название миссии STR_UFO_CRASH_RECOVERY",
     AN + "analysis/ri_final.py",
     "В ri3 grep нашёл 3 строки CRASH, все три про название миссии, настоящего сбоя нет.",
     "Шаблон не отделяет сбой от имени миссии в HIVEINIT, AIPROBE и AIRESULT.",
     "Сбой определять по коду возврата и строкам Exception или FATAL; CRASH только с исключением STR_UFO_CRASH_RECOVERY."),
]

sys.stdout.reconfigure(encoding="utf-8")
have = open("E:/OpenXCom/docs/rakes/aibench.md", encoding="utf-8-sig").read()
for title, files, sym, cause, rule in RAKES:
    if title in have:
        print("already there:", title[:60])
        continue
    r = subprocess.run([sys.executable, "tools/rake.py", "add", "--title", title, "--files", files, "--symptom", sym, "--cause", cause, "--rule", rule, "--area", "aibench"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd="E:/OpenXCom")
    print(r.returncode, (r.stdout or r.stderr).strip()[:140])
