# -*- coding: utf-8 -*-
"""Список для ручной проверки: оригинал | первая генерация (прежний пак) | вторая (LoRA).

Берёт оценки обеих генераций (score_batch.py по моду и по резерву) и отбирает --pick кадров,
у которых ХОТЯ БЫ ОДНА генерация ближе всего к оригиналу (больший из двух баллов), одна
картинка один раз, не больше --per-set на набор, площадь не меньше --min-area.

Для каждого кадра собирает «что это по данным игры» из MCD: тип части клетки (пол, западная
или северная стена, объект), сплошной блок и диагональ (Big_Wall), дверь и раздвижная дверь,
лифт, проходимость, высота, анимация, особая клетка (Target_Type), во что разрушается,
плюс террейны Пираток, где живёт набор (.index/mod/Piratez/set_terrains.tsv), и подсказку
кадра из hints.json. Поля MCD - по struct MCD в src/Mod/MapDataSet.cpp, у Пираток MCDPatches нет.

Пишет art/_review/triage/items.json и оригиналы 32x40 в art/_review/triage/orig/.

    python tools/hdart/triage/build.py --pick 1000
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import build_dataset as bd                                             # noqa: E402
import gen_lora_batch as glb                                           # noqa: E402
import link_frames as lfr                                              # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import pck_census as pc                                                # noqa: E402
import score_batch as sb                                               # noqa: E402
import tile_forge as tf                                                # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("art", "_review", "triage")
OLD = os.path.join("art", "_backup", "TERRAIN_before_lora_20260924_1057")
PIRATEZ = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez")

# смещения полей записи MCD (62 байта), порядок struct MCD в src/Mod/MapDataSet.cpp
F = dict(ufo_door=30, stop_los=31, no_floor=32, big_wall=33, gravlift=34, door=35,
         tu_walk=39, tu_slide=40, tu_fly=41, armor=42, die_mcd=44, flammable=45, alt_mcd=46,
         t_level=48, light_block=51, footstep=52, type=53, light=58, target=59)
TYPE_RU = {0: "пол", 1: "западная стена", 2: "северная стена", 3: "объект"}
TYPE_EN = {0: "floor", 1: "west wall", 2: "north wall", 3: "object"}
# Big_Wall: enum в src/Battlescape/Pathfinding.h (BLOCK = 1 ... BIGWALLWESTANDNORTH = 9)
BIG_RU = {1: "сплошной блок на всю клетку", 2: "диагональная стена СВ-ЮЗ", 3: "диагональная стена СЗ-ЮВ",
          4: "стена по западному краю", 5: "стена по северному краю", 6: "стена по восточному краю",
          7: "стена по южному краю", 8: "стена по восточному и южному краю",
          9: "стена по западному и северному краю"}
BIG_EN = {1: "solid block filling the whole tile", 2: "diagonal wall", 3: "diagonal wall",
          4: "wall on the west edge", 5: "wall on the north edge", 6: "wall on the east edge",
          7: "wall on the south edge", 8: "wall on the east and south edges",
          9: "wall on the west and north edges"}
# Target_Type: enum SpecialTileType в src/Mod/MapData.h
TARGET_RU = {1: "точка высадки", 2: "источник энергии НЛО", 3: "навигация НЛО", 4: "конструкция НЛО",
             5: "пища пришельцев", 6: "размножение пришельцев", 7: "развлечения пришельцев",
             8: "хирургия пришельцев", 9: "смотровая", 10: "сплав пришельцев", 11: "жилище пришельцев",
             12: "мёртвая клетка", 13: "выход", 14: "цель уничтожения"}


def read_full(path):
    with open(path, "rb") as f:
        data = f.read()
    out = []
    for n in range(0, len(data) - lfr.RECORD + 1, lfr.RECORD):
        b = data[n:n + lfr.RECORD]
        r = {k: b[o] for k, o in F.items()}
        r["t_level"] = r["t_level"] - 256 if r["t_level"] > 127 else r["t_level"]
        r["frames"] = list(b[0:8])
        r["i"] = len(out)
        out.append(r)
    return out


def describe(recs, i):
    """Факты о кадре i по всем записям MCD, которые на него ссылаются."""
    own = [r for r in recs if i in r["frames"]]
    if not own:
        return None
    ru, en, kinds = [], [], []
    for r in own[:3]:
        t = r["type"]
        parts = [TYPE_RU.get(t, "тип %d" % t)]
        e = [TYPE_EN.get(t, "object")]
        if r["big_wall"] in BIG_RU:
            parts.append(BIG_RU[r["big_wall"]])
            e.append(BIG_EN[r["big_wall"]])
        if r["door"]:
            parts.append("дверь (открывается)")
            e.append("hinged door")
        if r["ufo_door"]:
            parts.append("раздвижная дверь")
            e.append("sliding door")
        if r["gravlift"]:
            parts.append("гравилифт")
            e.append("grav lift pad")
        if r["no_floor"] and t == 0:
            parts.append("без пола (можно упасть)")
        if r["stop_los"]:
            parts.append("закрывает обзор")
        tu = r["tu_walk"]
        parts.append("непроходимо" if tu == 255 else "ход %d ОВ" % tu)
        if r["t_level"]:
            parts.append("высота %d" % -r["t_level"])
        if r["armor"]:
            parts.append("броня %d" % r["armor"])
        anim = len(set(r["frames"]))
        if anim > 1:
            parts.append("анимация %d кадров" % anim)
            e.append("animated")
        if r["light"]:
            parts.append("светится (%d)" % r["light"])
            e.append("light source")
        if r["target"] in TARGET_RU:
            parts.append("особая клетка: " + TARGET_RU[r["target"]])
        if r["die_mcd"]:
            parts.append("разрушается в запись %d" % r["die_mcd"])
        ru.append("запись %d: %s" % (r["i"], ", ".join(parts)))
        en.append(", ".join(e))
        kinds.append(r)
    dead = [r["i"] for r in recs if r["die_mcd"] and r["die_mcd"] in [o["i"] for o in own]]
    if dead:
        ru.append("это обломки записей %s" % ", ".join(map(str, dead[:4])))
        en.append("rubble left after destruction")
    return {"ru": ru, "en": "; ".join(en), "main": kinds[0], "rubble": bool(dead)}


def cls_phrase(d):
    """Кем назвать клетку в промпте - по данным игры, до всякого описания моделью."""
    r = d["main"]
    if d["rubble"]:
        return "rubble"
    if r["ufo_door"]:
        return "sliding door"
    if r["door"]:
        return "door"
    if r["big_wall"] == 1:
        return "solid block"
    if r["big_wall"] in (2, 3):
        return "diagonal wall"
    t = r["type"]
    if t == 0:
        return "floor tile"
    if t == 1:
        return "west wall segment"
    if t == 2:
        return "north wall segment"
    return "object"


def read(p):
    with open(p, encoding=ENC, newline="") as f:
        return {(r["набор"], r["кадр"]): r for r in csv.DictReader(f, delimiter="\t")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", default="art/_review/batch_score/score.tsv")
    ap.add_argument("--old", default="art/_review/batch_score_old/score.tsv")
    ap.add_argument("--old-mod", default=OLD, dest="old_mod")
    ap.add_argument("--mod", default=sb.MOD)
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--pick", type=int, default=1000)
    ap.add_argument("--per-set", type=int, default=6, dest="per_set")
    ap.add_argument("--min-area", type=float, default=0.08, dest="min_area")
    a = ap.parse_args()

    new, old = read(a.new), read(a.old)
    # набор -> террейны: terrains И battlescapeTerrainData кораблей и НЛО (set_terrains.tsv
    # из index_mod.py вторых не видит, а это самые ходовые наборы)
    terr = {}
    for tname, t in pc.collect_terrains(PIRATEZ).items():
        for s in t.get("mapDataSets") or []:
            terr.setdefault(str(s).upper(), []).append(tname)
    usage = {}
    with open(os.path.join("census", "sets.tsv"), encoding=ENC) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["раздел"] == "TERRAIN":
                usage[r["набор"].upper()] = (r["клеток"], r["блоков"])
    pool = []
    for k, n in new.items():
        o = old.get(k)
        if o is None or float(n["area"]) < a.min_area:
            continue
        pool.append((max(float(n["балл"]), float(o["балл"])), k, n, o))
    pool.sort(key=lambda x: -x[0])

    os.makedirs(os.path.join(a.out, "orig"), exist_ok=True)
    sheets, mcds, seen, per, items = {}, {}, set(), {}, []
    for best, (name, fr), n, o in pool:
        if len(items) >= a.pick:
            break
        if per.get(name, 0) >= a.per_set or (n["hash"] and n["hash"] in seen):
            continue
        i = int(fr)
        if not (os.path.exists(os.path.join(a.old_mod, name, fr + ".png"))
                and os.path.exists(os.path.join(a.mod, name, fr + ".png"))):
            continue
        if name not in mcds:
            p = lfr.find_mcd(glb.MCD_DIRS, name)
            mcds[name] = read_full(p) if p else None
            sheets[name] = tf.Sheet(a.sheets, name)
        sh, recs = sheets[name], mcds[name]
        d = describe(recs, i) if recs else None
        if d is None:
            continue                                   # кадр-сирота: игра его не рисует (R-052)
        stem = name[:-4]
        iid = "%s_%d" % (stem, i)
        sh.frame(i).save(os.path.join(a.out, "orig", iid + ".png"))
        hint = sh.hints.get(i, "")
        tl = terr.get(stem.upper()) or []
        facts_ru = d["ru"] + ["террейны: " + (", ".join(tl[:6]) + (" и ещё %d" % (len(tl) - 6) if len(tl) > 6 else "")
                                             if tl else "не найдены")]
        if stem.upper() in usage:
            facts_ru.append("набор на картах: %s клеток в %s блоках" % usage[stem.upper()])
        if hint:
            facts_ru.append("подсказка кадра: " + hint)
        items.append({
            "id": iid, "set": stem, "frame": i, "hash": n["hash"],
            "kind": n["подпись_вид"], "cls": cls_phrase(d),
            "facts_ru": facts_ru, "facts_en": d["en"] + ("; hint: " + hint if hint else ""),
            "hint": hint,
            "prompt_used": sb.CAPTION.format(trigger="oxcehd, ", kind=bd.prompt_kind(sh, i),
                                             hint=hint or "terrain tile"),
            "g1": {"ok": int(o["годен"]), "score": float(o["балл"]), "flags": o["flags"]},
            "g2": {"ok": int(n["годен"]), "score": float(n["балл"]), "flags": n["flags"]},
            "img1": os.path.join(a.old_mod, name, fr + ".png"),
            "img2": os.path.join(a.mod, name, fr + ".png"),
        })
        per[name] = per.get(name, 0) + 1
        if n["hash"]:
            seen.add(n["hash"])
    with open(os.path.join(a.out, "items.json"), "w", encoding=ENC) as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=0)
    c = {}
    for it in items:
        c[it["cls"]] = c.get(it["cls"], 0) + 1
    low = min((max(it["g1"]["score"], it["g2"]["score"]) for it in items), default=0)
    print("кадров %d из %d наборов, балл не ниже %.3f; %s" % (len(items), len(per), low, c))
    print("без террейна: %d" % sum(1 for it in items if "террейны: не найдены" in it["facts_ru"]))


if __name__ == "__main__":
    main()
