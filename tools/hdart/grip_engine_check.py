"""Сверка сборки карточек хвата с движком (указание специалиста 06.10, пункт 3).

Сборка weapon_grip_cards.compose_margin идёт через таблицы grip_matrix (CASES, OFF, order). Здесь независимая
эмуляция: ветки UnitSprite::drawRoutine0 (routine 0, состояние стоя/прицел, без ходьбы и колена) и sortRifles
переписаны заново прямо по C++, без таблиц grip_matrix, и обе сборки сравниваются попиксельно на всей сотне.
Плюс обрезка: Map::drawUnit рисует стоящего юнита с маской GraphSubset шириной 2 клетки (x от -16 до 48) и высотой
tileHeight + topMargin (y от -16 до 40, на верхнем слое от -32): что ниже y = 40, движок не рисует.
Плюс сдвиг предмета от роста: itemR/itemL.offY += 22 - standHeight - руки при этом не сдвигаются.
Плюс старые листы grip_matrix (place = np.roll): какие клетки compare_d2 и all_d2_NN несут перенесённые пиксели.

  py -3.13 tools/hdart/grip_engine_check.py
  -> art/items/weapons100-v1/grip_cards/engine_check/: engine_check.tsv, clip.tsv, wrapped_old_sheets.tsv, README.md
"""
import csv
import os
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grip_matrix as gm  # noqa: E402
import weapon_grip_cards as wgc  # noqa: E402

ROOT = wgc.ROOT
ENC = "utf-8-sig"
OUT = "art/items/weapons100-v1/grip_cards/engine_check"
M = wgc.M

# UnitSprite::drawRoutine0, _drawingRoutine <= 10 и не 10
RARM1H, LARM2H, RARM2H, RARMSHOOT, LARMSTAND, RARMSTAND, LEGS, TORSO = 232, 240, 248, 256, 0, 8, 16, 32
OFFX = (8, 10, 7, 4, -9, -11, -7, -3)
OFFY = (-6, -3, 0, 2, 0, -4, -7, -9)
OFFX2 = (-8, 3, 5, 12, 6, -1, -5, -13)
OFFY2 = (1, -4, -2, 0, 3, 3, 5, 0)
OFFX6 = (0, 6, 6, 12, -4, -5, -5, -13)
OFFY6 = (-4, -4, -1, 0, 5, 0, 1, 0)
# Map::drawUnit, стоящий юнит своей клетки: bonusWidth = tileFoorWidth, topMargin = tileFoorHeight
CLIP_X0, CLIP_X1, CLIP_Y0, CLIP_Y1, CLIP_Y0_TOP = -16, 48, -16, 40, -32


def engine(hs_r, two_r, hs_l, two_l, aiming, d, stand_h=22):
    """Ветки drawRoutine0 по C++. -> список слоёв в порядке рисования: (имя, 'gov'|'hob', кадр, offX, offY)."""
    R = (hs_r, two_r) if hs_r is not None else None
    L = (hs_l, two_l) if hs_l is not None else None
    # sortRifles
    if R and R[1]:
        if L and L[1]:
            L = None                       # getActiveHand: считаем активной правую
        elif not aiming:
            L = None
    elif L and L[1]:
        if not aiming:
            R = None
    la, ra = LARMSTAND + d, RARMSTAND + d
    iR = iL = None
    if R:
        if aiming and R[1]:
            iR = [R[0] + (d + 2) % 8, OFFX[d], OFFY[d]]
        else:
            iR = [R[0] + d, 0, 0]
        if R[1]:
            la = LARM2H + d
            ra = (RARMSHOOT if aiming else RARM2H) + d
        else:
            ra = RARM1H + d
    if L:
        la = LARM2H + d
        iL = [L[0] + d, 0, 0]
        if not L[1]:
            iL[1], iL[2] = OFFX2[d], OFFY2[d]
        else:
            iL[1], iL[2] = 0, 0
            ra = RARM2H + d
        if aiming and L[1]:
            iL = [L[0] + (d + 2) % 8, OFFX6[d], OFFY6[d]]
            ra = RARMSHOOT + d
    for it in (iR, iL):
        if it:
            it[2] += 22 - stand_h
    two_any = bool((R and R[1]) or (L and L[1]))
    alt = (not aiming) and two_any
    seq = {0: "iR iL la lg to ra", 1: "la lg iL to iR ra", 2: "la lg to iL iR ra",
           3: "lg to la iR iL ra" if alt else "lg to la ra iR iL", 4: "lg ra to la iR iL",
           5: "ra lg to la iR iL" if alt else "ra lg iR iL to la", 6: "ra iR iL lg to la",
           7: "ra iR iL la lg to" if alt else "iR iL la ra lg to"}[d].split()
    parts = {"la": ("gov", la, 0, 0), "ra": ("gov", ra, 0, 0), "lg": ("gov", LEGS + d, 0, 0), "to": ("gov", TORSO + d, 0, 0)}
    if iR:
        parts["iR"] = ("hob", iR[0], iR[1], iR[2])
    if iL:
        parts["iL"] = ("hob", iL[0], iL[1], iL[2])
    return [(n,) + parts[n] for n in seq if n in parts]


