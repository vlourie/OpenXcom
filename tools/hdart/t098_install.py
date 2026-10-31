#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка фонов экрана снаряжения (тикет XP-000098; Vitali 31.10, страница выбора, пункт c1031b_098: Y).

Три картинки темы (HdScreens) - файлы мода hd, как остальные фоны экранов, но через манифест (pack-guard):
  UI/screens/inventory_armory.png  <- art/tickets/t098/cand/armory_9802.png  (оружейная)
  UI/screens/inventory_ship.png    <- art/tickets/t098/cand/ship_9802.png    (на корабле)
  UI/screens/inventory_tarp.png    <- art/tickets/t098/cand/tarpc_9804.png   (брезент крупно)
и три строки в UI/screens/screens.txt: «картинка = id», id inventoryArmory / inventoryShip / inventoryTarp - по одному на
тему, выбор темы опцией oxceHdInvBackdrop (InventoryState.cpp, InventoryBackdrop). Те же строки держит gen_screens.py
(INVENTORY_LINES), чтобы его install их не стёр.

    py -3.13 tools\hdart\t098_install.py                     сухой прогон
    py -3.13 tools\hdart\t098_install.py --install --yes     установить (под очередью правок)
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

PICS = {
    "inventory_armory.png": "art/tickets/t098/cand/armory_9802.png",
    "inventory_ship.png": "art/tickets/t098/cand/ship_9802.png",
    "inventory_tarp.png": "art/tickets/t098/cand/tarpc_9804.png",
}
LINES = ["inventory_armory.png = inventoryArmory", "inventory_ship.png = inventoryShip",
         "inventory_tarp.png = inventoryTarp"]
REPO_SCREENS = os.path.join(ROOT, "user", "mods", "hd", "hd", "UI", "screens")
OUT = os.path.join(ROOT, "art", "tickets", "t098", "install")


def main():
    install = "--install" in sys.argv and "--yes" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    files = {}
    for name, src in PICS.items():
        im = Image.open(src).convert("RGBA")
        if im.size != (1280, 800):
            raise SystemExit("%s: %s, нужно 1280x800" % (src, im.size))
        dst = os.path.join(OUT, name)
        im.save(dst, optimize=True)
        files["UI/screens/" + name] = dst
    cur = os.path.join(REPO_SCREENS, "screens.txt")
    with open(cur, encoding="utf-8-sig") as f:
        text = f.read()
    keep = [l for l in text.split("\n") if l.strip() and not any(l.startswith(x.split(" = ")[0]) for x in LINES)]
    new = "\n".join(keep + LINES) + "\n"
    newp = os.path.join(OUT, "screens.txt")
    with open(newp, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(new)
    files["UI/screens/screens.txt"] = newp
    print("файлов к установке: %d" % len(files))
    for rel in files:
        print("  ", rel, "(новый)" if not os.path.exists(os.path.join(REPO_SCREENS, "..", "..", rel)) else "")
    if not install:
        raise SystemExit("сухой прогон; --install --yes - записать в мод (под очередью правок)")
    backup = os.path.join(ROOT, "art", "_backup", "t098_2026-10-31", "UI", "screens")
    os.makedirs(backup, exist_ok=True)
    shutil.copyfile(cur, os.path.join(backup, "screens.txt"))
    import ticket_scene as ts
    n = ts.install_files(files, "t098_install", "1", "Vitali 31.10, страница выбора, пункт c1031b_098: Y",
                         "XP-000098: фоны экрана снаряжения (оружейная 9802, на корабле 9802, брезент крупно 9804) + строки screens.txt")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
