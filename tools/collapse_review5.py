#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0h обрушения зданий: реальные здания со слепым эталоном. Модель M0h - collapse_v5 (под замком
stage0h/rules.lock.txt), этот файл её не меняет: отбор сценариев, проверка ответа рецензента, замок ожиданий,
оценка M0h, M0f, M0g и варианта «ничего не ронять».

Блоки - только не виденные в разработке: не из карт настройки (stage0g/known_names.json), не из пилота 0f,
не из сценариев 0g, не из второго набора карт 0g, не из блоков, которые смотрелись при сборке M0h.

Виды повреждения на связном участке пола этажа z (размер 6-60 клеток, целиком держится до боя в M0h и M0f):
  H1 отверстие в клетку внутри участка, H4 отверстие 2x2;
  O1 снята одна опора участка (несущая стена или столб этажа z-1 под ним);
  OA сняты ВСЕ опоры участка на этаже z-1;
  CUT сквозной разрез: ряд пола поперёк участка, по обе стороны остаётся не меньше трёх клеток.
Список оценки - весь участок, всё, что роняет M0h или M0f, и 4 устоявшие части рядом: он не выдаёт ответ.

    py -3.13 tools\collapse_review5.py pick        сценарии -> census/collapse/review0h (рецензенту), stage0h (модели)
    py -3.13 tools\collapse_review5.py check       ответ рецензента по форме
    py -3.13 tools\collapse_review5.py lock        sha сценариев и ответа в stage0h/review.lock.txt (до оценки)
    py -3.13 tools\collapse_review5.py score       оценка по группам: устояло / рухнуло по эталону
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
import collapse_pilot as P                        # noqa: E402
import collapse_v4 as G                           # noqa: E402
import collapse_summary as S                      # noqa: E402
import collapse_v5 as H                           # noqa: E402

ENC = "utf-8-sig"
OUT = H.OUT
REVIEW = "census/collapse/review0h"
SEED = 20261007
KINDS = ("H1", "H4", "O1", "OA", "CUT")
PER_KIND = 5
N_DIFF = 10
COMP_MIN, COMP_MAX = 6, 60
MAX_BLOCKS = 600
N_DECOY = 4
DEV_PEEK = ("EMANS", "GDX_HOUSE", "LOC_RAYNOR", "A_BASE12", "NUKECITY")   # смотрелись при сборке M0h
TASK = REVIEW + "/scenarios.tsv"
EXPECT = REVIEW + "/expect_0h.tsv"
PICKED = OUT + "/review_picked_model.tsv"
RLOCK = OUT + "/review.lock.txt"
MODELS = [("M0h", lambda blk, rm: H.evaluate5(blk, rm, H.MODEL)[0]),
          ("M0f", lambda blk, rm: T.evaluate3(blk, rm, H.M0F)[0]),
          ("M0g", lambda blk, rm: G.evaluate4(blk, rm, G.MODEL)[0])]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_model_lock():
    lock = H.read_lock()
    bad = [p for p in H.LOCKED if lock.get(p) != sha(p)]
    if bad:
        raise SystemExit("замок M0h нарушен: " + ", ".join(bad))


def known_blocks():
    out = set(json.load(open("census/collapse/stage0g/known_names.json", encoding=ENC)))
    for path in ("census/collapse/stage0f/pilot_blocks.tsv", "census/collapse/review0g/scenarios_rules.tsv",
                 "census/collapse/review0g/scenarios_crowns.tsv", "census/collapse/stage0g/holdout2_scen.tsv"):
        out |= {r["block"] for r in P.read_tsv(path) if r.get("block")}
    return {b.upper() for b in out}


def comps(cells):
    seen, out = set(), []
    for s in sorted(cells):
        if s in seen:
            continue
        comp, q = {s}, [s]
        seen.add(s)
        while q:
            x, y = q.pop()
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in cells and nb not in seen:
                    seen.add(nb)
                    comp.add(nb)
                    q.append(nb)
        out.append(comp)
    return out


def supports(blk, z, comp, carry):
    """Несущее этажа z-1 под участком: стены по краям его клеток, столбы и массив под ним и стены-края соседей."""
    below = blk.lv[z - 1]
    out = set()
    for x, y in comp:
        for k, xy in (("w", (x, y)), ("w", (x + 1, y)), ("n", (x, y)), ("n", (x, y + 1)), ("o", (x, y))):
            key = below[k].get(xy)
            if key in carry:
                out.add(key)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            key = below["o"].get((x + dx, y + dy))
            if key in carry and (-dx, -dy) in cc.EDGE_NB.get(blk.parts[key]["rec"]["big_wall"], ()):
                out.add(key)
    return out


