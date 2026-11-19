"""Runs every mode of crashtrace_test as a process of its own and checks the record it leaves.

  py -3 tests/crashtrace/run.py --exe <build-tests>/crashtrace_test.exe [--work <folder>]

Exit code 0: an exception gives named frames; every crash (main thread, second thread, division by zero, stack
overflow, a crash inside the notice) ends the process with code 1, leaves the record with frames in the log file, and
tools/crash_symbolize.py finds the crashing function by name."""
import argparse, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SYMBOLIZE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools", "crash_symbolize.py")

# mode: (the text of the record, a function the named frames must show, is the notice called)
CRASHES = {
    "segv": ("Segmentation fault. Reading 0x0", "readNowhere", True),
    "segv_thread": ("Segmentation fault. Reading 0x0", "readNowhere", True),
    "div0": ("Integer division by zero.", "divide", True),
    "overflow": ("Stack overflow.", "recurse", False),
    "second": ("Segmentation fault. Reading 0x0", "readNowhere", True),
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--work")
    a = ap.parse_args()
    work = a.work or tempfile.mkdtemp(prefix="oxce_crashtrace_")
    os.makedirs(work, exist_ok=True)
    bad = 0

    def check(name, ok, detail=""):
        nonlocal bad
        print("%-4s %s%s" % ("ok" if ok else "FAIL", name, (" - " + detail) if detail and not ok else ""))
        bad += 0 if ok else 1

    r = subprocess.run([a.exe, "exception"], capture_output=True, text=True, timeout=60)
    check("exception: caught, frames named", r.returncode == 0 and "throwInner" in r.stdout and "throwOuter" in r.stdout,
          r.stdout[-600:] + r.stderr[-300:])
    for mode, (text, func, noticed) in CRASHES.items():
        log = os.path.join(work, mode + ".log")
        if os.path.exists(log):
            os.remove(log)
        try:
            r = subprocess.run([a.exe, mode, log], capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            check(mode + ": the process ends", False, "hang")
            continue
        rec = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
        # a crash inside the notice is ended by the system itself, with the code of that crash
        check(mode + ": the process ends with an error code", r.returncode == 1 or (mode == "second" and r.returncode != 0),
              "exit %s" % r.returncode)
        check(mode + ": record in the log file", "Crash record: " + text in rec and rec.count("  #") >= 2, rec[-400:])
        check(mode + ": one record only", rec.count("Crash record:") == 1)
        check(mode + ": record on the error stream", "Crash record: " + text in r.stderr)
        check(mode + (": notice called" if noticed else ": no notice on what is left of the stack"),
              ("NOTICE" in r.stderr) == noticed)
        s = subprocess.run([sys.executable, SYMBOLIZE, log, "--exe", a.exe], capture_output=True, text=True)
        check(mode + ": the frames are named afterwards (%s)" % func, func in s.stdout, s.stdout[-600:] + s.stderr[-300:])
    r = subprocess.run([a.exe, "cost"], capture_output=True, text=True, timeout=120)
    print(r.stdout.strip())
    print("RESULT:", "PASS" if not bad else "FAIL (%d)" % bad)
    return 1 if bad else 0

sys.exit(main())
