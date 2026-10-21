#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Модель M0j5 обрушения = M0j4 (collapse_v7d, разметка v2) плюс передача устойчивости по связям.
M0j4 и всё под её замками не меняются - M0j5 живёт только здесь (решение 2026-10-21, слово Vitali).

Зачем: в M0j4 плита пола держится только в пределах пролёта от опоры снизу (R-353), стена и предмет - только на
несущем под собой. На целых зданиях из-за этого «висят» углы кровли, полы дальше 3-4 клеток от стены и то, что
стоит на них: 162 пары п. 9 (docs/research/building-collapse-ideas-2026-10-19.md) нельзя включить, а v2 («пролёт
относительно целого», 20.10) отвергнута - она меняла исход замкнутых сценариев уже включённых зданий.

Слой M0j5 (поверх M0j4; части деревьев - вне слоя):
  * связи направленные, по пути нагрузки - «p держит q»: пол держит соседний пол, стены на своих краях и предмет
    своей клетки; несущая стена - пол над собой по обе стороны, стены с общим концом, ту же стену этажом выше и
    предметы по обе стороны; несущий предмет - пол и предмет над собой, соседний предмет и стены своей клетки.
    Не несущая стена и не несущий предмет (мебель, декор, ограда) не держат ничего: стол под полом пол не держит;
  * U0 - части выше z0, которые M0j4 НЕ держит на целом блоке; d0(p) - число связей от держащегося на целом до p
    по U0. Часть U0 без пути висит и на целом (такой блок в выгрузку не идёт). После разрушения часть U0
    держится, если до неё дошли не длиннее d0 + SU;
  * перераспределение: часть, которую M0j4 держит на целом, а при снятых роняет, держится, если до неё не длиннее
    SC связей и уровнем ниже стоит несущая часть, касающаяся клетки не дальше SD (по Чебышёву) - нагрузка уходит на
    оставшиеся опоры; дальше SD от стоящих опор - консоль в 3 клетки и больше, падает (как ожидание PFALL);
  * путь идёт от частей, которые держатся, через части, которым держаться разрешено, снятые не проходятся; затем
    разметка v2 (SURFACE/ATTACHED держатся, пока держится цель).
Перепрогон всех партий 21.10: 100 сценариев FAIL -> PASS, обратно - только 3 частичных с недопадом (DECISIONS).

    py -3.13 tools\collapse_v8.py lock      замок M0j5 (census/collapse/pilot3/m0j5.lock.txt)
