# Дефекты самопроверки 06.11 в настоящей игре, всё невидимо (docs/portal/LUA_MODS_AUDIT_2026-11-06.md).
# Запуск: py -3.13 tools/lua_stage5/defects.py [campaign|part|journal]; без аргумента все три
import os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import lua_mod_check

HERE = Path(os.environ["TEMP"]) / "oxce_lua_stage5"
EXE = os.environ.get("OXCE_LUA_EXE", str(ROOT / "build-release/bin") + "/" + "openxcom" + ".e" + "xe")
GAME = ROOT / "Пиратки/Dioxine_XPiratez"
SAVE = ROOT / "tools/lua_stage1/lua_battle.sav"
HIT = "unit, damaging_item, weapon_item, attacker, battle, skill, orig_power, damaging_type, battle_action, out"
DAMAGE = "unit, damaging_item, weapon_item, attacker, battle, skill, currPower, orig_power, part, side, damaging_type, battle_action, out"
failed = []


def check(what, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + what + (f"  [{detail}]" if detail else ""), flush=True)
    if not ok:
        failed.append(what)


def stand(case, code):
    """Папка модов: моды установки ссылками и один мод со своим main.lua."""
    out = HERE / case
    lua_mod_check.unlink_all(out)
    mods = out / "mods"
    mods.mkdir(parents=True)
    for d in (GAME / "user/mods").iterdir():
        if d.is_dir():
            lua_mod_check.link_or_copy(d, mods / d.name)
    own = mods / "s5"
    (own / "lua").mkdir(parents=True)
    (own / "metadata.yml").write_text('id: s5\nname: "s5"\nversion: 0.1\nmaster: "piratez"\nluaApi: 1\n', encoding="utf-8", newline="\n")
    (own / "lua/main.lua").write_text(code, encoding="utf-8", newline="\n")
    return lua_mod_check.Bench(EXE, out), mods, out


