"""AI FORGE WP2.1, final OFF: the provenance and the result in full: what differs from the archived D0 once the exe's identity, the time and ms= are named as such; the two logs in the OFF archive."""
import hashlib
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
with zipfile.ZipFile(rr.RES / "res_fxOFF.zip") as z:
    print("members", z.namelist())
    off = {k: z.read(f"arena/fxOFF_YO_L8_s1.{k}.txt").decode("utf-8", errors="replace") for k in ("prov", "result")}
with zipfile.ZipFile(rr.ARCHIVE_D0) as z:
    d0 = {k: z.read(f"arena/sfF_D_L8_s1.{k}.txt").decode("utf-8", errors="replace") for k in ("prov", "result")}
EXPECTED = ("=== provenance", "exe_sha256=", "exe_size=", "exe_mtime=", "exe_path=", "build_label=", "git_commit=")
a, b = off["prov"].replace("fxOFF_YO", "L").splitlines(), d0["prov"].replace("sfF_D", "L").splitlines()
print("prov lines", len(a), len(b))
for x, y in zip(a, b):
    if x != y and not x.startswith(EXPECTED):
        if x.startswith("fingerprint:"):
            xx, yy = re.sub(r"exe=[0-9a-f]+", "exe=X", x), re.sub(r"exe=[0-9a-f]+", "exe=X", y)
            print("fingerprint the same but for the exe:", xx == yy)
            if xx != yy:
                print(" ", xx, "\n ", yy)
            print(" ", xx[:500])
        else:
            print("OTHER", x[:400], "|", y[:400])
print("git_commit prefix", [s for s in a if s.startswith("git_commit")], [s for s in b if s.startswith("git_commit")])
ms = re.compile(r" ms=\d+")
x, y = off["result"].replace("fxOFF_YO", "L"), d0["result"].replace("sfF_D", "L")
print("result the same but for ms=:", ms.sub("", x) == ms.sub("", y))
for u, v in zip(ms.sub("", x).splitlines(), ms.sub("", y).splitlines()):
    if u != v:
        print(" ", u[:500], "\n ", v[:500])
print("stray and real archive differ:", hashlib.sha256((Path(__file__).resolve().parent / "stray" / "res_fxOFF.zip").read_bytes()).hexdigest()[:16], hashlib.sha256((rr.RES / "res_fxOFF.zip").read_bytes()).hexdigest()[:16])
