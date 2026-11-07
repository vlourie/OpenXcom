# API после самопроверки 06.11 в настоящей игре, всё невидимо: каждый метод вызывается хотя бы раз, отрицательные случаи, редкие обработчики.
# Список методов берётся из tools/lua_api_doc.py, поэтому новый метод без строки здесь сразу виден как «не вызван».
# Запуск: py -3.13 tools/lua_stage5/api.py [battle|geo|cost]; без аргумента все три
import os, re, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lua_api_doc
import defects
from defects import DAMAGE, GAME, HERE, check, failed, lines, run_stand, stand

TAG_SECTIONS = ["BattleUnit", "BattleItem", "BattleGame", "GeoscapeGame", "GeoscapeSoldier", "Country", "Ufo", "Craft",
                "RuleArmor", "RuleItem", "RuleSoldier", "RuleSoldierBonus", "RuleUfo", "RuleCraft", "RuleCountry", "RuleResearch"]
# имя тега одно на всю игру: одинаковое в двух разделах движок отбрасывает
RUL = "extended:\n  tags:\n" + "".join(f"    {s}:\n      S5_{s}: int\n" for s in TAG_SECTIONS)
TAG_OF = {"unit": "BattleUnit", "item": "BattleItem", "battle": "BattleGame", "geoscape": "GeoscapeGame", "soldier": "GeoscapeSoldier", "country": "Country",
          "ufo": "Ufo", "craft": "Craft", "ruleArmor": "RuleArmor", "ruleItem": "RuleItem", "ruleSoldier": "RuleSoldier", "ruleSoldierBonus": "RuleSoldierBonus",
          "ruleUfo": "RuleUfo", "ruleCraft": "RuleCraft", "ruleCountry": "RuleCountry", "ruleResearch": "RuleResearch"}

# Аргументы, которых не вывести из имени. self - сам объект, u - любой юнит боя.
SAMPLE = {
    ("unit", "getInventoryItem"): "ANY_ITEM()",
    ("unit", "setSpawnUnitInstantRespawn"): "0",
    ("unit", "getInventoryItems"): "",
    ("unit", "getStat"): '"health"',
    ("unit", "setStat"): '"health", self:getStat("health")',
    ("unit", "addStat"): '"health", 0',
    ("unit", "getExp"): '"firing"',
    ("unit", "getMoveCost"): '"base"',
    ("unit", "setMoveCost"): '"base", self:getMoveCost("base")',
    ("unit", "getMaxViewDistance"): "20, 0, 0",
    ("unit", "getMaxViewDistanceAtDark"): "self",
    ("unit", "getMaxViewDistanceAtDay"): "self",
    ("unit", "reduceByResistance"): "10, 1",
    ("unit", "setSpawnUnit"): "nil",
    ("unit", "setMovementType"): "self:getMovementType()",
    ("unit", "setArmorMax"): "0, self:getArmorMax(0)",
    ("item", "getAmmoForSlot"): "0",
    ("item", "getAmmoForAction"): "game.BA_AUTOSHOT",
    ("item", "getActionCost"): "u, game.BA_AUTOSHOT",
    ("item", "getMoveToCost"): '"STR_RIGHT_HAND"',
    ("item", "setFuseEnabled"): "false",
    ("battle", "getTile"): "0, 0, 0",
    ("battle", "getUnits"): "",
    ("battle", "randomRange"): "1, 2",
    ("battle", "randomChance"): "50",
    ("battle", "tryConcealUnit"): "u",
    ("soldier", "getStat"): '"health"',
    ("soldier", "setStat"): '"health", self:getStat("health")',
    ("soldier", "addStat"): '"health", 0',
    ("ruleArmor", "getStat"): '"health"',
    ("ruleArmor", "getMoveCost"): '"base"',
    ("ruleItem", "hasCategory"): '"STR_NO_SUCH_CATEGORY"',
    ("ruleDamage", "getDamageTo"): '"health", 10',
    ("ruleDamage", "getRandomDamage"): "10",
    ("tile", "makeDiscovered"): "0",
    ("tile", "getDistanceTile"): "self",
    ("tile", "getDistanceVoxel"): "self",
    ("geoscape", "isResearched"): "RESEARCH",
    ("ufo", "getStat"): '"radarRange"',
    ("craft", "getStat"): '"radarRange"',
    ("geoscape", "randomRangeSymmetric"): "2",
    ("ruleInventory", "getMoveToCost"): "self",
    ("rules", "getRuleInventory"): '"STR_RIGHT_HAND"',
    ("rules", "getSmokeReduction"): "10",
    ("statsForNerds", "addIntRow"): '"S5INT", 7',
    ("statsForNerds", "addTextRow"): '"S5TEXT", "S5"',
    ("statsForNerds", "addTextFormatRow"): '"S5FMT", "{0}/{1}", 1, 2',
}


def call_args(kind, method, args):
    """Что подставить в вызов: свою строку, иначе по именам аргументов из страницы."""
    if (kind, method) in SAMPLE:
        return SAMPLE[(kind, method)]
    getter = "get" + method[3:]
    has_getter = method.startswith("set") and getter in lua_api_doc.METHODS[kind]
    names = [a.strip() for a in args.split(",") if a.strip()]
    out = []
    for a in names:
        if a == "value":
            # запись того же значения: вызов настоящий, бой не меняется
            lead = ", ".join(out)
            out.append(f"self:{getter}({lead})" if has_getter else ("0" if method.startswith("add") else "1"))
        elif a == "name":
            out.append(f'"S5_{TAG_OF[kind]}"')
        elif a in ("part", "side", "faction", "turn", "slot"):
            out.append("0")
        elif a in ("low", "percent", "base", "parts"):
            out.append("1")
        elif a in ("high",):
            out.append("2")
        elif a in ("other", "unit"):
            out.append("u")
        elif a in ("text", "type", "message"):
            out.append('"S5"')
        elif a in ("a", "b", "c", "x", "y", "z", "nerf", "buff"):
            out.append("0")
        else:
            raise SystemExit(f"нет образца для {kind}.{method}({a})")
    return ", ".join(out)


def probe_fn(kind):
    """Функция Lua: все методы типа через pcall, одна строка в журнал на метод. Первое обращение: всё, дальше молчит."""
    body = [f'probes.{kind} = function(self, u, RESEARCH)\n  if done.{kind} then return end\n  done.{kind} = true\n']
    for method, spec in lua_api_doc.METHODS[kind].items():
        args = call_args(kind, method, spec[0])
        body.append(f'  try("{kind}.{method}", function() return self:{method}({args}) end)\n')
    body.append("end\n")
    return "".join(body)


