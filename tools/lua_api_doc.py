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
}

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
    },
    "battle": {
        "getTurn": ("", "номер хода", "the turn number"),
        "getSize": ("", "размер карты, три значения: x, y, z", "the map size, three values: x, y, z"),
        "flashMessage": ("text, a, b, c", "сообщение на экране боя: строка из рулсета или текст, до трёх целых для {0} {1} {2}. "
                         "В returnFromMissionUnit ничего не делает",
                         "a message on the battle screen: a string id or plain text, up to three whole numbers for {0} {1} {2}. "
                         "Does nothing in returnFromMissionUnit"),
    },
    "soldier": {
        "getId": ("", "номер солдата", "the soldier's number"),
        "getRank": ("", "звание, целое", "the rank, a whole number"),
    },
    "ruleArmor": {"getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string")},
    "ruleItem": {"getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string")},
    "skill": {"getType": ("", "тип из рулсета, строка", "the type from the ruleset, a string")},
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
]

CONST_WORDS = {
    "BODYPART": ("части тела: part", "body parts: part"),
    "SIDE": ("стороны юнита: side в обработчиках урона и в броне", "sides of a unit: side in the damage handlers and in armor"),
    "FACTION": ("стороны боя", "sides of the battle"),
    "BA": ("действия: battle_action", "actions: battle_action"),
    "DT": ("типы урона: damaging_type", "damage types: damaging_type"),
}

