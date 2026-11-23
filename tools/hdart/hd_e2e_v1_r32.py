#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""HD_PIPELINE_E2E_V1_R3_2 - один пересчёт плана R3.1 после ревью (специалист 03.10, передал Vitali в чате):
«ответы сначала замораживаются как review decisions, потом один R3.2 recount».

Входы сверх R3.1 - только замороженные ответы человека (answers.lock.json):
  - решения девяти тикетов связей - review/e2e-v1/decisions.tsv (hd_e2e_v1_review.py import);
  - опознание BATHBITZ:14 - probes/hd-e2e-v1/identity/answers_vitali.tsv (тот же формат, что ось A V7; V7 не
    меняется, строка дописывается к оси A только в памяти этого пересчёта, пересечение с V7 - отказ).
Карточки перекраски DERIVE_RECOLOR_V2 в замок входят как диагностика к V3; планировщик их не читает.

Правило R3.2 - решение ревью закрывает неавтоматическое утверждение V7 (ключ решения тот же, что ключ тикета):
  NO_RELATION - форм нет, производство не меняется; CONFIRM_TYPE - тип утверждения; OTHER_TYPE - названный тип.
  Принятый тип переводится в форму правилом R3.1 (edge_of); принят может быть только тип, который единицу рисования,
  основу и способ не меняет (примыкание ATTACH). Решение, которое меняет производство (общая единица, вывод, пара),
  этот пересчёт исполнить не умеет - отказ, а не догадка. OPEN - решение остаётся открытым. Тикет закрытого решения
  остаётся в списке с полем resolution (ворота relation_decision_lost_in_handoff его видят).
Остальное - код R3 и правка R3.1 без изменений; R3, R3.1 и их записи не трогаются. Видеокарта не нужна.

    freeze  -> review/e2e-v1/answers.lock.json (неизменяемый; после него import отказывает)
    spec    -> hd-e2e-v1/r32/spec.json (неизменяемый)
    plan    -> hd-e2e-v1/r32/plan.json, plan.md; тикеты -> review/e2e-v1/review.jsonl (R3.1 - копия r31/review_r31.jsonl)
               один раз: второй пересчёт - отказ
    check   V7, spec V1, R2, R3, R3.1 и R3.2, relations, рендер и замок ответов не изменились

    py -3.13 tools/hdart/hd_e2e_v1_r32.py <команда>
