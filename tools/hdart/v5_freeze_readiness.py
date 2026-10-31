#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V5_FREEZE_READINESS_V2 - условия заморозки V5 (специалист 02.10, передал Vitali в чате). CPU, чтение.

V2 (второе решение специалиста 02.10): настоящие ворота безопасности - POST_REVIEW_DANGEROUS (post_review_safety):
кандидат, которого независимый закрытый эталон подтвердил как NONE, не имеет права спасать кадр. Опасные
считаются дважды - PRE_REVIEW_DANGEROUS и POST_REVIEW_DANGEROUS, для заморозки нужны оба нуля. Итог тремя
строками: legacy gates (шесть ворот V5_PREP), assembly validation (две точности слепой проверки), freeze readiness.

Пересчёт тех же 80 кадров holdout V4 замороженным кодом V5_PREP (relation_discovery_v5: claims, evaluate) плюс
итог слепой проверки V5_COMPONENT_VALIDATION_V1. Пороги и детекторы не меняются, новых доводов нет. Модуль ничего
не решает за человека: VERIFIED ставит только человек.

Что считается:
  ворота V5 (как в V5_PREP): опасных 0, существование >= 0.95, производный >= 0.70, состояние >= 0.70,
      composite_discovery_recall (STRONG + CANDIDATE) >= 0.70, авто >= 0.95;
  слепая проверка: ASSEMBLY candidate existence precision >= 0.95, ASSEMBLY STRONG typed precision >= 0.95;
  диагностика (не ворота): composite_strong_recall, candidate composite-subtype precision, STRONG existence
      precision, AR1;
  KITSUNE двумя строками: safety (опасен ли кадр) и true relation discovery (есть ли довод на истинной паре);
  безопасность после ревью (ворота): PRE_REVIEW_DANGEROUS и POST_REVIEW_DANGEROUS, закрытый NONE берётся из
      эталона holdout V4 и эталона слепой проверки V5_COMPONENT_VALIDATION_V1;
  чувствительность (не ворота): те же ворота, если оставить из новых доводов только STRONG.

    py -3.13 tools/hdart/v5_freeze_readiness.py      -> probes/v5-freeze-readiness/report.json, report.md
