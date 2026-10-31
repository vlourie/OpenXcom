#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Серия предметов карт: Qwen-Image-2.1 strict, как одобрено в пробе (DECISIONS 2026-09-27).

Предмет - кадр записи MCD, что стоит на карте в четвёртой позиции клетки (part 3: деревья, мебель,
ящики). Полы и стены (part 0-2) здесь не рисуются: отдельный предмет с соседом не стыкуется.

Порядок карт - docs/MAP_QUEUE.md, потом остальные карты art/maps/paint/series_maps.json; у каждой
карты свои подсказки на кадр (R-007: кадр без подсказки не рисуется, идёт в список). Одна картинка
рисуется один раз на всю серию, даже если стоит в нескольких наборах (R-049) - копии получают тот же
файл. Анимированные записи (кадры записи не все равны) пока не рисуются: кадры одной петли, нарисованные
порознь, мигают (R-071) - список в skipped.tsv.

Составной предмет (лестница на две клетки, купол на четыре, дерево на шесть - composites()) рисуется
целиком, одним заказом, и режется по клеткам (R-005): куски, нарисованные порознь, не сходятся.
Подсказка у него своя, на весь предмет (--comp-hints); без неё составной пропускается. Список всех
найденных с подсказками кусков - composites.tsv.

Одна загрузка модели на весь прогон (R-018). Уже нарисованное в --out пропускается - прогон можно
остановить и продолжить. Каждые --sheet-every кадров - лист сравнения sheet_NNNN.png:
оригинал x4 | прежний пак | новый, на тёмном полу, в размере игры (k=4).

В мод НЕ пишет: кадры лежат в art/objects/series/<НАБОР>.PCK/<кадр>.png до выбора Vitali.

    E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/obj_series.py --dry-run
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw                    # noqa: E402

import map_mockup as mm                             # noqa: E402
import map_paint as mp_                             # noqa: E402
import probe_object as po                           # noqa: E402

ENC = "utf-8-sig"
QUEUE_MD = "docs/MAP_QUEUE.md"
SERIES_MAPS = "art/maps/paint/series_maps.json"
FLOOR = (24, 20, 18)


def map_list(limit):
    """[(терраин, карта, файл подсказок)] в порядке очереди карт, потом остальные из series_maps."""
    with open(SERIES_MAPS, encoding=ENC) as f:
        sm = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    out, seen = [], set()
    with open(QUEUE_MD, encoding=ENC) as f:
        for line in f:
            m = re.match(r"\|\s*(\d+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|", line)
            if not m or int(m.group(1)) > limit:
                continue
            terrain, block = m.group(2), m.group(3)
            cfg = sm.get(block) if (sm.get(block) or {}).get("terrain") == terrain else None
            cfg = cfg or next((v for k, v in sm.items() if k.split("/")[-1] == block
                               and v.get("terrain") == terrain), None)
            out.append((terrain, block, (cfg or {}).get("hints", ""), (cfg or {}).get("field_objects", "")))
            seen.add((terrain, block))
    for block, v in sm.items():
        key = (v.get("terrain"), block.split("/")[-1])
        if key not in seen:
            out.append((key[0], key[1], v.get("hints", ""), v.get("field_objects", "")))
            seen.add(key)
    return out


def load_hints(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding=ENC) as f:
        return {(k.rsplit(":", 1)[0].upper(), int(k.rsplit(":", 1)[1])): v for k, v in json.load(f).items()}


def objects_of(world, terrain, block, field_objects=""):
    """Записи-предметы карты: {(набор, кадр): запись}. Только part 3, без анимации - анимация отдельно.
    Массив (скала, живая изгородь) - предмет, что стоит вплотную к своим копиям: отдельно нарисованный,
    он даёт решётку на стыках (R-039, R-005), ему нужен способ полов."""
    _im, _owner, inst = mp_.layout(world, terrain, block)
    objs, anim, cells = {}, {}, {}
    for d in inst:
        if d["part"] != 3:
            continue
        key = (d["set"], d["frame"])
        cells.setdefault(key, set()).add((d["x"], d["y"] + d["p_level"], d["z"]))
        if len(set(d["frames"])) > 1:
            anim[key] = d
        else:
            objs.setdefault(key, d)
    mass = {tuple([s.rsplit(":", 1)[0].upper(), int(s.rsplit(":", 1)[1])])
            for s in field_objects.split(",") if ":" in s}
    for key, pos in cells.items():
        # соседи по клетке на экране k=1: (+-16, +-8) - соседняя клетка по x или по y
        touch = sum(1 for (x, y, z) in pos for dx, dy in ((16, 8), (-16, 8)) if (x + dx, y + dy, z) in pos)
        if touch >= 3:
            mass.add(key)
    field = {k: objs.pop(k) for k in list(objs) if k in mass}
    return objs, anim, field


