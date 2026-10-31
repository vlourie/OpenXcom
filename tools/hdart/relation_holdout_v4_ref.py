#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Эталон и итог holdout RELATION_DISCOVERY_V4 по правилам специалиста 02.10 (сообщение 5), рядом с замороженным
relation_holdout_v4.py - тот не меняется (его хэш в FREEZE.json).

  lockref  - истина из двух судей правилом relation_truth_v2.combine_pair (замороженный holdout_truth) плюс
             машинные факты, которые судьи не отменяют: побайтовая копия закрывает EXACT_COPY, побайтовое отражение -
             MIRRORED_VARIANT_PEER, ребро MCD - только существование (смысл ребра судят судьи). Пишет truth.json и
             reference.lock.json в формате, который читает замороженный report, и дописывает в замок хэши ключей пар,
             ответов судей, этого модуля и зависимостей, истины и решений OPEN/CLOSED, схему, версию и счётчики.
             Отказывает, если есть answers_vitali.tsv, ответы неполны или замок уже есть.
  verify   - пересобирает истину из ответов судей и сверяет каждый хэш и счётчик замка.
  posthoc  - после замороженного report: эффективные выборки ворот, итог с INSUFFICIENT_SAMPLE (N_MIN), диагностика
             компонентов triggered / helped / unnecessary / hurt / open. Вердикт замороженного отчёта не меняет.

Правила записаны в docs/DECISIONS.md 02.10 до первого ответа судей.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import identity_routing as ir                     # noqa: E402
import relation_holdout_v4 as hv                  # noqa: E402

ENC = ir.ENC
OUT = hv.OUT
p, pk, file_sha = hv.p, hv.pk, hv.file_sha

VERSION = "HOLDOUT_V4_REF_1"
N_MIN = 10                                        # закрытых случаев у ворот-доли меньше - INSUFFICIENT_SAMPLE
COUNT_GATES = ("dangerous_creative_standalone", "handoff_unassigned")
SAMPLE_KIND = {"dangerous_creative_standalone": "frames", "handoff_unassigned": "frames",
               "relation_existence_precision": "closed_truth_pairs", "derived_recolor_discovery": "closed_truth_pairs",
               "state_discovery": "closed_truth_pairs", "true_composite_recall": "closed_truth_pairs",
               "automatic_action_precision": "closed_actions"}
FACT_CLOSES = {"BYTE_EXACT_COPY": "EXACT_COPY", "BYTE_MIRROR": "MIRRORED_VARIANT_PEER"}
DEPS = ("tools/hdart/relation_holdout_v4.py", "tools/hdart/relation_truth_v2.py", "tools/hdart/relation_taxonomy.py",
        "tools/hdart/routing_model_v8.py", "tools/hdart/relation_discovery_v2.py",
        "tools/hdart/relation_discovery_v3.py", "tools/hdart/relation_discovery_v4.py")
SELF = "tools/hdart/relation_holdout_v4_ref.py"
ADDENDUM = {"version": VERSION,
            "combine": "relation_truth_v2.combine_pair: оба NONE - NONE; оба RELATED - RELATED, подтип закрыт, если "
                       "совпал или общая группа, иначе открыт (объединение); RELATED против NONE - OPEN; судья без "
                       "взятого ярлыка (UNSURE, low) - ось OPEN; третьего судьи нет",
            "machine_facts": "BYTE_EXACT_COPY закрывает EXACT_COPY, BYTE_MIRROR закрывает MIRRORED_VARIANT_PEER, "
                             "MCD_EDGE закрывает только существование; судьи факт не отменяют",
            "subtype_status": "CLOSED - есть закрытые, нет открытых; PARTIAL - есть и те и другие; OPEN - закрытых нет",
            "n_min": N_MIN,
            "acceptance": "FAIL - FAIL ворот-счётчика или ворот-доли с n >= N_MIN; иначе INCONCLUSIVE при "
                          "INSUFFICIENT_SAMPLE или NO_DATA; иначе PASS",
            "source": "специалист 02.10, передал Vitali в чате; N_MIN и BYTE_MIRROR - уточнения до эталона "
                      "(docs/DECISIONS.md)"}
COMPONENTS = ("mirrored_recolor", "cell_bundle", "near_recolor", "local_edit", "set_correspondence")


def jsha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- эталон

