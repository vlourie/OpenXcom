#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Первая десятка Pipeline v2 - приёмочная, а не первые десять по популярности (P1-A).

Десятка проверяет все виды связей разом: если конвейер ошибается в одной из них, это видно на первой
же партии, а не на сотой. Состав:
  recolor    - семейство с перекраской AUTO (кресло: одна вещь в нескольких цветах, выводится);
  mirror x2  - зеркало (AUTO или HUMAN_APPROVED, выводится с возвратом света): кресло FRNITURE 9/8
               и стул VILFRNITURE 2 / FRNITURE 3 - на них партия made01 вышла разными вещами (R-136);
  alt_view   - семейство с другим боком AUTO (рисуется ОДНИМ заказом вместе с каноническим);
  composite  - составной предмет на 2-4 клетки (режется по клеткам после заказа);
  tileable   - плитка: кадр стоит вплотную к своим копиям (стык проверяется на карте);
  single x4  - обычные одиночные предметы без семейства.
Кандидат в категории - самый популярный РУКОТВОРНЫЙ ассет-предмет (R-125: природа - отдельной
очередью), у которого на проверке нет ничего, кроме опознания (ни кандидатов семейства, ни вопроса
«предмет или рельеф»). Рукотворность - по тексту опознания; без опознания предмет в десятку не идёт.
Опознание Vitali подтверждает на карточке (review_server, вкладка «Десятка»). Названным заранее
(PREFER) открытые вопросы семейства не мешают - они на той же карточке.

Пишет art/objects/generation/acceptance.json и .tsv. Сам ничего не генерирует.

    py -3.13 tools/hdart/acceptance_batch.py
"""
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ENC = "utf-8-sig"
GEN = os.path.join("art", "objects", "generation")
IDENT = os.path.join("art", "objects", "discovery", "asset_identity.tsv")
FAMS = os.path.join("art", "objects", "families", "families.json")
PREFER = {"mirror": ("FRNITURE:9", "VILFRNITURE:2")}
PLAN = (("recolor", 1), ("mirror", 2), ("alt_view", 1), ("composite", 1), ("tileable", 1), ("single", 4))
# природа - не предмет (R-125): деревья, кусты, камни, земля
NATURE = re.compile(r"\b(tree|trees|bush|bushes|shrub|fern|palm|pine|fir|spruce|conifer|foliage|leaves|stump|log|"
                    r"logs|trunk|rock|rocks|boulder|boulders|stone|stones|cliff|cactus|grass|flower|flowers|plant|"
                    r"plants|vine|vines|weed|weeds|reed|reeds|mushroom|coral|crystal|ice|snow|dirt|mud|root|roots|"
                    r"branch|branches|hedge|sapling|undergrowth|moss)\b", re.I)


def made(text):
    """Рукотворный предмет по тексту опознания; без опознания - не знаем, в десятку не берём."""
    return bool(text) and not NATURE.search(text)


def what(idr):
    return idr.get("identity") or idr.get("proposed") or ""


def pick(rows, fams, ident):
    fam = {fm["family_id"]: fm for fm in fams}
    preferred = {a for v in PREFER.values() for a in v}

    def open_ok(r):
        # вопросы семейства названному заранее предмету не помеха: они на той же карточке
        return not [b for b in r["blockers"] if b != "identity"
                    and not (r["asset_id"] in preferred and b.startswith("family_review"))]

    items = [r for r in rows if r["action"] == "GENERATE" and r["status"] != "SKIP" and open_ok(r)
             and made(what(ident.get(r["asset_id"], {})))]
    items.sort(key=lambda r: -int(r["places"]))

    def members(r):
        fm = fam.get(r["family"])
        return fm["members"][1:] if fm else []

    def rels(r, kinds, decisions=("AUTO", "HUMAN_APPROVED")):
        return any(m["relation"] in kinds and m["decision"] in decisions for m in members(r))

    test = {
        "recolor": lambda r: rels(r, ("recolor",)),
        "mirror": lambda r: rels(r, ("mirror",)),
        "alt_view": lambda r: rels(r, ("alternate_view",), ("AUTO",)),
        "composite": lambda r: r["kind"] == "составной",
        "tileable": lambda r: bool(fam.get(r["family"]) and fam[r["family"]]["members"][0].get("tile")),
        "single": lambda r: r["kind"] == "один" and not members(r) and not fam.get(r["family"], {}).get("review"),
    }
    used, out = set(), []
    for cat, n in PLAN:
        cands = [r for r in items if r["asset_id"] not in used and test[cat](r)]
        pref = [r for p in PREFER.get(cat, ()) for r in cands if r["asset_id"] == p]
        for r in (pref + [c for c in cands if c not in pref])[:n]:
            used.add(r["asset_id"])
            out.append({"category": cat, "asset_id": r["asset_id"], "rank": r["rank"], "places": r["places"],
                        "kind": r["kind"], "identity_status": r["identity_status"], "blockers": r["blockers"],
                        "identity": what(ident.get(r["asset_id"], {})),
                        "members": [[m["keys"][0], m["relation"], m["decision"]] for m in members(r)],
                        "candidates_in_category": len(cands)})
    return out


def main():
    with open(os.path.join(GEN, "generation.json"), encoding=ENC) as f:
        rows = json.load(f)
    with open(FAMS, encoding=ENC) as f:
        fams = json.load(f)
    with open(IDENT, encoding=ENC, newline="") as f:
        ident = {r["asset_id"]: r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}
    out = pick(rows, fams, ident)
    with open(os.path.join(GEN, "acceptance.json"), "w", encoding=ENC) as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(os.path.join(GEN, "acceptance.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("категория\tассет\tместо\tмест на картах\tвид\tопознание\tчто это\tчлены\n")
        for r in out:
            f.write("\t".join([r["category"], r["asset_id"], str(r["rank"]), str(r["places"]), r["kind"],
                               r["identity_status"], r["identity"],
                               " ".join("%s(%s)" % (k, rel) for k, rel, _d in r["members"])]) + "\n")
    for r in out:
        print("%-9s %-18s #%-5s %4s мест %-10s %-30s %s" % (
            r["category"], r["asset_id"], r["rank"], r["places"], r["kind"],
            " ".join("%s(%s)" % (k, rel[:3]) for k, rel, _d in r["members"])[:30], r["identity"][:55]))
    missing = [c for c, n in PLAN if sum(1 for r in out if r["category"] == c) < n]
    print("десятка: %d из 10%s -> %s" % (len(out), "; не набрано: " + ", ".join(missing) if missing else "",
                                          os.path.join(GEN, "acceptance.tsv")))


if __name__ == "__main__":
    main()
