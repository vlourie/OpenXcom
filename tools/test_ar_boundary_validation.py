#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверки ALIGNED_RECOLOR_BOUNDARY_VALIDATION_V1 без данных: слой пары по очкам AR1 и правило решения."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import ar_boundary_validation as bv     # noqa: E402

FAIL = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAIL.append(name)


def sc(border, sil=0.98, fmax=0.95, resid=0.05, colors=10, shift=(0, 1)):
    return {"shift": list(shift), "silhouette": sil, "fmax": fmax, "base_colors": colors, "topology": border,
            "residual": resid}


def rows(st, yes, no, opn=0):
    out = []
    for ex, n in (("yes", yes), ("no", no), ("OPEN", opn)):
        out += [{"stratum": st, "exist": ex, "existence": {"yes": "RELATED", "no": "NONE"}.get(ex, "OPEN"),
                 "derived": ex, "judge1": [], "judge2": []} for _ in range(n)]
    return out


def main():
    # слой: только границы по подполосам; ещё одна неудача - трудный отрицательный; силуэт ниже - похожий
    check("trigger", bv.stratum(sc(0.85), 0, 0) == "ANCHOR_TRIGGER")
    check("band 70", bv.stratum(sc(0.74), 0, 0) == "BAND_70")
    check("band 60", bv.stratum(sc(0.65), 0, 0) == "BAND_60")
    check("band 50", bv.stratum(sc(0.50), 0, 0) == "BAND_50")
    check("below band", bv.stratum(sc(0.49), 0, 0) is None)
    check("hard neg func", bv.stratum(sc(0.70, fmax=0.6), 0, 0) == "BAND_HARD_NEG")
    check("hard neg resid", bv.stratum(sc(0.70, resid=0.3), 0, 0) == "BAND_HARD_NEG")
    check("lookalike", bv.stratum(sc(0.70, sil=0.90), 0, 0) == "BAND_LOOKALIKE")
    check("zero shift", bv.stratum(sc(0.70, shift=(0, 0)), 0, 0) is None)
    check("generic", bv.stratum(sc(0.70), 99, 0) is None)

    # правило: сверху вниз до первой непрошедшей; порог - нижний край последней прошедшей
    r = rows("BAND_70", 30, 1) + rows("BAND_60", 25, 0, 5) + rows("BAND_50", 15, 10)
    steps, thr = bv.decide(r)
    check("threshold 0.60", thr == 0.60)
    check("third tested and failed", [x["status"] for x in steps] == ["PASS", "PASS", "FAIL"])
    # верхняя не прошла -> порога нет, нижние только для сведения, даже если они «хорошие»
    r = rows("BAND_70", 18, 2) + rows("BAND_60", 40, 0) + rows("BAND_50", 40, 0)
    steps, thr = bv.decide(r)
    check("top fails -> diagnostic", thr is None and steps[0]["status"] == "FAIL")
    check("lower not tested", all(x.get("not_tested") for x in steps[1:]))
    # мало закрытых (OPEN не считаются) - не PASS
    steps, thr = bv.decide(rows("BAND_70", 19, 0, 30))
    check("insufficient", thr is None and steps[0]["status"] == "INSUFFICIENT_SAMPLE")
    # ровно 0.95 на 20 закрытых проходит
    check("gate inclusive", bv.decide(rows("BAND_70", 19, 1) + rows("BAND_60", 0, 0))[1] == 0.70)

    check("wilson", abs(bv.wilson_low(19, 20) - 0.764) < 0.01)
    check("rule in spec", bv.spec()["decision_rule"]["gate"] == 0.95 and
          [s for s, *_ in bv.STEPS] == ["BAND_70", "BAND_60", "BAND_50"])

    print("\n%s" % ("всё прошло" if not FAIL else "провалено: %d" % len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
