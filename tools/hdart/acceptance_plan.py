#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Сухой план приёмочной десятки: что будет заказано модели, что выведено, какие кадры игры получатся (P1-B).

Модель НЕ зовёт и ничего не пишет в пак - только план. Для каждого ассета десятки (acceptance.json):
  asset_id, опознание (статус и текст), канонический кадр (куски составного);
  ревизия и content_hash семейства, identity_rev, связь каждого члена и чьё решение (AUTO / человек);
  что РИСУЕТ модель: задания (jobs) - канонический кадр; другой бок (GENERATE_WITH) - ОТДЕЛЬНОЕ задание
  той же multiview_group с ответом первого второй картинкой; готовый промпт v2 с модификаторами типа;
  что ВЫВОДИТСЯ без модели: перекраска и зеркало (obj_derive, derive_rev);
  какие кадры игры получат файл: TERRAIN/<набор>.PCK/<кадр>.png, включая копии той же картинки в других
  наборах (items.json frames);
  генератор, его ревизии и статус (obj_gen_spec: APPROVED_FOR_ACCEPTANCE на generator_rev, не production);
  стратегии генерации и проверки на строку (generation_strategy, qa_strategy);
  блокеры: что ещё не даёт заказать (опознание не подтверждено, открытые вопросы семейства).
Пишет art/objects/generation/acceptance_plan.md и .json. Решения со страницы ревью попадают в план
только после «Пересобрать» (obj_families + obj_generation) - план предупредит, если журналы новее.

Условия первой GPU-десятки (P1-B): опознание всех 10 подтверждено, спорные связи решены, план проверен,
ревизии работают, сборщик пака чист, hd_manifest verify - INTEGRITY PASS, и ни одна зависимость ЭТИХ десяти
не устарела (входы asset_rev каждой строки плана против пересчитанных сейчас; устаревшее в остальном паке -
предупреждение hd_manifest freshness, десятку не держит). Этот план проверяет опознание, связи и зависимости
(CURRENT, STALE - входы изменились, ORPHANED - семейства больше нет).

Между подтверждением и видеокартой - заморозка (замечания 29.09, R-087 «проверяли одно, запустили другое»):
--freeze - только готовая десятка (без блокеров, генератор утверждён для приёмки): неизменяемый снимок
batches/<acceptance_batch_id>.json - ассеты, ревизии семейств, опознание, канонические оригиналы, входы и
input_hash каждой строки, генератор, derive_rev и сами ЗАДАНИЯ модели (номер, зерно, готовый промпт, место
на карте, опорная картинка второго бока, ожидаемые файлы, задания вывода) с jobs_hash. Запускает только
acceptance_run.py run <id>: --check (BATCH_STALE - код 2, не едет), задания - из снимка, не из живых данных.

Задания (30.09): другой бок - ОТДЕЛЬНОЕ задание той же multiview-группы, ответ первого ему второй
картинкой; промпт - общий шаблон плюс модификаторы типа (obj_gen_spec.build_prompt); у ассета
generation_strategy и QA_strategy.

    py -3.13 tools/hdart/acceptance_plan.py
    py -3.13 tools/hdart/acceptance_plan.py --freeze
    py -3.13 tools/hdart/acceptance_plan.py --check acc-xxxxxxxxxxxx
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import obj_gen_spec as ogs                  # noqa: E402

ENC = "utf-8-sig"
GEN = os.path.join("art", "objects", "generation")
DISC = os.path.join("art", "objects", "discovery")
FAMS = os.path.join("art", "objects", "families", "families.json")
LOGS = (os.path.join(DISC, "identity_decisions.tsv"), os.path.join("art", "objects", "families", "decisions.tsv"))
BATCHES = os.path.join(GEN, "batches")
CONFIRMED = ("HUMAN_CONFIRMED", "HUMAN_EDITED")
REL_RU = {"canonical": "канонический", "recolor": "перекраска", "mirror": "зеркало",
          "alternate_view": "другой бок", "unknown": "связь?"}


def load(path):
    with open(path, encoding=ENC) as f:
        return json.load(f)


def frames_of(items_by_rank, rank):
    it = items_by_rank.get(rank)
    if not it:
        return []
    return list(dict.fromkeys(it.get("keys", []) + it.get("frames", [])))


