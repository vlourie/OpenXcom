#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ROUTING_RULES_V4_R1 holdout: вторая поправка - правило ACTIONABLE_RELATION_TRUTH и слепое дополнение эталона
для пяти утверждений детектора, не попавших в пакет эталона. Итог holdout - diag2.md.

Решение: специалист 01.10, передал Vitali в чате, до ответов Vitali и после заморозки эталона.
Замороженные routing_holdout.py, эталон (reference.lock.json), GATES_AMENDMENT.json и routing_holdout_diag.py
не меняются; эта поправка пишется отдельным файлом SCORING_AMENDMENT_2.json вместе с sha этого скрипта.

ACTIONABLE_RELATION_TRUTH (только для точности родства; маршрут и ось A не затрагивает):
  RECOLOR_OF        - связь симметрична, засчитывается при любом направлении эталона;
  STATE_VARIANT_OF  - нужна известная каноническая основа (direction asset_derived / relative_derived);
  DERIVED_FROM      - нужно известное направление parent -> derived (то же);
  DERIVED_FROM / STATE_VARIANT_OF без известного направления - unresolved: засчитанное утверждение уходит из
  числителя и знаменателя; утверждение другого вида связи против такой строки остаётся ошибкой.
  Общая основа с другой деталью сама по себе не DERIVED_FROM; эталон при этом не правится.

Срезы точности родства:
  relation_precision_gate  - исходный эталон, strict_blind (без XBASE1:99 ~ XB1BR:99), по правилу выше. Ворота.
  relation_precision_all   - исходный эталон, с XBASE-парой, по правилу выше.
  strong_relation_precision_primary      - STRONG, что покрыл исходный эталон.
  strong_relation_precision_supplemental - STRONG по слепому дополнению пяти пар (диагностика, ворота не меняет).
  те же числа без правила (raw) - для прозрачности.

    py -3.13 tools/hdart/routing_holdout_diag2.py amend2       # один раз, до answers_vitali.tsv
    py -3.13 tools/hdart/routing_holdout_diag2.py supplement   # пакет дополнения + шаблон TSV
    py -3.13 tools/hdart/routing_holdout_diag2.py locksupp     # до answers_vitali.tsv
    py -3.13 tools/hdart/routing_holdout_diag2.py diag         # после routing_holdout.py report
    py -3.13 tools/hdart/routing_holdout_diag2.py check
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir          # noqa: E402
import routing_holdout as rh           # noqa: E402
import routing_holdout_diag as rd      # noqa: E402

OUT = rh.OUT
ME = os.path.relpath(os.path.abspath(__file__), ir.ROOT).replace(os.sep, "/")
AMEND = "SCORING_AMENDMENT_2.json"
SUPP = "reference_relation_supplement.tsv"
SUPP_LOCK = "reference_relation_supplement.lock.json"
SUPP_PACK = "reference_supplement_pack"
KNOWN_DIR = ("asset_derived", "relative_derived")
NEEDS_DIR = ("DERIVED_FROM", "STATE_VARIANT_OF")
ACTIONABLE = {
    "RECOLOR_OF": "допустима симметричная связь - засчитывается при любом направлении",
    "STATE_VARIANT_OF": "требуется известная каноническая основа (direction asset_derived / relative_derived)",
    "DERIVED_FROM": "требуется известное направление parent -> derived (direction asset_derived / relative_derived)",
    "unknown-direction": "DERIVED_FROM / STATE_VARIANT_OF без известного направления - unresolved для точности родства "
                         "(утверждение, которое засчиталось бы, уходит из числителя и знаменателя; утверждение другого "
                         "вида связи против такой строки остаётся ошибкой)",
    "shared_base": "общая основа с другой деталью сама по себе не доказательство DERIVED_FROM",
}


def p(out, name):
    return os.path.join(out, name)


