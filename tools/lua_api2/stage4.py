# API 2, этап 4 в настоящей игре, всё невидимо: правка карты, падение, огонь и дым, отказы, потолки, сейв и загрузка, снятие мода.
# Запуск: py -3.13 tools/lua_api2/stage4.py [часть ...]; без аргумента все части. Потолок всего прогона LIMIT.
import base64, os, re, struct, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage1 as s1
from stage1 import ESC, OPEN, Stand, check, failed, p, quick, row, same_save
import lua_mod_check

ROOT = s1.ROOT
HERE = Path(os.environ["TEMP"]) / "oxce_lua_s4t"
SHOTS = ROOT / "scratchpad/lua_s4"
ALL = ("s4parts", "s4fall", "s4fire", "s4occ", "s4nocap", "s4api1", "s4turn", "s4whole", "s4save", "s4seed", "s4base", "s4goal", "s4boom", "s4start", "s4show", "s4heavy")
LIMIT = 480
started = time.time()

COMMON = r'''
--PICKS--
local function say(tag, ...) game.log("S4 " .. tag, ...) end
local function report(tag, f, ...)
  local ok, text = pcall(f, ...)
  game.log("S4 " .. tag, tostring(ok), tostring(text))
end
local function alive(b, side)
  local out = {}
  for _, u in ipairs(b:getUnits()) do
    if u:getFaction() == side and u:getHealth() > 0 and u:getStun() < u:getHealth() then out[#out + 1] = u end
  end
  return out
end
local function soldier(b, n) return alive(b, game.FACTION_PLAYER)[n or 1] end
local function show(t, part)
  local set, id = t:getPart(part)
  return tostring(set) .. "/" .. tostring(id)
end
local function empty(t)
  return t and t:getPart(game.PART_FLOOR) and not t:getPart(game.PART_WEST) and not t:getPart(game.PART_NORTH) and not t:getPart(game.PART_OBJECT)
end
-- открытая площадка 7 на 7 ближе всего к первому солдату: она видна в кадре. На этом бою таких мест мало, и в них стоят
-- солдаты, поэтому свободной от юнитов обязана быть только середина.
-- Один проход: у обработчика потолок команд, повторный обход карты его съест
local function zone(b)
  local ux, uy = soldier(b):getPosition()
  local sx, sy = b:getSize()
  local run = {}
  for x = 0, sx - 1 do
    run[x] = {}
    for y = sy - 1, 0, -1 do
      run[x][y] = empty(b:getTile(x, y, 0)) and (run[x][y + 1] or 0) + 1 or 0
    end
  end
  local best, bx, by = 1000000
  local wide = 0
  for x = 0, sx - 7 do
    for y = 0, sy - 7 do
      local free = true
      for dx = 0, 6 do
        if run[x + dx][y] < 7 then free = false break end
      end
      for dx = 2, 4 do
        for dy = 2, 4 do
          if free and b:getTile(x + dx, y + dy, 0):getUnit() then free = false end
        end
      end
      if free then
        local d = math.abs(x + 3 - ux) + math.abs(y + 3 - uy)
        if d < best then best, bx, by = d, x, y end
      end
    end
  end
  if not bx then error("no open place") end
  return bx, by
end
local function tileDone(tag)
  return function(t, why)
    if t then
      local x, y, z = t:getPosition()
      say("done " .. tag, x, y, z)
    else
      say("done " .. tag, "nil", why)
    end
  end
end
local function steps(list, read)
  local n = 0
  game.screen("lab", function(ui)
    ui:window{ x = 32, y = 20, w = 256, h = 160 }
    local b = game.getBattle()
    if b then report("build map", function() b:getTile(0, 0, 0):setSmoke(1) end) end
    ui:button{ x = 50, y = 50, w = 220, h = 18, text = "go", onClick = function()
      n = n + 1
      say("step", n)
      list[n](game.getBattle())
    end }
    if read then
      ui:button{ x = 50, y = 80, w = 220, h = 18, text = "read", onClick = function() read(game.getBattle()) end }
    end
  end, { menu = "inbattle" })
end
'''

PARTS = COMMON + r'''
local x, y
local F, W, N, O = game.PART_FLOOR, game.PART_WEST, game.PART_NORTH, game.PART_OBJECT
steps{
  function(b)
    x, y = zone(b)
    say("zone", x, y)
    local sets = b:getMapSets()
    say("sets", #sets, sets[1].name, sets[1].size)
    local t = b:getTile(x, y, 0)
    say("before", show(t, F), show(t, W), show(t, N), show(t, O))
    t:setPart(W, WALLW.set, WALLW.id, tileDone("set west"))
    say("not yet", show(t, W))
    b:getTile(x + 2, y, 0):setPart(N, WALLN.set, WALLN.id, tileDone("set north"))
    b:getTile(x + 4, y, 0):setPart(O, OBJ.set, OBJ.id, tileDone("set object"))
    b:getTile(x + 6, y, 0):setPart(F, FLOOR.set, FLOOR.id, tileDone("set floor"))
    b:getTile(x, y, 1):setPart(F, FLOOR.set, FLOOR.id, tileDone("set high floor"))
    b:getTile(x + 2, y + 2, 0):clearPart(O, tileDone("clear empty"))
    b:getTile(x + 2, y + 2, 0):destroyPart(W, tileDone("destroy empty"))
    if HOLE then b:getTile(x + 2, y + 2, 0):setPart(F, HOLE.set, HOLE.id, tileDone("lowest hole")) end
    report("part high", t.setPart, t, 4, WALLW.set, WALLW.id)
    report("part low", t.setPart, t, -1, WALLW.set, WALLW.id)
    report("no set", t.setPart, t, W, "S4_NOPE", 0)
    report("id high", t.setPart, t, W, WALLW.set, 100000)
    report("id low", t.setPart, t, W, WALLW.set, -1)
    report("other part", t.setPart, t, W, FLOOR.set, FLOOR.id)
    report("get high", t.getPart, t, 4)
    report("clear high", t.clearPart, t, 4)
    report("destroy high", t.destroyPart, t, 4)
    report("fire high", t.setFire, t, 256)
    report("fire low", t.setFire, t, -1)
    report("smoke high", t.setSmoke, t, 16)
    report("smoke low", t.setSmoke, t, -1)
  end,
  function(b)
    local t = b:getTile(x, y, 0)
    say("west", show(t, W))
    say("north", show(b:getTile(x + 2, y, 0), N))
    say("object", show(b:getTile(x + 4, y, 0), O))
    say("floor", show(b:getTile(x + 6, y, 0), F))
    say("high", show(b:getTile(x, y, 1), F))
    t:clearPart(W, tileDone("clear west"))
    b:getTile(x + 2, y, 0):destroyPart(N, tileDone("destroy north"))
    b:getTile(x + 4, y, 0):destroyPart(O, tileDone("destroy object"))
    b:getTile(x + 6, y, 0):clearPart(F, tileDone("clear floor"))
    b:getTile(x, y, 1):clearPart(F, tileDone("clear high"))
    b:getTile(x + 6, y + 2, 0):destroyPart(F, tileDone("destroy floor"))
  end,
  function(b)
    say("west gone", show(b:getTile(x, y, 0), W))
    say("north gone", show(b:getTile(x + 2, y, 0), N))
    say("object gone", show(b:getTile(x + 4, y, 0), O))
    say("earth", show(b:getTile(x + 6, y, 0), F))
    say("high gone", show(b:getTile(x, y, 1), F))
    say("wreck", show(b:getTile(x + 6, y + 2, 0), F))
    local t = b:getTile(x + 3, y + 3, 0)
    t:setSmoke(5, function(tile)
      say("in done", tile:getSmoke())
      game.getBattle():getTile(x + 3, y + 3, 0):setSmoke(9, tileDone("from failed done"))
      error("S4 boom")
    end)
    b:getTile(x + 4, y + 3, 0):setSmoke(3, tileDone("next to failed"))
  end,
  function(b)
    say("smoke", b:getTile(x + 3, y + 3, 0):getSmoke(), b:getTile(x + 4, y + 3, 0):getSmoke())
  end,
}
'''

