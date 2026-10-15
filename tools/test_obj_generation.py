#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""obj_generation и asset_rev: что уходит модели, что выводится, что ждёт человека, когда выход устарел
(docs/HD_PIPELINE_V2.md, 12-15, 20, 23; P1-A).

Синтетические очередь и семейства, без карт и модели:
  * прямой член (перекраска, AUTO) - DERIVE от канонического; другой бок AUTO - GENERATE_WITH, не DERIVE;
  * опознание одно на ассет: подтверждён канонический - готов, у членов своей строки опознания нет;
  * неопознанный, предложенный агентом, UNKNOWN - BLOCKED identity; SKIP - не рисовать;
  * кандидаты семейства на проверке - BLOCKED family_review; сам кандидат - BLOCKED in_review;
  * floor_like и structural - EXCLUDE до всякой проверки; object_or_relief - вопрос class_check;
    человек сказал NOT_OBJECT - EXCLUDE;
  * предложение: прежние партии старше подсказки карты; CONFIRM без текста - не подтверждение;
  * партии 10, 50, потом 100;
  * asset_rev: переименование ассета («стул» -> «пивной кран») делает выход STALE по identity_rev.

    py -3.13 tools/test_obj_generation.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))

import asset_rev as ar                  # noqa: E402
import obj_generation as og             # noqa: E402
import obj_struct as os_                # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def item(rank, key, cls="object", hint=""):
    return {"rank": rank, "keys": [key], "src": [key], "kind": "одиночный", "places": 100 - rank,
            "asset_class": cls, "hint": hint}


def mem(key, rel, dec="AUTO", cls="object"):
    return {"keys": [key], "src": [key], "relation": rel, "decision": dec, "asset_class": cls}


def rev(key, reason, rel="recolor"):
    return {"keys": [key], "relation": rel, "reason": reason}


def fam(fid, members, review=(), revision=1):
    return {"family_id": fid, "revision": revision, "canonical": [fid], "content_hash": "h" + fid,
            "members": list(members), "review": list(review)}


items = [item(1, "A:0"), item(2, "A:1"), item(3, "B:0"), item(4, "C:0"), item(5, "D:0"), item(6, "E:0"),
         item(7, "F:0"), item(8, "G:0"), item(9, "H:0"), item(10, "H:1"), item(11, "W:0", "floor_like"),
         item(12, "R:0", os_.UNCERTAIN), item(13, "N:0"), item(14, "S:0", "structural")]
fams = [
    fam("A:0", [mem("A:0", "canonical"), mem("A:1", "recolor")]),
    fam("Q:0", [mem("Q:0", "canonical")], [rev("C:0", "indirect_chain")]),
    fam("E:0", [mem("E:0", "canonical")], [rev("E:9", "alternate_view_possible", "alternate_view")]),
    fam("H:0", [mem("H:0", "canonical"), mem("H:1", "alternate_view")],
        [rev("H:9", "alternate_view_weak", "alternate_view")]),
    fam("S:0", [mem("S:0", "canonical", cls="structural")]),
]
ok_id = {"status": "HUMAN_CONFIRMED", "identity": "x"}
idrows = {"A:0": dict(ok_id, identity="armchair"), "C:0": ok_id, "D:0": {"status": "AGENT_PROPOSED"},
          "E:0": ok_id, "F:0": {"status": "SKIP"}, "G:0": dict(ok_id, status="HUMAN_EDITED"), "H:0": ok_id,
          "R:0": {"status": "AGENT_PROPOSED"}, "N:0": {"status": "NOT_OBJECT"}}
