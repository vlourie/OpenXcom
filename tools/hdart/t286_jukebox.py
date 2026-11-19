#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000286: музыкальный автомат BRICKBAR:18-21 - кадры петли нарисованы порознь (другой купол, задняя
стенка, «Х» вместо точек звука). В классике меняются только лампочки и серые точки звука справа.

Все четыре кадра (18, 19, 20, 21) - от ОДНОЙ «погашенной» основы: HD кадр 18, у которого красные лампочки (косой
красный «рог» на куполе, красные пятна сбоку) заглажены окружением. Лампочка каждого кадра - цвет КЛАССИКИ этого
кадра (красный, жёлтый, зелёный, голубой), гладко увеличенный; справа расходятся серые точки звука (anim_flicker,
R-341/R-351). Корпус неподвижный, одинаковый во всех четырёх кадрах, кадр 18 тоже пересобран (иначе его косая
красная лампа не совпала бы с квадратными остальных).

    py -3.13 tools/hdart/t286_jukebox.py            # кадры в art/tickets/t286/out/BRICKBAR/<кадр>.png (18-21)
"""
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import anim_flicker as af  # noqa: E402
import loop_twins as lt    # noqa: E402
import xcom_sprites as xs  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "art" / "tickets" / "t286" / "out" / "BRICKBAR"
SET, BASE, FRAMES, MARGIN = "BRICKBAR", 18, (19, 20, 21), 2


def hue_sat(rgb):
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    mx, mn = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    sat = (mx - mn) / np.maximum(mx, 1)
    dd = np.maximum(mx - mn, 1)
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) * 60
    return h, sat, mx


def lampish(rgb):
    """Цвет лампочки классики: красный, жёлтый, зелёный, голубой; не оранжевая отделка, не коричневый купол, не окно."""
    h, sat, mx = hue_sat(rgb)
    return (sat > 0.35) & (mx > 90) & ((h < 10) | (h > 330) | ((h > 48) & (h < 200)))


def red_lamp_hd(rgb):
    """Красная лампочка HD основы: красный-малиновый тон (не оранжевая отделка h ~ 25, не розовое окно h ~ 300+)."""
    h, sat, mx = hue_sat(rgb)
    return (sat > 0.40) & (mx > 40) & ((h < 12) | (h > 338))


def neutral_base(hb, cb, lamp_cl):
    """HD кадр 18 без красных лампочек: пиксели лампочки (чуть шире) залиты окружением; альфа там, где в классике пусто,
    нулевая (косой «рог» над куполом уходит)."""
    k = hb.shape[1] // cb.shape[1]
    rgb = hb[..., :3].astype(np.uint8)
    a = hb[..., 3] > 0
    # только возле лампочек классики кадра 18 (на 1 пиксель базы шире): розовые вещи в окне - тоже «красные», их не трогать
    near = af.up(af.dilate(lamp_cl, 1), k)
    m = red_lamp_hd(rgb) & a & near
    m = af.dilate(m, 2) & a
    fill = rgb.copy()
    inp = cv2.inpaint(fill, (m * 255).astype(np.uint8), 4, cv2.INPAINT_TELEA)
    out = hb.copy()
    out[..., :3] = np.where(m[..., None], inp, rgb)
    # «рог»: пиксели лампы вне силуэта классики, расширенного на 1 пиксель базы, - прозрачные
    sil = af.dilate(af.up((cb > 0), k), k)
    gone = m & ~sil
    out[..., 3] = np.where(gone, 0, out[..., 3])
    out[gone, :3] = 0
    return out, m


def relight(arr, hb, cf, lamp, pal, k):
    """Лампочка - цвет классики кадра (гладко увеличенный), а не красный HD основы плюс разница: сумма давала
    салатовый вместо жёлтого."""
    lw = af.up(lamp.astype(np.float32), k)
    lw = np.clip(af.gauss(lw, k * 0.3) * 1.8, 0, 1)
    pre = af.classic_up(cf, pal, k)                    # предумноженный RGBA
    a = np.maximum(pre[..., 3:], 1.0)
    col = np.clip(pre[..., :3] * 255.0 / a, 0, 255)
    out = arr.astype(np.float32)
    vis = (hb[..., 3:] > 0).astype(np.float32)
    w = lw[..., None] * vis
    out[..., :3] = out[..., :3] * (1 - w) + col * w
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def build():
    files = lt.game_files()
    pal = af.load_pal()
    tab = files.get(SET + ".TAB")
    fr = xs.read_pck(str(files[SET + ".PCK"]), str(tab) if tab else None)
    pack = ROOT / "user" / "mods" / "hd" / "hd" / "TERRAIN" / (SET + ".PCK")
    cb = np.asarray(fr[BASE])
    hb0 = af.rgba(pack / ("%d.png" % BASE))
    k = hb0.shape[1] // cb.shape[1]
    lamp18 = lampish(pal[cb].astype(np.int32)) & (cb > 0)
    hb, gone = neutral_base(hb0, cb, lamp18)
    OUT.mkdir(parents=True, exist_ok=True)
    out = {}
    near_body = af.dilate(cb > 0, 1)
    for f in (BASE,) + FRAMES:
        cf0 = np.asarray(fr[f])
        cf_rgb = pal[cf0].astype(np.int32)
        lamp = lampish(cf_rgb) & (cf0 > 0)
        # точки звука: отдельные пиксели вне корпуса (не касаются его даже по диагонали); у 19 и 21 контур купола
        # в классике на пару пикселей иной - это не звук
        dots = (cf0 > 0) & ~near_body if f != BASE else np.zeros_like(cb, bool)
        cf_dots = np.where(dots, cf0, cb)
        w = af.weight(cb, cf_dots, k, MARGIN)
        arr = af.compose_delta(hb, cb, cf_dots, pal, w) if dots.any() else hb.astype(np.uint8)
        arr = relight(arr, hb, cf0, lamp, pal, k)
        p = OUT / ("%d.png" % f)
        Image.fromarray(arr, "RGBA").save(p)
        out[f] = p
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    r = build()
    print("кадров: %d в %s" % (len(r), OUT))