FALL = COMMON + r'''
local x, y
local F = game.PART_FLOOR
steps{
  function(b)
    x, y = zone(b)
    b:getTile(x + 3, y + 3, 1):setPart(F, FLOOR.set, FLOOR.id, tileDone("floor"))
  end,
  function(b)
    b:spawnUnit{ type = "STR_MUTON_SOLDIER", x = x + 3, y = y + 3, z = 1, faction = game.FACTION_NEUTRAL, done = function(u, why)
      say("unit", u and u:getId() or "nil", tostring(why))
    end }
    b:spawnItem("S4_ITEM", x + 3, y + 3, 1, function(item, why) say("item", tostring(item ~= nil), tostring(why)) end)
  end,
  function(b)
    local u = b:getTile(x + 3, y + 3, 1):getUnit()
    say("up", u and u:getId() or "nil")
    b:getTile(x + 3, y + 3, 1):clearPart(F, tileDone("hole"))
  end,
  function(b)
    say("down", tostring(b:getTile(x + 3, y + 3, 1):getUnit() ~= nil), tostring(b:getTile(x + 3, y + 3, 0):getUnit() ~= nil))
  end,
}
'''

FIRE = COMMON + r'''
local x, y, gx, gy, gz
local asked
game.on("aiCalculateTargetWeight", function(unit, target, battle, out)
  if not asked then
    asked = true
    report("ai read only", function() battle:getTile(0, 0, 0):setSmoke(1) end)
  end
end)
local function burning(b)
  local list = {}
  for i = 1, 3 do
    local u = soldier(b, i)
    list[#list + 1] = u:getId() .. ":" .. u:getHealth()
  end
  return table.concat(list, " ")
end
steps({
  function(b)
    x, y = zone(b)
    local t = b:getTile(x + 3, y + 3, 0)
    t:setFire(3, tileDone("fire"))
    b:getTile(x + 5, y + 3, 0):setSmoke(15, tileDone("smoke"))
    local sx, sy, sz = b:getSize()
    b:getTile(x + 1, y + 1, sz - 1):setFire(3, tileDone("air fire"))
  end,
  function(b)
    local t = b:getTile(x + 3, y + 3, 0)
    say("burns", t:getFire(), t:getSmoke())
    say("thick", b:getTile(x + 5, y + 3, 0):getSmoke(), b:getTile(x + 5, y + 3, 0):getFire())
    b:getTile(x + 5, y + 3, 0):setSmoke(0, tileDone("no smoke"))
    t:setFire(0, tileDone("out"))
  end,
  function(b)
    local t = b:getTile(x + 3, y + 3, 0)
    say("out now", t:getFire())
    say("clean", b:getTile(x + 5, y + 3, 0):getSmoke())
    -- огонь под солдатами: урон обычным путём
    for i = 1, 3 do
      local ux, uy, uz = soldier(b, i):getPosition()
      b:getTile(ux, uy, uz):setFire(4, tileDone("under"))
    end
    say("health", burning(b))
    -- огонь на части, которую снимают: гаснет, как у взрыва
    local a = b:getTile(x + 1, y + 5, 0)
    a:setFire(4, function(tile)
      say("to clear", tile:getFire())
    end)
  end,
  function(b) say("health", burning(b)) end,
}, function(b) say("health", burning(b)) end)
'''

OCC = COMMON + r'''
steps{
  function(b)
    local u = soldier(b)
    local x, y, z = u:getPosition()
    local t = b:getTile(x, y, z)
    say("under", show(t, game.PART_OBJECT))
    t:setPart(game.PART_OBJECT, SOLID.set, SOLID.id, tileDone("solid"))
    local zx, zy = zone(b)
    b:getTile(zx + 3, zy + 3, 0):setPart(game.PART_OBJECT, SOLID.set, SOLID.id, tileDone("open solid"))
    -- стена на клетке юнита не глухая: у стены своя сторона
    t:setPart(game.PART_NORTH, WALLN.set, WALLN.id, tileDone("wall on unit"))
  end,
  function(b)
    local u = soldier(b)
    local x, y, z = u:getPosition()
    say("object now", show(b:getTile(x, y, z), game.PART_OBJECT))
  end,
}
'''

NOCAP = COMMON + r'''
local once
game.on("newTurnUnit", function(unit, battle, turn, side)
  if once then return end
  once = true
  local x, y, z = unit:getPosition()
  local t = battle:getTile(x, y, z)
  report("nocap setPart", t.setPart, t, game.PART_WEST, WALLW.set, WALLW.id)
  report("nocap clearPart", t.clearPart, t, game.PART_WEST)
  report("nocap destroyPart", t.destroyPart, t, game.PART_WEST)
  report("nocap setFire", t.setFire, t, 1)
  report("nocap setSmoke", t.setSmoke, t, 1)
  report("nocap getPart", function() return show(t, game.PART_FLOOR) end)
  report("nocap getMapSets", function() return #battle:getMapSets() end)
end)
'''

API1 = r'''
local said
game.on("newTurnUnit", function(unit, battle, turn, side)
  if said then return end
  said = true
  local x, y, z = unit:getPosition()
  local t = battle:getTile(x, y, z)
  game.log("S4 api1", tostring(t.getPart), tostring(t.setPart), tostring(t.clearPart), tostring(t.destroyPart), tostring(t.setFire), tostring(t.setSmoke), tostring(battle.getMapSets), tostring(game.PART_FLOOR))
end)
'''

