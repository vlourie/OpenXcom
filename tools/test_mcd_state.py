#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/mcd_state.py на синтетических записях MCD: die одной основы - STRONG, общий обломок -
CANDIDATE, взаимный alt - основа по клеткам, петля анимации со сдвигом фазы - одна группа без цикла, цепочка
die - корень, die-цель, что стоит на картах втрое чаще основы, - CANDIDATE (контроль: без правила - STRONG).

    py -3.13 tools/test_mcd_state.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import mcd_state as ms  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def rec(frame, die=0, alt=0, frames=None):
    return {"frame": frame, "frames": frames or [frame] * 8, "die": die, "alt": alt}


def find(links, state, base=None):
    return [x for x in links if x["state"] == state and (base is None or x["base"] == base)]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    # NUKE2: запись 3 (кадр 3) die -> запись 2 (кадр 2)
    links = ms.set_links("S", [rec(0), rec(1), rec(2), rec(3, die=2)], {})
    x = find(links, "S:2", "S:3")
    check("die одной основы - STATE_VARIANT_OF STRONG", len(x) == 1 and x[0]["level"] == "STRONG"
          and x[0]["kind"] == "STATE_VARIANT_OF" and x[0]["root"] == "S:3")
    check("основа сама состоянием не стала", not find(links, "S:3"))
    # общий обломок: кадр 9 - die трёх разных основ
    links = ms.set_links("S", [rec(0), rec(1, die=4), rec(2, die=4), rec(3, die=4), rec(9)], {})
    check("общий обломок - CANDIDATE", all(x["level"] == "CANDIDATE" for x in find(links, "S:9")) and
          len(find(links, "S:9")) == 3)
    # взаимный alt (дверь): кадр 5 стоит на картах чаще - он основа
    recs = [rec(0), rec(5, alt=2), rec(6, alt=1)]
    links = ms.set_links("S", recs, {("S", 5): 40, ("S", 6): 0})
    check("взаимный alt - состояние кадр с меньшим числом клеток", [x["base"] for x in find(links, "S:6")] == ["S:5"]
          and not find(links, "S:5"))
    links = ms.set_links("S", recs, {})
    check("взаимный alt поровну - CANDIDATE", all(x["level"] == "CANDIDATE" for x in links if x["via"] == "alt"))
    # петля со сдвигом фазы: записи 20-21-22 и 21-22-20 - одна группа, основа одна
    recs = [rec(0), rec(20, frames=[20, 21, 22, 20, 21, 22, 20, 21]), rec(21, frames=[21, 22, 20, 21, 22, 20, 21, 22])]
    links = ms.set_links("S", recs, {("S", 21): 9, ("S", 20): 3})
    an = [x for x in links if x["via"] == "anim"]
    check("петля анимации - основа по клеткам, без цикла", {x["base"] for x in an} == {"S:21"} and
          {x["state"] for x in an} == {"S:20", "S:22"})
    # цепочка: 26 die -> 27, 27 die -> 23
    links = ms.set_links("S", [rec(0), rec(26, die=2), rec(27, die=3), rec(23)], {})
    check("цепочка die - корень основы", find(links, "S:23")[0]["root"] == "S:26")
    # FORESTRED: пол 4 - die 1, но стоит в 1188 клетках против 140
    recs = [rec(0), rec(1, die=2), rec(4)]
    cells = {("S", 4): 1188, ("S", 1): 140}
    check("цель die втрое чаще основы - CANDIDATE", find(ms.set_links("S", recs, cells), "S:4")[0]["level"] == "CANDIDATE")
    check("контроль: без правила частоты - STRONG",
          find(ms.set_links("S", recs, cells, dominant=False), "S:4")[0]["level"] == "STRONG")
    check("редкая цель (меньше 20 клеток) не трогается",
          find(ms.set_links("S", recs, {("S", 4): 12, ("S", 1): 0}), "S:4")[0]["level"] == "STRONG")
    # индекс: обе стороны
    idx = ms.index({"S": ms.set_links("S", [rec(0), rec(2), rec(3, die=1)], {})})
    check("индекс: состояние derived, основа base", idx["S:2"][0]["side"] == "derived" and
          idx["S:3"][0]["side"] == "base" and idx["S:3"][0]["relative"] == "S:2")
    print("\nпровалов: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
