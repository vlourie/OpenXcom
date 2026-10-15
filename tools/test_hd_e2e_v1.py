#!/usr/bin/env python3
"""Проверка группировки сухого плана HD_PIPELINE_E2E_V1 (tools/hdart/hd_e2e_v1.plan_group) на синтетических
утверждениях: якорь, единица рисования, дерево вывода, удержание на ревью. Контроль: без удержания по
неавтоматическому утверждению кадр с открытым типом попал бы в рендер.

    py -3.13 tools/test_hd_e2e_v1.py
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import hd_e2e_v1 as E                              # noqa: E402
import relation_discovery_v3 as v3                 # noqa: E402

S, C_, TS, TO = v3.STRONG, v3.CAND, v3.T_STRONG, v3.T_OPEN


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


def check(name, cond, got):
    print("%-58s %s" % (name, "ok" if cond else "FAIL %s" % (got,)))
    return cond


def main():
    ok = True
    # перекраска к основе из набора оригинала и копия: якорь - основа, выводы по дереву
    C = FakeC()
    C.add("RECOLOR_OF", "B:1", "A:1")
    C.add("EXACT_COPY_PEER", "A:1", "C:1", group="derived")
    M = ["A:1", "B:1", "C:1"]
    g = E.plan_group(M, C, rows(M), {"B:1"}, {"A"}, {})
    ok &= check("перекраска: якорь основа A:1", g["anchor"] == "A:1" and not g["held"], (g["anchor"], g["held"]))
    ok &= check("перекраска: B:1 выводится из A:1", g["prod"]["B:1"] == {"method": "DERIVE_RECOLOR", "from": "A:1",
                                                                       "via": "RECOLOR_OF"}, g["prod"])
    ok &= check("копия: C:1 COPY из A:1", g["prod"]["C:1"]["method"] == "COPY", g["prod"])
    # две основы у одного выводимого - обратный вывод запрещён, группа на ревью
    C = FakeC()
    C.add("RECOLOR_OF", "X:1", "A:1")
    C.add("RECOLOR_OF", "X:1", "B:2")
    M = ["A:1", "B:2", "X:1"]
    g = E.plan_group(M, C, rows(M), {"X:1"}, {"A"}, {})
    ok &= check("две основы: REVERSE_DERIVATION", any(h.startswith("REVERSE_DERIVATION") for h in g["held"]), g["held"])
    # составной: одна единица рисования, самороль закрыта парой
    C = FakeC()
    C.add("COMPOSITE_PART", "P:1", "P:2", group="composite")
    C.self_roles["P:1"].append({"type": "COMPOSITE_PART", "level": "STRONG"})
    M = ["P:1", "P:2"]
    comp = {"P:1": {"keys": ["P:1", "P:2"], "src": ["P:1", "P:2"], "map": "", "at": [], "rank": 1}}
    comp["P:2"] = comp["P:1"]
    g = E.plan_group(M, C, rows(M, "OBJECT_PART"), {"P:1"}, set(), comp)
    u = g["units"][g["unit_of"]["P:1"]]
    ok &= check("составной: одна единица ASSEMBLY", u["frames"] == M and u["kind"] == "ASSEMBLY" and not g["held"],
                (u, g["held"]))
    # составной очереди шире единицы - на ревью
    comp3 = {k: {"keys": ["P:1", "P:2", "P:3"], "src": [], "map": "", "at": [], "rank": 1} for k in M}
    g = E.plan_group(M, C, rows(M, "OBJECT_PART"), {"P:1"}, set(), comp3)
    ok &= check("составной неполный: COMPOSITE_INCOMPLETE", any(h.startswith("COMPOSITE_INCOMPLETE") for h in g["held"]),
                g["held"])
    # разрушенный вид: основа рисуется, вид - STATE
    C = FakeC()
    C.add("DESTROYED_VARIANT_OF", "D:2", "D:1", group="state")
    M = ["D:1", "D:2"]
    g = E.plan_group(M, C, rows(M), {"D:2"}, set(), {})
    ok &= check("разрушенный: якорь D:1, D:2 STATE", g["anchor"] == "D:1" and g["prod"]["D:2"]["method"] == "STATE",
                (g["anchor"], g["prod"]))
    # AR2 TYPE_OPEN - на ревью, и контроль: без утверждения кадр рисуется сам
    C = FakeC()
    C.add("ALIGNED_RECOLOR", "R:1", "Q:1", ex=S, tl=TO)
    g = E.plan_group(["R:1"], C, rows(["R:1"]), {"R:1"}, set(), {})
    ok &= check("AR2 TYPE_OPEN: группа на ревью", any(h.startswith("REVIEW_CLAIMS") for h in g["held"]) and
                bool(g["review"]), g["held"])
    g0 = E.plan_group(["R:1"], FakeC(), rows(["R:1"]), {"R:1"}, set(), {})
    ok &= check("контроль: без утверждения - рисуется (держать нечего)", not g0["held"], g0["held"])
    # самороль без цели (STATE_VARIANT_OF R3) - основы нет, на ревью
    C = FakeC()
    C.self_roles["S:1"].append({"type": "STATE_VARIANT_OF", "level": "STRONG"})
    g = E.plan_group(["S:1"], C, rows(["S:1"]), {"S:1"}, set(), {})
    ok &= check("самороль без цели: SELF_ROLE_UNRESOLVED", any(h.startswith("SELF_ROLE_UNRESOLVED") for h in g["held"]),
                g["held"])
    # разные конвейеры в группе - на ревью
    C = FakeC()
    C.add("EXACT_COPY_PEER", "T:1", "U:1")
    rw = rows(["T:1"])
    rw.update(rows(["U:1"], "TERRAIN_RELIEF"))
    g = E.plan_group(["T:1", "U:1"], C, rw, {"T:1", "U:1"}, set(), {})
    ok &= check("конфликт конвейера: PIPELINE_CONFLICT", any(h.startswith("PIPELINE_CONFLICT") for h in g["held"]),
                g["held"])
    print("ИТОГ:", "все проверки прошли" if ok else "ЕСТЬ ПРОВАЛЫ")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
