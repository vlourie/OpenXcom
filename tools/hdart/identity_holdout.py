#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""IDENTITY_GATE_V2: слепой holdout - отбор и заморозка (специалист 01.10, после закрытия MADDECOR_WASTE:47). CPU.

Регрессия (3 известных провала) проверяет, раскрывает ли карточка старые ошибки. Holdout решает, выдавать ли
IDENTITY_VISUALLY_VERIFIED как production gate: 20-30 НОВЫХ спорных предметов, список замораживается ДО ответов
и до эталона, потом не правится. Отбор детерминированный (зерно), слои:

    agree      две модели согласны, статус AGENT_PROPOSED - так выглядели все три провала регрессии (R-143)
    disagree   две модели разошлись (REVIEW_REQUIRED)
    fragment   подозрение на кусок большего (part_fragment_suspect, R-153)
    confirmed  подтверждён человеком по кадру 32x40 (HUMAN_CONFIRMED / HUMAN_EDITED)
    class      спорный класс предмет / рельеф (class_check)

Генеральная совокупность: строки generation.tsv с action GENERATE (одиночные заказы модели - то, что ворота будут
пропускать в производство), кроме SKIP. Исключены: уже виденные на карточках опознания (все папки identity-*),
ассеты с классом от человека (class_decisions.tsv). Один ассет на семейство (asset_id) и на набор PCK. Слой в карточку не идёт -
порядок карточек перемешан зерном, человек не знает, из какого слоя предмет.

Порядок (специалист 01.10): Vitali размечает все 28 вслепую (answers_vitali.tsv) - он тестируемая сторона;
эталон (reference.tsv) собирается ПОСЛЕ ответов и не им, из независимых источников: подтверждённые структурные
связи, MCD, копии в других наборах, связи состояний и составных, место на карте, ранее закрытые истины человека,
при нужде второй независимый разбор. Не закрылась истина - semantic_ok open, из знаменателя названий исключается,
не угадывается. Карточку до конца holdout не менять (панель «исходный набор / состояние» - после).
Ворота и метрики заморожены ДО ответов (gates.json, команда gates - отказ, если ответы уже есть). Считаются в
целом и ПО СЛОЯМ: общий процент на 28 скрывает провал одного слоя.

Столбцы reference.tsv: asset_id, ref_status (статус-истина; пусто - класс не установлен), identity_ok, old_rejected,
structural_ok, semantic_ok (yes / no / open), truth_identity, relation, old_ok (верно ли прежнее описание-промпт
с карточки: yes / no / open - у слоя confirmed это old_human_confirmation_overturned), sources (чем закрыта истина).

    py -3.13 tools/hdart/identity_holdout.py freeze            выбрать и заморозить (повторно - отказ)
    py -3.13 tools/hdart/identity_holdout.py cards             карточки по замороженному списку
    py -3.13 tools/hdart/identity_holdout.py gates             заморозить ворота до ответов (повторно - отказ)
    py -3.13 tools/hdart/identity_holdout.py gates --refreeze "<причина>"   до ответов: прежние -> gates.vN.json
    py -3.13 tools/hdart/identity_holdout.py check             список и ворота не менялись (хэш)
    py -3.13 tools/hdart/identity_holdout.py report            ответы против эталона: метрики, слои, ворота
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ENC = "utf-8-sig"
GEN = os.path.join("art", "objects", "generation")
PROBES = os.path.join(GEN, "probes")
OUT = os.path.join(PROBES, "identity-gate-v2-holdout")
DISC = os.path.join("art", "objects", "discovery")
SEED = "identity-gate-v2-holdout-2026-10-01"
LAYERS = (("agree", 8), ("disagree", 8), ("fragment", 6), ("confirmed", 4), ("class", 2))


def read_tsv(path):
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def seen_on_cards():
    """Ассеты, уже показанные на карточках опознания (их ответ человека не слепой)."""
    out = set()
    for p in glob.glob(os.path.join(PROBES, "identity-*", "cards.json")):
        if os.path.normpath(os.path.dirname(p)) == os.path.normpath(OUT):
            continue
        with open(p, encoding=ENC) as f:
            out.update(a.upper() for a in json.load(f).get("assets", []))
    return out


