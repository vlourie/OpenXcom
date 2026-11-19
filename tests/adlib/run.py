"""Runs adlib_test: the damaged tracks one by one (each a process of its own), the fuzz, and - with a second executable
built from another tree - the comparison of the sound of the game's music.

  py -3 tests/adlib/run.py --exe build/adlib_test.exe [--old other/adlib_test.exe] [--cat bin/UFO/SOUND/ADLIB.CAT ...]
        [--fuzz 2000] [--expect-old-fails]

Exit code 0: every case of --exe ended cleanly, and the hashes of --exe and --old are the same."""
import argparse, subprocess, sys

def run(cmd, timeout=600):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return "hang", ""

def verdict(code, out):
    if code == "hang":
        return "HANG"
    if "AddressSanitizer" in out or "runtime error" in out:
        for line in out.splitlines():
            if "ERROR: AddressSanitizer" in line or "runtime error" in line:
                return "REPORT " + line.split("ERROR: ")[-1].strip()[:110]
    return "clean" if code == 0 else "exit %s" % code

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--old")
    ap.add_argument("--cat", nargs="*", default=[])
    ap.add_argument("--fuzz", type=int, default=0)
    a = ap.parse_args()
    bad = 0
    code, out = run([a.exe, "bad", "count"])
    n = int(out.strip())
    names = [l[5:] for l in run([a.exe, "bad"])[1].splitlines() if l.startswith("ok   ")]
    print("%-48s %-10s %s" % ("damaged track", "new", "old" if a.old else ""))
    for i in range(n):
        v = verdict(*run([a.exe, "bad", str(i)], 60))
        vo = verdict(*run([a.old, "bad", str(i)], 60)) if a.old else ""
        bad += v != "clean"
        print("%-48s %-10s %s" % (names[i] if i < len(names) else i, v, vo))
    for cat in a.cat:
        code, new = run([a.exe, "hash", cat])
        print("%s: %d tracks, %s" % (cat, len(new.splitlines()), verdict(code, new)))
        bad += code != 0
        if a.old:
            code2, old = run([a.old, "hash", cat])
            if code2 != 0:
                print("  the old player did not finish: %s" % verdict(code2, old))
            else:
                diff = [x for x, y in zip(new.splitlines(), old.splitlines()) if x != y]
                same = new == old
                print("  sound against the old player: %s" % ("the same on every track" if same else "DIFFERENT on %d tracks: %s" % (len(diff), " ".join(d.split()[0] for d in diff))))
                bad += not same
        if a.fuzz:
            for seed in range(1, 5):
                v = verdict(*run([a.exe, "fuzz", cat, str(seed), str(a.fuzz // 4)], 1800))
                vo = verdict(*run([a.old, "fuzz", cat, str(seed), str(a.fuzz // 4)], 1800)) if a.old else ""
                bad += v != "clean"
                print("  fuzz seed %d x%d: new %s%s" % (seed, a.fuzz // 4, v, (" | old " + vo) if a.old else ""))
    print("RESULT:", "PASS" if not bad else "FAIL (%d)" % bad)
    return 1 if bad else 0

sys.exit(main())
