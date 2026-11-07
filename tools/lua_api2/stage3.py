# API 2, этап 3 в настоящей игре, всё невидимо: создание и снятие, потолки, ИИ, сейв и загрузка, снятие мода.
# Запуск: py -3.13 tools/lua_api2/stage3.py [часть ...]; без аргумента все части. Потолок всего прогона LIMIT.
import os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage1 as s1
from stage1 import ESC, OPEN, Stand, check, failed, p, quick, row, same_save
import lua_mod_check

ROOT = s1.ROOT
HERE = Path(os.environ["TEMP"]) / "oxce_lua_s3t"
ALL = ("s3units", "s3give", "s3remove", "s3order", "s3nocap", "s3api1", "s3turn", "s3save", "s3seed", "s3ai", "s3end", "s3start", "s3heavy")
LIMIT = 480
started = time.time()

COMMON = r'''
local ITEM, FOE, BIG = "STR_ELECTRO_FLARE", "STR_MUTON_SOLDIER", "STR_TAMED_REAPER"
local function say(tag, ...) game.log("S3 " .. tag, ...) end
local function report(tag, f, ...)
  local ok, text = pcall(f, ...)
  game.log("S3 " .. tag, tostring(ok), tostring(text))
end
local function alive(b, side)
  local out = {}
  for _, u in ipairs(b:getUnits()) do
    if u:getFaction() == side and u:getHealth() > 0 and u:getStun() < u:getHealth() then out[#out + 1] = u end
  end
  return out
end
local function soldier(b, n) return alive(b, game.FACTION_PLAYER)[n or 1] end
-- открытое место: на складе и в корабле солдаты стоят плотно, вокруг них нет ни клетки
local function clear(b)
  local sx, sy = b:getSize()
  for x = 2, sx - 3 do
    for y = 2, sy - 3 do
      local free = true
      for dx = -1, 1 do
        for dy = -1, 1 do
          local t = b:getTile(x + dx, y + dy, 0)
          if not t or t:getUnit() then free = false end
        end
      end
      if free then return x, y, 0 end
    end
  end
  error("no clear place")
end
local function numbers(b) return #b:getUnits() .. " " .. #b:getItems() end
local function unitDone(tag, more)
  return function(unit, why)
    if unit then
      local x, y, z = unit:getPosition()
      say("unit " .. tag, unit:getId(), unit:getFaction(), unit:getTimeUnits(), x, y, z, unit:getType())
      if more then more(unit) end
    else
      say("unit " .. tag, "nil", why)
    end
  end
end
local function itemDone(tag)
  return function(item, why)
    if item == true then say("item " .. tag, "removed")
    elseif item then say("item " .. tag, item:getRuleItem():getType(), tostring(item:getOwner() ~= nil))
    else say("item " .. tag, "nil", why) end
  end
end
local function steps(list)
  local n = 0
  game.screen("lab", function(ui)
    ui:window{ x = 32, y = 20, w = 256, h = 160 }
    local b = game.getBattle()
    if b then report("build spawn", function() b:spawnItem(ITEM, 0, 0, 0) end) end
    ui:button{ x = 50, y = 50, w = 220, h = 18, text = "go", onClick = function()
      n = n + 1
      say("step", n)
      list[n](game.getBattle())
    end }
  end, { menu = "inbattle" })
end
'''

UNITS = COMMON + r'''
local rx, ry, rz
local function room(b)
  if not rx then rx, ry, rz = clear(b) end
  local x, y, z = rx, ry, rz
  for i = 1, 4 do b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL, done = unitDone("room") } end
end
steps{
  function(b)
    local x, y, z = clear(b)
    say("before", numbers(b))
    b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_HOSTILE, done = unitDone("enemy", function(u)
      u:setTimeUnits(7)
      say("enemy tu", u:getTimeUnits())
    end) }
    b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_PLAYER, direction = 3, done = unitDone("own") }
    b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL, done = unitDone("neutral") }
    b:spawnUnit{ type = FOE, x = x, y = y, z = z, done = unitDone("default") }
    say("not yet", numbers(b))
    report("fifth", b.spawnUnit, b, { type = FOE, x = x, y = y, z = z })
    report("no type", b.spawnUnit, b, { x = x, y = y, z = z })
    report("soldier", b.spawnUnit, b, { type = "STR_SOLDIER", x = x, y = y, z = z })
    report("x past", b.spawnUnit, b, { type = FOE, x = 1000, y = y, z = z })
    report("faction past", b.spawnUnit, b, { type = FOE, x = x, y = y, z = z, faction = 9 })
    report("direction past", b.spawnUnit, b, { type = FOE, x = x, y = y, z = z, direction = 9 })
    report("no item", b.spawnItem, b, "S3_NOPE", x, y, z)
    report("give no item", soldier(b).giveItem, soldier(b), "S3_NOPE")
    report("remove text", b.removeItem, b, "x")
  end,
  function(b) say("placed", numbers(b)) room(b) end,
  room,
  room,
  function(b)
    report("turn ceiling", b.spawnUnit, b, { type = FOE, x = 1, y = 1, z = 0 })
    say("after room", numbers(b))
  end,
  function(b)
    local x, y, z = clear(b)
    local sx, sy, sz = b:getSize()
    say("size", sx, sy, sz, x, y, z)
    b:spawnUnit{ type = BIG, x = x, y = y, z = z, faction = game.FACTION_PLAYER, done = unitDone("big", function(u)
      say("big has", #u:getInventoryItems(), tostring(u:getRightHandWeapon() ~= nil or u:getLeftHandWeapon() ~= nil))
    end) }
    b:spawnUnit{ type = BIG, x = sx - 1, y = sy - 1, z = 0, faction = game.FACTION_NEUTRAL, done = unitDone("corner") }
    b:spawnUnit{ type = FOE, x = x, y = y, z = sz - 1, faction = game.FACTION_NEUTRAL, done = unitDone("air") }
    b:spawnItem(ITEM, x, y, sz - 1, itemDone("air"))
  end,
  function(b)
    for _, u in ipairs(b:getUnits()) do
      local x, y, z = u:getPosition()
      if z > 2 then say("high", u:getId(), z) end
    end
    local list = b:getUnits()
    local x, y, z = list[#list]:getPosition()
    say("last unit", list[#list]:getType(), x, y, z)
  end,
}
'''

