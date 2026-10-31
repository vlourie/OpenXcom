#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка кандидатов тикетов XP-000384, 385-387, 389 (Vitali 31.10, страница выбора c1031b, ключ Y).

  384  трава MOUNTMUD 1, 2, 7, 9 сплошным полем G3841S3851P3861 (t384_fld/t384_build): основа + 3 варианта ковра на кадр
       (N.png, N.v1.png, N.v2.png, N.v3.png - движок читает <кадр>.v<n>.png как варианты кадра, HdSprites.cpp), куст
       MOUNTMUD:19 и BLACKFOREST:18 переносом (t384_bush) - 18 кадров;
       art/tickets/t384/cand/<НАБОР>_<кадр>[.vN].png
  385  снег MOUNTSNOW2 (t385_387_build): камень 21-23, пруд 17-20, трава 7-9, склоны 27-39 и родня POLAR, POLARPLANE,
       FOREST_SNOW, FORESTBITS_SNOW, FORESTSWAMP_SNOW - 48 кадров (куст MOUNTSNOW2:16 не готов, не ставится);
       art/tickets/t385/cand/<НАБОР>_<кадр>.png
  389  рваный асфальт ROADS_WASTE 1 2 4 5 6 7 10 11 12 + копии XOPSDESERTRUINS 34-36, второй проход (t389_edge);
       art/tickets/t389/cand/<НАБОР>_<кадр>.png (cand_pass1 не берём)

Через манифест (ticket_scene.install_files: stage + save + install в game и repo + сверка хэшей), резерв прежних файлов -
art/_backup/t<NNN>_2026-10-31/<путь пака>.

    py -3.13 tools\hdart\t1031b_install.py 384            сухой прогон
    py -3.13 tools\hdart\t1031b_install.py 384 --install --yes   установить (под очередью правок)
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

from PIL import Image                        # noqa: E402

REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
TICKETS = {
    "384": dict(cand="t384", n=18, ids="384",
                what="XP-000384: трава MOUNTMUD 1 2 7 9 полем G3841S3851P3861 с коврами .v1-.v3 + куст MOUNTMUD:19 и BLACKFOREST:18 (t384_fld/build/bush)",
                why="t384 трава MOUNTMUD сплошным полем, ковры, куст"),
    "385": dict(cand="t385", n=48, ids="385, 386, 387",
                what="XP-000385/386/387: снег MOUNTSNOW2 (камень, пруд, трава, склоны) и родня POLAR/POLARPLANE/FOREST_SNOW (t385_387_build)",
                why="t385-387 снег MOUNTSNOW2 и родня"),
    "389": dict(cand="t389", n=12, ids="389",
                what="XP-000389: рваный асфальт ROADS_WASTE 1 2 4 5 6 7 10 11 12 + копии XOPSDESERTRUINS 34-36, второй проход (t389_edge)",
                why="t389 рваный асфальт ROADS_WASTE без чёрных точек и лесенки"),
}


def collect(cand_dir):
    files = {}
    for name in sorted(os.listdir(cand_dir)):
        m = re.fullmatch(r"(.+?)_(\d+(?:\.v\d+)?)\.png", name)
        if m:
            files["TERRAIN/%s.PCK/%s.png" % (m.group(1), m.group(2))] = os.path.join(cand_dir, name)
    return files


def check(files):
    bad = []
    for rel, p in files.items():
        main = re.sub(r"\.v\d+\.png$", ".png", rel)
        old_p = os.path.join(REPO_PACK, rel)
        if not os.path.exists(old_p):
            old_p = os.path.join(REPO_PACK, main)       # новый вариант ковра: размер как у основы кадра
        if not os.path.exists(old_p):
            bad.append("%s: нет кадра в паке" % rel)
            continue
        # with: незакрытый кадр пака держит файл, и os.replace при установке падает (R-567)
        with Image.open(p) as im, Image.open(old_p) as old:
            if im.mode != "RGBA" or im.size != old.size:
                bad.append("%s: ждали RGBA %s, а %s %s" % (rel, old.size, im.mode, im.size))
    return bad


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1 or args[0] not in TICKETS:
        raise SystemExit("номер тикета: " + " ".join(TICKETS))
    t = TICKETS[args[0]]
    install = "--install" in sys.argv and "--yes" in sys.argv
    cand_dir = os.path.join(ROOT, "art", "tickets", t["cand"], "cand")
    files = collect(cand_dir)
    if len(files) != t["n"]:
        raise SystemExit("ждали %d кадров, а %d" % (t["n"], len(files)))
    bad = check(files)
    if bad:
        raise SystemExit("\n".join(bad))
    print("файлов к установке: %d" % len(files))
    for rel in files:
        print("  ", rel, "(новый)" if not os.path.exists(os.path.join(REPO_PACK, rel)) else "")
    if not install:
        raise SystemExit("сухой прогон; --install --yes - записать в мод (под очередью правок)")
    backup = os.path.join(ROOT, "art", "_backup", "%s_2026-10-31" % t["cand"])
    nb = 0
    for rel in files:
        src = os.path.join(REPO_PACK, rel)
        dst = os.path.join(backup, rel)
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            nb += 1
    print("резерв: %d файлов, %s" % (nb, backup))
    import ticket_scene as ts
    n = ts.install_files(files, "t1031b_install", "1", "Vitali 31.10, страница выбора, пункт c1031b_%s: Y" % t["ids"].replace(", ", "/"),
                         t["what"])
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
