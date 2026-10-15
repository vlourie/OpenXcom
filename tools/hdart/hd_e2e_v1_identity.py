#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""HD_PIPELINE_E2E_V1: собственные карточки опознания (ось A) для якорей партии без своего final_identity.

Специалист 03.10, передал Vitali в чате: «сделать собственное identity для BATHBITZ:14». Ось A E2E читается из
relation-holdout-v7/answers_vitali.tsv, а он закрыт хэшами VERIFIED V7 - дописывать туда нельзя. Поэтому ответы
этих карточек живут отдельно (hd-e2e-v1/identity/answers_vitali.tsv, те же пять столбцов, что у V7) и станут
входом планировщика только при пересборке плана после ревью (шаг 6), отдельным решением.

Карточка собирается тем же кодом, что карточки оси A V7 (identity_card.Cards, routing_holdout.PAGE_V,
relation_holdout_v7.clean_page: белый список полей n, asset, panels, facts, notes, блок гипотез вырезан, вся
страница проверяется на запрещённое - R-187). Кадра нет в asset_identity.tsv и в очереди (на картах он не стоит),
поэтому строка и запись очереди - пустые заглушки: src - сам кадр, мест 0; места на картах ищет Cards.places
по побайтным копиям кадра, и панель называет копию.

    cards --assets BATHBITZ:14   -> hd-e2e-v1/identity/index.html, cards.json, img/
    check                        карточки не изменились (sha картинок), ответов ещё нет / есть

    py -3.13 tools/hdart/hd_e2e_v1_identity.py <команда>
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hd_e2e_v1 as E1                            # noqa: E402
import identity_routing as ir                     # noqa: E402

OUT = os.path.join(E1.OUT, "identity")
ANSWERS = os.path.join(OUT, "answers_vitali.tsv")
STUB_RANK = 10 ** 6                               # ранг заглушки: в очереди таких нет
DECISION = ("специалист 03.10, передал Vitali в чате: собственная карточка опознания для BATHBITZ:14 "
            "(тикет IDENTITY_MISSING); ось A V7 не меняется, ответы - отдельный файл")


def p(*a):
    return os.path.join(OUT, *a)


def add_to_similar(C, key):
    """Индекс похожих (Cards.sim_index) знает только кадры, стоящие на картах, - кадра вне карт в нём нет,
    и similar() не находит даже его побайтных копий, а через копии Cards.places ищет места. Признаки кадра
    считаются той же формулой, что в sim_index, и дописываются в индекс в памяти; кэш на диске не трогаем."""
    import hashlib
    import numpy as np
    from PIL import Image
    S = C.sim_index()
    kk = "kept" if "kept" in S else "keys"
    if key in list(S[kk]):
        return
    a = np.asarray(C.sprite(key).convert("RGBA"))
    m = a[..., 3] > 0
    ys, xs = np.nonzero(m)
    crop, cm = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1], m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    mi = np.asarray(Image.fromarray((cm * 255).astype(np.uint8)).resize((16, 20), Image.BILINEAR)) / 255.0
    lum = (crop[..., :3].astype(np.float32).mean(-1) * cm).astype(np.uint8)
    li = np.asarray(Image.fromarray(lum).resize((16, 20), Image.BILINEAR)).astype(np.float32).ravel()
    li = (li - li.mean()) / (li.std() + 1e-6)
    S[kk] = list(S[kk]) + [key]
    S["M"] = np.vstack([S["M"], mi.ravel()[None].astype(np.float32)])
    S["L"] = np.vstack([S["L"], li[None]])
    S["COL"] = np.vstack([S["COL"], crop[cm][:, :3].astype(np.float32).mean(0)[None]])
    S["H"] = np.append(S["H"], hashlib.sha1(np.ascontiguousarray(a[..., :3] * m[..., None]).tobytes()
                                            + m.tobytes()).hexdigest())


