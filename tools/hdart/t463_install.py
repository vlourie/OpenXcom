#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка кулера XP-000463 (выбор Vitali 02.11, вариант D, пункт c1102b_463).

Новый арт не генерирует: берёт готовые кадры art/tickets/t463/cand2/D/ и ставит через манифест
(ticket_scene.install_files: stage + save + install в game и repo + сверка хэшей).
Семья: XBASEN_BITS:39 + побайтная копия FREIGHTER_COMMAND_2:30 (ticket_family.py).
Резерв прежних кадров - art/_backup/t463_2026-11-02/<путь пака>.

    py -3.13 tools\hdart\t463_install.py                 сухой прогон
    py -3.13 tools\hdart\t463_install.py --install --yes установить (под очередью правок)
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

from PIL import Image                        # noqa: E402

REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
CAND = os.path.join(ROOT, "art", "tickets", "t463", "cand2", "D_edge")   # D с ровным краем подставки (t463_edge.py, R-121); исходный D - cand2/D
FRAMES = [("XBASEN_BITS", 39), ("FREIGHTER_COMMAND_2", 30)]


def collect():
    return {"TERRAIN/%s.PCK/%d.png" % (s, f): os.path.join(CAND, "%s_%d.png" % (s, f)) for s, f in FRAMES}


def old_path(rel):
    p = os.path.join(REPO_PACK, rel)
    if not os.path.exists(p):
        import build_hd_pack as bp
        p = os.path.join(bp.TARGETS["game"], rel)
    return p


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files = collect()
    for rel, p in files.items():
        with Image.open(p) as im, Image.open(old_path(rel)) as old:
            if im.mode != "RGBA" or im.size != old.size:
                raise SystemExit("%s: ждали RGBA %s, а %s %s" % (p, old.size, im.mode, im.size))
    print("файлов к установке: %d" % len(files))
    for rel in files:
        print("  ", rel)
    if not (a.install and a.yes):
        print("сухой прогон; --install --yes - записать в мод (под очередью правок)")
        return
    import build_hd_pack as bp
    backup = os.path.join(ROOT, "art", "_backup", "t463_2026-11-02")
    for rel in files:
        dst = os.path.join(backup, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            shutil.copyfile(old_path(rel), dst)
    print("резерв:", backup)
    # R-257: набор в repo неполный - ставим набор из манифеста целиком
    man = bp.load()
    for pck in sorted({rel.split("/")[1] for rel in files}):
        want = [k for k in man["files"] if k.startswith("TERRAIN/%s/" % pck)]
        d = os.path.join(REPO_PACK, "TERRAIN", pck)
        have = os.listdir(d) if os.path.isdir(d) else []
        if len(have) < len(want):
            print("repo: набор %s неполный (%d из %d) - ставлю целиком" % (pck, len(have), len(want)))
            bp.install(man, "repo", only=want)
            if len(os.listdir(d)) != len(want):
                raise SystemExit("набор %s в repo: не полон" % pck)
    import ticket_scene as ts
    n = ts.install_files(files, "t463_install", "t463 cand2 D_edge",
                         "Vitali 02.11, страница выбора, пункт c1102b_463: вариант D",
                         "XP-000463: кулер XBASEN_BITS:39 + копия FREIGHTER_COMMAND_2:30, вариант D, край подставки спрямлён (R-121)")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
