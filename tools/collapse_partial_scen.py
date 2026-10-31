#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Частичное обрушение 20 зданий пилотов 4-6 (рецензия 14.10, пункт 3): сценарии и ожидание по конструкции.

Прежние сценарии пилота (collapse_pilot_scen: ONE, HOLE, CORNER, SIDE, ALL) не проверяют частичное падение: ALL роняет
всё, остальные ждут «стоит». Здесь сценарий PFALL снимает опоры одной полосы участка, и ожидание считается ДО модели
по геометрии и ролям опор, без её пределов пролёта; файл и замок пишутся до первого прогона модели.

PFALL, участок этажа z (collapse_ctype.units), сторона W/N/E/S:
  * полоса R - первые k рядов клеток участка с этой стороны, остальное - nonR (не меньше 4 клеток);
  * снимается supports(R) - supports(nonR) (collapse_pilot_scen.supports: несущие части этажа z-1 по краям и в
    клетках): общая стена полосы и остатка остаётся;
  * берётся наименьшее k, при котором ожидание «должно упасть» содержит пол этажа z.
Ожидание по этажам L >= z, клетки этажа L - клетки участков L (пол и скаты):
  * опорная клетка этажа L - клетка, которой касается стоящая несущая часть этажа L-1 (стена w касается двух клеток,
    стена n - двух, слот o - своей);
  * клетка ПОТЕРЯНА, если до ближайшей опорной клетки по Чебышёву больше D_FALL = 2 (вылет консоли 3 клетки и больше)
    при том, что в целом здании до опорной было не больше 2 - большой зал без опор в ожидание не идёт;
  * клетка УСТОЙЧИВА, если до опорной клетки из ДОЛЖНЫХ СТОЯТЬ частей не больше D_STAND = 1; на этаже z - только
    клетки вне полосы;
  * пол и предмет клетки: должен упасть - клетка потеряна; должен стоять - клетка устойчива (предмет - ещё и если
    стоит на должной стоять несущей части слота o ниже);
  * стена: должна упасть - все её клетки с полом этажа потеряны и часть того же слота ниже снята или падает; должна
    стоять - часть того же слота ниже должна стоять, или все её клетки с полом устойчивы;
  * разметка SURFACE/ATTACHED: должна стоять - все цели должны стоять; должна упасть - все цели сняты или падают;
  * всё ниже этажа z, кроме снятого и прикреплённого к снятому, - должно стоять.
Остальное - свободная полоса: модель вправе решить и так, и так.

Устойчивые сценарии те же, что заперты в census/collapse/pilot4-6/pilot_scen.tsv (HOLE, CORNER) - не переписываются.

    py -3.13 tools\collapse_partial_scen.py define   census/collapse/partial/partial_scen.tsv и замок
    py -3.13 tools\collapse_partial_scen.py run      модель M0j4 против ожиданий: census/collapse/partial/model_result.tsv
