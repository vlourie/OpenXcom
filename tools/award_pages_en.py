#!/usr/bin/env python3
"""
Страницы наград X-Piratez по уровням - для английской игры.

Русский патч (XPZ RU-patch) делит статьи наград ХабароПедии на два-три экрана: первый -
прежний текст, дальше таблица «ПО УРОВНЯМ». Таблицы написал переводчик, в английском моде
их нет вовсе, поэтому английская игра показывает награду одним экраном. Движку язык не
важен: pages: работает на любом, не хватает только правил и английских строк.

Скрипт берёт из патча статьи с pages: (без text_width - он подобран под русский текст)
и строки страниц _2, _3..., переводит таблицы по словарю статов и кладёт их ОДНИМ файлом
прямо в мод Пираток (Ruleset/zz_award_pages_en.rul: страницы плюс extraStrings en-US) -
отдельного мода нет. Русской игре файл не мешает: там строки даёт RU-патч.
Статью, где после перевода осталась кириллица (проза, имена), не трогает вовсе и
называет в выводе: лучше один экран, чем половина по-русски.

    py -3 tools/award_pages_en.py        пишет в Пиратки/.../user/mods/Piratez
"""
import argparse
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
from pck_census import Tolerant  # noqa: E402  (терпит повторные якоря, R-046)


class OxceLoader(Tolerant):
    """Теги OXCE (!add, !remove, !info) читаются как обычные значения: нам нужны только pages."""


def _untagged(loader, suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


OxceLoader.add_multi_constructor("!", _untagged)


def load_yaml(path):
    with open(path, "rb") as f:
        return yaml.load(f, Loader=OxceLoader)

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PATCH = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "XPZ RU-patch")
PIRATEZ = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez")
RUL_NAME = "zz_award_pages_en.rul"

# длинное раньше короткого: «восст. ОВ» раньше «ОВ»
PHRASES = [
    ("выше порог реген. ОЗ", "higher HP regen threshold"),
    ("(при ранениях)", "(when wounded)"),
    ("без изменений", "no change"),
    ("ПО УРОВНЯМ", "BY LEVEL"),
]
TERMS = [
    ("восст. от Оглуш.", "Stun recovery"),
    ("восст. ОВ", "Energy Regen"),
    ("восст. БД", "Morale Regen"),
    ("восст. ОД", "TU Regen"),
    ("восст. Бодрости", "FRS Regen"),
    ("реген. ОЗ", "HP regen"),
    ("Обзору ночью", "Night Vision"),
    ("П.Броне", "Front Armor"),
    ("Б.Броне", "Side Armor"),
    ("З.Броне", "Rear Armor"),
    ("Н.Броне", "Under Armor"),
    ("Бл.Бою", "MEL"),
    ("С.Вуду", "VPWR"),
    ("Н.Вуду", "VSKL"),
    ("Бодрости", "FRS"),
    ("Реакции", "REA"),
    ("Стрельбе", "ACC"),
    ("Метанию", "THR"),
    ("Храбрости", "BRA"),
    ("Контузии", "Stun"),
    ("Чутью", "SENSE"),
    ("Силе", "STR"),
    ("ОВ", "STA"),
    ("ОЗ", "HP"),
    ("ОД", "TU"),
    ("БД", "Morale"),
]
FULLWIDTH = {ord("０") + i: ord("0") + i for i in range(10)}


def translate(text):
    t = text.translate(FULLWIDTH)
    for ru, en in PHRASES:
        t = t.replace(ru, en)
    # «+1 к ОЗ» -> «+1 HP»: число остаётся, «к» уходит
    for ru, en in TERMS:
        t = re.sub(r"([+\-−]?\d+(?:\.\d+)?) к " + re.escape(ru), lambda m: m.group(1) + " " + en, t)
    t = t.replace(" и ", " and ")
    return t


def read_strings(path):
    out = {}
    for line in io.open(path, encoding="utf-8-sig"):
        m = re.match(r'\s+(STR_\w+):\s*"(.*)"\s*$', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--piratez", action="append", help="папка мода Piratez (по умолчанию - в установке Пираток)")
    args = ap.parse_args()

    rules = load_yaml(os.path.join(PATCH, "Ruleset", "EX_ufopedia.rul"))
    ru = read_strings(os.path.join(PATCH, "Language", "ru.yml"))
    arts, strings, skipped = [], {}, []
    for a in rules.get("ufopaedia", []):
        pages = a.get("pages")
        if not pages or not a.get("id", "").startswith("STR_MEDAL_"):
            continue
        extra = {}
        ok = True
        for p in pages[1:]:
            for key in (p.get("title"), p.get("text")):
                if not key:
                    continue
                if key not in ru:
                    ok = False
                    break
                en = translate(ru[key])
                if re.search("[А-Яа-яЁё]", en):
                    ok = False
                    break
                extra[key] = en
        if ok:
            arts.append(a)
            strings.update(extra)
        else:
            skipped.append(a["id"])

    for mod in args.piratez or [PIRATEZ]:
        # один файл внутри самого мода Пираток: страницы и их английские строки вместе.
        # Имя с zz_, чтобы шёл после рулсетов Пираток; статьи сливаются по id.
        # Файл читает игра (yaml-cpp), не PowerShell: без спецификации (R-001, исключение)
        out = os.path.join(mod, "Ruleset", RUL_NAME)
        with io.open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write("# Страницы наград по уровням для английской игры (как в XPZ RU-patch).\n"
                    "# Сделано tools/award_pages_en.py; новая версия Пираток этот файл не содержит -\n"
                    "# после её установки запустить скрипт заново.\nufopaedia:\n")
            for a in arts:
                f.write("  - id: %s\n    pages:\n" % a["id"])
                for p in a["pages"]:
                    f.write("    - title: %s\n      text: %s\n" % (p["title"], p["text"]))
            f.write("extraStrings:\n  - type: en-US\n    strings:\n")
            for k in sorted(strings):
                f.write('      %s: "%s"\n' % (k, strings[k].replace('"', '\\"')))
        print("%s: %d статей, %d строк" % (out, len(arts), len(strings)))
    if skipped:
        print("оставлены одним экраном (после перевода осталась кириллица): %d" % len(skipped))
        for s in skipped:
            print("  ", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
