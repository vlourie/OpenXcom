#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сравнение решений ИИ двух сборок по отпечаткам [AIDECIDE].

Зачем: число обращений к ИИ и даже posScanned зависят от кадров реального времени,
поэтому по ним нельзя сказать, изменила правка решения или нет (грабли R-025).
Строка [AIDECIDE] пишется РОВНО ОДИН раз на юнита в ход - на первое обращение,
когда состояние боя у любой сборки одно и то же. Её и сравниваем.

Пример:
  python tools/aibench/decide_diff.py BrutalAI/user_pz/log_a_1.log BrutalAI/user_pz/log_b_1.log
"""

import argparse
import re
import sys

ENC_R = "utf-8"
LINE = re.compile(r"\[AIDECIDE\] (.*)")
KV = re.compile(r"(\w+)=(.+?)(?=\s+\w+=|$)")


def parse(path):
    """Отпечатки решений: (ход, юнит) -> (откуда, тип действия, цель)."""
    out = {}
    with open(path, "r", encoding=ENC_R, errors="replace") as f:
        for line in f:
            m = LINE.search(line)
            if not m:
                continue
            kv = dict(KV.findall(m.group(1).strip()))
            key = (int(kv["turn"]), int(kv["unit"]))
            out[key] = (kv.get("side"), kv.get("from"), kv.get("type"), kv.get("target"))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--show", type=int, default=10, help="сколько расхождений печатать")
    args = p.parse_args()

    a, b = parse(args.a), parse(args.b)
    if not a or not b:
        sys.exit("нет строк [AIDECIDE]: нужен бинарник с патчем и -aiBench true")

    both = sorted(set(a) & set(b))
    same = [k for k in both if a[k] == b[k]]
    diff = [k for k in both if a[k] != b[k]]

    print("общих решений: %d, совпало: %d, разошлось: %d" % (len(both), len(same), len(diff)))
    only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    if only_a or only_b:
        print("только в первом: %d, только во втором: %d "
              "(юнит не дожил или не дошла очередь - сравнению не мешает)"
              % (len(only_a), len(only_b)))

    for k in diff[:args.show]:
        print("  ход %d юнит %d:" % k)
        print("    A side=%s from=%s type=%s target=%s" % a[k])
        print("    B side=%s from=%s type=%s target=%s" % b[k])

    # расхождение решений - это не ошибка, а ответ: правка на поведение влияет
    return 0


if __name__ == "__main__":
    sys.exit(main())
