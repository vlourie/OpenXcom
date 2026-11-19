# API 2, этап 2 в настоящей игре, всё невидимо: деньги и база, сутки и месяц на Пиратках, проигрыш, отметка в сейве.
# Запуск: py -3.13 tools/lua_api2/stage2.py [часть ...]; без аргумента все части. Потолок всего прогона LIMIT.
import os, re, shutil, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage1 as s1
from stage1 import ESC, OPEN, Stand, check, failed, p, quick, reach, row
import lua_mod_check

ROOT = s1.ROOT
HERE = Path(os.environ["TEMP"]) / "oxce_lua_s2t"
OLD_EXE = str(ROOT / "dist/_stage/openxcom_hd") + ".e" + "xe"
ALL = ("s2api", "s2fail", "s2nocap", "s2api1", "s2time", "s2debt", "s2over", "s2battle", "s2auto", "s2heavy")
LIMIT = 420
started = time.time()

COMMON = r'''
local ITEM, SOLDIER = "@ITEM@", "@SOLDIER@"
local function report(tag, f, ...)
  local ok, text = pcall(f, ...)
  game.log("S2 " .. tag, tostring(ok), tostring(text))
end
'''

API = COMMON + r'''
local held
local list = game.getBases()
if list and list[1] then
  report("main addItem", function() list[1]:addItem(ITEM, 1) end)
end
game.screen("api", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  local geo, b = game.getGeoscape(), game.getBases()[1]
  report("build addFunds", function() geo:addFunds(1) end)
  report("build addItem", function() b:addItem(ITEM, 1) end)
  report("build hire", function() b:hireSoldier(SOLDIER) end)
  report("build reads", function() return b:getName() end)
  ui:onClose(function()
    report("close addFunds", function() game.getGeoscape():addFunds(1) end)
  end)
  ui:button{ x = 50, y = 50, w = 220, h = 18, text = "numbers", onClick = function()
    local geo, b = game.getGeoscape(), game.getBases()[1]
    held = b
    game.log("S2 bases", #game.getBases(), b:getName())
    local f0 = geo:getFunds()
    geo:addFunds(1000)
    game.log("S2 funds up", geo:getFunds() - f0)
    geo:addFunds(-1000)
    game.log("S2 funds back", geo:getFunds() - f0)
    report("funds over", function() geo:addFunds(1000000001) end)
    report("funds under", function() geo:addFunds(-1000000001) end)
    report("funds zero", function() geo:addFunds(0) end)
    report("funds text", function() geo:addFunds("x") end)
    local stores, quarters = b:getStores(), b:getQuarters()
    game.log("S2 stores", stores.used, stores.capacity, "quarters", quarters.used, quarters.capacity)
    report("count unknown", function() return b:getItemCount("S2_NOPE") end)
    report("add unknown", function() b:addItem("S2_NOPE", 1) end)
    local c0 = b:getItemCount(ITEM)
    b:addItem(ITEM, 5)
    game.log("S2 items up", b:getItemCount(ITEM) - c0)
    b:removeItem(ITEM, 5)
    game.log("S2 items back", b:getItemCount(ITEM) - c0)
    report("remove more", function() b:removeItem(ITEM, c0 + 1) end)
    report("add zero", function() b:addItem(ITEM, 0) end)
    report("add over", function() b:addItem(ITEM, 1000000001) end)
    local s0, e0 = b:getFreeScientists(), b:getFreeEngineers()
    b:addScientists(3); b:addEngineers(2)
    game.log("S2 staff up", b:getFreeScientists() - s0, b:getFreeEngineers() - e0)
    b:removeScientists(3); b:removeEngineers(2)
    game.log("S2 staff back", b:getFreeScientists() - s0, b:getFreeEngineers() - e0)
    report("remove scientists", function() b:removeScientists(s0 + 1) end)
    report("remove engineers", function() b:removeEngineers(e0 + 1) end)
    report("hire unknown", function() b:hireSoldier("S2_NOPE") end)
  end }
  ui:button{ x = 50, y = 80, w = 220, h = 18, text = "hire", onClick = function()
    local b = game.getBases()[1]
    local q = b:getQuarters()
    local free = q.capacity - q.used
    game.log("S2 free quarters", free)
    report("held dead", function() return held:getName() end)
    local dead = b
    b:hireSoldier(SOLDIER, function(soldier, why)
      game.log("S2 hired", soldier ~= nil, tostring(why), soldier and soldier:getId() or 0)
      report("done dead", function() return dead:getName() end)
      report("done funds", function() game.getGeoscape():addFunds(5) end)
      report("done again", function() game.getBases()[1]:addItem(ITEM, 1) end)
    end)
    game.log("S2 hire asked")
  end }
  ui:button{ x = 50, y = 110, w = 220, h = 18, text = "full", onClick = function()
    local b = game.getBases()[1]
    local q = b:getQuarters()
    local free = q.capacity - q.used
    if free > 0 then b:addScientists(free) end
    b:hireSoldier(SOLDIER, function(soldier, why)
      game.log("S2 full", soldier ~= nil, tostring(why))
    end)
    report("hire many", function() for n = 1, 20 do b:hireSoldier(SOLDIER) end end)
  end }
end, { menu = "api" })
'''

