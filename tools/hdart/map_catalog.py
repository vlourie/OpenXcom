"""Каталог карт боя по фактическим картам из сейвов: использование, соседство, состояния, конфликты.

Только чтение. Карта клетки берётся из сейва через map_truth (MAP без дверей и разрушений = как её
положил генератор; состояния - разница сейва с ней). Ключи - те же, что в Pipeline v2:
кадр SET:frame (art/manifest/assets.tsv frame_id), запись MCD SET#rec, террейн, имя MAP.

  py -3.13 tools/hdart/map_catalog.py build <папка сейвов или сейвы> [--out census/maps]

Одинаковые бои (тот же список наборов и те же клетки MAP) считаются один раз: автосейвы одного боя
не множат соседства. Состояния - объединение по всем сейвам боя.

Выход (UTF-8 со спецификацией, TSV):
  battles.tsv        бой: сейвы, миссия, скрипт, террейн, блоки
  record_usage.tsv   запись MCD: слоты, где стоит, физика MCD, клетки, бои, террейны, MAP
  frame_usage.tsv    кадр: записи, слоты, клетки, соседство пола, роли стены, хэш картинки
  adjacency.tsv      пары кадров: отношение C (та же клетка) / E (x+1) / S (y+1) / U (z+1), слоты, счёт,
                     из них на стыке разных блоков
  wall_roles.tsv     кадр стены (слот west/north): концы отрезка - продолжение / угол / свободен
  state_graph.tsv    переходы записей: die, door (alt), анимация; смена слота; наблюдено в сейвах
  conflicts.tsv      конфликты повторного использования (вид, кадр, доводы)
  summary.json       итоги и проверка: клеток, необъяснённых
"""
import argparse
import csv
import hashlib
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import map_truth as mt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ENC_W = "utf-8-sig"
RELS = {"E": (0, 0, 1), "S": (0, 1, 0), "U": (1, 0, 0)}
B_STOPLOS, B_BIGWALL, B_TLEVEL = 31, 33, 48


class Records:
    """Сырые записи MCD с MCDPatch (bigWall, stopLOS, objectType, deathTile) и сквозные номера кадров."""

    def __init__(self):
        self.rec_id, self.rec_key, self.rec_info = {}, [], []
        self.frame_id, self.frame_key = {}, []

    def frame(self, key):
        i = self.frame_id.get(key)
        if i is None:
            i = self.frame_id[key] = len(self.frame_key)
            self.frame_key.append(key)
        return i

    def record(self, data, set_name, rec):
        key = (set_name, rec)
        i = self.rec_id.get(key)
        if i is not None:
            return i
        recs = data.mcd(set_name)
        raw = _raw(data, set_name)
        info = {"set": set_name, "rec": rec, "frames": [0] * 8, "type": None, "die": 0, "alt": 0, "door": 0,
                "ufo_door": 0, "yoff": 0, "t_level": 0, "big_wall": 0, "stop_los": 0}
        if rec < len(recs):
            r = recs[rec]
            info.update({k: r[k] for k in ("frames", "type", "die", "alt", "door", "ufo_door", "yoff")})
        if rec < len(raw):
            b = raw[rec]
            info["t_level"] = int(np.int8(np.uint8(b[B_TLEVEL])))
            info["big_wall"] = b[B_BIGWALL]
            info["stop_los"] = b[B_STOPLOS]
        for d in data.patches.get(set_name, []):
            if d.get("MCDIndex") == rec:
                if "bigWall" in d:
                    info["big_wall"] = d["bigWall"]
                if "stopLOS" in d:
                    info["stop_los"] = int(bool(d["stopLOS"]))
        info["frame0"] = self.frame((set_name, info["frames"][0]))
        info["anim"] = len(set(info["frames"])) > 1
        i = self.rec_id[key] = len(self.rec_key)
        self.rec_key.append(key)
        self.rec_info.append(info)
        # цели переходов - тоже в реестр, даже если на картах их нет: слот берётся из их Tile_Type
        for t in (info["die"], info["alt"] if info["door"] else 0):
            if t and t < len(recs):
                self.record(data, set_name, t)
        return i


