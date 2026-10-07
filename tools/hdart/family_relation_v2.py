#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""FAMILY_RELATION_V2 - прямые строгие пары перекраски отдельным файлом рядом с семействами (специалист 01.10). CPU.

Рабочий families.json не меняется. Семейство там - связная компонента, а замыкание по цепочке склеивает разные вещи
(families-recolor-v2: 4 компоненты, 19 пар связаны только через третий кадр). Здесь связь - только прямая пара:

    A ~ B строгая перекраска         связь A-B доказана
    A ~ B и B ~ C                    НЕ даёт A ~ C

Строгая пара: силуэт >= 0.98, цвет B - функция цвета A и обратно на >= 0.98 пикселей (relation_probe, поиск принят
на holdout V4_R1: первичных 17/17, дополнение 5/5). family_id в файле нет нарочно.

Статус пары:
    VERIFIED_DIRECT   рабочие семейства уже связывали эти кадры, и прямой строгий тест это подтвердил
    DIRECT_NEW        прямой строгий тест прошёл, в рабочих семействах кадры не в одном семействе
    LEGACY_RELATION   рабочая связь recolor (канон -> член), прямой строгий тест не прошла: не ложь, а REVIEW -
                      304 из 652 такие из-за сжатой палитры (функция в одну сторону); маршрут её не использует
VERIFIED_DIRECT - проверка машиной, не человеком (human_verified = no): подтверждение человеком - отдельно.
Уверенность: STRONG - набор того же номера целиком перекраска (доля >= SET_SHARE) и MCD тот же; иначе CANDIDATE.
Сторона: у пары из рабочего семейства с каноном - канон основа (выбор базы семейств не меняется); иначе основа -
кадр, что чаще стоит на картах (touch.tsv, при равенстве младший ключ), как у детектора родства.

    py -3.13 tools/hdart/family_relation_v2.py build    -> art/objects/discovery/family_relation_v2/