def damages(blk, z, comp, carry, rnd):
    """По одному случайному повреждению каждого вида на участке (или меньше, если вид невозможен)."""
    fk = blk.lv[z]["f"]
    out = {}
    inner = sorted(xy for xy in comp if all(nb in comp for nb in ((xy[0] + 1, xy[1]), (xy[0] - 1, xy[1]),
                                                                  (xy[0], xy[1] + 1), (xy[0], xy[1] - 1))))
    if inner:
        out["H1"] = frozenset([fk[rnd.choice(inner)]])
    sq = [(x, y) for x, y in sorted(comp) if all((x + a, y + b) in comp for a in range(-1, 3) for b in range(-1, 3))]
    if sq:
        x, y = rnd.choice(sq)
        out["H4"] = frozenset(fk[(x + a, y + b)] for a in (0, 1) for b in (0, 1))
    sup = sorted(supports(blk, z, comp, carry))
    if sup:
        out["O1"] = frozenset([rnd.choice(sup)])
        if len(sup) > 1:
            out["OA"] = frozenset(sup)
    cuts = []
    for ax in (0, 1):
        for c in sorted({xy[ax] for xy in comp}):
            line = {xy for xy in comp if xy[ax] == c}
            rest = comps(comp - line)
            if len(rest) >= 2 and min(len(r) for r in rest) >= 3:
                cuts.append(line)
    if cuts:
        out["CUT"] = frozenset(fk[xy] for xy in rnd.choice(cuts))
    return out


def fallen(sup0, sup, rm):
    return {k for k in sup0 if k not in sup and k not in rm and k[3] > 0}


def decoys(blk, sup_both, rm, event, rnd):
    cells = {(c[0], c[1]) for k in rm | event for c in T.part_cells(k)}
    near = {(x + a, y + b) for x, y in cells for a in range(-2, 3) for b in range(-2, 3)}
    pool = sorted(k for k in blk.parts if k[3] > 0 and (k[1], k[2]) in near and k not in rm and k not in event
                  and k in sup_both)
    rnd.shuffle(pool)
    return set(pool[:N_DECOY])


def cmd_pick():
    check_model_lock()
    rnd = random.Random(SEED)
    roles = V.load_roles()
    known = known_blocks()
    vess = T.vessels()
    cand = []
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None or blk.sz < 2 or kind != "terrain" or bname.upper() in known or \
                any(p in bname.upper() or p in tname.upper() for p in DEV_PEEK) or \
                (tname.upper(), bname.upper()) in vess or tname.upper() in T.hull_terrains():
            continue
        if any(z > 0 and len(blk.lv[z]["f"]) >= COMP_MIN for z in range(blk.sz)):
            cand.append((tname, bname, blk))
    rnd.shuffle(cand)
    print("блоков-кандидатов (не виденных, с полом выше земли) %d, смотрю %d" % (len(cand), min(len(cand), MAX_BLOCKS)),
          flush=True)
    pool = []
    seen_name = set()
    for tname, bname, blk in cand[:MAX_BLOCKS]:
        if bname.upper() in seen_name:
            continue
        seen_name.add(bname.upper())
        V.apply_roles(blk, roles)
        s0 = {}
        for name, fn in MODELS:
            s0[name] = fn(blk, frozenset())
        H.evaluate5(blk, frozenset(), H.MODEL)
        carry = set(blk.carry)
        both0 = s0["M0h"] & s0["M0f"]
        opts = []
        for z in range(1, blk.sz):
            for comp in comps(set(blk.lv[z]["f"])):
                if COMP_MIN <= len(comp) <= COMP_MAX and all(blk.lv[z]["f"][xy] in both0 for xy in comp):
                    opts.append((z, comp))
        if not opts:
            continue
        z, comp = rnd.choice(opts)
        for dk, rm in sorted(damages(blk, z, comp, carry, rnd).items()):
            fl = {name: fallen(s0[name], fn(blk, rm), rm) for name, fn in MODELS}
            pool.append({"kind": dk, "terrain": tname, "block": bname, "blk": blk, "z": z, "comp": comp, "rm": rm,
                         "fallen": fl, "s0": s0, "diff": fl["M0h"] != fl["M0f"], "r": rnd.random()})
    print("сценариев-кандидатов %d, из них M0h и M0f расходятся %d" % (len(pool), sum(p["diff"] for p in pool)),
          flush=True)
    picked, used_b, used_t = [], set(), collections.Counter()

    def take(rows, need):
        got = 0
        for pass_ in (0, 1):
            for p in sorted(rows, key=lambda p: p["r"]):
                if got >= need:
                    return got
                if p["block"].upper() in used_b or (pass_ == 0 and used_t[p["terrain"].upper()]):
                    continue
                picked.append(p)
                used_b.add(p["block"].upper())
                used_t[p["terrain"].upper()] += 1
                got += 1
        return got

    for dk in KINDS:
        n = take([p for p in pool if p["kind"] == dk and not p["diff"]], PER_KIND)
        print("вид %s: взято %d" % (dk, n), flush=True)
    n = take([p for p in pool if p["diff"]], N_DIFF)
    print("расхождение M0h/M0f: взято %d" % n, flush=True)
    os.makedirs(REVIEW + "/geom", exist_ok=True)
    order = list(range(len(picked)))
    rnd.shuffle(order)
    task_rows, model_rows, geoms = [], [], {}
    disp = S.disputed_records()
    for n, i in enumerate(order, 1):
        p = picked[i]
        sid = "R-%02d" % n
        blk, rm = p["blk"], p["rm"]
        fk = blk.lv[p["z"]]["f"]
        area = {fk[xy] for xy in p["comp"]} - rm
        event = set().union(*p["fallen"].values())
        both = set.intersection(*[set(s) for s in p["s0"].values()])
        dec = decoys(blk, both, rm, event | area, rnd)
        look = sorted(area | event | dec)
        st = H.Base5(blk, disp).judge(rm)
        task_rows.append([sid, p["terrain"], p["block"], T.compress(sorted(rm)), T.compress(look)])
        model_rows.append([sid, p["kind"], "да" if p["diff"] else "", p["terrain"], p["block"], p["z"],
                           T.compress(sorted(rm)), T.compress(sorted(p["fallen"]["M0h"])),
                           T.compress(sorted(p["fallen"]["M0f"])), T.compress(sorted(p["fallen"]["M0g"])),
                           st["status"], json.dumps(st["why"], ensure_ascii=False)])
        geoms[(blk.terrain.upper(), blk.name.upper())] = blk
    task_rows.sort()
    model_rows.sort()
    for (tn, bn), blk in geoms.items():
        with open("%s/geom/%s__%s.txt" % (REVIEW, tn, bn), "w", encoding=ENC) as f:
            f.write(V.geom_text(blk) + "\n")
    cc.write_tsv(TASK, ["id", "terrain", "block", "remove", "evaluate"], task_rows)
    cc.write_tsv(PICKED, ["id", "kind", "diff", "terrain", "block", "z", "remove", "fallen_M0h", "fallen_M0f",
                          "fallen_M0g", "judge_M0h", "why"], model_rows)
    print("сценариев %d, срезов %d -> %s" % (len(task_rows), len(geoms), REVIEW))


