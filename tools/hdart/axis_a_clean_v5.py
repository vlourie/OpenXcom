#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Очищенный ZIP карточек оси A holdout V5 (второй выпуск). Первый ZIP (relation_holdout_v4_axis_zip.py) вычищал
только prompt: в DATA остались поля answers, verdict, status, а шаблон страницы показывал их блоком
«7. гипотезы ... MODEL HYPOTHESIS A/B» - специалист нашёл это 02.10 до разметки, ответы по первому ZIP не слепые.

Здесь карточка собирается по белому списку - только поля, которые страница показывает как данные игры (n, asset,
panels, facts, notes), после той же чистки панелей и фактов, что в V4 (axis_zip.clean). Из шаблона физически вырезан
блок гипотез и фраза про ответы моделей. Затем вся страница проверяется на запрещённое, а не только DATA.
Выгрузка страницы - пять столбцов (asset_id, final_identity, semantic_kind, missing_context, note): отчёт V5 читает
из ответа только semantic_kind, render_unit не нужен.

Замороженные relation_holdout_v5.py и relation_holdout_v4_axis_zip.py не меняются; страница и cards.json в папке
holdout тоже. Собирается только после замка эталона и до ответов оси A.

  py -3.13 tools/hdart/axis_a_clean_v5.py [--out DIR] [--dest DIR]
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import identity_routing as ir                     # noqa: E402
import relation_holdout_v4_axis_zip as az         # noqa: E402

OUT = os.path.join(ir.PROBES, "relation-holdout-v5")
KEEP = ("n", "asset", "panels", "facts", "notes")
# строки шаблона: (признак строки, чем заменить; None - убрать строку)
LINES = (('7. гипотезы', '  h += `<div class="p">`;'),
         ('UNVERIFIED OLD DESCRIPTION', None),
         ('const ab = ["A", "B"];', None),
         ('MODEL HYPOTHESIS', None))
INTRO = ("Описание прежнее,\nответы моделей и статус в базе - непроверенные гипотезы. ", "")
PAGE_FORBIDDEN = ("HYPOTHESIS", "UNVERIFIED", "гипотез", "c.answers", "c.prompt", "ответы моделей",
                  '"answers"', '"verdict"', '"status"', '"prompt"', "prompt_src", "render_unit")
KEY_OLD, KEY_NEW = 'KEY = "relation-holdout-v5-', 'KEY = "relation-holdout-v5-axisA-v2-'
EXPORT = '["asset_id", "final_identity", "semantic_kind", "missing_context", "note"]'


def clean_card(card):
    c = az.clean(card)
    return {k: c[k] for k in KEEP}


def clean_template(text):
    out, hit = [], {k: 0 for k, _ in LINES}
    for ln in text.split("\n"):
        rule = next(((k, v) for k, v in LINES if k in ln), None)
        if rule is None:
            out.append(ln)
            continue
        hit[rule[0]] += 1
        if rule[1] is not None:
            out.append(rule[1])
    miss = [k for k, n in hit.items() if n != 1]
    if miss:
        raise SystemExit("в шаблоне не найдены ровно один раз: %s" % miss)
    text = "\n".join(out)
    if text.count(INTRO[0]) != 1:
        raise SystemExit("фраза про ответы моделей не найдена ровно один раз")
    return text.replace(INTRO[0], INTRO[1])


def build(out, dest):
    if not os.path.exists(os.path.join(out, "reference.lock.json")):
        raise SystemExit("эталон ещё не заморожен - ZIP оси A только после lockref")
    if os.path.exists(os.path.join(out, "answers_vitali.tsv")):
        raise SystemExit("ответы оси A уже есть")
    page = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    head, data, tail = az.split_page(page)
    cards = ir.load_json(os.path.join(out, "cards.json"))["cards"]
    if [c["asset"] for c in data] != [c["asset"] for c in cards]:
        raise SystemExit("страница и cards.json расходятся")
    new = [clean_card(c) for c in data]
    dropped = sorted({k for c in data for k in c} - set(KEEP))
    blob = json.dumps(new, ensure_ascii=False)
    cut = "\x00DATA\x00"
    head, tail = clean_template(head + cut + tail).split(cut)
    # свой ключ хранилища: та же страница первого ZIP в том же браузере подставила бы прежнюю (не слепую) разметку
    if tail.count(KEY_OLD) != 1:
        raise SystemExit("ключ хранилища страницы не найден ровно один раз")
    tail = tail.replace(KEY_OLD, KEY_NEW)
    full = head + blob + tail
    bad = [w for w in az.FORBIDDEN if w in blob] + [w for w in PAGE_FORBIDDEN if w in full]
    if bad:
        raise SystemExit("на странице осталось запрещённое: %s" % bad)
    if EXPORT not in full:
        raise SystemExit("выгрузка страницы не в пять столбцов")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(os.path.join(dest, "img"))
    with open(os.path.join(dest, "index.html"), "w", encoding="utf-8") as f:
        f.write(full)
    imgs = sorted({fn for c in new for _t, fn in c["panels"]})
    for fn in imgs:
        shutil.copy2(os.path.join(out, "img", fn), os.path.join(dest, "img", fn))
    zp = dest.rstrip("/\\") + ".zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(dest):
            for fn in files:
                full_p = os.path.join(root, fn)
                z.write(full_p, os.path.relpath(full_p, os.path.dirname(dest)))
    recheck(zp)
    sha = hashlib.sha256(open(zp, "rb").read()).hexdigest()
    ir.dump_json(dest.rstrip("/\\") + ".json", {
        "cards": len(new), "images": len(imgs), "card_fields": list(KEEP), "dropped_fields": dropped,
        "template_removed": [k for k, _ in LINES] + ["intro: ответы моделей"],
        "answer_columns": json.loads(EXPORT), "zip": os.path.basename(zp), "zip_sha256": sha,
        "supersedes": "axisA_cards.zip - гипотезы модели в DATA и на странице, ответы по нему не слепые",
        "reference_lock_sha256": hashlib.sha256(open(os.path.join(out, "reference.lock.json"), "rb").read())
        .hexdigest()})
    print("карточек %d, картинок %d, убраны поля %s; %s (sha256 %s)" % (len(new), len(imgs), dropped, zp, sha[:12]))


def recheck(zp):
    """Проверка по самому архиву: то, что уйдёт специалисту, а не то, что лежит рядом."""
    with zipfile.ZipFile(zp) as z:
        for name in z.namelist():
            if name.endswith((".html", ".json", ".js", ".txt", ".md")):
                text = z.read(name).decode("utf-8")
                bad = [w for w in PAGE_FORBIDDEN + az.FORBIDDEN if w in text]
                if bad:
                    raise SystemExit("в архиве %s осталось запрещённое: %s" % (name, bad))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--dest", default="")
    a = ap.parse_args()
    build(a.out, a.dest or os.path.join(a.out, "axisA_cards_v2"))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