def game_path(key):
    s, f = key.rsplit(":", 1)
    return "TERRAIN/%s.PCK/%s.png" % (s.upper(), f)


TILE_ADJ = 0.10        # кадр стоит вплотную к своей копии хотя бы в 10% мест - ADJACENCY_QA (не плитка)


def tile_share(member):
    """'160 из 971' (obj_families: в скольких местах кадр касается своей копии) -> 0.165."""
    t = (member or {}).get("tile", "")
    try:
        a, b = t.split(" из ")
        return int(a) / max(1, int(b))
    except ValueError:
        return 0.0


def out_path(key):
    """Файл, который obj_photo кладёт в --out: <НАБОР>.PCK/<кадр>.png."""
    s, f = key.rsplit(":", 1)
    return "%s.PCK/%s.png" % (s.upper(), f)


def strategy(category, pieces, with_, rels):
    """generation_strategy и QA_strategy ассета (замечания 30.09): как рисуется и чем принимается."""
    if with_:
        gs = "linked_alt_views_%d_jobs" % (1 + len(with_))
    elif len(pieces) > 1:
        gs = "composite_%d_parts" % len(pieces)
    elif category == "tileable":
        gs = "tileable_single"
    elif "mirror" in rels:
        gs = "mirror_canonical"
    elif "recolor" in rels:
        gs = "recolor_canonical"
    else:
        gs = "single"
    return gs


def qa_strategy(category, pieces, with_, rels, share):
    qa = ["geometry", "alpha", "ingame_lighting"]
    if with_:
        qa.append("identity_between_views")
    if len(pieces) > 1:
        qa.append("assembled_geometry")
    if category == "tileable":
        qa += ["tile_qa_3x3", "tile_qa_map"]    # TILE_QA: копии обязаны стыковаться бесшовно
    elif share >= TILE_ADJ:
        # ADJACENCY_QA: стоит рядом со своей копией, но не плитка - края не продолжаются; проверка, что
        # копии не залезают друг на друга, не сливаются, без общей тени и выступов (замечания 30.09)
        qa.append("adjacency_qa")
    if "recolor" in rels:
        qa.append("recolor_derived")
    if "mirror" in rels:
        qa.append("mirror_derived")
    if len(pieces) > 1 and rels & {"mirror", "recolor"}:
        qa.append("composite_seam_qa")          # выведенный по кускам составной - шов после сборки
    return qa


