#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RELATION_TAXONOMY_ADJUDICATION - схема подтипов связи и независимый слепой пересуд (специалист 02.10). CPU, чтение.

V3_PREP (probes/relation-discovery-v3-prep) показал: существование связи почти не ошибается (1.00 на 60, 0.99 на
контроле), опасных 0. Упёрлись в схему классов: эталон знает один смысл на пару и смешивает «совместную часть
одного предмета» с «противоположной частью того же типа конструкции». Детектор не трогаем (пороги V3 те же), меняем:

  1. Несколько истинных подтипов на пару. Анимация + перекраска - не спор: оба довода TYPE_STRONG, в производстве
     главная анимация - довод перекраски на паре с анимацией STRONG остаётся уликой материала и роли вывода не даёт
     (production = False). Спор анимации или перекраски с состоянием и спор направления - как в V3.
  2. Новые определения (JUDGE.md): COMPOSITE - совместные части одного размещённого экземпляра, нужно доказательство
     сборки; STRUCTURAL_COUNTERPART, MIRRORED_VARIANT_PEER, ATTACHMENT_CANDIDATE - отдельно от него.
  3. Слепой пересуд независимым агентом-судьёй: 12 пар «структура» эталона 60, спорные пары (несколько доводов,
     тип V3 разошёлся с эталоном, связь на паре NONE), все срабатывания MIRRORED_RECOLOR_V1 / NEAR_RECOLOR и похожие
     отрицательные контроли, пары согласия V3 с эталоном - вперемешку. Судья не видит детекторов, уверенности,
     прежнего эталона и групп отбора. Ответы medium и high берутся, low и UNSURE - нет (правило до ответов).

Пересчёт: истина пары - ответ судьи, где он есть, иначе прежний эталон, переведённый в ярлыки (STRUCTURAL_RELATION
прежнего эталона допускает COMPOSITE или MODULAR_SECTION, как V3). Довод верен, если его группа допускается хоть
одним ярлыком истины. Прежний эталон и замороженные holdout не переписываются; V3 и его отчёт не меняются.

    py -3.13 tools/hdart/relation_taxonomy.py select   пары для судьи -> blind_key.json (ключ, вне пакета)
    py -3.13 tools/hdart/relation_taxonomy.py pack     слепой пакет blind/: картинки, факты, JUDGE.md, batch_N.md
    py -3.13 tools/hdart/relation_taxonomy.py report   ответы answers/judge_N.tsv -> report.json, report.md
