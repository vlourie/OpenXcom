# -*- coding: utf-8 -*-
"""xBRZ движка для питона: scale(rgba PIL, k) -> PIL RGBA в k раз больше (k 2..6).

Тот же фильтр, которым игра сглаживает классические спрайты (src/Engine/Scalers/xbrz.cpp):
пиксельная лесенка становится ровной диагональю, а не мягкой ступенькой, как у бикубики.
Библиотека собирается build.cmd рядом.
"""
import ctypes
import os

import numpy as np
from PIL import Image

_LIB = None


def _lib():
    global _LIB
    if _LIB is None:
        _LIB = ctypes.CDLL(os.path.join(os.path.dirname(os.path.abspath(__file__)), "xbrz.dll"))
        _LIB.xbrz_scale.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        _LIB.xbrz_scale.restype = None
    return _LIB


def scale(im, k):
    a = np.asarray(im.convert("RGBA"), dtype=np.uint8)
    h, w = a.shape[:2]
    # ARGB в uint32 = байты B,G,R,A на little-endian
    src = np.ascontiguousarray(a[..., [2, 1, 0, 3]]).view(np.uint32).reshape(h, w)
    dst = np.zeros((h * k, w * k), np.uint32)
    _lib().xbrz_scale(k, src.ctypes.data, dst.ctypes.data, w, h)
    out = dst.view(np.uint8).reshape(h * k, w * k, 4)[..., [2, 1, 0, 3]]
    return Image.fromarray(np.ascontiguousarray(out), "RGBA")
