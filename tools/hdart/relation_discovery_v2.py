#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RELATION_DISCOVERY_V2_PREP - полнота обнаружения связей кадров (специалист 02.10). Только CPU и чтение данных.

Слепой holdout V8 (probes/routing-holdout-v8) показал: маршрут B почти не ошибается (logic 54/54, STRONG 51/51), но
связей знает мало (derived 0.16, state 0.32, composite 0.45, modular 0, animation 0), и пропущенная связь даёт ложный
одиночный заказ. Маршрут B не меняется; здесь - четыре детектора, все рёбра в одном графе (одна связь - одно ребро):

  1. EXACT   - глобальный хэш пикселей по всем наборам террейнов: EXACT_COPY_PEER (пиксели совпадают) и
               EXACT_MIRROR_PEER (совпадают после отражения по горизонтали). Симметрично, STRONG, одна группа
               рисования: остальные члены одиночного заказа не получают.
  2. RECOLOR - тот же силуэт (хэш маски, по всем наборам) и цвет одного кадра - функция цвета другого хотя бы в одну
               сторону (V1 требовал в обе - тёмная перекраска сводит оттенки и выпадала). STRONG только с
               подтверждением: у основы не меньше MIN_COLORS цветов, производный хранит границы областей
               (BORDER_KEEP), и ещё MCD совместим (те же воксели и тип клетки) или порядок номеров кадров повторён
               у соседей с тем же сдвигом (SEQ_MIN из SEQ_REACH). Остальное - CANDIDATE: улика, не маршрут.
  3. MCD     - граф записей MCD (mcd_state.build): кадр анимации -> голова петли, die -> основа; alt - только улика
               (V6). Ребро хранится один раз и читается с обеих сторон: голова петли и основа разрушения - тоже члены
               связи, но выводятся не они.
  4. PLACE   - расстановка на картах: COMPOSITE_PART - два куска почти всегда вместе на одном сдвиге, причём в ОБЕ
               стороны (стул у стола односторонний - не составной); STRUCTURAL_MODULAR - вплотную своя копия на
               одной оси. Модуль - только CANDIDATE (специалист: отдельно, пока выборка мала).

Пороги заданы до прогона на 60 кадрах и под ошибки V8 не подстраиваются. Безопасность V2 учитывает направление связи
(специалист 02.10): основа с исходящими связями рисуется сама законно; опасен одиночный творческий заказ кадра,
который по эталону выводится из другого, и кадра с симметричной связью без группы рисования. VERIFIED ставит только
человек; STRONG здесь - уровень доказательства детектора.

    py -3.13 tools/hdart/relation_discovery_v2.py index      глобальный индекс кадров (хэш пикселей и маски)
    py -3.13 tools/hdart/relation_discovery_v2.py discover   связи 60 кадров holdout V8 -> relations_v2.json
    py -3.13 tools/hdart/relation_discovery_v2.py controls   те же детекторы на парах эталонов V4_R1, V5, V7
    py -3.13 tools/hdart/relation_discovery_v2.py report     безопасность V2, полнота, точность -> report.md
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
import identity_routing as ir         # noqa: E402
import relation_probe as rp           # noqa: E402

ENC = ir.ENC
OUT = os.path.join(ir.PROBES, "relation-discovery-v2-prep")
H8 = os.path.join(ir.PROBES, "routing-holdout-v8")
CONTROLS = ("routing-holdout-v4r1", "routing-holdout-v5", "routing-holdout-v7")

# пороги - заданы до прогона на 60 (специалист 02.10: не подстраивать под конкретные ошибки)
GEO, FUNC = rp.GEO, rp.FUNC      # силуэт и функция цвета - пороги V1
MIN_COLORS = 6                   # функция цвета что-то доказывает, только если у основы столько цветов и больше
BORDER_KEEP = 0.60               # и производный хранит столько границ цветовых областей (IoU границ)
SEQ_REACH, SEQ_MIN = 2, 2        # порядок номеров: соседи ±1..±SEQ_REACH с тем же сдвигом, из них SEQ_MIN - тоже пары
CO_STRONG, CO_CAND = 0.95, 0.90  # составной: взаимная доля совместной встречи на одном сдвиге
CO_PLACES, CO_BLOCKS = 3, 2      # мест у каждого куска не меньше и карт (блоков) не меньше - иначе одна расстановка
MOD_SHARE, MOD_PLACES = 0.80, 4  # модуль: в стольких местах вплотную своя копия на одной оси, мест не меньше
THRESHOLDS = {"GEO": GEO, "FUNC": FUNC, "MIN_COLORS": MIN_COLORS, "BORDER_KEEP": BORDER_KEEP, "SEQ_REACH": SEQ_REACH,
              "SEQ_MIN": SEQ_MIN, "CO_STRONG": CO_STRONG, "CO_CAND": CO_CAND, "CO_PLACES": CO_PLACES,
              "CO_BLOCKS": CO_BLOCKS, "MOD_SHARE": MOD_SHARE, "MOD_PLACES": MOD_PLACES}

SYMMETRIC = ("EXACT_COPY_PEER", "EXACT_MIRROR_PEER", "RECOLOR_PEER", "COMPOSITE_PART", "STRUCTURAL_MODULAR")
GROUP = {"EXACT_COPY_PEER": "derived", "EXACT_MIRROR_PEER": "derived", "RECOLOR_PEER": "derived",
         "RECOLOR_OF": "derived", "DERIVED_FROM": "derived", "MATERIAL_VARIANT_OF": "derived",
         "COMPOSITE_PART": "composite", "STRUCTURAL_MODULAR": "modular", "ANIMATION_FAMILY": "animation",
         "ANIMATION_FAMILY_COPY": "animation", "STATE_VARIANT_OF": "state", "DESTROYED_VARIANT_OF": "state"}
GROUPS = ["canonical", "composite", "modular", "state", "animation", "derived"]
BINDING = ("STRONG", "VERIFIED", "PROVISIONAL")        # связывают кадр; CANDIDATE - улика (кадр уходит на ревью)
REF_GROUPS = {"RECOLOR_OF": {"derived"}, "DERIVED_FROM": {"derived"}, "STATE_VARIANT_OF": {"state"},
              "ANIMATION_FRAME_OF": {"animation"}, "STRUCTURAL_RELATION": {"composite", "modular"}}