"""
import argparse
import hashlib
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

ENC = ir.ENC
OUT = os.path.join(ir.PROBES, "relation-taxonomy-adjudication")
V3OUT = v3.OUT
p, split, rate = v2.p, v2.split, v2.rate
STRONG, CAND, T_STRONG, T_OPEN = v3.STRONG, v3.CAND, v3.T_STRONG, v3.T_OPEN
BINDING = v2.BINDING

# ---------------------------------------------------------------- схема ярлыков (до ответов)

LABELS = ("EXACT_COPY", "RECOLOR_PEER", "MIRRORED_VARIANT_PEER", "DERIVED", "STATE_VARIANT", "ANIMATION_FAMILY",
          "COMPOSITE", "STRUCTURAL_COUNTERPART", "MODULAR_SECTION", "ATTACHMENT_CANDIDATE", "NONE", "UNSURE")
CONF = ("high", "medium", "low")
TAKEN = ("high", "medium")                         # как REFERENCE_ADJUDICATION_V1: low и UNSURE не берутся
# группа довода -> ярлыки истины, при которых довод верен
GROUP_OK = {"derived": {"EXACT_COPY", "RECOLOR_PEER", "MIRRORED_VARIANT_PEER", "DERIVED"},
            "state": {"STATE_VARIANT"}, "animation": {"ANIMATION_FAMILY"}, "composite": {"COMPOSITE"},
            "modular": {"MODULAR_SECTION"}}
# прежний эталон -> ярлыки (там, где судьи нет); STRUCTURAL_RELATION прежнего эталона - составной или модуль
OLD_REF = {"RECOLOR_OF": {"RECOLOR_PEER"}, "DERIVED_FROM": {"DERIVED"}, "STATE_VARIANT_OF": {"STATE_VARIANT"},
           "ANIMATION_FRAME_OF": {"ANIMATION_FAMILY"}, "STRUCTURAL_RELATION": {"COMPOSITE", "MODULAR_SECTION"},
           "NONE": {"NONE"}}
# полнота: ярлык истины -> группа довода, которая его находит (нет группы - только существование)
LABEL_GROUP = {"EXACT_COPY": "derived", "RECOLOR_PEER": "derived", "MIRRORED_VARIANT_PEER": "derived",
               "DERIVED": "derived", "STATE_VARIANT": "state", "ANIMATION_FAMILY": "animation",
               "COMPOSITE": "composite", "MODULAR_SECTION": "modular"}
DERIVED_LABELS = ("RECOLOR_PEER", "MIRRORED_VARIANT_PEER", "DERIVED")
RECOLOR_TYPES = ("RECOLOR_PEER", "RECOLOR_OF", "MATERIAL_VARIANT_OF")
# состав пакета (до ответов)
AGREE_N = {"derived": 5, "state": 3, "animation": 3, "composite": 3, "none": 6}
MIRROR_NEG_MAX, MIRROR_NEG_PER = 36, 2
MIRROR_NEG_IOU = 0.90                              # 0.95 дало 8 пар на 36 мест - расширено до ответов
N_BATCHES = 4
GATES = {"dangerous": 0, "existence_precision": 0.95, "composite_recall": 0.70, "derived_discovery": 0.70,
         "state_discovery": 0.70, "typed_auto_precision": 0.95}


def order(s):
    return hashlib.sha256(("taxonomy|" + s).encode()).hexdigest()


def pk(a, b):
    return frozenset((a.upper(), b.upper()))


# ---------------------------------------------------------------- 1. политика типов: несколько истинных подтипов

class TaxClaims(v3.Claims):
    """Как v3.Claims, но анимация и перекраска на одной паре не спорят: оба TYPE_STRONG, перекраска при анимации
    STRONG - улика, production = False. Остальной спор (состояние против вывода, направление) - как V3."""

    def finalize(self):
        super().finalize()
        pairs = defaultdict(list)
        for c in self.claims.values():
            pairs[frozenset(c["pair"])].append(c)
        for cs in pairs.values():
            anim = [c for c in cs if c["group"] == "animation"]
            for c in cs:
                c["production"] = True
                c["coexists"] = []
            if not anim:
                continue
            rec = [c for c in cs if c["group"] == "derived" and not c["exact"] and
                   all(e["type"] in RECOLOR_TYPES for e in c["support"] if e["level"] in BINDING)]
            spoken = {c["group"] for c in cs if c["group"] in v3.DERIVATION and not c["exact"]}
            rest = spoken - ({"derived"} if rec else set())
            for c in cs:
                if c not in anim and c not in rec:
                    continue
                why = [w for w in c["type_open_why"] if not w.startswith("спор типа")]
                if len(rest) > 1:
                    why.append("спор типа: %s" % "/".join(sorted(rest)))
                c["type_open_why"] = why
                c["type_level"] = T_OPEN if why else T_STRONG
            if any(a["existence"] == STRONG for a in anim):
                for c in rec:
                    c["production"] = False
                    c["coexists"] = ["ANIMATION_FAMILY"]
        return self


def pipe_roles(C, a):
    """Как v3.pipe_roles, без доводов-улик (production = False)."""
    A = a.upper()
    roles = {x["type"] for x in C.self_roles.get(A, []) if x["level"] in BINDING}
    roles |= {v2.PIPE_ROLE.get(c["type"], c["type"]) for c in C.of(a)
              if c["existence"] == STRONG and c["type_level"] == T_STRONG and c.get("production", True) and
              (c["type"] in v3.SYMMETRIC or c["source"] == A)}
    return sorted(roles) or ["CANONICAL"]


def auto_claim(c):
    return c["existence"] == STRONG and c["type_level"] == T_STRONG and c.get("production", True)


def groups_of(C, a, mode):
    if mode != "auto":
        return v3.groups_of(C, a, mode)
    A = a.upper()
    gs = {v2.GROUP[x["type"]] for x in C.self_roles.get(A, []) if x["level"] in BINDING and x["type"] in v2.GROUP}
    gs |= {c["group"] for c in C.of(a) if auto_claim(c)}
    return sorted(gs) or ["canonical"]


# ---------------------------------------------------------------- 2. входы: доводы 60 и контроля

def v3_inputs():
    rep, _ref, pairs, h, sha = v2.h8_inputs()
    found = ir.load_json(p(V3OUT, "relations_v3.json"))
    ctl = ir.load_json(p(V3OUT, "controls.json"))
    keys = [x["asset_id"] for x in h["items"]]
    return rep, pairs, h, sha, found, ctl, keys


def claims_60(rep, found, cls):
    C = v3.claims_from_v8(rep["rows"])
    C.__class__ = cls
    return v3.add_found(C, found).finalize()


def control_claims(ctl, cls):
    """Доводы контроля из controls.json V3 (детекторы не перезапускаются): пара -> Claims."""
    out = {}
    for r in ctl["pairs"]:
        C = cls()
        for c in r["claims"]:
            for e in c["support"]:
                C.add(v2.edge(e["type"], c["source"], c["target"], e["level"], e["detector"], e["rule"], e["evidence"]))
        out[pk(r["asset_id"], r["relative"])] = (r, C.finalize())
    return out


def ref_pairs_60(keys, pairs):
    out, seen = [], set()
    for a in keys:
        for x in pairs.get(a, []):
            k = pk(a, x["relative"])
            if k in seen:
                continue
            seen.add(k)
            out.append((a.upper(), x["relative"].upper(), x["ref_pair_relation"]))
    return out


def outcome_old(c, rel):
    return v3.claim_outcome(c, rel)


# ---------------------------------------------------------------- 3. отбор пар для судьи (до ответов)

def mirror_negatives(ctx, fires, fired_pairs):
    """Похожие отрицательные: тот же исходный кадр, отражённый (или прямой для NEAR) силуэт >= MIRROR_NEG_IOU, тест
    цвета V1 не прошёл или силуэт ниже GEO. Сначала самые трудные (силуэт прошёл, цвет нет), по кругу исходных."""
    by_src = defaultdict(list)
    for a, b, typ in fires:
        by_src[a].append(typ)
    cands = {}
    for a in sorted(by_src, key=order):
        A = ctx.rgba(a)
        if A is None:
            continue
        m = A[..., 3] > 0
        if m.shape != ctx.masks.shape:
            continue
        direct, mirr = ctx.masks.iou(m), ctx.masks.iou(m[:, ::-1])
        skip = {a.upper()} | ctx.ix.exact(a) | ctx.ix.mirror(a) | ctx.ix.same_mask(a)
        hard, soft = [], []
        for flip, arr in ((True, mirr), (False, direct)):
            if not flip and "NEAR_RECOLOR" not in by_src[a]:
                continue
            for i in np.nonzero(arr >= MIRROR_NEG_IOU)[0]:
                b = ctx.masks.keys[i]
                if b in skip or pk(a, b) in fired_pairs or (flip and direct[i] >= v3.GEO):
                    continue
                if arr[i] >= v3.GEO:
                    sc, _why = v3.recolor_test(ctx, a, b, flip)
                    if sc:
                        continue
                    hard.append(b)
                else:
                    soft.append(b)
        cands[a] = sorted(hard, key=lambda b: order(a + b)) + sorted(soft, key=lambda b: order(a + b))
    out, used = [], set()
    for rnd in range(MIRROR_NEG_PER):
        for a in sorted(cands, key=order):
            if len(out) >= MIRROR_NEG_MAX:
                break
            for b in cands[a]:
                if pk(a, b) not in used and pk(a, b) not in fired_pairs:
                    used.add(pk(a, b))
                    out.append((a, b))
                    break
    return out


def do_select(out=OUT):
    if os.path.exists(p(out, "answers")) and os.listdir(p(out, "answers")):
        raise SystemExit("ответы судьи уже есть - отбор не перестраивается")
    rep, pairs, h, sha, found, ctl, keys = v3_inputs()
    C3 = claims_60(rep, found, v3.Claims)
    CC = control_claims(ctl, v3.Claims)
    items = {}

    def add(a, b, tag, src):
        k = pk(a, b)
        if k not in items:
            items[k] = {"a": a.upper(), "b": b.upper(), "tags": [], "source": src}
        if tag not in items[k]["tags"]:
            items[k]["tags"].append(tag)

    rp = ref_pairs_60(keys, pairs)
    agree = defaultdict(list)
    for a, b, rel in rp:
        cs = C3.pair(a, b)
        if rel == "STRUCTURAL_RELATION":
            add(a, b, "structural_ref", "60")
        groups = {c["group"] for c in cs}
        wrong = [c for c in cs if c["type_level"] == T_STRONG and outcome_old(c, rel) == "wrong"]
        if len(groups) > 1:
            add(a, b, "multi_claim", "60")
        if wrong:
            add(a, b, "typed_wrong", "60")
        if rel == "NONE" and any(c["existence"] == STRONG for c in cs):
            add(a, b, "existence_wrong", "60")
        if len(cs) == 1 and cs[0]["type_level"] == T_STRONG and outcome_old(cs[0], rel) == "ok":
            agree[cs[0]["group"]].append((a, b, "60"))
        if rel == "NONE" and not cs:
            agree["none"].append((a, b, "60"))
    for k, (r, C) in CC.items():
        a, b, rel = r["asset_id"], r["relative"], r["ref"]
        cs = list(C.claims.values())
        groups = {c["group"] for c in cs}
        if len(groups) > 1:
            add(a, b, "multi_claim", r["holdout"])
        if any(c["type_level"] == T_STRONG and outcome_old(c, rel) == "wrong" for c in cs):
            add(a, b, "typed_wrong", r["holdout"])
        if rel == "NONE" and any(c["existence"] == STRONG for c in cs):
            add(a, b, "existence_wrong", r["holdout"])
        if len(cs) == 1 and cs[0]["type_level"] == T_STRONG and outcome_old(cs[0], rel) == "ok":
            agree[cs[0]["group"]].append((a, b, r["holdout"]))
        if rel == "NONE" and not cs:
            agree["none"].append((a, b, r["holdout"]))
    for g, n in AGREE_N.items():
        cand = [x for x in agree.get(g, []) if pk(x[0], x[1]) not in items]
        for a, b, src in sorted(cand, key=lambda x: order(x[0] + x[1]))[:n]:
            add(a, b, "agree_" + g, src)
    fires, fired = [], set()
    for e in found["edges"]:
        if e["detector"] == "MIRROR":
            fires.append((e["source"], e["target"], e["type"]))
            fired.add(pk(e["source"], e["target"]))
    for r in ctl["pairs"]:
        for c in r["claims"]:
            for e in c["support"]:
                if e["detector"] == "MIRROR":
                    fires.append((r["asset_id"], r["relative"], e["type"]))
                    fired.add(pk(r["asset_id"], r["relative"]))
    for a, b, typ in fires:
        add(a, b, "mirror_fire_" + ("mr1" if typ == "MIRRORED_RECOLOR" else "nr1"), "detector")
    ctx = v3.Ctx(index=v2.load_index(v2.OUT), masks=v3.load_masks(V3OUT))
    srcs = fires + [(k.upper(), "", "MIRRORED_RECOLOR") for k in keys]       # и кадры 60 - их отражённые соседи
    for a, b in mirror_negatives(ctx, srcs, fired):
        add(a, b, "mirror_negative", "masks")
    lst = sorted(items.values(), key=lambda x: order(x["a"] + "|" + x["b"]))
    for n, it in enumerate(lst, 1):
        it["q"] = "Q%03d" % n
        if order("swap" + it["q"])[0] in "01234567":
            it["a"], it["b"] = it["b"], it["a"]
    key = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "RELATION_TAXONOMY_ADJUDICATION",
           "h8_sha256": sha, "v3_relations_created": found["created"], "v3_controls_created": ctl["created"],
           "rules": {"agree_n": AGREE_N, "mirror_neg_max": MIRROR_NEG_MAX, "mirror_neg_per": MIRROR_NEG_PER,
                     "mirror_neg_iou": MIRROR_NEG_IOU, "taken": TAKEN, "batches": N_BATCHES},
           "tags": dict(Counter(t for it in lst for t in it["tags"])), "items": lst}
    os.makedirs(out, exist_ok=True)
    ir.dump_json(p(out, "blind_key.json"), key)
    print("пар для судьи: %d" % len(lst))
    for t, n in sorted(key["tags"].items()):
        print("  %-24s %d" % (t, n))


# ---------------------------------------------------------------- 4. слепой пакет

DARK = (24, 24, 28)
DIRS = {(1, 0, 0): "x+1 (next cell down-right on screen)", (-1, 0, 0): "x-1 (next cell up-left)",
        (0, 1, 0): "y+1 (next cell down-left)", (0, -1, 0): "y-1 (next cell up-right)"}
TILE = {0: "floor", 1: "west wall", 2: "north wall", 3: "object"}
VIA = {("die", "OUT"): "A's MCD record names B as its destroyed version (Die_MCD)",
       ("die", "IN"): "B's MCD record names A as its destroyed version (Die_MCD)",
       ("alt", "OUT"): "A's MCD record names B as its alternative state (Alt_MCD, e.g. open door)",
       ("alt", "IN"): "B's MCD record names A as its alternative state (Alt_MCD)",
       ("anim", "OUT"): "A's MCD record has B as a later frame of its 8-frame animation",
       ("anim", "IN"): "B's MCD record has A as a later frame of its 8-frame animation"}


def off_text(o):
    if o in DIRS:
        return DIRS[o]
    if o == (0, 0, 0):
        return "same cell, other layer"
    parts = ["%s%+d" % (n, v) for n, v in zip("xyz", o) if v]
    return " ".join(parts) + (" (z is the floor level: +1 = one storey up)" if o[2] else "")


def big(arr, k=4):
    from PIL import Image
    im = Image.new("RGB", (arr.shape[1], arr.shape[0]), DARK)
    im.paste(Image.fromarray(arr, "RGBA"), (0, 0), Image.fromarray(arr, "RGBA"))
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def overlay(A, B, k=4):
    from PIL import Image
    h, w = max(A.shape[0], B.shape[0]), max(A.shape[1], B.shape[1])
    m = np.zeros((h, w, 3), np.uint8)
    m[:A.shape[0], :A.shape[1], 0] = (A[..., 3] > 0) * 220
    m[:B.shape[0], :B.shape[1], 1] = (B[..., 3] > 0) * 220
    return Image.fromarray(m, "RGB").resize((w * k, h * k), Image.NEAREST)


def captioned(im, text):
    from PIL import Image, ImageDraw
    out = Image.new("RGB", (max(im.width, 8 * len(text)), im.height + 16), (14, 14, 16))
    out.paste(im, (0, 16))
    ImageDraw.Draw(out).text((2, 2), text, fill=(230, 230, 230))
    return out


def hrow(ims, gap=8):
    from PIL import Image
    out = Image.new("RGB", (sum(i.width for i in ims) + gap * (len(ims) - 1), max(i.height for i in ims)), (14, 14, 16))
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + gap
    return out


def vstack(ims, gap=10):
    from PIL import Image
    ims = [i for i in ims if i is not None]
    out = Image.new("RGB", (max(i.width for i in ims), sum(i.height for i in ims) + gap * (len(ims) - 1)), (14, 14, 16))
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + gap
    return out


def pair_image(ctx, a, b):
    """A | B | B отражённый | силуэты A и B | силуэты A и отражённого B; ниже - соседние номера в PCK."""
    from PIL import ImageDraw
    A, B = ctx.rgba(a), ctx.rgba(b)
    Bm = np.ascontiguousarray(B[:, ::-1])
    top = hrow([captioned(big(A), "A " + a), captioned(big(B), "B " + b), captioned(big(Bm), "B mirrored"),
                captioned(overlay(A, B), "A red / B green"), captioned(overlay(A, Bm), "A red / B mirrored green")])
    strips = []
    sa, fa = split(a)
    sb, fb = split(b)
    groups = [(sa, sorted({fa, fb}))] if sa == sb else [(sa, [fa]), (sb, [fb])]
    for s, fs in groups:
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
            im = captioned(big(arr, 2), "%d" % f)
            k = "%s:%d" % (s, f)
            col = (255, 40, 40) if k == a.upper() else (40, 220, 40) if k == b.upper() else None
            if col:
                ImageDraw.Draw(im).rectangle((0, 0, im.width - 1, im.height - 1), outline=col, width=3)
            cells.append(im)
        if cells:
            strips.append(captioned(hrow(cells, 4), "PCK %s, neighbouring frame numbers (A red, B green)" % s))
    return vstack([top] + strips)


def coplace(ctx, a, b):
    """Где B стоит рядом с A: сдвиги (A -> B) по местам A, обратная доля по местам B, блоки встречи."""
    pa, pb = ctx.places.of(a), ctx.places.of(b)
    cnt, blocks = Counter(), defaultdict(Counter)
    for t, blk, grid, (x, y, z), _la in pa:
        seen = set()
        for o in v2.OFFSETS:
            for _lb, kb in grid.get((x + o[0], y + o[1], z + o[2]), []):
                if kb == b.upper():
                    seen.add(o)
        for o in seen:
            cnt[o] += 1
            blocks[o][(t, blk)] += 1
    rev = {}
    for o in cnt:
        hit = sum(any(k2 == a.upper() for _l, k2 in grid.get((x - o[0], y - o[1], z - o[2]), []))
                  for _t, _b, grid, (x, y, z), _l in pb)
        rev[o] = hit
    return pa, pb, cnt, rev, blocks


def block_crop(ctx, t, blk, a, b, only=None):
    """Блок с A (красная рамка) и B (зелёная): ближайшая пара их клеток, срез этажа по верхней из двух.
    only - показать место одного кадра (другой в этом блоке, если есть, рамкой не ищется)."""
    from PIL import Image, ImageDraw
    mm, w = ctx.mm, ctx.world
    try:
        _im, ma = mm.render(w, t, blk, None, 1, split(a))
        _im, mb = mm.render(w, t, blk, None, 1, split(b))
    except (Exception, SystemExit):                   # noqa: BLE001 - блок не читается: без этого места
        return None
    if only is not None:
        ma, mb = (ma, []) if only == a else ([], mb)
    if not ma and not mb:
        return None
    best = None
    for x in ma or [None]:
        for y in mb or [None]:
            r = [z[2] for z in (x, y) if z]
            cx = [((q[0] + q[2]) / 2, (q[1] + q[3]) / 2) for q in r]
            d = 0 if len(cx) < 2 else abs(cx[0][0] - cx[1][0]) + abs(cx[0][1] - cx[1][1])
            if best is None or d < best[0]:
                best = (d, x, y)
    _d, x, y = best
    marks = [(m, c) for m, c in ((x, (255, 40, 40)), (y, (40, 220, 40))) if m]
    zmax = max(m[3] for m, _c in marks)
    im, _m = mm.render(w, t, blk, None, 1, None, maxz=zmax)
    x0 = min(m[2][0] for m, _c in marks) - 80
    y0 = min(m[2][1] for m, _c in marks) - 60
    x1 = max(m[2][2] for m, _c in marks) + 80
    y1 = max(m[2][3] for m, _c in marks) + 50
    box = (max(0, x0), max(0, y0), min(im.width, x1), min(im.height, y1))
    k = 3
    crop = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), DARK + (255,))
    crop.alpha_composite(im.crop(box))
    crop = crop.resize((crop.width * k, crop.height * k), Image.NEAREST).convert("RGB")
    d = ImageDraw.Draw(crop)
    for m, c in marks:
        q = m[2]
        d.rectangle(((q[0] - box[0]) * k, (q[1] - box[1]) * k, (q[2] - box[0]) * k, (q[3] - box[1]) * k),
                    outline=c, width=3)
    return captioned(crop, "map %s / %s (storeys above the marked cells hidden)" % (t, blk))


def map_image(ctx, a, b, pa, pb, cnt, blocks):
    shots = []
    if cnt:
        tb = Counter()
        for o in cnt:
            tb.update(blocks[o])
        for (t, blk), _n in tb.most_common(2):
            shots.append(block_crop(ctx, t, blk, a, b))
    else:
        for k, pl in ((a, pa), (b, pb)):
            if pl:
                shots.append(block_crop(ctx, pl[0][0], pl[0][1], a, b, only=k))
    shots = [s for s in shots if s is not None]
    return vstack(shots) if shots else None


def facts(ctx, mcd, a, b):
    import routing_model_v8 as v8
    ia, ib = ctx.st.info(*split(a)), ctx.st.info(*split(b))
    sa, fa = split(a)
    sb, fb = split(b)
    L = ["A = %s, B = %s." % (a, b)]
    L.append("Same PCK set: %s%s." % ("yes" if sa == sb else "no",
                                      ", frame numbers %d and %d (difference %d)" % (fa, fb, abs(fa - fb)) if sa == sb else ""))
    links = [x for x in v8.facts(mcd, a) if x["relative"].upper() == b.upper()]
    if links:
        for x in links:
            L.append("MCD: %s." % VIA.get((x["via"], x["dir"]), x["via"]))
    else:
        L.append("MCD: no die / alt / animation link between A and B.")
    if ia.get("rec") and ib.get("rec"):
        same = (ia["vox"] == ib["vox"]).all()
        mir = (ib["vox"] == ia["vox"].transpose(0, 2, 1)).all()
        L.append("MCD tile type: A %s, B %s. Collision volume (LOFT): %s." % (
            TILE.get(ia["tile_type"], ia["tile_type"]), TILE.get(ib["tile_type"], ib["tile_type"]),
            "identical" if same else "mirror images of each other" if mir else "different"))
    pa, pb, cnt, rev, blocks = coplace(ctx, a, b)

    def where(pl):
        return "%d cells in %d map blocks of %d terrains" % (len(pl), len({(x[0], x[1]) for x in pl}),
                                                           len({x[0] for x in pl}))
    L.append("Placed on maps: A %s; B %s." % (where(pa) if pa else "nowhere", where(pb) if pb else "nowhere"))
    if cnt:
        for o, n in cnt.most_common(4):
            L.append("Together: B at %s from A in %d of A's %d placements; A at the reverse offset in %d of B's %d "
                     "placements; %d map blocks." % (off_text(o), n, len(pa), rev[o], len(pb), len(blocks[o])))
    else:
        L.append("Together: A and B are never in the same or adjacent cells on any map.")
    return L, (pa, pb, cnt, blocks)


JUDGE = """# Judging pairs of game sprites (blind)

