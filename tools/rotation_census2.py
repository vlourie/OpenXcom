# -*- coding: utf-8 -*-
"""Поворот карты на 4 стороны, второй подсчёт: что из нового вида уже есть в данных.

Стены. Где стоит каждая запись стены, известно из .MAP: перед ней клетка, видимая камерой, за ней
соседняя. Есть ли над клеткой пол верхнего этажа (крыша), тоже известно. Отсюда роль стены:
  ОДНА СРЕДА  — по обе стороны улица или по обе стороны помещение: забор, перегородка, скала;
                обратная сторона = та же грань (зеркало + сдвиг столбцов), рисовать нечего;
  ИЗНУТРИ     — камера видит грань помещения, за стеной улица: нужна наружная грань;
  СНАРУЖИ     — камера видит наружную грань, за стеной помещение: нужна внутренняя грань.
Для ИЗНУТРИ ищется в том же наборе и той же части (west/north) запись роли СНАРУЖИ с тем же силуэтом
(и наоборот) — это та же стена другой стороной, её кадр и есть нужная грань.

Объекты. Растения и сплошные кубы (BigWall 1) со всех сторон одинаковы; предмет у стены (класс
NEAR_WALL_ITEM переписи стен) с двух дальних сторон закрыт своей стеной — нужен один вид сбоку;
кадр, симметричный зеркально по силуэту и рисунку, — кандидат «одинаков со всех сторон».

    py -3.13 tools\\rotation_census2.py census\\rotation\\rotation_counts2.json
Справка: docs/research/map-rotation-2026-10-20.md.
"""
import os, sys, json
from collections import defaultdict, Counter

ROOT = r"E:\OpenXCom"
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "hdart"))
import pck_census as pc        # noqa
import rotation_census as rc   # noqa


def read_map3(path):
    d = open(path, "rb").read()
    if len(d) < 3:
        return None
    sy, sx, sz = d[0], d[1], d[2]
    body = d[3:]
    cells = {}
    i = 0
    for z in range(sz - 1, -1, -1):
        for y in range(sy):
            for x in range(sx):
                if i + 4 > len(body):
                    return sx, sy, sz, cells
                cells[(x, y, z)] = body[i:i + 4]
                i += 4
    return sx, sy, sz, cells


def mask_of(frame):
    return [[1 if v else 0 for v in row] for row in frame]


def iou(a, b):
    inter = uni = 0
    for ra, rb in zip(a, b):
        for va, vb in zip(ra, rb):
            if va or vb:
                uni += 1
                if va and vb:
                    inter += 1
    return inter / uni if uni else 0.0


def mirror_sym(frame):
    """(IoU силуэта с зеркалом, доля совпавших индексов на объединении)."""
    inter = uni = same = 0
    for row in frame:
        rr = row[::-1]
        for a, b in zip(row, rr):
            if a or b:
                uni += 1
                if a and b:
                    inter += 1
                    if a == b:
                        same += 1
    return (inter / uni if uni else 0.0), (same / uni if uni else 0.0)


def floor_height(frame, h):
    """Сколько пикселей кадр поднимается над верхним углом ромба пола (строка h-16)."""
    top = next((y for y in range(h) if any(frame[y])), h)
    return max(0, (h - 16) - top)


def load_classes():
    p = os.path.join(ROOT, "census", "walls", "wall_classes.tsv")
    out = {}
    if os.path.exists(p):
        for i, line in enumerate(open(p, encoding="utf-8-sig")):
            if i:
                c = line.rstrip("\n").split("\t")
                out[c[0]] = (c[3], c[4])
    return out


