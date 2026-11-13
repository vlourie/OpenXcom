"""COORDINATED OPERATION, phase A: which logs of M3, M11 and M2 exist in the battle archives, by archive, build label, scenario and seed. Only the names in the zips and folders. Read only."""
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
root = Path("E:/OXCE_AIWorker/battles_archive")
tab = defaultdict(set)
pat = re.compile(r"([^/]*?)_(M3|M11|M2)_s(\d+)(?:_[^/]*)?/[^/]*log\.gz$")
for a in sorted(root.iterdir()):
    zips = [a] if a.suffix == ".zip" else sorted(a.rglob("*.zip")) if a.is_dir() else []
    for z in zips:
        try:
            names = zipfile.ZipFile(z).namelist()
        except (zipfile.BadZipFile, OSError):
            continue
        for n in names:
            m = pat.search(n)
            if m:
                tab[(a.name, m.group(2), int(m.group(3)))].add(m.group(1))
    if a.is_dir():
        for p in a.rglob("*log.gz"):
            m = pat.search(p.as_posix())
            if m:
                tab[(a.name, m.group(2), int(m.group(3)))].add(m.group(1))
for k in sorted(tab):
    v = sorted(tab[k])
    print(k, len(v), v[:6])
