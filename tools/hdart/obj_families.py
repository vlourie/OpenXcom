#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Семейства предметов: одна вещь в разных цветах, повёрнутая, другим боком - рисуются вместе.

29.09 Vitali на листе отеля: синее и красное кресло - ОДИН предмет, раскрашенный по-разному; стулья
рядом - один стул, повёрнутый; стол из шести одинаковых частей обязан выглядеть одинаковым. obj_queue
ловит только побайтовое зеркало и точную перекраску (тот же рисунок цветов), а у Пираток перекраска
почти всегда с другим числом оттенков, зеркало - со светом на той же стороне (R-054). Поэтому кресла
FRNITURE 8/9 и стулья FRNITURE 2/3 ушли в партию отдельными заказами и вышли разными вещами.

Pipeline v2 (docs/HD_PIPELINE_V2.md, разделы 3-5): похожесть не транзитивна. Граф попарных связей
служит только ПОИСКУ кандидатов (связная компонента), а в семейство автоматически входит лишь тот, кто
прошёл сравнение НАПРЯМУЮ с каноническим кадром. Прошёл только через соседа (A~B, B~C, A!~C) -
REVIEW_REQUIRED, причина indirect_chain; мостов нет. Каноническим берётся самая частая строка компоненты
(наименьший номер очереди). Решения человека - decisions.tsv рядом с выходом, применяются при сборке.

Связи (relation), проверка кусок к куску, составные - в своём порядке:
  recolor        - силуэт тот же (IoU масок), рисунок яркости и краёв тот же, цвет другой;
  mirror         - силуэт тот же после поворота; geometry mirrored, lighting preserve_world_direction;
  mirror (слабое) - свет оставлен на своей стороне и цвет другой (кресла FRNITURE 8/9): только внутри
                   одного набора и только на проверку (weak_mirror), пока человек не подтвердит;
  alternate_view - кандидат «другой бок»: тот же набор, номер рядом, похожие цвета, форма другая;
                   не доказательство, всегда на проверку;
  exact_duplicate - та же картинка в другом наборе: ключи одной строки очереди (keys);
  tile_repeat    - кадр стоит вплотную к своей копии (стол из шести частей): признак члена (tile).
Число confidence - среднее геометрическое силуэта, рисунка и краёв; ничего не выбирает, только для листа.

Пишет в --out (art/objects/families), UTF-8 со спецификацией:
  families.json - семейство: family_id, revision, canonical, members (AUTO и HUMAN_APPROVED), review;
  families.tsv  - строка на члена или кандидата: решение, связь, числа против канонического;
  review.tsv    - только то, что ждёт человека (indirect_chain, weak_mirror, alternate_view);
  touch.tsv (в папке --items) - для каждого кадра-предмета: мест, из них вплотную к своей копии.
decisions.tsv (в --out, правит человек): canonical, member (первые ключи строк), decision
HUMAN_APPROVED | HUMAN_REJECTED, relation, кто, когда, заметка. Ревизия семейства растёт, когда меняется
состав или решения (revision invalidation, раздел 36).

    py -3.13 tools/hdart/obj_families.py              (перепись касаний ~10 минут)
    py -3.13 tools/hdart/obj_families.py --no-touch   (касания с прошлого прогона)
