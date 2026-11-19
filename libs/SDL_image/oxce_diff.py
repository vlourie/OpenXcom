# -*- coding: utf-8 -*-
"""Пересобирает OXCE.diff и SHA256SUMS после oxce_patch.py.
  py -3 libs/SDL_image/oxce_diff.py <папка с клоном ветки SDL-1.2>
Сравнение идёт без CR (в ветке часть файлов с CRLF), даты в заголовках не пишутся - файл не меняется от запуска к запуску."""
import difflib, hashlib, sys
from pathlib import Path

here = Path(__file__).resolve().parent
up = Path(sys.argv[1])
names = sorted(p.name for p in here.glob("IMG*.c")) + ["SDL_image.h", "COPYING", "CHANGES"]
out = []
for n in names:
    a = (up / n).read_bytes().decode("latin-1").replace("\r\n", "\n").splitlines(keepends=True)
    b = (here / n).read_bytes().decode("latin-1").replace("\r\n", "\n").splitlines(keepends=True)
    out += difflib.unified_diff(a, b, "a/" + n, "b/" + n)
(here / "OXCE.diff").write_bytes("".join(out).encode("latin-1"))
sums = ["%s *%s\n" % (hashlib.sha256((here / n).read_bytes()).hexdigest(), n)
        for n in sorted(p.name for p in here.glob("IMG*.c")) + ["IMG_oxce.h", "SDL_image.h", "COPYING", "CHANGES"]]
(here / "SHA256SUMS").write_bytes("".join(sums).encode("ascii"))
print("OXCE.diff: строк %d, файлов %d; SHA256SUMS: %d" % (len(out), sum(1 for l in out if l.startswith("--- a/")), len(sums)))
