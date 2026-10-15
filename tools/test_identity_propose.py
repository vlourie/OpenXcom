#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""identity_propose: ответ модели -> предложение, без модели и без видеокарты (Pipeline v2, P1-B).

  * ответ всегда PROPOSED, никогда не подтверждение;
  * UNKNOWN вместо догадки: пустое имя, категория UNKNOWN, уверенность 0.3 и ниже;
  * «предмет или рельеф?» без явного relief_decision - UNKNOWN с неоднозначностью;
  * потолки уверенности кодом: без опоры на картинку <= 0.6, без альтернатив <= 0.7
    (прогон 29.09: 150 ответов из 150 на 0.85-0.95 - число модели ничего не различало);
  * сводка по п.6: уровни уверенности, UNKNOWN, неоднозначные рельефы, источники;
  * версия запроса: правка текста меняет ask_rev.

    py -3.13 tools/test_identity_propose.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
sys.stdout.reconfigure(encoding="utf-8")

import identity_propose as ip           # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


OBJ = {"asset_id": "A:1", "asset_class": "object"}
REL = {"asset_id": "R:1", "asset_class": "object_or_relief"}
good = {"proposed_name": "Wooden Chair", "proposed_category": "furniture", "short_description": "a wooden chair",
        "confidence": 0.9, "evidence": ["picture", "mcd"], "alternatives": ["stool"], "picture_alone": "chair"}

p = ip.normalize(dict(good), OBJ)
check("обычный ответ - PROPOSED, уверенность как сказала модель", p["status"] == "PROPOSED" and p["confidence"] == 0.9
      and p["proposed_name"] == "Wooden Chair" and p["alternatives"] == ["stool"])
p = ip.normalize(dict(good, evidence=["tileset_name", "mcd"]), OBJ)
check("без картинки в основаниях - не выше 0.6", p["confidence"] == 0.6)
p = ip.normalize(dict(good, alternatives=[]), OBJ)
check("без альтернатив - не выше 0.7", p["confidence"] == 0.7)
p = ip.normalize(dict(good, confidence=0.25), OBJ)
check("уверенность 0.25 - UNKNOWN, догадка записана в неоднозначность",
      p["proposed_name"] == "UNKNOWN" and p["short_description"] == "" and "Wooden Chair" in p["ambiguity"])
p = ip.normalize(dict(good, proposed_name="UNKNOWN", ambiguity="chair or crate"), OBJ)
check("UNKNOWN модели - UNKNOWN с её сомнением", p["proposed_name"] == "UNKNOWN" and p["ambiguity"] == "chair or crate")
p = ip.normalize(dict(good, proposed_name=""), OBJ)
check("пустое имя - UNKNOWN с причиной", p["proposed_name"] == "UNKNOWN" and p["ambiguity"])
p = ip.normalize(dict(good, evidence=["made_up"]), OBJ)
check("неизвестные основания отброшены", p["evidence"] == ["picture"])
p = ip.normalize(dict(good, proposed_category="spaceship"), OBJ)
check("неизвестная категория - other", p["proposed_category"] == "other")

p = ip.normalize(dict(good, proposed_name="Grass Mound"), REL)
check("рельеф без relief_decision - UNKNOWN", p["proposed_name"] == "UNKNOWN" and "Grass Mound" in p["ambiguity"])
p = ip.normalize(dict(good, proposed_name="Grass Mound", relief_decision="unsure"), REL)
check("рельеф unsure - UNKNOWN", p["proposed_name"] == "UNKNOWN")
p = ip.normalize(dict(good, proposed_name="Hay Bale", relief_decision="object"), REL)
check("рельеф object - предложение", p["proposed_name"] == "Hay Bale" and p["relief_decision"] == "object")
p = ip.normalize(dict(good, relief_decision="object"), OBJ)
check("у обычного предмета relief_decision не пишется", p["relief_decision"] == "")

props = {"a": ip.normalize(dict(good), OBJ),
         "b": ip.normalize(dict(good, confidence=0.5, evidence=["picture", "map_context"]), OBJ),
         "c": ip.normalize(dict(good, confidence=0.4, evidence=["picture"]), OBJ),
         "d": ip.normalize(dict(good, proposed_name="X", relief_decision="unsure"), REL),
         "e": ip.normalize(dict(good, proposed_name="Hay", relief_decision="object", confidence=0.5), REL)}
