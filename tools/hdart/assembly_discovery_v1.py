#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ASSEMBLY_DISCOVERY_V1 - составной по повторяющейся сборке клеток (специалист 02.10, RELATION_DISCOVERY_V5_PREP).
CPU, чтение. Общий детектор: исключений по наборам нет; P3L/P3Lx V4 остаются как есть и не правятся.

P3L смотрит одного соседа на одном сдвиге (±1) и долю встречи в слое. Здесь по каждому месту кадра строится
локальный граф клеток (окно ASM_R по x/y, ASM_DZ по этажу), и ищется сборка, повторяющаяся по местам:

  узлы - (сдвиг от кадра, слот клетки, кадр); слот по формату MAP: 0 пол, 1 западная стена, 2 северная стена,
         3 предмет;
  рёбра - соседство в своей модели:
    OBJECT (слот 3): соседняя по грани клетка (x, y, этаж) с предметом - след из нескольких клеток;
    WALL (слоты 1 и 2): продолжение по оси стены (западная - по y, северная - по x), стык концов
                        западной и северной стены, этаж выше и ниже в том же слоте;
    FLOOR (слот 0): соседний по грани пол того же этажа - общий след / узор плиток;
  ребро «одна занятая конструкция» - воксели LOFT продолжаются через общую грань (v3.contact >= CONTACT).

Экземпляр сборки - связная часть графа вокруг кадра в окне. Ядро сборки кадра a в слоте s - узлы, которые есть
не меньше чем в ASM_REPEAT местах и не меньше чем в доле ASM_CORE мест a в этом слоте. Партнёр b годен, только если
стоит в ядре ровно на одном сдвиге (несколько сдвигов - узор плитки или модуль, не сборка). Сборку восстанавливаем
и со стороны b: a обязан быть в ядре b на обратном сдвиге (взаимность). Без взаимности довода нет - одностороннее
примыкание остаётся ATTACHMENT_CANDIDATE замороженного V4.

Уровни (довод COMPOSITE_PART, детектор ASM):
  OBJECT  AO  STRONG     - сборка повторяется у обоих (мест >= 2), взаимна, путь от a до b в ядре по рёбрам
                           одной конструкции, мест ядра не меньше чем в ASM_BLOCKS блоках;
          AOc CANDIDATE  - повторяется и взаимна, без конструкции или блоков;
          AOs CANDIDATE  - одно место у a или b: взаимна в этом месте, путь по конструкции и порядок номеров;
  WALL    AW  STRONG     - как AO, плюс порядок номеров или тот же строительный класс MCD;
          AWc, AWs       - как у OBJECT;
  FLOOR   AF  STRONG     - повторяется, взаимна, порядок номеров И тот же класс MCD, блоков >= ASM_BLOCKS
                           (касание вокселей у полов есть всегда и не доказывает ничего);
          AFc CANDIDATE  - повторяется и взаимна; одиночного довода для пола нет.