"""
import argparse
import json
import os
import shutil
import sys
import time
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hd_e2e_v1 as E1                            # noqa: E402
import hd_e2e_v1_r3 as R3                         # noqa: E402
import hd_e2e_v1_r31 as R31                       # noqa: E402
import hd_e2e_v1_review as RV                     # noqa: E402
import identity_routing as ir                     # noqa: E402

PROFILE = "HD_PIPELINE_E2E_V1_R3_2"
OUT = os.path.join(E1.OUT, "r32")
R31_OUT = R31.OUT
SELF = "tools/hdart/hd_e2e_v1_r32.py"
LOCK = os.path.join(RV.REVIEW_DIR, "answers.lock.json")
ID_ANSWERS = os.path.join(E1.OUT, "identity", "answers_vitali.tsv")
RECOLOR_ANSWERS = os.path.join("art", "objects", "generation", "probes", "derive-recolor-acceptance-v2",
                               "answers_human.tsv")
SOURCES = os.path.join(RV.REVIEW_DIR, "answers_in")
NOT_CHANGING = ("ATTACH",)                        # формы, которые принятое решение может дать в этом пересчёте
RULE = ("решение ревью закрывает утверждение: NO_RELATION - форм нет, CONFIRM_TYPE / OTHER_TYPE - форма принятого "
        "типа по R3.1, только не меняющая производство (ATTACH), иначе отказ; OPEN - открыто; опознание кадров вне "
        "оси A V7 - из замороженных ответов E2E")
DECISION = ("специалист 03.10, передал Vitali в чате: ответы ревью (9 тикетов) и опознание BATHBITZ:14 заморожены "
            "как review decisions, затем ровно один пересчёт R3.2; DERIVE_RECOLOR_V2 остаётся FAIL")
FREEZE_DECISION = ("специалист 03.10, передал Vitali в чате: ответы заморожены до пересчёта R3.2; решения тикетов и "
                   "опознание - вход планировщика, карточки перекраски - диагностика к V3")


def p(*a):
    return os.path.join(OUT, *a)


def rows_of(path):
    return len(ir.read_tsv(path))


# ---------------------------------------------------------------- замок ответов

def lock_body():
    files = {"decisions": RV.DECISIONS, "identity_answers": ID_ANSWERS, "recolor_human_answers": RECOLOR_ANSWERS}
    for f in sorted(os.listdir(SOURCES)):
        files["source:" + f] = os.path.join(SOURCES, f)
    out = {}
    for name, path in files.items():
        if not os.path.exists(path):
            raise SystemExit("нет файла ответов: %s" % path)
        out[name] = {"path": path.replace(os.sep, "/"), "sha256": E1.file_sha(path), "rows": rows_of(path)}
    return {"profile": PROFILE, "decision": FREEZE_DECISION, "files": out,
            "planner_inputs": ["decisions", "identity_answers"],
            "diagnostic_only": ["recolor_human_answers"]}


def do_freeze():
    body = lock_body()
    if body["files"]["decisions"]["rows"] == 0:
        raise SystemExit("decisions.tsv пуст - замораживать нечего")
    if os.path.exists(LOCK):
        old = ir.load_json(LOCK)
        if old["files"] != body["files"]:
            raise SystemExit("ответы уже заморожены и отличаются: %s" % LOCK)
        print("замок тот же: %s" % E1.file_sha(LOCK)[:12])
        return
    body["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    ir.dump_json(LOCK, body)
    for n, f in sorted(body["files"].items()):
        print("  %-48s %s  строк %d" % (n, f["sha256"][:12], f["rows"]))
    print("ответы заморожены: %s (%s)" % (LOCK, E1.file_sha(LOCK)[:12]))


def load_lock():
    if not os.path.exists(LOCK):
        raise SystemExit("ответы не заморожены: сначала freeze")
    lk = ir.load_json(LOCK)
    bad = [n for n, f in lk["files"].items() if E1.file_sha(f["path"]) != f["sha256"]]
    if bad:
        raise SystemExit("файлы ответов изменены после заморозки: %s" % ", ".join(bad))
    return lk


def resolutions(lk):
    """decisions.tsv -> {ticket_key: решение}; OPEN не закрывает."""
    out = {}
    for r in ir.read_tsv(lk["files"]["decisions"]["path"]):
        if r["decision"] != "OPEN":
            out[r["ticket_key"]] = r
    return out


def extra_axis_a(lk):
    rows = {r["asset_id"].upper(): r for r in ir.read_tsv(lk["files"]["identity_answers"]["path"])}
    return rows


# ---------------------------------------------------------------- правило R3.2 на время команд

@contextmanager
def semantics(lk):
    res = resolutions(lk)
    extra = extra_axis_a(lk)
    seen = set()
    base_forms, base_axis, base_make, base_write = R3.forms_of, E1.axis_a, R3.make_tickets, R3.write_review

    def forms_of(c):
        a, b = c["pair"]
        k = R3.decision_key("UNRESOLVED_RELATION", c["pair"], [c["group"], list(c["pair"])])
        r = res.get(k)
        if r is None:
            return base_forms(c)
        seen.add(k)
        if r["decision"] == "NO_RELATION":
            return []
        t = r["type"] if r["decision"] == "OTHER_TYPE" else c["type"]
        e = R3.edge_of(t, a, b, c["source"].upper(), c["target"].upper())
        if e is None or any(x[0] not in NOT_CHANGING for x in e):
            raise SystemExit("решение %s (%s %s) меняет производство (%s) - R3.2 такое не исполняет" % (
                k, r["decision"], t, e))
        return e

    def axis_a():
        ax = base_axis()
        both = sorted(set(ax) & set(extra))
        if both:
            raise SystemExit("опознание E2E пересекается с осью A V7: %s" % ", ".join(both))
        return dict(ax, **extra)

    def make_tickets(P, batch):
        tickets, rid = base_make(P, batch)
        keys = {t["ticket_key"] for t in tickets}
        lost = sorted(set(res) - keys)
        if lost:
            raise SystemExit("решения ревью без тикета в пересчёте: %s" % ", ".join(lost))
        for t in tickets:
            r = res.get(t["ticket_key"])
            t["resolution"] = None if r is None else {
                "decision": r["decision"], "type": r["type"] or (t["claim"] or {}).get("type"),
                "review_id_r31": r["review_id"], "who": r["who"], "when": r["when"], "note": r["note"]}
            if r is not None:
                t["released_despite"] = []                 # решение закрыто: отпущено не «при открытом»
        return tickets, rid

    def write_review(tickets):
        base_write(tickets)
        path = os.path.join(R3.REVIEW_DIR, "review.jsonl")
        by = {t["review_id"]: t.get("resolution") for t in tickets}
        with open(path, encoding=R3.ENC) as f:
            lines = [json.loads(x) for x in f if x.strip()]
        if len(lines) != len(tickets):
            raise SystemExit("review.jsonl: %d строк против %d тикетов" % (len(lines), len(tickets)))
        with open(path, "w", encoding=R3.ENC, newline="\n") as f:
            for x in lines:
                x["resolution"] = by[x["review_id"]]
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
    R3.forms_of, E1.axis_a, R3.make_tickets, R3.write_review = forms_of, axis_a, make_tickets, write_review
    try:
        yield res, seen
    finally:
        R3.forms_of, E1.axis_a, R3.make_tickets, R3.write_review = base_forms, base_axis, base_make, base_write


def r31_spec_sha(body_keys):
    sp = ir.load_json(os.path.join(R31_OUT, "spec.json"))
    if E1.jsha({k: sp[k] for k in body_keys}) != sp["sha256"]:
        raise SystemExit("spec.json R3.1 изменён после записи")
    return sp["sha256"]


@contextmanager
def redirect():
    """Поверх перенаправления R3.1: команды пишут в r32/ под своим профилем; spec хранит хэш spec R3.1 и замка."""
    with R31.redirect(), R31.semantics():
        names = ("OUT", "PROFILE", "SELF", "BODY", "spec_body", "keep_r2_review", "check_frozen")
        old = {n: getattr(R3, n) for n in names}
        r31_body = old["BODY"]

        def spec_body(d, ver, sp1, sp2):
            body = old["spec_body"](d, ver, sp1, sp2)
            body.update(profile=PROFILE, decision=DECISION, r31_spec_sha256=r31_spec_sha(r31_body),
                        answers_lock_sha256=E1.file_sha(LOCK))
            body["production_rules"] += "\n  R3.2: " + RULE
            return body

        def check_frozen(sp):
            sp1 = old["check_frozen"](sp)
            if r31_spec_sha(r31_body) != sp["r31_spec_sha256"]:
                raise SystemExit("spec R3.1 не тот, на котором записан R3.2")
            load_lock()
            if E1.file_sha(LOCK) != sp["answers_lock_sha256"]:
                raise SystemExit("замок ответов не тот, на котором записан R3.2")
            return sp1

        def keep_review():
            old["keep_r2_review"]()
            src = os.path.join(R3.REVIEW_DIR, "review.jsonl")
            dst = os.path.join(R31_OUT, "review_r31.jsonl")
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copyfile(src, dst)
        R3.OUT, R3.PROFILE, R3.SELF = OUT, PROFILE, SELF
        R3.BODY = r31_body + ("r31_spec_sha256", "answers_lock_sha256")
        R3.spec_body, R3.keep_r2_review, R3.check_frozen = spec_body, keep_review, check_frozen
        try:
            yield
        finally:
            for n, v in old.items():
                setattr(R3, n, v)


def do_spec():
    load_lock()
    with redirect():
        R3.do_spec()


def summary(path):
    pl = ir.load_json(path)
    dg = pl["diagnostics"]
    return {"verdict": pl["verdict"], "jobs": len(pl["jobs"]), "render_units": dg["render_units"],
            "render_units_released": dg["render_units_released"], "executable_actions": dg["executable_actions"],
            "identity_missing": dg["identity_missing"], "review_tickets": dg["review_tickets"],
            "frame_status": dg["frame_status"]}


def do_plan():
    lk = load_lock()
    if os.path.exists(p("plan.json")) and "r32_summary" in ir.load_json(p("plan.json")):
        raise SystemExit("пересчёт R3.2 уже сделан (один раз): %s" % p("plan.json"))
    with redirect(), semantics(lk) as (res, seen):
        R3.do_plan()
    if seen != set(res):
        raise SystemExit("решения не дошли до утверждений: %s" % ", ".join(sorted(set(res) - seen)))
    pl = ir.load_json(p("plan.json"))
    before, after = summary(os.path.join(R31_OUT, "plan.json")), summary(p("plan.json"))
    pl["answers_lock_sha256"] = E1.file_sha(LOCK)
    pl["r31_summary"], pl["r32_summary"] = before, after
    ir.dump_json(p("plan.json"), pl)
    tk = []
    with open(os.path.join(R3.REVIEW_DIR, "review.jsonl"), encoding=R3.ENC) as f:
        for x in f:
            t = json.loads(x)
            if t.get("resolution"):
                tk.append(t)
    md = p("plan.md")
    with open(md, encoding=R3.ENC) as f:
        text = f.read()
    rows = ["| что | R3.1 | R3.2 |", "|---|---|---|"] + [
        "| %s | %s | %s |" % (k, before[k], after[k]) for k in before if k != "frame_status"]
    res_rows = ["| тикет R3.2 (был) | пара | утверждение | решение | тип |", "|---|---|---|---|---|"] + [
        "| %s (%s) | %s | %s | %s | %s |" % (t["review_id"], t["resolution"]["review_id_r31"], "~".join(t["frames"]),
                                          (t["claim"] or {}).get("type"), t["resolution"]["decision"],
                                          t["resolution"]["type"]) for t in tk]
    add = ("Правка R3.2: %s. Spec R3.1 `%s`, замок ответов `%s`.\n\n## Решения ревью\n\n%s\n\n## R3.1 против R3.2\n\n"
           "%s\n\nСтатусы кадров R3.1: %s.\n\n## Сводка" % (
               RULE, ir.load_json(p("spec.json"))["r31_spec_sha256"][:12],
               E1.file_sha(LOCK)[:12], "\n".join(res_rows), "\n".join(rows), before["frame_status"]))
    text = text.replace("# HD_PIPELINE_E2E_V1_R3 - ", "# HD_PIPELINE_E2E_V1_R3.2 - ", 1)
    text = text.replace("## Сводка", add, 1)
    with open(md, "w", encoding=R3.ENC, newline="\n") as f:
        f.write(text)
    print("R3.1 -> R3.2: %s" % {k: (before[k], after[k]) for k in before if k != "frame_status"})


def do_check():
    with redirect():
        R3.check_frozen(R3.load_spec())
    print("R3.2: V7, spec V1, R2, R3, R3.1 и R3.2, relations, рендер и замок ответов целы")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("freeze", "spec", "plan", "check"))
    a = ap.parse_args()
    os.chdir(os.path.dirname(os.path.dirname(HERE)))
    {"freeze": do_freeze, "spec": do_spec, "plan": do_plan, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
