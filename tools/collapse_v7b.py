#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0k обрушения зданий, вторая версия M0j (M0j2). collapse_v7.py и его замок не меняются - M0j2 живёт здесь.

Почему вторая версия. Правило a в M0j (collapse_v7) применялось ко ВСЕМУ слоту o: на целых блоках (стоят до боя)
оно уронило 1284 части, и почти все - конструкция, а не предметы: стены в слоте o (роль WALL, edgewall и block)
486, непросмотренные колонны (COLUMN, при U - мебель) 402, фермы 11, кроны 4 (census/collapse/stage0k/a_drops.txt).
Рецензия 0j говорит о ПРЕДМЕТЕ: «предмет получает опору от пола; от стены - только при явном креплении».

M0j2 = M0j, но правило a действует только на часть слота o с ролью предмета (ITEM_ROLES: OBJECT - авто по классу
MCD object, и роли мебели FURNITURE, TRUNK, MACHINE, STAIRS). Конструкция в слоте o (WALL, COLUMN, TRUSS, MASS,
HULL - просмотренная и нет), крона CROWN и особые роли держатся как в M0i2. Критерий - по смыслу роли, а не по
числу потерь; он выбран после переписи M0j, поэтому 0h и 0i и перепись целых блоков здесь - разработка, не приёмка.
Правило b - без изменений (collapse_v7.wall_on_object).

Авто OBJECT (класс MCD object без просмотра) бывает и куском стены или кровли: такие потери - не решение модели, а
лист кандидатов на разметку (attach - крепление, или роль конструкции) - команда attach.

    py -3.13 tools\collapse_v7b.py lock        замок M0j2 (до прогона)
    py -3.13 tools\collapse_v7b.py selfcheck   M0j2 без a = M0j без a; целые блоки: что a и b меняют против M0i2
    py -3.13 tools\collapse_v7b.py synth       I1-I4
    py -3.13 tools\collapse_v7b.py dev         сценарии 0h и 0i - разработочные наборы
    py -3.13 tools\collapse_v7b.py attach      лист предметов, которые a роняет на целых блоках (кандидаты разметки)
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
import collapse_v7 as J                           # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/stage0k/v2"
LOCK = OUT + "/rules.lock.txt"
M0I2 = J.M0I2
MODEL = J.MODEL                                   # флаги те же (M0i2 + ab), меняется смысл a
ITEM_ROLES = {"OBJECT"} | V.FURN_ROLES            # предмет: OBJECT, FURNITURE, TRUNK, MACHINE, STAIRS
LOCKED = ["tools/collapse_v7b.py", "tools/collapse_v7.py"] + B.LOCKED


@contextlib.contextmanager
def items_only():
    """Правило a в collapse_v7.evaluate2j не трогает часть, чья роль в J.ATTACH_ROLES. Здесь туда на время
    добавляются все роли, которые не предметы: для конструкции a не действует, она держится как в M0i2."""
    old = J.ATTACH_ROLES
    J.ATTACH_ROLES = old | ALL_NON_ITEM
    try:
        yield
    finally:
        J.ATTACH_ROLES = old


ALL_NON_ITEM = {"WALL", "COLUMN", "TRUSS", "MASS", "HULL", "CROWN", "ROOF", "TARP", "RUN", "HANGER", "LOW", "DOOR",
                "FLOOR", ""}


def evaluate7b(blk, removed=frozenset(), flags=MODEL, tie="all"):
    """M0j2. Роль части, не известная ни ITEM_ROLES, ни ALL_NON_ITEM, - ошибка (новая роль требует решения)."""
    unk = {p.get("role", "") for k, p in blk.parts.items() if k[0] == "o"} - ITEM_ROLES - ALL_NON_ITEM
    if unk:
        raise SystemExit("M0j2: роль слота o не решена (предмет или нет): %s" % sorted(unk))
    with items_only():
        return J.evaluate7(blk, removed, flags, tie)


class Base7b(J.Base7):
    """Судья M0j (Base7) с правилом a только для предметов."""

    def __init__(self, *a, **kw):
        with items_only():
            J.Base7.__init__(self, *a, **kw)

    def set_foot(self, foot):
        with items_only():
            return J.Base7.set_foot(self, foot)

    def judge(self, removed, extra=()):
        with items_only():
            return J.Base7.judge(self, removed, extra)


# ------------------------------------------------------------------ замок

def check_lock():
    lock = {}
    with open(LOCK, encoding=ENC) as f:
        for line in f:
            p = line.rstrip("\n").split(" sha256 ")
            if len(p) == 2:
                lock[p[0]] = p[1]
    bad = [p for p in LOCKED if lock.get(p) != M.sha(p)]
    if bad:
        raise SystemExit("замок M0j2 нарушен: " + ", ".join(bad))


def cmd_lock():
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(LOCK):
        raise SystemExit("замок уже есть: " + LOCK)
    lines = ["версия модели M0j2 обрушения (исследовательская), записано %s - до прогона M0j2" %
             time.strftime("%Y-%m-%d %H:%M:%S"),
             "флаги %s как у M0j; правило a - только для частей слота o с ролью предмета %s; конструкция "
             "(WALL, COLUMN, TRUSS, MASS, HULL), крона и особые роли - как в M0i2; правило b без изменений" %
             (MODEL, sorted(ITEM_ROLES)),
             "M0j (collapse_v7, замок census/collapse/stage0k/rules.lock.txt) отклонена переписью целых блоков: "
             "a уронило 1284 части, почти все - конструкция в слоте o (a_drops.txt)",
             "критерий предмета выбран по смыслу роли ПОСЛЕ переписи M0j: 0h, 0i и целые блоки - разработка, "
             "не приёмка"]
    lines += ["%s sha256 %s" % (p, M.sha(p)) for p in LOCKED]
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