rows = {r["key"]: r for r in og.plan(items, fams, idrows)}
a0, a1 = rows["A:0"], rows["A:1"]
check("перекраска AUTO - DERIVE от канонического", a1["action"] == "DERIVE" and a1["derive_from"] == ["A:0"])
check("канонический опознан - READY, выводы после него", a0["status"] == "READY" and a0["derive_after"] == ["A:1"])
check("член наследует опознание ассета", a1["asset_id"] == "A:0" and a1["identity"] == "armchair")
check("нет опознания - BLOCKED identity", rows["B:0"]["status"] == "BLOCKED" and rows["B:0"]["blockers"] == ["identity"])
check("предложение агента - BLOCKED identity", rows["D:0"]["blockers"] == ["identity"])
check("кандидат цепочки - BLOCKED in_review, хоть и опознан",
      rows["C:0"]["status"] == "BLOCKED" and rows["C:0"]["blockers"] == ["in_review:indirect_chain"])
check("у канонического кандидат другого бока - BLOCKED family_review",
      rows["E:0"]["blockers"] == ["family_review:1"])
check("другой бок AUTO - GENERATE_WITH, не DERIVE",
      rows["H:1"]["action"] == "GENERATE_WITH" and rows["H:0"]["views"] == ["H:1"] and "derive_from" not in rows["H:1"])
check("слабый кандидат другого бока заказ не держит", rows["H:0"]["status"] == "READY")
check("SKIP - не рисовать", rows["F:0"]["status"] == "SKIP")
check("готовый без семейства - READY", rows["G:0"]["status"] == "READY" and rows["G:0"]["family"] == "")
check("floor_like - EXCLUDE", rows["W:0"]["action"] == "EXCLUDE" and rows["W:0"]["status"] == "FLOOR_LIKE")
check("structural семейства - EXCLUDE", rows["S:0"]["action"] == "EXCLUDE")
check("предмет или рельеф - class_check", rows["R:0"]["blockers"] == ["identity", "class_check"])
check("человек: не предмет - EXCLUDE", rows["N:0"]["action"] == "EXCLUDE" and rows["N:0"]["status"] == "NOT_OBJECT")
check("у BLOCKED, DERIVE и EXCLUDE партии нет",
      all("batch" not in rows[k] for k in ("A:1", "B:0", "C:0", "D:0", "E:0", "W:0", "H:1")))

# опознание ассета: строки только на канонический и одиночку-предмет, старшинство предложений, решения человека
batch = {"A:1": ("red armchair", "made_01.tsv"), "B:0": ("SKIP", "ident_02.tsv")}
items2 = [item(1, "A:0", hint="[фото] chair"), item(2, "A:1"), item(3, "B:0"), item(4, "G:0", hint="crate"),
          item(5, "W:0", "floor_like", hint="grass"), item(6, "K:0", hint="lamp")]
fams2 = [fam("A:0", [mem("A:0", "canonical"), mem("A:1", "recolor")])]
human = {"G:0": {"asset_id": "G:0", "decision": "EDIT", "identity": "wooden crate"},
         "K:0": {"asset_id": "K:0", "decision": "CONFIRM", "identity": ""}}
idn = og.build_identity(items2, fams2, {}, human, batch, {})
check("строка опознания только у ассетов-предметов", sorted(idn) == ["A:0", "B:0", "G:0", "K:0"])
check("прежняя партия старше подсказки карты, даже от члена",
      idn["A:0"]["proposed"] == "red armchair" and idn["A:0"]["status"] == "AGENT_PROPOSED")
check("SKIP прежней партии", idn["B:0"]["status"] == "SKIP")
check("EDIT человека - свой текст", idn["G:0"]["status"] == "HUMAN_EDITED" and idn["G:0"]["identity"] == "wooden crate")
check("CONFIRM подтверждает предложенный текст", idn["K:0"]["status"] == "HUMAN_CONFIRMED" and idn["K:0"]["identity"] == "lamp")
idn2 = og.build_identity([item(1, "Z:0")], [], {}, {"Z:0": {"asset_id": "Z:0", "decision": "CONFIRM"}}, {}, {})
check("CONFIRM без текста - не подтверждение", idn2["Z:0"]["status"] == "UNKNOWN")
cls_items = [item(1, "T:0"), item(2, "T:1"), item(3, "Q:0")]
cls_fams = [fam("T:0", [mem("T:0", "canonical"), mem("T:1", "recolor")])]
n = og.apply_class_decisions(cls_items, cls_fams, {"T:0": {"asset_id": "T:0", "asset_class": og.STRUCTURAL_MODULAR,
                                                           "note": "ферма"}})
