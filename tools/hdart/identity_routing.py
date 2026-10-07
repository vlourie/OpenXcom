#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""IDENTITY_ROUTING_V3 - диагностика схемы ответа на тех же 28 предметах (специалист 01.10, после FAIL holdout V2). CPU.

Holdout IDENTITY_GATE_V2 провалился на классе (0.714), и все 8 ошибок - в безопасную сторону: ни одного ложного
самостоятельного. Гипотеза специалиста: статус V2 смешивает две оси - ЧТО это (смысл) и КАК это рисовать
(маршрут в конвейер). Стойка шасси - часть самолёта по смыслу, но рисуется своим заказом; кадр составного -
единица генерации, но визуально кусок. Здесь те же 28 карточек (картинки побайтно те же, копия), а ответ - по двум
независимым осям плюс final_identity:

    A  SEMANTIC_KIND  что это вообще        OBJECT / OBJECT_PART / TERRAIN_RELIEF / NOT_OBJECT / UNSURE
    B  RENDER_UNIT    как попадает в HD     STANDALONE_RENDER / COMPOSITE_PART / STRUCTURAL_MODULAR /
                                            STATE_VARIANT / DERIVED / EXCLUDE / REVIEW

Это ДИАГНОСТИКА, не приёмка: ворот нет, Vitali уже видел эталон V1 (итог holdout в чате), поэтому разметка не
слепая. Вопрос один - исчезают ли 8 расхождений класса V2, когда оси разделены. Если да - замораживать новый
слепой holdout V3 на новых предметах.

Определения осей (SPEC ниже) замораживаются в spec.json ДО ответов и до эталона; эталон по двум осям
(reference_v2.tsv) собирается независимо от ответов, по источникам в порядке силы: MCD и смысл террейна, состав и
расстановка, побайтные копии, состояния и семейства, и только потом зрительный разбор. Нет доказательств - open,
это не ошибка человека. Эталон V1 holdout (reference.tsv) сохранён как REFERENCE_V1_BLIND_AGENT.

Карточка V3 отличается от V2 только формой ответа и подписями гипотез: прежнее описание - «UNVERIFIED OLD
DESCRIPTION», ответы моделей - «MODEL HYPOTHESIS A / B», статус в базе - тоже гипотеза (против якоря).

    py -3.13 tools/hdart/identity_routing.py spec      заморозить определения (повторно - отказ; после ответов - отказ)
    py -3.13 tools/hdart/identity_routing.py spec --refreeze "причина"   до ответов: прежний -> spec.vN.json
    py -3.13 tools/hdart/identity_routing.py cards     страница по карточкам holdout V2 (картинки копируются)
    py -3.13 tools/hdart/identity_routing.py check     spec и картинки не менялись
    py -3.13 tools/hdart/identity_routing.py report    ответы против reference_v2.tsv: оси, матрицы, 8 расхождений V2
Ответы: <out>/answers_vitali.tsv - asset_id, final_identity, semantic_kind, render_unit, missing_context, note.
Эталон: <out>/reference_v2.tsv - asset_id, ref_semantic_kind, ref_render_unit (значение или open), truth_identity,
semantic (closed / open), relation, sources (через запятую, сильные первыми), evidence; после ответов -
необязательный semantic_ok (yes / no / open) и semantic_why: сверка названия, как в V2.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ENC = "utf-8-sig"
PROBES = os.path.join("art", "objects", "generation", "probes")
SRC = os.path.join(PROBES, "identity-gate-v2-holdout")
OUT = os.path.join(PROBES, "identity-routing-v3-diag")

SEMANTIC = ["OBJECT", "OBJECT_PART", "TERRAIN_RELIEF", "NOT_OBJECT", "UNSURE"]
ROUTING = ["STANDALONE_RENDER", "COMPOSITE_PART", "STRUCTURAL_MODULAR", "STATE_VARIANT", "DERIVED", "EXCLUDE",
           "REVIEW"]