HEAD = '''
local atLoad = game.getRules():getRuleItem("STR_ALIEN_ALLOYS")
game.log("S5VAL", "rule_at_load", atLoad and atLoad:getType() or "nil")
local probes, done = {}, {}
local BATTLE
local function ANY_ITEM() return BATTLE:getItems()[1]:getRuleItem():getType() end
local function try(what, fn)
  local r = table.pack(pcall(fn))
  if r[1] then game.log("S5API", what, "ok", tostring(r[2])) else game.log("S5API", what, "ERR", tostring(r[2])) end
end
local function bad(what, fn)
  local ok, err = pcall(fn)
  game.log("S5BAD", what, ok and "NOERR" or "error", tostring(err))
end
local function good(what, value)
  game.log("S5VAL", what, tostring(value))
end
'''

# У объектов боя свойства берём цепочкой от того, что приходит в обработчик.
BATTLE = '''
local kept, keptDone
local listsDone
game.on("newTurnUnit", function(unit, battle, turn, side)
  BATTLE = battle
  if kept and not keptDone then
    keptDone = true
    bad("ручка юнита после вызова", function() return kept:getHealth() end)
  end
  if not kept then kept = unit end
  probes.unit(unit, unit)
  probes.battle(battle, unit)
  local x, y, z = unit:getPosition()
  local tile = battle:getTile(x, y, z)
  if tile then probes.tile(tile, unit) end
  probes.ruleArmor(unit:getRuleArmor(), unit)
  local rulesAll = game.getRules()
  probes.rules(rulesAll, unit)
  probes.ruleResearch(rulesAll:getRuleResearch("STR_ALIEN_ALLOYS"), unit)
  probes.ruleInventory(rulesAll:getRuleInventoryRightHand(), unit)
  local geo = battle:getGeoscapeGame()
  probes.geoscape(geo, unit, "STR_ALIEN_ALLOYS")
  local country = geo:getCountries()[1]
  if country then
    probes.country(country, unit)
    probes.ruleCountry(country:getRuleCountry(), unit)
  end
  local soldier = unit:getGeoscapeSoldier()
  if soldier then
    probes.soldier(soldier, unit)
    probes.ruleSoldier(soldier:getRuleSoldier(), unit)
  end
  local rules = unit:getRuleUnit()
  if rules then probes.ruleUnit(rules, unit) end

  if not listsDone then
    listsDone = true
    good("units_all", #battle:getUnits())
    good("units_player", #battle:getUnits(game.FACTION_PLAYER))
    good("units_hostile", #battle:getUnits(game.FACTION_HOSTILE))
    good("items_all", #battle:getItems())
    good("items_of_unit", #unit:getInventoryItems())
    good("tile_outside", tostring(battle:getTile(-1, 0, 0)) .. tostring(battle:getTile(100000, 0, 0)) .. tostring(battle:getTile(0, 0, 100000)))
    good("unit_on_tile", tile and tile:getUnit() and tile:getUnit():getId() == unit:getId())
    good("time_year", geo:getTime().year)
    good("rule_found", rulesAll:getRuleItem("STR_ALIEN_ALLOYS"):getType())
    good("rule_missing", tostring(rulesAll:getRuleItem("STR_NO_SUCH_ITEM")))
    good("inventory_hand", rulesAll:getRuleInventoryRightHand():getType() == game.INV_HAND and rulesAll:getRuleInventoryRightHand():isRightHand())
    good("inventory_cost", rulesAll:getRuleInventoryRightHand():getMoveToCost(rulesAll:getRuleInventoryLeftHand()))
    bad("чужой тип вместо ячейки", function() return rulesAll:getRuleInventoryRightHand():getMoveToCost(unit) end)
    -- запись и чтение
    local h = unit:getStat("health")
    unit:setStat("health", h + 3)
    good("stat_set", unit:getStat("health") - h)
    unit:addStat("health", -3)
    good("stat_back", unit:getStat("health") - h)
    unit:setStat("firing", 100000)
    good("stat_high", unit:getStat("firing"))
    unit:setStat("firing", -5)
    good("stat_low", unit:getStat("firing"))
    local mt, me = unit:getMoveCost("normal")
    unit:setMoveCost("normal", mt + 7, me + 9)
    local nt, ne = unit:getMoveCost("normal")
    good("move_cost", (nt - mt) .. "/" .. (ne - me))
    unit:setMoveCost("normal", mt, me)
    unit:setTag("S5_BattleUnit", 41)
    good("tag_unit", unit:getTag("S5_BattleUnit"))
    battle:setTag("S5_BattleGame", 42)
    good("tag_battle", battle:getTag("S5_BattleGame"))
    geo:setTag("S5_GeoscapeGame", 43)
    good("tag_geo", geo:getTag("S5_GeoscapeGame"))
    if soldier then
      soldier:setTag("S5_GeoscapeSoldier", 44)
      good("tag_soldier", soldier:getTag("S5_GeoscapeSoldier"))
    end
    -- отрицательные
    bad("неизвестная характеристика", function() return unit:getStat("nope") end)
    bad("неизвестная запись характеристики", function() unit:setStat("nope", 1) end)
    bad("опыт очков времени", function() return unit:getExp("timeUnits") end)
    bad("неизвестный вид хода", function() return unit:getMoveCost("nope") end)
    bad("чужой тип", function() return unit.getStat(battle, "health") end)
    bad("незнакомое превращение", function() unit:setSpawnUnit("STR_NO_SUCH_UNIT") end)
    bad("сторона за границей", function() return unit:getTurnsSinceSpottedByFaction(99) end)
    bad("сторона за границей отрицательная", function() return unit:getTurnsSinceSpottedByFaction(-1) end)
    -- как в Y-script: за границей ноль и ничего не меняется
    good("wounds_max_outside", unit:getFatalwoundsMax(99))
    unit:setArmorMax(99, 1)
    bad("тип урона за границей", function() return unit:reduceByResistance(1, 100000) end)
    bad("незнакомый предмет", function() return unit:getInventoryItem("STR_NO_SUCH_ITEM") end)
    bad("незнакомый слот у предмета юнита", function() return unit:getInventoryItems("STR_NO_SUCH_SLOT") end)
    bad("незнакомое исследование", function() return geo:isResearched("STR_NO_SUCH_RESEARCH") end)
    bad("тег без объявления", function() return battle:getTag("S5_NO_TAG") end)
    bad("низкая граница больше высокой", function() return battle:randomRange(5, 1) end)
  end
end)
local itemNeg
game.on("newTurnItem", function(item, battle, turn, side)
  local u = battle:getSelectedUnit() or battle:getUnits()[1]
  probes.item(item, u)
  local rules = item:getRuleItem()
  probes.ruleItem(rules, u)
  local damage = rules:getDamageType()
  if damage then probes.ruleDamage(damage, u) end
  if not itemNeg then
    itemNeg = true
    bad("гнездо боеприпаса за границей", function() return item:getAmmoForSlot(99) end)
    bad("гнездо боеприпаса отрицательное", function() return item:getAmmoForSlot(-1) end)
    bad("действие за границей", function() return item:getAmmoForAction(100000) end)
    bad("действие за границей у стоимости", function() return item:getActionCost(u, 100000) end)
    bad("незнакомый слот", function() return item:getMoveToCost("STR_NO_SUCH_SLOT") end)
    bad("чужой юнит вместо предмета", function() return item:getActionCost(item, game.BA_AUTOSHOT) end)
  end
end)
game.on("applySoldierBonuses", function(unit, battle, bonus)
  probes.ruleSoldierBonus(bonus, unit)
  if not done.applied then
    done.applied = true
    local h = unit:getStat("health")
    unit:addStat("health", 1)
    good("bonus_stat", unit:getStat("health") - h)
    unit:addStat("health", -1)
  end
end)
local seen = {}
local function once(name, unit, out)
  if seen[name] then return end
  seen[name] = true
  game.log("S5SEEN", name)
  bad("запись в обработчике только для чтения: " .. name, function() unit:addHealth(0) end)
end
game.on("awardExperience", function(attacker, unit, weapon, battle_action, out)
  once("awardExperience", attacker, out)
  good("experience_multipler", out.experience_multipler)
end)
game.on("tryPsiAttackItem", function(item, attacker, victim, skill, attack_strength, defense_strength, battle_action, distance, distance_strength_reduction, battle, out)
  once("tryPsiAttackItem", attacker, out)
  out.psi_attack_success = 77
end)
game.on("tryPsiAttackUnit", function(item, attacker, victim, skill, attack_strength, defense_strength, battle_action, battle, out)
  once("tryPsiAttackUnit", attacker, out)
  good("psi_chain", out.psi_attack_success)
end)
game.on("tryMeleeAttackItem", function(item, attacker, victim, is_same_faction, skill, attack_strength, defense_strength, battle_action, arc_to_attacker, defense_strength_penalty, battle, out)
  once("tryMeleeAttackItem", attacker, out)
  out.melee_attack_success = 77
end)
game.on("tryMeleeAttackUnit", function(item, attacker, victim, skill, attack_strength, defense_strength, battle_action, battle, out)
  once("tryMeleeAttackUnit", attacker, out)
  good("melee_chain", out.melee_attack_success)
end)
game.on("selectMoveSoundUnit", function(unit, walking_phase, unit_sound_index, tile_sound_index, base_tile_sound_index, base_tile_sound_offset, base_fly_sound_index, move, out)
  once("selectMoveSoundUnit", unit, out)
end)
'''

