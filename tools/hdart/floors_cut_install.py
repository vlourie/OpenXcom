#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка подрезанных плоских полов (тикет XP-000407, решение Vitali 30.10: «плоские полы, с сохранением шва»).
Заготовки - art/tickets/floors_cut/batch<N>/<НАБОР>_<кадр>[.vN].png (floors_cut_build.py build). Без --yes - сухой
прогон: ничего не пишет. Ставится одной партией в обе копии мода hd (R-457/R-087) со сверкой хэшей и записью в манифест;
под очередью правок (py -3 tools\editq.py wait --name "полы: подрезка выступа партия N").

Манифест: generator floors_cut_safe, generator_version с датой и словом Vitali; approved/approval кадра НЕ повышаются
(картинку никто заново не одобрял, срезан только выступ за силуэт классики) - остаётся прежний флаг, к approval
дописывается пометка. Кадр, у которого файл в моде уже не тот, из которого резали (sha_источника), пропускается и
называется: его мог перерисовать другой исполнитель.

    py -3.13 tools\hdart\floors_cut_install.py --batch 1
    py -3.13 tools\hdart\floors_cut_install.py --batch 1 --yes
"""
import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[1]
os.chdir(ROOT)
OUT = ROOT / "art" / "tickets" / "floors_cut"
WORD = "по слову Vitali 30.10 «плоские полы, с сохранением шва» (XP-000407)"


def rel_of(name):
    m = re.match(r"^(.+)_(\d+)(\.v\d+)?\.png$", name)
    if not m:
        raise SystemExit("странное имя заготовки: " + name)
    return "TERRAIN/%s.PCK/%d%s.png" % (m.group(1), int(m.group(2)), m.group(3) or "")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, choices=(1, 2), required=True)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    from PIL import Image
    import build_hd_pack as bp
    import floors_overhang as fo
    src = {r["файл"]: r["sha_источника"] for r in fo.read_tsv(str(OUT / "batch_list.tsv"))
           if r["партия"] == str(a.batch) and r["решение"] == "да"}
    d = OUT / ("batch%d" % a.batch)
    files = sorted(d.glob("*.png"))
    if {p.name for p in files} != set(src):
        raise SystemExit("batch_list.tsv и папка %s расходятся: %d против %d" % (d, len(src), len(files)))
    man = bp.load()
    todo, changed_since, same = {}, [], 0
    for p in files:
        im = Image.open(p)
        if im.size != (128, 160) or im.mode != "RGBA":
            raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
        rel = rel_of(p.name)
        old = man["files"].get(rel)
        if not old:
            raise SystemExit("нет в манифесте: " + rel)
        if old["sha256"] != src[p.name]:
            changed_since.append(rel)           # файл в моде изменился после нарезки - не трогаем
            continue
        if bp.sha256_file(str(p)) == old["sha256"]:
            same += 1
            continue
        todo[rel] = p
    print("партия %d: заготовок %d, к установке %d, уже стоит %d, в моде изменено после нарезки %d" % (
        a.batch, len(files), len(todo), same, len(changed_since)))
    for rel in changed_since[:20]:
        print("  ПРОПУЩЕН (файл в моде не тот, из которого резали):", rel)
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (под очередью правок)")
    rels = []
    for rel, p in todo.items():
        old = man["files"][rel]
        bp.stage(man, rel, str(p), generator="floors_cut_safe",
                 generator_version="floors_cut_safe 30.10: срез выступа за силуэт классики вверху ромба, шов цел; "
                                   "было: %s %s" % (old.get("generator"), old.get("generator_version") or ""),
                 source_path=str(p).replace(os.sep, "/"), approved=old.get("approved", False),
                 approval=("%s; подрезка выступа %s" % (old.get("approval") or "", WORD)),
                 derived_from=old.get("derived_from"))
        rels.append(rel)
    bp.save(man, why="полы: подрезка выступа партия %d (%d кадров) %s" % (a.batch, len(rels), WORD))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for root in bp.TARGETS.values():
        for rel in rels:
            with open(os.path.join(root, rel), "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != man["files"][rel]["sha256"]:
                    raise SystemExit("РАСХОДИТСЯ %s %s" % (root, rel))
    print("сверено: обе копии, файлов %d" % len(rels))


if __name__ == "__main__":
    main()