s = ip.stats(props, {"z": {"error": "x"}})
check("сводка: всего с ошибками", s["total processed"] == 6 and s["errors"] == 1)
# известные: a 0.9 (high), b 0.5 и e 0.5 (medium), c 0.4 (low); d - UNKNOWN
check("сводка: уровни уверенности",
      (s["high confidence"], s["medium confidence"], s["low confidence"]) == (1, 2, 1))
check("сводка: UNKNOWN и неоднозначные рельефы (d unsure, e ниже 0.6)",
      s["UNKNOWN"] == 1 and s["object/terrain ambiguous"] == 2)
check("сводка: источники (b карта; a, e данные; c только картинка)",
      s["with map context"] == 1 and s["with MCD/ruleset"] == 2 and s["visual only"] == 1)

# два независимых ответа
def ans(name, cat="furniture", relief="", conf=0.9, cls=OBJ):
    d = dict(good, proposed_name=name, proposed_category=cat, confidence=conf)
    if relief:
        d["relief_decision"] = relief
    return ip.normalize(d, cls)


c = ip.combine(ans("Wooden Chair"), ans("chair", conf=0.8))
check("совпали (тот же предмет, та же категория) - PROPOSED, меньшая из двух",
      c["status"] == "PROPOSED" and c["verdict"] == "agree" and c["confidence"] == 0.8
      and c["proposed_name"] == "Wooden Chair" and c["second"]["proposed_name"] == "chair")
c = ip.combine(ans("Hay Bale", "goods or small items"), ans("wood pile", "goods or small items"))
check("тюк сена / поленница - REVIEW_REQUIRED: имени нет, уверенность 0, догадки только в candidates",
      c["status"] == "REVIEW_REQUIRED" and c["proposed_name"] == "UNKNOWN" and c["confidence"] == 0
      and "Hay Bale" not in c["ambiguity"] and "wood pile" not in c["ambiguity"] and c["short_description"] == ""
      and [x["proposed_name"] for x in c["candidates"]] == ["Hay Bale", "wood pile"])
c = ip.combine(ans("Crypt Barrel"), ans("Crypt Pillar", "wall or building part"))
check("общее прилагательное, разные предметы (barrel / pillar) - REVIEW_REQUIRED", c["status"] == "REVIEW_REQUIRED")
check("общее прилагательное при той же категории - тоже разные предметы (wooden crate / wooden table)",
      ip.verdict(ans("wooden crate"), ans("wooden table")) == "conflict")
c = ip.combine(ans("Grass Mound", "rock or terrain relief", "relief", cls=REL),
               ans("Grass Mound", "rock or terrain relief", "object", cls=REL))
check("рельеф: решения object/relief разошлись - REVIEW_REQUIRED без имени",
      c["proposed_name"] == "UNKNOWN" and c["status"] == "REVIEW_REQUIRED" and not c["consistent"])
c = ip.combine(ans("Grass Mound", "rock or terrain relief", "relief", cls=REL),
               ans("grassy mounds", "rock or terrain relief", "relief", cls=REL))
check("рельеф: совпали (mound/mounds) - предложение", c["proposed_name"] == "Grass Mound" and c["status"] == "PROPOSED")
c = ip.combine(ip.normalize(dict(good, proposed_name="UNKNOWN"), OBJ), ip.normalize(dict(good, proposed_name="UNKNOWN"), OBJ))
check("оба UNKNOWN - UNKNOWN без догадок", c["status"] == "UNKNOWN" and not c["candidates"])
c = ip.combine(ip.normalize(dict(good, proposed_name="UNKNOWN"), OBJ), ans("lamp"))
check("один UNKNOWN - UNKNOWN, названное - скрытая догадка",
      c["status"] == "UNKNOWN" and c["proposed_name"] == "UNKNOWN" and [x["proposed_name"] for x in c["candidates"]] == ["lamp"])
check("стоп-слова не дают ложного согласия", ip.verdict(ans("small crate"), ans("small lamp")) == "conflict")
c = ip.combine(ans("crashed plane fuselage", "vehicle or vehicle part"), ans("crashed plane fuselage", "debris or junk"))
check("имя то же, категория нет - PROPOSED не выше 0.6, спор о категории в неоднозначности",
      c["status"] == "PROPOSED" and c["verdict"] == "category" and c["confidence"] == 0.6
      and "категория разошлась" in c["ambiguity"])
