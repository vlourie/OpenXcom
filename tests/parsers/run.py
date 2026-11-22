"""Writes the samples (valid and damaged files of the game's formats) and runs every case of parsers_test.cpp as a
process of its own.

  py -3 tests/parsers/run.py --exe <build>/bin/openxcom.exe [--old <old build>/bin/openxcom.exe] [--work <folder>]
        [--repeat 2000]

--exe  the build with the fixes (OXCE_PARSERS_TEST, sanitizers): every case must be handled
--old  the build of the tree before the fixes (old_tree.py): shown next to it, to prove the sample reaches the defect
Exit code 0: every case of --exe was handled and none leaks."""
import argparse, os, struct, subprocess, sys, tempfile, zlib

def png8(w, h, rows):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = b"".join(b"\0" + bytes(r) for r in rows)
    pal = b"".join(bytes((i, i, i)) for i in range(256))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0)) + chunk(b"PLTE", pal)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

def cat(records):
    """A CAT file: the table of offsets and sizes, then the records."""
    out, off = b"", 8 * len(records)
    for r in records:
        out += struct.pack("<II", off, len(r))
        off += len(r)
    return out + b"".join(records)

def wav(samples):
    data = bytes(samples)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 8000, 1, 8)
            + b"data" + struct.pack("<I", len(data)) + data)

def gm(tempo, subs, tracks):
    """A record of GM.CAT: a name, the tempo, the subsequences, the tracks (channel + sequence)."""
    out = bytes((0, tempo, len(subs)))
    for s in subs:
        out += struct.pack("<I", len(s) + 4) + bytes(s)
    out += bytes((len(tracks),))
    for ch, s in tracks:
        out += bytes((ch,)) + struct.pack("<I", len(s) + 4) + bytes(s)
    return out

NOTE = [0, 0xC0, 5, 0, 0x90, 0x40, 0x64, 0x10, 0x80, 0x40, 0, 0, 0xFF]
GM = {
    "gm_valid": gm(120, [], [(0, NOTE)]),
    "gm_valid_subsequence": gm(120, [[0, 0x90, 0x40, 0x64, 0, 0xFD]], [(0, [0, 0xFE, 0, 0, 0xFF])]),
    "gm_tempo_zero": gm(0, [], [(0, [0, 0xB0, 0, 60] + NOTE)]),
    "gm_length_past_end": bytes((0, 120, 1)) + struct.pack("<I", 0xFFFFFFF0) + bytes(8),
    # two tracks: the old code counts the first one's length off and reads the second one from behind the file
    "gm_track_length_past_end": bytes((0, 120, 0, 2, 0)) + struct.pack("<I", 0xFFFFFFF0) + bytes(8),
    "gm_subsequence_calls_itself": gm(120, [[0, 0xFE, 0]], [(0, [0, 0xFE, 0, 0, 0xFF])]),
    # 24 subsequences, each calls the next one 8 times: 8^23 calls that write nothing, the converter never ends
    "gm_subsequence_fanout": gm(120, [[0, 0xFE, i + 1] * 8 for i in range(23)] + [[0, 0xFD]], [(0, [0, 0xFE, 0, 0, 0xFF])]),
    "gm_patch_past_table": gm(120, [], [(0, [0, 0xC0, 0xF0, 0, 0x90, 0x40, 0x64, 0, 0xFF])]),
    "gm_name_longer_than_record": bytes((200, 1, 2)),
}

