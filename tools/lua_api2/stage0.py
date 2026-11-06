# API 2, этап 0 в настоящей игре, всё невидимо: разрешения, очередь, потолки, сохранение (docs/portal/LUA_MODS_V2.md).
# Запуск: py -3.13 tools/lua_api2/stage0.py
import os, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import lua_mod_check

HERE = Path(os.environ["TEMP"]) / "oxce_lua_api2"
EXE = os.environ.get("OXCE_LUA_EXE", str(ROOT / "build-release/bin") + "/" + "openxcom" + ".e" + "xe")
GAME = ROOT / "Пиратки/Dioxine_XPiratez"
SAVE = ROOT / "tools/lua_stage1/lua_battle.sav"
TYPE = "STR_ELECTRO_FLARE"
TURN_LIMIT = 150
failed = []
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

V1 = 'game.on("newTurnUnit", function(unit, battle, turn, side)\n  game.log("S0 v1", tostring(battle.spawnItem))\nend)\n'

NOCAP = '''local said = false
game.on("newTurnUnit", function(unit, battle, turn, side)
  if said then return end
  said = true
  local x, y, z = unit:getPosition()
  local ok, text = pcall(function() battle:spawnItem("%s", x, y, z) end)
  game.log("S0 nocap", tostring(ok), text)
end)
''' % TYPE

CAP = '''local TYPE = "%s"
local step, lastTurn = 0, nil
local inTurn, calls, asked, turnOk = 0, 0, 0, 0
local capDone, reads = false, false

local function count(battle)
  local n = 0
  for _, item in ipairs(battle:getItems()) do
    if item:getRuleItem():getType() == TYPE then n = n + 1 end
  end
  return n
end

local function spawn(battle, unit, tag, type)
  local x, y, z = unit:getPosition()
  asked = asked + 1
  local index = asked
  battle:spawnItem(type or TYPE, x, y, z, function(item)
    game.log("S0 done", tag, index, item:getRuleItem():getType(), tostring(item:getOwner() == nil))
  end)
end

local function wholeTurn(battle, unit)
  local x, y, z = unit:getPosition()
  while not capDone do
    local ok, text = pcall(function() battle:spawnItem(TYPE, x, y, z) end)
    if ok then
      turnOk = turnOk + 1
    else
      if string.find(text, "in one turn", 1, true) then
        capDone = true
        game.log("S0 turn ceiling", turnOk, text)
      end
      return
    end
  end
end

game.on("createItem", function(item, unit, battle, turn)
  if item:getRuleItem():getType() == TYPE and step == 1 then game.log("S0 created") end
end)

game.on("aiCalculateTargetWeight", function(unit, target, battle, out)
  if step >= 1 and not capDone then
    local x, y, z = unit:getPosition()
    local ok, text = pcall(function() battle:spawnItem(TYPE, x, y, z) end)
    if not ok and not reads then
      reads = true
      game.log("S0 reads", tostring(ok), text)
    end
  end
end)

game.on("newTurnUnit", function(unit, battle, turn, side)
  if side ~= game.FACTION_PLAYER then return end
  if turn ~= lastTurn then
    lastTurn, inTurn = turn, 0
    step = step + 1
    asked = 0
    game.log("S0 step", step, "turn", turn, "before", count(battle))
  end
  inTurn = inTurn + 1
  if step == 1 then
    spawn(battle, unit, "walk")
  elseif step == 2 and inTurn == 1 then
    local x, y, z = unit:getPosition()
    local good = 0
    local said
    for i = 1, 33 do
      local ok, text = pcall(function() battle:spawnItem(TYPE, x, y, z) end)
      if ok then good = good + 1 else said = text end
    end
    game.log("S0 call ceiling", good, said)
  elseif step == 2 and inTurn == 2 then
    for i = 1, 3 do spawn(battle, unit, "glow", "S0_FLARE") end
  elseif step == 3 and inTurn == 3 then
    for i = 1, 6 do spawn(battle, unit, "glow", "S0_FLARE") end
  elseif step == 3 and inTurn == 1 then
    spawn(battle, unit, "failed")
    spawn(battle, unit, "failed")
    spawn(battle, unit, "failed")
    error("S0 on purpose")
  elseif step == 3 and inTurn == 2 then
    spawn(battle, unit, "after")
  elseif step == 4 then
    wholeTurn(battle, unit)
  elseif step == 5 and inTurn <= 5 then
    spawn(battle, unit, "save")
  elseif step == 6 and inTurn == 1 then
    game.log("S0 after load", count(battle))
  end
end)

game.on("newTurnItem", function(item, battle, turn, side)
  if side ~= game.FACTION_PLAYER then return end
  local owner = item:getOwner()
  if step == 1 and asked < 60 and owner then
    spawn(battle, owner, "walk")
  elseif step == 4 and owner then
    wholeTurn(battle, owner)
  end
end)
''' % TYPE


