"""save_switch_asan_test.py [--no-build] [--exe <game>] [--rounds N]: the regression test of the change of the game
under the screens (audit: "double free when the save is changed"; the fix is Game::dropStates, commits 1cdb89471 and
c95630305).

Before the fix a screen of the former game outlived its save: the stand's "open geoscape" from a base, "open
newbattle" from nested base windows, a save loaded over a battle - and the address sanitizer said heap-use-after-free.
The test plays those changes on the game built with ASan + UBSan (build-asan, clang64) on the hidden stand.

It FAILS on:
  - any report of the address sanitizer;
  - any report of the undefined behaviour sanitizer whose kind is not in KNOWN_UB below (a new one is a finding);
  - a step after which the screens of the game are not the ones expected (the stack of state classes is compared);
  - a step the stand did not answer, a death of the game, a [FATAL] line in the game's log;
  - a game that did not leave by itself when told to quit.

The game is never started from here directly: only tools/hdbench.py starts it, through tools/hidden_game.py - on the
hidden desktop (ai_probe.Hidden) with SDL_VIDEODRIVER=dummy, so no window appears on the screen (R-124).

Every run is its own: the stand, its user folder, the copy of the game, the saves and the sanitizer reports carry the
id of the run (process id + time), so two runs at once do not touch each other's files. The reports are kept in
build-asan/saveswitch_<id>/ with the stacks turned into names of functions and lines (llvm-symbolizer, after the run:
during it the sanitizer starts no helper, a helper would open a console).

It needs no saves of its own: it starts a new game, writes a geoscape save and a battle save with the stand's
"savefile" into the stand's user folder, and loads them back. It needs the game's data (bin/), so it runs at home,
not on GitHub. About 10 minutes; exit code 0 = passed.

  py -3 tools/save_switch_asan_test.py            build build-asan, run the scenes once
  py -3 tools/save_switch_asan_test.py --rounds 3 the quick ring of changes three times
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "build-release" / "bin"       # the game is run from the folder that has its data
CLANG = r"C:\msys64\clang64\bin"
PY = sys.executable
RUN = f"{os.getpid()}_{int(time.time())}"  # the id of this run
NAME = "saveswitch_" + RUN
EXE = BIN / f"asan_game_{RUN}.exe"
REPORTS = "sanrep_" + RUN                  # log_path of the sanitizers, relative to the game's folder
KEEP = ROOT / "build-asan" / NAME
USER = Path(tempfile.gettempdir()) / ("oxce_bench_" + NAME)
GEO, BATTLE = f"saveswitch_{RUN}_geo.sav", f"saveswitch_{RUN}_battle.sav"

# The kinds of undefined behaviour the game is known to report in these scenes, each with where it is written up.
# Empty: the scenes ran without one (18.11.2026). A line that is not here fails the test.
KNOWN_UB = [
    # r"src/Battlescape/Example\.cpp:\d+:\d+: runtime error: ...",   # docs/QA/...
]

ap = argparse.ArgumentParser()
ap.add_argument("--no-build", action="store_true", help="take build-asan/bin/openxcom.exe as it is")
ap.add_argument("--exe", default="", help="another sanitizer build of the game to test (implies --no-build)")
ap.add_argument("--rounds", type=int, default=1, help="how many times the quick ring of changes is played")
a = ap.parse_args()

env = dict(os.environ, PYTHONIOENCODING="utf-8", PATH=CLANG + os.pathsep + os.environ["PATH"],
           # symbolize=0: no symbolizer console; log_path is relative to the game's folder (a colon parts the options)
           ASAN_OPTIONS=f"log_path={REPORTS} symbolize=0",
           UBSAN_OPTIONS=f"log_path={REPORTS} print_stacktrace=1 symbolize=0")
env.pop("ASAN_SYMBOLIZER_PATH", None)
failed = []


def bench(*args, timeout=3000):
    r = subprocess.run([PY, str(ROOT / "tools" / "hdbench.py"), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT, timeout=timeout, env=env)
    return r.returncode, (r.stdout + r.stderr).strip()


def alive():
    code, out = bench("list")
    return any(l.startswith(NAME + ":") and "жив" in l for l in out.splitlines())


def scene(label, script, expect, timeout=1800):
    """Plays the script (it ends with "state") and compares the screens of the game with `expect`: the stack of the
    state classes, bottom first; a tuple - any of them (a screen that closes itself by its own timer)."""
    code, out = bench("run", "--name", NAME, "--timeout", str(timeout), script)
    stack = (re.findall(r"stack=(\S+)", out) or ["?"])[-1]
    wanted = expect if isinstance(expect, tuple) else (expect,)
    why = []
    if code:
        why.append(f"the stand answered with code {code}")
    if "err " in out:
        why.append("a command was refused")
    if stack not in wanted:
        why.append(f"the screens are {stack}, expected {' or '.join(wanted)}")
    if not alive():
        why.append("the game is not running")
    print(f"{'PASS' if not why else 'FAIL'}  {label}: {stack}" + ("" if not why else "\n      " + "; ".join(why) + f"\n      {out[-400:]}"), flush=True)
    if why:
        failed.append(label)
    return not why


def symbolized(text, exe):
    """The frames of the game in a report, as functions and lines (llvm-symbolizer; no console: CREATE_NO_WINDOW)."""
    offsets = sorted(set(re.findall(r"\(" + re.escape(str(exe)) + r"\+(0x[0-9a-f]+)\)", text, re.I)))
    tool = Path(CLANG) / "llvm-symbolizer.exe"
    if not offsets or not tool.exists():
        return ""
    try:
        r = subprocess.run([str(tool), "--obj=" + str(exe), "--output-style=LLVM", "--functions=linkage", "--demangle", "--inlines"],
                           input="\n".join(offsets) + "\n", capture_output=True, text=True, errors="replace", timeout=600,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"\n(the stacks could not be turned into names: {e})\n"
    blocks = [b.strip() for b in r.stdout.split("\n\n") if b.strip()]
    lines = ["", "==== the frames of the game by name (llvm-symbolizer) ===="]
    for off, block in zip(offsets, blocks):
        lines.append(f"+{off}: " + " <- ".join(l.strip() for l in block.splitlines()))
    return "\n".join(lines) + "\n"


def reports():
    """The sanitizer reports of the run, kept with their stacks: (address errors, new kinds of undefined behaviour,
    known kinds seen)."""
    asan, new, known = [], set(), set()
    for f in sorted(BIN.glob(REPORTS + ".*")):
        t = f.read_text(encoding="utf-8", errors="replace")
        asan += re.findall(r"ERROR: AddressSanitizer: (.{0,100})", t)
        for m in re.findall(r"^(?:\S*?[/\\])?(src[/\\]\S+: runtime error: .{0,120})", t, re.M):
            m = m.replace("\\", "/")
            kind = re.sub(r"0x[0-9a-f]+|(?<![:\d])\d{4,}", "N", m)
            (known if any(re.search(k, m) for k in KNOWN_UB) else new).add(kind)
        KEEP.mkdir(parents=True, exist_ok=True)
        (KEEP / (f.name + ".txt")).write_text(t + symbolized(t, EXE), encoding="utf-8")
        f.unlink()
    if KEEP.exists():
        print("sanitizer reports kept, with the stacks by name:", KEEP)
    return asan, sorted(new), sorted(known)


if not a.no_build and not a.exe:
    r = subprocess.run(["ninja", "-C", str(ROOT / "build-asan"), "openxcom"], env=env, capture_output=True, text=True, errors="replace")
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-1000:])
        sys.exit("the sanitizer build failed (see docs/handbook/build.md for how build-asan is configured)")
built = Path(a.exe) if a.exe else ROOT / "build-asan" / "bin" / "openxcom.exe"
if not built.exists():
    sys.exit(f"no {built}: configure and build build-asan first")
shutil.copy(built, EXE)

W = "wait 1500; state"
# the base screen: RESEARCH in the right column, then NEW PROJECT in its window (base pixels of a 480x270 screen)
NEST = "open base; wait 1500; click 336,164; wait 1500; state; click 158,219; wait 1500; state"
G, B = "GeoscapeState", "GeoscapeState>BasescapeState"
NESTED = B + ">ResearchState>NewResearchListState"
BATTLE_NEW = "BattlescapeState>NextTurnState>InventoryState"   # a generated battle: the briefing closed with Enter
BATTLE_LOADED = "GeoscapeState>BattlescapeState"
quit_ok = False
try:
    code, out = bench("start", "--name", NAME, "--exe", str(EXE), "--save", "", "--timeout", "3000", "--set", "oxceHdScale=4;oxceHdMode=2")
    print(f"start [{code}] {out.splitlines()[-1][:160] if out else ''}", flush=True)
    if code or "stack=MainMenuState" not in out:
        failed.append("start")
    else:
        scene("new game: geoscape", f"open geoscape; {W}", G)
        scene("geoscape save written", f"savefile {GEO}; {W}", G)
        scene("base -> geoscape", f"open base; {W}; open geoscape; {W}", G)
        scene("base -> base", f"open base; {W}; open base; {W}", B)
        scene("base -> ufopaedia -> geoscape", f"open base; {W}; open ufopaedia; {W}; open geoscape; {W}", G)
        scene("base -> new battle screen -> geoscape", f"open base; {W}; open newbattle; {W}; open geoscape; {W}", G)
        scene("generated battle", "open battle; wait 12000; key enter; wait 6000; state", BATTLE_NEW)
        scene("battle save written", f"savefile {BATTLE}; {W}", BATTLE_NEW)
        scene("battle -> geoscape", f"open geoscape; {W}", G)
        scene("nested base windows", NEST, NESTED)
        scene("nested base windows -> geoscape (a new game)", f"open geoscape; {W}", G)
        scene("nested base windows -> load the geoscape save", f"{NEST}; load {GEO}; wait 3000; state", G)
        scene("nested base windows -> new battle screen", f"{NEST}; open newbattle; {W}", "MainMenuState>NewBattleState")
        scene("new battle screen: Cancel, main menu -> geoscape", f"key esc; {W}; open geoscape; {W}", G)
        scene("nested base windows -> generated battle", f"{NEST}; open battle; wait 12000; state", "BriefingState")
        scene("battle -> load the battle save", f"load {BATTLE}; wait 4000; state", BATTLE_LOADED)
        scene("loaded battle -> base", f"open base; {W}", B)
        scene("base -> load the battle save", f"load {BATTLE}; wait 4000; state", BATTLE_LOADED)
        scene("loaded battle -> options -> ufopaedia", f"open options; {W}; open ufopaedia; {W}", "GeoscapeState>UfopaediaStartState")
        scene("-> load the geoscape save", f"load {GEO}; wait 3000; state", G)
        ring = ("open base; wait 150; open geoscape; wait 150; open base; wait 150; open base; wait 150; open ufopaedia; wait 150; "
                "open newbattle; wait 150; open geoscape; wait 150; " + NEST.replace("1500", "150") + "; open geoscape; wait 150; "
                f"load {BATTLE}; wait 2500; open base; wait 150; load {GEO}; wait 1500; state")
        for i in range(a.rounds):
            scene(f"quick ring of changes, round {i + 1}", ring, G)
finally:
    # the way out is a step of the test: "stop" tells the game to quit and says whether it left by itself
    was_alive = alive()
    code, out = bench("stop", "--name", NAME, timeout=120)
    quit_ok = was_alive and "вышел" in out and "не вышел" not in out
    print(f"{'PASS' if quit_ok else 'FAIL'}  the game quits by itself: {out.splitlines()[-1][:120] if out else ''}"
          + ("" if was_alive else " (it was not running at the end)"), flush=True)
    if not quit_ok:
        failed.append("the game did not quit by itself")
    asan, new_ub, known_ub = reports()
    log = USER / "openxcom.log"
    fatal = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if "[FATAL]" in l] if log.exists() else []
    if not log.exists():
        failed.append(f"no log of the game at {log}")
    for _ in range(20):  # the file of a game that has just left is let go a moment later
        try:
            EXE.unlink()
            break
        except FileNotFoundError:
            break
        except OSError:
            time.sleep(0.5)
    else:
        print("the copy of the game could not be removed:", EXE)
for e in asan:
    print("ASan:", e)
for u in new_ub:
    print("UBSan, NEW:", u)
for u in known_ub:
    print("UBSan, known:", u)
for l in fatal[:5]:
    print("FATAL in the log:", l[-200:])
if asan:
    failed.append(f"{len(asan)} address sanitizer report(s)")
if new_ub:
    failed.append(f"{len(new_ub)} new kind(s) of undefined behaviour")
if fatal:
    failed.append(f"{len(fatal)} [FATAL] line(s) in the game's log")
print(("FAILED: " + "; ".join(failed)) if failed else
      "PASSED: no sanitizer report, every step answered with the screens expected, the game quit by itself")
sys.exit(1 if failed else 0)
