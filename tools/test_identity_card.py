#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""identity_card.report: две независимые проверки IDENTITY_GATE_V2 (специалист 01.10).

CONTEXT_GATE - карточки хватило (старая ошибка раскрыта, кусок не назван предметом, нет UNSURE из-за контекста);
IDENTITY_TRUTH_GATE - независимая истина установлена. identity_ok open - истина не установлена, это не «неверно».

    py -3.13 tools/test_identity_card.py
Без карт и видеокарты: синтетический cards.json и TSV во временной папке.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import identity_card as ic          # noqa: E402

ENC = "utf-8-sig"
HEAD = "asset_id\tfinal_identity\tstatus\tmissing_context\tnote"
RHEAD = "asset_id\tref_status\tidentity_ok\told_rejected"


def run(d, answers, reference=None, complete=True, rhead=RHEAD):
    cards = [{"asset": a, "prompt": "old", "card_complete": complete} for a in ("A:1", "B:2", "C:3")]
    with open(os.path.join(d, "cards.json"), "w", encoding=ENC) as f:
        json.dump({"title": "t", "cards": cards}, f)
    ap = os.path.join(d, "ans.tsv")
    with open(ap, "w", encoding=ENC) as f:
        f.write("\n".join([HEAD] + answers) + "\n")
    rp = ""
    if reference:
        rp = os.path.join(d, "ref.tsv")
        with open(rp, "w", encoding=ENC) as f:
            f.write("\n".join([rhead] + reference) + "\n")
    ic.report(d, ap, rp)
    with open(os.path.join(d, "report.json"), encoding=ENC) as f:
        r = json.load(f)
    return r, r["gates"]["CONTEXT_GATE"]["passed"], r["gates"]["IDENTITY_TRUTH_GATE"]["passed"]


GOOD = ["A:1\tstack of three white boxes with grey lids\tIDENTITY_VISUALLY_VERIFIED\t\t",
        "B:2\tglass shelf\tIDENTITY_VISUALLY_VERIFIED\t\t",
        "C:3\tpart of a multi-tile dissection table\tPART_FRAGMENT_CONFIRMED\t\t"]
REF = ["A:1\tIDENTITY_VISUALLY_VERIFIED\tyes\tyes", "B:2\tIDENTITY_VISUALLY_VERIFIED\tyes\tyes",
       "C:3\tPART_FRAGMENT_CONFIRMED\tyes\tyes"]