def make_jobs(acc, canon, with_, derive, fm, items_by_rank, gen, ident, fh):
    """Задания модели ассета (без номеров - их раздаёт number_jobs) и блокеры, найденные по дороге.
    Первый бок - канонический; каждый другой бок - отдельное задание той же multiview-группы, которое
    получает готовый ответ первого второй картинкой (замечания 30.09: два связанных заказа)."""
    import asset_rev as ar
    blockers = []
    derive_rels = {d["relation"] for d in derive}
    group = ("mv-" + canon["key"].replace(":", "_")) if with_ else None

    def job(row, mods, relation, view):
        it = items_by_rank.get(row["rank"], {})
        pieces = it.get("src", [row["key"]])
        at = it.get("at", [])
        if len(at) < len(pieces):
            blockers.append("%s: мест кусков на карте %d из %d (R-132)" % (row["key"], len(at), len(pieces)))
        if len(pieces) > 1:
            mods = ["composite"] + mods
        return {"asset_id": acc["asset_id"], "row_key": row["key"], "relation": relation, "view": view,
                "multiview_group": group, "identity": ident, "modifiers": mods, "parts": len(pieces),
                "prompt": ogs.build_prompt(gen["template"], ident, mods, len(pieces)) if ident else None,
                "map": it.get("map", ""), "at": at[:len(pieces)],
                "take": ["%s@%d" % (k, i) for i, k in enumerate(pieces)],
                "canonical_inputs": [{"key": k, "source_rev": fh.get(tuple([k.rsplit(":", 1)[0].upper(),
                                                                             int(k.rsplit(":", 1)[1])]), "missing")}
                                     for k in pieces],
                "input_hash": row["input_hash"],
                "expected_outputs": [out_path(k) for k in pieces],
                "game_frames": [game_path(k) for k in frames_of(items_by_rank, row["rank"])]}

    mods_a = (["alt_view_a"] if with_ else []) + [m for m in ("recolor", "mirror") if m in derive_rels] + \
             (["tileable"] if acc["category"] == "tileable" else [])
    a = job(canon, mods_a, "canonical", "A" if with_ else None)
    # вывод без модели - из ответа задания A: перекраска и зеркало (obj_derive.derive), по кускам основы
    can_src = fm["members"][0]["src"] if fm else [t.split("@")[0] for t in a["take"]]
    by_key = {m["keys"][0]: m for m in (fm["members"][1:] if fm else [])}
    a["derive"] = []
    for d in derive:
        m = by_key.get(d["key"])
        if not m or len(m["src"]) != len(can_src):
            blockers.append("%s: вывод не собрать - кусков %s против %d у основы" % (
                d["key"], len(m["src"]) if m else "?", len(can_src)))
            continue
        outs = m["keys"] if len(m["src"]) == 1 else m["src"]      # одиночный: один файл на все копии (R-049)
        dv = {"key": d["key"], "relation": d["relation"], "from": canon["key"],
              "base_src": can_src, "member_src": m["src"], "derive_rev": d["derive_rev"],
              "input_hash": d["input_hash"], "outputs": [out_path(k) for k in outs],
              "game_frames": [f["game"] for f in d["frames"]]}
        if len(m["src"]) > 1:
            # составной выводится по кускам - место на карте, где его куски стоят вместе (COMPOSITE_SEAM_QA)
            it = next((i for i in items_by_rank.values() if list(i.get("src", [])) == list(m["src"])), None)
            if not it or len(it.get("at", [])) < len(m["src"]):
                blockers.append("%s: выведенный составной без мест кусков на карте - шов не проверить" % d["key"])
            else:
                dv.update(map=it["map"], at=it["at"][:len(m["src"])])
        a["derive"].append(dv)
    jobs = [a]
    for r in with_:
        b = job(r, ["alt_view_b"], "alternate_view", chr(ord("B") + len(jobs) - 1))
        b.update(same_asset=True, same_material=True, same_dimensions=True, same_construction=True,
                 reference={"view": "A"})              # имя задания A и путь его ответа - в number_jobs
        b["derive"] = []
        jobs.append(b)
    return jobs, blockers


def number_jobs(plans, seed0):
    """Сквозные номера заданий партии, имена (по ним obj_photo называет raw/<имя>.png) и зёрна."""
    n = 0
    for p in plans:
        first = None
        for j in p["jobs"]:
            n += 1
            j["job_id"] = "j%02d" % n
            j["name"] = "j%02d_%s" % (n, j["row_key"].replace(":", "_"))
            j["seed"] = seed0 + n
            if first is None:
                first = j
            elif j.get("reference"):
                j["reference"] = {"view": "A", "job_id": first["job_id"], "job_name": first["name"],
                                  "raw": "raw/%s.png" % first["name"]}


