#!/usr/bin/env python3
"""Проверка правки R3.1 (tools/hdart/hd_e2e_v1_r31.py): ATTACHMENT_CANDIDATE не меняет прямой рисунок концов.
Положительные случаи - примыкание отпускает рисунок и копии, в мирах «принято» и «отвергнуто» решение рисовать то
же; отрицательные - составной и повтор сборки по-прежнему держат концы, а без правки R3.1 примыкание держит.

    py -3.13 tools/test_hd_e2e_v1_r31.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
sys.path.insert(0, HERE)
import hd_e2e_v1_r3 as R3                          # noqa: E402
import hd_e2e_v1_r31 as R31                        # noqa: E402
import test_hd_e2e_v1_r3 as T                      # noqa: E402

CA, TO = T.CA, T.TO
T.GROUP.setdefault("REPEATED_ASSEMBLY_RELATION", "assembly_open")


def worlds(r):
    """Отпущенные рисунки и выводы плана в мирах: решение отвергнуто (нет форм) и принято (все формы)."""
    base = R3.UF()
    for k in r["keys"]:
        base.find(k)
    renders = [k for k, s in r["st"].items() if s == "RENDER"]
    derived = {}
    for g in r["groups"]:
        for k in g["members"]:
            if g["status"][k] == "DERIVE":
                derived[k] = (g["anchor"], g["prod"][k]["from"], g["prod"][k]["via"])
    forms = [e for d in r["D"].values() for e in d["forms"]]
    return (R3.world_check(base, r["ae"], [], renders, derived),
            R3.world_check(base, r["ae"], forms, renders, derived))


def main():
    ok = True
    check, clean = T.check, T.clean
    # 1. примыкание A~B между отдельными предметами: оба рисуются, тикет на связь есть
    C = T.FakeC()
    C.add("ATTACHMENT_CANDIDATE", "A:1", "B:1", ex=CA, tl=TO)
    with R31.semantics():
        r = T.run([["A:1"], ["B:1"]], C)
        e = R3.forms_of(C.of("A:1")[0])[0]
        ctx = R3.Ctx(r["ae"], r["D"], r["keys"])
        aff = [R3.candidate_affects_action(e, k, "RENDER", ctx)[0] for k in ("A:1", "B:1")]
        rej, acc = worlds(r)
    ok &= check("1 примыкание: A и B рисуются", r["st"] == {"A:1": "RENDER", "B:1": "RENDER"}, r["st"])
    ok &= check("1 форма ATTACH, candidate_affects_action(DIRECT_RENDER) = NO у обоих концов",
                e[0] == "ATTACH" and aff == ["NO", "NO"], (e, aff))
    ok &= check("1 тикет на связь остаётся (UNRESOLVED_RELATION)",
                any(t["kind"] == "UNRESOLVED_RELATION" for t in r["tickets"]), [t["kind"] for t in r["tickets"]])
    ok &= check("1 принято и отвергнуто - решение рисовать то же, ворота чистые",
                not rej and not acc and T.clean(r["G"]), (rej, acc, dict(r["G"])))
    #    контроль: без правки R3.1 (как R3) примыкание держит оба конца, а отпущенный в нём рисунок ломается миром
    r0 = T.run([["A:1"], ["B:1"]], C)
    ok &= check("1 контроль R3: оба конца на ревью", r0["st"] == {"A:1": "BLOCKED_REVIEW", "B:1": "BLOCKED_REVIEW"},
                r0["st"])
    base = R3.UF()
    for k in r0["keys"]:
        base.find(k)
    tog = [x for d in r0["D"].values() for x in d["forms"]]
    ok &= check("1 контроль R3: в мире R3 «принято» рисунок A - кусок сборки",
                bool(R3.world_check(base, r0["ae"], tog, ["A:1"], {})), tog)
    # 2. примыкание у точной копии: якорь и копии идут, как у MILWARE:17 / URBAN40K:86
    C = T.FakeC()
    C.add("EXACT_COPY_PEER", "A:2", "B:2")
    C.add("EXACT_COPY_PEER", "A:2", "D:2")
    C.add("ATTACHMENT_CANDIDATE", "X:2", "B:2", ex=CA, tl=TO)
    with R31.semantics():
        r = T.run([["A:2", "B:2", "D:2"], ["X:2"]], C, ident={"A:2": "a", "X:2": "x"})
        rej, acc = worlds(r)
    ok &= check("2 примыкание у копии B: A RENDER, B и D - копии, X рисуется",
                (r["st"]["A:2"], r["st"]["B:2"], r["st"]["D:2"], r["st"]["X:2"]) ==
                ("RENDER", "DERIVE", "DERIVE", "RENDER"), r["st"])
    ok &= check("2 принято и отвергнуто - без нарушений, ворота чистые", not rej and not acc and clean(r["G"]),
                (rej, acc, dict(r["G"])))
    # 3. отрицательные: составной и повтор сборки по-прежнему держат концы и при R3.1
    for typ in ("COMPOSITE_PART", "REPEATED_ASSEMBLY_RELATION"):
        C = T.FakeC()
        C.add(typ, "A:3", "B:3", ex=CA, tl=TO)
        with R31.semantics():
            r = T.run([["A:3"], ["B:3"]], C)
        ok &= check("3 %s при R3.1: оба конца на ревью" % typ,
                    r["st"] == {"A:3": "BLOCKED_REVIEW", "B:3": "BLOCKED_REVIEW"} and clean(r["G"]), r["st"])
    # 4. примыкание не прячет другие причины: улика на том же кадре держит его
    C = T.FakeC()
    C.add("ATTACHMENT_CANDIDATE", "A:4", "B:4", ex=CA, tl=TO)
    C.evidence["A:4"].append({"rule": "R7", "why": "alternate_view"})
    with R31.semantics():
        r = T.run([["A:4"], ["B:4"]], C)
    ok &= check("4 примыкание + улика на A: A на ревью, B рисуется",
                r["st"] == {"A:4": "BLOCKED_REVIEW", "B:4": "RENDER"} and clean(r["G"]), r["st"])
    # 5. правка снимается после вызова: R3 вне semantics() прежний
    ok &= check("5 вне semantics() R3.edge_of прежний", R3.edge_of("ATTACHMENT_CANDIDATE", "A", "B", "A", "B")[0][0]
                == "TOG", R3.edge_of("ATTACHMENT_CANDIDATE", "A", "B", "A", "B"))
    print("ВСЁ ВЕРНО" if ok else "ЕСТЬ ОШИБКИ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