# как в регрессии 01.10: кусок закрыт, у двух предметов истина не установлена
REF_OPEN = ["A:1\tIDENTITY_VISUALLY_VERIFIED\topen\tyes", "B:2\tIDENTITY_VISUALLY_VERIFIED\topen\tyes",
            "C:3\tPART_FRAGMENT_CONFIRMED\tyes\tyes"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fails = []

    def check(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory() as d:
        r, c, t = run(d, GOOD)
        check("без сверки обе проверки не решены", c is None and t is None)
        r, c, t = run(d, GOOD, REF)
        check("всё закрыто и верно - обе PASS", c is True and t is True)
        check("identity_correct 2/2 closed, part_fragment_correct 1/1",
              r["metrics"]["identity_correct"] == "2/2 closed, 0 open" and r["metrics"]["part_fragment_correct"] == "1/1")
        r, c, t = run(d, GOOD, REF_OPEN)
        check("истина open - CONTEXT PASS, TRUTH не решена (1 закрыто, 2 открыто), не FAIL",
              c is True and t is None and r["gates"]["IDENTITY_TRUTH_GATE"]["open"] == 2)
        check("open не считается неверным", r["metrics"]["identity_correct"] == "0/0 closed, 2 open")
        # кусок назван самостоятельным предметом (R-153): провал контекста
        ans = GOOD[:2] + ["C:3\tdead cow on a white table\tIDENTITY_VISUALLY_VERIFIED\t\t"]
        r, c, t = run(d, ans, REF)
        check("кусок назван предметом - false_standalone 1, CONTEXT FAIL",
              r["metrics"]["false_standalone"] == 1 and c is False)
        # старое ложное описание осталось принятым
        r, c, t = run(d, GOOD, REF[:2] + ["C:3\tPART_FRAGMENT_CONFIRMED\tyes\tno"])
        check("старое описание не отвергнуто - CONTEXT FAIL", c is False)
        # истина закрыта неверно
        r, c, t = run(d, GOOD, ["A:1\tIDENTITY_VISUALLY_VERIFIED\tno\tyes"] + REF[1:])
        check("неверное название - TRUTH FAIL, CONTEXT PASS", t is False and c is True)
        # UNSURE с отметкой контекста - провал контекста даже без сверки
        r, c, t = run(d, GOOD[:2] + ["C:3\t\tUNSURE\tlarger map crop\t"])
        check("UNSURE из-за контекста - CONTEXT FAIL без сверки", c is False
              and r["metrics"]["unsure_missing_context"] == 1)
        r, c, t = run(d, [GOOD[0].replace("IDENTITY_VISUALLY_VERIFIED", "SURE")] + GOOD[1:], REF)
        check("статус SURE отвергнут", len(r["invalid"]) == 1 and c is False)
        r, c, t = run(d, GOOD, ["A:1\tIDENTITY_VISUALLY_VERIFIED\tmaybe\tyes"] + REF[1:])
        check("identity_ok вне yes/no/open отвергнут", len(r["invalid"]) == 1 and c is False)
        r, c, t = run(d, GOOD, REF, complete=False)
        check("карточка без рентгена - CONTEXT FAIL", c is False)
        # структура закрыта, смысл открыт (C_INT:27 - модуль колонны C_INT_COLUMN, 01.10): ворота истины по смыслу
        sref = [x + s for x, s in zip(REF_OPEN, ("\tyes", "\t", "\t"))]
        r, c, t = run(d, GOOD, sref, rhead=RHEAD + "\tstructural_ok")
        check("структура закрыта при открытом смысле - TRUTH не решена, structural 1/1 closed",
              c is True and t is None and r["metrics"]["structural"] == "1/1 closed, 0 open"
              and r["rows"][0]["structure"] is True and r["rows"][1]["structure"] is None)
        r, c, t = run(d, GOOD, [REF_OPEN[0] + "\tperhaps"] + [x + "\t" for x in REF_OPEN[1:]],
                      rhead=RHEAD + "\tstructural_ok")
        check("structural_ok вне yes/no/open отвергнут", len(r["invalid"]) == 1 and c is False)
        # класс верен, название нет (MADDECOR_WASTE:47 01.10: «ice vending machine» против эталона «water
        # cooler»); excluded - назначение не нужно для маршрутизации (C_INT:27), в точность названий не входит
        sh = RHEAD + "\tsemantic_ok\ttruth_identity\trelation"
        sref = [REF[0] + "\texcluded\tSTACK part\t", REF[1] + "\tno\twater cooler\tDAMAGED_VARIANT_OF M:50",
                REF[2] + "\tyes\tpart of table\t"]
        r, c, t = run(d, GOOD, sref, rhead=sh)
        m = r["metrics"]
        check("название отдельно от класса: класс 3/3, название 1/2, excluded 1; ворота не тронуты",
              c is True and t is True and m["classification_correct"] == "3/3"
              and m["semantic_correct"] == "1/2, excluded 1, open 0" and m["semantic_accuracy"] == 0.5
              and r["rows"][1]["semantic"] is False and r["rows"][1]["relation"] == "DAMAGED_VARIANT_OF M:50")
        r, c, t = run(d, GOOD, [REF[0] + "\tmaybe\t\t"] + [x + "\t\t\t" for x in REF[1:]], rhead=sh)
        check("semantic_ok вне yes/no/open/excluded отвергнут", len(r["invalid"]) == 1 and c is False)
        r, c, t = run(d, [GOOD[0].replace("IDENTITY_VISUALLY_VERIFIED", "PART_FRAGMENT_CONFIRMED")] + GOOD[1:], REF)
        check("неверный класс снижает точность класса", r["metrics"]["classification_correct"] == "2/3")
    print("итог:", "все проверки прошли" if not fails else "провалено %d" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
