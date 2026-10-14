"""Отложенные карты для проверки модели обрушения (этап 0f, census/collapse/stage0f/holdout.lock.txt).

Те же шаги, что у 90 карт настройки, но в своих каталогах, чтобы отложенные карты не попали в настройку:
  py -3.13 tools/collapse_holdout.py gen --seeds 14-17 [--jobs 2]   - бои стенда ИИ (невидимо, ai_probe.Hidden)
  py -3.13 tools/collapse_holdout.py source                         - исходная карта: клетки найденных блоков MAP
                                                                       возвращены к виду до первого хода
Сейвы - census/collapse/holdout/battles, исходные карты - census/collapse/holdout/source/<сейв>.pkl,
проверенные клетки - census/collapse/holdout/verified. Восстановление - как scratchpad cb_geom.py этапа 0c:
часть блока, которую бой заменил записью die или alt, убрал (die 0) или открыл (дверь), возвращается;
вне найденных блоков - как в сейве («непроверенная клетка»)."""
import argparse
import collections
import os
import pickle
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)
import collapse_battles as cb      # noqa: E402
import collapse_census as cc       # noqa: E402

ENC = "utf-8-sig"
HOLD = "census/collapse/holdout"
MISSIONS = ("STR_ERIDIAN_TERROR,STR_LOC_BANDIT_SALOON_TEMPERATE,STR_LOC_BANDIT_TOWN,STR_LOC_CHURCH_OUTPOST_TEMPERATE,"
            "STR_LOC_CRACKHOUSE,STR_LOC_DOOMED_FARM,STR_LOC_EMANSION,STR_LOC_EMANSION_MAG,"
            "STR_LOC_EUROSYNDICATE_ELIMINATION,STR_LOC_GHOUL_REFINERY")
KIDX = {k: i for i, k in enumerate(cb.KINDS)}
DESTROY = ("die", "gone_die0", "gone_has_die")


def game_args():
    return types.SimpleNamespace(install=os.path.join("Пиратки", "Dioxine_XPiratez"), mod="Piratez", master="xcom1")


def cmd_gen(a):
    cb.OUT = ROOT / HOLD / "battles"
    cb.cmd_gen(types.SimpleNamespace(missions=a.missions, seeds=a.seeds, jobs=a.jobs, timeout=a.timeout))


def chain(d, s, idx, field):
    recs = d.recs(s)
    out, i = [], idx
    for _ in range(6):
        if not (0 <= i < len(recs)):
            break
        n = recs[i][field]
        if not n or n == i or n in out:
            break
        out.append(n)
        i = n
    return out


