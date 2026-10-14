#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0j обрушения зданий: различающий опыт по пролёту. Модель M0i2 (collapse_v6b, замок
stage0i/rules2.lock.txt) не меняется: пределы пролёта и консоли подменяются В ПАМЯТИ на время прогона
(обёртка collapse_v6.evaluate2k с другими L и C, collapse_v3.L_ROOF), файлы модели не трогаются.

Вопрос: пропуски сценариев BALL (сняты все внутренние опоры, модель держит плиту) - из-за предела пролёта или нет.
Если из-за пролёта, то при меньшем L пропуски уходят. Цена меньшего L - ложные обрушения там, где пролёт вырос,
а конструкция должна стоять (BIN, BLINE, LSUP/LWALL, 'стоит' 0h) и потери на целых блоках до боя.

Наборы 0i и 0h здесь - материал разработки, не приёмка (их ответы уже видены).

    py -3.13 tools\collapse_span_probe.py sweep    сценарии 0i и 0h при каждом наборе пределов
    py -3.13 tools\collapse_span_probe.py mech     что держит каждую пропущенную часть (M0i2) и при каком L она падает
    py -3.13 tools\collapse_span_probe.py intact   потери на целых блоках до боя при каждом наборе пределов
"""
import collections
import contextlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_census as cc                      # noqa: E402
import collapse_v2 as V                           # noqa: E402
import collapse_v3 as T                           # noqa: E402
import collapse_pilot as P                        # noqa: E402
import collapse_v6 as M                           # noqa: E402
import collapse_v6b as B                          # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/stage0j"
# имя, L (пролёт плиты), L_ROOF (кровля над помещением), C (консоль)
CONFIGS = [("base L12 R16 C2", 12, 16, 2),
           ("L10", 10, 10, 2), ("L8", 8, 8, 2), ("L6", 6, 6, 2), ("L5", 5, 5, 2), ("L4", 4, 4, 2),
           ("L3", 3, 3, 2), ("L2", 2, 2, 2),
           ("L12 R16 C1", 12, 16, 1), ("L12 R16 C0", 12, 16, 0), ("L4 C0", 4, 4, 0), ("L2 C0", 2, 2, 0)]
WEAKEST = ("L2 C0", 2, 2, 0)
# порядок ослабления для 'с какого набора часть падает': пролёт при C2, потом консоль
FALL_ORDER = ["L10", "L8", "L6", "L5", "L4", "L3", "L2", "L4 C0", "L2 C0"]


@contextlib.contextmanager
def limits(L, R, C, mass_rule=True):
    orig, old_r = M.evaluate2k, T.L_ROOF

    def e2(blk, removed=frozenset(), flags="", **kw):
        kw.setdefault("L", L)
        kw.setdefault("C", C)
        kw.setdefault("mass_rule", mass_rule)
        return orig(blk, removed, flags, **kw)
    M.evaluate2k, T.L_ROOF = e2, R
    try:
        yield
    finally:
        M.evaluate2k, T.L_ROOF = orig, old_r


def run(blk, rm):
    return B.evaluate6b(blk, rm, B.MODEL)


def scenarios():
    """(набор, id, вид, группа, blk, rm, must_fall, must_stand)."""
    import collapse_review5 as R5
    import collapse_review6 as R6
    roles = V.load_roles()
    out = []
    task, blocks, crops = R6.load_task_blocks(roles)
    pm = {r["id"]: r for r in P.read_tsv(R6.PICKED)}
    for e in P.read_tsv(R6.EXPECT):
        t = task[e["id"]]
        blk = blocks[(t["terrain"].upper(), t["block"].upper())]
        out.append(("0i", e["id"], pm[e["id"]]["kind"], blk, t, e))
    task, blocks = R5.load_task_blocks(roles)
    pm = {r["id"]: r for r in P.read_tsv(R5.PICKED)}
    for e in P.read_tsv(R5.EXPECT):
        t = task[e["id"]]
        blk = blocks[(t["terrain"].upper(), t["block"].upper())]
        out.append(("0h", e["id"], pm[e["id"]]["kind"], blk, t, e))
    res = []
    for st, i, kind, blk, t, e in out:
        rm = frozenset(cc.select(blk, t["remove"]))
        mf = cc.select(blk, e["must_fall"]) - rm
        ms = cc.select(blk, e["must_stand"]) - rm
        res.append((st, i, kind, "рушится" if mf else "стоит", blk, rm, mf, ms))
    return res


def cmd_sweep():
    B.check_lock()
    sc = scenarios()
    rows, agg = [], collections.defaultdict(lambda: [0, 0, 0, 0])
    t0 = time.time()
    for name, L, R, C in CONFIGS:
        with limits(L, R, C):
            for st, i, kind, group, blk, rm, mf, ms in sc:
                s0, sup = run(blk, frozenset())[0], run(blk, rm)[0]
                missed = sorted(k for k in mf if k in sup and k in s0)
                false = sorted(k for k in ms if k not in sup and k in s0)
                ok = not missed and not false
                rows.append([name, st, i, kind, group, "да" if ok else "нет", len(false), len(missed),
                             T.compress(false)[:300], T.compress(missed)[:300]])
                for key in ((name, st, group), (name, st, kind), (name, "все", group)):
                    a = agg[key]
                    a[0] += 1
                    a[1] += ok
                    a[2] += len(false)
                    a[3] += len(missed)
        print("%-18s %4.0f с" % (name, time.time() - t0), flush=True)
    os.makedirs(OUT, exist_ok=True)
    cc.write_tsv(OUT + "/span_sweep.tsv", ["config", "set", "id", "kind", "group", "ok", "false_falls",
                                           "missed_falls", "false_parts", "missed_parts"], rows)
    res = {" / ".join(k): {"сценариев": v[0], "верно": v[1], "ложных": v[2], "пропущено": v[3]}
           for k, v in agg.items()}
    with open(OUT + "/span_sweep.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for k, v in res.items():
        print(k, v)


def mechanism(blk, key, sup, info, L, R):
    kind, x, y, z = key
    if kind == "f":
        d, dist, bl = info.get(key, (False, None, None))
        if d:
            return "f прямая опора", None
        lim = R if T.floor_types(blk).get(key) == ("помещ", "кровля") else L
        if bl == 0:
            return "f балка 2-го прохода или угол Q (длина не сохранена)", 0
        if bl is not None and bl <= lim:
            return "f балка", bl
        return "f консоль", dist
    lv = blk.lv[z]
    under = blk.lv[z - 1][kind].get((x, y)) if z > 0 else None
    if kind in ("w", "n"):
        sides = ((x, y), (x - 1, y)) if kind == "w" else ((x, y), (x, y - 1))
        if any(lv["f"].get(s) in sup for s in sides):
            return kind + " на удержанном полу", None
        if under in sup:
            return kind + " на стене ниже", None
        return kind + " перемычка/иное", None
    if lv["f"].get((x, y)) in sup:
        return "o на удержанном полу", None
    if under in sup:
        return "o на предмете ниже", None
    walls = [lv["w"].get((x, y)), lv["w"].get((x + 1, y)), lv["n"].get((x, y)), lv["n"].get((x, y + 1))]
    if any(w in sup for w in walls if w):
        return "o стенами клетки (пол снят или не держится)", None
    return "o иное (масса, мебель, скат)", None


def cmd_mech():
    """M0i2 (base): что держит каждую пропущенную часть; при каком наибольшем L из перебора она падает."""
    B.check_lock()
    sc = scenarios()
    sweep = [c for n in FALL_ORDER for c in CONFIGS if c[0] == n]
    falls_at = {}
    for name, L, R, C in sweep:
        with limits(L, R, C):
            for st, i, kind, group, blk, rm, mf, ms in sc:
                if not mf:
                    continue
                sup = run(blk, rm)[0]
                for k in mf:
                    if k not in sup and (st, i, k) not in falls_at:
                        falls_at[(st, i, k)] = name
    weak = {}
    with limits(*WEAKEST[1:]):
        for st, i, kind, group, blk, rm, mf, ms in sc:
            if mf:
                weak[(st, i)] = run(blk, rm)
    rows = []
    cnt = collections.Counter()
    cnt_w = collections.Counter()
    bl_hist = collections.Counter()
    for st, i, kind, group, blk, rm, mf, ms in sc:
        if not mf:
            continue
        s0 = run(blk, frozenset())[0]
        sup, info = run(blk, rm)
        ws, wi = weak[(st, i)]
        for k in sorted(mf):
            if k not in sup or k not in s0:
                continue
            mech, n = mechanism(blk, k, sup, info, 12, 16)
            fa = falls_at.get((st, i, k), "не падает и при L2 C0")
            mw = mechanism(blk, k, ws, wi, 2, 2)[0] if k in ws else "-"
            cnt[(st, kind, mech, fa)] += 1
            if k in ws:
                cnt_w[(st, kind, mw)] += 1
            if mech == "f балка":
                bl_hist[(st, kind, n)] += 1
            rows.append([st, i, kind, "%s:%d:%d:%d" % k, mech, "" if n is None else n, fa, mw])
    os.makedirs(OUT, exist_ok=True)
    cc.write_tsv(OUT + "/missed_mech.tsv", ["set", "id", "kind", "part", "mechanism", "n", "falls_from",
                                            "mechanism_L2C0"], rows)
    res = {"по механизму": {" / ".join(map(str, k)): v for k, v in sorted(cnt.items())},
           "держится и при L2 C0 - чем": {" / ".join(map(str, k)): v for k, v in sorted(cnt_w.items())},
           "расстояние между опорами у полов на балке": {" / ".join(map(str, k)): v
                                                         for k, v in sorted(bl_hist.items())}}
    with open(OUT + "/missed_mech.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


def cmd_intact():
    """Целые блоки до боя: сколько частей выше земли M0i2 держит при base и теряет при меньших пределах."""
    B.check_lock()
    roles = V.load_roles()
    blocks = []
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is not None:
            V.apply_roles(blk, roles)
            blocks.append((tname, bname, blk))
    base = {}
    with limits(12, 16, 2):
        for tname, bname, blk in blocks:
            base[(tname, bname)] = run(blk, frozenset())[0]
    res, rows = {}, []
    t0 = time.time()
    for name, L, R, C in CONFIGS[1:]:
        lost_k = collections.Counter()
        nb = 0
        with limits(L, R, C):
            for tname, bname, blk in blocks:
                s = run(blk, frozenset())[0]
                lost = [k for k in base[(tname, bname)] - s if k[3] > 0]
                if lost:
                    nb += 1
                    for k in lost:
                        lost_k[k[0]] += 1
                    rows.append([name, tname, bname, len(lost), T.compress(sorted(lost))[:300]])
        res[name] = {"блоков": len(blocks), "блоков с потерями": nb, "частей": sum(lost_k.values()),
                     "по видам": dict(lost_k)}
        print(name, res[name], "%.0f с" % (time.time() - t0), flush=True)
    os.makedirs(OUT, exist_ok=True)
    cc.write_tsv(OUT + "/intact_limits.tsv", ["config", "terrain", "block", "lost", "parts"], rows)
    with open(OUT + "/intact_limits.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"sweep": cmd_sweep, "mech": cmd_mech, "intact": cmd_intact}.get(cmd)
    if fn is None:
        print(__doc__)
        sys.exit(0)
    sys.exit(fn() or 0)
