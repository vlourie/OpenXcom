#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пак «Живой базы» (docs/research/base-living-2026-10-22.md, раздел 7а): новые картинки построек по клеткам
и файл сцены каждой клетки для HdBaseScene.

На клетку N (кадр BASEBITS, как BaseView::hdTileIndex) пишутся:
    <N>.png          картинка клетки 128x128 (k = 4), альфа - силуэт классики
    <N>.scene.txt    сцена: что за постройка и огни, центры которых лежат в этой клетке

    # base_scene_pack.py
    size 128 128                   размер картинки клетки в паке
    gate lab                      от чего горит: lab (учёные), work (инженеры), home (жильё гаснет ночью), none
    light 61.5 40.2 38.0 screen 0.45 0.85 1.00 1.70 0.31
          x y (пиксели пака от угла клетки, могут выходить за клетку), радиус, вид (steady, blink, pulse,
          screen, flicker), цвет 0..1, период с и фаза 0..1 (у blink и pulse; у прочих 0 0)

Огни ищет base_lights.py по картинке 512 на клетку (art/base_living/pilot/painted/<ТИП>@512.png).
Старые .anim.txt и фазы .v/.b движок у клетки со сценой не берёт (HdBase), поэтому их не трогаем.

В мод не пишет: выход в --out (по умолчанию art/base_living/pack), ставить - build_hd_pack (stage + install)
под очередью правок, и только постройки, выбранные Vitali (--only).

    py -3.13 tools/hdart/base_scene_pack.py --only STR_ACCESS_LIFT,STR_HANGAR
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

import base_lights                                  # noqa: E402
from facility_sheet import load_rules, sprites_map  # noqa: E402
from gen_base_anim import Facility                  # noqa: E402

ART = os.path.join(ROOT, "art", "base_living", "pilot", "painted")
TILE = 128
ENC = "utf-8-sig"


def gate_of(rule):
    """От чего горит постройка - по тому, что она даёт базе (рулсет), а не по имени."""
    # лаборатория и мастерская - где это главное дело постройки, а не пара мест в придачу (лазарет - 1 учёный,
    # склад - 5 мест, хеллерий - 3 учёных при 75 рабочих); поле рулсета - labs (RuleBaseFacility)
    if int(rule.get("labs", 0) or 0) >= 10:
        return "lab"
    if int(rule.get("workshops", 0) or 0) >= 20:
        return "work"
    if int(rule.get("personnel", 0) or 0) > 0:
        return "home"
    return "none"


def budget(lights, cover, most):
    """Бюджет огней клетки: светлую мебель детектор берёт за лампы и ночью заливает комнату как днём (лист
    ночи 98, 22.10). Огни идут от крупных к мелким; берём, пока сумма r^2 не выйдет за cover клетки и их не
    больше most. Одобренные 16 почти все укладываются в 0.6 и 6 (кроме хеллерия - он светится задуманно)."""
    keep, s = [], 0.0
    for L in lights:
        r = float(L.split()[3]) / TILE
        if len(keep) >= most or (keep and s + r * r > cover):
            continue
        keep.append(L)
        s += r * r
    return keep


# Частицы построек (HdBaseScene::drawParticles), доли постройки u0 v0 u1 v1 по листу emit_sheet.png 22.10, цвет
# 0..1. Искры горят, только пока мастерская работает (gate work), пар тонируется светом комнаты.
EMITS = {
    "STR_ONSEN": [("steam", .15, .20, .60, .75, .95, .95, 1.0)],
    "STR_LUXURY_SPA": [("steam", .30, .30, .68, .72, .85, .90, .95)],
    "STR_HOTEL": [("steam", .60, .58, .78, .78, .95, .95, 1.0)],
    "STR_HELLERIUM_PLANT": [("bubbles", .36, .30, .60, .54, .60, 1.0, .30)],
    "STR_SLUDGE_VATS": [("bubbles", u - .07, v - .07, u + .07, v + .07, .65, 1.0, .25)
                        for u, v in ((.30, .27), (.65, .27), (.30, .63), (.65, .63))],
    "STR_WELL": [("bubbles", .41, .36, .65, .60, .65, 1.0, .30)],
    "STR_WORKSHOP": [("sparks", .38, .40, .62, .64, 1.0, .75, .35)],
    "STR_FACTORY": [("sparks", .25, .28, .55, .55, 1.0, .75, .35), ("sparks", .50, .55, .80, .85, 1.0, .75, .35)],
    "STR_INDUSTRIAL_PRINTER": [("sparks", .12, .22, .45, .50, .55, .80, 1.0),
                               ("sparks", .45, .55, .80, .85, .55, .80, 1.0)],
    "STR_RED_FORGE": [("sparks", .25, .38, .42, .55, 1.0, .65, .25), ("embers", .22, .35, .45, .58, 1.0, .45, .15)],
    "STR_STILL": [("steam", .20, .22, .65, .36, .95, .92, .85)],
    "STR_MESS_HALL": [("steam", .38, .36, .62, .62, .95, .92, .88)],
    "STR_BURROW": [("embers", .45, .40, .55, .50, 1.0, .55, .20)],
    "STR_SUMMONING_CIRCLE": [("orbit", .22, .16, .82, .76, 1.0, .40, .15)],
}
# Огни, которых детектор не видит: сердце реактора, руна круга (u v, радиус в долях, вид, цвет, период)
LIGHTS = {
    "STR_FUSION_REACTOR": [(.48, .50, .45, "pulse", 1.0, .55, .15, 2.6)],
    "STR_SUMMONING_CIRCLE": [(.52, .46, .48, "pulse", 1.0, .35, .15, 3.2), (.52, .46, .31, "flicker", 1.0, .62, .30, 0)],
}


