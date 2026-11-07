#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADJUDICATED_TRUTH_V2 и MIRRORED_RECOLOR_BLIND_V1 - второй независимый судья (специалист 02.10). CPU, чтение.

Пересуд RELATION_TAXONOMY_ADJUDICATION (probes/relation-taxonomy-adjudication, заморожен) дал контроль 0.778 -
единственным эталоном новую истину не берём. Здесь:

  1. second: второй слепой судья только там, где истина держится на одном судье или меняет условия заморозки
     (правило отбора до ответов):
       a) пары 60 и контроля с прежним эталоном, где судья 1 не согласен с ним или ничего не взял (low / UNSURE);
       b) все пары 60, от которых зависит знаменатель составного: «структура» прежнего эталона или COMPOSITE у судьи 1;
       c) срабатывания MIRRORED_RECOLOR / NEAR_RECOLOR, где подтип судьи 1 не тот, что заявил детектор.
     Пакет без кадра «B mirrored» и без отражённого наложения; определения ярлыков те же.
  2. combine: истина v2 = CLOSED / OPEN.
       существование: класс судьи 1 == класс судьи 2 (RELATED / NONE) -> CLOSED, иначе OPEN; связь MCD между A и B
         (die / alt / анимация) или побайтное равенство (копия, отражение) закрывают RELATED без судей;
       подтип: ярлык закрыт, если его дали оба судьи или оба дали ярлык той же группы довода (derived, state,
         animation, composite, modular); остальные ярлыки - OPEN. Существование RELATED без закрытого ярлыка -
         подтип OPEN.
       Пары без второго судьи: согласие судьи 1 с прежним эталоном - CLOSED по общим группам (лишние ярлыки
       судьи 1 - OPEN); не судимые - прежний эталон, как был.
     Метрики: OPEN вне знаменателей; довод верен, если его группа закрыта, неверен, если её нет ни среди закрытых,
     ни среди открытых, иначе OPEN.
  3. mirror: слепая проверка MIRRORED_RECOLOR на новой выборке вне первого пакета - настоящие срабатывания
     вперемешку с трудными отрицательными, без отражённого кадра; два независимых судьи на каждую пару,
     то же правило CLOSED / OPEN. TYPE_STRONG для MIRRORED_RECOLOR - только при точности существования и подтипа
     >= 0.95 на закрытых.

Прежний пакет, его ответы, V2/V3 и holdout не меняются; пороги детекторов не меняются. Судьи - модели, не Vitali.

    py -3.13 tools/hdart/relation_truth_v2.py second-select | second-pack | combine
    py -3.13 tools/hdart/relation_truth_v2.py mirror-select | mirror-pack | mirror-report