def missing_pairs(out):
    """Утверждения детектора по 40, для которых в замороженном эталоне пар нет строки."""
    h = rh.load_holdout(out)
    _ref, refp, _lk = rh.load_reference(out)
    have = {(r["asset_id"].upper(), r["relative"].upper()) for r in refp}
    rels = rh.load_relations(out)
    return [[k, c["relative"]] for k in (x["asset_id"] for x in h["items"]) for c in rels.get(k, [])
            if (k.upper(), c["relative"].upper()) not in have]


# ---------------------------------------------------------------- amend2

def amend2(out=OUT):
    if os.path.exists(p(out, AMEND)):
        raise SystemExit("вторая поправка уже записана: %s" % p(out, AMEND))
    if os.path.exists(p(out, "answers_vitali.tsv")):
        raise SystemExit("ответы Vitali уже есть - поправка после ответов не пишется")
    a1 = rd.load_amend(out)
    _ref, _refp, lk = rh.load_reference(out)
    body = {"amends": "GATES_AMENDMENT.json: точность родства - по ACTIONABLE_RELATION_TRUTH",
            "gates_amendment_sha256": a1["sha256"], "freeze_sha256": a1["freeze_sha256"],
            "holdout_sha256": a1["holdout_sha256"], "reference_sha256": lk["reference_sha256"],
            "reference_pairs_sha256": lk["reference_pairs_sha256"],
            "actionable_relation_truth": ACTIONABLE, "known_direction": list(KNOWN_DIR),
            "needs_direction": list(NEEDS_DIR),
            "relation_precision_gate": "исходный замороженный эталон, strict_blind (без %s), по ACTIONABLE_RELATION_TRUTH"
                                       % " / ".join(" ~ ".join(x) for x in a1["strict_blind_exclude_pairs"]),
            "supplement_pairs": missing_pairs(out),
            "supplement_rule": "слепое дополнение тем же независимым агентом, без уверенности детектора, правил и "
                               "ответов; только strong_relation_precision_supplemental, PASS/FAIL ворот не меняет",
            "diag2_code": ME, "diag2_code_sha256": rh.file_sha(ME),
            "answers_present_at_amend": os.path.exists(p(out, "answers_vitali.tsv"))}
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body),
                decided="специалист 01.10, передал Vitali в чате: unknown-direction DERIVED_FROM -> unresolved; "
                        "пять пропущенных пар - отдельным слепым дополнением, только диагностика STRONG",
                rule="после ответов holdout никаких новых поправок по relation truth")
    ir.dump_json(p(out, AMEND), data)
    print("вторая поправка записана (sha256 %s): пар в дополнении %d" % (data["sha256"][:12],
                                                                       len(body["supplement_pairs"])))
    return data


def load_amend2(out=OUT):
    a = ir.load_json(p(out, AMEND))
    body = {k: a[k] for k in a if k not in ("created", "sha256", "decided", "rule")}
    if ir.sha(body) != a["sha256"]:
        raise SystemExit("%s изменён после записи" % AMEND)
    if a["answers_present_at_amend"]:
        raise SystemExit("вторая поправка записана при ответах - недействительна")
    if not os.path.exists(a["diag2_code"]) or rh.file_sha(a["diag2_code"]) != a["diag2_code_sha256"]:
        raise SystemExit("код diag2 изменён после поправки: %s" % a["diag2_code"])
    return a


# ---------------------------------------------------------------- дополнение эталона

def supplement(out=OUT):
    a = load_amend2(out)
    if os.path.exists(p(out, SUPP_LOCK)):
        raise SystemExit("дополнение уже заморожено")
    d, h = rh.load_freeze(out), rh.load_holdout(out)
    _c, ctx = rh.candidates(out, h, d["inputs"], rh.load_relations(out))
    pack = p(out, SUPP_PACK)
    os.makedirs(p(pack, "img"), exist_ok=True)
    n = {x["asset_id"]: i + 1 for i, x in enumerate(h["items"])}
    items = []
    for x, b in a["supplement_pairs"]:
        fn = "pair_%02d_%s__%s.png" % (n[x], x.replace(":", "-"), b.replace(":", "-"))
        ok = rh.pair_sheet(ctx, x, b, p(p(pack, "img"), fn))
        items.append({"asset_id": x, "relative": b, "pair_sheet": "img/" + fn if ok else ""})
    ir.dump_json(p(pack, "supplement.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "pairs": items,
                                              "ref_relations": rh.REF_RELATIONS,
                                              "directions": ["asset_derived", "relative_derived", "none", "open"]})
    with open(p(out, SUPP), "w", encoding=ir.ENC) as f:
        f.write("\t".join(rh.PAIR_HEAD) + "\n" + "".join("%s\t%s\t\t\t\n" % (x["asset_id"], x["relative"])
                                                         for x in items))
    print("пакет дополнения: %d пар -> %s, шаблон %s" % (len(items), pack, p(out, SUPP)))