You are an independent judge. Each item shows two 32x40 isometric sprites, A and B, from the game X-Piratez
(OpenXcom). Decide **what relation, if any, holds between A and B**, using only the pictures and the facts in your
batch file. Read only the files named in your batch file and this file. Do not open any other file in the
repository: other files contain answers of other tools, and your judgement must be independent of them.

Each item has:
- `Qnnn_pair.png`: A, B, B mirrored, silhouette overlays (A red, B green), and neighbouring frame numbers in the
  same sprite file (PCK). Frames of one multi-cell object often have consecutive numbers.
- `Qnnn_map.png` (if any): a crop of a map block with A outlined red and B outlined green. If A and B are adjacent
  on maps, the crop shows them together; otherwise it shows where they stand.
- facts: MCD engine links (die = destroyed version, alt = alternative state such as an open door, animation =
  frames of one 8-frame loop), collision volume, where and how often A and B stand next to each other.

## Labels (more than one may hold for the same pair)

- **EXACT_COPY**: the pixels are identical (possibly in another sprite file).
- **RECOLOR_PEER**: the same drawing in other colours or material; same orientation.
- **MIRRORED_VARIANT_PEER**: the same thing drawn as a left-right mirror image; colours or shading may differ.
- **DERIVED**: B is an edited version of A or vice versa (a part added, removed or changed), not just a recolour
  or mirror, and not a damaged state.
