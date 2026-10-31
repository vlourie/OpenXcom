# -*- coding: utf-8 -*-
"""Подсчёт: сколько кадров террейна понадобится при повороте карты боя на 4 стороны.

Кадр получает роль по тому, в какой ЧАСТИ клетки .MAP стоит запись MCD, которая его рисует
(пол / стена З / стена С / объект), плюс записи, достижимые по die/alt (разрушенные, открытые).
Справка и разбор чисел: docs/research/map-rotation-2026-10-20.md.

    py -3.13 tools\rotation_census.py census\rotation\rotation_counts.json
"""
import os, sys, json
from collections import defaultdict, Counter

ROOT = r"E:\OpenXCom"
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "hdart"))
import pck_census as pc   # noqa
import xcom_sprites as xs  # noqa

SLOT = {0: "floor", 1: "west", 2: "north", 3: "object"}


def collect(rul_dir):
    terrains = {}
    for dp, _d, names in os.walk(rul_dir):
        for name in sorted(names):
            if not name.lower().endswith(".rul"):
                continue
            try:
                doc = pc.load_yaml(os.path.join(dp, name))
            except Exception:
                continue
            if not isinstance(doc, dict):
                continue
            found = list(doc.get("terrains") or [])
            for sec in ("crafts", "ufos"):
                for it in doc.get(sec) or []:
                    if isinstance(it, dict) and isinstance(it.get("battlescapeTerrainData"), dict):
                        found.append(it["battlescapeTerrainData"])
            for t in found:
                if isinstance(t, dict) and t.get("name") and t.get("mapDataSets") and t.get("mapBlocks"):
                    terrains[t["name"]] = t
    return terrains


def mcd_full(files, s, cache):
    if s in cache:
        return cache[s]
    p = files.find(os.path.join("TERRAIN", s + ".MCD"))
    recs = []
    if p:
        d = open(p, "rb").read()
        for i in range(0, len(d) - 61, 62):
            r = d[i:i + 62]
            recs.append({"frames": list(r[0:8]), "ufo_door": r[30], "big_wall": r[33], "door": r[35],
                         "die": r[44], "alt": r[46], "tlevel": (r[48] - 256 if r[48] > 127 else r[48]),
                         "plevel": r[49], "type": r[53]})
    cache[s] = recs
    return recs


def diamond_outside(frame, w, h):
    """Доля пикселей кадра 32x40 вне ромба пола (ромб: строки 24..39 при k=1)."""
    tot = out = 0
    for y in range(h):
        row = frame[y]
        for x in range(w):
            if not row[x]:
                continue
            tot += 1
            # ромб с центром (15.5, 31.5), полуширина 16, полувысота 8, допуск 1 px
            if abs(x - 15.5) / 16.0 + abs(y - 31.5) / 8.0 > 1.0 + 1.0 / 8.0:
                out += 1
    return out / tot if tot else 0.0


