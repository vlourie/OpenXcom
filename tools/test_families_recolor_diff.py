#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/families_recolor_diff.py на синтетике: новая пара в разных семействах - слияние; цепочка
A~B~C, где A и C напрямую не перекраска, - ложная цепочка (контроль: если напрямую проходит - цепочки нет);
пара внутри одного семейства не новая; строгий тест - силуэт и функция цвета в обе стороны.

    py -3.13 tools/test_families_recolor_diff.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import families_recolor_diff as frd  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fam_of = {"A:1": "F1", "B:1": "F2", "C:1": "F2", "D:1": "F3", "D:2": "F3"}
    pairs = [("A:1", "B:1", "STRONG"), ("B:1", "C:1", "CANDIDATE"), ("D:1", "D:2", "CANDIDATE"),
             ("E:1", "E:2", "CANDIDATE")]
    new, merges, chains, comp = frd.diff(pairs, {}, fam_of, lambda a, b: False)
    got = {(x["a"], x["b"]): x["case"] for x in new}
    check("пара в разных семействах - новая", got.get(("A:1", "B:1")) == "разные семейства")
    check("пара в одном семействе - не новая", ("B:1", "C:1") not in got and ("D:1", "D:2") not in got)
    check("пара вне семейств - новая", got.get(("E:1", "E:2")) == "оба вне семейств")
    check("компонента задевает F1 и F2 - слияние", [m["families"] for m in merges] == [["F1", "F2"]])
    check("A~C только через B - ложная цепочка", [c["not_direct"] for c in chains] == [[["A:1", "C:1"]]])
    _n, _m, chains2, _c = frd.diff(pairs, {}, fam_of, lambda a, b: True)
    check("контроль: напрямую проходит - цепочки нет", chains2 == [])

    m = np.ones((4, 4), bool)
    ca = np.arange(16).reshape(4, 4) % 4
    check("перекраска один к одному - строгая", frd.strict(m, ca, m, (ca + 7) % 11)[3])
    cb = ca // 2                                    # две пары цветов слиты: в одну сторону функция, обратно нет
    r = frd.strict(m, ca, m, cb)
    check("сжатая палитра - не строгая, причина 'в одну сторону'",
          not r[3] and frd.unconf_why(*r[:3]).startswith("функция в одну сторону"))
    m2 = m.copy()
    m2[:, :2] = False
    check("силуэт другой - не строгая", not frd.strict(m, ca, m2, ca)[3])
    print("\nпровалов: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
