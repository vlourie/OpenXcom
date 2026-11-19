"""Unzip a PowerShell Compress-Archive zip (backslash names) into a folder. usage: unz.py <zip> <dir>"""
import sys
import zipfile
from pathlib import Path

z, d = Path(sys.argv[1]), Path(sys.argv[2])
n = 0
with zipfile.ZipFile(z) as f:
    for i in f.infolist():
        name = i.filename.replace("\\", "/")
        if name.endswith("/"):
            continue
        dst = d / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(f.read(i))
        n += 1
print("files", n)
