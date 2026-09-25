#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка map_update.py без видеокарты, на временных папках: настоящий учёт и мод не трогаются.

1. Первое обновление карты - «карта», в архиве ровно то, что записано в учёт, байт в байт.
2. Повторная сборка той же карты ничего не выдаёт: всё уже выдано.
3. Перерисованный кадр уходит отдельным «исправлением» - один файл, а не вся карта.
4. apply не кладёт в мод ни ждущее решения, ни отклонённое; заменённое уходит в резерв.

    py tools\\test_map_update.py
"""
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "hdart"), HERE]

from PIL import Image                                   # noqa: E402

import map_update as mu                                 # noqa: E402

T, B = "CULTA_UBER", "CULTAFARM01"
SRC = os.path.join("art", "maps", "paint", "CULTA_UBER_t17")


def main():
    if not os.path.isdir(SRC):
        print("нет %s - нечего проверять" % SRC)
        return 1
    tmp = tempfile.mkdtemp()
    root, upd, mod = os.path.join(tmp, "root"), os.path.join(tmp, "upd"), os.path.join(tmp, "mod")
    shutil.copytree(SRC, root)
    status = os.path.join(tmp, "MAP_STATUS.md")
    # в «моде» уже лежит прежний кадр BARN 11: его обязаны увести в резерв, а не затереть молча
    old11 = os.path.join(mod, "hd", "TERRAIN", "BARN.PCK", "11.png")
    os.makedirs(os.path.dirname(old11))
    Image.new("RGBA", (128, 160), (200, 0, 0, 255)).save(old11)
    old_bytes = open(old11, "rb").read()
    mu.BACKUP = os.path.join(tmp, "backup")
    base = ["--updates", upd, "--status", status]
    bad = 0

    def check(ok, text):
        nonlocal bad
        print("%s  %s" % ("ok " if ok else "BAD", text))
        bad += 0 if ok else 1

    mu.main(base + ["pack", "--terrain", T, "--block", B, "--root", root, "--mod", mod])
    led = mu.read_ledger()
    z = zipfile.ZipFile(os.path.join(upd, mu.upd_name(1, T, B) + ".zip"))
    names = set(z.namelist())
    same = all(r["файл"] in names and mu.hashlib.sha256(z.read(r["файл"])).hexdigest() == r["sha"] for r in led)
    check(led and all(r["вид"] == "карта" for r in led) and same,
          "обновление 1 - карта: %d файлов, архив совпадает с учётом" % len(led))
    check(any(r["файл"].endswith("BARN.PCK/11.png") and r["в_моде"] == "да" for r in led),
          "прежний кадр мода BARN 11 замечен")

    n0 = len(mu.read_ledger())
    mu.main(base + ["pack", "--terrain", T, "--block", B, "--root", root, "--mod", mod])
    check(len(mu.read_ledger()) == n0, "повторная сборка ничего не выдала")

    p13 = os.path.join(root, "BARN.PCK", "13.png")
    im = Image.open(p13).convert("RGBA")
    im.putpixel((64, 80), (1, 2, 3, 255))
    im.save(p13)
    mu.main(base + ["pack", "--terrain", T, "--block", B, "--root", root, "--mod", mod])
    fix = [r for r in mu.read_ledger() if r["обновление"] == "2"]
    check(len(fix) == 1 and fix[0]["вид"] == "исправление" and fix[0]["что"] == "исправлен"
          and fix[0]["файл"].endswith("BARN.PCK/13.png"), "перерисованный BARN 13 - исправление из одного файла")

    check(mu.main(base + ["apply", "1", "--mod", mod]) == 1 and open(old11, "rb").read() == old_bytes,
          "apply без решения отказывается и мод не трогает")
    mu.main(base + ["accept", "1"])
    mu.main(base + ["reject", "1", "--frames", "BARN:0"])
    mu.main(base + ["apply", "1", "--mod", mod])
    led = [r for r in mu.read_ledger() if r["обновление"] == "1"]
    in_mod = [r for r in led if r["решение"] == "в моде"]
    ok_files = all(mu.sha(os.path.join(mod, *r["файл"].split("/"))) == r["sha"] for r in in_mod)
    check(in_mod and ok_files and len(in_mod) == len(led) - sum(r["набор"] == "BARN" and r["кадр"] == "0"
                                                              for r in led),
          "apply: принятое в моде до байта (%d файлов)" % len(in_mod))
    check(not os.path.exists(os.path.join(mod, "hd", "TERRAIN", "BARN.PCK", "0.png")),
          "отклонённый BARN 0 в мод не попал")
    bk = os.path.join(mu.BACKUP, mu.upd_name(1, T, B), "hd", "TERRAIN", "BARN.PCK", "11.png")
    check(os.path.exists(bk) and open(bk, "rb").read() == old_bytes, "прежний BARN 11 - в резерве")
    text = open(status, encoding="utf-8-sig").read()
    check("| %s | %s | 0001 | карта |" % (T, B) in text and "0002" in text, "дорожная карта: карта и исправление")
    print("итог: %s" % ("всё верно" if not bad else "ОШИБОК %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
