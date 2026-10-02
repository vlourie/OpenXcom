"""The launcher voice "robot" at a 5.1 / 7.1 output (03.10, docs/research/voice-robot-2026-10-02.md): miniaudio's
duplex loop converted every piece for the device from the start of the callback's output. tools/voice_ma_patch.py
fixes it; this builds tools/voice_duplex_test.c (a fake device: playback f32 x N ch, capture mono, the client
s16 mono at 480 frames, a ramp through it) and checks the ramp arrives whole.
Control (R-086): the same test against a copy of miniaudio.h with the duplex patch taken out must break.
    py -3.13 tools/test_voice_duplex.py
Needs MSYS2 mingw64 gcc (tools/voice_deps.py GCC) and the patched miniaudio.h (py -3.13 tools/voice_deps.py --audio).
"""
import os, pathlib, subprocess, sys, tempfile

sys.stdout.reconfigure(encoding="utf-8")
TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import voice_ma_patch
from voice_deps import GCC

SRC = TOOLS / "voice_duplex_test.c"
HDR = voice_ma_patch.TARGET
# (playback channels, playback period, capture channels): the friend's X-Fi, 7.1, plain stereo, mono
CASES = [(6, 512, 1), (6, 480, 1), (8, 480, 1), (2, 480, 2), (2, 960, 1), (1, 480, 1)]
BROKEN = [(6, 512, 1), (8, 480, 1)]


def build(include: pathlib.Path, exe: pathlib.Path) -> None:
    env = {**os.environ, "PATH": f"{GCC.parent};" + os.environ.get("PATH", "")}
    subprocess.run([str(GCC), "-O1", f"-I{include}", "-o", str(exe), str(SRC), "-lole32", "-lwinmm"],
                   check=True, env=env, capture_output=True)


def run(exe: pathlib.Path, case) -> tuple[int, str]:
    p = subprocess.run([str(exe), *map(str, case)], capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout.strip()


def main() -> None:
    if not GCC.exists():
        raise SystemExit(f"no {GCC}: MSYS2 mingw64 is needed")
    text = HDR.read_text(encoding="utf-8")
    if voice_ma_patch.state(text, voice_ma_patch.MARK_DUPLEX, voice_ma_patch.DUPLEX_EDITS) != "applied":
        raise SystemExit(f"{HDR}: the duplex patch is not applied - py -3.13 tools/voice_deps.py --audio")
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        build(HDR.parent, tmp / "fixed.exe")
        for case in CASES:
            rc, out = run(tmp / "fixed.exe", case)
            ok = rc == 0
            fails += not ok
            print(f"{'ok  ' if ok else 'FAIL'} patched:   {out}")
        # control: the duplex patch taken out (replacements back to anchors) - the ramp must break
        raw = text
        for anchor, repl, _ in voice_ma_patch.DUPLEX_EDITS:
            assert raw.count(repl) == 1
            raw = raw.replace(repl, anchor)
        (tmp / "pristine").mkdir()
        (tmp / "pristine" / "miniaudio.h").write_text(raw, encoding="utf-8", newline="\n")
        build(tmp / "pristine", tmp / "pristine.exe")
        for case in BROKEN:
            rc, out = run(tmp / "pristine.exe", case)
            ok = rc == 1
            fails += not ok
            print(f"{'ok  ' if ok else 'FAIL'} unpatched: {out}  (must break)")
    print("passed" if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