GEO = '''
game.log("S5 main")
local function seen(name)
  if done[name] then return false end
  done[name] = true
  game.log("S5SEEN", name)
  return true
end
local badDetect, badMonth = 0, 0
local want, expect = {}, {}
-- обнаружение настоящее: велим обратное тому, что сейчас, и на следующей проверке НЛО обязано перемениться
local function force(ufo, out)
  local id, now = ufo:getId(), ufo:getDetected()
  if expect[id] ~= nil and expect[id] == now and not done.flip then
    done.flip = true
    good("ufo_flip", now and "on" or "off")
  end
  if expect[id] == nil or expect[id] == now then expect[id] = not now end
  out.detection_type = expect[id] and game.DETECTION_RADAR or game.DETECTION_NONE
  out.detection_chance = expect[id] and 100 or 0
end
game.on("detectUfoFromBase", function(ufo, geoscape_game, distance, already_tracked, radar_total_strength, radar_max_distance, hyperwave_total_strength, hyperwave_max_distance, out)
  probes.ufo(ufo)
  probes.ruleUfo(ufo:getRuleUfo())
  probes.geoscape(geoscape_game, nil, "STR_ALIEN_ALLOYS")
  if seen("detectUfoFromBase") then
    good("detect_type", out.detection_type)
    good("detect_chance", out.detection_chance)
    bad("запись в обработчике только для чтения: detectUfoFromBase", function() geoscape_game:setTag("S5_GeoscapeGame", 1) end)
  end
  badDetect = badDetect + 1
  if badDetect == 2 then out.detection_type = 99 end
  if badDetect == 3 then out.detection_type = -1 end
  if badDetect > 3 then force(ufo, out) end
  -- месяц прошёл: финансирование стало таким, как задал обработчик
  if next(want) and not done.fundingSeen then
    done.fundingSeen = true
    local right, wrong = 0, 0
    for _, c in ipairs(geoscape_game:getCountries()) do
      local w = want[c:getRuleCountry():getType()]
      if w then
        if c:getCurrentFunding() == w then right = right + 1 else wrong = wrong + 1 end
      end
    end
    good("funding_after", right .. "/" .. wrong)
  end
end)
game.on("detectUfoFromCraft", function(ufo, geoscape_game, craft, distance, already_tracked, radar_total_strength, radar_max_distance, out)
  probes.craft(craft)
  probes.ruleCraft(craft:getRuleCraft())
  if seen("detectUfoFromCraft") then good("detect_craft_type", out.detection_type) end
  force(ufo, out)
end)
game.on("newMonthCountry", function(country, geoscape_game, totalXcomScore, totalAlienScore, out)
  seen("newMonthCountry")
  probes.country(country)
  probes.ruleCountry(country:getRuleCountry())
  good("month_country", country:getRuleCountry():getType() .. " " .. out.fundingChange .. " " .. out.satisfaction)
  badMonth = badMonth + 1
  if badMonth == 1 then
    bad("запись в обработчике только для чтения: newMonthCountry", function() geoscape_game:setTag("S5_GeoscapeGame", 1) end)
    out.satisfaction = 99
  elseif badMonth == 2 then
    out.satisfaction = -1
  else
    out.fundingChange = 7
    out.satisfaction = game.SATISFACTION_HAPPY
    out.formPact = 0
    if not country:getPact() then want[country:getRuleCountry():getType()] = country:getCurrentFunding() + 7 end
  end
end)
'''