GIVE = COMMON + r'''
steps{
  function(b)
    for i = 3, 14 do
      local t = soldier(b, i)
      if t then t:giveItem("S3_ITEM", itemDone("try")) end
    end
    local a = soldier(b)
    say("give id", a:getId(), #a:getInventoryItems())
    local foe = alive(b, game.FACTION_HOSTILE)[1]
    local fid = foe:getId()
    foe:giveItem("S3_ITEM", function(item, why)
      say("foe got", item and tostring(item:getOwner():getId() == fid) or "nil", tostring(why))
    end)
    foe:giveItem("S3_ITEM", itemDone("foe second"))
    local c = soldier(b, 2)
    for i = 1, 3 do c:giveItem("S3_HEAVY", itemDone("heavy")) end
    local victim = alive(b, game.FACTION_HOSTILE)[2]
    say("victim", victim:getId())
    victim:setHealth(0)
  end,
  function(b)
    local list = {}
    for i = 3, 14 do
      local t = soldier(b, i)
      if t then
        local n = 0
        for _, item in ipairs(t:getInventoryItems()) do
          if item:getRuleItem():getType() == "S3_ITEM" then n = n + 1 end
        end
        list[#list + 1] = n
        if n == 1 then t:giveItem("S3_ITEM", itemDone("two")) end
      end
    end
    say("holders", table.concat(list, " "))
    -- юнит с нулём здоровья: потери считаются в конце хода, выдача до них не должна ломать
    local foe = alive(b, game.FACTION_HOSTILE)[1]
    foe:setHealth(0)
    foe:giveItem("S3_ITEM", itemDone("zero health"))
  end,
}
'''

REMOVE = COMMON + r'''
local weapon_id, stunned
steps{
  function(b)
    say("before", numbers(b))
    local ground
    for _, item in ipairs(b:getItems()) do
      if not item:getOwner() and not item:getBattleUnit() and not item:isAmmo() and not item:isSpecialWeapon() then ground = item break end
    end
    local gid = ground:getId()
    b:removeItem(ground, itemDone("ground"))
    b:removeItem(ground, itemDone("ground twice"))
    local hand, full
    for i = 1, 30 do
      local u = soldier(b, i)
      if not u then break end
      local w = u:getRightHandWeapon() or u:getLeftHandWeapon()
      if w and w:getAmmoForSlot(0) and w:getAmmoForSlot(0):getId() ~= w:getId() then
        if not hand then hand = w
        elseif not full then full = w break end
      end
    end
    say("hand", hand and hand:getId() or "none", full and full:getId() or "none")
    local w = hand
    say("hand has", w:getRuleItem():getType(), w:getAmmoForSlot(0):getRuleItem():getType())
    b:removeItem(w, itemDone("in hand"))
    weapon_id = full:getId()
    b:removeItem(full:getAmmoForSlot(0), itemDone("magazine"))
    local foe = alive(b, game.FACTION_HOSTILE)[1]
    stunned = foe:getId()
    foe:setStun(1000)
    local a = soldier(b)
    report("remove then read", function() return ground:getId() == gid end)
  end,
  function(b)
    say("after", numbers(b))
    for _, item in ipairs(b:getItems()) do
      if item:getId() == weapon_id then
        say("weapon empty", tostring(item:getAmmoForSlot(0) == nil), item:getRuleItem():getType())
      end
    end
    for _, item in ipairs(b:getItems()) do
      if item:getBattleUnit() then
        say("body of", item:getBattleUnit():getId(), stunned)
        b:removeItem(item, itemDone("body"))
        break
      end
    end
    local special
    for _, item in ipairs(b:getItems()) do
      if item:isSpecialWeapon() then special = item break end
    end
    say("special", special and special:getRuleItem():getType() or "none")
    if special then b:removeItem(special, itemDone("special")) end
  end,
}
'''

ORDER = COMMON + r'''
local seq = 0
local function next_(tag)
  return function(x, why)
    seq = seq + 1
    say("order", seq, tag, tostring(x ~= nil), tostring(why))
  end
end
steps{
  function(b)
    local x, y, z = clear(b)
    b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL, done = next_("u1") }
    b:spawnItem(ITEM, x, y, z, next_("i1"))
    soldier(b):giveItem(ITEM, next_("g1"))
    b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL, done = next_("u2") }
    b:spawnItem(ITEM, x, y, z, next_("i2"))
    b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL, done = next_("u3") }
    b:spawnItem(ITEM, x, y, z, next_("i3"))
  end,
  function(b)
    say("before", numbers(b))
    local x, y, z = soldier(b):getPosition()
    b:spawnItem(ITEM, x, y, z, function(item)
      local bb = game.getBattle()
      say("in done", numbers(bb))
      bb:spawnItem(ITEM, x, y, z, itemDone("from failed done"))
      error("S3 boom")
    end)
    b:spawnItem(ITEM, x, y, z, itemDone("next to failed"))
  end,
  function(b) say("after", numbers(b)) end,
}
'''

NOCAP = COMMON + r'''
game.on("newTurnUnit", function(unit, battle, turn, side)
  if said then return end
  said = true
  local x, y, z = unit:getPosition()
  report("nocap spawnItem", function() battle:spawnItem(ITEM, x, y, z) end)
  report("nocap spawnUnit", function() battle:spawnUnit{ type = FOE, x = x, y = y, z = z } end)
  report("nocap giveItem", function() unit:giveItem(ITEM) end)
  report("nocap removeItem", function() battle:removeItem(battle:getItems()[1]) end)
end)
'''.replace("if said then return end\n  said = true", "if done_ then return end\n  done_ = true").replace("game.on(", "local done_\ngame.on(", 1)

API1 = r'''
local said
game.on("newTurnUnit", function(unit, battle, turn, side)
  if said then return end
  said = true
  game.log("S3 api1", tostring(battle.spawnItem), tostring(battle.spawnUnit), tostring(battle.removeItem), tostring(unit.giveItem))
end)
'''