OPEN_REL = ("", "NONE", "OPEN")
PIPE_ROLE = {"EXACT_COPY_PEER": "RECOLOR_PEER", "EXACT_MIRROR_PEER": "RECOLOR_PEER"}   # пара - не целое (pipeline_of)
DETECTOR_ORDER = {"V8": 0, "EXACT": 1, "MCD": 2, "RECOLOR": 3, "PLACE": 4}
OFFSETS = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)]
AXES = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0))


def p(*a):
    return os.path.join(*a)


def split(k):
    s, f = k.rsplit(":", 1)
    return s.upper(), int(f)


def key(s, f):
    return "%s:%d" % (s.upper(), f)


def file_sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ---------------------------------------------------------------- 1. глобальный индекс кадров

def digests(a):
    """(хэш пикселей, хэш маски, хэш пикселей отражения, площадь, цветов) RGBA-кадра; пустой - None.
    Пиксели под нулевой альфой не входят: игра их не рисует (R-043)."""
    m = a[..., 3] > 0
    if not m.any():
        return None
    head = ("%dx%d" % m.shape).encode()
    rgb = np.where(m[..., None], a[..., :3], 0).astype(np.uint8)
    mf, rf = m[:, ::-1], rgb[:, ::-1]
    _m, c = rp.codes(a)
    return (hashlib.sha1(head + np.packbits(m).tobytes() + rgb.tobytes()).hexdigest()[:20],
            hashlib.sha1(head + np.packbits(m).tobytes()).hexdigest()[:20],
            hashlib.sha1(head + np.packbits(np.ascontiguousarray(mf)).tobytes()
                         + np.ascontiguousarray(rf).tobytes()).hexdigest()[:20],
            int(m.sum()), int(len(np.unique(c[m]))))


class Index:
    """Индекс всех непустых кадров наборов, на которые ссылаются террейны: ключ -> (pix, mask, pixm, area, ncol)."""

    def __init__(self, frames):
        self.frames = frames
        self.by_pix, self.by_mask = defaultdict(set), defaultdict(set)
        for k, v in frames.items():
            self.by_pix[v[0]].add(k)
            self.by_mask[v[1]].add(k)

    def get(self, k):
        return self.frames.get(k.upper())

    def exact(self, k):
        v = self.get(k)
        return set() if v is None else self.by_pix[v[0]] - {k.upper()}

    def mirror(self, k):
        v = self.get(k)
        return set() if v is None else self.by_pix[v[2]] - {k.upper()} - self.exact(k)

    def same_mask(self, k):
        v = self.get(k)
        return set() if v is None else self.by_mask[v[1]] - {k.upper()} - self.exact(k)


def all_sets(world):
    return sorted({s.upper() for t in world.terrains for s in world.sets_of(t)})


def build_index(world):
    frames, sets = {}, all_sets(world)
    for i, s in enumerate(sets):
        sh = world.sheet(s.lower())
        if sh is None:
            continue
        for f in range(sh.lay["count"]):
            im = world.sprite(s.lower(), f, None)
            if im is None:
                continue
            d = digests(np.asarray(im))
            if d is not None:
                frames[key(s, f)] = list(d)
        if i % 50 == 0:
            print("индекс: набор %d из %d, кадров %d" % (i + 1, len(sets), len(frames)), flush=True)
    return {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "sets": len(sets), "frames": frames}


def load_index(out=OUT):
    path = p(out, "index", "frames.json")
    if not os.path.exists(path):
        raise SystemExit("нет %s - сначала: relation_discovery_v2.py index" % path)
    return Index(ir.load_json(path)["frames"])


# ---------------------------------------------------------------- контекст: кадры, MCD, карты

class Ctx:
    def __init__(self, world=None, index=None):
        import map_mockup as mm
        import obj_struct as os_
        self.mm = mm
        self.world = world or mm.World()
        self.st = os_.Struct(self.world)
        self.ix = index
        self.arr = {}
        self.mcd_idx = {}
        self.places = Places(self.world, mm)

    def rgba(self, k):
        K = k.upper()
        if K not in self.arr:
            s, f = split(K)
            im = self.world.sprite(s.lower(), f, None)
            self.arr[K] = None if im is None else np.asarray(im.convert("RGBA"))
        return self.arr[K]

    def mcd_links(self, k):
        """Связи MCD набора кадра (mcd_state, обе стороны): [{state, base, via, level, why, side, relative}]."""
        import mcd_state as ms
        s, _f = split(k)
        if s not in self.mcd_idx:
            self.mcd_idx[s] = ms.index(ms.build([s], self.world, self._cells()))
        return self.mcd_idx[s].get(k.upper(), [])

    def _cells(self):
        if not hasattr(self, "_cells_v"):
            import mcd_state as ms
            self._cells_v = ms.placements()
        return self._cells_v

    def mcd_compatible(self, a, b):
        ia, ib = self.st.info(*split(a)), self.st.info(*split(b))
        if not (ia.get("rec") and ib.get("rec")):
            return False
        return bool(ia["tile_type"] == ib["tile_type"] and (ia["vox"] == ib["vox"]).all())


class Places:
    """Расстановка кадров на картах: по террейну - сетки блоков (клетка -> [(слой, кадр)]) и места каждого кадра.
    Читается так же, как relation_probe.neigh (pck_census.resolve, кадр записи - Frame[0])."""

    def __init__(self, world, mm):
        self.w, self.mm = world, mm
        self.t = {}
        self._set_terrains = None

    def terrains_of(self, s):
        if self._set_terrains is None:
            self._set_terrains = defaultdict(list)
            for t in sorted(self.w.terrains):
                for x in self.w.sets_of(t):
                    self._set_terrains[x.upper()].append(t)
        return self._set_terrains.get(s.upper(), [])

    def terrain(self, t):
        if t not in self.t:
            import pck_census as pc
            sets_t = self.w.sets_of(t)
            sizes = {s: len(self.w.records(s)) for s in sets_t}
            grids, occ = [], defaultdict(list)
            for b in self.w.blocks_of(t):
                try:
                    _sx, _sy, _sz, cells = self.mm.read_block(self.w, b)
                except (Exception, SystemExit):           # noqa: BLE001 - блок не читается: его нет
                    continue
                grid = {}
                for pos, cell in cells.items():
                    ks = []
                    for layer, v in enumerate(cell):
                        if not v:
                            continue
                        s, rec = pc.resolve(v, sets_t, sizes)
                        if s is None:
                            continue
                        k = key(s, self.w.records(s)[rec]["frame"])
                        ks.append((layer, k))
                        occ[k].append((len(grids), pos, layer))
                    if ks:
                        grid[pos] = ks
                grids.append((b, grid))
            self.t[t] = (grids, occ)
        return self.t[t]

    def of(self, k):
        """Места кадра: [(террейн, блок, сетка, (x, y, z), слой)]; один блок в двух террейнах - одно место."""
        s, _f = split(k)
        out, seen = [], set()
        for t in self.terrains_of(s):
            grids, occ = self.terrain(t)
            for bi, pos, layer in occ.get(k.upper(), []):
                b, grid = grids[bi]
                if (b, pos, layer) in seen:
                    continue
                seen.add((b, pos, layer))
                out.append((t, b, grid, pos, layer))
        return out


