#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALIGNED_RECOLOR_BOUNDARY_VALIDATION_V1 - слепая проверка полосы границ AR1 0.50-0.80 (специалист 02.10, передал
Vitali в чате, docs/DECISIONS.md). CPU, детекторы только вызываются.

Вопрос: строг ли порог границ AR_BORDER 0.80 для класса сдвинутой перекраски. В V5_COMPONENT_VALIDATION_V1 пары,
не прошедшие ТОЛЬКО границы, в полосе 0.50-0.80 оказались связаны 7 из 7 закрытых - этого мало. Здесь независимая
выборка по всему пулу, без особого случая KITSUNE:

  BAND_70 / BAND_60 / BAND_50 - AR1: сдвиг не нулевой, прошёл силуэт, функцию цвета, цвета основы и остаток, не
      прошёл только границы, и границы в [0.70, 0.80) / [0.60, 0.70) / [0.50, 0.60) - то, что взял бы новый порог;
  BAND_HARD_NEG  - выровнен со сдвигом (силуэт >= 0.92), границы в той же полосе, но не прошёл ещё и функцию цвета,
      цвета основы или остаток;
  BAND_LOOKALIKE - силуэт после сдвига ниже 0.92 (кандидат префильтра), границы в той же полосе;
  ANCHOR_TRIGGER - срабатывание AR1 (границы >= 0.80), опора для сравнения.

Судьям не показывается ничего, кроме пакета V4 (relation_truth_v2.write_pack, JUDGE.md V4): ни очков границ, ни
слоя, ни причины отбора, ни результата детектора, ни KITSUNE. Два независимых судьи на пару, эталон -
tv.combine_pair с авторитетом.

Исключено: кадры наборов 80 кадров holdout V4, кадры истины v2, кадры и пары пула V4 (как v5_component_validation),
плюс все пары, уже судимые в V5_COMPONENT_VALIDATION_V1. На исходный кадр одна пара, кадр в выборке один раз, пара
наборов один раз в слое; просматривается весь пул.

Правило решения - до сканирования, в FREEZE.json (специалист: порог выбирается по устройству проверки, а не так,
чтобы захватить KITSUNE 0.65-0.74):
  подполосы проверяются сверху вниз: [0.70, 0.80), затем [0.60, 0.70), затем [0.50, 0.60); подполоса проходит,
  если закрыто не меньше STEP_N_MIN пар её слоя BAND_* и точность существования связи по закрытым >= 0.95;
  проверка останавливается на первой непрошедшей. Новый порог = нижний край последней прошедшей подполосы; если не
  прошла верхняя - AR1 остаётся диагностикой, KITSUNE не решён, V5 не морозится.
Новый порог применяется только в следующей версии (ALIGNED_RECOLOR_V2), V5 и AR1 не переписываются. Подтип
производного, нижняя граница Уилсона и отрицательные слои - диагностика.