_RAW = {}


def _raw(data, set_name):
    if set_name not in _RAW:
        p = data.find("TERRAIN/%s.MCD" % set_name)
        b = p.read_bytes() if p else b""
        _RAW[set_name] = [b[i:i + mt.MCD_RECORD] for i in range(0, len(b) - mt.MCD_RECORD + 1, mt.MCD_RECORD)]
    return _RAW[set_name]


def owner_grid(bt, info):
    """Номер экземпляра блока по (y, x), имя MAP, террейн, вид (terrain / craft / ufo)."""
    inst = np.full((bt.Y, bt.X), -1, np.int32)
    meta = []
    for b in info["blocks"] + info["special"]:
        k = len(meta)
        meta.append((b["name"], b["terrain"], b["kind"]))
        inst[b["cy"] * 10:(b["cy"] + b["h"]) * 10, b["cx"] * 10:(b["cx"] + b["w"]) * 10] = k
    return inst, meta


def build(saves, out):
    out.mkdir(parents=True, exist_ok=True)
    R = Records()
    datas = {}
    battles = {}                       # ключ боя -> {'saves', 'mission', ...}
    rec_cells = Counter()              # (rec, slot) -> клеток
    rec_battles = defaultdict(set)
    rec_terr = defaultdict(Counter)
    rec_maps = defaultdict(Counter)
    rec_special = Counter()            # клетки в блоках корабля и НЛО
    adj = Counter()                    # (rel, pa, pb, fa, fb) -> счёт
    adj_border = Counter()
    adj_battles = Counter()
    wall_ends = Counter()              # (frame, slot, роль_конца_1, роль_конца_2) -> отрезков
    floor_self = Counter()             # кадр пола -> соседей-копий / всех (E и S в обе стороны)
    floor_all = Counter()
    floor_nb = defaultdict(Counter)    # кадр пола -> соседний кадр пола -> счёт
    state_obs = Counter()              # (rec_from, slot_from, путь, rec_to...) наблюдено клеток
    totals = Counter()
    for s in saves:
        bt = mt.Battle(s)
        key_mods = tuple(bt.mods)
        if key_mods not in datas:
            datas[key_mods] = mt.Data(bt.mods)
        data = datas[key_mods]
        rb, info = mt.rebuild(bt, data)
        h = hashlib.sha1()
        h.update("\n".join(bt.sets).encode())
        h.update(rb.SET.tobytes())
        h.update(rb.ID.tobytes())
        bkey = h.hexdigest()[:16]
        # сверка: каждая клетка сейва объяснена MAP плюс дверями и разрушением
        per, rows = mt.compare(bt, rb, data, info)
        for c in per.values():
            totals.update(c)
        first = bkey not in battles
        if first:
            battles[bkey] = {"saves": [], "mission": bt.mission, "script": bt.script,
                             "terrain": info["main_terrain"], "size": "%dx%dx%d" % (bt.X, bt.Y, bt.Z),
                             "blocks": sorted({b["name"] for b in info["blocks"]}),
                             "special": sorted({b["name"] for b in info["special"]}), "states": set()}
        battles[bkey]["saves"].append(Path(s).name)
        inst, meta = owner_grid(bt, info)
        # локальный (набор, запись) -> сквозная запись
        lut = {}
        F = np.full(rb.SET.shape, -1, np.int64)
        RID = np.full(rb.SET.shape, -1, np.int64)
        nz = np.argwhere(rb.SET >= 0)
        for z, y, x, p in nz:
            loc = (int(rb.SET[z, y, x, p]), int(rb.ID[z, y, x, p]))
            ri = lut.get(loc)
            if ri is None:
                ri = lut[loc] = R.record(data, bt.sets[loc[0]], loc[1])
            RID[z, y, x, p] = ri
            F[z, y, x, p] = R.rec_info[ri]["frame0"]
        # состояния: что сейв сделал с клеткой (без повторов внутри боя)
        for blk, x, y, z, kind, path, pred, act in rows:
            sk = (x, y, z, path, act)
            if sk in battles[bkey]["states"]:
                continue
            battles[bkey]["states"].add(sk)
            for step_rec, slot, how, to_rec, to_slot in _steps(bt, data, R, rb, x, y, z, path):
                state_obs[(step_rec, slot, how, to_rec, to_slot)] += 1
        if not first:
            continue
        # использование
        for z, y, x, p in nz:
            ri = int(RID[z, y, x, p])
            rec_cells[(ri, p)] += 1
            rec_battles[ri].add(bkey)
            k = inst[y, x]
            if k >= 0:
                name, terr, kind = meta[k]
                rec_terr[ri][terr] += 1
                rec_maps[ri][name] += 1
                if kind != "terrain":
                    rec_special[ri] += 1
        totals["battles"] += 1
        # соседство: та же клетка (C) и сдвиги E, S, U
        local = Counter()
        local_b = Counter()
        for pa in range(4):
            for pb in range(4):
                if pa < pb:
                    A, B = F[..., pa], F[..., pb]
                    m = (A >= 0) & (B >= 0)
                    _count(local, ("C", pa, pb), A[m], B[m])
                for rel, (dz, dy, dx) in RELS.items():
                    A = F[:F.shape[0] - dz, :F.shape[1] - dy, :F.shape[2] - dx, pa]
                    B = F[dz:, dy:, dx:, pb]
                    m = (A >= 0) & (B >= 0)
                    _count(local, (rel, pa, pb), A[m], B[m])
                    if rel != "U":
                        IA = np.broadcast_to(inst[:inst.shape[0] - dy, :inst.shape[1] - dx], A.shape)
                        IB = np.broadcast_to(inst[dy:, dx:], B.shape)
                        mb = m & (IA != IB)
                        _count(local_b, (rel, pa, pb), A[mb], B[mb])
        for k, n in local.items():
            adj[k] += n
            adj_battles[k] += 1
        for k, n in local_b.items():
            adj_border[k] += n
        # пол: доля соседей-копий
        for rel in ("E", "S"):
            dz, dy, dx = RELS[rel]
            A = F[:, :F.shape[1] - dy, :F.shape[2] - dx, 0]
            B = F[:, dy:, dx:, 0]
            m = (A >= 0) & (B >= 0)
            a, b = A[m], B[m]
            for u, v in ((a, b), (b, a)):
                same = u == v
                fa, ca = np.unique(u, return_counts=True)
                floor_all.update(dict(zip(fa.tolist(), ca.tolist())))
                fs, cs = np.unique(u[same], return_counts=True)
                floor_self.update(dict(zip(fs.tolist(), cs.tolist())))
        # роли концов стен: west идёт по y (концы - узлы (x,y) и (x,y+1)), north по x ((x,y) и (x+1,y))
        W = F[..., 1] >= 0
        N = F[..., 2] >= 0
        Z, Y, X = W.shape
        for z, y, x in np.argwhere(W):
            e1 = _end(W, N, z, x, y, "W", 0)
            e2 = _end(W, N, z, x, y, "W", 1)
            wall_ends[(int(F[z, y, x, 1]), 1) + tuple(sorted((e1, e2)))] += 1
        for z, y, x in np.argwhere(N):
            e1 = _end(W, N, z, x, y, "N", 0)
            e2 = _end(W, N, z, x, y, "N", 1)
            wall_ends[(int(F[z, y, x, 2]), 2) + tuple(sorted((e1, e2)))] += 1
        print("%s: бой %s %s %s" % (Path(s).name, bkey, bt.mission, info["main_terrain"]), flush=True)
    # соседи пола по кадру
    for (rel, pa, pb, fa, fb), n in adj.items():
        if rel in ("E", "S") and pa == 0 and pb == 0:
            floor_nb[fa][fb] += n
            floor_nb[fb][fa] += n
    totals["mods"] = list(key_mods)
    state = (R, battles, rec_cells, rec_battles, rec_terr, rec_maps, rec_special, adj, adj_border,
             adj_battles, wall_ends, floor_self, floor_all, floor_nb, state_obs, totals)
    with open(out / "_state.pickle", "wb") as f:        # write_all перезапускается без прохода по сейвам
        pickle.dump(state, f)
    write_all(out, *state)


