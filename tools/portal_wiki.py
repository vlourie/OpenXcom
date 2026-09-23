#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Вики мода собирается ИЗ РУЛСЕТОВ, а не пишется руками.

Числа на страницах обязаны быть теми же, что в игре, поэтому единственный источник тут -
файлы самого мода: Ruleset/*.rul и Language/*.yml. Слои читаются в том же порядке, в каком их
читает движок (сначала мастер из bin/standard, потом мод), с тем же правилом склейки:
запись с уже известным type/name ДОПОЛНЯЕТ прежнюю, а "- delete: X" её убирает.

Читать рулсеты обычным PyYAML нельзя (R-046): yaml-cpp разрешает переопределить якорь, PyYAML
на этом падает. Поэтому берём терпимый загрузчик из tools/pck_census.py - тот же, которым
собрана перепись наборов.

Выход - один JSON со страницами на всех запрошенных языках. Его забирает портал:

    py -3 tools\\portal_wiki.py --mod "Пиратки\\Dioxine_XPiratez\\user\\mods\\Piratez" ^
        --slug piratez --lang ru --lang en --out dist\\wiki\\piratez.json
    dotnet run --project portal\\src\\Xp.Portal -- wiki import --file dist\\wiki\\piratez.json

Проверка не по строке "готово", а по числам в конце прогона: сколько записей найдено в
рулсетах и сколько страниц вышло. Ноль страниц у раздела - это ошибка разбора, а не пустой мод.
"""
import argparse
import collections
import datetime
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pck_census import load_yaml  # noqa: E402

ENC_W = "utf-8"          # JSON читает .NET, спецификация ему не нужна

# ------------------------------------------------------------------ слои и склейка

# Блоки рулсета, из которых мы делаем страницы. Ключ записи у них разный: у предметов и брони
# это type, у исследований и производства - name, у статей педии - id.
BLOCKS = {
    "items": "type",
    "armors": "type",
    "research": "name",
    "manufacture": "name",
    "crafts": "type",
    "facilities": "type",
    "ufopaedia": "id",
}


def merge_block(store, rows, key):
    """Склейка слоя поверх прежнего - так же, как это делает движок."""
    for row in rows:
        if not isinstance(row, dict):
            continue
        dead = row.get("delete")
        if dead:
            store.pop(dead, None)
            continue
        name = row.get(key)
        if not name:
            continue
        old = store.get(name)
        if old is None:
            store[name] = dict(row)
        else:
            old.update(row)


def read_rulesets(roots):
    """Все блоки из всех .rul всех слоёв, в порядке чтения движком."""
    store = {k: collections.OrderedDict() for k in BLOCKS}
    files = 0
    for root in roots:
        rul = os.path.join(root, "Ruleset")
        paths = []
        if os.path.isdir(rul):
            paths = [os.path.join(rul, f) for f in sorted(os.listdir(rul)) if f.lower().endswith(".rul")]
        else:
            paths = [os.path.join(root, f) for f in sorted(os.listdir(root)) if f.lower().endswith(".rul")]
        for path in paths:
            data = load_yaml(path)
            if not isinstance(data, dict):
                continue
            files += 1
            for block, key in BLOCKS.items():
                rows = data.get(block)
                if isinstance(rows, list):
                    merge_block(store[block], rows, key)
    return store, files


def read_strings(roots, lang):
    """Строки языка из всех слоёв. Имена в игре - это они, а не ключи STR_."""
    out = {}
    names = [lang]
    if lang == "en":
        names = ["en-US", "en-GB", "en"]
    elif lang == "ru":
        names = ["ru"]
    for root in roots:
        for name in names:
            path = os.path.join(root, "Language", name + ".yml")
            if not os.path.isfile(path):
                continue
            data = load_yaml(path)
            for table in (data or {}).values():
                if isinstance(table, dict):
                    out.update({k: v for k, v in table.items() if isinstance(v, str)})
    return out


# ------------------------------------------------------------------ подписи

# Раздел вики и его название на двух языках. Раздел - это то, чем страницы сгруппированы
# в оглавлении мода, поэтому подпись переводится, а ключ остаётся прежним.
SECTIONS = {
    "weapon":    {"ru": "Оружие",        "en": "Weapons"},
    "ammo":      {"ru": "Боеприпасы",    "en": "Ammunition"},
    "melee":     {"ru": "Ближний бой",   "en": "Melee"},
    "grenade":   {"ru": "Гранаты",       "en": "Grenades"},
    "gear":      {"ru": "Снаряжение",    "en": "Equipment"},
    "corpse":    {"ru": "Трупы",         "en": "Corpses"},
    "goods":     {"ru": "Товары",        "en": "Goods"},
    "armour":    {"ru": "Броня",         "en": "Armour"},
    "research":  {"ru": "Исследования",  "en": "Research"},
    "craft":     {"ru": "Корабли",       "en": "Craft"},
    "facility":  {"ru": "Постройки",     "en": "Facilities"},
}

# battleType -> раздел. Значения из src/Mod/RuleItem.h, enum BattleType.
BATTLE_SECTION = {
    0: "goods", 1: "weapon", 2: "ammo", 3: "melee", 4: "grenade", 5: "grenade",
    6: "gear", 7: "gear", 8: "gear", 9: "gear", 10: "gear", 11: "corpse",
}

L = {
    "ru": {
        "stats": "Числа",
        "weight": "Вес",
        "size": "Место на складе",
        "buy": "Купить",
        "sell": "Продать",
        "transfer": "Доставка, ч",
        "power": "Сила",
        "damage": "Урон",
        "type": "Тип урона",
        "clip": "Зарядов",
        "shots": "Выстрелов",
        "acc.aimed": "Точность, прицельный",
        "acc.snap": "Точность, навскидку",
        "acc.auto": "Точность, очередь",
        "acc.melee": "Точность в рукопашной",
        "tu.aimed": "ОВ, прицельный",
        "tu.snap": "ОВ, навскидку",
        "tu.auto": "ОВ, очередь",
        "tu.melee": "ОВ, удар",
        "tu.throw": "ОВ, бросок",
        "auto.shots": "Патронов в очереди",
        "range.aimed": "Дальность прицельного",
        "range.snap": "Дальность навскидку",
        "range.auto": "Дальность очереди",
        "dropoff": "Спад точности",
        "blast": "Радиус взрыва",
        "fuse": "Запал",
        "armour.item": "Броня предмета",
        "two.handed": "Двуручное",
        "ammo.head": "Чем заряжается",
        "ammo.of": "Чем стреляет",
        "front": "Броня спереди",
        "side": "Броня сбоку",
        "rear": "Броня сзади",
        "under": "Броня снизу",
        "armour.from": "Даёт предмет",
        "bonus": "Прибавки к характеристикам",
        "resist": "Стойкость к урону",
        "cost": "Стоимость",
        "cost.research": "Работа учёных",
        "cost.build": "Работа инженеров",
        "space": "Место в мастерской",
        "needs": "Требует",
        "unlocks": "Открывает",
        "free": "Даёт бесплатно",
        "needs.item": "Нужен предмет",
        "needs.func": "Нужны постройки",
        "made.of": "Из чего",
        "made.gives": "Что получается",
        "speed": "Скорость",
        "accel": "Ускорение",
        "fuel": "Запас топлива",
        "hp": "Прочность",
        "shield": "Щит",
        "armour.craft": "Броня корабля",
        "crew": "Мест для бойцов",
        "cargo": "Место под груз",
        "hwp": "Мест под технику",
        "radar": "Дальность радара",
        "weapons": "Оружейных точек",
        "pilots": "Пилотов",
        "build.cost": "Цена постройки",
        "build.time": "Строится, дней",
        "upkeep": "Содержание в месяц",
        "build.size": "Размер",
        "defence": "Защита базы",
        "yes": "да",
        "no": "нет",
        "source": "Собрано из рулсетов мода, версия {0}. Ключ записи: {1}.",
        "no.name": "без названия",
    },
    "en": {
        "stats": "Numbers",
        "weight": "Weight",
        "size": "Store space",
        "buy": "Buy",
        "sell": "Sell",
        "transfer": "Delivery, h",
        "power": "Power",
        "damage": "Damage",
        "type": "Damage type",
        "clip": "Rounds",
        "shots": "Shots",
        "acc.aimed": "Accuracy, aimed",
        "acc.snap": "Accuracy, snap",
        "acc.auto": "Accuracy, auto",
        "acc.melee": "Accuracy, melee",
        "tu.aimed": "TU, aimed",
        "tu.snap": "TU, snap",
        "tu.auto": "TU, auto",
        "tu.melee": "TU, strike",
        "tu.throw": "TU, throw",
        "auto.shots": "Rounds per burst",
        "range.aimed": "Aimed range",
        "range.snap": "Snap range",
        "range.auto": "Auto range",
        "dropoff": "Accuracy dropoff",
        "blast": "Blast radius",
        "fuse": "Fuse",
        "armour.item": "Item armour",
        "two.handed": "Two-handed",
        "ammo.head": "Takes ammunition",
        "ammo.of": "Fired by",
        "front": "Front armour",
        "side": "Side armour",
        "rear": "Rear armour",
        "under": "Under armour",
        "armour.from": "Given by item",
        "bonus": "Stat bonuses",
        "resist": "Damage resistance",
        "cost": "Cost",
        "cost.research": "Scientist work",
        "cost.build": "Engineer work",
        "space": "Workshop space",
        "needs": "Requires",
        "unlocks": "Unlocks",
        "free": "Gives for free",
        "needs.item": "Needs the item",
        "needs.func": "Needs facilities",
        "made.of": "Made of",
        "made.gives": "Produces",
        "speed": "Speed",
        "accel": "Acceleration",
        "fuel": "Fuel",
        "hp": "Damage capacity",
        "shield": "Shield",
        "armour.craft": "Craft armour",
        "crew": "Soldier slots",
        "cargo": "Cargo space",
        "hwp": "Vehicle slots",
        "radar": "Radar range",
        "weapons": "Weapon hardpoints",
        "pilots": "Pilots",
        "build.cost": "Build cost",
        "build.time": "Build time, days",
        "upkeep": "Upkeep per month",
        "build.size": "Size",
        "defence": "Base defence",
        "yes": "yes",
        "no": "no",
        "source": "Built from the mod's rulesets, version {0}. Record key: {1}.",
        "no.name": "unnamed",
    },
}

# Индекс -> ключ строки. Из src/Ufopaedia/ArticleState.cpp, getDamageTypeText.
DAMAGE_KEY = {
    0: "STR_DAMAGE_NONE", 1: "STR_DAMAGE_ARMOR_PIERCING", 2: "STR_DAMAGE_INCENDIARY",
    3: "STR_DAMAGE_HIGH_EXPLOSIVE", 4: "STR_DAMAGE_LASER_BEAM", 5: "STR_DAMAGE_PLASMA_BEAM",
    6: "STR_DAMAGE_STUN", 7: "STR_DAMAGE_MELEE", 8: "STR_DAMAGE_ACID", 9: "STR_DAMAGE_SMOKE",
}

# Характеристики бойца в armors.stats - подписи те же, что у игры.
STAT_KEY = {
    "tu": "STR_TIME_UNITS", "stamina": "STR_STAMINA", "health": "STR_HEALTH",
    "bravery": "STR_BRAVERY", "reactions": "STR_REACTIONS", "firing": "STR_FIRING_ACCURACY",
    "throwing": "STR_THROWING_ACCURACY", "strength": "STR_STRENGTH", "psiStrength": "STR_PSIONIC_STRENGTH",
    "psiSkill": "STR_PSIONIC_SKILL", "melee": "STR_MELEE_ACCURACY", "mana": "STR_MANA_POOL",
}


def damage_key(n):
    if n in DAMAGE_KEY:
        return DAMAGE_KEY[n]
    return "STR_DAMAGE_%d" % n if 10 <= n <= 19 else None


# ------------------------------------------------------------------ адреса страниц

def slug(kind, key):
    """Адрес страницы строится из КЛЮЧА записи, а не из названия.

    Название у каждого языка своё, а страница на русском и на английском обязана лежать по
    одному адресу: иначе портал не сможет подставить вторую, когда первой ещё нет.
    """
    s = key
    if s.startswith("STR_"):
        s = s[4:]
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    if not s:
        s = "x"
    return s if kind == "item" else "%s-%s" % (kind, s)


# ------------------------------------------------------------------ сборка текста

def tr(strings, key, fallback=None):
    """Строка игры как текст для сайта.

    Разметка движка снимается, но {NEWLINE} - это НЕ мусор: им в описаниях разделены абзацы,
    и если просто его вырезать, соседние предложения склеятся ("при взрывеи скашивают").
    """
    v = strings.get(key)
    if v is None:
        return fallback
    v = v.replace("{NEWLINE}", "\n").replace("{SMALLLINE}", "\n")
    v = re.sub(r"\{[A-Z]+\}", "", v)
    # {NEWLINE} в педии ставили по ширине окошка, а не по смыслу, поэтому часть переносов режет
    # предложение пополам. Абзац начинаем только там, где предыдущий кусок кончился точкой.
    parts = [p.strip() for p in v.split("\n")]
    out = ""
    for part in parts:
        if not part:
            continue
        if not out:
            out = part
        elif out[-1] in ".!?:;":
            out += "\n\n" + part
        else:
            out += " " + part
    return out.strip()


def tr1(strings, key, fallback=None):
    """То же, но в одну строку: название, ячейка таблицы и подпись ссылки перевода строки не терпят."""
    v = tr(strings, key, fallback)
    return re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v


def fmt(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, float):
        return ("%.3f" % v).rstrip("0").rstrip(".")
    return str(v)


class Rows(object):
    """Таблица «подпись - значение». Пустые строки не кладутся: пустая ячейка врёт не меньше."""

    def __init__(self, lang):
        self.lang = lang
        self.rows = []

    def add(self, label_key, value, zero_ok=False):
        if value is None:
            return
        if isinstance(value, bool):
            value = L[self.lang]["yes"] if value else L[self.lang]["no"]
        elif isinstance(value, (int, float)):
            if not zero_ok and not value:
                return
            value = fmt(value)
        elif not str(value).strip():
            return
        self.rows.append((L[self.lang].get(label_key, label_key), str(value)))

    def add_raw(self, label, value):
        if value:
            self.rows.append((label, value))

    def markdown(self):
        if not self.rows:
            return ""
        out = ["| | |", "|---|---|"]
        for a, b in self.rows:
            out.append("| %s | %s |" % (a, b))
        return "\n".join(out)


def link(pages_index, kind, key, strings, strip_uc=False):
    """Ссылка на страницу того же мода, если она есть; иначе просто название."""
    name = tr1(strings, key) or key
    if strip_uc and name == key and key.endswith("_UC"):
        name = tr1(strings, key[:-3]) or key
    target = slug(kind, key)
    if target in pages_index:
        return "[%s](/wiki/%s/%s)" % (name, pages_index[target], target)
    return name


def links(pages_index, kind, keys, strings):
    return ", ".join(link(pages_index, kind, k, strings) for k in keys or [])


# ------------------------------------------------------------------ страницы

def tu_cost(rule, name):
    """Цена действия в ОВ: движок принимает и tuAimed, и costAimed: {time: N} (RuleItem.h, loadCost)."""
    v = rule.get("tu" + name)
    if v is None:
        cost = rule.get("cost" + name)
        if isinstance(cost, dict):
            v = cost.get("time")
    return v


def item_page(key, rule, ctx):
    lang, strings, mod = ctx["lang"], ctx["strings"], ctx["mod"]
    bt = rule.get("battleType", 0) or 0
    section = BATTLE_SECTION.get(bt, "goods")
    r = Rows(lang)
    r.add("weight", rule.get("weight"))
    r.add("size", rule.get("size"))
    r.add("buy", rule.get("costBuy"))
    r.add("sell", rule.get("costSell"))
    r.add("transfer", rule.get("transferTime"))
    r.add("two.handed", True if rule.get("twoHanded") else None)

    power = rule.get("power")
    r.add("power", power)
    dt = rule.get("damageType")
    if dt is not None:
        dk = damage_key(dt)
        r.add("type", tr1(strings, dk, dk) if dk else str(dt))
    # clipSize -1 - это "заряжать нечем, стреляет само" (RuleItem::_clipSize), а не минус один патрон
    clip = rule.get("clipSize")
    r.add("clip", clip if clip is None or clip >= 0 else None)
    r.add("acc.aimed", rule.get("accuracyAimed"))
    r.add("acc.snap", rule.get("accuracySnap"))
    r.add("acc.auto", rule.get("accuracyAuto"))
    r.add("acc.melee", rule.get("accuracyMelee"))
    r.add("tu.aimed", tu_cost(rule, "Aimed"))
    r.add("tu.snap", tu_cost(rule, "Snap"))
    r.add("tu.auto", tu_cost(rule, "Auto"))
    r.add("tu.melee", tu_cost(rule, "Melee"))
    r.add("auto.shots", rule.get("autoShots"))
    r.add("range.aimed", rule.get("aimRange"))
    r.add("range.snap", rule.get("snapRange"))
    r.add("range.auto", rule.get("autoRange"))
    r.add("dropoff", rule.get("dropoff"))
    r.add("blast", rule.get("blastRadius"))
    r.add("fuse", rule.get("fuseType"))
    r.add("armour.item", rule.get("armor"))
    r.add("tu.throw", tu_cost(rule, "Throw"))

    body = [r.markdown()]

    # чем заряжается - и с какими числами: урон у заряда, а не у ствола
    ammo = rule.get("compatibleAmmo") or []
    if isinstance(rule.get("ammo"), dict):
        for slot in rule["ammo"].values():
            if isinstance(slot, dict):
                ammo = ammo + (slot.get("compatibleAmmo") or [])
    ammo = [a for a in dict.fromkeys(ammo) if a in ctx["items"]]
    if ammo:
        head = L[lang]
        # первая колонка - ссылка на сам заряд, поэтому шапка у неё пустая
        table = ["", "## " + head["ammo.head"], "",
                 "| | %s | %s | %s | %s |" % (head["power"], head["type"], head["clip"], head["weight"]),
                 "|---|---|---|---|---|"]
        for a in ammo:
            ar = ctx["items"][a]
            dk = damage_key(ar.get("damageType", 0) or 0)
            rounds = ar.get("clipSize")
            table.append("| %s | %s | %s | %s | %s |" % (
                link(ctx["index"], "item", a, strings),
                fmt(ar.get("power", "")) or "", tr1(strings, dk, "") if dk else "",
                fmt(rounds) if isinstance(rounds, int) and rounds >= 0 else "",
                fmt(ar.get("weight", "")) or ""))
        body.append("\n".join(table))

    # обратная сторона: заряд знает, из чего им стреляют
    guns = ctx["ammo_of"].get(key) or []
    if guns:
        body.append("\n## %s\n\n%s" % (L[lang]["ammo.of"], links(ctx["index"], "item", guns, strings)))

    return section, "\n".join(x for x in body if x)


def armour_page(key, rule, ctx):
    lang, strings = ctx["lang"], ctx["strings"]
    r = Rows(lang)
    r.add("front", rule.get("frontArmor"))
    r.add("side", rule.get("sideArmor"))
    r.add("rear", rule.get("rearArmor"))
    r.add("under", rule.get("underArmor"))
    r.add("weight", rule.get("weight"))
    store = rule.get("storeItem")
    if store and store not in ("STR_NONE", "NONE"):
        r.add_raw(L[lang]["armour.from"], link(ctx["index"], "item", store, strings))
    body = [r.markdown()]

    stats = rule.get("stats")
    if isinstance(stats, dict):
        rows = []
        for stat, value in stats.items():
            name = tr1(strings, STAT_KEY.get(stat, ""), None) or stat
            rows.append("| %s | %+d |" % (name, value) if isinstance(value, int) else "| %s | %s |" % (name, value))
        if rows:
            body.append("\n## %s\n\n| | |\n|---|---|\n%s" % (L[lang]["bonus"], "\n".join(rows)))

    mods = rule.get("damageModifier")
    if isinstance(mods, list) and any(m != 1 for m in mods):
        rows = []
        for i, m in enumerate(mods):
            dk = damage_key(i)
            if dk is None:
                continue
            rows.append("| %s | %s |" % (tr1(strings, dk, dk), fmt(m)))
        if rows:
            body.append("\n## %s\n\n| | |\n|---|---|\n%s" % (L[lang]["resist"], "\n".join(rows)))

    return "armour", "\n".join(x for x in body if x)


def research_page(key, rule, ctx):
    lang, strings = ctx["lang"], ctx["strings"]
    r = Rows(lang)
    r.add("cost.research", rule.get("cost"))
    r.add("needs.item", True if rule.get("needItem") else None)
    body = [r.markdown()]
    for label, keys in (("needs", rule.get("dependencies")),
                        ("unlocks", ctx["unlocks"].get(key)),
                        ("free", rule.get("getOneFree"))):
        if keys:
            body.append("\n## %s\n\n%s" % (L[lang][label], links(ctx["index"], "research", keys, strings)))
    return "research", "\n".join(x for x in body if x)


def craft_page(key, rule, ctx):
    lang = ctx["lang"]
    r = Rows(lang)
    # имена полей - из src/Mod/RuleCraft.h (RuleCraftStats::load), а не по памяти
    r.add("speed", rule.get("speedMax"))
    r.add("accel", rule.get("accel"))
    r.add("fuel", rule.get("fuelMax"))
    r.add("hp", rule.get("damageMax"))
    r.add("shield", rule.get("shieldCapacity"))
    r.add("armour.craft", rule.get("armor"))
    r.add("crew", rule.get("soldiers"))
    r.add("hwp", rule.get("vehicles"))
    r.add("cargo", rule.get("maxItems"))
    r.add("radar", rule.get("radarRange"))
    r.add("weapons", rule.get("weapons"))
    r.add("pilots", rule.get("pilots"))
    r.add("buy", rule.get("costBuy"))
    r.add("sell", rule.get("costSell"))
    r.add("upkeep", rule.get("costRent"))
    return "craft", r.markdown()


def facility_page(key, rule, ctx):
    lang = ctx["lang"]
    r = Rows(lang)
    r.add("build.cost", rule.get("buildCost"))
    r.add("build.time", rule.get("buildTime"))
    r.add("upkeep", rule.get("monthlyCost"))
    r.add("build.size", rule.get("size"))
    r.add("defence", rule.get("defense"))
    return "facility", r.markdown()


KINDS = [
    ("items", "item", item_page),
    ("armors", "armour", armour_page),
    ("research", "research", research_page),
    ("crafts", "craft", craft_page),
    ("facilities", "facility", facility_page),
]


# ------------------------------------------------------------------ прогон

def build(store, strings, lang, mod_slug, version):
    items = store["items"]

    # чем стреляют из заряда - собирается один раз обходом стволов
    ammo_of = collections.defaultdict(list)
    for gun, rule in items.items():
        if (rule.get("battleType") or 0) != 1:
            continue
        for a in rule.get("compatibleAmmo") or []:
            ammo_of[a].append(gun)
        if isinstance(rule.get("ammo"), dict):
            for slot in rule["ammo"].values():
                if isinstance(slot, dict):
                    for a in slot.get("compatibleAmmo") or []:
                        ammo_of[a].append(gun)

    # обратные связи дерева исследований: чьей зависимостью является тема
    unlocks = collections.defaultdict(list)
    for name, rule in store["research"].items():
        for dep in rule.get("dependencies") or []:
            unlocks[dep].append(name)

    # что именно попадает в вики: запись с названием в языке игрока. Запись без названия
    # игрок не видит нигде - это внутренняя механика мода, и страница о ней врала бы.
    chosen = []
    for block, kind, _ in KINDS:
        for key, rule in store[block].items():
            title = tr1(strings, key)
            if not title and key.endswith("_UC"):
                title = tr1(strings, key[:-3])
            if not title:
                continue
            if block == "research" and not rule.get("cost"):
                continue     # тема без работы учёных - это флаг открытия, а не исследование
            chosen.append((block, kind, key, rule, title))

    index = {slug(kind, key): mod_slug for _, kind, key, _, _ in chosen}

    ctx = {
        "lang": lang, "strings": strings, "mod": mod_slug, "items": items,
        "ammo_of": ammo_of, "unlocks": unlocks, "index": index,
    }

    pedia = store["ufopaedia"]
    pages = []
    for block, kind, key, rule, title in chosen:
        make = dict((b, f) for b, _, f in KINDS)[block]
        section, table = make(key, rule, ctx)
        head = []
        art = pedia.get(key)
        if isinstance(art, dict) and art.get("text"):
            prose = tr(strings, art["text"])
            if prose:
                head.append(prose)
        body = "\n\n".join(x for x in head + [table] if x)
        body += "\n\n*%s*\n" % L[lang]["source"].format(version, key)
        pages.append({
            "slug": slug(kind, key),
            "lang": lang,
            "title": title,
            "section": SECTIONS[section][lang],
            "source": key,
            "body": body,
        })
    return pages


def main():
    ap = argparse.ArgumentParser(description="собирает страницы вики из рулсетов мода")
    ap.add_argument("--mod", required=True, help="каталог мода: там Ruleset и Language")
    ap.add_argument("--slug", required=True, help="адрес мода на сайте: /mods/<slug>")
    ap.add_argument("--base", action="append", default=[], help="слой под модом, обычно bin\\standard\\xcom1")
    ap.add_argument("--lang", action="append", default=[], help="язык страниц; можно несколько")
    ap.add_argument("--out", required=True, help="куда положить JSON")
    ap.add_argument("--version", default=None, help="версия мода; по умолчанию из metadata.yml")
    args = ap.parse_args()

    langs = args.lang or ["ru", "en"]
    for lang in langs:
        if lang not in L:
            raise SystemExit("нет подписей для языка %s: добавь их в L в tools/portal_wiki.py" % lang)

    roots = [r for r in args.base] + [args.mod]
    store, files = read_rulesets(roots)
    print("рулсетов прочитано: %d" % files)
    for block in BLOCKS:
        print("   %-12s %d" % (block, len(store[block])))

    version = args.version
    if not version:
        meta = os.path.join(args.mod, "metadata.yml")
        version = str((load_yaml(meta) or {}).get("version", "")) if os.path.isfile(meta) else ""

    pages = []
    for lang in langs:
        strings = read_strings(roots, lang)
        got = build(store, strings, lang, args.slug, version)
        by_section = collections.Counter(p["section"] for p in got)
        print("%s: строк в языке %d, страниц %d" % (lang, len(strings), len(got)))
        for name, n in by_section.most_common():
            print("   %-16s %d" % (name, n))
        if not got:
            raise SystemExit("язык %s не дал ни одной страницы - это ошибка разбора, а не пустой мод" % lang)
        pages.extend(got)

    out = {
        "mod": args.slug,
        "version": version,
        "generated": datetime.datetime.now().replace(microsecond=0).isoformat(),
        "pages": pages,
    }
    folder = os.path.dirname(os.path.abspath(args.out))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(args.out, "w", encoding=ENC_W, newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    size = os.path.getsize(args.out)
    print("готово: %s, страниц %d, %.1f МБ" % (args.out, len(pages), size / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
