#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0i обрушения зданий: новый слепой набор. Модель M0i2 - collapse_v6b (замок stage0i/rules2.lock.txt),
этот файл её не меняет: отбор сценариев, проверка ответа рецензента, замок ожиданий, оценка.

Часть A - разрушение ВНУТРИ больших зданий. Блоки только не виденные в разработке (как в 0h, плюс блоки
сценариев 0h). Участок - связный пол этажа z (z >= 1) не меньше BIG_MIN клеток, над которым есть этаж выше,
целиком держится до боя в M0i2, M0h и M0f. Виды повреждения:
  BIN   одна внутренняя опора (несущее этажа z-1 под клетками участка не у его края);
  BLINE внутренняя линия стен этажа z-1 длиной от 3 клеток;
  BALL  ВСЕ внутренние опоры участка (периметр остаётся);
  BH9   отверстие 3x3 в полу участка под этажом выше.
Часть B - связи между зданиями на картах holdout3 (зёрна 22-25, stage0i/holdout3.lock.txt). Пара соседних
размещений блоков, следы касаются гранью не короче 3 клеток, и выше земли у общей границы с обеих сторон
есть части на одном этаже. Повреждения в одном здании (A):
  LSUP  все опоры этажа под связью в полосе A у границы (две клетки);
  LWALL стены на самой границе ниже связи.
Модель и судья считаются на вырезке карты: оба здания с запасом 2 клетки.

Список оценки - участок (или связь), всё, что роняют M0i2/M0h/M0f, и 4 устоявшие части рядом.

    py -3.13 tools\collapse_review6.py pick     сценарии -> census/collapse/review0i (рецензенту), stage0i (модели)
    py -3.13 tools\collapse_review6.py check    ответ рецензента по форме
    py -3.13 tools\collapse_review6.py lock     sha сценариев и ответа в stage0i/review.lock.txt (до оценки)
    py -3.13 tools\collapse_review6.py score    оценка: модель и фильтр отдельно; части, сценарии, здания
