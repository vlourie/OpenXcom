"""Проверочная сцена для групп пола без сейва (no_save в очереди floor_batch).

Копия ровного сейва боя, где на нулевом этаже выложены пятна patch x patch клеток каждой группы (запись MCD,
которая рисует её кадр первым), между пятнами - полоса gap клеток одного нейтрального пола. Над пятнами и
полосами всё снято: стены и предмет нулевого этажа, все этажи выше; дым и огонь снимает floor_batch
(game_save -> map_screen_check.prep). Слоты рядом с юнитами и предметами на полу пропускаются - их не трогаем.

Наборы групп дописываются в mapdatasets сейва: игра грузит их по имени (SavedBattleGame::load ->
Mod::getMapDataSet, loadMapResources). Записи с анимацией (Frame[0..7] не все равны) не выкладываются -
петля только целиком (R-071); кадр, который не стоит первым ни в одной записи, - тоже.
enviroEffectsType снимается (--keep-env оставить): подмена палитры боя красит HD сеткой сдвигов (R-314, R-267).

    py -3.13 tools/hdart/floor_scene.py --base mars_cydonia_landing_mars_9996.asav --out scene_nosave_1.asav
    py -3.13 tools/hdart/floor_batch.py index              # сцена попадает в индекс как обычный сейв
Сцена лежит в art/ground/queue/saves, раскладка слотов - рядом, <имя>.json.
"""
import argparse
import base64
import collections
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import floor_batch as fb        # noqa: E402
import map_screen_check as msc  # noqa: E402
import map_truth as mt          # noqa: E402


def pick_records(D, groups, q):
    """Группа -> (набор, запись): статичная запись пола, у которой Frame[0] - кадр группы или её копии."""
    out, skipped = {}, {}
    for g in groups:
        r = q[g]
        best = None
        for m in [g] + [m for m in r["копии"].split(",") if m]:
            s, f = m.split(":")
            for i, rc in enumerate(D.mcd(s)):
                if rc["frames"][0] != int(f) or rc["type"] != 0:
                    continue
                cand = (len(set(rc["frames"])) == 1, m == g, -i, s, i)
                if best is None or cand > best:
                    best = cand
        if best is None:
            skipped[g] = "нет записи пола с этим кадром первым (кадр только внутри петли анимации, R-071)"
        elif not best[0]:
            skipped[g] = "запись с анимацией - петля только целиком (R-071)"
        else:
            out[g] = (best[3], best[4])
    return out, skipped