def pname(t):
    return mt.PARTS[t] if t is not None and 0 <= t < 4 else "type%s" % t


def _count(counter, key, a, b):
    if not len(a):
        return
    code = a * (1 << 24) + b
    u, c = np.unique(code, return_counts=True)
    for v, n in zip(u.tolist(), c.tolist()):
        counter[key + (v >> 24, v & ((1 << 24) - 1))] += n


def _wall(W, N, z, x, y, kind):
    Z, Y, X = W.shape
    if not (0 <= x < X and 0 <= y < Y):
        return False
    return bool((W if kind == "W" else N)[z, y, x])


def _end(W, N, z, x, y, kind, which):
    """Узел конца отрезка стены: что ещё в нём сходится. cont - продолжение по той же линии,
    corner - только поперечная стена, tee - и то и другое, free - ничего."""
    if kind == "W":
        vx, vy = x, y + which                      # узел
        cont = _wall(W, N, z, x, y - 1, "W") if which == 0 else _wall(W, N, z, x, y + 1, "W")
    else:
        vx, vy = x + which, y
        cont = _wall(W, N, z, x - 1, y, "N") if which == 0 else _wall(W, N, z, x + 1, y, "N")
    # поперечные отрезки в узле (vx, vy): north клетки (vx, vy) и (vx-1, vy); west клетки (vx, vy) и (vx, vy-1)
    if kind == "W":
        cross = _wall(W, N, z, vx, vy, "N") or _wall(W, N, z, vx - 1, vy, "N")
    else:
        cross = _wall(W, N, z, vx, vy, "W") or _wall(W, N, z, vx, vy - 1, "W")
    return "tee" if cont and cross else "cont" if cont else "corner" if cross else "free"


