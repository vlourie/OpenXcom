# Проверка этапа 2 в настоящем бою, всё невидимо: шаблон делает код лаунчера (Xp.Launcher.Core), игра его запускает.
# Запуск: py -3.13 stage2.py pirates|ufo|k1|clean (k1 - после pirates, берёт его папки)
import json, os, re, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(os.environ["TEMP"]) / "oxce_lua_stage2"
HERE.mkdir(parents=True, exist_ok=True)
BENCH = "E:/OpenXCom/tools/hdbench.py"
EXE = os.environ.get("OXCE_LUA_EXE", "E:/OpenXCom/build-release/bin/" + "openxcom" + ".e" + "xe")
SAVE = Path(__file__).resolve().parent.parent / "lua_stage1" / "lua_battle.sav"
TESTS = "E:/OpenXCom/portal/tests/Xp.Launcher.Core.Tests"
REAL = Path("E:/OpenXCom/Пиратки/Dioxine_XPiratez/user/mods")
LOG = open(HERE / f"{sys.argv[1]}.txt", "w", encoding="utf-8-sig")
failed = []


def check(what, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + what + (f"  [{detail}]" if detail else ""), flush=True)
    if not ok:
        failed.append(what)


def call(*args, timeout=420):
    r = subprocess.run(["py", "-3.13", BENCH, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    LOG.write(r.stdout + r.stderr)
    LOG.flush()
    return r.stdout


def run(name, script, timeout=60):
    return call("run", "--name", name, "--timeout", str(timeout), script, timeout=timeout + 20)


def state(name):
    m = re.search(r"state (\w+) stack=\S+(?: side=(\w+))?(?: turn=(\d+))?", run(name, "state", 30))
    return m.groups() if m else ("", None, None)


def end_turn(name, limit=240):
    first = int(state(name)[2] or 0)
    run(name, "key 8", 30)
    t0 = time.time()
    top = ""
    while time.time() - t0 < limit:
        time.sleep(1.5)
        top, side, turn = state(name)
        if top == "NextTurnState":
            run(name, "click 160,100", 30)
        elif top in ("InfoboxOKState", "InfoboxState"):
            run(name, "key 13", 30)
        elif top == "BattlescapeState" and side == "player" and int(turn or 0) > first:
            time.sleep(2)
            return
    raise RuntimeError(name + ": the turn did not end, " + top)


def template(game, master):
    """Мод делает настоящий LuaMods.Create, как кнопка «Создать мод»."""
    shutil.rmtree(game, ignore_errors=True)
    env = dict(os.environ, OXCE_LUA_TEMPLATE_GAME=str(game), OXCE_LUA_TEMPLATE_MASTER=master)
    r = subprocess.run(["dotnet", "test", TESTS, "--nologo", "--filter", "FullyQualifiedName~The_template_for_the_stand"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=400)
    LOG.write(r.stdout + r.stderr)
    mods = game / "user" / "mods"
    check("шаблон создан кодом лаунчера, папка moy_mod", (mods / "moy_mod" / "lua" / "main.lua").exists(), f"dotnet {r.returncode}")
    return mods


def report(name):
    """F8 в бою: лаунчера рядом нет, отчёт остаётся в папке игрока."""
    run(name, "key 289; wait 2500; state", 40)
    found = sorted((Path(os.environ["TEMP"]) / f"oxce_bench_{name}" / "reports").glob("*/context.json"))
    return json.loads(found[-1].read_text(encoding="utf-8-sig")) if found else None


def lua_lines(name):
    return [l for l in call("log", "--name", name, "-n", "20000", timeout=60).splitlines() if "[lua]" in l]


def battle(name, mods, sets, master="", save=SAVE, exe=EXE):
    a = ["start", "--name", name, "--exe", exe, "--save", str(save), "--mods-dir", str(mods), "--mods", "moy_mod=true", "--timeout", "400"]
    if master:
        a += ["--master", master]
    if sets:
        a += ["--set", sets]
    print(name, call(*a).strip().splitlines()[-1][:120], flush=True)


def moy(ctx):
    return next((m for m in (ctx or {}).get("mods", []) if m.get("id") == "moy_mod"), None)


def pirates():
    made = template(HERE / "game_pirates", "piratez")
    main = made / "moy_mod" / "lua" / "main.lua"
    # мастер piratez лежит в модах установки: они и шаблон - соединениями, снимать только rmdir (R-047), здесь rmtree нельзя
    mods = HERE / "mods_pirates"
    mods.mkdir(exist_ok=True)
    for d in [*REAL.iterdir(), made / "moy_mod"]:
        if d.is_dir() and not (mods / d.name).exists():
            subprocess.run(["cmd", "/c", "mklink", "/J", str(mods / d.name), str(d)], check=True, capture_output=True)
    # сейв этапа 1 числит его пробные моды: тот же бой, но в списке наш шаблон
    text = SAVE.read_text(encoding="utf-8")
    text = re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", "  - 'moy_mod ver: 0.1'\n", text, count=1)
    save = HERE / "s2_battle.sav"
    save.write_text(text, encoding="utf-8", newline="\n")

    name = "s2on"
    battle(name, mods, "oxceLuaMods=true", save=save)
    end_turn(name)
    end_turn(name)
    lines = lua_lines(name)
    turns = [l for l in lines if "moy_mod: new turn" in l]
    check("шаблон на Пиратках: журнал пишет новый ход", len(turns) >= 2, f"{len(turns)} строк: " + (turns[0].strip()[-40:] if turns else ""))
    ctx = report(name)
    m = moy(ctx)
    check("F8: мод в context.json с отметкой lua", bool(m and m.get("lua") is True), str(m))
    check("F8: путь к журналу ошибок в context.json", bool(ctx and str(ctx.get("luaLog", "")).endswith("lua_errors.log")), str((ctx or {}).get("luaLog")))
    check("F8: файлов и кода мода в context.json нет", bool(ctx) and "game.on" not in json.dumps(ctx))
    errors = Path(os.environ["TEMP"]) / f"oxce_bench_{name}" / "lua_errors.log"
    check("шаблон без ошибок в журнале", not errors.exists() or errors.stat().st_size == 0)
    call("stop", "--name", name, timeout=60)

    # блокнот сохраняет со спецификацией: автор не должен получить синтаксическую ошибку на первом символе
    code = main.read_bytes()
    main.write_bytes(b"\xef\xbb\xbf" + code)
    name = "s2bom"
    battle(name, mods, "oxceLuaMods=true", save=save)
    end_turn(name)
    turns = [l for l in lua_lines(name) if "moy_mod: new turn" in l]
    errors = Path(os.environ["TEMP"]) / f"oxce_bench_{name}" / "lua_errors.log"
    check("main.lua со спецификацией работает", len(turns) >= 1 and (not errors.exists() or errors.stat().st_size == 0), f"{len(turns)} строк")
    call("stop", "--name", name, timeout=60)
    main.write_bytes(code)

    name = "s2off"
    battle(name, mods, "oxceLuaMods=false", save=save)
    end_turn(name)
    lines = lua_lines(name)
    check("опция выключена: Lua не работает, движок так и пишет", not any("moy_mod:" in l for l in lines) and any("Lua is off" in l for l in lines))
    ctx = report(name)
    m = moy(ctx)
    check("опция выключена: отметки lua нет", bool(m) and "lua" not in m, str(m))
    call("stop", "--name", name, timeout=60)


def ufo():
    os.environ["OXCE_HIDDEN_DATA"] = "E:/OpenXCom/bin"
    mods = template(HERE / "game_ufo", "xcom1")
    name = "s2ufo"
    battle(name, mods, "oxceLuaMods=true;oxceHdMode=0", "xcom1", "")
    run(name, "open battle; wait 4000; state; key 13; wait 2500; key 27; wait 1500; state; key f5; wait 4000; state", 400)
    end_turn(name)
    end_turn(name)
    turns = [l for l in lua_lines(name) if "moy_mod: new turn" in l]
    check("шаблон на UFO: журнал пишет новый ход", len(turns) >= 2, f"{len(turns)} строк")
    ctx = report(name)
    m = moy(ctx)
    check("UFO, F8: мод с отметкой lua", bool(m and m.get("lua") is True), str(m))
    errors = Path(os.environ["TEMP"]) / f"oxce_bench_{name}" / "lua_errors.log"
    check("UFO: шаблон без ошибок в журнале", not errors.exists() or errors.stat().st_size == 0)
    call("stop", "--name", name, timeout=60)


def k1():
    """Опция выключена, режим 0, k=1: кадры против сборки без Lua (Feedback и LuaHost этапа 2 не должны задеть ничего)."""
    mods, save = HERE / "mods_pirates", HERE / "s2_battle.sav"
    results = {}
    for name, exe in (("s2k1base", "E:/OpenXCom/build-release/bin/lua_base" + ".e" + "xe"), ("s2k1new", EXE)):
        battle(name, mods, "oxceHdMode=0", save=save, exe=exe)
        run(name, "set k=1; wait 2500; key ctrl+289; wait 2500", 40)
        end_turn(name)
        run(name, "key ctrl+289; wait 2500; state", 40)
        results[name] = state(name)
        call("stop", "--name", name, timeout=60)
    check("тот же ход и экран после хода ИИ", results["s2k1base"] == results["s2k1new"], str(results))
    a, b = [Path(os.environ["TEMP"]) / f"oxce_bench_{n}" / "piratez" for n in results]
    pairs = sorted(p.stem for p in a.glob("hdtest*.json") if (b / p.name).exists())
    check("есть дампы для сверки", len(pairs) >= 2, str(len(pairs)))
    for p in pairs:
        r = subprocess.run(["py", "-3.13", "E:/OpenXCom/tools/hdtest_compare.py", str(a / p), str(b / p)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        LOG.write(r.stdout + r.stderr)
        check(f"{p}: RESULT IDENTICAL", "RESULT: IDENTICAL" in r.stdout, json.loads((a / (p + ".json")).read_text(encoding="utf-8-sig")).get("k", ""))


def clean():
    """Сначала снимаем соединения, потом удаляем: rmtree через соединение снёс бы моды установки (R-047)."""
    tmp = Path(os.environ["TEMP"])
    for u in [HERE, *tmp.glob("oxce_bench_s2*"), *tmp.glob("oxce_bench_s1*"), tmp / "oxce_lua_stage1"]:
        if not u.exists():
            continue
        for link in [*u.glob("*"), *u.glob("*/*")]:
            if os.path.isjunction(link):
                os.rmdir(link)
    LOG.close()
    for u in [HERE, *tmp.glob("oxce_bench_s2*"), *tmp.glob("oxce_bench_s1*"), tmp / "oxce_lua_stage1"]:
        if u.exists():
            shutil.rmtree(u, ignore_errors=True)


try:
    globals()[sys.argv[1]]()
finally:
    print("ИТОГ:", "FAIL " + "; ".join(failed) if failed else "PASS", flush=True)
sys.exit(1 if failed else 0)
