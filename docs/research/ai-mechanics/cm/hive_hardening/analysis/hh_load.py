"""HIVE hardening: runs 7 and 8 against run 6. The saved state and the loaded one line by line; the army after the load; and how the tail of the OFF run ends against D0 (read only).
Usage: hh_load.py <res/out dir of the logs> <D0 dir>"""
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
out = Path(sys.argv[1])


def read(d):
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


def recs(text):
    return text.split(";")


v, l7, l8 = read(out / "hh6_JV_M3_s1"), read(out / "hh7_HL_M3_s1"), read(out / "hh8_HL_M3_s1")
saved = next(s for s in v if s.startswith("[HIVESAVE]"))
k = dict(kv.findall(saved))
text = saved.split(" text=")[1]
print("saved turn", k["turn"], "hash", k["hash"], "bytes", k["bytes"], "squads", sum(r.startswith("S,") for r in recs(text)), "orders", sum(r.startswith("O,") for r in recs(text)), "contacts", sum(r.startswith("C,") for r in recs(text)))
for name, lines in (("run7", l7), ("run8", l8)):
    print("==", name, "lines", len(lines))
    print(" errors", [s[:120] for s in lines if s.startswith("[HIVELOAD] parsed=0") or "CRASH" in s or "Exception" in s][:3])
    print(" load", [s[:80] for s in lines if s.startswith("[HIVELOAD]")])
    print(" init", [s[:150] for s in lines if s.startswith("[HIVEINIT]")])
    print(" first", [s[:120] for s in lines if s.startswith("[HIVEFIRST]")])
    print(" new army lines", sum(s.startswith("[HIVESQUAD] id=") for s in lines))
    ld = next((s for s in lines if s.startswith("[HIVELOAD] parsed=1")), None)
    if ld:
        back = ld.split(" text=")[1]
        print(" text equal to saved", back == text, "hash", dict(kv.findall(ld))["hash"], "same", dict(kv.findall(ld))["same"])
    print(" commanders", [(dict(kv.findall(s))["turn"], dict(kv.findall(s))["squad"], dict(kv.findall(s))["old"], dict(kv.findall(s))["new"], dict(kv.findall(s))["task"]) for s in lines if s.startswith("[HIVECMD]")][:8])
    t = [dict(kv.findall(s)) for s in lines if s.startswith("[HIVESQUADTURN]")]
    for turn in sorted({int(x["turn"]) for x in t}):
        print("  t", turn, " ".join(f"{x['squad']}:{x['task'][0]}c{x['commander']}a{x['alive']}" for x in t if int(x["turn"]) == turn))
    sc = [dict(kv.findall(s)) for s in lines if s.startswith("[HIVESAVECHECK]")]
    print(" savecheck", len(sc), "same", sum(x["same"] == "1" for x in sc))
    print(" end", lines[-1][:80])
print("== run 6, after the save, the same turns")
t = [dict(kv.findall(s)) for s in v if s.startswith("[HIVESQUADTURN]")]
for turn in sorted({int(x["turn"]) for x in t}):
    if 4 <= turn <= 9:
        print("  t", turn, " ".join(f"{x['squad']}:{x['task'][0]}c{x['commander']}a{x['alive']}" for x in t if int(x["turn"]) == turn))
print("== tail of OFF against D0")
a = [s for s in read(out / "hh1_JO_M6_s1") if s.startswith(("[AIDECIDE]", "[AIEXEC]", "[AISTATE]", "[AICASUALTY]", "[AIREC]", "[AIPANIC]", "[AIAFTER]", "[AIPOSTWALK]", "[AIEVENT]"))]
print(" last 24 lines of OFF by tag", sorted({s.split(" ")[0] for s in a[-24:]}), "all AIAFTER with now=13", all('"now":13' in s for s in a[-24:] if s.startswith("[AIAFTER]")))
print(" last decide of OFF", next(s for s in reversed(a) if s.startswith("[AIDECIDE]"))[:80])
d = read(Path(sys.argv[2]))
print(" D0 has decisions", sum(s.startswith("[AIDECIDE]") for s in d))
