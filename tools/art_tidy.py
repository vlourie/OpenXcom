#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Свести всю графику в одно дерево art\ и убрать с корня старьё.

Зачем. Корень проекта оброс полусотней папок обмена с моделью (gpt_swamp, gpt_swamp2 ...
gpt_swamp13), просмотрами, пробами и остатками июньских прогонов. По именам уже не
вспомнить, какая партия к какому набору относится, а листы наборов лежат отдельно от
отчётов сверки. Поэтому графика собирается в одно дерево, повторяющее устройство мода:

    art\
      TERRAIN\<НАБОР>.PCK\        листы набора как были: layout.json, original*.png, crops\
                    sent\NN\      что уходило в модель (партия NN)
                    returned\NN\  что вернулось
                    report\       отчёт tile_forge: forge.tsv, листы сверки
      <НАБОР>.PCK\                наборы не из TERRAIN (SMOKE и прочие)
      _review\                    просмотры и сравнения
      _experiments\               пробы параметров, разовые опыты
      _refs\                      исходные фотографии и прочая натура

Скрипты НЕ переезжают: они под гитом в tools\hdart и на них ссылается вся документация.
Готовые паки тоже не копируются - они живут в моде, и вторая копия мода уже стоила нам
целого прогона (грабли R-015). В art\ лежит только то, из чего пак делается.

    py -3 tools\art_tidy.py              только показать план, ничего не трогая
    py -3 tools\art_tidy.py --apply      выполнить