def machine_facts(ctx, mcd, a, b):
    import routing_model_v8 as v8
    f = []
    if b.upper() in ctx.ix.exact(a):
        f.append("BYTE_EXACT_COPY")
    if b.upper() in ctx.ix.mirror(a):
        f.append("BYTE_MIRROR")
    vias = {x["via"] for x in v8.facts(mcd, a) if x["relative"].upper() == b.upper()} | \
           {x["via"] for x in v8.facts(mcd, b) if x["relative"].upper() == a.upper()}
    if vias:
        f.append("MCD_EDGE:" + "|".join(sorted(vias)))
    return f


def apply_facts(existence, closed, opn, facts):
    """Машинные факты поверх объединения судей -> (существование, закрытые, открытые)."""
    closed, opn = set(closed), set(opn)
    if facts:
        existence = "RELATED"
        closed.discard("NONE")
        opn.discard("NONE")
    for f in facts:
        lab = FACT_CLOSES.get(f)
        if lab:
            closed.add(lab)
            opn.discard(lab)
    return existence, closed, opn


def statuses(existence, closed, opn):
    ex = "OPEN" if existence == "OPEN" else "CLOSED"
    if existence == "NONE":
        sub = "NONE"
    elif existence == "OPEN" or not closed:
        sub = "OPEN"
    else:
        sub = "PARTIAL" if opn else "CLOSED"
    return ex, sub


def build(out, ctx=None):
    """-> (строки истины, ошибки ответов, пары без двух ответов)."""
    import relation_discovery_v2 as v2
    import relation_discovery_v3 as v3
    import routing_model_v8 as v8
    key = ir.load_json(p(out, "key.json"))
    plock = ir.load_json(p(out, "pack.lock.json"))
    rows, bad, missing = hv.holdout_truth(out, plock, key)
    ctx = ctx or v3.Ctx(index=v2.load_index(v2.OUT))
    mcd = v8.Mcd(ctx.world)
    res = []
    for r in rows:
        f = machine_facts(ctx, mcd, r["a"], r["b"])
        if bool(f) != bool(r["authority"]):
            raise SystemExit("%s: факты %s расходятся с авторитетом '%s'" % (r["q"], f, r["authority"]))
        ex, closed, opn = apply_facts(r["existence"], r["closed"], r["open"], f)
        es, ss = statuses(ex, closed, opn)
        res.append(dict(r, existence=ex, closed=sorted(closed), open=sorted(opn), facts=f,
                        judges_existence=r["existence"], judges_closed=r["closed"], judges_open=r["open"],
                        existence_status=es, subtype_status=ss,
                        existence_basis="machine_fact" if f else "judges"))
    return res, bad, missing


def decisions(rows):
    return [[r["q"], r["a"], r["b"], r["existence"], r["existence_status"], r["subtype_status"], r["closed"],
             r["open"], r["facts"]] for r in rows]


def counts(rows):
    c = {"pairs": len(rows),
         "existence_closed": sum(r["existence_status"] == "CLOSED" for r in rows),
         "existence_open": sum(r["existence_status"] == "OPEN" for r in rows),
         "existence": dict(Counter(r["existence"] for r in rows)),
         "subtype_closed": sum(r["subtype_status"] == "CLOSED" for r in rows),
         "subtype_partial": sum(r["subtype_status"] == "PARTIAL" for r in rows),
         "subtype_open": sum(r["subtype_status"] == "OPEN" for r in rows),
         "machine_fact_closed": sum(bool(r["facts"]) for r in rows),
         "machine_fact_kinds": dict(Counter(f.split(":")[0] for r in rows for f in r["facts"])),
         "machine_fact_changed_judges": sum(r["existence"] != r["judges_existence"] or
                                            r["closed"] != r["judges_closed"] for r in rows),
         "closed_labels": dict(Counter(l for r in rows for l in r["closed"]))}
    return c


def judge_files(out):
    plock = ir.load_json(p(out, "pack.lock.json"))
    return {"judge_%d.tsv" % (i + 1): file_sha(p(out, "answers", "judge_%d.tsv" % (i + 1)))
            for i in range(len(plock["batches"]))}


def pair_keys(out):
    return [[it["q"], it["a"], it["b"]] for it in ir.load_json(p(out, "key.json"))["items"]]


def code_hashes():
    return {c: file_sha(c) for c in (SELF,) + DEPS}