FAIL = COMMON + r'''
game.screen("fail", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  ui:button{ x = 50, y = 50, w = 220, h = 18, text = "fail", onClick = function()
    local geo, b = game.getGeoscape(), game.getBases()[1]
    geo:addFunds(12345)
    b:addItem(ITEM, 7)
    b:removeItem(ITEM, 1)
    b:addScientists(2)
    b:hireSoldier(SOLDIER, function() game.log("S2 fail hired") end)
    game.log("S2 fail before", geo:getFunds(), b:getItemCount(ITEM), b:getFreeScientists())
    error("S2 on purpose")
  end }
  ui:button{ x = 50, y = 80, w = 220, h = 18, text = "look", onClick = function()
    local geo, b = game.getGeoscape(), game.getBases()[1]
    game.log("S2 fail after", geo:getFunds(), b:getItemCount(ITEM), b:getFreeScientists())
  end }
end, { menu = "fail" })
game.on("newHour", function(geo)
  if not hourOnce then
    hourOnce = true
    game.log("S2 fail hour", geo:getFunds())
    geo:addFunds(54321)
    error("S2 hour on purpose")
  end
end)
'''

NOCAP = COMMON + r'''
game.screen("nocap", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  ui:button{ x = 50, y = 50, w = 220, h = 18, text = "go", onClick = function()
    local geo, b = game.getGeoscape(), game.getBases()[1]
    report("addFunds", function() geo:addFunds(1) end)
    report("addItem", function() b:addItem(ITEM, 1) end)
    report("removeScientists", function() b:removeScientists(1) end)
    report("hireSoldier", function() b:hireSoldier(SOLDIER) end)
    report("reads", function() return geo:getFunds() + b:getItemCount(ITEM) + b:getFreeScientists() end)
  end }
end, { menu = "nocap" })
'''

API1 = r'''
local ok, text = pcall(game.on, "newDay", function() end)
game.log("S2 api1 on", tostring(ok), tostring(text))
ok, text = pcall(game.on, "battleEnd", function() end)
game.log("S2 api1 end", tostring(ok), tostring(text))
game.log("S2 api1 bases", tostring(game.getBases))
game.on("newMonthCountry", function()
  local geo = game.getGeoscape
  game.log("S2 api1 month", tostring(geo))
end)
'''

TIME = COMMON + r'''
local hired = false
game.on("newHour", function(geo)
  local t = geo:getTime()
  game.log("S2 hour", t.month, t.day, t.hour)
end)
game.on("newDay", function(geo)
  local t = geo:getTime()
  geo:addFunds(1000)
  game.log("S2 day", t.month, t.day, geo:getFunds())
  if not hired then
    hired = true
    game.getBases()[1]:hireSoldier(SOLDIER, function(soldier, why)
      game.log("S2 day hired", soldier ~= nil, tostring(why), soldier and soldier:getId() or 0)
    end)
  end
end)
game.on("newMonth", function(geo)
  local t = geo:getTime()
  geo:addFunds(777000)
  game.log("S2 month", t.month, t.day, geo:getFunds(), geo:randomRange(1, 1000000))
end)
game.on("newMonthCountry", function(country)
  if not monthOnce then
    monthOnce = true
    report("month country addFunds", function() game.getGeoscape():addFunds(1) end)
  end
end)
'''

DEBT = COMMON + r'''
game.on("newHour", function(geo)
  if geo:getTime().hour == 23 and not done then
    done = true
    local steps = 0
    while geo:getFunds() > -1000000 and steps < 100 do
      geo:addFunds(-1000000000)
      steps = steps + 1
    end
    game.log("S2 debt", steps, geo:getFunds())
  end
end)
'''

OVER = COMMON + r'''
game.screen("over", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  ui:button{ x = 50, y = 50, w = 220, h = 18, text = "stores", onClick = function()
    local b = game.getBases()[1]
    b:addItem(ITEM, b:getStores().capacity + 100000)
    local s = b:getStores()
    game.log("S2 over", s.used > s.capacity)
  end }
  ui:button{ x = 50, y = 80, w = 220, h = 18, text = "quarters", onClick = function()
    local b = game.getBases()[1]
    b:addScientists(b:getQuarters().capacity + 50)
    local q = b:getQuarters()
    game.log("S2 over", q.used > q.capacity)
  end }
end, { menu = "over" })
game.on("newDay", function(geo) game.log("S2 over day", geo:getTime().day) end)
'''

BATTLE = COMMON + r'''
game.screen("inbattle", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  ui:button{ x = 50, y = 50, w = 220, h = 18, text = "go", onClick = function()
    local geo, b = game.getGeoscape(), game.getBases()[1]
    report("battle addFunds", function() geo:addFunds(1) end)
    report("battle addItem", function() b:addItem(ITEM, 1) end)
    report("battle hire", function() b:hireSoldier(SOLDIER) end)
    report("battle reads", function() return b:getItemCount(ITEM) end)
  end }
end, { menu = "inbattle" })
game.on("battleStart", function(battle)
  local x = battle:getSize()
  game.log("S2 begin", x > 0, #battle:getUnits() > 0, #game.getBases() > 0)
  report("start tag", function() game.getGeoscape():setTag("S2_T", 5) end)
  report("start addFunds", function() game.getGeoscape():addFunds(1) end)
  report("start screen", function() game.openScreen("inbattle") end)
end)
game.on("battleEnd", function(battle, aborted)
  game.log("S2 finish", aborted, #battle:getUnits() > 0, battle:getTurn())
  report("end tag", function() game.getGeoscape():setTag("S2_T", 5) end)
  report("end addFunds", function() game.getGeoscape():addFunds(1) end)
  report("end flash", function() battle:flashMessage("x") end)
  report("end screen", function() game.openScreen("inbattle") end)
end)
game.on("newDay", function(geo) geo:addFunds(1) game.log("S2 after battle day") end)
'''