def run(game, roots, rul_dir, trees):
    files = pc.Files(roots)
    terrains = rc.collect(rul_dir)
    cache, sizes = {}, {}
    used = defaultdict(Counter)          # (set, rec) -> части
    role = defaultdict(Counter)          # (set, rec, part) -> роль
    for t in terrains.values():
        sets = list(t["mapDataSets"])
        for s in sets:
            sizes.setdefault(s, len(rc.mcd_full(files, s, cache)))
        for b in t["mapBlocks"]:
            bn = b.get("name") if isinstance(b, dict) else None
            mp = files.find(os.path.join("MAPS", bn + ".MAP")) if bn else None
            if not mp:
                continue
            m = read_map3(mp)
            if not m:
                continue
            sx, sy, sz, cells = m
            covered = {}
            for (x, y, z) in cells:
                covered[(x, y, z)] = any(cells.get((x, y, zz), b"\0")[0] for zz in range(z + 1, sz))
            for (x, y, z), c in cells.items():
                for part in range(4):
                    v = c[part]
                    if not v:
                        continue
                    s, rec = pc.resolve(v, sets, sizes)
                    if s is None:
                        continue
                    used[(s, rec)][part] += 1
                    if part in (1, 2):
                        back = (x - 1, y, z) if part == 1 else (x, y - 1, z)
                        if back not in cells:
                            continue           # край блока: за стеной чужой блок
                        f, bk = covered[(x, y, z)], covered[back]
                        r = "одна" if f == bk else ("изнутри" if f else "снаружи")
                        role[(s, rec, part)][r] += 1
    # die/alt наследуют часть и роль
    reach = {k: set(v) for k, v in used.items()}
    rroles = {k: Counter(v) for k, v in role.items()}
    stack = list(reach)
    while stack:
        s, rec = stack.pop()
        recs = cache.get(s) or []
        if rec >= len(recs):
            continue
        for nxt in (recs[rec]["die"], recs[rec]["alt"]):
            if nxt and nxt < len(recs):
                k = (s, nxt)
                before = set(reach.get(k, set()))
                reach.setdefault(k, set()).update(reach[(s, rec)])
                for part in (1, 2):
                    if (s, rec, part) in rroles and (s, nxt, part) not in rroles:
                        rroles[(s, nxt, part)] = Counter(rroles[(s, rec, part)])
                if reach[k] != before:
                    stack.append(k)
    classes = load_classes()
    # кадры
    frames_of = {}
    for s in sorted({k[0] for k in reach}):
        fr, size = pc.read_set(files, os.path.join("TERRAIN", s + ".PCK"))
        if fr is not None:
            frames_of[s] = (fr, size)
    pics = {}       # exact -> сведения
    def pic(s, f):
        fr, (w, h) = frames_of[s]
        if f >= len(fr) or fr[f] is None:
            return None
        fp = pc.fingerprints(fr[f])
        if fp["pixels"] == 0:
            return None
        return fp, fr[f], w, h
    # ---- записи -> требование на картинку
    need = {}       # exact -> (ранг, вид)
    RANK = {"пол": 0, "стена_одна": 1, "стена_пара": 2, "стена_без_пары": 3, "стена_декор": 3,
            "объект_симм": 4, "объект_у_стены": 5, "объект": 6}
    wall_rec_dom = {}
    for (s, rec), parts in reach.items():
        if s not in frames_of:
            continue
        for part in (1, 2):
            if part in parts:
                rr = rroles.get((s, rec, part), Counter())
                wall_rec_dom[(s, rec, part)] = rr.most_common(1)[0][0] if rr else "одна"
    # силуэты стен по набору/части/роли для поиска пары
    sil = defaultdict(list)     # (s, part, роль) -> [(rec, mask)]
    for (s, rec, part), dom in wall_rec_dom.items():
        r = cache[s][rec]
        p = pic(s, r["frames"][0])
        if p:
            sil[(s, part, dom)].append((rec, mask_of(p[1])))
    # близнец: та же стена в другом развороте (west <-> north) в том же наборе = зеркальный силуэт
    by_part = defaultdict(list)
    for (s, part, _dom), lst in sil.items():
        by_part[(s, part)].extend(m for (_r, m) in lst)
    twin_rec = {}
    for (s, part, _dom), lst in sil.items():
        other = by_part.get((s, 3 - part), [])
        for rec, m in lst:
            mm = [row[::-1] for row in m]
            twin_rec[(s, rec, part)] = any(iou(mm, o) >= 0.9 for o in other)
    twins = {}
    stat = Counter()
    rows = []
    for (s, rec), parts in reach.items():
        if s not in frames_of:
            continue
        r = cache[s][rec]
        key = "%s:%d" % (s, rec)
        cls = classes.get(key, ("", ""))
        for part in sorted(parts):
            if part == 0:
                kind = "пол"
            elif part in (1, 2):
                dom = wall_rec_dom[(s, rec, part)]
                if "декор" in cls[1]:
                    kind = "стена_декор"
                elif dom == "одна":
                    kind = "стена_одна"
                else:
                    want = "снаружи" if dom == "изнутри" else "изнутри"
                    p0 = pic(s, r["frames"][0])
                    ok = False
                    if p0:
                        m0 = mask_of(p0[1])
                        ok = any(iou(m0, m) >= 0.9 for (_rr, m) in sil.get((s, part, want), []))
                    kind = "стена_пара" if ok else "стена_без_пары"
            else:
                kind = None
            for f in set(r["frames"]):
                p = pic(s, f)
                if not p:
                    continue
                fp, frame, w, h = p
                k = kind
                if k is None:
                    ms, ps = mirror_sym(frame)
                    solid = r["big_wall"] == 1 and not (cls[0] == "BW1" and
                                                         cls[1] in ("предмет_кандидат", "многоклеточная_кандидат"))
                    if (s, f) in trees or solid:
                        k = "объект_симм"
                    elif cls[0] == "NEAR_WALL_ITEM":
                        k = "объект_у_стены"
                    elif ms >= 0.9 and ps >= 0.6:
                        k = "объект_симм"
                    else:
                        k = "объект"
                ex = fp["exact"]
                sub = ""
                if k == "пол":
                    sub = "плоский" if floor_height(frame, h) <= 2 and r["tlevel"] == 0 else \
                          ("низкий" if floor_height(frame, h) <= 6 else "высокий")
                if k == "объект_симм":
                    sub = "растение" if (s, f) in trees else ("куб" if r["big_wall"] == 1 else "зеркальный")
                if kind and kind.startswith("стена"):
                    twins[ex] = twins.get(ex, False) or twin_rec.get((s, rec, part), False)
                prev = need.get(ex)
                if prev is None or RANK[k] > RANK[prev[0]]:
                    need[ex] = (k, sub)
    cnt = Counter(v[0] for v in need.values())
    sub = Counter("%s/%s" % v for v in need.values() if v[1])
    tw = Counter("%s/%s" % (v[0], "близнец" if twins.get(ex) else "без_близнеца")
                 for ex, v in need.items() if v[0].startswith("стена"))
    return {"картинок": len(need), "по_виду": dict(cnt), "подробно": dict(sub), "стены_близнец": dict(tw),
            "роли_записей_стен": dict(Counter(wall_rec_dom.values()))}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    PZ = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez")
    trees = set()
    tp = os.path.join(ROOT, "census", "trees", "trees.tsv")
    for i, line in enumerate(open(tp, encoding="utf-8-sig")):
        if i:
            c = line.split("\t")
            trees.add((c[0], int(c[1])))
    out = {"piratez": run("piratez",
                          [os.path.join(PZ, "user", "mods", "Piratez"), os.path.join(PZ, "standard", "xcom1"),
                           os.path.join(PZ, "UFO")],
                          os.path.join(PZ, "user", "mods", "Piratez", "Ruleset"), trees),
           "ufo": run("ufo", [os.path.join(ROOT, "bin", "standard", "xcom1"), os.path.join(ROOT, "bin", "UFO")],
                      os.path.join(ROOT, "bin", "standard", "xcom1"), set())}
    js = json.dumps(out, ensure_ascii=False, indent=1)
    open(sys.argv[1], "w", encoding="utf-8-sig").write(js)
    print(js)
