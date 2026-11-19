#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Сжатая таблица пилота обрушения: вместо 376 тыс. строк CollapsePilotData.h в исходнике движок встраивает в exe
файл данных src/Battlescape/CollapsePilotData.bin (сборка стенда, OXCE_AI_DEV) или CollapsePilotData.player.bin
(игроки: без экспериментальных зданий) и разворачивает его при первом обращении (CollapsePilotData.cpp).

Формат v1 - zlib (уровень 9) над потоком little-endian int32:
    magic 0x42435058 ("XPCB"), версия 1, число блоков
    на блок: строка label, строка name, sx sy sz x0 x1 y0 y1 experimental,
             число наборов и строки наборов,
             части (число, затем 17 полей CollapsePart по столбцам: все kind, все x, ...),
             targets, keep (части, -1 = нет массива), treeCols (-1 = nullptr) и nTreeCols, crowns (-1 = nullptr) и nCrowns
    строка - длина в байтах, затем байты, дополненные нулями до кратного 4
    массив int - длина, затем значения; длина -1 - массива нет (nullptr в C++)
Столбцы вместо строк - ради сжатия (у столбца мало разных значений); значения и порядок частей те же, что в заголовке.

    py -3.13 tools\collapse_blob.py from-header <CollapsePilotData.h> <выход.bin> [--player]
                                                  перевести прежний заголовок (перенос 27.10 и сверка)
    py -3.13 tools\collapse_blob.py dump <файл.bin>     сводка: блоков, частей, экспериментальных