# ---------------------------------------------------------------- 2. детекторы

def edge(typ, source, target, level, detector, rule, why):
    return {"type": typ, "source": source.upper(), "target": target.upper(), "level": level, "detector": detector,
            "rule": rule, "evidence": why}


def exact_edges(ix, a):
    out = [edge("EXACT_COPY_PEER", a, b, "STRONG", "EXACT", "X1", "пиксели совпадают") for b in sorted(ix.exact(a))]
    out += [edge("EXACT_MIRROR_PEER", a, b, "STRONG", "EXACT", "X2", "пиксели совпадают после отражения")
            for b in sorted(ix.mirror(a))]
    return out


def funcs(A, B):
    """(f_ab: цвет B - функция цвета A, f_ba, IoU, цветов A, цветов B, IoU границ) на общем силуэте."""
    ma, ca = rp.codes(A)
    mb, cb = rp.codes(B)
    u = (ma | mb).sum()
    m = ma & mb
    iou = float(m.sum() / u) if u else 0.0
    f_ab = rp.func_map(ca[m], cb[m])[0]
    f_ba = rp.func_map(cb[m], ca[m])[0]
    _agree, biou = rp.topology(m, ca, cb)
    return f_ab, f_ba, iou, int(len(np.unique(ca[ma]))), int(len(np.unique(cb[mb]))), biou


def sequence(ctx, a, b):
    """Сколько соседей по номеру (±1..±SEQ_REACH) в обоих наборах с тем же сдвигом - тоже пара: пиксели равны или
    тот же силуэт и функция цвета при основе с MIN_COLORS цветов."""
    (sa, fa), (sb, fb) = split(a), split(b)
    hits = []
    for i in [d for r in range(1, SEQ_REACH + 1) for d in (-r, r)]:
        ka, kb = key(sa, fa + i), key(sb, fb + i)
        va, vb = ctx.ix.get(ka), ctx.ix.get(kb)
        if va is None or vb is None or ka == kb:
            continue
        if va[0] == vb[0]:
            hits.append(i)
            continue
        if va[1] != vb[1] or max(va[4], vb[4]) < MIN_COLORS:
            continue
        A, B = ctx.rgba(ka), ctx.rgba(kb)
        f_ab, f_ba, _iou, _na, _nb, _b = funcs(A, B)
        if max(f_ab, f_ba) >= FUNC:
            hits.append(i)
    return hits


def recolor_pair(ctx, a, b):
    """Перекраска пары (силуэт уже тот же): ребро или None. RECOLOR_OF - производный -> основа (цвет производного -
    функция цвета основы, обратно нет); RECOLOR_PEER - функция в обе стороны, основа не назначается."""
    A, B = ctx.rgba(a), ctx.rgba(b)
    if A is None or B is None:
        return None
    f_ab, f_ba, iou, na, nb, biou = funcs(A, B)
    if iou < GEO or max(f_ab, f_ba) < FUNC:
        return None
    if f_ab >= FUNC and f_ba >= FUNC:
        typ, src, tgt, nbase = "RECOLOR_PEER", a, b, max(na, nb)
    elif f_ab >= FUNC:
        typ, src, tgt, nbase = "RECOLOR_OF", b, a, na          # b выводится из a
    else:
        typ, src, tgt, nbase = "RECOLOR_OF", a, b, nb
    informative = nbase >= MIN_COLORS and biou >= BORDER_KEEP
    mcd_ok = ctx.mcd_compatible(a, b)
    seq = sequence(ctx, a, b)
    strong = informative and (mcd_ok or len(seq) >= SEQ_MIN)
    why = "силуэт %.3f, функция %.3f/%.3f, цветов основы %d, границ %.2f; MCD %s; соседи по номеру %s" % (
        iou, f_ab, f_ba, nbase, biou, "совместим" if mcd_ok else "нет", seq or "нет")
    return edge(typ, src, tgt, "STRONG" if strong else "CANDIDATE", "RECOLOR", "C2" if strong else "C2c", why)


def recolor_edges(ctx, a):
    out = []
    for b in sorted(ctx.ix.same_mask(a)):
        e = recolor_pair(ctx, a, b)
        if e:
            out.append(e)
    return out


def mcd_edges(ctx, a):
    """Рёбра MCD кадра в обе стороны: состояние -> основа. alt - только улика (CANDIDATE), как в V6/V8."""
    out = []
    for x in ctx.mcd_links(a):
        typ = {"anim": "ANIMATION_FAMILY", "die": "DESTROYED_VARIANT_OF", "alt": "STATE_VARIANT_OF"}[x["via"]]
        level = "CANDIDATE" if x["via"] == "alt" else x["level"]
        out.append(edge(typ, x["state"], x["base"], level, "MCD", "M-" + x["via"],
                        "MCD %s %s -> %s%s" % (x["via"], x["state"], x["base"], (": " + x["why"]) if x["why"] else "")))
    return out


