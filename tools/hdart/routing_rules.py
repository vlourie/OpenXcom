#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ROUTING_RULES_V4 - маршрут в HD правилами из метаданных, человек даёт только смысл (специалист 01.10). CPU.

IDENTITY_ROUTING_V3 показал: смысл (ось A) человек по карточке размечает хорошо (25/28), а маршрут (ось B)
нет (13/24, опасных одиночных 5) - часть маршрута по карточке не видна вовсе: перекраска, состояние, четверть
составного. Здесь те же 28: ось A - из ответов Vitali V3, маршрут считается правилами, STANDALONE_RENDER -
последний запасной вариант, а не равноправный выбор.

Правила по порядку (первое сработавшее решает):
    R1  A = TERRAIN_RELIEF                                       EXCLUDE
    R2  A = NOT_OBJECT                                           EXCLUDE   (определение EXCLUDE в spec V3:
                                                                           пол, стена, рельеф, эффект)
    R3  state_variants.json / class_decisions state_variant      STATE_VARIANT
    R4  перекраска / зеркало: строка generation.tsv своего ключа
        с relation recolor / mirror или член семейства не canonical DERIVED
    R5  составной заказ (generation kind «составной», граф кусков
        obj_series) или class_decisions part_fragment             COMPOSITE_PART
    R6  modular_objects.json / class_decisions structural_modular STRUCTURAL_MODULAR
    R7  открытый вопрос о родстве: кадр в review семейства, блокеры
        family_review / in_review / part_fragment_suspect / class_check,
        relation alternate_view                                    REVIEW    (родство не доказано отсутствующим)
    R8  A = OBJECT / OBJECT_PART                                  STANDALONE_RENDER
    R9  иначе (UNSURE)                                            REVIEW

Ворота диагностики (специалист 01.10): DANGEROUS_FALSE_STANDALONE = 0; точность маршрута по решённым правилами
(REVIEW вне знаменателя) не ниже 0.90; REVIEW допустим, одиночный заказ по умолчанию - нет. Отдельно печатается
охват (решено правилами из закрытых в эталоне) и чувствительность: R2 выключен (буквальная схема специалиста,
NOT_OBJECT -> REVIEW) и R7 выключен (одиночный при любом открытом вопросе).

Не слепо: правила написаны после того, как эталон V3 и метаданные этих 28 были видны. Эталон в расчёт маршрута
не входит, только в сверку.

    py -3.13 tools/hdart/routing_rules.py freeze    заморозить правила, ворота и хэши входов (после результата - отказ)
    py -3.13 tools/hdart/routing_rules.py run       маршрут правилами, сверка с reference_v2.tsv, report.md / .json
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir          # noqa: E402

