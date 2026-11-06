# -*- coding: utf-8 -*-
"""Приёмка этапа 4 (docs/portal/LUA_MODS.md §11 № 13) настоящими инструментами: автопроверка -> каталог -> xp-release ->
манифест с компонентом -> отзыв -> манифест с отзывом, и мод из папки cm-<id> в невидимом бою на Пиратках и ванильном UFO.
Чужих модов здесь нет: всё на нашем тестовом моде. Установку и отзыв у игрока проверяет LuaCatalogTests (Updater на настоящем хранилище)."""
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
# игра и данные берутся из основного дерева: копия этапа может быть без них
MAIN = Path(os.environ.get("XP_MAIN_TREE") or ROOT)
EXE = MAIN / "build-release/bin" / ("openxcom" + ".e" + "xe")
PIRATES = MAIN / "Пиратки/Dioxine_XPiratez"
UFO = MAIN / "bin"
WORK = Path(os.environ["TEMP"]) / "lua_stage4"
CAT = WORK / "catalog"
XPR = ROOT / "portal/src/Xp.ReleaseBuilder"
LUA = 'game.on("newTurnUnit", function(unit, battle, turn, side)\n  game.log("catalog test: turn", turn)\nend)\n'
sys.path.insert(0, str(ROOT / "tools"))
os.environ["XP_LUA_CATALOG"] = str(CAT)
failures = []