"""
import collections
import copy
import hashlib
import json
import os
import pickle
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_census as cc                      # noqa: E402
import collapse_v2 as V                           # noqa: E402
import collapse_v3 as T                           # noqa: E402
import collapse_pilot as P                        # noqa: E402
import collapse_v4 as G                           # noqa: E402
import collapse_summary as S                      # noqa: E402
import collapse_v5 as H                           # noqa: E402
import collapse_v6b as B                          # noqa: E402
import collapse_review5 as R5                     # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/stage0i"
REVIEW = "census/collapse/review0i"
HOLD3 = "census/collapse/holdout3"
SEED = 20261008
KINDS_A = ("BIN", "BLINE", "BALL", "BH9")
KINDS_B = ("LSUP", "LWALL")
PER_A, N_DIFF_A, PER_B, N_DIFF_B = 5, 6, 6, 3
BIG_MIN = 40
UPPER_MIN = 10
MAX_BLOCKS = 900
N_DECOY = 4
MARGIN = 2
TASK = REVIEW + "/scenarios.tsv"
EXPECT = REVIEW + "/expect_0i.tsv"
PICKED = OUT + "/review_picked_model.tsv"
CROPS = OUT + "/review_crops.pkl"
RLOCK = OUT + "/review.lock.txt"
MODELS = [("M0i2", lambda blk, rm: B.evaluate6b(blk, rm, B.MODEL)[0]),
          ("M0h", lambda blk, rm: H.evaluate5(blk, rm, H.MODEL)[0]),
          ("M0f", lambda blk, rm: T.evaluate3(blk, rm, H.M0F)[0])]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def known_blocks():
    out = R5.known_blocks()
    out |= {r["block"].upper() for r in P.read_tsv(R5.TASK)}
    return out


def fallen(sup0, sup, rm):
    return {k for k in sup0 if k not in sup and k not in rm and k[3] > 0}


def carry_of(blk):
    B.evaluate6b(blk, frozenset(), B.MODEL)
    return set(blk.carry)


def run_models(blk, rm, s0):
    return {name: fallen(s0[name], fn(blk, rm), rm) for name, fn in MODELS}


def decoys(blk, sup_all, rm, event, rnd):
    cells = {(c[0], c[1]) for k in rm | event for c in T.part_cells(k)}
    near = {(x + a, y + b) for x, y in cells for a in range(-2, 3) for b in range(-2, 3)}
    pool = sorted(k for k in blk.parts if k[3] > 0 and (k[1], k[2]) in near and k not in rm and k not in event
                  and k in sup_all)
    rnd.shuffle(pool)
    return set(pool[:N_DECOY])


# ------------------------------------------------------------------ часть A

def interior_supports(blk, z, comp, carry):
    """Несущее этажа z-1 под клетками участка, все клетки которого не у края участка."""
    perim = {xy for xy in comp if any(nb not in comp for nb in ((xy[0] + 1, xy[1]), (xy[0] - 1, xy[1]),
                                                               (xy[0], xy[1] + 1), (xy[0], xy[1] - 1)))}
    inner = comp - perim
    below = blk.lv[z - 1]
    out = set()
    for (x, y), key in below["w"].items():
        if key in carry and (x - 1, y) in inner and (x, y) in inner:
            out.add(key)
    for (x, y), key in below["n"].items():
        if key in carry and (x, y - 1) in inner and (x, y) in inner:
            out.add(key)
    for (x, y), key in below["o"].items():
        if key in carry and (x, y) in inner:
            out.add(key)
    return out, inner


def wall_runs(sup):
    runs = []
    for k, ax in (("w", 1), ("n", 0)):
        keys = sorted(s for s in sup if s[0] == k)
        by_line = collections.defaultdict(list)
        for s in keys:
            by_line[s[2 - ax] if ax == 1 else s[2]].append(s)
        for line, lst in by_line.items():
            lst.sort(key=lambda s: s[1 + ax])
            run = [lst[0]]
            for s in lst[1:]:
                if s[1 + ax] == run[-1][1 + ax] + 1:
                    run.append(s)
                else:
                    if len(run) >= 3:
                        runs.append(run)
                    run = [s]
            if len(run) >= 3:
                runs.append(run)
    return runs


def damages_a(blk, z, comp, carry, rnd):
    fk = blk.lv[z]["f"]
    up = blk.lv[z + 1]["f"]
    out = {}
    sup, inner = interior_supports(blk, z, comp, carry)
    if sup:
        out["BIN"] = frozenset([rnd.choice(sorted(sup))])
        if len(sup) > 1:
            out["BALL"] = frozenset(sup)
    runs = wall_runs(sup)
    if runs:
        out["BLINE"] = frozenset(rnd.choice(runs))
    ctr = [(x, y) for x, y in sorted(comp) if all((x + a, y + b) in comp for a in range(-2, 3) for b in range(-2, 3))
           and sum((x + a, y + b) in up for a in (-1, 0, 1) for b in (-1, 0, 1)) >= 5]
    if ctr:
        x, y = rnd.choice(ctr)
        out["BH9"] = frozenset(fk[(x + a, y + b)] for a in (-1, 0, 1) for b in (-1, 0, 1))
    return out


def area_a(blk, z, comp, rm):
    """Участок для оценки: клетки участка в 3 клетках от повреждения, этажи z..верх."""
    cells = {(c[0], c[1]) for k in rm for c in T.part_cells(k)}
    near = {(x + a, y + b) for x, y in cells for a in range(-3, 4) for b in range(-3, 4)} & comp
    return {k for k in blk.parts if z <= k[3] <= z + 1 and (k[1], k[2]) in near and k not in rm}


def pick_a(rnd, roles, known, disp):
    vess = T.vessels()
    hull = T.hull_terrains()
    cand = []
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None or blk.sz < 3 or kind != "terrain" or bname.upper() in known or \
                any(p in bname.upper() or p in tname.upper() for p in R5.DEV_PEEK) or \
                (tname.upper(), bname.upper()) in vess or tname.upper() in hull:
            continue
        if any(len(blk.lv[z]["f"]) >= BIG_MIN for z in range(1, blk.sz - 1)):
            cand.append((tname, bname, blk))
    rnd.shuffle(cand)
    print("A: блоков-кандидатов %d, смотрю %d" % (len(cand), min(len(cand), MAX_BLOCKS)), flush=True)
    pool, seen = [], set()
    for tname, bname, blk in cand[:MAX_BLOCKS]:
        if bname.upper() in seen:
            continue
        seen.add(bname.upper())
        V.apply_roles(blk, roles)
        s0 = {name: fn(blk, frozenset()) for name, fn in MODELS}
        carry = carry_of(blk)
        all0 = set.intersection(*[set(s) for s in s0.values()])
        opts = []
        for z in range(1, blk.sz - 1):
            for comp in R5.comps(set(blk.lv[z]["f"])):
                up = sum(xy in blk.lv[z + 1]["f"] for xy in comp)
                if len(comp) >= BIG_MIN and up >= UPPER_MIN and all(blk.lv[z]["f"][xy] in all0 for xy in comp):
                    opts.append((z, comp))
        if not opts:
            continue
        z, comp = rnd.choice(opts)
        for dk, rm in sorted(damages_a(blk, z, comp, carry, rnd).items()):
            fl = run_models(blk, rm, s0)
            pool.append({"part": "A", "kind": dk, "terrain": tname, "block": bname, "blk": blk, "z": z,
                         "area": area_a(blk, z, comp, rm), "rm": rm, "fallen": fl, "s0": s0, "foot": None,
                         "diff": fl["M0i2"] != fl["M0h"], "r": rnd.random(), "pair": bname.upper(),
                         "group": tname.upper(), "note": "участок пола z=%d, %d клеток" % (z, len(comp))})
    print("A: сценариев-кандидатов %d, M0i2 и M0h расходятся %d" % (len(pool), sum(p["diff"] for p in pool)),
          flush=True)
    return pool


# ------------------------------------------------------------------ часть B

def crop(m, x0, y0, x1, y1, name):
    c = cc.Block(m.terrain, "map", name, x1 - x0 + 1, y1 - y0 + 1, m.sz)
    for (k, x, y, z), v in m.parts.items():
        if x0 <= x <= x1 and y0 <= y <= y1:
            key = (k, x - x0, y - y0, z)
            c.parts[key] = copy.copy(v)
            c.lv[z][k][(x - x0, y - y0)] = key
    return c


def touching(a, b):
    """Общая грань двух прямоугольников (x0, y0, x1, y1 включительно): ('x', bx, lo, hi) - граница по x = bx
    (столбец bx принадлежит правому), ('y', ...) - по y."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    if ax1 + 1 == bx0 or bx1 + 1 == ax0:
        lo, hi = max(ay0, by0), min(ay1, by1)
        if hi - lo + 1 >= 3:
            return ("x", max(ax0, bx0), lo, hi)
    if ay1 + 1 == by0 or by1 + 1 == ay0:
        lo, hi = max(ax0, bx0), min(ax1, bx1)
        if hi - lo + 1 >= 3:
            return ("y", max(ay0, by0), lo, hi)
    return None