c = ip.combine(ans("Grass Mound", "plant or nature", "relief", cls=REL),
               ans("grass mound", "rock or terrain relief", "relief", cls=REL))
check("рельеф: имя и решение те же, категория нет - предложение, а не UNKNOWN",
      c["proposed_name"] == "Grass Mound" and c["consistent"] and c["confidence"] == 0.6)
check("слово внутри слова: armchair / chair - согласие", ip.verdict(ans("armchair"), ans("Chair")) == "agree")
check("короткое слово внутри не считается: pod / tripod", ip.verdict(ans("pod"), ans("tripod")) == "conflict")
check("главное слово одного среди слов другого: hay bale / bale of hay",
      ip.verdict(ans("Hay Bale"), ans("bale of hay")) == "agree")
check("мн. число: wooden boxes / box, shelves / shelf",
      ip.verdict(ans("wooden boxes"), ans("box")) == "agree" and ip.verdict(ans("shelves"), ans("shelf")) == "agree")
check("общее слово пропускается: storage unit / storage cabinet - главное слово storage / cabinet",
      ip.head("storage unit") == "storage")
c = ip.combine(ans("structural pillar"), ans("Support column", "wall or building part"))
check("синонимы (pillar / column) - PROPOSED_AMBIGUOUS не выше 0.5, оба слова в неоднозначности",
      c["status"] == "PROPOSED_AMBIGUOUS" and c["verdict"] == "synonym" and c["confidence"] == 0.5
      and "pillar" in c["ambiguity"] and "column" in c["ambiguity"])
for x, y in (("crate", "box"), ("sofa", "couch"), ("lamp", "floor lamp"), ("wreckage", "debris")):
    got = ip.verdict(ans(x), ans(y))
    check("%s / %s - согласие (%s)" % (x, y, got), got in ("agree", "synonym"))
check("barrel / pillar - разные предметы", ip.verdict(ans("barrel"), ans("pillar")) == "conflict")
# приставка (замечания 29.09): главное слово то же, а предмет разный
check("table with computer / table with lamp - разные предметы",
      ip.verdict(ans("table with computer"), ans("table with lamp")) == "conflict")
check("rack with bottles / rack containing weapons - разные предметы",
      ip.verdict(ans("rack with bottles"), ans("rack containing weapons")) == "conflict")
check("bush with berries / berry bush - согласие", ip.verdict(ans("bush with berries"), ans("berry bush")) == "agree")
check("desk with computer / computer desk - согласие",
      ip.verdict(ans("desk with computer"), ans("computer desk")) == "agree")
check("table with computer / table - приставка у одного: близко, решает человек",
      ip.verdict(ans("table with computer"), ans("wooden table")) == "synonym")
check("shelf with bottles / shelves full of bottles - согласие",
      ip.verdict(ans("shelf with bottles"), ans("shelves full of bottles")) == "agree")
check("wall-mounted lamp - это лампа, а не стена", ip.head("wall-mounted lamp") == "lamp"
      and ip.verdict(ans("wall-mounted lamp"), ans("lamp")) == "agree")
check("lamp mounted on wall / lamp - приставка у одного", ip.head("lamp mounted on wall") == "lamp"
      and ip.attachment("lamp mounted on wall") == {"wall"})
check("table with lamp / table with light - приставки только через синонимы: близко",
      ip.verdict(ans("table with lamp"), ans("table with light")) == "synonym")
c = ip.combine(ans("Hay Bale"), ans("wood pile"))
check("оба ответа хранятся целиком, с материалом",
      c["first"]["proposed_name"] == "Hay Bale" and c["second"]["proposed_name"] == "wood pile"
      and "proposed_material" in c["first"])
# пересведение без модели: запись прежнего правила (rule 2) -> новый статус по first/second
old_rec = dict(c, status="PROPOSED", proposed_name="Hay Bale", confidence=0.4, consistent=False)
old_rec.pop("verdict")
r = ip.reconcile(old_rec)
check("reconcile: старая запись пересводится по first/second", r["status"] == "REVIEW_REQUIRED"
      and r["reconcile_rule"] == ip.RECONCILE_RULE and r["proposed_name"] == "UNKNOWN")
