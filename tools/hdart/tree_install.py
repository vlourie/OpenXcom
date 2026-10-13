#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Установка принятых деревьев TREE_RENDER_V2 в обе копии мода hd через манифест (build_hd_pack).

Семейство - готовые кадры <корень>/<семейство>/asm/frames/<НАБОР>.PCK/<кадр>.png. Каждый кадр ставится и на все
побайтные копии своей классики (census/frame_hash.tsv, R-296, R-317): иначе там, где карта собрана из копии,
остаётся прежний пак. Варианты .vN прежнего пака у заменённых кадров снимаются. В копию мода, где набора нет или он
неполный, набор ставится целиком (R-257). После установки - сверка sha256 и числа файлов в обеих копиях.

    py -3.13 tools/hdart/tree_install.py --why "..." census/trees/groups/batch1:TG002,TG008 batch1_retry:TG006
    ... --yes        записать (без него - сухой прогон: план и откуда что)

Корень без пути ищется в census/trees/groups."""
import argparse
import hashlib
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_hd_pack as bp        # noqa: E402
import floor_batch as fb          # noqa: E402

ROOT = fb.ROOT
GROUPS = ROOT / "census" / "trees" / "groups"


def say(*a):
    print(*a, flush=True)


def family_frames(root, fid):
    """(НАБОР, кадр, путь) готовых кадров семейства"""
    d = root / fid / "asm" / "frames"
    if not d.is_dir():
        raise SystemExit("%s: нет %s" % (fid, d))
    out = []
    for sd in sorted(d.iterdir()):
        if not sd.name.upper().endswith(".PCK"):
            continue
        for p in sorted(sd.glob("*.png")):
            if p.stem.isdigit():
                out.append((sd.name[:-4].upper(), int(p.stem), p))
    if not out:
        raise SystemExit("%s: в %s нет кадров" % (fid, d))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("groups", nargs="+", help="корень:TG001,TG002")
    ap.add_argument("--why", required=True, help="чья приёмка и по чему")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    os.chdir(ROOT)
    hof, by = fb.copies()
    man = bp.load()
    plan, drop, seen = [], [], {}
    for g in a.groups:
        r, fids = g.split(":", 1)
        root = Path(r) if ("/" in r or "\\" in r) else GROUPS / r
        for fid in fids.split(","):
            for S, n, src in family_frames(root, fid):
                k = fb.key_of(S, n)
                h = hof.get(k)
                group = by.get(h, [k]) if h else [k]
                if k not in group:
                    group = [k] + group
                for m in group:
                    why = fb.skip_reason(m)
                    if why:
                        say("  %-24s %s - пропуск" % (m, why))
                        continue
                    if m in seen and seen[m] != str(src):
                        raise SystemExit("%s ставится из двух мест: %s и %s" % (m, seen[m], src))
                    seen[m] = str(src)
                    ms, mf = m.split(":")
                    rel = "TERRAIN/%s.PCK/%s.png" % (ms, mf)
                    prev = man["files"].get(rel, {})
                    say("  %-6s %-24s <- %s%s   было: %s" % (fid, m, src.relative_to(ROOT),
                                                            "" if m == k else " (копия %s)" % k,
                                                            prev.get("generator", "нет в паке") if prev else "нет в паке"))
                    plan.append((rel, src, m, k, fid))
                    for root_ in (fb.GAME, fb.REPO):
                        for v in sorted((root_ / "TERRAIN" / ("%s.PCK" % ms)).glob(mf + ".v*.png")):
                            drop.append("TERRAIN/%s.PCK/%s" % (ms, v.name))
    drop = sorted(set(drop))
    say("кадров %d (с копиями), снять вариантов %d" % (len(plan), len(drop)))
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать")
    for rel, src, m, k, fid in plan:
        old = man["files"].get(rel, {}).get("sha256")
        bp.stage(man, rel, str(src), generator="tree_family", generator_version="tree_family.py TREE_RENDER_V2",
                 source_path=str(src), approved=True, approval="%s: %s" % (fid, a.why), asset_id=m,
                 source_frame=k, replaced=old)
    for rel in drop:
        man["files"].pop(rel, None)
    bp.save(man, why="tree_install")
    bp.log("save", "", bp.manifest_hash(man)[:16], "tree_install: %d кадров, снято вариантов %d" % (len(plan), len(drop)))
    rels = sorted({p[0] for p in plan})
    for target, base in (("game", fb.GAME), ("repo", fb.REPO)):
        only = []
        for r in rels:
            sd = r.rsplit("/", 1)[0] + "/"
            whole = [x for x in man["files"] if x.startswith(sd)]
            if (base / sd).is_dir() and len(os.listdir(base / sd)) >= len(whole) - 1:
                only.append(r)
            else:                                   # R-257: набора нет или он неполный - целиком
                say("  %s: %s неполный или нет - ставлю набор целиком (%d)" % (target, sd, len(whole)))
                only += whole
        say(target + ":", bp.install(man, target, only=sorted(set(only))))
    for rel in drop:
        for base in (fb.GAME, fb.REPO):
            p = base / rel
            if p.exists():
                bp.unlink_ro(str(p))
    bad = 0
    for r in rels:
        for base in (fb.GAME, fb.REPO):
            if hashlib.sha256((base / r).read_bytes()).hexdigest() != man["files"][r]["sha256"]:
                say("РАСХОДИТСЯ", base, r)
                bad += 1
    for sd in sorted({r.rsplit("/", 1)[0] + "/" for r in rels}):
        ng, nr = len(os.listdir(fb.GAME / sd)), len(os.listdir(fb.REPO / sd))
        nm = len([x for x in man["files"] if x.startswith(sd)])
        flag = "" if ng == nr == nm else "   ЧИСЛО ФАЙЛОВ РАСХОДИТСЯ"
        bad += bool(flag)
        say("  %-32s game %d repo %d манифест %d%s" % (sd, ng, nr, nm, flag))
    say("итог:", "OK" if not bad else "ОШИБОК %d" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