def check_supp(rows, pairs):
    bad = rh.check_reference({}, rows, [])
    got = sorted((r["asset_id"].upper(), r["relative"].upper()) for r in rows)
    want = sorted((x.upper(), b.upper()) for x, b in pairs)
    if got != want:
        bad.append("пары дополнения не те: %s против %s" % (got, want))
    return bad


def locksupp(out=OUT):
    a = load_amend2(out)
    if os.path.exists(p(out, SUPP_LOCK)):
        raise SystemExit("дополнение уже заморожено")
    if os.path.exists(p(out, "answers_vitali.tsv")):
        raise SystemExit("ответы Vitali уже есть - дополнение после ответов не замораживается")
    rows = ir.read_tsv(p(out, SUPP))
    bad = check_supp(rows, a["supplement_pairs"])
    if bad:
        raise SystemExit("дополнение с ошибками: " + "; ".join(bad))
    ir.dump_json(p(out, SUPP_LOCK), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "amendment2_sha256": a["sha256"],
                                     "supplement_sha256": rh.file_sha(p(out, SUPP)),
                                     "answers_present_at_lock": False})
    print("дополнение заморожено: %d пар" % len(rows))


def load_supp(out=OUT):
    if not os.path.exists(p(out, SUPP_LOCK)):
        return None
    lk = ir.load_json(p(out, SUPP_LOCK))
    if rh.file_sha(p(out, SUPP)) != lk["supplement_sha256"]:
        raise SystemExit("дополнение изменено после заморозки")
    return ir.read_tsv(p(out, SUPP))


# ---------------------------------------------------------------- подсчёт

def actionable(c):
    """Утверждение после правила: засчитанное по DERIVED_FROM / STATE_VARIANT_OF эталона без известного направления -
    unresolved (зачёта нет). Несовпадение вида связи (status wrong) остаётся ошибкой: правило не прячет промахи."""
    if c["status"] == "ok" and c["ref"] in NEEDS_DIR and c["direction"] not in KNOWN_DIR:
        return dict(c, status="open", unresolved_by_rule=True)
    return c


def slices(claims, exclude_pairs, excluded_sets):
    raw = rd.subsets(claims, exclude_pairs, excluded_sets)
    act = rd.subsets([actionable(c) for c in claims], exclude_pairs, excluded_sets)
    return {"relation_precision_gate": act["strict_blind"], "relation_precision_all": act["all"],
            "strict_unseen": act["strict_unseen"],
            "strong_relation_precision_primary": act["all_STRONG"],
            "candidate_relation_precision_primary": act["all_CANDIDATE"],
            "raw_strict_blind": raw["strict_blind"], "raw_all": raw["all"], "raw_all_STRONG": raw["all_STRONG"],
            "unresolved_by_rule": [[c["asset_id"], c["relative"], c["level"], c["ref"], c["direction"]]
                                   for c in claims if actionable(c).get("unresolved_by_rule")]}


def supp_slices(rels, supp, keys, pairs):
    want = {(x.upper(), b.upper()) for x, b in pairs}
    rows = [c for c in rh.relation_metrics(rels, supp, keys)["rows"]
            if (c["asset_id"].upper(), c["relative"].upper()) in want]
    act = [actionable(c) for c in rows]
    return {"strong_relation_precision_supplemental": rd.precision([c for c in act if c["level"] == "STRONG"]),
            "supplemental_all": rd.precision(act),
            "rows": [[c["asset_id"], c["relative"], c["level"], c["ref"], c["direction"], c["status"]] for c in act]}