def cooccur(ctx, a):
    """Соседи кадра на одном сдвиге: {(сдвиг, слой a, слой b, b): (мест вместе, мест a в слое, блоков вместе)}.
    Пол (слой 0) не считается: пол под предметом - основа, а не кусок (R-006)."""
    pa = ctx.places.of(a)
    per_layer = Counter(pl[4] for pl in pa)
    cnt, blocks = Counter(), defaultdict(set)
    for _t, b, grid, (x, y, z), la in pa:
        if la == 0:
            continue
        seen = set()
        for o in OFFSETS:
            for lb, kb in grid.get((x + o[0], y + o[1], z + o[2]), []):
                if lb == 0 or kb == a.upper() or (o == (0, 0, 0) and lb == la):
                    continue
                seen.add((o, la, lb, kb))
        for s in seen:
            cnt[s] += 1
            blocks[s].add(b)
    return {s: (n, per_layer[s[1]], len(blocks[s])) for s, n in cnt.items()}


def reverse_share(ctx, a, b, o, la, lb):
    """Доля мест b (в слое lb), где a стоит на обратном сдвиге в слое la; и число таких мест b."""
    pb = [pl for pl in ctx.places.of(b) if pl[4] == lb]
    if not pb:
        return 0.0, 0
    hit = sum(any(l2 == la and k2 == a.upper() for l2, k2 in grid.get((x - o[0], y - o[1], z - o[2]), []))
              for _t, _b, grid, (x, y, z), _l in pb)
    return hit / len(pb), len(pb)


def composite_edges(ctx, a, only=None):
    """COMPOSITE_PART: a и b вместе на одном сдвиге в обе стороны. STRONG - доли >= CO_STRONG, мест у каждого >=
    CO_PLACES и блоков >= CO_BLOCKS; CANDIDATE - доли >= CO_CAND и мест >= 2."""
    out, done = [], set()
    for (o, la, lb, kb), (n, na, nbl) in sorted(cooccur(ctx, a).items(), key=lambda kv: -kv[1][0]):
        if only is not None and kb != only.upper():
            continue
        s_ab = n / na if na else 0.0
        if s_ab < CO_CAND or kb in done:
            continue
        s_ba, nb = reverse_share(ctx, a, kb, o, la, lb)
        if s_ba < CO_CAND or min(na, nb) < 2:
            continue
        strong = min(s_ab, s_ba) >= CO_STRONG and min(na, nb) >= CO_PLACES and nbl >= CO_BLOCKS
        done.add(kb)
        out.append(edge("COMPOSITE_PART", a, kb, "STRONG" if strong else "CANDIDATE", "PLACE",
                        "P1" if strong else "P1c", "вместе на сдвиге %s (слои %d/%d): %d из %d мест a, %.2f мест b из %d,"
                        " блоков %d" % (list(o), la, lb, n, na, s_ba, nb, nbl)))
    return out


def module_role(ctx, a):
    """STRUCTURAL_MODULAR (CANDIDATE): в доле мест >= MOD_SHARE вплотную на одной оси своя копия (тот же кадр или
    точная копия пикселей), мест >= MOD_PLACES. Роль без цели: модуль стыкуется сам с собой."""
    copies = {a.upper()} | (ctx.ix.exact(a) if ctx.ix else set())
    pa = [pl for pl in ctx.places.of(a) if pl[4] != 0]
    if len(pa) < MOD_PLACES:
        return None
    axis, hit = Counter(), 0
    for _t, _b, grid, (x, y, z), la in pa:
        here = [o for o in AXES if any(l2 == la and k2 in copies for l2, k2 in grid.get((x + o[0], y + o[1], z), []))]
        hit += bool(here)
        axis.update({"x" if o[0] else "y" for o in here})
    share = hit / len(pa)
    if share < MOD_SHARE:
        return None
    return {"type": "STRUCTURAL_MODULAR", "level": "CANDIDATE", "detector": "PLACE", "rule": "P2c",
            "evidence": "своя копия вплотную в %d из %d мест (%.2f), оси %s" % (hit, len(pa), share, dict(axis))}


# ---------------------------------------------------------------- граф: одна связь - одно ребро

class Graph:
    """Ребро хранится один раз по неупорядоченной паре; второе ребро на ту же пару не добавляется (раньше - V8,
    затем STRONG раньше CANDIDATE). Роли без цели (V8 R5, R6, R3, R4; модуль V2) - отдельно, по кадру."""

    def __init__(self):
        self.edges = {}
        self.self_roles = defaultdict(list)
        self.evidence = defaultdict(list)

    def add(self, e):
        s, t = e["source"].upper(), e["target"].upper()
        if not t or s == t:
            return False
        k = frozenset((s, t))
        if k in self.edges:
            return False
        self.edges[k] = e
        return True

    def touching(self, a, levels=None):
        A = a.upper()
        return [e for k, e in self.edges.items() if A in k and (levels is None or e["level"] in levels)]

    def between(self, a, b):
        return self.edges.get(frozenset((a.upper(), b.upper())))


def v8_graph(rows):
    """Граф V8 из строк замороженного отчёта: рёбра строк, обратные чтения (relations_in), роли без цели, улики."""
    g = Graph()
    for r in rows:
        a = r["asset_id"].upper()
        for e in r["edges"]:
            if e["relation_type"] == "CANONICAL":
                continue
            if not e["target"]:
                g.self_roles[a].append({"type": e["relation_type"], "level": e["confidence"], "detector": "V8",
                                        "rule": e["rule"], "evidence": e["evidence"]})
                continue
            g.add(edge(e["relation_type"], a, e["target"], e["confidence"], "V8", e["rule"], e["evidence"]))
        for x in r.get("relations_in", []):
            g.add(edge(x["inverse_of"], x["target"], a, x["confidence"], "V8", x["rule"], x["evidence"]))
        for x in r.get("open_evidence", []):
            g.evidence[a].append(dict(x, detector="V8"))
    return g


def add_v2(g, v2):
    """Рёбра V2 в граф V8: сначала STRONG, затем CANDIDATE, внутри - по детектору. Возвращает добавленные."""
    added = []
    for e in sorted(v2["edges"], key=lambda e: (e["level"] != "STRONG", DETECTOR_ORDER[e["detector"]],
                                               e["source"], e["target"])):
        if g.add(e):
            added.append(e)
    for a, roles in v2["self_roles"].items():
        g.self_roles[a.upper()] += roles
    return added