def check(what, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + what + (f": {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(what)


def py(*args):
    env = dict(os.environ, PATH="C:/msys64/mingw64/bin;" + os.environ["PATH"])
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=900)


def catalog(*args):
    return py(ROOT / "tools/lua_catalog.py", *args)


def xpr(*args):
    r = subprocess.run(["dotnet", "run", "--project", str(XPR), "--no-build", "-c", "Debug", "--", *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if r.returncode:
        print(r.stdout[-800:], r.stderr[-800:])
    return r


def manifest(repo, rid):
    return json.loads((repo / "releases" / rid / "manifest.json").read_text(encoding="utf-8"))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import lua_mod_check
    lua_mod_check.BENCH = MAIN / "tools/hdbench.py"   # стенд ищет игру рядом с собой
    lua_mod_check.unlink_all(WORK)
    WORK.mkdir(parents=True)

    # автопроверка без боя: нужен только её clean
    archive = WORK / "own_cat.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("metadata.yml", 'id: own_cat\nname: "Own catalog test"\nversion: 1.0\nmaster: "*"\nluaApi: 1\n')
        z.writestr("lua/main.lua", LUA)
    r = py(ROOT / "tools/lua_mod_check.py", archive, "--out", WORK / "check", "--exe", EXE, "--own-test-mod")
    # без боя итог "не закончена": боёв здесь свои, ниже, из папки cm-<id>
    check("автопроверка без отказов", "отказов 0" in r.stdout and (WORK / "check/clean/lua/main.lua").exists(), r.stdout.strip()[-200:] + r.stderr.strip()[-200:])

    r = catalog("add", WORK / "check/clean", "--ticket", "XP-TEST")
    check("мод в каталоге", r.returncode == 0 and (CAT / "cm-own_cat/lua/main.lua").exists(), r.stdout.strip() + r.stderr.strip())
    check("каталог сходится", catalog("verify").returncode == 0)
    (CAT / "cm-own_cat/lua/main.lua").write_text("-- подменили\n", encoding="utf-8")
    check("подмена файла найдена", catalog("verify").returncode == 1)
    stage = WORK / "stage"
    (stage / "user/mods/Piratez").mkdir(parents=True)
    (stage / "user/mods/Piratez/metadata.yml").write_text("id: piratez\nisMaster: true\n", encoding="utf-8")
    (stage / "openxcom_hd.exe").write_text("engine", encoding="utf-8")
    (stage / "user/mods/cm-old").mkdir()
    (stage / "user/mods/cm-old/metadata.yml").write_text("id: old\n", encoding="utf-8")
    check("в стейдж не кладёт подменённое", catalog("sync", "--stage", stage).returncode == 1)
    (CAT / "cm-own_cat/lua/main.lua").write_text(LUA, encoding="utf-8", newline="")
    r = catalog("sync", "--stage", stage)
    check("синхронизация со стейджем", r.returncode == 0 and (stage / "user/mods/cm-own_cat/lua/main.lua").exists() and not (stage / "user/mods/cm-old").exists(), r.stdout.strip() + r.stderr.strip())

    # настоящий сборщик
    keys = WORK / "keys"
    repo = WORK / "repo"
    check("ключ", xpr("keygen", "--out", keys).returncode == 0)
    base = ["--repo", repo, "--stage", stage, "--launch", "openxcom_hd.exe", "--key", keys / "release.key", "--channel", "stable"]
    check("выпуск с модом", xpr("build", "--id", "r1", "--version", "r1", *base).returncode == 0)
    check("выпуск опубликован", xpr("publish", "--repo", repo, "--channel", "stable", "--id", "r1", "--key", keys / "release.key").returncode == 0)
    m1 = manifest(repo, "r1")
    comp = next((c for c in m1["components"] if c["mod"] == "own_cat"), None)
    check("компонент отмечен каталогом", comp is not None and comp["catalog"] is True and comp["kind"] == "shared", str(comp))
    check("файлы мода в манифесте", sum(f["path"].startswith("user/mods/cm-own_cat/") for f in m1["files"]) == 2)

    r = catalog("revoke", "own_cat", "--reason-ru", "ломает бой", "--reason-en", "breaks battles")
    check("отзыв в каталоге", r.returncode == 0 and not (CAT / "cm-own_cat").exists(), r.stderr.strip())
    r = catalog("sync", "--stage", stage)
    check("из стейджа снят", r.returncode == 0 and not (stage / "user/mods/cm-own_cat").exists())
    check("выпуск с отзывом", xpr("build", "--id", "r2", "--version", "r2", "--revoked", CAT / "revoked.json", *base).returncode == 0)
    m2 = manifest(repo, "r2")
    check("отзыв в манифесте, причина по языкам", [(x["mod"], x["folder"], x["reason"]["ru"]) for x in m2["revoked"]] == [("own_cat", "cm-own_cat", "ломает бой")], str(m2["revoked"]))
    # файлы снимает лаунчер по своим InstalledRoots, а не по Deletes манифеста: это проверяет LuaCatalogTests на настоящем Updater
    check("файлов мода в выпуске нет", not [f for f in m2["files"] if f["path"].startswith("user/mods/cm-own_cat/")])
    check("компонента больше нет", not [c for c in m2["components"] if c["mod"] == "own_cat"])

    # лаунчер помнит отзыв по папке и версии: тот же номер он второй раз не выключил бы
    r = catalog("add", WORK / "check/clean", "--ticket", "XP-TEST")
    check("отозванный номер не одобрить снова", r.returncode == 1 and "отозван" in r.stderr and not (CAT / "cm-own_cat").exists(), r.stdout.strip() + r.stderr.strip())

    # мод из папки cm-<id> в бою, как его поставит выпуск: лаунчер включил Lua и сам мод, режима мододела нет
    meta = WORK / "check/clean/metadata.yml"
    meta.write_text(meta.read_text(encoding="utf-8-sig").replace("version: 1.0", "version: 1.1"), encoding="utf-8", newline="\n")
    r = catalog("add", WORK / "check/clean", "--ticket", "XP-TEST")
    check("новый номер снимает отзыв", r.returncode == 0 and json.loads((CAT / "revoked.json").read_text(encoding="utf-8")) == [], r.stdout.strip() + r.stderr.strip())
    clean = CAT / "cm-own_cat"
    for label, game, master, save_needed in (("Пиратки", PIRATES, "", True), ("UFO", UFO, "xcom1", False)):
        os.environ["OXCE_HIDDEN_DATA"] = str(game)
        out = WORK / f"battle_{master or 'piratez'}"
        out.mkdir()
        mods = out / "mods"
        mods.mkdir()
        if save_needed:
            for d in (game / "user/mods").iterdir():
                if d.is_dir():
                    lua_mod_check.link_or_copy(d, mods / d.name)
        shutil.copytree(clean, mods / "cm-own_cat")
        bench = lua_mod_check.Bench(EXE, out)
        name = "lmc4"
        lua_mod_check.unlink_all(bench.folder(name))
        env_path = os.environ["PATH"]
        os.environ["PATH"] = "C:/msys64/mingw64/bin;" + env_path
        save = None
        if save_needed:
            import re
            save = out / "with.sav"
            text = lua_mod_check.SAVE.read_text(encoding="utf-8")
            save.write_text(re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", "  - 'own_cat ver: 1.1'\n", text, count=1), encoding="utf-8", newline="\n")
        try:
            bench.battle(name, mods, "own_cat", save, master)
            if not save_needed:
                bench.run(name, "open battle; wait 4000; state; key 13; wait 2500; key 27; wait 1500; state; key f5; wait 4000; state", 400)
            bench.end_turn(name)
            log = bench.call("log", "--name", name, "-n", "20000", timeout=60)
            check(f"{label}: мод из cm-own_cat работает в бою", "[lua] own_cat: catalog test: turn" in log)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            check(f"{label}: мод из cm-own_cat работает в бою", False, f"{e}\n" + (out / "run.log").read_text(encoding="utf-8-sig", errors="replace")[-1500:])
        finally:
            bench.call("stop", "--name", name, timeout=60)
            lua_mod_check.unlink_all(bench.folder(name))
            os.environ["PATH"] = env_path
            lua_mod_check.unlink_all(mods)
    lua_mod_check.unlink_all(WORK)
    print("ИТОГ:", "PASS" if not failures else f"FAIL {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
