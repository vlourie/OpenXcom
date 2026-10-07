# Проверка хука .claude/hooks/rake-check.ps1 (PreToolUse на Edit/Write).
# Грабли по правимому файлу обязаны доходить до МОДЕЛИ: единственный путь - поле
# hookSpecificOutput.additionalContext в ответе хука. systemMessage видит только человек
# (аудит кода 05.10.2026: правки docs/*.md шли без единого предупреждения, хотя
# .index/rake-hits.log их честно записывал).
# Побочный эффект: каждый запуск дописывает строку в .index/rake-hits.log (как и живой хук).
# Запуск: py -3.13 tools/test_rake_check.py
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "rake-check.ps1"


def run_hook(file_path):
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": file_path, "old_string": "a", "new_string": "b"},
    }
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT))
    p = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HOOK)],
        input=json.dumps(event).encode("utf-8"),
        capture_output=True, env=env, cwd=str(ROOT), timeout=120,
    )
    return p.returncode, p.stdout.decode("utf-8", errors="replace").strip()


def rakes_for(rel):
    p = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "rake.py"), "match", rel],
        capture_output=True, cwd=str(ROOT), timeout=120,
    )
    return p.stdout.decode("utf-8", errors="replace").strip()


def main():
    fails = []

    # 1. файл, по которому грабли точно есть (*.ps1: R-002, R-055, R-090 и другие)
    target = ".claude/hooks/bom-guard.ps1"
    if not rakes_for(target):
        print(f"ПРОПУСК: rake.py match {target} ничего не даёт - проверять нечем")
        return 0
    # путь - с прямыми косыми: так тоже приходит от инструментов, и хук обязан его обрезать до корня
    code, out = run_hook(str(ROOT / target).replace(os.sep, "/"))
    if code != 0:
        fails.append(f"хук вернул код {code}")
    try:
        data = json.loads(out) if out else {}
    except json.JSONDecodeError as e:
        data = {}
        fails.append(f"ответ хука не JSON: {e}: {out[:200]!r}")
    hso = data.get("hookSpecificOutput") or {}
    ctx = hso.get("additionalContext") or ""
    if hso.get("hookEventName") != "PreToolUse":
        fails.append("нет hookSpecificOutput.hookEventName = PreToolUse")
    if not ctx.startswith("ГРАБЛИ на"):
        fails.append(f"additionalContext не начинается с 'ГРАБЛИ на': {ctx[:120]!r}")
    expected = sorted(set(re.findall(r"R-\d{3}", rakes_for(target))))
    missing = [r for r in expected if r not in ctx]
    if not expected:
        fails.append("rake.py match не назвал ни одного номера граблей")
    if missing:
        fails.append(f"в additionalContext нет {', '.join(missing)} (их даёт rake.py match {target})")

    # 2. контроль: файл без граблей - хук молчит
    control = "LICENSE"
    if rakes_for(control):
        print(f"ПРОПУСК контроля: у {control} есть грабли, нужен другой файл")
    else:
        code, out = run_hook(str(ROOT / control).replace(os.sep, "/"))
        if code != 0 or out:
            fails.append(f"контроль {control}: ожидал пустой ответ, получил код {code}, {out[:120]!r}")

    if fails:
        for f in fails:
            print("ОШИБКА:", f)
        return 1
    print("всё верно: грабли доходят до модели через additionalContext, контроль молчит")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