def layer(r, prop):
    bl = r["blockers"].split()
    st = r["identity_status"]
    if "part_fragment_suspect" in bl:
        return "fragment"
    if "class_check" in bl:
        return "class"
    if st in ("HUMAN_CONFIRMED", "HUMAN_EDITED"):
        return "confirmed"
    if st == "REVIEW_REQUIRED":
        return "disagree"
    if st == "AGENT_PROPOSED" and (prop or {}).get("verdict") == "agree":
        return "agree"
    return ""


def order(key):
    return hashlib.sha256((SEED + "|" + key).encode()).hexdigest()


def select(rows, props, seen, classes):
    by = {}
    for r in rows:
        aid = r["asset_id"].upper()
        if r["action"] != "GENERATE" or r["status"] == "SKIP" or aid in seen or aid in classes:
            continue
        lay = layer(r, props.get(r["asset_id"]) or props.get(r["key"]))
        if lay:
            by.setdefault(lay, {}).setdefault(aid, r)        # первая строка ассета - самая популярная
    pick, short, sets = [], {}, set()
    for lay, n in LAYERS:
        cand = sorted(by.get(lay, {}).values(), key=lambda r: order(r["asset_id"].upper()))
        got = []
        for r in cand:                                   # не больше одного ассета на набор PCK
            s = r["asset_id"].split(":")[0].upper()
            if s not in sets and len(got) < n:
                sets.add(s)
                got.append(r)
        if len(got) < n:
            short[lay] = "%d из %d" % (len(got), n)
        pick += [{"asset_id": r["asset_id"], "layer": lay, "rank": int(r["rank"]), "kind": r["kind"],
                  "places": int(r["places"] or 0), "identity_status": r["identity_status"]} for r in got]
    pick.sort(key=lambda x: order("card|" + x["asset_id"].upper()))   # порядок карточек не выдаёт слой
    return pick, {lay: len(v) for lay, v in by.items()}, short


def digest(items):
    return hashlib.sha256("\n".join(x["asset_id"] for x in items).encode()).hexdigest()


def freeze(out):
    path = os.path.join(out, "holdout.json")
    if os.path.exists(path):
        raise SystemExit("holdout уже заморожен: %s - перевыбор запрещён (check / cards)" % path)
    rows = read_tsv(os.path.join(GEN, "generation.tsv"))
    with open(os.path.join(DISC, "proposals.json"), encoding=ENC) as f:
        props = json.load(f)
    classes = {r["asset_id"].upper() for r in read_tsv(os.path.join(DISC, "class_decisions.tsv"))}
    seen = seen_on_cards()
    items, pool, short = select(rows, props, seen, classes)
    if not 20 <= len(items) <= 30:
        raise SystemExit("отобрано %d, нужно 20-30 (недобор слоёв: %s)" % (len(items), short))
    os.makedirs(out, exist_ok=True)
    data = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "seed": SEED, "layers": dict(LAYERS),
            "pool": pool, "short": short, "excluded_seen": sorted(seen), "n": len(items),
            "sha256": digest(items), "items": items,
            "rule": "список заморожен до ответов и эталона; не правится; слой в карточку не идёт",
            "metrics": ["classification_accuracy", "semantic_accuracy", "unsure_rate", "false_standalone_rate"],
            "decided": "специалист 01.10, передал Vitali в чате 01.10: holdout можно замораживать при открытом "
                       "назначении C_INT:27"}
    with open(path, "w", encoding=ENC) as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("заморожено %d (sha256 %s): %s" % (len(items), data["sha256"][:12],
                                             ", ".join("%s %d" % (k, sum(1 for x in items if x["layer"] == k))
                                                       for k, _n in LAYERS)))
    print("пул по слоям:", pool, "; недобор:", short or "нет")
    return data


