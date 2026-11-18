"""save_switch_asan_test.py [--no-build] [--rounds N]: the regression test of the change of the game under the screens
(audit: "double free when the save is changed"; the fix is Game::dropStates, commits 1cdb89471 and c95630305).

Before the fix a screen of the former game outlived its save: the stand's "open geoscape" from a base, "open
newbattle" from nested base windows, a save loaded over a battle - and the address sanitizer said heap-use-after-free.
The test plays those changes on the game built with ASan + UBSan (build-asan, clang64) on the hidden stand
and fails on any sanitizer report of the address
kind, on a death of the game and on a step the stand did not answer.

The game is never started from here directly: only tools/hdbench.py starts it, through tools/hidden_game.py - on the
hidden desktop (ai_probe.Hidden) with SDL_VIDEODRIVER=dummy, so no window appears on the screen (R-124).

It needs no saves of its own: it starts a new game, writes a geoscape save and a battle save with the stand's
"savefile" into the stand's user folder, and loads them back. It needs the game's data (bin/), so it runs at home,
not on GitHub. About 10 minutes; exit code 0 = passed.

  py -3 tools/save_switch_asan_test.py            build build-asan, run the scenes once
  py -3 tools/save_switch_asan_test.py --rounds 3 the quick ring of changes three times more after the scenes
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "build-release" / "bin"       # the game is run from the folder that has its data
EXE = BIN / "asan_game.exe"
NAME = "saveswitch"
CLANG = r"C:\msys64\clang64\bin"
PY = sys.executable
GEO, BATTLE = "saveswitch_geo.sav", "saveswitch_battle.sav"

ap = argparse.ArgumentParser()
ap.add_argument("--no-build", action="store_true", help="take build-asan/bin/openxcom.exe as it is")
ap.add_argument("--exe", default="", help="another sanitizer build of the game to test (implies --no-build)")
ap.add_argument("--rounds", type=int, default=1, help="how many times the quick ring of changes is played")
a = ap.parse_args()

env = dict(os.environ, PYTHONIOENCODING="utf-8", PATH=CLANG + os.pathsep + os.environ["PATH"],
           # symbolize=0: no symbolizer console; log_path is relative to the game's folder (a colon parts the options)
           ASAN_OPTIONS="log_path=sanrep symbolize=0", UBSAN_OPTIONS="log_path=sanrep print_stacktrace=1 symbolize=0")
env.pop("ASAN_SYMBOLIZER_PATH", None)
failed = []


def bench(*args, timeout=3000):
    r = subprocess.run([PY, str(ROOT / "tools" / "hdbench.py"), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT, timeout=timeout, env=env)
    return r.returncode, (r.stdout + r.stderr).strip()


def alive():
    code, out = bench("list")
    return any(l.startswith(NAME + ":") and "жив" in l for l in out.splitlines())


def scene(label, script, timeout=1800):
    code, out = bench("run", "--name", NAME, "--timeout", str(timeout), script)
    stack = (re.findall(r"stack=(\S+)", out) or ["?"])[-1]
    ok = code == 0 and alive() and "err " not in out
    print(f"{'PASS' if ok else 'FAIL'}  {label}: code {code}, stack {stack}" + ("" if ok else f"\n      {out[-400:]}"), flush=True)
    if not ok:
        failed.append(label)
    return ok


def reports():
    """The sanitizer reports of the run: (address errors, kinds of undefined behaviour)."""
    asan, ub = [], set()
    for f in sorted(BIN.glob("sanrep.*")):
        t = f.read_text(encoding="utf-8", errors="replace")
        asan += re.findall(r"ERROR: AddressSanitizer: (.{0,100})", t)
        ub |= {re.sub(r"0x[0-9a-f]+|\d{4,}", "N", m) for m in re.findall(r"^(?:\S*?/)?(src/\S+: runtime error: .{0,90})", t, re.M)}
        keep = ROOT / "build-asan" / ("saveswitch_" + f.name + ".txt")
        shutil.copy(f, keep)
        print("sanitizer report kept:", keep)
        f.unlink()
    return asan, sorted(ub)


if not a.no_build and not a.exe:
    r = subprocess.run(["ninja", "-C", str(ROOT / "build-asan"), "openxcom"], env=env, capture_output=True, text=True, errors="replace")
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-1000:])
        sys.exit("the sanitizer build failed (see docs/handbook/build.md for how build-asan is configured)")
built = Path(a.exe) if a.exe else ROOT / "build-asan" / "bin" / "openxcom.exe"
if not built.exists():
    sys.exit(f"no {built}: configure and build build-asan first")
shutil.copy(built, EXE)
for f in BIN.glob("sanrep.*"):
    f.unlink()

W = "wait 1500; state"
# the base screen: MANUFACTURE in the right column, then NEW PRODUCTION in its window (base pixels of a 480x270 screen)
NEST = "open base; wait 1500; click 336,164; wait 1500; state; click 158,219; wait 1500; state"
code, out = bench("start", "--name", NAME, "--exe", str(EXE), "--save", "", "--timeout", "3000", "--set", "oxceHdScale=4;oxceHdMode=2")
print(f"start [{code}] {out.splitlines()[-1][:160] if out else ''}", flush=True)
try:
    if code:
        failed.append("start")
    else:
        scene("new game: geoscape", f"open geoscape; {W}")
        scene("geoscape save written", f"savefile {GEO}; {W}")
        scene("base -> geoscape", f"open base; {W}; open geoscape; {W}")
        scene("base -> base", f"open base; {W}; open base; {W}")
        scene("base -> ufopaedia -> geoscape", f"open base; {W}; open ufopaedia; {W}; open geoscape; {W}")
        scene("base -> new battle screen -> geoscape", f"open base; {W}; open newbattle; {W}; open geoscape; {W}")
        scene("generated battle", "open battle; wait 12000; key enter; wait 6000; state")
        scene("battle save written", f"savefile {BATTLE}; {W}")
        scene("battle -> geoscape", f"open geoscape; {W}")
        scene("nested base windows", NEST)
        scene("nested base windows -> geoscape (a new game)", f"open geoscape; {W}")
        scene("nested base windows -> load the geoscape save", f"{NEST}; load {GEO}; wait 3000; state")
        scene("nested base windows -> new battle screen", f"{NEST}; open newbattle; {W}")
        scene("new battle screen: Cancel, main menu -> geoscape", f"key esc; {W}; open geoscape; {W}")
        scene("nested base windows -> generated battle", f"{NEST}; open battle; wait 12000; state")
        scene("battle -> load the battle save", f"load {BATTLE}; wait 4000; state")
        scene("loaded battle -> base", f"open base; {W}")
        scene("base -> load the battle save", f"load {BATTLE}; wait 4000; state")
        scene("loaded battle -> options -> ufopaedia", f"open options; {W}; open ufopaedia; {W}")
        scene("-> load the geoscape save", f"load {GEO}; wait 3000; state")
        ring = ("open base; wait 150; open geoscape; wait 150; open base; wait 150; open base; wait 150; open ufopaedia; wait 150; "
                "open newbattle; wait 150; open geoscape; wait 150; " + NEST.replace("1500", "150") + "; open geoscape; wait 150; "
                f"load {BATTLE}; wait 2500; open base; wait 150; load {GEO}; wait 1500; state")
        for i in range(a.rounds):
            scene(f"quick ring of changes, round {i + 1}", ring)
        bench("run", "--name", NAME, "quit")
finally:
    bench("stop", "--name", NAME, timeout=120)
asan, ub = reports()
for e in asan:
    print("ASan:", e)
for u in ub:
    print("UBSan:", u)
if asan:
    failed.append(f"{len(asan)} address sanitizer report(s)")
print(("FAILED: " + "; ".join(failed)) if failed else "PASSED: no address sanitizer report, every step answered")
sys.exit(1 if failed else 0)
