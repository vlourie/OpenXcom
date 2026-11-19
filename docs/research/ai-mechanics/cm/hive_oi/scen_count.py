"""OPERATIONAL INTELLIGENCE: how many logs of the archive scen.py really read: all logs against the D0 ones, the scenarios and seeds of the D0 ones. Read only.
Usage: scen_count.py <archive dir>"""
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
root = Path(sys.argv[1])
names = []
for z in sorted(root.glob("res_*.zip")):
    names += [n for n in zipfile.ZipFile(z).namelist() if n.endswith("openxcom.log.gz")]
d0 = [n for n in names if "_D_" in n]
print("all logs", len(names), "D0 logs", len(d0))
sc = Counter(re.search(r"_([ML]\d+)_", n).group(1) for n in d0)
print("scenarios", len(sc), "logs per scenario", sorted(set(sc.values())))
print("sample", d0[:2])