# DANGEROUS_FALSE_STANDALONE (специалист 01.10, главный показатель будущего holdout V3): одиночный заказ там, где
# кадр рисуется с другими, выводится из основы (MADDECOR_WASTE:47) или вовсе не предметным конвейером
DANGEROUS_REF = ("COMPOSITE_PART", "STRUCTURAL_MODULAR", "STATE_VARIANT", "DERIVED", "EXCLUDE")
# обратная, дешёвая ошибка: самостоятельный кадр отправлен куда угодно, кроме одиночного заказа (включая REVIEW)
OVERCONSERVATIVE = ("COMPOSITE_PART", "STRUCTURAL_MODULAR", "STATE_VARIANT", "DERIVED", "EXCLUDE", "REVIEW")
SPEC = {
    "semantic_kind": {
        "OBJECT": "законченная вещь сама по себе: мебель, машина целиком, растение, ящик, фигура",
        "OBJECT_PART": "часть вещи или машины: кусок корпуса, четверть купола, стойка шасси, хвост вертолёта, "
                       "изголовье кровати на две клетки",
        "TERRAIN_RELIEF": "рельеф местности: скала, склон, кратер, осыпь, камни как часть земли",
        "NOT_OBJECT": "стена, пол, крыша, эффект - строительный элемент или не вещь",
        "UNSURE": "не ясно - отметить, какого контекста не хватило; не угадывать"},
    "render_unit": {
        "STANDALONE_RENDER": "кадр рисуется сам, одним заказом, законченной картинкой своей клетки - даже если по "
                             "смыслу это часть большего (стойка шасси в своей клетке)",
        "COMPOSITE_PART": "кадр имеет смысл только как часть КОНКРЕТНОГО многокадрового объекта и отдельно не "
                          "является полноценным модулем: рисуется вместе с соседними кадрами одной картинкой "
                          "(составной заказ) и режется по клеткам (кусок вертолёта, четверть купола)",
        "STRUCTURAL_MODULAR": "самостоятельный конструктивный модуль: может стоять отдельно и/или собираться с "
                              "другими модулями в более крупную конструкцию (секции колонны C_INT:25 / :27, "
                              "стеллажа, трубы); рисуется модулем со стыками",
        "STATE_VARIANT": "другое состояние другого предмета (разрушенный, грязный, открытый): выводится из основы",
        "DERIVED": "точная копия, перекраска или зеркало кадра, который рисуется сам: выводится, не рисуется",
        "EXCLUDE": "в конвейер предметов не идёт: пол, стена, рельеф, эффект - у них свои конвейеры",
        "REVIEW": "не ясно, как обрабатывать"},
    "precedence": "если подходит несколько B: EXCLUDE > STATE_VARIANT > DERIVED > (COMPOSITE_PART или "
                  "STRUCTURAL_MODULAR) > STANDALONE_RENDER. COMPOSITE_PART и STRUCTURAL_MODULAR взаимоисключающие "
                  "по смыслу, порядка между ними нет: кусок одного конкретного объекта - COMPOSITE_PART, модуль, "
                  "живущий и отдельно, и в сборке - STRUCTURAL_MODULAR. DERIVED - только когда основа другая и "
                  "вариант получается из неё без своего творческого рендера (у основы семейства - её собственная "
                  "форма заказа); STATE_VARIANT - основа другой canonical-ассет, этот кадр - её состояние",
    "axes_independent": "A и B отвечаются отдельно: OBJECT_PART + STANDALONE_RENDER законно (стойка шасси), "
                        "OBJECT_PART + COMPOSITE_PART тоже (четверть купола)",
    "dangerous": "DANGEROUS_FALSE_STANDALONE: ответ B STANDALONE_RENDER при эталоне %s - лишняя независимая "
                 "генерация (главный показатель безопасности)" % "/".join(DANGEROUS_REF),
    "overconservative": "OVERCONSERVATIVE_ROUTING: эталон STANDALONE_RENDER, ответ %s - дешевле опасной, но "
                        "нежелательна" % "/".join(OVERCONSERVATIVE),
    "status": "DIAGNOSTIC, не приёмка: ворот нет; Vitali видел эталон V1 до этой разметки",
}
ANS_HEAD = ["asset_id", "final_identity", "semantic_kind", "render_unit", "missing_context", "note"]
REF_HEAD = ["asset_id", "ref_semantic_kind", "ref_render_unit", "truth_identity", "semantic", "relation", "sources",
            "evidence"]


def sha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def read_tsv(path):
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def load_json(path):
    with open(path, encoding=ENC) as f:
        return json.load(f)


