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
    "ITEM": ("item", "Предмет", "Item"),
    "BATTLE": ("battle", "Бой", "Battle"),
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
}

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
        "getTime": ("", "таблица по Гринвичу: second, minute, hour, day, month, year, secondsPastMidnight, daysPastEpoch", "a table in Greenwich time: second, minute, hour, day, month, year, secondsPastMidnight, daysPastEpoch"),
        "difficultyLevel": ("", "сложность, DIFF_*", "the difficulty, DIFF_*"),
        "getMonthsPassed": ("", "сколько месяцев идёт игра", "how many months the game has run"),
        "getDaysPassed": ("", "сколько дней идёт игра", "how many days the game has run"),
        "getCountries": ("", "таблица стран", "a table of the countries"),
        "isResearched": ("name", "исследовано name. Незнакомое имя: ошибка", "name is researched. An unknown name is an error"),
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
    "ruleCountry": {"getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string")},
    "ruleUfo": {
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getTag": ("name", "значение тега RuleUfo", "the value of a RuleUfo tag"),
    },
    "ruleCraft": {
        "getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string"),
        "getTag": ("name", "значение тега RuleCraft", "the value of a RuleCraft tag"),
    },
}

HIT = "unit, damaging_item, weapon_item, attacker, battle, skill"
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
}

