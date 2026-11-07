# -*- coding: utf-8 -*-
"""Документация Lua API для авторов модов: русская и английская страницы из таблиц движка.

Что есть в API, берётся только из C++: таблицы *_METHODS, EVENTS и CONSTANTS в src/Mod/LuaHost.cpp, вызовы
lua->fire(...) по исходникам, BASE_ALLOWED и лимиты песочницы. Здесь лежат только слова о них. Метод без описания,
описание без метода, другое число аргументов у обработчика: сборка страницы останавливается, а не молчит.

py -3 tools/lua_api_doc.py          собрать portal/src/Xp.Launcher.Core/Docs/lua_api.{ru,en}.html
py -3 tools/lua_api_doc.py --check  только сверить, что страницы совпадают с тем, что дала бы сборка
"""
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = ROOT / "src/Mod/LuaHost.cpp"
HOST_H = ROOT / "src/Mod/LuaHost.h"
SANDBOX = ROOT / "src/Engine/LuaSandbox.cpp"
SANDBOX_H = ROOT / "src/Engine/LuaSandbox.h"
OUT = ROOT / "portal/src/Xp.Launcher.Core/Docs"

# имя таблицы в C++ -> заголовок и как метод пишется в коде мода
TYPES = {
    "UNIT": ("unit", "Юнит", "Unit"),
    "UI": ("ui", "Экран мода, luaCaps: screens", "A mod's screen, luaCaps: screens"),
    "UI_WIDGET": ("uiWidget", "Виджет экрана мода", "A widget of a mod's screen"),
    "ITEM": ("item", "Предмет", "Item"),
    "BATTLE": ("battle", "Бой", "Battle"),
    "BASE": ("base", "База, game.getBases()", "A base, game.getBases()"),
    "SOLDIER": ("soldier", "Солдат", "Soldier"),
    "RULE_ARMOR": ("ruleArmor", "Правила брони", "Armor rules"),
    "RULE_ITEM": ("ruleItem", "Правила предмета", "Item rules"),
    "SKILL": ("skill", "Навык", "Skill"),
    "TILE": ("tile", "Клетка карты", "Map tile"),
    "GEOSCAPE": ("geoscape", "Геоскейп", "Geoscape"),
    "COUNTRY": ("country", "Страна", "Country"),
    "UFO": ("ufo", "НЛО", "UFO"),
    "CRAFT": ("craft", "Корабль", "Craft"),
    "RULE_DAMAGE": ("ruleDamage", "Правила типа урона", "Damage type rules"),
    "RULE_UNIT": ("ruleUnit", "Правила юнита", "Unit rules"),
    "RULE_SOLDIER": ("ruleSoldier", "Правила солдата", "Soldier rules"),
    "RULE_BONUS": ("ruleSoldierBonus", "Правила бонуса солдата", "Soldier bonus rules"),
    "RULE_COUNTRY": ("ruleCountry", "Правила страны", "Country rules"),
    "RULE_UFO": ("ruleUfo", "Правила НЛО", "UFO rules"),
    "RULE_CRAFT": ("ruleCraft", "Правила корабля", "Craft rules"),
    "RULE_RESEARCH": ("ruleResearch", "Правила исследования", "Research rules"),
    "RULE_INVENTORY": ("ruleInventory", "Правила ячейки инвентаря", "Inventory slot rules"),
    "RULES": ("rules", "Все правила игры", "All the game's rules"),
    "NERDS": ("statsForNerds", "Страница для нердов", "The stats for nerds page"),
}

# слова luaCaps: открытые и закрытые до своего этапа docs/portal/LUA_MODS_V2.md
CAPS = ("screens", "economy")
CLOSED_CAPS = ("spawn",)
# обработчики только для luaApi: 2, в движке namesApi1 их не знает
API2_EVENTS = ("newHour", "newDay", "newMonth", "battleStart", "battleEnd")

# имена характеристик для getStat, setStat, addStat, getExp
STATS_RU = "timeUnits, stamina, health, manaPool, bravery, reactions, firing, throwing, strength, psiStrength, psiSkill, melee"
CRAFT_STATS = ("fuelMax, damageMax, speedMax, accel, radarRange, radarChance, sightRange, hitBonus, avoidBonus, avoidBonus2, powerBonus, armor, "
               "shieldCapacity, shieldRecharge, shieldRechargeInGeoscape, shieldBleedThrough, maxUnits, maxVehiclesAndLargeSoldiers, maxItems")

