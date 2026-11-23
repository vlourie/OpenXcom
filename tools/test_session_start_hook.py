"""Проверка хука .claude/hooks/session-start.ps1: в начале сессии агенту подсовываются карта проекта, грабли и очередь правок.

Хук запускается в пустой временной папке-проекте (CLAUDE_PROJECT_DIR), чтобы не пересобирать настоящий .index и не трогать очередь:
- без tools/ и .index/: сообщает, что карты нет; вывод - корректный JSON SessionStart;
- с заглушками tools/rake.py и .index/meta.json: грабли и карта попадают в additionalContext;
- заглушка rake.py падает: хук всё равно отдаёт остальное и выходит с 0 (сессию не роняет).
Запуск: python tools/test_session_start_hook.py   (код 0 - всё верно)
"""
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "hooks", "session-start.ps1")


def run(project):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=project)
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", HOOK],
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=project, timeout=120)
    return r.returncode, r.stdout.strip()


def ctx(out):
    j = json.loads(out)["hookSpecificOutput"]
    return j["hookEventName"], j["additionalContext"]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


bad = 0


def check(name, cond, extra=""):
    global bad
    bad += not cond
    print(("ok   " if cond else "FAIL ") + name + (f": {extra}" if extra and not cond else ""))


with tempfile.TemporaryDirectory() as d:
    # 1. пустой проект
    rc, out = run(d)
    check("пустой проект: код 0", rc == 0, str(rc))
    try:
        ev, text = ctx(out)
        check("пустой проект: событие SessionStart", ev == "SessionStart", ev)
        check("пустой проект: сказано, что карты нет", "Карты проекта нет" in text, text)
        check("пустой проект: грабли не выдуманы", "ГРАБЛИ" not in text, text)
    except Exception as e:
        check("пустой проект: вывод - JSON SessionStart", False, f"{e}: {out!r}")

with tempfile.TemporaryDirectory() as d:
    # 2. заглушки: карта и грабли
    write(os.path.join(d, ".index", "meta.json"),
          json.dumps({"files": 12, "symbols": 345, "built_human": "сегодня"}, ensure_ascii=False))
    write(os.path.join(d, "tools", "rake.py"), "print('R-999 stub rule')  # ASCII: stdout python в пайпе может быть cp1252\n")
    rc, out = run(d)
    check("заглушки: код 0", rc == 0, str(rc))
    try:
        ev, text = ctx(out)
        check("заглушки: карта проекта в контексте", "12 файлов, 345 символов" in text, text)
        check("заглушки: совет искать грепом по symbols.tsv", "symbols.tsv" in text, text)
        check("заглушки: грабли в контексте", "ГРАБЛИ ПРОЕКТА" in text and "R-999" in text, text)
        check("заглушки: команды match/find/hit", "rake.py match" in text and "rake.py hit" in text, text)
    except Exception as e:
        check("заглушки: вывод - JSON SessionStart", False, f"{e}: {out!r}")

with tempfile.TemporaryDirectory() as d:
    # 3. rake.py падает, meta.json битый: хук не роняет сессию
    write(os.path.join(d, ".index", "meta.json"), "{не json")
    write(os.path.join(d, "tools", "rake.py"), "raise SystemExit(3)\n")
    rc, out = run(d)
    check("сломанные карта и rake.py: код 0", rc == 0, str(rc))
    if out:
        try:
            ev, text = ctx(out)
            check("сломанные карта и rake.py: вывод - JSON SessionStart", ev == "SessionStart", ev)
        except Exception as e:
            check("сломанные карта и rake.py: вывод - JSON", False, f"{e}: {out!r}")
    else:
        check("сломанные карта и rake.py: тихо", True)

print("ВСЁ ВЕРНО" if bad == 0 else f"ОШИБОК: {bad}")
sys.exit(1 if bad else 0)
