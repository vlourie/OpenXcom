"""The checks of .github/workflows/checks.yml run at home (Windows, MSYS2 in C:\\msys64):

    py -3 tools/ci_checks.py            tests of the pool (gcc; clang + ASan/UBSan), clang-tidy, cppcheck
    py -3 tools/ci_checks.py --game     the same and the game itself: build-release (gcc) and build-asan (clang)
    py -3 tools/ci_checks.py cppcheck   one step by its name

Needs no data of the game and starts no game. The exit code is the number of steps that failed.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MSYS = Path(os.environ.get("MSYS2_ROOT", r"C:\msys64"))
GCC = MSYS / "mingw64" / "bin"
CLANG = MSYS / "clang64" / "bin"

CPPCHECK_DEFINES = [
    "-D_WIN32", "-D__MINGW32__",
    "-DC4_SUPPRESS_WARNING_GCC_WITH_PUSH(x)=", "-DC4_SUPPRESS_WARNING_GCC_POP=",
    "-DSDL_VERSION_ATLEAST(a,b,c)=0",
]


def run(tools: Path, *cmd: str) -> bool:
    env = dict(os.environ)
    env["PATH"] = str(tools) + os.pathsep + env["PATH"]
    print("   >", " ".join(cmd), flush=True)
    # (Windows looks the program up in the PATH of this process, not in the one given to the child)
    program = shutil.which(cmd[0], path=env["PATH"])
    if not program:
        print("   no such program:", cmd[0], flush=True)
        return False
    return subprocess.run([program, *cmd[1:]], cwd=ROOT, env=env).returncode == 0


def tests(tools: Path, folder: str, *options: str) -> bool:
    return (run(tools, "cmake", "-S", "tests", "-B", folder, "-G", "Ninja", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", *options)
            and run(tools, "ninja", "-C", folder)
            and run(tools, "ctest", "--test-dir", folder, "--output-on-failure"))


def tests_gcc() -> bool:
    return tests(GCC, "build-tests")


def tests_asan() -> bool:
    return tests(CLANG, "build-tests-asan", "-DCMAKE_CXX_COMPILER=clang++", "-DHD_TEST_SANITIZE=address,undefined")


def tidy() -> bool:
    # over the compile commands of the clang build of the tests: the pool and its test
    if not (ROOT / "build-tests-asan" / "compile_commands.json").exists() and not tests_asan():
        return False
    return run(CLANG, "clang-tidy", "--quiet", "--config-file=tests/clang-tidy.yml", "-p", "build-tests-asan",
               "src/Engine/HdWorkers.cpp", "tests/hdworkers_test.cpp", "tests/hdgputold_test.cpp")


def cppcheck() -> bool:
    # the level "error" over the whole HD layer; what is not a defect is suppressed at its line in the code,
    # and tests/cppcheck-suppress.txt names the kinds for the code of others only
    files = sorted(glob.glob("src/Engine/Hd*.cpp", root_dir=ROOT))
    return run(GCC, "cppcheck", "-j", str(os.cpu_count() or 4), "--quiet", "--std=c++17", "--language=c++",
               "--error-exitcode=1", "--inline-suppr", "--suppressions-list=tests/cppcheck-suppress.txt",
               "--template={file}:{line}: {severity}: {id}: {message}", *CPPCHECK_DEFINES, *files)


def game_gcc() -> bool:
    return run(GCC, "ninja", "-C", "build-release", "openxcom")


def game_asan() -> bool:
    return run(CLANG, "ninja", "-C", "build-asan", "openxcom")


STEPS = {"tests-gcc": tests_gcc, "tests-asan": tests_asan, "tidy": tidy, "cppcheck": cppcheck}
GAME = {"game-gcc": game_gcc, "game-asan": game_asan}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("steps", nargs="*", choices=[[], *STEPS, *GAME], help="steps to run (all but the game by default)")
    ap.add_argument("--game", action="store_true", help="build the game too (build-release, build-asan)")
    args = ap.parse_args()
    names = args.steps or [*STEPS, *(GAME if args.game else [])]
    failed = []
    for name in names:
        print("==", name, flush=True)
        began = time.time()
        ok = {**STEPS, **GAME}[name]()
        print("== %s: %s, %.0f s" % (name, "ok" if ok else "FAILED", time.time() - began), flush=True)
        if not ok:
            failed.append(name)
    print("checks:", "all passed" if not failed else "FAILED: " + ", ".join(failed))
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
