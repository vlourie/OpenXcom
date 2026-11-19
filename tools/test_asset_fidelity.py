#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""asset_fidelity: копия оригинала проходит; потухший сигнальный цвет, осветлённая арматура и подменённая
крупная часть - ловятся. Синтетика без данных игры."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import asset_fidelity as AF     # noqa: E402


def sprite():
    """32x40: серый стол, на нём красная банка, тёмные ножки."""
    o = np.zeros((40, 32, 4), np.uint8)
    o[14:24, 4:28] = (150, 140, 120, 255)        # столешница
    o[24:38, 5:8] = (30, 28, 30, 255)            # ножки
    o[24:38, 24:27] = (30, 28, 30, 255)
    o[6:14, 12:18] = (200, 25, 40, 255)          # банка
    return o


def x4(a):
    return np.repeat(np.repeat(a, 4, 0), 4, 1)


def run():
    o = sprite()
    up = x4(o)
    ok = AF.measure(o, up)
    assert AF.verdict(ok) == "PASS", ok
    # банка потухла: красный к серому
    dull = up.copy()
    m = x4((o[..., 0] == 200))
    dull[m, :3] = (110, 80, 82)
    r = AF.measure(o, dull)
    assert r["COLOR"][0] == "FAIL", r["COLOR"]
    # арматура осветлена до тона стола
    lit = up.copy()
    lit[x4(o[..., 0] == 30), :3] = (140, 130, 115)
    r = AF.measure(o, lit)
    assert r["DARK"][0] == "FAIL", r["DARK"]
    # столешница подменена цветом ножек - крупная часть пропала
    sw = up.copy()
    sw[x4(o[..., 0] == 150), :3] = (30, 28, 30)
    r = AF.measure(o, sw)
    assert r["PARTS"][0] == "REVIEW", r["PARTS"]
    # контроль меры: при одной только смене тона (всё темнее на 10) - не FAIL
    dim = up.copy()
    dim[..., :3] = np.clip(dim[..., :3].astype(int) - 10, 0, 255)
    r = AF.measure(o, dim)
    assert AF.verdict(r) != "FAIL", r
    # кайма: край тела окрашен синей подложкой - EDGE_COLOR_HALO FAIL; у копии кайма 0
    assert ok["EDGE_COLOR_HALO"][0] == "PASS" and ok["halo"] == 0, ok["EDGE_COLOR_HALO"]
    op = up[..., 3] > 128
    inner = op.copy()
    for _ in range(AF.HALO_BAND):
        g = inner.copy()
        g[1:] &= inner[:-1]
        g[:-1] &= inner[1:]
        g[:, 1:] &= inner[:, :-1]
        g[:, :-1] &= inner[:, 1:]
        inner = g
    edge = op & ~inner
    blue = up.copy()
    blue[edge, :3] = (59, 87, 239)
    r = AF.measure(o, blue)
    assert r["EDGE_COLOR_HALO"][0] == "FAIL" and AF.verdict(r) == "FAIL", r["EDGE_COLOR_HALO"]
    # контроль: край в СОБСТВЕННЫЙ цвет предмета (красный банки на столе и ножках) - не кайма
    own = up.copy()
    own[edge, :3] = (200, 25, 40)
    r = AF.measure(o, own)
    assert r["EDGE_COLOR_HALO"][0] == "PASS", r["EDGE_COLOR_HALO"]
    # размер не x4 - ошибка, а не вердикт
    try:
        AF.measure(o, up[:-4])
        raise AssertionError("размер не проверен")
    except ValueError:
        pass
    print("test_asset_fidelity: ok")


if __name__ == "__main__":
    run()