- **STATE_VARIANT**: another state of the same object: destroyed or damaged, open or closed, on or off.
- **ANIMATION_FAMILY**: frames of one animation loop of the same object.
- **COMPOSITE**: A and B are joint components of **one placed instance** of one object (two halves of one bed, the
  cells of one vehicle, the tiles of one big machine). Map adjacency is not the only possible proof, but there must
  be evidence that they are assembled together: they stand at a fixed offset on maps, consecutive frame numbers
  with shapes that continue each other, a known multi-cell layout, a shared footprint. Without such evidence it is
  not COMPOSITE.
- **STRUCTURAL_COUNTERPART**: the same type of construction in a complementary or opposite role (left and right
  side of a hull, start and end of a rail, opposite corners), without evidence that they are parts of one
  placed instance. Can hold together with MIRRORED_VARIANT_PEER.
- **MODULAR_SECTION**: both are discrete construction sections that occupy their own slot and are used in several
  different assemblies with different neighbours, keeping their identity (wall or hull sections that combine
  freely). Repeating a copy of itself next to itself is not enough.
- **ATTACHMENT_CANDIDATE**: one is regularly placed against the other (a chair at a table, a fixture on a wall),
  but they are separate objects.
- **NONE**: no relation beyond looking somewhat alike.
- **UNSURE**: you cannot tell from what is shown.

