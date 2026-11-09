"""CONTACT_COORDINATION_V0: run 7 (load) against run 6 (save): the saved text, the role records, whether the roles went on after the load; and the tails of the short off runs: what is left over after the first difference (read only).
Usage: cc_load.py <res/out dir>"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
out = Path(sys.argv[1])


def read(d):
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


v, l = read(out / "cc6_CV_M3_s1"), read(out / "cc7_CL_M3_s1")
saved = next(s for s in v if s.startswith("[HIVESAVE]"))
k = dict(kv.findall(saved))
text = saved.split(" text=")[1]
recs = text.split(";")
print("saved turn", k["turn"], "hash", k["hash"], "bytes", k["bytes"], "squads", sum(r.startswith("S,") for r in recs), "orders", sum(r.startswith("O,") for r in recs), "role records", sum(r.startswith("R,") for r in recs))
print(" role records", [r for r in recs if r.startswith("R,")][:12])
print("run 7 errors", [s[:120] for s in l if s.startswith("[HIVELOAD] parsed=0") or "CRASH" in s or "Exception" in s][:3])
print(" load", [s[:80] for s in l if s.startswith("[HIVELOAD]")])
ld = next((s for s in l if s.startswith("[HIVELOAD] parsed=1")), None)
if ld:
    print(" text equal to saved", ld.split(" text=")[1] == text, "same", dict(kv.findall(ld))["same"])
print(" new army lines", sum(s.startswith("[HIVESQUAD] id=") for s in l))
sc = [dict(kv.findall(s)) for s in l if s.startswith("[HIVESAVECHECK]")]
print(" savecheck", len(sc), "same", sum(x["same"] == "1" for x in sc))
for name, L in (("run 6", v), ("run 7", l)):
    print("==", name, "decisions")
    for s in L:
        if s.startswith("[HIVECC]") and "event=DECISION" in s:
            d = dict(kv.findall(s))
            if int(d["turn"]) <= 7:
                print("  ", s[len("[HIVECC] "):][:230])
    print("   assign", Counter((dict(kv.findall(s))["from"], dict(kv.findall(s))["to"]) for s in L if s.startswith("[HIVECC]") and "event=ASSIGN" in s).most_common(8))
    print(" end", L[-1][:80])
print("== run 7 first ASSIGN rows")
for s in [x for x in l if x.startswith("[HIVECC]") and "event=ASSIGN" in x][:8]:
    print("  ", s[len("[HIVECC] "):][:170])