"""
import hashlib
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ENC = "utf-8-sig"
OUT = "census/collapse/partial"
SCEN = OUT + "/partial_scen.tsv"
LOCK = OUT + "/partial_scen.lock.txt"
RESULT = OUT + "/model_result.tsv"
BEAR = {"WALL", "DOOR", "LOW", "COLUMN", "TRUSS", "MASS", "HULL"}
D_FALL = 2
D_STAND = 1
MAX_PER_BUILDING = 3
# 20 зданий выпуска игрокам (партии 4-6, без экспериментальных)
PLAYER20 = ["urban14", "urban17", "madurban22", "urban99", "madurban19", "madurban26", "culta18", "cultafarm21",
            "vilban50", "vilban55", "madurban23", "madurban24", "urbanjunk11", "urbanjunk36", "madurban25",
            "chemtown11", "chemtown12", "comrcurban50", "comrcurban51", "culta31"]
HEAD = ["building", "label", "scenario", "z", "unit_cells", "removed", "expect", "parts", "side", "strip",
        "must_fall", "must_stand"]
SIDES = {"W": lambda c: c[0], "E": lambda c: -c[0], "N": lambda c: c[1], "S": lambda c: -c[1]}


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def kstr(k):
    return "%s:%d,%d,%d" % k


def kparse(s):
    sl, xyz = s.split(":")
    x, y, z = map(int, xyz.split(","))
    return (sl, x, y, z)


def touch(k):
    sl, x, y, z = k
    if sl == "w":
        return {(x - 1, y), (x, y)}
    if sl == "n":
        return {(x, y - 1), (x, y)}
    return {(x, y)}


def bear(blk, k):
    return blk.parts[k].get("role") in BEAR


def dist(cells, src):
    """{клетка: расстояние Чебышёва до ближайшей из src} для клеток cells; без src - бесконечность."""
    src = list(src)
    big = 10 ** 6
    return {c: min((max(abs(c[0] - s[0]), abs(c[1] - s[1])) for s in src), default=big) for c in cells}


def modules():
    """Партии 4-6: (модуль, здание) для 20 зданий выпуска."""
    import collapse_pilot4_scen as P4
    import collapse_pilot5_scen as P5
    import collapse_pilot6_scen as P6
    out = []
    for M in (P4, P5, P6):
        for b in M.BUILDINGS:
            if b[3] in PLAYER20:
                out.append((M, b))
    if sorted(b[3] for _, b in out) != sorted(PLAYER20):
        raise SystemExit("не нашлись здания: %s" % sorted(set(PLAYER20) - {b[3] for _, b in out}))
    return out


def load():
    """[(террейн, блок, метка, label_en, блок)] - те же загрузчики партий 4-6, только 20 зданий выпуска."""
    import collapse_v7d as D
    D.install()                                   # evaluate7c считает M0j4, как заголовок игры
    res, C = [], None
    for M, (tn, bn, ru, en) in modules():
        keep = M.PILOT
        M.PILOT = [(tn, bn, ru)]
        try:
            C, CT, blds = M.load()
        finally:
            M.PILOT = keep
        for t, b, label, blk in blds:
            res.append((t, b, label, en, blk))
    return C, CT, res


def expectation(C, blk, z, strip, removed):
    """(должно упасть, должно стоять) по конструкции; strip - клетки полосы этажа z."""
    import collapse_ctype as CT
    removed = set(removed)
    tg = C.marked_parts(blk)
    floor = {}
    for L, fl, ro in CT.units(blk):
        floor.setdefault(L, set()).update((k[1], k[2]) for k in fl + ro)
    fall, stand = set(), set()
    for k in blk.parts:                           # ниже этажа z стоит всё, кроме снятого (разметка - по целям)
        if 0 < k[3] < z and k not in removed and k not in tg:
            stand.add(k)
    for L in range(z, blk.sz):
        cells = floor.get(L, set())
        below = [k for k in blk.parts if k[3] == L - 1 and bear(blk, k)]
        all_src = set().union(*(touch(k) for k in below)) if below else set()
        up_src = set().union(*(touch(k) for k in below if k not in removed and k not in fall)) if below else set()
        st_src = set().union(*(touch(k) for k in below if k in stand or (L - 1 == 0 and k not in removed))) \
            if below else set()
        d_all, d_up, d_st = dist(cells, all_src), dist(cells, up_src), dist(cells, st_src)
        lost = {c for c in cells if d_up[c] > D_FALL and d_all[c] <= D_FALL}
        safe = {c for c in cells if d_st[c] <= D_STAND and not (L == z and c in strip)}
        for k in [q for q in blk.parts if q[3] == L and q not in removed and q not in tg]:
            sl, x, y, _ = k
            if sl in ("f", "o"):
                under = blk.lv[L - 1]["o"].get((x, y))
                if (x, y) in lost and not (sl == "o" and under and bear(blk, under) and under not in fall
                                           and under not in removed):
                    fall.add(k)
                elif (x, y) in safe or (sl == "o" and under and bear(blk, under) and under in stand):
                    stand.add(k)
            else:
                under = blk.lv[L - 1][sl].get((x, y))
                tc = touch(k) & cells
                if tc and tc <= lost and (under is None or under in removed or under in fall):
                    fall.add(k)
                elif (under is not None and (under in stand or (L - 1 == 0 and under not in removed))) or \
                        (tc and tc <= safe):
                    stand.add(k)
    # разметка: по целям (цели этажом ниже уже решены, цели того же этажа - повтор до неподвижной точки)
    changed = True
    while changed:
        changed = False
        for k, (kind, ts) in tg.items():
            if k in removed or k in fall or k in stand or k[3] < 1:
                continue
            if not ts:
                continue
            if all(q in removed or q in fall for q in ts):
                fall.add(k)
                changed = True
            elif all(q in stand or (q[3] == 0 and q not in removed) for q in ts):
                stand.add(k)
                changed = True
    return fall, stand


def scenarios(PS, CT, C, blk):
    """[(сторона, z, клетки участка, полоса, снятое, должно упасть, должно стоять)] - до MAX_PER_BUILDING."""
    units = sorted(CT.units(blk), key=lambda u: -len(u[1]))
    res = []
    for z, fl, ro in units:
        cells = sorted({(k[1], k[2]) for k in fl})
        if len(cells) < 8:
            continue
        for side, key in SIDES.items():
            rows = sorted({key(c) for c in cells})
            for kk in range(1, len(rows)):
                strip = {c for c in cells if key(c) in rows[:kk]}
                rest = set(cells) - strip
                if len(rest) < 4:
                    break
                rm = PS.supports(blk, z, strip) - PS.supports(blk, z, rest)
                if not rm:
                    continue
                fall, stand = expectation(C, blk, z, strip, rm)
                if any(k[0] == "f" and k[3] == z for k in fall):
                    res.append((side, z, cells, strip, rm, fall, stand))
                    break
            if len(res) >= MAX_PER_BUILDING:
                return res
    return res


def cmd_define():
    import collapse_pilot_scen as PS
    os.makedirs(OUT, exist_ok=True)
    C, CT, blds = load()
    rows, none = [], []
    for tn, bn, label, en, blk in blds:
        sc = scenarios(PS, CT, C, blk)
        if not sc:
            none.append(en)
        for side, z, cells, strip, rm, fall, stand in sc:
            rows.append(["%s/%s" % (tn, bn), label, "PFALL", str(z), str(len(cells)), " ".join(map(kstr, sorted(rm))),
                         "PARTIAL", " ".join("%d,%d" % c for c in cells), side,
                         " ".join("%d,%d" % c for c in sorted(strip)), " ".join(map(kstr, sorted(fall))),
                         " ".join(map(kstr, sorted(stand)))])
            print("%-14s %s z%d участок %d полоса %d: снято %d, должно упасть %d (пол %d), должно стоять %d" % (
                en, side, z, len(cells), len(strip), len(rm), len(fall),
                sum(1 for k in fall if k[0] == "f"), len(stand)))
    with open(SCEN, "w", encoding=ENC) as f:
        f.write("\t".join(HEAD) + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("# замок сценариев частичного обрушения, поставлен ДО прогона модели\n")
        f.write("time\t%s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        for p in (SCEN, "tools/collapse_partial_scen.py"):
            f.write("%s\t%s\n" % (p, sha(p)))
    print("сценариев PFALL %d; зданий без PFALL %d: %s" % (len(rows), len(none), " ".join(none) or "-"))


def check_lock():
    for ln in open(LOCK, encoding=ENC).read().splitlines():
        if ln.startswith("#") or ln.startswith("time"):
            continue
        p, h = ln.split("\t")
        if sha(p) != h:
            raise SystemExit("замок сценариев частичного обрушения нарушен: %s" % p)


def rows():
    lines = open(SCEN, encoding=ENC).read().splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:]]


def verdict(r, fallen, base):
    """PASS - всё «должно упасть» упало и ничего из «должно стоять» не упало; части, которые модель не держит и в
    целом здании (base), в счёт не идут - их нет и в игре."""
    mf = {kparse(s) for s in r["must_fall"].split()} & base
    ms = {kparse(s) for s in r["must_stand"].split()}
    miss, extra = mf - fallen, ms & fallen
    return ("PASS" if not miss and not extra else "FAIL"), miss, extra


def cmd_run():
    check_lock()
    C, CT, blds = load()
    by = {"%s/%s" % (tn, bn): blk for tn, bn, label, en, blk in blds}
    base = {b: C.evaluate7c(blk, frozenset())[0] for b, blk in by.items()}
    out, tally = [], {}
    for r in rows():
        blk = by[r["building"]]
        rm = frozenset(kparse(s) for s in r["removed"].split())
        held = C.evaluate7c(blk, rm)[0]
        fallen = {k for k in base[r["building"]] if k not in held and k not in rm and k[3] > 0}
        v, miss, extra = verdict(r, fallen, base[r["building"]])
        tally[v] = tally.get(v, 0) + 1
        free = fallen - {kparse(s) for s in r["must_fall"].split()}
        out.append([r["building"], r["label"], r["side"], r["z"], v, str(len(fallen)),
                    str(len(r["must_fall"].split())), str(len(miss)), str(len(extra)), str(len(free)),
                    " ".join(map(kstr, sorted(miss)[:6])), " ".join(map(kstr, sorted(extra)[:6]))])
        print("%-34s %s z%s  %s  упало %d, ждали %d, не упало %d, лишнего %d, свободная полоса %d" % (
            r["building"], r["side"], r["z"], v, len(fallen), len(r["must_fall"].split()), len(miss), len(extra),
            len(free)))
    with open(RESULT, "w", encoding=ENC) as f:
        f.write("\t".join(["building", "label", "side", "z", "verdict", "fallen", "must_fall", "missed",
                           "must_stand_fallen", "fallen_free_band", "missed_examples", "extra_examples"]) + "\n")
        for o in out:
            f.write("\t".join(o) + "\n")
    print(tally)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"define": cmd_define, "run": cmd_run}[sys.argv[1]]()
