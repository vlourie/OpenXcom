"""AI FORGE WP2.1, final OFF: the scenario, the full flags and arm on rabota; what the archived D0 recorded of its own run; what the engine's lines hold when the monitor is off. No battle."""
import gzip
import re
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
F = Path(__file__).resolve().parent
S = F.parent
KEY = str(Path.home() / ".ssh" / "oxce_worker")
HOST = "user@100.93.184.94"
R = "C:\\OXCE_AIWorker\\cmrun"


def ps(cmd):
    return subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-i", KEY, HOST, f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{cmd}"'], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


print("== COMMON_D0 and the launch on rabota")
print(ps(f"Get-Content '{R}\\run_cm.py' | Select-Object -Index (27,28,29,30,31,127,137,138,139,140,141,142,143,144,145,146,147,148)"))
print("== arm names on rabota: YO", ps(f"(Select-String -Path '{R}\\run_cm.py' -Pattern '[\\\"]YO[\\\"]:').Count"))
print("== scen.tsv", ps(f"Get-ChildItem '{R}' -Recurse -Filter scen.tsv | Select-Object -First 3 | ForEach-Object {{ $_.FullName; Get-Content $_.FullName | Select-String -Pattern '^(scen|id|name)|^L8' }}"))
print("== last run of the arm D on rabota: logs with its label", ps(f"Get-ChildItem '{R}\\logs' -Filter 'run_sfF*' | ForEach-Object {{ $_.Name; Get-Content $_.FullName -Head 2 }}"))
for name, zp, label in (("D0", S / "sfc" / "res" / "res_sfF.zip", "sfF_D_L8_s1"), ("A1", F / "res" / "res_fxA1.zip", "fxA1_YA_L8_s1")):
    with zipfile.ZipFile(zp) as z:
        members = [m for m in z.namelist() if label in m]
        print("==", name, "members", members[:12])
        text = gzip.decompress(z.read(f"out/{label}/openxcom.log.gz")).decode("utf-8", errors="replace")
    lines = text.splitlines()
    plain = [re.sub(r"^\[[^\]]*\]\s*\[[A-Z]+\]\s*", "", s) for s in lines]
    print("   first lines", [s[:160] for s in plain[:10]])
    print("   lines mentioning the exe or flags", [s[:200] for s in plain if re.search(r"OXCE_AI_|exe|Version|version", s) and not s.startswith("[AI")][:12])
    kinds = Counter(re.match(r"(\[AI[A-Z0-9_]*\])", s).group(1) for s in plain if re.match(r"\[AI[A-Z0-9_]*\]", s))
    print("   engine line kinds", dict(kinds))
    dec = next((s for s in plain if s.startswith("[AIDECIDE]")), "")
    print("   a decide line", dec[:700])
    print("   lines with rng", sum(1 for s in plain if s.startswith("[AI") and re.search(r"\brng\b|rng=", s)), next((s[:300] for s in plain if s.startswith("[AI") and re.search(r"\brng\b|rng=", s)), None))
    rec = next((s for s in plain if s.startswith("[AIREC]")), "")
    print("   a record line", rec[:900])
