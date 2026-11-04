#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка XP-000486: лестница IDT_FARM (кадры :14 :15 :18 :19) одним стилем, вариант a или b из
art/tickets/t486_regen/<вариант>/. ПОДГОТОВЛЕНО, НЕ ЗАПУСКАТЬ до выбора Vitali и без очереди правок
(py -3 tools/editq.py wait ... / done). Через манифест: stage + save + install в game и repo + сверка хэшей;
резерв прежних - art/_backup/tickets_2026-11-04/<путь пака>.

    py -3.13 tools/hdart/t486_regen_install.py a            сухой прогон
    py -3.13 tools/hdart/t486_regen_install.py a --yes      установить (под очередью правок), коммит одной пачкой
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

from PIL import Image                        # noqa: E402

BACKUP = os.path.join(ROOT, "art", "_backup", "tickets_2026-11-04")
REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
SRC = os.path.join(ROOT, "art", "tickets", "t486_regen")
FRAMES = (14, 15, 18, 19)


def collect(var):
    return {"TERRAIN/IDT_FARM.PCK/%d.png" % f: os.path.join(SRC, var, "IDT_FARM_%d.png" % f) for f in FRAMES}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1 or args[0] not in ("a", "b"):
        raise SystemExit("нужен вариант: a или b")
    yes = "--yes" in sys.argv
    files = collect(args[0])
    for rel, p in files.items():
        with Image.open(p) as im, Image.open(os.path.join(REPO_PACK, rel)) as old:
            if im.mode != "RGBA" or im.size != old.size:
                raise SystemExit("%s: ждали RGBA %s, а %s %s" % (p, old.size, im.mode, im.size))
    print("файлов к установке: %d (вся семья IDT_FARM 14/15/18/19)" % len(files))
    if not yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (под очередью правок)")
    for rel in files:
        src = os.path.join(REPO_PACK, rel)
        dst = os.path.join(BACKUP, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            shutil.copyfile(src, dst)
    import ticket_scene as ts
    n = ts.install_files(files, "t486_regen_install",
                         "XP-000486: лестница IDT_FARM одним стилем, вариант %s" % args[0],
                         "Vitali: решение 04.11 (перегенерация одним стилем) и выбор варианта %s" % args[0],
                         "t486_regen: IDT_FARM:14/15/18/19")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