# Ворота IDENTITY_GATE_V2 на holdout (специалист 01.10, до ответов Vitali). false_standalone - самая дорогая
# ошибка: кусок самолёта, ушедший одиночным ассетом, рендер уже не спасёт
GATES = {
    "false_standalone_rate_max": 0.05,
    "class_accuracy_min": 0.90,
    "semantic_accuracy_min": 0.85,
    "unsure_rate_max": 0.15,
    "missing_context_rate_max": 0.10,
    "layer_class_accuracy_min": 0.75,
    "layer_hard_min_n": 4,                     # слой меньше - только диагностика (v2 ворот, специалист 01.10)
    "layer_diagnostic_max_class_errors": 1,
}
DEFINITIONS = {
    "class_accuracy": "статус ответа (предмет / кусок / не предмет) равен ref_status; знаменатель - ответы не UNSURE "
                      "с установленным ref_status (UNSURE считается только в unsure_rate, не дважды)",
    "false_standalone_rate": "ответ IDENTITY_VISUALLY_VERIFIED, а ref_status PART_FRAGMENT_CONFIRMED или NOT_OBJECT; "
                             "знаменатель - все предметы holdout",
    "semantic_accuracy": "только semantic_ok yes / no; верно - класс верен и semantic_ok yes, при неверном классе "
                         "название неверно; open, excluded и ответы UNSURE вне знаменателя",
    "unsure_rate": "ответов UNSURE из всех",
    "missing_context_rate": "ответов с непустым missing_context из всех (любой статус)",
    "old_human_confirmation_overturned": "слой confirmed: old_ok no - прежнее подтверждение по 32x40 опровергнуто; "
                                         "это довод ЗА V2, а не провал",
    "layers": "каждая метрика и по слою. Слой n >= layer_hard_min_n - ворота class_accuracy >= "
              "layer_class_accuracy_min; слой меньше - DIAGNOSTIC: показывается (ошибок класса не больше "
              "layer_diagnostic_max_class_errors), но сам holdout не валит - при n=2 одна ошибка это 50 %",
}


def canon(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def freeze_gates(out, refreeze="", decided=""):
    """refreeze - причина перезаморозки: только до ответов, прежняя версия уходит в gates.vN.json."""
    path = os.path.join(out, "gates.json")
    if os.path.exists(os.path.join(out, "answers_vitali.tsv")):
        raise SystemExit("ответы уже есть - ворота после ответов не замораживаются и не меняются")
    prev = None
    if os.path.exists(path):
        if not refreeze:
            raise SystemExit("ворота уже заморожены: %s (перезаморозка до ответов - --refreeze <причина>)" % path)
        prev = load_gates(out)
        k = 1
        while os.path.exists(os.path.join(out, "gates.v%d.json" % k)):
            k += 1
        os.replace(path, os.path.join(out, "gates.v%d.json" % k))
    d = load_frozen(out)
    body = {"thresholds": GATES, "definitions": DEFINITIONS, "holdout_sha256": d["sha256"]}
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=canon(body),
                decided=decided or "специалист 01.10, передал Vitali в чате 01.10: ворота до ответов, считать по слоям")
    if prev:
        data.update(replaces=prev["sha256"], replaced_created=prev["created"], refreeze_reason=refreeze)
    with open(path, "w", encoding=ENC) as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("ворота заморожены (sha256 %s): %s" % (data["sha256"][:12], GATES))


def load_gates(out):
    with open(os.path.join(out, "gates.json"), encoding=ENC) as f:
        g = json.load(f)
    body = {k: g[k] for k in ("thresholds", "definitions", "holdout_sha256")}
    if canon(body) != g["sha256"]:
        raise SystemExit("gates.json изменён после заморозки: хэш не сходится")
    return g


def rate(k, n):
    return round(k / n, 3) if n else None


def measure(rows):
    """Метрики набора строк report.json identity_card (с полями layer и old_ok)."""
    n = len(rows)
    cls = [r for r in rows if r["status"] != "UNSURE" and r["ref_status"]]
    sem = [r for r in rows if r["semantic"] is not None and r["status"] != "UNSURE"]
    conf = [r for r in rows if r.get("layer") == "confirmed"]
    return {"n": n,
            "class_accuracy": rate(sum(1 for r in cls if r["status_ok"]), len(cls)), "class_n": len(cls),
            "class_errors": sum(1 for r in cls if not r["status_ok"]),
            "class_open": sum(1 for r in rows if not r["ref_status"]),
            "false_standalone": sum(1 for r in rows if r["false_standalone"]),
            "false_standalone_rate": rate(sum(1 for r in rows if r["false_standalone"]), n),
            "semantic_accuracy": rate(sum(1 for r in sem if r["semantic"]), len(sem)), "semantic_n": len(sem),
            "semantic_open": sum(1 for r in rows if r["semantic_ok"] in ("open", "", "excluded")),
            "unsure_rate": rate(sum(1 for r in rows if r["status"] == "UNSURE"), n),
            "missing_context_rate": rate(sum(1 for r in rows if (r.get("missing_context") or "").strip()), n),
            "old_wrong": sum(1 for r in rows if r.get("old_ok") == "no"),
            "old_human_confirmation_overturned": "%d/%d" % (sum(1 for r in conf if r.get("old_ok") == "no"),
                                                          len(conf))}


