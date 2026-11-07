# -*- coding: utf-8 -*-
"""Автопроверка чужой заявки на Lua-мод в Windows Sandbox (docs/portal/LUA_MODS.md §8.2, §13 № 3).

Чужие YAML и PNG читает наш C++, а песочница Lua этого не закрывает, поэтому проверка идёт в одноразовой среде:
без сети, без видеокарты, без буфера обмена. Папка записи одна - результат, всё остальное только для чтения.
На станции чужие моды не запускать.

py -3.13 tools/lua_mod_sandbox.py <архив.zip> --out <папка>
    Код 0 пройдено, 1 отказ, 2 проверка не закончена, 3 среда недоступна.
py -3.13 tools/lua_mod_sandbox.py <архив.zip> --out <папка> --plan-only
    Только собрать набор и конфигурацию, ничего не запускать.

Компонент Windows Sandbox включает сам Vitali (§13 № 3), от администратора, с перезагрузкой:
Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsSandbox.exe"
EXE_NAME = "openxcom" + ".e" + "xe"
EXE_DIR = ROOT / "build-release" / "bin"
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez"
PYTHON = Path(sys.base_prefix)
MINGW = Path(json.loads((ROOT / "tools/build/build_config.json").read_text(encoding="utf-8-sig"))["MsysBin"])

# пути рядом со стендом считаются от его папки: набор повторяет дерево репозитория
KIT = ["tools/lua_mod_check.py", "tools/hdbench.py", "tools/ai_probe.py", "tools/hidden_game.py", "tools/build/build_config.json",
       "portal/src/Xp.Launcher.Core/Docs/lua_api.names.txt", "tools/lua_stage1/lua_battle.sav"]
OPTIONS = "Пиратки/Dioxine_XPiratez/user/options.cfg"
BOX = Path(r"C:\lmc")


def make_kit(out, archive):
    """Набор без остального репозитория. Его копия в песочнице пишет на её диск: стенд создаёт папки рядом с собой."""
    kit = out / "kit"
    shutil.rmtree(kit, ignore_errors=True)
    for rel in KIT + [OPTIONS]:
        target = kit / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    inbox = out / "in"
    shutil.rmtree(inbox, ignore_errors=True)
    inbox.mkdir()
    shutil.copy2(archive, inbox / "mod.zip")
    return kit, inbox


def run_cmd(battle, turns):
    script = "\r\n".join([
        "@echo off",
        "chcp 65001 > nul",
        f"set PATH={MINGW};{PYTHON};%PATH%",
        f"xcopy /e /i /q /y {BOX}\\kit {BOX}\\work > nul",
        f"\"{PYTHON}\\python.exe\" {BOX}\\work\\tools\\lua_mod_check.py {BOX}\\in\\mod.zip --out {BOX}\\out\\result --exe {BOX}\\exe\\{EXE_NAME}"
        f" --game {BOX}\\game --turns {turns}{' --battle' if battle else ''} > {BOX}\\out\\check.log 2>&1",
        f"echo %ERRORLEVEL% > {BOX}\\out\\finished.txt",
        "shutdown /s /t 0",
        "",
    ])
    return script


def wsb_xml(kit, inbox, result, exe_dir, game):
    root = ET.Element("Configuration")
    for tag in ("VGpu", "Networking", "AudioInput", "VideoInput", "PrinterRedirection", "ClipboardRedirection"):
        ET.SubElement(root, tag).text = "Disable"
    ET.SubElement(root, "MemoryInMB").text = "8192"
    folders = ET.SubElement(root, "MappedFolders")
    maps = [(PYTHON, PYTHON, True), (MINGW, MINGW, True), (kit, BOX / "kit", True), (inbox, BOX / "in", True),
            (exe_dir, BOX / "exe", True), (game, BOX / "game", True), (result, BOX / "out", False)]
    for host, box, read_only in maps:
        f = ET.SubElement(folders, "MappedFolder")
        ET.SubElement(f, "HostFolder").text = str(host)
        ET.SubElement(f, "SandboxFolder").text = str(box)
        ET.SubElement(f, "ReadOnly").text = "true" if read_only else "false"
    cmd = ET.SubElement(root, "LogonCommand")
    ET.SubElement(cmd, "Command").text = f"{BOX}\\kit\\run.cmd"
    return ET.tostring(root, encoding="unicode")


def plan(archive, out, exe_dir, game, battle, turns):
    out.mkdir(parents=True, exist_ok=True)
    kit, inbox = make_kit(out, archive)
    (kit / "run.cmd").write_text(run_cmd(battle, turns), encoding="utf-8", newline="")
    result = out / "box_out"
    shutil.rmtree(result, ignore_errors=True)
    result.mkdir()
    wsb = out / "check.wsb"
    wsb.write_text(wsb_xml(kit, inbox, result, exe_dir, game), encoding="utf-8")
    return wsb, result


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Автопроверка чужого Lua-мода в Windows Sandbox")
    ap.add_argument("archive", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--exe-dir", type=Path, default=EXE_DIR)
    ap.add_argument("--game", type=Path, default=GAME)
    ap.add_argument("--no-battle", action="store_true", help="без стадии 5: только архив, данные и компиляция")
    ap.add_argument("--turns", type=int, default=2)
    ap.add_argument("--limit", type=int, default=2400, help="предел всей проверки, секунд")
    ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args()

    if not a.plan_only and not RUNNER.exists():
        print("Windows Sandbox не включён: чужую заявку проверять негде. Компонент включает Vitali, команда в начале этого файла.", file=sys.stderr)
        return 3
    wsb, result = plan(a.archive.resolve(), a.out.resolve(), a.exe_dir.resolve(), a.game.resolve(), not a.no_battle, a.turns)
    if a.plan_only:
        print(wsb)
        return 0

    info = subprocess.STARTUPINFO()
    info.dwFlags = subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 7  # свёрнуто, без фокуса: проверка не мешает за компьютером
    box = subprocess.Popen([str(RUNNER), str(wsb)], startupinfo=info)
    done = result / "finished.txt"
    t0 = time.time()
    while not done.exists() and time.time() - t0 < a.limit:
        time.sleep(5)
    if not done.exists():
        box.terminate()
        print(f"Проверка не закончилась за {a.limit} с. Журнал: {result / 'check.log'}", file=sys.stderr)
        return 2
    report = result / "result" / "report.json"
    if not report.exists():
        print(f"Отчёта нет. Журнал: {result / 'check.log'}", file=sys.stderr)
        return 2
    print(f"{json.loads(report.read_text(encoding='utf-8-sig'))['verdict']}: {report.with_suffix('.md')}")
    return int(done.read_text(encoding="ascii", errors="replace").strip() or 2)


if __name__ == "__main__":
    sys.exit(main())