# метод: (аргументы, по-русски, по-английски)
METHODS = {
    "unit": {
        "getId": ("", "номер юнита в бою", "the unit's number in the battle"),
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getRank": ("", "звание, целое", "the rank, a whole number"),
        "getFaction": ("", "сторона сейчас, FACTION_*", "the side now, FACTION_*"),
        "getOriginalFaction": ("", "сторона до контроля разума, FACTION_*", "the side before mind control, FACTION_*"),
        "isKilled": ("", "убит", "killed"),
        "isStunned": ("", "оглушён", "stunned"),
        "isKneeled": ("", "на колене", "kneeling"),
        "isFloating": ("", "летит", "flying"),
        "getDirection": ("", "направление, от 0 до 7", "the direction, 0 to 7"),
        "getPosition": ("", "три значения: x, y, z", "three values: x, y, z"),
        "getTimeUnits": ("", "ОВ сейчас", "time units now"),
        "getTimeUnitsMax": ("", "ОВ, максимум", "time units, the maximum"),
        "setTimeUnits": ("value", "задать ОВ", "set time units"),
        "addTimeUnits": ("value", "прибавить ОВ", "add time units"),
        "getHealth": ("", "здоровье сейчас", "health now"),
        "getHealthMax": ("", "здоровье, максимум", "health, the maximum"),
        "setHealth": ("value", "задать здоровье", "set health"),
        "addHealth": ("value", "прибавить здоровье", "add health"),
        "setHealthWithOverkill": ("value", "задать здоровье, разрешая уйти ниже нуля", "set health, allowing it to go below zero"),
        "addHealthWithOverkill": ("value", "прибавить здоровье, разрешая уйти ниже нуля", "add health, allowing it to go below zero"),
        "getOverKillDamage": ("", "на сколько здоровье ушло ниже нуля", "how far health went below zero"),
        "getMana": ("", "мана сейчас", "mana now"),
        "getManaMax": ("", "мана, максимум", "mana, the maximum"),
        "setMana": ("value", "задать ману", "set mana"),
        "addMana": ("value", "прибавить ману", "add mana"),
        "getEnergy": ("", "энергия сейчас", "energy now"),
        "getEnergyMax": ("", "энергия, максимум", "energy, the maximum"),
        "setEnergy": ("value", "задать энергию", "set energy"),
        "addEnergy": ("value", "прибавить энергию", "add energy"),
        "getStun": ("", "оглушение сейчас", "stun now"),
        "getStunMax": ("", "оглушение, максимум", "stun, the maximum"),
        "setStun": ("value", "задать оглушение", "set stun"),
        "addStun": ("value", "прибавить оглушение", "add stun"),
        "getMorale": ("", "боевой дух", "morale"),
        "setMorale": ("value", "задать боевой дух", "set morale"),
        "addMorale": ("value", "прибавить боевой дух", "add morale"),
        "getFire": ("", "сколько ходов ещё горит", "how many turns it still burns"),
        "setFire": ("value", "задать, сколько ходов горит", "set how many turns it burns"),
        "getArmor": ("side", "броня стороны SIDE_* сейчас", "the armor of side SIDE_* now"),
        "getArmorMax": ("side", "броня стороны SIDE_*, максимум", "the armor of side SIDE_*, the maximum"),
        "setArmor": ("side, value", "задать броню стороны", "set the armor of a side"),
        "addArmor": ("side, value", "прибавить броню стороны", "add to the armor of a side"),
        "getFatalwoundsTotal": ("", "раны на всём теле", "wounds on the whole body"),
        "getFatalwounds": ("part", "раны на части тела BODYPART_*", "wounds on body part BODYPART_*"),
        "setFatalwounds": ("part, value", "задать раны на части тела", "set the wounds on a body part"),
        "addFatalwounds": ("part, value", "прибавить раны на части тела", "add wounds on a body part"),
        "getRightHandWeapon": ("", "предмет в правой руке или nil", "the item in the right hand, or nil"),
        "getLeftHandWeapon": ("", "предмет в левой руке или nil", "the item in the left hand, or nil"),
        "getRuleArmor": ("", "правила брони или nil", "the armor rules, or nil"),
        "getTag": ("name", "значение тега BattleUnit", "the value of a BattleUnit tag"),
        "setTag": ("name, value", "записать тег BattleUnit", "write a BattleUnit tag"),
        "getRankUnified": ("", "звание, одинаковая для всех сторон шкала UNIT_RANK_*", "the rank on the scale common to all sides, UNIT_RANK_*"),
        "getGender": ("", "пол, GENDER_*", "the gender, GENDER_*"),
        "getLook": ("", "внешность солдата, LOOK_*; не солдат: 0", "the soldier's look, LOOK_*; not a soldier: 0"),
        "getLookVariant": ("", "вариант внешности солдата; не солдат: 0", "the variant of the soldier's look; not a soldier: 0"),
        "isStanding": ("", "стоит и ничего не делает", "stands idle"),
        "isWalking": ("", "идёт", "walking"),
        "isFlying": ("", "летит сейчас, в движении", "flying right now, in motion"),
        "isCollapsing": ("", "падает", "collapsing"),
        "isAiming": ("", "целится", "aiming"),
        "isFearable": ("", "боится", "can be scared"),
        "isWoundable": ("", "может получать раны", "can get wounds"),
        "getReactionScore": ("", "очки реакции, целая часть", "the reaction score, the whole part"),
        "getIntelligence": ("", "интеллект", "intelligence"),
        "getAggression": ("", "агрессия", "aggression"),
        "getTurretDirection": ("", "направление башни", "the turret direction"),
        "getWalkingPhase": ("", "фаза ходьбы", "the walking phase"),
        "disableIndicators": ("", "скрыть индикаторы юнита", "hide the unit's indicators"),
        "isVisible": ("", "виден игроку", "visible to the player"),
        "makeVisible": ("", "сделать видимым игроку", "make visible to the player"),
        "getMaxViewDistanceAtDark": ("other", "дальность зрения в темноте по юниту other", "the view distance in the dark, towards unit other"),
        "getMaxViewDistanceAtDay": ("other", "дальность зрения днём по юниту other", "the view distance by day, towards unit other"),
        "getMaxViewDistance": ("base, nerf, buff", "дальность зрения с данным обзором, маскировкой и антимаскировкой", "the view distance with this base, camouflage and anti-camouflage"),
        "getPsiVision": ("", "пси-зрение", "psi vision"),
        "getHeatVision": ("", "зрение сквозь дым", "vision through smoke"),
        "getVisibilityThroughFire": ("", "зрение сквозь огонь", "vision through fire"),
        "setSpawnUnit": ("type", "в кого превратится при гибели: тип из рулсета или nil. Незнакомый тип: ошибка", "what it turns into when it dies: a type from the ruleset or nil. An unknown type is an error"),
        "getSpawnUnit": ("", "правила юнита, в которого превратится, или nil", "the rules of the unit it turns into, or nil"),
        "setSpawnUnitInstantRespawn": ("value", "1: превращение сразу, 0: при гибели", "1: it turns at once, 0: when it dies"),
        "getSpawnUnitInstantRespawn": ("", "превращение сразу", "it turns at once"),
        "setSpawnUnitFaction": ("value", "сторона после превращения", "the side after turning"),
        "getSpawnUnitFaction": ("", "сторона после превращения", "the side after turning"),
        "getPreviousOwner": ("", "кто последним был носителем, юнит или nil", "who carried it last, a unit or nil"),
        "getMoraleMax": ("", "боевой дух, максимум", "morale, the maximum"),
        "setArmorMax": ("side, value", "задать максимум брони стороны; сторона за границей: ничего", "set the maximum armor of a side; a side outside the range: nothing"),
        "getFatalwoundsMax": ("part", "сколько ран может быть на части тела; за таблицей частей 0", "how many wounds a body part can hold; outside the table of parts 0"),
        "getMovementType": ("", "способ передвижения сейчас, MT_*", "the movement type now, MT_*"),
        "getOriginalMovementType": ("", "способ передвижения от брони, MT_*", "the movement type from the armor, MT_*"),
        "setMovementType": ("value", "задать способ передвижения, MT_*", "set the movement type, MT_*"),
        "getVisibleUnitsCount": ("", "сколько юнитов видит", "how many units it sees"),
        "getRuleUnit": ("", "правила юнита или nil", "the unit rules, or nil"),
        "getRuleSoldier": ("", "правила солдата или nil", "the soldier rules, or nil"),
        "getGeoscapeSoldier": ("", "солдат игрока или nil", "the player's soldier, or nil"),
        "reduceByBravery": ("value", "значение, уменьшенное храбростью юнита", "the value reduced by the unit's bravery"),
        "reduceByResistance": ("value, type", "значение, уменьшенное сопротивлением брони типу урона DT_*", "the value reduced by the armor's resistance to damage type DT_*"),
        "getTurnsSinceSpotted": ("", "сколько ходов назад его заметили враги", "how many turns ago the enemies spotted it"),
        "setTurnsSinceSpotted": ("value", "задать, от 0 до 255", "set it, 0 to 255"),
        "getTurnsSinceSpottedByFaction": ("faction", "то же для стороны FACTION_*", "the same for side FACTION_*"),
        "setTurnsSinceSpottedByFaction": ("faction, value", "задать для стороны FACTION_*", "set it for side FACTION_*"),
        "getTurnsLeftSpottedForSnipers": ("", "сколько ходов снайперы врага ещё его видят", "for how many turns enemy snipers still see it"),
        "setTurnsLeftSpottedForSnipers": ("value", "задать, от 0 до 255", "set it, 0 to 255"),
        "getTurnsLeftSpottedForSnipersByFaction": ("faction", "то же для стороны FACTION_*", "the same for side FACTION_*"),
        "setTurnsLeftSpottedForSnipersByFaction": ("faction, value", "задать для стороны FACTION_*", "set it for side FACTION_*"),
        "getDisplayShieldHp": ("", "щит на индикаторе", "the shield on the indicator"),
        "setDisplayShieldHp": ("value", "задать щит на индикаторе; это только показ", "set the shield on the indicator; it is display only"),
        "getDisplayShieldCapacity": ("", "ёмкость щита на индикаторе", "the shield capacity on the indicator"),
        "setDisplayShieldCapacity": ("value", "задать ёмкость щита на индикаторе; это только показ", "set the shield capacity on the indicator; it is display only"),
        "getTurnsSinceStunned": ("", "сколько ходов назад его оглушили", "how many turns ago it was stunned"),
        "setTurnsSinceStunned": ("value", "задать, от 0 до 255", "set it, 0 to 255"),
        "getTileShade": ("", "темнота клетки под юнитом, 0 если её нет", "the darkness of the tile under the unit, 0 if there is none"),
        "getStat": ("name", "характеристика на этот бой, имена: " + STATS_RU, "a stat for this battle, names: " + STATS_RU),
        "setStat": ("name, value", "задать характеристику на этот бой, от 1 до 8000; текущие ОВ, здоровье, энергия и мана не больше нового максимума", "set a stat for this battle, 1 to 8000; current time units, health, energy and mana stay within the new maximum"),
        "addStat": ("name, value", "прибавить к характеристике на этот бой", "add to a stat for this battle"),
        "getExp": ("name", "опыт за этот бой, те же имена без timeUnits, stamina, health, manaPool", "the experience of this battle, the same names without timeUnits, stamina, health, manaPool"),
        "getMoveCost": ("kind", "надбавка к стоимости хода, kind: base, fly, normal, climb; два значения: проценты ОВ и энергии", "the move cost bonus, kind: base, fly, normal, climb; two values: percent of time units and of energy"),
        "setMoveCost": ("kind, time, energy", "задать надбавку к стоимости хода на этот бой", "set the move cost bonus for this battle"),
        "getInventoryItems": ("slot", "таблица предметов юнита; slot необязателен, это тип слота из рулсета", "a table of the unit's items; slot is optional, a slot type from the ruleset"),
        "getInventoryItem": ("type, slot", "первый предмет типа type или nil; slot необязателен. Тип не из рулсета: ошибка", "the first item of type type, or nil; slot is optional. A type not in the ruleset is an error"),
        "getSpecialItems": ("", "таблица особых предметов юнита: встроенное оружие", "a table of the unit's special items: built-in weapons"),
    },
    "item": {
        "getId": ("", "номер предмета в бою", "the item's number in the battle"),
        "getRuleItem": ("", "правила предмета или nil", "the item rules, or nil"),
        "getOwner": ("", "владелец, юнит или nil; у заряженного в оружие боеприпаса nil", "the owner, a unit, or nil; nil for ammunition loaded into a weapon"),
        "isAmmo": ("", "заряжен в оружие", "loaded into a weapon"),
        "getAmmoQuantity": ("", "патронов сейчас", "rounds now"),
        "getAmmoQuantityMax": ("", "патронов в обойме по правилам", "rounds in a clip by the rules"),
        "setAmmoQuantity": ("value", "задать патроны", "set the rounds"),
        "getFuseTimer": ("", "таймер взрывателя", "the fuse timer"),
        "setFuseTimer": ("value", "задать таймер взрывателя", "set the fuse timer"),
        "isFuseEnabled": ("", "взрыватель взведён", "the fuse is armed"),
        "getHealQuantity": ("", "заряды лечения", "heal charges"),
        "setHealQuantity": ("value", "задать заряды лечения", "set the heal charges"),
        "getPainKillerQuantity": ("", "заряды обезболивающего", "painkiller charges"),
        "setPainKillerQuantity": ("value", "задать заряды обезболивающего", "set the painkiller charges"),
        "getStimulantQuantity": ("", "заряды стимулятора", "stimulant charges"),
        "setStimulantQuantity": ("value", "задать заряды стимулятора", "set the stimulant charges"),
        "getTag": ("name", "значение тега BattleItem", "the value of a BattleItem tag"),
        "setTag": ("name, value", "записать тег BattleItem", "write a BattleItem tag"),
        "getBattleUnit": ("", "юнит на предмете-теле или nil", "the unit of a corpse item, or nil"),
        "getAmmoItem": ("", "боеприпас в первом гнезде или nil", "the ammunition in the first slot, or nil"),
        "getAmmoForSlot": ("slot", "боеприпас в гнезде от 0 до 3 или nil; другой номер: ошибка", "the ammunition in slot 0 to 3, or nil; another number is an error"),
        "getAmmoForAction": ("action", "чем будет стрелять это действие BA_*, или nil", "what action BA_* will fire, or nil"),
        "getSlot": ("", "тип слота из рулсета, строка, или nil", "the slot type from the ruleset, a string, or nil"),
        "getPreviousOwner": ("", "прежний владелец, юнит или nil", "the previous owner, a unit or nil"),
        "getGlow": ("", "светится", "glows"),
        "getTotalWeight": ("", "вес с боеприпасами", "the weight with ammunition"),
        "isSpecialWeapon": ("", "встроенное оружие", "a built-in weapon"),
        "getFuseTimerDefault": ("", "таймер взрывателя по правилам", "the fuse timer by the rules"),
        "setFuseEnabled": ("value", "взвести или снять взрыватель, true или false", "arm or disarm the fuse, true or false"),
        "getActionCost": ("unit, action", "сколько ОВ стоит юниту действие BA_* этим предметом", "how many time units action BA_* with this item costs the unit"),
        "getMoveToCost": ("slot", "сколько ОВ стоит перенести в слот; предмет не в слоте: 0", "how many time units moving to a slot costs; an item not in a slot: 0"),
        "getInventoryMoveCost": ("", "надбавка к стоимости переноса, проценты", "the bonus to the moving cost, percent"),
        "setInventoryMoveCost": ("value", "задать надбавку к стоимости переноса", "set the bonus to the moving cost"),
    },
    "battle": {
        "getTurn": ("", "номер хода", "the turn number"),
        "getSize": ("", "размер карты, три значения: x, y, z", "the map size, three values: x, y, z"),
        "flashMessage": ("text, a, b, c", "сообщение на экране боя: строка из рулсета или текст, до трёх целых для {0} {1} {2}. "
                         "В returnFromMissionUnit ничего не делает",
                         "a message on the battle screen: a string id or plain text, up to three whole numbers for {0} {1} {2}. "
                         "Does nothing in returnFromMissionUnit"),
        "flashLongMessage": ("text, a, b, c", "то же, держится на экране дольше", "the same, stays on the screen longer"),
        "getTile": ("x, y, z", "клетка карты; за границей nil", "a map tile; outside the map nil"),
        "getUnits": ("faction", "таблица живых юнитов боя, без оставшихся вне карты; faction необязателен, FACTION_*", "a table of the battle's living units, without those left off the map; faction is optional, FACTION_*"),
        "getItems": ("", "таблица предметов боя. В большом бою их тысячи: это дорого, см. лимиты", "a table of the battle's items. A big battle has thousands: this is costly, see the limits"),
        "getSelectedUnit": ("", "выбранный юнит или nil", "the selected unit, or nil"),
        "getTurnSide": ("", "чей сейчас ход, FACTION_*", "whose turn it is, FACTION_*"),
        "randomRange": ("low, high", "случайное целое от low до high через генератор игры", "a random whole number from low to high through the game's generator"),
        "randomChance": ("percent", "true с этим шансом через генератор игры", "true with this chance through the game's generator"),
        "difficultyLevel": ("", "сложность, DIFF_*", "the difficulty, DIFF_*"),
        "getAlienItemLevel": ("", "уровень снаряжения врага", "the enemy's item level"),
        "setAlienItemLevel": ("value", "задать уровень снаряжения врага", "set the enemy's item level"),
        "getReinforcementsItemLevel": ("", "уровень снаряжения подкреплений", "the item level of reinforcements"),
        "setReinforcementsItemLevel": ("value", "задать уровень снаряжения подкреплений", "set the item level of reinforcements"),
        "getDepth": ("", "глубина подводной миссии", "the depth of an underwater mission"),
        "getGlobalShade": ("", "общая темнота карты", "the darkness of the whole map"),
        "getGeoscapeGame": ("", "геоскейп", "the geoscape"),
        "tryConcealUnit": ("unit", "попробовать скрыть юнита от врага; итог true или false", "try to conceal a unit from the enemy; the result is true or false"),
        "getTag": ("name", "значение тега BattleGame", "the value of a BattleGame tag"),
        "setTag": ("name, value", "записать тег BattleGame", "write a BattleGame tag"),
    },
    "soldier": {
        "getId": ("", "номер солдата", "the soldier's number"),
        "getRank": ("", "звание, целое", "the rank, a whole number"),
        "getGender": ("", "пол, GENDER_*", "the gender, GENDER_*"),
        "getLook": ("", "внешность, LOOK_*", "the look, LOOK_*"),
        "getLookVariant": ("", "вариант внешности", "the variant of the look"),
        "getRuleSoldier": ("", "правила солдата", "the soldier rules"),
        "getWoundRecovery": ("", "сколько дней ещё лечит раны", "for how many more days wounds heal"),
        "setWoundRecovery": ("value", "задать дни лечения ран", "set the days of wound recovery"),
        "getManaMissing": ("", "сколько маны не хватает", "how much mana is missing"),
        "setManaMissing": ("value", "задать, сколько маны не хватает", "set how much mana is missing"),
        "getHealthMissing": ("", "сколько здоровья не хватает", "how much health is missing"),
        "setHealthMissing": ("value", "задать, сколько здоровья не хватает", "set how much health is missing"),
        "getStat": ("name", "постоянная характеристика, имена как у юнита", "a permanent stat, the names as for a unit"),
        "setStat": ("name, value", "задать постоянную характеристику, от 1 до 8000; остаётся после боя", "set a permanent stat, 1 to 8000; it stays after the battle"),
        "addStat": ("name, value", "прибавить к постоянной характеристике", "add to a permanent stat"),
        "getTag": ("name", "значение тега GeoscapeSoldier", "the value of a GeoscapeSoldier tag"),
        "setTag": ("name, value", "записать тег GeoscapeSoldier", "write a GeoscapeSoldier tag"),
    },
    "ruleArmor": {
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getStat": ("name", "прибавка брони к характеристике, имена как у юнита", "the armor's bonus to a stat, the names as for a unit"),
        "getCorpseGeoscape": ("", "правила предмета-тела на геоскейпе или nil", "the rules of the corpse item on the geoscape, or nil"),
        "getCorpseBattlescape": ("", "таблица правил предметов-тел в бою", "a table of the rules of corpse items in battle"),
        "getRequiredResearch": ("", "нужное исследование, строка, или nil", "the required research, a string, or nil"),
        "getDrawingRoutine": ("", "номер способа рисования", "the number of the drawing routine"),
        "getDrawBubbles": ("", "рисует пузыри под водой", "draws bubbles under water"),
        "getDeathFrames": ("", "кадров смерти", "death frames"),
        "getConstantAnimation": ("", "анимация идёт постоянно", "the animation runs all the time"),
        "getVisibilityAtDark": ("", "обзор в темноте", "the view range in the dark"),
        "getVisibilityAtDay": ("", "обзор днём", "the view range by day"),
        "getCamouflageAtDark": ("", "маскировка в темноте", "camouflage in the dark"),
        "getCamouflageAtDay": ("", "маскировка днём", "camouflage by day"),
        "getAntiCamouflageAtDark": ("", "антимаскировка в темноте", "anti-camouflage in the dark"),
        "getAntiCamouflageAtDay": ("", "антимаскировка днём", "anti-camouflage by day"),
        "getHeatVision": ("", "зрение сквозь дым", "vision through smoke"),
        "getVisibilityThroughFire": ("", "зрение сквозь огонь", "vision through fire"),
        "getPersonalLight": ("", "свой свет у стороны игрока", "the personal light on the player's side"),
        "getPersonalLightHostile": ("", "свой свет у врага", "the personal light on the enemy's side"),
        "getPersonalLightNeutral": ("", "свой свет у нейтралов", "the personal light on the neutral side"),
        "getSize": ("", "размер юнита в клетках", "the unit's size in tiles"),
        "getArmor": ("side", "броня стороны SIDE_*", "the armor of side SIDE_*"),
        "getMoveCost": ("kind", "надбавка к стоимости хода, как у юнита", "the move cost bonus, as for a unit"),
        "getTag": ("name", "значение тега RuleArmor", "the value of a RuleArmor tag"),
    },
    "ruleItem": {
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getAccuracyAimed": ("", "точность прицельного выстрела", "the accuracy of an aimed shot"),
        "getAccuracyAuto": ("", "точность очереди", "the accuracy of an auto shot"),
        "getAccuracyMelee": ("", "точность удара", "the melee accuracy"),
        "getAccuracyMind": ("", "точность контроля разума", "the accuracy of mind control"),
        "getAccuracyPanic": ("", "точность паники", "the accuracy of panic"),
        "getAccuracySnap": ("", "точность быстрого выстрела", "the accuracy of a snap shot"),
        "getAccuracyThrow": ("", "точность броска", "the accuracy of a throw"),
        "getAccuracyUse": ("", "точность применения", "the accuracy of use"),
        "getPower": ("", "сила", "the power"),
        "getDamageType": ("", "правила типа урона или nil", "the damage type rules, or nil"),
        "getMeleePower": ("", "сила удара", "the melee power"),
        "getMeleeDamageType": ("", "правила типа урона удара или nil", "the melee damage type rules, or nil"),
        "getArmorValue": ("", "прочность предмета", "the item's armor"),
        "getWeight": ("", "вес", "the weight"),
        "getBattleType": ("", "вид предмета, BT_*", "the kind of item, BT_*"),
        "getWaypoints": ("", "точек маршрута у ракеты", "waypoints of a guided missile"),
        "isWaterOnly": ("", "только под водой", "under water only"),
        "isTwoHanded": ("", "двуручный", "two-handed"),
        "isBlockingBothHands": ("", "занимает обе руки", "blocks both hands"),
        "isSingleTarget": ("", "без радиуса взрыва", "no blast radius"),
        "hasCategory": ("name", "есть категория name", "has category name"),
        "getTag": ("name", "значение тега RuleItem", "the value of a RuleItem tag"),
    },
    "skill": {"getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string")},
    "tile": {
        "getPosition": ("", "три значения: x, y, z", "three values: x, y, z"),
        "getFire": ("", "сколько ходов горит", "for how many turns it burns"),
        "getSmoke": ("", "плотность дыма", "the smoke density"),
        "getShade": ("", "темнота", "the darkness"),
        "isDiscovered": ("", "что открыто игроку, сумма: 1 пол, 2 западная стена, 4 северная стена", "what the player has discovered, a sum: 1 floor, 2 west wall, 4 north wall"),
        "makeDiscovered": ("parts", "открыть игроку, та же сумма", "discover for the player, the same sum"),
        "getUnit": ("", "юнит на клетке или nil", "the unit on the tile, or nil"),
        "getDistanceTile": ("other", "расстояние до клетки other в клетках", "the distance to tile other in tiles"),
        "getDistanceVoxel": ("other", "расстояние до клетки other в вокселях", "the distance to tile other in voxels"),
        "getFloorSpecialTileType": ("", "особый тип пола, STT_* или другое число из рулсета", "the special floor type, STT_* or another number from the ruleset"),
        "getObjectSpecialTileType": ("", "особый тип объекта, STT_* или другое число из рулсета", "the special object type, STT_* or another number from the ruleset"),
    },
    "geoscape": {
        "getFunds": ("", "деньги, только luaApi: 2", "the money, only luaApi: 2"),
        "addFunds": ("n", "прибавить деньги, n от -1000000000 до 1000000000. Разрешение economy", "add money, n from -1000000000 to 1000000000. Permission economy"),
        "getTime": ("", "таблица по Гринвичу: second, minute, hour, day, month, year, secondsPastMidnight, daysPastEpoch", "a table in Greenwich time: second, minute, hour, day, month, year, secondsPastMidnight, daysPastEpoch"),
        "difficultyLevel": ("", "сложность, DIFF_*", "the difficulty, DIFF_*"),
        "getMonthsPassed": ("", "сколько месяцев идёт игра", "how many months the game has run"),
        "getDaysPassed": ("", "сколько дней идёт игра", "how many days the game has run"),
        "getCountries": ("", "таблица стран", "a table of the countries"),
        "isResearched": ("name", "исследовано name. Незнакомое имя: ошибка", "name is researched. An unknown name is an error"),
        "randomRange": ("low, high", "случайное целое от low до high через генератор игры", "a random whole number from low to high through the game's generator"),
        "randomRangeSymmetric": ("max", "случайное целое от -max до max через генератор игры", "a random whole number from -max to max through the game's generator"),
        "randomChance": ("percent", "true с этим шансом через генератор игры", "true with this chance through the game's generator"),
        "getTag": ("name", "значение тега GeoscapeGame", "the value of a GeoscapeGame tag"),
        "setTag": ("name, value", "записать тег GeoscapeGame", "write a GeoscapeGame tag"),
    },
    "country": {
        "getRuleCountry": ("", "правила страны", "the country rules"),
        "getPact": ("", "заключила пакт", "has signed a pact"),
        "getCurrentFunding": ("", "финансирование этого месяца", "the funding of this month"),
        "getCurrentActivityAlien": ("", "активность врага за этот месяц", "the enemy's activity this month"),
        "getCurrentActivityXcom": ("", "активность игрока за этот месяц", "the player's activity this month"),
        "getTag": ("name", "значение тега Country", "the value of a Country tag"),
    },
    "ufo": {
        "getId": ("", "номер НЛО", "the UFO's number"),
        "getAltitude": ("", "высота, целое", "the altitude, a whole number"),
        "getStatus": ("", "состояние, UFO_*", "the status, UFO_*"),
        "getVisibility": ("", "заметность для радаров", "how visible it is to radars"),
        "getDamage": ("", "урон", "the damage"),
        "getDamageMax": ("", "прочность", "the hit points"),
        "getDamagePercentage": ("", "урон в процентах", "the damage in percent"),
        "getShield": ("", "щит", "the shield"),
        "getShieldMax": ("", "ёмкость щита", "the shield capacity"),
        "getShieldPercentage": ("", "щит в процентах", "the shield in percent"),
        "isHunterKiller": ("", "охотник", "a hunter-killer"),
        "isHunting": ("", "сейчас охотится", "hunting now"),
        "isEscorting": ("", "сейчас сопровождает", "escorting now"),
        "getHuntBehavior": ("", "поведение на охоте", "the behaviour in a hunt"),
        "getHuntMode": ("", "режим охоты", "the hunt mode"),
        "getDetected": ("", "обнаружено", "detected"),
        "getHyperDetected": ("", "обнаружено гипердетектором", "detected by a hyperwave decoder"),
        "getRuleUfo": ("", "правила НЛО", "the UFO rules"),
        "getStat": ("name", "характеристика, имена: " + CRAFT_STATS, "a stat, names: " + CRAFT_STATS),
        "getTag": ("name", "значение тега Ufo", "the value of an Ufo tag"),
    },
    "craft": {
        "getId": ("", "номер корабля", "the craft's number"),
        "getDamage": ("", "урон", "the damage"),
        "getDamageMax": ("", "прочность", "the hit points"),
        "getDamagePercentage": ("", "урон в процентах", "the damage in percent"),
        "getShield": ("", "щит", "the shield"),
        "getShieldMax": ("", "ёмкость щита", "the shield capacity"),
        "getShieldPercentage": ("", "щит в процентах", "the shield in percent"),
        "getRuleCraft": ("", "правила корабля", "the craft rules"),
        "getStat": ("name", "характеристика, имена как у НЛО", "a stat, the names as for a UFO"),
        "getTag": ("name", "значение тега Craft", "the value of a Craft tag"),
    },
    "ruleDamage": {
        "isDirect": ("", "прямой урон, без взрыва", "direct damage, no blast"),
        "isAreaOfEffect": ("", "урон по площади", "area damage"),
        "getResistType": ("", "против какого сопротивления, DT_*", "against which resistance, DT_*"),
        "getRandomType": ("", "способ разброса, номер", "the way of randomising, a number"),
        "getArmorEffectiveness": ("", "действие брони, проценты", "the effect of armor, percent"),
        "getDamageTo": ("kind, value", "сколько из силы value идёт на kind: armorPre, armor, energy, health, item, mana, morale, stun, tile, time, wound", "how much of power value goes to kind: armorPre, armor, energy, health, item, mana, morale, stun, tile, time, wound"),
        "getRandomDamage": ("value", "случайный урон от силы value через генератор игры", "random damage from power value through the game's generator"),
    },
    "ruleUnit": {
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getSpawnUnit": ("", "в кого превращается, правила юнита или nil", "what it turns into, the unit rules or nil"),
        "getCivilianRecoveryItemType": ("", "предмет за спасение гражданского или nil", "the item for rescuing a civilian, or nil"),
        "getLiveAlienGeoscape": ("", "предмет за живого пленного или nil", "the item for a live captive, or nil"),
    },
    "ruleSoldier": {
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getTag": ("name", "значение тега RuleSoldier", "the value of a RuleSoldier tag"),
    },
    "ruleSoldierBonus": {
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getTag": ("name", "значение тега RuleSoldierBonus", "the value of a RuleSoldierBonus tag"),
    },
    "ruleCountry": {
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getFundingCap": ("", "предел финансирования", "the funding cap"),
        "getTag": ("name", "значение тега RuleCountry", "the value of a RuleCountry tag"),
    },
    "ruleUfo": {
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getRadius": ("", "радиус, размер на карте боя", "the radius, the size on the battle map"),
        "getWeaponRange": ("", "дальность оружия", "the weapon range"),
        "getWeaponPower": ("", "сила оружия", "the weapon power"),
        "getWeaponReload": ("", "перезарядка оружия", "the weapon reload"),
        "getTag": ("name", "значение тега RuleUfo", "the value of a RuleUfo tag"),
    },
    "ruleCraft": {
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getWeaponsMax": ("", "сколько оружия", "how many weapons"),
        "getSoldiersMax": ("", "сколько мест для солдат", "how many soldier places"),
        "getVehiclesMax": ("", "сколько мест для техники и крупных солдат", "how many places for vehicles and large soldiers"),
        "getPilotsMax": ("", "сколько нужно пилотов", "how many pilots it needs"),
        "getTag": ("name", "значение тега RuleCraft", "the value of a RuleCraft tag"),
    },
    "ruleResearch": {
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getCost": ("", "стоимость в днях учёных", "the cost in scientist days"),
        "getPoints": ("", "очки за исследование", "the score for the research"),
        "getLookup": ("", "что открывается вместе с ним, правила исследования или nil", "what opens along with it, the research rules or nil"),
        "getNeededItem": ("", "нужный предмет, правила предмета или nil", "the item it needs, the item rules or nil"),
        "getTag": ("name", "значение тега RuleResearch", "the value of a RuleResearch tag"),
    },
    "ruleInventory": {
        "getId": ("", "имя ячейки из рулсета, строка", "the slot's name from the ruleset, a string"),
        "getType": ("", "вид ячейки: game.INV_SLOT, game.INV_HAND, game.INV_GROUND", "the kind of slot: game.INV_SLOT, game.INV_HAND, game.INV_GROUND"),
        "isRightHand": ("", "правая рука", "the right hand"),
        "isLeftHand": ("", "левая рука", "the left hand"),
        "getMoveToCost": ("other", "сколько очков времени стоит перенос в ячейку other", "how many time units moving to slot other costs"),
    },
    "rules": {
        "getRuleUnit": ("type", "правила юнита этого типа или nil, если такого нет", "the rules of a unit of this type, or nil if there is none"),
        "getRuleItem": ("type", "правила предмета или nil", "the rules of an item, or nil"),
        "getRuleArmor": ("type", "правила брони или nil", "the rules of an armor, or nil"),
        "getRuleSkill": ("type", "правила навыка или nil", "the rules of a skill, or nil"),
        "getRuleResearch": ("type", "правила исследования или nil", "the rules of a research, or nil"),
        "getRuleSoldier": ("type", "правила солдата или nil", "the rules of a soldier, or nil"),
        "getRuleInventory": ("id", "правила ячейки инвентаря или nil", "the rules of an inventory slot, or nil"),
        "getRuleInventoryRightHand": ("", "правая рука или nil", "the right hand, or nil"),
        "getRuleInventoryLeftHand": ("", "левая рука или nil", "the left hand, or nil"),
        "getRuleInventoryBackpack": ("", "рюкзак или nil", "the backpack, or nil"),
        "getRuleInventoryBelt": ("", "пояс или nil", "the belt, or nil"),
        "getRuleInventoryGround": ("", "земля или nil", "the ground, or nil"),
        "getMaxDarknessToSeeUnits": ("", "до какой темноты видно юнитов", "up to what darkness units are seen"),
        "getMaxViewDistance": ("", "наибольшая дальность зрения в клетках", "the greatest view distance in tiles"),
        "getSmokeReduction": ("smoke", "сколько вокселей дальности отнимает дым такой плотности", "how many voxels of range smoke of this density takes"),
    },
    "ui": {
        "window": ("{ x, y, w, h, background }", "окно: рамка и фон. Нужно раньше list и comboBox. background: картинка из игры или extraSprites мода, без него фон берётся из interface экрана", "a window: the frame and the background. Needed before list and comboBox. background: a picture of the game or the mod's extraSprites, without it the background comes from the screen's interface"),
        "text": ("{ x, y, w, h, text, big, align, wrap, color }", "текст: ключ extraStrings или сама строка. align: left, center, right", "text: a key of extraStrings or the string itself. align: left, center, right"),
        "button": ("{ x, y, w, h, text, color, onClick }", "кнопка. onClick(кнопка)", "a button. onClick(button)"),
        "toggleButton": ("{ x, y, w, h, text, pressed, color, onClick }", "кнопка-переключатель. onClick(кнопка)", "a toggle button. onClick(button)"),
        "list": ("{ x, y, w, h, columns, selectable, color, onClick }", "список: columns, ширины столбцов, от 1 до 8; до 2000 строк. onClick(список, строка), строки с единицы", "a list: columns, the widths of the columns, from 1 to 8; up to 2000 rows. onClick(list, row), rows count from one"),
        "comboBox": ("{ x, y, w, h, options, selected, color, onChange }", "выпадающий список, до 256 пунктов. onChange(список, пункт), пункты с единицы", "a drop-down list, up to 256 options. onChange(list, option), options count from one"),
        "edit": ("{ x, y, w, h, text, focus, color, onChange, onEnter }", "поле ввода. onChange(поле, текст), onEnter(поле, текст)", "an input field. onChange(field, text), onEnter(field, text)"),
        "slider": ("{ x, y, w, h, min, max, value, color, onChange }", "ползунок. onChange(ползунок, значение)", "a slider. onChange(slider, value)"),
        "image": ("{ x, y, image, onClick }", "картинка из игры или extraSprites мода, файлы из Lua не читаются. onClick(картинка)", "a picture of the game or the mod's extraSprites, Lua reads no files. onClick(picture)"),
        "onKey": ("fn", "клавиша на этом экране: fn(имя клавиши). Esc закрывает экран всегда", "a key on this screen: fn(key name). Esc always closes the screen"),
        "onClose": ("fn", "вызывается при закрытии. Без случайных чисел, записи и openScreen: открытый и закрытый экран ничего не меняет", "called on closing. No random numbers, writes or openScreen: a screen opened and closed changes nothing"),
        "close": ("", "закрыть экран, только верхний и только из обработчика, не из построения", "close the screen: only the top one, only from a handler, not while it builds"),
    },
    "uiWidget": {
        "setVisible": ("value", "показать или скрыть виджет", "show or hide the widget"),
        "isVisible": ("", "виден ли виджет", "whether the widget is shown"),
        "setText": ("text", "новый текст: text, button, toggleButton, edit", "new text: text, button, toggleButton, edit"),
        "getText": ("", "текст: text, edit", "the text: text, edit"),
        "setPressed": ("value", "нажать или отпустить: toggleButton", "press or release: toggleButton"),
        "isPressed": ("", "нажата ли: toggleButton", "whether it is pressed: toggleButton"),
        "addRow": ("cell, ...", "строка в конец: list. Ячеек не больше столбцов", "a row at the end: list. No more cells than columns"),
        "clearList": ("", "убрать все строки: list", "remove all rows: list"),
        "setCell": ("row, column, text", "текст ячейки: list, с единицы", "the text of a cell: list, from one"),
        "getRowCount": ("", "сколько строк: list", "how many rows: list"),
        "getSelected": ("", "выбранная строка или пункт, с единицы: list, comboBox. У списка без щелчка: 1", "the selected row or option, from one: list, comboBox. On a list not clicked yet: 1"),
        "setSelected": ("index", "выбрать пункт, с единицы: comboBox", "select an option, from one: comboBox"),
        "setOptions": ("options", "новые пункты: comboBox", "new options: comboBox"),
        "getValue": ("", "значение: slider", "the value: slider"),
        "setValue": ("value", "новое значение: slider. onChange не вызывается", "a new value: slider. onChange is not called"),
        "setRange": ("low, high", "новые границы: slider", "new limits: slider"),
        "setFocus": ("", "ввод с клавиатуры в это поле: edit. Пока фокус в поле, первый щелчок вне него только снимает фокус, а onKey молчит", "keyboard input into this field: edit. While the field has the focus, the first click outside it only takes the focus away, and onKey is silent"),
        "setImage": ("name", "другая картинка того же размера или меньше: image", "another picture of the same size or smaller: image"),
    },
    "base": {
        "getName": ("", "имя базы", "the base's name"),
        "getStores": ("", "таблица: used, занято места на складе, capacity, сколько вмещает", "a table: used, the stores' space taken, capacity, how much they hold"),
        "getQuarters": ("", "таблица: used, занято мест в жилье, capacity, сколько вмещает", "a table: used, the quarters taken, capacity, how many they hold"),
        "getItemCount": ("type", "сколько таких предметов на складе; нет правила: ошибка", "how many such items are in the stores; no such rule: an error"),
        "addItem": ("type[, n]", "положить на склад, по умолчанию один. Разрешение economy", "put into the stores, one by default. Permission economy"),
        "removeItem": ("type[, n]", "убрать со склада; больше, чем есть: ошибка. Разрешение economy", "take from the stores; more than there are: an error. Permission economy"),
        "getFreeScientists": ("", "незанятые учёные", "scientists without work"),
        "addScientists": ("n", "добавить учёных. Разрешение economy", "add scientists. Permission economy"),
        "removeScientists": ("n", "убрать незанятых учёных; больше: ошибка. Разрешение economy", "remove scientists without work; more: an error. Permission economy"),
        "getFreeEngineers": ("", "незанятые инженеры", "engineers without work"),
        "addEngineers": ("n", "добавить инженеров. Разрешение economy", "add engineers. Permission economy"),
        "removeEngineers": ("n", "убрать незанятых инженеров; больше: ошибка. Разрешение economy", "remove engineers without work; more: an error. Permission economy"),
        "hireSoldier": ("type[, done]", "нанять солдата после обработчика, бесплатно: done(soldier) или done(nil, причина). Разрешение economy", "hire a soldier after the handler, free: done(soldier) or done(nil, reason). Permission economy"),
    },
    "statsForNerds": {
        "addIntRow": ("name, value", "строка с числом", "a row with a number"),
        "addTextRow": ("name, text", "строка с текстом", "a row with text"),
        "addTextFormatRow": ("name, format, a[, b]", "строка из шаблона: {0} и {1} заменяются числами a и b", "a row from a template: {0} and {1} are replaced by the numbers a and b"),
    },
}

