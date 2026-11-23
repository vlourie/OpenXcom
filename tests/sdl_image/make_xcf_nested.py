# -*- coding: utf-8 -*-
"""A small XCF whose lists point at the same data again and again: every entry of the list of layers is the same
layer, every entry of the list of tiles is the same tile. The file is a few KiB per thousand layers, the work of a
decoder that follows the lists is layers x tiles. Regression sample for the read budget in IMG_xcf.c (OXCE patch 7).

  py -3 tests/sdl_image/make_xcf_nested.py <out.xcf> <layers> [side, pixels, default 1024]
"""
import struct, sys

out, layers = sys.argv[1], int(sys.argv[2])
side = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
tiles = ((side + 63) // 64) ** 2


def be(*v):
    return struct.pack(">%dI" % len(v), *v)


head = b"gimp xcf file\0" + be(side, side, 0) + be(0, 0)          # RGB, PROP_END
at_layer = len(head) + 4 * (layers + 1) + 4                        # list of layers, 0, list of channels: 0
layer_len = 12 + 4 + 1 + 8 + 8                                      # w h type, name "\0", PROP_END, hierarchy, mask
at_hier = at_layer + layer_len
at_level = at_hier + 12 + 8
at_tile = at_level + 8 + 4 * (tiles + 1)
data = head + be(*([at_layer] * layers), 0) + be(0)
data += be(side, side, 0) + be(1) + b"\0" + be(0, 0) + be(at_hier, 0)
data += be(side, side, 3) + be(at_level, 0)
data += be(side, side) + be(*([at_tile] * tiles), 0)
data += bytes(range(256)) * 16                                      # something to read as the tile
assert len(data) - 4096 == at_tile
open(out, "wb").write(data)
print("%s: %d bytes, %d layers x %d tiles" % (out, len(data), layers, tiles))