def diag(out=OUT):
    a1, a2 = rd.load_amend(out), load_amend2(out)
    d, h = rh.load_freeze(out), rh.load_holdout(out)
    if a2["gates_amendment_sha256"] != a1["sha256"] or a2["freeze_sha256"] != d["sha256"]:
        raise SystemExit("вторая поправка написана к другой первой поправке или снимку")
    _ref, _refp, lk = rh.load_reference(out)
    if lk["reference_sha256"] != a2["reference_sha256"] or lk["reference_pairs_sha256"] != a2["reference_pairs_sha256"]:
        raise SystemExit("эталон не тот, к которому написана вторая поправка")
    rep = ir.load_json(p(out, "report.json"))
    if rep["freeze_sha256"] != d["sha256"] or rep["holdout_sha256"] != h["sha256"]:
        raise SystemExit("report.json от другого снимка - сначала routing_holdout.py report")
    keys = [x["asset_id"] for x in h["items"]]
    rel = slices(rep["relation_claims"], a1["strict_blind_exclude_pairs"], set(h["excluded_sets"]))
    supp = load_supp(out)
    sup = supp_slices(rh.load_relations(out), supp, keys, a2["supplement_pairs"]) if supp is not None else None
    rows = rep["rows"]
    layers = {}
    for n, _q, sub in rh.LAYERS:
        rs = [r for r in rows if r["layer"] == n]
        layers[n] = {"metrics": rh.routing_metrics(rs), "outcomes": rd.breakdown(rs),
                     "subs": {s: rd.breakdown([r for r in rs if r["sub"] == s]) for s, _m in sub}}
    checks = rd.amended_checks(rep["checks"], rel["relation_precision_gate"], a1["gates_unchanged"])
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "amendment2_sha256": a2["sha256"],
           "gates_amendment_sha256": a1["sha256"], "freeze_sha256": d["sha256"], "report_created": rep["created"],
           "passed": rh.verdict(checks), "checks": checks, "frozen_report_passed": rep["passed"],
           "relations": rel, "supplement": sup, "total": rep["total"], "outcomes": rd.breakdown(rows),
           "layers": layers, "semantic_accuracy": rep["semantic_accuracy"], "semantic_n": rep["semantic_n"],
           "outcome_rows": [[r["asset_id"], r["layer"], r["semantic_kind"], r["ref_semantic_kind"], r["rule"],
                             r["rule_unit"], r["ref_route"], rd.outcome(r)] for r in rows],
           "missing_context": [[r["asset_id"], r["missing_context"]] for r in rows if r["missing_context"]]}
    ir.dump_json(p(out, "diag2.json"), res)
    write_md(out, res, a1)
    return res


