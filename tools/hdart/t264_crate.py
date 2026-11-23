#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000264: ящик CONTAINERS:2 у кровати - в HD светлые доски, в оригинале тёмная решётка.

Вариант 1 (Vitali 23.10 «чини все»): кадр df8357 (md5 начинается с df8357; art/_backup/hd_objects_v01/game/
CONTAINERS.PCK/2.png, копия art/tickets/t264/df8357.png) - густая решётка, IoU с классикой 0.979 - на оба кадра
семьи: CONTAINERS:2 и DOOM_BASE2:9 (в классике побайтно одно и то же, ticket_family.py, R-457).
Это отмена одобренного strict #13 (12.10) для CONTAINERS:2. Ставить под очередью правок, обе копии мода hd.

    py -3.13 tools/hdart/t264_crate.py            # сухой прогон
    py -3.13 tools/hdart/t264_crate.py --yes      # манифест + game + repo + сверка хэшей
"""
import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(os.path.dirname(os.path.dirname(HERE)))

import build_hd_pack as bp                           # noqa: E402

SRC = os.path.join("art", "tickets", "t264", "df8357.png")
MD5 = "df83579285d8780c9fab8348c2e07e35"
RELS = ["TERRAIN/CONTAINERS.PCK/2.png", "TERRAIN/DOOM_BASE2.PCK/9.png"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="записать в манифест и поставить в игру и в репозиторий")
    a = ap.parse_args()
    with open(SRC, "rb") as fh:
        data = fh.read()
    if hashlib.md5(data).hexdigest() != MD5:
        raise SystemExit("%s: не df8357 (md5 %s)" % (SRC, hashlib.md5(data).hexdigest()))
    new = bp.sha256_file(SRC)
    man = bp.load()
    todo = []
    for rel in RELS:
        old = man["files"].get(rel, {})
        print("%s: %s -> %s" % (rel, old.get("sha256", "-")[:12], new[:12]))
        if old.get("sha256") != new:
            todo.append(rel)
    if not todo:
        print("уже df8357")
        return 0
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (%d кадра)" % len(todo))
    for rel in todo:
        bp.stage(man, rel, SRC, generator="hd_objects_v01", generator_version="df8357, откат t264 23.10",
                 source_path="art/_backup/hd_objects_v01/game/CONTAINERS.PCK/2.png", approved=True,
                 approval="Vitali 23.10 t264: «чини все», вариант df8357",
                 derived_from=None if rel == RELS[0] else RELS[0])
    bp.save(man, why="t264: ящик CONTAINERS:2 и DOOM_BASE2:9 - решётка df8357, как в оригинале")
    print("game:", bp.install(man, "game", only=todo))
    print("repo:", bp.install(man, "repo", only=todo))
    for rel in todo:
        for root in bp.TARGETS.values():
            with open(os.path.join(root, rel), "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != new:
                    raise SystemExit("РАСХОДИТСЯ %s %s" % (root, rel))
    print("сверено: %d файла в обеих копиях" % len(todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
