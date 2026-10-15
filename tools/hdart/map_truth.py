"""Правда карты боя: что лежит в сейве против того, что дают MAP-блоки по правилам загрузки движка.

Сейв боя хранит итог генерации клетка в клетку (binTiles: четыре записи MCD на клетку - номер
записи и номер набора в общем списке mapdatasets) и имя блока на каждый кусок 10x10
(flattenedMapBlockNames). По ним карта восстанавливается из MAP-файлов тем же порядком, что
BattlescapeGenerator::loadMAP, и сверяется с сейвом. Расхождение раскладывается на то, что
объясняют двери (Tile::openDoor) и разрушение (Tile::destroy), и на необъяснённое.

Семантика, проверенная по коду (src/Battlescape/BattlescapeGenerator.cpp:2076):
  * часть клетки при загрузке - это СТОЛБЕЦ MAP (пол, стена З, стена С, объект), а не Tile_Type
    записи MCD. Tile_Type решает только при смене состояния: дверь открывается в часть
    Tile_Type записи Alt (Tile.cpp:388), обломок ложится в часть Tile_Type записи Die (Tile.cpp:549);
  * байт клетки - сквозной номер по наборам террейна (RuleTerrain::getMapData); вылет за конец
    даёт BLANKS 0 в наборе 0 общего списка;
  * блок ставится на этаж выше, если в углу блока выше нулевого этажа уже есть пол (только zoff 0);
  * корабль и НЛО (mapDataSetOffset > 0) перед каждой непустой частью снимают объект клетки;
  * после всех блоков пустой пол нулевого этажа - выжженная земля: запись 1 набора 0.

Порядок слоёв: блоки террейна (под кораблём - блоки группы 1, их имя в сейве затёрто именем
корабля и подбирается по совпадению), затем НЛО, затем корабль.

  py -3.13 tools/hdart/map_truth.py check <сейв> [<сейв>...] [--out census/map_truth]
  py -3.13 tools/hdart/map_truth.py layout <сейв>
"""
import argparse
import base64
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / "Пиратки" / "Dioxine_XPiratez"
VALUES = ROOT / ".index" / "mod" / "Piratez" / "rul" / "values.tsv"
ENC_W = "utf-8-sig"
PARTS = ("floor", "west", "north", "object")
MCD_RECORD = 62
# байты записи MCD - struct MCD в src/Mod/MapDataSet.cpp
B_UFO_DOOR, B_DOOR, B_DIE, B_ALT, B_TYPE = 30, 35, 44, 46, 53
B_PLEVEL = 49          # P_Level: кадр поднимается на столько пикселей (MapData::setYOffset)
SCORCHED = (0, 1)           # MapDataSet::getScorchedEarthTile: запись 1, набор 0 (BattlescapeGenerator.cpp:3343)


# ------------------------------------------------------------------ сейв

