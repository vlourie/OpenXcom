#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""map_screen_check.py - карта боя из сейва против кадра самой игры: якоря, высоты, порядок рисования.

Зачем. map_truth.py сверяет клетки сейва с тем, как их кладёт загрузка блоков. Здесь вторая
половина цепочки: клетки сейва -> кадры PCK -> экран. Классический кадр карты собирается по
клеткам сейва так же, как его рисует Map::drawTerrain, и сравнивается с дампом карты игры
(Ctrl+F8, hdtestNNN_map.png) на том же месте камеры.

Сверено с кодом, не по памяти:
  * экран клетки: x = (mx - my)*16, y = (mx + my)*8 - mz*24 плюс сдвиг камеры
    (Camera::convertMapToScreen, cameraOffsetX/Y из json дампа);
  * границы обхода - Camera::convertScreenToMap от углов поверхности, деление с отсечением к нулю,
    уровни до cameraOffsetZ (вид не «все уровни»);
  * в клетке: пол, стена З, стена С (если есть стена З - только правая половина кадра,
    Surface::blitRaw half), объект; кадр поднят на P_Level (байт 49 MCD);
  * кадр записи - Frame[currentFrame]; после заморозки дампа currentFrame = 0, кроме дверей НЛО,
    у них 7, если флаг открытой двери в сейве (Tile::hdTestResetAnimation, Tile::loadBinary);
  * индекс 0 прозрачен; свет выключен копией сейва (toggleBrightness 2: Map::reShade отдаёт 0),
    все клетки открыты (флаги discovered) - тогда игра рисует индексы как есть.
Юниты, предметы на полу, дым, огонь и курсор здесь не рисуются: они остаются отдельным классом
расхождений и показываются на листе.

    py -3.13 tools\hdart\map_screen_check.py prep <сейв> --out <копия.sav>
    py -3.13 tools\hdart\map_screen_check.py compare <копия.sav> <hdtestNNN> --out <папка>
"""
import argparse
import base64
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import map_truth as mt          # noqa: E402
import xcom_sprites as xs       # noqa: E402

ENC = "utf-8-sig"
SW, SH = 32, 40                 # кадр террейна при k = 1


def tdiv(a, b):
    """Целочисленное деление C++ (к нулю), а не питоновское (к минус бесконечности)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


# ------------------------------------------------------------------ копия сейва

def prep(src, out, center=None, clear_smoke=False):
    """Копия сейва: все клетки открыты, свет боя выключен (toggleBrightness 2), ночное зрение выкл.
    clear_smoke - дым и огонь клеток обнулены: они рисуются поверх террейна и прячут разрушенное.
    center (x, y, z) - выбранный юнит переставлен на эту клетку: камера дампа встаёт на него,
    так в кадр попадает нужное место карты (стык блоков). Клетка обязана быть пустой - без юнита."""
    text = Path(src).read_text(encoding="utf-8")
    bt = mt.Battle(src)
    if center:
        us, sel = units(src)
        busy = [uid for uid, p, _f in us if p == tuple(center) and uid != sel]
        if busy:
            raise SystemExit("клетка %s занята юнитом %s" % (center, busy))
        i = text.find("\nbattleGame:\n")
        j = text.find("\n  units:\n", i)
        m = re.compile(r"^    - id: %d\n((?:      .*\n)+)" % sel, re.M).search(text, j)
        p = re.search(r"^      position: \[[^\]]*\]", m.group(1), re.M)
        a, b = m.start(1) + p.start(), m.start(1) + p.end()
        text = text[:a] + "      position: [%d, %d, %d]" % tuple(center) + text[b:]
        print("юнит %d переставлен на %s, части клетки: %s"
              % (sel, center, [bt.part(center[2], center[1], center[0], q) for q in range(4)]))
    i = text.find("\nbattleGame:\n")
    bg = text[i:]
    sizes = {k: mt.Battle._size(bg, k) for k in ("tileIndexSize", "tileTotalBytesPer", "tileFireSize",
                                                 "tileSmokeSize", "tileIDSize", "tileSetIDSize",
                                                 "tileBoolFieldsSize")}
    m = re.search(r"^  binTiles: (\S+)$", text, re.M)
    raw = bytearray(base64.b64decode(m.group(1)))
    per = sizes["tileTotalBytesPer"]
    at = per - sizes["tileBoolFieldsSize"]
    if sizes["tileBoolFieldsSize"] != 1:
        raise SystemExit("флаги клетки не в одном байте: %d" % sizes["tileBoolFieldsSize"])
    # дым и огонь: после индекса, 4 номеров MCD и 4 номеров наборов (Tile::loadBinary)
    sm_at = sizes["tileIndexSize"] + 4 * sizes["tileIDSize"] + 4 * sizes["tileSetIDSize"]
    cleared = 0
    for t in range(bt.total_tiles):
        raw[t * per + at] |= 7          # discovered: стена З 1, стена С 2, пол 4 (Tile::loadBinary)
        if clear_smoke:
            span = slice(t * per + sm_at, t * per + sm_at + sizes["tileSmokeSize"] + sizes["tileFireSize"])
            cleared += any(raw[span])
            raw[span] = bytes(span.stop - span.start)
    if clear_smoke:
        print("дым и огонь сняты с %d клеток" % cleared)
    text = text[:m.start(1)] + base64.b64encode(bytes(raw)).decode() + text[m.end(1):]
    text, n1 = re.subn(r"(?m)^(\s*)toggleBrightness: \d+$", r"\g<1>toggleBrightness: 2", text)
    text, n2 = re.subn(r"(?m)^(\s*)toggleNightVision: \w+$", r"\g<1>toggleNightVision: false", text)
    Path(out).write_text(text, encoding="utf-8")
    print("копия %s: клеток %d открыто, toggleBrightness %d мест, toggleNightVision %d мест"
          % (out, bt.total_tiles, n1, n2))


