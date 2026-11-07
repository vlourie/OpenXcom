#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0i обрушения зданий, вторая версия модели: M0i2 = M0i без правила c (консоль от клетки на балке до 1).

Почему: самопроверка на всех целых блоках (stage0i/selfcheck.json) показала, что M0i роняет до боя 1210 полов,
156 w, 121 n и 111 предметов в 200 блоках, и всё это - одно правило c (scratchpad intact_by_flag: без c потерь 0,
только c - все потери). Правило c выведено на сценарии разработки R-32 и ломает здания, которые стоят до боя.
X и F на целых блоках не меняют ничего, k держит ещё 111 частей.

Модель и судья - из collapse_v6 (файл под замком stage0i/rules.lock.txt не меняется), здесь только набор флагов
и списки кандидатов судьи без c. Замок этой версии - stage0i/rules2.lock.txt, итоги - stage0i/m0i2.

    py -3.13 tools\collapse_v6b.py lock        замок M0i2 (до слепого набора 0i)
    py -3.13 tools\collapse_v6b.py selfcheck   M0i2 против M0h на всех целых блоках
    py -3.13 tools\collapse_v6b.py synth       контролируемые конструкции (правда stage0i/synth_truth.tsv)
    py -3.13 tools\collapse_v6b.py dev         33 сценария 0h - разработка, не приёмка
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
import collapse_v5 as H                           # noqa: E402
import collapse_v6 as M                           # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/stage0i/m0i2"
LOCK = "census/collapse/stage0i/rules2.lock.txt"
M0H = H.MODEL
MODEL = M0H + "XFk"                               # M0i2
NEW_RULES = "XFk"
CANDIDATE_RULES = H.CANDIDATE_RULES + NEW_RULES
LOCKED = ["tools/collapse_v6b.py"] + M.LOCKED


def evaluate6b(blk, removed=frozenset(), flags=MODEL, tie="all"):
    return M.evaluate6(blk, removed, flags, tie)


@contextlib.contextmanager
def candidates():
    old = M.CANDIDATE_RULES
    M.CANDIDATE_RULES = CANDIDATE_RULES
    try:
        yield
    finally:
        M.CANDIDATE_RULES = old


class Base6b(M.Base6):
    """Судья Base6 с моделью M0i2 и кандидатами без c."""

    def __init__(self, blk, disp, vessel=False, ver=None, foot=None, model=MODEL):
        with candidates():
            M.Base6.__init__(self, blk, disp, vessel, ver, foot, model)

    def set_foot(self, foot):
        with candidates():
            return M.Base6.set_foot(self, foot)

    def judge(self, removed, extra=()):
        with candidates():
            return M.Base6.judge(self, removed, extra)


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
        raise SystemExit("замок M0i2 нарушен: " + ", ".join(bad))


