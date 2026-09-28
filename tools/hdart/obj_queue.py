#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Очередь предметов по популярности: все предметы всех карт Пираток, от самого частого к редкому,
партиями по 100 на проверку Vitali (28.09: «найти все предметы по популярности, по 100 на проверку,
есть ок - пушим»).

Предмет - кадр записи MCD в четвёртой позиции клетки (part 3), который стоит на картах. Одна вещь -
одна строка:
  * составной (лестница, дерево на несколько клеток) - все куски одной строкой (obj_series.composites);
  * анимация - все кадры записи одной строкой, одно описание и одно зерно (R-071);
  * копии одной картинки в разных наборах - одна строка, файл потом кладётся на все копии (R-049);
  * точное зеркало более частой строки - выводится поворотом (R-051), своего заказа нет;
  * кандидат в перекраску (та же форма, другие цвета) - выводится из более частой строки подгонкой
    тона к своему оригиналу; это кандидат, а не доказательство: решает лист партии;
  * массив (скала, живая изгородь: стоит вплотную к своим копиям) - не предмет, а поле; рисуется
    способом полов, в очереди предметов его нет, он в massive.tsv.
Популярность - число мест на всех блоках карт всех террейнов. Как часто игра выбирает сам блок
в миссии, перепись не знает: это оговорка, а не учтено.

Пишет в --out (art/objects/queue), всё UTF-8 со спецификацией:
  queue.tsv   - строка на предмет: место, партия, вид, мест, клеток, блоков, ключи, пример на карте,
                подсказка, что уже есть (strict / фото / в игре), из чего выводится;
  items.json  - то же для следующих шагов (лист опознания, задания obj_photo: map и at как там);
  massive.tsv - массивы;
  summary.txt - итоги и охват по партиям.

    py -3.13 tools/hdart/obj_queue.py