def plan_one(acc, rows, fam, items_by_rank, gen, idrows=None, fh=None):
    aid = acc["asset_id"]
    proposed = (idrows or {}).get(aid, {}).get("proposed", "")
    mine = [r for r in rows if r["asset_id"] == aid]
    canon = next(r for r in mine if r["key"] == aid)      # у одиночки без семейства relation пустая
    with_ = [r for r in mine if r["action"] == "GENERATE_WITH"]
    derive = [r for r in mine if r["action"] == "DERIVE"]
    excluded = [r for r in mine if r["action"] == "EXCLUDE"]
    fm = fam.get(canon["family"])
    ident = canon.get("identity", "")
    st = canon.get("identity_status", "")
    blockers = []
    if st not in CONFIRMED:
        blockers.append("опознание %s - не подтверждено человеком" % st)
    if fm and fm.get("review"):
        blockers.append("семейство: открытых кандидатов %d (%s)" % (
            len(fm["review"]), ", ".join(m["keys"][0] for m in fm["review"])))
    unk = [m["keys"][0] for m in (fm["members"][1:] if fm else []) if m.get("relation") == "unknown"]
    if unk:
        blockers.append("связь не названа: %s" % ", ".join(unk))
    other = [b for b in canon.get("blockers", []) if b != "identity" and not b.startswith("family_review")]
    blockers += ["очередь: %s" % b for b in other]

    def frames(r):
        return [{"key": k, "game": game_path(k)} for k in frames_of(items_by_rank, r["rank"])]

    members = [{"key": m["keys"][0], "relation": m.get("relation", ""), "decision": m.get("decision", "")}
               for m in (fm["members"][1:] if fm else [])]
    derive_plan = [{"key": r["key"], "relation": r["relation"], "from": r.get("derive_from", aid),
                    "derive_rev": r["inputs"]["derive_rev"], "input_hash": r["input_hash"], "frames": frames(r)}
                   for r in derive]
    pieces = items_by_rank.get(canon["rank"], {}).get("src", [canon["key"]])
    rels = {d["relation"] for d in derive_plan}
    share = tile_share(fm["members"][0]) if fm else 0.0
    jobs, jb = make_jobs(acc, canon, with_, derive_plan, fm, items_by_rank, gen, ident, fh or {})
    blockers += jb
    return {
        "generation_strategy": strategy(acc["category"], pieces, with_, rels),
        "qa_strategy": qa_strategy(acc["category"], pieces, with_, rels, share),
        "tile_share": round(share, 3),
        "jobs": jobs,
        "category": acc["category"], "asset_id": aid, "rank": canon["rank"], "kind": canon["kind"],
        "places": canon["places"],
        "identity": {"status": st, "text": ident, "proposed": proposed, "identity_rev": canon["inputs"]["identity_rev"]},
        # куски - src (клетки составного); keys и frames ещё и копии той же картинки в других наборах
        "canonical": {"key": canon["key"], "pieces": items_by_rank.get(canon["rank"], {}).get("src", [canon["key"]])},
        "family": {"id": canon["family"], "revision": fm["revision"] if fm else None,
                   "content_hash": fm["content_hash"] if fm else "", "members": members,
                   "open_review": [m["keys"][0] for m in (fm or {}).get("review", [])],
                   "rejected": [m["keys"][0] if isinstance(m, dict) else m for m in (fm or {}).get("rejected", [])]},
        "generate": {"canonical": canon["key"], "linked_views": [r["key"] for r in with_],
                     "frames": frames(canon) + [f for r in with_ for f in frames(r)]},
        "derive": derive_plan,
        "excluded": [{"key": r["key"], "relation": r["relation"]} for r in excluded],
        "inputs": canon["inputs"], "input_hash": canon["input_hash"],
        "blockers": blockers,
    }


WORK = ("GENERATE", "GENERATE_WITH", "DERIVE")


def current_inputs(r, fam, items_by_rank, idrows, gen, dver, fh):
    """Входы строки плана, пересчитанные из текущих файлов так же, как их считает obj_generation."""
    import asset_rev as ar
    fm = fam.get(r["family"])
    can_src = fm["members"][0]["src"] if fm else items_by_rank[r["rank"]]["src"]
    kw = {"generator": gen["generator_rev"], "prompt": gen["prompt_rev"]}
    if r["action"] == "DERIVE":
        kw.update(member_src=items_by_rank[r["rank"]]["src"], derive=dver)
    return ar.inputs(fm, idrows.get(r["asset_id"]), can_src, fh=fh, **kw)


def dep_state(r, recorded, fam, items_by_rank, idrows, gen, dver, fh):
    """None - свежее; ("ORPHANED", why) - семейства, по которому записан вход, больше нет (основание пропало,
    а не изменилось); ("STALE", [входы]) - входы изменились."""
    import asset_rev as ar
    if r.get("family") and recorded and recorded.get("family_rev") and r["family"] not in fam:
        return ("ORPHANED", ["семейства %s больше нет" % r["family"]])
    diff = ar.stale(recorded, current_inputs(r, fam, items_by_rank, idrows, gen, dver, fh))
    return ("STALE", diff) if diff else None


def deps_stale(aid, rows, fam, items_by_rank, idrows, gen, dver, fh):
    """Зависимости ассета десятки: входы каждой его строки плана против пересчитанных сейчас.
    {ключ: (STALE | ORPHANED, что именно)}; пусто - всё CURRENT."""
    out = {}
    for r in rows:
        if r["asset_id"] == aid and r["action"] in WORK:
            st = dep_state(r, r.get("inputs"), fam, items_by_rank, idrows, gen, dver, fh)
            if st:
                out[r["key"]] = st
    return out