def extra_lines(t, cols, rows):
    """Ручные строки сцены (emit и light) по клеткам {(cx, cy): [строки]}: строка идёт в клетку, где лежит
    центр коробки или огня; координаты от угла этой клетки, за край клетки выходить могут."""
    W, H = cols * TILE, rows * TILE
    out = {}

    def tile(x, y):
        cx, cy = min(cols - 1, int(x // TILE)), min(rows - 1, int(y // TILE))
        return (cx, cy), x - cx * TILE, y - cy * TILE

    for kind, u0, v0, u1, v1, r, g, b in EMITS.get(t, []):
        key, x, y = tile((u0 + u1) / 2 * W, (v0 + v1) / 2 * H)
        w, h = (u1 - u0) * W, (v1 - v0) * H
        out.setdefault(key, []).append("emit %s %.1f %.1f %.1f %.1f %.2f %.2f %.2f" %
                                       (kind, x - w / 2, y - h / 2, w, h, r, g, b))
    for u, v, rad, kind, r, g, b, period in LIGHTS.get(t, []):
        key, x, y = tile(u * W, v * H)
        out.setdefault(key, []).append("light %.1f %.1f %.1f %s %.2f %.2f %.2f %.2f %.2f" %
                                       (x, y, rad * min(W, H), kind, r, g, b, period, 0.0))
    return out


def build(t, rule, sprites, out, cover=0.0, most=0):
    fac = Facility(rule, sprites)
    pic = os.path.join(ART, t + ".png")
    master = os.path.join(ART, t + "@512.png")
    if fac.missing or not os.path.exists(pic) or not os.path.exists(master):
        print("!! %s: нет картинки или кадров" % t)
        return []
    im = np.asarray(Image.open(pic).convert("RGBA"))
    if im.shape[:2] != (fac.rows * TILE, fac.cols * TILE):
        print("!! %s: размер %s, ждали %dx%d" % (t, im.shape[:2], fac.cols * TILE, fac.rows * TILE))
        return []
    found = base_lights.lights(np.asarray(Image.open(master).convert("RGBA")), fac.cols, fac.rows)
    gate = gate_of(rule)
    per_tile = {}
    for u, v, kind, col, rad, _area in found:
        x, y = u * fac.cols * TILE, v * fac.rows * TILE
        cx, cy = min(fac.cols - 1, int(x // TILE)), min(fac.rows - 1, int(y // TILE))
        # жильё и нора - лампы ровные и гаснут ночью; огонь в норе, онсэне и круге - пламя
        if kind == "steady" and t in ("STR_BURROW", "STR_ONSEN", "STR_SUMMONING_CIRCLE"):
            kind = "flicker"
        period = phase = 0.0
        if kind in ("blink", "pulse"):
            period, phase = 1.4 + (u * 7 + v * 3) % 1.2, (u * 13 + v * 5) % 1
        per_tile.setdefault((cx, cy), []).append(
            "light %.1f %.1f %.1f %s %.2f %.2f %.2f %.2f %.2f" %
            (x - cx * TILE, y - cy * TILE, rad * TILE, kind, col[0], col[1], col[2], period, phase))
    dest = os.path.join(out, "hd", "BASEBITS.PCK")
    os.makedirs(dest, exist_ok=True)
    written = []
    extra = extra_lines(t, fac.cols, fac.rows)
    num = 0
    for cy in range(fac.rows):
        for cx in range(fac.cols):
            n = fac.indices[num]
            tile = im[cy * TILE:(cy + 1) * TILE, cx * TILE:(cx + 1) * TILE]
            Image.fromarray(tile, "RGBA").save(os.path.join(dest, "%d.png" % n), optimize=True)
            here = per_tile.get((cx, cy), [])
            if most:
                here = budget(here, cover, most)
            lines = (["# base_scene_pack.py %s %d,%d" % (t, cx, cy), "size %d %d" % (TILE, TILE), "gate " + gate]
                     + here + extra.get((cx, cy), []))
            with open(os.path.join(dest, "%d.scene.txt" % n), "w", encoding="ascii", newline="\n") as f:
                f.write("\n".join(lines) + "\n")
            written += ["BASEBITS.PCK/%d.png" % n, "BASEBITS.PCK/%d.scene.txt" % n]
            num += 1
    print("%-30s %dx%d  огней %2d  gate %s  кадры %s" % (t, fac.cols, fac.rows, len(found), gate, fac.indices))
    return written


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", required=True, help="типы через запятую (только выбранные Vitali)")
    ap.add_argument("--out", default=os.path.join(ROOT, "art", "base_living", "pack"))
    ap.add_argument("--cover", type=float, default=0.6, help="бюджет клетки: сумма r^2 в долях клетки")
    ap.add_argument("--most", type=int, default=0, help="не больше огней на клетку (0 - без бюджета, как у 16)")
    ns = ap.parse_args()
    rules, _ = load_rules()
    sprites = sprites_map()
    files = []
    for t in [s for s in ns.only.split(",") if s]:
        files += build(t, rules[t], sprites, ns.out, ns.cover, ns.most)
    with open(os.path.join(ns.out, "files.txt"), "w", encoding=ENC) as f:
        f.write("\n".join(files) + "\n")
    print("файлов %d -> %s" % (len(files), ns.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
