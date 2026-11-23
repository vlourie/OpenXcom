#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000413 (камни со мхом FORESTSWAMPBITS и вся семья, 41 кадр): подключение заготовок в мод hd. ТОЛЬКО ПО СЛОВУ
Vitali «да» после листа art/_review/tickets_2026-10-30/t413_family.png (правило «арт - сначала показать»). Заготовки -
art/tickets/t413/fam/cand/<НАБОР>_<кадр>.png (их собирает t413_fam_build.py build). Без --yes - сухой прогон: ничего не пишет.

Что ставится: FORESTSWAMPBITS 4 5 6 7 9; FORESTBITS3 4 5 6 7 9; BLACKFORESTBITS 4 5 6 7 9; FORESTBITS2 3 4 5 6 7 9;
FORESTBITSRED 3 4 5 6 7 9; FORESTBITS_SNOW 3 4 5 9; FORESTBITSWASTE 3 4 5 6 7 9; JUNGLEROCKS 15 16 17 18.
Не трогаются: FORESTSWAMPBITS 3 и блоки 10-14 (одобрены), FORESTBITS3:3 / BLACKFORESTBITS:3 / JUNGLEROCKS:14 («один камень»),
FORESTBITS_SNOW 6/7 (26.10). Установщик останавливается, если у кадра в манифесте approved=True.
Ставится одним коммитом в обе копии мода hd (R-457), под очередью правок (CLAUDE.md), сверка хэшей - внутри install_files.

    py -3.13 tools\hdart\t413_install.py                                   # сухой прогон
    py -3.13 tools\hdart\t413_install.py --yes --approval "Vitali <дата>: <его слова>"
"""
import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[1]
os.chdir(ROOT)
CAND = ROOT / "art" / "tickets" / "t413" / "fam" / "cand"
EXPECT = 41


def frames():
    out = {}
    for p in sorted(CAND.glob("*.png")):
        s, f = p.stem.rsplit("_", 1)
        out["TERRAIN/%s.PCK/%d.png" % (s, int(f))] = p
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--approval", default="", help="слова Vitali, по которым ставится (в манифест)")
    ap.add_argument("--skip", nargs="*", default=[], help="наборы, которые не ставить (Vitali 30.10: без серых)")
    a = ap.parse_args()
    from PIL import Image
    files = frames()
    if len(files) != EXPECT:
        raise SystemExit("ждали %d заготовок, а их %d (py -3.13 tools\\hdart\\t413_fam_build.py build)" % (EXPECT, len(files)))
    files = {r: p for r, p in files.items() if r.split("/")[1][:-4] not in a.skip}
    for rel, p in files.items():
        im = Image.open(p)
        if im.size != (128, 160) or im.mode != "RGBA":
            raise SystemExit("%s: ждали RGBA 128x160, а %s %s" % (p, im.mode, im.size))
    import build_hd_pack as bp
    man = bp.load()
    stop = []
    for rel, p in files.items():
        e = man["files"].get(rel, {})
        print("  %-42s <- %s  (манифест: %s)" % (rel, p.name, "%s approved=%s %s" % (e.get("generator"), e.get("approved"),
                                                                                    str(e.get("sha256", ""))[:8])
                                                 if e else "нет в манифесте"))
        if e.get("approved"):
            stop.append(rel)
        d = Path(bp.TARGETS["game"]) / Path(rel).parent
        stem = Path(rel).stem
        if d.is_dir() and any(n.startswith(stem + ".v") for n in os.listdir(d)):
            stop.append(rel + " (есть варианты .vN - сначала решить)")
    if stop:
        raise SystemExit("СТОП, одобренные или с вариантами: %s" % stop)
    if not a.yes:
        raise SystemExit("сухой прогон, кадров %d; --yes --approval \"<слова Vitali>\" - записать в мод (под очередью правок)"
                         % len(files))
    if not a.approval.strip():
        raise SystemExit("нужен --approval \"<слова Vitali>\" (что именно он одобрил)")
    import ticket_scene as ts
    n = ts.install_files(files, "t413_family", "t413_fam_build 30.10: Qwen strict C2 + перенос цвета классики",
                         a.approval.strip(),
                         "t413: камни со мхом FORESTSWAMPBITS и семья, %d кадров (тикет XP-000413)" % len(files))
    print("установлено файлов:", n)
    print("дальше: CHANGELOG и «Что нового» (строка про камни), коммит одной правкой, editq done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