CTX = {  # вид хвата карточки -> (правая, левая, прицел)
    "ONE": ("R1", None, False), "LEFT_ONE": (None, "L1", False),
    "TWO_STAND": ("R2", None, False), "TWO_AIM": ("R2", None, True),
    "LEFT_TWO_STAND": (None, "L2", False), "LEFT_TWO_AIM": (None, "L2", True),
    "ONE_AIM": ("R1", None, True), "LEFT_ONE_AIM": (None, "L1", True),
}


def ctx_layers(hs, case, d, stand_h=22):
    r, l, aim = CTX[case]
    return engine(hs if r else None, r == "R2", hs if l else None, l == "L2", aim, d, stand_h)


def render(layers, pad=M):
    """Индексная сборка на холсте с полями pad: (rgb, кто нарисовал пиксель)."""
    H, W = 40 + 2 * pad, 32 + 2 * pad
    rgb = np.zeros((H, W, 3), np.uint8)
    who = np.full((H, W), "", object)
    for name, src, fr, ox, oy in layers:
        idx = gm.gov(fr) if src == "gov" else gm.hob(fr)
        pal = gm.gpal if src == "gov" else gm.hpal
        ys, xs = np.nonzero(idx)
        yy, xx = ys + pad + oy, xs + pad + ox
        ok = (yy >= 0) & (yy < H) & (xx >= 0) & (xx < W)
        rgb[yy[ok], xx[ok]] = pal[idx[ys[ok], xs[ok]]]
        who[yy[ok], xx[ok]] = name
    return rgb, who


def cards_render(hs, case, d):
    """То, что рисует карточка: compose_margin без пола, в индексах -> rgb."""
    la, ra, rot, side, _ = gm.CASES[case]
    L = {"la": ("gov", la + d, 0, 0), "ra": ("gov", ra + d, 0, 0), "lg": ("gov", 16 + d, 0, 0), "to": ("gov", 32 + d, 0, 0)}
    L["iR" if side == "R" else "iL"] = ("hob", hs + (d + rot) % 8, gm.OFF[case][0][d], gm.OFF[case][1][d])
    seq = [n for n in gm.order(d, case.endswith("AIM"), case in gm.TWO_H) if n in L]
    return render([(n,) + L[n] for n in seq])[0]