Перенос идёт переименованием в пределах диска - мгновенно, копий не создаёт. Ни один
шаг не перезаписывает непустое место назначения: такой шаг помечается ПРОПУСК.
"""
import argparse
import filecmp
import os
import shutil
import stat
import sys

ENC = "utf-8-sig"

# Обменники с моделью: папка -> (набор, номер партии). Соответствие восстановлено по
# именам кадров внутри и по описаниям _ОПИСАНИЯ.txt, а не по имени папки.
EXCHANGE = {
    "gpt_swamp":    ("TERRAIN/FORESTSWAMP.PCK", "01"),
    "gpt_swamp2":   ("TERRAIN/FORESTSWAMP.PCK", "02"),
    "gpt_swamp3":   ("TERRAIN/FORESTSWAMP.PCK", "03"),
    "gpt_swamp4":   ("TERRAIN/FORESTSWAMP.PCK", "04"),
    "gpt_swamp5":   ("TERRAIN/FORESTSWAMP.PCK", "05"),
    "gpt_swamp6":   ("TERRAIN/FORESTSWAMP.PCK", "06"),
    "gpt_swamp7":   ("TERRAIN/FORESTSWAMP.PCK", "07"),
    "gpt_swamp8":   ("TERRAIN/FORESTSWAMP.PCK", "08"),
    "gpt_swamp9":   ("TERRAIN/FORESTSWAMP.PCK", "09"),
    "gpt_swamp10":  ("TERRAIN/FORESTSWAMP.PCK", "10"),
    "gpt_swamp11":  ("TERRAIN/FORESTSWAMP.PCK", "11"),
    "gpt_swamp12":  ("TERRAIN/FORESTSWAMP.PCK", "12"),
    "gpt_swamp13":  ("TERRAIN/FORESTSWAMP.PCK", "13"),
    "gpt_desert":   ("TERRAIN/DESERT.PCK",      "01"),
    "gpt_fire":     ("SMOKE.PCK",               "01"),
}

# Имена подпапок обменника, в которых лежит ОТВЕТ модели. Всё остальное - то, что уходило.
RETURNED = ("Результат", "return", "returned", "Результаты")

REVIEW = ["review", "review_field", "review_qwen", "_cmp", "floors_check", "floors_ru",
          "cmp_fast_slow", "hit_compare"]
EXPERIMENTS = ["field_sweep", "qwen_sweep", "one_tile", "tank_work", "мурукон"]
REFS = ["photo_refs", "hdglobe_dl", "pics"]

# Прежде чем снести папку-двойник, из неё вынимается всё, чего нет в рабочем дереве
# ПОБАЙТОВО. Иначе вместе с 449 одинаковыми подсказками уедут 92 файла вчерашней работы:
# варианты полей CULTIVAT и DESERT (грабли R-039) и две правленые подсказки.
SALVAGE = {"hdart_sheets_pz_new": "_experiments/sheets_new"}

# Снести. Согласовано отдельно, каждая строка - почему.
DELETE = {
    "hdart_sheets_pz_new": "вторая копия листов наборов, рабочая - hdart_sheets_pz",
    "gfxscan":             "разовый обход графики, июнь",
    "roofscan":            "разовый обход крыш, июнь",
    "Multiplayer":         "один .rar, к проекту отношения не имеет",
    "Claude outputs":      "выгрузки переписки, в работе не участвуют",
}

# Не наше: дерево репозитория, установки игры, окружения. Молчим про них.
KEEP = {"bin", "build-release", "cmake", "deps", "dist", "docs", "install", "libs", "obj",
        "res", "scripts", "src", "tools", "user", "census", "forge", "dataset",
        "hdart_sheets_pz", "BrutalAI", "logs", "Пиратки", "X-Files 41b"}


def reparse(path):
    """Точка повторного разбора: junction или символьная ссылка. os.path.islink на
    Windows junction НЕ видит, поэтому смотрим сам флаг файловой системы."""
    try:
        return bool(os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, AttributeError):
        return False


def mb(path):
    """Размер дерева в мегабайтах. В соединения (junction) НЕ заходим: внутри BrutalAI
    их 112 штук на установку Пираток, и обход по ним даёт враньё в десятки гигабайт."""
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not reparse(os.path.join(root, d))]
        for f in files:
            p = os.path.join(root, f)
            try:
                total += os.path.getsize(p)
            except OSError:
                pass
    return total / 1048576.0


def nonempty(path):
    return os.path.isdir(path) and bool(os.listdir(path))


class Plan(object):
    def __init__(self, root, apply_):
        self.root = root
        self.apply = apply_
        self.moved = 0
        self.deleted = 0
        self.skipped = 0
        self.bytes_freed = 0.0

    def move(self, src, dst, note=""):
        s = os.path.join(self.root, src)
        d = os.path.join(self.root, dst)
        if not os.path.exists(s):
            return
        if nonempty(d):
            print("  ПРОПУСК %-28s -> %s (место занято)" % (src, dst))
            self.skipped += 1
            return
        print("  %-28s -> %-42s %s" % (src, dst, note))
        if self.apply:
            os.makedirs(os.path.dirname(d) or self.root, exist_ok=True)
            if os.path.isdir(d):
                os.rmdir(d)
            os.rename(s, d)
        self.moved += 1

    def move_files(self, src, dst, skipdirs=()):
        """Перенести ФАЙЛЫ из src в dst, подпапки из skipdirs оставить на месте."""
        s = os.path.join(self.root, src)
        d = os.path.join(self.root, dst)
        if not os.path.isdir(s):
            return
        names = [n for n in os.listdir(s)
                 if n not in skipdirs and not os.path.isdir(os.path.join(s, n))]
        if not names:
            return
        print("  %-28s -> %-42s %d файлов" % (src, dst, len(names)))
        if self.apply:
            os.makedirs(d, exist_ok=True)
            for n in names:
                os.replace(os.path.join(s, n), os.path.join(d, n))
        self.moved += 1

    def salvage(self, name, twin, dst):
        """Вынести из папки-двойника всё, что не совпадает побайтно с рабочим деревом."""
        src = os.path.join(self.root, name)
        ref = os.path.join(self.root, twin)
        if not os.path.isdir(src):
            return
        uniq = []
        for r, _dirs, files in os.walk(src):
            for f in files:
                a = os.path.join(r, f)
                rel = os.path.relpath(a, src)
                b = os.path.join(ref, rel)
                if not os.path.exists(b) or not filecmp.cmp(a, b, shallow=False):
                    uniq.append(rel)
        if not uniq:
            print("  %-28s -> ничего уникального" % name)
            return
        print("  СПАСТИ  %-28s -> %-32s %d файлов" % (name, dst, len(uniq)))
        for rel in uniq[:4]:
            print("            %s" % rel)
        if len(uniq) > 4:
            print("            ... ещё %d" % (len(uniq) - 4))
        if self.apply:
            for rel in uniq:
                d = os.path.join(self.root, dst, rel)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                os.replace(os.path.join(src, rel), d)
        self.moved += 1

    def drop(self, name, why):
        p = os.path.join(self.root, name)
        if not os.path.exists(p):
            return
        size = mb(p)
        print("  СНЕСТИ  %-28s %8.0f МБ  %s" % (name, size, why))
        if self.apply:
            shutil.rmtree(p, ignore_errors=True)
        self.deleted += 1
        self.bytes_freed += size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--art", default="art")
    ap.add_argument("--sheets", default="hdart_sheets_pz")
    ap.add_argument("--forge", default="forge")
    ap.add_argument("--apply", action="store_true", help="без него только показывает план")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    art = args.art
    p = Plan(root, args.apply)

    print("КУДА: %s" % os.path.join(root, art))
    print("режим: %s\n" % ("ВЫПОЛНЯЮ" if args.apply else "только план, ничего не трогаю"))

    # 1. листы наборов: одним переименованием родителя, 635 папок не по одной
    print("Листы наборов")
    s = os.path.join(root, args.sheets)
    d = os.path.join(root, art, "TERRAIN")
    if os.path.isdir(s) and not nonempty(d):
        n = len(os.listdir(s))
        print("  %-28s -> %-42s %d наборов" % (args.sheets, art + "/TERRAIN", n))
        if args.apply:
            os.makedirs(os.path.join(root, art), exist_ok=True)
            try:
                if os.path.isdir(d):
                    os.rmdir(d)
                os.rename(s, d)
            except OSError:
                # Переименовать САМУ папку нельзя, когда её держит открытой окно
                # проводника или терминал: Windows не даёт трогать каталог, который
                # чей-то текущий. Дети при этом переименовываются свободно, поэтому
                # переносим по набору - те же мгновенные переименования, только 635 штук.
                os.makedirs(d, exist_ok=True)
                stuck = []
                for name in os.listdir(s):
                    try:
                        os.replace(os.path.join(s, name), os.path.join(d, name))
                    except OSError:
                        stuck.append(name)
                if stuck:
                    print("      ЗАПЕРТО, осталось на месте: %s" % ", ".join(stuck))
                    print("      закрой то, что их открыло, и повтори --apply")
                try:
                    os.rmdir(s)
                except OSError:
                    pass
        p.moved += 1
    elif os.path.isdir(s):
        print("  ПРОПУСК %s -> %s/TERRAIN (место занято)" % (args.sheets, art))
        p.skipped += 1
    else:
        print("  уже перенесено")

    # 2. отчёты сверки под свой набор
    print("\nОтчёты сверки")
    f = os.path.join(root, args.forge)
    if os.path.isdir(f):
        for name in sorted(os.listdir(f)):
            if os.path.isdir(os.path.join(f, name)):
                p.move("%s/%s" % (args.forge, name),
                       "%s/TERRAIN/%s/report" % (art, name), "")
    else:
        print("  нет")

    # 3. обменники с моделью
    print("\nОбмен с моделью")
    for name in sorted(EXCHANGE, key=lambda k: (EXCHANGE[k][0], EXCHANGE[k][1])):
        target, batch = EXCHANGE[name]
        src = os.path.join(root, name)
        if not os.path.isdir(src):
            continue
        for sub in RETURNED:
            if os.path.isdir(os.path.join(src, sub)):
                p.move("%s/%s" % (name, sub),
                       "%s/%s/returned/%s" % (art, target, batch), "ответ модели")
        p.move_files(name, "%s/%s/sent/%s" % (art, target, batch), skipdirs=RETURNED)
        rest = os.listdir(src) if os.path.isdir(src) else []
        if not rest and p.apply:
            os.rmdir(src)
        elif rest:
            print("      осталось в %s: %s" % (name, ", ".join(rest[:5])))

    # 4. просмотры, пробы, натура
    for title, names, sub in (("Просмотры", REVIEW, "_review"),
                              ("Пробы", EXPERIMENTS, "_experiments"),
                              ("Натура", REFS, "_refs")):
        print("\n%s" % title)
        for name in names:
            p.move(name, "%s/%s/%s" % (art, sub, name))

    # 5. снести
    # сверяемся с рабочими листами ТАМ, где они лежат сейчас: к этому шагу они уже
    # переименованы в art\TERRAIN, и сравнение со старым путём нашло бы уникальным всё
    print("\nСпасти из двойников")
    twin = os.path.join(art, "TERRAIN") if os.path.isdir(d) else args.sheets
    for name, dst in SALVAGE.items():
        p.salvage(name, twin, os.path.join(art, dst))

    print("\nСнести")
    for name, why in DELETE.items():
        p.drop(name, why)

    # 6. что осталось неразобранным на корне
    known = set(KEEP) | set(DELETE) | set(EXCHANGE) | set(REVIEW) | set(EXPERIMENTS) | set(REFS)
    known.add(art)
    rest = [n for n in sorted(os.listdir(root))
            if os.path.isdir(os.path.join(root, n)) and not n.startswith(".")
            and n not in known]
    if rest:
        print("\nНе разобрано (оставлено на месте): %s" % ", ".join(rest))

    print("\nитого: перенести %d, снести %d (%.0f МБ), пропустить %d"
          % (p.moved, p.deleted, p.bytes_freed, p.skipped))
    if not args.apply:
        print("это только план. выполнить: py -3 tools\\art_tidy.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
