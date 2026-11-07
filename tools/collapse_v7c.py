#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0l обрушения зданий: M0j3 = M0j2 (collapse_v7b, не меняется) + разметка крепления 107 записей
(census/collapse/stage0l/attach_marks.tsv, замок attach_marks.lock.txt, инструмент collapse_attach.py).

Рецензия 0k: автоматическая роль - не основание для обрушения; разметка «стоит на поверхности / прикреплено /
несущая конструкция / неизвестно»; крепление указывает, к чему прикреплено.

Как разметка входит в расчёт (только части слота o, выше z0):
    STRUCTURE <роль>   роль части = <роль> (ROOF, WALL, MASS, HULL, COLUMN, TRUSS), просмотрено; дальше - ядро M0j2
    SURFACE floor      держится, пока держится пол своей клетки
    SURFACE below      держится, пока держится предмет слота o клеткой ниже
    ATTACHED w|n|e|s   держится, пока держится названная стена своей клетки (e - w соседа x+1, s - n соседа y+1)
    ATTACHED up        держится, пока держится пол клетки этажом выше
    ATTACHED ow|on|oe|os  держится, пока держится часть слота o соседней клетки с этой стороны
    несколько целей через '+' - держится, пока держится ХОТЯ БЫ одна; цепочки (труба на трубе) - наименьшая
    неподвижная точка: кольцо креплений без внешней опоры не держится
    в месте, где ни одной цели нет вовсе (в целом блоке), разметка не применима: часть держится как в M0j2, а место
    помечено UNKNOWN
    UNKNOWN            держится как в M0j2; судья: её падение - UNSUPPORTED
Судья M0j3 = судья M0j2 (Base7b) на M0j3 плюс UNSUPPORTED, если падает часть с разметкой UNKNOWN, спорная разметка
низкой уверенности, часть в месте без цели, или непросмотренный предмет (авто-роль, без разметки), упавший только
из-за правила a. Последствия смены исхода размеченной части для неразмеченных частей над ней не пересчитываются
(предмет на предмете): это допущение, а не правило.

0h и 0i - наборы разработки, не независимая выборка (рецензия 0k).

    py -3.13 tools\collapse_v7c.py lock      замок M0j3 (до прогона)
    py -3.13 tools\collapse_v7c.py intact    целые здания: что M0j3 роняет и держит против M0j2 и M0i2+b, конфликты
    py -3.13 tools\collapse_v7c.py dev       сценарии 0h и 0i
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
import collapse_v6 as M                           # noqa: E402
import collapse_v6b as B                          # noqa: E402
import collapse_v7 as J                           # noqa: E402
import collapse_v7b as K                          # noqa: E402
import collapse_attach as A                       # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/stage0l"
LOCK = OUT + "/m0j3.lock.txt"
MODEL = K.MODEL
M0I2 = K.M0I2
LOCKED = ["tools/collapse_v7c.py", "tools/collapse_attach.py", A.MARKS, A.GEOM] + K.LOCKED
ORIG7 = J.evaluate7                               # ядро M0j/M0j2; J.evaluate7 подменяется только в судье
_MARKS = None


def marks():
    global _MARKS
    if _MARKS is None:
        A.check_lock()
        _MARKS = A.read_marks()
    return _MARKS


def apply_marks(blk):
    """Разметка - на части слота o (поле mark); роль части не меняет - роль STRUCTURE только внутри marked_roles."""
    mk = marks()
    for key, p in blk.parts.items():
        if key[0] != "o":
            continue
        r = mk.get((p["set"].upper(), p["idx"]))
        if r is None:
            p.pop("mark", None)
            continue
        p["mark"] = (r["mark"], r["to"], r["confidence"], bool(r["dispute"].strip()))
    return blk


