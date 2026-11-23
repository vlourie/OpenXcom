#!/usr/bin/env python3
"""Execute the actual StartState intro decision in a C++ scenario harness.

The old condition is compiled separately as a mutation control. No game, SDL,
build tree or GPU is used. Requires g++ (configured MsysBin or PATH).

    py -3.13 tools/test_intro_startup.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = "(_oldMaster != Options::getActiveMaster() || playIntroAfterReload) && Options::playIntro"
CASES = [
    ("launcher-piratez", False, "piratez", "piratez", False, True),
    ("no-preselected-master", False, "", "piratez", False, True),
    ("launcher-xcom1", False, "xcom1", "xcom1", False, True),
    ("same-master-reload", True, "piratez", "piratez", False, False),
    ("changed-master-reload", True, "xcom1", "piratez", False, True),
    ("pending-intro-reload", True, "piratez", "piratez", True, True),
    ("pending-changed-master", True, "xcom1", "piratez", True, True),
]


def cxx():
    cfg = ROOT / "tools" / "build" / "build_config.json"
    candidates = []
    if cfg.exists():
        candidates.append(Path(json.loads(cfg.read_text(encoding="utf-8-sig"))["MsysBin"]) / "g++.exe")
    candidates.append(Path("C:/msys64/mingw64/bin/g++.exe"))
    found = shutil.which("g++")
    if found:
        candidates.append(Path(found))
    compiler = next((p for p in candidates if p.is_file()), None)
    if compiler is None:
        raise SystemExit("FAIL: g++ not found; intro decision was not tested")
    return compiler


def decision():
    source = (ROOT / "src" / "Menu" / "StartState.cpp").read_text(encoding="utf-8-sig")
    matches = re.findall(r"\bbool intro\s*=\s*([^;]+);\s*playIntroAfterReload\s*=\s*false;", source)
    if len(matches) != 1:
        raise SystemExit("FAIL: could not uniquely extract the real intro decision and pending reset")
    return f"bool intro = {matches[0]};\nplayIntroAfterReload = false;"


def harness(fragment):
    rows = []
    # Every scenario is also run with playIntro=false; expectations are explicit.
    for name, reload, old, active, pending, expected in CASES:
        for enabled in (True, False):
            values = (name + ("" if enabled else "-disabled"), reload, old, active, pending,
                      enabled, expected if enabled else False)
            rows.append("{" + ", ".join(json.dumps(v) for v in values) + "}")
    return """
#include <iostream>
#include <string>
namespace Options {
    bool reload, playIntro;
    std::string master;
    const std::string &getActiveMaster() { return master; }
}
bool decide(const std::string &_oldMaster, bool &playIntroAfterReload) {
""" + fragment + """
    return intro;
}
struct Case {
    const char *name;
    bool reload;
    const char *oldMaster, *activeMaster;
    bool pending, enabled, expected;
};
int main() {
    const Case cases[] = {
""" + ",\n".join(rows) + """
    };
    int failed = 0;
    for (const auto &c : cases) {
        Options::reload = c.reload;
        Options::playIntro = c.enabled;
        Options::master = c.activeMaster;
        bool pending = c.pending;
        if (decide(c.oldMaster, pending) != c.expected || pending) {
            std::cout << "FAIL " << c.name << '\\n';
            ++failed;
        }
        // The consumed pending flag must not replay the intro on the next reload.
        Options::reload = true;
        if (decide(c.activeMaster, pending) || pending) {
            std::cout << "FAIL repeated-" << c.name << '\\n';
            ++failed;
        }
    }
    return failed ? 1 : 0;
}
"""


def execute(tmp, compiler, name, fragment):
    source = Path(tmp) / (name + ".cpp")
    exe = Path(tmp) / (name + ".exe")
    source.write_text(harness(fragment), encoding="utf-8")
    env = dict(os.environ, PATH=str(compiler.parent) + os.pathsep + os.environ.get("PATH", ""))
    subprocess.run([str(compiler), "-std=c++17", "-Wall", "-Wextra", "-Werror", str(source),
                    "-o", str(exe)], env=env, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], env=env, capture_output=True, text=True, timeout=30)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"harness failed to run: {result.returncode}: {result.stderr}")
    return result


def main():
    fragment = decision()
    compiler = cxx()
    with tempfile.TemporaryDirectory(prefix="intro_startup_") as tmp:
        actual = execute(tmp, compiler, "actual", fragment)
        if actual.returncode:
            print(actual.stdout, end="")
            return 1
        control = execute(tmp, compiler, "old_condition", f"bool intro = {OLD};\nplayIntroAfterReload = false;")
    expected_failures = {"FAIL launcher-piratez", "FAIL launcher-xcom1"}
    if control.returncode != 1 or set(control.stdout.splitlines()) != expected_failures:
        print("FAIL: old-condition mutation did not fail the two launcher scenarios:", control.stdout)
        return 1
    print(f"PASS: actual C++ decision, {len(CASES) * 2} scenarios and subsequent reloads")
    print("PASS: old-condition mutation rejected for launcher-piratez and launcher-xcom1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
