#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000418: проверка кадров будки В ИГРЕ невидимо, не трогая мод. Строит папку модов-двойника (соединения на моды установки,
кроме hd/hd/TERRAIN/PORTROADS.PCK - своя папка с копиями кадров), в неё кладутся кадры-кандидаты; игра запускается стендом
tools/hdbench.py с --mods-dir на двойник. Сейв - копия сейва переписи (блок PORTUFO21 в клетке (2,8)): яркий день, камера на
клетке рядом с будкой. Снимается только rmdir по соединениям (R-047).
    py -3.13 tools\hdart\t418_stand.py build <папка двойника> [<кадр 34.png>]   - собрать, подложить кадр(ы) из cand/B
    py -3.13 tools\hdart\t418_stand.py put <папка двойника> <png> <кадр>          - заменить кадр в двойнике
    py -3.13 tools\hdart\t418_stand.py save <out.sav> [x y]                      - сейв: день, выбранный солдат в (x,y)
    py -3.13 tools\hdart\t418_stand.py clean <папка двойника>"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODS = ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods"
SAVE = ROOT / "census" / "collapse" / "battles" / "collapse_STR_LOC_BAD_COMPANY_PORTTFTD5_23.sav"
SPECIAL = ("hd", "hd", "TERRAIN", "PORTROADS.PCK")


def junction(link, target):
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def mirror(src, dst, rest):
    """Папка dst повторяет src; ветка rest (кортеж имён) - настоящая папка с копиями файлов, остальное - соединения."""
    dst.mkdir(parents=True, exist_ok=True)
    for e in src.iterdir():
        t = dst / e.name
        if len(rest) and e.name == rest[0]:
            if len(rest) == 1:
                t.mkdir(exist_ok=True)
                for f in e.iterdir():
                    shutil.copy2(f, t / f.name)
            else:
                mirror(e, t, rest[1:])
        elif e.is_dir():
            junction(t, e)
        else:
            shutil.copy2(e, t)


def build(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for e in MODS.iterdir():
        t = out / e.name
        if e.name == "hd":
            mirror(e, t, SPECIAL[1:])
        elif e.is_dir():
            junction(t, e)
        else:
            shutil.copy2(e, t)


def put(out, png, frame):
    shutil.copy2(png, Path(out) / "hd" / "hd" / "TERRAIN" / "PORTROADS.PCK" / ("%d.png" % int(frame)))


def make_save(dst, ux=4, uy=6):
    t = SAVE.read_bytes().decode("utf-8")
    i = t.index("\n  units:")
    old = "position: [1,21,0]"
    j = t.index(old, i)
    t = t[:j] + "position: [%s,%s,0]" % (ux, uy) + t[j + len(old):]
    assert "globalshade: 11" in t
    t = t.replace("globalshade: 11", "globalshade: 0")
    Path(dst).write_bytes(t.encode("utf-8"))


def clean(out):
    out = Path(out)
    for p in list(out.rglob("*")):
        pass
    for root, dirs, _files in os.walk(out):
        pass
    # соединения - rmdir, настоящие папки - после содержимого
    def walk(d):
        for e in list(d.iterdir()):
            if e.is_dir():
                if os.lstat(e).st_file_attributes & 0x400:
                    os.rmdir(e)
                else:
                    walk(e)
                    e.rmdir()
            else:
                e.unlink()
    walk(out)
    out.rmdir()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    c = sys.argv[1]
    if c == "build":
        build(sys.argv[2])
        for a in sys.argv[3:]:
            put(sys.argv[2], a, 34)
    elif c == "put":
        put(sys.argv[2], sys.argv[3], sys.argv[4])
    elif c == "save":
        make_save(sys.argv[2], *(sys.argv[3:5] or (4, 6)))
    elif c == "clean":
        clean(sys.argv[2])
    print("ok")


if __name__ == "__main__":
    main()
