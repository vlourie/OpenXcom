# API 2, этап 1 в настоящей игре, всё невидимо: экраны, вход игрока, потолки, чистота, сид и сейв (docs/portal/LUA_MODS_V2.md, §5.1, §10).
# Запуск: py -3.13 tools/lua_api2/stage1.py [часть ...]; без аргумента все части. Потолок всего прогона 8 минут.
import difflib, os, re, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/lua_api2"))
sys.path.insert(0, str(ROOT / "tools/lua_stage5"))
import lua_mod_check, bank_mod

HERE = Path(os.environ["TEMP"]) / "oxce_lua_s1t"
EXE = os.environ.get("OXCE_LUA_EXE", str(ROOT / "build-release/bin") + "/" + "openxcom" + ".e" + "xe")
GAME = ROOT / "Пиратки/Dioxine_XPiratez"
SAVE = ROOT / "tools/lua_stage1/lua_battle.sav"
ALL = ("s1bank", "s1t", "s1nocap", "s1turn", "s1done", "s1month", "s1brief")
LIMIT = 480
failed = []
started = time.time()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

T = r'''
local saved = {}
local function report(tag, f, ...)
  local ok, text = pcall(f, ...)
  game.log("S1 " .. tag, tostring(ok), tostring(text))
end

game.screen("pure", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  report("build write", function() game.getGeoscape():setTag("S1_T", 5) end)
  report("build random", function() return game.getGeoscape():randomRange(1, 6) end)
  report("build open", function() game.openScreen("leaf") end)
  ui:button{ x = 50, y = 150, w = 220, h = 18, text = "write", onClick = function()
    report("click write", function() game.getGeoscape():setTag("S1_T", 5) end)
    report("click random", function() return game.getGeoscape():randomRange(1, 6) end)
  end }
  ui:onClose(function()
    report("close write", function() game.getGeoscape():setTag("S1_T", 6) end)
    report("close random", function() return game.getGeoscape():randomRange(1, 6) end)
    report("close open", function() game.openScreen("leaf") end)
  end)
end, { menu = "pure" })

game.screen("bad", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  error("S1 build on purpose")
end, { menu = "bad" })

game.screen("closeerr", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  ui:onClose(function() error("S1 close on purpose") end)
end, { menu = "closeerr" })

game.screen("nest", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  game.log("S1 nest built")
  ui:button{ x = 50, y = 150, w = 220, h = 18, text = "more", onClick = function()
    report("nest open", function() game.openScreen("nest") end)
  end }
end, { menu = "nest" })

game.screen("leaf", function(ui)
  ui:window{ x = 100, y = 60, w = 120, h = 60 }
  game.log("S1 leaf built")
end)

game.screen("ceil", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  ui:button{ x = 50, y = 150, w = 220, h = 18, text = "leaf", onClick = function()
    report("ceil open", function() game.openScreen("leaf") end)
  end }
end, { menu = "ceil" })

game.screen("methods", function(ui)
  ui:window{ x = 10, y = 6, w = 300, h = 188 }
  local t = ui:text{ x = 20, y = 12, w = 100, h = 10, text = "STR_OK" }
  local b = ui:toggleButton{ x = 20, y = 24, w = 100, h = 16, text = "t", pressed = false }
  local l = ui:list{ x = 20, y = 44, w = 100, h = 40, columns = { 50, 50 }, selectable = true }
  local c = ui:comboBox{ x = 140, y = 12, w = 100, h = 16, options = { "a" } }
  local s = ui:slider{ x = 140, y = 32, w = 100, h = 16, min = 0, max = 10, value = 1 }
  local e = ui:edit{ x = 140, y = 52, w = 100, h = 10, text = "e" }
  local i = ui:image{ x = 140, y = 70, image = "S1_ICON.PNG" }
  local function same(tag, got, want)
    game.log("S1 m " .. tag, tostring(got == want), tostring(got))
  end
  t:setText("abc"); same("text", t:getText(), "abc")
  t:setVisible(false); same("hidden", t:isVisible(), false); t:setVisible(true); same("shown", t:isVisible(), true)
  b:setPressed(true); same("pressed", b:isPressed(), true)
  l:addRow("r1", "1"); l:addRow("r2", "2"); same("rows", l:getRowCount(), 2)
  l:setCell(2, 2, "x"); same("cell", l:getRowCount(), 2)
  same("selected", l:getSelected(), 1)
  l:clearList(); same("clear", l:getRowCount(), 0)
  c:setOptions({ "p", "q", "r" }); c:setSelected(3); same("combo", c:getSelected(), 3)
  s:setRange(0, 50); s:setValue(25); same("slider", s:getValue(), 25)
  e:setText("zz"); same("edit", e:getText(), "zz"); e:setFocus(true)
  i:setImage("S1_ICON.PNG"); i:setVisible(true); same("image", i:isVisible(), true)
  report("no field", function() ui:text{ x = 1, y = 1, w = 1, h = 1, bogus = 1 } end)
  report("wrong kind", function() t:setValue(1) end)
  report("no picture", function() ui:image{ x = 1, y = 1, image = "S1_NONE.PNG" } end)
  report("cols", function() ui:list{ x = 1, y = 1, w = 9, h = 9, columns = { 1, 1, 1, 1, 1, 1, 1, 1, 1 } } end)
  report("widgets", function() for n = 1, 100 do ui:text{ x = 1, y = 1, w = 9, h = 9, text = "" } end end)
  saved.ui, saved.t = ui, t
end, { menu = "methods" })

game.screen("dead", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  report("dead ui", function() saved.ui:text{ x = 1, y = 1, w = 1, h = 1, text = "" } end)
  report("dead widget", function() return saved.t:getText() end)
  ui:button{ x = 50, y = 150, w = 220, h = 18, text = "nope", onClick = function()
    report("no screen", function() game.openScreen("nope") end)
  end }
end, { menu = "dead" })

game.screen("rows", function(ui)
  ui:window{ x = 10, y = 6, w = 300, h = 188 }
  local list = ui:list{ x = 20, y = 12, w = 260, h = 160, columns = { 130, 120 }, selectable = true }
  local good, said = 0, nil
  for n = 1, 2100 do
    local ok, text = pcall(function() list:addRow("row " .. n, tostring(n * n)) end)
    if ok then good = good + 1 else said = text end
  end
  game.log("S1 rows", good, tostring(said))
end, { menu = "rows" })
'''

