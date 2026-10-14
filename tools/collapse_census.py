#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0 обрушения зданий: схема опор по картам игры и сценарии сноса без движка.

ТЗ - docs/research/building-collapse-task-2026-10-07.md. Движок не трогается, данные игры
только читаются (как их читает движок: MAP по BattlescapeGenerator::loadMAP, MCD по
MapDataSet::loadData, LOFTEMPS как Mod.cpp - сначала TERRAIN, потом GEODATA).

Модель опор v1:
  * z = 0 стоит на земле всегда;
  * несущие части: стена (полная высота, Stop_LOS), окно (полная высота без Stop_LOS),
    неразрушимое (броня 255), объект-блок и объект-колонна полной высоты, краевой bigWall;
  * пол на z подпирается несущими частями на z-1 (стена подпирает обе клетки по сторонам,
    объект - свою, краевой bigWall - ещё соседа за краем);
  * подпёртый пол держит соседей консолью на C клеток и пролётом между двумя подпёртыми
    по оси x или y длиной до L;
  * стена на z стоит на опёртом полу с любой стороны или на той же несущей стене ниже;
  * объект на z - на опёртом полу, на несущем объекте ниже или на опёртой несущей стене
    своей клетки.

    py -3.13 tools\collapse_census.py scan
    py -3.13 tools\collapse_census.py sheet --block URBAN05 [--terrain URBAN]
    py -3.13 tools\collapse_census.py damage            (после записи census\collapse\expect.tsv)