Confidence per label: `high` (clear from the evidence), `medium` (likely), `low` (a guess).

## Answer

Write a UTF-8 tab-separated file at the path named in your batch file, header
`q	label	confidence	evidence`, one row per label you assign (several rows for the same q if several labels
hold). Every q of your batch must have at least one row. `evidence`: one short sentence, what in the pictures or
facts decided it. No tabs or line breaks inside a field.
"""


def do_pack(out=OUT):
    if os.path.exists(p(out, "answers")) and os.listdir(p(out, "answers")):
        raise SystemExit("ответы судьи уже есть - пакет не перестраивается")
    import routing_model_v8 as v8
    key = ir.load_json(p(out, "blind_key.json"))
    blind = p(out, "blind")
    os.makedirs(blind, exist_ok=True)
    ctx = v3.Ctx(index=v2.load_index(v2.OUT))
    mcd = v8.Mcd(ctx.world)
    with open(p(blind, "JUDGE.md"), "w", encoding=ENC, newline="\n") as f:
        f.write(JUDGE)
    entries = []
    t0 = time.time()
    for it in key["items"]:
        q, a, b = it["q"], it["a"], it["b"]
        L, (pa, pb, cnt, blocks) = facts(ctx, mcd, a, b)
        pair_image(ctx, a, b).save(p(blind, q + "_pair.png"))
        mi = map_image(ctx, a, b, pa, pb, cnt, blocks)
        files = [q + "_pair.png"]
        if mi is not None:
            mi.save(p(blind, q + "_map.png"))
            files.append(q + "_map.png")
        entries.append({"q": q, "files": files, "facts": L})
        print("%s %s %s %.0f с" % (q, a, b, time.time() - t0), flush=True)
    os.makedirs(p(out, "answers"), exist_ok=True)
    n = len(entries)
    for i in range(N_BATCHES):
        part = entries[i * n // N_BATCHES:(i + 1) * n // N_BATCHES]
        ans = os.path.abspath(p(out, "answers", "judge_%d.tsv" % (i + 1))).replace(os.sep, "/")
        L = ["# Batch %d of %d: %d pairs" % (i + 1, N_BATCHES, len(part)), "",
             "Instructions and label definitions: JUDGE.md in this folder. Write your answers to:", "",
             "    " + ans, "", "Images are in this folder.", ""]
        for e in part:
            L += ["## " + e["q"], "", "Images: " + ", ".join(e["files"]), ""] + ["- " + x for x in e["facts"]] + [""]
        with open(p(blind, "batch_%d.md" % (i + 1)), "w", encoding=ENC, newline="\n") as f:
            f.write("\n".join(L))
    pack_sha = {f: v2.file_sha(p(blind, f)) for f in sorted(os.listdir(blind))}
    ir.dump_json(p(out, "pack.lock.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                            "blind_key_sha256": v2.file_sha(p(out, "blind_key.json")),
                                            "files": len(pack_sha), "pack_sha256": ir.sha(pack_sha)})
    print("пакет: %d пар, %d файлов, партий %d" % (n, len(pack_sha), N_BATCHES))


# ---------------------------------------------------------------- 5. ответы и истина

def read_answers(out=OUT):
    """q -> {ярлык: уверенность} из answers/judge_*.tsv; проверка формата."""
    ans, bad = defaultdict(dict), []
    d = p(out, "answers")
    for fn in sorted(os.listdir(d)) if os.path.exists(d) else []:
        if not fn.endswith(".tsv"):
            continue
        for r in ir.read_tsv(p(d, fn)):
            q, lab, cf = (r.get("q") or "").strip(), (r.get("label") or "").strip().upper(), \
                (r.get("confidence") or "").strip().lower()
            if lab not in LABELS or (lab != "UNSURE" and cf not in CONF):
                bad.append("%s %s: %s %s" % (fn, q, lab, cf))
                continue
            prev = ans[q].get(lab)
            if prev is None or CONF.index(cf if cf in CONF else "low") < CONF.index(prev if prev in CONF else "low"):
                ans[q][lab] = cf or "low"
    return ans, bad


def truth_of(labels):
    """Ярлыки, которые берутся: medium и high, без UNSURE; NONE вместе с другим ярлыком - другой ярлык."""
    took = {l for l, c in labels.items() if c in TAKEN and l != "UNSURE"}
    if len(took) > 1:
        took.discard("NONE")
    return took


def claim_ok(c, truth):
    return bool(GROUP_OK.get(c["group"], set()) & truth)


def build_truth(key, ans, old):
    """pair -> (ярлыки, откуда): судья (если взял хоть что-то) или прежний эталон."""
    out = {}
    for k, rel in old.items():
        if rel in OLD_REF:
            out[k] = (set(OLD_REF[rel]), "old")
    for it in key["items"]:
        k = pk(it["a"], it["b"])
        t = truth_of(ans.get(it["q"], {}))
        if t:
            out[k] = (t, "judge")
        elif it["q"] in ans and k in out and out[k][1] == "old":
            out[k] = (set(), "judge_unsure")
    return out


# ---------------------------------------------------------------- 6. метрики

def existence_typed(pc):
    """pc: [(истина или None, [довод])]. Точность существования, типа (факт) и автоматического действия."""
    ex = [(t, cs) for t, cs in pc if t and any(c["existence"] == STRONG for c in cs)]
    ty = [(t, c) for t, cs in pc if t for c in cs if c["existence"] == STRONG and c["type_level"] == T_STRONG]
    au = [(t, c) for t, c in ty if c.get("production", True)]

    def by(xs):
        g = defaultdict(lambda: [0, 0])
        for t, c in xs:
            g[c["group"]][0] += claim_ok(c, t)
            g[c["group"]][1] += 1
        return {k: {"ok": v[0], "n": v[1]} for k, v in sorted(g.items())}
    return {"existence_precision": rate(sum(t != {"NONE"} for t, _ in ex), len(ex)), "existence_judged": len(ex),
            "typed_fact_precision": rate(sum(claim_ok(c, t) for t, c in ty), len(ty)), "typed_fact_judged": len(ty),
            "typed_auto_precision": rate(sum(claim_ok(c, t) for t, c in au), len(au)), "typed_auto_judged": len(au),
            "typed_auto_by_group": by(au)}


def recall_labels(pc):
    out = {}
    for lab in LABELS[:-2]:
        pos = [cs for t, cs in pc if t and lab in t]
        g = LABEL_GROUP.get(lab)
        out[lab] = {"n": len(pos), "existence": sum(any(c["existence"] == STRONG for c in cs) for cs in pos),
                    "any_claim": sum(bool(cs) for cs in pos)}
        if g:
            out[lab].update({"discovery": sum(any(c["group"] == g for c in cs) for cs in pos),
                             "strong": sum(any(c["group"] == g and c["existence"] == STRONG for c in cs) for cs in pos),
                             "auto": sum(any(c["group"] == g and auto_claim(c) for c in cs) for cs in pos)})
    dpos = [cs for t, cs in pc if t and t & set(DERIVED_LABELS) and "EXACT_COPY" not in t]
    out["derived_any"] = {"n": len(dpos), "existence": sum(any(c["existence"] == STRONG for c in cs) for cs in dpos),
                          "discovery": sum(any(c["group"] == "derived" for c in cs) for cs in dpos),
                          "auto": sum(any(c["group"] == "derived" and auto_claim(c) for c in cs) for cs in dpos)}
    return out


def mirror_reference(key, ans, fires):
    """Независимый эталон зеркальных пар: срабатывания V1 и отрицательные, по ответам судьи."""
    rows = []
    for it in key["items"]:
        tags = it["tags"]
        if not any(t.startswith("mirror_") for t in tags):
            continue
        t = truth_of(ans.get(it["q"], {}))
        k = pk(it["a"], it["b"])
        typ = fires.get(k)
        rows.append({"q": it["q"], "a": it["a"], "b": it["b"], "fired": typ, "truth": sorted(t),
                     "cluster": min(it["a"], it["b"]) if typ else None})
    out = {}
    for typ, want in (("MIRRORED_RECOLOR", {"MIRRORED_VARIANT_PEER"}), ("NEAR_RECOLOR", {"RECOLOR_PEER", "DERIVED"})):
        allf = [r for r in rows if r["fired"] == typ]
        f = [r for r in allf if r["truth"]]
        ok = [r for r in f if set(r["truth"]) & want]
        rel = [r for r in f if set(r["truth"]) - {"NONE"}]
        cl = defaultdict(list)
        for r in f:
            cl[r["cluster"]].append(bool(set(r["truth"]) & want))
        other = Counter(l for r in rel if r not in ok for l in r["truth"])
        out[typ] = {"fired": len(allf), "correct_relation": len(rel), "wrong_relation": len(f) - len(rel),
                    "open": len(allf) - len(f), "precision": rate(len(rel), len(f)),
                    "typed_as_claimed": len(ok), "related_but_other_type": len(rel) - len(ok),
                    "typed_precision": rate(len(ok), len(f)), "other_types": dict(other),
                    "clusters": len(cl), "clusters_all_typed": sum(all(v) for v in cl.values()),
                    "wrong": ["%s %s %s" % (r["a"], r["b"], "/".join(r["truth"])) for r in f if r not in ok]}
    neg = [r for r in rows if not r["fired"] and r["truth"]]
    out["negatives"] = {"judged": len(neg), "judge_mirrored": sum("MIRRORED_VARIANT_PEER" in r["truth"] for r in neg),
                        "judge_related": sum(bool(set(r["truth"]) - {"NONE"}) for r in neg),
                        "list_related": ["%s %s %s" % (r["a"], r["b"], "/".join(r["truth"])) for r in neg
                                         if set(r["truth"]) - {"NONE"}]}
    out["unanswered"] = sum(not r["truth"] for r in rows)
    return out


def existence_class(t):
    """Истина существования: RELATED, NONE или OPEN (судья ничего не взял, эталон OPEN)."""
    if not t:
        return "OPEN"
    return "NONE" if t == {"NONE"} else "RELATED"


def composite_reclass(rp, T):
    """Откуда изменился знаменатель составного: прежние 12 пар «структура» 60 и куда их отнёс пересуд."""
    old = [(a, b) for a, b, rel in rp if rel == "STRUCTURAL_RELATION"]
    new = [(a, b, rel) for a, b, rel in rp if "COMPOSITE" in T.get(pk(a, b), (set(), ""))[0]]
    rc = Counter()
    for a, b in old:
        t, src = T.get(pk(a, b), (set(), ""))
        if src == "old":
            rc["not_rejudged"] += 1
        elif "COMPOSITE" in t:
            rc["kept_composite"] += 1
        elif not t:
            rc["open"] += 1
        else:
            for lab, name in (("STRUCTURAL_COUNTERPART", "reclassified_to_counterpart"),
                              ("MIRRORED_VARIANT_PEER", "reclassified_to_mirrored"),
                              ("ATTACHMENT_CANDIDATE", "reclassified_to_attachment"),
                              ("MODULAR_SECTION", "reclassified_to_modular"), ("NONE", "reclassified_to_none")):
                if lab in t:
                    rc[name] += 1
            if not t & {"STRUCTURAL_COUNTERPART", "MIRRORED_VARIANT_PEER", "ATTACHMENT_CANDIDATE",
                        "MODULAR_SECTION", "NONE"}:
                rc["reclassified_to_other"] += 1
    return {"old_composite_denominator": len(old), "new_true_composite_denominator": len(new),
            "new_from_other_old_labels": ["%s %s (было %s)" % x for x in new if x[2] != "STRUCTURAL_RELATION"],
            **{k: rc.get(k, 0) for k in ("kept_composite", "reclassified_to_counterpart", "reclassified_to_mirrored",
                                         "reclassified_to_attachment", "reclassified_to_modular",
                                         "reclassified_to_none", "reclassified_to_other", "open", "not_rejudged")}}


def control_agreement(changes):
    """Контрольные 20 (agree_*): согласие пересуда с прежним эталоном и список всех изменённых."""
    ctl = [x for x in changes if any(t.startswith("agree_") for t in x["tags"])]
    taken = [x for x in ctl if x["taken"]]
    changed = ["%s %s %s: было %s, судья %s%s" % (x["q"], x["a"], x["b"], x["old"],
                                                 ", ".join("%s:%s" % kv for kv in x["judge"].items()),
                                                 "" if x["taken"] else " (не взято: low/UNSURE)")
               for x in ctl if not x["agrees_old"]]
    ex_ok = [x for x in taken if existence_class(OLD_REF.get(x["old"], set())) == existence_class(set(x["taken"]))]
    widened = ["%s %s %s: было %s, взято %s" % (x["q"], x["a"], x["b"], x["old"], "/".join(x["taken"]))
               for x in ctl if x["agrees_old"] and set(x["taken"]) - OLD_REF.get(x["old"], set())]
    return {"n": len(ctl), "taken": len(taken), "agree": sum(x["agrees_old"] for x in ctl),
            "control_truth_agreement": rate(sum(x["agrees_old"] for x in taken), len(taken)),
            "control_existence_agreement": rate(len(ex_ok), len(taken)),
            "changed": changed, "agree_with_extra_labels": widened}


def frame_composite(rows60, truth, pairs, keys):
    """Кадровый составной (вторично, правило до ответов): кадр с ролью composite эталона остаётся составным, если
    у него нет пар STRUCTURAL_RELATION, или хоть одна из них - COMPOSITE по истине; иначе (все пересужены, ни одной
    COMPOSITE) - не составной."""
    out = []
    for r in rows60:
        a = r["asset_id"]
        if r["ref_role_status"] != "judged" or "composite" not in r["ref_role_groups"]:
            continue
        sp = [pk(a, x["relative"]) for x in pairs.get(a, []) if x["ref_pair_relation"] == "STRUCTURAL_RELATION"]
        stay = not sp or any("COMPOSITE" in truth.get(k, (set(), ""))[0] or truth.get(k, (set(), ""))[1] == "old"
                             for k in sp)
        out.append({"asset_id": a, "true_composite": stay, "found": "composite" in r["g_discovery"],
                    "auto": "composite" in r["g_auto"]})
    t = [x for x in out if x["true_composite"]]
    return {"n": len(t), "discovery": sum(x["found"] for x in t), "auto": sum(x["auto"] for x in t),
            "recall": rate(sum(x["found"] for x in t), len(t)), "rows": out}


def score_rows(rows, C, pairs, fsets, v8):
    out = []
    for r in rows:
        a = r["asset_id"]
        pipe, _why = v8.pipeline_of(r["semantic_eff"], r["surface"], pipe_roles(C, a))
        creative = pipe == "OBJECT_PIPELINE" and not v3.bound(C, a) and not v3.has_evidence(C, a)
        out.append({"asset_id": a, "pipeline": pipe, "creative": creative, "ref_pipeline": r["ref_pipeline"],
                    "ref_role_groups": r["ref_role_groups"], "ref_role_status": r["ref_role_status"],
                    "g_auto": groups_of(C, a, "auto"), "g_discovery": groups_of(C, a, "discovery"),
                    "danger": v2.danger_v2(r, creative, C, pairs.get(a, []), fsets[a.upper()])})
    return out


def gate_table(res):
    g = []
    d = max(len(res["axes"][ax]["dangerous"]) for ax in res["axes"])
    g.append(("dangerous", d, d == GATES["dangerous"]))
    e = min(res["truth_new"]["60"]["existence_precision"] or 0, res["truth_new"]["controls"]["existence_precision"] or 0)
    g.append(("existence_precision", e, e >= GATES["existence_precision"]))
    c = res["truth_new"]["60_recall"]["COMPOSITE"]
    cr = rate(c["discovery"], c["n"]) if c["n"] else None
    g.append(("composite_recall", cr, cr is not None and cr >= GATES["composite_recall"]))
    dv = res["truth_new"]["60_recall"]["derived_any"]
    dr = rate(dv["discovery"], dv["n"])
    g.append(("derived_discovery", dr, dr is not None and dr >= GATES["derived_discovery"]))
    s = res["truth_new"]["60_recall"]["STATE_VARIANT"]
    sr = rate(s["discovery"], s["n"])
    g.append(("state_discovery", sr, sr is not None and sr >= GATES["state_discovery"]))
    ta = min(res["truth_new"]["60"]["typed_auto_precision"] or 0, res["truth_new"]["controls"]["typed_auto_precision"] or 0)
    g.append(("typed_auto_precision", ta, ta >= GATES["typed_auto_precision"]))
    return [{"gate": n, "value": v, "pass": bool(ok), "need": GATES[n]} for n, v, ok in g]


def do_report(out=OUT):
    import map_mockup as mm
    import routing_model_v8 as v8
    key = ir.load_json(p(out, "blind_key.json"))
    ans, bad = read_answers(out)
    rep, pairs, h, sha, found, ctl, keys = v3_inputs()
    if sha != key["h8_sha256"]:
        raise SystemExit("holdout V8 изменился после отбора")
    qs = {it["q"] for it in key["items"]}
    missing = sorted(qs - set(ans))
    C3 = claims_60(rep, found, v3.Claims)
    CT = claims_60(rep, found, TaxClaims)
    CC3, CCT = control_claims(ctl, v3.Claims), control_claims(ctl, TaxClaims)
    rp = ref_pairs_60(keys, pairs)
    old60 = {pk(a, b): rel for a, b, rel in rp}
    oldc = {k: r["ref"] for k, (r, _C) in CC3.items()}
    T60, TC = build_truth(key, ans, old60), build_truth(key, ans, oldc)
    tr_old60 = {k: (set(OLD_REF[rel]), "old") for k, rel in old60.items() if rel in OLD_REF}
    tr_oldc = {k: (set(OLD_REF[rel]), "old") for k, rel in oldc.items() if rel in OLD_REF}

    def pc60(C, T):
        return [(T.get(pk(a, b), (None, ""))[0] or None, C.pair(a, b)) for a, b, _rel in rp]

    def pcc(CC, T):
        return [(T.get(k, (None, ""))[0] or None, list(C.claims.values())) for k, (_r, C) in CC.items()]

    mcd = v8.Mcd(mm.World())
    fsets = {a.upper(): v8.facts(mcd, a) for a in keys}
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "RELATION_TAXONOMY_ADJUDICATION",
           "h8_sha256": sha, "answers_q": len(ans), "items": len(qs), "missing": missing, "bad_rows": bad,
           "axes": {}}
    for axis, rows in (("logic", rep["rows_logic"]), ("end_to_end", rep["rows"])):
        s = score_rows(rows, CT, pairs, fsets, v8)
        res["axes"][axis] = {"dangerous": {r["asset_id"]: r["danger"] for r in s if r["danger"]},
                             "creative": [r["asset_id"] for r in s if r["creative"]],
                             "logic": v2.logic(s), "rows": s}
    res["policy_v3_old_truth"] = {"60": existence_typed(pc60(C3, tr_old60)),
                                  "controls": existence_typed(pcc(CC3, tr_oldc))}
    res["policy_tax_old_truth"] = {"60": existence_typed(pc60(CT, tr_old60)),
                                   "controls": existence_typed(pcc(CCT, tr_oldc))}
    res["truth_new"] = {"60": existence_typed(pc60(CT, T60)), "controls": existence_typed(pcc(CCT, TC)),
                        "60_recall": recall_labels(pc60(CT, T60)), "controls_recall": recall_labels(pcc(CCT, TC)),
                        "60_recall_old_truth": recall_labels(pc60(CT, tr_old60))}
    res["truth_new"]["60_v3policy"] = existence_typed(pc60(C3, T60))
    res["truth_new"]["controls_v3policy"] = existence_typed(pcc(CC3, TC))
    res["frame_composite"] = frame_composite(res["axes"]["logic"]["rows"], T60, pairs, keys)
    # пересуд против прежнего эталона
    changes = []
    for it in key["items"]:
        k = pk(it["a"], it["b"])
        old = old60.get(k) or oldc.get(k) or ""
        t = truth_of(ans.get(it["q"], {}))
        changes.append({"q": it["q"], "a": it["a"], "b": it["b"], "tags": it["tags"], "old": old,
                        "judge": {l: c for l, c in sorted(ans.get(it["q"], {}).items())}, "taken": sorted(t),
                        "agrees_old": bool(t) and old in OLD_REF and bool(set(OLD_REF[old]) & t)})
    res["adjudication"] = changes
    res["existence_truth"] = {"60": dict(Counter(existence_class(T60.get(pk(a, b), (set(), ""))[0]) for a, b, _r in rp)),
                              "controls": dict(Counter(existence_class(TC.get(k, (set(), ""))[0]) for k in CC3))}
    res["composite_reclass"] = composite_reclass(rp, T60)
    res["control_agreement"] = control_agreement(changes)
    by_tag = defaultdict(lambda: [0, 0, 0])
    for x in changes:
        for tg in x["tags"]:
            if x["old"] in OLD_REF:
                by_tag[tg][0] += 1
                by_tag[tg][1] += x["agrees_old"]
            by_tag[tg][2] += not x["taken"]
    res["agreement_by_tag"] = {k: {"with_old": v[0], "agree": v[1], "untaken": v[2]} for k, v in sorted(by_tag.items())}
    fires = {}
    for e in found["edges"]:
        if e["detector"] == "MIRROR":
            fires[pk(e["source"], e["target"])] = e["type"]
    for r in ctl["pairs"]:
        for c in r["claims"]:
            for e in c["support"]:
                if e["detector"] == "MIRROR":
                    fires[pk(r["asset_id"], r["relative"])] = e["type"]
    res["mirror_reference"] = mirror_reference(key, ans, fires)
    struct = []
    for a, b, rel in rp:
        if rel != "STRUCTURAL_RELATION":
            continue
        t, src = T60.get(pk(a, b), (set(), ""))
        struct.append({"a": a, "b": b, "truth": sorted(t), "source": src,
                       "v3": ["%s %s/%s%s" % (c["group"], c["existence"][8:], c["type_level"][5:],
                                              "" if c.get("production", True) else " улика") for c in CT.pair(a, b)]})
    res["structural_60"] = struct
    res["gates"] = gate_table(res) if not missing else None
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res)
    print("отчёт: %s" % p(out, "report.md"))


def f2(x):
    return "-" if x is None else ("%.3f" % x if isinstance(x, float) else str(x))


def write_md(out, res):
    L = ["# RELATION_TAXONOMY_ADJUDICATION - пересчёт V3 по новой схеме и слепому пересуду", "",
         "Ответов судьи: %d из %d пар%s; строк с ошибкой формата: %d." % (
             res["answers_q"], res["items"], (", нет ответа: " + ", ".join(res["missing"][:20])) if res["missing"] else "",
             len(res["bad_rows"])), ""]
    if res["gates"]:
        L += ["## Условия заморозки", "", "| условие | значение | нужно | |", "|---|---|---|---|"]
        for g in res["gates"]:
            L.append("| %s | %s | %s | %s |" % (g["gate"], f2(g["value"]), g["need"], "да" if g["pass"] else "**нет**"))
        L.append("")
    L += ["## Безопасность (политика: анимация + перекраска сосуществуют)", ""]
    for ax, x in res["axes"].items():
        L.append("- %s: опасных %d %s; одиночных творческих %d; логика %s" % (
            ax, len(x["dangerous"]), sorted(x["dangerous"]), len(x["creative"]), x["logic"]))
    ca = res["control_agreement"]
    L += ["", "## Контрольные пары согласия (%d)" % ca["n"], "",
          "control_truth_agreement %s: взято %d, согласен с прежним эталоном %d; "
          "по существованию (RELATED / NONE) %s." % (
              f2(ca["control_truth_agreement"]), ca["taken"], ca["agree"], f2(ca["control_existence_agreement"])), ""]
    L += ["- изменено: " + x for x in ca["changed"]] or ["- изменённых нет"]
    L += ["- согласен, но добавил ярлык: " + x for x in ca["agree_with_extra_labels"]]
    et = res["existence_truth"]
    L += ["", "## Существование и тип", "",
          "Истина существования: 60 %s; контроль %s." % (et["60"], et["controls"]), "",
          "| истина / политика | набор | relation_existence_precision | typed_fact_precision | "
          "automatic_action_precision |", "|---|---|---|---|---|"]
    for name, blk in (("прежний эталон / V3", res["policy_v3_old_truth"]), ("прежний эталон / новая", res["policy_tax_old_truth"]),
                      ("пересуд / V3", {"60": res["truth_new"]["60_v3policy"], "controls": res["truth_new"]["controls_v3policy"]}),
                      ("пересуд / новая", {"60": res["truth_new"]["60"], "controls": res["truth_new"]["controls"]})):
        for s in ("60", "controls"):
            x = blk[s]
            L.append("| %s | %s | %s (%d) | %s (%d) | %s (%d) |" % (
                name, s, f2(x["existence_precision"]), x["existence_judged"], f2(x["typed_fact_precision"]),
                x["typed_fact_judged"], f2(x["typed_auto_precision"]), x["typed_auto_judged"]))
    L += ["", "## Полнота на 60 по ярлыкам истины (пересуд)", "",
          "| ярлык | пар | существование | любой довод | обнаружение | STRONG | авто |", "|---|---|---|---|---|---|---|"]
    for lab, x in res["truth_new"]["60_recall"].items():
        if not x["n"]:
            continue
        L.append("| %s | %d | %d | %s | %s | %s | %s |" % (lab, x["n"], x.get("existence", 0), x.get("any_claim", "-"),
                                                          x.get("discovery", "-"), x.get("strong", "-"), x.get("auto", "-")))
    fc = res["frame_composite"]
    cr = res["composite_reclass"]
    L += ["", "Кадровый составной (вторично): %d из %d (%s), авто %d." % (fc["discovery"], fc["n"], f2(fc["recall"]), fc["auto"]),
          "", "## Знаменатель составного", ""]
    L += ["- %s: %s" % (k, v) for k, v in cr.items()]
    L += ["", "## 12 пар «структура» эталона 60", "", "| A | B | истина | откуда | доводы V3 |", "|---|---|---|---|---|"]
    for x in res["structural_60"]:
        L.append("| %s | %s | %s | %s | %s |" % (x["a"], x["b"], "/".join(x["truth"]) or "-", x["source"], "; ".join(x["v3"]) or "-"))
    m = res["mirror_reference"]
    L += ["", "## Зеркальный эталон (судья)", ""]
    L += ["| детектор | срабатываний | correct relation | wrong relation | open | precision | typed_as_claimed | "
          "related_but_other_type | кластеров (все с подтипом) |", "|---|---|---|---|---|---|---|---|---|"]
    for typ in ("MIRRORED_RECOLOR", "NEAR_RECOLOR"):
        x = m[typ]
        L.append("| %s | %d | %d | %d | %d | %s | %d | %d | %d (%d) |" % (
            typ, x["fired"], x["correct_relation"], x["wrong_relation"], x["open"], f2(x["precision"]),
            x["typed_as_claimed"], x["related_but_other_type"], x["clusters"], x["clusters_all_typed"]))
    L.append("")
    for typ in ("MIRRORED_RECOLOR", "NEAR_RECOLOR"):
        L.append("- %s: другие типы %s; не подтип: %s" % (typ, m[typ]["other_types"], "; ".join(m[typ]["wrong"][:15]) or "-"))
    n = m["negatives"]
    L.append("- отрицательные: судимых %d, судья видит зеркальный вариант %d, связь %d: %s" % (
        n["judged"], n["judge_mirrored"], n["judge_related"], "; ".join(n["list_related"][:12]) or "-"))
    L += ["", "## Пересуд против прежнего эталона, по группам отбора", "",
          "| группа | с прежним эталоном | согласен | не взято (low/UNSURE) |", "|---|---|---|---|"]
    for k, v in res["agreement_by_tag"].items():
        L.append("| %s | %d | %d | %d |" % (k, v["with_old"], v["agree"], v["untaken"]))
    with open(p(out, "report.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["select", "pack", "report"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    {"select": do_select, "pack": do_pack, "report": do_report}[a.cmd](a.out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