check("reconcile идемпотентен", ip.reconcile(r) == r)

# сводка: четыре числа и матрица
props = {"a": ip.combine(ans("chair"), ans("chair")),
         "b": ip.combine(ans("pillar"), ans("column")),
         "c": ip.combine(ans("fuselage", "vehicle or vehicle part"), ans("fuselage", "debris or junk")),
         "d": ip.combine(ans("barrel"), ans("pillar")),
         "e": ip.combine(ip.normalize(dict(good, proposed_name="UNKNOWN"), OBJ), ans("lamp"))}
s = ip.stats(props, {})
check("четыре числа: согласие 2 (точно 1, синонимы 1), категория 1, разошлись 1, UNKNOWN 1",
      (s["exact/near agreement"], s["  exact (same words)"], s["  near (synonyms, PROPOSED_AMBIGUOUS)"],
       s["category-only disagreement"], s["true semantic disagreement (REVIEW_REQUIRED)"],
       s["UNKNOWN (model did not identify)"]) == (2, 1, 1, 1, 1, 1))
check("уровни разбора: EASY 2, LIGHT 1, HARD 1, UNKNOWN 1",
      (s["review AUTO_REVIEW_EASY"], s["review HUMAN_REVIEW_LIGHT"], s["review HUMAN_REVIEW_HARD"],
       s["review UNKNOWN"]) == (2, 1, 1, 1))
check("приставка у одного - LIGHT, синоним без приставки - EASY",
      ip.combine(ans("table with computer"), ans("table"))["review_level"] == "HUMAN_REVIEW_LIGHT"
      and ip.combine(ans("crate"), ans("box"))["review_level"] == "AUTO_REVIEW_EASY")
m = ip.matrix(props)
check("матрица: строка по основаниям ответа (picture + mcd - MCD/ruleset)",
      any(x.startswith("MCD/ruleset supported") for x in m))
# когорты - по тому, что было дано в запросе
props["a"]["facts"] = {"mcd": {"burns": True}, "map_example": "X", "family": [{"key": "S:1"}], "neighbours": []}
props["d"]["facts"] = {"mcd": {"burns": False}, "map_example": "", "family": [], "other_sides": [],
                       "neighbours": [{"what": "lamp"}]}
check("когорты по фактам запроса",
      ip.cohorts(props["a"]) == ["MCD informative", "map context available", "family context available",
                                 "no named neighbours"]
      and ip.cohorts(props["d"]) == ["MCD generic", "map context unavailable", "family context unavailable",
                                     "named neighbours"]
      and ip.cohorts(props["e"])[0] == "no MCD")
ct = ip.cohort_table(props)
check("таблица когорт: MCD informative - 100% согласие, MCD generic - 100% расхождение",
      any(x.startswith("MCD informative") and "100%" in x.split()[3] for x in ct)
      and any(x.startswith("MCD generic") and x.split()[-2] == "100%" for x in ct))
check("тип расхождения: barrel / pillar - нет общих слов, та же категория",
      ip.conflict_type(props["d"]) == "no shared words, same category")
check("тип расхождения: Freighter Wall Corner / wall corner post - общие слова",
      ip.conflict_type(ip.combine(ans("Freighter Wall Corner"), ans("wall corner post"))).startswith("shared words"))
check("тип расхождения: table with computer / table with lamp - приставка",
      ip.conflict_type(ip.combine(ans("table with computer"), ans("table with lamp"))) == "attachment differs")
check("таблица типов HARD", any(x.startswith("HARD by conflict type") for x in ip.conflict_table(props)))
dp = ip.disagreement_pairs(props)
check("пары расхождений: barrel / pillar", any(x.strip() == "1  barrel / pillar" for x in dp))

check("ask_rev не зависит от правила сведения: прогон #274 не переспрашивается", ip.ask_rev() == "c1dda81474ee")
old = ip.ask_rev()
ip.RECONCILE_RULE += 1
check("правка правила сведения ask_rev не меняет", ip.ask_rev() == old)
ip.ASK += " "
check("правка запроса меняет ask_rev", ip.ask_rev() != old)

print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