def groups_of(g, a, levels=BINDING, self_levels=BINDING):
    A = a.upper()
    gs = {GROUP[x["type"]] for x in g.self_roles.get(A, []) if x["level"] in self_levels and x["type"] in GROUP}
    gs |= {GROUP[e["type"]] for e in g.touching(a, levels) if e["type"] in GROUP}
    return sorted(gs) or ["canonical"]


def bound(g, a):
    """Кадр не рисуется сам по себе: роль без цели, исходящее (производное) ребро или симметричное - группа."""
    A = a.upper()
    if any(x["level"] in BINDING for x in g.self_roles.get(A, [])):
        return True
    return any(e["type"] in SYMMETRIC or e["source"] == A for e in g.touching(a, BINDING))


def has_evidence(g, a):
    A = a.upper()
    return bool(g.evidence.get(A)) or any(x["level"] not in BINDING for x in g.self_roles.get(A, [])) or \
        bool(g.touching(a, ("CANDIDATE",)))


def pipe_roles(g, a):
    """Роли для routing_model_v8.pipeline_of (замороженная ось B): своё и симметричное, точная копия - как пара."""
    A = a.upper()
    roles = {x["type"] for x in g.self_roles.get(A, []) if x["level"] in BINDING}
    roles |= {PIPE_ROLE.get(e["type"], e["type"]) for e in g.touching(a, BINDING)
              if e["type"] in SYMMETRIC or e["source"] == A}
    return sorted(roles) or ["CANONICAL"]


# ---------------------------------------------------------------- безопасность V2: направление связи

def eff_direction(pair, fs):
    """Направление пары эталона: судья (asset_derived / relative_derived), иначе факт MCD между ними (OUT своей
    записи - родственник выводится, IN - кадр выводится), иначе симметрично."""
    d = pair.get("direction") or "open"
    if d in ("asset_derived", "relative_derived"):
        return d, "судья"
    link = [x for x in fs if x["relative"].upper() == pair["relative"].upper()]
    if any(x["dir"] == "OUT" for x in link):
        return "relative_derived", "MCD своей записи"
    if any(x["dir"] == "IN" for x in link):
        return "asset_derived", "MCD чужой записи"
    return "symmetric", "судья: %s" % d


NON_OBJECT = ("STRUCTURAL_PIPELINE", "TERRAIN_PIPELINE", "NONE")


def danger_v2(row, creative, g, pairs, fs):
    """Причины опасного одиночного творческого заказа по правилу V2 (пусто - не опасно)."""
    if not creative:
        return []
    a = row["asset_id"]
    why = []
    if row["ref_pipeline"] in NON_OBJECT:
        why.append("эталону нужен %s" % row["ref_pipeline"])
    closed = [x for x in pairs if x["ref_pair_relation"] not in OPEN_REL]
    for x in closed:
        d, src = eff_direction(x, fs)
        if d == "asset_derived":
            why.append("%s %s: кадр выводится (%s)" % (x["ref_pair_relation"], x["relative"], src))
        elif d == "symmetric" and not g.between(a, x["relative"]):
            why.append("%s %s: связь без направления, группы нет" % (x["ref_pair_relation"], x["relative"]))
    groups = set(row["ref_role_groups"]) if row["ref_role_status"] == "judged" else set()
    if groups & {"composite", "modular"} and not closed:
        why.append("эталон: %s без пары" % "|".join(sorted(groups)))
    if groups and "canonical" not in groups and not closed and not why:
        why.append("эталон: связь %s без пары" % "|".join(sorted(groups)))
    return why


# ---------------------------------------------------------------- discover: 60 кадров holdout V8

def discover(ctx, keys):
    edges, self_roles, log = [], {}, {}
    for a in keys:
        es = exact_edges(ctx.ix, a) + mcd_edges(ctx, a) + recolor_edges(ctx, a) + composite_edges(ctx, a)
        m = module_role(ctx, a)
        if m:
            self_roles[a.upper()] = [m]
        edges += es
        log[a] = Counter("%s %s" % (e["type"], e["level"]) for e in es)
        print(a, dict(log[a]), "модуль" if m else "", flush=True)
    return {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "thresholds": THRESHOLDS, "keys": list(keys),
            "edges": edges, "self_roles": self_roles,
            "note": "кандидаты и доказательства детекторов, не маршрут; VERIFIED ставит только человек"}


def h8_inputs(h8=H8):
    """Замороженный holdout V8 - только чтение: строки отчёта, эталон, пары, состав."""
    rep = ir.load_json(p(h8, "report.json"))
    ref = {r["asset_id"]: r for r in ir.read_tsv(p(h8, "reference.tsv"))}
    pairs = defaultdict(list)
    for x in ir.read_tsv(p(h8, "reference_pairs.tsv")):
        pairs[x["asset_id"]].append(x)
    h = ir.load_json(p(h8, "holdout.json"))
    sha = {f: file_sha(p(h8, f)) for f in ("report.json", "reference.tsv", "reference_pairs.tsv", "holdout.json",
                                            "FREEZE.json", "reference.lock.json")}
    return rep, ref, pairs, h, sha


# ---------------------------------------------------------------- контроль: пары прежних эталонов

def detect_pair(ctx, a, b):
    """Все детекторы на одной паре (для контроля): [ребро]."""
    a, b = a.upper(), b.upper()
    out = []
    if b in ctx.ix.exact(a):
        out.append(edge("EXACT_COPY_PEER", a, b, "STRONG", "EXACT", "X1", "пиксели совпадают"))
    elif b in ctx.ix.mirror(a):
        out.append(edge("EXACT_MIRROR_PEER", a, b, "STRONG", "EXACT", "X2", "пиксели совпадают после отражения"))
    elif b in ctx.ix.same_mask(a):
        e = recolor_pair(ctx, a, b)
        if e:
            out.append(e)
    if split(a)[0] == split(b)[0]:
        out += [e for e in mcd_edges(ctx, a) if {e["source"], e["target"]} == {a, b}]
    out += composite_edges(ctx, a, only=b)
    return out


def ref_outcome(e, rel):
    """Ребро против пары эталона: ok | wrong (NONE или другой смысл) | open."""
    if rel in ("", "OPEN"):
        return "open"
    if rel == "NONE":
        return "wrong"
    return "ok" if GROUP[e["type"]] in REF_GROUPS.get(rel, set()) else "wrong"


