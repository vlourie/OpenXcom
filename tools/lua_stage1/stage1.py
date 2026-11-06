# Проверки этапа 1 в настоящем бою, всё невидимо. Сначала make_mods0.py и make_mods1.py; сборка и эталон без Lua - OXCE_LUA_EXE и OXCE_LUA_BASE.
# Запуск: py -3.13 stage1.py abuse|same|tags|stale|kill|k1|mode0|identical|speed|ufo|uiheal
import os, re, shutil, subprocess, sys, threading, time
from pathlib import Path

HERE = Path(os.environ["TEMP"]) / "oxce_lua_stage1"
HERE.mkdir(parents=True, exist_ok=True)
BENCH = "E:/OpenXCom/tools/hdbench.py"
EXE = os.environ.get("OXCE_LUA_EXE", "E:/OpenXCom/build-release/bin/openxcom.exe")
BASE = os.environ.get("OXCE_LUA_BASE", "E:/OpenXCom/build-release/bin/lua_base.exe")
SAVE = Path(__file__).resolve().parent / "lua_battle.sav"
MODS = HERE / "luamods"
OUT = HERE / "lua_stage1"
OUT.mkdir(exist_ok=True)

ABUSE = {
    "lua_abuse": """
local n = 0
game.on("newTurnUnit", function(unit)
  n = n + 1
  local k = n % 6
  if k == 1 then while true do end
  elseif k == 2 then local s = 'x' while true do s = s .. s end
  elseif k == 3 then local function f() return 1 + f() end f()
  elseif k == 4 then string.rep('a', 50000):find('.-.-.-.-.-.-.-.-x')
  elseif k == 5 then local s = string.rep('x', 10000000000)
  else local function f() pcall(f) pcall(f) end f() end
end)
""",
    "lua_chain": """
game.on("hitUnit", function(unit, a, b, c, d, e, f, g, h, out)
  game.log("chain power", f, out.power)
end)
game.on("returnFromMissionUnit", function(unit, battle, soldier, out)
  game.log("chain recovery", out.recovery_time, out.health_loss)
end)
""",
    "lua_reload": """
local calls = 0
game.on("newTurnUnit", function(unit) calls = calls + 1; if calls == 1 then game.log("reload version ONE, calls", calls) end end)
""",
}


def mod(name, code, api=1):
    d = MODS / name
    (d / "lua").mkdir(parents=True, exist_ok=True)
    (d / "metadata.yml").write_text(f'name: "{name}"\nversion: 1.0\nauthor: probe\nmaster: piratez\nluaApi: {api}\n', encoding="utf-8", newline="\n")
    (d / "lua" / "main.lua").write_bytes(code if isinstance(code, bytes) else code.encode("utf-8"))