@contextlib.contextmanager
def marked_roles(blk):
    """На время расчёта M0j3 роль STRUCTURE-частей = разметка (просмотрено), после - прежняя: M0j2 и M0i2+b на том
    же блоке считаются со своими ролями. Вложенные вызовы (судья внутри судьи) подменяют один раз."""
    apply_marks(blk)
    d = blk.__dict__
    if d.get("_m0l_depth", 0) == 0:
        saved = {}
        for k, p in blk.parts.items():
            m = p.get("mark")
            if m and m[0] == "STRUCTURE":
                saved[k] = (p.get("role"), p.get("rev"))
                p["role"], p["rev"] = m[1], True
        d["_m0l_saved"] = saved
    d["_m0l_depth"] = d.get("_m0l_depth", 0) + 1
    try:
        yield
    finally:
        d["_m0l_depth"] -= 1
        if d["_m0l_depth"] == 0:
            for k, (r, v) in d.pop("_m0l_saved").items():
                p = blk.parts[k]
                p["role"] = r
                if v is None:
                    p.pop("rev", None)
                else:
                    p["rev"] = v


def core(blk, removed, flags, tie):
    """M0j2 (collapse_v7b.evaluate7b), но через сохранённое ядро ORIG7 - J.evaluate7 в судье подменён."""
    unk = {p.get("role", "") for k, p in blk.parts.items() if k[0] == "o"} - K.ITEM_ROLES - K.ALL_NON_ITEM
    if unk:
        raise SystemExit("M0j3: роль слота o не решена (предмет или нет): %s" % sorted(unk))
    with K.items_only():
        return ORIG7(blk, removed, flags, tie)


def targets(blk, key, to):
    """Части, к которым прикреплена или на которых стоит часть key (в целом блоке)."""
    _, x, y, z = key
    L = blk.lv[z]
    out = []
    for t in to.split("+"):
        if t == "floor":
            q = L["f"].get((x, y))
        elif t == "below":
            q = blk.lv[z - 1]["o"].get((x, y)) if z > 0 else None
        elif t == "up":
            q = blk.lv[z + 1]["f"].get((x, y)) if z + 1 < blk.sz else None
        elif t in A.SIDE:
            s, dx, dy = A.SIDE[t]
            q = L[s].get((x + dx, y + dy))
        elif t in A.NEIGH:
            dx, dy = A.NEIGH[t]
            q = L["o"].get((x + dx, y + dy))
        else:
            raise SystemExit("M0j3: неизвестная цель %s у %s" % (t, key))
        if q is not None:
            out.append(q)
    return out


def marked_parts(blk):
    """{часть: (вид, цели в целом блоке)} для SURFACE и ATTACHED выше z0; место без целей - пустой список."""
    cache = blk.__dict__.setdefault("_m0l", {})
    if "tg" not in cache:
        cache["tg"] = {k: (p["mark"][0], targets(blk, k, p["mark"][1])) for k, p in blk.parts.items()
                       if p.get("mark") and p["mark"][0] in ("SURFACE", "ATTACHED") and k[3] > 0}
    return cache["tg"]


def evaluate7c(blk, removed=frozenset(), flags=MODEL, tie="all"):
    """M0j3: ядро M0j2 с ролями STRUCTURE, затем держание SURFACE и ATTACHED по своим целям."""
    removed = frozenset(removed)
    with marked_roles(blk):
        sup, info = core(blk, removed, flags, tie)
    tg = {k: v for k, v in marked_parts(blk).items() if k not in removed}
    held = set(sup) - set(tg)
    pending = {}
    for k, (kind, ts) in tg.items():
        if not ts:                                 # места без цели: разметка не применима, как в M0j2
            if k in sup:
                held.add(k)
        else:
            pending[k] = [q for q in ts if q not in removed]
    changed = True
    while changed:
        changed = False
        for k in list(pending):
            if any(q in held for q in pending[k]):
                held.add(k)
                del pending[k]
                changed = True
    return held, info


# ------------------------------------------------------------------ судья