HIT = "unit, damaging_item, weapon_item, attacker, battle, skill"
BONUS = "unit, external_bonuses, weapon, ammo, battle_action, skill"
REACTION = "action_unit, reaction_unit, reaction_weapon, reaction_battle_action, reaction_count, weapon, skill, battle_action, action_target, move, arc_to_action_unit, battle_game"
# обработчик: (имя в enum, аргументы до out, когда, when)
EVENTS = {
    "createUnit": ("CREATE_UNIT", "unit, battle, turn", "юнит появился в бою", "a unit appears in the battle"),
    "newTurnUnit": ("NEW_TURN_UNIT", "unit, battle, turn, side", "начало хода стороны, для каждого юнита; side - чей ход, FACTION_*",
                    "the start of a side's turn, for each unit; side is whose turn it is, FACTION_*"),
    "hitUnit": ("HIT_UNIT", HIT + ", orig_power, damaging_type, battle_action", "попадание, до брони", "a hit, before the armor"),
    "damageUnit": ("DAMAGE_UNIT", HIT + ", currPower, orig_power, part, side, damaging_type, battle_action", "расчёт урона, после брони",
                   "the damage is worked out, after the armor"),
    "damageSpecialUnit": ("DAMAGE_SPECIAL_UNIT", HIT + ", health_damage, orig_power, part, side, damaging_type, battle_action",
                          "урон нанесён, особые последствия", "the damage is done, the special effects"),
    "healUnit": ("HEAL_UNIT", "actor, item, battle, target, battle_action", "применение аптечки", "a medikit is used"),
    "skillUseUnit": ("SKILL_USE_UNIT", "actor, item, battle, skill, battle_action, have_tu", "применение навыка", "a skill is used"),
    "returnFromMissionUnit": ("RETURN_FROM_MISSION_UNIT", "unit, battle, soldier", "конец миссии, для каждого солдата; экрана боя уже нет",
                              "the end of a mission, for each soldier; the battle screen is gone"),
    "createItem": ("CREATE_ITEM", "item, unit, battle, turn", "предмет появился в бою; unit может быть nil", "an item appears in the battle; unit may be nil"),
    "newTurnItem": ("NEW_TURN_ITEM", "item, battle, turn, side", "начало хода стороны, для каждого предмета", "the start of a side's turn, for each item"),
    "awardExperience": ("AWARD_EXPERIENCE", "attacker, unit, weapon, battle_action", "начисление опыта за попадание", "experience is awarded for a hit"),
    "tryPsiAttackItem": ("TRY_PSI_ATTACK_ITEM", "item, attacker, victim, skill, attack_strength, defense_strength, battle_action, distance, distance_strength_reduction, battle",
                         "расчёт пси-атаки, правило оружия. ИИ считает так же и свои прогнозы: вызов ещё не значит попытку", "a psi attack is worked out, the weapon's rule. The AI's forecasts work it out too: a call does not mean an attempt"),
    "tryPsiAttackUnit": ("TRY_PSI_ATTACK_UNIT", "item, attacker, victim, skill, attack_strength, defense_strength, battle_action, battle",
                         "расчёт пси-атаки, правило цели. Вызов ещё не значит попытку", "a psi attack is worked out, the target's rule. A call does not mean an attempt"),
    "tryMeleeAttackItem": ("TRY_MELEE_ATTACK_ITEM", "item, attacker, victim, is_same_faction, skill, attack_strength, defense_strength, battle_action, arc_to_attacker, defense_strength_penalty, battle",
                           "расчёт удара, правило оружия. Вызов ещё не значит попытку", "a melee attack is worked out, the weapon's rule. A call does not mean an attempt"),
    "tryMeleeAttackUnit": ("TRY_MELEE_ATTACK_UNIT", "item, attacker, victim, skill, attack_strength, defense_strength, battle_action, battle",
                           "расчёт удара, правило цели. Вызов ещё не значит попытку", "a melee attack is worked out, the target's rule. A call does not mean an attempt"),
    "selectMoveSoundUnit": ("SELECT_MOVE_SOUND_UNIT", "unit, walking_phase, unit_sound_index, tile_sound_index, base_tile_sound_index, base_tile_sound_offset, base_fly_sound_index, move",
                            "шаг юнита: какой звук играть", "a step of a unit: which sound to play"),
    "newMonthCountry": ("NEW_MONTH_COUNTRY", "country, geoscape_game, totalXcomScore, totalAlienScore", "конец месяца, для каждой страны", "the end of a month, for each country"),
    "detectUfoFromBase": ("DETECT_UFO_FROM_BASE", "ufo, geoscape_game, distance, already_tracked, radar_total_strength, radar_max_distance, hyperwave_total_strength, hyperwave_max_distance",
                          "база пробует заметить НЛО", "a base tries to detect a UFO"),
    "detectUfoFromCraft": ("DETECT_UFO_FROM_CRAFT", "ufo, geoscape_game, craft, distance, already_tracked, radar_total_strength, radar_max_distance",
                           "корабль пробует заметить НЛО", "a craft tries to detect a UFO"),
    "applySoldierBonuses": ("APPLY_SOLDIER_BONUSES", "unit, battle, bonus", "солдат входит в бой, для каждого его бонуса", "a soldier enters a battle, for each of their bonuses"),
    "hitUnitAmmo": ("HIT_UNIT_AMMO", HIT + ", orig_power, damaging_type, battle_action", "попадание, до брони, для патрона: идёт перед <code>hitUnit</code> и только если есть чем стреляли", "a hit, before the armor, for the round: comes before <code>hitUnit</code> and only if there is a round"),
    "damageUnitAmmo": ("DAMAGE_UNIT_AMMO", HIT + ", currPower, orig_power, part, side, damaging_type, battle_action", "расчёт урона для патрона, перед <code>damageUnit</code>", "the damage is worked out for the round, before <code>damageUnit</code>"),
    "damageSpecialUnitAmmo": ("DAMAGE_SPECIAL_UNIT_AMMO", HIT + ", health_damage, orig_power, part, side, damaging_type, battle_action", "особые последствия для патрона, перед <code>damageSpecialUnit</code>", "the special effects for the round, before <code>damageSpecialUnit</code>"),
    "reactionWeaponAction": ("REACTION_WEAPON_ACTION", REACTION, "шанс реакции, правило оружия действующего; идёт первым, только если оружие есть", "the reaction chance, the rule of the acting unit's weapon; comes first, only if there is a weapon"),
    "reactionUnitAction": ("REACTION_UNIT_ACTION", REACTION, "шанс реакции, правило действующего", "the reaction chance, the acting unit's rule"),
    "reactionUnitReaction": ("REACTION_UNIT_REACTION", REACTION, "шанс реакции, правило реагирующего", "the reaction chance, the reacting unit's rule"),
    "visibilityUnit": ("VISIBILITY_UNIT", "observer_unit, target_unit, target_tile, distance, distance_max, distance_target_max, smoke_density, fire_density, smoke_density_near_observer, fire_density_near_observer", "видит ли юнит цель или клетку; идёт очень часто", "whether a unit sees a target or a tile; comes very often"),
    "aiCalculateTargetWeight": ("AI_CALCULATE_TARGET_WEIGHT", "ai_unit, target_unit, battle_game", "вес цели для ИИ", "the weight of a target for the AI"),
    "sellCostItem": ("SELL_COST_ITEM", "item_rule, geoscape_game, difficulty_coefficient", "цена продажи предмета; приходит и при каждой строке магазина", "the sale price of an item; comes for each row of the shop too"),
    "buyCostItem": ("BUY_COST_ITEM", "item_rule, geoscape_game, difficulty_coefficient", "цена покупки предмета; приходит и при каждой строке магазина", "the purchase price of an item; comes for each row of the shop too"),
    "statsForNerdsItem": ("STATS_FOR_NERDS_ITEM", "item_rule, nerds, geoscape_game", "страница для нердов о предмете открыта или обновлена: дописать свои строки", "the nerds' page of an item opens or refreshes: add your rows"),
    "statsForNerdsArmor": ("STATS_FOR_NERDS_ARMOR", "armor_rule, nerds, geoscape_game", "то же о броне", "the same for an armor"),
    "statsForNerdsCraft": ("STATS_FOR_NERDS_CRAFT", "craft_rule, nerds, geoscape_game", "то же о корабле", "the same for a craft"),
    "statsForNerdsUfo": ("STATS_FOR_NERDS_UFO", "ufo_rule, nerds, geoscape_game", "то же о НЛО", "the same for a UFO"),
    "psiDefenceBonusStats": ("PSI_DEFENCE_BONUS", BONUS, "защита брони от пси", "the armor's psi defence"),
    "meleeDodgeBonusStats": ("MELEE_DODGE_BONUS", BONUS, "уклонение брони от удара", "the armor's melee dodge"),
    "timeRecoveryBonusStats": ("TIME_RECOVERY_BONUS", BONUS, "сколько очков времени возвращает броня за ход", "how many time units the armor returns per turn"),
    "energyRecoveryBonusStats": ("ENERGY_RECOVERY_BONUS", BONUS, "сколько энергии возвращает броня", "how much energy the armor returns"),
    "moraleRecoveryBonusStats": ("MORALE_RECOVERY_BONUS", BONUS, "сколько боевого духа возвращает броня", "how much morale the armor returns"),
    "healthRecoveryBonusStats": ("HEALTH_RECOVERY_BONUS", BONUS, "сколько здоровья возвращает броня", "how much health the armor returns"),
    "manaRecoveryBonusStats": ("MANA_RECOVERY_BONUS", BONUS, "сколько маны возвращает броня", "how much mana the armor returns"),
    "stunRecoveryBonusStats": ("STUN_RECOVERY_BONUS", BONUS, "сколько оглушения снимает броня", "how much stun the armor removes"),
    "timeSoldierRecoveryBonusStats": ("TIME_SOLDIER_RECOVERY_BONUS", BONUS, "очки времени от бонуса солдата", "time units from a soldier's bonus"),
    "energySoldierRecoveryBonusStats": ("ENERGY_SOLDIER_RECOVERY_BONUS", BONUS, "энергия от бонуса солдата", "energy from a soldier's bonus"),
    "moraleSoldierRecoveryBonusStats": ("MORALE_SOLDIER_RECOVERY_BONUS", BONUS, "боевой дух от бонуса солдата", "morale from a soldier's bonus"),
    "healthSoldierRecoveryBonusStats": ("HEALTH_SOLDIER_RECOVERY_BONUS", BONUS, "здоровье от бонуса солдата", "health from a soldier's bonus"),
    "manaSoldierRecoveryBonusStats": ("MANA_SOLDIER_RECOVERY_BONUS", BONUS, "мана от бонуса солдата", "mana from a soldier's bonus"),
    "stunSoldierRecoveryBonusStats": ("STUN_SOLDIER_RECOVERY_BONUS", BONUS, "оглушение от бонуса солдата", "stun from a soldier's bonus"),
    "damageBonusBonusStats": ("DAMAGE_BONUS_BONUS", BONUS, "сила предмета с бонусом от характеристик", "the item's power with the bonus from the stats"),
    "meleeBonusBonusStats": ("MELEE_BONUS_BONUS", BONUS, "сила удара предмета с бонусом", "the item's melee power with the bonus"),
    "accuracyMultiplierBonusStats": ("ACCURACY_MULTIPLIER_BONUS", BONUS, "точность стрельбы от характеристик", "shooting accuracy from the stats"),
    "meleeMultiplierBonusStats": ("MELEE_MULTIPLIER_BONUS", BONUS, "точность удара от характеристик", "melee accuracy from the stats"),
    "throwMultiplierBonusStats": ("THROW_MULTIPLIER_BONUS", BONUS, "точность броска от характеристик", "throwing accuracy from the stats"),
    "closeQuartersMultiplierBonusStats": ("CLOSE_QUARTERS_MULTIPLIER_BONUS", BONUS, "точность в упор от характеристик", "close quarters accuracy from the stats"),
    "newHour": ("NEW_HOUR", "geoscape_game", "начало игрового часа, геоскейп; только luaApi: 2", "a new game hour, geoscape; only luaApi: 2"),
    "newDay": ("NEW_DAY", "geoscape_game", "начало игровых суток, геоскейп; только luaApi: 2", "a new game day, geoscape; only luaApi: 2"),
    "newMonth": ("NEW_MONTH", "geoscape_game", "начало игрового месяца, отчёт уже посчитан; в одном такте месяц, сутки, час; только luaApi: 2",
                 "a new game month, the report is already counted; in one tick the month, the day, the hour; only luaApi: 2"),
    "battleStart": ("BATTLE_START", "battle", "бой создан, предпросмотр не считается; только чтение; только luaApi: 2", "a battle is created, a preview does not count; read only; only luaApi: 2"),
    "battleEnd": ("BATTLE_END", "battle, aborted", "бой кончился, итог миссии ещё не посчитан; только чтение; только luaApi: 2", "a battle ended, the mission's result is not counted yet; read only; only luaApi: 2"),
}

