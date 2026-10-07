#!/usr/bin/env python3
"""Самый частый стек из hang.samples.json с ближайшими экспортами системных DLL (без PDB - это подсказка, не имя).

  py -3.13 tools/ai_speed/hang_stack.py tools/ai_speed/runs/hang.samples.json"""
import bisect, json, struct, sys
from collections import Counter
from pathlib import Path

from _common import ENC_R

SYS = Path("C:/Windows/System32")


def exports(path):
    d = path.read_bytes()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", d, opt)[0]
    ddir = opt + (112 if magic == 0x20B else 96)
    exp_rva = struct.unpack_from("<I", d, ddir)[0]
    secs = []
    so = opt + struct.unpack_from("<H", d, pe + 20)[0]
    for i in range(nsec):
        vs, va, rs, ro = struct.unpack_from("<IIII", d, so + 40 * i + 8)
        secs.append((va, max(vs, rs), ro))

    def off(rva):
        for va, size, ro in secs:
            if va <= rva < va + size:
                return rva - va + ro
        return None

    e = off(exp_rva)
    if e is None:
        return [], []
    nfun, nnam, afun, anam, aord = struct.unpack_from("<IIIII", d, e + 20)
    out = []
    for i in range(nnam):
        name_rva = struct.unpack_from("<I", d, off(anam) + 4 * i)[0]
        o = off(name_rva)
        name = d[o:d.index(b"\0", o)].decode("ascii", "replace")
        ordn = struct.unpack_from("<H", d, off(aord) + 2 * i)[0]
        out.append((struct.unpack_from("<I", d, off(afun) + 4 * ordn)[0], name))
    out.sort()
    return [a for a, _ in out], [n for _, n in out]


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    d = json.loads(Path(sys.argv[1]).read_text(encoding=ENC_R))
    mods = sorted((b, b + s, n) for b, s, n in d["mods"])
    stacks = Counter(tuple(st) for _, st in d["samples"])
    cache = {}
    for stack, n in stacks.most_common(8):
        print(f"--- {n} выборок из {len(d['samples'])}")
        for addr in stack:
            for b, e, name in mods:
                if b <= addr < e:
                    hint = ""
                    p = SYS / name
                    if p.is_file():
                        if name not in cache:
                            cache[name] = exports(p)
                        rvas, names = cache[name]
                        i = bisect.bisect_right(rvas, addr - b) - 1
                        if i >= 0:
                            hint = f"  ~ {names[i]}+0x{addr - b - rvas[i]:x}"
                    print(f"  {name}+0x{addr - b:x}{hint}")
                    break
            else:
                print(f"  0x{addr:x}")


if __name__ == "__main__":
    main()
