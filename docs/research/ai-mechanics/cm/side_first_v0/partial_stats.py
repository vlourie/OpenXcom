"""SIDE-FIRST COMBAT V0.1: final_stats.py unchanged in its counting, on the missions the stopped series has. Builds one zip with D0 from sfF and the arm under test from the given zips under one prefix, then runs final_stats with MISSIONS narrowed.
args: out_dir name zip:prefix[,zip:prefix] (the XN battles), missions M3,L8"""
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
W = Path(__file__).parent
out_dir, name, sources, missions = sys.argv[1:5]
missions = missions.split(",")
P = "sfW"
target = Path(out_dir) / f"mix_{name}.zip"
with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as o:
    zd = zipfile.ZipFile(W / "res" / "res_sfF.zip")
    for m in missions:
        for s in (1, 2, 3, 4):
            o.writestr(f"out/{P}_D_{m}_s{s}/openxcom.log.gz", zd.read(f"out/sfF_D_{m}_s{s}/openxcom.log.gz"))
            o.writestr(f"arena/{P}_D_{m}_s{s}.tsv", zd.read(f"arena/sfF_D_{m}_s{s}.tsv"))
    for src in sources.split(","):
        zp, prefix = src.rsplit(":", 1)
        z = zipfile.ZipFile(zp)
        for m in missions:
            for s in (1, 2, 3, 4):
                if f"out/{prefix}_XN_{m}_s{s}/openxcom.log.gz" in z.namelist():
                    o.writestr(f"out/{P}_XN_{m}_s{s}/openxcom.log.gz", z.read(f"out/{prefix}_XN_{m}_s{s}/openxcom.log.gz"))
                    o.writestr(f"arena/{P}_XN_{m}_s{s}.tsv", z.read(f"arena/{prefix}_XN_{m}_s{s}.tsv"))
text = (W / "final_stats.py").read_text(encoding="utf-8")
marker = 'MISSIONS = ["M3", "M8", "L4", "L8"]'
if marker not in text:
    raise SystemExit("final_stats.py changed")
text = text.replace(marker, "MISSIONS = " + repr(missions))
script = Path(out_dir) / f"final_stats_{name}.py"
script.write_text(text, encoding="utf-8")
r = subprocess.run([sys.executable, "-I", str(script), str(target), P, str(Path(out_dir) / f"partial_{name}.json")], capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout)
print(r.stderr[-800:])