TURN = COMMON + r'''
local step, last, inTurn = 0, nil, 0
local units, items, msgU, msgI = 0, 0, nil, nil
local chain = false
local function foeTile(b)
  return alive(b, game.FACTION_HOSTILE)[1]:getPosition()
end
game.on("createUnit", function(unit, battle, turn)
  if chain then
    local x, y, z = unit:getPosition()
    local ok, text = pcall(function() battle:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL } end)
    say("chain", tostring(ok), tostring(text))
  end
end)
game.on("newTurnUnit", function(unit, battle, turn, side)
  if side ~= game.FACTION_PLAYER then return end
  if turn ~= last then
    last, inTurn = turn, 0
    step = step + 1
    chain = false
    say("step", step, "turn", turn, numbers(battle))
  end
  inTurn = inTurn + 1
  local x, y, z = foeTile(battle)
  if step == 1 then
    local ok, text = pcall(function() battle:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL } end)
    if ok then units = units + 1 elseif not msgU then msgU = text say("walk units", units, text) end
    local ok2, text2 = pcall(function() battle:spawnItem(ITEM, x, y, z) end)
    if ok2 then items = items + 1 elseif not msgI then msgI = text2 say("walk items", items, text2) end
  elseif step == 2 and inTurn == 1 then
    say("walk result", units, items, numbers(battle))
    for i = 1, 100000 do battle:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL } end
  elseif step == 2 and inTurn == 2 then
    for i = 1, 100000 do battle:spawnItem(ITEM, x, y, z) end
  elseif step == 2 and inTurn == 3 then
    battle:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL, done = unitDone("dropped") }
    battle:spawnItem(ITEM, x, y, z, itemDone("dropped"))
    error("S3 on purpose")
  elseif step == 2 and inTurn == 4 then
    battle:spawnItem(ITEM, x, y, z, itemDone("after error"))
  elseif step == 3 and inTurn == 1 then
    say("no leftovers", numbers(battle))
    chain = true
    battle:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL, done = unitDone("chain first") }
  elseif step == 4 and inTurn == 1 then
    say("after chain", numbers(battle))
  end
end)
game.on("newTurnItem", function(item, battle, turn, side)
  if side ~= game.FACTION_PLAYER or step ~= 1 or msgI then return end
  local x, y, z = foeTile(battle)
  local ok2, text2 = pcall(function() battle:spawnItem(ITEM, x, y, z) end)
  if ok2 then items = items + 1 else msgI = text2 say("walk items", items, text2) end
end)
'''

SAVE = COMMON + r'''
local last, inTurn, had = nil, 0, 0
game.on("newTurnUnit", function(unit, battle, turn, side)
  if side ~= game.FACTION_PLAYER then return end
  if turn ~= last then
    last, inTurn = turn, 0
    had = 0
    say("step", "turn", turn, numbers(battle))
    for _, u in ipairs(battle:getUnits()) do
      local x, y, z = u:getPosition()
      if u:getType() == "S3_UNIT" then
        had = had + 1
        say("mine", u:getId(), x, y, z, u:getFaction(), u:getTimeUnits(), #u:getInventoryItems())
      end
    end
  end
  inTurn = inTurn + 1
  if had == 0 and inTurn == 1 then
    local x, y, z = clear(battle)
    local sx, sy, sz = battle:getSize()
    battle:spawnUnit{ type = "S3_UNIT", x = x, y = y, z = z, faction = game.FACTION_NEUTRAL, done = unitDone("first", function(u) u:setTimeUnits(7) end) }
    battle:spawnUnit{ type = "S3_UNIT", x = x, y = y, z = z, faction = game.FACTION_PLAYER, done = unitDone("own") }
    battle:spawnUnit{ type = "S3_UNIT", x = x + 5, y = y, z = sz - 1, faction = game.FACTION_PLAYER, done = unitDone("air") }
    battle:spawnItem("S3_ITEM", x, y, z, itemDone("ground"))
    say("autosave has", numbers(battle))
  elseif had == 0 and inTurn >= 3 and inTurn <= 14 then
    unit:giveItem("S3_ITEM", itemDone("given"))
  elseif had > 0 and inTurn == 1 then
    for _, u in ipairs(battle:getUnits()) do
      if u:getType() == "S3_UNIT" then u:giveItem("STR_ELECTRO_FLARE", itemDone("to mine")) end
    end
  end
end)
'''

SEED = COMMON + r'''
local last
game.on("newTurnUnit", function(unit, battle, turn, side)
  if side ~= game.FACTION_PLAYER or turn == last then return end
  last = turn
  local x, y, z = alive(battle, game.FACTION_HOSTILE)[1]:getPosition()
  for i = 1, 4 do
    battle:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL, done = unitDone("seed") }
  end
  battle:spawnItem(ITEM, x, y, z, itemDone("seed"))
end)
'''

AI = COMMON + r'''
local foes, gone, skipped = 0, 0, 0
local chainUp = false
local function nextOne(battle)
  for _, u in ipairs(alive(battle, game.FACTION_HOSTILE)) do
    for _, item in ipairs(u:getInventoryItems()) do
      if not item:isSpecialWeapon() then
        battle:removeItem(item, function(ok, why)
          if ok then gone = gone + 1 else skipped = skipped + 1 end
          local b = game.getBattle()
          if b:getTurnSide() == game.FACTION_HOSTILE then nextOne(b) else chainUp = false end
        end)
        return true
      end
    end
  end
  chainUp = false
  return false
end
local asked, reads
game.on("aiCalculateTargetWeight", function(unit, target, battle, out)
  if not reads then
    reads = true
    report("ai read only", function() battle:spawnItem(ITEM, 0, 0, 0) end)
  end
end)
game.on("newTurnUnit", function(unit, battle, turn, side)
  if side ~= game.FACTION_HOSTILE then return end
  if turn ~= asked then
    asked = turn
    say("ai turn", turn, gone, skipped, #alive(battle, game.FACTION_HOSTILE))
    local x, y, z = clear(battle)
    battle:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_HOSTILE, done = unitDone("ai new", function(u)
      u:setTimeUnits(30)
    end) }
    unit:giveItem(ITEM, itemDone("ai got"))
    chainUp = true
    nextOne(battle)
  end
end)
'''

END = COMMON + r'''
local spawned = false
game.on("newTurnUnit", function(unit, battle, turn, side)
  if spawned and side == game.FACTION_HOSTILE then
    say("foe turn", turn, #alive(battle, game.FACTION_HOSTILE))
  end
  if not spawned and side == game.FACTION_PLAYER then
    spawned = true
    local x, y, z = unit:getPosition()
    battle:spawnItem(ITEM, x, y, z, itemDone("queued at the end"))
  end
end)
game.on("battleEnd", function(battle, aborted)
  say("finish", aborted)
  report("end spawn", function() battle:spawnItem(ITEM, 0, 0, 0) end)
  report("end remove", function() battle:removeItem(battle:getItems()[1]) end)
end)
steps{
  function(b)
    local x, y, z = clear(b)
    b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_PLAYER, done = unitDone("own") }
  end,
  function(b)
    for _, u in ipairs(alive(b, game.FACTION_HOSTILE)) do u:setHealth(0) end
    say("all dead", #alive(b, game.FACTION_HOSTILE))
    local x, y, z = clear(b)
    b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_HOSTILE, done = unitDone("last foe") }
  end,
  function(b)
    say("still", #alive(b, game.FACTION_HOSTILE), b:getTurn())
    spawned = false
    for _, u in ipairs(alive(b, game.FACTION_HOSTILE)) do u:setHealth(0) end
  end,
}
'''

