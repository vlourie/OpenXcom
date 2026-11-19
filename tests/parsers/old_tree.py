"""The tree of a commit with the hook of tests/parsers put into its src/CMakeLists.txt: to show that the code BEFORE a fix
breaks on the same samples.  py -3 tests/parsers/old_tree.py <commit> <empty folder>"""
import io, os, subprocess, sys, tarfile

HOOK = """
# tests/parsers (put here by old_tree.py)
if ( OXCE_PARSERS_TEST )
  include ( "${OXCE_PARSERS_TEST}/hook.cmake" )
endif ()
"""

def main():
    commit, out = sys.argv[1], sys.argv[2]
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.makedirs(out, exist_ok=True)
    tar = os.path.join(out, "tree.tar")
    subprocess.check_call(["git", "-C", repo, "archive", "-o", tar, commit, "src", "libs", "cmake", "CMakeLists.txt", "res", "docs/CMakeLists.txt",
                           "LICENSE.txt", "README.md"])
    with tarfile.open(tar) as t:
        t.extractall(out)
    os.remove(tar)
    for d in ("common", "standard", "UFO", "TFTD"):  # the build copies the data folders next to the exe: empty ones do
        os.makedirs(os.path.join(out, "bin", d), exist_ok=True)
    p = os.path.join(out, "src", "CMakeLists.txt")
    s = io.open(p, encoding="utf-8", newline="").read()
    if "OXCE_PARSERS_TEST" not in s:
        a = s.index("add_executable ( openxcom ")
        b = s.index("\n", a) + 1
        s = s[:b] + HOOK.replace("\n", "\r\n" if "\r\n" in s else "\n") + s[b:]
        io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("tree of", commit, "in", out)

main()