def side_cells(edge, rect, depth):
    """Клетки rect в полосе depth у границы edge."""
    ax, bd, lo, hi = edge
    x0, y0, x1, y1 = rect
    out = set()
    for t in range(lo, hi + 1):
        for d in range(depth):
            if ax == "x":
                x = bd + d if x0 >= bd else bd - 1 - d
                if x0 <= x <= x1:
                    out.add((x, t))
            else:
                y = bd + d if y0 >= bd else bd - 1 - d
                if y0 <= y <= y1:
                    out.add((t, y))
    return out


def pick_b(rnd, roles, disp, sizes):
    import collapse_battles as cb
    import collapse_holdout as HD
    HD.HOLD = HOLD3
    d = cb.Data(HD.game_args())
    pool = []
    for name in HD.names():
        m, src = HD.load_map(d, name, roles, V.apply_roles)
        rects = []
        for bt, bn, ox, oy, oz in src["blocks"]:
            sz = sizes.get((bt.upper(), bn.upper())) or sizes.get(("*", bn.upper()))
            if sz is None or oz != 0:
                continue
            rects.append((bt, bn, (ox, oy, ox + sz[0] - 1, oy + sz[1] - 1), sz[2]))
        pairs = []
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                e = touching(rects[i][2], rects[j][2])
                if e is None:
                    continue
                for a, b in ((i, j), (j, i)):
                    A, Bb = rects[a], rects[b]
                    sa, sb = side_cells(e, A[2], 1), side_cells(e, Bb[2], 1)
                    zs = [z for z in range(1, m.sz) if any(m.lv[z][k].get(xy) for xy in sa for k in cc.KINDS)
                          and any(m.lv[z][k].get(xy) for xy in sb for k in cc.KINDS)]
                    if zs:
                        pairs.append((A, Bb, e, min(zs)))
        rnd.shuffle(pairs)
        for A, Bb, e, zc in pairs[:4]:
            ra, rb = A[2], Bb[2]
            x0, y0 = max(0, min(ra[0], rb[0]) - MARGIN), max(0, min(ra[1], rb[1]) - MARGIN)
            x1, y1 = min(m.sx - 1, max(ra[2], rb[2]) + MARGIN), min(m.sy - 1, max(ra[3], rb[3]) + MARGIN)
            cname = "%s@%d,%d-%d,%d" % (name[:-4].replace("collapse_", ""), x0, y0, x1, y1)
            c = crop(m, x0, y0, x1, y1, cname)
            sh = lambda cells: {(x - x0, y - y0) for x, y in cells}
            fa = {(x - x0, y - y0, z) for x in range(ra[0], ra[2] + 1) for y in range(ra[1], ra[3] + 1)
                  for z in range(A[3])}
            fb = {(x - x0, y - y0, z) for x in range(rb[0], rb[2] + 1) for y in range(rb[1], rb[3] + 1)
                  for z in range(Bb[3])}
            ax, bd, lo, hi = e
            ec = (ax, bd - (x0 if ax == "x" else y0), lo - (y0 if ax == "x" else x0), hi - (y0 if ax == "x" else x0))
            rac = (ra[0] - x0, ra[1] - y0, ra[2] - x0, ra[3] - y0)
            rbc = (rb[0] - x0, rb[1] - y0, rb[2] - x0, rb[3] - y0)
            s0 = {nm: fn(c, frozenset()) for nm, fn in MODELS}
            all0 = set.intersection(*[set(s) for s in s0.values()])
            strip = side_cells(ec, rac, 3) | side_cells(ec, rbc, 3)
            link = {k for k in c.parts if k[3] >= 1 and (k[1], k[2]) in strip}
            if not link or len(link & all0) < len(link) * 0.8:
                continue
            carry = carry_of(c)
            dm = {}
            sa2 = side_cells(ec, rac, 2)
            rm = frozenset(c.lv[zc - 1][k][xy] for xy in sa2 for k in ("w", "n", "o")
                           if c.lv[zc - 1][k].get(xy) in carry)
            if rm:
                dm["LSUP"] = rm
            line = set()
            for z in range(zc):
                for t in range(ec[2], ec[3] + 1):
                    key = c.lv[z]["w"].get((ec[1], t)) if ax == "x" else c.lv[z]["n"].get((t, ec[1]))
                    if key and key in carry:
                        line.add(key)
            if len(line) >= 3:
                dm["LWALL"] = frozenset(line)
            for dk, rm in sorted(dm.items()):
                fl = run_models(c, rm, s0)
                pool.append({"part": "B", "kind": dk, "terrain": src["terrain"], "block": cname, "blk": c,
                             "z": zc, "area": link - rm, "rm": rm, "fallen": fl, "s0": s0, "foot": fa,
                             "foot_b": fb, "diff": fl["M0i2"] != fl["M0h"], "r": rnd.random(),
                             "pair": "%s|%s" % (A[1].upper(), Bb[1].upper()), "group": src["terrain"].upper(),
                             "note": "здание A %s x%d-%d y%d-%d, здание B %s x%d-%d y%d-%d (координаты вырезки), "
                                     "повреждено A" % (A[1], rac[0], rac[2], rac[1], rac[3],
                                                       Bb[1], rbc[0], rbc[2], rbc[1], rbc[3]),
                             "names": (A[0], A[1], Bb[0], Bb[1])})
        print("B: %s, мест %d, пар %d, кандидатов всего %d" % (name, len(rects), len(pairs), len(pool)), flush=True)
    print("B: сценариев-кандидатов %d, M0i2 и M0h расходятся %d" % (len(pool), sum(p["diff"] for p in pool)),
          flush=True)
    return pool