def units(path):
    """(id, позиция, сторона) юнитов боя и выбранный юнит - туда игра ставит камеру при загрузке."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    bg = text[text.find("\nbattleGame:\n"):]
    sel = re.search(r"^  selectedUnit: (-?\d+)", bg, re.M)
    res = []
    for m in re.finditer(r"^    - id: (\d+)\n((?:      .*\n)+)", bg[bg.find("\n  units:\n"):], re.M):
        body = m.group(2)
        p = re.search(r"^      position: \[(-?\d+), ?(-?\d+), ?(-?\d+)\]", body, re.M)
        f = re.search(r"^      faction: (\d+)", body, re.M)
        if p:
            res.append((int(m.group(1)), tuple(int(v) for v in p.groups()), int(f.group(1)) if f else -1))
    return res, int(sel.group(1)) if sel else None


def unit_status(path):
    """id -> status юнита (6 мёртв, 7 без сознания: на карте лежит предмет-тело, юнит не рисуется)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    bg = text[text.find("\nbattleGame:\n"):]
    out = {}
    for m in re.finditer(r"^    - id: (\d+)\n((?:      .*\n)+)", bg[bg.find("\n  units:\n"):], re.M):
        s = re.search(r"^      status: (\d+)", m.group(2), re.M)
        out[int(m.group(1))] = int(s.group(1)) if s else 0
    return out