TEXT = {
    "ru": {
        "title": "Lua API для модов OXCE-HD, версия {api}",
        "intro": "Мод пишется в файле <code>lua/main.lua</code> своей папки, в <code>metadata.yml</code> стоит <code>luaApi: {api}</code>. "
                 "Lua запускает только игра, лаунчер код мода не исполняет. API покрывает часть возможностей Y-script и не выходит за них. Страница описывает его полностью: чего здесь нет, того из Lua сделать нельзя. "
                 "Имена обработчиков и выходных значений те же, что у Y-script.",
        "h_where": "Где это работает",
        "where": "Только в нашей сборке OXCE-HD. Обычный OXCE не знает ключ <code>luaApi</code> и запустит мод без Lua: рулсеты мода будут работать, а код нет. Если мод нужен и там, пишите его на Y-script.",
        "h_can": "Что мод может менять",
        "th_area": "Что", "th_lua": "Из Lua",
        "can_rows": [
            ("Юнит в бою", "очки времени, здоровье, мана, энергия, оглушение, боевой дух, горение, броня сторон, раны"),
            ("Попадание и урон", "сила, часть тела, сторона, что сколько снимает, шанс превращения и взрыва, поджог, раскрытие атакующего"),
            ("Аптечка и навык", "сколько лечит аптечка, идёт ли действие навыка дальше, списывать ли за него очки времени"),
            ("Предмет в бою", "патроны, таймер взрывателя, заряды аптечки"),
            ("Конец миссии", "срок лечения, сколько здоровья и маны солдат недобирает на базе"),
            ("Служебное", "теги юнита и предмета, сообщение на экране, журнал"),
        ],
        "cannot": "<b>Из Lua нельзя:</b>"
                  "<ul><li>геоскейп, база, наука, производство, деньги, страны, НЛО, характеристики солдата вне боя;</li>"
                  "<li>создавать и двигать юнитов и предметы, менять карту. Списка всех юнитов нет: юнита или предмет можно получить только в обработчике;</li>"
                  "<li>спрайты, звук, свои экраны, видимость, реакции, решения ИИ, шанс пси- и ближней атаки, опыт, цены.</li></ul>"
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
                  "На одном обработчике сначала работает Y-script, затем Lua в порядке загрузки модов.",
        "th_event": "Обработчик", "th_when": "Когда", "th_out": "out",
        "readonly": "только чтение",
        "h_api": "Объекты",
        "th_method": "Метод", "th_what": "Что делает",
        "h_game": "Таблица game",
        "game": "<code>game.on(имя, функция)</code> подписывает функцию на обработчик, только пока грузится <code>main.lua</code>. <code>game.log(...)</code> и <code>print(...)</code> пишут строку в журнал игры.",
        "h_const": "Константы",
        "h_tags": "Теги: память между сохранениями",
        "tags": "Переменные Lua обнуляются при загрузке сейва, в новом бою и по Ctrl+F5. Долгая память — только теги. Тег объявляется в рулсете мода, например в файле <code>Ruleset/my_mod.rul</code>:"
                "<pre>extended:\n  tags:\n    BattleUnit:\n      MY_REGEN: int\n    BattleItem:\n      MY_CHARGE: int</pre>"
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
                "<li>Локальный мод может менять механику и сломать сейв. Для опытов лучше отдельная сборка в лаунчере.</li>"
                "<li>В отчёт об ошибке уходят только id мода, версия и отметка <code>[lua local]</code>, код и файлы мода не уходят. Журнал ошибок прикладывается, только если вы сами отметите его в форме.</li>",
    },
    "en": {
        "title": "Lua API for OXCE-HD mods, version {api}",
        "intro": "A mod is written in <code>lua/main.lua</code> in its folder, <code>metadata.yml</code> says <code>luaApi: {api}</code>. "
                 "Only the game runs Lua, the launcher never executes a mod's code. The API covers a part of what the Y-script can do and does not go beyond it. This page describes all of it: what is not here cannot be done from Lua. "
                 "The names of the handlers and of the output values are those of the Y-script.",
        "h_where": "Where it works",
        "where": "Only in our OXCE-HD build. Plain OXCE does not know the <code>luaApi</code> key and runs the mod without Lua: the mod's rulesets work and its code does not. If the mod is needed there too, write it in the Y-script.",
        "h_can": "What a mod can change",
        "th_area": "What", "th_lua": "From Lua",
        "can_rows": [
            ("A unit in battle", "time units, health, mana, energy, stun, morale, burning, the armor of each side, wounds"),
            ("A hit and damage", "the power, the body part, the side, what takes how much, the chance of transformation and explosion, setting on fire, revealing the attacker"),
            ("A medikit and a skill", "how much a medikit heals, whether a skill's action goes on, whether it costs time units"),
            ("An item in battle", "rounds, the fuse timer, medikit charges"),
            ("The end of a mission", "the recovery time, how much health and mana a soldier lacks at the base"),
            ("Service", "tags of units and items, a message on the screen, the log"),
        ],
        "cannot": "<b>From Lua you cannot:</b>"
                  "<ul><li>touch the geoscape, bases, research, production, money, countries, UFOs, a soldier's stats outside battle;</li>"
                  "<li>create or move units and items, change the map. There is no list of all units: a unit or an item comes only in a handler;</li>"
                  "<li>touch sprites, sound, your own screens, visibility, reactions, AI decisions, the chance of psi and melee attacks, experience, prices.</li></ul>"
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
                  "On one handler the Y-script runs first, then Lua in the mods' load order.",
        "th_event": "Handler", "th_when": "When", "th_out": "out",
        "readonly": "read only",
        "h_api": "Objects",
        "th_method": "Method", "th_what": "What it does",
        "h_game": "The game table",
        "game": "<code>game.on(name, function)</code> subscribes a function to a handler, only while <code>main.lua</code> loads. <code>game.log(...)</code> and <code>print(...)</code> write a line to the game's log.",
        "h_const": "Constants",
        "h_tags": "Tags: memory between saves",
        "tags": "Lua variables are reset when a save is loaded, in a new battle and by Ctrl+F5. Tags are the only long memory. A tag is declared in the mod's ruleset, for example in the file <code>Ruleset/my_mod.rul</code>:"
                "<pre>extended:\n  tags:\n    BattleUnit:\n      MY_REGEN: int\n    BattleItem:\n      MY_CHARGE: int</pre>"
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
    for name, outs, ro in re.findall(r'\{\s*"(\w+)",\s*\{([^}]*)\},\s*\{([^}]*)\}\s*\}', m.group(1)):
        events[name] = (re.findall(r'"(\w+)"', outs), set(re.findall(r'"(\w+)"', ro)))
    m = re.search(r"const Constant CONSTANTS\[\] = \{(.*?)\n\};", src, re.S)
    constants = re.findall(r'\{\s*"(\w+)"\s*,', m.group(1))

    calls = {}
    for path in (ROOT / "src").rglob("*.cpp"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if "LuaHost::" not in text:
            continue
        for enum, args in re.findall(r"lua->fire\(LuaHost::(\w+),\s*(?:\w+\.data,\s*)?\{([^}]*)\}\s*\)", text):
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
    for name, (outs, _ro) in events.items():
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
    for name, (outs, ro) in events.items():
        _enum, args, *when = EVENTS[name]
        full = args + (", out" if outs else "")
        listed = ", ".join(f'<code>{o}</code>' + (f' <span class="ro">({t["readonly"]})</span>' if o in ro else "") for o in outs) or "-"
        out.append(f'<tr id="event.{name}"><td><code>{name}({full})</code></td><td>{html.escape(when[i])}</td><td>{listed}</td></tr>')
    out.append("</table>")
    out.append(f"<h3>{t['h_args']}</h3><p>{t['args_note']}</p><ul>")
    out += [f"<li><code>{a}</code>: {words[i]}</li>" for a, words in ARG_WORDS.items()]
    out.append(f"</ul><h3>{t['h_outs']}</h3><table><tr><th>{t['th_event']}</th><th>{t['th_out']}</th><th>{t['th_what']}</th></tr>")
    for name, (outs, ro) in events.items():
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
