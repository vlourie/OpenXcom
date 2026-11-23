# Parsers of mod data on damaged files

One set of minimal valid and damaged files for the parsers fixed in AUDIT-05 (stage G), run through the game's own
functions: `SoundSet::loadCatByIndex`, `GMCatFile::loadMIDI`, `ExtraSounds::loadSoundSet`, `SurfaceSet::loadDat`,
`Font::load`, `RuleTerrain::getMapData`, `DiscoverySource`, `InteractiveSurface::mouseRelease`,
`BattlescapeGenerator::loadMAP`, `FlcPlayer::init`. The Adlib player has a test of its own (`tests/adlib`).

`parsers_test.cpp` is linked into the game's executable in front of its `main()` (`hook.cmake`); the file gets its own
name, `oxce_parsers_test`, and is never the player's build. Every case is a process of its own, without a window
(SDL's dummy drivers), started by `run.py`, which also writes the samples.

## Build (clang64 of MSYS2, sanitizers)

    cmake -S . -B build-parsers -G Ninja -DCMAKE_BUILD_TYPE=Debug -DDEV_BUILD=ON -DBUILD_PACKAGE=OFF
      -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
      "-DCMAKE_CXX_FLAGS=-O1 -g -DNDEBUG -fsanitize=address,undefined -fno-omit-frame-pointer -isystem <repo>/build-asan/shim"
      "-DCMAKE_C_FLAGS=-O1 -g -fsanitize=address,undefined" -DCMAKE_EXE_LINKER_FLAGS=-LC:/msys64/clang64/lib
      -DOXCE_PARSERS_TEST=<repo>/tests/parsers
    ninja -C build-parsers

## Run

    py -3 tests/parsers/run.py --exe build-parsers/bin/oxce_parsers_test.exe [--old <old build>/bin/oxce_parsers_test.exe]

A case passes when the file is loaded or refused (an exception, an empty result) without a report of the sanitizers,
and when 2000 repeats of it do not make the memory of the process grow (a refusal leaves nothing half-made behind).

`--old` shows next to it what the code before the fixes does with the same sample - the proof that the sample reaches
the defect. The old tree is made by `old_tree.py <commit> <folder>` (the commit before the fix: `de443bd32` for
stage G) and built the same way with the same `-DOXCE_PARSERS_TEST`.

## What it does not cover

- `flc_not_video`: the test proves that `FlcPlayer::init` refuses the file. The defect itself was in the caller,
  `VideoState`, which played after a refused `init`; that state needs the whole game and is checked by reading only.
- The valid files here are minimal ones made by `run.py`, not the game's data: the game's own data is covered by the
  hidden bench (tools/hdbench.py).