def floor_items(path):
    """Клетки, где лежат предметы (без владельца, с position) - Map::drawTerrain рисует верхний из них."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    bg = text[text.find("\nbattleGame:\n"):]
    i = bg.find("\n  items:\n")
    body = bg[i:]
    j = re.search(r"\n  [A-Za-z]", body[10:])
    body = body[:10 + j.start()] if j else body
    cells = set()
    for m in re.finditer(r"^    - id: \d+\n((?:      .*\n)+)", body, re.M):
        b = m.group(1)
        if "\n      owner:" in "\n" + b:
            continue
        p = re.search(r"^      position: \[(-?\d+), ?(-?\d+), ?(-?\d+)\]", b, re.M)
        if p and int(p.group(1)) >= 0:
            cells.add(tuple(int(v) for v in p.groups()))
    return cells


# ------------------------------------------------------------------ рисование

class Frames:
    def __init__(self, data):
        self.data = data
        self._pck = {}

    def frame(self, set_name, i):
        if set_name not in self._pck:
            p = self.data.find("TERRAIN/%s.PCK" % set_name)
            t = self.data.find("TERRAIN/%s.TAB" % set_name)
            fr = xs.read_pck(str(p), str(t) if t else None) if p else []
            self._pck[set_name] = [None if f is None else np.array(f, np.uint8).reshape(SH, SW) for f in fr]
        fr = self._pck[set_name]
        return fr[i] if 0 <= i < len(fr) else None


def sprite(bt, data, frames, z, y, x, p):
    cur = bt.part(z, y, x, p)
    if cur is None:
        return None, 0
    sid, mid = cur
    name = bt.sets[sid]
    recs = data.mcd(name)
    if mid >= len(recs):
        return None, 0
    r = recs[mid]
    cf = 0
    if r["ufo_door"] and p in (1, 2) and bt.flags[z, y, x] & (8 if p == 1 else 0x10):
        cf = 7
    return frames.frame(name, r["frames"][cf]), r["yoff"]


def blit(img, owner, spr, sx, sy, half, tag):
    h, w = spr.shape
    x0 = w // 2 if half else 0
    for yy in range(h):
        Y = sy + yy
        if Y < 0 or Y >= img.shape[0]:
            continue
        row = spr[yy]
        for xx in range(x0, w):
            v = row[xx]
            if not v:
                continue
            X = sx + xx
            if 0 <= X < img.shape[1]:
                img[Y, X] = v
                owner[Y, X] = tag


def render(bt, data, cam, W, H, breaks=()):
    """Индексы карты k = 1 и чья это точка (номер клетки*4 + часть + 1, 0 - пусто).
    breaks - контрольный опыт (R-086): нарочно неверное правило, сверка обязана его поймать:
    yoff - без P_Level, half - стена С целиком при стене З, order - объект раньше стен;
    pristine (в compare) - карта из MAP без дверей и разрушений сейва."""
    frames = Frames(data)
    img = np.zeros((H, W), np.uint8)
    owner = np.zeros((H, W), np.int64)
    cx, cy, cz = cam

    def s2m(sx, sy):
        sy += -SW // 2 + cz * ((SH + SW // 4) // 2)
        my = -sx + cx + 2 * sy - 2 * cy
        mx = sy - cy - tdiv(my, 4) - SW // 4
        mx, my = tdiv(mx, SW // 4), tdiv(my, SW)
        return max(-1, min(mx, bt.X)), max(-1, min(my, bt.Y))

    bx, _ = s2m(0, 0)
    _, by = s2m(W, 0)
    ex, _ = s2m(W + SW, H + SH)
    _, ey = s2m(0, H + SH)
    bx, by = max(0, bx - cz * 2), max(0, by - cz * 2)
    ex, ey = min(ex, bt.X), min(ey, bt.Y)
    for z in range(0, min(cz, bt.Z - 1) + 1):
        for y in range(by, ey):
            for x in range(bx, ex):
                px = x * 16 - y * 16 + cx
                py = x * 8 + y * 8 - z * 24 + cy
                if not (-SW < px < W + SW and -SH < py < H + SH):
                    continue
                base = ((z * bt.Y + y) * bt.X + x) * 4 + 1
                west = sprite(bt, data, frames, z, y, x, 1)[0]
                for p in ((0, 3, 1, 2) if "order" in breaks else range(4)):
                    spr, yoff = sprite(bt, data, frames, z, y, x, p)
                    if spr is None:
                        continue
                    if "yoff" in breaks:
                        yoff = 0
                    half = p == 2 and west is not None and "half" not in breaks
                    blit(img, owner, spr, px, py - yoff, half, base + p)
    return img, owner


# ------------------------------------------------------------------ сверка

def compare(save, prefix, out, breaks=()):
    js = json.loads(Path(prefix + ".json").read_text(encoding="utf-8-sig"))
    k = int(js["k"])
    W, H = int(js["mapSurfaceWidth"]) // k, int(js["mapSurfaceHeight"]) // k
    cam = (int(js["cameraOffsetX"]) // k, int(js["cameraOffsetY"]) // k, int(js["cameraOffsetZ"]))
    game = np.asarray(Image.open(prefix + "_map.png").convert("RGB"))[::k, ::k][:H, :W]
    bt = mt.Battle(save)
    data = mt.Data(bt.mods)
    if "pristine" in breaks:
        # контроль состояний: рисуем карту, как её положил MAP, без открытых дверей и разрушений
        import copy
        rb0, _i0 = mt.rebuild(bt, data)
        drawbt = copy.copy(bt)
        drawbt.SET, drawbt.ID = rb0.SET, rb0.ID
        img, owner = render(drawbt, data, cam, W, H, breaks)
    else:
        img, owner = render(bt, data, cam, W, H, breaks)
    # что рисует игра поверх террейна и чего нет у нас: юниты, предметы на полу, дым и огонь,
    # облако пара заморозки дампа (Map::hdTestFreeze: клетки (x + 2y) % 3 == 0 уровня камеры)
    def box(x, y, z, l, t, r, b):
        px = x * 16 - y * 16 + cam[0]
        py = x * 8 + y * 8 - z * 24 + cam[1]
        m = np.zeros((H, W), bool)
        m[max(0, py + t):max(0, min(H, py + b)), max(0, px + l):max(0, min(W, px + r))] = True
        return m

    st = unit_status(save)
    us, _sel = units(save)
    masks = {k2: np.zeros((H, W), bool) for k2 in ("unit", "item", "smoke_fire", "vapor")}
    for uid, (x, y, z), _f in us:
        if x < 0 or st.get(uid, 0) in (6, 7) or z > cam[2]:
            continue
        for dx in (0, 1):
            for dy in (0, 1):
                masks["unit"] |= box(x - dx, y - dy, z, -8, -32, 40, 44)
    for x, y, z in floor_items(save):
        if z <= cam[2]:
            masks["item"] |= box(x, y, z, 0, -8, 32, 44)
    for z, y, x in zip(*np.nonzero((bt.smoke > 0) | (bt.fire > 0))):
        if z <= cam[2]:
            masks["smoke_fire"] |= box(x, y, z, -4, -16, 36, 44)
    # клубок - квадрат 2x2 (Map.cpp pixelMaskBase); место - Particle::updateScreenPosition от вокселя
    # 2+4*(n%4), 2+4*(n/4), 4+6*(n%3) внутри клетки, начало - экранная точка клетки + (16, 24)
    for y in range(bt.Y):
        for x in range(bt.X):
            if (x + 2 * y) % 3 == 0:
                for n in range(16):
                    vx, vy, vz = 2 + 4 * (n % 4), 2 + 4 * (n // 4), 4 + 6 * (n % 3)
                    ox, oy = 16 + vx - vy, 24 + vx // 2 + vy // 2 - vz
                    masks["vapor"] |= box(x, y, cam[2], ox, oy, ox + 2, oy + 2)
    covered = np.zeros((H, W), bool)
    for m in masks.values():
        covered |= m
    # палитру не угадываем: индекс -> цвет по большинству точек, где индекс нарисован и ничем не закрыт
    # (редкий индекс под юнитом или паром иначе получает чужой цвет); закрыт везде - по всем точкам
    key = game[..., 0].astype(np.int64) << 16 | game[..., 1].astype(np.int64) << 8 | game[..., 2]
    pal = {}
    for i in np.unique(img):
        sel = (img == i) & ~covered
        c = Counter(key[sel if sel.any() else img == i].tolist())
        pal[int(i)] = c.most_common(1)[0][0]
    pred = np.vectorize(pal.get)(img)
    bad = pred != key
    drawn = img > 0
    # палитра обязана быть взаимно однозначной, иначе «по большинству» прячет ошибку
    clash = Counter(pal.values())
    shared = [(i, c) for i, c in pal.items() if clash[c] > 1]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(prefix).name
    vis = np.zeros((H, W * 3, 3), np.uint8)
    vis[:, :W] = game
    lut = np.zeros((256, 3), np.uint8)
    for i, c in pal.items():
        lut[i] = ((c >> 16) & 255, (c >> 8) & 255, c & 255)
    vis[:, W:2 * W] = lut[img]
    d = game.copy() // 3
    d[bad] = (255, 0, 64)
    vis[:, 2 * W:] = d
    Image.fromarray(vis).resize((W * 3 * 2, H * 2), Image.NEAREST).save(out / (stem + "_check.png"))
    left = bad.copy()
    why = {}
    for k2 in ("unit", "item", "smoke_fire", "vapor"):
        why[k2] = int((left & masks[k2]).sum())
        left &= ~masks[k2]
    why["unexplained"] = int(left.sum())
    why["tested_pixels"] = int((drawn & ~covered).sum())
    why["tested_parts"] = int(len(np.unique(owner[drawn & ~covered])))
    # что именно проверено: по блокам и по клеткам у стыка двух разных блоков (сосед по x или y - чужой блок)
    blocks, special, _pr = mt.layout(bt, data)
    inst = np.full((bt.X, bt.Y), -1, int)
    names = []
    for i, b in enumerate(blocks + special):
        names.append(b["name"])
        inst[b["cx"] * 10:(b["cx"] + b["w"]) * 10, b["cy"] * 10:(b["cy"] + b["h"]) * 10] = i
    by_block, by_border = Counter(), Counter()
    for t in owner[drawn & ~covered].tolist():
        q = (t - 1) // 4
        _z, r = divmod(q, bt.X * bt.Y)
        y, x = divmod(r, bt.X)
        me = inst[x, y]
        by_block[names[me] if me >= 0 else "?"] += 1
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            X, Y = x + dx, y + dy
            if 0 <= X < bt.X and 0 <= Y < bt.Y and inst[X, Y] != me and me >= 0 and inst[X, Y] >= 0:
                by_border["|".join(sorted((names[me], names[inst[X, Y]])))] += 1
                break
    why["tested_by_block"] = dict(by_block.most_common())
    why["tested_on_border"] = dict(by_border.most_common())
    # клетки, где сейв отличается от MAP (дверь открыта, разрушено): какой вид и сколько проверено на экране
    rb, _info = mt.rebuild(bt, data)
    eq = ((rb.SET == bt.SET) & (rb.ID == bt.ID)).all(axis=-1)
    kinds, state_px, state_cells = {}, Counter(), defaultdict(set)
    for t in owner[drawn & ~covered].tolist():
        q = (t - 1) // 4
        z, r = divmod(q, bt.X * bt.Y)
        y, x = divmod(r, bt.X)
        if eq[z, y, x]:
            continue
        if (z, y, x) not in kinds:
            pt = tuple(None if rb.SET[z, y, x, p] < 0 else (int(rb.SET[z, y, x, p]), int(rb.ID[z, y, x, p]))
                       for p in range(4))
            path = mt.transitions(pt, z, bt, data).get(tuple(bt.part(z, y, x, p) for p in range(4)))
            kinds[(z, y, x)] = "unexplained" if path is None else \
                "door" if all(s.startswith("door") for s in path) else \
                "destroyed" if all(s.startswith("die") for s in path) else "door+destroyed"
        state_px[kinds[(z, y, x)]] += 1
        state_cells[kinds[(z, y, x)]].add((x, y, z))
    why["tested_on_state"] = {k2: [n, len(state_cells[k2])] for k2, n in state_px.most_common()}
    r2 = game.copy() // 3
    r2[left] = (255, 0, 64)
    Image.fromarray(np.concatenate([game, r2], 1)).resize((W * 4, H * 2), Image.NEAREST).save(
        out / (stem + "_residual.png"))
    # расхождения по клеткам: чья точка у нас там, где кадр игры другой и это не объяснено
    cells = Counter()
    for t in owner[left & drawn].tolist():
        q = (t - 1) // 4
        z, r = divmod(q, bt.X * bt.Y)
        y, x = divmod(r, bt.X)
        cells[(x, y, z, mt.PARTS[(t - 1) % 4])] += 1
    res = {
        "save": str(save), "dump": prefix, "k": k, "camera": cam, "surface": [W, H],
        "globalShade": js.get("globalShade"), "debugVisionMode": js.get("debugVisionMode"),
        "nightVision": js.get("nightVision"), "hdMode": js.get("hdMode"),
        "pixels": int(W * H), "drawn_by_us": int(drawn.sum()),
        "mismatch": int(bad.sum()), "mismatch_on_ours": int((bad & drawn).sum()),
        "mismatch_on_empty": int((bad & ~drawn).sum()),
        "mismatch_by_cause": why,
        "palette_entries": len(pal), "palette_shared": shared[:20],
        "worst_cells": [[*c, n] for c, n in cells.most_common(40)],
    }
    (out / (stem + "_check.json")).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding=ENC)
    print("%s: k %d, камера %s, поверхность %dx%d, globalShade %s, debugVision %s, hdMode %s"
          % (stem, k, cam, W, H, res["globalShade"], res["debugVisionMode"], res["hdMode"]))
    print("  точек %d, наших %d; не совпало %d (на наших %d, где у нас пусто %d); палитра %d, общих цветов %d"
          % (res["pixels"], res["drawn_by_us"], res["mismatch"], res["mismatch_on_ours"],
             res["mismatch_on_empty"], len(pal), len(shared)))
    print("  по причинам:", why)
    for c in res["worst_cells"][:12]:
        print("   клетка", c)
    return res


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("prep")
    a.add_argument("save")
    a.add_argument("--out", required=True)
    a.add_argument("--center", default="", help="x,y,z: переставить выбранного юнита - камера дампа встанет туда")
    a.add_argument("--clear-smoke", action="store_true", help="снять дым и огонь клеток")
    a = sub.add_parser("units")
    a.add_argument("save")
    a = sub.add_parser("compare")
    a.add_argument("save")
    a.add_argument("prefix", help="путь к дампу без суффикса: .../hdtest000")
    a.add_argument("--out", required=True)
    a.add_argument("--break", dest="breaks", default="", help="контроль: yoff,half,order - сверка обязана упасть")
    o = ap.parse_args(argv)
    if o.cmd == "prep":
        prep(o.save, o.out, tuple(int(v) for v in o.center.split(",")) if o.center else None, o.clear_smoke)
    elif o.cmd == "units":
        us, sel = units(o.save)
        print("выбран", sel)
        for u in us:
            print(*u)
    else:
        compare(o.save, o.prefix, o.out, tuple(filter(None, o.breaks.split(","))))


if __name__ == "__main__":
    main()
