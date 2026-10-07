#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ROUTING_RULES_V4_R1 holdout: поправка к воротам и диагностика сверх замороженного отчёта.

Решение: специалист 01.10, передал Vitali в чате. Замороженный routing_holdout.py не правится (его sha в
FREEZE.json, report отказывает при изменении кода). Поправка - отдельный файл GATES_AMENDMENT.json, пишется
ДО ответов Vitali вместе с sha этого скрипта; diag читает report.json замороженного отчёта и считает:

  - relation_precision_all и relation_precision_strict_blind - без пар, где набор родственника был в выборке
    диагностики V3/V4 (XBASE1:99 ~ XB1BR:99: XB1BR:59 был на карточках V3). Ворота точности родства (>= 0.95,
    закрытых >= 5, счёт по утверждениям детектора) - по strict_blind. Совпали - вопрос закрыт, отбор не меняется;
  - relation_precision_strict_unseen - без всех утверждений, чей родственник в excluded_sets holdout
    (negatives / lookalikes V1 и прочее). Только диагностика;
  - точность родства по уровню STRONG / CANDIDATE - диагностика;
  - разбор 40 предметов по исходу (OUTCOMES) и он же по слоям отбора - диагностика.

Остальные ворота те же, что в FREEZE.json.

    py -3.13 tools/hdart/routing_holdout_diag.py amend   # один раз, до answers_vitali.tsv
    py -3.13 tools/hdart/routing_holdout_diag.py diag    # после routing_holdout.py report
    py -3.13 tools/hdart/routing_holdout_diag.py check