def holdout_report(out, answers="", reference=""):
    import identity_card as ic
    d, g = load_frozen(out), load_gates(out)
    answers = answers or os.path.join(out, "answers_vitali.tsv")
    reference = reference or os.path.join(out, "reference.tsv")
    for p in (answers, reference):
        if not os.path.exists(p):
            raise SystemExit("нет %s" % p)
    ic.report(out, answers, reference)
    with open(os.path.join(out, "report.json"), encoding=ENC) as f:
        rep = json.load(f)
    refs = {r["asset_id"]: r for r in ic.read_tsv(reference)}
    layer = {x["asset_id"]: x["layer"] for x in d["items"]}
    rows = rep["rows"]
    for r in rows:
        r["layer"] = layer.get(r["asset_id"], "")
        r["old_ok"] = (refs.get(r["asset_id"], {}).get("old_ok") or "").strip().lower()
    t = g["thresholds"]
    total = measure(rows)
    layers = {lay: measure([r for r in rows if r["layer"] == lay]) for lay, _n in LAYERS}

    def le(v, lim):
        return None if v is None else v <= lim

    def ge(v, lim):
        return None if v is None else v >= lim

    checks = {"false_standalone_rate <= %s" % t["false_standalone_rate_max"]:
                  le(total["false_standalone_rate"], t["false_standalone_rate_max"]),
              "class_accuracy >= %s" % t["class_accuracy_min"]: ge(total["class_accuracy"], t["class_accuracy_min"]),
              "semantic_accuracy >= %s (закрытые истины)" % t["semantic_accuracy_min"]:
                  ge(total["semantic_accuracy"], t["semantic_accuracy_min"]),
              "unsure_rate <= %s" % t["unsure_rate_max"]: le(total["unsure_rate"], t["unsure_rate_max"]),
              "missing_context_rate <= %s" % t["missing_context_rate_max"]:
                  le(total["missing_context_rate"], t["missing_context_rate_max"])}
    diag = {}
    hard_n = t.get("layer_hard_min_n", 0)
    for lay, m in layers.items():
        if not m["n"]:                                   # слоя нет в holdout - нечего проверять
            continue
        if m["n"] >= hard_n:
            checks["слой %s (n=%d): class_accuracy >= %s" % (lay, m["n"], t["layer_class_accuracy_min"])] = \
                ge(m["class_accuracy"], t["layer_class_accuracy_min"])
        else:                                            # маленький слой: одна ошибка - не приговор holdout
            diag["слой %s (n=%d, диагностика): ошибок класса <= %s" % (
                lay, m["n"], t["layer_diagnostic_max_class_errors"])] = \
                None if not m["class_n"] else m["class_errors"] <= t["layer_diagnostic_max_class_errors"]
    passed = ic.gate(checks)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "holdout_sha256": d["sha256"],
           "gates_sha256": g["sha256"], "passed": passed, "checks": checks, "diagnostics": diag, "total": total,
           "layers": layers, "answers": answers, "reference": reference, "invalid": rep["invalid"]}
    with open(os.path.join(out, "holdout_report.json"), "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    word = {True: "PASS", False: "**FAIL**", None: "не решены"}
    yes = {True: "да", False: "**нет**", None: "нет данных"}

    def cell(v):
        return "-" if v is None else str(v)

    # три блока рядом (специалист 01.10): не только PASS / FAIL, а где V2 работает и где нет
    L = ["# IDENTITY_GATE_V2 holdout: %s" % word[passed], "",
         "holdout %s, ворота %s (заморожены %s)" % (d["sha256"][:12], g["sha256"][:12], g["created"]), "",
         "## GLOBAL", "", "| метрика | значение | из | ворота | пройдено |", "|---|---|---|---|---|"]
    glob = (("class_accuracy", "class_n", ">= %s" % t["class_accuracy_min"]),
            ("semantic_accuracy", "semantic_n", ">= %s" % t["semantic_accuracy_min"]),
            ("false_standalone_rate", "n", "<= %s" % t["false_standalone_rate_max"]),
            ("unsure_rate", "n", "<= %s" % t["unsure_rate_max"]),
            ("missing_context_rate", "n", "<= %s" % t["missing_context_rate_max"]))
    for key, den, lim in glob:
        v = next((v for k, v in checks.items() if k.startswith(key)), None)
        L.append("| %s | %s | %s | %s | %s |" % (key, cell(total[key]), total[den], lim, yes[v]))
    L += ["", "Класс не установлен: %d; название open / excluded: %d (вне знаменателя названий)." % (
        total["class_open"], total["semantic_open"]),
          "", "## BY LAYER", "",
          "| слой | n | class_accuracy | ошибок класса | false_standalone_rate | semantic_accuracy | unsure_rate "
          "| missing_context_rate | правило | пройдено |", "|---" * 10 + "|"]
    for lay, m in layers.items():
        if not m["n"]:
            continue
        if m["n"] >= hard_n:
            rule, v = "ворота: class >= %s" % t["layer_class_accuracy_min"], next(
                v for k, v in checks.items() if k.startswith("слой %s " % lay))
        else:
            rule, v = "диагностика: ошибок <= %s" % t["layer_diagnostic_max_class_errors"], next(
                v for k, v in diag.items() if k.startswith("слой %s " % lay))
        L.append("| %s | %d | %s | %d | %s | %s | %s | %s | %s | %s |" % (
            lay, m["n"], cell(m["class_accuracy"]), m["class_errors"], cell(m["false_standalone_rate"]),
            cell(m["semantic_accuracy"]), cell(m["unsure_rate"]), cell(m["missing_context_rate"]), rule,
            yes[v] if m["n"] >= hard_n else "%s (не ворота)" % yes[v]))
    L += ["", "## OLD CONFIRMATIONS", "",
          "- old_human_confirmation_overturned (слой confirmed): %s - метрика, не ворота; опровергнутое прежнее "
          "подтверждение - довод за V2, а не провал" % total["old_human_confirmation_overturned"],
          "- прежнее описание неверно (old_ok no), все слои: %d из %d" % (total["old_wrong"], total["n"])]
    L += ["- %s: %d" % (lay, m["old_wrong"]) for lay, m in layers.items() if m["n"]]
    L += ["", "Ошибки в ответах или эталоне: " + "; ".join(rep["invalid"])] if rep["invalid"] else []
    with open(os.path.join(out, "holdout_report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return res


def load_frozen(out):
    with open(os.path.join(out, "holdout.json"), encoding=ENC) as f:
        data = json.load(f)
    if digest(data["items"]) != data["sha256"]:
        raise SystemExit("holdout.json изменён после заморозки: хэш не сходится")
    return data


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["freeze", "cards", "gates", "check", "report"])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--answers", default="")
    ap.add_argument("--reference", default="")
    ap.add_argument("--refreeze", default="", help="gates: причина перезаморозки (только до ответов)")
    ap.add_argument("--decided", default="", help="gates: кто и когда решил")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.cmd == "freeze":
        freeze(a.out)
    elif a.cmd == "gates":
        freeze_gates(a.out, a.refreeze, a.decided)
    elif a.cmd == "report":
        holdout_report(a.out, a.answers, a.reference)
    elif a.cmd == "check":
        d = load_frozen(a.out)
        print("holdout цел: %d предметов, sha256 %s, заморожен %s" % (d["n"], d["sha256"][:12], d["created"]))
        if os.path.exists(os.path.join(a.out, "gates.json")):
            g = load_gates(a.out)
            print("ворота целы: sha256 %s, заморожены %s" % (g["sha256"][:12], g["created"]))
    else:
        import identity_card as ic
        d = load_frozen(a.out)
        ic.make([x["asset_id"] for x in d["items"]], a.out,
                "IDENTITY_GATE_V2 - слепой holdout: %d новых спорных предметов" % d["n"])


if __name__ == "__main__":
    main()
