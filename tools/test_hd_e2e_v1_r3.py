#!/usr/bin/env python3
"""Проверка планировщика HD_PIPELINE_E2E_V1_R3 (tools/hdart/hd_e2e_v1_r3.py) на синтетических утверждениях:
candidate_affects_action, якорь S2, миры ворот unresolved_candidate_changed_completed_action. У каждой проверки
контрольный опыт: испорченное правило или план обязан открыть ворота, честный - нет.

    py -3.13 tools/test_hd_e2e_v1_r3.py
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import hd_e2e_v1_r3 as R3                          # noqa: E402
import relation_discovery_v3 as v3                 # noqa: E402

S, CA, TS, TO = v3.STRONG, v3.CAND, v3.T_STRONG, v3.T_OPEN
GROUP = {"COMPOSITE_PART": "composite", "ATTACHMENT_CANDIDATE": "attachment", "DESTROYED_VARIANT_OF": "state"}


class FakeC:
    def __init__(self):
        self.by = defaultdict(list)
        self.self_roles = defaultdict(list)
        self.evidence = defaultdict(list)

    def add(self, typ, src, tgt, ex=S, tl=TS):
        c = {"pair": sorted((src, tgt)), "type": typ, "group": GROUP.get(typ, "derived"), "existence": ex,
             "type_level": tl, "source": src, "target": tgt, "production": True, "support": [{"detector": "T"}]}
        if ex != S:
            c["type_open_why"] = ["существование - кандидат"]
        self.by[src].append(c)
        self.by[tgt].append(c)
        return c

    def of(self, a):
        return self.by.get(a.upper(), [])


def rows(keys, kind="OBJECT"):
    return {k: {"semantic_kind": kind, "semantic_eff": kind, "surface": "", "pipeline_why": "ось A"} for k in keys}


def run(comps, C, ident=None, batch=None, origin=("A",), rule=R3.candidate_affects_action, n_random=60):
    """comps - группы связей (кадры, связанные автоматическими утверждениями). -> план и ворота."""
    keys = sorted({k for fs in comps for k in fs})
    ident = {k: "thing %s" % k for k in keys} if ident is None else ident
    batch = keys if batch is None else batch
    rw = rows(keys)
    D = R3.build_decisions(keys, C, [])
    ae = R3.auto_edges_of(C, keys)
    groups = []
    for fs in comps:
        g = R3.plan_tree(sorted(fs), C, rw, set(origin), {}, ident, set(batch))
        g["group_id"] = "g:" + g["anchor"]
        g["batch_keys"] = sorted(set(fs) & set(batch))
        g["kinds"] = {k: "OBJECT" for k in fs}
        groups.append(g)
    ctx = R3.Ctx(ae, D, keys)
    R3.plan_all(groups, D, ae, ctx, ident, set(origin), set(batch), rule)
    P = {"groups": groups, "D": D, "auto_edges": ae, "ctx": ctx}
    tickets, _rid = R3.make_tickets(P, batch)
    jobs = R3.make_jobs(groups, ident, {})
    G, det, nw = R3.gates_r3(groups, jobs, C, tickets, D, ae, keys, None, batch, n_random)
    st = {k: g["status"][k] for g in groups for k in g["members"]}
    return {"st": st, "G": G, "det": det, "groups": groups, "jobs": jobs, "D": D, "ae": ae, "keys": keys,
            "tickets": tickets}


def check(name, cond, got):
    print("%-72s %s" % (name, "ok" if cond else "FAIL %s" % (got,)))
    return bool(cond)


def clean(G):
    return all(v == 0 for v in G.values())


def no_rule(e, f, action, ctx, auto=False, unit=()):
    """Испорченное правило: решение ничего не меняет."""
    return "NO", "", []


def derived_blind_rule(e, f, action, ctx, auto=False, unit=()):
    """Испорченное правило: вывод (DIR) не задевает выводимый кадр."""
    if e[0] == "DIR" and not auto:
        return "NO", "", []
    return R3.candidate_affects_action(e, f, action, ctx, auto, unit)


def main():
    ok = True
    gate = "unresolved_candidate_changed_completed_action"
    # 1. кандидат перекраски B от A: основа A рисуется, B (и вывод B из A, и свой рисунок B) - на ревью
    C = FakeC()
    C.add("RECOLOR_OF", "B:1", "A:1", ex=CA, tl=TO)
    r = run([["A:1"], ["B:1"]], C)
    ok &= check("1 RECOLOR_OF кандидат: A RENDER, B на ревью", r["st"] == {"A:1": "RENDER", "B:1": "BLOCKED_REVIEW"},
                r["st"])
    ok &= check("1 ворота чистые", clean(r["G"]), dict(r["G"]))
    e = ("DIR", "B:1", "A:1", "DERIVE_RECOLOR")
    ctx = R3.Ctx(r["ae"], r["D"], r["keys"])
    ok &= check("1 candidate_affects_action: A RENDER - NO, B RENDER - YES, B DERIVE_RECOLOR - YES",
                [R3.candidate_affects_action(e, k, a, ctx)[0] for k, a in
                 (("A:1", "RENDER"), ("B:1", "RENDER"), ("B:1", "DERIVE_RECOLOR"))] == ["NO", "YES", "YES"], "")
    rb = run([["A:1"], ["B:1"]], C, rule=derived_blind_rule)
    ok &= check("1 контроль: правило не видит выводимого - B рисуется, ворота миров открыты",
                rb["st"]["B:1"] == "RENDER" and rb["G"][gate] > 0, (rb["st"], rb["G"][gate]))
    # 1б. кандидат перекраски-пары: рисуется один (лучший по своему опознанию), второй - дубль
    C = FakeC()
    C.add("RECOLOR_PEER", "A:1", "B:1", ex=CA, tl=TO)
    r = run([["A:1"], ["B:1"]], C, ident={"B:1": "thing"})
    ok &= check("1б RECOLOR_PEER кандидат: рисуется B (своё опознание), A не рисуется",
                r["st"]["B:1"] == "RENDER" and r["st"]["A:1"] != "RENDER", r["st"])
    ok &= check("1б ворота чистые", clean(r["G"]), dict(r["G"]))
    base = R3.UF()
    for k in r["keys"]:
        base.find(k)
    sym = [e for d in r["D"].values() for e in d["forms"]]
    both = R3.world_check(base, r["ae"], sym, ["A:1", "B:1"], {})
    ok &= check("1б контроль: оба отпущены - мир «пара принята» даёт второй рисунок класса",
                any("второй рисунок" in v for v in both) and not R3.world_check(base, r["ae"], [], ["A:1", "B:1"], {}),
                both)
    # 2. кандидат составного A~B: оба конца на ревью
    C = FakeC()
    C.add("COMPOSITE_PART", "A:2", "B:2", ex=CA, tl=TO)
    r = run([["A:2"], ["B:2"]], C)
    ok &= check("2 COMPOSITE кандидат: оба конца на ревью",
                r["st"] == {"A:2": "BLOCKED_REVIEW", "B:2": "BLOCKED_REVIEW"}, r["st"])
    ok &= check("2 ворота чистые", clean(r["G"]), dict(r["G"]))
    rb = run([["A:2"], ["B:2"]], C, rule=no_rule)
    ok &= check("2 контроль: правило молчит - оба рисуются, ворота миров открыты",
                rb["st"]["A:2"] == "RENDER" and rb["G"][gate] > 0, (rb["st"], rb["G"][gate]))
    # 3. несвязанная единица той же группы: кандидат составного у D (выводится из A перекраской) не держит A и копию
    C = FakeC()
    C.add("EXACT_COPY_PEER", "A:3", "B:3")
    C.add("RECOLOR_OF", "D:3", "A:3")
    C.add("COMPOSITE_PART", "D:3", "X:3", ex=CA, tl=TO)
    r = run([["A:3", "B:3", "D:3"], ["X:3"]], C)
    ok &= check("3 кандидат у D: A RENDER, копия B DERIVE, D на ревью",
                (r["st"]["A:3"], r["st"]["B:3"], r["st"]["D:3"]) == ("RENDER", "DERIVE", "BLOCKED_REVIEW"), r["st"])
    ok &= check("3 ворота чистые", clean(r["G"]), dict(r["G"]))
    # 4. решение выше по дереву, способное сменить основу: кандидат «копия B выводится из Y» держит и A, и B
    C = FakeC()
    C.add("EXACT_COPY_PEER", "A:4", "B:4")
    C.add("RECOLOR_OF", "B:4", "Y:4", ex=CA, tl=TO)
    r = run([["A:4", "B:4"], ["Y:4"]], C)
    ok &= check("4 основа может смениться: A и B не исполняются, Y рисуется",
                r["st"]["A:4"] not in R3.EXEC and r["st"]["B:4"] not in R3.EXEC and r["st"]["Y:4"] == "RENDER", r["st"])
    ok &= check("4 ворота чистые", clean(r["G"]), dict(r["G"]))
    rb = run([["A:4", "B:4"], ["Y:4"]], C, rule=derived_blind_rule)
    ok &= check("4 контроль: правило не видит выводимого - A рисуется, ворота миров открыты",
                rb["st"]["A:4"] == "RENDER" and rb["G"][gate] > 0, (rb["st"], rb["G"][gate]))
    #    вывод ниже: D выводится из A (перекраска STRONG), кандидат «D - износ Z» держит D, A рисуется
    C = FakeC()
    C.add("EXACT_COPY_PEER", "A:4", "B:4")
    C.add("EXACT_MIRROR_PEER", "A:4", "D:4")
    C.add("DESTROYED_VARIANT_OF", "D:4", "Z:4", ex=CA, tl=TO)
    r = run([["A:4", "B:4", "D:4"], ["Z:4"]], C)
    ok &= check("4б кандидат износа на зеркале D: весь класс A не исполняется (D геометрически равен A)",
                all(r["st"][k] not in R3.EXEC for k in ("A:4", "B:4", "D:4")), r["st"])
    # 5. точная копия: якорем становится кадр со своим опознанием
    C = FakeC()
    C.add("EXACT_COPY_PEER", "A:5", "B:5")
    r = run([["A:5", "B:5"]], C, ident={"B:5": "thing"})
    g = r["groups"][0]
    ok &= check("5 S2: якорь B (своё опознание), A - копия",
                g["anchor"] == "B:5" and g["anchor_old"] == "A:5" and r["st"] == {"A:5": "DERIVE", "B:5": "RENDER"},
                (g["anchor"], r["st"]))
    ok &= check("5 задание с опознанием своего кадра", r["jobs"][0]["identity_source"] == "B:5" and
                r["G"]["identity_borrowed_from_other_asset"] == 0, r["jobs"])
    r0 = run([["A:5", "B:5"]], C, ident={})
    ok &= check("5 контроль: опознания нет ни у кого - IDENTITY_MISSING, не рисуется",
                r0["st"]["A:5"] == "BLOCKED_REVIEW" and any(t["kind"] == "IDENTITY_MISSING" for t in r0["tickets"]),
                r0["st"])
    #    перекраска-пара со своим опознанием якорем по S2 не становится (S2 - только точные копии)
    C = FakeC()
    C.add("RECOLOR_PEER", "A:5", "M:5")
    r = run([["A:5", "M:5"]], C, ident={"M:5": "thing"})
    ok &= check("5б RECOLOR_PEER со своим опознанием: якорь остаётся A, IDENTITY_MISSING",
                r["groups"][0]["anchor"] == "A:5" and r["st"]["A:5"] == "BLOCKED_REVIEW", r["st"])
    # 6. принят / отвергнут: отпущенное прямое действие верно в обоих мирах, отпущенный выводимый - нет
    C = FakeC()
    C.add("RECOLOR_OF", "B:6", "A:6", ex=CA, tl=TO)
    C.add("COMPOSITE_PART", "P:6", "Q:6", ex=CA, tl=TO)
    r = run([["A:6"], ["B:6"], ["P:6"], ["Q:6"]], C)
    base = R3.UF()
    for k in r["keys"]:
        base.find(k)
    renders = [k for k, s in r["st"].items() if s == "RENDER"]
    forms = [e for d in r["D"].values() for e in d["forms"]]
    acc = R3.world_check(base, r["ae"], forms, renders, {})
    rej = R3.world_check(base, r["ae"], [], renders, {})
    ok &= check("6 A рисуется; верно и при «принято», и при «отвергнуто»", renders == ["A:6"] and not acc and not rej,
                (renders, acc, rej))
    acc_b = R3.world_check(base, r["ae"], forms, renders + ["B:6", "P:6"], {})
    rej_b = R3.world_check(base, r["ae"], [], renders + ["B:6", "P:6"], {})
    ok &= check("6 контроль: B и P отпущены - «принято» ломает, «отвергнуто» нет", len(acc_b) == 2 and not rej_b,
                (acc_b, rej_b))
    # 7. улика на кадре: свой рисунок держится, рисунок без улик рядом идёт
    C = FakeC()
    C.evidence["A:7"].append({"rule": "R7", "why": "alternate_view"})
    r = run([["A:7"], ["B:7"]], C)
    ok &= check("7 улика на A: A на ревью, B рисуется", r["st"] == {"A:7": "BLOCKED_REVIEW", "B:7": "RENDER"},
                r["st"])
    ok &= check("7 ворота чистые", clean(r["G"]), dict(r["G"]))
    print("ВСЁ ВЕРНО" if ok else "ЕСТЬ ОШИБКИ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
