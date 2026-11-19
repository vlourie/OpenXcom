# -*- coding: utf-8 -*-
"""Общее для скриптов tools/hdart: где лежит установка X-Piratez.

Пути относительные, от корня репозитория: скрипты запускаются из корня (как и раньше, когда
каждый собирал этот путь сам - 21 файл, аудит 2026-09-26, пункт A-3). Кому нужен абсолютный
путь, соединяет с своим ROOT: os.path.join(ROOT, common.PIRATEZ).
"""
import os

INSTALL = os.path.join("Пиратки", "Dioxine_XPiratez")   # установленная игра - только чтение (правило 6)
MODS = os.path.join(INSTALL, "user", "mods")
PIRATEZ = os.path.join(MODS, "Piratez")                  # данные мода: TERRAIN, Ruleset, Resources
GAME_HD = os.path.join(MODS, "hd")                       # копия мода hd, которую читает игра (R-081, семья R-087)