ROOT = ir.ROOT
ENC = ir.ENC
V3 = ir.OUT
OUT = os.path.join(ir.PROBES, "routing-rules-v4-diag")
INPUTS = {
    "semantic": os.path.join(V3, "answers_vitali.tsv"),
    "reference": os.path.join(V3, "reference_v2.tsv"),
    "spec_v3": os.path.join(V3, "spec.json"),
    "generation": os.path.join("art", "objects", "generation", "generation.tsv"),
    "families": os.path.join("art", "objects", "families", "families.json"),
    "state_variants": os.path.join("art", "objects", "discovery", "state_variants.json"),
    "modular_objects": os.path.join("art", "objects", "discovery", "modular_objects.json"),
    "class_decisions": os.path.join("art", "objects", "discovery", "class_decisions.tsv"),
}
RULES = {
    "R1": "A = TERRAIN_RELIEF -> EXCLUDE",
    "R2": "A = NOT_OBJECT -> EXCLUDE (spec V3: EXCLUDE - пол, стена, рельеф, эффект)",
    "R3": "state_variants.json / class_decisions state_variant -> STATE_VARIANT",
    "R4": "generation.tsv своего ключа relation recolor / mirror или член семейства не canonical -> DERIVED",
    "R5": "generation kind составной или class_decisions part_fragment -> COMPOSITE_PART",
    "R6": "modular_objects.json / class_decisions structural_modular -> STRUCTURAL_MODULAR",
    "R7": "открытый вопрос о родстве (review семейства, family_review, in_review, part_fragment_suspect, "
          "class_check, alternate_view) -> REVIEW",
    "R8": "A = OBJECT / OBJECT_PART -> STANDALONE_RENDER (последний запасной)",
    "R9": "иначе -> REVIEW",
}
# V4_R1 (специалист 01.10, RELATION_DISCOVERY_V1): правила V4 без изменений плюс родство из
# relation_probe.discover и осторожный запасной для куска. Отдельная заморозка в своей папке; V4 считается как был.
RULES_R1 = dict(RULES)
RULES_R1.update({
    "R0v": "родство подтверждено человеком (verified) -> по родству: RECOLOR_OF -> DERIVED, "
           "RECOLOR_WITH_LOCAL_EDIT -> STATE_VARIANT (сейчас подтверждённых нет)",
    "R7r": "кандидат родства не подтверждён (RECOLOR_OF / RECOLOR_WITH_LOCAL_EDIT со стороны производного, "
           "FIXED_NEIGHBOUR) -> REVIEW; «сходство высокое -> родство» не делается",
    "R8a": "A = OBJECT_PART и подтверждённой одиночности нет -> REVIEW",
    "R8": "A = OBJECT -> STANDALONE_RENDER (последний запасной)",
})
OUT_R1 = os.path.join(ir.PROBES, "routing-rules-v4r1-diag")
RELATIONS = os.path.join(ir.PROBES, "relation-discovery-v1", "relations.json")
GATES = {"dangerous_false_standalone_max": 0, "routing_accuracy_min": 0.90,
         "accuracy": "верно / решено правилами при закрытом эталоне; REVIEW вне знаменателя, охват печатается отдельно"}
OPEN_BLOCKERS = ("family_review", "in_review", "part_fragment_suspect", "class_check")


def file_sha(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def freeze(out=OUT, inputs=None, version="V4"):
    inputs = dict(inputs or INPUTS)
    if version == "V4_R1" and "relations" not in inputs:
        inputs["relations"] = RELATIONS
    path = os.path.join(out, "rules.json")
    if os.path.exists(path):
        raise SystemExit("правила уже заморожены: %s" % path)
    if os.path.exists(os.path.join(out, "report.json")):
        raise SystemExit("результат уже есть - правила после результата не замораживаются")
    os.makedirs(out, exist_ok=True)
    body = {"rules": RULES_R1 if version == "V4_R1" else RULES, "gates": GATES,
            "inputs": {k: v.replace(os.sep, "/") for k, v in inputs.items()},
            "input_sha256": {k: file_sha(v) for k, v in inputs.items()}}
    if version != "V4":
        body["version"] = version           # у V4 поля нет - его хэш тот же, что при заморозке
    decided = ("специалист 01.10 после IDENTITY_ROUTING_V3 (manual routing FAIL), передал Vitali в чате"
               if version == "V4" else
               "специалист 01.10 RELATION_DISCOVERY_V1: правила V4 не менять, родство и OBJECT_PART -> REVIEW "
               "добавить и пересчитать те же 28; передал Vitali в чате")
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=ir.sha(body), decided=decided)
    ir.dump_json(path, data)
    print("правила заморожены (sha256 %s), входов %d" % (data["sha256"][:12], len(inputs)))
    return data


def load_rules(out=OUT):
    d = ir.load_json(os.path.join(out, "rules.json"))
    body = {k: d[k] for k in ("rules", "gates", "inputs", "input_sha256", "version") if k in d}
    if ir.sha(body) != d["sha256"]:
        raise SystemExit("rules.json изменён после заморозки: хэш не сходится")
    changed = [k for k, p in d["inputs"].items() if file_sha(p) != d["input_sha256"][k]]
    if changed:
        raise SystemExit("входы изменились после заморозки: %s" % ", ".join(changed))
    return d


