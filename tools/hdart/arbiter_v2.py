#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Семантический арбитр V2 (Pipeline v2, P1-C): выбор с перестановкой и отдельное отношение.

V1 (arbiter.py, acf097a4c063) - FAIL: FALSE_CONFIDENT 24 процента на контрольной сотне, модель не воздержалась ни
разу, отношение SAME сказано у 44 карточек при правде BOTH у 12 (решение специалиста 30.09). V1 не дорабатывается.
V2 - схема специалиста 30.09, два независимых вопроса:

1. Визуальный выбор (кадр, место на карте, семейство, MCD - вход V1 без изменений), кандидаты FIRST и SECOND,
   ДВАЖДЫ: порядок ab (FIRST=A) и ba (FIRST=B). Ответ переводится в физического кандидата; устойчив только выбор
   ОДНОГО И ТОГО ЖЕ физического кандидата в обоих порядках. Сведение - combine_visual.
2. Отношение двух названий - только текст, без картинок и MCD: SAME / BROADER_NARROWER / RELATED_BUT_DIFFERENT /
   DIFFERENT / CANNOT_TELL, тоже в двух порядках: REL_STABLE / REL_ORDER_UNSTABLE / REL_INVALID; для маршрута
   неустойчивое и невалидное - CANNOT_TELL.

Приговор (acceptance, замечания Codex 30.09): только на полном прогоне (все ассеты в обоих порядках этой версией на
тех же входах, правда у каждого) и при проверяемых LIGHT >= MIN_VERIFIED_LIGHT; по худшей из FC_STABLE / n и
FC_LIGHT / verified_LIGHT. Правда от модели (CODEX_BLIND) - приговор помечается как согласие моделей, не приёмка.
Версии две: v2_rev - вопросы и модель (каталог сырых ответов), reduce_rev - исходный текст сведения и порогов.

Маршрут: LIGHT - только устойчивый выбор И отношение SAME или BROADER_NARROWER; всё остальное HARD; CONFIRMED -
никогда. Опасна только устойчивая ошибка: FALSE_CONFIDENT_STABLE - устойчивый выбор X при правде не X, не BOTH и
не CANNOT_TELL. Успех: FALSE_CONFIDENT_STABLE <= 5 процентов. Нестабильность не ошибка - такие карточки остаются
человеку, их доля - ORDER_UNSTABLE_RATE.

Снимок, входы и правда - те же, что у V1 (arbiter.check_snapshot, inputs_of, load_truth); контрольная сотня не
меняется. Ответы - runs/v2-<v2_rev>/answers.json, по четыре вызова на ассет, докачка по вызову.

    py -3.13 tools/hdart/arbiter_v2.py run <снимок> --dry-run   (без модели: четыре запроса первого ассета)
    py -3 tools/gpuq.py add --name arbiter-v2 -- C:/Python313/python.exe E:/OpenXCom/tools/hdart/arbiter_v2.py run <снимок>
    py -3.13 tools/hdart/arbiter_v2.py report <снимок>          (без модели: метрики V2 и сравнение с V1)
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arbiter as ar                                   # noqa: E402

ENC = "utf-8-sig"
V1_REV = "acf097a4c063"
ORDERS = ("ab", "ba")                                  # ab: FIRST = A, SECOND = B; ba: FIRST = B, SECOND = A
VISUAL = ("FIRST", "SECOND", "NEITHER", "CANNOT_TELL")
RELATIONS = ar.RELATIONS + ("CANNOT_TELL",)
LIGHT_RELATIONS = ("SAME", "BROADER_NARROWER")
STATES = ("STABLE_A", "STABLE_B", "ORDER_UNSTABLE", "PARTIAL", "NEITHER", "CANNOT_TELL", "INVALID")
REL_STATES = ("REL_STABLE", "REL_ORDER_UNSTABLE", "REL_INVALID")
OPTIONS = dict(ar.OPTIONS)
REL_OPTIONS = dict(ar.OPTIONS, num_predict=120)
LIMIT = 0.05                                           # FC_STABLE / n и FC_LIGHT / verified_LIGHT - оба не выше
MIN_VERIFIED_LIGHT = 20                                # меньше проверяемых LIGHT - приговора нет, мало данных
MODEL_TRUTH = ("CODEX_BLIND", "CLAUDE_BLIND")          # правда от модели: приговор - согласие моделей, не приёмка