def counts(plans):
    """Числа партии: логических ассетов, заданий модели, файлов из ответов, кадров игры прямо и выводом."""
    jobs = [j for p in plans for j in p["jobs"]]
    return {"assets": len(plans), "ai_jobs": len(jobs),
            "model_outputs": sum(len(j["expected_outputs"]) for j in jobs),
            "direct_game_frames": sum(len(p["generate"]["frames"]) for p in plans),
            "derive_jobs": sum(len(j["derive"]) for j in jobs),
            "derived_files": sum(len(d["outputs"]) for j in jobs for d in j["derive"]),
            "derived_game_frames": sum(len(d["frames"]) for p in plans for d in p["derive"])}


def md(plans, gen, dver, stale_logs):
    ok = ogs.approved_for(gen, "acceptance")
    L = ["# Сухой план приёмочной десятки", "",
         "Только план: модель не вызывается, пак не трогается. Собран %s." % __import__("time").strftime("%Y-%m-%d %H:%M"),
         "",
         "**Генератор:** `%s` - %s, `%s %s`. generator_rev `%s`, prompt_rev `%s`, derive_rev `%s`, "
         "generator_policy_rev `%s`, замок модели `%s`." % (
             gen["name"], gen["model"], gen["script"], " ".join(gen["args"]), gen["generator_rev"],
             gen["prompt_rev"], dver, gen.get("generator_policy_rev"), gen.get("lock_rev") or "НЕТ"),
         "", "**Статус генератора:** %s (утверждён для generator_rev `%s`) - для приёмки: **%s**, для производства: **%s**. %s" % (
             gen["status"], gen["approved_rev"], "да" if ok else "НЕТ",
             "да" if ogs.approved_for(gen, "production") else "нет", gen["note"]), ""]
    if stale_logs:
        L += ["> Журналы решений новее плана генерации: %s. Нажми «Пересобрать» на странице ревью и "
              "запусти план заново." % ", ".join(stale_logs), ""]
    c = counts(plans)
    ready = [p for p in plans if not p["blockers"]]
    L += ["| что | сколько |", "|---|---|",
          "| логических ассетов | %d |" % c["assets"],
          "| заданий модели (AI generation jobs) | %d |" % c["ai_jobs"],
          "| файлов из ответов модели (expected outputs) | %d |" % c["model_outputs"],
          "| кадров игры прямо из ответов (с копиями в других наборах) | %d |" % c["direct_game_frames"],
          "| заданий вывода без модели (derive jobs) | %d |" % c["derive_jobs"],
          "| выведенных файлов | %d |" % c["derived_files"],
          "| выведенных кадров игры (с копиями) | %d |" % c["derived_game_frames"],
          "| готовы к заказу | %d из %d |" % (len(ready), len(plans)), "",
          "| # | категория | ассет | generation_strategy | QA_strategy | задания | выводится | блокеры |",
          "|---|---|---|---|---|---|---|---|"]
    for i, p in enumerate(plans, 1):
        L.append("| %d | %s | %s | %s | %s | %s | %s | %s |" % (
            i, p["category"], p["asset_id"], p["generation_strategy"], " + ".join(p["qa_strategy"]),
            ", ".join("%s %s" % (j["job_id"], j["row_key"]) for j in p["jobs"]),
            ", ".join("%s (%s)" % (d["key"], REL_RU.get(d["relation"], d["relation"])) for d in p["derive"]) or "-",
            "; ".join(p["blockers"]) or "нет"))
    for i, p in enumerate(plans, 1):
        L += ["", "## %d. %s - %s" % (i, p["asset_id"], p["category"]), "",
              "- generation_strategy: `%s`" % p["generation_strategy"],
              "- QA_strategy: `%s`%s" % (" + ".join(p["qa_strategy"]),
                                         "; стоит вплотную к своей копии в %.0f%% мест" % (100 * p["tile_share"])
                                         if p["tile_share"] else ""),
              "- опознание: %s `%s` (identity_rev `%s`)" % (
                  p["identity"]["status"], p["identity"]["text"] or "-", p["identity"]["identity_rev"]),
              "- семейство %s, ревизия %s, content_hash `%s`" % (p["family"]["id"] or "-", p["family"]["revision"],
                                                                 p["family"]["content_hash"] or "-")]
        for m in p["family"]["members"]:
            L.append("  - %s: %s, решение %s" % (m["key"], REL_RU.get(m["relation"], m["relation"]), m["decision"]))
        if p["family"]["open_review"]:
            L.append("  - на проверке: %s" % ", ".join(p["family"]["open_review"]))
        if p["family"]["rejected"]:
            L.append("  - отделены человеком (SPLIT): %s" % ", ".join(p["family"]["rejected"]))
        for j in p["jobs"]:
            L += ["- **задание %s** `%s` - %s%s, зерно %d, input_hash `%s`" % (
                      j["job_id"], j["name"], j["row_key"],
                      (", вид %s группы `%s`" % (j["view"], j["multiview_group"])) if j["multiview_group"] else "",
                      j["seed"], j["input_hash"]),
                  "  - входы модели: %s%s" % (
                      ", ".join("%s (source_rev `%s`)" % (x["key"], x["source_rev"]) for x in j["canonical_inputs"]),
                      ("; <image2> = ответ %s `%s`" % (j["reference"]["job_id"], j["reference"]["raw"]))
                      if j.get("reference") else ""),
                  "  - место на карте: %s %s, куски %s" % (j["map"], j["at"], " ".join(j["take"])),
                  "  - модификаторы промпта: %s" % (", ".join(j["modifiers"]) or "нет (single)")]
            if j.get("same_asset"):
                L.append("  - same_asset / same_material / same_dimensions / same_construction: да")
            L += ["  - промпт: `%s`" % (j["prompt"] or "нет - опознание не подтверждено"),
                  "  - ожидаемые файлы: %s" % ", ".join(j["expected_outputs"]),
                  "  - кадры игры (копии той же картинки): %s" % ", ".join(j["game_frames"])]
            for d in j["derive"]:
                L.append("  - **выводится** %s (%s из %s, derive_rev `%s`, input_hash `%s`): файлы %s; кадры игры %s" % (
                    d["key"], REL_RU.get(d["relation"], d["relation"]), " ".join(d["base_src"]), d["derive_rev"],
                    d["input_hash"], ", ".join(d["outputs"]), ", ".join(d["game_frames"])))
        for e in p["excluded"]:
            L.append("- не рисуется (исключён): %s (%s)" % (e["key"], e["relation"]))
        L.append("- входы ассета: %s, input_hash `%s`" % (
            ", ".join("%s `%s`" % (k, v or "-") for k, v in p["inputs"].items()), p["input_hash"]))
        L.append("- блокеры: %s" % ("; ".join(p["blockers"]) or "нет"))
    return "\n".join(L) + "\n"