def check(what, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + what + (f"  [{detail}]" if detail else ""), flush=True)
    if not ok:
        failed.append(what)


def mod(mods, name, api, code, caps=""):
    own = mods / name
    (own / "lua").mkdir(parents=True)
    meta = f'id: {name}\nname: "{name}"\nversion: 0.1\nmaster: "piratez"\nluaApi: {api}\n{caps}'
    (own / "metadata.yml").write_text(meta, encoding="utf-8", newline="\n")
    (own / "lua/main.lua").write_text(code, encoding="utf-8", newline="\n")


def stand(case):
    out = HERE / case
    lua_mod_check.unlink_all(out)
    mods = out / "mods"
    mods.mkdir(parents=True)
    for d in (GAME / "user/mods").iterdir():
        if d.is_dir():
            lua_mod_check.link_or_copy(d, mods / d.name)
    mod(mods, "s0v1", 1, V1)
    mod(mods, "s0nocap", 2, NOCAP)
    mod(mods, "s0cap", 2, CAP, "luaCaps: [spawn]\n")
    # светится сразу, как только создан: ELECTRO_FLARE ждёт броска
    (mods / "s0cap/Ruleset").mkdir()
    (mods / "s0cap/Ruleset/s0.rul").write_text("items:\n  - type: S0_FLARE\n    battleType: 10\n    size: 0.1\n    weight: 2\n    power: 15\n    bigSprite: 55\n    floorSprite: 72\n", encoding="utf-8", newline="\n")
    mod(mods, "s0badword", 2, V1, "luaCaps: [spawn, flight]\n")
    mod(mods, "s0capsv1", 1, V1, "luaCaps: [spawn]\n")
    return lua_mod_check.Bench(EXE, out), mods, out