def run(game, roots, rul_dir, hd_dir):
    files = pc.Files(roots)
    terrains = collect(rul_dir)
    cache = {}
    sizes = {}
    used = defaultdict(Counter)    # (set, rec) -> Counter(slot -> мест)
    for tname, t in terrains.items():
        sets = list(t["mapDataSets"])
        for s in sets:
            sizes.setdefault(s, len(mcd_full(files, s, cache)))
        for b in t["mapBlocks"]:
            bn = b.get("name") if isinstance(b, dict) else None
            if not bn:
                continue
            mp = files.find(os.path.join("MAPS", bn + ".MAP"))
            if not mp:
                continue
            try:
                cells = pc.read_map(mp)
            except Exception:
                continue
            for c in cells:
                for part in range(4):
                    v = c[part]
                    if not v:
                        continue
                    s, rec = pc.resolve(v, sets, sizes)
                    if s is not None:
                        used[(s, rec)][part] += 1
    # замыкание по die / alt: разрушенный и «другой» вид стоит в той же части клетки
    reach = {k: set(v) for k, v in used.items()}
    places = {k: sum(v.values()) for k, v in used.items()}
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
                if reach[k] != before:
                    stack.append(k)
    # кадры
    frame_role = defaultdict(set)      # (set, fr) -> {slot}
    frame_bw = defaultdict(set)
    frame_places = Counter()
    frame_anim = set()
    frame_raised = set()
    for (s, rec), slots in reach.items():
        r = cache[s][rec]
        fr = set(r["frames"])
        for f in fr:
            frame_role[(s, f)] |= slots
            frame_bw[(s, f)].add(r["big_wall"])
            frame_places[(s, f)] += places.get((s, rec), 0)
            if len(fr) > 1:
                frame_anim.add((s, f))
            if r["tlevel"] != 0 or r["plevel"] != 0:
                frame_raised.add((s, f))
    # PCK
    pics = {}
    for s in sorted({k[0] for k in frame_role}):
        frames, size = pc.read_set(files, os.path.join("TERRAIN", s + ".PCK"))
        if frames is None:
            continue
        w, h = size
        hd_have = set()
        hdp = os.path.join(hd_dir, "TERRAIN", s.upper() + ".PCK")
        if not os.path.isdir(hdp):
            hdp = os.path.join(hd_dir, "TERRAIN", s + ".PCK")
        if os.path.isdir(hdp):
            for fn in os.listdir(hdp):
                b = fn.split(".")[0]
                if b.isdigit() and fn.lower().endswith(".png") and fn.count(".") == 1:
                    hd_have.add(int(b))
        for (ss, f) in [k for k in frame_role if k[0] == s]:
            if f >= len(frames) or frames[f] is None:
                continue
            fp = pc.fingerprints(frames[f])
            if fp["pixels"] == 0:
                continue
            pics[(s, f)] = {"exact": fp["exact"], "mirror": fp["mirror"], "recolor": fp["recolor"],
                            "hd": f in hd_have,
                            "outside": diamond_outside(frames[f], w, h) if (w, h) == (32, 40) else 1.0}
    # классы
    def klass(k):
        roles = frame_role[k]
        if roles == {0}:
            return "floor"
        if roles <= {1, 2}:
            return "wall"
        if roles == {3}:
            return "bw1" if frame_bw[k] == {1} else ("bwdiag" if frame_bw[k] & {2, 3} else
                                                    ("bwedge" if frame_bw[k] - {0} else "object"))
        return "mixed"
    res = {}
    by_class = defaultdict(list)
    for k, p in pics.items():
        by_class[klass(k)].append(k)
    for c, ks in sorted(by_class.items()):
        uniq = {}
        for k in ks:
            uniq.setdefault(pics[k]["exact"], []).append(k)
        rec_u = {pics[k]["recolor"] for k in ks}
        d = {"кадров": len(ks), "разных_побайтно": len(uniq), "разных_по_раскраске": len(rec_u),
             "мест": sum(frame_places[k] for k in ks),
             "с_hd_кадров": sum(1 for k in ks if pics[k]["hd"]),
             "анимац_кадров": sum(1 for k in ks if k in frame_anim)}
        if c == "floor":
            flat = [h for h, kk in uniq.items()
                    if all(pics[x]["outside"] <= 0.03 and x not in frame_raised for x in kk)]
            d["плоских_разных"] = len(flat)
            d["с_рельефом_разных"] = len(uniq) - len(flat)
            d["мест_плоских"] = sum(frame_places[x] for h in flat for x in uniq[h])
        if c == "wall":
            d["W_только"] = sum(1 for k in ks if frame_role[k] == {1})
            d["N_только"] = sum(1 for k in ks if frame_role[k] == {2})
            d["и_W_и_N"] = sum(1 for k in ks if frame_role[k] == {1, 2})
        # самосимметричные (кадр = своё зеркало)
        d["самозеркальных_разных"] = sum(1 for h, kk in uniq.items() if pics[kk[0]]["mirror"] == h)
        res[c] = d
    # итог без двойного учёта: картинка (побайтно) -> самый требовательный класс
    trees = set()
    tp = os.path.join(ROOT, "census", "trees", "trees.tsv")
    if game == "piratez" and os.path.exists(tp):
        for i, line in enumerate(open(tp, encoding="utf-8-sig")):
            if i:
                c = line.split("\t")
                trees.add((c[0], int(c[1])))
    RANK = {"flat": 0, "wall": 1, "relief": 2, "object": 3}
    pic_need = {}
    pic_tree = defaultdict(lambda: True)
    pic_recolor = {}
    for k, p in pics.items():
        c = klass(k)
        if c == "floor":
            need = "flat" if (p["outside"] <= 0.03 and k not in frame_raised) else "relief"
        elif c == "wall":
            need = "wall"
        else:
            need = "object"
        h = p["exact"]
        if h not in pic_need or RANK[need] > RANK[pic_need[h]]:
            pic_need[h] = need
        pic_tree[h] = pic_tree[h] and (k in trees)
        pic_recolor[h] = p["recolor"]
    cnt = Counter(pic_need.values())
    trees_obj = sum(1 for h, n in pic_need.items() if n == "object" and pic_tree[h])
    rec_need = {}
    for h, n in pic_need.items():
        r = pic_recolor[h]
        if r not in rec_need or RANK[n] > RANK[rec_need[r]]:
            rec_need[r] = n
    rcnt = Counter(rec_need.values())
    res["ИТОГ"] = {"картинок": len(pic_need), "плоский_пол": cnt["flat"], "пол_с_рельефом": cnt["relief"],
                   "стены": cnt["wall"], "объекты": cnt["object"], "из_объектов_растения": trees_obj,
                   "по_раскраске": dict(rcnt), "по_раскраске_всего": len(rec_need)}
    allu = {p["exact"] for p in pics.values()}
    res["ВСЕГО"] = {"кадров": len(pics), "разных_побайтно": len(allu),
                    "наборов": len({k[0] for k in pics}), "террейнов": len(terrains),
                    "записей_MCD_на_картах": len(used), "записей_с_die_alt": len(reach)}
    return res


if __name__ == "__main__":
    PZ = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez")
    out = {}
    out["piratez"] = run("piratez",
                         [os.path.join(PZ, "user", "mods", "Piratez"), os.path.join(PZ, "standard", "xcom1"),
                          os.path.join(PZ, "UFO")],
                         os.path.join(PZ, "user", "mods", "Piratez", "Ruleset"),
                         os.path.join(PZ, "user", "mods", "hd", "hd"))
    out["ufo"] = run("ufo", [os.path.join(ROOT, "bin", "standard", "xcom1"), os.path.join(ROOT, "bin", "UFO")],
                     os.path.join(ROOT, "bin", "standard", "xcom1"),
                     os.path.join(ROOT, "user", "mods", "hd", "hd"))
    js = json.dumps(out, ensure_ascii=False, indent=1)
    open(sys.argv[1], "w", encoding="utf-8-sig").write(js)
    print("ok")
