"""Разметка типа конструкции 394 участков пакета review0k исполнителем (этап 0l, рецензия 0k).
Модель обрушения НЕ запускается: только геометрия блока (что под каждой клеткой) и материал записи по кадру.
Правила - census/collapse/stage0l/ctype_rules_v2.md. Выход - census/collapse/stage0l/ctype_marks.tsv (utf-8-sig).
review0k/ctype.tsv не трогается. Перенесён из блокнота сессии 2026-10-08 без изменения логики (вывод совпал до байта);
«zoom.png» в комментариях - кадры review0k/frames, увеличенные x8. Правила словами - ctype_rules_v2.md рядом с выходом;
замок census/collapse/stage0l/ctype_marks.lock.txt - sha256 генератора, правил и выхода (сверка - sha256sum).

    py -3.13 tools\\collapse_ctype_marks.py          ctype_marks.tsv и ctype_geo.json"""
import collections, os, sys
os.chdir("E:/OpenXCom")
sys.path.insert(0, "E:/OpenXCom/tools")
sys.stdout.reconfigure(encoding="utf-8")
import collapse_ctype as CT
import collapse_v2 as V

OUT = "census/collapse/stage0l/ctype_marks.tsv"

# --- материал записи по кадру (frames/<SET>_<idx>.png, просмотрены листами) ---
GROUND_SETS = {"CAVEBLACK", "CAVEBROWN", "CAVEDOOM", "MOUNT", "MOUNTMOON", "MOUNTSAND", "MOUNTTROP", "MUJUNGLE",
               "MUJUNGLE_2", "FOREST_WASTE", "FORESTBITSWASTE", "DESERTROCKS_RED", "LAVA", "SIETCHDOOM", "SIETCH",
               "SIETCH_DARK", "MUMMY_RUINS", "MANSIONGARDEN_MAG"}
GROUND_REC = {"URBITS:22", "WHITECASTLE:13", "WHITECASTLE:15", "XB1BR:0", "XB3BITZ3:17", "UAC_BASE_V:63"}
GROUND_LOW = {"XOPSUFOSMFLOOR:0": "красно-чёрная скала (лава?)", "FLOORSET:12": "оранжево-чёрная скала (лава?)",
              "XB3BITZ2:0": "красный щебень", "MUMMY_VILLAGE:63": "глина или грунт",
              "LAM_BASE:33": "органическая масса", "LAM_BASE:61": "органическая масса",
              "LAM_BASE:32": "органическая масса"}
GRATE = {"MILEXT:57", "MILEXT:58", "XB2BR:21", "XB3BITZ3:20", "XOPSDESERTRUINS:0", "XOPSDESERTRUINS:10",
         "WAREAN_TEC:1", "PORTROADS:15", "PORTROADS:36", "MADDECOR_WASTE:0", "DUNGEONEXTRA:0"}
WOOD = {"BARN:0", "BARN:20", "BARN_PP:0", "BARN_PP:1", "PORTROADS:16", "BRICKBAR:8", "URBAN:25", "COMMERCE:74",
        "COMMERCE_MAG:74", "IDT_BARNFLOOR:2", "IDT_SNOWBARN:20", "IDT_SNOWBARN:31", "VILFRNITURE:26"} | {
        "VILBAN:%d" % i for i in (42, 43, 44, 45, 48, 49, 50)}
# BARN 2 и MILWARE 48 при x8 (scratchpad zoom.png): сплошные складки без сквозных просветов, как PORTROADS 61 -
# профлист; решётка MILEXT 58 рядом - сетка с просветами.
SHEET = {"PORTROADS:61": "профлист", "BARN:2": "профлист (складки без просветов)", "BARN_PP:2":
         "профлист (складки без просветов)", "BRICKBAR:10": "черепица", "VILBAN:52": "кровля", "VILBAN:53": "кровля",
         "TAVERN:32": "кровля", "MILWARE:48": "профлист (складки без просветов)",
         "MILWAREGHOUL:48": "профлист (складки без просветов)"}
CONC = {"URBAN:78", "URBAN40K:78", "URBAN40KN1:78", "URBAN40K2MOON:78", "URBANLUX:78", "URBANWAR:78",
        "URBAN40K2MOON:25", "URBAN40KN1:25", "URBAN_WASTE:52", "URBAN_WASTE:53", "COMBITS:17", "COMBITS:20",
        "INDUSLUM:36", "INDUSLUM:31", "MILBARR:27", "MILBARRGHOUL:27", "COMROADS:12", "PORTROADS:1"}