@contextlib.contextmanager
def as_m0j3():
    """Судья M0j (Base7) зовёт модуль-функцию J.evaluate7 - на время судьи это M0j3."""
    J.evaluate7 = evaluate7c
    try:
        yield
    finally:
        J.evaluate7 = ORIG7


def uncertain(blk):
    """Части, падение которых не решается разметкой: UNKNOWN, спорная разметка низкой уверенности, место без цели."""
    apply_marks(blk)
    tg = marked_parts(blk)
    out = {}
    for k, p in blk.parts.items():
        m = p.get("mark")
        if not m:
            continue
        if m[0] == "UNKNOWN":
            out[k] = "разметка UNKNOWN %s:%d" % (p["set"].upper(), p["idx"])
        elif m[2] == "low" and m[3]:
            out[k] = "спорная разметка %s:%d" % (p["set"].upper(), p["idx"])
        elif k in tg and not tg[k][1]:
            out[k] = "нет цели крепления в этом месте %s:%d" % (p["set"].upper(), p["idx"])
    return out


def auto_item(p, key):
    return key[0] == "o" and not p.get("mark") and not p.get("rev") and p.get("role") in K.ITEM_ROLES


class Base7c(K.Base7b):
    def __init__(self, blk, *a, **kw):
        with as_m0j3(), marked_roles(blk):
            K.Base7b.__init__(self, blk, *a, **kw)
        self.unc = uncertain(blk)

    def set_foot(self, foot):
        with as_m0j3(), marked_roles(self.blk):
            return K.Base7b.set_foot(self, foot)

    def judge(self, removed, extra=()):
        with as_m0j3(), marked_roles(self.blk):
            res = K.Base7b.judge(self, removed, extra)
        removed = frozenset(removed)
        fallen = res["fallen"]
        why = res["why"]
        for k in fallen:
            if k in self.unc:
                why[self.unc[k]] = why.get(self.unc[k], 0) + 1
        s_na = evaluate7c(self.blk, removed, MODEL.replace("a", ""))[0]
        s0_na = evaluate7c(self.blk, frozenset(), MODEL.replace("a", ""))[0]
        by_a = fallen - self.fallen_of(s0_na, s_na, removed)
        n = sum(1 for k in by_a if auto_item(self.blk.parts[k], k))
        if n:
            why["непросмотренный предмет падает только по правилу a"] = n
        if why:
            res["status"] = "UNSUPPORTED"
        return res


# ------------------------------------------------------------------ замок

def check_lock():
    A.check_lock()
    lock = {}
    with open(LOCK, encoding=ENC) as f:
        for line in f:
            p = line.rstrip("\n").split(" sha256 ")
            if len(p) == 2:
                lock[p[0]] = p[1]
    bad = [p for p in LOCKED if lock.get(p) != M.sha(p)]
    if bad:
        raise SystemExit("замок M0j3 нарушен: " + ", ".join(bad))


def cmd_lock():
    A.check_lock()
    if os.path.exists(LOCK):
        raise SystemExit("замок уже есть: " + LOCK)
    lines = ["версия модели M0j3 обрушения (исследовательская), записано %s - до прогона M0j3" %
             time.strftime("%Y-%m-%d %H:%M:%S"),
             "ядро M0j2 (collapse_v7b, флаги %s) без изменений; поверх - разметка крепления 107 записей этапа 0l "
             "(attach_marks.tsv под своим замком): STRUCTURE - роль, SURFACE и ATTACHED - держание по своим целям, "
             "UNKNOWN и место без цели - UNSUPPORTED у судьи" % MODEL,
             "разметка сделана по кадру, LOFT и окружению мест без пола, до прогона M0j3; кандидаты - записи, "
             "которые правило a M0j2 роняет на целых блоках (stage0k/v2/attach_candidates.tsv); 0h и 0i - "
             "разработка"]
    lines += ["%s sha256 %s" % (p, M.sha(p)) for p in LOCKED]
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


