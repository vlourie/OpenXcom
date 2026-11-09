"""Pack a series' battle logs on the work machine for the analysis here: for every label <prefix>_* the game log of its work
folder (work/oxce_ai_probe/arena_<label>_w0/openxcom.log) as out/<label>/openxcom.log.gz, plus the arena's tables and
results, into one zip; the work folders stay as they are.

  python -I pack_logs.py <cmrun dir> <prefix> <out.zip>"""
import gzip
import sys
import zipfile
from pathlib import Path

R, PRE, OUT = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
W = R / "work" / "oxce_ai_probe"
n = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_STORED) as z:
    for d in sorted(W.glob(f"arena_{PRE}_*_w0")):
        label = d.name[len("arena_"):-len("_w0")]
        log = d / "openxcom.log"
        if not log.is_file():
            print("no log", label)
            continue
        z.writestr(f"out/{label}/openxcom.log.gz", gzip.compress(log.read_bytes(), 6))
        n += 1
    for p in sorted((W / "arena").glob(f"{PRE}_*")):
        if p.suffix in (".tsv", ".txt") and not p.name.endswith(".data_manifest.tsv"):
            z.write(p, f"arena/{p.name}")
print(f"logs {n} -> {OUT} {OUT.stat().st_size / 1e6:.1f} MB")
