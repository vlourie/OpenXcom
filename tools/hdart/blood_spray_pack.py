#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Брызги крови по полёту пули (XP-000298, выбор Vitali A, 26.10) -> мод hd через манифест build_hd_pack.

Клипы строит gen_combat_fx.py --blood-spray --out art/_review/xp298 (blood_<сила>_<направление>_<вариант>, 72 шт.);
этот скрипт кладёт их в хранилище и обе копии мода hd (FX/blood_*/N.png; удар клинком - stab_*, те же 72 имени). Движок берёт их только при опции
oxceHdBloodSpray (по умолчанию выключена), а без них оставляет прежнюю кровь.

    py -3.13 tools/hdart/blood_spray_pack.py          сухой прогон: что будет записано
    py -3.13 tools/hdart/blood_spray_pack.py --yes    записать
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SRC = os.path.join("art", "_review", "xp298", "FX")


def main():
    yes = "--yes" in sys.argv
    plan = []
    for clip in sorted(os.listdir(SRC)):
        d = os.path.join(SRC, clip)
        if not (clip.startswith(("blood_", "stab_")) and os.path.isdir(d)):
            continue
        for f in sorted(os.listdir(d), key=lambda n: int(n[:-4]) if n[:-4].isdigit() else 0):
            if f.endswith(".png") and f[:-4].isdigit():
                plan.append(("FX/%s/%s" % (clip, f), os.path.join(d, f)))
    print("клипов %d, файлов %d" % (len({r.split('/')[1] for r, _p in plan}), len(plan)))
    if not yes:
        raise SystemExit("сухой прогон; --yes - записать в мод")
    import build_hd_pack as bp
    man = bp.load()
    for rel, p in plan:
        bp.stage(man, rel, p, generator="gen_combat_fx", generator_version="gen_combat_fx.py --blood-spray (XP-000298)",
                 source_path=p.replace(os.sep, "/"), approved=True,
                 approval="Vitali 26.10 XP-000298 вариант A (процедурно; опция oxceHdBloodSpray по умолчанию выкл)")
    rels = [r for r, _p in plan]
    bp.save(man, why="XP-000298: %d кадров брызг крови по полёту пули" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for r in rels:
        for root in bp.TARGETS.values():
            with open(os.path.join(root, r), "rb") as f:
                if hashlib.sha256(f.read()).hexdigest() != man["files"][r]["sha256"]:
                    raise SystemExit("РАСХОДИТСЯ %s %s" % (root, r))
    print("сверено: %d файлов в обеих копиях" % len(rels))
    return 0


if __name__ == "__main__":
    sys.exit(main())