VISUAL_ASK = """You are a referee. Two earlier guesses disagree about what ONE object from the 1994 isometric game
X-COM (mod X-Piratez) is. Decide between them. Do not invent a new name.
Picture 1: the object itself - the original pixel art enlarged 4x with nearest neighbour (no changes);
the dark grey around it is empty background.
Picture 2 (if given): the object in its place on a real game map, marked with a red frame; other things there
are context, not the answer.
Picture 3 (if given): other members of its family (recolours, mirrors, possible other sides), each labelled
with its relation.
Game data (MCD) about the object:
{facts}
FIRST guess: {first}
SECOND guess: {second}
The order of the guesses means nothing.
Answer strictly as JSON with exactly these keys:
"decision": "FIRST" if the FIRST guess is what the pictures show and SECOND fits clearly worse; "SECOND" likewise;
"NEITHER" if the pictures clearly show something that is neither guess; "CANNOT_TELL" if the pictures and data do
not settle it. Picking a guess while unsure is an error; CANNOT_TELL is an acceptable answer;
"reason_short": at most 25 English words why; do not propose another name;
"evidence_used": a list of what you really used, from: sprite, map_crop, mcd, family_views."""

RELATION_ASK = """Two names were proposed for the same small object in an old video game. Do not look for which one
is right; say only how the two NAMES relate as kinds of object.
Name 1: {one}
Name 2: {two}
Answer strictly as JSON with exactly one key "relation", one of:
"SAME" - the same kind of object in other words (e.g. "wooden crate" and "wooden box");
"BROADER_NARROWER" - one is a more general or a more specific name of the other (e.g. "lamp" and "desk lamp");
"RELATED_BUT_DIFFERENT" - related but different objects or parts (e.g. "wall" and "pillar", "table" and "shelf");
"DIFFERENT" - unrelated objects (e.g. "cow" and "log pile");
"CANNOT_TELL" - the names alone do not settle it."""


def v2_rev(model=ar.MODEL):
    """Версия вопросов V2: оба запроса, модель, параметры - каталог сырых ответов. Ответ другой версии в сводку
    не идёт. Сведение и приговор - отдельная reduce_rev: они пересчитываются из сырых ответов без модели."""
    return "v2-" + ar.h12({"visual": VISUAL_ASK, "relation": RELATION_ASK, "model": model, "options": OPTIONS,
                           "rel_options": REL_OPTIONS})


def reduce_rev():
    """Версия сведения и приговора - по исходному тексту функций и порогам, а не по ручной строке:
    правка трактовки PARTIAL, отношения или маршрута меняет её сама."""
    import inspect
    src = [inspect.getsource(f) for f in (combine_visual, combine_relation, route_v2, decided, settle, acceptance)]
    return "r-" + ar.h12({"src": src, "light_relations": LIGHT_RELATIONS, "limit": LIMIT,
                          "min_verified_light": MIN_VERIFIED_LIGHT, "model_truth": MODEL_TRUTH,
                          "thresholds": ar.THRESHOLDS, "fc": inspect.getsource(ar.false_confident)})


def rel_name(c):
    """Название для вопроса об отношении: имя и категория, без описания (описание несёт видимые детали)."""
    return "%s (%s)" % (c["proposed_name"], c.get("proposed_category", ""))


def physical(order, pos):
    """Позиция в порядке -> физический кандидат A/B."""
    return {("ab", "FIRST"): "A", ("ab", "SECOND"): "B", ("ba", "FIRST"): "B", ("ba", "SECOND"): "A"}[(order, pos)]