class Battle:
    """Карта из сейва: размеры, сетки имён, общий список наборов и клетки."""

    def __init__(self, path):
        self.path = Path(path)
        text = self.path.read_text(encoding="utf-8", errors="replace")
        head, _, rest = text.partition("\n---\n")
        self.mods = re.findall(r"^  - '([^']*)'", head.split("\nmods:", 1)[-1].split("\n---", 1)[0], re.M)
        m = re.search(r"^rng: (\d+)", text, re.M)
        self.rng_at_save = m.group(1) if m else ""
        i = text.find("\nbattleGame:\n")
        if i < 0:
            raise SystemExit("%s: в сейве нет боя (battleGame)" % path)
        bg = text[i + 1:]
        self.X = int(self._scalar(bg, "width"))
        self.Y = int(self._scalar(bg, "length"))
        self.Z = int(self._scalar(bg, "height"))
        self.mission = self._scalar(bg, "missionType")
        self.script = self._scalar(bg, "lastUsedMapScript", "")
        self.terr = self._grid(bg, "flattenedMapTerrainNames")
        self.blocks = self._grid(bg, "flattenedMapBlockNames")
        self.sets = self._list(bg, "mapdatasets")
        key = {k: self._size(bg, k) for k in ("tileIndexSize", "tileTotalBytesPer", "tileFireSize",
                                               "tileSmokeSize", "tileIDSize", "tileSetIDSize",
                                               "tileBoolFieldsSize")}
        total = int(self._scalar(bg, "totalTiles"))
        raw = base64.b64decode(self._block_text(bg, "binTiles"))
        self.ID = np.full((self.Z, self.Y, self.X, 4), -1, np.int32)
        self.SET = np.full((self.Z, self.Y, self.X, 4), -1, np.int32)
        self.flags = np.zeros((self.Z, self.Y, self.X), np.uint8)
        self.smoke = np.zeros((self.Z, self.Y, self.X), np.uint8)
        self.fire = np.zeros((self.Z, self.Y, self.X), np.uint8)
        per = key["tileTotalBytesPer"]
        for t in range(total):
            p = t * per
            q = p
            idx, q = _int(raw, q, key["tileIndexSize"])
            ids = []
            for _ in range(4):
                v, q = _int(raw, q, key["tileIDSize"])
                ids.append(v)
            sids = []
            for _ in range(4):
                v, q = _int(raw, q, key["tileSetIDSize"])
                sids.append(v)
            sm, q = _int(raw, q, key["tileSmokeSize"])
            fi, q = _int(raw, q, key["tileFireSize"])
            fl, q = _int(raw, q, key["tileBoolFieldsSize"])
            z, r = divmod(idx, self.X * self.Y)
            y, x = divmod(r, self.X)
            self.ID[z, y, x] = ids
            self.SET[z, y, x] = sids
            self.flags[z, y, x] = fl
            self.smoke[z, y, x] = sm
            self.fire[z, y, x] = fi
        self.total_tiles = total

    @staticmethod
    def _scalar(bg, k, default=None):
        m = re.search(r"^  %s: (.*)$" % k, bg, re.M)
        if not m:
            if default is None:
                raise SystemExit("в бою нет поля %s" % k)
            return default
        return m.group(1).strip().strip("'\"")

    @staticmethod
    def _size(bg, k):
        m = re.search(r'^  %s: "?(?:\\x0?)?([0-9a-fA-F]+)"?$' % k, bg, re.M)
        v = m.group(1)
        return int(v, 16) if '\\x' in m.group(0) else int(v)

    @staticmethod
    def _list(bg, k):
        i = bg.find("\n  %s:\n" % k)
        out = []
        for line in bg[i:].splitlines()[2:]:
            if not line.startswith("    - "):
                break
            out.append(line[6:].strip().strip("'\""))
        return out

    @staticmethod
    def _block_text(bg, k):
        i = bg.find("\n  %s: " % k)
        lines = bg[i + 1:].splitlines()
        out = [lines[0].split(": ", 1)[1].strip()]
        for line in lines[1:]:
            if line.startswith("    "):
                out.append(line.strip())
            else:
                break
        return "".join(out)

    @staticmethod
    def _grid(bg, k):
        """Столбцы x, в каждом имена по y (как vector<vector<string>> в SavedBattleGame)."""
        i = bg.find("\n  %s:\n" % k)
        cols = []
        for line in bg[i:].splitlines()[2:]:
            s = line.rstrip()
            if s.startswith("    - - "):
                cols.append([s[8:].strip().strip("'\"")])
            elif s.startswith("      - "):
                cols[-1].append(s[8:].strip().strip("'\""))
            else:
                break
        return cols

    def part(self, z, y, x, p):
        s = int(self.SET[z, y, x, p])
        return None if s < 0 else (s, int(self.ID[z, y, x, p]))


def _int(buf, q, size):
    """unserializeInt (SerializationHelper.cpp:27): 1 - без знака, 2 - со знаком, 4 - Uint32."""
    if size == 1:
        return buf[q], q + 1
    if size == 2:
        return int.from_bytes(buf[q:q + 2], "little", signed=True), q + 2
    if size == 4:
        return int.from_bytes(buf[q:q + 4], "little", signed=False), q + 4
    raise ValueError("размер поля %d" % size)


# ------------------------------------------------------------------ данные игры

