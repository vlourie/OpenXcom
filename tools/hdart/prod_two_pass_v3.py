#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""PROD_TWO_PASS_V3 - третья производственная партия: предметы со спорным опознанием (специалист 05.10, передал
Vitali в чате).

Запас простых предметов после V1 и V2 кончился (пробный отбор: годен 1). Специалист открыл одну группу - HARD,
«модели разошлись в опознании» (447 кадров), остальные пулы закрыты: другой бок и семейство, не один кадр,
природа и рельеф, перекраски (у них своя SAFE-ветка), прежние опыты. Из HARD берутся только одиночные предметы
(kind один, класс object, без кандидатов другого бока и подозрения на кусок), спор - только в опознании.

Тот же конвейер, что V2 (prod_two_pass_v2.py и prod_two_pass_v1.py не правятся - здесь другие папка, цель, отбор):
    select     -> candidates_all.json (все годные), identity_list.json (первые TARGET по числу мест на картах)
    опознание  identity_card.py make (карточки) -> identity_auto.py --batch <папка V3> pack / codex / merge /
               arbiter-pack / final; первый арбитр не уверен -> arbiter2-pack / arbiter2 (Codex, упор на место
               на карте, соседей и спрайт крупно) / final; и он не уверен -> RESIDUAL_IDENTITY, Vitali не зовут
    build      RENDER в партию, STRUCTURAL_PART / NOT_OBJECT / RESIDUAL_IDENTITY - в excluded.tsv
    relations, freeze, prompts, render, report, strict, third - как в V2; модель только через очередь:
        py -3.13 tools/gpuq.py add --name prod_two_pass_v3_restore --cwd E:/OpenXCom -- \
            E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
            --out art/objects/generation/probes/prod-two-pass-v3 -- \
            E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/prod_two_pass_v3.py render
Гипотеза карточки у HARD - оба старых названия моделей с пометкой, что они разошлись: прежнего описания нет, и
судьи опознания знают, что гипотеза спорная.
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import prod_two_pass_v1 as v1      # noqa: E402
import prod_two_pass_v2 as v2      # noqa: E402  (настраивает v1 на V2 - ниже переставляется на V3)

V2_OUT = os.path.join(v1.PROBES, "prod-two-pass-v2")
v1.PROFILE = "PROD_TWO_PASS_V3"
v1.OUT = os.path.join(v1.PROBES, "prod-two-pass-v3")
v1.THIRD = os.path.join(v1.OUT, "third")
v1.TARGET = 200
v1.EXCLUDE, v1.EXCLUDE_LIKE = {}, {}
v1.__file__ = os.path.abspath(__file__)    # do_third V1 зовёт third-chunk этого файла
v2.__file__ = os.path.abspath(__file__)    # do_strict V2 зовёт strict-chunk этого файла
v2.ALL = os.path.join(v1.OUT, "candidates_all.json")
v2.IDENTITY = os.path.join(v1.OUT, "identity", "auto", "identity.tsv")
v2.JUDGE = os.path.join(v1.OUT, "judge")
v2.ID_NOTE = dict(v2.ID_NOTE, RESIDUAL_IDENTITY="опознание: оба арбитра не уверены - residual identity")
LEVEL = "MODEL_DISAGREEMENT"
# pilot_batch отсеивает природу, только когда ВСЕ категории природные; у HARD одна модель часто говорит «камень»,
# другая «контейнер» - это спор о природе, а пул природы специалист не открывал. «Стена или часть здания» не
# здесь: кусок ли это конструкции, решают судьи опознания (STRUCTURAL_PART).
NATURE_ANY = {"plant or nature", "rock or terrain relief"}
_tuning = v1.tuning_assets                 # уже с V1 (prod_two_pass_v2)


def tuning_assets():
    """Опыты, V1 и все кандидаты V2 (показанные на карточках, включая исключённые опознанием)."""
    out = _tuning()
    with open(os.path.join(V2_OUT, "candidates_all.json"), encoding=v1.ENC) as f:
        v2c = [c["asset_id"].upper() for c in json.load(f)]
    if len(v2c) < 100:
        raise SystemExit("кандидаты V2 прочитались не целиком: %d" % len(v2c))
    for a in v2c:
        out.setdefault(a, "партия PROD_TWO_PASS_V2")
    return out


