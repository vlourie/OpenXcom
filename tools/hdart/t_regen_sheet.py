#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Листы к t_regen_obj.py (модель не грузит, видеокарта не нужна): классика / HD сейчас / варианты на сером, тёмном и светлом
фоне и в сцене карты (крупно и в масштабе игры k=4) -> art/_review/tickets_2026-10-23/gen_XP-000NNN.png.

    py -3.13 tools\hdart\t_regen_sheet.py t264 | t248 | t253_75 (лист на все пять кадров 75-79) | t249
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import t_regen_obj as r                          # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2 or (sys.argv[1] not in r.JOBS and sys.argv[1] != "t249"):
        raise SystemExit(__doc__)
    r.do_sheet(sys.argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