# ------------------------------------------------------------------ ответ, замок, оценка

def load_task_blocks(roles):
    task = {r["id"]: r for r in P.read_tsv(TASK)}
    want = {(r["terrain"].upper(), r["block"].upper()) for r in task.values()}
    return task, G.load_many(want, roles)


def cmd_check():
    roles = V.load_roles()
    task, blocks = load_task_blocks(roles)
    exp = P.read_tsv(EXPECT)
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
    check_model_lock()
    if os.path.exists(RLOCK):
        raise SystemExit("замок уже есть: " + RLOCK)
    if cmd_check():
        raise SystemExit("ответ рецензента не прошёл проверку формы - замок не пишется")
    files = [TASK, EXPECT, PICKED, H.LOCK, "tools/collapse_review5.py"] + \
        sorted(REVIEW + "/geom/" + n for n in os.listdir(REVIEW + "/geom"))
    lines = ["эталон 0h по реальным зданиям, записано %s - до оценки модели" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "ответ писал слепой рецензент (%s/TASK.md) без доступа к модели" % REVIEW]
    lines += ["%s sha256 %s" % (p, sha(p)) for p in files]
    with open(RLOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:7]), "...")


def cmd_score():
    check_model_lock()
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
    task, blocks = load_task_blocks(roles)
    pm = {r["id"]: r for r in P.read_tsv(PICKED)}
    rows = []
    tot = collections.defaultdict(collections.Counter)
    for e in P.read_tsv(EXPECT):
        t = task[e["id"]]
        blk = blocks[(t["terrain"].upper(), t["block"].upper())]
        rm = frozenset(cc.select(blk, t["remove"]))
        mf = cc.select(blk, e["must_fall"]) - rm
        ms = cc.select(blk, e["must_stand"]) - rm
        group = "рушится" if mf else "стоит"
        meta = pm[e["id"]]
        for name, fn in MODELS + [("ничего не ронять", None)]:
            if fn is None:
                s0 = MODELS[0][1](blk, frozenset())
                sup = set(s0) - rm
            else:
                s0 = fn(blk, frozenset())
                sup = fn(blk, rm)
            missed = sorted(k for k in mf if k in sup and k in s0)
            false = sorted(k for k in ms if k not in sup and k in s0)
            ok = not missed and not false
            for scope in ("все", "судья M0h OK") if meta["judge_M0h"] == "OK" else ("все",):
                c = tot[(name, group, scope)]
                c["сценариев"] += 1
                c["верно"] += ok
                c["ложных обвалов"] += len(false)
                c["пропущенных обвалов"] += len(missed)
                c["частей должно стоять"] += len(ms)
                c["частей должно упасть"] += len(mf)
            rows.append([e["id"], meta["kind"], meta["diff"], meta["judge_M0h"], group, name,
                         "да" if ok else "нет", len(false), len(missed), T.compress(false), T.compress(missed)])
    cc.write_tsv(OUT + "/review_score.tsv", ["id", "kind", "diff", "judge_M0h", "group", "model", "ok",
                                             "false_falls", "missed_falls", "false_parts", "missed_parts"], rows)
    res = {"%s / %s / %s" % k: dict(v) for k, v in sorted(tot.items())}
    with open(OUT + "/review_score.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"pick": cmd_pick, "check": cmd_check, "lock": cmd_lock, "score": cmd_score}.get(cmd)
    if fn is None:
        print(__doc__)
        sys.exit(0)
    sys.exit(fn() or 0)
