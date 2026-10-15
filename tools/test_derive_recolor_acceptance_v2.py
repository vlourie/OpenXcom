#!/usr/bin/env python3
"""Проверка ворот DERIVE_RECOLOR_ACCEPTANCE_V2 (tools/hdart/derive_recolor_acceptance_v2.py) без вызова вывода:
синтетическая правда проходит все жёсткие ворота, контроли ловятся (основа вместо вывода - wrong_palette_mapping,
пятна - unintended_local_artifacts, член отражённой основы без отражения - source_target_alignment_error).

    py -3.13 tools/test_derive_recolor_acceptance_v2.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import derive_recolor_acceptance_v2 as A          # noqa: E402


def check(name, cond, info=""):
    print("%s %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else "  -> %s" % (info,)))
    return cond


def main():
    os.chdir(A.ROOT)
    ok = True
    for c in A.SYNTH:
        base, member, hd, truth = A.synth_inputs(c)
        tr = "mirror" if c.get("mirror_member") else "recolor"
        H, B = A.orient(hd, tr), A.orient(base, tr)
        g, info = A.gates(truth, H, B, member)
        ok &= check("%s правда проходит все ворота" % c["id"], not any(g.values()), g)
        cv = A.coverage(info, H, B, member, truth)
        ok &= check("%s ворота цвета и пятен покрывают случай, контроли пойманы" % c["id"], cv["covered"], cv)
        if c.get("mirror_member"):
            g2, _ = A.gates(truth, hd, base, member)
            ok &= check("%s без отражения - source_target_alignment_error" % c["id"],
                        g2["source_target_alignment_error"] > 0, g2)
    print("ВСЁ ВЕРНО" if ok else "ЕСТЬ ОШИБКИ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
