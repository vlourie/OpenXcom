#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот 3 обрушения: модель M0j4 = M0j3 (collapse_v7c, разметка v2) плюс консоль стены. M0j3 и всё под её
замками (collapse_v7, v7b, v7c, v6, attach) не меняются - M0j4 живёт только здесь.

Зачем: в M0j3 стена без опоры снизу держится только перемычкой collapse_v6.lintels6 (ряд до 4 клеток, ОБА конца
которого упираются в базу или угол) или плитой рядом. Держания с одной стороны нет, и в пилоте 3 у амбаров бандитов
по 6 сценариев «должно стоять» роняли стены: перемычку над воротами после снятия одного её конца, перегородку,
упёртую в дверь, стены угла над снятым углом (census/collapse/pilot3/fail_cases.md).

Консоль стены (W):
  * ряд несущих стен (w тянется по y, n - по x) без опоры снизу держится, если он упирается в базу (несущая стена
    той же линии на несущем или на плите) или в угол (перпендикулярная база в точке стыка) хотя бы с ОДНОЙ стороны,
    а другая сторона свободна (конец ряда, дверь, проём, не несущая стена);
  * длина ряда - не больше WC = 2 клеток;
  * стена, которую держит только консоль (нет в перемычках lintels6, нет плиты рядом, несущего под ней и предмета
    под основанием), держится, но несущей не становится: на неё не опирается ни пол, ни стена над ней.
Перемычка с двух сторон - как в M0j3. Без снятых частей консоль ничего не роняет: она только добавляет держание.

Проба до введения (блокнот сессии 14.10, те же правила): амбары бандитов FAIL в участке 6 -> 1 каждый, амбар фермы
9 -> 7, бункер и сарай без изменений, сценарии ALL - PASS; 0h пропущено 1 -> 8 (R-12), 0i 1267 -> 1278; целые блоки
не держится 169 413 -> 168 785, нового падения нет.

    py -3.13 tools\collapse_v7d.py lock      замок M0j4 (census/collapse/pilot3/m0j4.lock.txt)
    py -3.13 tools\collapse_v7d.py dev       сценарии 0h и 0i: M0j3 против M0j4
    py -3.13 tools\collapse_v7d.py intact    целые блоки: M0j3 против M0j4
    py -3.13 tools\collapse_v7d.py pilots    сценарии пилотов 2 и 3 (замки сценариев не меняются):
                                             census/collapse/stage0m/pilot_result_m0j4.tsv, pilot3/pilot_result_m0j4.tsv