# ------------------------------------------------------------------ целые здания

def why_lost(blk, k, sup):
    """Почему часть, которую M0i2+b держит, у M0j3 не держится (целый блок)."""
    p = blk.parts[k]
    m = p.get("mark")
    if m:
        tg = marked_parts(blk).get(k)
        if m[0] == "UNKNOWN":
            return "UNSUPPORTED", "разметка UNKNOWN"
        if tg is not None and not tg[1]:
            return "UNSUPPORTED", "%s %s: нет цели в этом месте" % (m[0], m[1])
        if m[0] == "SURFACE":
            return "CONFLICT", "SURFACE %s: опора есть, но сама не держится на целом блоке" % m[1]
        if m[0] == "ATTACHED":
            return "CONFLICT", "ATTACHED %s: цель есть, но сама не держится на целом блоке" % m[1]
        return "CONFLICT", "STRUCTURE %s: не держится по ядру" % m[1]
    if auto_item(p, k):
        return "UNSUPPORTED", "авто-роль %s без разметки" % p.get("role")
    return "CONFLICT", "%s роль %s без разметки" % ("просмотрено" if p.get("rev") else "авто", p.get("role"))


def cmd_intact():
    check_lock()
    os.makedirs(OUT, exist_ok=True)
    tot = collections.Counter()
    lost_rec, gain_rec, ex = collections.Counter(), collections.Counter(), {}
    nt_rec = collections.Counter()
    t0 = time.time()
    for tname, bname, blk in K.intact_blocks():
        apply_marks(blk)
        tot["блоков"] += 1
        base = K.evaluate7b(blk, frozenset(), M0I2 + "b")[0]
        s2 = K.evaluate7b(blk, frozenset(), MODEL)[0]
        s3 = evaluate7c(blk, frozenset(), MODEL)[0]
        up = [k for k in blk.parts if k[3] > 0]
        tot["частей выше z0"] += len(up)
        for name, s in (("M0i2+b", base), ("M0j2", s2), ("M0j3", s3)):
            tot["не держится, %s" % name] += sum(1 for k in up if k not in s)
        tot["M0j2 роняет против M0i2+b"] += sum(1 for k in up if k in base and k not in s2)
        for k, (kind, ts) in marked_parts(blk).items():
            if not ts:
                p = blk.parts[k]
                nt_rec[(p["set"].upper(), p["idx"], p["mark"][0], p["mark"][1])] += 1
        for k in up:
            p = blk.parts[k]
            rid = (p["set"].upper(), p["idx"], k[0])
            if k in base and k not in s3:
                st, why = why_lost(blk, k, s3)
                r = rid + (st, why)
                lost_rec[r] += 1
                tot["M0j3 роняет против M0i2+b: " + st] += 1
                ex.setdefault(r, "%s/%s %s" % (tname, bname, ",".join(map(str, k))))
            elif k not in base and k in s3:
                m = p.get("mark")
                r = rid + ("держит", "%s %s" % (m[0], m[1]) if m else "без разметки")
                gain_rec[r] += 1
                tot["M0j3 держит, M0i2+b нет"] += 1
                ex.setdefault(r, "%s/%s %s" % (tname, bname, ",".join(map(str, k))))
            if k in s2 and k not in s3:
                tot["M0j3 роняет, M0j2 держит"] += 1
            elif k not in s2 and k in s3:
                tot["M0j3 держит, M0j2 роняет"] += 1
    head = ["set", "idx", "slot", "status", "why", "parts", "example"]
    rows = [list(r) + [n, ex[r]] for r, n in sorted(lost_rec.items(), key=lambda kv: (kv[0][3], -kv[1], kv[0]))]
    cc.write_tsv(OUT + "/intact_lost.tsv", head, rows)
    rows = [list(r) + [n, ex[r]] for r, n in sorted(gain_rec.items(), key=lambda kv: (-kv[1], kv[0]))]
    cc.write_tsv(OUT + "/intact_gain.tsv", head, rows)
    cc.write_tsv(OUT + "/intact_no_target.tsv", ["set", "idx", "mark", "to", "places"],
                 [list(r) + [n] for r, n in sorted(nt_rec.items(), key=lambda kv: -kv[1])])
    agg = collections.Counter()
    for r, n in lost_rec.items():
        agg["%s | %s" % (r[3], r[4] if r[3] == "CONFLICT" or "авто" not in r[4] else "авто-роль без разметки")] += n
    res = {"итог": dict(tot), "потери M0j3 по причине": dict(agg.most_common()),
           "записей с потерями": len(lost_rec), "мест без цели (UNKNOWN в месте)": sum(nt_rec.values()),
           "sec": round(time.time() - t0)}
    with open(OUT + "/intact.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ 0h, 0i

def cmd_dev():
    check_lock()
    import collapse_summary as S
    import collapse_span_probe as SP
    disp = S.disputed_records()
    ms_ = [("M0j3", lambda blk, rm: evaluate7c(blk, rm, MODEL)[0]),
           ("M0j2", lambda blk, rm: K.evaluate7b(blk, rm, MODEL)[0]),
           ("M0i2", lambda blk, rm: B.evaluate6b(blk, rm, M0I2)[0]),
           ("ничего не ронять", None)]
    rows, per, meta = [], {}, {}
    for st, i, kind, group, blk, rm, mf, ms in SP.scenarios():
        apply_marks(blk)
        sid = st + " " + i
        try:
            jr = Base7c(blk, disp).judge(rm)
            js, jw = jr["status"], jr["why"]
        except Exception as e:                              # noqa: BLE001
            js, jw = "ERR " + type(e).__name__, {}
        try:
            j2 = K.Base7b(blk, disp).judge(rm)["status"]
        except Exception as e:                              # noqa: BLE001
            j2 = "ERR " + type(e).__name__
        meta[sid] = (st, kind, group, js, j2)
        for name, fn in ms_:
            if fn is None:
                s0 = B.evaluate6b(blk, frozenset(), M0I2)[0]
                sup = set(s0) - rm
            else:
                s0, sup = fn(blk, frozenset()), fn(blk, rm)
            missed = sorted(k for k in mf if k in sup and k in s0)
            false = sorted(k for k in ms if k not in sup and k in s0)
            per[(name, sid)] = (not missed and not false, len(false), len(missed))
            rows.append([st, i, kind, group, js, j2, name, "да" if not missed and not false else "нет", len(false),
                         len(missed), T.compress(false)[:300], T.compress(missed)[:300],
                         json.dumps(jw, ensure_ascii=False)[:300] if name == "M0j3" else ""])
    cc.write_tsv(OUT + "/dev.tsv", ["set", "id", "kind", "group", "judge_M0j3", "judge_M0j2", "model", "ok",
                                    "false_falls", "missed_falls", "false_parts", "missed_parts", "why_M0j3"], rows)
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
    res["сценарии, где M0j3 и M0j2 расходятся (верно, ложных, пропущенных)"] = {
        i: {n: per[(n, i)] for n in ("M0j3", "M0j2", "M0i2")} for i in meta if per[("M0j3", i)] != per[("M0j2", i)]}
    res["судья M0j3"] = dict(collections.Counter(m[3] for m in meta.values()))
    res["судья M0j2"] = dict(collections.Counter(m[4] for m in meta.values()))
    res["судья: M0j2 -> M0j3"] = dict(collections.Counter("%s -> %s" % (m[4], m[3]) for m in meta.values()))
    with open(OUT + "/dev.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"lock": cmd_lock, "intact": cmd_intact, "dev": cmd_dev}.get(cmd)
    if fn is None:
        print(__doc__)
        sys.exit(0)
    sys.exit(fn() or 0)
