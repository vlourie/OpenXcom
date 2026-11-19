# -*- coding: utf-8 -*-
"""Правки OXCE поверх исходников ветки SDL-1.2 (libs/SDL_image). Каждая замена обязана найтись ровно один раз.
oxce_patch.py <папка libs/SDL_image>"""
import sys, re
from pathlib import Path

root = Path(sys.argv[1])


def edit(name, fn):
    f = root / name
    raw = f.read_bytes()
    crlf = b"\r\n" in raw
    t = raw.decode("latin-1").replace("\r\n", "\n")
    t = fn(t)
    if crlf:
        t = t.replace("\n", "\r\n")
    f.write_bytes(t.encode("latin-1"))


def once(t, a, b):
    assert t.count(a) == 1, (a, t.count(a))
    return t.replace(a, b)


def inc(t):
    if "IMG_oxce.h" in t:
        return t
    return once(t, '#include "SDL_image.h"\n', '#include "SDL_image.h"\n#include "IMG_oxce.h"\n')


for n in "bmp gif jpg lbm pcx png pnm tga tif webp xcf xpm xv".split():
    edit("IMG_%s.c" % n, inc)


def gif(t):
    if "OXCE: the stack" in t:
        return t
    for line, code in (("*state->sp++ = state->table[1][code];", "-3"),
                       ("*state->sp++ = state->firstcode = state->table[1][code];", "-4")):
        m = re.search(r"(?m)^([ \t]*)" + re.escape(line) + "$", t)
        assert m and len(re.findall(r"(?m)^[ \t]*" + re.escape(line) + "$", t)) == 1, line
        ind = m.group(1)
        guard = (ind + "/* OXCE: the stack is full - codes that point at each other in a ring (upstream main, b0c94a0b) */\n" +
                 ind + "if (state->sp == &state->stack[SDL_arraysize(state->stack)]) {\n" +
                 ind + "    RWSetMsg(\"invalid LWZ data\");\n" +
                 ind + "    return " + code + ";\n" +
                 ind + "}\n")
        t = t[:m.start()] + guard + t[m.start():]
    return t


edit("IMG_gif.c", gif)


def lbm(t):
    if "OXCE: a chunk" in t:
        return t
    a = "\t\t\tsize -= bytesloaded;\n"
    b = ("\t\t\t/* OXCE: a chunk shorter than what was read of it, or one of 2 GiB and more, turns the skip below\n"
         "\t\t\t   into a seek backwards - the same chunks are then read again without an end */\n"
         "\t\t\tif ( size < bytesloaded || size - bytesloaded > 0x7FFFFFFF )\n"
         "\t\t\t{\n"
         "\t\t\t\terror=\"invalid IFF chunk size\";\n"
         "\t\t\t\tgoto done;\n"
         "\t\t\t}\n")
    return once(t, a, b + a)


edit("IMG_lbm.c", lbm)


def xcf(t):
    if "xcf_read_be32" in t:
        return t
    a = '#include "IMG_oxce.h"\n'
    b = ("\n/* OXCE: a read past the end of the file gives 0, which ends every list of offsets and is PROP_END\n"
         "   (SDL_ReadBE32 of SDL 1.2 gives back what its variable held - the lists then never end) */\n"
         "static Uint32 xcf_read_be32 (SDL_RWops * src) {\n"
         "  Uint32 v = 0;\n"
         "  if (SDL_RWread (src, &v, sizeof (v), 1) != 1)\n"
         "    return 0;\n"
         "  return SDL_SwapBE32 (v);\n"
         "}\n"
         "#define SDL_ReadBE32 xcf_read_be32\n")
    t = once(t, a, a + b)
    a = "    if (SDL_RWseek (src, prop->length, RW_SEEK_CUR) < 0)\n      return 0;  // ERROR\n"
    b = ("    /* OXCE: a length of 2 GiB and more is a seek backwards: the same properties again, without an end */\n"
         "    if ((Sint32) prop->length < 0 || SDL_RWseek (src, prop->length, RW_SEEK_CUR) < 0) {\n"
         "      prop->id = PROP_END;\n"
         "      return 0;  // ERROR\n"
         "    }\n")
    return once(t, a, b)


edit("IMG_xcf.c", xcf)


def png(t):
    if "OXCE: past the end" in t:
        return t
    a = "\tSDL_RWread(src, area, size, 1);\n"
    b = ("\t/* OXCE: past the end of the file libpng gets zeros, not what its buffer held before: a chunk header left\n"
         "\t   there from the last read is taken for the next chunk again and again, without an end. Zeros are a chunk\n"
         "\t   of no type, which libpng refuses. (upstream main raises png_error at this place, 99982b9b) */\n"
         "\tif ( SDL_RWread(src, area, size, 1) != 1 ) {\n"
         "\t\tmemset(area, 0, size);\n"
         "\t}\n")
    return once(t, a, b)


edit("IMG_png.c", png)
print("правки OXCE поставлены")
