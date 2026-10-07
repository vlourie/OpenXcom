#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZIP карточек оси A holdout V4 для специалиста - копия страницы без того, что запрещено на карточках (специалист
02.10, сообщение 5): выход детекторов, пул пар, ответы судей, эталон, слой, уверенность связи, группы рисования.

Страница и cards.json в папке holdout не меняются (их строил замороженный relation_holdout_v4.cards). В копии убраны:
  - панель 6 «семейство и другой бок» и заметка 6 (obj_families - детектор семейств);
  - панель 8 «тот же кадр и похожие» (поиск копий и сходства - детектор);
  - строки фактов «one object of N map cells (composite)» (группа рисования obj_series), «same object in other
    tilesets/colours» (семейства), «possible other sides of it» (другой бок);
  - гипотеза опознания кадра (prompt из asset_identity.tsv - ответ модели) и описания соседей в скобках из того же
    источника.
Остаются: кадр, места на картах, соседние кадры набора, соседи на карте, запись MCD, сырые факты MCD и объёма.
Собирается только после замка эталона: reference.lock.json есть, answers_vitali.tsv нет.

  py -3.13 tools/hdart/relation_holdout_v4_axis_zip.py [--dry DIR]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import identity_routing as ir                     # noqa: E402

OUT = os.path.join(ir.PROBES, "relation-holdout-v4")
DROP_PANELS = ("6. семейство", "8. тот же кадр")
DROP_NOTES = DROP_PANELS                          # заметка «панели нет» несёт ту же легенду
DROP_FACTS = ("- one object of ", "- same object in other tilesets", "- possible other sides of it")
NEAR = "- on the map next to:"
MARK = "const DATA = "
FORBIDDEN = ("composite", "other sides", "other tilesets", "семейство", "похожие", "COPY - ", "sim - ",
             "STRONG", "CANDIDATE", "TYPE_OPEN", "MIRRORED_RECOLOR", "R4b", "P5r", "judge", "truth")


def strip_near(line):
    """Соседи на карте без описаний модели в скобках (скобки могут быть вложенными и обрезанными)."""
    out, depth = [], 0
    for ch in line:
        if ch == "(":
            depth += 1
            continue
        if ch == ")" and depth:
            depth -= 1
            continue
        if not depth:
            out.append(ch)
    return re.sub(r" +;", ";", re.sub(r"  +", " ", "".join(out))).rstrip()


def clean(card):
    c = dict(card)
    c["panels"] = [[t, f] for t, f in card["panels"] if not t.startswith(DROP_PANELS)]
    c["notes"] = [n for n in card["notes"] if not n.startswith(DROP_NOTES)]
    lines = []
    for ln in card["facts"].split("\n"):
        if ln.startswith(DROP_FACTS):
            continue
        lines.append(strip_near(ln) if ln.startswith(NEAR) else ln)
    c["facts"] = "\n".join(lines)
    c["prompt"], c["prompt_src"] = "", ""
    return c


def split_page(page):
    i = page.index(MARK) + len(MARK)
    data, end = json.JSONDecoder().raw_decode(page, i)
    return page[:i], data, page[end:]


def build(out, dest):
    if not os.path.exists(os.path.join(out, "reference.lock.json")):
        raise SystemExit("эталон ещё не заморожен - ZIP оси A только после lockref")
    if os.path.exists(os.path.join(out, "answers_vitali.tsv")):
        raise SystemExit("ответы оси A уже есть")
    page = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    head, data, tail = split_page(page)
    cards = ir.load_json(os.path.join(out, "cards.json"))["cards"]
    if [c["asset"] for c in data] != [c["asset"] for c in cards]:
        raise SystemExit("страница и cards.json расходятся")
    new = [clean(c) for c in data]
    blob = json.dumps(new, ensure_ascii=False)
    bad = [w for w in FORBIDDEN if w in blob]
    if bad:
        raise SystemExit("в карточках осталось запрещённое: %s" % bad)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(os.path.join(dest, "img"))
    with open(os.path.join(dest, "index.html"), "w", encoding="utf-8") as f:
        f.write(head + blob + tail)
    imgs = sorted({fn for c in new for _t, fn in c["panels"]})
    for fn in imgs:
        shutil.copy2(os.path.join(out, "img", fn), os.path.join(dest, "img", fn))
    removed = {"panels": sum(len(a["panels"]) - len(b["panels"]) for a, b in zip(data, new)),
               "notes": sum(len(a["notes"]) - len(b["notes"]) for a, b in zip(data, new)),
               "fact_lines": sum(len(a["facts"].split("\n")) - len(b["facts"].split("\n")) for a, b in zip(data, new)),
               "identity_hypotheses": sum(bool(a.get("prompt")) for a in data),
               "neighbour_descriptions": sum(a["facts"].count("(") for a in data)}
    zp = dest.rstrip("/\\") + ".zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(dest):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, os.path.dirname(dest)))
    sha = hashlib.sha256(open(zp, "rb").read()).hexdigest()
    ir.dump_json(dest.rstrip("/\\") + ".json", {"cards": len(new), "images": len(imgs), "removed": removed,
                                                "zip": os.path.basename(zp), "zip_sha256": sha,
                                                "reference_lock_sha256": hashlib.sha256(open(os.path.join(
                                                    out, "reference.lock.json"), "rb").read()).hexdigest()})
    print("карточек %d, картинок %d, убрано %s; %s (sha256 %s)" % (len(new), len(imgs), removed, zp, sha[:12]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--dest", default="")
    a = ap.parse_args()
    build(a.out, a.dest or os.path.join(a.out, "axisA_cards"))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
