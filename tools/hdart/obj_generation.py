#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Очередь генерации предметов Pipeline v2: что рисовать моделью, что выводить, что ждёт человека
(docs/HD_PIPELINE_V2.md, разделы 11-13, 20, 23, 42; P1-A).

obj_queue (discovery) -> obj_families (что одна вещь) -> ЭТОТ шаг -> obj_batch.

Единица - АССЕТ: семейство (канонический кадр и его члены) или предмет без семейства. Опознание одно на
ассет (asset_identity.tsv): подтвердил человек каноническое кресло - перекраски и другой бок не
подтверждаются заново. На строку discovery одно действие:
  GENERATE      - канонический кадр ассета: один заказ модели;
  GENERATE_WITH - другой бок (alternate_view): НЕ выводится, рисуется тем же заказом, что канонический
                  (общий холст нескольких видов, раздел 14);
  DERIVE        - перекраска или зеркало (AUTO / HUMAN_APPROVED): выводит obj_derive из канонического;
  EXCLUDE       - не предмет: floor_like (покров, лужа, разметка) и structural (рельеф, пандус, лестница,
                  стена в клетке предмета) - полы и стены никогда не идут конвейером предметов (раздел 20).
GENERATE готов (READY), только если ничто не держит:
  identity      - опознание ассета не подтверждено человеком (раздел 23: модель не рисует неопознанное);
  family_review - у ассета есть кандидаты на проверке (цепочка, слабое зеркало, возможный другой бок):
                  их решают на той же карточке ассета, что и опознание;
  in_review     - строка сама кандидат в чужое семейство: ждёт, куда её отнесут.

asset_identity.tsv (art/objects/discovery) строится здесь и руками не правится. Решения человека -
identity_decisions.tsv рядом (пишет страница проверки tools/hdart/review_server.py): CONFIRM, EDIT (свой
текст), UNKNOWN, SKIP, REOPEN (подтверждённое - снова на проверку, статус IDENTITY_REVIEW). Предложения (статус AGENT_PROPOSED) - по старшинству: описания прежних партий
(ident_*, made_*, bed18 - писал агент), ответ предлагающей модели (proposals.json, identity_propose.py),
подсказка карты (items.json hint, модель по кадру 32x40). Ответ модели UNKNOWN - не предложение (статус
NO_PROPOSAL, в строке его ambiguity). Два ответа модели назвали разные предметы (REVIEW_REQUIRED) и описания
прежних партий нет - статус REVIEW_REQUIRED без текста: подсказка карты не подставляется, догадки - в столбце
candidates, на карточке они стоят рядом, по алфавиту, без «основной» (candidate_names, кнопки A / B / Другое /
Не знаю - не якорить); review_level - сколько работы человеку. Любое предложение, с любой уверенностью, остаётся AGENT_PROPOSED
(PROPOSED_AMBIGUOUS - тоже, пометка в model_status): подтверждённым опознание делает только решение человека.

Готовые делятся на партии 10, 50, 100 и дальше по 100 (раздел 42); первая десятка - приёмочная, её
собирает acceptance_batch.py, а не порядок очереди.

    py -3.13 tools/hdart/obj_generation.py