class Data:
    """Слои файлов (последний загруженный мод сверху, как FileMap), правила террейнов, MCD."""

    def __init__(self, mods):
        mods_dir = INSTALL / "user" / "mods"
        by_id = {}
        for d in sorted(mods_dir.iterdir()):
            meta = d / "metadata.yml"
            if d.is_dir() and meta.exists():
                m = re.search(r"^id:\s*\"?([^\"\r\n]+)\"?", meta.read_text(encoding="utf-8", errors="replace"), re.M)
                if m:
                    by_id[m.group(1).strip()] = d
        zips = [p.name for p in mods_dir.glob("*.zip")]
        if zips:
            print("  внимание: в user/mods есть zip (R-074): %s" % ", ".join(zips))
        order = []
        for line in mods:
            mid = line.split(" ver:")[0].strip()
            if mid in by_id:
                order.append(by_id[mid])
            else:
                print("  мод %s из сейва не найден в установке" % mid)
        self.roots = list(reversed(order)) + [INSTALL / "standard" / "xcom1", INSTALL / "UFO"]
        self.roots = [r for r in self.roots if r.is_dir()]
        self.used = {}
        self._mcd = {}
        self._map = {}
        self.terrains, self.crafts, self.ufos, self.patches = {}, {}, {}, {}
        csv.field_size_limit(10 ** 9)
        with open(VALUES, encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                if len(row) < 4:
                    continue
                sec, name, field, val = row[:4]
                if sec == "terrains" and field in ("mapDataSets", "mapBlocks"):
                    self.terrains.setdefault(name, {})[field] = json.loads(val)
                elif sec in ("crafts", "ufos") and field == "battlescapeTerrainData":
                    (self.crafts if sec == "crafts" else self.ufos)[name] = json.loads(val)
                elif sec == "MCDPatches" and field == "data":
                    self.patches[name] = json.loads(val)

    def find(self, rel):
        """Первый слой, где файл есть. Имя без учёта регистра, как в FileMap."""
        low = rel.lower()
        for r in self.roots:
            d = r / os.path.dirname(rel)
            if not d.is_dir():
                continue
            base = os.path.basename(low)
            for p in d.iterdir():
                if p.name.lower() == base:
                    if rel not in self.used:
                        self.used[rel] = (str(p.relative_to(INSTALL)), hashlib.sha1(p.read_bytes()).hexdigest()[:12])
                    return p
        return None

    def mcd(self, set_name):
        """Записи MCD набора с наложенными MCDPatches (Mod::getMCDPatch)."""
        if set_name in self._mcd:
            return self._mcd[set_name]
        p = self.find("TERRAIN/%s.MCD" % set_name)
        recs = []
        if p:
            b = p.read_bytes()
            for i in range(0, len(b) - MCD_RECORD + 1, MCD_RECORD):
                r = b[i:i + MCD_RECORD]
                recs.append({"frames": list(r[0:8]), "door": r[B_DOOR], "ufo_door": r[B_UFO_DOOR],
                             "die": r[B_DIE], "alt": r[B_ALT], "type": r[B_TYPE],
                             "yoff": r[B_PLEVEL]})
        for d in self.patches.get(set_name, []):
            k = d.get("MCDIndex")
            if k is None or k >= len(recs):
                continue
            if "deathTile" in d:
                recs[k]["die"] = d["deathTile"]
            if "objectType" in d:
                recs[k]["type"] = d["objectType"]
        self._mcd[set_name] = recs
        return recs

    def map_file(self, name):
        if name in self._map:
            return self._map[name]
        p = self.find("MAPS/%s.MAP" % name)
        if p is None:
            self._map[name] = None
            return None
        b = p.read_bytes()
        sy, sx, sz = [v - 256 if v > 127 else v for v in b[:3]]
        self._map[name] = (sy, sx, sz, b[3:])
        return self._map[name]


# ------------------------------------------------------------------ сборка, как loadMAP

class Rebuild:
    def __init__(self, bt, data):
        self.bt, self.data = bt, data
        self.sizes = [len(data.mcd(s)) for s in bt.sets]
        self.SET = np.full((bt.Z, bt.Y, bt.X, 4), -1, np.int32)
        self.ID = np.full((bt.Z, bt.Y, bt.X, 4), -1, np.int32)
        self.col_vs_type_at = []           # (z, y, x, столбец, набор, запись, Tile_Type) - столбец MAP != Tile_Type
        self.log = []

    def get_md(self, value, offset, nsets):
        """RuleTerrain::getMapData: сквозной номер по наборам террейна; вылет - BLANKS 0, набор 0."""
        mid, sid = value, offset
        for k in range(nsets):
            if mid < self.sizes[offset + k]:
                return sid, mid
            mid -= self.sizes[offset + k]
            sid += 1
        return 0, 0

    def load_map(self, name, xoff, yoff, zoff, offset, nsets, track=True):
        m = self.data.map_file(name)
        if m is None:
            self.log.append("нет файла MAPS/%s.MAP" % name)
            return None
        sy, sx, sz, body = m
        Z = self.bt.Z
        z = zoff + sz - 1
        for i in range(Z - 1, 0, -1):
            if self.SET[i, yoff, xoff, 0] >= 0 and zoff == 0:
                z += i
                break
        if z > Z - 1:
            raise SystemExit("блок %s выше карты" % name)
        x, y = xoff, yoff
        for k in range(0, len(body) - 3, 4):
            for part in range(4):
                v = body[k + part]
                if v > 0:
                    sid, mid = self.get_md(v, offset, nsets)
                    if 0 <= z < Z and 0 <= y < self.bt.Y and 0 <= x < self.bt.X:
                        if offset > 0:
                            self.SET[z, y, x, 3] = -1
                            self.ID[z, y, x, 3] = -1
                        self.SET[z, y, x, part] = sid
                        self.ID[z, y, x, part] = mid
                        rec = self.data.mcd(self.bt.sets[sid])
                        t = rec[mid]["type"] if mid < len(rec) else None
                        if track and t is not None and t != part:
                            self.col_vs_type_at.append((z, y, x, part, sid, mid, t))
            x += 1
            if x == sx + xoff:
                x = xoff
                y += 1
            if y == sy + yoff:
                y = yoff
                z -= 1
        return z

    def scorch(self):
        for y in range(self.bt.Y):
            for x in range(self.bt.X):
                if self.SET[0, y, x, 0] < 0:
                    self.SET[0, y, x, 0], self.ID[0, y, x, 0] = SCORCHED


def _same(rb, bt, sl):
    """Сколько клеток куска совпало с сейвом целиком (все четыре части)."""
    return int(((rb.SET[sl] == bt.SET[sl]) & (rb.ID[sl] == bt.ID[sl])).all(axis=-1).sum())


def set_offset(sets, names, prefer_tail=False):
    """Где в общем списке наборов стоит список наборов террейна."""
    n = len(names)
    hits = [i for i in range(len(sets) - n + 1) if sets[i:i + n] == names]
    if not hits:
        return None
    return hits[-1] if prefer_tail else hits[0]


def layout(bt, data):
    """Блоки по сетке кусков: начало, размер, террейн. Куски корабля и НЛО - отдельно."""
    nx, ny = len(bt.blocks), len(bt.blocks[0]) if bt.blocks else 0
    owner = [[None] * ny for _ in range(nx)]
    blocks, special, problems = [], [], []
    for cx in range(nx):
        for cy in range(ny):
            if owner[cx][cy] is not None:
                continue
            name, t = bt.blocks[cx][cy], bt.terr[cx][cy]
            kind = "craft" if t in data.crafts else "ufo" if t in data.ufos else "terrain"
            m = data.map_file(name)
            if m is None:
                problems.append("нет MAP %s" % name)
                owner[cx][cy] = -1
                continue
            w, h = max(1, m[1] // 10), max(1, m[0] // 10)
            rec = {"name": name, "terrain": t, "kind": kind, "cx": cx, "cy": cy, "w": w, "h": h}
            for i in range(w):
                for j in range(h):
                    X, Y = cx + i, cy + j
                    if X >= nx or Y >= ny:
                        problems.append("%s в (%d,%d) за краем" % (name, cx, cy))
                        continue
                    if bt.blocks[X][Y] != name or owner[X][Y] is not None:
                        problems.append("%s в (%d,%d): кусок (%d,%d) занят %s" % (name, cx, cy, X, Y, bt.blocks[X][Y]))
                    owner[X][Y] = len(blocks) + len(special)
            (special if kind != "terrain" else blocks).append(rec)
    return blocks, special, problems


def rebuild(bt, data, main_terrain=None):
    """Карта из MAP по сейву. Возвращает Rebuild и сводку о размещении."""
    rb = Rebuild(bt, data)
    blocks, special, problems = layout(bt, data)
    info = {"blocks": blocks, "special": special, "problems": problems, "under": [], "renamed": []}
    terr_names = Counter(b["terrain"] for b in blocks)
    main = main_terrain or (terr_names.most_common(1)[0][0] if terr_names else None)
    info["main_terrain"] = main
    # смещение - по террейну, а не по именам наборов (loadExtraTerrain, BattlescapeGenerator.cpp:2444-2462):
    # доп. террейн с тем же списком наборов грузит свою копию в конец списка - основной берёт первую копию
    taken = {}

    def terrain_offset(name, sets_list):
        if name in taken:
            return taken[name]
        n = len(sets_list)
        hits = [i for i in range(len(bt.sets) - n + 1) if bt.sets[i:i + n] == sets_list]
        free = [i for i in hits if i not in taken.values()]
        off = (free or hits or [None])[0]
        if off is not None:
            taken[name] = off
        return off

    if main in data.terrains:
        terrain_offset(main, data.terrains[main]["mapDataSets"])
    for b in blocks:
        tr = data.terrains.get(b["terrain"])
        if not tr:
            problems.append("террейн %s без правил" % b["terrain"])
            continue
        off = terrain_offset(b["terrain"], tr["mapDataSets"])
        if off is None:
            problems.append("наборы %s не найдены в mapdatasets" % b["terrain"])
            continue
        b["set_offset"] = off
        rb.load_map(b["name"], b["cx"] * 10, b["cy"] * 10, 0, off, len(tr["mapDataSets"]))
        # addLine на перекрёстке (BattlescapeGenerator.cpp:4384) меняет блок после clearModule, а имя
        # в flattenedMapBlockNames оставляет прежним: клетки куска - от блока группы перекрёстка
        if b["w"] == 1 and b["h"] == 1:
            sl = (slice(None), slice(b["cy"] * 10, b["cy"] * 10 + 10), slice(b["cx"] * 10, b["cx"] * 10 + 10))
            own = _same(rb, bt, sl)
            if own < bt.Z * 100:
                base_s, base_i = rb.SET.copy(), rb.ID.copy()
                best = (own, b["name"])
                for blk in tr["mapBlocks"]:
                    if blk.get("width", 10) != 10 or blk.get("length", 10) != 10 or blk["name"] == b["name"]:
                        continue
                    mf = data.map_file(blk["name"])
                    if mf is None or mf[2] > bt.Z:     # выше карты движок не кладёт (исключение в loadMAP)
                        continue
                    rb.SET[sl], rb.ID[sl] = -1, -1
                    rb.load_map(blk["name"], b["cx"] * 10, b["cy"] * 10, 0, off, len(tr["mapDataSets"]), track=False)
                    v = _same(rb, bt, sl)
                    if v > best[0]:
                        best = (v, blk["name"])
                rb.SET[:], rb.ID[:] = base_s, base_i
                if best[1] != b["name"] and best[0] - own >= 20:
                    b["recorded_name"], b["name"] = b["name"], best[1]
                    b["same_recorded"], b["same_actual"] = own, best[0]
                    rb.SET[sl], rb.ID[sl] = -1, -1
                    rb.col_vs_type_at = [t for t in rb.col_vs_type_at
                                         if not (b["cx"] * 10 <= t[2] < b["cx"] * 10 + 10 and b["cy"] * 10 <= t[1] < b["cy"] * 10 + 10)]
                    rb.load_map(best[1], b["cx"] * 10, b["cy"] * 10, 0, off, len(tr["mapDataSets"]))
                    info["renamed"].append({"cx": b["cx"], "cy": b["cy"], "recorded": b["recorded_name"],
                                            "actual": best[1], "same_recorded": own, "same_actual": best[0]})
    crafts = [s for s in special if s["kind"] == "craft"]
    ufos = [s for s in special if s["kind"] == "ufo"]
    n_craft = len(data.crafts[crafts[0]["terrain"]]["mapDataSets"]) if crafts else 0
    n_ufo = len(data.ufos[ufos[0]["terrain"]]["mapDataSets"]) if ufos else 0
    craft_off = len(bt.sets) - n_craft
    ufo_off = craft_off - n_ufo

    def overlay(target):
        for u in ufos:
            rb.load_map(u["name"], u["cx"] * 10, u["cy"] * 10, 0, ufo_off, n_ufo, track=False)
        for c in crafts:
            rb.load_map(c["name"], c["cx"] * 10, c["cy"] * 10, 0, craft_off, n_craft, track=False)

    # под кораблём и НЛО - блоки группы 1 основного террейна, имя затёрто: подбор по совпадению
    tr = data.terrains.get(main) or {}
    off = terrain_offset(main, tr.get("mapDataSets", [])) if tr else None
    cands = []
    for blk in tr.get("mapBlocks", []):
        g = blk.get("groups", 0)
        g = g if isinstance(g, list) else [g]
        if blk.get("width", 10) == 10 and blk.get("length", 10) == 10:
            cands.append((1 in g, blk["name"]))
    pool = [n for g1, n in cands if g1] or [n for _, n in cands]
    for s in crafts + ufos:
        for i in range(s["w"]):
            for j in range(s["h"]):
                cx, cy = s["cx"] + i, s["cy"] + j
                if off is None or not pool:
                    info["under"].append({"cx": cx, "cy": cy, "pick": None})
                    continue
                base_s, base_i = rb.SET.copy(), rb.ID.copy()
                scores = []
                for name in pool:
                    rb.SET[:], rb.ID[:] = base_s, base_i
                    rb.load_map(name, cx * 10, cy * 10, 0, off, len(tr["mapDataSets"]), track=False)
                    overlay(None)
                    sl = (slice(None), slice(cy * 10, cy * 10 + 10), slice(cx * 10, cx * 10 + 10))
                    same = int(((rb.SET[sl] == bt.SET[sl]) & (rb.ID[sl] == bt.ID[sl])).all(axis=-1).sum())
                    scores.append((same, name))
                rb.SET[:], rb.ID[:] = base_s, base_i
                scores.sort(reverse=True)
                best = scores[0]
                second = scores[1][0] if len(scores) > 1 else -1
                tied = [n for v, n in scores if v == best[0]]
                info["under"].append({"cx": cx, "cy": cy, "pick": best[1], "same": best[0],
                                      "runner_up": second, "pool": len(pool), "tied": tied})
                rb.load_map(best[1], cx * 10, cy * 10, 0, off, len(tr["mapDataSets"]))
    overlay(None)
    rb.scorch()
    return rb, info


# ------------------------------------------------------------------ сверка

def transitions(state, z, bt, data, depth=10):
    """Состояния клетки, достижимые из state дверями и разрушением (Tile::openDoor, Tile::destroy).
    state - кортеж из четырёх (набор, запись) или None. Возвращает {состояние: путь}."""
    seen = {state: ()}
    frontier = [state]
    for _ in range(depth):
        nxt = []
        for st in frontier:
            for p in range(4):
                cur = st[p]
                if cur is None:
                    continue
                sid, mid = cur
                recs = data.mcd(bt.sets[sid])
                if mid >= len(recs):
                    continue
                r = recs[mid]
                moves = []
                # разрушение: часть снимается, обломок Die ложится в часть своего Tile_Type
                s2 = list(st)
                s2[p] = None
                if r["die"]:
                    dt = recs[r["die"]]["type"] if r["die"] < len(recs) else p
                    s2[dt] = (sid, r["die"])
                if p == 0 and z == 0 and s2[0] is None:
                    s2[0] = SCORCHED
                moves.append(("die:%s" % PARTS[p], tuple(s2)))
                # дверь: запись Alt в часть своего Tile_Type, затем исходная часть снимается
                if r["door"] and r["alt"] < len(recs):
                    s3 = list(st)
                    s3[recs[r["alt"]]["type"]] = (sid, r["alt"])
                    s3[p] = None
                    moves.append(("door:%s" % PARTS[p], tuple(s3)))
                for lab, ns in moves:
                    if ns not in seen:
                        seen[ns] = seen[st] + (lab,)
                        nxt.append(ns)
        frontier = nxt
        if not frontier or len(seen) > 20000:
            break
    return seen


def compare(bt, rb, data, info):
    pred_s, pred_i = rb.SET, rb.ID
    owner = {}
    for b in info["blocks"]:
        for i in range(b["w"] * 10):
            for j in range(b["h"] * 10):
                owner[(b["cx"] * 10 + i, b["cy"] * 10 + j)] = b["name"]
    for s in info["special"]:
        for i in range(s["w"] * 10):
            for j in range(s["h"] * 10):
                owner[(s["cx"] * 10 + i, s["cy"] * 10 + j)] = s["name"] + "*"
    per = defaultdict(Counter)
    rows = []
    eq = ((pred_s == bt.SET) & (pred_i == bt.ID)).all(axis=-1)
    for z in range(bt.Z):
        for y in range(bt.Y):
            for x in range(bt.X):
                blk = owner.get((x, y), "?")
                pt = tuple(None if pred_s[z, y, x, p] < 0 else (int(pred_s[z, y, x, p]), int(pred_i[z, y, x, p])) for p in range(4))
                if eq[z, y, x]:
                    per[blk]["same" if any(pt) else "empty"] += 1
                    continue
                at = tuple(bt.part(z, y, x, p) for p in range(4))
                reach = transitions(pt, z, bt, data)
                if at in reach:
                    path = reach[at]
                    kind = "door" if all(s.startswith("door") for s in path) else \
                        "destroyed" if all(s.startswith("die") for s in path) else "door+destroyed"
                    per[blk][kind] += 1
                    rows.append((blk, x, y, z, kind, " ".join(path), _fmt(bt, pt), _fmt(bt, at)))
                else:
                    per[blk]["unexplained"] += 1
                    rows.append((blk, x, y, z, "unexplained", "", _fmt(bt, pt), _fmt(bt, at)))
    return per, rows


def _fmt(bt, st):
    return " | ".join("-" if p is None else "%s:%d" % (bt.sets[p[0]], p[1]) for p in st)


def col_type_check(bt, rb):
    """Части, где столбец MAP и Tile_Type записи разные: в каком слоте они оказались в сейве.
    Часть, которую потом перекрыл корабль, не считается; 'absent' - снесена за ход ИИ или пожаром."""
    res, pairs = Counter(), Counter()
    for z, y, x, part, sid, mid, t in rb.col_vs_type_at:
        if (int(rb.SET[z, y, x, part]), int(rb.ID[z, y, x, part])) != (sid, mid):
            res["overwritten_by_craft"] += 1
            continue
        pairs[(part, t)] += 1
        a = bt.part(z, y, x, part)
        if a == (sid, mid):
            res["in_map_column"] += 1
        else:
            w = [p for p in range(4) if bt.part(z, y, x, p) == (sid, mid)]
            res["in_tile_type_slot" if t in w else "elsewhere" if w else "absent"] += 1
    return res, pairs


def check(path, out):
    bt = Battle(path)
    data = Data(bt.mods)
    rb, info = rebuild(bt, data)
    per, rows = compare(bt, rb, data, info)
    ct, ct_pairs = col_type_check(bt, rb)
    tot = Counter()
    for c in per.values():
        tot.update(c)
    stem = Path(path).stem
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / ("%s_diff.tsv" % stem), "w", encoding=ENC_W, newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["block", "x", "y", "z", "kind", "path", "predicted", "actual"])
        w.writerows(rows)
    summary = {
        "save": str(path), "mods": bt.mods, "mission": bt.mission, "mapScript": bt.script,
        "rng_at_save": bt.rng_at_save, "size": [bt.X, bt.Y, bt.Z], "sets": bt.sets,
        "tiles_in_save": bt.total_tiles, "main_terrain": info["main_terrain"],
        "blocks": info["blocks"], "special": info["special"], "under_craft": info["under"],
        "problems": info["problems"] + rb.log, "totals": dict(tot),
        "per_block": {k: dict(v) for k, v in sorted(per.items())},
        "renamed_crossings": info["renamed"],
        "map_column_vs_tile_type": {"parts": sum(ct_pairs.values()),
                                    "pairs": {"%s->type%d" % (PARTS[a], b): n for (a, b), n in ct_pairs.most_common()},
                                    "where_in_save": dict(ct)},
        "files": data.used,
    }
    with open(out / ("%s.json" % stem), "w", encoding=ENC_W) as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    cells = sum(tot.values()) - tot["empty"]
    print("%s: %s %s, %dx%dx%d, блоков %d, особых %d" % (stem, bt.mission, info["main_terrain"], bt.X, bt.Y, bt.Z,
                                                       len(info["blocks"]), len(info["special"])))
    print("  клеток с содержимым %d: совпало %d, дверь %d, разрушение %d, смесь %d, НЕ объяснено %d" % (
        cells, tot["same"], tot["door"], tot["destroyed"], tot["door+destroyed"], tot["unexplained"]))
    print("  столбец MAP != Tile_Type: %d частей, в сейве: %s" % (sum(ct_pairs.values()), dict(ct)))
    for r in info["renamed"]:
        print("  перекрёсток (%d,%d): в сейве %s, по клеткам %s (%d -> %d из %d)" % (
            r["cx"], r["cy"], r["recorded"], r["actual"], r["same_recorded"], r["same_actual"], bt.Z * 100))
    for u in info["under"]:
        tied = u.get("tied") or []
        print("  под кораблём (%d,%d): %s, совпало %s клеток из %d, %s" % (
            u["cx"], u["cy"], u.get("pick"), u.get("same"), bt.Z * 100,
            "неразличимы %d из %d кандидатов группы 1" % (len(tied), u.get("pool", 0)) if len(tied) > 1
            else "второй %s" % u.get("runner_up")))
    for p in summary["problems"][:10]:
        print("  !", p)
    return summary


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("check")
    c.add_argument("saves", nargs="+")
    c.add_argument("--out", default=str(ROOT / "census" / "map_truth"))
    l = sp.add_parser("layout")
    l.add_argument("save")
    a = ap.parse_args()
    if a.cmd == "check":
        saves = []
        for s in a.saves:
            saves += sorted(Path(s).glob("*.sav")) if Path(s).is_dir() else [Path(s)]
        rows = []
        for s in saves:
            r = check(s, a.out)
            t = r["totals"]
            rows.append([s.name, r["mission"], r["main_terrain"], len(r["blocks"]), len(r["special"]),
                         sum(v for k, v in t.items() if k != "empty"), t.get("same", 0), t.get("door", 0),
                         t.get("destroyed", 0), t.get("door+destroyed", 0), t.get("unexplained", 0),
                         r["map_column_vs_tile_type"]["parts"],
                         r["map_column_vs_tile_type"]["where_in_save"].get("in_map_column", 0),
                         len(r["problems"])])
        if len(saves) > 1:
            with open(Path(a.out) / "summary.tsv", "w", encoding=ENC_W, newline="") as f:
                w = csv.writer(f, delimiter="\t", lineterminator="\n")
                w.writerow(["save", "mission", "terrain", "blocks", "special", "cells", "same", "door",
                            "destroyed", "door_destroyed", "unexplained", "col_ne_type", "col_ne_type_in_column",
                            "problems"])
                w.writerows(rows)
            tot = [sum(r[i] for r in rows) for i in range(5, 14)]
            print("ИТОГО %d сейвов: клеток %d, совпало %d, дверь %d, разрушение %d, смесь %d, НЕ объяснено %d; "
                  "столбец != Tile_Type %d, из них в столбце MAP %d; проблем %d" % (len(rows), *tot))
    else:
        bt = Battle(a.save)
        data = Data(bt.mods)
        blocks, special, problems = layout(bt, data)
        for b in blocks + special:
            print("%-8s %-20s %-16s (%d,%d) %dx%d" % (b["kind"], b["name"], b["terrain"], b["cx"], b["cy"], b["w"], b["h"]))
        for p in problems:
            print("!", p)


if __name__ == "__main__":
    main()
