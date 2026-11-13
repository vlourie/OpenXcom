"""UNIFIED ARMY CONTROL V0: the rakes of this stage, one rake.py call each."""
import subprocess
import sys

AN = "docs/research/ai-mechanics/cm/hive_ua/"
RAKES = [
    ("Поиск узла по всей карте снимает сторожа с поста: scout=false обходится незаметно",
     AN + "tree/src/Battlescape/AIModule.cpp",
     "UA, M6: двое лидеров и навигатор без штаба стоят 8 ходов и целы, со штабом уходят, оба лидера гибнут. 24 из 25 бойцо-ходов без трат и около 3000 из 3292 TU простоя в OFF - они, падение простоя выглядело как оживление армии.",
     "Ступени условия вызывают getPatrolNode(mapWide || scout): для бойца на узле с рангом это отменяет штатный scout=false.",
     "Меняя аргумент штатного поиска, перечислить, кого он держал на месте. Падение простоя разбирать по бойцам: кто дал цифру, до вывода об оживлении."),
    ("Сверка с базой другого лимита ходов расходится на границе хода - это не отличие решений",
     AN + "analysis/hh_same.py",
     "UO против D0 на M3 и M8: совпало 5077 из 5120 и 2657 из 2673, первое отличие в конце запуска на границе хода 9.",
     "База снята с более длинным лимитом и пишет строки следующего хода, а контроль на этой границе заканчивается.",
     "Первое отличие смотреть глазами: если контроль просто кончился, сравнивать до общей длины и так и писать в отчёте, а не называть это SAME."),
    ("Ворота времени против базы, которая мерила меньше: фаза turn есть только у новой сборки",
     AN + "analysis/plantime.py",
     "T9: у UA сумма полей за ход 761 мс, у RA только фаза plan 413 мс. plantime.py показывал UA намного дешевле, потому что поля после плана он не видит.",
     "phase=turn добавлен в этом этапе, а база RA писала поля только внутри плана. Счётчик floodNs не сбрасывается между планом и концом хода, поэтому turn уже включает plan.",
     "Перед воротами времени проверить, что база и новая сборка мерят одно и то же; если нет, писать это рядом с цифрой и не складывать plan и turn."),
    ("Пометка посещённого узла в секторе подразделения теряет узлы соседних секторов",
     AN + "tree/src/Battlescape/HiveCommand.cpp",
     "При подготовке UA по коду: боец подразделения, проходя узел чужого сектора, отмечал его не в том секторе, и для владельца узел оставался непосещённым. В бою отдельно не измерялось.",
     "markVisited писал в сектор текущего подразделения, а не в сектор-владелец узла.",
     "Посещённые узлы хранить у сектора-владельца. Сверять счётчик посещений с реальными проходами бойцов."),
]
sys.stdout.reconfigure(encoding="utf-8")
known = open("E:/OpenXCom/docs/rakes/aibench.md", encoding="utf-8-sig").read()
for title, files, symptom, cause, rule in RAKES:
    if title in known:
        print("already there:", title[:60])
        continue
    r = subprocess.run([sys.executable, "-I", "tools/rake.py", "add", "--title", title, "--files", files, "--symptom", symptom, "--cause", cause, "--rule", rule, "--area", "aibench"], cwd="E:/OpenXCom", capture_output=True, encoding="utf-8", env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    print(r.returncode, r.stdout.strip()[:120], r.stderr.strip()[:200])
r = subprocess.run([sys.executable, "-I", "tools/rake.py", "hit", "R-674"], cwd="E:/OpenXCom", capture_output=True, encoding="utf-8", env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
print(r.returncode, r.stdout.strip()[:120], r.stderr.strip()[:200])