Другие инструменты переводятся на M0j4 вызовом install(): collapse_v7c.evaluate7c в этом процессе считает M0j4.
"""
import collections
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
import collapse_v4 as G                           # noqa: E402
import collapse_v5 as H                           # noqa: E402
import collapse_v6 as M                           # noqa: E402
import collapse_v7 as J                           # noqa: E402
import collapse_v7c as C7                         # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/pilot3"
LOCK = OUT + "/m0j4.lock.txt"
NAME = "M0j4"
WC = 2                                            # длина консоли стены, клеток
LOCKED = ["tools/collapse_v7d.py"]
ORIG7 = C7.ORIG7                                  # ядро M0j3 (J.evaluate7), до install()


# ------------------------------------------------------------------ консоль стены

def wall_consoles(live, below, carry, bearing, strong, lint, wc=WC):
    """Стены, которые держит консоль (и нет в перемычках lint): ряд до wc клеток, упёртый в базу или угол хотя бы
    с одной стороны. База и угол - как в collapse_v6.lintels6."""
    def based(k, xy, key):
        if not bearing(key):
            return False
        if below[k].get(xy) in carry:
            return True
        x, y = xy
        sides = ((x, y), (x - 1, y)) if k == "w" else ((x, y), (x, y - 1))
        return any(s in strong for s in sides)

    base = {k: {xy for xy, key in live[k].items() if based(k, xy, key)} for k in ("w", "n")}

    def corner(k, px, py):
        if k == "w":
            return (px - 1, py) in base["n"] or (px, py) in base["n"]
        return (px, py - 1) in base["w"] or (px, py) in base["w"]

    out = set()
    for k, (dx, dy) in (("w", (0, 1)), ("n", (1, 0))):
        lw = live[k]
        for (x, y), key in lw.items():
            if key in lint or below[k].get((x, y)) in carry or not bearing(key):
                continue
            run, anchored = 1, 0
            for sgn in (1, -1):
                cx, cy = x, y
                while True:
                    px, py = (cx + dx, cy + dy) if sgn > 0 else (cx, cy)
                    if corner(k, px, py):
                        anchored += 1
                        break
                    cx += dx * sgn
                    cy += dy * sgn
                    nk = lw.get((cx, cy))
                    if nk is None or not bearing(nk):
                        break                      # свободный конец
                    if (cx, cy) in base[k]:
                        anchored += 1
                        break
                    run += 1
            if anchored >= 1 and run <= wc:
                out.add(key)
    return out


# ------------------------------------------------------------------ ядро: collapse_v7.evaluate2j с консолью

def intact_carry(blk, flags, kw):
    cache = blk.__dict__.setdefault("_carry7d", {})
    ck = (flags, tuple(sorted(kw.items())))
    if ck not in cache:
        saved = getattr(blk, "carry", None)
        evaluate2w(blk, frozenset(), flags, **kw)
        cache[ck] = frozenset(blk.carry)
        if saved is not None:
            blk.carry = saved
    return cache[ck]


def evaluate2w(blk, removed=frozenset(), flags="", C=2, L=12, mass_rule=True, order=2, carry_rule="any",
               run_c=2, roof_reach=1, **kw):
    """collapse_v7.evaluate2j (M0j3) плюс консоль стены (wall_consoles): держится, но несущей не становится.
    Без a и b - collapse_v6.evaluate2k без изменений, как в M0j3."""
    if not any(f in flags for f in J.NEW_RULES) or "Z" not in flags:   # как X F k: только поверх плиты Z
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
    attach = {key for key, p in blk.parts.items() if role[key] in J.ATTACH_ROLES or p.get("attach")}
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
        cons = set()
        if "I" in flags:
            lint = M.lintels6(live, below, carry, bearing, strong) if "k" in flags else \
                V.lintels(live, below, carry, bearing)
            if "k" in flags:
                cons = wall_consoles(live, below, carry, bearing, strong, lint)
                lint = lint | cons
        else:
            lint = set()
        for k, sides in (("w", lambda x, y: ((x, y), (x - 1, y))),
                         ("n", lambda x, y: ((x, y), (x, y - 1)))):
            for (x, y), key in live[k].items():
                under = below[k].get((x, y))
                on_obj = 0
                if RB:
                    on_obj = J.wall_on_object(blk, k, (x, y), key, below, carry)
                    if on_obj:
                        contact[key] = on_obj
                if key in nobase:
                    held_w = any(s in strong for s in sides(x, y)) or key in lint
                else:
                    held_w = any(s in okf for s in sides(x, y)) or under in carry or key in lint or on_obj > 0
                cons_only = key in cons and not (any(s in okf for s in sides(x, y)) or under in carry or
                                                 on_obj > 0)
                if held_w:
                    sup.add(key)
                    if bearing(key) and not cons_only and (carry_rule == "any" or under in carry or key in lint or on_obj > 0 or
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


def evaluate7w(blk, removed=frozenset(), flags=J.MODEL, tie="all"):
    """collapse_v7.evaluate7 с ядром evaluate2w."""
    removed = frozenset(removed)
    old_e2, old_ts, old_th = V.evaluate2, T.tree_structure, T.tree_hold
    V.evaluate2 = evaluate2w
    if "V" in flags:
        T.tree_structure = H.tree_structure5
    T.tree_hold = lambda b, r, c, ro, ca: G.tree_hold4(b, r, c, ro, ca, tie)
    try:
        return T.evaluate3(blk, removed, flags.replace("V", ""))
    finally:
        V.evaluate2, T.tree_structure, T.tree_hold = old_e2, old_ts, old_th


def install():
    """С этого момента collapse_v7c.evaluate7c (и всё, что её зовёт) считает M0j4. Разметка - v2."""
    import collapse_attach_v2 as A2
    check_lock()
    C = A2.use()
    C.ORIG7 = evaluate7w
    return C


def uninstall():
    C7.ORIG7 = ORIG7


def evaluate7d(blk, removed=frozenset(), flags=C7.MODEL, tie="all"):
    """M0j4 одним вызовом, без install(): разметка та, что задана в collapse_v7c."""
    old = C7.ORIG7
    C7.ORIG7 = evaluate7w
    try:
        return C7.evaluate7c(blk, removed, flags, tie)
    finally:
        C7.ORIG7 = old


# ------------------------------------------------------------------ замок

def check_lock():
    C7.check_lock()
    lock = {}
    with open(LOCK, encoding=ENC) as f:
        for line in f:
            p = line.rstrip("\n").split(" sha256 ")
            if len(p) == 2:
                lock[p[0]] = p[1]
    bad = [p for p in LOCKED if lock.get(p) != M.sha(p)]
    if bad:
        raise SystemExit("замок M0j4 нарушен: " + ", ".join(bad))


def cmd_lock():
    C7.check_lock()
    lines = ["версия модели M0j4 обрушения (пилот 3), записано %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "M0j3 (collapse_v7c, флаги %s, разметка v2) без изменений, плюс консоль стены WC=%d: ряд несущих стен "
             "без опоры снизу, упёртый в базу или угол хотя бы с одной стороны, держится; держится только консолью - "
             "не несущий. Правило проверено пробой до введения (census/collapse/pilot3/fail_cases.md)" % (C7.MODEL, WC)]
    lines += ["%s sha256 %s" % (p, M.sha(p)) for p in LOCKED]
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


# ------------------------------------------------------------------ проверки

def both(blk, rm):
    return C7.evaluate7c(blk, rm, C7.MODEL)[0], evaluate7d(blk, rm)[0]


def cmd_dev():
    import collapse_span_probe as SP
    check_lock()
    agg = collections.Counter()
    diff = []
    for st, i, kind, group, blk, rm, mf, ms in SP.scenarios():
        C7.apply_marks(blk)
        e0, e1 = both(blk, frozenset())
        s0, s1 = both(blk, rm)
        r = {}
        for tag, base, sup in (("M0j3", e0, s0), ("M0j4", e1, s1)):
            missed = sorted(k for k in mf if k in sup and k in base)
            false = sorted(k for k in ms if k not in sup and k in base)
            ok = not missed and not false
            agg[(st, group, tag, "n")] += 1
            agg[(st, group, tag, "ok")] += ok
            agg[(st, group, tag, "false")] += len(false)
            agg[(st, group, tag, "missed")] += len(missed)
            r[tag] = (ok, len(false), len(missed))
        if r["M0j3"] != r["M0j4"]:
            diff.append((st, i, kind, group, r["M0j3"], r["M0j4"]))
    for st in ("0h", "0i"):
        for group in ("рушится", "стоит"):
            if not agg[(st, group, "M0j3", "n")]:
                continue
            print("%s %-8s" % (st, group), " | ".join(
                "%s: верно %d/%d ложных %d пропущено %d" % (t, agg[(st, group, t, "ok")], agg[(st, group, t, "n")],
                                                           agg[(st, group, t, "false")], agg[(st, group, t, "missed")])
                for t in ("M0j3", "M0j4")))
    print("сценариев с другим исходом:", len(diff))
    for d in diff:
        print("  ", d)


def cmd_intact():
    import collapse_v7b as K
    check_lock()
    t0 = time.time()
    tot = collections.Counter()
    for tname, bname, blk in K.intact_blocks():
        C7.apply_marks(blk)
        up = [k for k in blk.parts if k[3] > 0]
        a, b = both(blk, frozenset())
        tot["блоков"] += 1
        tot["частей выше z0"] += len(up)
        tot["не держится M0j3"] += sum(1 for k in up if k not in a)
        tot["не держится M0j4"] += sum(1 for k in up if k not in b)
        tot["M0j4 роняет, M0j3 держит"] += sum(1 for k in up if k in a and k not in b)
        tot["M0j4 держит, M0j3 нет"] += sum(1 for k in up if k not in a and k in b)
    print(dict(tot), "сек", round(time.time() - t0))


def cmd_pilots():
    """Сценарии пилотов 2 и 3 под M0j4 тем же cmd_run, что M0j3; результат - в *_m0j4.tsv рядом с прежним."""
    import collapse_pilot_scen as PS
    import collapse_pilot3_scen as P3
    install()
    PS.RESULT = PS.OUT + "/pilot_result_m0j4.tsv"
    print("== пилот 2:", PS.RESULT)
    PS.cmd_run()
    P3.use()
    PS.RESULT = PS.OUT + "/pilot_result_m0j4.tsv"
    print("== пилот 3:", PS.RESULT)
    PS.cmd_run()


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    {"lock": cmd_lock, "dev": cmd_dev, "intact": cmd_intact, "pilots": cmd_pilots}[sys.argv[1]]()