BONUS_NAMES = [name for name in lua_api_doc.EVENTS if name.endswith("BonusStats")]
HOT = '''
local seen = {}
local function once(name)
  if seen[name] then return false end
  seen[name] = true
  game.log("S5SEEN", name)
  return true
end
-- обработчик без случайных чисел: запись, math.random и случайные методы
local function frozen(name, unit)
  if unit then bad("запись в обработчике только для чтения: " .. name, function() unit:addHealth(0) end) end
  bad("случайное число в обработчике: " .. name, function() return math.random(1, 2) end)
end
local BONUS = { %s }
for _, name in ipairs(BONUS) do
  game.on(name, function(unit, external_bonuses, weapon, ammo, battle_action, skill, out)
    if once(name) then
      frozen(name, unit)
      good("bonus_" .. name, out.bonus)
    end
  end)
end

-- восстановление: у одного юнита очки времени обнулены, бонус велит вернуть 3
local TU_UNIT
game.on("timeRecoveryBonusStats", function(unit, external_bonuses, weapon, ammo, battle_action, skill, out)
  if unit and unit:getId() == TU_UNIT then out.bonus = 3 end
end)

-- сила оружия: через раз ноль, hitUnit обязан увидеть его в orig_power
local zero = false
game.on("damageBonusBonusStats", function(unit, external_bonuses, weapon, ammo, battle_action, skill, out)
  zero = not zero
  if zero then out.bonus = 0 end
end)

-- патрон идёт перед юнитом, цепочка одна
local beforeHit, beforeDamage, beforeSpecial
game.on("hitUnitAmmo", function(unit, damaging_item, weapon_item, attacker, battle, skill, orig_power, damaging_type, battle_action, out)
  once("hitUnitAmmo")
  beforeHit = out.power
  out.power = out.power + 5
end)
game.on("hitUnit", function(unit, damaging_item, weapon_item, attacker, battle, skill, orig_power, damaging_type, battle_action, out)
  if damaging_item and beforeHit then
    good("ammo_hit_chain", out.power - beforeHit)
    beforeHit = nil
  end
  if weapon_item and damaging_item and battle_action ~= game.BA_HIT then
    game.log("S5POWER", zero and "zero" or "full", orig_power)
  end
end)
game.on("damageUnitAmmo", function(unit, damaging_item, weapon_item, attacker, battle, skill, currPower, orig_power, part, side, damaging_type, battle_action, out)
  once("damageUnitAmmo")
  beforeDamage = out.to_time
  out.to_time = out.to_time + 3
end)
game.on("damageUnit", function(unit, damaging_item, weapon_item, attacker, battle, skill, currPower, orig_power, part, side, damaging_type, battle_action, out)
  if damaging_item and beforeDamage then
    good("ammo_damage_chain", out.to_time - beforeDamage)
    beforeDamage = nil
  end
end)
game.on("damageSpecialUnitAmmo", function(unit, damaging_item, weapon_item, attacker, battle, skill, health_damage, orig_power, part, side, damaging_type, battle_action, out)
  once("damageSpecialUnitAmmo")
  beforeSpecial = out.morale_loss
  out.morale_loss = out.morale_loss + 2
end)
game.on("damageSpecialUnit", function(unit, damaging_item, weapon_item, attacker, battle, skill, health_damage, orig_power, part, side, damaging_type, battle_action, out)
  if damaging_item and beforeSpecial then
    good("ammo_special_chain", out.morale_loss - beforeSpecial)
    beforeSpecial = nil
  end
end)

-- реакция: оружие, действующий, реагирующий идут по порядку
local chance
game.on("reactionWeaponAction", function(action_unit, reaction_unit, reaction_weapon, reaction_battle_action, reaction_count, weapon, skill, battle_action, action_target, move, arc_to_action_unit, battle_game, out)
  once("reactionWeaponAction")
  good("reaction_weapon_distance", out.distance)
end)
game.on("reactionUnitAction", function(action_unit, reaction_unit, reaction_weapon, reaction_battle_action, reaction_count, weapon, skill, battle_action, action_target, move, arc_to_action_unit, battle_game, out)
  if once("reactionUnitAction") then
    bad("запись в обработчике только для чтения: reactionUnitAction", function() action_unit:addHealth(0) end)
    good("reaction_arc", arc_to_action_unit)
    good("reaction_side", action_unit:getFaction() ~= reaction_unit:getFaction())
  end
  out.reaction_chance = 37
end)
game.on("reactionUnitReaction", function(action_unit, reaction_unit, reaction_weapon, reaction_battle_action, reaction_count, weapon, skill, battle_action, action_target, move, arc_to_action_unit, battle_game, out)
  once("reactionUnitReaction")
  good("reaction_chain", out.reaction_chance)
  out.reaction_chance = 100
end)

-- видимость: с хода BLIND никто никого не видит
local BLIND, blind, shown = 8, false, 0
game.on("visibilityUnit", function(observer_unit, target_unit, target_tile, distance, distance_max, distance_target_max, smoke_density, fire_density, smoke_density_near_observer, fire_density_near_observer, out)
  if once("visibilityUnit") then
    frozen("visibilityUnit", observer_unit)
    good("visibility_default", out.default_visibility)
  end
  if target_unit and shown == 0 then
    shown = 1
    good("visibility_target", target_unit:getId() ~= observer_unit:getId())
  end
  if blind then out.current_visibility = 0 end
end)
game.on("aiCalculateTargetWeight", function(ai_unit, target_unit, battle_game, out)
  if once("aiCalculateTargetWeight") then
    bad("запись в обработчике только для чтения: aiCalculateTargetWeight", function() ai_unit:addHealth(0) end)
    good("ai_weight", out.default_target_weight)
  end
  out.current_target_weight = out.current_target_weight + 1
end)
game.on("newTurnUnit", function(unit, battle, turn, side)
  if side ~= unit:getFaction() then return end
  if turn >= BLIND then
    if not blind then game.log("S5VIS", "turn", turn, "before") end
    blind = true
  end
  if unit:isKilled() or unit:isStunned() then return end
  game.log("S5VIS", blind and "blind" or "open", unit:getVisibleUnitsCount())
  if side == game.FACTION_PLAYER then
    if TU_UNIT == nil then
      TU_UNIT = unit:getId()
      unit:setTimeUnits(0)
      good("tu_set", unit:getTimeUnits())
    elseif unit:getId() == TU_UNIT and not done.tu then
      done.tu = true
      good("tu_recovery", unit:getTimeUnits())
    end
  end
end)
''' % ", ".join(f'"{n}"' for n in BONUS_NAMES)

SCREENS = '''
local seen = {}
local function once(name)
  if seen[name] then return false end
  seen[name] = true
  game.log("S5SEEN", name)
  return true
end
local function frozen(name, geo)
  bad("запись в обработчике только для чтения: " .. name, function() geo:setTag("S5_GeoscapeGame", 1) end)
  bad("случайное число в обработчике: " .. name, function() return math.random(1, 2) end)
  bad("randomRange в обработчике: " .. name, function() return geo:randomRange(1, 2) end)
  bad("randomRangeSymmetric в обработчике: " .. name, function() return geo:randomRangeSymmetric(2) end)
  bad("randomChance в обработчике: " .. name, function() return geo:randomChance(50) end)
end
game.on("buyCostItem", function(item_rule, geoscape_game, difficulty_coefficient, out)
  if once("buyCostItem") then
    frozen("buyCostItem", geoscape_game)
    good("buy_coefficient", difficulty_coefficient)
  end
  out.cost_current = 7777
end)
game.on("sellCostItem", function(item_rule, geoscape_game, difficulty_coefficient, out)
  if once("sellCostItem") then
    frozen("sellCostItem", geoscape_game)
    good("sell_coefficient", difficulty_coefficient)
  end
  out.cost_current = 8888
end)
for _, name in ipairs({ "statsForNerdsItem", "statsForNerdsArmor", "statsForNerdsCraft", "statsForNerdsUfo" }) do
  game.on(name, function(rule, nerds, geoscape_game)
    if once(name) then frozen(name, geoscape_game) end
    probes.statsForNerds(nerds)
    nerds:addTextRow("S5 row", name)
  end)
end
'''