def snapshot(plans, rows, gen, dver):
    """Неизменяемый снимок десятки: что именно заказывается и из каких входов, и сами задания модели
    (acceptance_run.py компилирует их ТОЛЬКО отсюда). batch_id - хэш содержимого: тот же состав и те же
    входы дают тот же id, любое отличие (промпт, зерно, место на карте) - другой id."""
    import asset_rev as ar
    ids = [p["asset_id"] for p in plans]
    jobs = [{k: v for k, v in j.items()} for p in plans for j in p["jobs"]]
    snap = {"asset_ids": ids,
            "generator": {"name": gen["name"], "model": gen["model"], "script": gen["script"], "args": gen["args"],
                          "generator_rev": gen["generator_rev"], "prompt_rev": gen["prompt_rev"],
                          "status": gen["status"], "approved_rev": gen["approved_rev"],
                          "generator_policy_rev": gen.get("generator_policy_rev"),
                          "lock_rev": gen.get("lock_rev"), "code_rev": gen.get("code_rev")},
            "derive_rev": dver,
            "counts": counts(plans),
            "jobs": jobs, "jobs_hash": ar.h12(jobs),
            "assets": [{"asset_id": p["asset_id"], "category": p["category"],
                        "generation_strategy": p["generation_strategy"], "qa_strategy": p["qa_strategy"],
                        "family": {"id": p["family"]["id"], "revision": p["family"]["revision"],
                                   "content_hash": p["family"]["content_hash"]},
                        "identity": {"status": p["identity"]["status"], "text": p["identity"]["text"],
                                     "identity_rev": p["identity"]["identity_rev"]},
                        "canonical": p["canonical"], "job_ids": [j["job_id"] for j in p["jobs"]],
                        "frames": [f["game"] for f in p["generate"]["frames"]] +
                                  [f["game"] for d in p["derive"] for f in d["frames"]],
                        "rows": [{"key": r["key"], "rank": r["rank"], "asset_id": r["asset_id"],
                                  "family": r["family"], "action": r["action"], "relation": r.get("relation", ""),
                                  "inputs": r["inputs"], "input_hash": r["input_hash"]}
                                 for r in rows if r["asset_id"] == p["asset_id"] and r["action"] in WORK]}
                       for p in plans]}
    snap["acceptance_batch_id"] = "acc-" + ar.h12(snap)
    return snap