START = COMMON + r'''
local started
game.on("battleStart", function(battle)
  started = true
  local u = soldier(battle)
  say("start soldier", tostring(u ~= nil))
  local x, y, z = clear(battle)
  say("start numbers", numbers(battle))
  battle:spawnItem(ITEM, x, y, z, itemDone("first"))
  battle:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_PLAYER, done = unitDone("start") }
  for i = 1, 6 do
    local t = soldier(battle, i)
    if t then t:giveItem("S3_ITEM", itemDone("given")) end
  end
  local q = 0
  for _, base in ipairs(game.getBases()) do q = q + base:getQuarters().used end
  say("quarters before", q)
  report("start write", function() u:setTimeUnits(1) end)
  report("start screen", function() game.openScreen("lab") end)
  report("start tag", function() game.getGeoscape():addFunds(1) end)
  say("start end", numbers(battle))
end)
game.on("battleEnd", function(battle, aborted)
  say("finish", aborted, #battle:getUnits())
  report("end spawn", function() battle:spawnItem(ITEM, 0, 0, 0) end)
end)
game.on("newHour", function(geo)
  local q = 0
  for _, base in ipairs(game.getBases()) do q = q + base:getQuarters().used end
  say("quarters after", q)
end)
local function chain(b)
  local x, y, z = clear(b)
  b:spawnItem(ITEM, x, y, z, function(item)
    say("chain")
    chain(game.getBattle())
  end)
end
steps{ chain }
'''

HEAVY = COMMON + r'''
steps{
  function(b)
    local x, y, z = alive(b, game.FACTION_HOSTILE)[1]:getPosition()
    for i = 1, 4 do b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL } end
  end,
  function(b)
    local x, y, z = alive(b, game.FACTION_HOSTILE)[2]:getPosition()
    for i = 1, 4 do b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL } end
  end,
  function(b)
    local x, y, z = alive(b, game.FACTION_HOSTILE)[3]:getPosition()
    for i = 1, 4 do b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL } end
  end,
  function(b)
    local x, y, z = alive(b, game.FACTION_HOSTILE)[4]:getPosition()
    for i = 1, 4 do b:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL } end
  end,
}
'''

UFO = r'''
local ITEM, FOE = "STR_GRENADE", "STR_SECTOID_SOLDIER"
local last, n = nil, 0
game.on("battleStart", function(battle)
  local list = battle:getUnits()
  local x, y, z = list[1]:getPosition()
  battle:spawnItem(ITEM, x, y, z, function(item) game.log("S3 ufo start item", item ~= nil) end)
end)
game.on("newTurnUnit", function(unit, battle, turn, side)
  if turn == last then return end
  last = turn
  n = n + 1
  local x, y, z = unit:getPosition()
  battle:spawnUnit{ type = FOE, x = x, y = y, z = z, faction = game.FACTION_NEUTRAL, done = function(u, why)
    game.log("S3 ufo unit", u ~= nil, tostring(why), u and u:getType() or "")
  end }
  unit:giveItem(ITEM, function(item, why) game.log("S3 ufo give", item ~= nil, tostring(why)) end)
  battle:removeItem(battle:getItems()[1], function(ok, why) game.log("S3 ufo remove", tostring(ok), tostring(why)) end)
end)
'''

RUL = """units:
  - type: S3_UNIT
    race: STR_MUTON
    rank: STR_LIVE_SOLDIER
    armor: MUTON_ARMOR0
    standHeight: 21
    kneelHeight: 21
    stats:
      tu: 50
      stamina: 100
      health: 40
      bravery: 80
      reactions: 50
      firing: 50
      throwing: 50
      strength: 40
      psiStrength: 0
      psiSkill: 0
      melee: 50
    intelligence: 2
    aggression: 2
    energyRecharge: 40
    value: 1
items:
  - type: S3_ITEM
    size: 0.1
    weight: 1
    invWidth: 1
    invHeight: 1
    bigSprite: 1
    floorSprite: 1
  - type: S3_HEAVY
    size: 0.1
    weight: 900
    invWidth: 1
    invHeight: 1
    bigSprite: 1
    floorSprite: 1
"""


def said(st, word):
    """Хвост строки журнала после тега: то, что сказал мод."""
    out = []
    word = "S3 " + word
    for line in st.lines(word):
        out.append(line[line.index(word) + len(word):].strip())
    return out


def last(st, word):
    got = said(st, word)
    return got[-1] if got else ""


def want(st, word, ok, *parts):
    text = last(st, word)
    good = bool(text) and text.startswith(ok) and all(x in text for x in parts)
    check(f"{word}: {ok} {' '.join(parts)}", good, text[:150])


def step(st, settle=900):
    """Кнопка экрана мода; очередь идёт, только когда окна закрыты."""
    st.run(f"{OPEN}; {row(0)}; wait 200; {p(150, 59)}; wait 200; {ESC}; {ESC}; wait {settle}", 60)
    if st.top() != "BattlescapeState":
        print("после кнопки экран", st.top(), flush=True)