def mod_code(kinds, tail):
    return HEAD + "".join(probe_fn(k) for k in kinds) + tail


def add_tags(mods):
    d = mods / "s5/Ruleset"
    d.mkdir(parents=True, exist_ok=True)
    (d / "s5.rul").write_text(RUL, encoding="utf-8", newline="\n")


def api_lines(bench, name, kinds):
    """Строки S5API: метод -> ok/ERR. Журнал боя пишет через табуляцию или пробел."""
    res = {}
    for l in lines(bench, name, "S5API"):
        m = re.search(r"S5API\s+(\w+\.\w+)\s+(ok|ERR)\s*(.*)", l)
        if m:
            res.setdefault(m.group(1), (m.group(2), m.group(3)))
    return res


def report_methods(bench, name, kinds, may_fail=()):
    res = api_lines(bench, name, kinds)
    for kind in kinds:
        want = list(lua_api_doc.METHODS[kind])
        missed = [m for m in want if f"{kind}.{m}" not in res]
        wrong = [f"{m}: {res[f'{kind}.{m}'][1][:90]}" for m in want if f"{kind}.{m}" in res and res[f"{kind}.{m}"][0] == "ERR" and m not in may_fail]
        check(f"{kind}: все {len(want)} методов вызваны", not missed, str(missed[:12]))
        check(f"{kind}: без ошибок", not wrong, "; ".join(wrong[:12]))


def values(bench, name):
    res = {}
    for l in lines(bench, name, "S5VAL"):
        m = re.search(r"S5VAL\s+(\S+)\s+(.*)", l)
        if m:
            res.setdefault(m.group(1), m.group(2).strip())
    return res


def bads(bench, name):
    res = {}
    for l in lines(bench, name, "S5BAD"):
        m = re.search(r"S5BAD\s+(.*?)\s+(NOERR|error)\s*(.*)", l)
        if m:
            res.setdefault(m.group(1), (m.group(2), m.group(3)))
    return res


def report_bads(bench, name):
    for what, (verdict, text) in bads(bench, name).items():
        check("ошибка: " + what, verdict == "error", text[:110])


def battle():
    # страны есть только в кампании: они в случае geo
    kinds = ["unit", "battle", "tile", "ruleArmor", "geoscape", "country", "ruleCountry", "soldier", "ruleSoldier", "ruleUnit",
             "item", "ruleItem", "ruleDamage", "ruleSoldierBonus", "rules", "ruleResearch", "ruleInventory"]
    checked = [k for k in kinds if k not in ("ruleSoldierBonus", "country", "ruleCountry")]
    bench, mods, out = stand("api", mod_code(kinds, BATTLE))
    add_tags(mods)
    name = "s5api"
    run_stand(bench, name, mods, defects.battle_save(out))
    wanted = {"tryPsiAttackItem", "tryPsiAttackUnit", "tryMeleeAttackItem", "tryMeleeAttackUnit", "awardExperience", "selectMoveSoundUnit"}
    have = set()
    for t in range(int(os.environ.get("S5_TURNS", "12"))):
        bench.end_turn(name)
        have = {l.split("S5SEEN", 1)[1].strip() for l in lines(bench, name, "S5SEEN")}
        print("ход", t + 1, sorted(have), flush=True)
        if wanted <= have:
            break
    report_methods(bench, name, checked)
    v = values(bench, name)
    print(v, flush=True)
    check("список юнитов не пуст и сходится по сторонам", int(v.get("units_all", 0)) >= int(v.get("units_player", 0)) + int(v.get("units_hostile", 0)) > 0, str(v))
    check("список предметов не пуст", int(v.get("items_all", 0)) > 0)
    check("клетка за картой: nil", v.get("tile_outside") == "nilnilnil", v.get("tile_outside", ""))
    check("юнит стоит на своей клетке", v.get("unit_on_tile") == "true")
    check("дата игры читается", int(v.get("time_year", 0)) >= 1999, v.get("time_year", ""))
    check("setStat и addStat", v.get("stat_set") == "3" and v.get("stat_back") == "0", f"{v.get('stat_set')} {v.get('stat_back')}")
    check("setStat: верхняя граница 8000", v.get("stat_high") == "8000", v.get("stat_high", ""))
    check("setStat: нижняя граница 1", v.get("stat_low") == "1", v.get("stat_low", ""))
    check("раны за таблицей частей: ноль", v.get("wounds_max_outside") == "0", v.get("wounds_max_outside", ""))
    check("шанс удара идёт от оружия к цели", v.get("melee_chain") == "77", v.get("melee_chain", ""))
    check("пси-атака идёт от оружия к цели", v.get("psi_chain") == "77", v.get("psi_chain", ""))
    check("стоимость хода пишется", v.get("move_cost") == "7/9", v.get("move_cost", ""))
    check("правило находится по имени", v.get("rule_found") == "STR_ALIEN_ALLOYS", v.get("rule_found", ""))
    check("незнакомое правило: nil", v.get("rule_missing") == "nil", v.get("rule_missing", ""))
    check("правая рука: вид руки", v.get("inventory_hand") == "true", v.get("inventory_hand", ""))
    check("перенос между руками стоит ОВ", int(v.get("inventory_cost", -1)) >= 0, v.get("inventory_cost", ""))
    check("теги боя, геоскейпа, юнита", (v.get("tag_unit"), v.get("tag_battle"), v.get("tag_geo")) == ("41", "42", "43"))
    report_bads(bench, name)
    for ev in sorted(wanted):
        print(("ВЫЗВАН " if ev in have else "НЕ ВЫЗВАН ЗА ЭТОТ БОЙ ") + ev, flush=True)
    check("игра жива", bench.state(name)[0] in ("BattlescapeState", "NextTurnState"), bench.state(name)[0])
    errors = bench.folder(name) / "lua_errors.log"
    text = errors.read_text(encoding="utf-8", errors="replace") if errors.exists() else ""
    check("журнал ошибок мода пуст", not text, text[:400])
    bench.call("stop", "--name", name, timeout=60)