def dump_json(path, data):
    with open(path, "w", encoding=ENC) as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def freeze_spec(out, src=SRC, refreeze="", decided=""):
    """Заморозить определения. refreeze - причина перезаморозки: только до ответов, прежние -> spec.vN.json."""
    path = os.path.join(out, "spec.json")
    if os.path.exists(os.path.join(out, "answers_vitali.tsv")):
        raise SystemExit("ответы уже есть - определения после ответов не замораживаются")
    prev = None
    if os.path.exists(path):
        if not refreeze:
            raise SystemExit("spec уже заморожен: %s (перезаморозка до ответов - --refreeze \"причина\")" % path)
        prev = load_spec(out)
        k = 1
        while os.path.exists(os.path.join(out, "spec.v%d.json" % k)):
            k += 1
        os.replace(path, os.path.join(out, "spec.v%d.json" % k))
    hold = load_json(os.path.join(src, "holdout.json"))
    os.makedirs(out, exist_ok=True)
    body = {"spec": SPEC, "semantic": SEMANTIC, "routing": ROUTING, "holdout_sha256": hold["sha256"],
            "assets": [x["asset_id"] for x in hold["items"]]}
    data = dict(body, created=time.strftime("%Y-%m-%dT%H:%M:%S"), sha256=sha(body),
                decided=decided or "специалист 01.10 (после FAIL holdout V2), передал Vitali в чате 01.10")
    if prev:
        data.update(replaces=prev["sha256"], replaced_created=prev["created"], refreeze_reason=refreeze)
    dump_json(path, data)
    print("определения заморожены (sha256 %s), предметов %d%s" % (
        data["sha256"][:12], len(body["assets"]), "; заменяют %s" % prev["sha256"][:12] if prev else ""))
    return data


def load_spec(out):
    d = load_json(os.path.join(out, "spec.json"))
    body = {k: d[k] for k in ("spec", "semantic", "routing", "holdout_sha256", "assets")}
    if sha(body) != d["sha256"]:
        raise SystemExit("spec.json изменён после заморозки: хэш не сходится")
    return d


def holdout_cards(src):
    """Данные карточек V2 (с панелями) - из страницы holdout, чтобы картинки и порядок были те же."""
    with open(os.path.join(src, "index.html"), encoding="utf-8") as f:
        page = f.read()
    m = re.search(r"const DATA = (\[.*?\]), MISS = (\[.*?\]), CERT", page, re.S)
    if not m:
        raise SystemExit("в %s нет DATA карточек" % src)
    return json.loads(m.group(1)), json.loads(m.group(2))


def img_digest(folder):
    h = hashlib.sha256()
    for f in sorted(os.listdir(folder)):
        with open(os.path.join(folder, f), "rb") as fh:
            h.update(f.encode() + b"\0" + hashlib.sha256(fh.read()).digest())
    return h.hexdigest()


def make_cards(out, src=SRC):
    spec = load_spec(out)
    data, miss = holdout_cards(src)
    if sorted(c["asset"] for c in data) != sorted(spec["assets"]):
        raise SystemExit("карточки holdout не совпадают со списком spec")
    img = os.path.join(out, "img")
    if os.path.isdir(img):                      # перезаморозка определений: страница заново, картинки не трогаются
        if img_digest(img) != img_digest(os.path.join(src, "img")):
            raise SystemExit("img отличается от картинок holdout - карточки испорчены, не перестраиваю")
    else:
        shutil.copytree(os.path.join(src, "img"), img)
    same = img_digest(img) == img_digest(os.path.join(src, "img"))
    key = "identity-routing-v3-" + os.path.basename(os.path.normpath(out))
    page = (PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__MISS__", json.dumps(miss))
            .replace("__SEM__", json.dumps(SEMANTIC)).replace("__ROUTE__", json.dumps(ROUTING))
            .replace("__DEFS__", json.dumps(spec["spec"], ensure_ascii=False)).replace("__KEY__", key))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    dump_json(os.path.join(out, "cards.json"), {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "source": src.replace(os.sep, "/"),
        "img_sha256": img_digest(img), "images_identical_to_v2": same, "spec_sha256": spec["sha256"],
        "assets": [c["asset"] for c in data]})
    print("карточек %d, картинки побайтно те же: %s" % (len(data), "да" if same else "НЕТ"))
    gen = os.path.abspath(os.path.join(ROOT, "art", "objects", "generation"))
    if os.path.abspath(out).startswith(gen):
        rel = os.path.relpath(os.path.abspath(out), gen).replace(os.sep, "/")
        print("страница: http://localhost:8778/%s/index.html" % rel)


def rate(k, n):
    return round(k / n, 3) if n else None


