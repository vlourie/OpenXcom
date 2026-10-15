# Проверка хуков граблей: .claude/hooks/rake-check.ps1 (PreToolUse на Edit/Write),
# .claude/hooks/session-start.ps1 (SessionStart) и поиска rake.py match/find/show.
# Грабли доходят до МОДЕЛИ только через hookSpecificOutput.additionalContext: systemMessage
# видит лишь человек (аудит кода 05.10.2026). С 15.10.2026 (аудит кредитов) хук правки даёт
# не больше трёх кратких правил и не повторяет уже показанные в сессии
# (.index/rake-seen/<session_id>.txt), хук старта - короткий индекс вместо списка всех граблей.
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
START = ROOT / ".claude" / "hooks" / "session-start.ps1"
SEEN = ROOT / ".index" / "rake-seen"
SID_A, SID_B = "test-rake-check-a", "test-rake-check-b"
MAX_RULES = 3        # записей за одну правку
MAX_CHARS = 3000     # знаков на вброс хука правки (три кратких правила с заголовком)
MAX_START = 6000     # знаков на весь контекст хука старта
ENTRY = re.compile(r"^(?:!!|--|  ) (R-\d{3})  ", re.M)   # строка записи в формате rake.fmt


def ps(script, stdin=""):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT))
    p = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        input=stdin.encode("utf-8"), capture_output=True, env=env, cwd=str(ROOT), timeout=180,
    )
    return p.returncode, p.stdout.decode("utf-8", errors="replace").strip()


def run_hook(file_path, session_id=None):
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": file_path, "old_string": "a", "new_string": "b"},
    }
    if session_id:
        event["session_id"] = session_id
    return ps(HOOK, json.dumps(event))


def rake(*args):
    p = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "rake.py"), *args],
        capture_output=True, cwd=str(ROOT), timeout=120,
    )
    return p.returncode, p.stdout.decode("utf-8", errors="replace").strip()


def ctx_of(out, fails, label):
    try:
        data = json.loads(out) if out else {}
    except json.JSONDecodeError as e:
        fails.append(f"{label}: ответ хука не JSON: {e}: {out[:200]!r}")
        return "", {}
    hso = data.get("hookSpecificOutput") or {}
    return hso.get("additionalContext") or "", hso


def entries(text):
    return ENTRY.findall(text)


def cleanup():
    for sid in (SID_A, SID_B):
        f = SEEN / f"{sid}.txt"
        if f.exists():
            f.unlink()


def main():
    fails = []
    cleanup()

    target = ".claude/hooks/bom-guard.ps1"   # *.ps1: R-001, R-002, R-055, R-090 и другие
    full = rake("match", target)[1]
    expected = entries(full)
    if len(expected) <= MAX_RULES:
        print(f"ПРОПУСК: у {target} всего {len(expected)} граблей - лимит и повторы проверять нечем")
        return 0
    # путь - с прямыми косыми: так тоже приходит от инструментов, и хук обязан его обрезать до корня
    path = str(ROOT / target).replace(os.sep, "/")

    # 1. первая правка в сессии A: не больше трёх кратких правил, все - из rake.py match
    code, out = run_hook(path, SID_A)
    if code != 0:
        fails.append(f"хук вернул код {code}")
    ctx, hso = ctx_of(out, fails, "первая правка")
    if hso.get("hookEventName") != "PreToolUse":
        fails.append("нет hookSpecificOutput.hookEventName = PreToolUse")
    if not ctx.startswith("ГРАБЛИ на"):
        fails.append(f"additionalContext не начинается с 'ГРАБЛИ на': {ctx[:120]!r}")
    first = entries(ctx)
    if not first:
        fails.append("первая правка: ни одной записи граблей")
    if len(first) > MAX_RULES:
        fails.append(f"первая правка: {len(first)} записей, лимит {MAX_RULES}")
    if len(ctx) > MAX_CHARS:
        fails.append(f"первая правка: {len(ctx)} знаков, больше {MAX_CHARS}")
    bad = [r for r in first if r not in expected]
    if bad:
        fails.append(f"первая правка: {', '.join(bad)} не из rake.py match {target}")
    if ctx.count("Правило:") != len(first):
        fails.append(f"первая правка: строк 'Правило:' {ctx.count('Правило:')} при {len(first)} записях")

    # 2. та же сессия, тот же файл: показанное не повторяется, идут следующие подходящие
    code, out = run_hook(path, SID_A)
    ctx2, _ = ctx_of(out, fails, "вторая правка")
    second = entries(ctx2)
    dup = sorted(set(first) & set(second))
    if dup:
        fails.append(f"вторая правка той же сессии повторила {', '.join(dup)}")
    if not second:
        fails.append("вторая правка той же сессии: пусто, хотя непоказанные грабли ещё есть")
    if len(second) > MAX_RULES:
        fails.append(f"вторая правка: {len(second)} записей, лимит {MAX_RULES}")

    # 3. другая сессия видит те же первые записи заново (порядок детерминированный)
    code, out = run_hook(path, SID_B)
    ctx3, _ = ctx_of(out, fails, "другая сессия")
    if entries(ctx3) != first:
        fails.append(f"другая сессия: ожидал {first}, получил {entries(ctx3)}")

    # 4. контроль: файл без граблей - хук молчит
    control = "LICENSE"
    if rake("match", control)[1]:
        print(f"ПРОПУСК контроля: у {control} есть грабли, нужен другой файл")
    else:
        code, out = run_hook(str(ROOT / control).replace(os.sep, "/"), SID_A)
        if code != 0 or out:
            fails.append(f"контроль {control}: ожидал пустой ответ, получил код {code}, {out[:120]!r}")

    # 5. поиск вне хука: полный match даёт все записи, find - по теме, show - запись целиком
    if "Правило:" not in full or len(set(expected)) != len(expected):
        fails.append("rake.py match без ключей не даёт полный список с текстом правил")
    code, out = rake("find", "BOM")
    if "R-001" not in entries(out):
        fails.append(f"find BOM не нашёл R-001: {out[:200]!r}")
    code, out = rake("show", "R-001")
    if not out.startswith("## R-001") or "Правило:" not in out:
        fails.append(f"show R-001 не отдал запись целиком: {out[:200]!r}")

    # 6. хук старта: короткий индекс и команды поиска, а не список всех граблей
    code, out = ps(START, "{}")
    ctx6, hso6 = ctx_of(out, fails, "хук старта")
    if hso6.get("hookEventName") != "SessionStart":
        fails.append("хук старта: нет hookSpecificOutput.hookEventName = SessionStart")
    n = len(entries(ctx6))
    if n == 0 or n > 12:
        fails.append(f"хук старта: {n} записей граблей, ожидал 1..12")
    if "rake.py match" not in ctx6 or "rake.py find" not in ctx6:
        fails.append("хук старта не говорит, как искать грабли по файлу и по теме")
    if len(ctx6) > MAX_START:
        fails.append(f"хук старта: {len(ctx6)} знаков, ожидал до {MAX_START}")

    cleanup()
    if fails:
        for f in fails:
            print("ОШИБКА:", f)
        return 1
    print(f"всё верно: хук правки - до {MAX_RULES} кратких правил без повторов в сессии "
          f"({len(ctx)} знаков), хук старта - индекс ({len(ctx6)} знаков), match/find/show работают")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