def metadata(inp):
    """Всё, что правила знают о кадре, - только из метаданных, без эталона."""
    gen = {}
    for r in ir.read_tsv(inp["generation"]):
        gen.setdefault(r["key"], r)
    fam_rel, fam_review = {}, set()
    for fam in ir.load_json(inp["families"]):
        for m in fam.get("members", []):
            for k in m.get("keys", []):
                fam_rel.setdefault(k, m.get("relation", ""))
        for m in fam.get("review", []):
            fam_review.update(m.get("keys", []))
    state = {x["asset_id"] for x in ir.load_json(inp["state_variants"])}
    modular = set()
    for o in ir.load_json(inp["modular_objects"]):
        modular.update(p["asset_id"] for p in o.get("parts", []))
        modular.update(c["asset_id"] for c in o.get("composites", []))
    cls = {r["asset_id"]: r["asset_class"] for r in ir.read_tsv(inp["class_decisions"])}
    rels = ir.load_json(inp["relations"])["relations"] if "relations" in inp else None
    return gen, fam_rel, fam_review, state, modular, cls, rels


RELATION_UNIT = {"RECOLOR_OF": "DERIVED", "RECOLOR_WITH_LOCAL_EDIT": "STATE_VARIANT"}
# слепой holdout V4_R1 (специалист 01.10): перекраска с местной правкой - DERIVED_FROM, subtype
# recolor_with_local_edit, а не STATE_VARIANT, пока человек не докажет смену состояния. Влияет только на R0v
# (подтверждённое человеком); на диагностике 28 подтверждённых нет - её результат тот же
RELATION_UNIT_HOLDOUT = {"RECOLOR_OF": "DERIVED", "RECOLOR_WITH_LOCAL_EDIT": "DERIVED"}


def relation_open(rs, unit_map=None):
    """Кандидаты родства, которые могут сделать кадр не одиночным: производная сторона перекраски, сосед."""
    unit_map = unit_map or RELATION_UNIT
    return [r for r in rs if r["kind"] == "FIXED_NEIGHBOUR" or
            (r["kind"] in unit_map and r["side"] == "derived")]


def route(a, sk, meta, use_r2=True, use_r7=True, unit_map=None):
    """(маршрут, правило, улика) по оси A и метаданным. Родство (V4_R1) - если в meta есть relations."""
    unit_map = unit_map or RELATION_UNIT
    gen, fam_rel, fam_review, state, modular, cls, rels = meta
    g = gen.get(a, {})
    blockers = (g.get("blockers") or "").split()
    rel = g.get("relation", "")
    if sk == "TERRAIN_RELIEF":
        return "EXCLUDE", "R1", "A " + sk
    if sk == "NOT_OBJECT" and use_r2:
        return "EXCLUDE", "R2", "A " + sk
    cand = relation_open(rels.get(a, []), unit_map) if rels is not None else []
    ver = [r for r in cand if r.get("verified") and r["kind"] in unit_map]
    if ver:
        return unit_map[ver[0]["kind"]], "R0v", "%s %s (подтверждено)" % (ver[0]["kind"], ver[0]["relative"])
    if a in state or cls.get(a) == "state_variant":
        return "STATE_VARIANT", "R3", "state_variants / class_decisions"
    if rel in ("recolor", "mirror") or fam_rel.get(a, "canonical") not in ("canonical", "alternate_view"):
        return "DERIVED", "R4", "relation %s" % (rel or fam_rel.get(a))
    if g.get("kind") == "составной" or cls.get(a) == "part_fragment":
        return "COMPOSITE_PART", "R5", "kind %s, class %s" % (g.get("kind", "-"), cls.get(a, "-"))
    if a in modular or cls.get(a) == "structural_modular":
        return "STRUCTURAL_MODULAR", "R6", "modular_objects / class_decisions"
    opened = [b for b in blockers if b.split(":")[0] in OPEN_BLOCKERS]
    if a in fam_review:
        opened.append("review семейства")
    if rel == "alternate_view" or fam_rel.get(a) == "alternate_view":
        opened.append("alternate_view")
    if opened and use_r7:
        return "REVIEW", "R7", " ".join(opened)
    if rels is not None:
        if cand:
            return "REVIEW", "R7r", "; ".join("%s %s %s" % (r["kind"], r["level"], r["relative"]) for r in cand)
        if sk == "OBJECT_PART":
            return "REVIEW", "R8a", "OBJECT_PART, подтверждённой одиночности нет"
    if sk in ("OBJECT", "OBJECT_PART"):
        return "STANDALONE_RENDER", "R8", "нет более сильного родства" + (" (открыто: %s)" % " ".join(opened)
                                                                           if opened else "")
    return "REVIEW", "R9", "A " + (sk or "-")