def block_sizes():
    out = {}
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is not None:
            out.setdefault((tname.upper(), bname.upper()), (blk.sx, blk.sy, blk.sz))
            sz = (blk.sx, blk.sy, blk.sz)
            if out.setdefault(("*", bname.upper()), sz) != sz:
                out[("*", bname.upper())] = None          # одно имя - разные размеры: по имени не берём
    return out


# ------------------------------------------------------------------ отбор

def cmd_pick():
    B.check_lock()
    if os.path.exists(RLOCK):
        raise SystemExit("эталон уже под замком: " + RLOCK)
    rnd = random.Random(SEED)
    roles = V.load_roles()
    disp = S.disputed_records()
    known = known_blocks()
    print("известных блоков %d" % len(known), flush=True)
    pool_a = pick_a(rnd, roles, known, disp)
    pool_b = pick_b(rnd, roles, disp, block_sizes())
    picked = []
    used_pair, used_group = set(), collections.Counter()

    def take(rows, need):
        got = 0
        for pass_ in (0, 1):
            for p in sorted(rows, key=lambda p: p["r"]):
                if got >= need:
                    return got
                if p["pair"] in used_pair or (pass_ == 0 and used_group[p["group"]]):
                    continue
                picked.append(p)
                used_pair.add(p["pair"])
                used_group[p["group"]] += 1
                got += 1
        return got

    for dk in KINDS_A:
        print("A %s: взято %d" % (dk, take([p for p in pool_a if p["kind"] == dk and not p["diff"]], PER_A)))
    print("A расхождение: взято %d" % take([p for p in pool_a if p["diff"]], N_DIFF_A))
    for dk in KINDS_B:
        print("B %s: взято %d" % (dk, take([p for p in pool_b if p["kind"] == dk and not p["diff"]], PER_B)))
    print("B расхождение: взято %d" % take([p for p in pool_b if p["diff"]], N_DIFF_B))
    os.makedirs(REVIEW + "/geom", exist_ok=True)
    order = list(range(len(picked)))
    rnd.shuffle(order)
    task_rows, model_rows, geoms, crops = [], [], {}, {}
    for n, i in enumerate(order, 1):
        p = picked[i]
        sid = "Q-%02d" % n
        blk, rm = p["blk"], p["rm"]
        event = set().union(*p["fallen"].values())
        sup_all = set.intersection(*[set(s) for s in p["s0"].values()])
        dec = decoys(blk, sup_all, rm, event | p["area"], rnd)
        look = sorted((p["area"] | event | dec) - rm)
        jb = B.Base6b(blk, disp, foot=p["foot"]).judge(rm)
        jh = H.Base5(blk, disp, foot=p["foot"]).judge(rm)
        where = "блок" if p["part"] == "A" else "карта"
        task_rows.append([sid, where, p["terrain"], p["block"], T.compress(sorted(rm)), T.compress(look),
                          p["note"] if p["part"] == "B" else ""])
        model_rows.append([sid, p["part"], p["kind"], "да" if p["diff"] else "", p["terrain"], p["block"], p["z"],
                           T.compress(sorted(rm)), T.compress(sorted(p["fallen"]["M0i2"])),
                           T.compress(sorted(p["fallen"]["M0h"])), T.compress(sorted(p["fallen"]["M0f"])),
                           jb["status"], json.dumps(jb["why"], ensure_ascii=False), jh["status"],
                           json.dumps(jh["why"], ensure_ascii=False), p["note"]])
        geoms[(blk.terrain.upper(), blk.name.upper())] = blk
        if p["part"] == "B":
            crops[p["block"]] = {"blk": blk, "foot": p["foot"], "foot_b": p["foot_b"], "names": p["names"]}
    task_rows.sort()
    model_rows.sort()
    for (tn, bn), blk in geoms.items():
        fn = "%s__%s.txt" % (tn, bn.replace("@", "_at_").replace(",", "_"))
        with open(REVIEW + "/geom/" + fn, "w", encoding=ENC) as f:
            f.write(V.geom_text(blk) + "\n")
    with open(CROPS, "wb") as f:
        pickle.dump(crops, f)
    cc.write_tsv(TASK, ["id", "where", "terrain", "block", "remove", "evaluate", "note"], task_rows)
    cc.write_tsv(PICKED, ["id", "part", "kind", "diff", "terrain", "block", "z", "remove", "fallen_M0i2",
                          "fallen_M0h", "fallen_M0f", "judge_M0i2", "why_M0i2", "judge_M0h", "why_M0h", "note"],
                 model_rows)
    print("сценариев %d (A %d, B %d), срезов %d -> %s" % (
        len(task_rows), sum(r[1] == "блок" for r in task_rows), sum(r[1] == "карта" for r in task_rows), len(geoms),
        REVIEW))


