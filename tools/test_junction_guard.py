"""Проверка хука .claude/hooks/junction-guard.ps1: папки с соединениями не переносить, не копировать
рекурсивно, не удалять рекурсивно и не обмерять du (R-047).

Во временной папке создаётся рабочая папка боя arena_t_X_w0 с соединением mods на другую временную
папку (как у стенда ИИ), папка без соединения и файл. Хук обязан остановить опасные команды и
пропустить безопасные. Контроль: те же опасные команды на папке без соединения проходят.
Запуск: python tools/test_junction_guard.py   (код 0 - всё верно)
"""
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "junction-guard.ps1")

tmp = tempfile.mkdtemp(prefix="junction_guard_")
target = os.path.join(tmp, "install_mods")
os.makedirs(os.path.join(target, "Piratez"))
arena = os.path.join(tmp, "arena_t_X_w0")
os.makedirs(arena)
with open(os.path.join(arena, "options.cfg"), "w") as f:
    f.write("x")
r = subprocess.run(["cmd", "/c", "mklink", "/J", os.path.join(arena, "mods"), target], capture_output=True, text=True)
if r.returncode != 0:
    print("не удалось создать соединение:", r.stdout, r.stderr)
    sys.exit(2)
deep = os.path.join(tmp, "BrutalAI", "user_pzs_w01")
os.makedirs(deep)
subprocess.run(["cmd", "/c", "mklink", "/J", os.path.join(deep, "mods"), target], capture_output=True, check=True)
plain = os.path.join(tmp, "plain_dir")
os.makedirs(os.path.join(plain, "sub"))
with open(os.path.join(tmp, "a.rec"), "w") as f:
    f.write("x")

DENY = {
    "mv папки боя": "mv arena_t_X_w0 /c/tmp/",
    "mv по шаблону": "mv arena_t_* /c/tmp/",
    "rm -rf": "rm -rf arena_t_X_w0",
    "du": "du -sh arena_t_X_w0",
    "cp -r": "cp -r arena_t_X_w0 /c/tmp/x",
    "cp -a": "cp -a arena_t_X_w0 /c/tmp/x",
    "после cd и &&": "cd . && mv arena_t_X_w0 x",
    "соединение глубоко": "du -sh BrutalAI",
    "в цикле for": "for d in arena_t_*; do mv arena_t_X_w0 /c/x; done",
    "Move-Item": "Move-Item -Path arena_t_X_w0 -Destination C:/tmp",
    "Remove-Item -Recurse": "Remove-Item -Recurse -Force arena_t_X_w0",
    "robocopy": "robocopy arena_t_X_w0 C:/tmp/x //E",
    "само соединение mv": "mv arena_t_X_w0/mods /c/x",
}
ALLOW = {
    "rmdir соединения": "rmdir arena_t_X_w0/mods",
    "файл записи": "mv a.rec /c/tmp/",
    "rm файла": "rm -f a.rec",
    "rm без -r по папке": "rm arena_t_X_w0",
    "ls": "ls -d arena_t_*",
    "cp файла": "cp a.rec b.rec",
    "по разрешению": "JUNCTION_OK=1 mv arena_t_X_w0 /c/x",
    "Remove-Item -Force файла": "Remove-Item -Force a.rec",
    "нет такой папки": "mv nothing_here x",
}
CONTROL = {
    "контроль mv": "mv plain_dir x",
    "контроль rm -rf": "rm -rf plain_dir",
    "контроль du": "du -sh plain_dir",
    "контроль cp -r": "cp -r plain_dir x",
}


def decide(cmd):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": tmp}
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", HOOK],
                       input=json.dumps(ev), capture_output=True, text=True, encoding="utf-8")
    out = r.stdout.strip()
    if not out:
        return "allow"
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"]


bad = 0
for name, cmd in DENY.items():
    d = decide(cmd)
    ok = d == "deny"
    bad += not ok
    print(("ок  " if ok else "ОШИБКА ") + f"остановить: {name}: {d}")
for name, cmd in list(ALLOW.items()) + list(CONTROL.items()):
    d = decide(cmd)
    ok = d == "allow"
    bad += not ok
    print(("ок  " if ok else "ОШИБКА ") + f"пропустить: {name}: {d}")

# снимаем соединения rmdir, цель остаётся
for j in (os.path.join(arena, "mods"), os.path.join(deep, "mods")):
    os.rmdir(j)
assert os.path.isdir(os.path.join(target, "Piratez"))
print("ошибок:", bad)
sys.exit(1 if bad else 0)
