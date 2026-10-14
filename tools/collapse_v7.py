#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0k обрушения зданий: исследовательская модель M0j. Движок не трогается; M0f-M0i2 (collapse_v3-v6b),
их замки, сценарии и ожидания не меняются - M0j живёт только здесь.

Рецензия 0j: по данным карты прочность всех конструкций не определить, общий пролёт этого не исправит. M0j
чинит только связи опор, а тип конструкции задаётся отдельной разметкой (collapse_ctype.py).

M0j = M0i2 (RUADHQIMGOWZVXFk) плюс:
  a - предмет получает опору от пола, массива и несущего или мебели под собой; от стены своей клетки - только
      при явном креплении. Явное крепление - роль с собственным правилом (HANGER, RUN; при A они особые и
      держатся своими правилами) или пометка attach у части (разметка). Простого соседства со стеной мало.
  b - стена (w, n) получает опору от несущего предмета этажом ниже, только если он касается её основания:
      нижний занятый слой LOFT стены и верхний слой LOFT предмета ниже пересекаются хотя бы одним вокселем.
      Предмет в соседней клетке за ребром стены не касается её основания (толщина стены - в своей клетке).
      Критерий выбран до прогона (касание = общий воксель), чувствительность печатается отдельно.
Кровля атриума (R-12) правилом не меняется: навес остаётся навесом. Её тип - вопрос разметки.

    py -3.13 tools\collapse_v7.py lock        замок M0j (до прогона)
    py -3.13 tools\collapse_v7.py selfcheck   без a и b = M0i2 бит в бит; целые блоки: что a и b меняют
    py -3.13 tools\collapse_v7.py synth       контролируемые конструкции I1-I4 (правда stage0i/synth_truth.tsv)
    py -3.13 tools\collapse_v7.py dev         сценарии 0h и 0i - разработочные наборы, не приёмка