# ------------------------------------------------------------------ ответ, замок, оценка

def load_task_blocks(roles):
    task = {r["id"]: r for r in P.read_tsv(TASK)}
    with open(CROPS, "rb") as f:
        crops = pickle.load(f)
    want = {(r["terrain"].upper(), r["block"].upper()) for r in task.values() if r["where"] == "блок"}
    blocks = G.load_many(want, roles)
    for name, c in crops.items():
        blocks[(c["blk"].terrain.upper(), name.upper())] = c["blk"]
    return task, blocks, crops


def cmd_check():
    roles = V.load_roles()
    task, blocks, crops = load_task_blocks(roles)
    exp = P.read_tsv(EXPECT)
    bad, seen = [], set()
    for e in exp:
        t = task.get(e["id"])
        if t is None:
            bad.append("%s: нет в задании" % e["id"])
            continue
        seen.add(e["id"])
        if (e["block"].upper(), e["remove"].strip()) != (t["block"].upper(), t["remove"].strip()):
            bad.append("%s: block/remove не как в задании" % e["id"])
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
            bad.append("%s: часть в двух колонках" % e["id"])
        if (a | b | u) - ev:
            bad.append("%s: не из evaluate: %s" % (e["id"], T.compress(sorted((a | b | u) - ev))))
        if ev - (a | b | u):
            bad.append("%s: не оценено: %s" % (e["id"], T.compress(sorted(ev - (a | b | u)))))
    for sid in sorted(set(task) - seen):
        bad.append("%s: нет строки" % sid)
    print("ответ рецензента: строк %d, замечаний %d" % (len(exp), len(bad)))
    for b in bad:
        print("  ", b)
    return 1 if bad else 0


