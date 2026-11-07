#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0c обрушения зданий: явные роли частей и правила опор вариантами, каждое правило - своим флагом.

ТЗ - docs/research/building-collapse-task-2026-10-07.md, отчёт - building-collapse-stage0c-2026-10-07.md.
Движок не трогается. evaluate() из collapse_census.py не меняется; evaluate2() без флагов даёт тот же
результат (py -3.13 tools\collapse_v2.py selfcheck).

Роли (census\collapse\stage0c\roles.tsv): автоматически по классу MCD, поверх - просмотренные по листам кадров.
Флаги evaluate2:
  R - несущесть по ролям, а не по броне: лестница, машина, мебель, ствол не несут; свая, столб, ферма,
      скала несут. Скат, тент, трасса, крона, подвес - не несущие.
  U - (диагностика) объект, несущий только по броне и не просмотренный, не несёт.
  T - две опоры: конец балки только на прямо подпёртом или уже удержанном балкой полу, не на консоли;
      консоль отсчитывается от удержанного.
  P - гипотеза «поперёк» (включает T): балка по x кончается на клетке, подпёртой западной стеной
      (она идёт по y) или предметом; по y - северной стеной или предметом; второй круг - на клетке,
      удержанной балкой другой оси.
  A - крепление: крона держится с деревом одним целым; скат и тент - на верхе несущей стены или
      несущем под собой, на опёртом полу, или в 1 клетке от закреплённого ската; закреплённые
      скаты - концы балок пола своего этажа; трасса - балкой и консолью вдоль себя между креплениями;
      подвес - на опёртом полу клетки над ним или на несущей стене своей клетки.
  K - гипотеза E04: пол, на котором стоит несущая стена или опора (не над несущей того же слота ниже),
      держится только прямо или балкой; консоль такую нагрузку не держит.
  E, Q - этап 0d: направленная консоль (cp) и угол рамы - см. collapse_v3.py.
  I - этап 0d: перемычка - несущая стена над проёмом до LINTEL клеток между двумя простенками той же
      линии, стоящими на несущих, держится и несёт.
  M - этап 0d: тент - полотно между креплениями держится балкой до L_TARP (без M - только в 1 клетке).

    py -3.13 tools\collapse_v2.py roles                 роли -> census\collapse\stage0c\roles.tsv
    py -3.13 tools\collapse_v2.py selfcheck             evaluate2 без флагов = evaluate
    py -3.13 tools\collapse_v2.py geom --terrain T --block B   срез этажей блока без расчёта опор
    py -3.13 tools\collapse_v2.py expect FILE [вариант ...]     сценарии
    py -3.13 tools\collapse_v2.py maps [вариант ...]           целые карты, только проверенные клетки