def geo():
    """Геоскейп: конец месяца и НЛО в кампании, ошибки выходов не ломают месяц."""
    kinds = ["ufo", "ruleUfo", "geoscape", "craft", "ruleCraft", "country", "ruleCountry"]
    bench, mods, out = stand("geo", mod_code(kinds, GEO))
    add_tags(mods)
    text = (GAME / "user/piratez/NoCodexCatZ.sav").read_text(encoding="utf-8")
    # конец месяца: только первая строка time, она у всего сейва
    text = re.sub(r"\ntime: \{second: \d+,minute: \d+,hour: \d+,weekday: \d+,day: \d+,month: 3,year: (\d+)\}",
                  lambda m: f"\ntime: {{second: 10,minute: 0,hour: 18,weekday: 2,day: 31,month: 3,year: {m.group(1)}}}", text, count=1)
    save = out / "geo.sav"
    save.write_text(text, encoding="utf-8", newline="\n")
    name = "s5geo"
    run_stand(bench, name, mods, save)
    t0 = time.time()
    seen = set()
    top = ""
    while time.time() - t0 < 240:
        top = bench.state(name)[0]
        seen = {l.split("S5SEEN", 1)[1].strip() for l in lines(bench, name, "S5SEEN")}
        v = values(bench, name)
        if "newMonthCountry" in seen and "detectUfoFromBase" in seen and "funding_after" in v and "ufo_flip" in v:
            break
        if top == "GeoscapeState":
            # часы на час за шаг: ускорение как у игрока
            bench.run(name, "key 53; wait 1500", 30)
        else:
            print("окно", top, flush=True)
            bench.run(name, "key 13; wait 500; key 27; wait 500", 30)
        time.sleep(0.5)
    print("видели", sorted(seen), top, flush=True)
    check("месяц закончился", "newMonthCountry" in seen)
    check("база пробовала заметить НЛО", "detectUfoFromBase" in seen)
    report_methods(bench, name, ["ufo", "ruleUfo", "country", "ruleCountry"])
    # geoscape здесь только читает: setTag в этом обработчике обязан дать ошибку, тег проверен в бою
    report_methods(bench, name, ["geoscape"], {"setTag"})
    if "detectUfoFromCraft" in seen:
        report_methods(bench, name, ["craft", "ruleCraft"])
    else:
        print("НЕ ПРОВЕРЕНО: корабль за это время не пробовал заметить НЛО", flush=True)
    v = values(bench, name)
    print(v, flush=True)
    report_bads(bench, name)
    errors = bench.folder(name) / "lua_errors.log"
    text = errors.read_text(encoding="utf-8", errors="replace") if errors.exists() else ""
    check("выход обнаружения меняет игру", v.get("ufo_flip") in ("on", "off"), v.get("ufo_flip", ""))
    right, _, wrong = v.get("funding_after", "0/1").partition("/")
    check("выход месяца меняет финансирование", int(right) > 0 and wrong == "0", v.get("funding_after", ""))
    check("неверный detection_type: две ошибки в журнале", text.count("detection_type") == 2, str(text.count("detection_type")))
    check("неверный satisfaction: две ошибки в журнале", text.count("satisfaction") == 2, str(text.count("satisfaction")))
    check("игра жива", bench.state(name)[0] != "none", bench.state(name)[0])
    bench.call("stop", "--name", name, timeout=60)