AUTO = COMMON + r'''
local hired = false
game.on("newDay", function(geo)
  if not hired then
    hired = true
    game.getBases()[1]:hireSoldier(SOLDIER, function(soldier, why)
      game.log("S2 auto hired", soldier ~= nil, soldier and soldier:getId() or 0)
      game.getGeoscape():addFunds(4242)
    end)
  end
end)
'''

HEAVY = COMMON + r'''
game.on("newHour", function(geo)
  local b = game.getBases()[1]
  for n = 1, 64 do
    b:addItem(ITEM, 1)
    b:removeItem(ITEM, 1)
    geo:addFunds(1)
    geo:addFunds(-1)
  end
end)
game.on("newHour", function(geo) hours = (hours or 0) + 1 end)
game.on("newDay", function(geo)
  game.log("S2 heavy day", hours)
  for _, b in ipairs(game.getBases()) do
    local q = b:getQuarters()
    if q.capacity - q.used >= 16 then
      for n = 1, 16 do b:hireSoldier(SOLDIER) end
      break
    end
  end
end)
'''


UFO = r"""
game.on("newHour", function(geo)
  if once then return end
  once = true
  local b = game.getBases()[1]
  if not b then
    game.log("S2 ufo nobase")
    return
  end
  local f0, c0, s0 = geo:getFunds(), b:getItemCount("STR_PISTOL"), b:getFreeScientists()
  geo:addFunds(1000)
  b:addItem("STR_PISTOL", 2)
  b:addScientists(1)
  game.log("S2 ufo", geo:getFunds() - f0, b:getItemCount("STR_PISTOL") - c0, b:getFreeScientists() - s0)
  b:hireSoldier("STR_SOLDIER", function(soldier, why)
    game.log("S2 ufo hired", soldier ~= nil, tostring(why))
  end)
end)
"""


def api1_mod(mods, name, code):
    own = mods / name
    (own / "lua").mkdir(parents=True)
    (own / "metadata.yml").write_text(f'id: {name}\nname: "{name}"\nversion: 0.1\nmaster: "piratez"\nluaApi: 1\n', encoding="utf-8", newline="\n")
    (own / "lua/main.lua").write_text(code, encoding="utf-8", newline="\n")


