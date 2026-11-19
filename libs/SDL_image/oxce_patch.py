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


def xcf_budget(t):
    if "xcf_budget" in t:
        return t
    a = "#define SDL_ReadBE32 xcf_read_be32\n"
    b = ("\n/* OXCE: the read budget. Every list of the file (layers, channels, levels, tiles) is a list of offsets, and\n"
         "   nothing makes two entries point at different data: a file of a few KiB whose entries all point at one\n"
         "   layer and one tile is decoded layers x tiles times. A file that is what GIMP writes has every structure\n"
         "   once, so its decoder reads no byte twice, except that the last tile of a layer is read by its largest\n"
         "   possible length (24576 bytes). The budget is twice the file plus that tail for every layer; a layer with\n"
         "   its hierarchy, level and list of tiles takes 64 bytes at the least, a tile takes the 4 bytes of its\n"
         "   offset. Past the budget every read gives nothing and the decoder stops. */\n"
         "typedef struct {\n"
         "  SDL_RWops * src;\n"
         "  Uint64 left;\n"
         "  int spent;\n"
         "} xcf_budget;\n"
         "\n"
         "static int xcf_budget_seek (SDL_RWops * ctx, int offset, int whence) {\n"
         "  xcf_budget * b = (xcf_budget *) ctx->hidden.unknown.data1;\n"
         "  return b->src->seek (b->src, offset, whence);\n"
         "}\n"
         "\n"
         "static int xcf_budget_read (SDL_RWops * ctx, void * ptr, int size, int maxnum) {\n"
         "  xcf_budget * b = (xcf_budget *) ctx->hidden.unknown.data1;\n"
         "  Uint64 want = (Uint64) (size > 0 ? size : 0) * (Uint64) (maxnum > 0 ? maxnum : 0);\n"
         "  if (want == 0)\n"
         "    want = 1;\n"
         "  if (b->spent || want > b->left) {\n"
         "    b->spent = 1;\n"
         "    return 0;\n"
         "  }\n"
         "  b->left -= want;\n"
         "  return b->src->read (b->src, ptr, size, maxnum);\n"
         "}\n"
         "\n"
         "static int xcf_spent (SDL_RWops * src) {\n"
         "  return src->read == xcf_budget_read && ((xcf_budget *) src->hidden.unknown.data1)->spent;\n"
         "}\n"
         "\n"
         "static Uint64 xcf_tiles (Uint32 width, Uint32 height) {\n"
         "  return (((Uint64) width + 63) / 64) * (((Uint64) height + 63) / 64);\n"
         "}\n")
    t = once(t, a, a + b)
    a = "      SDL_RWseek (src, level->tile_file_offsets [j], RW_SEEK_SET);\n"
    b = ("      if (xcf_spent (src)) {  /* OXCE: the read budget */\n"
         "        free_xcf_level (level);\n"
         "        free_xcf_hierarchy (hierarchy);\n"
         "        return 1;\n"
         "      }\n")
    t = once(t, a, b + a)
    a = "  unsigned char * (* load_tile) (SDL_RWops *, Uint32, int, int, int);\n"
    b = ("  /* OXCE: the read budget, see xcf_budget */\n"
         "  SDL_RWops budget_rw;\n"
         "  xcf_budget budget;\n"
         "  Uint64 file_size, tiles;\n")
    t = once(t, a, a + b)
    a = "  /* Initialize the data we will clean up when we're done */\n  surface = NULL;\n"
    b = ("\n  {  /* OXCE: the read budget */\n"
         "    int end = SDL_RWseek (src, 0, RW_SEEK_END);\n"
         "    SDL_RWseek (src, start, RW_SEEK_SET);\n"
         "    file_size = end > start ? (Uint64) (end - start) : 0;\n"
         "  }\n"
         "  budget.src = src;\n"
         "  budget.left = 2 * file_size + 4096;\n"
         "  budget.spent = 0;\n"
         "  memset (&budget_rw, 0, sizeof (budget_rw));\n"
         "  budget_rw.seek = xcf_budget_seek;\n"
         "  budget_rw.read = xcf_budget_read;\n"
         "  budget_rw.hidden.unknown.data1 = &budget;\n"
         "  src = &budget_rw;\n"
         "  tiles = 0;\n")
    t = once(t, a, a + b)
    a = "\n  fp = SDL_RWtell (src);\n"
    b = ("\n  /* OXCE: a layer takes 64 bytes of the file at the least */\n"
         "  if ((Uint64) offsets > file_size / 64) {\n"
         "    error = \"XCF: more layers than the file can hold\";\n"
         "    goto done;\n"
         "  }\n"
         "  budget.left += (Uint64) offsets * 24576;\n")
    t = once(t, a, a + b)
    a = "    layer = read_xcf_layer (src, head);\n    if (layer != NULL) {\n"
    b = ("      /* OXCE: every tile of every layer has its own offset in the file, 4 bytes at the least */\n"
         "      tiles += xcf_tiles (layer->width, layer->height);\n"
         "      if (tiles > file_size / 4 || xcf_spent (src)) {\n"
         "        free_xcf_layer (layer);\n"
         "        error = \"XCF: the lists of the file point at the same data again and again\";\n"
         "        break;\n"
         "      }\n")
    t = once(t, a, a + b)
    a = "  SDL_FreeSurface (lays);\n"
    b = ("\n  if (error)  /* OXCE: the read budget */\n"
         "    goto done;\n")
    t = once(t, a, a + b)
    a = "    channel = (xcf_channel **) realloc (channel, sizeof (xcf_channel *) * (chnls+1));\n"
    b = ("    /* OXCE: a channel is as large as the image and has its tiles too */\n"
         "    tiles += xcf_tiles (head->width, head->height);\n"
         "    if (tiles > file_size / 4 || xcf_spent (src))\n"
         "      break;\n")
    return once(t, a, b + a)


edit("IMG_xcf.c", xcf_budget)


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