"""
import argparse
import collections
import hashlib
import json
import os
import pickle
import sys
import types
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_census as cc                      # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("census", "collapse", "stage0c")
SHEETS = OUT + "/sheets/"
BEARING = cc.BEARING
FURN_ROLES = {"FURNITURE", "TRUNK", "MACHINE", "STAIRS"}
SPECIAL = {"ROOF", "TARP", "RUN", "HANGER"}       # при A держатся своими правилами
LINTEL = 4                                        # флаг I (этап 0d): перемычка над проёмом до 4 клеток
L_TARP = 6                                        # флаг M (этап 0d): полотно тента между креплениями
L_WALK = int(os.environ.get("COLLAPSE_L_WALK", "10"))   # флаг L (этап 0f, гипотеза, в модель M0f не входит):
# лёгкий настил, L_WALK = расстояние между опорами = чистый пролёт + 1. Целая геометрия гипотезу не подтвердила:
# L_WALK 9 и 10 роняют мостки CHEMTOWN51 (от фермы (4,15) до фермы (15,15) - чистые 10), при 11 на целых блоках
# падают балкон WESTOWN_JEFFERSON и полоса TECBASE04W - определение «лёгкий» по 3x3 их захватывает
# (stage0f/walk_geom_L*.json)


def light_floors(floors):
    """Флаг L: лёгкий настил (мостки) - клетки пола, не входящие ни в один сплошной квадрат 3x3 пола своего
    этажа. Определяется местом на карте, а не записью MCD."""
    heavy = set()
    for (x, y) in floors:
        win = [(x + i, y + j) for i in range(3) for j in range(3)]
        if all(c in floors for c in win):
            heavy.update(win)
    return set(floors) - heavy

VARIANTS = {
    "base": "", "R": "R", "U": "RU", "T": "T", "TP": "TP", "A": "A", "K": "K",
    "R+T": "RT", "R+A": "RA", "R+T+A": "RTA", "R+T+A+K": "RTAK", "R+TP+A": "RTPA", "R+TP+A+K": "RTPAK",
}


def rng(a, b):
    return list(range(a, b + 1))


# ------------------------------------------------------------------ роли

# (роль, лист кадров, причина, спорно, [(набор, номера)])
REVIEWED = [
    ("COLUMN", "bearing_auto.png", "столб или стойка навеса по кадру", 0,
     [("COMMERCE", [37, 69, 72]), ("COMMERCE_MAG", [69, 72]), ("URBAN", [72]), ("MILEXT", [12]),
      ("ISLANDURBAN2", [48]), ("PORTURBITS", [19])]),
    ("COLUMN", "carry_candidates.png", "свая или столб, броня ниже 30 - несущий по смыслу (E17)", 0,
     [("COMROADS", [15]), ("VILROADS", [15])]),
    ("TRUSS", "bearing_auto.png", "решётчатая опора, вышка", 0,
     [("MILWARE", [28, 75]), ("MILWAREGHOUL", [28]), ("PORTROADS", [26])]),
    ("TRUSS", "carry_candidates.png", "нога вышки, броня ниже 30", 0, [("MILEXT", [36, 37])]),
    ("TRUSS", "stage0d: кадр NUKE2 10", "клетка-леса из железа на всю клетку, стопки до 5, сверху пол Nuke2:0 в 237 "
     "местах из 263 (сваи вышки, помосты лагерей бандитов и NUKECITY)", 0, [("NUKE2", [10])]),
    # этап 0d: непросмотренные COLUMN/TRUSS (census\collapse\stage0d\roles_gap.tsv), листы roles_gap_sheet*.png
    ("TRUSS", "../../stage0d/roles_gap_sheet.png", "решётчатая вышка, тот же кадр, что MILWARE 75 и PORTROADS 26", 0,
     [("MILWAREGHOUL", [75]), ("PORTROADS", [27])]),
    ("COLUMN", "../../stage0d/roles_gap_sheet.png", "бетонный столб на всю клетку, сверху пол в 169 местах из 171 (URBANWAR)",
     0, [("URBANWAR", [72])]),
    ("MASS", "../../stage0d/roles_gap_sheet.png", "куб грунта с травой (холм), сверху пол в 314 местах; кирпичный массив",
     0, [("FOREST", [40]), ("WESTFLOOR", [8])]),
    ("MASS", "../../stage0d/roles_gap_sheet3.png", "скаты грунта, валуны и земляные глыбы - сверху почти всегда пусто",
     0, [("FOREST", rng(54, 63)), ("MOUNTGRASS", rng(54, 65)), ("MOUNTROCK", rng(78, 85)), ("MOUNTWASTE2", [85]),
         ("ISLANDURBAN2", rng(34, 37))]),
    ("HULL", "../../stage0d/roles_gap_sheet.png", "обшивка капсулы (CAPSULE) - судно, модель корпуса G/J", 1,
     [("XBASEN_BITS", [33, 34])]),
    ("TRUNK", "../../stage0d/roles_gap_sheet2.png", "ствол и пень дерева джунглей, сверху продолжение ствола", 0,
     [("JUNGLE", [32, 80, 81])]),
    ("HANGER", "../../stage0d/roles_gap_sheet3.png", "цепь и крюк, подвешены", 0,
     [("MILWAREGHOUL", [21, 22]), ("MILWARE", [21]), ("PORTROADS", [37])]),
    ("STAIRS", "../../stage0d/roles_gap_sheet3.png", "ступени, трибуна на ножках - стоит, этаж не несёт", 0,
     [("URBAN40K", [56]), ("MADDECOR_WASTE", [4, 7])]),
    ("MACHINE", "../../stage0d/roles_gap_sheet.png", "реактор с трубами; сверху обычный пол здания (SGR_BASIS 6/9, "
     "SGR_SERVICE 13), его держат стены", 0, [("SGR_REACTORS", [3, 5])]),
    ("FURNITURE", "../../stage0d/roles_gap_sheet2.png", "свалка, контейнеры, шины, антенна, стулья, бак, стойки, ворот",
     0, [("URBAN_WASTE", [49, 54, 56, 83, 105]), ("PORTROADS", [35, 68]), ("INDUSLUM", [40]), ("MILWARE", [0]),
         ("MILWAREGHOUL", [0]), ("WESTFLOOR", [5]), ("BARN_JUNK", [9]), ("INDUSLUM", [19])]),
    ("ROOF", "../../stage0d/roles_rural_sheet.png", "соломенные скаты и конёк хаты (RURAL, H08 этапа 0c); "
     "решётчатая кровля листом на z2 без пола, снизу стены INDUSLUM 44", 0,
     [("VILBAN", rng(42, 46) + rng(48, 50)), ("INDUSLUM", [70])]),
    ("FURNITURE", "../../stage0d/roles_rural_sheet.png", "обгорелые остатки хаты и крыши, столбик; антенна на крыше "
     "(VILFRNITURE 89 стоит на скате VILBAN 44 на z2)", 0,
     [("VILBAN", [47, 51, 52, 53, 54]), ("VILFRNITURE", [89])]),
    ("RUN", "../../stage0d/roles_rural_sheet.png", "трубы, как PORTROADS 28/30", 0, [("PORTROADS", [29])]),
    ("FURNITURE", "../../stage0d/roles_gap_sheet.png", "СПОРНО: стеллажи и поддоны, сверху пол в 2-3 местах "
     "(CHEMTOWN51/52) - не опора или помост?", 1, [("MILWAREGHOUL", [6, 7, 30])]),
    ("FURNITURE", "../../stage0d/roles_gap_sheet.png", "СПОРНО: облако красно-синих точек в подземном слое NUKECITY "
     "между каменными блоками NUKE_UNDERGROUND 0/3, сверху улица Nuke2:0 в 33 местах из 42 - руда, грибы?", 1,
     [("NUKE_UNDERGROUND", [4])]),
    # этап 0d, вторая волна: записи вне roles.tsv (блоки, которых нет на картах боёв) под висящими полами
    # (census\collapse\stage0d\hung_below.tsv, лист roles_hung_sheet.png)
    ("MASS", "../../stage0d/roles_hung_sheet.png", "куб скалы или грунта на всю клетку: земля деревни мумий, "
     "пещеры некрополя и замков, лунный грунт, ледяной куб, коралловая скала, скала тёмной башни", 0,
     [("MUMMY_VILLAGE", [60]), ("CAVEBLACK", [9, 10, 11, 12]), ("CAVEBROWN", [9]), ("URBAN40K2MOON", [6]),
      ("FOREST_SNOW", [40]), ("FOREST_WASTE", [40]), ("BLACKFOREST", [40]), ("FORESTRED", [40]),
      ("XOPSDESERTRED", [40]), ("XOPSDESERT", [40]), ("SEACORAL", [16, 17, 21]), ("URBAN40KN1", [6]),
      ("SIETCH_DARK", [5])]),
    ("COLUMN", "../../stage0d/roles_hung_sheet.png", "столб на всю высоту этажа (дерево, бетон, металл), "
     "как URBANWAR 72; капитель колонны - верх столба под полом", 0,
     [("URBANLUX", [72]), ("SEAURBANDIO", [72]), ("URBAN_WASTE", [72]), ("MADDECOR_WASTE", [14]),
      ("IDT_SNOWBARN", [29]), ("DREAMVILLA", [26]), ("ATLANTDESERT", [47])]),
    ("COLUMN", "../../stage0d/roles_hung_sheet.png", "сваи дома на сваях NUKE18: рама и плита на четырёх ножках, "
     "сверху пол Nuke2:0 (как свая Nuke2:10 вышки бандитов)", 0, [("NUKE2", [8, 9])]),
    ("FURNITURE", "../../stage0d/roles_hung_sheet.png", "мусор и обломки под домом на сваях - не опора", 0,
     [("NUKE2", [11])]),
    ("MASS", "bearing_auto.png", "скала, грунт, кладка - массив", 0,
     [("ISLANDURBAN2", [28, 29]), ("URBAN40K", [6]), ("WESTFLOOR", [6]),
      ("MOUNTGRASS", rng(78, 85)), ("MOUNTWASTE2", rng(78, 84))]),
    ("MACHINE", "bearing_auto.png", "машина, стойка аппаратуры, бак - стоит, этаж не несёт", 1,
     [("MILTECHDIO", [0]), ("MILTECHGHOUL", [0, 1]), ("URBAN40K", [108]), ("COMMERCE", [94, 95]),
      ("COMMERCE_MAG", [94, 95]), ("MILINDUSTRIAL", rng(9, 12)), ("MILINDUSTRIALGHOUL", rng(9, 12))]),
    ("STAIRS", "bearing_auto.png", "лестница - стоит, этаж не несёт", 0,
     [("COMMERCE", [48, 49, 55, 56]), ("COMMERCE_MAG", [48, 49, 55, 56]), ("URBAN40K", [49]),
      ("MILWARE", [24, 26]), ("MILWAREGHOUL", [24, 26]), ("ISLANDURBAN2", [43]), ("BARN_JUNK", [16]),
      ("PORTROADS", [64, 67])]),
    ("FURNITURE", "bearing_auto.png", "мебель, ящики, автоматы - высокая броня не делает несущим", 0,
     [("COMDECOR", [59, 60]), ("CONTAINERS", [17, 18, 19]), ("MILTECHGHOUL", [15, 26]), ("MILWARE", [30]),
      ("PORTROADS", [32, 34]), ("ABUNKER", [0]), ("NUKE3", [33]), ("MILWAREGHOUL", [20]), ("JUNGLE", [76])]),
    ("FURNITURE", "carry_candidates.png", "мебель, ящики, реактор, шкаф", 0,
     [("URBAN", [42, 43, 111]), ("MILWARE", [38, 40]), ("CONTAINERS", [14, 15]), ("SGR_REACTORS", [0, 4]),
      ("MILINDUSTRIAL", [0]), ("XB3BITZ1", [25]), ("XB3BITZ1_MAG", [25]), ("URBAN40K", [95, 103]),
      ("COMMERCE", [103]), ("MANSIONFURNITURE_MAG", [10])]),
    ("TRUNK", "misc_check.png", "ствол дерева - держит крону, этаж не несёт", 0,
     [("JUNGLE", [33]), ("ISLANDURBAN2", [49]), ("COMDECOR", [15])]),
    ("CROWN", "misc_check.png", "крона пальмы или дерева над стволом и соседними клетками (на этапе 0b ошибочно - плющ)", 0,
     [("COMDECOR", [11, 12, 13]), ("ISLANDURBAN2", [45, 46, 47]), ("JUNGLE", rng(34, 42))]),
    ("ROOF", "idt_farm_roof.png", "скат и стропила крыши амбара", 0, [("IDT_FARM", rng(27, 37))]),
    ("TARP", "hang_objects.png", "тент над прилавком", 0, [("PORTURBITS", rng(38, 41))]),
    ("RUN", "hang_objects.png", "труба или транспортёр - трасса", 0,
     [("MILINDUSTRIAL", [1, 2]), ("MILINDUSTRIALGHOUL", [1, 2]), ("MILWARE", [29, 31, 78]),
      ("MILWAREGHOUL", [29, 31, 78]), ("PORTROADS", [28, 30])]),
    ("HANGER", "bearing_auto.png", "крюк крана, подвешен к потолку", 0, [("MILWARE", [22])]),
    ("HULL", "hang_objects.png", "обшивка корабля на наземной карте - вне пилота", 1,
     [("C_EXT_WALL_SILVER", rng(4, 7)), ("XBASEN_BITS", [2])]),
]
DISPUTED_FLOORS = {("FLOORSET", 25): "решётка пола над двором особняка на z=6 - стеклянная крыша? пролёт 14-17",
                   ("MANSIONFLOOR_MAG", 25): "то же, вариант _MAG"}

AUTO = {"f": {"floor": "FLOOR"},
        "w": {"wall": "WALL", "window": "WALL", "hard": "WALL", "door": "DOOR", "low": "LOW"},
        "o": {"block": "WALL", "edgewall": "WALL", "hard": "WALL", "column": "COLUMN", "truss": "TRUSS",
              "furniture": "FURNITURE", "object": "OBJECT", "door": "DOOR"}}
AUTO["n"] = AUTO["w"]


def reviewed_map():
    out = {}
    for role, sheet, why, disp, ids in REVIEWED:
        for s, nums in ids:
            for i in nums:
                out[(s.upper(), i)] = (role, sheet, why, disp)
    return out


def cmd_roles(a):
    rev = reviewed_map()
    with open(OUT + "/records.tsv", encoding=ENC) as f:
        lines = f.read().splitlines()
    head = lines[0].split("\t")
    rows, seen = [], set()
    cnt = collections.Counter()
    for ln in lines[1:]:
        r = dict(zip(head, ln.split("\t")))
        s, i, slot, cls = r["set"], int(r["idx"]), r["slot"], r["cls"]
        auto = AUTO[slot].get(cls, cls.upper())
        key = (s.upper(), i)
        if key in rev:
            role, sheet, why, disp = rev[key]
            src = "просмотрено"
            if role in ("COLUMN", "TRUSS", "MASS", "HULL") and auto == "WALL":
                role = "WALL"
        else:
            role, src, disp, sheet = auto, "авто", 0, ""
            why = "класс MCD %s" % cls
            if cls in ("column", "truss"):
                why = "несущий только по броне %s >= %d, не просмотрено" % (r["armor"], cc.COLUMN_MIN_ARMOR)
                disp = 1 if int(r["up"] or 0) >= 5 else 0
        if key in DISPUTED_FLOORS and slot == "f":
            disp, why, src = 1, DISPUTED_FLOORS[key], "просмотрено"
            sheet = "top_floors.png"
        bear = int(role in ("WALL", "COLUMN", "TRUSS", "MASS", "HULL"))
        rows.append(("%s:%d:%s" % (s, i, slot), s, i, slot, role, bear, cls, r["armor"], src,
                     (SHEETS + sheet) if sheet else "", why, disp, r["up"], r["hang"]))
        seen.add(key)
        cnt[(role, src)] += 1
    miss = sorted(k for k in rev if k not in seen)
    cc.write_tsv(OUT + "/roles.tsv", ["id", "set", "idx", "slot", "role", "bearing", "mcd_class", "armor", "source",
                                      "image", "reason", "disputed", "up_on_saves", "hang_on_saves"], rows)
    print("записей", len(rows), "просмотрено", sum(1 for r in rows if r[8] == "просмотрено"),
          "спорных", sum(1 for r in rows if r[11]))
    for (role, src), n in sorted(cnt.items()):
        print("  %-10s %-12s %d" % (role, src, n))
    if miss:
        print("НЕТ В ЗАПИСЯХ:", miss)


def load_roles():
    out = {}
    with open(OUT + "/roles.tsv", encoding=ENC) as f:
        lines = f.read().splitlines()
    head = lines[0].split("\t")
    for ln in lines[1:]:
        r = dict(zip(head, ln.split("\t")))
        out[(r["set"].upper(), int(r["idx"]), r["slot"])] = (r["role"], r["source"])
    return out


def apply_roles(blk, roles):
    rev = reviewed_map()
    for (k, x, y, z), p in blk.parts.items():
        role, src = roles.get((p["set"].upper(), p["idx"], k), (None, None))
        if role is None and (p["set"].upper(), p["idx"]) in rev:     # запись есть в блоках, но не на картах боёв
            role, src = rev[(p["set"].upper(), p["idx"])][0], "просмотрено"
            if role in ("COLUMN", "TRUSS", "MASS", "HULL") and AUTO[k].get(p["cls"]) == "WALL":
                role = "WALL"
        if role is None:
            role = AUTO[k].get(p["cls"], p["cls"].upper())
            src = "авто"
        p["role"], p["rev"] = role, src == "просмотрено"
    return blk


# ------------------------------------------------------------------ опоры v2

def eff_cls(key, p, flags):
    cls, role = p["cls"], p.get("role", "")
    if key[0] != "o":
        return cls
    if "R" in flags:
        if role in ("COLUMN", "MASS"):
            cls = "column"
        elif role == "TRUSS":
            cls = "truss"
        elif role in ("WALL", "HULL"):
            pass
        elif role in FURN_ROLES or role == "CROWN":
            cls = "furniture"
        elif cls in BEARING:                     # скат-блок, тент-ферма и прочие не несущие роли
            cls = "object"
        if "U" in flags and role in ("COLUMN", "TRUSS") and not p.get("rev"):
            cls = "furniture"
    if "A" in flags and role == "CROWN":
        cls = "furniture"
    return cls


def beam_axis(xy, floors, ends, axis):
    if xy in ends:
        return 0
    dx, dy = axis
    tot = 0
    for sgn in (1, -1):
        x, y = xy
        d = 0
        while True:
            x += dx * sgn
            y += dy * sgn
            d += 1
            if (x, y) not in floors:
                return None
            if (x, y) in ends:
                break
        tot += d
    return tot


def lintels(live, below, carry, bearing):
    """Флаг I: несущая стена над проёмом. Ряд несущих стен одной линии без несущей под собой держится,
    если с обеих сторон он упирается в несущую стену той же линии, стоящую на несущей, и длина ряда
    не больше LINTEL. Стена w тянется по y, n - по x."""
    out = set()
    for k, (dx, dy) in (("w", (0, 1)), ("n", (1, 0))):
        lw = live[k]
        base = {xy for xy, key in lw.items() if below[k].get(xy) in carry and bearing(key)}
        for (x, y), key in lw.items():
            if (x, y) in base or not bearing(key):
                continue
            run, ok = 1, True
            for sgn in (1, -1):
                cx, cy = x, y
                while True:
                    cx += dx * sgn
                    cy += dy * sgn
                    nk = lw.get((cx, cy))
                    if nk is None or not bearing(nk):
                        ok = False
                        break
                    if (cx, cy) in base:
                        break
                    run += 1
                if not ok:
                    break
            if ok and run <= LINTEL:
                out.add(key)
    return out


def consoles(held, floors, C):
    dist = {xy: 0 for xy in held}
    q = deque(held)
    while q:
        x, y = q.popleft()
        for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if nb in floors and nb not in dist:
                dist[nb] = dist[(x, y)] + 1
                q.append(nb)
    return dist


def consoles_dir(anchors, floors, C, cp):
    """Консоль с направлением (флаг E, гипотеза этапа 0d): от клетки, опёртой на линию стены, пол
    выносится поперёк линии до C, а вдоль неё за концом - не дальше cp. anchors: клетка -> оси,
    поперёк которых она опёрта ('x' - стена w, 'y' - стена n, обе - столб, массив, скат)."""
    dist = {}
    for axes in ({"x", "y"}, {"x"}, {"y"}):
        start = [xy for xy, a in anchors.items() if a == axes]
        seen = {(xy, 0): 0 for xy in start}
        q = deque((xy, 0) for xy in start)
        while q:
            (x, y), par = q.popleft()
            d = seen[((x, y), par)]
            if (x, y) not in dist or d < dist[(x, y)]:
                dist[(x, y)] = d
            if d >= C:
                continue
            for ax, nb in (("x", (x + 1, y)), ("x", (x - 1, y)), ("y", (x, y + 1)), ("y", (x, y - 1))):
                np_ = par + (ax not in axes)
                if nb in floors and np_ <= cp and (nb, np_) not in seen:
                    seen[(nb, np_)] = d + 1
                    q.append((nb, np_))
    return dist


def evaluate2(blk, removed=frozenset(), flags="", C=2, L=12, mass_rule=True, order=2, carry_rule="any",
              run_c=2, roof_reach=1, k_c=0, cp=1):
    if "P" in flags and "T" not in flags:
        flags += "T"
    A = "A" in flags
    cls = {key: eff_cls(key, p, flags) for key, p in blk.parts.items()}
    role = {key: p.get("role", "") for key, p in blk.parts.items()}
    bearing = lambda key: cls[key] in BEARING      # noqa: E731
    special = (lambda key: role[key] in SPECIAL) if A else (lambda key: False)   # noqa: E731
    sup, carry, info = set(), set(), {}
    hangers = []
    for z in range(blk.sz):
        lvl = blk.lv[z]
        live = {k: {xy: key for xy, key in lvl[k].items() if key not in removed} for k in cc.KINDS}
        if z == 0:
            for k in cc.KINDS:
                sup.update(live[k].values())
                carry.update(key for key in live[k].values() if bearing(key))
            continue
        below = blk.lv[z - 1]
        props, px, py, po = set(), set(), set(), set()
        for (x, y), key in below["w"].items():
            if key in carry:
                props.update(((x, y), (x - 1, y)))
                px.update(((x, y), (x - 1, y)))
        for (x, y), key in below["n"].items():
            if key in carry:
                props.update(((x, y), (x, y - 1)))
                py.update(((x, y), (x, y - 1)))
        for (x, y), key in below["o"].items():
            if key in carry:
                props.add((x, y))
                po.add((x, y))
                for dx, dy in cc.EDGE_NB.get(blk.parts[key]["rec"]["big_wall"], ()):
                    props.add((x + dx, y + dy))
                    (px if dx else py).add((x + dx, y + dy))
        floors = set(live["f"])
        mass = {xy for xy, key in live["o"].items() if bearing(key)}
        msup = set()
        for xy in mass:
            under = below["o"].get(xy)
            if under in carry or (xy in floors and xy in props):
                msup.add(xy)
        if mass_rule:
            q = deque(msup)
            while q:
                x, y = q.popleft()
                for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if nb in mass and nb not in msup:
                        msup.add(nb)
                        q.append(nb)
        direct = floors & (props | msup)
        # скаты и тенты: закреплены на верхе несущей стены или несущем под собой
        roofc = {xy: key for xy, key in live["o"].items() if A and role[key] in ("ROOF", "TARP")}
        ranch = set()
        for (x, y), key in roofc.items():
            edges = [below["w"].get((x, y)), below["w"].get((x + 1, y)),
                     below["n"].get((x, y)), below["n"].get((x, y + 1)), below["o"].get((x, y))]
            if any(e in carry for e in edges if e) or \
                    (below["o"].get((x, y)) in sup and role.get(below["o"].get((x, y))) in ("ROOF", "TARP")):
                ranch.add((x, y))
        floors_b = floors | ranch
        direct_b = direct | ranch
        if "Q" in flags:
            # угол рамы (гипотеза этапа 0d): клетка, у которой прямые опоры с соседней клетки и по x, и по y,
            # опёрта на два ребра и считается прямой; один шаг, не по цепочке
            direct_b |= {(x, y) for (x, y) in floors - direct_b
                         if ((x + 1, y) in direct_b or (x - 1, y) in direct_b) and
                         ((x, y + 1) in direct_b or (x, y - 1) in direct_b)}
        if "T" in flags:
            held = set(direct_b)
            best_l = {}
            if "P" in flags:
                ex = (floors & (px | po | msup)) | ranch
                ey = (floors & (py | po | msup)) | ranch
                bx, by = set(), set()
                for _ in range(order):
                    nbx = {xy for xy in floors if beam_axis(xy, floors_b, ex | by, (1, 0)) is not None and
                           beam_axis(xy, floors_b, ex | by, (1, 0)) <= L}
                    nby = {xy for xy in floors if beam_axis(xy, floors_b, ey | bx, (0, 1)) is not None and
                           beam_axis(xy, floors_b, ey | bx, (0, 1)) <= L}
                    bx, by = nbx, nby
                for xy in floors:
                    ls = [v for v in (beam_axis(xy, floors_b, ex | by, (1, 0)),
                                      beam_axis(xy, floors_b, ey | bx, (0, 1))) if v is not None]
                    if ls:
                        best_l[xy] = min(ls)
                held |= bx | by
            else:
                for _ in range(order):
                    base = set(held)
                    for xy in floors:
                        nl = cc.beam(xy, floors_b, base)
                        if nl is not None and (xy not in best_l or nl < best_l[xy]):
                            best_l[xy] = nl
                        if nl is not None and nl <= L:
                            held.add(xy)
            dist = consoles(held & floors_b, floors, C)
            okf = {xy for xy in floors if dist.get(xy) is not None and dist[xy] <= C}
        else:
            if "E" in flags:
                anchors = {}
                for xy in direct_b:
                    a = set()
                    if xy in px:
                        a.add("x")
                    if xy in py:
                        a.add("y")
                    if xy in po or xy in msup or xy in ranch or not a:
                        a = {"x", "y"}
                    anchors[xy] = a
                dist = consoles_dir(anchors, floors, C, cp)
            else:
                dist = consoles(direct_b, floors, C)
            okf = {xy for xy in floors if dist.get(xy) is not None and dist[xy] <= C}
            best_l = {}
            bheld = set(direct_b)
            light = light_floors(floors) if "L" in flags else set()
            lim = lambda xy: L_WALK if xy in light else L       # noqa: E731
            for _ in range(order):
                # B (этап 0e, эксперимент): концы балки - только прямые опоры и клетки, уже взятые балкой;
                # конец консоли концом балки не служит (иначе пролёт растёт до L + 2C)
                base = set(bheld) if "B" in flags else set(okf) | direct_b
                for xy in floors:
                    nl = cc.beam(xy, floors_b, base)
                    if nl is not None and (xy not in best_l or nl < best_l[xy]):
                        best_l[xy] = nl
                    if nl is not None and nl <= lim(xy):
                        okf.add(xy)
                        bheld.add(xy)
            held = direct | {xy for xy, nl in best_l.items() if nl <= lim(xy)}
        if "K" in flags:
            loaded = set()
            for k, sides in (("w", lambda x, y: ((x, y), (x - 1, y))),
                             ("n", lambda x, y: ((x, y), (x, y - 1)))):
                for (x, y), key in live[k].items():
                    if bearing(key) and below[k].get((x, y)) not in carry:
                        ss = [s for s in sides(x, y) if s in floors]
                        if ss and not any(s in held for s in ss):
                            loaded.update(ss)
            for xy, key in live["o"].items():
                if bearing(key) and below["o"].get(xy) not in carry and xy in floors and xy not in held:
                    loaded.add(xy)
            for xy in loaded:
                if xy in okf and xy not in held and (dist.get(xy) or 0) > k_c:
                    okf.discard(xy)
        for xy in floors:
            info[live["f"][xy]] = (xy in direct, dist.get(xy), best_l.get(xy))
            if xy in okf:
                sup.add(live["f"][xy])
        lint = lintels(live, below, carry, bearing) if "I" in flags else set()
        for k, sides in (("w", lambda x, y: ((x, y), (x - 1, y))),
                         ("n", lambda x, y: ((x, y), (x, y - 1)))):
            for (x, y), key in live[k].items():
                under = below[k].get((x, y))
                if any(s in okf for s in sides(x, y)) or under in carry or key in lint:
                    sup.add(key)
                    if bearing(key) and (carry_rule == "any" or under in carry or key in lint or
                                         any(s in direct for s in sides(x, y))):
                        carry.add(key)
        furn = {xy for xy, key in live["o"].items() if cls[key] == "furniture" and not special(key)}
        fsup = set()
        for (x, y), key in live["o"].items():
            if special(key):
                continue
            under = below["o"].get((x, y))
            walls = [live["w"].get((x, y)), live["w"].get((x + 1, y)),
                     live["n"].get((x, y)), live["n"].get((x, y + 1))]
            if (x, y) in okf or (x, y) in msup or \
                    under in carry or (under in sup and cls[under] == "furniture") or \
                    any(w in carry for w in walls if w):
                sup.add(key)
                if bearing(key) and (carry_rule == "any" or under in carry or
                                     (x, y) in direct or (x, y) in msup):
                    carry.add(key)
                if (x, y) in furn:
                    fsup.add((x, y))
        q = deque(fsup | {xy for xy, key in live["o"].items() if key in sup and bearing(key)})
        while q:
            x, y = q.popleft()
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in furn and nb not in fsup:
                    fsup.add(nb)
                    sup.add(live["o"][nb])
                    q.append(nb)
        if not A:
            continue
        # скаты: вторые крепления - опёртый пол или массив своей клетки; держатся в roof_reach от креплений
        anch = set(ranch) | {xy for xy in roofc if xy in okf or xy in msup}
        dr = consoles(anch, set(roofc), roof_reach)
        for xy, d in dr.items():
            if d <= roof_reach:
                sup.add(roofc[xy])
        if "M" in flags:
            # этап 0d: тент - полотно, натянутое между креплениями: держится балкой до L_TARP
            tset = {xy for xy, key in roofc.items() if role[key] == "TARP"}
            for xy in tset:
                nl = cc.beam(xy, tset, anch & tset)
                if nl is not None and nl <= L_TARP:
                    sup.add(roofc[xy])
        # трасса: крепления - опёртый пол, несущее под собой, опёртая мебель под собой, несущая стена
        # своей клетки, несущий предмет рядом; держится балкой до L и консолью до run_c
        runc = {xy: key for xy, key in live["o"].items() if role[key] == "RUN"}
        ra = set()
        for (x, y), key in runc.items():
            under = below["o"].get((x, y))
            walls = [live["w"].get((x, y)), live["w"].get((x + 1, y)),
                     live["n"].get((x, y)), live["n"].get((x, y + 1))]
            nbo = [live["o"].get(nb) for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))]
            if (x, y) in okf or (x, y) in msup or under in carry or \
                    (under in sup and cls[under] == "furniture") or any(w in carry for w in walls if w) or \
                    any(o in carry for o in nbo if o):
                ra.add((x, y))
        rset = set(runc)
        rheld = set(ra) | {xy for xy in rset if (cc.beam(xy, rset, ra) or 99) <= L and cc.beam(xy, rset, ra) is not None}
        dr = consoles(rheld, rset, run_c)
        for xy, d in dr.items():
            if d <= run_c:
                sup.add(runc[xy])
        hangers += [(xy, z, key) for xy, key in live["o"].items() if role[key] == "HANGER"]
    for (x, y), z, key in hangers:
        above = blk.lv[z + 1]["f"].get((x, y)) if z + 1 < blk.sz else None
        walls = [blk.lv[z]["w"].get((x, y)), blk.lv[z]["w"].get((x + 1, y)),
                 blk.lv[z]["n"].get((x, y)), blk.lv[z]["n"].get((x, y + 1))]
        if (above and above in sup and above not in removed) or any(w in carry for w in walls if w):
            sup.add(key)
    blk.carry = carry
    return sup, info


# ------------------------------------------------------------------ данные

def game_args():
    return types.SimpleNamespace(install=os.path.join("Пиратки", "Dioxine_XPiratez"), mod="Piratez", master="xcom1")


def read_expect(path):
    with open(path, encoding=ENC) as f:
        lines = f.read().splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln.strip() and not ln.startswith("#")]


def load_blocks(expect, roles):
    blocks = {}
    for e in expect:
        key = (e["terrain"].upper(), e["block"].upper())
        if key in blocks:
            continue
        for tname, kind, t, bname, blk, err, cache in cc.all_blocks(game_args(), only_block=e["block"],
                                                                    only_terrain=e["terrain"]):
            if blk is not None:
                blocks[key] = apply_roles(blk, roles)
                break
        if key not in blocks:
            raise SystemExit("нет блока %s/%s" % key)
    return blocks


def cmd_selfcheck(a):
    roles = load_roles()
    expect = read_expect("census/collapse/expect.tsv")
    blocks = load_blocks(expect, roles)
    bad = 0
    for e in expect:
        blk = blocks[(e["terrain"].upper(), e["block"].upper())]
        rm = frozenset(cc.select(blk, e["remove"]))
        for kw in (dict(), dict(order=1), dict(carry_rule="direct"), dict(C=0)):
            s1, i1 = cc.evaluate(blk, rm, **kw)
            s2, i2 = evaluate2(blk, rm, "", **kw)
            if s1 != s2 or i1 != i2:
                bad += 1
                print("РАСХОЖДЕНИЕ", e["id"], kw, len(s1 ^ s2))
    import collapse_battles as cb
    d = cb.Data(game_args())
    for name in sorted(os.listdir(OUT + "/source"))[:a.maps]:
        m, src = load_map(d, name[:-4] + ".sav", roles)
        s1, i1 = cc.evaluate(m)
        s2, i2 = evaluate2(m, frozenset(), "")
        if s1 != s2 or i1 != i2:
            bad += 1
            print("РАСХОЖДЕНИЕ карта", name, len(s1 ^ s2))
    print("selfcheck:", "OK" if not bad else "РАСХОЖДЕНИЙ %d" % bad)
    return 1 if bad else 0


# ------------------------------------------------------------------ срез блока для рецензента

OCH = {"COLUMN": "C", "TRUSS": "T", "MASS": "M", "WALL": "B", "HULL": "B", "FURNITURE": "f", "TRUNK": "t",
       "MACHINE": "x", "STAIRS": "s", "CROWN": "k", "ROOF": "r", "TARP": "a", "RUN": "p", "HANGER": "h",
       "OBJECT": "o", "DOOR": "d"}
ECH = {"WALL": "#", "DOOR": "D", "LOW": "_"}


def geom_text(blk):
    """Этажи блока буквами, без расчёта опор. Клетка - 3 знака: западный край, пол, предмет.
    Строка над клеткой - северный край. # несущая стена или окно, D дверь, _ низкая (перила);
    пол: = есть, пробел нет; предмет: C столб, T ферма, M массив, B блок-стена, f мебель, t ствол,
    x машина, s лестница, k крона, r скат, a тент, p трасса, h подвес, o мелочь, d дверь."""
    out = ["блок %s (%s) %dx%dx%d" % (blk.name, blk.terrain, blk.sx, blk.sy, blk.sz)]
    for z in range(blk.sz - 1, -1, -1):
        lv = blk.lv[z]
        if not any(lv[k] for k in cc.KINDS):
            continue
        out.append("z=%d" % z)
        out.append("    " + "".join("%-3d" % (x % 100) for x in range(blk.sx)))
        for y in range(blk.sy):
            top, mid = [], []
            for x in range(blk.sx):
                n = lv["n"].get((x, y))
                top.append(" " + (ECH.get(blk.parts[n]["role"], "?") * 2 if n else "  "))
                w = lv["w"].get((x, y))
                f = lv["f"].get((x, y))
                o = lv["o"].get((x, y))
                mid.append((ECH.get(blk.parts[w]["role"], "?") if w else " ") + ("=" if f else " ") +
                           (OCH.get(blk.parts[o]["role"], "?") if o else " "))
            out.append("    " + "".join(top))
            out.append("%3d " % y + "".join(mid))
    return "\n".join(out)


def cmd_geom(a):
    roles = load_roles()
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(game_args(), only_block=a.block or None, only_terrain=a.terrain):
        if blk is None:
            print(bname, err)
            continue
        if not a.block:
            up = sum(1 for k in blk.parts if k[3] > 0)
            if up:
                print("%-24s %-28s %dx%dx%d  частей выше земли %d" % (tname, bname, blk.sx, blk.sy, blk.sz, up))
            continue
        print(geom_text(apply_roles(blk, roles)))
        print()


# ------------------------------------------------------------------ сценарии

def run_expect(path, pick, roles):
    expect = read_expect(path)
    blocks = load_blocks(expect, roles)
    res = collections.defaultdict(dict)
    for v in pick:
        fl = VARIANTS[v]
        for e in expect:
            blk = blocks[(e["terrain"].upper(), e["block"].upper())]
            sup0, _ = evaluate2(blk, frozenset(), fl)
            rm = cc.select(blk, e["remove"])
            sup, _ = evaluate2(blk, frozenset(rm), fl)
            mf = cc.select(blk, e.get("must_fall", "")) - rm
            ms = cc.select(blk, e.get("must_stand", "")) - rm
            stood = sorted(k for k in mf if k in sup)
            fell = sorted(k for k in ms if k not in sup and k in sup0)
            h = sum(1 for k in ms if k not in sup0)
            verdict = "PASS" if not stood and not fell else "FAIL"
            if not mf and not ms:
                verdict = "EMPTY"
            elif verdict == "PASS" and h:
                verdict = "PASS*"
            res[e["id"]][v] = {"verdict": verdict, "stood": len(stood), "must_fall": len(mf), "fell": len(fell),
                               "must_stand": len(ms), "hung_before": h,
                               "stood_keys": [list(k) for k in stood[:12]], "fell_keys": [list(k) for k in fell[:12]]}
    return expect, res


def cmd_expect(a):
    roles = load_roles()
    pick = a.variants or list(VARIANTS)
    with open(a.file, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    lock = os.path.splitext(a.file)[0] + ".lock.txt"
    if os.path.exists(lock):
        with open(lock, encoding=ENC) as f:
            txt = f.read()
        print("хэш", "совпадает с замком" if sha in txt else "НЕ СОВПАДАЕТ С ЗАМКОМ %s" % lock)
    else:
        print("замка нет:", lock)
    expect, res = run_expect(a.file, pick, roles)
    print("вердикт устояло/должно упасть упало/должно стоять h висело с начала")
    print("%-5s " % "id" + " ".join("%-18s" % v for v in pick))
    for e in expect:
        print("%-5s " % e["id"] + " ".join("%-18s" % ("%s %d/%d %d/%d h%d" % (
            r["verdict"], r["stood"], r["must_fall"], r["fell"], r["must_stand"], r["hung_before"]))
            for r in (res[e["id"]][v] for v in pick)))
    npass = {v: sum(res[e["id"]][v]["verdict"].startswith("PASS") for e in expect) for v in pick}
    print("PASS:", npass)
    tag = os.path.splitext(os.path.basename(a.file))[0]
    with open(OUT + "/expect_%s.json" % tag, "w", encoding=ENC) as f:
        json.dump({"file": a.file, "sha256": sha, "pass": npass, "result": res}, f, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ целые карты

def load_map(d, name, roles):
    import collapse_battles as cb
    bt = cb.read_battle("census/collapse/battles/" + name)
    with open(OUT + "/source/" + name[:-4] + ".pkl", "rb") as f:
        src = pickle.load(f)
    bt["cells"] = src["cells"]
    bt["terrain"] = src["terrain"]
    return apply_roles(cb.map_block(d, bt, name[:-4]), roles), src


def verified_cells(d, name, m, src):
    """Клетки, где исходная карта совпадает с файлом блока MAP до части: геометрия доказана файлом блока,
    а не сейвом. Ключ - клетка, значение - террейн и имя блока."""
    import collapse_battles as cb
    cache = OUT + "/verified/" + name[:-4] + ".pkl"
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            return pickle.load(f)
    pls = cb.find_placements(m, d.candidates({"sets": sorted({p["set"] for p in m.parts.values()})},
                                             src["terrain"]), 0.8)
    out = {}
    for jac, _, blk, ox, oy, oz, mm, nmap in pls:
        bcell = collections.defaultdict(dict)
        for (k, x, y, z), v in blk.parts.items():
            bcell[(x + ox, y + oy, z + oz)][k] = (v["set"].upper(), v["idx"])
        for z in range(blk.sz):
            for y in range(blk.sy):
                for x in range(blk.sx):
                    c = (x + ox, y + oy, z + oz)
                    have = {}
                    for k in cc.KINDS:
                        key = m.lv[c[2]][k].get((c[0], c[1])) if c[2] < m.sz else None
                        if key:
                            have[k] = (m.parts[key]["set"].upper(), m.parts[key]["idx"])
                    if have == bcell.get(c, {}):
                        out[c] = (blk.terrain, blk.name)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "wb") as f:
        pickle.dump(out, f)
    return out


def cmd_maps(a):
    import collapse_battles as cb
    roles = load_roles()
    pick = a.variants or list(VARIANTS)
    if "base" not in pick:
        pick = ["base"] + pick
    d = cb.Data(game_args())
    names = sorted(n[:-4] + ".sav" for n in os.listdir(OUT + "/source") if n.endswith(".pkl"))
    if a.only:
        names = [n for n in names if a.only in n]
    tot = collections.defaultdict(collections.Counter)          # вариант -> счётчики
    byterr = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    newhang = collections.defaultdict(collections.Counter)      # вариант -> (террейн, набор, номер, роль)
    newsup = collections.defaultdict(collections.Counter)
    rows = []
    for name in names:
        m, src = load_map(d, name, roles)
        ver = verified_cells(d, name, m, src)
        up = [k for k in m.parts if k[3] > 0 and (k[1], k[2], k[3]) in ver]
        base = None
        line = [name, src["terrain"], len(up)]
        for v in pick:
            sup, _ = evaluate2(m, frozenset(), VARIANTS[v])
            hang = {k for k in up if k not in sup}
            if v == "base":
                base = hang
            tot[v]["up"] += len(up)
            tot[v]["hang"] += len(hang)
            for k in up:
                bt = ver[(k[1], k[2], k[3])][0]
                byterr[bt][v]["up"] += 1
                byterr[bt][v]["hang"] += k in hang
            for k in hang - base:
                p = m.parts[k]
                newhang[v][(ver[(k[1], k[2], k[3])][0], p["set"], p["idx"], p["role"])] += 1
            for k in base - hang:
                p = m.parts[k]
                newsup[v][(ver[(k[1], k[2], k[3])][0], p["set"], p["idx"], p["role"])] += 1
            line.append(len(hang))
        rows.append(line)
        print(name, src["terrain"], "проверено верха", len(up), " ".join(
            "%s=%d" % (v, n) for v, n in zip(pick, line[3:])), flush=True)
    tag = a.tag or "_".join(pick)
    cc.write_tsv(OUT + "/maps_%s.tsv" % tag, ["save", "terrain", "verified_up"] + pick, rows)
    print("\nВСЕГО проверенных частей верха", tot["base"]["up"])
    for v in pick:
        print("  %-12s висит %6d  %.2f%%  новых против базы %6d  опёрто против базы %6d" % (
            v, tot[v]["hang"], 100 * tot[v]["hang"] / max(1, tot[v]["up"]), sum(newhang[v].values()),
            sum(newsup[v].values())))
    with open(OUT + "/maps_%s.json" % tag, "w", encoding=ENC) as f:
        json.dump({"variants": {v: VARIANTS[v] for v in pick},
                   "total": {v: dict(tot[v]) for v in pick},
                   "by_terrain": {t: {v: dict(byterr[t][v]) for v in pick} for t in sorted(byterr)},
                   "new_hanging": {v: [[list(k), n] for k, n in newhang[v].most_common(80)] for v in pick},
                   "new_supported": {v: [[list(k), n] for k, n in newsup[v].most_common(80)] for v in pick}},
                  f, ensure_ascii=False, indent=1)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("roles")
    s = sub.add_parser("selfcheck")
    s.add_argument("--maps", type=int, default=6)
    s = sub.add_parser("geom")
    s.add_argument("--terrain")
    s.add_argument("--block", default="")
    s = sub.add_parser("expect")
    s.add_argument("file")
    s.add_argument("variants", nargs="*")
    s = sub.add_parser("maps")
    s.add_argument("variants", nargs="*")
    s.add_argument("--only", default="")
    s.add_argument("--tag", default="")
    a = ap.parse_args()
    return {"roles": cmd_roles, "selfcheck": cmd_selfcheck, "geom": cmd_geom, "expect": cmd_expect,
            "maps": cmd_maps}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