def hot():
    """Обработчики, которые идут часто: бонусы, реакция, видимость, вес цели, и патрон перед юнитом."""
    bench, mods, out = stand("hot", mod_code([], HOT))
    add_tags(mods)
    name = "s5hot"
    run_stand(bench, name, mods, defects.battle_save(out))
    wanted = {"hitUnitAmmo", "damageUnitAmmo", "damageSpecialUnitAmmo", "reactionUnitAction", "reactionUnitReaction", "visibilityUnit",
              "timeRecoveryBonusStats", "energyRecoveryBonusStats", "moraleRecoveryBonusStats", "healthRecoveryBonusStats", "manaRecoveryBonusStats", "stunRecoveryBonusStats",
              "accuracyMultiplierBonusStats", "damageBonusBonusStats"}
    have = set()
    for t in range(int(os.environ.get("S5_TURNS", "20"))):
        print("ход", t + 1, "секунд", round(bench.end_turn(name), 1), flush=True)
        have = {l.split("S5SEEN", 1)[1].strip() for l in lines(bench, name, "S5SEEN")}
        if wanted <= have and t >= 9:
            break
    print("видели", sorted(have), flush=True)
    for ev in sorted(wanted):
        check("вызван " + ev, ev in have)
    all_events = {n for n in lua_api_doc.EVENTS if n.endswith("BonusStats")} | {"reactionWeaponAction", "aiCalculateTargetWeight"}
    for ev in sorted(all_events - wanted - have):
        print("НЕ ВЫЗВАН ЗА ЭТОТ БОЙ " + ev, flush=True)
    v = values(bench, name)
    print(v, flush=True)
    check("правила читаются и пока грузится main.lua", v.get("rule_at_load") == "STR_ALIEN_ALLOYS", v.get("rule_at_load", ""))
    check("патрон перед юнитом: hitUnit", v.get("ammo_hit_chain") == "5", v.get("ammo_hit_chain", ""))
    check("патрон перед юнитом: damageUnit", v.get("ammo_damage_chain") == "3", v.get("ammo_damage_chain", ""))
    check("патрон перед юнитом: damageSpecialUnit", v.get("ammo_special_chain") == "2", v.get("ammo_special_chain", ""))
    check("шанс реакции идёт по цепочке", v.get("reaction_chain") == "37", v.get("reaction_chain", ""))
    check("реагирует чужая сторона", v.get("reaction_side") == "true", v.get("reaction_side", ""))
    check("бонус восстановления меняет игру: вместо полного запаса почти ничего", v.get("tu_set") == "0" and 3 <= int(v.get("tu_recovery", -1)) < 10, f"{v.get('tu_set')} {v.get('tu_recovery')}, обычно {v.get('bonus_timeRecoveryBonusStats')}")
    power = [l.split("S5POWER", 1)[1].split() for l in lines(bench, name, "S5POWER")]
    zero = [int(p[1]) for p in power if p[0] == "zero"]
    full = [int(p[1]) for p in power if p[0] == "full"]
    print("сила: при нуле", zero[:20], "без него", full[:20], flush=True)
    # ноль движок поднимает до единицы
    check("бонус силы меняет игру", bool(zero) and max(zero) <= 1 and max(full, default=0) > 1, f"{len(zero)} {len(full)}")
    vis = [l.split("S5VIS", 1)[1].split() for l in lines(bench, name, "S5VIS")]
    opened = [int(x[1]) for x in vis if x[0] == "open"]
    blinded = [int(x[1]) for x in vis if x[0] == "blind"]
    # первая строка слепого хода могла посчитаться до нового обзора: смотрим со второго хода слепоты
    tail_blind = blinded[len(blinded) // 2:]
    print("видит: обычный ход сумма", sum(opened), "слепой", sum(blinded), "вторая половина", sum(tail_blind), flush=True)
    check("видимость меняет игру", sum(opened) > 0 and bool(tail_blind) and sum(tail_blind) == 0, f"{sum(opened)} {sum(tail_blind)} {len(tail_blind)}")
    report_bads(bench, name)
    check("игра жива", bench.state(name)[0] in ("BattlescapeState", "NextTurnState"), bench.state(name)[0])
    errors = bench.folder(name) / "lua_errors.log"
    text = errors.read_text(encoding="utf-8", errors="replace") if errors.exists() else ""
    check("журнал ошибок мода пуст", not text, text[:400])
    bench.call("stop", "--name", name, timeout=60)


def screens():
    """Цены и страницы для нердов на настоящих экранах: нажатия в координатах базы 480x270."""
    bench, mods, out = stand("screens", mod_code(["statsForNerds"], SCREENS))
    add_tags(mods)
    save = out / "screens.sav"
    shutil.copyfile(GAME / "user/piratez/NoCodexCatZ.sav", save)
    name = "s5scr"
    run_stand(bench, name, mods, save)
    t0 = time.time()
    while time.time() - t0 < 60:
        top = bench.state(name)[0]
        if top == "GeoscapeState" and time.time() - t0 > 8:
            break
        if top != "GeoscapeState":
            bench.run(name, "key 13; wait 800", 30)
        time.sleep(0.5)
    def go(cmds, want):
        res = bench.run(name, cmds, 120)
        top = bench.state(name)[0]
        check("экран " + want, top == want, top + " " + res[-200:])
    # вверху списков люди, цены предметов в конце
    go(f"key 98; wait 2500; click 335,202; wait 2500; rclick 385,196; wait 800; shot {out / 'buy.png'}", "PurchaseState")
    go(f"key 27; wait 1500; click 335,215; wait 2500; rclick 385,196; wait 800; shot {out / 'sell.png'}", "SellState")
    go("key 27; wait 1500; click 335,202; wait 2000; rclick 385,196; wait 800; mclick 140,159; wait 2500", "ArticleStateItem")
    go(f"key 117; wait 2500; rclick 385,196; wait 800; shot {out / 'nerds_item.png'}", "StatsForNerdsState")
    go("key 27; wait 800; key 27; wait 800; key 27; wait 800; key 27; wait 1500; key 117; wait 2500", "UfopaediaStartState")
    # разделы педии Пираток: корабли, чужие корабли; броня ниже людей в списке второго раздела
    go("click 240,58; wait 1800; click 240,117; wait 1800", "ArticleStateCraft")
    go(f"key 117; wait 1800; rclick 385,196; wait 800; shot {out / 'nerds_craft.png'}", "StatsForNerdsState")
    go("key 27; wait 800; key 27; wait 800; key 27; wait 1000; click 240,175; wait 1800; click 240,100; wait 1800", "ArticleStateUfo")
    go(f"key 117; wait 1800; rclick 385,196; wait 800; shot {out / 'nerds_ufo.png'}", "StatsForNerdsState")
    go("key 27; wait 800; key 27; wait 800; key 27; wait 1000; click 240,71; wait 1800; rclick 354,194; wait 1000", "UfopaediaSelectState")
    for y in range(69, 200, 8):
        bench.run(name, f"click 240,{y}; wait 1200", 30)
        top = bench.state(name)[0]
        if top == "ArticleStateArmor":
            break
        if top != "UfopaediaSelectState":
            bench.run(name, "key 27; wait 800", 30)
    check("экран ArticleStateArmor", top == "ArticleStateArmor", top)
    go(f"key 117; wait 1800; rclick 385,196; wait 800; shot {out / 'nerds_armor.png'}", "StatsForNerdsState")
    have = {l.split("S5SEEN", 1)[1].strip() for l in lines(bench, name, "S5SEEN")}
    print("видели", sorted(have), flush=True)
    for ev in ("buyCostItem", "sellCostItem", "statsForNerdsItem", "statsForNerdsCraft", "statsForNerdsUfo", "statsForNerdsArmor"):
        check("вызван " + ev, ev in have)
    report_methods(bench, name, ["statsForNerds"])
    report_bads(bench, name)
    v = values(bench, name)
    print(v, flush=True)
    check("коэффициент цены приходит", int(v.get("buy_coefficient", 0)) > 0 and int(v.get("sell_coefficient", 0)) > 0, str(v))
    errors = bench.folder(name) / "lua_errors.log"
    text = errors.read_text(encoding="utf-8", errors="replace") if errors.exists() else ""
    check("журнал ошибок мода пуст", not text, text[:400])
    check("игра жива", bench.state(name)[0] != "none", bench.state(name)[0])
    bench.call("stop", "--name", name, timeout=60)


UI_CODE = """
local added = {}
game.screen("all", function(ui)
  try("ui.window", function() return ui:window{ x = 10, y = 6, w = 300, h = 188, background = "BACK01.SCR" } end)
  local t, b, g, l, c, e, s, i
  try("ui.text", function() t = ui:text{ x = 20, y = 12, w = 200, h = 10, text = "S5", big = false, align = "center", wrap = true, color = 133 } return t end)
  try("ui.toggleButton", function() g = ui:toggleButton{ x = 20, y = 30, w = 100, h = 16, text = "S5", pressed = true, onClick = function() end } return g end)
  try("ui.list", function() l = ui:list{ x = 130, y = 30, w = 160, h = 60, columns = { 80, 70 }, selectable = true, onClick = function() end } return l end)
  try("ui.comboBox", function() c = ui:comboBox{ x = 130, y = 100, w = 160, h = 16, options = { "a", "b" }, selected = 2, onChange = function() end } return c end)
  try("ui.edit", function() e = ui:edit{ x = 20, y = 50, w = 100, h = 10, text = "S5", focus = false, onChange = function() end, onEnter = function() end } return e end)
  try("ui.slider", function() s = ui:slider{ x = 20, y = 70, w = 100, h = 16, min = 0, max = 10, value = 5, onChange = function() end } return s end)
  try("ui.image", function() i = ui:image{ x = 20, y = 100, image = "BACK01.SCR", onClick = function() end } return i end)
  try("ui.onKey", function() ui:onKey(function() end) end)
  try("ui.onClose", function() ui:onClose(function() end) end)
  try("uiWidget.setVisible", function() t:setVisible(true) end)
  try("uiWidget.isVisible", function() return t:isVisible() end)
  try("uiWidget.setText", function() t:setText("S5 2") end)
  try("uiWidget.getText", function() return t:getText() end)
  try("uiWidget.setPressed", function() g:setPressed(false) end)
  try("uiWidget.isPressed", function() return g:isPressed() end)
  try("uiWidget.addRow", function() l:addRow("a", "b") end)
  try("uiWidget.setCell", function() l:setCell(1, 2, "c") end)
  try("uiWidget.getRowCount", function() return l:getRowCount() end)
  try("uiWidget.getSelected", function() return l:getSelected() end)
  try("uiWidget.clearList", function() l:clearList() end)
  try("uiWidget.setOptions", function() c:setOptions({ "x", "y", "z" }) end)
  try("uiWidget.setSelected", function() c:setSelected(3) end)
  try("uiWidget.getValue", function() return s:getValue() end)
  try("uiWidget.setValue", function() s:setValue(3) end)
  try("uiWidget.setRange", function() s:setRange(0, 5) end)
  try("uiWidget.setFocus", function() e:setFocus() end)
  try("uiWidget.setImage", function() i:setImage("BACK01.SCR") end)
  bad("запись при построении", function() game.getGeoscape():setTag("S5_GeoscapeGame", 1) end)
  bad("случайное число при построении", function() return math.random(1, 2) end)
  try("ui.button", function() b = ui:button{ x = 20, y = 170, w = 280, h = 18, text = "S5", onClick = function()
    try("ui.close", function() ui:close() end)
    good("click_battle", game.getBattle() ~= nil)
    good("click_geoscape", game.getGeoscape() ~= nil)
  end } return b end)
end, { menu = "S5 all" })
"""


def ui():
    """Все методы экрана на странице автора, в настоящем бою; мод с luaApi: 2 и luaCaps: [screens]."""
    bench, mods, out = stand("ui", HEAD + UI_CODE)
    add_tags(mods)
    (mods / "s5/metadata.yml").write_text('id: s5\nname: "s5"\nversion: 0.1\nmaster: "piratez"\nluaApi: 2\nluaCaps: [screens]\n', encoding="utf-8", newline="\n")
    name = "s5ui"
    run_stand(bench, name, mods, defects.battle_save(out))
    # кадр мира 480x270, окно 320x200 смещено на (80, 35); первая строка списка, кнопка внизу:
    # поле в фокусе модально, первый щелчок только снимает фокус
    bench.run(name, "wait 800; key 111; wait 400; click 230,91; wait 500; click 180,214; wait 300; click 180,214; wait 400", 40)
    top = bench.state(name)[0]
    check("экран закрылся кнопкой мода", top == "LuaModsState", top)
    report_methods(bench, name, ["ui", "uiWidget"])
    report_bads(bench, name)
    v = values(bench, name)
    check("из щелчка видны бой и кампания", v.get("click_battle") == "true" and v.get("click_geoscape") == "true", str(v))
    errors = bench.folder(name) / "lua_errors.log"
    text = errors.read_text(encoding="utf-8", errors="replace") if errors.exists() else ""
    check("журнал ошибок мода пуст", not text, text[:400])
    bench.call("stop", "--name", name, timeout=60)


def bonus():
    """applySoldierBonuses только при входе в бой: загруженный сейв боя его не вызывает, нужна посадка из кампании."""
    kinds = ["ruleSoldierBonus"]
    tail = '''
game.on("applySoldierBonuses", function(unit, battle, bonus)
  probes.ruleSoldierBonus(bonus, unit)
  if not done.applied then
    done.applied = true
    local h = unit:getStat("health")
    unit:addStat("health", 1)
    good("bonus_stat", unit:getStat("health") - h)
    unit:addStat("health", -1)
  end
end)
for _, what in ipairs({ "time", "energy", "morale", "health", "mana", "stun" }) do
  local ev = what .. "SoldierRecoveryBonusStats"
  game.on(ev, function(...)
    if not done[ev] then
      done[ev] = true
      game.log("S5SEEN", ev)
    end
  end)
end
'''
    bench, mods, out = stand("bonus", mod_code(kinds, tail))
    add_tags(mods)
    name = "s5bonus"
    run_stand(bench, name, mods, defects.geoscape_save(out))
    defects.wait_landing(bench, name)
    defects.land(bench, name)
    report_methods(bench, name, kinds)
    # восстановление от бонуса солдата считается в начале хода, у солдат кампании бонусы настоящие
    t0 = time.time()
    while bench.state(name)[0] != "BattlescapeState" and time.time() - t0 < 60:
        # брифинг закрывает Enter, снаряжение перед боем - Esc
        bench.run(name, ("key 27" if bench.state(name)[0] == "InventoryState" else "key 13") + "; wait 1000", 30)
    check("бой открылся", bench.state(name)[0] == "BattlescapeState", bench.state(name)[0])
    for t in range(3):
        bench.end_turn(name, limit=60)
    have ={l.split("S5SEEN", 1)[1].strip() for l in lines(bench, name, "S5SEEN")}
    print("видели", sorted(have), flush=True)
    for what in ("time", "energy", "morale", "health", "mana", "stun"):
        check("вызван " + what + "SoldierRecoveryBonusStats", what + "SoldierRecoveryBonusStats" in have)
    check("в бонусе можно менять юнита", values(bench, name).get("bonus_stat") == "1", str(values(bench, name)))
    errors = bench.folder(name) / "lua_errors.log"
    text = errors.read_text(encoding="utf-8", errors="replace") if errors.exists() else ""
    check("журнал ошибок мода пуст", not text, text[:400])
    bench.call("stop", "--name", name, timeout=60)


def cost():
    """Сколько стоит перебор. В песочнице нет часов, поэтому один и тот же ход с мерой и без неё: самый плохой случай, getItems в каждом newTurnItem. R-091."""
    code = '''
local first
game.on("newTurnItem", function(item, battle, turn, side)
  if HEAVY_TURN ~= turn then return end
  local items = battle:getItems()
  if not first then
    first = true
    game.log("S5COST", "items", #items, "units", #battle:getUnits())
  end
  game.log("S5COSTN", #items)
end)
'''
    # 1 ход: без меры; 2 ход: перебор на каждом предмете; 3 ход: снова без меры
    code = "local HEAVY_TURN = 2\n" + code
    bench, mods, out = stand("cost", code)
    name = "s5cost"
    run_stand(bench, name, mods, defects.battle_save(out))
    for t in range(1, 5):
        print("ход", t, "секунд", round(bench.end_turn(name), 1), flush=True)
    found = lines(bench, name, "S5COSTN")
    print(lines(bench, name, "S5COST\t")[:1] or lines(bench, name, "S5COST ")[:1], "вызовов getItems", len(found), flush=True)
    errors = bench.folder(name) / "lua_errors.log"
    print(errors.read_text(encoding="utf-8", errors="replace")[:600] if errors.exists() else "ошибок нет", flush=True)
    bench.call("stop", "--name", name, timeout=60)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ["OXCE_HIDDEN_DATA"] = str(GAME)
    os.environ["PATH"] = "C:/msys64/mingw64/bin;" + os.environ["PATH"]
    cases = {"battle": battle, "hot": hot, "screens": screens, "geo": geo, "bonus": bonus, "cost": cost, "ui": ui}
    for key in sys.argv[1:] or cases:
        cases[key]()
    print("ИТОГ:", "всё прошло" if not failed else f"провалов {len(failed)}: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