def pix_hash(spr):
    return hashlib.md5(spr.tobytes()).hexdigest()


# соседние клетки на экране k=1 в координатах (x, y + p_level, z): по горизонтали и этаж выше/ниже
_FLAT = ((16, 8), (-16, 8), (16, -8), (-16, -8), (32, 0), (-32, 0), (0, 16), (0, -16))
NEAR = [(dx, dy, 0) for dx, dy in _FLAT] + [(dx, dy - 24 * dz, dz) for dz in (-1, 1)
                                             for dx, dy in ((0, 0),) + _FLAT]


def composites(world, map_rows, mass, thr=0.8, near_frames=12):
    """Составной предмет: кадры part 3, что стоят рядом всегда с одним сдвигом - лестница на две клетки,
    купол на четыре, дерево на шесть. Нарисованные порознь, куски не сходятся (R-005): рисуем целиком
    и режем по клеткам. Ребро A-B: B стоит у A со сдвигом o не реже thr мест A и A у B со сдвигом -o
    не реже thr мест B; кроме того вместе хотя бы дважды или один набор с близкими номерами кадров -
    иначе это случайные соседи на единственной карте. Возвращает [{"members": [(ключ, (dx, dy, dz))]
    в порядке рисования, "spr": {ключ: кадр}, "pl": {ключ: p_level}}]."""
    from collections import Counter, defaultdict
    places, pair, together, spr, pl = Counter(), defaultdict(Counter), Counter(), {}, {}
    for terrain, block in map_rows:
        try:
            _im, _o, inst = mp_.layout(world, terrain, block)
        except Exception:                                       # noqa: BLE001
            continue
        at = defaultdict(set)
        for d in inst:
            if d["part"] == 3 and len(set(d["frames"])) == 1:
                key = (d["set"], d["frame"])
                at[(d["x"], d["y"] + d["p_level"], d["z"])].add(key)
                spr.setdefault(key, d["spr"])
                pl.setdefault(key, d["p_level"])
        for (x, y, z), keys in at.items():
            for a in keys:
                places[a] += 1
                seen = set()
                for o in NEAR:
                    for b in at.get((x + o[0], y + o[1], z + o[2]), ()):
                        if b != a and (b, o) not in seen:
                            seen.add((b, o))
                            pair[a][(b, o)] += 1
    edges = defaultdict(dict)
    for a, cnt in pair.items():
        if a in mass:
            continue
        for (b, o), n in cnt.items():
            if b in mass:
                continue
            back = pair[b][(a, tuple(-v for v in o))]
            kin = a[0] == b[0] and abs(a[1] - b[1]) <= near_frames
            if n / places[a] >= thr and back / places[b] >= thr and (min(n, back) >= 2 or kin):
                edges[a][b] = o
    out, seen = [], set()
    for a in sorted(edges):
        if a in seen:
            continue
        pos, stack, bad = {a: (0, 0, 0)}, [a], False
        while stack:
            u = stack.pop()
            for v, o in edges[u].items():
                p = tuple(pu + ov for pu, ov in zip(pos[u], o))
                if v in pos:
                    bad |= pos[v] != p
                else:
                    pos[v] = p
                    stack.append(v)
        seen |= set(pos)
        if bad or len(pos) < 2:
            continue

        def order(item):
            # клетка из экранного сдвига: x-y = dx/16, x+y = (dy + 24 dz)/8; рисуется по z, y, x (layout)
            (_k, (dx, dy, dz)) = item
            s, d = dx / 16, (dy + 24 * dz) / 8
            return (dz, (d - s) / 2, (d + s) / 2)
        out.append({"members": sorted(pos.items(), key=order),
                    "spr": {k: spr[k] for k in pos}, "pl": {k: pl[k] for k in pos}})
    return out


