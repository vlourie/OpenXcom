#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""OTHER_VIEW_REGISTRY_V1 - полный реестр «один физический предмет с разных сторон» до массового рендера.

Задание специалиста 07.10: перед любым следующим массовым HD-рендером предметов найти по ВСЕМУ проекту кадры,
где изображён один и тот же предмет с другой стороны или в другом повороте (OTHER_VIEW), а не только в
подклассе V4 (654 строки). Без Codex и без видеокарты: только признаки кадра, MCD, LOFT, карты и прежние связи.

Отличие от obj_families: там «другой бок» искался только в одном наборе и среди соседних номеров (NEAR 2);
здесь перебираются все пары кадров-предметов проекта, и соседство номера - лишь один из доводов.

    py -3.13 tools/hdart/other_view_registry.py features     -> кадры, признаки, связи MCD, карты (кэш)
    py -3.13 tools/hdart/other_view_registry.py pairs        -> candidates.tsv: граф кандидатов (полнота)
    py -3.13 tools/hdart/other_view_registry.py classify     -> pairs_classified.tsv, groups.json, gaps.tsv
    py -3.13 tools/hdart/other_view_registry.py report       -> REPORT.md и листы групп

Всё пишется в art/objects/generation/probes/other-view-registry-v1 (не в Git).
"""
import argparse
import csv
import glob
import json
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

import numpy as np                                      # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("art", "objects", "generation", "probes", "other-view-registry-v1")
ITEMS = os.path.join("art", "objects", "discovery", "items.json")
GEN = os.path.join("art", "objects", "generation", "generation.tsv")
REPORT_V1 = os.path.join("art", "objects", "generation", "probes", "remaining-classes-v1", "report.tsv")
IDENT = os.path.join("art", "objects", "discovery", "asset_identity.tsv")
STATES = os.path.join("art", "objects", "discovery", "state_variants.json")
FAMS = os.path.join("art", "objects", "families", "families.json")
FAM_DEC = os.path.join("art", "objects", "families", "decisions.tsv")
PROBES = os.path.join("art", "objects", "generation", "probes")
V4 = os.path.join(PROBES, "prod-two-pass-v4")
OBJECTISH = ("object", "object_or_relief")


def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def write_tsv(path, head, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("\t".join(head) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(h, "")) for h in head) + "\n")


def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def load(path):
    with open(path, encoding=ENC) as f:
        return json.load(f)


def split(k):
    s, f = k.split(":")
    return s.upper(), int(f)


def key(s, f):
    return "%s:%d" % (s.upper(), f)


# ---------------------------------------------------------------- features

def lum(a):
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def do_features(a):
    import map_mockup as mm
    import obj_struct as os_
    import pck_census as pc
    t0 = time.time()
    items = load(ITEMS)
    gen = {int(r["rank"]): r for r in read_tsv(GEN) if r.get("rank", "").isdigit()}
    world = mm.World()
    st = os_.Struct(world)

    frames, meta = [], []           # кадры вселенной: по куску на кадр src (составной - все куски)
    seen = {}
    for it in items:
        g = gen.get(it["rank"], {})
        src = it["src"] if it["kind"] == "составной" else it["src"][:1]
        for part, k in enumerate(src):
            s, fr = split(k)
            kk = key(s, fr)
            if kk in seen:          # кадр уже в другой строке очереди (кусок двух составных)
                meta[seen[kk]]["also_ranks"].append(it["rank"])
                continue
            im = world.sprite(s.lower(), fr, None)
            if im is None:
                continue
            arr = np.asarray(im.convert("RGBA"))
            if not (arr[..., 3] > 0).any():
                continue
            seen[kk] = len(frames)
            frames.append(arr)
            meta.append({"key": kk, "rank": it["rank"], "asset_id": g.get("asset_id", it["keys"][0]),
                         "kind": it["kind"], "part": part, "n_parts": len(src),
                         "copies": [k2.upper() for k2 in it["keys"]] if it["kind"] == "один" else [],
                         "asset_class": g.get("asset_class", ""), "action": g.get("action", ""),
                         "relation": g.get("relation", ""), "family": g.get("family", ""),
                         "places": it.get("places", 0), "also_ranks": []})
    n = len(frames)
    print("кадров вселенной: %d (строк очереди %d), %.0f с" % (n, len(items), time.time() - t0), flush=True)
    A = np.stack(frames)                                     # [n, 40, 32, 4]

    # MCD: физика, объём, связи записей (анимация, die, alt) по всему набору
    phys = np.full((n, len(os_.PHYS_KEY)), -1, np.int16)
    vox = np.zeros((n, 12, 16, 16), bool)
    has_rec = np.zeros(n, bool)
    ttype = np.full(n, -1, np.int16)
    for i, m in enumerate(meta):
        s, fr = split(m["key"])
        inf = st.info(s, fr, im=None)
        if inf.get("rec"):
            has_rec[i] = True
            phys[i] = [inf["phys"][k] for k in os_.PHYS_KEY]
            vox[i] = inf["vox"]
            ttype[i] = inf["tile_type"]
    links = defaultdict(set)                                 # (кадр, кадр) -> {ANIMATION, DESTROYED, STATE}
    sets_used = sorted({split(m["key"])[0] for m in meta})
    for s in sets_used:
        recs = world.records(s)
        for r in recs:
            fs = sorted({f for f in r["frames"]})
            if len(fs) > 1:
                for x in fs:
                    for y in fs:
                        if x < y:
                            links[(key(s, x), key(s, y))].add("ANIMATION")
            for fld, lab in (("die", "DESTROYED"), ("alt", "STATE_VARIANT")):
                d = r[fld]
                if d and d < len(recs):
                    x, y = r["frame"], recs[d]["frame"]
                    if x != y:
                        links[(key(s, min(x, y)), key(s, max(x, y)))].add(lab)
    for sv in (load(STATES) if os.path.exists(STATES) else []):
        x, y = sv.get("asset_id"), sv.get("variant_of")
        if x and y:
            x, y = x.upper(), y.upper()
            links[(min(x, y), max(x, y))].add(sv.get("relation") or "STATE_VARIANT")
    print("связей MCD (анимация, die, alt) и state_variants: %d пар, %.0f с" % (len(links), time.time() - t0), flush=True)

    # карты: в каких блоках (террейн, блок) стоит кадр - соседство на картах как довод
    idx = {m["key"]: i for i, m in enumerate(meta)}
    for i, m in enumerate(meta):
        for c in m["copies"]:                 # побайтовые копии кадра в других наборах - те же места
            idx.setdefault(c, i)
    blocks = defaultdict(set)
    bnames = []
    pairs = [(t, b) for t in world.terrains for b in world.blocks_of(t)]
    for bn, (t, b) in enumerate(pairs):
        try:
            sets = world.sets_of(t)
            sizes = np.array([len(world.records(s)) for s in sets], np.int64)
            path = world.files.find(os.path.join("MAPS", b + ".MAP"))
            if not path or not len(sizes):
                continue
            data = np.frombuffer(open(path, "rb").read()[3:], np.uint8)
        except (Exception, SystemExit):                      # noqa: BLE001 - битый блок: пропустить
            continue
        v = data[: len(data) // 4 * 4].reshape(-1, 4)[:, 1:].reshape(-1).astype(np.int64)  # пол - не предмет
        v = np.unique(v[v > 0])
        ends = np.cumsum(sizes)
        si = np.searchsorted(ends, v, side="right")
        ok = si < len(sets)
        bid = len(bnames)
        bnames.append(t + "/" + b)
        for val, sx in zip(v[ok], si[ok]):
            s = sets[sx]
            rec = int(val - (ends[sx - 1] if sx else 0))
            fr = world.records(s)[rec]["frame"]
            j = idx.get(key(s, fr))
            if j is not None:
                blocks[j].add(bid)
        if bn and bn % 2000 == 0:
            print("  блоков %d из %d, %.0f с" % (bn, len(pairs), time.time() - t0), flush=True)
    for i, m in enumerate(meta):
        m["blocks"] = sorted(blocks.get(i, ()))
    print("блоков карт: %d, кадров на картах: %d, %.0f с" % (len(bnames), len(blocks), time.time() - t0), flush=True)

    # опознание и флаги переписи остатка
    ident = {r["asset_id"].upper(): r for r in read_tsv(IDENT)}
    rep = {r["asset_id"].upper(): r for r in read_tsv(REPORT_V1)}
    for m in meta:
        aid = m["asset_id"].upper()
        r = ident.get(aid, {})
        m["identity"] = r.get("identity") or r.get("proposed") or ""
        m["category"] = r.get("proposed_category", "")
        rr = rep.get(aid, {})
        m["flags"] = (rr.get("flags") or "").split()
        m["v1_class"], m["v1_subclass"] = rr.get("class", ""), rr.get("subclass", "")

    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(os.path.join(OUT, "features.npz"), A=A, phys=phys, vox=vox, has_rec=has_rec, ttype=ttype)
    dump({"frames": meta, "links": [[x, y, sorted(l)] for (x, y), l in sorted(links.items())],
          "blocks": bnames, "phys_key": list(os_.PHYS_KEY)}, os.path.join(OUT, "features.json"))
    print("готово: %s, %.0f с" % (OUT, time.time() - t0))


def load_features():
    z = np.load(os.path.join(OUT, "features.npz"))
    j = load(os.path.join(OUT, "features.json"))
    return z, j


# ---------------------------------------------------------------- известные связи

def known_labels():
    """Все прежние решения о паре кадров: {(a, b): [(источник, ярлык), ...]}, a < b.

    Ярлыки приводятся к словарю задания: OTHER_VIEW, MIRROR, RECOLOR, SAME_FRAMEWORK_DIFFERENT_OBJECT,
    NOT_OBJECT, STATE_VARIANT, DESTROYED, STRUCTURAL_PART, EXACT_COPY, ANIMATION, NONE, UNCERTAIN, OLD_MIRRORED
    (зеркальный ярлык прежней схемы: в ней нет поворота, R-177, поэтому он не довод ни за, ни против)."""
    out = defaultdict(list)

    def add(a, b, src, lab):
        a, b = a.upper(), b.upper()
        if a != b:
            out[(min(a, b), max(a, b))].append((src, lab))
    for r in read_tsv(os.path.join(V4, "control", "truth.tsv")):
        add(r["a"], r["b"], "V4_CONTROL", r["truth"])
    for r in read_tsv(os.path.join(V4, "pool_cls", "classified.tsv")):
        add(r["a"], r["b"], "V4_POOL_CODEX", r["category"])
    old = {"RECOLOR_PEER": "RECOLOR", "EXACT_COPY": "EXACT_COPY", "STATE_VARIANT": "STATE_VARIANT",
           "ANIMATION_FAMILY": "ANIMATION", "COMPOSITE": "STRUCTURAL_PART", "STRUCTURAL_COUNTERPART": "STRUCTURAL_PART",
           "MODULAR_SECTION": "STRUCTURAL_PART", "MIRRORED_VARIANT_PEER": "OLD_MIRRORED", "NONE": "NONE",
           "DERIVED": "OLD_DERIVED", "ATTACHMENT_CANDIDATE": "OLD_ATTACHMENT"}
    tv2 = os.path.join(PROBES, "relation-truth-v2", "truth_v2.json")
    srcs = [("TRUTH_V2", tv2)] + [("HOLDOUT_" + os.path.basename(os.path.dirname(p)).split("-")[-1].upper(), p)
                                  for p in sorted(glob.glob(os.path.join(PROBES, "relation-holdout-v*", "truth.json")))]
    for name, p in srcs:
        if not os.path.exists(p):
            continue
        d = load(p)
        rows = d.get("truth") if isinstance(d.get("truth"), list) else (d.get("pairs") or d.get("rows") or [])
        for r in rows:
            if not isinstance(r, dict) or "a" not in r:
                continue
            if r.get("existence") == "NONE":
                add(r["a"], r["b"], name, "NONE")
            for lab in r.get("closed") or []:
                if lab in old and lab != "NONE":
                    add(r["a"], r["b"], name, old[lab])
    # семейства: перекраска и зеркало (машина), другой бок (машина или человек), решения человека
    for fm in load(FAMS):
        can = fm["canonical"]
        for m in fm.get("members", []):
            rel = m.get("relation")
            lab = {"recolor": "RECOLOR", "mirror": "MIRROR", "alternate_view": "OTHER_VIEW"}.get(rel)
            if lab:
                src = "FAMILY_HUMAN" if m.get("decision") == "HUMAN_APPROVED" else "FAMILY_AUTO"
                add(can, m["keys"][0], src, lab)
        for m in fm.get("review", []):
            if m.get("relation") == "alternate_view":
                add(can, m["keys"][0], "FAMILY_REVIEW", "OTHER_VIEW_CANDIDATE")
    # отказы alt_view внутри набора (obj_families, машина): довод против, не правда
    arp = os.path.join(os.path.dirname(FAMS), "alt_rejected.tsv")
    if os.path.exists(arp):
        with open(arp, encoding=ENC, newline="") as f:     # номер, ключ, номер, ключ: имена столбцов повторяются
            for vals in list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))[1:]:
                if len(vals) >= 4:
                    add(vals[1], vals[3], "ALT_REJECTED", "NONE")
    # связи MCD детекторов связей (die, alt, петля анимации), в обе стороны (R-171)
    via = {"alt": "STATE_VARIANT", "die": "DESTROYED", "anim": "ANIMATION", "animation": "ANIMATION"}
    for p in sorted(glob.glob(os.path.join(PROBES, "*", "relations", "detectors.json"))):
        for lst in load(p).get("by_set", {}).values():
            for e in lst:
                lab = via.get(e.get("via"))
                if lab and e.get("level") == "STRONG" and e.get("state") and e.get("base"):
                    add(e["state"], e["base"], "DETECTOR", lab)
    return out


# ---------------------------------------------------------------- граф кандидатов

def shifted(M, dx):
    """Маски [n, 40, 32] со сдвигом по x на dx (поля нулями)."""
    if dx == 0:
        return M
    R = np.zeros_like(M)
    if dx > 0:
        R[:, :, dx:] = M[:, :, :-dx]
    else:
        R[:, :, :dx] = M[:, :, -dx:]
    return R


def coarse_hist(A, m):
    """Грубая гистограмма цвета 4x4x4 по непрозрачному, корень, нормирована - косинус = сходство материалов."""
    q = (A[..., :3] // 64).astype(np.int32)
    code = q[..., 0] * 16 + q[..., 1] * 4 + q[..., 2]
    H = np.zeros((len(A), 64), np.float32)
    for i in range(len(A)):
        H[i] = np.bincount(code[i][m[i]], minlength=64)
    H = np.sqrt(H)
    H /= np.linalg.norm(H, axis=1, keepdims=True) + 1e-9
    return H


# пороги полноты (высокий охват: кандидат дальше разбирается, а не принимается)
AREA_MIN = 0.5          # площадь меньшего к большему
BOTTOM_MAX = 6          # низ рамки - стоят на одном полу
HEIGHT_MAX = 10
SHAPE_MIN = 0.5         # IoU силуэта как есть или отражённого, со сдвигом по x до 3
ROWS_MIN = 0.85         # или профиль ширины по строкам (не меняется при отражении)
COLOR_MIN = 0.5         # материалы похожи


def do_pairs(a):
    t0 = time.time()
    z, j = load_features()
    meta = j["frames"]
    A = z["A"]
    n = len(A)
    mask = A[..., 3] > 0
    obj = np.array([m["asset_class"] in OBJECTISH for m in meta])
    I = np.nonzero(obj)[0]
    M = mask[I].astype(np.float32)
    k = len(I)
    area = M.reshape(k, -1).sum(1)
    ys = [np.nonzero(x.any(1))[0] for x in mask[I]]
    top = np.array([y.min() for y in ys])
    bot = np.array([y.max() for y in ys])
    h = bot - top + 1
    print("кадров-предметов в переборе: %d из %d" % (k, n), flush=True)
    best, bestf = np.zeros((k, k), np.float32), np.zeros((k, k), np.float32)
    flat = M.reshape(k, -1)
    for flip, dst in ((False, best), (True, bestf)):
        Mb = M[:, :, ::-1] if flip else M
        for dx in range(-3, 4):
            S = shifted(Mb, dx)
            sf = S.reshape(k, -1)
            inter = flat @ sf.T
            union = area[:, None] + sf.sum(1)[None, :] - inter
            np.maximum(dst, inter / np.maximum(union, 1), out=dst)
    rows = M.sum(2)
    rc = rows - rows.mean(1, keepdims=True)
    rc /= np.linalg.norm(rc, axis=1, keepdims=True) + 1e-9
    RC = rc @ rc.T
    H = coarse_hist(A[I], mask[I])
    COL = H @ H.T
    ar = np.minimum(area[:, None], area[None, :]) / np.maximum(area[:, None], area[None, :])
    cand = (ar >= AREA_MIN) & (np.abs(bot[:, None] - bot[None, :]) <= BOTTOM_MAX) & \
        (np.abs(h[:, None] - h[None, :]) <= HEIGHT_MAX) & \
        ((np.maximum(best, bestf) >= SHAPE_MIN) | ((RC >= ROWS_MIN) & (ar >= 0.7))) & (COL >= COLOR_MIN)
    cand = np.triu(cand, 1)
    # один и тот же предмет очереди (куски составного) - это не пары видов
    rk = np.array([meta[i]["rank"] for i in I])
    cand &= rk[:, None] != rk[None, :]
    ii, jj = np.nonzero(cand)
    print("кандидатов по признакам: %d, %.0f с" % (len(ii), time.time() - t0), flush=True)

    known = known_labels()
    pos = {m["key"]: x for x, m in enumerate(meta)}
    loc = {g: x for x, g in enumerate(I)}
    pairs = {(int(I[x]), int(I[y])) for x, y in zip(ii, jj)}
    seed = 0
    for (ka, kb), labs in known.items():
        x, y = pos.get(ka), pos.get(kb)
        if x is None or y is None or (min(x, y), max(x, y)) in pairs:
            continue
        if any(l in ("OTHER_VIEW", "OTHER_VIEW_CANDIDATE", "OLD_MIRRORED") for _s, l in labs):
            pairs.add((min(x, y), max(x, y)))
            seed += 1
    print("добавлено из прежних связей (OTHER_VIEW, кандидаты, зеркальные ярлыки старой схемы): %d" % seed)
    out = []
    for x, y in sorted(pairs):
        lx, ly = loc.get(x), loc.get(y)
        rec = {"i": x, "j": y, "a": meta[x]["key"], "b": meta[y]["key"]}
        if lx is not None and ly is not None:
            rec.update(iou=round(float(best[lx, ly]), 3), iou_flip=round(float(bestf[lx, ly]), 3),
                       rows=round(float(RC[lx, ly]), 3), color=round(float(COL[lx, ly]), 3),
                       area_ratio=round(float(ar[lx, ly]), 3), dh=int(abs(h[lx] - h[ly])),
                       dbot=int(abs(bot[lx] - bot[ly])), by_features=int(bool(cand[min(lx, ly), max(lx, ly)])))
        else:
            rec.update(by_features=0)
        out.append(rec)
    dump(out, os.path.join(OUT, "candidates.json"))
    # полнота по прежним связям: сколько известных OTHER_VIEW признаки нашли сами
    rec_c = Counter()
    for (ka, kb), labs in known.items():
        x, y = pos.get(ka), pos.get(kb)
        for s, l in set(labs):
            if l not in ("OTHER_VIEW", "OTHER_VIEW_CANDIDATE", "OLD_MIRRORED", "SAME_FRAMEWORK_DIFFERENT_OBJECT", "MIRROR"):
                continue
            if x is None or y is None:
                rec_c[(s, l, "нет кадра во вселенной")] += 1
                continue
            lx, ly = loc.get(min(x, y)), loc.get(max(x, y))
            hit = lx is not None and ly is not None and bool(cand[min(lx, ly), max(lx, ly)])
            rec_c[(s, l, "найдено признаками" if hit else "НЕ найдено признаками")] += 1
    stat = {"frames": n, "object_frames": k, "by_features": int(len(ii)), "seeded": seed, "pairs": len(out),
            "recall_known": [[s, l, w, c] for (s, l, w), c in sorted(rec_c.items())]}
    dump(stat, os.path.join(OUT, "candidates_stat.json"))
    for r in stat["recall_known"]:
        print("  %-16s %-34s %-24s %d" % tuple(r))
    print("пар в графе: %d, %.0f с" % (len(out), time.time() - t0))


# ---------------------------------------------------------------- признаки пар узкого графа

def fine_hist(A, m):
    q = (A[..., :3] // 32).astype(np.int32)
    code = q[..., 0] * 64 + q[..., 1] * 8 + q[..., 2]
    H = np.zeros((len(A), 512), np.float32)
    for i in range(len(A)):
        H[i] = np.bincount(code[i][m[i]], minlength=512)
    H = np.sqrt(H)
    H /= np.linalg.norm(H, axis=1, keepdims=True) + 1e-9
    return H


def nature(m):
    # флаг nature переписи остатка ставится по имени набора (полки, стёкла, чаши в нём) - не довод;
    # природа - только по категории опознания
    return m["category"] in ("plant or nature", "rock or terrain relief")


def do_pairfeat(a):
    """Узкий граф: все пары внутри набора (номер кадра - признак, а не отсев) и пары разных наборов,
    которые стоят в одних блоках карт с тем же материалом или совпадают по материалу, физике и форме.
    Для каждой - признаки родства: точная копия, зеркало, перекраска, объём LOFT, физика, карты."""
    import mirror_frames as mf
    import obj_struct as os_
    import relation_probe as rp
    t0 = time.time()
    z, j = load_features()
    meta = j["frames"]
    A = z["A"]
    mask = A[..., 3] > 0
    n = len(A)
    cands = load(os.path.join(OUT, "candidates.json"))
    sets = np.array([split(m["key"])[0] for m in meta])
    frs = np.array([split(m["key"])[1] for m in meta])
    B = np.zeros((n, len(j["blocks"])), np.float32)
    for i, m in enumerate(meta):
        B[i, m["blocks"]] = 1
    nb = B.sum(1)
    H = fine_hist(A, mask)
    hr = z["has_rec"]
    ph = z["phys"]
    core = [j["phys_key"].index(c) for c in os_.CORE]
    links = {(x, y): l for x, y, l in j["links"]}
    known = known_labels()
    ci = np.array([c["i"] for c in cands])
    cj = np.array([c["j"] for c in cands])
    shp = np.array([max(c.get("iou", 0), c.get("iou_flip", 0)) for c in cands])
    SB = B @ B.T
    CF = H @ H.T
    PE = np.ones((n, n), bool)
    for q in core:
        PE &= ph[:, q][:, None] == ph[:, q][None, :]
    PE |= ~(hr[:, None] & hr[None, :])
    sb, cf, pe = SB[ci, cj], CF[ci, cj], PE[ci, cj]
    del SB, CF, PE
    kn = np.array([(min(meta[x]["key"], meta[y]["key"]), max(meta[x]["key"], meta[y]["key"])) in known
                   for x, y in zip(ci, cj)])
    ok = kn | (sets[ci] == sets[cj]) | (pe & (((sb > 0) & (cf >= 0.85)) | ((cf >= 0.95) & (shp >= 0.8))))
    keep = [c for c, o in zip(cands, ok) if o]
    print("узкий граф: %d пар из %d, %.0f с" % (len(keep), len(cands), time.time() - t0), flush=True)
    rows = []
    for q, c in enumerate(keep):
        x, y = c["i"], c["j"]
        ka, kb = meta[x]["key"], meta[y]["key"]
        same = sets[x] == sets[y]
        Ax, Ay = A[x], A[y]
        mx, my = mask[x], mask[y]
        exact = bool((mx == my).all() and (Ax[mx] == Ay[mx]).all())
        fl = Ax[:, ::-1]
        flip_exact = bool((mx[:, ::-1] == my).all() and (fl[my] == Ay[my]).all())
        relit = min(mf.relight_err(Ax, Ay), mf.relight_err(Ay, Ax))
        hue = mf.hue_gap(Ax, Ay)
        _, ca = rp.codes(Ax)
        _, cb = rp.codes(Ay)
        ov = mx & my
        f_ab = rp.func_map(ca[ov], cb[ov])[0] if ov.any() else 0.0
        f_ba = rp.func_map(cb[ov], ca[ov])[0] if ov.any() else 0.0
        cfl = ca[:, ::-1]
        ovf = mx[:, ::-1] & my
        ff_ab = rp.func_map(cfl[ovf], cb[ovf])[0] if ovf.any() else 0.0
        siou = float(ov.sum() / max(1, (mx | my).sum()))
        siou_f = float(ovf.sum() / max(1, (mx[:, ::-1] | my).sum()))
        vs = vt = vsym = -1.0
        core_d = -1
        if hr[x] and hr[y]:
            vs, vt, vsym = os_.voxel_relation(z["vox"][x], z["vox"][y])
            core_d = int(sum(ph[x, k] != ph[y, k] for k in core))
        ya = np.nonzero(mx.any(1))[0]
        yb = np.nonzero(my.any(1))[0]
        lk = links.get((min(ka, kb), max(ka, kb)), [])
        rows.append({
            "a": ka, "b": kb, "rank_a": meta[x]["rank"], "rank_b": meta[y]["rank"],
            "same_set": int(same), "fdist": int(abs(frs[x] - frs[y])) if same else 999,
            "iou": c.get("iou", round(siou, 3)), "iou_flip": c.get("iou_flip", round(siou_f, 3)),
            "siou": round(siou, 3), "siou_flip": round(siou_f, 3),
            "exact": int(exact), "flip_exact": int(flip_exact), "relight": round(relit, 1), "hue": round(hue, 1),
            "f_ab": round(f_ab, 3), "f_ba": round(f_ba, 3), "ff_ab": round(ff_ab, 3),
            "color": round(float(H[x] @ H[y]), 3),
            "dh": int(abs((ya.max() - ya.min()) - (yb.max() - yb.min()))), "dbot": int(abs(ya.max() - yb.max())),
            "area_ratio": round(min(mx.sum(), my.sum()) / max(mx.sum(), my.sum()), 3),
            "vox_same": round(vs, 3), "vox_turned": round(vt, 3), "vox_sym": round(vsym, 3), "core_diff": core_d,
            "shared_blocks": int(B[x] @ B[y]), "blocks_a": int(nb[x]), "blocks_b": int(nb[y]),
            "links": ",".join(lk), "known": ";".join(sorted({"%s=%s" % sl for sl in (kn_ for kn_ in
                                                             known.get((min(ka, kb), max(ka, kb)), []))})),
            "nature": int(nature(meta[x]) or nature(meta[y])),
            "class_a": meta[x]["asset_class"], "class_b": meta[y]["asset_class"],
            "kind_a": meta[x]["kind"], "kind_b": meta[y]["kind"],
            "ident_a": " ".join(meta[x]["identity"].split())[:60], "ident_b": " ".join(meta[y]["identity"].split())[:60],
        })
        if q and q % 2000 == 0:
            print("  пар %d из %d, %.0f с" % (q, len(keep), time.time() - t0), flush=True)
    head = list(rows[0].keys())
    write_tsv(os.path.join(OUT, "pairs_feat.tsv"), head, rows)
    print("готово: pairs_feat.tsv, %d пар, %.0f с" % (len(rows), time.time() - t0))


# ---------------------------------------------------------------- классы пар

HUMAN_SRC = ("V4_CONTROL", "FAMILY_HUMAN")
TRUTH_SRC = HUMAN_SRC + ("TRUTH_V2", "HOLDOUT_V4", "HOLDOUT_V5", "HOLDOUT_V7")


def fl(r, k):
    return float(r[k])


def turned_proof(r):
    """Объём LOFT доказывает поворот: форма несимметрична, после поворота на 90 совпала, как есть - нет
    (тот же критерий, что obj_struct.alt_view для ALT_VIEW_HIGH)."""
    return fl(r, "vox_sym") >= 0 and fl(r, "vox_sym") < 0.9 and fl(r, "vox_turned") >= 0.85 and \
        fl(r, "vox_turned") >= fl(r, "vox_same") + 0.15


def local_class(r):
    """Класс пары по своим признакам, без прежних ярлыков. -> (класс, довод)."""
    lk = r["links"]
    if "ANIMATION" in lk:
        return "ANIMATION", "одна запись MCD"
    if "DESTROYED" in lk:
        return "DESTROYED", "die записи MCD"
    if "STATE" in lk or "DOOR" in lk:
        return "STATE_VARIANT", "alt записи MCD / state_variants"
    if r["exact"] == "1":
        return "EXACT_COPY", "пиксели равны"
    if r["flip_exact"] == "1":
        return "MIRROR", "побайтовое отражение"
    if r["class_a"] not in OBJECTISH or r["class_b"] not in OBJECTISH:
        return "STRUCTURAL_PART", "класс %s / %s" % (r["class_a"], r["class_b"])
    if r["nature"] == "1":
        return "NOT_OBJECT", "природа"
    si, sif = fl(r, "siou"), fl(r, "siou_flip")
    if sif >= 0.97 and fl(r, "relight") < 25 and fl(r, "hue") < 70 and sif > si:
        # в изометрии поворот на 90 тоже отражает силуэт: зеркало - только когда цвет отражённого - функция цвета
        # (те же детали); иначе это зеркало или другой бок (контроль MANSIONFURNITURE_MAG:3/2: ff 0.49)
        if fl(r, "ff_ab") >= 0.95:
            return "MIRROR", "силуэт отражён %.2f, свет переносится %.1f, цвет %.3f" % (sif, fl(r, "relight"), fl(r, "ff_ab"))
        return "UNCERTAIN", "MIRROR_OR_OTHER_VIEW: силуэт отражён %.2f, свет %.1f, цвет %.3f" % (sif, fl(r, "relight"), fl(r, "ff_ab"))
    if si >= 0.98 and max(fl(r, "f_ab"), fl(r, "f_ba")) >= 0.98:
        return "RECOLOR", "силуэт %.2f, цвет - функция %.3f" % (si, max(fl(r, "f_ab"), fl(r, "f_ba")))
    if sif >= 0.98 and fl(r, "ff_ab") >= 0.98:
        return "MIRROR", "отражение с перекраской %.3f" % fl(r, "ff_ab")
    cd = int(r["core_diff"])
    col = fl(r, "color")
    why = "цвет %.2f, физика %s, объём %s/%s, dh %s" % (col, cd, r["vox_turned"], r["vox_same"], r["dh"])
    if cd >= 2 or col < 0.5 or int(r["dh"]) > 8 or fl(r, "area_ratio") < 0.6:
        return "DIFFERENT_OBJECT", why
    if turned_proof(r) and cd == 0 and col >= 0.8 and int(r["dh"]) <= 2 and fl(r, "area_ratio") >= 0.85:
        return "OTHER_VIEW_SURE", "поворот доказан объёмом; " + why
    return "UNCERTAIN", why


def known_class(labs):
    """Прежние ярлыки пары -> (класс, источник) по старшинству: человек, эталоны, V4 (Codex), семейства."""
    order = (HUMAN_SRC, ("TRUTH_V2", "HOLDOUT_V4", "HOLDOUT_V5", "HOLDOUT_V7"), ("V4_POOL_CODEX",), ("FAMILY_AUTO",))
    for grp in order:
        ls = [(s, l) for s, l in labs if s in grp and l not in ("OLD_MIRRORED", "OLD_DERIVED", "OLD_ATTACHMENT")]
        if ls:
            s, l = ls[0]
            return {"NONE": "DIFFERENT_OBJECT"}.get(l, l), s
    return "", ""


def do_classify(a):
    t0 = time.time()
    import obj_struct as os_
    rows = read_tsv(os.path.join(OUT, "pairs_feat.tsv"))
    known = known_labels()
    cal = Counter()
    out = []
    # канонический другой бок проекта (obj_struct.alt_view: физика MCD, объём LOFT, силуэт, цвет) - на всех
    # парах узкого графа; info собирается из features.npz, цвет - сходство материала этого реестра
    z, j = load_features()
    kidx = {m["key"]: i for i, m in enumerate(j["frames"])}
    infos = {}

    def sinfo(k):
        if k not in infos:
            i = kidx[k]
            a_ = z["A"][i]
            inf = {"rec": bool(z["has_rec"][i])}
            if inf["rec"]:
                inf["phys"] = {kk: int(v) for kk, v in zip(j["phys_key"], z["phys"][i])}
                inf["vox"] = z["vox"][i]
            m_ = a_[..., 3] > 0
            inf.update(os_.silhouette(m_))
            inf["col"] = a_[..., :3][m_].mean(0).astype(np.float64) if m_.any() else np.zeros(3)
            infos[k] = inf
        return infos[k]
    altc = Counter()
    # связи SURE, снятые по листу групп (Vitali 07.10): камни и природа -> NOT_OBJECT, сомнительные группы ->
    # UNCERTAIN (точность важнее охвата); снимаются на уровне пары рангов, со всеми кадрами
    vrej = {}
    for v in read_tsv(os.path.join(OUT, "sure_overrides.tsv")):
        vrej[(v["a"], v["b"])] = vrej[(v["b"], v["a"])] = v["to"]
    vrej_rk = {}
    for r in rows:
        if (r["a"], r["b"]) in vrej:
            x, y = int(r["rank_a"]), int(r["rank_b"])
            vrej_rk[(min(x, y), max(x, y))] = vrej[(r["a"], r["b"])]
    print("снято по листу: %d связей, пар рангов %d %s" % (len(vrej) // 2, len(vrej_rk), dict(Counter(vrej_rk.values()))))
    if len(vrej_rk) < len(vrej) // 2 - 2:
        raise SystemExit("sure_overrides.tsv: часть пар не найдена в узком графе")
    for r in rows:
        acls, ascore, _ = os_.alt_view(sinfo(r["a"]), sinfo(r["b"]), fl(r, "color"))
        r["alt_view"], r["alt_score"] = acls, ascore
        loc, why = local_class(r)
        kc, ks = known_class(known.get((min(r["a"], r["b"]), max(r["a"], r["b"])), []))
        if kc:
            cal[(ks, kc, loc)] += 1
        final, src = loc, "LOCAL"
        labs = known.get((min(r["a"], r["b"]), max(r["a"], r["b"])), [])
        det = [l for s, l in labs if s == "DETECTOR"]
        rej = any(s == "ALT_REJECTED" for s, l in labs)
        if rej:
            cal[("ALT_REJECTED", kc or "-", loc)] += 1
        if det and ks not in HUMAN_SRC:
            # связь MCD детектора: состояние, разрушенный вид или анимация - не другой бок
            final, src = det[0], "DETECTOR"
        elif rej and ks not in HUMAN_SRC and loc in ("UNCERTAIN", "OTHER_VIEW_SURE") and kc != "OTHER_VIEW":
            # отказ alt_view машины: неясную пару закрывает, с поворотом по объёму - спор, остаётся неясной
            final, src = ("DIFFERENT_OBJECT", "ALT_REJECTED") if loc == "UNCERTAIN" else ("UNCERTAIN", "ALT_REJECTED_CONFLICT")
        elif ks in HUMAN_SRC or (ks and ks.startswith(("TRUTH", "HOLDOUT")) and kc in ("DIFFERENT_OBJECT", "RECOLOR", "EXACT_COPY",
                                                                                   "STATE_VARIANT", "ANIMATION", "STRUCTURAL_PART")):
            final, src = ("OTHER_VIEW_SURE" if kc == "OTHER_VIEW" else kc), ks
        elif ks == "V4_POOL_CODEX" and loc in ("UNCERTAIN", "OTHER_VIEW_SURE"):
            # V4: решение Codex по листу с проверкой рендера; контроль V4 - 12% ложных OTHER_VIEW, все - зеркала,
            # а зеркала здесь отсеяны своими признаками раньше
            final, src = ("OTHER_VIEW_SURE" if kc == "OTHER_VIEW" else kc), ks
        if kc:
            cal[("ALT_VIEW:" + ks, kc, acls)] += 1
        altc[(loc, acls)] += 1
        if src == "ALT_REJECTED" and final == "DIFFERENT_OBJECT":
            # alt_rejected.tsv - тот же obj_struct.alt_view (obj_families): не доказанный отказ, а низкий приоритет
            final = "ALT_VIEW_DEFERRED"
        if src == "LOCAL" and final == "UNCERTAIN" and acls == os_.ALT_REJECT:
            # alt_view терял 2 из 50 известных OTHER_VIEW: отказ - отложенная очередь, а не NOT_OTHER_VIEW (Vitali 07.10)
            final, src = "ALT_VIEW_DEFERRED", "ALT_VIEW_REJECT"
        elif src == "LOCAL" and final == "OTHER_VIEW_SURE" and acls != os_.ALT_HIGH:
            final, src = "UNCERTAIN", "ALT_VIEW_NOT_HIGH"
        x_, y_ = int(r["rank_a"]), int(r["rank_b"])
        to = vrej_rk.get((min(x_, y_), max(x_, y_)))
        if to and final in ("OTHER_VIEW_SURE", "UNCERTAIN", "ALT_VIEW_DEFERRED"):
            final, src = to, "VITALI_SHEET"
        r2 = dict(r)
        r2.update(local=loc, local_why=why, known_class=kc, known_src=ks, final=final, final_src=src)
        out.append(r2)
    head = list(out[0].keys())
    write_tsv(os.path.join(OUT, "pairs_classified.tsv"), head, out)
    c = Counter(r["final"] for r in out)
    print("пар: %d" % len(out))
    for k_, v_ in c.most_common():
        print("  %-34s %d" % (k_, v_))
    print("локальный класс x alt_view:")
    for (lc, ac), v_ in sorted(altc.items()):
        print("  %-18s %-18s %d" % (lc, ac, v_))
    print("по источнику итога:", dict(Counter((r["final"], r["final_src"]) for r in out if r["final_src"].startswith("ALT"))))
    print("калибровка (источник, ярлык, локальный класс):")
    for (s, l, lc), v_ in sorted(cal.items()):
        print("  %-14s %-34s %-18s %d" % (s, l, lc, v_))
    dump({"final": dict(c), "calibration": [[s, l, lc, v_] for (s, l, lc), v_ in sorted(cal.items())]},
         os.path.join(OUT, "classify_stat.json"))
    print("%.0f с" % (time.time() - t0))


# ---------------------------------------------------------------- группы, пробелы

STRONG_NEG_SRC = HUMAN_SRC + ("TRUTH_V2", "HOLDOUT_V4", "HOLDOUT_V5", "HOLDOUT_V7", "V4_POOL_CODEX", "VITALI_SHEET")
DERIVE = ("MIRROR", "RECOLOR", "EXACT_COPY")


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)

    def comps(self):
        out = defaultdict(set)
        for x in list(self.p):
            out[self.find(x)].add(x)
        return out


def accepted_assets():
    """Ассеты с принятым HD-рендером (v1 и restore-batch-v1 - PASS Vitali, v2 - судьи, v3/v4 - закрытые)."""
    acc = {}
    for p, col, ok in ((os.path.join(PROBES, "prod-two-pass-v1", "verdicts_vitali.tsv"), "verdict", ("PASS",)),
                       (os.path.join(PROBES, "restore-batch-v1", "verdicts_vitali.tsv"), "verdict", ("PASS",)),
                       (os.path.join(PROBES, "prod-two-pass-v2", "final.tsv"), "status", ("ACCEPTED_BY_JUDGES",)),
                       (os.path.join(PROBES, "prod-two-pass-v3", "status.tsv"), "status", ("ACCEPTED_CLOSED",)),
                       (os.path.join(PROBES, "prod-two-pass-v4", "status.tsv"), "status", ("ACCEPTED_CLOSED",))):
        for r in read_tsv(p):
            if r.get(col) in ok:
                acc[r["asset_id"].upper()] = os.path.basename(os.path.dirname(p))
    return acc


def strong_negative(r):
    if r["final"] == "SAME_FRAMEWORK_DIFFERENT_OBJECT":
        return True     # решение человека по V4 (SF): как ракурс не всплывает никогда
    if r["final"] in ("DIFFERENT_OBJECT", "SAME_FRAMEWORK_DIFFERENT_OBJECT", "NOT_OBJECT") and r["final_src"] in STRONG_NEG_SRC:
        return True
    return r["local"] == "DIFFERENT_OBJECT" and (int(r["core_diff"]) >= 2 or float(r["color"]) < 0.4)


def do_groups(a):
    t0 = time.time()
    meta = load(os.path.join(OUT, "features.json"))["frames"]
    byk = {m["key"]: m for m in meta}
    rank_m = defaultdict(list)
    for m in meta:
        rank_m[m["rank"]].append(m)
    rows = read_tsv(os.path.join(OUT, "pairs_classified.tsv"))
    acc = accepted_assets()
    aid = {rk: ms[0]["asset_id"].upper() for rk, ms in rank_m.items()}

    def rk(r, s):
        return int(r["rank_" + s])
    by_rank_pair = defaultdict(list)
    for r in rows:
        x, y = rk(r, "a"), rk(r, "b")
        if x != y:
            by_rank_pair[(min(x, y), max(x, y))].append(r)
    override = []
    known = known_labels()
    for (ka, kb), ls in known.items():
        hs = sorted({s_ for s_, l_ in ls if l_ == "OTHER_VIEW" and s_ in HUMAN_SRC})
        if not hs:
            continue
        if ka not in byk or kb not in byk:
            override.append([ka, kb, "+".join(hs), "кадра нет во вселенной (не в очереди предметов)", "OUT_OF_UNIVERSE"])
            continue
        x, y = byk[ka]["rank"], byk[kb]["rank"]
        if x == y:
            override.append([ka, kb, "+".join(hs), "один ассет", "SAME_ASSET"])
            continue
        rs = by_rank_pair[(min(x, y), max(x, y))]
        if any(r["final"] == "OTHER_VIEW_SURE" for r in rs):
            rej = [r for r in rs if r.get("alt_view") == "REJECT"]
            if rej:
                override.append([ka, kb, "+".join(hs), "SURE по решению человека, хотя alt_view REJECT (фильтр вокселей)",
                                 "KEPT_OVER_VOXELS"])
            continue
        why = "известный OTHER_VIEW (%s), в узком графе: %s" % ("+".join(hs), ", ".join(sorted({r["final"] for r in rs})) or "нет")
        rs.insert(0, {"a": ka, "b": kb, "final": "OTHER_VIEW_SURE", "final_src": "KNOWN_OVERRIDE", "local": "OTHER_VIEW_SURE",
                      "local_why": why, "core_diff": "0", "color": "1", "siou": "-1", "siou_flip": "-1"})
        override.append([ka, kb, "+".join(hs), why, "INJECTED"])
    print("known_override (подтверждённые человеком OTHER_VIEW): %s" % dict(Counter(o[4] for o in override)))
    for o in override:
        print("  ", o)
    dump(override, os.path.join(OUT, "known_override.json"))
    sure = UF()
    for (x, y), rs in by_rank_pair.items():
        if any(r["final"] == "OTHER_VIEW_SURE" for r in rs) and not any(strong_negative(r) for r in rs):
            sure.union(x, y)
    cand = UF()
    for (x, y), rs in by_rank_pair.items():
        if any(r["final"] in ("OTHER_VIEW_SURE", "UNCERTAIN") for r in rs) and not any(strong_negative(r) for r in rs):
            cand.union(x, y)

    def members_info(ranks):
        return [{"asset_id": aid[x], "rank": x, "frames": [m["key"] for m in rank_m[x]], "kind": rank_m[x][0]["kind"],
                 "places": rank_m[x][0]["places"], "identity": rank_m[x][0]["identity"][:80],
                 "accepted_hd": acc.get(aid[x], "")} for x in sorted(ranks)]

    def build(uf, label, prefix):
        groups = []
        for root, ranks in sorted(uf.comps().items(), key=lambda kv: (-len(kv[1]), kv[0])):
            if len(ranks) < 2:
                continue
            ev, neg, derived = [], [], []
            for (x, y), rs in by_rank_pair.items():
                if x in ranks and y in ranks:
                    for r in rs:
                        if r["final"] in ("OTHER_VIEW_SURE", "UNCERTAIN"):
                            ev.append([r["a"], r["b"], r["final"], r["final_src"], r["local_why"][:90]])
                        elif strong_negative(r) or r["final"] in ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "DIFFERENT_OBJECT"):
                            neg.append([r["a"], r["b"], r["final"], r["final_src"]])
                elif (x in ranks) != (y in ranks):
                    for r in rs:
                        if r["final"] in DERIVE:
                            derived.append([r["a"], r["b"], r["final"], r["final_src"]])
            mem = members_info(ranks)
            can = max(mem, key=lambda m: (bool(m["accepted_hd"]), m["places"], -m["rank"]))
            ok_src = Counter(e[3] for e in ev if e[2] == "OTHER_VIEW_SURE")
            conf = "HIGH" if ok_src and not neg and set(ok_src) <= set(HUMAN_SRC + ("LOCAL", "V4_POOL_CODEX", "KNOWN_OVERRIDE")) else "MEDIUM"
            if neg:
                conf = "CONFLICT"
            # ракурс относительно канона: силуэт отражён (поворот на 90) или тот же (180 / симметричная вещь)
            for m in mem:
                m["view"] = "canonical" if m is can else "?"
                if m is can:
                    continue
                for (x, y), rs in by_rank_pair.items():
                    if {x, y} == {m["rank"], can["rank"]}:
                        r = rs[0]
                        m["view"] = "TURN_90 (силуэт отражён)" if float(r["siou_flip"]) > float(r["siou"]) + 0.05 else \
                            ("TURN_180_OR_SYMMETRIC" if float(r["siou"]) > float(r["siou_flip"]) + 0.05 else "TURN_UNKNOWN")
                if m["view"] == "?":
                    m["view"] = "через цепочку"
            groups.append({"label": label, "canonical": can["asset_id"], "n": len(mem), "confidence": conf,
                           "members": mem, "evidence": ev, "excluded_false_links": neg, "derived_outside": derived,
                           "sources": dict(Counter(e[3] for e in ev))})
        for i, g in enumerate(groups, 1):
            g["id"] = "%s_%04d" % (prefix, i)
        return groups
    gs = build(sure, "OTHER_VIEW_SURE", "OBJECT_GROUP")
    in_sure = {m["rank"] for g in gs for m in g["members"]}
    gc = [g for g in build(cand, "CANDIDATE_CLUSTER", "CANDIDATE") if any(m["rank"] not in in_sure for m in g["members"])
          or any(e[2] == "UNCERTAIN" for e in g["evidence"])]
    dump(gs, os.path.join(OUT, "groups.json"))
    dump(gc, os.path.join(OUT, "candidate_clusters.json"))

    # пробелы: третий и четвёртый вид - соседи по номеру в наборе и кадры, связанные с двумя членами
    obj_keys = {m["key"] for m in meta if m["asset_class"] in OBJECTISH and not nature(m)}
    by_set = defaultdict(dict)
    for m in meta:
        s, f = split(m["key"])
        by_set[s][f] = m
    pair_of = {}
    for r in rows:
        pair_of[(r["a"], r["b"])] = r
        pair_of[(r["b"], r["a"])] = r
    gaps = []
    for g in gs + gc:
        ranks = {m["rank"] for m in g["members"]}
        keys = [k for m in g["members"] for k in m["frames"]]
        seen = set()
        for k in keys:
            s, f = split(k)
            for d in (-3, -2, -1, 1, 2, 3):
                nm = by_set[s].get(f + d)
                if not nm or nm["rank"] in ranks or nm["key"] in seen or nm["key"] not in obj_keys:
                    continue
                seen.add(nm["key"])
                r = pair_of.get((k, nm["key"]))
                gaps.append({"group": g["id"], "member": k, "neighbour": nm["key"], "why": "сосед по номеру %+d" % d,
                             "pair_class": r["final"] if r else "НЕТ_В_ГРАФЕ",
                             "color": r["color"] if r else "", "siou": r["siou"] if r else "",
                             "siou_flip": r["siou_flip"] if r else "", "identity": nm["identity"][:60]})
        link = Counter()
        for (x, y), rs in by_rank_pair.items():
            if (x in ranks) == (y in ranks):
                continue
            o = y if x in ranks else x
            if any(r["final"] in ("UNCERTAIN", "OTHER_VIEW_SURE") for r in rs):
                link[o] += 1
        for o, c in link.items():
            if c >= 2 and o not in in_sure:
                gaps.append({"group": g["id"], "member": "", "neighbour": aid[o], "why": "связан с %d членами" % c,
                             "pair_class": "UNCERTAIN", "identity": rank_m[o][0]["identity"][:60]})
    write_tsv(os.path.join(OUT, "gaps.tsv"), ["group", "member", "neighbour", "why", "pair_class", "color", "siou",
                                             "siou_flip", "identity"], gaps)
    sz = Counter(min(g["n"], 4) for g in gs)
    print("групп OTHER_VIEW_SURE: %d, ассетов %d; по числу видов 2/3/4+: %s" % (len(gs), len(in_sure),
                                                                              [sz[2], sz[3], sz[4]]))
    print("  уверенность: %s" % dict(Counter(g["confidence"] for g in gs)))
    csz = Counter(min(g["n"], 10) for g in gc)
    print("кластеров-кандидатов: %d, ассетов %d; размеры %s" % (len(gc), len({m["rank"] for g in gc for m in g["members"]}),
                                                               sorted(csz.items())))
    print("пробелов: %d (%s)" % (len(gaps), dict(Counter(x["pair_class"] for x in gaps))))
    print("%.0f с" % (time.time() - t0))


# ---------------------------------------------------------------- отчёт и листы

def group_sheet(groups, A, kidx, path, title, per_page=24, scale=3):
    """Лист: строка - группа, кадры членов (первый кадр каждого ассета) на тёмном полу, подписи."""
    from PIL import Image, ImageDraw
    pages = []
    for p0 in range(0, len(groups), per_page):
        gs = groups[p0:p0 + per_page]
        cols = max(min(len(g["members"]), 8) for g in gs)
        cw, ch = 32 * scale + 8, 40 * scale + 26
        W, Hh = 170 + cols * cw, 22 + len(gs) * ch
        im = Image.new("RGB", (W, Hh), (34, 36, 40))
        d = ImageDraw.Draw(im)
        d.text((6, 4), "%s  (%d-%d из %d)" % (title, p0 + 1, p0 + len(gs), len(groups)), fill=(230, 230, 230))
        for gi, g in enumerate(gs):
            y = 22 + gi * ch
            d.text((4, y + 4), g["id"], fill=(240, 220, 120))
            d.text((4, y + 18), "%s, %d" % (g["confidence"], g["n"]), fill=(200, 200, 200))
            d.text((4, y + 32), (g["members"][0]["identity"] or "")[:26], fill=(160, 160, 160))
            for mi, m in enumerate(g["members"][:8]):
                k = m["frames"][0]
                if k not in kidx:
                    continue
                spr = Image.fromarray(A[kidx[k]]).resize((32 * scale, 40 * scale), Image.NEAREST)
                x = 170 + mi * cw
                bg = Image.new("RGBA", spr.size, (70, 74, 80, 255))
                bg.alpha_composite(spr)
                im.paste(bg.convert("RGB"), (x, y))
                lab = k + (" *" if m["accepted_hd"] else "")
                d.text((x, y + 40 * scale + 2), lab[:16], fill=(255, 255, 255) if m["asset_id"] == g["canonical"] else (190, 190, 190))
                d.text((x, y + 40 * scale + 12), m["view"][:16], fill=(140, 180, 220))
        fn = path % (p0 // per_page + 1)
        im.save(fn)
        pages.append(fn)
    return pages


def do_report(a):
    z, j = load_features()
    meta = j["frames"]
    A = z["A"]
    kidx = {m["key"]: i for i, m in enumerate(meta)}
    rows = read_tsv(os.path.join(OUT, "pairs_classified.tsv"))
    cand = load(os.path.join(OUT, "candidates_stat.json"))
    cst = load(os.path.join(OUT, "classify_stat.json"))
    gs = load(os.path.join(OUT, "groups.json"))
    gc = load(os.path.join(OUT, "candidate_clusters.json"))
    gaps = read_tsv(os.path.join(OUT, "gaps.tsv"))
    acc = accepted_assets()
    obj = [m for m in meta if m["asset_class"] in OBJECTISH]
    fin = Counter(r["final"] for r in rows)
    src = Counter((r["final"], r["final_src"]) for r in rows)
    sure_assets = {m["asset_id"] for g in gs for m in g["members"]}
    sz = Counter(min(g["n"], 4) for g in gs)
    # прежние известные против новых
    old_ov = set()
    for g in gs:
        for e in g["evidence"]:
            if e[2] == "OTHER_VIEW_SURE" and e[3] != "LOCAL":
                old_ov.add(g["id"])
    new_g = [g for g in gs if g["id"] not in old_ov]
    v4g = load(os.path.join(V4, "v4_groups.json")) if os.path.exists(os.path.join(V4, "v4_groups.json")) else []
    # рендер: что можно связать с принятым видом и что выводится зеркалом / перекраской
    with_acc = [g for g in gs if any(m["accepted_hd"] for m in g["members"])]
    link_assets = sum(sum(1 for m in g["members"] if not m["accepted_hd"]) for g in with_acc)
    derived = {(d[0], d[1], d[2]) for g in gs for d in g["derived_outside"]}
    unc_pairs = fin.get("UNCERTAIN", 0)
    unc_clusters = [g for g in gc if any(e[2] == "UNCERTAIN" for e in g["evidence"])]
    unc_cl_pairs = sum(sum(1 for e in g["evidence"] if e[2] == "UNCERTAIN") for g in unc_clusters)
    per_call = 12
    calls = -(-unc_cl_pairs // per_call)
    # сводка по шагам: каждая пара узкого графа - ровно в одной строке
    step = Counter()
    for r in rows:
        f, s = r["final"], r["final_src"]
        if s == "VITALI_SHEET":
            step["vitali"] += 1
        elif f == "OTHER_VIEW_SURE":
            step["sure"] += 1
        elif f == "UNCERTAIN":
            step["unc"] += 1
        elif f == "ALT_VIEW_DEFERRED":
            step["altview" if s == "ALT_VIEW_REJECT" else "rejected"] += 1
        elif s in ("V4_POOL_CODEX", "V4_CONTROL", "FAMILY_HUMAN"):
            step["v4"] += 1
        elif s.startswith(("TRUTH", "HOLDOUT")):
            step["truth"] += 1
        elif s == "DETECTOR" or f in ("ANIMATION", "DESTROYED", "STATE_VARIANT"):
            step["mcd"] += 1
        elif f in ("EXACT_COPY", "MIRROR", "RECOLOR"):
            step["copy"] += 1
        else:
            step["local"] += 1
    # очередь к судье: неясные пары в кластерах по довод / без довода / природа и куски
    flags = {m["key"]: set(m["flags"]) for m in meta}
    rowd = {(r["a"], r["b"]): r for r in rows}
    known = known_labels()
    tier = Counter()
    for g in unc_clusters:
        for e in g["evidence"]:
            if e[2] != "UNCERTAIN":
                continue
            r = rowd.get((e[0], e[1])) or rowd.get((e[1], e[0]))
            fa, fb = flags.get(e[0], set()), flags.get(e[1], set())
            if (fa | fb) & {"nature", "fragment_suspect"}:
                tier["C"] += 1
            elif r and (r["local_why"].startswith("MIRROR_OR_OTHER_VIEW") or r.get("alt_view") == "ALT_VIEW_HIGH"
                        or any(l == "OTHER_VIEW_CANDIDATE" for _, l in known.get((min(e[0], e[1]), max(e[0], e[1])), []))):
                tier["A"] += 1
            else:
                tier["B"] += 1
    big = sorted(gs, key=lambda g: -g["n"])[:15]
    bigc = sorted(gc, key=lambda g: -g["n"])[:10]
    sheets = group_sheet(sorted(gs, key=lambda g: (-g["n"], g["id"])), A, kidx,
                         os.path.join(OUT, "sheet_groups_%02d.png"), "OTHER_VIEW_SURE")
    sheets_c = group_sheet(sorted(unc_clusters, key=lambda g: (-g["n"], g["id"]))[:96], A, kidx,
                           os.path.join(OUT, "sheet_candidates_%02d.png"), "CANDIDATE (UNCERTAIN)")
    L = []
    w = L.append
    w("# OTHER_VIEW_REGISTRY_V1 - реестр «один предмет с разных сторон»")
    w("")
    w("Дата 2026-10-07. Без Codex, без видеокарты. Инструмент tools/hdart/other_view_registry.py (features, pairs, pairfeat, classify, groups, report).")
    w("")
    w("## Сводка до Codex")
    w("")
    w("| | |")
    w("|---|---|")
    w("| всего кадров-предметов (object, object_or_relief) | %d |" % len(obj))
    w("| исходных пар-кандидатов (граф высокого охвата) | %d |" % cand["by_features"])
    w("| после второго дешёвого отсева (узкий граф: набор, блоки карт, материал, физика MCD, силуэт) | %d |" % len(rows))
    w("| отложено ALT_VIEW_DEFERRED: obj_struct.alt_view REJECT (LOFT, MCD, силуэт при повороте) - не отказ, низкий приоритет | %d |" % step["altview"])
    w("| исключено своими признаками (другая физика, цвет, высота, площадь; не предмет; природа) | %d |" % step["local"])
    w("| исключено exact / mirror / recolor (пиксели, отражение, relation_probe.func_map) | %d |" % step["copy"])
    w("| исключено связями MCD (анимация, die, alt; детекторы в обе стороны) | %d |" % step["mcd"])
    w("| отложено ALT_VIEW_DEFERRED: прежний отказ alt_view в семействах (families/alt_rejected.tsv) | %d |" % step["rejected"])
    w("| снято с листа групп SURE (sure_overrides.tsv: камни и коралл -> NOT_OBJECT, G0006/G0008/G0011 -> UNCERTAIN) | %d |" % step["vitali"])
    w("| решено эталонами связей (truth v2, holdout v4/v5/v7) | %d |" % step["truth"])
    w("| решено V4 (контроль человека, пул Codex V4 вкл. SFDO) и семействами человека | %d |" % step["v4"])
    w("| осталось: OTHER_VIEW_SURE | %d |" % step["sure"])
    w("| осталось: UNCERTAIN | %d |" % step["unc"])
    w("| групп OTHER_VIEW (SURE) | %d (ассетов %d) |" % (len(gs), len(sure_assets)))
    w("| групп по 2 / 3 / 4+ вида | %d / %d / %d |" % (sz.get(2, 0), sz.get(3, 0), sz.get(4, 0)))
    w("| высокая уверенность (HIGH) / спор (CONFLICT) | %d / %d |" % (sum(g["confidence"] == "HIGH" for g in gs),
                                                                  sum(g["confidence"] == "CONFLICT" for g in gs)))
    w("| кластеров-кандидатов с UNCERTAIN | %d, пар в них %d |" % (len(unc_clusters), unc_cl_pairs))
    w("")
    w("V3 / V3SF / V4 status.tsv - статусы рендера по ассетам, а не связи пар: они дают canonical (принятый HD), "
      "а не исключение пар. SF-пары V4 (pool_cls/classified.tsv) - в строке V4; из них в узкий граф попало %d."
      % sum(1 for r in rows if r["final"] == "SAME_FRAMEWORK_DIFFERENT_OBJECT"))
    w("")
    w("## Охват")
    w("")
    w("| | |")
    w("|---|---|")
    w("| строк очереди предметов (items.json) | %d рангов |" % len({m["rank"] for m in meta}))
    w("| кадров проверено (куски составных отдельно, копии слиты) | %d |" % len(meta))
    w("| из них кадров-предметов (object, object_or_relief) - перебор всех пар | %d |" % len(obj))
    w("| пар перебора | %d |" % (len(obj) * (len(obj) - 1) // 2))
    w("| граф высокого охвата (силуэт/профиль, высота, низ, площадь, материал) | %d |" % cand["by_features"])
    w("| узкий граф: все пары внутри набора + пары разных наборов в одних блоках / с тем же материалом и физикой | %d |" % len(rows))
    w("")
    w("Охват графа по прежним связям (найдено признаками / не найдено / кадра нет во вселенной):")
    w("")
    w("| источник | ярлык | итог | пар |")
    w("|---|---|---|---|")
    for s_, l_, w_, c_ in cand["recall_known"]:
        w("| %s | %s | %s | %d |" % (s_, l_, w_, c_))
    w("")
    w("## Классы пар узкого графа")
    w("")
    w("| класс | пар | из них по прежнему решению (человек, эталон, V4) |")
    w("|---|---|---|")
    for k_, v_ in fin.most_common():
        w("| %s | %d | %d |" % (k_, v_, sum(c for (f, s), c in src.items() if f == k_ and s != "LOCAL")))
    w("")
    w("Калибровка локального класса по прежним ярлыкам (источник, ярлык -> локальный класс):")
    w("")
    w("| источник | ярлык | локально | пар |")
    w("|---|---|---|---|")
    for s_, l_, lc, c_ in cst["calibration"]:
        w("| %s | %s | %s | %d |" % (s_, l_, lc, c_))
    w("")
    w("## Группы OTHER_VIEW_SURE")
    w("")
    w("| | |")
    w("|---|---|")
    w("| групп | %d |" % len(gs))
    w("| ассетов в группах | %d |" % len(sure_assets))
    w("| групп по числу видов 2 / 3 / 4+ | %d / %d / %d |" % (sz[2], sz[3], sz[4]))
    w("| уверенность | %s |" % ", ".join("%s %d" % kv for kv in Counter(g["confidence"] for g in gs).most_common()))
    w("| группы с прежним подтверждением (человек, эталон, V4) | %d |" % len(old_ov))
    w("| группы, найденные заново (только локальное доказательство поворота объёмом) | %d |" % len(new_g))
    w("| группы V4 (v4_groups.json) | %d |" % len(v4g))
    w("")
    w("## Неразрешённое")
    w("")
    w("| | |")
    w("|---|---|")
    w("| пар UNCERTAIN | %d |" % unc_pairs)
    w("| кластеров-кандидатов с UNCERTAIN | %d (ассетов %d) |" % (len(unc_clusters), len({m["asset_id"] for g in unc_clusters for m in g["members"]})))
    w("| пар UNCERTAIN внутри кластеров | %d |" % unc_cl_pairs)
    w("| пробелов (соседи по номеру, третий вид) | %d |" % len(gaps))
    w("")
    # санитария SURE и заморозка реестра v1
    ovr = read_tsv(os.path.join(OUT, "sure_overrides.tsv"))
    kov = load(os.path.join(OUT, "known_override.json")) if os.path.exists(os.path.join(OUT, "known_override.json")) else []
    rec = load(os.path.join(OUT, "reconcile_copies.json"))["counts"] if os.path.exists(os.path.join(OUT, "reconcile_copies.json")) else {}
    frozen = [g for g in gs if g["confidence"] == "HIGH"]
    reg = []
    for g in frozen:
        srcs = sorted(g["sources"])
        reg.append({"group": g["id"], "canonical": g["canonical"], "n_views": g["n"],
                    "views": "; ".join("%s=%s" % (m["asset_id"], m["view"]) for m in g["members"]),
                    "evidence": "; ".join("%s~%s %s" % (e[0], e[1], e[3]) for e in g["evidence"]),
                    "confidence": g["confidence"],
                    "source": "OVERRIDE" if "KNOWN_OVERRIDE" in srcs else ("+".join(srcs)),
                    "identity": (g["members"][0].get("identity") or "")[:80]})
    write_tsv(os.path.join(OUT, "sure_registry_v1.tsv"), ["group", "canonical", "n_views", "views", "evidence",
                                                         "confidence", "source", "identity"], reg)
    w("## Санитария SURE и реестр v1")
    w("")
    w("| | |")
    w("|---|---|")
    w("| снято по листу групп (sure_overrides.tsv) | %s |" % ", ".join("%s %d" % kv for kv in Counter(o["to"] for o in ovr).most_common()))
    w("| известные OTHER_VIEW человека (known_override.json) | %s |" % ", ".join("%s %d" % kv for kv in Counter(k[4] for k in kov).most_common()))
    w("| пары SF (жёсткое исключение, strong_negative) | %d |" % fin.get("SAME_FRAMEWORK_DIFFERENT_OBJECT", 0))
    w("| отложено ALT_VIEW_DEFERRED (не удалено) | %d |" % fin.get("ALT_VIEW_DEFERRED", 0))
    w("| заморожено групп SURE v1 (HIGH) | %d, ассетов %d |" % (len(frozen), len({m["asset_id"] for g in frozen for m in g["members"]})))
    w("| групп со спором (в спорные, не в реестр) | %s |" % ", ".join(g["id"] for g in gs if g["confidence"] != "HIGH"))
    w("")
    if rec:
        w("Расхождения копий и зеркал с переписью (reconcile_copies.json, показаны только расхождения):")
        w("")
        for k, v in sorted(rec.items(), key=lambda kv: -kv[1]):
            w("- %d - %s" % (v, k))
        w("")
    sv = load(os.path.join(OUT, "sieve_clusters.json")) if os.path.exists(os.path.join(OUT, "sieve_clusters.json")) else None
    if sv:
        sm = sv["summary"]
        w("## Отсев UNCERTAIN по кластерам (без ИИ)")
        w("")
        w("| корзина пары рангов | пар | куда |")
        w("|---|---|---|")
        dest = {"NATURE_OR_FRAGMENT": "residual: природа или кусок корпуса", "NO_EVIDENCE": "residual: довода другого бока нет",
                "SAME_FRAMEWORK": "residual: тот же каркас (силуэт и объём без поворота)", "DERIVE": "residual: та же пара рангов уже зеркало / перекраска / копия",
                "INSIDE_SURE": "уже внутри группы SURE", "ATTACH": "спорные: подтянуть к группе SURE", "EVIDENCE": "спорные: есть довод",
                "KNOWN_OTHER_VIEW": "спорные: известный ярлык другого бока"}
        for k, v in sorted(sm["edges"].items(), key=lambda kv: -kv[1]):
            w("| %s | %d | %s |" % (k, v, dest.get(k, "")))
        w("")
        w("- Спорных групп: %d (ассетов %d, кадров %d, пар %d); из них подтягивают вид к группе SURE: %d." % (
            sm["disputed_clusters"], sm["disputed_assets"], sm["disputed_frames"], sm["disputed_pairs"], sm["with_attach"]))
        w("- Одиночных слабых рёбер (пара ассетов, один вид довода) в residual: %d." % sm["residual_single_weak"])
        w("- Размеры групп: %s." % ", ".join("%s - %d" % kv for kv in sorted(sm["sizes"].items(), key=lambda kv: int(kv[0]))))
        sheets_s = group_sheet([{"id": c["id"], "confidence": "+".join(c["evidence"])[:24], "n": len(c["assets"]),
                                 "canonical": c["assets"][0],
                                 "members": [{"frames": [x], "asset_id": x, "accepted_hd": False,
                                              "identity": (meta[kidx[x]]["identity"] if x in kidx else ""),
                                              "view": ""} for x in c["assets"]]}
                                for c in sv["clusters"] if c["tier"] == "DISPUTED"], A, kidx,
                               os.path.join(OUT, "sheet_disputed_%02d.png"), "Спорные группы после отсева")
        sheets_c = sheets_c + sheets_s
        w("")
    w("## Рендер")
    w("")
    w("- Групп, где хотя бы один вид уже принят в HD: %d; видов в них без принятого HD - %d: им можно взять описание опознания группы, рисовать каждый со своего спрайта (без копии и зеркала чужого HD)." % (len(with_acc), link_assets))
    w("- Выводимых перекраской / зеркалом / копией из члена группы (вне группы): %d связей." % len(derived))
    w("- OTHER_VIEW сам по себе рендер не экономит: каждый вид рисуется со своего спрайта (задание, этап 6); экономия - одно описание на группу и одна проверка согласованности.")
    w("")
    w("## Крупнейшие группы")
    w("")
    w("| группа | видов | уверенность | канон | члены |")
    w("|---|---|---|---|---|")
    for g in big:
        w("| %s | %d | %s | %s | %s |" % (g["id"], g["n"], g["confidence"], g["canonical"],
                                        ", ".join(m["asset_id"] for m in g["members"][:8])))
    w("")
    w("Крупнейшие кластеры-кандидаты:")
    w("")
    w("| кластер | ассетов | члены |")
    w("|---|---|---|")
    for g in bigc:
        w("| %s | %d | %s |" % (g["id"], g["n"], ", ".join(m["asset_id"] for m in g["members"][:10])))
    w("")
    w("## Предложение по Codex (НЕ запускалось, лимит 0)")
    w("")
    w("- Остаток для внешнего судьи: %d пар UNCERTAIN в %d кластерах." % (unc_cl_pairs, len(unc_clusters)))
    w("- По %d пар на лист - %d вызовов на один прогон; с правилом трёх голосов (R-231) - %d. Effort: medium." % (per_call, calls, calls * 3))
    w("- Очередь по ярусам (пар / вызовов x3):")
    w("  - A - довод есть (силуэт отражён без функции цвета, alt_view HIGH, кандидат семейств): %d / %d"
      % (tier["A"], 3 * -(-tier["A"] // per_call)))
    w("  - B - предметы без довода: %d / %d" % (tier["B"], 3 * -(-tier["B"] // per_call)))
    w("  - C - флаг природы или кусок корпуса: %d / %d (предлагается не судить, а отсеять человеку листом)"
      % (tier["C"], 3 * -(-tier["C"] // per_call)))
    if sv:
        w("- После отсева по кластерам (выше): %d пар в %d группах; по 12 пар на лист - %d листов, x3 голоса - %d вызовов; "
          "с 3 скрытыми контролями на лист (9 пар + 3) - %d вызовов. Effort: medium." % (
              sv["summary"]["disputed_pairs"], sv["summary"]["disputed_clusters"], sv["summary"]["sheets_12"],
              sv["summary"]["codex_calls_3_votes"], sv["summary"]["codex_calls_3_votes_with_controls"]))
    w("- До запуска нужно отдельное разрешение Vitali.")
    w("")
    w("## Файлы")
    w("")
    w("- features.npz / features.json, candidates.json, candidates_stat.json, pairs_feat.tsv, pairs_classified.tsv, classify_stat.json")
    w("- groups.json (OBJECT_GROUP_xxxx), candidate_clusters.json, gaps.tsv")
    w("- листы: " + ", ".join(os.path.basename(p) for p in sheets + sheets_c))
    txt = "\n".join(L) + "\n"
    with open(os.path.join(OUT, "REPORT.md"), "w", encoding=ENC) as f:
        f.write(txt)
    print(txt)


# ---------------------------------------------------------------- отсев UNCERTAIN по кластерам (без ИИ)

SIEVE_PAIRS_PER_SHEET = 12


def sf_suspect(r):
    """Тот же каркас: силуэт и объём совпадают без поворота, ядро и высота те же - SAME_FRAMEWORK, не другой бок."""
    return fl(r, "siou") >= 0.97 and fl(r, "vox_same") >= 0.95 and int(r["core_diff"]) == 0 and int(r["dh"]) <= 1


def do_sieve(a):
    """Каждую пару рангов с UNCERTAIN - в одну корзину; спорными остаются кластеры, где довод другого бока
    есть и он не одиночный. Остальное - residual с причиной, ничего не удаляется."""
    rows = read_tsv(os.path.join(OUT, "pairs_classified.tsv"))
    meta = {m["key"]: m for m in load(os.path.join(OUT, "features.json"))["frames"]}
    gs = load(os.path.join(OUT, "groups.json"))
    sure_rank = {m["rank"]: g["id"] for g in gs for m in g["members"] if g["confidence"] == "HIGH"}
    known = known_labels()
    by_rp = defaultdict(list)
    for r in rows:
        x, y = int(r["rank_a"]), int(r["rank_b"])
        by_rp[(min(x, y), max(x, y))].append(r)

    def kinds(p):
        k = set()
        for r in by_rp[p]:
            if r["final"] != "UNCERTAIN":
                continue
            if r["local_why"].startswith("MIRROR_OR_OTHER_VIEW"):
                k.add("SIL_MIRROR")
            if r["alt_view"] == "ALT_VIEW_HIGH":
                k.add("ALT_HIGH")
            if any(l == "OTHER_VIEW_CANDIDATE" for _, l in known.get(tuple(sorted((r["a"], r["b"]))), [])):
                k.add("CAND")
        return k

    edge = {}
    for p, rs in by_rp.items():
        unc = [r for r in rs if r["final"] == "UNCERTAIN"]
        if not unc or p[0] == p[1]:
            continue
        finals = {r["final"] for r in rs}
        flags = set()
        for r in unc:
            flags |= set(meta[r["a"]]["flags"]) | set(meta[r["b"]]["flags"])
        k = kinds(p)
        if any(r["known_class"] == "OTHER_VIEW" for r in unc):
            v = "KNOWN_OTHER_VIEW"     # известный ярлык другого бока отсев не снимает
            k = k | {"KNOWN_OV"}
        elif finals & set(DERIVE):
            v = "DERIVE"
        elif flags & {"nature", "fragment_suspect"}:
            v = "NATURE_OR_FRAGMENT"
        elif any(sf_suspect(r) for r in unc):
            v = "SAME_FRAMEWORK"
        elif p[0] in sure_rank and p[1] in sure_rank and sure_rank[p[0]] == sure_rank[p[1]]:
            v = "INSIDE_SURE"
        elif p[0] in sure_rank or p[1] in sure_rank:
            v = "ATTACH"
        elif k:
            v = "EVIDENCE"
        else:
            v = "NO_EVIDENCE"
        edge[p] = (v, k)
    keep = [p for p, (v, k) in edge.items() if v in ("ATTACH", "EVIDENCE", "KNOWN_OTHER_VIEW")]
    uf = UF()
    for x, y in keep:
        uf.union(x, y)
    comp = defaultdict(list)
    for p in keep:
        comp[uf.find(p[0])].append(p)
    aid, rank_keys = {}, defaultdict(set)
    for m in meta.values():
        rank_keys[m["rank"]].add(m["key"])
    for r in rows:
        aid.setdefault(int(r["rank_a"]), r["a"])
        aid.setdefault(int(r["rank_b"]), r["b"])
    clusters, out_edges = [], []
    for ps in comp.values():
        ranks = sorted({x for p in ps for x in p})
        kk = set()
        for p in ps:
            kk |= edge[p][1] | ({"ATTACH"} if edge[p][0] == "ATTACH" else set())
        weak = len(ranks) == 2 and len(kk) == 1 and kk != {"ATTACH"}
        clusters.append({"ranks": ranks, "assets": [aid[x] for x in ranks], "pairs": [[aid[x], aid[y]] for x, y in ps],
                         "evidence": sorted(kk), "attach_to": sorted({sure_rank[x] for x in ranks if x in sure_rank}),
                         "tier": "RESIDUAL_SINGLE_WEAK" if weak else "DISPUTED"})
    for g in gs:
        if g["confidence"] != "HIGH":
            clusters.append({"ranks": sorted(m["rank"] for m in g["members"]), "assets": [m["asset_id"] for m in g["members"]],
                             "pairs": [e[:2] for e in g["evidence"]] + [e[:2] for e in g["excluded_false_links"]],
                             "evidence": ["SURE_GROUP_" + g["confidence"]], "attach_to": [g["id"]], "tier": "DISPUTED"})
    clusters.sort(key=lambda c: (c["tier"], -len(c["ranks"]), c["assets"][0]))
    for i, c in enumerate(clusters, 1):
        c["id"] = "SIEVE_%04d" % i
    for p, (v, k) in sorted(edge.items()):
        out_edges.append({"a": aid[p[0]], "b": aid[p[1]], "sieve": v, "evidence": "+".join(sorted(k))})
    write_tsv(os.path.join(OUT, "sieve_edges.tsv"), ["a", "b", "sieve", "evidence"], out_edges)
    dis = [c for c in clusters if c["tier"] == "DISPUTED"]
    npairs = sum(len(c["pairs"]) for c in dis)
    summ = {"edges": dict(Counter(v for v, k in edge.values())),
            "disputed_clusters": len(dis), "disputed_assets": len({x for c in dis for x in c["ranks"]}),
            "disputed_frames": len({k for c in dis for x in c["ranks"] for k in rank_keys[x]}),
            "disputed_pairs": npairs,
            "residual_single_weak": sum(c["tier"] == "RESIDUAL_SINGLE_WEAK" for c in clusters),
            "sizes": dict(Counter(min(len(c["ranks"]), 10) for c in dis)),
            "evidence": dict(Counter("+".join(c["evidence"]) for c in dis)),
            "with_attach": sum(bool(c["attach_to"]) for c in dis),
            "sheets_12": -(-npairs // SIEVE_PAIRS_PER_SHEET),
            "sheets_9_plus_3_controls": -(-npairs // 9)}
    summ["codex_calls_3_votes"] = summ["sheets_12"] * 3
    summ["codex_calls_3_votes_with_controls"] = summ["sheets_9_plus_3_controls"] * 3
    dump({"summary": summ, "clusters": clusters}, os.path.join(OUT, "sieve_clusters.json"))
    print(json.dumps(summ, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("features", "pairs", "pairfeat", "classify", "groups", "sieve", "report"))
    a = ap.parse_args()
    {"features": do_features, "pairs": do_pairs, "pairfeat": do_pairfeat, "classify": do_classify,
     "groups": do_groups, "sieve": do_sieve, "report": do_report}[a.cmd](a)


if __name__ == "__main__":
    main()
