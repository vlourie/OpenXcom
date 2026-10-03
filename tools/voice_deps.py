"""Native parts of the launcher voice (docs/portal/VOICE_CHAT.md, part B) - kept out of git.

    py -3.13 tools/voice_deps.py                  download what is missing into portal/third_party/voice
    py -3.13 tools/voice_deps.py --from DIR       take the files from DIR instead of the internet
    py -3.13 tools/voice_deps.py --proto          generate C# from portal/src/Xp.Voice/protocol/*.proto
    py -3.13 tools/voice_deps.py --audio          build xpaudio.dll from native/xpaudio.c with MinGW gcc
    py -3.13 tools/voice_deps.py --check          0 if everything is there and built from today's sources, 1 if not

Every download is pinned by version and SHA-256: a mismatch stops the script, nothing is replaced.
--proto and --audio write what they were built from (*.inputs.sha256 next to the parts); --check
compares that with the sources in git, so a stale xpaudio.dll (one without a later miniaudio patch)
or C# from older .proto stops portal/publish.ps1 before the build, not the player after the release.
In the repository: the .proto files of livekit-ffi (126 KB) and xpaudio.c. Outside it, in
portal/third_party/voice: livekit_ffi.dll (25 MB), miniaudio.h (4 MB), protoc, the generated C#
(5.7 MB) and xpaudio.dll. Xp.Voice.csproj stops the build with this command if they are missing.
A new livekit-ffi: new FFI_TAG and SHA-256 here, its protocol/*.proto copied over, then --proto.
"""
import argparse
import hashlib
import io
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "portal" / "third_party" / "voice"
VOICE = ROOT / "portal" / "src" / "Xp.Voice"
GCC = pathlib.Path("C:/msys64/mingw64/bin/gcc.exe")
MA_PATCH = pathlib.Path(__file__).resolve().parent / "voice_ma_patch.py"
FIX = "py -3.13 tools\\voice_deps.py --proto --audio"