"""
import argparse
import csv
import glob
import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import asset_rev as ar                     # noqa: E402
import obj_gen_spec as ogs                 # noqa: E402
import obj_struct as os_                   # noqa: E402

ENC = "utf-8-sig"
SIZES = (10, 50, 100)
DISC = os.path.join("art", "objects", "discovery")
ID_COLS = ("asset_id", "canonical", "rank", "members", "asset_class", "status", "identity", "source",
           "confidence", "proposed", "proposed_source", "identity_rev", "who", "when", "note",
           # ответ предлагателя (identity_propose, P1-B): только для карточки и сортировки, не подтверждение
           "proposed_name", "proposed_category", "proposed_material", "ambiguity", "evidence", "model_confidence",
           # PROPOSED / PROPOSED_AMBIGUOUS / REVIEW_REQUIRED / UNKNOWN; догадки спорного ответа - скрыты на карточке
           "model_status", "candidates",
           # сколько работы человеку (AUTO_REVIEW_EASY / HUMAN_REVIEW_LIGHT / HUMAN_REVIEW_HARD / UNKNOWN) и имена
           # догадок для выбора бок о бок на карточке HARD - по алфавиту, ни одна не первая
           "review_level", "candidate_names")
HUMAN = {"CONFIRM": "HUMAN_CONFIRMED", "EDIT": "HUMAN_EDITED", "UNKNOWN": "UNKNOWN", "SKIP": "SKIP",
         "NOT_OBJECT": "NOT_OBJECT",
         # подтверждённое опознание оказалось под вопросом (ответ модели - «не тот предмет»): снова на проверку,
         # identity_rev меняется, всё построенное на нём STALE; провалом генератора не считается (приёмка 30.09)
         "REOPEN": "IDENTITY_REVIEW"}
READY_ID = ("HUMAN_CONFIRMED", "HUMAN_EDITED")
# кандидаты, которые видны на карточке, но заказ не держат: ответит человек или нет - рисуется как есть
OPTIONAL = ("alternate_view_weak",)


def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def write_tsv(path, cols, rows):
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")).replace("\t", " ").replace("\n", " ") for c in cols) + "\n")


def batch_texts(old_items):
    """Описания прежних партий по ключу кадра: {KEY: (текст, файл)}. Номера мест в них - старой очереди,
    а номера discovery совпали (5045 из 5045), поэтому ключ берётся по номеру."""
    if not os.path.exists(old_items):
        return {}
    with open(old_items, encoding=ENC) as f:
        key_of = {it["rank"]: it["keys"][0].upper() for it in json.load(f)}
    out = {}
    for p in sorted(glob.glob("art/objects/queue/ident_*.tsv") + glob.glob("art/objects/queue/made_*.tsv")
                    + glob.glob("art/objects/queue/bed18.tsv")):
        with open(p, encoding=ENC, newline="") as f:
            for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                if r and r[0].strip().isdigit() and len(r) >= 2 and int(r[0]) in key_of:
                    out.setdefault(key_of[int(r[0])], (r[1].strip(), os.path.basename(p)))
    return out


def human_decisions(path):
    """identity_decisions.tsv - журнал, последняя запись по ассету главная."""
    out = {}
    for r in read_tsv(path):
        if r.get("asset_id") and r.get("decision") in HUMAN:
            out[r["asset_id"]] = r
    return out


# класс, который решил человек (class_decisions.tsv, последняя запись по ассету главная): правила obj_struct
# его не перебивают. structural_modular - конструкция из модулей (ферма, решётка, леса): общий генератор
# предметов её упрощает и двоит стойки на стыках (приёмка acc-5e9f63c421c0, NUKE2:10) - не предмет, EXCLUDE
STRUCTURAL_MODULAR = "structural_modular"
CLASS_COLS = ("asset_id", "asset_class", "who", "when", "note")
# кусок большого предмета (R-153: MI8:34, PLANE2:38, DAWNURBAN:110, NUKE1:11 в SIMPLE A/B v1 - брак в обоих
# режимах): подтверждённый - класс part_fragment в class_decisions.tsv, одиночным предметом не рисуется
# (EXCLUDE, PART_FRAGMENT_CONFIRMED). Подозрение - на проверку, не запрет: касание края кадра само по себе
# не признак (1224 из 2295 одиночных касаются, у ящика на всю клетку ребро на краю), слово в опознании -
# догадка модели; вместе - блокер part_fragment_suspect, снимает его класс от человека
PART_FRAGMENT = "part_fragment"
# состояние другого предмета (специалист 01.10, MADDECOR_WASTE:47 = кулер MADDECOR:50 без бутыли, грязный): связь
# STATE_VARIANT, подвид damaged - не recolor, не alternate_view и не structural_modular. Отдельным заказом не
# рисуется (EXCLUDE, STATE_VARIANT); выводится из утверждённой основы, когда будет конвейер износа. Связи -
# art/objects/discovery/state_variants.json, поиск таких пар (BASE_SET -> *_WASTE) - отложенный
# STATE_VARIANT_DISCOVERY
STATE_VARIANT = "state_variant"
FRAGMENT_WORDS = (r"fuselage|aircraft|airplane|plane|helicopter|tail fin|wing|hull|vehicle|van|truck|car|bus|"
                  r"tank|train|wagon|ship|boat|submarine|engine|nose cone|cockpit|chassis|wreck|wreckage|"
                  r"section|segment|fragment|part of|piece of|panel of")


def frame_edge(im):
    """Непрозрачных пикселей на левом, правом и верхнем краю кадра (низ - ромб пола)."""
    import numpy as np
    a = np.asarray(im.convert("RGBA"))[:, :, 3] > 0
    return int(a[:, 0].sum() + a[:, -1].sum() + a[0].sum())


def fragment_suspects(items, idrows, dec, sprite):
    """{ключ: почему} - одиночные предметы, похожие на кусок большего: слово куска в опознании (текст или
    предложение) И силуэт касается края кадра. sprite(набор, кадр) -> картинка; класс человека снимает."""
    import re
    rx = re.compile(r"\b(%s)s?\b" % FRAGMENT_WORDS)
    out = {}
    for it in items:
        key = it["keys"][0].upper()
        if it["kind"] != "один" or key in dec:
            continue
        idn = idrows.get(key, {})
        m = rx.search((idn.get("identity") or idn.get("proposed") or "").lower())
        if not m:
            continue
        s, f = it["src"][0].split(":")
        im = sprite(s, int(f))
        edge = frame_edge(im) if im is not None else 0
        if edge:
            out[key] = "край %d, слово «%s»" % (edge, m.group(1))
    return out


# Ворота опознания IDENTITY_GATE_V2 (identity_card.py, специалист 01.10): позднее решение по карточке с контекстом
# старше раннего подтверждения по кадру 32x40. Решение человека не перезаписывается, но при конфликте ассет не
# бывает READY: MADDECOR_WASTE:47 01.10 подтверждён «кучей мусора» (10:39), регрессия это отвергла, истина OPEN -
# а пересборка плана подняла его до READY по старому подтверждению.
#   identity_truth_open             - в сверке ворот (reference.tsv) identity_ok open или no
#   CONFLICTING_IDENTITY_DECISIONS  - в журнале ассета есть решение, которое регрессия отвергла
#                                     (identity_regression.json: passed_card_as + card_when, human_outcome FAIL),
#                                     а истина не закрыта yes; ворота назвали кусок или не предмет, а ассет идёт в
#                                     заказ; или подтверждённый текст не тот, что ответ ворот
GATE_PROBES = os.path.join("art", "objects", "generation", "probes", "identity-gate-*")
REGRESSION = os.path.join(DISC, "identity_regression.json")
CONFLICT = "CONFLICTING_IDENTITY_DECISIONS"
TRUTH_OPEN = "identity_truth_open"


def norm_text(s):
    return " ".join((s or "").lower().split())


def identity_gates(probes=GATE_PROBES, regression=REGRESSION, decisions=""):
    """{ASSET: {truth, status, identity, failed}} по воротам опознания: сверка и ответы каждой папки ворот,
    отвергнутые регрессией решения журнала (failed - строки identity_decisions, которые регрессия признала
    провалом)."""
    out = {}
    for d in sorted(glob.glob(probes)):
        for r in read_tsv(os.path.join(d, "answers_vitali.tsv")):
            if r.get("asset_id"):
                g = out.setdefault(r["asset_id"].upper(), {})
                g.update(status=r.get("status", "").strip(), identity=r.get("final_identity", "").strip())
        for r in read_tsv(os.path.join(d, "reference.tsv")):
            if r.get("asset_id"):
                out.setdefault(r["asset_id"].upper(), {})["truth"] = (r.get("identity_ok") or "open").strip().lower()
    bad = set()
    if os.path.exists(regression):
        with open(regression, encoding=ENC) as f:
            for x in json.load(f).get("items", []):
                if x.get("human_outcome") == "FAIL" and x.get("passed_card_as"):
                    bad.add((x["asset_id"].upper(), x["passed_card_as"], x.get("card_when", "")))
    for r in read_tsv(decisions) if decisions else []:
        k = (r.get("asset_id", "").upper(), r.get("decision", ""), r.get("when", ""))
        if k in bad:
            out.setdefault(k[0], {}).setdefault("failed", []).append("%s %s" % (k[1], k[2]))
    return out


def gate_blockers(key, gates, idn, action):
    """Блокеры ворот опознания для строки заказа (пусто - ворота не против)."""
    g = (gates or {}).get(key)
    if not g:
        return []
    out = []
    truth = g.get("truth")
    if truth in ("open", "no"):
        out.append(TRUTH_OPEN)
    conflict = bool(g.get("failed")) and truth != "yes"
    if action == "GENERATE" and g.get("status") in ("PART_FRAGMENT_CONFIRMED", "NOT_OBJECT"):
        conflict = True
    text = norm_text(idn.get("identity"))
    if text and g.get("status") == "IDENTITY_VISUALLY_VERIFIED" and text != norm_text(g.get("identity")):
        conflict = True
    if conflict:
        out.append(CONFLICT)
    return out


def class_decisions(path):
    return {r["asset_id"].upper(): r for r in read_tsv(path) if r.get("asset_id") and r.get("asset_class")} \
        if os.path.exists(path) else {}


def apply_class_decisions(items, fams, dec):
    """Класс человека - на ассет целиком: у семейства на всех членов, у одиночки на строку. -> сколько ассетов."""
    done = set()
    for fm in fams:
        d = dec.get(fm["family_id"].upper())
        if d:
            for m in fm["members"]:
                m.update(asset_class=d["asset_class"], class_why="человек: " + (d.get("note") or d["asset_class"]))
            done.add(fm["family_id"].upper())
    for it in items:
        d = dec.get(it["keys"][0].upper())
        if d:
            it.update(asset_class=d["asset_class"], class_why="человек: " + (d.get("note") or d["asset_class"]))
            done.add(it["keys"][0].upper())
    return len(done)


def plan(items, fams, idrows, gates=None):
    """-> строки очереди [{rank, key, action, status, blockers, asset_id, ...}] в порядке популярности.
    idrows - {asset_id: строка asset_identity}; gates - identity_gates(): при конфликте или открытой истине
    ассет не бывает READY."""
    member, review = {}, {}
    for fm in fams:
        for m in fm["members"]:
            member[m["keys"][0].upper()] = (fm, m)
        for m in fm["review"]:
            if m["reason"] not in OPTIONAL:
                review.setdefault(m["keys"][0].upper(), []).append((fm, m["reason"]))
    rows = []
    for it in sorted(items, key=lambda it: it["rank"]):
        key = it["keys"][0].upper()
        fm, m = member.get(key, (None, None))
        cls = (m or {}).get("asset_class") or it.get("asset_class") or "object"
        aid = fm["family_id"] if fm else key
        row = {"rank": it["rank"], "key": key, "kind": it["kind"], "places": it["places"], "asset_id": aid,
               "family": fm["family_id"] if fm else "", "revision": fm["revision"] if fm else 0,
               "relation": m["relation"] if m else "", "asset_class": cls, "blockers": []}
        fam_cls = fm["members"][0].get("asset_class", "object") if fm else cls
        idn = idrows.get(aid, {})
        if fam_cls not in os_.OBJECTISH or idn.get("status") == "NOT_OBJECT":
            status = "PART_FRAGMENT_CONFIRMED" if fam_cls == PART_FRAGMENT else fam_cls.upper()
            row.update(action="EXCLUDE", status=status if fam_cls not in os_.OBJECTISH else "NOT_OBJECT",
                       why=(m or it).get("class_why", "") or "человек: не предмет")
            rows.append(row)
            continue
        rel = m["relation"] if m else ""
        if m and rel in ("recolor", "mirror") and m["decision"] in ("AUTO", "HUMAN_APPROVED"):
            row.update(action="DERIVE", derive_from=fm["canonical"])
        elif m and rel == "alternate_view":
            row.update(action="GENERATE_WITH", generate_with=fm["canonical"])
        else:
            row["action"] = "GENERATE"
            if fm:
                row["derive_after"] = [x["keys"][0] for x in fm["members"][1:] if x["relation"] in ("recolor", "mirror")]
                row["views"] = [x["keys"][0] for x in fm["members"][1:] if x["relation"] == "alternate_view"]
                need = [x for x in fm["review"] if x["reason"] not in OPTIONAL]
                if need:
                    row["blockers"].append("family_review:%d" % len(need))
            if key in review and not m:
                row["blockers"].append("in_review:" + ",".join(sorted({why for _f, why in review[key]})))
            if it.get("fragment_suspect"):
                row["blockers"].append("part_fragment_suspect")
                row["fragment_why"] = it["fragment_suspect"]
        row["identity"] = idn.get("identity", "")
        row["identity_status"] = idn.get("status", "")
        if idn.get("status") == "SKIP":
            row.update(status="SKIP")
            rows.append(row)
            continue
        if idn.get("status") not in READY_ID:
            row["blockers"].append("identity")
            if fam_cls == os_.UNCERTAIN:
                row["blockers"].append("class_check")       # предмет или рельеф - вопрос на той же карточке
        row["blockers"] += gate_blockers(aid.upper(), gates, idn, row["action"])
        if row["action"] == "GENERATE":
            row["status"] = "BLOCKED" if row["blockers"] else "READY"
        else:
            row["status"] = "WAIT_CANONICAL"
        rows.append(row)
    b, left = 1, SIZES[0]
    for row in rows:
        if row["status"] == "READY":
            row["batch"] = b
            left -= 1
            if left == 0:
                b += 1
                left = SIZES[min(b - 1, len(SIZES) - 1)]
    return rows


def build_identity(items, fams, prev, human, batch, proposals):
    """asset_identity: строка на ассет-предмет (канонический или одиночка), статус и текст."""
    in_fam = {}
    for fm in fams:
        for m in fm["members"]:
            in_fam[m["keys"][0].upper()] = fm
    by_key = {it["keys"][0].upper(): it for it in items}
    out = {}
    for it in sorted(items, key=lambda it: it["rank"]):
        key = it["keys"][0].upper()
        fm = in_fam.get(key)
        if fm and fm["family_id"] != key:
            continue                                        # член - опознание от канонического
        if (fm["members"][0].get("asset_class", "object") if fm else it.get("asset_class", "object")) not in os_.OBJECTISH:
            continue
        aid = key
        mem = fm["members"] if fm else []
        # предложение: прежние партии -> модель-предлагатель -> подсказка карты; у семейства - от любого
        # члена по порядку (каноническое первым)
        cand = []
        keys = [key] + [x["keys"][0].upper() for x in mem[1:]]
        for k in keys:
            if k in batch and batch[k][0] and batch[k][0] != "SKIP":
                cand.append((batch[k][0], "agent_batch:" + batch[k][1], 0.6))
        model_pr = None                                     # ответ предлагателя (P1-B): поля идут в строку
        for k in keys:
            if k in proposals:
                pr = proposals[k]
                model_pr = model_pr or pr
                if pr.get("proposed_name", "") == "UNKNOWN":
                    continue                                # UNKNOWN - не предложение: карточка без текста
                text = pr.get("short_description") or pr.get("proposed_name") or pr.get("en", "")
                cand.append((text, "agent_model:" + pr.get("model", ""), float(pr.get("confidence", 0.5))))
        # два ответа модели назвали разные предметы (REVIEW_REQUIRED): карточка без имени - ни подсказкой карты,
        # ни первой догадкой не подменять (якорит человека); прежние партии, писанные агентом, - старше модели
        conflict = bool(model_pr) and model_pr.get("status") == "REVIEW_REQUIRED" and not cand
        for k in keys:
            hint = by_key.get(k, {}).get("hint", "").replace("[фото] ", "")
            if hint and not conflict:
                cand.append((hint, "map_hint", 0.3))
        prop = next((c for c in cand if c[0]), ("", "", 0.0))
        skip = key in batch and batch[key][0] == "SKIP"
        row = {"asset_id": aid, "canonical": key, "rank": it["rank"], "members": len(mem) or 1,
               "asset_class": (mem[0].get("asset_class") if mem else "object"),
               "proposed": prop[0], "proposed_source": prop[1], "confidence": prop[2]}
        if model_pr:
            row.update(proposed_name=model_pr.get("proposed_name", ""),
                       proposed_category=model_pr.get("proposed_category", ""),
                       proposed_material=model_pr.get("proposed_material", ""),
                       ambiguity=model_pr.get("ambiguity", ""), evidence=",".join(model_pr.get("evidence", [])),
                       model_confidence=model_pr.get("confidence", ""), model_status=model_pr.get("status", ""),
                       # догадки спорного ответа: страница показывает их только по запросу
                       candidates=" | ".join("%s (%s)" % (c.get("proposed_name", ""), c.get("proposed_category", ""))
                                             for c in model_pr.get("candidates", [])),
                       review_level=model_pr.get("review_level", ""),
                       candidate_names=" | ".join(sorted({c.get("proposed_name", "").replace("|", "/").strip()
                                                          for c in model_pr.get("candidates", [])} - {""},
                                                         key=str.lower)))
            if conflict:
                hints = [by_key.get(k, {}).get("hint", "").replace("[фото] ", "") for k in keys]
                parts = [row["candidates"]] if row["candidates"] else []
                row["candidates"] = " | ".join(parts + ["подсказка карты: " + h for h in hints if h])
        h = human.get(aid)
        if h:
            st = HUMAN[h["decision"]]
            text = h.get("identity", "").strip() if h["decision"] == "EDIT" else prop[0]
            row.update(status=st, identity=text if st in READY_ID else "", source="human",
                       who=h.get("who", ""), when=h.get("when", ""), note=h.get("note", ""))
            if st == "HUMAN_CONFIRMED" and not text:
                row.update(status="UNKNOWN", note="CONFIRM без предложенного текста - нужен EDIT")
            if st == "IDENTITY_REVIEW":                     # было подтверждено - текст виден на карточке, не готово
                was = h.get("identity", "").strip()
                row["note"] = ("вернули на проверку%s; %s" % (" (было: %s)" % was if was else "",
                                                              h.get("note", ""))).strip("; ")
        elif skip:
            row.update(status="SKIP", source="agent_batch", identity="")
        elif prop[0]:
            row.update(status="AGENT_PROPOSED", identity="", source=prop[1])
        elif conflict:
            row.update(status="REVIEW_REQUIRED", identity="", source="agent_model")
        else:
            row.update(status="NO_PROPOSAL", identity="", source="")
        row["identity_rev"] = ar.identity_rev(row)
        old = prev.get(aid)
        if old and old.get("identity_rev") != row["identity_rev"] and old.get("status") in READY_ID:
            row["note"] = (row.get("note", "") + " опознание изменилось: выходы этого ассета STALE").strip()
        out[aid] = row
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default=os.path.join(DISC, "items.json"))
    ap.add_argument("--families", default="art/objects/families/families.json")
    ap.add_argument("--identity", default=os.path.join(DISC, "asset_identity.tsv"))
    ap.add_argument("--decisions", default=os.path.join(DISC, "identity_decisions.tsv"))
    ap.add_argument("--proposals", default=os.path.join(DISC, "proposals.json"))
    ap.add_argument("--classes", default=os.path.join(DISC, "class_decisions.tsv"))
    ap.add_argument("--old-items", default="art/objects/queue/items.json")
    ap.add_argument("--out", default="art/objects/generation")
    a = ap.parse_args()
    with open(a.items, encoding=ENC) as f:
        items = json.load(f)
    with open(a.families, encoding=ENC) as f:
        fams = json.load(f)
    # класс одиночки без семейства: берётся из families.json, где он посчитан для всех строк, что там есть;
    # остальным - obj_struct прямо здесь
    cls = {m["keys"][0].upper(): m.get("asset_class") for fm in fams for m in fm["members"] + fm["review"]}
    for it in items:
        if cls.get(it["keys"][0].upper()):
            it["asset_class"] = cls[it["keys"][0].upper()]
    missing = [it for it in items if not cls.get(it["keys"][0].upper())]
    if missing:
        import map_mockup as mm
        st = os_.Struct(mm.World())
        for it in missing:
            got = []
            for k in it["src"] if it["kind"] == "составной" else it["src"][:1]:
                s, fr = k.split(":")
                got.append(os_.asset_class(st.info(s, int(fr))))
            obj = [g for g in got if g[0] == "object"] or [g for g in got if g[0] in os_.OBJECTISH]
            it["asset_class"], it["class_why"] = (obj[0] if obj else got[0])
    cdec = class_decisions(a.classes)
    n_cls = apply_class_decisions(items, fams, cdec)
    if n_cls:
        print("класс решил человек: %d ассет(ов) (%s)" % (n_cls, a.classes))
    prev = {r["asset_id"]: r for r in read_tsv(a.identity)}
    proposals = {}
    if os.path.exists(a.proposals):
        with open(a.proposals, encoding=ENC) as f:
            proposals = {k.upper(): v for k, v in json.load(f).items()}
    if not os.path.exists(a.decisions):
        write_tsv(a.decisions, ("asset_id", "decision", "identity", "who", "when", "note"), [])
    idrows = build_identity(items, fams, prev, human_decisions(a.decisions), batch_texts(a.old_items), proposals)
    write_tsv(a.identity, ID_COLS, sorted(idrows.values(), key=lambda r: int(r["rank"])))
    import map_mockup as mm
    world = mm.World()
    sus = fragment_suspects(items, idrows, cdec, lambda s, f: world.sprite(s.lower(), f, None))
    for it in items:
        if it["keys"][0].upper() in sus:
            it["fragment_suspect"] = sus[it["keys"][0].upper()]
    gates = identity_gates(decisions=a.decisions)
    rows = plan(items, fams, idrows, gates)
    held = sorted({r["key"] for r in rows if set(r["blockers"]) & {CONFLICT, TRUTH_OPEN}})
    if held:
        print("ворота опознания держат: %s" % ", ".join(held))
    # входы каждого ассета (asset_rev): у готового выхода они записываются, и verify находит устаревшее
    fh = ar.frame_hashes()
    fam_by = {fm["family_id"]: fm for fm in fams}
    src_of = {it["rank"]: it["src"] for it in items}
    gen = ogs.spec()
    dver = ogs.derive_version()
    for r in rows:
        fm = fam_by.get(r["family"])
        can_src = fm["members"][0]["src"] if fm else src_of[r["rank"]]
        kw = {}
        if r["action"] in ("GENERATE", "GENERATE_WITH", "DERIVE"):
            # выведенный член - из картинки канонического: её генератор и промпт - тоже его входы
            kw = {"generator": gen["generator_rev"], "prompt": gen["prompt_rev"]}
            r["generator"] = gen["name"]
        if r["action"] == "DERIVE":
            kw.update(member_src=src_of[r["rank"]], derive=dver)
        r["inputs"] = ar.inputs(fm, idrows.get(r["asset_id"]), can_src, fh=fh, **kw)
        r["input_hash"] = ar.input_hash(r["inputs"])
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "generation.json"), "w", encoding=ENC) as f:
        json.dump(rows, f, ensure_ascii=False, indent=0)
    cols = ("rank", "key", "kind", "places", "asset_id", "asset_class", "action", "status", "batch", "family",
            "relation", "blockers", "identity_status", "identity", "input_hash", "fragment_why")
    write_tsv(os.path.join(a.out, "generation.tsv"), cols,
              [dict(r, blockers=" ".join(r["blockers"])) for r in rows])
    act = Counter(r["action"] for r in rows)
    st = Counter(r["status"] for r in rows)
    bl = Counter(x.split(":")[0] for r in rows for x in r["blockers"])
    ids = Counter(r["status"] for r in idrows.values())
    print("строк discovery: %d; %s" % (len(rows), ", ".join("%s %d" % kv for kv in act.most_common())))
    print("статус: %s" % ", ".join("%s %d" % kv for kv in st.most_common()))
    print("что держит заказы модели: %s" % ", ".join("%s %d" % kv for kv in bl.most_common()))
    print("ассетов-предметов на опознание: %d; %s" % (len(idrows), ", ".join("%s %d" % kv for kv in ids.most_common())))
    print("-> %s, %s  (%s)" % (a.identity, os.path.join(a.out, "generation.tsv"), time.strftime("%H:%M")))


if __name__ == "__main__":
    main()
