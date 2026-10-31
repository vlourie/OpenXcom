#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Сверка: хэши установленных файлов в игре (Пиратки) и в repo равны кандидатам тикета.

    py -3.13 tools\hdart\t1031b_verify.py 384
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import t1031b_install as ti                          # noqa: E402

GAME_PACK = os.path.join(ti.ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd")


def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    t = ti.TICKETS[sys.argv[1]]
    files = ti.collect(os.path.join(ti.ROOT, "art", "tickets", t["cand"], "cand"))
    bad = 0
    for rel, src in files.items():
        h = sha(src)
        for nm, root in (("game", GAME_PACK), ("repo", ti.REPO_PACK)):
            p = os.path.join(root, rel)
            if not os.path.exists(p) or sha(p) != h:
                bad += 1
                print("РАСХОДИТСЯ", nm, rel)
    print("файлов %d, расхождений %d" % (len(files), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
