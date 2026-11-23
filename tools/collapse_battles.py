"""Собранные карты для переписи обрушения (этап 0, docs/research/building-collapse-task-2026-10-07.md).

Перепись блоков (collapse_census.py) не видит опор между блоками: блок может продолжаться соседним или стоять
на нём. Здесь карты собирает сам движок: стенд ИИ (tools/ai_probe.py, сборка build-ai) поднимает случайный бой
мода по зерну с закреплённой миссией, игрок сразу отдаёт ход, ИИ ходит один раз, бой сохраняется
(OXCE_AI_PROBE_SAVE). В сейве карта целиком: список наборов MCD и номера частей каждой клетки
(SavedBattleGame::load, Tile::loadBinary). src/ не трогается, игра невидима (ai_probe.Hidden, R-124).

  py -3.13 tools/collapse_battles.py gen --missions STR_LOC_BANDIT_TOWN --seeds 1-6 [--jobs 2] [--terrain FOREST]
  py -3.13 tools/collapse_battles.py list
Сейвы - census/collapse/battles/<миссия>_<зерно>.sav, сводка - census/collapse/battles/index.tsv.
"""
import argparse
import base64
import os
import re
import shutil
import struct
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
OUT = ROOT / "census" / "collapse" / "battles"
ENC = "utf-8-sig"
KINDS = ("f", "w", "n", "o")                 # O_FLOOR, O_WESTWALL, O_NORTHWALL, O_OBJECT - порядок ID[] в Tile