cls_rows = {r["key"]: r for r in og.plan(cls_items, cls_fams,
                                        og.build_identity(cls_items, cls_fams, {}, {}, {}, {}))}
check("класс человека: семейство целиком вне конвейера предметов, одиночка не тронута",
      n == 1 and cls_rows["T:0"]["action"] == "EXCLUDE" and cls_rows["T:0"]["status"] == "STRUCTURAL_MODULAR"
      and cls_rows["T:1"]["action"] == "EXCLUDE" and cls_rows["Q:0"]["action"] != "EXCLUDE")
sv_items = [item(1, "W:47"), item(2, "M:50")]
og.apply_class_decisions(sv_items, [], {"W:47": {"asset_id": "W:47", "asset_class": og.STATE_VARIANT,
                                                 "note": "DAMAGED_VARIANT_OF M:50"}})
sv_rows = {r["key"]: r for r in og.plan(sv_items, [], og.build_identity(sv_items, [], {}, {}, {}, {}))}
check("состояние другого предмета: отдельным заказом не рисуется, основа не тронута",
      sv_rows["W:47"]["action"] == "EXCLUDE" and sv_rows["W:47"]["status"] == "STATE_VARIANT"
      and "DAMAGED_VARIANT_OF M:50" in sv_rows["W:47"]["why"] and sv_rows["M:50"]["action"] != "EXCLUDE")
reo =og.build_identity([item(1, "G:0", hint="crate")], [], {"G:0": idn["G:0"]},
                        {"G:0": {"asset_id": "G:0", "decision": "REOPEN", "identity": "wooden crate", "note": "колонна?"}},
                        {}, {})
check("REOPEN: снова на проверку, текст не готов, identity_rev другой, выходы STALE",
      reo["G:0"]["status"] == "IDENTITY_REVIEW" and reo["G:0"]["identity"] == "" and
      reo["G:0"]["identity_rev"] != idn["G:0"]["identity_rev"] and "было: wooden crate" in reo["G:0"]["note"]
      and "STALE" in reo["G:0"]["note"])

# ревизии: у выхода записаны входы; сменилось опознание - STALE именно по нему
fh = {("A", 0): "m0", ("A", 1): "m1"}
f = fams2[0]
before = ar.inputs(f, {"status": "HUMAN_CONFIRMED", "identity": "chair"}, ["A:0"], ["A:1"], fh, derive="d1")
after = ar.inputs(f, {"status": "HUMAN_EDITED", "identity": "beer tap"}, ["A:0"], ["A:1"], fh, derive="d1")
check("переименование - STALE по identity_rev", ar.stale(before, after) == ["identity_rev"])
check("то же самое - свежий", ar.stale(before, dict(before)) == [])
check("новая версия вывода - STALE по derive_rev",
      ar.stale(before, ar.inputs(f, {"status": "HUMAN_CONFIRMED", "identity": "chair"}, ["A:0"], ["A:1"], fh,
                                 derive="d2")) == ["derive_rev"])
check("перерисован оригинал члена - STALE по member_source_rev",
      ar.stale(before, ar.inputs(f, {"status": "HUMAN_CONFIRMED", "identity": "chair"}, ["A:0"], ["A:1"],
                                 {("A", 0): "m0", ("A", 1): "zz"}, derive="d1")) == ["member_source_rev"])
check("выход без записи входов - no_inputs", ar.stale({}, before) == ["no_inputs"])
check("input_hash меняется с опознанием", ar.input_hash(before) != ar.input_hash(after))

# P1-B: каждый вход по отдельности - STALE ровно по нему, без смены остальных
conf = {"status": "HUMAN_CONFIRMED", "identity": "refrigerator"}
base = dict(family=f, identity=conf, canonical_src=["A:0"], member_src=["A:1"], fh=fh,
            generator=ar.generator_rev("g", {"steps": 6}), prompt=ar.prompt_rev("photo of {what}"), derive="d1")
