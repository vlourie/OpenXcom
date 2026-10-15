#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""REPORTING_FIX_POST_FREEZE для DERIVE_RECOLOR_ACCEPTANCE_V2.

Специалист 03.10, передал Vitali в чате: «сохранить frozen исходный do_report; amended reporting script под новым
именем/version. Не перезаписывать frozen hash.» Замороженный derive_recolor_acceptance_v2.do_report ставит общий
итог AWAITING_HUMAN, пока хоть один случай ждёт человека, даже если другие случаи уже решены как HARD_FAIL или
ловушка не поймана. Поэтому V2 на 03.10 в замороженной подаче - AWAITING_HUMAN, а по сути FAIL.

Эта поправка касается ТОЛЬКО подачи итога: случаи, пороги, метрики и выходы детекторов берутся как есть из
results.json и answers_human.tsv замороженного модуля, его функции (load_spec, case_verdict, read_human) не
меняются. Правило итога: уже решённый провал (ожидался PASS/HUMAN - вышло не PASS и не AWAITING_HUMAN; ожидался
CAUGHT - не CAUGHT) или H4 ложна - FAIL сразу, ожидание человека итога не откладывает.

    py -3.13 tools/hdart/derive_recolor_acceptance_v2_report_fix.py   -> report_fix_post_freeze.md рядом с report.md
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import derive_recolor_acceptance_v2 as V2          # noqa: E402

FIX_ID = "REPORTING_FIX_POST_FREEZE"
SCOPE = "affects verdict presentation only; does not alter cases, thresholds, metrics or detector outputs"


def overall(res, verdicts):
    want_pass = [k for k, r in res["cases"].items() if r["expect"] in ("PASS", "HUMAN")]
    want_caught = [k for k, r in res["cases"].items() if r["expect"] == "CAUGHT"]
    waiting = [k for k in want_pass if verdicts[k] == "AWAITING_HUMAN"]
    settled_bad = [k for k in want_pass if verdicts[k] not in ("PASS", "AWAITING_HUMAN")] + \
        [k for k in want_caught if verdicts[k] != "CAUGHT"]
    if settled_bad or not res["hypotheses"]["H4"]:
        return "FAIL", waiting, settled_bad
    ok = all(verdicts[k] == "PASS" for k in want_pass) and all(verdicts[k] == "CAUGHT" for k in want_caught)
    return ("AWAITING_HUMAN" if waiting else ("PASS" if ok else "FAIL")), waiting, settled_bad


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(V2.ROOT)
    sp = V2.load_spec()                             # сам сверяет хэш замороженного кода
    res = V2.load_json(os.path.join(V2.OUT, "results.json"))
    if res["spec_sha256"] != sp["sha256"]:
        raise SystemExit("results.json от другого spec")
    hum = V2.read_human()
    verdicts, rows = {}, []
    for k, r in res["cases"].items():
        verdicts[k] = V2.case_verdict(r, hum.get(k))
        rows.append("| %s | %s | %s | %s | %s |" % (k, r["what"], r["expect"], verdicts[k], hum.get(k, "-")))
    total, waiting, bad = overall(res, verdicts)
    with open(os.path.join(V2.ROOT, "tools", "hdart", "derive_recolor_acceptance_v2.py"), "rb") as f:
        frozen = hashlib.sha256(f.read()).hexdigest()
    L = ["# DERIVE_RECOLOR_ACCEPTANCE_V2 - итог (%s)" % FIX_ID, "",
         "Поправка подачи после заморозки: %s." % SCOPE, "",
         "- замороженный модуль: tools/hdart/derive_recolor_acceptance_v2.py, sha256 `%s` "
         "(spec self_sha256 `%s`)" % (frozen, sp.get("self_sha256", "?")),
         "- замороженная подача (report.md) ставит AWAITING_HUMAN, пока кто-то ждёт человека, "
         "даже при уже решённых провалах",
         "- решение (специалист 03.10, передал Vitali в чате): frozen implementation/result = FAIL", "",
         "Итог по поправленной подаче: **%s**" % total, "",
         "- уже решённые провалы: %s" % (", ".join(bad) or "нет"),
         "- ждут человека (диагностика для V3, итог V2 не меняют): %s" % (", ".join(waiting) or "нет"),
         "- H4: %s" % res["hypotheses"]["H4"], "",
         "| случай | что | ожидание | вердикт | человек |", "|---|---|---|---|---|"] + rows
    out = os.path.join(V2.OUT, "report_fix_post_freeze.md")
    with open(out, "w", encoding=V2.ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("итог (%s): %s -> %s" % (FIX_ID, total, out))


if __name__ == "__main__":
    main()