HATCH = {"MILEXT:2", "MILEXT:3", "URBAN_WASTE:110", "URBAN_WASTE:111", "XB3BITZ2:25", "XB3BITZ2:26"}
LIFT = {"LIFTER:0", "MUMMY_VILLAGE:62", "SHOGG_VILLAGE_WALL02:12"}
ODD = {"MANSIONFLOOR_MAG:25": "почти пустой кадр (стекло или служебный пол)"}


# --- решения исполнителя по спорным участкам (срез geom/*.txt и кадр x8, scratchpad zoom.png) ---
# Спорным остаётся только участок, где разные прочтения дают РАЗНЫЙ тип.
_GRATE_ROOF = ("LIGHT_DECK", "medium", "решётчатая кровля модуля на стенах: кадр - сетка с просветами, пролёты между "
               "стенами в 1-3 клетки; кровля это или перекрытие - тип один, лёгкий настил")
_SOIL_ON_SLAB = ("HEAVY_SLAB", "medium", "грунт над помещениями по кадру x8 - земля; насыпь на перекрытии или "
                 "глинобитная плита - в обоих прочтениях тяжёлое перекрытие на стенах")
_CITY_CONC = ("HEAVY_SLAB", "medium", "пол постройки (URBAN40K*/C_INT_THIRD - бетон по кадру) в карте с природной "
              "семьёй: это здание города/базы, а не природный свод")
_HATCH = ("UNKNOWN", "low", "одиночный люк: тип задаёт окружающее перекрытие, по рецензии 0k расчёт с ним UNSUPPORTED; "
          "к Vitali не выносится")
MANUAL = {
    "U-049": ("LIGHT_DECK", "medium", "одна клетка решётки у края блока (y=13), рядом на z3 сеть мостков с перилами "
              "(_=, __): продолжение мостков в соседнем блоке"),
    "U-094": ("CANTILEVER", "medium", "профлист 2x2: две клетки над сараем, две за его стеной над пустотой - свес "
              "кровли, консоль от стены"),
    "U-140": _SOIL_ON_SLAB, "U-155": _SOIL_ON_SLAB, "U-315": _SOIL_ON_SLAB, "U-317": _SOIL_ON_SLAB,
    "U-386": _SOIL_ON_SLAB,
    "U-248": ("HEAVY_SLAB", "medium", "MUMMY_RUINS 44 по кадру x8 - тёмная каменная плита с бортиком, не грунт; "
              "лежит на стенах хижины"),
    "U-249": ("HEAVY_SLAB", "medium", "MUMMY_RUINS 44 по кадру x8 - тёмная каменная плита с бортиком, не грунт; "
              "лежит на стенах хижины"),
    "U-235": _CITY_CONC, "U-238": _CITY_CONC, "U-239": _CITY_CONC, "U-241": _CITY_CONC, "U-257": _CITY_CONC,
    "U-259": _CITY_CONC, "U-260": _CITY_CONC,
    "U-345": _HATCH, "U-347": _HATCH, "U-350": _HATCH, "U-393": _HATCH,
    "U-176": _GRATE_ROOF, "U-210": _GRATE_ROOF, "U-380": _GRATE_ROOF, "U-381": _GRATE_ROOF, "U-385": _GRATE_ROOF,
    "U-389": _GRATE_ROOF, "U-394": _GRATE_ROOF,
}
# остаются спорными (вопрос к Vitali, разные прочтения - разные типы)
ASK = {
    "U-250": "мост z3 между башнями ворот над проходом: арка (ARCH) или плита на стенах башен (HEAVY_SLAB)?",
    "U-251": "кровля z5 над воротами: навес на угловых столбах (CANOPY_POSTS) или свод/кровля на стенах башен?",
    "U-273": "TEC-база: красно-чёрная плита XOPSUFOSMFLOOR 0 на z3 - расплавленная скала над заглублённой базой "
             "(MASS) или пол корпуса (HEAVY_SLAB)? Тот же вопрос, что XOPSUFOEXT в conflicts.tsv",
    "U-278": "TEC-база: красно-чёрная плита XOPSUFOSMFLOOR 0 на z3 - расплавленная скала над заглублённой базой "
             "(MASS) или пол корпуса (HEAVY_SLAB)? Тот же вопрос, что XOPSUFOEXT в conflicts.tsv",
}