NOCAP = r'''
local ok, text = pcall(function() game.screen("x", function(ui) end) end)
game.log("S1 nocap screen", tostring(ok), tostring(text))
local said = false
game.on("newTurnUnit", function(unit, battle, turn, side)
  if said then return end
  said = true
  local ok2, text2 = pcall(function() game.openScreen("x") end)
  game.log("S1 nocap open", tostring(ok2), tostring(text2))
end)
'''

TURN = r'''
local ai, fall, player = false, false, 0
game.screen("ai", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  game.log("S1 ai built")
end)
game.screen("fall", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  game.log("S1 fall built")
end)
game.screen("loop", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  game.log("S1 loop built")
end)
game.on("newTurnUnit", function(unit, battle, turn, side)
  if side ~= game.FACTION_PLAYER then
    if not ai then
      ai = true
      game.openScreen("ai")
      game.log("S1 ai asked", side)
    elseif not fall then
      fall = true
      unit:setHealth(0)
      game.openScreen("fall")
      game.log("S1 fall asked", side)
    end
  elseif player == 0 then
    player = 1
    local good, said = 0, nil
    for n = 1, 100 do
      local ok, text = pcall(function() game.openScreen("loop") end)
      if ok then good = good + 1 else said = text end
    end
    game.log("S1 loop call", good, tostring(said))
  elseif player == 1 then
    player = 2
    for n = 1, 100000 do game.openScreen("loop") end
    game.log("S1 loop passed")
  elseif player < 20 then
    player = player + 1
    local ok, text = pcall(function() game.openScreen("loop") end)
    game.log("S1 loop next", tostring(ok), tostring(text))
  end
end)
'''

DONE = r'''
local asked = false
game.screen("fromdone", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  game.log("S1 fromdone built")
end)
game.on("newTurnUnit", function(unit, battle, turn, side)
  if asked or side ~= game.FACTION_PLAYER then return end
  asked = true
  local x, y, z = unit:getPosition()
  battle:spawnItem("STR_ELECTRO_FLARE", x, y, z, function(item)
    game.log("S1 done battle", tostring(game.getBattle() ~= nil))
    game.openScreen("fromdone")
  end)
end)
'''

MONTH = r'''
local asked = false
game.screen("month", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  game.log("S1 month built")
end)
game.on("newMonthCountry", function(country, fundingChange, satisfaction, formPact, cancelPact, geoscape, month)
  if asked then return end
  asked = true
  local ok, text = pcall(function() game.openScreen("month") end)
  game.log("S1 month asked", tostring(ok), tostring(text))
end)
'''