# аргумент обработчика: (по-русски, по-английски)
ARG_WORDS = {
    "unit": ("юнит, с которым это произошло", "the unit it happened to"),
    "item": ("предмет; в <code>healUnit</code> и <code>skillUseUnit</code> то, чем действуют, в <code>skillUseUnit</code> может быть nil", "the item; in <code>healUnit</code> and <code>skillUseUnit</code> the one used, in <code>skillUseUnit</code> it may be nil"),
    "battle": ("бой", "the battle"),
    "turn": ("номер хода", "the turn number"),
    "aborted": ("1, если отряд ушёл по команде, иначе 0", "1 if the squad left on an order, otherwise 0"),
    "side": ("в <code>newTurn*</code> чей сейчас ход, <code>FACTION_*</code>; в обработчиках урона сторона юнита, <code>SIDE_*</code>", "in <code>newTurn*</code> whose turn it is, <code>FACTION_*</code>; in the damage handlers the side of the unit, <code>SIDE_*</code>"),
    "damaging_item": ("чем нанесён урон, обычно патрон; может быть nil", "what did the damage, usually a round; may be nil"),
    "weapon_item": ("оружие; может быть nil", "the weapon; may be nil"),
    "attacker": ("кто атаковал; может быть nil, например огонь или среда", "who attacked; may be nil, for example fire or the environment"),
    "skill": ("навык; в обработчиках урона обычно nil", "the skill; usually nil in the damage handlers"),
    "orig_power": ("сила попадания после сопротивления брони типу урона, до правок скриптов и до вычитания брони", "the power of the hit after the armor's resistance to the damage type, before scripts and before the armor is subtracted"),
    "damaging_type": ("тип урона, <code>DT_*</code>", "the damage type, <code>DT_*</code>"),
    "battle_action": ("действие, <code>BA_*</code>", "the action, <code>BA_*</code>"),
    "currPower": ("сила после вычитания брони, бывает ноль и меньше", "the power after the armor is subtracted, may be zero or less"),
    "part": ("часть тела, <code>BODYPART_*</code>", "the body part, <code>BODYPART_*</code>"),
    "health_damage": ("сколько снято здоровья, итог <code>to_health</code>", "how much health was taken, the final <code>to_health</code>"),
    "actor": ("кто действует", "who acts"),
    "target": ("кого лечат", "who is healed"),
    "have_tu": ("1, если очков времени на действие хватает, иначе 0", "1 if there are enough time units for the action, otherwise 0"),
    "soldier": ("солдат игрока", "the player's soldier"),
    "weapon": ("чем действовали", "what was used"),
    "victim": ("цель", "the target"),
    "is_same_faction": ("1, если цель на той же стороне", "1 if the target is on the same side"),
    "attack_strength": ("сила атаки", "the attack strength"),
    "defense_strength": ("сила защиты", "the defense strength"),
    "distance": ("расстояние: в <code>tryPsiAttackItem</code> в вокселях, в <code>detectUfo*</code> в морских милях", "the distance: in <code>tryPsiAttackItem</code> in voxels, in <code>detectUfo*</code> in nautical miles"),
    "distance_strength_reduction": ("на сколько расстояние снижает силу", "how much the distance reduces the strength"),
    "arc_to_attacker": ("с какой стороны атакуют: 0 спереди, 4 сзади", "from where the attack comes: 0 the front, 4 the rear"),
    "defense_strength_penalty": ("штраф защиты за атаку сбоку и сзади", "the defense penalty for an attack from the side or the rear"),
    "walking_phase": ("фаза шага", "the phase of the step"),
    "unit_sound_index": ("звук юнита из рулсета", "the unit's sound from the ruleset"),
    "tile_sound_index": ("звук клетки", "the tile's sound"),
    "base_tile_sound_index": ("начало звуков шагов в наборе", "the start of the step sounds in the set"),
    "base_tile_sound_offset": ("смещение звука клетки", "the offset of the tile's sound"),
    "base_fly_sound_index": ("звук полёта", "the flying sound"),
    "move": ("как идёт, <code>BAM_*</code>", "how it moves, <code>BAM_*</code>"),
    "country": ("страна", "the country"),
    "geoscape_game": ("геоскейп", "the geoscape"),
    "totalXcomScore": ("очки игрока за месяц", "the player's score for the month"),
    "totalAlienScore": ("очки врага за месяц", "the enemy's score for the month"),
    "ufo": ("НЛО", "the UFO"),
    "craft": ("корабль", "the craft"),
    "already_tracked": ("1, если уже отслеживается", "1 if it is already tracked"),
    "radar_total_strength": ("общая сила радаров", "the total strength of the radars"),
    "radar_max_distance": ("дальность радаров", "the range of the radars"),
    "hyperwave_total_strength": ("общая сила гипердетекторов", "the total strength of the hyperwave decoders"),
    "hyperwave_max_distance": ("дальность гипердетекторов", "the range of the hyperwave decoders"),
    "bonus": ("бонус солдата", "the soldier's bonus"),
    "external_bonuses": ("добавка от движка, с неё начинается <code>out.bonus</code>", "the engine's addition, <code>out.bonus</code> starts from it"),
    "ammo": ("патрон или nil; в обработчиках без выстрела nil", "the round or nil; nil in handlers with no shot"),
    "action_unit": ("кто действует", "who acts"),
    "reaction_unit": ("кто реагирует", "who reacts"),
    "reaction_weapon": ("чем реагирует, может быть nil", "what it reacts with, may be nil"),
    "reaction_battle_action": ("каким действием реагирует, <code>BA_*</code>", "by which action it reacts, <code>BA_*</code>"),
    "reaction_count": ("счётчик реакций этого юнита", "the count of this unit's reactions"),
    "action_target": ("цель действия, клетка; может быть nil", "the action's target, a tile; may be nil"),
    "arc_to_action_unit": ("с какой стороны действующий: 0 спереди, 4 сзади", "where the acting unit is: 0 the front, 4 the rear"),
    "battle_game": ("бой", "the battle"),
    "observer_unit": ("кто смотрит", "who looks"),
    "target_unit": ("цель; в <code>visibilityUnit</code> nil, если проверяется клетка", "the target; nil in <code>visibilityUnit</code> if a tile is checked"),
    "target_tile": ("клетка цели", "the target's tile"),
    "distance_max": ("наибольшая дальность зрения для цели, в вокселях", "the greatest view distance for the target, in voxels"),
    "distance_target_max": ("наибольшая дальность зрения для цели, в клетках", "the greatest view distance for the target, in tiles"),
    "smoke_density": ("дым на пути", "the smoke on the way"),
    "fire_density": ("огонь на пути", "the fire on the way"),
    "smoke_density_near_observer": ("дым у смотрящего", "the smoke near the observer"),
    "fire_density_near_observer": ("огонь у смотрящего", "the fire near the observer"),
    "ai_unit": ("юнит ИИ", "the AI's unit"),
    "item_rule": ("правила предмета", "the item rules"),
    "armor_rule": ("правила брони", "the armor rules"),
    "craft_rule": ("правила корабля", "the craft rules"),
    "ufo_rule": ("правила НЛО", "the UFO rules"),
    "difficulty_coefficient": ("множитель цены этой игры, в процентах", "this game's price multiplier, in percent"),
    "nerds": ("страница для нердов, в неё дописываются строки", "the nerds' page, rows are added to it"),
}

REACTION_OUT = {
    "reaction_chance": ("шанс реакции в процентах", "the reaction chance in percent"),
    "distance": ("расстояние до действующего, в вокселях", "the distance to the acting unit, in voxels"),
}