b0 = ar.inputs(**base)
cases = {
    "family_rev": dict(family=dict(f, content_hash="other")),
    "identity_rev": dict(identity={"status": "HUMAN_CONFIRMED", "identity": "vending machine"}),
    "canonical_source_rev": dict(fh={("A", 0): "new", ("A", 1): "m1"}),
    "generator_rev": dict(generator=ar.generator_rev("g", {"steps": 8})),
    "prompt_rev": dict(prompt=ar.prompt_rev("a real photograph of {what}")),
    "derive_rev": dict(derive="d2"),
}
for field, change in cases.items():
    got = ar.stale(b0, ar.inputs(**dict(base, **change)))
    if field == "canonical_source_rev":
        got = [g for g in got if g != "member_source_rev"]      # новый хэш кадра A:0 не трогает A:1
    check("сменился %s - STALE ровно по нему" % field, got == [field])
check("«refrigerator» -> «vending machine» при том же семействе - STALE",
      ar.stale(b0, ar.inputs(**dict(base, identity={"status": "HUMAN_CONFIRMED", "identity": "vending machine"})))
      == ["identity_rev"])
check("все входы в FIELDS", set(cases) | {"member_source_rev"} == set(ar.FIELDS))

# P1-B: ответ предлагателя - только предложение, UNKNOWN - не предложение
props = {"P:0": {"proposed_name": "vending machine", "short_description": "a red vending machine",
                 "proposed_category": "machine or electronics", "confidence": 0.99, "evidence": ["picture", "mcd"],
                 "ambiguity": "", "model": "m", "status": "PROPOSED"},
         "U:0": {"proposed_name": "UNKNOWN", "short_description": "", "proposed_category": "UNKNOWN",
                 "confidence": 0.1, "evidence": ["picture"], "ambiguity": "hill or sofa", "model": "m"}}
idn3 = og.build_identity([item(1, "P:0"), item(2, "U:0", os_.UNCERTAIN)], [], {}, {}, {}, props)
check("уверенность 0.99 - всё равно AGENT_PROPOSED, не подтверждение",
      idn3["P:0"]["status"] == "AGENT_PROPOSED" and idn3["P:0"]["identity"] == ""
      and idn3["P:0"]["proposed"] == "a red vending machine" and idn3["P:0"]["proposed_category"].startswith("machine"))
check("ответ UNKNOWN - NO_PROPOSAL, неоднозначность на карточке",
      idn3["U:0"]["status"] == "NO_PROPOSAL" and idn3["U:0"]["ambiguity"] == "hill or sofa")
rows3 = {r["key"]: r for r in og.plan([item(1, "P:0"), item(2, "U:0", os_.UNCERTAIN)], [], idn3)}
check("предложение модели заказ не открывает", rows3["P:0"]["status"] == "BLOCKED"
      and rows3["U:0"]["blockers"] == ["identity", "class_check"])

# два ответа модели - разные предметы: REVIEW_REQUIRED без текста, подсказка карты не подставляется
conf = {"C:0": {"proposed_name": "UNKNOWN", "proposed_category": "UNKNOWN", "short_description": "", "confidence": 0.0,
                "evidence": ["picture"], "ambiguity": "два ответа модели - разные предметы", "model": "m",
                "status": "REVIEW_REQUIRED", "review_level": "HUMAN_REVIEW_HARD",
                "candidates": [{"proposed_name": "pillar", "proposed_category": "wall"},
                               {"proposed_name": "barrel", "proposed_category": "container"}]},
        "S:0": dict(props["P:0"], status="PROPOSED_AMBIGUOUS", proposed_name="support column")}
hinted = dict(item(1, "C:0"), hint="a wooden barrel")
idn4 = og.build_identity([hinted, item(2, "S:0")], [], {}, {}, {}, conf)
check("спорный ответ - REVIEW_REQUIRED, без текста и без подсказки карты",
      idn4["C:0"]["status"] == "REVIEW_REQUIRED" and idn4["C:0"]["proposed"] == "" and idn4["C:0"]["identity"] == "")