BRIEF = r'''
local asked = false
game.screen("brief", function(ui)
  ui:window{ x = 32, y = 20, w = 256, h = 160 }
  game.log("S1 brief built")
end)
game.on("createUnit", function(unit, battle, turn)
  if asked then return end
  asked = true
  local ok, text = pcall(function() game.openScreen("brief") end)
  game.log("S1 brief asked", tostring(ok), tostring(text))
end)
'''


def check(what, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + what + (f"  [{detail}]" if detail else ""), flush=True)
    if not ok:
        failed.append(what)


def mod(mods, name, code, caps, rul=""):
    own = mods / name
    (own / "lua").mkdir(parents=True)
    meta = f'id: {name}\nname: "{name}"\nversion: 0.1\nmaster: "piratez"\nluaApi: 2\n{caps}'
    (own / "metadata.yml").write_text(meta, encoding="utf-8", newline="\n")
    (own / "lua/main.lua").write_text(code, encoding="utf-8", newline="\n")
    if rul:
        (own / "Ruleset").mkdir()
        (own / "Ruleset/s1.rul").write_text(rul, encoding="utf-8", newline="\n")


def prepare():
    lua_mod_check.unlink_all(HERE)
    mods = HERE / "mods"
    mods.mkdir(parents=True)
    for d in (GAME / "user/mods").iterdir():
        if d.is_dir():
            lua_mod_check.link_or_copy(d, mods / d.name)
    bank_mod.write(mods)
    caps = "luaCaps: [screens]\n"
    mod(mods, "s1t", T, caps, "extended:\n  tags:\n    GeoscapeGame:\n      S1_T: int\n" + "extraSprites:\n  - type: S1_ICON.PNG\n    singleImage: true\n    files:\n      0: Resources/s1_icon.png\n")
    (mods / "s1t/Resources").mkdir()
    bank_mod.icon(mods / "s1t/Resources/s1_icon.png")
    mod(mods, "s1nocap", NOCAP, "")
    mod(mods, "s1turn", TURN, caps)
    mod(mods, "s1done", DONE, "luaCaps: [screens, spawn]\n")
    mod(mods, "s1month", MONTH, caps)
    mod(mods, "s1brief", BRIEF, caps)
    listed = "".join(f"  - '{m} ver: 0.1'\n" for m in ALL)
    battle = HERE / "with.sav"
    battle.write_text(re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", listed, SAVE.read_text(encoding="utf-8"), count=1), encoding="utf-8", newline="\n")
    text = (GAME / "user/piratez/NoCodexCatZ.sav").read_text(encoding="utf-8")
    geo = HERE / "geo.sav"
    text = re.sub(r"(?m)^ironman: true$", "ironman: false", text)  # в ironman F5 не пишет (R-498)
    geo.write_text(text, encoding="utf-8", newline="\n")
    month = HERE / "month.sav"
    month.write_text(re.sub(r"(?m)^time: \{.*\}$", "time: {second: 10,minute: 50,hour: 23,weekday: 2,day: 31,month: 3,year: 2606}", text, count=1), encoding="utf-8", newline="\n")
    os.environ.pop("OXCE_LUA_API2", None)  # экраны открыты и без заслона
    return lua_mod_check.Bench(EXE, HERE), mods, battle, geo, month


class Stand:
    def __init__(self, ctx, name, save, mod_ids, options="", display="", **env):
        self.bench, self.mods = ctx[0], ctx[1]
        self.name = name
        for k in ("OXCE_HD_FRAMELOG", "OXCE_LUA_API2"):
            os.environ.pop(k, None)
        os.environ.update(env)
        lua_mod_check.unlink_all(self.bench.folder(name))
        on = ";".join(f"{m}={'true' if m in mod_ids else 'false'}" for m in ALL)
        a = ["start", "--name", name, "--exe", EXE, "--save", str(save), "--mods-dir", str(self.mods), "--mods", on,
             "--set", "oxceLuaMods=true" + (";" + options if options else ""), "--timeout", "120"]
        if display:
            a += ["--display", display]
        print(name, (self.bench.call(*a, timeout=140).strip().splitlines() or ["?"])[-1][:90], flush=True)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.bench.call("stop", "--name", self.name, timeout=60)

    def run(self, script, timeout=60):
        out = self.bench.run(self.name, script, timeout)
        bad = [l for l in out.splitlines() if "-> err" in l]
        if bad:
            print("стенд:", bad[:3], flush=True)
        return out

    def top(self):
        return self.bench.state(self.name)[0]

    def info(self):
        return re.search(r"state (\w+) stack=(\S+)(?: side=(\w+))?(?: turn=(\d+))? seed=(\d+)", self.run("state", 30))

    def lines(self, word):
        return [l.strip() for l in self.bench.call("log", "--name", self.name, "-n", "40000", timeout=60).splitlines() if word in l]

    def errors(self):
        path = self.bench.folder(self.name) / "lua_errors.log"
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def p(x, y):
    """Клик по координатам 320×200: кадр мира 480×270, окно по центру."""
    return f"click {x + 80},{y + 35}"


def row(i):
    return p(150, 56 + 8 * i)


OPEN = "key 111; wait 300"
ESC = "key 27; wait 200"


def pause_button(st, x, top):
    """Вид B со страницы выбора: кнопка в правой половине ряда настроек, у окна паузы свой x."""
    st.run(ESC)
    check(f"{top}: открыта пауза", st.top() == "PauseState", st.top())
    st.run(f"{p(x + 154, 131)}; wait 300")
    check(f"{top}: кнопка паузы открывает список экранов", st.top() == "LuaModsState", st.top())
    st.run(f"{ESC}; {ESC}")
    check(f"{top}: Esc возвращает назад", st.top() == top, st.top())


def bank(st, k, top, want):
    """Рецепт: список, банк, вложить, закрыть, закрыть. want — ожидаемый остаток после вложения."""
    st.run(f"set k={k}; wait 300; {OPEN}; {row(0)}; wait 300")
    check(f"{top} k={k}: банк открыт", st.top() == "LuaScreenState", st.top())
    st.run(f"{p(100, 139)}; wait 200")
    deposit = st.lines("S1 deposit")
    check(f"{top} k={k}: вложено", deposit and deposit[-1].endswith(str(want)), deposit[-1][-30:] if deposit else "")
    st.run(f"{p(210, 139)}; wait 200; {p(100, 139)}; wait 200")
    withdraw = st.lines("S1 withdraw")
    check(f"{top} k={k}: забрано и вложено снова", withdraw and withdraw[-1].endswith(str(want - 1000)), withdraw[-1][-30:] if withdraw else "")
    closed = len(st.lines("S1 bank closed"))
    # кнопка самого мода закрывает как Esc
    st.run(f"{p(150, 163)}; wait 200")
    check(f"{top} k={k}: кнопка закрытия", len(st.lines("S1 bank closed")) == closed + 1 and st.top() == "LuaModsState", st.top())
    st.run(ESC)
    check(f"{top} k={k}: вернулись", st.top() == top, st.top())


def quick(st, target):
    for _ in range(4):
        if st.top() in ("GeoscapeState", "BattlescapeState"):
            break
        st.run(ESC)  # время на геоскейпе идёт: окно игры могло прийти само, F5 в него не попадёт
    before = {f: f.stat().st_mtime for f in st.bench.folder(st.name).rglob("*.asav")}
    st.run("key 286; wait 300")
    t0 = time.time()
    while time.time() - t0 < 10:
        now = [f for f in st.bench.folder(st.name).rglob("*.asav") if before.get(f) != f.stat().st_mtime]
        if now:
            time.sleep(0.5)  # файл пишется не мгновенно
            shutil.copyfile(now[0], target)
            return now[0]
        time.sleep(0.3)
    return None


def reach(st, keys, want, tries=5):
    """Окно игры на геоскейпе приходит когда хочет и съедает клавиши: закрыть и нажать снова."""
    for _ in range(tries):
        for _ in range(4):
            if st.top() == "GeoscapeState":
                break
            st.run(ESC)
        st.run(keys, 30)
        if st.top() == want:
            return True
        st.run("wait 800", 30)
    return False


def same_save(a, b):
    """Что различается в двух сейвах: только такт анимации (как в прошлом заходе, §10 № 2)."""
    x = a.read_text(encoding="utf-8", errors="replace").splitlines()
    y = b.read_text(encoding="utf-8", errors="replace").splitlines()
    diff = [l for l in difflib.unified_diff(x, y, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    return [l for l in diff if not re.search(r"animFrame|^.time: \{", l)]


def part_recipe(ctx):
    bench, mods, battle, geo, month = ctx
    with Stand(ctx, "s1rb", battle, ("s1bank",)) as st:
        seed = st.info().group(5)
        a, b = HERE / "b_a.asav", HERE / "b_b.asav"
        check("бой: быстрое сохранение", quick(st, a))
        st.run(f"{OPEN}; {row(0)}; wait 300; {ESC}; {ESC}")
        check("№ 11 бой: открыть и закрыть, сид тот же", st.info().group(5) == seed, st.info().group(5))
        quick(st, b)
        rest = same_save(a, b)
        check("№ 11 бой: сейв тот же", not rest, str(rest[:4]))
        bank(st, 4, "BattlescapeState", 1000)
        bank(st, 1, "BattlescapeState", 2000)
        saved = quick(st, HERE / "b_tag.asav")
        st.run("set k=4; wait 200")
        st.run(f"load {saved.name}; wait 3000", 120)
        st.run(f"{OPEN}; {row(0)}; wait 300; {ESC}; {ESC}")
        built = st.lines("S1 bank built")
        check("бой: остаток в сейве", built and built[-1].endswith("2000"), built[-1][-30:] if built else "")
        check("бой: без ошибок мода", not st.errors(), st.errors()[:200])
        pause_button(st, 52, "BattlescapeState")
    with Stand(ctx, "s1rg", geo, ("s1bank",)) as st:
        # время на геоскейпе идёт само и двигает сид: сверяем, пока он под списком и не думает
        st.run(OPEN)
        seed = st.info().group(5)
        st.run(f"{row(0)}; wait 300; {ESC}")
        check("№ 11 геоскейп: открыть и закрыть, сид тот же", st.info().group(5) == seed, st.info().group(5))
        st.run(ESC)
        bank(st, 4, "GeoscapeState", 1000)
        bank(st, 1, "GeoscapeState", 2000)
        saved = quick(st, HERE / "g_tag.asav")
        check("геоскейп: быстрое сохранение", saved)
        st.run("set k=4; wait 200")
        st.run(f"load {saved.name}; wait 3000", 120)
        check("геоскейп: список после загрузки", reach(st, OPEN, "LuaModsState"), st.top())
        st.run(f"{row(0)}; wait 300; {ESC}; {ESC}")
        built = st.lines("S1 bank built")
        check("геоскейп: остаток в сейве", built and built[-1].endswith("2000"), built[-1][-30:] if built else "")
        check("открыта база", reach(st, "key 98; wait 2500", "BasescapeState"), st.top())
        bank(st, 4, "BasescapeState", 3000)
        bank(st, 1, "BasescapeState", 4000)
        st.run(f"set k=4; wait 200; {ESC}")
        check("геоскейп: без ошибок мода", not st.errors(), st.errors()[:200])


def part_widgets(ctx):
    bench, mods, battle, geo, month = ctx
    with Stand(ctx, "s1w", battle, ("s1bank",)) as st:
        for k in (4, 1):
            st.run(f"set k={k}; wait 300; {OPEN}; {row(1)}; wait 300")
            check(f"k={k}: виджеты открыты", st.top() == "LuaScreenState", st.top())
            st.run("key 97; wait 100")
            check(f"k={k}: onKey", any(l.endswith("S1 key\ta") or l.endswith("S1 key a") for l in st.lines("S1 key")), str(st.lines("S1 key")[-1:]))
            st.run(f"{p(85, 52)}; wait 150")
            check(f"k={k}: toggleButton", st.lines("S1 toggle"), str(st.lines("S1 toggle")[-1:]))
            st.run(f"{p(120, 72)}; wait 200")
            check(f"k={k}: slider", st.lines("S1 slider"), str(st.lines("S1 slider")[-1:]))
            st.run(f"{p(190, 52)}; wait 150")
            rows = st.lines("S1 row")
            check(f"k={k}: строка списка", rows and re.search(r"3\D+3$", rows[-1]), str(rows[-1:]))
            st.run(f"{p(230, 134)}; wait 200; {p(230, 150)}; wait 200")
            check(f"k={k}: comboBox", st.lines("S1 combo"), str(st.lines("S1 combo")[-1:]))
            st.run(f"{p(40, 110)}; wait 150")
            check(f"k={k}: image", st.lines("S1 image"), str(st.lines("S1 image")[-1:]))
            edits = len(st.lines("S1 enter"))
            st.run(f"{p(80, 89)}; wait 100; type x; wait 150; key 13; wait 150")
            check(f"k={k}: edit, onChange и onEnter", st.lines("S1 edit") and len(st.lines("S1 enter")) == edits + 1, str(st.lines("S1 enter")[-1:]))
            st.run(f"{ESC}; {ESC}")
            top = st.top()
            if top != "BattlescapeState":  # Esc снял фокус с edit
                st.run(f"{ESC}; {ESC}")
            check(f"k={k}: вышли", st.top() == "BattlescapeState", st.top())
        check("виджеты: без ошибок мода", not st.errors(), st.errors()[:300])


def part_limits(ctx):
    bench, mods, battle, geo, month = ctx
    with Stand(ctx, "s1l", battle, ("s1t", "s1nocap")) as st:
        nocap = st.lines("S1 nocap screen")
        check("№ 4 game.screen без разрешения: ошибка с именем", nocap and "false" in nocap[-1] and "screens" in nocap[-1], nocap[-1][-110:] if nocap else "")
        seed = st.info().group(5)
        st.run(f"{OPEN}; {row(0)}; wait 300")
        check("построение не пишет", any("false" in l and "only read" in l for l in st.lines("S1 build write")), str(st.lines("S1 build write")[-1:])[-120:])
        check("построение без случайных чисел", any("false" in l and "random" in l for l in st.lines("S1 build random")), str(st.lines("S1 build random")[-1:])[-120:])
        check("построение не открывает экран", any("false" in l for l in st.lines("S1 build open")), str(st.lines("S1 build open")[-1:])[-120:])
        st.run(f"{ESC}")
        check("onClose не пишет", any("false" in l for l in st.lines("S1 close write")), str(st.lines("S1 close write")[-1:])[-120:])
        check("onClose без случайных чисел", any("false" in l for l in st.lines("S1 close random")), str(st.lines("S1 close random")[-1:])[-120:])
        check("onClose не открывает экран", any("false" in l for l in st.lines("S1 close open")), str(st.lines("S1 close open")[-1:])[-120:])
        check("сид тот же после чистого экрана", st.info().group(5) == seed)

        st.run(f"{row(1)}; wait 300")
        check("ошибка построения закрывает экран", st.top() == "LuaModsState" and "S1 build on purpose" in st.errors(), st.top())
        st.run(f"{row(2)}; wait 300; {ESC}")
        check("ошибка в onClose: экран закрыт", st.top() == "LuaModsState" and "S1 close on purpose" in st.errors(), st.top())

        st.run(f"{row(3)}; wait 300")
        for _ in range(4):
            st.run(f"{p(150, 159)}; wait 250")
        nest = st.lines("S1 nest open")
        check("вложенность: четыре экрана, пятый отказ", len(st.lines("S1 nest built")) == 4 and "one on another" in nest[-1], f"{len(st.lines('S1 nest built'))}: {nest[-1][-70:]}")
        st.run("; ".join([ESC] * 4))
        check("вложенные закрыты Esc", st.top() == "LuaModsState", st.top())

        st.run(f"{row(4)}; wait 300")
        for _ in range(7):
            st.run(f"{p(150, 159)}; wait 200")
            if st.top() == "LuaScreenState" and len(st.lines("S1 leaf built")) > 0:
                st.run(ESC) if "true" in st.lines("S1 ceil open")[-1] else None
        ceil = st.lines("S1 ceil open")
        oks = [l for l in ceil if "true" in l]
        # три уже потрачены на вложенность: всего восемь за ход
        check("потолок 8 экранов за ход, число в тексте", len(oks) == 5 and "more than 8 screens in one turn" in ceil[-1], f"{len(oks)}: {ceil[-1][-70:]}")
        st.run(ESC)
        check("после потолка список жив", st.top() == "LuaModsState", st.top())

        st.run(f"{row(5)}; wait 400")
        marks = st.lines("S1 m ")
        wrong = [l[-40:] for l in marks if "\tfalse" in l or " false " in l]
        check("все методы виджетов отвечают верно", len(marks) >= 12 and not wrong, f"{len(marks)}, неверно: {wrong[:4]}")
        for tag, word in (("no field", "bogus"), ("wrong kind", ""), ("no picture", "S1_NONE"), ("cols", ""), ("widgets", "64")):
            got = st.lines("S1 " + tag)
            check(f"отказ: {tag}", got and "false" in got[-1] and word in got[-1], got[-1][-100:] if got else "")
        st.run(f"{ESC}; {row(6)}; wait 300; {p(150, 159)}; wait 200")
        for tag, word in (("dead ui", ""), ("dead widget", ""), ("no screen", "nope")):
            got = st.lines("S1 " + tag)
            check(f"отказ: {tag}", got and "false" in got[-1] and word in got[-1], got[-1][-100:] if got else "")
        st.run(f"{ESC}; {row(7)}; wait 800")
        rows = st.lines("S1 rows")
        check("потолок 2000 строк, число в тексте", rows and "2000" in rows[-1] and "more than 2000 rows" in rows[-1], rows[-1][-80:] if rows else "")
        check("игра жива после всего", st.top() == "LuaScreenState", st.top())
        st.run(f"{ESC}; {ESC}")
        check("вернулись в бой", st.top() == "BattlescapeState", st.top())
    with Stand(ctx, "s1lg", geo, ("s1t",)) as st:
        st.run(f"{OPEN}; {row(4)}; wait 300")
        for _ in range(9):
            st.run(f"{p(150, 159)}; wait 200")
            if "true" in st.lines("S1 ceil open")[-1]:
                st.run(ESC)
        ceil = st.lines("S1 ceil open")
        check("геоскейп: потолок 8 за день", len([l for l in ceil if "true" in l]) == 8 and "more than 8" in ceil[-1], ceil[-1][-70:])
        st.run(f"{ESC}; {ESC}")
        check("геоскейп: вернулись", st.top() == "GeoscapeState", st.top())


def end_turn(st, limit=120):
    """Как Bench.end_turn, только экран мода закрывает Esc. Возвращает, что видел при каждом экране."""
    first = int(st.bench.state(st.name)[2] or 0)
    seen = []
    st.run("key 8", 30)
    t0 = time.time()
    while time.time() - t0 < limit:
        time.sleep(0.7)
        top, side, turn = st.bench.state(st.name)
        if top == "NextTurnState":
            st.run("click 160,100", 30)
        elif top in ("InfoboxOKState", "InfoboxState"):
            st.run("key 13", 30)
        elif top == "LuaScreenState":
            seen.append((side, turn))
            st.run("key 27", 30)
        elif top == "BattlescapeState" and side == "player" and int(turn or 0) > first:
            time.sleep(1)
            if st.top() == "BattlescapeState":
                return seen
        elif not top:
            raise RuntimeError("игра не отвечает")
    raise RuntimeError(f"ход не закончился за {limit} с, экран {top}")


def part_turn(ctx):
    bench, mods, battle, geo, month = ctx
    with Stand(ctx, "s1tu", battle, ("s1turn",)) as st:
        t0 = time.time()
        seen = end_turn(st)
        print(f"ход: {time.time() - t0:.0f} с, экраны: {seen}", flush=True)
        check("№ 12 экран при ходе ИИ построен", st.lines("S1 ai built"), str(st.lines("S1 ai built")[-1:])[-60:])
        check("№ 12 экран при ходе ИИ: сторона не игрока", any(s and s != "player" for s, _ in seen), str(seen[:2]))
        check("№ 12 падение юнита: экран после падения", st.lines("S1 fall asked") and st.lines("S1 fall built"), str(st.lines("S1 fall built")[-1:])[-60:])
        call = st.lines("S1 loop call")
        check("№ 6 сто попыток с pcall: один экран на вызов", call and re.search(r"S1 loop call\s+1\s", call[-1]) and "in one call" in call[-1], call[-1][-70:] if call else "")
        check("№ 6 цикл на 100 000 без pcall: ошибка мода на втором", not st.lines("S1 loop passed") and "in one call" in st.errors(), st.errors()[:160])
        nexts = st.lines("S1 loop next")
        built = st.lines("S1 loop built")
        refused = [l for l in nexts if "false" in l]
        check("№ 6 очередь из обхода не больше четырёх", 1 <= len(built) <= 8 and refused and "one on another" in refused[0], f"построено {len(built)}, {refused[0][-60:] if refused else ''}")
        check("ход продолжается: игра в бою", st.top() == "BattlescapeState", st.top())
        other = [l for l in st.errors().splitlines() if l.strip() and "in one call" not in l and "stack traceback" not in l and not l.startswith(("\t", " "))]
        check("ход: других ошибок мода нет", not other, str(other[:3])[:300])
    with Stand(ctx, "s1do", battle, ("s1done",), OXCE_LUA_API2="1") as st:  # spawn закрыт до этапа 3
        seen = end_turn(st)
        got = st.lines("S1 done battle")
        check("game.getBattle из done", got and "true" in got[-1], got[-1][-40:] if got else "")
        check("game.openScreen из done", st.lines("S1 fromdone built") and seen, str(seen[:1]))
        check("done: ошибок мода нет", not st.errors(), st.errors()[:300])


def part_month(ctx):
    bench, mods, battle, geo, month = ctx
    with Stand(ctx, "s1mo", month, ("s1month",)) as st:
        st.run("key 53; wait 200")
        t0 = time.time()
        order = []
        while time.time() - t0 < 30 and not st.lines("S1 month asked"):
            if st.top() != "GeoscapeState":
                st.run("key 13; wait 300", 30)
            time.sleep(0.5)
        # обработчики геоскейпа пока только читают: запрос экрана из них появится с событиями этапа 2
        asked = st.lines("S1 month asked")
        check("геоскейп: обработчик только для чтения экран не открывает", asked and "false" in asked[-1], asked[-1][-90:] if asked else "нет события")
        check("геоскейп: отказ не сломал месяц", st.top() not in ("", "LuaScreenState"), st.top())


def part_brief(ctx):
    bench, mods, battle, geo, month = ctx
    import defects
    save = defects.geoscape_save(HERE)
    with Stand(ctx, "s1br", save, ("s1brief",)) as st:
        t0 = time.time()
        order = []
        while time.time() - t0 < 60:
            top = st.top()
            if top and (not order or order[-1] != top):
                order.append(top)
            if top == "LuaScreenState":
                break
            if top == "ConfirmLandingState":
                st.run("key 13; wait 1200", 60)
            elif top == "BriefingState":
                time.sleep(1.5)
                shot = st.top()
                check("брифинг держит экран мода под собой", shot == "BriefingState", shot)
                st.run("key 13; wait 800", 60)
            elif top not in ("GeoscapeState", "BattlescapeState", ""):
                st.run("key 27; wait 400", 30)
            time.sleep(0.7)
        print("экраны:", order, f"{time.time() - t0:.0f} с", flush=True)
        asked = st.lines("S1 brief asked")
        print("запрос:", asked[-1][-110:] if asked else "нет", flush=True)
        check("№ 12 экран из подготовки боя открыт после брифинга", st.lines("S1 brief built") and "BriefingState" in order and order.index("BriefingState") < order.index("LuaScreenState") if "LuaScreenState" in order else False, str(order))
        st.run(ESC)
        check("после экрана идёт бой", st.top() in ("BattlescapeState", "InventoryState"), st.top())


def part_rows(ctx):
    bench, mods, battle, geo, month = ctx
    log = HERE / "frames.tsv"
    if log.exists():
        log.unlink()
    with Stand(ctx, "s1pf", battle, ("s1t",), display="2560x1440", OXCE_HD_FRAMELOG=str(log)) as st:
        shot = HERE / "rows2560.png"
        st.run(f"wait 800; shot {shot.as_posix()}", 30)
        from PIL import Image
        size = Image.open(shot).size
        print("кадр", size, flush=True)
        check("№ 13 кадр 2560×1440", size == (2560, 1440), str(size))
        dx, dy = (size[0] // 4 - 320) // 2, (size[1] // 4 - 200) // 2
        st.run(f"wait 2500; {OPEN}", 60)
        t0 = time.time()
        st.run(f"click {150 + dx},{112 + dy}; wait 50", 60)
        opening = time.time() - t0
        print(f"открытие экрана на 2000 строк: {opening:.2f} с", st.top(), flush=True)
        check("№ 13 экран на 2000 строк открылся", st.top() == "LuaScreenState", st.top())
        check("№ 13 открытие не дольше 2 с", opening <= 2, f"{opening:.2f}")
        st.run("wait 2500", 30)
        st.run("; ".join([f"wheel down {160 + dx},{100 + dy}; wait 100"] * 20), 30)
        st.run("wait 500", 30)
        check("№ 13 в журнале нет строк на каждую ячейку", len(st.lines("not found in")) < 50, str(len(st.lines("not found in"))))
    rows = []
    with open(log, encoding="utf-8", errors="replace") as f:
        head = f.readline().rstrip("\n").split("\t")
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == len(head):
                rows.append(dict(zip(head, parts)))
    def stat(state):
        v = sorted(int(r["loop_us"]) / 1000 for r in rows if state in r["state"])
        if not v:
            return None
        return len(v), round(v[len(v) // 2], 2), round(v[int(len(v) * 0.95)], 2), round(v[-1], 1)
    base = stat("BattlescapeState")
    list2000 = stat("LuaScreenState")
    print("кадры (число, p50 мс, p95 мс, худший мс): бой", base, "список", list2000, flush=True)
    check("№ 13 замер есть", base and list2000, f"{size}")
    check("№ 13 без падения кадра: p95 списка не хуже 33 мс", list2000 and list2000[2] <= 33, str(list2000))


PARTS = {"recipe": part_recipe, "widgets": part_widgets, "limits": part_limits, "turn": part_turn, "month": part_month, "brief": part_brief, "rows": part_rows}

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
        print("  FAIL:", f[:120])
    sys.exit(1 if failed else 0)