def material(rec):
    s = rec.split(":")[0]
    if rec in GROUND_LOW:
        return "GROUND", GROUND_LOW[rec], "low"
    if rec in GROUND_REC or s in GROUND_SETS:
        return "GROUND", "грунт/скала", "high"
    if rec in GRATE:
        return "GRATE", "решётка", "high"
    if rec in WOOD:
        return "WOOD", "доски", "high"
    if rec in SHEET:
        return "SHEET", SHEET[rec], "medium" if "или" in SHEET[rec] else "high"
    if rec in CONC:
        return "CONC", "бетонная плита", "medium"
    if rec in HATCH:
        return "HATCH", "люк", "high"
    if rec in LIFT:
        return "LIFT", "площадка лифта", "high"
    if rec in ODD:
        return "INTERIOR", ODD[rec], "low"
    return "INTERIOR", "внутренний пол", "medium"


NATURAL = ("CANYON", "CAVES", "CATACOMBS", "NINJA_BASE_2", "STORMMOUNTAIN", "MOUNTBD", "FORESTWASTE", "MOONBERIA",
           "CITY_OF_THE_DEAD", "NECROPOLIS", "DESERTCOLORADO", "JUNGLETEMPLE")
BASE = ("ABASE", "TEC_BASE", "XBASE", "UAC_BASE", "UBASE", "BLACKBASE", "THULEBASE", "TLETHBASE", "GUILDBASE",
        "GOVT_BASE", "NINJA_BASE_1")


def family(t):
    if t.startswith(NATURAL):
        return "NATURAL"
    if t.startswith(BASE):
        return "BASE"
    if t == "WHITE_CASTLE":
        return "CASTLE"
    return "HOUSE"


GEO_RU = {"M": "на массиве или стене-блоке", "C": "на столбе", "O": "над пустотой без стен",
          "E": "над пустотой, у края стена", "R": "над помещением (стены по краю)", "F": "над помещением без стен по краю",
          "S": "пролёт между стенами над залом"}


def solid(blk, lo, xy):
    o = lo["o"].get(xy)
    return o is not None and (blk.parts[o].get("role") or blk.parts[o]["cls"]).lower() in ("mass", "wall")


def spans(blk, lo, x, y, box):
    """Пустая снизу клетка между стенами этажа ниже с двух противоположных сторон (двухсветный зал, пролёт)."""
    x0, x1, y0, y1 = box
    def scan(step, axis):
        cx, cy = x, y
        while x0 - 1 <= cx <= x1 + 1 and y0 - 1 <= cy <= y1 + 1:
            if axis == "x":
                if lo["w"].get((cx + (1 if step > 0 else 0), cy)) is not None or solid(blk, lo, (cx + step, cy)):
                    return True
                cx += step
            else:
                if lo["n"].get((cx, cy + (1 if step > 0 else 0))) is not None or solid(blk, lo, (cx, cy + step)):
                    return True
                cy += step
        return False
    return (scan(-1, "x") and scan(1, "x")) or (scan(-1, "y") and scan(1, "y"))


def cell_geo(blk, z, x, y, box):
    lo = blk.lv[z - 1]
    o, f = lo["o"].get((x, y)), lo["f"].get((x, y))
    walls = [lo["w"].get((x, y)), lo["n"].get((x, y)), lo["w"].get((x + 1, y)), lo["n"].get((x, y + 1))]
    nw = sum(1 for w in walls if w is not None)
    if o is not None:
        r = (blk.parts[o].get("role") or blk.parts[o]["cls"]).lower()
        if r in ("mass", "wall"):
            return "M"
        if r in ("column", "truss"):
            return "C"
    if o is None and f is None:
        if spans(blk, lo, x, y, box):
            return "S"
        return "E" if nw else "O"
    return "R" if nw else "F"


roles = V.load_roles()
with open("census/collapse/review0k/units.tsv", encoding="utf-8-sig") as fh:
    fh.readline()
    ref = [ln.rstrip("\n").split("\t") for ln in fh if ln.strip()]
rows = []
GEODUMP = {}
n = 0
blocks_conc = collections.defaultdict(bool)
units = []
for (tn, bn), blk in sorted(CT.buildings().items()):
    V.apply_roles(blk, roles)
    for j, (z, fl, ro) in enumerate(CT.units(blk)):
        n += 1
        uid = "U-%03d" % n
        r0 = ref[n - 1]
        assert r0[0] == uid and r0[1] == tn and r0[2] == bn, (uid, r0[:3], tn, bn)
        rc = collections.Counter("%s:%d" % (blk.parts[k]["set"].upper(), blk.parts[k]["idx"]) for k in fl + ro)
        if any(material(r)[0] == "CONC" for r in rc):
            blocks_conc[(tn, bn)] = True
        units.append((uid, tn, bn, blk, z, fl, ro, rc))

