#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""HD_PIPELINE_E2E_V1_R3_1 - планировщик R3 с одной правкой (специалист 03.10, передал Vitali в чате):
ATTACHMENT_CANDIDATE - примыкание ОТДЕЛЬНЫХ предметов (relation_taxonomy: «separate objects»). Оно может потребовать
ревью самой связи и повлиять на расстановку, но само не объединяет кадры в единицу рисования, не меняет якорь и не
запрещает прямой рисунок: candidate_affects_action(примыкание, кадр, DIRECT_RENDER) = NO. Тикет на связь остаётся.

Остальное - код R3 (hd_e2e_v1_r3.py) без изменений: правка подставляется только на время своих команд, R3 и его
записи (r3/spec.json, r3/plan.json) не трогаются; тикеты R3 один раз копируются в r3/review_r3.jsonl.

    spec    -> hd-e2e-v1/r31/spec.json (неизменяемый)
    plan    -> hd-e2e-v1/r31/plan.json, plan.md; тикеты -> review/e2e-v1/review.jsonl
    check   V7, spec V1, R2, R3 и R3.1, relations и код рендера не изменились

    py -3.13 tools/hdart/hd_e2e_v1_r31.py <команда>
"""
import argparse
import os
import shutil
import sys
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hd_e2e_v1 as E1                            # noqa: E402
import hd_e2e_v1_r3 as R3                         # noqa: E402
import identity_routing as ir                     # noqa: E402

PROFILE = "HD_PIPELINE_E2E_V1_R3_1"
OUT = os.path.join(E1.OUT, "r31")
R3_OUT = os.path.join(E1.OUT, "r3")
SELF = "tools/hdart/hd_e2e_v1_r31.py"
ATTACH_T = "ATTACHMENT_CANDIDATE"
R3_BODY = R3.BODY
RULE = ("ATTACHMENT_CANDIDATE - примыкание отдельных предметов: форма решения ATTACH, единицу рисования, якорь и "
        "прямой рисунок не меняет (candidate_affects_action = NO); тикет на связь остаётся")
DECISION = ("специалист 03.10, передал Vitali в чате: R3.1 - единственная правка планировщика R3: "
            "ATTACHMENT_CANDIDATE не меняет единицу рисования; остальные правила R3 не меняются")


def edge_of_r31(t, a, b, src, tgt, _base=R3.edge_of):
    if t == ATTACH_T:
        return [("ATTACH", a, b, t)]
    return _base(t, a, b, src, tgt)


@contextmanager
def semantics():
    """Правило R3.1 на время вызова: примыкание - форма ATTACH, которую правило и миры ворот не считают сменой."""
    old = R3.edge_of
    R3.edge_of = edge_of_r31
    try:
        yield
    finally:
        R3.edge_of = old


def r3_spec_sha():
    sp = ir.load_json(os.path.join(R3_OUT, "spec.json"))
    if E1.jsha({k: sp[k] for k in R3_BODY}) != sp["sha256"]:
        raise SystemExit("spec.json R3 изменён после записи")
    return sp["sha256"]


@contextmanager
def redirect():
    """Команды R3 пишут в r31/ и под своим профилем; spec R3.1 хранит хэш spec R3."""
    names = ("OUT", "PROFILE", "SELF", "BODY", "spec_body", "keep_r2_review", "check_frozen")
    old = {n: getattr(R3, n) for n in names}
    base_body, base_check = R3.spec_body, R3.check_frozen

    def spec_body(d, ver, sp1, sp2):
        body = base_body(d, ver, sp1, sp2)
        body.update(profile=PROFILE, decision=DECISION, r3_spec_sha256=r3_spec_sha())
        body["production_rules"] += "\n  R3.1: " + RULE
        body["decision_forms"] = dict(body["decision_forms"], ATTACH=[ATTACH_T],
                                      TOG=[t for t in body["decision_forms"]["TOG"] if t != ATTACH_T])
        return body

    def check_frozen(sp):
        sp1 = base_check(sp)
        if r3_spec_sha() != sp["r3_spec_sha256"]:
            raise SystemExit("spec R3 не тот, на котором записан R3.1")
        return sp1

    def keep_review():
        old["keep_r2_review"]()
        src = os.path.join(R3.REVIEW_DIR, "review.jsonl")
        dst = os.path.join(R3_OUT, "review_r3.jsonl")
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copyfile(src, dst)
    R3.OUT, R3.PROFILE, R3.SELF = OUT, PROFILE, SELF
    R3.BODY = old["BODY"] + ("r3_spec_sha256",)
    R3.spec_body, R3.keep_r2_review, R3.check_frozen = spec_body, keep_review, check_frozen
    try:
        yield
    finally:
        for n, v in old.items():
            setattr(R3, n, v)


def do_spec():
    with redirect(), semantics():
        R3.do_spec()


def do_plan():
    with redirect(), semantics():
        R3.do_plan()
    md = os.path.join(OUT, "plan.md")
    with open(md, encoding=R3.ENC) as f:
        text = f.read()
    text = text.replace("# HD_PIPELINE_E2E_V1_R3 - ", "# HD_PIPELINE_E2E_V1_R3.1 - ", 1)
    text = text.replace("## Сводка", "Правка R3.1: %s. Spec R3 `%s`.\n\n## Сводка" % (RULE, r3_spec_sha()[:12]), 1)
    with open(md, "w", encoding=R3.ENC, newline="\n") as f:
        f.write(text)


def do_check():
    with redirect():
        R3.check_frozen(R3.load_spec())
    print("R3.1: V7, spec V1, R2, R3 и R3.1, relations и конфигурация рендера целы")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("spec", "plan", "check"))
    a = ap.parse_args()
    {"spec": do_spec, "plan": do_plan, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
