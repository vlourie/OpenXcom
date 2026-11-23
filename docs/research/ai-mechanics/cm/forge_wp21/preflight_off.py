"""AI FORGE WP2.1, final OFF: everything read on rabota itself, nothing from the runner's records. No battle starts here: run_cm stops at an unknown scenario."""
import hashlib
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
F = Path(__file__).resolve().parent
ST = F.parent / "cm" / "st"
KEY = str(Path.home() / ".ssh" / "oxce_worker")
HOST = "user@100.93.184.94"
R = "C:\\OXCE_AIWorker\\cmrun"
X = "openxcom" ".exe"


def ssh(cmd):
    p = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-i", KEY, HOST, cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout, p.stderr


def ps(cmd):
    return ssh(f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{cmd}"')[0]


print("== files on rabota")
print(ps(f"Get-FileHash '{R}\\exe\\FX\\{X}','{R}\\exe\\D0\\{X}','{R}\\run_cm.py','{R}\\env_FX.txt','{R}\\env_D0.txt' | ForEach-Object {{ $_.Hash + ' ' + $_.Path }}"))
print(ps(f"Get-Item '{R}\\exe\\FX\\{X}' | ForEach-Object {{ $_.FullName + ' ' + $_.Length + ' ' + $_.LastWriteTime }}"))
print("== frozen", (F / "FROZEN.txt").read_text(encoding="utf-8").splitlines()[0])
print("== env_FX on rabota")
fx = ps(f"Get-Content '{R}\\env_FX.txt'")
print(fx)
print("== env_D0 on rabota")
d0 = ps(f"Get-Content '{R}\\env_D0.txt'")
print(d0)
print("== env_FX with /exe/FX/ -> /exe/D0/ is env_D0:", fx.replace("/exe/FX/", "/exe/D0/") == d0)
print("== arms in run_cm on rabota")
lines = ps(f"Select-String -Path '{R}\\run_cm.py' -Pattern 'YO|YA|YB|YC|COMMON_D0 =|\\\"D\\\":|ENV_KEEP|OXCE_AI_FORGE_' | ForEach-Object {{ $_.LineNumber.ToString() + ': ' + $_.Line }}")
print(lines[:6000])
print("== local run_cm same as on rabota", hashlib.sha256((ST / "run_cm.py").read_bytes()).hexdigest())
print("== task", ps("(Get-ScheduledTask oxce_cmrun).State"))
print("== running game processes", ps("(Get-Process openxcom -ErrorAction SilentlyContinue | Measure-Object).Count"))
print("== OXCE variables in the machine and user environment", ps("[Environment]::GetEnvironmentVariables('Machine').Keys + [Environment]::GetEnvironmentVariables('User').Keys | Where-Object { $_ -like 'OXCE*' }"))