def visual_prompt(x, order):
    first, second = (x["A"], x["B"]) if order == "ab" else (x["B"], x["A"])
    return VISUAL_ASK.format(facts=x["facts"], first=ar.candidate(first), second=ar.candidate(second))


def relation_prompt(x, order):
    one, two = (x["A"], x["B"]) if order == "ab" else (x["B"], x["A"])
    return RELATION_ASK.format(one=rel_name(one), two=rel_name(two))


def norm_visual(d, order):
    dec = str(d.get("decision", "")).strip().upper().replace(" ", "_")
    out = {"decision": dec, "reason_short": str(d.get("reason_short", "")).strip()[:300],
           "evidence_used": [e for e in d.get("evidence_used", []) if e in ar.EVIDENCE]
           if isinstance(d.get("evidence_used"), list) else [], "valid": dec in VISUAL}
    if out["valid"] and dec in ("FIRST", "SECOND"):
        out["pick"] = physical(order, dec)
    return out


def norm_relation(d):
    rel = str(d.get("relation", "")).strip().upper().replace(" ", "_").replace("/", "_")
    return {"relation": rel, "valid": rel in RELATIONS}


def combine_visual(ab, ba):
    """Два ответа -> (состояние, физический выбор или None, позиционный перекос).
    Перекос - оба раза выбрана одна и та же ПОЗИЦИЯ, то есть разные физические кандидаты."""
    if not ab or not ba or not ab.get("valid") or not ba.get("valid"):
        return "INVALID", None, False
    pa, pb = ab.get("pick"), ba.get("pick")
    if pa and pb:
        if pa == pb:
            return "STABLE_" + pa, pa, False
        return "ORDER_UNSTABLE", None, ab["decision"] == ba["decision"]
    if pa or pb:
        return "PARTIAL", None, False
    if ab["decision"] == ba["decision"] == "NEITHER":
        return "NEITHER", None, False
    return "CANNOT_TELL", None, False


def combine_relation(ab, ba):
    """Два ответа об отношении -> (состояние, отношение для маршрута).
    REL_STABLE - оба порядка сказали одно (и CANNOT_TELL дважды - устойчивое воздержание);
    REL_ORDER_UNSTABLE - два валидных, но разных; REL_INVALID - ответа нет или он не по форме.
    Для маршрута неустойчивое и невалидное - CANNOT_TELL."""
    if not ab or not ba or not ab.get("valid") or not ba.get("valid"):
        return "REL_INVALID", "CANNOT_TELL"
    if ab["relation"] == ba["relation"]:
        return "REL_STABLE", ab["relation"]
    return "REL_ORDER_UNSTABLE", "CANNOT_TELL"


def route_v2(state, relation):
    if state in ("STABLE_A", "STABLE_B") and relation in LIGHT_RELATIONS:
        return ar.LIGHT
    return ar.HARD


def decided(rec):
    """Итог ассета в форме ответа V1, чтобы считать исходы теми же arbiter.outcome / false_confident:
    устойчивый выбор - A/B; NEITHER - NEITHER; всё прочее - CANNOT_TELL (арбитр не знает)."""
    st = rec["state"]
    dec = rec["pick"] if rec["pick"] else ("NEITHER" if st == "NEITHER" else "CANNOT_TELL")
    return {"decision": dec, "relation": rec["relation"], "valid": st != "INVALID"}


def settle(rec):
    rec["state"], rec["pick"], rec["order_bias"] = combine_visual(rec["visual"].get("ab"), rec["visual"].get("ba"))
    rec["rel_state"], rec["relation"] = combine_relation(rec["rel"].get("ab"), rec["rel"].get("ba"))
    rec["route"] = route_v2(rec["state"], rec["relation"])
    return rec