def do_lockref(out=OUT):
    lock = p(out, "reference.lock.json")
    if os.path.exists(lock):
        raise SystemExit("эталон уже заморожен: %s" % lock)
    if os.path.exists(p(out, "answers_vitali.tsv")):
        raise SystemExit("есть answers_vitali.tsv - эталон замораживается только до ответов оси A")
    d, h = hv.load_freeze(out), hv.load_holdout(out)
    hv.guard(d)
    hv.detectors_same(d)
    rows, bad, missing = build(out)
    if bad or missing:
        raise SystemExit("ответы судей неполны или с ошибками: %s; без двух ответов: %s" % (bad[:10], missing[:10]))
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    tpath = p(out, "truth.json")
    ir.dump_json(tpath, {"created": now, "schema": hv.REF_SCHEMA, "addendum": ADDENDUM, "pairs": rows,
                         "existence": dict(Counter(r["existence"] for r in rows)),
                         "closed_labels": dict(Counter(l for r in rows for l in r["closed"]))})
    plock = ir.load_json(p(out, "pack.lock.json"))
    ir.dump_json(lock, {"created": now, "holdout_sha256": h["sha256"], "key_sha256": file_sha(p(out, "key.json")),
                        "pack_sha256": plock["pack_sha256"], "truth_sha256": file_sha(tpath),
                        "answers_present_at_lock": False,
                        "freeze_sha256": d["sha256"],
                        "pair_keys_sha256": jsha(pair_keys(out)), "pair_count": len(rows),
                        "judge_files_sha256": judge_files(out),
                        "code_sha256": code_hashes(),
                        "decisions_sha256": jsha(decisions(rows)),
                        "schema_sha256": jsha({"schema": hv.REF_SCHEMA, "addendum": ADDENDUM}),
                        "schema": hv.REF_SCHEMA, "addendum": ADDENDUM, "counts": counts(rows)})
    print("эталон заморожен: %s" % json.dumps(counts(rows), ensure_ascii=False))


def do_verify(out=OUT):
    lk = ir.load_json(p(out, "reference.lock.json"))
    bad = []
    T, _lk = hv.load_truth(out)                     # замороженная проверка хэша truth.json
    if lk["answers_present_at_lock"]:
        bad.append("ответы оси A были при заморозке")
    if lk["freeze_sha256"] != hv.load_freeze(out)["sha256"]:
        bad.append("FREEZE.json не тот")
    if lk["key_sha256"] != file_sha(p(out, "key.json")) or lk["pair_keys_sha256"] != jsha(pair_keys(out)):
        bad.append("ключи пар изменены")
    if lk["pack_sha256"] != ir.load_json(p(out, "pack.lock.json"))["pack_sha256"]:
        bad.append("пакет судей изменён")
    jf = judge_files(out)
    bad += ["ответ судьи изменён: %s" % k for k in sorted(jf) if jf[k] != lk["judge_files_sha256"].get(k)]
    ch = code_hashes()
    bad += ["код изменён: %s" % k for k in sorted(ch) if ch[k] != lk["code_sha256"].get(k)]
    if lk["schema_sha256"] != jsha({"schema": hv.REF_SCHEMA, "addendum": ADDENDUM}):
        bad.append("схема изменена")
    rows, jbad, missing = build(out)
    if jbad or missing:
        bad.append("ответы судей не читаются: %s %s" % (jbad[:5], missing[:5]))
    if jsha(decisions(rows)) != lk["decisions_sha256"]:
        bad.append("истина, пересобранная из ответов, расходится с решениями замка")
    stored = ir.load_json(p(out, "truth.json"))["pairs"]
    if jsha(decisions(stored)) != lk["decisions_sha256"]:
        bad.append("truth.json расходится с решениями замка")
    if counts(stored) != lk["counts"]:
        bad.append("счётчики замка не сходятся с truth.json")
    if len(T) != lk["pair_count"]:
        bad.append("пар в истине %d, в замке %d" % (len(T), lk["pair_count"]))
    for b in bad:
        print("FAIL " + b)
    print("замок цел: пар %d, судей %d, решения %s" % (lk["pair_count"], len(jf), lk["decisions_sha256"][:12])
          if not bad else "замок НЕ цел: %d расхождений" % len(bad))
    return not bad


# ---------------------------------------------------------------- итог

def acceptance(gates):
    """gates - строки замороженного gate_rows -> (строки со статусом выборки, итог)."""
    out = []
    for g in gates:
        st = g["status"]
        if g["gate"] not in COUNT_GATES and st in ("PASS", "FAIL") and (g["n"] or 0) < N_MIN:
            st = "INSUFFICIENT_SAMPLE"
        out.append(dict(g, sample_kind=SAMPLE_KIND[g["gate"]], effective_n=g["n"], accepted_status=st))
    sts = {x["accepted_status"] for x in out}
    verdict = "FAIL" if "FAIL" in sts else (
        "INCONCLUSIVE" if sts & {"INSUFFICIENT_SAMPLE", "NO_DATA"} else "PASS")
    return out, verdict


