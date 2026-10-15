"""Проверка хука .claude/hooks/pack-guard.ps1: папка HD-пака - только выход build_hd_pack (Pipeline v2, R-087).

Гоняет хук на командах, которые он обязан остановить (копирование, перенос, удаление, перенаправление в
mods/hd/hd - обе копии мода, оба вида косой), и на тех, которые обязан пропустить (чтение, копирование
ИЗ пака наружу, сам сборщик).
Запуск: python tools/test_pack_guard.py   (код 0 - всё верно)
"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "pack-guard.ps1")
GAME = "E:/OpenXCom/Пиратки/Dioxine_XPiratez/user/mods/hd/hd"
BS = chr(92)

DENY = {
    "cp в игру": f"cp art/objects/photo/FRNITURE.PCK/8.png {GAME}/TERRAIN/FRNITURE.PCK/8.png",
    "cp -r в репозиторную копию": "cp -r art/x/TERRAIN user/mods/hd/hd/",
    "mv в пак": f"mv a.png '{GAME}/TERRAIN/A.PCK/1.png'",
    "rm из пака": f"rm {GAME}/TERRAIN/A.PCK/1.png",
    "robocopy в пак": f"robocopy art/objects/photo {GAME}/TERRAIN //E",
    "Copy-Item с обратной косой": "Copy-Item x.png " + GAME.replace("/", BS) + BS + "TERRAIN",
    "Remove-Item": f"Remove-Item -Recurse {GAME}/FX",
    "перенаправление": f"cat a.png > {GAME}/UI/a.png",
    "после cd и &&": f"cd /e/OpenXCom && cp x.png {GAME}/UI/x.png",
    "tee": f"echo 1 | tee {GAME}/x.txt",
}
ALLOW = {
    "ls пака": f"ls {GAME}/TERRAIN | head",
    "find и wc": f"find {GAME} -type f | wc -l",
    "du": f"du -sh {GAME}",
    "sha256sum": f"sha256sum {GAME}/TERRAIN/A.PCK/1.png",
    "копия ИЗ пака наружу": f"cp {GAME}/TERRAIN/A.PCK/1.png C:/tmp/1.png",
    "сборщик": "PYTHONIOENCODING=utf-8 py -3.13 tools/hdart/build_hd_pack.py install --yes --target game",
    "сборщик с путями пака": f"py -3.13 tools/hdart/build_hd_pack.py adopt --by map_update {GAME}/x",
    "другая папка мода": "cp a.yml user/mods/hd/metadata.yml",
    "команда без пака": "cp a b",
    "grep по пути": "grep -rn mods/hd/hd tools/",
}


def decide(cmd):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "E:/OpenXCom"}
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", HOOK],
                       input=json.dumps(ev, ensure_ascii=False), capture_output=True, text=True, encoding="utf-8")
    out = r.stdout.strip()
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "allow"


bad = 0
for name, cmd in DENY.items():
    d = decide(cmd)
    ok = d == "deny"
    bad += not ok
    print(("ok   " if ok else "FAIL ") + "остановлено: " + name + ("" if ok else " (" + d + ")"))
for name, cmd in ALLOW.items():
    d = decide(cmd)
    ok = d == "allow"
    bad += not ok
    print(("ok   " if ok else "FAIL ") + "пропущено: " + name + ("" if ok else " (" + d + ")"))
print("итог: %s" % ("всё прошло" if not bad else "упало %d" % bad))
sys.exit(1 if bad else 0)
