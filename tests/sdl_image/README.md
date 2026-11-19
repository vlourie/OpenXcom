# The decoding test of SDL_image

One program, `imgdecode`, reads a list of image files the way the game does (`IMG_Load_RW` from memory, no hint of
the type) and prints for every file what a caller can see of the `SDL_Surface`: size, bits per pixel, masks, colour
key, alpha, the palette (count and hashes) and a hash of the pixels. It is built against any SDL_image, so the old
and the new library are compared without the game.

    bash tests/sdl_image/build.sh <output folder> [folder of the SDL_image-1.2.12 sources of 2012]

builds `imgdecode_new.exe` (libs/SDL_image, gcc), `imgdecode_new_asan.exe` (libs/SDL_image, clang, ASan + UBSan -
the library itself is compiled with the sanitizers), `imgdecode_pkg.exe` (the package of MSYS2, when its
`libSDL_image.a` is installed) and `imgdecode_old_asan.exe` (the sources of 2012 with the sanitizers, when given:
`SDL_image-1.2.12.tar.gz`, SHA-256 `0b90722984561004de84847744d566809dbb9daf732a9e503b91a1b5a84e5699`).

`imgtest.py` drives it (a list is a text file, one full path a line, UTF-8):

    py -3 tests/sdl_image/imgtest.py compare <list> <old exe> <new exe> <output folder>
    py -3 tests/sdl_image/imgtest.py fuzz    <list> <asan exe> <output folder> <name>
    py -3 tests/sdl_image/imgtest.py time    <list> <exe> <repeats of the list>

- `compare`: valid files; every difference of the printed properties is listed by extension and kind.
- `fuzz`: damaged files; a file is either decoded or refused, anything else (a report of a sanitizer, a crash,
  no answer for `IMGTEST_HANG_S` seconds) is counted and the run goes on from the next file.
- `time`: decoding time and peak memory of the program on the list, three runs.

The lists are made by `img_inventory.py` (every image of the game folders by its signature, not by its extension)
and `make_corpus.py` (the valid samples of every format and their damaged copies: cut files, changed header fields,
flipped bytes). The samples of the formats are the test images of the upstream repository
(https://github.com/libsdl-org/SDL_image, `test/`); they are not kept here.

Two more lists are for the XCF decoder alone (OXCE patch 7, the read budget):

    py -3 tests/sdl_image/make_xcf_nested.py <out.xcf> <layers> [side]   one hostile file: every layer of the list
                                                                         is the same layer, every tile the same tile
    py -3 tests/sdl_image/make_xcf_valid.py <folder>                     28 well-formed files and list.txt

The hostile files go through `fuzz` and must be refused at once (before the patch: 1 s for 11 KiB, no end for
270 KiB); the well-formed ones go through `compare` against a build made before a change of the decoder and must
give no difference.

What the test says about the library taken into libs/SDL_image is written in `libs/SDL_image/README_OXCE.md`.
