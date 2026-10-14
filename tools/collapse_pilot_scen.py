#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0m обрушения зданий: сценарии первого игрового пилота на двух зданиях, проверка моделью «M0j3, разметка v2».

Здания (рецензия 0l: один амбар и бункер, пещера отдельно):
  * амбар  - CULTA / STR_LOC_DOOMED_FARM_24@28,18-41,41, двухэтажный дом-амбар (z0 стены, z1 пол и стены, z2 кровля);
  * бункер - GOVT_BASE_DEFENSE / GOVBASE_D_08, плита 7x7 на z1 по стенам z0.

Сценарии строятся правилом, а не руками, и пишутся в файл ДО прогона (define), ожидание - словами по смыслу, без
пределов пролёта (они экспериментальные):
  ONE    - снята одна опора (по очереди каждая)          -> стоит: падает только то, что крепилось к снятому;
  HOLE   - дыра 5 клеток (крест) в середине перекрытия    -> стоит: остальное перекрытие на месте;
  CORNER - у угла снято по две опоры с каждой стороны     -> стоит;
  SIDE   - снята вся сторона опор (западная)             -> ожидания нет: ответ зависит от пределов пролёта,
                                                              результат только показывается;
  ALL    - сняты все опоры перекрытия                    -> обвал: падает всё перекрытие и всё, что на нём.
Опора перекрытия на этаже z - стены (w, n) по краям его клеток и несущие части слота o (WALL, COLUMN, TRUSS, MASS,
HULL) в его клетках на этаже z-1; двери тоже снимаются (как часть стены).

Модель и разметка под замками этапа 0l не меняются: collapse_attach_v2.use(), collapse_v7c.evaluate7c.

    py -3.13 tools\collapse_pilot_scen.py define   census/collapse/stage0m/pilot_scen.tsv и замок
    py -3.13 tools\collapse_pilot_scen.py run      результат census/collapse/stage0m/pilot_result.tsv