def prepare():
    s1.HERE = HERE
    s1.ALL = ALL
    lua_mod_check.unlink_all(HERE)
    mods = HERE / "mods"
    mods.mkdir(parents=True)
    for d in (s1.GAME / "user/mods").iterdir():
        if d.is_dir():
            lua_mod_check.link_or_copy(d, mods / d.name)
    text = (s1.GAME / "user/piratez/NoCodexCatZ.sav").read_text(encoding="utf-8")
    text = re.sub(r"(?m)^ironman: true$", "ironman: false", text)
    first = text[text.index("\nbases:\n"):]
    item = re.search(r"\n    items:\n      (\w+): \d+", first).group(1)
    soldier = re.search(r"\n    soldiers:\n      - type: (\w+)", first).group(1)
    print("предмет", item, "солдат", soldier, flush=True)
    def code(c):
        return c.replace("@ITEM@", item).replace("@SOLDIER@", soldier)
    eco = "luaCaps: [screens, economy]\n"
    tag = "extended:\n  tags:\n    GeoscapeGame:\n      S2_T: int\n"
    s1.mod(mods, "s2api", code(API), eco)
    s1.mod(mods, "s2fail", code(FAIL), eco)
    s1.mod(mods, "s2nocap", code(NOCAP), "luaCaps: [screens]\n")
    api1_mod(mods, "s2api1", API1)
    s1.mod(mods, "s2time", code(TIME), eco)
    s1.mod(mods, "s2debt", code(DEBT), eco)
    s1.mod(mods, "s2over", code(OVER), eco)
    s1.mod(mods, "s2battle", code(BATTLE), eco, tag)
    s1.mod(mods, "s2auto", code(AUTO), eco)
    s1.mod(mods, "s2heavy", code(HEAVY), eco)
    geo = HERE / "geo.sav"
    geo.write_text(text, encoding="utf-8", newline="\n")
    def at(name, time_line, warned=None):
        t = re.sub(r"(?m)^time: \{.*\}$", time_line, text, count=1)
        if warned is not None:
            t = re.sub(r"(?m)^warned: \w+$", f"warned: {warned}", t, count=1)
        path = HERE / name
        path.write_text(t, encoding="utf-8", newline="\n")
        return path
    month = at("month.sav", "time: {second: 10,minute: 50,hour: 23,weekday: 2,day: 31,month: 3,year: 2606}")
    warn0 = at("warn0.sav", "time: {second: 10,minute: 50,hour: 22,weekday: 2,day: 31,month: 3,year: 2606}", "false")
    warn1 = at("warn1.sav", "time: {second: 10,minute: 50,hour: 22,weekday: 2,day: 31,month: 3,year: 2606}", "true")
    day = at("day.sav", "time: {second: 10,minute: 50,hour: 23,weekday: 2,day: 19,month: 3,year: 2606}")
    listed = "".join(f"  - '{m} ver: 0.1'\n" for m in ALL)
    battle = HERE / "with.sav"
    battle.write_text(re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", listed, s1.SAVE.read_text(encoding="utf-8"), count=1), encoding="utf-8", newline="\n")
    os.environ.pop("OXCE_LUA_API2", None)
    return lua_mod_check.Bench(s1.EXE, HERE), mods, battle, geo, month, warn0, warn1, day


def ints(text, key):
    m = re.search(rf"(?m)^{key}:\n((?:  - -?\d+\n)+)", text)
    return [int(x) for x in re.findall(r"-?\d+", m.group(1))] if m else []


def header(text):
    return text[:text.index("\n---")] if "\n---" in text else text[:2000]


def said(st, word):
    """Хвост строки журнала после тега: то, что сказал мод."""
    out = []
    for line in st.lines(word):
        out.append(line[line.index(word) + len(word):].strip())
    return out


def want(st, word, ok, *parts):
    got = said(st, "S2 " + word)
    last = got[-1] if got else ""
    good = bool(got) and last.startswith(ok) and all(x in last for x in parts)
    check(f"{word}: {ok} {' '.join(parts)}", good, last[:130])


def grab(st, target):
    path = quick(st, target)
    check(f"сохранение {target.name}", path is not None)
    return target.read_text(encoding="utf-8", errors="replace") if path else ""


def open_screen(st, keys_want="LuaScreenState"):
    """Со списка экранов на экран мода; окно игры может влезть, reach это знает."""
    return reach(st, f"{OPEN}; {row(0)}; wait 300", keys_want)


def part_api(ctx):
    bench, mods, battle, geo, *_ = ctx
    with Stand(ctx, "s2a", geo, ("s2api",)) as st:
        check("геоскейп: экран открыт", open_screen(st), st.top())
        want(st, "build addFunds", "false", "only read")
        want(st, "build addItem", "false", "only read")
        want(st, "build hire", "false", "only read")
        want(st, "build reads", "true")
        st.run(f"{p(150, 59)}; wait 300")
        check("геоскейп: без ошибок мода", not st.errors(), st.errors()[:300])
        want(st, "bases", "", "")
        want(st, "funds up", "1000")
        want(st, "funds back", "0")
        want(st, "funds over", "false", "1000000000")
        want(st, "funds under", "false", "1000000000")
        want(st, "funds zero", "true")
        want(st, "funds text", "false")
        got = said(st, "S2 stores")
        print("склад и места:", got[-1:], flush=True)
        m = re.fullmatch(r"(\S+) (\d+) quarters (\d+) (\d+)", got[-1]) if got else None
        check("склад и места: числа, места целые", m and int(m.group(2)) > 0 and int(m.group(4)) > 0, str(got[-1:]))
        want(st, "count unknown", "false", "S2_NOPE")
        want(st, "add unknown", "false", "S2_NOPE")
        want(st, "items up", "5")
        want(st, "items back", "0")
        want(st, "remove more", "false", "the stores have")
        want(st, "add zero", "false", "from 1 to")
        want(st, "add over", "false", "1000000000")
        want(st, "staff up", "3 2")
        want(st, "staff back", "0 0")
        want(st, "remove scientists", "false", "without work")
        want(st, "remove engineers", "false", "without work")
        want(st, "hire unknown", "false", "S2_NOPE")
        st.run(f"{p(150, 89)}; wait 300")
        free = said(st, "S2 free quarters")
        print("свободных мест:", free, flush=True)
        want(st, "held dead", "false")
        asked, hired = st.lines("S2 hire asked"), st.lines("S2 hired")
        check("найм после клика", asked and hired, str(hired[-1:])[:120])
        if free and int(free[-1]) > 0:
            want(st, "hired", "true")
        want(st, "done dead", "false")
        want(st, "done funds", "true")
        want(st, "done again", "true")
        st.run(f"{p(150, 119)}; wait 300")
        want(st, "full", "false", "no free quarters")
        want(st, "hire many", "false", "16")
        st.run(f"{ESC}")
        want(st, "close addFunds", "false", "only read")
        st.run(ESC)
        text = grab(st, HERE / "api.asav")
        check("отметка в заголовке", "luaTouched:" in header(text) and "s2api" in header(text) and "economy" in header(text), re.search(r"luaTouched.*", text).group(0)[:80] if "luaTouched" in text else "нет")
        # F8 пишет отчёт: строка для тикета
        st.run("key 289; wait 1200", 30)
        found = sorted(st.bench.folder(st.name).rglob("context.json"), key=lambda f: f.stat().st_mtime)
        ctxt = found[-1].read_text(encoding="utf-8") if found else ""
        print("отчёт:", found[-1] if found else "нет", flush=True)
        check("отчёт: saveTouched", '"saveTouched"' in ctxt and "s2api economy" in ctxt, re.search(r'"saveTouched[^\]]*\]', ctxt).group(0)[:80] if "saveTouched" in ctxt else ctxt[:80])
    # № 9: мод снят, след остался, старая сборка грузит сейв с новой строкой
    with Stand(ctx, "s2r", HERE / "api.asav", ()) as st:
        # окно игры может прийти сразу после выхода на геоскейп: смотрим сам выход
        check("№ 9 мод снят: загрузка без падения", reach(st, "wait 200", "GeoscapeState"), st.top())
        text = grab(st, HERE / "removed.asav")
        check("№ 9 мод снят: отметка держится в новом сохранении", "s2api" in header(text) and "luaTouched:" in header(text))
    keep = s1.EXE
    s1.EXE = OLD_EXE
    try:
        with Stand(ctx, "s2o", HERE / "api.asav", ()) as st:
            check("чужой ключ заголовка: старая сборка 2026.11.06-2 грузит сейв", reach(st, "wait 200", "GeoscapeState"), st.top())
    finally:
        s1.EXE = keep


def part_fail(ctx):
    bench, mods, battle, geo, *_ = ctx
    with Stand(ctx, "s2f", geo, ("s2fail",)) as st:
        check("откат: экран открыт", open_screen(st), st.top())
        st.run(f"{p(150, 89)}; wait 200")
        before = said(st, "S2 fail after")
        st.run(f"{p(150, 59)}; wait 300")
        st.run(f"{p(150, 89)}; wait 200")
        after = said(st, "S2 fail after")
        told = said(st, "S2 fail before")
        print("до", before[-1:], "внутри", told[-1:], "после", after[-1:], flush=True)
        check("ошибка в клике снимает деньги, склад, персонал", before and after and before[-1] == after[-1], f"{before[-1:]} {after[-1:]}")
        check("изнутри обработчика менялось", told and before and told[-1] != before[-1])
        check("ошибка в клике снимает найм", not st.lines("S2 fail hired"))
        st.run(f"{ESC}; {ESC}")
        check("ошибка в журнале мода", "on purpose" in st.errors(), st.errors()[:100])
        st.run("key 53; wait 200")
        t0 = time.time()
        while time.time() - t0 < 25 and not st.lines("S2 fail hour"):
            if st.top() not in ("GeoscapeState", ""):
                st.run(ESC, 30)
            st.run("key 53", 30)
            time.sleep(0.5)
        check("ошибка в newHour в журнале", "S2 hour on purpose" in st.errors(), st.errors()[-120:])
        st.run("key 49; wait 100")
        text = grab(st, HERE / "fail.asav")
        check("снятая операция отметки не оставляет", "luaTouched" not in header(text), re.search(r"luaTouched.*", text).group(0)[:80] if "luaTouched" in text else "")


def part_caps(ctx):
    bench, mods, battle, geo, *_ = ctx
    with Stand(ctx, "s2n", geo, ("s2nocap",)) as st:
        check("без слова: экран открыт", open_screen(st), st.top())
        st.run(f"{p(150, 59)}; wait 300")
        for name in ("addFunds", "addItem", "removeScientists", "hireSoldier"):
            want(st, name, "false", name, "economy")
        want(st, "reads", "true")
        st.run(f"{ESC}; {ESC}")
        text = grab(st, HERE / "nocap.asav")
        check("отказ отметки не оставляет", "luaTouched" not in header(text))
    with Stand(ctx, "s2v1", geo, ("s2api1",)) as st:
        reach(st, "wait 200", "GeoscapeState")
        got = said(st, "S2 api1 on") + said(st, "S2 api1 end")
        check("luaApi 1: новые события неизвестны", len(got) >= 2 and all("false" in g and "unknown event" in g for g in got[-2:]), str(got[-2:])[:160])
        api1 = said(st, "S2 api1 bases")
        check("luaApi 1: game.getBases нет", api1 and api1[-1].startswith("nil"), str(api1[-1:]))
        check("luaApi 1: без ошибок мода", not st.errors(), st.errors()[:200])


def run_month(ctx, name, mod_ids, save, stop):
    """Идёт часами, пока stop(st) не скажет хватит; окна игры закрывает, кроме отчёта месяца, его отметит."""
    with_report = False
    st = Stand(ctx, name, save, mod_ids)
    st.run("key 53; wait 200")
    t0 = time.time()
    while time.time() - t0 < 60 and not stop(st):
        top = st.top()
        if top == "MonthlyReportState":
            with_report = True
            break
        if top not in ("GeoscapeState", ""):
            st.run(ESC, 30)
        st.run("key 53", 30)
        time.sleep(0.3)
    return st, with_report


def part_month(ctx):
    bench, mods, battle, geo, month, *_ = ctx
    runs = {}
    for label, name, ids in (("без мода", "s2m0", ()), ("мод", "s2m1", ("s2time",)), ("мод снова", "s2m2", ("s2time",))):
        st, reported = run_month(ctx, name, ids, month, lambda s: False)
        try:
            check(f"{label}: отчёт месяца пришёл", reported, st.top())
            st.run("wait 500")
            shot = HERE / f"report_{name}.png"
            st.run(f"shot {shot.as_posix()}", 30)
            first = said(st, "S2 month") + said(st, "S2 day") + said(st, "S2 hour")
            hired = said(st, "S2 day hired")
            print(label, first[:4], hired[:1], flush=True)
            # закрыть отчёт и дождаться геоскейпа
            for _ in range(8):
                if st.top() == "GeoscapeState":
                    break
                st.run("key 13; wait 300", 30)
            st.run("key 49; wait 100", 30)
            text = grab(st, HERE / f"{name}.asav")
            runs[label] = dict(funds=ints(text, "funds"), income=ints(text, "incomes"), spent=ints(text, "expenditures"), head=header(text), first=first, hired=hired,
                               days=len(said(st, "S2 day") and [d for d in said(st, "S2 day") if not d.startswith("hired") and not d.startswith("true") and not d.startswith("false")]), text=text)
            if ids:
                order = [l for l in st.lines("S2 ") if re.search(r"S2 (month|day|hour) \d", l)]
                seq = [re.search(r"S2 (month|day|hour) \d", l).group(1) for l in order[:3]]
                check(f"{label}: порядок в такте месяц, сутки, час", seq == ["month", "day", "hour"], str(seq))
                want(st, "month country addFunds", "false", "only read")
                check(f"{label}: без ошибок мода", not st.errors(), st.errors()[:200])
        finally:
            st.bench.call("stop", "--name", st.name, timeout=60)
    base, a, b = runs.get("без мода"), runs.get("мод"), runs.get("мод снова")
    if not (base and a and b):
        check("месяц: все три прогона дошли", False)
        return
    print("прошлый месяц без мода", base["funds"][-2], base["income"][-2], base["spent"][-2], flush=True)
    print("прошлый месяц с модом ", a["funds"][-2], a["income"][-2], a["spent"][-2], flush=True)
    print("новый месяц без мода ", base["funds"][-1], base["income"][-1], base["spent"][-1], flush=True)
    print("новый месяц с модом  ", a["funds"][-1], a["income"][-1], a["spent"][-1], "суток", a["days"], flush=True)
    check("№ 15 отчёт прошлого месяца не изменён модом", (base["funds"][-2], base["income"][-2], base["spent"][-2]) == (a["funds"][-2], a["income"][-2], a["spent"][-2]))
    paid = 777000 + 1000 * a["days"]
    check("№ 15 приход нового месяца: ровно то, что мод дал", a["income"][-1] - base["income"][-1] == paid, f"{a['income'][-1] - base['income'][-1]} ожидалось {paid}")
    check("№ 15 расход нового месяца тот же", a["spent"][-1] == base["spent"][-1], f"{a['spent'][-1]} {base['spent'][-1]}")
    check("№ 15 деньги нового месяца: ровно то, что мод дал", a["funds"][-1] - base["funds"][-1] == paid, f"{a['funds'][-1] - base['funds'][-1]} ожидалось {paid}")
    check("отметка только с модом", "luaTouched" in a["head"] and "luaTouched" not in base["head"])
    check("найм из newDay выполнен", a["hired"] and a["hired"][0].startswith("true"), str(a["hired"][:1]))
    check("№ 7 тот же сид: те же значения и тот же солдат", a["first"][:3] == b["first"][:3] and a["hired"][:1] == b["hired"][:1], f"{a['first'][:2]} {b['first'][:2]}")
    if a["hired"]:
        sid = a["hired"][0].split()[-1]
        check("солдат в сейве: идёт на базу", re.search(rf"\n\s+id: {sid}\n", a["text"]) is not None, sid)


def part_debt(ctx):
    bench, mods, battle, geo, month, warn0, warn1, *_ = ctx
    st, reported = run_month(ctx, "s2d0", ("s2debt",), warn0, lambda s: False)
    try:
        check("долг 1: отчёт месяца пришёл", reported, st.top())
        debt = said(st, "S2 debt")
        print("долг:", debt[-1:], flush=True)
        check("долг ниже порога", debt and int(debt[-1].split()[-1]) <= -1000000, str(debt[-1:]))
        settle(st)
        check("долг 1: предупреждение, игра идёт", st.top() == "GeoscapeState", st.top())
        st.run("key 49; wait 100", 30)
        text = grab(st, HERE / "debt0.asav")
        check("долг 1: совет предупредил", re.search(r"(?m)^warned: true$", text) is not None)
    finally:
        st.bench.call("stop", "--name", st.name, timeout=60)
    st, reported = run_month(ctx, "s2d1", ("s2debt",), warn1, lambda s: False)
    try:
        check("долг 2: отчёт месяца пришёл", reported, st.top())
        seen = []
        for _ in range(6):
            top = st.top()
            seen.append(top)
            if top not in ("MonthlyReportState",):
                break
            st.run("key 13; wait 500", 30)
        print("после отчёта:", seen, flush=True)
        check("№ 15 долг 2: проигрыш штатный", seen[-1] in ("DefeatState", "VideoState", "CutsceneState", "SlideshowState"), str(seen))
    finally:
        st.bench.call("stop", "--name", st.name, timeout=60)
    st, reported = run_month(ctx, "s2d2", (), warn1, lambda s: False)
    try:
        check("без мода: отчёт месяца пришёл", reported, st.top())
        settle(st)
        check("без мода и без долга проигрыша нет", st.top() == "GeoscapeState", st.top())
    finally:
        st.bench.call("stop", "--name", st.name, timeout=60)


def settle(st, tries=20):
    """Закрыть окна игры: отчёт месяца Enter, прочее Esc."""
    seen = []
    for _ in range(tries):
        top = st.top()
        if top == "GeoscapeState":
            break
        seen.append(top)
        st.run("key 13; wait 300" if top == "MonthlyReportState" else "key 27; wait 300", 30)
    return seen


def part_over(ctx):
    bench, mods, battle, geo, month, *_ = ctx
    with Stand(ctx, "s2w", month, ("s2over",)) as st:
        check("склад: экран открыт", open_screen(st), st.top())
        st.run(f"{p(150, 59)}; wait 300")
        want(st, "over", "true")
        st.run(f"{ESC}; {ESC}")
        t0 = time.time()
        while time.time() - t0 < 30 and st.top() != "SellState":
            if st.top() != "GeoscapeState":
                st.run("key 13; wait 300" if st.top() == "MonthlyReportState" else ESC, 30)
            st.run("key 53", 30)
            time.sleep(0.3)
        check("склад сверх лимита: штатное окно продажи", st.top() == "SellState", st.top())
        st.run(f"{ESC}; wait 300", 30)
        check("пока не продано, окно не закрыть (штатно)", st.top() == "SellState", st.top())
        check("склад: без ошибок мода", not st.errors(), st.errors()[:200])
    with Stand(ctx, "s2v", month, ("s2over",)) as st:
        check("места: экран открыт", open_screen(st), st.top())
        st.run(f"{p(150, 89)}; wait 300")
        want(st, "over", "true")
        st.run(f"{ESC}; {ESC}")
        t0 = time.time()
        seen = set()
        while time.time() - t0 < 40 and not said(st, "S2 over day"):
            seen.update(settle(st))
            st.run("key 53", 30)
            time.sleep(0.3)
        seen.update(settle(st))
        print("сутки после перебора:", len(said(st, "S2 over day")), sorted(seen), flush=True)
        check("места сверх лимита: сутки прошли", said(st, "S2 over day"), str(sorted(seen)))
        check("места: без ошибок мода", not st.errors(), st.errors()[:200])
        text = grab(st, HERE / "over.asav")
    with Stand(ctx, "s2v2", HERE / "over.asav", ("s2over",)) as st:
        reach(st, "wait 200", "GeoscapeState")
        check("перебор: сейв грузится", st.top() == "GeoscapeState", st.top())


def part_battle(ctx):
    bench, mods, battle, geo, *_ = ctx
    with Stand(ctx, "s2b", battle, ("s2battle",)) as st:
        st.run(f"wait 500; {OPEN}; {row(0)}; wait 300")
        check("бой: экран открыт", st.top() == "LuaScreenState", st.top())
        st.run(f"{p(150, 59)}; wait 300")
        want(st, "battle addFunds", "false", "battle")
        want(st, "battle addItem", "false", "battle")
        want(st, "battle hire", "false", "battle")
        want(st, "battle reads", "true")
        st.run(f"{ESC}; {ESC}")
        text = grab(st, HERE / "battle.asav")
        check("№ 10 отказ в бою отметки не оставляет", "luaTouched" not in header(text))


def part_campaign(ctx):
    sys.path.insert(0, str(ROOT / "tools/lua_stage5"))
    import defects
    camp = HERE / "camp"
    camp.mkdir(exist_ok=True)
    save = defects.geoscape_save(camp)
    with Stand(ctx, "s2c", save, ("s2battle",)) as st:
        t0 = time.time()
        order = []
        while time.time() - t0 < 45:
            top = st.top()
            if top and (not order or order[-1] != top):
                order.append(top)
            if top == "BattlescapeState":
                break
            if top == "ConfirmLandingState":
                st.run("key 13; wait 1200", 60)
            elif top == "BriefingState":
                st.run("key 13; wait 800", 60)
            elif top not in ("GeoscapeState", ""):
                st.run(ESC, 30)
            time.sleep(0.5)
        print("экраны:", order, f"{time.time() - t0:.0f} с", flush=True)
        check("бой кампании начался", st.top() == "BattlescapeState", st.top())
        want(st, "begin", "true true true")
        want(st, "start tag", "false", "only reads")
        want(st, "start addFunds", "false")
        want(st, "start screen", "false")
        st.run("key 97; wait 400", 30)
        print("прерывание:", st.top(), flush=True)
        t0 = time.time()
        order = []
        while time.time() - t0 < 40:
            top = st.top()
            if top and (not order or order[-1] != top):
                order.append(top)
            if top == "GeoscapeState":
                break
            if top == "BattlescapeState":
                st.run("key 97; wait 400", 30)
            elif top in ("SoldierVoiceState", "NextTurnState"):
                st.run("key 27; wait 300", 30)
            else:
                st.run("key 13; wait 500", 30)
            time.sleep(0.2)
        print("конец боя:", order, f"{time.time() - t0:.0f} с", flush=True)
        check("бой прерван и вернулись на геоскейп", st.top() == "GeoscapeState", st.top())
        want(st, "finish", "1 true")
        want(st, "end tag", "false", "only reads")
        want(st, "end addFunds", "false")
        want(st, "end flash", "false", "only reads")
        want(st, "end screen", "false")
        check("конец боя: без ошибок мода", not st.errors(), st.errors()[:200])
        st.run("key 54; wait 100", 30)
        t0 = time.time()
        seen = set()
        while time.time() - t0 < 30 and not st.lines("S2 after battle day"):
            if st.top() not in ("GeoscapeState", ""):
                seen.add(st.top())
                st.run(ESC, 30)
            st.run("key 54", 30)
            time.sleep(0.3)
        print("после боя окна:", sorted(seen), f"{time.time() - t0:.0f} с", flush=True)
        check("после боя сутки идут и деньги работают", st.lines("S2 after battle day") and not st.errors(), st.errors()[:200])


def part_auto(ctx):
    day = ctx[-1]
    with Stand(ctx, "s2s", day, ("s2auto",)) as st:
        st.run("key 53; wait 200")
        folder = st.bench.folder(st.name)
        t0 = time.time()
        while time.time() - t0 < 30 and not st.lines("S2 auto hired"):
            if st.top() not in ("GeoscapeState", "", "SaveGameState"):
                st.run("key 13; wait 200", 30)
            st.run("key 53", 30)
            time.sleep(0.3)
        hired = said(st, "S2 auto hired")
        check("автосохранение: найм выполнен", hired and hired[-1].startswith("true"), str(hired[-1:]))
        st.run("wait 1500", 30)
        autos = sorted((f for f in folder.rglob("*auto*.asav")), key=lambda f: f.stat().st_mtime)
        print("автосохранения:", [f.name for f in autos][-3:], flush=True)
        check("автосохранение на месте", bool(autos))
        if autos and hired:
            text = autos[-1].read_text(encoding="utf-8", errors="replace")
            sid = hired[-1].split()[-1]
            check("автосохранение: солдат и деньги из done уже в файле", re.search(rf"\n\s+id: {sid}\n", text) is not None and "luaTouched" in header(text), sid)
        check("автосохранение: без ошибок мода", not st.errors(), st.errors()[:200])


def part_measure(ctx):
    """§10 базового ТЗ: цена новых событий. Часы и сутки одного и того же сейва, кадры геоскейпа."""
    bench, mods, battle, geo, *_ = ctx
    out = {}
    for label, name, ids in (("без мода", "s2p0", ()), ("тяжёлый мод", "s2p1", ("s2heavy",))):
        log = HERE / f"frames_{name}.tsv"
        if log.exists():
            log.unlink()
        with Stand(ctx, name, geo, ids, OXCE_HD_FRAMELOG=str(log)) as st:
            st.run("key 54; wait 200", 30)
            t0 = time.time()
            while time.time() - t0 < 30:
                if st.top() not in ("GeoscapeState", ""):
                    st.run("key 27; wait 100", 30)
                st.run("key 54", 30)
                time.sleep(0.2)
            st.run("key 49; wait 100", 30)
            text = grab(st, HERE / f"{name}.asav")
            print(label, re.search(r"(?m)^time: \{.*\}$", text).group(0)[:60] if text else "сейва нет", flush=True)
            if ids:
                check("замер: без ошибок мода", not st.errors(), st.errors()[:200])
                print("суток с модом:", len(said(st, "S2 heavy day")), said(st, "S2 heavy day")[-1:], flush=True)
        os.environ.pop("OXCE_HD_FRAMELOG", None)
        rows = []
        with open(log, encoding="utf-8", errors="replace") as f:
            head = f.readline().rstrip("\n").split("\t")
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == len(head):
                    rows.append(dict(zip(head, parts)))
        v = sorted(int(r["loop_us"]) / 1000 for r in rows if "GeoscapeState" in r["state"])
        if v:
            v = v[:-1]  # самый первый кадр геоскейпа после загрузки, он есть и без мода
        out[label] = (len(v), round(v[len(v) // 2], 2), round(v[int(len(v) * 0.95)], 2), round(v[-1], 1)) if v else None
        print(label, "кадры (число, p50 мс, p95 мс, худший мс):", out[label], flush=True)
    check("замер есть", all(out.values()))


def part_ufo(ctx):
    """№ 17: ванильный UFO, новая кампания стенда."""
    bench = ctx[0]
    mods = HERE / "mods_ufo"
    mods.mkdir(exist_ok=True)
    s1.mod(mods, "s2ufo", UFO, "luaCaps: [economy]\n")
    meta = mods / "s2ufo/metadata.yml"
    meta.write_text(meta.read_text(encoding="utf-8").replace("piratez", "xcom1"), encoding="utf-8", newline="\n")
    name = "s2u"
    lua_mod_check.unlink_all(bench.folder(name))
    a = ["start", "--name", name, "--exe", s1.EXE, "--save", "", "--master", "xcom1", "--mods-dir", str(mods), "--mods", "s2ufo=true", "--timeout", "120", "--set", "oxceLuaMods=true"]
    print(name, bench.call(*a, timeout=140).strip().splitlines()[-1][:120], flush=True)
    try:
        print(bench.run(name, "open geoscape; wait 1500; state", 60).strip()[-100:], flush=True)
        t0 = time.time()
        seen = set()
        log = bench.folder(name) / "openxcom.log"
        def text():
            return log.read_text(encoding="utf-8", errors="replace")
        while time.time() - t0 < 30 and "S2 ufo hired" not in text():
            top = bench.state(name)[0]
            seen.add(top)
            if top not in ("GeoscapeState", ""):
                bench.run(name, "key 27; wait 200", 30)
            bench.run(name, "key 53; wait 300", 30)
        print("окна:", sorted(seen), flush=True)
        lines = [l.split("S2 ", 1)[1].strip() for l in text().splitlines() if "S2 ufo" in l]
        print(lines, flush=True)
        check("UFO: деньги, склад, учёные", "ufo 1000 2 1" in lines, str(lines))
        check("UFO: найм выполнен", any(l.startswith("ufo hired true") for l in lines), str(lines))
        path = bench.folder(name) / "lua_errors.log"
        errs = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        check("UFO: журнал ошибок Lua пуст", not errs, errs[:200])
    finally:
        bench.call("stop", "--name", name, timeout=60)


PARTS = {"api": part_api, "fail": part_fail, "caps": part_caps, "month": part_month, "debt": part_debt, "over": part_over, "battle": part_battle, "campaign": part_campaign, "auto": part_auto, "ufo": part_ufo, "measure": part_measure}

if __name__ == "__main__":
    ctx = prepare()
    names = sys.argv[1:] or list(PARTS)
    for n in names:
        if time.time() - started > LIMIT:
            check(f"потолок времени {LIMIT} с: {n} и дальше не прогнаны", False)
            break
        t0 = time.time()
        print(f"--- {n}", flush=True)
        try:
            PARTS[n](ctx)
        except Exception as e:
            check(f"{n}: сбой проверки", False, repr(e)[:300])
        print(f"--- {n}: {time.time() - t0:.0f} с", flush=True)
    print(f"итог: {'FAIL ' + str(len(failed)) if failed else 'PASS'}, {time.time() - started:.0f} с", flush=True)
    for f in failed:
        print("  FAIL:", f[:140])
    sys.exit(1 if failed else 0)