"""
import argparse
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir          # noqa: E402
import routing_holdout as rh           # noqa: E402

OUT = rh.OUT
ME = os.path.relpath(os.path.abspath(__file__), ir.ROOT).replace(os.sep, "/")

STRICT_BLIND_EXCLUDE = [["XBASE1:99", "XB1BR:99"]]
STRICT_BLIND_WHY = ("набор XB1BR был в выборке диагностики V3/V4 (XB1BR:59 на карточках identity-routing-v3-diag) - "
                    "пара не слепая для правил, настроенных на V3/V4")

OUTCOMES = {
    "DANGEROUS_STANDALONE": "правило дало STANDALONE_RENDER, эталон - маршрут из DANGEROUS_REF",
    "AUTO_CORRECT": "правило решило само (не REVIEW), эталон закрыт, маршрут совпал",
    "AUTO_WRONG": "правило решило само, эталон закрыт, маршрут не совпал (и это не опасный одиночный)",
    "AUTO_REF_OPEN": "правило решило само, а эталон маршрут не закрыл - не судится",
    "REVIEW_CONSERVATIVE": "REVIEW, а эталон - не одиночный предмет или маршрут не закрыл: осторожность оправдана",
    "REVIEW_UNNECESSARY": "REVIEW, а эталон - STANDALONE_RENDER: лишняя работа человеку",
}


def p(out, name):
    return os.path.join(out, name)


# ---------------------------------------------------------------- amend

def amend_body(d, h, rl, out):
    return {"amends": "FREEZE.json gates: verified_relation_precision", "freeze_sha256": d["sha256"],
            "holdout_sha256": h["sha256"], "relations_sha256": rl["relations_sha256"],
            "relation_precision_gate_on": "strict_blind",
            "strict_blind_exclude_pairs": STRICT_BLIND_EXCLUDE, "strict_blind_why": STRICT_BLIND_WHY,
            "strict_unseen": "диагностика: без утверждений, чей родственник в excluded_sets holdout.json",
            "level_precision": "диагностика: точность родства отдельно по STRONG и CANDIDATE (all и strict_blind)",
            "outcomes": OUTCOMES, "outcomes_by_layer": "диагностика: OUTCOMES и метрики маршрута по слоям отбора",
            "gates_unchanged": d["gates"], "diag_code": ME, "diag_code_sha256": rh.file_sha(ME),
            "answers_present_at_amend": os.path.exists(p(out, "answers_vitali.tsv")),
            "reference_locked_at_amend": os.path.exists(p(out, "reference.lock.json"))}


def amend(out=OUT):
    if os.path.exists(p(out, "GATES_AMENDMENT.json")):
        raise SystemExit("поправка уже записана: %s" % p(out, "GATES_AMENDMENT.json"))
    if os.path.exists(p(out, "answers_vitali.tsv")):
        raise SystemExit("ответы Vitali уже есть - поправка к воротам после ответов не пишется")
    d, h = rh.load_freeze(out), rh.load_holdout(out)
    rl = ir.load_json(p(out, "relations.lock.json"))
    body = amend_body(d, h, rl, out)
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body),
                decided="специалист 01.10, передал Vitali в чате: relation_precision_all и _strict_blind, ворота по "
                        "strict_blind; STRONG/CANDIDATE и разбор исходов по слоям - диагностика, не ворота",
                rule="после ответов holdout поправка и код диагностики не меняются")
    ir.dump_json(p(out, "GATES_AMENDMENT.json"), data)
    print("поправка записана (sha256 %s), до ответов: %s, эталон заморожен: %s" % (
        data["sha256"][:12], not body["answers_present_at_amend"], body["reference_locked_at_amend"]))
    return data


def load_amend(out=OUT):
    a = ir.load_json(p(out, "GATES_AMENDMENT.json"))
    body = {k: a[k] for k in a if k not in ("created", "sha256", "decided", "rule")}
    if ir.sha(body) != a["sha256"]:
        raise SystemExit("GATES_AMENDMENT.json изменён после записи: хэш не сходится")
    if a["answers_present_at_amend"]:
        raise SystemExit("поправка записана при ответах - недействительна")
    if not os.path.exists(a["diag_code"]) or rh.file_sha(a["diag_code"]) != a["diag_code_sha256"]:
        raise SystemExit("код диагностики изменён после поправки: %s" % a["diag_code"])
    return a


# ---------------------------------------------------------------- metrics

def precision(claims):
    closed = [c for c in claims if c["status"] != "open"]
    ok = sum(c["status"] == "ok" for c in closed)
    return {"claims": len(claims), "closed": len(closed), "ok": ok, "relation_precision": rh.rate(ok, len(closed))}


def subsets(claims, exclude_pairs, excluded_sets):
    ex = {(a.upper(), b.upper()) for a, b in exclude_pairs}
    ex |= {(b, a) for a, b in ex}
    blind = [c for c in claims if (c["asset_id"].upper(), c["relative"].upper()) not in ex]
    unseen = [c for c in blind if rh.pset(c["relative"]) not in excluded_sets]
    res = {"all": precision(claims), "strict_blind": precision(blind), "strict_unseen": precision(unseen)}
    for name, cs in (("all", claims), ("strict_blind", blind)):
        for lv in ("STRONG", "CANDIDATE"):
            res["%s_%s" % (name, lv)] = precision([c for c in cs if c["level"] == lv])
    res["removed_strict_blind"] = [[c["asset_id"], c["relative"], c["level"], c["status"]] for c in claims
                                   if c not in blind]
    res["removed_strict_unseen"] = [[c["asset_id"], c["relative"], c["level"], c["status"]] for c in blind
                                    if c not in unseen]
    return res


def outcome(row):
    u, ref = row["rule_unit"], row["ref_route"]
    if u == "STANDALONE_RENDER" and ref in ir.DANGEROUS_REF:
        return "DANGEROUS_STANDALONE"
    if u == "REVIEW":
        return "REVIEW_UNNECESSARY" if ref == "STANDALONE_RENDER" else "REVIEW_CONSERVATIVE"
    if ref == "open":
        return "AUTO_REF_OPEN"
    return "AUTO_CORRECT" if u == ref else "AUTO_WRONG"


def breakdown(rows):
    c = Counter(outcome(r) for r in rows)
    return {k: c.get(k, 0) for k in OUTCOMES}


def amended_checks(checks, strict, g):
    out = dict(list(checks.items())[:-1])
    prec = strict["relation_precision"] if strict["closed"] >= g["relation_precision_min_n"] else None
    out["relation_precision_strict_blind >= %.2f (закрытых >= %d)" % (
        g["relation_precision_min"], g["relation_precision_min_n"])] = (
        None if prec is None else prec >= g["relation_precision_min"])
    return out


# ---------------------------------------------------------------- diag

def diag(out=OUT):
    a = load_amend(out)
    d, h = rh.load_freeze(out), rh.load_holdout(out)
    if a["freeze_sha256"] != d["sha256"] or a["holdout_sha256"] != h["sha256"]:
        raise SystemExit("поправка написана к другому снимку")
    rep = ir.load_json(p(out, "report.json"))
    if rep["freeze_sha256"] != d["sha256"] or rep["holdout_sha256"] != h["sha256"]:
        raise SystemExit("report.json от другого снимка - сначала routing_holdout.py report")
    rh.load_reference(out)
    rel = subsets(rep["relation_claims"], a["strict_blind_exclude_pairs"], set(h["excluded_sets"]))
    rows = rep["rows"]
    layers = {}
    for n, _q, sub in rh.LAYERS:
        rs = [r for r in rows if r["layer"] == n]
        layers[n] = {"metrics": rh.routing_metrics(rs), "outcomes": breakdown(rs),
                     "subs": {s: breakdown([r for r in rs if r["sub"] == s]) for s, _m in sub}}
    checks = amended_checks(rep["checks"], rel["strict_blind"], a["gates_unchanged"])
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "amendment_sha256": a["sha256"],
           "freeze_sha256": d["sha256"], "report_created": rep["created"],
           "passed": rh.verdict(checks), "checks": checks, "frozen_report_passed": rep["passed"],
           "all_equals_strict_blind": rel["all"]["relation_precision"] == rel["strict_blind"]["relation_precision"],
           "relations": rel, "outcomes": breakdown(rows), "layers": layers,
           "outcome_rows": [[r["asset_id"], r["layer"], r["rule_unit"], r["ref_route"], outcome(r)] for r in rows]}
    ir.dump_json(p(out, "diag.json"), res)
    write_md(out, res, a)
    return res


def write_md(out, res, a):
    word = {True: "PASS", False: "**FAIL**", None: "не решено"}
    yes = {True: "да", False: "**нет**", None: "нет данных"}
    rel = res["relations"]

    def pr(x):
        return "%s (%d из %d закрытых; утверждений %d)" % (x["relation_precision"], x["ok"], x["closed"], x["claims"])
    L = ["# ROUTING_RULES_V4_R1 holdout - с поправкой ворот: %s" % word[res["passed"]], "",
         "поправка %s (специалист 01.10, записана до ответов), снимок %s; замороженный отчёт: %s." % (
             res["amendment_sha256"][:12], res["freeze_sha256"][:12], word[res["frozen_report_passed"]]), "",
         "## Ворота (точность родства - по strict_blind)", "", "| ворота | пройдено |", "|---|---|"]
    L += ["| %s | %s |" % (k, yes[v]) for k, v in res["checks"].items()]
    L += ["", "## Точность родства (по утверждениям детектора)", "", "| срез | значение |", "|---|---|",
          "| all | %s |" % pr(rel["all"]),
          "| strict_blind (ворота) | %s |" % pr(rel["strict_blind"]),
          "| strict_unseen (диагностика) | %s |" % pr(rel["strict_unseen"]),
          "| all STRONG / CANDIDATE | %s / %s |" % (pr(rel["all_STRONG"]), pr(rel["all_CANDIDATE"])),
          "| strict_blind STRONG / CANDIDATE | %s / %s |" % (pr(rel["strict_blind_STRONG"]),
                                                           pr(rel["strict_blind_CANDIDATE"])), "",
          "all и strict_blind %s." % ("совпали - вопрос закрыт" if res["all_equals_strict_blind"] else "РАЗОШЛИСЬ"),
          "Убрано из strict_blind: %s (%s)." % ("; ".join("%s ~ %s %s %s" % tuple(x)
                                                       for x in rel["removed_strict_blind"]) or "-",
                                             a["strict_blind_why"]),
          "Убрано ещё из strict_unseen: %s." % ("; ".join("%s ~ %s %s %s" % tuple(x)
                                                       for x in rel["removed_strict_unseen"]) or "-"), "",
          "## Исходы маршрута (диагностика)", "", "| исход | n | что значит |", "|---|---|---|"]
    L += ["| %s | %d | %s |" % (k, res["outcomes"][k], OUTCOMES[k]) for k in OUTCOMES]
    L += ["", "## По слоям отбора", "",
          "| слой | n | точность | охват | " + " | ".join(OUTCOMES) + " |",
          "|---|---|---|---|" + "---|" * len(OUTCOMES)]
    for n, x in res["layers"].items():
        m = x["metrics"]
        L.append("| %s | %d | %s | %s | %s |" % (n, m["n"], m["routing_accuracy"], m["routing_coverage"],
                                                 " | ".join(str(x["outcomes"][k]) for k in OUTCOMES)))
    L += ["", "## По предметам", "", "| предмет | слой | правило | эталон | исход |", "|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %s |" % tuple(r) for r in res["outcome_rows"]]
    with open(p(out, "diag.md"), "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


def check(out=OUT):
    a = load_amend(out)
    print("поправка цела: %s, записана %s, до ответов; эталон тогда заморожен: %s" % (
        a["sha256"][:12], a["created"], a["reference_locked_at_amend"]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["amend", "diag", "check"])
    ap.add_argument("--out", default=OUT)
    x = ap.parse_args()
    os.chdir(ir.ROOT)
    {"amend": amend, "diag": diag, "check": check}[x.cmd](x.out)


if __name__ == "__main__":
    main()
