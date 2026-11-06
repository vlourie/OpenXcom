# API после самопроверки 06.11 в настоящей игре, всё невидимо: каждый метод вызывается хотя бы раз, отрицательные случаи, редкие обработчики.
# Список методов берётся из tools/lua_api_doc.py, поэтому новый метод без строки здесь сразу виден как «не вызван».
# Запуск: py -3.13 tools/lua_stage5/api.py [battle|geo|cost]; без аргумента все три
import os, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lua_api_doc
import defects
from defects import DAMAGE, GAME, HERE, check, failed, lines, run_stand, stand

TAG_SECTIONS = ["BattleUnit", "BattleItem", "BattleGame", "GeoscapeGame", "GeoscapeSoldier", "Country", "Ufo", "Craft",
                "RuleArmor", "RuleItem", "RuleSoldier", "RuleSoldierBonus", "RuleUfo", "RuleCraft"]
# имя тега одно на всю игру: одинаковое в двух разделах движок отбрасывает
RUL = "extended:\n  tags:\n" + "".join(f"    {s}:\n      S5_{s}: int\n" for s in TAG_SECTIONS)
TAG_OF = {"unit": "BattleUnit", "item": "BattleItem", "battle": "BattleGame", "geoscape": "GeoscapeGame", "soldier": "GeoscapeSoldier", "country": "Country",
          "ufo": "Ufo", "craft": "Craft", "ruleArmor": "RuleArmor", "ruleItem": "RuleItem", "ruleSoldier": "RuleSoldier", "ruleSoldierBonus": "RuleSoldierBonus",
          "ruleUfo": "RuleUfo", "ruleCraft": "RuleCraft"}

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
             "item", "ruleItem", "ruleDamage", "ruleSoldierBonus"]
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
'''
    bench, mods, out = stand("bonus", mod_code(kinds, tail))
    add_tags(mods)
    name = "s5bonus"
    run_stand(bench, name, mods, defects.geoscape_save(out))
    defects.wait_landing(bench, name)
    defects.land(bench, name)
    report_methods(bench, name, kinds)
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
    cases = {"battle": battle, "geo": geo, "bonus": bonus, "cost": cost}
    for key in sys.argv[1:] or cases:
        cases[key]()
    print("ИТОГ:", "всё прошло" if not failed else f"провалов {len(failed)}: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