for uid, tn, bn, blk, z, fl, ro, rc in units:
    cells = sorted({(k[1], k[2]) for k in fl + ro})
    N = len(cells)
    box = (min(c[0] for c in cells), max(c[0] for c in cells), min(c[1] for c in cells), max(c[1] for c in cells))
    geo = {c: cell_geo(blk, z, c[0], c[1], box) for c in cells}
    gc = collections.Counter(geo.values())
    mc = collections.Counter()
    mdesc, mconf = {}, {}
    for r, cnt in rc.items():
        m, d, cf = material(r)
        mc[m] += cnt
        mdesc.setdefault(m, (r, d, cf))
    mat = mc.most_common(1)[0][0]
    mshare = mc[mat] / sum(mc.values())
    rec0, mtext, mcf = mdesc[mat]
    fam = family(tn)
    fM = gc["M"] / N
    fC = gc["C"] / N
    fOpen = (gc["O"] + gc["E"]) / N
    fRoom = (gc["R"] + gc["F"] + gc["S"]) / N
    conf = "medium"
    why = []
    dispute = []
    if gc["S"]:
        why.append("%d клеток - пролёт между стенами над залом без пола ниже" % gc["S"])
    if fM >= 0.6 and mat not in ("WOOD", "SHEET", "GRATE"):
        typ = "MASS"
        conf = "high" if mat == "GROUND" and mcf == "high" else "medium"
        why.append("%d из %d клеток стоят на массиве или стене-блоке; материал: %s" % (gc["M"], N, mtext))
    elif fOpen >= 0.5 and mat == "GRATE":
        typ = "LIGHT_DECK"
        conf = "medium" if gc["C"] else "low"
        why.append("решётка (%s), под %d из %d клеток пусто%s" % (rec0, gc["O"] + gc["E"], N,
                   ", на стойках (%d)" % gc["C"] if gc["C"] else ", стоек нет"))
        if not gc["C"]:
            dispute.append("решётка над пустотой без стоек: мостки на консоли?")
    elif fOpen >= 0.5:
        if gc["C"]:
            typ = "CANOPY_POSTS"
            why.append("под %d из %d клеток пусто, есть стойки (%d); материал: %s" % (
                gc["O"] + gc["E"], N, gc["C"], mtext))
        elif gc["E"] or gc["R"] or gc["M"] or gc["F"] or gc["S"]:
            typ = "CANTILEVER"
            why.append("под %d из %d клеток пусто, опора только с края (стены/массив/помещение у %d клеток); "
                       "материал: %s" % (gc["O"] + gc["E"], N, gc["E"] + gc["R"] + gc["M"] + gc["F"] + gc["S"], mtext))
        else:
            typ = "UNKNOWN"
            why.append("под всеми клетками пусто, стен и стоек нет - опора за пределами участка; материал: %s" % mtext)
        conf = "low"
        dispute.append("открыто снизу: консоль, навес, мост или свод - по срезу не различить")
    elif mat == "GROUND" and (fam in ("NATURAL", "CASTLE") or fM >= 0.3):
        typ = "MASS"
        conf = "medium"
        why.append("материал - %s (%s), под клетками: %s" % (mtext, rec0, ", ".join(
            "%s %d" % (GEO_RU[g], c) for g, c in gc.most_common())))
        if fRoom >= 0.5:
            why.append("под грунтом полость - свод скалы над пещерой/помещением")
        if mcf == "low":
            conf = "low"
            dispute.append("материал по кадру неясен: " + mtext)
    elif mat == "GROUND":
        typ = "HEAVY_SLAB"
        conf = "low"
        why.append("пол цвета грунта (%s, %s) над помещением, массива под ним нет" % (rec0, mtext))
        dispute.append("грунт над помещением не в природной карте: глинобитная плита или насыпь")
    elif mat == "GRATE":
        typ = "LIGHT_DECK"
        conf = "medium"
        why.append("материал - решётка (%s)" % rec0)
        if fM >= 0.6:
            why.append("лежит на массиве (%d из %d клеток)" % (gc["M"], N))
        elif N >= 40 and (gc["R"] + gc["M"]) / N >= 0.5:
            dispute.append("решётка %d клеток на стенах - кровля/перекрытие модуля, а не мостки" % N)
            conf = "low"
    elif mat in ("WOOD", "SHEET"):
        typ = "FRAMED"
        conf = "high" if fam == "HOUSE" and mcf == "high" else "medium"
        why.append("материал - %s (%s); под клетками помещение" % (mtext, rec0))
        if fM >= 0.6:
            why.append("лежит на стенах-блоках (%d из %d клеток)" % (gc["M"], N))
        if mcf != "high":
            dispute.append("материал по кадру неясен: " + mtext)
    elif mat == "CONC":
        typ = "HEAVY_SLAB"
        why.append("материал - %s (%s) на стенах" % (mtext, rec0))
    elif mat in ("HATCH", "LIFT"):
        typ = "UNKNOWN"
        conf = "low"
        why.append("участок - %s (%s): устройство задаёт окружение" % (mtext, rec0))
        dispute.append("одиночный люк/лифт")
    else:  # INTERIOR
        if fam in ("BASE", "CASTLE"):
            typ = "HEAVY_SLAB"
            why.append("внутренний пол %s (%s); база/замок - плита на стенах" % (rec0, mtext))
        elif fam == "NATURAL":
            typ = "HEAVY_SLAB"
            conf = "low"
            why.append("внутренний пол %s в природной карте (храм/катакомбы): каменная плита?" % rec0)
            dispute.append("каменный пол над полостью: плита или свод (ARCH)")
        elif blocks_conc[(tn, bn)]:
            typ = "HEAVY_SLAB"
            conf = "low"
            why.append("внутренний пол %s; у здания бетонная кровля - бетонные перекрытия?" % rec0)
        else:
            typ = "FRAMED"
            why.append("внутренний пол %s жилого здания - обычный дом" % rec0)
        if mcf == "low":
            conf = "low"
            dispute.append("материал по кадру неясен: " + mtext)
    # смешанное устройство: меньшая часть клеток устроена иначе
    major = {"MASS": "M", "CANOPY_POSTS": "OEC", "CANTILEVER": "OE", "UNKNOWN": "O"}.get(typ, "RFMS")
    other = [c for c in cells if geo[c] not in major]
    note2 = ""
    if typ in ("MASS",) and len(other) >= max(3, 0.25 * N):
        note2 = "иначе: %d клеток не на массиве (%s), напр. %s" % (len(other), ", ".join(
            "%s %d" % (GEO_RU[g], c) for g, c in collections.Counter(geo[c] for c in other).most_common()),
            " ".join("f:%d:%d:%d" % (x, y, z) for x, y in other[:4]))
    elif typ in ("FRAMED", "HEAVY_SLAB", "LIGHT_DECK"):
        op = [c for c in cells if geo[c] in "OE"]
        if len(op) >= max(3, 0.2 * N):
            note2 = "иначе: %d клеток над пустотой (консоль/навес?), напр. %s" % (
                len(op), " ".join("f:%d:%d:%d" % (x, y, z) for x, y in op[:4]))
            if len(op) >= 0.35 * N and not (typ == "LIGHT_DECK" and gc["C"]):
                dispute.append("большая часть над пустотой")
                conf = "low" if conf == "medium" else conf
    if mshare < 0.6 and len(mc) > 1:
        why.append("материалы смешаны: " + ", ".join("%s %d" % (m, c) for m, c in mc.most_common()))
        if conf == "high":
            conf = "medium"
    if typ == "UNKNOWN" and not dispute:
        dispute.append("UNKNOWN")
    if uid in MANUAL:
        typ, conf, mreason = MANUAL[uid]
        why.insert(0, "решение исполнителя по срезу и кадру: " + mreason)
        dispute = []
    elif uid in ASK:
        dispute = [ASK[uid]]
        conf = "low"
    elif dispute:
        raise SystemExit("спорный участок без решения и без вопроса: %s %s" % (uid, "; ".join(dispute)))
    imgs = " ".join("frames/%s_%s.png" % tuple(r.split(":")) for r, _ in rc.most_common(3))
    gname = "geom/%s__%s.txt" % (tn, bn.replace("@", "_at_").replace(",", "_"))
    assert os.path.exists("census/collapse/review0k/" + gname), gname
    for im in imgs.split():
        assert os.path.exists("census/collapse/review0k/" + im), im
    GEODUMP[uid] = {"z": z, "terrain": tn, "block": bn, "cells": [[x, y, geo[(x, y)]] for x, y in cells]}
    rows.append([uid, typ, conf, "; ".join(why + ([note2] if note2 else [])), imgs + " " + gname,
                 "; ".join(dispute), mat, " ".join("%s:%d" % kv for kv in gc.most_common())])

with open(OUT, "w", encoding="utf-8-sig") as fh:
    fh.write("id\ttype\tconfidence\treason\timage\tdispute\tmaterial\tcells_below\n")
    for r in rows:
        fh.write("\t".join(str(x) for x in r) + "\n")
import json
with open("census/collapse/stage0l/ctype_geo.json", "w", encoding="utf-8-sig") as fh:
    json.dump(GEODUMP, fh, ensure_ascii=False)
print(len(rows), collections.Counter(r[1] for r in rows), collections.Counter(r[2] for r in rows),
      "спорных", sum(1 for r in rows if r[5]))