def write_md(out, res, a1):
    word = {True: "PASS", False: "**FAIL**", None: "не решено"}
    yes = {True: "да", False: "**нет**", None: "нет данных"}
    rel, t = res["relations"], res["total"]

    def pr(x):
        if not x:
            return "нет данных"
        return "%s (%d из %d закрытых; утверждений %d)" % (x["relation_precision"], x["ok"], x["closed"], x["claims"])
    vals = [str(t["dangerous_false_standalone"]),
            "%s (%d из %d)" % (t["routing_accuracy"], t["correct"], t["decided"]),
            "%s (%d из %d)" % (t["routing_coverage"], t["decided"], t["ref_closed"]),
            "%s (%d из %d одиночных по эталону)" % (t["overconservative_rate"], t["overconservative"], t["ref_standalone"]),
            pr(rel["relation_precision_gate"])]
    L = ["# ROUTING_RULES_V4_R1 - слепой holdout, итог: %s" % word[res["passed"]], "",
         "снимок %s, поправки %s и %s (обе до ответов); замороженный report.md: %s (точность родства там по всем, "
         "без правила)." % (res["freeze_sha256"][:12], res["gates_amendment_sha256"][:12],
                            res["amendment2_sha256"][:12], word[res["frozen_report_passed"]]), "",
         "## Ворота", "", "| ворота | значение | пройдено |", "|---|---|---|"]
    for (k, v), val in zip(res["checks"].items(), vals):
        L.append("| %s | %s | %s |" % (k, val, yes[v]))
    sup = res["supplement"]
    L += ["", "## Точность родства (по утверждениям детектора, ACTIONABLE_RELATION_TRUTH)", "",
          "| срез | значение |", "|---|---|",
          "| relation_precision_gate (strict_blind, ворота) | %s |" % pr(rel["relation_precision_gate"]),
          "| relation_precision_all (с XBASE-парой) | %s |" % pr(rel["relation_precision_all"]),
          "| strong_relation_precision_primary | %s |" % pr(rel["strong_relation_precision_primary"]),
          "| strong_relation_precision_supplemental (слепое дополнение, не ворота) | %s |" % (
              pr(sup["strong_relation_precision_supplemental"]) if sup else "дополнения нет"),
          "| candidate_relation_precision_primary | %s |" % pr(rel["candidate_relation_precision_primary"]),
          "| strict_unseen (диагностика) | %s |" % pr(rel["strict_unseen"]),
          "| без правила: strict_blind / all / STRONG | %s / %s / %s |" % (
              pr(rel["raw_strict_blind"]), pr(rel["raw_all"]), pr(rel["raw_all_STRONG"])), "",
          "unresolved по правилу (DERIVED_FROM / STATE_VARIANT_OF без направления): %s." % (
              "; ".join("%s ~ %s %s %s" % tuple(x[:4]) for x in rel["unresolved_by_rule"]) or "нет")]
    if sup:
        L += ["", "Дополнение: " + "; ".join("%s ~ %s %s -> %s %s (%s)" % tuple(x) for x in sup["rows"]) + "."]
    L += ["", "## Исходы маршрута (диагностика)", "", "| исход | n | что значит |", "|---|---|---|"]
    L += ["| %s | %d | %s |" % (k, res["outcomes"][k], rd.OUTCOMES[k]) for k in rd.OUTCOMES]
    L += ["", "Точность оси A Vitali против эталона: %s (из %d)." % (res["semantic_accuracy"], res["semantic_n"]),
          "", "## По слоям отбора", "",
          "| слой | n | точность | охват | " + " | ".join(rd.OUTCOMES) + " |",
          "|---|---|---|---|" + "---|" * len(rd.OUTCOMES)]
    for n, x in res["layers"].items():
        m = x["metrics"]
        L.append("| %s | %d | %s | %s | %s |" % (n, m["n"], m["routing_accuracy"], m["routing_coverage"],
                                                 " | ".join(str(x["outcomes"][k]) for k in rd.OUTCOMES)))
    L += ["", "## По предметам", "", "| предмет | слой | A Vitali / эталон | правило | маршрут | эталон | исход |",
          "|---|---|---|---|---|---|---|"]
    L += ["| %s | %s | %s / %s | %s | %s | %s | %s |" % tuple(r) for r in res["outcome_rows"]]
    if res["missing_context"]:
        L += ["", "missing_context: " + "; ".join("%s: %s" % tuple(x) for x in res["missing_context"])]
    with open(p(out, "diag2.md"), "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


def check(out=OUT):
    a = load_amend2(out)
    print("вторая поправка цела: %s, записана %s, до ответов; пар в дополнении %d" % (
        a["sha256"][:12], a["created"], len(a["supplement_pairs"])))
    s = load_supp(out)
    print("дополнение: %s" % ("заморожено, %d пар" % len(s) if s is not None else "не заморожено"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["amend2", "supplement", "locksupp", "diag", "check"])
    ap.add_argument("--out", default=OUT)
    x = ap.parse_args()
    os.chdir(ir.ROOT)
    {"amend2": amend2, "supplement": supplement, "locksupp": locksupp, "diag": diag, "check": check}[x.cmd](x.out)


if __name__ == "__main__":
    main()
