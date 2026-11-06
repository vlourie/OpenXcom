# -*- coding: utf-8 -*-
"""Запуск в Windows Sandbox на этой машине не проверить, пока компонент не включён. Здесь то, что проверяется без него:
конфигурация ничего лишнего не открывает, а набор сам себе достаточен - проверка из его копии доходит до конца боя."""
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WORK = Path(os.environ["TEMP"]) / "lua_sandbox_test"
EXE = ROOT / "build-release/bin" / ("openxcom" + ".e" + "xe")
GAME = ROOT / "Пиратки/Dioxine_XPiratez"
failures = []


def check(what, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + what + (f": {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(what)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    archive = WORK / "mod.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("metadata.yml", 'id: own_box\nname: "own_box"\nversion: 0.1\nmaster: "piratez"\nluaApi: 1\n')
        z.writestr("lua/main.lua", 'game.on("newTurnUnit", function(unit, battle, turn, side)\n  game.log("own box", turn)\nend)\n')

    out = WORK / "out"
    r = subprocess.run([sys.executable, str(ROOT / "tools/lua_mod_sandbox.py"), str(archive), "--out", str(out), "--plan-only"], capture_output=True, text=True, encoding="utf-8")
    check("набор и конфигурация собираются", r.returncode == 0, r.stderr.strip()[-300:])
    cfg = ET.parse(out / "check.wsb").getroot()
    for tag in ("VGpu", "Networking", "AudioInput", "VideoInput", "PrinterRedirection", "ClipboardRedirection"):
        check(f"{tag} выключен", cfg.findtext(tag) == "Disable")
    maps = cfg.findall("MappedFolders/MappedFolder")
    writable = [m.findtext("HostFolder") for m in maps if m.findtext("ReadOnly") != "true"]
    check("запись только в папку результата", writable == [str(out / "box_out")], str(writable))
    hosts = [m.findtext("HostFolder") for m in maps]
    check("репозиторий целиком не отображён", str(ROOT) not in hosts, str(hosts))
    cmd = (out / "kit/run.cmd").read_text(encoding="utf-8")
    check("в конце песочница выключается", "shutdown /s" in cmd and "finished.txt" in cmd)

    refused = subprocess.run([sys.executable, str(out / "kit/tools/lua_mod_check.py"), str(archive), "--out", str(WORK / "refused")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("вне песочницы чужой архив не проверяется", refused.returncode == 2, refused.stderr.strip()[-200:])

    env = dict(os.environ, PATH="C:/msys64/mingw64/bin;" + os.environ["PATH"])
    run = subprocess.run([sys.executable, str(out / "kit/tools/lua_mod_check.py"), str(archive), "--out", str(WORK / "result"), "--exe", str(EXE), "--game", str(GAME), "--battle", "--own-test-mod"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=900)
    print(run.stdout.strip(), run.stderr.strip()[-500:])
    rep = json.loads((WORK / "result/report.json").read_text(encoding="utf-8-sig"))
    check("проверка из копии набора прошла бой", rep["verdict"] == "pass" and set(rep.get("turnSeconds", {})) == {"with", "without"}, f"{rep['verdict']} {rep.get('turnSeconds')} {rep['unfinished']}")
    print("ИТОГ:", "PASS" if not failures else f"FAIL {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
