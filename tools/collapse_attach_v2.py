#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0l обрушения зданий: разметка крепления, версия 2 (новый файл, v1 под замком m0j3 не трогается).

v2 = все 107 записей v1 (census/collapse/stage0l/attach_marks.tsv) плюс:
  * предметы почти разобранных зданий-кандидатов пилота, которых в v1 не было (отбор pilot_candidates.tsv:
    амбары BARN/BARN_PP/IDT_SNOWBARN, пещера CAVEBLACK, база GOVBASE URBAN40K, крыша CHEMTOWN MILEXT);
  * BROWNHILL:14 - блок грунта холма LOC_RAYNOR (роль была COLUMN автоматически);
  * METROPIPES:41 - ИСПРАВЛЕНО ПОСЛЕ РЕЗУЛЬТАТА M0j3: в v1 труба крепилась только к соседним трубам (ow+oe),
    и ряд труб без якоря падал целиком; в v2 она ещё лежит на полу или на стене этажом ниже. Это правка по
    результату модели - в отчёте считается отдельно, а не как независимая разметка.

Поле origin: v1 (как в v1), new (новая запись v2), fixed (изменена после результата модели).
В v2 цель SURFACE и ATTACHED может быть смешанной (ow+oe+floor+below): держится, пока цела хотя бы одна -
так их понимает collapse_v7c.targets.

Модель с этой разметкой называется «M0j3, разметка v2»: тот же код collapse_v7c под замком m0j3, но таблица
разметки подменяется (use()). Код под замком не меняется.

    py -3.13 tools\collapse_attach_v2.py check   разметка v2 полна и поля допустимы
    py -3.13 tools\collapse_attach_v2.py lock    замок v2 (до прогона модели с v2)
"""
import hashlib
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_attach as A                       # noqa: E402

ENC = "utf-8-sig"
OUT = A.OUT
MARKS2 = OUT + "/attach_marks_v2.tsv"
LOCK2 = OUT + "/attach_marks_v2.lock.txt"
HEAD2 = A.MARK_HEAD + ["origin"]
TARGETS = {"floor", "below", "up", "w", "n", "e", "s", "ow", "on", "oe", "os"}
LOCKED2 = [MARKS2, "tools/collapse_attach_v2.py", "tools/collapse_v7c.py", "tools/collapse_attach.py", A.MARKS,
           A.GEOM, OUT + "/m0j3.lock.txt"]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def read_v2():
    lines = open(MARKS2, encoding=ENC).read().splitlines()
    head = lines[0].split("\t")
    if head != HEAD2:
        raise SystemExit("%s: шапка %s, ожидалась %s" % (MARKS2, head, HEAD2))
    out = {}
    for n, ln in enumerate(lines[1:], 2):
        if not ln.strip():
            continue
        r = dict(zip(head, ln.split("\t")))
        k = (r["set"].upper(), int(r["idx"]))
        if k in out:
            raise SystemExit("%s:%d: запись %s:%d повторена" % (MARKS2, n, *k))
        r["line"] = n
        out[k] = r
    return out


def cmd_check():
    v1, v2 = A.read_marks(), read_v2()
    bad = []
    for k, r in v2.items():
        if r["confidence"] not in A.CONF:
            bad.append("%s:%d уверенность %s" % (*k, r["confidence"]))
        if not r["reason"].strip():
            bad.append("%s:%d без причины" % k)
        if r["mark"] == "STRUCTURE":
            if r["to"] not in A.KINDS["STRUCTURE"]:
                bad.append("%s:%d роль %s" % (*k, r["to"]))
        elif r["mark"] in ("SURFACE", "ATTACHED"):
            ts = r["to"].split("+")
            if not r["to"] or set(ts) - TARGETS:
                bad.append("%s:%d цели %s" % (*k, r["to"]))
        elif r["mark"] == "UNKNOWN":
            if r["to"]:
                bad.append("%s:%d UNKNOWN с целью" % k)
        else:
            bad.append("%s:%d вид %s" % (*k, r["mark"]))
        o = r["origin"]
        if o == "v1":
            a = v1.get(k)
            if a is None or any(a[f] != r[f] for f in A.MARK_HEAD):
                bad.append("%s:%d origin v1, но не совпадает с v1" % k)
        elif o == "fixed":
            if k not in v1 or all(v1[k][f] == r[f] for f in A.MARK_HEAD):
                bad.append("%s:%d origin fixed, но записи нет в v1 или она не изменена" % k)
        elif o == "new":
            if k in v1:
                bad.append("%s:%d origin new, но запись есть в v1" % k)
        else:
            bad.append("%s:%d origin %s" % (*k, o))
    for k in v1:
        if k not in v2:
            bad.append("%s:%d из v1 нет в v2" % k)
    for b in bad:
        print("!!", b)
    c = {}
    for r in v2.values():
        c[r["origin"]] = c.get(r["origin"], 0) + 1
    print("записей v2 %d (%s), ошибок %d" % (len(v2), ", ".join("%s %d" % kv for kv in sorted(c.items())), len(bad)))
    return not bad


def cmd_lock():
    if not cmd_check():
        raise SystemExit("разметка v2 с ошибками - замок не ставится")
    with open(LOCK2, "w", encoding=ENC) as f:
        f.write("# замок разметки крепления v2 (этап 0l), поставлен до прогона «M0j3, разметка v2»\n")
        f.write("time\t%s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        for p in LOCKED2:
            f.write("%s\t%s\n" % (p, sha(p)))
    print("замок ->", LOCK2)


def check_lock():
    if not os.path.exists(LOCK2):
        raise SystemExit("нет замка разметки v2 %s" % LOCK2)
    for ln in open(LOCK2, encoding=ENC).read().splitlines():
        if ln.startswith("#") or ln.startswith("time"):
            continue
        p, h = ln.split("\t")
        if sha(p) != h:
            raise SystemExit("замок разметки v2 нарушен: %s" % p)


def use():
    """Подменить разметку M0j3 на v2 (collapse_v7c.marks() отдаёт _MARKS, если она уже задана)."""
    import collapse_v7c as C
    C.check_lock()
    check_lock()
    m = {}
    for k, r in read_v2().items():
        m[k] = {f: r[f] for f in A.MARK_HEAD}
        m[k]["line"] = r["line"]
    C._MARKS = m
    return C


def run_m0j3(name):
    """Проверки collapse_v7c (intact, dev) с разметкой v2; выход - в OUT/v2, файлы v1 не трогаются."""
    C = use()
    C.OUT = OUT + "/v2"
    return {"intact": C.cmd_intact, "dev": C.cmd_dev}[name]()


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd in ("intact", "dev"):
        run_m0j3(cmd)
    else:
        {"check": cmd_check, "lock": cmd_lock}[cmd]()