Команды: freeze, scan, pack, check, lockref, report. VERIFIED ставит только человек.
"""
import argparse
import math
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aligned_recolor_v1 as ar                   # noqa: E402
import identity_routing as ir                     # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402
import relation_taxonomy as tx                    # noqa: E402
import v5_component_validation as cv              # noqa: E402

ENC = ir.ENC
PROFILE = "ALIGNED_RECOLOR_BOUNDARY_VALIDATION_V1"
OUT = os.path.join(ir.PROBES, "ar-boundary-validation")
SEED = "ar-boundary-validation-2026-10-02"
BATCH_PAIRS = 40
GATE = 0.95
STEP_N_MIN = 20
BAND = (0.50, 0.80)
STEPS = [("BAND_70", 0.70, 0.80), ("BAND_60", 0.60, 0.70), ("BAND_50", 0.50, 0.60)]
# слой -> (сколько взять, описание); порядок - приоритет при выборе одной пары на исходный кадр
STRATA = [
    ("BAND_70", 50, "AR1: не прошёл только границы, границы [0.70, 0.80)"),
    ("BAND_60", 50, "AR1: не прошёл только границы, границы [0.60, 0.70)"),
    ("BAND_50", 50, "AR1: не прошёл только границы, границы [0.50, 0.60)"),
    ("BAND_HARD_NEG", 40, "выровнен со сдвигом, границы в полосе, не прошёл ещё функцию цвета, цвета или остаток"),
    ("BAND_LOOKALIKE", 30, "силуэт после сдвига ниже порога, границы в полосе"),
    ("ANCHOR_TRIGGER", 30, "срабатывание AR1, границы >= 0.80"),
]
QUOTA = {s: n for s, n, _d in STRATA}
CODE = ["tools/hdart/ar_boundary_validation.py", "tools/test_ar_boundary_validation.py",
        "tools/hdart/aligned_recolor_v1.py", "tools/hdart/v5_component_validation.py"]


def p(*a):
    return os.path.join(OUT, *a)


def order(s, salt=SEED):
    return cv.tx_order(s, salt)


def spec():
    return {"profile": PROFILE, "decision": "специалист 02.10, передал Vitali в чате (docs/DECISIONS.md 2026-10-02)",
            "strata": [{"name": s, "quota": n, "what": d} for s, n, d in STRATA], "band": list(BAND),
            "seed": SEED, "batch_pairs": BATCH_PAIRS, "judges": 2,
            "decision_rule": {"steps": [[s, lo, hi] for s, lo, hi in STEPS], "order": "сверху вниз, до первой "
                              "непрошедшей", "metric": "точность существования связи по закрытым парам слоя",
                              "gate": GATE, "step_n_min": STEP_N_MIN,
                              "threshold": "нижний край последней прошедшей подполосы; не прошла верхняя - AR1 "
                                           "остаётся диагностикой",
                              "applies_to": "только следующая версия ALIGNED_RECOLOR_V2; V5 и AR1 не переписываются"},
            "diagnostic": ["подтип производного", "нижняя граница Уилсона", "BAND_HARD_NEG", "BAND_LOOKALIKE",
                           "ANCHOR_TRIGGER"],
            "sampling": "весь пул по хэшу; на исходный кадр не больше одной пары, кадр в выборке один раз; в слое "
                        "пара наборов один раз; слой - первый по порядку STRATA, где ещё нужна пара",
            "exclusions": "как v5_component_validation (наборы 80 кадров holdout V4, истина v2, пул V4) плюс пары "
                          "V5_COMPONENT_VALIDATION_V1",
            "hidden_from_judges": ["очки границ", "слой", "причина отбора", "результат детектора", "KITSUNE"],
            "subtype_rule": "ярлык у обоих судей - да, ни у одного - нет, у одного - OPEN; существование - "
                            "relation_truth_v2.combine_pair с авторитетом",
            "ar1_params": ar.PARAMS}


def code_sha():
    return {c: v2.file_sha(c) for c in CODE}


def do_freeze():
    if os.path.exists(p("FREEZE.json")):
        raise SystemExit("уже заморожено: %s" % p("FREEZE.json"))
    if os.path.exists(p("key.json")):
        raise SystemExit("выборка уже есть - заморозка после неё не имеет смысла")
    os.makedirs(OUT, exist_ok=True)
    ir.dump_json(p("FREEZE.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec": spec(),
                                    "code_sha256": code_sha()})
    print("заморожено: %s, sha256 %s" % (p("FREEZE.json"), v2.file_sha(p("FREEZE.json"))[:12]))


def check_freeze():
    import json
    if not os.path.exists(p("FREEZE.json")):
        raise SystemExit("нет FREEZE.json - сначала freeze")
    fz = ir.load_json(p("FREEZE.json"))
    bad = [c for c, s in fz["code_sha256"].items() if v2.file_sha(c) != s]
    if json.dumps(fz["spec"], sort_keys=True, ensure_ascii=False) != \
            json.dumps(json.loads(json.dumps(spec(), ensure_ascii=False)), sort_keys=True, ensure_ascii=False):
        bad.append("spec")
    if bad:
        raise SystemExit("изменено после заморозки: %s" % ", ".join(bad))
    return fz


# ---------------------------------------------------------------- слой пары

def stratum(sc, gen_a, gen_b):
    """Слой пары по очкам AR1 или None. Нулевой сдвиг и общий силуэт - не AR1, слоя нет."""
    if sc["shift"] == [0, 0] or gen_a > ar.AR_GENERIC or gen_b > ar.AR_GENERIC:
        return None
    ok, why = ar.passes(sc, gen_a, gen_b)
    if ok:
        return "ANCHOR_TRIGGER"
    b = sc["topology"]
    if not BAND[0] <= b < BAND[1]:
        return None
    if sc["silhouette"] < ar.AR_IOU:
        return "BAND_LOOKALIKE"
    if len(why) == 1 and why[0].startswith("границ"):
        for s, lo, hi in STEPS:
            if lo <= b < hi:
                return s
    return "BAND_HARD_NEG"


def items_of(ctx, si, a):
    a = a.upper()
    A = ctx.rgba(a)
    if A is None or si.generic(a) > ar.AR_GENERIC:
        return []
    out = []
    skip = {a} | set(ctx.ix.exact(a)) | set(ctx.ix.mirror(a))
    for b in ar.candidates(ctx, a):
        if b in skip:
            continue
        B = ctx.rgba(b)
        if B is None or B.shape != A.shape:
            continue
        sc = ar.scores(A, B)
        st = stratum(sc, si.generic(a), si.generic(b))
        if st:
            out.append((st, b.upper(), {"scores": sc, "why": ar.passes(sc, si.generic(a), si.generic(b))[1]}))
    return out


def pick(cands, need, used):
    by = defaultdict(list)
    for st, b, info in cands:
        by[st].append((b, info))
    for st, _n, _d in STRATA:
        if need.get(st, 0) <= 0:
            continue
        for b, info in sorted(by.get(st, []), key=lambda x: order(x[0], SEED + "|" + st)):
            if b not in used:
                return st, b, info
    return None


def do_scan():
    check_freeze()
    if os.path.exists(p("key.json")):
        raise SystemExit("выборка уже есть: %s" % p("key.json"))
    import relation_holdout_v4 as hv
    ctx = hv.ctx_v3()
    si = v4.SetIndex(ctx)
    ex_sets, ex_frames, ex_pairs = cv.exclusions()
    ex_pairs |= {tx.pk(it["a"], it["b"]) for it in ir.load_json(cv.p("key.json"))["items"]}
    t0 = time.time()
    placed = cv.placed_frames(ctx)
    mk = set(ctx.masks.pos)
    pool = sorted((k for k in placed if k in mk and not cv.excluded(k, ex_sets, ex_frames)), key=order)
    print("кадров на картах %d, в пуле после исключений %d, %.0f с" % (len(placed), len(pool), time.time() - t0),
          flush=True)
    need, used, setpairs = dict(QUOTA), set(), defaultdict(set)
    items, popul, seen_pairs = [], Counter(), defaultdict(set)
    seen = 0
    for a in pool:
        if all(v <= 0 for v in need.values()):
            break
        seen += 1
        ok = []
        for st, b, info in items_of(ctx, si, a):
            k = tx.pk(a, b)
            if cv.excluded(b, ex_sets, ex_frames) or k in ex_pairs:
                continue
            if k not in seen_pairs[st]:
                seen_pairs[st].add(k)
                popul[st] += 1
            if frozenset((v2.split(a)[0], v2.split(b)[0])) in setpairs[st]:
                continue
            ok.append((st, b, info))
        if a not in used:
            got = pick(ok, need, used)
            if got:
                st, b, info = got
                items.append({"a": a, "b": b, "stratum": st, "info": info})
                need[st] -= 1
                used |= {a, b}
                setpairs[st].add(frozenset((v2.split(a)[0], v2.split(b)[0])))
        if seen % 500 == 0:
            print("просмотрено %d из %d, %.0f с: %s" % (seen, len(pool), time.time() - t0,
                                                        {s: QUOTA[s] - need[s] for s in QUOTA}), flush=True)
    lst = sorted(items, key=lambda it: order(it["a"] + "|" + it["b"], SEED + "|q"))
    for n, it in enumerate(lst, 1):
        it["q"] = "B%03d" % n
        if order("swap" + it["q"])[0] in "01234567":
            it["a"], it["b"], it["swapped"] = it["b"], it["a"], True
    key = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE,
           "freeze_sha256": v2.file_sha(p("FREEZE.json")), "sources_seen": seen, "pool": len(pool),
           "population": dict(popul), "taken": dict(Counter(it["stratum"] for it in lst)),
           "short": {s: max(0, need[s]) for s in QUOTA}, "items": lst,
           "note": "ключ вне пакета: слой, очки и причина отбора судье не показываются"}
    ir.dump_json(p("key.json"), key)
    print("выборка: %d пар %s; просмотрено %d из %d; недобор %s" % (
        len(lst), key["taken"], seen, len(pool), {s: v for s, v in key["short"].items() if v}))


# ---------------------------------------------------------------- пакет, проверка, эталон (как v5_component_validation)

def do_pack():
    import relation_truth_v2 as tv
    check_freeze()
    key = ir.load_json(p("key.json"))
    if os.path.exists(p("pack.lock.json")):
        raise SystemExit("пакет уже собран: %s" % p("pack.lock.json"))
    n = len(key["items"])
    tv.write_pack(OUT, [{"q": it["q"], "a": it["a"], "b": it["b"]} for it in key["items"]],
                  2 * math.ceil(n / BATCH_PAIRS), SEED, judges_per_item=2)


def do_check():
    import relation_truth_v2 as tv
    lock = ir.load_json(p("pack.lock.json"))
    res, bad = tv.read_by_judge(OUT, lock)
    done, todo = [], []
    for i, qs in enumerate(lock["batches"]):
        if not os.path.exists(p("answers", "judge_%d.tsv" % (i + 1))):
            todo.append(i + 1)
            continue
        miss = [q for q in qs if not any(x["judge"] == i + 1 and x["answered"] for x in res[q])]
        done.append(i + 1)
        if miss:
            print("judge_%d: без ответа %d: %s" % (i + 1, len(miss), miss[:5]))
    print("ошибки формата:", bad[:10])
    print("сдано %d из %d; не сдано: %s" % (len(done), len(lock["batches"]), todo))
    return not bad and not todo


def do_lockref():
    import relation_truth_v2 as tv
    import routing_model_v8 as v8
    check_freeze()
    if os.path.exists(p("reference.lock.json")):
        raise SystemExit("эталон уже заморожен")
    key, lock = ir.load_json(p("key.json")), ir.load_json(p("pack.lock.json"))
    js, bad = tv.read_by_judge(OUT, lock)
    ctx = v3.Ctx(index=v2.load_index(v2.OUT))
    mcd = v8.Mcd(ctx.world)
    rows, missing = [], []
    for it in key["items"]:
        got = [x for x in js.get(it["q"], []) if x["answered"]]
        if len(got) < 2:
            missing.append(it["q"])
            continue
        au = tv.authority(ctx, mcd, it["a"], it["b"])
        ex, closed, opn = tv.combine_pair(got[0]["taken"], got[1]["taken"], bool(au))
        rows.append({"q": it["q"], "a": it["a"], "b": it["b"], "existence": ex, "closed": sorted(closed),
                     "open": sorted(opn), "authority": au, "judge1": sorted(got[0]["taken"]),
                     "judge2": sorted(got[1]["taken"]), "raw1": got[0]["raw"], "raw2": got[1]["raw"]})
    if bad or missing:
        raise SystemExit("ответы неполны или с ошибками: %s; без двух ответов: %s" % (bad[:10], missing[:10]))
    ir.dump_json(p("truth.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "pairs": rows})
    ir.dump_json(p("reference.lock.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                            "key_sha256": v2.file_sha(p("key.json")),
                                            "pack_sha256": lock["pack_sha256"],
                                            "truth_sha256": v2.file_sha(p("truth.json"))})
    print("эталон заморожен: пар %d, %s" % (len(rows), dict(Counter(r["existence"] for r in rows))))


# ---------------------------------------------------------------- подсчёт и правило решения

def wilson_low(ok, n, z=1.96):
    if not n:
        return None
    ph = ok / n
    return (ph + z * z / (2 * n) - z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def enrich(key, truth):
    T = {r["q"]: r for r in truth["pairs"]}
    rows = []
    for it in key["items"]:
        r = dict(T[it["q"]], stratum=it["stratum"], info=it["info"])
        r["exist"] = {"RELATED": "yes", "NONE": "no"}.get(r["existence"], "OPEN")
        r["derived"] = cv.subtype(r, cv.DERIVED_SUB)
        rows.append(r)
    return rows


def step_stats(rows, st):
    rs = [r for r in rows if r["stratum"] == st]
    v, n, ok, op = cv.prec(rs, "exist", "yes")
    dv, dn, dok, dop = cv.prec(rs, "derived", "yes")
    return {"value": v, "n": n, "ok": ok, "open": op, "wilson_low": wilson_low(ok, n),
            "derived": {"value": dv, "n": dn, "ok": dok, "open": dop},
            "status": "INSUFFICIENT_SAMPLE" if n < STEP_N_MIN else ("PASS" if v >= GATE else "FAIL")}


def decide(rows):
    """Правило из FREEZE.json: сверху вниз до первой непрошедшей. -> (шаги, порог или None)."""
    steps, thr = [], None
    for s, lo, hi in STEPS:
        x = dict(step_stats(rows, s), step=s, lo=lo, hi=hi)
        steps.append(x)
        if x["status"] != "PASS":
            break
        thr = lo
    tested = {x["step"] for x in steps}
    for s, lo, hi in STEPS:
        if s not in tested:
            steps.append(dict(step_stats(rows, s), step=s, lo=lo, hi=hi, not_tested=True))
    return steps, thr


def do_report():
    check_freeze()
    lk = ir.load_json(p("reference.lock.json"))
    if v2.file_sha(p("truth.json")) != lk["truth_sha256"] or v2.file_sha(p("key.json")) != lk["key_sha256"]:
        raise SystemExit("эталон или ключ изменены после заморозки")
    key, truth = ir.load_json(p("key.json")), ir.load_json(p("truth.json"))
    rows = enrich(key, truth)
    steps, thr = decide(rows)
    other = {s: step_stats(rows, s) for s in ("BAND_HARD_NEG", "BAND_LOOKALIKE", "ANCHOR_TRIGGER")}
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE,
           "freeze_sha256": v2.file_sha(p("FREEZE.json")), "truth_sha256": lk["truth_sha256"],
           "population": key["population"], "taken": key["taken"], "short": key["short"],
           "steps": steps, "threshold": thr,
           "verdict": ("AR1 border threshold supported from %.2f (ALIGNED_RECOLOR_V2 candidate)" % thr
                       if thr is not None else "AR1 remains diagnostic"),
           "diagnostic_strata": {s: {k: v for k, v in x.items() if k != "status"} for s, x in other.items()},
           "rows": [{k: r[k] for k in ("q", "a", "b", "stratum", "existence", "closed", "open", "exist",
                                       "derived")} | {"border": r["info"]["scores"]["topology"],
                                                      "shift": r["info"]["scores"]["shift"],
                                                      "fmax": r["info"]["scores"]["fmax"]} for r in rows]}
    ir.dump_json(p("report.json"), res)
    write_md(res)
    print(res["verdict"])


def f3(x):
    return "-" if x is None else ("%.3f" % x if isinstance(x, float) else str(x))


def write_md(res):
    L = ["# ALIGNED_RECOLOR_BOUNDARY_VALIDATION_V1", "",
         "Слепая проверка полосы границ AR1 0.50–0.80 (FREEZE %s). Правило решения зафиксировано до сканирования. "
         "Порог AR1 0.80 в V5 не меняется." % res["freeze_sha256"][:12], "",
         "Итог: **%s**." % res["verdict"], "",
         "## Подполосы (сверху вниз, до первой непрошедшей)", "",
         "| подполоса | границы | точность связи | закрыто | верно | OPEN | Уилсон ниж. | производный | итог |",
         "|---|---|---|---|---|---|---|---|---|"]
    for x in res["steps"]:
        d = x["derived"]
        L.append("| %s | %.2f–%.2f | %s | %d | %d | %d | %s | %s (%d/%d) | %s |" % (
            x["step"], x["lo"], x["hi"], f3(x["value"]), x["n"], x["ok"], x["open"], f3(x["wilson_low"]),
            f3(d["value"]), d["ok"], d["n"], "не проверялась (диагностика)" if x.get("not_tested") else x["status"]))
    L += ["", "## Диагностика", "", "| слой | доля связанных | закрыто | связано | OPEN | производный |",
          "|---|---|---|---|---|---|"]
    for s, x in res["diagnostic_strata"].items():
        d = x["derived"]
        L.append("| %s | %s | %d | %d | %d | %s (%d/%d) |" % (s, f3(x["value"]), x["n"], x["ok"], x["open"],
                                                             f3(d["value"]), d["ok"], d["n"]))
    L += ["", "Численность слоёв в просмотренном пуле: %s; взято: %s; недобор: %s." % (
        res["population"], res["taken"], {s: v for s, v in res["short"].items() if v} or "нет"), "",
        "VERIFIED ставит только человек."]
    with open(p("report.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["freeze", "scan", "pack", "check", "lockref", "report"])
    a = ap.parse_args()
    {"freeze": do_freeze, "scan": do_scan, "pack": do_pack, "check": do_check, "lockref": do_lockref,
     "report": do_report}[a.cmd]()


if __name__ == "__main__":
    main()
