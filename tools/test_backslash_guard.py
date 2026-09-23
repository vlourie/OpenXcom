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
}


def decision(command):
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}
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