def blind_similar(C):
    """Cards.p_similar впечатывает в картинку опознание и статус аналога из asset_identity.tsv - у побайтной
    копии XB3BITZ1:14 это гипотеза модели (AGENT_PROPOSED). Чистка страницы (clean_page) картинок не видит
    (R-187), поэтому подпись здесь только данные игры: кадр, COPY или сходство, террейны."""
    import identity_card as ic

    def p_similar(sims):
        cells = []
        for score, iou, corr, dcol, k, exact in sims:
            sp = C.sprite(k)
            if sp is None:
                continue
            terr = ",".join(sorted({t for t, b, n in C.ctx.usage.get(k.upper(), [])})[:2])[:30]
            cells.append(ic.caption(ic.big(sp, 3, ic.DARK), [k, "COPY" if exact else "sim %.2f (iou %.2f)" % (
                score, iou), terr]))
        return ic.stack([ic.row(cells[i:i + 6]) for i in range(0, len(cells), 6)]) if cells else None
    C.p_similar = p_similar


def do_cards(assets):
    import identity_card as ic
    import relation_holdout_v7 as H
    import routing_holdout as rh
    import routing_holdout_v8 as h8
    import routing_model_v8 as v8
    if os.path.exists(ANSWERS):
        raise SystemExit("ответы уже есть - карточки не перестраиваются: %s" % ANSWERS)
    os.makedirs(p("img"), exist_ok=True)
    C = ic.Cards()
    blind_similar(C)
    cards = []
    for n, a in enumerate(assets, 1):
        if a in C.rows:
            raise SystemExit("%s есть в asset_identity.tsv - карточку собирает общий путь" % a)
        rank = STUB_RANK + n
        C.items[rank] = {"rank": rank, "kind": "один", "places": 0, "cells": 1, "blocks": 0, "keys": [a],
                         "frames": [a], "src": [a], "map": "", "at": [[0, 0, 0]], "hint": ""}
        C.rows[a] = {"asset_id": a, "canonical": a, "rank": str(rank), "asset_class": "", "status": "",
                     "identity": "", "proposed": ""}
        add_to_similar(C, a)
        t0 = time.time()
        c = C.card(a, OUT, n)
        cards.append(c)
        print("%-20s панелей %d, рентген %d, %.0f с" % (a, len(c["panels"]), c["xray"], time.time() - t0), flush=True)
        if not c["xray"]:
            raise SystemExit("%s: рентгена нет - карточка неполная, страницу не собираю" % a)
    key = "hd-e2e-v1-identity-" + E1.jsha(assets)[:8]
    title = "Holdout маршрута: 40 новых предметов"
    if title not in rh.PAGE_V:
        raise SystemExit("заголовок страницы V4_R1 не найден")
    raw = (rh.PAGE_V.replace(title, "E2E V1: опознание %d кадр(ов) - только ось A" % len(cards))
           .replace("__DATA__", json.dumps([dict(c) for c in cards], ensure_ascii=False))
           .replace("__MISS__", json.dumps(ic.MISSING)).replace("__SEM__", json.dumps(v8.SEMANTIC))
           .replace("__DEFS__", json.dumps({"semantic_kind": h8.SEM_DEFS}, ensure_ascii=False))
           .replace("__KEY__", key))
    page, clean, dropped = H.clean_page(raw, key)
    with open(p("index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    ir.dump_json(p("cards.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "decision": DECISION,
                                   "img_sha256": ir.img_digest(p("img")), "assets": [c["asset"] for c in clean],
                                   "cards": clean, "dropped_fields": dropped, "storage_key": key,
                                   "answers": os.path.relpath(ANSWERS, E1.OUT),
                                   "answer_columns": ["asset_id", "final_identity", "semantic_kind",
                                                      "missing_context", "note"]})
    rel = os.path.relpath(os.path.abspath(OUT), os.path.abspath(os.path.join("art", "objects", "generation")))
    print("карточек %d (убраны поля %s); страница: http://localhost:8778/%s/index.html" % (
        len(clean), dropped, rel.replace(os.sep, "/")))


def do_check():
    d = ir.load_json(p("cards.json"))
    if ir.img_digest(p("img")) != d["img_sha256"]:
        raise SystemExit("картинки карточек изменились после сборки")
    print("карточки целы: %s; ответов %s" % (", ".join(d["assets"]), "есть" if os.path.exists(ANSWERS) else "нет"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("cards", "check"))
    ap.add_argument("--assets", default="BATHBITZ:14")
    a = ap.parse_args()
    if a.cmd == "cards":
        do_cards([x.strip() for x in a.assets.split(",") if x.strip()])
    else:
        do_check()


if __name__ == "__main__":
    main()
