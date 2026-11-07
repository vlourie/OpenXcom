#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""voice_deps --check: сборка лаунчера не берёт части голоса, собранные из прежних исходников.

Во временной папке, без загрузки и без gcc:
  * пустая папка - названы все три недостающие части;
  * части с записанными входами - проверка проходит;
  * правка xpaudio.c, заплатки miniaudio или новый .proto - проверка называет изменившийся файл;
  * чужая livekit_ffi.dll и отсутствие записи входов - отказ;
  * контроль: проверка только наличия (как Xp.Voice.csproj) пропускает устаревшую xpaudio.dll.

    py -3.13 tools/test_voice_deps.py
"""
import contextlib
import io
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import voice_deps as vd                 # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def said(word):
    return any(word in p for p in vd.problems())


tmp = pathlib.Path(tempfile.mkdtemp(prefix="vdeps_"))
try:
    vd.OUT = tmp / "third_party" / "voice"
    vd.VOICE = tmp / "Xp.Voice"
    vd.MA_PATCH = tmp / "voice_ma_patch.py"
    vd.OUT.mkdir(parents=True)
    (vd.VOICE / "protocol").mkdir(parents=True)
    (vd.VOICE / "native").mkdir()

    p = vd.problems()
    check("пустая папка: нет трёх частей", len(p) == 3 and said("livekit_ffi.dll") and said("Ffi.cs") and said("xpaudio.dll"))

    vd.FFI_DLL_SHA = vd.sha(b"ffi")
    (vd.OUT / "livekit_ffi.dll").write_bytes(b"ffi")
    (vd.OUT / "generated").mkdir()
    (vd.OUT / "generated" / "Ffi.cs").write_text("// c#", encoding="ascii")
    (vd.OUT / "xpaudio.dll").write_bytes(b"dll")
    (vd.OUT / "miniaudio.h").write_text("// ma noLowLatencySharedMode", encoding="ascii")
    for n in ("ffi.proto", "room.proto"):
        (vd.VOICE / "protocol" / n).write_text("syntax = \"proto2\";", encoding="ascii")
    (vd.VOICE / "native" / "xpaudio.c").write_text("int x;", encoding="ascii")
    vd.MA_PATCH.write_text("EDITS = []", encoding="ascii")

    check("без записи входов - отказ", said("не записано"))
    vd.write_stamp("proto.inputs.sha256", vd.proto_stamp())
    vd.write_stamp("xpaudio.inputs.sha256", vd.audio_stamp())
    check("собрано из нынешних исходников - проходит", vd.problems() == [])
    with contextlib.redirect_stdout(io.StringIO()):
        check("check() даёт 0", vd.check() == 0)

    (vd.VOICE / "native" / "xpaudio.c").write_text("int y;", encoding="ascii")
    check("правка xpaudio.c - названа", said("xpaudio.c"))
    with contextlib.redirect_stdout(io.StringIO()) as s:
        code = vd.check()
    check("check() даёт 1 и печатает починку", code == 1 and vd.FIX in s.getvalue())
    files_there = all((vd.OUT / n).exists() for n in ("livekit_ffi.dll", "xpaudio.dll", "generated/Ffi.cs"))
    check("контроль: по одному наличию устаревшая xpaudio.dll прошла бы", files_there and vd.problems() != [])
    (vd.VOICE / "native" / "xpaudio.c").write_text("int x;", encoding="ascii")

    vd.MA_PATCH.write_text("EDITS = ['new']", encoding="ascii")
    check("новая заплатка miniaudio - названа", said("voice_ma_patch.py"))
    vd.MA_PATCH.write_text("EDITS = []", encoding="ascii")

    flags = vd.AUDIO_FLAGS
    vd.AUDIO_FLAGS = flags + ["-DNEW"]
    check("новый флаг gcc - назван", said("gcc-flags"))
    vd.AUDIO_FLAGS = flags

    (vd.OUT / "miniaudio.h").write_text("// ma pristine", encoding="ascii")
    check("miniaudio.h без заплатки - названа", said("miniaudio.h"))
    (vd.OUT / "miniaudio.h").write_text("// ma noLowLatencySharedMode", encoding="ascii")

    (vd.VOICE / "protocol" / "rpc.proto").write_text("syntax = \"proto2\";", encoding="ascii")
    check("новый .proto - назван", said("rpc.proto"))
    (vd.VOICE / "protocol" / "rpc.proto").unlink()

    (vd.OUT / "livekit_ffi.dll").write_bytes(b"other")
    check("чужая livekit_ffi.dll - отказ", said("не из закреплённого"))
    (vd.OUT / "livekit_ffi.dll").write_bytes(b"ffi")

    check("после возврата всё снова проходит", vd.problems() == [])
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
