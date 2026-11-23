"""UNIFIED ARMY SAFETY, read only: the results of the battles; who held the way out of the upper floor on M6 and on whose node he went; the rest of the idle on M3. Writes last.txt next to this file. Usage: us_last.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

HERE = Path(__file__).parent
out = open(HERE / "last.txt", "w", encoding="utf-8-sig")
sys.stdout.reconfigure(encoding="utf-8")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    out.write(s + "\n")


for run in ("us4_QO_M6_s1", "us5_QS_M6_s1", "ua1_UN_M6_s1", "us1_QN_M6_s1", "us6_QN_M6_s1", "ua6_UO_M3_s1", "ua2_UN_M3_s1", "us2_QN_M3_s1", "ua8_UO_M8_s1", "ua3_UN_M8_s1", "us3_QN_M8_s1"):
    r = [kv(s) for s in read(run) if s.startswith("[AIRESULT]")][-1]
    p(run, {k: r.get(k) for k in ("how", "turn", "pdead", "pwounded", "phplost", "hostile", "hdead", "hout", "hleft", "pattacks", "hattacks", "ms")})

p("===== ON us1: the choices of those who held the upper floor's way")
L = read("us1_QN_M6_s1")
for u in ("1000028", "1000033"):
    for s in L:
        if s.startswith("[HIVEUA] event=CHOICE") and f" unit={u} " in s:
            k = kv(s)
            if int(k["turn"]) <= 3:
                p(u, "t", k["turn"], "try", k["try"], "at", k["at"], "from", k["from"], "scout", k["scout"], "kind", k["kind"], "free", k["free"], "fl", k["free_linked"], "chosen", k["chosen"], "cl", k["chosen_linked"], "changed", k["changed"])
    p(u, "decisions", [(k["turn"], k["from"], "m" + k["mode"], "a" + k["act"], k["to"]) for k in (kv(s) for s in L if s.startswith("[AIDECIDE]") and f" unit={u} " in s) if int(k["turn"]) <= 3])
p("OFF")
L0 = read("us4_QO_M6_s1")
for u in ("1000028", "1000033"):
    p(u, "decisions", [(k["turn"], k["from"], "m" + k["mode"], "a" + k["act"], k["to"]) for k in (kv(s) for s in L0 if s.startswith("[AIDECIDE]") and f" unit={u} " in s) if int(k["turn"]) <= 3][:14])

p("===== M3 idle")
L = read("us2_QN_M3_s1")
for u in ("1000025", "1000040", "1000050"):
    ds = [kv(s) for s in L if s.startswith("[AIDECIDE]") and f" unit={u} " in s]
    p(u, "turns", sorted({int(d["turn"]) for d in ds}), [(d["turn"], d["from"], "m" + d["mode"], "a" + d["act"], "tu" + d["tu"]) for d in ds][:14])
out.close()
