#!/usr/bin/env python3
"""Доказательство полноты переписи графики юнитов: манифест охвата (docs/HD_UNITS.md раздел 15,
docs/HD_UNITS_REQUIREMENTS_R2.md раздел 3).

Только читает игру и выход tools/unit_census.py. Ничего не рисует, игру не запускает.

    set PYTHONIOENCODING=utf-8
    py -3.13 tools/unit_census.py --verify-hd -1     # сначала перепись (census/units/*.tsv)
    py -3.13 tools/unit_coverage.py                  # census/units/coverage/*
    py -3.13 tools/unit_coverage.py --no-profiles    # без проверки профилей RU/EN и модов игрока

Две НЕЗАВИСИМЫЕ таблицы и их сверка:
  * resources.tsv - всё, что лежит в данных: листы UNITS/*.PCK во всех слоях, каждое объявление
    extraSprites (и перекрытое), каждый файл, общие наборы HANDOB/FLOOROB/BIGOBS и превью брони,
    куклы инвентаря, файлы-сироты рядом с ними. Строится по файлам, без рулсетов брони;
  * references.tsv - всё, на что ссылаются итоговые рулсеты: брони, юниты, бойцы, предметы,
    превращения, условия старта, скрипты. Плюс сплошной обход всех строк всех записей: любая
    строка, равная id брони, юнита, бойца, листа или куклы, обязана попасть в известный класс пути
    (generic_paths.tsv), иначе это «необъяснённая ссылка».
Сверка ставит каждому ресурсу статус: используется / не используется / нет файла / перекрыт.
Ничего не удаляется, только помечается.

Смысл кадров (frame_semantics.tsv) снимается с src/Battlescape/UnitSprite.cpp: таблица routines[],
числа из объявлений внутри drawRoutineN и вызовы selectUnit ищутся регулярными выражениями
по коду; не нашёлся якорь - скрипт останавливается (R-084: из кода, не по памяти).
selectUnit бросает исключение, если кадра index+dir нет (UnitSprite.cpp, до вызова скрипта брони),
поэтому кадр, который движок запросит у надетой брони, а в листе его нет, - падение игры, а не
косметика; такие кадры считаются необъяснёнными.

Правила чтения данных - как у unit_census (импорт): PCK подряд, из TAB только число кадров (R-075),
листы индексами (R-043), рулсеты загрузчиком rul_map (R-046).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rul_map as rm  # noqa: E402
import unit_census as uc  # noqa: E402

ENC = uc.ENC
ROOT = uc.ROOT
OUTC = uc.OUT / "coverage"
US = ROOT / "src" / "Battlescape" / "UnitSprite.cpp"
ARMOR_CPP = ROOT / "src" / "Mod" / "Armor.cpp"
ITEM_SETS = ("HANDOB.PCK", "FLOOROB.PCK", "BIGOBS.PCK", "CustomArmorPreviews")
# CustomArmorPreviews создаётся пустым (Mod.cpp loadVanillaResources), общих кадров 0:
# любой номер получает смещение мода
SHARED_ZERO = {"CustomArmorPreviews"}
IMG_EXT = (".png", ".gif", ".bmp", ".spk")
TONE_MAX = 70.0          # R-054: расхождение тона зеркала, выше - другая вещь
MIRROR_DIR = {0: 6, 1: 5, 2: 4, 3: 3, 4: 2, 5: 1, 6: 0, 7: 7}   # Pathfinding dir_x/dir_y, отражение по горизонтали

_SHA = {}


def fsha(p):
    if p is None:
        return ""
    key = str(p)
    if key not in _SHA:
        try:
            _SHA[key] = hashlib.sha1(Path(p).read_bytes()).hexdigest()[:12]
        except OSError:
            _SHA[key] = "?"
    return _SHA[key]


def git_head():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "?"


def short(lst, n=6):
    lst = list(lst)
    return ",".join(str(x) for x in lst[:n]) + (f" (+{len(lst) - n})" if len(lst) > n else "")


# =================================================================== модель UnitSprite.cpp

class Code:
    def __init__(self, path: Path):
        self.rel = path.relative_to(ROOT).as_posix()
        self.lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        self.func = {}
        starts = []
        for i, l in enumerate(self.lines):
            m = re.match(r"void UnitSprite::drawRoutine(\d+)\(\)", l)
            if m:
                starts.append((i, int(m.group(1))))
        ends = [i for i, l in enumerate(self.lines) if re.match(r"(void|int|bool|\w+) UnitSprite::|UnitSprite::", l)]
        for i, n in starts:
            nxt = min([e for e in ends if e > i] + [len(self.lines)])
            self.func[n] = (i, nxt)
        t = self.find(r"routines\[\]\)\(\)\s*=")
        self.table, self.table_line = [], t + 1
        for l in self.lines[t:t + 40]:
            m = re.search(r"&UnitSprite::drawRoutine(\d+)", l)
            if m:
                self.table.append(int(m.group(1)))
            if "};" in l:
                break

    def find(self, pat, lo=0, hi=None):
        hi = len(self.lines) if hi is None else hi
        for i in range(lo, hi):
            if re.search(pat, self.lines[i]):
                return i
        raise SystemExit(f"{self.rel}: нет якоря /{pat}/ в строках {lo + 1}-{hi} - код изменился, сверить модель")

    def call(self, fn, pat):
        lo, hi = self.func[fn]
        i = self.find(pat, lo, hi)
        return i + 1, re.search(pat, self.lines[i])

    def consts(self, lo, hi):
        out = {}
        for i in range(lo, hi):
            l = self.lines[i].split("//")[0]
            for m in re.finditer(r"((?:\b[A-Za-z_]\w*\s*=\s*)+)(-?\d+)\s*[;,]", l):
                for name in re.findall(r"([A-Za-z_]\w*)\s*=", m.group(1)):
                    out.setdefault(name, []).append((int(m.group(2)), i + 1))
        return out

    def array(self, fn, name):
        lo, hi = self.func[fn]
        i = self.find(rf"{name}\[8\]\s*=\s*\{{", lo, hi)
        vals = re.search(r"\{([^}]*)\}", self.lines[i]).group(1)
        return [int(x) for x in vals.split(",")], i + 1


class Spec:
    """Часть тела в раскладке: подпись, форма номера, база, условие, строки кода."""
    __slots__ = ("label", "form", "base", "cond", "call_line", "base_line", "variant")

    def __init__(self, label, form, base, cond, call_line, base_line, variant=""):
        self.label, self.form, self.base, self.cond = label, form, base, cond
        self.call_line, self.base_line, self.variant = call_line, base_line, variant


def build_model(code: Code):
    """routine -> [Spec]; плюс сведения: какие функции рисуют предметы в руках."""
    M = defaultdict(list)
    info = {"table_line": code.table_line, "routine_func": {}, "items_drawn": {}, "lines": {}}
    for rt, fn in enumerate(code.table):
        info["routine_func"][rt] = fn
    for fn, (lo, hi) in code.func.items():
        try:
            code.find(r"selectItem\(", lo, hi)
            info["items_drawn"][fn] = True
        except SystemExit:
            info["items_drawn"][fn] = False

    def V(c, name, k=0):
        if name not in c:
            raise SystemExit(f"{code.rel}: нет числа {name} - код изменился")
        return c[name][k]

    # ---------------------------------------------------------- drawRoutine0 (0, 10, 13, 14, 15)
    lo, hi = code.func[0]
    c0 = code.consts(lo, hi)
    b_le10 = code.find(r"if \(_drawingRoutine <= 10\)", lo, hi)
    b_13 = code.find(r"else if \(_drawingRoutine == 13\)", b_le10, hi)
    b_h = code.find(r"if \(_helmet\)", b_13, hi)
    b_land = code.find(r"aquanaut land death frame", b_h, hi)
    b_tftd = code.find(r"tftd unit death frame", b_land, hi)
    b_end = code.find(r"legsFloat = \d+;", b_tftd, hi) + 1
    blocks = {"le10": code.consts(b_le10, b_13), "13h": code.consts(b_h, b_land),
              "13l": code.consts(b_land, b_tftd), "tftd": code.consts(b_tftd, b_end)}
    cl = {}
    for key, pat in [("die", r"selectUnit\(coll, die, _unit->getFallingPhase\(\)\)"),
                     ("maleTorso", r"selectUnit\(torso, maleTorso, unitDir\)"),
                     ("femaleTorso", r"selectUnit\(torso, femaleTorso, unitDir\)"),
                     ("legsStand", r"selectUnit\(legs, legsStand, unitDir\)"),
                     ("legsKneel", r"selectUnit\(legs, legsKneel, unitDir\)"),
                     ("legsFloat", r"selectUnit\(legs, legsFloat, unitDir\)"),
                     ("larmStand", r"selectUnit\(leftArm, larmStand, unitDir\)"),
                     ("rarmStand", r"selectUnit\(rightArm, rarmStand, unitDir\)"),
                     ("legsWalk", r"selectUnit\(legs, legsWalk, 24 \* unitDir \+ walkPhase\)"),
                     ("larmWalk", r"selectUnit\(leftArm, larmWalk, 24 \* unitDir \+ walkPhase\)"),
                     ("rarmWalk", r"selectUnit\(rightArm, rarmWalk, 24 \* unitDir \+ walkPhase\)"),
                     ("rarm1H", r"selectUnit\(rightArm, rarm1H, unitDir\)"),
                     ("larm2H", r"selectUnit\(leftArm, larm2H, unitDir\)"),
                     ("rarm2H", r"selectUnit\(rightArm, rarm2H, unitDir\)"),
                     ("rarmShoot", r"selectUnit\(rightArm, rarmShoot, unitDir\)")]:
        cl[key] = code.call(0, pat)[0]
    # мутон: одноручное держит рукой rarm2H (if (_drawingRoutine == 10) selectUnit(rightArm, rarm2H ...))
    r10 = code.find(r"if \(_drawingRoutine == 10\)", code.find(r"// draw arms holding the item", lo, hi), hi)
    code.find(r"selectUnit\(rightArm, rarm2H, unitDir\)", r10, r10 + 2)
    info["lines"]["r10_one_handed"] = r10 + 1
    common = {k: V(c0, k) for k in ("legsStand", "legsKneel", "larmStand", "rarmStand", "legsWalk", "larmWalk", "rarmWalk")}
    for variant, c in blocks.items():
        vv = {k: V(c, k) for k in ("die", "maleTorso", "rarm1H", "larm2H", "rarm2H", "rarmShoot", "legsFloat")}
        if variant == "13h":
            ft = c["femaleTorso"]          # первое - forcedTorso 0 (по полу), второе - иначе
            fbase = {"use_gender": ft[0][0], "other": ft[1][0]}
            fline = ft[0][1]
        else:
            fbase, fline = V(c, "femaleTorso")
        specs = [
            Spec("падение", "fall", vv["die"][0], None, cl["die"], vv["die"][1], variant),
            Spec("торс (муж.)", "dir", vv["maleTorso"][0], "male", cl["maleTorso"], vv["maleTorso"][1], variant),
            Spec("торс (жен.)", "dir", fbase, "female", cl["femaleTorso"], fline, variant),
            Spec("ноги стоя", "dir", common["legsStand"][0], None, cl["legsStand"], common["legsStand"][1], variant),
            Spec("ноги на колене", "dir", common["legsKneel"][0], "kneel", cl["legsKneel"], common["legsKneel"][1], variant),
            Spec("ноги в полёте", "dir", vv["legsFloat"][0], "fly", cl["legsFloat"], vv["legsFloat"][1], variant),
            Spec("левая рука", "dir", common["larmStand"][0], None, cl["larmStand"], common["larmStand"][1], variant),
            Spec("правая рука", "dir", common["rarmStand"][0], None, cl["rarmStand"], common["rarmStand"][1], variant),
            Spec("ноги, шаг", "walk24", common["legsWalk"][0], "walk", cl["legsWalk"], common["legsWalk"][1], variant),
            Spec("левая рука, шаг", "walk24", common["larmWalk"][0], "walk", cl["larmWalk"], common["larmWalk"][1], variant),
            Spec("правая рука, шаг", "walk24", common["rarmWalk"][0], "walk", cl["rarmWalk"], common["rarmWalk"][1], variant),
            Spec("правая рука, одноручное", "dir", vv["rarm1H"][0], "weapon1h", cl["rarm1H"], vv["rarm1H"][1], variant),
            Spec("левая рука, двуручное", "dir", vv["larm2H"][0], "weapon", cl["larm2H"], vv["larm2H"][1], variant),
            Spec("правая рука, двуручное", "dir", vv["rarm2H"][0], "weapon", cl["rarm2H"], vv["rarm2H"][1], variant),
            Spec("правая рука, прицел", "dir", vv["rarmShoot"][0], "weapon", cl["rarmShoot"], vv["rarmShoot"][1], variant),
        ]
        for rt, fn in enumerate(code.table):
            if fn != 0:
                continue
            want = "le10" if rt <= 10 else ("13" if rt == 13 else "tftd")
            if want == variant or (want == "13" and variant in ("13h", "13l")):
                M[rt] += specs

    # ---------------------------------------------------------- drawRoutine1
    lo, hi = code.func[1]
    c = code.consts(lo, hi)
    walk_line, _m = code.call(1, r"selectUnit\(torso, walk, \(5 \* unitDir\) \+ \(walkPhase / 1\.6\)\)")
    r1 = [Spec("падение", "fall", V(c, "die")[0], None, code.call(1, r"selectUnit\(coll, die,")[0], V(c, "die")[1]),
          Spec("торс", "dir", V(c, "stand")[0], None, code.call(1, r"selectUnit\(torso, stand, unitDir\)")[0], V(c, "stand")[1]),
          Spec("торс, полёт (5 фаз)", "walk5", V(c, "walk")[0], "walk", walk_line, V(c, "walk")[1]),
          Spec("левая рука", "dir", V(c, "larm")[0], None, code.call(1, r"selectUnit\(leftArm, larm, unitDir\)")[0], V(c, "larm")[1]),
          Spec("правая рука", "dir", V(c, "rarm")[0], None, code.call(1, r"selectUnit\(rightArm, rarm, unitDir\)")[0], V(c, "rarm")[1])]
    for nm, cond, lab in (("rarm1H", "weapon1h", "правая рука, одноручное"), ("larm2H", "weapon", "левая рука, двуручное"),
                          ("rarm2H", "weapon", "правая рука, двуручное"), ("rarmShoot", "weapon", "правая рука, прицел")):
        arm = "rightArm" if nm.startswith("r") else "leftArm"
        r1.append(Spec(lab, "dir", V(c, nm)[0], cond, code.call(1, rf"selectUnit\({arm}, {nm}, unitDir\)")[0], V(c, nm)[1]))
    for rt, fn in enumerate(code.table):
        if fn == 1:
            M[rt] += r1

    # ---------------------------------------------------------- drawRoutine2
    hv_line = code.call(2, r"hoverTank = .*\? (\d+) : 0")
    hover = int(hv_line[1].group(1))
    hull = code.call(2, r"selectUnit\(s, hoverTank \+ \(_part \* 8\), _unit->getDirection\(\)\)")[0]
    tur = code.call(2, r"selectUnit\(t, (\d+) \+ \(turret \* 8\), _unit->getTurretDirection\(\)\)")
    prop = code.call(2, r"selectUnit\(p, (\d+) \+ \(\(_part-1\) \* 8\), _animationFrame % 8\)")
    r2 = [Spec("корпус", "r2hull", 0, "ground", hull, hv_line[0]),
          Spec("корпус (парящий)", "r2hull", hover, "hover", hull, hv_line[0]),
          Spec("башня", "turret", int(tur[1].group(1)), "turret", tur[0], tur[0]),
          Spec("движитель (парение)", "prop", int(prop[1].group(1)), "hover", prop[0], prop[0])]
    for rt, fn in enumerate(code.table):
        if fn == 2:
            M[rt] += r2

    # ---------------------------------------------------------- drawRoutine3 (3, 22)
    lo, hi = code.func[3]
    body = code.call(3, r"selectUnit\(s, \(_part \* 8\), _unit->getDirection\(\)\)")[0]
    i3 = code.find(r"if \(_drawingRoutine == 3\)", lo, hi)
    i22 = code.find(r"if \(_drawingRoutine == 22\)", lo, hi)
    p3 = code.find(r"selectUnit\(p, (\d+) \+ \(\(_part-1\) \* 8\)", i3, hi)
    p22 = code.find(r"selectUnit\(p, (\d+) \+ \(\(_part-1\) \* 8\)", i22, hi)
    b3 = int(re.search(r"selectUnit\(p, (\d+)", code.lines[p3]).group(1))
    b22 = int(re.search(r"selectUnit\(p, (\d+)", code.lines[p22]).group(1))
    for rt, fn in enumerate(code.table):
        if fn == 3:
            pb, pl, lab = (b22, p22 + 1, "движитель над корпусом") if rt == 22 else (b3, p3 + 1, "движитель под корпусом")
            M[rt] += [Spec("корпус", "part8", 0, None, body, body), Spec(lab, "prop", pb, None, pl, pl)]

    # ---------------------------------------------------------- drawRoutine4 (4, 17, 18)
    lo, hi = code.func[4]
    b17 = code.find(r"if \(_drawingRoutine == 17\)", lo, hi)
    b18 = code.find(r"else if \(_drawingRoutine == 18\)", b17, hi)
    bend = code.find(r"const int unitDir", b18, hi)
    base4, v17, v18 = code.consts(lo, b17), code.consts(b17, b18), code.consts(b18, bend)
    sc, sc_line = code.array(4, "standConvert")
    info["standConvert"] = (sc, sc_line)
    dl = code.call(4, r"selectUnit\(coll, die, _unit->getFallingPhase\(\)\)")[0]
    wl = code.call(4, r"selectUnit\(s, walk, \(8 \* unitDir\) \+ _unit->getWalkingPhase\(\)\)")[0]
    sl = code.call(4, r"selectUnit\(s, stand, unitDir\)")[0]
    scl = code.call(4, r"selectUnit\(s, stand, standConvert\[unitDir\]\)")[0]
    for rt, fn in enumerate(code.table):
        if fn != 4:
            continue
        v = dict((k, base4[k][0]) for k in ("stand", "walk", "die"))
        over = v17 if rt == 17 else (v18 if rt == 18 else {})
        for k in ("stand", "walk", "die"):
            if k in over:
                v[k] = over[k][0]
        M[rt] += [Spec("падение", "fall", v["die"][0], None, dl, v["die"][1]),
                  Spec("стоя" + (" (standConvert)" if rt == 17 else ""), "dir", v["stand"][0], None, scl if rt == 17 else sl, v["stand"][1]),
                  Spec("шаг", "walk8", v["walk"][0], "walk", wl, v["walk"][1])]

    # ---------------------------------------------------------- drawRoutine5
    st5 = code.call(5, r"selectUnit\(s, 0 \+ \(_part \* 8\), _unit->getDirection\(\)\)")[0]
    wk5 = code.call(5, r"selectUnit\(s, (\d+) \+ \(_part \* 4\), \(_unit->getDirection\(\) \* 16\) \+ \(\(_unit->getWalkingPhase\(\) / 2\) % 4\)\)")
    for rt, fn in enumerate(code.table):
        if fn == 5:
            M[rt] += [Spec("корпус стоя", "part8", 0, None, st5, st5),
                      Spec("корпус, шаг (4 фазы)", "r5walk", int(wk5[1].group(1)), "walk", wk5[0], wk5[0])]

    # ---------------------------------------------------------- drawRoutine6
    lo, hi = code.func[6]
    c = code.consts(lo, hi)
    r6 = [Spec("падение", "fall", V(c, "die")[0], None, code.call(6, r"selectUnit\(coll, die,")[0], V(c, "die")[1]),
          Spec("торс", "dir", V(c, "Torso")[0], None, code.call(6, r"selectUnit\(torso, Torso, unitDir\)")[0], V(c, "Torso")[1]),
          Spec("ноги стоя", "dir", V(c, "legsStand")[0], None, code.call(6, r"selectUnit\(legs, legsStand, unitDir\)")[0], V(c, "legsStand")[1]),
          Spec("ноги, шаг", "walk8", V(c, "legsWalk")[0], "walk", code.call(6, r"selectUnit\(legs, legsWalk, 8 \* unitDir \+ walkPhase\)")[0], V(c, "legsWalk")[1]),
          Spec("левая рука", "dir", V(c, "larmStand")[0], None, code.call(6, r"selectUnit\(leftArm, larmStand, unitDir\)")[0], V(c, "larmStand")[1]),
          Spec("правая рука", "dir", V(c, "rarmStand")[0], None, code.call(6, r"selectUnit\(rightArm, rarmStand, unitDir\)")[0], V(c, "rarmStand")[1])]
    for nm, cond, lab in (("rarm1H", "weapon1h", "правая рука, одноручное"), ("larm2H", "weapon", "левая рука, двуручное"),
                          ("rarm2H", "weapon", "правая рука, двуручное"), ("rarmShoot", "weapon", "правая рука, прицел")):
        arm = "rightArm" if nm.startswith("r") else "leftArm"
        r6.append(Spec(lab, "dir", V(c, nm)[0], cond, code.call(6, rf"selectUnit\({arm}, {nm}, unitDir\)")[0], V(c, nm)[1]))
    for rt, fn in enumerate(code.table):
        if fn == 6:
            M[rt] += r6

    # ---------------------------------------------------------- drawRoutine7
    lo, hi = code.func[7]
    c = code.consts(lo, hi)
    r7 = [Spec("падение", "fall", V(c, "die")[0], None, code.call(7, r"selectUnit\(coll, die,")[0], V(c, "die")[1]),
          Spec("торс", "dir", V(c, "Torso")[0], None, code.call(7, r"selectUnit\(torso, Torso, unitDir\)")[0], V(c, "Torso")[1]),
          Spec("ноги стоя", "dir", V(c, "legsStand")[0], None, code.call(7, r"selectUnit\(legs, legsStand, unitDir\)")[0], V(c, "legsStand")[1]),
          Spec("левая рука", "dir", V(c, "larmStand")[0], None, code.call(7, r"selectUnit\(leftArm, larmStand, unitDir\)")[0], V(c, "larmStand")[1]),
          Spec("правая рука", "dir", V(c, "rarmStand")[0], None, code.call(7, r"selectUnit\(rightArm, rarmStand, unitDir\)")[0], V(c, "rarmStand")[1]),
          Spec("ноги, шаг", "walk24", V(c, "legsWalk")[0], "walk", code.call(7, r"selectUnit\(legs, legsWalk, 24 \* unitDir \+ walkPhase\)")[0], V(c, "legsWalk")[1]),
          Spec("левая рука, шаг", "walk24", V(c, "larmWalk")[0], "walk", code.call(7, r"selectUnit\(leftArm, larmWalk, 24 \* unitDir \+ walkPhase\)")[0], V(c, "larmWalk")[1]),
          Spec("правая рука, шаг", "walk24", V(c, "rarmWalk")[0], "walk", code.call(7, r"selectUnit\(rightArm, rarmWalk, 24 \* unitDir \+ walkPhase\)")[0], V(c, "rarmWalk")[1])]
    for rt, fn in enumerate(code.table):
        if fn == 7:
            M[rt] += r7

    # ---------------------------------------------------------- drawRoutine8, 9
    lo, hi = code.func[8]
    c = code.consts(lo, hi)
    pul, pul_line = code.array(8, "Pulsate")
    info["Pulsate"] = (pul, pul_line)
    r8 = [Spec("тело, пульсация", "pulsate", V(c, "Body")[0], None, code.call(8, r"selectUnit\(legs, Body, Pulsate\[_animationFrame % 8\]\)")[0], V(c, "Body")[1]),
          Spec("прицел", "single", V(c, "aim")[0], None, code.call(8, r"selectUnit\(legs, aim, 0\)")[0], V(c, "aim")[1]),
          Spec("падение", "fall", V(c, "die")[0], None, code.call(8, r"selectUnit\(coll, die,")[0], V(c, "die")[1])]
    lo, hi = code.func[9]
    c = code.consts(lo, hi)
    r9 = [Spec("тело, анимация", "anim8", V(c, "Body")[0], None, code.call(9, r"selectUnit\(torso, Body, _animationFrame % 8\)")[0], V(c, "Body")[1]),
          Spec("падение", "fall", V(c, "die")[0], None, code.call(9, r"selectUnit\(coll, die,")[0], V(c, "die")[1])]
    for rt, fn in enumerate(code.table):
        if fn == 8:
            M[rt] += r8
        if fn == 9:
            M[rt] += r9

    # ---------------------------------------------------------- drawRoutine11, 12, 16, 19, 20, 21
    lo, hi = code.func[11]
    bl = code.find(r"body = (\d+);", code.find(r"if \(_unit->getOriginalMovementType\(\) == MT_FLY\)", lo, hi), hi)
    fly11 = int(re.search(r"body = (\d+);", code.lines[bl]).group(1))
    b11 = code.call(11, r"selectUnit\(s, body \+ \(_part \* 4\), 16 \* _unit->getDirection\(\) \+ animFrame\)")[0]
    t11 = code.call(11, r"selectUnit\(t, (\d+) \+ \(turret \* 8\), _unit->getTurretDirection\(\)\)")
    r11 = [Spec("корпус (4 фазы)", "r11", 0, "ground", b11, b11),
           Spec("корпус, парение (4 фазы)", "r11", fly11, "hover", b11, bl + 1),
           Spec("башня", "turret", int(t11[1].group(1)), "turret", t11[0], t11[0])]
    r12 = [Spec("тело, анимация", "part_anim8", 0, None, code.call(12, r"selectUnit\(s, \(_part \* 8\), _animationFrame % 8\)")[0], 0)]
    lo, hi = code.func[16]
    c = code.consts(lo, hi)
    r16 = [Spec("тело, анимация", "anim8", 0, None, code.call(16, r"selectUnit\(s, 0, _animationFrame % 8\)")[0], 0),
           Spec("падение", "fall", V(c, "die")[0], None, code.call(16, r"selectUnit\(coll, die,")[0], V(c, "die")[1])]
    lo, hi = code.func[19]
    c = code.consts(lo, hi)
    r19 = [Spec("стоя", "dir", V(c, "stand")[0], None, code.call(19, r"selectUnit\(s, stand, _unit->getDirection\(\)\)")[0], V(c, "stand")[1]),
           Spec("движение", "dir", V(c, "move")[0], "walk", code.call(19, r"selectUnit\(s, move, _unit->getDirection\(\)\)")[0], V(c, "move")[1]),
           Spec("падение", "fall", V(c, "die")[0], None, code.call(19, r"selectUnit\(coll, die,")[0], V(c, "die")[1])]
    w20 = code.call(20, r"selectUnit\(s, \(_part \* 5\), \(_unit->getWalkingPhase\(\)/2%4\) \+ 5 \* \(4 \* _unit->getDirection\(\)\)\)")[0]
    s20 = code.call(20, r"selectUnit\(s, \(_part \* 5\), 5 \* \(4 \* _unit->getDirection\(\)\)\)")[0]
    r20 = [Spec("тело стоя", "r20stand", 0, None, s20, s20), Spec("тело, шаг (4 фазы)", "r20walk", 0, "walk", w20, w20)]
    w21 = code.call(21, r"selectUnit\(s, \(_part \* 4\), \(_unit->getDirection\(\) \* 16\) \+ \(_animationFrame % 4\)\)")[0]
    r21 = [Spec("тело, анимация (4 фазы)", "r21", 0, None, w21, w21)]
    for rt, fn in enumerate(code.table):
        M[rt] += {11: r11, 12: r12, 16: r16, 19: r19, 20: r20, 21: r21}.get(fn, [])
    info["pulsate"] = sorted(set(pul))
    return M, info


PART_FORMS = {"r2hull", "prop", "part8", "r5walk", "r11", "part_anim8", "r20stand", "r20walk", "r21"}


def expand(sp: Spec, o, info):
    """[(номер, _part, направление, фаза)] для части тела при условиях o."""
    D, P = o["D"], o["parts"]
    b = sp.base
    if isinstance(b, dict):
        b = b["use_gender"] if o.get("forced", 0) == 0 else b["other"]
    f = sp.form
    out = []
    if f == "dir":
        out = [(b + d, 0, d, "") for d in range(8)]
    elif f == "fall":
        out = [(b + k, 0, "", f"падение {k}") for k in range(D)]
    elif f == "walk24":
        out = [(b + 24 * d + p, 0, d, f"шаг {p}") for d in range(8) for p in range(8)]
    elif f == "walk8":
        out = [(b + 8 * d + p, 0, d, f"шаг {p}") for d in range(8) for p in range(8)]
    elif f == "walk5":
        out = sorted({(b + 5 * d + int(p / 1.6), 0, d, f"фаза {int(p / 1.6)}") for d in range(8) for p in range(8)})
    elif f == "anim8":
        out = [(b + a, 0, "", f"кадр {a}") for a in range(8)]
    elif f == "pulsate":
        out = [(b + a, 0, "", f"пульс {a}") for a in info["pulsate"]]
    elif f == "single":
        out = [(b, 0, "", "")]
    elif f == "r2hull":
        out = [(b + part * 8 + d, part, d, "") for part in range(P) for d in range(8)]
    elif f == "turret":
        out = [(b + t * 8 + d, 0, d, f"башня {t}") for t in sorted(o["turrets"]) for d in range(8)]
    elif f == "prop":
        out = [(b + (part - 1) * 8 + a, part, "", f"кадр {a}") for part in range(1, P) for a in range(8)]
    elif f == "part8":
        out = [(part * 8 + d, part, d, "") for part in range(P) for d in range(8)]
    elif f == "r5walk":
        out = [(b + part * 4 + 16 * d + k, part, d, f"шаг {k}") for part in range(P) for d in range(8) for k in range(4)]
    elif f == "r11":
        out = [(b + part * 4 + 16 * d + k, part, d, f"фаза {k}") for part in range(P) for d in range(8) for k in range(4)]
    elif f == "part_anim8":
        out = [(part * 8 + a, part, "", f"кадр {a}") for part in range(P) for a in range(8)]
    elif f == "r20stand":
        out = [(part * 5 + 20 * d, part, d, "") for part in range(P) for d in range(8)]
    elif f == "r20walk":
        out = [(part * 5 + 20 * d + k, part, d, f"шаг {k}") for part in range(P) for d in range(8) for k in range(4)]
    elif f == "r21":
        out = [(part * 4 + 16 * d + k, part, d, f"кадр {k}") for part in range(P) for d in range(8) for k in range(4)]
    else:
        raise SystemExit(f"неизвестная форма {f}")
    return out


def cond_ok(sp: Spec, rt, o):
    c = sp.cond
    v = sp.variant
    if v == "13h" and not o["helmet"]:
        return False
    if c is None:
        return True
    if c in ("male", "female"):
        if rt == 0 or v == "13h":
            branches = ["forced"]
        elif v == "13l":
            branches = ["gender"]
        elif v in ("le10", "tftd"):
            branches = ["gender"] + (["forced"] if o["helmet"] else [])
        else:
            branches = ["gender"]
        fz = o["forced"]
        for br in branches:
            if c == "female" and ((br == "forced" and ((o["can_f"] and fz != 1) or fz == 2)) or (br == "gender" and o["can_f"])):
                return True
            if c == "male" and ((br == "forced" and ((o["can_m"] and fz != 2) or fz == 1)) or (br == "gender" and o["can_m"])):
                return True
        return False
    if c == "weapon1h":
        return o["weapon"] and rt != 10
    if c == "ground":
        return not o["hover"]
    if c == "turret":
        return bool(o["turrets"])
    return bool(o[c])


def layout(model, info, rt, o):
    """{номер: [подпись]} - что движок запросит при условиях o."""
    res = defaultdict(list)
    for sp in model.get(rt, []):
        if not cond_ok(sp, rt, o):
            continue
        for idx, part, d, ph in expand(sp, o, info):
            res[idx].append((sp, part, d, ph))
    return res


def sem_label(entries):
    sp, part, d, ph = entries[0]
    s = sp.label
    if part:
        s += f" [часть {part}]"
    if d != "":
        s += f" напр.{d}"
    if ph:
        s += f" {ph}"
    return s


# =================================================================== сборка набора с учётом источников

class Built:
    def __init__(self, name):
        self.name = name
        self.frames = {}
        self.winner = {}
        self.sources = []        # dict(decl, kind, fname, mid, path, put)
        self.vanilla = 0
        self.shared = 1 << 31


def build_tracked(name, vfs, extras, offsets):
    """Тот же порядок, что uc.build_set (= ExtraSprites::loadSurfaceSet), плюс кто дал кадр."""
    b = Built(name)
    base = vfs.resolve(f"UNITS/{name}")
    if base:
        mid, pck = base
        w, h = (32, 48) if name.upper() == "BIGOBS.PCK" else (32, 40)
        tab = pck.with_suffix(".TAB")
        if not tab.exists():
            t2 = vfs.resolve(f"UNITS/{Path(name).stem}.TAB")
            tab = t2[1] if t2 else None
        frs = uc.read_pck(pck, tab, w, h)
        b.sources.append(dict(decl=None, kind="PCK", fname=f"UNITS/{pck.name}", mid=mid, path=pck, put=len(frs)))
        for i, f in enumerate(frs):
            b.frames[i] = f
            b.winner[i] = 0
        b.vanilla = len(frs)
        if name in uc.SHARED:
            b.shared = len(frs)
    if name in SHARED_ZERO:
        b.shared = 0
    for dno, (rid, rel, line, fields, op) in enumerate(extras.get(name, [])):
        if op == "delete":
            b.frames.clear()
            b.winner.clear()
            b.sources.append(dict(decl=dno, kind="удаление", fname="", mid=uc.mod_of(rel), path=None, put=0))
            continue
        if op == "typeSingle" or fields.get("singleImage"):
            continue
        mid = uc.mod_of(rel)
        moff, _ms = offsets.get(mid, (0, 1000))
        width = int(fields.get("width", 320))
        height = int(fields.get("height", 200))
        subx, suby = int(fields.get("subX", 0) or 0), int(fields.get("subY", 0) or 0)
        sub = subx != 0 and suby != 0
        files = fields.get("files") or {}
        if not isinstance(files, dict):
            b.sources.append(dict(decl=dno, kind="files не словарь", fname=str(files)[:60], mid=mid, path=None, put=0))
            continue

        def put(index, arr, si):
            idx = index + moff if index >= b.shared else index
            b.frames[idx] = arr
            b.winner[idx] = si
            b.sources[si]["put"] += 1

        for start, fname in sorted(files.items(), key=lambda kv: int(kv[0])):
            start, fname = int(start), str(fname)
            if fname.endswith("/"):
                folder = vfs.folder(fname.rstrip("/"))
                names = sorted(folder, key=lambda n: uc.natural_key(folder[n][1].name))
                k = start
                if not names:
                    b.sources.append(dict(decl=dno, kind="нет папки", fname=fname, mid=None, path=None, put=0))
                for n in names:
                    fmid, fp = folder[n]
                    if fp.suffix.lower() not in (".png", ".gif", ".bmp"):
                        b.sources.append(dict(decl=dno, kind="папка: не картинка", fname=fname + fp.name, mid=fmid, path=fp, put=0))
                        continue
                    idx, _pal, err = uc.read_image(fp)
                    if idx is None:
                        b.sources.append(dict(decl=dno, kind=f"не читается: {err}", fname=fname + fp.name, mid=fmid, path=fp, put=0))
                        continue
                    b.sources.append(dict(decl=dno, kind="папка", fname=fname + fp.name, mid=fmid, path=fp, put=0))
                    put(k, idx, len(b.sources) - 1)
                    k += 1
                continue
            hit = vfs.resolve(fname)
            if not hit:
                b.sources.append(dict(decl=dno, kind="нет файла", fname=fname, mid=None, path=None, put=0))
                continue
            fmid, fp = hit
            idx, _pal, err = uc.read_image(fp)
            if idx is None:
                b.sources.append(dict(decl=dno, kind=f"не читается: {err}", fname=fname, mid=fmid, path=fp, put=0))
                continue
            b.sources.append(dict(decl=dno, kind="лист" if sub else "кадр", fname=fname, mid=fmid, path=fp, put=0))
            si = len(b.sources) - 1
            if not sub:
                put(start, idx, si)
                continue
            canvas = np.zeros((height, width), np.uint8)
            hh, ww = min(height, idx.shape[0]), min(width, idx.shape[1])
            canvas[:hh, :ww] = idx[:hh, :ww]
            k = start
            for y in range(height // suby):
                for x in range(width // subx):
                    put(k, canvas[y * suby:(y + 1) * suby, x * subx:(x + 1) * subx].copy(), si)
                    k += 1
    return b


def shadows(vfs: uc.VFS, rel, eff_path):
    """Копии того же пути в других слоях данных (перекрыты верхним)."""
    out = []
    for mid, root in vfs.roots:
        p = vfs._walk(root, rel)
        if p is not None and p.exists() and (eff_path is None or Path(p) != Path(eff_path)):
            out.append((mid, p))
    return out


def lum(pal):
    return (0.299 * pal[:, 0] + 0.587 * pal[:, 1] + 0.114 * pal[:, 2]).astype(np.float32)


# =================================================================== классы путей сплошного обхода

COINCIDE = "совпадение id (не графика)"
PATHS = [
    # --- то, что ставит юнита или броню в бой и рисует лист / куклу
    (r"armors\.spriteSheet", "sheet", "лист брони", None),
    (r"armors\.spriteInv", "doll", "кукла брони", None),
    (r"armors\.(layersDefaultPrefix|layersSpecificPrefix.*)", "doll", "префикс слоёв куклы", None),
    (r"units\.armor", "armors", "броня юнита", None),
    (r"soldiers\.armor", "armors", "броня бойца по умолчанию", None),
    (r"soldiers\.armorForAvatar", "armors", "броня аватара (только кукла)", None),
    (r"armors\.units\[\]", "soldiers", "типы бойцов, которым броня разрешена", None),
    (r"enviroEffects\.armorTransformations\{\}\.?", "armors", "смена брони средой боя", None),
    (r"(events|manufacture)\.spawnedSoldier\.armor", "armors", "броня выданного бойца", None),
    (r"(events|manufacture)\.spawnedPersonType", "soldiers", "тип выданного бойца", None),
    (r"soldierTransformation\.producedSoldierArmor", "armors", "броня после превращения бойца", None),
    (r"soldierTransformation\.(producedSoldierType|allowedSoldierTypes\[\])", "soldiers", "тип бойца в превращении", None),
    (r"startingConditions\.defaultArmor\{\}(\.\{\})?", "*", "броня по условиям старта", None),
    (r"startingConditions\.(allowedArmors|forbiddenArmors|allowedSoldierTypes|forbiddenSoldierTypes|allowedVehicles)\[\]", "*",
     "разрешение/запрет условиями старта", None),
    (r"alienRaces\.(members\[\]|membersRandom\[\]\[\])", "units", "состав расы", None),
    (r"alienDeployments\.(reinforcements\[\]\.)?data\[\]\.customUnitType", "units", "юнит развёртывания", None),
    (r"alienDeployments\.civiliansByType\{\}", "units", "гражданские развёртывания", None),
    (r"terrains\.civilianTypes\[\]", "units", "гражданские террейна", None),
    (r"items\.(spawnUnit|zombieUnit|zombieUnitByArmorMale\{\}\.?|zombieUnitByArmorFemale\{\}\.?|zombieUnitByType\{\}\.?)", "*",
     "призыв/превращение предметом", None),
    (r"units\.spawnUnit", "units", "превращение юнита при смерти", None),
    # --- строка равна id брони/юнита, но поле - id другого раздела (исследование, предмет, раса...)
    (r"research\.(dependencies|getOneFree|unlocks|disables|requires|lookup|getOneFreeProtected\{\}(\.\[\])?|"
     r"getOneFree\[\]|dependencies\[\]|unlocks\[\]|requires\[\]|disables\[\]|reenables\[\]|reenables)", "*", COINCIDE, {"research"}),
    (r"research\.spawnedItem", "*", COINCIDE, {"items"}),
    (r"manufacture\.(requires\[\])", "*", COINCIDE, {"research"}),
    (r"manufacture\.(requiredItems\{\}|producedItems\{\}|randomProducedItems\[\]\[\]\{\})", "*", COINCIDE, {"items", "crafts"}),
    (r"events\.researchList\[\]", "*", COINCIDE, {"research"}),
    (r"events\.(everyItemList\[\]|randomItemList\[\]|everyMultiItemList\{\}|randomMultiItemList\[\]\{\})", "*", COINCIDE, {"items"}),
    (r"(eventScripts|missionScripts)\.itemTriggers\{\}", "*", COINCIDE, {"items"}),
    (r"(eventScripts|missionScripts)\.researchTriggers\{\}", "*", COINCIDE, {"research"}),
    (r"facilities\.buildCostItems\{\}", "*", COINCIDE, {"items"}),
    (r"items\.requiresBuy\[\]", "*", COINCIDE, {"research"}),
    (r"items\.ufopediaType", "*", COINCIDE, {"ufopaedia"}),
    (r"ufopaedia\.requires\[\]", "*", COINCIDE, {"research"}),
    (r"alienDeployments\.unlockedResearch", "*", COINCIDE, {"research"}),
    (r"alienDeployments\.missionBountyItem", "*", COINCIDE, {"items"}),
    (r"alienMissions\.raceWeights\{\}\.\{\}", "*", COINCIDE, {"alienRaces"}),
    (r"units\.race", "*", "строка расы юнита (подпись, Unit.cpp tryRead race)", {"STR"}),
    (r"units\.liveAlien", "*", COINCIDE, {"items"}),
    (r"units\.civilianRecoveryType", "*", COINCIDE, {"soldiers", "items"}),
    (r"armors\.corpseGeo", "*", COINCIDE, {"items"}),
    (r"armors\.requires", "*", COINCIDE, {"research"}),
    (r"(terrains\.mapBlocks|ufos\.battlescapeTerrainData\.mapBlocks)\[\]\.(items\{\}|randomizedItems\[\]\.itemList\[\])", "*", COINCIDE, {"items"}),
    (r"soldierTransformation\.requiredItems\{\}", "*", COINCIDE, {"items"}),
    (r"soldiers\.rankStrings\[\]", "*", "строка перевода звания", {"STR"}),
    # --- имя поверхности совпало с именем листа/куклы: картинки интерфейса и педии
    (r"ufopaedia(\{\}\.|\.image_id|\.background)", "*", "картинка педии", {"SURF"}),
    (r"(alienDeployments(\.reinforcements\[\])?\.briefing\.background|alienDeployments\.alertBackground|events\.background|"
     r"interfaces\.backgroundImage|items\.medikitBackground|ufos\.modSprite)", "*", "картинка интерфейса", {"SURF"}),
]
PATHS_RX = [(re.compile(p + r"$"), k, cls, exp) for p, k, cls, exp in PATHS]


def classify_path(path):
    for rx, _k, cls, exp in PATHS_RX:
        if rx.match(path):
            return cls, exp
    return None, None


# =================================================================== одна игра

def run_game(gname, g, model, info, code, acc, fsum):
    t0 = time.time()
    print(f"== {gname}: рулсеты", flush=True)
    st, ops = uc.load_rules(g["chain"], ROOT / "src")
    offsets = uc.mod_offsets(g["chain"])
    vfs = uc.VFS(g["data"])
    battle_pal = uc.load_battle_palette(*g["battle_pal"])
    blum = lum(battle_pal)
    hdx = uc.HdIndex(g["hd"])
    mod_dir = dict(g["chain"])
    layer_dir = dict(g["data"])
    head = acc["head"]

    def rule_path(rel):
        mid, p = rel.split("|", 1)
        return mod_dir[mid] / p

    def rloc(rel, line):
        if not rel:
            return "", ""
        return f"{rel}:{line}", fsha(rule_path(rel))

    def disp(p):
        if p is None:
            return ""
        try:
            return Path(p).relative_to(ROOT).as_posix()
        except ValueError:
            return str(p)

    def sec(s):
        return {rid: rec for (ss, rid), rec in st.rules.items() if ss == s}

    armors, units, soldiers, items = sec("armors"), sec("units"), sec("soldiers"), sec("items")
    research, races = sec("research"), sec("alienRaces")
    ids_of = defaultdict(set)
    for (s, rid) in st.rules:
        ids_of[rid].add(s)

    def setby(s, rid, field):
        rec = st.rules.get((s, rid))
        if not rec or field not in rec["setby"]:
            return "", 0
        return rec["setby"][field]

    # ---------------- extraSprites
    extras = defaultdict(list)
    single_decls = defaultdict(list)       # имя -> [(rel, line, файл, op)]
    for rid, rel, line, fields in st.lists.get("extraSprites", []):
        op = ops.get((rel, line), "type")
        extras[rid].append((rid, rel, line, fields, op))
        if op == "typeSingle" or fields.get("singleImage"):
            f = fields.get("fileSingle")
            if not f:
                fl = fields.get("files") or {}
                f = next(iter(fl.values()), "") if isinstance(fl, dict) and fl else ""
            single_decls[rid].append((rel, line, str(f), op))
        elif op == "delete":
            single_decls[rid].append((rel, line, "", op))

    # ---------------- кто носит броню
    sold_ff = {sid: int(rec["fields"].get("femaleFrequency", 50) if rec["fields"].get("femaleFrequency") is not None else 50)
               for sid, rec in soldiers.items()}
    wear_units = defaultdict(set)
    wear_sold = defaultdict(set)
    wear_how = defaultdict(set)
    for uid, rec in units.items():
        a = rec["fields"].get("armor")
        if a:
            wear_units[a].add(uid)
            wear_how[a].add("units.armor")
    for sid, rec in soldiers.items():
        a = rec["fields"].get("armor")
        if a:
            wear_sold[a].add(sid)
            wear_how[a].add("soldiers.armor")
    for aid, rec in armors.items():
        f = rec["fields"]
        if f.get("storeItem"):
            lst = [x for x in uc.as_list(f.get("units")) if x in soldiers] or list(soldiers)
            wear_sold[aid] |= set(lst)
            wear_how[aid].add("склад (storeItem)" + (", units[]" if f.get("units") else ", все типы"))
    for (s, rid), rec in st.rules.items():
        f = rec["fields"]
        if s == "startingConditions":
            da = f.get("defaultArmor") or {}
            if isinstance(da, dict):
                for stype, arms in da.items():
                    for a in (arms or {}):
                        wear_sold[a].add(stype)
                        wear_how[a].add("startingConditions.defaultArmor")
        if s == "soldierTransformation" and f.get("producedSoldierArmor"):
            a = f["producedSoldierArmor"]
            types = [f["producedSoldierType"]] if f.get("producedSoldierType") else (uc.as_list(f.get("allowedSoldierTypes")) or list(soldiers))
            wear_sold[a] |= set(t for t in types if t in soldiers)
            wear_how[a].add("soldierTransformation")
        if s in ("events", "manufacture") and isinstance(f.get("spawnedSoldier"), dict) and f["spawnedSoldier"].get("armor"):
            a = f["spawnedSoldier"]["armor"]
            t = f.get("spawnedPersonType")
            if t in soldiers:
                wear_sold[a].add(t)
            wear_how[a].add(f"{s}.spawnedSoldier")
    enviro = []                            # (среда, из, в, rel, line)
    for (s, rid), rec in st.rules.items():
        if s == "enviroEffects":
            at = rec["fields"].get("armorTransformations") or {}
            if isinstance(at, dict):
                rel, line = rec["setby"].get("armorTransformations", ("", 0))
                for a, b in at.items():
                    enviro.append((rid, a, b, rel, line))
    for _ in range(4):                     # носитель цели - носитель источника
        for _e, a, b, _r, _l in enviro:
            if a in armors and b in armors:
                wear_units[b] |= wear_units[a]
                wear_sold[b] |= wear_sold[a]
                if wear_units[a] or wear_sold[a]:
                    wear_how[b].add(f"enviro из {a}")

    # ---------------- башни: предметы с turretType, связанные с бронёй
    def unit_items(uid):
        f = units[uid]["fields"]
        out = set()
        for key in ("builtInWeaponSets", "builtInWeapons"):
            for _p, s in rm.walk_strings(f.get(key), key):
                if s in items:
                    out.add(s)
                elif ("weaponSets", s) in st.rules:
                    for _p2, s2 in rm.walk_strings(st.rules[("weaponSets", s)]["fields"], "w"):
                        if s2 in items:
                            out.add(s2)
        if f.get("livingWeapon") and f.get("race"):
            lw = str(f["race"])[4:] + "_WEAPON"
            if lw in items:
                out.add(lw)
        if uid in items and items[uid]["fields"].get("fixedWeapon"):
            out.add(uid)                  # техника: предмет с id юнита (RuleItem: fixedWeapon -> vehicleUnit)
        return out

    def armor_items(aid):
        out = set()
        for _p, s in rm.walk_strings(armors[aid]["fields"].get("builtInWeapons"), "b"):
            if s in items:
                out.add(s)
        sw = armors[aid]["fields"].get("specialWeapon")
        if sw in items:
            out.add(sw)
        for u in wear_units.get(aid, ()):
            out |= unit_items(u)
        return out

    def turret_of(it):
        v = items[it]["fields"].get("turretType")
        return int(v) if v is not None and int(v) >= 0 else None

    depth_possible = False
    for (s, rid), rec in st.rules.items():
        if s in ("alienDeployments", "ufos", "terrains", "missionScripts"):
            dv = rec["fields"].get("depth")
            if dv is not None:
                vals = [int(x) for x in uc.as_list(dv) if isinstance(x, (int, float))]
                if vals and max(vals) > 0:
                    depth_possible = True

    # ---------------- скрипты, меняющие кадр (текстом по файлам рулсетов цепочки)
    script_rows = []
    sprite_hooks = ("selectUnitSprite", "selectItemSprite", "recolorUnitSprite", "recolorItemSprite")
    for mid, d in g["chain"]:
        rdir = d / "Ruleset" if (d / "Ruleset").is_dir() else d
        for p in rm.rul_files(rdir):
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            cur_type, cur_sec = "", ""
            for i, l in enumerate(lines):
                m = re.match(r"^(\w+):", l)
                if m:
                    cur_sec = m.group(1)
                m = re.match(r"^\s*-\s*(type|name|delete|new|override|update):\s*(\S+)", l)
                if m:
                    cur_type = m.group(2)
                m = re.match(r"^(\s*)(" + "|".join(sprite_hooks) + r")\s*:", l)
                if m:
                    rel = f"{mid}|{p.relative_to(d).as_posix()}"
                    owner = cur_type if cur_sec in ("armors", "items") else ""
                    script_rows.append([gname, m.group(2), cur_sec, owner, f"{rel}:{i + 1}", fsha(p),
                                        "в записи" if owner else "глобальный (extended.scripts)"])
    scripted_armor = defaultdict(list)
    for r in script_rows:
        if r[1] == "selectUnitSprite" and r[2] == "armors" and r[3]:
            scripted_armor[r[3]].append(r[4])

    # ---------------- листы юнитов: имена
    sheet_users = defaultdict(list)
    for aid, rec in armors.items():
        s = rec["fields"].get("spriteSheet")
        if s:
            sheet_users[s].append(aid)
    names = set(sheet_users)
    nonpck_32x40 = set()
    for name, lst in extras.items():
        if name in uc.NOT_UNIT_SETS or name in names:
            continue
        for _r, _rel, _l, fields, op in lst:
            if op != "typeSingle" and not fields.get("singleImage") and \
                    int(fields.get("subX", 0) or 0) == 32 and int(fields.get("subY", 0) or 0) == 40:
                if name.upper().endswith(".PCK"):
                    names.add(name)
                else:
                    nonpck_32x40.add(name)
                break
    for n in vfs.folder("UNITS"):
        if n.endswith(".PCK") and n not in uc.SHARED:
            names.add(n)
    terrain_sets = set()
    for (s, rid), rec in st.rules.items():
        if s == "terrains":
            for x in uc.as_list(rec["fields"].get("mapDataSets")):
                terrain_sets.add(f"{x}.PCK".upper())

    # ---------------- раскладки брони
    def opts_for(aid, broad=False):
        f = armors[aid]["fields"]
        rt = int(f.get("drawingRoutine", 0) or 0)
        size = int(f.get("size", 1) or 1)
        su = wear_sold.get(aid, set())
        uu = wear_units.get(aid, set())
        can_f = any(sold_ff.get(s, 50) > 0 for s in su)
        can_m = bool(uu) or any(sold_ff.get(s, 50) < 100 for s in su)
        ak = f.get("allowsKneeling")
        kneel = (bool(su) and ak is not False) or ak is True
        fly = int(f.get("movementType", 0) or 0) == 1
        turrets = set()
        for it in armor_items(aid):
            t = turret_of(it)
            if t is not None:
                turrets.add(t)
        o = dict(D=int(f.get("deathFrames", 3) if f.get("deathFrames") is not None else 3),
                 parts=size * size, forced=int(f.get("forcedTorso", 0) or 0), can_f=can_f, can_m=can_m,
                 kneel=kneel, fly=fly, hover=fly, walk=f.get("allowsMoving") is not False, weapon=True,
                 helmet=depth_possible, turrets=turrets)
        if broad:
            o.update(can_f=True, can_m=True, kneel=True, fly=True, walk=True, weapon=True, helmet=True)
            o["broad_hover"] = True
        return rt, o

    def broad_layout(aid):
        rt, o = opts_for(aid, broad=True)
        res = layout(model, info, rt, o)
        if rt in (2, 11):          # парение и земля - оба варианта корпуса
            o2 = dict(o)
            o2["hover"] = not o["hover"]
            for k, v in layout(model, info, rt, o2).items():
                res[k] += v
        return rt, res

    # ---------------- кадры: сборка, отпечатки, сверка с переписью, зеркала
    print(f"   листов юнитов: {len(names)} (+ {len(nonpck_32x40)} 32x40 без .PCK); наборы предметов {len(ITEM_SETS)}", flush=True)
    res_rows, sheet_info = [], {}
    frame_owner = defaultdict(list)       # exact -> [(лист, номер)]
    mask_owner = defaultdict(list)
    mirror_rows, mirror_stats = [], []
    selfcheck = Counter()
    sem_of = {}                            # (лист, номер) -> смысл
    for name in sorted(names) + list(ITEM_SETS):
        b = build_tracked(name, vfs, extras, offsets)
        is_unit = name not in ITEM_SETS
        fps = {}
        for i, arr in b.frames.items():
            fp = uc.fingerprint(arr)
            if fp:
                fps[i] = fp
        users = sheet_users.get(name, [])
        lay = defaultdict(list)
        for a in users:
            _rt, bl = broad_layout(a)
            for k, v in bl.items():
                lay[k] += v
        if is_unit:
            for i, fp in fps.items():
                key = (gname, name, i)
                if key in fsum:
                    selfcheck["совпало" if fsum[key] == fp[0] else "РАЗНОЕ"] += 1
                else:
                    selfcheck["нет в переписи"] += 1
            for i, fp in fps.items():
                frame_owner[fp[0]].append((name, i))
                mask_owner[fp[1]].append((name, i))
                if i in lay:
                    sem_of[(name, i)] = sem_label(lay[i])
        # зеркала внутри листа: силуэт кадра i, отражённый, равен силуэту кадра j
        if is_unit and fps:
            by_mask = defaultdict(list)
            for i, fp in fps.items():
                by_mask[fp[1]].append(i)
            pairs = 0
            tone_ok = 0
            dir_pairs = Counter()
            sym = 0
            for i, fp in fps.items():
                if fp[3] == fp[1]:
                    sym += 1      # силуэт симметричен сам себе: зеркало силуэтом не доказуемо
                    continue
                for j in by_mask.get(fp[3], ()):
                    if j <= i:
                        continue
                    a = b.frames[i][:, ::-1]
                    c = b.frames[j]
                    if a.shape != c.shape:
                        continue
                    m = a != 0
                    tone = float(np.abs(blum[a[m]] - blum[c[m]]).mean()) if m.any() else 0.0
                    pairs += 1
                    ok = tone <= TONE_MAX
                    tone_ok += ok
                    si, sj = lay.get(i), lay.get(j)
                    dp = ""
                    if si and sj:
                        e1, e2 = si[0], sj[0]
                        if e1[0] is e2[0] and e1[1] == e2[1] and e1[3] == e2[3] and e1[2] != "" and e2[2] != "":
                            dp = f"{e1[2]}<->{e2[2]}"
                            dir_pairs[dp] += 1
                    mirror_rows.append([gname, name, i, j, f"{tone:.1f}", "да" if ok else "нет (другая вещь?)",
                                        sem_of.get((name, i), ""), sem_of.get((name, j), ""), dp])
            if pairs or sym:
                mirror_stats.append((name, pairs, tone_ok, dir_pairs, sym))
        # строки ресурсов
        decls = extras.get(name, [])
        wins = Counter(b.winner.values())
        in_lay = Counter(b.winner[i] for i in b.winner if i in lay)
        used_set = bool(users) if is_unit else None
        for si, s in enumerate(b.sources):
            d = decls[s["decl"]] if s["decl"] is not None else None
            dloc, dsha = rloc(d[1], d[2]) if d else ("", "")
            kind = s["kind"]
            if kind in ("нет файла", "нет папки"):
                status = "нет файла"
            elif kind.startswith("не читается") or kind in ("files не словарь", "папка: не картинка"):
                status = "не читается / не картинка"
            elif kind == "удаление":
                status = "удаление набора"
            elif s["put"] and not wins.get(si):
                status = "перекрыт кадрами (позднее объявление)"
            elif is_unit and not used_set:
                status = ("террейн, не юнит" if name.upper() in terrain_sets else "не используется (лист без брони)")
            else:
                status = "используется"
            res_rows.append([gname, "лист юнита" if is_unit else "общий набор", name, kind, d[4] if d else "",
                             dloc, dsha, s["mid"] or "", s["fname"], disp(s["path"]), fsha(s["path"]),
                             s["put"], wins.get(si, 0), in_lay.get(si, 0) if is_unit else "", status])
            if s["path"] is not None and kind in ("PCK", "лист", "кадр", "папка"):
                for smid, sp in shadows(vfs, s["fname"], s["path"]):
                    res_rows.append([gname, "лист юнита" if is_unit else "общий набор", name, kind + " (нижний слой)",
                                     d[4] if d else "", dloc, dsha, smid, s["fname"], disp(sp), fsha(sp), 0, 0, "",
                                     f"перекрыт файлом слоя {s['mid']}"])
        alloc = set(b.frames)
        sheet_info[name] = dict(alloc=alloc, nonempty=set(fps), users=users, lay=set(lay), fps=fps,
                                sources=[(s["mid"], s["fname"], fsha(s["path"])) for s in b.sources if s["path"] is not None],
                                content=hashlib.sha1("|".join(f"{i}:{fps[i][0] if i in fps else '0'}" for i in sorted(alloc)).encode()).hexdigest()[:12],
                                vanilla=b.vanilla, shared=b.shared, winner=b.winner, sources_raw=b.sources)
        if not is_unit:
            sheet_info[name]["frames"] = b.frames
    print(f"   кадры: {time.time() - t0:.1f} с; сверка с переписью: {dict(selfcheck)}", flush=True)

    # ---------------- куклы: ресурсы
    surf = {}                                  # имя -> (мод, файл) действующее
    for n, lst in single_decls.items():
        last = lst[-1]
        if last[3] == "delete":
            continue
        surf[n] = (uc.mod_of(last[0]), last[2])
    for n, (mid, p) in vfs.folder("UFOGRAPH").items():
        if n.endswith(".SPK"):
            surf.setdefault(n, (mid, f"UFOGRAPH/{p.name}"))
    surf_ci = {n.upper(): n for n in surf}
    by_base = defaultdict(list)
    for n in surf:
        m = re.match(r"^(.*?)([MF]\d+)?\.SPK$", n, re.I)
        if m:
            by_base[m.group(1).upper()].append(n)

    def find_surf(n):
        if n in surf:
            return n
        return surf_ci.get(n.upper())

    doll_refs = defaultdict(set)               # имя поверхности -> {броня}
    armor_doll = {}
    ref_rows = []

    def add_ref(src_sec, src_id, field, value, kind, target, status, note=""):
        rel, line = setby(src_sec, src_id, field.split(".")[0].split("[")[0]) if src_sec not in ("-",) else ("", 0)
        loc, sha = rloc(rel, line)
        ref_rows.append([gname, src_sec, src_id, field, uc.cell(value), kind, uc.cell(target), status,
                         uc.mod_of(rel), loc, sha, note])

    layer_names = {}
    for aid, rec in sorted(armors.items()):
        f = rec["fields"]
        got, missing = [], []
        p = f.get("spriteInv")
        if p:
            cands = [p, p + ".SPK", p + "M0.SPK"] + by_base.get(p.upper(), [])
            for n in cands:
                fn = find_surf(n)
                if fn and fn not in got:
                    got.append(fn)
                    doll_refs[fn].add(aid)
            add_ref("armors", aid, "spriteInv", p, "кукла", ";".join(got[:6]) + (f" (+{len(got) - 6})" if len(got) > 6 else ""),
                    "есть" if got else "НЕТ ПОВЕРХНОСТИ")
        ld = f.get("layersDefinition") or {}
        if isinstance(ld, dict) and ld:
            pre = f.get("layersDefaultPrefix", "")
            spec = f.get("layersSpecificPrefix") or {}
            for _ver, ll in ld.items():
                for li, item in enumerate(uc.as_list(ll)):
                    if not item:
                        continue
                    pfx = spec.get(li, spec.get(str(li), pre)) if isinstance(spec, dict) else pre
                    n = f"{pfx}__{li}__{item}"
                    fn = find_surf(n)
                    layer_names[n] = fn
                    if fn:
                        doll_refs[fn].add(aid)
                        got.append(fn)
                    else:
                        missing.append(n)
            add_ref("armors", aid, "layersDefinition", f"{len(ld)} верс.", "слои куклы",
                    f"есть {len(set(got))}" + (f"; нет {len(missing)}: {short(missing, 3)}" if missing else ""),
                    "есть" if not missing else "НЕТ ПОВЕРХНОСТИ СЛОЯ")
        armor_doll[aid] = (got, missing)

    # ресурсы кукол: объявления typeSingle (и перекрытые) + UFOGRAPH/*.SPK всех слоёв
    doll_pat = re.compile(r"([MF]\d+\.SPK$)|(__\d+__)", re.I)
    inv_bases = {str(r["fields"].get("spriteInv")).upper() for r in armors.values() if r["fields"].get("spriteInv")}
    lay_prefix = set()
    for r in armors.values():
        if r["fields"].get("layersDefaultPrefix"):
            lay_prefix.add(str(r["fields"]["layersDefaultPrefix"]).upper())

    def doll_like(n):
        u = n.upper()
        if doll_pat.search(n) or n in doll_refs:
            return True
        base = re.sub(r"([MF]\d+)?\.SPK$", "", u)
        return base in inv_bases or any(u.startswith(px + "__") for px in lay_prefix)

    doll_res = 0
    for n, lst in sorted(single_decls.items()):
        if not doll_like(n):
            continue
        for k, (rel, line, fname, op) in enumerate(lst):
            loc, sha = rloc(rel, line)
            hit = vfs.resolve(fname) if fname else None
            last = k == len(lst) - 1
            if op == "delete":
                status = "удаление поверхности"
            elif not hit:
                status = "нет файла"
            elif not last:
                status = "перекрыт объявлением"
            elif n in doll_refs:
                status = "используется"
            else:
                status = "не используется (нет брони с этой куклой)"
            res_rows.append([gname, "кукла", n, "поверхность", op, loc, sha, hit[0] if hit else "", fname,
                             disp(hit[1]) if hit else "", fsha(hit[1]) if hit else "", 1 if hit else 0,
                             1 if (hit and last) else 0, "", status])
            doll_res += 1
            if hit:
                for smid, sp in shadows(vfs, fname, hit[1]):
                    res_rows.append([gname, "кукла", n, "поверхность (нижний слой)", op, loc, sha, smid, fname, disp(sp),
                                     fsha(sp), 0, 0, "", f"перекрыт файлом слоя {hit[0]}"])
    for mid, root in vfs.roots:
        u = vfs._walk(root, "UFOGRAPH")
        if u is None or not u.is_dir():
            continue
        for fnm in sorted(os.listdir(u)):
            n = fnm.upper()
            if not n.endswith(".SPK") or not doll_like(n):
                continue
            eff = surf.get(n)
            top = vfs.resolve(f"UFOGRAPH/{fnm}")
            is_top = top and Path(top[1]) == u / fnm
            if n in single_decls:
                status = "перекрыт объявлением extraSprites"
            elif not is_top:
                status = f"перекрыт файлом слоя {top[0] if top else '?'}"
            elif n in doll_refs:
                status = "используется"
            else:
                status = "не используется (нет брони с этой куклой)"
            res_rows.append([gname, "кукла", n, "UFOGRAPH SPK", "", "", "", mid, f"UFOGRAPH/{fnm}", disp(u / fnm),
                             fsha(u / fnm), 1, 1 if is_top else 0, "", status])
            doll_res += 1
            _ = eff

    # ---------------- файлы-сироты рядом с ресурсами юнитов
    declared = set()
    for rid, lst in extras.items():
        for _r, rel, _l, fields, op in lst:
            fl = fields.get("files") or {}
            vals = list(fl.values()) if isinstance(fl, dict) else []
            if fields.get("fileSingle"):
                vals.append(fields["fileSingle"])
            for fname in vals:
                fname = str(fname)
                if fname.endswith("/"):
                    for mid, root in vfs.roots:
                        p = vfs._walk(root, fname.rstrip("/"))
                        if p is not None and p.is_dir():
                            for x in os.listdir(p):
                                declared.add(str(p / x).lower())
                else:
                    for mid, root in vfs.roots:
                        p = vfs._walk(root, fname)
                        if p is not None:
                            declared.add(str(p).lower())
    unit_dirs = set()
    for r in res_rows:
        if r[1] in ("лист юнита", "общий набор", "кукла") and r[9]:
            unit_dirs.add((ROOT / r[9]).parent)
    orphans = 0
    for d in sorted(unit_dirs):
        # UNITS и UFOGRAPH движок читает папкой целиком (Mod::loadVanillaResources), объявления им не нужны;
        # SPK кукол из UFOGRAPH уже в таблице строкой «UFOGRAPH SPK»
        if d.name.upper() in ("UNITS", "UFOGRAPH") or not d.is_dir():
            continue
        for x in sorted(os.listdir(d)):
            p = d / x
            if p.is_file() and p.suffix.lower() in IMG_EXT and str(p).lower() not in declared:
                res_rows.append([gname, "сирота", "", "файл без объявления", "", "", "", "", x, disp(p), fsha(p),
                                 0, 0, "", "не используется (ни одного объявления extraSprites)"])
                orphans += 1
    # UNITS: PCK без TAB и TAB без PCK во всех слоях
    for mid, root in vfs.roots:
        u = vfs._walk(root, "UNITS")
        if u is None or not u.is_dir():
            continue
        lst = {x.upper(): x for x in os.listdir(u)}
        for up, x in sorted(lst.items()):
            stem, ext = os.path.splitext(up)
            if ext == ".TAB" and stem + ".PCK" not in lst:
                res_rows.append([gname, "сирота", stem + ".PCK", "TAB без PCK", "", "", "", mid, f"UNITS/{x}",
                                 disp(u / x), fsha(u / x), 0, 0, "", "не используется (нет PCK)"])
                orphans += 1
            elif ext not in (".PCK", ".TAB"):
                res_rows.append([gname, "сирота", "", "чужой файл в UNITS", "", "", "", mid, f"UNITS/{x}",
                                 disp(u / x), fsha(u / x), 0, 0, "", "не используется (движок читает только PCK/TAB)"])
                orphans += 1

    # ---------------- ссылки из рулсетов (явные поля)
    hand_use = defaultdict(set)
    floor_use = defaultdict(set)
    big_use = defaultdict(set)
    prev_use = defaultdict(set)

    def engine_index(src_sec, rid, field, setname, raw):
        """Номер кадра так, как его даст Mod::loadOffsetNode."""
        if raw is None:
            return None
        b = sheet_info[setname]
        rel, _l = setby(src_sec, rid, field)
        mid = uc.mod_of(rel)
        v = raw
        if isinstance(raw, dict):
            v = raw.get("index")
            m = raw.get("mod")
            if m == "master":
                mid = g["chain"][0][0]
            elif m and m != "current":
                mid = m
        try:
            v = int(v)
        except (TypeError, ValueError):
            return None
        if v < 0:
            return None
        moff = offsets.get(mid, (0, 0))[0]
        return v + moff if v >= b["shared"] else v

    for iid, rec in sorted(items.items()):
        f = rec["fields"]
        hs = f.get("handSprite", 120)
        hi = engine_index("items", iid, "handSprite", "HANDOB.PCK", hs) if "handSprite" in f else 120
        if hi is not None:
            for d in range(8):
                hand_use[hi + d].add(iid)
        for field, setname, use in (("floorSprite", "FLOOROB.PCK", floor_use), ("bigSprite", "BIGOBS.PCK", big_use)):
            if field in f:
                ix = engine_index("items", iid, field, setname, f[field])
                if ix is not None:
                    use[ix].add(iid)
    for aid, rec in armors.items():
        for raw in uc.as_list(rec["fields"].get("customArmorPreviewIndex")):
            ix = engine_index("armors", aid, "customArmorPreviewIndex", "CustomArmorPreviews", raw)
            if ix is not None:
                prev_use[ix].add(aid)

    corpse_items = set()
    for aid, rec in sorted(armors.items()):
        f = rec["fields"]
        s = f.get("spriteSheet")
        if s:
            si = sheet_info.get(s)
            add_ref("armors", aid, "spriteSheet", s, "лист", s,
                    "есть" if si and si["alloc"] else "НЕТ ЛИСТА")
        for c in uc.as_list(f.get("corpseBattle")):
            corpse_items.add(c)
            add_ref("armors", aid, "corpseBattle", c, "труп (бой)", c, "есть" if c in items else "НЕТ ПРЕДМЕТА")
        if f.get("corpseGeo"):
            corpse_items.add(f["corpseGeo"])
            add_ref("armors", aid, "corpseGeo", f["corpseGeo"], "труп (склад)", f["corpseGeo"],
                    "есть" if f["corpseGeo"] in items else "НЕТ ПРЕДМЕТА")
        for _p, it in rm.walk_strings(f.get("builtInWeapons"), "b"):
            add_ref("armors", aid, "builtInWeapons", it, "встроенное оружие", it, "есть" if it in items else "НЕТ ПРЕДМЕТА")
        if f.get("specialWeapon"):
            add_ref("armors", aid, "specialWeapon", f["specialWeapon"], "особое оружие", f["specialWeapon"],
                    "есть" if f["specialWeapon"] in items else "НЕТ ПРЕДМЕТА")
        for raw in uc.as_list(f.get("customArmorPreviewIndex")):
            ix = engine_index("armors", aid, "customArmorPreviewIndex", "CustomArmorPreviews", raw)
            ok = ix is not None and ix in sheet_info["CustomArmorPreviews"]["alloc"]
            add_ref("armors", aid, "customArmorPreviewIndex", raw, "превью брони", ix, "есть" if ok else "НЕТ КАДРА")
        for st_ in uc.as_list(f.get("units")):
            add_ref("armors", aid, "units", st_, "тип бойца", st_, "есть" if st_ in soldiers else "НЕТ ТИПА БОЙЦА")
    for uid, rec in sorted(units.items()):
        f = rec["fields"]
        a = f.get("armor")
        add_ref("units", uid, "armor", a, "броня", a, "есть" if a in armors else "НЕТ БРОНИ")
        if f.get("spawnUnit"):
            add_ref("units", uid, "spawnUnit", f["spawnUnit"], "превращение при смерти", f["spawnUnit"],
                    "есть" if f["spawnUnit"] in units else "НЕТ ЮНИТА")
        if f.get("livingWeapon"):
            lw = str(f.get("race", ""))[4:] + "_WEAPON"
            add_ref("units", uid, "livingWeapon", True, "живое оружие (race[4:]+_WEAPON)", lw,
                    "есть" if lw in items else "НЕТ ПРЕДМЕТА (оружие не выдаётся)")
        for it in sorted(unit_items(uid) - ({uid} if uid in items else set())):
            add_ref("units", uid, "builtInWeaponSets", it, "встроенное оружие", it, "есть")
        if f.get("specab") not in (None, 0):
            add_ref("units", uid, "specab", f.get("specab"), "особая способность", f.get("specab"), "есть")
    for sid, rec in sorted(soldiers.items()):
        f = rec["fields"]
        for field in ("armor", "armorForAvatar"):
            if f.get(field):
                add_ref("soldiers", sid, field, f[field], "броня", f[field], "есть" if f[field] in armors else "НЕТ БРОНИ")
    for iid, rec in sorted(items.items()):
        f = rec["fields"]
        if f.get("fixedWeapon") and iid in units:
            add_ref("items", iid, "fixedWeapon", True, "техника (юнит с id предмета)", iid, "есть")
        for field in ("spawnUnit", "zombieUnit"):
            if f.get(field):
                add_ref("items", iid, field, f[field], "призыв/превращение", f[field], "есть" if f[field] in units else "НЕТ ЮНИТА")
        for field in ("zombieUnitByArmorMale", "zombieUnitByArmorFemale", "zombieUnitByType"):
            dv = f.get(field)
            if isinstance(dv, dict):
                for k, v in dv.items():
                    okk = (k in armors) if "Armor" in field else (k in units)
                    add_ref("items", iid, field, f"{k}->{v}", "превращение", v,
                            "есть" if (v in units and okk) else "НЕТ ЮНИТА/БРОНИ")
        if "handSprite" in f or iid in corpse_items:
            hs = f.get("handSprite", 120)
            hi = engine_index("items", iid, "handSprite", "HANDOB.PCK", hs) if "handSprite" in f else 120
            if hi is not None:
                miss = [hi + d for d in range(8) if hi + d not in sheet_info["HANDOB.PCK"]["alloc"]]
                add_ref("items", iid, "handSprite", hs, "кадры HANDOB x8", hi,
                        "есть" if not miss else f"НЕТ КАДРОВ {short(miss, 3)}")
        if iid in corpse_items:
            for field, setname in (("floorSprite", "FLOOROB.PCK"), ("bigSprite", "BIGOBS.PCK")):
                ix = engine_index("items", iid, field, setname, f.get(field)) if field in f else None
                ok = ix is not None and ix in sheet_info[setname]["alloc"]
                add_ref("items", iid, field, f.get(field, ""), f"труп: {setname}", ix,
                        "есть" if ok else ("не задан" if field not in f else "НЕТ КАДРА"))
    for env, a, b2, rel, line in enviro:
        loc, sha = rloc(rel, line)
        ref_rows.append([gname, "enviroEffects", env, "armorTransformations", f"{a}->{b2}", "смена брони", b2,
                         "есть" if (a in armors and b2 in armors) else "НЕТ БРОНИ", uc.mod_of(rel), loc, sha, ""])

    # ---------------- сплошной обход: любая строка = id брони/юнита/бойца/листа/куклы
    unit_sheet_names = set(names)
    doll_names = set(doll_refs) | {n for n in surf if doll_like(n)}
    gen_paths = Counter()
    gen_ex = {}
    gen_bad = []
    for (s, rid), rec in st.rules.items():
        for path, val in rm.walk_strings(rec["fields"], s):
            kinds = [k for k in ("armors", "units", "soldiers") if k in ids_of.get(val, ())]
            if val in unit_sheet_names:
                kinds.append("sheet")
            if val in doll_names:
                kinds.append("doll")
            if not kinds:
                continue
            cls, exp = classify_path(path)
            if cls is None:
                verdict = "НЕ КЛАССИФИЦИРОВАН"
            elif exp is None:
                verdict = "ок"
            elif exp == {"STR"}:
                verdict = "ок" if val.startswith("STR_") else "НЕ СОВПАЛО"
            elif exp == {"SURF"}:
                verdict = "ок" if find_surf(val) or val in unit_sheet_names else "НЕ СОВПАЛО"
            else:
                verdict = "ок" if (ids_of.get(val, set()) & exp) else "НЕ СОВПАЛО (id только юнита/брони)"
            key = (path, "+".join(kinds), cls or "", verdict)
            gen_paths[key] += 1
            gen_ex.setdefault(key, f"{s}:{rid} -> {val}")
            if verdict != "ок":
                gen_bad.append((path, s, rid, val, verdict))
    gen_rows = [[gname, p, k, c, v, n, gen_ex[(p, k, c, v)]] for (p, k, c, v), n in sorted(gen_paths.items())]

    # ---------------- манифест брони
    hd_sheet = {}
    for r in acc["census_sheets"]:
        if r.get("game") == gname:
            hd_sheet[r["sheet"]] = r
    ent_rows, missing_rows = [], []
    sheet_required = defaultdict(set)
    for aid, rec in sorted(armors.items()):
        f = rec["fields"]
        s = f.get("spriteSheet", "")
        rt, o = opts_for(aid)
        worn = bool(wear_units.get(aid) or wear_sold.get(aid))
        req = layout(model, info, rt, o) if s else {}
        si = sheet_info.get(s) if s else None
        miss = sorted(k for k in req if si is None or k not in si["alloc"]) if worn and s else []
        if worn and s:
            sheet_required[s] |= set(req)
        if miss:
            for k in miss:
                missing_rows.append([gname, aid, s, rt, k, sem_label(req[k]), short(sorted(wear_units.get(aid, ())), 3),
                                     short(sorted(wear_sold.get(aid, ())), 3), ";".join(scripted_armor.get(aid, []))])
        rel, line = setby("armors", aid, "spriteSheet")
        loc, sha = rloc(rel, line)
        defs = st.defs.get(("armors", aid), [])
        first = f"{defs[0][0]}:{defs[0][1]}" if defs else ""
        hd = hdx.find(s) if s else []
        hd_idx = set()
        for _m, inf in hd:
            hd_idx |= inf["idx"]
        need_ne = (set(req) & si["nonempty"]) if si else set()
        hrow = hd_sheet.get(s, {})
        got, dmiss = armor_doll.get(aid, ([], []))
        ent_rows.append([
            gname, aid, head[:12], first, uc.mod_of(rel), loc, sha, s, rt, uc.ROUTINES.get(rt, "?"),
            int(f.get("size", 1) or 1), uc.MOVEMENT.get(int(f.get("movementType", 0) or 0), f.get("movementType")),
            o["D"], o["forced"], short(sorted(wear_units.get(aid, ())), 4), short(sorted(wear_sold.get(aid, ())), 4),
            ";".join(sorted(wear_how.get(aid, ()))), "да" if o["can_m"] else "", "да" if o["can_f"] else "",
            "да" if o["kneel"] else "", ",".join(map(str, sorted(o["turrets"]))),
            len(req), len(miss), short(miss, 8),
            ";".join(scripted_armor.get(aid, [])),
            short(sorted(armor_items(aid)), 4), uc.jcell(f.get("corpseBattle")), f.get("corpseGeo", ""),
            f.get("spriteInv", ""), short(got, 3), len(dmiss),
            si["content"] if si else "", short([f"{m}:{n}@{h}" for m, n, h in si["sources"]], 3) if si else "",
            ";".join(m for m, _i in hd), max((inf["count"] for _m, inf in hd), default=0),
            len(need_ne - hd_idx) if hd else "", hrow.get("hd_stale", ""), hrow.get("hd_check", ""),
            "да" if worn else "НЕТ (не носится)",
        ])

    # ---------------- покрытие кадров листа
    cov_rows = []
    for name in sorted(names):
        si = sheet_info[name]
        alloc, ne, lay = si["alloc"], si["nonempty"], si["lay"]
        users = si["users"]
        scripted = [a for a in users if scripted_armor.get(a)]
        outside = sorted(alloc - lay) if users else sorted(alloc)
        outside_ne = [i for i in outside if i in ne]
        req = sheet_required.get(name, set())
        cov_rows.append([gname, name, len(users), short(users, 4), len(alloc), len(ne), len(lay & alloc), len(req),
                         len(req - alloc), len(outside), len(outside_ne), short(outside_ne, 8),
                         ("скрипт selectUnitSprite: " + short(scripted, 3)) if (scripted and outside_ne) else
                         ("не используется движком" if outside_ne else ""), si["content"]])

    # ---------------- общие листы и общие кадры
    shared_sheet_rows = []
    for name in sorted(names):
        users = sheet_info[name]["users"]
        if len(users) >= 2:
            rts = sorted({int(armors[a]["fields"].get("drawingRoutine", 0) or 0) for a in users})
            sz = sorted({int(armors[a]["fields"].get("size", 1) or 1) for a in users})
            shared_sheet_rows.append([gname, name, len(users), short(sorted(users), 8), ",".join(map(str, rts)),
                                      ",".join(map(str, sz)), "РАЗНЫЕ routine" if len(rts) > 1 else ""])
    sf_rows = []
    diff_sem = 0
    for h, occ in frame_owner.items():
        sheets_ = sorted({n for n, _i in occ})
        if len(sheets_) < 2:
            continue
        sems = {sem_of.get(o_) for o_ in occ if sem_of.get(o_)}
        bare = {re.sub(r" напр\.\d.*$", "", x) for x in sems}
        dsem = len(bare) > 1
        diff_sem += dsem
        sf_rows.append([gname, h, len(sheets_), len(occ), short(sheets_, 6), short([f"{n}#{i}" for n, i in occ[:6]], 6),
                        short(sorted(sems), 3), "разный смысл" if dsem else ""])
    item_shared = []
    for setname, use in (("HANDOB.PCK", hand_use), ("FLOOROB.PCK", floor_use), ("BIGOBS.PCK", big_use),
                         ("CustomArmorPreviews", prev_use)):
        for ix, us in sorted(use.items()):
            if len(us) >= 2:
                item_shared.append([gname, setname, ix, len(us), short(sorted(us), 6),
                                    "есть" if ix in sheet_info[setname]["alloc"] else "НЕТ КАДРА"])
    # общие наборы: использование кадров
    for setname, use in (("HANDOB.PCK", hand_use), ("FLOOROB.PCK", floor_use), ("BIGOBS.PCK", big_use),
                         ("CustomArmorPreviews", prev_use)):
        si = sheet_info[setname]
        used_src = Counter(si["winner"][i] for i in use if i in si["winner"])
        si["used_frames"] = len(set(use) & si["alloc"])
        si["missing_frames"] = sorted(set(use) - si["alloc"])
        si["unused_frames"] = len(si["alloc"] - set(use))
        si["used_src"] = used_src
    # пометка ресурсов общих наборов: ни один кадр источника не нужен предметам
    for r in res_rows:
        if r[0] == gname and r[1] == "общий набор" and r[14] == "используется":
            si = sheet_info[r[2]]
            srcs = si["sources_raw"]
            idx = next((k for k, s in enumerate(srcs) if s["fname"] == r[8] and (s["mid"] or "") == r[7]), None)
            if idx is not None and not si["used_src"].get(idx):
                r[14] = "не используется (ни один кадр не нужен предметам)"

    # ---------------- семейства со сдвигом номера (одна картинка под разными номерами в разных листах)
    cross = Counter()
    cross_ex = {}
    for h, occ in frame_owner.items():
        if len(occ) < 2 or len(occ) > 40:
            continue
        for x in range(len(occ)):
            for y in range(x + 1, len(occ)):
                (a, i), (b2, j) = occ[x], occ[y]
                if a == b2 or i == j:
                    continue
                key = (a, b2, j - i) if a < b2 else (b2, a, i - j)
                cross[key] += 1
                cross_ex.setdefault(key, f"{a}#{i}={b2}#{j}")
    cross_rows = [[gname, a, b2, d, n, cross_ex[(a, b2, d)]] for (a, b2, d), n in cross.most_common() if n >= 8]

    # ---------------- видимость и маскировка (поля Armor::load, взяты из кода)
    vis_fields = acc["vis_fields"]
    vis_rows = []
    for aid, rec in sorted(armors.items()):
        for fld in vis_fields:
            if fld in rec["fields"]:
                rel, line = rec["setby"].get(fld, ("", 0))
                loc, sha = rloc(rel, line)
                vis_rows.append([gname, aid, fld, uc.cell(rec["fields"][fld]), rec["fields"].get("spriteSheet", ""),
                                 "да" if (wear_units.get(aid) or wear_sold.get(aid)) else "нет", uc.mod_of(rel), loc])

    # ---------------- превращения и призывы
    tr_rows = []

    def armor_sheet(a):
        return armors.get(a, {}).get("fields", {}).get("spriteSheet", "")

    def unit_sheet(u):
        return armor_sheet(units.get(u, {}).get("fields", {}).get("armor", ""))

    for env, a, b2, rel, line in enviro:
        loc, _sh = rloc(rel, line)
        tr_rows.append([gname, "броня меняется средой", f"enviroEffects:{env}", a, b2, armor_sheet(b2),
                        "есть" if sheet_info.get(armor_sheet(b2), {}).get("alloc") else "НЕТ ЛИСТА", loc])
    for iid, rec in sorted(items.items()):
        f = rec["fields"]
        for field in ("spawnUnit", "zombieUnit"):
            if f.get(field):
                rel, line = rec["setby"].get(field, ("", 0))
                fac = f.get("spawnUnitFaction" if field == "spawnUnit" else "zombieUnitFaction", "")
                tr_rows.append([gname, f"предмет: {field}" + (f" (фракция {fac})" if fac != "" else ""), f"items:{iid}", "",
                                f[field], unit_sheet(f[field]), "есть" if sheet_info.get(unit_sheet(f[field]), {}).get("alloc") else "НЕТ ЛИСТА",
                                rloc(rel, line)[0]])
        for field in ("zombieUnitByArmorMale", "zombieUnitByArmorFemale", "zombieUnitByType"):
            dv = f.get(field)
            if isinstance(dv, dict):
                rel, line = rec["setby"].get(field, ("", 0))
                for k, v in dv.items():
                    tr_rows.append([gname, f"предмет: {field}", f"items:{iid}", k, v, unit_sheet(v),
                                    "есть" if sheet_info.get(unit_sheet(v), {}).get("alloc") else "НЕТ ЛИСТА", rloc(rel, line)[0]])
    for uid, rec in sorted(units.items()):
        f = rec["fields"]
        if f.get("spawnUnit"):
            rel, line = rec["setby"].get("spawnUnit", ("", 0))
            tr_rows.append([gname, "юнит при смерти/оглушении (spawnUnit)", f"units:{uid}", "", f["spawnUnit"], unit_sheet(f["spawnUnit"]),
                            "есть" if sheet_info.get(unit_sheet(f["spawnUnit"]), {}).get("alloc") else "НЕТ ЛИСТА", rloc(rel, line)[0]])
        if f.get("specab") not in (None, 0):
            rel, line = rec["setby"].get("specab", ("", 0))
            tr_rows.append([gname, f"specab {f.get('specab')}", f"units:{uid}", "", "", unit_sheet(uid), "", rloc(rel, line)[0]])
    for (s, rid), rec in sorted(st.rules.items()):
        f = rec["fields"]
        if s == "soldierTransformation" and f.get("producedSoldierArmor"):
            rel, line = rec["setby"].get("producedSoldierArmor", ("", 0))
            a = f["producedSoldierArmor"]
            tr_rows.append([gname, "превращение бойца", f"soldierTransformation:{rid}", "", a, armor_sheet(a),
                            "есть" if sheet_info.get(armor_sheet(a), {}).get("alloc") else "НЕТ ЛИСТА", rloc(rel, line)[0]])

    # ---------------- категории R2
    def ex(lst, n=5):
        return short(sorted(lst), n)

    rt_of = {a: int(r["fields"].get("drawingRoutine", 0) or 0) for a, r in armors.items()}
    size_of = {a: int(r["fields"].get("size", 1) or 1) for a, r in armors.items()}
    worn = {a for a in armors if wear_units.get(a) or wear_sold.get(a)}
    enemies, civs, allies = set(), set(), set()
    for (s, rid), rec in st.rules.items():
        for path, val in rm.walk_strings(rec["fields"], s):
            if val not in units:
                continue
            cls, _e = classify_path(path)
            if cls in ("состав расы", "юнит развёртывания"):
                enemies.add(val)
            elif cls in ("гражданские развёртывания", "гражданские террейна"):
                civs.add(val)
    for iid, rec in items.items():
        f = rec["fields"]
        if f.get("spawnUnit") in units and int(f.get("spawnUnitFaction", -1) if f.get("spawnUnitFaction") is not None else -1) == 0:
            allies.add(f["spawnUnit"])
        if f.get("fixedWeapon") and iid in units:
            allies.add(iid)
    humanoid_rt = {0, 1, 4, 6, 10, 13, 14, 15, 17, 18}
    machine_rt = {2, 3, 5, 11, 22}
    scripted = sorted(scripted_armor)
    pck_ufo = sorted(n for n in names if sheet_info[n]["sources"] and sheet_info[n]["sources"][0][0] == "UFO"
                     and sheet_info[n]["users"])
    tftd_layer = [m for m, _p in g["data"] if m == "TFTD"]
    tftd_dir = uc.PZ / "TFTD"
    tftd_files = sorted(os.listdir(tftd_dir)) if gname == "piratez" and tftd_dir.is_dir() else []
    load_res = {mid: uc.read_meta(d).get("loadResources", "") for mid, d in g["chain"]}
    states_D = Counter(int(r["fields"].get("deathFrames", 3) if r["fields"].get("deathFrames") is not None else 3) for r in armors.values())
    cat_rows = [
        ["бойцы (типы)", len(soldiers), ex(soldiers), "раздел soldiers итоговых рулсетов"],
        ["брони, которые носят бойцы", sum(1 for a in armors if wear_sold.get(a)), ex([a for a in armors if wear_sold.get(a)]),
         "soldiers.armor, storeItem+units[], defaultArmor, превращения, spawnedSoldier, enviro"],
        ["враги (юниты рас и развёртываний)", len(enemies), ex(enemies), "alienRaces.members/membersRandom, alienDeployments data[].customUnitType"],
        ["гражданские/нейтралы", len(civs), ex(civs), "terrains.civilianTypes, alienDeployments.civiliansByType"],
        ["союзники (техника и призыв за игрока)", len(allies), ex(allies), "items fixedWeapon с юнитом того же id; items.spawnUnit c spawnUnitFaction 0"],
        ["не гуманоиды (routine вне 0,1,4,6,10,13-15,17,18)", sum(1 for a in worn if rt_of[a] not in humanoid_rt),
         ex([a for a in worn if rt_of[a] not in humanoid_rt]), "drawingRoutine надетых броней"],
        ["машины (routine 2,3,5,11,22)", sum(1 for a in worn if rt_of[a] in machine_rt), ex([a for a in worn if rt_of[a] in machine_rt]),
         "drawingRoutine надетых броней"],
        ["большие 2x2 (size 2)", sum(1 for a in worn if size_of[a] >= 2), ex([a for a in worn if size_of[a] >= 2]), "armors.size"],
        ["состояния: брони с падением не из 3 кадров", sum(n for d, n in states_D.items() if d != 3),
         ", ".join(f"deathFrames {d}: {n}" for d, n in sorted(states_D.items())), "armors.deathFrames; шаг/колено/полёт/прицел - раскладка frame_semantics"],
        ["тела (предметы-трупы)", len(corpse_items), ex(corpse_items), "armors.corpseBattle/corpseGeo -> FLOOROB/BIGOBS"],
        ["снаряжение (кадры HANDOB, нужные предметам)", len(set(hand_use) & sheet_info["HANDOB.PCK"]["alloc"]),
         f"предметов с handSprite: {sum(1 for r in items.values() if 'handSprite' in r['fields'])}", "items.handSprite (+8 направлений), по умолчанию 120"],
        ["сопутствующий арт: куклы", len(doll_refs), ex(doll_refs), "spriteInv (+.SPK, M0.SPK, <M|F><n>.SPK), слои layersDefinition"],
        ["сопутствующий арт: превью брони (броней)", len({a for v in prev_use.values() for a in v}),
         f"кадров {len(set(prev_use) & sheet_info['CustomArmorPreviews']['alloc'])}: " + ex(sorted({a for v in prev_use.values() for a in v})),
         "armors.customArmorPreviewIndex -> CustomArmorPreviews"],
        ["сопутствующий арт: аватары", sum(1 for r in soldiers.values() if r["fields"].get("armorForAvatar")),
         ex([s for s, r in soldiers.items() if r["fields"].get("armorForAvatar")]), "soldiers.armorForAvatar"],
        ["заёмные листы UFO (PCK из слоя UFO)", len(pck_ufo), ex(pck_ufo), "источник PCK листа - слой данных UFO"],
        ["заёмные листы TFTD", 0 if not tftd_layer else -1,
         f"слоя TFTD в данных нет; loadResources цепочки: {load_res}; папка TFTD установки: {tftd_files or 'нет'}",
         "слои данных игры (games()) и metadata.yml loadResources"],
        ["замены скриптом (selectUnitSprite в броне)", len(scripted), ex(scripted, 11), "текст рулсетов: selectUnitSprite под armors"],
        ["глобальные скрипты спрайтов", sum(1 for r in script_rows if not r[3]),
         short([f"{r[1]}@{r[4]}" for r in script_rows if not r[3]], 6), "extended.scripts: select/recolor Unit/Item Sprite"],
    ]
    cat_rows = [[gname] + r for r in cat_rows]

    # ---------------- исключения
    exc = []
    for aid, rec in sorted(armors.items()):
        f = rec["fields"]
        w = bool(wear_units.get(aid) or wear_sold.get(aid))
        if not f.get("spriteSheet"):
            exc.append([gname, "броня без spriteSheet", aid, "лист не задан - броня не рисуется в бою",
                        "да" if not w else "НЕТ: броню носят " + short(sorted(wear_units.get(aid, set()) | wear_sold.get(aid, set())), 4)])
        elif not w:
            exc.append([gname, "броня не носится", aid, "ни юнит, ни боец, ни превращение не надевают её", "да"])
    for r in missing_rows:
        exc.append([gname, "нет кадра, который запросит движок", f"{r[1]}#{r[4]}",
                    f"{r[2]} routine {r[3]}: {r[5]} (selectUnit бросит исключение)", "НЕТ"])
    for name in sorted(names):
        if not sheet_info[name]["users"]:
            exc.append([gname, "лист без брони", name, "ни одна броня не ссылается - не рисуется", "да"])
    for r in ref_rows:
        if str(r[7]).startswith("не задан"):
            exc.append([gname, f"труп: {r[3]} не задан", f"{r[1]}:{r[2]}",
                        f"{r[5]}: номер -1, движок не рисует (BattleItem::getFloorSprite / ItemSprite::draw: if (sprite))", "да"])
        elif r[7] != "есть":
            explained = "да" if (r[3] in ("spriteInv", "layersDefinition") and not wear_sold.get(r[2])) else "НЕТ"
            why = f"{r[4]} -> {r[7]}"
            if r[3] == "livingWeapon":
                explained = "да"
                why += " (SavedBattleGame.cpp: if (ruleItem) - нет предмета, нет оружия, кадров не нужно)"
            exc.append([gname, f"ссылка: {r[3]}", f"{r[1]}:{r[2]}", why, explained])
    for path, s, rid, val, verdict in gen_bad:
        exc.append([gname, "сплошной обход", f"{s}:{rid}", f"{path} = {val}: {verdict}", "НЕТ"])
    for setname in ITEM_SETS:
        for ix in sheet_info[setname]["missing_frames"]:
            users_ = {"HANDOB.PCK": hand_use, "FLOOROB.PCK": floor_use, "BIGOBS.PCK": big_use, "CustomArmorPreviews": prev_use}[setname][ix]
            corpse = bool(users_ & corpse_items)
            exc.append([gname, f"нет кадра {setname}", f"{setname}#{ix}", f"нужен {short(sorted(users_), 3)}",
                        "НЕТ" if (corpse or setname == "CustomArmorPreviews") else "да (ветка предметов, не юнитов)"])
    if selfcheck.get("РАЗНОЕ") or selfcheck.get("нет в переписи"):
        exc.append([gname, "сверка с переписью", "frames_summary.tsv", f"{dict(selfcheck)}", "НЕТ"])

    # ---------------- итоги игры
    unexplained = [r for r in exc if r[4].startswith("НЕТ")]
    st_res = Counter(r[14] for r in res_rows if r[0] == gname)
    st_ref = Counter(r[7] if r[7] in ("есть",) else "нет цели" for r in ref_rows)
    mirror_dirs = Counter()
    for _n, _p, _t, dp, _s in mirror_stats:
        mirror_dirs.update(dp)
    canon = sum(v for k, v in mirror_dirs.items() if MIRROR_DIR[int(k.split("<->")[0])] == int(k.split("<->")[1]))
    derivable = len({(r[1], r[3]) for r in mirror_rows if r[0] == gname and r[5] == "да"})
    summ = dict(
        engine_commit=head, rules_records=len(st.rules), seconds=0,
        p1_resources=dict(rows=sum(1 for r in res_rows if r[0] == gname), by_status=dict(st_res.most_common()),
                          unit_sheets=len(names), non_unit_32x40_sets_excluded=sorted(nonpck_32x40), orphans=orphans, doll_resources=doll_res),
        p1_references=dict(rows=len(ref_rows), by_status=dict(st_ref.most_common()),
                           generic_paths=len(gen_rows), generic_unclassified=sum(1 for p in gen_bad if p[4] == "НЕ КЛАССИФИЦИРОВАН"),
                           generic_mismatch=sum(1 for p in gen_bad if p[4] != "НЕ КЛАССИФИЦИРОВАН")),
        p2_manifest=dict(armors=len(ent_rows), worn=sum(1 for r in ent_rows if r[-1] == "да"),
                         routines_in_use=sorted({r[8] for r in ent_rows}),
                         missing_required_frames=len(missing_rows),
                         armors_with_missing=len({r[1] for r in missing_rows}),
                         selfcheck=dict(selfcheck)),
        p3_shared=dict(sheets_with_2plus_armors=len(shared_sheet_rows),
                       shared_sheets_mixed_routine=sum(1 for r in shared_sheet_rows if r[6]),
                       frames_in_2plus_sheets=len(sf_rows), frames_shared_different_meaning=diff_sem,
                       item_frames_2plus_items=len(item_shared)),
        p4_mirrors=dict(sheets_with_pairs=len(mirror_stats), pairs=sum(p for _n, p, _t, _d, _s in mirror_stats),
                        tone_ok=sum(t for _n, _p, t, _d, _s in mirror_stats),
                        self_symmetric_frames=sum(x for _n, _p, _t, _d, x in mirror_stats),
                        frames_derivable_by_mirror=derivable, direction_pairs_canonical=canon,
                        direction_pairs_total=sum(mirror_dirs.values()), direction_pairs=dict(mirror_dirs.most_common(12)),
                        cross_index_families=len(cross_rows)),
        p6=dict(visibility_rows=len(vis_rows), visibility_armors=len({r[1] for r in vis_rows}),
                transforms=len(tr_rows), scripts=len(script_rows), scripted_armors=len(scripted), depth_missions=depth_possible),
        p7=dict(exceptions=len(exc), unexplained=len(unexplained),
                unexplained_by_kind=dict(Counter(r[1] for r in unexplained).most_common())),
    )
    summ["seconds"] = round(time.time() - t0, 1)
    acc["summary"][gname] = summ
    for k, rows in (("resources", res_rows), ("references", ref_rows), ("generic", gen_rows), ("entities", ent_rows),
                    ("missing", missing_rows), ("coverage", cov_rows), ("shared_sheets", shared_sheet_rows),
                    ("shared_frames", sf_rows), ("item_shared", item_shared), ("mirror_pairs", mirror_rows),
                    ("cross", cross_rows), ("visibility", vis_rows), ("transforms", tr_rows), ("scripts", script_rows),
                    ("categories", cat_rows), ("exceptions", exc)):
        acc[k] += rows
    for n, p, t, d, sy in mirror_stats:
        acc["mirror_sheets"].append([gname, n, p, t, sy,", ".join(f"{k}:{v}" for k, v in d.most_common(6))])
    acc["rules"][gname] = st
    if gname == "piratez":
        acc["unit_sheet_names"] = sorted(names)
    print(f"   готово за {summ['seconds']} с; необъяснённых {len(unexplained)}", flush=True)


# =================================================================== профили RU/EN и моды игрока

GRAPH_FIELDS = {
    "armors": ("spriteSheet", "spriteInv", "drawingRoutine", "size", "corpseBattle", "corpseGeo", "layersDefaultPrefix",
               "layersDefinition", "movementType", "deathFrames", "forcedTorso", "customArmorPreviewIndex", "scripts"),
    "units": ("armor", "spawnUnit", "livingWeapon"),
    "soldiers": ("armor", "armorForAvatar", "femaleFrequency"),
    "items": ("handSprite", "floorSprite", "bigSprite", "spawnUnit", "zombieUnit"),
}


def graph_snapshot(st, ops):
    snap = {}
    for (s, rid), rec in st.rules.items():
        if s in GRAPH_FIELDS:
            for f in GRAPH_FIELDS[s]:
                if f in rec["fields"]:
                    snap[(s, rid, f)] = json.dumps(rec["fields"][f], ensure_ascii=False, sort_keys=True, default=str)
    for rid, rel, line, fields in st.lists.get("extraSprites", []):
        key = ("extraSprites", rid, f"{uc.mod_of(rel)}:{ops.get((rel, line), 'type')}")
        snap[key] = snap.get(key, "") + json.dumps(fields.get("files") or fields.get("fileSingle"), ensure_ascii=False,
                                                    sort_keys=True, default=str)
    return snap


def item_check(chain, st, ops):
    """Кадры HANDOB (x8), FLOOROB, BIGOBS всех предметов и превью брони в данном наборе модов:
    (список отсутствующих, сколько проверено). Номер - как Mod::loadOffsetNode, набор - как loadSurfaceSet."""
    data = [("common", uc.PZ / "common"), ("UFO", uc.PZ / "UFO")] + list(chain)
    vfs = uc.VFS(data)
    offsets = uc.mod_offsets(chain)
    extras = defaultdict(list)
    for rid, rel, line, fields in st.lists.get("extraSprites", []):
        if rid in ITEM_SETS:
            extras[rid].append((rid, rel, line, fields, ops.get((rel, line), "type")))
    sets = {n: build_tracked(n, vfs, extras, offsets) for n in ITEM_SETS}
    master = chain[0][0]

    def index(rec, field, setname, raw):
        rel = rec["setby"].get(field, ("", 0))[0]
        mid = uc.mod_of(rel)
        v = raw
        if isinstance(raw, dict):
            v = raw.get("index")
            m = raw.get("mod")
            mid = master if m == "master" else (m if m and m != "current" else mid)
        try:
            v = int(v)
        except (TypeError, ValueError):
            return None
        if v < 0:
            return None
        return v + offsets.get(mid, (0, 0))[0] if v >= sets[setname].shared else v

    miss, n = [], 0
    for (s, rid), rec in st.rules.items():
        f = rec["fields"]
        if s == "items":
            for field, setname, k in (("handSprite", "HANDOB.PCK", 8), ("floorSprite", "FLOOROB.PCK", 1),
                                      ("bigSprite", "BIGOBS.PCK", 1)):
                if field not in f:
                    continue
                ix = index(rec, field, setname, f[field])
                if ix is None:
                    continue
                for d in range(k):
                    n += 1
                    if ix + d not in sets[setname].frames:
                        miss.append(f"{rid}:{field}={ix + d}")
        if s == "armors":
            for raw in uc.as_list(f.get("customArmorPreviewIndex")):
                ix = index(rec, "customArmorPreviewIndex", "CustomArmorPreviews", raw)
                if ix is not None:
                    n += 1
                    if ix not in sets["CustomArmorPreviews"].frames:
                        miss.append(f"{rid}:preview={ix}")
    return miss, n


def profiles(acc):
    """EN-профиль (без модов lang: ru) и моды игрока вне цепочки - что они меняют в графике юнитов."""
    prof = json.loads(re.sub(r"^\s*//.*$", "", (uc.PZ / "xp-profiles.json").read_text(encoding="utf-8-sig"), flags=re.M))
    p = next(x for x in prof["profiles"] if x["master"] == "piratez")
    ru = {m["id"] for m in p["mods"] if m.get("lang") == "ru"}
    off = {m["id"] for m in p["mods"] if m.get("off")}
    base_chain = uc.piratez_chain()
    base_ids = [m for m, _d in base_chain]
    st0 = acc["rules"]["piratez"]
    _st, ops0 = None, {}
    for (sec, rid), lst in st0.defs.items():
        if sec == "extraSprites":
            for rel, line, op in lst:
                ops0[(rel, line)] = op
    snap0 = graph_snapshot(st0, ops0)
    dirs = {}
    for d in (uc.PZ / "user" / "mods").iterdir():
        if d.is_dir():
            dirs[uc.read_meta(d).get("id") or d.name] = d
    variants = [("RU (цепочка переписи, контроль)", base_chain),
                ("EN (без модов lang: ru: " + ",".join(sorted(ru)) + ")", [(m, d) for m, d in base_chain if m not in ru])]
    star = base_ids.index("intro_voice") if "intro_voice" in base_ids else len(base_ids)
    for mid, d in sorted(dirs.items()):
        if mid in base_ids:
            continue
        ch = list(base_chain)
        ch.insert(star, (mid, d))
        variants.append((f"+ {mid} (мод игрока, место '*'" + (", в профиле выключен" if mid in off else "") + ")", ch))
    unit_sheets = set(acc["unit_sheet_names"])
    rows, summ = [], {}
    for label, chain in variants:
        t = time.time()
        st, ops = uc.load_rules(chain, ROOT / "src")
        snap = graph_snapshot(st, ops)
        diff = []
        for k in sorted(set(snap0) | set(snap), key=str):
            a, b = snap0.get(k), snap.get(k)
            if a != b:
                diff.append(k)
                rows.append(["piratez", label, k[0], k[1], k[2], (a or "")[:120], (b or "")[:120]])
        miss, checked = item_check(chain, st, ops)
        unit_touch = sorted({f"{k[0]}:{k[1]}" for k in diff if (k[0] == "extraSprites" and k[1] in unit_sheets)
                             or k[0] in ("armors", "units", "soldiers")})
        summ[label] = dict(changes=len(diff), by_section=dict(Counter(k[0] for k in diff).most_common()),
                           unit_graphics_changes=unit_touch,
                           item_frames_checked=checked, item_frames_missing=miss[:20], item_frames_missing_n=len(miss),
                           examples=[f"{k[0]}:{k[1]}:{k[2]}" for k in diff[:8]], seconds=round(time.time() - t, 1))
        print(f"   профиль {label}: изменений графики {len(diff)}, юнитов {len(unit_touch)}, "
              f"кадров предметов нет {len(miss)} из {checked} ({summ[label]['seconds']} с)", flush=True)
    summ["off_mods"] = sorted(off)
    summ["ru_mods"] = sorted(ru)
    return rows, summ


# =================================================================== main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--games", default="piratez,xcom1")
    ap.add_argument("--no-profiles", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    OUTC.mkdir(parents=True, exist_ok=True)
    code = Code(US)
    model, info = build_model(code)
    head = git_head()
    # поля видимости - из Armor::load, между visibilityAtDark и alwaysVisible
    al = ARMOR_CPP.read_text(encoding="utf-8", errors="replace").splitlines()
    i0 = next(i for i, l in enumerate(al) if 'tryRead("visibilityAtDark"' in l)
    i1 = next(i for i, l in enumerate(al) if 'tryRead("alwaysVisible"' in l)
    vis_fields = [re.search(r'tryRead\("(\w+)"', l).group(1) for l in al[i0:i1 + 1] if re.search(r'tryRead\("(\w+)"', l)]
    fsum = {}
    with open(uc.OUT / "frames_summary.tsv", encoding=ENC) as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split("\t")
            fsum[(p[0], p[1], int(p[2]))] = p[3]
    census_sheets = []
    with open(uc.OUT / "sheets.tsv", encoding=ENC) as f:
        hdr = next(f).rstrip("\n").split("\t")
        for line in f:
            census_sheets.append(dict(zip(hdr, line.rstrip("\n").split("\t"))))
    acc = defaultdict(list)
    acc["summary"] = {}
    acc["rules"] = {}
    acc["head"] = head
    acc["vis_fields"] = vis_fields
    acc["census_sheets"] = census_sheets

    # смысл кадров: все routine из таблицы, широкие условия
    sem_rows = []
    turrets_seen = [0, 1, 2]
    for rt, fn in enumerate(code.table):
        large = any(sp.form in PART_FORMS for sp in model.get(rt, []))
        variants = sorted({sp.variant for sp in model.get(rt, [])}) or [""]
        for forced in ((0, 2) if rt in (0, 13) else (0,)):
            o = dict(D=3, parts=4 if large else 1, forced=forced, can_f=True, can_m=True, kneel=True, fly=True, hover=True,
                     walk=True, weapon=True, helmet=True, turrets=set(turrets_seen))
            for hover in ((True, False) if rt in (2, 11) else (True,)):
                o["hover"] = hover
                for idx, entries in sorted(layout(model, info, rt, o).items()):
                    for sp, part, d, ph in entries:
                        if forced == 2 and not (sp.cond == "female" and sp.variant == "13h"):
                            continue
                        sem_rows.append([rt, fn, sp.variant, idx, sp.label, part, d, ph, sp.cond or "",
                                         f"{code.rel}:{sp.call_line}", f"{code.rel}:{sp.base_line}" if sp.base_line else "",
                                         "forcedTorso!=0" if forced == 2 else ("парение" if (rt in (2, 11) and hover) else "")])
        _ = variants
    sem_rows = [list(x) for x in dict.fromkeys(tuple(r) for r in sem_rows)]

    games = uc.games()
    for gname in [x.strip() for x in a.games.split(",") if x.strip()]:
        run_game(gname, games[gname], model, info, code, acc, fsum)

    prof_rows, prof_summ = ([], {})
    if not a.no_profiles and "piratez" in acc["rules"]:
        print("== профили", flush=True)
        prof_rows, prof_summ = profiles(acc)
    ev = uc.OUT / "explicit_variants.tsv"
    hd18 = dict(file=ev.relative_to(ROOT).as_posix(), exists=ev.is_file())
    if ev.is_file():
        with open(ev, encoding=ENC) as f:
            hd18["rows"] = sum(1 for _ in f) - 1

    W = uc.write_tsv
    W(OUTC / "frame_semantics.tsv", ["routine", "draw_func", "variant", "index", "part", "unit_part", "direction", "phase",
                                     "condition", "code_call", "code_number", "note"], sem_rows)
    W(OUTC / "resources.tsv", ["game", "class", "set", "source_kind", "decl_op", "decl_rule", "decl_rule_sha", "layer_mod",
                               "file", "path", "file_sha", "frames_put", "frames_won", "frames_in_layout", "status"], acc["resources"])
    W(OUTC / "references.tsv", ["game", "section", "id", "field", "value", "target_kind", "target", "status",
                                "winner_mod", "rule_file_line", "rule_file_sha", "note"], acc["references"])
    W(OUTC / "generic_paths.tsv", ["game", "path", "matches", "class", "verdict", "count", "example"], acc["generic"])
    W(OUTC / "entities.tsv", ["game", "armor", "engine_commit", "first_def", "sheet_winner_mod", "sheet_rule_line", "rule_file_sha",
                              "sheet", "routine", "routine_name", "size", "movement", "deathFrames", "forcedTorso", "worn_by_units",
                              "worn_by_soldier_types", "worn_how", "male", "female", "kneel", "turrets", "required_frames",
                              "missing_required", "missing_examples", "select_script", "linked_items", "corpseBattle",
                              "corpseGeo", "spriteInv", "doll_surfaces", "doll_layers_missing", "sheet_content_sha",
                              "sheet_files", "hd_mods", "hd_frames", "hd_missing_required", "hd_stale", "hd_check", "worn"],
      acc["entities"])
    W(OUTC / "missing_frames.tsv", ["game", "armor", "sheet", "routine", "index", "meaning", "units", "soldier_types", "script"],
      acc["missing"])
    W(OUTC / "sheet_coverage.tsv", ["game", "sheet", "armors", "armor_examples", "frames", "nonempty", "in_layout",
                                    "required_by_worn", "required_missing", "outside_layout", "outside_nonempty",
                                    "outside_examples", "outside_reason", "content_sha"], acc["coverage"])
    W(OUTC / "shared_sheets.tsv", ["game", "sheet", "armors", "armor_list", "routines", "sizes", "note"], acc["shared_sheets"])
    W(OUTC / "shared_frames.tsv", ["game", "exact", "sheets", "occurrences", "sheet_list", "examples", "meanings", "note"],
      acc["shared_frames"])
    W(OUTC / "shared_item_frames.tsv", ["game", "set", "index", "items", "item_list", "frame"], acc["item_shared"])
    W(OUTC / "mirror_pairs.tsv", ["game", "sheet", "i", "j", "tone_diff", "tone_ok", "meaning_i", "meaning_j", "dir_pair"],
      acc["mirror_pairs"])
    W(OUTC / "mirror_sheets.tsv", ["game", "sheet", "pairs", "tone_ok", "self_symmetric", "direction_pairs"], acc["mirror_sheets"])
    W(OUTC / "cross_index.tsv", ["game", "sheet_a", "sheet_b", "index_shift", "frames", "example"], acc["cross"])
    W(OUTC / "visibility.tsv", ["game", "armor", "field", "value", "sheet", "worn", "mod", "rule_file_line"], acc["visibility"])
    W(OUTC / "transforms.tsv", ["game", "kind", "source", "from", "to", "to_sheet", "sheet_status", "rule_file_line"], acc["transforms"])
    W(OUTC / "scripts.tsv", ["game", "hook", "section", "owner", "rule_file_line", "rule_file_sha", "scope"], acc["scripts"])
    W(OUTC / "categories.tsv", ["game", "category", "found", "examples", "searched"], acc["categories"])
    W(OUTC / "exceptions.tsv", ["game", "kind", "id", "reason", "explained"], acc["exceptions"])
    W(OUTC / "profiles.tsv", ["game", "profile", "section", "id", "field", "base", "variant"], prof_rows)
    summary = dict(engine_commit=head, unit_sprite_cpp=code.rel, routine_table=dict(enumerate(code.table)),
                   routine_table_line=f"{code.rel}:{code.table_line}", visibility_fields=vis_fields,
                   games=acc["summary"], profiles=prof_summ, hd18=hd18,
                   unexplained_total=sum(s["p7"]["unexplained"] for s in acc["summary"].values()),
                   seconds=round(time.time() - t0, 1))
    with open(OUTC / "coverage_summary.json", "w", encoding=ENC) as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, default=str)
    print(f"готово за {summary['seconds']} с; необъяснённых всего {summary['unexplained_total']} -> {OUTC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
