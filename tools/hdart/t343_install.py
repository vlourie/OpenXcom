#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000343 (выбор Vitali 27.10, вариант AE: A + края 44/45, включая одобренные): крыша башни связи.

  - t343_pit.py: углы и край ямы (логические 40-43, 46, 47) по классике в поле настоящего блока COMMS_TOWER_ROOF,
    8 наборов C_EXT_ROOF*, SPACESTATION_EXTRA 36-39/42/43, STATIONBITS 16-19/22/23 (60 кадров), затем края 44, 45 (ext, 20 кадров);
  - t343_cage.py: клеть XBASEN_BITS:0 и побайтные копии CYBERWAREAN:96, METRO1:91, RUSTSHACKS2:52;
  - C_EXT_ROOFBITS_SILVER 40-47 - копии новых C_EXT_ROOF_SILVER (набор есть только в HD-паке, в классике его нет), в том числе
    одобренные 45 и 46 (слово Vitali 27.10);
  - FREIGHTER_MAIN:63 и NINJATECH:27 (wall_exact_C, одобрены) не трогаются.
Установка - ticket_scene.install_files (манифест, обе копии мода hd, сверка хешей). В копии repo нет целых наборов
C_EXT_ROOF_BLACK2/GOLD/PRPL/RED - они ставятся целиком из манифеста (R-257).

    py -3.13 tools\hdart\t343_install.py          # сухой прогон: кадры в art/tickets/t343/out
    py -3.13 tools\hdart\t343_install.py --yes    # в мод hd (под очередью правок, по слову Vitali)
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)
OUT = os.path.join(ROOT, "art", "tickets", "t343", "out")
CE = ["C_EXT_ROOF", "C_EXT_ROOF_BLACK", "C_EXT_ROOF_BLACK2", "C_EXT_ROOF_DBLUE", "C_EXT_ROOF_GOLD", "C_EXT_ROOF_PRPL",
      "C_EXT_ROOF_RED", "C_EXT_ROOF_SILVER"]
REPO_FULL = ["C_EXT_ROOF_BLACK2", "C_EXT_ROOF_GOLD", "C_EXT_ROOF_PRPL", "C_EXT_ROOF_RED"]


def tpath(s, f):
    return "TERRAIN/%s.PCK/%d.png" % (s, f)


def generate():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    py = [sys.executable]
    subprocess.run(py + [os.path.join(HERE, "t343_pit.py"), "--out", OUT], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(py + [os.path.join(HERE, "t343_pit.py"), "--out", OUT, "--frames", "44,45", "--sets", ",".join(CE)],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run(py + [os.path.join(HERE, "t343_pit.py"), "--out", OUT, "--frames", "44,45", "--sets",
                         "SPACESTATION_EXTRA,STATIONBITS"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(py + [os.path.join(HERE, "t343_cage.py"), "--out", OUT], check=True)


def build():
    generate()
    files = {}
    for fn in sorted(os.listdir(OUT)):
        if not fn.endswith(".png"):
            continue
        s, f = fn[:-4].rsplit("_", 1)
        files[tpath(s, int(f))] = os.path.join(OUT, fn)
    for f in range(40, 48):                       # C_EXT_ROOFBITS_SILVER - копии новых SILVER
        src = files[tpath("C_EXT_ROOF_SILVER", f)]
        files[tpath("C_EXT_ROOFBITS_SILVER", f)] = src
    assert tpath("FREIGHTER_MAIN", 63) not in files and tpath("NINJATECH", 27) not in files
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    files = build()
    print("файлов:", len(files))
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (по слову Vitali, под очередью правок)")
    import ticket_scene as ts
    import build_hd_pack as bp
    n = ts.install_files(files, "t343_install", "t343_install.py 27.10", "Vitali: вариант AE 27.10 (A + края 44/45, включая одобренные)",
                         "t343: крыша башни связи - углы и края ямы по классике, клеть XBASEN_BITS:0")
    print("установлено файлов:", n)
    man = bp.load()
    for s in REPO_FULL:                           # R-257: в копии repo этих наборов нет - целиком из манифеста
        rels = [r for r in man["files"] if r.startswith("TERRAIN/%s.PCK/" % s)]
        print("repo", s, "из", len(rels), "в манифесте:", bp.install(man, "repo", only=rels))
        have = len([x for x in os.listdir(os.path.join(bp.TARGETS["repo"], "TERRAIN", s + ".PCK"))])
        print("   файлов в repo:", have)


if __name__ == "__main__":
    main()