def _steps(bt, data, R, rb, x, y, z, path):
    """Шаги пути перехода клетки как (запись, слот, вид, запись-итог, слот-итог)."""
    st = tuple(None if rb.SET[z, y, x, p] < 0 else (int(rb.SET[z, y, x, p]), int(rb.ID[z, y, x, p])) for p in range(4))
    out = []
    for step in path.split():
        how, part = step.split(":")
        p = mt.PARTS.index(part)
        cur = st[p]
        if cur is None:
            break
        sid, mid = cur
        recs = data.mcd(bt.sets[sid])
        r = recs[mid]
        ri = R.record(data, bt.sets[sid], mid)
        s2 = list(st)
        s2[p] = None
        to, to_slot = None, None
        if how == "die":
            if r["die"]:
                to_slot = recs[r["die"]]["type"] if r["die"] < len(recs) else p
                to = R.record(data, bt.sets[sid], r["die"])
                if to_slot < 4:              # Tile_Type 4+ движок кастует без проверки - путь дальше не ведём
                    s2[to_slot] = (sid, r["die"])
            if p == 0 and z == 0 and s2[0] is None:
                s2[0] = mt.SCORCHED
                to_slot = 0
                to = R.record(data, bt.sets[0], mt.SCORCHED[1])
        else:
            to_slot = recs[r["alt"]]["type"]
            to = R.record(data, bt.sets[sid], r["alt"])
            s2 = list(st)
            if to_slot < 4:                  # как Tile::openDoor: сначала alt в свою часть, потом очистка исходной
                s2[to_slot] = (sid, r["alt"])
            s2[p] = None
        out.append((ri, p, how, to, to_slot))
        st = tuple(s2)
    return out


def frame_name(R, f):
    s, n = R.frame_key[f]
    return "%s:%d" % (s, n)


def rec_name(R, r):
    s, n = R.rec_key[r]
    return "%s#%d" % (s, n)


