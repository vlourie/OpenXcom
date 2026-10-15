#!/usr/bin/env python3
"""Проверка планировщика HD_PIPELINE_E2E_V1_R2 (tools/hdart/hd_e2e_v1_r2.py) на синтетических утверждениях: ревью на
уровне единиц рисования, ворота с контрольными опытами - испорченный план обязан их открыть, честный - нет.

    py -3.13 tools/test_hd_e2e_v1_r2.py
"""
import copy
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import hd_e2e_v1_r2 as R                           # noqa: E402
import relation_discovery_v3 as v3                 # noqa: E402

S, CA, TS, TO = v3.STRONG, v3.CAND, v3.T_STRONG, v3.T_OPEN


class FakeC:
    def __init__(self):
        self.by = defaultdict(list)
        self.self_roles = defaultdict(list)
        self.evidence = defaultdict(list)

    def add(self, typ, src, tgt, ex=S, tl=TS, group="derived"):
        c = {"pair": sorted((src, tgt)), "type": typ, "group": group, "existence": ex, "type_level": tl,
             "source": src, "target": tgt, "production": True, "support": [{"detector": "T"}]}
        self.by[src].append(c)
        self.by[tgt].append(c)
        return c

    def of(self, a):
        return self.by.get(a.upper(), [])


def rows(keys, kind="OBJECT"):
    return {k: {"semantic_kind": kind, "semantic_eff": kind, "surface": "", "pipeline_why": "ось A"} for k in keys}


def plan(members, C, rw=None, ident=None, comp=None, supports=R.RENDERER_SUPPORTS, origin=("A",)):
    rw = rw or rows(members)
    ident = {m: "thing %s" % m for m in members} if ident is None else ident
    g = R.plan_group_r2(members, C, rw, set(origin), comp or {}, ident, supports)
    g["group_id"] = "g:" + g["anchor"]
    g["kinds"] = {k: rw[k]["semantic_kind"] for k in members}
    jobs = []
    if g["status"][g["anchor"]] == "RENDER":
        a = g["anchor"]
        jobs.append({"job_id": "r01", "group_id": g["group_id"], "render_asset": a,
                     "render_unit": g["units"][g["unit_of"][a]]["frames"], "identity": ident.get(a, ""),
                     "identity_source": a if ident.get(a) else ""})
    return g, jobs


def gates(g, jobs, C):
    G, det = R.gates_r2([g], jobs, C)
    return G, det


def check(name, cond, got):
    print("%-66s %s" % (name, "ok" if cond else "FAIL %s" % (got,)))
    return bool(cond)


def clean(G):
    return all(v == 0 for v in G.values())


