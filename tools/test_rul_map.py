#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rul_map.py читает рулсеты так же, как движок (грабли R-046 и R-043: инструмент обязан
читать данные как игра, иначе проверка проверяет инструмент).

Синтетический мод из двух файлов, без установки Пираток:
  * порядок - полный путь по УБЫВАНИЮ (Mod::loadMod): b.rul грузится раньше a.rul;
  * повтор ключа - берётся ПЕРВЫЙ (YamlNodeReader::useIndex, emplace), PyYAML взял бы последний;
  * refNode читается раньше своих полей; delete убирает запись;
  * ключ, который движок читает у другого раздела, помечается «не в классе»;
  * битая ссылка находится, а STR_NONE и dummy ссылками не считаются.

    py -3 tools\\test_rul_map.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

A_RUL = """\
items:
  - type: STR_GUN
    power: 30
    power: 99
    costSell: 5
  - type: STR_TEMPLATE_AMMO
    power: 11
    weight: 3
  - delete: STR_GONE
research:
  - name: STR_GUN
    cost: 10
    dependencies: [STR_BASE]
  - name: STR_BASE
    cost: 1
  - name: STR_LOOP_A
    dependencies: [STR_LOOP_B]
  - name: STR_LOOP_B
    dependencies: [STR_LOOP_A]
  - name: STR_LOOP_C
    unlocks: [STR_LOOP_A]
manufacture:
  - name: STR_GUN
    requires: [STR_GUN, STR_TYPO_TOPIC]
    requiredItems: {STR_GUN: 1}
  - name: STR_GUN2
    requires: [STR_GUN]
  - name: STR_GUN3
    requires: [STR_BASE]
armors:
  - type: STR_ARMOR
    storeItem: STR_NONE
alienDeployments:
  - type: STR_SITE
    despawnEvenIfTargeted: true
"""

B_RUL = """\
tmpl: &T
  power: 7
  weight: 1
items:
  - type: STR_GUN
    costSell: 1
  - type: STR_GONE
    power: 1
  - type: STR_CLIP
    refNode: *T
    weight: 2
"""


def main():
    with tempfile.TemporaryDirectory() as tmp:
        mod = Path(tmp, "mod")
        (mod / "Ruleset").mkdir(parents=True)
        (mod / "Ruleset" / "a.rul").write_text(A_RUL, encoding="utf-8")
        (mod / "Ruleset" / "b.rul").write_text(B_RUL, encoding="utf-8")
        out = Path(tmp, "out")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, str(HERE / "rul_map.py"), "--mod", str(mod),
                            "--master", "", "--out", str(out)],
                           capture_output=True, text=True, encoding="utf-8", env=env)
        if r.returncode:
            print(r.stdout, r.stderr)
            print("итог: ОШИБКА - скрипт упал")
            return 1

        def rows(name):
            with open(out / name, encoding="utf-8-sig") as f:
                return [ln.rstrip("\n").split("\t") for ln in f][1:]

        vals = {(r[0], r[1], r[2]): r[3] for r in rows("values.tsv")}
        unk = {(r[0], r[2]): r[3] for r in rows("unknown_keys.tsv")}
        dang = {(r[0], r[1], r[4]) for r in rows("dangling.tsv")}
        dups = {(r[2], r[4], r[5]) for r in rows("dup_keys.tsv")}
        cyc = rows("research_cycles.tsv")
        checks = [
            ("повтор ключа: движок берёт первый (30, а не 99)",
             vals.get(("items", "STR_GUN", "power")) == "30"),
            ("повтор записан в dup_keys.tsv с потерянным значением",
             ("power", "30", "99") in dups),
            ("порядок по убыванию пути: a.rul позже b.rul, costSell = 5",
             vals.get(("items", "STR_GUN", "costSell")) == "5"),
            ("delete в a.rul убрал запись, заведённую в b.rul",
             ("items", "STR_GONE", "power") not in vals),
            ("refNode: поле шаблона пришло (power 7)",
             vals.get(("items", "STR_CLIP", "power")) == "7"),
            ("refNode: своё поле сильнее шаблона (weight 2)",
             vals.get(("items", "STR_CLIP", "weight")) == "2"),
            ("ключ миссии у развёртывания - «не в классе»",
             unk.get(("alienDeployments", "despawnEvenIfTargeted"), "").startswith("не в классе")),
            ("битая ссылка manufacture.requires найдена",
             ("manufacture", "STR_GUN", "STR_TYPO_TOPIC") in dang),
            ("STR_NONE - не битая ссылка",
             not any(d[2] == "STR_NONE" for d in dang)),
            ("цикл A<->B найден и вход через unlocks STR_LOOP_C назван",
             len(cyc) == 1 and "STR_LOOP_C" in cyc[0][1]),
        ]
        bad = 0
        for name, ok in checks:
            print("%s  %s" % ("ok " if ok else "BAD", name))
            bad += not ok
        print("итог: %s" % ("всё верно" if not bad else "ОШИБОК: %d" % bad))
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