# обработчик: выходное значение: (по-русски, по-английски). Смысл прочитан в BattleUnit::damage, TileEngine::medikitUse, skillUse, BattleUnit::postMissionProcedures
OUT_WORDS = {
    "hitUnit": {
        "power": ("сила попадания; ноль и меньше: урона нет и <code>damageUnit</code> не придёт", "the power of the hit; zero or less: no damage, and <code>damageUnit</code> does not come"),
        "part": ("куда попали, <code>BODYPART_*</code>; неверное значение становится головой", "where it hit, <code>BODYPART_*</code>; a wrong value becomes the head"),
        "side": ("с какой стороны, <code>SIDE_*</code>, неверное значение становится передом. У урона от среды сторону и часть задаёт сам движок", "from which side, <code>SIDE_*</code>, a wrong value becomes the front. For damage from the environment the engine sets the side and the part itself"),
    },
    "damageUnit": {
        "to_health": ("сколько снять здоровья", "how much health to take"),
        "to_armor": ("сколько снять брони этой стороны", "how much armor of this side to take"),
        "to_stun": ("сколько прибавить оглушения; не действует на того, кто не чувствует боли, если тип урона этого не обходит", "how much stun to add; does nothing to a unit immune to pain, unless the damage type ignores that"),
        "to_time": ("сколько снять очков времени", "how many time units to take"),
        "to_energy": ("сколько снять энергии", "how much energy to take"),
        "to_morale": ("сколько снять боевого духа, храбрость юнита это уменьшает", "how much morale to take, the unit's bravery reduces it"),
        "to_wound": ("сколько прибавить ран на этой части тела; столько же снимается боевого духа", "how many wounds to add on this body part; as much morale is taken"),
        "to_transform": ("шанс превращения в процентах, дальше он идёт в <code>transform_chance</code>", "the chance of transformation in percent, it goes on to <code>transform_chance</code>"),
        "to_mana": ("сколько снять маны", "how much mana to take"),
    },
    "damageSpecialUnit": {
        "transform": ("1, если этот урон умеет превращать", "1 if this damage can transform"),
        "transform_chance": ("шанс превращения в процентах", "the chance of transformation in percent"),
        "self_destruct": ("1, если юнит взрывается при гибели", "1 if the unit explodes when it dies"),
        "self_destruct_chance": ("шанс взрыва в процентах; 100, если это попадание его выводит из строя", "the chance of the explosion in percent; 100 if this hit takes it out"),
        "morale_loss": ("сколько снять боевого духа", "how much morale to take"),
        "fire": ("сколько ходов юнит будет гореть, итоговое значение", "how many turns the unit will burn, the final value"),
        "attacker_turns_since_spotted": ("для стороны цели: 0 — атакующий раскрыт, 255 — не замечен", "for the target's side: 0 means the attacker is revealed, 255 means not spotted"),
        "attacker_turns_left_spotted_for_snipers": ("сколько ходов снайперы стороны цели ещё видят атакующего", "for how many turns the snipers of the target's side still see the attacker"),
    },
    "healUnit": {
        "medikit_action_type": ("что делает аптечка, сумма: 1 лечение, 2 стимулятор, 4 обезболивающее. Заряд к этому моменту уже списан", "what the medikit does, a sum: 1 heal, 2 stimulant, 4 painkiller. The charge is already spent by now"),
        "body_part": ("какую часть тела лечат, <code>BODYPART_*</code>", "which body part is healed, <code>BODYPART_*</code>"),
        "wound_recovery": ("сколько ран закрыть", "how many wounds to close"),
        "health_recovery": ("сколько вернуть здоровья; только если на этой части тела есть рана", "how much health to return; only if this body part has a wound"),
        "energy_recovery": ("стимулятор: сколько вернуть энергии", "stimulant: how much energy to return"),
        "stun_recovery": ("стимулятор: сколько снять оглушения", "stimulant: how much stun to take away"),
        "mana_recovery": ("стимулятор: сколько вернуть маны", "stimulant: how much mana to return"),
        "morale_recovery": ("обезболивающее: сколько вернуть боевого духа", "painkiller: how much morale to return"),
        "painkiller_recovery": ("обезболивающее: сила в сотых, 100 значит 1,0", "painkiller: the strength in hundredths, 100 means 1.0"),
    },
    "skillUseUnit": {
        "continue_action": ("1 — действие идёт дальше, 0 — отменить: мод всё сделал сам", "1 means the action goes on, 0 cancels it: the mod did it all itself"),
        "spend_tu": ("1 — списать стоимость действия; по умолчанию 0", "1 spends the cost of the action; 0 by default"),
    },
    "returnFromMissionUnit": {
        "recovery_time": ("сколько дней солдат лечит раны", "for how many days the soldier heals wounds"),
        "mana_loss": ("сколько маны не хватало в конце боя", "how much mana was missing at the end of the battle"),
        "health_loss": ("сколько здоровья не хватало в конце боя", "how much health was missing at the end of the battle"),
        "final_mana_loss": ("сколько маны не хватает на базе", "how much mana is missing at the base"),
        "final_health_loss": ("сколько здоровья не хватает на базе", "how much health is missing at the base"),
    },
    "awardExperience": {
        "experience_multipler": ("сколько опыта в процентах: 100 одно начисление, 250 два и шанс 50% на третье; 0 ничего", "how much experience in percent: 100 is one award, 250 is two and a 50% chance of a third; 0 is nothing"),
        "experience_type": ("вид опыта, номер", "the kind of experience, a number"),
    },
    "tryPsiAttackItem": {"psi_attack_success": ("запас успеха, больше нуля: атака прошла. Идёт дальше в <code>tryPsiAttackUnit</code>", "the margin of success, above zero the attack lands. Goes on to <code>tryPsiAttackUnit</code>")},
    "tryPsiAttackUnit": {"psi_attack_success": ("запас успеха, больше нуля: атака прошла", "the margin of success, above zero the attack lands")},
    "tryMeleeAttackItem": {"melee_attack_success": ("запас успеха: сила атаки минус случайное число минус защита. Больше нуля: удар прошёл, поэтому +1 здесь это примерно +1% шанса. Идёт дальше в <code>tryMeleeAttackUnit</code>", "the margin of success: attack strength minus a random number minus defense. Above zero the hit lands, so +1 here is about +1% of chance. Goes on to <code>tryMeleeAttackUnit</code>")},
    "tryMeleeAttackUnit": {"melee_attack_success": ("запас успеха, больше нуля: удар прошёл", "the margin of success, above zero the hit lands")},
    "selectMoveSoundUnit": {"sound_index": ("какой звук играть; меньше нуля: без звука", "which sound to play; below zero: no sound")},
    "newMonthCountry": {
        "fundingChange": ("на сколько меняется финансирование", "how much the funding changes"),
        "satisfaction": ("настроение, <code>SATISFACTION_*</code>; другое значение: ошибка", "the mood, <code>SATISFACTION_*</code>; another value is an error"),
        "formPact": ("1: заключить пакт", "1: sign a pact"),
        "cancelPact": ("1: разорвать пакт", "1: cancel a pact"),
    },
    "detectUfoFromBase": {
        "detection_type": ("как заметит, <code>DETECTION_*</code>; другое значение: ошибка", "how it detects, <code>DETECTION_*</code>; another value is an error"),
        "detection_chance": ("шанс в процентах", "the chance in percent"),
    },
    "detectUfoFromCraft": {
        "detection_type": ("как заметит, <code>DETECTION_*</code>; другое значение: ошибка", "how it detects, <code>DETECTION_*</code>; another value is an error"),
        "detection_chance": ("шанс в процентах", "the chance in percent"),
    },
    "reactionWeaponAction": REACTION_OUT,
    "reactionUnitAction": REACTION_OUT,
    "reactionUnitReaction": REACTION_OUT,
    "visibilityUnit": {
        "current_visibility": ("больше нуля: цель видна. Это запас видимости, а не шанс", "above zero the target is seen. It is a margin of visibility, not a chance"),
        "default_visibility": ("запас видимости без скриптов", "the margin of visibility without scripts"),
    },
    "aiCalculateTargetWeight": {
        "current_target_weight": ("вес цели: чем больше, тем охотнее ИИ её выберет", "the target's weight: the higher, the more readily the AI picks it"),
        "default_target_weight": ("вес из рулсета", "the weight from the ruleset"),
    },
    "sellCostItem": {
        "cost_current": ("цена продажи с поправками", "the sale price with adjustments"),
        "cost_base": ("цена продажи из рулсета", "the sale price from the ruleset"),
    },
    "buyCostItem": {
        "cost_current": ("цена покупки с поправками", "the purchase price with adjustments"),
        "cost_base": ("цена покупки из рулсета", "the purchase price from the ruleset"),
    },
    "psiDefenceBonusStats": {"bonus": ("итог защиты от пси", "the final psi defence")},
    "meleeDodgeBonusStats": {"bonus": ("итог уклонения", "the final dodge")},
    "damageBonusBonusStats": {"bonus": ("итоговая сила предмета", "the item's final power")},
    "meleeBonusBonusStats": {"bonus": ("итоговая сила удара", "the final melee power")},
    "accuracyMultiplierBonusStats": {"bonus": ("итог расчёта точности", "the final accuracy")},
    "meleeMultiplierBonusStats": {"bonus": ("итог расчёта точности", "the final accuracy")},
    "throwMultiplierBonusStats": {"bonus": ("итог расчёта точности", "the final accuracy")},
    "closeQuartersMultiplierBonusStats": {"bonus": ("итог расчёта точности", "the final accuracy")},
    "timeRecoveryBonusStats": {"bonus": ("итог, сколько очков времени за ход", "the final amount of time units per turn")},
    "timeSoldierRecoveryBonusStats": {"bonus": ("сколько очков времени даёт бонус", "the amount of time units the bonus gives")},
    "energyRecoveryBonusStats": {"bonus": ("итог, сколько энергии за ход", "the final amount of energy per turn")},
    "energySoldierRecoveryBonusStats": {"bonus": ("сколько энергии даёт бонус", "the amount of energy the bonus gives")},
    "moraleRecoveryBonusStats": {"bonus": ("итог, сколько боевого духа за ход", "the final amount of morale per turn")},
    "moraleSoldierRecoveryBonusStats": {"bonus": ("сколько боевого духа даёт бонус", "the amount of morale the bonus gives")},
    "healthRecoveryBonusStats": {"bonus": ("итог, сколько здоровья за ход", "the final amount of health per turn")},
    "healthSoldierRecoveryBonusStats": {"bonus": ("сколько здоровья даёт бонус", "the amount of health the bonus gives")},
    "manaRecoveryBonusStats": {"bonus": ("итог, сколько маны за ход", "the final amount of mana per turn")},
    "manaSoldierRecoveryBonusStats": {"bonus": ("сколько маны даёт бонус", "the amount of mana the bonus gives")},
    "stunRecoveryBonusStats": {"bonus": ("итог, сколько оглушения за ход", "the final amount of stun per turn")},
    "stunSoldierRecoveryBonusStats": {"bonus": ("сколько оглушения даёт бонус", "the amount of stun the bonus gives")},
}

OUT_WORDS["hitUnitAmmo"] = OUT_WORDS["hitUnit"]
OUT_WORDS["damageUnitAmmo"] = OUT_WORDS["damageUnit"]
OUT_WORDS["damageSpecialUnitAmmo"] = OUT_WORDS["damageSpecialUnit"]

HIT_HEAD = "game.on(\"hitUnit\", function(unit, damaging_item, weapon_item, attacker, battle, skill, orig_power, damaging_type, battle_action, out)\n"
DAMAGE_HEAD = "game.on(\"damageUnit\", function(unit, damaging_item, weapon_item, attacker, battle, skill, currPower, orig_power, part, side, damaging_type, battle_action, out)\n"

# Рецепты проверяет в настоящем бою tools/lua_stage2/recipes.py: код берётся отсюда как есть.
RECIPES = [
    {"id": "regen", "ru": "Регенерация", "en": "Regeneration",
     "ru_text": "Каждый живой юнит в начале своего хода получает 1 здоровья. <code>newTurnUnit</code> приходит на ход каждой стороны, поэтому <code>side</code> сравнивается со стороной юнита.",
     "en_text": "Each living unit gets 1 health at the start of its own turn. <code>newTurnUnit</code> comes on the turn of each side, so <code>side</code> is compared with the unit's side.",
     "code": "game.on(\"newTurnUnit\", function(unit, battle, turn, side)\n"
             "  if side == unit:getFaction() and not unit:isKilled() and not unit:isStunned() then\n"
             "    unit:addHealth(1)\n"
             "  end\n"
             "end)\n"},
    {"id": "headshot", "ru": "Попадание в голову и сообщение на экране", "en": "A head hit and a message on the screen",
     "ru_text": "Сила удваивается до вычитания брони, игрок видит сообщение.",
     "en_text": "The power doubles before the armor is subtracted, the player sees a message.",
     "code": HIT_HEAD +
             "  if out.part == game.BODYPART_HEAD then\n"
             "    out.power = out.power * 2\n"
             "    battle:flashMessage(\"Head hit! Power {0}\", out.power)\n"
             "  end\n"
             "end)\n"},
    {"id": "weapon", "ru": "Своё оружие", "en": "A particular weapon",
     "ru_text": "Прибавка к силе по типу оружия из рулсета. Подставьте свои типы. <code>weapon_item</code> может быть nil, поэтому сначала проверка.",
     "en_text": "A bonus to the power by the weapon type from the ruleset. Put your own types in. <code>weapon_item</code> may be nil, so it is checked first.",
     "code": "local BONUS = { STR_PISTOL = 5, STR_RIFLE = 10 }\n\n" + HIT_HEAD +
             "  local bonus = weapon_item and BONUS[weapon_item:getRuleItem():getType()]\n"
             "  if bonus then\n"
             "    out.power = out.power + bonus\n"
             "  end\n"
             "end)\n"},
    {"id": "shock", "ru": "Ранение отнимает очки времени", "en": "A wound takes time units",
     "ru_text": "Сколько здоровья снято, столько же снимается очков времени.",
     "en_text": "As much health as is taken, as many time units are taken.",
     "code": DAMAGE_HEAD +
             "  if out.to_health > 0 then\n"
             "    out.to_time = out.to_time + out.to_health\n"
             "  end\n"
             "end)\n"},
    {"id": "rage", "ru": "Память в теге: ярость", "en": "Memory in a tag: rage",
     "ru_text": "Ранения копятся в теге и в начале своего хода возвращают боевой дух. Переменная Lua обнулилась бы при загрузке сейва, тег сохраняется. Тег объявляется в файле <code>Ruleset/my_mod.rul</code>:",
     "en_text": "Wounds add up in a tag and return morale at the start of the unit's own turn. A Lua variable would be reset when a save is loaded, a tag is saved. The tag is declared in the file <code>Ruleset/my_mod.rul</code>:",
     "rul": "extended:\n  tags:\n    BattleUnit:\n      MY_RAGE: int\n",
     "code": DAMAGE_HEAD +
             "  if out.to_health > 0 then\n"
             "    unit:setTag(\"MY_RAGE\", unit:getTag(\"MY_RAGE\") + 1)\n"
             "  end\n"
             "end)\n\n"
             "game.on(\"newTurnUnit\", function(unit, battle, turn, side)\n"
             "  local rage = unit:getTag(\"MY_RAGE\")\n"
             "  if side == unit:getFaction() and rage > 0 then\n"
             "    unit:addMorale(rage * 5)\n"
             "    unit:setTag(\"MY_RAGE\", 0)\n"
             "  end\n"
             "end)\n"},
    {"id": "recharge", "ru": "Подзарядка патронов", "en": "Rounds recharge",
     "ru_text": "В начале хода игрока каждый заряженный в оружие магазин получает 1 патрон, у всех сторон. Владельца у него нет: он лежит в оружии.",
     "en_text": "At the start of the player's turn each clip loaded into a weapon gets 1 round, on all sides. It has no owner: it lies in the weapon.",
     "code": "game.on(\"newTurnItem\", function(item, battle, turn, side)\n"
             "  if side == game.FACTION_PLAYER and item:isAmmo() then\n"
             "    local now, max = item:getAmmoQuantity(), item:getAmmoQuantityMax()\n"
             "    if now < max then\n"
             "      item:setAmmoQuantity(now + 1)\n"
             "    end\n"
             "  end\n"
             "end)\n"},
    {"id": "medikit", "ru": "Аптечка лечит вдвое", "en": "A medikit heals twice as much",
     "ru_text": "Здоровье возвращается, только если на этой части тела есть рана.",
     "en_text": "Health returns only if this body part has a wound.",
     "code": "game.on(\"healUnit\", function(actor, item, battle, target, battle_action, out)\n"
             "  out.health_recovery = out.health_recovery * 2\n"
             "end)\n"},
    {"id": "recovery", "ru": "Быстрое выздоровление", "en": "A quick recovery",
     "ru_text": "После миссии солдат лечит раны вдвое быстрее. Деление целое: в <code>out</code> принимаются только целые числа, <code>/</code> дал бы ошибку.",
     "en_text": "After a mission a soldier heals wounds twice as fast. The division is whole: <code>out</code> takes only whole numbers, <code>/</code> would give an error.",
     "code": "game.on(\"returnFromMissionUnit\", function(unit, battle, soldier, out)\n"
             "  out.recovery_time = out.recovery_time // 2\n"
             "end)\n"},
    {"id": "officer", "ru": "Офицер поднимает дух", "en": "An officer lifts morale",
     "ru_text": "Пока в отряде стоит на ногах сержант или старше, каждый свой ход боевой дух +5. Список юнитов берётся раз в ход, а не на каждого юнита: он стоит тактов.",
     "en_text": "While a sergeant or higher in the squad is on their feet, morale goes up by 5 every turn of the side. The list of units is taken once a turn, not for every unit: it costs ticks.",
     "code": "local seen_turn, officer\n"
             "game.on(\"newTurnUnit\", function(unit, battle, turn, side)\n"
             "  if side ~= game.FACTION_PLAYER or unit:getFaction() ~= side then\n"
             "    return\n"
             "  end\n"
             "  if seen_turn ~= turn then\n"
             "    seen_turn = turn\n"
             "    officer = false\n"
             "    for _, u in ipairs(battle:getUnits(side)) do\n"
             "      if u:getRankUnified() >= game.UNIT_RANK_SERGEANT and not u:isStunned() then\n"
             "        officer = true\n"
             "      end\n"
             "    end\n"
             "  end\n"
             "  if officer then\n"
             "    unit:setMorale(unit:getMorale() + 5)\n"
             "  end\n"
             "end)\n"},
    {"id": "veteran", "ru": "Закалка в бою", "en": "Hardened in battle",
     "ru_text": "Каждый свой ход храбрость юнита +1. <code>addStat</code> у юнита действует только на этот бой, постоянно менять характеристику можно у <code>soldier</code>.",
     "en_text": "Every turn of the side a unit's bravery goes up by 1. <code>addStat</code> of a unit works only for this battle, a stat changes for good at <code>soldier</code>.",
     "code": "game.on(\"newTurnUnit\", function(unit, battle, turn, side)\n"
             "  if side == unit:getFaction() then\n"
             "    unit:addStat(\"bravery\", 1)\n"
             "  end\n"
             "end)\n"},
    {"id": "experience", "ru": "Опыт вдвое", "en": "Double experience",
     "ru_text": "Имя <code>experience_multipler</code> с опечаткой пришло из Y-script. Здесь только <code>out</code>: этот обработчик только читает.",
     "en_text": "The misspelt name <code>experience_multipler</code> comes from the Y-script. Only <code>out</code> changes here: this handler only reads.",
     "code": "game.on(\"awardExperience\", function(attacker, unit, weapon, battle_action, out)\n"
             "  out.experience_multipler = out.experience_multipler * 2\n"
             "end)\n"},
    {"id": "backstab", "ru": "Удар в спину", "en": "A stab in the back",
     "ru_text": "Шанс удара сбоку и сзади +20. ИИ считает так же и свои прогнозы: без <code>math.random</code>, без журнала на каждый вызов.",
     "en_text": "The chance of a hit from the side and the rear goes up by 20. The AI's forecasts work it out too: no <code>math.random</code>, no log on every call.",
     "code": "game.on(\"tryMeleeAttackItem\", function(item, attacker, victim, is_same_faction, skill, attack_strength, defense_strength, battle_action, arc_to_attacker, defense_strength_penalty, battle, out)\n"
             "  if arc_to_attacker >= 2 then\n"
             "    out.melee_attack_success = out.melee_attack_success + 20\n"
             "  end\n"
             "end)\n"},
    {"id": "month", "ru": "Страна ценит победы", "en": "A country values victories",
     "ru_text": "Если игрок набрал за месяц больше очков, чем враг, страна не снижает финансирование.",
     "en_text": "If the player scored more than the enemy this month, a country does not cut the funding.",
     "code": "game.on(\"newMonthCountry\", function(country, geoscape_game, totalXcomScore, totalAlienScore, out)\n"
             "  if totalXcomScore > totalAlienScore and out.fundingChange < 0 then\n"
             "    out.fundingChange = 0\n"
             "  end\n"
             "end)\n"},
    {"id": "shop", "ru": "Цена в магазине", "en": "A price in the shop",
     "ru_text": "Всё продаётся на четверть дороже. Обработчик приходит при каждой строке магазина: случайных чисел в нём быть не может, тяжёлых расчётов не нужно.",
     "en_text": "Everything sells a quarter dearer. The handler comes for each row of the shop: there can be no random numbers in it, and heavy work is not needed.",
     "code": "game.on(\"sellCostItem\", function(item_rule, geoscape_game, difficulty_coefficient, out)\n"
             "  out.cost_current = out.cost_current * 125 // 100\n"
             "end)\n"},
    {"id": "alert", "ru": "Свой шанс реакции", "en": "A reaction chance of your own",
     "ru_text": "Реакция на цель сзади вдвое вероятнее. Шанс считается перед каждым выстрелом реакции и идёт дальше в <code>reactionUnitReaction</code>.",
     "en_text": "A reaction to a target from behind is twice as likely. The chance is worked out before each reaction shot and goes on to <code>reactionUnitReaction</code>.",
     "code": "game.on(\"reactionUnitReaction\", function(action_unit, reaction_unit, reaction_weapon, reaction_battle_action, reaction_count, weapon, skill, battle_action, action_target, move, arc_to_action_unit, battle_game, out)\n"
             "  if arc_to_action_unit >= 3 then\n"
             "    out.reaction_chance = out.reaction_chance * 2\n"
             "  end\n"
             "end)\n"},
    {"id": "camo", "ru": "Камуфляж", "en": "Camouflage",
     "ru_text": "Юнит с тегом брони <code>MY_CAMO</code> не виден дальше 10 клеток. Обработчик идёт на каждую пару юнитов при каждом шаге: только простой расчёт, без журнала.",
     "en_text": "A unit in armor with the tag <code>MY_CAMO</code> is not seen beyond 10 tiles. The handler comes for each pair of units at each step: only simple work, no log.",
     "rul": "extended:\n  tags:\n    RuleArmor:\n      MY_CAMO: int\narmors:\n  - type: STR_NONE_UC\n    tags:\n      MY_CAMO: 1\n",
     "code": "game.on(\"visibilityUnit\", function(observer_unit, target_unit, target_tile, distance, distance_max, distance_target_max, smoke_density, fire_density, smoke_density_near_observer, fire_density_near_observer, out)\n"
             "  if target_unit and target_unit:getRuleArmor():getTag(\"MY_CAMO\") == 1 and distance > 10 * 16 then\n"
             "    out.current_visibility = 0\n"
             "  end\n"
             "end)\n"},
    {"id": "tired", "ru": "Раненый устаёт", "en": "The wounded get tired",
     "ru_text": "Раненый вполовину юнит получает за ход на 10 очков времени меньше. <code>out.bonus</code> приходит с расчётом рулсета, так же устроены сила и точность оружия, защита от пси и уклонение.",
     "en_text": "A unit at half health gets 10 time units less per turn. <code>out.bonus</code> comes with the ruleset's calculation, the power and accuracy of a weapon, psi defence and dodge work the same way.",
     "code": "game.on(\"timeRecoveryBonusStats\", function(unit, external_bonuses, weapon, ammo, battle_action, skill, out)\n"
             "  if unit:getHealth() * 2 < unit:getHealthMax() then\n"
             "    out.bonus = out.bonus - 10\n"
             "  end\n"
             "end)\n"},
    {"id": "nerds", "ru": "Строка на странице для нердов", "en": "A row on the nerds' page",
     "ru_text": "Своя строка на странице предмета. Игрок её только читает, на бой она не влияет.",
     "en_text": "A row of your own on an item's page. The player only reads it, it does not affect the battle.",
     "code": "game.on(\"statsForNerdsItem\", function(item_rule, nerds, geoscape_game)\n"
             "  if item_rule:isTwoHanded() then\n"
             "    nerds:addTextRow(\"My mod\", \"two-handed: slower reactions\")\n"
             "  end\n"
             "end)\n"},
    {"id": "other_mod", "ru": "Поиск правила другого мода", "en": "Looking up another mod's rule",
     "ru_text": "Мод проверяет, стоит ли другой мод: нет такого правила, <code>getRuleItem</code> вернёт nil, ошибки не будет.",
     "en_text": "A mod checks whether another mod is installed: without such a rule <code>getRuleItem</code> returns nil, there is no error.",
     "code": "local other = game.getRules():getRuleItem(\"STR_ALIEN_ALLOYS\")\n"
             "if other then\n"
             "  game.log(\"found: \" .. other:getType())\n"
             "end\n"},
    {"id": "bank", "ru": "Свой экран: пиратский банк", "en": "A screen of your own: the pirate bank",
     "ru_text": "Экран нужно объявить и разрешить: в <code>metadata.yml</code> мода <code>luaApi: 2</code> и <code>luaCaps: [screens]</code>. Благодаря <code>menu</code> игрок найдёт его на экране модов: кнопка в меню паузы или клавиша. Деньги лежат в теге кампании и живут в сейве.",
     "en_text": "A screen has to be declared and allowed: <code>luaApi: 2</code> and <code>luaCaps: [screens]</code> in the mod's <code>metadata.yml</code>. Thanks to <code>menu</code> the player finds it on the mods' screen: a button in the pause menu or a key. The money lies in a tag of the campaign and lives in the save.",
     "api": 2, "caps": "screens",
     "rul": "extended:\n  tags:\n    GeoscapeGame:\n      MY_BANK: int\nextraStrings:\n  - type: en-US\n    strings:\n      STR_MY_BANK: \"The pirate bank\"\n      STR_MY_DEPOSIT: \"Deposit 1000\"\n      STR_MY_CLOSE: \"Close\"\n",
     "code": "local function balance()\n"
             "  return game.getGeoscape():getTag(\"MY_BANK\")\n"
             "end\n\n"
             "game.screen(\"bank\", function(ui)\n"
             "  ui:window{ x = 32, y = 20, w = 256, h = 160 }\n"
             "  ui:text{ x = 40, y = 30, w = 240, h = 17, text = \"STR_MY_BANK\", big = true, align = \"center\" }\n"
             "  local sum = ui:text{ x = 50, y = 60, w = 220, h = 10, text = \"\" }\n"
             "  local function show()\n"
             "    sum:setText(tostring(balance()))\n"
             "  end\n"
             "  show()\n"
             "  ui:button{ x = 50, y = 130, w = 106, h = 18, text = \"STR_MY_DEPOSIT\", onClick = function()\n"
             "    game.getGeoscape():setTag(\"MY_BANK\", balance() + 1000)\n"
             "    show()\n"
             "  end }\n"
             "  ui:button{ x = 164, y = 130, w = 106, h = 18, text = \"STR_MY_CLOSE\", onClick = function()\n"
             "    ui:close()\n"
             "  end }\n"
             "end, { menu = \"STR_MY_BANK\" })\n"},
    {"id": "tithe", "ru": "Деньги: десятина раз в неделю", "en": "Money: a tithe once a week",
     "ru_text": "Раз в семь суток кампании приносит 50 000. Нужны <code>luaApi: 2</code> и <code>luaCaps: [economy]</code>. Счётчик суток лежит в теге кампании: переменная Lua обнулилась бы после первого боя. Приход виден в отчёте месяца. Снимете мод: уже полученные деньги останутся.",
     "en_text": "Once in seven days the campaign earns 50,000. It takes <code>luaApi: 2</code> and <code>luaCaps: [economy]</code>. The day counter is in a campaign tag: a Lua variable would be reset after the first battle. The income shows in the month's report. Remove the mod: the money already received stays.",
     "api": 2, "caps": "economy",
     "rul": "extended:\n  tags:\n    GeoscapeGame:\n      MY_TITHE_DAYS: int\n",
     "code": "game.on(\"newDay\", function(geoscape_game)\n"
             "  local days = geoscape_game:getTag(\"MY_TITHE_DAYS\") + 1\n"
             "  if days >= 7 then\n"
             "    geoscape_game:addFunds(50000)\n"
             "    days = 0\n"
             "  end\n"
             "  geoscape_game:setTag(\"MY_TITHE_DAYS\", days)\n"
             "end)\n"},
]