v1.tuning_assets = tuning_assets


def hypothesis(c):
    names = [n for n in (c["name"], c["other_name"]) if n.strip() and n.strip().upper() != "UNKNOWN"]
    if len(names) == 1 and len([n for n in (c["name"], c["other_name"]) if n.strip()]) == 2:
        return "one older model could not identify it, the other guessed: %s (disputed)" % names[0]
    if c["other_name"]:
        return "two older model guesses DISAGREE: (a) %s; (b) %s" % (c["name"], c["other_name"])
    return "older model guess (disputed): %s" % c["name"]


def do_select():
    lp = os.path.join(v1.OUT, "identity_list.json")
    if os.path.exists(lp):
        raise SystemExit("identity_list.json уже есть - список не переписываю")
    import re
    import photo_accept as pa
    import pilot_batch as pbt
    keep_lv, keep_geo = pbt.LEVELS, pbt.GEOMETRY
    pbt.LEVELS = dict(keep_lv, HARD=LEVEL)
    pbt.GEOMETRY = re.compile(r"(?!x)x")       # сложная геометрия - тоже производство (как V1)
    try:
        cands, drop = pbt.select()
    finally:
        pbt.LEVELS, pbt.GEOMETRY = keep_lv, keep_geo
    drop = Counter({k: v for k, v in drop.items()})
    other = [c for c in cands if c["level"] != LEVEL]
    drop["не HARD (прочие уровни взяты V1/V2 или вне V3)"] += len(other)
    used = tuning_assets()
    dec = {r["asset_id"]: r for r in v1.read_tsv(v1.ID_LOG)}
    picked, taken = [], []
    for c in sorted((c for c in cands if c["level"] == LEVEL), key=lambda c: (-c["places"], c["asset_id"])):
        aid, fam = c["asset_id"].upper(), c["family"].upper()
        d = dec.get(c["asset_id"], {}).get("decision", "") or dec.get(c["family"], {}).get("decision", "")
        why = None
        if aid in used or fam in used:
            why = "был в опытах или в V1/V2"
        elif pa.DEBRIS.search(c["name"]) or pa.DEBRIS.search(c["other_name"]):
            why = "обломки или кусок по названию (R-153)"
        elif d in v1.REJECTED:
            why = "опознание отклонено человеком"
        elif not c["name"].strip():
            why = "нет ни одного старого названия"
        elif set(c["categories"]) & NATURE_ANY or pbt.NATURE.search(c["name"] + " " + c["other_name"]):
            why = "природа или рельеф хотя бы у одной модели (пул природы закрыт)"
        elif v1.set_variant(aid, taken):
            why = "вероятная перекраска набора (R-166)"
        if why:
            drop[why] += 1
            continue
        taken.append(aid)
        picked.append(dict(c, ident_key=c["asset_id"], card=hypothesis(c), confirmed=False))
    os.makedirs(v1.OUT, exist_ok=True)
    v1.dump(picked, v2.ALL)
    v1.dump([{"category": "prod %d" % (i + 1), "asset_id": c["ident_key"], "rank": c["rank"], "places": c["places"],
              "kind": "один", "identity_status": c["level"], "identity": c["card"], "for": c["asset_id"]}
             for i, c in enumerate(picked[:v1.TARGET])], lp)
    v1.dump({"created": v1.time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": v1.PROFILE, "target": v1.TARGET,
             "group": "HARD (models disagree on identity), specialist 05.10", "pool": len(cands),
             "eligible": len(picked), "listed": min(len(picked), v1.TARGET), "dropped": dict(drop),
             "sets": len({c["asset_id"].split(":")[0] for c in picked[:v1.TARGET]})},
            os.path.join(v1.OUT, "candidates_manifest.json"))
    print("годных HARD: %d; на карточки %d (цель %d)" % (len(picked), min(len(picked), v1.TARGET), v1.TARGET))
    print("отсев: %s" % dict(drop))
    for i, c in enumerate(picked[:v1.TARGET], 1):
        print("  %3d %-26s мест %-4d %s" % (i, c["asset_id"], c["places"], c["card"][:90]))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "select":
        sys.stdout.reconfigure(encoding="utf-8")
        os.chdir(v1.ROOT)
        do_select()
    else:
        v2.main()


if __name__ == "__main__":
    main()