def controls(ctx):
    rows, seen = [], set()
    for name in CONTROLS:
        for x in ir.read_tsv(p(ir.PROBES, name, "reference_pairs.tsv")):
            a, b = x["asset_id"].upper(), x["relative"].upper()
            k = frozenset((a, b))
            if k in seen or a == b:
                continue
            seen.add(k)
            es = detect_pair(ctx, a, b)
            rel = x["ref_pair_relation"]
            rows.append({"holdout": name, "asset_id": a, "relative": b, "ref": rel,
                         "edges": [{"type": e["type"], "level": e["level"], "detector": e["detector"],
                                    "outcome": ref_outcome(e, rel), "evidence": e["evidence"]} for e in es]})
        print(name, "пар", len(rows), flush=True)
    return {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "thresholds": THRESHOLDS, "pairs": rows}


def control_stats(c):
    """По детектору и уровню: верно / неверно (NONE или другой смысл) / открыто; полнота по видам эталона."""
    by = defaultdict(Counter)
    fp_none = defaultdict(Counter)
    for r in c["pairs"]:
        for e in r["edges"]:
            by[(e["detector"], e["level"])][e["outcome"]] += 1
            if r["ref"] == "NONE":
                fp_none[(e["detector"], e["level"])][e["type"]] += 1
    rec = {}
    for rel in REF_GROUPS:
        pos = [r for r in c["pairs"] if r["ref"] == rel]
        rec[rel] = {"n": len(pos),
                    "strong": sum(any(e["outcome"] == "ok" and e["level"] == "STRONG" for e in r["edges"]) for r in pos),
                    "any": sum(any(e["outcome"] == "ok" for e in r["edges"]) for r in pos)}
    neg = [r for r in c["pairs"] if r["ref"] == "NONE"]
    st = [e for r in c["pairs"] for e in r["edges"] if e["level"] == "STRONG" and e["outcome"] != "open"]
    st_none = sum(e["level"] == "STRONG" for r in neg for e in r["edges"])
    return {"strong_precision": rate(sum(e["outcome"] == "ok" for e in st), len(st)),
            "strong_binding_precision": rate(len(st) - st_none, len(st)), "strong_judged": len(st),
            "by_detector": {"%s %s" % k: dict(v) for k, v in sorted(by.items())},
            "none_pairs": len(neg),
            "none_with_strong": sum(any(e["level"] == "STRONG" for e in r["edges"]) for r in neg),
            "none_with_any": sum(bool(r["edges"]) for r in neg),
            "fp_types": {"%s %s" % k: dict(v) for k, v in fp_none.items()}, "recall": rec}


# ---------------------------------------------------------------- отчёт

def rate(k, n):
    return round(k / n, 3) if n else None


def group_metrics(rows, gk):
    """Как routing_model_v8.metrics relation_by_type, по группам из поля gk строки."""
    judged = [r for r in rows if r["ref_role_status"] == "judged"]
    out = {}
    for gr in GROUPS:
        pred = [r for r in judged if gr in r[gk]]
        ref = [r for r in judged if gr in r["ref_role_groups"]]
        out[gr] = {"precision": rate(sum(gr in r["ref_role_groups"] for r in pred), len(pred)), "predicted": len(pred),
                   "recall": rate(sum(gr in r[gk] for r in ref), len(ref)), "reference": len(ref)}
    return out


def pair_metrics(g, keys, pairs, levels):
    """Пары эталона с закрытым смыслом: найдена ли связь нужной группы между кадром и родственником."""
    by = defaultdict(Counter)
    miss = []
    for a in keys:
        for x in pairs.get(a, []):
            rel = x["ref_pair_relation"]
            if rel in OPEN_REL:
                continue
            e = g.between(a, x["relative"])
            ok = e is not None and e["level"] in levels and GROUP.get(e["type"]) in REF_GROUPS[rel]
            by[rel]["n"] += 1
            by[rel]["found"] += ok
            if not ok:
                miss.append("%s %s %s%s" % (a, rel, x["relative"], " (есть %s %s)" % (e["type"], e["level"]) if e else ""))
    return {rel: {"n": c["n"], "found": c["found"], "recall": rate(c["found"], c["n"])} for rel, c in by.items()}, miss


def precision_v2(added, keys, pairs):
    """Независимые пары рёбер V2 с кадром holdout: верно / неверно / открыто / эталон пару не видел."""
    K = {k.upper() for k in keys}
    pmap = {}
    for a, xs in pairs.items():
        for x in xs:
            pmap[frozenset((a.upper(), x["relative"].upper()))] = x["ref_pair_relation"]
    res = defaultdict(Counter)
    wrong = []
    for e in added:
        if not ({e["source"], e["target"]} & K):
            continue
        k = frozenset((e["source"], e["target"]))
        rel = pmap.get(k)
        out = "unjudged" if rel is None else ref_outcome(e, rel)
        res[(e["detector"], e["level"])][out] += 1
        if out == "wrong":
            wrong.append("%s %s %s %s: эталон %s" % (e["source"], e["type"], e["target"], e["level"], rel))
    return {"%s %s" % k: dict(v) for k, v in sorted(res.items())}, wrong


def exact_recall(ix, keys, pairs, g):
    """Пары эталона, где кадры совпадают попиксельно (по индексу): связаны ли они ребром, и что сказал судья. Пара,
    которую уже держит другое ребро (петля анимации MCD), связана - второе ребро на ту же пару не кладётся."""
    out = []
    for a in keys:
        for x in pairs.get(a, []):
            b = x["relative"].upper()
            if b in ix.exact(a) or b in ix.mirror(a):
                e = g.between(a, b)
                out.append({"pair": [a, b], "mirror": b in ix.mirror(a), "ref": x["ref_pair_relation"],
                            "found": bool(e and e["level"] in BINDING), "edge": e["type"] if e else ""})
    return out


