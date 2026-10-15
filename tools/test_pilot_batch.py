#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pilot_batch.select не мягче заморозки: незакрытый вопрос семейства отсекается ещё при отборе (30.09).

TAVERN:15 прошёл отбор пилота и лист Vitali, а поймала его только заморозка (acceptance_plan.plan_one):
у семейства открыт кандидат «другой бок?» TAVERN:17 (alternate_view_weak). obj_generation такой вопрос
заказом не держит (OPTIONAL), поэтому в generation.tsv блокера нет - отбор по столбцу blockers его не видел.

  * синтетика: open_questions берёт канонический кадр и кандидата, в том числе необязательного вида;
  * живые данные: каждый кандидат select() проходит plan_one без блокеров, кроме опознания (его допуск
    пилота - согласие моделей плюс лист человека); контрольный опыт - с пустым open_questions то же
    сравнение обязано найти расхождение, иначе проверка ничего не проверяет (R-086).

    py -3.13 tools/test_pilot_batch.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
os.chdir(os.path.dirname(HERE))

import acceptance_plan as ap            # noqa: E402
import asset_rev as ar                  # noqa: E402
import obj_gen_spec as ogs              # noqa: E402
import pilot_batch as pb                # noqa: E402

FAIL = []


def check(what, ok):
    print("%s  %s" % ("ok  " if ok else "FAIL", what))
    if not ok:
        FAIL.append(what)


sys.stdout.reconfigure(encoding="utf-8")

fams = [{"family_id": "TAVERN:15", "members": [{"keys": ["TAVERN:15"]}],
         "review": [{"keys": ["TAVERN:17"], "reason": "alternate_view_weak"}]},
        {"family_id": "FRNITURE:10", "members": [{"keys": ["FRNITURE:10"]}], "review": []}]
q = pb.open_questions(fams)
check("канонический кадр с кандидатом на проверке - вопрос", "TAVERN:15" in q)
check("сам кандидат (другой бок?) - вопрос", "TAVERN:17" in q)
check("семейство без проверки - не вопрос", "FRNITURE:10" not in q)


def mismatches():
    """Кандидаты select(), которых заморозка остановила бы блокером, кроме опознания."""
    cands, _drop = pb.select()
    rows, fam, items_by_rank, idrows = ap.load_state()
    gen, fh = ogs.spec(), ar.frame_hashes()
    bad = []
    for c in cands:
        p = ap.plan_one({"asset_id": c["asset_id"], "category": "pilot_simple"}, rows, fam, items_by_rank, gen,
                        idrows, fh)
        rest = [b for b in p["blockers"] if not b.startswith("опознание ")]
        if rest:
            bad.append((c["asset_id"], rest))
    return cands, bad


cands, bad = mismatches()
check("живые данные: кандидатов %d, заморозка не остановила бы ни одного (%s)" % (
    len(cands), "; ".join("%s: %s" % (a, ", ".join(b)) for a, b in bad[:5]) or "-"), cands and not bad)

real = pb.open_questions
pb.open_questions = lambda _fams: set()
try:
    _c, bad0 = mismatches()
finally:
    pb.open_questions = real
check("контроль: без open_questions отбор пропускает вопросы семейства (%d: %s)" % (
    len(bad0), ", ".join(a for a, _b in bad0[:5])), bool(bad0))

print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