"""
import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                  # noqa: E402

import obj_struct as os_                            # noqa: E402

ENC = "utf-8-sig"
IOU = 0.90          # силуэт тот же
CORR = 0.75         # яркостный рисунок тот же (перекраска)
CORR_M = 0.60       # у зеркала свет может остаться на своей стороне - рисунок совпадает слабее
EDGE = 0.60         # рисунок краёв тот же: у коробок одного силуэта грани светят одинаково, а
                    # содержимое разное - без краёв шкаф и ящик выходили «перекраской» (первый прогон:
                    # одно семейство на 1134 строки)
IOU_W, EDGE_W, CORR_W = 0.95, 0.40, 0.30   # зеркало со своим светом и цветом - только в одном наборе
NEAR = 2            # другой бок: номер кадра в наборе рядом
HIST = 0.55         # другой бок: пересечение цветовых гистограмм
TILE = 0.15         # плитка: доля мест вплотную к своей копии (стол FRNITURE 0 - 21 из 30 в отеле)
TILE_N = 8          # и не меньше стольких мест
TILE_PX = 8         # и копии касаются стыком не короче стольких пикселей базы

AUTO, APPROVED, REJECTED, REVIEW = "AUTO", "HUMAN_APPROVED", "HUMAN_REJECTED", "REVIEW_REQUIRED"
RU = {"recolor": "перекраска", "mirror": "зеркало", "mirror_weak": "зеркало слабое",
      "alternate_view": "другой бок?", "canonical": "каноническая"}


def feats(im):
    a = np.asarray(im.convert("RGBA"), np.float32)
    m = a[..., 3] > 0
    lum = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    z = np.zeros_like(lum)
    if m.sum() > 4:
        v = lum[m]
        z[m] = (v - v.mean()) / (v.std() + 1e-3)
    q = (a[..., :3][m] // 64).astype(np.int32)
    h = np.bincount(q[:, 0] * 16 + q[:, 1] * 4 + q[:, 2], minlength=64).astype(np.float32)
    h /= max(1.0, h.sum())
    col = a[..., :3][m].mean(0) if m.any() else np.zeros(3, np.float32)
    g = np.zeros_like(lum)
    g[:, :-1] += np.abs(np.diff(z, axis=1))
    g[:-1, :] += np.abs(np.diff(z, axis=0))
    return m, z, h, col, g


def iou(a, b):
    u = (a | b).sum()
    return (a & b).sum() / u if u else 0.0


def corr(za, zb, m):
    if m.sum() < 8:
        return 0.0
    x, y = za[m], zb[m]
    x, y = x - x.mean(), y - y.mean()
    d = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / d) if d else 0.0


def relation(fa, fb):
    """Связь двух кусков: (kind, iou, corr, edge_corr, разница цвета); kind - 'recolor' | 'mirror' |
    'mirror_weak' | None. Числа есть и при отказе - той стороны, где силуэт ближе (для листа)."""
    ma, za, _ha, ca, ga = fa
    mb, zb, _hb, cb, gb = fb
    dc = float(np.abs(ca - cb).max())
    i = float(iou(ma, mb))
    c = corr(za, zb, ma & mb)
    e = corr(ga, gb, ma & mb)
    if i >= IOU and c >= CORR and e >= EDGE:
        return "recolor", i, c, e, dc
    mf, zf, gf = mb[:, ::-1], zb[:, ::-1], gb[:, ::-1]
    i2 = float(iou(ma, mf))
    c2 = corr(za, zf, ma & mf)
    e2 = corr(ga, gf, ma & mf)
    if i2 >= IOU and c2 >= CORR_M and e2 >= EDGE:
        return "mirror", i2, c2, e2, dc
    # свет оставлен на своей стороне (R-054) и цвет другой: кресла FRNITURE 8/9 - силуэт 1.00,
    # яркость -0.42, края 0.45; унитазы BATHBITZ_HT 13/14 - 0.98, 0.53, 0.52. Признак слабый -
    # годится только внутри одного набора (pair_relation), между наборами склеивает коробки
    if i2 >= IOU_W and e2 >= EDGE_W and abs(c2) >= CORR_W:
        return "mirror_weak", i2, c2, e2, dc
    if i2 > i:
        return None, i2, c2, e2, dc
    return None, i, c, e, dc


def pair_relation(fr, fq, same_set):
    """Связь двух строк очереди кусок к куску: (kind | None, iou, corr, edge, dc) - худшие по кускам."""
    if len(fr) != len(fq):
        return None, 0.0, 0.0, 0.0, 0.0
    rels = [relation(x, y) for x, y in zip(fr, fq)]
    ev = (min(x[1] for x in rels), min(x[2] for x in rels), min(x[3] for x in rels), max(x[4] for x in rels))
    kinds = {x[0] for x in rels}
    if None in kinds:
        return (None,) + ev
    if "mirror_weak" in kinds:
        if kinds - {"mirror", "mirror_weak"} or not same_set:
            return (None,) + ev
        return ("mirror_weak",) + ev
    if len(kinds) != 1:
        return (None,) + ev
    return (kinds.pop(),) + ev


def confidence(ev):
    i, c, e = ev[0], abs(ev[1]), max(0.0, ev[2])
    return round(float((i * c * e) ** (1 / 3)), 3)


def assemble(ranks, edges, direct, decisions=None):
    """Семейства из графа кандидатов. ranks - строки (меньше = чаще на картах); edges - прошедшие
    попарные связи (r, q, kind) - только для поиска компонент; direct(c, r) -> (kind | None, iou,
    corr, edge, dc) - сравнение с каноническим НАПРЯМУЮ; decisions {(c, r): (decision, relation)} -
    решения человека. Итог: [{canonical, members: [(r, kind, ev, decision)], review: [(r, kind, ev,
    reason, via)], rejected: [r]}] только для компонент из двух строк и больше."""
    decisions = decisions or {}
    par = {r: r for r in ranks}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    nb = defaultdict(list)
    for r, q, kind in edges:
        nb[r].append((q, kind))
        nb[q].append((r, kind))
        ra, rb = find(r), find(q)
        if ra != rb:
            par[max(ra, rb)] = min(ra, rb)
    comp = defaultdict(list)
    for r in ranks:
        comp[find(r)].append(r)
    out = []
    for root in sorted(comp):
        mem = sorted(comp[root])
        if len(mem) < 2:
            continue
        can = mem[0]
        fam = {"canonical": can, "members": [], "review": [], "rejected": []}
        for r in mem[1:]:
            d = direct(can, r)
            kind, ev = d[0], d[1:]
            hum = decisions.get((can, r))
            if hum and hum[0] == REJECTED:
                fam["rejected"].append(r)
                continue
            if hum and hum[0] == APPROVED:
                fam["members"].append((r, hum[1] or kind or "unknown", ev, APPROVED))
            elif kind in ("recolor", "mirror"):
                fam["members"].append((r, kind, ev, AUTO))
            elif kind == "mirror_weak":
                fam["review"].append((r, "mirror", ev, "weak_mirror", []))
            else:
                via = sorted({"%s %d" % (k, q) for q, k in nb[r] if q in mem})
                fam["review"].append((r, "unknown", ev, "indirect_chain", via))
        out.append(fam)
    return out


def contact(m):
    """Длина стыка кадра со своей копией в соседней клетке по x (экран +16,+8) и по y (-16,+8), в
    пикселях базы: у крышки стола - вдоль всего ребра, у унитазов в ряд - ноль (стоят рядом, но не
    касаются). Плитка - только там, где копии касаются: иначе это просто ряд одинаковых вещей."""
    out = []
    for dx in (16, -16):
        a = np.zeros((40 + 10, 32 + 34), bool)
        b = np.zeros_like(a)
        ox = 17 if dx < 0 else 1
        a[1:41, ox:ox + 32] = m
        b[9:49, ox + dx:ox + dx + 32] = m
        near = b | np.roll(b, 1, 0) | np.roll(b, -1, 0) | np.roll(b, 1, 1) | np.roll(b, -1, 1)
        out.append(int((a & near).sum()))
    return out


def scan_touch(world):
    """По всем блокам всех террейнов: мест кадра-предмета и сколько из них вплотную к своей копии
    соседом по x и по y."""
    import map_mockup as mm
    import pck_census as pc
    places, touch = Counter(), {"x": Counter(), "y": Counter()}
    pairs = [(t, b) for t in world.terrains for b in world.blocks_of(t)]
    t0 = time.time()
    for n, (t, b) in enumerate(pairs):
        if n and n % 1000 == 0:
            print("  блоков %d из %d, %.0f с" % (n, len(pairs), time.time() - t0), flush=True)
        try:
            sets = world.sets_of(t)
            sizes = {s: len(world.records(s)) for s in sets}
            _sx, _sy, _sz, cells = mm.read_block(world, b)
        except (Exception, SystemExit):                     # noqa: BLE001 - битый блок: пропустить
            continue
        pos = defaultdict(set)
        for (x, y, z), cell in cells.items():
            v = cell[3]
            if not v:
                continue
            s, rec = pc.resolve(v, sets, sizes)
            if s is None:
                continue
            pos[(s.upper(), world.records(s)[rec]["frame"])].add((x, y, z))
        for key, ps in pos.items():
            places[key] += len(ps)
            touch["x"][key] += sum(1 for (x, y, z) in ps if {(x + 1, y, z), (x - 1, y, z)} & ps)
            touch["y"][key] += sum(1 for (x, y, z) in ps if {(x, y + 1, z), (x, y - 1, z)} & ps)
    return places, touch


def split(k):
    s, f = k.split(":")
    return s.upper(), int(f)


def read_decisions(path, rank_of_key):
    """decisions.tsv -> {(canonical rank, member rank): (decision, relation)}."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding=ENC) as f:
        for line in list(f)[1:]:
            p = line.rstrip("\n").split("\t")
            if len(p) < 3 or not p[0] or p[0].startswith("#"):
                continue
            c, r = rank_of_key.get(p[0].upper()), rank_of_key.get(p[1].upper())
            if c is None or r is None:
                print("decisions.tsv: нет строки очереди для %s или %s - пропущено" % (p[0], p[1]))
                continue
            out[(c, r)] = (p[2].strip(), p[3].strip() if len(p) > 3 else "")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default="art/objects/discovery/items.json")
    ap.add_argument("--out", default="art/objects/families")
    ap.add_argument("--no-touch", action="store_true", help="взять touch.tsv с прошлого прогона")
    a = ap.parse_args()
    import map_mockup as mm
    world = mm.World()
    with open(a.items, encoding=ENC) as f:
        # parent из obj_queue не учитывается: связи решает только эта стадия (раздел 11)
        items = json.load(f)
    by_rank = {it["rank"]: it for it in items}
    rank_of_key = {}
    for it in items:
        for k in it["keys"]:
            rank_of_key.setdefault(k.upper(), it["rank"])
    os.makedirs(a.out, exist_ok=True)

    tpath = os.path.join(os.path.dirname(a.items), "touch.tsv")
    if a.no_touch and os.path.exists(tpath):
        places, touch = Counter(), {"x": Counter(), "y": Counter()}
        with open(tpath, encoding=ENC) as f:
            for line in list(f)[1:]:
                k, p, tx, ty = line.rstrip("\n").split("\t")
                places[split(k)], touch["x"][split(k)], touch["y"][split(k)] = int(p), int(tx), int(ty)
    else:
        print("перепись мест вплотную к своей копии", flush=True)
        places, touch = scan_touch(world)
        with open(tpath, "w", encoding=ENC, newline="") as f:
            f.write("кадр\tмест\tвплотную к копии по x\tпо y\n")
            for k in sorted(places, key=lambda k: -places[k]):
                f.write("%s:%d\t%d\t%d\t%d\n" % (k + (places[k], touch["x"][k], touch["y"][k])))

    # признаки: по куску на кадр src; строки сравниваются, только если число кусков совпадает
    fe, keysets = {}, {}
    for it in items:
        src = it["src"] if it["kind"] == "составной" else it["src"][:1]
        fs = []
        for k in src:
            s, fr = split(k)
            im = world.sprite(s.lower(), fr, None)
            if im is None:
                fs = None
                break
            fs.append(feats(im))
        if fs:
            fe[it["rank"]] = fs
        keysets[it["rank"]] = [split(k) for k in it["keys"]]
    sets_of = {r: {s for s, _f in keysets[r]} for r in keysets}

    def rel(r, q):
        return pair_relation(fe[r], fe[q], bool(sets_of[r] & sets_of[q]))

    ranks = sorted(fe)
    print("строк очереди с кадром: %d" % len(ranks), flush=True)
    # поиск кандидатов: сравнивать только строки с похожей площадью первого куска (IoU 0.9 не
    # пропускает разницу площадей больше 1/0.9)
    area = {r: int(fe[r][0][0].sum()) for r in ranks}
    order = sorted(ranks, key=lambda r: area[r])
    edges = []
    for i, r in enumerate(order):
        for q in order[i + 1:]:
            if area[q] > area[r] * 1.25 + 4:
                break
            kind = rel(r, q)[0]
            if kind:
                edges.append((min(r, q), max(r, q), kind))
    # другой бок: тот же набор, кадр рядом, цвета похожи; только одиночные предметы
    side = []
    frame_of = defaultdict(list)
    for r in ranks:
        if len(fe[r]) == 1:
            for s, fr in keysets[r]:
                frame_of[s].append((fr, r))
    linked = {(e[0], e[1]) for e in edges}
    seen = set()
    st = os_.Struct(world)

    def sinfo(r):
        s, fr = split(by_rank[r]["src"][0])
        return st.info(s, fr)

    side_rej = []
    for s, lst in frame_of.items():
        lst.sort()
        for i, (f1, r1) in enumerate(lst):
            for f2, r2 in lst[i + 1:]:
                if f2 - f1 > NEAR:
                    break
                p = (min(r1, r2), max(r1, r2))
                if r1 == r2 or p in linked or p in seen:
                    continue
                seen.add(p)
                h = float(np.minimum(fe[r1][0][2], fe[r2][0][2]).sum())
                c1, c2 = os_.asset_class(sinfo(p[0]))[0], os_.asset_class(sinfo(p[1]))[0]
                if c1 not in os_.OBJECTISH or c2 not in os_.OBJECTISH:
                    # рельеф, стена, пол: не предмет - другой бок ему не ищется
                    side_rej.append((p[0], p[1], 0.0, ["не предмет: %s / %s" % (c1, c2)]))
                    continue
                # другой бок решает строение (obj_struct.alt_view), цвет в нём весит 0.1
                cls, score, why = os_.alt_view(sinfo(p[0]), sinfo(p[1]), h)
                if cls == os_.ALT_REJECT:
                    side_rej.append((p[0], p[1], score, why))
                else:
                    side.append((p[0], p[1], h, cls, score, why))

    dpath = os.path.join(a.out, "decisions.tsv")
    decisions = read_decisions(dpath, rank_of_key)
    fams = assemble(ranks, edges, rel, decisions)

    def tiled(r):
        """(мест, из них вплотную к копии и касаясь её); 0, если кадр со своей копией не стыкуется."""
        ks = keysets[r]
        p = sum(places[k] for k in ks)
        cx, cy = contact(fe[r][0][0])
        t = 0
        for d, c in (("x", cx), ("y", cy)):
            if c >= TILE_PX:
                t = max(t, sum(touch[d][k] for k in ks))
        return p, t

    def tile_of(r):
        if by_rank[r]["kind"] != "один":
            return ""
        p, t = tiled(r)
        return "%d из %d" % (t, p) if t >= TILE_N and t >= TILE * p else ""

    # семейство существует и у одиночки, если она плитка или у неё есть кандидат «другой бок»
    fam_of = {}
    for fm in fams:
        fam_of[fm["canonical"]] = fm
        for m in fm["members"]:
            fam_of[m[0]] = fm
    in_review = {x[0] for fm in fams for x in fm["review"]}
    lonely = {}

    def new_family(r):
        fm = {"canonical": r, "members": [], "review": [], "rejected": []}
        lonely[r] = fam_of[r] = fm
        return fm

    for r in ranks:
        if r not in fam_of and r not in in_review and tile_of(r):
            new_family(r)
    for r1, r2, h, cls, score, why in side:
        f1, f2 = fam_of.get(r1), fam_of.get(r2)
        if f1 is not None and f1 is f2:
            continue
        if f1 is None and f2 is not None:
            fm, other = f2, r1
        else:
            fm, other = f1 or new_family(r1), r2
        if other in fam_of and fam_of[other] is not fm:
            continue                  # другой бок уже в другом семействе: не склеивать семейства
        ev = (score, h, cls, why)
        hum = decisions.get((fm["canonical"], other))
        if hum and hum[0] == APPROVED:
            fm["members"].append((other, hum[1] or "alternate_view", ev, APPROVED))
            fam_of[other] = fm
        elif hum and hum[0] == REJECTED:
            continue
        elif cls == os_.ALT_HIGH:
            # физика MCD одна, объём и силуэт сходятся: одна вещь другим боком. Рисуется вместе с
            # каноническим (не выводится!), человек видит её на карточке ассета и может отделить
            fm["members"].append((other, "alternate_view", ev, AUTO))
            fam_of[other] = fm
        elif any(x[0] == other for x in fm["review"]):
            continue                  # пара уже на проверке (с другого конца поиска соседей)
        else:
            # ниже ALT_REQUIRED другой бок редок (лист alt_62_70, 29.09: ~1 из 4, но среди них повёрнутый
            # стул FRNITURE 3) - кандидат виден на карточке, но заказ не держит (obj_generation.OPTIONAL)
            fm["review"].append((other, "alternate_view", ev,
                                 "alternate_view_possible" if score >= os_.ALT_REQUIRED else "alternate_view_weak",
                                 ["другой бок? %d-%d, %.2f" % (r1, r2, score)]))
    fams = sorted(fams + list(lonely.values()), key=lambda fm: fm["canonical"])

    prev = {}
    jpath = os.path.join(a.out, "families.json")
    if os.path.exists(jpath):
        with open(jpath, encoding=ENC) as f:
            prev = {fm["family_id"]: fm for fm in json.load(f)}

    def aclass(r):
        """Класс строки: составной - предмет, если хоть один кусок предмет (obj_struct.asset_class)."""
        got = []
        for k in by_rank[r]["src"][:len(fe[r])]:
            s, fr = split(k)
            got.append(os_.asset_class(st.info(s, fr)))
        obj = [g for g in got if g[0] == "object"] or [g for g in got if g[0] in os_.OBJECTISH]
        return obj[0] if obj else got[0]

    def row(r):
        it = by_rank[r]
        c, why = aclass(r)
        return {"rank": r, "batch": it["batch"], "kind": it["kind"], "keys": it["keys"], "src": it["src"],
                "tile": tile_of(r), "asset_class": c, "class_why": why}

    def evid(ev, kind=""):
        if kind == "alternate_view":
            return {"score": ev[0], "color_hist": round(ev[1], 3), "alt_class": ev[2], "why": ev[3]}
        return {"iou": round(ev[0], 3), "corr": round(ev[1], 3), "edge_corr": round(ev[2], 3),
                "color_diff": round(ev[3], 1)}

    out = []
    for fm in fams:
        can = fm["canonical"]
        fid = by_rank[can]["keys"][0].upper()
        mem = [dict(row(can), relation="canonical", confidence=1.0, decision=AUTO, direct=True)]
        for r, kind, ev, dec in fm["members"]:
            conf = ev[0] if kind == "alternate_view" else confidence(ev)
            m = dict(row(r), relation=kind, confidence=conf, evidence=evid(ev, kind), decision=dec, direct=True)
            if kind == "mirror":
                m.update(geometry="mirrored", lighting="preserve_world_direction")
            elif kind == "alternate_view":
                m.update(derive=False, generation="multi_view")
            mem.append(m)
        rev = [dict(row(r), relation=kind, evidence=evid(ev, kind), decision=REVIEW, reason=why, direct=False, via=via)
               for r, kind, ev, why, via in fm["review"]]
        body = json.dumps([[m["keys"][0], m["relation"], m["decision"]] for m in mem] +
                          [[m["keys"][0], m["reason"]] for m in rev] +
                          [by_rank[r]["keys"][0] for r in fm["rejected"]], ensure_ascii=False)
        h = hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]
        old = prev.get(fid)
        revision = 1 if not old else old["revision"] + (old.get("content_hash") != h)
        out.append({"family_id": fid, "revision": revision, "content_hash": h, "canonical": fid,
                    "canonical_rank": can, "batch": by_rank[can]["batch"], "members": mem, "review": rev,
                    "rejected": [by_rank[r]["keys"][0] for r in fm["rejected"]]})

    with open(jpath, "w", encoding=ENC) as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    head = "семейство\tревизия\tномер\tпартия\tвид\tключи\tсвязь\tрешение\tпричина\tIoU\tрисунок\tкрая\tцвет\tплитка\tчерез\n"

    def line(fm, m):
        e = m.get("evidence", {})
        return "%s\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (
            fm["family_id"], fm["revision"], m["rank"], m["batch"], m["kind"], " ".join(m["keys"]),
            m["relation"], m["decision"], m.get("reason", ""), e.get("iou", ""), e.get("corr", ""),
            e.get("edge_corr", ""), e.get("color_diff", ""), m["tile"], "; ".join(m.get("via", [])))
    with open(os.path.join(a.out, "families.tsv"), "w", encoding=ENC, newline="") as f:
        f.write(head)
        for fm in out:
            for m in fm["members"] + fm["review"]:
                f.write(line(fm, m))
    with open(os.path.join(a.out, "review.tsv"), "w", encoding=ENC, newline="") as f:
        f.write(head)
        for fm in out:
            for m in fm["review"]:
                f.write(line(fm, m))
    with open(os.path.join(a.out, "alt_rejected.tsv"), "w", encoding=ENC, newline="") as f:
        # отсеянные строением кандидаты «другой бок» - для проверки порогов, не для человека
        f.write("номер\tключ\tномер\tключ\tscore\tпочему\n")
        for r1, r2, score, why in side_rej:
            f.write("%d\t%s\t%d\t%s\t%.3f\t%s\n" % (r1, by_rank[r1]["keys"][0], r2, by_rank[r2]["keys"][0],
                                                   score, "; ".join(why)))
    if not os.path.exists(dpath):
        with open(dpath, "w", encoding=ENC, newline="") as f:
            f.write("canonical\tmember\tdecision\trelation\tкто\tкогда\tзаметка\n")

    kinds = Counter(e[2] for e in edges)
    multi = [fm for fm in out if len(fm["members"]) > 1]
    auto = sum(len(fm["members"]) - 1 for fm in out)
    why = Counter(m["reason"] for fm in out for m in fm["review"])
    changed = sum(1 for fm in out if fm["family_id"] in prev and fm["revision"] != prev[fm["family_id"]]["revision"])
    alt = Counter(x[3] for x in side)
    print("связей-кандидатов: %s; другой бок: пар %d - высокий %d, возможный %d, отсеян строением %d"
          % (", ".join("%s %d" % kv for kv in kinds.most_common()), len(side) + len(side_rej),
             alt[os_.ALT_HIGH], alt[os_.ALT_POSSIBLE], len(side_rej)))
    cls = Counter(fm_m["asset_class"] for fm in out for fm_m in fm["members"][:1])
    print("класс канонических: %s" % ", ".join("%s %d" % kv for kv in cls.most_common()))
    print("семейств: %d, из них с членами: %d; членов напрямую (AUTO/HUMAN): %d; на проверку: %s"
          % (len(out), len(multi), auto, ", ".join("%s %d" % kv for kv in why.most_common())))
    print("плиток: %d; решений человека применено: %d; семейств с новой ревизией: %d"
          % (sum(1 for fm in out for m in fm["members"] if m["tile"]), len(decisions), changed))


if __name__ == "__main__":
    main()