check("догадки спорного - в candidates, с подсказкой карты",
      idn4["C:0"]["candidates"] == "pillar (wall) | barrel (container) | подсказка карты: a wooden barrel")
check("HARD: уровень и имена догадок по алфавиту - ни одна не первая по порядку ответов",
      idn4["C:0"]["review_level"] == "HUMAN_REVIEW_HARD" and idn4["C:0"]["candidate_names"] == "barrel | pillar")
check("PROPOSED_AMBIGUOUS - предложение с пометкой в model_status",
      idn4["S:0"]["status"] == "AGENT_PROPOSED" and idn4["S:0"]["model_status"] == "PROPOSED_AMBIGUOUS")
check("спорный ответ заказ не открывает", {r["key"]: r for r in og.plan([hinted], [], idn4)}["C:0"]["status"] == "BLOCKED")
idn5 = og.build_identity([hinted], [], {}, {}, {"C:0": ("old batch text", "ident_1")}, conf)
check("описание прежней партии старше спора модели - AGENT_PROPOSED",
      idn5["C:0"]["status"] == "AGENT_PROPOSED" and idn5["C:0"]["proposed"] == "old batch text")

# кусок большого предмета (R-153): подтверждённый - EXCLUDE всем семейством; подозрение - слово И край, на проверку
from PIL import Image                   # noqa: E402
fr_items = [item(1, "M:0"), item(2, "M:1"), item(3, "V:0"), item(4, "V:1"), item(5, "V:2"), item(6, "V:3")]
for it in fr_items:
    it["kind"] = "один"
fr_fams = [fam("M:0", [mem("M:0", "canonical"), mem("M:1", "mirror")])]
og.apply_class_decisions(fr_items, fr_fams, {"M:0": {"asset_id": "M:0", "asset_class": og.PART_FRAGMENT}})
edge_im, free_im = Image.new("RGBA", (32, 40)), Image.new("RGBA", (32, 40))
edge_im.putpixel((31, 20), (9, 9, 9, 255))
free_im.putpixel((16, 20), (9, 9, 9, 255))
pics = {"V:0": edge_im, "V:1": free_im, "V:2": edge_im, "V:3": edge_im}
fr_id = {"V:0": dict(ok_id, identity="green helicopter fuselage section"),
         "V:1": dict(ok_id, identity="helicopter fuselage section"),
         "V:2": dict(ok_id, identity="large wooden crate"),
         "V:3": {"status": "AGENT_PROPOSED", "proposed": "white panel van"}, "M:0": ok_id}
sus = og.fragment_suspects(fr_items, fr_id, {}, lambda s, f: pics.get("%s:%d" % (s, f)))
check("подозрение: слово и край - да; слово без края, край без слова - нет; предложение модели считается",
      set(sus) == {"V:0", "V:3"} and "helicopter" in sus["V:0"] and "край 1" in sus["V:0"])
check("класс человека снимает подозрение",
      og.fragment_suspects(fr_items, fr_id, {"V:0": {}}, lambda s, f: pics.get("%s:%d" % (s, f))).keys() == {"V:3"})
for it in fr_items:
    if it["keys"][0] in sus:
        it["fragment_suspect"] = sus[it["keys"][0]]
fr_rows = {r["key"]: r for r in og.plan(fr_items, fr_fams, fr_id)}
check("подтверждённый кусок - EXCLUDE PART_FRAGMENT_CONFIRMED, зеркало с ним",
      fr_rows["M:0"]["action"] == fr_rows["M:1"]["action"] == "EXCLUDE"
      and fr_rows["M:0"]["status"] == fr_rows["M:1"]["status"] == "PART_FRAGMENT_CONFIRMED")
check("подозрение держит заказ блокером, не исключает",
      fr_rows["V:0"]["action"] == "GENERATE" and fr_rows["V:0"]["status"] == "BLOCKED"
      and fr_rows["V:0"]["blockers"] == ["part_fragment_suspect"] and fr_rows["V:1"]["status"] == "READY")