def cmd_source(a):
    d = cb.Data(game_args())
    os.makedirs(HOLD + "/source", exist_ok=True)
    terrain_of = {}
    for ln in open(HOLD + "/battles/index.tsv", encoding=ENC).read().splitlines()[1:]:
        f = ln.split("\t")
        if len(f) > 4 and f[2]:
            terrain_of[f[2]] = f[4]
    rows = []
    for path in sorted(os.listdir(HOLD + "/battles")):
        if not path.endswith(".sav"):
            continue
        bt = cb.read_battle(HOLD + "/battles/" + path)
        tname = terrain_of.get(path, "")
        bt["terrain"] = tname
        mblk = cb.map_block(d, bt, path[:-4])
        pls = cb.find_placements(mblk, d.candidates(bt, tname), 0.8)
        cnt = collections.Counter()
        src = {c: list(p) for c, p in bt["cells"].items()}
        covered = set()
        blocks = []
        for jac, _, blk, ox, oy, oz, m, nmap in pls:
            blocks.append((blk.terrain, blk.name, ox, oy, oz))
            bcell = collections.defaultdict(dict)
            for (k, x, y, z), v in blk.parts.items():
                bcell[(x + ox, y + oy, z + oz)][k] = (v["set"], v["idx"])
            for z in range(blk.sz):
                for y in range(blk.sy):
                    for x in range(blk.sx):
                        c = (x + ox, y + oy, z + oz)
                        covered.add(c)
                        B = bcell.get(c, {})
                        mp = bt["cells"].get(c) or [None] * 4
                        M = {k: mp[KIDX[k]] for k in cb.KINDS
                             if mp[KIDX[k]] and mp[KIDX[k]][0].upper() != "BLANKS"}
                        S0 = dict(M)
                        um = {k: v for k, v in M.items()
                              if not (k in B and B[k][0].upper() == v[0].upper() and B[k][1] == v[1])}
                        ub = {k: v for k, v in B.items()
                              if not (k in M and M[k][0].upper() == v[0].upper() and M[k][1] == v[1])}
                        for k, (s, i) in sorted(ub.items()):
                            hit = None
                            for cat, test in (("slot", lambda q: q[1] == i),
                                              ("alt", lambda q: q[1] in chain(d, s, i, "alt")),
                                              ("die", lambda q: q[1] in chain(d, s, i, "die"))):
                                for mk, q in um.items():
                                    if q[0].upper() == s.upper() and test(q):
                                        hit = (cat, mk, q)
                                        break
                                if hit:
                                    break
                            if hit:
                                cat, mk, q = hit
                                del um[mk]
                                S0.pop(mk, None)
                                S0[k] = (s, i)
                            elif k in um:
                                cat = "other"
                                um.pop(k)
                            else:
                                cat = "gone_die0" if not d.recs(s)[i]["die"] else "gone_has_die"
                                S0[k] = (s, i)
                            cnt[cat] += 1
                        src[c] = [S0.get(k) for k in cb.KINDS]
        with open(HOLD + "/source/" + path[:-4] + ".pkl", "wb") as f:
            pickle.dump({"sx": bt["sx"], "sy": bt["sy"], "sz": bt["sz"], "terrain": tname, "cells": src,
                         "covered": covered, "blocks": blocks}, f)
        destroyed = sum(cnt[c] for c in DESTROY)
        rows.append([path, tname, len(pls), destroyed, cnt["other"]])
        print(path, tname, "мест блоков", len(pls), "возвращено разрушенного", destroyed, "прочее", cnt["other"],
              flush=True)
    cc.write_tsv(HOLD + "/source_summary.tsv", ["save", "terrain", "placements", "restored_destroyed", "other"], rows)


def load_map(d, name, roles, apply_roles):
    bt = cb.read_battle(HOLD + "/battles/" + name)
    with open(HOLD + "/source/" + name[:-4] + ".pkl", "rb") as f:
        src = pickle.load(f)
    bt["cells"] = src["cells"]
    bt["terrain"] = src["terrain"]
    return apply_roles(cb.map_block(d, bt, name[:-4]), roles), src


def verified_cells(d, name, m, src):
    """Как collapse_v2.verified_cells, со своим кэшем; значение - (террейн, имя блока)."""
    cache = HOLD + "/verified/" + name[:-4] + ".pkl"
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            return pickle.load(f)
    pls = cb.find_placements(m, d.candidates({"sets": sorted({p["set"] for p in m.parts.values()})},
                                             src["terrain"]), 0.8)
    out = {}
    for jac, _, blk, ox, oy, oz, mm, nmap in pls:
        bcell = collections.defaultdict(dict)
        for (k, x, y, z), v in blk.parts.items():
            bcell[(x + ox, y + oy, z + oz)][k] = (v["set"].upper(), v["idx"])
        for z in range(blk.sz):
            for y in range(blk.sy):
                for x in range(blk.sx):
                    c = (x + ox, y + oy, z + oz)
                    have = {}
                    for k in cc.KINDS:
                        key = m.lv[c[2]][k].get((c[0], c[1])) if c[2] < m.sz else None
                        if key:
                            have[k] = (m.parts[key]["set"].upper(), m.parts[key]["idx"])
                    if have == bcell.get(c, {}):
                        out[c] = (blk.terrain, blk.name)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "wb") as f:
        pickle.dump(out, f)
    return out


def names():
    return sorted(n[:-4] + ".sav" for n in os.listdir(HOLD + "/source") if n.endswith(".pkl"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("--missions", default=MISSIONS)
    g.add_argument("--seeds", default="14-17")
    g.add_argument("--jobs", type=int, default=2)
    g.add_argument("--timeout", type=int, default=600)
    sub.add_parser("source")
    a = ap.parse_args()
    {"gen": cmd_gen, "source": cmd_source}[a.cmd](a)


if __name__ == "__main__":
    main()
