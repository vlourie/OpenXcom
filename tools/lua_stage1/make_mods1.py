# Тестовые Lua-моды этапа 1: все обработчики, выходные значения, старая ручка, плохой выход, ошибка в main.lua.
import os
from pathlib import Path

ROOT = Path(os.environ["TEMP"]) / "oxce_lua_stage1" / "luamods"

ALL = """
local seen = {}
local function once(name, limit)
  seen[name] = (seen[name] or 0) + 1
  return seen[name] <= (limit or 3)
end
local function utext(u)
  if not u then return "nil" end
  local x, y, z = u:getPosition()
  return string.format("%s#%d rank=%d f=%d/%d hp=%d/%d tu=%d/%d en=%d/%d st=%d/%d mo=%d mana=%d/%d fire=%d wounds=%d arm=%d/%d pos=%d,%d,%d dir=%d killed=%s stunned=%s kneel=%s float=%s armor=%s tag=%d",
    u:getType(), u:getId(), u:getRank(), u:getFaction(), u:getOriginalFaction(), u:getHealth(), u:getHealthMax(), u:getTimeUnits(), u:getTimeUnitsMax(),
    u:getEnergy(), u:getEnergyMax(), u:getStun(), u:getStunMax(), u:getMorale(), u:getMana(), u:getManaMax(), u:getFire(), u:getFatalwoundsTotal(),
    u:getArmor(game.SIDE_FRONT), u:getArmorMax(game.SIDE_FRONT), x, y, z, u:getDirection(), tostring(u:isKilled()), tostring(u:isStunned()),
    tostring(u:isKneeled()), tostring(u:isFloating()), u:getRuleArmor():getType(), u:getTag("LUA_PROBE"))
end
local function itext(i)
  if not i then return "nil" end
  local owner = i:getOwner()
  return string.format("%s#%d ammo=%d/%d fuse=%d fuseOn=%s heal=%d pk=%d stim=%d isAmmo=%s owner=%s tag=%d", i:getRuleItem():getType(), i:getId(),
    i:getAmmoQuantity(), i:getAmmoQuantityMax(), i:getFuseTimer(), tostring(i:isFuseEnabled()), i:getHealQuantity(), i:getPainKillerQuantity(),
    i:getStimulantQuantity(), tostring(i:isAmmo()), owner and owner:getId() or "nil", i:getTag("LUA_ITEM"))
end

game.on("createUnit", function(unit, battle, turn)
  unit:setTag("LUA_PROBE", 100 + unit:getId() % 7)
  if once("createUnit") then game.log("createUnit turn=" .. turn, utext(unit)) end
end)
game.on("createItem", function(item, unit, battle, turn)
  item:setTag("LUA_ITEM", 5)
  if once("createItem") then game.log("createItem turn=" .. turn, itext(item), "unit", unit and unit:getId() or "nil") end
end)
game.on("newTurnUnit", function(unit, battle, turn, side)
  unit:setTag("LUA_PROBE", unit:getTag("LUA_PROBE") + 1)
  if once("newTurnUnit", 2) then
    local sx, sy, sz = battle:getSize()
    local left, right = unit:getLeftHandWeapon(), unit:getRightHandWeapon()
    game.log("newTurnUnit turn=" .. turn .. "/" .. battle:getTurn() .. " side=" .. side .. " map=" .. sx .. "x" .. sy .. "x" .. sz, utext(unit), "right", itext(right), "left", itext(left))
    battle:flashMessage("Lua says hello on turn {0}", turn)
  end
end)
game.on("newTurnItem", function(item, battle, turn, side)
  item:setTag("LUA_ITEM", item:getTag("LUA_ITEM") + 1)
  if once("newTurnItem", 2) then game.log("newTurnItem turn=" .. turn .. " side=" .. side .. " rnd=" .. math.random(1, 1000), itext(item)) end
end)
game.on("hitUnit", function(unit, damaging_item, weapon_item, attacker, battle, skill, orig_power, damaging_type, battle_action, out)
  if once("hitUnit", 8) then
    game.log("hitUnit", utext(unit), "ammo", itext(damaging_item), "attacker", attacker and attacker:getId() or "nil", "skill", skill and skill:getType() or "nil",
      "orig", orig_power, "dt", damaging_type, "ba", battle_action, "out", out.power, out.part, out.side)
  end
  out.power = out.power + 7
end)
game.on("damageUnit", function(unit, damaging_item, weapon_item, attacker, battle, skill, currPower, orig_power, part, side, damaging_type, battle_action, out)
  if once("damageUnit", 8) then
    game.log("damageUnit unit=" .. unit:getId(), "hp", unit:getHealth(), "cur", currPower, "orig", orig_power, "part", part, "side", side, "wounds", unit:getFatalwounds(part),
      "armor", unit:getArmor(side), "out", out.to_health, out.to_armor, out.to_stun, out.to_time, out.to_energy, out.to_morale, out.to_wound, out.to_transform, out.to_mana)
  end
  out.to_health = 3
end)
game.on("damageSpecialUnit", function(unit, damaging_item, weapon_item, attacker, battle, skill, health_damage, orig_power, part, side, damaging_type, battle_action, out)
  if once("damageSpecialUnit", 8) then
    game.log("damageSpecialUnit unit=" .. unit:getId(), "hp now", unit:getHealth(), "dmg", health_damage, "out", out.transform, out.transform_chance, out.self_destruct, out.self_destruct_chance,
      out.morale_loss, out.fire, out.attacker_turns_since_spotted, out.attacker_turns_left_spotted_for_snipers)
  end
  out.transform = 123 -- read only, ignored
end)
game.on("healUnit", function(actor, item, battle, target, battle_action, out)
  if once("healUnit", 8) then
    game.log("healUnit actor=" .. actor:getId(), "target", target:getId(), itext(item), "ba", battle_action, "out", out.medikit_action_type, out.body_part, out.wound_recovery, out.health_recovery,
      out.energy_recovery, out.stun_recovery, out.mana_recovery, out.morale_recovery, out.painkiller_recovery)
  end
end)
game.on("skillUseUnit", function(actor, item, battle, skill, battle_action, have_tu, out)
  if once("skillUseUnit", 8) then game.log("skillUseUnit actor=" .. actor:getId(), skill:getType(), "ba", battle_action, "tu", have_tu, "out", out.continue_action, out.spend_tu) end
end)
game.on("returnFromMissionUnit", function(unit, battle, soldier, out)
  if once("returnFromMissionUnit", 8) then
    game.log("returnFromMissionUnit", utext(unit), "soldier", soldier:getId(), soldier:getRank(), "out", out.recovery_time, out.mana_loss, out.health_loss, out.final_mana_loss, out.final_health_loss)
    battle:flashMessage("must not show")
  end
  out.recovery_time = out.recovery_time + 2
  out.health_loss = 999 -- read only, ignored
end)
game.log("all main.lua ok, api sample", game.BODYPART_HEAD, game.SIDE_UNDER, game.FACTION_HOSTILE, game.BA_CQB, game.DT_19)
"""

