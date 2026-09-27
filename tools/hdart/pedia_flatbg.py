# -*- coding: utf-8 -*-
"""Педия: вернуть ровный фон оригинала вокруг фигуры.

На картинках с ровным однотонным фоном (спрайты бойцов UPed_*, корабль на пустом поле) модель рисует
вокруг фигуры прямоугольную плашку чуть другого тона. Фон оригинала - один цвет, поэтому всё, что в
оригинале этого цвета и лежит дальше нескольких пикселей от фигуры, берём из оригинала как есть;
кромку фигуры сводим мягким переходом.

  py -3 tools/hdart/pedia_flatbg.py --names UPed_Human_8,Necrobomber [--out папка] [--dry-run]
  py -3 tools/hdart/pedia_flatbg.py --all      все картинки серий hd_NN с ровным фоном
"""
import argparse
import glob
import os
import shutil

import numpy as np
from PIL import Image, ImageFilter

ORIG = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "Resources", "Pedia")
REGEN = os.path.join("art", "pedia_regen")


def flat_bg(org):
    """Цвет фона, если он ровный: самый частый цвет по краю кадра занимает большую часть края."""
    a = np.asarray(org)
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    cols, cnt = np.unique(edge.reshape(-1, 3), axis=0, return_counts=True)
    i = cnt.argmax()
    return cols[i] if cnt[i] >= 0.9 * len(edge) else None


def read_orig(path):
    """Оригинал так, как его читает игра (R-043): индексы и палитра, а не convert. Прозрачный индекс
    (из tRNS, иначе 0 - Surface::loadImage) игра не рисует, поэтому он отдаётся отдельной маской."""
    im = Image.open(path)
    if im.mode != "P":
        return im.convert("RGB"), np.zeros((im.height, im.width), bool)
    a = np.asarray(im)
    trns = im.info.get("transparency")
    if isinstance(trns, bytes):
        t = trns.find(b"\x00")
        t = t if t >= 0 else 0
    else:
        t = trns if isinstance(trns, int) else 0
    pal = np.zeros((256, 3), np.uint8)
    p = np.array(im.getpalette()[:768], np.uint8).reshape(-1, 3)
    pal[:len(p)] = p
    return Image.fromarray(pal[a]), a == t


def fix(res_path, org_path, grow=3):
    res = Image.open(res_path).convert("RGB")
    org, hole = read_orig(org_path)
    bg = flat_bg(org)
    if bg is None:
        return None, 0.0
    # прозрачное в оригинале - не фон: берётся из ответа модели, как фигура
    fig = ((np.abs(np.asarray(org).astype(int) - bg).sum(axis=2) > 12) | hole).astype(np.uint8) * 255
    k = res.width / org.width
    m = Image.fromarray(fig).resize(res.size, Image.NEAREST)
    m = m.filter(ImageFilter.MaxFilter(2 * int(grow * k) + 1))
    m = m.filter(ImageFilter.GaussianBlur(max(1.0, k)))
    orig_up = org.resize(res.size, Image.NEAREST)
    out = Image.composite(res, orig_up, m)
    return out, 1 - np.asarray(m).mean() / 255


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="", help="куда класть; по умолчанию поверх, прежнее - в _try1/flatbg")
    ap.add_argument("--dry-run", dest="dry", action="store_true")
    a = ap.parse_args()
    have = {os.path.splitext(f)[0]: os.path.join(ORIG, f) for f in os.listdir(ORIG)}
    files = sorted(glob.glob(os.path.join(REGEN, "hd_[0-9][0-9]", "*__hd__v1.png")))
    if not a.all:
        want = {n.strip() for n in a.names.split(",") if n.strip()}
        files = [f for f in files if os.path.basename(f).split("__")[0] in want]
    bak = os.path.join(REGEN, "_try1", "flatbg")
    n = 0
    for f in files:
        stem = os.path.basename(f).split("__")[0]
        if stem not in have:
            continue
        out, share = fix(f, have[stem])
        if out is None:
            continue
        n += 1
        print("%s: фон ровный, из оригинала %.0f%% кадра" % (stem, share * 100), flush=True)
        if a.dry:
            continue
        if a.out:
            os.makedirs(a.out, exist_ok=True)
            out.save(os.path.join(a.out, os.path.basename(f)))
        else:
            os.makedirs(bak, exist_ok=True)
            if not os.path.exists(os.path.join(bak, os.path.basename(f))):
                shutil.copy2(f, bak)
            out.save(f)
    print("картинок с ровным фоном: %d" % n)


if __name__ == "__main__":
    main()