def write_samples(root):
    def put(rel, data):
        p = os.path.join(root, "common", rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    put("SOUND/SNDVALID.CAT", cat([b"\0" + wav([128 + (i % 16) for i in range(400)])]))
    # the short record is the last one: the old code reads and writes behind it, behind the buffer of the file
    put("SOUND/SNDSHORT.CAT", cat([b"\0" + wav([128] * 64), b"\0RIFF\x10\0\0\0WAVEfmt "]))
    put("GEODATA/DATVALID.DAT", bytes(32 * 40 * 2))
    put("GEODATA/DATSHORT.DAT", bytes(10))
    put("GEODATA/DATPARTIAL.DAT", bytes([7]) * (32 * 40) + bytes([9]) * (32 * 20))
    rows = [[(1 if (x + y) % 3 == 0 else 0) for x in range(24)] for y in range(8)]
    put("Language/FONTTEST.png", png8(24, 8, rows))
    put("MAPS/MAPVALID.MAP", bytes((10, 10, 2)) + bytes(4 * 200))
    put("MAPS/MAPEXTRA.MAP", bytes((10, 10, 2)) + bytes(4 * 260))
    put("MAPS/MAPFLAT.MAP", bytes((10, 10, 0)) + bytes(4 * 100))
    put("MAPS/MAPTAIL.MAP", bytes((10, 10, 2)) + bytes(4 * 200 + 1))
    put("MAPS/MAPSHORT.MAP", bytes((10, 10)))
    put("MAPS/MAPONE.MAP", bytes((10, 10, 1)) + bytes(4 * 100))
    put("MAPS/MAPONEEXTRA.MAP", bytes((10, 10, 1)) + bytes(4 * 200))
    # BLANKS: two MCD records of 62 bytes, one frame (32-bit TAB, a PCK that ends at once)
    put("TERRAIN/BLANKS.MCD", bytes(62 * 2))
    put("TERRAIN/BLANKS.TAB", bytes(4))
    put("TERRAIN/BLANKS.PCK", bytes((0, 255)))
    put("FLC/SHORT.FLC", bytes(6)) # the header is read to its 16th byte at least
    put("FLC/NOTFLC.FLC", bytes(200))
    # a mod in a .zip with HD interface pictures (case hdui_zip): 300 PNG of 2x-4x an 8x8 image, each with a block of
    # random bytes (the reads of a picture take a while) and its own palette (line j: i j 255-j)
    import random, zipfile
    rnd = random.Random(5)
    os.makedirs(os.path.join(root, "mods"), exist_ok=True)
    with zipfile.ZipFile(os.path.join(root, "mods", "hdzip.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("hdzip/", b"")
        z.writestr("hdzip/metadata.yml", "id: hdzip\nname: hdzip\nisMaster: true\n")
        for i in range(300):
            s = 8 * (2 + i % 3)
            pic = png8(s, s, [[(x + y) % 256 for x in range(s)] for y in range(s)])
            blob = bytes(rnd.getrandbits(8) for _ in range(24000))
            pic = pic[:-12] + struct.pack(">I", len(blob)) + b"zzZz" + blob + struct.pack(">I", zlib.crc32(b"zzZz" + blob) & 0xffffffff) + pic[-12:]
            z.writestr("hdzip/hd/UI/hdzip_%03d.png" % i, pic)
            z.writestr("hdzip/hd/UI/hdzip_%03d.pal.txt" % i, "".join("%d %d %d\n" % (i % 256, j, 255 - j) for j in range(256)))
    return put

def run(cmd, env, timeout=300):
    try:
        # the game looks for the folder 'common' from where it is started
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env, cwd=cmd[3])
        return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        return "hang", ((e.stdout or b"") + (e.stderr or b"")).decode("utf-8", "replace")

def verdict(code, out):
    if code == "hang":
        return "HANG"
    for line in out.splitlines():
        if "ERROR: AddressSanitizer" in line:
            return "REPORT " + line.split("AddressSanitizer: ")[1].split(" on ")[0].split(" (pc")[0][:60]
    for line in out.splitlines():
        if "runtime error:" in line:
            return "REPORT " + line.split("runtime error: ")[1][:60]
    for line in out.splitlines():
        if line.startswith("RESULT broken"):
            return "BROKEN " + line[15:75]
    if code != 0:
        return "CRASH exit %s" % (hex(code & 0xffffffff) if isinstance(code, int) else code)
    for line in out.splitlines():
        if line.startswith("RESULT handled"):
            return "ok: " + line[16:70]
    return "ok"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--old")
    ap.add_argument("--work")
    ap.add_argument("--repeat", type=int, default=2000)
    ap.add_argument("--only")
    a = ap.parse_args()
    work = a.work or tempfile.mkdtemp(prefix="oxce_parsers_")
    put = write_samples(work)
    # no window, no sound device; SDL must not take the output away into stdout.txt next to the exe
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", SDL_STDIO_REDIRECT="0",
               ASAN_OPTIONS="quarantine_size_mb=1:abort_on_error=0:detect_leaks=0", UBSAN_OPTIONS="print_stacktrace=0")
    code, out = run([a.exe, "--parsers-test", "list", work], env)
    names = [l.strip() for l in out.splitlines() if l.strip() and l.strip().replace("_", "").isalpha() and l.strip().islower()]
    if not names:
        print("the executable has no parsers test in it:\n" + out[-2000:])
        return 2
    jobs = []
    for n in names:
        if n == "gm":
            jobs += [(g, "gm") for g in GM]
        else:
            jobs.append((n, n))
    bad = 0
    print("%-30s | %-58s | %-12s | %s" % ("case", "with the fixes", "x%d" % a.repeat, "before the fixes" if a.old else ""))
    for label, case in jobs:
        if a.only and a.only not in label:
            continue
        if case == "gm":
            put("SOUND/GMTEST.CAT", cat([GM[label]]))
        v = verdict(*run([a.exe, "--parsers-test", case, work], env))
        rep = ""
        if v.startswith("ok") and a.repeat:
            c2, o2 = run([a.exe, "--parsers-test", case, work, "repeat", str(a.repeat)], env, 1800)
            v2 = verdict(c2, o2)
            grown = [l for l in o2.splitlines() if l.startswith("REPEAT")]
            rep = ("%s KiB" % grown[0].split(": ")[1].split(" ")[0]) if v2.startswith("ok") and grown else v2[:40]
            if not v2.startswith("ok"):
                bad += 1
        vo = verdict(*run([a.old, "--parsers-test", case, work], env)) if a.old else ""
        if not v.startswith("ok"):
            bad += 1
        print("%-30s | %-58s | %-12s | %s" % (label, v, rep, vo))
        sys.stdout.flush()
    print("RESULT:", "PASS" if not bad else "FAIL (%d)" % bad)
    return 1 if bad else 0

sys.exit(main())