def load_hashes():
    p = ROOT / "census" / "frame_hash.tsv"
    out = {}
    if p.exists():
        with open(p, encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                if len(row) >= 3 and row[1].isdigit():
                    out[(row[0].upper(), int(row[1]))] = row[2]
    return out


def write_tsv(path, head, rows):
    with open(path, "w", encoding=ENC_W, newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE, escapechar="\\")
        w.writerow(head)
        w.writerows(rows)


def top(counter, n=6):
    return ", ".join("%s %d" % (k, v) for k, v in counter.most_common(n))


def wall_role(e1, e2):
    if "corner" in (e1, e2) or "tee" in (e1, e2):
        return "corner"
    if e1 == e2 == "cont":
        return "mid"
    if e1 == e2 == "free":
        return "solo"
    return "end"


def write_all(out, R, battles, rec_cells, rec_battles, rec_terr, rec_maps, rec_special, adj, adj_border,
              adj_battles, wall_ends, floor_self, floor_all, floor_nb, state_obs, totals):
    hashes = load_hashes()
    write_tsv(out / "battles.tsv", ["battle", "saves", "n_saves", "mission", "script", "terrain", "size",
                                    "blocks", "special", "state_cells"],
              [[k, " ".join(sorted(v["saves"])[:5]), len(v["saves"]), v["mission"], v["script"], v["terrain"],
                v["size"], " ".join(v["blocks"]), " ".join(v["special"]), len(v["states"])]
               for k, v in sorted(battles.items(), key=lambda kv: kv[1]["mission"])])
    # записи
    slots = defaultdict(Counter)
    for (ri, p), n in rec_cells.items():
        slots[ri][mt.PARTS[p]] += n
    rows = []
    for ri, info in enumerate(R.rec_info):
        if ri not in slots:
            continue
        sl = slots[ri]
        col_ne = sum(n for k, n in sl.items() if info["type"] is not None and k != pname(info["type"]))
        rows.append([rec_name(R, ri), info["set"], info["rec"], info["type"], " ".join(map(str, info["frames"])),
                     int(info["anim"]), info["yoff"], info["t_level"], info["big_wall"], info["stop_los"],
                     info["door"], info["ufo_door"], info["die"], info["alt"],
                     " ".join("%s %d" % kv for kv in sl.most_common()), col_ne, sum(sl.values()),
                     len(rec_battles[ri]), len(rec_terr[ri]), top(rec_terr[ri]), len(rec_maps[ri]), top(rec_maps[ri]),
                     rec_special[ri]])
    rows.sort(key=lambda r: -r[16])
    write_tsv(out / "record_usage.tsv", ["record_id", "set", "rec", "tile_type", "frames", "animated", "p_level",
                                         "t_level", "big_wall", "stop_los", "door", "ufo_door", "die", "alt",
                                         "slots", "cells_not_in_tile_type_slot", "cells", "battles", "terrains_n",
                                         "terrains", "maps_n", "maps", "cells_in_craft_ufo"], rows)
    # кадры
    f_recs = defaultdict(set)
    f_slots = defaultdict(Counter)
    f_cells = Counter()
    f_battles = defaultdict(set)
    f_terr = defaultdict(Counter)
    f_maps = defaultdict(Counter)
    f_anim = defaultdict(set)          # кадр - фаза анимации каких записей
    f_plevel = defaultdict(set)
    for ri, info in enumerate(R.rec_info):
        if ri not in slots:
            continue
        f = info["frame0"]
        f_recs[f].add(ri)
        f_slots[f].update(slots[ri])
        f_cells[f] += sum(slots[ri].values())
        f_battles[f] |= rec_battles[ri]
        f_terr[f].update(rec_terr[ri])
        f_maps[f].update(rec_maps[ri])
        f_plevel[f].add(info["yoff"])
        if info["anim"]:
            for k in set(info["frames"][1:]):
                f_anim[R.frame((info["set"], k))].add(ri)
    roles = defaultdict(Counter)
    for (f, slot, e1, e2), n in wall_ends.items():
        roles[f][wall_role(e1, e2)] += n
    rows = []
    for f in sorted(set(f_cells) | set(f_anim), key=lambda f: -f_cells.get(f, 0)):
        s, n = R.frame_key[f]
        fa = floor_all.get(f, 0)
        nb = floor_nb.get(f, Counter())
        other = Counter({frame_name(R, k): v for k, v in nb.items() if k != f})
        rows.append([frame_name(R, f), s, n, hashes.get((s.upper(), n), ""),
                     " ".join(sorted(rec_name(R, r) for r in f_recs.get(f, ()))),
                     " ".join(sorted(rec_name(R, r) for r in f_anim.get(f, ()))),
                     " ".join("%s %d" % kv for kv in f_slots[f].most_common()),
                     " ".join(map(str, sorted(f_plevel.get(f, ())))), f_cells.get(f, 0), len(f_battles.get(f, ())),
                     len(f_terr.get(f, ())), top(f_terr.get(f, Counter())), len(f_maps.get(f, ())),
                     top(f_maps.get(f, Counter())),
                     "%.3f" % (floor_self.get(f, 0) / fa) if fa else "", fa, len(other), top(other, 5),
                     " ".join("%s %d" % kv for kv in roles[f].most_common()) if f in roles else ""])
    write_tsv(out / "frame_usage.tsv", ["frame_id", "set", "frame", "image_hash", "records", "anim_phase_of",
                                        "slots", "p_level", "cells", "battles", "terrains_n", "terrains", "maps_n",
                                        "maps", "floor_self_share", "floor_edges", "floor_other_neighbours_n",
                                        "floor_other_neighbours", "wall_roles"], rows)
    # соседство
    rows = []
    for k, n in adj.items():
        rel, pa, pb, fa, fb = k
        rows.append([frame_name(R, fa), mt.PARTS[pa], rel, frame_name(R, fb), mt.PARTS[pb], n, adj_border.get(k, 0),
                     adj_battles[k], int(R.frame_key[fa][0] != R.frame_key[fb][0])])
    rows.sort(key=lambda r: -r[5])
    write_tsv(out / "adjacency.tsv", ["frame_a", "slot_a", "rel", "frame_b", "slot_b", "count", "on_block_border",
                                      "battles", "cross_set"], rows)
    rows = [[frame_name(R, f), mt.PARTS[slot], e1, e2, wall_role(e1, e2), n]
            for (f, slot, e1, e2), n in sorted(wall_ends.items(), key=lambda kv: -kv[1])]
    write_tsv(out / "wall_roles.tsv", ["frame_id", "slot", "end_1", "end_2", "role", "segments"], rows)
    # состояния: из MCD для всех записей, что стоят на картах, плюс наблюдения
    rows = []
    seen = set()
    for ri, info in enumerate(R.rec_info):
        if ri not in slots:
            continue
        src_slot = slots[ri].most_common(1)[0][0]
        if info["die"]:
            rows.append(_state_row(R, ri, src_slot, "die", info["set"], info["die"], state_obs, seen))
        if info["door"]:
            rows.append(_state_row(R, ri, src_slot, "door", info["set"], info["alt"], state_obs, seen))
        if info["ufo_door"]:
            rows.append([rec_name(R, ri), src_slot, "ufo_door", rec_name(R, ri), src_slot, 0, "", 0])
        if info["anim"]:
            rows.append([rec_name(R, ri), src_slot, "anim", " ".join(map(str, info["frames"])), src_slot, 0, "", 0])
    for (ri, slot, how, to, to_slot), n in state_obs.items():
        if (ri, how, to) in seen or to is None:
            continue
        note = "scorch: z0 floor without die" if R.rec_key[to] == ("BLANKS", mt.SCORCHED[1]) else "only_in_saves"
        rows.append([rec_name(R, ri), pname(slot), how, rec_name(R, to), pname(to_slot),
                     int(slot != to_slot), note, n])
    write_tsv(out / "state_graph.tsv", ["record_from", "slot_from", "transition", "record_to", "slot_to",
                                        "slot_changes", "note", "observed_cells"], rows)
    totals_d = dict(totals)
    totals_d["frames_on_maps"] = len(f_cells)
    totals_d["records_on_maps"] = len(slots)
    with open(out / "summary.json", "w", encoding=ENC_W) as f:
        json.dump(totals_d, f, ensure_ascii=False, indent=1)
    print("итог:", totals_d)


def _state_row(R, ri, src_slot, how, set_name, target, state_obs, seen):
    key = (set_name, target)
    to = R.rec_id.get(key)
    info_to = R.rec_info[to] if to is not None else None
    to_slot = pname(info_to["type"]) if info_to else "?"
    obs = sum(n for (r, s, h, t, ts), n in state_obs.items() if r == ri and h == how and t == to) if to is not None else 0
    seen.add((ri, how, to))
    note = "" if to is not None else "target_not_seen"
    return ["%s#%d" % R.rec_key[ri], src_slot, how, "%s#%d" % key, to_slot, int(src_slot != to_slot), note, obs]


# ------------------------------------------------------------------ стыки по пикселям классики

# сдвиг соседа на экране (Camera::convertMapToScreen: x = (mx-my)*16, y = (mx+my)*8) и стороны пары
SEAM_RELS = {("E", 0): ((16, 8), "E", "W"), ("S", 0): ((-16, 8), "S", "N"),
             ("S", 1): ((-16, 8), "S", "N"), ("E", 2): ((16, 8), "E", "W")}
STRIP = 3          # полоса у грани, пикселей базы


class Frames:
    """Кадры наборов в RGB по палитре боя мастер-мода (delicious_regular), прозрачность - индекс 0."""

    def __init__(self, data):
        import xcom_sprites as xs
        self.xs, self.data, self.cache = xs, data, {}
        pal = data.find("Resources/Pals/delicious_regular.pal")
        self.pal = np.array(xs.load_palette_file(str(pal)), np.float32)

    def get(self, set_name, n):
        if set_name not in self.cache:
            p = self.data.find("TERRAIN/%s.PCK" % set_name)
            t = self.data.find("TERRAIN/%s.TAB" % set_name)
            self.cache[set_name] = self.xs.read_pck(str(p), str(t) if t else None) if p else []
        fr = self.cache[set_name]
        if n >= len(fr) or fr[n] is None:
            return None
        return np.array(fr[n], np.int32)


def seam_measure(fa, fb, off):
    """Два кадра рядом, как их кладёт движок: средний цвет полосы у общей грани с каждой стороны,
    разброс внутри полос и разница цвета соседних пикселей через грань против разницы внутри полосы."""
    dx, dy = off
    ox, oy = 16 - min(0, dx), 0
    H, W = 40 + abs(dy) + 2, 32 + abs(dx) + 32
    own = np.zeros((H, W), np.int8)
    idx = np.zeros((H, W), np.int32)
    for k, (f, (x0, y0)) in enumerate(((fa, (ox, oy)), (fb, (ox + dx, oy + dy)))):
        m = f > 0
        sub = own[y0:y0 + 40, x0:x0 + 32]
        sub[m] = k + 1
        idx[y0:y0 + 40, x0:x0 + 32][m] = f[m]
    A, B = own == 1, own == 2
    if not A.any() or not B.any():
        return None
    # пары соседей через грань (по горизонтали и вертикали)
    pa, pb = [], []
    for sy, sx in ((0, 1), (1, 0)):
        a1, b1 = own[:H - sy, :W - sx], own[sy:, sx:]
        i1, i2 = idx[:H - sy, :W - sx], idx[sy:, sx:]
        for u, v in ((1, 2), (2, 1)):
            m = (a1 == u) & (b1 == v)
            pa.append((i1 if u == 1 else i2)[m])
            pb.append((i2 if u == 1 else i1)[m])
    pa, pb = np.concatenate(pa), np.concatenate(pb)
    if len(pa) < 4:
        return None
    return idx, A, B, pa, pb


def seam_stats(pal, res):
    idx, A, B, pa, pb = res
    from numpy.lib.stride_tricks import sliding_window_view as swv
    pad = np.pad(B, STRIP)
    nb = swv(pad, (2 * STRIP + 1, 2 * STRIP + 1)).any(axis=(-1, -2))
    pad = np.pad(A, STRIP)
    na = swv(pad, (2 * STRIP + 1, 2 * STRIP + 1)).any(axis=(-1, -2))
    sa, sb = pal[idx[A & nb]], pal[idx[B & na]]
    dmean = float(np.linalg.norm(sa.mean(0) - sb.mean(0)))
    tex = float((sa.std(0).mean() + sb.std(0).mean()) / 2)
    cross = float(np.linalg.norm(pal[pa] - pal[pb], axis=1).mean())
    return dmean, tex, cross, len(pa)


def seams(cat):
    """Для каждой пары соседних кадров (пол E и S, west вдоль S, north вдоль E) - непрерывен ли
    материал классики через грань. Пишет seams.tsv."""
    pairs = []
    with open(cat / "adjacency.tsv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if r["slot_a"] != r["slot_b"]:
                continue
            p = mt.PARTS.index(r["slot_a"])
            if (r["rel"], p) in SEAM_RELS:
                pairs.append((r["frame_a"], r["frame_b"], r["rel"], p, int(r["count"]), int(r["on_block_border"])))
    data = mt.Data(json.loads((cat / "summary.json").read_text(encoding="utf-8-sig"))["mods"])
    fr = Frames(data)
    rows = []
    for a, b, rel, p, n, nb in pairs:
        (sa, ka), (sb, kb) = a.rsplit(":", 1), b.rsplit(":", 1)
        fa, fb = fr.get(sa, int(ka)), fr.get(sb, int(kb))
        if fa is None or fb is None:
            rows.append([a, b, rel, mt.PARTS[p], n, nb, "", "", "", 0])
            continue
        res = seam_measure(fa, fb, SEAM_RELS[(rel, p)][0])
        if res is None:
            rows.append([a, b, rel, mt.PARTS[p], n, nb, "", "", "", 0])
            continue
        dmean, tex, cross, np_ = seam_stats(fr.pal, res)
        rows.append([a, b, rel, mt.PARTS[p], n, nb, "%.1f" % dmean, "%.1f" % tex, "%.1f" % cross, np_])
    write_tsv(cat / "seams.tsv", ["frame_a", "frame_b", "rel", "slot", "count", "on_block_border", "dmean",
                                  "texture", "cross_diff", "edge_pairs"], rows)
    print("стыков:", len(rows), "по клеткам:", sum(r[4] for r in rows))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("saves", nargs="+")
    b.add_argument("--out", default=str(ROOT / "census" / "maps"))
    w = sp.add_parser("write", help="переписать TSV из _state.pickle без прохода по сейвам")
    w.add_argument("--out", default=str(ROOT / "census" / "maps"))
    s = sp.add_parser("seams", help="стыки одинаковых слотов по пикселям классики -> seams.tsv")
    s.add_argument("--out", default=str(ROOT / "census" / "maps"))
    a = ap.parse_args()
    if a.cmd == "write":
        with open(Path(a.out) / "_state.pickle", "rb") as f:
            write_all(Path(a.out), *pickle.load(f))
        return
    if a.cmd == "seams":
        seams(Path(a.out))
        return
    saves = []
    for s in a.saves:
        if s.startswith("@"):            # список сейвов файлом: длинная командная строка Windows режется
            saves += [Path(t) for t in Path(s[1:]).read_text(encoding="utf-8-sig").split("\n") if t.strip()]
            continue
        p = Path(s)
        saves += sorted(p.glob("*.sav")) if p.is_dir() else [p]
    build(saves, Path(a.out))


if __name__ == "__main__":
    main()