def write_frozen(snap, folder=BATCHES):
    """Снимок на диск только для чтения; тот же id уже лежит - не трогать (содержимое то же по построению)."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, snap["acceptance_batch_id"] + ".json")
    if not os.path.exists(path):
        with open(path, "w", encoding=ENC) as f:
            json.dump(dict(snap, frozen=__import__("time").strftime("%Y-%m-%dT%H:%M:%S")), f,
                      ensure_ascii=False, indent=1)
        os.chmod(path, 0o444)                       # только для чтения: снимок не правится, а делается новый
    return path


def check_snapshot(snap, fam, items_by_rank, idrows, gen, dver, fh):
    """[(ключ, STALE | ORPHANED, что)] - чем текущие данные разошлись со снимком; пусто - BATCH_CURRENT."""
    out = []
    if gen["generator_rev"] != snap["generator"]["generator_rev"]:
        out.append(("*", "STALE", ["generator_rev"]))
    if gen["prompt_rev"] != snap["generator"]["prompt_rev"]:
        out.append(("*", "STALE", ["prompt_rev"]))
    # приёмочная десятка - утверждение для приёмки, пилотная партия (pilot_batch.py) - для пилота
    if not ogs.approved_for(gen, snap.get("use", "acceptance")):
        out.append(("*", "STALE", ["generator_not_approved"]))
    # границы применимости сменились - партия заморожена под другую политику (снимки до R-145 её не помнят)
    if "generator_policy_rev" in snap["generator"] and gen.get("generator_policy_rev") != snap["generator"]["generator_policy_rev"]:
        out.append(("*", "STALE", ["generator_policy_rev"]))
    import asset_rev as ar
    if ar.h12(snap.get("jobs", [])) != snap.get("jobs_hash"):
        out.append(("*", "STALE", ["jobs_hash"]))     # снимок правили руками мимо --freeze
    for a in snap["assets"]:
        for r in a["rows"]:
            st = dep_state(r, r["inputs"], fam, items_by_rank, idrows, gen, dver, fh)
            if st:
                out.append((r["key"], st[0], st[1]))
    return out


def check_batch(batch_id, folder=BATCHES):
    """(снимок или None, [(ключ, STALE | ORPHANED, что)]) - для acceptance_run и obj_photo --batch."""
    import asset_rev as ar
    path = os.path.join(folder, batch_id + ".json")
    if not os.path.exists(path):
        return None, [("*", "STALE", ["снимка %s нет" % batch_id])]
    snap = load(path)
    rows, fam, items_by_rank, idrows = load_state()
    return snap, check_snapshot(snap, fam, items_by_rank, idrows, ogs.spec(), ogs.derive_version(),
                                ar.frame_hashes())


def load_state():
    rows = load(os.path.join(GEN, "generation.json"))
    fam = {fm["family_id"]: fm for fm in load(FAMS)}
    items_by_rank = {it["rank"]: it for it in load(os.path.join(DISC, "items.json"))}
    import csv
    with open(os.path.join(DISC, "asset_identity.tsv"), encoding=ENC, newline="") as f:
        idrows = {r["asset_id"]: r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}
    return rows, fam, items_by_rank, idrows


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--freeze", action="store_true",
                    help="заморозить готовую десятку: снимок batches/<acceptance_batch_id>.json только для чтения")
    ap.add_argument("--check", default="", metavar="ID",
                    help="сверить снимок с текущими данными: BATCH_CURRENT (код 0) или BATCH_STALE (код 2)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    import asset_rev as ar
    fh = ar.frame_hashes()
    gen, dver = ogs.spec(), ogs.derive_version()
    if a.check:
        # GPU-задание десятки получает acceptance_batch_id и первым делом зовёт это: изменились семейство,
        # опознание, оригиналы, генератор, промпт или вывод, пока задание стояло в очереди - не едет
        snap, bad = check_batch(a.check)
        for k, st, what in bad:
            print("  %-9s %-22s %s" % (st, k, ",".join(what)))
        print("%s %s (%d ассетов)" % ("BATCH_STALE" if bad else "BATCH_CURRENT", a.check,
                                      len(snap["asset_ids"]) if snap else 0))
        sys.exit(2 if bad else 0)
    acc = load(os.path.join(GEN, "acceptance.json"))
    rows, fam, items_by_rank, idrows = load_state()
    gtime = os.path.getmtime(os.path.join(GEN, "generation.json"))
    stale_logs = [p for p in LOGS if os.path.exists(p) and os.path.getmtime(p) > gtime]
    plans = [plan_one(x, rows, fam, items_by_rank, gen, idrows, fh) for x in acc]
    number_jobs(plans, ogs.SEED0)
    for p in plans:
        # зависимости десятки не устарели: семейство, опознание, оригиналы, генератор, промпт, вывод - всё то же,
        # из чего собран план (условие первой GPU-десятки; устаревшее в остальном паке - hd_manifest freshness)
        p["deps_stale"] = deps_stale(p["asset_id"], rows, fam, items_by_rank, idrows, gen, dver, fh)
        for k, (st, diff) in p["deps_stale"].items():
            p["blockers"].append("зависимости %s у %s: %s - пересобрать план" % (st, k, ",".join(diff)))
    if a.freeze:
        why = ["%s: %s" % (p["asset_id"], "; ".join(p["blockers"])) for p in plans if p["blockers"]]
        if stale_logs:
            why.append("журналы решений новее плана генерации - Пересобрать")
        if not ogs.approved_for(gen, "acceptance"):
            why.append("генератор %s (%s, generator_rev %s) не утверждён для приёмки (obj_gen_spec)" % (
                gen["name"], gen["status"], gen["generator_rev"]))
        if why:
            raise SystemExit("не замораживаю - десятка не готова:\n  " + "\n  ".join(why))
        snap = snapshot(plans, rows, gen, dver)
        path = write_frozen(snap)
        print("заморожено: %s -> %s\nзаданий модели %d, jobs_hash %s. Запуск - только "
              "acceptance_run.py run %s (сверка снимка, компиляция заданий из него, obj_photo --batch)" % (
                  snap["acceptance_batch_id"], path, len(snap["jobs"]), snap["jobs_hash"], snap["acceptance_batch_id"]))
        return
    with open(os.path.join(GEN, "acceptance_plan.json"), "w", encoding=ENC) as f:
        json.dump({"generator": {k: v for k, v in gen.items() if k != "template"}, "derive_rev": dver,
                   "stale_logs": stale_logs, "plans": plans}, f, ensure_ascii=False, indent=1)
    out = os.path.join(GEN, "acceptance_plan.md")
    with open(out, "w", encoding=ENC) as f:
        f.write(md(plans, gen, dver, stale_logs))
    ready = sum(1 for p in plans if not p["blockers"])
    for p in plans:
        print("%-9s %-15s %-26s jobs %d  gen %d  derive %d  %s" % (
            p["category"], p["asset_id"], p["generation_strategy"], len(p["jobs"]), len(p["generate"]["frames"]),
            sum(len(d["frames"]) for d in p["derive"]), "; ".join(p["blockers"])[:90] or "готов"))
    dep = Counter(st for p in plans for st, _d in p["deps_stale"].values())
    print("зависимости десятки: %s" % ("CURRENT" if not dep else ", ".join("%s %d" % kv for kv in dep.items())))
    print("счёт: %s" % ", ".join("%s %d" % kv for kv in counts(plans).items()))
    print("готовы к заказу: %d из %d; генератор для приёмки: %s, prompt_rev %s -> %s" % (
        ready, len(plans), ogs.approved_for(gen, "acceptance"), gen["prompt_rev"], out))
    if stale_logs:
        print("!! журналы решений новее плана генерации - Пересобрать")


if __name__ == "__main__":
    main()