TURN = COMMON + r'''
local function fill(b, n)
  local t = b:getTile(1, 1, 0)
  for i = 1, n do t:setSmoke(1) end
end
local list = {
  function(b) report("call ceiling", fill, b, 100000) end,
}
for i = 1, 7 do list[#list + 1] = function(b) report("fill", fill, b, 64) end end
list[#list + 1] = function(b) report("turn ceiling", fill, b, 1) end
list[#list + 1] = function(b) fill(b, 100000) end
steps(list)
'''

WHOLE = COMMON + r'''
local cx, cy, cz = 0, 0, 0
local parts = 0
local function next_part(b)
  local sx, sy, sz = b:getSize()
  local n = 0
  while n < 60 and cz < sz do
    local t = b:getTile(cx, cy, cz)
    for part = game.PART_FLOOR, game.PART_OBJECT do
      if t:getPart(part) then
        t:destroyPart(part)
        n = n + 1
      end
    end
    cx = cx + 1
    if cx >= sx then
      cx = 0
      cy = cy + 1
      if cy >= sy then
        cy = 0
        cz = cz + 1
      end
    end
  end
  parts = parts + n
end
game.on("newTurnUnit", function(unit, battle, turn, side)
  local ok, text = pcall(next_part, battle)
  if not ok then
    if not said_ then say("ceiling", parts, text) end
    said_ = true
  end
end)
game.on("battleEnd", function(battle, aborted) say("finish", parts) end)
'''.replace("local parts = 0", "local parts = 0\nlocal said_")

SAVE = COMMON + r'''
local F, W, N, O = game.PART_FLOOR, game.PART_WEST, game.PART_NORTH, game.PART_OBJECT
-- отпечаток нижних этажей: части, огонь и дым; переменные Lua после загрузки обнуляются, поэтому читаем всю карту
local function fingerprint(b)
  local sx, sy = b:getSize()
  local sum, count = 0, 0
  for z = 0, 1 do
    for y = 0, sy - 1 do
      for x = 0, sx - 1 do
        local t = b:getTile(x, y, z)
        for part = F, O do
          local set, id = t:getPart(part)
          if set then
            count = count + 1
            sum = (sum * 31 + id + #set * 257 + part * 65537 + x * 7 + y * 11 + z * 13) % 2147483647
          end
        end
        sum = (sum * 31 + t:getFire() * 3 + t:getSmoke() * 5) % 2147483647
      end
    end
  end
  return count .. ":" .. sum
end
local x, y
steps({
  function(b)
    say("print before", fingerprint(b))
    x, y = zone(b)
    b:getTile(x, y, 0):setPart(W, WALLW.set, WALLW.id)
    b:getTile(x + 2, y, 0):setPart(N, WALLN.set, WALLN.id)
    b:getTile(x + 4, y, 0):setPart(O, OBJ.set, OBJ.id)
    b:getTile(x + 6, y, 0):setPart(F, FLOOR.set, FLOOR.id)
    b:getTile(x, y + 2, 0):setPart(DOORW.part, DOORW.set, DOORW.id)
    b:getTile(x + 2, y + 2, 0):setPart(UFOW.part, UFOW.set, UFOW.id)
    b:getTile(x + 4, y + 2, 1):setPart(F, FLOOR.set, FLOOR.id)
    b:getTile(x + 6, y + 2, 0):clearPart(F)
    b:getTile(x, y + 4, 0):setFire(5)
    b:getTile(x + 2, y + 4, 0):setSmoke(11)
    -- запрос прямо перед сохранением: F5 выполняет очередь
    say("queued")
  end,
}, function(b) say("print", fingerprint(b)) end)
'''

SEED = COMMON + r'''
local last
game.on("newTurnUnit", function(unit, battle, turn, side)
  if side ~= game.FACTION_PLAYER or turn == last then return end
  last = turn
  local x, y = zone(battle)
  battle:getTile(x, y, 0):setPart(game.PART_WEST, WALLW.set, WALLW.id, tileDone("seed"))
  battle:getTile(x + 2, y, 0):setPart(game.PART_OBJECT, OBJ.set, OBJ.id, tileDone("seed"))
  battle:getTile(x + 4, y, 0):setFire(3, tileDone("seed"))
  battle:getTile(x + 6, y, 0):setSmoke(9, tileDone("seed"))
  battle:getTile(x + 3, y + 3, 0):destroyPart(game.PART_FLOOR, tileDone("seed"))
end)
'''

BASE = COMMON + r'''
steps{
  function(b)
    local x, y, z = soldier(b):getPosition()
    local t = b:getTile(x, y, z)
    t:setPart(game.PART_WEST, WALLW.set, WALLW.id, tileDone("set"))
    t:clearPart(game.PART_FLOOR, tileDone("clear"))
    t:destroyPart(game.PART_FLOOR, tileDone("destroy"))
    t:setFire(1, tileDone("fire"))
    t:setSmoke(1, tileDone("smoke"))
    say("read", show(t, game.PART_FLOOR))
  end,
  function(b) end,
}
'''

GOAL = COMMON + r'''
local tx, ty
local function find(b)
  local sx, sy = b:getSize()
  for x = 0, sx - 1 do
    for y = 0, sy - 1 do
      local t = b:getTile(x, y, 0)
      if not t:getUnit() and t:getFloorSpecialTileType() == game.STT_START_POINT then return x, y, t end
    end
  end
end
steps{
  function(b)
    local t
    tx, ty, t = find(b)
    say("found", tostring(tx), tostring(ty))
    local set, id = t:getPart(game.PART_FLOOR)
    say("goal part", set, id)
    local zx, zy = zone(b)
    b:getTile(zx + 3, zy + 3, 0):setPart(game.PART_FLOOR, set, id, tileDone("put goal"))
    t:setPart(game.PART_FLOOR, FLOOR.set, FLOOR.id, tileDone("replace goal"))
    t:clearPart(game.PART_FLOOR, tileDone("clear goal"))
    t:destroyPart(game.PART_FLOOR, tileDone("destroy goal"))
  end,
  function(b)
    say("goal now", show(b:getTile(tx, ty, 0), game.PART_FLOOR))
  end,
}
'''

