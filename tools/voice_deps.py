"""Native parts of the launcher voice (docs/portal/VOICE_CHAT.md, part B) - kept out of git.

    py -3.13 tools/voice_deps.py                  download what is missing into portal/third_party/voice
    py -3.13 tools/voice_deps.py --from DIR       take the files from DIR instead of the internet
    py -3.13 tools/voice_deps.py --proto          generate C# from portal/src/Xp.Voice/protocol/*.proto
    py -3.13 tools/voice_deps.py --audio          build xpaudio.dll from native/xpaudio.c with MinGW gcc

Every download is pinned by version and SHA-256: a mismatch stops the script, nothing is replaced.
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

FFI_TAG = "livekit-ffi/v0.12.81"
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
    print(f"C#: {len(list(out.glob('*.cs')))} файлов из {len(files)} .proto")


def audio() -> None:
    if not GCC.exists():
        raise SystemExit(f"нет {GCC}: нужен MSYS2 mingw64 (tools/build/build_config.json, MsysBin)")
    if not (OUT / "miniaudio.h").exists():
        raise SystemExit("нет miniaudio.h - сначала py -3.13 tools/voice_deps.py")
    dll = OUT / "xpaudio.dll"
    # the runtime switch for IAudioClient3 (wasapi.noLowLatencySharedMode) - a small local patch, idempotent
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import voice_ma_patch
    print("miniaudio.h: " + ("patched" if voice_ma_patch.apply() else "already patched") + " (noLowLatencySharedMode)")
    # -static: the DLL must not need MinGW runtime DLLs next to the launcher
    cmd = [str(GCC), "-O2", "-shared", "-static", "-s", f"-I{OUT}", "-o", str(dll),
           str(VOICE / "native" / "xpaudio.c"), "-lole32", "-lwinmm"]
    env = {**os.environ, "PATH": f"{GCC.parent};" + os.environ.get("PATH", "")}
    subprocess.run(cmd, check=True, env=env)
    print(f"xpaudio.dll: {dll.stat().st_size / 1e3:.0f} КБ")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", type=str, default="", help="папка с уже скачанными файлами")
    ap.add_argument("--proto", action="store_true")
    ap.add_argument("--audio", action="store_true")
    a = ap.parse_args()
    # an empty --from means "download" (R-092: Path('') is the current directory)
    src = pathlib.Path(a.src) if a.src else None
    fetch(src)
    if a.proto:
        proto(src)
    if a.audio:
        audio()


if __name__ == "__main__":
    main()