Выход - census\collapse\ (census в гит не идёт).
"""
import argparse
import hashlib
import os
import re
import sys
from collections import defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import pck_census as pc                          # noqa: E402

ENC = "utf-8-sig"
REC = 62
KINDS = ("f", "w", "n", "o")                     # пол, стена З, стена С, объект - слоты MAP
BEARING = {"hard", "wall", "window", "block", "column", "edgewall", "truss"}
PRESETS = [(2, 12, False), (1, 8, True), (2, 12, True), (3, 16, True), (2, 99, True), (99, 99, True)]
MAIN_PRESET = (2, 12, True)
# объект во всю высоту слабее этой брони - мебель и штабели (ящики URBAN 42/43 - 20, шкафы FRNITURE - 4-22),
# а не колонна (колонна навеса URBAN 72 - 35, скала пещер - 35-50). Порог - находка этапа 0, не решение
COLUMN_MIN_ARMOR = int(os.environ.get("COLLAPSE_COLUMN_MIN_ARMOR", "30"))
# краевой bigWall (Pathfinding.h): 4 WEST, 5 NORTH, 6 EAST, 7 SOUTH, 8 EAST+SOUTH, 9 WEST+NORTH
EDGE_NB = {4: [(-1, 0)], 5: [(0, -1)], 6: [(1, 0)], 7: [(0, 1)],
           8: [(1, 0), (0, 1)], 9: [(-1, 0), (0, -1)]}


# ------------------------------------------------------------------ данные игры

def load_loft(files):
    path = files.find(os.path.join("TERRAIN", "LOFTEMPS.DAT")) \
        or files.find(os.path.join("GEODATA", "LOFTEMPS.DAT"))
    with open(path, "rb") as f:
        data = f.read()
    vals = [data[i] | (data[i + 1] << 8) for i in range(0, len(data) - 1, 2)]
    occ = [any(vals[t * 16:(t + 1) * 16]) for t in range(len(vals) // 16)]
    return path, occ


PATCHES = {}                                     # набор MCD -> [запись патча], как Mod::_MCDPatches


def load_patches(dirs):
    """MCDPatches из рулсетов по порядку загрузки (мастер, потом мод): записи одного набора дописываются
    друг за другом (Mod.cpp, MCDPatch::load), MCDPatch::modifyData применяет их по порядку."""
    PATCHES.clear()
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.lower().endswith(".rul"):
                continue
            try:
                doc = pc.load_yaml(os.path.join(d, name))
            except Exception as e:                              # noqa: BLE001
                print("  рулсет %s не разобран: %s" % (name, e), file=sys.stderr)
                continue
            for p in (doc or {}).get("MCDPatches") or [] if isinstance(doc, dict) else []:
                if isinstance(p, dict) and p.get("type"):
                    PATCHES.setdefault(p["type"], []).extend(p.get("data") or [])
    return sum(len(v) for v in PATCHES.values())


def apply_patch(name, recs, loft_occ):
    for m in PATCHES.get(name, ()):
        i = m.get("MCDIndex")
        if not isinstance(i, int) or i >= len(recs):
            continue
        r = recs[i]
        for src, dst in (("bigWall", "big_wall"), ("TUWalk", "tu_walk"), ("deathTile", "die"),
                         ("terrainHeight", "t_level"), ("armor", "armor"), ("objectType", "type")):
            if src in m:
                r[dst] = int(m[src])
        for src, dst in (("stopLOS", "stop_los"), ("noFloor", "no_floor")):
            if src in m:
                r[dst] = int(bool(m[src]))
        if "LOFTS" in m:
            r["layers"] = [bool(loft_occ[v]) if v < len(loft_occ) else False for v in m["LOFTS"][:12]]
            r["nl"] = sum(r["layers"])
        r["patched"] = True


def read_mcd(files, name, loft_occ, cache):
    if name in cache:
        return cache[name]
    path = files.find(os.path.join("TERRAIN", name + ".MCD"))
    recs = []
    if path:
        with open(path, "rb") as f:
            d = f.read()
        for i in range(0, len(d) - REC + 1, REC):
            r = d[i:i + REC]
            layers = [bool(loft_occ[v]) if v < len(loft_occ) else False for v in r[8:20]]
            recs.append({
                "layers": layers, "nl": sum(layers),
                "ufo_door": r[30], "stop_los": r[31], "no_floor": r[32], "big_wall": r[33],
                "door": r[35], "tu_walk": r[39], "armor": r[42], "die": r[44], "alt": r[46],
                "t_level": r[48] - 256 if r[48] > 127 else r[48], "type": r[53]})
    apply_patch(name, recs, loft_occ)
    cache[name] = recs
    return recs


def classify(rec, kind):
    lay, nl = rec["layers"], rec["nl"]
    full = nl >= 10 and lay[11]
    door = rec["door"] or rec["ufo_door"]
    if kind == "f":
        return "floor"
    if kind in ("w", "n"):
        if rec["armor"] == 255:
            return "hard"
        if door:
            return "door"
        if full:
            return "wall" if rec["stop_los"] else "window"
        if (lay[11] or lay[10]) and nl >= 6:
            return "window"
        return "low"
    if door:
        return "door"
    if full:
        if rec["armor"] == 255:
            return "hard"
        bw = rec["big_wall"]
        if bw in (1, 2, 3):
            return "block"
        if bw in EDGE_NB:
            return "edgewall"
        # штабель ящиков, шкаф, холодильник тоже во всю высоту клетки - отличает их только броня
        return "column" if rec["armor"] >= COLUMN_MIN_ARMOR else "furniture"
    if lay[0] and (lay[11] or lay[10]) and nl >= 6 and rec["armor"] < 255:
        if rec["armor"] < COLUMN_MIN_ARMOR:
            return "furniture"
        return "truss"                   # решётчатая опора: низ и верх клетки, пролёты в середине
    return "object"


def collect(mod_dir):
    """Террейны со своим видом: обычный, корабль игрока, НЛО."""
    out = {}
    rul = os.path.join(mod_dir, "Ruleset")
    for name in sorted(os.listdir(rul)):
        if not name.lower().endswith(".rul"):
            continue
        try:
            doc = pc.load_yaml(os.path.join(rul, name))
        except Exception as e:                                  # noqa: BLE001
            print("  рулсет %s не разобран: %s" % (name, e), file=sys.stderr)
            continue
        if not isinstance(doc, dict):
            continue
        found = [("terrain", t) for t in doc.get("terrains") or []]
        for sec, kind in (("crafts", "craft"), ("ufos", "ufo")):
            for it in doc.get(sec) or []:
                if isinstance(it, dict) and isinstance(it.get("battlescapeTerrainData"), dict):
                    found.append((kind, it["battlescapeTerrainData"]))
        for kind, t in found:
            if not isinstance(t, dict) or not t.get("name"):
                continue
            if not t.get("mapDataSets") or not t.get("mapBlocks"):
                continue
            out[t["name"]] = (kind, t)
    return out


# ------------------------------------------------------------------ блок карты

class Block:
    def __init__(self, terrain, kind, name, sx, sy, sz):
        self.terrain, self.kind, self.name = terrain, kind, name
        self.sx, self.sy, self.sz = sx, sy, sz
        self.parts = {}                  # (k, x, y, z) -> {set, idx, cls, rec}
        self.lv = [{k: {} for k in KINDS} for _ in range(sz)]

    def add(self, k, x, y, z, s, idx, rec):
        key = (k, x, y, z)
        self.parts[key] = {"set": s, "idx": idx, "cls": classify(rec, k), "rec": rec}
        self.lv[z][k][(x, y)] = key

    def bearing(self, key):
        return self.parts[key]["cls"] in BEARING


def load_block(files, tname, kind, t, bname, mcd_cache, loft_occ, sizes):
    mp = files.find(os.path.join("MAPS", bname + ".MAP"))
    if not mp:
        return None, "нет .MAP"
    with open(mp, "rb") as f:
        data = f.read()
    if len(data) < 3:
        return None, "пустой .MAP"
    sy, sx, sz = data[0], data[1], data[2]
    sets = list(t.get("mapDataSets") or [])
    for s in sets:
        if s not in sizes:
            sizes[s] = len(read_mcd(files, s, loft_occ, mcd_cache))
    blk = Block(tname, kind, bname, sx, sy, sz)
    body = data[3:]
    n = len(body) // 4
    if n != sx * sy * sz:
        return None, "размер %d клеток против %dx%dx%d" % (n, sx, sy, sz)
    i = 0
    for zz in range(sz - 1, -1, -1):             # в файле сверху вниз
        for y in range(sy):
            for x in range(sx):
                cell = body[i * 4:i * 4 + 4]
                i += 1
                for p, k in enumerate(KINDS):
                    v = cell[p]
                    if not v:
                        continue
                    s, idx = pc.resolve(v, sets, sizes)
                    if s is None:                # движок берёт BLANKS 0 - пусто
                        continue
                    if s.upper() == "BLANKS":
                        continue
                    recs = read_mcd(files, s, loft_occ, mcd_cache)
                    if idx >= len(recs):
                        continue
                    blk.add(k, x, y, zz, s, idx, recs[idx])
    return blk, None


# ------------------------------------------------------------------ опоры

def evaluate(blk, removed=frozenset(), C=2, L=12, mass_rule=True, order=2, carry_rule="any"):
    """Опёртые части и сведения об остальных. Снизу вверх, без кругов: пол z зависит
    только от частей z-1, стены и объекты z - от пола z и частей z-1.
    carry_rule - какая опёртая несущая часть несёт этаж выше: "any" - любая (прежняя модель),
    "direct" - только стоящая на несущей ниже, на прямо подпёртом полу или в массиве; стена
    на консоли или в пролёте стоит, но этаж выше на неё не опирается. Несущие части,
    которые несут, - в blk.carry после вызова."""
    sup = set()
    carry = set()
    info = {}                                    # ключ пола -> (direct, need_c, need_l)
    for z in range(blk.sz):
        lvl = blk.lv[z]
        live = {k: {xy: key for xy, key in lvl[k].items() if key not in removed} for k in KINDS}
        if z == 0:
            for k in KINDS:
                sup.update(live[k].values())
                carry.update(key for key in live[k].values() if blk.bearing(key))
            continue
        below = blk.lv[z - 1]
        props = set()
        for (x, y), key in below["w"].items():
            if key in carry:
                props.update(((x, y), (x - 1, y)))
        for (x, y), key in below["n"].items():
            if key in carry:
                props.update(((x, y), (x, y - 1)))
        for (x, y), key in below["o"].items():
            if key in carry:
                props.add((x, y))
                for dx, dy in EDGE_NB.get(blk.parts[key]["rec"]["big_wall"], ()):
                    props.add((x + dx, y + dy))
        floors = set(live["f"])
        # массив: несущие объекты полной высоты держат друг друга сбоку (скала над пещерой)
        mass = {xy for xy, key in live["o"].items() if blk.bearing(key)}
        msup = set()
        for xy in mass:
            under = below["o"].get(xy)
            if under in carry or (xy in floors and xy in props):
                msup.add(xy)
        if mass_rule:
            q = deque(msup)
            while q:
                x, y = q.popleft()
                for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if nb in mass and nb not in msup:
                        msup.add(nb)
                        q.append(nb)
        direct = floors & (props | msup)
        dist = {xy: 0 for xy in direct}
        q = deque(direct)
        while q:
            x, y = q.popleft()
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in floors and nb not in dist:
                    dist[nb] = dist[(x, y)] + 1
                    q.append(nb)
        okf = {xy for xy in floors if dist.get(xy) is not None and dist[xy] <= C}
        # балки по порядку: сначала между прямо подпёртыми, затем между уже опёртыми
        # (обвязка по колоннам, потом плита между обвязками)
        best_l = {}
        for _ in range(order):
            base = set(okf) | direct
            for xy in floors:
                nl = beam(xy, floors, base)
                if nl is not None and (xy not in best_l or nl < best_l[xy]):
                    best_l[xy] = nl
                if nl is not None and nl <= L:
                    okf.add(xy)
        for xy in floors:
            info[live["f"][xy]] = (xy in direct, dist.get(xy), best_l.get(xy))
            if xy in okf:
                sup.add(live["f"][xy])
        for k, sides in (("w", lambda x, y: ((x, y), (x - 1, y))),
                         ("n", lambda x, y: ((x, y), (x, y - 1)))):
            for (x, y), key in live[k].items():
                under = below[k].get((x, y))
                if any(s in okf for s in sides(x, y)) or under in carry:
                    sup.add(key)
                    if blk.bearing(key) and (carry_rule == "any" or under in carry or
                                             any(s in direct for s in sides(x, y))):
                        carry.add(key)
        furn = {xy for xy, key in live["o"].items() if blk.parts[key]["cls"] == "furniture"}
        fsup = set()
        for (x, y), key in live["o"].items():
            under = below["o"].get((x, y))
            walls = [live["w"].get((x, y)), live["w"].get((x + 1, y)),
                     live["n"].get((x, y)), live["n"].get((x, y + 1))]
            # предмет стоит и на предмете во всю высоту (крона на стволе, верх штабеля): нести пол мебель
            # не может, а продолжение самой себя - может
            if (x, y) in okf or (x, y) in msup or \
                    under in carry or (under in sup and blk.parts[under]["cls"] == "furniture") or \
                    any(w in carry for w in walls if w):
                sup.add(key)
                if blk.bearing(key) and (carry_rule == "any" or under in carry or
                                         (x, y) in direct or (x, y) in msup):
                    carry.add(key)
                if (x, y) in furn:
                    fsup.add((x, y))
        # предмет на несколько клеток (крона дерева над соседними клетками) держится целиком,
        # если опёрта хоть одна его клетка; пол на нём от этого не держится - пол считан выше
        # от опёртой клетки самого предмета или от несущего ствола рядом (колонна JUNGLE 80 под кроной)
        q = deque(fsup | {xy for xy, key in live["o"].items() if key in sup and blk.bearing(key)})
        while q:
            x, y = q.popleft()
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in furn and nb not in fsup:
                    fsup.add(nb)
                    sup.add(live["o"][nb])
                    q.append(nb)
    blk.carry = carry
    return sup, info


def beam(xy, floors, direct):
    """Самый короткий пролёт через клетку между двумя подпёртыми по оси x или y."""
    if xy in direct:
        return 0
    best = None
    for dx, dy in ((1, 0), (0, 1)):
        ends = []
        for sgn in (1, -1):
            x, y = xy
            d = 0
            while True:
                x += dx * sgn
                y += dy * sgn
                d += 1
                if (x, y) not in floors:
                    d = None
                    break
                if (x, y) in direct:
                    break
            ends.append(d)
        if None not in ends:
            span = ends[0] + ends[1]
            best = span if best is None else min(best, span)
    return best


def reason(blk, key, sup, info):
    k, x, y, z = key
    if k == "f":
        direct, nc, nl = info.get(key, (False, None, None))
        if nc is not None or nl is not None:
            return "далеко от опоры: консоль %s, пролёт %s" % (
                "-" if nc is None else nc, "-" if nl is None else nl)
        below = blk.lv[z - 1]
        cls = set()
        for kk, cells in (("w", ((x, y), (x + 1, y))), ("n", ((x, y), (x, y + 1))), ("o", ((x, y),))):
            for c in cells:
                b = below[kk].get(c)
                if b:
                    cls.add(blk.parts[b]["cls"] + ("" if b in sup else "(висит)"))
        edge = x == 0 or y == 0 or x == blk.sx - 1 or y == blk.sy - 1
        tail = "; у края блока - опора может быть в соседнем" if edge else ""
        if cls:
            return "под клеткой только " + ",".join(sorted(cls)) + tail
        return "висит: под связкой пола нет ничего" + tail
    flo = blk.lv[z]["f"]
    if k in ("w", "n"):
        sides = ((x, y), (x - 1, y)) if k == "w" else ((x, y), (x, y - 1))
        if any(s in flo for s in sides):
            return "стоит на неопёртом полу"
        return "висит: нет пола и стены ниже"
    if (x, y) in flo:
        return "стоит на неопёртом полу"
    return "висит: нет пола и несущего ниже"


def why(blk, key, sup, info, removed=frozenset(), C=2, L=12, depth=0, seen=None):
    """Чем держится опёртая часть: цепочка до земли (оставшиеся связи для схемы сценария).
    Возвращает строки с отступом и множество частей цепочки."""
    seen = set() if seen is None else seen
    pad = "  " * depth
    if key in seen or depth > 12:
        return [pad + "%s:%d:%d:%d (см. выше)" % key], set()
    seen.add(key)
    k, x, y, z = key
    cls = blk.parts[key]["cls"]
    name = "%s:%d:%d:%d %s %s:%d" % (k, x, y, z, cls, blk.parts[key]["set"], blk.parts[key]["idx"])
    if key not in sup:
        return [pad + name + " - НЕ ОПЁРТО"], set()
    if z == 0:
        return [pad + name + " - земля"], {key}
    below = blk.lv[z - 1]
    lvl = blk.lv[z]
    live = lambda kk, xy: (lambda q: q if q is not None and q not in removed else None)(lvl[kk].get(xy))

    def bearing_below(xy):
        """Несущие части z-1, которые подпирают клетку пола xy (как props в evaluate)."""
        cx, cy = xy
        out = []
        for kk, cells in (("w", ((cx, cy), (cx + 1, cy))), ("n", ((cx, cy), (cx, cy + 1))), ("o", ((cx, cy),))):
            for c in cells:
                b = below[kk].get(c)
                if b and b in sup and blk.bearing(b):
                    out.append(b)
        for (ex, ey), b in below["o"].items():
            if b in sup and blk.bearing(b):
                for dx, dy in EDGE_NB.get(blk.parts[b]["rec"]["big_wall"], ()):
                    if (ex + dx, ey + dy) == (cx, cy):
                        out.append(b)
        return out

    lines, chain = [pad + name], {key}
    def sub(kk):
        return why(blk, kk, sup, info, removed, C, L, depth + 1, seen)
    if k == "f":
        direct, dist, span = info.get(key, (False, None, None))
        if direct:
            bb = bearing_below((x, y))
            if bb:
                lines[0] += " - прямо на несущем ниже"
                for b in bb[:2]:
                    ls, ch = sub(b)
                    lines += ls
                    chain |= ch
            else:
                lines[0] += " - прямо на массиве (несущий объект рядом)"
            return lines, chain
        floors = {xy for xy, kk in lvl["f"].items() if kk not in removed}
        if dist is not None and dist <= C:
            # путь консоли до ближайшего прямо подпёртого пола
            prev, q, end = {(x, y): None}, deque([(x, y)]), None
            while q and end is None:
                c = q.popleft()
                cf = lvl["f"].get(c)
                if c != (x, y) and info.get(cf, (False,))[0]:
                    end = c
                    break
                for nb in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)):
                    if nb in floors and nb not in prev:
                        prev[nb] = c
                        q.append(nb)
            path = []
            c = end
            while c is not None:
                path.append(c)
                c = prev[c]
            lines[0] += " - консоль %d клетк. от прямо подпёртого %s" % (dist, end)
            for c in path[:-1]:
                chain.add(lvl["f"][c])
            ls, ch = sub(lvl["f"][end])
            return lines + ls, chain | ch
        if span is not None and span <= L:
            base = {xy for xy, kk in lvl["f"].items() if kk in sup and kk not in removed and
                    (info.get(kk, (False, None))[0] or (info.get(kk, (False, None))[1] or 99) <= C)}
            ends = None
            for dx, dy in ((1, 0), (0, 1)):
                e = []
                for sgn in (1, -1):
                    cx, cy = x, y
                    while True:
                        cx, cy = cx + dx * sgn, cy + dy * sgn
                        if (cx, cy) not in floors:
                            e = None
                            break
                        if (cx, cy) in base:
                            e.append((cx, cy))
                            break
                    if e is None:
                        break
                if e and len(e) == 2:
                    ends = e
                    break
            # span из info после второго прохода балки бывает 0 (клетка уже опёрта) - длину берём по концам
            n = abs(ends[0][0] - ends[1][0]) + abs(ends[0][1] - ends[1][1]) if ends else span
            lines[0] += " - пролёт %d между %s и %s" % (n, ends[0] if ends else "?", ends[1] if ends else "?")
            for c in ends or []:
                ls, ch = sub(lvl["f"][c])
                lines += ls
                chain |= ch
            return lines, chain
        return lines + [pad + "  (опёрт без найденной причины)"], chain
    if k in ("w", "n"):
        sides = ((x, y), (x - 1, y)) if k == "w" else ((x, y), (x, y - 1))
        under = below[k].get((x, y))
        if under in sup and blk.bearing(under):
            lines[0] += " - на несущей стене ниже"
            ls, ch = sub(under)
            return lines + ls, chain | ch
        for s in sides:
            f = live("f", s)
            if f and f in sup:
                lines[0] += " - на опёртом полу %s" % (s,)
                ls, ch = sub(f)
                return lines + ls, chain | ch
        return lines, chain
    under = below["o"].get((x, y))
    f = live("f", (x, y))
    if f and f in sup:
        lines[0] += " - на опёртом полу"
        ls, ch = sub(f)
        return lines + ls, chain | ch
    if under in sup:
        lines[0] += " - на объекте ниже"
        ls, ch = sub(under)
        return lines + ls, chain | ch
    for w in (live("w", (x, y)), live("w", (x + 1, y)), live("n", (x, y)), live("n", (x, y + 1))):
        if w and w in sup and blk.bearing(w):
            lines[0] += " - на несущей стене своей клетки"
            ls, ch = sub(w)
            return lines + ls, chain | ch
    lines[0] += " - держится соседней клеткой того же предмета"
    return lines, chain


def cmd_why(args):
    """Схема сценария: что снято, что должно было упасть и чем каждая такая часть держится."""
    C, L, _ = MAIN_PRESET
    exp = os.path.join(args.out, "expect.tsv")
    lines = open(exp, encoding=ENC).read().splitlines()
    head = lines[0].split("\t")
    want = [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln.strip() and not ln.startswith("#")]
    want = [e for e in want if e["id"] in args.ids.split(",")]
    out_md = []
    for e in want:
        for tname, kind, t, bname, blk, err, cache in all_blocks(args, e["block"], e["terrain"]):
            if blk is None:
                continue
            rm = select(blk, e["remove"])
            sup0, _ = evaluate(blk, C=C, L=L)
            sup, info = evaluate(blk, frozenset(rm), C=C, L=L)
            mf = select(blk, e.get("must_fall", "")) - rm
            ms = select(blk, e.get("must_stand", "")) - rm
            stood = sorted(k for k in mf if k in sup)
            fell = sorted(k for k in ms if k not in sup and k in sup0)
            out_md.append("### %s %s %s" % (e["id"], tname, bname))
            out_md.append("")
            out_md.append("Ожидание: " + e.get("note", ""))
            out_md.append("")
            out_md.append("Снято %d: %s" % (len(rm), " ".join("%s:%d:%d:%d" % k for k in sorted(rm))))
            out_md.append("")
            out_md.append("Должно упасть %d, устояло %d; должно стоять %d, упало %d." % (
                len(mf), len(stood), len(ms), len(fell)))
            out_md.append("")
            mark = set()
            roots = {}
            for k in stood:
                ls, ch = why(blk, k, sup, info, frozenset(rm), C, L)
                mark |= ch
                # одна цепочка на механизм (правило каждого звена без координат), чтобы не печатать 60 одинаковых
                sig = "|".join(re.sub(r"[\d(), :]+", " ", ln.split(" - ", 1)[-1]).strip() + "/" +
                               ln.split()[1] for ln in ls if " - " in ln)
                roots.setdefault(sig, []).append((k, ls))
            for sig, items in roots.items():
                k, ls = items[0]
                out_md.append("Устояло %d (%s), пример `%s:%d:%d:%d`:" % (
                    (len(items), " ".join("%s:%d:%d:%d" % kk for kk, _ in items[:12]) +
                     (" ..." if len(items) > 12 else "")) + k))
                out_md.append("")
                out_md.append("```")
                out_md += ls
                out_md.append("```")
                out_md.append("")
            for k in fell[:6]:
                out_md.append("Упало, хотя должно стоять: `%s:%d:%d:%d` - %s" % (k + (reason(blk, k, sup, info),)))
            if fell:
                out_md.append("")
            sheet(blk, os.path.join(args.out, "sheets", "why_%s.png" % e["id"]), removed=rm, base=sup0,
                  C=C, L=L, title="%s %s: снято (маджента), упало (красн.), цепочка устоявших (голуб.)" % (
                      e["id"], bname), pre=(sup, info), mark=mark)
    p = os.path.join(args.out, "why.md")
    with open(p, "w", encoding=ENC) as f:
        f.write("\n".join(out_md) + "\n")
    print("\n".join(out_md))
    print(p)


# ------------------------------------------------------------------ обход данных

def open_data(args):
    mod_dir = os.path.join(args.install, "user", "mods", args.mod)
    files = pc.Files([mod_dir, os.path.join(args.install, "standard", args.master),
                      os.path.join(args.install, "UFO")])
    loft_path, loft_occ = load_loft(files)
    load_patches([os.path.join(args.install, "standard", args.master), os.path.join(mod_dir, "Ruleset")])
    return mod_dir, files, loft_path, loft_occ


def all_blocks(args, only_block=None, only_terrain=None):
    mod_dir, files, loft_path, loft_occ = open_data(args)
    terr = collect(mod_dir)
    cache, sizes = {}, {}
    seen = set()
    for tname, (kind, t) in sorted(terr.items()):
        if only_terrain and tname.upper() != only_terrain.upper():
            continue
        for b in t.get("mapBlocks") or []:
            bname = b.get("name") if isinstance(b, dict) else None
            if not bname:
                continue
            if only_block and bname.upper() != only_block.upper():
                continue
            sig = (bname, tuple(t.get("mapDataSets") or []))
            if sig in seen:                    # тот же блок на тех же наборах
                continue
            seen.add(sig)
            blk, err = load_block(files, tname, kind, t, bname, cache, loft_occ, sizes)
            yield tname, kind, t, bname, blk, err, cache


def write_tsv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join("" if v is None else str(v) for v in r) + "\n")


def upper_parts(blk):
    return [k for k in blk.parts if k[3] > 0]


def rubble_candidates(t, files_cache):
    """Низкие проходимые объекты набора, в которые что-то превращается при разрушении."""
    out = []
    for s in t.get("mapDataSets") or []:
        recs = files_cache.get(s) or []
        targets = {r["die"] for r in recs if r["die"]}
        for i in sorted(targets):
            if i >= len(recs):
                continue
            r = recs[i]
            if r["type"] == 3 and r["nl"] <= 4 and r["tu_walk"] < 255 \
                    and not (r["door"] or r["ufo_door"]) and r["armor"] < 255:
                out.append("%s:%d" % (s, i))
    return out


# ------------------------------------------------------------------ scan

def cmd_scan(args):
    out = args.out
    rows, part_rows, preset_tot, rub_rows, broken = [], [], defaultdict(lambda: [0, 0, 0, 0]), [], []
    done_terr = set()
    nblk = 0
    for tname, kind, t, bname, blk, err, cache in all_blocks(args):
        if tname not in done_terr:
            done_terr.add(tname)
            cand = rubble_candidates(t, cache)
            rub_rows.append((tname, kind, len(cand), " ".join(cand[:12])))
        if blk is None:
            broken.append((tname, bname, err))
            continue
        nblk += 1
        up = upper_parts(blk)
        if not up:
            continue
        for C, L, M in PRESETS:
            sup, info = evaluate(blk, C=C, L=L, mass_rule=M)
            bad = [k for k in up if k not in sup]
            for grp in (kind, "all"):
                tot = preset_tot[(C, L, M, grp)]
                tot[0] += 1
                tot[1] += bool(bad)
                tot[2] += len(up)
                tot[3] += len(bad)
            if (C, L, M) == MAIN_PRESET:
                reasons = defaultdict(int)
                for k in bad:
                    r = reason(blk, k, sup, info)
                    reasons[r.split(":")[0].split(";")[0]] += 1
                    pr = blk.parts[k]
                    part_rows.append((tname, kind, bname, "%s:%d:%d:%d" % k, pr["cls"],
                                      "%s:%d" % (pr["set"], pr["idx"]), r))
                fl = [v for kk, v in info.items() if not v[0]]
                need_c = max([v[1] for v in fl if v[1] is not None] or [0])
                need_l = max([v[2] for v in fl if v[2] is not None] or [0])
                rows.append((tname, kind, bname, "%dx%dx%d" % (blk.sx, blk.sy, blk.sz),
                             len(up), len(bad), round(len(bad) / len(up), 3), need_c, need_l,
                             "; ".join("%s %d" % kv for kv in sorted(reasons.items(), key=lambda a: -a[1]))))
        if nblk % 300 == 0:
            print("  блоков %d" % nblk)
    write_tsv(os.path.join(out, "static.tsv"),
              ["terrain", "kind", "block", "size", "parts_up", "unsupported", "share",
               "need_c_max", "need_l_max", "reasons"], rows)
    write_tsv(os.path.join(out, "static_parts.tsv"),
              ["terrain", "kind", "block", "part", "class", "mcd", "reason"], part_rows)
    write_tsv(os.path.join(out, "rubble.tsv"), ["terrain", "kind", "candidates", "first"], rub_rows)
    write_tsv(os.path.join(out, "broken.tsv"), ["terrain", "block", "error"], broken)
    prow = [("C=%d L=%d %s %s" % (p[0], p[1], "массив" if p[2] else "без_массива", p[3]), v[0], v[1], round(v[1] / max(v[0], 1), 3), v[2], v[3],
             round(v[3] / max(v[2], 1), 4)) for p, v in sorted(preset_tot.items())]
    write_tsv(os.path.join(out, "presets.tsv"),
              ["preset", "blocks_with_upper", "blocks_with_unsupported", "share_blocks",
               "parts_up", "parts_unsupported", "share_parts"], prow)
    print("блоков прочитано %d, не прочитано %d" % (nblk, len(broken)))
    for r in prow:
        print("  %-36s блоков с верхом %5d, с неопёртым %5d (%.1f%%), частей %d из %d (%.2f%%)"
              % (r[0], r[1], r[2], 100 * r[3], r[5], r[4], 100 * r[6]))
    nz = sum(1 for r in rub_rows if r[2] == 0)
    print("террейнов без кандидата обломков: %d из %d" % (nz, len(rub_rows)))


# ------------------------------------------------------------------ сценарии

def footprints(blk, sup):
    """Здания: связные пятна опёртого пола на z=1 (не меньше 4 клеток)."""
    if blk.sz < 2:
        return []
    fl = {xy for xy, key in blk.lv[1]["f"].items() if key in sup}
    out, seen = [], set()
    for s in fl:
        if s in seen:
            continue
        comp, q = set(), deque([s])
        seen.add(s)
        while q:
            x, y = q.popleft()
            comp.add((x, y))
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in fl and nb not in seen:
                    seen.add(nb)
                    q.append(nb)
        if len(comp) >= 4:
            out.append(comp)
    return out


def ground_supports(blk, F):
    """Несущие части z=0 под зданием, кроме неразрушимых."""
    lv = blk.lv[0]
    res = []
    for (x, y), key in lv["w"].items():
        if ((x, y) in F or (x - 1, y) in F) and blk.bearing(key):
            res.append(key)
    for (x, y), key in lv["n"].items():
        if ((x, y) in F or (x, y - 1) in F) and blk.bearing(key):
            res.append(key)
    for (x, y), key in lv["o"].items():
        if (x, y) in F and blk.bearing(key):
            res.append(key)
    return [k for k in res if blk.parts[k]["cls"] != "hard"]


def scenarios(blk, F, sups):
    xs = [x for x, _ in F]
    ys = [y for _, y in F]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    sset = set(sups)
    sc = []
    walls = [k for k in sups if k[0] in ("w", "n")]
    step = max(1, len(walls) // 12)
    for k in walls[::step]:
        sc.append(("one", "%s:%d:%d" % k[:3], {k}, "nothing"))
    for name, cells in (("NW", [("w", x0, y0), ("n", x0, y0), ("o", x0, y0)]),
                        ("NE", [("w", x1 + 1, y0), ("n", x1, y0), ("o", x1, y0)]),
                        ("SW", [("w", x0, y1), ("n", x0, y1 + 1), ("o", x0, y1)]),
                        ("SE", [("w", x1 + 1, y1), ("n", x1, y1 + 1), ("o", x1, y1)])):
        rm = {c + (0,) for c in cells} & sset
        if rm:
            sc.append(("corner", name, rm, "local"))
    lines = {"W": {k for k in sset if k[0] == "w" and k[1] == x0},
             "E": {k for k in sset if k[0] == "w" and k[1] == x1 + 1},
             "N": {k for k in sset if k[0] == "n" and k[2] == y0},
             "S": {k for k in sset if k[0] == "n" and k[2] == y1 + 1}}
    for name, rm in lines.items():
        if rm:
            sc.append(("line", name, rm, "far_half"))
    sc.append(("storey", "all", sset, "most"))
    return sc, (x0, x1, y0, y1)


def check_auto(kind, side, fallen, blk, F, bbox, base_up):
    x0, x1, y0, y1 = bbox
    fl = [k for k in fallen if k[0] == "f"]
    if kind == "one":
        return not fallen, "упало %d" % len(fallen)
    if kind == "corner":
        return len(fl) <= 4, "упало полов %d" % len(fl)
    if kind == "line":
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        far = {"W": lambda k: k[1] > mx, "E": lambda k: k[1] < mx,
               "N": lambda k: k[2] > my, "S": lambda k: k[2] < my}[side]
        bad = [k for k in fallen if far(k)]
        return not bad, "упало %d, из них в дальней половине %d" % (len(fallen), len(bad))
    share = len(fallen) / max(base_up, 1)
    return share >= 0.9, "упало %.0f%% верха" % (100 * share)


def parse_region(tok):
    """kind:x:y:z, где каждая координата - число, a-b или *; kind - f,w,n,o или *."""
    parts = tok.split(":")
    if len(parts) != 4:
        raise ValueError("область %r: нужно kind:x:y:z" % tok)

    def rng(v):
        if v == "*":
            return None
        if "-" in v:
            a, b = v.split("-")
            return (int(a), int(b))
        return (int(v), int(v))
    return parts[0], rng(parts[1]), rng(parts[2]), rng(parts[3])


def match(region, key):
    kind, rx, ry, rz = region
    if kind != "*" and kind != key[0]:
        return False
    for r, v in ((rx, key[1]), (ry, key[2]), (rz, key[3])):
        if r is not None and not (r[0] <= v <= r[1]):
            return False
    return True


def select(blk, toks):
    regs = [parse_region(t) for t in toks.split() if t]
    return {k for k in blk.parts if any(match(r, k) for r in regs)}


def cmd_damage(args):
    out = args.out
    C, L, _ = MAIN_PRESET                      # массив - по умолчанию evaluate
    exp_path = os.path.join(out, "expect.tsv")
    expect = []
    exp_hash = None
    if os.path.exists(exp_path):
        with open(exp_path, "rb") as f:
            raw = f.read()
        exp_hash = hashlib.sha256(raw).hexdigest()[:16]
        lines = raw.decode("utf-8-sig").splitlines()
        head = lines[0].split("\t")
        for ln in lines[1:]:
            if not ln.strip() or ln.startswith("#"):
                continue
            expect.append(dict(zip(head, ln.split("\t"))))
        print("ожидания %s: %d сценариев, sha256 %s, изменён %s" % (
            exp_path, len(expect), exp_hash,
            __import__("time").strftime("%Y-%m-%d %H:%M", __import__("time").localtime(os.path.getmtime(exp_path)))))
    want = {(e["terrain"].upper(), e["block"].upper()) for e in expect}
    auto_rows, hand_rows, fall_terr = [], [], defaultdict(int)
    rub = {}
    stats = defaultdict(lambda: [0, 0])
    unbreak = []
    for tname, kind, t, bname, blk, err, cache in all_blocks(args):
        if blk is None or kind != "terrain" and not args.with_craft:
            continue
        if tname not in rub:
            rub[tname] = rubble_candidates(t, cache)
        sup0, _ = evaluate(blk, C=C, L=L)
        up0 = [k for k in upper_parts(blk) if k in sup0]
        for F in footprints(blk, sup0):
            sups = ground_supports(blk, F)
            if not sups:
                continue
            sc, bbox = scenarios(blk, F, sups)
            near = {k for k in up0 if bbox[0] - 1 <= k[1] <= bbox[1] + 1 and bbox[2] - 1 <= k[2] <= bbox[3] + 1}
            for skind, side, rm, _ in sc:
                sup, _ = evaluate(blk, frozenset(rm), C=C, L=L)
                fallen = [k for k in near if k not in sup]
                ok, note = check_auto(skind, side, fallen, blk, F, bbox, len(near))
                stats[skind][0] += 1
                stats[skind][1] += not ok
                if skind == "storey":
                    for k in fallen:
                        fall_terr[tname] += 1
                    if len(fallen) < 0.5 * len(near):
                        unbreak.append((tname, bname, "%d-%d,%d-%d" % bbox, len(near), len(fallen)))
                if not ok:
                    auto_rows.append((tname, bname, "%d-%d,%d-%d" % bbox, skind, side,
                                      " ".join("%s:%d:%d:%d" % k for k in sorted(rm))[:200], note))
        if (tname.upper(), bname.upper()) in want:
            for e in expect:
                if (e["terrain"].upper(), e["block"].upper()) != (tname.upper(), bname.upper()):
                    continue
                rm = select(blk, e["remove"])
                sup, _ = evaluate(blk, frozenset(rm), C=C, L=L)
                must_fall = select(blk, e.get("must_fall", "")) - rm
                must_stand = select(blk, e.get("must_stand", "")) - rm
                fallen_all = {k for k in sup0 if k not in sup and k not in rm}
                miss_fall = sorted(k for k in must_fall if k in sup)
                miss_stand = sorted(k for k in must_stand if k not in sup and k in sup0)
                # «должно стоять», а висело уже на целой карте: PASS по такой части пустой
                hung0 = sorted(k for k in must_stand if k not in sup0)
                extra = sorted(fallen_all - must_fall)
                verdict = "PASS" if not miss_fall and not miss_stand else "FAIL"
                if verdict == "PASS" and hung0:
                    verdict = "PASS*"
                if not rm or not (must_fall | must_stand):
                    verdict = "EMPTY"           # область не нашла ни одной части - ожидание не проверено
                hand_rows.append((e["id"], tname, bname, len(rm), len(fallen_all), verdict,
                                  len(must_fall), len(must_stand),
                                  len(miss_fall), " ".join("%s:%d:%d:%d" % k for k in miss_fall[:20]),
                                  len(miss_stand), " ".join("%s:%d:%d:%d" % k for k in miss_stand[:20]),
                                  len(hung0), " ".join("%s:%d:%d:%d" % k for k in hung0[:20]),
                                  len(extra), " ".join("%s:%d:%d:%d" % k for k in extra[:20]),
                                  e.get("note", "")))
                if args.sheets:
                    sheet(blk, os.path.join(out, "sheets", "expect_%s.png" % e["id"]),
                          removed=rm, base=sup0, C=C, L=L,
                          title="%s %s %s: %s" % (e["id"], tname, bname, verdict))
    write_tsv(os.path.join(out, "damage_fail.tsv"),
              ["terrain", "block", "bbox", "scenario", "side", "removed", "result"], auto_rows)
    write_tsv(os.path.join(out, "unbreakable.tsv"),
              ["terrain", "block", "bbox", "parts_up", "fallen"], unbreak)
    write_tsv(os.path.join(out, "expect_result.tsv"),
              ["id", "terrain", "block", "removed", "fallen", "verdict", "must_fall_n", "must_stand_n",
               "should_fall_but_stood", "list", "should_stand_but_fell", "list",
               "stand_hung_at_start", "list", "fallen_unlisted", "list", "note"], hand_rows)
    tot = sum(fall_terr.values())
    miss = sum(v for k, v in fall_terr.items() if not rub.get(k))
    srow = [(k, v[0], v[1], round(v[1] / max(v[0], 1), 3)) for k, v in sorted(stats.items())]
    write_tsv(os.path.join(out, "damage_summary.tsv"), ["scenario", "runs", "mismatch", "share"],
              srow + [("rubble_missing_share", tot, miss, round(miss / max(tot, 1), 3)),
                      ("expect_sha256", exp_hash or "-", "", "")])
    for r in srow:
        print("  %-7s прогонов %6d, против ожидания %6d (%.1f%%)" % (r[0], r[1], r[2], 100 * r[3]))
    print("  обрушенных частей при сносе этажа %d, у террейна нет обломков %d (%.1f%%)"
          % (tot, miss, 100 * miss / max(tot, 1)))
    print("  неразрушимых зданий (снос этажа роняет меньше половины): %d" % len(unbreak))
    for r in hand_rows:
        print("  %s %s %s: %s, снято %d, упало %d, должно упасть %d - устояло %d; должно стоять %d - упало %d, висело с начала %d; упало сверх списка %d" % (r[0], r[1], r[2], r[5], r[3], r[4], r[6], r[8], r[7], r[10], r[12], r[14]))


# ------------------------------------------------------------------ лист

def sheet(blk, path, removed=frozenset(), base=None, C=2, L=12, title="", pre=None, org=(0, 0, 0), mark=frozenset()):
    """pre - уже посчитанные (sup, info) для этого blk (вырезка собранной карты: опора считана по всей карте);
    org - сдвиг подписей x, y, z от вырезки к карте; mark - части цепочки опоры, обводятся голубым."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        fnt = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 11)
    except OSError:
        fnt = ImageFont.load_default()
    T = 18
    sup, info = pre if pre is not None else evaluate(blk, frozenset(removed), C=C, L=L)
    base = base if base is not None else sup
    lvls = list(range(blk.sz))
    W = blk.sx * T + 24
    H = blk.sy * T + 24
    img = Image.new("RGB", (W * len(lvls) + 8, H + 40), (250, 250, 247))
    d = ImageDraw.Draw(img)
    d.text((6, 4), "%s   (%s %s, C=%d L=%d; север вверху, x вправо)" % (title or blk.name, blk.terrain, blk.name, C, L), fill=(0, 0, 0), font=fnt)
    for i, z in enumerate(lvls):
        ox, oy = 8 + i * W + 16, 36
        d.text((ox, oy - 14), "z=%d" % (z + org[2]), fill=(0, 0, 0), font=fnt)
        for x in range(0, blk.sx, 2):
            d.text((ox + x * T + 4, oy + blk.sy * T + 2), str(x + org[0]), fill=(120, 120, 120), font=fnt)
        for y in range(0, blk.sy, 2):
            d.text((ox - 14, oy + y * T + 4), str(y + org[1]), fill=(120, 120, 120), font=fnt)
        lv = blk.lv[z]
        for (x, y), key in lv["f"].items():
            r = (ox + x * T, oy + y * T, ox + x * T + T - 1, oy + y * T + T - 1)
            if key in removed:
                col = (255, 200, 255)
            elif z == 0:
                col = (215, 215, 210)
            elif key not in sup:
                col = (240, 90, 80) if key in base else (250, 170, 60)
            elif info.get(key, (True,))[0]:
                col = (110, 190, 110)
            else:
                col = (190, 230, 170)
            d.rectangle(r, fill=col, outline=(200, 200, 200))
            if key in mark:
                d.rectangle((r[0] + 1, r[1] + 1, r[2] - 1, r[3] - 1), outline=(0, 170, 230), width=3)
        for k in ("w", "n", "o"):
            for (x, y), key in lv[k].items():
                cls = blk.parts[key]["cls"]
                gone = key not in sup and key not in removed
                if key in removed:
                    col = (220, 0, 220)
                elif gone:
                    col = (220, 20, 20) if key in base else (230, 130, 0)
                elif key in mark:
                    col = (0, 170, 230)
                elif cls == "door":
                    col = (40, 90, 230)
                elif cls in BEARING:
                    col = (20, 20, 20)
                else:
                    col = (150, 150, 150)
                wdt = 4 if cls in BEARING else 2
                px, py = ox + x * T, oy + y * T
                if k == "w":
                    d.line((px, py, px, py + T - 1), fill=col, width=wdt)
                elif k == "n":
                    d.line((px, py, px + T - 1, py), fill=col, width=wdt)
                else:
                    if cls in BEARING:
                        d.rectangle((px + 5, py + 5, px + T - 6, py + T - 6), fill=col)
                    else:
                        d.ellipse((px + 6, py + 6, px + T - 7, py + T - 7), outline=col, width=2)
                if key in removed:
                    d.line((px + 2, py + 2, px + T - 3, py + T - 3), fill=col, width=2)
                    d.line((px + T - 3, py + 2, px + 2, py + T - 3), fill=col, width=2)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