def score(rows):
    closed = [r for r in rows if r["ref_render_unit"] != "open"]
    decided = [r for r in closed if r["rule_unit"] != "REVIEW"]
    ok = sum(r["rule_unit"] == r["ref_render_unit"] for r in decided)
    return {"n": len(rows), "ref_closed": len(closed), "decided": len(decided), "correct": ok,
            "routing_accuracy": ir.rate(ok, len(decided)), "coverage": ir.rate(len(decided), len(closed)),
            "dangerous_false_standalone": sum(r["rule_unit"] == "STANDALONE_RENDER" and
                                              r["ref_render_unit"] in ir.DANGEROUS_REF for r in rows),
            "overconservative_routing": sum(r["ref_render_unit"] == "STANDALONE_RENDER" and
                                            r["rule_unit"] in ir.OVERCONSERVATIVE for r in rows),
            "review": sum(r["rule_unit"] == "REVIEW" for r in rows),
            "review_ref_closed": sum(r["rule_unit"] == "REVIEW" for r in closed)}


def run(out=OUT):
    d = load_rules(out)
    inp = d["inputs"]
    spec = ir.load_spec(os.path.dirname(inp["spec_v3"]))
    sem = {r["asset_id"]: r for r in ir.read_tsv(inp["semantic"])}
    ref = {r["asset_id"]: r for r in ir.read_tsv(inp["reference"])}
    meta = metadata(inp)
    v3 = {}
    v3p = os.path.join(os.path.dirname(inp["semantic"]), "report.json")
    if os.path.exists(v3p):
        v3 = {r["asset_id"]: r for r in ir.load_json(v3p)["rows"]}

    def build(use_r2=True, use_r7=True):
        rows = []
        for a in spec["assets"]:
            sk = sem.get(a, {}).get("semantic_kind", "")
            u, rule, why = route(a, sk, meta, use_r2, use_r7)
            rr = ref.get(a, {}).get("ref_render_unit") or "open"
            rows.append({"asset_id": a, "semantic_kind": sk, "ref_semantic_kind": ref.get(a, {}).get(
                "ref_semantic_kind") or "open", "rule_unit": u, "rule": rule, "why": why, "ref_render_unit": rr,
                "human_unit_v3": sem.get(a, {}).get("render_unit", ""),
                "v2_mismatch": bool(v3.get(a, {}).get("v2_mismatch"))})
        return rows

    rows = build()
    total = score(rows)
    g = d["gates"]
    checks = {"dangerous_false_standalone = 0": total["dangerous_false_standalone"] <= g["dangerous_false_standalone_max"],
              "routing_accuracy >= %.2f" % g["routing_accuracy_min"]:
                  total["routing_accuracy"] is not None and total["routing_accuracy"] >= g["routing_accuracy_min"]}
    mism = [r for r in rows if r["v2_mismatch"]]
    sens = {"R2 выключен (NOT_OBJECT -> REVIEW)": score(build(use_r2=False)),
            "R7 выключен (открытый вопрос не мешает одиночному)": score(build(use_r7=False))}
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "rules_sha256": d["sha256"], "total": total,
           "checks": checks, "passed": all(checks.values()), "sensitivity": sens,
           "v2_mismatches": {"n": len(mism), "resolved": sum(r["rule_unit"] == r["ref_render_unit"] for r in mism),
                             "review": sum(r["rule_unit"] == "REVIEW" for r in mism)},
           "rules_fired": dict(Counter(r["rule"] for r in rows)), "rows": rows}
    ir.dump_json(os.path.join(out, "report.json"), res)
    mark = lambda r: ("**ОПАСНО**" if r["rule_unit"] == "STANDALONE_RENDER" and r["ref_render_unit"] in ir.DANGEROUS_REF
                      else "сверхосторожно" if r["ref_render_unit"] == "STANDALONE_RENDER" and
                      r["rule_unit"] in ir.OVERCONSERVATIVE
                      else "-" if r["ref_render_unit"] == "open" or r["rule_unit"] == "REVIEW"
                      else "да" if r["rule_unit"] == r["ref_render_unit"] else "**нет**")
    t = total
    ver = d.get("version", "V4")
    L = ["# ROUTING_RULES_%s - маршрут правилами на 28 предметах (диагностика)" % ver, "",
         "правила %s; ось A - ответы Vitali V3; эталон - reference_v2.tsv (агент); не слепо." % d["sha256"][:12], "",
         "## Ворота", "", "| показатель | значение | ворота | итог |", "|---|---|---|---|",
         "| DANGEROUS_FALSE_STANDALONE | %d | 0 | %s |" % (t["dangerous_false_standalone"],
                                                        "PASS" if checks["dangerous_false_standalone = 0"] else "FAIL"),
         "| точность маршрута (решено правилами) | %s (%d из %d) | >= 0.90 | %s |" % (
             t["routing_accuracy"], t["correct"], t["decided"],
             "PASS" if checks["routing_accuracy >= %.2f" % g["routing_accuracy_min"]] else "FAIL"),
         "", "Итог: **%s**." % ("PASS" if res["passed"] else "FAIL"), "",
         "| ещё | значение |", "|---|---|",
         "| охват: решено правилами из закрытых в эталоне | %s (%d из %d) |" % (t["coverage"], t["decided"],
                                                                            t["ref_closed"]),
         "| REVIEW всего / при закрытом эталоне | %d / %d |" % (t["review"], t["review_ref_closed"]),
         "| OVERCONSERVATIVE_ROUTING | %d |" % t["overconservative_routing"],
         "| расхождения V2: маршрут правилами совпал / REVIEW | %d / %d из %d |" % (
             res["v2_mismatches"]["resolved"], res["v2_mismatches"]["review"], res["v2_mismatches"]["n"]),
         "| сработали правила | %s |" % ", ".join("%s %d" % kv for kv in sorted(res["rules_fired"].items())), "",
         "## Чувствительность (не итог)", "",
         "| вариант | точность | решено | опасных | сверхосторожных | REVIEW |", "|---|---|---|---|---|---|"]
    for k, s in sens.items():
        L.append("| %s | %s | %d из %d | %d | %d | %d |" % (k, s["routing_accuracy"], s["decided"], s["ref_closed"],
                                                          s["dangerous_false_standalone"],
                                                          s["overconservative_routing"], s["review"]))
    L += ["", "## По предметам", "",
          "| предмет | A (Vitali) | правило | маршрут правилами | эталон B | человек V3 | сверка | улика |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["asset_id"], r["semantic_kind"], r["rule"], r["rule_unit"], r["ref_render_unit"], r["human_unit_v3"],
            mark(r), r["why"]))
    with open(os.path.join(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["freeze", "run"])
    ap.add_argument("--version", choices=["V4", "V4_R1"], default="V4",
                    help="V4_R1 - плюс родство relation-discovery-v1 и OBJECT_PART -> REVIEW (своя папка)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    os.chdir(ROOT)
    out = a.out or (OUT_R1 if a.version == "V4_R1" else OUT)
    if a.cmd == "freeze":
        freeze(out, version=a.version)
    else:
        run(out)


if __name__ == "__main__":
    main()
