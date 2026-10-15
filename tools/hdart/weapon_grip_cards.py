"""Связанные карточки сотни W-001..W-100: BIGOBS + боеприпасы + восемь HANDOB + макет хвата (указание специалиста 06.10).

Подготовка без генерации, видеокарта не нужна. Связывает то, что уже собрано:
  - ammo_cards/  (weapon_ammo_cards.py) - ствол и все боеприпасы, педия;
  - handob_cards/ (weapon_handob_cards.py) - восемь кадров handSprite+k и точка вспышки noteTip;
  - art/units/grip-contract/ (grip_matrix.py) - виды хвата routine 0, фильтр касания, общая опора цевья в прицеле.
и добавляет то, чего не было: сборку кадра с персонажем (агент GOV_1, классика) по каждому виду хвата и направлению,
точки макета на каждом кадре HANDOB и список носителей оружия по процедурам рисования.

Макет хвата - что HD-кадр HANDOB обязан выдержать (не покрытие классического силуэта):
  - точка хвата: пиксель кадра, ближайший к кисти главной руки (rarm 232/248/256+d);
  - точка опоры: пиксель кадра, ближайший к кисти опорной руки (larm 240+d) - цевьё двуручного;
  - направление ствола: взгляд юнита d на экране (axis_cos длинной оси кадра к взгляду);
  - точка вспышки: крайняя точка рисунка вдоль взгляда (копия HdFx::noteTip), в координатах кадра и юнита.
    Это НЕ проверенное дуло: настоящий конец ствола размечен руками только у восьми конструкций
    (grip_check8/parts_manual.json, проверка tools/hdart/grip_check8.py).
Касание кисти и кадра (держит / рядом / мимо) - фильтр, не доказательство хвата; IoU и покрытие тут не меряются.

Носители: брони с drawingRoutine. Предмет в руке рисуют только процедуры 0 (и 10, 13, 14, 15 - та же drawRoutine0),
1, 4 (и 17, 18), 6. Контракт снят для routine 0; для 1, 4, 6 и 10 совместимость НЕ объявляется - только помечается.
Бойцы игрока могут взять любое оружие: их процедуры одни на всю сотню. Враги: units.builtInWeapons(Sets) точно,
alienDeployments.data.itemSets по рангу -> расы развёртывания (race, иначе alienMissions по siteType или ufo волн)
-> members[ранг] -> armor -> drawingRoutine. reinforcements и civiliansByType не разбираются.

  py -3.13 tools/hdart/weapon_grip_cards.py [--only W-053]
  -> art/items/weapons100-v1/grip_cards/: <W>.<тип>.png, sheet_NN.png, cards.json, frames.tsv, carriers.tsv, summary.tsv
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grip_matrix as gm  # noqa: E402
import weapon_ammo_cards as wac  # noqa: E402
import weapon_handob_cards as whc  # noqa: E402

ROOT = wac.ROOT
ENC = "utf-8-sig"
LIST = "art/items/weapons100-v1/list.tsv"
OUT = "art/items/weapons100-v1/grip_cards"
HANDOB_CARDS = "art/items/weapons100-v1/handob_cards"
AMMO_TSV = "art/items/weapons100-v1/ammo_cards/ammo.tsv"
GRIP = "art/units/grip-contract"
ITEMS = "census/items/items.tsv"
WEAP = "docs/research/piratez-weapons.tsv"
VALUES = ".index/mod/Piratez/rul/values.tsv"
K = gm.K
M = 14            # поля холста сборки, пикс базы: сдвиг предмета до 13
KA = 3            # масштаб сборки на карточке
FAMILY = {0: "R0", 13: "R0", 14: "R0", 15: "R0", 10: "R10", 1: "R1", 4: "R4", 17: "R4", 18: "R4", 6: "R6"}
FAMILY_NOTE = {"R0": "контракт снят (drawRoutine0)", "R10": "drawRoutine0 со своими сдвигами - не объявлено",
               "R1": "drawRoutine1 - не объявлено", "R4": "drawRoutine4, рук нет - не объявлено",
               "R6": "drawRoutine6 - не объявлено", "-": "предмет в руке не рисуется"}
ARM = {"ONE": ("ra", 232), "TWO_STAND": ("ra", 248), "TWO_AIM": ("ra", 256), "LEFT_ONE": ("la", 240),
       "LEFT_TWO_AIM": ("ra", 256)}
SUPPORT = {"TWO_STAND": 240, "TWO_AIM": 240, "LEFT_TWO_AIM": 240}


def fam(r):
    return FAMILY.get(r, "-")


def read_tsv(p):
    with open(p, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def load_values():
    csv.field_size_limit(1 << 30)
    d = defaultdict(dict)
    keep = {"armors", "units", "soldiers", "alienRaces", "alienDeployments", "alienMissions"}
    with open(VALUES, encoding=ENC, newline="") as f:
        for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(r) >= 4 and r[0] in keep:
                d[(r[0], r[1])][r[2]] = wac.jv(r[3])
    return d


def carriers(v):
    """-> (процедуры бойцов игрока Counter, {предмет: {routine: set(unit)}}, {предмет: [заметки]})."""
    sec = lambda s: {i: x for (a, i), x in v.items() if a == s}
    armors, units, soldiers, races = sec("armors"), sec("units"), sec("soldiers"), sec("alienRaces")
    deps, missions = sec("alienDeployments"), sec("alienMissions")
    routine = {a: (x.get("drawingRoutine") or 0) for a, x in armors.items()}
    player = Counter()
    for a, x in armors.items():
        us = x.get("units")
        if isinstance(us, list) and any(u in soldiers for u in us):
            player[routine[a]] += 1
    item_units = defaultdict(lambda: defaultdict(set))
    notes = defaultdict(set)

    def add(item, unit, how):
        a = (units.get(unit) or {}).get("armor")
        if a is None:
            notes[item].add("носитель %s без брони в рулсетах" % unit)
            return
        item_units[item][routine.get(a, 0)].add(unit)
        notes[item].add(how)
    for u, x in units.items():
        bw = list(x.get("builtInWeapons") or [])
        for s in x.get("builtInWeaponSets") or []:
            bw += list(s) if isinstance(s, list) else []
        for it in bw:
            if isinstance(it, str):
                add(it, u, "встроено у юнита")
    # расы развёртывания
    by_dep = defaultdict(set)
    for m, x in missions.items():
        rs = set()
        for wts in (x.get("raceWeights") or {}).values():
            if isinstance(wts, dict):
                rs |= set(wts)
        for w in x.get("waves") or []:
            if isinstance(w, dict) and w.get("ufo"):
                by_dep[w["ufo"]] |= rs
        if x.get("siteType"):
            by_dep[x["siteType"]] |= rs
    for dep, x in deps.items():
        rs = {x["race"]} if x.get("race") else by_dep.get(dep, set())
        for blk in x.get("data") or []:
            if not isinstance(blk, dict):
                continue
            rank = blk.get("alienRank", 0)
            its = {i for s in blk.get("itemSets") or [] if isinstance(s, list) for i in s if isinstance(i, str)}
            for it in its:
                if not rs:
                    notes[it].add("развёртывание %s: раса не найдена" % dep)
                for r in rs:
                    mem = (races.get(r) or {}).get("members") or []
                    if rank < len(mem):
                        add(it, mem[rank], "в развёртываниях врагов")
    return player, item_units, notes


def skin_center(n, d):
    ys, xs = np.nonzero(np.isin(gm.gov(n + d), gm.SKIN))
    return (float(xs.mean()), float(ys.mean())) if len(xs) else None


def nearest(mask, p):
    ys, xs = np.nonzero(mask)
    if not len(xs) or p is None:
        return None
    i = int(np.argmin((xs - p[0]) ** 2 + (ys - p[1]) ** 2))
    return int(xs[i]), int(ys[i]), float(np.hypot(xs[i] - p[0], ys[i] - p[1]))


def contexts(hs, two, d):
    """Виды хвата routine 0 для направления d: (вид, кадр, сдвиг, кадр главной руки, кадр опорной руки или None)."""
    cases = gm.TWO_H if two else gm.ONE_H
    out = []
    for c in cases:
        la, ra, rot, side, who = gm.CASES[c]
        main = ARM[c][1]
        sup = SUPPORT.get(c)
        out.append((c, hs + (d + rot) % 8, gm.OFF[c][0][d], gm.OFF[c][1][d], main, sup))
    return out


def frame_rows(m, t, hs, two, matrix, aim_sup):
    rows = []
    for d in range(8):
        for c, fr, ox, oy, main, sup in contexts(hs, two, d):
            idx = gm.hob(fr)
            mask = idx > 0
            tip = whc.note_tip(idx, d) if mask.any() else None
            flags = whc.shape_flags(idx, tip) if tip else {}
            hp = skin_center(main, d)
            sp = skin_center(sup, d) if sup is not None else None
            # точки в координатах кадра HANDOB: кисть юнита минус сдвиг предмета
            g = nearest(mask, (hp[0] - ox, hp[1] - oy) if hp else None)
            s = nearest(mask, (sp[0] - ox, sp[1] - oy) if sp else None)
            mx = matrix.get((hs, c, d), {})
            r = {"master": m, "type": t, "case": c, "dir": d, "frame": fr, "offX": ox, "offY": oy,
                 "main_arm": main + d, "main_hand_x": "%.1f" % hp[0] if hp else "", "main_hand_y": "%.1f" % hp[1] if hp else "",
                 "grip_x": g[0] if g else "", "grip_y": g[1] if g else "", "grip_gap": "%.1f" % g[2] if g else "",
                 "support_arm": sup + d if sup is not None else "",
                 "support_hand_x": "%.1f" % sp[0] if sp else "", "support_hand_y": "%.1f" % sp[1] if sp else "",
                 "forend_x": s[0] if s else "", "forend_y": s[1] if s else "", "forend_gap": "%.1f" % s[2] if s else "",
                 "aim_support_unit": ("%s,%s" % (aim_sup[d]["aim_support_x"], aim_sup[d]["aim_support_y"]))
                 if c == "TWO_AIM" else "",
                 "flash_x": tip[0] if tip else "", "flash_y": tip[1] if tip else "",
                 "flash_unit_x": tip[0] + ox if tip else "", "flash_unit_y": tip[1] + oy if tip else "",
                 "axis_cos": flags.get("axis_cos", ""), "tip_cross": flags.get("cross", ""),
                 "tip_split": flags.get("split", ""),
                 "near": mx.get("near", ""), "far": mx.get("far", "")}
            rows.append(r)
    return rows


def short(v):
    if not v:
        return "-"
    s = {"держит": "Д", "рядом": "Р", "мимо": "М", "нет кисти": "нет"}.get(v.split(",")[0], "?")
    return s + ("*" if "не видна" in v else "")


def cross(dr, x, y, col, r=7, w=2):
    dr.line([x - r, y, x + r, y], fill=col, width=w)
    dr.line([x, y - r, x, y + r], fill=col, width=w)


def compose_margin(hs, case, d):
    """Кадр юнита routine 0 на холсте с полями M: предмет со сдвигом выходит за 32x40, движок его не обрезает
    (gm.compose сдвигает np.roll - вышедшее переносится на другой край)."""
    la, ra, rot, side, _ = gm.CASES[case]
    H, W = 40 + 2 * M, 32 + 2 * M
    rgb = np.zeros((H, W, 3), np.float32)
    alpha = np.zeros((H, W), np.float32)
    def put(idx, pal, x, y):
        nonlocal rgb, alpha
        a = (idx > 0).astype(np.float32)
        sl = (slice(y, y + idx.shape[0]), slice(x, x + idx.shape[1]))
        rgb[sl] = pal[idx] * a[..., None] + rgb[sl] * (1 - a[..., None])
        alpha[sl] = np.maximum(alpha[sl], a)
    L = {"la": la + d, "ra": ra + d, "lg": 16 + d, "to": 32 + d}
    item = "iR" if side == "R" else "iL"
    for n in gm.order(d, case.endswith("AIM"), case in gm.TWO_H):
        if n in L:
            put(gm.gov(L[n]), gm.gpal, M, M)
        elif n == item:
            put(gm.hob(hs + (d + rot) % 8), gm.hpal, M + gm.OFF[case][0][d], M + gm.OFF[case][1][d])
    fl = (np.indices((H, W)).sum(0) % 2)[..., None] * 8 + 50.0
    fl[M:M + 40, M:M + 32] += 10
    out = np.clip(rgb * alpha[..., None] + fl * (1 - alpha[..., None]), 0, 255).astype(np.uint8)
    return Image.fromarray(out).resize((W * KA, H * KA), Image.NEAREST)


def assembly_cell(hs, case, d, fr_row, fonts):
    img = compose_margin(hs, case, d)
    dr = ImageDraw.Draw(img)
    c = lambda x, y: ((float(x) + 0.5 + M) * KA, (float(y) + 0.5 + M) * KA)
    if fr_row["main_hand_x"] != "":
        cross(dr, *c(fr_row["main_hand_x"], fr_row["main_hand_y"]), (0, 230, 255))
    if fr_row["support_hand_x"] != "":
        cross(dr, *c(fr_row["support_hand_x"], fr_row["support_hand_y"]), (60, 255, 120))
    if fr_row["aim_support_unit"]:
        ax, ay = fr_row["aim_support_unit"].split(",")
        if ax:
            x, y = c(ax, ay)
            dr.ellipse([x - 5, y - 5, x + 5, y + 5], outline=(255, 200, 0), width=2)
    if fr_row["flash_unit_x"] != "":
        # точка вспышки noteTip, не дуло; tipX - угол пикселя (среднее + 0.5, округлено), как в handob_cards
        x, y = (fr_row["flash_unit_x"] + M) * KA, (fr_row["flash_unit_y"] + M) * KA
        dr.line([x - 6, y - 6, x + 6, y + 6], fill=(255, 150, 0), width=2)
        dr.line([x - 6, y + 6, x + 6, y - 6], fill=(255, 150, 0), width=2)
    # взгляд юнита над головой
    sx, sy = whc.DIRX[d] - whc.DIRY[d], (whc.DIRX[d] + whc.DIRY[d]) * 0.5
    L = 16 / np.hypot(sx, sy)
    x0, y0 = (16 + M) * KA, (M - 4) * KA
    dr.line([x0, y0, x0 + sx * L, y0 + sy * L], fill=(80, 200, 255), width=2)
    dr.ellipse([x0 + sx * L - 3, y0 + sy * L - 3, x0 + sx * L + 3, y0 + sy * L + 3], fill=(80, 200, 255))
    return img


def build_card(row, it, cls, ammo, frows, hs, two, carrier, fonts, player):
    F, FB, FS = fonts
    t, m = row["type"], row["master"]
    top_p = os.path.join(HANDOB_CARDS, "%s.%s.png" % (m, t))
    top = Image.open(top_p).convert("RGB") if os.path.exists(top_p) else None
    cases = (gm.TWO_H if two else gm.ONE_H) if hs is not None else ()
    cw, chh, gap = (32 + 2 * M) * KA, (40 + 2 * M) * KA, 6
    text_lines = []
    W = max(top.width if top else 0, 10 + 8 * (cw + gap) + 150)
    H = (top.height if top else 0) + 16 + 30 + len(cases) * (chh + 26) + 18 * 9 + 20
    card = Image.new("RGB", (W, H), (24, 24, 27))
    dr = ImageDraw.Draw(card)
    y = 0
    if top:
        card.paste(top, (0, 0))
        y = top.height + 8
    dr.line([0, y, W, y], fill=(90, 90, 100))
    y += 8
    dr.text((10, y), "Макет хвата, routine 0, агент GOV_1 (классика x3, светлее - клетка 32x40, предмет за ней движок не режет).Голубой крест - кисть главной руки, зелёный - опорной, "
                     "жёлтый круг - общая точка цевья в прицеле, оранжевый X - точка вспышки noteTip (не дуло), синяя - взгляд. "
                     "Д/Р/М - фильтр касания (держит/рядом/мимо), * - кисть закрыта", font=FS, fill=(150, 200, 255))
    y += 24
    by = {(r["case"], r["dir"]): r for r in frows}
    for c in cases:
        dr.text((10, y), c, font=FB, fill=(235, 235, 235))
        for d in range(8):
            r = by[(c, d)]
            x = 150 + d * (cw + gap)
            card.paste(assembly_cell(hs, c, d, r, fonts), (x, y))
            lab = "d%d  к%d  %s/%s" % (d, r["frame"], short(r["near"]), short(r["far"]))
            dr.text((x, y + chh + 2), lab, font=FS, fill=(200, 200, 200))
        dr.text((10, y + 24), "кадр hs+%s" % ("(d+2)%8" if c.endswith("AIM") else "d"), font=FS, fill=(170, 170, 170))
        y += chh + 26
    # текст карточки
    fams = Counter()
    for rt, us in carrier.items():
        fams[fam(rt)] += len(us)
    lines = [
        "%s %s - %s / %s;  вид %s;  класс: %s (%s)" % (m, t, row["ru"], row["en"], row["kind"], cls[0], cls[1]),
        "BIGOBS %s, клетки %s;  handSprite %s%s;  %s;  fixedWeapon %s;  скрипты кадра: %s" % (
            row["frame"], row["cells"], it.get("handSprite_raw", "?"),
            " (кадры %d..%d)" % (hs, hs + 7) if hs is not None else " - кадра в руке нет",
            "двуручное" if two else "одноручное", it.get("fixedWeapon", "?"), it.get("sprite_scripts") or "нет"),
        "боеприпасы: " + (", ".join("%s [к%s%s]" % (a["ammo"], a["frame"], ", " + a["same_frame_as"] if a["same_frame_as"] else "")
                                    for a in ammo) if ammo else "нет (заряд встроен или холодное)"),
        "бойцы игрока: процедуры " + ", ".join("%s:%d брон%s" % (k, n, "я" if n == 1 else "и")
                                              for k, n in sorted(player.items())) + " - одни на всю сотню",
        "враги: " + (", ".join("%s %d юн. (%s)" % (f, n, FAMILY_NOTE[f]) for f, n in sorted(fams.items())) or "не найдены"),
    ]
    lines += ["примечание: " + n for n in row.get("_notes", [])]
    for ln in lines:
        dr.text((10, y), ln, font=FS, fill=(220, 220, 220))
        y += 18
    return card.crop((0, 0, W, y + 8))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    os.chdir(ROOT)
    rows = read_tsv(LIST)
    if a.only:
        rows = [r for r in rows if r["master"] in set(a.only.split(","))]
    items = {r["type"]: r for r in read_tsv(ITEMS)}
    cls = {}
    for r in read_tsv(WEAP):
        cls.setdefault(r["оружие_id"], (r["класс_название"], r["основание_класса"]))
    ammo = defaultdict(list)
    for r in read_tsv(AMMO_TSV):
        ammo[r["master"]].append(r)
    matrix = defaultdict(dict)
    for r in read_tsv(os.path.join(GRIP, "grip_matrix.tsv")):
        matrix[(int(r["handSprite"]), r["case"], int(r["dir"]))][r["hand"]] = r["verdict"]
    aim_sup = {int(r["dir"]): r for r in read_tsv(os.path.join(GRIP, "aim_support.tsv"))}
    player, item_units, notes = carriers(load_values())
    fonts = (ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15), ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 16),
             ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13))
    os.makedirs(OUT, exist_ok=True)
    allf, cards, carr, pngs = [], [], [], []
    for row in rows:
        t, m = row["type"], row["master"]
        it = items.get(t, {})
        two = it.get("twoHanded") == "True"
        hs = int(it["handSprite"]) if it.get("hand_default") == "False" and it.get("hand_frames") == "8" else None
        rnotes = []
        if hs is None:
            rnotes.append("кадра в руке нет (handSprite по умолчанию %s, кадров %s) - в бою предмет в руке не виден"
                          % (it.get("handSprite", "?"), it.get("hand_frames", "?")))
        if it.get("sprite_scripts"):
            rnotes.append("кадр меняет скрипт (%s) - макет по базовому кадру" % it["sprite_scripts"])
        if it.get("fixedWeapon") == "True":
            rnotes.append("fixedWeapon - встроенное оружие")
        if hs is not None and not any(matrix.get((hs, c, 0)) for c in (gm.TWO_H if two else gm.ONE_H)):
            rnotes.append("handSprite %d нет в матрице хвата" % hs)
        carrier = item_units.get(t, {})
        nonzero = sorted({fam(r) for r in carrier} - {"R0", "-"})
        if nonzero:
            rnotes.append("у врагов есть носители %s - совместимость не объявлена" % ", ".join(nonzero))
        row["_notes"] = rnotes
        frows = frame_rows(m, t, hs, two, matrix, aim_sup) if hs is not None else []
        allf += frows
        for rt, us in sorted(carrier.items()):
            carr.append({"master": m, "type": t, "routine": rt, "family": fam(rt), "units": len(us),
                         "examples": ", ".join(sorted(us)[:6]), "note": FAMILY_NOTE[fam(rt)]})
        card = build_card(row, it, cls.get(t, ("?", "?")), ammo.get(m, []), frows, hs, two, carrier, fonts, player)
        p = os.path.join(OUT, "%s.%s.png" % (m, t))
        card.save(p)
        pngs.append(p)
        fams = Counter()
        for rt, us in carrier.items():
            fams[fam(rt)] += len(us)
        def cnt(case, hand, word):
            return sum(1 for r in frows if r["case"] == case and r[hand].startswith(word) and "не видна" not in r[hand])
        cards.append({"master": m, "type": t, "ru": row["ru"], "en": row["en"], "kind": row["kind"],
                      "class": cls.get(t, ("?", "?"))[0], "class_basis": cls.get(t, ("?", "?"))[1],
                      "bigobs": int(row["frame"]), "cells": row["cells"], "handSprite": hs, "twoHanded": two,
                      "grip_cases": list(gm.TWO_H if two else gm.ONE_H) if hs is not None else [],
                      "ammo": [{"ammo": x["ammo"], "frame": x["frame"], "same_frame_as": x["same_frame_as"]} for x in ammo.get(m, [])],
                      "handob_card": os.path.join(HANDOB_CARDS, "%s.%s.png" % (m, t)).replace(os.sep, "/"),
                      "ammo_card": "art/items/weapons100-v1/ammo_cards/%s.%s.png" % (m, t),
                      "grip_card": p.replace(os.sep, "/"),
                      "enemy_families": dict(fams), "notes": rnotes,
                      "filter": {c: {h: [cnt(c, h, w) for w in ("держит", "рядом", "мимо")] for h in ("near", "far")}
                                 for c in (gm.TWO_H if two else gm.ONE_H)} if hs is not None else {}})
        print("%s %-24s hs %-5s %s  враги %s%s" % (m, t, hs, "2р" if two else "1р", dict(fams) or "-",
                                                    ("  !" + "; ".join(rnotes)) if rnotes else ""))
    tag = "_only" if a.only else ""
    with open(os.path.join(OUT, "cards%s.json" % tag), "w", encoding=ENC) as f:
        json.dump({"player_routines": dict(player), "family_note": FAMILY_NOTE, "cards": cards}, f, ensure_ascii=False, indent=1)
    for name, data in (("frames", allf), ("carriers", carr)):
        if data:
            with open(os.path.join(OUT, "%s%s.tsv" % (name, tag)), "w", encoding=ENC, newline="") as f:
                w = csv.DictWriter(f, list(data[0]), delimiter="\t")
                w.writeheader()
                w.writerows(data)
    summ = []
    for c in cards:
        summ.append({"master": c["master"], "type": c["type"], "kind": c["kind"], "class": c["class"],
                     "two": c["twoHanded"], "handSprite": c["handSprite"] if c["handSprite"] is not None else "",
                     "ammo": len(c["ammo"]), "enemy": ",".join("%s:%d" % kv for kv in sorted(c["enemy_families"].items())),
                     "notes": "; ".join(c["notes"])})
    with open(os.path.join(OUT, "summary%s.tsv" % tag), "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, list(summ[0]), delimiter="\t")
        w.writeheader()
        w.writerows(summ)
    if not a.only:
        wac.sheets(pngs, OUT)
    print("бойцы игрока, процедуры:", dict(sorted(player.items())))
    ef = Counter(f for c in cards for f in c["enemy_families"])
    print("стволов с врагами-носителями по семьям:", dict(ef))
    print("итог: карточек %d, без кадра в руке %d, двуручных %d" % (
        len(cards), sum(c["handSprite"] is None for c in cards), sum(c["twoHanded"] for c in cards)))


if __name__ == "__main__":
    main()
