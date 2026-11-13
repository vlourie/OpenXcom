"""TACTICAL TURN SOLVER: reading a battle save (line by line, formats from SavedBattleGame.cpp, Tile.cpp, MapDataSet.cpp)."""
import base64
import re
import struct
from pathlib import Path

MCD_SIZE = 62
# offsets of struct MCD in MapDataSet.cpp
F_LOFT, F_UFO, F_LOS, F_NOFLOOR, F_BIG, F_LIFT, F_DOOR, F_FIRE, F_TUW, F_ARMOR, F_TLEVEL, F_TYPE = 8, 30, 31, 32, 33, 34, 35, 36, 39, 42, 48, 53


class Save:
    def __init__(self, path):
        self.L = Path(path).read_text(encoding="utf-8", errors="surrogateescape").split("\n")
        self.bg = next(i for i, s in enumerate(self.L) if s == "battleGame:")
        self.key = {}
        for i in range(self.bg + 1, len(self.L)):
            m = re.match(r"^  (\w+):", self.L[i])
            if m:
                self.key[m.group(1)] = i
            elif self.L[i] and not self.L[i].startswith(" "):
                break
        self.w, self.l, self.h = (int(self.L[self.key[k]].split(":")[1]) for k in ("width", "length", "height"))
        self.bytes = int(self.L[self.key["tileTotalBytesPer"]].split(":")[1])
        self.sets = []
        i = self.key["mapdatasets"] + 1
        while self.L[i].startswith("    - "):
            self.sets.append(self.L[i][6:].strip())
            i += 1

    def block(self, name):
        """(first, past the last) lines of a list key"""
        a = self.key[name] + 1
        b = a
        while b < len(self.L) and (self.L[b].startswith("    ") or self.L[b].startswith("  - ")):
            b += 1
        return a, b

    def records(self, name):
        """list of (first line, past the last) of each record of a list key"""
        a, b = self.block(name)
        st = [i for i in range(a, b) if self.L[i].startswith("    - ")]
        return [(st[k], st[k + 1] if k + 1 < len(st) else b) for k in range(len(st))]

    def field(self, rec, name):
        for i in range(*rec):
            m = re.match(r"^(    - |      )" + name + r": (.*)$", self.L[i])
            if m:
                return m.group(2)
        return None

    def tiles(self):
        """{index: (ids[4], sets[4], smoke, fire, flags)}"""
        raw = base64.b64decode(self.L[self.key["binTiles"]].split(":", 1)[1].strip())
        out = {}
        for p in range(0, len(raw), self.bytes):
            r = raw[p:p + self.bytes]
            idx = struct.unpack_from("<i", r, 0)[0]
            ids = struct.unpack_from("<4h", r, 4)
            sets = struct.unpack_from("<4h", r, 12)
            out[idx] = (list(ids), list(sets), r[20], r[21], r[22])
        return out

    def pos(self, x, y, z):
        return x + y * self.w + z * self.w * self.l

    def store_tiles(self, tiles):
        parts = []
        for idx in sorted(tiles):
            t = tiles[idx]
            parts.append(struct.pack("<i4h4hBBB", idx, *t[0], *t[1], t[2], t[3], t[4]))
        self.L[self.key["binTiles"]] = "  binTiles: " + base64.b64encode(b"".join(parts)).decode()
        self.L[self.key["totalTiles"]] = f"  totalTiles: {len(parts)}"

    def write(self, path):
        Path(path).write_text("\n".join(self.L), encoding="utf-8", errors="surrogateescape", newline="\n")


def read_mcd(path):
    b = Path(path).read_bytes()
    return [b[i:i + MCD_SIZE] for i in range(0, len(b), MCD_SIZE)]
