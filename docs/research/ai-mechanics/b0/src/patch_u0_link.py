"""U0 build only: the fork's static MSYS2 link set (the same deps folder), nothing else in the build changes."""
import sys
from pathlib import Path

p = Path(sys.argv[1])
raw = p.read_bytes()
crlf = b"\r\n" in raw
t = raw.decode("utf-8").replace("\r\n", "\n")
old = "target_link_libraries ( openxcom ${system_libs} ${PKG_DEPS_LDFLAGS} ${EXTRA_XCOM_LIBS} ${WIN32_LIBS} )\n"
new = ("target_link_libraries ( openxcom ${system_libs} ${PKG_DEPS_LDFLAGS} ${EXTRA_XCOM_LIBS} ${WIN32_LIBS} -Wl,--start-group jpeg png z "
       "tiff webp mad vorbisfile vorbis -l:libogg.a mikmod -l:libwinpthread.a winmm dxguid dinput8 ole32 oleaut32 imm32 version setupapi "
       "jbig zstd lzma lerc deflate sharpyuv -l:libFLAC.dll.a -Wl,--end-group )\n")
assert t.count(old) == 1
t = t.replace(old, new)
p.write_bytes((t.replace("\n", "\r\n") if crlf else t).encode("utf-8"))
print("patched", p)