"""
import argparse
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import families_recolor_diff as frd    # noqa: E402
import identity_routing as ir          # noqa: E402
import relation_probe as rp            # noqa: E402

ROOT = ir.ROOT
OUT = os.path.join("art", "objects", "discovery", "family_relation_v2")
TSV = os.path.join(OUT, "family_relation_v2.tsv")
DIRECT = ("VERIFIED_DIRECT", "DIRECT_NEW")
COLS = ["asset_a", "asset_b", "relation", "status", "confidence", "direct", "base", "direction_source",
        "human_verified", "iou", "f_ab", "f_ba", "evidence"]


def orient(a, b, places, canon):
    """(основа, производный, источник направления). canon - ключи канонов рабочих семейств, общих для пары."""
    if a in canon and b not in canon:
        return a, b, "family_canonical"
    if b in canon and a not in canon:
        return b, a, "family_canonical"
    pa, pb = places.get(a.upper(), 0), places.get(b.upper(), 0)
    if pa > pb or (pa == pb and a < b):
        return a, b, "places"
    return b, a, "places"


def classify(pairs, links, fam_of, keys_of, places, canonical_of):
    """pairs: [(a, b, level, iou, f_ab, f_ba)] прямых строгих; links: [(канон, член, family, iou, f_ab, f_ba, ok, why)]
    рабочих связей recolor. Возвращает строки файла."""
    fams = lambda k: {fam_of[x.upper()] for x in keys_of.get(k, [k]) if x.upper() in fam_of}   # noqa: E731
    rows, seen = [], set()
    for a, b, lv, iou, f_ab, f_ba in pairs:
        shared = fams(a) & fams(b)
        canon = {canonical_of[f] for f in shared if f in canonical_of}
        base, der, src = orient(a, b, places, canon)
        seen.add(frozenset((a.upper(), b.upper())))
        rows.append({"asset_a": base, "asset_b": der, "relation": "RECOLOR_OF",
                     "status": "VERIFIED_DIRECT" if shared else "DIRECT_NEW", "confidence": lv, "direct": "yes",
                     "base": base, "direction_source": src, "human_verified": "no", "iou": iou, "f_ab": f_ab,
                     "f_ba": f_ba, "evidence": "силуэт %.3f, функция цвета %.3f / %.3f" % (iou, f_ab, f_ba)})
    for c, m, fid, iou, f_ab, f_ba, ok, why in links:
        if frozenset((c.upper(), m.upper())) in seen:
            continue
        seen.add(frozenset((c.upper(), m.upper())))
        rows.append({"asset_a": c, "asset_b": m, "relation": "RECOLOR_OF",
                     "status": "VERIFIED_DIRECT" if ok else "LEGACY_RELATION",
                     "confidence": "CANDIDATE" if ok else "", "direct": "yes" if ok else "no", "base": c,
                     "direction_source": "family_canonical", "human_verified": "no", "iou": iou, "f_ab": f_ab,
                     "f_ba": f_ba, "evidence": ("рабочая связь, строгий тест прошёл (вне скана: %s)" % why) if ok
                     else "рабочая связь, строгий тест не прошёл: %s" % why})
    return rows


def build(out=OUT):
    t0 = time.time()
    ctx = rp.Ctx()
    items = ir.load_json(rp.ITEMS)
    keys_of = {it["src"][0]: it["keys"] for it in items if it["kind"] != "составной"}
    rep = {k.upper(): it["src"][0] for it in items if it["kind"] != "составной" for k in it["keys"]}
    touch = rp.places_of()
    places = {r.upper(): sum(touch.get(k.upper(), 0) for k in ks) for r, ks in keys_of.items()}
    os.makedirs(out, exist_ok=True)
    _res, found = rp.scan(ctx, out)
    fams = ir.load_json(rp.FAMILIES)
    canonical_of = {f["family_id"]: rep.get(f["canonical"].upper(), f["canonical"]) for f in fams}
    fam_of, links = frd.production()
    cache = {}

    def arr(k):
        if k not in cache:
            a = ctx.rgba(k)
            cache[k] = None if a is None else rp.codes(a)
        return cache[k]

    set_cache = {}

    def level(a, b):
        sa, fa = rp.of.split(a)
        sb, fb = rp.of.split(b)
        if fa != fb or sa.upper() == sb.upper():
            return "CANDIDATE"
        key = tuple(sorted((sa.upper(), sb.upper())))
        if key not in set_cache:
            set_cache[key] = rp.sets(ctx, key[0], key[1])
        if set_cache[key]["share_strict"] < rp.SET_SHARE:
            return "CANDIDATE"
        ia, ib = ctx.st.info(sa, fa), ctx.st.info(sb, fb)
        same = (ia.get("rec") and ib.get("rec") and not [k for k in ia["phys"] if ia["phys"][k] != ib["phys"].get(k)]
                and bool((ia["vox"] == ib["vox"]).all()))
        return "STRONG" if same else "CANDIDATE"

    pairs = []
    for x in found:
        if x[2] >= rp.FUNC and x[3] >= rp.FUNC and not x[5]:
            A, B = arr(x[0]), arr(x[1])
            iou = frd.strict(A[0], A[1], B[0], B[1])[0]
            pairs.append((x[0], x[1], level(x[0], x[1]), round(iou, 3), x[2], x[3]))
    lk = []
    for c, m, fid in links:
        c, m = rep.get(c.upper(), c), rep.get(m.upper(), m)
        A, B = arr(c), arr(m)
        if A is None or B is None or c == m:
            continue
        iou, f_ab, f_ba, ok = frd.strict(A[0], A[1], B[0], B[1])
        why = "пиксели равны или меньше %d пикселей" % 20 if ok else frd.unconf_why(iou, f_ab, f_ba)
        lk.append((c, m, fid, round(iou, 3), round(f_ab, 3), round(f_ba, 3), ok, why))
    rows = classify(pairs, lk, fam_of, keys_of, places, canonical_of)
    with open(os.path.join(out, "family_relation_v2.tsv"), "w", encoding=ir.ENC, newline="") as f:
        f.write("\t".join(COLS) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in COLS) + "\n")
    st = Counter(r["status"] for r in rows)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "families_json_untouched": rp.FAMILIES,
           "thresholds": {"GEO": rp.GEO, "FUNC": rp.FUNC, "SET_SHARE": rp.SET_SHARE},
           "rows": len(rows), "by_status": dict(st),
           "by_status_confidence": {"%s %s" % k: v for k, v in sorted(Counter((r["status"], r["confidence"] or "-")
                                                                             for r in rows).items())},
           "direction_source": dict(Counter(r["direction_source"] for r in rows if r["status"] in DIRECT)),
           "legacy_why": dict(Counter(r["evidence"].split(": ", 1)[-1] for r in rows
                                      if r["status"] == "LEGACY_RELATION")),
           "seconds": round(time.time() - t0)}
    ir.dump_json(os.path.join(out, "summary.json"), res)
    L = ["# FAMILY_RELATION_V2 - прямые строгие пары перекраски", "",
         "Файл рядом с семействами; рабочий %s не менялся. Связь - только прямая пара, без family_id и без "
         "замыкания по цепочке." % rp.FAMILIES, "", "| статус | уверенность | пар |", "|---|---|---|"]
    L += ["| %s |" % k.replace(" ", " | ") + " %d |" % v for k, v in res["by_status_confidence"].items()]
    L += ["", "Направление прямых пар: %s." % ", ".join("%s %d" % kv for kv in sorted(res["direction_source"].items())),
          "", "LEGACY_RELATION по причине: %s." % ", ".join("%s %d" % kv for kv in sorted(res["legacy_why"].items())),
          "", "VERIFIED_DIRECT - подтверждено машиной (human_verified = no). LEGACY_RELATION - не ложь: маршрут её "
          "не использует, решает человек или миграция семейств."]
    with open(os.path.join(out, "summary.md"), "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return res


def load(path=TSV):
    """Ключ кадра (все ключи предмета) -> рёбра со стороной: [{relative, status, confidence, side, ...}]."""
    items = ir.load_json(rp.ITEMS)
    keys_of = defaultdict(list)
    for it in items:
        for k in it["keys"]:
            keys_of[it["src"][0].upper()].append(k.upper())
    idx = defaultdict(list)
    for r in ir.read_tsv(path):
        for me, other, side in ((r["asset_b"], r["asset_a"], "derived"), (r["asset_a"], r["asset_b"], "base")):
            for k in keys_of.get(me.upper(), [me.upper()]):
                idx[k].append(dict(r, relative=other, side=side))
    return dict(idx)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build"])
    ap.parse_args()
    os.chdir(ROOT)
    build()


if __name__ == "__main__":
    main()