def roll_render(hs, case, d):
    """Старые листы grip_matrix: 32x40, предмет сдвинут np.roll."""
    la, ra, rot, side, _ = gm.CASES[case]
    fi = hs + (d + rot) % 8
    idx = gm.hob(fi)
    ox, oy = gm.OFF[case][0][d], gm.OFF[case][1][d]
    rolled = np.roll(np.roll(idx, oy, 0), ox, 1)
    clean = gm.shifted(idx, ox, oy)
    return int(((rolled > 0) & ~(clean > 0)).sum()), rolled, clean


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    os.makedirs(OUT, exist_ok=True)
    rows = wgc.read_tsv(wgc.LIST)
    items = {r["type"]: r for r in wgc.read_tsv(wgc.ITEMS)}
    eq_rows, clip_rows = [], []
    diff = Counter()
    clip_cnt = Counter()
    left_two_stand = Counter()
    for row in rows:
        it = items.get(row["type"], {})
        two = it.get("twoHanded") == "True"
        if not (it.get("hand_default") == "False" and it.get("hand_frames") == "8"):
            continue
        hs = int(it["handSprite"])
        cases = gm.TWO_H if two else gm.ONE_H
        for d in range(8):
            for case in cases:
                a = cards_render(hs, case, d)
                b, who = render(ctx_layers(hs, case, d))
                n = int((a != b).any(-1).sum())
                diff[case, n == 0] += 1
                eq_rows.append({"master": row["master"], "type": row["type"], "handSprite": hs, "case": case, "dir": d,
                                "differs_px": n})
            # виды, которых на карточке нет
            extra = ("LEFT_TWO_STAND",) if two else ("ONE_AIM", "LEFT_ONE_AIM")
            for case in extra:
                b = render(ctx_layers(hs, case, d))[0]
                base = {"LEFT_TWO_STAND": "TWO_STAND", "ONE_AIM": "ONE", "LEFT_ONE_AIM": "LEFT_ONE"}[case]
                a = cards_render(hs, base, d)
                n = int((a != b).any(-1).sum())
                left_two_stand[case, d, n == 0] += 1
                eq_rows.append({"master": row["master"], "type": row["type"], "handSprite": hs,
                                "case": case + " (против %s карточки)" % base, "dir": d, "differs_px": n})
            # обрезка маской клетки
            for case in cases + (("LEFT_TWO_STAND",) if two else ()):
                for name, src, fr, ox, oy in ctx_layers(hs, case, d):
                    if src != "hob":
                        continue
                    ys, xs = np.nonzero(gm.hob(fr))
                    ux, uy = xs + ox, ys + oy
                    below = int((uy >= CLIP_Y1).sum())
                    side = int(((ux < CLIP_X0) | (ux >= CLIP_X1)).sum())
                    above = int((uy < CLIP_Y0).sum())
                    off_card = int(((ux < -M) | (ux >= 32 + M) | (uy < -M) | (uy >= 40 + M)).sum())
                    if below or side or above or off_card:
                        clip_cnt[case] += 1
                        clip_rows.append({"master": row["master"], "type": row["type"], "case": case, "dir": d, "frame": fr,
                                          "offX": ox, "offY": oy, "cut_below_y40": below, "cut_side": side,
                                          "cut_above_y-16": above, "outside_card_canvas": off_card})
    # рост носителя: сдвиг предмета против рук
    v = wgc.load_values()
    sh = Counter()
    for (sec, name), x in v.items():
        if sec in ("units", "soldiers") and isinstance(x.get("standHeight"), int):
            sh[(sec, x["standHeight"])] += 1
    # старые листы
    wr = []
    per = {}
    for r in wgc.read_tsv(os.path.join(wgc.GRIP, "grip_matrix.tsv")):
        per.setdefault(int(r["handSprite"]), r)
    by_two = {}
    for it in items.values():
        if it.get("hand_default") == "False" and it.get("hand_frames") == "8":
            by_two.setdefault(int(it["handSprite"]), it.get("twoHanded") == "True")
    crop_cmp = tuple(gm.CROP)
    for hs in sorted(per):
        two = by_two.get(hs, True)
        for case in (("TWO_STAND", "TWO_AIM") if two else ("ONE",)):
            n, rolled, clean = roll_render(hs, case, 2)
            if n:
                ys, xs = np.nonzero((rolled > 0) & ~(clean > 0))
                in_all = int(((xs >= 2) & (xs < 30) & (ys >= 6) & (ys < 34)).sum())
                in_cmp = int(((xs >= crop_cmp[0]) & (xs < crop_cmp[2]) & (ys >= crop_cmp[1]) & (ys < crop_cmp[3])).sum())
                wr.append({"handSprite": hs, "case": case, "dir": 2, "wrapped_px": n, "inside_all_d2_crop": in_all,
                           "inside_compare_d2_crop": in_cmp})
    for name, data in (("engine_check", eq_rows), ("clip", clip_rows), ("wrapped_old_sheets", wr)):
        with open(os.path.join(OUT, name + ".tsv"), "w", encoding=ENC, newline="") as f:
            if data:
                w = csv.DictWriter(f, list(data[0]), delimiter="\t")
                w.writeheader()
                w.writerows(data)
    print("сверка карточка = эмуляция движка (вид, совпало):", dict(diff))
    print("виды вне карточки (вид, d, совпало с видом карточки):", dict(sorted(left_two_stand.items())))
    print("обрезка/выход за холст (вид: позиций):", dict(clip_cnt))
    print("rост standHeight:", dict(sorted(sh.items())))
    print("старые листы, d=2, перенесённые пиксели: позиций %d, из них видны в обрезке all_d2 %d, compare_d2 %d" % (
        len(wr), sum(r["inside_all_d2_crop"] > 0 for r in wr), sum(r["inside_compare_d2_crop"] > 0 for r in wr)))


if __name__ == "__main__":
    main()