"""
import struct
import sys
import zlib

MAGIC = 0x42435058
VERSION = 1
FIELDS = 17   # CollapsePart: kind x y z set mcd flags contact limL nEdge e0x e0y e1x e1y mark tOff tCount


class Block:
    """Блок карты пилота - те же поля, что CollapseBlock в CollapseCore.h."""
    __slots__ = ("label", "name", "sx", "sy", "sz", "x0", "x1", "y0", "y1", "experimental", "sets", "parts",
                 "targets", "keep", "treeCols", "nTreeCols", "crowns", "nCrowns")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw[k])

    def __eq__(self, other):
        return all(getattr(self, k) == getattr(other, k) for k in self.__slots__)


# ------------------------------------------------------------------ запись и чтение

def encode(blocks):
    out = []

    def ints(*v):
        out.extend(v)

    def string(s):
        b = s.encode("utf-8")
        b += b"\0" * (-len(b) % 4)
        ints(len(s.encode("utf-8")))
        out.extend(struct.unpack("<%di" % (len(b) // 4), b))

    def array(a):
        if a is None:
            ints(-1)
        else:
            ints(len(a), *a)

    def parts(P):
        if P is None:
            ints(-1)
            return
        ints(len(P))
        for f in range(FIELDS):
            out.extend(p[f] for p in P)

    ints(MAGIC, VERSION, len(blocks))
    for b in blocks:
        string(b.label)
        string(b.name)
        ints(b.sx, b.sy, b.sz, b.x0, b.x1, b.y0, b.y1, b.experimental)
        ints(len(b.sets))
        for s in b.sets:
            string(s)
        parts(b.parts)
        array(b.targets)
        parts(b.keep)
        array(b.treeCols)
        ints(b.nTreeCols)
        array(b.crowns)
        ints(b.nCrowns)
    raw = struct.pack("<%di" % len(out), *out)
    return struct.pack("<I", len(raw)) + zlib.compress(raw, 9)


def decode(data):
    size = struct.unpack_from("<I", data)[0]
    raw = zlib.decompress(data[4:])
    if len(raw) != size:
        raise ValueError("collapse blob: размер %d, ожидалось %d" % (len(raw), size))
    v = struct.unpack("<%di" % (len(raw) // 4), raw)
    pos = 0

    def take(n=1):
        nonlocal pos
        r = v[pos:pos + n]
        pos += n
        return r

    def one():
        return take()[0]

    def string():
        n = one()
        words = (n + 3) // 4
        return struct.pack("<%di" % words, *take(words))[:n].decode("utf-8")

    def array():
        n = one()
        return None if n < 0 else list(take(n))

    def parts():
        n = one()
        if n < 0:
            return None
        cols = [take(n) for _ in range(FIELDS)]
        return [tuple(c[i] for c in cols) for i in range(n)]

    if one() != MAGIC or one() != VERSION:
        raise ValueError("collapse blob: не тот формат")
    blocks = []
    for _ in range(one()):
        label, name = string(), string()
        sx, sy, sz, x0, x1, y0, y1, exp = take(8)
        sets = [string() for _ in range(one())]
        P = parts()
        targets = array()
        keep = parts()
        treeCols = array()
        nTreeCols = one()
        crowns = array()
        nCrowns = one()
        blocks.append(Block(label=label, name=name, sx=sx, sy=sy, sz=sz, x0=x0, x1=x1, y0=y0, y1=y1, experimental=exp,
                            sets=sets, parts=P, targets=targets, keep=keep, treeCols=treeCols, nTreeCols=nTreeCols,
                            crowns=crowns, nCrowns=nCrowns))
    if pos != len(v):
        raise ValueError("collapse blob: лишние данные в конце")
    return blocks


def load(path):
    with open(path, "rb") as f:
        return decode(f.read())


def write(path, blocks):
    data = encode(blocks)
    if decode(data) != blocks:
        raise SystemExit("collapse blob: запись не читается обратно один в один")
    with open(path, "wb") as f:
        f.write(data)
    return data


def player(blocks):
    """Игрокам - без экспериментальных зданий (их берёт только сборка стенда, OXCE_AI_DEV)."""
    return [b for b in blocks if not b.experimental]


# ------------------------------------------------------------------ перенос прежнего заголовка

def from_header(text):
    """Блоки из CollapsePilotData.h (формат tools/collapse_pilot_export.py до 27.10)."""
    import re
    sets, parts, ints = {}, {}, {}
    for m in re.finditer(r'static const char \*const (sets\d+)\[\] = \{([^}]*)\};', text):
        sets[m.group(1)] = re.findall(r'"([^"]*)"', m.group(2))
    for m in re.finditer(r"static const CollapsePart (\w+)\[\] = \{\n(.*?)\n\};", text, re.S):
        rows = re.findall(r"\{([^{}]*)\}", m.group(2))
        parts[m.group(1)] = [tuple(int(s) for s in r.split(",")) for r in rows]
        if any(len(p) != FIELDS for p in parts[m.group(1)]):
            raise SystemExit("заголовок: в %s не %d полей" % (m.group(1), FIELDS))
    for m in re.finditer(r"static const int (\w+)\[\] = \{([^}]*)\};", text):
        ints[m.group(1)] = [int(s) for s in m.group(2).split(",")]
    body = re.search(r"static const CollapseBlock blocks\[\] = \{\n(.*?)\n\};", text, re.S).group(1)
    blocks = []
    for row in body.split("\n"):
        m = re.fullmatch(r'\t\{ "([^"]*)", "([^"]*)", (.*) \},', row)
        f = [s.strip() for s in m.group(3).split(",")]
        sx, sy, sz, x0, x1, y0, y1 = map(int, f[0:7])
        nSets, nParts = int(f[8]), int(f[10])
        P = parts[f[9]]
        if len(sets[f[7]]) != nSets or len(P) != nParts:
            raise SystemExit("заголовок: у %s число наборов или частей не сходится" % m.group(1))
        ptr = lambda name, table: None if name == "nullptr" else table[name]
        keep = ptr(f[13], parts)
        if (len(keep) if keep else 0) != int(f[14]):
            raise SystemExit("заголовок: у %s nKeep не сходится" % m.group(1))
        blocks.append(Block(label=m.group(1), name=m.group(2), sx=sx, sy=sy, sz=sz, x0=x0, x1=x1, y0=y0, y1=y1,
                            experimental=int(f[12]), sets=sets[f[7]], parts=P, targets=ints[f[11]], keep=keep,
                            treeCols=ptr(f[15], ints), nTreeCols=int(f[16]), crowns=ptr(f[17], ints),
                            nCrowns=int(f[18])))
    count = int(re.search(r"static const int blockCount = (\d+);", text).group(1))
    if count != len(blocks):
        raise SystemExit("заголовок: blockCount %d, блоков %d" % (count, len(blocks)))
    return blocks


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "from-header":
        blocks = from_header(open(sys.argv[2], encoding="utf-8").read())
        if "--player" in sys.argv:
            blocks = player(blocks)
        data = write(sys.argv[3], blocks)
        print("%s: блоков %d, частей %d, %d байт" % (sys.argv[3], len(blocks), sum(len(b.parts) for b in blocks),
                                                    len(data)))
    elif cmd == "dump":
        blocks = load(sys.argv[2])
        print("блоков %d, частей %d, экспериментальных %d" % (len(blocks), sum(len(b.parts) for b in blocks),
                                                               sum(1 for b in blocks if b.experimental)))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
