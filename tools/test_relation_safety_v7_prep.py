#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка relation_safety_v7_prep на синтетике, без установки игры (RELATION_SAFETY_MODEL_V7_PREP, специалист 02.10).

  related_frame_safety_recall:
  - кадр с истинным COMPOSITE и кандидатом на этой паре - найден, действие REVIEW
  - кадр с истинной связью без утверждения - промах
  - утверждение только на паре NONE не спасает кадр с пропущенной истинной связью
  - кадр только с парами NONE - не в знаменателе
  - RELATED с открытым подтипом (открыт COMPOSITE) - в знаменателе; только STRUCTURAL_COUNTERPART - нет
  - STRONG направленный, кадр - основа: CANONICAL; кадр - выводимая сторона: BLOCK
  REPEATED_ASSEMBLY_RELATION:
  - довод RC переписан: детектор RAR, группа assembly_open, CANDIDATE, TYPE_OPEN
  - в составной (v4.recall composite) не голосует, а кадр для безопасности найден
  - контроль: тот же довод без переписи голосует за составной
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
import relation_discovery_v2 as v2                              # noqa: E402
import relation_discovery_v4 as v4                              # noqa: E402
import relation_safety_v7_prep as s7                            # noqa: E402
import v5_ar2_recount as rc                                     # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def claim(a, b, group, existence="RELATED_CANDIDATE", type_level="TYPE_OPEN", typ="COMPOSITE_PART", det="ASM"):
    return {"pair": sorted((a, b)), "group": group, "existence": existence, "type_level": type_level, "type": typ,
            "source": a, "target": b, "support": [{"detector": det, "level": "CANDIDATE", "type": typ}]}


REL_COMP = ("RELATED", {"COMPOSITE"}, set())
REL_OPEN = ("RELATED", set(), {"COMPOSITE"})
REL_CTR = ("RELATED", {"STRUCTURAL_COUNTERPART"}, set())
REL_REC = ("RELATED", {"RECOLOR_PEER"}, set())
NONE = ("NONE", set(), set())

pc = [("A:1", "A:2", REL_COMP, [claim("A:1", "A:2", "composite")]),          # найден, REVIEW
      ("B:1", "B:2", REL_COMP, []),                                         # промах
      ("C:1", "C:9", NONE, [claim("C:1", "C:9", "composite")]),             # NONE не спасает
      ("C:1", "C:2", REL_REC, []),
      ("D:1", "D:2", NONE, []),                                             # не в знаменателе
      ("E:1", "E:2", REL_OPEN, [claim("E:1", "E:2", "composite")]),         # открытый подтип - в знаменателе
      ("F:1", "F:2", REL_CTR, []),                                          # не значимый ярлык
      ("G:1", "G:2", REL_REC, [claim("G:2", "G:1", "derived", "RELATED_STRONG", "TYPE_STRONG", "RECOLOR_OF")]),
      ("H:1", "H:2", REL_REC, [claim("H:1", "H:2", "derived", "RELATED_STRONG", "TYPE_STRONG", "RECOLOR_OF")])]
keys = ["A:1", "B:1", "C:1", "D:1", "E:1", "F:1", "G:1", "H:1"]
r = s7.related_frame_safety(pc, keys)
check("знаменатель: A B C E G H (D только NONE, F только STRUCTURAL_COUNTERPART)", r["n"] == 6)
check("найдено 4 из 6 (A, E, G, H); промахи B и C", r["hit"] == 4 and sorted(r["missed"]) == ["B:1", "C:1"])
check("значение 0.667", abs(r["value"] - 0.667) < 1e-9)
check("кадр-основа направленного STRONG - CANONICAL, выводимый - BLOCK, кандидат - REVIEW",
      r["by_best_action"] == {"REVIEW": 2, "CANONICAL": 1, "BLOCK": 1})
check("вариант только BLOCK+REVIEW: 3 из 6", abs(r["variant_block_review_only"] - 0.5) < 1e-9)
check("вариант по закрытым значимым ярлыкам: E выпадает, 3 из 5",
      r["variant_closed_relevant_frames"] == {"value": 0.6, "n": 5})

# ---------------------------------------------------------------- переклассификация RC
raw = v2.edge("COMPOSITE_PART", "HULL:5", "HULL:0", "CANDIDATE", "ASMR", "RC", "синтетика")
raw["scores"] = {"anchor": "HULL:0"}
e = s7.reclass_rc(raw)
check("RC -> RAR, REPEATED_ASSEMBLY_RELATION, CANDIDATE",
      e["detector"] == "RAR" and e["type"] == "REPEATED_ASSEMBLY_RELATION" and e["level"] == "CANDIDATE"
      and e["scores"]["source_detector"] == "ASMR" and e["scores"]["anchor"] == "HULL:0")
check("исходный довод не изменён", raw["detector"] == "ASMR" and "v7_class" not in raw["scores"])
try:
    s7.reclass_rc(dict(raw, detector="ASM2"))
    check("не довод RC - отказ", False)
except SystemExit:
    check("не довод RC - отказ", True)

EMPTY3, EMPTY4 = {"edges": [], "self_roles": {}}, {"edges": []}
C = rc.claims([], EMPTY3, EMPTY4, [e])
cs = C.pair("HULL:5", "HULL:0")
check("утверждение: группа assembly_open, CANDIDATE, TYPE_OPEN",
      len(cs) == 1 and cs[0]["group"] == "assembly_open" and cs[0]["existence"] == rc.CAND
      and cs[0]["type_level"] == v4.T_OPEN)
pc2 = [("HULL:5", "HULL:0", REL_COMP, cs)]
check("RAR не голосует за составной", v4.recall([(REL_COMP, cs)])["composite"]["discovery"] == 0)
check("RAR находит кадр для безопасности (REVIEW)",
      s7.related_frame_safety(pc2, ["HULL:5"])["hit"] == 1)
C0 = rc.claims([], EMPTY3, EMPTY4, [raw])
cs0 = C0.pair("HULL:5", "HULL:0")
check("контроль: без переписи тот же довод голосует за составной",
      v4.recall([(REL_COMP, cs0)])["composite"]["discovery"] == 1)

print("\n%s: %d провалов" % ("FAIL" if FAILS else "OK", len(FAILS)))
sys.exit(1 if FAILS else 0)