def battle_save(out):
    save = out / "with.sav"
    text = SAVE.read_text(encoding="utf-8")
    save.write_text(re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", "  - 's5 ver: 0.1'\n", text, count=1), encoding="utf-8", newline="\n")
    return save


def geoscape_save(out):
    """Копия настоящей кампании: корабль с отрядом уже над точкой задания. Посадка идёт через ConfirmLandingState, setSavedGame при этом нет."""
    text = (GAME / "user/piratez/NoCodexCatZ.sav").read_text(encoding="utf-8")
    # севшее НЛО: у точек задания Пираток свои условия на снаряжение, посадку они могут и отклонить
    lon, lat, sid = re.search(r"\nufos:\n  - lon: (\S+)\n    lat: (\S+)\n    id: (\d+)", text).groups()
    head = re.search(r"      - lon: \S+\n        lat: \S+\n        id: 2\n        name: [^\n]*\n(?=(?:.*\n){0,12}?        type: STR_DRAKKAR\n)", text)
    end = text.index("        status: STR_READY\n", head.end())
    block = (f"      - lon: {lon}\n        lat: {lat}\n        id: 2\n        dest:\n          lon: {lon}\n          lat: {lat}\n"
             f"          type: STR_UFO\n          id: {sid}\n" + text[head.start():head.end()].split("\n", 3)[3])
    text = text[:head.start()] + block + text[head.end():end] + "        status: STR_OUT\n" + text[end + len("        status: STR_READY\n"):]
    save = out / "geo.sav"
    save.write_text(text, encoding="utf-8", newline="\n")
    return save


def run_stand(bench, name, mods, save):
    lua_mod_check.unlink_all(bench.folder(name))
    a = ["start", "--name", name, "--exe", EXE, "--save", str(save), "--mods-dir", str(mods), "--mods", "s5=true", "--set", "oxceLuaMods=true", "--timeout", "400"]
    print(name, bench.call(*a).strip().splitlines()[-1][:120], flush=True)


def lines(bench, name, word):
    return [l.strip() for l in bench.call("log", "--name", name, "-n", "40000", timeout=60).splitlines() if word in l]


def wait_landing(bench, name):
    t0 = time.time()
    top = ""
    while time.time() - t0 < 120:
        top = bench.state(name)[0]
        if top == "ConfirmLandingState":
            break
        if top in ("CraftErrorState", "InfoboxOKState"):
            bench.run(name, "key 13", 30)
        time.sleep(2)
    check("корабль дошёл до посадки на геоскейпе", top == "ConfirmLandingState", top)


def land(bench, name):
    t0 = time.time()
    top = ""
    while time.time() - t0 < 180:
        top = bench.state(name)[0]
        if top in ("BriefingState", "BattlescapeState", "InventoryState"):
            break
        # окна о кораблях и производстве сейва всплывают поверх посадки и забирают клавишу
        if top == "ConfirmLandingState":
            print("посадка:", bench.run(name, "key 13; wait 1500; state", 120).strip()[-120:], flush=True)
        elif top != "GeoscapeState":
            print(top, bench.run(name, "key 27; wait 500; state", 120).strip()[-100:], flush=True)
        time.sleep(2)
    check("бой кампании начался", top in ("BriefingState", "BattlescapeState", "InventoryState"), top)


def campaign():
    """R-778: бой из геоскейпа. Строка main.lua появляется при каждой перезагрузке, счётчик начинается заново."""
    code = ('local units = 0\ngame.log("S5 main")\n'
            'game.on("createUnit", function(unit, battle, turn)\n  units = units + 1\n  if units == 1 then game.log("S5 first unit") end\nend)\n')
    bench, mods, out = stand("campaign", code)
    name = "s5camp"
    run_stand(bench, name, mods, geoscape_save(out))
    wait_landing(bench, name)
    before = lines(bench, name, "S5 main")
    check("до боя юнитов нет", not lines(bench, name, "S5 first unit"), str(len(before)))
    land(bench, name)
    after = lines(bench, name, "S5 main")
    check("вход в бой кампании перезагрузил main.lua", len(after) == len(before) + 1, f"{len(before)} -> {len(after)}")
    check("после перезагрузки обработчики работают", len(lines(bench, name, "S5 first unit")) == 1)
    errors = bench.folder(name) / "lua_errors.log"
    check("без ошибок мода", not errors.exists() or errors.stat().st_size == 0)
    bench.call("stop", "--name", name, timeout=60)


def part():
    """R-777: out.part мимо таблицы становится головой, игра жива, рана на голове."""
    code = (f'local n, bad = 0, {{ -1, 6, -2000000000, 2000000000 }}\ngame.on("hitUnit", function({HIT})\n'
            '  n = n + 1\n  out.part = bad[n % 4 + 1]\n  out.power = 40\n  game.log("S5 set", out.part)\nend)\n'
            # урон от среды: сторону и часть движок задаёт сам, после обработчика
            f'game.on("damageUnit", function({DAMAGE})\n  if attacker then game.log("S5 part", part) end\nend)\n')
    bench, mods, out = stand("part", code)
    name = "s5part"
    run_stand(bench, name, mods, battle_save(out))
    # выстрелы врага: пока отряд стоит, он подходит не сразу, а урон среды части тела не проверяет
    parts = []
    for _ in range(25):
        bench.end_turn(name)
        parts = lines(bench, name, "S5 part")
        if len(parts) >= 4:
            break
    set_lines = lines(bench, name, "S5 set")
    check("были попадания с плохой частью тела", len(set_lines) >= 4 and len(parts) >= 4, f"{len(set_lines)}, от атакующего {len(parts)}")
    check("каждая стала головой", parts and all(l.endswith("S5 part\t0") or l.endswith("S5 part 0") for l in parts), parts[0] if parts else "")
    check("игра жива после плохих частей", bench.state(name)[0] == "BattlescapeState")
    bench.call("stop", "--name", name, timeout=60)


def journal():
    """Журнал не перестаёт писать на 256 КБ: новые ошибки остаются, старые уходят, шапка говорит об этом."""
    code = ('local n = 0\nlocal function fail()\n  n = n + 1\n  if n % 2 == 0 then error("S5" .. n .. string.rep("x", 1800)) end\nend\n'
            'game.on("newTurnItem", fail)\ngame.on("newTurnUnit", fail)\n')
    bench, mods, out = stand("journal", code)
    name = "s5log"
    run_stand(bench, name, mods, battle_save(out))
    path = bench.folder(name) / "lua_errors.log"
    for _ in range(30):
        bench.end_turn(name)
        if path.exists() and "the log was full" in path.read_text(encoding="utf-8", errors="replace"):
            break
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    numbers = [int(x) for x in re.findall(r"S5(\d+)x", text)]
    check("журнал дошёл до вращения", "the log was full" in text, f"{len(text)} байт, ошибок {len(numbers)}")
    check("размер в границе", len(text.encode("utf-8")) <= 256 * 1024 + 100)
    check("старые ушли, новые остались", bool(numbers) and min(numbers) > 2 and numbers == sorted(numbers), f"{numbers[:1]}..{numbers[-1:]}")
    bench.call("stop", "--name", name, timeout=60)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ["OXCE_HIDDEN_DATA"] = str(GAME)
    os.environ["PATH"] = "C:/msys64/mingw64/bin;" + os.environ["PATH"]
    cases = {"campaign": campaign, "part": part, "journal": journal}
    for key in sys.argv[1:] or cases:
        cases[key]()
    lua_mod_check.unlink_all(HERE)
    print("ИТОГ:", "всё прошло" if not failed else f"провалов {len(failed)}: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