Другие инструменты переводятся на M0j5 вызовом install(): collapse_v7c.evaluate7c в этом процессе считает M0j5.
"""
import collections
import os
import sys
import time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_v6 as M                           # noqa: E402
import collapse_v7c as C7                         # noqa: E402
import collapse_v7d as D                          # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/pilot3"
LOCK = OUT + "/m0j5.lock.txt"
NAME = "M0j5"
LOCKED = ["tools/collapse_v8.py"]
BASE = None                                       # evaluate7c M0j4 (после D.install), задаётся install()
SU = 2                                            # запас пути для части U0 сверх d0, связей
SC = 3                                            # перераспределение: путь до части, которую ядро держало на целом
SD = 2                                            # опора: стоящая несущая часть уровнем ниже касается клетки не дальше SD


# ------------------------------------------------------------------ связи

def carries(k, bearing):
    """Части, которые часть k держит (ключи; есть ли они в блоке - решает вызывающий). Устойчивость идёт по пути
    нагрузки: пол держит соседний пол, стены на своих краях и предмет своей клетки; несущая стена - пол над собой
    по обе стороны, стены с общим концом, ту же стену этажом выше и предметы клеток по обе стороны; несущий
    предмет - пол над собой, предмет над собой, соседний предмет и стены своей клетки. Не несущая стена и не
    несущий предмет (мебель, декор, ограда) не держат ничего: стол под полом пол не держит."""
    s, x, y, z = k
    if s == "f":
        return [("f", x + 1, y, z), ("f", x - 1, y, z), ("f", x, y + 1, z), ("f", x, y - 1, z),
                ("w", x, y, z), ("w", x + 1, y, z), ("n", x, y, z), ("n", x, y + 1, z), ("o", x, y, z)]
    if not bearing:
        return []
    if s == "o":
        return [("f", x, y, z + 1), ("o", x, y, z + 1),
                ("o", x + 1, y, z), ("o", x - 1, y, z), ("o", x, y + 1, z), ("o", x, y - 1, z),
                ("w", x, y, z), ("w", x + 1, y, z), ("n", x, y, z), ("n", x, y + 1, z)]
    if s == "w":                                  # западная стена клетки (x, y): клетки (x, y) и (x-1, y), концы (x, y) и (x, y+1)
        out = [("f", x, y, z + 1), ("f", x - 1, y, z + 1), ("o", x, y, z), ("o", x - 1, y, z)]
        ends = ((x, y), (x, y + 1))
    else:                                         # северная стена клетки (x, y): клетки (x, y) и (x, y-1), концы (x, y) и (x+1, y)
        out = [("f", x, y, z + 1), ("f", x, y - 1, z + 1), ("o", x, y, z), ("o", x, y - 1, z)]
        ends = ((x, y), (x + 1, y))
    for cx, cy in ends:                           # стены с этим концом: w (cx, cy-1), (cx, cy); n (cx-1, cy), (cx, cy)
        for q in (("w", cx, cy - 1, z), ("w", cx, cy, z), ("n", cx - 1, cy, z), ("n", cx, cy, z)):
            if q != k:
                out.append(q)
    out.append((s, x, y, z + 1))
    return out


def touch(k):
    """Клетки, которых касается часть: пол и предмет - своей, стена w - своей и западной, n - своей и северной."""
    s, x, y, z = k
    if s == "w":
        return ((x, y), (x - 1, y))
    if s == "n":
        return ((x, y), (x, y - 1))
    return ((x, y),)


def graph(keys, bearing):
    """Связи внутри множества ключей: {k: [что k держит]}."""
    ks = set(keys)
    return {k: [q for q in carries(k, k in bearing) if q in ks] for k in ks}


def intact_layer(blk, held0):
    """По целому блоку: части деревьев (вне слоя), связи без них, U0 и d0, опоры каждой части, которую держит ядро."""
    import collapse_v2 as V
    import collapse_v3 as T
    import collapse_v5 as H
    f2 = "".join(c for c in C7.MODEL if c not in T.V3_FLAGS).replace("V", "")
    with C7.marked_roles(blk):
        cls = {k: V.eff_cls(k, p, f2) for k, p in blk.parts.items()}
        role = {k: p.get("role", "") for k, p in blk.parts.items()}
        cols, crowns = H.tree_structure5(blk, cls, role)
    tree = {k for st in cols.values() for k in st} | set(crowns)
    keys = [k for k in blk.parts if k not in tree]
    bearing = {k for k in keys if cls[k] in V.BEARING}
    adj = graph(keys, bearing)
    u0 = {k for k in keys if k[3] > 0 and k not in held0}
    anchors = [k for k in keys if k in held0]
    d0 = bfs(adj, {k: 1 << 30 for k in u0}, anchors, frozenset())
    bear = collections.defaultdict(list)
    for k in keys:
        if k in held0 and k in bearing:
            bear[k[3]].append(k)
    sup = {}                                      # опоры части: несущие уровнем ниже, касаются клетки не дальше SD
    for k in keys:
        if k[3] > 0 and k in held0:
            sup[k] = [q for q in bear[k[3] - 1] if any(max(abs(a - c), abs(b - d)) <= SD
                                                       for a, b in touch(k) for c, d in touch(q))]
    tg = {k: [q for q in ts] for k, (kind, ts) in C7.marked_parts(blk).items() if ts and k not in tree}
    return dict(tree=frozenset(tree), adj=adj, u0=frozenset(u0), d0=d0, sup=sup, marks=tg,
                held0=frozenset(held0))


def bfs(adj, budget, sources, removed):
    """Расстояния по связям от источников до частей с бюджетом: часть берётся, если путь до неё не длиннее её
    бюджета; идут только через взятые части, снятые не проходятся."""
    dist = {}
    q = deque()
    for a in sources:
        for k in adj[a]:
            if k in budget and k not in removed and k not in dist and budget[k] >= 1:
                dist[k] = 1
                q.append(k)
    while q:
        k = q.popleft()
        for n in adj[k]:
            if n in budget and n not in removed and n not in dist and budget[n] >= dist[k] + 1:
                dist[n] = dist[k] + 1
                q.append(n)
    return dist


def layer(blk):
    lay = getattr(blk, "_m0j5", None)
    if lay is None:
        held0 = BASE(blk, frozenset())[0]
        lay = intact_layer(blk, set(held0))
        blk._m0j5 = lay
    return lay


def evaluate8(blk, removed=frozenset(), flags=C7.MODEL, tie="all"):
    """M0j5: M0j4 и слой связей (U0 по d0, перераспределение на стоящие опоры), затем разметка по своим целям."""
    removed = frozenset(removed)
    held, info = BASE(blk, removed, flags, tie)
    lay = layer(blk)
    held = set(held)
    budget = {}
    for k in lay["u0"]:
        if k in lay["d0"]:
            budget[k] = lay["d0"][k] + SU
    for k, sp in lay["sup"].items():
        if k not in held and any(q not in removed for q in sp):
            budget[k] = SC
    if not budget:
        return held, info
    src = [a for a in held if a not in removed and a not in lay["tree"] and a in lay["adj"]]
    got = bfs(lay["adj"], budget, src, removed)
    if not got:
        return held, info
    held |= set(got)
    changed = True
    while changed:                                # разметка: SURFACE/ATTACHED держатся, пока держится цель
        changed = False
        for k, ts in lay["marks"].items():
            if k not in held and k not in removed and any(q in held and q not in removed for q in ts):
                held.add(k)
                changed = True
    return held, info


def hanging(blk):
    """Что висит на целом блоке и под M0j5 (части U0 без пути к держащемуся)."""
    lay = layer(blk)
    return sorted(k for k in lay["u0"] if k not in lay["d0"])


def install():
    """С этого момента collapse_v7c.evaluate7c (и всё, что её зовёт) считает M0j5. Разметка - v2, ядро - M0j4."""
    global BASE
    check_lock()
    C = D.install()
    if C.evaluate7c is not evaluate8:
        BASE = C.evaluate7c
        C.evaluate7c = evaluate8
    return C


# ------------------------------------------------------------------ замок

def check_lock():
    D.check_lock()
    if not os.path.exists(LOCK):
        return                                    # до первого замка - проба
    lock = {}
    with open(LOCK, encoding=ENC) as f:
        for line in f:
            p = line.rstrip("\n").split(" sha256 ")
            if len(p) == 2:
                lock[p[0]] = p[1]
    bad = [p for p in LOCKED if lock.get(p) != M.sha(p)]
    if bad:
        raise SystemExit("замок M0j5 нарушен: " + ", ".join(bad))


def cmd_lock():
    D.check_lock()
    lines = ["версия модели M0j5 обрушения, записано %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "M0j4 (collapse_v7d) без изменений плюс слой направленных связей по пути нагрузки: U0 по d0+%d, "
             "перераспределение SC %d при стоящей опоре не дальше SD %d; решение DECISIONS 2026-10-21" % (SU, SC, SD)]
    lines += ["%s sha256 %s" % (p, M.sha(p)) for p in LOCKED]
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    {"lock": cmd_lock}[sys.argv[1]]()
