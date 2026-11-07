# -*- coding: utf-8 -*-
"""Очередь заявок на Lua-моды (docs/portal/LUA_MODS.md §8): те же команды, что у tools/tickets.py, но свой ключ и своя папка.

Обычный разбор тикетов заявок не видит: у его ключа нет категории luamod. Статусы меняет и авторам пишет только командир тикетов.

py -3.13 tools/lua_mods.py pull --no-take          забрать новые заявки в census/lua_mods, статус не меняется
py -3.13 tools/lua_mods.py check 123               очередь -> автопроверка -> разбор; отчёт в папке заявки, check/box_out/result
py -3.13 tools/lua_mods.py check 123 --own-test-mod  наш собственный архив вне песочницы
py -3.13 tools/lua_mods.py reply|note|ask|status|show ...  как в tickets.py

Ключ: BotAccounts на станции с --categories luamod, файл ~/.xp-portal/bot_lua.json.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("XP_BOT_CONFIG", str(Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".xp-portal" / "bot_lua.json"))
os.environ.setdefault("XP_TICKETS_DIR", str(ROOT / "census" / "lua_mods"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lua_mod_sandbox  # noqa: E402
import tickets  # noqa: E402

EXE = ROOT / "build-release" / "bin" / ("openxcom" + ".e" + "xe")
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez"


def folder_of(number):
    return tickets.OUT / tickets.safe_name(tickets.fmt(number))


def archive_of(folder):
    zips = sorted((folder / "files").glob("*.zip"))
    if not zips:
        tickets.die(f"в {folder / 'files'} нет архива: сначала pull")
    return zips[-1]


def game_for(folder):
    """Пиратки или ванильный UFO: бой идёт на той игре, для которой мод заявлен."""
    context = json.loads((folder / "ticket.json").read_text(encoding="utf-8-sig")).get("context") or ""
    return ROOT / "bin" if "master: xcom1" in context else GAME


def check(number, own):
    n = tickets.parse_number(number)
    d = folder_of(n)
    archive = archive_of(d)
    out = d / "check"
    if not own and not lua_mod_sandbox.RUNNER.exists():
        tickets.die("Windows Sandbox не включён: чужую заявку проверять негде, статус не менялся. Компонент включает Vitali (LUA_MODS.md §13 № 3).", 3)
    cfg = tickets.load_config()
    tickets.change_status(cfg, n, "Triaged", "Автопроверка началась.")
    env = dict(os.environ, PATH=f"C:/msys64/mingw64/bin;{os.environ['PATH']}")
    game = game_for(d)
    report = out / "box_out" / "result"
    if own:
        cmd = [sys.executable, str(ROOT / "tools/lua_mod_check.py"), str(archive), "--out", str(report), "--exe", str(EXE), "--game", str(game), "--battle", "--own-test-mod"]
    else:
        cmd = [sys.executable, str(ROOT / "tools/lua_mod_sandbox.py"), str(archive), "--out", str(out), "--game", str(game)]
    code = subprocess.run(cmd, env=env).returncode
    word = {0: "пройдена", 1: "отказ"}.get(code, "не закончена")
    tickets.change_status(cfg, n, "InProgress", f"Автопроверка: {word}. Отчёт: {report / 'report.md'}. Дальше разбор и решение Vitali.")
    print(f"{tickets.fmt(n)}: автопроверка {word}, отчёт {report / 'report.md'}")
    return code


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "check":
        return check(sys.argv[2], "--own-test-mod" in sys.argv[3:])
    return tickets.main()


if __name__ == "__main__":
    sys.exit(main())
