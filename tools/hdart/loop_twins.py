#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Петли анимации террейна: кадры с одинаковой классикой обязаны иметь одинаковый HD.

Запись MCD перебирает кадры Frame[0..7] каждые 100 мс (Tile::animate). Часто в петле
есть кадры, у которых классика побайтно одна (NUKE_CITY_2 запись 10: петля 11,12,12,...,
кадры 11 и 12 одинаковы). В классике смены кадра не видно. А HD-кадры 11 и 12 рисовались
порознь и разные - на стене раз в 0,8 с на 100 мс вспыхивают точки (R-338).

Близнецы ищутся только среди кадров, которые стоят в одной петле: одинаковая классика
без общей петли не мигает, её не трогаем (минимальный диф). Общий HD берётся у кадра,
который на экране чаще всех: число мест в Frame[0..7] по всем записям набора, при
равенстве - младший номер. Его PNG и варианты .vN копируются близнецам; варианты
близнеца, которых у основы нет, снимаются. Правка идёт через манифест пака (build_hd_pack:
stage, install в обе копии мода hd), прямой записи в папку пака нет.

    py -3.13 tools/hdart/loop_twins.py                   # проверка обеих копий мода hd, код 1 - есть мигание
    py -3.13 tools/hdart/loop_twins.py --fix             # выровнять
    py -3.13 tools/hdart/loop_twins.py --sets NUKE_CITY_2 --fix