def battle_save(out):
    save = out / "with.sav"
    list_ = "".join(f"  - '{m} ver: 0.1'\n" for m in ("s0v1", "s0nocap", "s0cap", "s0badword", "s0capsv1"))
    text = SAVE.read_text(encoding="utf-8")
    save.write_text(re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", list_, text, count=1), encoding="utf-8", newline="\n")
    return save


def start(bench, name, mods, save, api2):
    os.environ.pop("OXCE_LUA_API2", None)
    if api2:
        os.environ["OXCE_LUA_API2"] = "1"
    lua_mod_check.unlink_all(bench.folder(name))
    on = ";".join(f"{m}=true" for m in ("s0v1", "s0nocap", "s0cap", "s0badword", "s0capsv1"))
    a = ["start", "--name", name, "--exe", EXE, "--save", str(save), "--mods-dir", str(mods), "--mods", on,
         "--set", "oxceLuaMods=true;autosave=true;autosaveFrequency=1;autosaveSlots=1", "--timeout", "300"]
    print(name, (bench.call(*a, timeout=330).strip().splitlines() or ["?"])[-1][:120], flush=True)


def lines(bench, name, word):
    return [l.strip() for l in bench.call("log", "--name", name, "-n", "40000", timeout=60).splitlines() if word in l]


def tail(line):
    return line.split("S0 ", 1)[1]


def errors(bench, name):
    path = bench.folder(name) / "lua_errors.log"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def closed():
    """Без переменной окружения API 2 закрыт: заслон до открытия с этапа 1."""
    bench, mods, out = stand("closed")
    name = "s0closed"
    try:
        start(bench, name, mods, battle_save(out), False)
        text = errors(bench, name)
        check("без OXCE_LUA_API2 мод luaApi: 2 не грузится", "s0cap" in text and "needs Lua API 2, this game has 1" in text)
        check("без OXCE_LUA_API2 мод luaApi: 1 загружен", lines(bench, name, "s0v1: loaded"))
    finally:
        bench.call("stop", "--name", name, timeout=60)


def opened():
    bench, mods, out = stand("open")
    name = "s0open"
    try:
        start(bench, name, mods, battle_save(out), True)
        text = errors(bench, name)
        check("неизвестное слово в luaCaps отключает Lua мода", "unknown word 'flight'" in text and not lines(bench, name, "s0badword: loaded"))
        check("luaCaps при luaApi: 1 отключает Lua мода", "luaCaps needs luaApi 2" in text and not lines(bench, name, "s0capsv1: loaded"))

        # шаг 1: очередь полна из обхода юнитов и предметов, до такта ничего не создано
        t0 = time.time()
        bench.end_turn(name, TURN_LIMIT)
        print(f"ход 1: {time.time() - t0:.0f} с", flush=True)
        step = [tail(l) for l in lines(bench, name, "S0 step")]
        done = [tail(l) for l in lines(bench, name, "S0 done walk")]
        created = lines(bench, name, "S0 created")
        check("luaApi: 1 не видит метода", any("nil" in l for l in lines(bench, name, "S0 v1")))
        nocap = lines(bench, name, "S0 nocap")
        check("без luaCaps ошибка называет spawn", nocap and "false" in nocap[0] and "'spawn'" in nocap[0], nocap[0] if nocap else "")
        check("запросы из обхода выполнены все, в обход ни одного", len(done) > 0 and len(done) == len(created), f"{len(done)} / {len(created)}")
        first = int(step[0].split()[-1])
        check("done получает предмет на карте, по порядку запросов", [l.split() for l in done] == [["done", "walk", str(i + 1), TYPE, "true"] for i in range(len(done))], done[0] if done else "")

        # шаг 2: потолок на вызов
        bench.end_turn(name, TURN_LIMIT)
        now = int([tail(l) for l in lines(bench, name, "S0 step")][-1].split()[-1])
        check("предметы остались на карте", now == first + len(done), f"{first} + {len(done)} -> {now}")
        call = lines(bench, name, "S0 call ceiling")
        check("потолок на вызов: 32 из 33, число в тексте", call and "32" in call[0].split("ceiling")[1][:6] and "more than 32 items in one call" in call[0], call[0][:150] if call else "")

        # шаг 3: ошибка снимает операции вызова
        bench.end_turn(name, TURN_LIMIT)
        check("ошибка снимает все операции вызова", not lines(bench, name, "S0 done failed"))
        check("следующий вызов работает", lines(bench, name, "S0 done after"))
        check("ошибка в журнале мода", "S0 on purpose" in errors(bench, name))
        check("светящиеся предметы: по одному и пачкой", len(lines(bench, name, "S0 done glow")) == 9, str(len(lines(bench, name, "S0 done glow"))))

        # шаг 4: потолок на ход
        t0 = time.time()
        bench.end_turn(name, TURN_LIMIT)
        whole = lines(bench, name, "S0 turn ceiling")
        check("потолок на ход: 256, число в тексте", whole and "more than 256 items in one turn" in whole[0], whole[0][:150] if whole else "")
        print(f"ход 4 с потолком: {time.time() - t0:.0f} с", flush=True)

        # шаг 5: операции из нового хода обязаны попасть в автосохранение этого хода
        bench.end_turn(name, TURN_LIMIT)
        before = int([tail(l) for l in lines(bench, name, "S0 step")][-1].split()[-1])
        saves = sorted(bench.folder(name).rglob("*.asav"), key=lambda p: p.stat().st_mtime)
        check("автосохранение есть", saves, str(saves[-1].name) if saves else "")
        asked = len(lines(bench, name, "S0 done save"))
        inside = saves[-1].read_text(encoding="utf-8", errors="replace").count(f"type: {TYPE}") if saves else -1
        check("в сейве предметы этого хода", asked == 5 and inside == before + 5, f"до {before}, запрошено {asked}, в сейве {inside}")

        # загрузка этого сейва даёт тот же бой
        shown = bench.run(name, f"load {saves[-1].name}; wait 3000; state", 120)
        print(shown.strip()[-100:], flush=True)
        try:
            bench.end_turn(name, 40)
        except RuntimeError as e:
            print("end_turn:", str(e)[:100], bench.run(name, "state", 30).strip()[-160:], flush=True)
            print("\n".join(bench.call("log", "--name", name, "-n", "25", timeout=60).splitlines()[-25:])[-2400:], flush=True)
        after = lines(bench, name, "S0 after load") or lines(bench, name, "S0 step")
        check("после загрузки столько же", after and str(before + 5) in after[-1], after[-1][:120] if after else "")

        check("игра жива", bench.state(name)[0] == "BattlescapeState")
        reads = lines(bench, name, "S0 reads")
        print("обработчик только для чтения:", reads[0][:160] if reads else "не вызван за эти ходы", flush=True)
    finally:
        bench.call("stop", "--name", name, timeout=60)


if __name__ == "__main__":
    t0 = time.time()
    closed()
    opened()
    print(f"итог: {'FAIL ' + str(len(failed)) if failed else 'PASS'}, {time.time() - t0:.0f} с", flush=True)
    sys.exit(1 if failed else 0)
