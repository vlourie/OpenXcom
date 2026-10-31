"""Проверка хука .claude/hooks/game-guard.ps1: игра для проверки запускается только невидимо (R-124).

Гоняет хук на командах, которые он обязан остановить, и на тех, которые обязан пропустить.
Скрипты-запускатели создаются во временной папке: видимый (Start-Process -WindowStyle Hidden,
как тот, что показал окно Vitali 28.09) и невидимые (ai_probe.Hidden, SDL_VIDEODRIVER=dummy).
Запуск: python tools/test_game_guard.py   (код 0 - всё верно)
"""
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "game-guard.ps1")
EXE = "E:/OpenXCom/build-release/bin/openxcom.exe"
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..")).replace(os.sep, "/")

tmp = tempfile.mkdtemp(prefix="game_guard_")
SCRIPTS = {
    "visible.ps1": f"$p = Start-Process -FilePath '{EXE}' -WindowStyle Hidden -PassThru\n",
    "visible.py": f"import subprocess\nsubprocess.Popen(['{EXE}', '-load', 'x.sav'])\n",
    "hidden.py": f"import ai_probe\np = ai_probe.Hidden(['{EXE}'], '.', env)\n",
    "dummy.sh": f"SDL_VIDEODRIVER=dummy {EXE} -load x.sav\n",
    "nogame.py": "print('hello')\n",
}
for name, text in SCRIPTS.items():
    with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
        f.write(text)

DENY = {
    "exe напрямую": f"{EXE} -load x.sav",
    "exe после cd": "cd /e/OpenXCom/build-release/bin && ./openxcom.exe -data x",
    "Start-Process": f"Start-Process -FilePath '{EXE}' -WindowStyle Hidden",
    "вызов &": f"& \"{EXE}\" -fullscreen false",
    "скрипт ps1 с Start-Process": "powershell -NoProfile -File visible.ps1 -Out x",
    "скрипт py с Popen": "PYTHONIOENCODING=utf-8 py -3.13 visible.py --out a",
    "скрипт полным путём": "py -3 " + os.path.join(tmp, "visible.py").replace(os.sep, "/"),
    "замер с окном measure_hd": f"powershell -File {REPO}/tools/measure_hd.ps1",
}
ALLOW = {
    "game_hidden": "PYTHONIOENCODING=utf-8 py -3.13 tools/game_hidden.py --out a.png --clicks 1,2",
    "скрипт с ai_probe.Hidden": "py -3.13 hidden.py",
    "скрипт с dummy": "sh dummy.sh",
    "exe с dummy": f"SDL_VIDEODRIVER=dummy {EXE} -load x.sav",
    "скрипт без игры": "py -3 nogame.py",
    "grep": "grep -n openxcom.exe tools/*.py",
    "taskkill": "taskkill //IM openxcom.exe //F",
    "Get-Process": "Get-Process openxcom -ErrorAction SilentlyContinue",
    "ninja": "cd build-release && ninja",
    "по просьбе Vitali": f"GAME_VISIBLE=1 {EXE} -load x.sav",
    "сборка build.ps1": f"powershell -File {REPO}/tools/build/build.ps1 -Target Exe",
    "путь репозитория в команде": "cd /e/OpenXCom && py -3 tools/editq.py list",
}


def decide(cmd):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": tmp}
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", HOOK],
                       input=json.dumps(ev), capture_output=True, text=True, encoding="utf-8")
    out = r.stdout.strip()
    return "deny" if '"deny"' in out else "allow"


bad = 0
for want, cases in (("deny", DENY), ("allow", ALLOW)):
    for name, cmd in cases.items():
        got = decide(cmd)
        mark = "ok " if got == want else "ОШИБКА"
        if got != want:
            bad += 1
        print(f"{mark} {want:5} {name}: {got}")
print("всё верно" if not bad else f"ошибок: {bad}")
sys.exit(1 if bad else 0)