def compose(comp, frames=None, k=1):
    """Куски составного в одну картинку, как их рисует игра. frames = {ключ: кадр размера k} - свой кадр
    вместо оригинала (прежний пак, новый). Возвращает (картинка, {ключ: (x, y) левого верха куска})."""
    at = {key: (dx, dy - comp["pl"][key]) for key, (dx, dy, _dz) in comp["members"]}
    x0 = min(x for x, _y in at.values())
    y0 = min(y for _x, y in at.values())
    at = {key: (x - x0, y - y0) for key, (x, y) in at.items()}
    w = max(x for x, _y in at.values()) + 32
    h = max(y for _x, y in at.values()) + 40
    im = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    for key, _o in comp["members"]:
        f = (frames or {}).get(key)
        if f is None:
            f = comp["spr"][key] if k == 1 else comp["spr"][key].resize((32 * k, 40 * k), Image.NEAREST)
        im.alpha_composite(f.convert("RGBA"), (at[key][0] * k, at[key][1] * k))
    return im, at


def split(cut, comp, at, grow):
    """Нарисованное целиком (x4) - по клеткам. Кусок берёт свой силуэт целиком (где куски перекрываются,
    у обоих один и тот же пиксель общей картинки - игра рисует любой из них, шва нет) и кайму за
    силуэтом, ближайшую к нему: кайма общей картинки не делится пополам и не дублируется."""
    whole, _ = compose(comp)
    h, w = whole.height, whole.width
    sil, lab = {}, np.full((h, w), -1, np.int32)
    for i, (key, _o) in enumerate(comp["members"]):
        m = np.zeros((h, w), bool)
        x, y = at[key]
        m[y:y + 40, x:x + 32] = np.asarray(comp["spr"][key])[..., 3] > 0
        sil[key] = m
        lab[m & (lab < 0)] = i
    any_sil = lab >= 0
    for _ in range(grow + 2):
        # кайма растёт от силуэтов по шагу; спорный пиксель - тому, кто дотянулся первым
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(lab, (dy, dx), (0, 1))
            take = (lab < 0) & (src >= 0)
            lab[take] = src[take]
    alpha = np.asarray(cut.split()[3], np.float32)
    out = {}
    for i, (key, _o) in enumerate(comp["members"]):
        m = sil[key] | ((lab == i) & ~any_sil)
        m4 = np.repeat(np.repeat(m, 4, 0), 4, 1)
        piece = np.asarray(cut, np.uint8).copy()
        piece[..., 3] = (alpha * m4).astype(np.uint8)
        x, y = at[key]
        out[key] = Image.fromarray(piece, "RGBA").crop((x * 4, y * 4, x * 4 + 128, y * 4 + 160))
    return out


def on_floor(im, size):
    bg = Image.new("RGBA", im.size, FLOOR + (255,))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize(size, Image.NEAREST)


