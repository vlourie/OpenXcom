"""Проверка хука .claude/hooks/gpu-guard.ps1: видеокарта только через очередь tools/gpuq.py.

Гоняет хук на командах, которые он обязан остановить, и на тех, которые обязан пропустить.
Запуск: python tools/test_gpu_guard.py   (код 0 - всё верно)
"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "gpu-guard.ps1")
BS = chr(92)

DENY = {
    "python из venv": "tools/hdart/.venv-qwen21/Scripts/python.exe -u tools/hdart/gen_promo.py draw --seeds 4",
    "py -3 с окружением": "PYTHONIOENCODING=utf-8 py -3 tools/hdart/keep_batch.py --hours 48",
    "после cd": "cd /e/OpenXCom && python tools/hdart/map_paint.py --map UBASE_00",
    "путь Windows в кавычках": "\"E:" + BS + "train" + BS + ".venv-train" + BS + "Scripts" + BS
                               + "python.exe\" tools" + BS + "hdart" + BS + "paint3.py --n 32",
    "powershell -File": "powershell -NoProfile -ExecutionPolicy Bypass -File tools/hdart/train_lora.ps1 -Steps 3000",
    ".ps1 первым словом": "& .\\tools\\hdart\\gen_all.ps1 -Data x".replace("\\", BS),
    "nohup в фон": "nohup python tools/hdart/triage/caption.py --all > cap.log 2>&1 &",
    "timeout": "timeout 600 py -3 tools/hdart/score_batch.py --mod user/mods/hd",
    "в конвейере": "python tools/hdart/gen_lora_batch.py --max-plan 10 | tee run.log",
}

ALLOW = {
    "через очередь": "py -3 tools/gpuq.py add --name promo -- tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/gen_promo.py draw",
    "чтение cat": "cat tools/hdart/gen_hd.py",
    "grep по скрипту": "grep -n python tools/hdart/gen_hd.py",
    "grep со словом py в кавычках": "grep -n \"py\" tools/hdart/map_paint.py",
    "git diff": "git diff tools/hdart/gen_lora_batch.py",
    "справка": "python tools/hdart/gen_hd.py --help",
    "пробный прогон": "powershell -File tools/hdart/train_lora.ps1 -DryRun",
    "явный обход": "GPUQ_BYPASS=1 python tools/hdart/score_batch.py --report-only",
    "тест с похожим именем": "python tools/test_map_paint_tiled.py",
    "свой скрипт": "python tools/rake.py hit R-035",
    "Get-Content": "Get-Content tools/hdart/paint3.py -Encoding UTF8",
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