def component_of(e):
    s = set()
    if e.get("type") == "MIRRORED_RECOLOR":
        s.add("mirrored_recolor")
    rule = e.get("rule") or ""
    if rule in ("P5r", "P5rc"):
        s.add("cell_bundle")
    if e.get("detector") == "R4":
        for pre, name in (("R4b", "near_recolor"), ("R4d", "local_edit"), ("R4c", "set_correspondence")):
            if rule.startswith(pre):
                s.add(name)
    return s


def components(pc, state):
    """pc = [(a, b, истина, доводы)] -> {компонент: Counter исходов}. state(c, t) -> ok / wrong / open."""
    res = {k: Counter() for k in COMPONENTS}
    for _a, _b, t, cs in pc:
        for c in cs:
            per = [component_of(e) for e in c["support"]]
            for comp in set().union(*per) if per else set():
                r = res[comp]
                r["triggered"] += 1
                s = state(c, t)
                if s == "wrong":
                    r["hurt"] += 1
                elif s == "ok":
                    r["helped" if all(comp in x for x in per) else "unnecessary"] += 1
                else:
                    r["open"] += 1
    return {k: dict(v) for k, v in res.items()}


def report_pc(out):
    """Пары пула с истиной и доводами - так же, как замороженный do_report."""
    d, h = hv.load_freeze(out), hv.load_holdout(out)
    T, _lk = hv.load_truth(out)
    ans = {r["asset_id"]: r for r in ir.read_tsv(p(out, "answers_vitali.tsv"))}
    found3, found4 = hv.load_found(out)
    base = hv.routing_base(out, d, h)
    rows = hv.routing_rows(base, lambda a: ans.get(a, {}).get("semantic_kind", ""))
    C = hv.system_claims(rows, found3, found4)
    key = ir.load_json(p(out, "key.json"))
    return [(it["a"], it["b"], T.get(pk(it["a"], it["b"])), C.pair(it["a"], it["b"])) for it in key["items"]]


def do_posthoc(out=OUT):
    rp = p(out, "report.json")
    if not os.path.exists(rp):
        raise SystemExit("сначала замороженный report: relation_holdout_v4.py report")
    if not do_verify(out):
        raise SystemExit("замок эталона не цел - итог не считается")
    rep = ir.load_json(rp)
    gates, verdict = acceptance(rep["gates"])
    comp = components(report_pc(out), hv.tv_state)
    lk = ir.load_json(p(out, "reference.lock.json"))
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "version": VERSION, "n_min": N_MIN,
           "frozen_verdict": rep["verdict"], "acceptance": verdict, "gates": gates, "components": comp,
           "reference_counts": lk["counts"], "report_sha256": file_sha(rp)}
    ir.dump_json(p(out, "posthoc.json"), res)
    L = ["# Итог holdout V4 по правилам эталона", "",
         "Замороженный вердикт: **%s**. Acceptance (N_MIN %d): **%s**." % (rep["verdict"], N_MIN, verdict), "",
         "| ворота | значение | эффективная выборка | нужно | замороженный | итог |", "|---|---|---|---|---|---|"]
    for g in gates:
        L.append("| %s | %s | %s %s | %s | %s | %s |" % (g["gate"], hv.f3(g["value"]), g["sample_kind"],
                                                         g["effective_n"], g["need"], g["status"],
                                                         g["accepted_status"]))
    L += ["", "## Компоненты", "", "| компонент | triggered | helped | unnecessary | hurt | open |",
          "|---|---|---|---|---|---|"]
    for k in COMPONENTS:
        v = comp[k]
        L.append("| %s | %d | %d | %d | %d | %d |" % (k, v.get("triggered", 0), v.get("helped", 0),
                                                     v.get("unnecessary", 0), v.get("hurt", 0), v.get("open", 0)))
    L += ["", "Эталон: %s" % json.dumps(lk["counts"], ensure_ascii=False), "", "VERIFIED ставит только человек."]
    with open(p(out, "posthoc.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("acceptance %s (замороженный %s); %s" % (verdict, rep["verdict"], p(out, "posthoc.md")))
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["lockref", "verify", "posthoc"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    r = {"lockref": do_lockref, "verify": do_verify, "posthoc": do_posthoc}[a.cmd](a.out)
    if a.cmd == "verify" and not r:
        sys.exit(1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