def write_tiles(text, bt, ID, SET, keep):
    """binTiles заново: каждая клетка, где есть хоть одна часть или которая была в сейве. Формат - Tile::saveBinary."""
    i = text.find("\nbattleGame:\n")
    bg = text[i:]
    sz = {k: mt.Battle._size(bg, k) for k in ("tileIndexSize", "tileTotalBytesPer", "tileFireSize", "tileSmokeSize",
                                              "tileIDSize", "tileSetIDSize", "tileBoolFieldsSize")}
    if sz["tileIDSize"] != 2 or sz["tileSetIDSize"] != 2 or sz["tileBoolFieldsSize"] != 1:
        raise SystemExit("формат клетки не тот, что ждали: %s" % sz)
    per = sz["tileTotalBytesPer"]
    known = sz["tileIndexSize"] + 8 * 2 + sz["tileSmokeSize"] + sz["tileFireSize"] + 1
    if per < known:
        raise SystemExit("tileTotalBytesPer %d меньше полей %d" % (per, known))
    out = bytearray()
    n = 0
    Z, Y, X = bt.Z, bt.Y, bt.X
    for z in range(Z):
        for y in range(Y):
            for x in range(X):
                if not (keep[z, y, x] or (SET[z, y, x] >= 0).any()):
                    continue
                rec = bytearray(per)
                q = 0
                idx = (z * Y + y) * X + x
                rec[q:q + sz["tileIndexSize"]] = idx.to_bytes(sz["tileIndexSize"], "little")
                q += sz["tileIndexSize"]
                for v in list(ID[z, y, x]) + list(SET[z, y, x]):
                    rec[q:q + 2] = int(v).to_bytes(2, "little", signed=True)
                    q += 2
                rec[q:q + sz["tileSmokeSize"]] = int(bt.smoke[z, y, x]).to_bytes(sz["tileSmokeSize"], "little")
                q += sz["tileSmokeSize"]
                rec[q:q + sz["tileFireSize"]] = int(bt.fire[z, y, x]).to_bytes(sz["tileFireSize"], "little")
                q += sz["tileFireSize"]
                rec[q] = int(bt.flags[z, y, x])
                out += rec
                n += 1
    m = re.search(r"^  binTiles: (\S+)$", text, re.M)
    text = text[:m.start(1)] + base64.b64encode(bytes(out)).decode() + text[m.end(1):]
    text, k = re.subn(r"(?m)^  totalTiles: \d+$", "  totalTiles: %d" % n, text)
    if k != 1:
        raise SystemExit("totalTiles: %d мест" % k)
    return text, n


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True, help="сейв из art/ground/queue/saves")
    p.add_argument("--out", required=True)
    p.add_argument("--groups", default="", help="через запятую; по умолчанию все no_save очереди")
    p.add_argument("--patch", type=int, default=4)
    p.add_argument("--gap", type=int, default=1)
    p.add_argument("--margin", type=int, default=2, help="столько клеток от юнитов и предметов на полу не трогать")
    p.add_argument("--keep-env", action="store_true")
    a = p.parse_args()
    q = fb.load_queue()
    groups = [g for g in a.groups.split(",") if g] or sorted(
        (g for g, r in q.items() if r["статус"] == "no_save"), key=lambda g: -int(q[g]["клеток"]))
    src = fb.SAVES / a.base
    bt = mt.Battle(str(src))
    D = mt.Data(bt.mods)
    recs, skipped = pick_records(D, groups, q)
    # нейтральный пол полос - самый частый пол нулевого этажа сейва
    cnt = collections.Counter((int(bt.SET[0, y, x, 0]), int(bt.ID[0, y, x, 0])) for y in range(bt.Y)
                              for x in range(bt.X) if bt.SET[0, y, x, 0] >= 0)
    gap_floor = cnt.most_common(1)[0][0]
    us, _sel = msc.units(str(src))
    stop = {(x, y) for _u, (x, y, _z), _f in us if x >= 0}
    stop |= {(x, y) for x, y, _z in msc.floor_items(str(src))}
    blocked = np.zeros((bt.Y, bt.X), bool)
    for x, y in stop:
        blocked[max(0, y - a.margin):y + a.margin + 1, max(0, x - a.margin):x + a.margin + 1] = True
    pitch = a.patch + a.gap
    slots = [(x0, y0) for y0 in range(a.gap, bt.Y - pitch + 1, pitch) for x0 in range(a.gap, bt.X - pitch + 1, pitch)
             if not blocked[y0 - a.gap:y0 + a.patch + a.gap, x0 - a.gap:x0 + a.patch + a.gap].any()]
    put = list(recs.items())
    if len(put) > len(slots):
        for g, _r in put[len(slots):]:
            skipped[g] = "в сцене не хватило слотов (%d)" % len(slots)
        put = put[:len(slots)]
    sets = list(bt.sets)
    for s, _i in recs.values():
        if s not in sets:
            sets.append(s)
    ID, SET = bt.ID.copy(), bt.SET.copy()
    keep = SET.max(axis=3) >= 0
    layout = {}
    for (g, (s, i)), (x0, y0) in zip(put, slots):
        ys, xs = slice(y0 - a.gap, y0 + a.patch + a.gap), slice(x0 - a.gap, x0 + a.patch + a.gap)
        ID[:, ys, xs], SET[:, ys, xs] = -1, -1                      # всё над слотом и вокруг пятна снять
        SET[0, ys, xs, 0], ID[0, ys, xs, 0] = gap_floor
        SET[0, y0:y0 + a.patch, x0:x0 + a.patch, 0] = sets.index(s)
        ID[0, y0:y0 + a.patch, x0:x0 + a.patch, 0] = i
        layout[g] = {"set": s, "rec": i, "x": x0, "y": y0, "patch": a.patch}
    text = src.read_text(encoding="utf-8")
    i = text.find("\n  mapdatasets:\n")
    j = i + len("\n  mapdatasets:\n")
    while text.startswith("    - ", j):
        j = text.index("\n", j) + 1
    text = text[:i] + "\n  mapdatasets:\n" + "".join("    - %s\n" % s for s in sets) + text[j:]
    text, n = write_tiles(text, bt, ID, SET, keep)
    if not a.keep_env:
        text, k = re.subn(r"(?m)^  enviroEffectsType: .*\n", "", text)
        print("enviroEffectsType снят: %d" % k)
    out = fb.SAVES / a.out
    out.write_text(text, encoding="utf-8")
    # проверка чтением: каждая группа на своём месте
    chk = mt.Battle(str(out))
    bad = [g for g, v in layout.items()
           if chk.sets[chk.SET[0, v["y"], v["x"], 0]] != v["set"] or chk.ID[0, v["y"], v["x"], 0] != v["rec"]
           or (chk.SET[1:, v["y"]:v["y"] + a.patch, v["x"]:v["x"] + a.patch] >= 0).any()]
    if bad:
        raise SystemExit("после записи не на месте: %s" % bad[:10])
    (fb.SAVES / (Path(a.out).stem + ".json")).write_text(json.dumps(
        {"base": a.base, "gap_floor": [sets[gap_floor[0]], gap_floor[1]], "layout": layout, "skipped": skipped},
        ensure_ascii=False, indent=1), encoding="utf-8-sig")
    print("сцена %s: клеток %d, наборов %d (+%d), слотов %d, выложено групп %d, пропущено %d"
          % (out.name, n, len(sets), len(sets) - len(bt.sets), len(slots), len(layout), len(skipped)))
    for g, w in sorted(skipped.items()):
        print("  пропущено %-24s %s" % (g, w))


if __name__ == "__main__":
    main()
