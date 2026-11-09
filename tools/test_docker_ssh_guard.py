"""Проверка хука .claude/hooks/docker-ssh-guard.ps1: через ssh не собирать и не скачивать образы Docker (R-510).

Хук обязан остановить docker build / pull / compose --build / station.ps1 up на удалённой стороне ssh
и пропустить docker run / exec / ps / rm, локальный docker и команды без docker.
Запуск: python tools/test_docker_ssh_guard.py   (код 0 - всё верно)
"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "docker-ssh-guard.ps1")
H = "ssh -i ~/.ssh/oxce_worker -o BatchMode=yes user@100.83.70.95"

DENY = {
    "build": f'{H} "cd /d C:/wine-test & docker build -t x ."',
    "build через обёртку": f'{H} "cd /d C:/wine-test & d.cmd build -t x ."',
    "pull": f'{H} "docker pull ubuntu:24.04"',
    "buildx": f'{H} "docker buildx build ."',
    "compose up --build": f'{H} "cd C:/xp-portal/portal/deploy; docker compose -f compose.station.yaml up -d --build"',
    "compose pull": f'{H} "docker compose pull"',
    "station.ps1 up": f'{H} "cd C:/xp-portal/portal/deploy; powershell -File .\\station.ps1 up"',
    "ssh.exe": f'ssh.exe user@100.93.184.94 "docker pull postgres:15"',
}
ALLOW = {
    "run": f'{H} "docker run -d --name t --entrypoint sleep postgres:15 infinity"',
    "exec": f'{H} "docker exec t bash /work/g.sh log"',
    "ps": f'{H} "docker ps -a"',
    "rm": f'{H} "docker rm -f t"',
    "station.ps1 releases": f'{H} "powershell -File .\\station.ps1 releases C:/XPiratezModHD/a.zip"',
    "локальный build": "docker build -t x .",
    "scp": "scp -q a.zip user@100.83.70.95:C:/XPiratezModHD/",
    "по разрешению": f'DOCKER_SSH_OK=1 {H} "docker pull ubuntu:24.04"',
    "слово ssh в пути": "docker build -t x ~/.ssh_tools",
}


def decide(cmd):
    ev = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": os.getcwd()})
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", HOOK],
                       input=ev, capture_output=True, text=True, encoding="utf-8")
    out = r.stdout.strip()
    if not out:
        return "allow"
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"]


bad = 0
for name, cmd in DENY.items():
    d = decide(cmd)
    ok = d == "deny"
    bad += not ok
    print(("ok   " if ok else "FAIL ") + f"deny  {name}: {d}")
for name, cmd in ALLOW.items():
    d = decide(cmd)
    ok = d == "allow"
    bad += not ok
    print(("ok   " if ok else "FAIL ") + f"allow {name}: {d}")
print("ВСЁ ВЕРНО" if bad == 0 else f"ОШИБОК: {bad}")
sys.exit(1 if bad else 0)