"""
import argparse
import glob
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
from PIL import Image                               # noqa: E402

import map_mockup as mm                             # noqa: E402
import map_paint as mp_                             # noqa: E402
import obj_series as osr                            # noqa: E402

ENC = "utf-8-sig"
GAME_HD = "Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN"
STRICT = ["art/objects/series"]
PHOTO = ["art/objects/photo", "art/objects/photo_cap2", "art/objects/photo_mansion"]
TOUCH = ((16, 8), (-16, 8))


def phash(im):
    return hashlib.md5(np.asarray(im.convert("RGBA")).tobytes()).hexdigest()[:16]


def recolor_key(im):
    """Форма и раскладка цветов без самих цветов: цвета нумеруются по первому появлению (как в переписи)."""
    a = np.asarray(im.convert("RGBA"))
    flat = a.reshape(-1, 4)
    _u, first, inv = np.unique(flat, axis=0, return_index=True, return_inverse=True)
    rank = np.argsort(np.argsort(first))
    norm = rank[inv.ravel()].astype(np.int32)
    norm[flat[:, 3] == 0] = -1
    return hashlib.md5(norm.tobytes()).hexdigest()[:16]


def kstr(k):
    return "%s:%d" % k


def scan(world, pairs):
    """Один проход по всем блокам: места, блоки, пример на карте, анимации, массивы."""
    places, massn = Counter(), Counter()
    blocks, where, best, anim, spr = defaultdict(set), {}, {}, {}, {}
    t0 = time.time()
    for i, (tr, b) in enumerate(pairs):
        if i and i % 1000 == 0:
            print("  блоков %d из %d, %.0f с" % (i, len(pairs), time.time() - t0), flush=True)
        try:
            _im, _o, inst = mp_.layout(world, tr, b)
        except Exception:                                   # noqa: BLE001
            continue
        pos, raw = defaultdict(set), defaultdict(list)
        for d in inst:
            if d["part"] != 3:
                continue
            key = (d["set"], d["frame"])
            pos[key].add((d["x"], d["y"] + d["p_level"], d["z"]))
            raw[key].append((d["x"], d["y"], d["z"]))
            spr.setdefault(key, d["spr"])
            if len(set(d["frames"])) > 1:
                anim[key] = tuple(d["frames"])
        for key, ps in pos.items():
            n = len(raw[key])
            places[key] += n
            blocks[key].add((tr, b))
            if n > best.get(key, 0):
                best[key] = n
                where[key] = (tr, b, raw[key][0])
            touch = sum(1 for (x, y, z) in ps for dx, dy in TOUCH if (x + dx, y + dy, z) in ps)
            if touch >= 3:
                massn[key] += n
    return places, massn, blocks, where, anim, spr


def comp_at(world, comp, anchor_where):
    """Места кусков составного в блоке-примере якоря - в координатах layout, как at у obj_photo."""
    tr, b, (x, y, z) = anchor_where
    _im, _o, inst = mp_.layout(world, tr, b)
    by = {}
    for d in inst:
        if d["part"] == 3:
            by.setdefault((d["x"], d["y"] + d["p_level"], d["z"]), []).append(d)
    first = comp["members"][0][0]
    a = next((d for d in by.get((x, y + comp["pl"][first], z), ()) if (d["set"], d["frame"]) == first), None)
    if a is None:
        return None
    ax, ay, az = a["x"], a["y"] + a["p_level"], a["z"]
    out = []
    for key, (dx, dy, dz) in comp["members"]:
        d = next((d for d in by.get((ax + dx, ay + dy, az + dz), ()) if (d["set"], d["frame"]) == key), None)
        if d is None:
            return None
        out.append([d["x"], d["y"], d["z"]])
    return out


def load_hints():
    hints = {}
    for p in sorted(glob.glob("art/maps/paint/hints_*.json")) + ["art/objects/composite_hints.json"]:
        with open(p, encoding=ENC) as f:
            for k, v in json.load(f).items():
                if ":" in k and isinstance(v, str):
                    hints[k.upper()] = v
    for p in glob.glob("art/objects/photo_jobs*.json"):
        with open(p, encoding=ENC) as f:
            for j in json.load(f):
                for t in j.get("take", []) + [j.get("anim", "")]:
                    s = t.split("@")[0]
                    if ":" in s:
                        name, fr = s.split(":", 1)
                        for f_ in fr.split(","):
                            hints["%s:%s" % (name.upper(), f_)] = "[фото] " + j["what"]
    return hints


def md5f(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def done_of(keys):
    """Что уже есть по ключам предмета: strict, фото, в игре (тот же файл в моде, который читает игра)."""
    st, ph, game = 0, 0, 0
    for s, fr in keys:
        rel = os.path.join(s + ".PCK", "%d.png" % fr)
        mine = [os.path.join(r, rel) for r in STRICT + PHOTO if os.path.exists(os.path.join(r, rel))]
        st += any(os.path.exists(os.path.join(r, rel)) for r in STRICT)
        ph += any(os.path.exists(os.path.join(r, rel)) for r in PHOTO)
        g = os.path.join(GAME_HD, rel)
        if mine and os.path.exists(g):
            gm = md5f(g)
            game += any(md5f(m) == gm for m in mine)
    parts = []
    for name, n in (("strict", st), ("фото", ph), ("в игре", game)):
        if n:
            parts.append("%s %d/%d" % (name, n, len(keys)))
    return ", ".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="art/objects/queue")
    ap.add_argument("--batch", type=int, default=100)
    ap.add_argument("--limit", type=int, default=0, help="только первые N блоков - для проверки скрипта")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    world = mm.World()
    pairs = [(tr, b) for tr in world.terrains for b in world.blocks_of(tr)]
    if a.limit:
        pairs = pairs[:a.limit]
    print("блоков карт %d (террейн + блок), проход 1 из 2" % len(pairs), flush=True)
    places, massn, blocks, where, anim, spr = scan(world, pairs)
    mass = {k for k in places if massn[k] * 2 > places[k]}
    print("предметов-кадров %d, из них массивов %d, анимаций %d; проход 2 из 2 - составные"
          % (len(places), len(mass), len(set(anim) - mass)), flush=True)
    comps = osr.composites(world, pairs, mass)

    items, comp_of = {}, set()

    def add(sig, kind, keys, n, extra):
        it = items.get(sig)
        if it is None:
            it = items[sig] = dict(kind=kind, keys=[], places=0, cells=0, blocks=set(), src=None, **extra)
        it["keys"] += [k for k in keys if k not in it["keys"]]
        it["places"] += n
        it["cells"] += sum(places[k] for k in keys)
        for k in keys:
            it["blocks"] |= blocks[k]
        # пример на карте - у копии, что стоит чаще; составной берёт куски этой же копии
        if it["src"] is None or n > it["src"][0]:
            it["src"] = (n, keys)
            it.update(extra)

    for c in comps:
        keys = [k for k, _o in c["members"]]
        sig = "C" + hashlib.md5("|".join(phash(c["spr"][k]) + str(o) for k, o in c["members"])
                                .encode()).hexdigest()[:16]
        add(sig, "составной", keys, min(places[k] for k in keys), {"comp": c})
        comp_of |= set(keys)
    for key in places:
        if key in comp_of or key in mass:
            continue
        if key in anim:
            sprs = [world.sprite(key[0], f, None) for f in anim[key]]
            sig = "A" + hashlib.md5("|".join(phash(s) if s else "-" for s in sprs).encode()).hexdigest()[:16]
            add(sig, "анимация", [key], places[key], {"frames": sorted(set(anim[key]))})
        else:
            add("S" + phash(spr[key]), "один", [key], places[key],
                {"mirror": "S" + phash(spr[key].transpose(Image.FLIP_LEFT_RIGHT)),
                 "recolor": recolor_key(spr[key])})

    order = sorted(items.items(), key=lambda kv: (-kv[1]["places"], -kv[1]["cells"], kv[0]))
    rank, by_mirror, by_recolor, n_draw = {}, {}, {}, 0
    for sig, it in order:
        parent = None
        if it["kind"] == "один":
            if it["mirror"] != sig and it["mirror"] in rank:
                parent, it["derive"] = it["mirror"], "зеркало"
            elif it["recolor"] in by_recolor:
                parent, it["derive"] = by_recolor[it["recolor"]], "перекраска?"
        if parent:
            it["parent"] = parent
            it["batch"] = items[parent]["batch"]
        else:
            it["batch"] = n_draw // a.batch + 1
            n_draw += 1
        rank[sig] = len(rank) + 1
        if it["kind"] == "один":
            by_recolor.setdefault(it["recolor"], sig)
    hints = load_hints()

    total_cells = sum(places[k] for k in places if k not in mass)
    rows, jitems, cover = [], [], Counter()
    for sig, it in order:
        keys = it["keys"]
        anchor = it["src"][1][0]
        tr, b, xyz = where[anchor]
        at = [list(xyz)]
        if it["kind"] == "составной":
            at = comp_at(world, it["comp"], where[anchor]) or at
        hint = next((hints[kstr(k)] for k in keys if kstr(k) in hints), "")
        frames = keys
        if it["kind"] == "анимация":
            frames = [(anchor[0], f) for f in it["frames"]]
        par = it.get("parent")
        cover[it["batch"]] += it["cells"]
        rows.append([rank[sig], it["batch"], it["kind"], it["places"], it["cells"], len(it["blocks"]),
                     " ".join(kstr(k) for k in keys), "%s/%s @%s" % (tr, b, ",".join(map(str, at[0]))),
                     ("%s из %d" % (it["derive"], rank[par])) if par else "", done_of(frames), hint])
        jitems.append({"rank": rank[sig], "batch": it["batch"], "kind": it["kind"], "sig": sig,
                       "places": it["places"], "cells": it["cells"], "blocks": len(it["blocks"]),
                       "keys": [kstr(k) for k in keys], "frames": [kstr(k) for k in frames],
                       "src": [kstr(k) for k in it["src"][1]],
                       "map": "%s/%s" % (tr, b), "at": at, "hint": hint,
                       "derive": it.get("derive", ""), "parent": rank[par] if par else 0})

    with open(os.path.join(a.out, "queue.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("\t".join(["место", "партия", "вид", "мест", "клеток", "блоков", "ключи", "пример",
                           "выводится", "есть", "подсказка"]) + "\n")
        for r in rows:
            f.write("\t".join(str(v).replace("\t", " ") for v in r) + "\n")
    with open(os.path.join(a.out, "items.json"), "w", encoding=ENC) as f:
        json.dump(jitems, f, ensure_ascii=False, indent=0)
    with open(os.path.join(a.out, "massive.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("ключ\tмест\tиз них вплотную\n")
        for k in sorted(mass, key=lambda k: -places[k]):
            f.write("%s\t%d\t%d\n" % (kstr(k), places[k], massn[k]))

    kinds = Counter(it["kind"] for _s, it in order)
    der = Counter(it.get("derive", "") for _s, it in order)
    n_batches = max(it["batch"] for _s, it in order) if order else 0
    lines = ["Очередь предметов, %s" % time.strftime("%Y-%m-%d %H:%M"),
             "блоков карт (террейн + блок): %d" % len(pairs),
             "кадров-предметов на картах: %d, массивов (способ полов): %d" % (len(places), len(mass)),
             "предметов (строк очереди): %d - один %d, составной %d, анимация %d"
             % (len(order), kinds["один"], kinds["составной"], kinds["анимация"]),
             "выводятся без заказа: зеркало %d, перекраска-кандидат %d" % (der["зеркало"], der["перекраска?"]),
             "заказов модели: %d, партий по %d: %d" % (n_draw, a.batch, n_batches),
             "мест предметов на картах (без массивов): %d" % total_cells, "",
             "партия\tохват мест, %\tнакопленный, %"]
    acc = 0
    for bn in range(1, n_batches + 1):
        acc += cover[bn]
        if bn <= 20 or bn % 10 == 0 or bn == n_batches:
            lines.append("%d\t%.1f\t%.1f" % (bn, 100.0 * cover[bn] / max(1, total_cells),
                                             100.0 * acc / max(1, total_cells)))
    with open(os.path.join(a.out, "summary.txt"), "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