FFI_TAG = "livekit-ffi/v0.12.81"
# -static: the DLL must not need MinGW runtime DLLs next to the launcher;
# --no-insert-timestamp: the same sources give the same bytes on any build machine
AUDIO_FLAGS = ["-O2", "-shared", "-static", "-s", "-Wl,--no-insert-timestamp"]
# livekit_ffi.dll inside the pinned zip of FFI_TAG
FFI_DLL_SHA = "25ab07691a739ed41fd6a220d864a518ca8145cdc3695f050bfd9904034797e5"
FILES = {
    # name: (url, sha256)
    "ffi-windows-x86_64.zip": (f"https://github.com/livekit/rust-sdks/releases/download/{FFI_TAG}/ffi-windows-x86_64.zip",
                               "c242f1cde2c6ace38d3a12919e4b3ea49ef2f67fbf5d0a5bd3ad2b10be1f1086"),
    "miniaudio.h": ("https://raw.githubusercontent.com/mackron/miniaudio/0.11.25/miniaudio.h",
                    "ac7af4de748b7e26b777f37e01cee313a308a7296a3eb080e2906b320cc55c89"),
    "protoc.zip": ("https://github.com/protocolbuffers/protobuf/releases/download/v36.2/protoc-36.2-win64.zip",
                   "f0c128dc0d8492eceece83bb459a4c0e316764b929ffbf1aa416357fd644edd3"),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def obtain(name: str, src: pathlib.Path | None) -> bytes:
    url, want = FILES[name]
    if src is not None:
        data = (src / name).read_bytes()
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "xp-voice-deps"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
    got = sha(data)
    if got != want:
        raise SystemExit(f"{name}: SHA-256 {got} не совпал с закреплённым {want} - файл не тот, ничего не меняю")
    print(f"{name}: {len(data) / 1e6:.1f} МБ, SHA-256 совпал")
    return data


def stamp_lines(files: list[pathlib.Path]) -> list[str]:
    return [f"{sha(f.read_bytes())}  {f.name}" for f in files]


def proto_stamp() -> list[str]:
    return stamp_lines(sorted((VOICE / "protocol").glob("*.proto")))


def audio_stamp() -> list[str]:
    files = [VOICE / "native" / "xpaudio.c", OUT / "miniaudio.h", MA_PATCH]
    return stamp_lines(files) + [f"{sha(' '.join(AUDIO_FLAGS).encode())}  gcc-flags"]


def write_stamp(name: str, lines: list[str]) -> None:
    (OUT / name).write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")


def stamp_problem(name: str, what: str, lines: list[str]) -> str | None:
    p = OUT / name
    if not p.exists():
        return f"{what}: не записано, из чего собрано ({name})"
    was = p.read_text(encoding="ascii").split()
    now = " ".join(lines).split()
    if was == now:
        return None
    old = dict(zip(was[1::2], was[0::2]))
    new = dict(zip(now[1::2], now[0::2]))
    diff = sorted(n for n in old.keys() | new.keys() if old.get(n) != new.get(n))
    return f"{what}: собрано из других исходников - изменились {', '.join(diff)}"


def problems() -> list[str]:
    """What stops the launcher build: missing parts or parts built from older sources than in git."""
    out = []
    dll = OUT / "livekit_ffi.dll"
    if not dll.exists():
        out.append("нет livekit_ffi.dll")
    elif sha(dll.read_bytes()) != FFI_DLL_SHA:
        out.append(f"livekit_ffi.dll не из закреплённого {FFI_TAG}")
    if not (OUT / "generated" / "Ffi.cs").exists():
        out.append("нет C# из .proto (generated/Ffi.cs)")
    else:
        out.append(stamp_problem("proto.inputs.sha256", "C# из .proto", proto_stamp()))
    if not (OUT / "xpaudio.dll").exists():
        out.append("нет xpaudio.dll")
    elif not (OUT / "miniaudio.h").exists():
        out.append("нет miniaudio.h, из которого собрана xpaudio.dll")
    else:
        out.append(stamp_problem("xpaudio.inputs.sha256", "xpaudio.dll", audio_stamp()))
    return [p for p in out if p]


def check() -> int:
    bad = problems()
    if not bad:
        print(f"голос: части лаунчера в {OUT} на месте и собраны из нынешних исходников")
        return 0
    print(f"голос: части лаунчера в {OUT} не годятся для сборки:")
    for b in bad:
        print(f"  - {b}")
    print(f"починка: {FIX}")
    return 1


def fetch(src: pathlib.Path | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not (OUT / "livekit_ffi.dll").exists():
        z = zipfile.ZipFile(io.BytesIO(obtain("ffi-windows-x86_64.zip", src)))
        (OUT / "livekit_ffi.dll").write_bytes(z.read("livekit_ffi.dll"))
        (OUT / "LICENSE-livekit-ffi.md").write_bytes(z.read("LICENSE.md"))
    if not (OUT / "miniaudio.h").exists():
        (OUT / "miniaudio.h").write_bytes(obtain("miniaudio.h", src))
    for f in sorted(OUT.iterdir()):
        if f.is_file():
            print(f"  {f.name}  {f.stat().st_size / 1e6:.1f} МБ")


def proto(src: pathlib.Path | None) -> None:
    protoc = OUT / "protoc" / "bin" / "protoc.exe"
    if not protoc.exists():
        zipfile.ZipFile(io.BytesIO(obtain("protoc.zip", src))).extractall(OUT / "protoc")
    out = OUT / "generated"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.cs"):
        old.unlink()
    files = sorted(p.name for p in (VOICE / "protocol").glob("*.proto"))
    subprocess.run([str(protoc), f"--proto_path={VOICE / 'protocol'}", f"--csharp_out={out}",
                    "--csharp_opt=internal_access", *files], check=True)
    write_stamp("proto.inputs.sha256", proto_stamp())
    print(f"C#: {len(list(out.glob('*.cs')))} файлов из {len(files)} .proto")


def audio() -> None:
    if not GCC.exists():
        raise SystemExit(f"нет {GCC}: нужен MSYS2 mingw64 (tools/build/build_config.json, MsysBin)")
    if not (OUT / "miniaudio.h").exists():
        raise SystemExit("нет miniaudio.h - сначала py -3.13 tools/voice_deps.py")
    dll = OUT / "xpaudio.dll"
    # local patches, idempotent: the duplex-loop fix of the "robot" at a 5.1/7.1 output and the runtime
    # switch for IAudioClient3 (wasapi.noLowLatencySharedMode)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import voice_ma_patch
    print("miniaudio.h: " + ("patched" if voice_ma_patch.apply() else "already patched") + " (duplex loop, noLowLatencySharedMode)")
    cmd = [str(GCC), *AUDIO_FLAGS, f"-I{OUT}", "-o", str(dll),
           str(VOICE / "native" / "xpaudio.c"), "-lole32", "-lwinmm"]
    env = {**os.environ, "PATH": f"{GCC.parent};" + os.environ.get("PATH", "")}
    subprocess.run(cmd, check=True, env=env)
    write_stamp("xpaudio.inputs.sha256", audio_stamp())
    print(f"xpaudio.dll: {dll.stat().st_size / 1e3:.0f} КБ")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", type=str, default="", help="папка с уже скачанными файлами")
    ap.add_argument("--proto", action="store_true")
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--check", action="store_true", help="ничего не качать и не собирать, только проверить")
    a = ap.parse_args()
    if a.check:
        sys.exit(check())
    # an empty --from means "download" (R-092: Path('') is the current directory)
    src = pathlib.Path(a.src) if a.src else None
    fetch(src)
    if a.proto:
        proto(src)
    if a.audio:
        audio()


if __name__ == "__main__":
    main()
