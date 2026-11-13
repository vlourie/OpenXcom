"""Проверка хука .claude/hooks/backslash-guard.ps1 (грабли R-035).

Гоняет хук на командах, которые он обязан остановить, и на тех, которые обязан пропустить.
Запуск: python tools/test_backslash_guard.py   (код 0 - всё верно)
"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "backslash-guard.ps1")
BS = chr(92)

DENY = {
    "heredoc python": "python - <<'EOF'\ns = s.replace('a', 'Replace(" + BS * 4 + ")')\nEOF",
    "heredoc без кавычек": "cat > f.py <<EOF\nprint('a" + BS + "nb')\nEOF",
    "heredoc <<-": "perl <<-END\n\tprint \"" + BS + "n\";\n\tEND",
    "python -c": "python -c \"print('a" + BS + "nb')\"",
    "py -3 -c": "py -3 -c \"import re; re.sub('" + BS + "d', '', s)\"",
    "perl -e": "perl -e 'print \"" + BS + "n\"'",
    "sed -i": "sed -i 's/a" + BS + ".b/c/' file.txt",
    "sed -E -i": "sed -E -i 's/x" + BS + "s+/y/' file.txt",
    "perl -pi -e": "perl -pi -e 's/x" + BS + "n/y/' file.txt",
    "после cd": "cd /e/OpenXCom; python -c \"print('" + BS + "t')\"",
    "sed s в конвейере": "cat f.cs | sed 's/a" + BS * 2 + "b/c/' > g.cs",
    "sed s с > в файл": "sed 's/x" + BS + "n/y/' in.txt > out.txt",
    "sed -e s в двойных кавычках": "grep x f | sed -e \"s|a" + BS + "|b|c|g\"",
    # R-037: ключ через одну косую Git Bash переводит в путь
    "robocopy /E": "robocopy src dst /E /NFL",
    "taskkill /IM после cd": "cd /e/OpenXCom && taskkill /IM notepad.exe /F",
    "cmd /c": "cmd /c dir",
    # R-184: питон без программы - REPL, у фоновой команды пишет ошибку по кругу
    "py - с пустым heredoc": "cd /c/x && py -3.13 - <<'EOF'\nEOF\necho skip",
    "python - без stdin": "python - ; echo done",
    "py -3.13 без аргументов": "PYTHONIOENCODING=utf-8 py -3.13",
    "python.exe по пути без скрипта": "E:/v/.venv/Scripts/python.exe -u > out.txt",
    # третий раз R-184 (03.10): перенаправление с номером потока прятало питон без программы
    "py - с 2>/dev/null": "cd $S && py -3.13 - 2>/dev/null; grep -n x f.py",
    "python - с 2>&1": "python - 2>&1 | tail -3",
    "py - с 2>/dev/null и пустым heredoc": "py -3.13 - 2>/dev/null <<'EOF'\nEOF",
    # четвёртый раз R-184 (03.10): ключ с аргументом между версией и - , плюс < /dev/null
    "py -3.13 -X utf8 -": "py -3.13 -X utf8 -",
    "python -u -": "python -u -",
    "py -X utf8 - < /dev/null (случай 03.10)":
        "PYTHONIOENCODING=utf-8 py -3.13 -X utf8 - < /dev/null 2>/dev/null; grep -n x f.py",
    "py -3.13 -W ignore - < /dev/null": "py -3.13 -W ignore - < /dev/null",
    "py -Xutf8 слитно без скрипта": "py -3.13 -Xutf8 -u 2>&1 | tail -3",
    "python -i без скрипта": "python -i > out.txt",
    "py -V:3.13 -": "py -V:3.13 - ; echo x",
    # пятый раз R-184 (07.10): питон за словом оболочки do / then не считался началом команды
    "py - < /dev/null за do (случай 07.10)":
        "cd /c/some/dir; for f in a.py b.py; do py -3.13 - < /dev/null 2>/dev/null; done; grep -n \"x\" a.py",
    "while ... do python -": "while true; do python - ; done",
    "if ... then py -X utf8 - < NUL": "if x; then py -3.13 -X utf8 - < NUL; fi",
    "else python -": "if x; then echo; else python -; fi",
    "{ python - ; }": "{ python - ; } 2>&1",
    "! py -": "! py -3.13 - 2>/dev/null",
    "time python -": "time python -",
    "py -X utf8 -c с косой":"py -3.13 -X utf8 -c \"print('a" + BS + "nb')\"",
}

ALLOW = {
    "grep с альтернативой": "grep -n \"a" + BS + "|b\" file.txt",
    "путь Windows": "cd E:" + BS + "OpenXCom && ls",
    "heredoc без косых": "git commit -F - <<'EOF'\nrelease: text\nEOF",
    "косая после heredoc": "cat > f <<'EOF'\nhello\nEOF\ngrep -n \"a" + BS + "|b\" f",
    "sed только чтение": "sed -n '/a" + BS + "|b/p' file.txt",
    "без косых": "python tools/rake.py hit R-035",
    "python со скриптом по пути": "python C:" + BS + "tmp" + BS + "edit.py",
    "PowerShell путь": "Get-Content E:" + BS + "x.txt -Encoding UTF8",
    "sed s без косых": "sed 's/utf-8/utf-8-sig/' f.py > g.py",
    "sed чтение по пути Windows": "sed -n '1,20p' \"E:" + BS + "x.txt\"",
    "sed в конвейере без подстановки": "git log | sed -n '/a" + BS + "|b/p'",
    "robocopy //E": "robocopy src dst //E //NFL",
    "путь /e/ после robocopy": "robocopy /e/OpenXCom/a /e/OpenXCom/b //E",
    "MSYS2_ARG_CONV_EXCL": "MSYS2_ARG_CONV_EXCL='*' robocopy a b /E",
    "ключ в кавычках grep": "grep -n \"taskkill /IM\" tools/x.ps1",
    "ключ в теле heredoc": "git commit -F - <<'EOF'\nhooks: robocopy /E ловится\nEOF",
    "PowerShell-инструмент": ("PS", "robocopy src dst /E"),
    "python - с непустым heredoc": "python - <<'EOF'\nprint(1)\nEOF",
    "конвейер в python -": "cat x.py | python -",
    "python - < файл": "py -3.13 - < x.py",
    "python - 2>&1 < файл": "py -3.13 - 2>&1 < x.py",
    "python - 2>/dev/null с непустым heredoc": "py -3.13 - 2>/dev/null <<'EOF'\nprint(1)\nEOF",
    "py -3.13 со скриптом и 2>&1": "py -3.13 tools/x.py 2>&1 | tail -3",
    "py -3.13 со скриптом": "py -3.13 tools/x.py --a 1",
    "python -m": "python -m pytest -q",
    "python --version": "python --version && py -0p",
    "python в тексте": "grep -n python f.txt; echo use py",
    "py -3.13 -X utf8 со скриптом": "py -3.13 -X utf8 tools/x.py",
    "py -3.13 -m pytest": "py -3.13 -m pytest",
    "py -3.13 -W ignore - < файл": "py -3.13 -W ignore - < f",
    "py -3.13 -X utf8 -c без косой": "py -3.13 -X utf8 -c \"print(1)\"",
    "python -V": "python -V",
    "py -3.13 -u со скриптом 2>&1": "py -3.13 -u -X utf8 tools/x.py 2>&1 | tail",
    "for ... do py \"$f\"": "for f in *.py; do py -3.13 \"$f\"; done",
    "for ... do python скрипт": "for f in a; do python tools/x.py; done",
    "if ... then py скрипт": "if x; then py -3.13 -X utf8 tools/x.py < NUL; fi",
    "do python - с непустым heredoc": "for f in a; do python - <<'EOF'\nprint(1)\nEOF\ndone",
    "слово do в тексте": "echo do python -m x; grep -n 'then py' f.txt",
}


def decision(command):
    tool = "Bash"
    if isinstance(command, tuple):   # ("PS", команда) - вызов из инструмента PowerShell
        tool, command = "PowerShell", command[1]
    event = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command}}
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", HOOK],
                       input=json.dumps(event).encode("utf-8"), capture_output=True, timeout=60)
    return "deny" if b'"deny"' in r.stdout else "allow"


def main():
    bad = 0
    for want, cases in (("deny", DENY), ("allow", ALLOW)):
        for name, cmd in cases.items():
            got = decision(cmd)
            ok = got == want
            bad += not ok
            print(f"{'ok ' if ok else 'ОШИБКА'} {want:5} {name}" + ("" if ok else f"  (хук ответил {got})"))
    print("всё верно" if bad == 0 else f"ошибок: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
