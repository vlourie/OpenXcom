# Тестовые Lua-моды пробы, этап 0: два рабочих с одним и тем же lua/main.lua и моды-нарушители.
import os
from pathlib import Path

import subprocess

ROOT = Path(os.environ["TEMP"]) / "oxce_lua_stage1" / "luamods"
REAL = Path("E:/OpenXCom/Пиратки/Dioxine_XPiratez/user/mods")
ROOT.mkdir(parents=True, exist_ok=True)
# настоящие моды установки - соединениями, снимать только rmdir (R-047); ROOT целиком не удалять
for d in REAL.iterdir():
    if d.is_dir() and not (ROOT / d.name).exists():
        subprocess.run(["cmd", "/c", "mklink", "/J", str(ROOT / d.name), str(d)], check=True, capture_output=True)

WORK = """
local seen = 0
game.on("newTurnUnit", function(unit, battle, turn, side)
  seen = seen + 1
  local tag = unit:getTag("LUA_PROBE")
  unit:setTag("LUA_PROBE", tag + 1)
  if seen <= 6 then
    local hp = unit:getHealth()
    unit:addHealth(-1)
    game.log(string.format("%s turn=%d/%d side=%d id=%d faction=%d hp %d->%d of %d tag %d->%d r=%d",
      NAME, turn, battle:getTurn(), side, unit:getId(), unit:getFaction(), hp, unit:getHealth(),
      unit:getHealthMax(), tag, unit:getTag("LUA_PROBE"), math.random(1, 1000)))
  end
end)
game.log(NAME .. " main.lua ok")
"""

MODS = {
    "lua_a": (1, 'local NAME = "A"\n' + WORK),
    "lua_b": (1, 'local NAME = "B"\n' + WORK),
    "lua_loop": (1, """
local n = 0
game.on("newTurnUnit", function(unit)
  n = n + 1
  game.log("loop call " .. n)
  while true do end
end)
"""),
    "lua_syntax": (1, "this is not lua (((\n"),
    "lua_future": (99, 'game.log("MUST NOT RUN: api 99")\n'),
    "lua_nokey": (0, 'game.log("MUST NOT RUN: no luaApi")\n'),
    "lua_escape": (1, """
game.log("escape io=" .. type(io) .. " os=" .. type(os) .. " debug=" .. type(debug) .. " package=" .. type(package)
  .. " require=" .. type(require) .. " dofile=" .. type(dofile) .. " loadfile=" .. type(loadfile)
  .. " coroutine=" .. type(coroutine) .. " collectgarbage=" .. type(collectgarbage))
local ok, err = pcall(function() return getmetatable("").__index end)
game.log("escape string metatable: " .. tostring(ok) .. " " .. tostring(err))
game.on("newTurnUnit", function(unit)
  local ok, err = pcall(function() return unit:getTag("NO_SUCH") end)
  game.log("escape unknown tag read: " .. tostring(ok) .. " " .. tostring(err))
  ok, err = pcall(function() unit:setTag("NO_SUCH", 1) end)
  game.log("escape unknown tag write: " .. tostring(ok) .. " " .. tostring(err))
  ok, err = pcall(function() unit.getHealth(1) end)
  game.log("escape wrong self: " .. tostring(ok) .. " " .. tostring(err))
  error("handler dies on purpose")
end)
"""),
}

for name, (api, code) in MODS.items():
    d = ROOT / name
    (d / "lua").mkdir(parents=True, exist_ok=True)
    (d / "Ruleset").mkdir(exist_ok=True)
    meta = f'name: "{name}"\nversion: 1.0\nauthor: probe\nmaster: piratez\n'
    if api:
        meta += f"luaApi: {api}\n"
    (d / "metadata.yml").write_text(meta, encoding="utf-8", newline="\n")
    (d / "lua" / "main.lua").write_text(code, encoding="utf-8", newline="\n")
    rul = "extended:\n  tags:\n    BattleUnit:\n      LUA_PROBE: int\n"
    (d / "Ruleset" / f"{name}.rul").write_text(rul, encoding="utf-8", newline="\n")
print(ROOT)
print(";".join(f"{n}=true" for n in MODS))