# аргумент обработчика: (по-русски, по-английски)
ARG_WORDS = {
    "unit": ("юнит, с которым это произошло", "the unit it happened to"),
    "item": ("предмет; в <code>healUnit</code> и <code>skillUseUnit</code> то, чем действуют, в <code>skillUseUnit</code> может быть nil", "the item; in <code>healUnit</code> and <code>skillUseUnit</code> the one used, in <code>skillUseUnit</code> it may be nil"),
    "battle": ("бой", "the battle"),
    "turn": ("номер хода", "the turn number"),
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
}

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
            ("Конец миссии", "срок лечения, сколько здоровья и маны солдат недобирает на базе"),
            ("Служебное", "теги юнита, предмета, боя, солдата и геоскейпа, журнал"),
        ],
        "cannot": "<b>Из Lua нельзя:</b>"
                  "<ul><li>базы, наука, производство, деньги: геоскейп можно читать, а менять только теги, итог месяца для страны и обнаружение НЛО;</li>"
                  "<li>создавать и двигать юнитов и предметы, менять карту;</li>"
                  "<li>спрайты, перекраску, свои экраны, расчёт видимости и реакций, решения ИИ, цены. Эти обработчики Y-script в Lua не вынесены, для них есть Y-script.</li></ul>"
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
        "h_api": "Объекты",
        "th_method": "Метод", "th_what": "Что делает",
        "h_game": "Таблица game",
        "game": "<code>game.on(имя, функция)</code> подписывает функцию на обработчик, только пока грузится <code>main.lua</code>. <code>game.log(...)</code> и <code>print(...)</code> пишут строку в журнал игры.",
        "h_const": "Константы",
        "h_tags": "Теги: память между сохранениями",
        "tags": "Переменные Lua обнуляются при загрузке сейва, в новом бою и по Ctrl+F5. Долгая память — только теги. Тег объявляется в рулсете мода, например в файле <code>Ruleset/my_mod.rul</code>:"
                "<pre>extended:\n  tags:\n    BattleUnit:\n      MY_REGEN: int\n    BattleItem:\n      MY_CHARGE: int</pre>"
                "Разделы по объектам: BattleUnit, BattleItem, BattleGame, GeoscapeGame, GeoscapeSoldier, Country, Ufo, Craft, RuleArmor, RuleItem, RuleSoldier, RuleSoldierBonus, RuleUfo, RuleCraft. Имя тега одно на всю игру: то же имя во втором разделе движок отбросит с ошибкой в своём журнале. "
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
                "<li>Обработчик <code>hitUnit</code>, <code>damageUnit</code> или <code>damageSpecialUnit</code> лишает ИИ точного прогноза выстрела: он считает результат неизвестным и может стрелять по неуязвимой цели.</li>"
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
            ("The end of a mission", "the recovery time, how much health and mana a soldier lacks at the base"),
            ("Service", "tags of units, items, the battle, soldiers and the geoscape, the log"),
        ],
        "cannot": "<b>From Lua you cannot:</b>"
                  "<ul><li>touch bases, research, production, money: the geoscape can be read, and only tags, a country's month and UFO detection can be changed;</li>"
                  "<li>create or move units and items, change the map;</li>"
                  "<li>touch sprites, recolouring, your own screens, the calculation of visibility and reactions, AI decisions, prices. Those Y-script handlers are not in Lua, the Y-script is there for them.</li></ul>"
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
        "h_api": "Objects",
        "th_method": "Method", "th_what": "What it does",
        "h_game": "The game table",
        "game": "<code>game.on(name, function)</code> subscribes a function to a handler, only while <code>main.lua</code> loads. <code>game.log(...)</code> and <code>print(...)</code> write a line to the game's log.",
        "h_const": "Constants",
        "h_tags": "Tags: memory between saves",
        "tags": "Lua variables are reset when a save is loaded, in a new battle and by Ctrl+F5. Tags are the only long memory. A tag is declared in the mod's ruleset, for example in the file <code>Ruleset/my_mod.rul</code>:"
                "<pre>extended:\n  tags:\n    BattleUnit:\n      MY_REGEN: int\n    BattleItem:\n      MY_CHARGE: int</pre>"
                "The sections go by object: BattleUnit, BattleItem, BattleGame, GeoscapeGame, GeoscapeSoldier, Country, Ufo, Craft, RuleArmor, RuleItem, RuleSoldier, RuleSoldierBonus, RuleUfo, RuleCraft. A tag name is one for the whole game: the same name in a second section is dropped by the engine with an error in its log. "
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
                "<li>A <code>hitUnit</code>, <code>damageUnit</code> or <code>damageSpecialUnit</code> handler takes the AI's exact forecast of a shot away: it treats the result as unknown and may shoot at an invulnerable target.</li>"
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
    m = re.search(r"const EventInfo EVENTS\[.*?\] = \{(.*?)\n\};", src, re.S)
    if not m:
        fail(["нет таблицы EVENTS в LuaHost.cpp"])
    events = {}
    for name, outs, ro, reads in re.findall(r'\{\s*"(\w+)",\s*\{([^}]*)\},\s*\{([^}]*)\}(\s*,\s*true)?', m.group(1)):
        events[name] = (re.findall(r'"(\w+)"', outs), set(re.findall(r'"(\w+)"', ro)), bool(reads))
    m = re.search(r"const Constant CONSTANTS\[\] = \{(.*?)\n\};", src, re.S)
    constants = re.findall(r'\{\s*"(\w+)"\s*,', m.group(1))

    calls = {}
    for path in (ROOT / "src").rglob("*.cpp"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if "LuaHost::" not in text:
            continue
        for enum, args in re.findall(r"lua->fire\(LuaHost::(\w+),\s*(?:[\w.]+,\s*)?\{([^}]*)\}\s*\)", text):
            calls[enum] = len([a for a in args.split(",") if a.strip()])

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


def check_words(tables, events, calls):
    problems = []
    for lua_name, names in tables.items():
        words = METHODS.get(lua_name, {})
        problems += [f"{lua_name}:{n} нет описания" for n in names if n not in words]
        problems += [f"{lua_name}:{n} описан, а в движке нет" for n in words if n not in names]
    problems += [f"обработчик {n} нет описания" for n in events if n not in EVENTS]
    problems += [f"обработчик {n} описан, а в движке нет" for n in EVENTS if n not in events]
    for name, (enum, args, *_rest) in EVENTS.items():
        if enum not in calls:
            problems.append(f"{name}: вызов lua->fire(LuaHost::{enum}) не найден")
        elif calls[enum] != len(args.split(",")):
            problems.append(f"{name}: в движке аргументов {calls[enum]}, в описании {len(args.split(','))}")
        problems += [f"{name}: аргумент {a} без описания" for a in (x.strip() for x in args.split(",")) if a not in ARG_WORDS]
    used = {x.strip() for _enum, args, *_rest in EVENTS.values() for x in args.split(",")}
    problems += [f"аргумент {a} описан, а его нет ни у кого" for a in ARG_WORDS if a not in used]
    for name, (outs, _ro, _reads) in events.items():
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
    for name, (outs, ro, reads) in events.items():
        _enum, args, *when = EVENTS[name]
        full = args + (", out" if outs else "")
        listed = ", ".join(f'<code>{o}</code>' + (f' <span class="ro">({t["readonly"]})</span>' if o in ro else "") for o in outs) or "-"
        mark = f' <span class="ro">({t["only_reads"]})</span>' if reads else ""
        out.append(f'<tr id="event.{name}"><td><code>{name}({full})</code>{mark}</td><td>{html.escape(when[i])}</td><td>{listed}</td></tr>')
    out.append("</table>")
    out.append(f"<h3>{t['h_args']}</h3><p>{t['args_note']}</p><ul>")
    out += [f"<li><code>{a}</code>: {words[i]}</li>" for a, words in ARG_WORDS.items()]
    out.append(f"</ul><h3>{t['h_outs']}</h3><table><tr><th>{t['th_event']}</th><th>{t['th_out']}</th><th>{t['th_what']}</th></tr>")
    for name, (outs, ro, _reads) in events.items():
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
    names = [f"api\t{numbers['api']}"] + [f"event\t{e}" for e in events] + [f"const\t{c}" for c in constants] + [f"base\t{b}" for b in base]
    names += [f"method\t{m}" for m in sorted({m for v in tables.values() for m in v})]
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