# ------------------------------------------------------------------ проверки

def models():
    return [("M0j2", lambda blk, rm: evaluate7b(blk, rm, MODEL)[0]),
            ("M0j2 без a", lambda blk, rm: evaluate7b(blk, rm, MODEL.replace("a", ""))[0]),
            ("M0j2 без b", lambda blk, rm: evaluate7b(blk, rm, MODEL.replace("b", ""))[0]),
            ("M0j", lambda blk, rm: J.evaluate7(blk, rm, MODEL)[0]),
            ("M0i2", lambda blk, rm: B.evaluate6b(blk, rm, M0I2)[0])]


def intact_blocks():
    roles = V.load_roles()
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None:
            continue
        V.apply_roles(blk, roles)
        yield tname, bname, blk


def cmd_selfcheck():
    """1) M0j2 без a = M0j без a (b не тронуто) на всех целых блоках; 2) что M0j2, только a, только b меняют против
    M0i2 на целых блоках - по слоту и роли."""
    check_lock()
    os.makedirs(OUT, exist_ok=True)
    diff = collections.Counter()
    rows, nblk, same, t0 = [], 0, 0, time.time()
    for tname, bname, blk in intact_blocks():
        nblk += 1
        base = B.evaluate6b(blk, frozenset(), M0I2)[0]
        same += J.evaluate7(blk, frozenset(), M0I2 + "b")[0] == evaluate7b(blk, frozenset(), M0I2 + "b")[0]
        for name, fl in (("M0j2", MODEL), ("только a", M0I2 + "a"), ("только b", M0I2 + "b")):
            s = evaluate7b(blk, frozenset(), fl)[0]
            lost = sorted(k for k in base - s if k[3] > 0)
            got = sorted(k for k in s - base if k[3] > 0)
            for k in lost:
                diff[(name, "роняет", k[0], blk.parts[k].get("role", ""))] += 1
            for k in got:
                diff[(name, "держит", k[0], blk.parts[k].get("role", ""))] += 1
            if (lost or got) and name == "M0j2":
                rows.append([tname, bname, len(lost), len(got), T.compress(lost)[:400], T.compress(got)[:400]])
    cc.write_tsv(OUT + "/selfcheck_intact.tsv", ["terrain", "block", "drops", "holds", "drop_parts", "hold_parts"],
                 rows)
    res = {"blocks": nblk, "M0j2 без a = M0j без a (блоков)": same, "blocks_differ_M0j2": len(rows),
           "by_kind": {" ".join(k): v for k, v in sorted(diff.items())}, "sec": round(time.time() - t0)}
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
        st = Base7b(M.synth_block(t["build"]), disp).judge(rm)
        judge_rows.append([t["id"], "M0j2", st["status"], t["judge_expect"],
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
            js = Base7b(blk, disp).judge(rm)["status"]
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
    cc.write_tsv(OUT + "/dev.tsv", ["set", "id", "kind", "group", "judge_M0j2", "model", "ok", "false_falls",
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
        if len({per[(n, i)] for n in ("M0j2", "M0j", "M0i2")}) > 1:
            changed[i] = {n: per[(n, i)] for n in ("M0j2", "M0j", "M0i2", "M0j2 без a", "M0j2 без b")}
    res["сценарии, где M0j2, M0j и M0i2 расходятся (верно, ложных, пропущенных)"] = changed
    res["судья M0j2"] = dict(collections.Counter(m[3] for m in meta.values()))
    with open(OUT + "/dev.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


def cmd_attach():
    """Предметы, которые правило a M0j2 роняет на целых блоках: по записи - роль, источник роли, есть ли пол, сколько
    частей, пример. Это лист для разметки (крепление или роль конструкции), а не решение модели."""
    check_lock()
    os.makedirs(OUT, exist_ok=True)
    rec, ex = collections.Counter(), {}
    for tname, bname, blk in intact_blocks():
        base = evaluate7b(blk, frozenset(), M0I2 + "b")[0]
        s = evaluate7b(blk, frozenset(), MODEL)[0]
        for k in base - s:
            if k[3] == 0 or k[0] != "o":
                continue
            p = blk.parts[k]
            fl = blk.lv[k[3]]["f"].get((k[1], k[2]))
            floor = "нет пола" if fl is None else ("пол держится" if fl in s else "пол не держится")
            r = (p["set"], p["idx"], p.get("role", ""), "просмотрено" if p.get("rev") else "авто", p["cls"], floor)
            rec[r] += 1
            ex.setdefault(r, "%s/%s %s" % (tname, bname, ",".join(map(str, k))))
    rows = [list(r) + [n, ex[r]] for r, n in sorted(rec.items(), key=lambda kv: (-kv[1], kv[0]))]
    cc.write_tsv(OUT + "/attach_candidates.tsv", ["set", "idx", "role", "role_source", "mcd_class", "floor",
                                                  "parts", "example"], rows)
    agg = collections.Counter()
    for r, n in rec.items():
        agg[(r[2], r[3], r[5])] += n
    print("записей", len(rows), "частей", sum(rec.values()))
    for k, v in sorted(agg.items(), key=lambda kv: -kv[1]):
        print(" ", v, *k)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"lock": cmd_lock, "selfcheck": cmd_selfcheck, "synth": cmd_synth, "dev": cmd_dev,
          "attach": cmd_attach}.get(cmd)
    if fn is None:
        print(__doc__)
        sys.exit(0)
    sys.exit(fn() or 0)
