#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ROUTING_RULES_V4_R1 holdout: таблица точности родства correct / wrong / unresolved / знаменатель по срезам.

Только вид: читает diag2.json (routing_holdout_diag2.py diag) и раскладывает уже посчитанные числа, ничего не
пересчитывает по-новому и сверяет свою раскладку с diag2 (correct и знаменатель обязаны совпасть). Методику не
меняет - она заморожена в SCORING_AMENDMENT_2.json. Просьба специалиста 01.10: рядом с процентом видеть, не держится
ли он на маленьком знаменателе.

  correct     - тип связи совпал, направление / основа известны или не нужны (RECOLOR_OF);
  wrong       - тип связи не совпал (в том числе против DERIVED_FROM / STATE_VARIANT_OF без направления);
  unresolved  - тип совпал, но эталон не знает направления / основы (ACTIONABLE_RELATION_TRUTH);
  ref_open    - эталон пару не закрыл (OPEN или строки нет);
  denominator = correct + wrong.

    py -3.13 tools/hdart/routing_holdout_table.py      # -> relation_table.md рядом с diag2.md
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir          # noqa: E402
import routing_holdout as rh           # noqa: E402

KNOWN_DIR = ("asset_derived", "relative_derived")
NEEDS_DIR = ("DERIVED_FROM", "STATE_VARIANT_OF")
SLICES = [("relation_precision_gate", "ворота: исходный эталон, strict_blind"),
          ("relation_precision_all", "исходный эталон, с XBASE-парой"),
          ("strong_relation_precision_primary", "STRONG, покрытые исходным эталоном"),
          ("strong_relation_precision_supplemental", "STRONG, слепое дополнение (диагностика)"),
          ("candidate_relation_precision_primary", "CANDIDATE, исходный эталон (диагностика)")]


def row(x, unresolved):
    wrong = x["closed"] - x["ok"]
    return {"correct": x["ok"], "wrong": wrong, "unresolved": unresolved,
            "ref_open": x["claims"] - x["closed"] - unresolved, "denominator": x["closed"], "claims": x["claims"],
            "precision": x["relation_precision"]}


def table(res, exclude_pairs):
    rel, sup = res["relations"], res.get("supplement")
    ex = {(a.upper(), b.upper()) for a, b in exclude_pairs}
    ex |= {(b, a) for a, b in ex}
    unr = rel["unresolved_by_rule"]
    n_unr = {"relation_precision_gate": sum((u[0].upper(), u[1].upper()) not in ex for u in unr),
             "relation_precision_all": len(unr),
             "strong_relation_precision_primary": sum(u[2] == "STRONG" for u in unr),
             "candidate_relation_precision_primary": sum(u[2] == "CANDIDATE" for u in unr)}
    out = {}
    for k, _t in SLICES:
        if k == "strong_relation_precision_supplemental":
            if not sup:
                out[k] = None
                continue
            x = sup[k]
            n = sum(r[2] == "STRONG" and r[5] == "open" and r[3] in NEEDS_DIR and r[4] not in KNOWN_DIR
                    for r in sup["rows"])
        else:
            x, n = rel[k], n_unr[k]
        out[k] = row(x, n)
        if out[k]["ref_open"] < 0:
            raise SystemExit("раскладка не сходится с diag2 в срезе %s" % k)
    return out


def write_md(out, res, t):
    L = ["# Точность родства по срезам (из diag2.json %s, поправка %s)" % (res["created"], res["amendment2_sha256"][:12]),
         "", "| срез | что это | correct | wrong | unresolved | ref_open | знаменатель | точность |",
         "|---|---|---|---|---|---|---|---|"]
    for k, what in SLICES:
        r = t[k]
        if r is None:
            L.append("| %s | %s | - | - | - | - | - | дополнения нет |" % (k, what))
        else:
            L.append("| %s | %s | %d | %d | %d | %d | %d | %s |" % (k, what, r["correct"], r["wrong"], r["unresolved"],
                                                                 r["ref_open"], r["denominator"], r["precision"]))
    L += ["", "знаменатель = correct + wrong; unresolved - тип совпал, направление / основа неизвестны; ref_open - "
              "эталон пару не закрыл. Ворота: >= 0.95 при знаменателе >= 5 в срезе relation_precision_gate."]
    with open(os.path.join(out, "relation_table.md"), "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=rh.OUT)
    a = ap.parse_args()
    os.chdir(ir.ROOT)
    res = ir.load_json(os.path.join(a.out, "diag2.json"))
    a1 = ir.load_json(os.path.join(a.out, "GATES_AMENDMENT.json"))
    write_md(a.out, res, table(res, a1["strict_blind_exclude_pairs"]))


if __name__ == "__main__":
    main()