Параметры записаны в spec.json V5_PREP до диагностического пересчёта.
"""
import os
import sys
from collections import Counter, defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402

DETECTOR = "ASM"
TYPE = "COMPOSITE_PART"
ASM_R = 2                       # окно 5x5 клеток: машина 3x2 видна целиком из любой своей клетки
ASM_DZ = 1                      # этаж выше и ниже
ASM_REPEAT = 2                  # сборка повторяется - не меньше двух мест
ASM_CORE = 0.75                 # узел ядра - в стольких местах кадра; одно отличное место из четырёх допустимо
ASM_BLOCKS = v2.CO_BLOCKS       # 2 - STRONG только когда ядро встречается на разных картах
CONTACT = v3.CONTACT            # 0.5 - воксели продолжаются через грань
ORDER_REACH = v3.ORDER_REACH    # 6 - порядок номеров в наборе
MODEL = {0: "FLOOR", 1: "WALL", 2: "WALL", 3: "OBJECT"}
PARAMS = {"ASM_R": ASM_R, "ASM_DZ": ASM_DZ, "ASM_REPEAT": ASM_REPEAT, "ASM_CORE": ASM_CORE,
          "ASM_BLOCKS": ASM_BLOCKS, "CONTACT": CONTACT, "ORDER_REACH": ORDER_REACH, "MODEL": MODEL,
          "partner": "ровно один сдвиг в ядре", "mutual": "обязательна, иначе довода нет"}

# ходы графа: слот -> [(сдвиг, слот соседа)]
MOVES = {
    3: [((1, 0, 0), 3), ((-1, 0, 0), 3), ((0, 1, 0), 3), ((0, -1, 0), 3), ((0, 0, 1), 3), ((0, 0, -1), 3)],
    # западная стена (x, y): отрезок от точки (x, y) до (x, y + 1)
    1: [((0, -1, 0), 1), ((0, 1, 0), 1), ((0, 0, 0), 2), ((-1, 0, 0), 2), ((0, 1, 0), 2), ((-1, 1, 0), 2),
        ((0, 0, 1), 1), ((0, 0, -1), 1)],
    # северная стена (x, y): отрезок от точки (x, y) до (x + 1, y)
    2: [((-1, 0, 0), 2), ((1, 0, 0), 2), ((0, 0, 0), 1), ((0, -1, 0), 1), ((1, 0, 0), 1), ((1, -1, 0), 1),
        ((0, 0, 1), 2), ((0, 0, -1), 2)],
    0: [((1, 0, 0), 0), ((-1, 0, 0), 0), ((0, 1, 0), 0), ((0, -1, 0), 0)],
}


def add(o, d):
    return (o[0] + d[0], o[1] + d[1], o[2] + d[2])


def neg(o):
    return (-o[0], -o[1], -o[2])


def in_window(o):
    return abs(o[0]) <= ASM_R and abs(o[1]) <= ASM_R and abs(o[2]) <= ASM_DZ


def at(grid, pos, slot):
    for la, k in grid.get(pos, []):
        if la == slot:
            return k
    return None


def instance(grid, xyz, slot, A):
    """Экземпляр сборки в одном месте: {(сдвиг, слот): кадр} связной части вокруг (0, 0, 0, slot) в окне."""
    seen = {((0, 0, 0), slot): A}
    q = deque([((0, 0, 0), slot)])
    while q:
        o, s = q.popleft()
        for d, s2 in MOVES[s]:
            o2 = add(o, d)
            if not in_window(o2) or (o2, s2) in seen:
                continue
            k = at(grid, add(xyz, o2), s2)
            if k is None:
                continue
            seen[(o2, s2)] = k
            q.append((o2, s2))
    return seen


class Assembly:
    """Ядра сборок кадров по слотам (с кэшем) и рёбра конструкции по MCD."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.cache = {}
        self.cc = {}

    def places(self, k, slot):
        return [(t, b, g, xyz) for t, b, g, xyz, la in self.ctx.places.of(k) if la == slot]

    def core(self, k, slot):
        """-> {"n", "blocks", "members": {(сдвиг, слот, кадр): (мест, блоков)}, "single"}; узел ядра - по правилу."""
        kk = (k.upper(), slot)
        if kk in self.cache:
            return self.cache[kk]
        A = k.upper()
        pl = self.places(A, slot)
        rec, blk = Counter(), defaultdict(set)
        for _t, b, g, xyz in pl:
            for (o, s), kb in instance(g, xyz, slot, A).items():
                if kb == A:
                    continue
                rec[(o, s, kb)] += 1
                blk[(o, s, kb)].add(b)
        n = len(pl)
        need = max(ASM_REPEAT, ASM_CORE * n) if n >= ASM_REPEAT else 1
        mem = {m: (c, len(blk[m])) for m, c in rec.items() if c >= need}
        r = {"n": n, "blocks": len({b for _t, b, _g, _x in pl}), "members": mem, "single": n < ASM_REPEAT}
        self.cache[kk] = r
        return r

    def contact(self, a, b, o):
        kk = (a, b, o)
        if kk not in self.cc:
            ia, ib = self.ctx.info(a), self.ctx.info(b)
            c = v3.contact(ia["vox"], ib["vox"], o) if ia.get("rec") and ib.get("rec") else None
            self.cc[kk] = c
        return self.cc[kk]

    def struct_path(self, A, slot, core, target):
        """Путь от кадра до target = (сдвиг, слот) по узлам ядра, каждое ребро - одна конструкция (касание вокселей)."""
        nodes = {((0, 0, 0), slot): A}
        nodes.update({(o, s): kb for (o, s, kb) in core["members"]})
        seen = {((0, 0, 0), slot)}
        q = deque(seen)
        while q:
            o, s = q.popleft()
            if (o, s) == target:
                return True
            for d, s2 in MOVES[s]:
                o2 = add(o, d)
                if (o2, s2) in seen or (o2, s2) not in nodes:
                    continue
                c = self.contact(nodes[(o, s)], nodes[(o2, s2)], d)
                if c is not None and c >= CONTACT:
                    seen.add((o2, s2))
                    q.append((o2, s2))
        return False


