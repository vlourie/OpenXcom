#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALIGNED_RECOLOR_V2 - AR1 с порогом границ 0.70 (специалист 02.10, передал Vitali в чате). CPU, чтение.

Порог границ обоснован слепой проверкой ALIGNED_RECOLOR_BOUNDARY_VALIDATION_V1 (ar_boundary_validation.py):
правило выбора подполосы записано до сканирования, подполоса 0.70-0.80 - существование связи 24/25 = 0.960 на
25 закрытых независимых парах, ниже 0.70 данных мало. Поэтому:

    границ >= 0.70 - проверенный диапазон V2;
    границ <  0.70 - НЕ ПРОВЕРЕНО: AR2 там не срабатывает, ниже порог не двигается ни ради какого кадра.

Всё остальное - как у AR1 без изменений (aligned_recolor_v1: сдвиг, силуэт, функция цвета, цвета основы,
остаток, общий силуэт, отбор кандидатов, отражение). Отличия AR2 от AR1, все из решения специалиста:

  - порог границ AR_BORDER 0.70 вместо 0.80;
  - существование связи всегда STRONG (проверка подтвердила существование, а не только строгую перекраску наборов);
  - подтип открыт: тип ALIGNED_RECOLOR, TYPE_OPEN, автоматического действия перекраски нет (проверка не
    подтвердила подтип: AR1 уже поймал анимацию как перекраску - связь настоящая, подтип нет).

Сам модуль только находит доводы; как довод AR2 входит в маршрут (TYPE_OPEN, «AR2: подтип на ревью») - в
v5_ar2_recount.py. VERIFIED ставит только человек.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aligned_recolor_v1 as ar1                  # noqa: E402
import identity_routing as ir                     # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402

TYPE = ar1.TYPE                  # ALIGNED_RECOLOR - группа derived, подтип на ревью
DETECTOR = "AR2"
AR_BORDER = 0.70                 # нижний край подполосы 0.70-0.80, прошедшей слепую проверку; ниже - не проверено
VALIDATION_PROFILE = "ALIGNED_RECOLOR_BOUNDARY_VALIDATION_V1"
PARAMS = dict(ar1.PARAMS, AR_BORDER=AR_BORDER, detector=DETECTOR,
              level="STRONG всегда (существование подтверждено слепой проверкой полосы)",
              type_level="TYPE_OPEN (подтип ALIGNED_RECOLOR / RECOLOR - кандидат, автоматического действия нет)",
              validated_range="границ >= 0.70", not_validated="границ < 0.70",
              unchanged_from_ar1="AR_SHIFT, AR_IOU, AR_FUNC, AR_RESID, AR_GENERIC, MIN_COLORS, PREFILTER, "
                                 "отражение, отбор кандидатов, исключение точных копий и зеркал")
scores = ar1.scores
candidates = ar1.candidates      # отбор по силуэту; границы в нём не участвуют


def passes(sc, gen_a, gen_b):
    """Условия AR2: все условия AR1, кроме границ, плюс границы >= AR_BORDER. -> (годно, [почему нет])."""
    _ok, no = ar1.passes(sc, gen_a, gen_b)
    no = [w for w in no if not w.startswith("границ")]
    if sc["topology"] < AR_BORDER:
        no.append("границ %.2f < %.2f" % (sc["topology"], AR_BORDER))
    return not no, no


def pair(ctx, si, a, b, B=None):
    """Довод AR2 на паре (a, b) или []. B - подмена кадра b (перемешанный контроль)."""
    a, b = a.upper(), b.upper()
    if a == b or b in ctx.ix.exact(a) or b in ctx.ix.mirror(a):
        return []
    A, B0 = ctx.rgba(a), ctx.rgba(b)
    if A is None or B0 is None or A.shape != B0.shape:
        return []
    sc = scores(A, B0 if B is None else B)
    ok, _no = passes(sc, si.generic(a), si.generic(b))
    if not ok:
        return []
    (sa, _fa), (sb, _fb) = v2.split(a), v2.split(b)
    st = si.pair_stats(sa, sb) if sa != sb else None
    e = v2.edge(TYPE, a, b, "STRONG", DETECTOR, "AR2",
                "%s, сдвиг %+d,%+d: силуэт %.3f (без сдвига %.3f), границ %.2f, функция %.3f/%.3f, остаток %.3f, "
                "цветов основы %d%s; подтип открыт" % (
                    "отражение" if sc["flip"] else "прямо", sc["shift"][0], sc["shift"][1], sc["silhouette"],
                    sc["unshifted"], sc["topology"], sc["f_ab"], sc["f_ba"], sc["residual"], sc["base_colors"],
                    "" if st is None else "; наборы: общих %d, строгая перекраска %.2f" % (
                        st["common"], st["strict"] or 0)))
    e["scores"] = dict(sc, set=st)
    return [e]


def discover(ctx, si, a):
    out = []
    for b in candidates(ctx, a):
        out += pair(ctx, si, a, b)
    return out


def check_validation():
    """Порог взят из слепой проверки: её отчёт обязан давать ровно AR_BORDER. -> сведения о проверке."""
    import ar_boundary_validation as bv
    rep = bv.p("report.json")
    if not os.path.exists(rep):
        raise SystemExit("нет отчёта слепой проверки полосы: %s" % rep)
    bv.check_freeze()
    r = ir.load_json(rep)
    if r.get("threshold") != AR_BORDER:
        raise SystemExit("порог слепой проверки %s, а AR2 использует %.2f" % (r.get("threshold"), AR_BORDER))
    return {"profile": r["profile"], "freeze_sha256": r["freeze_sha256"], "truth_sha256": r["truth_sha256"],
            "report_sha256": v2.file_sha(rep), "threshold": r["threshold"], "verdict": r["verdict"],
            "steps": [{k: x.get(k) for k in ("step", "lo", "hi", "value", "n", "ok", "open", "status", "not_tested")}
                      for x in r["steps"]]}


assert v4.R4D_BORDER == ar1.AR_BORDER == 0.80, "AR1 изменился - AR2 описан как AR1 с другим порогом границ"