def score_rows(rows, g, pairs, fsets, v8):
    out = []
    for r in rows:
        a = r["asset_id"]
        roles = pipe_roles(g, a)
        pipe, _why = v8.pipeline_of(r["semantic_eff"], r["surface"], roles)
        creative = pipe == "OBJECT_PIPELINE" and not bound(g, a) and not has_evidence(g, a)
        out.append({"asset_id": a, "layer": r.get("layer", ""), "pipeline": pipe, "creative": creative,
                    "ref_pipeline": r["ref_pipeline"], "ref_role_groups": r["ref_role_groups"],
                    "ref_role_status": r["ref_role_status"],
                    "groups": groups_of(g, a), "groups_cand": groups_of(g, a, BINDING + ("CANDIDATE",),
                                                                        BINDING + ("CANDIDATE",)),
                    "danger": danger_v2(r, creative, g, pairs.get(a, []), fsets[a.upper()]),
                    "frozen_creative": r["creative"]})
    return out


def logic(rows):
    closed = [r for r in rows if r["ref_pipeline"] != "open"]
    dec = [r for r in closed if r["pipeline"] != "REVIEW"]
    ok = [r for r in dec if r["pipeline"] == r["ref_pipeline"]]
    return {"accuracy": rate(len(ok), len(dec)), "coverage": rate(len(dec), len(closed)), "ok": len(ok),
            "decided": len(dec), "closed": len(closed)}


def do_report(out=OUT, h8=H8):
    import routing_model_v8 as v8
    rep, ref, pairs, h, sha = h8_inputs(h8)
    v2 = ir.load_json(p(out, "relations_v2.json"))
    ctl = ir.load_json(p(out, "controls.json")) if os.path.exists(p(out, "controls.json")) else None
    ix = load_index(out)
    keys = [x["asset_id"] for x in h["items"]]
    for rr_ in (rep["rows"], rep["rows_logic"]):
        assert [r["asset_id"] for r in rr_] == keys, "строки отчёта V8 не в порядке holdout"
    import map_mockup as mm
    mcd = v8.Mcd(mm.World())
    fsets = {a.upper(): v8.facts(mcd, a) for a in keys}
    g8 = v8_graph(rep["rows"])
    g = v8_graph(rep["rows"])
    added = add_v2(g, v2)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "RELATION_DISCOVERY_V2_PREP",
           "thresholds": THRESHOLDS, "h8_sha256": sha, "relations_v2_created": v2["created"], "axes": {}}
    for axis, rows in (("logic", rep["rows_logic"]), ("end_to_end", rep["rows"])):
        s8, s2 = score_rows(rows, g8, pairs, fsets, v8), score_rows(rows, g, pairs, fsets, v8)
        frozen = {r["asset_id"]: r for r in rows}
        for x in s8 + s2:
            x["groups_frozen"] = frozen[x["asset_id"]]["relation_groups"] or ["canonical"]
        res["axes"][axis] = {
            "frozen_dangerous": [r["asset_id"] for r in rows if v8.dangerous_creative_standalone(r)],
            "v2rule_v8edges": {r["asset_id"]: r["danger"] for r in s8 if r["danger"]},
            "v2rule_v2edges": {r["asset_id"]: r["danger"] for r in s2 if r["danger"]},
            "creative": {"frozen": sum(r["creative"] for r in rows), "v8edges": sum(r["creative"] for r in s8),
                         "v2edges": sum(r["creative"] for r in s2)},
            "creative_to_review": [r["asset_id"] for r, r8 in zip(s2, s8) if r8["creative"] and not r["creative"]
                                   and r["pipeline"] == "OBJECT_PIPELINE" and not bound(g, r["asset_id"])],
            "logic_v8edges": logic(s8), "logic_v2edges": logic(s2),
            "groups": {"frozen_own": group_metrics(s8, "groups_frozen"), "v8_both": group_metrics(s8, "groups"),
                       "v2": group_metrics(s2, "groups"), "v2_cand": group_metrics(s2, "groups_cand")},
            "rows": s2}
    pm8, _m8 = pair_metrics(g8, keys, pairs, BINDING)
    pm2, miss2 = pair_metrics(g, keys, pairs, BINDING)
    pm2c, _m2c = pair_metrics(g, keys, pairs, BINDING + ("CANDIDATE",))
    prec, wrong = precision_v2(added, keys, pairs)
    res.update({"pairs": {"v8": pm8, "v2": pm2, "v2_cand": pm2c, "missed_v2": miss2},
                "precision_v2": prec, "wrong_v2": wrong, "exact": exact_recall(ix, keys, pairs, g),
                "added": Counter("%s %s" % (e["type"], e["level"]) for e in added),
                "added_edges": added, "controls": control_stats(ctl) if ctl else None})
    ir.dump_json(p(out, "report.json"), res)
    write_md(out, res)
    print("отчёт: %s" % p(out, "report.md"))


def fmt_group(gm):
    return "%s (%s/%s)" % (gm["recall"], round(gm["recall"] * gm["reference"]) if gm["recall"] is not None else 0,
                           gm["reference"])


