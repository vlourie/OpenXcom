"""NEKOMIMI в устройстве других рас: тело в слое 4 вместе с головой, волосы слоя 15 - копия волос из него.

Конвейер рас ждёт имена RACE__2__<внешность>_NUDE, RACE__10__HEAD_<внешность>, RACE__13__HAIR_<внешность>. Здесь это другие имена на
те же файлы классики, а голова вырезана отдельным файлом: всё, что выше шеи и совпадает в двух позах. Внешность "F0" - поза NUDE,
"AF0" - та же кошка в позе NUDE_ALT. Головы и волосы в двух позах одни и те же, поэтому у "AF0" их имена на файлы "F0".
"""
import os

import numpy as np
from PIL import Image
import doll_b2_render as db

RACE = "NEKOMIMI"
OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", RACE.lower())
KEYS = ["F%d" % i for i in range(24)] + ["M%d" % i for i in range(24)]
LOOKS = KEYS + ["A" + k for k in KEYS]
HEAD_ROW = 66                                       # выше - голова; основа тела рисуется ниже
NECK_ROW = 69
HEAD_X = 92                                         # правее - поднятая кисть позы NUDE, слева от неё всё общее у двух поз (замер 07.11)
FACE_BOX = (78, 57, 85, 66)
REAL = {}                                           # имя конвейера -> имя настоящего слоя
MAXI = ("F0", "F2", "F4", "F5", "F6", "F10", "F13", "F18", "F21", "F23", "M1", "M4", "M10", "M12", "M21")   # размер фигуры, он же размер вещей
MINI = ("F3", "F7", "F11", "F12", "F17", "M2", "M3", "M7", "M11", "M14", "M15", "M18", "M20", "M23")


def key_of(look):
    return look[1:] if look[0] == "A" else look


def size_of(look):
    key = key_of(look)
    return "MAXI" if key in MAXI else "MINI" if key in MINI else "MIDI"


def real_body(look):
    return "%s__4__%s_%s" % (RACE, "NUDE_ALT" if look[0] == "A" else "NUDE", key_of(look))


def real_hair(look):
    return "%s__15__HAIR_%s" % (RACE, key_of(look))


def head_mask(files, key):
    a = db.load_indices(files[real_body(key)])
    m = (a == db.load_indices(files[real_body("A" + key)])) & (a != 0)
    m[NECK_ROW:] = False
    m[:, HEAD_X:] = False
    return m


def bind(files):
    """Добавить в словарь файлов имена конвейера; файлы голов лежат в art/doll/pipe_pilot/nekomimi/classic/."""
    d = os.path.join(OUT, "classic")
    os.makedirs(d, exist_ok=True)
    for key in KEYS:
        p = os.path.join(d, "head_%s.png" % key.lower())
        if not os.path.exists(p):
            src = Image.open(files[real_body(key)])
            idx = db.load_indices(files[real_body(key)]) * head_mask(files, key)
            im = Image.fromarray(idx.astype(np.uint8), "P")
            im.putpalette(src.getpalette())
            im.save(p)
        for look in (key, "A" + key):
            files["%s__2__%s_NUDE" % (RACE, look)] = files[real_body(look)]
            files["%s__10__HEAD_%s" % (RACE, look)] = p
            files["%s__13__HAIR_%s" % (RACE, look)] = files[real_hair(look)]
            REAL["%s__2__%s_NUDE" % (RACE, look)] = (real_body(look), None)
            REAL["%s__10__HEAD_%s" % (RACE, look)] = (real_body(key), key)
            REAL["%s__13__HAIR_%s" % (RACE, look)] = (real_hair(look), None)
    return files


def patch_b2(dp, files):
    """B2 есть у настоящих слоёв: головой служит B2 тела по маске головы, поверх самого тела она ничего не меняет."""
    orig = dp.b2_layer

    def b2_layer(name):
        if name not in REAL:
            return orig(name)
        real, key = REAL[name]
        im, how = orig(real)
        if im is None or key is None:
            return im, how
        m = Image.fromarray((head_mask(files, key) * 255).astype(np.uint8)).resize(im.size, Image.NEAREST)
        im = im.copy()
        im.putalpha(Image.fromarray(np.minimum(np.asarray(im.getchannel("A")), np.asarray(m))))
        return im, how

    dp.b2_layer = b2_layer