def judge(a, r):
    """Одна строка: оси отдельно. None - не оценивается (UNSURE / REVIEW у человека или open в эталоне)."""
    sk, ru = a.get("semantic_kind", ""), a.get("render_unit", "")
    rs, rr = (r.get("ref_semantic_kind") or "open"), (r.get("ref_render_unit") or "open")
    j = {"sem_kind_ok": None, "route_ok": None, "dangerous": False, "overconservative": False,
         "sem_ok": None}
    j["overconservative"] = rr == "STANDALONE_RENDER" and ru in OVERCONSERVATIVE
    if sk != "UNSURE" and rs != "open":
        j["sem_kind_ok"] = sk == rs
    if ru != "REVIEW" and rr != "open":
        j["route_ok"] = ru == rr
    j["dangerous"] = ru == "STANDALONE_RENDER" and rr in DANGEROUS_REF
    name = (r.get("semantic_ok") or "").strip().lower()
    if name in ("yes", "no") and r.get("semantic") == "closed":
        j["sem_ok"] = name == "yes"
    return j


def report(out, src=SRC, answers="", reference=""):
    spec = load_spec(out)
    answers = answers or os.path.join(out, "answers_vitali.tsv")
    reference = reference or os.path.join(out, "reference_v2.tsv")
    for p in (answers, reference):
        if not os.path.exists(p):
            raise SystemExit("нет %s" % p)
    ans = {r["asset_id"]: r for r in read_tsv(answers)}
    ref = {r["asset_id"]: r for r in read_tsv(reference)}
    bad = []
    for a in spec["assets"]:
        x, r = ans.get(a), ref.get(a)
        if not x:
            bad.append("%s: нет ответа" % a)
            continue
        if x.get("semantic_kind") not in SEMANTIC:
            bad.append("%s: semantic_kind '%s' не из списка" % (a, x.get("semantic_kind")))
        if x.get("render_unit") not in ROUTING:
            bad.append("%s: render_unit '%s' не из списка" % (a, x.get("render_unit")))
        if not r:
            bad.append("%s: нет строки эталона" % a)
            continue
        if (r.get("ref_semantic_kind") or "open") not in SEMANTIC[:-1] + ["open"]:
            bad.append("%s: ref_semantic_kind '%s'" % (a, r.get("ref_semantic_kind")))
        if (r.get("ref_render_unit") or "open") not in ROUTING[:-1] + ["open"]:
            bad.append("%s: ref_render_unit '%s'" % (a, r.get("ref_render_unit")))
    # расхождения класса V2: статус окончательных ответов holdout против эталона V1
    v2 = {}
    pa, pr = os.path.join(src, "answers_vitali.tsv"), os.path.join(src, "reference.tsv")
    if os.path.exists(pa) and os.path.exists(pr):
        va = {r["asset_id"]: r for r in read_tsv(pa)}
        v2 = {r["asset_id"]: (va.get(r["asset_id"], {}).get("status", ""), r["ref_status"]) for r in read_tsv(pr)}
    layers = {}
    if os.path.exists(os.path.join(src, "holdout.json")):
        layers = {x["asset_id"]: x["layer"] for x in load_json(os.path.join(src, "holdout.json"))["items"]}
    rows = []
    for a in spec["assets"]:
        x, r = ans.get(a, {}), ref.get(a, {})
        j = judge(x, r)
        st, rs = v2.get(a, ("", ""))
        rows.append(dict(j, asset_id=a, layer=layers.get(a, ""), semantic_kind=x.get("semantic_kind", ""),
                         render_unit=x.get("render_unit", ""), ref_semantic_kind=r.get("ref_semantic_kind") or "open",
                         ref_render_unit=r.get("ref_render_unit") or "open", final_identity=x.get("final_identity", ""),
                         truth_identity=r.get("truth_identity", ""), sources=r.get("sources", ""),
                         v2_status=st, v2_ref=rs, v2_mismatch=bool(st and rs and st != rs),
                         missing_context=(x.get("missing_context") or "").strip()))

    def measure(rs):
        n = len(rs)
        sk = [r for r in rs if r["sem_kind_ok"] is not None]
        ro = [r for r in rs if r["route_ok"] is not None]
        nm = [r for r in rs if r["sem_ok"] is not None]
        return {"n": n,
                "semantic_kind_accuracy": rate(sum(r["sem_kind_ok"] for r in sk), len(sk)), "semantic_kind_n": len(sk),
                "render_unit_accuracy": rate(sum(r["route_ok"] for r in ro), len(ro)), "render_unit_n": len(ro),
                "dangerous_false_standalone": sum(r["dangerous"] for r in rs),
                "overconservative_routing": sum(r["overconservative"] for r in rs),
                "name_accuracy": rate(sum(r["sem_ok"] for r in nm), len(nm)), "name_n": len(nm),
                "unsure_rate": rate(sum(r["semantic_kind"] == "UNSURE" for r in rs), n),
                "review_rate": rate(sum(r["render_unit"] == "REVIEW" for r in rs), n),
                "missing_context_rate": rate(sum(bool(r["missing_context"]) for r in rs), n),
                "ref_open_semantic_kind": sum(r["ref_semantic_kind"] == "open" for r in rs),
                "ref_open_render_unit": sum(r["ref_render_unit"] == "open" for r in rs)}

    total = measure(rows)
    by_layer = {lay: measure([r for r in rows if r["layer"] == lay]) for lay in
                sorted({r["layer"] for r in rows if r["layer"]})}
    mism = [r for r in rows if r["v2_mismatch"]]
    # главный показатель: сколько из расхождений V2 перестали быть настоящей ошибкой маршрута
    resolved = {"n": len(mism),
                "routing_error_gone": sum(r["route_ok"] is True for r in mism),
                "routing_error_left": sum(r["route_ok"] is False for r in mism),
                "routing_unresolved": sum(r["route_ok"] is None for r in mism),
                "render_unit_agrees": sum(r["route_ok"] is True for r in mism),
                "semantic_kind_agrees": sum(r["sem_kind_ok"] is True for r in mism),
                "both_agree": sum(r["route_ok"] is True and r["sem_kind_ok"] is True for r in mism),
                "ref_open": sum(r["route_ok"] is None or r["sem_kind_ok"] is None for r in mism)}
    conf_sem = Counter((r["ref_semantic_kind"], r["semantic_kind"]) for r in rows)
    conf_route = Counter((r["ref_render_unit"], r["render_unit"]) for r in rows)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec_sha256": spec["sha256"], "status": spec["spec"]["status"],
           "total": total, "layers": by_layer, "v2_mismatches": resolved, "invalid": bad,
           "confusion_semantic_kind": {"%s -> %s" % k: v for k, v in sorted(conf_sem.items())},
           "confusion_render_unit": {"%s -> %s" % k: v for k, v in sorted(conf_route.items())}, "rows": rows}
    cell = lambda v: "-" if v is None else str(v)
    yn = {True: "да", False: "**нет**", None: "-"}
    left = {True: "нет", False: "**да**", None: "не решено"}
    review = sum(r["render_unit"] == "REVIEW" for r in rows)
    ref_open = sum(r["ref_render_unit"] == "open" for r in rows)
    unresolved = sum(r["route_ok"] is None for r in rows)
    res["four"] = {"v2_mismatches_resolved": resolved["routing_error_gone"], "v2_mismatches": resolved["n"],
                   "dangerous_false_standalone": total["dangerous_false_standalone"],
                   "overconservative_routing": total["overconservative_routing"],
                   "routing_unresolved": unresolved, "routing_review": review, "routing_ref_open": ref_open}
    part_alone = [r for r in rows if "OBJECT_PART" in (r["semantic_kind"], r["ref_semantic_kind"])
                  and "STANDALONE_RENDER" in (r["render_unit"], r["ref_render_unit"])]
    dump_json(os.path.join(out, "report.json"), res)
    L = ["# IDENTITY_ROUTING_V3 - диагностика на 28 предметах holdout V2", "",
         "spec %s. %s." % (spec["sha256"][:12], spec["spec"]["status"]), "",
         "## Четыре числа", "",
         "| показатель | значение |", "|---|---|",
         "| V2 mismatches resolved by V3 (маршрут B совпал с эталоном) | **%d из %d** |" % (
             resolved["routing_error_gone"], resolved["n"]),
         "| DANGEROUS_FALSE_STANDALONE (самая дорогая ошибка) | **%d** из %d |" % (
             total["dangerous_false_standalone"], total["n"]),
         "| OVERCONSERVATIVE_ROUTING (безопасная, дорогая ручной работой) | **%d** из %d |" % (
             total["overconservative_routing"], total["n"]),
         "| routing unresolved / open (не оценено по B) | **%d** из %d: REVIEW у человека %d, эталон open %d |" % (
             unresolved, total["n"], review, ref_open), "",
         "## OBJECT_PART + STANDALONE_RENDER (раньше выглядели ошибками)", "",
         "| предмет | ответ A / B | эталон A / B | V2 ответ / эталон V1 |", "|---|---|---|---|"] + \
        ["| %s | %s / %s | %s / %s | %s / %s |" % (r["asset_id"], r["semantic_kind"] or "-", r["render_unit"] or "-",
                                                   r["ref_semantic_kind"], r["ref_render_unit"],
                                                   r["v2_status"] or "-", r["v2_ref"] or "-") for r in part_alone] + \
        (["", "нет ни одного"] if not part_alone else []) + ["",
         "## Главный вопрос: 8 расхождений класса V2 после разделения осей", "",
         "Расхождений V2: %d. Перестали быть ошибкой маршрута (B совпал с эталоном): **%d**; остались ошибкой: %d; "
         "не решено (REVIEW у человека или эталон open): %d. Смысл A совпал: %d, обе оси: %d." % (
             resolved["n"], resolved["routing_error_gone"], resolved["routing_error_left"],
             resolved["routing_unresolved"], resolved["semantic_kind_agrees"], resolved["both_agree"]), "",
         "| предмет | V2 ответ / эталон V1 | V3 смысл A | V3 маршрут B | эталон A | эталон B | ошибка маршрута осталась |",
         "|---|---|---|---|---|---|---|"]
    for r in mism:
        L.append("| %s | %s / %s | %s | %s | %s | %s | %s |" % (
            r["asset_id"], r["v2_status"], r["v2_ref"], r["semantic_kind"] or "-", r["render_unit"] or "-",
            r["ref_semantic_kind"], r["ref_render_unit"], left[r["route_ok"]]))
    L += ["", "## GLOBAL", "", "| метрика | значение | из |", "|---|---|---|"]
    for k, den in (("semantic_kind_accuracy", "semantic_kind_n"), ("render_unit_accuracy", "render_unit_n"),
                   ("name_accuracy", "name_n"), ("dangerous_false_standalone", "n"),
                   ("overconservative_routing", "n"), ("unsure_rate", "n"), ("review_rate", "n"),
                   ("missing_context_rate", "n")):
        L.append("| %s | %s | %s |" % (k, cell(total[k]), total[den]))
    L += ["", spec["spec"]["dangerous"] + ".", spec["spec"]["overconservative"] + ".",
          "", "Эталон open: смысл %d, маршрут %d (вне знаменателей)." % (
              total["ref_open_semantic_kind"], total["ref_open_render_unit"]), "", "## BY LAYER (слои holdout V2)", "",
          "| слой | n | смысл A | маршрут B | название | опасных | сверхосторожных |", "|---|---|---|---|---|---|---|"]
    for lay, m in by_layer.items():
        L.append("| %s | %d | %s | %s | %s | %d | %d |" % (
            lay, m["n"], cell(m["semantic_kind_accuracy"]), cell(m["render_unit_accuracy"]), cell(m["name_accuracy"]),
            m["dangerous_false_standalone"], m["overconservative_routing"]))
    short = {"STANDALONE_RENDER": "STAND", "COMPOSITE_PART": "COMP", "STRUCTURAL_MODULAR": "MOD",
             "STATE_VARIANT": "STATE", "DERIVED": "DERIV", "EXCLUDE": "EXCL", "REVIEW": "REVIEW", "open": "open"}
    cols = ROUTING[:-1] + ["open"]
    L += ["", "## Маршрут B: матрица (строки - ответ, столбцы - эталон)", "",
          "| ответ \\ эталон | " + " | ".join(short[c] for c in cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for a_ in ROUTING + sorted({r["render_unit"] for r in rows} - set(ROUTING)):
        L.append("| %s | %s |" % (short.get(a_, a_ or "(пусто)"),
                                  " | ".join(str(conf_route.get((c, a_), 0) or ".") for c in cols)))
    L += ["", "Диагональ - совпадение; строка STAND вне столбцов STAND и open - опасные; столбец STAND вне строки "
          "STAND - сверхосторожные.", "", "## Смысл A (эталон -> ответ)", ""] + \
         ["- %s: %d" % kv for kv in res["confusion_semantic_kind"].items()]
    L += ["", "## По предметам", "", "| предмет | V2 ответ / эталон | A ответ / эталон | B ответ / эталон | A | B | "
          "источники |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s / %s | %s / %s | %s / %s | %s | %s | %s |" % (
            r["asset_id"], r["v2_status"] or "-", r["v2_ref"] or "-", r["semantic_kind"], r["ref_semantic_kind"],
            r["render_unit"], r["ref_render_unit"], yn[r["sem_kind_ok"]], yn[r["route_ok"]], r["sources"]))
    if bad:
        L += ["", "Ошибки в ответах или эталоне: " + "; ".join(bad)]
    with open(os.path.join(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return res


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Опознание и маршрут</title>
<style>
:root{--bg:#1b1b1f;--card:#26262c;--fg:#e8e8ea;--mut:#9a9aa3;--acc:#f2c14e;--on:#3a6fa8;--hyp:#5a4a2a}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px;max-width:1200px}
h1{font-size:18px;margin:0 0 4px}h2{font-size:16px;margin:0 0 8px}.mut{color:var(--mut)}
.card{background:var(--card);border-radius:8px;padding:14px;margin:16px 0}
.p{margin:10px 0}.p .t{color:var(--acc);font-weight:600;font-size:13px;margin-bottom:4px}
.p img{max-width:100%;border-radius:4px;image-rendering:pixelated}
pre{white-space:pre-wrap;background:#1f1f24;padding:8px;border-radius:4px;font-size:12px;margin:4px 0}
.hyp{background:#1f1f24;border-left:4px solid var(--hyp);border-radius:4px;padding:6px 8px;margin:4px 0}
.hyp .k{font-size:11px;letter-spacing:.06em;color:#c9a35a;font-weight:700}
button{background:#33333b;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:3px 10px;cursor:pointer}
button.on{background:var(--on)}button.m.on{background:#7a5ab8}
.btns{display:flex;gap:4px;flex-wrap:wrap;margin:6px 0}
.q{color:var(--acc);font-weight:600;margin-top:8px}
dl{margin:4px 0 0}dt{font-weight:600;margin-top:4px}dd{margin:0 0 0 12px;color:var(--mut)}
input[type=text]{width:100%;box-sizing:border-box;background:#1f1f24;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:5px;margin:4px 0}
textarea{width:100%;height:140px;background:#1f1f24;color:var(--fg);box-sizing:border-box}
details{background:#222228;border-radius:6px;padding:8px 10px;margin:8px 0}
</style></head><body>
<h1>IDENTITY_ROUTING_V3 - диагностика: те же 28 предметов, ответ по двум осям</h1>
<div class="mut">Картинки те же, что в holdout. Три ответа на каждый предмет, независимо друг от друга:
<b>A</b> - что это вообще (смысл), <b>B</b> - как это должно попасть в HD (маршрут), и final_identity по-английски.
Ось A не решает ось B: стойка шасси - OBJECT_PART, но может рисоваться своим заказом (STANDALONE_RENDER); четверть
купола - OBJECT_PART и COMPOSITE_PART. Описание прежнее, ответы моделей и статус в базе - непроверенные гипотезы.
TSV внизу - прислать целиком.</div>
<details><summary>определения A и B (заморожены до ответов)</summary><div id="defs"></div></details>
<div id="cards"></div>
<h2>TSV</h2><textarea id="tsv" readonly></textarea>
<script>
const DATA = __DATA__, MISS = __MISS__, SEM = __SEM__, ROUTE = __ROUTE__, DEFS = __DEFS__, KEY = "__KEY__";
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} tsv(); }
const clean = s => (s || "").replace(/[\\t\\n]/g, " ");
const esc = t => String(t).replace(/[&<>"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[ch]));
function tsv(){
  const L = [["asset_id", "final_identity", "semantic_kind", "render_unit", "missing_context", "note"].join("\\t")];
  for (const c of DATA) { const s = st[c.asset] || {};
    L.push([c.asset, clean(s.i), s.a || "", s.b || "", Object.keys(s.m || {}).filter(k => s.m[k]).join(","), clean(s.n)].join("\\t")); }
  document.getElementById("tsv").value = L.join("\\n");
}
function deflist(title, d){ let h = `<div class="q">${esc(title)}</div><dl>`;
  for (const [k, v] of Object.entries(d)) h += `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`; return h + "</dl>"; }
document.getElementById("defs").innerHTML = deflist("A. SEMANTIC_KIND", DEFS.semantic_kind) +
  deflist("B. RENDER_UNIT", DEFS.render_unit) + `<div class="mut" style="margin-top:6px">${esc(DEFS.precedence)}<br>${esc(DEFS.axes_independent)}<br>${esc(DEFS.dangerous)}<br>${esc(DEFS.overconservative)}</div>`;
function choice(el, s, field, vals){
  const cb = document.createElement("div"); cb.className = "btns";
  for (const v of vals) { const b = document.createElement("button"); b.textContent = v; b.dataset.v = v;
    if (s[field] === v) b.classList.add("on");
    b.onclick = () => { s[field] = s[field] === v ? "" : v; cb.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === s[field])); save(); };
    cb.appendChild(b); }
  el.appendChild(cb);
}
const root = document.getElementById("cards");
for (const c of DATA) {
  const s = st[c.asset] = st[c.asset] || {}; s.m = s.m || {};
  const el = document.createElement("div"); el.className = "card";
  let h = `<h2>${c.n}. ${esc(c.asset)}</h2>`;
  for (const [t, f] of c.panels) h += `<div class="p"><div class="t">${esc(t)}</div><img src="img/${f}"></div>`;
  h += `<div class="p"><div class="t">7. гипотезы - НЕ проверены, могут быть неверны</div>`;
  h += `<div class="hyp"><div class="k">UNVERIFIED OLD DESCRIPTION</div>${esc(c.prompt || "-")}</div>`;
  const ab = ["A", "B"];
  c.answers.forEach((a, i) => { h += `<div class="hyp"><div class="k">MODEL HYPOTHESIS ${ab[i] || i + 1}</div>${esc(a)}</div>`; });
  h += `<div class="hyp"><div class="k">UNVERIFIED DATABASE STATUS</div>${esc(c.status || "-")}; модели: ${esc(c.verdict || "-")}</div>`;
  h += `<div class="t" style="margin-top:8px">факты из данных игры</div><pre>${esc(c.facts)}</pre>`;
  if (c.notes.length) h += `<div class="mut">${c.notes.map(esc).join("<br>")}</div>`;
  h += `</div>`;
  el.innerHTML = h;
  el.insertAdjacentHTML("beforeend", `<div class="q">A. что это (SEMANTIC_KIND)</div>`); choice(el, s, "a", SEM);
  el.insertAdjacentHTML("beforeend", `<div class="q">B. как обрабатывать (RENDER_UNIT)</div>`); choice(el, s, "b", ROUTE);
  const i = document.createElement("input"); i.type = "text"; i.placeholder = "final_identity, in English: what it is, or what it is a part of";
  i.value = s.i || ""; i.oninput = () => { s.i = i.value; save(); };
  el.insertAdjacentHTML("beforeend", `<div class="q">что это (final_identity)</div>`); el.appendChild(i);
  el.insertAdjacentHTML("beforeend", `<div class="mut">UNSURE / REVIEW - какого контекста не хватило:</div>`);
  const mb = document.createElement("div"); mb.className = "btns";
  for (const v of MISS) { const b = document.createElement("button"); b.textContent = v; b.className = "m";
    if (s.m[v]) b.classList.add("on"); b.onclick = () => { s.m[v] = !s.m[v]; b.classList.toggle("on", s.m[v]); save(); };
    mb.appendChild(b); }
  el.appendChild(mb);
  const n = document.createElement("input"); n.type = "text"; n.placeholder = "заметка (по-русски можно)";
  n.value = s.n || ""; n.oninput = () => { s.n = n.value; save(); }; el.appendChild(n);
  root.appendChild(el);
}
tsv();
</script></body></html>"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["spec", "cards", "check", "report"])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--answers", default="")
    ap.add_argument("--reference", default="")
    ap.add_argument("--refreeze", default="", help="spec: причина перезаморозки (только до ответов)")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.cmd == "spec":
        freeze_spec(a.out, a.src, a.refreeze)
    elif a.cmd == "cards":
        make_cards(a.out, a.src)
    elif a.cmd == "report":
        report(a.out, a.src, a.answers, a.reference)
    else:
        s = load_spec(a.out)
        print("spec цел: sha256 %s, заморожен %s, предметов %d%s" % (
            s["sha256"][:12], s["created"], len(s["assets"]),
            "; заменил %s (%s)" % (s["replaces"][:12], s["refreeze_reason"]) if s.get("replaces") else ""))
        if s["spec"] != SPEC:
            print("ВНИМАНИЕ: определения в коде отличаются от замороженных - страница и отчёт берут замороженные")
        print("ответов: %s" % ("ЕСТЬ" if os.path.exists(os.path.join(a.out, "answers_vitali.tsv")) else "нет"))
        cj = os.path.join(a.out, "cards.json")
        if os.path.exists(cj):
            c = load_json(cj)
            now = img_digest(os.path.join(a.out, "img"))
            print("картинки: %s (те же, что в V2: %s)" % ("целы" if now == c["img_sha256"] else "ИЗМЕНЕНЫ",
                                                       "да" if c["images_identical_to_v2"] else "НЕТ"))
            print("страница по spec: %s" % ("та же" if c.get("spec_sha256") == s["sha256"] else "СТАРАЯ - cards"))


if __name__ == "__main__":
    main()