# ворота опознания (01.10): MADDECOR_WASTE:47 подтверждён «кучей мусора», регрессия это отвергла, истина OPEN -
# READY по старому подтверждению не бывает; без ворот тот же ассет READY (контроль)
import json as _json                    # noqa: E402
import tempfile                         # noqa: E402
with tempfile.TemporaryDirectory() as td:
    gd = os.path.join(td, "identity-gate-x")
    os.makedirs(gd)
    with open(os.path.join(gd, "answers_vitali.tsv"), "w", encoding="utf-8-sig") as f:
        f.write("asset_id\tfinal_identity\tstatus\tmissing_context\tnote\n"
                "W:0\tWhite ice vending machine\tIDENTITY_VISUALLY_VERIFIED\t\t\n"
                "T:0\tglass shelf\tIDENTITY_VISUALLY_VERIFIED\t\t\n"
                "F:0\tend of a dissection table\tPART_FRAGMENT_CONFIRMED\t\t\n"
                "Y:0\tred chair\tIDENTITY_VISUALLY_VERIFIED\t\t\n")
    with open(os.path.join(gd, "reference.tsv"), "w", encoding="utf-8-sig") as f:
        f.write("asset_id\tref_status\tidentity_ok\told_rejected\n"
                "W:0\tIDENTITY_VISUALLY_VERIFIED\topen\tyes\nT:0\tIDENTITY_VISUALLY_VERIFIED\tyes\tyes\n"
                "Y:0\tIDENTITY_VISUALLY_VERIFIED\tyes\tyes\n")
    rp = os.path.join(td, "reg.json")
    with open(rp, "w", encoding="utf-8-sig") as f:
        _json.dump({"items": [{"asset_id": "W:0", "passed_card_as": "CONFIRM", "card_when": "2026-10-01 10:39",
                               "human_outcome": "FAIL"}]}, f)
    dp = os.path.join(td, "dec.tsv")
    with open(dp, "w", encoding="utf-8-sig") as f:
        f.write("asset_id\tdecision\tidentity\twho\twhen\tnote\nW:0\tCONFIRM\t\tVitali\t2026-10-01 10:39\t\n")
    gates = og.identity_gates(os.path.join(td, "identity-gate-*"), rp, dp)
g_items = [item(1, "W:0"), item(2, "T:0"), item(3, "F:0"), item(4, "Y:0"), item(5, "Z:0")]
g_id = {"W:0": dict(ok_id, identity="pile of crumpled trash"), "T:0": dict(ok_id, identity="a pile of trash"),
        "F:0": dict(ok_id, identity="cow on a table"), "Y:0": dict(ok_id, identity="Red  Chair"), "Z:0": ok_id}
g_rows = {r["key"]: r for r in og.plan(g_items, [], g_id, gates)}
check("отвергнутое регрессией подтверждение при открытой истине - не READY, оба блокера",
      g_rows["W:0"]["status"] == "BLOCKED" and og.CONFLICT in g_rows["W:0"]["blockers"]
      and og.TRUTH_OPEN in g_rows["W:0"]["blockers"])
check("подтверждён не тот текст, что ответ ворот - конфликт", g_rows["T:0"]["blockers"] == [og.CONFLICT])
check("ворота назвали кусок, а ассет в заказе - конфликт", g_rows["F:0"]["blockers"] == [og.CONFLICT])
check("тот же текст (регистр, пробелы) при закрытой истине и ассет вне ворот - READY",
      g_rows["Y:0"]["status"] == "READY" and g_rows["Z:0"]["status"] == "READY")
check("контроль: без ворот отвергнутое подтверждение READY",
      {r["key"]: r for r in og.plan(g_items, [], g_id)}["W:0"]["status"] == "READY")

many = [item(i, "S%d:0" % i) for i in range(1, 71)]
rows = og.plan(many, [], {"S%d:0" % i: ok_id for i in range(1, 71)})
b = [r.get("batch") for r in rows]
check("партии 10, 50, потом 100", b.count(1) == 10 and b.count(2) == 50 and b.count(3) == 10)
print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