def prepare():
    s1.HERE = HERE
    s1.ALL = ALL
    lua_mod_check.unlink_all(HERE)
    mods = HERE / "mods"
    mods.mkdir(parents=True)
    for d in (s1.GAME / "user/mods").iterdir():
        if d.is_dir():
            lua_mod_check.link_or_copy(d, mods / d.name)
    cap = "luaCaps: [screens, spawn]\n"
    s1.mod(mods, "s3units", UNITS, cap)
    s1.mod(mods, "s3give", GIVE, cap, RUL)
    s1.mod(mods, "s3remove", REMOVE, cap)
    s1.mod(mods, "s3order", ORDER, cap)
    s1.mod(mods, "s3nocap", NOCAP, "luaCaps: [screens]\n")
    own = mods / "s3api1"
    (own / "lua").mkdir(parents=True)
    (own / "metadata.yml").write_text('id: s3api1\nname: "s3api1"\nversion: 0.1\nmaster: "piratez"\nluaApi: 1\n', encoding="utf-8", newline="\n")
    (own / "lua/main.lua").write_text(API1, encoding="utf-8", newline="\n")
    s1.mod(mods, "s3turn", TURN, cap)
    s1.mod(mods, "s3save", SAVE, cap, RUL)
    s1.mod(mods, "s3seed", SEED, cap)
    s1.mod(mods, "s3ai", AI, cap)
    s1.mod(mods, "s3end", END, cap)
    s1.mod(mods, "s3start", START, cap, RUL)
    s1.mod(mods, "s3heavy", HEAVY, cap)
    listed = "".join(f"  - '{m} ver: 0.1'\n" for m in ALL)
    battle = HERE / "with.sav"
    text = s1.SAVE.read_text(encoding="utf-8")
    battle.write_text(re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", listed, text, count=1), encoding="utf-8", newline="\n")
    return lua_mod_check.Bench(s1.EXE, HERE), mods, battle


def part_units(ctx):
    bench, mods, battle = ctx
    with Stand(ctx, "s3a", battle, ("s3units",)) as st:
        st.run("wait 500")
        step(st, 1200)
        want(st, "build spawn", "false", "only read")
        before = last(st, "before")
        check("до такта ничего нет", last(st, "not yet") == before, f"{before} -> {last(st, 'not yet')}")
        for tag, side in (("enemy", "1"), ("own", "0"), ("neutral", "2"), ("default", "1")):
            text = last(st, "unit " + tag)
            f = text.split()
            check(f"юнит {tag}: фракция {side}, TU 0", len(f) >= 7 and f[1] == side and f[2] == "0" and f[6] == "STR_MUTON_SOLDIER", text)
        check("в done можно дать TU", last(st, "enemy tu") == "7", last(st, "enemy tu"))
        want(st, "fifth", "false", "more than 4", "one call")
        want(st, "no type", "false", "type")
        want(st, "soldier", "false", "soldier cannot be made")
        want(st, "x past", "false")
        want(st, "faction past", "false")
        want(st, "direction past", "false")
        want(st, "no item", "false", "S3_NOPE")
        want(st, "give no item", "false", "S3_NOPE")
        want(st, "remove text", "false")
        for _ in range(3):
            step(st, 1200)
        check("новых юнитов четыре", int(last(st, "placed").split()[0]) == int(before.split()[0]) + 4, last(st, "placed"))
        room = said(st, "unit room")
        refused = [x for x in room if x.startswith("nil")]
        print("места:", len(room), "из них отказов", len(refused), flush=True)
        check("вокруг клетки места кончаются: done(nil, причина)", len(room) == 12 and refused and "no room for the unit" in refused[0], str(refused[:1]))
        step(st)
        want(st, "turn ceiling", "false", "16", "one turn")
        check("игра жива", st.top() == "BattlescapeState", st.top())
        bench.end_turn("s3a", 150)
        print("ход с юнитами:", st.info().group(0)[:80], flush=True)
        step(st, 2000)
        big = last(st, "unit big")
        print("большой:", big, "|", last(st, "big has"), "| угол:", last(st, "unit corner"), "| воздух:", last(st, "unit air"), last(st, "item air"), flush=True)
        check("большой юнит с оружием", big.startswith(tuple("0123456789")) and "true" in last(st, "big has"), big)
        step(st, 2500)
        print("наверху:", said(st, "high"), "последний:", last(st, "last unit"), flush=True)
        check("без ошибок мода", not st.errors(), st.errors()[:300])
        check("игра жива в конце", st.top() == "BattlescapeState", st.top())


def part_give(ctx):
    bench, mods, battle = ctx
    with Stand(ctx, "s3b", battle, ("s3give",)) as st:
        st.run("wait 500")
        step(st, 1000)
        print("выдача:", said(st, "item try"), last(st, "foe got"), last(st, "item foe second"), flush=True)
        heavy = said(st, "item heavy")
        print("тяжёлое:", len(heavy), heavy[0][:60] if heavy else "", heavy[-1][:80] if heavy else "", flush=True)
        check("солдату выдано", any(x.startswith("S3_ITEM true") for x in said(st, "item try")), str(said(st, "item try")[:3]))
        check("чужому выдано", last(st, "foe got").startswith("true"), last(st, "foe got"))
        check("чужому и второй", last(st, "item foe second").startswith("S3_ITEM true"), last(st, "item foe second"))
        check("тяжёлое солдату: отказ с причиной", any(x.startswith("nil the unit does not take it") for x in heavy), str(heavy[-1:]))
        bench.end_turn("s3b", 150)
        step(st, 800)
        print("держат:", last(st, "holders"), "| второй:", said(st, "item two")[:2], "| ноль здоровья:", last(st, "item zero health"), flush=True)
        check("второй такой же: отказ", said(st, "item two") and said(st, "item two")[0].startswith("nil the unit does not take it"), str(said(st, "item two")[:1]))
        check("без ошибок мода", not st.errors(), st.errors()[:300])
        check("игра жива", st.top() == "BattlescapeState", st.top())


def part_remove(ctx):
    bench, mods, battle = ctx
    with Stand(ctx, "s3c", battle, ("s3remove",)) as st:
        st.run("wait 500")
        step(st, 1000)
        before, after = last(st, "before"), None
        print("рука:", last(st, "hand"), last(st, "hand has"), flush=True)
        check("снятие с земли", said(st, "item ground")[0] == "removed", said(st, "item ground")[0])
        check("второе снятие того же: причина", last(st, "item ground twice").startswith("nil the item is gone"), last(st, "item ground twice"))
        check("снятие из руки", last(st, "item in hand") == "removed", last(st, "item in hand"))
        check("снятие магазина", last(st, "item magazine") == "removed", last(st, "item magazine"))
        print("чтение снятого:", last(st, "remove then read"), flush=True)
        st.run("wait 200")
        path = quick(st, HERE / "removed0.asav")
        bench.end_turn("s3c", 150)
        step(st, 800)
        after = last(st, "after")
        print("счёт:", before, "->", after, flush=True)
        # оружие из руки ушло с магазином, с земли один, магазин один
        check("предмет, оружие с магазином и магазин ушли", int(before.split()[1]) - int(after.split()[1]) == 3, f"{before} -> {after}: четыре минус, тело оглушённого плюс")
        check("оружие осталось пустым", last(st, "weapon empty").startswith("true"), last(st, "weapon empty"))
        check("тело не снимается", last(st, "item body").startswith("nil a body stays"), last(st, "item body"))
        print("специальное:", last(st, "special"), last(st, "item special"), flush=True)
        if last(st, "special") != "none":
            check("специальное оружие не снимается", last(st, "item special").startswith("nil a unit's special weapon stays"), last(st, "item special"))
        check("без ошибок мода", not st.errors(), st.errors()[:300])
        path = quick(st, HERE / "removed.asav")
        check("сохранение после снятия", path is not None)
        name = path.name
        shown = st.run(f"load {name}; wait 3000; state", 120)
        check("загрузка после снятия", st.top() == "BattlescapeState", shown.strip()[-100:])
        bench.end_turn("s3c", 150)
        check("ход после снятия", st.top() == "BattlescapeState", st.top())


def part_order(ctx):
    bench, mods, battle = ctx
    with Stand(ctx, "s3d", battle, ("s3order",)) as st:
        st.run("wait 500")
        step(st, 1000)
        order = [x.split()[1] for x in said(st, "order")]
        check("порядок запросов сохранён", order == ["u1", "i1", "g1", "u2", "i2", "u3", "i3"], str(order))
        step(st, 800)
        print("ошибка в done:", last(st, "before"), last(st, "in done"), last(st, "after"), flush=True)
        check("ошибка в done в журнале мода", "S3 boom" in st.errors(), st.errors()[:200])
        check("поставленное упавшим done снято", not said(st, "item from failed done"), str(said(st, "item from failed done")))
        check("соседний запрос выполнен", last(st, "item next to failed").startswith("STR_ELECTRO_FLARE"), last(st, "item next to failed"))
        step(st, 500)
        check("игра жива", st.top() == "BattlescapeState", st.top())


def part_caps(ctx):
    bench, mods, battle = ctx
    with Stand(ctx, "s3e", battle, ("s3nocap", "s3api1")) as st:
        bench.end_turn("s3e", 150)
        for name in ("spawnItem", "spawnUnit", "giveItem", "removeItem"):
            want(st, "nocap " + name, "false", "'spawn'")
        check("№ 3 luaApi: 1 не видит методов", last(st, "api1").startswith("nil nil nil nil"), last(st, "api1"))


def part_turn(ctx):
    bench, mods, battle = ctx
    with Stand(ctx, "s3f", battle, ("s3turn",)) as st:
        t0 = time.time()
        bench.end_turn("s3f", 150)
        print(f"ход 1: {time.time() - t0:.0f} с", flush=True)
        print("обход:", last(st, "walk units"), "|", last(st, "walk items"), flush=True)
        check("№ 5 потолок юнитов на ход", last(st, "walk units").startswith("16 ") and "16" in last(st, "walk units").split(" ", 1)[1], last(st, "walk units"))
        items = last(st, "walk items")
        check("№ 5 потолок предметов на ход", items.startswith("256 ") and "256" in items.split(" ", 1)[1], items)
        check("игра жива после обхода", st.top() == "BattlescapeState", st.top())
        t0 = time.time()
        bench.end_turn("s3f", 150)
        print(f"ход 2: {time.time() - t0:.0f} с", flush=True)
        print("итог обхода:", last(st, "walk result"), last(st, "step"), flush=True)
        errors = st.errors()
        check("№ 6 цикл юнитов: ошибка потолка вызова", "more than 4 units in one call" in errors, errors[:300])
        check("№ 6 цикл предметов: ошибка потолка вызова", "more than 32 items in one call" in errors, errors[:300])
        check("ошибка обработчика в журнале", "S3 on purpose" in errors)
        check("снятые ошибкой не выполнены", not said(st, "unit dropped") and not said(st, "item dropped"), str(said(st, "unit dropped")))
        check("следующий обработчик работает", last(st, "item after error").startswith("STR_ELECTRO_FLARE"), last(st, "item after error"))
        t0 = time.time()
        bench.end_turn("s3f", 150)
        print(f"ход 3: {time.time() - t0:.0f} с", last(st, "no leftovers"), flush=True)
        for _ in range(20):
            st.run("wait 1000", 30)
            chain = said(st, "chain")
            if chain and chain[-1].startswith("false"):
                break
        chain = said(st, "chain")
        print("цепочка:", len(chain), chain[-1:] if chain else "", flush=True)
        ok = [x for x in chain if x.startswith("true")]
        check("цепочка из createUnit останавливается потолком", 1 <= len(ok) <= 15 and chain[-1].startswith("false") and "16" in chain[-1], f"{len(ok)} {chain[-1:]}")
        check("игра жива", st.top() == "BattlescapeState", st.top())
        bench.end_turn("s3f", 150)
        print("после цепочки:", last(st, "after chain"), flush=True)
        check("игра жива в конце", st.top() == "BattlescapeState", st.top())


def part_save(ctx):
    bench, mods, battle = ctx
    options = "autosave=true;autosaveFrequency=1;autosaveSlots=1"
    with Stand(ctx, "s3g", battle, ("s3save",), options) as st:
        bench.end_turn("s3g", 150)
        saves = sorted(bench.folder("s3g").rglob("*.asav"), key=lambda f: f.stat().st_mtime)
        check("автосохранение есть", saves, saves[-1].name if saves else "")
        first = last(st, "autosave has")
        for tag in ("first", "own", "air"):
            print(tag, last(st, "unit " + tag), flush=True)
        check("done выполнены до записи", all(last(st, "unit " + t)[:1].isdigit() for t in ("first", "own", "air")), last(st, "unit air"))
        text = saves[-1].read_text(encoding="utf-8", errors="replace")
        keep = HERE / "with_units.sav"
        keep.write_text(text, encoding="utf-8", newline="\n")
        check("№ 8 в сейве новые юниты", text.count("genUnitType: S3_UNIT") == 3, str(text.count("genUnitType: S3_UNIT")))
        given = [x for x in said(st, "item given") if x.startswith("S3_ITEM")]
        print("выдача:", len(given), "|", last(st, "item ground"), flush=True)
        check("№ 8 в сейве новые предметы", text.count("type: S3_ITEM") == 1 + len(given) and given, f"{text.count('type: S3_ITEM')} при выданных {len(given)}")
        head = text[:text.index("\n---")] if "\n---" in text else text[:800]
        check("№ 9 отметка в заголовке со словом spawn", "luaTouched" in head and "spawn" in head, head[-200:])
        print("статусы новых:", re.findall(r"genUnitType: S3_UNIT\n.*?\n\s+faction: (\d+)\n\s+status: (\d+)\n\s+position: (\[[^\]]*\])", text, flags=re.S), flush=True)
        name = saves[-1].name
        shown = st.run(f"load {name}; wait 3000; state", 120)
        print(shown.strip()[-100:], flush=True)
        check("загрузка с новыми", st.top() == "BattlescapeState", st.top())
        st.run("wait 1500", 30)
        path = quick(st, HERE / "loaded.asav")
        again = path.read_text(encoding="utf-8", errors="replace") if path else ""
        places = re.findall(r"genUnitType: S3_UNIT\n.*?\n\s+position: (\[[^\]]*\])", again, flags=re.S)
        print("в воздухе после загрузки:", places, flush=True)
        check("созданный над пустотой упал после загрузки", places and not any(x.endswith(",8]") for x in places), str(places))
        bench.end_turn("s3g", 150)
        mine = said(st, "mine")
        print("после загрузки:", mine, flush=True)
        check("после загрузки юниты на месте", len(mine) >= 3, str(mine))
        check("игра жива", st.top() == "BattlescapeState", st.top())
        # второе автосохранение: у юнитов мода теперь есть предметы игры
        saves = sorted(bench.folder("s3g").rglob("*.asav"), key=lambda f: f.stat().st_mtime)
        check("без ошибок мода", not st.errors(), st.errors()[:300])
        text = saves[-1].read_text(encoding="utf-8", errors="replace")
        print("выдано юнитам мода:", said(st, "item to mine"), flush=True)
        keep.write_text(text, encoding="utf-8", newline="\n")
    # № 9: мода нет, его юниты и предметы в сейве
    with Stand(ctx, "s3h", keep, ()) as st:
        st.run("wait 500", 30)
        top = st.top()
        print("без мода экран:", top, flush=True)
        log = bench.call("log", "--name", "s3h", "-n", "40000", timeout=60)
        rows = [l.strip()[:140] for l in log.splitlines() if "S3_" in l or "Failed to load" in l]
        print("журнал без мода:", rows[:8], flush=True)
        check("№ 9 вещи юнита мода названы в журнале", any("its unit is gone" in r for r in rows), str(rows[-3:]))
        check("№ 9 без мода сейв загружен", top == "BattlescapeState", top)
        check("№ 9 в журнале названы предмет и юнит", any("S3_ITEM" in r for r in rows) and any("S3_UNIT" in r for r in rows), str(rows[:4]))
        info = st.info()
        check("№ 9 бой живой", info is not None and info.group(1) == "BattlescapeState")
        bench.end_turn("s3h", 150)
        check("№ 9 ход без мода", st.top() == "BattlescapeState", st.top())
        path = quick(st, HERE / "without.asav")
        check("№ 9 сохранение без мода", path is not None)
        if path:
            text = path.read_text(encoding="utf-8", errors="replace")
            check("№ 9 в новом сейве следов нет", "S3_UNIT" not in text and "S3_ITEM" not in text, str(text.count("S3_")))


def part_seed(ctx):
    bench, mods, battle = ctx
    runs = []
    for label in ("s3s", "s3t"):
        with Stand(ctx, label, battle, ("s3seed",)) as st:
            bench.end_turn(label, 150)
            bench.end_turn(label, 150)
            runs.append((said(st, "unit seed"), HERE / f"{label}.asav"))
            quick(st, runs[-1][1])
    check("№ 7 тот же сид: те же юниты", runs[0][0] == runs[1][0] and len(runs[0][0]) >= 8, f"{len(runs[0][0])} {len(runs[1][0])}")
    base = []
    for label in ("s3v", "s3w"):
        with Stand(ctx, label, battle, ()) as st:
            bench.end_turn(label, 150)
            bench.end_turn(label, 150)
            base.append(HERE / f"{label}.asav")
            quick(st, base[-1])
    plain = [l for l in same_save(base[0], base[1]) if "_FRAME" not in l]
    print("контроль без мода, строк различий:", len(plain), plain[:6], flush=True)
    # rankIntUnified нейтрала движок берёт из RNG::seedless (BattleUnit::deriveNeutralRank): и у штатно созданного
    diff = [l for l in same_save(runs[0][1], runs[1][1]) if "_FRAME" not in l and "rankIntUnified" not in l]
    check("№ 7 тот же сид: тот же сейв", not diff, str(diff)[:300])


def part_ai(ctx):
    bench, mods, battle = ctx
    with Stand(ctx, "s3i", battle, ("s3ai",)) as st:
        for _ in range(3):
            t0 = time.time()
            bench.end_turn("s3i", 150)
            print(f"ход ИИ: {time.time() - t0:.0f} с", last(st, "ai turn"), flush=True)
        turns = said(st, "ai turn")
        print("снятия:", turns, flush=True)
        check("у ИИ сняты предметы на его ходу", len(turns) >= 3 and int(turns[-1].split()[1]) > 0, str(turns[-1:]))
        new = said(st, "unit ai new")
        check("ИИ получил юнита на своём ходу", new and new[-1][:1].isdigit(), str(new[-1:]))
        want(st, "ai read only", "false", "only read")
        check("игра жива", st.top() == "BattlescapeState", st.top())
        check("без ошибок мода", not st.errors(), st.errors()[:300])


def to_geoscape(st, limit=60):
    t0 = time.time()
    order = []
    while time.time() - t0 < limit:
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
    print("экраны:", order, f"{time.time() - t0:.0f} с", flush=True)
    return st.top() == "GeoscapeState"


def part_end(ctx):
    bench, mods, battle = ctx
    with Stand(ctx, "s3j", battle, ("s3end",)) as st:
        st.run("wait 500")
        step(st, 800)
        own = last(st, "unit own")
        check("свой юнит в бою", own[:1].isdigit(), own)
        step(st, 1200)
        print("все мертвы:", last(st, "all dead"), "| новый:", last(st, "unit last foe"), flush=True)
        t0 = time.time()
        bench.end_turn("s3j", 150)
        print(f"ход: {time.time() - t0:.0f} с", st.info().group(0)[:80], flush=True)
        check("новый враг продлил бой", st.top() == "BattlescapeState", st.top())
        step(st, 800)
        print("живых:", last(st, "still"), flush=True)
        st.run("key 8", 30)
        t0 = time.time()
        seen = []
        while time.time() - t0 < 60:
            top = st.top()
            if top and (not seen or seen[-1] != top):
                seen.append(top)
            if top in ("GeoscapeState", "MainMenuState"):
                break
            if top in ("NextTurnState",):
                st.run("click 160,100", 30)
            elif top not in ("BattlescapeState", ""):
                st.run("key 13; wait 500", 30)
            time.sleep(0.5)
        print("конец боя:", seen, f"{time.time() - t0:.0f} с", flush=True)
        check("бой окончен", st.top() == "MainMenuState" and "DebriefingState" in seen, st.top())
        check("battleEnd сработал", said(st, "finish"), str(said(st, "finish")))
        want(st, "end spawn", "false")
        want(st, "end remove", "false")
        print("очередь при конце:", st.lines("dropped")[:3], said(st, "item queued at the end")[:2], flush=True)
        check("без ошибок мода", not st.errors(), st.errors()[:300])


def part_start(ctx):
    bench, mods, battle = ctx
    sys.path.insert(0, str(ROOT / "tools/lua_stage5"))
    import defects
    camp = HERE / "camp"
    camp.mkdir(exist_ok=True)
    save = defects.geoscape_save(camp)
    with Stand(ctx, "s3k", save, ("s3start",)) as st:
        t0 = time.time()
        while time.time() - t0 < 45:
            top = st.top()
            if top == "BattlescapeState":
                break
            if top == "ConfirmLandingState":
                st.run("key 13; wait 1200", 60)
            elif top == "BriefingState":
                st.run("key 13; wait 800", 60)
            elif top not in ("GeoscapeState", ""):
                st.run(ESC, 30)
            time.sleep(0.5)
        check("бой кампании начался", st.top() == "BattlescapeState", st.top())
        st.run("wait 1500", 30)
        check("battleStart: до такта ничего нет", last(st, "start numbers") == last(st, "start end"), last(st, "start end"))
        check("battleStart: предмет на первом такте", last(st, "item first").startswith("STR_ELECTRO_FLARE"), last(st, "item first"))
        check("battleStart: юнит на первом такте", last(st, "unit start")[:1].isdigit(), last(st, "unit start"))
        check("battleStart: выдача после снаряжения", any(x.startswith("S3_ITEM true") for x in said(st, "item given")), str(said(st, "item given")[:2]))
        want(st, "start write", "false", "only read")
        want(st, "start screen", "false")
        want(st, "start tag", "false")
        # цепочка: done ставит следующий запрос, очередь не пуста всё время
        step(st, 0)
        check("бой кампании закончился", to_geoscape(st), st.top())
        print("цепочка до конца боя:", len(st.lines("S3 chain")), flush=True)
        errors = st.errors()
        check("конец боя чистит очередь со строкой журнала", "queued changes are dropped" in errors, errors[:200])
        want(st, "end spawn", "false")
        # окна кампании приходят одно за другим: сохранение не пробиться, солдат считает сам мод
        t0 = time.time()
        while time.time() - t0 < 30 and not said(st, "quarters after"):
            if st.top() not in ("GeoscapeState", ""):
                st.run("key 27; wait 300", 30)
            else:
                st.run("key 53; wait 300", 30)
        was, now = last(st, "quarters before"), last(st, "quarters after")
        print("жилых мест:", was, "->", now, flush=True)
        check("свой юнит не стал солдатом", was and now and int(now) <= int(was), f"{was} -> {now}")
        check("без ошибок мода", " s3start " not in st.errors(), st.errors()[:300])


def part_ufo(ctx):
    """№ 17: ванильный UFO, бой стенда."""
    bench = ctx[0]
    mods = HERE / "mods_ufo"
    mods.mkdir(exist_ok=True)
    s1.mod(mods, "s3ufo", UFO, "luaCaps: [spawn]\n")
    meta = mods / "s3ufo/metadata.yml"
    meta.write_text(meta.read_text(encoding="utf-8").replace("piratez", "xcom1"), encoding="utf-8", newline="\n")
    name = "s3u"
    lua_mod_check.unlink_all(bench.folder(name))
    a = ["start", "--name", name, "--exe", s1.EXE, "--save", "", "--master", "xcom1", "--mods-dir", str(mods), "--mods", "s3ufo=true", "--timeout", "120", "--set", "oxceLuaMods=true"]
    print(name, bench.call(*a, timeout=140).strip().splitlines()[-1][:120], flush=True)
    try:
        print(bench.run(name, "open battle; wait 2500; state", 90).strip()[-100:], flush=True)
        for _ in range(8):
            top = bench.state(name)[0]
            if top == "BattlescapeState":
                break
            bench.run(name, "key 27; wait 800" if top == "InventoryState" else "key 13; wait 800", 30)
        for _ in range(2):
            bench.end_turn(name, 120)
        log = bench.folder(name) / "openxcom.log"
        lines = [l.split("S3 ", 1)[1].strip() for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if "S3 ufo" in l]
        print(lines[:10], flush=True)
        check("UFO: юнит создан", any(l.startswith("ufo unit true") for l in lines), str(lines[:3]))
        check("UFO: выдача", any(l.startswith("ufo give") for l in lines), str(lines[:3]))
        check("UFO: снятие", any(l.startswith("ufo remove") for l in lines), str(lines[:3]))
        path = bench.folder(name) / "lua_errors.log"
        errs = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        check("UFO: журнал ошибок Lua пуст", not errs, errs[:200])
    finally:
        bench.call("stop", "--name", name, timeout=60)


def part_measure(ctx):
    """Цена юнитов: 16 штук порциями в бою, кадр самый плохой против боя без создания."""
    out = {}
    for label, name, clicks in (("без создания", "s3p0", 0), ("16 юнитов", "s3p1", 4)):
        log = HERE / f"frames_{name}.tsv"
        if log.exists():
            log.unlink()
        with Stand(ctx, name, ctx[2], ("s3heavy",), OXCE_HD_FRAMELOG=str(log)) as st:
            st.run("wait 500")
            for _ in range(4):
                if clicks:
                    step(st, 700)
                else:
                    st.run(f"{OPEN}; {ESC}; wait 900", 30)
            check("замер: без ошибок мода", not st.errors(), st.errors()[:200])
        os.environ.pop("OXCE_HD_FRAMELOG", None)
        rows = []
        with open(log, encoding="utf-8", errors="replace") as f:
            head = f.readline().rstrip("\n").split("\t")
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == len(head):
                    rows.append(dict(zip(head, parts)))
        v = sorted(int(r["loop_us"]) / 1000 for r in rows if "BattlescapeState" in r["state"])
        if v:
            v = v[:-1]  # самый первый кадр боя после загрузки, он есть и без мода
        out[label] = (len(v), round(v[len(v) // 2], 2), round(v[int(len(v) * 0.95)], 2), round(v[-1], 1)) if v else None
        print(label, "кадры (число, p50 мс, p95 мс, худший мс):", out[label], flush=True)
    check("замер есть", all(out.values()))


PARTS = {"units": part_units, "give": part_give, "remove": part_remove, "order": part_order, "caps": part_caps, "turn": part_turn,
         "save": part_save, "seed": part_seed, "ai": part_ai, "end": part_end, "start": part_start, "ufo": part_ufo, "measure": part_measure}
ALONE = ("measure",)  # замер времени: без соседей


def run(ctx, n):
    if time.time() - started > LIMIT:
        check(f"потолок времени {LIMIT} с: {n} не прогнан", False)
        return
    t0 = time.time()
    print(f"--- {n}", flush=True)
    try:
        PARTS[n](ctx)
    except Exception as e:
        check(f"{n}: сбой проверки", False, repr(e)[:300])
    print(f"--- {n}: {time.time() - t0:.0f} с", flush=True)


if __name__ == "__main__":
    ctx = prepare()
    names = sys.argv[1:] or list(PARTS)
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda n: run(ctx, n), [n for n in names if n not in ALONE]))
    for n in names:
        if n in ALONE:
            run(ctx, n)
    print(f"итог: {'FAIL ' + str(len(failed)) if failed else 'PASS'}, {time.time() - started:.0f} с", flush=True)
    for f in failed:
        print("  FAIL:", f[:140])
    sys.exit(1 if failed else 0)