"""
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir                     # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v5 as rd5               # noqa: E402
import relation_holdout_v4 as hv                  # noqa: E402
import relation_taxonomy as tx                    # noqa: E402
import post_review_safety as prs                  # noqa: E402
import v5_component_validation as cv              # noqa: E402

ENC = ir.ENC
PROFILE = "V5_FREEZE_READINESS_V2"
OUT = os.path.join(ir.PROBES, "v5-freeze-readiness")
KITSUNE = "KITSUNE:15"
GATE = 0.95
FREEZE_GATES = ["dangerous_creative_standalone", "relation_existence_precision", "derived_recolor_discovery",
                "state_discovery", "true_composite_recall", "automatic_action_precision"]


def p(*a):
    return os.path.join(OUT, *a)


def precision(rows, field, good="yes"):
    """Точность по закрытым: (значение, закрыто, верно, OPEN)."""
    closed = [r for r in rows if r[field] != "OPEN"]
    ok = sum(r[field] == good for r in closed)
    return (ok / len(closed) if closed else None), len(closed), ok, len(rows) - len(closed)


def validation():
    """Слепая проверка: четыре точности сборки по слоям asm_pos, без KNOWN80."""
    cv.check_freeze()
    lk = ir.load_json(cv.p("reference.lock.json"))
    if v2.file_sha(cv.p("truth.json")) != lk["truth_sha256"] or v2.file_sha(cv.p("key.json")) != lk["key_sha256"]:
        raise SystemExit("эталон или ключ слепой проверки изменены после заморозки")
    key, truth = ir.load_json(cv.p("key.json")), ir.load_json(cv.p("truth.json"))
    rows = cv.enrich(key, truth)
    pos = [r for r in rows if r["family"] == "asm_pos"]
    out = {}
    for lev in ("CANDIDATE", "STRONG"):
        rs = [r for r in pos if r["level"] == lev]
        for name, field in (("existence", "exist"), ("composite_subtype", "composite")):
            v, n, ok, op = precision(rs, field)
            out["%s_%s" % (lev.lower(), name)] = {"value": v, "n": n, "ok": ok, "open": op}
    by_pair = {tx.pk(r["a"], r["b"]): r for r in rows}
    return out, by_pair, rows


AR_BANDS = ((0.0, 0.5), (0.5, 0.65), (0.65, 0.8))
SAME_DRAWING = (0.94, 0.70)     # силуэт и функция цвета без сдвига - описание класса после просмотра, не правило
DEV_VERTICAL_FP = ("SEASUNK6:48", "SEASUNK6:49")


def band(x, bands):
    for lo, hi in bands:
        if lo <= x < hi:
            return "%.2f-%.2f" % (lo, hi)
    return ">=%.2f" % bands[-1][1]


def ar1_analysis(vrows):
    """AR1: срабатывания по сдвигу; «только границы» по полосам границ (подтип производного yes / no / OPEN)."""
    trig, border = Counter(), {}
    for r in vrows:
        sc = (r["info"] or {}).get("scores") or {}
        if r["stratum"] == "AR1_TRIGGER":
            trig[("shift %d" % min(abs(sc["shift"][0]) + abs(sc["shift"][1]), 3), r["derived"])] += 1
        if r["stratum"] == "AR1_BORDER_ONLY":
            b = band(sc["topology"], AR_BANDS)
            border.setdefault(b, Counter())[r["derived"]] += 1
            if sc["topology"] >= AR_BANDS[1][0]:
                border.setdefault("rows", []).append({"q": r["q"], "a": r["a"], "b": r["b"],
                                                      "border": sc["topology"], "fmax": sc["fmax"],
                                                      "shift": sc["shift"], "derived": r["derived"],
                                                      "closed": r["closed"]})
    out = {"triggers_by_shift": {"%s %s" % k: n for k, n in sorted(trig.items())},
           "border_only_by_band": {k: dict(v) for k, v in sorted(border.items()) if k != "rows"},
           "border_only_rows_ge_0.5": border.get("rows", [])}
    hi = [x for x in out["border_only_rows_ge_0.5"] if x["derived"] != "OPEN"]
    out["border_ge_0.5_closed"] = len(hi)
    out["border_ge_0.5_ok"] = sum(x["derived"] == "yes" for x in hi)
    return out


def vertical_analysis(vrows):
    """Вертикальные стопки ASM: признаки и истина; сходство рисунков без сдвига (ar.scores)."""
    import aligned_recolor_v1 as ar
    import relation_discovery_v3 as v3
    ctx = v3.Ctx(index=v2.load_index(v2.OUT))

    def sim(a, b):
        A, B = ctx.rgba(a), ctx.rgba(b)
        if A is None or B is None or A.shape != B.shape:
            return None, None
        s = ar.scores(A, B)
        return s["unshifted"], s["fmax"]
    out = []
    for r in vrows:
        if not r["vertical"]:
            continue
        sc = r["info"]["scores"]
        sil, fm = sim(r["a"], r["b"])
        out.append({"q": r["q"], "a": r["a"], "b": r["b"], "rule": r["info"].get("rule"), "level": r["level"],
                    "offset": sc["offset"], "xy": bool(sc["offset"][0] or sc["offset"][1]),
                    "struct": sc["struct"], "order": sc["order"], "mcd": sc["mcd"], "single": sc["single"],
                    "cross_set": r["a"].split(":")[0] != r["b"].split(":")[0], "silhouette": sil, "fmax": fm,
                    "same_drawing": sil is not None and sil >= SAME_DRAWING[0] and fm >= SAME_DRAWING[1],
                    "stratum": r["stratum"], "existence": r["existence"], "composite": r["composite"],
                    "closed": r["closed"], "open": r["open"]})
    sil, fm = sim(*DEV_VERTICAL_FP)
    dev = {"pair": list(DEV_VERTICAL_FP), "silhouette": sil, "fmax": fm,
           "same_drawing": sil is not None and sil >= SAME_DRAWING[0] and fm >= SAME_DRAWING[1]}
    blind = [x for x in out if x["stratum"] == "ASM_VERTICAL"]
    summ = {"n": len(blind), "existence": dict(Counter(x["existence"] for x in blind)),
            "composite": dict(Counter(x["composite"] for x in blind)),
            "same_drawing": dict(Counter(x["composite"] for x in blind if x["same_drawing"])),
            "other_drawing": dict(Counter(x["composite"] for x in blind if not x["same_drawing"]))}
    return {"rows": out, "dev_false_positive": dev, "summary": summ}


def blind_state(by_pair, a, b):
    r = by_pair.get(tx.pk(a, b))
    return None if r is None else {"q": r["q"], "existence": r["existence"], "closed": r["closed"],
                                   "open": r["open"]}


def kitsune(res, C, by_pair):
    """Две строки KITSUNE: безопасность и обнаружение истинной связи."""
    sc = {x["asset_id"].upper(): x for x in res["score"]}[KITSUNE]
    true_pairs = [(a, b, t) for a, b, t, _cs in res["pc"] if KITSUNE in (a.upper(), b.upper()) and t and
                  t[0] == "RELATED"]
    found = []
    for a, b, t in true_pairs:
        other = b if a.upper() == KITSUNE else a
        found.append({"pair": [KITSUNE, other.upper()], "truth": sorted(t[1]),
                      "claims": [c["group"] for c in C.pair(KITSUNE, other)]})
    held = []
    for c in C.of(KITSUNE):
        other = [x for x in c["pair"] if x != KITSUNE][0]
        held.append({"pair": c["pair"], "group": c["group"], "existence": c["existence"],
                     "detectors": sorted({e["detector"] + " " + e["rule"] for e in c["support"]}),
                     "blind": blind_state(by_pair, KITSUNE, other)})
    safe = not sc["danger"]
    discovered = bool(found) and all(x["claims"] for x in found)
    return {"safety": ("SAFE via REVIEW" if safe and not sc["creative"] else
                       "SAFE" if safe else "DANGEROUS"),
            "true_relation_discovery": "FOUND" if discovered else "MISSED",
            "true_pairs": found, "held_by": held, "creative": sc["creative"], "danger": sc["danger"]}


def gate_map(gates):
    return {g["gate"]: g for g in gates}


RENAME = {"true_composite_recall": "composite_discovery_recall",
          "dangerous_creative_standalone": "PRE_REVIEW_DANGEROUS"}


def overall(rows):
    sts = {r["status"] for r in rows}
    return "PASS" if sts == {"PASS"} else "FAIL" if "FAIL" in sts else "INCONCLUSIVE"


def readiness(G, V, post_dangerous):
    """Условия заморозки: ворота V5, POST_REVIEW_DANGEROUS, две точности слепой проверки.
    -> (строки, {legacy_gates, assembly_validation, post_review_safety, freeze_readiness})."""
    legacy, asm_rows = [], []
    for g in FREEZE_GATES:
        x = G[g]
        legacy.append({"cond": RENAME.get(g, g), "value": x["value"], "n": x["n"], "need": x["need"],
                       "status": x["status"], "part": "legacy"})
    post = {"cond": "POST_REVIEW_DANGEROUS", "value": post_dangerous, "n": G["dangerous_creative_standalone"]["n"],
            "need": 0, "status": "PASS" if post_dangerous == 0 else "FAIL", "part": "post_review"}
    for name, k in (("asm_candidate_existence_precision", "candidate_existence"),
                    ("asm_strong_typed_precision", "strong_composite_subtype")):
        x = V[k]
        st = "INSUFFICIENT_SAMPLE" if x["n"] < cv.N_MIN else ("PASS" if x["value"] >= GATE else "FAIL")
        asm_rows.append({"cond": name, "value": x["value"], "n": x["n"], "need": GATE, "status": st,
                         "part": "assembly"})
    rows = legacy + [post] + asm_rows
    return rows, {"legacy_gates": overall(legacy), "assembly_validation": overall(asm_rows),
                  "post_review_safety": post["status"], "freeze_readiness": overall(rows)}


def variant(rows_r, found3, found4, f5, keep, T, items, keys, h, fsets):
    edges = [e for e in f5["edges"] if keep(e)]
    C = rd5.claims(rows_r, found3, found4, {"edges": edges})
    return rd5.evaluate(rows_r, C, T, items, keys, h, fsets), C, len(f5["edges"]) - len(edges)


def summary(res):
    G = gate_map(res["gates"])
    comp = res["recall"]["composite"]
    return {"dangerous": sorted(res["dangerous"]), "gates": {g: G[g]["status"] for g in FREEZE_GATES},
            "composite_discovery_recall": comp.get("discovery_rate"),
            "composite_strong_recall": v2.rate(comp["strong"], comp["n"])}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    import relation_holdout_v4_ref as ref
    rd5.check_freeze()
    if not ref.do_verify(rd5.HOLD):
        raise SystemExit("замок эталона holdout V4 не цел")
    d, h = hv.load_freeze(rd5.HOLD), hv.load_holdout(rd5.HOLD)
    ch = hv.code_changed(d)
    if ch:
        raise SystemExit("замороженный код V4 изменён: %s" % ", ".join(ch))
    V, by_pair, vrows = validation()
    f5 = rd5.load_found5()
    T, _lk = hv.load_truth(rd5.HOLD)
    ans = {r["asset_id"]: r for r in ir.read_tsv(os.path.join(rd5.HOLD, "answers_vitali.tsv"))}
    keys = hv.keys_of(h)
    found3, found4 = hv.load_found(rd5.HOLD)
    base_r = hv.routing_base(rd5.HOLD, d, h)
    rows_r = hv.routing_rows(base_r, lambda a: ans.get(a, {}).get("semantic_kind", ""))
    items = ir.load_json(os.path.join(rd5.HOLD, "key.json"))["items"]
    args = (T, items, keys, h, base_r["fsets"])

    new, C5, _ = variant(rows_r, found3, found4, f5, lambda e: True, *args)
    frozen = ir.load_json(rd5.p("report.json"))
    control = [g["value"] for g in new["gates"]] == [g["value"] for g in frozen["gates"]]
    G = gate_map(new["gates"])
    comp = new["recall"]["composite"]
    none_pairs = prs.closed_none(
        ("holdout V4", [tuple(sorted(k)) + (t[0],) for k, t in T.items()]),
        ("V5 component validation", [(r["a"], r["b"], r["existence"]) for r in vrows]))
    pp, post = prs.pre_post(lambda C: rd5.evaluate(rows_r, C, *args), C5, none_pairs)
    if pp["PRE_REVIEW_DANGEROUS"] != len(new["dangerous"]):
        raise SystemExit("PRE_REVIEW_DANGEROUS не совпал с пересчётом V5_PREP")
    cond, verdict = readiness(G, V, pp["POST_REVIEW_DANGEROUS"])
    v_strong, _c, drop_s = variant(rows_r, found3, found4, f5, lambda e: e["level"] == "STRONG", *args)
    ks = kitsune(new, C5, by_pair)
    ks["post_review_safety"] = "DANGEROUS" if KITSUNE in post["dangerous"] else "SAFE"

    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE,
           "decision": "специалист 02.10, передал Vitali в чате (docs/DECISIONS.md 2026-10-02)",
           "v5_prep_freeze_sha256": hv.file_sha(rd5.p("FREEZE.json")),
           "found5_sha256": hv.file_sha(rd5.p("found5.json")),
           "validation_freeze_sha256": hv.file_sha(cv.p("FREEZE.json")),
           "validation_truth_sha256": hv.file_sha(cv.p("truth.json")),
           "control_equals_v5_prep_report": control,
           "freeze_conditions": cond, "verdict": verdict,
           "composite_discovery_recall": {"value": comp.get("discovery_rate"), "found": comp["discovery"],
                                          "n": comp["n"], "role": "gate >= 0.70"},
           "composite_strong_recall": {"value": v2.rate(comp["strong"], comp["n"]), "found": comp["strong"],
                                       "n": comp["n"], "role": "diagnostic"},
           "validation": V, "ar1": ar1_analysis(vrows), "vertical": vertical_analysis(vrows),
           "post_review": pp, "post_review_gates": summary(post),
           "kitsune": ks,
           "sensitivity": {"new_edges_strong_only": dict(summary(v_strong), dropped_edges=drop_s)}}
    os.makedirs(OUT, exist_ok=True)
    ir.dump_json(p("report.json"), res)
    write_md(res)
    print("legacy %s, assembly %s, post-review %s (PRE %d, POST %d) -> freeze readiness %s; контроль = V5_PREP: %s; "
          "KITSUNE: %s / post-review %s / %s" % (
              verdict["legacy_gates"], verdict["assembly_validation"], verdict["post_review_safety"],
              pp["PRE_REVIEW_DANGEROUS"], pp["POST_REVIEW_DANGEROUS"], verdict["freeze_readiness"], control,
              ks["safety"], ks["post_review_safety"], ks["true_relation_discovery"]))


def f3(x):
    return "-" if x is None else ("%.3f" % x if isinstance(x, float) else str(x))


def write_md(res):
    K = res["kitsune"]
    v = res["verdict"]
    L = ["# V5_FREEZE_READINESS_V2 — условия заморозки V5", "",
         "```", "V4 = frozen FAIL", "", "V5_PREP:",
         "legacy gates        = %s" % v["legacy_gates"], "assembly validation = %s" % v["assembly_validation"],
         "freeze readiness    = %s" % v["freeze_readiness"]]
    if res["post_review"]["POST_REVIEW_DANGEROUS"]:
        L += ["", "blocker:", "post-review dangerous = %d" % res["post_review"]["POST_REVIEW_DANGEROUS"]]
        for u in res["post_review"]["unmasked"]:
            L.append("asset: %s" % u["asset"])
        if K["true_relation_discovery"] == "MISSED":
            L.append("true relation missed (%s)" % "; ".join(
                "%s %s" % (" ~ ".join(x["pair"]), "/".join(x["truth"])) for x in K["true_pairs"]))
    L += ["```", "",
         "Решение: %s. Те же 80 кадров holdout V4, замороженный код V5_PREP (FREEZE %s, found5 %s) и эталон слепой "
         "проверки V5_COMPONENT_VALIDATION_V1 (FREEZE %s). Пороги не менялись, новых доводов нет. Контроль: "
         "пересчёт совпал с отчётом V5_PREP — %s." % (
             res["decision"], res["v5_prep_freeze_sha256"][:12], res["found5_sha256"][:12],
             res["validation_freeze_sha256"][:12], "да" if res["control_equals_v5_prep_report"] else "НЕТ"), "",
         "## Условия заморозки", "", "| условие | значение | n | нужно | итог |", "|---|---|---|---|---|"]
    for r in res["freeze_conditions"]:
        L.append("| %s | %s | %s | %s | %s |" % (r["cond"], f3(r["value"]), r["n"], r["need"], r["status"]))
    cd, cs = res["composite_discovery_recall"], res["composite_strong_recall"]
    P = res["post_review"]
    L += ["", "Итог условий: legacy gates **%s**, assembly validation **%s**, post-review safety **%s** — "
          "freeze readiness **%s**." % (v["legacy_gates"], v["assembly_validation"], v["post_review_safety"],
                                        v["freeze_readiness"]), "",
          "## Безопасность до и после ревью (post_review_safety)", "",
          "- PRE_REVIEW_DANGEROUS = **%d** %s" % (P["PRE_REVIEW_DANGEROUS"], ", ".join(P["pre_dangerous"])),
          "- POST_REVIEW_DANGEROUS = **%d** %s" % (P["POST_REVIEW_DANGEROUS"], ", ".join(P["post_dangerous"])),
          "", "После ревью удалены кандидаты на парах, которые закрытый независимый эталон подтвердил как NONE "
          "(%d): " % len(P["dropped_candidates"]) + "; ".join(
              "%s (%s, %s; %s)" % (" ~ ".join(d["pair"]), d["group"], ", ".join(d["detectors"]),
                                   "/".join(d["truth"])) for d in P["dropped_candidates"]) + ".",
          "Кандидаты на парах с OPEN эталоном остаются блокирующими. STRONG на парах closed NONE: %d." % len(
              P["strong_on_closed_none"]), ""]
    for u in P["unmasked"]:
        L.append("- %s после ревью опасен: его держал только %s" % (u["asset"], "; ".join(
            " ~ ".join(d["pair"]) for d in u["masked_by"])))
    L += ["",
          "## Составной — две метрики", "",
          "- composite_discovery_recall (STRONG + CANDIDATE) = **%s** (%d / %d) — ворота, нужно ≥ 0.70" % (
              f3(cd["value"]), cd["found"], cd["n"]),
          "- composite_strong_recall (только STRONG) = **%s** (%d / %d) — диагностика" % (
              f3(cs["value"]), cs["found"], cs["n"]), "",
          "## Слепая проверка ASSEMBLY (слои ASM_*, без KNOWN80)", "",
          "| точность | значение | закрыто | верно | OPEN | роль |", "|---|---|---|---|---|---|"]
    role = {"candidate_existence": "ворота ≥ 0.95", "strong_composite_subtype": "ворота ≥ 0.95",
            "candidate_composite_subtype": "диагностика", "strong_existence": "диагностика"}
    for k in ("candidate_existence", "candidate_composite_subtype", "strong_existence", "strong_composite_subtype"):
        x = res["validation"][k]
        L.append("| %s | %s | %d | %d | %d | %s |" % (k, f3(x["value"]), x["n"], x["ok"], x["open"], role[k]))
    L += ["", "## KITSUNE:15", "", "- KITSUNE safety (pre-review): **%s**" % K["safety"],
          "- KITSUNE safety (post-review): **%s**" % K["post_review_safety"],
          "- KITSUNE true relation discovery: **%s**" % K["true_relation_discovery"], "",
          "Истинные пары эталона V4: " + "; ".join("%s (%s): доводы %s" % (
              " ~ ".join(x["pair"]), "/".join(x["truth"]), "/".join(x["claims"]) or "нет") for x in K["true_pairs"]),
          "", "Доводы на кадре (что держит его вне creative standalone):", ""]
    for x in K["held_by"]:
        b = x["blind"]
        L.append("- %s, группа %s, %s, %s; слепая проверка: %s" % (
            " ~ ".join(x["pair"]), x["group"], x["existence"], ", ".join(x["detectors"]),
            "%s %s %s" % (b["q"], b["existence"], "/".join(b["closed"]) or "-") if b else "не проверялась"))
    A = res["ar1"]
    L += ["", "## AR1 (диагностика, порог границ 0.80 не меняется)", "",
          "Срабатывания по сдвигу |dx|+|dy|, подтип производного: " + "; ".join(
              "%s: %d" % (k, n) for k, n in A["triggers_by_shift"].items()), "",
          "«Только границы» (всё прочее прошло) по полосам границ: " + "; ".join(
              "%s: %s" % (k, ", ".join("%s %d" % kv for kv in sorted(v.items())))
              for k, v in A["border_only_by_band"].items()), "",
          "Полоса 0.50–0.80: закрыто %d, производный верен %d. Строки:" % (
              A["border_ge_0.5_closed"], A["border_ge_0.5_ok"]), ""]
    for x in A["border_only_rows_ge_0.5"]:
        L.append("- %s %s ~ %s: границы %.2f, fmax %.2f, сдвиг %s — %s (%s)" % (
            x["q"], x["a"], x["b"], x["border"], x["fmax"], x["shift"], x["derived"], "/".join(x["closed"]) or "-"))
    Vt = res["vertical"]
    s, dv = Vt["summary"], Vt["dev_false_positive"]
    L += ["", "## Вертикальные стопки ASM", "",
          "Слепая выборка ASM_VERTICAL: %d; существование %s; составной %s." % (
              s["n"], s["existence"], s["composite"]),
          "Одинаковый рисунок без сдвига (силуэт ≥ %.2f и fmax ≥ %.2f, описание, не правило): составной %s; "
          "прочие: %s." % (SAME_DRAWING[0], SAME_DRAWING[1], s["same_drawing"], s["other_drawing"]),
          "Ложная стопка разработки %s: силуэт %s, fmax %s, одинаковый рисунок: %s." % (
              " ~ ".join(dv["pair"]), f3(dv["silhouette"]), f3(dv["fmax"]), "да" if dv["same_drawing"] else "нет"),
          "", "| q | пара | уровень | сдвиг | struct/ord/mcd | силуэт | fmax | существование | составной |",
          "|---|---|---|---|---|---|---|---|---|"]
    for x in Vt["rows"]:
        L.append("| %s | %s ~ %s | %s | %s | %s/%s/%s | %s | %s | %s | %s |" % (
            x["q"], x["a"], x["b"], x["level"], x["offset"], int(bool(x["struct"])), int(bool(x["order"])),
            int(bool(x["mcd"])), f3(x["silhouette"]), f3(x["fmax"]), x["existence"], x["composite"]))
    L += ["", "## Чувствительность (не ворота)", "",
          "| вариант | убрано доводов | опасные | composite discovery | composite strong | ворота |",
          "|---|---|---|---|---|---|"]
    for name, x in res["sensitivity"].items():
        L.append("| %s | %d | %s | %s | %s | %s |" % (
            name, x["dropped_edges"], ", ".join(x["dangerous"]) or "0", f3(x["composite_discovery_recall"]),
            f3(x["composite_strong_recall"]), ", ".join("%s %s" % (g, s) for g, s in x["gates"].items()
                                                        if s != "PASS") or "все PASS"))
    L += ["", "VERIFIED ставит только человек."]
    with open(p("report.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
