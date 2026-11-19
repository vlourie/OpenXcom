#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0g обрушения зданий: версия модели M0g поверх M0f (collapse_v3). Движок не трогается, M0f не меняется.

Рецензия этапа 0f: одна исправленная версия и её проверка, итоги PASS / FAIL / UNSUPPORTED раздельно.
Отчёт - docs/research/building-collapse-stage0g-2026-10-07.md, данные - census/collapse/stage0g.

Отличия M0g от M0f (флаги M0f плюс Y; без Y и при tie="all" evaluate4 = collapse_v3.evaluate3 бит в бит):
  Y - перемычка по проёму, заданному зданием. Правило I держит ряд несущих стен без несущей под собой,
      если он с обеих сторон упирается в несущую стену той же линии на опоре (как M0f). M0g добавляет
      признак: такой ряд держится, только если в ЦЕЛОМ блоке на этом месте был такой же ряд - проём,
      заданный зданием, длиной до LINTEL, - и сейчас ряд не длиннее заданного. Это и есть рама:
      перемычка плюс простенки, на которые она опирается в целом здании.
      - дверь не несущая и в признак не входит: снята дверь - проём тот же, перемычка стоит;
      - снят простенок (или стена под ним) - ряд тянется до следующей опоры, длиннее заданного - не держится;
      - проём, сделанный разрушением (снята несущая стена под рядом), заданным не был - перемычки нет.
      На целом блоке Y ничего не меняет: заданный проём - ровно то, что M0f держит перемычкой.
  Судья (Base4), что считается неподдерживаемым сверх M0f:
    общая крона - кусок кроны, привязанный к двум и больше стволам. Модель (как M0f) роняет его при
      потере любого из стволов; это не обосновано. Если исход сценария зависит от выбора «все стволы»
      против «любой ствол» - UNSUPPORTED «общая крона». Сам случай - отдельные ожидания.
    граница здания (на собранной карте) - связь через границу здания не обрывается: модель считает всю
      карту. Если исход частей здания в зоне (или судимых частей) меняется, когда всё вне здания снято,
      или упало что-то вне здания - UNSUPPORTED: внешняя конструкция не проверена.

    py -3.13 tools\collapse_v4.py selfcheck          M0g без Y = M0f; целые блоки группы 1: M0g = M0f
    py -3.13 tools\collapse_v4.py search             места, где исход после повреждения зависит от S, M, B, Y
    py -3.13 tools\collapse_v4.py pick               сценарии и задание слепому рецензенту
    py -3.13 tools\collapse_v4.py lock               замок M0g (код, данные, ожидания, набор карт)
    py -3.13 tools\collapse_v4.py scen FILE          сценарии по ожиданиям, PASS / FAIL / UNSUPPORTED
    py -3.13 tools\collapse_v4.py dev                ожидания и карты 0f под M0g - материал разработки, не приёмка
    py -3.13 tools\collapse_v4.py holdout2           второй независимый набор карт (stage0g/holdout2.lock.txt)
