# Сверка дампов и сейвов эталона и этапа 1: py -3.13 compare.py <имя A> <имя B>
import difflib, json, os, re, subprocess, sys
from pathlib import Path

A, B = [Path(os.environ["TEMP"]) / f"oxce_bench_{n}" / "piratez" for n in sys.argv[1:3]]
for i in range(0, 12):
    ja, jb = A / f"hdtest{i:03d}.json", B / f"hdtest{i:03d}.json"
    if not (ja.exists() and jb.exists()):
        continue
    r = subprocess.run(["py", "-3.13", "E:/OpenXCom/tools/hdtest_compare.py", str(A / f"hdtest{i:03d}"), str(B / f"hdtest{i:03d}")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.loads(ja.read_text(encoding="utf-8-sig"))
    lines = [l.strip()[:110] for l in r.stdout.splitlines() if re.search(r"IDENTICAL|DIFF|RESULT", l)]
    print(i, "mode", d.get("hdMode"), "k", d.get("k"), lines[:5])
sa = (A / "_quick_.asav").read_text(encoding="utf-8", errors="replace").splitlines()
sb = (B / "_quick_.asav").read_text(encoding="utf-8", errors="replace").splitlines()
print("save lines", len(sa), len(sb))
keys = {}
for l in difflib.unified_diff(sa, sb, lineterm="", n=0):
    if l[:1] in "+-" and l[:3] not in ("+++", "---"):
        k = l[1:].strip().split(":")[0]
        keys[k] = keys.get(k, 0) + 1
print("differing fields:", keys)