def cmd_sheet(args):
    n = 0
    for tname, kind, t, bname, blk, err, cache in all_blocks(args, args.block, args.terrain):
        if blk is None:
            print("  %s %s: %s" % (tname, bname, err))
            continue
        p = os.path.join(args.out, "sheets", "%s__%s.png" % (tname, bname))
        rm = select(blk, args.remove) if args.remove else frozenset()
        sheet(blk, p, removed=rm, C=MAIN_PRESET[0], L=MAIN_PRESET[1])
        n += 1
        print("  " + p)
        if n >= args.limit:
            break


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("scan", "sheet", "damage", "why"))
    ap.add_argument("--install", default=os.path.join("Пиратки", "Dioxine_XPiratez"))
    ap.add_argument("--mod", default="Piratez")
    ap.add_argument("--master", default="xcom1")
    ap.add_argument("--out", default=os.path.join("census", "collapse"))
    ap.add_argument("--block", default="")
    ap.add_argument("--terrain", default="")
    ap.add_argument("--remove", default="", help="области через пробел, kind:x:y:z")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--sheets", action="store_true", help="damage: листы ручных сценариев")
    ap.add_argument("--with-craft", action="store_true", help="damage: и корабли с НЛО")
    ap.add_argument("--ids", default="E02,E04,E07,E09,E17", help="why: сценарии expect.tsv")
    args = ap.parse_args()
    {"scan": cmd_scan, "sheet": cmd_sheet, "damage": cmd_damage, "why": cmd_why}[args.cmd](args)


if __name__ == "__main__":
    main()
