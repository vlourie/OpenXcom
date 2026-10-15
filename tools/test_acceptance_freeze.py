#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""acceptance_plan --freeze / --check: неизменяемый снимок десятки и BATCH_STALE (P1-B, замечания 29.09).

Синтетика, без файлов проекта и без модели:
  * тот же состав и те же входы - тот же acceptance_batch_id; другое опознание - другой id;
  * снимок пишется только для чтения, повторная заморозка его не переписывает;
  * сразу после заморозки --check - BATCH_CURRENT;
  * изменились семейство, опознание, оригинал, derive_rev, генератор, промпт - BATCH_STALE с причиной;
  * семейство переразбито (его больше нет) - ORPHANED, а не STALE;
  * задания в снимке (30.09): другой бок - второе задание с ответом первого второй картинкой, составной -
    куски и места, плитка - свой модификатор и TILE_QA, рядом со своей копией - ADJACENCY_QA без модификатора,
    выведенный по кускам составной - места кусков и COMPOSITE_SEAM_QA; зерно или промпт - другой id; задания
    правили в файле мимо --freeze - STALE jobs_hash; генератор не утверждён для приёмки - STALE.

    py -3.13 tools/test_acceptance_freeze.py
"""
import copy
import json
import os
import shutil
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))

import acceptance_plan as ap            # noqa: E402
import asset_rev as ar                  # noqa: E402
import obj_gen_spec as ogs              # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


GEN = {"name": "g", "model": "m", "script": "tools/hdart/obj_photo.py", "args": ["--engine", "turbo", "--rgba"],
       "template": {"head": "H. ", "tail": " T.", "parts": ogs.PROMPT_V2, "order": list(ogs.MODIFIER_ORDER)},
       "generator_rev": "gen1", "prompt_rev": "pr1", "status": "APPROVED_FOR_ACCEPTANCE", "approved_rev": "gen1"}
DVER = "d1"
FH = {("SET", 0): "h0", ("SET", 1): "h1", ("SET", 2): "h2", ("SET", 3): "h3"}
FAM = {"SET:0": {"family_id": "SET:0", "revision": 1, "content_hash": "c1", "review": [],
                 "members": [{"keys": ["SET:0"], "src": ["SET:0"], "relation": "canonical", "decision": "AUTO"},
                             {"keys": ["SET:1"], "src": ["SET:1"], "relation": "recolor", "decision": "AUTO"}]}}
ITEMS = {1: {"rank": 1, "src": ["SET:0"], "keys": ["SET:0"], "frames": [], "map": "T/B", "at": [[16, 8, 0]]},
         2: {"rank": 2, "src": ["SET:1"], "keys": ["SET:1"], "frames": [], "map": "T/B", "at": [[32, 16, 0]]},
         3: {"rank": 3, "src": ["SET:2", "SET:3"], "keys": ["SET:2", "SET:3"], "frames": [], "map": "T/B2",
             "at": [[0, 0, 0], [16, 8, 0]]}}
IDROWS = {"SET:0": {"asset_id": "SET:0", "status": "HUMAN_CONFIRMED", "identity": "wooden crate"}}
SPEC = (("SET:0", 1, "GENERATE", "canonical"), ("SET:1", 2, "DERIVE", "recolor"))


def rows_now(fam, idrows, gen=GEN, dver=DVER, fh=FH, spec=SPEC):
    out = []
    for key, rank, action, rel in spec:
        r = {"key": key, "rank": rank, "asset_id": "SET:0", "family": "SET:0", "action": action, "relation": rel,
             "kind": "object", "places": 3, "identity": idrows["SET:0"]["identity"],
             "identity_status": idrows["SET:0"]["status"], "blockers": []}
        r["inputs"] = ap.current_inputs(r, fam, ITEMS, idrows, gen, dver, fh)
        r["input_hash"] = ar.input_hash(r["inputs"])
        out.append(r)
    return out


def plans_of(fam, idrows, category="ящик", spec=SPEC, items=ITEMS):
    rows = rows_now(fam, idrows, spec=spec)
    plans = [ap.plan_one({"asset_id": "SET:0", "category": category}, rows, fam, items, GEN, idrows, FH)]
    ap.number_jobs(plans, 100)
    return plans, rows


def freeze(fam, idrows):
    plans, rows = plans_of(fam, idrows)
    check("план без блокеров", plans[0]["blockers"] == [])
    return ap.snapshot(plans, rows, GEN, DVER)


snap = freeze(FAM, IDROWS)
check("id вида acc-<12>", snap["acceptance_batch_id"].startswith("acc-") and len(snap["acceptance_batch_id"]) == 16)
check("тот же состав - тот же id", freeze(FAM, IDROWS)["acceptance_batch_id"] == snap["acceptance_batch_id"])
id2 = copy.deepcopy(IDROWS)
id2["SET:0"]["identity"] = "wooden box"
check("другое опознание - другой id", freeze(FAM, id2)["acceptance_batch_id"] != snap["acceptance_batch_id"])
a = snap["assets"][0]
j = snap["jobs"][0]
check("в снимке ревизия семейства, identity_rev, кадры, строки",
      a["family"]["content_hash"] == "c1" and a["identity"]["identity_rev"]
      and "TERRAIN/SET.PCK/1.png" in a["frames"] and [r["action"] for r in a["rows"]] == ["GENERATE", "DERIVE"])
check("задание: номер, зерно, место, куски, ожидаемый файл, source_rev, input_hash",
      j["job_id"] == "j01" and j["seed"] == 101 and j["map"] == "T/B" and j["take"] == ["SET:0@0"]
      and j["expected_outputs"] == ["SET.PCK/0.png"] and j["canonical_inputs"] == [{"key": "SET:0", "source_rev": "h0"}]
      and j["input_hash"] == a["rows"][0]["input_hash"] and snap["jobs_hash"] == ar.h12(snap["jobs"]))
check("промпт: опознание, модификатор перекраски, цвет - соотношения, а не точные цвета",
      j["prompt"].startswith("H. ") and "wooden crate" in j["prompt"] and "Other color variants" in j["prompt"]
      and "dominant colors and color relationships" in j["prompt"] and "the colours" not in j["prompt"]
      and j["modifiers"] == ["recolor"])
check("задание вывода: из ответа основы, выход и input_hash строки",
      j["derive"] == [{"key": "SET:1", "relation": "recolor", "from": "SET:0", "base_src": ["SET:0"],
                       "member_src": ["SET:1"], "derive_rev": DVER, "input_hash": a["rows"][1]["input_hash"],
                       "outputs": ["SET.PCK/1.png"], "game_frames": ["TERRAIN/SET.PCK/1.png"]}])
check("стратегии: recolor_canonical, проверка перекраски",
      a["generation_strategy"] == "recolor_canonical" and "recolor_derived" in a["qa_strategy"])
p2, r2 = plans_of(FAM, IDROWS)
p2[0]["jobs"][0]["seed"] = 7
check("другое зерно в задании - другой id", ap.snapshot(p2, r2, GEN, DVER)["acceptance_batch_id"] != snap["acceptance_batch_id"])

# другой бок: второе задание той же группы, ответ первого - второй картинкой
FAM_ALT = copy.deepcopy(FAM)
FAM_ALT["SET:0"]["members"][1]["relation"] = "alternate_view"
pa, _r = plans_of(FAM_ALT, IDROWS, spec=(("SET:0", 1, "GENERATE", "canonical"), ("SET:1", 2, "GENERATE_WITH", "alternate_view")))
ja, jb = pa[0]["jobs"]
check("другой бок - два задания одной группы, B опирается на ответ A",
      len(pa[0]["jobs"]) == 2 and ja["multiview_group"] == jb["multiview_group"] == "mv-SET_0"
      and (ja["view"], jb["view"]) == ("A", "B") and jb["reference"]["raw"] == "raw/%s.png" % ja["name"]
      and jb["reference"]["job_name"] == ja["name"] and jb["same_asset"] and jb["same_construction"]
      and ja["seed"] != jb["seed"] and pa[0]["generation_strategy"] == "linked_alt_views_2_jobs"
      and "identity_between_views" in pa[0]["qa_strategy"])
check("промпт B: <image2>, тот же физический предмет, другой бок; промпт A - без <image2>",
      "<image2> is the finished photograph" in jb["prompt"] and "alternate isometric side" in jb["prompt"]
      and "<image2>" not in ja["prompt"] and "other isometric side in a separate" in ja["prompt"]
      and jb["expected_outputs"] == ["SET.PCK/1.png"])

# составной: куски и места; мест меньше, чем кусков, - блокер R-132
items_c = dict(ITEMS)
items_c[1] = dict(ITEMS[3], rank=1)
pc, _r = plans_of({}, IDROWS, spec=(("SET:0", 1, "GENERATE", ""),), items=items_c)
jc = pc[0]["jobs"][0]
check("составной: оба куска, оба места, промпт про одну вещь из 2 частей",
      jc["take"] == ["SET:2@0", "SET:3@1"] and len(jc["at"]) == 2 and "its 2 parts" in jc["prompt"]
      and "one continuous physical object" in jc["prompt"] and pc[0]["generation_strategy"] == "composite_2_parts"
      and "assembled_geometry" in pc[0]["qa_strategy"] and pc[0]["blockers"] == [])
items_c[1] = dict(ITEMS[3], rank=1, at=[[0, 0, 0]])
pc, _r = plans_of({}, IDROWS, spec=(("SET:0", 1, "GENERATE", ""),), items=items_c)
check("составной без мест кусков - блокер R-132", any("R-132" in b for b in pc[0]["blockers"]))

# составной, выведенный зеркалом по кускам: место его кусков на карте и COMPOSITE_SEAM_QA
FAM_M = {"SET:0": {"family_id": "SET:0", "revision": 1, "content_hash": "c1", "review": [],
                   "members": [{"keys": ["SET:0"], "src": ["SET:2", "SET:3"], "relation": "canonical", "decision": "AUTO"},
                               {"keys": ["SET:1"], "src": ["SET:4", "SET:5"], "relation": "mirror", "decision": "AUTO"}]}}
items_m = {1: dict(ITEMS[3], rank=1),
           2: {"rank": 2, "src": ["SET:4", "SET:5"], "keys": ["SET:4", "SET:5"], "frames": [], "map": "T/B3",
               "at": [[16, 0, 0], [32, 8, 0]]}}
spec_m = (("SET:0", 1, "GENERATE", "canonical"), ("SET:1", 2, "DERIVE", "mirror"))
pm, _r = plans_of(FAM_M, IDROWS, spec=spec_m, items=items_m)
dvm = pm[0]["jobs"][0]["derive"][0] if pm[0]["jobs"][0]["derive"] else {}
check("выведенный составной: места его кусков в задании вывода, composite_seam_qa, без блокеров",
      dvm.get("map") == "T/B3" and dvm.get("at") == [[16, 0, 0], [32, 8, 0]]
      and dvm.get("outputs") == ["SET.PCK/4.png", "SET.PCK/5.png"]
      and "composite_seam_qa" in pm[0]["qa_strategy"] and pm[0]["blockers"] == [])
items_m[2] = dict(items_m[2], at=[[16, 0, 0]])
pm, _r = plans_of(FAM_M, IDROWS, spec=spec_m, items=items_m)
check("выведенный составной без мест кусков - блокер (шов не проверить)",
      any("шов не проверить" in b for b in pm[0]["blockers"]))

# плитка: модификатор и TILE_QA только у tileable; рядом со своей копией - ADJACENCY_QA, без модификатора
pt, _r = plans_of({}, IDROWS, category="tileable", spec=(("SET:0", 1, "GENERATE", ""),))
ps, _r = plans_of({}, IDROWS, category="single", spec=(("SET:0", 1, "GENERATE", ""),))
check("tileable: модификатор и TILE_QA (3x3, карта); single - без них",
      "repeating modular game asset" in pt[0]["jobs"][0]["prompt"] and pt[0]["generation_strategy"] == "tileable_single"
      and {"tile_qa_3x3", "tile_qa_map"} <= set(pt[0]["qa_strategy"]) and "adjacency_qa" not in pt[0]["qa_strategy"]
      and "repeating modular" not in ps[0]["jobs"][0]["prompt"] and ps[0]["generation_strategy"] == "single"
      and not {"tile_qa_3x3", "tile_qa_map", "adjacency_qa"} & set(ps[0]["qa_strategy"]))
qa02 = ap.qa_strategy("mirror", ["X:1"], [], {"mirror"}, 0.2)
check("tile_share 0.2, не плитка - ADJACENCY_QA, а не TILE_QA",
      "adjacency_qa" in qa02 and not {"tile_qa_3x3", "tile_qa_map"} & set(qa02)
      and "adjacency_qa" not in ap.qa_strategy("mirror", ["X:1"], [], {"mirror"}, 0.05))
check("общая фраза про части - про то, что есть в оригинале, без шкафа (ступени, полки, ящики, двери)",
      "meaningful structural parts, openings, and attached elements visible in the source" in ps[0]["jobs"][0]["prompt"]
      and "shelves" not in ps[0]["jobs"][0]["prompt"] and "drawers" not in ps[0]["jobs"][0]["prompt"])
check("порядок модификаторов в тексте не зависит от порядка вызова",
      ogs.build_prompt(GEN["template"], "x", ["mirror", "recolor"]) == ogs.build_prompt(GEN["template"], "x", ["recolor", "mirror"]))

tmp = tempfile.mkdtemp(prefix="accfrz_")
try:
    path = ap.write_frozen(snap, tmp)
    check("снимок только для чтения", not os.stat(path).st_mode & stat.S_IWRITE)
    with open(path, encoding=ap.ENC) as f:
        first = f.read()
    ap.write_frozen(snap, tmp)
    with open(path, encoding=ap.ENC) as f:
        check("повторная заморозка не переписывает", f.read() == first)
    on_disk = json.loads(first.lstrip("﻿"))
finally:
    for p in os.listdir(tmp):
        os.chmod(os.path.join(tmp, p), stat.S_IWRITE)
    shutil.rmtree(tmp, ignore_errors=True)


def verdict(fam=FAM, idrows=IDROWS, gen=GEN, dver=DVER, fh=FH):
    return ap.check_snapshot(on_disk, fam, ITEMS, idrows, gen, dver, fh)


check("сразу после заморозки - BATCH_CURRENT", verdict() == [])
fam2 = copy.deepcopy(FAM)
fam2["SET:0"]["content_hash"] = "c2"
got = verdict(fam=fam2)
check("семейство изменилось - STALE family_rev у обеих строк",
      [(k, s) for k, s, _w in got] == [("SET:0", "STALE"), ("SET:1", "STALE")] and "family_rev" in got[0][2])
got = verdict(idrows=id2)
check("опознание изменилось - STALE identity_rev", got and all("identity_rev" in w for _k, _s, w in got))
got = verdict(fh={("SET", 0): "h0", ("SET", 1): "h1x"})
check("оригинал члена изменился - STALE member_source_rev только у DERIVE",
      [(k, w) for k, _s, w in got] == [("SET:1", ["member_source_rev"])])
got = verdict(dver="d2")
check("derive_rev изменился - STALE только у DERIVE", [(k, w) for k, _s, w in got] == [("SET:1", ["derive_rev"])])
got = verdict(gen=dict(GEN, generator_rev="gen2"))
check("генератор сменился - STALE", any(k == "*" and w == ["generator_rev"] for k, _s, w in got))
got = verdict(gen=dict(GEN, prompt_rev="pr2"))
check("промпт сменился - STALE", any(k == "*" and w == ["prompt_rev"] for k, _s, w in got))
got = verdict(fam={})
check("семейства больше нет - ORPHANED, не STALE", got and all(s == "ORPHANED" for _k, s, _w in got))
got = verdict(gen=dict(GEN, status="REVOKED"))
check("генератор не утверждён для приёмки - STALE", any(w == ["generator_not_approved"] for _k, _s, w in got))
got = verdict(gen=dict(GEN, generator_rev="gen2"))
check("утверждение привязано к generator_rev", any(w == ["generator_not_approved"] for _k, _s, w in got))
tampered = copy.deepcopy(on_disk)
tampered["jobs"][0]["prompt"] += " extra"
got = ap.check_snapshot(tampered, FAM, ITEMS, IDROWS, GEN, DVER, FH)
check("задания правили в файле мимо --freeze - STALE jobs_hash", any(w == ["jobs_hash"] for _k, _s, w in got))
check("утверждено для приёмки - не для производства",
      ogs.approved_for(GEN, "acceptance") and not ogs.approved_for(GEN, "production"))

print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