CONST_WORDS = {
    "BODYPART": ("части тела: part", "body parts: part"),
    "SIDE": ("стороны юнита: side в обработчиках урона и в броне", "sides of a unit: side in the damage handlers and in armor"),
    "FACTION": ("стороны боя", "sides of the battle"),
    "BA": ("действия: battle_action", "actions: battle_action"),
    "DT": ("типы урона: damaging_type", "damage types: damaging_type"),
    "UNIT": ("звания: getRankUnified", "ranks: getRankUnified"),
    "GENDER": ("пол", "gender"),
    "LOOK": ("внешность", "looks"),
    "MT": ("способ передвижения", "movement types"),
    "STT": ("особые клетки", "special tiles"),
    "DIFF": ("сложность", "difficulty"),
    "BT": ("вид предмета: getBattleType", "item kinds: getBattleType"),
    "BAM": ("как идёт юнит: move", "how a unit moves: move"),
    "BMA": ("действия аптечки: medikit_action_type", "medikit actions: medikit_action_type"),
    "SATISFACTION": ("настроение страны: satisfaction", "a country's mood: satisfaction"),
    "UFO": ("состояние НЛО: getStatus", "UFO status: getStatus"),
    "DETECTION": ("обнаружение НЛО: detection_type", "UFO detection: detection_type"),
    "INV": ("виды ячеек: ruleInventory:getType", "slot kinds: ruleInventory:getType"),
}