BOOM = COMMON + r'''
local x, y
local function around(b)
  local smoke, gone = 0, 0
  for dx = -2, 2 do
    for dy = -2, 2 do
      if b:getTile(x + dx, y + dy, 0):getSmoke() > 0 then smoke = smoke + 1 end
    end
  end
  return smoke
end
steps({
  function(b)
    x, y = zone(b)
    x, y = x + 3, y + 3
    b:getTile(x, y, 0):setPart(game.PART_OBJECT, BLAST.set, BLAST.id, tileDone("put"))
  end,
  function(b)
    say("object", show(b:getTile(x, y, 0), game.PART_OBJECT))
    say("smoke before", around(b))
    b:getTile(x, y, 0):destroyPart(game.PART_OBJECT, tileDone("blow"))
  end,
  function(b)
    say("smoke after", around(b))
  end,
})
'''

START = COMMON + r'''
game.on("battleStart", function(battle)
  local list = battle:getUnits()
  local x, y, z = list[1]:getPosition()
  local t = battle:getTile(x, y, z)
  say("start read", show(t, game.PART_FLOOR), #battle:getMapSets())
  t:setSmoke(4, function(tile, why)
    say("start smoke", tile and tile:getSmoke() or "nil", tostring(why))
  end)
  say("start not yet", t:getSmoke())
end)
game.on("battleEnd", function(battle, aborted)
  say("finish", aborted)
  report("end map", function() battle:getTile(0, 0, 0):setSmoke(1) end)
  report("end read", function() return #battle:getMapSets() end)
end)
steps{ function(b) end }
'''

SHOW = COMMON + r'''
local F, W, N, O = game.PART_FLOOR, game.PART_WEST, game.PART_NORTH, game.PART_OBJECT
steps({
  function(b)
    local x, y = zone(b)
    say("zone", x, y)
    b:getTile(x, y, 0):setPart(W, WALLW.set, WALLW.id, tileDone("a"))
    b:getTile(x, y + 1, 0):setPart(W, WALLW.set, WALLW.id, tileDone("a"))
    b:getTile(x + 2, y, 0):setPart(N, WALLN.set, WALLN.id, tileDone("a"))
    b:getTile(x + 3, y, 0):setPart(N, WALLN.set, WALLN.id, tileDone("a"))
    b:getTile(x + 5, y, 0):setPart(O, OBJ.set, OBJ.id, tileDone("a"))
    b:getTile(x, y + 3, 0):setPart(DOORW.part, DOORW.set, DOORW.id, tileDone("door"))
    b:getTile(x + 2, y + 3, 0):setPart(DOORN.part, DOORN.set, DOORN.id, tileDone("door"))
    b:getTile(x + 4, y + 3, 0):setPart(UFOW.part, UFOW.set, UFOW.id, tileDone("ufo"))
    b:getTile(x + 6, y + 3, 0):setPart(UFON.part, UFON.set, UFON.id, tileDone("ufo"))
    for dx = 0, 3 do
      for dy = 5, 6 do
        b:getTile(x + dx, y + dy, 0):setPart(F, FLOOR.set, FLOOR.id, tileDone("floor"))
      end
    end
    b:getTile(x + 5, y + 5, 0):clearPart(F, tileDone("earth"))
    b:getTile(x + 5, y + 6, 0):setFire(6, tileDone("fire"))
    b:getTile(x + 6, y + 5, 0):setSmoke(12, tileDone("smoke"))
  end,
}, function(b)
  local x, y = zone(b)
  local sx, sy = b:getSelectedUnit():getPosition()
  say("selected", math.abs(sx - x - 3) + math.abs(sy - y - 3))
end)
'''

HEAVY = COMMON + r'''
local function walls(b, ax, ay)
  for dx = 0, 7 do
    for dy = 0, 7 do
      b:getTile(ax + dx, ay + dy, 0):setPart(game.PART_WEST, WALLW.set, WALLW.id)
    end
  end
end
steps{
  function(b) walls(b, 14, 4) end,
  function(b) walls(b, 22, 4) end,
  function(b) walls(b, 14, 12) end,
  function(b) walls(b, 22, 12) end,
}
'''

UFO = r'''
local last
local F, O = game.PART_FLOOR, game.PART_OBJECT
local function near(battle)
  local sx, sy = battle:getSize()
  for x = 1, sx - 2 do
    for y = 1, sy - 2 do
      local t = battle:getTile(x, y, 0)
      if not t:getUnit() and t:getPart(O) then return t, x, y end
    end
  end
end
game.on("battleStart", function(battle)
  local t = battle:getTile(0, 0, 0)
  game.log("S4 ufo start", #battle:getMapSets(), tostring(t:getPart(F)))
end)
game.on("newTurnUnit", function(unit, battle, turn, side)
  if turn == last then return end
  last = turn
  local t, x, y = near(battle)
  local set, id = t:getPart(O)
  game.log("S4 ufo object", set, id)
  t:destroyPart(O, function(tile, why) game.log("S4 ufo destroy", tostring(tile ~= nil), tostring(why)) end)
  battle:getTile(x + 1, y, 0):setFire(3, function(tile, why) game.log("S4 ufo fire", tostring(tile ~= nil), tostring(why)) end)
  battle:getTile(x, y + 1, 0):setSmoke(5, function(tile, why) game.log("S4 ufo smoke", tostring(tile ~= nil), tostring(why)) end)
end)
'''

RUL = """items:
  - type: S4_ITEM
    size: 0.1
    weight: 1
    invWidth: 1
    invHeight: 1
    bigSprite: 1
    floorSprite: 1
"""


def terrain():
    """Наборы карты этого боя: имя и записи MCD; разметка записи как в MapDataSet::loadData."""
    text = s1.SAVE.read_text(encoding="utf-8")
    names = re.findall(r"- (\S+)", re.search(r"  mapdatasets:\n((?:    - \S+\n)+)", text).group(1))
    files = {}
    for top in (s1.GAME / "standard", s1.GAME / "user/mods"):
        for f in top.rglob("*.MCD"):
            files[f.stem] = f
    out = {}
    for n in names:
        if n in files and n not in out:
            out[n] = files[n].read_bytes()
    return out