"""
import argparse
import hashlib
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import xcom_sprites as xs                                           # noqa: E402

INST = ROOT / "Пиратки" / "Dioxine_XPiratez"
MCD_DIRS = [INST / "user/mods/Piratez/TERRAIN", INST / "standard/xcom1/TERRAIN", INST / "UFO/TERRAIN"]
COPIES = {"установка": INST / "user/mods/hd/hd/TERRAIN", "репозиторий": ROOT / "user/mods/hd/hd/TERRAIN"}
REC = 62


def say(*a):
    print(*a, flush=True)


def game_files(dirs=MCD_DIRS):
    """ИМЯ.РАСШ (заглавными) -> путь; порядок папок - порядок приоритета."""
    out = {}
    for d in dirs:
        if Path(d).is_dir():
            for n in os.listdir(d):
                out.setdefault(n.upper(), Path(d) / n)
    return out


def loops(mcd_bytes):
    """Frame[0..7] каждой записи."""
    return [list(mcd_bytes[i:i + 8]) for i in range(0, len(mcd_bytes) - REC + 1, REC)]


def twin_groups(records, frames):
    """Группы кадров с побайтно одинаковой классикой, которые стоят в одной петле.

    records - Frame[0..7] записей, frames - кадры классики (массивы индексов).
    Возвращает [(основа, [близнецы...])]: основа - кадр с наибольшим числом мест в
    Frame[0..7] всех записей, при равенстве младший.
    """
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for fr8 in records:
        if len(set(fr8)) < 2:
            continue
        by = defaultdict(list)
        for f in dict.fromkeys(fr8):
            if f < len(frames):
                by[np.asarray(frames[f]).tobytes()].append(f)
        for fs in by.values():
            for f in fs[1:]:
                parent[find(f)] = find(fs[0])
    shown = Counter(f for fr8 in records for f in fr8)
    comp = defaultdict(list)
    for f in parent:
        comp[find(f)].append(f)
    out = []
    for fs in comp.values():
        if len(fs) < 2:
            continue
        base = min(fs, key=lambda f: (-shown[f], f))
        out.append((base, sorted(f for f in fs if f != base)))
    return sorted(out)


def frame_files(pack, f):
    """<f>.png и варианты <f>.vN.png: имя файла -> путь."""
    out = {}
    p = pack / ("%d.png" % f)
    if p.exists():
        out[p.name] = p
    for v in pack.glob("%d.v*.png" % f):
        rest = v.name[len(str(f)):]
        if rest[2:-4].isdigit():
            out[v.name] = v
    return out


def pixels(p):
    return np.asarray(Image.open(p).convert("RGBA"))


def same_hd(pack, a, b):
    """Одинаковы ли HD кадров a и b (с вариантами) по пикселям; плюс средняя разница основного."""
    fa, fb = frame_files(pack, a), frame_files(pack, b)
    va = sorted(n[len(str(a)):] for n in fa)
    vb = sorted(n[len(str(b)):] for n in fb)
    if va != vb:
        return False, None
    diff = 0.0
    eq = True
    for rest in va:
        x, y = pixels(pack / (str(a) + rest)), pixels(pack / (str(b) + rest))
        if x.shape != y.shape:
            return False, 999.0
        if not np.array_equal(x, y):
            eq = False
            if rest == ".png":
                diff = float(np.abs(x.astype(int) - y.astype(int)).max(2).mean())
    return eq, round(diff, 2)


def scan(hd_root, sets=None, files=None):
    """Близнецы петель с разным HD: [(набор, основа, близнец, разница, что не так)]."""
    files = files if files is not None else game_files()
    bad = []
    for key in sorted(files):
        if not key.endswith(".MCD"):
            continue
        name = key[:-4]
        if sets and name not in sets:
            continue
        pack = Path(hd_root) / (name + ".PCK")
        if not pack.is_dir() or name + ".PCK" not in files:
            continue
        recs = loops(files[key].read_bytes())
        if not any(len(set(r)) > 1 for r in recs):
            continue
        tab = files.get(name + ".TAB")
        frames = xs.read_pck(str(files[name + ".PCK"]), str(tab) if tab else None)
        for base, twins in twin_groups(recs, frames):
            has_base = bool(frame_files(pack, base))
            for t in twins:
                has_t = bool(frame_files(pack, t))
                if not has_base and not has_t:
                    continue
                if has_base != has_t:
                    bad.append((name, base, t, None, "HD есть только у " + ("основы" if has_base else "близнеца")))
                    continue
                eq, d = same_hd(pack, base, t)
                if not eq:
                    bad.append((name, base, t, d, "разный HD"))
    return bad


def man_frame(man, name, f):
    """Файлы кадра f набора в манифесте: окончание ('.png', '.v1.png') -> rel."""
    pre = "TERRAIN/%s.PCK/%d." % (name, f)
    out = {}
    for rel in man["files"]:
        if rel.startswith(pre):
            rest = rel[len(pre) - 1:]
            if rest == ".png" or (rest.startswith(".v") and rest[2:-4].isdigit() and rest.endswith(".png")):
                out[rest] = rel
    return out


def fix(bad):
    """HD основы - близнецу, через манифест пака (build_hd_pack): stage, save, install в обе копии.

    Основа берётся из манифеста; если файл основы в установке не равен манифесту (правка мимо
    манифеста) или основы в манифесте нет - близнец не трогается, это решать отдельно.
    """
    import build_hd_pack as bp
    os.chdir(ROOT)
    man = bp.load()
    game = ROOT / bp.TARGETS["game"]
    repo = ROOT / bp.TARGETS["repo"]
    staged, drop, skip = [], [], 0
    for name, base, t, _d, why in bad:
        src = man_frame(man, name, base)
        if ".png" not in src:
            say("  пропуск %s %d <- %d: основы нет в манифесте" % (name, t, base))
            skip += 1
            continue
        if any(not (game / r).exists() or bp.sha256_file(str(game / r)) != man["files"][r]["sha256"]
               for r in src.values()):
            say("  пропуск %s %d <- %d: основа в установке не равна манифесту" % (name, t, base))
            skip += 1
            continue
        old = man_frame(man, name, t)
        for rest, rel in src.items():
            e = man["files"][rel]
            trel = "TERRAIN/%s.PCK/%d%s" % (name, t, rest)
            bp.stage(man, trel, bp.blob_path(e["sha256"], rel), generator="loop_twins",
                     generator_version="loop_twins.py 14.10", source_path=rel, approved=True,
                     approval="близнец петли анимации: классика %s %d и %d одна, HD - как у основы (R-338)"
                     % (name, t, base), asset_id="%s:%d" % (name, t), source_frame="%s:%d" % (name, base),
                     derived_from=rel, replaced=man["files"].get(trel, {}).get("sha256"))
            staged.append(trel)
        for rest, rel in old.items():
            if rest not in src:
                man["files"].pop(rel, None)
                drop.append(rel)
    say("  в манифест: файлов %d, снято вариантов %d, пропущено близнецов %d" % (len(staged), len(drop), skip))
    if not staged and not drop:
        return 0
    bp.save(man, why="loop_twins: близнецы петель анимации")
    bp.log("save", "", bp.manifest_hash(man)[:16], "loop_twins: %d файлов, снято вариантов %d"
           % (len(staged), len(drop)))
    rels = sorted(set(staged))
    say("  game:", bp.install(man, "game", only=rels))
    rrels = []
    for r in rels:
        sd = r.rsplit("/", 1)[0] + "/"
        whole = [k for k in man["files"] if k.startswith(sd)]
        if (repo / sd).is_dir() and len(os.listdir(repo / sd)) >= len(whole):
            rrels.append(r)
        else:                                   # R-257: набора нет или он неполный - целиком
            rrels += whole
    say("  repo:", bp.install(man, "repo", only=sorted(set(rrels))))
    for rel in drop:
        for root in (game, repo):
            if (root / rel).exists():
                bp.unlink_ro(str(root / rel))
    errs = 0
    for r in rels:
        for root in (game, repo):
            if bp.sha256_file(str(root / r)) != man["files"][r]["sha256"]:
                say("  РАСХОДИТСЯ", root, r)
                errs += 1
    for sd in sorted({r.rsplit("/", 1)[0] + "/" for r in rels}):
        nm = len([k for k in man["files"] if k.startswith(sd)])
        ng, nr = len(os.listdir(game / sd)), len(os.listdir(repo / sd))
        if not ng == nr == nm:
            say("  ЧИСЛО ФАЙЛОВ", sd, "game", ng, "repo", nr, "манифест", nm)
            errs += 1
    say("  сверка: расхождений", errs)
    return len(staged)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fix", action="store_true", help="выровнять: HD основы - близнецам")
    ap.add_argument("--sets", nargs="*", help="только эти наборы")
    ap.add_argument("--copy", choices=list(COPIES), help="только эта копия мода hd")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sets = {s.upper() for s in a.sets} if a.sets else None
    files = game_files()
    if a.fix:                                   # правка - по установке, она равна манифесту; репозиторий следом
        bad = scan(COPIES["установка"], sets, files)
        say("установка: близнецов петель с разным HD - %d" % len(bad))
        fix(bad)
    left = 0
    for label, root in COPIES.items():
        if a.copy and a.copy != label:
            continue
        bad = scan(root, sets, files)
        say("%s (%s): близнецов петель с разным HD - %d" % (label, root, len(bad)))
        for name, base, t, d, why in bad:
            say("  %s %d <- %d  %s%s" % (name, t, base, why, "" if d is None else ", разница %.2f" % d))
        left += len(bad)
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