TEXT = {
    "ru": {
        "title": "Lua API для модов OXCE-HD, версия {api}",
        "intro": "Мод пишется в файле <code>lua/main.lua</code> своей папки, в <code>metadata.yml</code> стоит <code>luaApi: {api}</code>. "
                 "Lua запускает только игра, лаунчер код мода не исполняет. API покрывает большую часть возможностей Y-script и не выходит за них. Страница описывает его полностью: чего здесь нет, того из Lua сделать нельзя. "
                 "Имена обработчиков и выходных значений те же, что у Y-script.",
        "h_where": "Где это работает",
        "where": "Только в нашей сборке OXCE-HD. Обычный OXCE не знает ключ <code>luaApi</code> и запустит мод без Lua: рулсеты мода будут работать, а код нет. Если мод нужен и там, пишите его на Y-script.",
        "h_can": "Что мод может менять",
        "th_area": "Что", "th_lua": "Из Lua",
        "can_rows": [
            ("Юнит в бою", "очки времени, здоровье, мана, энергия, оглушение, боевой дух, горение, броня сторон, раны, характеристики и стоимость хода на этот бой, превращение при гибели, способ передвижения, раскрытие снайперам"),
            ("Попадание и урон", "сила, часть тела, сторона, что сколько снимает, шанс превращения и взрыва, поджог, раскрытие атакующего"),
            ("Аптечка и навык", "сколько лечит аптечка, идёт ли действие навыка дальше, списывать ли за него очки времени"),
            ("Предмет в бою", "патроны, таймер и взведение взрывателя, заряды аптечки, стоимость переноса"),
            ("Бой", "сообщения, скрытие юнита, открытие клеток игроку, уровень снаряжения врага, списки юнитов и предметов"),
            ("Солдат", "постоянные характеристики, раны, недостающие здоровье и мана"),
            ("Расчёты движка", "шанс пси-атаки и удара, сколько опыта за попадание, звук шага, замечено ли НЛО, итог месяца для страны"),
            ("Реакции и видимость", "шанс реакции, видит ли юнит цель, камуфляж, вес цели для ИИ"),
            ("Формулы из рулсета", "сила и точность оружия, защита от пси, уклонение, восстановление за ход"),
            ("Магазин и справка", "цены покупки и продажи, свои строки на странице для нердов"),
            ("Чужие правила", "найти правила предмета, брони, юнита, навыка, исследования и ячейки инвентаря по имени"),
            ("Конец миссии", "срок лечения, сколько здоровья и маны солдат недобирает на базе"),
            ("Служебное", "теги юнита, предмета, боя, солдата и геоскейпа, журнал"),
        ],
        "cannot": "<b>Из Lua нельзя:</b>"
                  "<ul><li>наука и производство; базы и деньги только с разрешением <code>economy</code>. Без него геоскейп можно читать, а менять только теги, итог месяца для страны, обнаружение НЛО и цены;</li>"
                  "<li>создавать и двигать юнитов и предметы, менять карту;</li>"
                  "<li>спрайты и перекраску: эти обработчики Y-script идут из потоков рисования на каждый кадр, для них есть Y-script;</li>"
                  "<li>выбор действий ИИ, кроме веса цели.</li></ul>"
                  "<b>Рядом с кодом работает обычный OXCE.</b> Папка <code>Ruleset/</code> мода с файлами <code>.rul</code> подключается как у любого мода: там меняются числа предметов, брони и юнитов, исследования и всё остальное, что умеют рулсеты, в том числе Y-script. "
                  "Нужна новая возможность в Lua — напишите нам тикет с описанием, что мод должен делать.",
        "h_args": "Аргументы",
        "args_note": "Обработчики получают их в порядке из таблицы выше. Значения, которые могут быть nil, проверяйте перед вызовом метода, иначе будет ошибка.",
        "h_outs": "Что значит каждое значение out",
        "h_recipes": "Рецепты",
        "recipes": "Каждый рецепт — целый файл <code>lua/main.lua</code>. Все проверены в настоящем бою. В одном файле может быть сколько угодно подписок, в том числе на один обработчик: они идут в порядке записи.",
        "h_start": "С чего начать",
        "start": "<li>В лаунчере: Настройки, «Режим мододела», «Создать мод». Появится папка с рабочим примером.</li>"
                 "<li>Запустите игру и начните бой. Строки <code>game.log</code> и <code>print</code> идут в <code>user/openxcom.log</code>.</li>"
                 "<li>Поправьте <code>main.lua</code> и нажмите <b>Ctrl+F5</b> в бою: код всех модов перечитается, итог на экране. Обычное быстрое сохранение F5 работает как раньше.</li>",
        "h_events": "Обработчики",
        "events": "Подписка: <code>game.on(\"имя\", функция)</code>. Аргументы идут в порядке входа Y-script, последним — таблица <code>out</code> с выходными значениями, если они есть. "
                  "Значения в <code>out</code> принимаются целыми и только все разом: одно плохое значение — ошибка, остальные не применяются. "
                  "Обработчики с пометкой «только читает» меняют только <code>out</code>: как и в Y-script, объекты там неизменяемые, и вызов <code>set...</code> или <code>add...</code> в них — ошибка. "
                  "На одном обработчике сначала работает Y-script, затем Lua в порядке загрузки модов.",
        "th_event": "Обработчик", "th_when": "Когда", "th_out": "out",
        "readonly": "только чтение",
        "only_reads": "только читает",
        "pure": "без случайных чисел",
        "h_api": "Объекты",
        "th_method": "Метод", "th_what": "Что делает",
        "h_game": "Таблица game",
        "game": "<code>game.on(имя, функция)</code> подписывает функцию на обработчик, только пока грузится <code>main.lua</code>. <code>game.log(...)</code> и <code>print(...)</code> пишут строку в журнал игры. <code>game.getRules()</code> даёт все правила игры, в том числе из других модов, таблица <code>rules</code> выше. С <code>luaApi: 2</code>: <code>game.getBattle()</code> и <code>game.getGeoscape()</code> дают бой и кампанию там, где обработчик их не получает, например из щелчка на экране; боя нет: nil. <code>game.getBases()</code> даёт таблицу баз игрока, в бою и в щелчке тоже. Только разрешение <code>screens</code>: <code>game.screen(имя, функция[, { menu = \"STR_NAME\", interface = \"pauseMenu\" }])</code> объявляет экран, только пока грузится <code>main.lua</code>; <code>game.openScreen(имя)</code> открывает его из обработчика.",
        "h_caps": "Разрешения и свои экраны",
        "caps": "<p>С <code>luaApi: 2</code> у мода есть разрешения: слова в <code>metadata.yml</code>, например <code>luaCaps: [screens, economy]</code>. Без слова метода для мода нет: вызов даёт ошибку Lua с названием разрешения. Неизвестное слово или <code>luaCaps</code> при <code>luaApi: 1</code> отключают Lua мода. Сейчас есть два слова: <code>screens</code> и <code>economy</code>.</p>"
                "<ul><li>Экран строится из виджетов игры в координатах 320×200, поэтому работает при любом разрешении и масштабе.</li>"
                "<li>Открывает его игрок на экране модов, если у <code>game.screen</code> есть <code>menu</code>, или обработчик через <code>game.openScreen</code>: тогда экран откроется, когда игра закончит свой шаг, в бою это может быть после анимации или после брифинга. Пока экран открыт, игра под ним стоит.</li>"
                "<li>Функция построения и <code>onClose</code> только читают: без случайных чисел, записи и <code>openScreen</code>. Открытый и закрытый экран не меняет игру. В щелчке можно всё, что можно в обработчике.</li>"
                "<li>Обработчики только для чтения, в том числе старые обработчики геоскейпа и страницы для нердов, экран не открывают.</li>"
                "<li>Esc закрывает экран всегда. Ошибка в построении закрывает экран и пишется в журнал. Кадровых обработчиков и таймеров нет: только реакция на действие.</li>"
                "<li>Ручки виджетов живут, пока экран открыт, после закрытия: ошибка Lua.</li>"
                "<li>Потолки: 64 виджета, 2000 строк списка, 8 столбцов, 256 пунктов, 64 экрана на мод, вложенность и очередь вместе 4, один экран на вызов, 8 экранов за ход боя или день кампании. Сверх потолка: ошибка мода, игра живёт.</li></ul>"
                "<p><code>economy</code>: деньги, склад, персонал и наём, только вне боя.</p>"
                "<ul><li><b>Переменные Lua обнуляются при каждом новом бою и загрузке.</b> Счётчик дней в переменной забудется после первого боя. Всё, что должно пережить бой, держите в тегах, для кампании раздел <code>GeoscapeGame</code>.</li>"
                "<li>Читать можно без слова: <code>game.getBases()</code>, <code>geoscape:getFunds()</code>, методы чтения <code>base</code>. Менять можно только со словом и только в <code>newHour</code>, <code>newDay</code>, <code>newMonth</code>, в щелчке на экране и в функции <code>done</code> у <code>hireSoldier</code>. В бою нельзя: конец боя сам считает склад.</li>"
                "<li>Эти три обработчика могут открыть экран: <code>game.openScreen</code>. <code>battleStart</code> и <code>battleEnd</code> только читают.</li>"
                "<li>Деньги, склад и персонал меняются сразу. Ошибка Lua в том же вызове отменяет всё, что вызов успел, и наём тоже.</li>"
                "<li><code>addFunds</code> попадает в приход или расход месяца, как обычные деньги. В <code>newMonth</code> отчёт прошлого месяца уже посчитан: деньги идут в новый месяц. Долг ниже порога даёт обычное предупреждение совета, затем обычный проигрыш.</li>"
                "<li><code>hireSoldier(type[, done])</code> бесплатный: цену, если нужна, снимает сам мод. Солдат создаётся после обработчика и едет на базу обычной пересылкой. <code>done(soldier)</code> получает нового солдата, <code>done(nil, причина)</code> отказ: нет мест или месячный лимит. Объекты из обработчика в <code>done</code> уже мертвы, базу берите заново через <code>game.getBases()</code>.</li>"
                "<li>Склад сверх лимита игра обрабатывает как обычно: окно продажи, которое нельзя закрыть, пока лишнее не продано. Не выдавайте игроку больше, чем вмещает склад. На Пиратках <code>getStores().used</code> бывает отрицательным: есть предметы с отрицательным размером.</li>"
                "<li>Мод снят: деньги, предметы обычных правил и персонал остаются, отмены нет; теги теряются при новом сохранении. В сейв пишется отметка <code>luaTouched</code>, она остаётся и после снятия мода и видна в отчёте об ошибке.</li>"
                "<li>Потолки: <code>addFunds</code> до ±1 000 000 000 за вызов, предметы и персонал до 1 000 000 000 за вызов, наём 16 за вызов и 64 в сутки. Сверх потолка: ошибка мода, игра живёт.</li></ul>",
        "h_const": "Константы",
        "h_tags": "Теги: память между сохранениями",
        "tags": "Переменные Lua обнуляются при загрузке сейва, в новом бою и по Ctrl+F5. Долгая память — только теги. Тег объявляется в рулсете мода, например в файле <code>Ruleset/my_mod.rul</code>:"
                "<pre>extended:\n  tags:\n    BattleUnit:\n      MY_REGEN: int\n    BattleItem:\n      MY_CHARGE: int</pre>"
                "Разделы по объектам: BattleUnit, BattleItem, BattleGame, GeoscapeGame, GeoscapeSoldier, Country, Ufo, Craft, RuleArmor, RuleItem, RuleSoldier, RuleSoldierBonus, RuleUfo, RuleCraft, RuleCountry, RuleResearch. Имя тега одно на всю игру: то же имя во втором разделе движок отбросит с ошибкой в своём журнале. "
                "В коде имя без приставки: <code>unit:getTag(\"MY_REGEN\")</code>. Чтение и запись незнакомого тега — ошибка: опечатка видна сразу. Тег с одним именем в двух модах — один на двоих. "
                "Значение живёт, пока мод стоит: сейв без мода грузится и играется, но новое сохранение без мода значения теряет.",
        "h_lua": "Что есть в самой Lua",
        "lua": "Базовые функции: {base}. Библиотеки <code>string</code> (без <code>dump</code>), <code>table</code>, <code>math</code> (без <code>randomseed</code>), <code>utf8</code>. "
               "Нет <code>io os debug package require load dofile loadfile coroutine collectgarbage</code>, байткод не загружается. "
               "<code>math.random</code> идёт через генератор игры; пока грузится <code>main.lua</code>, он даёт ошибку: загрузка не должна сдвигать сид боя. "
               "Часов и времени нет.",
        "h_limits": "Лимиты",
        "limits": "<li>Память: {memory} МБ на мод.</li><li>Один вызов обработчика: {instructions} инструкций, {cticks} тактов функций на C (шаблоны строк, <code>string.rep</code>, <code>table.*</code>). "
                  "<code>main.lua</code> при загрузке получает в 10 раз больше инструкций.</li><li>{errors} ошибок подряд выключают мод до Ctrl+F5 или новой загрузки. Игра не падает и не зависает.</li>"
                  "<li>Сообщение <code>flashMessage</code>: до {message} байт текста.</li>",
        "h_errors": "Ошибки",
        "errors": "Ошибка или превышение лимита: выходные значения остаются как до вызова, в <code>user/lua_errors.log</code> пишутся мод, файл, строка, обработчик и текст. "
                  "На экране показывается первая ошибка мода за загрузку и его отключение, а не каждая ошибка. Журнал начинается заново при каждой загрузке игры.",
        "h_know": "Что важно знать",
        "know": "<li>Объект живёт только внутри обработчика, который его получил. Сохранённый в переменной даёт ошибку Lua, игра не падает.</li>"
                "<li>Порядок <code>pairs</code> постоянен только у строковых ключей. Ключи-таблицы и <code>tostring(таблица)</code> зависят от адресов: у двух игроков тот же мод даст разный итог.</li>"
                "<li><code>health_recovery</code> у <code>healUnit</code> действует только на часть тела с раной, как и у Y-script.</li>"
                "<li>Обработчик <code>hitUnit</code>, <code>damageUnit</code>, <code>damageSpecialUnit</code>, их <code>...Ammo</code>, <code>damageBonusBonusStats</code> или <code>meleeBonusBonusStats</code> лишает ИИ точного прогноза выстрела: он считает результат неизвестным и может стрелять по неуязвимой цели.</li>"
                "<li>Обработчики с пометкой «без случайных чисел» приходят из списков, подсказок и прогнозов, и сколько раз, игра не определяет: случайное число там сдвинуло бы общий генератор, поэтому <code>math.random</code>, <code>randomRange</code> и <code>randomChance</code> в них — ошибка. Изменить что-то кроме <code>out</code> там тоже нельзя.</li>"
                "<li><code>visibilityUnit</code>, бонусы и цены идут очень часто: на каждую пару юнитов при каждом шаге, на каждую строку магазина. Тяжёлый код или журнал на каждый вызов замедлят игру, а расчёт списков упрётся в лимит.</li>"
                "<li>Там, где движок считает те же формулы в фоновых потоках, Lua не вызывается: остаётся значение Y-script. Итог действия считается в основном потоке и учитывает Lua.</li>"
                "<li>Методы <code>set...</code> и <code>add...</code> сами держат значение в границах: здоровье и очки времени не выше максимума, боевой дух от 0 до 100. Поэтому прибавка очков времени в начале хода обычно ничего не даёт: они уже полные.</li>"
                "<li><code>damageSpecialUnit</code> приходит и при нулевом уроне, <code>damageUnit</code> только при силе попадания больше нуля.</li>"
                "<li><code>getUnits</code>, <code>getItems</code> и другие списки делают новую таблицу при каждом вызове и платят за каждый элемент. Лимит памяти или тактов даёт ошибку <code>not enough memory</code> или про лимит: вызывайте их редко, а не на каждый предмет каждого хода.</li>"
                "<li><code>tryPsiAttack*</code> и <code>tryMeleeAttack*</code> приходят и при прогнозах ИИ, поэтому там нет места побочным эффектам. <code>math.random</code>, <code>randomRange</code> и <code>randomChance</code> там сдвигают общий генератор, у двух игроков бой разойдётся.</li>"
                "<li>Ошибка мода вне боя пишется в журнал сразу, а на экране появится в ближайшем бою.</li>"
                "<li>Локальный мод может менять механику и сломать сейв. Для опытов лучше отдельная сборка в лаунчере.</li>"
                "<li>В отчёт об ошибке уходят только id мода, версия и отметка <code>[lua local]</code>, код и файлы мода не уходят. Журнал ошибок прикладывается, только если вы сами отметите его в форме.</li>",
    },
    "en": {
        "title": "Lua API for OXCE-HD mods, version {api}",
        "intro": "A mod is written in <code>lua/main.lua</code> in its folder, <code>metadata.yml</code> says <code>luaApi: {api}</code>. "
                 "Only the game runs Lua, the launcher never executes a mod's code. The API covers most of what the Y-script can do and does not go beyond it. This page describes all of it: what is not here cannot be done from Lua. "
                 "The names of the handlers and of the output values are those of the Y-script.",
        "h_where": "Where it works",
        "where": "Only in our OXCE-HD build. Plain OXCE does not know the <code>luaApi</code> key and runs the mod without Lua: the mod's rulesets work and its code does not. If the mod is needed there too, write it in the Y-script.",
        "h_can": "What a mod can change",
        "th_area": "What", "th_lua": "From Lua",
        "can_rows": [
            ("A unit in battle", "time units, health, mana, energy, stun, morale, burning, the armor of each side, wounds, stats and move costs for this battle, turning on death, the movement type, being revealed to snipers"),
            ("A hit and damage", "the power, the body part, the side, what takes how much, the chance of transformation and explosion, setting on fire, revealing the attacker"),
            ("A medikit and a skill", "how much a medikit heals, whether a skill's action goes on, whether it costs time units"),
            ("An item in battle", "rounds, the fuse timer and arming, medikit charges, the moving cost"),
            ("The battle", "messages, concealing a unit, discovering tiles for the player, the enemy's item level, lists of units and items"),
            ("A soldier", "permanent stats, wounds, missing health and mana"),
            ("The engine's calculations", "the chance of psi and melee attacks, how much experience a hit gives, the sound of a step, whether a UFO is detected, the end of a month for a country"),
            ("Reactions and visibility", "the reaction chance, whether a unit sees a target, camouflage, a target's weight for the AI"),
            ("Formulas from the ruleset", "a weapon's power and accuracy, psi defence, dodge, recovery per turn"),
            ("The shop and the reference", "purchase and sale prices, your own rows on the nerds' page"),
            ("Other rules", "find the rules of an item, armor, unit, skill, research or inventory slot by name"),
            ("The end of a mission", "the recovery time, how much health and mana a soldier lacks at the base"),
            ("Service", "tags of units, items, the battle, soldiers and the geoscape, the log"),
        ],
        "cannot": "<b>From Lua you cannot:</b>"
                  "<ul><li>touch research and production; bases and money only with the permission <code>economy</code>. Without it the geoscape can be read, and only tags, a country's month, UFO detection and prices can be changed;</li>"
                  "<li>create or move units and items, change the map;</li>"
                  "<li>touch sprites and recolouring: those Y-script handlers come from the drawing threads on every frame, the Y-script is there for them;</li>"
                  "<li>choose the AI's actions, except a target's weight.</li></ul>"
                  "<b>Plain OXCE works next to the code.</b> The mod's <code>Ruleset/</code> folder with <code>.rul</code> files is loaded as for any mod: the numbers of items, armor and units, research and everything else rulesets can do are changed there, the Y-script included. "
                  "If you need something new in Lua, send us a ticket saying what the mod should do.",
        "h_args": "Arguments",
        "args_note": "Handlers get them in the order of the table above. Check values that may be nil before calling a method on them, otherwise it is an error.",
        "h_outs": "What each out value means",
        "h_recipes": "Recipes",
        "recipes": "Each recipe is a whole <code>lua/main.lua</code> file. All are checked in a real battle. One file can hold any number of subscriptions, several on one handler too: they run in the order they are written.",
        "h_start": "Getting started",
        "start": "<li>In the launcher: Settings, \"Modding mode\", \"Create mod\". A folder with a working example appears.</li>"
                 "<li>Start the game and begin a battle. Lines from <code>game.log</code> and <code>print</code> go to <code>user/openxcom.log</code>.</li>"
                 "<li>Change <code>main.lua</code> and press <b>Ctrl+F5</b> in battle: the code of all mods is read again, the result is on the screen. The usual quick save F5 works as before.</li>",
        "h_events": "Handlers",
        "events": "To subscribe: <code>game.on(\"name\", function)</code>. Arguments come in the order of the Y-script's input, the last one is the table <code>out</code> of output values, if there are any. "
                  "Values in <code>out</code> are taken as whole numbers and only all at once: one bad value is an error, the others are not applied. "
                  "Handlers marked \"only reads\" change only <code>out</code>: as in the Y-script, the objects there cannot be changed, and calling <code>set...</code> or <code>add...</code> in them is an error. "
                  "On one handler the Y-script runs first, then Lua in the mods' load order.",
        "th_event": "Handler", "th_when": "When", "th_out": "out",
        "readonly": "read only",
        "only_reads": "only reads",
        "pure": "no random numbers",
        "h_api": "Objects",
        "th_method": "Method", "th_what": "What it does",
        "h_game": "The game table",
        "game": "<code>game.on(name, function)</code> subscribes a function to a handler, only while <code>main.lua</code> loads. <code>game.log(...)</code> and <code>print(...)</code> write a line to the game's log. <code>game.getRules()</code> gives all the game's rules, those of other mods too, the <code>rules</code> table above. With <code>luaApi: 2</code>: <code>game.getBattle()</code> and <code>game.getGeoscape()</code> give the battle and the campaign where a handler does not receive them, a click on a screen for one; no battle: nil. <code>game.getBases()</code> gives a table of the player's bases, in a battle and in a click too. Only with the permission <code>screens</code>: <code>game.screen(name, function[, { menu = \"STR_NAME\", interface = \"pauseMenu\" }])</code> declares a screen, only while <code>main.lua</code> loads; <code>game.openScreen(name)</code> opens it from a handler.",
        "h_caps": "Permissions and screens of your own",
        "caps": "<p>With <code>luaApi: 2</code> a mod has permissions: words in <code>metadata.yml</code>, for example <code>luaCaps: [screens, economy]</code>. Without the word there is no method for the mod: a call gives a Lua error naming the permission. An unknown word, or <code>luaCaps</code> with <code>luaApi: 1</code>, switches the mod's Lua off. There are two words now: <code>screens</code> and <code>economy</code>.</p>"
                "<ul><li>A screen is made of the game's widgets in coordinates 320×200, so it works at any resolution and scale.</li>"
                "<li>The player opens it on the mods' screen, if <code>game.screen</code> has <code>menu</code>, or a handler through <code>game.openScreen</code>: the screen then opens when the game has finished its step, in battle it may be after an animation or after the briefing. While a screen is open the game under it stands.</li>"
                "<li>The building function and <code>onClose</code> only read: no random numbers, writes or <code>openScreen</code>. A screen opened and closed does not change the game. In a click you may do all a handler may.</li>"
                "<li>Read-only handlers, the old handlers of the geoscape and the nerds' pages among them, do not open screens.</li>"
                "<li>Esc always closes a screen. An error while building closes the screen and goes to the log. There are no frame handlers or timers: only a reaction to an action.</li>"
                "<li>Widget handles live while the screen is open, after closing: a Lua error.</li>"
                "<li>Ceilings: 64 widgets, 2000 list rows, 8 columns, 256 options, 64 screens a mod, nesting and the queue together 4, one screen a call, 8 screens a battle turn or a campaign day. Over a ceiling: the mod's error, the game lives.</li></ul>"
                "<p><code>economy</code>: money, stores, personnel and hiring, only out of a battle.</p>"
                "<ul><li><b>Lua variables are reset at every new battle and load.</b> A day counter in a variable is forgotten after the first battle. Whatever has to outlive a battle goes into tags, for the campaign the section <code>GeoscapeGame</code>.</li>"
                "<li>Reading needs no word: <code>game.getBases()</code>, <code>geoscape:getFunds()</code>, the reading methods of <code>base</code>. Changes need the word and work only in <code>newHour</code>, <code>newDay</code>, <code>newMonth</code>, in a click on a screen and in the function <code>done</code> of <code>hireSoldier</code>. Not in a battle: its end counts the stores itself.</li>"
                "<li>These three handlers may open a screen: <code>game.openScreen</code>. <code>battleStart</code> and <code>battleEnd</code> only read.</li>"
                "<li>Money, stores and personnel change at once. A Lua error in the same call undoes everything the call did, hiring too.</li>"
                "<li><code>addFunds</code> goes to the month's income or expenditure, like ordinary money. In <code>newMonth</code> the report of the past month is already counted: the money goes to the new month. A debt below the threshold gives the council's usual warning, then the usual defeat.</li>"
                "<li><code>hireSoldier(type[, done])</code> is free: the mod takes the price itself if it wants one. The soldier is created after the handler and travels to the base as a usual transfer. <code>done(soldier)</code> gets the new soldier, <code>done(nil, reason)</code> a refusal: no quarters or the monthly limit. Objects of the handler are dead in <code>done</code>, take the base again with <code>game.getBases()</code>.</li>"
                "<li>The game treats stores over the limit as usual: a sell window that does not close until the excess is sold. Do not give the player more than the stores hold. On Piratez <code>getStores().used</code> can be negative: some items have a negative size.</li>"
                "<li>The mod removed: money, items of ordinary rules and personnel stay, nothing is undone; tags are lost at a new save. The mark <code>luaTouched</code> goes into the save, it stays after the mod is removed and shows in an error report.</li>"
                "<li>Ceilings: <code>addFunds</code> up to ±1,000,000,000 a call, items and personnel up to 1,000,000,000 a call, hiring 16 a call and 64 a day. Over a ceiling: the mod's error, the game lives.</li></ul>",
        "h_const": "Constants",
        "h_tags": "Tags: memory between saves",
        "tags": "Lua variables are reset when a save is loaded, in a new battle and by Ctrl+F5. Tags are the only long memory. A tag is declared in the mod's ruleset, for example in the file <code>Ruleset/my_mod.rul</code>:"
                "<pre>extended:\n  tags:\n    BattleUnit:\n      MY_REGEN: int\n    BattleItem:\n      MY_CHARGE: int</pre>"
                "The sections go by object: BattleUnit, BattleItem, BattleGame, GeoscapeGame, GeoscapeSoldier, Country, Ufo, Craft, RuleArmor, RuleItem, RuleSoldier, RuleSoldierBonus, RuleUfo, RuleCraft, RuleCountry, RuleResearch. A tag name is one for the whole game: the same name in a second section is dropped by the engine with an error in its log. "
                "In the code the name has no prefix: <code>unit:getTag(\"MY_REGEN\")</code>. Reading or writing an unknown tag is an error: a typo shows at once. A tag of the same name in two mods is shared by them. "
                "A value lives while the mod is installed: a save without the mod loads and plays, but a new save made without the mod loses the values.",
        "h_lua": "What Lua itself has",
        "lua": "Base functions: {base}. Libraries <code>string</code> (no <code>dump</code>), <code>table</code>, <code>math</code> (no <code>randomseed</code>), <code>utf8</code>. "
               "There is no <code>io os debug package require load dofile loadfile coroutine collectgarbage</code>, bytecode is not loaded. "
               "<code>math.random</code> goes through the game's generator; while <code>main.lua</code> loads it is an error: loading must not shift the battle's seed. "
               "There are no clocks and no time.",
        "h_limits": "Limits",
        "limits": "<li>Memory: {memory} MB per mod.</li><li>One handler call: {instructions} instructions, {cticks} ticks of C functions (string patterns, <code>string.rep</code>, <code>table.*</code>). "
                  "<code>main.lua</code> gets ten times the instructions while it loads.</li><li>{errors} errors in a row switch the mod off until Ctrl+F5 or a new load. The game neither crashes nor hangs.</li>"
                  "<li>A <code>flashMessage</code>: up to {message} bytes of text.</li>",
        "h_errors": "Errors",
        "errors": "An error or a limit reached: the output values stay as they were before the call, <code>user/lua_errors.log</code> gets the mod, file, line, handler and text. "
                  "The screen shows a mod's first error of the load and its switching off, not every error. The log starts anew at each start of the game.",
        "h_know": "Good to know",
        "know": "<li>An object lives only inside the handler that received it. One kept in a variable gives a Lua error, the game does not crash.</li>"
                "<li>The order of <code>pairs</code> is stable only for string keys. Table keys and <code>tostring(table)</code> depend on addresses: the same mod gives two players different results.</li>"
                "<li><code>health_recovery</code> of <code>healUnit</code> works only on a body part with a wound, as in the Y-script.</li>"
                "<li>A <code>hitUnit</code>, <code>damageUnit</code>, <code>damageSpecialUnit</code>, their <code>...Ammo</code>, <code>damageBonusBonusStats</code> or <code>meleeBonusBonusStats</code> handler takes the AI's exact forecast of a shot away: it treats the result as unknown and may shoot at an invulnerable target.</li>"
                "<li>Handlers marked \"no random numbers\" come from lists, tooltips and forecasts, and how many times is not up to the game: a random number there would shift the common generator, so <code>math.random</code>, <code>randomRange</code> and <code>randomChance</code> in them are an error. Nothing but <code>out</code> can be changed there either.</li>"
                "<li><code>visibilityUnit</code>, the bonuses and the prices come very often: for each pair of units at each step, for each row of the shop. Heavy code or a log line on every call slows the game, and working out lists will hit the limit.</li>"
                "<li>Where the engine works the same formulas out in background threads, Lua is not called: the value of the Y-script stays. The outcome of an action is worked out in the main thread and takes Lua into account.</li>"
                "<li><code>set...</code> and <code>add...</code> methods keep the value within its limits themselves: health and time units no higher than the maximum, morale from 0 to 100. So adding time units at the start of a turn usually does nothing: they are already full.</li>"
                "<li><code>damageSpecialUnit</code> comes at zero damage too, <code>damageUnit</code> only when the power of the hit is above zero.</li>"
                "<li><code>getUnits</code>, <code>getItems</code> and other lists make a new table on every call and pay for each element. The memory or tick limit gives an error <code>not enough memory</code> or about the limit: call them rarely, not for every item of every turn.</li>"
                "<li><code>tryPsiAttack*</code> and <code>tryMeleeAttack*</code> come during the AI's forecasts too, so they are no place for side effects. <code>math.random</code>, <code>randomRange</code> and <code>randomChance</code> shift the common generator there, and two players' battles will diverge.</li>"
                "<li>A mod's error outside a battle goes to the log at once and shows on the screen in the next battle.</li>"
                "<li>A local mod can change game mechanics and break a save. A separate build in the launcher is better for experiments.</li>"
                "<li>A bug report carries only the mod's id, version and the mark <code>[lua local]</code>, not its code or files. The error log goes with it only if you tick it in the form yourself.</li>",
    },
}

