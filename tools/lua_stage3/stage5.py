# -*- coding: utf-8 -*-
"""Стадия 5 автопроверки на наших собственных модах: Пиратки и ванильный UFO, бои невидимо (LUA_MODS.md §8.2, п. 5).
Чужих модов здесь нет, поэтому --own-test-mod: вне Windows Sandbox чужой архив проверка не примет."""
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CHECK = ROOT / "tools/lua_mod_check.py"
EXE = ROOT / "build-release/bin" / ("openxcom" + ".e" + "xe")
PIRATES = ROOT / "Пиратки/Dioxine_XPiratez"
UFO = ROOT / "bin"
WORK = Path(os.environ["TEMP"]) / "lua_stage5"

GOOD = 'game.on("newTurnUnit", function(unit, battle, turn, side)\n  game.log("own test: turn", turn, "side", side)\nend)\n'
BAD = 'game.on("newTurnUnit", function(unit, battle, turn, side)\n  error("own test: this mod fails on purpose")\nend)\n'
SLOW = 'game.on("newTurnUnit", function(unit, battle, turn, side)\n  while true do end\nend)\n'
failures = []


def check(what, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + what + (f": {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(what)


def run(name, mod_id, master, lua, game):
    out = WORK / name
    out.mkdir(parents=True, exist_ok=True)
    archive = out.parent / f"{name}.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("metadata.yml", f'id: {mod_id}\nname: "{mod_id}"\nversion: 0.1\nmaster: "{master}"\nluaApi: 1\n')
        z.writestr("lua/main.lua", lua)
    env = dict(os.environ, PATH="C:/msys64/mingw64/bin;" + os.environ["PATH"])
    r = subprocess.run([sys.executable, str(CHECK), str(archive), "--out", str(out), "--exe", str(EXE), "--game", str(game), "--battle", "--own-test-mod"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=1800)
    print(r.stdout.strip() + r.stderr.strip()[-500:], flush=True)
    return r.returncode, json.loads((out / "report.json").read_text(encoding="utf-8-sig"))


def codes(report, key):
    return [x["code"] for x in report[key]]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    code, rep = run("good_pirates", "own_good", "piratez", GOOD, PIRATES)
    check("Пиратки: рабочий мод проходит", code == 0, str(rep["unfinished"]))
    check("Пиратки: ходы посчитаны с модом и без", set(rep.get("turnSeconds", {})) == {"with", "without"}, str(rep.get("turnSeconds")))
    check("Пиратки: мод писал в журнал", "lua_silent" not in codes(rep, "signals"), str(codes(rep, "signals")))

    code, rep = run("bad_pirates", "own_bad", "piratez", BAD, PIRATES)
    check("Пиратки: ошибки Lua - сигнал, не отказ", code == 0 and "lua_errors" in codes(rep, "signals"), f"код {code}, {codes(rep, 'signals')}")

    code, rep = run("hang_pirates", "own_hang", "piratez", SLOW, PIRATES)
    check("Пиратки: бесконечный цикл остановлен песочницей, игра живёт", code == 0 and "lua_limits" in codes(rep, "signals"), f"код {code}, {codes(rep, 'signals')}, {codes(rep, 'errors')}")

    code, rep = run("good_ufo", "own_ufo", "xcom1", GOOD, UFO)
    check("UFO: рабочий мод проходит", code == 0, str(rep["unfinished"]))
    check("UFO: ходы посчитаны с модом и без", set(rep.get("turnSeconds", {})) == {"with", "without"}, str(rep.get("turnSeconds")))
    check("UFO: мод писал в журнал", "lua_silent" not in codes(rep, "signals"), str(codes(rep, "signals")))
    print("ИТОГ:", "PASS" if not failures else f"FAIL {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