def make_sheet(items, old_root, path):
    """Тройки оригинал x4 | прежний пак | новый, по 4 тройки в ряд, в размере игры. Составной предмет
    (шестой элемент - прежний пак, собранный из кусков) - целиком, своим рядом внизу."""
    cw, ch, gap = 128, 160, 16
    per = 4
    tw = 3 * cw + 2 * 4
    ones = [it for it in items if len(it) == 5]
    comps = [it for it in items if len(it) == 6]
    rows = (len(ones) + per - 1) // per
    tall = [spr.height * 4 + 22 for _s, _f, spr, *_ in comps]
    wide = max([per * tw + (per - 1) * gap if ones else 0] + [3 * spr.width * 4 + 8 for _s, _f, spr, *_ in comps])
    sheet = Image.new("RGB", (wide, rows * (ch + 22) + sum(tall)), (32, 32, 36))
    d = ImageDraw.Draw(sheet)
    for n, (s, fr, spr, cut, what) in enumerate(ones):
        x, y = (n % per) * (tw + gap), (n // per) * (ch + 22)
        old = os.path.join(old_root, s + ".PCK", "%d.png" % fr)
        old = Image.open(old).convert("RGBA") if os.path.exists(old) else None
        cells = [spr.resize((cw, ch), Image.NEAREST), old, cut]
        for j, c in enumerate(cells):
            if c is not None:
                sheet.paste(on_floor(c, (cw, ch)), (x + j * (cw + 4), y + 20))
        # подписи латиницей: у шрифта PIL по умолчанию нет кириллицы
        d.text((x + 2, y + 4), "%s %d" % (s, fr), fill=(255, 255, 0))
    y = rows * (ch + 22)
    for (s, fr, spr, cut, what, old), t in zip(comps, tall):
        w, h = spr.width * 4, spr.height * 4
        for j, c in enumerate([spr.resize((w, h), Image.NEAREST), old, cut]):
            if c is not None:
                sheet.paste(on_floor(c, (w, h)), (j * (w + 4), y + 20))
        d.text((2, y + 4), "%s %d composite: orig | old pack | new" % (s, fr), fill=(255, 255, 0))
        y += t
    sheet.save(path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", type=int, default=47, help="сколько карт очереди взять (строки MAP_QUEUE.md)")
    ap.add_argument("--out", default="art/objects")
    ap.add_argument("--old", default="Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN",
                    help="прежний пак для листа - копия, которую читает игра (R-087)")
    ap.add_argument("--sheet-every", type=int, default=100, dest="sheet_every")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run", help="только план: сколько кадров, чего нет")
    ap.add_argument("--limit", type=int, default=0, help="нарисовать не больше стольких кадров (проверка)")
    ap.add_argument("--seed", type=int, default=2711)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--grow", type=int, default=2)
    ap.add_argument("--soft", type=int, default=40)
    ap.add_argument("--pad", type=int, default=3)
    ap.add_argument("--tone", type=float, default=0.7)
    ap.add_argument("--models", default=None)
    ap.add_argument("--model", default="")
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    ap.add_argument("--comp-hints", default="art/objects/composite_hints.json", dest="comp_hints",
                    help="подсказки составных предметов: ключ - первый кусок НАБОР:кадр")
    ap.add_argument("--only", default="",
                    help="только эти кадры (НАБОР:кадр,...) и составные, куда они входят - проба")
    ap.add_argument("--recut", default="",
                    help="перевырезка без модели: папки с сохранёнными ответами (raw) через запятую, поздняя "
                         "перекрывает раннюю; вырезается всё, у чего есть ответ, готовое в series не пропускается")
    ap.add_argument("--old-mask", action="store_true", dest="old_mask",
                    help="с --recut: прежний силуэт NEAREST x4 (контроль перевырезки, R-121)")
    args = ap.parse_args()
    recut = [d for d in args.recut.split(",") if d]
    if args.old_mask:
        po.SMOOTH_SILHOUETTE = False

    def raw_src(name):
        """Сохранённый ответ модели для --recut: последняя папка, где он есть."""
        for d in reversed(recut):
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
        return None

    world = mm.World()
    series = os.path.join(args.out, "series")
    raw = os.path.join(args.out, "raw")
    os.makedirs(series, exist_ok=True)
    os.makedirs(raw, exist_ok=True)

    # план: по картам, одна картинка - один заказ
    plan, by_hash, skipped, maps, mass = [], {}, [], [], set()
    for terrain, block, hp, fobj in map_list(args.maps):
        try:
            objs, anim, field = objects_of(world, terrain, block, fobj)
        except Exception as e:                                  # noqa: BLE001
            skipped.append((terrain, block, "", "", "карта не читается: %s" % e))
            continue
        maps.append((terrain, block, load_hints(hp), objs, anim, field))
        mass |= set(field)
    only = {(s.rsplit(":", 1)[0].upper(), int(s.rsplit(":", 1)[1])) for s in args.only.split(",") if ":" in s}
    comps = composites(world, [(m[0], m[1]) for m in maps], mass)
    in_comp = {key for c in comps for key, _o in c["members"]}
    comp_hints = load_hints(args.comp_hints)
    comp_plan, comp_seen = [], set()
    with open(os.path.join(args.out, "composites.tsv"), "w", encoding=ENC) as f:
        f.write("первый кусок\tкусков\tподсказка\tкуски и подсказки кусков\n")
        piece_hints = {}
        for m in maps:
            for k, v in m[2].items():
                piece_hints.setdefault(k, v)
        for c in comps:
            keys = [k for k, _o in c["members"]]
            sig = tuple((pix_hash(c["spr"][k]), o) for k, o in c["members"])
            what = comp_hints.get(keys[0], "")
            f.write("%s:%d\t%d\t%s\t%s\n" % (keys[0][0], keys[0][1], len(keys), what,
                                             " | ".join("%s:%d %s" % (k[0], k[1], piece_hints.get(k, "-"))
                                                        for k in keys)))
            if only and not only & set(keys):
                continue
            if sig in comp_seen:
                # тот же предмет в другом наборе (FOREST и FOREST_WASTE): копии кусков
                prev = next(p for p in comp_plan if p["sig"] == sig)
                prev["copies"].append(keys)
                continue
            if not what:
                skipped.append(("", "", keys[0][0], keys[0][1], "составной - нет подсказки"))
                continue
            comp_seen.add(sig)
            comp_plan.append({"comp": c, "sig": sig, "what": what, "copies": [keys]})
    for terrain, block, hints, objs, anim, field in maps:
        # массив на любой карте - массив везде: одна картинка на все его места
        for key in [k for k in objs if k in mass]:
            field[key] = objs.pop(key)
        # кусок составного рисуется вместе со всем предметом
        for key in [k for k in objs if k in in_comp or (only and k not in only)]:
            objs.pop(key)
        for (s, fr) in sorted(anim):
            skipped.append((terrain, block, s, fr, "анимация"))
        for (s, fr) in sorted(field):
            skipped.append((terrain, block, s, fr, "массив - способом полов"))
        n_new = 0
        for (s, fr), d in sorted(objs.items()):
            h = pix_hash(d["spr"])
            if h in by_hash:
                by_hash[h]["copies"].add((s, fr))
                continue
            what = hints.get((s, fr))
            if not what:
                skipped.append((terrain, block, s, fr, "нет подсказки"))
                continue
            by_hash[h] = {"set": s, "frame": fr, "spr": d["spr"], "what": what, "copies": {(s, fr)},
                          "block": block}
            plan.append(h)
            n_new += 1
        print("%-34s %-26s предметов %3d, новых картинок %3d, анимаций %d, массивов %d%s"
              % (terrain, block, len(objs), n_new, len(anim), len(field),
                 "" if hints else "  НЕТ ПОДСКАЗОК"), flush=True)
    with open(os.path.join(args.out, "skipped.tsv"), "w", encoding=ENC) as f:
        f.write("террейн\tкарта\tнабор\tкадр\tпочему\n")
        for r in skipped:
            f.write("\t".join(str(v) for v in r) + "\n")
    todo = [h for h in plan if not os.path.exists(
        os.path.join(series, by_hash[h]["set"] + ".PCK", "%d.png" % by_hash[h]["frame"]))]
    # составной готов, когда есть его ответ модели: куски могли остаться от прежней серии, где их
    # рисовали порознь, - их надо перерисовать
    for p in comp_plan:
        s, fr = p["copies"][0][0]
        p["raw"] = os.path.join(raw, "comp_%s_%d.png" % (s, fr))
    comp_todo = [p for p in comp_plan if not os.path.exists(p["raw"])]
    if recut:
        # перевырезка: всё, у чего есть сохранённый ответ; нет ответа - не рисуем
        for h in plan:
            by_hash[h]["src"] = raw_src("%s_%d.png" % (by_hash[h]["set"], by_hash[h]["frame"]))
        for p in comp_plan:
            s, fr = p["copies"][0][0]
            p["src"] = raw_src("comp_%s_%d.png" % (s, fr))
        todo = [h for h in plan if by_hash[h]["src"]]
        comp_todo = [p for p in comp_plan if p["src"]]
        print("ПЕРЕВЫРЕЗКА (%s силуэт): ответов есть - картинок %d из %d, составных %d из %d"
              % ("прежний" if args.old_mask else "xBRZ", len(todo), len(plan), len(comp_todo), len(comp_plan)),
              flush=True)
    print("картинок в плане %d, уже готово %d, рисовать %d; составных %d (найдено %d, без подсказки %d), "
          "рисовать %d; пропущено %d (skipped.tsv)"
          % (len(plan), len(plan) - len(todo), len(todo), len(comp_plan), len(comps),
             sum(1 for r in skipped if r[4].startswith("составной")), len(comp_todo), len(skipped)), flush=True)
    if args.dry_run:
        return
    todo = [("comp", p) for p in comp_todo] + [("one", h) for h in todo]
    if args.limit:
        todo = todo[:args.limit]

    ns = argparse.Namespace(models=args.models or po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model=args.model,
                            qwen21_steps=args.steps, qwen21_cfg=args.cfg, qwen21_mp=args.mp,
                            qwen21_strength=0.0, qwen21_offload=args.offload, qwen21_thrifty=False,
                            qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = None if recut else po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    po.gen_fire.NEGATIVE = po.NEGATIVE

    def paint(full, what, seed, raw_path, src_raw=None):
        """Кадр (или составной целиком) k=1 -> x4 RGBA того же размера."""
        box = (0, 0, full.width, full.height)
        bb = full.split()[3].getbbox()
        if args.pad >= 0:
            box = (max(0, bb[0] - args.pad), max(0, bb[1] - args.pad),
                   min(full.width, bb[2] + args.pad), min(full.height, bb[3] + args.pad))
        frame = full.crop(box)
        if src_raw:
            hd = Image.open(src_raw).convert("RGB")
        else:
            panel = po.pick_background(frame)
            src = frame.resize((frame.width * args.zoom, frame.height * args.zoom), Image.BICUBIC)
            flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
            flat.alpha_composite(src)
            prompt = po.STYLE["strict"].replace("{what}", what)
            hd = po.gen_fire.run_pass(painter, args, prompt, flat.convert("RGB"), seed)
            po.gen_hd.save_png(hd, raw_path)
        part = po.match_tone(po.cut_out(hd, frame, args.grow, args.soft), frame, args.tone)
        cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        return cut

    def save(cut, s, fr):
        os.makedirs(os.path.join(series, s + ".PCK"), exist_ok=True)
        po.gen_hd.save_png(cut, os.path.join(series, s + ".PCK", "%d.png" % fr))

    batch, t0 = [], time.time()
    for n, (kind, h) in enumerate(todo, 1):
        if kind == "comp":
            c = h["comp"]
            whole, at = compose(c)
            s, fr = c["members"][0][0]
            cut = paint(whole, h["what"], args.seed + fr, h["raw"], h.get("src"))
            pieces = split(cut, c, at, args.grow)
            for keys in h["copies"]:
                for (key, _o), (cs, cf) in zip(c["members"], keys):
                    save(pieces[key], cs, cf)
            old = {}
            for key, _o in c["members"]:
                p = os.path.join(args.old, key[0] + ".PCK", "%d.png" % key[1])
                if os.path.exists(p):
                    old[key] = Image.open(p).convert("RGBA")
            old_im = compose(c, old, 4)[0] if len(old) == len(c["members"]) else None
            batch.append((s, fr, whole, compose(c, pieces, 4)[0], h["what"], old_im))
            info = "составной из %d, копий %d" % (len(c["members"]), len(h["copies"]))
            what = h["what"]
        else:
            e = by_hash[h]
            s, fr, full = e["set"], e["frame"], e["spr"]
            if full.split()[3].getbbox() is None:
                continue
            cut = paint(full, e["what"], args.seed + fr, os.path.join(raw, "%s_%d.png" % (s, fr)), e.get("src"))
            for (cs, cf) in sorted(e["copies"]):
                save(cut, cs, cf)
            batch.append((s, fr, full, cut, e["what"]))
            info = "%s, копий %d" % (e["block"], len(e["copies"]))
            what = e["what"]
        el = time.time() - t0
        print("[%d/%d] %s %d (%s): %s | %s, осталось ~%s"
              % (n, len(todo), s, fr, info, what[:60],
                 po.gen_hd.human_time(el), po.gen_hd.human_time(el / n * (len(todo) - n))), flush=True)
        if len(batch) >= args.sheet_every or n == len(todo):
            k = len([f for f in os.listdir(args.out) if f.startswith("sheet_")]) + 1
            p = make_sheet(batch, args.old, os.path.join(args.out, "sheet_%04d.png" % k))
            print("ЛИСТ %s: %d кадров" % (p, len(batch)), flush=True)
            batch = []
    print("готово за %s" % po.gen_hd.human_time(time.time() - t0))


if __name__ == "__main__":
    main()