"""
import hashlib
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ENC = "utf-8-sig"
OUT = "census/collapse/stage0m"
SCEN = OUT + "/pilot_scen.tsv"
LOCK = OUT + "/pilot_scen.lock.txt"
RESULT = OUT + "/pilot_result.tsv"
PILOT = [("CULTA", "STR_LOC_DOOMED_FARM_24@28,18-41,41", "амбар"), ("GOVT_BASE_DEFENSE", "GOVBASE_D_08", "бункер")]
BEAR = {"WALL", "DOOR", "LOW", "COLUMN", "TRUSS", "MASS", "HULL"}
HEAD = ["building", "label", "scenario", "z", "unit_cells", "removed", "expect", "parts"]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def kstr(k):
    return "%s:%d,%d,%d" % k


def kparse(s):
    sl, xyz = s.split(":")
    x, y, z = map(int, xyz.split(","))
    return (sl, x, y, z)


def load():
    import collapse_ctype as CT
    import collapse_v2 as V
    import collapse_attach_v2 as A2
    C = A2.use()
    roles = V.load_roles()
    allb = CT.buildings()
    out = []
    for tn, bn, label in PILOT:
        blk = allb[(tn, bn)]
        V.apply_roles(blk, roles)
        C.apply_marks(blk)
        out.append((tn, bn, label, blk))
    return C, CT, out


def supports(blk, z, cells):
    """Опоры участка на этаже z: стены по краям клеток и несущие части слота o в клетках, этаж z-1."""
    lv = blk.lv[z - 1]
    res = set()
    for x, y in cells:
        for sl, xy in (("w", (x, y)), ("w", (x + 1, y)), ("n", (x, y)), ("n", (x, y + 1))):
            k = lv[sl].get(xy)
            if k and blk.parts[k].get("role") in BEAR:
                res.add(k)
        k = lv["o"].get((x, y))
        if k and blk.parts[k].get("role") in BEAR:
            res.add(k)
    return res


def scenarios(CT, blk):
    """[(сценарий, z, клетки участка, снятое, ожидание)] - по правилу, для всех участков от 4 клеток."""
    res = []
    for z, fl, ro in CT.units(blk):
        cells = sorted({(k[1], k[2]) for k in fl})
        if len(cells) < 4:
            continue
        sup = supports(blk, z, cells)
        if not sup:
            continue
        for k in sorted(sup):
            res.append(("ONE", z, cells, [k], "STAND"))
        cx = sorted(x for x, y in cells)[len(cells) // 2]
        cy = sorted(y for x, y in cells)[len(cells) // 2]
        hole = [blk.lv[z]["f"][xy] for xy in ((cx, cy), (cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1))
                if xy in blk.lv[z]["f"] and xy in cells]
        if len(hole) == 5:
            res.append(("HOLE", z, cells, hole, "STAND"))
        x0, y0 = min(x for x, y in cells), min(y for x, y in cells)
        corner = sorted(sup, key=lambda k: abs(k[1] - x0) + abs(k[2] - y0))
        wside = [k for k in corner if k[0] == "w" and k[1] == x0][:2]
        nside = [k for k in corner if k[0] == "n" and k[2] == y0][:2]
        if len(wside) == 2 and len(nside) == 2:
            res.append(("CORNER", z, cells, wside + nside, "STAND"))
        west = sorted(k for k in sup if k[0] == "w" and k[1] == x0)
        if len(west) >= 3:
            res.append(("SIDE", z, cells, west, "NONE"))
        res.append(("ALL", z, cells, sorted(sup), "COLLAPSE"))
    return res


def cmd_define():
    os.makedirs(OUT, exist_ok=True)
    C, CT, blds = load()
    rows = []
    for tn, bn, label, blk in blds:
        for sc, z, cells, rm, ex in scenarios(CT, blk):
            rows.append(["%s/%s" % (tn, bn), label, sc, str(z), str(len(cells)), " ".join(map(kstr, rm)), ex,
                         " ".join("%d,%d" % c for c in cells)])
    with open(SCEN, "w", encoding=ENC) as f:
        f.write("\t".join(HEAD) + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("# замок сценариев пилота 0m, поставлен ДО прогона модели\n")
        f.write("time\t%s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        for p in (SCEN, "tools/collapse_pilot_scen.py"):
            f.write("%s\t%s\n" % (p, sha(p)))
    n = {}
    for r in rows:
        n[(r[1], r[2])] = n.get((r[1], r[2]), 0) + 1
    print("сценариев %d: %s" % (len(rows), ", ".join("%s %s %d" % (a, b, c) for (a, b), c in sorted(n.items()))))


def check_lock():
    for ln in open(LOCK, encoding=ENC).read().splitlines():
        if ln.startswith("#") or ln.startswith("time"):
            continue
        p, h = ln.split("\t")
        if sha(p) != h:
            raise SystemExit("замок сценариев 0m нарушен: %s" % p)


def cmd_run():
    check_lock()
    C, CT, blds = load()
    by = {"%s/%s" % (tn, bn): blk for tn, bn, label, blk in blds}
    lines = open(SCEN, encoding=ENC).read().splitlines()
    head = lines[0].split("\t")
    base = {b: C.evaluate7c(blk, frozenset())[0] for b, blk in by.items()}
    out, t0 = [], time.time()
    tally = {}
    for ln in lines[1:]:
        r = dict(zip(head, ln.split("\t")))
        blk = by[r["building"]]
        rm = frozenset(kparse(s) for s in r["removed"].split())
        z = int(r["z"])
        cells = {tuple(map(int, c.split(","))) for c in r["parts"].split()}
        t1 = time.perf_counter()
        held = C.evaluate7c(blk, rm)[0]
        ms = (time.perf_counter() - t1) * 1000
        fallen = {k for k in base[r["building"]] if k not in held and k not in rm and k[3] > 0}
        unit = {k for k in blk.parts if k[3] >= z and (k[1], k[2]) in cells and k not in rm}
        unit_f = {k for k in unit if k[3] == z and k[0] == "f"}
        fell_unit = sum(1 for k in unit_f if k in fallen)
        outside = {k for k in fallen if k not in unit}
        # что крепилось к снятому: разметка ATTACHED/SURFACE, все цели которой сняты
        tg = C.marked_parts(blk)
        own = {k for k in fallen if k in tg and tg[k][1] and all(q in rm for q in tg[k][1])}
        ex = r["expect"]
        if ex == "STAND":
            ok = "PASS" if not (fallen - own) else "FAIL"
        elif ex == "COLLAPSE":
            ok = "PASS" if fell_unit == len(unit_f) else "FAIL"
        else:
            ok = "SHOWN"
        tally[(r["label"], r["scenario"], ok)] = tally.get((r["label"], r["scenario"], ok), 0) + 1
        ex_f = sorted(fallen - own)[:6]
        out.append([r["building"], r["label"], r["scenario"], r["z"], r["unit_cells"], r["removed"], ex, ok,
                    str(len(fallen)), str(len(own)), "%d/%d" % (fell_unit, len(unit_f)), str(len(outside)),
                    "%.1f" % ms, " ".join(map(kstr, ex_f))])
    with open(RESULT, "w", encoding=ENC) as f:
        f.write("\t".join(["building", "label", "scenario", "z", "unit_cells", "removed", "expect", "verdict",
                           "fallen", "fallen_attached_to_removed", "unit_floor_fallen", "fallen_outside_unit", "ms",
                           "fallen_examples"]) + "\n")
        for r in out:
            f.write("\t".join(r) + "\n")
    for k, v in sorted(tally.items()):
        print("  %-7s %-7s %-6s %d" % (k + (v,)))
    print("сценариев %d, %.1f с" % (len(out), time.time() - t0))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    {"define": cmd_define, "run": cmd_run}[sys.argv[1] if len(sys.argv) > 1 else "define"]()
