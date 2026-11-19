"""Manifest of game data folders: relpath<TAB>size<TAB>sha256 for every file under the given roots of <base>.

  python -I hman.py <base> <out.tsv> <root> [root ...]"""
import hashlib
import os
import sys
from pathlib import Path

base, out, roots = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
rows = []
for r in roots:
    for dp, dn, fn in os.walk(base / r):
        dn.sort()
        for f in sorted(fn):
            p = Path(dp) / f
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for b in iter(lambda: fh.read(1 << 20), b""):
                    h.update(b)
            rows.append(f"{p.relative_to(base).as_posix()}\t{p.stat().st_size}\t{h.hexdigest()}")
out.write_text("\n".join(rows) + "\n", encoding="utf-8")
print(len(rows), "files")