def cmd_lock():
    if os.path.exists(LOCK):
        raise SystemExit("замок уже есть: " + LOCK)
    lines = ["версия модели M0i2 обрушения, записано %s - до нового слепого набора 0i (часть A - большие здания, "
             "часть B - связи между зданиями на картах holdout3)" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "флаги %s (collapse_v6.evaluate6: M0h плюс X кладка без основания, F навес по целому блоку, k "
             "перемычка с углом; правило c M0i снято - роняло 1210 полов на целых блоках)" % MODEL,
             "судья Base6b: Base6 с кандидатами %s" % CANDIDATE_RULES,
             "оговорка: синтетика и 33 сценария 0h для варианта 'M0i без c' уже смотрелись (stage0i/dev_0h.tsv) - "
             "это разработка; приёмка - только слепой набор 0i"]
    lines += ["%s sha256 %s" % (p, M.sha(p)) for p in LOCKED]
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def cmd_selfcheck():
    check_lock()
    roles = V.load_roles()
    os.makedirs(OUT, exist_ok=True)
    diff = collections.Counter()
    rows, nblk, t0 = [], 0, time.time()
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None:
            continue
        V.apply_roles(blk, roles)
        nblk += 1
        a = H.evaluate5(blk, frozenset(), M0H)[0]
        i = evaluate6b(blk, frozenset(), MODEL)[0]
        lost = sorted(k for k in a - i if k[3] > 0)
        got = sorted(k for k in i - a if k[3] > 0)
        for k in lost:
            diff[("M0i2 роняет", k[0], blk.parts[k].get("role", ""))] += 1
        for k in got:
            diff[("M0i2 держит", k[0], blk.parts[k].get("role", ""))] += 1
        if lost or got:
            rows.append([tname, bname, len(lost), len(got), T.compress(lost)[:400], T.compress(got)[:400]])
    cc.write_tsv(OUT + "/selfcheck_intact.tsv", ["terrain", "block", "drops", "holds", "drop_parts", "hold_parts"],
                 rows)
    res = {"blocks": nblk, "blocks_differ": len(rows), "by_kind": {" ".join(k): v for k, v in sorted(diff.items())},
           "sec": round(time.time() - t0)}
    with open(OUT + "/selfcheck.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


def models():
    out = [("M0i2", lambda blk, rm: evaluate6b(blk, rm, MODEL)[0])]
    for e in NEW_RULES:
        out.append(("M0i2 без " + e, lambda blk, rm, e=e: evaluate6b(blk, rm, MODEL.replace(e, ""))[0]))
    out += [("M0i", lambda blk, rm: M.evaluate6(blk, rm, M.MODEL)[0]),
            ("M0h", lambda blk, rm: H.evaluate5(blk, rm, M0H)[0]),
            ("M0f", lambda blk, rm: T.evaluate3(blk, rm, H.M0F)[0])]
    return out


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
        for name, cls_ in (("M0i2", Base6b), ("M0h", H.Base5)):
            st = cls_(M.synth_block(t["build"]), disp).judge(rm)
            judge_rows.append([t["id"], name, st["status"], t["judge_expect"],
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
    for r in rows:
        if r[4] == "нет" and r[3] in ("M0i2", "M0h"):
            print("  ", *r)
    for r in judge_rows:
        print("   судья", *r[:5])


def cmd_dev():
    """Сценарии 0h - разработка. Модель без судьи и судья отдельно; по частям, сценариям и блокам."""
    check_lock()
    import collapse_summary as S
    import collapse_review5 as R
    roles = V.load_roles()
    task, blocks = R.load_task_blocks(roles)
    disp = S.disputed_records()
    ms_ = models() + [("ничего не ронять", None)]
    rows, per, meta = [], {}, {}
    os.makedirs(OUT, exist_ok=True)
    for e in P.read_tsv(R.EXPECT):
        t = task[e["id"]]
        bkey = (t["terrain"].upper(), t["block"].upper())
        blk = blocks[bkey]
        rm = frozenset(cc.select(blk, t["remove"]))
        mf = cc.select(blk, e["must_fall"]) - rm
        ms = cc.select(blk, e["must_stand"]) - rm
        group = "рушится" if mf else "стоит"
        ji = Base6b(blk, disp).judge(rm)
        jh = H.Base5(blk, disp).judge(rm)
        meta[e["id"]] = (group, bkey, ji["status"], jh["status"], ji["why"])
        for name, fn in ms_:
            if fn is None:
                s0 = evaluate6b(blk, frozenset(), MODEL)[0]
                sup = set(s0) - rm
            else:
                s0, sup = fn(blk, frozenset()), fn(blk, rm)
            missed = sorted(k for k in mf if k in sup and k in s0)
            false = sorted(k for k in ms if k not in sup and k in s0)
            per[(name, e["id"])] = (not missed and not false, len(false), len(missed))
            rows.append([e["id"], group, "%s/%s" % bkey, ji["status"], jh["status"], name,
                         "да" if not missed and not false else "нет", len(false), len(missed), T.compress(false),
                         T.compress(missed)])
    cc.write_tsv(OUT + "/dev_0h.tsv", ["id", "group", "block", "judge_M0i2", "judge_M0h", "model", "ok",
                                       "false_falls", "missed_falls", "false_parts", "missed_parts"], rows)
    res = {}
    for scope, keep in (("модель, все сценарии", lambda m: True), ("судья M0i2 OK", lambda m: m[2] == "OK"),
                        ("судья M0h OK", lambda m: m[3] == "OK")):
        for name, _ in ms_:
            for group in ("рушится", "стоит"):
                ids = [i for i, m in meta.items() if m[0] == group and keep(m)]
                if not ids:
                    continue
                bl = collections.defaultdict(list)
                for i in ids:
                    bl[meta[i][1]].append(per[(name, i)][0])
                res["%s / %s / %s" % (scope, name, group)] = {
                    "сценариев": len(ids), "верно": sum(per[(name, i)][0] for i in ids),
                    "ложных частей": sum(per[(name, i)][1] for i in ids),
                    "пропущенных частей": sum(per[(name, i)][2] for i in ids),
                    "блоков": len(bl), "блоков верно": sum(all(v) for v in bl.values())}
    res["судья"] = {i: {"M0i2": m[2], "M0h": m[3], "почему M0i2": m[4]} for i, m in sorted(meta.items())}
    with open(OUT + "/dev_0h.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    for k, v in res.items():
        if k != "судья" and ("M0i2" in k.split(" / ")[1] or k.split(" / ")[1] in ("M0h", "ничего не ронять")):
            print(k, v)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"lock": cmd_lock, "selfcheck": cmd_selfcheck, "synth": cmd_synth, "dev": cmd_dev}.get(cmd)
    if fn is None:
        print(__doc__)
        sys.exit(0)
    sys.exit(fn() or 0)