def cmd_lock():
    B.check_lock()
    if os.path.exists(RLOCK):
        raise SystemExit("замок уже есть: " + RLOCK)
    if cmd_check():
        raise SystemExit("ответ рецензента не прошёл проверку формы - замок не пишется")
    files = [TASK, EXPECT, PICKED, CROPS, B.LOCK, "tools/collapse_review6.py", "census/collapse/stage0i/holdout3.lock.txt"] + \
        sorted(REVIEW + "/geom/" + n for n in os.listdir(REVIEW + "/geom"))
    lines = ["эталон 0i (большие здания и связи между зданиями), записано %s - до оценки модели"
             % time.strftime("%Y-%m-%d %H:%M:%S"),
             "ответ писал слепой рецензент (%s/TASK.md) без доступа к модели" % REVIEW]
    lines += ["%s sha256 %s" % (p, sha(p)) for p in files]
    with open(RLOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:8]), "...")


def cmd_score():
    B.check_lock()
    lock = {}
    with open(RLOCK, encoding=ENC) as f:
        for line in f:
            p = line.rstrip("\n").split(" sha256 ")
            if len(p) == 2:
                lock[p[0]] = p[1]
    bad = [p for p in lock if sha(p) != lock[p]]
    if bad:
        raise SystemExit("замок эталона нарушен: " + ", ".join(bad))
    roles = V.load_roles()
    task, blocks, crops = load_task_blocks(roles)
    pm = {r["id"]: r for r in P.read_tsv(PICKED)}
    models = MODELS + [("ничего не ронять", None)]
    rows, per, meta = [], {}, {}
    for e in P.read_tsv(EXPECT):
        t = task[e["id"]]
        blk = blocks[(t["terrain"].upper(), t["block"].upper())]
        rm = frozenset(cc.select(blk, t["remove"]))
        mf = cc.select(blk, e["must_fall"]) - rm
        ms = cc.select(blk, e["must_stand"]) - rm
        group = "рушится" if mf else "стоит"
        meta_r = pm[e["id"]]
        cr = crops.get(t["block"])
        # здания сценария: A - сам блок; B - здание A и здание B по следам на вырезке
        if cr is None:
            bld = {t["block"].upper(): lambda k: True}
        else:
            fa, fb = cr["foot"], cr["foot_b"]
            bld = {"A:" + cr["names"][1]: lambda k, fa=fa: (k[1], k[2], k[3]) in fa,
                   "B:" + cr["names"][3]: lambda k, fb=fb: (k[1], k[2], k[3]) in fb}
        meta[e["id"]] = (meta_r["part"], group, meta_r["judge_M0i2"], meta_r["judge_M0h"])
        for name, fn in models:
            if fn is None:
                s0 = MODELS[0][1](blk, frozenset())
                sup = set(s0) - rm
            else:
                s0, sup = fn(blk, frozenset()), fn(blk, rm)
            missed = sorted(k for k in mf if k in sup and k in s0)
            false = sorted(k for k in ms if k not in sup and k in s0)
            bok = {}
            for bn, inside in bld.items():
                if any(inside(k) for k in mf | ms):
                    bok[bn] = not any(inside(k) for k in missed + false)
            per[(name, e["id"])] = (not missed and not false, len(false), len(missed), bok)
            rows.append([e["id"], meta_r["part"], meta_r["kind"], meta_r["diff"], meta_r["judge_M0i2"],
                         meta_r["judge_M0h"], group, name, "да" if not missed and not false else "нет", len(false),
                         len(missed), T.compress(false), T.compress(missed),
                         " ".join("%s=%s" % (b, "да" if v else "нет") for b, v in sorted(bok.items()))])
    cc.write_tsv(OUT + "/review_score.tsv", ["id", "part", "kind", "diff", "judge_M0i2", "judge_M0h", "group", "model",
                                             "ok", "false_falls", "missed_falls", "false_parts", "missed_parts",
                                             "buildings"], rows)
    res = {}
    for scope, keep in (("модель, все сценарии", lambda m: True), ("фильтр M0i2: судья OK", lambda m: m[2] == "OK"),
                        ("фильтр M0h: судья OK", lambda m: m[3] == "OK")):
        for part in ("A", "B", "все"):
            for name, _ in models:
                for group in ("рушится", "стоит"):
                    ids = [i for i, m in meta.items() if m[1] == group and keep(m) and part in ("все", m[0])]
                    if not ids:
                        continue
                    nb = sum(len(per[(name, i)][3]) for i in ids)
                    res["%s / %s / %s / %s" % (scope, part, name, group)] = {
                        "сценариев": len(ids), "верно": sum(per[(name, i)][0] for i in ids),
                        "ложных частей": sum(per[(name, i)][1] for i in ids),
                        "пропущенных частей": sum(per[(name, i)][2] for i in ids),
                        "зданий": nb, "зданий верно": sum(sum(per[(name, i)][3].values()) for i in ids)}
    res["судья"] = {i: {"M0i2": m[2], "M0h": m[3]} for i, m in sorted(meta.items())}
    with open(OUT + "/review_score.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for k, v in res.items():
        if k != "судья":
            print(k, v)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"pick": cmd_pick, "check": cmd_check, "lock": cmd_lock, "score": cmd_score}.get(cmd)
    if fn is None:
        print(__doc__)
        sys.exit(0)
    sys.exit(fn() or 0)