def write_md(out, res):
    L = ["# RELATION_DISCOVERY_V2_PREP — связи 60 кадров holdout V8", "",
         "Диагностика на известных 60 (специалист 02.10): маршрут B не меняется, V8 остаётся FAIL. Пороги заданы до "
         "прогона: %s." % ", ".join("%s %s" % kv for kv in res["thresholds"].items()),
         "Входы V8 только читаются: %s." % ", ".join("%s %s" % (k, v[:12]) for k, v in res["h8_sha256"].items()), ""]
    for axis, name in (("logic", "ось A эталона (как B_SAFETY)"), ("end_to_end", "ось A специалиста (как E2E_SAFETY)")):
        x = res["axes"][axis]
        L += ["## Безопасность — %s" % name, "",
              "| правило | опасных | кадры |", "|---|---|---|",
              "| V8 замороженное (без направления) | %d | %s |" % (len(x["frozen_dangerous"]), " ".join(x["frozen_dangerous"])),
              "| V2 с направлением, рёбра V8 | %d | %s |" % (len(x["v2rule_v8edges"]), " ".join(x["v2rule_v8edges"])),
              "| V2 с направлением, рёбра V8 + V2 | %d | %s |" % (len(x["v2rule_v2edges"]), " ".join(x["v2rule_v2edges"])),
              "",
              "Одиночных творческих заказов: замороженный %d, по рёбрам V8 %d, V8 + V2 %d. Ушли в ревью только из-за "
              "кандидатов V2: %s." % (x["creative"]["frozen"], x["creative"]["v8edges"], x["creative"]["v2edges"],
                                      ", ".join(x["creative_to_review"]) or "нет"), ""]
        if x["v2rule_v2edges"]:
            L += ["Причины (V2, рёбра V8 + V2):", ""] + ["- %s: %s" % (a, "; ".join(w)) for a, w in x["v2rule_v2edges"].items()] + [""]
        L += ["Логика B: рёбра V8 %s (%s/%s, охват %s), V8 + V2 %s (%s/%s, охват %s)" % (
            x["logic_v8edges"]["accuracy"], x["logic_v8edges"]["ok"], x["logic_v8edges"]["decided"],
            x["logic_v8edges"]["coverage"], x["logic_v2edges"]["accuracy"], x["logic_v2edges"]["ok"],
            x["logic_v2edges"]["decided"], x["logic_v2edges"]["coverage"]), ""]
    gm = res["axes"]["logic"]["groups"]
    L += ["## Полнота по группам связи (кадр, ось A эталона)", "",
          "Свои рёбра V8 — как в замороженном отчёте; «в обе стороны» — те же рёбра V8, прочитанные и со стороны основы "
          "(голова петли, основа разрушения): это подсчёт, а не новое обнаружение.", "",
          "| группа | V8 свои | V8 в обе стороны | V8 + V2 | V8 + V2 с кандидатами | точность V8 + V2 |",
          "|---|---|---|---|---|---|"]
    for gr in GROUPS:
        L.append("| %s | %s | %s | %s | %s | %s (%d) |" % (gr, fmt_group(gm["frozen_own"][gr]), fmt_group(gm["v8_both"][gr]),
                                                        fmt_group(gm["v2"][gr]), fmt_group(gm["v2_cand"][gr]),
                                                        gm["v2"][gr]["precision"], gm["v2"][gr]["predicted"]))
    L += ["", "## Пары эталона с закрытым смыслом", "", "| смысл | пар | V8 | V8 + V2 | V8 + V2 с кандидатами |",
          "|---|---|---|---|---|"]
    for rel in sorted(res["pairs"]["v2"]):
        a, b, c = res["pairs"]["v8"].get(rel, {}), res["pairs"]["v2"][rel], res["pairs"]["v2_cand"][rel]
        L.append("| %s | %d | %s | %s | %s |" % (rel, b["n"], a.get("recall"), b["recall"], c["recall"]))
    ex = res["exact"]
    L += ["", "## Точные копии", "",
          "Пар эталона, где кадры совпадают попиксельно (или зеркально): %d, связано ребром: %d (полнота %s). Судья: %s." % (
              len(ex), sum(x["found"] for x in ex), rate(sum(x["found"] for x in ex), len(ex)),
              ", ".join("%s %d" % kv for kv in Counter(x["ref"] for x in ex).most_common()) or "-"), ""]
    sp = [v for k, v in res["precision_v2"].items() if k.endswith("STRONG")]
    ok, bad = sum(v.get("ok", 0) for v in sp), sum(v.get("wrong", 0) for v in sp)
    L += ["## Точность рёбер V2 на 60 (независимые пары)", "",
          "STRONG на судимых парах: %d верно, %d неверно (точность %s)." % (ok, bad, rate(ok, ok + bad)), "",
          "| детектор | верно | неверно | открыто | эталон не видел |",
          "|---|---|---|---|---|"]
    for k, v in res["precision_v2"].items():
        L.append("| %s | %d | %d | %d | %d |" % (k, v.get("ok", 0), v.get("wrong", 0), v.get("open", 0), v.get("unjudged", 0)))
    if res["wrong_v2"]:
        L += ["", "Неверные:", ""] + ["- " + w for w in res["wrong_v2"]]
    L += ["", "Добавлено рёбер V2: " + ", ".join("%s %d" % kv for kv in sorted(res["added"].items())), ""]
    c = res["controls"]
    if c:
        L += ["## Контроль: пары эталонов V4_R1, V5, V7", "",
              "Пары из прежних эталонов (судьи смотрели досье кандидатов, NONE — трудные отрицательные). Пороги на них не "
              "подбирались. Пар «связи нет»: %d, из них со STRONG V2: %d, с любым ребром V2: %d." % (
                  c["none_pairs"], c["none_with_strong"], c["none_with_any"]), "",
              "Точность STRONG на судимых парах (%d рёбер): смысл совпал %s; связь есть, судья не сказал NONE %s." % (
                  c["strong_judged"], c["strong_precision"], c["strong_binding_precision"]), "",
              "| детектор | верно | неверно | открыто |", "|---|---|---|---|"]
        for k, v in c["by_detector"].items():
            L.append("| %s | %d | %d | %d |" % (k, v.get("ok", 0), v.get("wrong", 0), v.get("open", 0)))
        L += ["", "| смысл эталона | пар | найдено STRONG | найдено любым |", "|---|---|---|---|"]
        for rel, v in c["recall"].items():
            L.append("| %s | %d | %d (%s) | %d (%s) |" % (rel, v["n"], v["strong"], rate(v["strong"], v["n"]),
                                                       v["any"], rate(v["any"], v["n"])))
        if c["fp_types"]:
            L += ["", "Рёбра на парах NONE: " + "; ".join("%s: %s" % (k, v) for k, v in c["fp_types"].items())]
        L.append("")
    L += ["## Пропущенные пары (V8 + V2)", ""] + ["- " + m for m in res["pairs"]["missed_v2"]] + [""]
    with open(p(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L))


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["index", "discover", "controls", "report"])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.cmd == "index":
        import map_mockup as mm
        os.makedirs(p(a.out, "index"), exist_ok=True)
        d = build_index(mm.World())
        ir.dump_json(p(a.out, "index", "frames.json"), d)
        print("индекс: наборов %d, непустых кадров %d" % (d["sets"], len(d["frames"])))
    elif a.cmd == "discover":
        h = ir.load_json(p(H8, "holdout.json"))
        ctx = Ctx(index=load_index(a.out))
        ir.dump_json(p(a.out, "relations_v2.json"), discover(ctx, [x["asset_id"] for x in h["items"]]))
    elif a.cmd == "controls":
        ctx = Ctx(index=load_index(a.out))
        ir.dump_json(p(a.out, "controls.json"), controls(ctx))
    else:
        do_report(a.out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
