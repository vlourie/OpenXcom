#!/usr/bin/bash
# Builds imgdecode against SDL_image of libs/SDL_image (plain gcc and clang with ASan + UBSan) and, when they are
# there, against the old library: the package of MSYS2 as it is (libSDL_image.a) and its sources of 2012 with the
# sanitizers. Run from MSYS2 or Git Bash:
#   bash tests/sdl_image/build.sh <output folder> [folder of SDL_image-1.2.12 sources]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
NEW="$HERE/../../libs/SDL_image"
OUT="$1"; OLD="$2"
[ -n "$OUT" ] || { echo "usage: build.sh <output folder> [SDL_image-1.2.12 sources]"; exit 2; }
MSYS="${MSYS_ROOT:-/c/msys64}"
DEFS="-DLOAD_BMP -DLOAD_GIF -DLOAD_JPG -DLOAD_LBM -DLOAD_PCX -DLOAD_PNG -DLOAD_PNM -DLOAD_TGA -DLOAD_TIF -DLOAD_WEBP -DLOAD_XCF -DLOAD_XPM -DLOAD_XV"
SRCS="IMG.c IMG_bmp.c IMG_gif.c IMG_jpg.c IMG_lbm.c IMG_pcx.c IMG_png.c IMG_pnm.c IMG_tga.c IMG_tif.c IMG_webp.c IMG_xcf.c IMG_xpm.c IMG_xv.c"
LIBS="-ljpeg -lpng -ltiff -lwebp -lsharpyuv -lz -ljbig -lzstd -llzma -llerc -ldeflate -lpsapi"
SAN="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer"
mkdir -p "$OUT"

one() { # name, sources, toolchain, flags
	local name="$1" src="$2" tc="$3" flags="$4" cc="$MSYS/$3/bin/gcc"
	[ "$tc" = clang64 ] && cc="$MSYS/clang64/bin/clang"
	local obj="$OUT/obj_$name"; mkdir -p "$obj"
	for f in $SRCS; do
		PATH="$MSYS/$tc/bin:$PATH" "$cc" -c $flags $DEFS -w -I"$src" -I"$MSYS/$tc/include/SDL" "$src/$f" -o "$obj/${f%.c}.o"
	done
	PATH="$MSYS/$tc/bin:$PATH" "$cc" $flags -I"$src" -I"$MSYS/$tc/include/SDL" "$HERE/imgdecode.c" "$obj"/*.o \
		-o "$OUT/imgdecode_$name.exe" -L"$MSYS/$tc/lib" -lSDL $LIBS
	echo "built: imgdecode_$name.exe"
}

one new "$NEW" mingw64 "-O2"
one new_asan "$NEW" clang64 "$SAN"
if [ -f "$MSYS/mingw64/lib/libSDL_image.a" ]; then
	PATH="$MSYS/mingw64/bin:$PATH" gcc -O2 -I"$MSYS/mingw64/include/SDL" "$HERE/imgdecode.c" -o "$OUT/imgdecode_pkg.exe" -l:libSDL_image.a -lSDL $LIBS
	echo "built: imgdecode_pkg.exe (the package of MSYS2)"
fi
if [ -n "$OLD" ]; then
	# (the sources of 2012 do not agree with the pointer types of libpng 1.6 - clang makes that an error by default)
	one old_asan "$OLD" clang64 "$SAN -Wno-incompatible-function-pointer-types -Wno-incompatible-pointer-types"
fi