CSS = """
:root{color-scheme:light dark;--bg:#fbfaf7;--fg:#22211e;--dim:#6c6a62;--line:#dcd9d0;--code:#efece4}
@media (prefers-color-scheme:dark){:root{--bg:#1d1c1a;--fg:#e8e6df;--dim:#a3a095;--line:#3b3934;--code:#2b2a26}}
*{box-sizing:border-box}body{margin:0 auto;max-width:980px;padding:28px 16px 60px;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,"Segoe UI",sans-serif}
h1{font-size:26px;margin:0 0 12px}h2{font-size:19px;margin:32px 0 10px;border-bottom:1px solid var(--line);padding-bottom:4px}h3{font-size:15px;margin:20px 0 6px}
code,pre{font-family:Consolas,monospace;font-size:13px;background:var(--code);border-radius:3px}code{padding:1px 4px}pre{padding:10px;overflow-x:auto}pre code{padding:0;background:none}
table{border-collapse:collapse;width:100%;margin:8px 0;display:block;overflow-x:auto}th,td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}th{color:var(--dim);font-weight:600}
.ro{color:var(--dim)}
"""


def fail(problems):
    for p in problems:
        print("!!", p)
    sys.exit(1)


def strip_comments(text):
    return re.sub(r"//[^\n]*", "", text)


def read_engine():
    """То, что есть в движке на самом деле."""
    src = strip_comments(HOST.read_text(encoding="utf-8-sig"))
    tables = {}
    for prefix, (lua_name, *_rest) in TYPES.items():
        m = re.search(r"const luaL_Reg %s_METHODS\[\] = \{(.*?)\n?\};" % prefix, src, re.S)
        if not m:
            fail([f"нет таблицы {prefix}_METHODS в LuaHost.cpp"])
        tables[lua_name] = re.findall(r'\{\s*"(\w+)"\s*,', m.group(1))
    m = re.search(r"const luaL_Reg API2_GEOSCAPE_REGS\[\] = \{(.*?)\n?\};", src, re.S)
    if not m:
        fail(["нет таблицы API2_GEOSCAPE_REGS в LuaHost.cpp"])
    tables["geoscape"] += re.findall(r'\{\s*"(\w+)"\s*,', m.group(1))
    m = re.search(r"const EventInfo EVENTS\[.*?\] = \{(.*?)\n\};", src, re.S)
    if not m:
        fail(["нет таблицы EVENTS в LuaHost.cpp"])
    events = {}
    for name, outs, ro, reads, pure in re.findall(r'\{\s*"(\w+)",\s*\{([^}]*)\},\s*\{([^}]*)\}(\s*,\s*true)?(\s*,\s*\{\s*\}\s*,\s*true)?', m.group(1)):
        events[name] = (re.findall(r'"(\w+)"', outs), set(re.findall(r'"(\w+)"', ro)), bool(reads), bool(pure))
    m = re.search(r"const Constant CONSTANTS\[\] = \{(.*?)\n\};", src, re.S)
    constants = re.findall(r'\{\s*"(\w+)"\s*,', m.group(1))

    calls = {}
    for path in (ROOT / "src").rglob("*.cpp"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if "LuaHost::" not in text:
            continue
        for enum, args in re.findall(r"lua->fire\(LuaHost::(\w+),\s*(?:[\w.]+,\s*)?\{([^}]*)\}\s*\)", text):
            calls[enum] = len([a for a in args.split(",") if a.strip()])
        for args in re.findall(r"lua->fire\(static_cast<LuaHost::Event>\(_luaEvent\),\s*[\w.]+,\s*\{([^}]*)\}\s*\)", text):
            calls["BONUS"] = len([a for a in args.split(",") if a.strip()])

    sandbox = SANDBOX.read_text(encoding="utf-8-sig")
    m = re.search(r"BASE_ALLOWED\[\] = \{(.*?)\};", sandbox, re.S)
    base = [b for b in re.findall(r'"(\w+)"', m.group(1)) if b not in ("_G", "_VERSION")]

    head = SANDBOX_H.read_text(encoding="utf-8-sig")
    memory = re.search(r"memoryBytes = (\d+) \* 1024 \* 1024", head)
    instructions = re.search(r"instructions = (\d+)", head)
    cticks = re.search(r"cTicks = (\d+)", head)
    errors = re.search(r"maxErrors = (\d+)", head)
    message = re.search(r"MESSAGE_MAX = (\d+)", src)
    api = re.search(r"API_VERSION = (\d+)", HOST_H.read_text(encoding="utf-8-sig"))
    for name, found in (("memoryBytes", memory), ("instructions", instructions), ("cTicks", cticks), ("maxErrors", errors), ("MESSAGE_MAX", message), ("API_VERSION", api)):
        if not found:
            fail([f"не найден {name}"])
    numbers = {
        "memory": memory.group(1), "instructions": f"{int(instructions.group(1)):,}".replace(",", " "), "cticks": f"{int(cticks.group(1)):,}".replace(",", " "),
        "errors": errors.group(1), "message": message.group(1), "api": api.group(1),
    }
    return tables, events, constants, calls, base, numbers


def game_calls():
    """Функции таблицы game. Слова разрешений сверяются с capOf: закрытое до своего этапа слово на страницу не идёт."""
    src = strip_comments(HOST.read_text(encoding="utf-8-sig"))
    m = re.search(r"const luaL_Reg API2_GAME_REGS\[\] = \{(.*?)\n?\};", src, re.S)
    if not m:
        fail(["нет таблицы API2_GAME_REGS в LuaHost.cpp"])
    words = re.findall(r'word == "(\w+)"', src)
    wrong = [c for c in CAPS if c not in words] + [w for w in words if w not in CAPS and w not in CLOSED_CAPS]
    if wrong:
        fail([f"разрешение {w}: в движке и на странице по-разному" for w in wrong])
    return ["on", "log", "getRules"] + re.findall(r'\{\s*"(\w+)"\s*,', m.group(1))


def check_words(tables, events, calls):
    problems = []
    for lua_name, names in tables.items():
        words = METHODS.get(lua_name, {})
        problems += [f"{lua_name}:{n} нет описания" for n in names if n not in words]
        problems += [f"{lua_name}:{n} описан, а в движке нет" for n in words if n not in names]
    problems += [f"обработчик {n} нет описания" for n in events if n not in EVENTS]
    problems += [f"обработчик {n} описан, а в движке нет" for n in EVENTS if n not in events]
    for name, (enum, args, *_rest) in EVENTS.items():
        called = calls.get("BONUS" if enum.endswith("_BONUS") else enum)
        if called is None:
            problems.append(f"{name}: вызов lua->fire(LuaHost::{enum}) не найден")
        elif called != len(args.split(",")):
            problems.append(f"{name}: в движке аргументов {called}, в описании {len(args.split(','))}")
        problems += [f"{name}: аргумент {a} без описания" for a in (x.strip() for x in args.split(",")) if a not in ARG_WORDS]
    used = {x.strip() for _enum, args, *_rest in EVENTS.values() for x in args.split(",")}
    problems += [f"аргумент {a} описан, а его нет ни у кого" for a in ARG_WORDS if a not in used]
    for name, (outs, _ro, _reads, _pure) in events.items():
        words = OUT_WORDS.get(name, {})
        problems += [f"{name}: out.{o} без описания" for o in outs if o not in words]
        problems += [f"{name}: out.{o} описан, а в движке нет" for o in words if o not in outs]
    return problems


def recipes_html(lang):
    parts = []
    for r in RECIPES:
        parts.append(f"<h3>{html.escape(r[lang])}</h3><p>{r[lang + '_text']}</p>")
        if "rul" in r:
            parts.append(f"<pre><code>{html.escape(r['rul'])}</code></pre>")
        parts.append(f"<pre><code>{html.escape(r['code'])}</code></pre>")
    return parts


def page(lang, tables, events, constants, base, numbers):
    t = TEXT[lang]
    i = 0 if lang == "ru" else 1
    out = [f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           f"<title>{html.escape(t['title'].format(**numbers))}</title><style>{CSS}</style></head><body>",
           f"<h1>{html.escape(t['title'].format(**numbers))}</h1><p>{t['intro'].format(**numbers)}</p>",
           f"<h2>{t['h_where']}</h2><p>{t['where']}</p>",
           f"<h2>{t['h_start']}</h2><ol>{t['start']}</ol>",
           f"<h2>{t['h_can']}</h2><table><tr><th>{t['th_area']}</th><th>{t['th_lua']}</th></tr>",
           *(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td></tr>" for a, b in t["can_rows"]),
           f"</table><div>{t['cannot']}</div>",
           f"<h2>{t['h_recipes']}</h2><p>{t['recipes']}</p>",
           *recipes_html(lang),
           f"<h2>{t['h_events']}</h2><p>{t['events']}</p>",
           f"<table><tr><th>{t['th_event']}</th><th>{t['th_when']}</th><th>{t['th_out']}</th></tr>"]
    for name, (outs, ro, reads, pure) in events.items():
        _enum, args, *when = EVENTS[name]
        full = args + (", out" if outs else "")
        listed = ", ".join(f'<code>{o}</code>' + (f' <span class="ro">({t["readonly"]})</span>' if o in ro else "") for o in outs) or "-"
        mark = f' <span class="ro">({t["only_reads"]})</span>' if reads else ""
        mark += f' <span class="ro">({t["pure"]})</span>' if pure else ""
        out.append(f'<tr id="event.{name}"><td><code>{name}({full})</code>{mark}</td><td>{when[i]}</td><td>{listed}</td></tr>')
    out.append("</table>")
    out.append(f"<h3>{t['h_args']}</h3><p>{t['args_note']}</p><ul>")
    out += [f"<li><code>{a}</code>: {words[i]}</li>" for a, words in ARG_WORDS.items()]
    out.append(f"</ul><h3>{t['h_outs']}</h3><table><tr><th>{t['th_event']}</th><th>{t['th_out']}</th><th>{t['th_what']}</th></tr>")
    for name, (outs, ro, _reads, _pure) in events.items():
        for o in outs:
            mark = f' <span class="ro">({t["readonly"]})</span>' if o in ro else ""
            out.append(f"<tr><td><code>{name}</code></td><td><code>{o}</code>{mark}</td><td>{OUT_WORDS[name][o][i]}</td></tr>")
    out.append("</table>")
    out.append(f"<h2>{t['h_api']}</h2>")
    for _prefix, (lua_name, *titles) in TYPES.items():
        out.append(f"<h3>{titles[i]}: <code>{lua_name}</code></h3><table><tr><th>{t['th_method']}</th><th>{t['th_what']}</th></tr>")
        for method in tables[lua_name]:
            args, *what = METHODS[lua_name][method]
            out.append(f'<tr id="{lua_name}.{method}"><td><code>{lua_name}:{method}({args})</code></td><td>{html.escape(what[i])}</td></tr>')
        out.append("</table>")
    out.append(f"<h2>{t['h_game']}</h2><p>{t['game']}</p>")
    out.append(f"<h2>{t['h_caps']}</h2>{t['caps']}")
    out.append(f"<h2>{t['h_const']}</h2>")
    groups = {}
    for c in constants:
        groups.setdefault(c.split("_")[0], []).append(c)
    for prefix, names in groups.items():
        out.append(f"<p>{html.escape(CONST_WORDS[prefix][i])}: " + " ".join(f"<code>game.{n}</code>" for n in names) + "</p>")
    out.append(f"<h2>{t['h_tags']}</h2><p>{t['tags']}</p>")
    out.append(f"<h2>{t['h_lua']}</h2><p>{t['lua'].format(base=' '.join(f'<code>{b}</code>' for b in base))}</p>")
    out.append(f"<h2>{t['h_limits']}</h2><ul>{t['limits'].format(**numbers)}</ul>")
    out.append(f"<h2>{t['h_errors']}</h2><p>{t['errors']}</p>")
    out.append(f"<h2>{t['h_know']}</h2><ul>{t['know'].format(**numbers)}</ul>")
    out.append("</body></html>\n")
    return "\n".join(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tables, events, constants, calls, base, numbers = read_engine()
    problems = check_words(tables, events, calls)
    if problems:
        fail(problems)
    check = "--check" in sys.argv
    stale = []
    OUT.mkdir(parents=True, exist_ok=True)
    for lang in TEXT:
        path = OUT / f"lua_api.{lang}.html"
        text = page(lang, tables, events, constants, base, numbers)
        if check:
            if not path.exists() or path.read_text(encoding="utf-8-sig") != text:
                stale.append(path.name)
        else:
            path.write_text(text, encoding="utf-8-sig", newline="\n")
            print(path, len(text))
    # имена для проверки заявок: лаунчер и tools/lua_mod_check.py сверяют вызовы мода с одним и тем же списком
    names = [f"api\t{numbers['api']}"] + [f"event\t{e}" for e in events] + [f"event2\t{e}" for e in API2_EVENTS] + [f"const\t{c}" for c in constants] + [f"base\t{b}" for b in base]
    names += [f"method\t{m}" for m in sorted({m for v in tables.values() for m in v})]
    names += [f"game\t{g}" for g in game_calls()] + [f"cap\t{c}" for c in CAPS]
    text = "\n".join(names) + "\n"
    path = OUT / "lua_api.names.txt"
    if check:
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            stale.append(path.name)
    else:
        path.write_text(text, encoding="utf-8", newline="\n")
    if stale:
        fail([f"{n} устарел: py -3 tools/lua_api_doc.py" for n in stale])
    count = sum(len(v) for v in tables.values())
    print(f"методов {count}, обработчиков {len(events)}, констант {len(constants)}")


if __name__ == "__main__":
    main()