STALE = """
local saved
local after = 0
game.on("newTurnUnit", function(unit)
  if not saved then saved = unit; return end
  after = after + 1
  if after <= 2 then
    local ok, err = pcall(function() return saved:getHealth() end)
    game.log("stale handle:", ok, err)
  end
end)
game.on("damageSpecialUnit", function(unit, a, b, c, d, e, f, g, h, i, j, k, out)
  if after < 1000 and unit:isKilled() then
    after = 1000
    saved = unit
    game.log("kept a dying unit", unit:getId())
  elseif after == 1000 then
    after = 1001
    local ok, err = pcall(function() return saved:getHealth() end)
    game.log("handle of a dead unit:", ok, err)
  end
end)
"""

BADOUT = """
local n = 0
game.on("hitUnit", function(unit, a, b, c, d, e, f, g, h, out)
  n = n + 1
  local before = out.power
  if n % 3 == 1 then out.power = 1.5
  elseif n % 3 == 2 then out.power = "lots"
  else setmetatable(out, {__index=function() return 1 end, __newindex=function() while true do end end}); out.power = nil end
end)
"""

ERRMOD = """
game.on("newTurnUnit", function(unit) unit:getTag("NO_SUCH_TAG") end)
"""

ITEMTAG = "  BattleItem:\n      LUA_ITEM: int\n"
MODS = {"lua_all": ALL, "lua_stale": STALE, "lua_badout": BADOUT, "lua_err": ERRMOD}
for name, code in MODS.items():
    d = ROOT / name
    (d / "lua").mkdir(parents=True, exist_ok=True)
    (d / "Ruleset").mkdir(exist_ok=True)
    (d / "metadata.yml").write_text(f'name: "{name}"\nversion: 1.0\nauthor: probe\nmaster: piratez\nluaApi: 1\n', encoding="utf-8", newline="\n")
    (d / "lua" / "main.lua").write_text(code, encoding="utf-8", newline="\n")
    rul = "extended:\n  tags:\n    BattleUnit:\n      LUA_PROBE: int\n    BattleItem:\n      LUA_ITEM: int\n"
    (d / "Ruleset" / f"{name}.rul").write_text(rul, encoding="utf-8", newline="\n")
print(ROOT)
print(";".join(f"{n}=true" for n in MODS))