def call(host, model, prompt, imgs, options):
    body = {"model": model, "stream": False, "think": False, "format": "json", "options": options, "prompt": prompt}
    if imgs:
        body["images"] = [base64.b64encode(b).decode() for b in imgs]
    req = urllib.request.Request(host + "/api/generate", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        raw = json.loads(r.read().decode())["response"]
    try:
        d = json.loads(raw)
    except ValueError:
        d = {}
    return (d if isinstance(d, dict) else {}), raw[:800]


def run(path, host="http://127.0.0.1:11434", model=ar.MODEL, limit=0, dry_run=False):
    snap, d = ar.check_snapshot(path)
    rev = v2_rev(model)
    rd = os.path.join(d, "runs", rev)
    ans_path = os.path.join(rd, "answers.json")
    answers = ar.load_json(ans_path, {}) if not dry_run else {}
    todo = [x for x in snap["items"] if not complete(answers.get(x["asset_id"]))]
    if limit:
        todo = todo[:limit]
    print("арбитр %s, модель %s: спросить %d, готово %d" % (rev, model, len(todo), len(snap["items"]) - len(todo)),
          flush=True)
    if dry_run:
        x = todo[0]
        imgs = ar.inputs_of(x, d)
        for o in ORDERS:
            print("== %s visual %s, картинок %d\n%s\n" % (x["asset_id"], o, len(imgs), visual_prompt(x, o)))
        for o in ORDERS:
            print("== %s relation %s, без картинок\n%s\n" % (x["asset_id"], o, relation_prompt(x, o)))
        return 0
    os.makedirs(rd, exist_ok=True)
    t0 = time.time()
    errors = 0
    for n, x in enumerate(todo, 1):
        imgs = ar.inputs_of(x, d)
        rec = answers.get(x["asset_id"]) or {"visual": {}, "rel": {}}
        try:
            for o in ORDERS:
                if o not in rec["visual"]:
                    dd, raw = call(host, model, visual_prompt(x, o), imgs, OPTIONS)
                    rec["visual"][o] = dict(norm_visual(dd, o), raw=raw)
                if o not in rec["rel"]:
                    dd, raw = call(host, model, relation_prompt(x, o), None, REL_OPTIONS)
                    rec["rel"][o] = dict(norm_relation(dd), raw=raw)
        except Exception as e:                                          # noqa: BLE001
            print("  %s: ОШИБКА %s" % (x["asset_id"], str(e)[:200]), flush=True)
            errors += 1
            answers[x["asset_id"]] = rec
            ar.save_json(ans_path, answers)
            continue
        rec.update(v2_rev=rev, model=model, when=time.strftime("%Y-%m-%dT%H:%M:%S"), inputs=x["inputs"])
        answers[x["asset_id"]] = settle(rec)
        ar.save_json(ans_path, answers)
        el = time.time() - t0
        print("  %d/%d %-22s %-14s %-22s -> %s | %.1f с/шт, осталось ~%d мин" % (
            n, len(todo), x["asset_id"], rec["state"], rec["relation"], rec["route"], el / n,
            (len(todo) - n) * el / n / 60), flush=True)
    if errors:
        print("ошибок вызова %d: ассеты недоспрошены, приговора не будет - повторить run (докачает)" % errors,
              flush=True)
    meta = {"v2_rev": rev, "reduce_rev": reduce_rev(), "model": model, "options": OPTIONS, "rel_options": REL_OPTIONS,
            "visual_sha256": ar.sha256_bytes(VISUAL_ASK.encode("utf-8")),
            "relation_sha256": ar.sha256_bytes(RELATION_ASK.encode("utf-8")),
            "snapshot": snap["snapshot_id"], "items_hash": snap["items_hash"], "answers": len(answers)}
    ar.save_json(os.path.join(rd, "run.json"), meta)
    report(path, rev)
    return 0


def complete(rec):
    return bool(rec) and all(o in rec.get("visual", {}) and o in rec.get("rel", {}) for o in ORDERS)


# ------------------------------------------------------------------ сводка

def pct(v):
    return "-" if v is None else "%.1f %%" % (100 * v)


def ratio(a, b):
    return round(a / b, 4) if b else None


def upper95(err, n, z=1.645):
    """Верхняя односторонняя 95-процентная граница доли ошибок (Уилсон): 0 из 20 - это ещё до 12 процентов."""
    if not n:
        return None
    p = err / n
    c = z * z / n
    return round((p + c / 2 + z * ((p * (1 - p) + c / 4) / n) ** 0.5) / (1 + c), 4)


def acceptance(k):
    """Приговор (verdict, пояснение). Приговора нет (None), пока прогон неполон: каждый ассет спрошен в обоих
    порядках этой версией на тех же входах и у каждого есть правда; и пока проверяемых LIGHT меньше
    MIN_VERIFIED_LIGHT. Иначе - по худшей из двух долей: FC_STABLE / n и FC_LIGHT / verified_LIGHT (обе <= LIMIT)."""
    why = []
    if k["answered"] < k["n"]:
        why.append("недоспрошено %d" % (k["n"] - k["answered"]))
    if k["truth"] < k["n"]:
        why.append("без правды %d" % (k["n"] - k["truth"]))
    if k["stale"]:
        why.append("ответов другой версии или других входов %d" % k["stale"])
    if not why and k["verified_light"] < MIN_VERIFIED_LIGHT:
        why.append("проверяемых LIGHT %d < %d" % (k["verified_light"], MIN_VERIFIED_LIGHT))
    if why:
        return None, "нет приговора: " + "; ".join(why)
    worst = max(k["fc_stable_total_pct"], k["fc_light_verified_pct"])
    note = "худшая из FC_STABLE/n и FC_LIGHT/verified_LIGHT = %s, предел %s" % (pct(worst), pct(LIMIT))
    src = sorted(k["truth_sources"])
    if src and all(s in MODEL_TRUTH for s in src):
        note += "; правда %s - это согласие моделей, не приёмка" % "+".join(src)
    return ar.verdict_of(worst), note


def report(path, rev=None):
    snap, d = ar.check_snapshot(path)
    rev = rev or v2_rev()
    rd = os.path.join(d, "runs", rev)
    answers = {k: settle(v) for k, v in ar.load_json(os.path.join(rd, "answers.json"), {}).items() if complete(v)}
    v1 = ar.load_json(os.path.join(d, "runs", V1_REV, "answers.json"), {})
    truth = ar.load_truth(d)
    per = {c: Counter() for c in ("ALL",) + ar.CLASSES}
    rows = []
    for x in snap["items"]:
        aid = x["asset_id"]
        rec, t = answers.get(aid), truth.get(aid)
        for c in ("ALL", x["class"]):
            k = per[c]
            k["n"] += 1
            if not rec:
                k["no_answer"] += 1
                continue
            k["answered"] += 1
            k["stale"] += rec.get("v2_rev") != rev or rec.get("inputs") != x["inputs"]
            k["state_" + rec["state"]] += 1
            k["order_bias"] += rec["order_bias"]
            k["rel_state_" + rec["rel_state"]] += 1
            k["rel_" + rec["relation"]] += 1
            k[rec["route"]] += 1
            if t:
                k["truth"] += 1
                k["truth_" + t["truth"]] += 1
                k["src_" + t["truth_source"]] += 1
                if rec["pick"] and t["truth"].strip().upper() == "CANNOT_TELL":
                    k["stable_truth_ct"] += 1
                    k["stable_light_truth_ct"] += rec["route"] == ar.LIGHT
                fc = ar.false_confident(decided(rec), t)
                if fc is True:
                    k["fc_stable"] += 1
                    k["fc_light"] += rec["route"] == ar.LIGHT
                    k["fc_rel_" + rec["relation"]] += 1
                if fc is not None and rec["pick"]:
                    k["verified_stable"] += 1
                    k["verified_light"] += rec["route"] == ar.LIGHT
                a1 = v1.get(aid)
                if a1:
                    fc1 = ar.false_confident(a1, t)
                    if fc1 is True:
                        k["v1_fc"] += 1
                        k["v1_fc_now_fc"] += fc is True
                        k["v1_fc_now_hard"] += rec["route"] == ar.HARD
                    elif fc is True:
                        k["new_fc"] += 1
        if rec:
            rows.append({"asset_id": aid, "class": x["class"], "A": x["A"]["proposed_name"],
                         "B": x["B"]["proposed_name"], "ab": rec["visual"]["ab"].get("decision"),
                         "ba": rec["visual"]["ba"].get("decision"), "state": rec["state"],
                         "rel_ab": rec["rel"]["ab"].get("relation"), "rel_ba": rec["rel"]["ba"].get("relation"),
                         "relation": rec["relation"], "route": rec["route"], "truth": t and t["truth"],
                         "false_confident_stable": ar.false_confident(decided(rec), t) if t else None,
                         "reason_ab": rec["visual"]["ab"].get("reason_short"),
                         "reason_ba": rec["visual"]["ba"].get("reason_short")})
    for k in per.values():
        for key in ("fc_stable", "fc_light", "order_bias", "v1_fc", "v1_fc_now_fc", "v1_fc_now_hard", "new_fc",
                    "stale", "verified_stable", "verified_light", "stable_truth_ct", "stable_light_truth_ct"):
            k[key] += 0                                # нули - тоже поле отчёта, а не отсутствие
        n, lab = k["n"], k["truth"]
        k["truth_sources"] = {s[4:]: v for s, v in k.items() if s.startswith("src_")}
        k["order_unstable_rate"] = ratio(k["state_ORDER_UNSTABLE"] + k["state_PARTIAL"], k["answered"])
        k["order_bias_rate"] = ratio(k["order_bias"], k["answered"])
        k["cannot_tell_rate"] = ratio(k["state_CANNOT_TELL"], k["answered"])
        k["relation_stable_rate"] = ratio(k["rel_state_REL_STABLE"], k["answered"])
        k["light_rate"] = ratio(k[ar.LIGHT], k["answered"])
        k["fc_stable_total_pct"] = ratio(k["fc_stable"], n) if lab else None
        k["fc_stable_labeled_pct"] = ratio(k["fc_stable"], lab) if lab else None
        k["fc_light_verified_pct"] = ratio(k["fc_light"], k["verified_light"]) if lab else None
        k["fc_light_upper95"] = upper95(k["fc_light"], k["verified_light"])
        k["verdict"], k["verdict_note"] = acceptance(k)
    out = {"snapshot": snap["snapshot_id"], "v2_rev": rev, "reduce_rev": reduce_rev(), "answers": len(answers),
           "truth": len(truth),
           "per_class": {c: dict(v) for c, v in per.items()}, "rows": rows,
           "made": time.strftime("%Y-%m-%dT%H:%M:%S")}
    os.makedirs(rd, exist_ok=True)
    ar.save_json(os.path.join(rd, "report.json"), out)
    summary = summary_text(per)
    with open(os.path.join(rd, "summary.txt"), "w", encoding=ENC) as f:
        f.write(summary + "\n")
    L = ["# Арбитр V2 (перестановка + отношение): контрольные 100 HARD", "",
         "Снимок `%s`, вопросы `%s`, сведение `%s` (%s). Ответов %d из %d." % (
             snap["snapshot_id"], rev, reduce_rev(), ar.MODEL, len(answers), len(snap["items"])), "",
         "```", summary, "```", "",
         "| ассет | класс | A | B | ab | ba | итог | связь ab / ba | для маршрута | куда | правда | FC | почему (ab / ba) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s / %s | %s | %s | %s | %s | %s / %s |" % (
            r["asset_id"], r["class"], r["A"], r["B"], r["ab"], r["ba"], r["state"], r["rel_ab"], r["rel_ba"],
            r["relation"],
            r["route"].replace("HUMAN_REVIEW_", ""), r["truth"] or "-",
            "**да**" if r["false_confident_stable"] else "", (r["reason_ab"] or "").replace("|", "/"),
            (r["reason_ba"] or "").replace("|", "/")))
    with open(os.path.join(rd, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print(summary)
    print("-> %s" % os.path.join(rd, "report.md"))
    return out


def summary_text(per):
    L = []
    for c in ("ALL",) + ar.CLASSES:
        k = per[c]
        L += ["TOTAL" if c == "ALL" else c.upper(),
              "answered: %d/%d" % (k["answered"], k["n"]),
              "labeled: %d/%d" % (k["truth"], k["n"]),
              "truth_source: " + (", ".join("%s %d" % kv for kv in sorted(k["truth_sources"].items())) or "-"),
              "",
              "visual (ab + ba):"] + ["%s %d" % (s, k["state_" + s]) for s in STATES] + [
              "",
              "relation (both orders):"] + ["%s %d" % (s, k["rel_state_" + s]) for s in REL_STATES] + [
              "relation for route:"] + ["%s %d" % (r, k["rel_" + r]) for r in RELATIONS] + [
              "",
              "route: LIGHT %d, HARD %d" % (k[ar.LIGHT], k[ar.HARD]),
              "",
              "ORDER_UNSTABLE_RATE %s" % pct(k["order_unstable_rate"]),
              "ORDER_BIAS_RATE %s" % pct(k["order_bias_rate"]),
              "CANNOT_TELL_RATE %s" % pct(k["cannot_tell_rate"]),
              "RELATION_STABLE_RATE %s" % pct(k["relation_stable_rate"]),
              "LIGHT_RATE %s" % pct(k["light_rate"]),
              "FALSE_CONFIDENT_STABLE %d" % k["fc_stable"],
              "FALSE_CONFIDENT_STABLE_total_pct %s" % pct(k["fc_stable_total_pct"]),
              "FALSE_CONFIDENT_STABLE_labeled_pct %s" % pct(k["fc_stable_labeled_pct"]),
              "FALSE_CONFIDENT_LIGHT %d of %d verified LIGHT (%s, upper95 %s); LIGHT all %d" % (
                  k["fc_light"], k["verified_light"], pct(k["fc_light_verified_pct"]), pct(k["fc_light_upper95"]),
                  k[ar.LIGHT]),
              "STABLE_WHILE_TRUTH_CANNOT_TELL %d, of them LIGHT %d" % (k["stable_truth_ct"],
                                                                      k["stable_light_truth_ct"]),
              "verdict: %s" % (k["verdict"] or "-"),
              "verdict_note: %s" % k["verdict_note"],
              "",
              "FALSE_CONFIDENT_STABLE_BY_RELATION:"] + ["%s %d" % (r, k["fc_rel_" + r]) for r in RELATIONS] + [
              "",
              "vs V1: FC %d, still FC %d, now HARD %d; new FC %d" % (
                  k["v1_fc"], k["v1_fc_now_fc"], k["v1_fc_now_hard"], k["new_fc"]),
              "", ""]
    L.append("ORDER_UNSTABLE_RATE - ORDER_UNSTABLE + PARTIAL (выбор в одном порядке, отказ в другом) от отвеченных; "
             "ORDER_BIAS_RATE - оба раза одна позиция, то есть разные физические кандидаты. FALSE_CONFIDENT_STABLE - "
             "устойчивый выбор при правде не он, не BOTH и не CANNOT_TELL; total_pct - от всех n (порог 5 %), "
             "labeled_pct - от размеченных. FALSE_CONFIDENT_LIGHT - то же среди ушедших в LIGHT с проверяемой правдой "
             "(не CANNOT_TELL), upper95 - верхняя граница Уилсона. RELATION_STABLE_RATE - оба порядка отношения "
             "сказали одно (и CANNOT_TELL дважды). Приговор - только на полном прогоне, по худшей из двух долей.")
    return "\n".join(L)


def main():
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("snapshot")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default=ar.MODEL)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    a = ap.parse_args()
    if a.cmd == "run":
        sys.exit(run(a.snapshot, a.host, a.model, a.limit, a.dry_run))
    report(a.snapshot)


if __name__ == "__main__":
    main()
