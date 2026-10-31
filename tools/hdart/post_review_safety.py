#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""POST_REVIEW_SAFETY - инвариант жизненного цикла REVIEW (специалист 02.10, передал Vitali в чате; R-181).

CANDIDATE значит «не уверен - остановись и отправь на REVIEW». После ревью маршрут обязан продолжиться с учётом
решения человека: отклонённого кандидата больше нет. Поэтому безопасность считается дважды:

  PRE_REVIEW_DANGEROUS  - опасные при всех доводах, как есть;
  POST_REVIEW_DANGEROUS - опасные после того, как все доводы уровня CANDIDATE на парах, которые независимый
                          закрытый эталон подтвердил как NONE, удалены, а решение маршрута пересчитано.

Кандидаты на парах с OPEN эталоном остаются блокирующими: неизвестно, ложны ли они. Ворота заморозки - оба нуля.
STRONG на паре с закрытым NONE не удаляется (это ложное автоматическое действие, его ловят ворота точности), но
считается отдельной строкой.

Модуль только пересчитывает: правила детекторов не трогает, VERIFIED не ставит.
"""
import copy
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import relation_discovery_v3 as v3                # noqa: E402
import relation_taxonomy as tx                    # noqa: E402

PROFILE = "POST_REVIEW_SAFETY_V1"


def closed_none(*sources):
    """sources - итерируемые (a, b, существование) из закрытых независимых эталонов -> {ключ пары: откуда}."""
    out = {}
    for name, rows in sources:
        for a, b, ex in rows:
            if ex == "NONE":
                out.setdefault(tx.pk(a, b), []).append(name)
    return out


def after_review(C, none_pairs):
    """Копия доводов без CANDIDATE на парах closed NONE. -> (копия, удалённые, STRONG на closed NONE)."""
    C2 = copy.copy(C)
    C2.claims, C2.by_asset = {}, defaultdict(set)
    dropped, strong = [], []
    for k, c in C.claims.items():
        src = none_pairs.get(tx.pk(*c["pair"]))
        if src and c["existence"] != v3.STRONG:
            dropped.append({"pair": c["pair"], "group": c["group"], "existence": c["existence"], "truth": src,
                            "detectors": sorted({e["detector"] + " " + e.get("rule", "") for e in c["support"]})})
            continue
        if src:
            strong.append({"pair": c["pair"], "group": c["group"], "truth": src})
        C2.claims[k] = c
        for x in c["pair"]:
            C2.by_asset[x].add(k)
    return C2, dropped, strong


def pre_post(evaluate, C, none_pairs):
    """evaluate(C) -> отчёт с полем dangerous ({кадр: причины}). -> сводка PRE/POST и отчёт после ревью."""
    pre = evaluate(C)
    C2, dropped, strong = after_review(C, none_pairs)
    post = evaluate(C2)
    newly = sorted(set(post["dangerous"]) - set(pre["dangerous"]))
    return {"profile": PROFILE,
            "PRE_REVIEW_DANGEROUS": len(pre["dangerous"]), "POST_REVIEW_DANGEROUS": len(post["dangerous"]),
            "pre_dangerous": sorted(pre["dangerous"]), "post_dangerous": sorted(post["dangerous"]),
            "unmasked": [{"asset": a, "masked_by": [d for d in dropped if a in d["pair"]]} for a in newly],
            "dropped_candidates": dropped, "strong_on_closed_none": strong}, post