"""
import argparse
import os
import sys
import time
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir                     # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_taxonomy as tx                    # noqa: E402

ENC = ir.ENC
p, split, rate = v2.p, v2.split, v2.rate
OUT = os.path.join(ir.PROBES, "relation-truth-v2")
MOUT = os.path.join(ir.PROBES, "mirror-recolor-blind-v1")
SECOND_BATCHES = 2
# выборка зеркальной проверки (до ответов)
M_FIRES, M_NEGS = 48, 40                           # срабатываний и трудных отрицательных
M_SOURCES = 6000                                   # исходных кадров просмотреть не больше
M_JUDGES = 2                                       # независимых судей на каждую пару
M_BATCHES = 4                                      # партий: каждая пара в двух партиях разных судей
M_GATE = 0.95


def order(s, salt):
    import hashlib
    return hashlib.sha256((salt + "|" + s).encode()).hexdigest()


def pk(a, b):
    return tx.pk(a, b)


def groups(labels):
    return {tx.LABEL_GROUP[l] for l in labels if l in tx.LABEL_GROUP}


# ---------------------------------------------------------------- правило CLOSED / OPEN (до ответов)

def combine_pair(j1, j2, authority=False):
    """j1, j2 - взятые ярлыки двух судей (medium/high, NONE с другим снят). -> (существование, закрытые, открытые)."""
    e1, e2 = tx.existence_class(j1), tx.existence_class(j2)
    if authority:
        ex = "RELATED"
    elif e1 == e2 and e1 != "OPEN":
        ex = e1
    else:
        ex = "OPEN"
    if ex == "NONE":
        return ex, {"NONE"}, set()
    allr = (set(j1) | set(j2)) - {"NONE"}
    g = groups(j1) & groups(j2)
    closed = {l for l in allr if (l in j1 and l in j2) or tx.LABEL_GROUP.get(l) in g}
    if ex == "OPEN":
        return ex, set(), allr
    return ex, closed, allr - closed


def combine_with_old(j1, old):
    """Пара без второго судьи, судья 1 согласен с прежним эталоном: закрыты ярлыки общих групп."""
    ref = tx.OLD_REF[old]
    if ref == {"NONE"}:
        return ("NONE", {"NONE"}, set()) if tx.existence_class(j1) == "NONE" else ("OPEN", set(), set(j1))
    g = groups(j1) & groups(ref)
    closed = {l for l in j1 if tx.LABEL_GROUP.get(l) in g}
    return "RELATED", closed, set(j1) - closed - {"NONE"}


def claim_state(c, t):
    """Довод против истины v2: ok / wrong / open."""
    ex, closed, opn = t
    if ex == "OPEN":
        return "open"
    if ex == "NONE":
        return "wrong"
    gc, go = groups(closed), groups(opn)
    if c["group"] in gc:
        return "ok"
    if c["group"] in go or not closed:
        return "open"
    return "wrong"


# ---------------------------------------------------------------- пакет без отражённого кадра

def pair_image(ctx, a, b):
    """A | B | силуэты A и B; ниже - соседние номера в PCK. Без B mirrored и отражённого наложения."""
    from PIL import ImageDraw
    A, B = ctx.rgba(a), ctx.rgba(b)
    top = tx.hrow([tx.captioned(tx.big(A), "A " + a), tx.captioned(tx.big(B), "B " + b),
                   tx.captioned(tx.overlay(A, B), "A red / B green")])
    strips = []
    sa, fa = split(a)
    sb, fb = split(b)
    grp = [(sa, sorted({fa, fb}))] if sa == sb else [(sa, [fa]), (sb, [fb])]
    for s, fs in grp:
        lo, hi = max(0, min(fs) - 2), max(fs) + 2
        if hi - lo > 13:
            rng = sorted(set(range(max(0, fs[0] - 2), fs[0] + 3)) | set(range(max(0, fs[-1] - 2), fs[-1] + 3)))
        else:
            rng = list(range(lo, hi + 1))
        cells = []
        for f in rng:
            arr = ctx.rgba("%s:%d" % (s, f))
            if arr is None:
                continue
            im = tx.captioned(tx.big(arr, 2), "%d" % f)
            k = "%s:%d" % (s, f)
            col = (255, 40, 40) if k == a.upper() else (40, 220, 40) if k == b.upper() else None
            if col:
                ImageDraw.Draw(im).rectangle((0, 0, im.width - 1, im.height - 1), outline=col, width=3)
            cells.append(im)
        if cells:
            strips.append(tx.captioned(tx.hrow(cells, 4), "PCK %s, neighbouring frame numbers (A red, B green)" % s))
    return tx.vstack([top] + strips)


JUDGE = tx.JUDGE.replace(
    "- `Qnnn_pair.png`: A, B, B mirrored, silhouette overlays (A red, B green), and neighbouring frame numbers in the\n"
    "  same sprite file (PCK).",
    "- `Qnnn_pair.png`: A, B, their silhouettes overlaid as drawn (A red, B green), and neighbouring frame numbers\n"
    "  in the same sprite file (PCK). To compare with a left-right mirror image, mirror it in your mind.")
assert JUDGE != tx.JUDGE, "текст JUDGE прежнего пакета изменился - замена не легла"


def write_pack(out, items, batches, salt, judges_per_item=1):
    """items: [{q, a, b}] -> blind/ (картинки, JUDGE.md, batch_N.md), answers/, pack.lock.json.
    judges_per_item 2: каждая пара попадает в две партии, у разных судей (партии i и i + batches/2)."""
    import routing_model_v8 as v8
    if os.path.exists(p(out, "answers")) and os.listdir(p(out, "answers")):
        raise SystemExit("ответы уже есть - пакет не перестраивается")
    blind = p(out, "blind")
    os.makedirs(blind, exist_ok=True)
    ctx = v3.Ctx(index=v2.load_index(v2.OUT))
    mcd = v8.Mcd(ctx.world)
    with open(p(blind, "JUDGE.md"), "w", encoding=ENC, newline="\n") as f:
        f.write(JUDGE)
    entries = []
    t0 = time.time()
    for it in items:
        q, a, b = it["q"], it["a"], it["b"]
        L, (pa, pb, cnt, blocks) = tx.facts(ctx, mcd, a, b)
        pair_image(ctx, a, b).save(p(blind, q + "_pair.png"))
        mi = tx.map_image(ctx, a, b, pa, pb, cnt, blocks)
        files = [q + "_pair.png"]
        if mi is not None:
            mi.save(p(blind, q + "_map.png"))
            files.append(q + "_map.png")
        entries.append({"q": q, "files": files, "facts": L})
        print("%s %s %s %.0f с" % (q, a, b, time.time() - t0), flush=True)
    os.makedirs(p(out, "answers"), exist_ok=True)
    n = len(entries)
    per = batches // judges_per_item
    parts = []
    for j in range(judges_per_item):
        es = entries if j == 0 else sorted(entries, key=lambda e: order(e["q"], salt + "|judge%d" % j))
        for i in range(per):
            parts.append(es[i * n // per:(i + 1) * n // per])
    for i, part in enumerate(parts):
        ans = os.path.abspath(p(out, "answers", "judge_%d.tsv" % (i + 1))).replace(os.sep, "/")
        L = ["# Batch %d of %d: %d pairs" % (i + 1, len(parts), len(part)), "",
             "Instructions and label definitions: JUDGE.md in this folder. Write your answers to:", "",
             "    " + ans, "", "Images are in this folder.", ""]
        for e in part:
            L += ["## " + e["q"], "", "Images: " + ", ".join(e["files"]), ""] + ["- " + x for x in e["facts"]] + [""]
        with open(p(blind, "batch_%d.md" % (i + 1)), "w", encoding=ENC, newline="\n") as f:
            f.write("\n".join(L))
    pack_sha = {f: v2.file_sha(p(blind, f)) for f in sorted(os.listdir(blind))}
    ir.dump_json(p(out, "pack.lock.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                            "key_sha256": v2.file_sha(p(out, "key.json")),
                                            "batches": [[e["q"] for e in part] for part in parts],
                                            "files": len(pack_sha), "pack_sha256": ir.sha(pack_sha)})
    print("пакет: %d пар, %d файлов, партий %d" % (n, len(pack_sha), len(parts)))


def read_by_judge(out, lock):
    """q -> [взятые ярлыки судьи партии] по порядку партий; формат проверяется как в первом пересуде."""
    res, bad = defaultdict(list), []
    for i, qs in enumerate(lock["batches"]):
        fn = p(out, "answers", "judge_%d.tsv" % (i + 1))
        got = defaultdict(dict)
        if os.path.exists(fn):
            for r in ir.read_tsv(fn):
                q, lab, cf = (r.get("q") or "").strip(), (r.get("label") or "").strip().upper(), \
                    (r.get("confidence") or "").strip().lower()
                if q not in qs or lab not in tx.LABELS or (lab != "UNSURE" and cf not in tx.CONF):
                    bad.append("judge_%d %s: %s %s" % (i + 1, q, lab, cf))
                    continue
                prev = got[q].get(lab)
                if prev is None or tx.CONF.index(cf if cf in tx.CONF else "low") < \
                        tx.CONF.index(prev if prev in tx.CONF else "low"):
                    got[q][lab] = cf or "low"
        for q in qs:
            res[q].append({"judge": i + 1, "raw": dict(got.get(q, {})), "taken": tx.truth_of(got.get(q, {})),
                           "answered": q in got})
    return res, bad


# ---------------------------------------------------------------- 1. второй судья: отбор

def authority(ctx, mcd, a, b):
    import routing_model_v8 as v8
    if b.upper() in ctx.ix.exact(a) or b.upper() in ctx.ix.mirror(a):
        return "byte"
    if any(x["relative"].upper() == b.upper() for x in v8.facts(mcd, a)) or \
            any(x["relative"].upper() == a.upper() for x in v8.facts(mcd, b)):
        return "mcd"
    return ""


def do_second_select(out=OUT):
    if os.path.exists(p(out, "answers")) and os.listdir(p(out, "answers")):
        raise SystemExit("ответы уже есть - отбор не перестраивается")
    R = ir.load_json(p(tx.OUT, "report.json"))
    key1 = ir.load_json(p(tx.OUT, "blind_key.json"))
    rep, pairs, h, sha, found, ctl, keys = tx.v3_inputs()
    if sha != key1["h8_sha256"]:
        raise SystemExit("holdout V8 изменился")
    rp = tx.ref_pairs_60(keys, pairs)
    p60 = {pk(a, b) for a, b, _r in rp}
    struct60 = {pk(a, b) for a, b, rel in rp if rel == "STRUCTURAL_RELATION"}
    fires = {}
    for e in found["edges"]:
        if e["detector"] == "MIRROR":
            fires[pk(e["source"], e["target"])] = e["type"]
    for r in ctl["pairs"]:
        for c in r["claims"]:
            for e in c["support"]:
                if e["detector"] == "MIRROR":
                    fires[pk(r["asset_id"], r["relative"])] = e["type"]
    want = {"MIRRORED_RECOLOR": {"MIRRORED_VARIANT_PEER"}, "NEAR_RECOLOR": {"RECOLOR_PEER", "DERIVED"}}
    items = []
    for x in R["adjudication"]:
        k = pk(x["a"], x["b"])
        why = []
        taken = set(x["taken"])
        if x["old"] in tx.OLD_REF and (not taken or not x["agrees_old"]):
            why.append("judge1_vs_old" if taken else "judge1_untaken")
        if k in p60 and (k in struct60 or "COMPOSITE" in taken):
            why.append("composite_denominator")
        typ = fires.get(k)
        if typ and taken and not (taken & want[typ]):
            why.append("mirror_subtype")
        if why:
            items.append({"first_q": x["q"], "a": x["a"], "b": x["b"], "why": why, "old": x["old"],
                          "first_tags": x["tags"], "in_60": k in p60})
    lst = sorted(items, key=lambda it: order(it["a"] + "|" + it["b"], "truth2"))
    for n, it in enumerate(lst, 1):
        it["q"] = "S%03d" % n
        if order("swap" + it["q"], "truth2")[0] in "01234567":
            it["a"], it["b"] = it["b"], it["a"]
    key = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "ADJUDICATED_TRUTH_V2",
           "first_report_created": R["created"], "first_key_created": key1["created"], "h8_sha256": sha,
           "rules": {"select": "judge1_vs_old | judge1_untaken | composite_denominator (60) | mirror_subtype",
                     "batches": SECOND_BATCHES, "taken": tx.TAKEN},
           "why": dict(Counter(w for it in lst for w in it["why"])), "items": lst}
    os.makedirs(out, exist_ok=True)
    ir.dump_json(p(out, "key.json"), key)
    print("пар второму судье: %d" % len(lst))
    for w, n in sorted(key["why"].items()):
        print("  %-22s %d" % (w, n))


def do_second_pack(out=OUT):
    key = ir.load_json(p(out, "key.json"))
    write_pack(out, key["items"], SECOND_BATCHES, "truth2")


# ---------------------------------------------------------------- 2. истина v2

def truth_v2(out=OUT):
    """pair -> (существование, закрытые, открытые, откуда) для 60 и контроля."""
    import routing_model_v8 as v8
    key = ir.load_json(p(out, "key.json"))
    lock = ir.load_json(p(out, "pack.lock.json"))
    j2, bad = read_by_judge(out, lock)
    key1 = ir.load_json(p(tx.OUT, "blind_key.json"))
    ans1, _bad1 = tx.read_answers(tx.OUT)
    rep, pairs, h, sha, found, ctl, keys = tx.v3_inputs()
    rp = tx.ref_pairs_60(keys, pairs)
    old = {pk(a, b): rel for a, b, rel in rp}
    for r in ctl["pairs"]:
        old.setdefault(pk(r["asset_id"], r["relative"]), r["ref"])
    ctx = v3.Ctx(index=v2.load_index(v2.OUT))
    mcd = v8.Mcd(ctx.world)
    second = {pk(it["a"], it["b"]): it for it in key["items"]}
    first = {pk(it["a"], it["b"]): it["q"] for it in key1["items"]}
    T, rows = {}, []
    for k, rel in old.items():
        if rel not in tx.OLD_REF:
            continue
        a, b = sorted(k)
        if k in second:
            it = second[k]
            js = j2.get(it["q"], [])
            jj2 = js[0]["taken"] if js else set()
            jj1 = tx.truth_of(ans1.get(first[k], {}))
            au = authority(ctx, mcd, a, b)
            ex, closed, opn = combine_pair(jj1, jj2, bool(au))
            T[k] = (ex, closed, opn, "two_judges" + ("+" + au if au else ""))
            rows.append({"q": it["q"], "first_q": first[k], "a": it["a"], "b": it["b"], "why": it["why"],
                         "old": rel, "judge1": sorted(jj1), "judge2": sorted(jj2), "authority": au,
                         "existence": ex, "closed": sorted(closed), "open": sorted(opn)})
        elif k in first:
            jj1 = tx.truth_of(ans1.get(first[k], {}))
            ex, closed, opn = combine_with_old(jj1, rel)
            T[k] = (ex, closed, opn, "judge1+old")
        else:
            ref = tx.OLD_REF[rel]
            T[k] = ("NONE", {"NONE"}, set(), "old") if ref == {"NONE"} else \
                ("RELATED", set(ref) if len(ref) == 1 else set(), set() if len(ref) == 1 else set(ref), "old")
    for k, it in second.items():                  # без прежнего эталона (зеркальный подтип) - в отчёт, не в истину
        if k in T:
            continue
        a, b = sorted(k)
        js = j2.get(it["q"], [])
        jj2 = js[0]["taken"] if js else set()
        jj1 = tx.truth_of(ans1.get(first[k], {}))
        au = authority(ctx, mcd, a, b)
        ex, closed, opn = combine_pair(jj1, jj2, bool(au))
        rows.append({"q": it["q"], "first_q": first[k], "a": it["a"], "b": it["b"], "why": it["why"], "old": "-",
                     "judge1": sorted(jj1), "judge2": sorted(jj2), "authority": au, "existence": ex,
                     "closed": sorted(closed), "open": sorted(opn)})
    return T, rows, bad, j2


def do_combine(out=OUT):
    T, rows, bad, j2 = truth_v2(out)
    missing = [q for q, js in j2.items() if not all(j["answered"] for j in js)]
    st = Counter((t[0], "subtype_open" if t[0] == "RELATED" and not t[1] else "") for t in T.values())
    src = Counter(t[3].split("+")[0] for t in T.values())
    agree = Counter()
    for r in rows:
        e1, e2 = tx.existence_class(set(r["judge1"])), tx.existence_class(set(r["judge2"]))
        agree["existence_same" if e1 == e2 else "existence_diff"] += 1
        agree["subtype_closed" if r["closed"] and not r["open"] else
              "subtype_partly" if r["closed"] else "subtype_open"] += 1
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "ADJUDICATED_TRUTH_V2",
           "missing": missing, "bad_rows": bad, "pairs": len(T), "status": {"%s %s" % k: v for k, v in st.items()},
           "source": dict(src), "second_judge": dict(agree), "rows": rows,
           "truth": [{"a": sorted(k)[0], "b": sorted(k)[1], "existence": t[0], "closed": sorted(t[1]),
                      "open": sorted(t[2]), "source": t[3]} for k, t in sorted(T.items(), key=lambda kv: sorted(kv[0]))]}
    ir.dump_json(p(out, "truth_v2.json"), res)
    L = ["# ADJUDICATED_TRUTH_V2 - истина CLOSED / OPEN", "",
         "Нет ответа второго судьи: %s; строк с ошибкой формата: %d." % (", ".join(missing) or "нет", len(bad)), "",
         "Пар в истине: %d. Состояние: %s. Откуда: %s." % (len(T), res["status"], res["source"]), "",
         "Второй судья (%d пар): %s." % (len(rows), res["second_judge"]), "",
         "| q | A | B | почему | прежний | судья 1 | судья 2 | MCD/байты | существование | закрыто | открыто |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["q"]):
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["q"], r["a"], r["b"], ", ".join(r["why"]), r["old"], "/".join(r["judge1"]) or "-",
            "/".join(r["judge2"]) or "-", r["authority"] or "-", r["existence"], "/".join(r["closed"]) or "-",
            "/".join(r["open"]) or "-"))
    with open(p(out, "truth_v2.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("истина v2: %s; второй судья %s" % (res["status"], res["second_judge"]))


# ---------------------------------------------------------------- 3. зеркальная проверка вслепую

def mirror_exclude():
    """Кадры первого пакета, 60 и контроля - новая выборка их не берёт."""
    key1 = ir.load_json(p(tx.OUT, "blind_key.json"))
    rep, pairs, h, sha, found, ctl, keys = tx.v3_inputs()
    ex = {k.upper() for k in keys}
    for it in key1["items"]:
        ex |= {it["a"].upper(), it["b"].upper()}
    for r in ctl["pairs"]:
        ex |= {r["asset_id"].upper(), r["relative"].upper()}
    for e in found["edges"]:
        ex |= {e["source"].upper(), e["target"].upper()}
    return ex


def do_mirror_select(out=MOUT):
    if os.path.exists(p(out, "answers")) and os.listdir(p(out, "answers")):
        raise SystemExit("ответы уже есть - отбор не перестраивается")
    ctx = v3.Ctx(index=v2.load_index(v2.OUT), masks=v3.load_masks(v3.OUT))
    excl = mirror_exclude()
    used, setpairs = set(excl), set()
    fires, negs = [], []
    srcs = sorted(ctx.masks.keys, key=lambda k: order(k, "mirror1"))
    seen = 0
    t0 = time.time()
    for a in srcs:
        if len(fires) >= M_FIRES and len(negs) >= M_NEGS or seen >= M_SOURCES:
            break
        if a in used:
            continue
        seen += 1
        cls_a = {a} | ctx.ix.exact(a) | ctx.ix.mirror(a)
        if cls_a & excl:
            continue
        A = ctx.rgba(a)
        if A is None:
            continue
        m = A[..., 3] > 0
        if m.shape != ctx.masks.shape:
            continue
        direct, mirr = ctx.masks.iou(m), ctx.masks.iou(m[:, ::-1])
        skip = cls_a | ctx.ix.same_mask(a)
        fire, hard = None, None
        for i in np.argsort(-mirr):
            if mirr[i] < tx.MIRROR_NEG_IOU:
                break
            b = ctx.masks.keys[i]
            if b in skip or b in used or direct[i] >= v3.GEO:
                continue
            if ({b} | ctx.ix.exact(b) | ctx.ix.mirror(b)) & excl:
                continue
            sp = frozenset((split(a)[0], split(b)[0]))
            if mirr[i] >= v3.GEO:
                sc, why = v3.recolor_test(ctx, a, b, True)
                if sc and fire is None and sp not in setpairs:
                    fire = (b, sc, sp)
                elif not sc and hard is None:
                    hard = (b, "mirrored silhouette %.3f, %s" % (mirr[i], why))
            elif hard is None:
                hard = (b, "mirrored silhouette %.3f" % mirr[i])
            if fire and hard:
                break
        if fire and len(fires) < M_FIRES:
            b, sc, sp = fire
            fires.append({"a": a, "b": b, "kind": "fire", "scores": sc})
            setpairs.add(sp)
            used |= {a, b}
        elif hard and len(negs) < M_NEGS and (len(negs) < len(fires) or len(fires) >= M_FIRES):
            b, why = hard
            negs.append({"a": a, "b": b, "kind": "negative", "why": why})
            used |= {a, b}
        if seen % 500 == 0:
            print("просмотрено %d: срабатываний %d, отрицательных %d, %.0f с" % (seen, len(fires), len(negs),
                                                                                time.time() - t0), flush=True)
    lst = sorted(fires + negs, key=lambda it: order(it["a"] + "|" + it["b"], "mirror1"))
    for n, it in enumerate(lst, 1):
        it["q"] = "M%03d" % n
        if order("swap" + it["q"], "mirror1")[0] in "01234567":
            it["a"], it["b"] = it["b"], it["a"]
    key = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "MIRRORED_RECOLOR_BLIND_V1",
           "rules": {"fires": M_FIRES, "negatives": M_NEGS, "sources_max": M_SOURCES, "judges": M_JUDGES,
                     "batches": M_BATCHES, "gate": M_GATE, "neg_iou": tx.MIRROR_NEG_IOU, "geo": v3.GEO,
                     "one_fire_per_set_pair": True, "frames_used_once": True,
                     "excluded_frames": len(excl)},
           "sources_seen": seen, "fires": len(fires), "negatives": len(negs), "items": lst}
    os.makedirs(out, exist_ok=True)
    ir.dump_json(p(out, "key.json"), key)
    print("зеркальная проверка: срабатываний %d, отрицательных %d, просмотрено %d" % (len(fires), len(negs), seen))


def do_mirror_pack(out=MOUT):
    key = ir.load_json(p(out, "key.json"))
    write_pack(out, key["items"], M_BATCHES, "mirror1", judges_per_item=M_JUDGES)


def do_mirror_report(out=MOUT):
    key = ir.load_json(p(out, "key.json"))
    lock = ir.load_json(p(out, "pack.lock.json"))
    js, bad = read_by_judge(out, lock)
    ctx = v3.Ctx(index=v2.load_index(v2.OUT))
    import routing_model_v8 as v8
    mcd = v8.Mcd(ctx.world)
    rows = []
    for it in key["items"]:
        jj = js.get(it["q"], [])
        t1 = jj[0]["taken"] if jj else set()
        t2 = jj[1]["taken"] if len(jj) > 1 else set()
        au = authority(ctx, mcd, it["a"], it["b"])
        ex, closed, opn = combine_pair(t1, t2, bool(au))
        rows.append({"q": it["q"], "a": it["a"], "b": it["b"], "kind": it["kind"], "judge1": sorted(t1),
                     "judge2": sorted(t2), "authority": au, "existence": ex, "closed": sorted(closed),
                     "open": sorted(opn)})
    # подтип MIRRORED_RECOLOR закрывается по самому ярлыку, не по группе: MIRRORED_VARIANT_PEER у обоих - да,
    # ни у одного - нет, у одного - OPEN (RECOLOR_PEER той же группы ответа «отражено ли» не даёт)
    for r in rows:
        m1, m2 = "MIRRORED_VARIANT_PEER" in r["judge1"], "MIRRORED_VARIANT_PEER" in r["judge2"]
        r["mirrored_subtype"] = "OPEN" if r["existence"] != "RELATED" or m1 != m2 else ("yes" if m1 else "no")
    f = [r for r in rows if r["kind"] == "fire"]
    fe = [r for r in f if r["existence"] != "OPEN"]
    rel = [r for r in fe if r["existence"] == "RELATED"]
    ft = [r for r in rel if r["mirrored_subtype"] != "OPEN"]
    mir = [r for r in ft if r["mirrored_subtype"] == "yes"]
    n = [r for r in rows if r["kind"] == "negative"]
    ne = [r for r in n if r["existence"] != "OPEN"]
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "MIRRORED_RECOLOR_BLIND_V1", "bad_rows": bad,
           "missing": [q for q, j in js.items() if not all(x["answered"] for x in j)],
           "fires": len(f), "fires_existence_closed": len(fe), "fires_related": len(rel),
           "existence_precision": rate(len(rel), len(fe)),
           "fires_subtype_closed": len(ft), "fires_mirrored": len(mir), "subtype_precision": rate(len(mir), len(ft)),
           "fires_existence_open": len(f) - len(fe), "fires_subtype_open": len(rel) - len(ft),
           "negatives": len(n), "negatives_closed": len(ne),
           "negatives_related": sum(r["existence"] == "RELATED" for r in ne),
           "negatives_mirrored": sum(r["mirrored_subtype"] == "yes" for r in ne),
           "judge_agreement_existence": rate(sum(tx.existence_class(set(r["judge1"])) ==
                                                 tx.existence_class(set(r["judge2"])) for r in rows), len(rows)),
           "rows": rows}
    ep, sp = res["existence_precision"], res["subtype_precision"]
    res["type_strong_allowed"] = bool(ep is not None and sp is not None and ep >= M_GATE and sp >= M_GATE)
    ir.dump_json(p(out, "report.json"), res)
    L = ["# MIRRORED_RECOLOR_BLIND_V1 - слепая проверка без отражённого кадра", "",
         "Срабатываний %d: существование закрыто %d, связь %d - precision %s; подтип закрыт %d, зеркальный %d - "
         "precision %s. OPEN: существование %d, подтип %d." % (
             len(f), len(fe), len(rel), tx.f2(ep), len(ft), len(mir), tx.f2(sp), res["fires_existence_open"],
             res["fires_subtype_open"]), "",
         "TYPE_STRONG разрешён: **%s** (нужно >= %.2f по обоим)." % ("да" if res["type_strong_allowed"] else "нет", M_GATE),
         "", "Отрицательных %d: закрыто %d, связь %d, зеркальный %d. Согласие судей по существованию %s." % (
             len(n), len(ne), res["negatives_related"], res["negatives_mirrored"],
             tx.f2(res["judge_agreement_existence"])), "",
         "| q | вид | A | B | судья 1 | судья 2 | MCD/байты | существование | отражено | закрыто | открыто |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["q"], r["kind"], r["a"], r["b"], "/".join(r["judge1"]) or "-", "/".join(r["judge2"]) or "-",
            r["authority"] or "-", r["existence"], r["mirrored_subtype"], "/".join(r["closed"]) or "-",
            "/".join(r["open"]) or "-"))
    with open(p(out, "report.md"), "w", encoding=ENC, newline="\n") as f2:
        f2.write("\n".join(L) + "\n")
    print("зеркало вслепую: существование %s, подтип %s, TYPE_STRONG %s" % (tx.f2(ep), tx.f2(sp),
                                                                          res["type_strong_allowed"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["second-select", "second-pack", "combine", "mirror-select", "mirror-pack",
                                    "mirror-report"])
    ap.add_argument("--out")
    a = ap.parse_args()
    fn = {"second-select": do_second_select, "second-pack": do_second_pack, "combine": do_combine,
          "mirror-select": do_mirror_select, "mirror-pack": do_mirror_pack, "mirror-report": do_mirror_report}[a.cmd]
    out = a.out or (MOUT if a.cmd.startswith("mirror") else OUT)
    os.makedirs(out, exist_ok=True)
    fn(out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
