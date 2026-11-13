"""Проверка хука .claude/hooks/guard-paths.ps1: запрет правок установленной игры, оригинальных данных и вывода сборки.

Главное: в Пиратки, bin/UFO, bin/TFTD, build-release, dist, game и в папку HD-пака (user/mods/hd/hd/) писать нельзя (deny);
bin/common и bin/standard - только после подтверждения (ask, R-003); наш мод внутри Пираток (user/mods/hd/) и обычный код - пропуск.
Запуск: python tools/test_guard_paths_guard.py   (код 0 - всё верно)
"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "hooks", "guard-paths.ps1")
R = "E:/OpenXCom"

# (имя, поле пути, путь, ожидаемое решение)
CASES = [
    ("Пиратки: файл мода игры", "file_path", f"{R}/Пиратки/Dioxine_XPiratez/standard/Xcom1Ruleset/Piratez.rul", "deny"),
    ("Пиратки: обратные косые", "file_path", "E:\\OpenXCom\\Пиратки\\Dioxine_XPiratez\\common\\Language\\ru.yml", "deny"),
    ("Пиратки: соседний user/mods", "file_path", f"{R}/Пиратки/Dioxine_XPiratez/user/mods/other/x.rul", "deny"),
    ("Пиратки: через поле path", "path", f"{R}/Пиратки/readme.txt", "deny"),
    ("Пиратки: через notebook_path", "notebook_path", f"{R}/Пиратки/a.ipynb", "deny"),
    ("bin/UFO", "file_path", f"{R}/bin/UFO/GEODATA/PALETTES.DAT", "deny"),
    ("bin/TFTD", "file_path", f"{R}/bin/TFTD/GEODATA/PALETTES.DAT", "deny"),
    ("build-release", "file_path", f"{R}/build-release/CMakeCache.txt", "deny"),
    ("dist", "file_path", f"{R}/dist/UI/a.png", "deny"),
    ("game", "file_path", f"{R}/game/openxcom.exe", "deny"),
    ("HD-пак мода, прямые косые", "file_path", f"{R}/user/mods/hd/hd/sprites/a.png", "deny"),
    ("HD-пак внутри Пираток", "file_path", f"{R}/Пиратки/Dioxine_XPiratez/user/mods/hd/hd/a.png", "deny"),
    ("HD-пак, обратные косые", "file_path", "E:\\OpenXCom\\user\\mods\\hd\\hd\\b.png", "deny"),
    ("bin/common: подтверждение", "file_path", f"{R}/bin/common/Language/ru.yml", "ask"),
    ("bin/standard: подтверждение", "file_path", f"{R}/bin/standard/Xcom1Ruleset/x.rul", "ask"),
    ("bin/standard, обратные косые", "file_path", "E:\\OpenXCom\\bin\\standard\\x.rul", "ask"),
    ("наш мод в Пиратках: рулсет", "file_path", f"{R}/Пиратки/Dioxine_XPiratez/user/mods/hd/Ruleset/hd.rul", "allow"),
    ("наш мод в Пиратках: metadata", "file_path", "E:\\OpenXCom\\Пиратки\\Dioxine_XPiratez\\user\\mods\\hd\\metadata.yml", "allow"),
    ("рулсет мода hd в репозитории", "file_path", f"{R}/user/mods/hd/Ruleset/hd.rul", "allow"),
    ("исходник движка", "file_path", f"{R}/src/Engine/Game.cpp", "allow"),
    ("документ", "file_path", f"{R}/docs/BACKLOG.md", "allow"),
    ("инструмент", "path", f"{R}/tools/rake.py", "allow"),
    ("слово dist в имени файла", "file_path", f"{R}/tools/redist/a.py", "allow"),
    ("слово game в имени файла", "file_path", f"{R}/tools/game_guard.py", "allow"),
    ("слово bin без common/standard", "file_path", f"{R}/bin/other/x.txt", "allow"),
]


def decide(raw):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", HOOK],
                       input=raw, capture_output=True, text=True, encoding="utf-8")
    out = r.stdout.strip()
    if not out:
        return "allow"
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"]


def event(field, path):
    return json.dumps({"tool_name": "Edit", "tool_input": {field: path}}, ensure_ascii=False)


bad = 0
for name, field, path, want in CASES:
    got = decide(event(field, path))
    ok = got == want
    bad += not ok
    print(("ok   " if ok else "FAIL ") + f"{want:5} {name}: {got}")

# хук не должен ронять сессию: пустой ввод, сломанный JSON, событие без пути - пропуск
for name, raw in [("пустой ввод", ""), ("сломанный JSON", "{не json"),
                  ("без tool_input", "{}"), ("Bash без пути", json.dumps({"tool_input": {"command": "ls Пиратки"}}))]:
    got = decide(raw)
    ok = got == "allow"
    bad += not ok
    print(("ok   " if ok else "FAIL ") + f"allow {name}: {got}")

print("ВСЁ ВЕРНО" if bad == 0 else f"ОШИБОК: {bad}")
sys.exit(1 if bad else 0)