def order(a, b):
    (sa, fa), (sb, fb) = v2.split(a), v2.split(b)
    return sa == sb and 0 < abs(fa - fb) <= ORDER_REACH


def same_mcd(ctx, a, b):
    ca, cb = v3.struct_class(ctx.info(a)), v3.struct_class(ctx.info(b))
    return ca is not None and ca == cb


def partners(core):
    """b -> (сдвиг, слот), если b в ядре ровно на одном сдвиге; несколько сдвигов - узор, не сборка."""
    by = defaultdict(list)
    for (o, s, kb) in core["members"]:
        by[kb].append((o, s))
    return {kb: v[0] for kb, v in by.items() if len(v) == 1}


def judge(asm, a, slot, b, o, sb):
    """Довод на паре (a в слоте slot, b на сдвиге o в слоте sb) или None; уже известно, что b - партнёр ядра a."""
    ctx = asm.ctx
    A, B = a.upper(), b.upper()
    ca, cb = asm.core(A, slot), asm.core(B, sb)
    back = partners(cb).get(A)
    if back != (neg(o), slot):
        return None                                   # нет взаимности - не сборка
    model = MODEL[slot]
    if MODEL[sb] != model:
        return None
    st = asm.struct_path(A, slot, ca, (o, sb)) if model != "FLOOR" else False
    od, mc = order(A, B), same_mcd(ctx, A, B)
    ma, mb = ca["members"][(o, sb, B)], cb["members"][(neg(o), slot, A)]
    blocks = min(ma[1], mb[1])
    single = ca["single"] or cb["single"]
    pfx = {"OBJECT": "AO", "WALL": "AW", "FLOOR": "AF"}[model]
    if single:
        if model == "FLOOR" or not (st and od):
            return None
        level, rule = "CANDIDATE", pfx + "s"
    elif model == "OBJECT" and st and blocks >= ASM_BLOCKS:
        level, rule = "STRONG", pfx
    elif model == "WALL" and st and (od or mc) and blocks >= ASM_BLOCKS:
        level, rule = "STRONG", pfx
    elif model == "FLOOR" and od and mc and blocks >= ASM_BLOCKS:
        level, rule = "STRONG", pfx
    else:
        level, rule = "CANDIDATE", pfx + "c"
    e = v2.edge(TYPE, A, B, level, DETECTOR, rule,
                "%s, сдвиг %s, слоты %d/%d: в ядре a %d из %d мест (%d блоков), в ядре b %d из %d (%d блоков); "
                "конструкция %s, порядок %s, класс MCD %s%s" % (
                    model, list(o), slot, sb, ma[0], ca["n"], ma[1], mb[0], cb["n"], mb[1],
                    "да" if st else ("-" if model == "FLOOR" else "нет"), "да" if od else "нет",
                    "тот же" if mc else "другой", "; одно место" if single else ""))
    e["scores"] = {"model": model, "offset": list(o), "slots": [slot, sb], "a": [ma[0], ca["n"], ma[1]],
                   "b": [mb[0], cb["n"], mb[1]], "struct": st, "order": od, "mcd": mc, "single": single,
                   "core_a": len(ca["members"]), "core_b": len(cb["members"])}
    return e


def discover(asm, a, only=None):
    """Доводы ASM кадра a по всем его слотам; only - одна пара (контроль)."""
    A = a.upper()
    out = []
    for slot in sorted({la for _t, _b, _g, _x, la in asm.ctx.places.of(A)}):
        core = asm.core(A, slot)
        for b, (o, sb) in sorted(partners(core).items()):
            if only is not None and b != only.upper():
                continue
            e = judge(asm, A, slot, b, o, sb)
            if e:
                out.append(e)
    return out
