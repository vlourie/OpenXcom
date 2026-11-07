#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Заготовки кадров к тикетам XP-000402 (стулья), XP-000406 (стол), XP-000408 (раковина).

В мод ничего не ставит: кладёт кадры в art/tickets/t402_409/cand/<вариант>/<НАБОР>_<кадр>.png.
Видеокарту не трогает: перенос цвета - obj_derive.transfer (процедурно по оригиналам).

  402A  XB1BR 54-57 из снимка пака 22.09 (откат)
  402B  XB1BR 54-57 = HD синего XBASE1 54-57, перекрашенный в серый тон классики XB1BR
  406A  XB1BR 58 из снимка 22.09
  408A  XB3BITZ1:19 = одобренный XB3BITZ1_MAG:19, перекрашенный в бежевую керамику классики
        XB3BITZ1:19; :20 - зеркало с маской своей классики; вся семья из 29 кадров:
        копия классики - копией файла, зеркало - файлом :20, перекраска - переносом цвета

    py -3.13 tools/hdart/t402_409_cand.py
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(os.path.dirname(os.path.dirname(HERE)))

import numpy as np                       # noqa: E402
from PIL import Image, ImageFilter       # noqa: E402

import obj_derive as od                  # noqa: E402
import ticket_scene as ts                # noqa: E402

ROOT = os.getcwd()
GAME = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd", "TERRAIN")
SNAP = os.path.join(ROOT, "art", "_backup", "hd_TERRAIN_2026-09-22")
OUT = os.path.join(ROOT, "art", "tickets", "t402_409", "cand")

SC = ts.Scene()

FAMILY = """XB3BITZ1:19 XB3BITZ1:20 A_DECOR:66 A_DECOR:67 BATHBITZ:19 BATHBITZ:20 BATHBITZ_HT:11 BATHBITZ_HT:12
COMDECOR:36 COMPLEXBITSMOON:23 CRIBDECOR:37 DECORLUX:77 FREIGHTER_AGRARIAN:66 FREIGHTER_AGRARIAN:67 FREIGHTER_CARGO:84
FREIGHTER_COMMAND:105 FREIGHTER_PASSENGER:67 FREIGHTER_PASSENGER:68 FREIGHTER_TECHNICAL:126 GOVTDECOR:54 JAILBITES:8
MADDECOR:84 MADDECOR_WASTE:72 MAGETOWER0:17 MILBARR:34 MILBARRGHOUL:35 SEAMADDECOR:84""".split()


def hd(root, s, f):
    return Image.open(os.path.join(root, s + ".PCK", "%d.png" % f)).convert("RGBA")


def orig(s, f):
    """Оригинал 32x40 RGBA, палитра Пираток (R-444)."""
    c = SC.classic(s, f)
    return None if c is None else Image.fromarray(np.asarray(c)[::4, ::4].copy(), "RGBA")


def clip(im, o, grow=2):
    """Контур по маске классики: альфа не выходит за силуэт оригинала (с допуском grow HD-пикселей)."""
    m = np.asarray(o)[..., 3] > 0
    mm = Image.fromarray((m * 255).astype(np.uint8)).resize(im.size, Image.NEAREST)
    mm = mm.filter(ImageFilter.MaxFilter(2 * grow + 1))
    a = np.asarray(im).copy()
    a[..., 3] = np.minimum(a[..., 3], np.asarray(mm))
    a[a[..., 3] == 0, :3] = 0
    return Image.fromarray(a, "RGBA")


def put(variant, s, f, im):
    d = os.path.join(OUT, variant)
    os.makedirs(d, exist_ok=True)
    im.save(os.path.join(d, "%s_%d.png" % (s, f)))


def copy(variant, s, f, src):
    d = os.path.join(OUT, variant)
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(src, os.path.join(d, "%s_%d.png" % (s, f)))


def main():
    # 402A / 406A: откат на снимок 22.09
    for f in (54, 55, 56, 57):
        copy("402A", "XB1BR", f, os.path.join(SNAP, "XB1BR.PCK", "%d.png" % f))
    copy("406A", "XB1BR", 58, os.path.join(SNAP, "XB1BR.PCK", "58.png"))

    # 402B: серый XB1BR из HD синего XBASE1 (ракурсы и маски совпадают кадр в кадр, зеркала те же)
    for f in (54, 55, 56, 57):
        o_t = orig("XB1BR", f)
        im = od.transfer(hd(GAME, "XBASE1", f), orig("XBASE1", f), o_t)
        put("402B", "XB1BR", f, clip(im, o_t))

    # 408A: из одобренного MAG:19
    o19, o20 = orig("XB3BITZ1", 19), orig("XB3BITZ1", 20)
    mag19 = hd(GAME, "XB3BITZ1_MAG", 19)
    n19 = clip(od.transfer(mag19, orig("XB3BITZ1_MAG", 19), o19), o19)
    n20 = clip(od.derive(n19, o19, o20, "зеркало"), o20)
    put("408A", "XB3BITZ1", 19, n19)
    put("408A", "XB3BITZ1", 20, n20)
    a19, a20 = np.asarray(o19), np.asarray(o20)
    for k in FAMILY[2:]:
        s, f = k.rsplit(":", 1)
        f = int(f)
        o = orig(s, f)
        arr = np.asarray(o)
        if np.array_equal(arr, a19):
            put("408A", s, f, n19)
        elif np.array_equal(arr, a20):
            put("408A", s, f, n20)
        else:
            # перекраска той же формы (MADDECOR_WASTE:72): перенос цвета своей классики
            put("408A", s, f, clip(od.transfer(n19, o19, o), o))
        print("408A", k)
    # MAG:19 одобрен - не трогаем; MAG:20 - зеркало одобренного MAG:19 с маской своей классики
    m20 = orig("XB3BITZ1_MAG", 20)
    put("408A", "XB3BITZ1_MAG", 20, clip(od.derive(mag19, orig("XB3BITZ1_MAG", 19), m20, "зеркало"), m20))


if __name__ == "__main__":
    main()