def picks():
    """Части под проверку берём из самих MCD: дверь, UFO-дверь, глухой объект, взрывчатый, пустой пол."""
    found = {}

    def take(key, set_, i, part):
        found.setdefault(key, (set_, i, part))

    for set_, data in terrain().items():
        if set_ == "BLANKS":
            continue
        for i in range(len(data) // 62):
            r = data[i * 62:(i + 1) * 62]
            ufo, nofloor, big, door = r[30], r[32], r[33], r[35]
            walk, kind, he, target = r[39], r[53], r[55], r[59]
            if target != 0:
                continue
            plain = not ufo and not door
            if kind == 0 and nofloor:
                take("HOLE", set_, i, kind)
            elif kind == 0 and walk < 255 and plain:
                take("FLOOR", set_, i, kind)
            elif kind == 1 and door:
                take("DOORW", set_, i, kind)
            elif kind == 2 and door:
                take("DOORN", set_, i, kind)
            elif kind == 1 and ufo:
                take("UFOW", set_, i, kind)
            elif kind == 2 and ufo:
                take("UFON", set_, i, kind)
            elif kind == 1 and plain and not he:
                take("WALLW", set_, i, kind)
            elif kind == 2 and plain and not he:
                take("WALLN", set_, i, kind)
            elif kind == 3 and he >= 20:
                take("BLAST", set_, i, kind)
            elif kind == 3 and walk == 255 and not big and not he:
                take("SOLID", set_, i, kind)
            elif kind == 3 and walk < 255 and not he:
                take("OBJ", set_, i, kind)
    need = ("FLOOR", "DOORW", "DOORN", "UFOW", "UFON", "WALLW", "WALLN", "BLAST", "SOLID", "OBJ")
    lost = [k for k in need if k not in found]
    print("части:", {k: v[:2] for k, v in found.items()}, flush=True)
    if lost:
        raise SystemExit(f"нет в наборах боя: {lost}")
    # пустого пола в наборах этого боя может не быть: тогда отказ нижнего этажа не проверить
    return "local HOLE\n" + "".join(f'{"" if k == "HOLE" else "local "}{k} = {{ set = "{v[0]}", id = {v[1]}, part = {v[2]} }}\n' for k, v in found.items())


def said(st, word):
    """Хвост строки журнала после тега: то, что сказал мод."""
    out = []
    word = "S4 " + word
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


def step(st, settle=900, button=59):
    """Кнопка экрана мода; очередь идёт, только когда окна закрыты."""
    st.run(f"{OPEN}; {row(0)}; wait 200; {p(150, button)}; wait 200; {ESC}; {ESC}; wait {settle}", 60)
    if st.top() != "BattlescapeState":
        print("после кнопки экран", st.top(), flush=True)


def read(st, settle=300):
    step(st, settle, 89)


def tiles(path):
    """Вся карта из сейва: binTiles, по нему мод снят или нет, одна и та же карта."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"(?m)^  binTiles: (\S+)$", text)
    return base64.b64decode(m.group(1)) if m else b""


def prepare():
    s1.HERE = HERE
    s1.ALL = ALL
    lua_mod_check.unlink_all(HERE)
    mods = HERE / "mods"
    mods.mkdir(parents=True)
    for d in (s1.GAME / "user/mods").iterdir():
        if d.is_dir():
            lua_mod_check.link_or_copy(d, mods / d.name)
    pick = picks()
    cap = "luaCaps: [screens, map]\n"
    with_picks = lambda code: code.replace("--PICKS--", pick)
    s1.mod(mods, "s4parts", with_picks(PARTS), cap)
    s1.mod(mods, "s4fall", with_picks(FALL), "luaCaps: [screens, spawn, map]\n", RUL)
    s1.mod(mods, "s4fire", with_picks(FIRE), cap)
    s1.mod(mods, "s4occ", with_picks(OCC), cap)
    s1.mod(mods, "s4nocap", with_picks(NOCAP), "luaCaps: [screens]\n")
    own = mods / "s4api1"
    (own / "lua").mkdir(parents=True)
    (own / "metadata.yml").write_text('id: s4api1\nname: "s4api1"\nversion: 0.1\nmaster: "piratez"\nluaApi: 1\n', encoding="utf-8", newline="\n")
    (own / "lua/main.lua").write_text(API1, encoding="utf-8", newline="\n")
    s1.mod(mods, "s4turn", with_picks(TURN), cap)
    s1.mod(mods, "s4whole", with_picks(WHOLE), cap)
    s1.mod(mods, "s4save", with_picks(SAVE), cap)
    s1.mod(mods, "s4seed", with_picks(SEED), cap)
    s1.mod(mods, "s4base", with_picks(BASE), cap)
    s1.mod(mods, "s4goal", with_picks(GOAL), cap)
    s1.mod(mods, "s4boom", with_picks(BOOM), cap)
    s1.mod(mods, "s4start", with_picks(START), cap)
    s1.mod(mods, "s4show", with_picks(SHOW), cap)
    s1.mod(mods, "s4heavy", with_picks(HEAVY), cap)
    listed = "".join(f"  - '{m} ver: 0.1'\n" for m in ALL)
    battle = HERE / "with.sav"
    text = s1.SAVE.read_text(encoding="utf-8")
    text = re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", listed, text, count=1)
    battle.write_text(text, encoding="utf-8", newline="\n")
    base = HERE / "base.sav"
    base.write_text(text.replace("  missionType: STR_UFO_CRASH_RECOVERY\n", "  missionType: STR_BASE_DEFENSE\n", 1), encoding="utf-8", newline="\n")
    goal = HERE / "goal.sav"
    goal.write_text(text.replace("  missionType: STR_UFO_CRASH_RECOVERY\n", "  missionType: STR_UFO_CRASH_RECOVERY\n  objectiveType: 1\n  objectivesDestroyed: 0\n  objectivesNeeded: 100\n", 1), encoding="utf-8", newline="\n")
    # снимки: камера встаёт у выбранного, поэтому один солдат стоит у площадки и выбран
    show = HERE / "show.sav"
    moved, n = re.subn(r"(?m)^(    - id: 4\n(?:      .*\n)*?      position: )\[17,21,0\]", r"\g<1>[23,10,0]", text, count=1)
    assert n == 1
    show.write_text(moved.replace("  selectedUnit: 1\n", "  selectedUnit: 4\n", 1), encoding="utf-8", newline="\n")
    return lua_mod_check.Bench(s1.EXE, HERE), mods, battle, base, goal, show


def part_parts(ctx):
    bench, mods, battle = ctx[:3]
    with Stand(ctx, "s4a", battle, ("s4parts",)) as st:
        st.run("wait 500")
        step(st, 1000)
        want(st, "build map", "false", "only read")
        print("площадка:", last(st, "zone"), "| наборы:", last(st, "sets"), "| было:", last(st, "before"), flush=True)
        check("до такта ничего нет", last(st, "not yet") == "nil/nil", last(st, "not yet"))
        for tag in ("set west", "set north", "set object", "set floor", "set high floor"):
            check(f"{tag}: done(tile)", last(st, "done " + tag)[:1].isdigit(), last(st, "done " + tag))
        want(st, "done clear empty", "nil", "the part is empty")
        want(st, "done destroy empty", "nil", "the part is empty")
        if said(st, "done lowest hole"):
            want(st, "done lowest hole", "nil", "the lowest level needs a floor")
        else:
            print("пустого пола в наборах боя нет: отказ нижнего этажа только по коду", flush=True)
        for tag in ("part high", "part low", "get high", "clear high", "destroy high"):
            want(st, tag, "false", "no such part")
        want(st, "no set", "false", "no set 'S4_NOPE'")
        want(st, "id high", "false", "no such number")
        want(st, "id low", "false", "no such number")
        want(st, "other part", "false", "another part")
        for tag in ("fire high", "fire low"):
            want(st, tag, "false", "0 to 255")
        for tag in ("smoke high", "smoke low"):
            want(st, tag, "false", "0 to 15")
        step(st, 1000)
        for tag in ("west", "north", "object", "floor", "high"):
            text = last(st, tag)
            check(f"прочитано {tag}: набор и номер", "/" in text and not text.startswith("nil"), text)
        for tag in ("clear west", "destroy north", "destroy object", "clear floor", "clear high", "destroy floor"):
            check(f"{tag}: done(tile)", last(st, "done " + tag)[:1].isdigit(), last(st, "done " + tag))
        step(st, 1000)
        print("после снятия:", last(st, "west gone"), last(st, "north gone"), last(st, "object gone"), last(st, "earth"), last(st, "high gone"), last(st, "wreck"), flush=True)
        check("снятая западная стена пуста", last(st, "west gone") == "nil/nil", last(st, "west gone"))
        check("пол z = 0 снят: выжженная земля", last(st, "earth").startswith("BLANKS/"), last(st, "earth"))
        check("пол z = 1 снят: пусто", last(st, "high gone") == "nil/nil", last(st, "high gone"))
        check("разрушенный пол на z = 0 не пустой", not last(st, "wreck").startswith("nil"), last(st, "wreck"))
        step(st, 1000)
        print("ошибка в done:", last(st, "in done"), last(st, "smoke"), flush=True)
        check("ошибка в done в журнале мода", "S4 boom" in st.errors(), st.errors()[:200])
        check("поставленное упавшим done снято", not said(st, "done from failed done"), str(said(st, "done from failed done")))
        check("соседний запрос выполнен", last(st, "smoke").endswith(" 3"), last(st, "smoke"))
        check("игра жива", st.top() == "BattlescapeState", st.top())


def part_fall(ctx):
    bench, mods, battle = ctx[:3]
    with Stand(ctx, "s4b", battle, ("s4fall",)) as st:
        st.run("wait 500")
        step(st, 800)
        check("пол наверху поставлен", last(st, "done floor")[:1].isdigit(), last(st, "done floor"))
        step(st, 1200)
        print("юнит:", last(st, "unit"), "| предмет:", last(st, "item"), flush=True)
        check("юнит встал на новый пол", last(st, "unit")[:1].isdigit(), last(st, "unit"))
        step(st, 1500)
        check("юнит наверху", last(st, "up")[:1].isdigit(), last(st, "up"))
        step(st, 2500)
        down = last(st, "down")
        print("после снятия пола: на z = 1, на z = 0:", down, flush=True)
        check("снятый пол уронил юнита", down == "false true", down)
        path = quick(st, HERE / "fall.asav")
        text = path.read_text(encoding="utf-8", errors="replace") if path else ""
        items = re.findall(r"type: S4_ITEM\n(?:.*\n){0,12}?\s+position: \[([^\]]*)\]", text)
        print("предмет в сейве:", items, flush=True)
        check("снятый пол уронил предмет", items and items[0].replace(" ", "").endswith(",0"), str(items))
        check("без ошибок мода", not st.errors(), st.errors()[:300])
        check("игра жива", st.top() == "BattlescapeState", st.top())


def part_fire(ctx):
    bench, mods, battle = ctx[:3]
    with Stand(ctx, "s4c", battle, ("s4fire",)) as st:
        st.run("wait 500")
        step(st, 800)
        check("огонь поставлен", last(st, "done fire")[:1].isdigit(), last(st, "done fire"))
        want(st, "done air fire", "nil", "nothing to burn")
        step(st, 800)
        print("горит (огонь, дым):", last(st, "burns"), "| дым:", last(st, "thick"), flush=True)
        f = last(st, "burns").split()
        check("огонь 3 и дым для рисунка", f[0] == "3" and int(f[1]) >= 1, last(st, "burns"))
        check("дым 15, огня нет", last(st, "thick") == "15 0", last(st, "thick"))
        step(st, 800)
        check("огонь погашен", last(st, "out now") == "0", last(st, "out now"))
        check("дым снят", last(st, "clean") == "0", last(st, "clean"))
        path = quick(st, HERE / "fire.asav")
        check("сохранение с огнём", path is not None)
        before = last(st, "health")
        bench.end_turn("s4c", 150)
        step(st, 300)
        after = last(st, "health")
        print("здоровье:", before, "->", after, flush=True)
        check("огонь под солдатами обжигает обычным путём", before != after, f"{before} -> {after}")
        want(st, "ai read only", "false", "only read")
        check("без ошибок мода", not st.errors(), st.errors()[:300])
        check("игра жива", st.top() == "BattlescapeState", st.top())


def part_occupied(ctx):
    bench, mods, battle = ctx[:3]
    with Stand(ctx, "s4d", battle, ("s4occ",)) as st:
        st.run("wait 500")
        step(st, 800)
        want(st, "done solid", "nil", "occupied")
        check("на свободную клетку глухой ставится", last(st, "done open solid")[:1].isdigit(), last(st, "done open solid"))
        print("стена на клетке юнита:", last(st, "done wall on unit"), flush=True)
        step(st, 300)
        check("на клетке юнита объект прежний", last(st, "object now") == last(st, "under"), f"{last(st, 'under')} -> {last(st, 'object now')}")
        check("без ошибок мода", not st.errors(), st.errors()[:300])


def part_caps(ctx):
    bench, mods, battle = ctx[:3]
    with Stand(ctx, "s4e", battle, ("s4nocap", "s4api1")) as st:
        bench.end_turn("s4e", 150)
        for name in ("setPart", "clearPart", "destroyPart", "setFire", "setSmoke"):
            want(st, "nocap " + name, "false", "'map'")
        want(st, "nocap getPart", "true", "/")
        want(st, "nocap getMapSets", "true")
        check("№ 3 luaApi: 1 не видит методов", last(st, "api1").startswith("nil nil nil nil nil nil nil "), last(st, "api1"))


def part_turn(ctx):
    bench, mods, battle = ctx[:3]
    with Stand(ctx, "s4f", battle, ("s4turn",)) as st:
        st.run("wait 500")
        # 64 штуки потолка вызова уже стоят: F5 не нужен, поток очереди идёт сам
        step(st, 800)
        want(st, "call ceiling", "false", "more than 64 changes of tiles in one call")
        for _ in range(7):
            step(st, 500)
        check("все порции прошли", all(x.startswith("true") for x in said(st, "fill")) and len(said(st, "fill")) == 7, str(said(st, "fill")[-2:]))
        step(st, 500)
        want(st, "turn ceiling", "false", "more than 512 changes of tiles in one turn")
        step(st, 500)
        errors = st.errors()
        check("№ 6 цикл без pcall: ошибка мода, игра жива", "more than 512" in errors and st.top() == "BattlescapeState", errors[:200])
        bench.end_turn("s4f", 150)
        check("ход сбрасывает потолок, игра жива", st.top() == "BattlescapeState", st.top())


def part_whole(ctx):
    """№ 6: мод сносит всю карту по порциям за ход, потолок держит."""
    bench, mods, battle = ctx[:3]
    with Stand(ctx, "s4g", battle, ("s4whole",)) as st:
        for i in range(3):
            t0 = time.time()
            bench.end_turn("s4g", 150)
            top = st.top()
            print(f"ход {i + 1}: {time.time() - t0:.0f} с, экран {top}", flush=True)
            if top != "BattlescapeState":
                break
        info = st.info()
        check("игра жива при сносе карты", info is not None, st.top())
        print("потолок:", last(st, "ceiling")[:120], flush=True)
        check("№ 6 снос упирается в потолок хода", "512" in last(st, "ceiling") or "64" in last(st, "ceiling"), last(st, "ceiling")[:200])
        if st.top() == "BattlescapeState":
            path = quick(st, HERE / "whole.asav")
            check("сохранение после сноса", path is not None)
            if path:
                shown = st.run(f"load {path.name}; wait 3000; state", 120)
                check("загрузка после сноса", st.top() == "BattlescapeState", shown.strip()[-100:])


def part_save(ctx):
    bench, mods, battle = ctx[:3]
    with Stand(ctx, "s4h", battle, ("s4save",)) as st:
        st.run("wait 500")
        before_click = None
        # F5 сразу после кнопки: очередь обязана уйти раньше записи
        st.run(f"{OPEN}; {row(0)}; wait 200; {p(150, 59)}; wait 200; {ESC}; {ESC}", 60)
        path = quick(st, HERE / "map.asav")
        check("сохранение есть", path is not None)
        text = path.read_text(encoding="utf-8", errors="replace")
        head = text[:text.index("\n---")] if "\n---" in text else text[:800]
        check("№ 9 отметка в заголовке со словом map", "luaTouched" in head and "map" in head, head[-200:])
        read(st, 300)
        was = last(st, "print")
        print("отпечаток:", last(st, "print before"), "->", was, flush=True)
        check("правка есть в отпечатке", was and was != last(st, "print before"), was)
        name = path.name
        shown = st.run(f"load {name}; wait 3000; state", 120)
        check("загрузка с правкой", st.top() == "BattlescapeState", shown.strip()[-100:])
        st.run("wait 500", 30)
        read(st, 300)
        check("№ 8 после загрузки та же карта", last(st, "print") == was, f"{was} -> {last(st, 'print')}")
        check("без ошибок мода", not st.errors(), st.errors()[:300])
        again = quick(st, HERE / "map2.asav")
        check("№ 8 второй сейв: те же клетки", tiles(HERE / "map.asav") == tiles(HERE / "map2.asav"), "")
        bench.end_turn("s4h", 150)
        check("ход после загрузки", st.top() == "BattlescapeState", st.top())
    with Stand(ctx, "s4i", HERE / "map.asav", ()) as st:
        st.run("wait 500", 30)
        check("№ 9 без мода сейв загружен", st.top() == "BattlescapeState", st.top())
        path = quick(st, HERE / "without.asav")
        check("№ 9 сохранение без мода", path is not None)
        if path:
            check("№ 9 правка осталась", tiles(HERE / "map.asav") == tiles(path), f"{len(tiles(path))}")
            head = path.read_text(encoding="utf-8", errors="replace")[:4000]
            check("№ 9 отметка держится", "luaTouched" in head and "map" in head)
        bench.end_turn("s4i", 150)
        check("№ 9 ход без мода", st.top() == "BattlescapeState", st.top())


def part_seed(ctx):
    bench, mods, battle = ctx[:3]
    runs = []
    for label in ("s4s", "s4t"):
        with Stand(ctx, label, battle, ("s4seed",)) as st:
            bench.end_turn(label, 150)
            bench.end_turn(label, 150)
            runs.append((said(st, "done seed"), HERE / f"{label}.asav"))
            quick(st, runs[-1][1])
    check("№ 7 тот же сид: те же клетки", runs[0][0] == runs[1][0] and len(runs[0][0]) >= 5, f"{len(runs[0][0])} {len(runs[1][0])}")
    diff = [l for l in same_save(runs[0][1], runs[1][1]) if "_FRAME" not in l and "rankIntUnified" not in l]
    check("№ 7 тот же сид: тот же сейв", not diff, str(diff)[:300])


def part_base(ctx):
    """№ 10: оборона базы, тип миссии подменён в копии сейва."""
    with Stand(ctx, "s4j", ctx[3], ("s4base",)) as st:
        st.run("wait 500")
        check("бой обороны загружен", st.top() == "BattlescapeState", st.top())
        step(st, 800)
        for tag in ("set", "clear", "destroy", "fire", "smoke"):
            want(st, "done " + tag, "nil", "not in a base defense")
        check("чтение работает", "/" in last(st, "read"), last(st, "read"))
        check("без ошибок мода", not st.errors(), st.errors()[:300])


def part_goal(ctx):
    """Цель миссии: копия сейва с objectiveType 1 (START_POINT), её держит пол корабля."""
    with Stand(ctx, "s4k", ctx[4], ("s4goal",)) as st:
        st.run("wait 500")
        step(st, 800)
        print("цель:", last(st, "found"), last(st, "goal part"), flush=True)
        want(st, "done put goal", "nil", "the mission would not count")
        want(st, "done replace goal", "nil", "the mission counts this part")
        want(st, "done clear goal", "nil", "the mission counts this part")
        check("destroyPart цель берёт", last(st, "done destroy goal")[:1].isdigit(), last(st, "done destroy goal"))
        step(st, 300)
        print("после:", last(st, "goal now"), flush=True)
        path = quick(st, HERE / "goal.asav")
        text = path.read_text(encoding="utf-8", errors="replace") if path else ""
        m = re.search(r"objectivesDestroyed: (\d+)", text)
        check("цель засчитана", m and m.group(1) == "1", m.group(0) if m else "нет в сейве")
        check("без ошибок мода", not st.errors(), st.errors()[:300])


def part_boom(ctx):
    bench, mods, battle = ctx[:3]
    with Stand(ctx, "s4l", battle, ("s4boom",)) as st:
        st.run("wait 500")
        step(st, 800)
        check("взрывчатый объект поставлен", last(st, "done put")[:1].isdigit(), last(st, "done put"))
        step(st, 800)
        check("объект снесён", last(st, "done blow")[:1].isdigit(), last(st, "done blow"))
        print("дым до:", last(st, "smoke before"), flush=True)
        t0 = time.time()
        bench.end_turn("s4l", 150)
        print(f"ход: {time.time() - t0:.0f} с", flush=True)
        step(st, 400)
        print("дым после:", last(st, "smoke after"), flush=True)
        check("взрыв пришёл в конце хода", int(last(st, "smoke after") or 0) > int(last(st, "smoke before") or 0), f"{last(st, 'smoke before')} -> {last(st, 'smoke after')}")
        check("без ошибок мода", not st.errors(), st.errors()[:300])
        check("игра жива", st.top() == "BattlescapeState", st.top())


def part_start(ctx):
    bench, mods, battle = ctx[:3]
    sys.path.insert(0, str(ROOT / "tools/lua_stage5"))
    import defects
    import stage3 as s3
    camp = HERE / "camp"
    camp.mkdir(exist_ok=True)
    save = defects.geoscape_save(camp)
    with Stand(ctx, "s4m", save, ("s4start",)) as st:
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
        print("battleStart:", last(st, "start read"), last(st, "start not yet"), last(st, "start smoke"), flush=True)
        check("battleStart: чтение", "/" in last(st, "start read"), last(st, "start read"))
        check("battleStart: запрос на первом такте", last(st, "start smoke").startswith("4"), last(st, "start smoke"))
        check("бой кампании закончился", s3.to_geoscape(st), st.top())
        want(st, "end map", "false")
        want(st, "end read", "true")
        check("без ошибок мода", " s4start " not in st.errors(), st.errors()[:300])


def part_ufo(ctx):
    """№ 17: ванильный UFO, бой стенда."""
    bench = ctx[0]
    mods = HERE / "mods_ufo"
    mods.mkdir(exist_ok=True)
    s1.mod(mods, "s4ufo", UFO, "luaCaps: [map]\n")
    meta = mods / "s4ufo/metadata.yml"
    meta.write_text(meta.read_text(encoding="utf-8").replace("piratez", "xcom1"), encoding="utf-8", newline="\n")
    name = "s4u"
    lua_mod_check.unlink_all(bench.folder(name))
    a = ["start", "--name", name, "--exe", s1.EXE, "--save", "", "--master", "xcom1", "--mods-dir", str(mods), "--mods", "s4ufo=true", "--timeout", "120", "--set", "oxceLuaMods=true"]
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
        lines = [l.split("S4 ", 1)[1].strip() for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if "S4 ufo" in l]
        print(lines[:8], flush=True)
        check("UFO: разрушение", any(l.startswith("ufo destroy true") for l in lines), str(lines[:3]))
        check("UFO: дым", any(l.startswith("ufo smoke true") for l in lines), str(lines[:3]))
        path = bench.folder(name) / "lua_errors.log"
        errs = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        check("UFO: журнал ошибок Lua пуст", not errs, errs[:200])
    finally:
        bench.call("stop", "--name", name, timeout=60)


def part_show(ctx):
    """№ 14: снимки всех частей на k = 1 и k = 4 и в четырёх поворотах. Правка видна сразу, сброс кэша не нужен."""
    bench, mods, battle = ctx[:3]
    SHOTS.mkdir(parents=True, exist_ok=True)
    lab = "oxceHdLabKey=7309b580d5a6cf0a"
    for k in (1, 4):
        name = f"s4v{k}"
        with Stand(ctx, name, ctx[5], ("s4show",), f"oxceHdScale={k};{lab}") as st:
            st.run("wait 800")
            read(st, 300)
            near = last(st, "selected")
            check(f"k = {k}: выбранный рядом с площадкой", near and int(near) <= 8, near)
            st.run("wait 500")
            before = SHOTS / f"k{k}_before.png"
            st.run(f"shot {before.as_posix()}", 60)
            step(st, 800)
            for r in range(4):
                shot = SHOTS / f"k{k}_r{r}.png"
                st.run(f"set oxceHdMapRotation={r}; wait 600; shot {shot.as_posix()}", 60)
                check(f"снимок k = {k} поворот {r}", shot.exists())
            st.run("set oxceHdMapRotation=0; wait 300", 30)
            check(f"k = {k}: кадр изменился", before.read_bytes() != (SHOTS / f"k{k}_r0.png").read_bytes())
            print(f"k = {k}: площадка", last(st, "zone"), said(st, "done door")[:2], said(st, "done ufo")[:2], flush=True)
            check(f"k = {k}: все части встали", not [x for x in said(st, "done") if x.startswith("nil")], str([x for x in said(st, "done") if x.startswith("nil")][:3]))
            check(f"k = {k}: без ошибок мода", not st.errors(), st.errors()[:300])


def part_measure(ctx):
    """Цена точки: 64 стены за раз, свет всей карты и обзор, кадр самый плохой против боя без правки."""
    out = {}
    for label, name, clicks in (("без правки", "s4p0", 0), ("64 стены 4 раза", "s4p1", 4)):
        log = HERE / f"frames_{name}.tsv"
        if log.exists():
            log.unlink()
        with Stand(ctx, name, ctx[2], ("s4heavy",), OXCE_HD_FRAMELOG=str(log)) as st:
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


PARTS_ = {"parts": part_parts, "fall": part_fall, "fire": part_fire, "occupied": part_occupied, "caps": part_caps, "turn": part_turn,
          "whole": part_whole, "save": part_save, "seed": part_seed, "base": part_base, "goal": part_goal, "boom": part_boom,
          "start": part_start, "ufo": part_ufo, "show": part_show, "measure": part_measure}
ALONE = ("measure",)  # замер времени: без соседей


def run(ctx, n):
    if time.time() - started > LIMIT:
        check(f"потолок времени {LIMIT} с: {n} не прогнан", False)
        return
    t0 = time.time()
    print(f"--- {n}", flush=True)
    try:
        PARTS_[n](ctx)
    except Exception as e:
        check(f"{n}: сбой проверки", False, repr(e)[:300])
    print(f"--- {n}: {time.time() - t0:.0f} с", flush=True)


if __name__ == "__main__":
    ctx = prepare()
    names = sys.argv[1:] or list(PARTS_)
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda n: run(ctx, n), [n for n in names if n not in ALONE]))
    for n in names:
        if n in ALONE:
            run(ctx, n)
    print(f"итог: {'FAIL ' + str(len(failed)) if failed else 'PASS'}, {time.time() - started:.0f} с", flush=True)
    for f in failed:
        print("  FAIL:", f[:140])
    sys.exit(1 if failed else 0)
