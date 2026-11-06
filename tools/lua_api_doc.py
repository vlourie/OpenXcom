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
        "getOwner": ("", "владелец, юнит или nil", "the owner, a unit, or nil"),
        "isAmmo": ("", "это боеприпас", "this is ammunition"),
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
                 "Lua запускает только игра, лаунчер код мода не исполняет. Граница API: Lua может то, что уже может Y-script, и ничего сверх. "
                 "Имена обработчиков и выходных значений те же, что у Y-script.",
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
        "game": "<code>game.on(имя, функция)</code> подписывает функцию на обработчик. <code>game.log(...)</code> и <code>print(...)</code> пишут строку в журнал игры.",
        "h_const": "Константы",
        "h_tags": "Теги: память между сохранениями",
        "tags": "Переменные Lua обнуляются при загрузке сейва, в новом бою и по Ctrl+F5. Долгая память — только теги. Тег объявляется в рулсете мода:"
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
                "<li>В API версии {api} нет спрайтов, видимости, реакций и ИИ: это частые вызовы и рисование.</li>"
                "<li>Локальный мод может менять механику и сломать сейв. Для опытов лучше отдельная сборка в лаунчере.</li>"
                "<li>В отчёт об ошибке уходят только id мода, версия и отметка <code>[lua local]</code>, код и файлы мода не уходят. Журнал ошибок прикладывается, только если вы сами отметите его в форме.</li>",
    },
    "en": {
        "title": "Lua API for OXCE-HD mods, version {api}",
        "intro": "A mod is written in <code>lua/main.lua</code> in its folder, <code>metadata.yml</code> says <code>luaApi: {api}</code>. "
                 "Only the game runs Lua, the launcher never executes a mod's code. The border of the API: Lua can do what the Y-script can do and nothing beyond it. "
                 "The names of the handlers and of the output values are those of the Y-script.",
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
        "game": "<code>game.on(name, function)</code> subscribes a function to a handler. <code>game.log(...)</code> and <code>print(...)</code> write a line to the game's log.",
        "h_const": "Constants",
        "h_tags": "Tags: memory between saves",
        "tags": "Lua variables are reset when a save is loaded, in a new battle and by Ctrl+F5. Tags are the only long memory. A tag is declared in the mod's ruleset:"
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
                "<li>API version {api} has no sprites, visibility, reactions or AI: these are frequent calls and drawing.</li>"
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
    return problems


def page(lang, tables, events, constants, base, numbers):
    t = TEXT[lang]
    i = 0 if lang == "ru" else 1
    out = [f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           f"<title>{html.escape(t['title'].format(**numbers))}</title><style>{CSS}</style></head><body>",
           f"<h1>{html.escape(t['title'].format(**numbers))}</h1><p>{t['intro'].format(**numbers)}</p>",
           f"<h2>{t['h_start']}</h2><ol>{t['start']}</ol>",
           f"<h2>{t['h_events']}</h2><p>{t['events']}</p>",
           f"<table><tr><th>{t['th_event']}</th><th>{t['th_when']}</th><th>{t['th_out']}</th></tr>"]
    for name, (outs, ro) in events.items():
        _enum, args, *when = EVENTS[name]
        full = args + (", out" if outs else "")
        listed = ", ".join(f'<code>{o}</code>' + (f' <span class="ro">({t["readonly"]})</span>' if o in ro else "") for o in outs) or "-"
        out.append(f'<tr id="event.{name}"><td><code>{name}({full})</code></td><td>{html.escape(when[i])}</td><td>{listed}</td></tr>')
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
    if stale:
        fail([f"{n} устарел: py -3 tools/lua_api_doc.py" for n in stale])
    count = sum(len(v) for v in tables.values())
    print(f"методов {count}, обработчиков {len(events)}, констант {len(constants)}")


if __name__ == "__main__":
    main()
