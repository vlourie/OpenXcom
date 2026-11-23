"""Names the frames of a crash record of the game's log ("[FATAL]  #3 exe+0x1a2b3c").

  py -3 tools/crash_symbolize.py <the log of the game> --exe <the exe that crashed>

The record is written inside the crashed process without any symbol library (src/Engine/CrashTrace.cpp), as offsets
into the exe. The names are found here, from THE SAME exe (the same release; the file is only read, never started):
the nearest symbol below the address in its symbol table (a build that keeps it) or its export table, plus file:line
from addr2line when the exe has debug information. Frames of other modules (module@0x...) are left as they are."""
import argparse, bisect, os, re, shutil, struct, subprocess, sys

def pe_symbols(path):
    """[(rva, name)] of the exe: the COFF symbol table when it is there, else the exports."""
    with open(path, "rb") as f:
        d = f.read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE file: " + path)
    nsec, _, symtab, nsym, optsize = struct.unpack_from("<HIIIH", d, pe + 6)
    opt = pe + 24
    magic = struct.unpack_from("<H", d, opt)[0]
    datadir = opt + (112 if magic == 0x20B else 96)
    sec0 = opt + optsize
    secs = []
    for i in range(nsec):
        vsize, va, rsize, raw = struct.unpack_from("<IIII", d, sec0 + 40 * i + 8)
        secs.append((va, max(vsize, rsize), raw))
    out = []
    if symtab and nsym:
        strtab = symtab + 18 * nsym
        i = 0
        while i < nsym:
            name, value, sec, _typ, cls, aux = struct.unpack_from("<8sIhHBB", d, symtab + 18 * i)
            if cls in (2, 3) and 0 < sec <= nsec:
                if name[:4] == b"\0\0\0\0":
                    o = strtab + struct.unpack_from("<I", name, 4)[0]
                    name = d[o:d.index(b"\0", o)]
                else:
                    name = name.rstrip(b"\0")
                if not name.startswith(b"."):
                    out.append((secs[sec - 1][0] + value, name.decode("latin-1")))
            i += 1 + aux
    if not out:
        def off(rva):
            for va, size, raw in secs:
                if va <= rva < va + size:
                    return rva - va + raw
            return None
        exp_rva = struct.unpack_from("<I", d, datadir)[0]
        e = off(exp_rva) if exp_rva else None
        if e is not None:
            nnames, funcs, names, ords = struct.unpack_from("<IIII", d, e + 24)
            f0, n0, o0 = off(funcs), off(names), off(ords)
            for i in range(nnames):
                no = off(struct.unpack_from("<I", d, n0 + 4 * i)[0])
                ordinal = struct.unpack_from("<H", d, o0 + 2 * i)[0]
                out.append((struct.unpack_from("<I", d, f0 + 4 * ordinal)[0], d[no:d.index(b"\0", no)].decode("latin-1")))
    out.sort()
    image_base = struct.unpack_from("<Q" if magic == 0x20B else "<I", d, opt + 24 if magic == 0x20B else opt + 28)[0]
    return out, image_base

def tool(name):
    return shutil.which(name) or shutil.which(name, path=r"C:\msys64\mingw64\bin")

def demangle(names):
    filt = tool("c++filt")
    if not filt or not names:
        return dict((n, n) for n in names)
    r = subprocess.run([filt], input="\n".join(names), capture_output=True, text=True)
    lines = r.stdout.splitlines()
    return dict(zip(names, lines)) if len(lines) == len(names) else dict((n, n) for n in names)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--exe", required=True)
    a = ap.parse_args()
    exe = a.exe
    if not os.path.exists(exe):
        print("the exe is not found: " + exe)
        return 2
    syms, image_base = pe_symbols(exe)
    rvas = [s[0] for s in syms]
    with open(a.log, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    frame = re.compile(r"#(\d+) exe\+0x([0-9a-fA-F]+)")
    found = []
    for line in lines:
        m = frame.search(line)
        if m:
            rva = int(m.group(2), 16)
            # every frame but the first is the address after a call: one byte back is inside the call
            look = rva if m.group(1) == "0" else rva - 1
            i = bisect.bisect_right(rvas, look) - 1
            found.append((line, rva, look, syms[i] if i >= 0 else None))
        elif "Crash record:" in line or "thrown at:" in line or re.search(r"#\d+ (module@|0x)", line):
            found.append((line, None, None, None))
    names = demangle(sorted(set(s[1] for _, _, _, s in found if s)))
    where = {}
    a2l = tool("addr2line")
    looks = sorted(set(l for _, _, l, s in found if s))
    if a2l and looks:
        r = subprocess.run([a2l, "-e", exe] + [hex(image_base + l) for l in looks], capture_output=True, text=True)
        got = r.stdout.splitlines()
        if len(got) == len(looks):
            where = dict((l, g) for l, g in zip(looks, got) if not g.startswith("??"))
    print("exe: %s (%d symbols)" % (exe, len(syms)))
    for line, rva, look, s in found:
        if rva is None:
            print(line.strip())
        elif s:
            print("%s  %s+0x%x%s" % (line.strip(), names[s[1]], rva - s[0], ("  " + where[look]) if look in where else ""))
        else:
            print(line.strip() + "  ?")
    return 0

sys.exit(main())