def seeds_of(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


# ------------------------------------------------------------------ чтение сейва боя

def _scalar(text, key):
    m = re.search(r"^  %s: (.*)$" % re.escape(key), text, re.M)
    if not m:
        return None
    v = m.group(1).strip()
    if v.startswith('"') and v.endswith('"'):
        v = bytes(v[1:-1], "utf-8").decode("unicode_escape")
    return v


def _num(v):
    """Размеры полей в сейве записаны строкой с символом: "\\x04" или "\\x02"."""
    if v is None:
        return None
    return ord(v) if len(v) == 1 and not v.isdigit() else int(v)


def read_battle(path):
    """Собранная карта из сейва: размеры, наборы MCD и клетки {(x, y, z): [(set, idx) или None] * 4}."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    i = text.index("\nbattleGame:")
    bg = text[i:]
    sx, sy, sz = int(_scalar(bg, "width")), int(_scalar(bg, "length")), int(_scalar(bg, "height"))
    mission = _scalar(bg, "missionType")
    m = re.search(r"^  mapdatasets:\n((?:    - .*\n)+)", bg, re.M)
    sets = [ln.strip()[2:].strip().strip("'\"") for ln in m.group(1).splitlines()]
    key = {k: _num(_scalar(bg, k)) for k in ("tileIndexSize", "tileTotalBytesPer", "tileFireSize",
                                               "tileSmokeSize", "tileIDSize", "tileSetIDSize",
                                               "tileBoolFieldsSize")}
    total = int(_scalar(bg, "totalTiles"))
    m = re.search(r"^  binTiles: !binary \|?-?\n((?:    .*\n)+)", bg, re.M)
    if m:
        raw = base64.b64decode("".join(ln.strip() for ln in m.group(1).splitlines()))
    else:
        raw = base64.b64decode(_scalar(bg, "binTiles").replace("!binary", "").strip().strip('"'))
    fmt = {1: "b", 2: "<h", 4: "<i"}
    ufmt = {1: "B", 2: "<H", 4: "<I"}
    cells = {}
    per = key["tileTotalBytesPer"]
    for t in range(total):
        p = t * per
        idx = struct.unpack_from(ufmt[key["tileIndexSize"]], raw, p)[0]
        p += key["tileIndexSize"]
        ids, sids = [], []
        for _ in range(4):
            ids.append(struct.unpack_from(fmt[key["tileIDSize"]], raw, p)[0]); p += key["tileIDSize"]
        for _ in range(4):
            sids.append(struct.unpack_from(fmt[key["tileSetIDSize"]], raw, p)[0]); p += key["tileSetIDSize"]
        z, rest = divmod(idx, sx * sy)
        y, x = divmod(rest, sx)
        cells[(x, y, z)] = [None if ids[k] < 0 or sids[k] < 0 else (sets[sids[k]], ids[k]) for k in range(4)]
    head = {k: v for k, v in (ln.split(": ", 1) for ln in text[:i].splitlines() if ": " in ln and not ln.startswith(" "))}
    return {"sx": sx, "sy": sy, "sz": sz, "mission": mission, "sets": sets, "cells": cells,
            "turn": _scalar(bg, "turn"), "head": head}


# ------------------------------------------------------------------ генерация

def gen_one(mission, seed, timeout, terrain=""):
    import ai_probe
    name = "collapse_%s_%s%d" % (re.sub(r"[^A-Za-z0-9]+", "_", mission), (terrain + "_") if terrain else "", seed)
    r = ai_probe.run(None, turns=1, save_as=name + ".sav", name=name, timeout=timeout, bot=False,
                     seed=seed, mission=mission)
    battle = r.tagged("[AIPROBE] battle")
    info = ai_probe.fields(battle[0]) if battle else {}
    dst = OUT / (name + ".sav")
    if r.saved:
        shutil.copyfile(r.saved, dst)
    stuck = r.tagged("[AIPROBE] stuck")
    return {"mission": mission, "seed": seed, "file": dst.name if r.saved else "",
            "got": info.get("mission", ""), "terrain": info.get("terrain", ""),
            "seconds": "%.0f" % r.seconds, "note": stuck[0] if stuck else ("" if r.saved else "нет сейва")}


def cmd_gen(a):
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(m, s) for m in a.missions.split(",") for s in seeds_of(a.seeds)]
    idx = OUT / "index.tsv"
    lock = threading.Lock()
    cols = ("mission", "seed", "file", "got", "terrain", "seconds", "note")
    if not idx.exists():
        idx.write_text("\t".join(cols) + "\n", encoding=ENC)

    if a.terrain:
        os.environ["OXCE_AI_TERRAIN"] = a.terrain      # NewBattleState: террейн миссии закреплён, иначе случайный

    def work(job):
        row = gen_one(job[0], job[1], a.timeout, a.terrain)
        with lock:
            with open(idx, "a", encoding="utf-8", newline="") as f:
                f.write("\t".join(str(row[c]) for c in cols) + "\n")
            print("\t".join(str(row[c]) for c in cols), flush=True)
        return row

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(work, jobs))


def cmd_list(a):
    for p in sorted(OUT.glob("*.sav")):
        b = read_battle(p)
        print(p.name, b["mission"], "%dx%dx%d" % (b["sx"], b["sy"], b["sz"]), "клеток", len(b["cells"]),
              "наборов", len(b["sets"]))


# ------------------------------------------------------------------ собранная карта против блоков

class Data:
    """Данные мода один раз на прогон: MCD с патчами, LOFT, террейны и их блоки."""

    def __init__(self, a):
        import collapse_census as cc
        self.cc = cc
        self.mod_dir, self.files, _, self.loft = cc.open_data(a)
        self.terr = cc.collect(self.mod_dir)
        self.mcd, self.sizes, self.blocks = {}, {}, {}

    def recs(self, s):
        return self.cc.read_mcd(self.files, s, self.loft, self.mcd)

    def terrain_blocks(self, tname):
        if tname not in self.blocks:
            out = []
            kind, t = self.terr.get(tname, (None, None))
            for b in (t or {}).get("mapBlocks") or []:
                bname = b.get("name") if isinstance(b, dict) else None
                if not bname:
                    continue
                blk, err = self.cc.load_block(self.files, tname, kind, t, bname, self.mcd, self.loft, self.sizes)
                if blk is not None and blk.parts:
                    out.append(blk)
            self.blocks[tname] = out
        return self.blocks[tname]

    def candidates(self, battle, main):
        """Блоки террейна боя и всех террейнов, чьи наборы MCD целиком есть в сейве (скрипт карты
        берёт блоки и из чужих террейнов). Корабли и НЛО не ищем - пилот без них."""
        have = {s.upper() for s in battle["sets"]}
        names = [main] if main in self.terr else []
        for tname, (kind, t) in sorted(self.terr.items()):
            if kind != "terrain" or tname == main:
                continue
            ds = [s.upper() for s in t.get("mapDataSets") or []]
            if ds and set(ds) <= have:
                names.append(tname)
        seen, out = set(), []
        for tname in names:
            for blk in self.terrain_blocks(tname):
                sig = (blk.name.upper(), tuple(sorted({p["set"].upper() for p in blk.parts.values()})))
                if sig not in seen:
                    seen.add(sig)
                    out.append(blk)
        return out


def map_block(d, battle, name):
    """Собранная карта как один большой блок модели опор (те же классы частей, тот же evaluate)."""
    cc = d.cc
    blk = cc.Block(battle.get("terrain", ""), "map", name, battle["sx"], battle["sy"], battle["sz"])
    for (x, y, z), parts in battle["cells"].items():
        for k, p in zip(KINDS, parts):
            if p is None or p[0].upper() == "BLANKS":
                continue
            recs = d.recs(p[0])
            if p[1] < len(recs):
                blk.add(k, x, y, z, p[0], p[1], recs[p[1]])
    return blk


def find_placements(mblk, blocks, thr):
    """Где на карте стоит каждый блок: сдвиг по сетке 10 клеток и по высоте, сходство по Жаккару
    частей (набор, номер) - бой мог что-то снести, корабль мог лечь поверх. Жадно без наложения."""
    mp = {key: (v["set"].upper(), v["idx"]) for key, v in mblk.parts.items()}
    col = defaultdict(int)                       # (x, y, z) -> частей в клетке карты
    for (k, x, y, z) in mp:
        col[(x, y, z)] += 1
    cand = []
    for blk in blocks:
        bp = [(key, (v["set"].upper(), v["idx"])) for key, v in blk.parts.items()]
        sample = bp[:: max(1, len(bp) // 24)]
        for oz in range(0, mblk.sz - blk.sz + 1):
            for oy in range(0, mblk.sy - blk.sy + 1, 10):
                for ox in range(0, mblk.sx - blk.sx + 1, 10):
                    hit = sum(mp.get((k, x + ox, y + oy, z + oz)) == v for (k, x, y, z), v in sample)
                    if hit < 0.5 * len(sample):
                        continue
                    m = sum(mp.get((k, x + ox, y + oy, z + oz)) == v for (k, x, y, z), v in bp)
                    nmap = sum(col.get((x, y, z), 0) for z in range(oz, oz + blk.sz)
                               for y in range(oy, oy + blk.sy) for x in range(ox, ox + blk.sx))
                    jac = m / max(1, len(bp) + nmap - m)
                    if jac >= thr:
                        cand.append((jac, len(bp), blk, ox, oy, oz, m, nmap))
    cand.sort(key=lambda c: (-c[0], -c[1]))
    used, out = set(), []
    for c in cand:
        _, _, blk, ox, oy, oz, _, _ = c
        cells = {(x, y) for x in range(ox, ox + blk.sx) for y in range(oy, oy + blk.sy)}
        if cells & used:
            continue
        used |= cells
        out.append(c)
    return out


def shift(key, o):
    return (key[0], key[1] + o[0], key[2] + o[1], key[3] + o[2])


def crop(cc, mblk, box, keys_sup, info, removed, base):
    """Вырезка карты для листа: части в прямоугольнике, опора - посчитанная по всей карте."""
    x0, y0, x1, y1 = box
    c = cc.Block(mblk.terrain, "map", mblk.name, x1 - x0, y1 - y0, mblk.sz)
    back = {}
    for key, v in mblk.parts.items():
        k, x, y, z = key
        if x0 <= x < x1 and y0 <= y < y1:
            nk = (k, x - x0, y - y0, z)
            c.parts[nk] = v
            c.lv[z][k][(x - x0, y - y0)] = nk
            back[key] = nk
    tr = lambda s: {back[k] for k in s if k in back}
    return c, (tr(keys_sup), {back[k]: v for k, v in info.items() if k in back}), tr(removed), tr(base)


def cmd_maps(a):
    import collapse_census as cc
    d = Data(a)
    C, L, _ = cc.MAIN_PRESET
    out = ROOT / "census" / "collapse" / "maps"
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    terrain_of = {}
    idx = OUT / "index.tsv"
    if idx.exists():
        for ln in idx.read_text(encoding=ENC).splitlines()[1:]:
            f = ln.split("\t")
            if len(f) > 4 and f[2]:
                terrain_of[f[2]] = f[4]
    expect = []
    exp_path = ROOT / "census" / "collapse" / "expect.tsv"
    lines = exp_path.read_text(encoding=ENC).splitlines()
    head = lines[0].split("\t")
    for ln in lines[1:]:
        if ln.strip() and not ln.startswith("#"):
            expect.append(dict(zip(head, ln.split("\t"))))
    by_block = defaultdict(list)
    for e in expect:
        by_block[e["block"].upper()].append(e)

    rows_map, rows_pl, rows_exp, rows_diff = [], [], [], []
    saves = sorted(OUT.glob("*.sav"))
    if a.only:
        saves = [p for p in saves if any(s in p.name for s in a.only.split(","))]
    nsheet = 0
    for path in saves:
        battle = read_battle(path)
        tname = terrain_of.get(path.name, "")
        battle["terrain"] = tname
        mblk = map_block(d, battle, path.stem)
        sup, info = cc.evaluate(mblk, C=C, L=L)
        up = [k for k in mblk.parts if k[3] > 0]
        uns = [k for k in up if k not in sup]
        blocks = d.candidates(battle, tname)
        pls = find_placements(mblk, blocks, a.thr)
        covered = sum(blk.sx * blk.sy for _, _, blk, *_ in pls)
        # вне найденных блоков - корабль игрока, НЛО, блоки чужих террейнов: пилот их не берёт
        inb = lambda k: any(ox <= k[1] < ox + blk.sx and oy <= k[2] < oy + blk.sy for _, _, blk, ox, oy, *_ in pls)
        up_in = [k for k in up if inb(k)]
        uns_in = [k for k in uns if inb(k)]
        rows_map.append((path.name, battle["mission"], tname, "%dx%dx%d" % (battle["sx"], battle["sy"], battle["sz"]),
                         len(mblk.parts), len(up), len(uns), round(len(uns) / max(1, len(up)), 4),
                         len(up_in), len(uns_in), round(len(uns_in) / max(1, len(up_in)), 4),
                         len(blocks), len(pls), round(covered / (battle["sx"] * battle["sy"]), 3)))
        print("%s %s: выше земли %d, не опёрто %d (%.2f%%); в найденных блоках %d, не опёрто %d (%.2f%%); "
              "блоков %d, покрыто %.0f%% площади"
              % (path.name, tname, len(up), len(uns), 100 * len(uns) / max(1, len(up)), len(up_in), len(uns_in),
                 100 * len(uns_in) / max(1, len(up_in)), len(pls), 100 * covered / (battle["sx"] * battle["sy"])),
              flush=True)
        for jac, _, blk, ox, oy, oz, m, nmap in pls:
            o = (ox, oy, oz)
            bsup, binfo = cc.evaluate(blk, C=C, L=L)
            same = [k for k, v in blk.parts.items()
                    if shift(k, o) in mblk.parts and mblk.parts[shift(k, o)]["set"].upper() == v["set"].upper()
                    and mblk.parts[shift(k, o)]["idx"] == v["idx"]]
            cnt = defaultdict(list)
            for k in same:
                if k[3] + oz == 0:
                    continue
                cnt[("S" if k in bsup else "U") + ("S" if shift(k, o) in sup else "U")].append(k)
            rows_pl.append((path.name, blk.terrain, blk.name, ox, oy, oz, round(jac, 3), len(blk.parts), m,
                            len(blk.parts) - len(same), len(cnt["SS"]), len(cnt["UU"]), len(cnt["US"]),
                            len(cnt["SU"])))
            for cat in ("US", "SU"):
                for k in cnt[cat]:
                    mk = shift(k, o)
                    rows_diff.append((path.name, blk.terrain, blk.name, cat, "%s:%d:%d:%d" % k,
                                      "%s:%d:%d:%d" % mk, blk.parts[k]["cls"],
                                      cc.reason(blk, k, bsup, binfo) if cat == "US" else
                                      cc.reason(mblk, mk, sup, info)))
            for e in by_block.get(blk.name.upper(), []):
                rm_b = cc.select(blk, e["remove"])
                ok = lambda ks: {shift(k, o) for k in ks if k in same}
                rm = ok(rm_b)
                mf = ok(cc.select(blk, e.get("must_fall", ""))) - rm
                ms = ok(cc.select(blk, e.get("must_stand", ""))) - rm
                sup2, info2 = cc.evaluate(mblk, frozenset(rm), C=C, L=L)
                fallen = {k for k in sup if k not in sup2 and k not in rm}
                inside = lambda k: ox <= k[1] < ox + blk.sx and oy <= k[2] < oy + blk.sy
                miss_f = sorted(k for k in mf if k in sup2)
                miss_s = sorted(k for k in ms if k not in sup2 and k in sup)
                hung0 = sorted(k for k in ms if k not in sup)
                verdict = "PASS" if not miss_f and not miss_s else "FAIL"
                if verdict == "PASS" and hung0:
                    verdict = "PASS*"
                if not rm or not (mf | ms):
                    verdict = "EMPTY"
                # тот же сценарий на блоке отдельно - для сравнения
                b2, _ = cc.evaluate(blk, frozenset(rm_b), C=C, L=L)
                bmf = cc.select(blk, e.get("must_fall", "")) - rm_b
                bms = cc.select(blk, e.get("must_stand", "")) - rm_b
                bv = "PASS" if not [k for k in bmf if k in b2] and not [k for k in bms if k not in b2 and k in bsup] else "FAIL"
                out_f = sorted(k for k in fallen if not inside(k))
                rows_exp.append((e["id"], path.name, blk.terrain, blk.name, "%d,%d,%d" % o, bv, verdict,
                                 len(rm_b), len(rm), len(fallen), len(mf), len(miss_f),
                                 " ".join("%s:%d:%d:%d" % k for k in miss_f[:20]), len(ms), len(miss_s),
                                 " ".join("%s:%d:%d:%d" % k for k in miss_s[:20]), len(hung0), len(out_f),
                                 " ".join("%s:%d:%d:%d" % k for k in out_f[:20])))
                print("  %s %s в %s (%d,%d,%d): блок %s, карта %s; упало %d, из них за блоком %d"
                      % (e["id"], blk.name, path.name, ox, oy, oz, bv, verdict, len(fallen), len(out_f)))
                if a.sheets:
                    box = (max(0, ox - 3), max(0, oy - 3), min(mblk.sx, ox + blk.sx + 3), min(mblk.sy, oy + blk.sy + 3))
                    cb, pre, crm, cbase = crop(cc, mblk, box, sup2, info2, rm, sup)
                    cc.sheet(cb, str(out / "sheets" / ("expect_%s_%s.png" % (e["id"], path.stem))), removed=crm,
                             base=cbase, C=C, L=L, pre=pre, org=(box[0], box[1], 0),
                             title="%s %s на карте %s (%d,%d,%d): блок %s, карта %s" % (
                                 e["id"], blk.name, path.stem, ox, oy, oz, bv, verdict))
            if a.sheets and (cnt["US"] or cnt["SU"]) and nsheet < a.limit:
                nsheet += 1
                box = (max(0, ox - 3), max(0, oy - 3), min(mblk.sx, ox + blk.sx + 3), min(mblk.sy, oy + blk.sy + 3))
                cb, pre, crm, cbase = crop(cc, mblk, box, sup, info, set(), sup)
                cc.sheet(cb, str(out / "sheets" / ("place_%s_%s_%d_%d.png" % (path.stem, blk.name, ox, oy))),
                         C=C, L=L, pre=pre, org=(box[0], box[1], 0),
                         title="%s на карте %s (%d,%d,%d): блок отдельно не опёрто %d, на карте %d; US %d SU %d" % (
                             blk.name, path.stem, ox, oy, oz, len(cnt["UU"]) + len(cnt["US"]),
                             len(cnt["UU"]) + len(cnt["SU"]), len(cnt["US"]), len(cnt["SU"])))
    cc.write_tsv(str(out / "maps.tsv"), ["save", "mission", "terrain", "size", "parts", "parts_up", "unsupported",
                                         "share", "up_in_blocks", "unsupported_in_blocks", "share_in_blocks",
                                         "candidate_blocks", "placements", "covered"], rows_map)
    cc.write_tsv(str(out / "placements.tsv"), ["save", "terrain", "block", "x", "y", "z", "jaccard", "block_parts",
                                               "matched", "changed", "SS", "UU", "US", "SU"], rows_pl)
    cc.write_tsv(str(out / "support_diff.tsv"), ["save", "terrain", "block", "cat", "block_key", "map_key", "cls",
                                                 "reason"], rows_diff)
    cc.write_tsv(str(out / "expect_maps.tsv"),
                 ["id", "save", "terrain", "block", "at", "block_verdict", "map_verdict", "removed_block",
                  "removed_map", "fallen", "must_fall_n", "should_fall_but_stood", "list", "must_stand_n",
                  "should_stand_but_fell", "list", "stand_hung_at_start", "fallen_outside_block", "list"], rows_exp)
    tot = defaultdict(int)
    for r in rows_pl:
        for i, c in enumerate(("SS", "UU", "US", "SU")):
            tot[c] += r[10 + i]
    print("итого по найденным блокам: опёрто и там и там %d, не опёрто и там и там %d, "
          "блок отдельно висит - на карте держится %d, блок держится - на карте висит %d"
          % (tot["SS"], tot["UU"], tot["US"], tot["SU"]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("--missions", required=True)
    g.add_argument("--seeds", default="1-4")
    g.add_argument("--jobs", type=int, default=2)
    g.add_argument("--timeout", type=int, default=600)
    g.add_argument("--terrain", default="", help="закрепить террейн миссии (OXCE_AI_TERRAIN), имя сейва с ним")
    sub.add_parser("list")
    m = sub.add_parser("maps")
    m.add_argument("--install", default=os.path.join("Пиратки", "Dioxine_XPiratez"))
    m.add_argument("--mod", default="Piratez")
    m.add_argument("--master", default="xcom1")
    m.add_argument("--thr", type=float, default=0.8, help="порог сходства блока с местом карты")
    m.add_argument("--only", default="", help="подстроки имён сейвов через запятую")
    m.add_argument("--sheets", action="store_true")
    m.add_argument("--limit", type=int, default=30, help="листов мест с расхождением опор")
    a = ap.parse_args()
    {"gen": cmd_gen, "list": cmd_list, "maps": cmd_maps}[a.cmd](a)


if __name__ == "__main__":
    main()
