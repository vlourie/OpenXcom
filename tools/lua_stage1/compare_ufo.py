import os, re, subprocess
from pathlib import Path

T = Path(os.environ["TEMP"])
for i in range(3):
    a = T / "oxce_bench_s1ufobase" / "xcom1" / f"hdtest{i:03d}"
    b = T / "oxce_bench_s1ufonew" / "xcom1" / f"hdtest{i:03d}"
    if not Path(str(a) + ".json").exists():
        continue
    r = subprocess.run(["py", "-3.13", "E:/OpenXCom/tools/hdtest_compare.py", str(a), str(b)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(i, [l.strip()[:60] for l in r.stdout.splitlines() if re.search("IDENTICAL|DIFF|RESULT", l)])