def main():
    ok = True
    # 1. копии от якоря, открытый вопрос между двумя выводами: держит их двоих, третий и якорь идут дальше
    C = FakeC()
    C.add("EXACT_COPY_PEER", "A:1", "B:1")
    C.add("EXACT_MIRROR_PEER", "A:1", "C:1")
    C.add("EXACT_COPY_PEER", "A:1", "D:1")
    C.add("RECOLOR_PEER", "B:1", "C:1", ex=CA, tl=TO)
    M = ["A:1", "B:1", "C:1", "D:1"]
    g, jobs = plan(M, C)
    st = g["status"]
    ok &= check("вопрос B~C: B и C на ревью", st["B:1"] == st["C:1"] == "BLOCKED_REVIEW", st)
    ok &= check("вопрос B~C: третья единица D выводится, якорь A рисуется",
                st["D:1"] == "DERIVE" and st["A:1"] == "RENDER" and len(jobs) == 1, st)
    ok &= check("вопрос B~C: один тикет, две задетые единицы",
                len(g["tickets"]) == 1 and g["tickets"][0]["affected_render_units"] == ["u:B:1", "u:C:1"], g["tickets"])
    G, det = gates(g, jobs, C)
    ok &= check("вопрос B~C: все ворота 0", clean(G), dict(det))
    ok &= check("вопрос B~C: якорь под решением, способным сменить основу (видно)",
                "A:1" in g["exposed"] and "D:1" not in g["exposed"], g["exposed"])
    # 1к. контроль потери решения: тикет выброшен и B исполняется - ворота открываются
    g2 = copy.deepcopy(g)
    g2["tickets"] = []
    g2["status"]["B:1"] = "DERIVE"
    G2, _ = gates(g2, jobs, C)
    ok &= check("контроль: тикет потерян -> relation_decision_lost_in_handoff",
                G2["relation_decision_lost_in_handoff"] > 0, dict(G2))
    g3 = copy.deepcopy(g)
    g3["status"]["B:1"] = "DERIVE"
    G3, _ = gates(g3, jobs, C)
    ok &= check("контроль: задетый тикетом кадр исполняется -> unresolved_relation_used",
                G3["unresolved_relation_used_for_render"] > 0, dict(G3))
    # 2. вывод ниже заблокированного: блокируется вниз, и контроль утечки
    C = FakeC()
    C.add("EXACT_COPY_PEER", "A:1", "B:1")
    C.add("EXACT_COPY_PEER", "B:1", "E:1")
    C.add("EXACT_COPY_PEER", "A:1", "D:1")
    C.evidence["B:1"].append({"rule": "R7"})
    M = ["A:1", "B:1", "D:1", "E:1"]
    g, jobs = plan(M, C)
    st = g["status"]
    ok &= check("улика на B: B ревью, E ниже - BLOCKED_UPSTREAM, D выводится",
                st["B:1"] == "BLOCKED_REVIEW" and st["E:1"] == "BLOCKED_UPSTREAM" and st["D:1"] == "DERIVE", st)
    ok &= check("улика на B: тикет блокирует ниже u:E:1", g["tickets"][0]["downstream_blocked"] == ["u:E:1"],
                g["tickets"])
    G, det = gates(g, jobs, C)
    ok &= check("улика на B: все ворота 0", clean(G), dict(det))
    g2 = copy.deepcopy(g)
    g2["status"]["E:1"] = "DERIVE"
    G2, _ = gates(g2, jobs, C)
    ok &= check("контроль: E освобождён под заблокированным B -> review_dependency_leak",
                G2["review_dependency_leak"] > 0, dict(G2))
    # 3. опознание: нет своего - тикет и ничего не рисуется; чужое в задании - ворота
    C = FakeC()
    C.add("EXACT_COPY_PEER", "A:1", "X:1")
    M = ["A:1", "X:1"]
    g, jobs = plan(M, C, ident={"X:1": "golden cabinet"})
    ok &= check("нет своего опознания у якоря: IDENTITY_MISSING, заданий нет",
                [t["kind"] for t in g["tickets"]] == ["IDENTITY_MISSING"] and not jobs and
                g["status"]["X:1"] == "BLOCKED_UPSTREAM", (g["tickets"], g["status"]))
    g["status"]["A:1"] = "RENDER"
    bad = [{"job_id": "r01", "group_id": g["group_id"], "render_asset": "A:1", "render_unit": ["A:1"],
            "identity": "golden cabinet", "identity_source": "X:1"}]
    g["tickets"] = []
    G, _ = gates(g, bad, C)
    ok &= check("контроль: опознание X:1 в задании A:1 -> identity_borrowed",
                G["identity_borrowed_from_other_asset"] > 0, dict(G))
    # 4. перекраска не исполняется, ниже неё - BLOCKED_UPSTREAM
    C = FakeC()
    C.add("RECOLOR_OF", "B:1", "A:1")
    C.add("EXACT_COPY_PEER", "B:1", "F:1")
    M = ["A:1", "B:1", "F:1"]
    g, jobs = plan(M, C)
    ok &= check("перекраска: B DERIVE_NOT_VERIFIED, F ниже BLOCKED_UPSTREAM, A рисуется",
                g["status"] == {"A:1": "RENDER", "B:1": "DERIVE_NOT_VERIFIED", "F:1": "BLOCKED_UPSTREAM"},
                g["status"])
    G, det = gates(g, jobs, C)
    ok &= check("перекраска: все ворота 0", clean(G), dict(det))
    # 5. структура и рельеф - только план; задание на них открывает ворота
    C = FakeC()
    C.add("EXACT_MIRROR_PEER", "W:1", "W:2")
    M = ["W:1", "W:2"]
    g, jobs = plan(M, C, rw=rows(M, "STRUCTURAL_SURFACE"), origin=("W",))
    ok &= check("структура: оба PLAN_ONLY_STRUCTURAL, заданий нет",
                set(g["status"].values()) == {"PLAN_ONLY_STRUCTURAL"} and not jobs, g["status"])
    G, det = gates(g, jobs, C)
    ok &= check("структура: все ворота 0", clean(G), dict(det))
    forced = [{"job_id": "r01", "group_id": g["group_id"], "render_asset": "W:1", "render_unit": ["W:1"],
               "identity": "wall", "identity_source": "W:1"}]
    g["status"]["W:1"] = "RENDER"
    G, _ = gates(g, forced, C)
    ok &= check("контроль: структура в задании -> wrongly_sent_to_object_renderer",
                G["wrongly_sent_to_object_renderer"] > 0, dict(G))
    # 6. составной: одна единица; PHOTO_STRUCT_V1 только одиночные - RENDERER_UNSUPPORTED, с поддержкой - рисуется
    C = FakeC()
    C.add("COMPOSITE_PART", "P:1", "P:2", group="composite")
    C.add("EXACT_COPY_PEER", "P:2", "Q:2")
    C.add("EXACT_COPY_PEER", "P:1", "Q:1")
    C.add("COMPOSITE_PART", "Q:1", "Q:2", group="composite")
    M = ["P:1", "P:2", "Q:1", "Q:2"]
    comp = {k: {"keys": ["P:1", "P:2"], "src": [], "map": "", "at": [], "rank": 1} for k in ("P:1", "P:2")}
    g, jobs = plan(M, C, rw=rows(M, "OBJECT_PART"), comp=comp, origin=("P",))
    ok &= check("составной: единица P рендеру не по силам, Q ниже - BLOCKED_UPSTREAM",
                g["status"]["P:1"] == "RENDERER_UNSUPPORTED" and g["status"]["Q:2"] == "BLOCKED_UPSTREAM", g["status"])
    g, jobs = plan(M, C, rw=rows(M, "OBJECT_PART"), comp=comp, supports=("SINGLE", "ASSEMBLY"), origin=("P",))
    ok &= check("составной с поддержкой: P рисуется одной единицей, Q выводится по кадрам",
                g["status"] == {"P:1": "RENDER", "P:2": "RENDER", "Q:1": "DERIVE", "Q:2": "DERIVE"} and
                jobs[0]["render_unit"] == ["P:1", "P:2"], (g["status"], jobs))
    G, det = gates(g, jobs, C)
    ok &= check("составной с поддержкой: все ворота 0", clean(G), dict(det))
    g2 = copy.deepcopy(g)
    g2["unit_of"]["P:2"] = "u:P:2"
    g2["units"]["u:P:2"] = {"frames": ["P:2"], "kind": "SINGLE"}
    G2, _ = gates(g2, jobs, C)
    ok &= check("контроль: составной разрезан -> relation_decision_lost", G2["relation_decision_lost_in_handoff"] > 0,
                dict(G2))
    # 7. вопрос между двумя единицами составного держит их, но не третью (независимую) единицу в группе
    C = FakeC()
    C.add("EXACT_COPY_PEER", "A:1", "B:1")
    C.add("EXACT_COPY_PEER", "A:1", "D:1")
    C.add("COMPOSITE_PART", "B:1", "D:1", ex=CA, tl=TO, group="composite")
    C.add("EXACT_COPY_PEER", "A:1", "K:1")
    M = ["A:1", "B:1", "D:1", "K:1"]
    g, jobs = plan(M, C)
    ok &= check("кандидат составного B~D: B и D держатся, K и A идут",
                g["status"] == {"A:1": "RENDER", "B:1": "BLOCKED_REVIEW", "D:1": "BLOCKED_REVIEW", "K:1": "DERIVE"},
                g["status"])
    # 8. открытый вопрос на якоре: держит всё дерево
    C = FakeC()
    C.add("EXACT_COPY_PEER", "A:1", "B:1")
    C.add("ALIGNED_RECOLOR", "A:1", "Z:9", ex=S, tl=TO)
    g, jobs = plan(["A:1", "B:1"], C)
    ok &= check("TYPE_OPEN на якоре: A ревью, B ниже, заданий нет",
                g["status"] == {"A:1": "BLOCKED_REVIEW", "B:1": "BLOCKED_UPSTREAM"} and not jobs, g["status"])
    G, det = gates(g, jobs, C)
    ok &= check("TYPE_OPEN на якоре: все ворота 0", clean(G), dict(det))
    g2 = copy.deepcopy(g)
    g2["status"]["A:1"] = "RENDER"
    g2["tickets"] = []
    j2 = [{"job_id": "r01", "group_id": g2["group_id"], "render_asset": "A:1", "render_unit": ["A:1"],
           "identity": "thing", "identity_source": "A:1"}]
    G2, _ = gates(g2, j2, C)
    ok &= check("контроль: якорь с TYPE_OPEN в задании -> dangerous_independent_render",
                G2["dangerous_independent_render"] > 0, dict(G2))
    # 8б. расхождение с holdout V7 по паре - тикет на пару; контроль: пара исполняется - ворота
    C = FakeC()
    C.add("EXACT_COPY_PEER", "A:1", "B:1")
    C.add("EXACT_COPY_PEER", "A:1", "D:1")
    rep = {"lost": [], "weaker": [], "stronger": [],
           "type_changed": ["B:1 EXACT_COPY_PEER A:1~B:1/STRONG -> RECOLOR_PEER"]}
    g = R.plan_group_r2(["A:1", "B:1", "D:1"], C, rows(["A:1", "B:1", "D:1"]), {"A"}, {},
                        {"A:1": "t", "B:1": "t", "D:1": "t"}, replay=R.replay_pairs(rep))
    g["group_id"], g["kinds"] = "g:A:1", {}
    ok &= check("расхождение с V7 по A~B: A и B ревью, D ниже A - BLOCKED_UPSTREAM",
                g["status"] == {"A:1": "BLOCKED_REVIEW", "B:1": "BLOCKED_REVIEW", "D:1": "BLOCKED_UPSTREAM"},
                g["status"])
    G, det = R.gates_r2([g], [], C, rep)
    ok &= check("расхождение с V7: все ворота 0", clean(G), dict(det))
    g2 = copy.deepcopy(g)
    g2["status"]["B:1"] = "DERIVE"
    G2, _ = R.gates_r2([g2], [], C, rep)
    ok &= check("контроль: пара расхождения исполняется -> relation_decision_lost",
                G2["relation_decision_lost_in_handoff"] > 0, dict(G2))
    # 9. второй рендер в одной группе связей
    g2 = copy.deepcopy(plan(["A:1", "B:1"], FakeC())[0])
    G2, _ = R.gates_r2([g2], [{"job_id": "r01", "group_id": g2["group_id"], "render_asset": g2["anchor"],
                               "render_unit": [g2["anchor"]], "identity": "t", "identity_source": g2["anchor"]}] * 2,
                       FakeC())
    ok &= check("контроль: два задания в группе -> unexpected_duplicate_creative_render",
                G2["unexpected_duplicate_creative_render"] > 0, dict(G2))
    print("ИТОГ:", "все проверки прошли" if ok else "ЕСТЬ ПРОВАЛЫ")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