def call(log, *args, timeout=400):
    r = subprocess.run(["py", "-3.13", BENCH, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    log.write(r.stdout + r.stderr)
    log.flush()
    return r.stdout


def start(log, name, exe, save, mods, sets="oxceLuaMods=true"):
    a = ["start", "--name", name, "--exe", exe, "--save", str(save), "--mods-dir", str(MODS), "--mods", mods, "--timeout", "400"]
    if sets:
        a += ["--set", sets]
    return call(log, *a, timeout=420)


def state(log, name):
    out = call(log, "run", "--name", name, "--timeout", "30", "state", timeout=50)
    m = re.search(r"state (\w+) stack=\S+(?: side=(\w+))?(?: turn=(\d+))?(?: seed=(\d+))?", out)
    return m.groups() if m else ("", None, None, None)


def end_turn(log, name, limit=240):
    """Конец хода и ход ИИ: панель хода закрывается, когда появится, ждём ход игрока на экране боя."""
    start_turn = int(state(log, name)[2] or 0)
    call(log, "run", "--name", name, "--timeout", "30", "key 8", timeout=50)
    t0 = time.time()
    while time.time() - t0 < limit:
        time.sleep(1.5)
        top, side, turn, seed = state(log, name)
        if top == "NextTurnState":
            call(log, "run", "--name", name, "--timeout", "30", "click 160,100", timeout=50)
        elif top in ("InfoboxOKState", "InfoboxState"):
            call(log, "run", "--name", name, "--timeout", "30", "key 13", timeout=50)
        elif top == "BattlescapeState" and side == "player" and int(turn or 0) > start_turn:
            time.sleep(2)
            log.write(f"TURN {turn} seed {seed}\n")
            return seed
    raise RuntimeError(name + ": the turn did not end, " + top)


def lualog(log, name):
    text = call(log, "log", "--name", name, "-n", "20000", timeout=60)
    (OUT / f"{name}.lua.txt").write_text("\n".join(l for l in text.splitlines() if "[lua]" in l), encoding="utf-8-sig")


def user(name):
    return Path(os.environ["TEMP"]) / f"oxce_bench_{name}"


def abuse():
    for n, code in ABUSE.items():
        mod(n, code)
    mod("lua_bytecode", b"\x1bLuaT\x00\x19\x93\r\n\x1a\ngame.log('MUST NOT RUN: bytecode')")
    name = "s1abuse"
    log = open(OUT / f"{name}.txt", "w", encoding="utf-8-sig")
    mods = "lua_all=true;lua_chain=true;lua_stale=true;lua_badout=true;lua_err=true;lua_abuse=true;lua_escape=true;lua_bytecode=true;lua_syntax=true;lua_future=true;lua_nokey=true;lua_reload=true"
    start(log, name, EXE, SAVE, mods)
    end_turn(log, name)
    mod("lua_reload", ABUSE["lua_reload"].replace("ONE", "TWO"))
    call(log, "run", "--name", name, "--timeout", "60", "key ctrl+286; wait 700; shot " + str(OUT / "reload.png").replace(chr(92), "/") + "; wait 1500; state", timeout=80)
    print("after ctrl+f5, quick save exists:", (user(name) / "piratez" / "_quick_.asav").exists(), state(log, name))
    end_turn(log, name)
    call(log, "run", "--name", name, "--timeout", "30", "shot " + str(OUT / "notice.png").replace(chr(92), "/"), timeout=50)
    call(log, "run", "--name", name, "--timeout", "120", "key 97; wait 1500; state; key 13; wait 15000; state", timeout=140)
    print("after abort", state(log, name))
    lualog(log, name)
    j = user(name) / "lua_errors.log"
    print("journal", j.exists(), j.stat().st_size if j.exists() else 0)
    if j.exists():
        shutil.copy(j, OUT / "lua_errors.log")
    call(log, "stop", "--name", name, timeout=60)
    mod("lua_reload", ABUSE["lua_reload"])


def same():
    def one(name):
        log = open(OUT / f"{name}.txt", "w", encoding="utf-8-sig")
        start(log, name, EXE, SAVE, "lua_all=true")
        for _ in range(3):
            end_turn(log, name)
        call(log, "run", "--name", name, "--timeout", "60", "key f5; wait 6000; state", timeout=80)
        lualog(log, name)
        call(log, "stop", "--name", name, timeout=60)
    jobs = [threading.Thread(target=one, args=(n,)) for n in ("s1same1", "s1same2")]
    for j in jobs:
        j.start()
    for j in jobs:
        j.join()
    seeds = []
    for n in ("s1same1", "s1same2"):
        t = (OUT / f"{n}.txt").read_text(encoding="utf-8-sig")
        seeds.append(re.findall(r"TURN \d+ seed (\d+)", t))
        shutil.copy(user(n) / "piratez" / "_quick_.asav", OUT / f"{n}.asav")
    print("seeds", seeds[0], "same:", seeds[0] == seeds[1])
    a, b = [[re.sub(r"^.*\[lua\]", "", l) for l in (OUT / f"{n}.lua.txt").read_text(encoding="utf-8-sig").splitlines()] for n in ("s1same1", "s1same2")]
    print("lua lines", len(a), len(b), "same:", a == b)


def tags():
    save = OUT / "s1same1.asav"
    t = save.read_text(encoding="utf-8", errors="replace")
    print("in the save, LUA_PROBE:", len(re.findall(r"LUA_PROBE: \d+", t)), re.findall(r"LUA_PROBE: \d+", t)[:5], "LUA_ITEM:", len(re.findall(r"LUA_ITEM: \d+", t)), re.findall(r"LUA_ITEM: \d+", t)[:3])
    # с модом: значение идёт дальше; без мода: тем же exe и эталоном
    for name, exe, mods, sets in (("s1tagon", EXE, "lua_all=true", "oxceLuaMods=true"), ("s1tagoff", EXE, "", ""), ("s1tagbase", BASE, "", "")):
        log = open(OUT / f"{name}.txt", "w", encoding="utf-8-sig")
        print(name, start(log, name, exe, save, mods, sets).strip().splitlines()[-1][:120])
        print(name, "turn seed", end_turn(log, name))
        call(log, "run", "--name", name, "--timeout", "60", "key f5; wait 6000; state", timeout=80)
        lualog(log, name)
        q = user(name) / "piratez" / "_quick_.asav"
        t = q.read_text(encoding="utf-8", errors="replace")
        print(name, "LUA_PROBE after:", len(re.findall(r"LUA_PROBE: \d+", t)), re.findall(r"LUA_PROBE: \d+", t)[:5], "LUA_ITEM:", len(re.findall(r"LUA_ITEM: \d+", t)))
        call(log, "stop", "--name", name, timeout=60)


def stale():
    # настоящий урон: юниты гибнут, ручка умирающего сохранена и использована позже
    name = "s1stale"
    log = open(OUT / f"{name}.txt", "w", encoding="utf-8-sig")
    start(log, name, EXE, OUT / "s1same1.asav", "lua_stale=true")
    for _ in range(4):
        end_turn(log, name)
    lualog(log, name)
    call(log, "stop", "--name", name, timeout=60)
    print((OUT / f"{name}.lua.txt").read_text(encoding="utf-8-sig")[-900:])


def k1():
    # режим 0 при k=1: кадр в начале и после хода ИИ
    def one(name, exe):
        log = open(OUT / f"{name}.txt", "w", encoding="utf-8-sig")
        start(log, name, exe, SAVE, "", "oxceHdMode=0")
        call(log, "run", "--name", name, "--timeout", "30", "set k=1; wait 2500; key ctrl+289; wait 2500", timeout=50)
        print(name, end_turn(log, name), flush=True)
        call(log, "run", "--name", name, "--timeout", "30", "key ctrl+289; wait 2500; key f5; wait 5000", timeout=50)
        call(log, "stop", "--name", name, timeout=60)
    jobs = [threading.Thread(target=one, args=i) for i in (("s1k1base", BASE), ("s1k1new", EXE))]
    for j in jobs:
        j.start()
    for j in jobs:
        j.join()


def uiheal():
    # healUnit и skillUseUnit: в бою Пираток ИИ до них не дошёл, поэтому ванильный UFO, встроенная аптечка и навык
    os.environ["OXCE_HIDDEN_DATA"] = "E:/OpenXCom/bin"
    ufomods = HERE / "luamods_ufo"
    d = ufomods / "lua_heal"
    (d / "lua").mkdir(parents=True, exist_ok=True)
    (d / "Ruleset").mkdir(exist_ok=True)
    (d / "metadata.yml").write_text('name: "lua_heal"\nversion: 1.0\nauthor: probe\nmaster: xcom1\nluaApi: 1\n', encoding="utf-8", newline="\n")
    (d / "Ruleset" / "lua_heal.rul").write_text("""
items:
  - type: STR_MEDI_KIT
    medikitType: 1
    medikitTargetSelf: true
    specialUseEmptyHand: true
armors:
  - type: STR_NONE_UC
    specialWeapon: STR_MEDI_KIT
skills:
  - type: STR_LUA_SKILL
    targetMode: 0
    tuUse: 4
soldiers:
  - type: STR_SOLDIER
    skills:
      - STR_LUA_SKILL
""", encoding="utf-8", newline="\n")
    (d / "lua" / "main.lua").write_text("""
local function hands(u)
  local r, l = u:getRightHandWeapon(), u:getLeftHandWeapon()
  return (r and r:getRuleItem():getType() or "nil") .. " / " .. (l and l:getRuleItem():getType() or "nil")
end
local shown = false
game.on("newTurnUnit", function(unit, battle, turn, side)
  if not shown then shown = true; game.log("hands", unit:getId(), hands(unit), "tu", unit:getTimeUnits()) end
end)
game.on("healUnit", function(actor, item, battle, target, battle_action, out)
  game.log("healUnit actor", actor:getId(), "tu", actor:getTimeUnits(), "target", target:getId(), "hp", target:getHealth(), "kit", item:getRuleItem():getType(), "ba", battle_action,
    "out", out.medikit_action_type, out.body_part, out.wound_recovery, out.health_recovery, out.energy_recovery, out.stun_recovery, out.mana_recovery, out.morale_recovery, out.painkiller_recovery)
  target:setHealth(1)
  target:setFatalwounds(game.BODYPART_TORSO, 2)
  out.health_recovery = 11
end)
local uses = 0
game.on("skillUseUnit", function(actor, item, battle, skill, battle_action, have_tu, out)
  uses = uses + 1
  if uses == 3 then error("deliberate error for the notice frame") end
  game.log("skillUseUnit actor", actor:getId(), "hp", actor:getHealth(), "wounds", actor:getFatalwounds(game.BODYPART_TORSO), "tu", actor:getTimeUnits(), skill:getType(), "ba", battle_action, "have_tu", have_tu, "out", out.continue_action, out.spend_tu)
  out.spend_tu = 1
end)
game.on("newTurnItem", function(item, battle, turn, side)
  if turn >= 2 and not shown2 then
    shown2 = true
    game.log("turn", turn, "first owner", item:getOwner() and item:getOwner():getHealth() or "nil")
  end
end)
""", encoding="utf-8", newline="\n")
    name = "s1heal"
    log = open(OUT / f"{name}.txt", "w", encoding="utf-8-sig")
    a = ["start", "--name", name, "--exe", EXE, "--save", "", "--master", "xcom1", "--mods-dir", str(ufomods), "--mods", "lua_heal=true", "--timeout", "300", "--set", "oxceLuaMods=true;oxceHdMode=0"]
    print(call(log, *a, timeout=320).strip().splitlines()[-1][:130], flush=True)
    print(call(log, "run", "--name", name, "--timeout", "60", "open battle; wait 4000; state; key 13; wait 2500; key 27; wait 1500; state", timeout=420)[-200:], flush=True)
    for keys in ("key 113; wait 1200; state; key 49; wait 1500; state", "key 119; wait 1200; state; key 49; wait 1500; state", "key 119; wait 1200; state; key 49; wait 1500; state"):
        print(call(log, "run", "--name", name, "--timeout", "40", keys, timeout=60)[-420:], flush=True)
        print(state(log, name), flush=True)
        if state(log, name)[0] != "BattlescapeState":
            call(log, "run", "--name", name, "--timeout", "30", "key 27; wait 800", timeout=50)
    print(call(log, "run", "--name", name, "--timeout", "30", "key 119; wait 900; key 49; wait 350; shot " + str(OUT / "notice.png").replace(chr(92), "/") + "; wait 300; state", timeout=50)[-160:], flush=True)
    lualog(log, name)
    print((OUT / f"{name}.lua.txt").read_text(encoding="utf-8-sig")[-1800:])
    call(log, "stop", "--name", name, timeout=60)


def mode0():
    identical({"s1m0base": BASE, "s1m0new": EXE}, "oxceHdMode=0")


def identical(names=None, sets=""):
    """Опция выключена: эталон против этапа 1, кадр в начале и после каждого хода ИИ, сейв."""
    names = names or {"s1idbase": BASE, "s1idnew": EXE}
    base_name, new_name = list(names)
    mods = "lua_all=true;lua_a=true;lua_b=true;lua_loop=true;lua_syntax=true;lua_future=true;lua_nokey=true;lua_escape=true"
    seeds = {}
    def one(name, exe):
        log = open(OUT / f"{name}.txt", "w", encoding="utf-8-sig")
        start(log, name, exe, SAVE, mods, sets)
        call(log, "run", "--name", name, "--timeout", "30", "wait 3000; key ctrl+289; wait 2500", timeout=50)
        seeds[name] = []
        for _ in range(3):
            seeds[name].append(end_turn(log, name))
            call(log, "run", "--name", name, "--timeout", "30", "key ctrl+289; wait 2500", timeout=50)
        call(log, "run", "--name", name, "--timeout", "60", "key f5; wait 6000; state", timeout=80)
        call(log, "run", "--name", name, "--timeout", "60", "set k=4; wait 1500; key ctrl+289; wait 2500", timeout=80)
        lualog(log, name)
        call(log, "stop", "--name", name, timeout=60)
    jobs = [threading.Thread(target=one, args=i) for i in names.items()]
    for j in jobs:
        j.start()
    for j in jobs:
        j.join()
    print("seeds base", seeds[base_name])
    print("seeds new ", seeds[new_name], "same:", seeds[base_name] == seeds[new_name])
    print("lua lines in the new build:", (OUT / f"{new_name}.lua.txt").read_text(encoding="utf-8-sig").count("[lua]"))


def kill():
    # ручка цели сохранена, цель убита через API, ручка использована после смерти
    mod("lua_kill", """
local saved
local step = 0
game.on("newTurnUnit", function(unit, battle, turn, side)
  if step == 0 and side == game.FACTION_HOSTILE and unit:getFaction() == game.FACTION_HOSTILE and not unit:isKilled() then
    step = 1
    saved = unit
    game.log("keeping unit", unit:getId(), "hp", unit:getHealth())
    unit:setHealth(0)
    game.log("hp now", unit:getHealth(), "killed", unit:isKilled())
  elseif step == 1 then
    step = 2
    local ok, err = pcall(function() return saved:getHealth() end)
    game.log("same call of nothing: handle of the killed unit:", ok, err)
    error("and the handler dies too")
  end
end)
game.on("newTurnItem", function(item) if step == 2 then step = 3; local ok, err = pcall(function() return saved:isKilled() end); game.log("next event:", ok, err) end end)
""")
    name = "s1kill"
    log = open(OUT / f"{name}.txt", "w", encoding="utf-8-sig")
    start(log, name, EXE, SAVE, "lua_kill=true")
    for _ in range(2):
        print("turn seed", end_turn(log, name))
    lualog(log, name)
    print((OUT / f"{name}.lua.txt").read_text(encoding="utf-8-sig")[-800:])
    j = user(name) / "lua_errors.log"
    print("journal", j.exists())
    call(log, "stop", "--name", name, timeout=60)


def speed():
    # опция выкл., опция вкл. без Lua-модов, опция вкл. с lua_all; три раза по кругу, та же сборка и сейв
    runs = {"off": ("", ""), "on_nomods": ("", "oxceLuaMods=true"), "on_all": ("lua_all=true", "oxceLuaMods=true"), "base": ("", "")}
    res = {k: [] for k in runs}
    for round_ in range(3):
        for what, (mods, sets) in runs.items():
            name = "s1sp" + what.replace("_", "")
            log = open(OUT / f"{name}.txt", "w", encoding="utf-8-sig")
            out = start(log, name, BASE if what == "base" else EXE, SAVE, mods, sets)
            ready = float(re.search(r"(\d+[.,]\d+) .", out[out.index("готов"):]).group(1).replace(",", "."))
            call(log, "run", "--name", name, "--timeout", "30", "wait 2000; key ctrl+289; wait 2500", timeout=50)
            t0 = time.time()
            seed = end_turn(log, name)
            turn = time.time() - t0
            call(log, "run", "--name", name, "--timeout", "30", "key ctrl+289; wait 2500", timeout=50)
            text = call(log, "log", "--name", name, "-n", "20000", timeout=60)
            call(log, "stop", "--name", name, timeout=60)
            perf = []
            for f in sorted((user(name) / "piratez").glob("hdtest*.json"))[-2:]:
                d = __import__("json").loads(f.read_text(encoding="utf-8-sig"))
                perf.append(d.get("perf") or {})
            worst = [int(x) for x in re.findall(r"worst (\d+) ms", text)]
            res[what].append((ready, round(turn, 1), max(worst or [0]), seed, perf[-1:] and {k: perf[-1].get(k) for k in ("drawMs", "uiMs")}))
            print(round_, what, res[what][-1], flush=True)


def ufo():
    # ванильный UFO: опция выкл. эталон против этапа 1 на одном сейве, опция вкл. с Lua-модом
    os.environ["OXCE_HIDDEN_DATA"] = "E:/OpenXCom/bin"
    ufomods = HERE / "luamods_ufo"
    d = ufomods / "lua_ufo"
    (d / "lua").mkdir(parents=True, exist_ok=True)
    (d / "Ruleset").mkdir(exist_ok=True)
    (d / "metadata.yml").write_text('name: "lua_ufo"\nversion: 1.0\nauthor: probe\nmaster: xcom1\nluaApi: 1\n', encoding="utf-8", newline="\n")
    (d / "Ruleset" / "lua_ufo.rul").write_text("extended:\n  tags:\n    BattleUnit:\n      LUA_PROBE: int\n", encoding="utf-8", newline="\n")
    (d / "lua" / "main.lua").write_text("""
game.on("newTurnUnit", function(unit, battle, turn, side)
  unit:setTag("LUA_PROBE", unit:getTag("LUA_PROBE") + 1)
  if unit:getTag("LUA_PROBE") == 1 then game.log("ufo unit", unit:getType(), unit:getRuleArmor():getType(), "hp", unit:getHealth(), "rnd", math.random(1, 100)) end
end)
game.on("hitUnit", function(unit, a, b, c, d, e, f, g, h, out) game.log("ufo hit", unit:getId(), out.power) out.power = out.power + 1 end)
game.log("ufo main.lua ok")
""", encoding="utf-8", newline="\n")

    def begin(log, name, exe, save, mods, sets):
        a = ["start", "--name", name, "--exe", exe, "--save", str(save), "--master", "xcom1", "--mods-dir", str(ufomods), "--mods", mods, "--timeout", "300"]
        if sets:
            a += ["--set", sets]
        print(name, call(log, *a, timeout=320).strip().splitlines()[-1][:130], flush=True)

    name = "s1ufomake"
    log = open(OUT / f"{name}.txt", "w", encoding="utf-8-sig")
    begin(log, name, EXE, "", "lua_ufo=true", "oxceLuaMods=true;oxceHdMode=0")
    print(call(log, "run", "--name", name, "--timeout", "60", "open battle; wait 4000; state; key 13; wait 2500; key 27; wait 1500; state; key f5; wait 4000; state", timeout=420)[-260:], flush=True)
    for _ in range(2):
        print("with Lua, turn seed", end_turn(log, name), flush=True)
    lualog(log, name)
    print((OUT / f"{name}.lua.txt").read_text(encoding="utf-8-sig")[:700])
    save = OUT / "ufo_battle.sav"
    shutil.copy(user(name) / "xcom1" / "_quick_.asav", save)
    call(log, "stop", "--name", name, timeout=60)

    seeds = {}
    def one(nm, exe):
        lg = open(OUT / f"{nm}.txt", "w", encoding="utf-8-sig")
        begin(lg, nm, exe, save, "", "oxceHdMode=0")
        call(lg, "run", "--name", nm, "--timeout", "30", "wait 2500; key ctrl+289; wait 2500", timeout=50)
        seeds[nm] = [end_turn(lg, nm)]
        call(lg, "run", "--name", nm, "--timeout", "30", "key ctrl+289; wait 2500; key f5; wait 4000", timeout=50)
        call(lg, "stop", "--name", nm, timeout=60)
    jobs = [threading.Thread(target=one, args=i) for i in (("s1ufobase", BASE), ("s1ufonew", EXE))]
    for j in jobs:
        j.start()
    for j in jobs:
        j.join()
    print("ufo seeds", seeds, flush=True)


globals()[sys.argv[1]]()