"""
import collections
import json
import os
import sys
import time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_census as cc                      # noqa: E402
import collapse_v2 as V                           # noqa: E402
import collapse_v3 as T                           # noqa: E402
import collapse_pilot as P                        # noqa: E402
import collapse_v4 as G                           # noqa: E402
import collapse_v5 as H                           # noqa: E402
import collapse_v6 as M                           # noqa: E402
import collapse_v6b as B                          # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/stage0k"
LOCK = OUT + "/rules.lock.txt"
M0I2 = B.MODEL                                    # RUADHQIMGOWZVXFk
MODEL = M0I2 + "ab"                               # M0j
NEW_RULES = "ab"
CANDIDATE_RULES = B.CANDIDATE_RULES + NEW_RULES
ATTACH_ROLES = {"HANGER", "RUN"}                  # явное крепление: свои правила держания
LOCKED = ["tools/collapse_v7.py"] + B.LOCKED


# ------------------------------------------------------------------ LOFT частей (b)

_LOFT = {}


def _loft_data():
    if "vals" not in _LOFT:
        mod_dir, files, loft_path, occ = cc.open_data(V.game_args())
        with open(loft_path, "rb") as f:
            data = f.read()
        _LOFT["vals"] = [data[i] | (data[i + 1] << 8) for i in range(0, len(data) - 1, 2)]
        _LOFT["files"] = files
        _LOFT["mcd"] = {}
    return _LOFT


def loft_ids(set_, idx):
    """12 номеров LOFT записи MCD с MCDPatch, как в игре (MapData::getLoftID). None - записи нет."""
    d = _loft_data()
    if set_ not in d["mcd"]:
        path = d["files"].find(os.path.join("TERRAIN", set_ + ".MCD"))
        raw = b""
        if path:
            with open(path, "rb") as f:
                raw = f.read()
        recs = [list(raw[i + 8:i + 20]) for i in range(0, len(raw) - cc.REC + 1, cc.REC)]
        for m in cc.PATCHES.get(set_, ()):
            i = m.get("MCDIndex")
            if isinstance(i, int) and i < len(recs) and "LOFTS" in m:
                recs[i] = list(m["LOFTS"][:12])
        d["mcd"][set_] = recs
    recs = d["mcd"][set_]
    return recs[idx] if idx < len(recs) else None


def footprint(t):
    """Воксели слоя LOFT t: множество (x, y), y - к югу, x - к востоку (TileEngine::voxelCheck)."""
    rows = _loft_data()["vals"][t * 16:(t + 1) * 16]
    return {(x, y) for y, r in enumerate(rows) for x in range(16) if r & (1 << x)}


def synth_foot(k, cls, layer):
    """Синтетика (набор SYNTH): стена w - столбцы 0-1, n - строки 0-1, колонна и блок - вся клетка."""
    if k == "w":
        return {(x, y) for x in (0, 1) for y in range(16)}
    if k == "n":
        return {(x, y) for x in range(16) for y in (0, 1)}
    if cls in ("column", "block", "hard", "wall"):
        return {(x, y) for x in range(16) for y in range(16)}
    return set()


def part_foot(blk, key, which):
    """Нижний занятый слой ('bottom') или верхний слой 11 ('top') части - множество вокселей."""
    cache = blk.__dict__.setdefault("_foot7", {})
    ck = (key, which)
    if ck in cache:
        return cache[ck]
    p = blk.parts[key]
    lay = p["rec"]["layers"]
    if p["set"] == "SYNTH":
        res = synth_foot(key[0], p["cls"], which) if (which == "bottom" and any(lay)) or \
            (which == "top" and lay[11]) else set()
    else:
        ids = loft_ids(p["set"], p["idx"])
        res = set()
        if ids:
            if which == "top":
                res = footprint(ids[11]) if lay[11] else set()
            else:
                for li in range(12):
                    if lay[li]:
                        res = footprint(ids[li])
                        break
    cache[ck] = res
    return res


def wall_on_object(blk, k, xy, wkey, below, carry):
    """b: несущий предмет этажом ниже В КЛЕТКЕ СТЕНЫ касается её основания. Возвращает число общих вокселей."""
    okey = below["o"].get(xy)
    if okey is None or okey not in carry:
        return 0
    return len(part_foot(blk, wkey, "bottom") & part_foot(blk, okey, "top"))


# ------------------------------------------------------------------ evaluate2 с a и b

def intact_carry(blk, flags, kw):
    cache = blk.__dict__.setdefault("_carry7", {})
    ck = (flags, tuple(sorted(kw.items())))
    if ck not in cache:
        saved = getattr(blk, "carry", None)
        evaluate2j(blk, frozenset(), flags, **kw)
        cache[ck] = frozenset(blk.carry)
        if saved is not None:
            blk.carry = saved
    return cache[ck]


def evaluate2j(blk, removed=frozenset(), flags="", C=2, L=12, mass_rule=True, order=2, carry_rule="any",
               run_c=2, roof_reach=1, **kw):
    """collapse_v6.evaluate2k с правилами a и b. Без a и b - evaluate2k без изменений."""
    if not any(f in flags for f in NEW_RULES) or "Z" not in flags:   # как X F k: только поверх плиты Z
        return M.evaluate2k(blk, removed, flags, C=C, L=L, mass_rule=mass_rule, order=order,
                            carry_rule=carry_rule, run_c=run_c, roof_reach=roof_reach, **kw)
    carry0 = None
    if removed and ("X" in flags or "F" in flags):
        carry0 = intact_carry(blk, flags, dict(C=C, L=L, mass_rule=mass_rule, order=order, carry_rule=carry_rule,
                                               run_c=run_c, roof_reach=roof_reach))
    if not removed:
        carry0 = None
    X = "X" in flags and carry0 is not None
    A = "A" in flags
    RA, RB = "a" in flags, "b" in flags
    cls = {key: V.eff_cls(key, p, flags) for key, p in blk.parts.items()}
    role = {key: p.get("role", "") for key, p in blk.parts.items()}
    attach = {key for key, p in blk.parts.items() if role[key] in ATTACH_ROLES or p.get("attach")}
    bearing = lambda key: cls[key] in V.BEARING      # noqa: E731
    special = (lambda key: role[key] in V.SPECIAL) if A else (lambda key: False)   # noqa: E731
    sup, carry, info = set(), set(), {}
    fallen_x = set()
    hangers = []
    contact = blk.__dict__.setdefault("_contact7", {})   # стена, держащаяся по b -> общих вокселей
    for z in range(blk.sz):
        lvl = blk.lv[z]
        live = {k: {xy: key for xy, key in lvl[k].items() if key not in removed} for k in cc.KINDS}
        if z == 0:
            for k in cc.KINDS:
                sup.update(live[k].values())
                carry.update(key for key in live[k].values() if bearing(key))
            continue
        below = blk.lv[z - 1]
        props = set()
        for (x, y), key in below["w"].items():
            if key in carry:
                props.update(((x, y), (x - 1, y)))
        for (x, y), key in below["n"].items():
            if key in carry:
                props.update(((x, y), (x, y - 1)))
        for (x, y), key in below["o"].items():
            if key in carry:
                props.add((x, y))
                for dx, dy in cc.EDGE_NB.get(blk.parts[key]["rec"]["big_wall"], ()):
                    props.add((x + dx, y + dy))
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
        roofc = {xy: key for xy, key in live["o"].items() if A and role[key] in ("ROOF", "TARP")}
        ranch = set()
        for (x, y), key in roofc.items():
            edges = [below["w"].get((x, y)), below["w"].get((x + 1, y)),
                     below["n"].get((x, y)), below["n"].get((x, y + 1)), below["o"].get((x, y))]
            if any(e in carry for e in edges if e) or \
                    (below["o"].get((x, y)) in sup and role.get(below["o"].get((x, y))) in ("ROOF", "TARP")):
                ranch.add((x, y))
        direct_b = direct | ranch
        if "Q" in flags:
            direct_b |= {(x, y) for (x, y) in floors - direct_b
                         if ((x + 1, y) in direct_b or (x - 1, y) in direct_b) and
                         ((x, y + 1) in direct_b or (x, y - 1) in direct_b)}
        okf, dist, best_l, strong = M.slab_floors6(blk, z, live, below, carry, floors, direct, ranch, direct_b,
                                                   C, L, flags, carry0)
        nobase = set()
        if X:
            for k in ("w", "n", "o"):
                for xy, key in live[k].items():
                    if not bearing(key) or special(key):
                        continue
                    under = below[k].get(xy)
                    if under is not None and under in carry0 and under not in carry:
                        nobase.add(key)
            x_fall_o = {xy for xy, key in live["o"].items() if key in nobase and xy not in msup and
                        xy not in strong}
            tier = {xy for xy in okf - strong if xy in x_fall_o or below["o"].get(xy) in fallen_x}
            okf -= tier
        for xy in floors:
            info[live["f"][xy]] = (xy in direct, dist.get(xy), best_l.get(xy))
            if xy in okf:
                sup.add(live["f"][xy])
        if "I" in flags:
            lint = M.lintels6(live, below, carry, bearing, strong) if "k" in flags else \
                V.lintels(live, below, carry, bearing)
        else:
            lint = set()
        for k, sides in (("w", lambda x, y: ((x, y), (x - 1, y))),
                         ("n", lambda x, y: ((x, y), (x, y - 1)))):
            for (x, y), key in live[k].items():
                under = below[k].get((x, y))
                on_obj = 0
                if RB:
                    on_obj = wall_on_object(blk, k, (x, y), key, below, carry)
                    if on_obj:
                        contact[key] = on_obj
                if key in nobase:
                    held_w = any(s in strong for s in sides(x, y)) or key in lint
                else:
                    held_w = any(s in okf for s in sides(x, y)) or under in carry or key in lint or on_obj > 0
                if held_w:
                    sup.add(key)
                    if bearing(key) and (carry_rule == "any" or under in carry or key in lint or on_obj > 0 or
                                         any(s in direct for s in sides(x, y))):
                        carry.add(key)
                elif key in nobase:
                    fallen_x.add(key)
        furn = {xy for xy, key in live["o"].items() if cls[key] == "furniture" and not special(key)}
        fsup = set()
        for (x, y), key in live["o"].items():
            if special(key):
                continue
            under = below["o"].get((x, y))
            walls = [live["w"].get((x, y)), live["w"].get((x + 1, y)),
                     live["n"].get((x, y)), live["n"].get((x, y + 1))]
            by_wall = any(w in carry for w in walls if w) and (not RA or key in attach)
            if key in nobase:
                held_o = (x, y) in msup or (x, y) in strong
            else:
                held_o = (x, y) in okf or (x, y) in msup or \
                    under in carry or (under in sup and cls[under] == "furniture") or by_wall
            if held_o:
                sup.add(key)
                if bearing(key) and (carry_rule == "any" or under in carry or
                                     (x, y) in direct or (x, y) in msup):
                    carry.add(key)
                if (x, y) in furn:
                    fsup.add((x, y))
            elif key in nobase:
                fallen_x.add(key)
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
        anch = set(ranch) | {xy for xy in roofc if xy in okf or xy in msup}
        dr = V.consoles(anch, set(roofc), roof_reach)
        for xy, d in dr.items():
            if d <= roof_reach:
                sup.add(roofc[xy])
        if "M" in flags:
            tset = {xy for xy, key in roofc.items() if role[key] == "TARP"}
            for xy in tset:
                nl = cc.beam(xy, tset, anch & tset)
                if nl is not None and nl <= V.L_TARP:
                    sup.add(roofc[xy])
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
        dr = V.consoles(rheld, rset, run_c)
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


def evaluate7(blk, removed=frozenset(), flags=MODEL, tie="all"):
    """M0j. Без a и b - collapse_v6b.evaluate6b (M0i2)."""
    removed = frozenset(removed)
    old_e2, old_ts, old_th = V.evaluate2, T.tree_structure, T.tree_hold
    V.evaluate2 = evaluate2j
    if "V" in flags:
        T.tree_structure = H.tree_structure5
    T.tree_hold = lambda b, r, c, ro, ca: G.tree_hold4(b, r, c, ro, ca, tie)
    try:
        return T.evaluate3(blk, removed, flags.replace("V", ""))
    finally:
        V.evaluate2, T.tree_structure, T.tree_hold = old_e2, old_ts, old_th


# ------------------------------------------------------------------ судья

class Base7(G.Base4):
    """Судья Base6b (UNSUPPORTED у M0i2, плюс непросмотренные опоры) с evaluate7 и кандидатами a, b."""

    def __init__(self, blk, disp, vessel=False, ver=None, foot=None, model=MODEL):
        self.blk, self.disp, self.vessel, self.ver, self.foot, self.model = blk, disp, vessel, ver, foot, model
        self.sup0, info = evaluate7(blk, frozenset(), model)
        self.light = P.light_beam(blk, self.sup0, info)
        self.by_cell = collections.defaultdict(list)
        for key in blk.parts:
            for c in T.part_cells(key):
                self.by_cell[c].append(key)
        self.alt0 = {e: evaluate7(blk, frozenset(), M.alt_flags(model, e))[0] for e in CANDIDATE_RULES}
        self.any0 = evaluate7(blk, frozenset(), model, tie="any")[0]
        self.unrev = any(p.get("role") in ("COLUMN", "TRUSS") and not p.get("rev") for p in blk.parts.values())
        self.nou0 = evaluate7(blk, frozenset(), model.replace("U", ""))[0] if self.unrev else None
        if foot is not None:
            self.set_foot(foot)

    def set_foot(self, foot):
        self.foot = foot
        self.ext = frozenset(k for k in self.blk.parts if (k[1], k[2], k[3]) not in foot)
        self.iso0 = evaluate7(self.blk, self.ext, self.model)[0]
        return self

    def judge(self, removed, extra=()):
        old4, oldc = G.evaluate4, G.CANDIDATE_RULES
        model = self.model

        def ev(blk, rm, flags=model, tie="all"):
            for e in CANDIDATE_RULES:
                if flags == model.replace(e, ""):
                    flags = M.alt_flags(model, e)
            return evaluate7(blk, rm, flags, tie)
        G.evaluate4, G.CANDIDATE_RULES = ev, CANDIDATE_RULES
        try:
            res = G.Base4.judge(self, removed, extra)
        finally:
            G.evaluate4, G.CANDIDATE_RULES = old4, oldc
        if self.unrev:
            removed = frozenset(removed)
            s_nou = evaluate7(self.blk, removed, model.replace("U", ""))[0]
            if self.fallen_of(self.nou0, s_nou, removed) != res["fallen"]:
                res["why"]["исход зависит от непросмотренной опоры (COLUMN/TRUSS)"] = 1
                res["status"] = "UNSUPPORTED"
        return res


# ------------------------------------------------------------------ замок

def read_lock():
    out = {}
    with open(LOCK, encoding=ENC) as f:
        for line in f:
            p = line.rstrip("\n").split(" sha256 ")
            if len(p) == 2:
                out[p[0]] = p[1]
    return out


def check_lock():
    lock = read_lock()
    bad = [p for p in LOCKED if lock.get(p) != M.sha(p)]
    if bad:
        raise SystemExit("замок M0j нарушен: " + ", ".join(bad))


def cmd_lock():
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(LOCK):
        raise SystemExit("замок уже есть: " + LOCK)
    lines = ["версия модели M0j обрушения (исследовательская), записано %s - до прогона" %
             time.strftime("%Y-%m-%d %H:%M:%S"),
             "флаги %s: M0i2 плюс a (предмет держится стеной своей клетки только при явном креплении: роли %s "
             "или пометка attach) и b (стена держится несущим предметом ниже в своей клетке, если нижний слой "
             "LOFT стены и верхний слой LOFT предмета имеют общий воксель)" % (MODEL, sorted(ATTACH_ROLES)),
             "кровля атриума правилом не меняется - тип конструкции задаёт разметка (collapse_ctype.py)",
             "оговорка: 0h и 0i - разработочные наборы (Q-32 и R-12 смотрелись в 0j), не независимая приёмка"]
    lines += ["%s sha256 %s" % (p, M.sha(p)) for p in LOCKED]
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


# ------------------------------------------------------------------ проверки

def models():
    return [("M0j", lambda blk, rm: evaluate7(blk, rm, MODEL)[0]),
            ("M0j без a", lambda blk, rm: evaluate7(blk, rm, MODEL.replace("a", ""))[0]),
            ("M0j без b", lambda blk, rm: evaluate7(blk, rm, MODEL.replace("b", ""))[0]),
            ("M0i2", lambda blk, rm: B.evaluate6b(blk, rm, M0I2)[0])]


def cmd_selfcheck():
    """1) evaluate7 без a и b = evaluate6b (M0i2) на всех целых блоках; 2) что a и b по отдельности и вместе
    меняют на целых блоках (стоят до боя): потери и новые удержанные, по ролям и записям."""
    check_lock()
    roles = V.load_roles()
    os.makedirs(OUT, exist_ok=True)
    diff = collections.Counter()
    by_rec = collections.Counter()
    contact_hist = collections.Counter()
    rows, nblk, same, t0 = [], 0, 0, time.time()
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None:
            continue
        V.apply_roles(blk, roles)
        nblk += 1
        base = B.evaluate6b(blk, frozenset(), M0I2)[0]
        mine = evaluate7(blk, frozenset(), M0I2)[0]
        same += base == mine
        for name, fl in (("M0j", MODEL), ("только a", M0I2 + "a"), ("только b", M0I2 + "b")):
            blk.__dict__.pop("_contact7", None)
            s = evaluate7(blk, frozenset(), fl)[0]
            lost = sorted(k for k in base - s if k[3] > 0)
            got = sorted(k for k in s - base if k[3] > 0)
            for k in lost:
                diff[(name, "роняет", k[0], blk.parts[k].get("role", ""))] += 1
                if name == "M0j":
                    by_rec[("роняет", blk.parts[k]["set"], blk.parts[k]["idx"], k[0], blk.parts[k].get("role", ""))] += 1
            for k in got:
                diff[(name, "держит", k[0], blk.parts[k].get("role", ""))] += 1
                if name == "M0j":
                    by_rec[("держит", blk.parts[k]["set"], blk.parts[k]["idx"], k[0], blk.parts[k].get("role", ""))] += 1
            if name == "только b":
                for k in got:
                    if k[0] in ("w", "n"):
                        c = blk.__dict__.get("_contact7", {}).get(k)
                        contact_hist["нет" if c is None else ("1-4" if c <= 4 else ("5-15" if c < 16 else "16+"))] += 1
            if (lost or got) and name == "M0j":
                rows.append([tname, bname, len(lost), len(got), T.compress(lost)[:400], T.compress(got)[:400]])
    cc.write_tsv(OUT + "/selfcheck_intact.tsv", ["terrain", "block", "drops", "holds", "drop_parts", "hold_parts"],
                 rows)
    cc.write_tsv(OUT + "/selfcheck_records.tsv", ["what", "set", "idx", "slot", "role", "parts"],
                 [list(k) + [v] for k, v in sorted(by_rec.items(), key=lambda kv: -kv[1])])
    res = {"blocks": nblk, "M0j без a и b = M0i2 (блоков)": same, "blocks_differ_M0j": len(rows),
           "by_kind": {" ".join(k): v for k, v in sorted(diff.items())},
           "b: общих вокселей у стен, удержанных только по b": dict(contact_hist),
           "sec": round(time.time() - t0)}
    with open(OUT + "/selfcheck.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


def cmd_synth():
    check_lock()
    import collapse_summary as S
    disp = S.disputed_records()
    os.makedirs(OUT, exist_ok=True)
    rows, judge_rows = [], []
    tot = collections.defaultdict(collections.Counter)
    for t in P.read_tsv(M.TRUTH):
        blk0 = M.synth_block(t["build"])
        rm = frozenset(cc.select(blk0, t["remove"]))
        must = cc.select(blk0, t["must_fall"]) - rm if t["must_fall"] else set()
        unsure = cc.select(blk0, t["unsure"]) - rm if t["unsure"] else set()
        stand = M.above_ground(blk0) - rm - must - unsure
        group = "рушится" if must else "стоит"
        for name, fn in models() + [("ничего не ронять", None)]:
            blk = M.synth_block(t["build"])
            sup = M.above_ground(blk) - rm if fn is None else fn(blk, rm)
            fell = M.above_ground(blk) - rm - set(sup)
            false, missed = sorted(stand & fell), sorted(must - fell)
            ok = not false and not missed
            c = tot[(name, group)]
            c["сценариев"] += 1
            c["верно"] += ok
            c["ложных частей"] += len(false)
            c["пропущенных частей"] += len(missed)
            rows.append([t["id"], t["check"], group, name, "да" if ok else "нет", len(false), len(missed),
                         T.compress(false), T.compress(missed)])
        st = Base7(M.synth_block(t["build"]), disp).judge(rm)
        judge_rows.append([t["id"], "M0j", st["status"], t["judge_expect"],
                           "да" if t["judge_expect"] in ("", st["status"]) else "нет",
                           json.dumps(st["why"], ensure_ascii=False)])
    cc.write_tsv(OUT + "/synth.tsv", ["id", "check", "group", "model", "ok", "false_falls", "missed_falls",
                                      "false_parts", "missed_parts"], rows)
    cc.write_tsv(OUT + "/synth_judge.tsv", ["id", "judge", "status", "expect", "ok", "why"], judge_rows)
    res = {"%s / %s" % k: dict(v) for k, v in sorted(tot.items())}
    with open(OUT + "/synth.json", "w", encoding=ENC) as f:
        json.dump({"by_model_group": res, "judge": [r[:5] for r in judge_rows]}, f, ensure_ascii=False, indent=1)
    for k, v in res.items():
        print(k, v)
    for r in judge_rows:
        print("   судья", *r[:5])


def cmd_dev():
    """Сценарии 0h и 0i (разработка): модель без судьи по частям и сценариям, судья M0j отдельно."""
    check_lock()
    import collapse_summary as S
    import collapse_span_probe as SP
    disp = S.disputed_records()
    ms_ = models() + [("ничего не ронять", None)]
    rows, per, meta = [], {}, {}
    os.makedirs(OUT, exist_ok=True)
    for st, i, kind, group, blk, rm, mf, ms in SP.scenarios():
        sid = st + " " + i
        try:
            js = Base7(blk, disp).judge(rm)["status"]
        except Exception as e:                              # noqa: BLE001
            js = "ERR " + type(e).__name__
        meta[sid] = (st, kind, group, js)
        for name, fn in ms_:
            if fn is None:
                s0 = B.evaluate6b(blk, frozenset(), M0I2)[0]
                sup = set(s0) - rm
            else:
                s0, sup = fn(blk, frozenset()), fn(blk, rm)
            missed = sorted(k for k in mf if k in sup and k in s0)
            false = sorted(k for k in ms if k not in sup and k in s0)
            per[(name, sid)] = (not missed and not false, len(false), len(missed))
            rows.append([st, i, kind, group, js, name, "да" if not missed and not false else "нет", len(false),
                         len(missed), T.compress(false)[:300], T.compress(missed)[:300]])
    cc.write_tsv(OUT + "/dev.tsv", ["set", "id", "kind", "group", "judge_M0j", "model", "ok", "false_falls",
                                    "missed_falls", "false_parts", "missed_parts"], rows)
    res = {}
    for st in ("0h", "0i"):
        for name, _ in ms_:
            for group in ("рушится", "стоит"):
                ids = [i for i, m in meta.items() if m[0] == st and m[2] == group]
                if not ids:
                    continue
                res["%s / %s / %s" % (st, name, group)] = {
                    "сценариев": len(ids), "верно": sum(per[(name, i)][0] for i in ids),
                    "ложных частей": sum(per[(name, i)][1] for i in ids),
                    "пропущенных частей": sum(per[(name, i)][2] for i in ids)}
    changed = {}
    for i in meta:
        a, b = per[("M0j", i)], per[("M0i2", i)]
        if a != b:
            changed[i] = {"M0j": a, "M0i2": b, "без a": per[("M0j без a", i)], "без b": per[("M0j без b", i)]}
    res["сценарии, где M0j отличается от M0i2 (верно, ложных, пропущенных)"] = changed
    res["судья M0j"] = dict(collections.Counter(m[3] for m in meta.values()))
    with open(OUT + "/dev.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"lock": cmd_lock, "selfcheck": cmd_selfcheck, "synth": cmd_synth, "dev": cmd_dev}.get(cmd)
    if fn is None:
        print(__doc__)
        sys.exit(0)
    sys.exit(fn() or 0)