"""
import collections
import hashlib
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_census as cc                      # noqa: E402
import collapse_v2 as V                           # noqa: E402
import collapse_v3 as T                           # noqa: E402
import collapse_summary as S                      # noqa: E402
import collapse_pilot as P                        # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/stage0g"
LOCK = OUT + "/rules.lock.txt"
M0F = P.MODEL                                     # RUADHSNQIMGOWB
MODEL = M0F + "Y"
CANDIDATE_RULES = "SNQIMBY"                       # Y - отличие M0g от M0f
SEARCH_RULES = "SMBY"                             # рецензия 0f: S, M, B после повреждения не проверены; Y - новое
CODE = ["tools/collapse_census.py", "tools/collapse_v2.py", "tools/collapse_v3.py", "tools/collapse_summary.py",
        "tools/collapse_pilot.py", "tools/collapse_holdout.py", "tools/collapse_holdout2.py", "tools/collapse_v4.py"]
DATA = ["census/collapse/stage0c/roles.tsv", "census/collapse/ships/conn_blocks.tsv",
        "census/collapse/ships/terrain_groups.tsv", "census/collapse/stage0d/tree_offsets.tsv",
        OUT + "/holdout2.lock.txt"]
HOLD2 = "census/collapse/holdout2"
DEV_FILES = ["census/collapse/stage0f/expect_0f_pilot.tsv", "census/collapse/stage0f/expect_0f_trees.tsv"]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ------------------------------------------------------------------ модель M0g

def lintel_runs(live, below, carry, bearing):
    """Как collapse_v2.lintels, но длина ряда для каждой стены, которую ряд держал бы при любом пределе."""
    out = {}
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
            if ok:
                out[key] = run
    return out


def designed(blk, f):
    """Заданные зданием проёмы: стена -> длина ряда на ЦЕЛОМ блоке (до LINTEL). Наибольшая по всем
    прогонам evaluate2 внутри evaluate3, поэтому на целом блоке M0g держит ровно то же, что M0f."""
    cache = blk.__dict__.setdefault("_designed", {})
    if f in cache:
        return cache[f]
    rec = {}

    def recorder(live, below, carry, bearing):
        held = set()
        for key, r in lintel_runs(live, below, carry, bearing).items():
            if r <= V.LINTEL:
                rec[key] = max(rec.get(key, 0), r)
                held.add(key)
        return held

    old = V.lintels
    V.lintels = recorder
    try:
        T.evaluate3(blk, frozenset(), f)
    finally:
        V.lintels = old
    cache[f] = rec
    return rec


def tree_hold4(blk, removed, cls, role, carry, tie="all"):
    """collapse_v3.tree_hold с выбором для куска кроны с несколькими стволами: all - держат все (как M0f),
    any - держит любой уцелевший."""
    cols, crowns = T.tree_structure(blk, cls, role)
    held_to = {}
    held = set()
    for xy, st in cols.items():
        top = -1
        for z, key in enumerate(st):
            if key in removed:
                break
            top = z
            held.add(key)
        held_to[xy] = top

    def on_wall(key):
        k, x, y, z = key
        lv = blk.lv[z]
        walls = [lv["w"].get((x, y)), lv["w"].get((x + 1, y)), lv["n"].get((x, y)), lv["n"].get((x, y + 1))]
        return any(w in carry and w not in removed for w in walls if w)

    managed = {k for st in cols.values() for k in st[1:] if not on_wall(k)}
    pick = all if tie == "all" else any
    for key, (how, cs) in crowns.items():
        if not cs or on_wall(key):
            continue
        managed.add(key)
        if key in removed:
            continue
        need = min(key[3], max(len(cols[c]) - 1 for c in cs))
        if pick(held_to[c] >= need for c in cs):
            held.add(key)
    return managed, held & managed


def evaluate4(blk, removed=frozenset(), flags=MODEL, tie="all"):
    f = flags.replace("Y", "")
    old_l, old_t = V.lintels, T.tree_hold
    T.tree_hold = lambda b, r, c, ro, ca: tree_hold4(b, r, c, ro, ca, tie)
    try:
        if "Y" in flags and "I" in f:
            des = designed(blk, f)
            V.lintels = lambda live, below, carry, bearing: {
                k for k, r in lintel_runs(live, below, carry, bearing).items() if r <= des.get(k, 0)}
        return T.evaluate3(blk, frozenset(removed), f)
    finally:
        V.lintels, T.tree_hold = old_l, old_t


def shared_crowns(blk):
    """Куски кроны с двумя и больше стволами-кандидатами."""
    cls = {key: V.eff_cls(key, p, "RUA") for key, p in blk.parts.items()}
    role = {key: p.get("role", "") for key, p in blk.parts.items()}
    cols, crowns = T.tree_structure(blk, cls, role)
    return {key: cs for key, (how, cs) in crowns.items() if len(cs) > 1}


# ------------------------------------------------------------------ судья

class Base4:
    """Исходное состояние блока или карты: опоры M0g и всё, что нужно судье. foot - клетки (x, y, z) здания на
    карте: связь через его границу не обрывается, но зависимость от внешнего - UNSUPPORTED."""

    def __init__(self, blk, disp, vessel=False, ver=None, foot=None, model=MODEL):
        self.blk, self.disp, self.vessel, self.ver, self.foot, self.model = blk, disp, vessel, ver, foot, model
        self.sup0, info = evaluate4(blk, frozenset(), model)
        self.light = P.light_beam(blk, self.sup0, info)
        self.by_cell = collections.defaultdict(list)
        for key in blk.parts:
            for c in T.part_cells(key):
                self.by_cell[c].append(key)
        self.alt0 = {e: evaluate4(blk, frozenset(), model.replace(e, ""))[0] for e in CANDIDATE_RULES}
        self.any0 = evaluate4(blk, frozenset(), model, tie="any")[0]
        if foot is not None:
            self.set_foot(foot)

    def set_foot(self, foot):
        """Граница здания на карте (клетки места блока). Связь через неё модель не рвёт: ext - всё вне здания,
        iso0 - опоры здания, если бы вне него не было ничего; разница - UNSUPPORTED."""
        # часть принадлежит клетке своих координат, как в файле блока: стена соседа на общей границе (w по
        # западному краю его клетки) - его, а не здания (R-270: навес URBANDIO04 держится стеной URBANDIO03)
        self.foot = foot
        self.ext = frozenset(k for k in self.blk.parts if (k[1], k[2], k[3]) not in foot)
        self.iso0 = evaluate4(self.blk, self.ext, self.model)[0]
        return self

    def fallen_of(self, sup0, sup, removed):
        return {k for k in sup0 if k not in sup and k not in removed and k[3] > 0}

    def judge(self, removed, extra=()):
        blk = self.blk
        removed = frozenset(removed)
        sup, _ = evaluate4(blk, removed, self.model)
        fallen = self.fallen_of(self.sup0, sup, removed)
        ev_cells = {c for k in fallen | removed for c in T.part_cells(k)}
        zone = {k for c in P.near(ev_cells) for k in self.by_cell.get(c, ())}
        look = zone | set(extra)
        why = collections.Counter()
        if self.vessel:
            why["судно"] += 1
        for key in zone:
            u = P.unknown(blk.parts[key], key[0], self.disp)
            if u:
                why[u] += 1
            if key[3] > 0 and key not in self.sup0:
                why["рядом висело до боя"] += 1
            if key in self.light:
                why["лёгкий настил на балке"] += 1
        for key in fallen:
            for x, y, z in T.part_cells(key):
                if x <= 0 or y <= 0 or x >= blk.sx - 1 or y >= blk.sy - 1:
                    why["край" if self.ver is None else "край карты"] += 1
                if self.ver is not None and (x, y, z) not in self.ver:
                    why["непроверенная клетка"] += 1
        s_any, _ = evaluate4(blk, removed, self.model, tie="any")
        d_any = fallen ^ self.fallen_of(self.any0, s_any, removed)
        if d_any:
            why["общая крона: исход зависит от того, держит ли кусок любой из стволов"] += len(d_any)
        if self.foot is not None:
            inside = lambda k: (k[1], k[2], k[3]) in self.foot      # noqa: E731
            out_f = {k for k in fallen if not inside(k)}
            if out_f:
                why["падает за границей здания"] += len(out_f)
            s_iso, _ = evaluate4(blk, removed | self.ext, self.model)
            dep = {k for k in look | fallen if inside(k) and k not in self.ext and
                   ((k in self.sup0) != (k in self.iso0) or (k in sup) != (k in s_iso))}
            if dep:
                why["опора через соседнюю постройку"] += len(dep)
        deps = []
        for e in CANDIDATE_RULES:
            s_e, _ = evaluate4(blk, removed, self.model.replace(e, ""))
            if self.fallen_of(self.alt0[e], s_e, removed) != fallen:
                deps.append(e)
        return {"status": "UNSUPPORTED" if why else "OK", "fallen": fallen, "why": dict(why), "depends_on": deps,
                "sup": sup}


def verdict(blk, base, res, rm, mf, ms):
    mf, ms = mf - rm, ms - rm
    stood = sorted(k for k in mf if k in res["sup"] and k in base.sup0)
    fell = sorted(k for k in ms if k not in res["sup"] and k in base.sup0)
    v = "PASS" if not stood and not fell else "FAIL"
    if not mf and not ms:
        v = "EMPTY"
    return v, stood, fell


# ------------------------------------------------------------------ самопроверка

def cmd_selfcheck():
    roles = V.load_roles()
    g, low = S.groups()
    vs = T.vessels()
    n = same_f = same_g = 0
    diff_f, diff_g = [], []
    t0 = time.time()
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None or blk.sz < 2 or g.get(tname.upper()) != "1" or tname.upper() in low:
            continue
        if (tname.upper(), bname.upper()) in vs:
            continue
        V.apply_roles(blk, roles)
        n += 1
        a, _ = T.evaluate3(blk, frozenset(), M0F)
        b, _ = evaluate4(blk, frozenset(), M0F)
        c, _ = evaluate4(blk, frozenset(), MODEL)
        if a == b:
            same_f += 1
        else:
            diff_f.append((tname, bname))
        if a == c:
            same_g += 1
        else:
            diff_g.append((tname, bname, len(a ^ c)))
        if n % 300 == 0:
            print("  блоков %d, %.0f с" % (n, time.time() - t0), flush=True)
    res = {"blocks": n, "evaluate4_без_Y_равно_M0f": same_f, "M0g_целый_равно_M0f": same_g,
           "diff_noY": diff_f[:20], "diff_M0g": diff_g[:20]}
    os.makedirs(OUT, exist_ok=True)
    with open(OUT + "/selfcheck.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if diff_f or diff_g:
        raise SystemExit("САМОПРОВЕРКА НЕ ПРОШЛА")


# ------------------------------------------------------------------ поиск сценариев по правилам

DEV_TREES = {"SOLFOREST16", "JUNGLE12", "JUNGLEDIO05"}      # по имени: блок живёт в нескольких террейнах
SEARCH_SEED = 20261007
N_SINGLE, N_ROW, N_FLOOR, N_SPECIAL, N_PIER = 40, 12, 12, 10, 12


def is_door(p):
    return p.get("cls") == "door" or p.get("role") == "DOOR"


def removals(blk, f):
    """Варианты повреждения блока: (вид, части). Зерно - от имени блока, выборка воспроизводима."""
    import zlib
    rnd = random.Random(SEARCH_SEED ^ zlib.crc32(("%s/%s" % (blk.terrain, blk.name)).upper().encode()))
    cls = {k: V.eff_cls(k, p, "RUA") for k, p in blk.parts.items()}
    bear = sorted(k for k in blk.parts if cls[k] in V.BEARING)
    out = []

    def take(kind, items, n):
        items = list(items)
        rnd.shuffle(items)
        for it in items[:n]:
            out.append((kind, it if isinstance(it, frozenset) else frozenset([it])))
    take("несущая", bear, N_SINGLE)
    rows = []
    for k, x, y, z in bear:
        if k in ("w", "n"):
            dx, dy = (0, 1) if k == "w" else (1, 0)
            row = [(k, x + dx * i, y + dy * i, z) for i in range(3)]
            if all(r in blk.parts and cls[r] in V.BEARING for r in row):
                rows.append(frozenset(row))
    take("ряд из 3", rows, N_ROW)
    take("пол", [k for k in blk.parts if k[0] == "f" and k[3] >= 1], N_FLOOR)
    take("скат или тент", [k for k, p in blk.parts.items() if p.get("role") in ("ROOF", "TARP")], N_SPECIAL)
    des = designed(blk, f) if "I" in f else {}
    piers, doors = set(), set()
    for k, x, y, z in des:
        if z < 1:
            continue
        dx, dy = (0, 1) if k == "w" else (1, 0)
        for s in (1, -1):
            for i in range(1, V.LINTEL + 2):
                nk = (k, x + dx * s * i, y + dy * s * i, z - 1)
                if nk in blk.parts and cls[nk] in V.BEARING:
                    piers.add(nk)
                    break
        under = (k, x, y, z - 1)
        if under in blk.parts and is_door(blk.parts[under]):
            doors.add(under)
    take("простенок под перемычкой", sorted(piers), N_PIER)
    take("дверь под перемычкой", sorted(doors), 6)
    seen, uniq = set(), []
    for kind, rm in out:
        if rm not in seen:
            seen.add(rm)
            uniq.append((kind, rm))
    return uniq


def applicable(blk, f):
    """Правила, у которых в блоке есть на чём сработать (иначе прогон без правила не нужен)."""
    ft = T.floor_types(blk)
    out = "B"
    if any(v[1] == "кровля" for v in ft.values()):
        out += "S"
    if any(p.get("role") == "TARP" for p in blk.parts.values()):
        out += "M"
    if "I" in f and designed(blk, f):
        out += "Y"
    return out


def search_worker(args):
    shard, jobs, want = args
    roles = V.load_roles()
    rows = []
    i = 0
    f = MODEL.replace("Y", "")
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None or (tname.upper(), bname.upper()) not in want:
            continue
        i += 1
        if i % jobs != shard:
            continue
        V.apply_roles(blk, roles)
        sup0 = evaluate4(blk, frozenset(), MODEL)[0]
        app = applicable(blk, f)
        alt0 = {e: evaluate4(blk, frozenset(), MODEL.replace(e, ""))[0] for e in app}
        for rk, rm in removals(blk, f):
            sup = evaluate4(blk, rm, MODEL)[0]
            fm = {k for k in sup0 if k not in sup and k not in rm and k[3] > 0}
            for e in app:
                se = evaluate4(blk, rm, MODEL.replace(e, ""))[0]
                fe = {k for k in alt0[e] if k not in se and k not in rm and k[3] > 0}
                if fe != fm:
                    rows.append([tname, bname, e, rk, T.compress(sorted(rm)), len(fm), len(fe), len(fm ^ fe),
                                 T.compress(sorted(fm - fe)), T.compress(sorted(fe - fm))])
            if rk == "дверь под перемычкой":
                rows.append([tname, bname, "door", rk, T.compress(sorted(rm)), len(fm), len(fm), 0, "", ""])
    return rows


def tarp_rows(skip):
    """Тенты (правило M) есть только в 5 блоках игры, кандидат пилота из них один, и выборка его не задела.
    Блоки группы 1 с тентом вне кандидатов: полный перебор - каждая часть и пары несущих/предметов рядом
    на одном этаже. Висящее до боя и неизвестные роли отсеет судья при отборе."""
    import itertools
    roles = V.load_roles()
    g, low = S.groups()
    vs = T.vessels()
    rows = []
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        k0 = (tname.upper(), bname.upper())
        if blk is None or blk.sz < 2 or k0 in skip or k0[1] in skip or g.get(k0[0]) != "1" or k0[0] in low or k0 in vs:
            continue
        V.apply_roles(blk, roles)
        if not any(p.get("role") == "TARP" for p in blk.parts.values()):
            continue
        s0 = evaluate4(blk, frozenset(), MODEL)[0]
        a0 = evaluate4(blk, frozenset(), MODEL.replace("M", ""))[0]
        cls = {k: V.eff_cls(k, p, "RUA") for k, p in blk.parts.items()}
        bear = sorted(k for k in blk.parts if cls[k] in V.BEARING or k[0] == "o")
        vs_ = [("часть", frozenset([k])) for k in sorted(blk.parts)]
        vs_ += [("пара рядом", frozenset(p)) for p in itertools.combinations(bear, 2)
                if abs(p[0][1] - p[1][1]) + abs(p[0][2] - p[1][2]) <= 2 and p[0][3] == p[1][3]]
        for rk, rm in vs_:
            s = evaluate4(blk, rm, MODEL)[0]
            a = evaluate4(blk, rm, MODEL.replace("M", ""))[0]
            fm = {k for k in s0 if k not in s and k not in rm and k[3] > 0}
            fa = {k for k in a0 if k not in a and k not in rm and k[3] > 0}
            if fm != fa:
                rows.append([tname, bname, "M", rk, T.compress(sorted(rm)), len(fm), len(fa), len(fm ^ fa),
                             T.compress(sorted(fm - fa)), T.compress(sorted(fa - fm))])
    return rows


def cmd_search(jobs=12):
    import multiprocessing as mp
    # пилот 0f исключается по имени блока: один блок стоит в нескольких террейнах (CHEMTOWN02)
    pilot_names = {r["block"].upper() for r in P.read_tsv(P.PILOT)}
    pilot = {(r["terrain"].upper(), r["block"].upper()) for r in P.read_tsv(P.PILOT)}
    cand = P.read_tsv("census/collapse/stage0f/pilot_candidates.tsv")
    want = {(r["terrain"].upper(), r["block"].upper()) for r in cand
            if r["block"].upper() not in DEV_TREES | pilot_names}
    t0 = time.time()
    with mp.Pool(jobs) as pool:
        parts = pool.map(search_worker, [(s, jobs, want) for s in range(jobs)])
    rows = sorted(r for p in parts for r in p)
    if not any(r[2] == "M" for r in rows):
        rows += sorted(tarp_rows(want | pilot | pilot_names))
    cc.write_tsv(OUT + "/search.tsv", ["terrain", "block", "rule", "removal_kind", "remove", "fallen_model",
                                       "fallen_without_rule", "diff", "falls_only_with_rule",
                                       "falls_only_without_rule"], rows)
    cnt = collections.Counter(r[2] for r in rows)
    blocks = collections.defaultdict(set)
    for r in rows:
        blocks[r[2]].add((r[0], r[1]))
    print("блоков %d, %.0f с; мест, где исход зависит от правила: %s; блоков: %s" % (
        len(want), time.time() - t0, dict(cnt), {e: len(b) for e, b in blocks.items()}))


# ------------------------------------------------------------------ отбор сценариев и задание рецензенту

REVIEW = "census/collapse/review0g"               # вне stage0*: рецензенту туда можно, в stage0* нельзя
PER_RULE = 6
MAX_DIFF, MAX_FALLEN = 12, 30
N_DECOY = 4


def load_many(want, roles):
    out = {}
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        k = (tname.upper(), bname.upper())
        if blk is not None and k in want and k not in out:
            out[k] = V.apply_roles(blk, roles)
    return out


def decoys(blk, base, rm, fallen_any, rnd):
    """Устоявшие при обоих вариантах части выше земли рядом с событием - чтобы список оценки не выдавал ответ."""
    cells = {c for k in rm | fallen_any for c in T.part_cells(k)}
    near = {k for c in P.near(P.near(cells)) for k in base.by_cell.get(c, ())}
    pool = sorted(k for k in near if k[3] > 0 and k not in rm and k not in fallen_any and k in base.sup0)
    rnd.shuffle(pool)
    return set(pool[:N_DECOY])


def scen_fallen(blk, rm, flags, tie="all"):
    s0 = evaluate4(blk, frozenset(), flags, tie)[0]
    s = evaluate4(blk, frozenset(rm), flags, tie)[0]
    return {k for k in s0 if k not in s and k not in rm and k[3] > 0}


def crown_cases(roles, rnd):
    """Общие куски кроны вне деревьев разработки 0f: снят комель одного из стволов куска."""
    out = []
    skip = DEV_TREES | {r["block"].upper() for r in P.read_tsv(P.PILOT)}
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None or blk.sz < 2 or bname.upper() in skip:
            continue
        V.apply_roles(blk, roles)
        sh = shared_crowns(blk)
        if not sh:
            continue
        cls = {key: V.eff_cls(key, p, "RUA") for key, p in blk.parts.items()}
        role = {key: p.get("role", "") for key, p in blk.parts.items()}
        cols, crowns = T.tree_structure(blk, cls, role)
        trunks = sorted({c for cs in sh.values() for c in cs})
        c = trunks[rnd.randrange(len(trunks))]
        rm = frozenset([cols[c][0]])
        fa = scen_fallen(blk, rm, MODEL, "all")
        fy = scen_fallen(blk, rm, MODEL, "any")
        if fa != fy:
            out.append((tname, bname, blk, rm, fa, fy, {k for k, cs in sh.items() if c in cs}))
    return out


def cmd_pick():
    rnd = random.Random(SEARCH_SEED)
    roles = V.load_roles()
    disp = S.disputed_records()
    rows = P.read_tsv(OUT + "/search.tsv")
    maps = {(r["terrain"].upper(), r["block"].upper()): int(r["maps"])
            for r in P.read_tsv("census/collapse/stage0f/pilot_candidates.tsv")}
    for r in rows:
        r["_k"] = (r["terrain"].upper(), r["block"].upper())
        r["_r"] = rnd.random()
    want = {r["_k"] for r in rows}
    blocks = load_many(want, roles)
    bases = {}
    picked, log = [], []
    used_b = collections.Counter()                 # по ИМЕНИ блока: один блок живёт в нескольких террейнах
    for e in list(SEARCH_RULES) + ["door"]:
        cand = [r for r in rows if r["rule"] == e and int(r["fallen_model"]) <= MAX_FALLEN and
                int(r["fallen_without_rule"]) <= MAX_FALLEN and (e == "door" or 1 <= int(r["diff"]) <= MAX_DIFF)]
        cand.sort(key=lambda r: (maps.get(r["_k"], 0) == 0, int(r["diff"]), r["_r"]))
        need = 3 if e == "door" else PER_RULE
        dir_of = lambda r: ("+" if r["falls_only_with_rule"] else "") + ("-" if r["falls_only_without_rule"] else "")  # noqa: E731
        dirs = {dir_of(r) for r in cand}
        dcap = -(-need // len(dirs)) if len(dirs) > 1 else need   # оба направления - поровну
        got, used_t, kinds, dcnt = [], set(), collections.Counter(), collections.Counter()
        used_rm = set()
        for pass_ in (0, 1, 2, 3):                 # 0 разные террейны, 1 разные блоки, 2 без «поровну»
            if pass_ == 3 and e != "M":            # тенты - три маленьких блока: по два места на блок
                break
            for r in cand:
                if len(got) >= need:
                    break
                bn = r["block"].upper()
                if (bn, r["remove"]) in used_rm or used_b[bn] >= (2 if pass_ == 3 else 1):
                    continue
                if pass_ == 0 and r["terrain"].upper() in used_t:
                    continue
                if pass_ < 2 and dcnt[dir_of(r)] >= dcap:
                    continue
                if e == "Y" and pass_ == 0 and kinds[r["removal_kind"]] >= 3:
                    continue
                blk = blocks[r["_k"]]
                if r["_k"] not in bases:
                    bases[r["_k"]] = Base4(blk, disp)
                base = bases[r["_k"]]
                rm = cc.select(blk, r["remove"])
                res = base.judge(rm)
                if res["status"] != "OK" or (e != "door" and e not in res["depends_on"]):
                    log.append([e, r["terrain"], r["block"], r["remove"], res["status"],
                                json.dumps(res["why"], ensure_ascii=False), "".join(res["depends_on"])])
                    continue
                fm = res["fallen"]
                fe = fm if e == "door" else scen_fallen(blk, rm, MODEL.replace(e, ""))
                got.append((e, r, blk, rm, fm, fe))
                used_b[bn] += 1
                used_rm.add((bn, r["remove"]))
                used_t.add(r["terrain"].upper())
                kinds[r["removal_kind"]] += 1
                dcnt[dir_of(r)] += 1
        picked += got
        print("правило %s: кандидатов %d, взято %d, по направлениям %s" % (e, len(cand), len(got), dict(dcnt)),
              flush=True)
    crowns = crown_cases(roles, rnd)
    rnd.shuffle(crowns)
    crowns.sort(key=lambda c: len(c[4] ^ c[5]) > MAX_DIFF)
    cpick, cb, ct = [], set(), set()
    for pass_ in (0, 1):                           # сначала разные террейны, потом разные блоки
        for c in crowns:
            if c[1].upper() in cb or len(cpick) >= PER_RULE or (pass_ == 0 and c[0].upper() in ct):
                continue
            cb.add(c[1].upper())
            ct.add(c[0].upper())
            cpick.append(c)
    print("общих крон: блоков с расхождением all/any %d, взято %d" % (len(crowns), len(cpick)), flush=True)

    # что знает модель (в stage0g, рецензенту не показывается) и задание рецензенту (review0g)
    os.makedirs(REVIEW + "/geom", exist_ok=True)
    for n in os.listdir(REVIEW + "/geom"):         # срезы прежнего отбора
        os.remove(REVIEW + "/geom/" + n)
    model_rows, task_rows, crow_rows, cmodel_rows = [], [], [], []
    order = list(range(len(picked)))
    rnd.shuffle(order)                             # номер сценария не выдаёт правило
    ids = {}
    for n, i in enumerate(order, 1):
        ids[i] = "G-%02d" % n
    geoms = set()
    for i, (e, r, blk, rm, fm, fe) in enumerate(picked):
        base = bases[r["_k"]]
        dec = decoys(blk, base, rm, fm | fe, rnd)
        look = sorted(fm | fe | dec)
        sid = ids[i]
        model_rows.append([sid, e, r["terrain"], r["block"], r["removal_kind"], T.compress(sorted(rm)),
                           T.compress(sorted(fm)), T.compress(sorted(fe)), T.compress(sorted(dec))])
        task_rows.append([sid, r["terrain"], r["block"], T.compress(sorted(rm)), T.compress(look)])
        geoms.add(blk)
    for n, (tname, bname, blk, rm, fa, fy, sh) in enumerate(cpick, 1):
        base = Base4(blk, disp)
        dec = decoys(blk, base, rm, fa | fy | sh, rnd)
        look = sorted(fa | fy | (sh - rm) | dec)
        sid = "K-%02d" % n
        cmodel_rows.append([sid, tname, bname, T.compress(sorted(rm)), T.compress(sorted(fa)), T.compress(sorted(fy)),
                            T.compress(sorted(sh)), T.compress(sorted(dec))])
        crow_rows.append([sid, tname, bname, T.compress(sorted(rm)), T.compress(look)])
        geoms.add(blk)
    task_rows.sort()
    for blk in geoms:
        with open("%s/geom/%s__%s.txt" % (REVIEW, blk.terrain.upper(), blk.name.upper()), "w", encoding=ENC) as f:
            f.write(V.geom_text(blk) + "\n")
    cc.write_tsv(OUT + "/picked_model.tsv", ["id", "rule", "terrain", "block", "removal_kind", "remove",
                                             "fallen_M0g", "fallen_without_rule", "decoys"], model_rows)
    cc.write_tsv(OUT + "/picked_crowns_model.tsv", ["id", "terrain", "block", "remove", "fallen_all", "fallen_any",
                                                    "shared_pieces", "decoys"], cmodel_rows)
    cc.write_tsv(OUT + "/pick_rejected.tsv", ["rule", "terrain", "block", "remove", "status", "why", "depends_on"], log)
    cc.write_tsv(REVIEW + "/scenarios_rules.tsv", ["id", "terrain", "block", "remove", "evaluate"], task_rows)
    cc.write_tsv(REVIEW + "/scenarios_crowns.tsv", ["id", "terrain", "block", "remove", "evaluate"], crow_rows)
    print("сценариев правил %d, крон %d, срезов блоков %d -> %s" % (len(task_rows), len(crow_rows), len(geoms), REVIEW))


# ------------------------------------------------------------------ ожидания и замок

EXPECT_RULES = REVIEW + "/expect_0g_rules.tsv"
EXPECT_CROWNS = REVIEW + "/expect_0g_crowns.tsv"
TASKS = {EXPECT_RULES: REVIEW + "/scenarios_rules.tsv", EXPECT_CROWNS: REVIEW + "/scenarios_crowns.tsv"}
PICKED = [OUT + "/search.tsv", OUT + "/picked_model.tsv", OUT + "/picked_crowns_model.tsv"]
HOLD2_DATA = [HOLD2 + "/source_summary.tsv", HOLD2 + "/battles/index.tsv"]


def check_expect(exp_path, roles):
    """Ответ рецензента по форме: каждая часть evaluate ровно в одной колонке, чужих частей нет, каждая запись
    находит часть (опечатка в записи иначе молча выпала бы из проверки)."""
    task = {r["id"]: r for r in P.read_tsv(TASKS[exp_path])}
    exp = P.read_tsv(exp_path)
    blocks = load_many({(r["terrain"].upper(), r["block"].upper()) for r in task.values()}, roles)
    bad, seen = [], set()
    for e in exp:
        t = task.get(e["id"])
        if t is None:
            bad.append("%s: нет в задании" % e["id"])
            continue
        seen.add(e["id"])
        if (e["terrain"].upper(), e["block"].upper(), e["remove"].strip()) != (
                t["terrain"].upper(), t["block"].upper(), t["remove"].strip()):
            bad.append("%s: terrain/block/remove не как в задании" % e["id"])
            continue
        blk = blocks[(t["terrain"].upper(), t["block"].upper())]
        ev = cc.select(blk, t["evaluate"])
        cols = {}
        for c in ("must_fall", "must_stand", "unsure"):
            toks = (e.get(c) or "").split()
            try:
                empty = [tk for tk in toks if not cc.select(blk, tk)]
                cols[c] = cc.select(blk, " ".join(toks))
            except ValueError as ex:
                bad.append("%s: %s" % (e["id"], ex))
                cols[c] = set()
                continue
            if empty:
                bad.append("%s: в %s записи без части: %s" % (e["id"], c, " ".join(empty)))
        a, b, u = cols["must_fall"], cols["must_stand"], cols["unsure"]
        if (a & b) | (a & u) | (b & u):
            bad.append("%s: часть в двух колонках: %s" % (e["id"], T.compress(sorted((a & b) | (a & u) | (b & u)))))
        if (a | b | u) - ev:
            bad.append("%s: не из evaluate: %s" % (e["id"], T.compress(sorted((a | b | u) - ev))))
        if ev - (a | b | u):
            bad.append("%s: не оценено: %s" % (e["id"], T.compress(sorted(ev - (a | b | u)))))
    for sid in sorted(set(task) - seen):
        bad.append("%s: нет строки" % sid)
    return bad


def cmd_lock():
    roles = V.load_roles()
    for p in TASKS:
        if not os.path.exists(p):
            raise SystemExit("нет ожиданий %s - замок пишется после ответа рецензента" % p)
        bad = check_expect(p, roles)
        if bad:
            raise SystemExit("ожидания %s не по форме:\n  %s" % (p, "\n  ".join(bad)))
    lines = ["версия модели M0g обрушения, записано %s - до прогона сценариев, разработки и второго набора карт" %
             time.strftime("%Y-%m-%d %H:%M:%S"),
             "флаги %s (collapse_v4.evaluate4: M0f плюс Y, общая крона tie=all); E, J, L не входят" % MODEL,
             "параметры (экспериментальные): C=2 L=12 order=2 cp=1 LINTEL=%d L_TARP=%d L_ROOF=%d C_CANOPY=%d" % (
                 V.LINTEL, V.L_TARP, T.L_ROOF, T.C_CANOPY),
             "правила-кандидаты %s; судья Base4: неизвестные роли как M0f, общая крона (all против any), граница "
             "здания на карте (падает за границей, опора через соседнюю постройку)" % CANDIDATE_RULES,
             "ожидания 0g писал слепой рецензент (census/collapse/review0g/TASK.md) без доступа к модели"]
    for p in CODE + DATA + HOLD2_DATA + PICKED + list(TASKS.values()) + list(TASKS) + DEV_FILES + [P.PILOT]:
        lines.append("%s sha256 %s" % (p, sha(p)))
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def check_lock():
    if not os.path.exists(LOCK):
        raise SystemExit("нет замка %s - сначала lock" % LOCK)
    txt = open(LOCK, encoding=ENC).read()
    bad = [p for p in CODE + DATA + HOLD2_DATA + PICKED + list(TASKS.values()) + list(TASKS) + DEV_FILES + [P.PILOT]
           if sha(p) not in txt]
    if bad:
        raise SystemExit("замок M0g НЕ СОВПАДАЕТ: " + ", ".join(bad))
    print("замок M0g совпадает", flush=True)


# ------------------------------------------------------------------ сценарии

def judge_parts(sup0, sup, rm, mf, ms):
    """Вердикт по ожиданиям для одного варианта модели: опоры до и после - свои у каждого варианта."""
    mf, ms = mf - rm, ms - rm
    stood = sorted(k for k in mf if k in sup and k in sup0)
    fell = sorted(k for k in ms if k not in sup and k in sup0)
    if not mf and not ms:
        return "EMPTY", stood, fell
    return ("PASS" if not stood and not fell else "FAIL"), stood, fell


def agree_label(v_with, v_without):
    return {("PASS", "FAIL"): "с правилом", ("FAIL", "PASS"): "без правила", ("PASS", "PASS"): "оба",
            ("FAIL", "FAIL"): "ни один"}.get((v_with, v_without), "-")


def run_scen(path, model_rows, disp, roles, tag):
    """Сценарии по ожиданиям на отдельных блоках. model_rows - id -> правило сценария (или None)."""
    expect = P.read_tsv(path)
    blocks = V.load_blocks(expect, roles)
    bases, out = {}, {}
    cnt, by_rule = collections.Counter(), collections.defaultdict(collections.Counter)
    m0f_mismatch = []
    for e in expect:
        key = (e["terrain"].upper(), e["block"].upper())
        blk = blocks[key]
        if key not in bases:
            bases[key] = Base4(blk, disp)
        base = bases[key]
        rm = cc.select(blk, e["remove"])
        mf, ms = cc.select(blk, e.get("must_fall", "")), cc.select(blk, e.get("must_stand", ""))
        uns = cc.select(blk, e.get("unsure", ""))
        res = base.judge(rm, mf | ms)
        v, stood, fell = judge_parts(base.sup0, res["sup"], rm, mf, ms)
        shown = "UNSUPPORTED" if res["status"] == "UNSUPPORTED" else v
        cnt[shown] += 1
        # M0f на том же сценарии: без Y evaluate4 обязан совпасть с collapse_v3 и после повреждения
        a = evaluate4(blk, frozenset(rm), M0F)[0]
        b = T.evaluate3(blk, frozenset(rm), M0F)[0]
        if a != b:
            m0f_mismatch.append(e["id"])
        v_m0f, _, _ = judge_parts(evaluate4(blk, frozenset(), M0F)[0], a, rm, mf, ms)
        r = {"shown": shown, "model_verdict": v, "M0f_verdict": v_m0f, "why": res["why"],
             "depends_on": res["depends_on"], "fallen": T.compress(sorted(res["fallen"])), "n_fallen": len(res["fallen"]),
             "stood": T.compress(stood), "fell": T.compress(fell), "must_fall": len(mf - rm),
             "must_stand": len(ms - rm), "unsure": len(uns)}
        rule = model_rows.get(e["id"])
        if rule:
            r["rule"] = rule
            if rule in CANDIDATE_RULES:
                f = MODEL.replace(rule, "")
                s0e, se = evaluate4(blk, frozenset(), f)[0], evaluate4(blk, frozenset(rm), f)[0]
                v_wo, st_wo, fe_wo = judge_parts(s0e, se, rm, mf, ms)
                r.update({"without_rule_verdict": v_wo, "without_stood": T.compress(st_wo),
                          "without_fell": T.compress(fe_wo), "reviewer_agrees_with": agree_label(v, v_wo)})
                by_rule[rule][("согласие", r["reviewer_agrees_with"])] += 1
            by_rule[rule][("показано", shown)] += 1
        out[e["id"]] = r
        print("%-6s %-5s %-11s (M0g %s, M0f %s%s) упало %d | устояло из должных упасть %d/%d, упало из должных "
              "стоять %d/%d, unsure %d %s %s" % (
                  e["id"], rule or "", shown, v, v_m0f,
                  ", без правила %s" % r["without_rule_verdict"] if "without_rule_verdict" in r else "",
                  len(res["fallen"]), len(stood), len(mf - rm), len(fell), len(ms - rm), len(uns),
                  "зависит от " + "".join(res["depends_on"]) if res["depends_on"] else "",
                  json.dumps(res["why"], ensure_ascii=False) if res["why"] else ""), flush=True)
    summary = {"count": dict(cnt), "M0f_evaluate4_mismatch": m0f_mismatch,
               "by_rule": {e: {"%s: %s" % k: n for k, n in sorted(c.items())} for e, c in sorted(by_rule.items())}}
    with open(OUT + "/scen_%s.json" % tag, "w", encoding=ENC) as f:
        json.dump({"file": path, "sha256": sha(path), "model": MODEL, "summary": summary, "result": out}, f,
                  ensure_ascii=False, indent=1)
    print("итог %s: %s" % (tag, json.dumps(summary, ensure_ascii=False)), flush=True)
    return summary


def run_crowns(path, disp, roles):
    """Общие кроны - отдельные ожидания: рецензент против «держат все стволы» (как M0f) и «держит любой»."""
    expect = P.read_tsv(path)
    blocks = V.load_blocks(expect, roles)
    out, cnt = {}, collections.Counter()
    for e in expect:
        blk = blocks[(e["terrain"].upper(), e["block"].upper())]
        base = Base4(blk, disp)
        rm = cc.select(blk, e["remove"])
        mf, ms = cc.select(blk, e.get("must_fall", "")), cc.select(blk, e.get("must_stand", ""))
        res = base.judge(rm, mf | ms)
        v_all, st_a, fe_a = judge_parts(base.sup0, res["sup"], rm, mf, ms)
        s_any = evaluate4(blk, frozenset(rm), MODEL, tie="any")[0]
        v_any, st_y, fe_y = judge_parts(base.any0, s_any, rm, mf, ms)
        other = {k: n for k, n in res["why"].items() if not k.startswith("общая крона")}
        shown = "UNSUPPORTED" if res["status"] == "UNSUPPORTED" else v_all
        lab = {("PASS", "FAIL"): "все стволы", ("FAIL", "PASS"): "любой ствол"}.get(
            (v_all, v_any), {"PASS": "оба", "FAIL": "ни один"}.get(v_all, "-") if v_all == v_any else "-")
        cnt[("показано", shown)] += 1
        cnt[("согласие", lab)] += 1
        out[e["id"]] = {"shown": shown, "all_verdict": v_all, "any_verdict": v_any, "reviewer_agrees_with": lab,
                        "why": res["why"], "other_unsupported": other, "all_stood": T.compress(st_a),
                        "all_fell": T.compress(fe_a), "any_stood": T.compress(st_y), "any_fell": T.compress(fe_y),
                        "must_fall": len(mf - rm), "must_stand": len(ms - rm),
                        "unsure": len(cc.select(blk, e.get("unsure", "")))}
        print("%-6s %-11s все стволы %s, любой %s -> рецензент: %s %s" % (
            e["id"], shown, v_all, v_any, lab, json.dumps(other, ensure_ascii=False) if other else ""), flush=True)
    summary = {"%s: %s" % k: n for k, n in sorted(cnt.items())}
    with open(OUT + "/scen_expect_0g_crowns.json", "w", encoding=ENC) as f:
        json.dump({"file": path, "sha256": sha(path), "model": MODEL, "summary": summary, "result": out}, f,
                  ensure_ascii=False, indent=1)
    print("итог кроны:", json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def cmd_scen():
    check_lock()
    roles = V.load_roles()
    disp = S.disputed_records()
    rules = {r["id"]: r["rule"] for r in P.read_tsv(OUT + "/picked_model.tsv")}
    run_scen(EXPECT_RULES, rules, disp, roles, "expect_0g_rules")
    run_crowns(EXPECT_CROWNS, disp, roles)


# ------------------------------------------------------------------ карты: разработка (отложенные 0f) и второй набор

def known_names():
    """Имена блоков на 90 картах настройки - по verified_cells, как отбор пилота (R-269)."""
    cache = OUT + "/known_names.json"
    if os.path.exists(cache):
        with open(cache, encoding=ENC) as f:
            return set(json.load(f))
    import collapse_battles as cb
    roles = V.load_roles()
    d = cb.Data(V.game_args())
    known = set()
    for n in sorted(os.listdir(V.OUT + "/source")):
        if n.endswith(".pkl"):
            name = n[:-4] + ".sav"
            m, src = V.load_map(d, name, roles)
            known.update(tb[1].upper() for tb in V.verified_cells(d, name, m, src).values())
    if len(known) < 100:
        raise SystemExit("известных блоков %d - деление сломано (R-269)" % len(known))
    with open(cache, "w", encoding=ENC) as f:
        json.dump(sorted(known), f, ensure_ascii=False)
    return known


def map_worker(args):
    """Одна карта: висящее до боя по проверенным клеткам и сценарии всех ожиданий на местах их блоков."""
    hold, name, exp_paths, known, pilot = args
    import collapse_battles as cb
    import collapse_holdout as H
    H.HOLD = hold
    roles = V.load_roles()
    g, low = S.groups()
    disp = S.disputed_records()
    d = cb.Data(H.game_args())
    m, src = H.load_map(d, name, roles, V.apply_roles)
    ver = H.verified_cells(d, name, m, src)
    t0 = time.time()
    base = Base4(m, disp, ver=ver)
    sup = base.sup0
    m0f_diff = len(sup ^ T.evaluate3(m, frozenset(), M0F)[0])
    cat = {"известный": collections.Counter(), "новый": collections.Counter()}
    hung = []
    for key in m.parts:
        if key[3] == 0:
            continue
        c = (key[1], key[2], key[3])
        if c not in ver:
            cat["новый"]["верх непроверенный"] += 1
            if key not in sup:
                cat["новый"]["висит в непроверенной клетке"] += 1
            continue
        bt, bn = ver[c][0].upper(), ver[c][1].upper()
        kk = "известный" if bn in known else "новый"
        cat[kk]["верх"] += 1
        if key in sup:
            continue
        vessel = g.get(bt) in ("2", "3")
        cl, wh = S.classify(m, key, sup, vessel, bt in low, disp, m.sx, m.sy)
        cl = {"край": "край карты"}.get(cl, cl)
        cat[kk][cl] += 1
        if bn in pilot:
            hung.append([name, bt, bn, cl, wh, "%s:%d:%d:%d" % key])
    srows = []
    for path in exp_paths:
        expect = P.read_tsv(path)
        want = {(e["terrain"].upper(), e["block"].upper()) for e in expect}
        places = [p for p in src["blocks"] if (p[0].upper(), p[1].upper()) in want]
        if not places:
            continue
        refs = V.load_blocks([e for e in expect if (e["terrain"].upper(), e["block"].upper()) in
                              {(p[0].upper(), p[1].upper()) for p in places}], roles)
        for bt, bn, ox, oy, oz in places:
            ref = refs[(bt.upper(), bn.upper())]
            foot = {(x + ox, y + oy, z + oz) for z in range(ref.sz) for y in range(ref.sy) for x in range(ref.sx)}
            base.set_foot(foot)
            for e in expect:
                if (e["terrain"].upper(), e["block"].upper()) != (bt.upper(), bn.upper()):
                    continue
                rm = P.shift_select(m, e["remove"], ox, oy, oz, ref)
                if not rm:
                    continue
                mf = P.shift_select(m, e.get("must_fall", ""), ox, oy, oz, ref) - rm
                ms = P.shift_select(m, e.get("must_stand", ""), ox, oy, oz, ref) - rm
                res = base.judge(rm, mf | ms)
                v, stood, fell = judge_parts(sup, res["sup"], rm, mf, ms)
                shown = "UNSUPPORTED" if res["status"] == "UNSUPPORTED" else v
                srows.append([name, os.path.basename(path), e["id"], bt, bn, ox, oy, oz, shown, v,
                              len(res["fallen"]), len(stood), len(mf), len(fell), len(ms),
                              json.dumps(res["why"], ensure_ascii=False), "".join(res["depends_on"])])
    return {"name": name, "terrain": src["terrain"], "cat": {k: dict(v) for k, v in cat.items()}, "hung": hung,
            "scen": srows, "m0f_intact_diff": m0f_diff, "sec": round(time.time() - t0)}


def run_maps(hold, exp_paths, tag, jobs=10):
    import multiprocessing as mp
    import collapse_holdout as H
    H.HOLD = hold
    names = H.names()
    known = known_names()
    pilot = {r["block"].upper() for r in P.read_tsv(P.PILOT)}
    print("%s: карт %d, известных имён блоков %d" % (tag, len(names), len(known)), flush=True)
    cat = {"известный": collections.Counter(), "новый": collections.Counter()}
    hung, srows, m0f_diff = [], [], {}
    with mp.Pool(jobs) as pool:
        for r in pool.imap_unordered(map_worker, [(hold, n, exp_paths, known, pilot) for n in names]):
            for k, v in r["cat"].items():
                cat[k].update(v)
            hung += r["hung"]
            srows += r["scen"]
            if r["m0f_intact_diff"]:
                m0f_diff[r["name"]] = r["m0f_intact_diff"]
            print("  %s %s, мест сценариев %d, %d с" % (r["name"], r["terrain"], len(r["scen"]), r["sec"]), flush=True)
    srows.sort()
    hung.sort()
    head = ["save", "file", "id", "terrain", "block", "ox", "oy", "oz", "shown", "model", "fallen", "stood",
            "must_fall", "fell", "must_stand", "why", "depends_on"]
    cc.write_tsv(OUT + "/%s_scen.tsv" % tag, head, srows)
    cc.write_tsv(OUT + "/%s_pilot_hung.tsv" % tag, ["save", "terrain", "block", "category", "why", "part"], hung)
    by_file = collections.defaultdict(collections.Counter)
    why = collections.Counter()
    for r in srows:
        by_file[r[1]][r[8]] += 1
        if r[8] == "UNSUPPORTED":
            for k in json.loads(r[15]):
                why[k] += 1
    res = {"model": MODEL, "maps": len(names), "known_names": len(known),
           "by_block_kind": {k: dict(v) for k, v in cat.items()},
           "pilot_hung": len(hung), "M0g_vs_M0f_intact_diff": m0f_diff,
           "scenarios": {f: dict(c) for f, c in sorted(by_file.items())}, "unsupported_why": dict(why)}
    with open(OUT + "/%s.json" % tag, "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1), flush=True)


def cmd_dev():
    """Материал разработки, не приёмка: ожидания 0f на блоках и отложенные карты 0f (зёрна 14-17) под M0g."""
    check_lock()
    roles = V.load_roles()
    disp = S.disputed_records()
    for p in DEV_FILES:
        run_scen(p, {}, disp, roles, "dev_" + os.path.splitext(os.path.basename(p))[0])
    run_maps("census/collapse/holdout", DEV_FILES, "dev_holdout0f")


def cmd_holdout2():
    """Второй независимый набор (stage0g/holdout2.lock.txt): один раз, после замка."""
    check_lock()
    run_maps(HOLD2, [EXPECT_RULES, EXPECT_CROWNS] + DEV_FILES, "holdout2")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "selfcheck":
        cmd_selfcheck()
    elif cmd == "search":
        cmd_search()
    elif cmd == "pick":
        cmd_pick()
    elif cmd == "check":                           # форма ответа рецензента, без модели
        for p in TASKS:
            print(p, check_expect(p, V.load_roles()) or "по форме верно")
    elif cmd == "lock":
        cmd_lock()
    elif cmd == "scen":
        cmd_scen()
    elif cmd == "dev":
        cmd_dev()
    elif cmd == "holdout2":
        cmd_holdout2()
